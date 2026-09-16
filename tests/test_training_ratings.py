import sqlite3
import unittest
from app.services.training_ratings import evaluate_training, record_training_rating, recent_ratings
from database.league_simulation_repository import SIMULATION_SCHEMA


class TrainingRatingTests(unittest.TestCase):
    def setUp(self):
        self.player = dict(id=1, team='KIA', age=20, contact=10)
        self.state = dict(condition=85, fatigue=10, morale=75)
        self.training = dict(training_gain=3, focus='컨택', sessions=3, focus_aligned=True)
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        for schema in SIMULATION_SCHEMA:
            self.connection.execute(schema)

    def evaluate(self, **state):
        return evaluate_training(1, self.player, dict(self.state, **state), '2025-11-03', self.training)

    def test_state_affects_performance_not_ability_or_age(self):
        score = self.evaluate()['rating']
        self.assertLess(self.evaluate(condition=50, fatigue=90, morale=40)['rating'], score)
        changed = dict(self.player, contact=20, age=38)
        self.assertEqual(evaluate_training(1, changed, self.state, '2025-11-03', self.training)['rating'], score)

    def test_absences_are_unrated(self):
        self.assertIsNone(self.evaluate(injury_days=3)['rating'])
        self.assertIsNone(self.evaluate(squad_group='국가대표')['rating'])
        rest = dict(self.training, training_gain=0, rest_day=True)
        self.assertIsNone(evaluate_training(1, self.player, self.state, '2025-11-03', rest)['rating'])

    def test_zero_growth_does_not_mean_bad_training(self):
        active = dict(self.training, training_gain=0)
        self.assertIsNotNone(evaluate_training(1, self.player, self.state, '2025-11-03', active)['rating'])

    def test_deterministic_bounded_individual_scores(self):
        scores = [evaluate_training(1, dict(self.player, id=i), self.state, '2025-11-03', self.training)['rating'] for i in range(100)]
        self.assertTrue(all(1 <= s <= 10 for s in scores))
        self.assertGreater(len(set(scores)), 10)
        self.assertEqual(self.evaluate(), self.evaluate())

    def test_idempotency_save_isolation_and_average_excludes_rest(self):
        for day, training in [('2025-11-03', self.training), ('2025-11-04', dict(self.training, rest_day=True)),
                              ('2025-11-10', self.training), ('2025-11-20', self.training)]:
            record_training_rating(self.connection, 1, self.player, self.state, day, training)
            record_training_rating(self.connection, 1, self.player, self.state, day, training)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM player_training_ratings').fetchone()[0], 4)
        result = recent_ratings(self.connection, 1, 'KIA', '2025-11-10')[1]
        self.assertEqual(result['days'], 1)
        self.assertIsNotNone(result['trend'])
        self.assertEqual(len(result['history']), 3)
        self.assertEqual(recent_ratings(self.connection, 2, 'KIA', '2025-11-10'), {})
        self.assertEqual(recent_ratings(self.connection, 1, 'LG', '2025-11-10'), {})
