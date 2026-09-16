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
from app.player_ratings import overall_rating
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
        root.setContentsMargins(7, 6, 7, 7)
        self.stack = QStackedWidget()
        self.transition = FadeStackTransition(self.stack, self)
        root.addWidget(self.stack)

        self.search_page = QWidget()
        layout = QVBoxLayout(self.search_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("선수 탐색")
        title.setFont(QFont("Malgun Gothic", 25, QFont.Bold))
        title.setStyleSheet(f"color: {colors['accent_light']};")
        layout.addWidget(title)
        subtitle = QLabel("스카우팅 조건을 먼저 설정한 뒤 KBO 선수 데이터베이스를 탐색합니다.")
        subtitle.setStyleSheet("color: #91a4b7; font-size: 15px;")
        layout.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(12)
        filters = QFrame()
        filters.setObjectName("SearchFilters")
        filters.setMinimumWidth(255)
        filters.setMaximumWidth(310)
        filter_layout = QVBoxLayout(filters)
        filter_layout.setContentsMargins(17, 17, 17, 17)
        filter_layout.setSpacing(8)
        filter_title = QLabel("검색 조건")
        filter_title.setObjectName("FilterTitle")
        filter_layout.addWidget(filter_title)
        filter_help = QLabel("원하는 조건을 조합하면 해당 선수만 목록에 표시됩니다.")
        filter_help.setObjectName("FilterHelp")
        filter_help.setWordWrap(True)
        filter_layout.addWidget(filter_help)
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
        self.squad_combo = QComboBox()
        self.squad_combo.addItem("전체 선수단", None)
        self.squad_combo.addItem("1군", "1군")
        self.squad_combo.addItem("C팀·퓨처스", "reserve")
        self.origin_combo = QComboBox()
        self.origin_combo.addItem("국적 구분 없음", None)
        self.origin_combo.addItem("국내 선수", "domestic")
        self.origin_combo.addItem("외국인 선수", "foreign")
        self.rating_combo = QComboBox()
        for label, value in (("능력 제한 없음", 0), ("현재 능력 12+", 12), ("현재 능력 14+", 14), ("현재 능력 16+", 16)):
            self.rating_combo.addItem(label, value)
        search_button = QPushButton("검색")
        search_button.setObjectName("SearchButton")
        search_button.clicked.connect(self.search)
        reset_button = QPushButton("조건 초기화")
        reset_button.setObjectName("ResetButton")
        reset_button.clicked.connect(self.reset_filters)
        filter_widgets = (
            ("선수 이름", self.name_input), ("소속 구단", self.team_combo),
            ("주요 포지션", self.position_combo), ("연령", self.age_combo),
            ("선수단", self.squad_combo), ("선수 구분", self.origin_combo),
            ("현재 능력", self.rating_combo),
        )
        for label, widget in filter_widgets:
            field_label = QLabel(label)
            field_label.setObjectName("FieldLabel")
            filter_layout.addWidget(field_label)
            filter_layout.addWidget(widget)
        filter_layout.addSpacing(5)
        filter_layout.addWidget(search_button)
        filter_layout.addWidget(reset_button)
        filter_layout.addStretch()
        body.addWidget(filters)

        results = QFrame()
        results.setObjectName("SearchResults")
        result_layout = QVBoxLayout(results)
        result_layout.setContentsMargins(14, 13, 14, 14)
        self.result_label = QLabel("검색 대기")
        self.result_label.setObjectName("ResultLabel")
        result_layout.addWidget(self.result_label)
        self.result_stack = QStackedWidget()
        self.empty_state = QFrame()
        self.empty_state.setObjectName("EmptyState")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.addStretch()
        empty_icon = QLabel("⌕")
        empty_icon.setObjectName("EmptyIcon")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = QLabel("검색 조건을 설정해 주세요")
        empty_title.setObjectName("EmptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_text = QLabel("왼쪽 조건에서 구단·포지션·연령·선수단을 선택한 뒤 검색을 누르면 결과가 표시됩니다.")
        empty_text.setObjectName("EmptyText")
        empty_text.setWordWrap(True)
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_text)
        empty_layout.addStretch()
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
        self.result_stack.addWidget(self.empty_state)
        self.result_stack.addWidget(self.table)
        result_layout.addWidget(self.result_stack, 1)
        body.addWidget(results, 1)
        layout.addLayout(body, 1)

        self.profile_page = PlayerProfilePage(colors)
        self.profile_page.back_requested.connect(lambda: self.transition.to_widget(self.search_page))
        self.stack.addWidget(self.search_page)
        self.stack.addWidget(self.profile_page)
        self.name_input.returnPressed.connect(self.search)
        self.result_stack.setCurrentWidget(self.empty_state)
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
        squad = self.squad_combo.currentData()
        origin = self.origin_combo.currentData()
        minimum_rating = int(self.rating_combo.currentData() or 0)
        self.filtered_players = [
            player for player in self.players
            if (not query or query in str(player.get("name", "")).casefold())
            and (not team or player.get("team") == team)
            and (not position or player.get("position_group") == position)
            and (age_group != "under30" or int(player.get("age") or 0) < 30)
            and (age_group != "over30" or int(player.get("age") or 0) >= 30)
            and (not squad or (int(player.get("status") or 0) == 1 if squad == "1군" else int(player.get("status") or 0) != 1))
            and (origin != "domestic" or not bool(player.get("is_foreign")))
            and (origin != "foreign" or bool(player.get("is_foreign")))
            and int(overall_rating(player)) >= minimum_rating
        ]
        self.filtered_players.sort(key=lambda p: (p.get("team", ""), p.get("name", "")))
        self.result_label.setText(f"검색 결과 · {len(self.filtered_players)}명")
        self.result_stack.setCurrentWidget(self.table)
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

    def reset_filters(self):
        self.name_input.clear()
        for combo in (
            self.team_combo, self.position_combo, self.age_combo,
            self.squad_combo, self.origin_combo, self.rating_combo,
        ):
            combo.setCurrentIndex(0)
        self.filtered_players = []
        self.table.setRowCount(0)
        self.result_label.setText("검색 대기")
        self.result_stack.setCurrentWidget(self.empty_state)

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
            QWidget {{ background-color: #09131f; color: #dce6ef; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QFrame#SearchFilters, QFrame#SearchResults {{ background-color: #111d29; border: 1px solid #2b4053; border-radius: 7px; }}
            QLabel#FilterTitle {{ color: white; font-size: 18px; font-weight: 800; }}
            QLabel#FilterHelp {{ color: #8194a6; font-size: 13px; padding-bottom: 7px; }}
            QLabel#FieldLabel {{ color: #a9b8c7; font-size: 13px; font-weight: 700; padding-top: 3px; }}
            QLabel#ResultLabel {{ color: {colors['accent_light']}; font-size: 15px; font-weight: 800; padding: 3px 2px 8px 2px; }}
            QLineEdit, QComboBox {{ min-height: 35px; background-color: #0b141e; border: 1px solid #3b5063; border-radius: 4px; padding: 0 9px; }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {colors['accent_light']}; }}
            QPushButton {{ min-height: 36px; border-radius: 4px; padding: 0 14px; font-weight: 800; }}
            QPushButton#SearchButton {{ color: white; background-color: {colors['accent']}; border: 1px solid {colors['accent_light']}; }}
            QPushButton#ResetButton {{ color: #aebdcb; background-color: #1b2a38; border: 1px solid #3b5063; }}
            QFrame#EmptyState {{ background-color: #0d1823; border: 1px dashed #31475a; border-radius: 5px; }}
            QLabel#EmptyIcon {{ color: {colors['accent_light']}; font-size: 52px; }}
            QLabel#EmptyTitle {{ color: white; font-size: 18px; font-weight: 800; }}
            QLabel#EmptyText {{ color: #8295a7; font-size: 14px; padding: 0 40px; }}
            QTableWidget {{ background-color: #0d1b2a; alternate-background-color: #101f31; border: 1px solid #263b52; border-radius: 4px; selection-background-color: {colors['accent']}; }}
            QHeaderView::section {{ background-color: #162a40; border: none; border-bottom: 1px solid #38506a; padding: 10px; font-weight: 700; }}
        """
