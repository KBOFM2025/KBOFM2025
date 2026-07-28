"""단장실 장면 위에서 진행되는 FM 스타일 트레이드 협상."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ai.negotiation_worker import NegotiationWorker
from app.utils import resource_path
from app.views.player_meeting import MeetingBackdrop


TRADE_TALKING_POINTS = (
    "두 선수의 최근 성적과 연령을 보면 공정한 제안 같습니다. 수락 의사를 전달해 주세요.",
    "우리 선수가 더 가치 있습니다. 현금 보상을 추가해 달라고 전달해 주세요.",
    "현재 조건에는 부족함이 있습니다. 추가 선수를 포함해 달라고 전달해 주세요.",
    "추가 선수와 현금을 함께 주는 복합 보상을 요청해 주세요.",
    "상대 구단이 후보군에서 30일 이내 한 명을 확정하는 추후 지명 선수를 요청해 주세요.",
)


class TradeNegotiationPage(QWidget):
    back_requested = Signal()
    event_resolved = Signal()

    def __init__(self, colors, event_service, save_id, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.event_service = event_service
        self.save_id = save_id
        self.current_event = None
        self.negotiation_data = None
        self.worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scene = MeetingBackdrop(
            resource_path("image", "Scenes", "trade_office.png")
        )
        root.addWidget(self.scene)
        overlay = QVBoxLayout(self.scene)
        overlay.setContentsMargins(28, 20, 28, 24)
        overlay.setSpacing(12)

        header = QHBoxLayout()
        back = QPushButton("←  수신함")
        back.setObjectName("TradeBack")
        back.clicked.connect(self.back_requested.emit)
        header.addWidget(back)
        badge = QLabel("  GM OFFICE  ")
        badge.setObjectName("TradeBadge")
        header.addWidget(badge)
        header.addStretch()
        self.date_label = QLabel()
        self.date_label.setObjectName("TradeDate")
        header.addWidget(self.date_label)
        overlay.addLayout(header)

        upper = QHBoxLayout()
        upper.setSpacing(12)
        upper.addStretch(1)
        dialogue = QFrame()
        dialogue.setObjectName("TradeDialogue")
        dialogue.setMaximumHeight(310)
        dialogue_layout = QVBoxLayout(dialogue)
        dialogue_layout.setContentsMargins(21, 16, 21, 18)
        self.counterpart_label = QLabel("우리 구단 단장")
        self.counterpart_label.setObjectName("TradeCounterpart")
        dialogue_layout.addWidget(self.counterpart_label)
        self.reply_label = QTextEdit()
        self.reply_label.setObjectName("TradeReply")
        self.reply_label.setReadOnly(True)
        self.reply_label.setMinimumHeight(130)
        self.reply_label.setMaximumHeight(185)
        dialogue_layout.addWidget(self.reply_label)
        self.last_manager_label = QLabel()
        self.last_manager_label.setObjectName("LastManager")
        self.last_manager_label.setWordWrap(True)
        dialogue_layout.addWidget(self.last_manager_label)
        upper.addWidget(dialogue, 6)

        deal = QFrame()
        deal.setObjectName("DealCard")
        deal.setFixedWidth(340)
        deal_layout = QVBoxLayout(deal)
        deal_layout.setContentsMargins(18, 16, 18, 18)
        deal_title = QLabel("상대 구단 현재 제안")
        deal_title.setObjectName("DealTitle")
        deal_layout.addWidget(deal_title)
        self.other_team_label = QLabel()
        self.other_team_label.setObjectName("OtherTeam")
        deal_layout.addWidget(self.other_team_label)
        receive_caption = QLabel("우리 구단이 영입")
        receive_caption.setObjectName("DealCaption")
        deal_layout.addWidget(receive_caption)
        self.receive_label = QLabel()
        self.receive_label.setObjectName("ReceivePlayer")
        self.receive_label.setWordWrap(True)
        deal_layout.addWidget(self.receive_label)
        arrow = QLabel("⇅")
        arrow.setObjectName("TradeArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        deal_layout.addWidget(arrow)
        give_caption = QLabel("우리 구단이 이적")
        give_caption.setObjectName("DealCaption")
        deal_layout.addWidget(give_caption)
        self.give_label = QLabel()
        self.give_label.setObjectName("GivePlayer")
        self.give_label.setWordWrap(True)
        deal_layout.addWidget(self.give_label)
        compensation_caption = QLabel("추가 조건 및 역제안")
        compensation_caption.setObjectName("DealCaption")
        deal_layout.addWidget(compensation_caption)
        self.compensation_label = QLabel()
        self.compensation_label.setObjectName("Compensation")
        self.compensation_label.setWordWrap(True)
        deal_layout.addWidget(self.compensation_label)
        self.offer_status_label = QLabel()
        self.offer_status_label.setObjectName("OfferStatus")
        self.offer_status_label.setWordWrap(True)
        deal_layout.addWidget(self.offer_status_label)
        upper.addWidget(deal)
        overlay.addLayout(upper, 4)
        overlay.addStretch(2)

        action = QFrame()
        action.setObjectName("TradeAction")
        action_layout = QVBoxLayout(action)
        action_layout.setContentsMargins(20, 15, 20, 18)
        action_layout.setSpacing(9)
        state_row = QHBoxLayout()
        action_title = QLabel("단장에게 전달할 의견")
        action_title.setObjectName("ActionTitle")
        state_row.addWidget(action_title)
        state_row.addStretch()
        self.round_label = QLabel()
        self.round_label.setObjectName("TradeRound")
        state_row.addWidget(self.round_label)
        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setFixedWidth(235)
        self.score_bar.setFixedHeight(19)
        state_row.addWidget(self.score_bar)
        action_layout.addLayout(state_row)

        hint_row = QGridLayout()
        hint_row.setSpacing(7)
        self.hint_buttons = []
        for index, point in enumerate(TRADE_TALKING_POINTS, start=1):
            button = QPushButton(f"{index}. {point}")
            button.setProperty("tradeHint", True)
            button.setToolTip(point)
            button.clicked.connect(
                lambda _checked=False, text=point: self.message_input.setPlainText(text)
            )
            self.hint_buttons.append(button)
            hint_row.addWidget(button, (index - 1) // 3, (index - 1) % 3)
        action_layout.addLayout(hint_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.message_input = QTextEdit()
        self.message_input.setObjectName("TradeInput")
        self.message_input.setPlaceholderText(
            "들어온 제안에 대한 생각, 역제안 또는 거절 이유를 우리 단장에게 말하세요."
        )
        self.message_input.setFixedHeight(70)
        input_row.addWidget(self.message_input, 1)
        self.send_button = QPushButton("의견 전달\nENTER")
        self.send_button.setObjectName("TradeSend")
        self.send_button.setFixedSize(120, 70)
        self.send_button.clicked.connect(self._send_message)
        input_row.addWidget(self.send_button)
        action_layout.addLayout(input_row)
        footer = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("TradeStatus")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        withdraw = QPushButton("협상 철회")
        withdraw.setObjectName("TradeWithdraw")
        withdraw.clicked.connect(self._withdraw)
        footer.addWidget(withdraw)
        action_layout.addLayout(footer)
        overlay.addWidget(action, 4)
        self._apply_style()

    def _apply_style(self):
        c = self.colors
        self.setStyleSheet(f"""
            QLabel {{ color: #f4f7fa; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QPushButton#TradeBack, QPushButton#TradeWithdraw {{
                color: #eef3f7; background: rgba(12, 17, 23, 226);
                border: 1px solid rgba(142, 159, 174, 150);
                border-radius: 6px; padding: 7px 14px; font-weight: 750;
            }}
            QPushButton#TradeBack:hover {{ background: {c['accent']}; }}
            QPushButton#TradeWithdraw:hover {{ background: #6b2b31; }}
            QLabel#TradeBadge {{
                color: {c['accent_light']}; background: rgba(10, 15, 21, 220);
                border: 1px solid {c['accent']}; border-radius: 5px;
                padding: 6px 10px; font-size: 10px; font-weight: 900;
            }}
            QLabel#TradeDate {{ color: #d1d9e0; font-size: 11px; }}
            QFrame#TradeDialogue {{
                background: rgba(10, 15, 21, 235);
                border: 1px solid rgba(133, 151, 166, 150);
                border-left: 4px solid {c['accent_light']}; border-radius: 9px;
            }}
            QLabel#TradeCounterpart {{
                color: {c['accent_light']}; font-size: 12px; font-weight: 900;
            }}
            QTextEdit#TradeReply {{
                color: white; background: transparent; border: none;
                font-size: 14px; font-weight: 700; padding: 0;
            }}
            QLabel#LastManager {{
                color: #94a4b2; border-top: 1px solid rgba(110, 127, 141, 90);
                padding-top: 7px; font-size: 11px;
            }}
            QFrame#DealCard {{
                background: rgba(10, 15, 21, 238);
                border: 1px solid rgba(133, 151, 166, 145); border-radius: 9px;
            }}
            QLabel#DealTitle {{ color: #94a4b2; font-size: 11px; font-weight: 800; }}
            QLabel#OtherTeam {{ color: white; font-size: 17px; font-weight: 900; padding-bottom: 5px; }}
            QLabel#DealCaption {{ color: #7f909f; font-size: 10px; }}
            QLabel#ReceivePlayer {{ color: #78ddb0; font-size: 15px; font-weight: 900; }}
            QLabel#GivePlayer {{ color: #f0ad78; font-size: 15px; font-weight: 900; }}
            QLabel#Compensation {{ color: #ffd074; font-size: 14px; font-weight: 900; }}
            QLabel#OfferStatus {{
                color: #b3c0cb; background: rgba(39, 49, 59, 180);
                border-radius: 4px; padding: 5px 7px; font-size: 10px;
            }}
            QLabel#TradeArrow {{ color: {c['accent_light']}; font-size: 18px; }}
            QFrame#TradeAction {{
                background: rgba(9, 14, 20, 244);
                border: 1px solid rgba(133, 151, 166, 145); border-radius: 10px;
            }}
            QLabel#ActionTitle {{ color: white; font-size: 14px; font-weight: 900; }}
            QLabel#TradeRound {{ color: #8999a7; font-size: 11px; }}
            QLabel#TradeStatus {{ color: #87d8b0; font-size: 11px; font-weight: 700; }}
            QPushButton[tradeHint="true"] {{
                color: #c5d0d9; background: rgba(31, 40, 50, 235);
                border: 1px solid #3b4956; border-radius: 6px;
                padding: 8px 10px; text-align: left; font-size: 10px;
            }}
            QPushButton[tradeHint="true"]:hover {{
                color: white; background: rgba(47, 61, 74, 245);
                border-color: {c['accent_light']};
            }}
            QTextEdit#TradeInput {{
                color: white; background: rgba(8, 12, 17, 245);
                border: 1px solid #4b5b69; border-radius: 7px;
                padding: 9px; selection-background-color: {c['accent']};
                font-size: 12px;
            }}
            QPushButton#TradeSend {{
                color: white; background: {c['accent']};
                border: 1px solid {c['accent_light']}; border-radius: 7px;
                font-size: 12px; font-weight: 900;
            }}
            QPushButton#TradeSend:hover {{ background: {c['accent_light']}; }}
            QPushButton#TradeSend:disabled {{ background: #39434c; color: #7f8992; border-color: #4a545d; }}
            QProgressBar {{
                color: white; background: rgba(5, 9, 13, 230);
                border: 1px solid #4a5865; border-radius: 5px;
                text-align: center; font-size: 10px; font-weight: 800;
            }}
            QProgressBar::chunk {{ background: {c['accent_light']}; border-radius: 4px; }}
        """)

    def set_event(self, event):
        self.current_event = event
        self.date_label.setText(str(event.get("event_date", "")).replace("-", "."))
        self.negotiation_data = self.event_service.negotiation_state(
            self.save_id, int(event["id"])
        )
        payload = self.negotiation_data["payload"]
        self.other_team_label.setText(payload.get("other_team", "상대 구단"))
        self.counterpart_label.setText(
            f"{payload.get('managed_team', '우리 구단')} 단장 · "
            f"{payload.get('other_team', '상대 구단')} 회신"
        )
        self._render_state()

    def _render_state(self):
        data = self.negotiation_data
        state = data["negotiation"]
        transcript = state.get("transcript", [])
        latest_reply = next(
            (
                item.get("text", "")
                for item in reversed(transcript)
                if item.get("speaker") == "counterpart"
            ),
            data["rule"]["opening"],
        )
        latest_manager = next(
            (
                item.get("text", "")
                for item in reversed(transcript)
                if item.get("speaker") == "manager"
            ),
            "",
        )
        conversation_lines = []
        for item in transcript[-16:]:
            if item.get("speaker") == "manager":
                speaker = "감독"
            else:
                speaker = (
                    f"{data['payload'].get('managed_team', '우리 구단')} 단장 "
                    f"· {data['payload'].get('other_team', '상대 구단')} 회신"
                )
            conversation_lines.append(
                f"{speaker}\n{item.get('text', '')}"
            )
        self.reply_label.setPlainText(
            "\n\n".join(conversation_lines) or latest_reply
        )
        self.reply_label.verticalScrollBar().setValue(
            self.reply_label.verticalScrollBar().maximum()
        )
        self.last_manager_label.setText(
            f"내 마지막 의견  ·  {latest_manager}"
            if latest_manager else "아직 단장에게 전달한 의견이 없습니다."
        )
        self._render_trade_terms(data["payload"], transcript)
        score = int(state.get("score", 0))
        current_round = int(state.get("round", 0))
        self.round_label.setText(
            f"ROUND {current_round} · 수락 또는 거절 전까지 계속"
        )
        self.score_bar.setValue(score)
        self.score_bar.setFormat(
            f"협상 분위기 {score}  ·  조건 수락 시에만 확정"
        )
        active = (
            not data.get("resolved")
            and state.get("status") == "active"
            and self.worker is None
        )
        self.message_input.setEnabled(active)
        self.send_button.setEnabled(active)
        for button in self.hint_buttons:
            button.setEnabled(active)
        if data.get("resolved"):
            self.status_label.setText(data.get("result_text", "협상이 종료됐습니다."))
        elif state.get("status") == "accepted":
            self.status_label.setText("단장이 상대 구단의 최종 합의를 받아왔습니다.")
        elif state.get("status") == "rejected":
            self.status_label.setText("단장이 상대 구단의 협상 종료 의사를 보고했습니다.")
        else:
            self.status_label.setText(
                "양 구단이 조건을 주고받는 중입니다. 수락·수정·거절 의사를 "
                "우리 단장에게 구체적으로 전달하십시오."
            )

    def _render_trade_terms(self, payload, transcript):
        latest_terms = next(
            (
                dict(item.get("terms") or {})
                for item in reversed(transcript)
                if item.get("speaker") == "counterpart" and item.get("terms")
            ),
            dict(payload.get("trade_terms") or {}),
        )
        incoming_name = latest_terms.get(
            "incoming_name", payload.get("incoming_name", "-")
        )
        incoming_rating = int(
            latest_terms.get(
                "incoming_rating", payload.get("incoming_rating", 0)
            ) or 0
        )
        incoming_salary = int(
            latest_terms.get(
                "incoming_salary", payload.get("incoming_salary", 0)
            ) or 0
        )
        additional_name = str(
            latest_terms.get("additional_incoming_name") or ""
        )
        receive_text = self._player_term_text(
            incoming_name, incoming_rating, incoming_salary
        )
        if additional_name:
            receive_text += "\n+ " + self._player_term_text(
                additional_name,
                int(latest_terms.get("additional_incoming_rating") or 0),
                int(latest_terms.get("additional_incoming_salary") or 0),
                suffix="추가 보상",
            )
        self.receive_label.setText(receive_text)
        give_text = self._player_term_text(
            latest_terms.get(
                "outgoing_name", payload.get("outgoing_name", "-")
            ),
            int(
                latest_terms.get(
                    "outgoing_rating", payload.get("outgoing_rating", 0)
                ) or 0
            ),
            int(
                latest_terms.get(
                    "outgoing_salary", payload.get("outgoing_salary", 0)
                ) or 0
            ),
        )
        additional_outgoing_name = str(
            latest_terms.get("additional_outgoing_name") or ""
        )
        if additional_outgoing_name:
            give_text += "\n+ " + self._player_term_text(
                additional_outgoing_name,
                int(latest_terms.get("additional_outgoing_rating") or 0),
                int(latest_terms.get("additional_outgoing_salary") or 0),
                suffix="상대 요구",
            )
        self.give_label.setText(give_text)
        cash_label = str(latest_terms.get("cash_label") or "없음")
        cash_amount = int(latest_terms.get("cash_to_user_10k") or 0)
        future_pool = list(latest_terms.get("future_player_pool") or [])
        cash_from_user = int(
            latest_terms.get("cash_from_user_10k") or 0
        )
        cash_from_user_label = str(
            latest_terms.get("cash_from_user_label") or "없음"
        )
        future_pool_outgoing = list(
            latest_terms.get("future_player_pool_outgoing") or []
        )
        direction = str(
            latest_terms.get("compensation_direction") or "none"
        )
        if future_pool_outgoing:
            pool_lines = [
                self._player_term_text(
                    player.get("name", "후보"),
                    int(player.get("rating") or 0),
                    int(player.get("salary") or 0),
                )
                for player in future_pool_outgoing
            ]
            compensation = (
                "상대 요구 · 우리 선수 추후 지명\n"
                + "\n".join(f"• {line}" for line in pool_lines)
            )
        elif future_pool:
            pool_lines = [
                self._player_term_text(
                    player.get("name", "후보"),
                    int(player.get("rating") or 0),
                    int(player.get("salary") or 0),
                )
                for player in future_pool
            ]
            compensation = (
                "추후 지명 선수 · 상대 구단이 30일 이내 1명 확정\n"
                + "\n".join(f"• {line}" for line in pool_lines)
            )
        elif additional_outgoing_name and cash_from_user > 0:
            compensation = (
                f"상대 요구 · {additional_outgoing_name} + "
                f"현금 {cash_from_user_label}"
            )
        elif additional_outgoing_name:
            compensation = f"상대 요구 선수 · {additional_outgoing_name}"
        elif cash_from_user > 0:
            compensation = f"상대 요구 현금 · {cash_from_user_label}"
        elif additional_name and cash_amount > 0:
            compensation = (
                f"복합 보상 · {additional_name} + 현금 {cash_label}"
            )
        elif additional_name:
            compensation = f"선수 · {additional_name}"
        elif cash_amount > 0:
            compensation = f"현금 · {cash_label}"
        else:
            compensation = "추가 보상 없음"
        if direction == "counterpart" and not compensation.startswith("상대"):
            compensation = f"상대 구단 요구 · {compensation}"
        self.compensation_label.setText(compensation)
        status_labels = {
            "original": "최초 제안 · 상대 구단 답변 대기",
            "reviewing": "원안 유지 · 보상 유형 확인 요청",
            "counter_offer": "수정 제안 도착 · 감독 결정 대기",
            "accepted": "양 구단 조건 합의",
            "rejected": "상대 구단 협상 종료",
        }
        status = str(latest_terms.get("status") or "original")
        summary = str(latest_terms.get("summary") or "선수 1대1 교환")
        self.offer_status_label.setText(
            f"{status_labels.get(status, '조건 검토 중')}\n{summary}"
        )

    @staticmethod
    def _player_term_text(name, rating=0, salary=0, suffix=""):
        details = []
        if int(rating or 0) > 0:
            details.append(f"내부 평가 {int(rating)}")
        if int(salary or 0) > 0:
            details.append(f"연봉 {int(salary):,}만원")
        if suffix:
            details.append(suffix)
        return (
            f"{name}  ·  {' · '.join(details)}"
            if details else str(name)
        )

    def _send_message(self):
        if not self.current_event or self.worker is not None:
            return
        message = self.message_input.toPlainText().strip()
        if len(message) < 5:
            QMessageBox.information(
                self, "단장 의견", "우리 단장에게 전달할 생각을 조금 더 구체적으로 작성하세요."
            )
            return
        if len(message) > 600:
            QMessageBox.information(self, "협상 제안", "한 번의 제안은 600자 이내로 작성하세요.")
            return
        try:
            context = self.event_service.negotiation_context(
                self.save_id, int(self.current_event["id"]), message
            )
        except Exception as error:
            QMessageBox.critical(self, "트레이드 협상 오류", str(error))
            return
        self.message_input.clear()
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.status_label.setText("단장이 감독님의 의견을 상대 구단에 전달하고 있습니다…")
        self.worker = NegotiationWorker(context, self)
        self.worker.response_ready.connect(
            lambda response, text=message: self._receive_response(text, response)
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
            QMessageBox.critical(self, "트레이드 결과 처리 오류", str(error))

    def _response_failed(self, message):
        self.status_label.setText("응답 생성에 실패했습니다. 같은 제안을 다시 보낼 수 있습니다.")
        QMessageBox.warning(self, "트레이드 협상 AI", message)

    def _worker_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        if self.negotiation_data:
            self._render_state()

    def _withdraw(self):
        if not self.current_event:
            return
        answer = QMessageBox.question(
            self, "협상 철회", "이번 트레이드 협상을 최종 철회하시겠습니까?"
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
            QMessageBox.critical(self, "협상 철회 오류", str(error))

    def shutdown_worker(self):
        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        worker.cancel()
        if not worker.wait(1500):
            worker.terminate()
            worker.wait(500)
        self.worker = None
