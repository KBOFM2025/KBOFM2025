"""팝업 없이 사용하는 FM 스타일 3단 선수 상세 페이지."""

import csv
import json
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.player_ratings import core_rating_values
from database.paths import DATA_DIR


DEFAULT_COLORS = {
    "bg_dark": "#11161d",
    "card_bg": "#1a212a",
    "tab_selected": "#26313d",
    "accent": "#3b82f6",
    "accent_light": "#93c5fd",
    "text": "#e5eef8",
}

PLAYER_PHOTO_DIRECTORY = DATA_DIR.parent / "image" / "players" / "local"
PLAYER_PHOTO_EXTENSIONS = (".webp", ".png", ".jpg", ".jpeg")
PITCH_COLUMN_CODES = {
    "pitch_four_seam": "FF", "pitch_sinker": "SI", "pitch_cutter": "FC",
    "pitch_changeup": "CH", "pitch_slider": "SL", "pitch_curve": "CU",
    "pitch_splitter": "FS", "pitch_sweeper": "ST", "pitch_knuckleball": "KN",
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
            ("pitcher_velocity", "구속", False),
            ("pitcher_stuff", "구위", False),
            ("pitcher_command", "제구", False),
            ("pitcher_movement", "무브먼트", False),
            ("pitcher_stamina", "스태미나", False),
            ("pitcher_pitchability", "경기 운영", False),
            ("pitcher_composure", "위기 관리", False),
        ),
    ),
    (
        "구종 보유",
        (
            ("pitch_four_seam", "포심", False),
            ("pitch_slider", "슬라이더", False),
            ("pitch_changeup", "체인지업", False),
            ("pitch_curve", "커브", False),
            ("pitch_splitter", "스플리터", False),
            ("pitch_sinker", "싱커", False),
            ("pitch_cutter", "커터", False),
        ),
    ),
    (
        "세부 평가",
        (
            ("pitcher_strikeout", "탈삼진 능력", False),
            ("pitcher_walk_control", "볼넷 억제", False),
            ("pitch_sweeper", "스위퍼", False),
            ("pitch_knuckleball", "너클볼", False),
            (None, "견제", False),
            (None, "번트 수비", False),
            (None, "베이스 커버", False),
        ),
    ),
)


def _source_path(filename):
    external = DATA_DIR / "source" / filename
    if external.exists():
        return external
    bundle_root = Path(getattr(sys, "_MEIPASS", DATA_DIR.parent))
    return bundle_root / "data" / "source" / filename


def _player_photo_path(kbo_player_id, player_name=None, team_name=None):
    if kbo_player_id:
        for extension in PLAYER_PHOTO_EXTENSIONS:
            candidate = PLAYER_PHOTO_DIRECTORY / f"{kbo_player_id}{extension}"
            if candidate.exists():
                return candidate
    team_directories = {"NC 다이노스": "NC", "NC": "NC"}
    team_directory = team_directories.get(team_name)
    if player_name and team_directory:
        directory = DATA_DIR.parent / "image" / "Player_Image" / team_directory
        for extension in PLAYER_PHOTO_EXTENSIONS:
            candidate = directory / f"{player_name}{extension}"
            if candidate.exists():
                return candidate
    return None


@lru_cache(maxsize=2)
def _season_records(filename):
    path = _source_path(filename)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["kbo_player_id"]: row for row in csv.DictReader(source)}


@lru_cache(maxsize=1)
def _career_records():
    path = _source_path("kbo_player_career_history.csv")
    records = defaultdict(list)
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                records[str(row["kbo_player_id"])].append(row)
    return records


@lru_cache(maxsize=1)
def _membership_movements():
    path = _source_path("kbo_2025_membership_movements.csv")
    records = defaultdict(list)
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                records[(row.get("team", ""), row.get("player", ""))].append(row)
    return records


@lru_cache(maxsize=1)
def _verified_career_transactions():
    path = _source_path("kbo_verified_career_transactions.csv")
    records = defaultdict(list)
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                records[str(row.get("kbo_player_id", ""))].append(row)
    return records


def _career_summary(player):
    rows = sorted(
        _career_records().get(str(player.get("kbo_player_id")), []),
        key=lambda row: (int(row["season"]), row["record_team"]),
    )
    spans = []
    for row in rows:
        season, team = int(row["season"]), row["record_team"]
        if spans and spans[-1][0] == team and season <= spans[-1][2] + 1:
            spans[-1][2] = max(spans[-1][2], season)
            spans[-1][3].add(season)
        else:
            spans.append([team, season, season, {season}])
    route = " → ".join(
        f"{start}–{end} {team} ({len(years)}시즌)" if start != end else f"{start} {team}"
        for team, start, end, years in spans
    ) or "KBO 1군 경력 없음"
    events = _membership_movements().get((player.get("team", ""), player.get("name", "")), [])
    verified = []
    for event in _verified_career_transactions().get(str(player.get("kbo_player_id")), []):
        verified.append(f"{event.get('effective_season')} {event.get('detail')}")
    for event in events:
        if event.get("type") == "트레이드":
            verified.append(f"{event.get('date')} 트레이드 {event.get('detail')}")
        elif event.get("type") in {"웨이버", "자유계약선수"}:
            verified.append(f"{event.get('date')} {event.get('type')}")
    suffix = f"\n최근 이동  {' · '.join(verified)}" if verified else ""
    return f"KBO 경력  {route}{suffix}"


def _career_card_data(player):
    career_tokens = [token.strip() for token in (player.get("career") or "").split("-") if token.strip()]
    high_schools = [token for token in career_tokens if token.endswith("고") or "(고)" in token]
    colleges = [token for token in career_tokens if token.endswith("대") or "(대)" in token]
    education = " → ".join((high_schools[-1:] + colleges[-1:])) or "공식 프로필 미등록"

    rows = sorted(
        _career_records().get(str(player.get("kbo_player_id")), []),
        key=lambda row: (int(row["season"]), row["record_team"]),
    )
    if rows:
        first_year = int(rows[0]["season"])
        first_team = rows[0]["record_team"]
        debut = f"{first_year}년 · {first_team} (KBO 첫 기록 기준)"
    elif player.get("is_rookie"):
        debut = f"2025년 · {player.get('team', '-')} (신인 등록)"
    else:
        debut = "공식 1군 기록 없음"

    spans = []
    for row in rows:
        season, team = int(row["season"]), row["record_team"]
        if spans and spans[-1][0] == team and season <= spans[-1][2] + 1:
            spans[-1][2] = max(spans[-1][2], season)
            spans[-1][3].add(season)
        else:
            spans.append([team, season, season, {season}])
    clubs = " → ".join(
        f"{team} {start}–{end} ({len(years)}시즌)" if start != end
        else f"{team} {start}"
        for team, start, end, years in spans
    ) or "KBO 1군 경력 없음"

    movements = [
        f"{event.get('effective_season')} {event.get('detail')}"
        for event in _verified_career_transactions().get(str(player.get("kbo_player_id")), [])
    ]
    for event in _membership_movements().get((player.get("team", ""), player.get("name", "")), []):
        if event.get("type") == "트레이드":
            movements.append(f"{event.get('date')} 트레이드 {event.get('detail')}")
    if movements:
        movement = " · ".join(movements)
    elif len(spans) == 1:
        movement = f"원클럽 · {spans[0][0]} {len(spans[0][3])}시즌"
    elif spans:
        movement = "구단 이동 확인 · 이적 방식 미확인"
    else:
        movement = "프로 이동 이력 없음"
    return (
        ("학력", education),
        ("프로 입단", debut),
        ("구단 경력", clubs),
        ("주요 이동", movement),
    )


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
        self.pitch_popup_text = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(5)
        self.title_label = QLabel()
        self.title_label.setObjectName("ColumnTitle")
        layout.addWidget(self.title_label)
        for _ in range(7):
            row_frame = QFrame()
            row_frame.setObjectName("AttributeRow")
            row = QHBoxLayout(row_frame)
            row.setContentsMargins(9, 5, 6, 5)
            name = QLabel()
            name.setObjectName("AttributeName")
            value = QLabel("-")
            value.setObjectName("AttributeValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setFixedWidth(34)
            value.setFont(QFont("Malgun Gothic", 12, QFont.Weight.DemiBold))
            for widget in (row_frame, name, value):
                widget.setMouseTracking(True)
                widget.installEventFilter(self)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(value)
            layout.addWidget(row_frame)
            self.rows.append((name, value))

    def eventFilter(self, watched, event):
        popup_text = self.pitch_popup_text.get(watched, "")
        if popup_text and event.type() == QEvent.Type.Enter:
            QToolTip.showText(QCursor.pos() + QPoint(14, 18), popup_text, watched)
            return False
        if event.type() == QEvent.Type.Leave and watched in self.pitch_popup_text:
            QToolTip.hideText()
            return False
        return super().eventFilter(watched, event)

    def set_schema(self, title, fields, player):
        self.title_label.setText(title)
        self.pitch_popup_text.clear()
        try:
            pitch_details = {
                detail.get("code"): detail
                for detail in json.loads(player.get("pitcher_pitch_detail_json") or "[]")
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            pitch_details = {}
        for index, ((name_label, value_label), (key, title, scale_100)) in enumerate(zip(self.rows, fields)):
            rating = _display_rating(player.get(key), scale_100) if key else None
            name_label.setText(title)
            tooltip = ""
            pitch_code = PITCH_COLUMN_CODES.get(key)
            detail = pitch_details.get(pitch_code) if pitch_code else None
            is_pitch_row = pitch_code is not None
            if is_pitch_row:
                value_label.setText("O" if detail and rating is not None else "X")
            else:
                value_label.setText(str(rating) if rating is not None else "-")
            if detail:
                usage = float(detail.get("usage_pct") or 0)
                whiff = float(detail.get("whiff_rate") or 0) * 100
                csw = float(detail.get("csw_rate") or 0) * 100
                tooltip = (
                    f"{title} 구종 가치 {rating}/20\n"
                    f"구위 K-Stuff+ {float(detail.get('k_stuff_plus') or 0):.1f}\n"
                    f"제구 K-Location+ {float(detail.get('k_location_plus') or 0):.1f}\n"
                    f"사용률 {usage:.1f}% · 평균 구속 {float(detail.get('speed') or 0):.1f}km/h\n"
                    f"Whiff {whiff:.1f}% · CSW {csw:.1f}% · 표본 {int(detail.get('n') or 0):,}구"
                )
            row_frame = self.rows[index][0].parentWidget()
            for widget in (row_frame, name_label, value_label):
                widget.setToolTip("")
                if tooltip:
                    self.pitch_popup_text[widget] = tooltip
            value_label.setProperty(
                "rating",
                "good" if is_pitch_row and detail and rating is not None
                else "empty" if is_pitch_row
                else _rating_tier(rating),
            )
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
        self.setObjectName("PlayerProfilePage")
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
        nav_layout.setContentsMargins(12, 5, 14, 5)
        nav_layout.setSpacing(4)
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

        canvas = QWidget()
        canvas.setObjectName("ProfileCanvas")
        canvas.setMinimumSize(1120, 720)
        root.addWidget(canvas, 1)
        grid = QGridLayout(canvas)
        grid.setContentsMargins(14, 14, 14, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._build_left_card(grid)
        self._build_center(grid)
        self._build_right_analysis(grid)
        grid.setColumnStretch(0, 22)
        grid.setColumnStretch(1, 53)
        grid.setColumnStretch(2, 25)

        self.setStyleSheet(f"""
            QWidget {{
                color: {colors['text']};
                font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 13px;
            }}
            QWidget#PlayerProfilePage, QWidget#ProfileCanvas {{ background-color: {colors['bg_dark']}; }}
            QLabel {{ background-color: transparent; border: none; }}
            QToolTip {{
                color: #edf6ff; background-color: #101820;
                border: 1px solid {colors['accent_light']}; border-radius: 5px;
                padding: 8px; font-size: 12px;
            }}
            QFrame#TopNavigation {{
                min-height: 42px; background-color: {colors['card_bg']};
                border-bottom: 1px solid #334252;
            }}
            QLabel#NavItem, QLabel#ActiveNav {{
                color: #95a5b6; padding: 10px 13px; font-size: 13px; font-weight: 500;
            }}
            QLabel#ActiveNav {{ color: white; border-bottom: 2px solid {colors['accent_light']}; font-weight: 700; }}
            QLabel#HeaderType {{ color: {colors['accent_light']}; padding: 7px 11px; font-size: 12px; font-weight: 700; }}
            QPushButton#BackButton {{
                color: white; background-color: {colors['tab_selected']};
                border: 1px solid #405063; border-radius: 6px;
                padding: 8px 13px; font-size: 13px; font-weight: 600;
            }}
            QPushButton#BackButton:hover {{ background-color: {colors['accent']}; }}
            QFrame#LeftCard, QFrame#CenterCard, QFrame#RightCard {{
                background-color: {colors['card_bg']}; border: 1px solid #2d3946; border-radius: 10px;
            }}
            QFrame#SubCard {{
                background-color: {colors['tab_selected']}; border: 1px solid #354455; border-radius: 7px;
            }}
            QFrame#CareerCard {{
                background-color: #0d1520; border: 1px solid #39495b;
                border-top: 3px solid #caa85d; border-radius: 7px;
                min-height: 190px;
            }}
            QLabel#CareerTitle {{
                color: #e0bc68; font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 13px; font-weight: 700;
            }}
            QLabel#CareerBadge {{
                color: #f5e3b3; background-color: #4b3b1c;
                border: 1px solid #8b6b2d; border-radius: 8px;
                padding: 2px 8px; font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 10px; font-weight: 500;
            }}
            QFrame#CareerTimelineRow {{
                background-color: #151f2c; border: 1px solid #273646;
                border-radius: 5px;
            }}
            QLabel#CareerMarker {{
                color: #d5ad54; font-size: 10px;
            }}
            QLabel#CareerStep {{
                color: #91a1b2; font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 11px; font-weight: 500;
            }}
            QLabel#CareerValue {{
                color: #f2f5f8; font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 12px; font-weight: 600;
            }}
            QLabel#Avatar {{
                color: white;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {colors['accent']}, stop:1 {colors['tab_selected']});
                border: 1px solid #40536a; border-radius: 8px;
            }}
            QLabel#PlayerName {{ color: white; font-size: 30px; font-weight: 800; }}
            QLabel#AccentText {{ color: {colors['accent_light']}; font-size: 14px; font-weight: 600; }}
            QLabel#SectionTitle {{
                color: #edf6ff; border-left: 3px solid {colors['accent']};
                padding: 3px 0 3px 9px; font-size: 16px; font-weight: 700;
            }}
            QLabel#ColumnTitle {{ color: {colors['accent_light']}; font-size: 14px; font-weight: 700; padding-bottom: 4px; }}
            QLabel#Muted {{ color: #8fa0b1; font-size: 12px; }}
            QLabel#AttributeName {{ color: #b5c0cb; font-size: 13px; font-weight: 400; }}
            QLabel#AttributeValue {{
                border-radius: 4px; padding: 2px 4px;
                font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 15px; font-weight: 700;
            }}
            QLabel#AttributeValue[rating="elite"] {{ color: #67e8f9; background-color: #164e63; }}
            QLabel#AttributeValue[rating="good"] {{ color: #86efac; background-color: #14532d; }}
            QLabel#AttributeValue[rating="average"] {{ color: #fde68a; background-color: #713f12; }}
            QLabel#AttributeValue[rating="low"] {{ color: #fca5a5; background-color: #7f1d1d; }}
            QLabel#AttributeValue[rating="empty"] {{ color: #64748b; background-color: #202936; }}
            QFrame#AttributeColumn {{
                background-color: {colors['tab_selected']}; border: 1px solid #344456; border-radius: 7px;
            }}
            QFrame#AttributeRow {{ background-color: {colors['card_bg']}; border: none; border-radius: 4px; min-height: 32px; }}
            QFrame#SeasonBox {{
                background-color: {colors['tab_selected']}; border: 1px solid #344456; border-radius: 6px;
            }}
            QLabel#SeasonName {{ color: #92a2b3; font-size: 12px; font-weight: 500; }}
            QLabel#SeasonValue {{
                color: white; font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 17px; font-weight: 700;
            }}
            QLabel#BigRating {{
                color: {colors['accent_light']}; font-family: 'Malgun Gothic', 'Segoe UI';
                font-size: 32px; font-weight: 700;
            }}
            QLabel#Stars {{ color: #facc15; font-size: 17px; }}
            QLabel#Positive {{ color: #4ade80; font-size: 13px; font-weight: 600; }}
            QLabel#Warning {{ color: #fbbf24; font-weight: 600; }}
            QLabel#BodyText {{ color: #c3cfda; font-size: 13px; }}
            QLabel#InfoName {{ color: #93a3b4; font-size: 12px; }}
            QLabel#InfoValue {{ color: #edf3f9; font-size: 13px; font-weight: 600; }}
            QLabel#RolePrimary {{ color: #6ee7a0; background-color: #183e2a; border-radius: 4px; padding: 4px 7px; font-weight: 600; }}
            QLabel#RoleEmpty {{ color: #657487; background-color: #202936; border-radius: 4px; padding: 4px 7px; }}
        """)

    def _build_left_card(self, grid):
        card = QFrame()
        card.setObjectName("LeftCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(9)
        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setMinimumHeight(285)
        self.avatar.setFont(QFont("Malgun Gothic", 36, QFont.Weight.Bold))
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
        self.team_badge.setFont(QFont("Malgun Gothic", 15, QFont.Weight.Bold))
        self.squad_number = QLabel("등번호  -")
        self.squad_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shirt_layout.addWidget(self.team_badge)
        shirt_layout.addWidget(self.squad_number)
        layout.addWidget(shirt)

        self.registration_status = QLabel()
        self.registration_status.setObjectName("Positive")
        self.registration_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.registration_status)

        career_card = QFrame()
        career_card.setObjectName("CareerCard")
        career_layout = QVBoxLayout(career_card)
        career_layout.setContentsMargins(10, 9, 10, 10)
        career_layout.setSpacing(5)
        career_header = QHBoxLayout()
        career_title = QLabel("선수 경력")
        career_title.setObjectName("CareerTitle")
        career_badge = QLabel("KBO CAREER")
        career_badge.setObjectName("CareerBadge")
        career_header.addWidget(career_title)
        career_header.addStretch()
        career_header.addWidget(career_badge)
        career_layout.addLayout(career_header)
        self.career_timeline_rows = []
        for index in range(4):
            timeline_row = QFrame()
            timeline_row.setObjectName("CareerTimelineRow")
            timeline_layout = QHBoxLayout(timeline_row)
            timeline_layout.setContentsMargins(7, 5, 7, 5)
            timeline_layout.setSpacing(7)
            marker = QLabel("●" if index == 0 else "◆")
            marker.setObjectName("CareerMarker")
            marker.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            marker.setFixedWidth(14)
            text_column = QVBoxLayout()
            text_column.setSpacing(1)
            step_label = QLabel()
            step_label.setObjectName("CareerStep")
            value_label = QLabel()
            value_label.setObjectName("CareerValue")
            value_label.setWordWrap(True)
            text_column.addWidget(step_label)
            text_column.addWidget(value_label)
            timeline_layout.addWidget(marker)
            timeline_layout.addLayout(text_column, 1)
            career_layout.addWidget(timeline_row)
            self.career_timeline_rows.append((step_label, value_label))
        layout.addWidget(career_card, 1)
        grid.addWidget(card, 0, 0, 2, 1)

    def _build_center(self, grid):
        center = QFrame()
        center.setObjectName("CenterCard")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(16, 14, 16, 15)
        layout.setSpacing(11)
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
            box_layout.setContentsMargins(7, 7, 7, 7)
            box_layout.setSpacing(2)
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
        layout.setContentsMargins(14, 14, 14, 15)
        layout.setSpacing(10)
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
        self._set_player_photo(name)
        self.name_label.setText(name)
        self.header_type.setText("투수 PROFILE" if is_pitcher else "타자 PROFILE")
        self.subtitle_label.setText(f"{self.player.get('team', '-')}  ·  {position}")
        self.career_label.setText(_career_summary(self.player))
        self.career_label.setToolTip(f"입단 경로  {self.player.get('career') or '미등록'}")
        reserve_label = (
            "C팀(퓨처스)"
            if self.player.get("team") == "NC 다이노스"
            else "퓨처스팀(2군)"
        )
        self.status_label.setText(
            "● 1군 엔트리"
            if self.player.get("status")
            else f"● {reserve_label} / 육성"
        )

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
        self.registration_status.setText(
            "1군 등록 선수"
            if self.player.get("status")
            else f"육성 · {reserve_label} 선수"
        )
        for (step_label, value_label), (step, value) in zip(
            self.career_timeline_rows, _career_card_data(self.player)
        ):
            step_label.setText(step)
            value_label.setText(value)

        record = self._load_record(is_pitcher)
        ratings = self._current_ratings(is_pitcher)
        overall = round(sum(ratings) / len(ratings), 1) if ratings else None
        stars = self._stars(overall)
        self.current_stars.setText(f"현재 능력  {stars}")
        self.overall_stars.setText(stars)
        self.overall_value.setText(f"{overall} / 20" if overall is not None else "미평가")
        self._set_season_stats(is_pitcher, record)
        self._set_report(is_pitcher)

        source = (
            self.player.get("pitcher_source_level") if is_pitcher
            else self.player.get("ability_source_level")
        ) or "미평가"
        confidence_code = self.player.get("pitcher_confidence") if is_pitcher else ""
        confidence = {"high": "높음", "medium": "보통", "low": "낮음", "none": "자료 없음"}.get(
            confidence_code,
            "높음" if source == "KBO" else "보통" if source == "FUTURES" else "낮음",
        )
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
        if is_pitcher:
            velocity = self.player.get("pitcher_avg_velocity")
            stuff_plus = self.player.get("pitcher_k_stuff_plus")
            location_plus = self.player.get("pitcher_k_location_plus")
            whiff = self.player.get("pitcher_whiff_rate")
            csw = self.player.get("pitcher_csw_rate")
            k_rate = self.player.get("pitcher_k_rate")
            bb_rate = self.player.get("pitcher_bb_rate")
            fip = self.player.get("pitcher_fip")
            repertoire = (self.player.get("pitcher_repertoire") or "미확인").replace(
                "Four-seam", "포심"
            ).replace("Changeup", "체인지업").replace("Slider", "슬라이더").replace(
                "Curve", "커브"
            ).replace("Splitter", "스플리터").replace("Sinker", "싱커").replace(
                "Cutter", "커터"
            ).replace("Sweeper", "스위퍼").replace("Knuckleball", "너클볼")
            velocity_text = f"{float(velocity):.1f}km/h" if velocity is not None else "미확인"
            self.formula_label.setText(f"구종  {repertoire}\n평균 구속  {velocity_text}")
            tracking = []
            if stuff_plus is not None:
                tracking.append(f"K-Stuff+ {float(stuff_plus):.1f}")
            if location_plus is not None:
                tracking.append(f"K-Loc+ {float(location_plus):.1f}")
            if whiff is not None:
                tracking.append(f"Whiff {float(whiff) * 100:.1f}%")
            if csw is not None:
                tracking.append(f"CSW {float(csw) * 100:.1f}%")
            if k_rate is not None:
                tracking.append(f"K% {float(k_rate) * 100:.1f}")
            if bb_rate is not None:
                tracking.append(f"BB% {float(bb_rate) * 100:.1f}")
            if fip is not None:
                tracking.append(f"FIP {float(fip):.2f}")
            if tracking:
                self.formula_label.setText(self.formula_label.text() + "\n" + " · ".join(tracking))
        else:
            source_name = (
                "KBO 공식 + 공개 고급지표"
                if self.player.get("hitter_advanced_public_player_id")
                else "KBO 공식 기록"
            )
            confidence_labels = {
                "high": "높음", "medium": "보통", "low": "낮음",
                "very_low": "매우 낮음", "none": "자료 없음",
            }
            evidence = []
            if self.player.get("hitter_advanced_wrc_plus") is not None:
                evidence.append(f"wRC+ {float(self.player['hitter_advanced_wrc_plus']):.1f}")
            if self.player.get("hitter_advanced_sfr") is not None:
                evidence.append(f"SFR {float(self.player['hitter_advanced_sfr']):+.1f}")
            if self.player.get("hitter_advanced_war") is not None:
                evidence.append(f"WAR {float(self.player['hitter_advanced_war']):.2f}")
            confidence = confidence_labels.get(
                self.player.get("hitter_rating_confidence"), "미확인"
            )
            formula_lines = [
                source_name,
                f"신뢰도 {confidence}",
                " · ".join(evidence) if evidence else "세이버 지표 미확보 · 공식 기록 산정",
            ]
            self.formula_label.setText("\n".join(formula_lines))
        profile = "완료" if self.player.get("profile_complete") else "일부 정보 없음"
        detail_hint = " · O 구종에 마우스를 올리면 세부 가치" if is_pitcher else ""
        self.profile_state_label.setText(f"공식 프로필  {profile}{detail_hint}")

        for label in (self.fitness_value, self.condition_value, self.injury_value, self.morale_value):
            label.setText("미평가")

    def _set_player_photo(self, player_name):
        photo_path = _player_photo_path(
            self.player.get("kbo_player_id"),
            self.player.get("name"),
            self.player.get("team"),
        )
        if photo_path is not None:
            pixmap = QPixmap(str(photo_path))
            if not pixmap.isNull():
                width = max(220, min(self.avatar.width(), 420))
                self.avatar.setText("")
                self.avatar.setPixmap(
                    pixmap.scaled(
                        width,
                        285,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.avatar.setToolTip(str(photo_path))
                return
        self.avatar.setPixmap(QPixmap())
        self.avatar.setText(player_name[-2:])
        self.avatar.setToolTip("로컬 선수 사진 없음")

    def _load_record(self, is_pitcher):
        filename = "kbo_2025_first_team_pitching.csv" if is_pitcher else "kbo_2025_first_team_hitting.csv"
        return _season_records(filename).get(str(self.player.get("kbo_player_id")), {})

    def _current_ratings(self, is_pitcher):
        return core_rating_values(self.player, is_pitcher)

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
                ("구속", self.player.get("pitcher_velocity"), False),
                ("구위", self.player.get("pitcher_stuff"), False),
                ("제구", self.player.get("pitcher_command"), False),
                ("무브먼트", self.player.get("pitcher_movement"), False),
                ("스태미나", self.player.get("pitcher_stamina"), False),
                ("경기 운영", self.player.get("pitcher_pitchability"), False),
                ("탈삼진", self.player.get("pitcher_strikeout"), False),
                ("볼넷 억제", self.player.get("pitcher_walk_control"), False),
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
        missing = "" if is_pitcher else "\n• 수비·멘탈 데이터 미평가" if any(
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
