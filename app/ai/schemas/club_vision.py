"""구단 비전 협상 응답 스키마."""


CLUB_VISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision",
        "conditions",
        "gm_reply",
        "board_reply",
        "tone",
    ],
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["accept", "conditional_accept", "counter_offer", "reject"],
        },
        "conditions": {
            "type": "array",
            "maxItems": 2,
            "items": {"type": "string", "minLength": 4, "maxLength": 25},
        },
        "gm_reply": {"type": "string", "minLength": 4, "maxLength": 60},
        "board_reply": {"type": "string", "minLength": 4, "maxLength": 60},
        "tone": {"type": "string", "minLength": 2, "maxLength": 10},
    },
}


BOARD_REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reviews"],
    "properties": {
        "reviews": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["objective_key", "status", "feedback"],
                "properties": {
                    "objective_key": {"type": "string"},
                    "status": {"type": "string", "enum": ["ok", "adjust"]},
                    "feedback": {"type": "string", "minLength": 5, "maxLength": 80},
                },
            },
        }
    },
}
