import json
import unittest
from unittest.mock import patch
from app.services.potential_lifecycle import lifecycle_for
from app.services.player_potential import profile_for


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.player = dict(id=1,kbo_player_id='123',draft_year=2022,age=23,position_group='IF',contact=10)
        self.history = dict(records=[], signals={}, first_team_sample=0, futures_sample=0, seasons=0, confidence='낮음')
        self.coverage = {('123','hitting',y,level) for y in range(2022,2026) for level in ('first_team','futures')}

    def policy(self, day, coverage=None):
        with patch('app.services.potential_lifecycle.career_index', return_value={}), patch('app.services.potential_lifecycle.coverage_index',return_value=self.coverage if coverage is None else coverage):
            return lifecycle_for(self.player, day, self.history)

    def test_fourth_year_then_fifth_year_freeze(self):
        self.assertEqual(self.policy('2025-11-01')['state'], 'developing')
        self.assertEqual(self.policy('2026-01-01')['state'], 'fixed')

    def test_missing_minor_year_blocks_freeze(self):
        coverage = self.coverage - {('123','hitting',2022,'futures')}
        state = self.policy('2026-01-01',coverage)
        self.assertEqual(state['state'],'awaiting_history')
        self.assertEqual(state['missing_records'], ['2022:futures'])

    def test_first_team_debut_is_not_pro_entry(self):
        with patch('app.services.potential_lifecycle.career_index', return_value={'123':{2024,2025}}):
            state = lifecycle_for(dict(self.player,draft_year=None),'2025-11-01',self.history)
        self.assertIsNone(state['career_year'])
        self.assertEqual(state['state'],'entry_unknown')

    def test_conflicting_draft_year_cannot_create_fixed_rookie(self):
        with patch('app.services.potential_lifecycle.career_index',return_value={'123':{2019,2020}}), patch('app.services.potential_lifecycle.coverage_index',return_value=self.coverage):
            state = lifecycle_for(dict(self.player,draft_year=2025),'2025-11-01',self.history)
        self.assertTrue(state['entry_conflict'])
        self.assertNotEqual(state['state'],'fixed')

    def test_fixed_profile_is_immutable(self):
        with patch('app.services.potential_evidence.evidence_for',return_value=self.history), patch('app.services.potential_lifecycle.career_index',return_value={}), patch('app.services.potential_lifecycle.coverage_index',return_value=self.coverage):
            fixed = profile_for(self.player,'2026-01-01')
        self.assertEqual(fixed['lifecycle']['state'],'fixed')
        later = profile_for(dict(self.player,contact=18,potential_profile_json=json.dumps(fixed)),'2030-11-01')
        self.assertEqual(later, fixed)

    def test_new_evidence_changes_young_evaluation_not_daily_training(self):
        with patch('app.services.potential_evidence.evidence_for',return_value=self.history), patch('app.services.potential_lifecycle.career_index',return_value={}):
            first = profile_for(self.player,'2025-11-01')
            saved = dict(self.player,contact=14,potential_profile_json=json.dumps(first))
            second = profile_for(saved,'2025-11-02')
            self.assertEqual(second['caps'],first['caps'])
        history = dict(self.history, records=[dict(season=2025,level='futures',sample=100)],signals={'contact':.8})
        with patch('app.services.potential_evidence.evidence_for',return_value=history), patch('app.services.potential_lifecycle.career_index',return_value={}):
            revised = profile_for(saved,'2025-11-03')
        self.assertNotEqual(revised['caps'],first['caps'])

    def test_no_future_season_aggregates(self):
        from app.services.potential_evidence import evidence_for
        data = {('123','hitting'): [(2025,'first_team',dict(PA=100,AB=90,H=30),dict(PA=100,AB=90,H=30))]}
        with patch('app.services.potential_evidence.records',return_value=data):
            self.assertEqual(evidence_for(self.player,'2025-06-01')['records'],[])

    def test_official_entry_corrects_wrong_draft_with_identity_check(self):
        player = dict(self.player, birth_date='1999-01-01', draft_year=2025)
        pages = {('123', level): dict(professional_entry_year='2019', birth_date='1999-01-01',
                 role='hitting', verified_through='2025') for level in ('first_team','futures')}
        with patch('app.services.potential_lifecycle.verified_careers', return_value=pages), patch('app.services.potential_lifecycle.career_index', return_value={'123':{2019}}):
            result = lifecycle_for(player, '2025-11-01', self.history)
            self.assertEqual(result['entry_year'], 2019)
            self.assertEqual(result['state'], 'fixed')
            self.assertEqual(result['missing_records'], [])
            result = lifecycle_for(dict(player,birth_date='2005-01-01'), '2025-11-01', self.history)
            self.assertNotEqual(result['state'], 'fixed')

    def test_foreign_kbo_join_does_not_establish_global_entry(self):
        result = lifecycle_for(dict(self.player, is_foreign=1, draft_year=2022), '2025-11-01', self.history)
        self.assertIsNone(result['entry_year'])
        self.assertFalse(result['history_complete'])

    def test_valid_fixed_potential_survives_model_update(self):
        with patch('app.services.potential_evidence.evidence_for',return_value=self.history), patch('app.services.potential_lifecycle.coverage_index',return_value=self.coverage):
            fixed = profile_for(self.player,'2026-01-01')
        fixed['version'] = 'previous-scoring-model'
        self.assertEqual(profile_for(dict(self.player,potential_profile_json=json.dumps(fixed)), '2030-11-01'), fixed)

    def test_returned_domestic_player_needs_overseas_records(self):
        from app.services.potential_lifecycle import overseas_history_required
        self.assertTrue(overseas_history_required(dict(career='고교-KIA-텍사스'), {'official_join':'07KIA'}))
        self.assertTrue(overseas_history_required({}, {'official_join':'09애리조나'}))
        self.assertFalse(overseas_history_required(dict(career='고교-KIA-상무'), {'official_join':'07KIA'}))
        self.assertFalse(overseas_history_required(dict(career='고교-상무-SK'), {'official_join':'13상무'}))


if __name__ == '__main__':
    unittest.main()
