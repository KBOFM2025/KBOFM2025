import sqlite3
import unittest
from app.services.player_potential import estimate_potential, populate_potentials, ensure_saved_potential
from database.league_simulation_repository import SIMULATION_SCHEMA


class PotentialTests(unittest.TestCase):
    def setUp(self):
        self.player = dict(id=1, name="테스트", age=20, position_group="IF", pos="SS", contact=10,
                           power=10, speed=12, fielding_range=10, plate_discipline=11, draft_pick=5)

    def test_age_and_position_specific_limits(self):
        young = estimate_potential(self.player)
        old = estimate_potential(dict(self.player, age=36))
        self.assertGreater(young["rating"], old["rating"])
        self.assertEqual(old["caps"]["speed"], 12)
        mature = estimate_potential(dict(self.player, age=28))
        self.assertLessEqual(mature["caps"]["speed"] - 12, mature["caps"]["plate_discipline"] - 11)
        self.assertTrue(all(self.player[k] <= cap <= 20 for k, cap in young["caps"].items()))

    def test_low_samples_mean_uncertainty_not_automatic_star(self):
        low = estimate_potential(self.player)
        high = estimate_potential(dict(self.player, hitter_rating_detail_json='{"PA":500}'))
        self.assertEqual(low["confidence"], "낮음")
        self.assertEqual(high["confidence"], "보통")  # Young-player projection remains uncertain.
        self.assertGreater(low["rating_range"][1] - low["rating_range"][0],
                           high["rating_range"][1] - high["rating_range"][0])

    def test_pitchers_do_not_receive_hitter_caps_or_new_pitches(self):
        profile = estimate_potential(dict(self.player, position_group="P", pitcher_stuff=13,
                                          pitcher_command=8, pitch_slider=12, pitch_curve=0))
        self.assertNotIn("contact", profile["caps"])
        self.assertNotIn("pitch_curve", profile["caps"])
        self.assertIn("pitch_slider", profile["caps"])

    def test_irrelevant_traits_and_repertoire_do_not_change_summary(self):
        p = dict(self.player, leadership=1, aggressiveness=1, bunt=1)
        self.assertEqual(estimate_potential(p)["rating"], estimate_potential(dict(p, leadership=20, aggressiveness=20, bunt=20))["rating"])
        pitcher = dict(position_group="P", age=25, pitcher_stuff=12, pitcher_command=11)
        self.assertEqual(estimate_potential(pitcher)["rating"], estimate_potential(dict(pitcher, pitch_slider=20))["rating"])

    def test_two_season_evidence_and_lower_league_discount(self):
        from unittest.mock import patch
        from app.services.potential_evidence import evidence_for
        totals = dict(PA=10000, AB=9000, H=2400, TB=3500, BB=800, SO=2000)
        row = dict(PA=500, AB=450, H=180, TB=320, BB=60, SO=50, G=100)
        def evaluate(level):
            with patch('app.services.potential_evidence.records', return_value={('123', 'hitting'): [(2024, level, row, totals), (2025, level, row, totals)]}):
                return evidence_for(dict(self.player, kbo_player_id='123'))
        major, minor = evaluate('first_team'), evaluate('futures')
        self.assertEqual(major['seasons'], 2)
        self.assertEqual(major['first_team_sample'], 1000)
        self.assertGreater(major['signals']['power'], minor['signals']['power'])
        self.assertEqual(minor['confidence'], '낮음')

    def test_missing_identifier_does_not_match_a_namesake(self):
        from app.services.potential_evidence import evidence_for
        self.assertEqual(evidence_for(dict(self.player, name='김도영'))['records'], [])

    def test_historical_absence_does_not_mean_no_evidence(self):
        from app.services.potential_evidence import evidence_for
        evidence = evidence_for(dict(kbo_player_id='68341', position_group='P'))
        self.assertTrue({2022, 2023}.issubset({r['season'] for r in evidence['records']}))
        self.assertTrue(all(r['season'] <= 2025 for r in evidence['records']))
        self.assertEqual(len([r for r in evidence['records'] if r['season'] == 2022 and r['level'] in ('first_team', 'historical')]), 1)
        self.assertGreater(evidence['signals']['pitcher_stuff'], 0)

    def test_unverified_identity_is_flagged(self):
        self.assertTrue(estimate_potential(dict(self.player, age=46, draft_pick=None))['review_required'])

    def test_persistence_does_not_reroll_after_trade_or_age(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE players(id INTEGER,age INTEGER,contact INTEGER,team TEXT)")
        connection.execute("INSERT INTO players VALUES (1,20,10,'KIA')")
        self.assertEqual(populate_potentials(connection), 1)
        old = connection.execute("SELECT potential_profile_json FROM players").fetchone()[0]
        connection.execute("UPDATE players SET age=30,team='LG',contact=12")
        self.assertEqual(populate_potentials(connection), 0)
        self.assertEqual(connection.execute("SELECT potential_profile_json FROM players").fetchone()[0], old)

    def test_save_migration_preserves_progress(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        for schema in SIMULATION_SCHEMA:
            connection.execute(schema)
        connection.execute("INSERT INTO player_attribute_development VALUES (1,1,'contact',19,44)")
        ensure_saved_potential(connection, 1, self.player)
        ceiling, progress = connection.execute("SELECT ceiling,progress FROM player_attribute_development WHERE attribute='contact'").fetchone()
        self.assertEqual(ceiling, estimate_potential(self.player)["caps"]["contact"])
        self.assertEqual(progress, 44)
        ensure_saved_potential(connection, 1, dict(self.player, age=39))
        self.assertEqual(connection.execute("SELECT ceiling FROM player_attribute_development WHERE attribute='contact'").fetchone()[0], ceiling)


if __name__ == "__main__":
    unittest.main()
