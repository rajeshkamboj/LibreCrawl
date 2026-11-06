"""PyInstaller hook for the `playwright` package.

Why this is needed
------------------
Playwright is not a normal Python package: it drives a Node.js "driver"
directory that ships inside the installed wheel and is located at import time
from ``__file__``. PyInstaller only collects Python modules and known binaries,
so without this hook the frozen app starts fine but the first crawl with
JavaScript rendering fails with:

    playwright._impl._errors.Error: Executable doesn't exist at .../playwright/driver/node

What it collects
----------------
The whole ``playwright/driver`` tree (node + the JS driver package). The wheel
is platform specific, so this is already only the current OS's Node binary;
the Chromium browsers themselves are NOT here and are handled separately by
the build script, which installs them next to the executable and sets
PLAYWRIGHT_BROWSERS_PATH.

Usage: librecrawl.spec passes ``hookspath=['packaging']``, so PyInstaller picks
this file up automatically for any ``import playwright``.
"""
from pathlib import Path

from PyInstaller.utils.hooks import get_package_paths

# Python modules Playwright loads dynamically (it has plugin-style imports).
hiddenimports = [
    'playwright',
    'playwright.async_api',
    'playwright.sync_api',
    'playwright._impl',
    'playwright._impl._api_types',
    'playwright._impl._driver',
    'playwright._impl._connection',
    'playwright._impl._transport',
    'playwright._impl._errors',
    'greenlet',
    'pyee',
]

datas = []

_, package_dir = get_package_paths('playwright')
driver = Path(package_dir) / 'driver'
if driver.is_dir():
    # (dest_dir, source_dir) pairs are supported by PyInstaller, but an explicit
    # per-file list makes the collected tree obvious in the build log.
    for path in driver.rglob('*'):
        if path.is_file():
            # Dest must be the CONTAINING directory: (src_file, dest_dir).
            datas.append((str(path), str(Path('playwright') / path.parent.relative_to(package_dir))))
else:  # pragma: no cover - a broken install is not worth failing the build over
    print('[hook-playwright] WARNING: playwright driver directory not found; '
          'JavaScript rendering will not work in the packaged app')
