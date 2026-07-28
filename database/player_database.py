import csv
import hashlib
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .paths import DATA_DIR, PLAYERS_DB_PATH
from .roster_data import ROSTER_PLAYERS, build_roster_rows


ROSTER_IMPORT_VERSION = "kbo-2025-10-31-v1"
ROSTER_SNAPSHOT_DATE = "2025-10-31"
ROSTER_FILE_NAME = "kbo_2025_final_roster.csv"
HITTER_ABILITIES_FILE_NAME = "kbo_2025_hitter_abilities.csv"
PITCHER_ABILITIES_FILE_NAME = "kbo_2025_pitcher_abilities.csv"
FINAL_FIRST_TEAM_FILE_NAME = "kbo_2025_final_first_team.csv"
FINAL_FIRST_TEAM_VERSION = "kbo-2025-regular-season-final-first-team-v2"


def _roster_source_path():
    external = DATA_DIR / "source" / ROSTER_FILE_NAME
    if external.exists():
        return external
    bundle_root = Path(getattr(sys, "_MEIPASS", DATA_DIR.parent))
    return bundle_root / "data" / "source" / ROSTER_FILE_NAME


def _hitter_abilities_source_path():
    external = DATA_DIR / "source" / HITTER_ABILITIES_FILE_NAME
    if external.exists():
        return external
    bundle_root = Path(getattr(sys, "_MEIPASS", DATA_DIR.parent))
    return bundle_root / "data" / "source" / HITTER_ABILITIES_FILE_NAME


def _pitcher_abilities_source_path():
    external = DATA_DIR / "source" / PITCHER_ABILITIES_FILE_NAME
    if external.exists():
        return external
    bundle_root = Path(getattr(sys, "_MEIPASS", DATA_DIR.parent))
    return bundle_root / "data" / "source" / PITCHER_ABILITIES_FILE_NAME


def _final_first_team_source_path():
    external = DATA_DIR / "source" / FINAL_FIRST_TEAM_FILE_NAME
    if external.exists():
        return external
    bundle_root = Path(getattr(sys, "_MEIPASS", DATA_DIR.parent))
    return bundle_root / "data" / "source" / FINAL_FIRST_TEAM_FILE_NAME


CREATE_PLAYERS_TABLE = """
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_uid TEXT UNIQUE,
        kbo_player_id TEXT UNIQUE,
        team TEXT NOT NULL,
        name TEXT NOT NULL,
        pos TEXT NOT NULL,
        age INTEGER NOT NULL,
        birth_date TEXT,
        bats_throws TEXT DEFAULT '',
        height_cm INTEGER,
        weight_kg INTEGER,
        career TEXT DEFAULT '',
        con INTEGER NOT NULL,
        pow INTEGER NOT NULL,
        eye INTEGER NOT NULL,
        def INTEGER NOT NULL,
        contact INTEGER,
        power INTEGER,
        plate_discipline INTEGER,
        bat_control INTEGER,
        timing INTEGER,
        bunt INTEGER,
        speed INTEGER,
        baserunning_judgment INTEGER,
        fielding_range INTEGER,
        catching INTEGER,
        throwing_power INTEGER,
        throwing_accuracy INTEGER,
        fielding_judgment INTEGER,
        composure INTEGER,
        leadership INTEGER,
        aggressiveness INTEGER,
        ability_source_level TEXT,
        ability_formula_version TEXT,
        hitter_advanced_public_player_id TEXT,
        hitter_advanced_wrc_plus REAL,
        hitter_advanced_sfr REAL,
        hitter_advanced_war REAL,
        hitter_advanced_source_url TEXT,
        hitter_rating_confidence TEXT,
        hitter_rating_detail_json TEXT,
        pitcher_velocity INTEGER,
        pitcher_stuff INTEGER,
        pitcher_command INTEGER,
        pitcher_movement INTEGER,
        pitcher_stamina INTEGER,
        pitcher_pitchability INTEGER,
        pitcher_strikeout INTEGER,
        pitcher_walk_control INTEGER,
        pitcher_composure INTEGER,
        pitch_four_seam INTEGER,
        pitch_sinker INTEGER,
        pitch_cutter INTEGER,
        pitch_changeup INTEGER,
        pitch_slider INTEGER,
        pitch_curve INTEGER,
        pitch_splitter INTEGER,
        pitch_sweeper INTEGER,
        pitch_knuckleball INTEGER,
        pitcher_repertoire TEXT,
        pitcher_source_level TEXT,
        pitcher_confidence TEXT,
        pitcher_formula_version TEXT,
        pitcher_sample_tbf INTEGER,
        pitcher_sample_ip REAL,
        pitcher_avg_velocity REAL,
        pitcher_k_stuff_plus REAL,
        pitcher_k_location_plus REAL,
        pitcher_whiff_rate REAL,
        pitcher_csw_rate REAL,
        pitcher_k_rate REAL,
        pitcher_bb_rate REAL,
        pitcher_hr_rate REAL,
        pitcher_fip REAL,
        pitcher_pitch_detail_json TEXT,
        pitcher_tracking_source_url TEXT,
        status INTEGER DEFAULT 1,
        lineup_pos INTEGER DEFAULT 0,
        role TEXT DEFAULT '선수',
        salary INTEGER DEFAULT 5000,
        snapshot_date TEXT,
        position_group TEXT,
        is_rookie INTEGER NOT NULL DEFAULT 0,
        is_foreign INTEGER NOT NULL DEFAULT 0,
        profile_complete INTEGER NOT NULL DEFAULT 0,
        source_note TEXT DEFAULT '',
        source_url TEXT DEFAULT '',
        draft_year INTEGER,
        draft_pick INTEGER,
        school TEXT DEFAULT '',
        arrival_date TEXT
    )
"""

INSERT_PLAYER = """
    INSERT INTO players (
        team, name, pos, age, con, pow, eye, def,
        status, lineup_pos, role, salary
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

ROSTER_COLUMNS = {
    "player_uid": "TEXT",
    "kbo_player_id": "TEXT",
    "snapshot_date": "TEXT",
    "position_group": "TEXT",
    "birth_date": "TEXT",
    "bats_throws": "TEXT DEFAULT ''",
    "height_cm": "INTEGER",
    "weight_kg": "INTEGER",
    "career": "TEXT DEFAULT ''",
    "is_rookie": "INTEGER NOT NULL DEFAULT 0",
    "is_foreign": "INTEGER NOT NULL DEFAULT 0",
    "profile_complete": "INTEGER NOT NULL DEFAULT 0",
    "source_note": "TEXT DEFAULT ''",
    "source_url": "TEXT DEFAULT ''",
    "draft_year": "INTEGER",
    "draft_pick": "INTEGER",
    "school": "TEXT DEFAULT ''",
    "arrival_date": "TEXT",
}

PLAYER_ABILITY_COLUMNS = {
    "contact": "INTEGER",
    "power": "INTEGER",
    "plate_discipline": "INTEGER",
    "bat_control": "INTEGER",
    "timing": "INTEGER",
    "bunt": "INTEGER",
    "speed": "INTEGER",
    "baserunning_judgment": "INTEGER",
    "fielding_range": "INTEGER",
    "catching": "INTEGER",
    "throwing_power": "INTEGER",
    "throwing_accuracy": "INTEGER",
    "fielding_judgment": "INTEGER",
    "composure": "INTEGER",
    "leadership": "INTEGER",
    "aggressiveness": "INTEGER",
    "ability_source_level": "TEXT",
    "ability_formula_version": "TEXT",
    "hitter_advanced_public_player_id": "TEXT",
    "hitter_advanced_wrc_plus": "REAL",
    "hitter_advanced_sfr": "REAL",
    "hitter_advanced_war": "REAL",
    "hitter_advanced_source_url": "TEXT",
    "hitter_rating_confidence": "TEXT",
    "hitter_rating_detail_json": "TEXT",
    "pitcher_velocity": "INTEGER", "pitcher_stuff": "INTEGER",
    "pitcher_command": "INTEGER", "pitcher_movement": "INTEGER",
    "pitcher_stamina": "INTEGER", "pitcher_pitchability": "INTEGER",
    "pitcher_strikeout": "INTEGER", "pitcher_walk_control": "INTEGER",
    "pitcher_composure": "INTEGER", "pitch_four_seam": "INTEGER",
    "pitch_sinker": "INTEGER", "pitch_cutter": "INTEGER",
    "pitch_changeup": "INTEGER", "pitch_slider": "INTEGER",
    "pitch_curve": "INTEGER", "pitch_splitter": "INTEGER",
    "pitch_sweeper": "INTEGER", "pitch_knuckleball": "INTEGER",
    "pitcher_repertoire": "TEXT", "pitcher_source_level": "TEXT",
    "pitcher_confidence": "TEXT", "pitcher_formula_version": "TEXT",
    "pitcher_sample_tbf": "INTEGER", "pitcher_sample_ip": "REAL",
    "pitcher_avg_velocity": "REAL", "pitcher_k_stuff_plus": "REAL",
    "pitcher_k_location_plus": "REAL", "pitcher_whiff_rate": "REAL",
    "pitcher_csw_rate": "REAL", "pitcher_k_rate": "REAL",
    "pitcher_bb_rate": "REAL", "pitcher_hr_rate": "REAL",
    "pitcher_fip": "REAL", "pitcher_pitch_detail_json": "TEXT",
    "pitcher_tracking_source_url": "TEXT",
}

PITCHER_RATING_COLUMNS = (
    "pitcher_velocity", "pitcher_stuff", "pitcher_command", "pitcher_movement",
    "pitcher_stamina", "pitcher_pitchability", "pitcher_strikeout",
    "pitcher_walk_control", "pitcher_composure", "pitch_four_seam",
    "pitch_sinker", "pitch_cutter", "pitch_changeup", "pitch_slider",
    "pitch_curve", "pitch_splitter", "pitch_sweeper", "pitch_knuckleball",
)

PITCHER_CSV_TO_DB = {
    "repertoire": "pitcher_repertoire", "source_level": "pitcher_source_level",
    "confidence": "pitcher_confidence", "formula_version": "pitcher_formula_version",
    "sample_tbf": "pitcher_sample_tbf", "sample_ip": "pitcher_sample_ip",
    "avg_velocity": "pitcher_avg_velocity", "k_stuff_plus": "pitcher_k_stuff_plus",
    "k_location_plus": "pitcher_k_location_plus", "whiff_rate": "pitcher_whiff_rate",
    "csw_rate": "pitcher_csw_rate", "k_rate": "pitcher_k_rate",
    "bb_rate": "pitcher_bb_rate", "hr_rate": "pitcher_hr_rate",
    "fip": "pitcher_fip", "pitch_detail_json": "pitcher_pitch_detail_json",
    "tracking_source_url": "pitcher_tracking_source_url",
}

HITTER_RATING_COLUMNS = (
    "contact", "power", "plate_discipline", "bat_control",
    "timing", "bunt", "speed", "baserunning_judgment",
)

EMPTY_FUTURE_COLUMNS = (
    "fielding_range", "catching", "throwing_power", "throwing_accuracy",
    "fielding_judgment", "composure", "leadership", "aggressiveness",
)

ALL_HITTER_ABILITY_COLUMNS = HITTER_RATING_COLUMNS + EMPTY_FUTURE_COLUMNS

HITTER_CSV_TO_DB = {
    "advanced_public_player_id": "hitter_advanced_public_player_id",
    "advanced_wrc_plus": "hitter_advanced_wrc_plus",
    "advanced_sfr": "hitter_advanced_sfr",
    "advanced_war": "hitter_advanced_war",
    "advanced_source_url": "hitter_advanced_source_url",
    "rating_confidence": "hitter_rating_confidence",
    "rating_detail_json": "hitter_rating_detail_json",
}

DEFENSE_ABILITY_COLUMNS = (
    "fielding_range", "catching", "throwing_power",
    "throwing_accuracy", "fielding_judgment",
)

MENTAL_ABILITY_COLUMNS = (
    "composure", "leadership", "aggressiveness",
)


def _migrate_columns(connection):
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(players)")}
    if "team" not in columns:
        connection.execute("ALTER TABLE players ADD COLUMN team TEXT NOT NULL DEFAULT 'NC 다이노스'")
    for name, declaration in {**ROSTER_COLUMNS, **PLAYER_ABILITY_COLUMNS}.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE players ADD COLUMN {name} {declaration}")


def _create_import_history(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS roster_imports (
            version TEXT PRIMARY KEY,
            snapshot_date TEXT NOT NULL,
            player_count INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_hitter_ability_import_history(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hitter_ability_imports (
            formula_version TEXT PRIMARY KEY,
            player_count INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_pitcher_ability_import_history(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pitcher_ability_imports (
            formula_version TEXT PRIMARY KEY,
            player_count INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_first_team_import_history(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS first_team_roster_imports (
            version TEXT PRIMARY KEY,
            snapshot_date TEXT NOT NULL,
            player_count INTEGER NOT NULL,
            source_path TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _read_final_first_team():
    source_path = _final_first_team_source_path()
    if not source_path.exists():
        return []
    with source_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    team_counts = Counter(row["team"] for row in rows)
    if len(team_counts) != 10 or any(count < 30 or count > 33 for count in team_counts.values()):
        raise ValueError(f"2025 최종 1군 명단의 구단별 인원이 올바르지 않습니다: {dict(team_counts)}")
    player_ids = [row["kbo_player_id"] for row in rows]
    missing = [f"{row['team']} {row['name']}" for row in rows if not row["kbo_player_id"]]
    duplicate_ids = sorted(
        player_id for player_id, count in Counter(player_ids).items()
        if player_id and count > 1
    )
    if missing or duplicate_ids:
        raise ValueError(
            "2025 최종 1군 명단의 KBO 선수 ID 오류: "
            f"누락={missing or '없음'}, 중복={duplicate_ids or '없음'}"
        )
    return rows


def _import_final_first_team(connection):
    if connection.execute(
        "SELECT 1 FROM first_team_roster_imports WHERE version = ?",
        (FINAL_FIRST_TEAM_VERSION,),
    ).fetchone():
        return False
    rows = _read_final_first_team()
    if not rows:
        return False
    csv_ids = {row["kbo_player_id"] for row in rows}
    db_ids = {
        str(row["kbo_player_id"])
        for row in connection.execute("SELECT kbo_player_id FROM players")
        if row["kbo_player_id"]
    }
    unknown = csv_ids - db_ids
    if unknown:
        raise ValueError(f"선수 DB에 없는 최종 1군 선수 ID가 있습니다: {sorted(unknown)}")

    connection.execute("UPDATE players SET status = 0, lineup_pos = 0")
    cursor = connection.cursor()
    updated = 0
    for row in rows:
        cursor.execute(
            "UPDATE players SET status = 1 WHERE kbo_player_id = ? AND team = ?",
            (row["kbo_player_id"], row["team"]),
        )
        updated += cursor.rowcount
    if updated != len(rows):
        raise ValueError(f"최종 1군 명단 {len(rows)}명 중 {updated}명만 DB에 반영되었습니다.")
    connection.execute(
        """
        INSERT INTO first_team_roster_imports
            (version, snapshot_date, player_count, source_path)
        VALUES (?, ?, ?, ?)
        """,
        (
            FINAL_FIRST_TEAM_VERSION,
            "2025-10-31",
            len(rows),
            str(_final_first_team_source_path()),
        ),
    )
    return True


def _create_ability_views(connection):
    connection.execute("DROP VIEW IF EXISTS player_defense_abilities")
    connection.execute(
        """
        CREATE VIEW player_defense_abilities AS
        SELECT id AS player_id, player_uid, kbo_player_id, team, name,
               fielding_range, catching, throwing_power,
               throwing_accuracy, fielding_judgment
        FROM players
        """
    )
    connection.execute("DROP VIEW IF EXISTS player_mental_abilities")
    connection.execute(
        """
        CREATE VIEW player_mental_abilities AS
        SELECT id AS player_id, player_uid, kbo_player_id, team, name,
               composure, leadership, aggressiveness
        FROM players
        """
    )


def _read_hitter_abilities():
    source_path = _hitter_abilities_source_path()
    if not source_path.exists():
        return [], ""
    with source_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    if len(rows) != 317:
        raise ValueError(f"Expected 317 hitter ability rows, got {len(rows)}")
    player_ids = [row["kbo_player_id"] for row in rows]
    if any(not player_id for player_id in player_ids) or len(set(player_ids)) != len(rows):
        raise ValueError("Hitter ability KBO player IDs must be present and unique")

    versions = {row.get("formula_version", "").strip() for row in rows}
    if len(versions) != 1 or not next(iter(versions)):
        raise ValueError("Hitter ability rows must have one non-empty formula version")

    for row in rows:
        for column in ALL_HITTER_ABILITY_COLUMNS:
            try:
                rating = int(row[column])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid {column} rating for player {row.get('kbo_player_id', '')}"
                ) from error
            if rating < 1 or rating > 20:
                raise ValueError(
                    f"Rating out of range: {row['kbo_player_id']} {column}={rating}"
                )
    return rows, versions.pop()


def _import_hitter_abilities(connection):
    rows, formula_version = _read_hitter_abilities()
    if not rows:
        return False

    # 동일한 산식 버전이 이미 반영됐다면 원본 선수 능력치를 다시 쓰지 않는다.
    # 게임 실행 및 화면 진입은 DB 초기화가 아니라 스키마 확인만 수행해야 한다.
    if connection.execute(
        "SELECT 1 FROM hitter_ability_imports WHERE formula_version = ?",
        (formula_version,),
    ).fetchone():
        return True

    csv_ids = {row["kbo_player_id"] for row in rows}
    db_ids = {
        row["kbo_player_id"]
        for row in connection.execute(
            """
            SELECT kbo_player_id
            FROM players
            WHERE position_group <> 'P'
              AND kbo_player_id NOT LIKE 'DRAFT-%'
            """
        )
    }
    if csv_ids != db_ids:
        raise ValueError(
            "Hitter ability IDs do not match the current hitter roster "
            f"(missing={len(db_ids - csv_ids)}, unknown={len(csv_ids - db_ids)})"
        )

    db_columns = list(ALL_HITTER_ABILITY_COLUMNS) + list(HITTER_CSV_TO_DB.values())
    assignments = ", ".join(f"{column} = ?" for column in db_columns)
    statement = connection.cursor()
    updated = 0
    for row in rows:
        values: list[object] = [
            int(row[column]) for column in ALL_HITTER_ABILITY_COLUMNS
        ]
        for csv_column in HITTER_CSV_TO_DB:
            raw = row.get(csv_column, "").strip()
            if csv_column in {"advanced_wrc_plus", "advanced_sfr", "advanced_war"}:
                values.append(float(raw) if raw else None)
            else:
                values.append(raw or None)
        salary_text = row.get("salary_10k_krw", "").strip()
        values.extend(
            (
                int(salary_text) if salary_text else None,
                row.get("source_level", ""),
                formula_version,
                row["kbo_player_id"],
            )
        )
        statement.execute(
            f"""
            UPDATE players
            SET {assignments},
                salary = COALESCE(?, salary),
                ability_source_level = ?, ability_formula_version = ?
            WHERE kbo_player_id = ? AND position_group <> 'P'
            """,
            values,
        )
        updated += statement.rowcount
    if updated != len(rows):
        raise ValueError(f"Expected to update {len(rows)} hitters, updated {updated}")

    connection.execute(
        """
        INSERT OR REPLACE INTO hitter_ability_imports
            (formula_version, player_count, source_path, imported_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (formula_version, len(rows), str(_hitter_abilities_source_path())),
    )
    return True


def _read_pitcher_abilities():
    source_path = _pitcher_abilities_source_path()
    if not source_path.exists():
        return [], ""
    with source_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 319:
        raise ValueError(f"Expected 319 pitcher ability rows, got {len(rows)}")
    player_ids = [row["kbo_player_id"] for row in rows]
    if any(not value for value in player_ids) or len(set(player_ids)) != 319:
        raise ValueError("Pitcher ability KBO player IDs must be present and unique")
    versions = {row.get("formula_version", "").strip() for row in rows}
    if len(versions) != 1 or not next(iter(versions)):
        raise ValueError("Pitcher ability rows must have one formula version")
    for row in rows:
        for column in PITCHER_RATING_COLUMNS:
            value = row.get(column, "").strip()
            if not value:
                continue
            rating = int(value)
            if rating < 1 or rating > 20:
                raise ValueError(f"Pitcher rating out of range: {player_ids} {column}={rating}")
    return rows, versions.pop()


def _import_pitcher_abilities(connection):
    rows, formula_version = _read_pitcher_abilities()
    if not rows:
        return False

    # 최초 반영 뒤에는 2025 신인 드래프트 선수가 DB에 추가된다. 실행할
    # 때마다 공식 명단과 확장된 게임 명단을 다시 대조하면 다음 실행부터
    # 신인 투수 수만큼 불일치하므로, 동일 산식은 다시 가져오지 않는다.
    if connection.execute(
        "SELECT 1 FROM pitcher_ability_imports WHERE formula_version = ?",
        (formula_version,),
    ).fetchone():
        return True

    csv_ids = {row["kbo_player_id"] for row in rows}
    db_ids = {
        str(row["kbo_player_id"])
        for row in connection.execute(
            """
            SELECT kbo_player_id
            FROM players
            WHERE position_group = 'P'
              AND kbo_player_id NOT LIKE 'DRAFT-%'
            """
        )
    }
    if csv_ids != db_ids:
        raise ValueError(
            "Pitcher ability IDs do not match the current pitcher roster "
            f"(missing={len(db_ids - csv_ids)}, unknown={len(csv_ids - db_ids)})"
        )
    db_columns = list(PITCHER_RATING_COLUMNS) + list(PITCHER_CSV_TO_DB.values())
    statement = connection.cursor()
    updated = 0
    for row in rows:
        values = []
        for column in PITCHER_RATING_COLUMNS:
            raw = row.get(column, "").strip()
            values.append(int(raw) if raw else None)
        for csv_column in PITCHER_CSV_TO_DB:
            raw = row.get(csv_column, "").strip()
            if csv_column in {"sample_tbf"}:
                values.append(int(raw) if raw else None)
            elif csv_column in {"sample_ip", "avg_velocity", "k_stuff_plus", "k_location_plus", "whiff_rate", "csw_rate", "k_rate", "bb_rate", "hr_rate", "fip"}:
                values.append(float(raw) if raw else None)
            else:
                values.append(raw)
        salary_text = row.get("salary_10k_krw", "").strip()
        values.extend((
            int(salary_text) if salary_text else None,
            row.get("source_level", ""), formula_version, row["kbo_player_id"],
        ))
        statement.execute(
            f"""
            UPDATE players SET {', '.join(f'{column} = ?' for column in db_columns)},
                salary = COALESCE(?, salary), ability_source_level = ?,
                ability_formula_version = ?
            WHERE kbo_player_id = ? AND position_group = 'P'
            """,
            values,
        )
        updated += statement.rowcount
    if updated != len(rows):
        raise ValueError(
            f"Expected to update {len(rows)} pitchers, updated {updated}"
        )
    connection.execute(
        """INSERT OR REPLACE INTO pitcher_ability_imports
           (formula_version, player_count, source_path, imported_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
        (formula_version, len(rows), str(_pitcher_abilities_source_path())),
    )
    return True


def _read_official_roster():
    source_path = _roster_source_path()
    if not source_path.exists():
        return []
    with source_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    if len(rows) != 636:
        raise ValueError(f"2025-10-31 선수 명단은 636명이어야 합니다: {len(rows)}명")
    if len({row["kbo_player_id"] for row in rows}) != 636:
        raise ValueError("KBO 선수 ID가 비어 있거나 중복되었습니다.")
    if any(not row["birth_date"] for row in rows):
        raise ValueError("생년월일이 비어 있는 선수가 있습니다.")
    team_counts = Counter(row["team"] for row in rows)
    if len(team_counts) != 10:
        raise ValueError(f"구단 수가 올바르지 않습니다: {dict(team_counts)}")
    return rows


def _preserved_player_ids(connection, roster_rows):
    existing = [dict(row) for row in connection.execute("SELECT * FROM players")]
    by_kbo = {str(row.get("kbo_player_id")): row["id"] for row in existing if row.get("kbo_player_id")}
    by_name = defaultdict(list)
    by_team_name = defaultdict(list)
    for row in existing:
        by_name[row["name"]].append(row["id"])
        by_team_name[(row["team"], row["name"])].append(row["id"])

    final_name_counts = Counter(row["name"] for row in roster_rows)
    aliases = {"배제성": "배재성"}
    preserved = {}
    for row in roster_rows:
        old_id = by_kbo.get(row["kbo_player_id"])
        old_name = aliases.get(row["name"], row["name"])
        if old_id is None:
            exact = by_team_name.get((row["team"], old_name), [])
            if len(exact) == 1:
                old_id = exact[0]
        if old_id is None and final_name_counts[row["name"]] == 1:
            same_name = by_name.get(old_name, [])
            if len(same_name) == 1:
                old_id = same_name[0]
        preserved[row["kbo_player_id"]] = old_id
    return preserved


def _import_official_roster(connection):
    if connection.execute(
        "SELECT 1 FROM roster_imports WHERE version = ?", (ROSTER_IMPORT_VERSION,)
    ).fetchone():
        return True

    rows = _read_official_roster()
    if not rows:
        return False
    preserved = _preserved_player_ids(connection, rows)

    connection.execute("DROP TABLE IF EXISTS official_roster_staging")
    connection.execute(
        """
        CREATE TEMP TABLE official_roster_staging (
            player_uid TEXT PRIMARY KEY, kbo_player_id TEXT UNIQUE NOT NULL,
            snapshot_date TEXT NOT NULL, team TEXT NOT NULL, name TEXT NOT NULL,
            position_group TEXT NOT NULL, position_name TEXT NOT NULL,
            age INTEGER NOT NULL, birth_date TEXT NOT NULL, bats_throws TEXT NOT NULL,
            height_cm INTEGER, weight_kg INTEGER, career TEXT NOT NULL,
            is_rookie INTEGER NOT NULL, is_foreign INTEGER NOT NULL,
            source_note TEXT NOT NULL, source_url TEXT NOT NULL, preserved_id INTEGER
        )
        """
    )
    connection.executemany(
        "INSERT INTO official_roster_staging VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                row["player_uid"], row["kbo_player_id"], row["snapshot_date"], row["team"],
                row["name"], row["position_group"], row["position_name"], int(row["age"]),
                row["birth_date"], row["bats_throws"], int(row["height_cm"]) if row["height_cm"] else None,
                int(row["weight_kg"]) if row["weight_kg"] else None, row["career"], int(row["is_rookie"]),
                int(row["is_foreign"]), row["source_note"], row["source_url"],
                preserved[row["kbo_player_id"]],
            )
            for row in rows
        ],
    )

    connection.execute("DROP TABLE IF EXISTS players_import")
    connection.execute(CREATE_PLAYERS_TABLE.replace("players", "players_import", 1))
    connection.execute(
        """
        INSERT INTO players_import (
            player_uid, kbo_player_id, team, name, pos, age, birth_date, bats_throws,
            height_cm, weight_kg, career, con, pow, eye, def, status, lineup_pos, role,
            salary, snapshot_date, position_group, is_rookie, is_foreign,
            profile_complete, source_note, source_url
        )
        SELECT o.player_uid, o.kbo_player_id, o.team, o.name,
               COALESCE(p.pos, o.position_group), o.age, o.birth_date, o.bats_throws,
               o.height_cm, o.weight_kg, o.career,
               COALESCE(p.con, 50), COALESCE(p.pow, 50), COALESCE(p.eye, 50), COALESCE(p.def, 50),
               COALESCE(p.status, 0), COALESCE(p.lineup_pos, 0), COALESCE(p.role, '선수'),
               COALESCE(p.salary, 3000), o.snapshot_date, o.position_group,
               o.is_rookie, o.is_foreign, 1, o.source_note, o.source_url
        FROM official_roster_staging o
        LEFT JOIN players p ON p.id = o.preserved_id
        """
    )
    connection.execute("DROP TABLE players")
    connection.execute("ALTER TABLE players_import RENAME TO players")
    connection.execute("CREATE INDEX idx_players_team ON players(team)")
    connection.execute("CREATE UNIQUE INDEX idx_players_uid ON players(player_uid)")
    connection.execute("CREATE UNIQUE INDEX idx_players_kbo_id ON players(kbo_player_id)")
    connection.execute(
        "INSERT INTO roster_imports (version, snapshot_date, player_count, source_path) VALUES (?,?,?,?)",
        (ROSTER_IMPORT_VERSION, ROSTER_SNAPSHOT_DATE, len(rows), str(_roster_source_path())),
    )
    return True


def _seed_missing_teams(connection):
    existing = {row["team"] for row in connection.execute("SELECT DISTINCT team FROM players")}
    for team_name in ROSTER_PLAYERS:
        if team_name not in existing:
            connection.executemany(INSERT_PLAYER, build_roster_rows(team_name))


def _import_2025_draft_players(connection):
    """최종 보류명단에서 빠진 2025 지명 선수까지 구단 2군에 보존한다."""
    source_path = DATA_DIR / "source" / "kbo_2025_rookie_draft.csv"
    if not source_path.exists():
        return 0
    with source_path.open("r", encoding="utf-8-sig", newline="") as source:
        rookies = list(csv.DictReader(source))
    schema = {
        row["name"]: dict(row)
        for row in connection.execute("PRAGMA table_info(players)").fetchall()
    }
    inserted = 0
    for rookie in rookies:
        existing = connection.execute(
            "SELECT id FROM players WHERE team=? AND name=?",
            (rookie["team"], rookie["name"]),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE players SET
                    is_rookie=1, draft_year=2025, draft_pick=?,
                    school=?, source_note=CASE
                        WHEN source_note='' THEN ?
                        ELSE source_note
                    END
                WHERE id=?
                """,
                (
                    int(rookie["overall_pick"]), rookie["school"],
                    "2025 KBO 신인 드래프트 공식 지명",
                    existing["id"],
                ),
            )
            continue
        round_no = int(rookie["round"])
        seed = int.from_bytes(
            hashlib.sha256(
                f"2025:{rookie['overall_pick']}:{rookie['name']}".encode(
                    "utf-8"
                )
            ).digest()[:4],
            "big",
        )
        base = max(6, min(12, 12 - (round_no - 1) // 2))
        ratings = [
            max(1, min(20, base + ((seed >> offset) % 3) - 1))
            for offset in (0, 2, 4, 6)
        ]
        age = 22 if "대" in rookie["school"] else 19
        values = {
            "player_uid": f"DRAFT-2025-{int(rookie['overall_pick']):03d}",
            "kbo_player_id": f"DRAFT-2025-{int(rookie['overall_pick']):03d}",
            "team": rookie["team"],
            "name": rookie["name"],
            "pos": rookie["position_group"],
            "age": age,
            "birth_date": "",
            "bats_throws": "",
            "career": f"{rookie['school']}-{rookie['team']}",
            "con": ratings[0],
            "pow": ratings[1],
            "eye": ratings[2],
            "def": ratings[3],
            "status": 0,
            "lineup_pos": 0,
            "role": "신인 육성",
            "salary": 3000,
            "snapshot_date": ROSTER_SNAPSHOT_DATE,
            "position_group": rookie["position_group"],
            "is_rookie": 1,
            "is_foreign": 0,
            "profile_complete": 0,
            "source_note": (
                "2025 KBO 신인 드래프트 공식 지명 · 프로 표본 미확보"
            ),
            "source_url": rookie["source_url"],
            "draft_year": 2025,
            "draft_pick": int(rookie["overall_pick"]),
            "school": rookie["school"],
            "arrival_date": "2025-01-01",
        }
        _fill_required_player_values(values, schema)
        columns = tuple(
            column for column in values if column in schema
        )
        connection.execute(
            f"""
            INSERT INTO players ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            """,
            tuple(values[column] for column in columns),
        )
        inserted += 1
    return inserted


def _fill_required_player_values(values, schema):
    """DB 변형본의 필수 열을 허위 프로필 없이 안전한 빈 값으로 채운다."""
    for column, info in schema.items():
        if column in values or column == "id":
            continue
        if not int(info.get("notnull") or 0) or info.get("dflt_value") is not None:
            continue
        column_type = str(info.get("type") or "").upper()
        if "INT" in column_type:
            values[column] = 0
        elif any(kind in column_type for kind in ("REAL", "FLOA", "DOUB", "NUM")):
            values[column] = 0.0
        else:
            values[column] = ""


def ensure_player_database():
    """게임 수치는 보존하면서 2025-10-31 KBO 소속 선수와 공식 프로필을 반영한다."""
    connection = sqlite3.connect(PLAYERS_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(CREATE_PLAYERS_TABLE)
        _migrate_columns(connection)
        _create_import_history(connection)
        _create_hitter_ability_import_history(connection)
        _create_pitcher_ability_import_history(connection)
        _create_first_team_import_history(connection)
        if not _import_official_roster(connection):
            _seed_missing_teams(connection)
        _import_hitter_abilities(connection)
        _import_pitcher_abilities(connection)
        _import_final_first_team(connection)
        _import_2025_draft_players(connection)
        _create_ability_views(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_uid ON players(player_uid)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_kbo_id ON players(kbo_player_id)")
        connection.commit()
    finally:
        connection.close()


def ensure_final_roster_assignments(db_path=PLAYERS_DB_PATH):
    """기존 세이브 DB에도 최종 경기 기준 1군/2군 편성을 한 번만 적용한다."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        _create_first_team_import_history(connection)
        changed = _import_final_first_team(connection)
        connection.commit()
        return changed
    finally:
        connection.close()


def ensure_2025_draft_players(db_path=PLAYERS_DB_PATH):
    """기존 감독 세이브 DB에도 공식 2025 지명 선수 110명을 보장한다."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        _migrate_columns(connection)
        changed = _import_2025_draft_players(connection)
        connection.commit()
        return changed
    finally:
        connection.close()


def initialize_database(reset=False):
    if reset and PLAYERS_DB_PATH.exists():
        PLAYERS_DB_PATH.unlink()
    ensure_player_database()
    print(f"✅ 성공: {PLAYERS_DB_PATH} 선수 데이터베이스 준비 완료")


if __name__ == "__main__":
    initialize_database()
