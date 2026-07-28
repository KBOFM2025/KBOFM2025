"""협상 AI 호출로 UI가 멈추지 않게 하는 작업 스레드."""

from PySide6.QtCore import QThread, Signal

from app.ai.negotiation_ai import NegotiationAI


class NegotiationWorker(QThread):
    response_ready = Signal(dict)
    response_failed = Signal(str)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.ai = NegotiationAI()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.ai.cancel()

    def run(self):
        try:
            response = self.ai.respond(self.context)
            if not self._cancelled:
                self.response_ready.emit(response)
        except Exception as error:
            if not self._cancelled:
                self.response_failed.emit(str(error))
