"""메인 화면의 게임 날짜 표시 및 하루 진행 컨트롤."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal, QStringListModel
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QCompleter,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class CalendarBar(QFrame):
    next_day_requested = Signal()
    search_selected = Signal(object)
    search_submitted = Signal(str)

    def __init__(self, game_date, colors, club_name="KBO 구단", parent=None):
        super().__init__(parent)
        self.game_date = game_date
        self._pending_date = None
        self._animation = None
        self.setObjectName("CalendarBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(9)

        brand = QLabel("KBO")
        brand.setObjectName("HeaderBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFixedSize(46, 32)
        layout.addWidget(brand)

        title_column = QVBoxLayout()
        title_column.setSpacing(0)
        section = QLabel("수신함")
        section.setObjectName("HeaderTitle")
        self.section_label = section
        title_column.addWidget(section)
        context = QLabel(f"{club_name}  ·  구단 운영 센터")
        context.setObjectName("HeaderContext")
        self.context_label = context
        title_column.addWidget(context)
        layout.addLayout(title_column)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("GlobalSearch")
        self.search_input.setPlaceholderText("구단 또는 선수 검색")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(360)
        self.search_input.setMaximumWidth(760)
        self.search_input.setFixedHeight(32)
        self._search_items = {}
        self._search_model = QStringListModel(self)
        self._search_completer = QCompleter(self._search_model, self)
        self._search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._search_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._search_completer.setMaxVisibleItems(12)
        self._search_completer.popup().setStyleSheet(
            f"QAbstractItemView {{ color: #e5edf5; background: #171c22; "
            f"border: 1px solid #4b5662; padding: 3px; font-size: 12px; "
            f"outline: 0; selection-color: white; "
            f"selection-background-color: {colors['accent']}; }}"
        )
        self._search_completer.activated[str].connect(self._activate_search_result)
        self.search_input.setCompleter(self._search_completer)
        self.search_input.returnPressed.connect(self._submit_search)
        layout.addWidget(self.search_input, 1)
        self.search_button = QPushButton("탐색")
        self.search_button.setObjectName("GlobalSearchButton")
        self.search_button.setFixedHeight(32)
        self.search_button.clicked.connect(
            lambda _checked=False: self._submit_search()
        )
        layout.addWidget(self.search_button)

        self.date_label = QLabel(self._date_text(game_date))
        self.date_label.setFont(QFont("Malgun Gothic", 12, QFont.Bold))
        self.date_label.setObjectName("HeaderDate")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.date_label)

        self.next_button = QPushButton("다음 날짜  →")
        self.next_button.setObjectName("NextDateButton")
        self.next_button.clicked.connect(self.next_day_requested.emit)
        layout.addWidget(self.next_button)

        self.setStyleSheet(f"""
            QFrame#CalendarBar {{
                background-color: #11161c;
                border-bottom: 2px solid {colors['accent']};
            }}
            QLabel {{ color: {colors['text']}; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QLabel#HeaderBrand {{ color: white; background-color: {colors['accent']}; border-radius: 1px; font-size: 14px; font-weight: 800; }}
            QLabel#HeaderTitle {{ color: white; font-size: 14px; font-weight: 700; }}
            QLabel#HeaderContext {{ color: #84909c; font-size: 10px; }}
            QLabel#HeaderDate {{ color: #e2e7ec; font-size: 12px; padding: 0 7px; }}
            QLineEdit#GlobalSearch {{
                color: #f8fafc; background-color: #0d1217;
                placeholder-text-color: #7f8b98;
                border: 1px solid #46515d; border-radius: 1px;
                padding: 0 10px; font-size: 12px;
            }}
            QLineEdit#GlobalSearch:hover {{ border-color: #6b7784; }}
            QLineEdit#GlobalSearch:focus {{
                background-color: #151b22;
                border: 1px solid {colors['accent_light']};
            }}
            QPushButton#GlobalSearchButton {{
                color: #e7ebef; background-color: #202832;
                border: 1px solid #4a5662; border-radius: 1px;
                padding: 0 14px; font-size: 12px; font-weight: 700;
            }}
            QPushButton#GlobalSearchButton:hover {{ background-color: {colors['accent']}; }}
            QPushButton#NextDateButton {{
                color: white;
                background-color: {colors['accent']};
                border: 1px solid {colors['accent_light']};
                border-radius: 1px;
                min-height: 32px;
                padding: 0 17px;
                font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton#NextDateButton:hover {{ background-color: {colors['accent_light']}; }}
            QPushButton#NextDateButton[progressBlocked="true"] {{
                color: white; background-color: #9f2734; border-color: #ef6672;
            }}
            QPushButton#NextDateButton[progressBlocked="true"]:hover {{ background-color: #bd3341; }}
            QPushButton#NextDateButton:disabled {{ color: #94a3b8; background-color: #334155; border-color: #475569; }}
        """)

    def set_section(self, title, context=None):
        """Keep the persistent header in sync with the active management area."""
        self.section_label.setText(title)
        if context is not None:
            self.context_label.setText(context)

    def set_progress_blocked(self, required_count):
        blocked = required_count > 0
        self.next_button.setProperty("progressBlocked", blocked)
        self.next_button.setText(
            f"필수 소식 확인  ({required_count})" if blocked else "다음 날짜  →"
        )
        self.next_button.setToolTip(
            "수신함의 필수 응답 항목을 처리해야 날짜를 진행할 수 있습니다."
            if blocked else "다음 날짜로 진행합니다."
        )
        self.next_button.style().unpolish(self.next_button)
        self.next_button.style().polish(self.next_button)

    def set_search_entries(self, clubs, players):
        """구단과 선수를 하나의 자동완성 드롭다운에 등록한다."""
        items = {}
        for club in clubs:
            label = f"구단  |  {club}"
            items[label] = {"type": "club", "club": club}
        for player in players:
            label = f"선수  |  {player.get('name', '-')}  ·  {player.get('team', '-')}"
            # 동명이인은 구분 가능한 내부 키를 유지한다.
            unique_label = label
            suffix = 2
            while unique_label in items:
                unique_label = f"{label}  ({suffix})"
                suffix += 1
            items[unique_label] = {"type": "player", "player": player}
        self._search_items = items
        self._search_model.setStringList(list(items))

    def _activate_search_result(self, label):
        result = self._search_items.get(label)
        if result:
            self.search_selected.emit(result)
            self.search_input.clear()

    def _submit_search(self):
        query = self.search_input.text().strip()
        self.search_submitted.emit(query)

    def set_game_date(self, game_date, animated=True):
        if not animated:
            self.game_date = game_date
            self.date_label.setText(self._date_text(game_date))
            return

        self._pending_date = game_date
        self.next_button.setEnabled(False)
        effect = QGraphicsOpacityEffect(self.date_label)
        self.date_label.setGraphicsEffect(effect)
        self._animation = QPropertyAnimation(effect, b"opacity", self)
        self._animation.setDuration(130)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.finished.connect(self._fade_in_date)
        self._animation.start()

    def _fade_in_date(self):
        self.date_label.setGraphicsEffect(None)
        self.game_date = self._pending_date
        self.date_label.setText(self._date_text(self.game_date))

        effect = QGraphicsOpacityEffect(self.date_label)
        self.date_label.setGraphicsEffect(effect)
        self._animation = QPropertyAnimation(effect, b"opacity", self)
        self._animation.setDuration(210)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._finish_transition)
        self._animation.start()

    def _finish_transition(self):
        self.date_label.setGraphicsEffect(None)
        self._pending_date = None
        self._animation = None
        self.next_button.setEnabled(True)

    @staticmethod
    def _date_text(game_date):
        weekdays = "월화수목금토일"
        return (
            f"{game_date.year}년 {game_date.month}월 {game_date.day}일 "
            f"({weekdays[game_date.weekday()]}요일)"
        )
