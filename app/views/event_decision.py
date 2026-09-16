"""협상 대화가 필요 없는 일정·부상·엔트리 업무 처리 화면."""

import sqlite3
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHeaderView,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.player_ratings import overall_rating
from app.services.fa_eligibility import fa_eligibility_report
from app.team_assets import team_logo_path
from app.views.team_manage.player_profile import _player_photo_path
from database.paths import PLAYERS_DB_PATH


class EventDecisionPage(QWidget):
    back_requested = Signal()
    event_resolved = Signal()
    player_requested = Signal(object)

    def __init__(
        self, colors, event_service, save_id, team_name="",
        db_path=None, parent=None,
    ):
        super().__init__(parent)
        self.colors = colors
        self.event_service = event_service
        self.save_id = save_id
        self.team_name = team_name
        self.db_path = db_path or PLAYERS_DB_PATH
        self.current_event = None
        self.choice_buttons = []
        self.roster_audit_players = []
        self.roster_decision_boxes = []
        self.draft_protection_players = []
        self.draft_protection_boxes = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        canvas = QWidget()
        canvas.setObjectName("DecisionCanvas")
        page = QVBoxLayout(canvas)
        page.setContentsMargins(42, 28, 42, 36)
        page.setSpacing(15)

        header = QHBoxLayout()
        back = QPushButton("←  수신함")
        back.setObjectName("Back")
        back.clicked.connect(self.back_requested.emit)
        header.addWidget(back)
        header.addStretch()
        self.date_label = QLabel()
        self.date_label.setObjectName("Date")
        header.addWidget(self.date_label)
        page.addLayout(header)

        self.category_label = QLabel()
        self.category_label.setObjectName("Category")
        page.addWidget(self.category_label)
        self.headline_label = QLabel()
        self.headline_label.setObjectName("Headline")
        self.headline_label.setWordWrap(True)
        page.addWidget(self.headline_label)

        card = QFrame()
        card.setObjectName("BriefingCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(25, 23, 25, 25)
        card_layout.setSpacing(14)
        briefing = QLabel("MANAGER BRIEFING")
        briefing.setObjectName("Kicker")
        card_layout.addWidget(briefing)
        self.body_label = QLabel()
        self.body_label.setObjectName("Body")
        self.body_label.setWordWrap(True)
        self.body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.body_label)
        page.addWidget(card)
        self.briefing_card = card

        self.medical_panel = self._build_medical_panel()
        self.medical_panel.setVisible(False)
        page.addWidget(self.medical_panel)

        self.roster_audit_panel = self._build_roster_audit_panel()
        self.roster_audit_panel.setVisible(False)
        page.addWidget(self.roster_audit_panel)

        self.draft_protection_panel = self._build_draft_protection_panel()
        self.draft_protection_panel.setVisible(False)
        page.addWidget(self.draft_protection_panel)

        choice_title = QLabel("감독 결정")
        choice_title.setObjectName("ChoiceTitle")
        page.addWidget(choice_title)
        self.choice_title = choice_title
        self.choice_layout = QVBoxLayout()
        self.choice_layout.setSpacing(9)
        page.addLayout(self.choice_layout)

        self.result_label = QLabel()
        self.result_label.setObjectName("Result")
        self.result_label.setWordWrap(True)
        self.result_label.setVisible(False)
        page.addWidget(self.result_label)
        page.addStretch()
        scroll.setWidget(canvas)
        root.addWidget(scroll)
        self._apply_style()

    def _build_roster_audit_panel(self):
        panel = QFrame()
        panel.setObjectName("RosterAuditPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(11)

        top = QHBoxLayout()
        heading = QVBoxLayout()
        kicker = QLabel("ROSTER & CONTRACT REVIEW")
        kicker.setObjectName("RosterAuditKicker")
        heading.addWidget(kicker)
        self.roster_panel_title = QLabel("2026 선수단 1차 분류")
        self.roster_panel_title.setObjectName("RosterAuditTitle")
        heading.addWidget(self.roster_panel_title)
        self.roster_panel_note = QLabel(
            "프런트 권고를 참고해 선수별 방침을 정하십시오. "
            "이번 단계에서는 실제 방출이나 계약 체결이 발생하지 않습니다."
        )
        self.roster_panel_note.setObjectName("RosterAuditNote")
        self.roster_panel_note.setWordWrap(True)
        heading.addWidget(self.roster_panel_note)
        top.addLayout(heading, 1)
        self.apply_recommendations_button = QPushButton("프런트 권고 일괄 적용")
        self.apply_recommendations_button.setObjectName("ApplyRecommendations")
        self.apply_recommendations_button.clicked.connect(
            self._apply_roster_recommendations
        )
        top.addWidget(self.apply_recommendations_button)
        layout.addLayout(top)

        summary = QGridLayout()
        summary.setSpacing(7)
        self.roster_summary_values = []
        for index, label in enumerate((
            "검토 대상", "계약 만료", "FA 주의", "방출 검토",
        )):
            card = QFrame()
            card.setObjectName("RosterSummaryCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(11, 8, 11, 8)
            card_label = QLabel(label)
            card_label.setObjectName("RosterSummaryLabel")
            card_layout.addWidget(card_label)
            value = QLabel("0명")
            value.setObjectName("RosterSummaryValue")
            card_layout.addWidget(value)
            self.roster_summary_values.append(value)
            summary.addWidget(card, 0, index)
        layout.addLayout(summary)

        guide = QLabel(
            "선수 이름을 누르면 상세 정보와 FA 등록일수·계약 내용을 확인할 수 있습니다."
        )
        guide.setObjectName("RosterAuditGuide")
        layout.addWidget(guide)

        self.roster_audit_table = QTableWidget(0, 9)
        self.roster_audit_table.setObjectName("RosterAuditTable")
        self.roster_audit_table.setHorizontalHeaderLabels((
            "선수", "포지션", "나이", "현재 능력", "연봉",
            "계약 만료", "FA 상태", "프런트 권고", "감독 방침",
        ))
        self.roster_audit_table.verticalHeader().setVisible(False)
        self.roster_audit_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.roster_audit_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.roster_audit_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.roster_audit_table.setAlternatingRowColors(True)
        self.roster_audit_table.setWordWrap(False)
        self.roster_audit_table.setShowGrid(False)
        self.roster_audit_table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.roster_audit_table.setMinimumHeight(410)
        vertical_header = self.roster_audit_table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical_header.setDefaultSectionSize(46)
        vertical_header.setMinimumSectionSize(46)
        header = self.roster_audit_table.horizontalHeader()
        header.setMinimumSectionSize(54)
        for column in (0, 1, 2, 3, 4, 5, 7):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((
            116, 68, 54, 82, 104, 108, 180, 112, 160,
        )):
            header.resizeSection(column, width)
        self.roster_audit_table.cellClicked.connect(
            self._open_roster_audit_player
        )
        layout.addWidget(self.roster_audit_table)

        footer = QFrame()
        footer.setObjectName("RosterAuditFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(13, 9, 13, 9)
        self.roster_footer_text = QLabel(
            "다음 단계  ·  11월 25일 보류선수 명단 제출 점검에서 최종 확정"
        )
        footer_layout.addWidget(self.roster_footer_text)
        footer_layout.addStretch()
        self.roster_selection_summary = QLabel()
        self.roster_selection_summary.setObjectName("RosterSelectionSummary")
        footer_layout.addWidget(self.roster_selection_summary)
        layout.addWidget(footer)
        return panel

    def _build_draft_protection_panel(self):
        panel = QFrame()
        panel.setObjectName("RosterAuditPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(11)

        heading = QLabel("2차 드래프트 · 우리 구단 보호선수 확정")
        heading.setObjectName("RosterAuditTitle")
        layout.addWidget(heading)
        note = QLabel(
            "자동 제외 선수는 선택할 필요가 없습니다. 지명 자격이 있는 선수 중 "
            "정확히 35명을 보호해야 하며, 나머지는 11월 19일 지명 대상이 됩니다."
        )
        note.setObjectName("RosterAuditNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.draft_protection_summary = QLabel("보호 0 / 35")
        self.draft_protection_summary.setObjectName("RosterSelectionSummary")
        layout.addWidget(self.draft_protection_summary)

        self.draft_protection_table = QTableWidget(0, 8)
        self.draft_protection_table.setObjectName("RosterAuditTable")
        self.draft_protection_table.setHorizontalHeaderLabels((
            "선수", "포지션", "나이", "1·2군", "현재 능력",
            "잠재력", "보호 점수", "감독 결정",
        ))
        self.draft_protection_table.verticalHeader().setVisible(False)
        self.draft_protection_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.draft_protection_table.setAlternatingRowColors(True)
        self.draft_protection_table.setShowGrid(False)
        self.draft_protection_table.setMinimumHeight(430)
        self.draft_protection_table.verticalHeader().setDefaultSectionSize(42)
        header = self.draft_protection_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 8):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.draft_protection_table)
        return panel

    def _load_roster_audit_players(self):
        connection = None
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM players WHERE team=? ORDER BY status DESC, name",
                (self.team_name,),
            ).fetchall()
            players = [dict(row) for row in rows]
        except sqlite3.Error:
            return []
        finally:
            if connection is not None:
                connection.close()

        reviewed = []
        for player in players:
            report = fa_eligibility_report(player)
            rating = float(overall_rating(player))
            contract_end = str(
                report.get("contract_end_date")
                or player.get("contract_end_date") or "2025-11-30"
            )
            expires = contract_end[:4] <= "2025"
            fa_attention = bool(
                report.get("qualification_met")
                or report.get("can_apply_now")
                or int(report.get("shortage_seasons") or 99) <= 1
            )
            if expires and (rating < 10.5 and int(player.get("age") or 0) >= 29):
                recommendation = "방출 후보"
            elif expires and fa_attention:
                recommendation = "보류·재계약"
            elif int(player.get("age") or 0) <= 25 and rating < 12.5:
                recommendation = "퓨처스 육성"
            elif expires:
                recommendation = "계약 재검토"
            else:
                recommendation = "보류·재계약"
            reviewed.append({
                **player,
                "_fa_report": report,
                "_rating": rating,
                "_contract_end": contract_end,
                "_expires": expires,
                "_fa_attention": fa_attention,
                "_recommendation": recommendation,
            })
        return sorted(
            reviewed,
            key=lambda item: (
                not item["_expires"],
                not item["_fa_attention"],
                item["_recommendation"] != "방출 후보",
                -item["_rating"],
            ),
        )

    def _populate_roster_audit(self):
        self.roster_audit_players = self._load_roster_audit_players()
        self.roster_decision_boxes.clear()
        schedule_id = str(
            (((self.current_event or {}).get("payload") or {}).get(
                "schedule_event"
            ) or {}).get("event_id") or ""
        )
        is_final = schedule_id == "reserve_submit"
        decision_payload = dict(
            (((self.current_event or {}).get("payload") or {}).get(
                "manager_decision"
            ) or {})
        )
        saved_decisions = {
            int(item.get("player_id") or 0): str(item.get("decision") or "")
            for item in decision_payload.get("players", [])
        }
        if is_final and not saved_decisions:
            connection = sqlite3.connect(self.event_service.saves_db_path)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    """
                    SELECT player_id, decision FROM roster_audit_decisions
                    WHERE save_id=? AND team=?
                    """,
                    (self.save_id, self.team_name),
                ).fetchall()
                saved_decisions = {
                    int(row["player_id"]): (
                        "자유계약 공시"
                        if row["decision"] == "방출 후보" else row["decision"]
                    )
                    for row in rows
                }
            except sqlite3.OperationalError:
                saved_decisions = {}
            finally:
                connection.close()
        table = self.roster_audit_table
        table.setRowCount(len(self.roster_audit_players))
        options = (
            "보류·재계약", "계약 재검토", "퓨처스 육성",
            "자유계약 공시" if is_final else "방출 후보",
        )
        for row, player in enumerate(self.roster_audit_players):
            report = player["_fa_report"]
            shortage = report.get("shortage_seasons")
            fa_label = (
                "FA 신청 가능"
                if report.get("can_apply_now") else
                "자격 충족 · 계약 유보"
                if report.get("qualification_met") else
                f"FA까지 {int(shortage)}시즌"
                if isinstance(shortage, (int, float)) and shortage <= 2 else
                "FA 자격 누적 중"
            )
            fa_detail = (
                report.get("availability_label")
                or report.get("status") or "미산정"
            )
            values = (
                player.get("name") or "-",
                player.get("pos") or "-",
                str(player.get("age") or "-"),
                f"{player['_rating']:.1f}",
                f"{int(player.get('salary') or 0):,}만원",
                player["_contract_end"],
                fa_label,
                player["_recommendation"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, player.get("id"))
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignVCenter)
                    | int(
                        Qt.AlignmentFlag.AlignLeft
                        if column in (0, 6, 7) else
                        Qt.AlignmentFlag.AlignCenter
                    )
                )
                if column == 0:
                    item.setForeground(QColor("#78c4ee"))
                    item.setToolTip("클릭하여 선수 상세 정보 보기")
                elif column == 6:
                    item.setToolTip(fa_detail)
                    if player["_fa_attention"]:
                        item.setForeground(QColor("#efc467"))
                elif column == 7:
                    tone = {
                        "방출 후보": "#ef7474",
                        "계약 재검토": "#e3b65d",
                        "퓨처스 육성": "#70b9e6",
                        "보류·재계약": "#76c89b",
                    }.get(player["_recommendation"], "#d9e1e7")
                    item.setForeground(QColor(tone))
                table.setItem(row, column, item)
            decision = QComboBox()
            decision.setObjectName("RosterDecision")
            decision.setFixedHeight(32)
            decision.addItems(options)
            recommended_decision = player["_recommendation"]
            if is_final and recommended_decision == "방출 후보":
                recommended_decision = "자유계약 공시"
            decision.setCurrentText(
                saved_decisions.get(
                    int(player.get("id") or 0),
                    recommended_decision,
                )
            )
            decision.currentTextChanged.connect(
                self._update_roster_selection_summary
            )
            decision.currentTextChanged.connect(
                lambda text, box=decision: self._set_roster_decision_tone(
                    box, text
                )
            )
            self._set_roster_decision_tone(
                decision, decision.currentText()
            )
            decision_cell = QWidget()
            decision_cell.setObjectName("RosterDecisionCell")
            decision_layout = QHBoxLayout(decision_cell)
            decision_layout.setContentsMargins(6, 6, 6, 6)
            decision_layout.setSpacing(0)
            decision_layout.addWidget(decision)
            table.setCellWidget(row, 8, decision_cell)
            table.setRowHeight(row, 46)
            self.roster_decision_boxes.append(decision)
        expires = sum(player["_expires"] for player in self.roster_audit_players)
        fa_attention = sum(
            player["_fa_attention"] for player in self.roster_audit_players
        )
        release = sum(
            player["_recommendation"] == "방출 후보"
            for player in self.roster_audit_players
        )
        for widget, value in zip(self.roster_summary_values, (
            len(self.roster_audit_players), expires, fa_attention, release,
        )):
            widget.setText(f"{value}명")
        self._update_roster_selection_summary()

    def _apply_roster_recommendations(self):
        for player, box in zip(
            self.roster_audit_players, self.roster_decision_boxes
        ):
            box.setCurrentText(player["_recommendation"])
        self._update_roster_selection_summary()

    @staticmethod
    def _set_roster_decision_tone(box, decision):
        tone = {
            "보류·재계약": "retain",
            "계약 재검토": "review",
            "퓨처스 육성": "develop",
            "방출 후보": "release",
            "자유계약 공시": "release",
        }.get(str(decision), "neutral")
        box.setProperty("tone", tone)
        box.style().unpolish(box)
        box.style().polish(box)

    def _update_roster_selection_summary(self, _value=None):
        counts = {}
        for box in self.roster_decision_boxes:
            counts[box.currentText()] = counts.get(box.currentText(), 0) + 1
        self.roster_selection_summary.setText(
            " · ".join(
                f"{label} {counts.get(label, 0)}"
                for label in (
                    "보류·재계약", "계약 재검토",
                    "퓨처스 육성",
                    "자유계약 공시"
                    if any(
                        box.findText("자유계약 공시") >= 0
                        for box in self.roster_decision_boxes
                    ) else "방출 후보",
                )
            )
        )

    def _open_roster_audit_player(self, row, _column):
        if 0 <= row < len(self.roster_audit_players):
            self.player_requested.emit(self.roster_audit_players[row])

    def _roster_audit_resolution(self):
        return {
            "team": self.team_name,
            "event_date": str(
                (self.current_event or {}).get("event_date") or "2025-11-03"
            ),
            "players": [
                {
                    "player_id": player.get("id"),
                    "player_name": player.get("name"),
                    "decision": box.currentText(),
                }
                for player, box in zip(
                    self.roster_audit_players, self.roster_decision_boxes
                )
            ]
        }

    def _populate_draft_protection(self):
        self.draft_protection_players = []
        self.draft_protection_boxes.clear()
        connection = sqlite3.connect(self.event_service.saves_db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT * FROM second_draft_pool
                WHERE save_id=? AND original_team=?
                  AND classification!='automatic_exempt'
                ORDER BY protection_score DESC, player_name
                """,
                (self.save_id, self.team_name),
            ).fetchall()
            self.draft_protection_players = [dict(row) for row in rows]
        finally:
            connection.close()

        table = self.draft_protection_table
        table.setRowCount(len(self.draft_protection_players))
        for row, player in enumerate(self.draft_protection_players):
            values = (
                player.get("player_name") or "-",
                player.get("position_group") or "-",
                player.get("age") or "-",
                "1군" if int(player.get("roster_status") or 0) else "2군",
                f"{float(player.get('overall') or 0):.1f}",
                f"{float(player.get('potential') or 0):.1f}",
                f"{float(player.get('protection_score') or 0):.1f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
            decision = QComboBox()
            decision.setObjectName("RosterDecision")
            decision.addItems(("보호선수", "지명 가능"))
            decision.setCurrentText(
                "보호선수"
                if player.get("classification") == "protected" else "지명 가능"
            )
            decision.currentTextChanged.connect(
                self._update_draft_protection_summary
            )
            table.setCellWidget(row, 7, decision)
            self.draft_protection_boxes.append(decision)
        self._update_draft_protection_summary()

    def _update_draft_protection_summary(self, _value=None):
        protected = sum(
            box.currentText() == "보호선수"
            for box in self.draft_protection_boxes
        )
        required = min(35, len(self.draft_protection_boxes))
        self.draft_protection_summary.setText(
            f"보호 {protected} / {required} · 지명 가능 "
            f"{len(self.draft_protection_boxes) - protected}"
        )
        tone = "#76c89b" if protected == required else "#ef7474"
        self.draft_protection_summary.setStyleSheet(f"color:{tone}; font-weight:800;")

    def _draft_protection_resolution(self):
        protected_ids = [
            int(player["player_id"])
            for player, box in zip(
                self.draft_protection_players, self.draft_protection_boxes
            )
            if box.currentText() == "보호선수"
        ]
        required = min(35, len(self.draft_protection_players))
        if len(protected_ids) != required:
            raise ValueError(f"보호선수를 정확히 {required}명 선택해 주십시오.")
        return {
            "team": self.team_name,
            "event_date": str(
                (self.current_event or {}).get("event_date") or "2025-11-12"
            ),
            "protected_player_ids": protected_ids,
        }

    def _build_medical_panel(self):
        panel = QFrame()
        panel.setObjectName("MedicalPanel")
        root = QVBoxLayout(panel)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        self.medical_severity = QLabel("진료 필요")
        self.medical_severity.setObjectName("MedicalSeverity")
        header.addWidget(self.medical_severity)
        title = QLabel("MEDICAL CENTRE · PLAYER REPORT")
        title.setObjectName("MedicalKicker")
        header.addWidget(title)
        header.addStretch()
        self.medical_report_date = QLabel()
        self.medical_report_date.setObjectName("MedicalDate")
        header.addWidget(self.medical_report_date)
        root.addLayout(header)

        dossier = QHBoxLayout()
        dossier.setSpacing(12)
        identity = QFrame()
        identity.setObjectName("MedicalIdentity")
        identity.setMinimumWidth(190)
        identity.setMaximumWidth(250)
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(14, 14, 14, 14)
        identity_layout.setSpacing(7)
        self.medical_photo = QLabel("선수")
        self.medical_photo.setObjectName("MedicalPhoto")
        self.medical_photo.setFixedSize(132, 150)
        self.medical_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity_layout.addWidget(
            self.medical_photo, 0, Qt.AlignmentFlag.AlignHCenter
        )
        identity_name = QHBoxLayout()
        self.medical_logo = QLabel()
        self.medical_logo.setFixedSize(36, 28)
        identity_name.addWidget(self.medical_logo)
        self.medical_player = QLabel("-")
        self.medical_player.setObjectName("MedicalPlayer")
        identity_name.addWidget(self.medical_player, 1)
        identity_layout.addLayout(identity_name)
        self.medical_meta = QLabel("-")
        self.medical_meta.setObjectName("MedicalMeta")
        self.medical_meta.setWordWrap(True)
        identity_layout.addWidget(self.medical_meta)
        dossier.addWidget(identity)

        clinical = QFrame()
        clinical.setObjectName("ClinicalCard")
        clinical_layout = QVBoxLayout(clinical)
        clinical_layout.setContentsMargins(18, 16, 18, 17)
        clinical_layout.setSpacing(9)
        diagnosis_kicker = QLabel("검사 결과")
        diagnosis_kicker.setObjectName("ClinicalKicker")
        clinical_layout.addWidget(diagnosis_kicker)
        self.medical_diagnosis = QLabel("-")
        self.medical_diagnosis.setObjectName("Diagnosis")
        self.medical_diagnosis.setWordWrap(True)
        clinical_layout.addWidget(self.medical_diagnosis)
        self.medical_summary = QLabel()
        self.medical_summary.setObjectName("ClinicalSummary")
        self.medical_summary.setWordWrap(True)
        clinical_layout.addWidget(self.medical_summary)
        clinical_layout.addStretch()

        facts = QGridLayout()
        facts.setSpacing(7)
        self.medical_fact_values = []
        for index, label in enumerate(("예상 이탈", "복귀 예정", "현재 상태", "발생 당시")):
            fact = QFrame()
            fact.setObjectName("MedicalFact")
            fact_layout = QVBoxLayout(fact)
            fact_layout.setContentsMargins(10, 8, 10, 8)
            fact_label = QLabel(label)
            fact_label.setObjectName("MedicalFactLabel")
            fact_layout.addWidget(fact_label)
            value = QLabel("-")
            value.setObjectName("MedicalFactValue")
            value.setWordWrap(True)
            fact_layout.addWidget(value)
            self.medical_fact_values.append(value)
            facts.addWidget(fact, index // 2, index % 2)
        clinical_layout.addLayout(facts)
        dossier.addWidget(clinical, 1)
        root.addLayout(dossier)

        timeline = QFrame()
        timeline.setObjectName("TreatmentPlan")
        timeline_layout = QHBoxLayout(timeline)
        timeline_layout.setContentsMargins(14, 11, 14, 11)
        timeline_layout.setSpacing(8)
        self.medical_steps = []
        for index, title in enumerate(("01 진단", "02 치료", "03 재활", "04 복귀")):
            step = QFrame()
            step.setObjectName("TreatmentStep")
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(10, 7, 10, 7)
            step_title = QLabel(title)
            step_title.setObjectName("TreatmentStepTitle")
            step_layout.addWidget(step_title)
            step_value = QLabel("-")
            step_value.setObjectName("TreatmentStepValue")
            step_value.setWordWrap(True)
            step_layout.addWidget(step_value)
            timeline_layout.addWidget(step, 1)
            self.medical_steps.append(step_value)
        root.addWidget(timeline)

        recommendation = QFrame()
        recommendation.setObjectName("MedicalRecommendation")
        recommendation_layout = QHBoxLayout(recommendation)
        recommendation_layout.setContentsMargins(14, 11, 14, 11)
        recommendation_icon = QLabel("+")
        recommendation_icon.setObjectName("MedicalCross")
        recommendation_icon.setFixedSize(32, 32)
        recommendation_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recommendation_layout.addWidget(recommendation_icon)
        recommendation_text = QVBoxLayout()
        recommendation_title = QLabel("메디컬팀 권고")
        recommendation_title.setObjectName("RecommendationTitle")
        recommendation_text.addWidget(recommendation_title)
        self.medical_recommendation = QLabel()
        self.medical_recommendation.setObjectName("RecommendationBody")
        self.medical_recommendation.setWordWrap(True)
        recommendation_text.addWidget(self.medical_recommendation)
        recommendation_layout.addLayout(recommendation_text, 1)
        root.addWidget(recommendation)
        return panel

    def _medical_player_record(self, payload):
        connection = None
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            row = None
            if payload.get("player_id"):
                row = connection.execute(
                    "SELECT * FROM players WHERE id=?",
                    (int(payload["player_id"]),),
                ).fetchone()
            if row is None and payload.get("player_name"):
                row = connection.execute(
                    "SELECT * FROM players WHERE name=? AND team=? LIMIT 1",
                    (payload["player_name"], payload.get("team", "")),
                ).fetchone()
            return dict(row) if row else {}
        except (sqlite3.Error, TypeError, ValueError):
            return {}
        finally:
            if connection is not None:
                connection.close()

    def _set_medical_event(self, event):
        payload = dict(event.get("payload") or {})
        player = str(payload.get("player_name") or "선수")
        team = str(payload.get("team") or "KBO")
        diagnosis = str(payload.get("injury_type") or "정밀 검사 필요")
        days = int(payload.get("expected_days") or 0)
        record = self._medical_player_record(payload)
        try:
            injured_on = date.fromisoformat(str(event.get("event_date")))
            return_on = injured_on + timedelta(days=max(1, days))
            injured_text = injured_on.strftime("%Y.%m.%d")
            return_text = return_on.strftime("%Y.%m.%d")
        except (TypeError, ValueError):
            injured_text = str(event.get("event_date") or "-").replace("-", ".")
            return_text = "재검 후 확정"
        severity = "경미" if days <= 7 else "주의" if days <= 21 else "장기 이탈"
        self.medical_severity.setText(severity)
        self.medical_severity.setProperty(
            "level", "minor" if days <= 7 else "care" if days <= 21 else "major"
        )
        self.medical_severity.style().unpolish(self.medical_severity)
        self.medical_severity.style().polish(self.medical_severity)
        self.medical_report_date.setText(f"보고일  {injured_text}")
        self.medical_player.setText(player)
        self.medical_meta.setText(
            f"{team}\n"
            f"{record.get('pos') or payload.get('position') or '-'} · "
            f"{record.get('age') or payload.get('age') or '-'}세 · "
            f"{payload.get('squad') or '1군'}"
        )
        self.medical_diagnosis.setText(diagnosis)
        self.medical_summary.setText(
            f"검사 결과 {diagnosis} 소견이 확인됐습니다. 예상 이탈 기간은 "
            f"{days or '-'}일이며, 회복 상태에 따라 복귀 일정이 조정될 수 있습니다."
        )
        for widget, value in zip(self.medical_fact_values, (
            f"{days or '-'}일", return_text, "팀 훈련 제외",
            (
                f"컨디션 {payload.get('condition')} · 피로도 {payload.get('fatigue')}"
                if payload.get("condition") is not None
                and payload.get("fatigue") is not None
                else "메디컬 센터"
            ),
        )):
            widget.setText(value)
        treatment = (
            "휴식·통증 관찰" if days <= 7 else
            "치료·제한 훈련" if days <= 21 else "정밀 치료·재활"
        )
        for widget, value in zip(self.medical_steps, (
            injured_text, treatment, "단계별 강도 회복", return_text,
        )):
            widget.setText(value)
        self.medical_recommendation.setText(
            f"{player}의 재발 위험을 줄이려면 메디컬 재검 전까지 경기 출전을 "
            "제한하고, 선택한 치료 방침에 맞춰 훈련 강도를 조절해야 합니다."
        )
        self.medical_photo.setText(player[-2:])
        self.medical_photo.setPixmap(QPixmap())
        photo_path = _player_photo_path(
            record.get("kbo_player_id"), player, team
        )
        if photo_path:
            pixmap = QPixmap(str(photo_path))
            if not pixmap.isNull():
                self.medical_photo.setText("")
                self.medical_photo.setPixmap(pixmap.scaled(
                    self.medical_photo.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        logo = QPixmap(str(team_logo_path(team)))
        self.medical_logo.setPixmap(QPixmap())
        if not logo.isNull():
            self.medical_logo.setPixmap(logo.scaled(
                self.medical_logo.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def set_event(self, event):
        self.current_event = event
        self.date_label.setText(str(event.get("event_date", "")).replace("-", "."))
        self.headline_label.setText(str(event.get("headline") or "감독 결정 요청"))
        self.body_label.setText(str(event.get("body") or "업무 내용을 확인해 주십시오."))
        event_type = str(event.get("event_type") or "")
        schedule_event = dict(
            (event.get("payload") or {}).get("schedule_event") or {}
        )
        is_medical = event_type == "injury"
        is_roster_audit = (
            event_type == "schedule"
            and schedule_event.get("event_id") in {
                "roster_audit", "reserve_submit",
            }
        )
        is_reserve_submit = (
            event_type == "schedule"
            and schedule_event.get("event_id") == "reserve_submit"
        )
        is_draft_protection = (
            event_type == "schedule"
            and schedule_event.get("event_id") == "second_draft_protect"
        )
        self.category_label.setText(
            "선수단 관리 · 계약/보류"
            if is_roster_audit else
            str(event.get("category") or "구단 업무")
        )
        self.briefing_card.setVisible(
            not is_medical and not is_roster_audit and not is_draft_protection
        )
        self.medical_panel.setVisible(is_medical)
        self.roster_audit_panel.setVisible(is_roster_audit)
        self.draft_protection_panel.setVisible(is_draft_protection)
        if is_medical:
            self._set_medical_event(event)
        if is_roster_audit:
            self.roster_panel_title.setText(
                "2026 보류선수 명단 최종 제출"
                if is_reserve_submit else "2026 선수단 1차 분류"
            )
            self.roster_panel_note.setText(
                "선수별 최종 결정을 제출하면 퓨처스 편성과 자유계약 공시가 "
                "즉시 선수단 데이터에 반영됩니다."
                if is_reserve_submit else
                "프런트 권고를 참고해 선수별 방침을 정하십시오. 이번 단계에서는 "
                "실제 방출이나 계약 체결이 발생하지 않습니다."
            )
            self.roster_footer_text.setText(
                "최종 단계  ·  자유계약 공시 선택 선수는 제출 즉시 구단 명단에서 제외"
                if is_reserve_submit else
                "다음 단계  ·  11월 25일 보류선수 명단 제출 점검에서 최종 확정"
            )
            self._populate_roster_audit()
        if is_draft_protection:
            self._populate_draft_protection()
        self.choice_title.setText(
            "보류선수 명단 제출"
            if is_reserve_submit else
            "1차 검토안 제출"
            if is_roster_audit else
            "보호선수 명단 제출"
            if is_draft_protection else "감독 결정"
        )
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.choice_buttons.clear()
        resolved = str(event.get("status") or "open") == "resolved"
        choices = list(event.get("choices") or [])
        if resolved:
            self.result_label.setText(event.get("result_text") or "이미 처리된 업무입니다.")
            self.result_label.setVisible(True)
            return
        self.result_label.setVisible(False)
        if not choices:
            choices = [{
                "key": "acknowledge", "label": "내용 확인",
                "description": "업무 내용을 확인하고 수신함으로 돌아갑니다.",
            }]
        for choice in choices:
            label = choice.get("label", "확인")
            description = choice.get("description", "")
            if is_roster_audit:
                label = (
                    "보류선수 명단 최종 제출"
                    if is_reserve_submit else "선수단 1차 분류안 저장"
                )
                description = (
                    "선택한 자유계약·육성 결정을 실제 선수단에 반영합니다."
                    if is_reserve_submit else
                    "선수별 감독 방침을 저장하고 11월 25일 최종 검토로 넘깁니다."
                )
            elif is_draft_protection:
                label = "보호선수 35인 최종 확정"
                description = "선택한 보호 명단을 11월 19일 2차 드래프트에 적용합니다."
            button = QPushButton(
                f"{label}\n{description}"
            )
            button.setProperty("choice", True)
            button.setMinimumHeight(66)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, key=choice.get("key", "acknowledge"):
                self._resolve(key)
            )
            self.choice_layout.addWidget(button)
            self.choice_buttons.append(button)

    def _resolve(self, choice_key):
        if not self.current_event:
            return
        for button in self.choice_buttons:
            button.setEnabled(False)
        try:
            resolution_data = (
                self._draft_protection_resolution()
                if self.draft_protection_panel.isVisible() else
                self._roster_audit_resolution()
                if self.roster_audit_panel.isVisible() else None
            )
            result = self.event_service.resolve(
                self.save_id, int(self.current_event["id"]), choice_key,
                resolution_data=resolution_data,
            )
        except Exception as error:
            for button in self.choice_buttons:
                button.setEnabled(True)
            QMessageBox.critical(self, "업무 처리 오류", str(error))
            return
        self.current_event["status"] = "resolved"
        self.current_event["result_text"] = result
        self.result_label.setText(result)
        self.result_label.setVisible(True)
        self.event_resolved.emit()

    def _apply_style(self):
        c = self.colors
        self.setStyleSheet(f"""
            QWidget#DecisionCanvas {{ background: #0e141a; }}
            QLabel {{ color: #dce5ed; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QPushButton#Back {{ color: #dce5ed; background: #202932; border: 1px solid #46535e; padding: 8px 14px; font-weight: 700; }}
            QPushButton#Back:hover {{ background: {c['accent']}; }}
            QLabel#Date {{ color: #82919d; font-size: 14px; }}
            QLabel#Category, QLabel#Kicker {{ color: {c['accent_light']}; font-size: 14px; font-weight: 800; }}
            QLabel#Headline {{ color: white; font-size: 27px; font-weight: 900; }}
            QFrame#BriefingCard {{ background: #171f27; border: 1px solid #3a4854; border-left: 4px solid {c['accent']}; }}
            QLabel#Body {{ color: #d1dbe4; font-size: 15px; line-height: 1.5; }}
            QFrame#RosterAuditPanel {{ background: #111820; border: 1px solid #40515e; border-radius: 4px; }}
            QLabel#RosterAuditKicker {{ color: #d7ad52; font-size: 13px; font-weight: 900; }}
            QLabel#RosterAuditTitle {{ color: white; font-size: 24px; font-weight: 900; }}
            QLabel#RosterAuditNote {{ color: #aebbc5; font-size: 14px; }}
            QPushButton#ApplyRecommendations {{ color: #e8edf1; background: #26323c; border: 1px solid #566572; padding: 9px 14px; font-weight: 800; }}
            QPushButton#ApplyRecommendations:hover {{ color: white; background: #34434f; border-color: #d0aa53; }}
            QFrame#RosterSummaryCard {{ background: #18232c; border: 1px solid #334653; border-top: 3px solid #4c849f; border-radius: 3px; }}
            QLabel#RosterSummaryLabel {{ color: #8798a5; font-size: 13px; font-weight: 800; }}
            QLabel#RosterSummaryValue {{ color: white; font-size: 20px; font-weight: 900; }}
            QLabel#RosterAuditGuide {{ color: #86bad8; background: #18242d; border-left: 3px solid #4e9cca; padding: 8px 10px; font-size: 13px; }}
            QTableWidget#RosterAuditTable {{ color: #dbe4eb; background: #11171d; alternate-background-color: #182028; border: 1px solid #3b4955; gridline-color: transparent; selection-background-color: #244a65; selection-color: white; font-size: 13px; outline: none; }}
            QTableWidget#RosterAuditTable::item {{ border-bottom: 1px solid #2b3741; padding: 0 9px; }}
            QHeaderView::section {{ color: #c5d0d9; background: #202a33; border: none; border-right: 1px solid #384651; border-bottom: 1px solid #4a5965; padding: 9px 7px; font-size: 13px; font-weight: 800; }}
            QWidget#RosterDecisionCell {{ background: transparent; }}
            QComboBox#RosterDecision {{ color: white; background: #202b34; border: 1px solid #4a5a66; border-radius: 2px; padding: 5px 24px 5px 9px; font-weight: 700; }}
            QComboBox#RosterDecision:hover {{ border-color: #d0aa53; }}
            QComboBox#RosterDecision[tone="retain"] {{ color: #9de1b9; border-color: #3f7257; }}
            QComboBox#RosterDecision[tone="review"] {{ color: #f0ca76; border-color: #7b6739; }}
            QComboBox#RosterDecision[tone="develop"] {{ color: #91caec; border-color: #426d87; }}
            QComboBox#RosterDecision[tone="release"] {{ color: #ff9292; border-color: #8a474c; background: #2b2024; }}
            QComboBox#RosterDecision::drop-down {{ border: none; width: 22px; }}
            QComboBox#RosterDecision QAbstractItemView {{ color: white; background: #1a232b; selection-background-color: #35536a; }}
            QFrame#RosterAuditFooter {{ background: #1b232a; border: 1px solid #394650; border-left: 4px solid #d0aa53; }}
            QFrame#RosterAuditFooter QLabel {{ color: #bdc8d1; font-size: 13px; font-weight: 700; }}
            QLabel#RosterSelectionSummary {{ color: #f0c766; font-weight: 900; }}
            QFrame#MedicalPanel {{ background: #111820; border: 1px solid #43515e; border-radius: 4px; }}
            QLabel#MedicalSeverity {{ color: white; background: #a3484e; border-radius: 3px; padding: 5px 11px; font-size: 13px; font-weight: 900; }}
            QLabel#MedicalSeverity[level="minor"] {{ background: #58707d; }}
            QLabel#MedicalSeverity[level="care"] {{ background: #a16b29; }}
            QLabel#MedicalSeverity[level="major"] {{ background: #a3484e; }}
            QLabel#MedicalKicker {{ color: #71bce5; font-size: 13px; font-weight: 900; }}
            QLabel#MedicalDate {{ color: #8695a2; font-size: 13px; }}
            QFrame#MedicalIdentity, QFrame#ClinicalCard {{ background: #18222b; border: 1px solid #354654; border-radius: 4px; }}
            QLabel#MedicalPhoto {{ color: white; background: #253642; border: 1px solid #536674; border-radius: 3px; font-size: 28px; font-weight: 900; }}
            QLabel#MedicalPlayer {{ color: white; font-size: 18px; font-weight: 900; }}
            QLabel#MedicalMeta {{ color: #99a9b6; font-size: 13px; }}
            QLabel#ClinicalKicker {{ color: #e1b557; font-size: 13px; font-weight: 900; }}
            QLabel#Diagnosis {{ color: white; font-size: 24px; font-weight: 900; }}
            QLabel#ClinicalSummary {{ color: #b8c4ce; font-size: 15px; }}
            QFrame#MedicalFact {{ background: #111820; border: 1px solid #2f3d48; border-radius: 3px; }}
            QLabel#MedicalFactLabel {{ color: #80909e; font-size: 13px; font-weight: 800; }}
            QLabel#MedicalFactValue {{ color: #e6ebef; font-size: 15px; font-weight: 900; }}
            QFrame#TreatmentPlan {{ background: #151d24; border: 1px solid #35434e; }}
            QFrame#TreatmentStep {{ background: #1c2730; border: none; border-top: 3px solid #54758b; }}
            QLabel#TreatmentStepTitle {{ color: #74b8df; font-size: 13px; font-weight: 900; }}
            QLabel#TreatmentStepValue {{ color: #d8e0e6; font-size: 13px; font-weight: 700; }}
            QFrame#MedicalRecommendation {{ background: #20242a; border: 1px solid #54482f; border-left: 4px solid #d3a442; }}
            QLabel#MedicalCross {{ color: #17130a; background: #e0ae43; border-radius: 16px; font-size: 21px; font-weight: 900; }}
            QLabel#RecommendationTitle {{ color: #f0c664; font-size: 13px; font-weight: 900; }}
            QLabel#RecommendationBody {{ color: #d3dce3; font-size: 14px; }}
            QLabel#ChoiceTitle {{ color: white; font-size: 17px; font-weight: 800; margin-top: 4px; }}
            QPushButton[choice="true"] {{ color: #e3eaf0; background: #1c252e; border: 1px solid #3b4854; padding: 12px 16px; text-align: left; font-size: 15px; font-weight: 700; }}
            QPushButton[choice="true"]:hover {{ color: white; background: #263541; border-color: {c['accent_light']}; }}
            QPushButton[choice="true"]:disabled {{ color: #71808c; background: #161d24; }}
            QLabel#Result {{ color: #dff7e8; background: #173226; border-left: 4px solid #4fb77b; padding: 15px; font-weight: 700; }}
            QScrollArea {{ border: none; background: #0e141a; }}
        """)
