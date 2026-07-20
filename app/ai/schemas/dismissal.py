"""감독 재계약·경질 판단 확장용 스키마."""


DISMISSAL_SCHEMA = {
    "type": "object",
    "required": ["gm_recommendation", "board_decision", "reason"],
    "properties": {
        "gm_recommendation": {"enum": ["extend", "wait", "dismiss"]},
        "board_decision": {"enum": ["extend", "warning", "dismiss"]},
        "review_period_days": {"type": "integer", "minimum": 0, "maximum": 180},
        "reason": {"type": "string"},
        "required_improvements": {"type": "array", "items": {"type": "string"}},
    },
}
