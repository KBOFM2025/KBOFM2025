import sqlite3
from datetime import datetime
from pathlib import Path

from .paths import SAVES_DB_PATH


MANAGER_COLUMNS = {
    "manager_name": "TEXT NOT NULL DEFAULT '무명 감독'",
    "manager_age": "INTEGER NOT NULL DEFAULT 45",
    "manager_style": "TEXT NOT NULL DEFAULT '염경엽'",
    "manager_batting": "INTEGER NOT NULL DEFAULT 5",
    "manager_pitching": "INTEGER NOT NULL DEFAULT 5",
    "manager_defense": "INTEGER NOT NULL DEFAULT 5",
    "manager_baserunning": "INTEGER NOT NULL DEFAULT 5",
    "manager_game_management": "INTEGER NOT NULL DEFAULT 5",
    "manager_pitching_change": "INTEGER NOT NULL DEFAULT 5",
    "manager_pinch_hitting": "INTEGER NOT NULL DEFAULT 5",
    "manager_data_analysis": "INTEGER NOT NULL DEFAULT 5",
    "manager_development": "INTEGER NOT NULL DEFAULT 5",
    "manager_fitness": "INTEGER NOT NULL DEFAULT 5",
    "manager_leadership": "INTEGER NOT NULL DEFAULT 5",
    "manager_ability_scale": "INTEGER NOT NULL DEFAULT 20",
}

MANAGER_ABILITY_COLUMNS = (
    "manager_batting",
    "manager_pitching",
    "manager_defense",
    "manager_baserunning",
    "manager_game_management",
    "manager_pitching_change",
    "manager_pinch_hitting",
    "manager_data_analysis",
    "manager_development",
    "manager_fitness",
    "manager_leadership",
)


class SaveDatabase:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else SAVES_DB_PATH
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS game_saves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    club_name TEXT NOT NULL,
                    base_team TEXT NOT NULL,
                    season INTEGER NOT NULL DEFAULT 2025,
                    season_day INTEGER NOT NULL DEFAULT 1,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    manager_name TEXT NOT NULL DEFAULT '무명 감독',
                    manager_age INTEGER NOT NULL DEFAULT 45,
                    manager_style TEXT NOT NULL DEFAULT '염경엽',
                    manager_batting INTEGER NOT NULL DEFAULT 5,
                    manager_pitching INTEGER NOT NULL DEFAULT 5,
                    manager_defense INTEGER NOT NULL DEFAULT 5,
                    manager_baserunning INTEGER NOT NULL DEFAULT 5,
                    manager_game_management INTEGER NOT NULL DEFAULT 5,
                    manager_pitching_change INTEGER NOT NULL DEFAULT 5,
                    manager_pinch_hitting INTEGER NOT NULL DEFAULT 5,
                    manager_data_analysis INTEGER NOT NULL DEFAULT 5,
                    manager_development INTEGER NOT NULL DEFAULT 5,
                    manager_fitness INTEGER NOT NULL DEFAULT 5,
                    manager_leadership INTEGER NOT NULL DEFAULT 5,
                    manager_ability_scale INTEGER NOT NULL DEFAULT 20,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(game_saves)").fetchall()
            }
            added_columns = set()
            for column_name, definition in MANAGER_COLUMNS.items():
                if column_name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE game_saves ADD COLUMN {column_name} {definition}"
                    )
                    added_columns.add(column_name)

            if "manager_game_management" in added_columns and "manager_tactics" in existing_columns:
                connection.execute(
                    "UPDATE game_saves SET manager_game_management = manager_tactics"
                )
            if "manager_leadership" in added_columns and "manager_management" in existing_columns:
                connection.execute(
                    "UPDATE game_saves SET manager_leadership = manager_management"
                )
            if "manager_ability_scale" in added_columns:
                assignments = ", ".join(
                    f"{column_name} = {column_name} * 2"
                    for column_name in MANAGER_ABILITY_COLUMNS
                )
                connection.execute(f"UPDATE game_saves SET {assignments}")

    def create_save(self, club_name, base_team, manager=None):
        manager = manager or {}
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO game_saves (
                    club_name, base_team,
                    manager_name, manager_age, manager_style,
                    manager_batting, manager_pitching, manager_defense,
                    manager_baserunning, manager_game_management,
                    manager_pitching_change, manager_pinch_hitting,
                    manager_data_analysis, manager_development,
                    manager_fitness, manager_leadership,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    club_name,
                    base_team,
                    manager.get("manager_name", "무명 감독"),
                    manager.get("manager_age", 45),
                    manager.get("manager_style", "염경엽"),
                    manager.get("batting", 10),
                    manager.get("pitching", 10),
                    manager.get("defense", 10),
                    manager.get("baserunning", 10),
                    manager.get("game_management", 10),
                    manager.get("pitching_change", 10),
                    manager.get("pinch_hitting", 10),
                    manager.get("data_analysis", 10),
                    manager.get("development", 10),
                    manager.get("fitness", 10),
                    manager.get("leadership", 10),
                    now,
                    now,
                ),
            )
            return cursor.lastrowid

    def list_saves(self):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM game_saves
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_save(self, save_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM game_saves WHERE id = ?",
                (save_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_save(self, save_id):
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM game_saves WHERE id = ?",
                (save_id,),
            )
            return cursor.rowcount > 0

    def update_club_info(self, save_id, club_name, base_team):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE game_saves
                SET club_name = ?, base_team = ?, updated_at = ?
                WHERE id = ?
                """,
                (club_name, base_team, now, save_id),
            )
