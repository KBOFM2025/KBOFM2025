"""KBO 2차 드래프트 보호 명단과 지명 결과 전체 화면."""

import json
import sqlite3
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import TEAM_COLORS
from app.services.second_draft import (
    DRAFT_DATE,
    DRAFT_PREPARATION_DATE,
    SecondDraftService,
)


CLASSIFICATION_LABELS = {
    "available": "지명 가능",
    "protected": "보호선수",
    "automatic_exempt": "자동 제외",
}
POSITION_LABELS = {"P": "투수", "C": "포수", "IF": "내야수", "OF": "외야수"}


class SecondDraftPage(QWidget):
    back_requested = Signal()
    player_requested = Signal(object)

    def __init__(
        self, colors, save_database, save_id, player_db_path,
        current_date=None, parent=None,
    ):
        super().__init__(parent)
        self.colors = colors
        self.save_database = save_database
        self.save_id = save_id
        self.player_db_path = player_db_path
        self.current_date = self._as_date(current_date)
        self.service = SecondDraftService(
            save_database, save_id, player_db_path
        )
        self.visible_rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 8)
        root.setSpacing(6)

        header = QFrame()
        header.setObjectName("DraftHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        back = QPushButton("←  이전 화면")
        back.setObjectName("BackButton")
        back.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(back)
        heading = QVBoxLayout()
        title = QLabel("KBO 2차 드래프트")
        title.setObjectName("DraftTitle")
        title.setFont(QFont("Malgun Gothic", 20, QFont.Bold))
        heading.addWidget(title)
        self.subtitle = QLabel()
        heading.addWidget(self.subtitle)
        header_layout.addLayout(heading)
        header_layout.addStretch()
        self.status_badge = QLabel()
        self.status_badge.setObjectName("StatusBadge")
        header_layout.addWidget(self.status_badge)
        root.addWidget(header)

        summary_row = QHBoxLayout()
        self.summary_cards = {}
        for key, title_text in (
            ("available", "지명 가능"),
            ("protected", "AI 보호(최대 35)"),
            ("automatic_exempt", "자동 제외"),
            ("results", "지명 결과"),
        ):
            card = QFrame()
            card.setObjectName("SummaryCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 5, 12, 5)
            label = QLabel(title_text)
            label.setObjectName("CardLabel")
            value = QLabel("0")
            value.setObjectName("CardValue")
            value.setFont(QFont("Malgun Gothic", 16, QFont.Bold))
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            summary_row.addWidget(card)
            self.summary_cards[key] = value
        root.addLayout(summary_row)

        filters = QFrame()
        filters.setObjectName("DraftFilters")
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(8, 5, 8, 5)
        self.view_combo = QComboBox()
        self.view_combo.addItem("지명 가능 명단", "available")
        self.view_combo.addItem("보호선수(구단별 최대 35명)", "protected")
        self.view_combo.addItem("자동 제외 선수", "automatic_exempt")
        self.view_combo.addItem("지명 결과", "results")
        self.team_combo = QComboBox()
        self.team_combo.addItem("전체 구단", None)
        for team in TEAM_COLORS:
            self.team_combo.addItem(team, team)
        self.position_combo = QComboBox()
        self.position_combo.addItem("전체 포지션", None)
        for position, label in POSITION_LABELS.items():
            self.position_combo.addItem(label, position)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("선수 이름")
        self.search_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.view_combo)
        filter_layout.addWidget(self.team_combo)
        filter_layout.addWidget(self.position_combo)
        filter_layout.addWidget(self.search_input, 1)
        for widget in (
            self.view_combo, self.team_combo, self.position_combo
        ):
            widget.currentIndexChanged.connect(self.refresh)
        self.search_input.textChanged.connect(self.refresh)
        root.addWidget(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            [
                "선수", "원소속", "포지션", "나이", "입단",
                "1·2군", "종합", "잠재력", "연봉", "보호 점수", "판정",
            ]
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.cellDoubleClicked.connect(self._open_player)
        self.table.cellClicked.connect(
            lambda row, column: self._open_player(row) if column == 0 else None
        )
        table_header = self.table.horizontalHeader()
        table_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 11):
            table_header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        root.addWidget(self.table, 1)

        footer = QFrame()
        footer.setObjectName("DraftFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(9, 5, 9, 5)
        footer_layout.addWidget(
            QLabel(
                "보호 점수 = 능력치 + 추정 잠재력 + 1군 활용도 + "
                "포지션 희소성 + 연봉 신호 − 고연봉 부담"
            )
        )
        footer_layout.addStretch()
        footer_layout.addWidget(
            QLabel("1R 4억 · 2R 3억 · 3R 2억 · 4R 이하 1억")
        )
        root.addWidget(footer)

        self.refresh()
        self.setStyleSheet(self._style(colors))

    @staticmethod
    def _as_date(value):
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value or DRAFT_PREPARATION_DATE

    def set_game_date(self, value):
        self.current_date = self._as_date(value)
        self.refresh()

    def show_view(self, view):
        """뉴스에서 선택한 명단 또는 결과 탭만 보여 준다."""
        index = self.view_combo.findData(view)
        if index >= 0:
            self.view_combo.setCurrentIndex(index)
        self.refresh()

    def refresh(self, _index=None):
        state = self.service.settings()
        mode = state.get("mode", "ai")
        status = state.get("status", "not_prepared")

        status_text = {
            "not_prepared": "명단 생성 전",
            "prepared": "보호 명단 확정",
            "completed": "드래프트 종료",
        }.get(status, status)
        self.status_badge.setText(status_text)
        self.subtitle.setText(
            f"{self.current_date.strftime('%Y년 %m월 %d일')}  ·  "
            f"명단 확정 {DRAFT_PREPARATION_DATE.strftime('%m월 %d일')}  ·  "
            f"드래프트 {DRAFT_DATE.strftime('%m월 %d일')}"
        )
        pool = self.service.list_pool()
        results = self.service.list_results(mode)
        counts = {
            key: sum(1 for row in pool if row["classification"] == key)
            for key in ("available", "protected", "automatic_exempt")
        }
        for key in ("available", "protected", "automatic_exempt"):
            self.summary_cards[key].setText(f"{counts[key]}명")
        result_count = (
            len(results)
            if mode == "actual" or status == "completed" else 0
        )
        self.summary_cards["results"].setText(f"{result_count}명")

        view = self.view_combo.currentData()
        if mode == "actual" and view == "results":
            self._show_results(results)
        elif view == "results":
            self._show_results(results if status == "completed" else [])
        else:
            self._show_pool(pool, view)

    def _show_pool(self, pool, classification):
        team = self.team_combo.currentData()
        position = self.position_combo.currentData()
        query = self.search_input.text().strip().casefold()
        self.visible_rows = [
            row for row in pool
            if row["classification"] == classification
            and (not team or row["original_team"] == team)
            and (not position or row["position_group"] == position)
            and (not query or query in row["player_name"].casefold())
        ]
        self.table.setHorizontalHeaderLabels(
            [
                "선수", "원소속", "포지션", "나이", "입단",
                "1·2군", "종합", "잠재력", "연봉", "보호 점수", "판정",
            ]
        )
        self.table.setRowCount(len(self.visible_rows))
        for row_index, row in enumerate(self.visible_rows):
            values = (
                row["player_name"], row["original_team"],
                POSITION_LABELS.get(row["position_group"], row["position_group"]),
                row["age"], row["entry_year"] or "-",
                "1군" if row["roster_status"] else "2군",
                f"{row['overall']:.1f}", f"{row['potential']:.1f}",
                self._salary_text(row["salary"]),
                f"{row['protection_score']:.1f}",
                CLASSIFICATION_LABELS.get(row["classification"], row["reason"]),
            )
            tooltip = self._component_tooltip(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column in (9, 10):
                    item.setToolTip(tooltip if column == 9 else row["reason"])
                self.table.setItem(row_index, column, item)

    def _show_results(self, results):
        team = self.team_combo.currentData()
        position = self.position_combo.currentData()
        query = self.search_input.text().strip().casefold()
        self.visible_rows = [
            {**row, "_result": True} for row in results
            if (
                not team
                or row["selecting_team"] == team
                or row["original_team"] == team
            )
            and (not position or row["position_group"] == position)
            and (not query or query in row["player_name"].casefold())
        ]
        self.table.setHorizontalHeaderLabels(
            [
                "선수", "지명 구단", "원소속", "라운드", "순번",
                "포지션", "양도금", "비고", "", "", "",
            ]
        )
        self.table.setRowCount(len(self.visible_rows))
        for row_index, row in enumerate(self.visible_rows):
            values = (
                row["player_name"], row["selecting_team"],
                row["original_team"], f"{row['round_no']}R",
                row["pick_order"],
                POSITION_LABELS.get(row["position_group"], row["position_group"]),
                self._fee_text(row["fee"]), row.get("note") or "-", "", "", "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, column, item)

    @staticmethod
    def _component_tooltip(row):
        try:
            detail = json.loads(row.get("component_json") or "{}")
        except json.JSONDecodeError:
            detail = {}
        return (
            f"능력치 {detail.get('ability', 0):.1f}\n"
            f"잠재력 {detail.get('potential', 0):.1f}\n"
            f"활용도 {detail.get('utilization', 0):.1f}\n"
            f"포지션 희소성 {detail.get('position_scarcity', 0):.1f}\n"
            f"연봉 신호 +{detail.get('salary_signal', 0):.1f}\n"
            f"고연봉 부담 -{detail.get('salary_burden', 0):.1f}"
        )

    def _open_player(self, row, _column=None):
        if not (0 <= row < len(self.visible_rows)):
            return
        selected = self.visible_rows[row]
        player_id = selected.get("player_id")
        if player_id is None:
            return
        connection = sqlite3.connect(self.player_db_path)
        connection.row_factory = sqlite3.Row
        try:
            player = connection.execute(
                "SELECT * FROM players WHERE id = ?", (player_id,)
            ).fetchone()
        finally:
            connection.close()
        if player:
            self.player_requested.emit(dict(player))

    @staticmethod
    def _salary_text(value):
        value = int(value or 0)
        return f"{value / 10_000:.1f}억" if value >= 10_000 else f"{value:,}만"

    @staticmethod
    def _fee_text(value):
        return f"{int(value or 0) / 100_000_000:.0f}억"

    @staticmethod
    def _style(colors):
        return f"""
            QWidget {{
                color: #dce6ef; background-color: #0e141b;
                font-family: 'Malgun Gothic', 'Segoe UI';
            }}
            QFrame#DraftHeader {{
                background-color: #202630;
                border-bottom: 2px solid {colors['accent']};
            }}
            QLabel#DraftTitle {{ color: white; }}
            QLabel#StatusBadge {{
                color: white; background-color: {colors['accent']};
                border: 1px solid {colors['accent_light']};
                padding: 6px 14px; font-weight: 800;
            }}
            QFrame#DraftFilters, QFrame#DraftFooter {{
                background-color: #171e26; border: 1px solid #3b4652;
            }}
            QFrame#SummaryCard {{
                background-color: #1c242d; border: 1px solid #3c4854;
                border-left: 3px solid {colors['accent_light']};
            }}
            QLabel#CardLabel {{ color: #91a2b2; font-size: 11px; }}
            QLabel#CardValue {{ color: white; }}
            QPushButton#BackButton {{
                color: white; background-color: #222b35;
                border: 1px solid #4a5662; padding: 6px 16px;
                font-weight: 800; border-radius: 0;
            }}
            QPushButton:hover {{ color: white; border-color: {colors['accent_light']}; }}
            QPushButton:disabled {{ color: #75808a; background-color: #1b2229; }}
            QLineEdit, QComboBox {{
                min-height: 29px; color: white; background-color: #0e141b;
                border: 1px solid #46515d; padding: 0 8px; border-radius: 0;
            }}
            QComboBox QAbstractItemView {{
                color: white; background-color: #202630;
                selection-background-color: {colors['accent']};
            }}
            QTableWidget {{
                background-color: #111820; alternate-background-color: #18212a;
                border: 1px solid #38434e;
                selection-background-color: {colors['accent']};
            }}
            QHeaderView::section {{
                color: white; background-color: #252e38; border: none;
                border-bottom: 1px solid #4a5662; padding: 6px; font-weight: 800;
            }}
            QToolTip {{
                color: white; background-color: #111820;
                border: 1px solid {colors['accent_light']}; padding: 7px;
            }}
        """
