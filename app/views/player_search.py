"""메인 세션에서 전체 리그 선수를 찾는 탐색 화면."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.config import TEAM_COLORS
from app.transitions import FadeStackTransition
from app.views.team_manage.player_profile import PlayerProfilePage
from database import PLAYERS_DB_PATH


class PlayerSearchPage(QWidget):
    player_requested = Signal(object)

    def __init__(self, colors, managed_team, save_database, save_id, db_path=None, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.managed_team = managed_team
        self.save_database = save_database
        self.save_id = save_id
        self.db_path = db_path or PLAYERS_DB_PATH
        self.players = self._load_players()
        self.filtered_players = []

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 24)
        self.stack = QStackedWidget()
        self.transition = FadeStackTransition(self.stack, self)
        root.addWidget(self.stack)

        self.search_page = QWidget()
        layout = QVBoxLayout(self.search_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("선수 탐색")
        title.setFont(QFont("Noto Sans KR", 25, QFont.Bold))
        title.setStyleSheet(f"color: {colors['accent_light']};")
        layout.addWidget(title)
        subtitle = QLabel("이름, 구단, 포지션과 연령대로 KBO 전체 선수를 검색합니다.")
        subtitle.setStyleSheet("color: #91a4b7; font-size: 13px;")
        layout.addWidget(subtitle)

        filters = QFrame()
        filters.setObjectName("SearchFilters")
        filter_layout = QHBoxLayout(filters)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("선수 이름 입력")
        self.name_input.setClearButtonEnabled(True)
        self.team_combo = QComboBox()
        self.team_combo.addItem("전체 구단", None)
        for team in TEAM_COLORS:
            self.team_combo.addItem(team, team)
        self.position_combo = QComboBox()
        for label, value in (("전체 포지션", None), ("투수", "P"), ("포수", "C"), ("내야수", "IF"), ("외야수", "OF")):
            self.position_combo.addItem(label, value)
        self.age_combo = QComboBox()
        self.age_combo.addItem("전체 연령", None)
        self.age_combo.addItem("30세 미만", "under30")
        self.age_combo.addItem("30세 이상", "over30")
        search_button = QPushButton("검색")
        search_button.clicked.connect(self.search)
        for widget in (self.name_input, self.team_combo, self.position_combo, self.age_combo, search_button):
            filter_layout.addWidget(widget)
        layout.addWidget(filters)

        self.result_label = QLabel()
        self.result_label.setStyleSheet("color: #aebdcb; font-size: 13px;")
        layout.addWidget(self.result_label)
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["선수", "구단", "포지션", "나이", "컨택/구위", "파워/제구", "선구/변화", "수비/체력", "생성 기준"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self._open_profile)
        self.table.cellClicked.connect(lambda row, column: self._open_profile(row) if column == 0 else None)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 9):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.profile_page = PlayerProfilePage(colors)
        self.profile_page.back_requested.connect(lambda: self.transition.to_widget(self.search_page))
        self.stack.addWidget(self.search_page)
        self.stack.addWidget(self.profile_page)
        self.name_input.returnPressed.connect(self.search)
        self.search()
        self.setStyleSheet(self._style(colors))

    def _load_players(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute("SELECT * FROM players")]
        finally:
            connection.close()

    def search(self):
        query = self.name_input.text().strip().casefold()
        team = self.team_combo.currentData()
        position = self.position_combo.currentData()
        age_group = self.age_combo.currentData()
        self.filtered_players = [
            player for player in self.players
            if (not query or query in str(player.get("name", "")).casefold())
            and (not team or player.get("team") == team)
            and (not position or player.get("position_group") == position)
            and (age_group != "under30" or int(player.get("age") or 0) < 30)
            and (age_group != "over30" or int(player.get("age") or 0) >= 30)
        ]
        self.filtered_players.sort(key=lambda p: (p.get("team", ""), p.get("name", "")))
        self.result_label.setText(f"검색 결과 · {len(self.filtered_players)}명")
        self.table.setRowCount(len(self.filtered_players))
        for row, player in enumerate(self.filtered_players):
            values = (
                player.get("name", "-"), player.get("team", "-"),
                player.get("pos", "-"), str(player.get("age", "-")),
                player.get("contact") or player.get("con") or "-",
                player.get("power") or player.get("pow") or "-",
                player.get("plate_discipline") or player.get("eye") or "-",
                player.get("fielding_judgment") or player.get("def") or "-",
                "원본" if player.get("team") == self.managed_team
                else ("고정" if int(player.get("age") or 0) >= 30 else "±2"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

    def _open_profile(self, row, _column=None):
        if 0 <= row < len(self.filtered_players):
            self.player_requested.emit(self.filtered_players[row])

    def select_team(self, team_name):
        index = self.team_combo.findData(team_name)
        if index >= 0:
            self.team_combo.setCurrentIndex(index)
        self.name_input.clear()
        self.search()
        self.transition.to_widget(self.search_page)

    def search_text(self, query):
        self.team_combo.setCurrentIndex(0)
        self.position_combo.setCurrentIndex(0)
        self.age_combo.setCurrentIndex(0)
        self.name_input.setText(query)
        self.search()
        self.transition.to_widget(self.search_page)

    def open_player(self, player):
        self.player_requested.emit(player)

    @staticmethod
    def _style(colors):
        return f"""
            QWidget {{ background-color: #09131f; color: #dce6ef; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QFrame#SearchFilters {{ background-color: #101e2e; border: 1px solid #30465d; border-radius: 9px; }}
            QLineEdit, QComboBox {{ min-height: 34px; background-color: #0c1825; border: 1px solid #30465d; border-radius: 6px; padding: 0 9px; }}
            QPushButton {{ min-height: 34px; background-color: {colors['accent']}; border-radius: 6px; padding: 0 18px; font-weight: 700; }}
            QTableWidget {{ background-color: #0d1b2a; alternate-background-color: #101f31; border: 1px solid #263b52; selection-background-color: {colors['accent']}; }}
            QHeaderView::section {{ background-color: #162a40; border: none; padding: 9px; font-weight: 700; }}
        """
