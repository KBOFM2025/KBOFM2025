import tempfile
import unittest
import sqlite3
from pathlib import Path

from app.ai.context_builder import governance_profile_for, load_governance_profiles
from app.ai.decision_validator import (
    InvalidDecision,
    validate_board_review,
    validate_club_vision_decision,
)
from app.ai.governance_ai import GovernanceAI
from app.services.governance_engine import GovernanceEngine
from app.services.negotiation_rules import LEVELS
from database.save_database import SaveDatabase


class FakeCard:
    objective_key = "season_result"
    title = "이번 시즌 성과"
    description = "한국시리즈 진출"
    base_priority = "필수"
    gm_proposed_level = None


class ObjectiveFakeCard:
    title = "테스트 목표"
    description = "테스트 설명"
    base_priority = "중요"
    gm_proposed_level = None

    def __init__(self, objective_key):
        self.objective_key = objective_key


class GovernanceEngineTests(unittest.TestCase):
    def test_board_negotiation_uses_five_levels(self):
        self.assertEqual([1, 2, 3, 4, 5], list(LEVELS))
        self.assertEqual(
            ["대폭 완화", "일부 완화", "단장 원안", "도전 목표", "최고 목표"],
            [LEVELS[level]["label"] for level in LEVELS],
        )

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

    def test_all_clubs_expose_detailed_twenty_point_scorecard(self):
        for club_name in load_governance_profiles():
            scorecard = GovernanceEngine(
                governance_profile_for(club_name)
            ).board_scorecard()
            self.assertEqual(10, len(scorecard), club_name)
            self.assertEqual(10, len({item["key"] for item in scorecard}))
            self.assertTrue(
                all(1 <= item["value"] <= 20 for item in scorecard),
                club_name,
            )
            self.assertTrue(all(item["grade"] for item in scorecard))
            self.assertTrue(all(item["description"] for item in scorecard))

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

    def test_hanwha_rejects_season_goal_below_hard_floor(self):
        engine = GovernanceEngine(governance_profile_for("한화 이글스"))
        evaluation = engine.evaluate_vision_request(FakeCard(), 3)
        result = engine.fallback_decision(evaluation)
        self.assertEqual(5, evaluation.hard_floor)
        self.assertEqual("reject", result["decision"])
        self.assertEqual(5, result["target_level"])
        visible_reply = " ".join(
            [result["gm_reply"], result["board_reply"], *result["reasons"]]
        )
        for internal_term in ("절대 하한", "적합도", "점수", "알고리즘"):
            self.assertNotIn(internal_term, visible_reply)
        self.assertIn("다시", result["board_reply"])

    def test_kiwoom_protects_development_even_with_low_season_target(self):
        engine = GovernanceEngine(governance_profile_for("키움 히어로즈"))
        season = engine.evaluate_vision_request(FakeCard(), 2)
        development = engine.evaluate_vision_request(
            ObjectiveFakeCard("long_term_vision"), 2
        )
        self.assertGreater(season.approval_score, development.approval_score)
        self.assertEqual(5, development.hard_floor)

    def test_manager_abilities_change_execution_fit(self):
        profile = governance_profile_for("NC 다이노스")
        low = GovernanceEngine(
            profile,
            manager_data={"development": 2, "fitness": 2, "data_analysis": 2, "leadership": 2},
        )
        high = GovernanceEngine(
            profile,
            manager_data={"development": 20, "fitness": 20, "data_analysis": 20, "leadership": 20},
        )
        card = ObjectiveFakeCard("long_term_vision")
        self.assertLess(
            low.evaluate_vision_request(card, 4).manager_fit_score,
            high.evaluate_vision_request(card, 4).manager_fit_score,
        )

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
    def test_temporary_four_level_objective_is_migrated_to_five_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.db"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """
                    CREATE TABLE gm_objective_defaults (
                        club_name TEXT NOT NULL,
                        gm_name TEXT NOT NULL,
                        objective_key TEXT NOT NULL,
                        initial_level INTEGER NOT NULL
                            CHECK(initial_level BETWEEN 1 AND 4),
                        rationale TEXT NOT NULL,
                        PRIMARY KEY(club_name, objective_key)
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO gm_objective_defaults VALUES (?, ?, ?, ?, ?)",
                    ("한화 이글스", "손혁", "season_result", 4, "구버전"),
                )
            database = SaveDatabase(path)
            self.assertEqual(
                5,
                database.get_gm_objective_defaults("한화 이글스")[
                    "season_result"
                ]["initial_level"],
            )

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
