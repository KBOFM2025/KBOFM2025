"""시작 화면, 새 게임 생성, 메인 대시보드 창 구현."""

import traceback
from datetime import date, timedelta
from time import monotonic

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QFont,
    QPixmap,
)
from PySide6.QtWidgets import (
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
from app.styles import START_STYLE, UI_FONT_FAMILY
from app.transitions import FadeStackTransition
from app.utils import manager_data_from_save, resource_path
from app.views.league_rank import LeagueRankTab
from app.views.load_game import LoadGameDialog
from app.views.calendar_bar import CalendarBar
from app.views.day_advance_overlay import DayAdvanceOverlay
from app.views.board_vision import BoardVisionPage
from app.views.manager_welcome import ManagerWelcomePage
from app.views.manager_event import ManagerEventPage
from app.views.player_meeting import PlayerMeetingPage
from app.views.trade_negotiation import TradeNegotiationPage
from app.views.news_center import DailyNewsPage, NewsFeedPage
from app.views.season_calendar import SeasonCalendarPage
from app.views.team_manager import MyTeamManager
from app.views.team_roster_preview import TeamRosterPreviewWidget
from app.views.player_search import PlayerSearchPage
from app.views.team_manage.player_profile import PlayerProfilePage
from app.views.team_manage.set_lineup import SetLineupTab
from app.views.club_info import ClubInfoPage
from app.views.club_squad import ClubSquadPage
from app.views.second_draft import SecondDraftPage
from app.services.day_advance_worker import DayAdvanceWorker
from app.services.manager_events import ManagerEventService
from app.services.second_draft import SecondDraftService
from app.services.team_ai_processor import TeamAIDecisionWorker
from app.ai.local_model import stop_owned_local_ai_server
from database import (
    PLAYERS_DB_PATH,
    SaveDatabase,
    ensure_final_roster_assignments,
    ensure_2025_draft_players,
    ensure_player_database,
)


class ClickableLabel(QLabel):
    """버튼처럼 동작하지만 긴 구단명 줄바꿈을 유지하는 라벨."""

    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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
                font-family: 'Malgun Gothic', 'Segoe UI';
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
    def __init__(self, save_database=None, database_ready=False):
        super().__init__()
        self.game_window = None
        self._start_transitioning = False
        self._start_target_widget = None
        self._start_animation = None
        if not database_ready:
            ensure_player_database()
        self.save_database = save_database or SaveDatabase()
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

        self.new_button = QPushButton("새로 생성")
        self.new_button.setObjectName("PrimaryButton")
        self.new_button.clicked.connect(self.create_new_game)
        card_layout.addWidget(self.new_button)

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
        if self._start_transitioning:
            return
        existing_wizard = getattr(self, "new_game_wizard", None)
        if existing_wizard is not None and self.start_stack.currentWidget() is existing_wizard:
            return
        self.new_button.setEnabled(False)
        if hasattr(self, "new_game_wizard"):
            self.start_stack.removeWidget(self.new_game_wizard)
            self.new_game_wizard.deleteLater()

        self.new_game_wizard = NewGameWizard(self)
        self.new_game_wizard.canceled.connect(self.show_home)
        self.new_game_wizard.completed.connect(self.finish_new_game)
        self.start_stack.addWidget(self.new_game_wizard)
        self.transition_start_widget(self.new_game_wizard)

    def show_home(self):
        self.new_button.setEnabled(True)
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
        self.new_button.setEnabled(True)

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
        if self.start_stack.currentWidget() is self.home_page:
            self.new_button.setEnabled(True)

    def finish_new_game(self, base_team, club_name, manager_data, start_point):
        initial_date = start_point_date(start_point)
        save_id = self.save_database.create_save(
            club_name,
            base_team,
            manager_data,
            start_point,
            initial_date.isoformat(),
        )
        _player_db_path, opponent_count = self.save_database.create_manager_player_database(
            save_id, manager_data.get("manager_name", "감독"), base_team
        )
        manager_data = dict(manager_data)
        manager_data["opponent_player_count"] = opponent_count
        self.game_window = MainWindow(
            base_team,
            club_name,
            start_window=self,
            save_database=self.save_database,
            save_id=save_id,
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

        try:
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
        except Exception as error:
            details = traceback.format_exc()
            print(f"[불러오기 오류]\n{details}", flush=True)
            QMessageBox.critical(
                self,
                "불러오기 실패",
                "저장 데이터는 삭제되지 않았습니다.\n"
                "게임 화면을 준비하는 중 오류가 발생했습니다.\n\n"
                f"{type(error).__name__}: {error}",
            )
            self.game_window = None
            return
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
        save_record = self.save_database.get_save(save_id) if save_id is not None else None
        self.player_db_path = (
            save_record.get("player_db_path")
            if save_record and save_record.get("player_db_path")
            else None
        )
        if self.player_db_path:
            self.save_database.sync_manager_hitter_abilities(self.save_id)
            ensure_final_roster_assignments(self.player_db_path)
            ensure_2025_draft_players(self.player_db_path)
        self._team_ai_worker = None
        self._day_advance_worker = None
        self._day_advance_target = None
        self._day_advance_started_at = 0.0
        self._day_advance_warning = None
        self.last_simulation_summary = None
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
        self._content_transitioning = False
        self._content_target_index = None
        self._content_animation = None
        self._pending_required_action_count = 0
        self.colors = TEAM_COLORS[base_team]

        self.setWindowTitle(f"{APP_TITLE} - {self.club_name}")
        self.resize(1400, 880)

        self.root_stack = QStackedWidget()
        self.root_transition = FadeStackTransition(self.root_stack, self, 180, 280)
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

        self.board_vision_page = BoardVisionPage(
            self.club_name,
            self.manager_data,
            TEAM_INFO[self.selected_team],
            self.colors,
            base_team=self.selected_team,
            gm_objective_defaults=self.save_database.get_gm_objective_defaults(
                self.selected_team
            ),
        )
        self.board_vision_page.restore_state(
            self.save_database.load_governance_state(self.save_id)
        )
        self.board_vision_page.continue_requested.connect(self.finish_board_vision)
        self.root_stack.addWidget(self.board_vision_page)

        self.global_player_profile = PlayerProfilePage(self.colors)
        self.global_player_profile.back_requested.connect(
            self._close_global_player_profile
        )
        self.root_stack.addWidget(self.global_player_profile)

        self.manager_event_service = ManagerEventService(
            self.save_database.db_path,
            self.player_db_path or PLAYERS_DB_PATH,
        )
        # 협상 화면은 루트 스택의 다른 페이지처럼 메인 창 구성 단계에서
        # 한 번만 만들고, 이벤트를 열 때 데이터와 표시 페이지만 바꾼다.
        self.manager_event_page = ManagerEventPage(
            self.colors,
            self.manager_event_service,
            self.save_id,
        )
        self.manager_event_page.back_requested.connect(
            self._close_manager_event
        )
        self.manager_event_page.event_resolved.connect(
            self._manager_event_resolved
        )
        self.root_stack.addWidget(self.manager_event_page)
        self.player_meeting_page = PlayerMeetingPage(
            self.colors,
            self.manager_event_service,
            self.save_id,
        )
        self.player_meeting_page.back_requested.connect(
            self._close_manager_event
        )
        self.player_meeting_page.event_resolved.connect(
            self._manager_event_resolved
        )
        self.root_stack.addWidget(self.player_meeting_page)
        self.trade_negotiation_page = TradeNegotiationPage(
            self.colors,
            self.manager_event_service,
            self.save_id,
        )
        self.trade_negotiation_page.back_requested.connect(
            self._close_manager_event
        )
        self.trade_negotiation_page.event_resolved.connect(
            self._manager_event_resolved
        )
        self.root_stack.addWidget(self.trade_negotiation_page)

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
        appointment_date = start_point_date(self.start_point)
        self.league_home = LeagueRankTab(
            self.colors, self.selected_team, db_path=self.player_db_path,
            save_database=self.save_database, save_id=self.save_id,
            appointment_date=appointment_date,
        )
        self.league_home.board_vision_requested.connect(self.open_board_vision)
        self.league_home.required_action_count_changed.connect(
            self._update_progress_gate
        )
        self.league_home.club_info_requested.connect(
            lambda team_name: self._open_searched_club_info(team_name, 0)
        )
        self.league_home.player_requested.connect(
            lambda player: self._open_full_player_profile(player, return_page=0)
        )
        self.league_home.manager_event_requested.connect(
            self._open_manager_event
        )
        if self.board_vision_page.reviewed:
            self.league_home.mark_board_vision_reviewed()
        self.content_stack.addWidget(self.league_home)

        self.news_feed = NewsFeedPage(
            self.club_name,
            self.selected_team,
            self.manager_data,
            self.start_point,
            appointment_date,
            TEAM_INFO[self.selected_team],
            self.colors,
            self.save_database,
            self.save_id,
        )
        self.news_feed.notification_count_changed.connect(self.update_news_notification_badge)
        self.news_feed.second_draft_requested.connect(
            lambda view: self._open_second_draft(view, 1)
        )
        self.league_home.notification_count_changed.connect(self.update_news_notification_badge)
        self.league_home.news_requested.connect(lambda: self.switch_page(1))
        self.league_home.second_draft_requested.connect(
            lambda view: self._open_second_draft(view, 0)
        )
        self.league_home.squad_requested.connect(lambda: self.switch_page(3))
        self.league_home.calendar_requested.connect(self._open_season_calendar)
        self.league_home.refresh_notifications()
        self.league_home.set_game_date(self.current_date)
        self.news_feed.refresh_news()
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
        self.season_calendar = SeasonCalendarPage(self.colors, self.current_date)
        self.season_calendar.back_requested.connect(self._close_season_calendar)
        self.root_stack.addWidget(self.season_calendar)
        self.content_stack.addWidget(QWidget())
        self.news_feed.set_game_date(self.current_date)
        self.daily_news.set_game_date(self.current_date)

        self.my_team_manager = MyTeamManager(
            self.selected_team,
            self,
            display_name=self.club_name,
            db_path=self.player_db_path,
        )
        self.content_stack.addWidget(self.my_team_manager)

        self.player_search = PlayerSearchPage(
            self.colors,
            self.selected_team,
            self.save_database,
            self.save_id,
            db_path=self.player_db_path,
        )
        self.content_stack.addWidget(self.player_search)
        self.player_search.player_requested.connect(self._open_full_player_profile)
        self.calendar_bar.set_search_entries(TEAM_INFO.keys(), self.player_search.players)
        self.calendar_bar.search_selected.connect(self._open_global_search_result)
        self.calendar_bar.search_submitted.connect(self._open_global_search_page)

        self.tactics_page = SetLineupTab(self.my_team_manager)
        self.content_stack.addWidget(self.tactics_page)

        self.club_info_page = ClubInfoPage(
            self.selected_team,
            self.club_name,
            self.manager_data,
            self.colors,
            db_path=self.player_db_path,
        )
        self.club_info_page.back_requested.connect(self._close_club_info)
        self.club_info_page.squad_requested.connect(self._open_club_squad)
        self.club_info_page.player_requested.connect(
            lambda player, page=self.club_info_page:
            self._open_full_player_profile(player, page)
        )
        self.root_stack.addWidget(self.club_info_page)
        self.club_info_pages = {self.selected_team: self.club_info_page}
        self.club_squad_pages = {}
        self._club_info_return_page = 0
        self.second_draft_page = None

        body_layout.addWidget(self.content_stack)

        self.apply_team_theme()
        self.day_advance_overlay = DayAdvanceOverlay(
            self.colors, self.selected_team, self.root_stack
        )
        self.root_stack.setCurrentWidget(
            self.welcome_page if self.show_welcome else self.main_widget
        )

    def open_board_vision(self):
        """메인 수신함에서 전체 화면 이사회 협상 페이지를 연다."""
        self.root_transition.to_widget(self.board_vision_page)

    def _open_season_calendar(self):
        """메인 레이아웃을 벗어난 전체 화면 일정 페이지를 연다."""
        self._calendar_return_page = self.content_stack.currentIndex()
        self.btn_daily_news.setChecked(True)
        self.season_calendar.set_game_date(self.current_date)
        self.root_transition.to_widget(self.season_calendar)

    def _close_season_calendar(self):
        """일정 페이지를 닫고 기존 메인 콘텐츠로 돌아간다."""
        return_page = getattr(self, "_calendar_return_page", 0)
        self.root_transition.to_widget(
            self.main_widget,
            after_switch=lambda: self.switch_page(return_page),
        )

    def _open_global_search_result(self, result):
        """상단 자동완성에서 선택한 구단 또는 선수로 즉시 이동한다."""
        if result.get("type") == "club":
            self._open_searched_club_info(result["club"])
        elif result.get("type") == "player":
            self._open_full_player_profile(result["player"])

    def _open_global_search_page(self, query):
        """검색어를 전체 결과 페이지에 전달한다."""
        self.player_search.search_text(query)
        self._show_player_search_page()

    def _show_player_search_page(self):
        """진행 중인 콘텐츠 애니메이션과 무관하게 탐색 화면을 연다."""
        if self._content_animation is not None:
            self._content_animation.stop()
        self.content_stack.setGraphicsEffect(None)
        self._content_animation = None
        self._content_target_index = None
        self._content_transitioning = False
        self.content_stack.setCurrentIndex(4)
        self._apply_content_page(4)

    def _open_full_player_profile(self, player, return_widget=None, return_page=None):
        self._player_profile_return_widget = return_widget
        self._player_profile_return_page = (
            self.content_stack.currentIndex()
            if return_widget is None and return_page is None
            else return_page
        )
        self.global_player_profile.set_player(player)
        self.root_transition.to_widget(self.global_player_profile)

    def _close_global_player_profile(self):
        return_widget = getattr(self, "_player_profile_return_widget", None)
        if return_widget is not None:
            self._player_profile_return_widget = None
            self.root_transition.to_widget(return_widget)
            return
        return_page = getattr(self, "_player_profile_return_page", 4)
        self._player_profile_return_page = None
        self.root_transition.to_widget(
            self.main_widget,
            after_switch=lambda: self.switch_page(return_page),
        )

    def _open_manager_event(self, event_id):
        event = self.save_database.get_manager_event(
            self.save_id, int(event_id)
        )
        if event is None:
            QMessageBox.warning(
                self, "구단 업무", "해당 업무를 찾을 수 없습니다."
            )
            return
        if event.get("event_type") == "player_complaint":
            target_page = self.player_meeting_page
        elif event.get("event_type") == "trade_offer":
            target_page = self.trade_negotiation_page
        else:
            target_page = self.manager_event_page
        target_page.save_id = self.save_id
        target_page.set_event(event)
        self.root_stack.setCurrentWidget(target_page)
        self.league_home.refresh_notifications()

    def _close_manager_event(self):
        self.root_stack.setCurrentWidget(self.main_widget)
        self.switch_page(0)

    def _manager_event_resolved(self):
        governance_state = self.save_database.load_governance_state(
            self.save_id
        )
        if governance_state:
            self.board_vision_page.restore_state(governance_state)
        self.league_home.refresh_notifications()
        self.news_feed.refresh_news()
        self.player_search.players = self.player_search._load_players()
        self.player_search.search()
        self.calendar_bar.set_search_entries(
            TEAM_INFO.keys(), self.player_search.players
        )
        self.my_team_manager.refresh_all()
        for page in self.club_squad_pages.values():
            page.refresh_players()

    def _open_club_info(self):
        self._club_info_return_page = self.content_stack.currentIndex()
        self.btn_club_info.setChecked(True)
        self.root_transition.to_widget(self.club_info_page)

    def _open_searched_club_info(self, team_name, return_page=4):
        page = self.club_info_pages.get(team_name)
        if page is None:
            page = ClubInfoPage(
                team_name,
                team_name,
                {"manager_name": TEAM_INFO[team_name]["manager"]},
                TEAM_COLORS[team_name],
                db_path=self.player_db_path,
            )
            page.back_requested.connect(self._close_club_info)
            page.squad_requested.connect(self._open_club_squad)
            page.player_requested.connect(
                lambda player, club_page=page:
                self._open_full_player_profile(player, club_page)
            )
            self.club_info_pages[team_name] = page
            self.root_stack.addWidget(page)
        self._club_info_return_page = return_page
        self.root_transition.to_widget(page)

    def _open_club_squad(self, team_name):
        page = self.club_squad_pages.get(team_name)
        if page is None:
            page = ClubSquadPage(
                team_name, TEAM_COLORS[team_name], db_path=self.player_db_path,
                save_database=self.save_database, save_id=self.save_id,
            )
            page.back_requested.connect(self._close_club_info)
            page.club_info_requested.connect(
                lambda team: self.root_transition.to_widget(
                    self.club_info_pages[team]
                )
            )
            page.player_requested.connect(
                lambda player, squad_page=page: self._open_full_player_profile(
                    player, squad_page
                )
            )
            self.club_squad_pages[team_name] = page
            self.root_stack.addWidget(page)
        else:
            page.refresh_players()
        self.root_transition.to_widget(page)

    def _close_club_info(self):
        return_page = self._club_info_return_page
        self.root_transition.to_widget(
            self.main_widget,
            after_switch=lambda: self.switch_page(return_page),
        )

    def _open_second_draft(self, view="available", return_page=1):
        """명단 발표·결과 소식에서만 2차 드래프트 전체 화면을 연다."""
        if self.save_id is None:
            return
        service = SecondDraftService(
            self.save_database,
            self.save_id,
            self.player_db_path or PLAYERS_DB_PATH,
        )
        state = service.settings()
        if state.get("status") == "not_prepared":
            return
        if state.get("status") != "completed":
            service.set_mode("ai")
        self._second_draft_return_page = return_page
        if self.second_draft_page is None:
            self.second_draft_page = SecondDraftPage(
                self.colors,
                self.save_database,
                self.save_id,
                self.player_db_path or PLAYERS_DB_PATH,
                self.current_date,
            )
            self.second_draft_page.back_requested.connect(
                self._close_second_draft
            )
            self.second_draft_page.player_requested.connect(
                lambda player: self._open_full_player_profile(
                    player, self.second_draft_page
                )
            )
            self.root_stack.addWidget(self.second_draft_page)
        else:
            self.second_draft_page.set_game_date(self.current_date)
        self.second_draft_page.show_view(view)
        self.root_transition.to_widget(self.second_draft_page)

    def _close_second_draft(self):
        self.root_transition.to_widget(
            self.main_widget,
            after_switch=lambda: self.switch_page(
                getattr(self, "_second_draft_return_page", 1)
            ),
        )

    def _refresh_after_second_draft(self):
        """지명 직후 검색·선수단·뉴스를 새 소속 구단 기준으로 갱신한다."""
        self.player_search.players = self.player_search._load_players()
        self.player_search.search()
        self.calendar_bar.set_search_entries(
            TEAM_INFO.keys(), self.player_search.players
        )
        for page in self.club_squad_pages.values():
            page.refresh_players()
        if self.my_team_manager:
            self.my_team_manager.refresh_all()
        self._refresh_news_pages()

    def open_dashboard(self):
        """취임 기사를 확인한 뒤 메인 수신함으로 이동한다."""
        self.root_transition.to_widget(
            self.main_widget,
            after_switch=self._show_initial_inbox,
        )

    def _show_initial_inbox(self):
        self.switch_page(0)
        self._update_progress_gate(len(self.league_home.pending_required_messages()))

    def finish_board_vision(self):
        """협의 완료 상태를 수신함에 표시하고 메인 화면으로 돌아간다."""
        self.board_vision_page.mark_reviewed()
        self.league_home.mark_board_vision_reviewed()
        if self.save_id is None:
            self.save_game(show_message=False)
        self.save_database.save_governance_state(
            self.save_id, self.board_vision_page.export_state()
        )
        self.root_transition.to_widget(
            self.main_widget,
            after_switch=lambda: self.switch_page(0),
        )

    def create_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(184)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        logo = QLabel(TEAM_EMOJIS.get(self.selected_team, "🏟️"))
        logo.setFont(QFont("Arial", 20))
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedHeight(40)
        logo.setObjectName("SidebarCrest")
        layout.addWidget(logo)

        team_label = ClickableLabel(self.club_name)
        team_label.setObjectName("SidebarClubLink")
        team_label.setWordWrap(True)
        team_label.setFont(QFont(UI_FONT_FAMILY, 13, QFont.Bold))
        team_label.setAlignment(Qt.AlignCenter)
        team_label.setCursor(Qt.CursorShape.PointingHandCursor)
        team_label.setToolTip("구단 상세 정보 열기")
        team_label.clicked.connect(self._open_club_info)
        team_label.setStyleSheet(f"color: {self.colors['accent_light']}; padding: 0 8px;")
        layout.addWidget(team_label)

        base_label = QLabel(f"기준 구단 · {self.selected_team}")
        base_label.setAlignment(Qt.AlignCenter)
        base_label.setStyleSheet("color: #74808d; font-size: 10px;")
        layout.addWidget(base_label)

        manager_label = QLabel(
            f'{self.manager_data["manager_name"]} 감독  ·  '
            f'{self.manager_data["manager_style"]}'
        )
        manager_label.setWordWrap(True)
        manager_label.setAlignment(Qt.AlignCenter)
        manager_label.setStyleSheet("color: #98a3ae; font-size: 10px; padding: 3px 8px 10px 8px; border-bottom: 1px solid #303841;")
        layout.addWidget(manager_label)

        club_section = QLabel("구단")
        club_section.setProperty("sidebarSection", True)
        layout.addWidget(club_section)

        self.btn_home = QPushButton("▣  수신함")
        self.btn_home.setCheckable(True)
        self.btn_home.setText("수신함")
        self.btn_home.setChecked(True)
        self.btn_home.clicked.connect(lambda: self.switch_page(0))
        layout.addWidget(self.btn_home)

        self.btn_news = QPushButton("▤  구단 뉴스")
        self.btn_news.setCheckable(True)
        self.btn_news.setText("구단 뉴스")
        self.btn_news.clicked.connect(lambda: self.switch_page(1))
        layout.addWidget(self.btn_news)

        self.btn_daily_news = QPushButton("▦  일정")
        self.btn_daily_news.setCheckable(True)
        self.btn_daily_news.setText("일정")
        self.btn_daily_news.clicked.connect(self._open_season_calendar)
        layout.addWidget(self.btn_daily_news)

        self.btn_manage = QPushButton("♟  선수단")
        self.btn_manage.setCheckable(True)
        self.btn_manage.setText("선수단")
        self.btn_manage.clicked.connect(lambda: self.switch_page(3))
        layout.addWidget(self.btn_manage)

        self.btn_search = QPushButton("⌕  탐색")
        self.btn_search.setCheckable(True)
        self.btn_search.setText("탐색")
        self.btn_search.clicked.connect(lambda: self.switch_page(4))
        layout.addWidget(self.btn_search)

        self.btn_club_info = QPushButton("▰  구단 정보")
        self.btn_club_info.setCheckable(True)
        self.btn_club_info.setText("구단 정보")
        self.btn_club_info.clicked.connect(self._open_club_info)
        layout.addWidget(self.btn_club_info)

        self.btn_tactics = QPushButton("전술")
        self.btn_tactics.setCheckable(True)
        self.btn_tactics.clicked.connect(lambda: self.switch_page(5))
        layout.addWidget(self.btn_tactics)

        for title in (
            "◉  데이터 센터",
            "♟  스태프",
            "▲  훈련",
            "✚  의료 센터",
            "⇄  이적",
            "₩  재정",
        ):
            placeholder = QPushButton(title.split("  ", 1)[-1])
            placeholder.setProperty("placeholder", True)
            placeholder.setEnabled(False)
            placeholder.setToolTip("후속 개발에서 구현될 메뉴입니다.")
            layout.addWidget(placeholder)
        layout.addStretch()

        self.btn_save = QPushButton("▣  게임 저장")
        self.btn_save.setObjectName("SaveButton")
        self.btn_save.setText("게임 저장")
        self.btn_save.clicked.connect(lambda: self.save_game())
        layout.addWidget(self.btn_save)

        self.btn_start = QPushButton("↩  시작 화면")
        self.btn_start.setObjectName("StartButton")
        self.btn_start.setText("시작 화면")
        self.btn_start.clicked.connect(self.return_to_start)
        layout.addWidget(self.btn_start)
        return sidebar

    def advance_to_next_day(self):
        """상단 진행 패널과 함께 다음 날짜 시뮬레이션을 시작한다."""
        pending = self.league_home.pending_required_messages()
        if pending:
            self.switch_page(0)
            message = self.league_home.focus_first_required_message()
            self._update_progress_gate(len(pending))
            QMessageBox.information(
                self,
                "필수 응답 필요",
                "날짜를 진행하기 전에 아래 소식을 처리해야 합니다.\n\n"
                f"{message['headline'] if message else pending[0]['headline']}",
            )
            return
        if (
            self._day_advance_worker is not None
            and self._day_advance_worker.isRunning()
        ):
            return
        target_date = self.current_date + timedelta(days=1)
        if self.save_id is None:
            self.save_game(show_message=False)
        self.calendar_bar.next_button.setEnabled(False)
        self._day_advance_target = target_date
        self._day_advance_started_at = monotonic()
        self._day_advance_warning = None
        self.day_advance_overlay.begin(self.current_date, target_date)
        self._day_advance_worker = DayAdvanceWorker(
            self.save_database,
            self.save_id,
            self.player_db_path or PLAYERS_DB_PATH,
            self.selected_team,
            target_date,
            self,
        )
        self._day_advance_worker.completed.connect(
            self._day_simulation_completed
        )
        self._day_advance_worker.failed.connect(
            self._day_simulation_failed
        )
        self._day_advance_worker.progress.connect(
            self.day_advance_overlay.update_progress
        )
        self._day_advance_worker.start()

    def _wait_for_minimum_day_loading(self, callback):
        """시뮬레이션이 빨라도 진행 화면을 최소 2초 동안 유지한다."""
        elapsed_ms = int(
            (monotonic() - self._day_advance_started_at) * 1000
        )
        QTimer.singleShot(max(0, 2000 - elapsed_ms), callback)

    def _day_simulation_completed(self, summary):
        self.last_simulation_summary = summary
        self._wait_for_minimum_day_loading(
            self._apply_completed_day_advance
        )

    def _day_simulation_failed(self, message):
        target_date = self._day_advance_target
        print(
            f"[리그 시뮬레이션 오류] "
            f"{target_date.isoformat() if target_date else '-'} · {message}",
            flush=True,
        )
        self._wait_for_minimum_day_loading(
            lambda reason=message: self.day_advance_overlay.fail(
                "하루 진행을 완료하지 못했습니다",
                after_hidden=lambda: self._finish_failed_day_advance(reason),
            )
        )

    def _apply_completed_day_advance(self):
        target_date = self._day_advance_target
        if target_date is None:
            return
        self.current_date = target_date
        try:
            SecondDraftService(
                self.save_database,
                self.save_id,
                self.player_db_path or PLAYERS_DB_PATH,
            ).process_date(self.current_date)
        except Exception as error:
            print(
                f"[2차 드래프트 일정 처리 오류] "
                f"{self.current_date.isoformat()} · {error!r}",
                flush=True,
            )
            self._day_advance_warning = (
                "리그 날짜는 정상 진행됐지만 2차 드래프트 처리를 완료하지 "
                f"못했습니다. 다음 날짜 진행 시 자동으로 다시 시도합니다.\n\n{error}"
            )
        self.calendar_bar.set_game_date(self.current_date, animated=True)
        self.news_feed.set_game_date(self.current_date)
        self.daily_news.set_game_date(self.current_date)
        self.league_home.refresh_notifications()
        self.league_home.set_game_date(self.current_date)
        self.season_calendar.set_game_date(self.current_date)
        if self.second_draft_page is not None:
            self.second_draft_page.set_game_date(self.current_date)
        for page in self.club_squad_pages.values():
            page.save_id = self.save_id
            page.refresh_players()
        if self.my_team_manager:
            self.my_team_manager.refresh_all()
        self._start_team_ai_processing()
        self.day_advance_overlay.complete(
            self.current_date,
            after_hidden=self._finish_day_advance_transition,
        )

    def _finish_day_advance_transition(self):
        self.calendar_bar.next_button.setEnabled(True)
        self._day_advance_target = None
        worker = self._day_advance_worker
        self._day_advance_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._day_advance_warning:
            warning = self._day_advance_warning
            self._day_advance_warning = None
            QMessageBox.warning(
                self, "2차 드래프트 일정 처리", warning
            )

    def _finish_failed_day_advance(self, reason):
        self.calendar_bar.next_button.setEnabled(True)
        self._day_advance_target = None
        worker = self._day_advance_worker
        self._day_advance_worker = None
        if worker is not None:
            worker.deleteLater()
        QMessageBox.critical(
            self,
            "리그 진행 오류",
            "다른 구단을 포함한 하루 진행을 완료하지 못했습니다.\n"
            "모든 변경은 취소되었습니다.\n\n"
            f"{reason}",
        )

    def _start_team_ai_processing(self):
        """중요 구단 결정을 백그라운드 Qwen 작업으로 넘겨 날짜 진행을 막지 않는다."""
        if self.save_id is None:
            return
        if self._team_ai_worker is not None and self._team_ai_worker.isRunning():
            print("[상대 구단 Qwen AI] 기존 백그라운드 작업이 진행 중입니다", flush=True)
            return
        self._team_ai_worker = TeamAIDecisionWorker(
            self.save_database.db_path, self.save_id, self
        )
        self._team_ai_worker.processed.connect(self._refresh_news_pages)
        self._team_ai_worker.start()

    def _refresh_news_pages(self, _count=0):
        self.daily_news.set_game_date(self.current_date)
        self.news_feed.set_game_date(self.current_date)
        self.league_home.refresh_notifications()

    def _update_progress_gate(self, required_count):
        self._pending_required_action_count = int(required_count)
        self.calendar_bar.set_progress_blocked(self._pending_required_action_count)
        if self._pending_required_action_count:
            self.btn_home.setToolTip(
                f"날짜 진행 전에 처리할 필수 소식이 {self._pending_required_action_count}건 있습니다."
            )
        else:
            self.btn_home.setToolTip("")

    def update_news_notification_badge(self, unread_count):
        suffix = f"  ({unread_count})" if unread_count else ""
        self.btn_home.setText(f"수신함{suffix}")
        self.btn_news.setText(f"구단 뉴스{suffix}")

    def update_daily_news_badge(self, unread_count):
        text = "일정"
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
        self.news_feed.set_save_id(self.save_id)
        self.league_home.set_save_id(self.save_id)
        self.save_database.save_governance_state(
            self.save_id,
            self.board_vision_page.export_state(),
        )
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
        if self._day_advance_target is not None:
            event.ignore()
            QMessageBox.information(
                self,
                "일정 진행 중",
                "하루 진행이 끝난 뒤 게임을 종료할 수 있습니다.",
            )
            return
        self._shutdown_ai()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        overlay = getattr(self, "day_advance_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.root_stack.rect())

    def _shutdown_ai(self):
        if self.manager_event_page is not None:
            self.manager_event_page.shutdown_worker()
        if self.player_meeting_page is not None:
            self.player_meeting_page.shutdown_worker()
        if self.trade_negotiation_page is not None:
            self.trade_negotiation_page.shutdown_worker()
        worker = self._team_ai_worker
        if worker is not None and worker.isRunning():
            print("[상대 구단 Qwen AI] 게임 종료 · 작업 중단 요청", flush=True)
            try:
                worker.processed.disconnect()
            except (RuntimeError, TypeError):
                pass
            worker.stop()
            if not worker.wait(3000):
                print("[상대 구단 Qwen AI] 연결 종료 대기 중 · 강제 스레드 종료", flush=True)
                worker.terminate()
                worker.wait(1000)
            worker.defer_processing_rows()
        stop_owned_local_ai_server()

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
        self.btn_search.setChecked(page_index == 4)
        self.btn_tactics.setChecked(page_index == 5)
        self.btn_club_info.setChecked(False)
        section_titles = {
            0: ("수신함", "구단 운영과 리그의 주요 메시지"),
            1: ("구단 뉴스", "KBO 뉴스와 1군 부상 소식"),
            2: ("일정", "시즌 일정과 구단 일정"),
            3: ("선수단", "1군·2군 선수단 관리"),
            4: ("탐색", "구단과 선수를 통합 검색"),
            5: ("전술", "타순·수비 위치·선발 로테이션·불펜 운용"),
        }
        title, context = section_titles.get(page_index, ("구단 운영", self.club_name))
        self.calendar_bar.set_section(title, context)
        if page_index == 0:
            self.league_home.refresh_notifications()
        if page_index == 1:
            self.news_feed.set_game_date(self.current_date)
        if page_index == 3:
            self.sidebar.hide()
            self.my_team_manager.refresh_all()
        else:
            self.sidebar.show()
        if page_index == 5:
            self.tactics_page.reload()

    def apply_team_theme(self):
        c = self.colors
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {c['bg_dark']}; }}
            QWidget#Sidebar {{
                background-color: #10151a;
                border-right: 1px solid #343d46;
            }}
            QWidget#Sidebar QLabel#SidebarCrest {{
                background-color: {c['accent']};
                border-bottom: 1px solid {c['accent_light']};
            }}
            QWidget#Sidebar QLabel[sidebarSection="true"] {{
                color: #6f7c89;
                background-color: #0d1217;
                border-top: 1px solid #273039;
                border-bottom: 1px solid #273039;
                padding: 7px 10px 5px 10px;
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel {{ color: {c['text']}; font-family: 'Malgun Gothic', 'Segoe UI'; }}
            QWidget#Sidebar QPushButton {{
                background-color: transparent;
                color: #aeb7c0;
                border: 0;
                border-left: 3px solid transparent;
                border-bottom: 1px solid #1b2229;
                min-height: 30px;
                padding: 2px 10px;
                text-align: left;
                font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 12px;
                border-radius: 0;
                font-weight: 600;
            }}
            QWidget#Sidebar QPushButton:hover {{
                background-color: #1a2128;
                color: {c['accent_light']};
            }}
            QWidget#Sidebar QPushButton:checked {{
                background-color: #202831;
                color: white;
                border-left: 3px solid {c['accent_light']};
            }}
            QWidget#Sidebar QPushButton[placeholder="true"] {{ color: #83909e; }}
            QWidget#Sidebar QPushButton[placeholder="true"]:hover {{ color: {c['accent_light']}; border-left: 3px solid {c['accent']}; }}
            QTableWidget {{
                background-color: {c['card_bg']};
                border: 1px solid #1e293b;
                gridline-color: #1e293b;
                border-radius: 0;
            }}
        """)


def run():
    """이전 진입점 호환용 래퍼."""
    from app.application import run as application_run

    return application_run()
