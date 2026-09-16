"""선수 ID를 로컬 고화질 원본 사진에 연결한다."""

import csv
from functools import lru_cache
from pathlib import Path

from database.paths import APP_ROOT, DATA_DIR


PLAYER_PHOTO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
PLAYER_PHOTO_DIRECTORIES = (
    APP_ROOT / "image" / "players" / "local" / "highres-originals",
    APP_ROOT / "image" / "players" / "local" / "game-ready",
    APP_ROOT / "image" / "players" / "local",
)


@lru_cache(maxsize=1)
def _roster_photo_ids():
    roster_path = DATA_DIR / "source" / "kbo_2025_final_roster.csv"
    if not roster_path.exists():
        return {}
    by_identity = {}
    with roster_path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            player_id = str(row.get("kbo_player_id") or "").strip()
            name = str(row.get("name") or "").strip()
            team = str(row.get("team") or "").strip()
            if player_id and name:
                by_identity[(team, name)] = player_id
    return by_identity


def _photo_for_id(kbo_player_id):
    player_id = str(kbo_player_id or "").strip()
    if not player_id:
        return None
    for directory in PLAYER_PHOTO_DIRECTORIES:
        for extension in PLAYER_PHOTO_EXTENSIONS:
            candidate = directory / f"{player_id}{extension}"
            if candidate.is_file():
                return candidate
    return None


@lru_cache(maxsize=2048)
def resolve_player_photo(kbo_player_id=None, player_name=None, team_name=None):
    """고화질 원본을 우선해 선수 사진 경로를 반환한다."""
    direct = _photo_for_id(kbo_player_id)
    if direct is not None:
        return direct

    name = str(player_name or "").strip()
    team = str(team_name or "").strip()
    if name:
        roster_id = _roster_photo_ids().get((team, name))
        fallback = _photo_for_id(roster_id)
        if fallback is not None:
            return fallback

    team_directories = {"NC 다이노스": "NC", "NC": "NC"}
    team_directory = team_directories.get(team)
    if name and team_directory:
        legacy_directory = APP_ROOT / "image" / "Player_Image" / team_directory
        for extension in PLAYER_PHOTO_EXTENSIONS:
            candidate = legacy_directory / f"{name}{extension}"
            if candidate.is_file():
                return candidate
    return None
