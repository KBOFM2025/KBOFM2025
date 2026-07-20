"""구단 성향을 수치화해 AI가 선택할 수 있는 협상 범위를 계산한다."""

from dataclasses import dataclass

from app.services.negotiation_rules import (
    LEVELS,
    final_level_for_decision,
    trust_delta_for_level,
)


@dataclass(frozen=True)
class VisionEvaluation:
    objective_key: str
    objective_title: str
    objective_description: str
    priority: str
    requested_level: int
    approval_score: int
    allowed_decisions: tuple
    board_delta_range: tuple
    gm_delta_range: tuple

    def as_dict(self):
        return {
            "objective_key": self.objective_key,
            "objective_title": self.objective_title,
            "objective_description": self.objective_description,
            "priority": self.priority,
            "requested_level": self.requested_level,
            "requested_label": LEVELS[self.requested_level]["label"],
            "base_approval_score": self.approval_score,
            "allowed_decisions": list(self.allowed_decisions),
            "board_trust_delta_range": list(self.board_delta_range),
            "gm_relationship_delta_range": list(self.gm_delta_range),
        }


class GovernanceEngine:
    """수학과 하드 제한을 담당하며 생성 모델의 자유도를 제한한다."""

    def __init__(self, profile):
        self.profile = profile
        self.gm = profile["general_manager"]["traits"]
        self.owner = profile["ownership"]["traits"]

    def evaluate_vision_request(self, card, requested_level):
        requested_level = int(requested_level)
        approval_score = self._vision_approval_score(card, requested_level)
        allowed = self._allowed_decisions(requested_level, approval_score)
        deltas = [
            self._relationship_deltas(requested_level, decision, card.base_priority)
            for decision in allowed
        ]
        board_deltas = [item[0] for item in deltas]
        gm_deltas = [item[1] for item in deltas]
        return VisionEvaluation(
            objective_key=card.objective_key,
            objective_title=card.title,
            objective_description=card.description,
            priority=card.base_priority,
            requested_level=requested_level,
            approval_score=approval_score,
            allowed_decisions=tuple(allowed),
            board_delta_range=(min(board_deltas), max(board_deltas)),
            gm_delta_range=(min(gm_deltas), max(gm_deltas)),
        )

    def resolve_vision_decision(self, evaluation, decision_payload):
        decision = decision_payload["decision"]
        if decision not in evaluation.allowed_decisions:
            decision = self.fallback_decision(evaluation)["decision"]
        final_level = final_level_for_decision(evaluation.requested_level, decision)
        board_delta, gm_delta = self._relationship_deltas(
            evaluation.requested_level,
            decision,
            evaluation.priority,
        )
        return {
            **decision_payload,
            "decision": decision,
            "requested_level": evaluation.requested_level,
            "final_level": final_level,
            "level_label": LEVELS[final_level]["label"],
            "board_trust_delta": board_delta,
            "gm_relationship_delta": gm_delta,
        }

    def fallback_decision(self, evaluation):
        score = evaluation.approval_score
        if "accept" in evaluation.allowed_decisions and score >= 72:
            decision = "accept"
        elif "conditional_accept" in evaluation.allowed_decisions and score >= 52:
            decision = "conditional_accept"
        elif score < 30 and "reject" in evaluation.allowed_decisions:
            decision = "reject"
        elif "counter_offer" in evaluation.allowed_decisions:
            decision = "counter_offer"
        else:
            decision = "reject"

        gm_name = self.profile["general_manager"]["name"]
        requested_label = LEVELS[evaluation.requested_level]["label"]
        messages = {
            "accept": (
                f"{gm_name} 단장은 감독의 {requested_label} 제안이 구단 운영 방향과 양립할 수 있다고 판단했습니다.",
                "이사회는 제안의 취지와 감독의 책임 의지를 확인하고 요청을 승인했습니다.",
            ),
            "conditional_accept": (
                f"{gm_name} 단장은 제안을 받아들이되 시즌 중간에 진행 상황을 다시 확인하자는 의견을 냈습니다.",
                "이사회는 정기 평가에서 성과와 선수단 발전을 함께 점검하는 조건으로 요청을 수용했습니다.",
            ),
            "counter_offer": (
                f"{gm_name} 단장은 감독의 사정을 이해하지만 요청한 폭을 그대로 수용하기는 어렵다고 판단했습니다.",
                "이사회는 기존 목표와 감독의 제안 사이에서 한 단계 조정된 목표를 역제안했습니다.",
            ),
            "reject": (
                f"{gm_name} 단장은 현재 구단 기대치와 전력 구성을 고려할 때 제안을 지지하기 어렵다는 의견을 냈습니다.",
                "이사회는 취임 시점에 제시한 원래 목표를 유지하기로 결정했습니다.",
            ),
        }
        gm_reply, board_reply = messages[decision]
        conditions = (
            ["시즌 중간 평가에서 목표 진행 상황을 재검토합니다."]
            if decision == "conditional_accept"
            else []
        )
        return {
            "decision": decision,
            "conditions": conditions,
            "gm_reply": gm_reply,
            "board_reply": board_reply,
            "tone": "신중함",
            "source": "rules_fallback",
        }

    def _vision_approval_score(self, card, requested_level):
        if requested_level == 3:
            return 100

        objective_key = card.objective_key
        if objective_key == "season_result":
            resistance = (self.owner["performance_pressure"] + self.gm["winning_pressure"]) / 2
            flexibility = (self.owner["manager_autonomy"] + self.gm["manager_autonomy"]) / 2
        elif objective_key == "long_term_vision":
            resistance = (self.owner["long_term_development"] + self.gm["development"]) / 2
            flexibility = (self.owner["manager_autonomy"] + self.gm["manager_autonomy"]) / 2
        elif objective_key == "front_office_style":
            resistance = (self.gm["negotiation"] + self.gm["data"]) / 2
            flexibility = self.gm["manager_autonomy"]
        elif objective_key == "club_identity":
            resistance = (self.owner["brand_value"] + self.owner["performance_pressure"]) / 2
            flexibility = self.owner["manager_autonomy"]
        else:
            resistance = (self.gm["development"] + self.owner["long_term_development"]) / 2
            flexibility = (self.gm["manager_autonomy"] + self.owner["manager_autonomy"]) / 2

        distance = abs(requested_level - 3)
        if requested_level < 3:
            raw = 78 - distance * 21 + (flexibility - resistance) * 1.6
        else:
            ambition = (self.gm["winning_pressure"] + self.owner["performance_pressure"]) / 2
            raw = 80 - (distance - 1) * 7 + (ambition - 10) * 1.2
        return max(0, min(100, round(raw)))

    @staticmethod
    def _allowed_decisions(requested_level, score):
        if requested_level == 3:
            return ("accept",)
        if requested_level > 3:
            return ("accept", "conditional_accept") if score >= 55 else ("conditional_accept", "counter_offer")
        if score >= 70:
            return ("accept", "conditional_accept")
        if score >= 50:
            return ("conditional_accept", "counter_offer")
        if score >= 30:
            return ("counter_offer", "reject")
        return ("reject", "counter_offer")

    def _gm_delta(self, level, priority):
        board_delta = trust_delta_for_level(level, priority)
        negotiation_resistance = max(0, self.gm["negotiation"] - 14)
        if level < 3:
            return board_delta - round(negotiation_resistance / 2)
        if level > 3:
            return board_delta + round((self.gm["winning_pressure"] - 10) / 5)
        return 0

    def _relationship_deltas(self, requested_level, decision, priority):
        final_level = final_level_for_decision(requested_level, decision)
        board_delta = trust_delta_for_level(final_level, priority)
        gm_delta = self._gm_delta(final_level, priority)
        if requested_level < 3 and decision == "reject":
            request_friction = 3 - requested_level
            board_delta -= request_friction
            gm_delta -= request_friction + round(max(0, self.gm["negotiation"] - 14) / 3)
        return board_delta, gm_delta
