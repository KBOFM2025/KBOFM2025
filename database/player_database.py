import csv
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
        source_url TEXT DEFAULT ''
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
}

HITTER_RATING_COLUMNS = (
    "contact", "power", "plate_discipline", "bat_control",
    "timing", "bunt", "speed", "baserunning_judgment",
)

EMPTY_FUTURE_COLUMNS = (
    "fielding_range", "catching", "throwing_power", "throwing_accuracy",
    "fielding_judgment", "composure", "leadership", "aggressiveness",
)

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
        for column in HITTER_RATING_COLUMNS:
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
        for column in EMPTY_FUTURE_COLUMNS:
            if row.get(column, "").strip():
                raise ValueError(
                    f"Future ability must be blank: {row['kbo_player_id']} {column}"
                )
    return rows, versions.pop()


def _import_hitter_abilities(connection):
    rows, formula_version = _read_hitter_abilities()
    if not rows:
        return False

    csv_ids = {row["kbo_player_id"] for row in rows}
    db_ids = {
        row["kbo_player_id"]
        for row in connection.execute(
            "SELECT kbo_player_id FROM players WHERE position_group <> 'P'"
        )
    }
    if csv_ids != db_ids:
        raise ValueError(
            "Hitter ability IDs do not match the current hitter roster "
            f"(missing={len(db_ids - csv_ids)}, unknown={len(csv_ids - db_ids)})"
        )

    assignments = ", ".join(f"{column} = ?" for column in HITTER_RATING_COLUMNS)
    null_assignments = ", ".join(f"{column} = NULL" for column in EMPTY_FUTURE_COLUMNS)
    statement = connection.cursor()
    updated = 0
    for row in rows:
        values = [int(row[column]) for column in HITTER_RATING_COLUMNS]
        values.extend((row.get("source_level", ""), formula_version, row["kbo_player_id"]))
        statement.execute(
            f"""
            UPDATE players
            SET {assignments}, {null_assignments},
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


def ensure_player_database():
    """게임 수치는 보존하면서 2025-10-31 KBO 소속 선수와 공식 프로필을 반영한다."""
    connection = sqlite3.connect(PLAYERS_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(CREATE_PLAYERS_TABLE)
        _migrate_columns(connection)
        _create_import_history(connection)
        _create_hitter_ability_import_history(connection)
        if not _import_official_roster(connection):
            _seed_missing_teams(connection)
        _import_hitter_abilities(connection)
        _create_ability_views(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_uid ON players(player_uid)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_players_kbo_id ON players(kbo_player_id)")
        connection.commit()
    finally:
        connection.close()


def initialize_database(reset=False):
    if reset and PLAYERS_DB_PATH.exists():
        PLAYERS_DB_PATH.unlink()
    ensure_player_database()
    print(f"✅ 성공: {PLAYERS_DB_PATH} 선수 데이터베이스 준비 완료")


if __name__ == "__main__":
    initialize_database()
