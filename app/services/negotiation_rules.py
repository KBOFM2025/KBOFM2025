"""구단 비전 협상에서 사용하는 결정·단계 공통 규칙."""


LEVELS = {
    1: {"label": "대폭 완화", "base_trust_delta": -8},
    2: {"label": "일부 완화", "base_trust_delta": -3},
    3: {"label": "원안 합의", "base_trust_delta": 0},
    4: {"label": "도전 합의", "base_trust_delta": 3},
    5: {"label": "최고 목표", "base_trust_delta": 6},
}

PRIORITY_WEIGHTS = {"필수": 2.0, "중요": 1.4, "장기": 1.2, "권장": 0.8}

DECISION_LABELS = {
    "accept": "승인",
    "conditional_accept": "조건부 승인",
    "counter_offer": "역제안",
    "reject": "거절",
}


def trust_delta_for_level(level, priority):
    data = LEVELS[int(level)]
    weight = PRIORITY_WEIGHTS.get(priority, 1.0)
    return round(data["base_trust_delta"] * weight)


def final_level_for_decision(requested_level, decision):
    requested_level = int(requested_level)
    if decision in {"accept", "conditional_accept"}:
        return requested_level
    if decision == "counter_offer":
        if requested_level < 3:
            return requested_level + 1
        if requested_level > 3:
            return requested_level - 1
    return 3
