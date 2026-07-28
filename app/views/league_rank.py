"""FM 스타일의 메인 수신함과 뉴스 유형별 상세 대시보드."""

import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import TEAM_NAMES
from app.config.season_schedule import SEASON_EVENTS, phase_for
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
    player_requested = Signal(object)
    manager_event_requested = Signal(int)
    news_requested = Signal()
    squad_requested = Signal()
    calendar_requested = Signal()
    second_draft_requested = Signal(str)
    notification_count_changed = Signal(int)
    required_action_count_changed = Signal(int)

    def __init__(
        self,
        colors,
        team_name=None,
        db_path=None,
        save_database=None,
        save_id=None,
        appointment_date=None,
    ):
        super().__init__()
        self.colors = colors
        self.team_name = team_name
        self.db_path = db_path or PLAYERS_DB_PATH
        self.save_database = save_database
        self.save_id = save_id
        self._read_static_messages = set()
        if isinstance(appointment_date, str):
            appointment_date = date.fromisoformat(appointment_date)
        self.appointment_date = appointment_date
        self.current_date = None
        self.messages = [
            dict(
                message,
                received_date=(
                    self.appointment_date.isoformat()
                    if self.appointment_date is not None
                    else "0000-00-00"
                ),
                is_board=index == 0,
                requires_action=index == 0,
                resolved=index != 0,
            )
            for index, message in enumerate(INBOX_ITEMS)
        ]
        self.board_vision_reviewed = False
        self._build_ui()
        self._load_team_players()
        self._load_standings()
        first_row = self._row_for_message_index(0)
        if first_row is not None:
            self.inbox_list.setCurrentRow(first_row)
            self._show_message(first_row)

    def _build_ui(self):
        c = self.colors
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 6, 7, 7)
        root.setSpacing(5)

        section_nav = QFrame()
        section_nav.setObjectName("SectionNav")
        nav = QHBoxLayout(section_nav)
        nav.setContentsMargins(8, 0, 8, 0)
        nav.setSpacing(2)
        sections = (
            ("수신함", None),
            ("구단 뉴스", self.news_requested.emit),
            ("선수단", self.squad_requested.emit),
            ("일정", self.calendar_requested.emit),
        )
        for index, (text, callback) in enumerate(sections):
            button = QPushButton(text)
            button.setObjectName("ActiveSection" if index == 0 else "SectionItem")
            if callback is not None:
                button.clicked.connect(lambda _checked=False, action=callback: action())
            nav.addWidget(button)
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
        header_layout.setContentsMargins(10, 6, 9, 6)
        all_items = QLabel("⌕  모든 항목")
        all_items.setObjectName("InboxFilter")
        header_layout.addWidget(all_items)
        header_layout.addStretch()
        self.inbox_count = QLabel(f"{len(self.messages)}")
        self.inbox_count.setObjectName("InboxCount")
        header_layout.addWidget(self.inbox_count)
        inbox_layout.addWidget(inbox_header)

        day = QLabel("날짜별 받은 메시지")
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
        detail_layout.setContentsMargins(12, 9, 12, 10)
        detail_layout.setSpacing(6)

        message_meta = QHBoxLayout()
        self.sender_badge = QLabel("구단")
        self.sender_badge.setObjectName("SenderBadge")
        self.sender_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sender_badge.setFixedSize(38, 38)
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

        operations_strip = QFrame()
        operations_strip.setObjectName("OperationsStrip")
        operations_layout = QHBoxLayout(operations_strip)
        operations_layout.setContentsMargins(0, 0, 0, 0)
        operations_layout.setSpacing(1)
        self.phase_metric = self._metric_label("시즌 단계", "업무 시작 전")
        self.condition_metric = self._metric_label("1군 평균 컨디션", "-")
        self.injury_metric = self._metric_label("선수단 부상", "0명")
        self.task_metric = self._metric_label("필수 업무", "0건")
        for metric in (
            self.phase_metric, self.condition_metric,
            self.injury_metric, self.task_metric,
        ):
            operations_layout.addWidget(metric, 1)
        detail_layout.addWidget(operations_strip)
        self.operations_strip = operations_strip

        self.news_visual = QFrame()
        self.news_visual.setObjectName("NewsVisual")
        self.news_visual_layout = QVBoxLayout(self.news_visual)
        self.news_visual_layout.setContentsMargins(12, 12, 12, 12)
        self.news_visual_layout.setSpacing(10)
        self.news_visual.setVisible(False)
        detail_layout.addWidget(self.news_visual, 1)

        agenda_card = self._data_card("오늘의 구단 운영")
        self.agenda_card = agenda_card
        self.agenda_title = agenda_card.title_label
        self.today_agenda = QLabel()
        self.today_agenda.setObjectName("AgendaText")
        self.today_agenda.setWordWrap(True)
        agenda_card.layout().addWidget(self.today_agenda)
        detail_layout.addWidget(agenda_card)

        data_split = QSplitter(Qt.Orientation.Horizontal)
        data_split.setChildrenCollapsible(False)
        data_split.setHandleWidth(8)
        self.data_split = data_split

        players_card = self._data_card("1군 상태 · 대응이 필요한 선수")
        self.players_card = players_card
        self.players_title = players_card.title_label
        self.player_table = QTableWidget()
        self._configure_table(self.player_table)
        self.player_table.setColumnCount(5)
        self.player_table.setHorizontalHeaderLabels(["선수", "포지션", "컨디션", "피로", "현재 상태"])
        self.player_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.player_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.player_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.player_table.cellClicked.connect(self._open_dashboard_player)
        players_card.layout().addWidget(self.player_table)
        data_split.addWidget(players_card)

        standings_card = self._data_card("KBO 구단 운영 현황")
        self.standings_card = standings_card
        self.standings_title = standings_card.title_label
        self.standings_table = QTableWidget()
        self._configure_table(self.standings_table)
        self.standings_table.setColumnCount(5)
        self.standings_table.setHorizontalHeaderLabels(["구단", "단계", "컨디션", "부상", "전력 과제"])
        self.standings_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.standings_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
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
        league_button.setText("리그 뉴스 보기  ›")
        league_button.clicked.connect(lambda _checked=False: self.news_requested.emit())
        actions.addWidget(league_button)
        detail_layout.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setSizes((370, 1000))

        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QFrame#SectionNav {{ background-color: #171d24; border-bottom: 1px solid #35414f; }}
            QPushButton#SectionItem, QPushButton#ActiveSection {{ color: #a9b4c1; background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 4px 12px; font-size: 12px; }}
            QPushButton#SectionItem:hover {{ color: white; background: #202831; border-bottom-color: #586675; }}
            QPushButton#ActiveSection {{ color: white; border-bottom-color: {c['accent']}; font-weight: 700; }}
            QFrame#InboxPanel, QFrame#MessagePanel {{ background-color: #151a20; border: 1px solid #39434e; border-radius: 0; }}
            QFrame#InboxHeader {{ background-color: #20262d; border-bottom: 1px solid #39434e; }}
            QLabel#InboxFilter {{ color: #e8eef5; font-size: 12px; font-weight: 600; }}
            QLabel#InboxCount {{ color: white; background-color: {c['accent']}; border-radius: 1px; padding: 1px 7px; font-weight: 700; }}
            QLabel#InboxDay {{ color: #aeb9c5; background-color: #10151a; padding: 6px 10px; font-size: 11px; font-weight: 600; }}
            QListWidget#InboxList {{ color: #dce4ec; background-color: #151a20; border: none; outline: none; font-size: 12px; }}
            QListWidget#InboxList::item {{ border-bottom: 1px solid #303943; padding: 7px 10px; }}
            QListWidget#InboxList::item:hover {{ background-color: #242b33; }}
            QListWidget#InboxList::item:selected {{ background-color: {c['tab_selected']}; border-left: 4px solid {c['accent_light']}; }}
            QLabel#SenderBadge {{ color: white; background-color: {c['accent']}; border-radius: 1px; font-size: 11px; font-weight: 800; }}
            QLabel#Sender {{ color: #f4f7fb; font-size: 13px; font-weight: 700; }}
            QLabel#MessageCategory, QLabel#MessageTime {{ color: #8492a1; font-size: 11px; }}
            QLabel#MessageHeadline {{ color: white; border-top: 1px solid #37414c; padding-top: 9px; font-size: 18px; font-weight: 700; }}
            QLabel#MessageBody {{ color: #c8d1da; padding: 2px 0 7px 0; font-size: 12px; }}
            QFrame#DataCard {{ background-color: #1b2128; border: 1px solid #343e49; border-radius: 0; }}
            QFrame#OperationsStrip {{ background-color: #11161b; border: 1px solid #343e49; }}
            QLabel#OperationMetric {{ color: #dbe3eb; background-color: #1a2027; border-right: 1px solid #343e49; padding: 6px 9px; font-size: 11px; }}
            QLabel#AgendaText {{ color: #c8d1da; padding: 1px 2px 4px 2px; font-size: 11px; }}
            QLabel#DataTitle {{ color: {c['accent_light']}; padding: 2px 2px 5px 2px; font-size: 12px; font-weight: 700; }}
            QFrame#NewsVisual {{ background-color: #171d24; border: 1px solid #39434e; }}
            QFrame#NewsVisual[context="trade"] {{ background-color: #101a26; border-color: #31577d; }}
            QFrame#NewsVisual[context="fa"] {{ background-color: #111e19; border-color: #347151; }}
            QFrame#NewsVisual[context="medical"] {{ background-color: #211416; border-color: #793b43; }}
            QFrame#NewsVisual[context="meeting"] {{ background-color: #191522; border-color: #654b82; }}
            QFrame#NewsVisual[context="entry"] {{ background-color: #211912; border-color: #885629; }}
            QFrame#NewsVisual[context="board"] {{ background-color: #1e1a11; border-color: #796633; }}
            QFrame#NewsVisual[context="schedule"] {{ background-color: #101d21; border-color: #2e6e79; }}
            QFrame#NewsVisual[context="analysis"] {{ background-color: #111925; border-color: #3c5f92; }}
            QFrame#NewsVisual[context="squad"] {{ background-color: #151a24; border-color: #526a9a; }}
            QFrame#NewsVisual[context="simulation"] {{ background-color: #121a21; border-color: #3e6278; }}
            QFrame#NewsVisual[context="opponent"] {{ background-color: #201415; border-color: #844844; }}
            QFrame#NewsVisual[context="club_news"] {{ background-color: #17191c; border-color: {c['accent']}; }}
            QFrame#NewsVisual[context="league_news"] {{ background-color: #15191e; border-color: #576879; }}
            QFrame#NewsVisual[context="second_draft"] {{ background-color: #1d1910; border-color: #8b7438; }}
            QFrame#VisualHero {{ background-color: #10151b; border: 1px solid #3b4652; border-left: 5px solid {c['accent']}; }}
            QLabel#VisualKicker {{ color: {c['accent_light']}; font-size: 10px; font-weight: 800; }}
            QLabel#VisualTitle {{ color: white; font-size: 22px; font-weight: 800; }}
            QLabel#VisualSummary {{ color: #b8c4cf; font-size: 12px; }}
            QFrame#VisualTile {{ background-color: #202731; border: 1px solid #3a4652; border-radius: 2px; }}
            QLabel#VisualTileLabel {{ color: #8493a2; font-size: 10px; font-weight: 700; }}
            QLabel#VisualTileValue {{ color: white; font-size: 16px; font-weight: 800; }}
            QLabel#VisualTileNote {{ color: #aeb9c4; font-size: 10px; }}
            QLabel#TradeArrow {{ color: {c['accent_light']}; font-size: 30px; font-weight: 900; }}
            QLabel#DialogueBubble {{ color: #e7edf3; background-color: #242c35; border: 1px solid #465361; border-radius: 4px; padding: 14px; font-size: 13px; }}
            QLabel#BigNumber {{ color: white; font-size: 38px; font-weight: 900; }}
            QLabel#BigCaption {{ color: #99a8b6; font-size: 11px; font-weight: 700; }}
            QLabel#FlowArrow {{ color: #7f91a2; font-size: 25px; font-weight: 900; }}
            QLabel#NewsMasthead {{ color: white; border-bottom: 3px solid {c['accent']}; padding-bottom: 7px; font-size: 27px; font-weight: 900; }}
            QLabel#NewsDeck {{ color: #aebac5; font-size: 13px; line-height: 1.4; }}
            QLabel#TimelineDate {{ color: white; background-color: #24616c; border-radius: 3px; padding: 12px; font-size: 20px; font-weight: 900; }}
            QFrame#TimelineRail {{ background-color: #17282d; border: none; border-left: 4px solid #3d8b99; }}
            QFrame#ProfilePanel {{ background-color: #172b21; border: 1px solid #356b4e; border-radius: 3px; }}
            QLabel#ProfileInitial {{ color: #d9f4e5; background-color: #285a40; border-radius: 42px; font-size: 31px; font-weight: 900; }}
            QFrame#StatusPanel {{ background-color: #2b171a; border: 1px solid #743b43; border-radius: 3px; }}
            QFrame#BoardGoal {{ background-color: #292414; border: 1px solid #6f5d2d; border-radius: 3px; }}
            QProgressBar#ContextProgress {{ color: white; background-color: #0f1419; border: 1px solid #3a4652; border-radius: 2px; text-align: center; min-height: 18px; }}
            QProgressBar#ContextProgress::chunk {{ background-color: {c['accent']}; }}
            QFrame#NewsVisual[context="fa"] QProgressBar#ContextProgress::chunk {{ background-color: #4fae78; }}
            QFrame#NewsVisual[context="medical"] QProgressBar#ContextProgress::chunk {{ background-color: #d94b4b; }}
            QFrame#NewsVisual[context="meeting"] QProgressBar#ContextProgress::chunk {{ background-color: #9a71d0; }}
            QFrame#NewsVisual[context="analysis"] QProgressBar#ContextProgress::chunk {{ background-color: #6c8fe0; }}
            QFrame#NewsVisual[context="squad"] QProgressBar#ContextProgress::chunk {{ background-color: #6f8fd0; }}
            QTableWidget {{ color: #e2e8ef; background-color: #1b2026; alternate-background-color: #23292f; border: none; font-size: 12px; }}
            QHeaderView::section {{ color: #9eacba; background-color: #151a1f; border: none; border-bottom: 1px solid #39434e; padding: 5px; font-size: 11px; font-weight: 600; }}
            QPushButton#PrimaryAction {{ color: white; background-color: {c['accent']}; border-color: {c['accent_light']}; }}
            QPushButton#SecondaryAction {{ color: {c['accent_light']}; background-color: transparent; border-color: {c['accent']}; }}
        """)

    @staticmethod
    def _metric_label(title, value):
        label = QLabel(f"{title}\n{value}")
        label.setObjectName("OperationMetric")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    @staticmethod
    def _data_card(title):
        card = QFrame()
        card.setObjectName("DataCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("DataTitle")
        layout.addWidget(label)
        card.title_label = label
        return card

    @staticmethod
    def _configure_table(table):
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(29)
        table.horizontalHeader().setSectionsMovable(False)

    def _show_message(self, row):
        message_index = self._message_index_for_row(row)
        if message_index is None:
            return
        message = self.messages[message_index]
        self.sender_label.setText(message["sender"])
        category = message["category"]
        badge_text, badge_color = self._message_badge(category)
        self.sender_badge.setText(badge_text)
        self.sender_badge.setStyleSheet(
            "color: white;"
            f"background-color: {badge_color};"
            "border-radius: 2px;"
            "font-size: 10px;"
            "font-weight: 900;"
        )
        if message.get("requires_action") and not message.get("resolved"):
            category += "  ·  필수 응답"
        self.category_label.setText(category)
        message_time = str(message["time"])
        self.message_time.setText(
            message_time
            if message_time.count(".") == 2
            else f"오늘  {message_time}"
        )
        self.headline_label.setText(message["headline"])
        self.body_label.setText(message["body"])
        is_board_message = bool(message.get("is_board"))
        is_news_message = message.get("news_id") is not None
        is_manager_event = message.get("event_id") is not None
        is_rookie_draft = self._is_rookie_draft_message(message)
        self._render_message_context(message)
        self.message_action_button.setVisible(
            is_board_message
            or is_manager_event
            or (is_news_message and not is_rookie_draft)
        )
        self.message_action_button.setEnabled(
            is_board_message
            or is_manager_event
            or (is_news_message and not is_rookie_draft)
        )
        if is_board_message:
            self.message_action_button.setText(
                "이사회 목표 다시 보기  ›"
                if self.board_vision_reviewed
                else "필수 응답 · 이사회 목표 협상  ›"
            )
        elif is_manager_event:
            self.message_action_button.setText(
                "처리 결과 보기  ›"
                if message.get("resolved")
                else "필수 응답 처리  ›"
                if message.get("requires_action")
                else "업무 내용 보기  ›"
            )
        elif is_news_message:
            draft_view = self._second_draft_view(message)
            if not is_rookie_draft:
                self.message_action_button.setText(
                    "2차 드래프트 결과 확인  ›"
                    if draft_view == "results"
                    else "지명 가능 명단 확인  ›"
                    if draft_view
                    else "전체 뉴스 보기  ›"
                )
            if not message.get("is_read") and self.save_database and self.save_id is not None:
                self.save_database.mark_daily_news_read(self.save_id, message["news_id"])
                message["is_read"] = 1
                item = self.inbox_list.item(row)
                if item is not None and item.text().startswith("●  "):
                    item.setText(item.text()[3:])
                self._update_unread_count()
        if not message.get("is_read"):
            if (
                is_manager_event
                and self.save_database
                and self.save_id is not None
            ):
                self.save_database.mark_manager_event_read(
                    self.save_id, message["event_id"]
                )
                self._update_unread_count()
            elif not is_news_message:
                self._read_static_messages.add(message["headline"])
            message["is_read"] = 1
        self._set_inbox_item_read_style(row, True)

    @staticmethod
    def _message_badge(category):
        return {
            "이사회": ("이사", "#9a7b32"),
            "전력 분석": ("분석", "#416fa8"),
            "선수단": ("선수", "#526c9f"),
            "선수 면담": ("면담", "#7957a1"),
            "선수 불만": ("면담", "#7957a1"),
            "의무": ("의무", "#a8414b"),
            "의료 센터": ("의무", "#a8414b"),
            "부상": ("부상", "#a8414b"),
            "트레이드": ("TR", "#3970a5"),
            "FA": ("FA", "#39845b"),
            "엔트리": ("등록", "#a26028"),
            "경기 일정": ("일정", "#337887"),
            "상대 구단": ("분석", "#9a4e49"),
            "리그 시뮬레이션": ("진행", "#466e87"),
            "구단 공식 발표": ("구단", "#78643b"),
            "프런트 브리핑": ("구단", "#78643b"),
            "시즌 전망": ("전망", "#78643b"),
            "KBO": ("KBO", "#987f3f"),
            "리그": ("KBO", "#526577"),
            "리그 소식": ("KBO", "#526577"),
        }.get(str(category), ("뉴스", "#586675"))

    def _activate_current_message(self):
        row = self.inbox_list.currentRow()
        message_index = self._message_index_for_row(row)
        if message_index is None:
            return
        self._show_message(row)
        message = self.messages[message_index]
        if message.get("is_board"):
            self.board_vision_requested.emit()
        elif message.get("event_id") is not None:
            self.manager_event_requested.emit(int(message["event_id"]))
        elif message.get("news_id") is not None:
            if self._is_rookie_draft_message(message):
                return
            draft_view = self._second_draft_view(message)
            if draft_view:
                self.second_draft_requested.emit(draft_view)
            else:
                self.news_requested.emit()

    @staticmethod
    def _second_draft_view(message):
        headline = str(message.get("headline") or "")
        if headline.startswith("2차 드래프트 보호선수 및 지명 대상 명단 확정"):
            return "available"
        if headline.startswith("2025 KBO 2차 드래프트 종료"):
            return "results"
        return None

    @staticmethod
    def _is_rookie_draft_message(message):
        text = " ".join((
            str(message.get("headline") or ""),
            str(message.get("body") or ""),
        ))
        return "신인 드래프트" in text and "2차 드래프트" not in text

    def _render_message_context(self, message):
        """선택한 수신함 항목의 종류에 맞는 세부 데이터를 표시한다."""
        if self._is_rookie_draft_message(message):
            self._render_rookie_draft_context(message)
            return
        category = str(message.get("category") or "")
        event_type = str(message.get("event_type") or "")
        text = " ".join((
            category,
            event_type,
            str(message.get("headline") or ""),
            str(message.get("body") or ""),
        ))
        if "2차 드래프트" in text:
            self._render_second_draft_context(message)
        elif event_type == "trade_offer" or "트레이드" in text:
            self._render_trade_context(message)
        elif event_type == "fa_opportunity" or category == "FA":
            self._render_fa_context(message)
        elif (
            event_type == "injury"
            or category in ("부상", "의료 센터", "의무")
            or any(keyword in text for keyword in ("부상", "회복", "재활"))
        ):
            self._render_medical_context(message)
        elif (
            event_type == "player_complaint"
            or category in ("선수 면담", "선수 불만")
        ):
            self._render_meeting_context(message)
        elif event_type == "entry_review" or category == "엔트리":
            self._render_entry_context(message)
        elif event_type == "board_review" or category == "이사회":
            self._render_board_context(message)
        elif event_type == "schedule" or category == "경기 일정":
            self._render_schedule_context(message)
        elif category == "전력 분석":
            self._render_analysis_context(message)
        elif category == "선수단":
            self._render_squad_context(message)
        elif category == "리그 시뮬레이션":
            self._render_simulation_context(message)
        elif category == "상대 구단":
            self._render_opponent_context(message)
        elif category in ("구단 공식 발표", "프런트 브리핑", "시즌 전망"):
            self._render_club_news_context(message)
        elif (
            category in ("리그", "리그 소식", "KBO")
            or message.get("news_id") is not None
        ):
            self._render_league_news_context(message)
        else:
            self._render_generic_news_context(message)

    def _render_operational_context(self):
        self._detail_context = "operations"
        self.news_visual.setVisible(False)
        self.agenda_card.setVisible(True)
        self.data_split.setVisible(True)
        self.agenda_title.setText("오늘의 구단 운영")
        self.players_title.setText("1군 상태 · 대응이 필요한 선수")
        self.standings_title.setText("KBO 구단 운영 현황")
        self._configure_player_status_table()
        self._configure_club_status_table()
        self._load_operational_dashboard()

    def _render_generic_news_context(self, message):
        """전용 화면이 없는 뉴스에서도 무관한 구단 운영표는 숨긴다."""
        self._detail_context = "news"
        self._show_visual_context(
            "NEWS BRIEFING",
            message.get("headline") or "새 소식",
            message.get("body") or "상세 내용이 없습니다.",
            (
                ("분류", message.get("category") or "리그 소식", ""),
                ("게시일", self._message_date_key(message).replace("-", "."), ""),
                ("발신처", message.get("sender") or "KBO 뉴스센터", ""),
            ),
        )
        self.agenda_card.setVisible(False)
        self.data_split.setVisible(False)
        self._set_context_metrics(
            ("뉴스 분류", message.get("category") or "리그 소식"),
            ("게시일", self._message_date_key(message).replace("-", ".")),
            ("발신처", message.get("sender") or "KBO 뉴스센터"),
            ("확인 상태", "확인 완료"),
        )

    @staticmethod
    def _payload_for(message):
        payload = message.get("payload")
        if isinstance(payload, dict):
            return payload
        raw = message.get("payload_json")
        if isinstance(raw, str) and raw:
            try:
                value = json.loads(raw)
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    def _set_context_metrics(self, *metrics):
        labels = (
            self.phase_metric,
            self.condition_metric,
            self.injury_metric,
            self.task_metric,
        )
        for widget, metric in zip(labels, metrics):
            title, value = metric
            widget.setText(f"{title}\n{value}")

    def _clear_news_visual(self):
        while self.news_visual_layout.count():
            item = self.news_visual_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_child_layout(child_layout)

    @classmethod
    def _clear_child_layout(cls, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                cls._clear_child_layout(item.layout())

    def _visual_hero(self, kicker, title, summary):
        hero = QFrame()
        hero.setObjectName("VisualHero")
        kicker_text = str(kicker)
        accent = next(
            (
                color for keyword, color in (
                    ("MEDICAL", "#d94b4b"),
                    ("TRADE", "#4f8dcc"),
                    ("FREE AGENT", "#4fae78"),
                    ("PLAYER MEETING", "#9a71d0"),
                    ("ROSTER", "#ec8f42"),
                    ("BOARDROOM", "#b99a52"),
                    ("SCHEDULE", "#4ba8b8"),
                    ("DATA", "#6c8fe0"),
                    ("DRAFT", "#b99a52"),
                    ("OPPOSITION", "#d36f68"),
                )
                if keyword in kicker_text
            ),
            self.colors["accent"],
        )
        hero.setStyleSheet(
            "QFrame#VisualHero {"
            "background-color: #10151b;"
            "border: 1px solid #3b4652;"
            f"border-left: 5px solid {accent};"
            "}"
        )
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(4)
        kicker_label = QLabel(kicker_text)
        kicker_label.setObjectName("VisualKicker")
        kicker_label.setStyleSheet(
            f"color: {accent}; font-size: 10px; font-weight: 800;"
        )
        layout.addWidget(kicker_label)
        title_label = QLabel(str(title))
        title_label.setObjectName("VisualTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        summary_label = QLabel(str(summary))
        summary_label.setObjectName("VisualSummary")
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)
        return hero

    @staticmethod
    def _visual_tile(label, value, note=""):
        tile = QFrame()
        tile.setObjectName("VisualTile")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(3)
        label_widget = QLabel(str(label))
        label_widget.setObjectName("VisualTileLabel")
        layout.addWidget(label_widget)
        value_widget = QLabel(str(value))
        value_widget.setObjectName("VisualTileValue")
        value_widget.setWordWrap(True)
        layout.addWidget(value_widget)
        if note:
            note_widget = QLabel(str(note))
            note_widget.setObjectName("VisualTileNote")
            note_widget.setWordWrap(True)
            layout.addWidget(note_widget)
        layout.addStretch()
        return tile

    @staticmethod
    def _progress_panel(label, value, maximum=100, detail=""):
        panel = QFrame()
        panel.setObjectName("VisualTile")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(11, 9, 11, 10)
        layout.setSpacing(5)
        heading = QLabel(label)
        heading.setObjectName("VisualTileLabel")
        layout.addWidget(heading)
        progress = QProgressBar()
        progress.setObjectName("ContextProgress")
        progress.setRange(0, max(1, int(maximum)))
        progress.setValue(max(0, int(value)))
        progress.setFormat(detail or f"{int(value)} / {int(maximum)}")
        layout.addWidget(progress)
        return panel

    @staticmethod
    def _big_number(value, caption):
        panel = QFrame()
        panel.setObjectName("VisualTile")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        number = QLabel(str(value))
        number.setObjectName("BigNumber")
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(number)
        text = QLabel(caption)
        text.setObjectName("BigCaption")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        layout.addWidget(text)
        return panel

    def _show_visual_context(
        self, kicker, title, summary, tiles=(), progresses=()
    ):
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(kicker, title, summary)
        )
        if tiles:
            grid = QGridLayout()
            grid.setSpacing(8)
            for index, (label, value, note) in enumerate(tiles):
                grid.addWidget(
                    self._visual_tile(label, value, note),
                    index // 3,
                    index % 3,
                )
            self.news_visual_layout.addLayout(grid)
        for label, value, maximum in progresses:
            progress_label = QLabel(label)
            progress_label.setObjectName("VisualTileNote")
            self.news_visual_layout.addWidget(progress_label)
            progress = QProgressBar()
            progress.setObjectName("ContextProgress")
            progress.setRange(0, max(1, int(maximum)))
            progress.setValue(max(0, int(value)))
            self.news_visual_layout.addWidget(progress)
        self.news_visual_layout.addStretch()

    def _prepare_visual_only(self, context_name):
        self._detail_context = context_name
        self.news_visual.setProperty("context", context_name)
        self.news_visual.style().unpolish(self.news_visual)
        self.news_visual.style().polish(self.news_visual)
        self.agenda_card.setVisible(False)
        self.data_split.setVisible(False)

    @staticmethod
    def _extract_number(text, pattern, default=0):
        match = re.search(pattern, str(text or ""))
        return int(match.group(1).replace(",", "")) if match else default

    def _render_second_draft_context(self, message):
        self._prepare_visual_only("second_draft")
        text = f"{message.get('headline', '')} {message.get('body', '')}"
        completed = "종료" in text
        picked = self._extract_number(text, r"(\d+)명\s*지명")
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "KBO SECONDARY DRAFT",
                "2차 드래프트 결과"
                if completed else "보호선수 명단 확정",
                message.get("body") or "",
            )
        )
        draft_flow = QHBoxLayout()
        draft_flow.setSpacing(8)
        draft_flow.addWidget(
            self._big_number("35", "구단별 최대 보호 인원"), 1
        )
        arrow = QLabel("→")
        arrow.setObjectName("FlowArrow")
        draft_flow.addWidget(arrow)
        draft_flow.addWidget(
            self._big_number("10", "참가 구단"), 1
        )
        arrow2 = QLabel("→")
        arrow2.setObjectName("FlowArrow")
        draft_flow.addWidget(arrow2)
        draft_flow.addWidget(
            self._big_number(
                picked if picked else "?",
                "최종 지명 인원"
                if completed else "지명 가능 선수 풀",
            ),
            1,
        )
        self.news_visual_layout.addLayout(draft_flow)
        self.news_visual_layout.addWidget(
            self._visual_tile(
                "현재 단계",
                "지명 종료" if completed else "구단별 보호 명단 확정",
                "하단 버튼에서 구단별 명단과 양도금을 확인합니다.",
            )
        )
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("제도", "2차 드래프트"),
            ("상태", "완료" if completed else "준비"),
            ("보호 한도", "35명"),
            ("감독 업무", "결과 확인"),
        )

    def _render_trade_context(self, message):
        self._prepare_visual_only("trade")
        payload = self._payload_for(message)
        terms = payload.get("trade_terms") or {}
        outgoing = (
            terms.get("outgoing_name")
            or payload.get("outgoing_name")
            or "우리 구단 선수"
        )
        incoming = (
            terms.get("incoming_name")
            or payload.get("incoming_name")
            or "상대 구단 선수"
        )
        outgoing_rating = int(
            terms.get("outgoing_rating")
            or payload.get("outgoing_rating")
            or 0
        )
        incoming_rating = int(
            terms.get("incoming_rating")
            or payload.get("incoming_rating")
            or 0
        )
        other_team = payload.get("other_team") or "상대 구단"
        summary = (
            terms.get("summary")
            or message.get("body")
            or "트레이드 조건 검토가 필요합니다."
        )
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "TRADE ROOM",
                f"{self.team_name}  ↔  {other_team}",
                summary,
            )
        )
        exchange = QHBoxLayout()
        exchange.setSpacing(12)
        exchange.addWidget(
            self._visual_tile(
                "우리 구단이 보내는 선수",
                outgoing,
                f"내부 평가 {outgoing_rating or '-'}",
            ),
            1,
        )
        arrow = QLabel("⇄")
        arrow.setObjectName("TradeArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exchange.addWidget(arrow)
        exchange.addWidget(
            self._visual_tile(
                "우리 구단이 받는 선수",
                incoming,
                f"내부 평가 {incoming_rating or '-'}",
            ),
            1,
        )
        self.news_visual_layout.addLayout(exchange)
        if terms.get("compensation_direction") == "counterpart":
            compensation = (
                terms.get("cash_from_user_label")
                or terms.get("additional_outgoing_name")
                or "상대 구단 역제안"
            )
        else:
            compensation = (
                terms.get("cash_label")
                or terms.get("additional_incoming_name")
                or "없음"
            )
        self.news_visual_layout.addWidget(
            self._visual_tile(
                "추가 조건 및 협상 상태",
                compensation,
                terms.get("reply")
                or "단장에게 감독 의견을 전달해 협상을 진행합니다.",
            )
        )
        self.news_visual_layout.addStretch()
        trade_status = {
            "original": "최초 제안",
            "counter_offer": "역제안",
            "accepted": "합의",
            "rejected": "결렬",
        }.get(terms.get("status"), terms.get("status") or "검토 중")
        self._set_context_metrics(
            ("협상 상대", other_team),
            ("IN 평가", incoming_rating or "-"),
            ("OUT 평가", outgoing_rating or "-"),
            ("협상 상태", trade_status),
        )

    def _render_fa_context(self, message):
        self._prepare_visual_only("fa")
        payload = self._payload_for(message)
        body = str(message.get("body") or "")
        player = payload.get("player_name") or (
            message.get("headline", "").split("·")[-1].strip()
        )
        age = self._extract_number(body, r"(\d+)세")
        rating = self._extract_number(body, r"내부 종합\s*(\d+)")
        offer = int(
            payload.get("offer_salary")
            or self._extract_number(body, r"연봉은?\s*([\d,]+)만원")
        )
        old_team = payload.get("old_team") or "FA 시장"
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "FREE AGENT DOSSIER",
                "FA 영입 검토 보고서",
                "스카우트팀 평가와 프런트 권장 계약안을 함께 검토합니다.",
            )
        )
        dossier = QHBoxLayout()
        dossier.setSpacing(12)
        profile = QFrame()
        profile.setObjectName("ProfilePanel")
        profile_layout = QVBoxLayout(profile)
        profile_layout.setContentsMargins(18, 15, 18, 15)
        profile_layout.setSpacing(7)
        initial = QLabel((player or "FA")[-2:])
        initial.setObjectName("ProfileInitial")
        initial.setFixedSize(84, 84)
        initial.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(
            initial, 0, Qt.AlignmentFlag.AlignHCenter
        )
        name_label = QLabel(player or "FA 영입 후보")
        name_label.setObjectName("VisualTitle")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(name_label)
        origin = QLabel(f"{old_team} 출신  ·  {age or '-'}세")
        origin.setObjectName("VisualSummary")
        origin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(origin)
        profile_layout.addStretch()
        dossier.addWidget(profile, 4)

        contract = QFrame()
        contract.setObjectName("VisualTile")
        contract_layout = QVBoxLayout(contract)
        contract_layout.setContentsMargins(15, 13, 15, 13)
        contract_layout.setSpacing(8)
        contract_layout.addWidget(
            self._big_number(
                rating or "-",
                "내부 종합 평가",
            )
        )
        if rating:
            contract_layout.addWidget(
                self._progress_panel(
                    "영입 우선도",
                    rating,
                    100,
                    f"스카우트 평가 {rating}",
                )
            )
        contract_layout.addWidget(
            self._visual_tile(
                "프런트 권장 계약안",
                f"연봉 {offer:,}만원" if offer else "협상 필요",
                "보직과 계약 기간은 에이전트 협상에서 확정",
            )
        )
        dossier.addWidget(contract, 6)
        self.news_visual_layout.addLayout(dossier)
        report = QLabel(body)
        report.setObjectName("DialogueBubble")
        report.setWordWrap(True)
        self.news_visual_layout.addWidget(report)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("시장", "FA"),
            ("후보", player or "-"),
            ("내부 평가", rating or "-"),
            ("예상 연봉", f"{offer:,}만원" if offer else "-"),
        )

    def _render_medical_context(self, message):
        self._prepare_visual_only("medical")
        payload = self._payload_for(message)
        headline = str(message.get("headline") or "")
        body = str(message.get("body") or "")
        is_league_report = headline.startswith("KBO 부상자 현황")
        player = payload.get("player_name") or (
            "KBO 1군 전체"
            if is_league_report
            else headline.split(",")[0]
            if "," in headline
            else "선수단 전체"
        )
        days = self._extract_number(
            f"{headline} {body}", r"(\d+)일"
        )
        condition = self._extract_number(body, r"컨디션\s*(\d+)")
        fatigue = self._extract_number(body, r"피로도\s*(\d+)")
        recovered = "회복" in headline or "재활을 마쳤" in body
        diagnosis_match = re.search(
            r"가\s+([^.\n]+?)\s+진단", body
        )
        diagnosis = (
            "리그 부상자 집계"
            if is_league_report
            else "정상 훈련 복귀"
            if recovered
            else diagnosis_match.group(1).strip()
            if diagnosis_match
            else "메디컬 점검"
        )
        readiness = (
            condition if recovered else max(5, 100 - days * 4)
        )
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        medical = QHBoxLayout()
        medical.setSpacing(12)
        status_panel = QFrame()
        status_panel.setObjectName("StatusPanel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(17, 15, 17, 15)
        medical_status = QLabel("MEDICAL STATUS")
        medical_status.setObjectName("VisualKicker")
        status_layout.addWidget(medical_status)
        status_layout.addWidget(
            self._big_number(
                "복귀" if recovered else days or "!",
                "훈련 복귀 승인"
                if recovered
                else "예상 이탈 일수",
            )
        )
        status_layout.addWidget(
            self._progress_panel(
                "복귀 준비도",
                readiness,
                100,
                f"{readiness}%",
            )
        )
        medical.addWidget(status_panel, 4)

        timeline = QFrame()
        timeline.setObjectName("TimelineRail")
        timeline_layout = QVBoxLayout(timeline)
        timeline_layout.setContentsMargins(18, 13, 14, 13)
        timeline_layout.setSpacing(8)
        timeline_layout.addWidget(
            self._visual_hero(
                "MEDICAL REPORT",
                f"{player} · {diagnosis}",
                body,
            )
        )
        stages = (
            ("01  진단", diagnosis, "완료"),
            (
                "02  재활",
                "단계적 훈련 합류"
                if recovered else "메디컬 프로그램 진행",
                "완료" if recovered else "진행 중",
            ),
            (
                "03  복귀",
                "라인업 편성 가능"
                if recovered else f"예상 {days}일 후",
                "승인" if recovered else "대기",
            ),
        )
        for stage, detail, state in stages:
            timeline_layout.addWidget(
                self._visual_tile(stage, detail, state)
            )
        medical.addWidget(timeline, 7)
        self.news_visual_layout.addLayout(medical)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("메디컬 상태", "복귀" if recovered else "이탈"),
            ("대상 선수", player or "-"),
            ("예상 기간", "완료" if recovered else f"{days}일"),
            ("필요 조치", "라인업 검토" if recovered else "치료 방침"),
        )

    def _render_meeting_context(self, message):
        self._prepare_visual_only("meeting")
        payload = self._payload_for(message)
        player = payload.get("player_name") or (
            str(message.get("headline") or "").split(",")[0]
        )
        morale = int(payload.get("morale") or 50)
        squad = payload.get("squad") or "-"
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "PLAYER MEETING",
                f"{player} 선수 면담",
                f"현재 소속 {squad} · 사기 {morale}",
            )
        )
        bubble = QLabel(
            message.get("body")
            or "감독님과 제 역할에 대해 솔직하게 이야기하고 싶습니다."
        )
        bubble.setObjectName("DialogueBubble")
        bubble.setWordWrap(True)
        self.news_visual_layout.addWidget(bubble)
        self.news_visual_layout.addWidget(
            self._visual_tile(
                "면담 핵심",
                "기용 계획과 역할",
                "선수의 요구를 확인하고 구체적인 답변을 선택합니다.",
            )
        )
        progress = QProgressBar()
        progress.setObjectName("ContextProgress")
        progress.setRange(0, 100)
        progress.setValue(morale)
        progress.setFormat(f"현재 사기  {morale}")
        self.news_visual_layout.addWidget(progress)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("면담 대상", player or "-"),
            ("소속", squad),
            ("현재 사기", morale),
            ("상태", "답변 필요" if not message.get("resolved") else "처리 완료"),
        )

    def _render_entry_context(self, message):
        self._prepare_visual_only("entry")
        payload = self._payload_for(message)
        promote = payload.get("promote_name") or "변동 없음"
        demote = payload.get("demote_name") or "변동 없음"
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "ROSTER REGISTRATION",
                "1군 엔트리 제출안",
                message.get("body") or "",
            )
        )
        movement = QHBoxLayout()
        movement.addWidget(
            self._visual_tile(
                "1군 말소 · OUT",
                demote,
                "부상·컨디션·전력 구성을 반영",
            ),
            1,
        )
        arrow = QLabel("→")
        arrow.setObjectName("TradeArrow")
        movement.addWidget(arrow)
        movement.addWidget(
            self._visual_tile(
                "1군 등록 · IN",
                promote,
                "대체 등록 또는 엔트리 보강",
            ),
            1,
        )
        self.news_visual_layout.addLayout(movement)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("업무", "엔트리 제출"),
            ("등록", promote),
            ("말소", demote),
            ("마감 상태", "결정 필요"),
        )

    def _render_board_context(self, message):
        self._prepare_visual_only("board")
        payload = self._payload_for(message)
        first_count = payload.get("first_team_count") or "-"
        injured = payload.get("injured_count") or 0
        condition = payload.get("average_condition") or "-"
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "BOARDROOM BRIEFING",
                message.get("headline") or "구단 이사회 보고",
                message.get("body") or "",
            )
        )
        board = QHBoxLayout()
        board.setSpacing(9)
        board.addWidget(
            self._big_number(first_count, "현재 1군 인원"), 1
        )
        board.addWidget(
            self._big_number(injured, "관리 중인 부상자"), 1
        )
        board.addWidget(
            self._big_number(condition, "평균 컨디션"), 1
        )
        self.news_visual_layout.addLayout(board)
        goals = QGridLayout()
        goals.setSpacing(8)
        goal_data = (
            ("단기 성과", "시즌 목표 합의", "이사회가 요구하는 즉시 성과"),
            ("장기 전략", "육성과 성적 균형", "구단 철학과 세대교체"),
            ("현장 권한", "감독 협상 가능", "답변에 따라 신뢰도 변화"),
        )
        for column, (label, value, note) in enumerate(goal_data):
            goal = self._visual_tile(label, value, note)
            goal.setObjectName("BoardGoal")
            goals.addWidget(goal, 0, column)
        self.news_visual_layout.addLayout(goals)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("회의", "이사회"),
            ("1군", f"{first_count}명"),
            ("부상", f"{injured}명"),
            ("응답", "필수" if message.get("requires_action") else "확인"),
        )

    def _render_schedule_context(self, message):
        self._prepare_visual_only("schedule")
        body = str(message.get("body") or "")
        task = body.split("감독 업무:", 1)[-1].strip() if "감독 업무:" in body else "일정 확인"
        day = self._message_date_key(message).replace("-", ".")
        phase_name = (
            phase_for(date.fromisoformat(day.replace(".", "-")))[0]
            if day != "0000.00.00" else "-"
        )
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        schedule = QHBoxLayout()
        schedule.setSpacing(12)
        date_card = QLabel(day)
        date_card.setObjectName("TimelineDate")
        date_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_card.setFixedWidth(155)
        schedule.addWidget(date_card)
        rail = QFrame()
        rail.setObjectName("TimelineRail")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(18, 14, 15, 14)
        rail_layout.setSpacing(9)
        kicker = QLabel(f"KBO OFFICIAL SCHEDULE  /  {phase_name}")
        kicker.setObjectName("VisualKicker")
        rail_layout.addWidget(kicker)
        title = QLabel(message.get("headline") or "경기 일정")
        title.setObjectName("VisualTitle")
        title.setWordWrap(True)
        rail_layout.addWidget(title)
        description = QLabel(
            body.split("감독 업무:", 1)[0].strip()
        )
        description.setObjectName("VisualSummary")
        description.setWordWrap(True)
        rail_layout.addWidget(description)
        rail_layout.addWidget(
            self._visual_tile(
                "감독 체크리스트",
                task,
                "일정 진행 전에 확인해야 하는 필수 업무",
            )
        )
        schedule.addWidget(rail, 1)
        self.news_visual_layout.addLayout(schedule)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("일정", day),
            ("분류", message.get("category") or "경기 일정"),
            ("중요도", message.get("priority") or "일반"),
            ("업무", "확인 필요"),
        )

    def _render_analysis_context(self, message):
        self._prepare_visual_only("analysis")
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "DATA & SCOUTING",
                message.get("headline") or "전력 분석 보고서",
                message.get("body") or "",
            )
        )
        matrix = QHBoxLayout()
        matrix.setSpacing(10)
        scope = QFrame()
        scope.setObjectName("VisualTile")
        scope_layout = QVBoxLayout(scope)
        scope_layout.setContentsMargins(13, 11, 13, 11)
        scope_layout.addWidget(
            self._visual_tile(
                "분석 표본",
                "1군 + 퓨처스",
                "2025 KBO 공식 기록 기반",
            )
        )
        scope_layout.addWidget(
            self._visual_tile(
                "보정 원칙",
                "표본별 신뢰도 차등",
                "표본 부족 선수는 보수적으로 평가",
            )
        )
        matrix.addWidget(scope, 4)
        chart = QFrame()
        chart.setObjectName("VisualTile")
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(13, 11, 13, 11)
        chart_layout.setSpacing(8)
        chart_title = QLabel("분석 영역별 데이터 완성도")
        chart_title.setObjectName("VisualTileValue")
        chart_layout.addWidget(chart_title)
        for label, value in (
            ("타격 데이터", 92),
            ("투구 데이터", 90),
            ("주루 데이터", 76),
            ("수비 데이터", 61),
            ("멘탈·리더십", 38),
        ):
            chart_layout.addWidget(
                self._progress_panel(
                    label, value, 100, f"{value}%"
                )
            )
        matrix.addWidget(chart, 6)
        self.news_visual_layout.addLayout(matrix)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("보고서", "전력 분석"),
            ("대상", "전체 선수단"),
            ("기준", "2025 기록"),
            ("상태", "1차 완료"),
        )

    def _render_squad_context(self, message):
        self._prepare_visual_only("squad")
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "SQUAD PLANNING",
                message.get("headline") or "선수단 운영",
                message.get("body") or "",
            )
        )
        route = QHBoxLayout()
        route.setSpacing(7)
        stages = (
            ("01", "CAMP1 참가", "1군·C팀 초기 분류"),
            ("02", "포지션 경쟁", "주전 후보 압축"),
            ("03", "실전 테스트", "체력·컨디션 검증"),
            ("04", "개막 엔트리", "최종 등록 명단"),
        )
        for index, (number, title, note) in enumerate(stages):
            route.addWidget(
                self._visual_tile(number, title, note), 1
            )
            if index < len(stages) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("FlowArrow")
                route.addWidget(arrow)
        self.news_visual_layout.addLayout(route)
        self.news_visual_layout.addWidget(
            self._progress_panel(
                "현재 선수단 구성 진행도",
                25,
                100,
                "초기 분류 단계",
            )
        )
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("업무", "선수단 구성"),
            ("단계", "캠프 준비"),
            ("경쟁", "포지션별"),
            ("결과", "엔트리 후보"),
        )

    def _render_simulation_context(self, message):
        self._prepare_visual_only("simulation")
        body = str(message.get("body") or "")
        players = self._extract_number(body, r"구단\s+([\d,]+)명")
        injuries = self._extract_number(body, r"신규 부상\s+(\d+)명")
        recoveries = self._extract_number(body, r"1군 복귀\s+(\d+)명")
        assignments = self._extract_number(body, r"보직\s+(\d+)건")
        roster_moves = self._extract_number(body, r"엔트리 이동\s+(\d+)건")
        ai_jobs = self._extract_number(body, r"AI 검토\s+(\d+)건")
        self._show_visual_context(
            "LEAGUE PROCESSING REPORT",
            message.get("headline") or "리그 하루 진행 결과",
            "오늘 처리된 10개 구단의 선수 상태와 운영 결과입니다.",
            (
                ("처리 선수", f"{players}명", "10개 구단"),
                ("신규 부상", f"{injuries}명", "1군 기준"),
                ("복귀 선수", f"{recoveries}명", "1군 기준"),
                ("보직 편성", f"{assignments}건", "타순·투수 보직"),
                ("엔트리 이동", f"{roster_moves}건", "1·2군 이동"),
                ("AI 검토", f"{ai_jobs}건", "백그라운드 처리"),
            ),
        )
        self._set_context_metrics(
            ("처리 구단", "10개"),
            ("선수", f"{players}명"),
            ("부상/복귀", f"{injuries}/{recoveries}"),
            ("AI 업무", f"{ai_jobs}건"),
        )

    def _render_opponent_context(self, message):
        self._prepare_visual_only("opponent")
        body = str(message.get("body") or "")
        fields = {}
        for line in body.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "OPPOSITION INTELLIGENCE",
                message.get("headline") or "상대 구단 대응",
                fields.get("판단 근거") or body,
            )
        )
        flow = QHBoxLayout()
        flow.setSpacing(8)
        steps = (
            (
                "01  상대 구단 결정",
                fields.get("실행안") or "확인 필요",
                fields.get("검토 대상") or "구단 운영",
            ),
            (
                "02  예상 효과",
                fields.get("기대 효과") or "-",
                "상대 전력에 미치는 영향",
            ),
            (
                "03  위험 신호",
                fields.get("위험 요소") or "-",
                "우리 구단 대응 검토",
            ),
        )
        for index, step in enumerate(steps):
            flow.addWidget(self._visual_tile(*step), 1)
            if index < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("FlowArrow")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                flow.addWidget(arrow)
        self.news_visual_layout.addLayout(flow)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("분석", "상대 구단"),
            ("상태", "대응안 확정"),
            ("효과", "검토"),
            ("위험", "관리 필요"),
        )

    def _render_club_news_context(self, message):
        self._prepare_visual_only("club_news")
        category = message.get("category") or "구단 소식"
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        masthead = QLabel(f"{self.team_name or 'CLUB'}  OFFICIAL")
        masthead.setObjectName("NewsMasthead")
        self.news_visual_layout.addWidget(masthead)
        meta = QLabel(
            f"{category}  |  "
            f"{self._message_date_key(message).replace('-', '.')}"
        )
        meta.setObjectName("VisualKicker")
        self.news_visual_layout.addWidget(meta)
        headline = QLabel(
            message.get("headline") or f"{self.team_name} 공식 발표"
        )
        headline.setObjectName("VisualTitle")
        headline.setWordWrap(True)
        self.news_visual_layout.addWidget(headline)
        columns = QHBoxLayout()
        columns.setSpacing(14)
        body = QLabel(message.get("body") or "")
        body.setObjectName("NewsDeck")
        body.setWordWrap(True)
        columns.addWidget(body, 7)
        side = self._visual_tile(
            "프런트 노트",
            "현장과 프런트 공동 관리",
            "감독 결정에 따라 후속 발표가 갱신됩니다.",
        )
        columns.addWidget(side, 3)
        self.news_visual_layout.addLayout(columns)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("채널", "구단 미디어"),
            ("구단", self.team_name or "-"),
            ("분류", category),
            ("상태", "공식 발표"),
        )

    def _render_league_news_context(self, message):
        text = f"{message.get('headline', '')} {message.get('body', '')}"
        mentioned = [team for team in TEAM_NAMES if team in text]
        tiles = [
            ("관련 구단", team, "기사에서 언급된 구단")
            for team in mentioned[:6]
        ]
        if not tiles:
            tiles = [
                ("보도 범위", "KBO 리그", "10개 구단 공통 소식"),
                ("분류", message.get("category") or "리그", ""),
                ("게시일", self._message_date_key(message).replace("-", "."), ""),
            ]
        self._prepare_visual_only("league_news")
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        masthead = QLabel("KBO  NEWSWIRE")
        masthead.setObjectName("NewsMasthead")
        self.news_visual_layout.addWidget(masthead)
        meta = QLabel(
            f"리그 뉴스  ·  "
            f"{self._message_date_key(message).replace('-', '.')}  ·  "
            f"{len(mentioned) if mentioned else 10}개 구단"
        )
        meta.setObjectName("VisualKicker")
        self.news_visual_layout.addWidget(meta)
        headline = QLabel(
            message.get("headline") or "KBO 리그 소식"
        )
        headline.setObjectName("VisualTitle")
        headline.setWordWrap(True)
        self.news_visual_layout.addWidget(headline)
        body = QLabel(message.get("body") or "")
        body.setObjectName("NewsDeck")
        body.setWordWrap(True)
        self.news_visual_layout.addWidget(body)
        team_strip = QHBoxLayout()
        team_strip.setSpacing(6)
        for label, value, note in tiles:
            team_strip.addWidget(
                self._visual_tile(label, value, note), 1
            )
        self.news_visual_layout.addLayout(team_strip)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("채널", "KBO 뉴스센터"),
            ("관련 구단", f"{len(mentioned)}개" if mentioned else "리그 전체"),
            ("게시일", self._message_date_key(message).replace("-", ".")),
            ("상태", "확인 완료"),
        )

    def _render_rookie_draft_context(self, message):
        """신인 드래프트 뉴스 전용 지명 결과 대시보드."""
        self._detail_context = "rookie_draft"
        self.news_visual.setVisible(False)
        self.agenda_card.setVisible(True)
        self.data_split.setVisible(True)
        rookies = []
        if self.save_database and self.save_id is not None:
            rookies = self.save_database.list_incoming_rookies(
                self.save_id
            )

        team_rookies = [
            rookie for rookie in rookies
            if rookie.get("team") == self.team_name
        ]
        draft_year = (
            int(rookies[0]["draft_year"])
            if rookies else 2026
        )
        first_pick = next(
            (
                rookie for rookie in team_rookies
                if int(rookie.get("round_no") or 0) == 1
            ),
            None,
        )

        self.phase_metric.setText(f"드래프트 연도\n{draft_year}")
        self.condition_metric.setText(
            f"전체 지명\n{len(rookies) or 110}명"
        )
        self.injury_metric.setText(
            f"우리 구단 지명\n{len(team_rookies)}명"
        )
        self.task_metric.setText(
            "1라운드 지명\n"
            + (
                f"{first_pick['player_name']} "
                f"({int(first_pick['overall_pick'])}순위)"
                if first_pick else "지명 정보 없음"
            )
        )

        self.agenda_title.setText("우리 구단 드래프트 요약")
        position_counts = {}
        for rookie in team_rookies:
            position = (
                rookie.get("position_name")
                or rookie.get("position_group")
                or "미분류"
            )
            position_counts[position] = (
                position_counts.get(position, 0) + 1
            )
        position_summary = " · ".join(
            f"{position} {count}명"
            for position, count in position_counts.items()
        ) or "포지션별 지명 정보가 없습니다."
        first_pick_summary = (
            f"1라운드 {int(first_pick['overall_pick'])}순위 "
            f"{first_pick['player_name']} "
            f"({first_pick['position_name']} · {first_pick['school']})"
            if first_pick else "1라운드 지명 정보가 없습니다."
        )
        self.today_agenda.setText(
            f"{self.team_name}은 총 {len(team_rookies)}명을 "
            f"지명했습니다.\n"
            f"[최상위 지명] {first_pick_summary}\n"
            f"[포지션 구성] {position_summary}\n"
            "지명 선수는 2026년 합류 예정 선수로 관리되며, "
            "합류 후 퓨처스 선수단에서 육성을 시작합니다."
        )

        self.players_title.setText(
            f"{self.team_name} · 전체 지명 결과"
        )
        self._configure_draft_table(
            self.player_table,
            ("전체", "R", "선수", "포지션", "출신교"),
            team_rookies,
            include_team=False,
        )
        self.standings_title.setText(
            f"KBO {draft_year} 신인 드래프트 · 전체 지명"
        )
        self._configure_draft_table(
            self.standings_table,
            ("전체", "구단", "선수", "포지션", "출신교"),
            rookies,
            include_team=True,
        )

    def _configure_draft_table(
        self, table, headers, rookies, include_team
    ):
        table.clear()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rookies))
        for row, rookie in enumerate(rookies):
            second_value = (
                rookie.get("team")
                if include_team
                else f"{int(rookie.get('round_no') or 0)}R"
            )
            values = (
                int(rookie.get("overall_pick") or 0),
                second_value,
                rookie.get("player_name") or "-",
                rookie.get("position_name")
                or rookie.get("position_group")
                or "-",
                rookie.get("school") or "-",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (0, 1, 3):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                table.setItem(row, column, item)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )

    def _configure_player_status_table(self):
        self.player_table.clear()
        self.player_table.setColumnCount(5)
        self.player_table.setHorizontalHeaderLabels(
            ["선수", "포지션", "컨디션", "피로", "현재 상태"]
        )
        self.player_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.player_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, 4):
            self.player_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

    def _configure_club_status_table(self):
        self.standings_table.clear()
        self.standings_table.setColumnCount(5)
        self.standings_table.setHorizontalHeaderLabels(
            ["구단", "단계", "컨디션", "부상", "전력 과제"]
        )
        self.standings_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.standings_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        for column in (1, 2, 3):
            self.standings_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

    def mark_board_vision_reviewed(self):
        self.board_vision_reviewed = True
        board_row = next((index for index, message in enumerate(self.messages) if message.get("is_board")), -1)
        if board_row >= 0:
            self.messages[board_row]["resolved"] = True
        self._populate_inbox()
        if board_row >= 0:
            visible_row = self._row_for_message_index(board_row)
            if visible_row is not None:
                self.inbox_list.setCurrentRow(visible_row)
        self.message_action_button.setText("이사회 목표 다시 보기  ›")
        self._emit_required_action_count()

    def pending_required_messages(self):
        """날짜 진행 전에 감독이 반드시 처리해야 하는 수신함 항목을 반환한다."""
        return [
            message for message in self.messages
            if message.get("requires_action") and not message.get("resolved")
        ]

    def focus_first_required_message(self):
        for row, message in enumerate(self.messages):
            if message.get("requires_action") and not message.get("resolved"):
                visible_row = self._row_for_message_index(row)
                if visible_row is None:
                    return message
                self.inbox_list.setCurrentRow(visible_row)
                self.inbox_list.scrollToItem(
                    self.inbox_list.item(visible_row)
                )
                return message
        return None

    def _emit_required_action_count(self):
        count = len(self.pending_required_messages())
        if hasattr(self, "task_metric"):
            self.task_metric.setText(f"필수 업무\n{count}건")
        self.required_action_count_changed.emit(count)

    def set_save_id(self, save_id):
        self.save_id = save_id
        self.refresh_notifications()
        self._load_operational_dashboard()

    def set_game_date(self, game_date):
        self.current_date = game_date
        self._populate_inbox()
        self._load_operational_dashboard()

    def refresh_notifications(self):
        dynamic = []
        if self.save_database and self.save_id is not None:
            sender_names = {
                "경기 일정": "KBO 경기운영팀",
                "부상": "메디컬 센터",
                "선수 불만": "선수단 관리팀",
                "선수 면담": "선수단 관리팀",
                "이사회": "구단 이사회",
                "엔트리": "수석코치",
                "트레이드": "단장실",
                "FA": "프런트",
            }
            for event in self.save_database.list_manager_events(
                self.save_id, limit=40
            ):
                dynamic.append({
                    "category": event["category"],
                    "sender": sender_names.get(event["category"], "구단 사무국"),
                    "time": event["event_date"].replace("-", "."),
                    "received_date": event["event_date"],
                    "headline": event["headline"],
                    "body": event["body"],
                    "event_id": event["id"],
                    "event_type": event.get("event_type"),
                    "payload_json": event.get("payload_json"),
                    "result_text": event.get("result_text"),
                    "priority": event.get("priority"),
                    "is_read": int(event["is_read"]),
                    "is_board": False,
                    "requires_action": bool(event["requires_action"]),
                    "resolved": event["status"] == "resolved",
                })
            for news in self.save_database.list_daily_news(self.save_id):
                if news["category"] == "경기 일정":
                    continue
                if news["category"] == "의료 센터" and (
                    "발생 당시 소속은 2군," in news["body"] or "기존 2군 선수단" in news["body"]
                ):
                    continue
                dynamic.append({
                    "category": news["category"],
                    "sender": "메디컬 센터" if news["category"] == "의료 센터" else "KBO 뉴스센터",
                    "time": news["news_date"].replace("-", "."),
                    "received_date": news["news_date"],
                    "headline": news["headline"], "body": news["body"],
                    "news_id": news["id"], "is_read": int(news["is_read"]), "is_board": False,
                })
                if len(dynamic) >= 30:
                    break
        static = []
        for index, message in enumerate(INBOX_ITEMS):
            is_board = index == 0
            static.append(dict(
                message,
                received_date=(
                    self.appointment_date.isoformat()
                    if self.appointment_date is not None
                    else "0000-00-00"
                ),
                is_board=is_board,
                is_read=message["headline"] in self._read_static_messages,
                requires_action=is_board,
                resolved=self.board_vision_reviewed if is_board else True,
            ))
        self.messages = dynamic + static
        self._populate_inbox()
        self._update_unread_count()
        self._emit_required_action_count()

    def _populate_inbox(self):
        if not hasattr(self, "inbox_list"):
            return
        self.inbox_list.blockSignals(True)
        self.inbox_list.clear()
        indexed_messages = sorted(
            enumerate(self.messages),
            key=lambda pair: self._message_date_key(pair[1]),
            reverse=True,
        )
        previous_date = None
        first_message_row = None
        for message_index, message in indexed_messages:
            date_key = self._message_date_key(message)
            if date_key != previous_date:
                header = QListWidgetItem(self._date_group_title(date_key))
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setForeground(QColor("#8f9dac"))
                header.setBackground(QColor("#0f1419"))
                header_font = header.font()
                header_font.setBold(True)
                header_font.setPointSize(10)
                header.setFont(header_font)
                header.setSizeHint(QSize(320, 32))
                header.setData(Qt.ItemDataRole.UserRole, None)
                self.inbox_list.addItem(header)
                previous_date = date_key
            unread = (
                "●  "
                if (
                    message.get("news_id") is not None
                    or message.get("event_id") is not None
                ) and not message.get("is_read")
                else ""
            )
            required = "[필수]  " if message.get("requires_action") and not message.get("resolved") else ""
            completed = "[처리 완료]  " if message.get("requires_action") and message.get("resolved") else ""
            item = QListWidgetItem(f'{unread}{required}{completed}{message["sender"]}     {message["time"]}\n{message["headline"]}')
            confirmed = bool(message.get("is_read")) or bool(
                message.get("requires_action") and message.get("resolved")
            )
            item.setForeground(
                QColor("#7f8b96" if confirmed else "#e7edf3")
            )
            item.setSizeHint(QSize(320, 64))
            item.setData(Qt.ItemDataRole.UserRole, message_index)
            self.inbox_list.addItem(item)
            if first_message_row is None:
                first_message_row = self.inbox_list.count() - 1
        self.inbox_list.blockSignals(False)
        self.inbox_count.setText(str(len(self.messages))) if hasattr(self, "inbox_count") else None
        if self.inbox_list.currentRow() < 0 and first_message_row is not None:
            self.inbox_list.setCurrentRow(first_message_row)

    def _set_inbox_item_read_style(self, row, is_read):
        item = self.inbox_list.item(row)
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        if is_read and item.text().startswith("●  "):
            item.setText(item.text()[3:])
        item.setForeground(QColor("#7f8b96" if is_read else "#e7edf3"))

    def _message_date_key(self, message):
        received_date = str(message.get("received_date") or "")
        if received_date:
            try:
                return date.fromisoformat(received_date).isoformat()
            except ValueError:
                pass
        value = str(message.get("time") or "")
        if value.count(".") == 2:
            return value.replace(".", "-")
        if self.current_date is not None:
            return self.current_date.isoformat()
        return "0000-00-00"

    def _date_group_title(self, date_key):
        if date_key == "0000-00-00":
            return "시작일"
        try:
            message_date = date.fromisoformat(date_key)
        except ValueError:
            return date_key.replace("-", ".")
        formatted = message_date.strftime("%Y.%m.%d")
        if self.current_date == message_date:
            return f"오늘  ·  {formatted}"
        if self.current_date and self.current_date - timedelta(days=1) == message_date:
            return f"어제  ·  {formatted}"
        return formatted

    def _message_index_for_row(self, row):
        if row < 0:
            return None
        item = self.inbox_list.item(row)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _row_for_message_index(self, message_index):
        for row in range(self.inbox_list.count()):
            item = self.inbox_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == message_index:
                return row
        return None

    def _update_unread_count(self):
        if self.save_database and self.save_id is not None:
            unread = (
                self.save_database.unread_daily_news_count(self.save_id)
                + self.save_database.unread_manager_event_count(self.save_id)
            )
        else:
            unread = 0
        self.notification_count_changed.emit(unread)

    def _load_team_players(self):
        if not self.db_path or not Path(self.db_path).exists():
            return
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM players
                WHERE (? IS NULL OR team = ?)
                ORDER BY status DESC, name
                """,
                (self.team_name, self.team_name),
            ).fetchall()
        finally:
            connection.close()
        states = (
            self.save_database.get_player_simulation_states(self.save_id, self.team_name)
            if self.save_database and self.save_id is not None else {}
        )
        players = []
        for row in rows:
            player = dict(row)
            state = states.get(player["id"], {})
            squad = state.get("squad_group")
            if player.get("status") != 1 and squad != "1군":
                continue
            player["state"] = state
            players.append(player)
        players.sort(key=lambda player: (
            -int(player["state"].get("injury_days", 0)),
            -int(player["state"].get("fatigue", 0)),
            int(player["state"].get("condition", 100)),
            player["name"],
        ))
        visible = players[:8]
        self.player_table.setRowCount(len(visible))
        for row_index, player in enumerate(visible):
            state = player["state"]
            injury_days = int(state.get("injury_days", 0))
            status = (
                f"{state.get('injury_type') or '부상'} · {injury_days}일"
                if injury_days else
                ("피로 관리" if int(state.get("fatigue", 0)) >= 55 else "정상")
            )
            values = (
                player["name"], player.get("pos") or "-",
                state.get("condition", "미측정"), state.get("fatigue", "-"), status,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value if value is not None else "-"))
                if column == 0:
                    link_font = item.font()
                    link_font.setUnderline(True)
                    item.setFont(link_font)
                    item.setToolTip(f"{player['name']} 선수 상세 정보 열기")
                    item.setData(Qt.ItemDataRole.UserRole, player)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.player_table.setItem(row_index, column, item)

    def _load_standings(self):
        states = []
        if self.save_database and self.save_id is not None:
            states = self.save_database.list_team_daily_states(self.save_id)
        by_team = {state["team"]: state for state in states}
        self.standings_table.setRowCount(len(TEAM_NAMES))
        for row, team in enumerate(TEAM_NAMES):
            state = by_team.get(team)
            values = (
                team,
                state["season_phase"] if state else "진행 전",
                f"{float(state['average_condition']):.0f}" if state else "-",
                f"{state['injured_count']}명" if state else "-",
                state["roster_need"] if state and state["roster_need"] else "점검 중",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    link_font = item.font()
                    link_font.setUnderline(True)
                    item.setFont(link_font)
                    item.setToolTip(f"{team} 구단 정보 열기")
                if column not in (0, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.standings_table.setItem(row, column, item)

    def _load_operational_dashboard(self):
        day = self.current_date or date(2025, 11, 1)
        phase_name, phase_detail = phase_for(day)
        state = None
        training = None
        if self.save_database and self.save_id is not None:
            states = self.save_database.list_team_daily_states(
                self.save_id, day.isoformat()
            ) or self.save_database.list_team_daily_states(self.save_id)
            state = next((item for item in states if item["team"] == self.team_name), None)
            plans = self.save_database.list_team_training_plans(
                self.save_id, team=self.team_name, plan_date=day.isoformat(), limit=1
            ) or self.save_database.list_team_training_plans(
                self.save_id, team=self.team_name, limit=1
            )
            training = plans[0] if plans else None

        self.phase_metric.setText(f"시즌 단계\n{phase_name}")
        self.condition_metric.setText(
            f"1군 평균 컨디션\n{float(state['average_condition']):.0f}"
            if state else "1군 평균 컨디션\n측정 전"
        )
        self.injury_metric.setText(
            f"선수단 부상\n{int(state['injured_count'])}명" if state else "선수단 부상\n0명"
        )
        self.task_metric.setText(f"필수 업무\n{len(self.pending_required_messages())}건")

        agenda_lines = [f"{day:%Y.%m.%d}  ·  {phase_name} — {phase_detail}"]
        events = SEASON_EVENTS.get(day, ())
        for event in events[:2]:
            agenda_lines.append(f"[{event['category']}] {event['title']}  ·  {event['task']}")
        if training:
            agenda_lines.append(
                f"[훈련] {training['focus']} · 강도 {training['intensity']}  —  {training['note']}"
            )
        elif not events:
            next_event = next(
                ((event_day, day_events[0]) for event_day, day_events in sorted(SEASON_EVENTS.items()) if event_day > day),
                None,
            )
            if next_event:
                agenda_lines.append(
                    f"다음 주요 일정  {next_event[0]:%m.%d}  ·  {next_event[1]['title']}"
                )
            else:
                agenda_lines.append("등록된 주요 일정이 없습니다. 선수단 상태와 훈련 보고서를 점검하세요.")
        self.today_agenda.setText("\n".join(agenda_lines))
        self._load_team_players()
        self._load_standings()

    def _open_dashboard_player(self, row, column):
        if (
            column != 0
            or getattr(self, "_detail_context", "operations")
            != "operations"
        ):
            return
        item = self.player_table.item(row, 0)
        player = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if player:
            self.player_requested.emit(player)

    def _open_standings_club(self, row, column):
        if (
            column != 0
            or getattr(self, "_detail_context", "operations")
            != "operations"
        ):
            return
        item = self.standings_table.item(row, 0)
        if item is not None:
            self.club_info_requested.emit(item.text())
