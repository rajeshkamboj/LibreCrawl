# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for the LibreCrawl Windows desktop app.

Build (run on Windows, or let .github/workflows/build-windows.yml do it):

    pyinstaller --noconfirm --clean packaging/librecrawl.spec

Output:
    dist/LibreCrawl/LibreCrawl.exe   + bundled web UI and Python runtime

Design notes
------------
* onedir, not onefile. Chromium is ~200 MB and Playwright expects a real
  directory it can point at; unpacking that to a temp folder on every launch
  would add many seconds of start-up time.
* windowed (no console) because the app opens the UI in the browser. main.py
  installs a null/tee stdout so print() is safe without a console, and writes
  a log to %APPDATA%\\LibreCrawl\\logs.
* web/ is collected as data so Flask can find templates, static files and the
  plugin folder that the UI scans at runtime (/static/plugins/*.js).
* hidden imports cover modules the app imports lazily (inside functions), which
  PyInstaller's static analysis cannot see.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent

APP_NAME = 'LibreCrawl'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip() or '0.0.0'

# The web UI (templates, CSS/JS, plugins) is read from disk by Flask and by
# plugin-loader.js, so it has to sit in the bundle as plain files.
datas = [
    (str(ROOT / 'web'), 'web'),
    (str(ROOT / 'VERSION'), '.'),
]
datas += collect_data_files('waitress')       # waitress ships its own assets
datas += collect_data_files('flask_compress')

hiddenimports = [
    # Imported inside request handlers / crawler methods.
    'src.auth_db',
    'src.crawl_db',
    'src.email_service',
    'src.zoho_oauth',
    'src.settings_manager',
    'src.core.custom_extractor',
    'src.core.event_log',
    'src.core.issue_detector',
    'src.core.js_renderer',
    'src.core.link_manager',
    'src.core.memory_monitor',
    'src.core.memory_profiler',
    'src.core.ngram_analyzer',
    'src.core.rate_limiter',
    'src.core.seo_extractor',
    'src.core.sitemap_parser',
    # Third-party plugins that import things dynamically.
    'waitress',
    'waitress.server',
    'flask_compress',
    'playwright',
    'playwright.async_api',
    'playwright.sync_api',
    'greenlet',
    'bcrypt',
    'dotenv',
    'markdown',
    'openpyxl',
    'lxml',
    'lxml.etree',
    'lxml.html',
    'bs4',
    'psutil',
    'requests',
    'nest_asyncio',
    'email.mime.text',
    'email.mime.multipart',
    'sqlite3',
    'encodings.idna',
    'charset_normalizer',
]

# Trim obvious weight; these are build/runtime helpers we never use directly.
excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'IPython',
    'pytest',
    'PyQt5',
    'PySide2',
    'setuptools._distutils',
    'distutils',
]

block_cipher = None

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / 'packaging')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX on Playwright/DLLs causes crashes
    console=False,             # windowed desktop app; logs go to a file
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'packaging' / 'librecrawl.ico'),
    version=str(ROOT / 'packaging' / 'version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

# ---------------------------------------------------------------------------
# Optional: the Inno Setup installer is produced by an Inno Setup script that
# consumes dist/LibreCrawl/ (see packaging/installer.iss). Nothing to do here.
# ---------------------------------------------------------------------------
