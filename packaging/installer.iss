; Inno Setup script for the LibreCrawl Windows desktop app.
;
; Compile after PyInstaller has produced dist\LibreCrawl\:
;
;   iscc packaging\installer.iss /DAppVersion=1.0.0 /DSourceDir=dist\LibreCrawl
;
; packaging\build_windows.ps1 and the GitHub Actions workflow do this for you.
; Requires Inno Setup 6 (https://jrsoftware.org/isdl.php).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

; Directory holding LibreCrawl.exe, the bundled Chromium and the web UI.
#ifndef SourceDir
  #define SourceDir "dist\LibreCrawl"
#endif

#define AppName "LibreCrawl"
#define AppPublisher "LibreCrawl"
#define AppUrl "https://librecrawl.com"
#define AppExeName "LibreCrawl.exe"

[Setup]
AppId={{8F3A6C1E-4B2D-4E77-9C1A-2F0B7D5E9A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
AppUpdatesURL={#AppUrl}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
; Per-user install by default (no UAC prompt), which keeps Playwright's
; Chromium cache, the database and the log file in %LOCALAPPDATA%/%APPDATA%.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=LibreCrawl-Setup-{#AppVersion}
SetupIconFile=librecrawl.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Chromium is a large tree of many small files.
CloseApplications=yes
RestartApplications=no
MinVersion=10.0
; Allow installing over a running copy is intentionally false: the database is
; in use. The user gets a clear "close LibreCrawl first" message instead.
AppMutex=LibreCrawlDesktop

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Everything PyInstaller produced: LibreCrawl.exe, the Python runtime, the web
; UI, and (because the build script stages it) ms-playwright\ with Chromium.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Launch once after install so first-run setup (database) happens immediately.
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Anything the app wrote inside its own install folder (should be nothing --
; data lives in %APPDATA% -- but be tidy if a user pointed PORT/logs here).
Type: filesandordirs; Name: "{app}\ms-playwright"
Type: dirifempty; Name: "{app}"

[Code]
const
  // Matches the named mutex main.py creates (CreateMutexW) while the desktop
  // server runs.
  AppMutexName = 'LibreCrawlDesktop';

function IsLibreCrawlRunning(): Boolean;
var
  Mutex: THandle;
begin
  Mutex := OpenMutex(SYNCHRONIZE, False, AppMutexName);
  Result := Mutex <> 0;
  if Result then
    CloseHandle(Mutex);
end;

// LibreCrawl is a long-running local server, so installing over a running copy
// would try to replace files that are in use. Ask the user to quit first (the
// app has a Quit button) instead of failing halfway through with a file-in-use
// error.
function InitializeSetup(): Boolean;
var
  Answer: Integer;
begin
  Result := True;
  while IsLibreCrawlRunning() do
  begin
    Answer := MsgBox('LibreCrawl is still running.' + #13#10#13#10 +
                     'Click Quit in the LibreCrawl browser window, then click Retry to continue.' + #13#10 +
                     'Any running crawl is saved before the app closes.',
                     mbError, MB_RETRYCANCEL);
    if Answer <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Hook for future data migrations (e.g. moving a legacy per-install folder).
end;
