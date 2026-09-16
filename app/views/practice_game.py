"""연습경기 편성 대화상자."""

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
)

from app.services.practice_games import (
    LINEUP_POLICIES,
    PITCHING_PLANS,
    PRACTICE_PURPOSES,
    PRACTICE_WINDOW_END,
    PRACTICE_WINDOW_START,
    VENUE_TYPES,
    PracticeGameError,
)


class PracticeGameSetupDialog(QDialog):
    """상대·구장·운용 목적을 한 번에 정해 연습경기를 등록한다."""

    def __init__(self, colors, service, game_date, selected_date=None, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.service = service
        self.game_date = game_date
        self.created_game_id = None
        self.setWindowTitle("연습경기 계획")
        self.setModal(True)
        self.resize(820, 640)
        self.setMinimumSize(740, 590)
        self._build_ui(selected_date)
        self._update_summary()

    def _build_ui(self, selected_date):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(objectName="PracticeHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(32, 27, 32, 25)
        eyebrow = QLabel("DEBUG LAB  ·  MATCH PLANNING  ·  SPRING CAMP")
        eyebrow.setObjectName("PracticeEyebrow")
        header_layout.addWidget(eyebrow)
        title = QLabel("연습경기 편성")
        title.setObjectName("PracticeTitle")
        header_layout.addWidget(title)
        subtitle = QLabel(
            "정규시즌 성적과 분리된 평가 경기입니다. 상대와 운용 목적을 먼저 확정하세요."
        )
        subtitle.setObjectName("PracticeMuted")
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        body = QFrame(objectName="PracticeBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(32, 24, 32, 28)
        body_layout.setSpacing(18)

        editor = QGridLayout()
        editor.setHorizontalSpacing(18)
        editor.setVerticalSpacing(12)

        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("yyyy.MM.dd")
        minimum_day = max(PRACTICE_WINDOW_START, min(self.game_date, PRACTICE_WINDOW_END))
        self.date_edit.setMinimumDate(
            QDate(minimum_day.year, minimum_day.month, minimum_day.day)
        )
        self.date_edit.setMaximumDate(QDate(2026, 2, 28))
        initial = selected_date or PRACTICE_WINDOW_START
        if initial < PRACTICE_WINDOW_START or initial > PRACTICE_WINDOW_END:
            initial = PRACTICE_WINDOW_START
        if self.game_date <= PRACTICE_WINDOW_END:
            initial = max(initial, minimum_day)
        self.date_edit.setDate(QDate(initial.year, initial.month, initial.day))

        self.time_edit = QTimeEdit(QTime(13, 0))
        self.time_edit.setDisplayFormat("HH:mm")
        self.opponent_combo = QComboBox()
        self.opponent_combo.addItems(self.service.opponents)
        self.venue_combo = QComboBox()
        for key, label in VENUE_TYPES.items():
            self.venue_combo.addItem(label, key)
        self.innings_spin = QSpinBox()
        self.innings_spin.setRange(7, 9)
        self.innings_spin.setSingleStep(2)
        self.innings_spin.setValue(9)
        self.innings_spin.setSuffix("이닝")

        self.purpose_combo = QComboBox()
        self.purpose_combo.addItems(PRACTICE_PURPOSES)
        self.lineup_combo = QComboBox()
        self.lineup_combo.addItems(LINEUP_POLICIES)
        self.pitching_combo = QComboBox()
        self.pitching_combo.addItems(PITCHING_PLANS)

        fields = (
            (0, 0, "경기 날짜", self.date_edit),
            (0, 1, "시작 시각", self.time_edit),
            (1, 0, "상대 구단", self.opponent_combo),
            (1, 1, "경기장", self.venue_combo),
            (2, 0, "경기 이닝", self.innings_spin),
            (2, 1, "평가 목적", self.purpose_combo),
            (3, 0, "라인업 운용", self.lineup_combo),
            (3, 1, "투수 운용", self.pitching_combo),
        )
        for row, column, label_text, field in fields:
            box = QVBoxLayout()
            label = QLabel(label_text, objectName="PracticeFieldLabel")
            box.addWidget(label)
            box.addWidget(field)
            editor.addLayout(box, row, column)
        body_layout.addLayout(editor)

        summary_card = QFrame(objectName="PracticeSummary")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 15, 18, 16)
        summary_layout.addWidget(QLabel("편성 요약", objectName="PracticeFieldLabel"))
        self.summary = QLabel()
        self.summary.setObjectName("PracticeSummaryText")
        self.summary.setWordWrap(True)
        summary_layout.addWidget(self.summary)
        self.rule_hint = QLabel(
            "2차 캠프 구간에는 하루 한 경기만 편성할 수 있습니다. 결과는 정규시즌 승패에 반영되지 않습니다."
        )
        self.rule_hint.setObjectName("PracticeMuted")
        self.rule_hint.setWordWrap(True)
        summary_layout.addWidget(self.rule_hint)
        body_layout.addWidget(summary_card)
        body_layout.addStretch()

        action_row = QHBoxLayout()
        action_row.addStretch()
        cancel = QPushButton("닫기")
        cancel.clicked.connect(self.reject)
        action_row.addWidget(cancel)
        self.submit = QPushButton("연습경기 등록", objectName="PracticePrimary")
        self.submit.clicked.connect(self._submit)
        action_row.addWidget(self.submit)
        body_layout.addLayout(action_row)
        root.addWidget(body, 1)

        for widget in (
            self.date_edit, self.time_edit, self.opponent_combo, self.venue_combo,
            self.innings_spin, self.purpose_combo, self.lineup_combo,
            self.pitching_combo,
        ):
            if isinstance(widget, (QComboBox, QDateEdit, QTimeEdit)):
                if isinstance(widget, QComboBox):
                    widget.currentIndexChanged.connect(self._update_summary)
                else:
                    widget.dateTimeChanged.connect(self._update_summary)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._update_summary)

        if self.game_date > PRACTICE_WINDOW_END:
            self.submit.setEnabled(False)
            self.rule_hint.setText("연습경기 편성 가능 기간이 이미 종료되었습니다.")
        self.setStyleSheet(self._style())

    def _update_summary(self, *_args):
        opponent = self.opponent_combo.currentText()
        venue = self.venue_combo.currentText()
        day = self.date_edit.date().toString("M월 d일")
        self.summary.setText(
            f"{day} {self.time_edit.time().toString('HH:mm')}  ·  "
            f"{self.service.managed_team} vs {opponent}  ·  {venue}\n"
            f"{self.innings_spin.value()}이닝  ·  {self.purpose_combo.currentText()}  ·  "
            f"{self.lineup_combo.currentText()} / {self.pitching_combo.currentText()}"
        )

    def _submit(self):
        selected = self.date_edit.date().toPython()
        try:
            self.created_game_id = self.service.schedule_game(
                selected,
                self.opponent_combo.currentText(),
                venue_type=self.venue_combo.currentData(),
                start_time=self.time_edit.time().toString("HH:mm"),
                innings=self.innings_spin.value(),
                purpose=self.purpose_combo.currentText(),
                lineup_policy=self.lineup_combo.currentText(),
                pitching_plan=self.pitching_combo.currentText(),
                current_date=self.game_date,
            )
        except PracticeGameError as error:
            QMessageBox.warning(self, "연습경기 편성", str(error))
            return
        self.accept()

    def _style(self):
        accent = self.colors["accent"]
        accent_light = self.colors["accent_light"]
        return f"""
            QDialog {{ background:#0b1014; color:#edf3f8; }}
            QFrame#PracticeHeader {{ background:#111920; border:0; border-bottom:1px solid #26333c; border-left:5px solid {accent_light}; }}
            QFrame#PracticeBody {{ background:#0b1014; }}
            QLabel {{ color:#eaf0f5; font-family:'Malgun Gothic','Segoe UI'; }}
            QLabel#PracticeEyebrow {{ color:{accent_light}; font-size:13px; font-weight:800; letter-spacing:1px; }}
            QLabel#PracticeTitle {{ font-size:29px; font-weight:900; }}
            QLabel#PracticeMuted {{ color:#8d9ca7; font-size:14px; }}
            QLabel#PracticeFieldLabel {{ color:#b7c3ce; font-size:14px; font-weight:800; }}
            QFrame#PracticeSummary {{ background:#111d25; border:1px solid #2b424f; border-left:4px solid {accent_light}; border-radius:9px; }}
            QLabel#PracticeSummaryText {{ color:#f5f8fb; font-size:15px; font-weight:800; line-height:1.5; }}
            QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
                min-height:40px; padding:0 12px; color:#eef3f7; background:#151e25;
                border:1px solid #33414b; border-radius:7px; font-weight:700;
            }}
            QComboBox:hover, QDateEdit:hover, QTimeEdit:hover, QSpinBox:hover {{ border-color:{accent_light}; }}
            QPushButton {{ min-height:39px; padding:0 20px; color:#dce5ec; background:#19232b; border:1px solid #354550; border-radius:7px; font-weight:800; }}
            QPushButton:hover {{ background:#293641; border-color:#607384; }}
            QPushButton#PracticePrimary {{ color:white; background:{accent}; border-color:{accent_light}; min-width:150px; }}
            QPushButton#PracticePrimary:hover {{ background:{accent_light}; }}
            QPushButton:disabled {{ color:#66727e; background:#182028; border-color:#2a3540; }}
        """
