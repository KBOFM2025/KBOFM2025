"""시설·육성 건의 판단 확장용 스키마."""


FACILITY_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["decision", "conditions", "alternative"],
    "properties": {
        "decision": {"enum": ["accept", "delay", "counter_offer", "reject"]},
        "approved_budget": {"type": "integer", "minimum": 0},
        "start_date": {"type": "string"},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "alternative": {"type": "string"},
    },
}
