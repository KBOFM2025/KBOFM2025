"""생성 모델의 출력을 게임에 반영하기 전에 검증하고 정규화한다."""


class InvalidDecision(ValueError):
    pass


def validate_board_review(payload, objective_keys):
    """Validate an AI-authored, five-item board review without rule-engine gating."""
    if not isinstance(payload, dict) or not isinstance(payload.get("reviews"), list):
        raise InvalidDecision("AI 응답에 reviews 배열이 없습니다.")
    expected = list(objective_keys)
    by_key = {}
    for item in payload["reviews"]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("objective_key", "")).strip()
        status = str(item.get("status", "")).strip()
        feedback = str(item.get("feedback", "")).strip()[:120]
        if key in expected and status in {"ok", "adjust"} and feedback:
            reason, separator, adjustment = feedback.partition(";")
            reason = reason.strip().rstrip(". ")
            if status == "adjust":
                feedback = (
                    "단장 및 이사회는 이 사안에 대해 협의할 수 없습니다. "
                    f"이유는 {reason}이기 때문입니다."
                )
                if separator and adjustment.strip():
                    feedback += f" 조정 요구: {adjustment.strip().rstrip('.')}입니다."
            else:
                feedback = (
                    "단장 및 이사회는 이 협의안을 수용합니다. "
                    f"이유는 {reason}이기 때문입니다."
                )
            by_key[key] = {"objective_key": key, "status": status, "feedback": feedback}
    if set(by_key) != set(expected):
        raise InvalidDecision("AI가 5개 협의 항목 모두에 답하지 않았습니다.")
    return {"reviews": [by_key[key] for key in expected], "source": "local_ai"}


def validate_club_vision_decision(payload, allowed_decisions):
    if not isinstance(payload, dict):
        raise InvalidDecision("AI 응답이 JSON 객체가 아닙니다.")

    decision = payload.get("decision")
    if decision not in set(allowed_decisions):
        raise InvalidDecision(f"허용되지 않은 결정입니다: {decision}")

    conditions = payload.get("conditions", [])
    if not isinstance(conditions, list):
        raise InvalidDecision("conditions는 배열이어야 합니다.")
    conditions = [str(item).strip()[:100] for item in conditions[:3] if str(item).strip()]
    if decision != "conditional_accept":
        conditions = []

    gm_reply = str(payload.get("gm_reply", "")).strip()[:260]
    board_reply = str(payload.get("board_reply", "")).strip()[:260]
    tone = str(payload.get("tone", "중립")).strip()[:40]
    if not gm_reply or not board_reply:
        raise InvalidDecision("단장 또는 이사회 답변이 비어 있습니다.")

    return {
        "decision": decision,
        "conditions": conditions,
        "gm_reply": gm_reply,
        "board_reply": board_reply,
        "tone": tone or "중립",
        "source": "local_ai",
    }
