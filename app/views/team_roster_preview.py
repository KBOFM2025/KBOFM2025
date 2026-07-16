"""새 게임 구단 선택 화면에 삽입되는 선수단 미리보기."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database import PLAYERS_DB_PATH
from app.views.team_manage.player_profile import PlayerProfilePage


POSITION_TABS = (
    ("전체", None),
    ("투수", "P"),
    ("포수", "C"),
    ("내야수", "IF"),
    ("외야수", "OF"),
)
POSITION_NAMES = {"P": "투수", "C": "포수", "IF": "내야수", "OF": "외야수"}


def load_team_players(team_name):
    """기준 구단 소속 선수를 공식 포지션 순서로 반환한다."""
    connection = sqlite3.connect(PLAYERS_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM players
                WHERE team = ?
                ORDER BY CASE position_group
                    WHEN 'P' THEN 1 WHEN 'C' THEN 2
                    WHEN 'IF' THEN 3 WHEN 'OF' THEN 4 ELSE 5 END,
                    name, kbo_player_id
                """,
                (team_name,),
            )
        ]
    finally:
        connection.close()


class TeamRosterPreviewWidget(QFrame):
    """선택 화면을 떠나지 않고 구단별 선수단을 보여주는 인라인 위젯."""

    profile_mode_changed = Signal(bool)

    def __init__(self, team_name, colors, parent=None):
        super().__init__(parent)
        self.setObjectName("RosterPreview")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.view_stack = QStackedWidget()
        outer_layout.addWidget(self.view_stack)

        self.roster_page = QWidget()
        layout = QVBoxLayout(self.roster_page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        title_column = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Malgun Gothic", 17, QFont.Bold))
        title_column.addWidget(self.title_label)
        subtitle = QLabel("2025년 10월 31일 기준 · 생년월일은 KBO 공식 프로필 기준")
        subtitle.setStyleSheet("color: #8fa3b8; font-size: 11px;")
        title_column.addWidget(subtitle)
        heading.addLayout(title_column)
        heading.addStretch()
        self.total_label = QLabel()
        heading.addWidget(self.total_label)
        layout.addLayout(heading)

        summary = QHBoxLayout()
        summary.setSpacing(8)
        self.position_count_labels = {}
        for code in ("P", "C", "IF", "OF"):
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                "color: #dbe7f3; background-color: #101f31; "
                "border-radius: 7px; padding: 8px; font-weight: bold;"
            )
            self.position_count_labels[code] = label
            summary.addWidget(label)
        layout.addLayout(summary)

        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(390)
        layout.addWidget(self.tabs)

        guide = QLabel("신인 · 외국인 선수는 이름 옆 배지로 표시됩니다.")
        guide.setStyleSheet("color: #718096; font-size: 10px;")
        layout.addWidget(guide)

        self.view_stack.addWidget(self.roster_page)
        self.profile_page = None

        self.set_team(team_name, colors)

    def set_team(self, team_name, colors):
        """현재 표를 선택한 구단의 DB 선수 목록으로 교체한다."""
        self._replace_profile_page(colors)
        players = load_team_players(team_name)
        self.players_by_id = {player["id"]: player for player in players}
        self.title_label.setText(f"{team_name} 전체 선수단 미리보기")
        self.title_label.setStyleSheet(f"color: {colors['accent_light']};")
        self.total_label.setText(f"총 {len(players)}명")
        self.total_label.setStyleSheet(
            f"color: white; background-color: {colors['accent']}; "
            "border-radius: 11px; padding: 7px 13px; font-weight: bold;"
        )

        for code, label in self.position_count_labels.items():
            count = sum(player["position_group"] == code for player in players)
            label.setText(f"{POSITION_NAMES[code]}  {count}명")

        while self.tabs.count():
            page = self.tabs.widget(0)
            self.tabs.removeTab(0)
            page.deleteLater()
        for tab_name, position_group in POSITION_TABS:
            tab_players = (
                players
                if position_group is None
                else [p for p in players if p["position_group"] == position_group]
            )
            self.tabs.addTab(
                self._create_roster_table(tab_players),
                f"{tab_name} {len(tab_players)}",
            )
        self.tabs.setCurrentIndex(0)
        self._show_roster()
        self.setStyleSheet(self._style_sheet(colors))

    def _replace_profile_page(self, colors):
        """선택 구단이 바뀌면 상세 페이지 팔레트도 해당 구단색으로 교체한다."""
        if self.profile_page is not None:
            self.view_stack.removeWidget(self.profile_page)
            self.profile_page.deleteLater()
        self.profile_page = PlayerProfilePage(colors)
        self.profile_page.back_requested.connect(self._show_roster)
        self.view_stack.addWidget(self.profile_page)

    def _create_roster_table(self, players):
        table = QTableWidget(len(players), 6)
        table.setHorizontalHeaderLabels(
            ["선수", "포지션", "생년월일", "만 나이", "투타", "신장 / 체중"]
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)

        for row_index, player in enumerate(players):
            badges = []
            if player["is_rookie"]:
                badges.append("신인")
            if player["is_foreign"]:
                badges.append("외국인")
            display_name = player["name"]
            if badges:
                display_name += f"  ·  {' / '.join(badges)}"
            size = "-"
            if player["height_cm"] and player["weight_kg"]:
                size = f'{player["height_cm"]}cm / {player["weight_kg"]}kg'
            values = (
                display_name,
                POSITION_NAMES.get(player["position_group"], player["position_group"]),
                player["birth_date"] or "-",
                f'{player["age"]}세',
                player["bats_throws"] or "-",
                size,
            )
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, player["id"])
                table.setItem(row_index, column_index, item)

        table.cellClicked.connect(
            lambda row, column, source=table: self._show_player(source, row)
            if column == 0 else None
        )

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _show_player(self, table, row):
        player_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        player = self.players_by_id.get(player_id)
        if player:
            self.profile_page.set_player(player)
            self.view_stack.setCurrentWidget(self.profile_page)
            self.profile_mode_changed.emit(True)

    def _show_roster(self):
        self.view_stack.setCurrentWidget(self.roster_page)
        self.profile_mode_changed.emit(False)

    @staticmethod
    def _style_sheet(colors):
        return f"""
            QFrame#RosterPreview {{
                background-color: #0b1828;
                border: 1px solid {colors['accent']};
                border-radius: 11px;
            }}
            QLabel {{ color: #f8fafc; font-family: 'Malgun Gothic'; border: none; }}
            QTabWidget::pane {{
                background-color: #0d1b2a;
                border: 1px solid #263b52;
                border-radius: 7px;
            }}
            QTabBar::tab {{
                color: #9fb2c7; background-color: #101f31;
                border: 1px solid #263b52; padding: 9px 17px;
                font-family: 'Malgun Gothic'; font-weight: bold;
            }}
            QTabBar::tab:selected {{ color: white; background-color: {colors['accent']}; }}
            QTableWidget {{
                color: #dbe7f3; background-color: #0d1b2a;
                alternate-background-color: #101f31; border: none;
                selection-background-color: {colors['accent']};
                font-family: 'Malgun Gothic'; font-size: 12px;
            }}
            QHeaderView::section {{
                color: #dbe7f3; background-color: #162a40; border: none;
                border-bottom: 1px solid #30445c; padding: 8px;
                font-family: 'Malgun Gothic'; font-weight: bold;
            }}
        """
