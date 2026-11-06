"""Filesystem locations for LibreCrawl, run from source or as a frozen app.

When the app is packaged with PyInstaller (the Windows .exe) two things break
if paths are derived from ``__file__``:

* read-only assets (templates, static files) live in the temporary directory
  PyInstaller unpacks the bundle into, and that directory vanishes on exit;
* the install directory (e.g. ``C:\\Program Files\\LibreCrawl``) is not writable
  by a normal user, so the SQLite database cannot be created there.

This module centralises both cases. Run from a checkout or inside Docker it
returns exactly the paths the app has always used, so nothing changes for
existing deployments.

The data location can be overridden with ``LIBRECRAWL_DATA_DIR`` (handy for a
portable install on a USB stick, or for tests).
"""
import os
import sys
from pathlib import Path

APP_NAME = 'LibreCrawl'
DATA_DIR_ENV = 'LIBRECRAWL_DATA_DIR'


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle (.exe)."""
    return bool(getattr(sys, 'frozen', False))


def resource_root() -> Path:
    """Directory that bundled read-only files are resolved against."""
    if is_frozen():
        # PyInstaller sets sys._MEIPASS to the unpacked bundle directory.
        return Path(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Absolute path to a bundled resource (templates, static, plugins...)."""
    return resource_root().joinpath(*parts)


def _default_data_dir() -> Path:
    """Per-user writable directory for the database and logs."""
    if not is_frozen():
        # Source checkout / Docker: keep the historical repo-relative data/
        # folder so docker-compose volume mounts and backups keep working.
        return resource_root() / 'data'

    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser(r'~\AppData\Roaming')
        return Path(base) / APP_NAME
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / APP_NAME
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return Path(base) / APP_NAME


def data_dir(create: bool = True) -> Path:
    """Writable directory holding users.db and crawl data."""
    override = os.environ.get(DATA_DIR_ENV)
    path = Path(override).expanduser().resolve() if override else _default_data_dir()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(create: bool = True) -> Path:
    """Path to the SQLite database shared by auth and crawl storage."""
    return data_dir(create=create) / 'users.db'


def log_dir(create: bool = True) -> Path:
    path = data_dir(create=create) / 'logs'
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


# --- Packaged-desktop helpers ----------------------------------------------

def bundled_chromium_env() -> bool:
    """Point Playwright at the Chromium shipped inside the app bundle.

    The Windows build installs Chromium next to the executable (under
    ``ms-playwright``) so JavaScript rendering works offline. Playwright only
    looks there when PLAYWRIGHT_BROWSERS_PATH says so; an explicit value from
    the user always wins.

    Returns True if the bundled browser directory exists and was selected.
    """
    if os.environ.get('PLAYWRIGHT_BROWSERS_PATH'):
        return False
    if not is_frozen():
        return False

    candidates = [
        Path(sys.executable).resolve().parent / 'ms-playwright',
        resource_root() / 'ms-playwright',
    ]
    for candidate in candidates:
        if candidate.is_dir():
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(candidate)
            return True

    # Nothing bundled: fall back to Playwright's normal per-user cache so a
    # user-run `playwright install chromium` still works.
    os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
    return False


def is_first_run() -> bool:
    """True when this is a fresh install (no database yet)."""
    return not db_path(create=False).exists()


def ensure_secret_key(env_path: Path = None) -> str:
    """Load or create a persistent SECRET_KEY for the packaged app.

    Without this, every launch would generate a new random key and log the
    user out (and invalidate existing sessions). The key is stored in the
    user's data directory, readable only by them.
    """
    env_path = env_path or (data_dir() / '.env')
    key = os.environ.get('SECRET_KEY')
    if key:
        return key

    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line.startswith('SECRET_KEY=') and not line.startswith('#'):
                value = line.split('=', 1)[1].strip().strip('"').strip("'")
                if value:
                    os.environ['SECRET_KEY'] = value
                    return value

    import secrets as _secrets
    key = _secrets.token_hex(32)
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        with open(env_path, 'a', encoding='utf-8') as handle:
            handle.write('\n# Generated by LibreCrawl; keeps logins valid across restarts.\n')
            handle.write(f'SECRET_KEY={key}\n')
        try:
            os.chmod(env_path, 0o600)
        except Exception:
            pass
    except Exception as exc:  # read-only location: session-only key
        print(f'Could not persist SECRET_KEY to {env_path}: {exc}')
    os.environ['SECRET_KEY'] = key
    return key
