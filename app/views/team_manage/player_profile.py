"""팝업 없이 사용하는 FM 스타일 3단 선수 상세 페이지."""

import csv
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database.paths import DATA_DIR


DEFAULT_COLORS = {
    "bg_dark": "#11161d",
    "card_bg": "#1a212a",
    "tab_selected": "#26313d",
    "accent": "#3b82f6",
    "accent_light": "#93c5fd",
    "text": "#e5eef8",
}

HITTER_COLUMNS = (
    (
        "타격",
        (
            ("contact", "컨택", False),
            ("power", "파워", False),
            ("plate_discipline", "선구안", False),
            ("bat_control", "배트 컨트롤", False),
            ("timing", "타이밍", False),
            ("bunt", "번트", False),
            (None, "대타 능력", False),
        ),
    ),
    (
        "주루 · 수비",
        (
            ("speed", "주력", False),
            ("baserunning_judgment", "주루 판단", False),
            ("fielding_range", "수비범위", False),
            ("catching", "포구", False),
            ("throwing_power", "송구력", False),
            ("throwing_accuracy", "송구 정확도", False),
            ("fielding_judgment", "수비판단", False),
        ),
    ),
    (
        "멘탈",
        (
            ("composure", "침착성", False),
            ("leadership", "리더십", False),
            ("aggressiveness", "적극성", False),
            (None, "집중력", False),
            (None, "팀워크", False),
            (None, "승부욕", False),
            (None, "프로 의식", False),
        ),
    ),
)

PITCHER_COLUMNS = (
    (
        "투구",
        (
            ("con", "구속", True),
            ("pow", "제구", True),
            ("eye", "변화구", True),
            ("def", "스태미나", True),
            (None, "구위", False),
            (None, "위기관리", False),
            (None, "견제", False),
        ),
    ),
    (
        "수비",
        (
            ("fielding_range", "수비범위", False),
            ("catching", "포구", False),
            ("throwing_power", "송구력", False),
            ("throwing_accuracy", "송구 정확도", False),
            ("fielding_judgment", "수비판단", False),
            (None, "번트 수비", False),
            (None, "베이스 커버", False),
        ),
    ),
    (
        "멘탈",
        (
            ("composure", "침착성", False),
            ("leadership", "리더십", False),
            ("aggressiveness", "적극성", False),
            (None, "집중력", False),
            (None, "일관성", False),
            (None, "승부욕", False),
            (None, "프로 의식", False),
        ),
    ),
)


def _source_path(filename):
    external = DATA_DIR / "source" / filename
    if external.exists():
        return external
    bundle_root = Path(getattr(sys, "_MEIPASS", DATA_DIR.parent))
    return bundle_root / "data" / "source" / filename


@lru_cache(maxsize=2)
def _season_records(filename):
    path = _source_path(filename)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["kbo_player_id"]: row for row in csv.DictReader(source)}


def _display_rating(value, scale_100=False):
    if value is None or value == "":
        return None
    rating = int(value)
    return max(1, min(20, round(rating / 5))) if scale_100 else rating


def _rating_tier(rating):
    if rating is None:
        return "empty"
    if rating >= 16:
        return "elite"
    if rating >= 13:
        return "good"
    if rating >= 9:
        return "average"
    return "low"


class AttributeColumn(QFrame):
    """참고 이미지 중앙의 세로 능력치 열."""

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.setObjectName("AttributeColumn")
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(4)
        self.title_label = QLabel()
        self.title_label.setObjectName("ColumnTitle")
        layout.addWidget(self.title_label)
        for _ in range(7):
            row_frame = QFrame()
            row_frame.setObjectName("AttributeRow")
            row = QHBoxLayout(row_frame)
            row.setContentsMargins(7, 4, 5, 4)
            name = QLabel()
            name.setObjectName("AttributeName")
            value = QLabel("-")
            value.setObjectName("AttributeValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setFixedWidth(29)
            value.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            row.addWidget(name)
            row.addStretch()
            row.addWidget(value)
            layout.addWidget(row_frame)
            self.rows.append((name, value))

    def set_schema(self, title, fields, player):
        self.title_label.setText(title)
        for (name_label, value_label), (key, title, scale_100) in zip(self.rows, fields):
            rating = _display_rating(player.get(key), scale_100) if key else None
            name_label.setText(title)
            value_label.setText(str(rating) if rating is not None else "-")
            value_label.setProperty("rating", _rating_tier(rating))
            value_label.style().unpolish(value_label)
            value_label.style().polish(value_label)


class BaseballPositionMap(QWidget):
    """우측 포지션 분석용 간단한 야구장 다이어그램."""

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.position_group = None
        self.setMinimumSize(190, 150)

    def set_position(self, position_group):
        self.position_group = position_group
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(self.colors["bg_dark"]))
        pen = QPen(QColor(self.colors["accent_light"]), 1)
        painter.setPen(pen)
        center_x, center_y = width // 2, int(height * 0.55)
        size = min(width, height) * 0.42
        points = [
            (center_x, center_y + size * 0.62),
            (center_x + size * 0.62, center_y),
            (center_x, center_y - size * 0.62),
            (center_x - size * 0.62, center_y),
        ]
        for start, end in zip(points, points[1:] + points[:1]):
            painter.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))
        painter.drawArc(
            int(center_x - size), int(center_y - size * 1.08),
            int(size * 2), int(size * 2), 0, 180 * 16,
        )
        positions = {
            "C": [(center_x, center_y + size * 0.78)],
            "P": [(center_x, center_y)],
            "IF": [
                (center_x - size * 0.48, center_y),
                (center_x + size * 0.48, center_y),
                (center_x - size * 0.32, center_y - size * 0.32),
                (center_x + size * 0.32, center_y - size * 0.32),
            ],
            "OF": [
                (center_x - size * 0.72, center_y - size * 0.62),
                (center_x, center_y - size * 0.88),
                (center_x + size * 0.72, center_y - size * 0.62),
            ],
        }
        for group, dots in positions.items():
            color = QColor(self.colors["accent_light"]) if group == self.position_group else QColor("#506174")
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#0b1118"), 1))
            for x, y in dots:
                painter.drawEllipse(int(x - 5), int(y - 5), 10, 10)


class PlayerProfilePage(QWidget):
    """참고 이미지와 같은 좌측 카드·중앙 능력치·우측 분석 구조."""

    back_requested = Signal()

    def __init__(self, colors=None, parent=None):
        super().__init__(parent)
        self.colors = {**DEFAULT_COLORS, **(colors or {})}
        self.player = {}
        self._build_ui()

    def _build_ui(self):
        colors = self.colors
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        nav = QFrame()
        nav.setObjectName("TopNavigation")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 4, 10, 4)
        nav_layout.setSpacing(3)
        self.back_button = QPushButton("← 선수단")
        self.back_button.setObjectName("BackButton")
        self.back_button.clicked.connect(self.back_requested.emit)
        nav_layout.addWidget(self.back_button)
        for index, title in enumerate(("개요", "계약", "기록", "훈련", "부상", "보고서", "비교", "이력")):
            tab = QLabel(title)
            tab.setObjectName("ActiveNav" if index == 0 else "NavItem")
            tab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nav_layout.addWidget(tab)
        nav_layout.addStretch()
        self.header_type = QLabel()
        self.header_type.setObjectName("HeaderType")
        nav_layout.addWidget(self.header_type)
        root.addWidget(nav)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)
        canvas = QWidget()
        canvas.setMinimumSize(1080, 700)
        scroll.setWidget(canvas)
        grid = QGridLayout(canvas)
        grid.setContentsMargins(8, 8, 8, 10)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self._build_left_card(grid)
        self._build_center(grid)
        self._build_right_analysis(grid)
        grid.setColumnStretch(0, 22)
        grid.setColumnStretch(1, 53)
        grid.setColumnStretch(2, 25)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {colors['bg_dark']}; color: {colors['text']};
                font-family: 'Malgun Gothic'; font-size: 12px;
            }}
            QScrollArea {{ border: none; }}
            QFrame#TopNavigation {{ background-color: {colors['card_bg']}; border-bottom: 1px solid {colors['accent']}; }}
            QLabel#NavItem, QLabel#ActiveNav {{ color: #aeb9c5; padding: 7px 11px; }}
            QLabel#ActiveNav {{ color: white; border-bottom: 2px solid {colors['accent_light']}; font-weight: bold; }}
            QLabel#HeaderType {{ color: {colors['accent_light']}; padding: 5px 9px; font-weight: bold; }}
            QPushButton#BackButton {{ color: white; background-color: {colors['tab_selected']}; border: 1px solid {colors['accent']}; padding: 6px 10px; }}
            QPushButton#BackButton:hover {{ background-color: {colors['accent']}; }}
            QFrame#LeftCard, QFrame#CenterCard, QFrame#RightCard {{
                background-color: {colors['card_bg']}; border: 1px solid #2d3946;
            }}
            QFrame#SubCard {{ background-color: {colors['tab_selected']}; border: 1px solid {colors['accent']}; }}
            QLabel#Avatar {{ color: white; background-color: {colors['accent']}; border: 1px solid {colors['accent_light']}; }}
            QLabel#PlayerName {{ color: white; font-size: 23px; font-weight: bold; }}
            QLabel#AccentText, QLabel#SectionTitle, QLabel#ColumnTitle {{ color: {colors['accent_light']}; font-weight: bold; }}
            QLabel#Muted, QLabel#AttributeName, QLabel#InfoName, QLabel#SeasonName {{ color: #95a3b2; }}
            QLabel#AttributeValue {{ border-radius: 3px; padding: 2px 4px; }}
            QLabel#AttributeValue[rating="elite"] {{ color: #67e8f9; background-color: #164e63; }}
            QLabel#AttributeValue[rating="good"] {{ color: #86efac; background-color: #14532d; }}
            QLabel#AttributeValue[rating="average"] {{ color: #fde68a; background-color: #713f12; }}
            QLabel#AttributeValue[rating="low"] {{ color: #fca5a5; background-color: #7f1d1d; }}
            QLabel#AttributeValue[rating="empty"] {{ color: #64748b; background-color: #202936; }}
            QFrame#AttributeColumn {{ background-color: {colors['tab_selected']}; border: 1px solid {colors['accent']}; }}
            QFrame#AttributeRow {{ background-color: {colors['card_bg']}; border: none; min-height: 25px; }}
            QFrame#SeasonBox {{ background-color: {colors['tab_selected']}; border: 1px solid {colors['accent']}; }}
            QLabel#SeasonValue {{ color: white; font-weight: bold; }}
            QLabel#BigRating {{ color: {colors['accent_light']}; font-size: 28px; font-weight: bold; }}
            QLabel#Stars {{ color: #facc15; font-size: 16px; }}
            QLabel#Positive {{ color: #4ade80; font-weight: bold; }}
            QLabel#Warning {{ color: #fbbf24; font-weight: bold; }}
            QLabel#BodyText {{ color: #c6d1dc; }}
            QLabel#InfoValue {{ color: #e6edf5; font-weight: bold; }}
            QLabel#RolePrimary {{ color: #4ade80; background-color: #183e2a; padding: 4px 6px; }}
            QLabel#RoleEmpty {{ color: #657487; background-color: #202936; padding: 4px 6px; }}
        """)

    def _build_left_card(self, grid):
        card = QFrame()
        card.setObjectName("LeftCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(7)
        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setMinimumHeight(275)
        self.avatar.setFont(QFont("Malgun Gothic", 34, QFont.Weight.Bold))
        layout.addWidget(self.avatar)
        self.physical_line = QLabel()
        self.physical_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.physical_line)
        self.age_line = QLabel()
        self.age_line.setObjectName("Muted")
        self.age_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.age_line)

        contract = QFrame()
        contract.setObjectName("SubCard")
        contract_layout = QGridLayout(contract)
        contract_layout.setContentsMargins(8, 7, 8, 7)
        self.salary_value = self._info_pair(contract_layout, 0, "연봉")
        self.market_value = self._info_pair(contract_layout, 1, "시장 가치")
        self.contract_end = self._info_pair(contract_layout, 2, "계약 만료")
        layout.addWidget(contract)

        self.current_stars = QLabel()
        self.current_stars.setObjectName("Stars")
        self.current_stars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.potential_stars = QLabel("잠재력  ☆☆☆☆☆  미평가")
        self.potential_stars.setObjectName("Muted")
        self.potential_stars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.current_stars)
        layout.addWidget(self.potential_stars)

        shirt = QFrame()
        shirt.setObjectName("SubCard")
        shirt_layout = QVBoxLayout(shirt)
        shirt_layout.setContentsMargins(8, 12, 8, 12)
        self.team_badge = QLabel()
        self.team_badge.setObjectName("AccentText")
        self.team_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.team_badge.setFont(QFont("Malgun Gothic", 14, QFont.Weight.Bold))
        self.squad_number = QLabel("등번호  -")
        self.squad_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shirt_layout.addWidget(self.team_badge)
        shirt_layout.addWidget(self.squad_number)
        layout.addWidget(shirt)

        self.registration_status = QLabel()
        self.registration_status.setObjectName("Positive")
        self.registration_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.registration_status)
        layout.addStretch()
        grid.addWidget(card, 0, 0, 2, 1)

    def _build_center(self, grid):
        center = QFrame()
        center.setObjectName("CenterCard")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        identity = QVBoxLayout()
        self.name_label = QLabel()
        self.name_label.setObjectName("PlayerName")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("AccentText")
        self.career_label = QLabel()
        self.career_label.setObjectName("Muted")
        self.career_label.setWordWrap(True)
        identity.addWidget(self.name_label)
        identity.addWidget(self.subtitle_label)
        identity.addWidget(self.career_label)
        heading.addLayout(identity, 1)
        self.status_label = QLabel()
        self.status_label.setObjectName("Positive")
        heading.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(heading)

        section = QLabel("능력치")
        section.setObjectName("SectionTitle")
        layout.addWidget(section)
        attributes = QHBoxLayout()
        attributes.setSpacing(6)
        self.attribute_columns = [AttributeColumn(self.colors) for _ in range(3)]
        for column in self.attribute_columns:
            attributes.addWidget(column, 1)
        layout.addLayout(attributes)

        self.season_title = QLabel()
        self.season_title.setObjectName("SectionTitle")
        layout.addWidget(self.season_title)
        season_grid = QGridLayout()
        season_grid.setHorizontalSpacing(4)
        season_grid.setVerticalSpacing(4)
        self.season_names = []
        self.season_values = []
        for index in range(10):
            box = QFrame()
            box.setObjectName("SeasonBox")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(5, 5, 5, 5)
            name = QLabel()
            name.setObjectName("SeasonName")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value = QLabel("-")
            value.setObjectName("SeasonValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box_layout.addWidget(name)
            box_layout.addWidget(value)
            season_grid.addWidget(box, index // 5, index % 5)
            self.season_names.append(name)
            self.season_values.append(value)
        layout.addLayout(season_grid)

        lower = QHBoxLayout()
        lower.setSpacing(7)
        report = QFrame()
        report.setObjectName("SubCard")
        report_layout = QVBoxLayout(report)
        report_layout.setContentsMargins(9, 8, 9, 8)
        title = QLabel("코칭스태프 보고서")
        title.setObjectName("SectionTitle")
        self.strengths_label = QLabel()
        self.strengths_label.setObjectName("BodyText")
        self.strengths_label.setWordWrap(True)
        self.improvements_label = QLabel()
        self.improvements_label.setObjectName("BodyText")
        self.improvements_label.setWordWrap(True)
        report_layout.addWidget(title)
        report_layout.addWidget(self.strengths_label)
        report_layout.addWidget(self.improvements_label)
        report_layout.addStretch()
        lower.addWidget(report, 3)

        medical = QFrame()
        medical.setObjectName("SubCard")
        medical_layout = QGridLayout(medical)
        medical_layout.setContentsMargins(9, 8, 9, 8)
        medical_title = QLabel("컨디션 · 의무 정보")
        medical_title.setObjectName("SectionTitle")
        medical_layout.addWidget(medical_title, 0, 0, 1, 2)
        self.fitness_value = self._info_pair(medical_layout, 1, "체력")
        self.condition_value = self._info_pair(medical_layout, 2, "경기 감각")
        self.injury_value = self._info_pair(medical_layout, 3, "부상 위험")
        self.morale_value = self._info_pair(medical_layout, 4, "사기")
        lower.addWidget(medical, 2)
        layout.addLayout(lower)
        grid.addWidget(center, 0, 1, 2, 1)

    def _build_right_analysis(self, grid):
        right = QFrame()
        right.setObjectName("RightCard")
        layout = QVBoxLayout(right)
        layout.setContentsMargins(9, 9, 9, 10)
        layout.setSpacing(7)
        title = QLabel("능력치 분석")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        self.overall_value = QLabel()
        self.overall_value.setObjectName("BigRating")
        self.overall_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.overall_value)
        self.overall_stars = QLabel()
        self.overall_stars.setObjectName("Stars")
        self.overall_stars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.overall_stars)

        info = QFrame()
        info.setObjectName("SubCard")
        info_layout = QGridLayout(info)
        info_layout.setContentsMargins(8, 7, 8, 7)
        self.analysis_values = {}
        for row, (key, name) in enumerate((
            ("position", "주 포지션"), ("hand", "투타"),
            ("source", "평가 자료"), ("confidence", "평가 신뢰도"),
            ("kbo_id", "KBO ID"), ("snapshot", "기준일"),
        )):
            self.analysis_values[key] = self._info_pair(info_layout, row, name)
        layout.addWidget(info)

        position_title = QLabel("수비 위치")
        position_title.setObjectName("SectionTitle")
        layout.addWidget(position_title)
        self.position_map = BaseballPositionMap(self.colors)
        layout.addWidget(self.position_map)

        role_title = QLabel("포지션 숙련도")
        role_title.setObjectName("SectionTitle")
        layout.addWidget(role_title)
        self.role_labels = {}
        for code, name in (("P", "투수"), ("C", "포수"), ("IF", "내야수"), ("OF", "외야수")):
            row = QHBoxLayout()
            label = QLabel(name)
            value = QLabel("미평가")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            layout.addLayout(row)
            self.role_labels[code] = value

        data_title = QLabel("데이터 상태")
        data_title.setObjectName("SectionTitle")
        layout.addWidget(data_title)
        self.formula_label = QLabel()
        self.formula_label.setObjectName("Muted")
        self.formula_label.setWordWrap(True)
        self.profile_state_label = QLabel()
        self.profile_state_label.setObjectName("Muted")
        layout.addWidget(self.formula_label)
        layout.addWidget(self.profile_state_label)
        layout.addStretch()
        grid.addWidget(right, 0, 2, 2, 1)

    @staticmethod
    def _info_pair(layout, row, title):
        name = QLabel(title)
        name.setObjectName("InfoName")
        value = QLabel("-")
        value.setObjectName("InfoValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(name, row, 0)
        layout.addWidget(value, row, 1)
        return value

    def set_player(self, player):
        self.player = dict(player)
        is_pitcher = self.player.get("position_group") == "P" or self.player.get("pos") == "P"
        position_group = "P" if is_pitcher else self.player.get("position_group")
        position = "투수" if is_pitcher else self._position_name(self.player)
        schema = PITCHER_COLUMNS if is_pitcher else HITTER_COLUMNS
        for column, (title, fields) in zip(self.attribute_columns, schema):
            column.set_schema(title, fields, self.player)

        name = self.player.get("name", "-")
        self.avatar.setText(name[-2:])
        self.name_label.setText(name)
        self.header_type.setText("투수 PROFILE" if is_pitcher else "타자 PROFILE")
        self.subtitle_label.setText(f"{self.player.get('team', '-')}  ·  {position}")
        self.career_label.setText(f"경력  {self.player.get('career') or '미등록'}")
        self.status_label.setText("● 1군 엔트리" if self.player.get("status") else "● C팀 / 육성")

        height, weight = self.player.get("height_cm"), self.player.get("weight_kg")
        self.physical_line.setText(
            f"{height or '-'}cm     {self.player.get('age', '-')}세     {weight or '-'}kg"
        )
        self.age_line.setText(
            f"{self.player.get('birth_date') or '-'}  ·  {self.player.get('bats_throws') or '-'}"
        )
        salary = int(self.player.get("salary") or 0)
        self.salary_value.setText(f"₩{salary:,}만")
        self.market_value.setText("미평가")
        self.contract_end.setText("미등록")
        self.team_badge.setText(self.player.get("team", "-"))
        self.registration_status.setText("1군 등록 선수" if self.player.get("status") else "육성 · C팀 선수")

        record = self._load_record(is_pitcher)
        ratings = self._current_ratings(is_pitcher)
        overall = round(sum(ratings) / len(ratings), 1) if ratings else None
        stars = self._stars(overall)
        self.current_stars.setText(f"현재 능력  {stars}")
        self.overall_stars.setText(stars)
        self.overall_value.setText(f"{overall} / 20" if overall is not None else "미평가")
        self._set_season_stats(is_pitcher, record)
        self._set_report(is_pitcher)

        source = self.player.get("ability_source_level") or "미평가"
        confidence = "높음" if source == "KBO" else "보통" if source == "FUTURES" else "낮음"
        for key, value in (
            ("position", position), ("hand", self.player.get("bats_throws") or "-"),
            ("source", source), ("confidence", confidence),
            ("kbo_id", self.player.get("kbo_player_id") or "-"),
            ("snapshot", self.player.get("snapshot_date") or "-"),
        ):
            self.analysis_values[key].setText(str(value))
        self.position_map.set_position(position_group)
        for code, label in self.role_labels.items():
            if code == position_group:
                label.setText("주 포지션")
                label.setObjectName("RolePrimary")
            else:
                label.setText("미평가")
                label.setObjectName("RoleEmpty")
            label.style().unpolish(label)
            label.style().polish(label)
        self.formula_label.setText(
            f"능력치 버전\n{self.player.get('ability_formula_version') or '미적용'}"
        )
        profile = "완료" if self.player.get("profile_complete") else "일부 정보 없음"
        self.profile_state_label.setText(f"공식 프로필  {profile}")

        for label in (self.fitness_value, self.condition_value, self.injury_value, self.morale_value):
            label.setText("미평가")

    def _load_record(self, is_pitcher):
        filename = "kbo_2025_first_team_pitching.csv" if is_pitcher else "kbo_2025_first_team_hitting.csv"
        return _season_records(filename).get(str(self.player.get("kbo_player_id")), {})

    def _current_ratings(self, is_pitcher):
        if is_pitcher:
            return [
                _display_rating(self.player.get(key), True)
                for key in ("con", "pow", "eye", "def")
                if self.player.get(key) is not None
            ]
        return [
            _display_rating(self.player.get(key))
            for key in (
                "contact", "power", "plate_discipline", "bat_control",
                "timing", "bunt", "speed", "baserunning_judgment",
            )
            if self.player.get(key) is not None
        ]

    @staticmethod
    def _stars(overall):
        if overall is None:
            return "☆☆☆☆☆"
        filled = max(1, min(5, round(overall / 4)))
        return "★" * filled + "☆" * (5 - filled)

    def _set_season_stats(self, is_pitcher, record):
        if is_pitcher:
            self.season_title.setText("2025 시즌 투수 기록")
            fields = (
                ("G", "경기"), ("W", "승"), ("L", "패"), ("SV", "세이브"),
                ("HLD", "홀드"), ("ERA", "ERA"), ("IP", "이닝"),
                ("WHIP", "WHIP"), ("SO", "탈삼진"), ("BB", "볼넷"),
            )
        else:
            self.season_title.setText("2025 시즌 타자 기록")
            fields = (
                ("G", "경기"), ("PA", "타석"), ("AVG", "타율"),
                ("OBP", "출루율"), ("SLG", "장타율"), ("OPS", "OPS"),
                ("HR", "홈런"), ("RBI", "타점"), ("SB", "도루"), ("SO", "삼진"),
            )
        has_record = record.get("has_record") == "1" if record else False
        for index, (key, title) in enumerate(fields):
            self.season_names[index].setText(title)
            self.season_values[index].setText(record.get(key, "-") if has_record else "-")

    def _set_report(self, is_pitcher):
        if is_pitcher:
            raw = (
                ("구속", self.player.get("con"), True), ("제구", self.player.get("pow"), True),
                ("변화구", self.player.get("eye"), True), ("스태미나", self.player.get("def"), True),
            )
        else:
            raw = (
                ("컨택", self.player.get("contact"), False), ("파워", self.player.get("power"), False),
                ("선구안", self.player.get("plate_discipline"), False),
                ("배트 컨트롤", self.player.get("bat_control"), False),
                ("타이밍", self.player.get("timing"), False), ("번트", self.player.get("bunt"), False),
                ("주력", self.player.get("speed"), False),
                ("주루 판단", self.player.get("baserunning_judgment"), False),
            )
        ratings = [(name, _display_rating(value, scaled)) for name, value, scaled in raw if value is not None]
        best = sorted(ratings, key=lambda item: item[1], reverse=True)[:3]
        weak = sorted(ratings, key=lambda item: item[1])[:3]
        strengths = [f"• {name} {value}/20" for name, value in best if value >= 11]
        needs = [f"• {name} {value}/20" for name, value in weak if value <= 10]
        self.strengths_label.setText("강점\n" + ("\n".join(strengths) if strengths else "• 추가 관찰 필요"))
        missing = "\n• 수비·멘탈 데이터 미평가" if any(
            self.player.get(key) is None for key in (
                "fielding_range", "catching", "throwing_power", "throwing_accuracy",
                "fielding_judgment", "composure", "leadership", "aggressiveness",
            )
        ) else ""
        self.improvements_label.setText(
            "보완점\n" + ("\n".join(needs) if needs else "• 뚜렷한 약점 없음") + missing
        )

    @staticmethod
    def _position_name(player):
        return {"C": "포수", "IF": "내야수", "OF": "외야수"}.get(
            player.get("position_group"), player.get("pos") or "야수"
        )
