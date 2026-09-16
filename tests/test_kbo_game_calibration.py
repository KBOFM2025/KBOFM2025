import unittest

from app.services.kbo_game_calibration import (
    build_game_environment,
    load_game_calibration,
    matchup_adjustments,
    pitcher_day_form,
)


class KboGameCalibrationTests(unittest.TestCase):
    def test_official_2024_and_2025_profiles_are_complete(self):
        calibration = load_game_calibration()
        self.assertEqual(720, calibration["seasons"]["2024"]["league"]["games"])
        self.assertEqual(720, calibration["seasons"]["2025"]["league"]["games"])
        self.assertEqual(10, len(calibration["seasons"]["2024"]["teams"]))
        self.assertEqual(10, len(calibration["seasons"]["2025"]["teams"]))

    def test_historical_results_keep_favorites_probabilistic(self):
        combined = load_game_calibration()["combined"]
        self.assertGreater(combined["favorite_loss_rate"], 0.35)
        self.assertGreater(combined["strong_favorite_loss_rate"], 0.20)
        self.assertGreater(combined["one_run_game_rate"], 0.18)
        self.assertGreater(combined["runs_stddev"], 3.0)

    def test_game_environment_is_reproducible_but_varies_by_game(self):
        teams = ("KIA 타이거즈", "LG 트윈스")
        first = build_game_environment(1, 10, teams, "KIA 타이거즈")
        repeated = build_game_environment(1, 10, teams, "KIA 타이거즈")
        other = build_game_environment(1, 11, teams, "KIA 타이거즈")
        self.assertEqual(first, repeated)
        self.assertNotEqual(
            first["teams"]["KIA 타이거즈"]["offense_form"],
            other["teams"]["KIA 타이거즈"]["offense_form"],
        )

    def test_pitcher_rating_is_modified_by_independent_day_form(self):
        teams = ("KIA 타이거즈", "LG 트윈스")
        environments = [
            build_game_environment(7, game_id, teams, "KIA 타이거즈")
            for game_id in range(1, 30)
        ]
        forms = [
            pitcher_day_form(env, 7, game_id, "LG 트윈스", 99)
            for game_id, env in enumerate(environments, 1)
        ]
        self.assertLess(min(forms), -0.5)
        self.assertGreater(max(forms), 0.5)
        adjustment = matchup_adjustments(
            environments[0], "KIA 타이거즈", "LG 트윈스", forms[0]
        )
        self.assertIn("offense", adjustment)
        self.assertIn("pitching", adjustment)


if __name__ == "__main__":
    unittest.main()
