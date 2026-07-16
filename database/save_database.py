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

SAVE_COLUMNS = {
    "start_point": "TEXT NOT NULL DEFAULT 'camp1_before'",
    "current_date": "TEXT NOT NULL DEFAULT '2025-11-01'",
}

DAILY_NEWS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS daily_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        news_date TEXT NOT NULL,
        category TEXT NOT NULL,
        headline TEXT NOT NULL,
        body TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(save_id, news_date, headline)
    )
"""

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
                    start_point TEXT NOT NULL DEFAULT 'camp1_before',
                    current_date TEXT NOT NULL DEFAULT '2025-11-01',
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
            self._ensure_daily_news_table(connection)
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(game_saves)").fetchall()
            }
            added_columns = set()
            for column_name, definition in {**MANAGER_COLUMNS, **SAVE_COLUMNS}.items():
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
            if "current_date" in added_columns:
                connection.execute(
                    """
                    UPDATE game_saves
                    SET current_date = CASE start_point
                        WHEN 'camp1_after' THEN '2025-11-27'
                        WHEN 'camp2_before' THEN '2025-12-15'
                        ELSE '2025-11-01'
                    END
                    """
                )

    @staticmethod
    def _ensure_daily_news_table(connection):
        """구버전 또는 외부에서 교체된 세이브 DB에도 뉴스 스키마를 보장한다."""
        connection.execute(DAILY_NEWS_TABLE_SQL)

    def create_save(
        self,
        club_name,
        base_team,
        manager=None,
        start_point="camp1_before",
        current_date="2025-11-01",
    ):
        manager = manager or {}
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO game_saves (
                    club_name, base_team, start_point, current_date,
                    manager_name, manager_age, manager_style,
                    manager_batting, manager_pitching, manager_defense,
                    manager_baserunning, manager_game_management,
                    manager_pitching_change, manager_pinch_hitting,
                    manager_data_analysis, manager_development,
                    manager_fitness, manager_leadership,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    club_name,
                    base_team,
                    start_point,
                    current_date,
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
            self._ensure_daily_news_table(connection)
            connection.execute(
                "DELETE FROM daily_news WHERE save_id = ?",
                (save_id,),
            )
            cursor = connection.execute(
                "DELETE FROM game_saves WHERE id = ?",
                (save_id,),
            )
            return cursor.rowcount > 0

    def add_daily_news(self, save_id, news_date, category, headline, body):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            self._ensure_daily_news_table(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_news (
                    save_id, news_date, category, headline, body, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (save_id, news_date, category, headline, body, now),
            )

    def list_daily_news(self, save_id):
        with self.connect() as connection:
            self._ensure_daily_news_table(connection)
            rows = connection.execute(
                """
                SELECT * FROM daily_news
                WHERE save_id = ?
                ORDER BY news_date DESC, id DESC
                """,
                (save_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_daily_news_read(self, save_id, news_id):
        with self.connect() as connection:
            self._ensure_daily_news_table(connection)
            connection.execute(
                """
                UPDATE daily_news SET is_read = 1
                WHERE save_id = ? AND id = ?
                """,
                (save_id, news_id),
            )

    def mark_all_daily_news_read(self, save_id):
        with self.connect() as connection:
            self._ensure_daily_news_table(connection)
            connection.execute(
                "UPDATE daily_news SET is_read = 1 WHERE save_id = ?",
                (save_id,),
            )

    def unread_daily_news_count(self, save_id):
        with self.connect() as connection:
            self._ensure_daily_news_table(connection)
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM daily_news
                WHERE save_id = ? AND is_read = 0
                """,
                (save_id,),
            ).fetchone()
        return int(row["count"])

    def sync_daily_news(self, save_id, news_items):
        """메모리에 누적된 소식과 확인 상태를 수동 저장 시점에 반영한다."""
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            self._ensure_daily_news_table(connection)
            for news in news_items:
                connection.execute(
                    """
                    INSERT INTO daily_news (
                        save_id, news_date, category, headline, body,
                        is_read, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(save_id, news_date, headline) DO UPDATE SET
                        category = excluded.category,
                        body = excluded.body,
                        is_read = excluded.is_read
                    """,
                    (
                        save_id,
                        news["news_date"],
                        news["category"],
                        news["headline"],
                        news["body"],
                        int(bool(news["is_read"])),
                        now,
                    ),
                )

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

    def update_game_date(self, save_id, current_date):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE game_saves
                SET current_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (current_date, now, save_id),
            )
