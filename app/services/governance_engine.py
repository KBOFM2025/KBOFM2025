"""구단별 방향, 추진력, 감독 역량을 반영하는 결정론적 이사회 판정 엔진."""

from dataclasses import dataclass

from app.services.negotiation_rules import LEVELS, PRIORITY_WEIGHTS


OBJECTIVE_ABILITY_WEIGHTS = {
    "season_result": {
        "game_management": 0.30,
        "leadership": 0.20,
        "pitching_change": 0.15,
        "pinch_hitting": 0.10,
        "batting": 0.10,
        "pitching": 0.15,
    },
    "long_term_vision": {
        "development": 0.45,
        "fitness": 0.20,
        "data_analysis": 0.20,
        "leadership": 0.15,
    },
    "front_office_style": {
        "data_analysis": 0.40,
        "leadership": 0.30,
        "development": 0.15,
        "game_management": 0.15,
    },
    "club_identity": {
        "leadership": 0.45,
        "game_management": 0.25,
        "development": 0.15,
        "baserunning": 0.15,
    },
    "roster_balance": {
        "development": 0.35,
        "data_analysis": 0.30,
        "fitness": 0.20,
        "leadership": 0.15,
    },
}

OBJECTIVE_SIGNALS = {
    "season_result": ("win_now", "winning_pressure", "performance_pressure"),
    "long_term_vision": ("development", "development", "long_term_development"),
    "front_office_style": ("data", "negotiation", "manager_autonomy"),
    "club_identity": ("winning_pressure", "manager_autonomy", "brand_value"),
    "roster_balance": ("development", "economy", "long_term_development"),
}

OBJECTIVE_REASON_LABELS = {
    "season_result": "현재 경쟁 창과 성적 압박",
    "long_term_vision": "육성 투자와 장기 코어 계획",
    "front_office_style": "프런트의 데이터·협상 원칙",
    "club_identity": "팬 기대와 구단 브랜드 기준",
    "roster_balance": "즉시 전력과 내부 성장의 균형",
}


def _clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, round(value)))


@dataclass(frozen=True)
class VisionEvaluation:
    objective_key: str
    objective_title: str
    objective_description: str
    priority: str
    requested_level: int
    preferred_level: int
    hard_floor: int
    recommended_level: int
    approval_score: int
    direction_score: int
    execution_score: int
    manager_fit_score: int
    allowed_decisions: tuple
    reasons: tuple
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
            "preferred_level": self.preferred_level,
            "hard_floor": self.hard_floor,
            "recommended_level": self.recommended_level,
            "base_approval_score": self.approval_score,
            "direction_score": self.direction_score,
            "execution_score": self.execution_score,
            "manager_fit_score": self.manager_fit_score,
            "allowed_decisions": list(self.allowed_decisions),
            "reasons": list(self.reasons),
            "board_trust_delta_range": list(self.board_delta_range),
            "gm_relationship_delta_range": list(self.gm_delta_range),
        }


class GovernanceEngine:
    """같은 선택도 구단과 감독에 따라 다른 결과가 나오는 즉시 판정 엔진."""

    def __init__(self, profile, manager_data=None):
        self.profile = profile
        self.manager_data = manager_data or {}
        self.gm = profile["general_manager"]["traits"]
        self.owner = profile["ownership"]["traits"]
        self.policy = profile.get("board_policy", {})

    def board_scorecard(self):
        """내부 20점 판정값과 화면용 정성 등급을 함께 반환한다."""
        autonomy = round(
            (self.gm.get("manager_autonomy", 10) + self.owner.get("manager_autonomy", 10)) / 2
        )
        pressure = round(
            (self.gm.get("winning_pressure", 10) + self.owner.get("performance_pressure", 10)) / 2
        )
        development = round(
            (self.gm.get("development", 10) + self.owner.get("long_term_development", 10)) / 2
        )
        investment = round(
            (
                self.policy.get("investment_aggression", 10)
                + self.owner.get("financial_support", 10)
            )
            / 2
        )
        stability = round(
            (
                self.policy.get("roster_continuity", 10)
                + self.owner.get("stability", 10)
            )
            / 2
        )
        items = (
            ("성과 압박", pressure, "높을수록 시즌 목표 완화가 어렵고 부진 시 이사회 신뢰가 빠르게 하락"),
            (
                "즉시 전력",
                round((self.gm.get("win_now", 10) + self.policy.get("execution_drive", 10)) / 2),
                "높을수록 즉시 전력 보강과 빠른 포스트시즌 성과를 요구",
            ),
            ("장기 육성", development, "높을수록 유망주 출전·성장 목표 완화와 미래 자산 소진에 강하게 반대"),
            ("데이터 운영", self.gm.get("data", 10), "높을수록 분석 보고서·선수 가치·효율 지표를 협의 근거로 요구"),
            ("투자 적극성", investment, "높을수록 FA·외국인·시설 예산이 큰 목표의 실행 가능성을 높임"),
            ("재정 효율", self.gm.get("economy", 10), "높을수록 총액보다 가성비·보상 가치·장기 비용을 엄격하게 평가"),
            ("협상 강도", self.gm.get("negotiation", 10), "높을수록 원안 변경 시 관계 손실과 역제안 폭이 커짐"),
            ("위험 감수", self.policy.get("risk_tolerance", 10), "높을수록 대형 트레이드·세대교체·공격적 목표를 받아들임"),
            ("감독 자율", autonomy, "높을수록 이사회 원안과 다른 라인업·육성·운영 제안의 허용 폭이 넓어짐"),
            ("운영 안정", stability, "높을수록 주축 유지와 장기 계획을 선호하고 급격한 전면 개편을 경계"),
        )
        return [
            {
                "key": title,
                "value": max(1, min(20, int(value))),
                "grade": self._trait_grade(value),
                "description": description,
            }
            for title, value, description in items
        ]

    @staticmethod
    def _trait_grade(value):
        value = int(value)
        if value >= 19:
            return "최상"
        if value >= 16:
            return "높음"
        if value >= 13:
            return "다소 높음"
        if value >= 9:
            return "보통"
        if value >= 6:
            return "낮음"
        return "매우 낮음"

    def evaluate_vision_request(self, card, requested_level):
        requested_level = max(1, min(5, int(requested_level)))
        preferred_level = self._preferred_level(card)
        hard_floor = self._hard_floor(card.objective_key, preferred_level)
        direction_score = self._direction_score(
            card.objective_key, requested_level, preferred_level
        )
        execution_score = self._execution_score(card.objective_key, requested_level)
        manager_fit_score = self._manager_fit_score(card.objective_key)
        autonomy = (
            self.gm.get("manager_autonomy", 10)
            + self.owner.get("manager_autonomy", 10)
        ) / 2
        approval_score = self._approval_score(
            requested_level,
            preferred_level,
            hard_floor,
            direction_score,
            execution_score,
            manager_fit_score,
            card.base_priority,
            autonomy,
        )
        recommended_level = self._recommended_level(
            requested_level,
            preferred_level,
            hard_floor,
            execution_score,
            manager_fit_score,
        )
        allowed = self._allowed_decisions(
            requested_level,
            preferred_level,
            hard_floor,
            approval_score,
        )
        reasons = self._reasons(
            card.objective_key,
            requested_level,
            preferred_level,
            hard_floor,
            direction_score,
            execution_score,
            manager_fit_score,
        )
        deltas = [
            self._relationship_deltas(
                requested_level,
                decision,
                card.base_priority,
                recommended_level,
                preferred_level,
            )
            for decision in allowed
        ]
        return VisionEvaluation(
            objective_key=card.objective_key,
            objective_title=card.title,
            objective_description=card.description,
            priority=card.base_priority,
            requested_level=requested_level,
            preferred_level=preferred_level,
            hard_floor=hard_floor,
            recommended_level=recommended_level,
            approval_score=approval_score,
            direction_score=direction_score,
            execution_score=execution_score,
            manager_fit_score=manager_fit_score,
            allowed_decisions=tuple(allowed),
            reasons=tuple(reasons),
            board_delta_range=(min(item[0] for item in deltas), max(item[0] for item in deltas)),
            gm_delta_range=(min(item[1] for item in deltas), max(item[1] for item in deltas)),
        )

    def fallback_decision(self, evaluation):
        requested = evaluation.requested_level
        if requested < evaluation.hard_floor:
            decision = "reject" if evaluation.hard_floor - requested >= 2 else "counter_offer"
        elif evaluation.approval_score >= 82:
            decision = "accept"
        elif evaluation.approval_score >= 64:
            decision = "conditional_accept"
        elif evaluation.approval_score >= 38:
            decision = "counter_offer"
        else:
            decision = "reject"
        if decision not in evaluation.allowed_decisions:
            decision = evaluation.allowed_decisions[0]

        policy_reason = self.policy.get("rationale", "구단의 중장기 운영 기준을 우선합니다.")
        requested_label = LEVELS[evaluation.requested_level]["label"]
        target_label = LEVELS[evaluation.recommended_level]["label"]
        if decision == "accept":
            gm_reply = (
                f"감독님이 제안하신 {requested_label} 방향이면 구단이 준비해 온 계획과도 잘 맞습니다. "
                "저도 이 안으로 이사회에 보고하겠습니다."
            )
            board_reply = (
                "감독님의 제안을 검토했습니다. 현재 선수단 구성과 구단의 계획을 함께 고려했을 때 "
                "충분히 추진할 수 있는 안이라고 판단해 승인하겠습니다."
            )
            conditions = []
        elif decision == "conditional_accept":
            gm_reply = (
                "제안하신 방향에는 공감합니다. 다만 시즌 상황에 따라 부담이 커질 수 있으니 "
                "중간에 진행 상황을 함께 확인하는 조건으로 전달하겠습니다."
            )
            board_reply = (
                "제안의 취지에는 동의합니다. 우선 이 방향으로 진행하되 시즌 중간에 선수단 운영과 "
                "성과를 다시 살펴본 뒤 필요하면 계획을 조정하겠습니다."
            )
            conditions = ["시즌 중간 회의에서 진행 상황과 선수단 운영 계획을 다시 논의합니다."]
        elif decision == "counter_offer":
            if evaluation.recommended_level > evaluation.requested_level:
                gm_reply = (
                    f"감독님의 {requested_label} 제안은 이해했습니다. 다만 구단은 이 안건에서 조금 더 "
                    f"분명한 책임을 기대하고 있습니다. {target_label} 수준으로 다시 검토해 주시겠습니까?"
                )
                board_reply = (
                    f"현재 제안만으로는 구단이 기대하는 방향을 충분히 담기 어렵습니다. "
                    f"{target_label} 수준까지 목표를 높여 수정안을 보내주시면 다시 검토하겠습니다."
                )
            else:
                gm_reply = (
                    f"의욕적인 제안은 고맙습니다. 하지만 현재 자원과 준비 상황을 보면 {requested_label}을 "
                    f"그대로 약속하기에는 부담이 큽니다. {target_label} 수준으로 현실화해 보는 것이 어떻겠습니까?"
                )
                board_reply = (
                    f"방향에는 공감하지만 지금 단계에서 약속할 수 있는 범위를 넘어섰다고 판단했습니다. "
                    f"{target_label} 수준으로 조정한 안을 보내주시면 긍정적으로 다시 논의하겠습니다."
                )
            conditions = []
        else:
            gm_reply = (
                f"감독님의 생각은 이해하지만, 이번 안은 구단이 준비해 온 계획과 차이가 너무 큽니다. "
                f"현 상태로는 제가 이사회에 동의를 요청하기 어렵습니다. {target_label} 수준에서 다시 논의했으면 합니다."
            )
            board_reply = (
                "이번 제안은 현재 구단의 우선순위와 기대를 충분히 반영하지 못했습니다. "
                f"{target_label} 수준을 기준으로 내용을 보완한 뒤 다시 제안해 주시기 바랍니다."
            )
            conditions = []
        return {
            "decision": decision,
            "target_level": evaluation.recommended_level,
            "conditions": conditions,
            "gm_reply": gm_reply,
            "board_reply": board_reply,
            "policy_summary": policy_reason,
            "reasons": list(evaluation.reasons),
            "tone": "존중",
            "source": "club_governance_rules_v2",
        }

    def resolve_vision_decision(self, evaluation, decision_payload):
        decision = decision_payload.get("decision", "counter_offer")
        if decision not in evaluation.allowed_decisions:
            decision_payload = self.fallback_decision(evaluation)
            decision = decision_payload["decision"]
        if decision in {"accept", "conditional_accept"}:
            final_level = evaluation.requested_level
        else:
            final_level = max(
                evaluation.hard_floor,
                min(5, int(decision_payload.get("target_level", evaluation.recommended_level))),
            )
        board_delta, gm_delta = self._relationship_deltas(
            evaluation.requested_level,
            decision,
            evaluation.priority,
            final_level,
            evaluation.preferred_level,
        )
        return {
            **decision_payload,
            "decision": decision,
            "requested_level": evaluation.requested_level,
            "final_level": final_level,
            "level_label": LEVELS[final_level]["label"],
            "approval_score": evaluation.approval_score,
            "direction_score": evaluation.direction_score,
            "execution_score": evaluation.execution_score,
            "manager_fit_score": evaluation.manager_fit_score,
            "board_trust_delta": board_delta,
            "gm_relationship_delta": gm_delta,
        }

    def _preferred_level(self, card):
        policy_level = self.policy.get("preferred_levels", {}).get(card.objective_key)
        proposal_level = getattr(card, "gm_proposed_level", None)
        # 저장 DB의 단장 원안과 조사 프로필이 다르면 더 강한 기준을 적용한다.
        candidates = [value for value in (policy_level, proposal_level) if value is not None]
        return max(1, min(5, int(max(candidates) if candidates else 3)))

    def _hard_floor(self, objective_key, preferred_level):
        value = self.policy.get("hard_floors", {}).get(objective_key, max(1, preferred_level - 1))
        return max(1, min(preferred_level, int(value)))

    def _direction_score(self, objective_key, requested_level, preferred_level):
        gm_primary, gm_secondary, owner_key = OBJECTIVE_SIGNALS.get(
            objective_key, OBJECTIVE_SIGNALS["roster_balance"]
        )
        values = [
            self.gm.get(gm_primary, 10),
            self.gm.get(gm_secondary, 10),
            self.owner.get(owner_key, 10),
        ]
        policy_strength = sum(values) / len(values) * 5
        distance = abs(requested_level - preferred_level)
        # 성향이 뚜렷한 구단일수록 선호 단계에서 벗어날 때 적합도가 더 빠르게 하락한다.
        fit = 75 + policy_strength * 0.25
        fit -= distance * (14 + policy_strength * 0.12)
        return _clamp(fit)

    def _execution_score(self, objective_key, requested_level):
        drive = self.policy.get("execution_drive", 10) * 5
        investment = self.policy.get("investment_aggression", self.owner.get("financial_support", 10)) * 5
        risk = self.policy.get("risk_tolerance", 10) * 5
        stability = self.owner.get("stability", 10) * 5
        if objective_key == "season_result":
            raw = drive * 0.40 + investment * 0.35 + risk * 0.15 + stability * 0.10
        elif objective_key in {"long_term_vision", "roster_balance"}:
            development = (self.gm.get("development", 10) + self.owner.get("long_term_development", 10)) * 2.5
            raw = drive * 0.25 + investment * 0.15 + stability * 0.20 + development * 0.40
        elif objective_key == "front_office_style":
            raw = drive * 0.30 + self.gm.get("data", 10) * 3 + self.gm.get("negotiation", 10) * 2
        else:
            raw = drive * 0.30 + investment * 0.15 + stability * 0.20 + self.owner.get("brand_value", 10) * 1.75
        if requested_level >= 4 and self.policy.get("execution_drive", 10) < 14:
            raw -= (14 - self.policy.get("execution_drive", 10)) * 3
        if requested_level == 5:
            raw -= max(0, 16 - self.policy.get("execution_drive", 10)) * 2
        return _clamp(raw)

    def _manager_fit_score(self, objective_key):
        weights = OBJECTIVE_ABILITY_WEIGHTS.get(objective_key, {})
        if not weights:
            return 50
        values = []
        for ability, weight in weights.items():
            raw = self.manager_data.get(ability, self.manager_data.get(f"manager_{ability}", 10))
            try:
                value = max(0, min(20, int(raw)))
            except (TypeError, ValueError):
                value = 10
            values.append(value * 5 * weight)
        return _clamp(sum(values))

    @staticmethod
    def _approval_score(
        requested,
        preferred,
        hard_floor,
        direction,
        execution,
        manager_fit,
        priority,
        autonomy,
    ):
        distance = abs(requested - preferred)
        target_fit = max(0, 100 - distance * 20)
        raw = target_fit * 0.58 + direction * 0.16 + execution * 0.16 + manager_fit * 0.10
        if requested == preferred:
            raw += 8
        if requested < preferred:
            raw -= (preferred - requested) * 5
        if requested < hard_floor:
            raw -= (hard_floor - requested) * 28
        if requested > preferred and requested >= 4:
            feasibility = min(execution, manager_fit)
            if feasibility < 60:
                raw -= (60 - feasibility) * 0.45
        if requested != preferred:
            # 현장 자율성이 높은 구단은 원안 이탈을 조금 더 허용하고,
            # 낮은 구단은 같은 단계 차이에도 더 강하게 저항한다.
            raw += (autonomy - 10) * distance * 0.8
        if priority == "필수" and requested < preferred:
            raw -= 7
        return _clamp(raw)

    @staticmethod
    def _recommended_level(requested, preferred, hard_floor, execution, manager_fit):
        if requested < hard_floor:
            return hard_floor
        if requested != preferred:
            return preferred
        return requested

    @staticmethod
    def _allowed_decisions(requested, preferred, hard_floor, score):
        if requested < hard_floor:
            return ("reject", "counter_offer")
        if requested == preferred and score >= 76:
            return ("accept", "conditional_accept")
        if score >= 82:
            return ("accept", "conditional_accept")
        if score >= 64:
            return ("conditional_accept", "counter_offer")
        if score >= 38:
            return ("counter_offer", "reject")
        return ("reject", "counter_offer")

    def _reasons(self, objective_key, requested, preferred, hard_floor, direction, execution, manager_fit):
        subject = OBJECTIVE_REASON_LABELS.get(objective_key, "구단 운영 방향")
        reasons = []
        if requested < hard_floor:
            reasons.append(
                f"이번 안건은 {subject}과 직접 연결되는 만큼, 현재 제안보다 더 분명한 목표가 필요합니다."
            )
        elif requested < preferred:
            reasons.append(
                f"제안의 취지는 이해하지만 구단이 준비해 온 {subject}을 충분히 반영하기에는 다소 조심스러운 안입니다."
            )
        elif requested > preferred and min(execution, manager_fit) < 60:
            reasons.append(
                "도전적인 목표는 환영하지만 현재 선수단과 투자 계획을 고려하면 약속을 지키기 어려울 수 있습니다."
            )
        else:
            reasons.append(
                f"감독님의 제안은 구단이 생각하는 {subject}과 큰 차이가 없으며 현재 계획 안에서 추진할 수 있습니다."
            )
        if execution < 55:
            reasons.append("필요한 지원과 선수단 보강 계획을 조금 더 구체적으로 설명해 주시기 바랍니다.")
        elif manager_fit < 50:
            reasons.append("감독님이 이 목표를 어떤 방식으로 실행할지 구체적인 운영 계획도 함께 듣고 싶습니다.")
        elif requested >= 4:
            reasons.append("높은 목표를 제시한 만큼 시즌 중 진행 상황을 꾸준히 공유해 주시기 바랍니다.")
        return reasons

    def _relationship_deltas(self, requested, decision, priority, final_level, preferred):
        weight = PRIORITY_WEIGHTS.get(priority, 1.0)
        gap = abs(requested - preferred)
        if decision == "accept":
            board_delta = round((2 if gap == 0 else 1) * weight)
        elif decision == "conditional_accept":
            board_delta = round((1 if gap == 0 else 0) * weight)
        elif decision == "counter_offer":
            board_delta = -round(max(1, gap) * weight)
        else:
            board_delta = -round((2 + gap) * weight)
        gm_delta = board_delta
        if requested != preferred:
            gm_delta -= round(max(0, self.gm.get("negotiation", 10) - 12) / 4)
        return board_delta, gm_delta
