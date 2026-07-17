"""시작 화면, 새 게임 생성, 메인 대시보드 창 구현."""

import sys
from datetime import date, timedelta

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    DEFAULT_START_POINT,
    MANAGER_ABILITIES,
    MANAGER_ABILITY_MAX,
    MANAGER_ABILITY_DESCRIPTIONS,
    MANAGER_POINT_BUDGET,
    MANAGER_STYLES,
    START_POINTS,
    TEAM_COLORS,
    TEAM_DATA_AS_OF,
    TEAM_EMOJIS,
    TEAM_INFO,
    start_point_date,
    start_point_title,
)
from app.constants import APP_TITLE
from app.manager_widgets import AbilitySliderControl, ManagerRadarChart, ManagerStyleCard
from app.styles import GLOBAL_STYLE, START_STYLE, UI_FONT_FAMILY
from app.utils import manager_data_from_save, resource_path
from app.views.league_rank import LeagueRankTab
from app.views.load_game import LoadGameDialog
from app.views.calendar_bar import CalendarBar
from app.views.manager_welcome import ManagerWelcomePage
from app.views.news_center import DailyNewsPage, NewsFeedPage
from app.views.team_manager import MyTeamManager
from app.views.team_roster_preview import TeamRosterPreviewWidget
from database import SaveDatabase, ensure_player_database


class NewGameWizard(QWidget):
    """감독 생성, 구단과 시작 시점 선택을 진행하는 새 게임 마법사."""

    completed = Signal(str, str, dict, str)
    canceled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_team = next(iter(TEAM_COLORS))
        self.club_name = self.base_team
        self.manager_data = {}
        self.selected_style = None
        self.selected_start_point = None
        self._wizard_transitioning = False
        self._wizard_target_index = None
        self._wizard_animation = None

        self.setMinimumSize(1100, 720)
        self.setStyleSheet(START_STYLE)

        layout = QVBoxLayout(self)
        self.wizard_layout = layout
        layout.setContentsMargins(46, 34, 46, 34)
        layout.setSpacing(14)

        self.step_label = QLabel()
        self.step_label.setStyleSheet("color: #42a5f5; font-size: 14px; font-weight: 700;")
        layout.addWidget(self.step_label)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            "color: #fecaca; background-color: #4c1d24; border: 1px solid #7f3540; "
            "border-radius: 7px; padding: 9px 12px; font-weight: bold;"
        )
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._create_profile_page())
        self.pages.addWidget(self._create_style_page())
        self.pages.addWidget(self._create_ability_page())
        self.pages.addWidget(self._create_team_page())
        self.pages.addWidget(self._create_start_point_page())
        self.pages.addWidget(self._create_summary_page())
        self.roster_preview_page_index = self.pages.addWidget(
            self._create_roster_preview_page()
        )
        layout.addWidget(self.pages, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.back_button = QPushButton("취소")
        self.back_button.setObjectName("BackButton")
        self.back_button.setFixedWidth(130)
        self.back_button.clicked.connect(self.go_back)
        buttons.addWidget(self.back_button)

        self.next_button = QPushButton("다음")
        self.next_button.setObjectName("PrimaryButton")
        self.next_button.setFixedWidth(250)
        self.next_button.clicked.connect(self.go_next)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)

        for control in self.ability_controls.values():
            control.setValue(0)
        self.style_description.setText(
            "감독 카드를 선택하면 해당 프리셋으로 시작합니다. "
            "직접 만들려면 아래의 나만의 감독 스타일 생성을 선택하세요."
        )
        self.update_ability_visuals()
        self.update_navigation()

    @staticmethod
    def _page_header(title_text, subtitle_text):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        title = QLabel(title_text)
        title.setFont(QFont(UI_FONT_FAMILY, 27, QFont.Bold))
        layout.addWidget(title)
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(15)
        return page, layout

    def _create_profile_page(self):
        page, layout = self._page_header(
            "감독 프로필",
            "새로운 커리어를 시작할 감독의 기본 정보를 설정하세요.",
        )
        label = QLabel("감독 이름")
        label.setObjectName("FieldLabel")
        layout.addWidget(label)
        self.manager_name_input = QLineEdit()
        self.manager_name_input.setMaxLength(12)
        self.manager_name_input.setPlaceholderText("감독 이름을 입력하세요")
        layout.addWidget(self.manager_name_input)

        age_label = QLabel("감독 나이")
        age_label.setObjectName("FieldLabel")
        layout.addWidget(age_label)
        self.manager_age_spin = QSpinBox()
        self.manager_age_spin.setRange(30, 80)
        self.manager_age_spin.setValue(45)
        self.manager_age_spin.setSuffix("세")
        layout.addWidget(self.manager_age_spin)
        layout.addStretch()
        return page

    def _create_style_page(self):
        page, layout = self._page_header(
            "감독 스타일",
            "선택한 스타일은 초기 능력치 배분과 이후 경기 운영 특성에 사용됩니다.",
        )
        label = QLabel("스타일 프리셋")
        label.setObjectName("FieldLabel")
        layout.addWidget(label)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)
        self.style_buttons = {}
        for style_name, style in MANAGER_STYLES.items():
            image_path = resource_path("image", style["image"])
            button = ManagerStyleCard(
                style_name,
                style["tagline"],
                image_path,
                style.get("focus_x", 0.5),
            )
            button.setToolTip(style["description"])
            button.clicked.connect(
                lambda checked, name=style_name: checked and self.confirm_manager_style(name)
            )
            self.style_group.addButton(button)
            self.style_buttons[style_name] = button
            cards.addWidget(button)
        layout.addLayout(cards)

        self.style_description = QLabel()
        self.style_description.setWordWrap(True)
        self.style_description.setStyleSheet(
            "background-color: #101f31; border: 1px solid #30445c; "
            "border-radius: 10px; color: #d5e0ea; padding: 20px; font-size: 16px;"
        )
        layout.addWidget(self.style_description)

        self.custom_style_button = QPushButton("＋ 나만의 감독 스타일 생성")
        self.custom_style_button.setObjectName("PrimaryButton")
        self.custom_style_button.setMaximumWidth(320)
        self.custom_style_button.clicked.connect(self.start_custom_style)
        custom_row = QHBoxLayout()
        custom_row.addStretch()
        custom_row.addWidget(self.custom_style_button)
        custom_row.addStretch()
        layout.addLayout(custom_row)
        layout.addStretch()
        return page

    def _create_ability_page(self):
        page, layout = self._page_header(
            "감독 능력 설정",
            f"각 능력은 0~{MANAGER_ABILITY_MAX}이며 총 {MANAGER_POINT_BUDGET}포인트를 배분해야 합니다.",
        )
        self.point_label = QLabel()
        self.point_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.point_label)

        level_guide = QLabel(
            "능력 수준  ·  0~5 미숙   |   6~10 보통   |   11~15 우수   |   16~20 특화"
        )
        level_guide.setAlignment(Qt.AlignCenter)
        level_guide.setStyleSheet(
            "color: #bcd1e5; background-color: #10243a; border: 1px solid #29445f; "
            "border-radius: 8px; padding: 10px; font-size: 14px; font-weight: 600;"
        )
        layout.addWidget(level_guide)

        content = QHBoxLayout()
        content.setSpacing(18)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 6, 0)
        controls_layout.setSpacing(9)
        self.ability_controls = {}
        for key, label_text in MANAGER_ABILITIES.items():
            control = AbilitySliderControl(
                label_text,
                MANAGER_ABILITY_DESCRIPTIONS[key],
            )
            control.valueChanged.connect(self.update_ability_visuals)
            controls_layout.addWidget(control)
            self.ability_controls[key] = control
        controls_layout.addStretch()
        scroll.setWidget(controls_widget)
        content.addWidget(scroll, 3)

        self.radar_chart = ManagerRadarChart()
        content.addWidget(self.radar_chart, 2)
        layout.addLayout(content, 1)
        return page

    def _create_team_page(self):
        page, layout = self._page_header(
            "구단 선택",
            "역사, 프런트 성향, 팬 문화와 미디어 규모까지 비교하고 커리어를 시작할 구단을 선택하세요. "
            f"구단·선수 데이터 {TEAM_DATA_AS_OF.replace('-', '.')} 기준.",
        )

        content = QHBoxLayout()
        content.setSpacing(18)

        self.team_list = QListWidget()
        self.team_list.setFixedWidth(260)
        self.team_list.setStyleSheet("""
            QListWidget {
                color: #dbe7f3;
                background-color: #0d1b2a;
                border: 1px solid #263b52;
                border-radius: 10px;
                padding: 7px;
                font-family: 'Noto Sans KR', 'Malgun Gothic';
                font-size: 15px;
                font-weight: 600;
            }
            QListWidget::item { padding: 12px 10px; border-radius: 7px; }
            QListWidget::item:hover { background-color: #162a40; }
            QListWidget::item:selected { background-color: #1976d2; color: white; }
        """)
        for team_name, info in TEAM_INFO.items():
            item = QListWidgetItem(f'{info["emoji"]}  {team_name}\n     {info["city"]}')
            item.setData(Qt.UserRole, team_name)
            item.setSizeHint(QSize(230, 70))
            self.team_list.addItem(item)
        content.addWidget(self.team_list)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.team_detail_frame = QFrame()
        self.team_detail_frame.setObjectName("TeamDetail")
        detail = QVBoxLayout(self.team_detail_frame)
        detail.setContentsMargins(26, 22, 26, 22)
        detail.setSpacing(14)

        heading = QHBoxLayout()
        self.team_emoji_label = QLabel()
        self.team_emoji_label.setFont(QFont("Arial", 42))
        self.team_emoji_label.setFixedWidth(70)
        heading.addWidget(self.team_emoji_label)
        self.team_name_label = QLabel()
        self.team_name_label.setFont(QFont(UI_FONT_FAMILY, 25, QFont.Bold))
        heading.addWidget(self.team_name_label)
        heading.addStretch()
        self.team_roster_preview_button = QPushButton("선수단 미리보기")
        self.team_roster_preview_button.setObjectName("RosterPreviewButton")
        self.team_roster_preview_button.setFixedWidth(170)
        self.team_roster_preview_button.clicked.connect(self.show_team_roster_preview)
        heading.addWidget(self.team_roster_preview_button)
        detail.addLayout(heading)

        detail_columns = QHBoxLayout()
        detail_columns.setSpacing(22)
        info_column = QVBoxLayout()
        info_column.setSpacing(12)
        visual_column = QVBoxLayout()
        visual_column.setSpacing(12)
        detail_columns.addLayout(info_column, 1)
        detail_columns.addLayout(visual_column, 1)
        detail.addLayout(detail_columns)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.team_location_label = QLabel()
        self.team_location_label.setWordWrap(True)
        self.team_location_label.setStyleSheet(
            "background-color: #101f31; border-radius: 8px; padding: 11px; color: #cbd5e1;"
        )
        metrics.addWidget(self.team_location_label, 3)
        self.team_attendance_label = QLabel()
        self.team_attendance_label.setAlignment(Qt.AlignCenter)
        self.team_attendance_label.setStyleSheet(
            "background-color: #101f31; border-radius: 8px; padding: 11px; color: #cbd5e1;"
        )
        metrics.addWidget(self.team_attendance_label, 2)
        info_column.addLayout(metrics)

        facts = QVBoxLayout()
        facts.setSpacing(8)
        self.team_founded_label = QLabel()
        self.team_founded_label.setWordWrap(True)
        self.team_founded_label.setAlignment(Qt.AlignTop)
        self.team_championship_label = QLabel()
        self.team_championship_label.setWordWrap(True)
        self.team_championship_label.setAlignment(Qt.AlignTop)
        self.team_parent_label = QLabel()
        self.team_parent_label.setWordWrap(True)
        self.team_parent_label.setAlignment(Qt.AlignTop)
        for label in (
            self.team_founded_label,
            self.team_championship_label,
            self.team_parent_label,
        ):
            label.setStyleSheet(
                "background-color: #101f31; border: 1px solid #263b52; border-radius: 8px; "
                "padding: 13px; color: #dbe7f3; font-size: 14px;"
            )
            facts.addWidget(label)
        info_column.addLayout(facts)

        goal_title = QLabel("구단 목표")
        goal_title.setObjectName("FieldLabel")
        info_column.addWidget(goal_title)
        self.team_goal_label = QLabel()
        self.team_goal_label.setWordWrap(True)
        self.team_goal_label.setStyleSheet(
            "color: #f8fafc; background-color: #162a40; border: 1px solid #3b82f6; "
            "border-radius: 9px; padding: 15px; font-size: 14px; font-weight: 600;"
        )
        info_column.addWidget(self.team_goal_label)

        description_title = QLabel("구단 소개와 운영 방향")
        description_title.setObjectName("FieldLabel")
        info_column.addWidget(description_title)
        self.team_description_label = QLabel()
        self.team_description_label.setWordWrap(True)
        self.team_description_label.setStyleSheet(
            "color: #d2dee9; background-color: #0d1b2a; border-radius: 8px; "
            "padding: 15px; font-size: 15px; line-height: 1.45;"
        )
        info_column.addWidget(self.team_description_label)

        player_title = QLabel("대표 선수와 전력 내 역할")
        player_title.setObjectName("FieldLabel")
        info_column.addWidget(player_title)
        self.team_player_cards = []
        for _ in range(3):
            player_card = QLabel()
            player_card.setWordWrap(True)
            player_card.setStyleSheet(
                "color: #cbd5e1; background-color: #10243a; border-radius: 8px; "
                "padding: 13px; font-size: 14px;"
            )
            info_column.addWidget(player_card)
            self.team_player_cards.append(player_card)

        culture_title = QLabel("구단 운영 환경  ·  게임 내 성향")
        culture_title.setObjectName("FieldLabel")
        info_column.addWidget(culture_title)
        self.team_front_office_label = QLabel()
        self.team_fan_label = QLabel()
        self.team_social_style_label = QLabel()
        for label in (
            self.team_front_office_label,
            self.team_fan_label,
            self.team_social_style_label,
        ):
            label.setWordWrap(True)
            label.setStyleSheet(
                "color: #cbd5e1; background-color: #0d1b2a; border-radius: 8px; "
                "padding: 13px; font-size: 14px;"
            )
            info_column.addWidget(label)

        self.team_youtube_label = QLabel()
        self.team_youtube_label.setWordWrap(True)
        self.team_youtube_label.setStyleSheet(
            "color: #fff1f2; background-color: #3b1018; border: 1px solid #7f1d2d; "
            "border-radius: 8px; padding: 13px; font-size: 14px; font-weight: 600;"
        )
        info_column.addWidget(self.team_youtube_label)

        interpretation_note = QLabel(
            "※ 프런트·팬·SNS 성향은 실제 인물에 대한 평가가 아니라 게임 플레이를 위한 구단 환경 해석입니다."
        )
        interpretation_note.setWordWrap(True)
        interpretation_note.setStyleSheet("color: #8495a8; font-size: 12px;")
        info_column.addWidget(interpretation_note)

        name_label = QLabel("게임에서 사용할 구단 이름")
        name_label.setObjectName("FieldLabel")
        info_column.addWidget(name_label)
        self.name_input = QLineEdit(self.base_team)
        self.name_input.setMaxLength(20)
        self.name_input.setPlaceholderText("구단 이름을 입력하세요")
        info_column.addWidget(self.name_input)
        info_column.addStretch()

        mascot_title = QLabel("구단 마스코트")
        mascot_title.setObjectName("FieldLabel")
        visual_column.addWidget(mascot_title)
        self.team_mascot_frame = QFrame()
        self.team_mascot_frame.setObjectName("MascotFrame")
        mascot_layout = QVBoxLayout(self.team_mascot_frame)
        mascot_layout.setContentsMargins(18, 18, 18, 18)
        self.team_mascot_label = QLabel()
        self.team_mascot_label.setAlignment(Qt.AlignCenter)
        self.team_mascot_label.setMinimumHeight(460)
        self.team_mascot_label.setWordWrap(True)
        mascot_layout.addWidget(self.team_mascot_label)
        visual_column.addWidget(self.team_mascot_frame)

        self.team_mascot_name_label = QLabel()
        self.team_mascot_name_label.setAlignment(Qt.AlignCenter)
        self.team_mascot_name_label.setWordWrap(True)
        visual_column.addWidget(self.team_mascot_name_label)

        mascot_help = QLabel(
            "구단을 바꾸면 해당 마스코트와 이름이 자동으로 표시됩니다.\n"
            "이미지는 원본 배경을 그대로 사용합니다."
        )
        mascot_help.setAlignment(Qt.AlignCenter)
        mascot_help.setWordWrap(True)
        mascot_help.setStyleSheet(
            "color: #718096; background-color: #0d1b2a; border-radius: 8px; "
            "padding: 12px; font-size: 12px;"
        )
        visual_column.addWidget(mascot_help)
        visual_column.addStretch()

        detail_scroll.setWidget(self.team_detail_frame)
        content.addWidget(detail_scroll, 1)

        layout.addLayout(content, 1)
        self.team_list.currentItemChanged.connect(self.update_team_details)
        self.team_list.setCurrentRow(0)
        return page

    def update_team_details(self, current, previous=None):
        if current is None:
            return
        team_name = current.data(Qt.UserRole)
        info = TEAM_INFO[team_name]
        colors = info["colors"]

        self.selected_base_team = team_name
        self._sync_default_name(team_name)
        self.team_emoji_label.setText(info["emoji"])
        self.team_name_label.setText(team_name)
        self.team_name_label.setStyleSheet(f'color: {colors["accent_light"]};')
        self.team_location_label.setText(
            f'📍 {info["city"]}\n🏟️ {info["stadium"]}'
        )
        self.team_attendance_label.setText(
            f'2026 평균 관중\n약 {info["average_attendance"]:,}명\n7월 9일 전반기 참고치'
        )
        self.team_founded_label.setText(f'창단·계보\n{info["founded"]}')
        self.team_championship_label.setText(f'역대 우승\n{info["championships"]}')
        self.team_parent_label.setText(f'모기업·운영 기반\n{info["parent_company"]}')
        self.team_goal_label.setText(
            f'이번 시즌  ·  {info["season_goal"]}\n\n'
            f'장기 비전  ·  {info["long_term_goal"]}'
        )
        self.team_description_label.setText(info["description"])
        for label, (player_name, player_description) in zip(
            self.team_player_cards, info["featured_players"]
        ):
            label.setText(f"● {player_name}\n{player_description}")
        self.team_front_office_label.setText(
            f'감독·단장·프런트 성향\n{info["manager"]} 감독 · '
            f'{info["general_manager"]} 단장 · {info["front_office_style"]}'
        )
        self.team_fan_label.setText(f'팬 성향\n{info["fan_style"]}')
        self.team_social_style_label.setText(
            f'공식 SNS · Instagram / Facebook / YouTube\n{info["social_style"]}'
        )
        youtube = info["youtube"]
        self.team_youtube_label.setText(
            f'▶ YouTube  {youtube["channel"]}\n'
            f'구독자 약 {youtube["subscribers"] / 10000:.1f}만 명  ·  '
            f'{youtube["as_of"].replace("-", ".")} 기준'
        )
        mascot_path = resource_path("image", "Mascort", info["mascot_image"])
        mascot_pixmap = QPixmap(str(mascot_path)) if mascot_path.exists() else QPixmap()
        if not mascot_pixmap.isNull():
            self.team_mascot_label.setText("")
            self.team_mascot_label.setStyleSheet("background: transparent; border: none;")
            self.team_mascot_label.setPixmap(
                mascot_pixmap.scaled(
                    QSize(380, 520),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.team_mascot_label.setPixmap(QPixmap())
            self.team_mascot_label.setText(
                f'{info["emoji"]}\n\n마스코트 이미지 준비 중\n'
                f'image/Mascort/{info["mascot_image"]}'
            )
            self.team_mascot_label.setStyleSheet(
                "color: #94a3b8; font-size: 14px; font-weight: bold;"
            )
        self.team_mascot_name_label.setText(info["mascot_name"])
        self.team_mascot_name_label.setStyleSheet(
            f'color: {colors["accent_light"]}; background-color: #0d1b2a; '
            "border-radius: 8px; padding: 10px; font-size: 16px; font-weight: bold;"
        )
        self.team_mascot_frame.setStyleSheet(
            f"QFrame#MascotFrame {{ background-color: {colors['bg_dark']}; "
            f"border: 1px solid {colors['accent']}; border-radius: 14px; }}"
        )
        self.team_detail_frame.setStyleSheet(
            f"QFrame#TeamDetail {{ background-color: {colors['card_bg']}; "
            f"border: 2px solid {colors['accent']}; border-radius: 12px; }}"
        )
        self.team_roster_preview_button.setStyleSheet(
            f"QPushButton#RosterPreviewButton {{ color: white; background-color: {colors['accent']}; "
            f"border: 1px solid {colors['accent_light']}; border-radius: 8px; "
            "min-height: 42px; padding: 0 16px; font-size: 14px; font-weight: 700; }} "
            f"QPushButton#RosterPreviewButton:hover {{ background-color: {colors['accent_light']}; }}"
        )

    def _create_roster_preview_page(self):
        self.team_roster_preview = TeamRosterPreviewWidget(
            self.base_team,
            TEAM_COLORS[self.base_team],
        )
        self.team_roster_preview.profile_mode_changed.connect(
            self._set_roster_profile_mode
        )
        return self.team_roster_preview

    def _set_roster_profile_mode(self, active):
        """선수 상세 화면에서는 새 게임 마법사 장식을 숨겨 전체 면적을 사용한다."""
        self.step_label.setVisible(not active)
        self.back_button.setVisible(not active)
        self.next_button.setVisible(False)
        if active:
            self.wizard_layout.setContentsMargins(0, 0, 0, 0)
            self.wizard_layout.setSpacing(0)
        else:
            self.wizard_layout.setContentsMargins(10, 8, 10, 8)
            self.wizard_layout.setSpacing(6)
            self.update_navigation()

    def show_team_roster_preview(self):
        """팝업 없이 새 게임 화면 전체를 선택 구단 선수단으로 전환한다."""
        team_name = self.selected_base_team
        self.team_roster_preview.set_team(team_name, TEAM_COLORS[team_name])
        self.transition_to_page(self.roster_preview_page_index)

    def _create_summary_page(self):
        page, layout = self._page_header(
            "생성 정보 확인",
            "감독과 구단 정보를 확인한 뒤 새 게임을 시작하세요.",
        )
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background-color: #101f31; border: 1px solid #30445c; "
            "border-radius: 9px; color: #e5edf5; padding: 22px; font-size: 14px;"
        )
        layout.addWidget(self.summary_label)
        layout.addStretch()
        return page

    def _create_start_point_page(self):
        page, layout = self._page_header(
            "시작 시점 선택",
            "얼마나 이른 시점부터 선수단을 운영할지 선택하세요. 선택한 시점은 세이브에 저장됩니다.",
        )

        self.start_point_group = QButtonGroup(self)
        self.start_point_group.setExclusive(True)
        self.start_point_buttons = {}

        for start_point, info in START_POINTS.items():
            button = QPushButton(f'{info["title"]}\n{info["description"]}')
            button.setObjectName("StartPointButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked, point=start_point: checked
                and self.select_start_point(point)
            )
            self.start_point_group.addButton(button)
            self.start_point_buttons[start_point] = button
            layout.addWidget(button)

        guide = QLabel(
            "※ 현재는 시즌 진행 기준점으로 저장되며, 실제 일정 날짜는 이후 일정 시스템과 연결됩니다."
        )
        guide.setWordWrap(True)
        guide.setStyleSheet("color: #8495a8; font-size: 13px; padding-top: 9px;")
        layout.addWidget(guide)
        layout.addStretch()
        return page

    def select_start_point(self, start_point):
        self.selected_start_point = start_point
        self.start_point_buttons[start_point].setChecked(True)
        self.clear_error()

    def confirm_manager_style(self, style_name):
        answer = QMessageBox.question(
            self,
            "감독 스타일 선택",
            f"{style_name} 감독의 스타일로 진행하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.style_group.setExclusive(False)
            self.style_buttons[style_name].setChecked(False)
            self.style_group.setExclusive(True)
            return
        self.clear_error()
        self.select_manager_style(style_name)
        self.transition_to_page(2)

    def select_manager_style(self, style_name):
        self.selected_style = style_name
        self.style_buttons[style_name].setChecked(True)
        self.apply_style_preset(style_name)

    def start_custom_style(self):
        self.clear_error()
        self.selected_style = "나만의 스타일"
        self.style_group.setExclusive(False)
        for button in self.style_buttons.values():
            button.setChecked(False)
        self.style_group.setExclusive(True)
        for control in self.ability_controls.values():
            control.setValue(0)
        self.update_ability_visuals()
        self.transition_to_page(2)

    def apply_style_preset(self, style_name):
        style = MANAGER_STYLES[style_name]
        self.style_description.setText(style["description"])
        for key, value in style["abilities"].items():
            self.ability_controls[key].setValue(value)
        self.update_ability_visuals()

    def update_ability_visuals(self, _value=None):
        abilities = {
            key: control.value()
            for key, control in self.ability_controls.items()
        }
        used = sum(abilities.values())
        remaining = MANAGER_POINT_BUDGET - used
        color = "#7dd3fc" if remaining == 0 else "#ff8a8a"
        self.point_label.setText(f"사용 {used} / {MANAGER_POINT_BUDGET} · 남은 포인트 {remaining}")
        self.point_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.radar_chart.set_abilities(abilities)

    def _sync_default_name(self, team_name):
        previous_team = self.base_team
        if not self.name_input.text().strip() or self.name_input.text().strip() == previous_team:
            self.name_input.setText(team_name)
        self.base_team = team_name

    def go_back(self):
        index = self.pages.currentIndex()
        if index == self.roster_preview_page_index:
            self.clear_error()
            self.transition_to_page(3)
            return
        if index == 0:
            self.canceled.emit()
            return
        self.clear_error()
        self.transition_to_page(index - 1)

    def go_next(self):
        index = self.pages.currentIndex()
        self.clear_error()
        if not self.validate_page(index):
            return
        if index == 5:
            self.accept_game()
            return
        if index == 4:
            self.update_summary()
        self.transition_to_page(index + 1)

    def transition_to_page(self, target_index):
        """새 게임 단계 이동을 페이드 아웃과 페이드 인으로 연결한다."""
        if self._wizard_transitioning or target_index == self.pages.currentIndex():
            return
        self._wizard_transitioning = True
        self._wizard_target_index = target_index
        self.back_button.setEnabled(False)
        self.next_button.setEnabled(False)

        effect = QGraphicsOpacityEffect(self.pages)
        self.pages.setGraphicsEffect(effect)
        self._wizard_animation = QPropertyAnimation(effect, b"opacity", self)
        self._wizard_animation.setDuration(150)
        self._wizard_animation.setStartValue(1.0)
        self._wizard_animation.setEndValue(0.0)
        self._wizard_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._wizard_animation.finished.connect(self._fade_in_wizard_page)
        self._wizard_animation.start()

    def _fade_in_wizard_page(self):
        self.pages.setGraphicsEffect(None)
        self.pages.setCurrentIndex(self._wizard_target_index)
        self.update_navigation()

        effect = QGraphicsOpacityEffect(self.pages)
        self.pages.setGraphicsEffect(effect)
        self._wizard_animation = QPropertyAnimation(effect, b"opacity", self)
        self._wizard_animation.setDuration(220)
        self._wizard_animation.setStartValue(0.0)
        self._wizard_animation.setEndValue(1.0)
        self._wizard_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._wizard_animation.finished.connect(self._finish_wizard_transition)
        self._wizard_animation.start()

    def _finish_wizard_transition(self):
        self.pages.setGraphicsEffect(None)
        self._wizard_animation = None
        self._wizard_target_index = None
        self._wizard_transitioning = False
        self.back_button.setEnabled(True)
        self.next_button.setEnabled(True)

    def validate_page(self, index):
        if index == 0 and not self.manager_name_input.text().strip():
            self.show_error("감독 이름을 입력해 주세요.")
            self.manager_name_input.setFocus()
            return False
        if index == 2:
            used = sum(control.value() for control in self.ability_controls.values())
            if used != MANAGER_POINT_BUDGET:
                self.show_error(
                    f"감독 능력치는 정확히 {MANAGER_POINT_BUDGET}포인트를 사용해야 합니다."
                )
                return False
        if index == 3 and not self.name_input.text().strip():
            self.show_error("구단 이름을 입력해 주세요.")
            self.name_input.setFocus()
            return False
        if index == 4 and self.selected_start_point is None:
            self.show_error("게임을 시작할 CAMP 시점을 선택해 주세요.")
            return False
        return True

    def show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()

    def clear_error(self):
        self.error_label.clear()
        self.error_label.hide()

    def update_summary(self):
        abilities = " · ".join(
            f"{label} {self.ability_controls[key].value()}"
            for key, label in MANAGER_ABILITIES.items()
        )
        self.summary_label.setText(
            f"감독  {self.manager_name_input.text().strip()} ({self.manager_age_spin.value()}세)\n"
            f"스타일  {self.selected_style}\n\n"
            f"{abilities}\n\n"
            f"기준 구단  {self.selected_base_team}\n"
            f"구단 이름  {self.name_input.text().strip()}\n"
            f"시작 시점  {start_point_title(self.selected_start_point)}"
        )

    def update_navigation(self):
        index = self.pages.currentIndex()
        if index == self.roster_preview_page_index:
            self.wizard_layout.setContentsMargins(10, 8, 10, 8)
            self.wizard_layout.setSpacing(6)
            self.step_label.setVisible(True)
            self.step_label.setText("TEAM ROSTER PREVIEW  ·  2025.10.31")
            self.back_button.setText("구단 선택으로")
            self.back_button.setVisible(True)
            self.next_button.setVisible(False)
            return
        self.wizard_layout.setContentsMargins(46, 34, 46, 34)
        self.wizard_layout.setSpacing(14)
        self.step_label.setVisible(True)
        self.step_label.setText(f"NEW GAME  ·  {index + 1} / 6")
        self.back_button.setText("취소" if index == 0 else "이전")
        self.back_button.setVisible(True)
        next_labels = {
            0: "감독 스타일 선택",
            1: "나만의 감독 스타일 만들기",
            2: "구단 선택으로",
            3: "시작 시점 선택",
            4: "최종 정보 확인",
            5: "게임 생성",
        }
        self.next_button.setText(next_labels[index])
        self.next_button.setVisible(index != 1)

    def accept_game(self):
        self.base_team = self.selected_base_team
        self.club_name = self.name_input.text().strip()
        self.manager_data = {
            "manager_name": self.manager_name_input.text().strip(),
            "manager_age": self.manager_age_spin.value(),
            "manager_style": self.selected_style,
            **{key: control.value() for key, control in self.ability_controls.items()},
        }
        self.completed.emit(
            self.base_team,
            self.club_name,
            self.manager_data,
            self.selected_start_point or DEFAULT_START_POINT,
        )


class StartWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.game_window = None
        self._start_transitioning = False
        self._start_target_widget = None
        self._start_animation = None
        ensure_player_database()
        self.save_database = SaveDatabase()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 720)
        self.resize(1400, 880)

        self.start_stack = QStackedWidget()
        self.start_stack.setObjectName("StartRoot")
        self.setCentralWidget(self.start_stack)
        self.setStyleSheet(START_STYLE)

        self.home_page = QWidget()
        self.home_page.setObjectName("StartRoot")
        self.start_stack.addWidget(self.home_page)

        outer = QHBoxLayout(self.home_page)
        outer.setContentsMargins(70, 60, 70, 60)
        outer.addStretch()

        card = QFrame()
        card.setObjectName("StartCard")
        card.setMaximumWidth(600)
        card.setMinimumWidth(520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(62, 58, 62, 58)
        card_layout.setSpacing(14)

        badge = QLabel("KOREA BASEBALL MANAGEMENT")
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("color: #42a5f5; font-size: 14px; font-weight: 700;")
        card_layout.addWidget(badge)

        title = QLabel(APP_TITLE)
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 34, QFont.Bold))
        card_layout.addWidget(title)

        subtitle = QLabel("당신의 선택으로 완성되는 한 시즌")
        subtitle.setObjectName("Subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(35)

        new_button = QPushButton("새로 생성")
        new_button.setObjectName("PrimaryButton")
        new_button.clicked.connect(self.create_new_game)
        card_layout.addWidget(new_button)

        load_button = QPushButton("불러오기")
        load_button.clicked.connect(self.show_load_game)
        card_layout.addWidget(load_button)

        option_button = QPushButton("옵션")
        option_button.clicked.connect(self.show_options)
        card_layout.addWidget(option_button)
        card_layout.addStretch()

        version = QLabel("PRE-SEASON BUILD 0.1")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #718399; font-size: 13px;")
        card_layout.addWidget(version)

        outer.addWidget(card)
        outer.addStretch()

    def create_new_game(self):
        if hasattr(self, "new_game_wizard"):
            self.start_stack.removeWidget(self.new_game_wizard)
            self.new_game_wizard.deleteLater()

        self.new_game_wizard = NewGameWizard(self)
        self.new_game_wizard.canceled.connect(self.show_home)
        self.new_game_wizard.completed.connect(self.finish_new_game)
        self.start_stack.addWidget(self.new_game_wizard)
        self.transition_start_widget(self.new_game_wizard)

    def show_home(self):
        if self.isVisible():
            self.transition_start_widget(self.home_page)
        else:
            self._show_home_immediately()

    def _show_home_immediately(self):
        if self._start_animation is not None:
            self._start_animation.stop()
        self.start_stack.setGraphicsEffect(None)
        self.start_stack.setCurrentWidget(self.home_page)
        self._start_animation = None
        self._start_target_widget = None
        self._start_transitioning = False

    def transition_start_widget(self, target_widget):
        """시작 홈과 새 게임 화면 사이를 부드럽게 전환한다."""
        if target_widget is self.start_stack.currentWidget() or self._start_transitioning:
            return
        self._start_transitioning = True
        self._start_target_widget = target_widget

        effect = QGraphicsOpacityEffect(self.start_stack)
        self.start_stack.setGraphicsEffect(effect)
        self._start_animation = QPropertyAnimation(effect, b"opacity", self)
        self._start_animation.setDuration(160)
        self._start_animation.setStartValue(1.0)
        self._start_animation.setEndValue(0.0)
        self._start_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._start_animation.finished.connect(self._fade_in_start_widget)
        self._start_animation.start()

    def _fade_in_start_widget(self):
        self.start_stack.setGraphicsEffect(None)
        self.start_stack.setCurrentWidget(self._start_target_widget)

        effect = QGraphicsOpacityEffect(self.start_stack)
        self.start_stack.setGraphicsEffect(effect)
        self._start_animation = QPropertyAnimation(effect, b"opacity", self)
        self._start_animation.setDuration(230)
        self._start_animation.setStartValue(0.0)
        self._start_animation.setEndValue(1.0)
        self._start_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._start_animation.finished.connect(self._finish_start_transition)
        self._start_animation.start()

    def _finish_start_transition(self):
        self.start_stack.setGraphicsEffect(None)
        self._start_animation = None
        self._start_target_widget = None
        self._start_transitioning = False

    def finish_new_game(self, base_team, club_name, manager_data, start_point):
        initial_date = start_point_date(start_point)
        self.game_window = MainWindow(
            base_team,
            club_name,
            start_window=self,
            save_database=self.save_database,
            save_id=None,
            manager_data=manager_data,
            start_point=start_point,
            current_date=initial_date,
            show_welcome=True,
        )
        self._show_home_immediately()
        self.game_window.show()
        self.close()

    def show_load_game(self):
        # 실행 중 구버전 세이브 DB가 복원되어도 불러오기 전에 최신 스키마로 보정한다.
        self.save_database.initialize()
        saves = self.save_database.list_saves()
        if not saves:
            QMessageBox.information(
                self,
                "불러오기",
                "아직 저장된 게임이 없습니다.\n새로 생성을 눌러 첫 구단을 만들어 주세요.",
            )
            return

        dialog = LoadGameDialog(saves, self.save_database, self)
        if dialog.exec() != QDialog.Accepted:
            return

        save = self.save_database.get_save(dialog.selected_save_id)
        if save is None:
            QMessageBox.warning(self, "불러오기 실패", "저장 정보를 찾을 수 없습니다.")
            return

        self.game_window = MainWindow(
            save["base_team"],
            save["club_name"],
            start_window=self,
            save_database=self.save_database,
            save_id=save["id"],
            manager_data=manager_data_from_save(save),
            start_point=save.get("start_point", DEFAULT_START_POINT),
            current_date=save.get("current_date"),
        )
        self.game_window.show()
        self.close()

    def show_options(self):
        QMessageBox.information(
            self,
            "옵션",
            "화면, 사운드, 게임 진행 옵션은 다음 단계에서 추가됩니다.",
        )


class MainWindow(QMainWindow):
    def __init__(
        self,
        base_team,
        club_name=None,
        start_window=None,
        save_database=None,
        save_id=None,
        manager_data=None,
        start_point=DEFAULT_START_POINT,
        current_date=None,
        show_welcome=False,
    ):
        super().__init__()
        self.selected_team = base_team
        self.club_name = club_name or base_team
        self.start_window = start_window
        self.save_database = save_database or SaveDatabase()
        self.save_id = save_id
        self.manager_data = manager_data or {
            "manager_name": "무명 감독",
            "manager_age": 45,
            "manager_style": "염경엽",
        }
        self.start_point = start_point
        if isinstance(current_date, str):
            self.current_date = date.fromisoformat(current_date)
        else:
            self.current_date = current_date or start_point_date(start_point)
        self.show_welcome = show_welcome
        self._is_transitioning = False
        self._fade_animation = None
        self._content_transitioning = False
        self._content_target_index = None
        self._content_animation = None
        self.colors = TEAM_COLORS[base_team]

        self.setWindowTitle(f"{APP_TITLE} - {self.club_name}")
        self.resize(1400, 880)

        self.root_stack = QStackedWidget()
        self.setCentralWidget(self.root_stack)

        self.welcome_page = ManagerWelcomePage(
            self.club_name,
            self.selected_team,
            self.manager_data,
            self.start_point,
            TEAM_INFO[self.selected_team],
            self.colors,
        )
        self.welcome_page.continue_requested.connect(self.open_dashboard)
        self.root_stack.addWidget(self.welcome_page)

        self.main_widget = QWidget()
        self.root_stack.addWidget(self.main_widget)

        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.calendar_bar = CalendarBar(self.current_date, self.colors, self.club_name)
        self.calendar_bar.next_day_requested.connect(self.advance_to_next_day)
        main_layout.addWidget(self.calendar_bar)

        dashboard_body = QWidget()
        body_layout = QHBoxLayout(dashboard_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        main_layout.addWidget(dashboard_body, 1)

        self.sidebar = self.create_sidebar()
        body_layout.addWidget(self.sidebar)

        self.content_stack = QStackedWidget()
        self.league_home = LeagueRankTab(self.colors, self.selected_team)
        self.content_stack.addWidget(self.league_home)

        appointment_date = start_point_date(self.start_point)
        self.news_feed = NewsFeedPage(
            self.club_name,
            self.selected_team,
            self.manager_data,
            self.start_point,
            appointment_date,
            TEAM_INFO[self.selected_team],
            self.colors,
        )
        self.content_stack.addWidget(self.news_feed)

        self.daily_news = DailyNewsPage(
            self.club_name,
            self.manager_data,
            self.start_point,
            appointment_date,
            self.colors,
            self.save_database,
            self.save_id,
        )
        self.daily_news.unread_count_changed.connect(self.update_daily_news_badge)
        self.content_stack.addWidget(self.daily_news)
        self.news_feed.set_game_date(self.current_date)
        self.daily_news.set_game_date(self.current_date)

        self.my_team_manager = MyTeamManager(
            self.selected_team,
            self,
            display_name=self.club_name,
        )
        self.content_stack.addWidget(self.my_team_manager)
        body_layout.addWidget(self.content_stack)

        self.apply_team_theme()
        self.root_stack.setCurrentWidget(
            self.welcome_page if self.show_welcome else self.main_widget
        )

    def open_dashboard(self):
        """부임 뉴스에서 대시보드로 부드럽게 전환한다."""
        if self._is_transitioning:
            return
        self._is_transitioning = True

        fade_effect = QGraphicsOpacityEffect(self.welcome_page)
        self.welcome_page.setGraphicsEffect(fade_effect)
        self._fade_animation = QPropertyAnimation(fade_effect, b"opacity", self)
        self._fade_animation.setDuration(260)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade_animation.finished.connect(self._show_dashboard_with_fade)
        self._fade_animation.start()

    def _show_dashboard_with_fade(self):
        self.welcome_page.setGraphicsEffect(None)
        self.root_stack.setCurrentWidget(self.main_widget)
        self.switch_page(0)

        fade_effect = QGraphicsOpacityEffect(self.main_widget)
        self.main_widget.setGraphicsEffect(fade_effect)
        self._fade_animation = QPropertyAnimation(fade_effect, b"opacity", self)
        self._fade_animation.setDuration(340)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.finished.connect(self._finish_dashboard_transition)
        self._fade_animation.start()

    def _finish_dashboard_transition(self):
        self.main_widget.setGraphicsEffect(None)
        self._fade_animation = None
        self._is_transitioning = False

    def create_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(9, 12, 9, 12)
        layout.setSpacing(4)

        logo = QLabel(TEAM_EMOJIS.get(self.selected_team, "🏟️"))
        logo.setFont(QFont("Arial", 30))
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        team_label = QLabel(self.club_name)
        team_label.setWordWrap(True)
        team_label.setFont(QFont(UI_FONT_FAMILY, 15, QFont.Bold))
        team_label.setAlignment(Qt.AlignCenter)
        team_label.setStyleSheet(f"color: {self.colors['accent_light']}; margin-top: 2px;")
        layout.addWidget(team_label)

        base_label = QLabel(f"기준 구단 · {self.selected_team}")
        base_label.setAlignment(Qt.AlignCenter)
        base_label.setStyleSheet("color: #748396; font-size: 12px;")
        layout.addWidget(base_label)

        manager_label = QLabel(
            f'{self.manager_data["manager_name"]} 감독  ·  '
            f'{self.manager_data["manager_style"]}'
        )
        manager_label.setWordWrap(True)
        manager_label.setAlignment(Qt.AlignCenter)
        manager_label.setStyleSheet("color: #98a7b7; font-size: 12px; padding: 5px 0 9px 0;")
        layout.addWidget(manager_label)

        self.btn_home = QPushButton("▣  수신함")
        self.btn_home.setCheckable(True)
        self.btn_home.setChecked(True)
        self.btn_home.clicked.connect(lambda: self.switch_page(0))
        layout.addWidget(self.btn_home)

        self.btn_news = QPushButton("▤  구단 뉴스")
        self.btn_news.setCheckable(True)
        self.btn_news.clicked.connect(lambda: self.switch_page(1))
        layout.addWidget(self.btn_news)

        self.btn_daily_news = QPushButton("▦  주요 일정")
        self.btn_daily_news.setCheckable(True)
        self.btn_daily_news.clicked.connect(lambda: self.switch_page(2))
        layout.addWidget(self.btn_daily_news)

        self.btn_manage = QPushButton("♟  선수단")
        self.btn_manage.setCheckable(True)
        self.btn_manage.clicked.connect(lambda: self.switch_page(3))
        layout.addWidget(self.btn_manage)

        for title in (
            "⌁  전술",
            "◉  데이터 센터",
            "♟  스태프",
            "▲  훈련",
            "✚  의료 센터",
            "⌕  스카우트",
            "⇄  이적",
            "▰  구단 정보",
            "₩  재정",
        ):
            placeholder = QPushButton(title)
            placeholder.setProperty("placeholder", True)
            placeholder.setToolTip("후속 개발에서 구현될 메뉴입니다.")
            layout.addWidget(placeholder)
        layout.addStretch()

        self.btn_save = QPushButton("▣  게임 저장")
        self.btn_save.setObjectName("SaveButton")
        self.btn_save.clicked.connect(lambda: self.save_game())
        layout.addWidget(self.btn_save)

        self.btn_start = QPushButton("↩  시작 화면")
        self.btn_start.setObjectName("StartButton")
        self.btn_start.clicked.connect(self.return_to_start)
        layout.addWidget(self.btn_start)
        return sidebar

    def advance_to_next_day(self):
        """게임 날짜와 세션 화면만 갱신하며 DB 저장은 보류한다."""
        self.current_date += timedelta(days=1)
        self.calendar_bar.set_game_date(self.current_date, animated=True)
        self.news_feed.set_game_date(self.current_date)
        self.daily_news.set_game_date(self.current_date)

    def update_daily_news_badge(self, unread_count):
        text = "▦  주요 일정"
        if unread_count:
            text += f"  ({unread_count})"
        self.btn_daily_news.setText(text)

    def save_game(self, show_message=True):
        if self.save_id is None:
            self.save_id = self.save_database.create_save(
                self.club_name,
                self.selected_team,
                self.manager_data,
                self.start_point,
                self.current_date.isoformat(),
            )
        else:
            self.save_database.update_club_info(
                self.save_id,
                self.club_name,
                self.selected_team,
            )
            self.save_database.update_game_date(
                self.save_id,
                self.current_date.isoformat(),
            )
        self.daily_news.persist(self.save_id)
        if show_message:
            QMessageBox.information(self, "게임 저장", "구단 정보가 저장되었습니다.")

    def return_to_start(self):
        """현재 게임 창을 닫고 최초 시작 화면으로 돌아간다."""
        if self.start_window is None:
            self.start_window = StartWindow()
        self.start_window.game_window = None
        self.start_window.show_home()
        self.start_window.show()
        self.start_window.raise_()
        self.start_window.activateWindow()
        self.close()

    def closeEvent(self, event):
        """명시적으로 저장하지 않은 진행 상황은 DB에 기록하지 않는다."""
        super().closeEvent(event)

    def switch_page(self, page_index):
        if page_index == self.content_stack.currentIndex():
            self._apply_content_page(page_index)
            return
        if self._content_transitioning:
            return

        self._content_transitioning = True
        self._content_target_index = page_index
        effect = QGraphicsOpacityEffect(self.content_stack)
        self.content_stack.setGraphicsEffect(effect)
        self._content_animation = QPropertyAnimation(effect, b"opacity", self)
        self._content_animation.setDuration(140)
        self._content_animation.setStartValue(1.0)
        self._content_animation.setEndValue(0.0)
        self._content_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._content_animation.finished.connect(self._fade_in_content_page)
        self._content_animation.start()

    def _fade_in_content_page(self):
        self.content_stack.setGraphicsEffect(None)
        self.content_stack.setCurrentIndex(self._content_target_index)
        self._apply_content_page(self._content_target_index)

        effect = QGraphicsOpacityEffect(self.content_stack)
        self.content_stack.setGraphicsEffect(effect)
        self._content_animation = QPropertyAnimation(effect, b"opacity", self)
        self._content_animation.setDuration(210)
        self._content_animation.setStartValue(0.0)
        self._content_animation.setEndValue(1.0)
        self._content_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._content_animation.finished.connect(self._finish_content_transition)
        self._content_animation.start()

    def _finish_content_transition(self):
        self.content_stack.setGraphicsEffect(None)
        self._content_animation = None
        self._content_target_index = None
        self._content_transitioning = False

    def _apply_content_page(self, page_index):
        self.btn_home.setChecked(page_index == 0)
        self.btn_news.setChecked(page_index == 1)
        self.btn_daily_news.setChecked(page_index == 2)
        self.btn_manage.setChecked(page_index == 3)
        if page_index == 3:
            self.sidebar.hide()
            self.my_team_manager.refresh_all()
        else:
            self.sidebar.show()

    def apply_team_theme(self):
        c = self.colors
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {c['bg_dark']}; }}
            QWidget#Sidebar {{
                background-color: #151a20;
                border-right: 1px solid #3a4551;
            }}
            QLabel {{ color: {c['text']}; font-family: 'Noto Sans KR', 'Malgun Gothic'; }}
            QWidget#Sidebar QPushButton {{
                background-color: transparent;
                color: #9ca3af;
                border: 1px solid transparent;
                min-height: 35px;
                padding: 7px 12px;
                text-align: left;
                font-family: 'Noto Sans KR', 'Malgun Gothic';
                font-size: 14px;
                border-radius: 5px;
                font-weight: 600;
            }}
            QWidget#Sidebar QPushButton:hover {{
                background-color: {c['bg_dark']};
                color: {c['accent_light']};
            }}
            QWidget#Sidebar QPushButton:checked {{ background-color: {c['accent']}; color: white; }}
            QWidget#Sidebar QPushButton[placeholder="true"] {{ color: #83909e; }}
            QWidget#Sidebar QPushButton[placeholder="true"]:hover {{ color: {c['accent_light']}; border-left: 2px solid {c['accent']}; }}
            QTableWidget {{
                background-color: {c['card_bg']};
                border: 1px solid #1e293b;
                gridline-color: #1e293b;
                border-radius: 4px;
            }}
        """)


def run():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setFont(QFont(UI_FONT_FAMILY, 11))
    app.setStyleSheet(GLOBAL_STYLE)
    start_window = StartWindow()
    start_window.show()
    return app.exec()
