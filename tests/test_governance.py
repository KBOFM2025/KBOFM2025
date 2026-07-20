import tempfile
import unittest
from pathlib import Path

from app.ai.context_builder import governance_profile_for, load_governance_profiles
from app.ai.decision_validator import (
    InvalidDecision,
    validate_board_review,
    validate_club_vision_decision,
)
from app.ai.governance_ai import GovernanceAI
from app.services.governance_engine import GovernanceEngine
from database.save_database import SaveDatabase


class FakeCard:
    objective_key = "season_result"
    title = "이번 시즌 성과"
    description = "한국시리즈 진출"
    base_priority = "필수"


class GovernanceEngineTests(unittest.TestCase):
    def test_ai_board_review_covers_all_five_items(self):
        keys = ["a", "b", "c", "d", "e"]
        payload = {
            "reviews": [
                {"objective_key": key, "status": "ok", "feedback": f"{key} 승인 근거"}
                for key in keys
            ]
        }
        result = validate_board_review(payload, keys)
        self.assertEqual(keys, [item["objective_key"] for item in result["reviews"]])

    def test_ai_board_review_rejects_missing_item(self):
        keys = ["a", "b", "c", "d", "e"]
        payload = {
            "reviews": [
                {"objective_key": key, "status": "adjust", "feedback": "단계 조정 필요"}
                for key in keys[:-1]
            ]
        }
        with self.assertRaises(InvalidDecision):
            validate_board_review(payload, keys)

    def test_all_ten_profiles_are_available(self):
        profiles = load_governance_profiles()
        self.assertEqual(10, len(profiles))
        self.assertIn("한화 이글스", profiles)
        self.assertIn("키움 히어로즈", profiles)

    def test_club_traits_change_relaxation_score(self):
        hanwha = GovernanceEngine(governance_profile_for("한화 이글스"))
        nc = GovernanceEngine(governance_profile_for("NC 다이노스"))
        hanwha_score = hanwha.evaluate_vision_request(FakeCard(), 1).approval_score
        nc_score = nc.evaluate_vision_request(FakeCard(), 1).approval_score
        self.assertLess(hanwha_score, nc_score)

    def test_fallback_stays_inside_allowed_decisions(self):
        engine = GovernanceEngine(governance_profile_for("한화 이글스"))
        evaluation = engine.evaluate_vision_request(FakeCard(), 1)
        result = engine.fallback_decision(evaluation)
        self.assertIn(result["decision"], evaluation.allowed_decisions)
        resolved = engine.resolve_vision_decision(evaluation, result)
        self.assertGreaterEqual(resolved["final_level"], 1)
        self.assertLessEqual(resolved["final_level"], 5)

    def test_validator_rejects_decision_outside_rule_engine(self):
        payload = {
            "decision": "accept",
            "conditions": [],
            "gm_reply": "단장 의견",
            "board_reply": "이사회 의견",
            "tone": "중립",
        }
        with self.assertRaises(InvalidDecision):
            validate_club_vision_decision(payload, ["reject"])

    def test_governance_ai_accepts_valid_structured_reply(self):
        class FakeClient:
            def generate_json(self, _prompt, _context, _schema):
                return {
                    "decision": "counter_offer",
                    "conditions": ["허용되지 않아 제거될 조건"],
                    "gm_reply": "단장은 한 단계 조정된 목표를 제안했습니다.",
                    "board_reply": "이사회는 단장의 역제안을 승인했습니다.",
                    "tone": "신중함",
                }

        context = {"request": {"allowed_decisions": ["counter_offer", "reject"]}}
        result = GovernanceAI(FakeClient()).decide_club_vision(context)
        self.assertEqual("counter_offer", result["decision"])
        self.assertEqual([], result["conditions"])
        self.assertEqual("local_ai", result["source"])


class GovernanceSaveTests(unittest.TestCase):
    def test_all_clubs_have_five_gm_objective_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            database = SaveDatabase(Path(directory) / "save.db")
            for club_name in load_governance_profiles():
                defaults = database.get_gm_objective_defaults(club_name)
                self.assertEqual(5, len(defaults), club_name)
                self.assertTrue(
                    all(1 <= item["initial_level"] <= 5 for item in defaults.values())
                )

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            database = SaveDatabase(Path(directory) / "save.db")
            save_id = database.create_save("테스트 구단", "NC 다이노스")
            state = {
                "board_confidence": 71,
                "gm_relationship": 66,
                "reviewed": True,
                "objectives": {"season_result": {"selected_level": 2}},
                "negotiation_history": [],
            }
            database.save_governance_state(save_id, state)
            self.assertEqual(state, database.load_governance_state(save_id))


if __name__ == "__main__":
    unittest.main()
