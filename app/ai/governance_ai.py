"""거버넌스 도메인의 로컬 모델 호출과 검증을 묶는다."""

from app.ai.decision_validator import validate_board_review, validate_club_vision_decision
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
        return validate_board_review(payload, keys)
