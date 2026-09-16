"""FM 스타일 FA·트레이드·선수 면담 대화 협상 페이지."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ai.negotiation_worker import NegotiationWorker


TALKING_POINTS = {
    "fa_opportunity": (
        "선수에게 보장할 역할과 기용 계획을 구체적으로 설명한다.",
        "구단의 우승 계획과 선수가 맡을 핵심 임무를 제시한다.",
        "현재 제시한 연봉이 선수 가치에 맞는 이유를 설명한다.",
    ),
    "trade_offer": (
        "양 구단의 포지션별 필요와 이번 거래의 상호 이익을 설명한다.",
        "두 선수의 가치가 균형을 이룬다는 전력 데이터를 제시한다.",
        "장기적인 선수단 구성 측면에서 상대 구단의 이익을 강조한다.",
    ),
    "player_complaint": (
        "선수에게 경쟁이 공정하게 이뤄질 기준을 구체적으로 설명한다.",
        "훈련 성과에 따른 출전 기회와 향후 역할을 약속한다.",
        "선수의 불만을 먼저 인정하고 함께 성장 계획을 세우자고 제안한다.",
    ),
}


class ManagerEventPage(QWidget):
    back_requested = Signal()
    event_resolved = Signal()

    def __init__(self, colors, event_service, save_id, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.event_service = event_service
        self.save_id = save_id
        # QWidget.event()를 데이터로 덮어쓰면 Qt 이벤트 전달이 충돌한다.
        self.current_event = None
        self.negotiation_data = None
        self.worker = None

        root = QVBoxLayout()
        self.setLayout(root)
        root.setContentsMargins(0, 0, 0, 0)
        canvas = QWidget()
        canvas.setObjectName("NegotiationCanvas")
        page = QVBoxLayout(canvas)
        page.setContentsMargins(34, 22, 34, 28)
        page.setSpacing(12)

        header = QHBoxLayout()
        back = QPushButton("←  수신함")
        back.setObjectName("BackButton")
        back.clicked.connect(self.back_requested.emit)
        header.addWidget(back)
        header.addStretch()
        self.date_label = QLabel()
        self.date_label.setObjectName("DateLabel")
        header.addWidget(self.date_label)
        page.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        info_card = QFrame()
        info_card.setObjectName("InfoCard")
        info_card.setMinimumWidth(300)
        info_card.setMaximumWidth(390)
        info = QVBoxLayout(info_card)
        info.setContentsMargins(23, 22, 23, 24)
        info.setSpacing(11)
        self.category_label = QLabel()
        self.category_label.setObjectName("Category")
        info.addWidget(self.category_label)
        self.headline_label = QLabel()
        self.headline_label.setWordWrap(True)
        self.headline_label.setObjectName("Headline")
        self.headline_label.setFont(QFont("Malgun Gothic", 20, QFont.Bold))
        info.addWidget(self.headline_label)
        self.body_label = QLabel()
        self.body_label.setWordWrap(True)
        self.body_label.setObjectName("Body")
        info.addWidget(self.body_label)
        info.addSpacing(8)
        role_title = QLabel("협상 상대")
        role_title.setObjectName("InfoTitle")
        info.addWidget(role_title)
        self.counterpart_label = QLabel()
        self.counterpart_label.setObjectName("Counterpart")
        info.addWidget(self.counterpart_label)
        demand_title = QLabel("상대의 핵심 요구")
        demand_title.setObjectName("InfoTitle")
        info.addWidget(demand_title)
        self.demand_label = QLabel()
        self.demand_label.setWordWrap(True)
        self.demand_label.setObjectName("Demand")
        info.addWidget(self.demand_label)
        info.addStretch()
        score_title = QLabel("협상 설득도")
        score_title.setObjectName("InfoTitle")
        info.addWidget(score_title)
        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setTextVisible(True)
        info.addWidget(self.score_bar)
        self.round_label = QLabel()
        self.round_label.setObjectName("Round")
        info.addWidget(self.round_label)
        columns.addWidget(info_card)

        talk_card = QFrame()
        talk_card.setObjectName("TalkCard")
        talk = QVBoxLayout(talk_card)
        talk.setContentsMargins(21, 17, 21, 19)
        talk.setSpacing(9)
        talk_title_row = QHBoxLayout()
        talk_title = QLabel("협상 대화")
        talk_title.setObjectName("TalkTitle")
        talk_title_row.addWidget(talk_title)
        talk_title_row.addStretch()
        self.ai_status = QLabel("상대의 반응을 읽고 직접 설득하십시오")
        self.ai_status.setObjectName("AIStatus")
        talk_title_row.addWidget(self.ai_status)
        talk.addLayout(talk_title_row)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_canvas = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_canvas)
        self.chat_layout.setContentsMargins(4, 6, 4, 6)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_canvas)
        talk.addWidget(self.chat_scroll, 1)

        hint_label = QLabel("대화 방향 제안 · 누르면 입력창에 추가됩니다")
        hint_label.setObjectName("HintLabel")
        talk.addWidget(hint_label)
        self.hint_layout = QHBoxLayout()
        self.hint_layout.setSpacing(6)
        talk.addLayout(self.hint_layout)

        input_row = QHBoxLayout()
        self.message_input = QTextEdit()
        self.message_input.setObjectName("MessageInput")
        self.message_input.setPlaceholderText(
            "상대를 설득할 말을 직접 입력하세요. 구체적인 약속과 근거가 중요합니다."
        )
        self.message_input.setFixedHeight(76)
        input_row.addWidget(self.message_input, 1)
        self.send_button = QPushButton("대화 전달")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedWidth(112)
        self.send_button.setFixedHeight(76)
        self.send_button.clicked.connect(self._send_message)
        input_row.addWidget(self.send_button)
        talk.addLayout(input_row)

        footer = QHBoxLayout()
        self.withdraw_button = QPushButton("협상 중단")
        self.withdraw_button.setObjectName("WithdrawButton")
        self.withdraw_button.clicked.connect(self._withdraw)
        footer.addWidget(self.withdraw_button)
        footer.addStretch()
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("Result")
        footer.addWidget(self.result_label, 1)
        talk.addLayout(footer)
        columns.addWidget(talk_card, 1)

        page.addLayout(columns, 1)
        root.addWidget(canvas)
        self._apply_style()

    def _apply_style(self):
        c = self.colors
        self.setStyleSheet(f"""
            QWidget#NegotiationCanvas {{ background: #0f141a; }}
            QFrame#InfoCard, QFrame#TalkCard {{
                background: #171e26; border: 1px solid #3a4652;
            }}
            QLabel {{ color: #dce5ed; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QLabel#Category {{ color: {c['accent_light']}; font-size: 14px; font-weight: 800; }}
            QLabel#Headline {{ color: white; }}
            QLabel#Body {{ color: #aebac5; font-size: 15px; padding: 4px 0 10px 0; }}
            QLabel#InfoTitle, QLabel#HintLabel {{ color: #778796; font-size: 13px; font-weight: 700; }}
            QLabel#Counterpart {{ color: white; font-size: 15px; font-weight: 800; }}
            QLabel#Demand {{ color: #d2dbe3; background: #202934; border-left: 3px solid {c['accent']}; padding: 10px; }}
            QLabel#Round, QLabel#DateLabel, QLabel#AIStatus {{ color: #82909d; font-size: 13px; }}
            QLabel#TalkTitle {{ color: white; font-size: 17px; font-weight: 800; }}
            QLabel#Result {{ color: #7ed7aa; font-weight: 700; }}
            QPushButton#BackButton, QPushButton#WithdrawButton {{
                color: #d8e0e7; background: #202832; border: 1px solid #46525e;
                padding: 7px 13px; font-weight: 700;
            }}
            QPushButton#BackButton:hover {{ background: {c['accent']}; }}
            QPushButton#WithdrawButton:hover {{ background: #5a2528; }}
            QPushButton#SendButton {{
                color: white; background: {c['accent']}; border: 1px solid {c['accent_light']};
                font-size: 15px; font-weight: 800;
            }}
            QPushButton#SendButton:hover {{ background: {c['accent_light']}; }}
            QPushButton#SendButton:disabled {{ background: #3a434c; color: #7c8791; border-color: #505963; }}
            QPushButton[hint="true"] {{
                color: #b9c5cf; background: #202934; border: 1px solid #3c4956;
                padding: 7px; text-align: left; font-size: 13px;
            }}
            QPushButton[hint="true"]:hover {{ color: white; border-color: {c['accent_light']}; }}
            QTextEdit#MessageInput {{
                color: white; background: #0f151b; border: 1px solid #46525e;
                padding: 8px; selection-background-color: {c['accent']};
            }}
            QScrollArea {{ background: #11171d; border: 1px solid #2e3944; }}
            QWidget#ChatCanvas {{ background: #11171d; }}
            QLabel[bubble="counterpart"] {{
                color: #dce4eb; background: #252f39; border-left: 3px solid #6f8192;
                padding: 10px 12px; margin-right: 90px;
            }}
            QLabel[bubble="manager"] {{
                color: white; background: {c['accent']}; border-right: 3px solid {c['accent_light']};
                padding: 10px 12px; margin-left: 90px;
            }}
            QProgressBar {{
                color: white; background: #0f151b; border: 1px solid #46525e;
                height: 20px; text-align: center; font-weight: 800;
            }}
            QProgressBar::chunk {{ background: {c['accent']}; }}
        """)
        self.chat_canvas.setObjectName("ChatCanvas")

    def set_event(self, event):
        self.current_event = event
        self.date_label.setText(str(event.get("event_date", "")).replace("-", "."))
        self.headline_label.setText(event.get("headline", "감독 업무"))
        self.body_label.setText(event.get("body", ""))
        try:
            self.negotiation_data = self.event_service.negotiation_state(
                self.save_id, int(event["id"])
            )
        except Exception as error:
            QMessageBox.critical(self, "협상 불러오기 오류", str(error))
            return
        rule = self.negotiation_data["rule"]
        self.category_label.setText(rule["title"])
        self.counterpart_label.setText(rule["counterpart_role"])
        self.demand_label.setText(rule["demand"])
        self._build_hints(self.negotiation_data["event_type"])
        self._render_state()

    def _build_hints(self, event_type):
        while self.hint_layout.count():
            item = self.hint_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, text in enumerate(TALKING_POINTS.get(event_type, ())):
            button = QPushButton(f"{index + 1}. {text}")
            button.setProperty("hint", True)
            button.setToolTip(text)
            button.clicked.connect(
                lambda _checked=False, value=text: self.message_input.setPlainText(value)
            )
            self.hint_layout.addWidget(button, 1)

    def _clear_chat(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_state(self):
        data = self.negotiation_data
        state = data["negotiation"]
        self._clear_chat()
        for turn in state.get("transcript", []):
            speaker = turn.get("speaker", "counterpart")
            prefix = "감독" if speaker == "manager" else data["rule"]["counterpart_role"]
            delta = turn.get("delta")
            suffix = ""
            if delta is not None:
                suffix = f"\n\n반응 {'+' if int(delta) >= 0 else ''}{int(delta)}"
            bubble = QLabel(f"{prefix}\n{turn.get('text', '')}{suffix}")
            bubble.setWordWrap(True)
            bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            bubble.setProperty("bubble", speaker)
            self.chat_layout.addWidget(bubble)
        self.chat_layout.addStretch()

        score = int(state.get("score", 0))
        target = int(state.get("target_score", 100))
        current_round = int(state.get("round", 0))
        max_rounds = int(state.get("max_rounds", 5))
        self.score_bar.setValue(score)
        self.score_bar.setFormat(f"{score} / 합의 기준 {target}")
        self.round_label.setText(
            f"대화 {current_round}/{max_rounds}회 · 남은 기회 {max(0, max_rounds-current_round)}회"
        )
        resolved = bool(data.get("resolved"))
        active = state.get("status") == "active" and not resolved
        self.message_input.setEnabled(active)
        self.send_button.setEnabled(active)
        self.withdraw_button.setEnabled(active)
        self.result_label.setText(data.get("result_text", "") if resolved else "")
        self.ai_status.setText(
            "협상 완료" if resolved
            else "합의 도달" if state.get("status") == "accepted"
            else "협상 결렬" if state.get("status") == "rejected"
            else "상대의 반응을 읽고 직접 설득하십시오"
        )
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _send_message(self):
        if not self.current_event or self.worker is not None:
            return
        text = self.message_input.toPlainText().strip()
        if len(text) < 5:
            QMessageBox.information(
                self, "대화 입력", "상대를 설득할 내용을 조금 더 구체적으로 입력하세요."
            )
            return
        if len(text) > 600:
            QMessageBox.information(
                self, "대화 입력", "한 번의 대화는 600자 이내로 입력하세요."
            )
            return
        try:
            context = self.event_service.negotiation_context(
                self.save_id, int(self.current_event["id"]), text
            )
        except Exception as error:
            QMessageBox.critical(self, "협상 오류", str(error))
            return
        self.message_input.clear()
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.ai_status.setText("상대가 제안을 검토하고 있습니다…")
        self.worker = NegotiationWorker(context, self)
        self.worker.response_ready.connect(
            lambda response, message=text: self._receive_response(message, response)
        )
        self.worker.response_failed.connect(self._response_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _receive_response(self, manager_message, response):
        try:
            state = self.event_service.record_negotiation_turn(
                self.save_id,
                int(self.current_event["id"]),
                manager_message,
                response,
            )
            self.negotiation_data = self.event_service.negotiation_state(
                self.save_id, int(self.current_event["id"])
            )
            self._render_state()
            if state.get("status") in {"accepted", "rejected"}:
                accepted = state["status"] == "accepted"
                result = self.event_service.finish_negotiation(
                    self.save_id, int(self.current_event["id"]), accepted
                )
                self.negotiation_data["resolved"] = True
                self.negotiation_data["result_text"] = result
                self._render_state()
                self.event_resolved.emit()
        except Exception as error:
            QMessageBox.critical(self, "협상 결과 처리 오류", str(error))

    def _response_failed(self, message):
        self.ai_status.setText("응답 생성 실패")
        QMessageBox.warning(
            self,
            "협상 AI",
            f"상대의 응답을 생성하지 못했습니다. 다시 시도할 수 있습니다.\n\n{message}",
        )

    def _worker_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        if self.negotiation_data and not self.negotiation_data.get("resolved"):
            active = self.negotiation_data["negotiation"].get("status") == "active"
            self.message_input.setEnabled(active)
            self.send_button.setEnabled(active)

    def _withdraw(self):
        if not self.current_event:
            return
        answer = QMessageBox.question(
            self,
            "협상 중단",
            "협상을 중단하면 이번 제안은 최종 거절됩니다. 계속하시겠습니까?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.event_service.finish_negotiation(
                self.save_id, int(self.current_event["id"]), False
            )
            self.negotiation_data["resolved"] = True
            self.negotiation_data["result_text"] = result
            self._render_state()
            self.event_resolved.emit()
        except Exception as error:
            QMessageBox.critical(self, "협상 중단 오류", str(error))

    def shutdown_worker(self):
        """메인 창 종료 전에 실행 중인 로컬 AI 연결을 정리한다."""
        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        worker.cancel()
        if not worker.wait(1500):
            worker.terminate()
            worker.wait(500)
        self.worker = None
