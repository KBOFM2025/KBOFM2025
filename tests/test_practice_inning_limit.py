import unittest

from app.services.practice_games import PracticeGameService


class PracticeInningLimitTests(unittest.TestCase):
    def test_extra_inning_end_conditions(self):
        for inning, half, outs, home, away, expected in (
            (9, "말", 3, 2, 2, False),
            (10, "말", 3, 2, 2, False),
            (11, "초", 3, 2, 2, False),
            (11, "말", 2, 2, 2, False),
            (11, "말", 3, 2, 2, True),
            (11, "말", 1, 3, 2, True),
            (11, "말", 3, 2, 3, True),
            (9, "초", 3, 3, 2, True),
        ):
            with self.subTest(inning=inning, half=half, outs=outs, home=home, away=away):
                state = {"inning": inning, "half": half, "outs": outs,
                         "home_team": "H", "away_team": "A",
                         "scores": {"H": home, "A": away}}
                self.assertEqual(
                    PracticeGameService._live_game_should_end(state, {"innings": 9}),
                    expected,
                )
