import sys
from pathlib import Path


def _application_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = _application_root()
DATA_DIR = APP_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _data_file(filename):
    """이전 루트 DB가 있으면 data 폴더로 한 번만 자동 이전한다."""
    target = DATA_DIR / filename
    legacy = APP_ROOT / filename
    if legacy.exists() and not target.exists():
        legacy.replace(target)
    return target


PLAYERS_DB_PATH = _data_file("players.db")
SAVES_DB_PATH = _data_file("kbo_fm_saves.db")
