import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

from app.services.domestic_fa import DomesticFAService
from app.services.manager_events import ManagerEventService
from app.services.training import TrainingService
from database.league_simulation_repository import SIMULATION_SCHEMA


DAILY_NEWS_SQL = """
CREATE TABLE daily_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id INTEGER NOT NULL,
    news_date TEXT NOT NULL,
    category TEXT NOT NULL,
    headline TEXT NOT NULL,
    body TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(save_id, news_date, headline)
)
"""


class NovemberWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.saves_path = root / "save.db"
        self.players_path = root / "players.db"
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            for statement in SIMULATION_SCHEMA:
                connection.execute(statement)
            connection.execute(DAILY_NEWS_SQL)
        with closing(sqlite3.connect(self.players_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY,
                    team TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status INTEGER NOT NULL DEFAULT 0,
                    lineup_pos INTEGER NOT NULL DEFAULT 0,
                    role TEXT NOT NULL DEFAULT '',
                    salary INTEGER NOT NULL DEFAULT 0,
                    age INTEGER NOT NULL DEFAULT 25,
                    position_group TEXT NOT NULL DEFAULT 'P',
                    pos TEXT NOT NULL DEFAULT 'P',
                    is_foreign INTEGER NOT NULL DEFAULT 0,
                    is_rookie INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        self.service = ManagerEventService(
            self.saves_path, self.players_path,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _event(self, event_date):
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT * FROM manager_events
                WHERE save_id=1 AND event_date=? AND requires_action=1
                ORDER BY id DESC LIMIT 1
                """,
                (event_date,),
            ).fetchone()
            return dict(row)

    def test_start_date_event_is_seeded_and_strategy_is_persisted(self):
        self.service.ensure_schedule_date(1, "KIA 타이거즈", date(2025, 11, 1))
        event = self._event("2025-11-01")
        choices = json.loads(event["choices_json"])
        self.assertTrue(event["requires_action"])
        self.assertEqual(
            {"win_now", "balanced", "development"},
            {choice["key"] for choice in choices},
        )
        self.service.resolve(1, event["id"], "balanced")
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            decision = connection.execute(
                """
                SELECT decision FROM offseason_strategy_decisions
                WHERE save_id=1 AND team='KIA 타이거즈'
                  AND event_id='offseason_open'
                """
            ).fetchone()[0]
        self.assertEqual("balanced", decision)

    def test_november_27_start_carries_over_reserve_submission(self):
        with closing(sqlite3.connect(self.players_path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO players (id,team,name,status,lineup_pos,role)
                VALUES (77,'KIA 타이거즈','이월 점검 선수',1,1,'선수')
                """
            )
        self.service.ensure_schedule_date(
            1, "KIA 타이거즈", date(2025, 11, 27)
        )
        with closing(sqlite3.connect(self.saves_path)) as connection:
            rows = [
                (row[0], json.loads(row[1]))
                for row in connection.execute(
                    """
                    SELECT id,payload_json FROM manager_events
                    WHERE save_id=1 AND event_date='2025-11-27'
                    ORDER BY id
                    """
                )
            ]
        event_ids = {
            payload["schedule_event"]["event_id"] for _id, payload in rows
        }
        self.assertEqual(
            {"reserve_submit", "november_review"}, event_ids
        )
        reserve_id = next(
            event_id for event_id, payload in rows
            if payload["schedule_event"]["event_id"] == "reserve_submit"
        )
        self.service.resolve(
            1, reserve_id, "submit_reserve",
            resolution_data={"players": ({
                "player_id": 77, "player_name": "이월 점검 선수",
                "decision": "보류·재계약",
            },)},
        )
        with closing(sqlite3.connect(self.saves_path)) as connection:
            review_body = connection.execute(
                """
                SELECT body FROM manager_events
                WHERE save_id=1 AND status='open' AND headline='11월 전력 정비 결산'
                """
            ).fetchone()[0]
        self.assertIn("보류 1명", review_body)

    def test_domestic_fa_market_is_locked_until_november_ninth(self):
        service = DomesticFAService(
            self.saves_path, self.players_path, 1, "KIA 타이거즈",
            date(2025, 11, 8),
        )
        self.assertFalse(service.market_is_open())
        service.set_game_date(date(2025, 11, 9))
        self.assertTrue(service.market_is_open())

    def test_coaching_staff_event_requires_three_core_assignments(self):
        self.service.ensure_schedule_date(1, "KIA 타이거즈", date(2025, 11, 2))
        event = self._event("2025-11-02")
        with self.assertRaises(ValueError):
            self.service.resolve(1, event["id"], "complete_staff_review")

        training = TrainingService(
            self.saves_path, self.players_path, 1, "KIA 타이거즈"
        )
        coaches = [
            coach for coach in training.coaches("hired")
            if coach["team"] == "KIA 타이거즈"
        ]
        for coach, focus in zip(coaches[:3], ("타격", "투수", "수비")):
            training.assign_coach(coach["id"], "team", 0, focus)
        result = self.service.resolve(
            1, event["id"], "complete_staff_review"
        )
        self.assertIn("업무 배정을 확정", result)

    def test_training_event_requires_team_plan_and_three_players(self):
        with closing(sqlite3.connect(self.players_path)) as connection, connection:
            connection.executemany(
                """
                INSERT INTO players (id,team,name,position_group,pos)
                VALUES (?,'KIA 타이거즈',?,'IF','1B')
                """,
                ((1, "훈련1"), (2, "훈련2"), (3, "훈련3")),
            )
        self.service.ensure_schedule_date(1, "KIA 타이거즈", date(2025, 11, 4))
        event = self._event("2025-11-04")
        training = TrainingService(
            self.saves_path, self.players_path, 1, "KIA 타이거즈"
        )
        training.set_team_setting("균형", 3, "보통")
        training.set_weekly_schedule(training.weekly_schedule())
        for player_id in (1, 2):
            training.set_individual_plan(player_id, "컨택", 2)
        with self.assertRaises(ValueError):
            self.service.resolve(1, event["id"], "complete_training_plan")
        training.set_individual_plan(3, "컨택", 2)
        result = self.service.resolve(
            1, event["id"], "complete_training_plan"
        )
        self.assertIn("개인 계획 3명", result)

    def test_manager_protection_list_replaces_ai_list(self):
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            for player_id in range(1, 41):
                connection.execute(
                    """
                    INSERT INTO second_draft_pool (
                        save_id, player_id, player_name, original_team,
                        classification, protection_score
                    ) VALUES (1, ?, ?, 'KIA 타이거즈', ?, ?)
                    """,
                    (
                        player_id, f"선수{player_id}",
                        "protected" if player_id <= 35 else "available",
                        100 - player_id,
                    ),
                )
        self.service.ensure_schedule_date(1, "KIA 타이거즈", date(2025, 11, 12))
        event = self._event("2025-11-12")
        manager_ids = list(range(6, 41))
        self.service.resolve(
            1, event["id"], "submit_protection",
            resolution_data={"protected_player_ids": manager_ids},
        )
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            protected = {
                row[0] for row in connection.execute(
                    """
                    SELECT player_id FROM second_draft_pool
                    WHERE save_id=1 AND original_team='KIA 타이거즈'
                      AND classification='protected'
                    """
                )
            }
        self.assertEqual(set(manager_ids), protected)

    def test_reserve_submission_changes_actual_roster(self):
        with closing(sqlite3.connect(self.players_path)) as connection, connection:
            connection.executemany(
                """
                INSERT INTO players (id, team, name, status, lineup_pos, role)
                VALUES (?, 'KIA 타이거즈', ?, 1, 1, '선수')
                """,
                ((1, "보류 선수"), (2, "육성 선수"), (3, "방출 선수")),
            )
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            connection.executemany(
                """
                INSERT INTO player_simulation_states (
                    save_id, player_id, team, last_updated
                ) VALUES (1, ?, 'KIA 타이거즈', '2025-11-25')
                """,
                ((1,), (2,), (3,)),
            )
        self.service.ensure_schedule_date(1, "KIA 타이거즈", date(2025, 11, 25))
        event = self._event("2025-11-25")
        self.service.resolve(
            1, event["id"], "submit_reserve",
            resolution_data={
                "players": (
                    {"player_id": 1, "player_name": "보류 선수", "decision": "보류·재계약"},
                    {"player_id": 2, "player_name": "육성 선수", "decision": "퓨처스 육성"},
                    {"player_id": 3, "player_name": "방출 선수", "decision": "자유계약 공시"},
                )
            },
        )
        with closing(sqlite3.connect(self.players_path)) as connection, connection:
            rows = {
                row[0]: row[1:] for row in connection.execute(
                    "SELECT id, team, status, role FROM players ORDER BY id"
                )
            }
        self.assertEqual(("KIA 타이거즈", 1, "선수"), rows[1])
        self.assertEqual(("KIA 타이거즈", 0, "육성"), rows[2])
        self.assertEqual(("자유계약선수", 0, "방출"), rows[3])

    def test_player_meeting_relationship_update_has_matching_bindings(self):
        with closing(sqlite3.connect(self.saves_path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO player_simulation_states (
                    save_id, player_id, team, last_updated
                ) VALUES (1, 99, 'KIA 타이거즈', '2025-11-06')
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO manager_events (
                    save_id, event_date, category, event_type, headline, body,
                    requires_action, choices_json, payload_json
                ) VALUES (1, '2025-11-06', '선수 면담', 'player_complaint',
                          '면담', '기용 계획 면담', 1, ?, ?)
                """,
                (
                    json.dumps((
                        {"key": "promise", "label": "약속", "description": ""},
                        {"key": "firm", "label": "거절", "description": ""},
                    ), ensure_ascii=False),
                    json.dumps({
                        "player_id": 99, "player_name": "면담 선수",
                        "negotiation": {"score": 50},
                        "meeting_commitment": {"made_on": "2025-11-06"},
                    }, ensure_ascii=False),
                ),
            )
            event_id = cursor.lastrowid
        self.service.resolve(1, event_id, "firm")
        with closing(sqlite3.connect(self.saves_path)) as connection:
            relationship = connection.execute(
                """
                SELECT trust, respect, failed_talks
                FROM player_manager_relationships
                WHERE save_id=1 AND player_id=99
                """
            ).fetchone()
        self.assertIsNotNone(relationship)
        self.assertEqual(1, relationship[2])


if __name__ == "__main__":
    unittest.main()
