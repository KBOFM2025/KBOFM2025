"""구단 정보에서 진입하는 전체 화면 선수단 명단."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.config import TEAM_EMOJIS
from app.views.team_manage.player_profile import _display_rating
from database import PLAYERS_DB_PATH


FINAL_REGULAR_GAME_DATES = {
    "LG 트윈스": "2025년 10월 1일",
    "한화 이글스": "2025년 10월 3일",
    "SSG 랜더스": "2025년 10월 4일",
    "삼성 라이온즈": "2025년 10월 4일",
    "NC 다이노스": "2025년 10월 4일",
    "KT 위즈": "2025년 10월 3일",
    "롯데 자이언츠": "2025년 9월 30일",
    "KIA 타이거즈": "2025년 10월 4일",
    "두산 베어스": "2025년 9월 30일",
    "키움 히어로즈": "2025년 9월 30일",
}


class ClubSquadPage(QWidget):
    back_requested = Signal()
    club_info_requested = Signal(str)
    player_requested = Signal(object)

    def __init__(self, team_name, colors, db_path=None, save_database=None, save_id=None, parent=None):
        super().__init__(parent)
        self.team_name = team_name
        self.colors = colors
        self.db_path = db_path or PLAYERS_DB_PATH
        self.save_database = save_database
        self.save_id = save_id
        self.players = self._load_players()
        self.simulation_states = self._load_simulation_states()
        self.visible_players = []
        self.status_buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(12)
        header = QFrame()
        header.setObjectName("SquadHeader")
        header_layout = QHBoxLayout(header)
        back = QPushButton("←  이전 화면")
        back.setObjectName("BackButton")
        back.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(back)
        emblem = QLabel(TEAM_EMOJIS.get(team_name, "⚾"))
        emblem.setFont(QFont("Segoe UI Emoji", 30))
        header_layout.addWidget(emblem)
        heading = QVBoxLayout()
        title = QLabel(f"{team_name} 선수단")
        title.setObjectName("SquadTitle")
        title.setFont(QFont("Noto Sans KR", 25, QFont.Bold))
        heading.addWidget(title)
        self.summary = QLabel()
        heading.addWidget(self.summary)
        header_layout.addLayout(heading)
        header_layout.addStretch()
        layout.addWidget(header)

        sections = QHBoxLayout()
        club_section = QPushButton("구단 정보")
        club_section.setObjectName("SectionButton")
        club_section.clicked.connect(lambda: self.club_info_requested.emit(self.team_name))
        squad_section = QPushButton("선수단 정보")
        squad_section.setObjectName("SectionActive")
        sections.addWidget(club_section)
        sections.addWidget(squad_section)
        sections.addStretch()
        layout.addLayout(sections)

        basis = QFrame()
        basis.setObjectName("RosterBasis")
        basis_layout = QHBoxLayout(basis)
        basis_layout.setContentsMargins(14, 9, 14, 9)
        basis_title = QLabel("2025 최종 선수단 편성")
        basis_title.setObjectName("RosterBasisTitle")
        basis_layout.addWidget(basis_title)
        basis_layout.addWidget(QLabel(f"정규시즌 최종 경기 · {FINAL_REGULAR_GAME_DATES.get(team_name, '2025년 시즌 종료일')} KBO 등록 현황 기준"))
        basis_layout.addStretch()
        self.roster_counts = QLabel()
        self.roster_counts.setObjectName("RosterCounts")
        basis_layout.addWidget(self.roster_counts)
        layout.addWidget(basis)

        filters = QHBoxLayout()
        self.status_group = QButtonGroup(self)
        for index, (label, value) in enumerate((("1군 선수단", 1), ("2군 선수단", 0))):
            button = QPushButton(label)
            button.setObjectName("RosterButton")
            button.setCheckable(True)
            button.setProperty("roster_status", value)
            self.status_group.addButton(button, index)
            self.status_buttons[value] = button
            filters.addWidget(button)
            if index == 0:
                button.setChecked(True)
        filters.addStretch()
        filters.addWidget(QLabel("포지션"))
        self.position_combo = QComboBox()
        self.position_combo.setObjectName("PositionCombo")
        for label, value in (("전체", None), ("투수", "P"), ("포수", "C"), ("내야수", "IF"), ("외야수", "OF")):
            self.position_combo.addItem(label, value)
        self.position_combo.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.position_combo)
        self.status_group.idClicked.connect(self._apply_filter)
        layout.addLayout(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            ["선수명", "포지션", "나이", "종합", "컨디션", "경기 감각", "사기", "훈련조", "현재 역할", "상태"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.cellDoubleClicked.connect(self._open_player)
        self.table.cellClicked.connect(lambda row, column: self._open_player(row) if column == 0 else None)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 150)
        for column in (1, 2, 3, 4, 5, 6, 9):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for column in (7, 8):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self._apply_filter()
        self.setStyleSheet(self._style(colors))

    def _load_players(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute("SELECT * FROM players WHERE team = ? ORDER BY status DESC, position_group, name", (self.team_name,))]
        finally:
            connection.close()

    def _apply_filter(self, _button_id=None):
        button = self.status_group.checkedButton()
        roster_status = int(button.property("roster_status")) if button else 1
        position = self.position_combo.currentData()
        self.visible_players = [
            p for p in self.players
            if int(bool(p.get("status"))) == roster_status
            and (not position or p.get("position_group") == position)
        ]
        roster_name = "1군" if roster_status else "2군"
        assignments = self._load_assignments(roster_status)
        first_count = sum(1 for player in self.players if int(bool(player.get("status"))) == 1)
        second_count = len(self.players) - first_count
        self.status_buttons[1].setText(f"1군 선수단  {first_count}")
        self.status_buttons[0].setText(f"2군 선수단  {second_count}")
        self.roster_counts.setText(f"1군 {first_count}명  ·  2군 {second_count}명  ·  전체 {len(self.players)}명")
        self.summary.setText(f"{roster_name} 라인업 · {len(self.visible_players)}명 · 선수를 누르면 전체 보고서로 이동")
        self.table.setRowCount(len(self.visible_players))
        for row, player in enumerate(self.visible_players):
            ratings = self._ratings(player)
            overall = round(sum(ratings) / len(ratings), 1) if ratings else "-"
            state = self.simulation_states.get(player["id"], {})
            injury_days = int(state.get("injury_days", 0))
            status = f"{state.get('injury_type', '부상')} · {injury_days}일" if injury_days else "정상"
            values = (
                player.get("name", "-"), player.get("pos", "-"), player.get("age", "-"), overall,
                state.get("condition", "-"), state.get("match_sharpness", "-"), state.get("morale", "-"),
                state.get("squad_group", roster_name), assignments.get(player["id"], "대기"), status,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

    def refresh_players(self):
        """콜업·강등 결과를 포함해 현재 선수 DB에서 명단을 다시 읽는다."""
        self.players = self._load_players()
        self.simulation_states = self._load_simulation_states()
        self._apply_filter()

    def _load_simulation_states(self):
        if self.save_database is None or self.save_id is None:
            return {}
        return self.save_database.get_player_simulation_states(self.save_id, self.team_name)

    def _load_assignments(self, roster_status):
        if self.save_database is None or self.save_id is None:
            return {}
        return self.save_database.get_latest_team_assignments(
            self.save_id, self.team_name, roster_status
        )

    @staticmethod
    def _ratings(player):
        if player.get("position_group") == "P":
            return [_display_rating(player.get(key), True) for key in ("con", "pow", "eye", "def") if player.get(key) is not None]
        return [player.get(key) for key in ("contact", "power", "plate_discipline", "fielding_judgment") if player.get(key) is not None]

    def _open_player(self, row, _column=None):
        if 0 <= row < len(self.visible_players):
            self.player_requested.emit(self.visible_players[row])

    @staticmethod
    def _style(colors):
        return f"""
            QWidget {{ color: #dce6ef; background-color: #11161d; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QFrame#SquadHeader {{ background-color: #202630; border-bottom: 2px solid {colors['accent']}; }}
            QFrame#RosterBasis {{ background-color: #171e26; border: 1px solid #3b4652; border-left: 4px solid {colors['accent_light']}; border-radius: 5px; }}
            QLabel#RosterBasisTitle {{ color: white; font-weight: 800; padding-right: 10px; }}
            QLabel#RosterCounts {{ color: {colors['accent_light']}; font-weight: 800; }}
            QLabel#SquadTitle {{ color: white; }}
            QPushButton#BackButton, QPushButton#RosterButton {{ color: white; background-color: #202630; border: 1px solid #46515d; border-radius: 6px; padding: 9px 22px; font-weight: 700; }}
            QPushButton#BackButton:hover, QPushButton#RosterButton:hover, QPushButton#RosterButton:checked {{ background-color: {colors['accent']}; border-color: {colors['accent_light']}; }}
            QComboBox#PositionCombo {{ color: white; background-color: #202630; border: 1px solid {colors['accent']}; border-radius: 5px; padding: 7px 28px 7px 10px; min-width: 100px; }}
            QComboBox#PositionCombo QAbstractItemView {{ color: white; background-color: #202630; selection-background-color: {colors['accent']}; }}
            QPushButton#SectionActive, QPushButton#SectionButton {{ color: #c8d2dc; background-color: #1b2027; border: none; border-bottom: 2px solid #46515d; padding: 9px 24px; font-size: 14px; font-weight: 700; }}
            QPushButton#SectionActive {{ color: white; border-bottom-color: {colors['accent_light']}; background-color: #252c35; }}
            QPushButton#SectionButton:hover {{ color: white; background-color: #252c35; border-bottom-color: {colors['accent']}; }}
            QTableWidget {{ background-color: #151a20; alternate-background-color: #1d232b; border: 1px solid #38424d; selection-background-color: {colors['accent']}; }}
            QHeaderView::section {{ color: white; background-color: #252c35; border: none; border-bottom: 1px solid #46515d; padding: 9px; font-weight: 700; }}
        """
