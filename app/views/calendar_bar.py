"""메인 화면의 게임 날짜 표시 및 하루 진행 컨트롤."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
)


class CalendarBar(QFrame):
    next_day_requested = Signal()

    def __init__(self, game_date, colors, parent=None):
        super().__init__(parent)
        self.game_date = game_date
        self._pending_date = None
        self._animation = None
        self.setObjectName("CalendarBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 11, 24, 11)
        layout.setSpacing(14)

        section = QLabel("구단 일정")
        section.setStyleSheet(
            f"color: {colors['accent_light']}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(section)

        self.date_label = QLabel(self._date_text(game_date))
        self.date_label.setFont(QFont("Malgun Gothic", 16, QFont.Bold))
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.date_label)
        layout.addStretch()

        self.next_button = QPushButton("다음 날짜  →")
        self.next_button.setObjectName("NextDateButton")
        self.next_button.clicked.connect(self.next_day_requested.emit)
        layout.addWidget(self.next_button)

        self.setStyleSheet(f"""
            QFrame#CalendarBar {{
                background-color: {colors['card_bg']};
                border-bottom: 1px solid {colors['accent']};
            }}
            QLabel {{ color: {colors['text']}; font-family: 'Malgun Gothic'; }}
            QPushButton#NextDateButton {{
                color: white;
                background-color: {colors['accent']};
                border: 1px solid {colors['accent_light']};
                border-radius: 7px;
                padding: 9px 20px;
                font-family: 'Malgun Gothic';
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton#NextDateButton:hover {{ background-color: {colors['accent_light']}; }}
            QPushButton#NextDateButton:disabled {{ color: #94a3b8; background-color: #334155; border-color: #475569; }}
        """)

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
