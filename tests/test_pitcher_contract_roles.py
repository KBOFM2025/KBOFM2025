import unittest
from app.services.foreign_players import ForeignPlayerService, STARTER_ROLES, BULLPEN_ROLES, STARTER_USAGE, BULLPEN_USAGE
from app.services.domestic_fa import DomesticFAService


class PitcherRoleTests(unittest.TestCase):
    def test_closer_can_request_starter_without_changing_default_demand(self):
        roles, usages = ForeignPlayerService._role_plan(dict(position_group='P', role='마무리'))
        self.assertEqual(roles[0], '마무리')
        self.assertTrue(set(STARTER_ROLES + BULLPEN_ROLES).issubset(roles))
        self.assertTrue(set(STARTER_USAGE + BULLPEN_USAGE).issubset(usages))

    def test_rp_and_sp_allow_both_directions(self):
        for position in ('RP', 'SP'):
            roles, _ = ForeignPlayerService._role_plan(dict(primary_position=position))
            self.assertIn('1선발', roles)
            self.assertIn('마무리', roles)

    def test_hitter_does_not_receive_pitcher_roles(self):
        roles, _ = ForeignPlayerService._role_plan(dict(position_group='IF', pos='SS'))
        self.assertNotIn('1선발', roles)
        self.assertNotIn('마무리', roles)

    def test_domestic_closer_can_promise_starting(self):
        usages = DomesticFAService._usage_options(dict(position_group='P', role='마무리'))
        self.assertIn('선발 로테이션 고정', usages)

    def test_conflicting_role_usage_is_rejected(self):
        service = ForeignPlayerService.__new__(ForeignPlayerService)
        service._contract_sessions = {'1': dict(status='ready', max_total=2000000, interest=80,
            usage_by_role={r: STARTER_USAGE if r in STARTER_ROLES else BULLPEN_USAGE for r in STARTER_ROLES+BULLPEN_ROLES})}
        result = service.submit_contract_offer(1, dict(salary=1000000,role='1선발',usage='마무리 우선 기용'))
        self.assertEqual(result['status'], 'countered')
        self.assertIn('맞지 않습니다', result['message'])

    def test_contract_controls_switch_usage_with_role(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from app.views.contract_negotiation import AgentContractNegotiationWidget
        app = QApplication.instance() or QApplication([])
        widget = AgentContractNegotiationWidget()
        widget.session = dict(role_options=BULLPEN_ROLES + STARTER_ROLES,
            usage_options=BULLPEN_USAGE + STARTER_USAGE,
            usage_by_role={r: STARTER_USAGE if r in STARTER_ROLES else BULLPEN_USAGE for r in STARTER_ROLES+BULLPEN_ROLES})
        widget._configure_fields()
        widget.role.setCurrentText('1선발')
        self.assertEqual(tuple(widget.usage.itemText(i) for i in range(widget.usage.count())), STARTER_USAGE)
        widget.role.setCurrentText('마무리')
        self.assertEqual(tuple(widget.usage.itemText(i) for i in range(widget.usage.count())), BULLPEN_USAGE)
        widget.close()
