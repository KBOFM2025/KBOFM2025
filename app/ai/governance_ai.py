"""거버넌스 도메인의 로컬 모델 호출과 검증을 묶는다."""

from app.ai.decision_validator import (
    level_constraints_from_feedback,
    validate_board_review,
    validate_club_vision_decision,
)
from app.ai.local_model import LocalModelClient
from app.ai.prompts.board import BOARD_BATCH_REVIEW_SYSTEM_PROMPT, BOARD_VISION_SYSTEM_PROMPT
from app.ai.schemas.club_vision import BOARD_REVIEW_SCHEMA, CLUB_VISION_SCHEMA


class GovernanceAI:
    def __init__(self, client=None):
        self.client = client or LocalModelClient()

    def decide_club_vision(self, context):
        payload = self.client.generate_json(
            BOARD_VISION_SYSTEM_PROMPT,
            context,
            CLUB_VISION_SCHEMA,
        )
        return validate_club_vision_decision(
            payload,
            context["request"]["allowed_decisions"],
        )

    def review_vision_submission(self, context):
        payload = self.client.generate_json(
            BOARD_BATCH_REVIEW_SYSTEM_PROMPT, context, BOARD_REVIEW_SCHEMA
        )
        keys = [item["objective_key"] for item in context["submission"]]
        result = validate_board_review(payload, keys)
        reviews = {
            item["objective_key"]: item for item in result["reviews"]
        }
        for submission in context["submission"]:
            previous = dict(submission.get("previous_review") or {})
            if previous.get("status") != "adjust":
                continue
            constraints = {
                key: previous[key]
                for key in (
                    "required_min_level",
                    "required_max_level",
                    "required_level",
                )
                if previous.get(key) is not None
            }
            if not constraints:
                constraints = level_constraints_from_feedback(
                    previous.get("feedback")
                )
            if not constraints:
                continue
            selected = int(submission["selected_level"])
            satisfies = (
                selected >= int(constraints.get("required_min_level", 1))
                and selected <= int(constraints.get("required_max_level", 5))
                and (
                    "required_level" not in constraints
                    or selected == int(constraints["required_level"])
                )
            )
            if satisfies:
                reviews[submission["objective_key"]] = {
                    "objective_key": submission["objective_key"],
                    "status": "ok",
                    "feedback": (
                        "단장 및 이사회는 이 협의안을 수용합니다. "
                        "이유는 직전 이사회의 단계 조정 요구를 충족했기 때문입니다."
                    ),
                }
        result["reviews"] = [reviews[key] for key in keys]
        return result
