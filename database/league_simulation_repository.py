"""세이브별 리그 일일 시뮬레이션 상태 저장소."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


SIMULATION_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS simulation_runs (
        save_id INTEGER NOT NULL,
        simulation_date TEXT NOT NULL,
        status TEXT NOT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
        started_at TEXT NOT NULL,
        completed_at TEXT,
        PRIMARY KEY(save_id, simulation_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_simulation_states (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        condition INTEGER NOT NULL DEFAULT 85,
        fatigue INTEGER NOT NULL DEFAULT 0,
        training_points INTEGER NOT NULL DEFAULT 0,
        injury_days INTEGER NOT NULL DEFAULT 0,
        match_sharpness INTEGER NOT NULL DEFAULT 55,
        morale INTEGER NOT NULL DEFAULT 75,
        injury_risk INTEGER NOT NULL DEFAULT 5,
        squad_group TEXT NOT NULL DEFAULT '2군',
        injury_type TEXT NOT NULL DEFAULT '',
        last_updated TEXT NOT NULL,
        PRIMARY KEY(save_id, player_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_daily_states (
        save_id INTEGER NOT NULL,
        simulation_date TEXT NOT NULL,
        team TEXT NOT NULL,
        season_phase TEXT NOT NULL,
        first_team_count INTEGER NOT NULL,
        second_team_count INTEGER NOT NULL,
        average_condition REAL NOT NULL,
        injured_count INTEGER NOT NULL DEFAULT 0,
        roster_need TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(save_id, simulation_date, team)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_roster_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        decision_date TEXT NOT NULL,
        team TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(save_id, decision_date, team, player_id, action)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_simulation_events (
        save_id INTEGER NOT NULL,
        event_date TEXT NOT NULL,
        team TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        detail TEXT NOT NULL,
        PRIMARY KEY(save_id, event_date, team, title)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_ai_profiles (
        save_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        win_now INTEGER NOT NULL,
        development INTEGER NOT NULL,
        roster_aggression INTEGER NOT NULL,
        stability INTEGER NOT NULL,
        risk_tolerance INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, team)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_lineups (
        save_id INTEGER NOT NULL,
        lineup_date TEXT NOT NULL,
        team TEXT NOT NULL,
        squad_level INTEGER NOT NULL,
        batting_order INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        defensive_position TEXT NOT NULL,
        selection_score REAL NOT NULL,
        PRIMARY KEY(save_id, lineup_date, team, squad_level, batting_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_pitching_roles (
        save_id INTEGER NOT NULL,
        assignment_date TEXT NOT NULL,
        team TEXT NOT NULL,
        squad_level INTEGER NOT NULL,
        role_order INTEGER NOT NULL,
        role TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        selection_score REAL NOT NULL,
        PRIMARY KEY(save_id, assignment_date, team, squad_level, role_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_training_plans (
        save_id INTEGER NOT NULL,
        plan_date TEXT NOT NULL,
        team TEXT NOT NULL,
        season_phase TEXT NOT NULL,
        focus TEXT NOT NULL,
        intensity INTEGER NOT NULL,
        note TEXT NOT NULL,
        PRIMARY KEY(save_id, plan_date, team)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_injury_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        event_date TEXT NOT NULL,
        team TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        injury_type TEXT NOT NULL,
        expected_days INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        UNIQUE(save_id, event_date, player_id, injury_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS team_ai_decision_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        decision_date TEXT NOT NULL,
        team TEXT NOT NULL,
        decision_type TEXT NOT NULL,
        context_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ready_for_qwen',
        result_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(save_id, decision_date, team, decision_type)
    )
    """,
)

PLAYER_STATE_COLUMNS = {
    "match_sharpness": "INTEGER NOT NULL DEFAULT 55",
    "morale": "INTEGER NOT NULL DEFAULT 75",
    "injury_risk": "INTEGER NOT NULL DEFAULT 5",
    "squad_group": "TEXT NOT NULL DEFAULT '2군'",
    "injury_type": "TEXT NOT NULL DEFAULT ''",
}


class LeagueSimulationRepository:
    def __init__(self, saves_db_path, player_db_path):
        self.saves_db_path = Path(saves_db_path)
        self.player_db_path = Path(player_db_path)
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.saves_db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self):
        with self.connect() as connection:
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(player_simulation_states)"
                ).fetchall()
            }
            for column, declaration in PLAYER_STATE_COLUMNS.items():
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE player_simulation_states ADD COLUMN {column} {declaration}"
                    )

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("ATTACH DATABASE ? AS playerdb", (str(self.player_db_path),))
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def completed_summary(connection, save_id, simulation_date):
        row = connection.execute(
            """
            SELECT summary_json FROM simulation_runs
            WHERE save_id = ? AND simulation_date = ? AND status = 'completed'
            """,
            (save_id, simulation_date),
        ).fetchone()
        return json.loads(row["summary_json"]) if row else None

    @staticmethod
    def begin_run(connection, save_id, simulation_date):
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute(
            """
            INSERT INTO simulation_runs (
                save_id, simulation_date, status, summary_json, started_at
            ) VALUES (?, ?, 'running', '{}', ?)
            ON CONFLICT(save_id, simulation_date) DO UPDATE SET
                status = 'running', summary_json = '{}',
                started_at = excluded.started_at, completed_at = NULL
            """,
            (save_id, simulation_date, now),
        )

    @staticmethod
    def complete_run(connection, save_id, simulation_date, summary):
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute(
            """
            UPDATE simulation_runs
            SET status = 'completed', summary_json = ?, completed_at = ?
            WHERE save_id = ? AND simulation_date = ?
            """,
            (
                json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                now,
                save_id,
                simulation_date,
            ),
        )

    @staticmethod
    def save_roster_decision(connection, save_id, simulation_date, decision):
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute(
            """
            INSERT OR IGNORE INTO team_roster_decisions (
                save_id, decision_date, team, player_id, player_name,
                action, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                save_id,
                simulation_date,
                decision["team"],
                decision["player_id"],
                decision["player_name"],
                decision["action"],
                decision["reason"],
                now,
            ),
        )

    @staticmethod
    def save_team_state(connection, save_id, simulation_date, state):
        connection.execute(
            """
            INSERT INTO team_daily_states (
                save_id, simulation_date, team, season_phase,
                first_team_count, second_team_count, average_condition,
                injured_count, roster_need
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(save_id, simulation_date, team) DO UPDATE SET
                season_phase = excluded.season_phase,
                first_team_count = excluded.first_team_count,
                second_team_count = excluded.second_team_count,
                average_condition = excluded.average_condition,
                injured_count = excluded.injured_count,
                roster_need = excluded.roster_need
            """,
            (
                save_id,
                simulation_date,
                state["team"],
                state["season_phase"],
                state["first_team_count"],
                state["second_team_count"],
                state["average_condition"],
                state["injured_count"],
                state["roster_need"],
            ),
        )

    @staticmethod
    def save_schedule_event(connection, save_id, simulation_date, team, event):
        connection.execute(
            """
            INSERT OR IGNORE INTO league_simulation_events (
                save_id, event_date, team, category, title, detail
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                save_id,
                simulation_date,
                team,
                event["category"],
                event["title"],
                event["detail"],
            ),
        )

    @staticmethod
    def add_league_news(connection, save_id, simulation_date, decisions):
        if not decisions:
            return
        teams = sorted({decision["team"] for decision in decisions})
        promoted = [d for d in decisions if d["action"] == "promote"]
        summary = ", ".join(
            f"{decision['team']} {decision['player_name']} 콜업"
            for decision in promoted[:5]
        )
        if len(promoted) > 5:
            summary += f" 외 {len(promoted) - 5}건"
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute(
            """
            INSERT OR IGNORE INTO daily_news (
                save_id, news_date, category, headline, body, created_at
            ) VALUES (?, ?, '리그', ?, ?, ?)
            """,
            (
                save_id,
                simulation_date,
                f"상대 구단 선수단 변동 · {len(teams)}개 구단",
                summary,
                now,
            ),
        )
