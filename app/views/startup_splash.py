"""main.py 실행 직후 표시되는 게임 부팅 화면."""

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class StartupSplash(QWidget):
    def __init__(self):
        super().__init__()
        self._progress_animation = None
        self._fade_animation = None
        self._finished_callback = None
        self.setWindowTitle("KBO FM 2025")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(900, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("StartupCard")
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(54, 42, 54, 38)
        layout.setSpacing(0)

        top = QHBoxLayout()
        league = QLabel("KBO")
        league.setObjectName("LeagueMark")
        top.addWidget(league)
        top.addSpacing(10)
        edition = QLabel("2025 PRE-SEASON")
        edition.setObjectName("Edition")
        top.addWidget(edition)
        top.addStretch()
        build = QLabel("CAREER DATABASE  ·  2025.1")
        build.setObjectName("Build")
        top.addWidget(build)
        layout.addLayout(top)

        layout.addStretch(2)
        kicker = QLabel("KOREA BASEBALL MANAGEMENT")
        kicker.setObjectName("Kicker")
        layout.addWidget(kicker)

        title_row = QHBoxLayout()
        title_row.setSpacing(15)
        title = QLabel("KBO")
        title.setObjectName("GameTitle")
        title_row.addWidget(title)
        fm = QLabel("FM")
        fm.setObjectName("GameAccent")
        title_row.addWidget(fm)
        year = QLabel("2025")
        year.setObjectName("GameYear")
        title_row.addWidget(year)
        title_row.addStretch()
        layout.addLayout(title_row)

        subtitle = QLabel("한 구단의 선택이 리그 전체의 하루를 바꿉니다")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(subtitle)
        layout.addStretch(3)

        self.status_label = QLabel("게임 엔진을 시작하고 있습니다")
        self.status_label.setObjectName("StartupStatus")
        layout.addWidget(self.status_label)
        layout.addSpacing(9)

        self.progress = QProgressBar()
        self.progress.setObjectName("StartupProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(4)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)
        layout.addSpacing(12)

        footer = QHBoxLayout()
        self.percent_label = QLabel("04%")
        self.percent_label.setObjectName("Percent")
        footer.addWidget(self.percent_label)
        footer.addStretch()
        tip = QLabel("데이터를 준비하는 동안 창을 닫지 마십시오")
        tip.setObjectName("Tip")
        footer.addWidget(tip)
        layout.addLayout(footer)

        self.setStyleSheet("""
            QFrame#StartupCard {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #071019, stop:0.58 #0b1722, stop:1 #132333
                );
                border: 1px solid #405365;
                border-top: 4px solid #2d9cff;
                border-radius: 5px;
            }
            QLabel {
                color: #eef4f8;
                font-family: 'Malgun Gothic', 'Segoe UI';
            }
            QLabel#LeagueMark {
                color: white; background: #1679c8;
                padding: 5px 9px; font-size: 11px; font-weight: 900;
            }
            QLabel#Edition {
                color: #9baab7; font-size: 10px; font-weight: 800;
            }
            QLabel#Build, QLabel#Tip {
                color: #667685; font-size: 9px; font-weight: 700;
            }
            QLabel#Kicker {
                color: #5bb6ff; font-size: 12px; font-weight: 900;
            }
            QLabel#GameTitle {
                color: white; font-size: 64px; font-weight: 900;
            }
            QLabel#GameAccent {
                color: #46adff; font-size: 64px; font-weight: 900;
            }
            QLabel#GameYear {
                color: #718291; font-size: 29px; font-weight: 900;
                padding-top: 25px;
            }
            QLabel#Subtitle {
                color: #aab7c2; font-size: 14px; font-weight: 650;
            }
            QLabel#StartupStatus {
                color: #dce5ec; font-size: 11px; font-weight: 750;
            }
            QLabel#Percent {
                color: #57b5ff; font-size: 10px; font-weight: 900;
            }
            QProgressBar#StartupProgress {
                background: #27333e; border: none; border-radius: 3px;
            }
            QProgressBar#StartupProgress::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1477c9, stop:1 #5fc1ff
                );
                border-radius: 3px;
            }
        """)

    def show_centered(self):
        screen = self.screen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )
        self.show()
        self.raise_()

    def set_progress(self, value, message):
        value = max(self.progress.value(), min(100, int(value)))
        self.status_label.setText(str(message))
        self.percent_label.setText(f"{value:02d}%")
        if self._progress_animation is not None:
            self._progress_animation.stop()
        self._progress_animation = QPropertyAnimation(
            self.progress, b"value", self
        )
        self._progress_animation.setDuration(300)
        self._progress_animation.setStartValue(self.progress.value())
        self._progress_animation.setEndValue(value)
        self._progress_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )
        self._progress_animation.start()

    def finish(self, callback):
        self._finished_callback = callback
        self.set_progress(100, "준비 완료 · 시작 화면으로 이동합니다")
        QTimer.singleShot(260, self._fade_out)

    def show_error(self, message):
        self.status_label.setStyleSheet("color: #ff7d88;")
        self.status_label.setText(message)
        self.percent_label.setText("ERROR")

    def _fade_out(self):
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade_animation = QPropertyAnimation(
            effect, b"opacity", self
        )
        self._fade_animation.setDuration(360)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(
            QEasingCurve.Type.InOutCubic
        )
        self._fade_animation.finished.connect(self._finish_hidden)
        self._fade_animation.start()

    def _finish_hidden(self):
        self.hide()
        callback = self._finished_callback
        self._finished_callback = None
        if callback is not None:
            callback()
