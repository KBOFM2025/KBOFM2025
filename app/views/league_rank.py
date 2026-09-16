"""FM 스타일의 메인 수신함과 뉴스 유형별 상세 대시보드."""

import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
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
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import TEAM_NAMES
from app.config.teams import TEAM_INFO
from app.config.season_schedule import SEASON_EVENTS, phase_for
from app.ai.context_builder import governance_profile_for
from app.player_ratings import overall_rating
from app.services.fa_eligibility import fa_eligibility_report
from app.services.negotiation_rules import LEVELS
from app.services.second_draft import FA_APPROVED_2025
from app.team_assets import team_logo_path
from app.utils import resource_path
from app.views.team_manage.player_profile import _player_photo_path
from database.paths import PLAYERS_DB_PATH


STADIUM_IMAGE_FILES = {
    "KIA 타이거즈": "kia.jpg", "삼성 라이온즈": "samsung.jpg",
    "LG 트윈스": "jamsil.jpg", "두산 베어스": "jamsil.jpg",
    "KT 위즈": "kt.jpg", "SSG 랜더스": "ssg.jpg",
    "롯데 자이언츠": "lotte.jpg", "한화 이글스": "hanwha.jpg",
    "NC 다이노스": "NC파크.png", "키움 히어로즈": "kiwoom.jpg",
}


class MedicalFeatureFrame(QFrame):
    """구장 사진 위에 의료 정보를 올리는 FM형 부상 전용 배경."""

    def __init__(self, team_name, parent=None):
        super().__init__(parent)
        self.setObjectName("MedicalFeature")
        filename = STADIUM_IMAGE_FILES.get(team_name or "", "")
        self._background = QPixmap(
            str(resource_path("image", "Stadium", filename))
        ) if filename else QPixmap()
        self.setMinimumHeight(350)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        target = QRectF(self.rect())
        if not self._background.isNull():
            source_size = self._background.size()
            target_ratio = target.width() / max(1.0, target.height())
            source_ratio = source_size.width() / max(1.0, source_size.height())
            if source_ratio > target_ratio:
                crop_width = source_size.height() * target_ratio
                source = QRectF(
                    (source_size.width() - crop_width) / 2,
                    0,
                    crop_width,
                    source_size.height(),
                )
            else:
                crop_height = source_size.width() / target_ratio
                source = QRectF(
                    0,
                    (source_size.height() - crop_height) / 2,
                    source_size.width(),
                    crop_height,
                )
            painter.drawPixmap(target, self._background, source)
        shade = QLinearGradient(0, 0, self.width(), 0)
        shade.setColorAt(0.0, QColor(7, 10, 14, 238))
        shade.setColorAt(0.38, QColor(9, 12, 16, 218))
        shade.setColorAt(1.0, QColor(8, 10, 13, 228))
        painter.fillRect(target, shade)
        painter.fillRect(target, QColor(8, 11, 15, 58))


class LeagueStatRing(QWidget):
    """뉴스 사이드바의 작은 원형 기록 지표."""

    def __init__(self, value, maximum, label, display=None, parent=None):
        super().__init__(parent)
        self.value = max(0, float(value))
        self.maximum = max(1, float(maximum))
        self.label = str(label)
        self.display = str(display if display is not None else value)
        self.setMinimumSize(76, 88)
        self.setMaximumWidth(96)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(12, 6, self.width() - 24, self.width() - 24)
        painter.setPen(QPen(QColor("#35414d"), 5))
        painter.drawArc(ring, 0, 360 * 16)
        painter.setPen(QPen(QColor("#4b9ed1"), 5))
        painter.drawArc(
            ring, 90 * 16,
            -int(360 * 16 * min(1.0, self.value / self.maximum)),
        )
        painter.setPen(QColor("#f1f5f8"))
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.drawText(ring, Qt.AlignmentFlag.AlignCenter, self.display)
        painter.setPen(QColor("#8f9ca8"))
        painter.setFont(QFont("Malgun Gothic", 10))
        painter.drawText(
            QRectF(0, self.width() - 5, self.width(), 22),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.label,
        )


class AdaptiveGrid(QWidget):
    """가용 폭에 따라 카드 열 수를 바꾸는 간단한 반응형 컨테이너."""

    def __init__(
        self,
        widgets,
        max_columns=2,
        medium_width=680,
        wide_width=1040,
        column_weights=None,
        spacing=10,
        parent=None,
    ):
        super().__init__(parent)
        self._widgets = list(widgets)
        self._max_columns = max(1, int(max_columns))
        self._medium_width = int(medium_width)
        self._wide_width = int(wide_width)
        self._column_weights = list(column_weights or [])
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(spacing)
        self._grid.setVerticalSpacing(spacing)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._relayout(1)

    def _column_count(self, width):
        if self._max_columns == 1 or width < self._medium_width:
            return 1
        if self._max_columns == 2 or width < self._wide_width:
            return min(2, self._max_columns)
        return self._max_columns

    def _relayout(self, width):
        columns = self._column_count(width)
        if columns == self._columns:
            return
        while self._grid.count():
            self._grid.takeAt(0)
        for column in range(self._max_columns):
            self._grid.setColumnStretch(column, 0)
        for index, widget in enumerate(self._widgets):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            weight = (
                self._column_weights[column]
                if columns > 1 and column < len(self._column_weights)
                else 1
            )
            self._grid.setColumnStretch(column, weight)
        self._columns = columns
        self.updateGeometry()

    def resizeEvent(self, event):
        self._relayout(event.size().width())
        super().resizeEvent(event)


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
        "headline": "스토브리그 선수단 구성과 포지션 경쟁 구도",
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

APPOINTMENT_PRESS_ITEM = {
    "category": "기자회견",
    "sender": "구단 홍보팀",
    "time": "14:25",
    "headline": "신임 감독 취임 기자회견 참석 요청",
    "body": (
        "공식 선임 발표가 완료되었습니다. 지역 연고 매체와 MBC·SBS·KBS·SPOTV "
        "기자들이 참석하는 취임 기자회견이 준비됐습니다. 수신함의 아래 버튼을 "
        "눌러 구단 목표와 선수단 운영 구상에 관한 공식 질의에 답변해 주십시오."
    ),
}


class LeagueRankTab(QWidget):
    """수신함 목록과 선택 메시지, 선수·리그 정보를 한 화면에 표시한다."""

    board_vision_requested = Signal()
    appointment_press_requested = Signal()
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
        manager_name=None,
    ):
        super().__init__()
        self.colors = colors
        self.team_name = team_name
        self.db_path = db_path or PLAYERS_DB_PATH
        self.save_database = save_database
        self.save_id = save_id
        self.manager_name = manager_name or "감독"
        self._read_static_messages = set()
        self.appointment_press_available = False
        self.appointment_press_completed = False
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
        inbox.setMinimumWidth(250)
        inbox.setMaximumWidth(410)
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
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("MessageDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.detail_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.detail_scroll.setWidget(detail)
        splitter.addWidget(self.detail_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((350, 1050))

        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QFrame#SectionNav {{ background-color: #171d24; border-bottom: 1px solid #35414f; }}
            QPushButton#SectionItem, QPushButton#ActiveSection {{ color: #a9b4c1; background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 4px 12px; font-size: 14px; }}
            QPushButton#SectionItem:hover {{ color: white; background: #202831; border-bottom-color: #586675; }}
            QPushButton#ActiveSection {{ color: white; border-bottom-color: {c['accent']}; font-weight: 700; }}
            QFrame#InboxPanel, QFrame#MessagePanel {{ background-color: #151a20; border: 1px solid #39434e; border-radius: 0; }}
            QScrollArea#MessageDetailScroll {{ background-color: #151a20; border: none; }}
            QScrollArea#MessageDetailScroll > QWidget > QWidget {{ background-color: #151a20; }}
            QScrollArea#MessageDetailScroll QScrollBar:vertical {{ background: #10151a; width: 10px; margin: 0; }}
            QScrollArea#MessageDetailScroll QScrollBar::handle:vertical {{ background: #526170; border-radius: 4px; min-height: 36px; }}
            QScrollArea#MessageDetailScroll QScrollBar::handle:vertical:hover {{ background: #6b7c8d; }}
            QScrollArea#MessageDetailScroll QScrollBar::add-line:vertical, QScrollArea#MessageDetailScroll QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollArea#MessageDetailScroll QScrollBar::add-page:vertical, QScrollArea#MessageDetailScroll QScrollBar::sub-page:vertical {{ background: transparent; }}
            QFrame#InboxHeader {{ background-color: #20262d; border-bottom: 1px solid #39434e; }}
            QLabel#InboxFilter {{ color: #e8eef5; font-size: 14px; font-weight: 600; }}
            QLabel#InboxCount {{ color: white; background-color: {c['accent']}; border-radius: 1px; padding: 1px 7px; font-weight: 700; }}
            QLabel#InboxDay {{ color: #aeb9c5; background-color: #10151a; padding: 6px 10px; font-size: 13px; font-weight: 600; }}
            QListWidget#InboxList {{ color: #dce4ec; background-color: #151a20; border: none; outline: none; font-size: 14px; }}
            QListWidget#InboxList::item {{ border-bottom: 1px solid #303943; padding: 7px 10px; }}
            QListWidget#InboxList::item:hover {{ background-color: #242b33; }}
            QListWidget#InboxList::item:selected {{ background-color: {c['tab_selected']}; border-left: 4px solid {c['accent_light']}; }}
            QLabel#SenderBadge {{ color: white; background-color: {c['accent']}; border-radius: 1px; font-size: 13px; font-weight: 800; }}
            QLabel#Sender {{ color: #f4f7fb; font-size: 15px; font-weight: 700; }}
            QLabel#MessageCategory, QLabel#MessageTime {{ color: #8492a1; font-size: 13px; }}
            QLabel#MessageHeadline {{ color: white; border-top: 1px solid #37414c; padding-top: 9px; font-size: 18px; font-weight: 700; }}
            QLabel#MessageBody {{ color: #c8d1da; padding: 2px 0 7px 0; font-size: 14px; }}
            QFrame#DataCard {{ background-color: #1b2128; border: 1px solid #343e49; border-radius: 0; }}
            QFrame#OperationsStrip {{ background-color: #11161b; border: 1px solid #343e49; }}
            QLabel#OperationMetric {{ color: #dbe3eb; background-color: #1a2027; border-right: 1px solid #343e49; padding: 6px 9px; font-size: 13px; }}
            QLabel#AgendaText {{ color: #c8d1da; padding: 1px 2px 4px 2px; font-size: 13px; }}
            QLabel#DataTitle {{ color: {c['accent_light']}; padding: 2px 2px 5px 2px; font-size: 14px; font-weight: 700; }}
            QFrame#NewsVisual {{ background-color: #171d24; border: 1px solid #39434e; }}
            QFrame#NewsVisual[context="trade"] {{ background-color: #101a26; border-color: #31577d; }}
            QFrame#NewsVisual[context="fa"] {{ background-color: #111e19; border-color: #347151; }}
            QFrame#NewsVisual[context="medical"] {{ background-color: #211416; border-color: #793b43; }}
            QFrame#NewsVisual[context="condition"] {{ background-color: #111a22; border-color: #3c6079; }}
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
            QLabel#VisualKicker {{ color: {c['accent_light']}; font-size: 13px; font-weight: 800; }}
            QLabel#VisualTitle {{ color: white; font-size: 22px; font-weight: 800; }}
            QLabel#VisualSummary {{ color: #b8c4cf; font-size: 14px; }}
            QFrame#VisualTile {{ background-color: #202731; border: 1px solid #3a4652; border-radius: 2px; }}
            QLabel#VisualTileLabel {{ color: #8493a2; font-size: 13px; font-weight: 700; }}
            QLabel#VisualTileValue {{ color: white; font-size: 16px; font-weight: 800; }}
            QLabel#VisualTileNote {{ color: #aeb9c4; font-size: 13px; }}
            QLabel#TradeArrow {{ color: {c['accent_light']}; font-size: 30px; font-weight: 900; }}
            QLabel#DialogueBubble {{ color: #e7edf3; background-color: #242c35; border: 1px solid #465361; border-radius: 4px; padding: 14px; font-size: 15px; }}
            QFrame#PlayerPortraitCard {{ background-color: #151b22; border: 1px solid #3b4856; border-radius: 5px; }}
            QLabel#PlayerPortrait {{ color: #e8eef5; background-color: #242d37; border: 1px solid #526170; border-radius: 4px; font-size: 30px; font-weight: 900; }}
            QLabel#PortraitName {{ color: white; font-size: 17px; font-weight: 900; }}
            QLabel#PortraitMeta {{ color: #9baaba; font-size: 13px; }}
            QLabel#ArticleEyebrow, QLabel#MeetingStamp {{ color: {c['accent_light']}; font-size: 13px; font-weight: 900; letter-spacing: 1px; }}
            QLabel#ArticleHeadline {{ color: white; font-size: 23px; font-weight: 900; padding: 3px 0; }}
            QLabel#ArticleByline {{ color: #7f8c99; font-size: 13px; padding-bottom: 6px; }}
            QLabel#ArticleLead {{ color: #d6dee6; font-size: 15px; padding: 7px 1px; }}
            QLabel#ArticleSubhead {{ color: white; font-size: 15px; font-weight: 800; }}
            QLabel#ArticleQuote {{ color: #d6dee6; background-color: #202831; border-left: 4px solid {c['accent_light']}; padding: 11px; font-size: 14px; }}
            QFrame#TradeDirection {{ background-color: #172638; border: 1px solid #31577d; border-radius: 4px; }}
            QLabel#TradeReply {{ color: #b9c8d7; font-size: 14px; padding-top: 4px; }}
            QFrame#MeetingLetter {{ background-color: #eee9df; border: 1px solid #c8bfae; border-radius: 4px; }}
            QLabel#MeetingStamp {{ color: #775495; }}
            QLabel#MeetingHeadline {{ color: #1c2025; font-size: 21px; font-weight: 900; }}
            QLabel#MeetingBody {{ color: #343b43; font-size: 15px; }}
            QLabel#MeetingQuote {{ color: #22272d; background-color: #ddd6c9; border-left: 4px solid #775495; padding: 13px; font-size: 15px; }}
            QLabel#MeetingAgenda {{ color: #675d50; border-top: 1px solid #bdb3a3; padding-top: 8px; font-size: 13px; font-weight: 700; }}
            QLabel#BigNumber {{ color: white; font-size: 38px; font-weight: 900; }}
            QLabel#BigCaption {{ color: #99a8b6; font-size: 13px; font-weight: 700; }}
            QLabel#FlowArrow {{ color: #7f91a2; font-size: 25px; font-weight: 900; }}
            QLabel#NewsMasthead {{ color: white; border-bottom: 3px solid {c['accent']}; padding-bottom: 7px; font-size: 27px; font-weight: 900; }}
            QLabel#NewsDeck {{ color: #aebac5; font-size: 15px; line-height: 1.4; }}
            QFrame#LeagueArticle {{ background-color: #15191e; border: none; }}
            QLabel#LeagueArticleKicker {{ color: #d4ad52; font-size: 13px; font-weight: 900; }}
            QLabel#NewsSummary {{ color: #9fb1bf; background-color: #1c252d; border-left: 3px solid #4b9ed1; padding: 8px 10px; font-size: 13px; font-weight: 700; }}
            QFrame#AssistantDeliveryPortrait {{ background-color: #090d12; border: 2px solid #465563; border-radius: 3px; }}
            QLabel#AssistantDeliveryPhoto {{ color: #8fa0ad; background-color: #202b35; border: none; font-size: 14px; font-weight: 800; }}
            QFrame#AssistantDeliveryCopy {{ background-color: #151c23; border: 1px solid #35434f; border-radius: 3px; }}
            QLabel#AssistantDeliveryKicker {{ color: #62aede; font-size: 13px; font-weight: 900; }}
            QLabel#AssistantDeliveryTitle {{ color: white; font-size: 22px; font-weight: 900; }}
            QLabel#AssistantDeliverySummary {{ color: #bbc6cf; font-size: 14px; }}
            QLabel#AssistantDeliveryNote {{ color: #8fa0ad; background-color: #1d2730; border-left: 3px solid #4b9ed1; padding: 8px; font-size: 13px; }}
            QLabel#ClubNoticeLogo {{ background-color: transparent; border: none; }}
            QLabel#ClubSecretaryName {{ color: #d8e2ea; font-size: 13px; font-weight: 800; }}
            QLabel#ClubNoticeMeta {{ color: {c['accent_light']}; font-size: 13px; font-weight: 800; }}
            QLabel#ClubNoticeHeadline {{ color: white; font-size: 23px; font-weight: 900; }}
            QFrame#ClubNoticeRule {{ color: #3c4650; background-color: #3c4650; max-height: 1px; }}
            QLabel#ClubNoticeLead {{ color: #e2e8ed; font-size: 15px; font-weight: 700; padding: 7px 2px; }}
            QLabel#ClubNoticeBody {{ color: #c1cad2; font-size: 14px; padding: 6px 2px; }}
            QLabel#ClubNoticeFooter {{ color: #7f8e9b; background-color: #11161b; border-top: 1px solid #343e47; padding: 9px; font-size: 13px; }}
            QLabel#LeagueArticleHeadline {{ color: white; font-size: 25px; font-weight: 900; padding: 3px 0 2px 0; }}
            QLabel#LeagueArticleDeck {{ color: #c5ced7; font-size: 15px; font-weight: 700; padding-bottom: 4px; }}
            QFrame#LeagueArticleRule {{ color: #3b4651; background-color: #3b4651; max-height: 1px; }}
            QLabel#LeagueArticleParagraph {{ color: #c0c8d0; font-size: 14px; padding: 5px 0; }}
            QLabel#LeagueArticleSubhead {{ color: white; border-bottom: 1px solid #38434d; padding: 10px 0 5px 0; font-size: 15px; font-weight: 900; }}
            QLabel#LeagueArticleQuote {{ color: #e4e9ee; background-color: #1e252c; border-left: 4px solid #d1aa4f; padding: 12px 14px; font-size: 14px; font-weight: 700; }}
            QLabel#LeagueArticleClosing {{ color: #8493a0; background-color: #11161b; border-top: 1px solid #36414b; padding: 10px; font-size: 13px; }}
            QFrame#LeagueNewsGraphic {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #263746, stop:0.55 #19242e, stop:1 #10171d); border: 1px solid #435362; border-radius: 5px; }}
            QLabel#LeagueSideEyebrow {{ color: #78b9df; font-size: 13px; font-weight: 900; }}
            QLabel#LeagueGraphicTitle {{ color: white; font-size: 22px; font-weight: 900; }}
            QLabel#LeagueGraphicPhase {{ color: #d4ad52; font-size: 15px; font-weight: 800; padding-bottom: 4px; }}
            QLabel#LeagueTeamLogo {{ background-color: rgba(9, 14, 19, 170); border: 1px solid #3b4b59; border-radius: 3px; }}
            QLabel#LeagueGraphicTeamName {{ color: white; font-size: 15px; font-weight: 900; padding-top: 2px; }}
            QFrame#LeagueSideCard {{ background-color: #20252b; border: 1px solid #383f47; border-radius: 5px; }}
            QLabel#LeagueSideTitle {{ color: #dce3e9; font-size: 13px; font-weight: 900; padding-bottom: 3px; }}
            QLabel#LeaguePointBadge {{ color: #11171d; background-color: #d4ad52; border-radius: 11px; font-size: 13px; font-weight: 900; }}
            QLabel#LeaguePointText {{ color: #b6c0c9; font-size: 13px; }}
            QLabel#LeagueNoteLabel {{ color: #d4ad52; font-size: 13px; font-weight: 900; padding-top: 4px; }}
            QLabel#LeagueNoteText {{ color: #aeb9c3; font-size: 13px; padding-bottom: 5px; }}
            QLabel#TimelineDate {{ color: white; background-color: #24616c; border-radius: 3px; padding: 12px; font-size: 20px; font-weight: 900; }}
            QFrame#TimelineRail {{ background-color: #17282d; border: none; border-left: 4px solid #3d8b99; }}
            QFrame#RosterAuditCallout {{ background-color: #1b272d; border: 1px solid #3b5964; border-left: 4px solid #d0a84e; }}
            QLabel#RosterAuditCalloutLabel {{ color: #f0c35f; font-size: 13px; font-weight: 900; padding-right: 8px; }}
            QLabel#RosterAuditCalloutText {{ color: #d3dde4; font-size: 13px; font-weight: 700; }}
            QTableWidget#RosterAuditPreview {{ color: #dce5eb; background-color: #10171c; alternate-background-color: #182128; border: 1px solid #394955; gridline-color: transparent; selection-background-color: #28506a; font-size: 13px; outline: none; }}
            QTableWidget#RosterAuditPreview::item {{ border-bottom: 1px solid #2d3942; padding: 0 8px; }}
            QFrame#ProfilePanel {{ background-color: #172b21; border: 1px solid #356b4e; border-radius: 3px; }}
            QLabel#ProfileInitial {{ color: #d9f4e5; background-color: #285a40; border-radius: 42px; font-size: 31px; font-weight: 900; }}
            QFrame#StatusPanel {{ background-color: #2b171a; border: 1px solid #743b43; border-radius: 3px; }}
            QFrame#MedicalFeature {{ background-color: #090c10; border: 1px solid #39434d; border-radius: 5px; }}
            QFrame#MedicalChart {{ background-color: #111820; border: 1px solid #40505d; border-radius: 5px; }}
            QLabel#MedicalSeverity {{ color: white; background-color: #a53f48; border-radius: 3px; padding: 5px 10px; font-size: 13px; font-weight: 900; }}
            QLabel#MedicalSeverity[level="clear"] {{ background-color: #287453; }}
            QLabel#MedicalSeverity[level="minor"] {{ background-color: #59717f; }}
            QLabel#MedicalSeverity[level="care"] {{ background-color: #a06b27; }}
            QLabel#MedicalSeverity[level="major"] {{ background-color: #a53f48; }}
            QLabel#MedicalChartTitle {{ color: white; font-size: 16px; font-weight: 900; }}
            QLabel#MedicalChartDate {{ color: #8796a4; font-size: 13px; }}
            QLabel#MedicalIntro {{ color: #e4e8ec; font-size: 15px; font-weight: 700; }}
            QLabel#MedicalIntroSub {{ color: #aeb7c0; font-size: 13px; padding-bottom: 3px; }}
            QFrame#MedicalProfile {{ background-color: #18232d; border: 1px solid #344654; border-radius: 4px; }}
            QLabel#MedicalPlayerPhoto {{ color: white; background-color: #243440; border: 1px solid #4a5d6b; border-radius: 3px; font-size: 28px; font-weight: 900; }}
            QLabel#MedicalPlayerName {{ color: white; font-size: 17px; font-weight: 900; }}
            QLabel#MedicalPlayerMeta {{ color: #c0c8d0; font-size: 13px; }}
            QLabel#MedicalPlayerTeam {{ color: #8795a3; font-size: 13px; }}
            QFrame#MedicalDiagnosisCard, QFrame#MedicalTimeline {{ background-color: #172029; border: 1px solid #33434f; border-radius: 4px; }}
            QLabel#MedicalCardKicker {{ color: #69b4df; font-size: 13px; font-weight: 900; }}
            QLabel#MedicalDiagnosisName {{ color: white; font-size: 20px; font-weight: 900; padding: 3px 0; }}
            QLabel#MedicalCardBody {{ color: #aebbc5; font-size: 13px; }}
            QLabel#MedicalTreatmentLine {{ color: #f0c56a; background-color: #202a33; border-left: 3px solid #d2a23d; padding: 8px 10px; font-size: 13px; font-weight: 700; }}
            QLabel#MedicalTimelineTitle {{ color: white; font-size: 17px; font-weight: 900; padding-bottom: 3px; }}
            QFrame#MedicalTimelineStep {{ background-color: #111820; border: none; border-left: 3px solid #526b7d; }}
            QLabel#MedicalTimelineLabel {{ color: #7f91a0; font-size: 13px; font-weight: 800; }}
            QLabel#MedicalTimelineValue {{ color: #dbe3ea; font-size: 13px; font-weight: 700; }}
            QFrame#MedicalDecision {{ background-color: #1c252d; border: 1px solid #4a3f2a; border-left: 4px solid #d2a23d; }}
            QLabel#MedicalDecisionIcon {{ color: #17130a; background-color: #e0ad3f; border-radius: 15px; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; qproperty-alignment: AlignCenter; font-size: 20px; font-weight: 900; }}
            QLabel#MedicalDecisionTitle {{ color: #f1c767; font-size: 13px; font-weight: 900; }}
            QLabel#MedicalDecisionBody {{ color: #d6dee5; font-size: 13px; }}
            QFrame#MedicalAlert {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8c2729, stop:1 #5e181c); border: 1px solid #a43b3e; border-radius: 4px; }}
            QLabel#MedicalCross {{ color: #29200c; background-color: #f0b52f; border-radius: 21px; font-size: 31px; font-weight: 900; }}
            QLabel#MedicalReportTitle {{ color: #f4b9b9; font-size: 13px; font-weight: 900; }}
            QLabel#MedicalTreatment {{ color: white; font-size: 15px; font-weight: 900; }}
            QLabel#MedicalReportMeta {{ color: #e7b4b5; font-size: 13px; }}
            QFrame#InjurySummary {{ background-color: rgba(9, 12, 16, 210); border: none; border-top: 1px solid #3b4148; }}
            QLabel#InjuryCurrentLabel {{ color: #da5558; font-size: 13px; font-weight: 900; }}
            QLabel#InjuryName {{ color: #ef5f61; font-size: 15px; font-weight: 900; }}
            QLabel#InjuryCause {{ color: #9da8b2; font-size: 13px; }}
            QFrame#InjuryFacts {{ background-color: rgba(9, 12, 16, 210); border: none; border-top: 1px solid #3b4148; }}
            QLabel#InjuryFactLabel {{ color: #7f8b96; font-size: 13px; }}
            QLabel#InjuryFactValue {{ color: #e0e5ea; font-size: 13px; font-weight: 700; }}
            QFrame#InjuryHistory {{ background-color: rgba(18, 22, 27, 225); border-top: 1px solid #353d45; }}
            QLabel#InjuryHistoryTitle {{ color: #8d99a4; font-size: 13px; font-weight: 900; }}
            QLabel#InjuryHistoryPlayer {{ color: white; font-size: 13px; font-weight: 800; }}
            QLabel#InjuryHistoryValue {{ color: #b4bec7; font-size: 13px; }}
            QLabel#MedicalFanReaction {{ color: #b7c0c9; background-color: #171d24; border-left: 4px solid #a63c3f; padding: 10px 12px; font-size: 13px; }}
            QLabel#ConditionSectionTitle {{ color: white; font-size: 15px; font-weight: 900; padding: 5px 1px 2px 1px; }}
            QFrame#WeeklyTeamStatus {{ background-color: #17212a; border: 1px solid #354653; border-radius: 3px; }}
            QFrame#WeeklyTeamStatus[changed="true"] {{ background-color: #192633; border-color: #47789b; }}
            QLabel#WeeklyTeamLogo {{ background-color: #10171e; border: 1px solid #334554; border-radius: 3px; }}
            QLabel#WeeklyTeamName {{ color: #f4f7fa; font-size: 15px; font-weight: 800; }}
            QLabel#WeeklyTeamChange {{ color: #b7c5d1; font-size: 13px; }}
            QLabel#WeeklyTeamChange[changed="false"] {{ color: #74818d; }}
            QFrame#ConditionStarCard {{ background-color: #17232d; border: 1px solid #344b5c; border-radius: 5px; }}
            QLabel#ConditionRank {{ color: #6eaed5; font-size: 13px; font-weight: 900; }}
            QLabel#ConditionPlayerPhoto {{ color: white; background-color: #243440; border: 1px solid #496171; border-radius: 3px; font-size: 23px; font-weight: 900; }}
            QLabel#ConditionPlayerName {{ color: white; font-size: 16px; font-weight: 900; }}
            QLabel#ConditionPlayerMeta {{ color: #91a3b1; font-size: 13px; }}
            QLabel#ConditionFieldLabel {{ color: #9aabb8; font-size: 13px; font-weight: 700; }}
            QLabel#ConditionValue {{ color: white; font-size: 15px; font-weight: 900; }}
            QLabel#ConditionCardFooter {{ color: #8193a1; font-size: 13px; }}
            QProgressBar#ConditionBar {{ background-color: #0b1218; border: none; border-radius: 3px; min-height: 7px; max-height: 7px; }}
            QProgressBar#ConditionBar::chunk {{ background-color: #63aee8; border-radius: 3px; }}
            QProgressBar#ConditionBar[level="good"]::chunk {{ background-color: #52c991; }}
            QProgressBar#ConditionBar[level="care"]::chunk {{ background-color: #e16868; }}
            QFrame#SquadConditionPanel {{ background-color: #172029; border: 1px solid #34434f; border-radius: 5px; }}
            QLabel#SquadConditionTitle {{ color: white; font-size: 16px; font-weight: 900; }}
            QLabel#SquadConditionCount {{ color: #98a9b7; background-color: #25323c; border-radius: 8px; padding: 2px 8px; font-size: 13px; font-weight: 800; }}
            QLabel#SquadConditionAverage {{ color: white; font-size: 35px; font-weight: 900; }}
            QLabel#SquadConditionAverageLabel {{ color: #8495a3; font-size: 13px; }}
            QProgressBar#SquadConditionBar {{ color: white; background-color: #0c1319; border: 1px solid #34444f; border-radius: 3px; min-height: 17px; text-align: center; font-size: 13px; font-weight: 800; }}
            QProgressBar#SquadConditionBar::chunk {{ background-color: #438f75; }}
            QFrame#ConditionStat {{ background-color: #101820; border: 1px solid #2b3944; border-radius: 3px; }}
            QLabel#ConditionStatValue {{ font-size: 17px; font-weight: 900; }}
            QLabel#ConditionStatLabel {{ color: #8394a1; font-size: 13px; }}
            QLabel#ConditionEmpty {{ color: #8fa0ad; background-color: #121a21; border: 1px dashed #3a4b58; padding: 28px; font-size: 14px; }}
            QFrame#BoardGoal {{ background-color: #292414; border: 1px solid #6f5d2d; border-radius: 3px; }}
            QFrame#BoardroomHero {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #172331, stop:0.62 #101820, stop:1 #15140f); border: 1px solid #4d5863; border-left: 5px solid #c2a35b; border-radius: 3px; }}
            QLabel#BoardroomLogo {{ color: white; background-color: rgba(7, 12, 18, 190); border: 1px solid #465462; border-radius: 3px; font-size: 28px; font-weight: 900; }}
            QLabel#BoardroomEyebrow {{ color: #c8aa62; font-size: 13px; font-weight: 900; letter-spacing: 1px; }}
            QLabel#BoardroomTitle {{ color: white; font-size: 23px; font-weight: 900; }}
            QLabel#BoardroomDeck {{ color: #afbbc6; font-size: 13px; }}
            QFrame#BoardroomStatus {{ background-color: #241f14; border: 1px solid #705f35; border-radius: 3px; min-width: 150px; }}
            QFrame#BoardroomStatus[resolved="true"] {{ background-color: #14241d; border-color: #3c7358; }}
            QLabel#BoardroomStatusLabel {{ color: #9b8a62; font-size: 13px; font-weight: 900; }}
            QLabel#BoardroomStatusValue {{ color: #f2d27d; font-size: 15px; font-weight: 900; }}
            QFrame#BoardroomStatus[resolved="true"] QLabel#BoardroomStatusValue {{ color: #75d39c; }}
            QLabel#BoardroomStatusNote {{ color: #9ba5ae; font-size: 13px; }}
            QFrame#BoardAgendaPanel {{ background-color: #11171d; border: 1px solid #3a4651; border-radius: 3px; }}
            QLabel#BoardSectionTitle {{ color: white; font-size: 15px; font-weight: 900; }}
            QLabel#BoardSectionGuide {{ color: #8594a1; border-bottom: 1px solid #303b45; padding-bottom: 7px; font-size: 13px; }}
            QFrame#BoardAgendaRow {{ background-color: #192129; border: 1px solid #35424e; border-radius: 3px; }}
            QFrame#BoardAgendaRow:hover {{ background-color: #1d2832; border-color: #536474; }}
            QFrame#BoardAgendaRow[required="true"] {{ border-left: 4px solid #d9b455; }}
            QLabel#BoardAgendaMarker {{ color: #d8b65e; background-color: #292514; border: 1px solid #746332; border-radius: 14px; font-size: 15px; font-weight: 900; }}
            QLabel#BoardAgendaTitle {{ color: #f2f5f7; font-size: 14px; font-weight: 800; }}
            QLabel#BoardAgendaDescription {{ color: #92a1ae; font-size: 13px; }}
            QLabel#BoardAgendaProposal {{ color: #f0d27d; background-color: #292414; border: 1px solid #6f5d2d; border-radius: 2px; padding: 4px 7px; font-size: 13px; font-weight: 800; min-width: 72px; }}
            QLabel#BoardAgendaPeriod {{ color: #748491; font-size: 13px; }}
            QFrame#BoardInformationCard {{ background-color: #17202a; border: 1px solid #354451; border-radius: 3px; }}
            QLabel#BoardInfoKicker {{ color: #c5a85f; font-size: 13px; font-weight: 900; letter-spacing: 1px; }}
            QLabel#BoardInfoTitle {{ color: white; font-size: 15px; font-weight: 900; }}
            QLabel#BoardInfoBody {{ color: #9eabb7; font-size: 13px; }}
            QFrame#BoardInfoDivider {{ background-color: #34414c; border: none; }}
            QLabel#BoardInfoSubhead {{ color: #dce3e8; font-size: 13px; font-weight: 800; }}
            QFrame#BoardroomCallout {{ background-color: #19232c; border: 1px solid #3c4b57; border-left: 4px solid #c4a45a; border-radius: 2px; }}
            QLabel#BoardCalloutBadge {{ color: #11161b; background-color: #c7a85d; border-radius: 2px; padding: 5px 8px; font-size: 13px; font-weight: 900; }}
            QLabel#BoardCalloutTitle {{ color: white; font-size: 14px; font-weight: 900; }}
            QLabel#BoardCalloutText {{ color: #91a0ac; font-size: 13px; }}
            QProgressBar#ContextProgress {{ color: white; background-color: #0f1419; border: 1px solid #3a4652; border-radius: 2px; text-align: center; min-height: 18px; }}
            QProgressBar#ContextProgress::chunk {{ background-color: {c['accent']}; }}
            QFrame#NewsVisual[context="fa"] QProgressBar#ContextProgress::chunk {{ background-color: #4fae78; }}
            QFrame#NewsVisual[context="medical"] QProgressBar#ContextProgress::chunk {{ background-color: #d94b4b; }}
            QFrame#NewsVisual[context="meeting"] QProgressBar#ContextProgress::chunk {{ background-color: #9a71d0; }}
            QFrame#NewsVisual[context="analysis"] QProgressBar#ContextProgress::chunk {{ background-color: #6c8fe0; }}
            QFrame#NewsVisual[context="squad"] QProgressBar#ContextProgress::chunk {{ background-color: #6f8fd0; }}
            QTableWidget {{ color: #e2e8ef; background-color: #1b2026; alternate-background-color: #23292f; border: none; font-size: 14px; }}
            QHeaderView::section {{ color: #9eacba; background-color: #151a1f; border: none; border-bottom: 1px solid #39434e; padding: 5px; font-size: 13px; font-weight: 600; }}
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
        self._set_sender_badge(
            message.get("sender") or "", badge_text, badge_color
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
        self.headline_label.setVisible(True)
        self.body_label.setVisible(True)
        self.operations_strip.setVisible(True)
        is_board_message = bool(message.get("is_board"))
        is_appointment_press = bool(message.get("is_appointment_press"))
        is_news_message = message.get("news_id") is not None
        is_manager_event = message.get("event_id") is not None
        is_rookie_draft = self._is_rookie_draft_message(message)
        self._render_message_context(message)
        self.detail_scroll.verticalScrollBar().setValue(0)
        self.message_action_button.setVisible(
            is_board_message
            or is_appointment_press
            or is_manager_event
            or (is_news_message and not is_rookie_draft)
        )
        self.message_action_button.setEnabled(
            is_board_message
            or (is_appointment_press and not message.get("resolved"))
            or is_manager_event
            or (is_news_message and not is_rookie_draft)
        )
        if is_board_message:
            self.message_action_button.setText(
                "이사회 목표 다시 보기  ›"
                if self.board_vision_reviewed
                else "필수 응답 · 이사회 목표 협상  ›"
            )
        elif is_appointment_press:
            self.message_action_button.setText(
                "취임 기자회견 처리 완료"
                if message.get("resolved")
                else "필수 응답 · 취임 기자회견 참석  ›"
            )
        elif is_manager_event:
            if message.get("headline") == "보류선수·계약 현황 1차 검토":
                self.message_action_button.setText(
                    "저장한 1차 분류안 보기  ›"
                    if message.get("resolved") else
                    "필수 업무 · 선수별 방침 정하기  ›"
                )
            else:
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
            "기자회견": ("PRESS", "#8b6c34"),
            "전력 분석": ("분석", "#416fa8"),
            "선수단": ("선수", "#526c9f"),
            "선수단 관리": ("계약", "#3d7180"),
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

    def _set_sender_badge(self, sender, badge_text, badge_color):
        self.sender_badge.setPixmap(QPixmap())
        self.sender_badge.setFixedSize(38, 38)
        self.sender_badge.setText(badge_text)
        self.sender_badge.setStyleSheet(
            "color: white;"
            f"background-color: {badge_color};"
            "border-radius: 2px;"
            "font-size: 13px;"
            "font-weight: 900;"
        )
        self.sender_badge.setToolTip("")

    def _activate_current_message(self):
        row = self.inbox_list.currentRow()
        message_index = self._message_index_for_row(row)
        if message_index is None:
            return
        self._show_message(row)
        message = self.messages[message_index]
        if message.get("is_board"):
            self.board_vision_requested.emit()
        elif message.get("is_appointment_press"):
            if not message.get("resolved"):
                self.appointment_press_requested.emit()
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
        elif "취임 기자회견" in str(message.get("headline") or ""):
            self._render_press_conference_news(message)
        elif event_type == "trade_offer" or "트레이드" in text:
            self._render_trade_context(message)
        elif event_type == "fa_opportunity" or category == "FA":
            self._render_fa_context(message)
        elif "컨디션" in str(message.get("headline") or "") and any(
            keyword in str(message.get("headline") or "")
            for keyword in ("점검", "보고", "안내")
        ):
            self._render_condition_context(message)
        elif (
            event_type == "injury"
            or category in ("부상", "의료 센터", "의무")
            or any(
                keyword in str(message.get("headline") or "")
                for keyword in ("부상", "치료", "재활", "복귀")
            )
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
        elif "FA 승인 선수" in text or "FA 승인" in text and "공시" in text:
            self._render_fa_approved_context(message)
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
        elif category in (
            "구단 뉴스", "구단 공식 발표", "프런트 브리핑", "시즌 전망",
        ):
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
        self._prepare_visual_only("news")
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        heading = QVBoxLayout()
        heading.addWidget(self._article_label(
            f"{message.get('category') or '새 소식'}  ·  "
            f"{self._message_date_key(message).replace('-', '.')}",
            "LeagueArticleKicker",
        ))
        heading.addWidget(self._article_label(
            message.get("headline") or "새 소식",
            "LeagueArticleHeadline",
        ))
        heading.addWidget(self._article_label(
            message.get("body") or "상세 내용이 없습니다.",
            "LeagueArticleDeck",
        ))
        heading.addStretch()
        self.news_visual_layout.addLayout(heading)
        self.news_visual_layout.addWidget(self._article_label(
            message.get("body") or "상세 내용이 없습니다.",
            "LeagueArticleParagraph",
        ))
        self.news_visual_layout.addStretch()
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
            f"color: {accent}; font-size: 13px; font-weight: 800;"
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

    def _player_record(self, player_id=None, name=None, team=None):
        """메시지 payload를 실제 선수 데이터와 연결한다."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            if player_id:
                row = connection.execute(
                    "SELECT * FROM players WHERE id=?", (int(player_id),)
                ).fetchone()
                if row is not None:
                    return dict(row)
            if name:
                query = "SELECT * FROM players WHERE name=?"
                params = [str(name)]
                if team:
                    query += " AND team=?"
                    params.append(str(team))
                row = connection.execute(query + " LIMIT 1", params).fetchone()
                if row is not None:
                    return dict(row)
        except (sqlite3.Error, TypeError, ValueError):
            return {}
        finally:
            connection.close()
        return {}

    def _player_portrait(self, player, fallback_name, caption=""):
        card = QFrame()
        card.setObjectName("PlayerPortraitCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        name = str(player.get("name") or fallback_name or "선수")
        portrait = QLabel()
        portrait.setObjectName("PlayerPortrait")
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait.setFixedSize(132, 150)
        photo_path = _player_photo_path(
            player.get("kbo_player_id"), name, player.get("team")
        )
        if photo_path and Path(photo_path).exists():
            pixmap = QPixmap(str(photo_path))
            if not pixmap.isNull():
                portrait.setPixmap(
                    pixmap.scaled(
                        portrait.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        if portrait.pixmap() is None or portrait.pixmap().isNull():
            portrait.setText(name[-2:])
        layout.addWidget(portrait, 0, Qt.AlignmentFlag.AlignHCenter)

        name_label = QLabel(name)
        name_label.setObjectName("PortraitName")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        meta = caption or " · ".join(
            value for value in (
                str(player.get("team") or ""),
                str(player.get("pos") or player.get("position_group") or ""),
            ) if value
        )
        meta_label = QLabel(meta or "선수 정보 확인 중")
        meta_label.setObjectName("PortraitMeta")
        meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta_label.setWordWrap(True)
        layout.addWidget(meta_label)
        return card

    @staticmethod
    def _article_label(text, object_name, word_wrap=True):
        label = QLabel(str(text or ""))
        label.setObjectName(object_name)
        label.setWordWrap(word_wrap)
        return label

    @staticmethod
    def _uses_assistant_portrait(message):
        sender = str(message.get("sender") or "").replace(" ", "")
        return sender in {
            "KBO뉴스센터", "메디컬센터", "데이터분석팀",
        }

    def _assistant_portrait_card(self):
        frame = QFrame()
        frame.setObjectName("AssistantDeliveryPortrait")
        frame.setFixedSize(184, 208)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        photo = QLabel("비서 사진")
        photo.setObjectName("AssistantDeliveryPhoto")
        photo.setFixedSize(172, 196)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(resource_path(
            "image", "staff", "assistant_secretary.png"
        )))
        if not pixmap.isNull():
            photo.setText("")
            photo.setPixmap(pixmap.scaled(
                photo.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        layout.addWidget(photo)
        return frame

    def _add_assistant_delivery_header(
        self, message, kicker, title, summary
    ):
        if not self._uses_assistant_portrait(message):
            return
        portrait = self._assistant_portrait_card()
        copy = QFrame()
        copy.setObjectName("AssistantDeliveryCopy")
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(16, 13, 16, 14)
        copy_layout.setSpacing(7)
        copy_layout.addWidget(
            self._article_label(kicker, "AssistantDeliveryKicker")
        )
        copy_layout.addWidget(
            self._article_label(title, "AssistantDeliveryTitle")
        )
        copy_layout.addWidget(
            self._article_label(summary, "AssistantDeliverySummary")
        )
        copy_layout.addStretch()
        copy_layout.addWidget(self._article_label(
            "구단 비서 전달  |  담당 부서의 보고 내용을 정리했습니다.",
            "AssistantDeliveryNote",
        ))
        self.news_visual_layout.addWidget(AdaptiveGrid(
            (portrait, copy),
            max_columns=2,
            medium_width=650,
            column_weights=(0, 1),
            spacing=16,
        ))

    @staticmethod
    def _month_roster_reason(month):
        return {
            11: "포스트시즌 종료 뒤 선수단 뎁스를 재점검하는 과정에서 즉시 전력과 성장 가능성을 함께 확인하기 위해",
            12: "비시즌 전력 구상을 구체화하고 내년 캠프의 포지션 경쟁 후보를 선별하기 위해",
            1: "스프링캠프 준비 상태와 선수별 훈련 성과를 반영해 경쟁의 폭을 넓히기 위해",
            2: "실전 캠프 점검 결과와 개막 엔트리 경쟁력을 반영하기 위해",
            3: "개막 직전 컨디션과 최근 실전 경기력을 반영해 즉시 전력을 보강하기 위해",
        }.get(month, "최근 경기력과 선수단의 포지션별 필요를 종합적으로 검토해")

    @staticmethod
    def _fame_reaction(player):
        try:
            rating = int(overall_rating(player)) if player else 0
        except (TypeError, ValueError):
            rating = 0
        salary = int(player.get("salary") or 0) if player else 0
        fame_score = rating + (2 if salary >= 50000 else 1 if salary >= 20000 else 0)
        if fame_score >= 18:
            return "리그 스타", "주축 선수의 이탈 소식에 팬 커뮤니티와 SNS에서는 큰 우려와 빠른 회복을 바라는 반응이 이어지고 있다."
        if fame_score >= 15:
            return "구단 핵심", "팬들은 핵심 전력의 공백이 팀 운영에 미칠 영향을 걱정하며 정확한 복귀 일정을 기다리고 있다."
        if fame_score >= 12:
            return "1군 전력", "로테이션과 벤치 운용에 생길 공백을 아쉬워하는 팬들의 반응이 나오고 있다."
        return "성장 자원", "팬들은 성장 흐름이 끊기지 않도록 충분한 회복과 신중한 복귀 결정을 당부하고 있다."

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
        self._add_assistant_delivery_header(
            message,
            "KBO NEWS CENTER",
            "2차 드래프트 브리핑",
            "지명 절차와 구단별 결과를 KBO 뉴스센터에서 전달받았습니다.",
        )
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
        outgoing_player = self._player_record(
            terms.get("outgoing_id") or payload.get("outgoing_id"),
            outgoing,
            self.team_name,
        )
        incoming_player = self._player_record(
            terms.get("incoming_id") or payload.get("incoming_id"),
            incoming,
            other_team,
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
        outgoing_role = "1군 전력" if int(outgoing_player.get("status") or 0) == 1 else "퓨처스·육성 전력"
        outgoing_salary = int(outgoing_player.get("salary") or payload.get("outgoing_salary") or 0)
        outgoing_meta = (
            f"{outgoing_player.get('pos') or '포지션 미정'} · {outgoing_role}\n"
            f"{outgoing_player.get('age') or '-'}세 · 평가 {outgoing_rating or '-'} · "
            f"연봉 {outgoing_salary:,}만원"
        )
        exchange.addWidget(self._player_portrait(outgoing_player, outgoing, outgoing_meta), 4)
        arrow = QLabel("⇄")
        arrow.setObjectName("TradeArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exchange.addWidget(arrow)
        incoming_role = "1군 전력" if int(incoming_player.get("status") or 0) == 1 else "퓨처스·육성 전력"
        incoming_salary = int(incoming_player.get("salary") or payload.get("incoming_salary") or 0)
        incoming_meta = (
            f"{incoming_player.get('pos') or '포지션 미정'} · {incoming_role}\n"
            f"{incoming_player.get('age') or '-'}세 · 평가 {incoming_rating or '-'} · "
            f"연봉 {incoming_salary:,}만원"
        )
        exchange.addWidget(self._player_portrait(incoming_player, incoming, incoming_meta), 4)
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
        direction = QFrame()
        direction.setObjectName("TradeDirection")
        direction_layout = QVBoxLayout(direction)
        direction_layout.setContentsMargins(15, 12, 15, 13)
        direction_layout.addWidget(self._article_label("상대 구단의 협상 방향", "ArticleEyebrow"))
        direction_layout.addWidget(self._article_label(
            f"{other_team}은(는) {outgoing}을 핵심 대상으로 보고 있으며, "
            f"현재 추가 조건은 ‘{compensation}’입니다.", "ArticleSubhead"
        ))
        direction_layout.addWidget(self._article_label(
            terms.get("reply") or "우리 단장이 감독의 의견을 정리해 상대 구단에 전달합니다. 조건의 균형과 선수단 공백을 함께 검토하십시오.",
            "TradeReply",
        ))
        self.news_visual_layout.addWidget(direction)
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
        cap = dict(payload.get("salary_cap") or {})
        if cap:
            projected = int(cap.get("projected") or 0)
            limit = int(cap.get("limit") or 0)
            excess = int(cap.get("excess") or 0)
            contract_layout.addWidget(self._visual_tile(
                "2026 경쟁균형세 전망",
                f"{projected:,}만원 / {limit:,}만원",
                (
                    f"상한 {excess:,}만원 초과 · 1회 기준 발전기금 "
                    f"{int(cap.get('first_excess_levy') or 0):,}만원"
                    if excess else
                    f"계약 후 잔여 한도 {int(cap.get('projected_room') or 0):,}만원"
                ),
            ))
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
            ("캡 여유", f"{int(cap.get('projected_room') or 0):,}만원" if cap else "-"),
        )

    def _condition_roster(self):
        if not self.db_path or not Path(self.db_path).exists():
            return []
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM players WHERE team=?",
                (self.team_name,),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()
        states = (
            self.save_database.get_player_simulation_states(
                self.save_id, self.team_name
            )
            if self.save_database and self.save_id is not None else {}
        )
        roster = []
        for row in rows:
            player = dict(row)
            state = states.get(player["id"], {})
            player["_condition"] = int(
                state.get("condition")
                or player.get("sim_condition")
                or 85
            )
            player["_fatigue"] = int(
                state.get("fatigue")
                or player.get("sim_fatigue")
                or 0
            )
            player["_squad"] = state.get("squad_group") or (
                "1군" if int(player.get("status") or 0) == 1 else "2군"
            )
            player["_overall"] = float(overall_rating(player))
            roster.append(player)
        return roster

    def _condition_player_card(self, player, rank):
        card = QFrame()
        card.setObjectName("ConditionStarCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(7)

        rank_label = QLabel(f"CURRENT ABILITY  #{rank}")
        rank_label.setObjectName("ConditionRank")
        layout.addWidget(rank_label)
        profile = QHBoxLayout()
        profile.setSpacing(10)
        photo = QLabel((player.get("name") or "선수")[-2:])
        photo.setObjectName("ConditionPlayerPhoto")
        photo.setFixedSize(82, 94)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo_path = _player_photo_path(
            player.get("kbo_player_id"),
            player.get("name"),
            player.get("team"),
        )
        if photo_path:
            pixmap = QPixmap(str(photo_path))
            if not pixmap.isNull():
                photo.setText("")
                photo.setPixmap(pixmap.scaled(
                    photo.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        profile.addWidget(photo)
        identity = QVBoxLayout()
        name = QLabel(player.get("name") or "-")
        name.setObjectName("ConditionPlayerName")
        identity.addWidget(name)
        meta = QLabel(
            f"{player.get('pos') or '-'}  ·  {player['_squad']}\n"
            f"현재 능력  {player['_overall']:.1f} / 20"
        )
        meta.setObjectName("ConditionPlayerMeta")
        identity.addWidget(meta)
        identity.addStretch()
        profile.addLayout(identity, 1)
        layout.addLayout(profile)

        condition = int(player["_condition"])
        condition_row = QHBoxLayout()
        condition_label = QLabel("컨디션")
        condition_label.setObjectName("ConditionFieldLabel")
        condition_row.addWidget(condition_label)
        condition_row.addStretch()
        condition_value = QLabel(f"{condition}%")
        condition_value.setObjectName("ConditionValue")
        condition_row.addWidget(condition_value)
        layout.addLayout(condition_row)
        bar = QProgressBar()
        bar.setObjectName("ConditionBar")
        bar.setRange(0, 100)
        bar.setValue(condition)
        bar.setTextVisible(False)
        bar.setProperty(
            "level", "good" if condition >= 90 else
            "normal" if condition >= 75 else "care"
        )
        layout.addWidget(bar)
        footer = QLabel(
            f"피로도 {player['_fatigue']}  ·  "
            f"{'최상' if condition >= 90 else '정상' if condition >= 75 else '관리 필요'}"
        )
        footer.setObjectName("ConditionCardFooter")
        layout.addWidget(footer)
        return card

    def _condition_squad_panel(self, title, players, accent):
        panel = QFrame()
        panel.setObjectName("SquadConditionPanel")
        panel.setStyleSheet(
            "QFrame#SquadConditionPanel {"
            f"border-top: 4px solid {accent};"
            "}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("SquadConditionTitle")
        heading.addWidget(title_label)
        heading.addStretch()
        count = QLabel(f"{len(players)}명")
        count.setObjectName("SquadConditionCount")
        heading.addWidget(count)
        layout.addLayout(heading)

        values = [int(player["_condition"]) for player in players]
        fatigues = [int(player["_fatigue"]) for player in players]
        average = round(sum(values) / len(values)) if values else 0
        average_row = QHBoxLayout()
        average_number = QLabel(str(average) if values else "-")
        average_number.setObjectName("SquadConditionAverage")
        average_row.addWidget(average_number)
        average_text = QLabel("평균 컨디션\n100점 기준")
        average_text.setObjectName("SquadConditionAverageLabel")
        average_row.addWidget(average_text)
        average_row.addStretch()
        layout.addLayout(average_row)
        bar = QProgressBar()
        bar.setObjectName("SquadConditionBar")
        bar.setRange(0, 100)
        bar.setValue(average)
        bar.setFormat(f"{average}%")
        layout.addWidget(bar)

        good = sum(value >= 90 for value in values)
        normal = sum(75 <= value < 90 for value in values)
        care = sum(value < 75 for value in values)
        average_fatigue = (
            round(sum(fatigues) / len(fatigues)) if fatigues else 0
        )
        grid = QGridLayout()
        grid.setSpacing(6)
        stats = (
            ("최상", good, "#52c991"),
            ("정상", normal, "#63aee8"),
            ("관리 필요", care, "#e16868"),
            ("평균 피로", average_fatigue, "#d5a84d"),
        )
        for index, (label, value, color) in enumerate(stats):
            tile = QFrame()
            tile.setObjectName("ConditionStat")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(9, 7, 9, 7)
            value_label = QLabel(str(value))
            value_label.setObjectName("ConditionStatValue")
            value_label.setStyleSheet(f"color: {color};")
            tile_layout.addWidget(value_label)
            label_widget = QLabel(label)
            label_widget.setObjectName("ConditionStatLabel")
            tile_layout.addWidget(label_widget)
            grid.addWidget(tile, 0, index)
        layout.addLayout(grid)
        return panel

    def _render_condition_context(self, message):
        self._prepare_visual_only("condition")
        self.operations_strip.setVisible(False)
        roster = self._condition_roster()
        ranked = sorted(
            roster,
            key=lambda player: (
                player["_overall"],
                player["_condition"],
                player.get("name") or "",
            ),
            reverse=True,
        )
        top_players = ranked[:3]
        first_team = [
            player for player in roster if player["_squad"] == "1군"
        ]
        second_team = [
            player for player in roster if player["_squad"] != "1군"
        ]
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self._add_assistant_delivery_header(
            message,
            "MEDICAL CENTER BRIEFING",
            "선수단 초기 컨디션 점검",
            "핵심 선수와 1·2군 전체 컨디션 현황을 전달드립니다.",
        )
        self.news_visual_layout.addWidget(self._visual_hero(
            "SQUAD CONDITION REPORT",
            "핵심 선수 컨디션 점검",
            "현재 능력이 가장 높은 핵심 선수 3명과 1·2군 전체 "
            "컨디션을 구분해 표시합니다.",
        ))
        section = QLabel("현재 능력 상위 3명")
        section.setObjectName("ConditionSectionTitle")
        self.news_visual_layout.addWidget(section)
        star_cards = []
        for index, player in enumerate(top_players, 1):
            star_cards.append(self._condition_player_card(player, index))
        if not top_players:
            empty = QLabel("선수단 컨디션 데이터가 아직 준비되지 않았습니다.")
            empty.setObjectName("ConditionEmpty")
            star_cards.append(empty)
        self.news_visual_layout.addWidget(AdaptiveGrid(
            star_cards,
            max_columns=3,
            medium_width=560,
            wide_width=930,
            spacing=9,
        ))

        summary_title = QLabel("선수단 전체 컨디션")
        summary_title.setObjectName("ConditionSectionTitle")
        self.news_visual_layout.addWidget(summary_title)
        squad_cards = (
            self._condition_squad_panel(
                "1군 선수단", first_team, "#4fae78"
            ),
            self._condition_squad_panel(
                "2군 선수단", second_team, "#4f8dcc"
            ),
        )
        self.news_visual_layout.addWidget(AdaptiveGrid(
            squad_cards,
            max_columns=2,
            medium_width=760,
            spacing=10,
        ))
        self.news_visual_layout.addStretch()

        top_average = (
            round(sum(player["_condition"] for player in top_players)
                  / len(top_players))
            if top_players else "-"
        )
        first_average = (
            round(sum(player["_condition"] for player in first_team)
                  / len(first_team))
            if first_team else "-"
        )
        second_average = (
            round(sum(player["_condition"] for player in second_team)
                  / len(second_team))
            if second_team else "-"
        )
        self._set_context_metrics(
            ("보고서", "초기 컨디션"),
            ("핵심 3인 평균", top_average),
            ("1군 평균", first_average),
            ("2군 평균", second_average),
        )

    def _render_medical_context(self, message):
        self._prepare_visual_only("medical")
        payload = self._payload_for(message)
        headline = str(message.get("headline") or "")
        body = str(message.get("body") or "")

        # 리그 뉴스는 "구단명 선수명"으로 시작한다. 구단명을 선수명에
        # 포함시키면 사진과 선수 DB 연결이 모두 실패하므로 먼저 분리한다.
        reported_team = str(payload.get("team") or "").strip()
        if not reported_team:
            reported_team = next(
                (
                    team_name for team_name in TEAM_NAMES
                    if headline.startswith(f"{team_name} ")
                    or f"{team_name}의 " in body
                ),
                "",
            )
        player_headline = headline
        if reported_team and player_headline.startswith(f"{reported_team} "):
            player_headline = player_headline[len(reported_team):].strip()
        headline_player = re.match(
            r"(.+?)(?:,|\s+부상|\s+치료|\s+회복|\s+재활)",
            player_headline,
        )
        player = payload.get("player_name") or (
            headline_player.group(1).strip()
            if headline_player else "선수단"
        )
        days = int(payload.get("expected_days") or self._extract_number(
            f"{headline} {body}", r"(\d+)일"
        ) or 0)
        recovered = "회복" in headline or "재활을 마쳤" in body
        diagnosis_match = re.search(
            r"(?:이\(가\)|가)\s+([^.\n]+?)\s+진단", body
        )
        diagnosis = (
            "정상 훈련 복귀"
            if recovered
            else str(payload.get("injury_type") or "").strip()
            if payload.get("injury_type")
            else diagnosis_match.group(1).strip()
            if diagnosis_match
            else "훈련 중 근육 이상"
        )
        player_record = self._player_record(
            payload.get("player_id"), player,
            reported_team or self.team_name,
        )
        if not player_record and (
            player == self.manager_name or str(player).endswith("감독")
        ):
            # 기사 분류가 잘못돼도 감독을 부상 선수로 그리지 않는다.
            self._render_generic_news_context(message)
            return
        fame_label, fan_reaction = self._fame_reaction(player_record)
        team = (
            player_record.get("team") or reported_team
            or self.team_name or "KBO"
        )
        message_date = self._message_date_key(message)
        try:
            injury_date = date.fromisoformat(message_date)
            return_date = injury_date + timedelta(days=max(1, days))
            injury_date_text = injury_date.strftime("%Y.%m.%d")
            return_date_text = return_date.strftime("%Y.%m.%d")
        except ValueError:
            injury_date_text = message_date.replace("-", ".")
            return_date_text = "메디컬 재검 후 확정"
        treatment = (
            "정상 훈련 복귀 및 출전 가능"
            if recovered else
            "완전 휴식 후 통증 반응 재검"
            if days <= 7 else
            "통증 완화 치료와 재활조 프로그램 병행"
            if days <= 21 else
            "정밀 치료 후 재활·실전 훈련 단계별 복귀"
        )
        return_status = "출전 가능" if recovered else "팀 훈련 제외"
        severity = (
            "복귀 완료" if recovered else
            "경미" if days <= 7 else
            "주의" if days <= 21 else
            "장기 이탈"
        )
        condition = int(
            payload.get("condition")
            or self._extract_number(body, r"컨디션\s*(\d+)")
            or 0
        )
        fatigue = int(
            payload.get("fatigue")
            or self._extract_number(body, r"피로도\s*(\d+)")
            or 0
        )
        squad_match = re.search(r"(?:소속은|기존)\s*(1군|2군)", body)
        squad = payload.get("squad") or (
            squad_match.group(1) if squad_match else "1군"
        )

        self._clear_news_visual()
        self.news_visual.setVisible(True)
        is_league_medical_news = (
            message.get("news_id") is not None
            and team != self.team_name
        )
        self._add_assistant_delivery_header(
            message,
            "KBO MEDICAL NEWSWIRE" if is_league_medical_news else "MEDICAL CENTER REPORT",
            (
                f"{team} {player}, {diagnosis}로 전력 이탈"
                if is_league_medical_news and not recovered else
                f"{team} {player}, 재활 마치고 훈련 복귀"
                if is_league_medical_news else
                f"{player} 메디컬 보고"
            ),
            (
                f"리그 메디컬 속보입니다. 예상 이탈 기간과 {team}의 전력 영향을 정리했습니다."
                if is_league_medical_news else
                f"{diagnosis} 진단과 치료 방침을 메디컬 센터에서 전달받았습니다."
            ),
        )
        chart = QFrame()
        chart.setObjectName("MedicalChart")
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(18, 16, 18, 18)
        chart_layout.setSpacing(12)

        report_header = QHBoxLayout()
        report_header.setSpacing(10)
        severity_badge = QLabel(severity)
        severity_badge.setObjectName("MedicalSeverity")
        severity_badge.setProperty(
            "level", "clear" if recovered else
            "minor" if days <= 7 else "care" if days <= 21 else "major"
        )
        report_header.addWidget(severity_badge)
        report_header.addWidget(self._article_label(
            "선수 메디컬 차트", "MedicalChartTitle"
        ))
        report_header.addStretch()
        report_header.addWidget(self._article_label(
            f"보고일  {injury_date_text}", "MedicalChartDate"
        ))
        chart_layout.addLayout(report_header)

        profile = QFrame()
        profile.setObjectName("MedicalProfile")
        profile_layout = QVBoxLayout(profile)
        profile_layout.setContentsMargins(13, 12, 13, 13)
        profile_layout.setSpacing(8)
        photo = QLabel(player[-2:])
        photo.setObjectName("MedicalPlayerPhoto")
        photo.setFixedSize(128, 144)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo_path = _player_photo_path(
            player_record.get("kbo_player_id"), player, team
        )
        if photo_path:
            pixmap = QPixmap(str(photo_path))
            if not pixmap.isNull():
                photo.setText("")
                photo.setPixmap(pixmap.scaled(
                    photo.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        profile_layout.addWidget(photo, 0, Qt.AlignmentFlag.AlignHCenter)
        name_row = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(38, 30)
        logo_pixmap = QPixmap(str(team_logo_path(team)))
        if not logo_pixmap.isNull():
            logo.setPixmap(logo_pixmap.scaled(
                logo.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        name_row.addWidget(logo)
        name_row.addWidget(
            self._article_label(player, "MedicalPlayerName")
        )
        name_row.addStretch()
        profile_layout.addLayout(name_row)
        profile_layout.addWidget(self._article_label(
            f"{player_record.get('age') or '-'}세  ·  "
            f"{player_record.get('pos') or '-'}  ·  {squad}  ·  {fame_label}",
            "MedicalPlayerMeta",
        ))
        profile_layout.addWidget(
            self._article_label(team, "MedicalPlayerTeam")
        )

        diagnosis_card = QFrame()
        diagnosis_card.setObjectName("MedicalDiagnosisCard")
        diagnosis_layout = QVBoxLayout(diagnosis_card)
        diagnosis_layout.setContentsMargins(16, 15, 16, 15)
        diagnosis_layout.setSpacing(8)
        diagnosis_layout.addWidget(self._article_label(
            "DIAGNOSIS", "MedicalCardKicker"
        ))
        diagnosis_layout.addWidget(
            self._article_label(diagnosis, "MedicalDiagnosisName")
        )
        diagnosis_layout.addWidget(self._article_label(
            "메디컬팀 관찰 아래 정상 훈련 강도를 회복하고 있습니다."
            if recovered else
            f"검사 결과 {diagnosis} 소견이 확인됐습니다. "
            f"현재 {squad} 훈련 명단에서 제외해 회복 상태를 관찰합니다.",
            "MedicalCardBody",
        ))
        diagnosis_layout.addStretch()
        diagnosis_layout.addWidget(self._article_label(
            f"치료 방침  ·  {treatment}", "MedicalTreatmentLine"
        ))

        timeline = QFrame()
        timeline.setObjectName("MedicalTimeline")
        timeline_layout = QVBoxLayout(timeline)
        timeline_layout.setContentsMargins(16, 15, 16, 15)
        timeline_layout.setSpacing(7)
        timeline_layout.addWidget(self._article_label(
            "RETURN PLAN", "MedicalCardKicker"
        ))
        timeline_layout.addWidget(self._article_label(
            "복귀 일정" if not recovered else "복귀 승인",
            "MedicalTimelineTitle",
        ))
        timeline_steps = (
            ("01  진단", injury_date_text),
            ("02  치료·재활", treatment),
            ("03  복귀 예정", return_date_text),
        )
        for label, value in timeline_steps:
            step = QFrame()
            step.setObjectName("MedicalTimelineStep")
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(10, 7, 10, 7)
            step_layout.setSpacing(2)
            step_layout.addWidget(self._article_label(
                label, "MedicalTimelineLabel"
            ))
            step_layout.addWidget(self._article_label(
                value, "MedicalTimelineValue"
            ))
            timeline_layout.addWidget(step)

        chart_layout.addWidget(AdaptiveGrid(
            (profile, diagnosis_card, timeline),
            max_columns=3,
            medium_width=670,
            wide_width=1060,
            spacing=10,
        ))

        fact_cards = []
        for label, value, note in (
            ("예상 이탈", "복귀 완료" if recovered else f"{days or '-'}일", severity),
            ("현재 조치", return_status, squad),
            ("컨디션", f"{condition}%" if condition else "확인 중", "부상 발생 시점"),
            ("피로도", str(fatigue) if fatigue else "확인 중", "100점 기준"),
        ):
            fact_cards.append(self._visual_tile(label, value, note))
        chart_layout.addWidget(AdaptiveGrid(
            fact_cards,
            max_columns=4,
            medium_width=560,
            wide_width=980,
            spacing=8,
        ))

        decision = QFrame()
        decision.setObjectName("MedicalDecision")
        decision_layout = QHBoxLayout(decision)
        decision_layout.setContentsMargins(14, 11, 14, 11)
        decision_layout.setSpacing(12)
        decision_layout.addWidget(self._article_label(
            "+", "MedicalDecisionIcon", False
        ))
        decision_text = QVBoxLayout()
        decision_text.setSpacing(3)
        decision_text.addWidget(self._article_label(
            "메디컬팀 권고", "MedicalDecisionTitle"
        ))
        decision_text.addWidget(self._article_label(
            (
                f"{player}은 정상 훈련과 경기 출전이 가능합니다."
                if recovered else
                f"{return_date_text} 전후 재검 전까지 무리한 훈련과 경기 출전을 제한하십시오."
            ),
            "MedicalDecisionBody",
        ))
        decision_layout.addLayout(decision_text, 1)
        chart_layout.addWidget(decision)

        self.news_visual_layout.addWidget(chart)
        impact_text = (
            f"{player}의 복귀로 {team}은 정상적인 선수단 운영이 가능해졌습니다."
            if recovered else
            f"{player}의 이탈 기간 동안 {team}은 동일 포지션의 대체 자원을 검토해야 합니다."
        )
        self.news_visual_layout.addWidget(self._article_label(
            f"전력 영향  |  {impact_text}\n팬 반응  |  {fan_reaction}",
            "MedicalFanReaction",
        ))
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("부상 선수", player),
            ("진단", diagnosis),
            ("예상 결장", "복귀 완료" if recovered else f"{days or '-'}일"),
            ("현재 조치", return_status),
        )

    def _render_meeting_context(self, message):
        self._prepare_visual_only("meeting")
        payload = self._payload_for(message)
        player = payload.get("player_name") or (
            str(message.get("headline") or "").split(",")[0]
        )
        morale = int(payload.get("morale") or 50)
        squad = payload.get("squad") or "-"
        player_record = self._player_record(
            payload.get("player_id"), player, payload.get("team") or self.team_name
        )
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        meeting = QHBoxLayout()
        meeting.setSpacing(14)
        meeting.addWidget(
            self._player_portrait(
                player_record, player,
                f"{player_record.get('pos') or '-'} · {squad} · 사기 {morale}",
            ), 3
        )
        letter = QFrame()
        letter.setObjectName("MeetingLetter")
        letter_layout = QVBoxLayout(letter)
        letter_layout.setContentsMargins(22, 18, 22, 18)
        letter_layout.setSpacing(9)
        letter_layout.addWidget(self._article_label("PRIVATE · 면담 요청", "MeetingStamp"))
        letter_layout.addWidget(self._article_label(
            f"감독님, 잠시 이야기할 수 있을까요?", "MeetingHeadline"
        ))
        letter_layout.addWidget(self._article_label(
            message.get("body") or "최근 제 기용 계획과 팀에서 맡게 될 역할을 직접 듣고 싶어 면담을 요청했습니다.",
            "MeetingBody",
        ))
        quote = self._article_label(
            f'“팀에 도움이 되고 싶습니다. 다만 앞으로 어떤 역할을 준비해야 하는지 솔직한 설명을 듣고 싶습니다.”\n\n— {player}',
            "MeetingQuote",
        )
        letter_layout.addWidget(quote)
        letter_layout.addStretch()
        letter_layout.addWidget(self._article_label(
            "면담 의제  ·  출전 기회 / 선수단 내 역할 / 향후 기용 계획",
            "MeetingAgenda",
        ))
        meeting.addWidget(letter, 7)
        self.news_visual_layout.addLayout(meeting)
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
        team = payload.get("team") or self.team_name or "구단"
        promote_player = self._player_record(payload.get("promote_id"), promote, team)
        demote_player = self._player_record(payload.get("demote_id"), demote, team)
        try:
            month = date.fromisoformat(self._message_date_key(message)).month
        except ValueError:
            month = 11
        reason = self._month_roster_reason(month)
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(self._article_label("KBO ROSTER NEWS", "NewsMasthead"))
        self.news_visual_layout.addWidget(self._article_label(
            f"{self.manager_name} 감독, {team} {promote} 1군 콜업 예정",
            "ArticleHeadline",
        ))
        self.news_visual_layout.addWidget(self._article_label(
            f"{self._message_date_key(message).replace('-', '.')}  |  {team} 담당 기자",
            "ArticleByline",
        ))
        self.news_visual_layout.addWidget(self._article_label(
            f"{team}은 {reason} {promote}의 1군 등록을 검토하고 있다. "
            f"구단 관계자는 ‘현장 평가와 선수의 최근 컨디션을 함께 살폈다’고 전했다.",
            "ArticleLead",
        ))
        movement = QHBoxLayout()
        movement.addWidget(self._player_portrait(
            demote_player, demote,
            f"1군 말소 후보 · {demote_player.get('pos') or '-'}",
        ), 4)
        arrow = QLabel("→")
        arrow.setObjectName("TradeArrow")
        movement.addWidget(arrow)
        movement.addWidget(self._player_portrait(
            promote_player, promote,
            f"1군 콜업 후보 · {promote_player.get('pos') or '-'}",
        ), 4)
        self.news_visual_layout.addLayout(movement)
        self.news_visual_layout.addWidget(self._article_label(
            message.get("body") or f"엔트리 변경안은 최종 컨디션 점검 후 확정될 예정이다.",
            "ArticleQuote",
        ))
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("업무", "엔트리 제출"),
            ("등록", promote),
            ("말소", demote),
            ("마감 상태", "결정 필요"),
        )

    def _render_board_context(self, message):
        self._prepare_visual_only("board")
        team = self.team_name or "구단"
        team_info = TEAM_INFO.get(team, {})
        try:
            profile = governance_profile_for(team)
        except (KeyError, OSError, ValueError):
            profile = {
                "general_manager": {
                    "name": team_info.get("general_manager", "단장"),
                    "style": "선수단 구성과 구단 운영의 균형을 중시합니다.",
                },
                "ownership": {
                    "name": team_info.get("parent_company", team),
                    "style": "구단의 장기적인 경쟁력과 안정적인 운영을 중시합니다.",
                },
                "board_policy": {
                    "competitive_window": "balanced",
                    "preferred_levels": {},
                    "rationale": "현재 전력과 미래 경쟁력을 함께 고려합니다.",
                },
            }
        general_manager = profile["general_manager"]
        ownership = profile["ownership"]
        policy = profile.get("board_policy", {})
        resolved = bool(message.get("resolved"))
        status_text = "협의 완료" if resolved else "감독 응답 대기"
        status_note = (
            "합의된 목표는 시즌 평가에 반영됩니다."
            if resolved
            else "다섯 가지 안건을 검토하고 구단과 목표 수준을 조율하십시오."
        )
        self._clear_news_visual()
        self.news_visual.setVisible(True)

        hero = QFrame()
        hero.setObjectName("BoardroomHero")
        hero.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 15, 18, 15)
        hero_layout.setSpacing(16)
        logo = QLabel()
        logo.setObjectName("BoardroomLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(78, 78)
        logo_pixmap = QPixmap(str(team_logo_path(team)))
        if not logo_pixmap.isNull():
            logo.setPixmap(
                logo_pixmap.scaled(
                    66, 66,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo.setText(team[:1])
        hero_layout.addWidget(logo)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(3)
        hero_copy.addWidget(self._article_label(
            f"{team.upper()}  ·  BOARDROOM",
            "BoardroomEyebrow",
        ))
        hero_copy.addWidget(self._article_label(
            message.get("headline") or "구단 비전과 시즌 목표 협의",
            "BoardroomTitle",
        ))
        hero_copy.addWidget(self._article_label(
            "감독님의 운영 구상과 이사회의 기대를 조율하는 취임 협의입니다. "
            "각 안건은 시즌 중 평가와 향후 지원 결정에 반영됩니다.",
            "BoardroomDeck",
        ))
        hero_layout.addLayout(hero_copy, 1)
        status = QFrame()
        status.setObjectName("BoardroomStatus")
        status.setProperty("resolved", "true" if resolved else "false")
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(14, 11, 14, 11)
        status_layout.setSpacing(4)
        status_layout.addWidget(self._article_label(
            "MEETING STATUS", "BoardroomStatusLabel"
        ))
        status_layout.addWidget(self._article_label(
            status_text, "BoardroomStatusValue"
        ))
        status_layout.addWidget(self._article_label(
            "5개 핵심 안건", "BoardroomStatusNote"
        ))
        hero_layout.addWidget(status)
        self.news_visual_layout.addWidget(hero)

        main = QGridLayout()
        main.setHorizontalSpacing(10)
        main.setVerticalSpacing(10)
        agenda = QFrame()
        agenda.setObjectName("BoardAgendaPanel")
        agenda.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        agenda_layout = QVBoxLayout(agenda)
        agenda_layout.setContentsMargins(14, 13, 14, 14)
        agenda_layout.setSpacing(7)
        agenda_layout.addWidget(self._article_label(
            "이번 회의의 핵심 안건", "BoardSectionTitle"
        ))
        agenda_layout.addWidget(self._article_label(
            "이사회 제안은 확정 명령이 아닙니다. 감독은 각 목표를 1~5단계로 조정해 의견을 전달할 수 있습니다.",
            "BoardSectionGuide",
        ))
        objectives = (
            ("season_result", "이번 시즌 성과", team_info.get("season_goal", "이번 시즌 경쟁 목표를 합의합니다."), "이번 시즌"),
            ("long_term_vision", "구단의 장기 비전", team_info.get("long_term_goal", "중장기 선수단 구축 방향을 합의합니다."), "3시즌"),
            ("front_office_style", "프런트 운영 철학", team_info.get("front_office_style", general_manager.get("style", "프런트와 현장의 운영 원칙을 합의합니다.")), "상시"),
            ("club_identity", "팬들이 기대하는 정체성", team_info.get("fan_style", "구단과 팬이 기대하는 경기 철학을 확인합니다."), "상시"),
            ("roster_balance", "현재 전력과 내부 성장의 균형", "즉시 전력과 젊은 선수의 성장 기회를 함께 관리합니다.", "2시즌"),
        )
        preferred = policy.get("preferred_levels", {})
        for key, title, description, period in objectives:
            level = max(1, min(5, int(preferred.get(key, 3))))
            agenda_layout.addWidget(
                self._board_agenda_row(
                    title,
                    description,
                    period,
                    LEVELS[level]["label"],
                    key == "season_result",
                )
            )
        main.addWidget(agenda, 0, 0, 2, 1)

        members = self._board_information_card(
            "BOARD & FRONT OFFICE",
            ownership.get("name", team_info.get("parent_company", team)),
            ownership.get("style", "구단의 지속 가능한 경쟁력을 중시합니다."),
            f"담당 단장  ·  {general_manager.get('name', team_info.get('general_manager', '단장'))}",
            general_manager.get("style", "선수단 운영과 현장 지원을 총괄합니다."),
        )
        main.addWidget(members, 0, 1)
        philosophy = self._board_information_card(
            "CLUB DIRECTION",
            "구단이 원하는 방향",
            policy.get("rationale", "현재 전력과 장기 성장을 함께 고려합니다."),
            "감독에게 바라는 답변",
            "수용 여부만 고르는 것이 아니라 실행 가능한 수준과 운영 계획을 제안해 주십시오.",
        )
        main.addWidget(philosophy, 1, 1)
        main.setColumnStretch(0, 7)
        main.setColumnStretch(1, 3)
        self.news_visual_layout.addLayout(main)

        callout = QFrame()
        callout.setObjectName("BoardroomCallout")
        callout_layout = QHBoxLayout(callout)
        callout_layout.setContentsMargins(14, 10, 14, 10)
        callout_layout.setSpacing(12)
        callout_layout.addWidget(self._article_label("NEXT", "BoardCalloutBadge"))
        callout_copy = QVBoxLayout()
        callout_copy.setSpacing(1)
        callout_copy.addWidget(self._article_label(status_text, "BoardCalloutTitle"))
        callout_copy.addWidget(self._article_label(status_note, "BoardCalloutText"))
        callout_layout.addLayout(callout_copy, 1)
        self.news_visual_layout.addWidget(callout)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("회의", "취임 이사회"),
            ("안건", "핵심 목표 5개"),
            ("협의 방식", "목표별 1~5단계"),
            ("현재 상태", status_text),
        )

    @staticmethod
    def _board_agenda_row(title, description, period, proposal, required=False):
        row = QFrame()
        row.setObjectName("BoardAgendaRow")
        row.setProperty("required", "true" if required else "false")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(11)
        marker = QLabel("!" if required else "•")
        marker.setObjectName("BoardAgendaMarker")
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedSize(28, 28)
        layout.addWidget(marker)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("BoardAgendaTitle")
        heading.setWordWrap(True)
        copy.addWidget(heading)
        detail = QLabel(description)
        detail.setObjectName("BoardAgendaDescription")
        detail.setWordWrap(True)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        terms = QVBoxLayout()
        terms.setSpacing(3)
        term = QLabel(proposal)
        term.setObjectName("BoardAgendaProposal")
        term.setAlignment(Qt.AlignmentFlag.AlignCenter)
        terms.addWidget(term)
        span = QLabel(period)
        span.setObjectName("BoardAgendaPeriod")
        span.setAlignment(Qt.AlignmentFlag.AlignCenter)
        terms.addWidget(span)
        layout.addLayout(terms)
        return row

    @staticmethod
    def _board_information_card(kicker, title, body, subhead, subbody):
        card = QFrame()
        card.setObjectName("BoardInformationCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(6)
        kicker_label = QLabel(kicker)
        kicker_label.setObjectName("BoardInfoKicker")
        layout.addWidget(kicker_label)
        title_label = QLabel(title)
        title_label.setObjectName("BoardInfoTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        body_label = QLabel(body)
        body_label.setObjectName("BoardInfoBody")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)
        divider = QFrame()
        divider.setObjectName("BoardInfoDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        subhead_label = QLabel(subhead)
        subhead_label.setObjectName("BoardInfoSubhead")
        subhead_label.setWordWrap(True)
        layout.addWidget(subhead_label)
        subbody_label = QLabel(subbody)
        subbody_label.setObjectName("BoardInfoBody")
        subbody_label.setWordWrap(True)
        layout.addWidget(subbody_label)
        layout.addStretch()
        return card

    def _render_schedule_context(self, message):
        self._prepare_visual_only("schedule")
        payload = self._payload_for(message)
        schedule_event = dict(payload.get("schedule_event") or {})
        if schedule_event.get("event_id") == "roster_audit":
            self._render_roster_audit_context(message)
            return
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

    def _render_fa_approved_context(self, message):
        """KBO FA 승인 공시에 전체 명단과 핵심 선수를 함께 표시한다."""
        self._prepare_visual_only("fa")
        players_by_key = {}
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            for team, name in FA_APPROVED_2025:
                row = connection.execute(
                    "SELECT * FROM players WHERE team=? AND name=? LIMIT 1",
                    (team, name),
                ).fetchone()
                if row:
                    players_by_key[(team, name)] = dict(row)
        except sqlite3.Error:
            pass
        finally:
            if "connection" in locals():
                connection.close()

        rows = []
        for team, name in sorted(FA_APPROVED_2025):
            player = players_by_key.get((team, name), {})
            rating = float(overall_rating(player)) if player else 0.0
            rows.append((team, name, player, rating))
        major_names = {
            (team, name) for team, name, _player, _rating in
            sorted(rows, key=lambda item: item[3], reverse=True)[:7]
        }

        self._clear_news_visual()
        self.news_visual.setVisible(True)
        title = QLabel("2026 FA 승인 선수 21명 · 전체 공시 명단")
        title.setObjectName("VisualTitle")
        self.news_visual_layout.addWidget(title)
        summary = QLabel(
            "KBO가 승인한 FA 선수 전원을 구단별로 표시합니다. "
            "★는 선수 DB 종합 평가 기준으로 분류한 주요 영입 대상입니다."
        )
        summary.setObjectName("VisualSummary")
        summary.setWordWrap(True)
        self.news_visual_layout.addWidget(summary)

        table = QTableWidget(len(rows), 7)
        table.setObjectName("RosterAuditPreview")
        table.setHorizontalHeaderLabels(
            ("주요", "원소속팀", "선수", "포지션", "나이", "종합", "연봉")
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(29)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.setMinimumHeight(min(680, 34 + len(rows) * 29))
        for row_index, (team, name, player, rating) in enumerate(rows):
            is_major = (team, name) in major_names
            values = (
                "★" if is_major else "",
                team,
                name,
                player.get("position") or player.get("pos") or "-",
                player.get("age") or "-",
                f"{rating:.1f}" if player else "-",
                f"{int(player.get('salary') or 0):,}" if player else "-",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (0, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_major:
                    item.setForeground(QColor("#ffd166"))
                table.setItem(row_index, column, item)
        self.news_visual_layout.addWidget(table)
        self._set_context_metrics(
            ("공시일", self._message_date_key(message).replace("-", ".")),
            ("승인 선수", f"{len(rows)}명"),
            ("주요 선수", f"{len(major_names)}명"),
            ("업무", "후보군 검토"),
        )

    def _render_roster_audit_context(self, message):
        """11월 3일 계약·보류 1차 검토를 실제 선수 데이터로 안내한다."""
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM players WHERE team=? ORDER BY status DESC, name",
                (self.team_name,),
            ).fetchall()
            players = [dict(row) for row in rows]
        except sqlite3.Error:
            players = []
        finally:
            if "connection" in locals():
                connection.close()

        reviews = []
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
            recommendation = (
                "방출 후보"
                if expires and rating < 10.5
                and int(player.get("age") or 0) >= 29 else
                "우선 재계약"
                if expires and (fa_attention or rating >= 14) else
                "육성 유지"
                if int(player.get("age") or 0) <= 25 and rating < 12.5 else
                "계약 재검토"
                if expires else "계약 유지"
            )
            reviews.append({
                **player,
                "report": report,
                "rating": rating,
                "contract_end": contract_end,
                "expires": expires,
                "fa_attention": fa_attention,
                "recommendation": recommendation,
            })
        reviews.sort(key=lambda item: (
            not item["expires"], not item["fa_attention"],
            item["recommendation"] != "방출 후보", -item["rating"],
        ))
        expires_count = sum(item["expires"] for item in reviews)
        fa_count = sum(item["fa_attention"] for item in reviews)
        release_count = sum(
            item["recommendation"] == "방출 후보" for item in reviews
        )

        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self.news_visual_layout.addWidget(self._visual_hero(
            "ROSTER & CONTRACT REVIEW · 1차 검토",
            "보류선수·계약 현황을 직접 분류하십시오",
            "단순 공지가 아닙니다. 선수별 계약과 FA 상태를 확인한 뒤 "
            "보류·재계약·육성·방출 후보 방침을 제출해야 합니다.",
        ))
        summary_cards = (
            self._visual_tile("전체 선수단", f"{len(reviews)}명", "등록 선수 기준"),
            self._visual_tile("계약 만료 검토", f"{expires_count}명", "2025시즌 종료 기준"),
            self._visual_tile("FA 주의 대상", f"{fa_count}명", "자격 충족 또는 1시즌 이내"),
            self._visual_tile("프런트 방출 검토", f"{release_count}명", "감독 최종 판단 필요"),
        )
        self.news_visual_layout.addWidget(AdaptiveGrid(
            summary_cards, max_columns=4, medium_width=570,
            wide_width=980, spacing=8,
        ))

        instruction = QFrame()
        instruction.setObjectName("RosterAuditCallout")
        instruction_layout = QHBoxLayout(instruction)
        instruction_layout.setContentsMargins(14, 10, 14, 10)
        instruction_layout.addWidget(self._article_label(
            "감독 업무", "RosterAuditCalloutLabel", False
        ))
        instruction_layout.addWidget(self._article_label(
            "아래 ‘업무 내용 보기’를 눌러 선수별 방침을 선택하고 1차 분류안을 저장하십시오. "
            "실제 방출은 11월 25일 최종 검토 전까지 발생하지 않습니다.",
            "RosterAuditCalloutText",
        ), 1)
        self.news_visual_layout.addWidget(instruction)

        table = QTableWidget(min(10, len(reviews)), 7)
        table.setObjectName("RosterAuditPreview")
        table.setHorizontalHeaderLabels((
            "선수", "포지션", "능력", "연봉", "계약 만료", "FA 현황", "프런트 의견",
        ))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setShowGrid(False)
        table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        vertical_header = table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical_header.setDefaultSectionSize(39)
        vertical_header.setMinimumSectionSize(39)
        for row, player in enumerate(reviews[:10]):
            report = player["report"]
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
                f"{player['rating']:.1f}",
                f"{int(player.get('salary') or 0):,}만원",
                player["contract_end"],
                fa_label,
                player["recommendation"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignVCenter)
                    | int(
                        Qt.AlignmentFlag.AlignLeft
                        if column in (0, 5, 6) else
                        Qt.AlignmentFlag.AlignCenter
                    )
                )
                if column == 0:
                    item.setForeground(QColor("#78c4ee"))
                elif column == 5:
                    item.setToolTip(fa_detail)
                    if player["fa_attention"]:
                        item.setForeground(QColor("#efc467"))
                elif column == 6:
                    tone = {
                        "방출 후보": "#ef7474",
                        "계약 재검토": "#e3b65d",
                        "육성 유지": "#70b9e6",
                        "우선 재계약": "#76c89b",
                        "계약 유지": "#9baab5",
                    }.get(player["recommendation"], "#d9e1e7")
                    item.setForeground(QColor(tone))
                table.setItem(row, column, item)
            table.setRowHeight(row, 39)
        header = table.horizontalHeader()
        header.setMinimumSectionSize(52)
        for column in (1, 2, 3, 4, 6):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((110, 68, 62, 100, 105, 170, 115)):
            header.resizeSection(column, width)
        table.setFixedHeight(39 * min(10, len(reviews)) + 39)
        self.news_visual_layout.addWidget(table)
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("검토 단계", "1차 분류"),
            ("검토 대상", f"{len(reviews)}명"),
            ("계약 만료", f"{expires_count}명"),
            ("업무", "감독 방침 제출"),
        )

    def _render_analysis_context(self, message):
        self._prepare_visual_only("analysis")
        self.operations_strip.setVisible(False)
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self._add_assistant_delivery_header(
            message,
            "DATA ANALYSIS BRIEFING",
            message.get("headline") or "전력 분석 보고서",
            "데이터 분석팀의 핵심 결과와 선수단 적용 범위를 전달드립니다.",
        )
        self.news_visual_layout.addWidget(
            self._visual_hero(
                "DATA & SCOUTING",
                message.get("headline") or "전력 분석 보고서",
                message.get("body") or "",
            )
        )
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
        self.news_visual_layout.addWidget(AdaptiveGrid(
            (scope, chart),
            max_columns=2,
            medium_width=760,
            column_weights=(4, 6),
            spacing=10,
        ))
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
            ("01", "스토브리그 평가", "1군·C팀 초기 분류"),
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
        if "[구단별 변동]" not in body:
            injuries = self._extract_number(body, r"신규 부상\s+(\d+)명")
            recoveries = self._extract_number(body, r"1군 복귀\s+(\d+)명")
            assignments = self._extract_number(body, r"보직\s+(\d+)건")
            roster_moves = self._extract_number(body, r"엔트리 이동\s+(\d+)건")
            ai_jobs = self._extract_number(body, r"AI 검토\s+(\d+)건")
            self._show_visual_context(
                "LEAGUE PROCESSING REPORT",
                message.get("headline") or "리그 하루 진행 결과",
                "이 기록은 변경 전 생성된 일일 리그 진행 보고서입니다.",
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
            return
        changed_count = self._extract_number(body, r"변동 구단\s+(\d+)개")
        unchanged_count = self._extract_number(body, r"변동 없음\s+(\d+)개")
        period_match = re.search(r"보고 기간:\s*([^\n]+)", body)
        period = period_match.group(1).strip() if period_match else "최근 7일"
        team_changes = {}
        for line in body.splitlines():
            match = re.match(r"[•·]\s*(.+?):\s*(.+)$", line.strip())
            if match and match.group(1) in TEAM_NAMES:
                team_changes[match.group(1)] = match.group(2).strip()

        self._clear_news_visual()
        self.news_visual.setVisible(True)
        self._add_assistant_delivery_header(
            message,
            "KBO WEEKLY OPERATIONS",
            message.get("headline") or "10개 구단 주간 진행 보고",
            f"{period} 동안 발생한 실제 선수단 변동만 정리했습니다.",
        )
        self.news_visual_layout.addWidget(self._visual_hero(
            "LEAGUE WEEKLY REPORT",
            "10개 구단 변동 현황",
            "엔트리 이동과 신규 부상, 부상자 수 및 보강 과제의 변화를 "
            "직전 상태와 비교합니다. 기록할 변화가 없으면 변동 없음으로 표시합니다.",
        ))

        cards = []
        for team in TEAM_NAMES:
            detail = team_changes.get(team, "변동 없음")
            changed = detail != "변동 없음"
            card = QFrame()
            card.setObjectName("WeeklyTeamStatus")
            card.setProperty("changed", changed)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(11, 9, 12, 9)
            card_layout.setSpacing(11)
            logo = QLabel()
            logo.setObjectName("WeeklyTeamLogo")
            logo.setFixedSize(58, 42)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(team_logo_path(team)))
            if not pixmap.isNull():
                logo.setPixmap(pixmap.scaled(
                    50,
                    34,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            card_layout.addWidget(logo)
            copy = QVBoxLayout()
            copy.setSpacing(3)
            name_label = QLabel(team)
            name_label.setObjectName("WeeklyTeamName")
            copy.addWidget(name_label)
            change_label = QLabel(detail)
            change_label.setObjectName("WeeklyTeamChange")
            change_label.setProperty("changed", changed)
            change_label.setWordWrap(True)
            copy.addWidget(change_label)
            card_layout.addLayout(copy, 1)
            cards.append(card)
        self.news_visual_layout.addWidget(AdaptiveGrid(
            cards,
            max_columns=2,
            medium_width=780,
            spacing=8,
        ))
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("처리 구단", "10개"),
            ("선수", f"{players}명"),
            ("변동 구단", f"{changed_count}개"),
            ("변동 없음", f"{unchanged_count}개"),
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

    def _render_press_conference_news(self, message):
        """취임 기자회견 기사를 의료·일반 리그 뉴스와 분리해 표시한다."""
        self._prepare_visual_only("club_news")
        self.headline_label.setVisible(False)
        self.body_label.setVisible(False)
        self.operations_strip.setVisible(False)
        self._clear_news_visual()
        self.news_visual.setVisible(True)

        headline = str(message.get("headline") or "취임 기자회견 결과")
        body = str(message.get("body") or "")
        date_key = self._message_date_key(message).replace("-", ".")
        intro = body.split("\n\n", 1)[0].strip()
        summary_match = re.search(r"\[현장 평가\]\s*(.+)$", body, re.S)
        summary = (
            summary_match.group(1).strip()
            if summary_match else
            "신임 감독의 운영 철학과 시즌 목표가 공식적으로 공개됐습니다."
        )
        transcript = re.findall(
            r"\[([^\]·]+)\s*·\s*([^\]]+)\s*기자\]\s*"
            r"Q\.\s*(.*?)\s*A\.\s*(.*?)"
            r"(?=\n\n\[|\Z)",
            body,
            re.S,
        )

        hero = QFrame()
        hero.setObjectName("LeagueArticle")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(18)
        copy = QVBoxLayout()
        copy.setSpacing(8)
        copy.addWidget(self._article_label(
            f"CLUB PRESS ROOM  ·  {date_key}  ·  구단 홍보팀",
            "LeagueArticleKicker",
        ))
        copy.addWidget(
            self._article_label(headline, "LeagueArticleHeadline")
        )
        copy.addWidget(self._article_label(
            intro or "신임 감독의 공식 취임 기자회견이 열렸습니다.",
            "LeagueArticleDeck",
        ))
        copy.addWidget(self._article_label(
            f"현장 평가  |  {summary}", "NewsSummary"
        ))
        copy.addStretch()
        hero_layout.addLayout(copy, 5)

        room = QLabel()
        room.setObjectName("PressConferenceNewsPhoto")
        room.setFixedSize(360, 200)
        room.setAlignment(Qt.AlignmentFlag.AlignCenter)
        room_pixmap = QPixmap(str(resource_path(
            "image", "Scenes", "press_conference_room.png"
        )))
        if not room_pixmap.isNull():
            room.setPixmap(room_pixmap.scaled(
                room.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        hero_layout.addWidget(room)
        self.news_visual_layout.addWidget(hero)

        section = QLabel("기자별 주요 질의와 감독 답변")
        section.setObjectName("ConditionSectionTitle")
        self.news_visual_layout.addWidget(section)
        cards = []
        for outlet, reporter, question, answer in transcript:
            cards.append(self._visual_tile(
                f"{outlet.strip()}  ·  {reporter.strip()} 기자",
                question.strip(),
                f"감독 답변  |  {answer.strip()}",
            ))
        if cards:
            self.news_visual_layout.addWidget(AdaptiveGrid(
                cards,
                max_columns=2,
                medium_width=820,
                spacing=9,
            ))
        else:
            self.news_visual_layout.addWidget(
                self._article_label(body, "ClubNoticeBody")
            )
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("일정", "취임 기자회견"),
            ("참석 매체", f"{len(transcript)}개"),
            ("감독", self.manager_name),
            ("상태", "공식 일정 완료"),
        )

    def _render_club_news_context(self, message):
        self._prepare_visual_only("club_news")
        category = message.get("category") or "구단 소식"
        date_key = self._message_date_key(message)
        try:
            news_date = date.fromisoformat(date_key)
        except ValueError:
            news_date = self.current_date or date(2025, 11, 1)
        phase_name, phase_detail = phase_for(news_date)
        headline_text = (
            message.get("headline") or f"{self.team_name} 공식 발표"
        )
        body_text = str(message.get("body") or "상세 내용이 없습니다.")
        self.headline_label.setVisible(False)
        self.body_label.setVisible(False)
        self.operations_strip.setVisible(False)
        self._clear_news_visual()
        self.news_visual.setVisible(True)
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("ClubNoticeLogo")
        logo.setFixedSize(96, 112)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap(str(team_logo_path(self.team_name)))
        if not logo_pixmap.isNull():
            logo.setPixmap(logo_pixmap.scaled(
                logo.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        header.addWidget(logo)
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addStretch()
        secretary = QLabel("구단 공식 공지  |  홍보팀")
        secretary.setObjectName("ClubSecretaryName")
        heading.addWidget(secretary)
        club_label = QLabel(
            f"{self.team_name or '구단'}  ·  {category}  ·  "
            f"{date_key.replace('-', '.')}"
        )
        club_label.setObjectName("ClubNoticeMeta")
        heading.addWidget(club_label)
        headline = QLabel(headline_text)
        headline.setObjectName("ClubNoticeHeadline")
        headline.setWordWrap(True)
        heading.addWidget(headline)
        heading.addStretch()
        header.addLayout(heading, 1)
        self.news_visual_layout.addLayout(header)

        rule = QFrame()
        rule.setObjectName("ClubNoticeRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        self.news_visual_layout.addWidget(rule)
        self.news_visual_layout.addWidget(
            self._article_label(body_text, "ClubNoticeLead")
        )
        self.news_visual_layout.addWidget(self._article_label(
            f"요약하면, 현재 구단은 {phase_name} 단계에 맞춰 {phase_detail} "
            f"관련 업무를 진행하고 있습니다. 이번 공지는 현장과 프런트가 "
            "공유해야 할 방향을 공식적으로 정리한 내용입니다.",
            "ClubNoticeBody",
        ))
        self.news_visual_layout.addWidget(self._article_label(
            f"{self.manager_name} 감독님께서는 선수단에 전달될 영향을 확인한 뒤 "
            "필요한 후속 결정을 내려주시면 됩니다. 구단 사무국은 관련 일정과 "
            "추가 보고가 확정되는 대로 바로 전달드리겠습니다.",
            "ClubNoticeBody",
        ))
        self.news_visual_layout.addWidget(self._article_label(
            f"{self.team_name or '구단'} 구성원들도 이번 방향을 공유하고 있으며, "
            "선수단 운영과 시즌 준비가 흔들리지 않도록 각 부서가 후속 업무를 "
            "이어갈 예정입니다.",
            "ClubNoticeBody",
        ))
        footer = self._article_label(
            f"구단 홍보팀  |  {date_key.replace('-', '.')}  |  "
            "추가 확인 사항은 수신함에 갱신됩니다.",
            "ClubNoticeFooter",
        )
        self.news_visual_layout.addWidget(footer)
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
        related_teams = mentioned or list(TEAM_NAMES)
        date_key = self._message_date_key(message)
        try:
            news_date = date.fromisoformat(date_key)
        except ValueError:
            news_date = self.current_date or date(2025, 11, 1)
        phase_name, phase_detail = phase_for(news_date)
        category = message.get("category") or "리그 소식"
        headline_text = message.get("headline") or "KBO 리그 소식"
        body_text = str(message.get("body") or "상세 내용이 없습니다.")
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", body_text)
            if sentence.strip()
        ]
        deck_text = sentences[0] if sentences else body_text
        article_sentences = sentences[1:]
        paragraphs = [
            " ".join(article_sentences[index:index + 2])
            for index in range(0, len(article_sentences), 2)
        ]
        if not paragraphs:
            paragraphs.append(
                f"현재 KBO는 {phase_name} 단계에 있다. {phase_detail}을 중심으로 "
                "각 구단 프런트와 현장이 다음 시즌 선수단 구성을 검토하고 있다."
            )
        if any(keyword in text for keyword in ("비시즌", "전력 정비", "시즌 준비")):
            paragraphs.append(
                "주요 검토 항목은 보류선수 정리와 계약 협상, 외국인 선수 구성, "
                "포지션별 뎁스 보강이다. 캠프 명단이 확정되기 전까지 구단별 "
                "전력 구상은 계속 달라질 수 있다."
            )
            key_points = (
                "선수 이동·계약 협상 시작",
                "외국인·FA 시장 동향 점검",
                "스프링캠프 경쟁 구도 준비",
            )
            impact_text = (
                "전력 정비 결과는 스프링캠프의 포지션 경쟁과 개막 엔트리 구성에 "
                "직접 연결된다. 특히 같은 포지션의 영입과 방출이 이어질 경우 "
                "기존 선수의 역할과 육성 계획도 함께 조정될 가능성이 크다."
            )
            outlook_text = (
                "구단별 보류선수 명단과 계약 협상 결과가 순차적으로 공개되면 "
                "전력 구도의 윤곽도 선명해질 전망이다. KBO 뉴스센터는 공식 발표와 "
                "선수 이동이 확인되는 대로 후속 소식을 전할 예정이다."
            )
        else:
            key_points = (
                headline_text[:24] + ("…" if len(headline_text) > 24 else ""),
                (
                    f"{mentioned[0]} 관련 소식"
                    if len(mentioned) == 1 else
                    f"관련 구단 {len(related_teams)}개"
                ),
                f"{phase_name} 후속 상황 점검",
            )
            impact_text = (
                f"이번 소식은 {phase_name} 단계의 선수단 운영과 구단별 의사결정에 "
                "영향을 줄 수 있다. 각 구단은 현재 전력과 예산, 포지션별 뎁스를 "
                "기준으로 대응 방향을 검토하게 된다."
            )
            outlook_text = (
                "후속 절차는 구단 공식 발표와 KBO 공시를 통해 구체화된다. "
                "선수 계약이나 엔트리 변화가 확정될 경우 관련 구단의 전력 평가와 "
                "시즌 준비 계획도 함께 갱신될 예정이다."
            )
        scope_text = (
            f"이번 기사는 {mentioned[0]}을(를) 중심으로 다룬다. "
            f"{mentioned[0]}은(는) 현재 {phase_name} 일정에 맞춰 후속 업무를 "
            "진행하며, 관련 결정은 공식 발표 이후 게임 데이터에 반영된다."
            if len(mentioned) == 1 else
            f"이번 소식은 KBO {len(related_teams)}개 구단에 걸친 리그 현안을 "
            f"다룬다. 구단별 대응 속도와 선택에 따라 {phase_name} 이후의 "
            "전력 구도에는 차이가 생길 수 있다."
        )
        self._prepare_visual_only("league_news")
        self.headline_label.setVisible(False)
        self.body_label.setVisible(False)
        self.operations_strip.setVisible(False)
        self._clear_news_visual()
        self.news_visual.setVisible(True)

        article = QFrame()
        article.setObjectName("LeagueArticle")
        article_layout = QVBoxLayout(article)
        article_layout.setContentsMargins(18, 14, 20, 18)
        article_layout.setSpacing(8)
        portrait = None
        if self._uses_assistant_portrait(message):
            portrait = self._assistant_portrait_card()
        story_heading_widget = QWidget()
        story_heading = QVBoxLayout(story_heading_widget)
        story_heading.setContentsMargins(0, 0, 0, 0)
        story_heading.setSpacing(8)
        story_heading.addWidget(self._article_label(
            f"{category}  ·  {date_key.replace('-', '.')}  ·  KBO 뉴스센터",
            "LeagueArticleKicker",
        ))
        story_heading.addWidget(
            self._article_label(headline_text, "LeagueArticleHeadline")
        )
        deck = self._article_label(deck_text, "LeagueArticleDeck")
        story_heading.addWidget(deck)
        briefing = self._article_label(
            "KBO 뉴스센터 요약  |  주요 내용과 후속 일정을 정리했습니다.",
            "NewsSummary",
        )
        story_heading.addWidget(briefing)
        story_heading.addStretch()
        if portrait is not None:
            article_layout.addWidget(AdaptiveGrid(
                (portrait, story_heading_widget),
                max_columns=2,
                medium_width=650,
                column_weights=(0, 1),
                spacing=16,
            ))
        else:
            article_layout.addWidget(story_heading_widget)
        rule = QFrame()
        rule.setObjectName("LeagueArticleRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        article_layout.addWidget(rule)
        for index, paragraph in enumerate(paragraphs):
            paragraph_label = self._article_label(
                paragraph, "LeagueArticleParagraph"
            )
            article_layout.addWidget(paragraph_label)
            if index == 0 and len(paragraphs) > 1:
                quote = self._article_label(
                    f"“{phase_name}의 핵심은 다음 시즌 전력 구상을 얼마나 "
                    "빠르게 구체화하느냐에 달려 있다.”",
                    "LeagueArticleQuote",
                )
                article_layout.addWidget(quote)
        for section_title, section_body in (
            ("기사 배경", scope_text),
            ("전력 구성에 미칠 영향", impact_text),
            ("향후 전망", outlook_text),
        ):
            article_layout.addWidget(
                self._article_label(section_title, "LeagueArticleSubhead")
            )
            article_layout.addWidget(
                self._article_label(section_body, "LeagueArticleParagraph")
            )
        closing = self._article_label(
            f"KBO 뉴스센터  |  {date_key.replace('-', '.')}  "
            f"{category} 후속 보도는 관련 구단의 공식 발표 이후 갱신됩니다.",
            "LeagueArticleClosing",
        )
        article_layout.addWidget(closing)
        sidebar_widget = QWidget()
        sidebar = QVBoxLayout(sidebar_widget)
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(8)
        graphic = QFrame()
        graphic.setObjectName("LeagueNewsGraphic")
        graphic_layout = QVBoxLayout(graphic)
        graphic_layout.setContentsMargins(13, 12, 13, 12)
        graphic_layout.addWidget(self._article_label(
            "KBO LEAGUE BRIEFING", "LeagueSideEyebrow"
        ))
        graphic_layout.addWidget(self._article_label(
            f"{news_date.year}  KBO", "LeagueGraphicTitle"
        ))
        graphic_layout.addWidget(self._article_label(
            phase_name, "LeagueGraphicPhase"
        ))
        logo_grid = QGridLayout()
        logo_grid.setSpacing(7)
        single_team = len(related_teams) == 1
        for index, team in enumerate(related_teams[:10]):
            logo = QLabel()
            logo.setObjectName("LeagueTeamLogo")
            logo.setFixedSize(
                190 if single_team else 58,
                105 if single_team else 42,
            )
            pixmap = QPixmap(str(team_logo_path(team)))
            if not pixmap.isNull():
                logo.setPixmap(pixmap.scaled(
                    logo.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            logo.setToolTip(team)
            logo_grid.addWidget(
                logo,
                index // (1 if single_team else 5),
                index % (1 if single_team else 5),
                Qt.AlignmentFlag.AlignCenter,
            )
        graphic_layout.addLayout(logo_grid)
        if single_team:
            team_name_label = self._article_label(
                related_teams[0], "LeagueGraphicTeamName"
            )
            team_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            graphic_layout.addWidget(team_name_label)
        sidebar.addWidget(graphic)

        records = QFrame()
        records.setObjectName("LeagueSideCard")
        records_layout = QVBoxLayout(records)
        records_layout.setContentsMargins(11, 9, 11, 10)
        records_layout.addWidget(
            self._article_label("리그 현황", "LeagueSideTitle")
        )
        rings = QHBoxLayout()
        rings.setSpacing(2)
        rings.addWidget(LeagueStatRing(
            len(related_teams), 10, "관련 구단",
            f"{len(related_teams)}/10",
        ))
        phase_index = {
            "전력 정비": 1,
            "계약과 편성": 2,
            "캠프 준비": 3,
            "1차 캠프": 4,
            "2차 캠프": 4,
        }.get(phase_name, 1)
        rings.addWidget(LeagueStatRing(
            phase_index, 4, "준비 단계", f"{phase_index}/4"
        ))
        rings.addWidget(LeagueStatRing(
            news_date.month, 12, "기준 월", f"{news_date.month}월"
        ))
        records_layout.addLayout(rings)
        sidebar.addWidget(records)

        points = QFrame()
        points.setObjectName("LeagueSideCard")
        points_layout = QVBoxLayout(points)
        points_layout.setContentsMargins(12, 10, 12, 11)
        points_layout.addWidget(
            self._article_label("기사 핵심", "LeagueSideTitle")
        )
        for number, point in enumerate(key_points, 1):
            row = QHBoxLayout()
            badge = QLabel(str(number))
            badge.setObjectName("LeaguePointBadge")
            badge.setFixedSize(22, 22)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(badge)
            row.addWidget(
                self._article_label(point, "LeaguePointText"), 1
            )
            points_layout.addLayout(row)
        sidebar.addWidget(points)

        note = QFrame()
        note.setObjectName("LeagueSideCard")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(12, 11, 12, 13)
        note_layout.setSpacing(8)
        note_layout.addWidget(
            self._article_label("취재 노트", "LeagueSideTitle")
        )
        for title, detail in (
            ("현재 단계", f"{phase_name} · {phase_detail}"),
            (
                "취재 범위",
                related_teams[0]
                if len(related_teams) == 1 else
                f"KBO {len(related_teams)}개 구단",
            ),
            ("전력 영향", impact_text),
            ("다음 확인", outlook_text),
        ):
            note_layout.addWidget(
                self._article_label(title, "LeagueNoteLabel")
            )
            note_layout.addWidget(
                self._article_label(detail, "LeagueNoteText")
            )
        note_layout.addStretch()
        sidebar.addWidget(note, 1)
        self.news_visual_layout.addWidget(AdaptiveGrid(
            (article, sidebar_widget),
            max_columns=2,
            medium_width=1060,
            column_weights=(7, 3),
            spacing=16,
        ))
        self.news_visual_layout.addStretch()
        self._set_context_metrics(
            ("채널", "KBO 뉴스센터"),
            ("관련 구단", f"{len(mentioned)}개" if mentioned else "리그 전체"),
            ("게시일", date_key.replace("-", ".")),
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

    def set_appointment_press_status(self, available=True, completed=False):
        """공식 선임 이후 취임 기자회견을 수신함 필수 업무로 표시한다."""
        self.appointment_press_available = bool(available)
        self.appointment_press_completed = bool(completed)
        self.refresh_notifications()

    def mark_appointment_press_completed(self):
        self.set_appointment_press_status(True, True)

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
                "선수단 관리": "선수단 운영팀",
                "부상": "메디컬 센터",
                "선수 불만": "선수단 관리팀",
                "선수 면담": "선수단 관리팀",
                "이사회": "구단 이사회",
                "엔트리": "수석코치",
                "트레이드": "단장실",
                "FA": "프런트",
                "전력 분석": "데이터 분석팀",
            }
            for event in self.save_database.list_manager_events(
                self.save_id, limit=40
            ):
                event_category = event["category"]
                event_sender = sender_names.get(
                    event_category, "구단 사무국"
                )
                if event.get("event_type") == "schedule" and (
                    event.get("headline") == "보류선수·계약 현황 1차 검토"
                ):
                    # 이전 세이브에서 경기 일정으로 저장된 항목도 새 분류로 보인다.
                    event_category = "선수단 관리"
                    event_sender = "선수단 운영팀"
                is_roster_audit = (
                    event.get("event_type") == "schedule"
                    and event.get("headline") == "보류선수·계약 현황 1차 검토"
                )
                dynamic.append({
                    "category": event_category,
                    "sender": event_sender,
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
                    "requires_action": bool(event["requires_action"])
                    or is_roster_audit,
                    "resolved": event["status"] == "resolved",
                })
            news_sender_names = {
                "의료 센터": "메디컬 센터",
                "전력 분석": "데이터 분석팀",
                "데이터 분석": "데이터 분석팀",
                "리그 시뮬레이션": "데이터 분석팀",
                "구단 공식 발표": "구단 홍보팀",
                "프런트 브리핑": "구단 사무국",
                "시즌 전망": "구단 홍보팀",
                "상대 구단": "스카우트팀",
            }
            for news in self.save_database.list_daily_news(self.save_id):
                if news["category"] == "경기 일정":
                    continue
                if (
                    news["category"] == "리그 시뮬레이션"
                    and "10개 구단 하루 진행 완료" in news["headline"]
                ):
                    continue
                if news["category"] in (
                    "선수 면담", "선수 불만", "트레이드"
                ):
                    continue
                if news["category"] == "의료 센터" and (
                    "발생 당시 소속은 2군," in news["body"] or "기존 2군 선수단" in news["body"]
                ):
                    continue
                dynamic.append({
                    "category": news["category"],
                    "sender": news_sender_names.get(
                        news["category"], "KBO 뉴스센터"
                    ),
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
        if self.appointment_press_available:
            static.insert(1, dict(
                APPOINTMENT_PRESS_ITEM,
                received_date=(
                    self.appointment_date.isoformat()
                    if self.appointment_date is not None
                    else "0000-00-00"
                ),
                is_board=False,
                is_appointment_press=True,
                is_read=(
                    self.appointment_press_completed
                    or APPOINTMENT_PRESS_ITEM["headline"]
                    in self._read_static_messages
                ),
                requires_action=True,
                resolved=self.appointment_press_completed,
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
        unread = sum(
            1 for message in self.messages
            if (
                message.get("news_id") is not None
                or message.get("event_id") is not None
            ) and not message.get("is_read")
        )
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
