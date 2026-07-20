"""FA 영입 요청 판단 확장용 스키마."""


FREE_AGENT_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["decision", "gm_reply"],
    "properties": {
        "decision": {"enum": ["approve", "shortlist", "alternative", "reject"]},
        "target_player_id": {"type": "integer"},
        "maximum_total_value": {"type": "integer", "minimum": 0},
        "maximum_years": {"type": "integer", "minimum": 1, "maximum": 6},
        "alternative_player_ids": {"type": "array", "items": {"type": "integer"}},
        "gm_reply": {"type": "string"},
    },
}
