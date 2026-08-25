"""감독 공식 선임 전에 진행하는 구단 비전과 이사회 목표 협의 화면."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ai.context_builder import governance_profile_for
from app.services.board_confidence import (
    INITIAL_BOARD_CONFIDENCE,
    INITIAL_GM_RELATIONSHIP,
    clamp_relationship,
)
from app.services.governance_engine import GovernanceEngine
from app.services.negotiation_rules import DECISION_LABELS, LEVELS


class ObjectiveCard(QFrame):
    """중요도와 평가 기간이 표시되는 이사회 목표 카드."""

    negotiation_requested = Signal(object)

    def __init__(
        self,
        priority,
        title,
        description,
        period,
        object_name,
        objective_key=None,
        parent=None,
    ):
        super().__init__(parent)
        self.objective_key = objective_key or title
        self.priority = priority
        self.base_priority = priority
        self.title = title
        self.description = description
        self.period = period
        self.base_period = period
        self.selected_level = None
        self.trust_delta = 0
        self.gm_delta = 0
        self.decision = None
        self.conditions = []
        self.response = {}
        self.gm_proposed_level = None
        self.setObjectName(object_name)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(16)

        self.badge = QLabel(priority)
        self.badge.setObjectName("ObjectiveBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedWidth(72)
        layout.addWidget(self.badge)

        text = QVBoxLayout()
        text.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("ObjectiveTitle")
        title_label.setWordWrap(True)
        text.addWidget(title_label)
        description_label = QLabel(description)
        description_label.setObjectName("ObjectiveDescription")
        description_label.setWordWrap(True)
        text.addWidget(description_label)
        layout.addLayout(text, 1)

        actions = QVBoxLayout()
        actions.setSpacing(7)
        self.period_label = QLabel(period)
        self.period_label.setObjectName("ObjectivePeriod")
        self.period_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.period_label)
        self.negotiate_button = QPushButton("단계 선택")
        self.negotiate_button.setObjectName("NegotiateButton")
        self.negotiate_button.setFixedWidth(86)
        self.negotiate_button.clicked.connect(
            lambda: self.negotiation_requested.emit(self)
        )
        actions.addWidget(self.negotiate_button)
        self.result_label = QLabel("미협의")
        self.result_label.setObjectName("NegotiationState")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        actions.addWidget(self.result_label)
        layout.addLayout(actions)

    def apply_negotiation_level(
        self,
        level,
        label,
        trust_delta,
        gm_delta=0,
        decision="accept",
        conditions=None,
        response=None,
    ):
        self.selected_level = level
        self.trust_delta = trust_delta
        self.gm_delta = gm_delta
        self.decision = decision
        self.conditions = list(conditions or [])
        self.response = dict(response or {})
        self.priority = self.base_priority
        self.period = self.base_period
        self.badge.setText(self.base_priority)
        self.period_label.setText(self.base_period)
        decision_label = DECISION_LABELS.get(decision, "합의")
        self.result_label.setText(f"{label} · {decision_label}")
        self.result_label.setProperty(
            "direction",
            "negative" if decision in {"counter_offer", "reject"} else "positive",
        )
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("재협상")

    def stage_level(self, level):
        self.selected_level = level
        self.decision = "pending"
        self.conditions = []
        self.trust_delta = 0
        self.gm_delta = 0
        self.result_label.setText(f"{LEVELS[level]['label']} · 전달 대기")
        self.result_label.setProperty("direction", "")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("단계 변경")

    def set_gm_proposal(self, level):
        self.gm_proposed_level = level
        self.selected_level = level
        self.decision = "proposal"
        self.result_label.setText(f"{LEVELS[level]['label']} · 단장 원안")
        self.result_label.setProperty("direction", "")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("원안 조정")

    def apply_board_review(self, review):
        self.decision = "accept" if review["status"] == "ok" else "counter_offer"
        self.response = {
            **dict(review),
            "reviewed_level": self.selected_level,
        }
        label = "OK" if review["status"] == "ok" else "조정 요청"
        importance = LEVELS[self.selected_level]["label"]
        self.result_label.setText(f"{importance} · {label}")
        self.result_label.setProperty("direction", "positive" if review["status"] == "ok" else "negative")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("승인 완료" if review["status"] == "ok" else "재조정")


class BoardVisionPage(QWidget):
    continue_requested = Signal()

    def __init__(
        self,
        club_name,
        manager_data,
        team_info,
        colors,
        base_team=None,
        gm_objective_defaults=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("BoardVisionPage")
        self.setStyleSheet(self._style(colors))
        self.base_team = base_team or club_name
        self.club_name = club_name
        self.manager_data = manager_data
        self.governance_profile = governance_profile_for(self.base_team)
        self.governance_engine = GovernanceEngine(
            self.governance_profile,
            manager_data=self.manager_data,
        )
        self.selected_objective = None
        self.board_confidence = INITIAL_BOARD_CONFIDENCE
        self.gm_relationship = INITIAL_GM_RELATIONSHIP
        self.objective_cards = []
        self.negotiation_history = []
        self.reviewed = False
        self._ai_worker = None
        self._pending_negotiation = None
        self.gm_objective_defaults = gm_objective_defaults or {}

        manager_name = manager_data.get("manager_name", "무명")
        root = QVBoxLayout(self)
        root.setContentsMargins(42, 30, 42, 32)
        root.setSpacing(18)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("BOARD MEETING  ·  APPOINTMENT NEGOTIATION")
        eyebrow.setObjectName("Eyebrow")
        heading.addWidget(eyebrow)
        title = QLabel("감독 선임 조건 및 구단 비전 협의")
        title.setObjectName("PageTitle")
        title.setFont(QFont("Malgun Gothic", 28, QFont.Bold))
        heading.addWidget(title)
        subtitle = QLabel(
            f"{manager_name} 감독 후보와 {club_name} 이사회가 공식 선임 전에 합의할 평가 기준입니다."
        )
        subtitle.setObjectName("Subtitle")
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        status = QLabel("선임 협의  1 / 1")
        status.setObjectName("MeetingStatus")
        header.addWidget(status, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        rule = QFrame()
        rule.setObjectName("HeaderRule")
        rule.setFixedHeight(2)
        root.addWidget(rule)

        content = QHBoxLayout()
        content.setSpacing(18)

        board = QFrame()
        board.setObjectName("BoardPanel")
        board.setMinimumWidth(280)
        board_layout = QVBoxLayout(board)
        board_layout.setContentsMargins(20, 20, 20, 20)
        board_layout.setSpacing(13)

        board_title = QLabel("이사회 브리핑")
        board_title.setObjectName("PanelTitle")
        board_layout.addWidget(board_title)
        club = QLabel(club_name)
        club.setObjectName("ClubName")
        club.setWordWrap(True)
        board_layout.addWidget(club)
        board_layout.addWidget(
            self._fact("담당 단장", self.governance_profile["general_manager"]["name"])
        )
        board_layout.addWidget(self._fact("홈구장", team_info["stadium"]))
        board_layout.addWidget(self._fact("구단 기반", team_info["parent_company"]))
        board_policy = self.governance_profile.get("board_policy", {})
        window_labels = {
            "all_in": "우승 올인",
            "win_now": "즉시 우승",
            "sustained_contender": "지속 우승권",
            "stable_contender": "안정적 상위권",
            "transition_contender": "경쟁·세대교체",
            "build_and_compete": "육성·성과 병행",
            "balanced": "균형 운영",
            "developing": "코어 육성",
            "rebuild": "리빌딩",
        }
        board_layout.addWidget(
            self._fact(
                "경쟁 국면",
                window_labels.get(
                    board_policy.get("competitive_window"), "균형 운영"
                ),
            )
        )
        board_layout.addWidget(
            self._fact(
                "이사회 추진력",
                self.governance_engine._trait_grade(
                    int(board_policy.get("execution_drive", 10))
                ),
            )
        )

        scorecard_title = QLabel("구단 운영 성향")
        scorecard_title.setObjectName("TraitSectionTitle")
        board_layout.addWidget(scorecard_title)
        scorecard_guide = QLabel("세부 수치는 내부 판정에만 사용되며 성향과 판단 근거만 표시합니다.")
        scorecard_guide.setObjectName("TraitGuide")
        scorecard_guide.setWordWrap(True)
        board_layout.addWidget(scorecard_guide)
        for trait in self.governance_engine.board_scorecard():
            board_layout.addWidget(self._trait_meter(trait))

        evaluation = QLabel(
            "평가 원칙\n\n"
            "• 필수 목표는 감독직 유지에 직접 반영\n"
            "• 중요 목표는 이사회 신뢰도에 큰 영향\n"
            "• 권장 목표는 장기 평가의 보너스 항목\n\n"
            "구단 방향\n"
            f"{board_policy.get('rationale', '구단의 중장기 운영 기준을 따릅니다.')}"
        )
        evaluation.setObjectName("EvaluationNote")
        evaluation.setWordWrap(True)
        board_layout.addWidget(evaluation)
        board_layout.addStretch()
        board_scroll = QScrollArea()
        board_scroll.setObjectName("BoardProfileScroll")
        board_scroll.setWidgetResizable(True)
        board_scroll.setFrameShape(QFrame.Shape.NoFrame)
        board_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        board_scroll.setMinimumWidth(285)
        board_scroll.setMaximumWidth(330)
        board_scroll.setWidget(board)
        content.addWidget(board_scroll)

        scroll = QScrollArea()
        scroll.setObjectName("ObjectiveScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        objectives = QWidget()
        objectives.setObjectName("Objectives")
        objective_layout = QVBoxLayout(objectives)
        objective_layout.setContentsMargins(0, 0, 7, 0)
        objective_layout.setSpacing(10)

        section = QLabel("이사회가 제시한 핵심 목표")
        section.setObjectName("SectionTitle")
        objective_layout.addWidget(section)
        self._add_objective(
            objective_layout,
            ObjectiveCard(
                "필수",
                "이번 시즌 성과",
                team_info["season_goal"],
                "이번 시즌",
                "RequiredObjective",
                objective_key="season_result",
            ),
        )
        self._add_objective(
            objective_layout,
            ObjectiveCard(
                "장기",
                "구단의 장기 비전",
                team_info["long_term_goal"],
                "3시즌",
                "LongTermObjective",
                objective_key="long_term_vision",
            ),
        )
        self._add_objective(
            objective_layout,
            ObjectiveCard(
                "중요",
                "프런트 운영 철학 존중",
                team_info["front_office_style"],
                "상시",
                "ImportantObjective",
                objective_key="front_office_style",
            ),
        )
        self._add_objective(
            objective_layout,
            ObjectiveCard(
                "중요",
                "팬들이 기대하는 구단 정체성 유지",
                team_info["fan_style"],
                "상시",
                "ImportantObjective",
                objective_key="club_identity",
            ),
        )
        self._add_objective(
            objective_layout,
            ObjectiveCard(
                "권장",
                "현재 전력과 내부 성장의 균형",
                "즉시 전력만이 아니라 젊은 선수의 출전 기회와 장기적인 선수단 경쟁력도 함께 관리하십시오.",
                "2시즌",
                "RecommendedObjective",
                objective_key="roster_balance",
            ),
        )

        note = QLabel(
            "목표의 진행도와 이사회 평가는 시즌 중 구단 정보 화면에서 계속 확인할 수 있습니다."
        )
        note.setObjectName("BoardNote")
        note.setWordWrap(True)
        objective_layout.addWidget(note)
        objective_layout.addStretch()
        scroll.setWidget(objectives)
        content.addWidget(scroll, 1)

        negotiation = QFrame()
        negotiation.setObjectName("NegotiationPanel")
        negotiation.setFixedWidth(315)
        negotiation_layout = QVBoxLayout(negotiation)
        negotiation_layout.setContentsMargins(18, 18, 18, 18)
        negotiation_layout.setSpacing(11)
        negotiation_title = QLabel("협의 단계 설정")
        negotiation_title.setObjectName("PanelTitle")
        negotiation_layout.addWidget(negotiation_title)
        self.negotiation_target = QLabel("단계를 설정할 항목을 선택하십시오")
        self.negotiation_target.setObjectName("NegotiationTarget")
        self.negotiation_target.setWordWrap(True)
        negotiation_layout.addWidget(self.negotiation_target)
        self.current_terms = QLabel(
            "1~5단계로 목표 수준을 협의합니다. 구단 방향과 실행 가능성을 종합 평가하며 내부 점수는 공개하지 않습니다."
        )
        self.current_terms.setObjectName("CurrentTerms")
        self.current_terms.setWordWrap(True)
        negotiation_layout.addWidget(self.current_terms)

        self.level_buttons = []
        for level, title in (
            (1, "1단계  ·  대폭 완화"),
            (2, "2단계  ·  일부 완화"),
            (3, "3단계  ·  단장 원안"),
            (4, "4단계  ·  도전 목표"),
            (5, "5단계  ·  최고 목표"),
        ):
            button = QPushButton(title)
            button.setObjectName(f"Level{level}Button")
            button.clicked.connect(
                lambda _checked=False, selected_level=level: self._choose_level(selected_level)
            )
            negotiation_layout.addWidget(button)
            self.level_buttons.append(button)
        for button in self.level_buttons:
            button.setEnabled(False)

        response_title = QLabel("이사회 답변")
        response_title.setObjectName("ResponseTitle")
        negotiation_layout.addWidget(response_title)
        self.board_response = QLabel("아직 이사회에 전달하지 않았습니다.")
        self.board_response.setObjectName("BoardResponse")
        self.board_response.setWordWrap(True)
        self.board_response.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        response_scroll = QScrollArea()
        response_scroll.setObjectName("BoardResponseScroll")
        response_scroll.setWidgetResizable(True)
        response_scroll.setFrameShape(QFrame.Shape.NoFrame)
        response_scroll.setMinimumHeight(150)
        response_scroll.setWidget(self.board_response)
        negotiation_layout.addWidget(response_scroll, 1)
        self.ai_status = QLabel("이사회 즉시 판정 준비")
        self.ai_status.setObjectName("AIStatus")
        self.ai_status.setWordWrap(True)
        negotiation_layout.addWidget(self.ai_status)
        negotiation_layout.addStretch()
        warning = QLabel(
            "이사회는 각 항목에 OK 또는 조정 의견을 회신합니다. "
            "조정 요청을 받은 항목만 다시 선택해 재전달할 수 있습니다."
        )
        warning.setObjectName("NegotiationWarning")
        warning.setWordWrap(True)
        negotiation_layout.addWidget(warning)
        content.addWidget(negotiation)
        root.addLayout(content, 1)

        footer = QHBoxLayout()
        hint = QLabel("5개 목표가 모두 합의되면 공식 선임 발표와 취임 기자회견이 진행됩니다.")
        hint.setObjectName("FooterHint")
        footer.addWidget(hint)
        footer.addStretch()
        self.accept_button = QPushButton("이사회에 5개 안건 전달")
        self.accept_button.setObjectName("AcceptButton")
        self.accept_button.clicked.connect(self._submit_to_board)
        footer.addWidget(self.accept_button)
        root.addLayout(footer)
        self._apply_gm_initial_proposal()

    def _add_objective(self, layout, card):
        card.negotiation_requested.connect(self._select_objective)
        self.objective_cards.append(card)
        layout.addWidget(card)

    def _apply_gm_initial_proposal(self):
        for card in self.objective_cards:
            proposal = self.gm_objective_defaults.get(card.objective_key)
            if not proposal:
                continue
            try:
                level = int(proposal["initial_level"])
            except (KeyError, TypeError, ValueError):
                continue
            if level in LEVELS:
                card.set_gm_proposal(level)
        proposed = sum(card.selected_level is not None for card in self.objective_cards)
        if proposed == len(self.objective_cards):
            gm_name = self.governance_profile["general_manager"]["name"]
            self.ai_status.setText(f"{gm_name} 단장 원안 · 5/5 항목 설정 완료")

    def _select_objective(self, card):
        self.selected_objective = card
        self.negotiation_target.setText(card.title)
        feedback = card.response.get("feedback") if card.response else None
        self.board_response.setText(feedback or "감독님의 단계 선택을 기다리고 있습니다.")
        selected_text = (
            f"\n현재 중요도  ·  {LEVELS[card.selected_level]['label']}"
            if card.selected_level is not None
            else "\n현재 합의  ·  미협의"
        )
        self.current_terms.setText(
            f"현재 중요도  ·  {card.priority}\n"
            f"평가 기간  ·  {card.period}{selected_text}\n\n{card.description}"
        )
        approved = card.decision == "accept"
        for button in self.level_buttons:
            button.setEnabled(not approved and self._ai_worker is None)
        if approved:
            self.board_response.setText(
                feedback or "이 안건은 이사회 승인이 완료되어 확정되었습니다."
            )

    def _choose_level(self, level):
        card = self.selected_objective
        if (
            card is None
            or self._ai_worker is not None
            or card.decision == "accept"
        ):
            return
        card.stage_level(level)
        level_data = LEVELS[level]
        self.current_terms.setText(
            f"선택 중요도 · {level_data['label']} ({level_data['fm_label']})\n"
            f"{level_data['description']}\n\n{card.description}"
        )
        self.board_response.setText("선택을 저장했습니다. 5개 항목을 모두 선택한 뒤 전달하십시오.")
        selected = sum(item.selected_level is not None for item in self.objective_cards)
        self.ai_status.setText(f"전달 준비 · {selected}/5 항목 선택")

    def _submit_to_board(self):
        if self._ai_worker is not None:
            return
        pending_cards = [
            card for card in self.objective_cards
            if card.decision != "accept"
        ]
        if not pending_cards:
            self.continue_requested.emit()
            return
        untouched_adjustments = [
            card for card in pending_cards
            if card.decision == "counter_offer"
        ]
        if untouched_adjustments:
            self.ai_status.setText(
                f"조정 요청 {len(untouched_adjustments)}건의 단계를 변경한 뒤 다시 전달하십시오."
            )
            return
        if any(card.selected_level is None for card in pending_cards):
            self.ai_status.setText(
                f"재검토 대상 {len(pending_cards)}개 항목의 단계를 먼저 선택하십시오."
            )
            return
        self._on_board_review(
            self._instant_board_review_payload(pending_cards)
        )

    def _instant_board_review_payload(self, cards):
        reviews = []
        for card in cards:
            evaluation = self.governance_engine.evaluate_vision_request(
                card, card.selected_level
            )
            fallback = self.governance_engine.fallback_decision(evaluation)
            result = self.governance_engine.resolve_vision_decision(
                evaluation, fallback
            )
            accepted = result["decision"] in {
                "accept", "conditional_accept"
            }
            level_label = LEVELS[int(card.selected_level)]["label"]
            reason_line = "\n".join(f"• {reason}" for reason in evaluation.reasons)
            if result["decision"] == "accept":
                feedback = (
                    f"‘{card.title}’ 안건은 {level_label} 수준으로 "
                    f"추진하는 데 동의합니다.\n{reason_line}"
                )
            elif result["decision"] == "conditional_accept":
                feedback = (
                    f"‘{card.title}’ 안건은 시즌 중간 진행 상황을 "
                    f"재점검하는 조건으로 승인합니다.\n"
                    f"{reason_line}"
                )
            else:
                feedback = (
                    f"‘{card.title}’ 안건은 현재 구단의 기대 수준과 "
                    f"차이가 있어 조정이 필요합니다.\n"
                    f"{reason_line}"
                )
            review = {
                "objective_key": card.objective_key,
                "status": "ok" if accepted else "adjust",
                "feedback": feedback,
                "decision": result["decision"],
                "approval_score": result["approval_score"],
                "preferred_level": evaluation.preferred_level,
                "hard_floor": evaluation.hard_floor,
                "direction_score": result["direction_score"],
                "execution_score": result["execution_score"],
                "manager_fit_score": result["manager_fit_score"],
                "reasons": list(evaluation.reasons),
            }
            if not accepted:
                target = int(result["final_level"])
                target_name = LEVELS[target]["label"]
                if target >= int(card.selected_level):
                    review["required_min_level"] = target
                    review["feedback"] += (
                        f"\n\n이사회는 이 안건을 {target_name} 수준으로 높여 "
                        "다시 제안해 주시길 바랍니다."
                    )
                else:
                    review["required_max_level"] = target
                    review["feedback"] += (
                        f"\n\n현재 여건을 고려해 {target_name} 수준으로 조정한 뒤 "
                        "다시 제안해 주시길 바랍니다."
                    )
            reviews.append(review)
        return {
            "reviews": reviews,
            "source": "instant_board_rules",
        }

    def _on_board_review(self, payload):
        review_source = payload.get("source", "local_ai")
        reviews = {item["objective_key"]: item for item in payload["reviews"]}
        response_lines = []
        for card in self.objective_cards:
            review = reviews.get(card.objective_key)
            if review is None:
                continue
            card.apply_board_review(review)
            status_label = "OK" if review["status"] == "ok" else "조정 요청"
            response_lines.append(
                f"[{status_label}] {card.title}\n{review['feedback']}"
            )
            self.negotiation_history.append({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "objective_key": card.objective_key,
                "requested_level": card.selected_level,
                "decision": card.decision,
                "board_reply": review["feedback"],
                "source": review_source,
            })
        adjustments = [
            card for card in self.objective_cards
            if card.decision != "accept"
        ]
        approved_count = len(self.objective_cards) - len(adjustments)
        review_label = (
            "AI 응답 지연 · 이사회 기준 판정"
            if review_source == "rules_timeout_fallback"
            else "이사회 즉시 판정"
            if review_source == "instant_board_rules"
            else "AI 검토"
        )
        if adjustments:
            self.ai_status.setText(
                f"{review_label} 완료 · 누적 승인 {approved_count} / "
                f"재조정 {len(adjustments)}"
            )
            self.board_response.setText("\n\n".join(response_lines))
            self.accept_button.setText(
                f"조정 {len(adjustments)}건 다시 전달  →"
            )
        else:
            self.ai_status.setText(
                f"{review_label} 완료 · 5개 항목 모두 OK"
            )
            self.board_response.setText(
                "\n\n".join(response_lines)
                + "\n\n이사회가 모든 안건을 승인했습니다. 공식 선임 절차로 이동할 수 있습니다."
            )
            self.accept_button.setText("협의 확정 및 선임 발표  →")
            try:
                self.accept_button.clicked.disconnect()
            except RuntimeError:
                pass
            self.accept_button.clicked.connect(self.continue_requested.emit)
        self._refresh_card_locks()

    def _on_board_review_failed(self, reason):
        print(f"[이사회 AI] 검토 실패 · {reason}", flush=True)
        pending_cards = [
            card for card in self.objective_cards
            if card.decision != "accept" and card.selected_level is not None
        ]
        self._on_board_review(
            self._instant_board_review_payload(pending_cards)
        )

    def _on_ai_decision(self, payload):
        if self._pending_negotiation is None:
            return
        self._apply_negotiation_decision(payload)
        self.ai_status.setText("로컬 AI 응답 · 게임 규칙 검증 완료")

    def _on_ai_failed(self, reason):
        if self._pending_negotiation is None:
            return
        evaluation = self._pending_negotiation["evaluation"]
        fallback = self.governance_engine.fallback_decision(evaluation)
        self._apply_negotiation_decision(fallback)
        self.ai_status.setText("규칙 엔진 응답 · 즉시 적용 완료")

    def _apply_negotiation_decision(self, payload):
        pending = self._pending_negotiation
        if pending is None:
            return
        card = pending["card"]
        evaluation = pending["evaluation"]
        result = self.governance_engine.resolve_vision_decision(evaluation, payload)
        card.apply_negotiation_level(
            result["final_level"],
            result["level_label"],
            result["board_trust_delta"],
            result["gm_relationship_delta"],
            result["decision"],
            result.get("conditions", []),
            result,
        )
        self._recalculate_confidence()
        conditions = result.get("conditions", [])
        condition_text = (
            "\n\n조건\n• " + "\n• ".join(conditions) if conditions else ""
        )
        self.board_response.setText(
            f"단장 의견\n{result['gm_reply']}\n\n"
            f"이사회 답변\n{result['board_reply']}"
            f"{condition_text}"
        )
        self.current_terms.setText(
            f"요청 단계  ·  {result['requested_level']}단계\n"
            f"최종 합의  ·  {result['final_level']}단계 ({result['level_label']})\n"
            f"결정  ·  {DECISION_LABELS[result['decision']]}\n\n"
            "이사회 평가는 내부적으로 반영됩니다."
        )
        self.negotiation_history.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "objective_key": card.objective_key,
                "objective_title": card.title,
                "requested_level": result["requested_level"],
                "final_level": result["final_level"],
                "decision": result["decision"],
                "approval_score": evaluation.approval_score,
                "board_trust_delta": result["board_trust_delta"],
                "gm_relationship_delta": result["gm_relationship_delta"],
                "conditions": conditions,
                "gm_reply": result["gm_reply"],
                "board_reply": result["board_reply"],
                "source": result.get("source", "unknown"),
            }
        )

    def _finish_ai_worker(self):
        worker = self._ai_worker
        self._ai_worker = None
        self._pending_negotiation = None
        self._set_negotiation_busy(False)
        self.accept_button.setEnabled(True)
        if worker is not None:
            worker.deleteLater()

    def _set_negotiation_busy(self, busy):
        for button in self.level_buttons:
            button.setEnabled(
                not busy
                and self.selected_objective is not None
                and self.selected_objective.decision != "accept"
            )
        for card in self.objective_cards:
            card.negotiate_button.setEnabled(
                not busy and card.decision != "accept"
            )

    def _refresh_card_locks(self):
        """승인된 안건은 확정하고 재조정 대상만 다시 선택할 수 있게 한다."""
        for card in self.objective_cards:
            approved = card.decision == "accept"
            card.negotiate_button.setEnabled(
                not approved and self._ai_worker is None
            )
            if approved:
                card.negotiate_button.setText("승인 완료")
        if self.selected_objective is not None:
            approved = self.selected_objective.decision == "accept"
            for button in self.level_buttons:
                button.setEnabled(not approved and self._ai_worker is None)

    def _recalculate_confidence(self):
        self.board_confidence = clamp_relationship(
            INITIAL_BOARD_CONFIDENCE
            + sum(card.trust_delta for card in self.objective_cards)
        )
        self.gm_relationship = clamp_relationship(
            INITIAL_GM_RELATIONSHIP
            + sum(card.gm_delta for card in self.objective_cards)
        )

    def mark_reviewed(self):
        self.reviewed = True

    def export_state(self):
        return {
            "schema_version": 3,
            "base_team": self.base_team,
            "board_confidence": self.board_confidence,
            "gm_relationship": self.gm_relationship,
            "reviewed": self.reviewed,
            "objectives": {
                card.objective_key: {
                    "selected_level": card.selected_level,
                    "trust_delta": card.trust_delta,
                    "gm_delta": card.gm_delta,
                    "decision": card.decision,
                    "conditions": card.conditions,
                    "response": card.response,
                }
                for card in self.objective_cards
                if card.selected_level is not None
            },
            "negotiation_history": list(self.negotiation_history),
        }

    def restore_state(self, state):
        if not state:
            return
        objective_states = state.get("objectives", {})
        state_schema = int(state.get("schema_version", 1))
        for card in self.objective_cards:
            saved = objective_states.get(card.objective_key)
            if not saved:
                continue
            try:
                level = int(saved.get("selected_level"))
            except (TypeError, ValueError):
                continue
            # schema 2에서 잠시 사용했던 4단계 값을 현행 5단계로 복원한다.
            # schema 1은 원래부터 1~5단계였으므로 그대로 유지한다.
            if state_schema == 2:
                level = min(5, max(1, level + 1))
            if level not in LEVELS:
                continue
            card.apply_negotiation_level(
                level,
                LEVELS[level]["label"],
                int(saved.get("trust_delta", 0)),
                int(saved.get("gm_delta", 0)),
                saved.get("decision", "accept"),
                saved.get("conditions", []),
                saved.get("response", {}),
            )
        self.reviewed = bool(state.get("reviewed", False))
        self.negotiation_history = list(state.get("negotiation_history", []))
        self._recalculate_confidence()
        self.board_confidence = clamp_relationship(
            int(state.get("board_confidence", self.board_confidence))
        )
        self.gm_relationship = clamp_relationship(
            int(state.get("gm_relationship", self.gm_relationship))
        )
        adjustments = [
            card for card in self.objective_cards
            if card.decision != "accept"
        ]
        if not adjustments:
            self.accept_button.setText("협의 확정 및 선임 발표  →")
            try:
                self.accept_button.clicked.disconnect()
            except RuntimeError:
                pass
            self.accept_button.clicked.connect(self.continue_requested.emit)
            self.ai_status.setText("저장된 협상 복원 · 5개 항목 모두 승인")
        else:
            approved_count = len(self.objective_cards) - len(adjustments)
            self.accept_button.setText(
                f"조정 {len(adjustments)}건 다시 전달  →"
            )
            self.ai_status.setText(
                f"저장된 협상 복원 · 승인 {approved_count} / 재조정 {len(adjustments)}"
            )
        self._refresh_card_locks()

    @staticmethod
    def _fact(title, value):
        label = QLabel(f"{title}\n{value}")
        label.setObjectName("BoardFact")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _trait_meter(trait):
        card = QFrame()
        card.setObjectName("TraitMeter")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        name = QLabel(trait["key"])
        name.setObjectName("TraitName")
        header.addWidget(name)
        header.addStretch()
        score = QLabel(trait["grade"])
        score.setObjectName("TraitScore")
        score.setProperty("grade", trait["grade"])
        header.addWidget(score)
        layout.addLayout(header)

        description = QLabel(trait["description"])
        description.setObjectName("TraitDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        card.setToolTip(trait["description"])
        return card

    @staticmethod
    def _style(colors):
        return f"""
            QWidget#BoardVisionPage, QWidget#Objectives {{ background-color: #09131f; }}
            QLabel {{ color: #dce6ef; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QLabel#Eyebrow {{ color: {colors['accent_light']}; font-size: 13px; font-weight: 700; }}
            QLabel#PageTitle {{ color: white; }}
            QLabel#Subtitle {{ color: #9badbf; font-size: 15px; }}
            QLabel#MeetingStatus {{ color: #dce6ef; background-color: #14263a; border: 1px solid #354b63; border-radius: 7px; padding: 9px 14px; font-size: 13px; }}
            QFrame#HeaderRule {{ background-color: {colors['accent']}; border: none; }}
            QFrame#BoardPanel {{ background-color: #101e2e; border: 1px solid #30465d; border-radius: 10px; }}
            QScrollArea#BoardProfileScroll {{ background-color: transparent; border: none; }}
            QScrollArea#BoardProfileScroll > QWidget > QWidget {{ background-color: transparent; }}
            QLabel#PanelTitle, QLabel#SectionTitle {{ color: {colors['accent_light']}; font-size: 16px; font-weight: 700; }}
            QLabel#ClubName {{ color: white; border-bottom: 1px solid #30465d; padding-bottom: 12px; font-size: 21px; font-weight: 700; }}
            QLabel#BoardFact {{ color: #e5edf5; background-color: #0c1825; border-radius: 6px; padding: 10px; font-size: 13px; }}
            QLabel#EvaluationNote {{ color: #aebdcb; background-color: #0c1825; border-radius: 7px; padding: 12px; font-size: 12px; }}
            QLabel#TraitSectionTitle {{ color: white; padding-top: 5px; font-size: 14px; font-weight: 700; }}
            QLabel#TraitGuide {{ color: #71869a; font-size: 11px; }}
            QFrame#TraitMeter {{ background-color: #0c1825; border: 1px solid #26394c; border-radius: 6px; }}
            QLabel#TraitName {{ color: #dce6ef; font-size: 12px; font-weight: 700; }}
            QLabel#TraitScore {{ color: {colors['accent_light']}; font-size: 11px; font-weight: 700; }}
            QLabel#TraitScore[grade="최상"] {{ color: #67e8f9; }}
            QLabel#TraitScore[grade="높음"] {{ color: #86efac; }}
            QLabel#TraitScore[grade="낮음"], QLabel#TraitScore[grade="매우 낮음"] {{ color: #fca5a5; }}
            QLabel#TraitDescription {{ color: #8194a6; font-size: 10px; }}
            QScrollArea#ObjectiveScroll {{ background-color: transparent; border: none; }}
            QFrame#RequiredObjective, QFrame#ImportantObjective, QFrame#LongTermObjective, QFrame#RecommendedObjective {{ background-color: #111f2e; border: 1px solid #30465d; border-radius: 9px; }}
            QFrame#RequiredObjective {{ border-left: 5px solid #ef4444; }}
            QFrame#ImportantObjective {{ border-left: 5px solid #f59e0b; }}
            QFrame#LongTermObjective {{ border-left: 5px solid {colors['accent']}; }}
            QFrame#RecommendedObjective {{ border-left: 5px solid #3b82f6; }}
            QLabel#ObjectiveBadge {{ color: white; background-color: #26394c; border-radius: 6px; padding: 7px 5px; font-size: 13px; font-weight: 700; }}
            QLabel#ObjectiveTitle {{ color: white; font-size: 16px; font-weight: 700; }}
            QLabel#ObjectiveDescription {{ color: #afbfce; font-size: 13px; }}
            QLabel#ObjectivePeriod {{ color: #8395a7; font-size: 12px; }}
            QPushButton#NegotiateButton {{ min-height: 30px; padding: 0 10px; color: {colors['accent_light']}; background-color: transparent; border: 1px solid {colors['accent']}; border-radius: 5px; font-size: 12px; }}
            QPushButton#NegotiateButton:hover {{ color: white; background-color: {colors['accent']}; }}
            QLabel#NegotiationState {{ color: #718396; font-size: 11px; }}
            QLabel#NegotiationState[direction="positive"] {{ color: #4ade80; }}
            QLabel#NegotiationState[direction="negative"] {{ color: #f87171; }}
            QLabel#BoardNote {{ color: #91a4b6; background-color: #0e1a27; border: 1px solid #26394c; border-radius: 7px; padding: 12px; font-size: 13px; }}
            QFrame#NegotiationPanel {{ background-color: #101e2e; border: 1px solid {colors['accent']}; border-radius: 10px; }}
            QLabel#NegotiationTarget {{ color: white; border-bottom: 1px solid #30465d; padding-bottom: 10px; font-size: 17px; font-weight: 700; }}
            QLabel#CurrentTerms {{ color: #adbdcb; background-color: #0b1723; border-radius: 7px; padding: 12px; font-size: 12px; }}
            QLabel#ResponseTitle {{ color: {colors['accent_light']}; padding-top: 7px; font-size: 13px; font-weight: 700; }}
            QLabel#BoardResponse {{ color: #d5e0e9; background-color: {colors['card_bg']}; border-left: 3px solid {colors['accent']}; padding: 12px; font-size: 12px; }}
            QScrollArea#BoardResponseScroll {{ background-color: transparent; border: none; }}
            QLabel#AIStatus {{ color: #71869a; font-size: 10px; padding: 2px 1px; }}
            QLabel#NegotiationWarning {{ color: #7f91a3; font-size: 11px; }}
            QPushButton#Level1Button, QPushButton#Level2Button, QPushButton#Level3Button, QPushButton#Level4Button, QPushButton#Level5Button {{ min-height: 40px; font-size: 13px; text-align: left; padding-left: 13px; }}
            QPushButton#Level1Button {{ color: #9fb1c3; border-color: #42566b; }}
            QPushButton#Level2Button {{ color: #7dd3fc; border-color: #2479a5; }}
            QPushButton#Level3Button {{ color: #fcd34d; border-color: #a16207; }}
            QPushButton#Level4Button {{ color: #fdba74; border-color: #c2410c; background-color: #241914; }}
            QPushButton#Level5Button {{ color: #fca5a5; border-color: #b91c1c; background-color: #26151b; }}
            QLabel#FooterHint {{ color: #8497a9; font-size: 13px; }}
            QPushButton#AcceptButton {{ color: white; background-color: {colors['accent']}; border: 1px solid {colors['accent_light']}; border-radius: 8px; padding: 13px 24px; font-size: 15px; font-weight: 700; }}
            QPushButton#AcceptButton:hover {{ background-color: {colors['accent_light']}; }}
        """
