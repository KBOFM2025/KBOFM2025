import sqlite3
import unittest
from datetime import date, timedelta
from app.services.player_development import age_on, growth_multiplier, apply_daily_development
from database.league_simulation_repository import SIMULATION_SCHEMA


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        for schema in SIMULATION_SCHEMA:
            self.connection.execute(schema)
        self.connection.execute("ATTACH DATABASE ':memory:' AS playerdb")
        self.connection.execute("CREATE TABLE playerdb.players (id INTEGER,contact INTEGER,power INTEGER,speed INTEGER)")
        self.connection.execute("INSERT INTO playerdb.players VALUES (1,10,10,10)")
        self.player = dict(id=1, age=20, position_group="IF", contact=10, power=10, speed=10)
        self.state = dict(condition=90, fatigue=0, morale=85, match_sharpness=70, injury_days=0)

    def tearDown(self):
        self.connection.close()

    def test_age_and_environment_change_growth_rate(self):
        day = date(2025, 11, 1)
        young = growth_multiplier(self.player, self.state, day, "contact")
        self.assertGreater(young, growth_multiplier(dict(self.player, age=36), self.state, day, "contact"))
        self.assertGreater(young, growth_multiplier(self.player, dict(self.state, fatigue=80, morale=40), day, "contact"))
        self.assertEqual(age_on(dict(birth_date="2000-11-02"), day), 24)

    def test_injured_and_national_players_do_not_grow(self):
        for state in (dict(self.state, injury_days=5), dict(self.state, squad_group="국가대표")):
            self.assertEqual(growth_multiplier(self.player, state, date(2025, 11, 1), "contact"), 0)

    def test_daily_idempotence_and_attribute_specific_progress(self):
        for _ in range(2):
            apply_daily_development(self.connection, 1, self.player, self.state, "2025-11-01",
                                    dict(attribute="contact", training_gain=20))
        records = self.connection.execute("SELECT * FROM player_attribute_development").fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["attribute"], "contact")
        self.assertLess(records[0]["progress"], 30)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM development_processed_days").fetchone()[0], 1)

    def test_ceiling_and_no_unrelated_skill_growth(self):
        self.connection.execute("INSERT INTO player_attribute_development VALUES (1,1,'contact',11,0)")
        for index in range(60):
            self.player["contact"] = self.connection.execute("SELECT contact FROM playerdb.players").fetchone()[0]
            apply_daily_development(self.connection, 1, self.player, self.state, date(2025, 11, 1) + timedelta(days=index),
                                    dict(attribute="contact", training_gain=20))
        row = self.connection.execute("SELECT * FROM playerdb.players").fetchone()
        self.assertEqual((row["contact"], row["power"], row["speed"]), (11, 10, 10))

    def test_invalid_attribute_does_not_mutate_database(self):
        apply_daily_development(self.connection, 1, self.player, self.state, "2025-11-01",
                                dict(attribute="contact=20; DROP TABLE players", training_gain=500))
        self.assertEqual(self.connection.execute("SELECT contact FROM playerdb.players").fetchone()[0], 10)


if __name__ == "__main__":
    unittest.main()
