import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from app.services.league_simulation import LeagueSimulationService
from app.services.manager_events import ManagerEventService
from app.services.second_draft import SecondDraftService
from app.services.training import TrainingService
from database.paths import PLAYERS_DB_PATH
from database.save_database import SaveDatabase


class NovemberProgressionTests(unittest.TestCase):
    def test_full_month_progresses_without_skipping_required_workflows(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            saves_path = root / "save.db"
            players_path = root / "players.db"
            shutil.copy2(PLAYERS_DB_PATH, players_path)
            save_database = SaveDatabase(saves_path)
            save_id = save_database.create_save(
                "KIA 타이거즈", "KIA 타이거즈",
                current_date="2025-11-01",
            )
            manager_events = ManagerEventService(saves_path, players_path)
            manager_events.ensure_schedule_date(
                save_id, "KIA 타이거즈", date(2025, 11, 1),
            )
            self._resolve_required(
                save_database, manager_events, players_path, save_id,
            )

            current = date(2025, 11, 1)
            with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
                while current < date(2025, 11, 30):
                    current += timedelta(days=1)
                    LeagueSimulationService(
                        save_database, save_id, players_path, "KIA 타이거즈",
                    ).simulate_day(current)
                    SecondDraftService(
                        save_database, save_id, players_path,
                    ).process_date(current)
                    self._resolve_required(
                        save_database, manager_events, players_path, save_id,
                    )

            save = save_database.get_save(save_id)
            self.assertEqual("2025-11-30", save["current_date"])
            with closing(sqlite3.connect(saves_path)) as connection, connection:
                completed_days = connection.execute(
                    """
                    SELECT COUNT(*) FROM simulation_runs
                    WHERE save_id=? AND status='completed'
                    """,
                    (save_id,),
                ).fetchone()[0]
                open_required = connection.execute(
                    """
                    SELECT COUNT(*) FROM manager_events
                    WHERE save_id=? AND requires_action=1 AND status='open'
                    """,
                    (save_id,),
                ).fetchone()[0]
                schedule_ids = {
                    json.loads(row[0])["schedule_event"]["event_id"]
                    for row in connection.execute(
                        """
                        SELECT payload_json FROM manager_events
                        WHERE save_id=? AND event_type='schedule'
                        """,
                        (save_id,),
                    )
                }
                strategy_ids = {
                    row[0] for row in connection.execute(
                        """
                        SELECT event_id FROM offseason_strategy_decisions
                        WHERE save_id=? AND team='KIA 타이거즈'
                        """,
                        (save_id,),
                    )
                }
            self.assertEqual(29, completed_days)
            self.assertEqual(0, open_required)
            self.assertEqual(
                {
                    "offseason_open", "coaching_staff_review", "roster_audit",
                    "national_team_roster", "national_team_callup",
                    "offseason_training_plan", "national_team_late_join", "fa_eligible",
                    "fa_approved", "fa_market_open", "second_draft_protect",
                    "national_team_departure", "national_team_return",
                    "second_draft", "draft_integration", "kbo_awards",
                    "reserve_submit", "november_review", "reserve_publication",
                },
                schedule_ids,
            )
            self.assertTrue({
                "offseason_open", "fa_eligible", "fa_approved",
                "fa_market_open", "draft_integration", "november_review",
            } <= strategy_ids)

    def test_named_official_events_change_real_player_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            saves_path = root / "save.db"
            players_path = root / "players.db"
            shutil.copy2(PLAYERS_DB_PATH, players_path)
            save_database = SaveDatabase(saves_path)
            save_id = save_database.create_save(
                "KT 위즈", "KT 위즈", current_date="2025-11-14",
            )
            with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
                summary = LeagueSimulationService(
                    save_database, save_id, players_path, "KT 위즈",
                ).simulate_day(date(2025, 11, 15))
            self.assertGreaterEqual(summary["schedule_player_effect_count"], 2)
            with closing(sqlite3.connect(players_path)) as players:
                player_id = players.execute(
                    "SELECT id FROM players WHERE name='안현민' LIMIT 1"
                ).fetchone()[0]
            with closing(sqlite3.connect(saves_path)) as connection:
                state = connection.execute(
                    """
                    SELECT fatigue,match_sharpness,morale
                    FROM player_simulation_states
                    WHERE save_id=? AND player_id=?
                    """,
                    (save_id, player_id),
                ).fetchone()
            self.assertGreaterEqual(state[0], 7)
            self.assertGreaterEqual(state[1], 46)
            self.assertGreaterEqual(state[2], 77)

    def test_national_team_callup_and_return_lifecycle(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            saves_path = root / "save.db"
            players_path = root / "players.db"
            shutil.copy2(PLAYERS_DB_PATH, players_path)
            save_database = SaveDatabase(saves_path)
            save_id = save_database.create_save(
                "KIA 타이거즈", "KIA 타이거즈",
                current_date="2025-11-01",
            )
            service = LeagueSimulationService(
                save_database, save_id, players_path, "KIA 타이거즈",
            )
            with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
                service.simulate_day(date(2025, 11, 2))
            with closing(sqlite3.connect(saves_path)) as connection:
                roster_count = connection.execute(
                    "SELECT COUNT(*) FROM national_team_callups WHERE save_id=?",
                    (save_id,),
                ).fetchone()[0]
                statuses = dict(connection.execute(
                    """
                    SELECT status,COUNT(*) FROM national_team_callups
                    WHERE save_id=? GROUP BY status
                    """,
                    (save_id,),
                ))
                kia_group = connection.execute(
                    """
                    SELECT state.squad_group
                    FROM player_simulation_states state
                    JOIN national_team_callups callup
                      ON callup.save_id=state.save_id
                     AND callup.player_id=state.player_id
                    WHERE state.save_id=? AND callup.player_name='성영탁'
                    """,
                    (save_id,),
                ).fetchone()[0]
            self.assertEqual(34, roster_count)
            self.assertEqual(22, statuses["active"])
            self.assertEqual(12, statuses["selected"])
            self.assertEqual("국가대표", kia_group)

            with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
                service.simulate_day(date(2025, 11, 17))
            with closing(sqlite3.connect(saves_path)) as connection:
                returned = connection.execute(
                    """
                    SELECT COUNT(*) FROM national_team_callups
                    WHERE save_id=? AND status='returned'
                    """,
                    (save_id,),
                ).fetchone()[0]
                kia_group = connection.execute(
                    """
                    SELECT state.squad_group
                    FROM player_simulation_states state
                    JOIN national_team_callups callup
                      ON callup.save_id=state.save_id
                     AND callup.player_id=state.player_id
                    WHERE state.save_id=? AND callup.player_name='성영탁'
                    """,
                    (save_id,),
                ).fetchone()[0]
            self.assertEqual(34, returned)
            self.assertNotEqual("국가대표", kia_group)

    @staticmethod
    def _resolve_required(
        save_database, manager_events, players_path, save_id,
    ):
        open_events = [
            event for event in save_database.list_manager_events(save_id, 100)
            if event["status"] == "open" and event["requires_action"]
        ]
        for event in open_events:
            schedule_id = (
                event["payload"].get("schedule_event") or {}
            ).get("event_id")
            resolution_data = None
            if schedule_id in {"roster_audit", "reserve_submit"}:
                with closing(sqlite3.connect(players_path)) as connection:
                    rows = connection.execute(
                        "SELECT id, name FROM players WHERE team='KIA 타이거즈'"
                    ).fetchall()
                resolution_data = {
                    "players": [
                        {
                            "player_id": row[0], "player_name": row[1],
                            "decision": "보류·재계약",
                        }
                        for row in rows
                    ]
                }
            elif schedule_id == "coaching_staff_review":
                training = TrainingService(
                    save_database.db_path, players_path, save_id, "KIA 타이거즈"
                )
                coaches = [
                    coach for coach in training.coaches("hired")
                    if coach["team"] == "KIA 타이거즈"
                ]
                for coach, focus in zip(coaches[:3], ("타격", "투수", "수비")):
                    training.assign_coach(coach["id"], "team", 0, focus)
            elif schedule_id == "offseason_training_plan":
                training = TrainingService(
                    save_database.db_path, players_path, save_id, "KIA 타이거즈"
                )
                training.set_team_setting("균형", 3, "보통")
                training.set_weekly_schedule(training.weekly_schedule())
                for player in training.players()[:3]:
                    focus = next(
                        option for option in player["focus_options"]
                        if option != "자동"
                    )
                    training.set_individual_plan(player["id"], focus, 2)
            elif schedule_id == "second_draft_protect":
                with closing(save_database.connect()) as connection:
                    rows = connection.execute(
                        """
                        SELECT player_id FROM second_draft_pool
                        WHERE save_id=? AND original_team='KIA 타이거즈'
                          AND classification!='automatic_exempt'
                        ORDER BY protection_score DESC LIMIT 35
                        """,
                        (save_id,),
                    ).fetchall()
                resolution_data = {
                    "protected_player_ids": [row[0] for row in rows]
                }
            choice = event["choices"][0]["key"]
            manager_events.resolve(
                save_id, event["id"], choice,
                resolution_data=resolution_data,
            )


if __name__ == "__main__":
    unittest.main()
