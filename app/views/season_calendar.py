"""KBO 오프시즌을 한눈에 확인하는 월간 일정 페이지."""

import calendar
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config.season_schedule import (
    CALENDAR_END,
    CALENDAR_START,
    SEASON_EVENTS,
    phase_for,
)


class SeasonCalendarPage(QWidget):
    """2025년 11월부터 2026년 2월까지의 고정 월간 달력."""

    back_requested = Signal()

    def __init__(self, colors, game_date, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.game_date = game_date
        visible = min(max(game_date, CALENDAR_START), CALENDAR_END)
        self.visible_year = visible.year
        self.visible_month = visible.month
        self.selected_date = visible
        self.day_buttons = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(10)

        header = QHBoxLayout()
        self.back_button = QPushButton("←  수신함으로")
        self.back_button.setObjectName("CalendarBackButton")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)
        header.addSpacing(8)
        title_box = QVBoxLayout()
        title = QLabel("KBO 시즌 일정")
        title.setObjectName("CalendarTitle")
        title_box.addWidget(title)
        self.range_label = QLabel("2025.11.01 — 2026.02.28  ·  구단 운영 및 공식 KBO 일정")
        self.range_label.setObjectName("CalendarSubtitle")
        title_box.addWidget(self.range_label)
        header.addLayout(title_box)
        header.addStretch()

        self.today_button = QPushButton("게임 날짜")
        self.today_button.clicked.connect(self.go_to_game_date)
        header.addWidget(self.today_button)
        self.prev_button = QPushButton("‹")
        self.prev_button.setFixedWidth(42)
        self.prev_button.clicked.connect(lambda: self.change_month(-1))
        header.addWidget(self.prev_button)
        self.month_label = QLabel()
        self.month_label.setObjectName("MonthLabel")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setFixedWidth(150)
        header.addWidget(self.month_label)
        self.next_button = QPushButton("›")
        self.next_button.setFixedWidth(42)
        self.next_button.clicked.connect(lambda: self.change_month(1))
        header.addWidget(self.next_button)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(12)
        calendar_panel = QFrame()
        calendar_panel.setObjectName("CalendarPanel")
        calendar_layout = QVBoxLayout(calendar_panel)
        calendar_layout.setContentsMargins(10, 10, 10, 10)
        calendar_layout.setSpacing(5)

        weekday_row = QHBoxLayout()
        weekday_row.setSpacing(4)
        for index, weekday in enumerate(("월", "화", "수", "목", "금", "토", "일")):
            label = QLabel(weekday)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setProperty("weekend", index >= 5)
            weekday_row.addWidget(label, 1)
        calendar_layout.addLayout(weekday_row)

        self.month_grid = QGridLayout()
        self.month_grid.setContentsMargins(0, 0, 0, 0)
        self.month_grid.setHorizontalSpacing(4)
        self.month_grid.setVerticalSpacing(4)
        for row in range(6):
            self.month_grid.setRowStretch(row, 1)
        for column in range(7):
            self.month_grid.setColumnStretch(column, 1)
        calendar_layout.addLayout(self.month_grid, 1)
        body.addWidget(calendar_panel, 7)

        detail = QFrame()
        detail.setObjectName("CalendarDetail")
        detail.setMinimumWidth(285)
        detail.setMaximumWidth(390)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(18, 17, 18, 17)
        detail_layout.setSpacing(10)
        self.detail_date = QLabel()
        self.detail_date.setObjectName("DetailDate")
        detail_layout.addWidget(self.detail_date)
        self.detail_phase = QLabel()
        self.detail_phase.setObjectName("DetailPhase")
        detail_layout.addWidget(self.detail_phase)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("DetailLine")
        detail_layout.addWidget(line)
        self.detail_events = QVBoxLayout()
        self.detail_events.setSpacing(8)
        detail_layout.addLayout(self.detail_events)
        detail_layout.addStretch()
        self.detail_hint = QLabel("날짜를 선택하면 일정과\n감독 업무가 표시됩니다.")
        self.detail_hint.setWordWrap(True)
        self.detail_hint.setObjectName("DetailHint")
        detail_layout.addWidget(self.detail_hint)
        body.addWidget(detail, 3)
        root.addLayout(body, 1)

        self.setStyleSheet(self._style())
        self.refresh_month()

    def _style(self):
        accent = self.colors["accent"]
        accent_light = self.colors["accent_light"]
        return f"""
            SeasonCalendarPage {{ background: #11161c; }}
            QLabel {{ color: #e9eef4; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QLabel#CalendarTitle {{ font-size: 24px; font-weight: 800; }}
            QLabel#CalendarSubtitle {{ color: #8996a5; font-size: 12px; }}
            QLabel#MonthLabel {{ font-size: 20px; font-weight: 800; }}
            QPushButton {{ color: #e9eef4; background: #202831; border: 1px solid #3b4856; border-radius: 5px; padding: 7px 12px; font-weight: 700; }}
            QPushButton:hover {{ border: 1px solid {accent_light}; background: #28333e; }}
            QPushButton#CalendarBackButton {{ background: transparent; border: 1px solid #465462; padding: 9px 14px; }}
            QFrame#CalendarPanel, QFrame#CalendarDetail {{ background: #171d24; border: 1px solid #35414d; border-radius: 7px; }}
            QLabel[weekend="false"], QLabel[weekend="true"] {{ color: #8e9aa8; padding: 4px; font-weight: 700; }}
            QLabel[weekend="true"] {{ color: #d1a0a8; }}
            QPushButton[day="true"] {{ text-align: left; padding: 8px; color: #dfe6ed; background: #151b21; border: 1px solid #2d3944; border-radius: 4px; font-size: 12px; font-weight: 600; }}
            QPushButton[day="true"]:hover {{ background: #202a33; border: 1px solid {accent_light}; }}
            QPushButton[event="true"] {{ border-left: 4px solid {accent_light}; background: #1c242c; }}
            QPushButton[today="true"] {{ border: 2px solid {accent_light}; }}
            QPushButton[past="true"] {{ color: #66727e; background: #12171c; }}
            QPushButton[selected="true"] {{ background: {accent}; color: white; border: 2px solid {accent_light}; }}
            QLabel#DetailDate {{ font-size: 21px; font-weight: 800; }}
            QLabel#DetailPhase {{ color: {accent_light}; font-size: 13px; font-weight: 700; }}
            QFrame#DetailLine {{ color: #35414d; }}
            QLabel#EventCategory {{ color: {accent_light}; font-size: 11px; font-weight: 800; }}
            QLabel#EventTitle {{ color: white; font-size: 15px; font-weight: 800; }}
            QLabel#EventDetail {{ color: #b8c2cc; font-size: 12px; }}
            QLabel#EventTask {{ color: #e8edf2; background: #222b34; border-left: 3px solid {accent_light}; padding: 8px; font-size: 12px; }}
            QLabel#DetailHint {{ color: #778594; font-size: 12px; }}
        """

    def set_game_date(self, game_date):
        self.game_date = game_date
        if CALENDAR_START <= game_date <= CALENDAR_END:
            self.visible_year, self.visible_month = game_date.year, game_date.month
            self.selected_date = game_date
        self.refresh_month()

    def go_to_game_date(self):
        target = min(max(self.game_date, CALENDAR_START), CALENDAR_END)
        self.visible_year, self.visible_month = target.year, target.month
        self.selected_date = target
        self.refresh_month()

    def change_month(self, delta):
        serial = self.visible_year * 12 + self.visible_month - 1 + delta
        year, month_index = divmod(serial, 12)
        candidate = date(year, month_index + 1, 1)
        if not (date(2025, 11, 1) <= candidate <= date(2026, 2, 1)):
            return
        self.visible_year, self.visible_month = year, month_index + 1
        self.selected_date = candidate
        self.refresh_month()

    def refresh_month(self):
        while self.month_grid.count():
            item = self.month_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.day_buttons.clear()
        self.month_label.setText(f"{self.visible_year}년 {self.visible_month}월")
        self.prev_button.setEnabled((self.visible_year, self.visible_month) > (2025, 11))
        self.next_button.setEnabled((self.visible_year, self.visible_month) < (2026, 2))
        month_weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.visible_year, self.visible_month)
        while len(month_weeks) < 6:
            month_weeks.append([0] * 7)
        for row, week in enumerate(month_weeks[:6]):
            for column, day_number in enumerate(week):
                if not day_number:
                    blank = QFrame()
                    blank.setStyleSheet("background: #12171c; border: 1px solid #202a33; border-radius: 4px;")
                    self.month_grid.addWidget(blank, row, column)
                    continue
                day = date(self.visible_year, self.visible_month, day_number)
                events = SEASON_EVENTS.get(day, ())
                text = str(day_number)
                if events:
                    text += f"\n● {events[0]['title']}"
                    if len(events) > 1:
                        text += f"\n  +{len(events) - 1}개"
                button = QPushButton(text)
                button.setProperty("day", True)
                button.setProperty("event", bool(events))
                button.setProperty("today", day == self.game_date)
                button.setProperty("selected", day == self.selected_date)
                button.setProperty("past", day < self.game_date)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                button.clicked.connect(lambda _checked=False, selected=day: self.select_date(selected))
                self.month_grid.addWidget(button, row, column)
                self.day_buttons.append(button)
        self.refresh_detail()

    def select_date(self, selected):
        self.selected_date = selected
        self.refresh_month()

    def refresh_detail(self):
        weekdays = "월화수목금토일"
        selected = self.selected_date
        self.detail_date.setText(f"{selected.month}월 {selected.day}일 {weekdays[selected.weekday()]}요일")
        phase_name, phase_description = phase_for(selected)
        self.detail_phase.setText(f"{phase_name}  ·  {phase_description}")
        while self.detail_events.count():
            item = self.detail_events.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        events = SEASON_EVENTS.get(selected, ())
        if not events:
            empty = QLabel("등록된 주요 일정이 없습니다.\n선수단 상태를 점검하고 다음 일정을 준비하세요.")
            empty.setWordWrap(True)
            empty.setObjectName("EventDetail")
            self.detail_events.addWidget(empty)
            return
        for event in events:
            category = QLabel(event["category"])
            category.setObjectName("EventCategory")
            self.detail_events.addWidget(category)
            title = QLabel(event["title"])
            title.setWordWrap(True)
            title.setObjectName("EventTitle")
            self.detail_events.addWidget(title)
            detail = QLabel(event["detail"])
            detail.setWordWrap(True)
            detail.setObjectName("EventDetail")
            self.detail_events.addWidget(detail)
            task = QLabel(f"감독 업무  |  {event['task']}")
            task.setWordWrap(True)
            task.setObjectName("EventTask")
            self.detail_events.addWidget(task)
