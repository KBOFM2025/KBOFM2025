"""선수 상세 페이지 안에서 사용하는 FM 스타일 외국인 선수 협상 화면."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


PITCHER_STARTER_ROLES = ("1선발", "2선발", "3선발", "4~5선발")
PITCHER_STARTER_USAGE = (
    "선발 30경기 이상", "선발 25경기 이상", "선발 20경기 이상", "등판 기회 보장 없음",
)
PITCHER_BULLPEN_ROLES = ("마무리", "필승조", "롱릴리프")
PITCHER_BULLPEN_USAGE = ("마무리 우선 기용", "접전 8회 우선", "60경기 이상 등판", "상황별 기용")
HITTER_ROLES = (
    "중심타선(3~5번)", "상위타선(1~2번)", "하위타선(6~9번)", "플래툰 기용", "대타·수비 보강",
)
HITTER_USAGE = (
    "선발 출장 130경기 이상", "선발 출장 110경기 이상", "선발 출장 90경기 이상",
    "상대 투수에 따른 기용", "출장 보장 없음",
)


class ForeignNegotiationPanel(QWidget):
    contract_completed = Signal()

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.service = None
        self.player = {}
        self.context = {}
        self.round_number = 1
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        header = QFrame(objectName="NegotiationHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        title_box = QVBoxLayout()
        eyebrow = QLabel("FOREIGN PLAYER NEGOTIATION", objectName="Eyebrow")
        self.title = QLabel("외국인 선수 계약 협상", objectName="NegotiationTitle")
        self.subtitle = QLabel(objectName="NegotiationMuted")
        title_box.addWidget(eyebrow)
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        self.round_badge = QLabel("ROUND 1 / 4", objectName="RoundBadge")
        self.availability = QLabel(objectName="NegotiationStatus")
        header_layout.addWidget(self.round_badge)
        header_layout.addWidget(self.availability)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(10)

        profile = self._card("선수 · 에이전트 정보", "ProfileCard")
        profile_layout = profile.layout()
        self.player_photo = QLabel(objectName="NegotiationPhoto")
        self.player_photo.setFixedHeight(205)
        self.player_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_photo.setFont(QFont("Malgun Gothic", 30, QFont.Weight.Bold))
        self.player_name = QLabel(objectName="PlayerHeadline")
        self.player_summary = QLabel(objectName="NegotiationBody")
        self.player_summary.setWordWrap(True)
        self.player_tags = QLabel(objectName="PlayerTags")
        self.player_tags.setWordWrap(True)
        demand_box = QFrame(objectName="DemandBox")
        demand_layout = QVBoxLayout(demand_box)
        demand_layout.setContentsMargins(11, 9, 11, 9)
        demand_layout.addWidget(QLabel("에이전트 최초 요구액", objectName="MiniLabel"))
        self.asking = QLabel(objectName="MoneyValue")
        demand_layout.addWidget(self.asking)
        self.budget = QLabel(objectName="NegotiationBody")
        self.budget.setWordWrap(True)
        profile_layout.addWidget(self.player_photo)
        profile_layout.addWidget(self.player_name)
        profile_layout.addWidget(self.player_tags)
        profile_layout.addWidget(self.player_summary)
        profile_layout.addWidget(demand_box)
        profile_layout.addWidget(self.budget)
        profile_layout.addStretch()
        body.addWidget(profile, 25)

        offer_card = self._card("계약 조건 설계", "OfferCard")
        offer_layout = offer_card.layout()
        offer_layout.addWidget(self._section_title("금액 조건", "계약 총액은 KBO 한도에 포함됩니다"))
        money_grid = QGridLayout()
        money_grid.setHorizontalSpacing(8)
        money_grid.setVerticalSpacing(7)
        self.salary = self._money_control(money_grid, 0, "기본 연봉", "보장")
        self.bonus = self._money_control(money_grid, 1, "계약금", "보장")
        self.incentive = self._money_control(money_grid, 2, "성적 인센티브", "변동")
        self.transfer_fee = self._money_control(money_grid, 3, "전 소속팀 이적료", "기타")
        offer_layout.addLayout(money_grid)

        offer_layout.addWidget(self._section_title("기용 계획", "야구 보직과 실제 출장·등판 계획을 약속합니다"))
        role_box = QFrame(objectName="UsageBox")
        role_layout = QVBoxLayout(role_box)
        role_layout.setContentsMargins(12, 10, 12, 10)
        role_grid = QGridLayout()
        role_grid.addWidget(QLabel("예상 보직 / 타순", objectName="FieldLabel"), 0, 0)
        role_grid.addWidget(QLabel("출장·등판 약속", objectName="FieldLabel"), 0, 1)
        self.role = QComboBox()
        self.usage = QComboBox()
        role_grid.addWidget(self.role, 1, 0)
        role_grid.addWidget(self.usage, 1, 1)
        role_layout.addLayout(role_grid)
        self.role_description = QLabel(objectName="RoleDescription")
        self.role_description.setWordWrap(True)
        role_layout.addWidget(self.role_description)
        offer_layout.addWidget(role_box)

        total_line = QFrame(objectName="OfferTotal")
        total_layout = QHBoxLayout(total_line)
        total_layout.setContentsMargins(12, 9, 12, 9)
        total_layout.addWidget(QLabel("이번 제안 총액", objectName="TotalLabel"))
        total_layout.addStretch()
        self.total_value = QLabel("$0", objectName="MoneyValue")
        total_layout.addWidget(self.total_value)
        offer_layout.addWidget(total_line)
        self.cap_progress = QProgressBar(objectName="CapBar")
        self.cap_progress.setRange(0, 100)
        self.cap_progress.setTextVisible(False)
        offer_layout.addWidget(self.cap_progress)
        self.cap_note = QLabel(objectName="NegotiationMuted")
        self.cap_note.setWordWrap(True)
        offer_layout.addWidget(self.cap_note)
        offer_layout.addStretch()
        button_row = QHBoxLayout()
        self.meet_demand = QPushButton("요구액 기준안", objectName="SecondaryAction")
        self.submit = QPushButton("에이전트에게 제안 전달", objectName="PrimaryAction")
        button_row.addWidget(self.meet_demand)
        button_row.addStretch()
        button_row.addWidget(self.submit)
        offer_layout.addLayout(button_row)
        body.addWidget(offer_card, 47)

        agent = self._card("에이전트 협상실", "AgentCard")
        agent_layout = agent.layout()
        identity = QFrame(objectName="AgentIdentity")
        identity_layout = QHBoxLayout(identity)
        avatar = QLabel("AG", objectName="AgentAvatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(44, 44)
        agent_copy = QVBoxLayout()
        agent_copy.addWidget(QLabel("선수 에이전트", objectName="AgentName"))
        agent_copy.addWidget(QLabel("계약 조건과 기용 약속을 함께 검토합니다", objectName="NegotiationMuted"))
        identity_layout.addWidget(avatar)
        identity_layout.addLayout(agent_copy, 1)
        agent_layout.addWidget(identity)
        self.interest = QProgressBar(objectName="InterestBar")
        self.interest.setRange(0, 100)
        self.interest.setValue(50)
        self.interest.setFormat("협상 관심도  %p%")
        agent_layout.addWidget(self.interest)
        agent_layout.addWidget(QLabel("에이전트 답변", objectName="MiniLabel"))
        self.response = QLabel("조건을 제시하면 에이전트의 반응이 여기에 표시됩니다.", objectName="AgentResponse")
        self.response.setWordWrap(True)
        self.response.setMinimumHeight(125)
        self.response.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        agent_layout.addWidget(self.response)
        positive = QLabel("긍정 요소\n  • 높은 보장액\n  • 명확한 보직과 출장 계획", objectName="PositiveBox")
        concern = QLabel("검토 요소\n  • 인센티브 실현 가능성\n  • KBO 신규 선수 개인 한도", objectName="ConcernBox")
        positive.setWordWrap(True)
        concern.setWordWrap(True)
        agent_layout.addWidget(positive)
        agent_layout.addWidget(concern)
        agent_layout.addStretch()
        body.addWidget(agent, 28)
        root.addLayout(body, 1)

        for spin in (self.salary, self.bonus, self.incentive, self.transfer_fee):
            spin.valueChanged.connect(self._update_total)
        self.role.currentTextChanged.connect(self._update_role_description)
        self.usage.currentTextChanged.connect(self._update_role_description)
        self.meet_demand.clicked.connect(self._fill_demand)
        self.submit.clicked.connect(self._submit_offer)
        self.setStyleSheet(self._style())

    def _card(self, title, object_name):
        frame = QFrame(objectName=object_name)
        frame.setProperty("class", "NegotiationCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(9)
        layout.addWidget(QLabel(title, objectName="CardHeading"))
        return frame

    @staticmethod
    def _section_title(title, caption):
        frame = QFrame(objectName="SectionHeading")
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 2, 0, 2)
        row.addWidget(QLabel(title, objectName="SectionTitle"))
        row.addStretch()
        row.addWidget(QLabel(caption, objectName="NegotiationMuted"))
        return frame

    @staticmethod
    def _money_control(grid, row, title, tag):
        frame = QFrame(objectName="MoneyRow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.addWidget(QLabel(title, objectName="FieldLabel"))
        layout.addWidget(QLabel(tag, objectName="ClauseTag"))
        layout.addStretch()
        spin = QSpinBox()
        spin.setRange(0, 4_000_000)
        spin.setSingleStep(10_000)
        spin.setPrefix("$")
        spin.setGroupSeparatorShown(True)
        layout.addWidget(spin)
        grid.addWidget(frame, row, 0)
        return spin

    def set_context(self, service, player, photo_path=None):
        self.service = service
        self.player = dict(player or {})
        self.round_number = 1
        self.round_badge.setText("ROUND 1 / 4")
        self.context = service.negotiation_context(self.player.get("id")) if service else {
            "can_negotiate": False, "reason": "협상 서비스가 연결되지 않았습니다."
        }
        name = self.player.get("name") or "-"
        if photo_path:
            pixmap = QPixmap(str(photo_path))
            self.player_photo.setPixmap(pixmap.scaled(
                250, 198, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.player_photo.setText("")
        else:
            self.player_photo.setPixmap(QPixmap())
            self.player_photo.setText(name[-2:])
        kind_text = "재계약 협상" if self.context.get("kind") == "renew" else "신규 외국인 선수 영입 협상"
        position = self.player.get("primary_position") or self.player.get("pos") or "-"
        nationality = self.player.get("nationality") or self.player.get("career") or "국적 미상"
        self.title.setText(f"{name} 계약 협상")
        self.subtitle.setText(kind_text)
        self.player_name.setText(name)
        self.player_tags.setText(f"{nationality}   |   {position}   |   OVR {self.player.get('overall', '-')} ")
        self.player_summary.setText(
            f"{self.player.get('archetype') or position}\n"
            f"{self.player.get('summary') or self.player.get('source_note') or '스카우팅 보고서가 없습니다.'}"
        )
        asking = int(self.context.get("asking_salary") or 0)
        self.asking.setText(f"${asking:,}")
        self.budget.setText(
            f"구단 한도  ${int(self.context.get('team_cap') or 0):,}\n"
            f"현재 지출  ${int(self.context.get('spent_usd') or 0):,}\n"
            f"가용 금액  ${int(self.context.get('available_usd') or 0):,}"
        )
        can_negotiate = bool(self.context.get("can_negotiate"))
        self.availability.setText(self.context.get("reason") or "협상 가능")
        self.availability.setProperty("available", can_negotiate)
        self.availability.style().unpolish(self.availability)
        self.availability.style().polish(self.availability)
        self.submit.setEnabled(can_negotiate)
        self.meet_demand.setEnabled(can_negotiate)
        maximum = int(self.context.get("max_total") or 0)
        for spin in (self.salary, self.bonus, self.incentive, self.transfer_fee):
            spin.setMaximum(maximum)
        self.cap_note.setText(
            f"이번 협상 최대 제안 가능액 ${maximum:,} · "
            + ("신규 외국인 선수 개인 한도 $1,000,000 적용" if self.context.get("kind") == "sign"
               else "재계약은 구단 계약 총액 $4,000,000 한도 적용")
        )
        self._configure_usage_options()
        self._fill_demand()
        self.response.setText(self.context.get("reason") or "조건을 제시해 주십시오.")
        self.interest.setValue(50 if can_negotiate else 0)

    def _configure_usage_options(self):
        position = self.player.get("primary_position") or self.player.get("pos")
        is_pitcher = self.player.get("position_group") == "P" or self.player.get("pos") == "P" or position in ("SP", "RP")
        existing_role = str(self.player.get("role") or "")
        is_bullpen = position == "RP" or any(
            keyword in existing_role for keyword in ("마무리", "필승조", "불펜", "롱릴리프", "추격조")
        )
        self.role.blockSignals(True)
        self.usage.blockSignals(True)
        self.role.clear()
        self.usage.clear()
        if is_pitcher and not is_bullpen:
            self.role.addItems(PITCHER_STARTER_ROLES)
            self.usage.addItems(PITCHER_STARTER_USAGE)
        elif is_pitcher:
            self.role.addItems(PITCHER_BULLPEN_ROLES)
            self.usage.addItems(PITCHER_BULLPEN_USAGE)
        else:
            self.role.addItems(HITTER_ROLES)
            self.usage.addItems(HITTER_USAGE)
        self.role.blockSignals(False)
        self.usage.blockSignals(False)
        self._update_role_description()

    def _fill_demand(self):
        asking = min(int(self.context.get("asking_salary") or 0), int(self.context.get("max_total") or 0))
        self.salary.setValue(round(asking * 0.75 / 10_000) * 10_000)
        self.bonus.setValue(round(asking * 0.10 / 10_000) * 10_000)
        self.incentive.setValue(max(0, asking - self.salary.value() - self.bonus.value()))
        self.transfer_fee.setValue(0)
        self._update_total()

    def _update_role_description(self):
        role = self.role.currentText()
        usage = self.usage.currentText()
        if not role:
            return
        self.role_description.setText(
            f"기용 합의  |  {role} · {usage}\n"
            "계약 후 감독의 기용 계획과 선수가 기대하는 출전 기회의 기준으로 사용됩니다."
        )

    def _update_total(self):
        total = sum(spin.value() for spin in (self.salary, self.bonus, self.incentive, self.transfer_fee))
        maximum = int(self.context.get("max_total") or 0)
        self.total_value.setText(f"${total:,}")
        over = total > maximum
        self.total_value.setProperty("over", over)
        self.total_value.style().unpolish(self.total_value)
        self.total_value.style().polish(self.total_value)
        self.cap_progress.setValue(min(100, round(total / maximum * 100)) if maximum else 0)

    def _submit_offer(self):
        if not self.service:
            return
        offer = {
            "salary": self.salary.value(), "bonus": self.bonus.value(),
            "incentive": self.incentive.value(), "transfer_fee": self.transfer_fee.value(),
            "role": self.role.currentText(), "usage": self.usage.currentText(),
        }
        result = self.service.submit_negotiation_offer(self.player.get("id"), offer, self.round_number)
        self.interest.setValue(int(result.get("interest") or 0))
        self.response.setText(result.get("message") or "에이전트의 답변이 없습니다.")
        if result.get("accepted"):
            self.submit.setEnabled(False)
            self.meet_demand.setEnabled(False)
            self.round_badge.setText("AGREED")
            QMessageBox.information(self, "계약 완료", result["message"])
            self.contract_completed.emit()
            return
        self.round_number += 1
        self.round_badge.setText(f"ROUND {min(self.round_number, 4)} / 4")
        if result.get("closed"):
            self.round_badge.setText("NEGOTIATION CLOSED")
            self.submit.setEnabled(False)
            self.meet_demand.setEnabled(False)

    def _style(self):
        accent = self.colors.get("accent", "#2884c7")
        return f"""
        QWidget {{ color:#dce6ed; font-family:'Malgun Gothic'; }}
        QFrame#NegotiationHeader {{ background:#111a22; border:1px solid #334552; border-left:4px solid {accent}; border-radius:5px; }}
        QFrame#ProfileCard, QFrame#OfferCard, QFrame#AgentCard {{ background:#171f27; border:1px solid #34434f; border-radius:5px; }}
        QLabel#Eyebrow {{ color:#68b9ea; font-size:9px; font-weight:800; letter-spacing:1px; }}
        QLabel#NegotiationTitle {{ color:white; font-size:21px; font-weight:850; }}
        QLabel#PlayerHeadline {{ color:white; font-size:22px; font-weight:850; }}
        QLabel#NegotiationPhoto {{ color:white; background:#202b34; border:1px solid #40515e; border-radius:4px; }}
        QLabel#CardHeading {{ color:#f4f7f9; border-bottom:1px solid #35434e; padding-bottom:9px; font-size:14px; font-weight:850; }}
        QLabel#SectionTitle {{ color:#79c9f3; font-size:13px; font-weight:850; }}
        QLabel#NegotiationMuted, QLabel#MiniLabel {{ color:#8e9ca7; font-size:10px; }}
        QLabel#NegotiationBody {{ color:#b9c5cd; }}
        QLabel#PlayerTags {{ color:#7bd8aa; background:#102a23; border:1px solid #285843; padding:6px 8px; }}
        QLabel#MoneyValue {{ color:#69d4a3; font-size:18px; font-weight:850; }}
        QLabel#MoneyValue[over="true"] {{ color:#f06b6b; }}
        QLabel#NegotiationStatus, QLabel#RoundBadge {{ padding:7px 11px; border-radius:9px; font-weight:800; }}
        QLabel#RoundBadge {{ color:#81c9ef; background:#142b3a; border:1px solid #2a5a74; }}
        QLabel#NegotiationStatus[available="true"] {{ color:#67dca5; background:#17382d; border:1px solid #2b7156; }}
        QLabel#NegotiationStatus[available="false"] {{ color:#ef8a8a; background:#3c2024; border:1px solid #71353d; }}
        QLabel#FieldLabel {{ color:#dfe8ed; font-weight:750; }}
        QLabel#ClauseTag {{ color:#8ec6e7; background:#1b3443; border:1px solid #31566b; border-radius:7px; padding:2px 6px; font-size:9px; }}
        QLabel#RoleDescription {{ color:#a8d7ee; background:#101a22; border-left:3px solid {accent}; padding:8px; }}
        QLabel#AgentName {{ color:white; font-size:13px; font-weight:800; }}
        QLabel#AgentAvatar {{ color:white; background:{accent}; border-radius:22px; font-weight:900; }}
        QLabel#AgentResponse {{ color:#eef5f8; background:#10171d; border:1px solid #344651; border-left:3px solid {accent}; padding:12px; }}
        QLabel#PositiveBox {{ color:#8ce1b6; background:#122a22; border:1px solid #285640; padding:10px; }}
        QLabel#ConcernBox {{ color:#efbd8d; background:#302218; border:1px solid #654329; padding:10px; }}
        QFrame#DemandBox, QFrame#UsageBox, QFrame#MoneyRow {{ background:#111920; border:1px solid #303f4a; border-radius:3px; }}
        QFrame#OfferTotal {{ background:#0f191f; border:1px solid #3b5260; border-radius:3px; }}
        QLabel#TotalLabel {{ color:white; font-size:13px; font-weight:800; }}
        QSpinBox, QComboBox {{ color:white; background:#242e36; border:1px solid #465762; border-radius:3px; padding:7px; min-width:150px; }}
        QSpinBox:focus, QComboBox:focus {{ border:1px solid {accent}; }}
        QProgressBar {{ color:white; background:#222b32; border:1px solid #3c4953; text-align:center; min-height:21px; }}
        QProgressBar#InterestBar::chunk {{ background:#2da46f; }}
        QProgressBar#CapBar {{ min-height:7px; max-height:7px; border:0; }}
        QProgressBar#CapBar::chunk {{ background:{accent}; }}
        QPushButton {{ padding:9px 14px; border-radius:3px; font-weight:800; }}
        QPushButton#PrimaryAction {{ color:white; background:{accent}; border:1px solid {accent}; }}
        QPushButton#PrimaryAction:hover {{ background:#3a97d1; }}
        QPushButton#SecondaryAction {{ color:#ccd7de; background:#26313a; border:1px solid #46545f; }}
        QPushButton#SecondaryAction:hover {{ color:white; border:1px solid #6b7f8d; }}
        QPushButton:disabled {{ color:#6c7880; background:#20272d; border:1px solid #303a42; }}
        """
