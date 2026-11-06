# Building the Windows installer

This folder turns LibreCrawl into a downloadable `LibreCrawl-Setup-x.y.z.exe`.

```
packaging/
├── librecrawl.spec      PyInstaller build definition (what goes in the bundle)
├── hook-playwright.py   PyInstaller hook: ships Playwright's Node driver
├── installer.iss        Inno Setup script (Windows integration, uninstaller)
├── build_windows.ps1    one-command build: deps → freeze → Chromium → installer
├── make_icon.py         generates librecrawl.ico / .png
└── version_info.txt     Windows file-version resource (rewritten per build)
```

The produced `.exe` runs LibreCrawl as a desktop app: a local-only server plus
the browser UI, with bundled Chromium so JavaScript rendering works offline.

---

## Build it (no Windows machine needed)

Push to `main`, tag a release, or run the workflow by hand:

**GitHub Actions → “Build Windows installer” → Run workflow**

It produces two artifacts:

| Artifact | What it is |
|---|---|
| `LibreCrawl-Setup-<version>` | The installer to distribute. |
| `LibreCrawl-portable-<version>` | The same app as a folder (for debugging). |

Tagging attaches the installer to a GitHub Release automatically:

```bash
git tag v1.2.0
git push origin v1.2.0
```

The version comes from the `VERSION` file, but a `v*` tag always wins, so the
tag and the file name never disagree.

## Build it locally (Windows)

Requirements: Python 3.11+, [Inno Setup 6](https://jrsoftware.org/isdl.php)
(`choco install innosetup`), and nothing else — the script installs its own
Python dependencies.

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

# app folder only, no installer
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -SkipInstaller

# smaller build without bundled Chromium (JS rendering then needs a manual
# "playwright install chromium" in %LOCALAPPDATA%\ms-playwright)
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -SkipChromium
```

Output:

```
dist\LibreCrawl\LibreCrawl.exe              the app (runs in place)
dist\LibreCrawl\ms-playwright\              bundled Chromium
dist\installer\LibreCrawl-Setup-1.0.0.exe   the installer
```

The script smoke-tests the frozen exe before packaging: it launches it on a
spare port against a temporary data directory and fails the build if the UI
does not answer. A broken build never reaches a release.

> PyInstaller cannot cross-compile. A Linux or macOS machine cannot produce a
> Windows `.exe`; use the workflow (which runs on `windows-latest`) instead.

---

## Design decisions

**onedir, not onefile.** Chromium is ~200 MB and Playwright needs a real
directory to point at. A onefile build would re-unpack all of that to a temp
folder on every launch, adding many seconds of start-up time.

**Windowed (no console).** With no console attached, Python sets `sys.stdout`
to `None` and the first `print()` would crash the app, so `main.py` installs a
null/tee stream and mirrors output to
`%APPDATA%\LibreCrawl\logs\librecrawl.log`.

**Data outside the install directory.** `Program Files` (and the per-user
`%LOCALAPPDATA%\Programs`) is not writable by the running user, so the SQLite
database lives in `%APPDATA%\LibreCrawl`. `src/app_paths.py` owns this rule and
keeps the old repo-relative `data/` folder when running from source or Docker,
so nothing changes for existing deployments. Set `LIBRECRAWL_DATA_DIR` to
point it somewhere else (e.g. a USB stick for a portable install).

**Local mode by default.** A packaged desktop app has no SMTP server and no
admin to approve accounts, so when `sys.frozen` is set the app forces
`--local`: no sign-in, admin access, no rate limits. Set `LOCAL_MODE=false` in
the environment to opt out.

**Localhost only.** The frozen build binds `127.0.0.1` rather than `0.0.0.0`,
so it is not silently exposed to the local network. `--host 0.0.0.0` shares it
deliberately.

**Persistent `SECRET_KEY`.** Generated once into `%APPDATA%\LibreCrawl\.env`;
without it every launch would invalidate the session cookie and log you out.

**Quit button.** A windowless app has no console to close, so the UI in
desktop mode posts to `/api/desktop/quit`, which saves running crawls and exits.
The route returns 404 outside a frozen build — a self-hosted server must never
be stoppable over HTTP.

**App mutex.** The running app holds the named mutex `LibreCrawlDesktop`; the
installer detects it and asks the user to click Quit instead of failing halfway
through with "file in use".

## Playwright's two moving parts

Packaging Playwright fails in two different ways, so both are handled:

1. **The Node driver** ships inside the wheel (`playwright/driver`, ~130 MB) and
   is located from `__file__`. PyInstaller copies only Python modules unless a
   hook says otherwise → `packaging/hook-playwright.py` collects the driver tree.
2. **Chromium itself** is not in the wheel at all. The build script installs it
   into `dist/LibreCrawl/ms-playwright`, and `src/app_paths.py` sets
   `PLAYWRIGHT_BROWSERS_PATH` to that folder when it exists next to the exe.

Playwright ≥ 1.49 installs **two** browser builds — full Chromium (headed
rendering) and `chromium_headless_shell` (used when `headless=True`, which is
LibreCrawl's default). Both must ship: deleting either one makes launching fail
with "Executable doesn't exist".

## Tests

```bash
python tests/packaging_tests.py
```

Covers the behaviour that only shows up once installed: `%APPDATA%` location,
`SECRET_KEY` persistence, bundled-Chromium detection, and template resolution
inside the PyInstaller bundle. No Windows machine or built exe required.

## Code signing

The installer is unsigned, so Windows SmartScreen shows "unrecognised app" on
first run. To sign it, add your certificate to the workflow after the build:

```yaml
- name: Sign installer
  run: |
    signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
      /f cert.pfx /p $env:CERT_PASSWORD dist/installer/LibreCrawl-Setup-*.exe
  env:
    CERT_PASSWORD: ${{ secrets.WINDOWS_CERT_PASSWORD }}
```

(Omit `/f`/`/p` and use `/a` to select a certificate from the store instead.)

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| App starts, no browser window | `--no-browser` was passed, or the default browser did not open. Visit `http://localhost:5000`. |
| "Port 5000 already in use" | Another process holds it. Launch with `--port 5001`. |
| JS rendering says Chromium is missing | The `ms-playwright` folder was deleted, or the app was copied without it. Reinstall, or run `python -m playwright install chromium`. |
| Installer refuses to continue | LibreCrawl is running. Click **Quit** in the browser window, then Retry. |
| Crashes on launch, no window | Read `%APPDATA%\LibreCrawl\logs\librecrawl.log` — the traceback is there. |
| Need to reset everything | Quit the app and delete `%APPDATA%\LibreCrawl`. |

## Publishing a release

```bash
# 1. bump the version
echo 1.0.1 > VERSION

# 2. commit, tag, push
git commit -am "Release 1.0.1"
git tag v1.0.1
git push origin main --tags
```

The workflow builds, smoke-tests and attaches
`LibreCrawl-Setup-1.0.1.exe` to the release. The README links to
`/releases/latest`, so no doc change is needed.
