"""Tests for the frozen-app (.exe) path handling.

The Windows installer ships the app as a PyInstaller bundle. Two things are
easy to break and impossible to notice until a user installs it:

  * data must go to %APPDATA%\\LibreCrawl, not next to the .exe (Program Files
    is read-only for normal users, so the database would fail to open);
  * the SECRET_KEY must be generated once and reused, or every restart logs
    the user out.

Run without a Windows machine or a built exe:

    python tests/packaging_tests.py
"""
import contextlib
import importlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSED, FAILED = [], []


def result(name, ok, detail=''):
    (PASSED if ok else FAILED).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{(' - ' + detail) if detail else ''}")


@contextlib.contextmanager
def simulated(frozen, platform, appdata):
    """Yield src.app_paths while pretending to be a frozen app on `platform`.

    sys.platform and sys.frozen are read at call time, so both have to stay
    patched for the whole body of the test, not just the import.
    """
    old_frozen = getattr(sys, 'frozen', None)
    had_frozen = hasattr(sys, 'frozen')
    real_platform = sys.platform
    old_appdata = os.environ.get('APPDATA')
    old_override = os.environ.pop('LIBRECRAWL_DATA_DIR', None)
    old_browser = os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
    old_secret = os.environ.pop('SECRET_KEY', None)
    old_executable = sys.executable

    sys.frozen = frozen
    sys.platform = platform
    if appdata:
        os.environ['APPDATA'] = str(appdata)
    try:
        import src.app_paths as app_paths
        yield importlib.reload(app_paths)
    finally:
        sys.platform = real_platform
        sys.executable = old_executable
        if had_frozen:
            sys.frozen = old_frozen
        else:
            sys.frozen = False          # attribute is checked with getattr
            del sys.frozen
        for key, value in (('APPDATA', old_appdata),
                           ('LIBRECRAWL_DATA_DIR', old_override),
                           ('PLAYWRIGHT_BROWSERS_PATH', old_browser),
                           ('SECRET_KEY', old_secret)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Leave the module describing a normal source checkout for other tests.
        sys.platform = real_platform
        importlib.reload(app_paths)


def test_source_checkout_keeps_repo_data_dir():
    repo_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp, \
            simulated(frozen=False, platform='linux', appdata=tmp) as paths:
        expected = repo_root / 'data'
        result('source checkout still uses <repo>/data',
               paths.data_dir(create=False) == expected, str(paths.data_dir(create=False)))
        result('source checkout db is <repo>/data/users.db',
               paths.db_path(create=False) == expected / 'users.db')
        result('frozen flag is False when not bundled', not paths.is_frozen())


def test_frozen_windows_uses_appdata():
    with tempfile.TemporaryDirectory() as tmp:
        appdata = Path(tmp) / 'Roaming'
        with simulated(frozen=True, platform='win32', appdata=appdata) as paths:
            expected = appdata / 'LibreCrawl'
            result('frozen Windows app writes to %APPDATA%\\LibreCrawl',
                   paths.data_dir(create=False) == expected, str(paths.data_dir(create=False)))
            result('frozen app creates the data directory on demand',
                   paths.data_dir(create=True).is_dir())
            result('frozen app puts users.db in the data directory',
                   paths.db_path(create=False) == expected / 'users.db')
            result('frozen app puts logs in the data directory',
                   paths.log_dir(create=True) == expected / 'logs')
            result('frozen flag is True when bundled', paths.is_frozen())
            result('install directory is never used for data',
                   'Program Files' not in str(paths.data_dir()))


def test_data_dir_override():
    with tempfile.TemporaryDirectory() as tmp:
        portable = Path(tmp) / 'portable'
        with simulated(frozen=True, platform='win32',
                       appdata=Path(tmp) / 'Roaming') as paths:
            os.environ['LIBRECRAWL_DATA_DIR'] = str(portable)
            result('LIBRECRAWL_DATA_DIR overrides the data location',
                   paths.data_dir() == portable.resolve(), str(paths.data_dir()))


def test_secret_key_persists():
    with tempfile.TemporaryDirectory() as tmp:
        with simulated(frozen=True, platform='win32',
                       appdata=Path(tmp) / 'Roaming') as paths:
            env_file = paths.data_dir() / '.env'

            first = paths.ensure_secret_key(env_path=env_file)
            result('a SECRET_KEY is generated on first launch',
                   len(first) == 64, f'{len(first)} chars')
            result('the key is written to the data directory', env_file.exists())

            # Simulate a restart: no env var, key must come back from disk.
            os.environ.pop('SECRET_KEY', None)
            second = paths.ensure_secret_key(env_path=env_file)
            result('the same key is reused after a restart (sessions survive)',
                   first == second)

            # An explicit environment variable must always win.
            os.environ['SECRET_KEY'] = 'explicit-from-environment'
            third = paths.ensure_secret_key(env_path=env_file)
            result('an explicit SECRET_KEY is respected',
                   third == 'explicit-from-environment')
            os.environ.pop('SECRET_KEY', None)


def test_bundled_chromium_detection():
    with tempfile.TemporaryDirectory() as tmp:
        with simulated(frozen=True, platform='win32',
                       appdata=Path(tmp) / 'Roaming') as paths:
            os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)

            # No bundle present: fall back to Playwright's own cache.
            result('no bundled Chromium leaves Playwright on its default path',
                   not paths.bundled_chromium_env()
                   and 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ)

            # Bundle present next to the executable.
            fake_exe_dir = Path(tmp) / 'app'
            (fake_exe_dir / 'ms-playwright').mkdir(parents=True)
            sys.executable = str(fake_exe_dir / 'LibreCrawl.exe')
            selected = paths.bundled_chromium_env()
            value = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
            result('bundled Chromium next to the .exe is used',
                   selected and value and Path(value).name == 'ms-playwright', str(value))

            # A user-supplied path must never be overwritten.
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = 'D:\\custom-browsers'
            result('a user-set PLAYWRIGHT_BROWSERS_PATH wins',
                   paths.bundled_chromium_env() is False
                   and os.environ['PLAYWRIGHT_BROWSERS_PATH'] == 'D:\\custom-browsers')
            os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)


def test_resource_paths_follow_meipass():
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / '_MEI12345'
        (bundle / 'web' / 'templates').mkdir(parents=True)
        real_meipass = getattr(sys, '_MEIPASS', None)
        sys._MEIPASS = str(bundle)
        try:
            with simulated(frozen=True, platform='win32',
                           appdata=Path(tmp) / 'Roaming') as paths:
                result('templates resolve inside the PyInstaller bundle',
                       paths.resource_path('web', 'templates') == bundle / 'web' / 'templates')
                result('resource root is the unpacked bundle',
                       paths.resource_root() == bundle)
        finally:
            if real_meipass is None:
                del sys._MEIPASS
            else:
                sys._MEIPASS = real_meipass


def load_hook(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pyinstaller_hook_collects_playwright_driver():
    """The Playwright hook must ship a valid (src_file, dest_dir) data list.

    A first CI attempt shipped 118 driver files whose `dest` was the file path
    instead of its folder, so PyInstaller tried to create a directory named
    LICENSE where a file already existed and aborted the whole build.
    """
    hook_path = Path(__file__).resolve().parent.parent / 'packaging' / 'hook-playwright.py'
    result('the Playwright hook exists', hook_path.is_file())
    if not hook_path.is_file():
        return

    hook = load_hook(hook_path, 'hook_playwright')
    result('hook exposes hiddenimports', bool(hook.hiddenimports))
    result('hook collects playwright driver data', len(hook.datas) > 0,
           f'{len(hook.datas)} entries')

    if importlib.util.find_spec('playwright') is None:
        result('playwright driver entry shape is valid', True, 'skipped, playwright not installed')
        return

    import playwright
    site_packages = Path(playwright.__file__).resolve().parent.parent

    # Every dest must be an existing directory and must be the file's parent.
    not_a_dir = [d for _, d in hook.datas if not (site_packages / d).is_dir()]
    result('every dest is a directory, never a file path', not not_a_dir, str(not_a_dir[:2]))

    wrong_parent = [(src, d) for src, d in hook.datas
                    if Path(src).parent != (site_packages / d)]
    result('each file lands in its own directory', not wrong_parent, str(wrong_parent[:2]))

    # (dest, filename) collisions make PyInstaller abort.
    seen, collisions = set(), []
    for src, dest in hook.datas:
        key = (dest, Path(src).name)
        if key in seen:
            collisions.append(key)
        seen.add(key)
    result('no two files claim the same destination', not collisions, str(collisions[:2]))

    result('the node driver binary is collected',
           any(Path(src).name == 'node' for src, _ in hook.datas))


def main():
    for test in (test_source_checkout_keeps_repo_data_dir,
                 test_frozen_windows_uses_appdata,
                 test_data_dir_override,
                 test_secret_key_persists,
                 test_bundled_chromium_detection,
                 test_resource_paths_follow_meipass,
                 test_pyinstaller_hook_collects_playwright_driver):
        print(f'\n{test.__name__}:')
        test()

    print('\n' + '=' * 60)
    print(f'  {len(PASSED)} passed, {len(FAILED)} failed')
    if FAILED:
        print('  failed: ' + ', '.join(FAILED))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
