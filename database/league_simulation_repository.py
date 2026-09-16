"""세이브별 리그 일일 시뮬레이션 상태 저장소."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


SIMULATION_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS player_training_ratings (
        save_id INTEGER NOT NULL, player_id INTEGER NOT NULL, training_date TEXT NOT NULL,
        team TEXT NOT NULL, rating REAL, participation TEXT NOT NULL,
        focus TEXT NOT NULL, detail_json TEXT NOT NULL,
        PRIMARY KEY(save_id,player_id,training_date))""",
    """CREATE TABLE IF NOT EXISTS player_potential_versions (
        save_id INTEGER NOT NULL, player_id INTEGER NOT NULL, version TEXT NOT NULL,
        PRIMARY KEY(save_id,player_id))""",
    """CREATE TABLE IF NOT EXISTS player_attribute_development (
        save_id INTEGER NOT NULL, player_id INTEGER NOT NULL, attribute TEXT NOT NULL,
        ceiling INTEGER NOT NULL, progress REAL NOT NULL DEFAULT 0,
        PRIMARY KEY(save_id,player_id,attribute))""",
    """CREATE TABLE IF NOT EXISTS player_development_events (
        save_id INTEGER NOT NULL, player_id INTEGER NOT NULL, event_date TEXT NOT NULL,
        attribute TEXT NOT NULL, old_value INTEGER NOT NULL, new_value INTEGER NOT NULL,
        reason TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS development_processed_days (
        save_id INTEGER NOT NULL, player_id INTEGER NOT NULL, processed_date TEXT NOT NULL,
        PRIMARY KEY(save_id,player_id,processed_date))""",
    """CREATE TABLE IF NOT EXISTS training_management (
        save_id INTEGER NOT NULL, team TEXT NOT NULL,
        delegate_team INTEGER NOT NULL DEFAULT 0, delegate_individual INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(save_id,team))""",
    """CREATE TABLE IF NOT EXISTS training_delegation_reports (
        save_id INTEGER NOT NULL, team TEXT NOT NULL, report_date TEXT NOT NULL,
        summary TEXT NOT NULL, PRIMARY KEY(save_id,team,report_date))""",
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
    CREATE TABLE IF NOT EXISTS player_manager_relationships (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        trust INTEGER NOT NULL DEFAULT 50,
        respect INTEGER NOT NULL DEFAULT 50,
        last_interaction_date TEXT NOT NULL DEFAULT '',
        successful_talks INTEGER NOT NULL DEFAULT 0,
        failed_talks INTEGER NOT NULL DEFAULT 0,
        broken_promises INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(save_id, player_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_promises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        promise_type TEXT NOT NULL,
        description TEXT NOT NULL,
        created_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        activated_date TEXT NOT NULL DEFAULT '',
        target_value REAL NOT NULL DEFAULT 0,
        progress_value REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        manager_followup TEXT NOT NULL DEFAULT '',
        source_event_id INTEGER,
        UNIQUE(save_id, player_id, promise_type, source_event_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        metric TEXT NOT NULL,
        description TEXT NOT NULL,
        created_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        baseline_value REAL NOT NULL DEFAULT 0,
        target_value REAL NOT NULL DEFAULT 0,
        progress_value REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        source_event_id INTEGER,
        UNIQUE(save_id, player_id, metric, source_event_id)
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
    CREATE TABLE IF NOT EXISTS team_tactic_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        name TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 0,
        batting_json TEXT NOT NULL DEFAULT '[]',
        pitching_json TEXT NOT NULL DEFAULT '[]',
        game_plan_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(save_id, team, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS foreign_contract_decisions (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        decision TEXT NOT NULL,
        previous_salary INTEGER NOT NULL,
        offer_salary INTEGER NOT NULL DEFAULT 0,
        decided_at TEXT NOT NULL,
        PRIMARY KEY(save_id, player_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS foreign_fa_market (
        save_id INTEGER NOT NULL,
        candidate_id TEXT NOT NULL,
        player_json TEXT NOT NULL,
        asking_salary INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'available',
        signed_team TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, candidate_id)
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
    CREATE TABLE IF NOT EXISTS team_training_settings (
        save_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        focus TEXT NOT NULL DEFAULT '균형',
        intensity INTEGER NOT NULL DEFAULT 3,
        rest_policy TEXT NOT NULL DEFAULT '보통',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, team)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS individual_training_plans (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        focus TEXT NOT NULL DEFAULT '자동',
        intensity INTEGER NOT NULL DEFAULT 2,
        coach_id INTEGER,
        active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, player_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS weekly_training_sessions (
        save_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        session_date TEXT NOT NULL,
        slot TEXT NOT NULL,
        session_type TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, team, session_date, slot)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_training_units (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        unit_name TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, player_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS coaching_staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        team TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        specialty TEXT NOT NULL,
        development INTEGER NOT NULL,
        fitness INTEGER NOT NULL,
        tactical INTEGER NOT NULL,
        reputation INTEGER NOT NULL,
        salary_10k INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'candidate',
        hired_at TEXT NOT NULL DEFAULT '',
        contract_end TEXT NOT NULL DEFAULT '',
        squad TEXT NOT NULL DEFAULT '1군',
        batting INTEGER NOT NULL DEFAULT 8,
        pitching INTEGER NOT NULL DEFAULT 8,
        defense INTEGER NOT NULL DEFAULT 8,
        baserunning INTEGER NOT NULL DEFAULT 8,
        catching INTEGER NOT NULL DEFAULT 8,
        mental INTEGER NOT NULL DEFAULT 10,
        motivation INTEGER NOT NULL DEFAULT 10,
        discipline INTEGER NOT NULL DEFAULT 10,
        man_management INTEGER NOT NULL DEFAULT 10,
        adaptability INTEGER NOT NULL DEFAULT 10,
        youth_development INTEGER NOT NULL DEFAULT 10,
        data_analysis INTEGER NOT NULL DEFAULT 10,
        current_ability INTEGER NOT NULL DEFAULT 100,
        potential_ability INTEGER NOT NULL DEFAULT 110,
        personality TEXT NOT NULL DEFAULT '신중함',
        coaching_style TEXT NOT NULL DEFAULT '균형형',
        qualification TEXT NOT NULL DEFAULT 'KBO 지도자',
        experience_years INTEGER NOT NULL DEFAULT 1,
        source_url TEXT NOT NULL DEFAULT '',
        source_label TEXT NOT NULL DEFAULT '',
        source_as_of TEXT NOT NULL DEFAULT '2025-01-31',
        is_real INTEGER NOT NULL DEFAULT 0,
        UNIQUE(save_id, team, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS coach_assignments (
        save_id INTEGER NOT NULL,
        coach_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        assignment_type TEXT NOT NULL,
        target_id INTEGER NOT NULL DEFAULT 0,
        focus TEXT NOT NULL,
        workload INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(save_id, coach_id, assignment_type, target_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_conditional_cash_obligations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        paying_team TEXT NOT NULL,
        receiving_team TEXT NOT NULL,
        amount_10k INTEGER NOT NULL,
        condition_text TEXT NOT NULL,
        probability INTEGER NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        source_event_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(save_id, source_event_id, paying_team, amount_10k)
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
    """
    CREATE TABLE IF NOT EXISTS incoming_rookies (
        save_id INTEGER NOT NULL,
        draft_year INTEGER NOT NULL,
        event_date TEXT NOT NULL,
        overall_pick INTEGER NOT NULL,
        round_no INTEGER NOT NULL,
        team TEXT NOT NULL,
        player_name TEXT NOT NULL,
        position_group TEXT NOT NULL,
        position_name TEXT NOT NULL,
        school TEXT NOT NULL,
        is_early_draft INTEGER NOT NULL DEFAULT 0,
        arrival_date TEXT NOT NULL DEFAULT '2026-01-01',
        status TEXT NOT NULL DEFAULT 'incoming',
        source_url TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(save_id, draft_year, overall_pick)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS second_draft_settings (
        save_id INTEGER PRIMARY KEY,
        mode TEXT NOT NULL DEFAULT 'ai',
        status TEXT NOT NULL DEFAULT 'not_prepared',
        prepared_at TEXT,
        completed_at TEXT,
        source_note TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS second_draft_pool (
        save_id INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        kbo_player_id TEXT NOT NULL DEFAULT '',
        player_name TEXT NOT NULL,
        original_team TEXT NOT NULL,
        position_group TEXT NOT NULL DEFAULT '',
        age INTEGER NOT NULL DEFAULT 0,
        entry_year INTEGER,
        service_year INTEGER,
        roster_status INTEGER NOT NULL DEFAULT 0,
        salary INTEGER NOT NULL DEFAULT 0,
        overall REAL NOT NULL DEFAULT 0,
        potential REAL NOT NULL DEFAULT 0,
        protection_score REAL NOT NULL DEFAULT 0,
        classification TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        component_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(save_id, player_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS second_draft_results (
        save_id INTEGER NOT NULL,
        mode TEXT NOT NULL,
        round_no INTEGER NOT NULL,
        pick_order INTEGER NOT NULL,
        selecting_team TEXT NOT NULL,
        original_team TEXT NOT NULL,
        player_id INTEGER,
        kbo_player_id TEXT NOT NULL DEFAULT '',
        player_name TEXT NOT NULL,
        position_group TEXT NOT NULL DEFAULT '',
        fee INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(save_id, mode, pick_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS practice_games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        game_date TEXT NOT NULL,
        managed_team TEXT NOT NULL,
        opponent_team TEXT NOT NULL,
        venue_type TEXT NOT NULL DEFAULT 'home',
        stadium TEXT NOT NULL DEFAULT '',
        start_time TEXT NOT NULL DEFAULT '13:00',
        innings INTEGER NOT NULL DEFAULT 9,
        purpose TEXT NOT NULL DEFAULT '전력 점검',
        lineup_policy TEXT NOT NULL DEFAULT '주전 중심',
        pitching_plan TEXT NOT NULL DEFAULT '선발 3이닝 제한',
        status TEXT NOT NULL DEFAULT 'scheduled',
        managed_score INTEGER,
        opponent_score INTEGER,
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(save_id, managed_team, game_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS practice_game_roster (
        game_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'bench',
        batting_order INTEGER NOT NULL DEFAULT 0,
        position TEXT NOT NULL DEFAULT '',
        is_starter INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(game_id, team, player_id),
        FOREIGN KEY(game_id) REFERENCES practice_games(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS practice_game_plays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        sequence_no INTEGER NOT NULL,
        inning INTEGER NOT NULL,
        half TEXT NOT NULL,
        offense_team TEXT NOT NULL,
        batter_id INTEGER,
        batter_name TEXT NOT NULL DEFAULT '',
        pitcher_id INTEGER,
        pitcher_name TEXT NOT NULL DEFAULT '',
        result_code TEXT NOT NULL,
        description TEXT NOT NULL,
        runs_scored INTEGER NOT NULL DEFAULT 0,
        managed_score INTEGER NOT NULL DEFAULT 0,
        opponent_score INTEGER NOT NULL DEFAULT 0,
        outs_after INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(game_id) REFERENCES practice_games(id) ON DELETE CASCADE,
        UNIQUE(game_id, sequence_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS practice_game_player_stats (
        game_id INTEGER NOT NULL,
        team TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        squad_group TEXT NOT NULL DEFAULT '',
        batting_order INTEGER NOT NULL DEFAULT 0,
        position TEXT NOT NULL DEFAULT '',
        plate_appearances INTEGER NOT NULL DEFAULT 0,
        at_bats INTEGER NOT NULL DEFAULT 0,
        runs INTEGER NOT NULL DEFAULT 0,
        hits INTEGER NOT NULL DEFAULT 0,
        doubles INTEGER NOT NULL DEFAULT 0,
        triples INTEGER NOT NULL DEFAULT 0,
        home_runs INTEGER NOT NULL DEFAULT 0,
        walks INTEGER NOT NULL DEFAULT 0,
        strikeouts INTEGER NOT NULL DEFAULT 0,
        rbi INTEGER NOT NULL DEFAULT 0,
        innings_outs INTEGER NOT NULL DEFAULT 0,
        hits_allowed INTEGER NOT NULL DEFAULT 0,
        runs_allowed INTEGER NOT NULL DEFAULT 0,
        walks_allowed INTEGER NOT NULL DEFAULT 0,
        strikeouts_pitched INTEGER NOT NULL DEFAULT 0,
        pitches INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(game_id, team, player_id),
        FOREIGN KEY(game_id) REFERENCES practice_games(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS practice_game_live_states (
        game_id INTEGER PRIMARY KEY,
        state_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL,
        FOREIGN KEY(game_id) REFERENCES practice_games(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS manager_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id INTEGER NOT NULL,
        event_date TEXT NOT NULL,
        category TEXT NOT NULL,
        event_type TEXT NOT NULL,
        headline TEXT NOT NULL,
        body TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'normal',
        requires_action INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'open',
        choices_json TEXT NOT NULL DEFAULT '[]',
        payload_json TEXT NOT NULL DEFAULT '{}',
        resolution_key TEXT,
        result_text TEXT NOT NULL DEFAULT '',
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        UNIQUE(save_id, event_date, event_type, headline)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS national_team_callups (
        save_id INTEGER NOT NULL,
        series_id TEXT NOT NULL,
        player_id INTEGER,
        player_name TEXT NOT NULL,
        club_team TEXT NOT NULL,
        position_group TEXT NOT NULL,
        join_date TEXT NOT NULL,
        release_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'selected',
        source_url TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(save_id, series_id, player_name, club_team)
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

COACHING_STAFF_COLUMNS = {
    "squad": "TEXT NOT NULL DEFAULT '1군'",
    "batting": "INTEGER NOT NULL DEFAULT 8",
    "pitching": "INTEGER NOT NULL DEFAULT 8",
    "defense": "INTEGER NOT NULL DEFAULT 8",
    "baserunning": "INTEGER NOT NULL DEFAULT 8",
    "catching": "INTEGER NOT NULL DEFAULT 8",
    "mental": "INTEGER NOT NULL DEFAULT 10",
    "motivation": "INTEGER NOT NULL DEFAULT 10",
    "discipline": "INTEGER NOT NULL DEFAULT 10",
    "man_management": "INTEGER NOT NULL DEFAULT 10",
    "adaptability": "INTEGER NOT NULL DEFAULT 10",
    "youth_development": "INTEGER NOT NULL DEFAULT 10",
    "data_analysis": "INTEGER NOT NULL DEFAULT 10",
    "current_ability": "INTEGER NOT NULL DEFAULT 100",
    "potential_ability": "INTEGER NOT NULL DEFAULT 110",
    "personality": "TEXT NOT NULL DEFAULT '신중함'",
    "coaching_style": "TEXT NOT NULL DEFAULT '균형형'",
    "qualification": "TEXT NOT NULL DEFAULT 'KBO 지도자'",
    "experience_years": "INTEGER NOT NULL DEFAULT 1",
    "source_url": "TEXT NOT NULL DEFAULT ''",
    "source_label": "TEXT NOT NULL DEFAULT ''",
    "source_as_of": "TEXT NOT NULL DEFAULT '2025-01-31'",
    "is_real": "INTEGER NOT NULL DEFAULT 0",
}


def ensure_simulation_migrations(connection):
    """CREATE TABLE만으로 보강되지 않는 기존 세이브 열을 추가한다."""
    promise_columns = {
        row["name"] for row in connection.execute(
            "PRAGMA table_info(player_promises)"
        ).fetchall()
    }
    if promise_columns and "activated_date" not in promise_columns:
        connection.execute(
            "ALTER TABLE player_promises "
            "ADD COLUMN activated_date TEXT NOT NULL DEFAULT ''"
        )


def ensure_coaching_staff_team_identity(connection):
    """Allow namesakes at different clubs while preserving existing coach IDs."""
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='coaching_staff'"
    ).fetchone()
    table_sql = str(row["sql"] if row else "").replace(" ", "").lower()
    if "unique(save_id,name)" not in table_sql:
        return
    columns = tuple(COACHING_STAFF_COLUMNS)
    base_columns = (
        "id", "save_id", "team", "name", "role", "specialty", "development",
        "fitness", "tactical", "reputation", "salary_10k", "status", "hired_at",
        "contract_end",
    )
    all_columns = base_columns + columns
    column_list = ",".join(all_columns)
    connection.execute("ALTER TABLE coaching_staff RENAME TO coaching_staff_legacy")
    connection.execute(
        """
        CREATE TABLE coaching_staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            save_id INTEGER NOT NULL,
            team TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            specialty TEXT NOT NULL,
            development INTEGER NOT NULL,
            fitness INTEGER NOT NULL,
            tactical INTEGER NOT NULL,
            reputation INTEGER NOT NULL,
            salary_10k INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate',
            hired_at TEXT NOT NULL DEFAULT '',
            contract_end TEXT NOT NULL DEFAULT '',
            squad TEXT NOT NULL DEFAULT '1군',
            batting INTEGER NOT NULL DEFAULT 8,
            pitching INTEGER NOT NULL DEFAULT 8,
            defense INTEGER NOT NULL DEFAULT 8,
            baserunning INTEGER NOT NULL DEFAULT 8,
            catching INTEGER NOT NULL DEFAULT 8,
            mental INTEGER NOT NULL DEFAULT 10,
            motivation INTEGER NOT NULL DEFAULT 10,
            discipline INTEGER NOT NULL DEFAULT 10,
            man_management INTEGER NOT NULL DEFAULT 10,
            adaptability INTEGER NOT NULL DEFAULT 10,
            youth_development INTEGER NOT NULL DEFAULT 10,
            data_analysis INTEGER NOT NULL DEFAULT 10,
            current_ability INTEGER NOT NULL DEFAULT 100,
            potential_ability INTEGER NOT NULL DEFAULT 110,
            personality TEXT NOT NULL DEFAULT '신중함',
            coaching_style TEXT NOT NULL DEFAULT '균형형',
            qualification TEXT NOT NULL DEFAULT 'KBO 지도자',
            experience_years INTEGER NOT NULL DEFAULT 1,
            source_url TEXT NOT NULL DEFAULT '',
            source_label TEXT NOT NULL DEFAULT '',
            source_as_of TEXT NOT NULL DEFAULT '2025-01-31',
            is_real INTEGER NOT NULL DEFAULT 0,
            UNIQUE(save_id, team, name)
        )
        """
    )
    connection.execute(
        f"INSERT INTO coaching_staff ({column_list}) "
        f"SELECT {column_list} FROM coaching_staff_legacy"
    )
    connection.execute("DROP TABLE coaching_staff_legacy")


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
        connection = self.connect()
        try:
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
            ensure_simulation_migrations(connection)
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
            staff_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(coaching_staff)"
                ).fetchall()
            }
            for column, declaration in COACHING_STAFF_COLUMNS.items():
                if column not in staff_columns:
                    connection.execute(
                        f"ALTER TABLE coaching_staff ADD COLUMN {column} {declaration}"
                    )
            ensure_coaching_staff_team_identity(connection)
            connection.commit()
        finally:
            connection.close()

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
