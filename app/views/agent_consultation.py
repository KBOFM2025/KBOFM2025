"""국내 FA와 외국인 선수에 공통으로 쓰는 FM풍 에이전트 협의 팝업."""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from app.team_assets import set_team_logo
from app.player_photos import resolve_player_photo


class AgentConsultationDialog(QDialog):
    """정식 계약 제안 전에 관심 여부와 정확한 요구 조건만 확인한다."""

    AGENT_NAMES = ("김태성", "박준호", "이현석", "최민재", "정우진", "한도윤")

    def __init__(self, service, player, parent=None):
        super().__init__(parent)
        self.service = service
        self.player = dict(player or {})
        self.session = service.open_agent_talk(self.player.get("id"))
        self.contract_ready = self.session.get("status") in {
            "ready", "countered", "accepted", "signed",
        }
        seed = sum(ord(char) for char in str(self.player.get("id") or self.player.get("name") or "agent"))
        self.agent_name = self.AGENT_NAMES[seed % len(self.AGENT_NAMES)]
        self.setWindowTitle(f"에이전트 원격 대화 · {self.player.get('name', '-')}")
        self.setMinimumSize(980, 700)
        self.resize(1080, 760)
        self.setModal(True)
        self._build_ui()
        self._add_message("에이전트", self._opening_message())
        self._refresh_side_data()
        self._render_choices()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QFrame(objectName="TopBar")
        top.setFixedHeight(54)
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(18, 0, 14, 0)
        channel = QLabel("●", objectName="OnlineDot")
        title = QLabel("원격 대화", objectName="PopupTitle")
        subject = QLabel(f"— {self.player.get('name', '-')} 에이전트 협의", objectName="PopupSubject")
        self.status_label = QLabel("사전 조건 확인", objectName="PopupStatus")
        close = QPushButton("대화 종료", objectName="CloseButton")
        close.clicked.connect(self.reject)
        top_row.addWidget(channel)
        top_row.addWidget(title)
        top_row.addWidget(subject)
        top_row.addStretch()
        top_row.addWidget(self.status_label)
        top_row.addSpacing(8)
        top_row.addWidget(close)
        root.addWidget(top)

        content = QFrame(objectName="Content")
        body = QHBoxLayout(content)
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(10)
        body.addWidget(self._build_agent_panel())
        body.addWidget(self._build_conversation_panel(), 1)
        body.addWidget(self._build_club_panel())
        root.addWidget(content, 1)
        self.setStyleSheet(self._style())

    def _build_agent_panel(self):
        panel = QFrame(objectName="SidePanel")
        panel.setFixedWidth(224)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)

        avatar = QLabel("AG", objectName="AgentAvatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(86, 86)
        name = QLabel(self.agent_name, objectName="SideName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        role = QLabel("등록 선수 에이전트", objectName="SideRole")
        role.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(name)
        layout.addWidget(role)

        relation = QFrame(objectName="RelationCard")
        relation_box = QVBoxLayout(relation)
        relation_box.setContentsMargins(10, 9, 10, 9)
        relation_box.setSpacing(5)
        relation_box.addWidget(QLabel("구단과의 관계", objectName="MiniCaption"))
        self.relation_text = QLabel("업무적인 관계", objectName="RelationText")
        relation_box.addWidget(self.relation_text)
        self.relation_bar = QProgressBar(objectName="RelationBar")
        self.relation_bar.setRange(0, 100)
        self.relation_bar.setTextVisible(False)
        relation_box.addWidget(self.relation_bar)
        layout.addWidget(relation)

        layout.addWidget(QLabel("에이전트의 고객", objectName="SectionCaption"))
        client = QFrame(objectName="ClientCard")
        client_box = QVBoxLayout(client)
        client_box.setContentsMargins(10, 10, 10, 10)
        client_box.setSpacing(8)
        client_head = QHBoxLayout()
        self.player_photo = QLabel(objectName="PlayerPhoto")
        self.player_photo.setFixedSize(54, 54)
        self.player_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_player_photo()
        player_copy = QVBoxLayout()
        player_name = QLabel(self.player.get("name") or "-", objectName="ClientName")
        player_name.setWordWrap(True)
        position = self.player.get("primary_position") or self.player.get("pos") or "포지션 미상"
        player_meta = QLabel(f"{self.player.get('age') or '-'}세 · {position}", objectName="ClientMeta")
        player_copy.addWidget(player_name)
        player_copy.addWidget(player_meta)
        client_head.addWidget(self.player_photo)
        client_head.addLayout(player_copy, 1)
        client_box.addLayout(client_head)
        line = QFrame(objectName="Divider")
        line.setFixedHeight(1)
        client_box.addWidget(line)
        client_box.addWidget(QLabel("현재 확인된 요구", objectName="MiniCaption"))
        self.demand_value = QLabel("에이전트에게 문의 필요", objectName="DemandValue")
        self.demand_value.setWordWrap(True)
        client_box.addWidget(self.demand_value)
        layout.addWidget(client)
        layout.addStretch()
        return panel

    def _build_club_panel(self):
        panel = QFrame(objectName="SidePanel")
        panel.setFixedWidth(210)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)
        club = self.service.team if hasattr(self.service, "team") else "우리 구단"
        logo_shell = QFrame(objectName="ClubLogoShell")
        logo_shell.setFixedSize(90, 90)
        logo_box = QVBoxLayout(logo_shell)
        logo_box.setContentsMargins(8, 8, 8, 8)
        logo = QLabel()
        set_team_logo(logo, club, 70, 62)
        logo_box.addWidget(logo)
        club_name = QLabel(club, objectName="SideName")
        club_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        club_name.setWordWrap(True)
        role = QLabel("감독 · 계약 결정권자", objectName="SideRole")
        role.setAlignment(Qt.AlignmentFlag.AlignCenter)
        role.setWordWrap(True)
        layout.addWidget(logo_shell, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(club_name)
        layout.addWidget(role)
        layout.addSpacing(12)
        brief = QFrame(objectName="ClubBrief")
        brief_box = QVBoxLayout(brief)
        brief_box.setContentsMargins(11, 10, 11, 10)
        brief_box.addWidget(QLabel("이번 대화의 목적", objectName="MiniCaption"))
        purpose = QLabel(
            "• 선수 측 관심 확인\n• 정확한 요구액 파악\n• 정식 협상 초대 결정",
            objectName="BriefText",
        )
        purpose.setWordWrap(True)
        brief_box.addWidget(purpose)
        layout.addWidget(brief)
        layout.addStretch()
        return panel

    def _build_conversation_panel(self):
        center = QFrame(objectName="ConversationPanel")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(10)
        context = QFrame(objectName="ContextCard")
        context_box = QVBoxLayout(context)
        context_box.setContentsMargins(13, 10, 13, 10)
        context_box.setSpacing(3)
        context_box.addWidget(QLabel("PRE-CONTRACT CONVERSATION", objectName="Eyebrow"))
        self.context_label = QLabel(self._context_text(), objectName="ContextText")
        self.context_label.setWordWrap(True)
        context_box.addWidget(self.context_label)
        center_layout.addWidget(context)

        self.scroll = QScrollArea(objectName="ChatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_body = QWidget(objectName="ChatBody")
        self.chat_layout = QVBoxLayout(self.chat_body)
        self.chat_layout.setContentsMargins(2, 4, 2, 4)
        self.chat_layout.setSpacing(9)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.chat_body)
        center_layout.addWidget(self.scroll, 1)

        self.choice_box = QFrame(objectName="ChoiceBox")
        self.choice_layout = QVBoxLayout(self.choice_box)
        self.choice_layout.setContentsMargins(9, 9, 9, 9)
        self.choice_layout.setSpacing(6)
        center_layout.addWidget(self.choice_box)
        return center

    def _set_player_photo(self):
        photo_path = self._player_photo_path()
        if photo_path:
            pixmap = QPixmap(str(photo_path))
            self.player_photo.setPixmap(pixmap.scaled(
                QSize(52, 52), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
            return
        name = str(self.player.get("name") or "선수")
        self.player_photo.setText(name[-2:])

    def _player_photo_path(self):
        return resolve_player_photo(
            self.player.get("kbo_player_id"),
            self.player.get("name"),
            self.player.get("team"),
        )

    def _opening_message(self):
        if self.session.get("status") == "signed":
            return "이미 계약서 서명까지 완료됐습니다."
        if self.session.get("status") == "withdrawn":
            return "현재 선수 측은 구단과의 사전 협의를 이어갈 의사가 없습니다."
        if self.session.get("demand_revealed"):
            return self.session.get("demand_message") or "앞서 전달한 요구 조건을 다시 확인해 주십시오."
        return self.session.get("initial_message") or "선수에 대한 구단의 관심 내용을 듣겠습니다."

    def _context_text(self):
        detail = self.session.get("subtitle") or "선수 계약 사전 협의"
        return f"{self.player.get('name', '-')} · {detail}  |  여기서는 계약을 체결하지 않고 선수 측 요구와 협상 의사만 확인합니다."

    def _clear_choices(self):
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _choice(self, text, action, primary=False, danger=False):
        button = QPushButton(f"  {text}    ›")
        button.setObjectName("DangerChoice" if danger else "PrimaryChoice" if primary else "DialogueChoice")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(42)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda: self._choose(action, text))
        self.choice_layout.addWidget(button)

    def _choice_heading(self, text):
        heading = QLabel(text, objectName="ChoiceHeading")
        self.choice_layout.addWidget(heading)

    def _render_choices(self):
        self._clear_choices()
        status = self.session.get("status")
        self._choice_heading("지금 할 말")
        if status in {"signed", "withdrawn"}:
            self._choice("대화를 마칩니다.", "close")
            return
        if status in {"ready", "countered", "accepted"}:
            self.status_label.setText("계약 협상 가능")
            self._choice("정식 계약 조건 협상으로 이동하겠습니다.", "proceed", True)
            self._choice("요구 조건을 다시 설명해 주십시오.", "terms")
            self._choice("지금은 대화를 마치겠습니다.", "close")
            return
        if not self.session.get("demand_revealed"):
            self.status_label.setText("요구 조건 미확인")
            self._choice("선수가 원하는 정확한 계약 기간과 금액을 알려주십시오.", "terms", True)
            self._choice("우리 구단이 생각하는 보직과 기용 계획부터 설명하겠습니다.", "plan")
            self._choice("검토할 시간이 필요합니다. 나중에 다시 연락하겠습니다.", "later")
            self._choice("현재는 이 선수와 계약을 추진하지 않겠습니다.", "reject", danger=True)
            return
        self.status_label.setText("요구 조건 파악 완료")
        self._choice("선수를 정식 계약 협상에 초대하겠습니다.", "invite", True)
        if "plan" not in self.session.get("discussed_actions", []):
            self._choice("계약 제안 전에 보직과 기용 계획을 전달하겠습니다.", "plan")
        self._choice("검토할 시간이 필요합니다. 지금은 대화를 마치겠습니다.", "later")
        self._choice("조건이 맞지 않아 계약을 추진하지 않겠습니다.", "reject", danger=True)

    def _choose(self, action, manager_text):
        if action == "close":
            self.reject()
            return
        if action == "proceed":
            self.contract_ready = True
            self.accept()
            return
        self._add_message("감독", manager_text)
        reply = self.service.agent_message(self.player.get("id"), action)
        self._add_message("에이전트", reply)
        self.session = self.service.open_agent_talk(self.player.get("id"))
        self._refresh_side_data()
        if action == "invite" and self.session.get("status") == "ready":
            self.contract_ready = True
        if action == "later":
            self.reject()
            return
        self._render_choices()

    def _refresh_side_data(self):
        interest = int(self.session.get("interest") or 50)
        self.relation_bar.setValue(interest)
        self.relation_text.setText(
            "매우 긍정적" if interest >= 80 else "긍정적인 관계" if interest >= 60
            else "업무적인 관계" if interest >= 40 else "신중한 관계"
        )
        if self.session.get("demand_revealed"):
            if self.session.get("currency") == "USD":
                self.demand_value.setText(f"총액 ${int(self.session.get('asking_total') or 0):,}")
            else:
                years = int(self.session.get("asking_years") or 1)
                salary = int(self.session.get("asking_salary") or 0)
                bonus = int(self.session.get("asking_bonus") or 0)
                self.demand_value.setText(f"{years}년 · 연봉 {salary:,}만원\n계약금 {bonus:,}만원")
        else:
            self.demand_value.setText("에이전트에게 문의 필요")

    def _add_message(self, speaker, text):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        bubble = QLabel(f"<b>{speaker}</b><br><span style='line-height:130%'>{text}</span>")
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(555)
        bubble.setMinimumWidth(290)
        bubble.setObjectName("ManagerBubble" if speaker == "감독" else "AgentBubble")
        if speaker == "감독":
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch()
        self.chat_layout.addWidget(row)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    @staticmethod
    def _style():
        return """
        QDialog { background:#111315; color:#edf1f4; font-family:'Malgun Gothic'; font-size:14px; }
        QFrame#TopBar { background:#181a1d; border-bottom:1px solid #30343a; }
        QLabel#OnlineDot { color:#e7f500; font-size:18px; }
        QLabel#PopupTitle { color:#e7f500; font-size:15px; font-weight:900; }
        QLabel#PopupSubject { color:#aeb5bc; font-size:14px; }
        QLabel#PopupStatus { color:#dce2e6; background:#25292d; border:1px solid #3a3f45; border-radius:11px; padding:6px 11px; }
        QPushButton#CloseButton { color:#f4f5f6; background:#25282c; border:1px solid #aeb3b7; padding:7px 13px; border-radius:5px; font-weight:700; }
        QPushButton#CloseButton:hover { background:#363b40; }
        QFrame#Content { background:#111315; }
        QFrame#SidePanel { background:#181a1c; border:1px solid #292d31; border-radius:7px; }
        QLabel#AgentAvatar { color:#0c0d0e; background:#e8f300; border:3px solid #f5ff26; border-radius:43px; font-size:22px; font-weight:900; }
        QFrame#ClubLogoShell { background:#222529; border:2px solid #e8f300; border-radius:45px; }
        QLabel#SideName { color:#ffffff; font-size:15px; font-weight:900; }
        QLabel#SideRole { color:#60aee5; font-size:13px; }
        QLabel#SectionCaption, QLabel#ChoiceHeading { color:#aeb5bb; font-size:13px; font-weight:800; }
        QLabel#MiniCaption { color:#777f87; font-size:13px; }
        QFrame#RelationCard, QFrame#ClientCard, QFrame#ClubBrief { background:#141618; border:1px solid #292d31; border-radius:5px; }
        QLabel#RelationText { color:#dce5ea; font-weight:700; }
        QProgressBar#RelationBar { background:#292d31; border:0; min-height:5px; max-height:5px; }
        QProgressBar#RelationBar::chunk { background:#9ed755; }
        QLabel#PlayerPhoto { color:#e9f400; background:#292d31; border:1px solid #4a5056; border-radius:27px; font-weight:900; }
        QLabel#ClientName { color:#f0f3f5; font-weight:900; }
        QLabel#ClientMeta { color:#8f989f; font-size:13px; }
        QFrame#Divider { background:#303438; border:0; }
        QLabel#DemandValue { color:#e9f400; font-size:13px; font-weight:800; }
        QLabel#BriefText { color:#b8c0c6; line-height:145%; }
        QFrame#ConversationPanel { background:#1a1c1f; border:1px solid #2b2f34; border-radius:7px; }
        QFrame#ContextCard { background:#23262a; border:1px solid #31363b; border-radius:6px; }
        QLabel#Eyebrow { color:#e6f300; font-size:13px; font-weight:900; }
        QLabel#ContextText { color:#c5cbd0; font-size:13px; }
        QScrollArea#ChatScroll, QWidget#ChatBody { background:transparent; border:0; }
        QLabel#AgentBubble { color:#ecf0f2; background:#292c30; border:1px solid #33383d; border-radius:7px; padding:12px 14px; }
        QLabel#ManagerBubble { color:#ffffff; background:#245fa8; border:1px solid #3476c6; border-radius:7px; padding:12px 14px; }
        QFrame#ChoiceBox { background:#222529; border:1px solid #30353a; border-radius:7px; }
        QPushButton#DialogueChoice, QPushButton#PrimaryChoice, QPushButton#DangerChoice { color:white; text-align:left; padding:9px 12px; border:0; border-radius:4px; }
        QPushButton#DialogueChoice { background:#2461a9; }
        QPushButton#PrimaryChoice { background:#2e76c9; border-left:3px solid #e8f300; font-weight:900; }
        QPushButton#DangerChoice { color:#d5d9dc; background:#34383c; }
        QPushButton#DialogueChoice:hover, QPushButton#PrimaryChoice:hover { background:#3a86da; }
        QPushButton#DangerChoice:hover { color:white; background:#6a3439; }
        QScrollBar:vertical { background:#181a1c; width:8px; margin:0; }
        QScrollBar::handle:vertical { background:#454b50; min-height:24px; border-radius:4px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        """
