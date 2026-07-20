import json
import hashlib
import random
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .league_simulation_repository import SIMULATION_SCHEMA
from .paths import DATA_DIR, PLAYERS_DB_PATH, SAVES_DB_PATH


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
    "player_db_path": "TEXT",
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

GOVERNANCE_STATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS governance_state (
        save_id INTEGER PRIMARY KEY,
        board_confidence INTEGER NOT NULL DEFAULT 75,
        gm_relationship INTEGER NOT NULL DEFAULT 70,
        state_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(save_id) REFERENCES game_saves(id) ON DELETE CASCADE
    )
"""

GM_OBJECTIVE_DEFAULTS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS gm_objective_defaults (
        club_name TEXT NOT NULL,
        gm_name TEXT NOT NULL,
        objective_key TEXT NOT NULL,
        initial_level INTEGER NOT NULL CHECK(initial_level BETWEEN 1 AND 5),
        rationale TEXT NOT NULL,
        PRIMARY KEY(club_name, objective_key)
    )
"""

OPPONENT_PLAYERS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS opponent_players (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        age INTEGER NOT NULL,
        player_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(save_id, player_id),
        FOREIGN KEY(save_id) REFERENCES game_saves(id) ON DELETE CASCADE
    )
"""

PLAYER_RATING_COLUMNS = (
    "con", "pow", "eye", "def", "contact", "power",
    "plate_discipline", "bat_control", "timing", "bunt", "speed",
    "baserunning_judgment", "fielding_range", "catching",
    "throwing_power", "throwing_accuracy", "fielding_judgment",
    "composure", "leadership", "aggressiveness",
)

OBJECTIVE_KEYS = (
    "season_result", "long_term_vision", "front_office_style",
    "club_identity", "roster_balance",
)

GM_OBJECTIVE_SEEDS = {
    "KIA 타이거즈": ("심재학", (5, 3, 4, 4, 3), "우승 전력과 현장 위임 중심"),
    "삼성 라이온즈": ("이종열", (5, 3, 4, 4, 3), "정상권 복귀와 적극 보강 중심"),
    "LG 트윈스": ("차명석", (5, 4, 4, 5, 4), "우승 전력 유지와 내부 육성 병행"),
    "두산 베어스": ("김태룡", (4, 4, 3, 4, 5), "팜 시스템과 내부 대체 자원 중시"),
    "KT 위즈": ("나도현", (4, 3, 4, 3, 3), "검증된 주축과 운영 안정성 중시"),
    "SSG 랜더스": ("김재현", (4, 4, 3, 5, 5), "성적과 세대교체를 함께 추진"),
    "롯데 자이언츠": ("박준혁", (4, 5, 3, 5, 5), "육성 체계와 팬 기대 충족 중시"),
    "한화 이글스": ("손혁", (5, 3, 5, 5, 3), "신구장 시대 즉시 우승 도전"),
    "NC 다이노스": ("임선남", (3, 5, 4, 4, 5), "데이터 기반 효율과 젊은 코어 육성"),
    "키움 히어로즈": ("허승필", (2, 5, 3, 4, 5), "선수 가치와 육성 선순환 최우선"),
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
            self._ensure_governance_state_table(connection)
            self._ensure_gm_objective_defaults(connection)
            connection.execute(OPPONENT_PLAYERS_TABLE_SQL)
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
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

    @staticmethod
    def _ensure_governance_state_table(connection):
        """구버전 세이브에도 이사회·단장 관계 상태 스키마를 보장한다."""
        connection.execute(GOVERNANCE_STATE_TABLE_SQL)

    @staticmethod
    def _ensure_gm_objective_defaults(connection):
        """구단별 단장 원안 5개를 생성하되 운영 중 수정된 값은 보존한다."""
        connection.execute(GM_OBJECTIVE_DEFAULTS_TABLE_SQL)
        rows = []
        for club_name, (gm_name, levels, rationale) in GM_OBJECTIVE_SEEDS.items():
            for objective_key, level in zip(OBJECTIVE_KEYS, levels):
                rows.append((club_name, gm_name, objective_key, level, rationale))
        connection.executemany(
            """
            INSERT OR IGNORE INTO gm_objective_defaults (
                club_name, gm_name, objective_key, initial_level, rationale
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )

    def get_gm_objective_defaults(self, club_name):
        with self.connect() as connection:
            self._ensure_gm_objective_defaults(connection)
            rows = connection.execute(
                """
                SELECT objective_key, initial_level, rationale, gm_name
                FROM gm_objective_defaults
                WHERE club_name = ?
                """,
                (club_name,),
            ).fetchall()
        return {row["objective_key"]: dict(row) for row in rows}

    def create_manager_player_database(self, save_id, manager_name, managed_team):
        """원본을 복제한 감독 전용 선수 DB를 만들고 상대팀 U30만 ±2 조정한다."""
        safe_name = re.sub(r'[^0-9A-Za-z가-힣_-]+', '_', manager_name).strip('_') or "감독"
        save_directory = DATA_DIR / "saves" / str(save_id)
        save_directory.mkdir(parents=True, exist_ok=True)
        target = save_directory / f"{safe_name}_db.sqlite"
        created = not target.exists()
        if created:
            shutil.copy2(PLAYERS_DB_PATH, target)

        connection = sqlite3.connect(target)
        connection.row_factory = sqlite3.Row
        try:
            players = (
                connection.execute(
                    "SELECT id, age, * FROM players WHERE team <> ? AND age < 30",
                    (managed_team,),
                ).fetchall()
                if created else []
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(players)")}
            rating_columns = [column for column in PLAYER_RATING_COLUMNS if column in columns]
            for source_row in players:
                assignments = []
                values = []
                for column in rating_columns:
                    value = source_row[column]
                    if value is None:
                        continue
                    seed_text = f"{save_id}:{source_row['id']}:{column}".encode("utf-8")
                    seed = int.from_bytes(hashlib.sha256(seed_text).digest()[:8], "big")
                    delta = random.Random(seed).randint(-2, 2)
                    assignments.append(f"{column} = ?")
                    values.append(max(1, min(20, int(value) + delta)))
                if assignments:
                    values.append(source_row["id"])
                    connection.execute(
                        f"UPDATE players SET {', '.join(assignments)} WHERE id = ?",
                        values,
                    )
            connection.commit()
            opponent_count = connection.execute(
                "SELECT COUNT(*) AS count FROM players WHERE team <> ?",
                (managed_team,),
            ).fetchone()["count"]
        finally:
            connection.close()

        with self.connect() as saves:
            saves.execute(
                "UPDATE game_saves SET player_db_path = ? WHERE id = ?",
                (str(target), save_id),
            )
        return target, int(opponent_count)

    def list_opponent_players(self, save_id, team_name=None):
        with self.connect() as connection:
            connection.execute(OPPONENT_PLAYERS_TABLE_SQL)
            if team_name:
                rows = connection.execute(
                    "SELECT player_json FROM opponent_players WHERE save_id = ? AND team = ? ORDER BY player_id",
                    (save_id, team_name),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT player_json FROM opponent_players WHERE save_id = ? ORDER BY team, player_id",
                    (save_id,),
                ).fetchall()
        return [json.loads(row["player_json"]) for row in rows]

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
            self._ensure_governance_state_table(connection)
            connection.execute(
                "DELETE FROM daily_news WHERE save_id = ?",
                (save_id,),
            )
            connection.execute(
                "DELETE FROM governance_state WHERE save_id = ?",
                (save_id,),
            )
            connection.execute(OPPONENT_PLAYERS_TABLE_SQL)
            connection.execute(
                "DELETE FROM opponent_players WHERE save_id = ?",
                (save_id,),
            )
            for table_name in (
                "team_ai_decision_queue",
                "player_injury_events",
                "team_training_plans",
                "team_pitching_roles",
                "team_lineups",
                "team_ai_profiles",
                "league_simulation_events",
                "team_roster_decisions",
                "team_daily_states",
                "player_simulation_states",
                "simulation_runs",
            ):
                connection.execute(
                    f"DELETE FROM {table_name} WHERE save_id = ?",
                    (save_id,),
                )
            cursor = connection.execute(
                "DELETE FROM game_saves WHERE id = ?",
                (save_id,),
            )
            return cursor.rowcount > 0

    def list_team_daily_states(self, save_id, simulation_date=None):
        with self.connect() as connection:
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
            if simulation_date:
                rows = connection.execute(
                    """
                    SELECT * FROM team_daily_states
                    WHERE save_id = ? AND simulation_date = ?
                    ORDER BY team
                    """,
                    (save_id, simulation_date),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT state.* FROM team_daily_states state
                    JOIN (
                        SELECT team, MAX(simulation_date) AS latest_date
                        FROM team_daily_states WHERE save_id = ? GROUP BY team
                    ) latest
                    ON latest.team = state.team
                    AND latest.latest_date = state.simulation_date
                    WHERE state.save_id = ? ORDER BY state.team
                    """,
                    (save_id, save_id),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_player_simulation_states(self, save_id, team=None):
        with self.connect() as connection:
            if team:
                rows = connection.execute(
                    """
                    SELECT * FROM player_simulation_states
                    WHERE save_id = ? AND team = ? ORDER BY player_id
                    """,
                    (save_id, team),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM player_simulation_states WHERE save_id = ? ORDER BY team, player_id",
                    (save_id,),
                ).fetchall()
        return {row["player_id"]: dict(row) for row in rows}

    def get_latest_team_assignments(self, save_id, team, squad_level):
        with self.connect() as connection:
            lineup_date = connection.execute(
                """
                SELECT MAX(lineup_date) AS value FROM team_lineups
                WHERE save_id = ? AND team = ? AND squad_level = ?
                """,
                (save_id, team, squad_level),
            ).fetchone()["value"]
            pitching_date = connection.execute(
                """
                SELECT MAX(assignment_date) AS value FROM team_pitching_roles
                WHERE save_id = ? AND team = ? AND squad_level = ?
                """,
                (save_id, team, squad_level),
            ).fetchone()["value"]
            lineups = connection.execute(
                """
                SELECT * FROM team_lineups
                WHERE save_id = ? AND team = ? AND squad_level = ? AND lineup_date = ?
                ORDER BY batting_order
                """,
                (save_id, team, squad_level, lineup_date),
            ).fetchall() if lineup_date else []
            pitchers = connection.execute(
                """
                SELECT * FROM team_pitching_roles
                WHERE save_id = ? AND team = ? AND squad_level = ? AND assignment_date = ?
                ORDER BY role_order
                """,
                (save_id, team, squad_level, pitching_date),
            ).fetchall() if pitching_date else []
        assignments = {}
        for row in lineups:
            assignments[row["player_id"]] = f"{row['batting_order']}번 · {row['defensive_position']}"
        for row in pitchers:
            assignments[row["player_id"]] = row["role"]
        return assignments

    def save_user_lineup(self, save_id, lineup_date, team, assignments):
        """감독이 지정한 타순과 수비 위치를 해당 날짜의 공식 라인업으로 저장한다."""
        with self.connect() as connection:
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
            connection.execute(
                "DELETE FROM team_lineups WHERE save_id=? AND lineup_date=? AND team=? AND squad_level=1",
                (save_id, lineup_date, team),
            )
            for player_id, assignment in assignments.items():
                connection.execute(
                    """INSERT INTO team_lineups
                    (save_id,lineup_date,team,squad_level,batting_order,player_id,
                     player_name,defensive_position,selection_score)
                    VALUES (?,?,?,1,?,?,?,?,0)""",
                    (save_id, lineup_date, team, assignment["order"], player_id,
                     assignment["name"], assignment["position"]),
                )

    def update_player_squad_group(self, save_id, player_id, squad_group):
        with self.connect() as connection:
            connection.execute(
                "UPDATE player_simulation_states SET squad_group=? WHERE save_id=? AND player_id=?",
                (squad_group, save_id, player_id),
            )

    def list_roster_decisions(self, save_id, decision_date=None):
        with self.connect() as connection:
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
            if decision_date:
                rows = connection.execute(
                    """
                    SELECT * FROM team_roster_decisions
                    WHERE save_id = ? AND decision_date = ?
                    ORDER BY team, action, player_name
                    """,
                    (save_id, decision_date),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM team_roster_decisions
                    WHERE save_id = ? ORDER BY decision_date DESC, team, action
                    """,
                    (save_id,),
                ).fetchall()
        return [dict(row) for row in rows]

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
                AND NOT (
                    category = '의료 센터'
                    AND (body LIKE '%발생 당시 소속은 2군,%' OR body LIKE '%기존 2군 선수단%')
                )
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

    def save_governance_state(self, save_id, state):
        """현재 합의 목표·관계도·협상 기록을 수동 저장 시점에 기록한다."""
        now = datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with self.connect() as connection:
            self._ensure_governance_state_table(connection)
            connection.execute(
                """
                INSERT INTO governance_state (
                    save_id, board_confidence, gm_relationship,
                    state_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(save_id) DO UPDATE SET
                    board_confidence = excluded.board_confidence,
                    gm_relationship = excluded.gm_relationship,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    save_id,
                    int(state.get("board_confidence", 75)),
                    int(state.get("gm_relationship", 70)),
                    payload,
                    now,
                ),
            )

    def load_governance_state(self, save_id):
        if save_id is None:
            return None
        with self.connect() as connection:
            self._ensure_governance_state_table(connection)
            row = connection.execute(
                "SELECT state_json FROM governance_state WHERE save_id = ?",
                (save_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["state_json"])
        except (TypeError, json.JSONDecodeError):
            return None
