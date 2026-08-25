import unittest

from app.services.manager_events import ManagerEventService
from app.services.negotiation_rules import player_meeting_rule_delta


class NegotiationRuleTests(unittest.TestCase):
    def test_player_meeting_rewards_concrete_fair_opportunity(self):
        positive = player_meeting_rule_delta(
            "공정한 기준을 공개하고 수비와 체력 목표를 달성하면 출전 기회를 주겠다."
        )
        harsh = player_meeting_rule_delta(
            "기용은 감독의 권한이다. 싫으면 다른 선택을 검토해라."
        )
        self.assertGreater(positive, 0)
        self.assertLess(harsh, 0)
        self.assertGreater(positive, harsh)

    def test_trade_value_rewards_age_contract_and_salary_efficiency(self):
        young = {
            "position_group": "IF", "age": 24, "salary": 5000,
            "contract_years": 4, "contact": 14, "power": 13,
            "plate_discipline": 13, "bat_control": 14, "timing": 13,
        }
        veteran = {
            **young, "age": 36, "salary": 70000, "contract_years": 1,
        }
        young_value = ManagerEventService._trade_asset_value(young)
        veteran_value = ManagerEventService._trade_asset_value(veteran)
        self.assertGreater(young_value, veteran_value)

    def test_trade_value_reflects_destination_position_need(self):
        player = {
            "position_group": "C", "age": 28, "salary": 10000,
            "contract_years": 2, "contact": 12, "power": 10,
            "plate_discipline": 12, "bat_control": 12, "timing": 11,
        }
        neutral = ManagerEventService._trade_asset_value(player)
        needed = ManagerEventService._trade_asset_value(player, {"C"})
        self.assertEqual(7, round(needed - neutral))


if __name__ == "__main__":
    unittest.main()
