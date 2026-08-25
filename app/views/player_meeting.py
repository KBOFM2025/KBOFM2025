"""구단 면담실 장면 위에서 진행되는 FM 스타일 선수 대화."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils import resource_path


MEETING_RESPONSES = (
    (
        "네가 답답함을 느낀 이유부터 듣고 싶다. 네 입장을 충분히 이해한 뒤 함께 해결책을 찾자.",
        "훈련에서 경쟁력을 증명하면 분명히 출전 기회를 주겠다. 평가 기준도 투명하게 공개하겠다.",
        "현재 선수단 경쟁 상황과 네 역할을 솔직히 설명하겠다. 필요한 부분을 함께 보완하자.",
        "기용은 감독의 권한이다. 결정에 불만을 갖기보다 훈련장에서 먼저 증명해야 한다.",
        "네가 생각하는 가장 적합한 역할과 원하는 출전 방식을 먼저 구체적으로 말해 달라.",
        "최근 훈련 기록과 포지션 경쟁 데이터를 함께 보면서 부족한 항목부터 정하자.",
        "담당 코치와 개인 훈련 계획을 만들고 2주 뒤 같은 기준으로 다시 평가하겠다.",
        "당장 출전을 보장할 수는 없다. 다만 경쟁에서 제외된 것은 아니며 기준은 모두에게 같다.",
    ),
    (
        "네가 원하는 역할을 구체적으로 말해 달라. 가능한 부분과 어려운 부분을 분명하게 답하겠다.",
        "다음 훈련 기간에 명확한 평가 기회를 주고, 기준을 충족하면 1군 경쟁에 포함하겠다.",
        "출전만 약속할 수는 없지만 성장 계획과 단계별 목표는 지금 함께 정할 수 있다.",
        "모든 선수가 같은 기준으로 경쟁한다. 특별 대우를 요구한다면 받아들이기 어렵다.",
        "선발, 교체 출전, 2군 조정 가운데 네가 받아들일 수 있는 역할의 우선순위를 말해 달라.",
        "수비·주루·체력·최근 경기력 가운데 두 가지 목표를 정하고 달성 여부로 판단하겠다.",
        "코치진에게 별도 평가를 요청하고 다음 엔트리 검토일에 결과를 직접 설명하겠다.",
        "팀 사정상 지금 역할을 즉시 바꾸기는 어렵다. 약속할 수 있는 범위만 솔직히 말하겠다.",
    ),
    (
        "지금까지의 노력을 인정한다. 코칭스태프와 네 의견을 다시 검토해 가장 맞는 역할을 찾겠다.",
        "수비와 체력 지표를 개선하면 대수비와 선발 기회를 순서대로 제공하겠다.",
        "팀이 필요로 하는 역할과 네 장점을 연결하자. 결과가 나오면 기회도 자연스럽게 늘어난다.",
        "팀보다 개인의 출전만 앞세운다면 더 이상의 면담은 의미가 없다.",
        "현재 역할을 유지하되 특정 상황에서 우선 기용하는 단계적 확대안을 제안하겠다.",
        "최근 기록을 기준으로 경쟁 선수와 같은 표에서 비교하고 부족한 항목을 공개하겠다.",
        "담당 코치의 주간 보고서와 네 의견을 함께 받아 다음 면담에서 역할을 확정하겠다.",
        "현재 경쟁 선수의 경기력이 더 낫다는 판단은 바뀌지 않았다. 뒤집을 기회는 훈련에서 열어두겠다.",
    ),
    (
        "우리의 목표는 같다. 네가 팀에 중요한 선수라는 점을 행동과 계획으로 보여주겠다.",
        "앞으로의 기용 계획을 코치진과 공유하고 약속한 평가 시점에 직접 결과를 설명하겠다.",
        "오늘 정한 목표를 기준으로 다시 면담하자. 그때는 감정이 아니라 기록으로 판단하겠다.",
        "결정은 바뀌지 않는다. 지금 역할을 받아들이지 못한다면 다른 선택도 검토하겠다.",
        "이번 합의는 단계적 기용 확대안으로 정리하겠다. 첫 기회에서 맡을 역할도 미리 알려주겠다.",
        "평가일과 필수 지표를 문서로 남기고 달성하면 다음 엔트리 회의에서 반드시 검토하겠다.",
        "담당 코치와 매주 진행 상황을 확인하고 약속한 날짜에 내가 직접 최종 답변하겠다.",
        "출전 보장은 하지 않겠다. 그러나 공정한 재평가와 결과 설명은 감독으로서 책임지겠다.",
    ),
)

MEETING_CHOICE_STYLES = (
    {
        "tone": "공감과 경청",
        "intent": "선수의 불만과 요구를 먼저 듣고 함께 해결책을 찾는다.",
    },
    {
        "tone": "구체적인 약속",
        "intent": "훈련 과제, 평가 시점, 역할 또는 기회의 조건을 명확히 제시한다.",
    },
    {
        "tone": "현실적인 설명",
        "intent": "현재 경쟁 상황을 숨기지 않되 선수가 준비할 다음 단계를 제시한다.",
    },
    {
        "tone": "강경한 지시",
        "intent": "감독 권한과 팀 결정을 앞세워 선수 요구를 받아들이지 않는다.",
    },
    {
        "tone": "역할 협상",
        "intent": "선수가 원하는 보직과 출전 형태를 확인하고 가능한 범위를 조율한다.",
    },
    {
        "tone": "데이터 기준",
        "intent": "기록과 경쟁 지표를 공개하고 측정 가능한 평가 기준을 제시한다.",
    },
    {
        "tone": "코칭 지원",
        "intent": "담당 코치와 훈련 계획, 재평가 일정을 연결한다.",
    },
    {
        "tone": "솔직한 한계",
        "intent": "보장할 수 없는 요구는 거절하되 공정한 재평가 기회는 남긴다.",
    },
)


class MeetingBackdrop(QWidget):
    """창 비율에 맞춰 면담실 이미지를 검은 여백 없이 크롭한다."""

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap(str(image_path))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#10151b"))
        if self.pixmap.isNull():
            return
        scaled = self.pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - self.width()) // 2
        y = (scaled.height() - self.height()) // 2
        painter.drawPixmap(self.rect(), scaled, scaled.rect().adjusted(x, y, -x, -y))
        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0.0, QColor(4, 8, 13, 80))
        shade.setColorAt(0.52, QColor(4, 8, 13, 20))
        shade.setColorAt(1.0, QColor(4, 8, 13, 175))
        painter.fillRect(self.rect(), shade)


class PlayerMeetingPage(QWidget):
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
            resource_path("image", "Scenes", "player_meeting_room.png")
        )
        root.addWidget(self.scene)
        overlay = QVBoxLayout(self.scene)
        overlay.setContentsMargins(28, 20, 28, 24)
        overlay.setSpacing(12)

        top = QHBoxLayout()
        back = QPushButton("←  수신함")
        back.setObjectName("MeetingBack")
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        badge = QLabel("  PLAYER TALK  ")
        badge.setObjectName("MeetingBadge")
        top.addWidget(badge)
        top.addStretch()
        self.date_label = QLabel()
        self.date_label.setObjectName("MeetingDate")
        top.addWidget(self.date_label)
        overlay.addLayout(top)

        conversation = QHBoxLayout()
        conversation.addStretch(1)
        self.speech_panel = QFrame()
        self.speech_panel.setObjectName("SpeechPanel")
        self.speech_panel.setMaximumHeight(170)
        speech_layout = QVBoxLayout(self.speech_panel)
        speech_layout.setContentsMargins(18, 13, 18, 13)
        self.speaker_label = QLabel()
        self.speaker_label.setObjectName("Speaker")
        speech_layout.addWidget(self.speaker_label)
        self.speech_label = QLabel()
        self.speech_label.setObjectName("Speech")
        self.speech_label.setWordWrap(True)
        self.speech_label.setMinimumHeight(60)
        speech_layout.addWidget(self.speech_label)
        conversation.addWidget(self.speech_panel, 6)

        self.profile_panel = QFrame()
        self.profile_panel.setObjectName("ProfilePanel")
        self.profile_panel.setFixedWidth(238)
        profile = QVBoxLayout(self.profile_panel)
        profile.setContentsMargins(15, 14, 15, 16)
        self.portrait = QLabel()
        self.portrait.setObjectName("Portrait")
        self.portrait.setFixedSize(84, 84)
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile.addWidget(self.portrait, 0, Qt.AlignmentFlag.AlignHCenter)
        self.player_name = QLabel()
        self.player_name.setObjectName("PlayerName")
        self.player_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile.addWidget(self.player_name)
        self.player_details = QLabel()
        self.player_details.setObjectName("PlayerDetails")
        self.player_details.setWordWrap(True)
        profile.addWidget(self.player_details)
        self.attitude_label = QLabel()
        self.attitude_label.setObjectName("Attitude")
        profile.addWidget(self.attitude_label)
        conversation.addWidget(self.profile_panel, 2)
        overlay.addLayout(conversation, 3)
        overlay.addStretch(3)

        choice_panel = QFrame()
        choice_panel.setObjectName("ChoicePanel")
        choice_panel.setMaximumHeight(410)
        choices = QVBoxLayout(choice_panel)
        choices.setContentsMargins(18, 12, 18, 16)
        choices.setSpacing(8)
        choice_header = QHBoxLayout()
        title = QLabel("감독의 답변")
        title.setObjectName("ChoiceTitle")
        choice_header.addWidget(title)
        choice_header.addStretch()
        self.round_label = QLabel()
        self.round_label.setObjectName("MeetingRound")
        choice_header.addWidget(self.round_label)
        choices.addLayout(choice_header)
        self.choice_grid = QGridLayout()
        self.choice_grid.setSpacing(8)
        self.choice_buttons = []
        for index in range(8):
            button = QPushButton()
            button.setObjectName("MeetingChoice")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(70)
            button.clicked.connect(
                lambda _checked=False, choice=index: self._choose_response(choice)
            )
            self.choice_buttons.append(button)
            self.choice_grid.addWidget(button, index // 2, index % 2)
        choices.addLayout(self.choice_grid)
        footer = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("MeetingStatus")
        footer.addWidget(self.status_label, 1)
        stop = QPushButton("면담 종료")
        stop.setObjectName("EndMeeting")
        stop.clicked.connect(self._withdraw)
        footer.addWidget(stop)
        choices.addLayout(footer)
        overlay.addWidget(choice_panel, 4)
        self._apply_style()

    def _apply_style(self):
        c = self.colors
        self.setStyleSheet(f"""
            QLabel {{ color: white; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QFrame#SpeechPanel {{
                background: rgba(10, 15, 21, 235);
                border: 1px solid rgba(133, 151, 166, 150);
                border-left: 4px solid {c['accent_light']}; border-radius: 9px;
            }}
            QLabel#Speaker {{ color: {c['accent_light']}; font-size: 12px; font-weight: 900; }}
            QLabel#Speech {{ color: white; font-size: 15px; font-weight: 700; }}
            QFrame#ProfilePanel {{
                background: rgba(10, 15, 21, 238);
                border: 1px solid rgba(133, 151, 166, 145); border-radius: 9px;
            }}
            QLabel#Portrait {{ background: #252e38; border: 2px solid {c['accent']}; border-radius: 6px; }}
            QLabel#PlayerName {{ font-size: 17px; font-weight: 900; padding-top: 4px; }}
            QLabel#PlayerDetails {{ color: #aebac5; font-size: 12px; }}
            QLabel#Attitude {{ color: {c['accent_light']}; font-weight: 800; padding-top: 8px; }}
            QFrame#ChoicePanel {{
                background: rgba(9, 14, 20, 244);
                border: 1px solid rgba(133, 151, 166, 145); border-radius: 10px;
            }}
            QLabel#ChoiceTitle {{ font-size: 14px; font-weight: 900; }}
            QLabel#MeetingRound, QLabel#MeetingDate {{ color: #a9b4be; font-size: 11px; }}
            QLabel#MeetingStatus {{ color: #7ed7aa; font-weight: 750; }}
            QLabel#MeetingBadge {{
                color: {c['accent_light']}; background: rgba(10, 15, 21, 220);
                border: 1px solid {c['accent']}; border-radius: 5px;
                padding: 6px 10px; font-size: 10px; font-weight: 900;
            }}
            QPushButton#MeetingChoice {{
                color: #e7edf2; background: rgba(31, 40, 50, 238);
                border: 1px solid #3f4b59; border-left: 3px solid #596a7b;
                border-radius: 6px; padding: 9px 13px; text-align: left; font-size: 11px;
            }}
            QPushButton#MeetingChoice:hover {{
                background: rgba(49, 63, 77, 250);
                border-color: {c['accent_light']}; border-left-color: {c['accent_light']};
            }}
            QPushButton#MeetingChoice:disabled {{ color: #737f89; background: rgba(30, 35, 42, 220); }}
            QPushButton#MeetingBack, QPushButton#EndMeeting {{
                color: white; background: rgba(12, 17, 23, 226);
                border: 1px solid rgba(142, 159, 174, 150);
                border-radius: 6px; padding: 7px 14px; font-weight: 750;
            }}
            QPushButton#MeetingBack:hover {{ background: {c['accent']}; }}
            QPushButton#EndMeeting:hover {{ background: #642c31; }}
        """)

    def set_event(self, event):
        self.current_event = event
        self.date_label.setText(str(event.get("event_date", "")).replace("-", "."))
        self.negotiation_data = self.event_service.negotiation_state(
            self.save_id, int(event["id"])
        )
        payload = self.negotiation_data["payload"]
        name = payload.get("player_name", "선수")
        self.player_name.setText(name)
        squad = payload.get("squad", "선수단")
        morale = payload.get("morale", "-")
        self.player_details.setText(
            f"{payload.get('managed_team', '')}\n소속 · {squad}\n현재 사기 · {morale}"
        )
        self._set_portrait(payload.get("managed_team"), name)
        self._render_state()

    def _set_portrait(self, team, name):
        paths = (
            resource_path("image", "Player_Image", str(team or ""), f"{name}.jpg"),
            resource_path("image", "players", "local", str(team or ""), f"{name}.png"),
        )
        path = next((Path(item) for item in paths if Path(item).exists()), None)
        if path is None:
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText("선수")
            return
        pixmap = QPixmap(str(path)).scaled(
            self.portrait.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.portrait.setText("")
        self.portrait.setPixmap(pixmap)

    def _render_state(self):
        data = self.negotiation_data
        state = data["negotiation"]
        transcript = state.get("transcript", [])
        last_counterpart = next(
            (
                turn.get("text", "")
                for turn in reversed(transcript)
                if turn.get("speaker") == "counterpart"
            ),
            data["rule"]["opening"],
        )
        self.speaker_label.setText(self.player_name.text())
        self.speech_label.setText(last_counterpart)
        score = int(state.get("score", 0))
        target = int(state.get("target_score", 65))
        current_round = int(state.get("round", 0))
        max_rounds = int(state.get("max_rounds", 5))
        self.attitude_label.setText(f"신뢰도 {score} · 합의 기준 {target}")
        self.round_label.setText(f"대화 {current_round}/{max_rounds}")

        response_set = MEETING_RESPONSES[
            min(current_round, len(MEETING_RESPONSES) - 1)
        ]
        active = (
            not data.get("resolved")
            and state.get("status") == "active"
            and self.worker is None
        )
        for number, (button, text) in enumerate(
            zip(self.choice_buttons, response_set), start=1
        ):
            tone = MEETING_CHOICE_STYLES[number - 1]["tone"]
            button.setText(f"{number}. {tone}\n{text}")
            button.setToolTip(
                f"{MEETING_CHOICE_STYLES[number - 1]['intent']}\n\n{text}"
            )
            button.setEnabled(active)
        if data.get("resolved"):
            self.status_label.setText(data.get("result_text", "면담이 종료됐습니다."))
        elif state.get("status") == "accepted":
            self.status_label.setText("선수가 감독의 설명을 받아들였습니다.")
        elif state.get("status") == "rejected":
            self.status_label.setText("선수와의 면담이 합의 없이 종료됐습니다.")
        else:
            self.status_label.setText("답변의 구체성과 태도에 따라 선수의 신뢰가 변합니다.")

    def _choose_response(self, index):
        if self.worker is not None or not self.current_event:
            return
        state = self.negotiation_data["negotiation"]
        response_set = MEETING_RESPONSES[
            min(int(state.get("round", 0)), len(MEETING_RESPONSES) - 1)
        ]
        message = response_set[index]
        manager_choice = {
                "number": index + 1,
                **MEETING_CHOICE_STYLES[index],
        }
        try:
            response = self.event_service.rule_based_negotiation_response(
                self.save_id,
                int(self.current_event["id"]),
                message,
                manager_choice,
            )
        except Exception as error:
            QMessageBox.critical(self, "면담 오류", str(error))
            return
        for button in self.choice_buttons:
            button.setEnabled(False)
        self.status_label.setText("선수의 성격·역할·사기를 기준으로 답변을 판정했습니다.")
        self._receive_response(message, response)

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
            QMessageBox.critical(self, "면담 결과 처리 오류", str(error))

    def _response_failed(self, message):
        self.status_label.setText("선수의 응답을 계산하지 못했습니다. 다시 선택할 수 있습니다.")
        QMessageBox.warning(self, "면담 판정", message)

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
            self, "면담 종료", "면담을 지금 종료하시겠습니까?"
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
            QMessageBox.critical(self, "면담 종료 오류", str(error))

    def shutdown_worker(self):
        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        worker.cancel()
        if not worker.wait(1500):
            worker.terminate()
            worker.wait(500)
        self.worker = None
