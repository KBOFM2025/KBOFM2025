"""신임 감독이 취임 직후 확인하는 구단 비전과 이사회 목표 화면."""

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

from app.ai.context_builder import (
    build_board_submission_context,
    build_vision_context,
    governance_profile_for,
)
from app.ai.local_model import local_ai_enabled
from app.ai.worker import BoardReviewWorker, VisionDecisionWorker
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
        self.result_label.setText(f"{level}단계 · {label} · {decision_label}")
        self.result_label.setProperty("direction", "negative" if level < 3 else "positive")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("재협상")

    def stage_level(self, level):
        self.selected_level = level
        self.decision = "pending"
        self.conditions = []
        self.response = {}
        self.trust_delta = 0
        self.gm_delta = 0
        self.result_label.setText(f"{level}단계 · 전달 대기")
        self.result_label.setProperty("direction", "")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("단계 변경")

    def set_gm_proposal(self, level):
        self.gm_proposed_level = level
        self.selected_level = level
        self.decision = "proposal"
        self.result_label.setText(f"{level}단계 · 단장 원안")
        self.result_label.setProperty("direction", "")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("원안 조정")

    def apply_board_review(self, review):
        self.decision = "accept" if review["status"] == "ok" else "counter_offer"
        self.response = dict(review)
        label = "OK" if review["status"] == "ok" else "조정 요청"
        self.result_label.setText(f"{self.selected_level}단계 · {label}")
        self.result_label.setProperty("direction", "positive" if review["status"] == "ok" else "negative")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.negotiate_button.setText("확인" if review["status"] == "ok" else "재조정")


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
        self.governance_engine = GovernanceEngine(self.governance_profile)
        self.selected_objective = None
        self.board_confidence = INITIAL_BOARD_CONFIDENCE
        self.gm_relationship = INITIAL_GM_RELATIONSHIP
        self.objective_cards = []
        self.negotiation_history = []
        self.reviewed = False
        self._ai_worker = None
        self._pending_negotiation = None
        self.local_ai_enabled = local_ai_enabled()
        self.gm_objective_defaults = gm_objective_defaults or {}

        manager_name = manager_data.get("manager_name", "무명")
        root = QVBoxLayout(self)
        root.setContentsMargins(42, 30, 42, 32)
        root.setSpacing(18)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("BOARD MEETING  ·  APPOINTMENT BRIEFING")
        eyebrow.setObjectName("Eyebrow")
        heading.addWidget(eyebrow)
        title = QLabel("구단 비전과 이사회 목표")
        title.setObjectName("PageTitle")
        title.setFont(QFont("Noto Sans KR", 28, QFont.Bold))
        heading.addWidget(title)
        subtitle = QLabel(
            f"{manager_name} 감독에게 적용될 {club_name} 이사회의 평가 기준입니다."
        )
        subtitle.setObjectName("Subtitle")
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        status = QLabel("취임 회의  1 / 1")
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
        board.setFixedWidth(300)
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

        evaluation = QLabel(
            "평가 원칙\n\n"
            "• 필수 목표는 감독직 유지에 직접 반영\n"
            "• 중요 목표는 이사회 신뢰도에 큰 영향\n"
            "• 권장 목표는 장기 평가의 보너스 항목"
        )
        evaluation.setObjectName("EvaluationNote")
        evaluation.setWordWrap(True)
        board_layout.addWidget(evaluation)
        board_layout.addStretch()
        content.addWidget(board)

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
            "5개 항목의 단계를 모두 선택한 뒤 한 번에 이사회로 전달합니다."
        )
        self.current_terms.setObjectName("CurrentTerms")
        self.current_terms.setWordWrap(True)
        negotiation_layout.addWidget(self.current_terms)

        self.level_buttons = []
        for level, title in (
            (1, "1단계  ·  대폭 완화"),
            (2, "2단계  ·  일부 완화"),
            (3, "3단계  ·  이사회 원안"),
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
        self.ai_status = QLabel(
            "Qwen3-1.7B 로컬 AI 대기"
            if self.local_ai_enabled
            else "로컬 AI가 비활성화되어 있습니다"
        )
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
        hint = QLabel("목표를 확인하면 수석코치의 선수단 보고서가 수신함에 도착합니다.")
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
            f"\n현재 합의  ·  {card.selected_level}단계"
            if card.selected_level is not None
            else "\n현재 합의  ·  미협의"
        )
        self.current_terms.setText(
            f"현재 중요도  ·  {card.priority}\n"
            f"평가 기간  ·  {card.period}{selected_text}\n\n{card.description}"
        )
        for button in self.level_buttons:
            button.setEnabled(True)

    def _choose_level(self, level):
        card = self.selected_objective
        if card is None or self._ai_worker is not None:
            return
        card.stage_level(level)
        self.current_terms.setText(f"선택 단계 · {level}단계 ({LEVELS[level]['label']})\n\n{card.description}")
        self.board_response.setText("선택을 저장했습니다. 5개 항목을 모두 선택한 뒤 전달하십시오.")
        selected = sum(item.selected_level is not None for item in self.objective_cards)
        self.ai_status.setText(f"전달 준비 · {selected}/5 항목 선택")

    def _submit_to_board(self):
        if self._ai_worker is not None:
            return
        if not self.local_ai_enabled:
            self.ai_status.setText("KBOFM_AI_ENABLED=1로 로컬 AI를 활성화해야 합니다.")
            return
        if any(card.selected_level is None for card in self.objective_cards):
            self.ai_status.setText("5개 항목의 단계를 먼저 모두 선택하십시오.")
            return
        context = build_board_submission_context(
            self.base_team, self.club_name, self.manager_data,
            self.governance_profile, self.objective_cards,
        )
        self._set_negotiation_busy(True)
        self.accept_button.setEnabled(False)
        self.board_response.setText("이사회가 5개 안건을 검토하고 있습니다.")
        self.ai_status.setText("Qwen3-1.7B 검토 중…")
        self._ai_worker = BoardReviewWorker(context, self)
        self._ai_worker.review_ready.connect(self._on_board_review)
        self._ai_worker.review_failed.connect(self._on_board_review_failed)
        self._ai_worker.finished.connect(self._finish_ai_worker)
        self._ai_worker.start()

    def _on_board_review(self, payload):
        reviews = {item["objective_key"]: item for item in payload["reviews"]}
        response_lines = []
        for card in self.objective_cards:
            review = reviews[card.objective_key]
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
                "source": "local_ai",
            })
        adjustments = [c for c in self.objective_cards if c.decision != "accept"]
        if adjustments:
            self.ai_status.setText(f"AI 검토 완료 · OK {5-len(adjustments)} / 조정 {len(adjustments)}")
            self.board_response.setText("\n\n".join(response_lines))
        else:
            self.ai_status.setText("AI 검토 완료 · 5개 항목 모두 OK")
            self.board_response.setText(
                "\n\n".join(response_lines)
                + "\n\n이사회가 모든 안건을 승인했습니다. 단장 검토로 이동할 수 있습니다."
            )
            self.accept_button.setText("단장 검토로 이동  →")
            try:
                self.accept_button.clicked.disconnect()
            except RuntimeError:
                pass
            self.accept_button.clicked.connect(self.continue_requested.emit)

    def _on_board_review_failed(self, reason):
        self.ai_status.setText(f"로컬 AI 검토 실패 · {reason}")
        self.board_response.setText("규칙 기반 대체 판정은 하지 않습니다. AI 서버를 확인한 뒤 다시 전달하십시오.")

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
            button.setEnabled(not busy and self.selected_objective is not None)
        for card in self.objective_cards:
            card.negotiate_button.setEnabled(not busy)

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
            "schema_version": 1,
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
        for card in self.objective_cards:
            saved = objective_states.get(card.objective_key)
            if not saved:
                continue
            try:
                level = int(saved.get("selected_level"))
            except (TypeError, ValueError):
                continue
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
        self.ai_status.setText("저장된 구단 협상 상태 복원 완료")

    @staticmethod
    def _fact(title, value):
        label = QLabel(f"{title}\n{value}")
        label.setObjectName("BoardFact")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _style(colors):
        return f"""
            QWidget#BoardVisionPage, QWidget#Objectives {{ background-color: #09131f; }}
            QLabel {{ color: #dce6ef; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QLabel#Eyebrow {{ color: {colors['accent_light']}; font-size: 13px; font-weight: 700; }}
            QLabel#PageTitle {{ color: white; }}
            QLabel#Subtitle {{ color: #9badbf; font-size: 15px; }}
            QLabel#MeetingStatus {{ color: #dce6ef; background-color: #14263a; border: 1px solid #354b63; border-radius: 7px; padding: 9px 14px; font-size: 13px; }}
            QFrame#HeaderRule {{ background-color: {colors['accent']}; border: none; }}
            QFrame#BoardPanel {{ background-color: #101e2e; border: 1px solid #30465d; border-radius: 10px; }}
            QLabel#PanelTitle, QLabel#SectionTitle {{ color: {colors['accent_light']}; font-size: 16px; font-weight: 700; }}
            QLabel#ClubName {{ color: white; border-bottom: 1px solid #30465d; padding-bottom: 12px; font-size: 21px; font-weight: 700; }}
            QLabel#BoardFact {{ color: #e5edf5; background-color: #0c1825; border-radius: 6px; padding: 10px; font-size: 13px; }}
            QLabel#EvaluationNote {{ color: #aebdcb; background-color: #0c1825; border-radius: 7px; padding: 12px; font-size: 12px; }}
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
            QPushButton#Level1Button, QPushButton#Level2Button, QPushButton#Level3Button, QPushButton#Level4Button, QPushButton#Level5Button {{ min-height: 36px; font-size: 13px; text-align: left; padding-left: 13px; }}
            QPushButton#Level1Button {{ color: #fca5a5; border-color: #991b1b; }}
            QPushButton#Level2Button {{ color: #fcd34d; border-color: #a16207; }}
            QPushButton#Level3Button {{ color: white; background-color: {colors['accent']}; border-color: {colors['accent_light']}; }}
            QPushButton#Level4Button {{ color: #86efac; border-color: #15803d; }}
            QPushButton#Level5Button {{ color: #67e8f9; border-color: #0e7490; }}
            QLabel#FooterHint {{ color: #8497a9; font-size: 13px; }}
            QPushButton#AcceptButton {{ color: white; background-color: {colors['accent']}; border: 1px solid {colors['accent_light']}; border-radius: 8px; padding: 13px 24px; font-size: 15px; font-weight: 700; }}
            QPushButton#AcceptButton:hover {{ background-color: {colors['accent_light']}; }}
        """
