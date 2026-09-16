import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.services.practice_games import (
    PracticeGameError,
    PracticeGameService,
    _pitcher_usage_profiles,
    _pitcher_workload_limit,
)
from database.paths import PLAYERS_DB_PATH
from database.save_database import SaveDatabase


class PracticeGameServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.database = SaveDatabase(root / "saves.db")
        self.save_id = self.database.create_save(
            "테스트 구단", "KIA 타이거즈", current_date="2025-11-01",
            is_debug=True,
        )
        self.service = PracticeGameService(
            root / "saves.db", PLAYERS_DB_PATH,
            self.save_id, "KIA 타이거즈",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_schedule_is_persisted_and_exposed_to_calendar(self):
        game_id = self.service.schedule_game(
            date(2026, 2, 24),
            "LG 트윈스",
            venue_type="away",
            start_time="13:30",
            innings=7,
            purpose="유망주 평가",
            lineup_policy="유망주 중심",
            pitching_plan="투수 전원 점검",
            current_date=date(2025, 11, 1),
        )

        games = self.service.games_on(date(2026, 2, 24))
        self.assertEqual(1, len(games))
        self.assertEqual(game_id, games[0]["id"])
        self.assertEqual("서울종합운동장 야구장", games[0]["stadium"])
        self.assertEqual(7, games[0]["innings"])

        events = self.service.calendar_events(date(2026, 2, 24))
        self.assertEqual("practice_game", events[0]["event_type"])
        self.assertIn("LG 트윈스", events[0]["title"])
        self.assertIn("유망주 평가", events[0]["task"])

    def test_invalid_opponent_window_and_duplicate_are_rejected(self):
        with self.assertRaises(PracticeGameError):
            self.service.schedule_game(date(2026, 2, 23), "LG 트윈스")
        with self.assertRaises(PracticeGameError):
            self.service.schedule_game(date(2026, 2, 24), "KIA 타이거즈")

        self.service.schedule_game(date(2026, 2, 24), "LG 트윈스")
        with self.assertRaisesRegex(PracticeGameError, "이미"):
            self.service.schedule_game(date(2026, 2, 24), "두산 베어스")

    def test_cancelled_games_are_hidden_from_calendar(self):
        game_id = self.service.schedule_game(date(2026, 2, 25), "두산 베어스")
        self.service.cancel_game(game_id, current_date=date(2026, 2, 24))

        self.assertEqual([], self.service.games_on(date(2026, 2, 25)))
        cancelled = self.service.games_on(
            date(2026, 2, 25), include_cancelled=True
        )
        self.assertEqual("cancelled", cancelled[0]["status"])

    def test_result_does_not_change_regular_season_record(self):
        game_id = self.service.schedule_game(date(2026, 2, 26), "한화 이글스")
        self.service.record_result(
            game_id, 5, 3, {"note": "연습경기 엔진 연결용 결과"}
        )

        game = self.service.games_on(date(2026, 2, 26))[0]
        self.assertEqual("completed", game["status"])
        self.assertEqual((5, 3), (game["managed_score"], game["opponent_score"]))
        save = self.database.get_save(self.save_id)
        assert save is not None
        self.assertEqual((0, 0, 0), (save["wins"], save["losses"], save["draws"]))

    def test_debug_game_slot_can_be_reset_and_replayed_without_date_limit(self):
        game_id = self.service.schedule_game(
            date(2026, 2, 24), "LG 트윈스", innings=7
        )
        hitters, starter = self.service.suggest_lineup("mixed")
        assert starter is not None
        self.service.save_lineup(
            game_id,
            [player["id"] for player in hitters],
            starter["id"],
            [player["defensive_position"] for player in hitters],
        )
        self.service.record_result(game_id, 4, 2, {"run": 1})

        replay_id = self.service.reset_debug_game(
            game_id, opponent_team="SSG 랜더스"
        )

        self.assertEqual(game_id, replay_id)
        reset = self.service.game_details(game_id)
        self.assertEqual("scheduled", reset["status"])
        self.assertEqual("SSG 랜더스", reset["opponent_team"])
        self.assertIsNone(reset["managed_score"])
        self.assertEqual("{}", reset["result_json"])
        self.assertEqual([], self.service.prepared_lineup(game_id))
        self.assertIsNone(self.service.load_live_state(game_id))

    def test_deleting_save_removes_practice_game_schedule(self):
        self.service.schedule_game(date(2026, 2, 27), "삼성 라이온즈")

        self.assertTrue(self.database.delete_save(self.save_id))
        self.assertEqual([], self.service.list_games(include_cancelled=True))

    def test_regular_save_cannot_open_practice_game_service(self):
        regular_id = self.database.create_save(
            "일반 구단", "LG 트윈스", current_date="2025-11-01"
        )
        with self.assertRaisesRegex(PracticeGameError, "DEBUG"):
            PracticeGameService(
                self.database.db_path,
                Path(self.temporary.name) / "regular_players.db",
                regular_id,
                "LG 트윈스",
            )

    def test_lineup_game_flow_saves_plays_result_and_player_effects(self):
        game_id = self.service.schedule_game(
            date(2026, 2, 28), "LG 트윈스", innings=7
        )
        hitters, starter = self.service.suggest_lineup("mixed")
        self.assertEqual(9, len(hitters))
        self.assertIsNotNone(starter)
        assert starter is not None
        lineup = self.service.save_lineup(
            game_id,
            [player["id"] for player in hitters],
            starter["id"],
            [player["defensive_position"] for player in hitters],
        )
        self.assertEqual(20, len(lineup))

        match = self.service.simulate_game(game_id)
        self.assertEqual("completed", match["game"]["status"])
        self.assertGreater(len(match["plays"]), 40)
        self.assertGreaterEqual(len(match["stats"]), 20)
        self.assertIn("line_score", match["result"])
        self.assertEqual(
            "KBO_2024_2025_GAME_DISTRIBUTION_V1",
            match["result"]["simulation_model"],
        )
        self.assertIn("favorite_loss_rate", match["result"]["historical_calibration"])

        with self.database.connect() as connection:
            state = connection.execute(
                """
                SELECT match_sharpness,fatigue
                FROM player_simulation_states
                WHERE save_id=? AND player_id=?
                """,
                (self.save_id, hitters[0]["id"]),
            ).fetchone()
        self.assertEqual(60, state["match_sharpness"])
        self.assertGreater(state["fatigue"], 0)

        replay = self.service.simulate_game(game_id)
        self.assertEqual(match["result"], replay["result"])

    def test_live_game_advances_one_pitch_at_a_time_until_final_out(self):
        game_id = self.service.schedule_game(
            date(2026, 2, 24), "LG 트윈스", innings=7
        )
        hitters, starter = self.service.suggest_lineup("mixed")
        assert starter is not None
        self.service.save_lineup(
            game_id,
            [player["id"] for player in hitters],
            starter["id"],
            [player["defensive_position"] for player in hitters],
        )

        state = self.service.start_live_game(game_id)
        self.assertEqual("live", state["status"])
        self.assertEqual([], state["plays"])
        self.assertEqual(
            "KBO_2024_2025_GAME_DISTRIBUTION_V1",
            state["game_environment"]["model"],
        )
        self.assertEqual("live", self.service.game_details(game_id)["status"])

        reliever = next(
            player for player in self.service.available_players()
            if player["position_group"] == "P"
            and player["id"] != starter["id"]
            and not player["injury_days"]
        )
        changed = self.service.change_pitcher(game_id, reliever["id"])
        self.assertEqual(reliever["id"], changed["pitcher_id"])

        first = self.service.advance_live_pitch(
            game_id, "적극 타격", "공격적 승부"
        )
        self.assertEqual(2, len(first["state"]["plays"]))
        self.assertEqual("live", first["state"]["status"])
        self.assertTrue(first["state"]["last_pitch_type"])
        self.assertGreaterEqual(first["state"]["last_pitch_speed"], 105)
        self.assertEqual(
            first["state"]["last_pitch_speed"],
            first["event"]["pitch_speed"],
        )
        resumed_service = PracticeGameService(
            self.database.db_path, PLAYERS_DB_PATH,
            self.save_id, "KIA 타이거즈",
        )
        resumed = resumed_service.load_live_state(game_id)
        assert resumed is not None
        self.assertEqual(first["state"]["pitch_no"], resumed["pitch_no"])

        state = first["state"]
        for _ in range(1500):
            if state["status"] == "completed":
                break
            state = self.service.advance_live_pitch(game_id)["state"]
        self.assertEqual("completed", state["status"])
        result = self.service.load_game_result(game_id)
        self.assertEqual("completed", result["game"]["status"])
        self.assertGreater(len(result["plays"]), 100)

    def test_regular_starter_workload_uses_2025_usage(self):
        anderson = next(
            player for player in self.service.available_players("SSG 랜더스")
            if str(player.get("kbo_player_id") or "") == "54833"
        )
        profile = _pitcher_usage_profiles()["54833"]
        limit = _pitcher_workload_limit(
            anderson, "정규 선발 운용", is_starter=True
        )

        self.assertGreater(profile["average_outs"], 16)
        self.assertGreaterEqual(limit["outs"], 16)
        self.assertLessEqual(limit["outs"], 19)
        self.assertGreaterEqual(limit["pitches"], 80)
        self.assertLessEqual(limit["pitches"], 100)


if __name__ == "__main__":
    unittest.main()
