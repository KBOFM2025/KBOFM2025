"""팀 훈련, 개인 훈련, 코칭스태프를 한 화면에서 관리한다."""

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QGridLayout, QScrollArea, QSizePolicy, QStackedWidget, QButtonGroup, QLineEdit,
)

from app.services.training import (
    COACH_DEPARTMENTS, COACH_ROLES, REST_POLICIES, SESSION_TYPES, TEAM_FOCUSES,
    coaching_quality,
    TRAINING_SLOTS, TRAINING_UNITS, TrainingService,
)


class TrainingCenterPage(QWidget):
    """FM식 훈련 편성과 코치 배정을 제공하는 구단 운영 페이지."""

    workflow_completed = Signal(int)

    def __init__(self, colors, service: TrainingService, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.service = service
        self._players = []
        self._coaches = []
        self._workflow_event = None
        self.setObjectName('TrainingCenter')
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(16)
        header = QFrame(objectName="TrainingHeader")
        header_row = QHBoxLayout(header)
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("CLUB DEVELOPMENT  /  훈련 · 육성", objectName="TrainingEyebrow"))
        title_box.addWidget(QLabel("훈련 센터", objectName="TrainingTitle"))
        title_box.addWidget(QLabel(
            "팀 강도와 개인 중점, 담당 코치가 매일 성장·피로·부상 위험에 반영됩니다.",
            objectName="TrainingMuted",
        ))
        header_row.addLayout(title_box, 1)
        self.summary = QLabel(objectName="TrainingSummary")
        self.summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.summary)
        root.addWidget(header)

        self.workflow_bar = QFrame(objectName="TrainingWorkflow")
        workflow_row = QHBoxLayout(self.workflow_bar)
        workflow_row.setContentsMargins(18, 11, 12, 11)
        workflow_text = QVBoxLayout()
        workflow_text.setSpacing(2)
        self.workflow_title = QLabel(objectName="WorkflowTitle")
        self.workflow_detail = QLabel(objectName="WorkflowDetail")
        self.workflow_detail.setWordWrap(True)
        workflow_text.addWidget(self.workflow_title)
        workflow_text.addWidget(self.workflow_detail)
        workflow_row.addLayout(workflow_text, 1)
        self.workflow_finish = QPushButton("업무 완료", objectName="WorkflowButton")
        self.workflow_finish.clicked.connect(self._complete_workflow)
        workflow_row.addWidget(self.workflow_finish)
        self.workflow_bar.setVisible(False)
        root.addWidget(self.workflow_bar)

        self.tabs = QTabWidget(objectName="TrainingTabs")
        self.tabs.addTab(self._team_tab(), "팀 훈련")
        self.tabs.addTab(self._individual_tab(), "개인 훈련")
        self.tabs.addTab(self._units_tab(), "훈련 유닛")
        self.tabs.addTab(self._staff_tab(), "코치 선임·배정")
        self.tabs.addTab(self._responsibilities_tab(), "훈련 책임·담당 분야")
        self.tabs.addTab(self._management_tab(), "훈련 대시보드")
        self.tabs.addTab(self._development_tab(), "선수 성장")
        # The weekly editor needs its own vertical viewport on shorter displays.
        # Its minimum layout height must not enlarge every other stacked tab.
        team_page = self.tabs.widget(0)
        team_page.setObjectName('DashboardContent')
        self.tabs.removeTab(0)
        team_scroll = QScrollArea(objectName='DashboardScroll')
        team_scroll.setWidgetResizable(True)
        team_scroll.setFrameShape(QFrame.Shape.NoFrame)
        team_scroll.setWidget(team_page)
        self.tabs.insertTab(0, team_scroll, '팀 훈련')
        self.tabs.tabBar().hide()
        navigation = QFrame(objectName='TrainingNavigation')
        nav = QHBoxLayout(navigation)
        nav.setContentsMargins(5, 5, 5, 5)
        nav.setSpacing(4)
        self.navigation = QButtonGroup(self)
        for index, label in ((5, '대시보드'), (0, '팀 훈련'), (1, '개인 훈련'),
                             (2, '훈련 유닛'), (3, '코칭스태프'), (4, '담당 분야'), (6, '선수 성장')):
            button = QPushButton(label, objectName='TrainingNavButton')
            button.setCheckable(True)
            self.navigation.addButton(button, index)
            nav.addWidget(button, 1)
        self.navigation.idClicked.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(lambda index: self.navigation.button(index).setChecked(True))
        root.addWidget(navigation)
        self.tabs.setCurrentIndex(5)
        self._polish_tables()
        from app.views.coach_profile import CoachProfilePage
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.tabs)
        self.coach_profile = CoachProfilePage(self.service)
        self.coach_profile.back_requested.connect(lambda: self.content_stack.setCurrentWidget(self.tabs))
        self.content_stack.addWidget(self.coach_profile)
        root.addWidget(self.content_stack, 1)
        for table, name_column in ((self.league_staff_table, 2), (self.candidate_table, 0),
                                   (self.staff_table, 1), (self.duties_table, 0)):
            table.cellClicked.connect(lambda row, column, t=table, c=name_column:
                                      self._open_coach_from_table(t, row, column, c))
        self.setStyleSheet(self._style())

    def _open_coach_from_table(self, table, row, column, name_column):
        if column != name_column:
            return
        item = table.item(row, column)
        coach_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if coach_id is not None and self.coach_profile.set_coach(coach_id):
            self.content_stack.setCurrentWidget(self.coach_profile)

    def _development_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(16, 18, 16, 18)
        box.addWidget(QLabel("선수 성장 · 능력 변화 기록", objectName="SectionTitle"))
        note = QLabel("현재 소속 선수의 최근 200건 · 성장과 하락을 함께 표시합니다.\n"
                      "정수 능력치가 그대로여도 능력별 훈련 누적은 저장됩니다. 나이·잠재 한계·회복·사기·코치 지도에 따라 성장 속도가 다릅니다.", objectName="TrainingMuted")
        note.setWordWrap(True)
        box.addWidget(note)
        self.development_table = QTableWidget(0, 6, objectName="TrainingTable")
        self.development_table.setHorizontalHeaderLabels(("날짜", "선수", "능력", "이전", "현재", "변화 사유"))
        self.development_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.development_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.development_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.development_table.verticalHeader().setVisible(False)
        self.development_table.verticalHeader().setDefaultSectionSize(40)
        self.development_table.setAlternatingRowColors(True)
        self.development_table.setShowGrid(False)
        box.addWidget(self.development_table, 1)
        self.development_empty = QLabel("아직 기록된 능력 변화가 없습니다.", objectName="TrainingMuted")
        self.development_empty.setObjectName('TrainingEmpty')
        self.development_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.development_empty.setWordWrap(True)
        self.development_empty.setText('아직 기록된 능력 변화가 없습니다.\n\n날짜를 진행하면 선수의 성장과 하락이 이곳에 기록됩니다.\n정수 능력치 변화 전의 훈련 누적도 저장됩니다.')
        box.addWidget(self.development_empty, 1)
        return page

    def _refresh_development(self):
        names = dict(contact="컨택", power="장타", plate_discipline="선구안", bat_control="배트 컨트롤",
                     timing="타이밍", speed="주력", baserunning_judgment="주루 판단", fielding_range="수비 범위",
                     catching="포구", throwing_power="송구 강도", throwing_accuracy="송구 정확도",
                     fielding_judgment="수비 판단", composure="침착성", pitcher_velocity="구속",
                     pitcher_stuff="구위", pitcher_strikeout="탈삼진", pitcher_command="제구",
                     pitcher_walk_control="볼넷 억제", pitcher_movement="무브먼트", pitcher_pitchability="투구 운영",
                     pitcher_stamina="투수 체력", pitcher_composure="투수 침착성")
        rows = self.service.development_history()
        self.development_table.setRowCount(len(rows))
        self.development_empty.setVisible(not rows)
        self.development_table.setVisible(bool(rows))
        for row, event in enumerate(rows):
            values = (event["event_date"], event["name"], names.get(event["attribute"], event["attribute"]),
                      event["old_value"], event["new_value"], event["reason"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column in (3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 4:
                    item.setForeground(QColor("#67d5a4" if event["new_value"] > event["old_value"] else "#ec9393"))
                self.development_table.setItem(row, column, item)

    @staticmethod
    def _coach_name_link(item):
        item.setForeground(QColor("#79cdea"))
        font = item.font()
        font.setUnderline(True)
        item.setFont(font)
        item.setToolTip("클릭하여 코치 세부 능력 보기")

    def _management_tab(self):
        from app.config.club_training_profiles import club_profile
        profile = club_profile(self.service.team)
        page = QScrollArea(objectName="DashboardScroll")
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(objectName="DashboardContent")
        content.setMinimumWidth(850)
        page.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(14)

        def card(title, eyebrow):
            frame = QFrame(objectName="DashboardCard")
            box = QVBoxLayout(frame)
            box.setContentsMargins(20, 18, 20, 18)
            box.setSpacing(12)
            box.addWidget(QLabel(eyebrow, objectName="SectionEyebrow"))
            box.addWidget(QLabel(title, objectName="SectionTitle"))
            return frame, box

        stats = QHBoxLayout()
        self.dashboard_stats = []
        for title, hint in (("선수단 컨디션", "전체 선수 평균 · 100 기준"),
                            ("회복 관리 대상", "컨디션 70 미만 또는 피로 50 이상"),
                            ("훈련 총괄", "훈련 책임 탭에서 배정"),
                            ("운영 권한", "저장된 운영 방식")):
            frame = QFrame(objectName="DashboardStat")
            box = QVBoxLayout(frame)
            box.setContentsMargins(18, 14, 18, 14)
            box.addWidget(QLabel(title, objectName="TrainingMuted"))
            value = QLabel("—", objectName="DashboardValue")
            value.setWordWrap(True)
            self.dashboard_stats.append(value)
            box.addWidget(value)
            note = QLabel(hint, objectName="TrainingMuted")
            note.setWordWrap(True)
            box.addWidget(note)
            stats.addWidget(frame, 1)
        layout.addLayout(stats)
        columns = QHBoxLayout()
        columns.setSpacing(14)
        left = QVBoxLayout()
        schedule, box = card("이번 주 훈련 계획", "WEEKLY PROGRAMME")
        tools = QHBoxLayout()
        self.dashboard_week = QLabel(objectName="TrainingMuted")
        tools.addWidget(self.dashboard_week)
        tools.addStretch()
        edit = QPushButton("일정 편성  →", objectName="SecondaryButton")
        edit.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        tools.addWidget(edit)
        box.addLayout(tools)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.dashboard_sessions = {}
        self.dashboard_dates = []
        for index, weekday in enumerate(("월", "화", "수", "목", "금", "토", "일")):
            label = QLabel(weekday, objectName="DashboardDay")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.dashboard_dates.append(label)
            grid.addWidget(label, 0, index + 1)
            grid.setColumnStretch(index + 1, 1)
            for row, slot in enumerate(TRAINING_SLOTS, 1):
                if index == 0:
                    grid.addWidget(QLabel(slot, objectName="TrainingMuted"), row, 0)
                cell = QLabel(objectName="DashboardSession")
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setWordWrap(True)
                cell.setMinimumHeight(55)
                cell.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                grid.addWidget(cell, row, index + 1)
                self.dashboard_sessions[(index, slot)] = cell
        box.addLayout(grid)
        legend = QLabel('<span style="color:#6bc5a5">● 회복·휴식</span>　 '
                        '<span style="color:#67accf">● 기술 훈련</span>　 '
                        '<span style="color:#d9ac65">● 고강도</span>', objectName="TrainingMuted")
        box.addWidget(legend)
        left.addWidget(schedule)
        report, report_box = card("수석 코치 브리핑", "STAFF REPORT")
        self.management_report = QLabel(objectName="DashboardReport")
        self.management_report.setWordWrap(True)
        report_box.addWidget(self.management_report)
        left.addWidget(report)
        research, research_box = card(profile['theme'], "CLUB TRAINING IDENTITY · 2025")
        research_text = QLabel("11월 집중 훈련 → 후반 회복 → 겨울 휴식\n" + profile['note'], objectName="TrainingMuted")
        research_text.setWordWrap(True)
        research_box.addWidget(research_text)
        source = QLabel(f'<a style="color:#69cfff" href="{profile["source"]}">공개 캠프 자료 ↗</a>')
        source.setOpenExternalLinks(True)
        research_box.addWidget(source)
        left.addWidget(research)
        left.addStretch()
        columns.addLayout(left, 3)
        right = QVBoxLayout()
        authority, authority_box = card("훈련 운영 권한", "MANAGER’S OFFICE")
        authority.setMaximumWidth(360)
        self.management_mode = QComboBox()
        for title, flags in (("감독 직접 운영", (0, 0)), ("팀 훈련만 수석 코치 위임", (1, 0)),
                             ("개인 훈련만 수석 코치 위임", (0, 1)), ("팀·개인 훈련 모두 위임", (1, 1))):
            self.management_mode.addItem(title, flags)
        authority_box.addWidget(self.management_mode)
        explanation = QLabel("팀 일정과 개인 훈련을 따로 위임할 수 있습니다. 수석 코치가 날짜 진행 시 계획을 조정합니다.", objectName="TrainingMuted")
        explanation.setWordWrap(True)
        authority_box.addWidget(explanation)
        save = QPushButton("운영 방식 저장", objectName="PrimaryButton")
        save.clicked.connect(self._save_management)
        authority_box.addWidget(save)
        protected = QLabel("수동 계획 우선\n직접 저장한 계획은 자동 편성에서 보호합니다.", objectName="DashboardProtection")
        protected.setWordWrap(True)
        authority_box.addWidget(protected)
        release = QPushButton("직접 계획 보호 해제…", objectName="SecondaryButton")
        release.clicked.connect(self._release_management)
        authority_box.addWidget(release)
        right.addWidget(authority)
        players, players_box = card("선수 상태 점검", "PLAYER CARE")
        self.dashboard_care = QLabel(objectName="DashboardReport")
        self.dashboard_care.setWordWrap(True)
        players_box.addWidget(self.dashboard_care)
        individual = QPushButton("개인 훈련 확인  →", objectName="SecondaryButton")
        individual.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        players_box.addWidget(individual)
        coaches = QPushButton("코치 담당 분야  →", objectName="SecondaryButton")
        coaches.clicked.connect(lambda: self.tabs.setCurrentIndex(4))
        players_box.addWidget(coaches)
        right.addWidget(players)
        right.addStretch()
        columns.addLayout(right, 1)
        layout.addLayout(columns)
        layout.addStretch()
        return page

    def _save_management(self):
        try:
            self.service.set_management_policy(*self.management_mode.currentData())
            self.refresh()
        except ValueError as exc:
            QMessageBox.warning(self, "훈련 운영", str(exc))

    def _release_management(self):
        if QMessageBox.question(self, "직접 계획 보호 해제",
                "미래 팀 일정과 개인 계획을 자동 편성이 수정할 수 있도록 전환할까요?\n과거 일정은 유지됩니다.") == QMessageBox.StandardButton.Yes:
            self.service.release_training_overrides()
            self.refresh()

    def _polish_tables(self):
        for table in (
            self.player_table, self.unit_table, self.league_staff_table,
            self.candidate_table, self.staff_table, self.duties_table,
        ):
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(46)
            table.setShowGrid(False)
            table.setAlternatingRowColors(True)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            table.setWordWrap(False)
            table.setTextElideMode(Qt.TextElideMode.ElideRight)
            table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
            table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        for label in self.findChildren(QLabel):
            if label.objectName() in ('TrainingMuted', 'CoachDetail', 'ImpactText'):
                label.setWordWrap(True)
        for combo in self.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(5)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _team_tab(self):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(14, 16, 14, 14)
        outer.setSpacing(12)

        schedule_card = QFrame(objectName="ScheduleBoard")
        schedule_box = QVBoxLayout(schedule_card)
        schedule_box.setContentsMargins(18, 16, 18, 18)
        schedule_box.setSpacing(14)
        schedule_header = QHBoxLayout()
        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title_column.addWidget(QLabel("THIS WEEK", objectName="SectionEyebrow"))
        title_column.addWidget(QLabel("주간 훈련 일정", objectName="SectionTitle"))
        schedule_header.addLayout(title_column)
        schedule_header.addStretch()
        self.schedule_week_label = QLabel(objectName="WeekRange")
        schedule_header.addWidget(self.schedule_week_label)
        save_schedule = QPushButton("주간 일정 저장", objectName="PrimaryButton")
        save_schedule.clicked.connect(self._save_weekly_schedule)
        schedule_header.addWidget(save_schedule)
        schedule_box.addLayout(schedule_header)

        legend = QFrame(objectName="ScheduleLegend")
        legend_row = QHBoxLayout(legend)
        legend_row.setContentsMargins(12, 7, 12, 7)
        legend_row.addWidget(QLabel(
            "세션을 선택해 이번 주 훈련을 편성하세요.",
            objectName="TrainingMuted",
        ))
        legend_row.addStretch()
        legend_row.addWidget(QLabel("● 회복", objectName="LegendRecovery"))
        legend_row.addWidget(QLabel("● 기술", objectName="LegendSkill"))
        legend_row.addWidget(QLabel("● 고강도", objectName="LegendLoad"))
        schedule_box.addWidget(legend)

        self.schedule_combos = {}
        self.day_names = []
        self.day_dates = []
        days_row = QGridLayout()
        days_row.setHorizontalSpacing(12)
        days_row.setVerticalSpacing(10)
        days_row.addWidget(QLabel('훈련일', objectName='SessionLabel'), 0, 0)
        for column, slot in enumerate(TRAINING_SLOTS, 1):
            days_row.addWidget(QLabel(slot, objectName='SessionLabel'), 0, column)
            days_row.setColumnStretch(column, 1)
        for day_index, weekday in enumerate(("월", "화", "수", "목", "금", "토", "일")):
            day_card = QFrame(objectName="TrainingDay")
            day_card.setProperty("weekend", day_index >= 5)
            day_box = QHBoxLayout(day_card)
            day_box.setContentsMargins(12, 6, 12, 6)
            day_box.setSpacing(12)
            day_name = QLabel(weekday, objectName="DayName")
            day_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_date = QLabel("", objectName="DayDate")
            day_date.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.day_names.append(day_name)
            self.day_dates.append(day_date)
            day_box.addWidget(day_name)
            day_box.addWidget(day_date)
            days_row.addWidget(day_card, day_index + 1, 0)
            for column, slot in enumerate(TRAINING_SLOTS, 1):
                combo = QComboBox(objectName="SessionCombo")
                combo.addItems(SESSION_TYPES)
                combo.currentTextChanged.connect(lambda text, control=combo: self._session_color(control, text))
                days_row.addWidget(combo, day_index + 1, column)
                self.schedule_combos[(day_index, slot)] = combo
        schedule_box.addLayout(days_row)
        schedule_box.addStretch(1)
        outer.addWidget(schedule_card, 1)

        editor = QFrame(objectName="TrainingControlPanel")
        editor.setFixedWidth(290)
        box = QVBoxLayout(editor)
        box.setContentsMargins(18, 17, 18, 18)
        box.setSpacing(8)
        box.addWidget(QLabel("TEAM LOAD", objectName="SectionEyebrow"))
        box.addWidget(QLabel("팀 훈련 기준", objectName="SectionTitle"))
        team_note = QLabel('팀 기본 강도에 세션·개인 훈련 부하가 더해집니다.', objectName='TrainingMuted')
        team_note.setWordWrap(True)
        team_note.setMinimumHeight(42)
        box.addWidget(team_note)
        box.addSpacing(6)
        box.addWidget(QLabel("주간 중점", objectName="FieldLabel"))
        self.team_focus = QComboBox()
        self.team_focus.addItems(TEAM_FOCUSES)
        box.addWidget(self.team_focus)
        box.addWidget(QLabel("기본 강도 · 1 회복 / 5 매우 강함", objectName="FieldLabel"))
        self.team_intensity = QSpinBox()
        self.team_intensity.setRange(1, 5)
        box.addWidget(self.team_intensity)
        box.addWidget(QLabel("휴식 정책", objectName="FieldLabel"))
        self.rest_policy = QComboBox()
        self.rest_policy.addItems(REST_POLICIES)
        box.addWidget(self.rest_policy)
        save = QPushButton("팀 기준 적용", objectName="SecondaryButton")
        save.clicked.connect(self._save_team_setting)
        box.addWidget(save)
        box.addSpacing(12)
        box.addWidget(QLabel("예상 부하", objectName="CardTitle"))
        self.team_effect = QLabel(objectName="ImpactText")
        self.team_effect.setWordWrap(True)
        box.addWidget(self.team_effect)
        box.addStretch()
        outer.addWidget(editor)
        self.team_focus.currentTextChanged.connect(self._render_team_effect)
        self.team_intensity.valueChanged.connect(self._render_team_effect)
        self.rest_policy.currentTextChanged.connect(self._render_team_effect)
        return page

    @staticmethod
    def _session_color(combo, text):
        category = 'recovery' if text in ('휴식', '회복', '재활') else 'load' if text in ('체력', '실전 훈련', '청백전') else 'skill'
        combo.setProperty('category', category)
        combo.style().unpolish(combo)
        combo.style().polish(combo)

    def _individual_tab(self):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(8, 12, 8, 8)
        self.player_table = QTableWidget(0, 9)
        self.player_table.setObjectName("TrainingTable")
        self.player_table.setHorizontalHeaderLabels(
            ("선수", "포지션", "1·2군", "훈련 유닛", "개인 중점", "강도", "7일 평점", "컨디션", "피로")
        )
        self.player_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.player_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.player_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.player_table.itemSelectionChanged.connect(self._select_player)
        roster = QVBoxLayout()
        roster.setSpacing(12)
        roster.addWidget(QLabel('선수별 훈련 계획', objectName='SectionTitle'))
        self.player_search = QLineEdit()
        self.player_search.setPlaceholderText('선수 이름 또는 포지션 검색')
        self.player_search.textChanged.connect(self._filter_players)
        roster.addWidget(self.player_search)
        roster.addWidget(self.player_table, 1)
        outer.addLayout(roster, 1)

        editor = QFrame(objectName="TrainingCard")
        editor.setFixedWidth(290)
        box = QVBoxLayout(editor)
        box.setContentsMargins(18, 17, 18, 18)
        box.addWidget(QLabel("개인 훈련 배정", objectName="CardTitle"))
        self.selected_player = QLabel("선수를 선택하세요", objectName="SelectedName")
        box.addWidget(self.selected_player)
        box.addWidget(QLabel("훈련 중점", objectName="FieldLabel"))
        self.individual_focus = QComboBox()
        box.addWidget(self.individual_focus)
        box.addWidget(QLabel("개인 강도", objectName="FieldLabel"))
        self.individual_intensity = QSpinBox()
        self.individual_intensity.setRange(1, 3)
        self.individual_intensity.setValue(2)
        box.addWidget(self.individual_intensity)
        box.addWidget(QLabel("담당 코치", objectName="FieldLabel"))
        self.individual_coach = QComboBox()
        box.addWidget(self.individual_coach)
        self.individual_note = QLabel(
            "담당 코치의 전문 분야가 훈련 중점과 일치하면 성장 효율이 추가로 상승합니다.",
            objectName="TrainingMuted",
        )
        self.individual_note.setWordWrap(True)
        box.addWidget(self.individual_note)
        self.individual_rating = QLabel(objectName='TrainingRating')
        self.individual_rating.setWordWrap(True)
        self.individual_rating.setText('아직 훈련 평점이 없습니다.')
        box.addWidget(self.individual_rating)
        self.individual_rating_history = QLabel(objectName='TrainingMuted')
        self.individual_rating_history.setWordWrap(True)
        box.addWidget(self.individual_rating_history)
        box.addStretch()
        self.apply_individual = QPushButton("개인 계획 적용", objectName="PrimaryButton")
        self.apply_individual.clicked.connect(self._save_individual)
        box.addWidget(self.apply_individual)
        editor.setMinimumWidth(0)
        editor.setMaximumWidth(16777215)
        editor_scroll = QScrollArea(objectName='DashboardScroll')
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setFixedWidth(290)
        editor_scroll.setWidget(editor)
        outer.addWidget(editor_scroll)
        return page

    def _units_tab(self):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(8, 12, 8, 8)
        self.unit_table = QTableWidget(0, 5)
        self.unit_table.setObjectName("TrainingTable")
        self.unit_table.setHorizontalHeaderLabels(
            ("선수", "포지션", "소속", "현재 유닛", "개인 중점")
        )
        self.unit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.unit_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.unit_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.unit_table.itemSelectionChanged.connect(self._select_unit_player)
        unit_roster = QVBoxLayout()
        unit_roster.addWidget(QLabel('훈련조 구성', objectName='SectionTitle'))
        self.unit_filter = QComboBox()
        self.unit_filter.addItems(('전체 훈련조', *TRAINING_UNITS))
        self.unit_filter.currentTextChanged.connect(self._filter_units)
        unit_roster.addWidget(self.unit_filter)
        unit_roster.addWidget(self.unit_table, 1)
        outer.addLayout(unit_roster, 1)

        editor = QFrame(objectName="TrainingCard")
        editor.setFixedWidth(290)
        box = QVBoxLayout(editor)
        box.addWidget(QLabel("훈련 유닛 이동", objectName="CardTitle"))
        self.unit_player_name = QLabel("선수를 선택하세요", objectName="SelectedName")
        box.addWidget(self.unit_player_name)
        box.addWidget(QLabel("배정 유닛", objectName="FieldLabel"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(TRAINING_UNITS)
        box.addWidget(self.unit_combo)
        unit_note = QLabel(
            "선수는 유닛에 맞는 세션에서 가장 큰 효과를 받습니다. 포지션 전환을 "
            "시험할 때는 다른 유닛으로 이동할 수 있지만 적응 전까지 효율이 낮아질 수 있습니다.",
            objectName="TrainingMuted",
        )
        unit_note.setWordWrap(True)
        box.addWidget(unit_note)
        box.addStretch()
        apply_unit = QPushButton("유닛 배정", objectName="PrimaryButton")
        apply_unit.clicked.connect(self._save_training_unit)
        box.addWidget(apply_unit)
        outer.addWidget(editor)
        return page

    def _staff_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(8, 12, 8, 8)

        browser = QFrame(objectName="TrainingCard")
        browser_box = QVBoxLayout(browser)
        browser_header = QHBoxLayout()
        browser_header.addWidget(QLabel("2025 KBO 전체 코칭스태프", objectName="CardTitle"))
        browser_header.addStretch()
        browser_header.addWidget(QLabel("구단", objectName="FieldLabel"))
        self.league_team_filter = QComboBox()
        self.league_team_filter.setMinimumWidth(170)
        self.league_team_filter.addItem("전체 구단")
        browser_header.addWidget(self.league_team_filter)
        browser_header.addWidget(QLabel("소속", objectName="FieldLabel"))
        self.league_squad_filter = QComboBox()
        self.league_squad_filter.addItems(("전체", "1군", "퓨처스", "잔류·육성·재활"))
        browser_header.addWidget(self.league_squad_filter)
        browser_box.addLayout(browser_header)
        browser_box.addWidget(QLabel(
            "명단·보직은 2025 구단 발표 기준이며, 능력치는 보직·소속 단계·지도 경력에 따른 게임 추정치입니다.",
            objectName="TrainingMuted",
        ))
        self.league_staff_table = QTableWidget(0, 8)
        self.league_staff_table.setObjectName("TrainingTable")
        self.league_staff_table.setHorizontalHeaderLabels(
            ("구단", "소속", "이름 ↗", "보직", "전문", "동기부여", "유망주 육성", "지도 스타일")
        )
        self.league_staff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.league_staff_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.league_staff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.league_staff_table.setAlternatingRowColors(True)
        self.league_staff_table.setMinimumHeight(210)
        self.league_staff_table.itemSelectionChanged.connect(
            lambda: self._show_coach_detail(self.league_staff_table)
        )
        browser_box.addWidget(self.league_staff_table)
        self.coach_detail = QLabel("코치를 선택하면 FM식 세부 능력치와 출처를 확인할 수 있습니다.")
        self.coach_detail.setObjectName("CoachDetail")
        self.coach_detail.setWordWrap(True)
        self.coach_detail.setMinimumHeight(82)
        browser_box.addWidget(self.coach_detail)
        self.league_team_filter.currentTextChanged.connect(self._fill_league_staff)
        self.league_squad_filter.currentTextChanged.connect(self._fill_league_staff)
        self.staff_sections = QTabWidget(objectName='StaffSections')
        self.staff_sections.addTab(browser, '전체 코치 명단')
        outer.addWidget(self.staff_sections, 1)

        left = QFrame(objectName="TrainingCard")
        left_box = QVBoxLayout(left)
        left_box.addWidget(QLabel("영입 가능한 실제 지도자", objectName="CardTitle"))
        self.candidate_table = QTableWidget(0, 6)
        self.candidate_table.setObjectName("TrainingTable")
        self.candidate_table.setHorizontalHeaderLabels(
            ("이름 ↗", "희망 보직", "전문", "동기부여", "유망주 육성", "요구 연봉")
        )
        self.candidate_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.candidate_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.candidate_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.candidate_table.itemSelectionChanged.connect(
            lambda: self._show_coach_detail(self.candidate_table)
        )
        left_box.addWidget(self.candidate_table)
        hire_row = QHBoxLayout()
        self.hire_role = QComboBox()
        self.hire_role.addItems(COACH_ROLES)
        hire_row.addWidget(self.hire_role)
        hire = QPushButton("선임", objectName="PrimaryButton")
        hire.clicked.connect(self._hire_coach)
        hire_row.addWidget(hire)
        left_box.addLayout(hire_row)

        right = QFrame(objectName="TrainingCard")
        right_box = QVBoxLayout(right)
        right_box.addWidget(QLabel("우리 코칭스태프", objectName="CardTitle"))
        self.staff_table = QTableWidget(0, 8)
        self.staff_table.setObjectName("TrainingTable")
        self.staff_table.setHorizontalHeaderLabels(
            ("소속", "이름 ↗", "보직", "전문", "동기부여", "업무량", "훈련 품질", "계약 종료")
        )
        self.staff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.staff_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.staff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.staff_table.itemSelectionChanged.connect(
            lambda: self._show_coach_detail(self.staff_table)
        )
        right_box.addWidget(self.staff_table)
        assignment_row = QHBoxLayout()
        self.assignment_focus = QComboBox()
        self.assignment_focus.addItems(COACH_DEPARTMENTS)
        assignment_row.addWidget(self.assignment_focus)
        self.assignment_unit = QComboBox()
        self.assignment_unit.addItems(("팀 전체", *TRAINING_UNITS))
        assignment_row.addWidget(self.assignment_unit)
        assign = QPushButton("담당 배정", objectName="SecondaryButton")
        assign.clicked.connect(self._assign_team_coach)
        assignment_row.addWidget(assign)
        right_box.addLayout(assignment_row)
        self.assignment_text = QLabel(objectName="TrainingMuted")
        self.assignment_text.setWordWrap(True)
        right_box.addWidget(self.assignment_text)
        # Each roster gets the full width instead of two cramped half-width tables.
        self.staff_sections.addTab(right, '우리 코칭스태프 · 배정')
        self.staff_sections.addTab(left, '영입 후보 · 선임')
        self.staff_sections.setCurrentIndex(1)
        return page

    def _filter_players(self, text=''):
        query = text.strip().casefold()
        for row in range(self.player_table.rowCount()):
            values = [self.player_table.item(row, column) for column in (0, 1)]
            self.player_table.setRowHidden(row, bool(query) and not any(query in item.text().casefold() for item in values if item))

    def _filter_units(self, text='전체 훈련조'):
        for row in range(self.unit_table.rowCount()):
            item = self.unit_table.item(row, 3)
            self.unit_table.setRowHidden(row, text != '전체 훈련조' and (not item or item.text() != text))

    def _responsibilities_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        header = QFrame(objectName="TrainingCard")
        header_layout = QVBoxLayout(header)
        header_layout.addWidget(QLabel("훈련 책임 및 코치 배정", objectName="CardTitle"))
        note = QLabel(
            "감독은 훈련 편성을 결정합니다. 수석 코치에게 주간 편성을 맡기거나 직접 조정하세요.\n"
            "담당 분야를 체크하면 지도 능력과 겸임 업무량이 훈련 품질에 반영됩니다. 숫자는 분야별 지도 품질(5점 만점)입니다.",
            objectName="TrainingMuted",
        )
        note.setWordWrap(True)
        header_layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(QLabel("훈련 총괄"))
        self.head_coach_combo = QComboBox()
        row.addWidget(self.head_coach_combo, 1)
        recommend = QPushButton("능력에 맞춰 배정안 작성", objectName="SecondaryButton")
        recommend.clicked.connect(self._recommend_duties)
        row.addWidget(recommend)
        header_layout.addLayout(row)
        layout.addWidget(header)
        self.duties_table = QTableWidget(0, len(COACH_DEPARTMENTS) + 2)
        self.duties_table.setObjectName("TrainingTable")
        self.duties_table.setHorizontalHeaderLabels(("코치 / 소속 / 보직", *COACH_DEPARTMENTS, "업무량"))
        self.duties_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.duties_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.duties_table.setColumnWidth(0, 260)
        self.duties_table.setWordWrap(False)
        self.duties_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.duties_table.itemChanged.connect(self._update_duty_quality)
        self.head_coach_combo.currentIndexChanged.connect(self._update_duty_quality)
        layout.addWidget(self.duties_table, 1)
        self.duties_summary = QLabel(objectName="TrainingMuted")
        self.duties_summary.setWordWrap(True)
        layout.addWidget(self.duties_summary)
        actions = QHBoxLayout()
        save = QPushButton("책임·배정 저장", objectName="PrimaryButton")
        save.clicked.connect(self._save_duties)
        actions.addWidget(save)
        week = QPushButton("수석 코치에게 선택 주간 편성 맡기기", objectName="SecondaryButton")
        week.clicked.connect(self._head_coach_week)
        actions.addWidget(week)
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _fill_duties(self, proposal=None):
        assignments = self.service.assignments()
        self._duty_coaches = [c for c in self._coaches if c["status"] == "hired" and c["team"] == self.service.team]
        self.head_coach_combo.blockSignals(True)
        self.head_coach_combo.clear()
        self.head_coach_combo.addItem("감독 — 직접 총괄", None)
        head_id = next((a["coach_id"] for a in assignments if a["assignment_type"] == "responsibility"), None)
        for coach in self._duty_coaches:
            if "수석" in coach["role"]:
                self.head_coach_combo.addItem(f"{coach['name']} · {coach['squad']} {coach['role']}", coach["id"])
        self.head_coach_combo.setCurrentIndex(max(0, self.head_coach_combo.findData(head_id)))
        self.head_coach_combo.blockSignals(False)
        self.duties_table.blockSignals(True)
        self.duties_table.setRowCount(len(self._duty_coaches))
        for row, coach in enumerate(self._duty_coaches):
            name_item = QTableWidgetItem(f"{coach['name']} / {coach['squad']} / {coach['role']}")
            name_item.setData(Qt.ItemDataRole.UserRole, int(coach["id"]))
            self._coach_name_link(name_item)
            self.duties_table.setItem(row, 0, name_item)
            focuses = proposal.get(int(coach["id"]), set()) if proposal is not None else {
                a["focus"] for a in assignments if a["coach_id"] == coach["id"] and a["assignment_type"] == "team"
            }
            for column, focus in enumerate(COACH_DEPARTMENTS, 1):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if focus in focuses else Qt.CheckState.Unchecked)
                self.duties_table.setItem(row, column, item)
        self.duties_table.blockSignals(False)
        self._update_duty_quality()

    def _duty_selection(self):
        return {int(coach["id"]): {
            focus for column, focus in enumerate(COACH_DEPARTMENTS, 1)
            if self.duties_table.item(row, column).checkState() == Qt.CheckState.Checked
        } for row, coach in enumerate(self._duty_coaches)}

    def _update_duty_quality(self, *_args):
        selection = self._duty_selection()
        other = self.service.assignments()
        self.duties_table.blockSignals(True)
        for row, coach in enumerate(self._duty_coaches):
            load = len(selection[int(coach["id"])]) + sum(
                a["workload"] for a in other if a["coach_id"] == coach["id"] and a["assignment_type"] not in {"team", "responsibility"}
            ) + int(self.head_coach_combo.currentData() == coach["id"])
            for column, focus in enumerate(COACH_DEPARTMENTS, 1):
                item = self.duties_table.item(row, column)
                quality = coaching_quality(coach, focus, max(1, load)) / 4
                item.setText(f"{quality:.1f}")
                item.setToolTip(f"{focus} 지도 품질 {quality:.1f} / 5 · 겸임 {load}개 반영")
            label = "없음" if load == 0 else "낮음" if load == 1 else "보통" if load == 2 else "높음" if load == 3 else "과중"
            self.duties_table.setItem(row, len(COACH_DEPARTMENTS) + 1, QTableWidgetItem(f"{label} ({load})"))
        self.duties_table.blockSignals(False)
        covered = set().union(*selection.values()) if selection else set()
        missing = [f for f in COACH_DEPARTMENTS if f not in covered]
        self.duties_summary.setText("미배정 분야: " + (", ".join(missing) or "없음") + " · 변경 후 저장해야 훈련에 적용됩니다.")

    def _recommend_duties(self):
        try:
            self._fill_duties(self.service.recommended_coaching_structure())
        except ValueError as error:
            QMessageBox.warning(self, "코치 배정", str(error))

    def _save_duties(self):
        try:
            self.service.save_coaching_structure(self._duty_selection(), self.head_coach_combo.currentData())
        except ValueError as error:
            QMessageBox.warning(self, "코치 배정", str(error))
            return
        self.refresh()

    def _head_coach_week(self):
        try:
            self.service.prepare_head_coach_week(self._schedule_week_start)
        except ValueError as error:
            QMessageBox.warning(self, "주간 훈련 편성", str(error))
            return
        self.refresh()
        self.tabs.setCurrentIndex(0)

    def refresh(self):
        policy = self.service.management_policy()
        flags = (policy["delegate_team"], policy["delegate_individual"])
        self.management_mode.setCurrentIndex(next(i for i in range(self.management_mode.count())
                                                 if tuple(self.management_mode.itemData(i)) == flags))
        self.management_report.setText(self.service.delegation_report())
        setting = self.service.team_setting()
        self.team_focus.setCurrentText(setting["focus"])
        self.team_intensity.setValue(int(setting["intensity"]))
        self.rest_policy.setCurrentText(setting["rest_policy"])
        self._players = self.service.players()
        self._coaches = self.service.coaches()
        teams = sorted({c["team"] for c in self._coaches if c["team"]})
        selected_team = self.league_team_filter.currentText()
        self.league_team_filter.blockSignals(True)
        self.league_team_filter.clear()
        self.league_team_filter.addItem("전체 구단")
        self.league_team_filter.addItems(teams)
        self.league_team_filter.setCurrentText(
            selected_team if selected_team in teams or selected_team == "전체 구단" else self.service.team
        )
        self.league_team_filter.blockSignals(False)
        self._fill_players()
        self._fill_weekly_schedule()
        self._fill_units()
        self._fill_coaches()
        self._fill_duties()
        self._align_coach_tables()
        self._render_team_effect()
        hired = [c for c in self._coaches if c["status"] == "hired" and c["team"] == self.service.team]
        average_condition = round(sum(p["condition"] for p in self._players) / max(1, len(self._players)))
        self.summary.setText(
            f"{self.service.team}\n선수 {len(self._players)}명 · 코칭스태프 {len(hired)}명 · 평균 컨디션 {average_condition}"
        )
        self._refresh_dashboard(average_condition)
        self._refresh_development()
        self._filter_players(self.player_search.text())
        self._filter_units(self.unit_filter.currentText())
        if self.player_table.currentRow() < 0 and self.player_table.rowCount():
            self.player_table.selectRow(0)
        elif self.player_table.currentRow() >= 0:
            self._select_player()
        if self.unit_table.currentRow() < 0 and self.unit_table.rowCount():
            self.unit_table.selectRow(0)
        self._update_workflow()

    def _align_coach_tables(self):
        for table, numeric in ((self.league_staff_table, {5, 6}),
                               (self.candidate_table, {3, 4, 5}),
                               (self.staff_table, {4, 5, 6}),
                               (self.duties_table, set(range(1, len(COACH_DEPARTMENTS) + 2)))):
            for column in range(table.columnCount()):
                alignment = Qt.AlignmentFlag.AlignCenter if column in numeric else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                header = table.horizontalHeaderItem(column)
                if header:
                    header.setTextAlignment(alignment)
                for row in range(table.rowCount()):
                    item = table.item(row, column)
                    if item:
                        item.setTextAlignment(alignment)

    def _refresh_dashboard(self, average_condition):
        at_risk = sorted((p for p in self._players if p["condition"] < 70 or p["fatigue"] >= 50),
                         key=lambda p: (p["condition"], -p["fatigue"]))
        head = next((a["coach_name"] for a in self.service.assignments()
                     if a["assignment_type"] == "responsibility"), "미배정")
        policy = self.service.management_policy()
        mode = {(0, 0): "감독 직접 운영", (1, 0): "팀 훈련 위임",
                (0, 1): "개인 훈련 위임", (1, 1): "수석 코치 위임"}
        for label, text in zip(self.dashboard_stats, (
                f"{average_condition} / 100", f"{len(at_risk)}명", head,
                mode[(policy["delegate_team"], policy["delegate_individual"])],)):
            label.setText(text)
        self.dashboard_care.setText("\n\n".join(
            f"{p['name']}\n컨디션 {p['condition']} · 피로 {p['fatigue']}" for p in at_risk[:4]
        ) + (f"\n\n외 {len(at_risk) - 4}명 · 개인 훈련에서 확인" if len(at_risk) > 4 else "")
            if at_risk else "현재 회복 관리 기준에 해당하는 선수가 없습니다.\n\n개인 훈련에서 선수별 중점과 강도를 조정하세요.")
        start = self._schedule_week_start
        if isinstance(start, str):
            start = date.fromisoformat(start)
        self.dashboard_week.setText(f"{start:%Y.%m.%d} — {start + timedelta(days=6):%m.%d} · 저장된 계획")
        for index, label in enumerate(self.dashboard_dates):
            day = start + timedelta(days=index)
            label.setText(f"{('월','화','수','목','금','토','일')[index]}\n{day:%m.%d}")
        for session in self.service.weekly_schedule(start):
            index = (date.fromisoformat(session["session_date"]) - start).days
            cell = self.dashboard_sessions[(index, session["slot"])]
            name = session["session_type"]
            cell.setText(name)
            cell.setToolTip(f"{session['session_date']} {session['slot']} · {name}\n일정 편성 버튼에서 변경할 수 있습니다.")
            category = "recovery" if name in ("휴식", "회복") else "load" if name in ("체력", "장타 훈련", "라이브 BP") else "skill"
            cell.setProperty("category", category)
            cell.style().unpolish(cell)
            cell.style().polish(cell)

    def set_workflow(self, event):
        """수신함의 11월 필수 업무를 훈련 센터의 실제 작업과 연결한다."""
        self._workflow_event = dict(event or {})
        schedule = dict(
            (self._workflow_event.get("payload") or {}).get("schedule_event") or {}
        )
        schedule_id = str(schedule.get("event_id") or "")
        self.workflow_title.setText(
            str(schedule.get("title") or self._workflow_event.get("headline") or "필수 업무")
        )
        self.workflow_bar.setVisible(True)
        self.tabs.setCurrentIndex(3 if schedule_id == "coaching_staff_review" else 0)
        self.refresh()

    def clear_workflow(self):
        self._workflow_event = None
        self.workflow_bar.setVisible(False)

    def _update_workflow(self):
        if not self._workflow_event:
            return
        schedule = dict(
            (self._workflow_event.get("payload") or {}).get("schedule_event") or {}
        )
        schedule_id = str(schedule.get("event_id") or "")
        progress = self.service.workflow_progress()
        if schedule_id == "coaching_staff_review":
            missing = progress["missing_focuses"]
            ready = progress["staff_ready"]
            self.workflow_detail.setText(
                "타격·투수·수비 담당 배정 완료"
                if ready else
                f"아직 담당 코치가 필요한 분야: {', '.join(missing)}"
            )
        else:
            ready = progress["training_ready"]
            team_status = "완료" if progress["team_plan_ready"] else "미설정"
            self.workflow_detail.setText(
                f"팀 훈련 {team_status} · 개인 훈련 "
                f"{progress['individual_plan_count']}/{progress['individual_plan_required']}명 · "
                f"주간 세션 {progress['weekly_session_count']}/21"
            )
        self.workflow_finish.setEnabled(ready)
        self.workflow_finish.setText("업무 제출 가능" if ready else "필수 항목 미완료")

    def _complete_workflow(self):
        if not self._workflow_event:
            return
        progress = self.service.workflow_progress()
        schedule_id = str(
            ((self._workflow_event.get("payload") or {}).get("schedule_event") or {}).get(
                "event_id"
            ) or ""
        )
        ready = (
            progress["staff_ready"]
            if schedule_id == "coaching_staff_review"
            else progress["training_ready"]
        )
        if not ready:
            QMessageBox.information(
                self, "필수 업무", "표시된 필수 항목을 먼저 완료하세요."
            )
            return
        self.workflow_completed.emit(int(self._workflow_event["id"]))

    def _fill_players(self):
        self.player_table.setRowCount(len(self._players))
        for row, player in enumerate(self._players):
            values = (
                player.get("name", "-"), player.get("pos") or player.get("position_group") or "-",
                "1군" if int(player.get("status") or 0) else "2군",
                player["training_unit"], player["training_focus"],
                player["training_intensity"], self._rating_text(player.get('training_rating', {})),
                player["condition"], player["fatigue"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(player["id"]))
                item.setToolTip(str(value))
                if column >= 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 7:
                    item.setForeground(QColor('#a8d9bc' if float(value) >= 70 else '#ebbf87'))
                elif column == 8:
                    item.setForeground(QColor('#e5a295' if float(value) >= 50 else '#91aabb'))
                elif column == 6:
                    rating = player.get('training_rating', {})
                    average = rating.get('average')
                    item.setForeground(QColor('#a8d9bc' if average is not None and average >= 7.5 else
                                               '#e5a295' if average is not None and average < 6 else '#c4d4df'))
                    item.setToolTip(self._rating_details(rating))
                self.player_table.setItem(row, column, item)

    @staticmethod
    def _rating_text(rating):
        average = rating.get('average')
        return f'{average:.1f}' if average is not None else '—'

    @staticmethod
    def _rating_details(rating):
        if not rating.get('history'):
            return '아직 훈련 평점이 없습니다. 날짜 진행 후 기록됩니다.'
        trend = rating.get('trend')
        change = f'{trend:+.1f}' if trend is not None else '비교 자료 부족'
        return (f"최근 7일 · 평가 {rating.get('days', 0)}일\n이전 7일 대비 {change}\n"
                '휴식·재활·차출일은 평균에서 제외\n훈련 수행 평가이며 능력치 상승을 보장하지 않습니다.')

    def _fill_coaches(self):
        candidates = [c for c in self._coaches if c["status"] == "candidate"]
        hired = [c for c in self._coaches if c["status"] == "hired" and c["team"] == self.service.team]
        self.candidate_table.setRowCount(len(candidates))
        for row, coach in enumerate(candidates):
            values = (
                coach["name"], coach["role"], coach["specialty"], coach["motivation"],
                coach["youth_development"], f"{coach['salary_10k']:,}만원",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(coach["id"]))
                self.candidate_table.setItem(row, column, item)
                if column == 0:
                    self._coach_name_link(item)
        workload_by_id = {
            int(item["id"]): item for item in self.service.coach_workloads()
        }
        self.staff_table.setRowCount(len(hired))
        for row, coach in enumerate(hired):
            workload = workload_by_id.get(int(coach["id"]), {})
            values = (
                coach["squad"], coach["name"], coach["role"], coach["specialty"],
                coach["motivation"], workload.get("workload_label", "없음"),
                f"{float(workload.get('training_stars', 1)):.1f} ★",
                coach["contract_end"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(coach["id"]))
                self.staff_table.setItem(row, column, item)
                if column == 1:
                    self._coach_name_link(item)
        assignments = self.service.assignments()
        self.assignment_text.setText(
            "현재 배정 · " + (", ".join(f"{a['coach_name']}→{a['focus']}" for a in assignments) or "없음")
        )
        self._fill_league_staff()

    def _fill_weekly_schedule(self):
        rows = self.service.weekly_schedule()
        by_key = {
            (str(row["session_date"]), str(row["slot"])): str(row["session_type"])
            for row in rows
        }
        if not rows:
            return
        start = date.fromisoformat(str(rows[0]["session_date"]))
        self._schedule_week_start = start
        end = start + timedelta(days=6)
        self.schedule_week_label.setText(f"{start:%Y.%m.%d} — {end:%m.%d}")
        for row_index in range(7):
            day = start + timedelta(days=row_index)
            self.day_dates[row_index].setText(f"{day:%m.%d}")
            for slot in TRAINING_SLOTS:
                combo = self.schedule_combos[(row_index, slot)]
                combo.setCurrentText(by_key.get((day.isoformat(), slot), "자율 훈련"))
                self._session_color(combo, combo.currentText())

    def _save_weekly_schedule(self):
        sessions = []
        start = getattr(self, "_schedule_week_start", self.service._week_start(date.today()))
        for row_index in range(7):
            session_date = (start + timedelta(days=row_index)).isoformat()
            for slot in TRAINING_SLOTS:
                combo = self.schedule_combos[(row_index, slot)]
                sessions.append({
                    "session_date": session_date,
                    "slot": slot,
                    "session_type": combo.currentText(),
                })
        try:
            self.service.set_weekly_schedule(sessions, start)
        except ValueError as error:
            QMessageBox.warning(self, "주간 훈련", str(error))
            return
        QMessageBox.information(self, "주간 훈련", "7일간 21개 훈련 세션을 적용했습니다.")
        self.refresh()

    def _fill_units(self):
        self.unit_table.setRowCount(len(self._players))
        for row, player in enumerate(self._players):
            values = (
                player.get("name", "-"),
                player.get("pos") or player.get("position_group") or "-",
                "1군" if int(player.get("status") or 0) else "2군",
                player["training_unit"], player["training_focus"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(player["id"]))
                self.unit_table.setItem(row, column, item)

    def _select_unit_player(self):
        player_id = self._selected_id(self.unit_table)
        player = next(
            (item for item in self._players if int(item["id"]) == player_id), None
        )
        if not player:
            return
        self.unit_player_name.setText(
            f"{player['name']} · {player.get('pos') or player.get('position_group') or '-'}"
        )
        self.unit_combo.setCurrentText(player["training_unit"])

    def _save_training_unit(self):
        player_id = self._selected_id(self.unit_table)
        if player_id is None:
            QMessageBox.information(self, "훈련 유닛", "먼저 선수를 선택하세요.")
            return
        try:
            self.service.set_training_unit(player_id, self.unit_combo.currentText())
        except ValueError as error:
            QMessageBox.warning(self, "훈련 유닛", str(error))
            return
        self.refresh()

    def _fill_league_staff(self, *_args):
        if not hasattr(self, "league_staff_table"):
            return
        team_filter = self.league_team_filter.currentText()
        squad_filter = self.league_squad_filter.currentText()
        rows = [coach for coach in self._coaches if coach["status"] == "hired" and coach["is_real"]]
        if team_filter and team_filter != "전체 구단":
            rows = [coach for coach in rows if coach["team"] == team_filter]
        if squad_filter == "1군":
            rows = [coach for coach in rows if coach["squad"] == "1군"]
        elif squad_filter == "퓨처스":
            rows = [coach for coach in rows if "퓨처스" in coach["squad"]]
        elif squad_filter == "잔류·육성·재활":
            rows = [coach for coach in rows if coach["squad"] != "1군" and "퓨처스" not in coach["squad"]]
        squad_order = {"1군": 0, "퓨처스": 1}
        rows.sort(key=lambda coach: (
            coach["team"], squad_order.get(coach["squad"], 2), coach["role"], coach["name"]
        ))
        self.league_staff_table.setRowCount(len(rows))
        for row, coach in enumerate(rows):
            values = (
                coach["team"], coach["squad"], coach["name"], coach["role"], coach["specialty"],
                coach["motivation"], coach["youth_development"], coach["coaching_style"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(coach["id"]))
                self.league_staff_table.setItem(row, column, item)
                if column == 2:
                    self._coach_name_link(item)

    def _show_coach_detail(self, table):
        coach_id = self._selected_id(table)
        coach = next((item for item in self._coaches if int(item["id"]) == coach_id), None)
        if not coach:
            return
        self.coach_detail.setText(
            f"{coach['name']}  |  {coach['team'] or '영입 후보'} · {coach['squad']} · {coach['role']}  |  "
            "이름을 클릭하면 전체 능력치 페이지가 열립니다.\n"
            f"기술  타격 {coach['batting']} · 투수 {coach['pitching']} · 수비 {coach['defense']} · "
            f"주루 {coach['baserunning']} · 포수 {coach['catching']} · 멘털 {coach['mental']}   |   "
            f"지도  동기부여 {coach['motivation']} · 규율 {coach['discipline']} · 선수관리 {coach['man_management']} · "
            f"적응 {coach['adaptability']} · 유망주 {coach['youth_development']} · 데이터 {coach['data_analysis']}\n"
            f"{coach['personality']} · {coach['coaching_style']} · 경력 추정 {coach['experience_years']}년   |   "
            f"명단 출처: {coach['source_label']} ({coach['source_as_of']})"
        )

    def _render_team_effect(self, *_args):
        focus = self.team_focus.currentText()
        intensity = self.team_intensity.value()
        rest = self.rest_policy.currentText()
        fatigue = "낮음" if intensity <= 2 else "보통" if intensity == 3 else "높음"
        development = "완만" if intensity <= 2 else "표준" if intensity == 3 else "빠름"
        risk = "감소" if rest == "회복 우선" else "증가" if rest == "강행" or intensity >= 5 else "보통"
        self.team_effect.setText(
            f"훈련 중점  {focus}\n\n성장 속도  {development}\n피로 누적  {fatigue}\n부상 위험  {risk}\n\n"
            "개인 중점과 코치 전문성이 일치하면 추가 훈련 포인트를 얻습니다. "
            "능력별 훈련 누적과 나이·잠재 한계·회복 상태에 따라 성장 여부가 달라집니다."
        )

    def _save_team_setting(self):
        try:
            self.service.set_team_setting(
                self.team_focus.currentText(), self.team_intensity.value(), self.rest_policy.currentText()
            )
        except ValueError as error:
            QMessageBox.warning(self, "팀 훈련", str(error))
            return
        QMessageBox.information(self, "팀 훈련", "다음 날 진행부터 새 훈련 계획이 적용됩니다.")
        self.refresh()

    def _selected_id(self, table):
        row = table.currentRow()
        item = table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _select_player(self):
        player_id = self._selected_id(self.player_table)
        player = next((p for p in self._players if int(p["id"]) == player_id), None)
        if not player:
            return
        self.selected_player.setText(f"{player['name']} · {player.get('pos') or player.get('position_group') or '-'}")
        rating = player.get('training_rating', {})
        trend = rating.get('trend')
        change = f' · 이전 주 대비 {trend:+.1f}' if trend is not None else ''
        self.individual_rating.setText(f"훈련 평점  {self._rating_text(rating)} / 10\n최근 7일 · 평가 {rating.get('days', 0)}일{change}")
        self.individual_rating.setToolTip(self._rating_details(rating))
        history = rating.get('history', [])[:3]
        self.individual_rating_history.setText('\n'.join(
            f"{row['training_date'][5:]}  ·  " + (f"{row['rating']:.1f}  {row['focus']}" if row['rating'] is not None else row['participation'])
            for row in history))
        self.individual_focus.clear()
        self.individual_focus.addItems(player["focus_options"])
        self.individual_focus.setCurrentText(player["training_focus"])
        self.individual_intensity.setValue(player["training_intensity"])
        self.individual_coach.clear()
        self.individual_coach.addItem("담당 코치 없음", None)
        for coach in self._coaches:
            if coach["status"] == "hired" and coach["team"] == self.service.team:
                self.individual_coach.addItem(
                    f"{coach['name']} · {coach['role']} · {coach['specialty']}", coach["id"]
                )
        index = self.individual_coach.findData(player.get("coach_id"))
        self.individual_coach.setCurrentIndex(max(0, index))

    def _save_individual(self):
        player_id = self._selected_id(self.player_table)
        if player_id is None:
            QMessageBox.information(self, "개인 훈련", "먼저 선수를 선택하세요.")
            return
        try:
            self.service.set_individual_plan(
                player_id, self.individual_focus.currentText(),
                self.individual_intensity.value(), self.individual_coach.currentData(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "개인 훈련", str(error))
            return
        self.refresh()

    def _hire_coach(self):
        coach_id = self._selected_id(self.candidate_table)
        if coach_id is None:
            QMessageBox.information(self, "코치 선임", "먼저 후보를 선택하세요.")
            return
        try:
            coach = self.service.hire_coach(coach_id, self.hire_role.currentText())
        except ValueError as error:
            QMessageBox.warning(self, "코치 선임", str(error))
            return
        QMessageBox.information(self, "코치 선임", f"{coach['name']} 코치를 {coach['role']}로 선임했습니다.")
        self.refresh()

    def _assign_team_coach(self):
        coach_id = self._selected_id(self.staff_table)
        if coach_id is None:
            QMessageBox.information(self, "코치 배정", "먼저 우리 코치를 선택하세요.")
            return
        try:
            self.service.assign_coach(
                coach_id, "team" if self.assignment_unit.currentIndex() == 0 else "unit",
                self.assignment_unit.currentIndex(), self.assignment_focus.currentText()
            )
        except ValueError as error:
            QMessageBox.warning(self, "코치 배정", str(error))
            return
        self.refresh()

    def _style(self):
        from app.views.training_theme import TRAINING_STYLE
        accent = self.colors.get("accent", "#238ac1")
        light = self.colors.get("accent_light", "#5bc4ec")
        return f"""
            QLabel#CoachAvatar {{ color:#a0d5de; background:#1a3542; border:1px solid #355767; border-radius:12px; font-size:72px; font-weight:800; }}
            QLabel#CoachAttributeName {{ color:#c7d4dc; font-size:15px; border-bottom:1px solid #263742; padding:0 2px; }}
            QLabel#CoachAttributeValue {{ font-size:20px; font-weight:800; border-bottom:1px solid #263742; }}
            QLabel#CoachAttributeValue[level="elite"] {{ color:#67d5a4; }}
            QLabel#CoachAttributeValue[level="good"] {{ color:#dfcf83; }}
            QLabel#CoachAttributeValue[level="low"] {{ color:#91a2b0; }}
            QProgressBar#CoachQuality {{ background:#0a151c; color:#f1f6fa; border:1px solid #304551; border-radius:4px; text-align:center; font-size:13px; }}
            QProgressBar#CoachQuality::chunk {{ background:#326879; border-radius:3px; }}
            QScrollArea#DashboardScroll, QWidget#DashboardContent {{ background:#080d11; border:0; }}
            QFrame#DashboardCard {{ background:#111d26; border:1px solid #2a3b48; border-radius:10px; }}
            QFrame#DashboardStat {{ background:#14232d; border:1px solid #30424e; border-top:2px solid #539da8; border-radius:8px; }}
            QLabel#DashboardValue {{ color:#f1f7fa; font-size:23px; font-weight:800; padding:4px 0; }}
            QLabel#DashboardDay {{ color:#b4c8d3; font-size:14px; font-weight:700; padding:6px 0; }}
            QLabel#DashboardSession {{ border:1px solid #314a5d; border-left:3px solid #67accf; border-radius:5px; background:#192e3d; color:#c4e4f6; font-size:14px; font-weight:700; padding:4px; }}
            QLabel#DashboardSession[category="recovery"] {{ background:#142e29; border-color:#2b5045; border-left-color:#6bc5a5; color:#ade2cd; }}
            QLabel#DashboardSession[category="load"] {{ background:#342b20; border-color:#574633; border-left-color:#d9ac65; color:#f1d29f; }}
            QLabel#DashboardReport {{ color:#c1d0da; font-size:14px; padding:4px 0; }}
            QLabel#DashboardProtection {{ color:#a0cfba; background:#122a24; border:1px solid #2c4e41; border-radius:6px; padding:12px; font-size:14px; }}
            TrainingCenterPage {{ background:#080d11; }}
            QWidget {{ color:#e9eff4; font-family:'Malgun Gothic','Segoe UI'; }}
            QFrame#TrainingHeader {{ background:#0e171e; border:0; border-bottom:1px solid #26353f; border-radius:0; }}
            QLabel#TrainingEyebrow {{ color:{light}; font-size:13px; font-weight:900; }}
            QLabel#TrainingTitle {{ color:white; font-size:22px; font-weight:900; }}
            QLabel#TrainingMuted {{ color:#8fa0ad; font-size:13px; }}
            QLabel#TrainingSummary {{ color:#c7d4dc; font-weight:800; }}
            QFrame#TrainingWorkflow {{ background:#10212a; border:1px solid #2c4655; border-left:4px solid {light}; border-radius:5px; }}
            QLabel#WorkflowTitle {{ color:white; font-size:15px; font-weight:900; }}
            QLabel#WorkflowDetail {{ color:#a9c2d0; font-size:13px; }}
            QPushButton#WorkflowButton {{ color:white; background:{accent}; border:1px solid {light}; border-radius:5px; min-width:140px; min-height:36px; font-weight:900; }}
            QPushButton#WorkflowButton:disabled {{ color:#71818c; background:#18232a; border-color:#34444f; }}
            QTabWidget#TrainingTabs::pane {{ border:0; border-top:1px solid #25333c; background:#080d11; top:-1px; }}
            QTabBar::tab {{ background:#0d151b; color:#7f909b; padding:11px 25px; border:0; border-right:1px solid #25333c; border-bottom:2px solid transparent; font-weight:800; }}
            QTabBar::tab:hover {{ color:#dce5eb; background:#121d24; }}
            QTabBar::tab:selected {{ color:white; background:#121d24; border-bottom:2px solid {light}; }}
            QFrame#TrainingCard, QFrame#TrainingControlPanel {{ background:#0f171d; border:1px solid #273742; border-radius:7px; }}
            QFrame#ScheduleBoard {{ background:#0b1217; border:1px solid #263640; border-radius:7px; }}
            QFrame#ScheduleLegend {{ background:#0e1b22; border:1px solid #21343f; border-radius:5px; }}
            QFrame#TrainingDay {{ background:#101920; border:1px solid #293a45; border-radius:6px; }}
            QFrame#TrainingDay[weekend="true"] {{ background:#11171d; border-color:#3b343b; }}
            QLabel#SectionEyebrow {{ color:{light}; font-size:13px; font-weight:900; letter-spacing:1px; }}
            QLabel#SectionTitle {{ color:#f5f8fa; font-size:17px; font-weight:900; }}
            QLabel#WeekRange {{ color:#b8c6cf; background:#121d24; border:1px solid #2b3b46; border-radius:13px; padding:5px 11px; font-size:13px; font-weight:800; }}
            QLabel#DayName {{ color:#eef4f7; font-size:16px; font-weight:900; }}
            QLabel#DayDate {{ color:#738894; font-size:13px; font-weight:700; padding-bottom:4px; }}
            QLabel#SessionLabel {{ color:#657986; font-size:13px; font-weight:900; }}
            QLabel#LegendRecovery {{ color:#64c7a1; font-size:13px; font-weight:800; }}
            QLabel#LegendSkill {{ color:#69cce5; font-size:13px; font-weight:800; }}
            QLabel#LegendLoad {{ color:#e8ac5b; font-size:13px; font-weight:800; }}
            QLabel#CardTitle {{ color:white; font-size:15px; font-weight:900; }}
            QLabel#FieldLabel {{ color:#a9b7c1; font-size:13px; margin-top:7px; }}
            QLabel#ImpactText {{ color:#b9c8d1; background:#0a1116; border:1px solid #22313a; border-radius:5px; padding:11px; font-size:14px; line-height:1.5; }}
            QLabel#SelectedName {{ color:{light}; font-size:17px; font-weight:900; padding:8px 0; }}
            QLabel#CoachDetail {{ color:#d9e4ea; background:#0b1217; border-left:3px solid {accent}; padding:9px 12px; font-size:13px; }}
            QComboBox,QSpinBox {{ color:white; background:#172129; border:1px solid #344650; border-radius:4px; min-height:31px; padding:3px 8px; }}
            QComboBox:hover,QSpinBox:hover {{ border-color:#587081; }}
            QComboBox#SessionCombo {{ min-height:38px; padding:2px 6px; color:#dce7ed; background:#162129; border:1px solid #30434f; font-size:13px; font-weight:800; }}
            QPushButton#PrimaryButton {{ color:white; background:{accent}; border:1px solid {light}; border-radius:6px; min-height:34px; font-weight:900; padding:2px 14px; }}
            QPushButton#PrimaryButton:hover {{ background:{light}; }}
            QPushButton#SecondaryButton {{ color:#dce6ec; background:#19262f; border:1px solid #3e5665; border-radius:5px; min-height:34px; font-weight:800; padding:2px 12px; }}
            QPushButton#SecondaryButton:hover {{ color:white; border-color:{light}; }}
            QTableWidget#TrainingTable {{ background:#0b1217; alternate-background-color:#0f181e; border:1px solid #273842; gridline-color:#1d2b34; selection-background-color:#1d5269; selection-color:white; outline:0; }}
            QTableWidget#TrainingTable::item {{ padding-left:8px; border-bottom:1px solid #1c2931; }}
            QHeaderView::section {{ color:#899ca8; background:#121c23; border:none; border-right:1px solid #263741; border-bottom:1px solid #31434f; padding:8px; font-size:13px; font-weight:900; }}
        """ + TRAINING_STYLE
