import sqlite3

from .paths import PLAYERS_DB_PATH
from .roster_data import ROSTER_PLAYERS, build_roster_rows


CREATE_PLAYERS_TABLE = """
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team TEXT NOT NULL,
        name TEXT NOT NULL,
        pos TEXT NOT NULL,
        age INTEGER NOT NULL,
        con INTEGER NOT NULL,
        pow INTEGER NOT NULL,
        eye INTEGER NOT NULL,
        def INTEGER NOT NULL,
        status INTEGER DEFAULT 1,
        lineup_pos INTEGER DEFAULT 0,
        role TEXT DEFAULT '선수',
        salary INTEGER DEFAULT 5000
    )
"""

INSERT_PLAYER = """
    INSERT INTO players (
        team, name, pos, age, con, pow, eye, def,
        status, lineup_pos, role, salary
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _migrate_team_column(connection):
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(players)").fetchall()
    }
    if "team" not in columns:
        connection.execute(
            "ALTER TABLE players ADD COLUMN team TEXT NOT NULL DEFAULT 'NC 다이노스'"
        )


def _seed_missing_teams(connection):
    existing = {
        row["team"]
        for row in connection.execute(
            "SELECT DISTINCT team FROM players WHERE team IS NOT NULL"
        ).fetchall()
    }
    for team_name in ROSTER_PLAYERS:
        if team_name not in existing:
            connection.executemany(INSERT_PLAYER, build_roster_rows(team_name))


def ensure_player_database():
    """기존 선수 DB를 보존하면서 최신 10개 구단 스키마로 맞춘다."""
    connection = sqlite3.connect(PLAYERS_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(CREATE_PLAYERS_TABLE)
        _migrate_team_column(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_players_team ON players(team)"
        )
        _seed_missing_teams(connection)
        connection.commit()
    finally:
        connection.close()


def initialize_database(reset=False):
    """선수 DB를 준비한다. reset=True일 때만 기존 데이터를 초기화한다."""
    if reset and PLAYERS_DB_PATH.exists():
        PLAYERS_DB_PATH.unlink()
    ensure_player_database()
    print(f"✅ 성공: {PLAYERS_DB_PATH} 선수 데이터베이스 준비 완료")


if __name__ == "__main__":
    initialize_database()
