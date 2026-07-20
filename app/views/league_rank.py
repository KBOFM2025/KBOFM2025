"""FM 스타일의 메인 수신함과 구단 현황 대시보드."""

import sqlite3
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import TEAM_NAMES
from database.paths import PLAYERS_DB_PATH


INBOX_ITEMS = (
    {
        "category": "이사회",
        "sender": "구단 이사회",
        "time": "14:18",
        "headline": "구단 비전과 이번 시즌 목표 협의를 요청합니다",
        "body": "감독님의 부임을 환영합니다. 이사회는 이번 시즌 성과 목표와 장기적인 구단 운영 방향을 협의하고자 합니다. 아래 버튼을 눌러 목표별 조건을 확인하고 협상을 진행해 주십시오.",
    },
    {
        "category": "전력 분석",
        "sender": "데이터 분석팀",
        "time": "14:11",
        "headline": "2025 선수단 능력치 1차 분석 보고서",
        "body": "KBO 1군과 퓨처스 기록을 기준으로 선수단의 현재 능력을 산정했습니다. 표본이 부족한 선수는 신뢰도를 낮게 표시했으며 수비와 멘탈 평가는 추가 자료 확보 후 반영할 예정입니다.",
    },
    {
        "category": "선수단",
        "sender": "수석코치",
        "time": "14:05",
        "headline": "CAMP1 참가 선수와 포지션 경쟁 구도",
        "body": "1군과 C팀 선수의 초기 분류가 완료되었습니다. 캠프 기간에는 주전 경쟁과 체력 상태를 함께 확인하며 개막 엔트리 후보를 좁혀갈 예정입니다.",
    },
    {
        "category": "리그 소식",
        "sender": "KBO 뉴스센터",
        "time": "13:42",
        "headline": "10개 구단 비시즌 전력 정비 시작",
        "body": "한국시리즈 종료와 함께 각 구단이 다음 시즌 준비에 들어갔습니다. 선수 이동과 계약 소식은 확인되는 대로 구단 수신함에 전달됩니다.",
    },
    {
        "category": "의무",
        "sender": "메디컬 센터",
        "time": "12:30",
        "headline": "선수단 초기 컨디션 점검 안내",
        "body": "캠프 시작 전 전 선수의 컨디션과 부상 이력을 점검합니다. 현재 상세 의무 데이터는 준비 중이며 향후 선수 보고서와 연동됩니다.",
    },
)


class LeagueRankTab(QWidget):
    """수신함 목록과 선택 메시지, 선수·리그 정보를 한 화면에 표시한다."""

    board_vision_requested = Signal()
    club_info_requested = Signal(str)
    news_requested = Signal()
    notification_count_changed = Signal(int)

    def __init__(self, colors, team_name=None, db_path=None, save_database=None, save_id=None):
        super().__init__()
        self.colors = colors
        self.team_name = team_name
        self.db_path = db_path or PLAYERS_DB_PATH
        self.save_database = save_database
        self.save_id = save_id
        self.messages = [dict(message, is_board=index == 0) for index, message in enumerate(INBOX_ITEMS)]
        self.board_vision_reviewed = False
        self._build_ui()
        self._load_team_players()
        self._load_standings()
        self.inbox_list.setCurrentRow(0)

    def _build_ui(self):
        c = self.colors
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(9)

        section_nav = QFrame()
        section_nav.setObjectName("SectionNav")
        nav = QHBoxLayout(section_nav)
        nav.setContentsMargins(12, 0, 12, 0)
        nav.setSpacing(4)
        for index, text in enumerate(("수신함", "소셜 피드", "구단 뉴스", "리그 소식", "이적 시장", "세계 소식")):
            label = QLabel(text)
            label.setObjectName("ActiveSection" if index == 0 else "SectionItem")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nav.addWidget(label)
        nav.addStretch()
        root.addWidget(section_nav)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(2)
        root.addWidget(splitter, 1)

        inbox = QFrame()
        inbox.setObjectName("InboxPanel")
        inbox.setMinimumWidth(330)
        inbox.setMaximumWidth(430)
        inbox_layout = QVBoxLayout(inbox)
        inbox_layout.setContentsMargins(0, 0, 0, 0)
        inbox_layout.setSpacing(0)

        inbox_header = QFrame()
        inbox_header.setObjectName("InboxHeader")
        header_layout = QHBoxLayout(inbox_header)
        header_layout.setContentsMargins(14, 10, 12, 10)
        all_items = QLabel("⌕  모든 항목")
        all_items.setObjectName("InboxFilter")
        header_layout.addWidget(all_items)
        header_layout.addStretch()
        self.inbox_count = QLabel(f"{len(self.messages)}")
        self.inbox_count.setObjectName("InboxCount")
        header_layout.addWidget(self.inbox_count)
        inbox_layout.addWidget(inbox_header)

        day = QLabel("오늘  ·  받은 메시지")
        day.setObjectName("InboxDay")
        inbox_layout.addWidget(day)

        self.inbox_list = QListWidget()
        self.inbox_list.setObjectName("InboxList")
        self.inbox_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._populate_inbox()
        self.inbox_list.currentRowChanged.connect(self._show_message)
        self.inbox_list.itemDoubleClicked.connect(
            lambda _item: self._activate_current_message()
        )
        inbox_layout.addWidget(self.inbox_list, 1)
        splitter.addWidget(inbox)

        detail = QFrame()
        detail.setObjectName("MessagePanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(18, 14, 18, 14)
        detail_layout.setSpacing(10)

        message_meta = QHBoxLayout()
        self.sender_badge = QLabel("구단")
        self.sender_badge.setObjectName("SenderBadge")
        self.sender_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sender_badge.setFixedSize(48, 48)
        message_meta.addWidget(self.sender_badge)
        sender_column = QVBoxLayout()
        self.sender_label = QLabel()
        self.sender_label.setObjectName("Sender")
        self.category_label = QLabel()
        self.category_label.setObjectName("MessageCategory")
        sender_column.addWidget(self.sender_label)
        sender_column.addWidget(self.category_label)
        message_meta.addLayout(sender_column)
        message_meta.addStretch()
        self.message_time = QLabel()
        self.message_time.setObjectName("MessageTime")
        message_meta.addWidget(self.message_time)
        detail_layout.addLayout(message_meta)

        self.headline_label = QLabel()
        self.headline_label.setObjectName("MessageHeadline")
        self.headline_label.setWordWrap(True)
        detail_layout.addWidget(self.headline_label)

        self.body_label = QLabel()
        self.body_label.setObjectName("MessageBody")
        self.body_label.setWordWrap(True)
        detail_layout.addWidget(self.body_label)

        data_split = QSplitter(Qt.Orientation.Horizontal)
        data_split.setChildrenCollapsible(False)
        data_split.setHandleWidth(8)

        players_card = self._data_card("주요 선수 · 현재 선수단")
        self.player_table = QTableWidget()
        self._configure_table(self.player_table)
        self.player_table.setColumnCount(4)
        self.player_table.setHorizontalHeaderLabels(["선수", "포지션", "나이", "종합"])
        self.player_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.player_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        players_card.layout().addWidget(self.player_table)
        data_split.addWidget(players_card)

        standings_card = self._data_card("KBO 리그 순위")
        self.standings_table = QTableWidget()
        self._configure_table(self.standings_table)
        self.standings_table.setColumnCount(5)
        self.standings_table.setHorizontalHeaderLabels(["순위", "구단", "승", "패", "승률"])
        self.standings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4):
            self.standings_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.standings_table.cellClicked.connect(self._open_standings_club)
        standings_card.layout().addWidget(self.standings_table)
        data_split.addWidget(standings_card)
        data_split.setSizes((620, 520))
        detail_layout.addWidget(data_split, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.message_action_button = QPushButton("이사회 목표 협상  ›")
        self.message_action_button.setObjectName("PrimaryAction")
        self.message_action_button.clicked.connect(self._activate_current_message)
        actions.addWidget(self.message_action_button)
        league_button = QPushButton("리그 순위표  ›")
        league_button.setObjectName("SecondaryAction")
        actions.addWidget(league_button)
        detail_layout.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setSizes((370, 1000))

        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QFrame#SectionNav {{ background-color: #171d24; border-bottom: 1px solid #35414f; }}
            QLabel#SectionItem, QLabel#ActiveSection {{ color: #a9b4c1; padding: 11px 15px; font-size: 14px; }}
            QLabel#ActiveSection {{ color: white; border-bottom: 3px solid {c['accent']}; font-weight: 700; }}
            QFrame#InboxPanel, QFrame#MessagePanel {{ background-color: #171c22; border: 1px solid #39434e; border-radius: 8px; }}
            QFrame#InboxHeader {{ background-color: #20262d; border-bottom: 1px solid #39434e; }}
            QLabel#InboxFilter {{ color: #e8eef5; font-size: 15px; font-weight: 600; }}
            QLabel#InboxCount {{ color: white; background-color: {c['accent']}; border-radius: 10px; padding: 2px 8px; font-weight: 700; }}
            QLabel#InboxDay {{ color: #aeb9c5; background-color: #12171c; padding: 9px 14px; font-size: 13px; font-weight: 600; }}
            QListWidget#InboxList {{ color: #dce4ec; background-color: #171c22; border: none; outline: none; font-size: 13px; }}
            QListWidget#InboxList::item {{ border-bottom: 1px solid #303943; padding: 11px 14px; }}
            QListWidget#InboxList::item:hover {{ background-color: #242b33; }}
            QListWidget#InboxList::item:selected {{ color: white; background-color: {c['tab_selected']}; border-left: 4px solid {c['accent_light']}; }}
            QLabel#SenderBadge {{ color: white; background-color: {c['accent']}; border-radius: 24px; font-size: 13px; font-weight: 800; }}
            QLabel#Sender {{ color: #f4f7fb; font-size: 15px; font-weight: 700; }}
            QLabel#MessageCategory, QLabel#MessageTime {{ color: #8492a1; font-size: 12px; }}
            QLabel#MessageHeadline {{ color: white; border-top: 1px solid #37414c; padding-top: 12px; font-size: 21px; font-weight: 700; }}
            QLabel#MessageBody {{ color: #c8d1da; padding: 4px 0 10px 0; font-size: 14px; }}
            QFrame#DataCard {{ background-color: #20262d; border: 1px solid #343e49; border-radius: 7px; }}
            QLabel#DataTitle {{ color: {c['accent_light']}; padding: 3px 2px 7px 2px; font-size: 15px; font-weight: 700; }}
            QTableWidget {{ color: #e2e8ef; background-color: #1b2026; alternate-background-color: #23292f; border: none; font-size: 13px; }}
            QHeaderView::section {{ color: #9eacba; background-color: #151a1f; border: none; border-bottom: 1px solid #39434e; padding: 7px; font-size: 12px; font-weight: 600; }}
            QPushButton#PrimaryAction {{ color: white; background-color: {c['accent']}; border-color: {c['accent_light']}; }}
            QPushButton#SecondaryAction {{ color: {c['accent_light']}; background-color: transparent; border-color: {c['accent']}; }}
        """)

    @staticmethod
    def _data_card(title):
        card = QFrame()
        card.setObjectName("DataCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 9, 11, 11)
        layout.setSpacing(5)
        label = QLabel(title)
        label.setObjectName("DataTitle")
        layout.addWidget(label)
        return card

    @staticmethod
    def _configure_table(table):
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(35)
        table.horizontalHeader().setSectionsMovable(False)

    def _show_message(self, row):
        if row < 0 or row >= len(self.messages):
            return
        message = self.messages[row]
        self.sender_label.setText(message["sender"])
        self.category_label.setText(message["category"])
        self.message_time.setText(f'오늘  {message["time"]}')
        self.headline_label.setText(message["headline"])
        self.body_label.setText(message["body"])
        is_board_message = bool(message.get("is_board"))
        is_news_message = message.get("news_id") is not None
        self.message_action_button.setVisible(is_board_message or is_news_message)
        self.message_action_button.setEnabled(is_board_message or is_news_message)
        if is_board_message:
            self.message_action_button.setText(
                "이사회 목표 다시 보기  ›"
                if self.board_vision_reviewed
                else "이사회 목표 협상  ›"
            )
        elif is_news_message:
            self.message_action_button.setText("전체 뉴스 보기  ›")
            if not message.get("is_read") and self.save_database and self.save_id is not None:
                self.save_database.mark_daily_news_read(self.save_id, message["news_id"])
                message["is_read"] = 1
                item = self.inbox_list.item(row)
                if item is not None and item.text().startswith("●  "):
                    item.setText(item.text()[3:])
                self._update_unread_count()

    def _activate_current_message(self):
        row = self.inbox_list.currentRow()
        if row < 0 or row >= len(self.messages):
            return
        message = self.messages[row]
        if message.get("is_board"):
            self.board_vision_requested.emit()
        elif message.get("news_id") is not None:
            self.news_requested.emit()

    def mark_board_vision_reviewed(self):
        self.board_vision_reviewed = True
        board_row = next((index for index, message in enumerate(self.messages) if message.get("is_board")), -1)
        item = self.inbox_list.item(board_row) if board_row >= 0 else None
        if item is not None and "[확인 완료]" not in item.text():
            item.setText(f"[확인 완료]  {item.text()}")
        self.message_action_button.setText("이사회 목표 다시 보기  ›")

    def set_save_id(self, save_id):
        self.save_id = save_id
        self.refresh_notifications()

    def refresh_notifications(self):
        dynamic = []
        if self.save_database and self.save_id is not None:
            for news in self.save_database.list_daily_news(self.save_id):
                if news["category"] == "의료 센터" and (
                    "발생 당시 소속은 2군," in news["body"] or "기존 2군 선수단" in news["body"]
                ):
                    continue
                dynamic.append({
                    "category": news["category"],
                    "sender": "메디컬 센터" if news["category"] == "의료 센터" else "KBO 뉴스센터",
                    "time": news["news_date"].replace("-", "."),
                    "headline": news["headline"], "body": news["body"],
                    "news_id": news["id"], "is_read": int(news["is_read"]), "is_board": False,
                })
                if len(dynamic) >= 30:
                    break
        static = [dict(message, is_board=index == 0) for index, message in enumerate(INBOX_ITEMS)]
        self.messages = dynamic + static
        self._populate_inbox()
        self._update_unread_count()

    def _populate_inbox(self):
        if not hasattr(self, "inbox_list"):
            return
        self.inbox_list.blockSignals(True)
        self.inbox_list.clear()
        for message in self.messages:
            unread = "●  " if message.get("news_id") is not None and not message.get("is_read") else ""
            item = QListWidgetItem(f'{unread}{message["sender"]}     {message["time"]}\n{message["headline"]}')
            item.setSizeHint(QSize(320, 88))
            self.inbox_list.addItem(item)
        self.inbox_list.blockSignals(False)
        self.inbox_count.setText(str(len(self.messages))) if hasattr(self, "inbox_count") else None

    def _update_unread_count(self):
        if self.save_database and self.save_id is not None:
            unread = self.save_database.unread_daily_news_count(self.save_id)
        else:
            unread = 0
        self.notification_count_changed.emit(unread)

    def _load_team_players(self):
        if not self.db_path or not Path(self.db_path).exists():
            return
        connection = sqlite3.connect(self.db_path)
        try:
            rows = connection.execute(
                """
                SELECT name, pos, age,
                       CAST((COALESCE(con, 0) + COALESCE(pow, 0)) / 2 AS INTEGER) AS total
                FROM players
                WHERE (? IS NULL OR team = ?)
                ORDER BY status DESC, total DESC, name
                LIMIT 10
                """,
                (self.team_name, self.team_name),
            ).fetchall()
        finally:
            connection.close()
        self.player_table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value if value is not None else "-"))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.player_table.setItem(row_index, column, item)

    def _load_standings(self):
        self.standings_table.setRowCount(len(TEAM_NAMES))
        for row, team in enumerate(TEAM_NAMES):
            values = (row + 1, team, 0, 0, "0.000")
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(f"{team} 구단 정보 열기")
                if column != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.standings_table.setItem(row, column, item)

    def _open_standings_club(self, row, _column):
        item = self.standings_table.item(row, 1)
        if item is not None:
            self.club_info_requested.emit(item.text())
