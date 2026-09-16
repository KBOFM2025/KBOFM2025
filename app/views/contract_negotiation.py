"""국내·외국인 선수 계약에 공통으로 쓰는 계약 조건 협상 화면."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from app.player_photos import resolve_player_photo

from app.utils import resource_path


class AgentContractNegotiationWidget(QWidget):
    """사전 협의가 끝난 뒤 계약 조항을 설계하고 서명하는 공통 화면."""

    contract_completed = Signal()

    def __init__(self, colors=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ContractCanvas")
        self.colors = colors or {}
        self.service = None
        self.player = {}
        self.session = {}
        self.photo_path = None
        self._term_cards = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame(objectName="ContractHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(18, 12, 16, 12)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(QLabel("KBO CONTRACT NEGOTIATION", objectName="Eyebrow"))
        self.title = QLabel("선수 계약 협상", objectName="ContractTitle")
        self.subtitle = QLabel(objectName="Muted")
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header_row.addLayout(title_box)
        header_row.addStretch()
        self.step_agent = QLabel("✓  사전 협의", objectName="StepDone")
        self.step_offer = QLabel("2  조건 협상", objectName="StepActive")
        self.step_sign = QLabel("3  계약 서명", objectName="StepIdle")
        for step in (self.step_agent, self.step_offer, self.step_sign):
            header_row.addWidget(step)
        root.addWidget(header)

        self.gate = QFrame(objectName="GateCard")
        gate_box = QVBoxLayout(self.gate)
        gate_box.setContentsMargins(20, 22, 20, 22)
        gate_box.setSpacing(10)
        gate_title = QLabel("에이전트 사전 협의가 필요합니다", objectName="GateTitle")
        gate_text = QLabel(
            "선수 측의 정확한 요구액과 계약 협상 의사를 먼저 확인해야 정식 조건을 제시할 수 있습니다.",
            objectName="GateText",
        )
        gate_text.setWordWrap(True)
        self.gate_contact = QPushButton("에이전트 대화 팝업 열기  ›", objectName="PrimaryAction")
        self.gate_contact.clicked.connect(self._open_agent_popup)
        gate_box.addStretch()
        gate_box.addWidget(gate_title, 0, Qt.AlignmentFlag.AlignHCenter)
        gate_box.addWidget(gate_text, 0, Qt.AlignmentFlag.AlignHCenter)
        gate_box.addWidget(self.gate_contact, 0, Qt.AlignmentFlag.AlignHCenter)
        gate_box.addStretch()
        root.addWidget(self.gate, 1)

        self.negotiation_body = QWidget()
        body = QHBoxLayout(self.negotiation_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self._build_player_panel())
        body.addWidget(self._build_terms_panel(), 1)
        body.addWidget(self._build_summary_panel())
        root.addWidget(self.negotiation_body, 1)
        self.setStyleSheet(self._style())

    def _build_player_panel(self):
        panel = QFrame(objectName="SideCard")
        panel.setFixedWidth(245)
        box = QVBoxLayout(panel)
        box.setContentsMargins(14, 14, 14, 14)
        box.setSpacing(8)
        self.player_photo = QLabel(objectName="PlayerPhoto")
        self.player_photo.setFixedHeight(150)
        self.player_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_name = QLabel("-", objectName="PlayerName")
        self.player_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_meta = QLabel(objectName="PlayerMeta")
        self.player_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_meta.setWordWrap(True)
        box.addWidget(self.player_photo)
        box.addWidget(self.player_name)
        box.addWidget(self.player_meta)

        demand = QFrame(objectName="DemandCard")
        demand_box = QVBoxLayout(demand)
        demand_box.setContentsMargins(11, 10, 11, 10)
        demand_box.setSpacing(5)
        demand_box.addWidget(QLabel("AGENT DEMAND", objectName="Eyebrow"))
        self.demand_total = QLabel("-", objectName="DemandMoney")
        self.demand_breakdown = QLabel(objectName="SmallText")
        self.demand_breakdown.setWordWrap(True)
        demand_box.addWidget(self.demand_total)
        demand_box.addWidget(self.demand_breakdown)
        box.addWidget(demand)

        self.contact_button = QPushButton("사전 협의 내용 다시 보기", objectName="GhostAction")
        self.contact_button.clicked.connect(self._open_agent_popup)
        box.addWidget(self.contact_button)
        box.addWidget(QLabel("규정 · 예산", objectName="SectionCaption"))
        self.rules = QLabel(objectName="RulesText")
        self.rules.setWordWrap(True)
        box.addWidget(self.rules)
        self.budget_progress = QProgressBar(objectName="BudgetProgress")
        self.budget_progress.setRange(0, 100)
        self.budget_progress.setTextVisible(False)
        self.budget_caption = QLabel(objectName="SmallText")
        box.addWidget(self.budget_progress)
        box.addWidget(self.budget_caption)
        box.addStretch()
        return panel

    def _build_terms_panel(self):
        panel = QFrame(objectName="TermsCard")
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(5)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("계약 조건 설계", objectName="SectionTitle"))
        heading.addStretch()
        heading.addWidget(QLabel("금액과 기용 약속을 함께 제안합니다", objectName="Muted"))
        box.addLayout(heading)
        box.addSpacing(4)

        self.years = self._spin(1, 10, 1, 1)
        self.salary = self._spin(0, 4_000_000, 0, 100)
        self.bonus = self._spin(0, 4_000_000, 0, 100)
        self.incentive = self._spin(0, 4_000_000, 0, 10_000)
        self.transfer_fee = self._spin(0, 4_000_000, 0, 10_000)
        self.role = QComboBox()
        self.usage = QComboBox()

        box.addWidget(QLabel("보장 조건", objectName="ClauseGroup"))
        box.addWidget(self._term_card("salary", "기본 연봉", "매 시즌 보장", self.salary))
        box.addWidget(self._term_card("bonus", "계약금", "서명 시 보장", self.bonus))
        box.addWidget(self._term_card("incentive", "성적 인센티브", "조건부 지급", self.incentive))
        box.addWidget(self._term_card("transfer_fee", "전 소속팀 이적료", "선수 수령액 제외", self.transfer_fee))
        box.addWidget(self._term_card("years", "계약 기간", "보장 기간", self.years))

        box.addSpacing(5)
        box.addWidget(QLabel("선수단 지위와 기용 약속", objectName="ClauseGroup"))
        box.addWidget(self._term_card("role", "선수단 역할 / 보직", "계약상 기대 지위", self.role))
        box.addWidget(self._term_card("usage", "출장·등판 계획", "불만 판단의 기준", self.usage))
        self.role_guidance = QLabel(objectName='Muted')
        self.role_guidance.setWordWrap(True)
        box.addWidget(self.role_guidance)
        self.role.currentTextChanged.connect(self._sync_role_usage)
        box.addSpacing(5)

        total = QFrame(objectName="OfferTotalCard")
        total_row = QHBoxLayout(total)
        total_row.setContentsMargins(13, 9, 13, 9)
        total_copy = QVBoxLayout()
        total_copy.addWidget(QLabel("현재 제안 총액", objectName="MiniLabel"))
        self.offer_total = QLabel("-", objectName="OfferMoney")
        total_copy.addWidget(self.offer_total)
        total_row.addLayout(total_copy)
        total_row.addStretch()
        self.gap_label = QLabel("요구안 대비 -", objectName="GapLabel")
        total_row.addWidget(self.gap_label)
        box.addWidget(total)

        box.addStretch(1)
        box.addWidget(QLabel("최근 에이전트 응답", objectName="ClauseGroup"))
        self.transcript = QTextEdit(objectName="Transcript")
        self.transcript.setReadOnly(True)
        self.transcript.setMinimumHeight(90)
        self.transcript.setMaximumHeight(120)
        box.addWidget(self.transcript)
        return panel

    def _build_summary_panel(self):
        panel = QFrame(objectName="SideCard")
        panel.setFixedWidth(270)
        box = QVBoxLayout(panel)
        box.setContentsMargins(14, 14, 14, 14)
        box.setSpacing(9)
        box.addWidget(QLabel("제안 검토", objectName="SectionTitle"))
        self.stage = QLabel("조건 협상", objectName="StatusPill")
        box.addWidget(self.stage)

        fit = QFrame(objectName="FitCard")
        fit_box = QVBoxLayout(fit)
        fit_box.setContentsMargins(11, 10, 11, 10)
        fit_head = QHBoxLayout()
        fit_head.addWidget(QLabel("PLAYER FIT", objectName="Eyebrow"))
        fit_head.addStretch()
        self.fit_grade = QLabel("B", objectName="FitGrade")
        fit_head.addWidget(self.fit_grade)
        fit_box.addLayout(fit_head)
        self.fit_title = QLabel("선수단 적합도 평가", objectName="FitTitle")
        self.fit_traits = QLabel(objectName="SmallText")
        self.fit_traits.setWordWrap(True)
        fit_box.addWidget(self.fit_title)
        fit_box.addWidget(self.fit_traits)
        box.addWidget(fit)

        compare = QFrame(objectName="AnalysisCard")
        compare_box = QVBoxLayout(compare)
        compare_box.setContentsMargins(11, 10, 11, 10)
        compare_box.addWidget(QLabel("요구안 충족 수준", objectName="MiniLabel"))
        self.offer_progress = QProgressBar(objectName="OfferProgress")
        self.offer_progress.setRange(0, 120)
        self.offer_progress.setTextVisible(False)
        compare_box.addWidget(self.offer_progress)
        self.offer_ratio = QLabel("-", objectName="AnalysisValue")
        compare_box.addWidget(self.offer_ratio)
        box.addWidget(compare)

        checklist = QFrame(objectName="AnalysisCard")
        checklist_box = QVBoxLayout(checklist)
        checklist_box.setContentsMargins(11, 10, 11, 10)
        checklist_box.addWidget(QLabel("제안 체크리스트", objectName="MiniLabel"))
        self.money_check = QLabel("● 금액 조건 확인 필요", objectName="CheckText")
        self.role_check = QLabel("● 선수단 역할 확인 필요", objectName="CheckText")
        self.usage_check = QLabel("● 기용 계획 확인 필요", objectName="CheckText")
        for label in (self.money_check, self.role_check, self.usage_check):
            label.setWordWrap(True)
            checklist_box.addWidget(label)
        box.addWidget(checklist)

        self.demand_button = QPushButton("에이전트 요구안 불러오기", objectName="GhostAction")
        self.offer_button = QPushButton("계약 조건 제시", objectName="PrimaryAction")
        self.finalize_button = QPushButton("계약서 서명", objectName="SignAction")
        self.demand_button.clicked.connect(self._fill_demand)
        self.offer_button.clicked.connect(self._submit_offer)
        self.finalize_button.clicked.connect(self._finalize)
        box.addStretch()
        box.addWidget(self.demand_button)
        box.addWidget(self.offer_button)
        box.addWidget(self.finalize_button)
        return panel

    def _term_card(self, key, title, hint, control):
        card = QFrame(objectName="TermCard")
        card.setFixedHeight(48)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(11, 6, 9, 6)
        layout.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(0)
        copy.addWidget(QLabel(title, objectName="TermTitle"))
        copy.addWidget(QLabel(hint, objectName="TermHint"))
        layout.addLayout(copy)
        layout.addStretch()
        if isinstance(control, QSpinBox):
            control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            control.setFixedWidth(185)
            minus = QPushButton("−", objectName="StepButton")
            plus = QPushButton("+", objectName="StepButton")
            minus.setFixedSize(29, 30)
            plus.setFixedSize(29, 30)
            minus.setToolTip(f"{title} 낮추기")
            plus.setToolTip(f"{title} 높이기")
            minus.clicked.connect(control.stepDown)
            plus.clicked.connect(control.stepUp)
            layout.addWidget(control)
            layout.addWidget(minus)
            layout.addWidget(plus)
        else:
            control.setFixedWidth(251)
            layout.addWidget(control)
        self._term_cards[key] = card
        return card

    @staticmethod
    def _spin(minimum, maximum, value, step):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setGroupSeparatorShown(True)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        return spin

    def set_context(self, service, player, photo_path=None):
        self.service = service
        self.player = dict(player or {})
        self.photo_path = photo_path or resolve_player_photo(
            self.player.get("kbo_player_id"),
            self.player.get("name"),
            self.player.get("team"),
        )
        self.session = service.open_agent_talk(self.player.get("id")) if service else {
            "can_negotiate": False, "reason": "협상 서비스가 연결되지 않았습니다.",
            "status": "withdrawn", "fields": (),
        }
        name = self.player.get("name") or self.session.get("player", {}).get("name") or "-"
        self.title.setText(f"{name} 계약 협상")
        self.subtitle.setText(self.session.get("subtitle") or "계약 조건을 협의합니다.")
        self.player_name.setText(name)
        position = self.player.get("primary_position") or self.player.get("pos") or "-"
        self.player_meta.setText(f"{self.player.get('team') or '-'} · {position} · {self.player.get('age') or '-'}세")
        self._set_photo(name)
        self.rules.setText(self.session.get("rules_summary") or "규정 정보 없음")
        self._update_budget_summary()
        self._configure_fields()
        self._set_demand_copy()
        self.transcript.clear()
        if self._contract_ready():
            self._say("에이전트", "사전 협의에서 전달한 요구 조건을 기준으로 정식 제안을 검토하겠습니다.")
        else:
            self._say("안내", "에이전트 사전 협의를 완료해야 계약 조건을 입력할 수 있습니다.")
        self._fill_demand()
        self._apply_status()

    def _set_photo(self, name):
        self.player_photo.setPixmap(QPixmap())
        if self.photo_path:
            pixmap = QPixmap(str(self.photo_path))
            if not pixmap.isNull():
                self.player_photo.setPixmap(pixmap.scaled(
                    215, 146, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self.player_photo.setText("")
                return
        self.player_photo.setText(name[-2:])

    def _configure_fields(self):
        self.role_guidance.setText(self.session.get('role_guidance') or '')
        self.role_guidance.setVisible(bool(self.session.get('role_guidance')))
        visible = set(self.session.get("fields") or ("salary", "bonus", "role", "usage"))
        for key, card in self._term_cards.items():
            card.setVisible(key in visible)
        self.role.clear()
        self.role.addItems(self.session.get("role_options") or ("주전", "로테이션", "백업"))
        self.usage.clear()
        self.usage.addItems(self.session.get("usage_options") or ("기용 보장 없음",))
        self._sync_role_usage()
        self.years.setMaximum(int(self.session.get("max_years") or 1))
        for key in ("salary", "bonus", "incentive", "transfer_fee"):
            spin = getattr(self, key)
            spin.setMaximum(int(self.session.get("max_value") or 4_000_000))
            spin.setSingleStep(int(self.session.get("money_step") or 100))
            spin.setSuffix("만원" if self.session.get("currency") == "KRW_10K" else "")
            spin.setPrefix("$" if self.session.get("currency") == "USD" else "")
        for control in (self.years, self.salary, self.bonus, self.incentive, self.transfer_fee):
            try:
                control.valueChanged.disconnect(self._update_offer_summary)
            except (RuntimeError, TypeError):
                pass
            control.valueChanged.connect(self._update_offer_summary)
        for control in (self.role, self.usage):
            try:
                control.currentTextChanged.disconnect(self._update_offer_summary)
            except (RuntimeError, TypeError):
                pass
            control.currentTextChanged.connect(self._update_offer_summary)

    def _sync_role_usage(self, *_args):
        options = (self.session.get('usage_by_role') or {}).get(self.role.currentText())
        if not options:
            return
        previous = self.usage.currentText()
        self.usage.blockSignals(True)
        self.usage.clear()
        self.usage.addItems(options)
        if previous in options:
            self.usage.setCurrentText(previous)
        self.usage.blockSignals(False)

    def _set_demand_copy(self):
        demand = self._demand_total_value()
        self.demand_total.setText(self._money(demand))
        if self.session.get("currency") == "USD":
            self.demand_breakdown.setText(
                f"연봉 {self._money(self.session.get('asking_salary', 0))}\n"
                f"계약금 {self._money(self.session.get('asking_bonus', 0))} · "
                f"인센티브 {self._money(self.session.get('asking_incentive', 0))}"
            )
        else:
            self.demand_breakdown.setText(
                f"{int(self.session.get('asking_years') or 1)}년 · 연봉 "
                f"{self._money(self.session.get('asking_salary', 0))}\n"
                f"계약금 {self._money(self.session.get('asking_bonus', 0))}"
            )

    def _fill_demand(self):
        self.years.setValue(int(self.session.get("asking_years") or 1))
        for key in ("salary", "bonus", "incentive", "transfer_fee"):
            getattr(self, key).setValue(int(self.session.get(f"asking_{key}") or 0))
        self.role.setCurrentText(self.session.get("desired_role") or self.role.currentText())
        self.usage.setCurrentText(self.session.get("desired_usage") or self.usage.currentText())
        self._update_offer_summary()

    def _open_agent_popup(self):
        if not self.service:
            return
        from app.views.agent_consultation import AgentConsultationDialog
        dialog = AgentConsultationDialog(self.service, self.player, self)
        dialog.exec()
        self.session = self.service.open_agent_talk(self.player.get("id"))
        self._configure_fields()
        self._set_demand_copy()
        if self._contract_ready():
            self._say("에이전트", "사전 협의가 완료됐습니다. 정식 계약 조건을 제시해 주십시오.")
            self._fill_demand()
        self._apply_status()

    def _contract_ready(self):
        return self.session.get("status") in {"ready", "countered", "accepted", "signed"}

    def _offer_payload(self):
        return {
            "years": self.years.value(), "salary": self.salary.value(),
            "bonus": self.bonus.value(), "incentive": self.incentive.value(),
            "transfer_fee": self.transfer_fee.value(), "role": self.role.currentText(),
            "usage": self.usage.currentText(),
        }

    def _offer_total_value(self):
        offer = self._offer_payload()
        salary = offer["salary"] * offer["years"] if self.session.get("currency") == "KRW_10K" else offer["salary"]
        return salary + offer["bonus"] + offer["incentive"] + offer["transfer_fee"]

    def _offer_evaluation_value(self):
        """에이전트가 보는 보장액+조건부 옵션 기대가치."""
        offer = self._offer_payload()
        salary = (
            offer["salary"] * offer["years"]
            if self.session.get("currency") == "KRW_10K"
            else offer["salary"]
        )
        return (
            salary + offer["bonus"] + round(offer["incentive"] * 0.55)
            + offer["transfer_fee"]
        )

    def _demand_total_value(self):
        if self.session.get("currency") == "USD":
            return (
                int(self.session.get("asking_salary") or 0)
                + int(self.session.get("asking_bonus") or 0)
                + round(int(self.session.get("asking_incentive") or 0) * 0.55)
                + int(self.session.get("asking_transfer_fee") or 0)
            )
        return (
            int(self.session.get("asking_salary") or 0) * int(self.session.get("asking_years") or 1)
            + int(self.session.get("asking_bonus") or 0)
            + round(int(self.session.get("asking_incentive") or 0) * 0.55)
        )

    def _update_offer_summary(self, *_args):
        total = self._offer_total_value()
        evaluated = self._offer_evaluation_value()
        demand = self._demand_total_value()
        ratio = round(evaluated / max(1, demand) * 100)
        self.offer_total.setText(self._money(total))
        self.gap_label.setText(f"상대 평가액 기준 {ratio}%")
        self.offer_progress.setValue(min(120, ratio))
        self.offer_ratio.setText(
            f"조건부 옵션 55% 반영 · 에이전트 요구 평가액의 {ratio}%"
        )
        desired_role = self.session.get("desired_role")
        desired_usage = self.session.get("desired_usage")
        self.money_check.setText("● 금액 수준 양호" if ratio >= 95 else "● 금액 조건 조정 필요")
        self.role_check.setText("● 희망 역할 반영" if self.role.currentText() == desired_role else "● 희망 역할과 차이 있음")
        self.usage_check.setText("● 희망 기용 계획 반영" if self.usage.currentText() == desired_usage else "● 기용 기대치와 차이 있음")
        for label, good in (
            (self.money_check, ratio >= 95),
            (self.role_check, self.role.currentText() == desired_role),
            (self.usage_check, self.usage.currentText() == desired_usage),
        ):
            label.setProperty("good", good)
            label.style().unpolish(label)
            label.style().polish(label)
        try:
            overall = float(self.player.get("overall") or 10)
        except (TypeError, ValueError):
            overall = 10.0
        fit_score = min(100, round(overall / 20 * 70))
        fit_score += 15 if self.role.currentText() == desired_role else 4
        fit_score += 15 if self.usage.currentText() == desired_usage else 4
        grade = "A" if fit_score >= 85 else "B" if fit_score >= 70 else "C" if fit_score >= 55 else "D"
        self.fit_grade.setText(grade)
        self.fit_title.setText(f"선수단 적합도 {min(100, fit_score)}점")
        self.fit_traits.setText(
            f"종합 {overall:g} · {self.player.get('age') or '-'}세\n"
            f"희망 역할 {desired_role or '-'}\n기용 기대 {desired_usage or '-'}"
        )

    def _update_budget_summary(self):
        if self.session.get("currency") == "USD":
            spent = int(self.session.get("spent_usd") or 0)
            limit = int(self.session.get("team_cap") or 0)
            self.budget_caption.setText(f"현재 ${spent:,} / 한도 ${limit:,}")
        else:
            cap = self.session.get("salary_cap") or {}
            spent = int(cap.get("current") or 0)
            limit = int(cap.get("limit") or 0)
            self.budget_caption.setText(f"현재 {spent:,}만원 / 상한 {limit:,}만원")
        self.budget_progress.setValue(min(100, round(spent / max(1, limit) * 100)))

    def _submit_offer(self):
        if not self.service:
            return
        offer = self._offer_payload()
        self._say(
            "구단",
            f"{offer['years']}년 · 총액 {self._money(self._offer_total_value())} · "
            f"{offer['role']} · {offer['usage']} 조건을 제안합니다.",
        )
        result = self.service.submit_contract_offer(self.player.get("id"), offer)
        self._say("에이전트", result.get("message") or "선수 측 답변이 없습니다.")
        self.session = self.service.open_agent_talk(self.player.get("id"))
        if result.get("status") == "countered":
            self._set_demand_copy()
            self._fill_demand()
        self._apply_status()

    def _say(self, speaker, message):
        color = "#65b7ec" if speaker == "에이전트" else "#e7f300" if speaker == "구단" else "#9ba5ad"
        self.transcript.append(f"<span style='color:{color}; font-weight:700'>{speaker}</span><br>{message}<br>")

    def _apply_status(self):
        status = self.session.get("status")
        can_negotiate = bool(self.session.get("can_negotiate", True))
        accepted = status == "accepted"
        closed = status in {"withdrawn", "signed"} or not can_negotiate
        ready = self._contract_ready()
        self.step_agent.setText("✓  사전 협의" if ready else "1  사전 협의")
        self.step_agent.setObjectName("StepDone" if ready else "StepActive")
        self.step_offer.setObjectName("StepActive" if ready else "StepIdle")
        self.step_sign.setObjectName("StepIdle")
        self.gate.setVisible(not ready)
        self.negotiation_body.setVisible(ready)
        self.gate_contact.setEnabled(status not in {"signed", "withdrawn"} and can_negotiate)
        self.contact_button.setEnabled(status not in {"signed", "withdrawn"})
        self.demand_button.setEnabled(not closed and not accepted and ready)
        self.offer_button.setEnabled(not closed and not accepted and ready)
        self.finalize_button.setEnabled(accepted)
        if status == "signed":
            self.stage.setText("계약 완료")
            self.step_agent.setObjectName("StepDone")
            self.step_offer.setObjectName("StepDone")
            self.step_sign.setObjectName("StepDone")
        elif status == "withdrawn" or not can_negotiate:
            self.stage.setText("협상 종료")
        elif accepted:
            self.stage.setText("선수 측 수락 · 서명 대기")
            self.step_offer.setObjectName("StepDone")
            self.step_sign.setObjectName("StepActive")
        else:
            self.stage.setText("계약 조건 협상 중")
        for step in (self.step_agent, self.step_offer, self.step_sign):
            step.style().unpolish(step)
            step.style().polish(step)
        self._update_offer_summary()

    def _finalize(self):
        if not self.service:
            return
        success, message = self.service.finalize_contract(self.player.get("id"))
        QMessageBox.information(self, "계약 결과", message)
        self.session = self.service.open_agent_talk(self.player.get("id"))
        self._apply_status()
        if success:
            self.contract_completed.emit()

    def _money(self, value):
        return f"${int(value):,}" if self.session.get("currency") == "USD" else f"{int(value):,}만원"

    def _style(self):
        accent = self.colors.get("accent", "#2f83c5")
        scene = str(resource_path("image", "Scenes", "player_meeting_room.png")).replace("\\", "/")
        return f"""
        QWidget#ContractCanvas {{ background-image:url("{scene}"); background-position:center; background-repeat:no-repeat; }}
        QWidget {{ color:#dce4e9; font-family:'Malgun Gothic'; font-size:14px; }}
        QFrame#ContractHeader {{ background:rgba(18,21,24,235); border:1px solid #30363c; border-left:4px solid #e6f200; border-radius:6px; }}
        QLabel#Eyebrow {{ color:#dce900; font-size:13px; font-weight:900; }}
        QLabel#ContractTitle {{ color:#ffffff; font-size:22px; font-weight:900; }}
        QLabel#Muted, QLabel#TermHint, QLabel#MiniLabel {{ color:#859099; font-size:13px; }}
        QLabel#StepDone, QLabel#StepActive, QLabel#StepIdle {{ padding:8px 11px; border-radius:10px; font-weight:800; }}
        QLabel#StepDone {{ color:#a8df76; background:#1b3324; border:1px solid #31573d; }}
        QLabel#StepActive {{ color:#8bcdf2; background:#17364a; border:1px solid #2c6688; }}
        QLabel#StepIdle {{ color:#77828a; background:#23272b; border:1px solid #343a3f; }}
        QFrame#GateCard {{ background:rgba(18,21,24,238); border:1px solid #30363c; border-radius:7px; }}
        QLabel#GateTitle {{ color:white; font-size:20px; font-weight:900; }}
        QLabel#GateText {{ color:#9da8af; max-width:520px; }}
        QFrame#SideCard, QFrame#TermsCard {{ background:rgba(18,21,24,238); border:1px solid #30363c; border-radius:7px; }}
        QLabel#PlayerPhoto {{ color:#e8f300; background:#22272c; border:1px solid #3a4249; border-radius:5px; font-size:34px; font-weight:900; }}
        QLabel#PlayerName {{ color:white; font-size:18px; font-weight:900; }}
        QLabel#PlayerMeta {{ color:#91a0aa; font-size:13px; }}
        QFrame#DemandCard {{ background:#111416; border:1px solid #343b40; border-left:3px solid #e5f000; border-radius:5px; }}
        QLabel#DemandMoney {{ color:#eaf400; font-size:18px; font-weight:900; }}
        QLabel#SmallText, QLabel#RulesText {{ color:#aab4ba; line-height:140%; }}
        QLabel#SectionCaption {{ color:#8e9aa2; font-size:13px; font-weight:800; padding-top:4px; }}
        QLabel#SectionTitle {{ color:white; font-size:15px; font-weight:900; }}
        QLabel#ClauseGroup {{ color:#dce900; background:#202429; border-left:3px solid #dce900; padding:5px 8px; font-size:13px; font-weight:900; }}
        QFrame#TermCard, QFrame#AnalysisCard {{ background:rgba(14,18,21,225); border:1px solid #2d3439; border-radius:3px; }}
        QFrame#TermCard:hover {{ background:rgba(28,34,39,235); border:1px solid #46525a; }}
        QLabel#TermTitle {{ color:#e9eef1; font-weight:800; }}
        QSpinBox, QComboBox {{ color:white; background:#22282d; border:1px solid #46515a; border-radius:4px; padding:7px 10px; min-height:20px; }}
        QSpinBox:focus, QComboBox:focus {{ border:1px solid {accent}; background:#26323a; }}
        QPushButton#StepButton {{ color:#dce4e8; background:#2b3136; border:1px solid #465058; border-radius:3px; padding:0; font-size:15px; font-weight:900; }}
        QPushButton#StepButton:hover {{ color:#111; background:#e4ef00; border-color:#eef748; }}
        QFrame#OfferTotalCard {{ background:#10202a; border:1px solid #31566d; border-radius:5px; }}
        QLabel#OfferMoney {{ color:#6fc9f6; font-size:19px; font-weight:900; }}
        QLabel#GapLabel {{ color:#b9c5cb; background:#1b303d; border-radius:9px; padding:6px 10px; font-weight:800; }}
        QTextEdit#Transcript {{ color:#dce5e9; background:#101315; border:1px solid #30373c; border-radius:5px; padding:8px; }}
        QLabel#StatusPill {{ color:#8fd0f5; background:#153449; border:1px solid #2b6689; border-radius:9px; padding:8px 10px; font-weight:900; }}
        QProgressBar#OfferProgress {{ background:#292f34; border:0; min-height:7px; max-height:7px; }}
        QProgressBar#OfferProgress::chunk {{ background:{accent}; }}
        QProgressBar#BudgetProgress {{ background:#292f34; border:0; min-height:7px; max-height:7px; }}
        QProgressBar#BudgetProgress::chunk {{ background:#e6ef00; }}
        QFrame#FitCard {{ background:#152719; border:1px solid #315b38; border-radius:6px; }}
        QLabel#FitGrade {{ color:#102113; background:#8fdb58; border-radius:14px; min-width:28px; min-height:28px; font-size:16px; font-weight:900; qproperty-alignment:AlignCenter; }}
        QLabel#FitTitle {{ color:#a8e17e; font-size:15px; font-weight:900; }}
        QLabel#AnalysisValue {{ color:#cbd5da; padding-top:4px; }}
        QLabel#CheckText {{ color:#e6a86f; padding:3px 0; }}
        QLabel#CheckText[good="true"] {{ color:#77d5a3; }}
        QPushButton {{ padding:10px 13px; border-radius:4px; font-weight:900; }}
        QPushButton#PrimaryAction {{ color:white; background:{accent}; border:1px solid #4397d0; }}
        QPushButton#PrimaryAction:hover {{ background:#3b94d2; }}
        QPushButton#SignAction {{ color:#111; background:#e4ef00; border:1px solid #f2fb48; }}
        QPushButton#SignAction:hover {{ background:#f2fb33; }}
        QPushButton#GhostAction {{ color:#cbd6dc; background:#242a2f; border:1px solid #434c53; }}
        QPushButton#GhostAction:hover {{ color:white; border:1px solid #73818a; }}
        QPushButton:disabled {{ color:#626d74; background:#202529; border:1px solid #2d3439; }}
        """
