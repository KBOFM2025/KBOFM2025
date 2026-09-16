"""KBO 오프시즌을 한눈에 확인하는 월간 일정 페이지."""

import calendar
from datetime import date

from PySide6.QtCore import Qt, Signal, QSize, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QFrame,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from app.config.season_schedule import (
    CALENDAR_END,
    CALENDAR_START,
    SEASON_EVENTS,
    phase_for,
)
from app.services.practice_games import (
    PRACTICE_WINDOW_END,
    PRACTICE_WINDOW_START,
    PracticeGameError,
)
from app.views.practice_game import PracticeGameSetupDialog


class CalendarDayButton(QPushButton):
    """일정 제목 길이와 무관한 크기 힌트. 실제 칸 폭 안에서만 텍스트를 그린다."""

    def __init__(self, day_number, events):
        super().__init__()
        self.day_number = day_number
        self.events = events
        self.setAccessibleName(f"{day_number}일 · " + " · ".join(e["title"] for e in events))
        self.setToolTip("\n".join(e["title"] for e in events))
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(0, 0)

    def sizeHint(self):
        return QSize(100, 96)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setClipRect(self.rect().adjusted(5, 4, -5, -4))
        painter.setPen(QColor("#ffffff" if self.property("selected") else "#91a1b0" if self.property("past") else "#dfe6ed"))
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        line_height = metrics.height() + 3
        width = max(0, self.width() - 18)
        painter.drawText(QRect(9, 7, width, line_height), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(self.day_number))
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        available = max(0, (self.height() - 14) // line_height - 1)
        # At most two preview rows; every other event remains available in the detail panel.
        count = min(len(self.events), min(2, available))
        for index in range(count):
            more = len(self.events) - index
            text = f"+{more}개 일정" if index == count - 1 and more > 1 else self.events[index]["title"]
            text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
            painter.drawText(QRect(9, 7 + (index + 1) * line_height, width, line_height),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.end()


class SeasonCalendarPage(QWidget):
    """2025년 11월부터 2026년 2월까지의 고정 월간 달력."""

    back_requested = Signal()
    practice_game_requested = Signal(int)

    def __init__(
        self, colors, game_date, practice_game_service=None,
        managed_team="", parent=None,
    ):
        super().__init__(parent)
        self.colors = colors
        self.game_date = game_date
        self.practice_game_service = practice_game_service
        self.managed_team = managed_team
        visible = min(max(game_date, CALENDAR_START), CALENDAR_END)
        self.visible_year = visible.year
        self.visible_month = visible.month
        self.selected_date = visible
        self.day_buttons = []
        self._compact_mode = False

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
        self.title = QLabel("KBO 시즌 일정")
        self.title.setObjectName("CalendarTitle")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_box.addWidget(self.title)
        self.range_label = QLabel("2025.11.01 — 2026.02.28  ·  구단 운영 및 공식 KBO 일정")
        self.range_label.setObjectName("CalendarSubtitle")
        self.range_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_box.addWidget(self.range_label)
        header.addLayout(title_box, 1)

        self.practice_button = QPushButton("＋ 연습경기 계획")
        self.practice_button.setObjectName("PracticeGameButton")
        self.practice_button.setVisible(self.practice_game_service is not None)
        self.practice_button.clicked.connect(self.open_practice_game_setup)
        header.addWidget(self.practice_button)
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

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setObjectName("CalendarSplitter")
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(8)
        self.calendar_panel = QFrame()
        self.calendar_panel.setObjectName("CalendarPanel")
        calendar_layout = QVBoxLayout(self.calendar_panel)
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
        self.body_splitter.addWidget(self.calendar_panel)

        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("CalendarDetail")
        self.detail_panel.setMinimumWidth(245)
        detail_shell = QVBoxLayout(self.detail_panel)
        detail_shell.setContentsMargins(0, 0, 0, 0)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_content = QWidget(objectName="CalendarDetailContent")
        self.detail_scroll.setWidget(detail_content)
        detail_shell.addWidget(self.detail_scroll)
        detail_layout = QVBoxLayout(detail_content)
        detail_layout.setContentsMargins(18, 17, 18, 17)
        detail_layout.setSpacing(10)
        self.detail_date = QLabel()
        self.detail_date.setObjectName("DetailDate")
        detail_layout.addWidget(self.detail_date)
        self.detail_phase = QLabel()
        self.detail_phase.setObjectName("DetailPhase")
        self.detail_phase.setWordWrap(True)
        self.detail_phase.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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
        self.body_splitter.addWidget(self.detail_panel)
        self.body_splitter.setStretchFactor(0, 7)
        self.body_splitter.setStretchFactor(1, 3)
        self.body_splitter.setSizes((850, 330))
        root.addWidget(self.body_splitter, 1)

        self.setStyleSheet(self._style())
        self.refresh_month()

    def _style(self):
        accent = self.colors["accent"]
        accent_light = self.colors["accent_light"]
        return f"""
            SeasonCalendarPage {{ background: #11161c; }}
            QWidget#CalendarDetailContent, QScrollArea {{ background:#171d24; border:0; }}
            QLabel {{ color: #e9eef4; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QLabel#CalendarTitle {{ font-size: 24px; font-weight: 800; }}
            QLabel#CalendarSubtitle {{ color: #8996a5; font-size: 14px; }}
            QLabel#MonthLabel {{ font-size: 20px; font-weight: 800; }}
            QPushButton {{ color: #e9eef4; background: #202831; border: 1px solid #3b4856; border-radius: 5px; padding: 7px 12px; font-weight: 700; }}
            QPushButton:hover {{ border: 1px solid {accent_light}; background: #28333e; }}
            QPushButton#CalendarBackButton {{ background: transparent; border: 1px solid #465462; padding: 9px 14px; }}
            QPushButton#PracticeGameButton {{ color:#ecf7ff; background:#173044; border:1px solid #39779d; padding:9px 14px; }}
            QPushButton#PracticeGameButton:hover {{ background:#20445f; border-color:#64b5e5; }}
            QFrame#CalendarPanel, QFrame#CalendarDetail {{ background: #171d24; border: 1px solid #35414d; border-radius: 7px; }}
            QSplitter#CalendarSplitter::handle {{ background: #10151b; border-radius: 3px; }}
            QSplitter#CalendarSplitter::handle:hover {{ background: {accent}; }}
            QLabel[weekend="false"], QLabel[weekend="true"] {{ color: #8e9aa8; padding: 4px; font-weight: 700; }}
            QLabel[weekend="true"] {{ color: #d1a0a8; }}
            QPushButton[day="true"] {{ text-align: left; padding: 8px; color: #dfe6ed; background: #151b21; border: 1px solid #2d3944; border-radius: 4px; font-size: 14px; font-weight: 600; }}
            QPushButton[day="true"]:hover {{ background: #202a33; border: 1px solid {accent_light}; }}
            QPushButton[event="true"] {{ border-left: 4px solid {accent_light}; background: #1c242c; }}
            QPushButton[today="true"] {{ border: 2px solid {accent_light}; }}
            QPushButton[past="true"] {{ color: #66727e; background: #12171c; }}
            QPushButton[selected="true"] {{ background: {accent}; color: white; border: 2px solid {accent_light}; }}
            QLabel#DetailDate {{ font-size: 21px; font-weight: 800; }}
            QLabel#DetailPhase {{ color: {accent_light}; font-size: 15px; font-weight: 700; }}
            QFrame#DetailLine {{ color: #35414d; }}
            QLabel#EventCategory {{ color: {accent_light}; font-size: 13px; font-weight: 800; }}
            QLabel#EventTitle {{ color: white; font-size: 15px; font-weight: 800; }}
            QLabel#EventDetail {{ color: #b8c2cc; font-size: 14px; }}
            QLabel#EventTask {{ color: #e8edf2; background: #222b34; border-left: 3px solid {accent_light}; padding: 8px; font-size: 14px; }}
            QLabel#DetailHint {{ color: #778594; font-size: 14px; }}
            SeasonCalendarPage[compact="true"] QLabel#CalendarTitle {{ font-size: 19px; }}
            SeasonCalendarPage[compact="true"] QLabel#MonthLabel {{ font-size: 17px; }}
            SeasonCalendarPage[compact="true"] QPushButton[day="true"] {{ padding: 5px; font-size: 13px; }}
        """

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 980
        if compact == self._compact_mode:
            return
        self._compact_mode = compact
        self.setProperty("compact", compact)
        self.style().unpolish(self)
        self.style().polish(self)
        self.range_label.setVisible(not compact)
        self.today_button.setVisible(not compact)
        self.practice_button.setText("＋ 경기" if compact else "＋ 연습경기 계획")
        self.back_button.setText("←" if compact else "←  수신함으로")
        self.month_label.setFixedWidth(112 if compact else 150)
        self.month_grid.setHorizontalSpacing(4)
        self.month_grid.setVerticalSpacing(2 if compact else 4)
        self.body_splitter.setOrientation(
            Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal
        )
        self.detail_panel.setMinimumWidth(0 if compact else 245)
        self.detail_panel.setMinimumHeight(220 if compact else 0)
        self.body_splitter.setSizes((520, 260) if compact else (850, 330))
        self.refresh_month()

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
                    blank.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
                    blank.setStyleSheet("background: #12171c; border: 1px solid #202a33; border-radius: 4px;")
                    self.month_grid.addWidget(blank, row, column)
                    continue
                day = date(self.visible_year, self.visible_month, day_number)
                events = self._events_for_day(day)
                button = CalendarDayButton(day_number, events)
                button.setProperty("day", True)
                button.setProperty("event", bool(events))
                button.setProperty("today", day == self.game_date)
                button.setProperty("selected", day == self.selected_date)
                button.setProperty("past", day < self.game_date)
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
        self.detail_scroll.verticalScrollBar().setValue(0)
        while self.detail_events.count():
            item = self.detail_events.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        events = self._events_for_day(selected)
        if not events:
            empty = QLabel("등록된 주요 일정이 없습니다.\n선수단 상태를 점검하고 다음 일정을 준비하세요.")
            empty.setWordWrap(True)
            empty.setObjectName("EventDetail")
            self.detail_events.addWidget(empty)
            return
        for event in events:
            category = QLabel(event["category"])
            category.setWordWrap(True)
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
            if event.get("event_type") == "practice_game":
                open_match = QPushButton(
                    "경기 결과 보기"
                    if event.get("practice_game_status") == "completed"
                    else "진행 중인 경기 계속하기"
                    if event.get("practice_game_status") == "live"
                    else "라인업 설정 · 경기 시작"
                )
                open_match.setObjectName("PracticeGameButton")
                open_match.clicked.connect(
                    lambda _checked=False, game_id=event["practice_game_id"]:
                    self.practice_game_requested.emit(game_id)
                )
                self.detail_events.addWidget(open_match)
            if (
                event.get("event_type") == "practice_game"
                and event.get("practice_game_status") == "scheduled"
                and selected >= self.game_date
            ):
                cancel = QPushButton("연습경기 일정 취소")
                cancel.setObjectName("CancelPracticeButton")
                cancel.clicked.connect(
                    lambda _checked=False, game_id=event["practice_game_id"]:
                    self.cancel_practice_game(game_id)
                )
                self.detail_events.addWidget(cancel)
        for index in range(self.detail_events.count()):
            label = self.detail_events.itemAt(index).widget()
            if isinstance(label, QLabel):
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def _events_for_day(self, selected):
        events = list(SEASON_EVENTS.get(selected, ()))
        if self.practice_game_service is not None:
            events.extend(self.practice_game_service.calendar_events(selected))
        return tuple(events)

    def open_practice_game_setup(self):
        if self.practice_game_service is None:
            return
        selected = self.selected_date
        if not PRACTICE_WINDOW_START <= selected <= PRACTICE_WINDOW_END:
            selected = PRACTICE_WINDOW_START
        dialog = PracticeGameSetupDialog(
            self.colors,
            self.practice_game_service,
            self.game_date,
            selected,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        game = self.practice_game_service.list_games(
            PRACTICE_WINDOW_START, PRACTICE_WINDOW_END
        )
        created = next(
            (item for item in game if item["id"] == dialog.created_game_id), None
        )
        if created:
            selected = date.fromisoformat(created["game_date"])
            self.visible_year, self.visible_month = selected.year, selected.month
            self.selected_date = selected
        self.refresh_month()

    def cancel_practice_game(self, game_id):
        answer = QMessageBox.question(
            self,
            "연습경기 일정 취소",
            "선택한 연습경기 일정을 취소하시겠습니까?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.practice_game_service.cancel_game(
                game_id, current_date=self.game_date
            )
        except PracticeGameError as error:
            QMessageBox.warning(self, "연습경기 일정", str(error))
            return
        self.refresh_month()
