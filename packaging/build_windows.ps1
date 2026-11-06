# Build the LibreCrawl Windows installer.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -SkipInstaller
#
# Output:
#   dist\LibreCrawl\LibreCrawl.exe             (the app itself, runs in place)
#   dist\installer\LibreCrawl-Setup-X.Y.Z.exe  (the downloadable installer)
#
# What it does:
#   1. installs Python dependencies
#   2. freezes the app with PyInstaller
#   3. downloads Chromium into dist\LibreCrawl\ms-playwright so JavaScript
#      rendering works offline (the user never runs "playwright install")
#   4. smoke tests the frozen exe (starts it, expects the UI to answer)
#   5. compiles the Inno Setup installer
#
# Must run on Windows: PyInstaller cannot cross-compile from Linux or macOS.

[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$SkipChromium,
    # Overrides the VERSION file (used by CI for tag builds).
    [string]$VersionOverride = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
Write-Host "==> Building LibreCrawl in $RepoRoot" -ForegroundColor Cyan

$Version = $VersionOverride
if (-not $Version) { $Version = (Get-Content (Join-Path $RepoRoot "VERSION") -Raw).Trim() }
if (-not $Version) { $Version = "0.0.0" }
Write-Host "==> Version $Version"

# --- 1. dependencies --------------------------------------------------------
Write-Host "==> Installing Python dependencies" -ForegroundColor Cyan
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install "pyinstaller>=6.6" pillow
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# --- 2. icon ----------------------------------------------------------------
Write-Host "==> Rendering icon" -ForegroundColor Cyan
& $Python packaging\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }

# --- 3. version resource ----------------------------------------------------
$parts = @($Version -split '\.')
while ($parts.Count -lt 4) { $parts += '0' }
$v0, $v1, $v2, $v3 = [int]$parts[0], [int]$parts[1], [int]$parts[2], [int]$parts[3]

$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($v0, $v1, $v2, $v3),
    prodvers=($v0, $v1, $v2, $v3),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'LibreCrawl'),
        StringStruct(u'FileDescription', u'LibreCrawl - SEO Spider'),
        StringStruct(u'FileVersion', u'$Version'),
        StringStruct(u'InternalName', u'LibreCrawl'),
        StringStruct(u'LegalCopyright', u'LibreCrawl contributors, MIT licensed'),
        StringStruct(u'OriginalFilename', u'LibreCrawl.exe'),
        StringStruct(u'ProductName', u'LibreCrawl'),
        StringStruct(u'ProductVersion', u'$Version'),
        StringStruct(u'Comments', u'https://librecrawl.com')
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
Set-Content -Path packaging\version_info.txt -Value $versionInfo -Encoding ASCII
Write-Host "==> Wrote packaging\version_info.txt for $Version"

# --- 4. freeze --------------------------------------------------------------
Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }
& $Python -m PyInstaller --noconfirm --clean packaging\librecrawl.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
if (-not (Test-Path "dist\LibreCrawl\LibreCrawl.exe")) {
    throw "PyInstaller did not produce dist\LibreCrawl\LibreCrawl.exe"
}

# --- 5. bundle Chromium -----------------------------------------------------
if (-not $SkipChromium) {
    Write-Host "==> Downloading Chromium for offline JavaScript rendering" -ForegroundColor Cyan
    $browsers = Join-Path $RepoRoot "dist\LibreCrawl\ms-playwright"
    New-Item -ItemType Directory -Force -Path $browsers | Out-Null
    # main.py points PLAYWRIGHT_BROWSERS_PATH here when the folder exists next
    # to the executable, so this is exactly where Playwright must install it.
    $env:PLAYWRIGHT_BROWSERS_PATH = $browsers
    & $Python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "playwright install chromium failed" }

    # Playwright >= 1.49 installs TWO browser builds: the full Chromium used
    # for headed rendering, and "chromium_headless_shell" used when
    # headless=True (LibreCrawl's default). Both are required -- deleting
    # either one makes launching fail with "Executable doesn't exist".
    $builds = (Get-ChildItem $browsers -Directory | Select-Object -ExpandProperty Name) -join ', '
    Write-Host "    installed browser builds: $builds"

    $chromiumMb = [math]::Round(((Get-ChildItem $browsers -Recurse -File |
                   Measure-Object -Property Length -Sum).Sum / 1MB), 1)
    Write-Host "==> Bundled Chromium: $chromiumMb MB"
} else {
    Write-Host "==> Skipping Chromium (-SkipChromium)" -ForegroundColor Yellow
}

# --- 6. smoke test ----------------------------------------------------------
Write-Host "==> Smoke testing the frozen executable" -ForegroundColor Cyan
$testPort = 5179
$dataDir = Join-Path $env:TEMP "librecrawl-smoke-$([guid]::NewGuid().ToString('N').Substring(0,8))"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$env:LIBRECRAWL_DATA_DIR = $dataDir
$proc = Start-Process -FilePath "dist\LibreCrawl\LibreCrawl.exe" `
    -ArgumentList "--no-browser", "--port", "$testPort" -PassThru
try {
    $ok = $false
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        if ($proc.HasExited) { break }
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$testPort/login" `
                -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200 -and $resp.Content -match "LibreCrawl") {
                $ok = $true
                break
            }
        } catch { }
    }
    if (-not $ok) {
        $log = Join-Path $dataDir "logs\librecrawl.log"
        if (Test-Path $log) { Get-Content $log -Tail 40 }
        throw "Packaged app did not answer on http://127.0.0.1:$testPort"
    }
    Write-Host "    app answered on http://127.0.0.1:$testPort" -ForegroundColor Green
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Remove-Item -Recurse -Force $dataDir -ErrorAction SilentlyContinue
    Remove-Item Env:\LIBRECRAWL_DATA_DIR -ErrorAction SilentlyContinue
}

# --- 7. installer -----------------------------------------------------------
if ($SkipInstaller) {
    Write-Host "==> Done. App folder: dist\LibreCrawl\LibreCrawl.exe" -ForegroundColor Green
    exit 0
}

Write-Host "==> Building installer with Inno Setup" -ForegroundColor Cyan
$iscc = $null
foreach ($candidate in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"))) {
    if (Test-Path $candidate) { $iscc = $candidate; break }
}
if (-not $iscc) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    throw "Inno Setup 6 not found. Install it (choco install innosetup) or rerun with -SkipInstaller."
}

& $iscc "packaging\installer.iss" "/DAppVersion=$Version" "/DSourceDir=$RepoRoot\dist\LibreCrawl"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }

$setup = Get-ChildItem "dist\installer\LibreCrawl-Setup-*.exe" |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { throw "Installer was not produced" }
$setupMb = [math]::Round($setup.Length / 1MB, 1)
Write-Host "==> Built $($setup.FullName) ($setupMb MB)" -ForegroundColor Green
