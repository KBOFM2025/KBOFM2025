import unittest

from app.views.live_baseball_field import runner_paths


class RunnerAnimationTests(unittest.TestCase):
    def test_home_run_uses_run_records_and_visits_every_base(self):
        before = {"offense_team": "A", "bases": {"1": 10}, "stats": {}}
        after = {"stats": {"A|10": {"runs": 1}, "A|20": {"runs": 1}}}
        event = {"result_code": "HR", "batter_id": 20, "bases_after": {}}
        self.assertEqual(runner_paths(before, after, event), [(10, [1, 2, 3, 4]), (20, [0, 1, 2, 3, 4])])

    def test_third_out_does_not_turn_stranded_runner_into_score(self):
        before = {"offense_team": "A", "bases": {"3": 10}}
        after = {"offense_team": "B", "bases": {}, "stats": {}}
        event = {"result_code": "OUT", "batter_id": 20, "bases_after": {"3": 10}, "description": "외야 뜬공 아웃"}
        self.assertEqual(runner_paths(before, after, event), [])

    def test_caught_stealing_is_a_run_to_second_not_home(self):
        event = {"result_code": "CS", "bases_after": {}}
        self.assertEqual(runner_paths({"bases": {"1": 10}}, {}, event), [(10, [1, 2])])

    def test_walk_only_moves_forced_runners(self):
        before = {"bases": {"1": 10, "3": 30}}
        event = {"result_code": "BB", "batter_id": 20, "bases_after": {"1": 20, "2": 10, "3": 30}}
        self.assertEqual(runner_paths(before, {}, event), [(10, [1, 2]), (20, [0, 1])])
