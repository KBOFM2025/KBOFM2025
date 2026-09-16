"""FM처럼 상단에서 내려오는 날짜 진행 오버레이."""

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.config import TEAM_INFO


class DayAdvanceOverlay(QWidget):
    PANEL_HEIGHT = 350

    def __init__(self, colors, managed_team, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.managed_team = managed_team
        self._animation = None
        self._after_hidden = None
        self._pending_updates = []
        self._pending_completion = None
        self._progress_count = 0
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(70)
        self._update_timer.timeout.connect(self._consume_progress)
        self.setObjectName("DayAdvanceOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        self.panel = QFrame(self)
        self.panel.setObjectName("AdvancePanel")
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(22, 15, 22, 16)
        layout.setSpacing(8)

        heading = QHBoxLayout()
        title = QLabel("일정 진행")
        title.setObjectName("AdvanceTitle")
        heading.addWidget(title)
        heading.addStretch()
        self.day_badge = QLabel("NEXT DAY")
        self.day_badge.setObjectName("AdvanceBadge")
        heading.addWidget(self.day_badge)
        layout.addLayout(heading)

        self.date_label = QLabel()
        self.date_label.setObjectName("AdvanceDate")
        layout.addWidget(self.date_label)

        self.status_label = QLabel("10개 구단의 하루 일정을 불러오는 중입니다")
        self.status_label.setObjectName("AdvanceStatus")
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, max(1, len(TEAM_INFO) * 3))
        self.progress.setFixedHeight(5)
        layout.addWidget(self.progress)

        team_grid = QGridLayout()
        team_grid.setHorizontalSpacing(10)
        team_grid.setVerticalSpacing(5)
        self.team_labels = {}
        for index, team in enumerate(TEAM_INFO):
            label = QLabel()
            label.setObjectName("TeamProgress")
            label.setMinimumHeight(28)
            self.team_labels[team] = label
            team_grid.addWidget(label, index % 5, index // 5)
        layout.addLayout(team_grid)

        self.step_label = QLabel("선수 상태  ·  구단 운영  ·  뉴스 및 일정")
        self.step_label.setObjectName("AdvanceSteps")
        layout.addWidget(self.step_label)

        accent = colors["accent"]
        accent_light = colors["accent_light"]
        self.setStyleSheet(f"""
            QWidget#DayAdvanceOverlay {{
                background: rgba(3, 7, 12, 145);
            }}
            QFrame#AdvancePanel {{
                background: #111820;
                border: 1px solid #536170;
                border-top: 3px solid {accent_light};
                border-radius: 3px;
            }}
            QLabel {{
                color: #e8eef4;
                font-family: 'Malgun Gothic', 'Segoe UI';
            }}
            QLabel#AdvanceTitle {{
                color: #aebbc7; font-size: 13px; font-weight: 800;
            }}
            QLabel#AdvanceBadge {{
                color: {accent_light}; background: #1b2530;
                border: 1px solid {accent}; padding: 3px 8px;
                font-size: 13px; font-weight: 900;
            }}
            QLabel#AdvanceDate {{
                color: white; font-size: 21px; font-weight: 900;
            }}
            QLabel#AdvanceStatus {{
                color: #c1cbd4; font-size: 13px; font-weight: 700;
            }}
            QLabel#AdvanceSteps {{
                color: #71808d; font-size: 13px;
            }}
            QLabel#TeamProgress {{
                color: #7d8b98; background: #171f28;
                border: 1px solid #2b3742; border-radius: 4px;
                padding: 4px 8px; font-size: 13px; font-weight: 750;
            }}
            QProgressBar {{
                background: #27313b; border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {accent_light}; border-radius: 2px;
            }}
        """)

    def begin(self, current_date, target_date):
        self._update_timer.stop()
        self._pending_updates.clear()
        self._pending_completion = None
        self._progress_count = 0
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self.progress.setRange(0, max(1, len(TEAM_INFO) * 3))
        self.progress.setValue(0)
        self.status_label.setStyleSheet("")
        self.status_label.setText("10개 구단의 하루 일정을 불러오는 중입니다")
        self.date_label.setText(
            f"{self._date_text(current_date)}  →  {self._date_text(target_date)}"
        )
        self.day_badge.setText("NEXT DAY")
        for team in self.team_labels:
            self._set_team_status(team, "대기", "waiting")
        self._animate_panel(down=True)

    def update_progress(self, update):
        """작업 스레드의 진행 알림을 짧은 간격으로 재생한다."""
        if not self.isVisible() or not isinstance(update, dict):
            return
        if not update.get("team"):
            self.status_label.setText(
                str(update.get("status") or "리그 일정을 처리하고 있습니다.")
            )
            return
        self._pending_updates.append(dict(update))
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _consume_progress(self):
        if not self._pending_updates:
            self._update_timer.stop()
            if self._pending_completion is not None:
                target_date, after_hidden = self._pending_completion
                self._pending_completion = None
                self._show_complete(target_date, after_hidden)
            return
        update = self._pending_updates.pop(0)
        team = str(update.get("team") or "")
        status = str(update.get("status") or "처리 중")
        state = str(update.get("state") or "working")
        self._set_team_status(team, status, state)
        detail = str(update.get("detail") or "")
        label = self.team_labels.get(team)
        if label is not None:
            label.setToolTip(detail or status)
        self.status_label.setText(
            f"{team} · {detail or status}"
        )
        self._progress_count += 1
        self.progress.setValue(
            min(self.progress.maximum() - 1, self._progress_count)
        )

    def _set_team_status(self, team, status, state):
        label = self.team_labels.get(team)
        if label is None:
            return
        palette = {
            "waiting": ("#71808d", "#171f28", "#2b3742"),
            "roster": ("#8fc8ff", "#172536", "#315270"),
            "planning": ("#ffd27c", "#2c2518", "#635331"),
            "done": ("#83dfae", "#172a22", "#315e48"),
        }
        foreground, background, border = palette.get(
            state, ("#c2ccd5", "#1d2731", "#3b4b59")
        )
        marker = "◆" if team == self.managed_team else "●"
        suffix = "  내 구단" if team == self.managed_team else ""
        label.setText(f"{marker}  {team}{suffix}    {status}")
        label.setStyleSheet(
            f"color: {foreground}; background: {background}; "
            f"border: 1px solid {border}; border-radius: 4px; "
            "padding: 4px 8px; font-size: 13px; font-weight: 750;"
        )

    def complete(self, target_date, after_hidden=None):
        if self._pending_updates:
            self._pending_completion = (target_date, after_hidden)
            return
        self._show_complete(target_date, after_hidden)

    def _show_complete(self, target_date, after_hidden=None):
        self._after_hidden = after_hidden
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.day_badge.setText("READY")
        self.date_label.setText(self._date_text(target_date))
        self.status_label.setText("다음 날짜 준비가 완료됐습니다")
        QTimer.singleShot(320, lambda: self._animate_panel(down=False))

    def fail(self, message, after_hidden=None):
        self._update_timer.stop()
        self._pending_updates.clear()
        self._pending_completion = None
        self._after_hidden = after_hidden
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.day_badge.setText("ERROR")
        self.status_label.setStyleSheet("color: #ff8a94;")
        self.status_label.setText(message)
        QTimer.singleShot(500, lambda: self._animate_panel(down=False))

    def _animate_panel(self, down):
        width = min(980, max(640, self.width() - 100))
        x = (self.width() - width) // 2
        shown_y = max(42, int(self.height() * 0.075))
        hidden = QRect(x, -self.PANEL_HEIGHT - 8, width, self.PANEL_HEIGHT)
        shown = QRect(x, shown_y, width, self.PANEL_HEIGHT)
        self.panel.setGeometry(hidden if down else shown)
        self._animation = QPropertyAnimation(self.panel, b"geometry", self)
        self._animation.setDuration(300 if down else 240)
        self._animation.setStartValue(hidden if down else shown)
        self._animation.setEndValue(shown if down else hidden)
        self._animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
            if down else QEasingCurve.Type.InCubic
        )
        if not down:
            self._animation.finished.connect(self._hide_finished)
        self._animation.start()

    def _hide_finished(self):
        self.hide()
        callback = self._after_hidden
        self._after_hidden = None
        if callback is not None:
            callback()

    @staticmethod
    def _date_text(game_date):
        weekdays = "월화수목금토일"
        return (
            f"{game_date.year}.{game_date.month:02d}.{game_date.day:02d} "
            f"{weekdays[game_date.weekday()]}"
        )
