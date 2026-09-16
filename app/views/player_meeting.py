"""구단 면담실 장면 위에서 진행되는 FM 스타일 선수 대화."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils import resource_path
from app.player_photos import resolve_player_photo


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

MEETING_GESTURES = (
    ("calm", "차분하게 말한다"),
    ("empathetic", "고개를 끄덕이며 공감한다"),
    ("encouraging", "미소 지으며 격려한다"),
    ("assertive", "단호한 표정으로 말한다"),
    ("aggressive", "손가락으로 가리키며 경고한다"),
)


def meeting_responses_for(player_reply, current_round=0):
    """선수의 방금 답변에 맞춰 감독 선택지 문장을 구성한다."""
    reply = str(player_reply or "")
    if any(word in reply for word in ("믿기", "못 믿", "확신", "말뿐", "보장")):
        return (
            "내 말을 바로 믿기 어렵다는 점은 이해한다. 무엇이 불안한지 정확히 말해 달라.",
            "말로 끝내지 않겠다. 다음 엔트리 검토일까지 평가 결과를 직접 설명하겠다.",
            "출전을 보장할 수는 없지만 경쟁에서 제외하지 않고 같은 기준으로 평가하겠다.",
            "감독의 결정을 계속 불신한다면 더 이상의 예외는 두기 어렵다.",
            "네가 신뢰할 수 있는 역할과 최소한의 기회가 무엇인지 제안해 달라.",
            "훈련·경기 지표와 경쟁 선수의 수치를 함께 공개해 판단 근거를 보여주겠다.",
            "담당 코치를 포함한 주간 점검으로 약속의 이행 여부를 확인하게 하겠다.",
            "확정되지 않은 출전을 약속하지는 않겠다. 대신 평가 시점과 결과 설명은 지키겠다.",
        )
    if any(word in reply for word in ("구체", "언제", "어떤 기준", "기준", "역할")):
        return MEETING_RESPONSES[1]
    if any(word in reply for word in ("받아들이", "알겠", "노력", "준비", "해보")):
        return MEETING_RESPONSES[3]
    if any(word in reply for word in ("불공정", "왜 저", "납득", "불만", "기회")):
        return MEETING_RESPONSES[2]
    return MEETING_RESPONSES[min(int(current_round), len(MEETING_RESPONSES) - 1)]


def contextualize_meeting_responses(responses, payload):
    """선수 수준·현재 소속에 맞는 수치 목표와 명확한 거절안을 넣는다."""
    result = list(responses)
    squad = str(payload.get("squad") or "2군")
    position = str(payload.get("position") or "")
    appearances = int(payload.get("recent_appearances") or 0)
    if "투수" in position or position in ("P", "SP", "RP", "CP"):
        target = "앞으로 4주 동안 투수 훈련 포인트 40점을 추가로 획득"
        opportunity = "조건을 달성하면 다음 2주 안에 1군 불펜 2경기 등판 기회를 주겠다"
    else:
        target = "앞으로 4주 동안 야수 훈련 포인트 40점을 추가로 획득"
        opportunity = "조건을 달성하면 다음 2주 안에 선발 2경기와 교체 출전 3경기를 보장하겠다"
    if squad == "1군":
        opportunity = "조건을 달성하면 다음 2주 동안 최소 5경기에 기용하겠다"
    if payload.get("broken_promise"):
        result = [
            "이전 면담에서 한 약속을 지키지 못한 것은 내 책임이다. 변명하지 않고 네가 받은 피해부터 듣겠다.",
            f"약속을 다시 막연하게 연장하지 않겠다. {target}하면 {opportunity}. 이 조건을 받아들일 수 있는지 말해 달라.",
            f"최근 30일 출전이 {appearances}경기에 그친 것은 경쟁 선수의 경기력과 팀 일정 때문이었다. 약속을 지키지 못한 판단 근거는 공개하겠다.",
            "이전 약속은 지키지 못했지만 팀보다 개인을 우선 기용할 수는 없다. 추가 출전 보장은 하지 않겠다.",
            "원래 약속한 역할을 즉시 주는 대신 단계적 기용 확대와 역할 변경 중 어느 쪽을 원하는지 협의하자.",
            "약속 기간의 엔트리·선발 기록과 경쟁 선수 성적을 함께 보자. 내 판단이 잘못됐다면 인정하고 바로잡겠다.",
            "담당 코치와 새 목표를 공동 관리하고 매주 진행 상황을 공유하겠다. 이번에는 이행 여부가 기록에 남는다.",
            "깨진 약속을 같은 내용으로 반복하지 않겠다. 출전 보장은 거절하지만 다음 평가일과 판단 이유는 반드시 전달하겠다.",
        ]
    else:
        result[0] = (
            f"최근 30일 동안 {appearances}경기 출전에 그친 데 불만이 있다는 점을 이해한다. "
            "네가 기대하는 역할을 먼저 말해 달라."
        )
        result[1] = f"{target}해라. {opportunity}. 이 목표 수준에 동의하는지 말해 달라."
        result[2] = (
            f"최근 30일 출전은 {appearances}경기였고 현재 경쟁 순위상 즉시 주전 보장은 어렵다. "
            "선발·대타·2군 조정 중 가능한 경로를 설명하겠다."
        )
        result[4] = "원하는 출전 역할과 받아들일 수 있는 최소 기용 수준을 말해 달라. 팀 상황과 맞는 범위에서 협상하자."
        result[5] = "최근 엔트리와 경쟁 선수 기록을 같은 기준으로 비교하자. 판단이 불공정했다면 바로 수정하겠다."
        result[6] = (
            f"담당 코치와 특별 훈련을 진행하되 4주 동안 훈련 포인트 80점을 획득해야 한다. "
            f"달성하면 {opportunity}."
        )
    result[7] = (
        "요구한 출전 보장은 받아들일 수 없다. 현재 경쟁 선수보다 우선할 근거가 부족하다. "
        "다만 위 평가 기준을 충족하면 다음 엔트리 회의에서 다시 검토하고 이유를 직접 설명하겠다."
    )
    return tuple(result)


def adaptive_meeting_choices(responses, payload, player_reply, current_round):
    """직전 선수 반응에 실제로 이어지는 답변만 가변적으로 반환한다."""
    reply = str(player_reply or "")
    if any(word in reply for word in ("너무 높", "부당", "달성하기", "조정")):
        indices = (0, 1, 2, 4, 7)
    elif any(word in reply for word in ("받아들이", "준비하겠습니다", "해보겠습니다", "알겠습니다")):
        indices = (1, 6, 7)
    elif any(word in reply for word in ("믿기", "말뿐", "확신", "약속")) or payload.get("broken_promise"):
        indices = (0, 1, 2, 4, 5, 7)
    elif any(word in reply for word in ("어떤 항목", "기준", "언제까지", "구체")):
        indices = (1, 2, 5, 6, 7)
    elif any(word in reply for word in ("이적", "떠나", "다른 팀")):
        indices = (0, 4, 7)
    elif int(current_round or 0) == 0:
        indices = (0, 1, 2, 4, 7)
    else:
        indices = (0, 1, 2, 4, 5)
    return tuple({
        "text": responses[index],
        "style": MEETING_CHOICE_STYLES[index],
        "source_number": index + 1,
    } for index in indices)


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
        self.issue_label = QLabel()
        self.issue_label.setObjectName("PlayerDetails")
        self.issue_label.setWordWrap(True)
        profile.addWidget(self.issue_label)
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
        self.gesture_combo = QComboBox()
        self.gesture_combo.setObjectName("MeetingGesture")
        for key, label in MEETING_GESTURES:
            self.gesture_combo.addItem(label, key)
        choice_header.addWidget(self.gesture_combo)
        choice_header.addStretch()
        self.round_label = QLabel()
        self.round_label.setObjectName("MeetingRound")
        choice_header.addWidget(self.round_label)
        choices.addLayout(choice_header)
        self.choice_grid = QGridLayout()
        self.choice_grid.setSpacing(8)
        self.choice_buttons = []
        self.current_choices = ()
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
            QLabel#Speaker {{ color: {c['accent_light']}; font-size: 14px; font-weight: 900; }}
            QLabel#Speech {{ color: white; font-size: 15px; font-weight: 700; }}
            QFrame#ProfilePanel {{
                background: rgba(10, 15, 21, 238);
                border: 1px solid rgba(133, 151, 166, 145); border-radius: 9px;
            }}
            QLabel#Portrait {{ background: #252e38; border: 2px solid {c['accent']}; border-radius: 6px; }}
            QLabel#PlayerName {{ font-size: 17px; font-weight: 900; padding-top: 4px; }}
            QLabel#PlayerDetails {{ color: #aebac5; font-size: 14px; }}
            QLabel#Attitude {{ color: {c['accent_light']}; font-weight: 800; padding-top: 8px; }}
            QFrame#ChoicePanel {{
                background: rgba(9, 14, 20, 244);
                border: 1px solid rgba(133, 151, 166, 145); border-radius: 10px;
            }}
            QLabel#ChoiceTitle {{ font-size: 15px; font-weight: 900; }}
            QLabel#MeetingRound, QLabel#MeetingDate {{ color: #a9b4be; font-size: 13px; }}
            QLabel#MeetingStatus {{ color: #7ed7aa; font-weight: 750; }}
            QLabel#MeetingBadge {{
                color: {c['accent_light']}; background: rgba(10, 15, 21, 220);
                border: 1px solid {c['accent']}; border-radius: 5px;
                padding: 6px 10px; font-size: 13px; font-weight: 900;
            }}
            QPushButton#MeetingChoice {{
                color: #e7edf2; background: rgba(31, 40, 50, 238);
                border: 1px solid #3f4b59; border-left: 3px solid #596a7b;
                border-radius: 6px; padding: 9px 13px; text-align: left; font-size: 13px;
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
            QComboBox#MeetingGesture {{
                color: #e7edf2; background: #202a34; border: 1px solid #465665;
                border-radius: 5px; padding: 6px 10px; min-width: 190px;
            }}
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
        severity = int(payload.get("concern_severity") or 1)
        relationship = dict(payload.get("relationship") or {})
        issue = "약속 불이행" if payload.get("broken_promise") else "출전 시간 부족"
        promise = dict(payload.get("latest_promise") or {})
        promise_line = ""
        if promise:
            promise_line = (
                f"\n약속 · {promise.get('status')} / "
                f"{float(promise.get('progress_value') or 0):.0f}"
                f"/{float(promise.get('target_value') or 0):.0f} "
                f"(기한 {promise.get('due_date') or '-'})"
            )
        self.issue_label.setText(
            f"쟁점 · {issue} ({'!' * severity})\n"
            f"위상 · {payload.get('hierarchy') or '-'} / {payload.get('personality') or '-'}\n"
            f"관계 · 신뢰 {int(relationship.get('trust') or 50)} / "
            f"존중 {int(relationship.get('respect') or 50)}{promise_line}"
        )
        self._set_portrait(
            payload.get("kbo_player_id"), payload.get("managed_team"), name
        )
        self._render_state()

    def _set_portrait(self, kbo_player_id, team, name):
        resolved = resolve_player_photo(kbo_player_id, name, team)
        if resolved is not None:
            path = Path(resolved)
        else:
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
        payload = data.get("payload") or {}
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
        current_round = int(state.get("round", 0))
        attitude = (
            "매우 우호적" if score >= 75 else
            "조금 누그러짐" if score >= 60 else
            "신중하게 듣는 중" if score >= 45 else
            "불만이 남아 있음" if score >= 30 else "대화를 끝낼 가능성이 높음"
        )
        self.attitude_label.setText(f"현재 태도 · {attitude}")
        self.round_label.setText(f"대화 {current_round}회 · 상황에 따라 종료")

        response_pool = contextualize_meeting_responses(
            meeting_responses_for(last_counterpart, current_round), payload
        )
        choices = adaptive_meeting_choices(
            response_pool, payload, last_counterpart, current_round
        )
        active = (
            not data.get("resolved")
            and state.get("status") == "active"
            and self.worker is None
        )
        if not active:
            choices = ()
        self.current_choices = choices
        self._rebuild_choice_buttons(choices, active)
        if data.get("resolved"):
            self.status_label.setText(data.get("result_text", "면담이 종료됐습니다."))
        elif state.get("status") == "accepted":
            self.status_label.setText("선수가 감독의 설명을 받아들였습니다.")
        elif state.get("status") == "rejected":
            self.status_label.setText(
                "선수가 면담을 중단했습니다."
                if state.get("ended_by") == "player" else
                "선수와의 면담이 합의 없이 종료됐습니다."
            )
        else:
            self.status_label.setText("답변의 구체성과 태도에 따라 선수의 신뢰가 변합니다.")

    def _rebuild_choice_buttons(self, choices, active):
        while self.choice_grid.count():
            item = self.choice_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.choice_buttons = []
        columns = 2 if len(choices) >= 4 else 1
        for index, choice in enumerate(choices):
            button = QPushButton(
                f"{index + 1}. {choice['style']['tone']}\n{choice['text']}"
            )
            button.setObjectName("MeetingChoice")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(70)
            button.setToolTip(
                f"{choice['style']['intent']}\n\n{choice['text']}"
            )
            button.setEnabled(active)
            button.clicked.connect(
                lambda _checked=False, choice_index=index: self._choose_response(
                    choice_index
                )
            )
            self.choice_buttons.append(button)
            self.choice_grid.addWidget(button, index // columns, index % columns)

    def _choose_response(self, index):
        if self.worker is not None or not self.current_event:
            return
        state = self.negotiation_data["negotiation"]
        choices = getattr(self, "current_choices", ())
        if not choices:
            transcript = state.get("transcript", [])
            last_reply = next((
                turn.get("text", "") for turn in reversed(transcript)
                if turn.get("speaker") == "counterpart"
            ), "")
            response_pool = contextualize_meeting_responses(
                meeting_responses_for(last_reply, state.get("round", 0)),
                self.negotiation_data.get("payload") or {},
            )
            choices = adaptive_meeting_choices(
                response_pool, self.negotiation_data.get("payload") or {},
                last_reply, state.get("round", 0),
            )
        if index < 0 or index >= len(choices):
            return
        selected = choices[index]
        message = selected["text"]
        manager_choice = {
                "number": selected["source_number"],
                **selected["style"],
                "gesture": self.gesture_combo.currentData() or "calm",
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
