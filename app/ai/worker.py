"""로컬 추론이 PySide6 UI 스레드를 막지 않도록 하는 작업 스레드."""

from PySide6.QtCore import QThread, Signal

from app.ai.governance_ai import GovernanceAI


class VisionDecisionWorker(QThread):
    decision_ready = Signal(dict)
    decision_failed = Signal(str)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context

    def run(self):
        try:
            result = GovernanceAI().decide_club_vision(self.context)
        except Exception as exc:  # UI에는 폴백을 제공하고 상세 오류만 전달한다.
            self.decision_failed.emit(str(exc))
            return
        self.decision_ready.emit(result)


class BoardReviewWorker(QThread):
    review_ready = Signal(dict)
    review_failed = Signal(str)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context

    def run(self):
        try:
            result = GovernanceAI().review_vision_submission(self.context)
        except Exception as exc:
            self.review_failed.emit(str(exc))
            return
        self.review_ready.emit(result)
