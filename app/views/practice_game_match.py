"""연습경기 라인업 편성, 문자 중계, 결과를 잇는 전체 화면."""

import csv
import math
from functools import lru_cache

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.teams import TEAM_INFO
from app.services.practice_games import PracticeGameError
from app.player_photos import resolve_player_photo
from app.utils import resource_path
from app.views.live_baseball_field import LiveBaseballField


STADIUM_IMAGE_FILES = {
    "KIA 타이거즈": "kia.jpg", "삼성 라이온즈": "samsung.jpg",
    "LG 트윈스": "jamsil.jpg", "두산 베어스": "jamsil.jpg",
    "KT 위즈": "kt.jpg", "SSG 랜더스": "ssg.jpg",
    "롯데 자이언츠": "lotte.jpg", "한화 이글스": "hanwha.jpg",
    "NC 다이노스": "nc.jpg", "키움 히어로즈": "kiwoom.jpg",
}

TEAM_LOGO_FILES = {
    "KIA 타이거즈": "kia.png", "삼성 라이온즈": "samsung.png",
    "LG 트윈스": "lg.png", "두산 베어스": "doosan.png",
    "KT 위즈": "kt.png", "SSG 랜더스": "ssg.png",
    "롯데 자이언츠": "lotte.png", "한화 이글스": "hanwha.png",
    "NC 다이노스": "nc.png", "키움 히어로즈": "kiwoom.png",
}


@lru_cache(maxsize=1)
def _season_hitting_records():
    """중계 카드에서 사용하는 2025 KBO 공식 타격 기록."""
    path = resource_path("data", "source", "kbo_2025_first_team_hitting.csv")
    if not path.exists():
        return {}
    records = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            player_id = str(row.get("kbo_player_id") or "").strip()
            if player_id:
                records[player_id] = row
    return records


class PracticeFieldWidget(QWidget):
    """실제 구장과 선수 사진을 결합한 중계형 타자 카드."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = {}
        self.player = {}
        self.season = {}
        self.game_stat = {}
        self._stadium = QPixmap()
        self._stadium_path = ""
        self._portrait = QPixmap()
        self.setMinimumSize(430, 360)

    def set_state(self, state):
        self.state = state or {}
        self.update()

    def set_broadcast_context(self, stadium_path, player, season, game_stat=None):
        path = str(stadium_path or "")
        if path and path != self._stadium_path:
            self._stadium = QPixmap(path)
            self._stadium_path = path
        self.player = player or {}
        self.season = season or {}
        self.game_stat = game_stat or {}
        photo = resolve_player_photo(
            self.player.get("kbo_player_id"),
            self.player.get("name"),
            self.player.get("team"),
        )
        self._portrait = QPixmap(str(photo)) if photo else QPixmap()
        self.update()

    @staticmethod
    def _draw_cover(painter, target, pixmap, vertical_focus=.28):
        if pixmap.isNull() or target.width() <= 0 or target.height() <= 0:
            return
        target_ratio = target.width() / target.height()
        source_ratio = pixmap.width() / max(1, pixmap.height())
        if source_ratio > target_ratio:
            crop_width = pixmap.height() * target_ratio
            source = QRectF((pixmap.width() - crop_width) / 2, 0, crop_width, pixmap.height())
        else:
            crop_height = pixmap.width() / target_ratio
            source = QRectF(
                0,
                max(0, (pixmap.height() - crop_height) * vertical_focus),
                pixmap.width(),
                crop_height,
            )
        painter.drawPixmap(target, pixmap, source)

    @staticmethod
    def _value(record, key, fallback="-"):
        value = record.get(key)
        return str(value) if value not in (None, "") else fallback

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        width, height = self.width(), self.height()
        target = QRectF(0, 0, width, height)
        painter.fillRect(target, QColor("#071017"))
        if not self._stadium.isNull():
            self._draw_cover(painter, target, self._stadium, .20)
        shade = QLinearGradient(0, 0, width, 0)
        shade.setColorAt(0, QColor(4, 12, 19, 235))
        shade.setColorAt(.46, QColor(5, 14, 22, 115))
        shade.setColorAt(1, QColor(3, 10, 16, 225))
        painter.fillRect(target, QBrush(shade))

        # 현재 타자 사진
        portrait = QRectF(width * .035, height * .075, width * .36, height * .82)
        if not self._portrait.isNull():
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(portrait, 8, 8)
            painter.setClipPath(clip)
            self._draw_cover(painter, portrait, self._portrait, .08)
            painter.fillRect(portrait, QColor(3, 10, 16, 58))
            painter.restore()
        else:
            painter.setBrush(QBrush(QColor(20, 42, 54, 220)))
            painter.setPen(QPen(QColor("#36566a"), 1))
            painter.drawRoundedRect(portrait, 6, 6)
            painter.setPen(QColor("#718c9d"))
            painter.setFont(QFont("Malgun Gothic", 20, QFont.Weight.Bold))
            painter.drawText(portrait, Qt.AlignmentFlag.AlignCenter, self.player.get("name", "선수"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 54), 1))
        painter.drawRoundedRect(portrait, 8, 8)
        portrait_fade = QLinearGradient(portrait.left(), 0, portrait.right(), 0)
        portrait_fade.setColorAt(.42, QColor(5, 12, 19, 0))
        portrait_fade.setColorAt(1, QColor(5, 12, 19, 248))
        painter.fillRect(portrait, QBrush(portrait_fade))

        info_left = width * .42
        position = self.player.get("live_position") or self.player.get("pos") or "BATTER"
        order = self.player.get("live_order")
        painter.setPen(QColor("#60d5ed"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(QRectF(info_left, height * .09, width * .46, 24), f"{position}   ·   {order}번 타자" if order else str(position))
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Malgun Gothic", 28, QFont.Weight.Bold))
        painter.drawText(QRectF(info_left, height * .15, width * .47, 50), self.player.get("name", "-"))
        painter.setPen(QColor("#8ca5b4"))
        painter.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        painter.drawText(QRectF(info_left, height * .27, width * .45, 22), "2025 KBO 정규시즌 기록")

        stat_top = height * .34
        stat_width = width * .255
        stats = (
            ("타율", self._value(self.season, "AVG")),
            ("홈런", self._value(self.season, "HR", "0")),
            ("타점", self._value(self.season, "RBI", "0")),
            ("OPS", self._value(self.season, "OPS")),
        )
        for index, (label, value) in enumerate(stats):
            column = index % 2
            row = index // 2
            rect = QRectF(info_left + column * (stat_width + 8), stat_top + row * 67, stat_width, 58)
            painter.setBrush(QBrush(QColor(6, 24, 37, 218)))
            painter.setPen(QPen(QColor("#23485f"), 1))
            painter.drawRect(rect)
            painter.setPen(QColor("#6db8d1"))
            painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(9, 5, -7, -29), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(8, 23, -8, -5), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value)

        # 오늘 기록과 주자 상황
        at_bats = int(self.game_stat.get("at_bats", 0))
        hits = int(self.game_stat.get("hits", 0))
        home_runs = int(self.game_stat.get("home_runs", 0))
        rbi = int(self.game_stat.get("rbi", 0))
        today = f"오늘  {at_bats}타수  {hits}안타  {home_runs}홈런  {rbi}타점"
        painter.setBrush(QBrush(QColor(3, 13, 20, 220)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(info_left, height * .76, width * .43, 36))
        painter.setPen(QColor("#e8c15f"))
        painter.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        painter.drawText(QRectF(info_left + 10, height * .76, width * .40, 36), Qt.AlignmentFlag.AlignVCenter, today)

        bases = self.state.get("bases") or {}
        base_center = QPointF(width * .90, height * .88)
        for key, dx, dy in (("1", 15, 0), ("2", 0, -15), ("3", -15, 0)):
            point = QPointF(base_center.x() + dx, base_center.y() + dy)
            occupied = bases.get(key) is not None
            painter.setBrush(QBrush(QColor("#f0b84b") if occupied else QColor("#25343e")))
            painter.setPen(QPen(QColor("#d8e2e7"), 1))
            painter.drawRect(QRectF(point.x() - 5, point.y() - 5, 10, 10))


class InningScoreTable(QTableWidget):
    """두 팀과 모든 이닝을 현재 너비에 맞추는 스크롤 없는 전광판."""

    def __init__(self, parent=None):
        super().__init__(2, 13, parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalHeader().setMinimumSectionSize(16)
        self.horizontalHeader().setFixedHeight(28)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setStretchLastSection(False)
        self.verticalHeader().hide()
        self.verticalHeader().setMinimumSectionSize(20)
        self.setWordWrap(False)

    def fit_scoreboard(self):
        self.setRowHeight(0, 27)
        self.setRowHeight(1, 27)
        self.setFixedHeight(self.horizontalHeader().height() + 54 + 2*self.frameWidth())
        available = self.viewport().width()
        count = self.columnCount() - 1
        if count < 1 or available <= 0:
            return
        team_width = min(180, max(90, round(available * .20)))
        self.setColumnWidth(0, team_width)
        width, extra = divmod(max(count*16, available-team_width), count)
        for column in range(1, count+1):
            self.setColumnWidth(column, width + int(column <= extra))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_scoreboard()


class CountBoardWidget(QFrame):
    """볼·스트라이크·아웃을 색 점으로 즉시 읽게 하는 카운트 보드."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CountBoard")
        layout = QGridLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(5)
        self.lamps = {}
        for row, (key, label, total) in enumerate((("B", "B", 3), ("S", "S", 2), ("O", "O", 2))):
            title = QLabel(label, objectName=f"Count{key}")
            layout.addWidget(title, row, 0)
            dots = []
            for column in range(total):
                dot = QLabel(objectName="CountLamp")
                dot.setFixedSize(11, 11)
                layout.addWidget(dot, row, column + 1)
                dots.append(dot)
            self.lamps[key] = dots
        layout.setColumnStretch(4, 1)
        self.set_count(0, 0, 0)

    def set_count(self, balls, strikes, outs):
        colors = {"B": "#44c377", "S": "#f0b84b", "O": "#ef6262"}
        for key, value in (("B", balls), ("S", strikes), ("O", outs)):
            for index, dot in enumerate(self.lamps[key]):
                fill = colors[key] if index < int(value) else "#26323a"
                dot.setStyleSheet(
                    f"background:{fill}; border:1px solid {fill}; border-radius:5px;"
                )


class PracticeBroadcastIntro(QWidget):
    """장면마다 다른 방송 그래픽을 그리는 경기 인트로 캔버스."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stadium = QPixmap()
        self._progress = 0.0
        self._scene_index = 0
        self._scene_total = 1
        self._scene = {}
        self._portraits = {}
        self._logos = {}
        self.setMinimumHeight(590)

    def set_stadium(self, path):
        self._stadium = QPixmap(str(path)) if path else QPixmap()
        self._progress = 0.0
        self.update()

    def set_scene(self, scene, index, total):
        self._scene = scene or {}
        self._scene_index = int(index)
        self._scene_total = max(1, int(total))
        self._progress = 0.0
        self._portraits = {}
        teams = {
            value for value in (
                self._scene.get("away_team"),
                self._scene.get("home_team"),
                self._scene.get("team"),
                *(player.get("team") for player in self._scene.get("players", ())),
            )
            if value
        }
        self._logos = {
            team: QPixmap(str(resource_path("image", "team_logos", TEAM_LOGO_FILES[team])))
            for team in teams
            if team in TEAM_LOGO_FILES
        }
        for player in self._scene.get("players", ()):
            photo = resolve_player_photo(
                player.get("kbo_player_id"),
                player.get("name"),
                player.get("team"),
            )
            if photo:
                self._portraits[int(player["id"])] = QPixmap(str(photo))
        self.update()

    def advance_frame(self):
        self._progress = min(1.0, self._progress + .0038)
        self.update()

    @staticmethod
    def _font(size, weight=QFont.Weight.Normal):
        return QFont("Malgun Gothic", max(10, int(size)), weight)

    @staticmethod
    def _team_color(team):
        value = TEAM_INFO.get(team, {}).get("colors", {}).get("accent", "#2185b5")
        return QColor(value)

    @staticmethod
    def _draw_cover(painter, target, pixmap, pan=.5, zoom=1.0, focus=.28):
        if pixmap.isNull() or target.width() <= 0 or target.height() <= 0:
            return
        source_width = float(pixmap.width())
        source_height = float(pixmap.height())
        target_ratio = target.width() / max(1.0, target.height())
        source_ratio = source_width / max(1.0, source_height)
        if source_ratio > target_ratio:
            crop_height = source_height / zoom
            crop_width = crop_height * target_ratio
            source = QRectF(
                max(0.0, source_width - crop_width) * max(0.0, min(1.0, pan)),
                max(0.0, source_height - crop_height) * focus,
                crop_width,
                crop_height,
            )
        else:
            crop_width = source_width / zoom
            crop_height = crop_width / target_ratio
            source = QRectF(
                max(0.0, source_width - crop_width) * .5,
                max(0.0, source_height - crop_height) * focus,
                crop_width,
                crop_height,
            )
        painter.drawPixmap(target, pixmap, source)

    @staticmethod
    def _draw_fit(painter, target, pixmap):
        if pixmap.isNull() or target.width() <= 0 or target.height() <= 0:
            return
        ratio = min(
            target.width() / max(1, pixmap.width()),
            target.height() / max(1, pixmap.height()),
        )
        width = pixmap.width() * ratio
        height = pixmap.height() * ratio
        fitted = QRectF(
            target.center().x() - width / 2,
            target.center().y() - height / 2,
            width,
            height,
        )
        painter.drawPixmap(fitted, pixmap, QRectF(pixmap.rect()))

    def _logo(self, painter, rect, team):
        logo = self._logos.get(team, QPixmap())
        if not logo.isNull():
            self._draw_fit(painter, rect, logo)

    def _text(
        self, painter, rect, text, size, color="#ffffff",
        weight=QFont.Weight.Normal, alignment=Qt.AlignmentFlag.AlignLeft,
        wrap=False,
    ):
        painter.setPen(QColor(color))
        painter.setFont(self._font(size, weight))
        flags = alignment | Qt.AlignmentFlag.AlignVCenter
        if wrap:
            flags |= Qt.TextFlag.TextWordWrap
        painter.drawText(rect, flags, str(text))

    def _base(self, painter, darkness=105, clean=False):
        target = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(target, QColor("#05090d"))
        if not self._stadium.isNull():
            direction = self._progress if self._scene_index % 2 == 0 else 1 - self._progress
            zoom = 1.035 + .045 * math.sin(self._progress * math.pi)
            self._draw_cover(painter, target, self._stadium, direction, zoom, .22)
        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0, QColor(2, 6, 9, min(255, darkness + 38)))
        shade.setColorAt(.50, QColor(2, 7, 11, 20 if clean else darkness - 25))
        shade.setColorAt(1, QColor(2, 6, 9, 232))
        painter.fillRect(target, QBrush(shade))

        # 사진 중심과 방송 정보에 시선이 모이도록 좌우 가장자리만 눌러 준다.
        side_shade = QLinearGradient(0, 0, self.width(), 0)
        side_shade.setColorAt(0, QColor(1, 5, 8, 178))
        side_shade.setColorAt(.22, QColor(1, 5, 8, 18))
        side_shade.setColorAt(.78, QColor(1, 5, 8, 18))
        side_shade.setColorAt(1, QColor(1, 5, 8, 178))
        painter.fillRect(target, QBrush(side_shade))

    def _broadcast_bug(self, painter):
        bar = QRectF(28, 22, self.width() - 56, 36)
        painter.setBrush(QBrush(QColor(4, 10, 15, 202)))
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1))
        painter.drawRoundedRect(bar, 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#f2b84b")))
        painter.drawEllipse(QRectF(41, 35, 8, 8))
        self._text(
            painter, QRectF(58, 22, 150, 36), "KBO FM  ·  MATCHDAY", 9,
            "#f5f7f9", QFont.Weight.Bold,
        )
        self._text(
            painter, QRectF(self.width() - 430, 22, 386, 36),
            self._scene.get("stadium", ""), 9, "#b9c6ce",
            QFont.Weight.Bold, Qt.AlignmentFlag.AlignRight,
        )

    def _portrait(self, painter, rect, player, tint=None):
        pixmap = self._portraits.get(int(player.get("id") or 0), QPixmap())
        if not pixmap.isNull():
            self._draw_cover(painter, rect, pixmap, .5, 1.0, .08)
        else:
            painter.fillRect(rect, QColor("#172630"))
            self._text(
                painter, rect, player.get("name", "선수"), 22, "#718895",
                QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
            )
        fade = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        fade.setColorAt(.48, QColor(4, 10, 14, 0))
        fade.setColorAt(1, QColor(4, 10, 14, 235))
        painter.fillRect(rect, QBrush(fade))
        if tint:
            color = QColor(tint)
            color.setAlpha(38)
            painter.fillRect(rect, color)

    def _paint_venue(self, painter):
        self._base(painter, 58, clean=True)
        self._broadcast_bug(painter)
        scene = self._scene
        left = 58
        bottom = self.height() - 126
        title_band = QRectF(28, bottom - 160, self.width() - 56, 150)
        painter.setBrush(QBrush(QColor(3, 9, 14, 186)))
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        painter.drawRoundedRect(title_band, 12, 12)
        self._text(
            painter, QRectF(left, bottom - 139, self.width() * .62, 25),
            "TODAY'S BALLPARK", 10, "#70d5eb", QFont.Weight.Bold,
        )
        self._text(
            painter, QRectF(left, bottom - 110, self.width() * .62, 54),
            scene.get("title", "경기장"), 34, "#ffffff", QFont.Weight.Bold,
        )
        self._text(
            painter, QRectF(left, bottom - 57, self.width() * .62, 31),
            scene.get("subtitle", ""), 12, "#c1cdd4", QFont.Weight.Bold,
        )
        card = QRectF(self.width() - 430, bottom - 135, 370, 100)
        painter.setBrush(QBrush(QColor(9, 18, 24, 216)))
        painter.setPen(QPen(QColor(255, 255, 255, 34), 1))
        painter.drawRoundedRect(card, 8, 8)
        self._text(
            painter, card.adjusted(18, 9, -18, -68), "PRACTICE MATCH", 9,
            "#f2b84b", QFont.Weight.Bold,
        )
        self._text(
            painter, card.adjusted(18, 30, -18, -37), scene.get("matchup", ""),
            16, "#ffffff", QFont.Weight.Bold,
        )
        self._text(
            painter, card.adjusted(18, 66, -18, -8), scene.get("meta", ""),
            10, "#91a4b0",
        )

    def _paint_matchup(self, painter):
        self._base(painter, 188)
        self._broadcast_bug(painter)
        away = self._scene.get("away_team", "AWAY")
        home = self._scene.get("home_team", "HOME")
        width = self.width()
        content = QRectF(42, 78, width - 84, self.height() - 225)
        gap = 16
        half = (content.width() - gap) / 2
        panels = (
            (QRectF(content.left(), content.top(), half, content.height()), away, "AWAY"),
            (QRectF(content.left() + half + gap, content.top(), half, content.height()), home, "HOME"),
        )
        for rect, team, side in panels:
            color = self._team_color(team)
            painter.setBrush(QBrush(QColor(5, 13, 19, 218)))
            painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
            painter.drawRoundedRect(rect, 12, 12)
            painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 6), color)
            dark = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
            tint = QColor(color)
            tint.setAlpha(74)
            dark.setColorAt(0, tint)
            dark.setColorAt(1, QColor(3, 8, 12, 20))
            painter.fillRect(rect.adjusted(0, 6, 0, 0), QBrush(dark))
            self._text(
                painter, rect.adjusted(28, 24, -28, -rect.height() + 57),
                side, 10, "#dce7ed", QFont.Weight.Bold,
            )
            self._logo(
                painter,
                QRectF(rect.center().x() - 62, rect.top() + 76, 124, 124),
                team,
            )
            self._text(
                painter, QRectF(rect.left() + 28, rect.top() + 214, rect.width() - 56, 54), team, 29,
                "#ffffff", QFont.Weight.Bold,
                Qt.AlignmentFlag.AlignCenter,
            )
            info = self._scene.get("team_info", {}).get(team, "")
            self._text(
                painter, rect.adjusted(28, rect.height() - 102, -28, -24),
                info, 11, "#cbd6dc", QFont.Weight.Normal,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, True,
            )
        center = QPointF(width / 2, content.center().y())
        painter.setBrush(QBrush(QColor(5, 12, 18, 235)))
        painter.setPen(QPen(QColor("#f2b84b"), 2))
        painter.drawEllipse(center, 42, 42)
        self._text(
            painter, QRectF(center.x() - 42, center.y() - 42, 84, 84),
            "VS", 18, "#ffffff", QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
        )

    def _paint_story(self, painter):
        self._base(painter, 172)
        self._broadcast_bug(painter)
        self._text(
            painter, QRectF(48, 82, self.width() - 96, 32),
            "MATCH PREVIEW", 10, "#e5ad4f", QFont.Weight.Bold,
        )
        self._text(
            painter, QRectF(48, 112, self.width() - 96, 50),
            self._scene.get("title", "오늘의 관전 포인트"), 29,
            "#ffffff", QFont.Weight.Bold,
        )
        stories = self._scene.get("stories", ())
        gap = 15
        count = max(1, len(stories))
        card_width = min(
            465,
            (self.width() - 96 - gap * max(0, count - 1)) / count,
        )
        group_width = card_width * count + gap * max(0, count - 1)
        start_x = (self.width() - group_width) / 2
        for index, story in enumerate(stories):
            rect = QRectF(
                start_x + index * (card_width + gap), 190,
                card_width, min(340, self.height() - 340),
            )
            painter.setBrush(QBrush(QColor(7, 16, 22, 218)))
            painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
            painter.drawRoundedRect(rect, 10, 10)
            self._text(
                painter, rect.adjusted(20, 16, -20, -rect.height() + 47),
                f"0{index + 1}", 11, "#67d1e9", QFont.Weight.Bold,
            )
            self._text(
                painter, rect.adjusted(20, 58, -20, -rect.height() + 102),
                story.get("title", ""), 17, "#ffffff", QFont.Weight.Bold,
            )
            self._text(
                painter, rect.adjusted(20, 111, -20, -20), story.get("body", ""),
                11, "#aebdc6", QFont.Weight.Normal,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, True,
            )

    def _paint_pitchers(self, painter):
        self._base(painter, 212)
        self._broadcast_bug(painter)
        players = list(self._scene.get("players", ()))
        if len(players) < 2:
            return
        self._text(
            painter, QRectF(0, 62, self.width(), 28), "STARTING PITCHERS", 10,
            "#e5ad4f", QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
        )
        self._text(
            painter, QRectF(0, 88, self.width(), 44), "오늘의 선발 매치업", 27,
            "#ffffff", QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
        )
        portrait_width = min(390, self.width() * .29)
        portrait_height = self.height() - 285
        left_rect = QRectF(80, 145, portrait_width, portrait_height)
        right_rect = QRectF(self.width() - 80 - portrait_width, 145, portrait_width, portrait_height)
        for player, rect in ((players[0], left_rect), (players[1], right_rect)):
            color = self._team_color(player.get("team"))
            painter.setBrush(QBrush(QColor(5, 13, 19, 232)))
            painter.setPen(QPen(color, 3))
            painter.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), 9, 9)
            self._portrait(painter, rect, player, color)
            self._logo(
                painter, QRectF(rect.left() + 16, rect.top() + 16, 54, 54),
                player.get("team"),
            )
            self._text(
                painter, rect.adjusted(18, rect.height() - 104, -18, -68),
                player.get("team", ""), 10, "#78d6ec", QFont.Weight.Bold,
            )
            self._text(
                painter, rect.adjusted(18, rect.height() - 73, -18, -27),
                player.get("name", ""), 25, "#ffffff", QFont.Weight.Bold,
            )
            metrics = (
                f"능력 {player.get('rating', '-')}  ·  컨디션 {player.get('condition', '-')}  ·  "
                f"구위 {player.get('pitcher_stuff', '-')}"
            )
            self._text(
                painter, rect.adjusted(18, rect.height() - 33, -18, -7),
                metrics, 9, "#c3d0d7", QFont.Weight.Bold,
            )
        center = QRectF(self.width() / 2 - 70, self.height() / 2 - 45, 140, 90)
        self._text(
            painter, center, "VS", 35, "#ffffff", QFont.Weight.Bold,
            Qt.AlignmentFlag.AlignCenter,
        )

    def _paint_lineup(self, painter):
        self._base(painter, 218)
        self._broadcast_bug(painter)
        scene = self._scene
        team = scene.get("team", "")
        color = self._team_color(team)
        painter.fillRect(QRectF(0, 72, 8, self.height() - 205), color)
        self._text(
            painter, QRectF(42, 74, self.width() * .58, 26),
            scene.get("side", "STARTING LINEUP"), 10, "#e5ad4f", QFont.Weight.Bold,
        )
        self._text(
            painter, QRectF(88, 100, self.width() * .53, 46), team, 27,
            "#ffffff", QFont.Weight.Bold,
        )
        self._logo(painter, QRectF(42, 101, 38, 38), team)
        lineup = scene.get("lineup", ())
        panel = QRectF(42, 160, self.width() * .58, self.height() - 315)
        row_height = panel.height() / 9
        for index, player in enumerate(lineup):
            rect = QRectF(
                panel.left(), panel.top() + index * row_height, panel.width(),
                row_height - 6,
            )
            fill = QColor(7, 16, 22, 224 if index % 2 == 0 else 206)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
            painter.drawRoundedRect(rect, 6, 6)
            self._text(
                painter, rect.adjusted(13, 0, -rect.width() + 48, 0),
                str(player.get("batting_order", "")), 15, "#69d2e9", QFont.Weight.Bold,
                Qt.AlignmentFlag.AlignCenter,
            )
            self._text(
                painter, rect.adjusted(54, 0, -rect.width() + 235, 0), player.get("name", ""),
                14, "#ffffff", QFont.Weight.Bold,
            )
            self._text(
                painter, rect.adjusted(238, 0, -rect.width() + 300, 0),
                player.get("position", ""), 10, "#91a5b0", QFont.Weight.Bold,
                Qt.AlignmentFlag.AlignCenter,
            )
            avg = str(player.get("season_avg") or "-").removeprefix("0")
            obp = str(player.get("season_obp") or "-").removeprefix("0")
            ops = str(player.get("season_ops") or "-").removeprefix("0")
            self._text(
                painter, rect.adjusted(315, 0, -14, 0),
                f"2025  AVG {avg}   OBP {obp}   OPS {ops}",
                10, "#bdcbd3", QFont.Weight.Bold,
                Qt.AlignmentFlag.AlignRight,
            )
        key_player = scene.get("key_player") or (lineup[0] if lineup else {})
        feature = QRectF(self.width() * .65, 105, self.width() * .31, self.height() - 260)
        painter.setBrush(QBrush(QColor(5, 13, 19, 222)))
        painter.setPen(QPen(color, 2))
        painter.drawRoundedRect(feature.adjusted(-3, -3, 3, 3), 10, 10)
        self._portrait(painter, feature, key_player, color)
        self._text(
            painter, feature.adjusted(20, 18, -20, -feature.height() + 46),
            "KEY BATTER", 10, "#e5ad4f", QFont.Weight.Bold,
        )
        self._text(
            painter, feature.adjusted(20, feature.height() - 90, -20, -48),
            key_player.get("name", ""), 24, "#ffffff", QFont.Weight.Bold,
        )
        self._text(
            painter, feature.adjusted(20, feature.height() - 47, -20, -12),
            f"{key_player.get('position', '')}  ·  2025 AVG "
            f"{str(key_player.get('season_avg') or '-').removeprefix('0')}  ·  "
            f"OPS {str(key_player.get('season_ops') or '-').removeprefix('0')}",
            10, "#c3d0d7", QFont.Weight.Bold,
        )

    def _paint_lineups(self, painter):
        """양 팀 타순을 한 흐름 안에서 비교하는 통합 라인업 장면."""
        self._base(painter, 214)
        self._broadcast_bug(painter)
        scene = self._scene
        away_team = scene.get("away_team", "AWAY")
        home_team = scene.get("home_team", "HOME")
        self._text(
            painter, QRectF(0, 68, self.width(), 24), "STARTING LINEUPS", 10,
            "#f2b84b", QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
        )
        self._text(
            painter, QRectF(0, 91, self.width(), 42), "오늘의 선발 타순", 26,
            "#ffffff", QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
        )

        margin = 42
        gap = 18
        column_width = (self.width() - margin * 2 - gap) / 2
        content_top = 145
        content_bottom = self.height() - 142
        for column, (team, side, lineup) in enumerate((
            (away_team, "AWAY", scene.get("away_lineup", ())),
            (home_team, "HOME", scene.get("home_lineup", ())),
        )):
            left = margin + column * (column_width + gap)
            color = self._team_color(team)
            header = QRectF(left, content_top, column_width, 58)
            painter.setBrush(QBrush(QColor(6, 15, 21, 232)))
            painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
            painter.drawRoundedRect(header, 9, 9)
            painter.fillRect(QRectF(left, content_top, 5, 58), color)
            self._logo(
                painter, QRectF(left + 17, content_top + 10, 38, 38), team
            )
            self._text(
                painter, QRectF(left + 68, content_top + 5, column_width - 88, 22),
                side, 9, "#8fa1ad", QFont.Weight.Bold,
            )
            self._text(
                painter, QRectF(left + 68, content_top + 23, column_width - 88, 28),
                team, 17, "#ffffff", QFont.Weight.Bold,
            )

            rows_top = content_top + 68
            row_height = (content_bottom - rows_top) / 9
            for index, player in enumerate(lineup):
                rect = QRectF(
                    left, rows_top + index * row_height,
                    column_width, row_height - 5,
                )
                painter.setBrush(QBrush(QColor(5, 14, 20, 222 if index % 2 == 0 else 198)))
                painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
                painter.drawRoundedRect(rect, 5, 5)
                self._text(
                    painter, QRectF(rect.left() + 8, rect.top(), 36, rect.height()),
                    str(player.get("batting_order", index + 1)), 13,
                    "#69d2e9", QFont.Weight.Bold, Qt.AlignmentFlag.AlignCenter,
                )
                self._text(
                    painter, QRectF(rect.left() + 48, rect.top(), 46, rect.height()),
                    player.get("position", ""), 9, "#8297a4", QFont.Weight.Bold,
                    Qt.AlignmentFlag.AlignCenter,
                )
                self._text(
                    painter, QRectF(rect.left() + 103, rect.top(), 170, rect.height()),
                    player.get("name", ""), 12, "#ffffff", QFont.Weight.Bold,
                )
                avg = str(player.get("season_avg") or "-").removeprefix("0")
                ops = str(player.get("season_ops") or "-").removeprefix("0")
                self._text(
                    painter,
                    QRectF(rect.left() + 285, rect.top(), rect.width() - 299, rect.height()),
                    f"AVG {avg}    OPS {ops}", 9, "#aebdc6", QFont.Weight.Bold,
                    Qt.AlignmentFlag.AlignRight,
                )

    def _paint_watchlist(self, painter):
        self._base(painter, 202)
        self._broadcast_bug(painter)
        self._text(
            painter, QRectF(48, 83, self.width() - 96, 30),
            "ROSTER WATCH", 10, "#e5ad4f", QFont.Weight.Bold,
        )
        self._text(
            painter, QRectF(48, 112, self.width() - 96, 48),
            "오늘 기회를 받은 선수들", 28, "#ffffff", QFont.Weight.Bold,
        )
        players = list(self._scene.get("players", ()))[:4]
        gap = 14
        count = max(1, len(players))
        width = min(
            330,
            (self.width() - 96 - gap * max(0, count - 1)) / count,
        )
        group_width = width * count + gap * max(0, count - 1)
        start_x = (self.width() - group_width) / 2
        for index, player in enumerate(players):
            rect = QRectF(
                start_x + index * (width + gap), 185,
                width, min(500, self.height() - 335),
            )
            color = self._team_color(player.get("team"))
            painter.fillRect(rect, QColor(8, 18, 25, 230))
            painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 5), color)
            portrait = QRectF(
                rect.left(), rect.top() + 5, rect.width(), rect.height() - 124,
            )
            self._portrait(painter, portrait, player, color)
            self._logo(
                painter, QRectF(rect.left() + 17, rect.top() + 17, 46, 46),
                player.get("team"),
            )
            self._text(
                painter, QRectF(rect.left() + 18, rect.bottom() - 112, rect.width() - 36, 24),
                player.get("team", ""), 9, "#7bcfe3", QFont.Weight.Bold,
            )
            self._text(
                painter, QRectF(rect.left() + 18, rect.bottom() - 89, rect.width() - 36, 38),
                player.get("name", ""), 19, "#ffffff", QFont.Weight.Bold,
            )
            self._text(
                painter, QRectF(rect.left() + 18, rect.bottom() - 49, rect.width() - 36, 30),
                f"{player.get('position', '')}  ·  능력 {player.get('rating', '-')}  ·  "
                f"컨디션 {player.get('condition', '-')}",
                10, "#acbbc4", QFont.Weight.Bold,
            )

    def _paint_play_ball(self, painter):
        self._base(painter, 72, clean=True)
        self._broadcast_bug(painter)
        pulse = .78 + .22 * math.sin(self._progress * math.pi)
        accent = QColor("#e5ad4f")
        accent.setAlpha(int(255 * pulse))
        painter.setPen(QPen(accent, 2))
        center_y = self.height() // 2
        painter.drawLine(150, center_y - 58, self.width() - 150, center_y - 58)
        self._text(
            painter, QRectF(0, center_y - 55, self.width(), 112),
            "PLAY BALL", 50, "#ffffff", QFont.Weight.Bold,
            Qt.AlignmentFlag.AlignCenter,
        )
        painter.drawLine(150, center_y + 60, self.width() - 150, center_y + 60)
        self._text(
            painter, QRectF(0, center_y + 72, self.width(), 32),
            self._scene.get("subtitle", ""), 13, "#d8e2e7", QFont.Weight.Bold,
            Qt.AlignmentFlag.AlignCenter,
        )

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        kind = self._scene.get("kind", "venue")
        renderer = {
            "venue": self._paint_venue,
            "matchup": self._paint_matchup,
            "story": self._paint_story,
            "pitchers": self._paint_pitchers,
            "lineup": self._paint_lineup,
            "lineups": self._paint_lineups,
            "watchlist": self._paint_watchlist,
            "play_ball": self._paint_play_ball,
        }.get(kind, self._paint_venue)
        renderer(painter)


class PracticeGameMatchPage(QWidget):
    """DEBUG 계정에서 실제 연습경기를 진행하는 4단계 화면."""

    back_requested = Signal()
    completed = Signal()

    def __init__(self, colors, service, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.service = service
        self.game_id = None
        self.game = None
        self.players = []
        self.player_maps = {}
        self.live_roster = []
        self.lineup = []
        self.match = None
        self.live_state = None
        self._pending_progress = None
        self.play_index = 0
        self.intro_scene_index = 0
        self.intro_scenes = []
        self.intro_starting = False
        self.intro_transitioning = False
        self.intro_fade_out = None
        self.intro_fade_in = None
        self.fast_timer = QTimer(self)
        self.fast_timer.setInterval(520)
        self.fast_timer.timeout.connect(self._show_next_play)
        self.intro_motion_timer = QTimer(self)
        self.intro_motion_timer.setInterval(40)
        self.intro_motion_timer.timeout.connect(self._advance_intro_frame)
        self.intro_scene_timer = QTimer(self)
        self.intro_scene_timer.setSingleShot(True)
        self.intro_scene_timer.setInterval(2800)
        self.intro_scene_timer.timeout.connect(self._advance_intro_scene)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(objectName="MatchHeader")
        self.match_header = header
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(18, 10, 20, 10)
        self.back_button = QPushButton("←  일정", objectName="BackButton")
        self.back_button.clicked.connect(self._back)
        header_row.addWidget(self.back_button)
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("DEBUG MATCH LAB", objectName="MatchEyebrow"))
        self.header_title = QLabel("연습경기", objectName="MatchTitle")
        title_box.addWidget(self.header_title)
        header_row.addLayout(title_box)
        header_row.addStretch()
        self.stage_label = QLabel(
            "1  LINEUP   ›   2  INTRO   ›   3  MATCH   ›   4  RESULT"
        )
        self.stage_label.setObjectName("StageLabel")
        header_row.addWidget(self.stage_label)
        root.addWidget(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._lineup_page())
        self.stack.addWidget(self._intro_page())
        self.stack.addWidget(self._match_page())
        self.stack.addWidget(self._result_page())
        root.addWidget(self.stack, 1)
        self.setStyleSheet(self._style())

    def _lineup_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 16, 18, 18)
        outer.setSpacing(14)

        hero = QFrame(objectName="LineupHero")
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(22, 15, 20, 15)
        hero_row.setSpacing(20)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(3)
        hero_text.addWidget(QLabel("PRACTICE MATCH · MATCHDAY", objectName="HeroEyebrow"))
        self.lineup_match_title = QLabel("연습경기 매치 플랜", objectName="HeroTitle")
        hero_text.addWidget(self.lineup_match_title)
        self.game_summary = QLabel(objectName="GameSummary")
        hero_text.addWidget(self.game_summary)
        hero_row.addLayout(hero_text, 1)
        divider = QFrame(objectName="HeroDivider")
        divider.setFixedWidth(1)
        hero_row.addWidget(divider)
        status_box = QVBoxLayout()
        status_box.setSpacing(3)
        status_box.addWidget(QLabel("MATCH STATUS", objectName="TinyLabel"))
        status_box.addWidget(QLabel("●  라인업 편성 중", objectName="ReadyStatus"))
        status_box.addWidget(QLabel("선발 9명과 선발투수를 확정하세요", objectName="Muted"))
        hero_row.addLayout(status_box)
        outer.addWidget(hero)

        control_bar = QFrame(objectName="LineupToolbar")
        auto_row = QHBoxLayout(control_bar)
        auto_row.setContentsMargins(14, 8, 14, 8)
        auto_row.setSpacing(8)
        auto_row.addWidget(QLabel("빠른 편성", objectName="ToolbarTitle"))
        for label, mode in (
            ("1군 중심", "first"),
            ("1·2군 혼합", "mixed"),
            ("2군 점검", "second"),
        ):
            button = QPushButton(label, objectName="SegmentButton")
            button.clicked.connect(
                lambda _checked=False, selected_mode=mode: self._auto_lineup(selected_mode)
            )
            auto_row.addWidget(button)
        auto_row.addStretch()
        auto_row.addWidget(QLabel("선수를 더블클릭해 직접 교체할 수 있습니다", objectName="Muted"))
        outer.addWidget(control_bar)

        body = QHBoxLayout()
        body.setSpacing(12)
        roster_card = QFrame(objectName="RosterCard")
        roster_box = QVBoxLayout(roster_card)
        roster_box.setContentsMargins(0, 0, 0, 0)
        roster_head = QFrame(objectName="CardHeader")
        roster_head_row = QHBoxLayout(roster_head)
        roster_head_row.setContentsMargins(16, 11, 14, 9)
        roster_head_row.addWidget(QLabel("선수단", objectName="CardTitle"))
        roster_head_row.addStretch()
        roster_head_row.addWidget(QLabel("야수 후보", objectName="CardMeta"))
        roster_box.addWidget(roster_head)
        self.roster_tabs = QTabWidget()
        self.roster_tabs.setObjectName("RosterTabs")
        self.first_table = self._roster_table()
        self.second_table = self._roster_table()
        self.roster_tabs.addTab(self.first_table, "1군 선수단")
        self.roster_tabs.addTab(self.second_table, "2군 선수단")
        roster_box.addWidget(self.roster_tabs, 1)
        body.addWidget(roster_card, 47)

        lineup_card = QFrame(objectName="LineupCard")
        lineup_box = QVBoxLayout(lineup_card)
        lineup_box.setContentsMargins(0, 0, 0, 0)
        lineup_head = QFrame(objectName="CardHeader")
        lineup_head_row = QHBoxLayout(lineup_head)
        lineup_head_row.setContentsMargins(16, 11, 14, 9)
        lineup_head_row.addWidget(QLabel("STARTING LINEUP", objectName="CardTitle"))
        lineup_head_row.addStretch()
        self.lineup_count = QLabel(objectName="Muted")
        lineup_head_row.addWidget(self.lineup_count)
        lineup_box.addWidget(lineup_head)
        self.lineup_table = QTableWidget(0, 7)
        self.lineup_table.setObjectName("LineupTable")
        self.lineup_table.setHorizontalHeaderLabels(
            ("타순", "선수", "2025 타율", "OPS", "군", "수비 위치", "능력")
        )
        self._polish_table(self.lineup_table, 39)
        self.lineup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.lineup_table.setColumnWidth(0, 54)
        self.lineup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in (
            (2, 82), (3, 76), (4, 54), (5, 108), (6, 62),
        ):
            self.lineup_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.lineup_table.setColumnWidth(column, width)
        self.lineup_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.lineup_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        lineup_box.addWidget(self.lineup_table, 1)

        footer = QFrame(objectName="LineupFooter")
        footer_box = QVBoxLayout(footer)
        footer_box.setContentsMargins(14, 9, 14, 12)
        footer_box.setSpacing(8)
        order_row = QHBoxLayout()
        order_row.addWidget(QLabel("타순 조정", objectName="TinyLabel"))
        order_row.addStretch()
        up = QPushButton("↑", objectName="IconButton")
        down = QPushButton("↓", objectName="IconButton")
        remove = QPushButton("선발 제외", objectName="DangerGhostButton")
        up.clicked.connect(lambda: self._move_lineup(-1))
        down.clicked.connect(lambda: self._move_lineup(1))
        remove.clicked.connect(self._remove_lineup)
        order_row.addWidget(up)
        order_row.addWidget(down)
        order_row.addWidget(remove)
        footer_box.addLayout(order_row)

        pitcher_row = QHBoxLayout()
        pitcher_text = QVBoxLayout()
        pitcher_text.setSpacing(1)
        pitcher_text.addWidget(QLabel("선발투수", objectName="SectionLabel"))
        pitcher_text.addWidget(QLabel("첫 이닝을 맡을 투수를 선택하세요", objectName="Muted"))
        pitcher_row.addLayout(pitcher_text)
        pitcher_row.addStretch()
        self.pitcher_combo = QComboBox()
        self.pitcher_combo.setMinimumWidth(310)
        pitcher_row.addWidget(self.pitcher_combo)
        footer_box.addLayout(pitcher_row)
        self.start_button = QPushButton("라인업 확정하고 경기장 입장  →", objectName="PrimaryButton")
        self.start_button.clicked.connect(self._start_game)
        footer_box.addWidget(self.start_button)
        lineup_box.addWidget(footer)
        body.addWidget(lineup_card, 53)
        outer.addLayout(body, 1)
        return page

    def _intro_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.intro_canvas = PracticeBroadcastIntro()
        self.intro_opacity = QGraphicsOpacityEffect(self.intro_canvas)
        self.intro_opacity.setOpacity(1.0)
        self.intro_canvas.setGraphicsEffect(self.intro_opacity)
        self.intro_fade_out = QPropertyAnimation(
            self.intro_opacity, b"opacity", self
        )
        self.intro_fade_out.setDuration(260)
        self.intro_fade_out.setStartValue(1.0)
        self.intro_fade_out.setEndValue(0.0)
        self.intro_fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self.intro_fade_out.finished.connect(self._swap_intro_scene)
        self.intro_fade_in = QPropertyAnimation(
            self.intro_opacity, b"opacity", self
        )
        self.intro_fade_in.setDuration(430)
        self.intro_fade_in.setStartValue(0.0)
        self.intro_fade_in.setEndValue(1.0)
        self.intro_fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.intro_fade_in.finished.connect(self._finish_intro_transition)
        canvas_layout = QVBoxLayout(self.intro_canvas)
        canvas_layout.setContentsMargins(34, 24, 34, 26)
        canvas_layout.setSpacing(0)
        top_controls = QHBoxLayout()
        top_controls.addStretch()
        self.intro_skip_button = QPushButton(
            "SKIP INTRO  ›", objectName="BroadcastSkipButton"
        )
        self.intro_skip_button.clicked.connect(self._begin_live_game)
        top_controls.addWidget(self.intro_skip_button)
        canvas_layout.addLayout(top_controls)
        canvas_layout.addStretch()

        caption = QFrame(objectName="BroadcastCaption")
        caption_row = QHBoxLayout(caption)
        caption_row.setContentsMargins(20, 12, 14, 12)
        caption_row.setSpacing(14)
        live_mark = QLabel("●", objectName="BroadcastLiveDot")
        live_mark.setAlignment(Qt.AlignmentFlag.AlignTop)
        caption_row.addWidget(live_mark)
        caption_text = QVBoxLayout()
        caption_text.setSpacing(2)
        self.intro_caption_label = QLabel("CASTER", objectName="BroadcastCaptionLabel")
        caption_text.addWidget(self.intro_caption_label)
        self.intro_caster = QLabel(objectName="BroadcastCasterText")
        self.intro_caster.setWordWrap(True)
        caption_text.addWidget(self.intro_caster)
        caption_row.addLayout(caption_text, 1)
        self.intro_counter = QLabel("", objectName="BroadcastSequenceDots")
        self.intro_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption_row.addWidget(self.intro_counter)
        self.intro_next_button = QPushButton(
            "다음  ›", objectName="BroadcastNextButton"
        )
        self.intro_next_button.clicked.connect(self._advance_intro_scene)
        caption_row.addWidget(self.intro_next_button)
        canvas_layout.addWidget(caption)
        outer.addWidget(self.intro_canvas)
        return page

    def _roster_table(self):
        table = QTableWidget(0, 6)
        table.setObjectName("RosterTable")
        table.setHorizontalHeaderLabels(
            ("선수", "포지션", "능력", "컨디션", "피로", "실전감각")
        )
        self._polish_table(table, 39)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 72), (2, 60), (3, 66), (4, 60), (5, 72)):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(column, width)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.itemDoubleClicked.connect(
            lambda _item, source=table: self._add_selected_player(source)
        )
        return table

    @staticmethod
    def _polish_table(table, row_height=38):
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(row_height)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _match_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(10)

        scoreboard = QFrame(objectName="Scoreboard")
        score_row = QHBoxLayout(scoreboard)
        score_row.setContentsMargins(26, 10, 26, 10)
        self.managed_name = QLabel(objectName="ScoreTeam")
        self.managed_name.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.managed_score = QLabel("0", objectName="ScoreNumber")
        middle_box = QVBoxLayout()
        middle_box.setSpacing(0)
        self.match_state = QLabel("경기 준비", objectName="MatchState")
        self.match_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        versus = QLabel("VS", objectName="ScoreDivider")
        versus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        middle_box.addWidget(self.match_state)
        middle_box.addWidget(versus)
        self.opponent_score = QLabel("0", objectName="ScoreNumber")
        self.opponent_name = QLabel(objectName="ScoreTeam")
        score_row.addWidget(self.managed_name, 3)
        score_row.addWidget(self.managed_score)
        score_row.addLayout(middle_box)
        score_row.addWidget(self.opponent_score)
        score_row.addWidget(self.opponent_name, 3)
        outer.addWidget(scoreboard)

        self.inning_table = InningScoreTable()
        self.inning_table.setObjectName("InningScore")
        self._polish_table(self.inning_table, 27)
        self.inning_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.inning_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        outer.addWidget(self.inning_table)

        live_body = QHBoxLayout()
        live_body.setSpacing(10)

        manager_card = QFrame(objectName="ManagerDock")
        manager_card.setMinimumWidth(235)
        manager_card.setMaximumWidth(275)
        manager_box = QVBoxLayout(manager_card)
        manager_box.setContentsMargins(0, 0, 0, 0)
        manager_head = QFrame(objectName="DockHeader")
        manager_head_box = QVBoxLayout(manager_head)
        manager_head_box.setContentsMargins(15, 11, 15, 10)
        manager_head_box.setSpacing(1)
        manager_head_box.addWidget(QLabel("MANAGER DUGOUT", objectName="DockEyebrow"))
        manager_head_box.addWidget(QLabel("감독 지시", objectName="DockTitle"))
        manager_box.addWidget(manager_head)
        pitcher_panel = QFrame(objectName="PitcherPanel")
        pitcher_panel_box = QVBoxLayout(pitcher_panel)
        pitcher_panel_box.setContentsMargins(14, 9, 14, 9)
        pitcher_panel_box.setSpacing(1)
        pitcher_panel_box.addWidget(QLabel("ON THE MOUND", objectName="TinyLabel"))
        self.current_pitcher_label = QLabel("투수 -", objectName="CurrentPitcher")
        pitcher_panel_box.addWidget(self.current_pitcher_label)
        self.current_pitcher_stat = QLabel("0구 · 0K · 0실점", objectName="PitcherStat")
        pitcher_panel_box.addWidget(self.current_pitcher_stat)
        manager_box.addWidget(pitcher_panel)
        command_box = QVBoxLayout()
        command_box.setContentsMargins(14, 13, 14, 13)
        command_box.setSpacing(8)
        command_box.addWidget(QLabel("공격 전술", objectName="SectionLabel"))
        command_box.addWidget(QLabel("우리 팀 공격 중에 적용됩니다", objectName="Muted"))
        self.offense_strategy = QComboBox()
        self.offense_strategy.addItems(("균형", "적극 타격", "신중 승부", "번트"))
        command_box.addWidget(self.offense_strategy)
        self.steal_button = QPushButton("주자에게 도루 지시", objectName="CommandButton")
        self.steal_button.clicked.connect(self._request_steal)
        command_box.addWidget(self.steal_button)
        command_box.addSpacing(12)
        command_box.addWidget(QLabel("수비 전술", objectName="SectionLabel"))
        command_box.addWidget(QLabel("우리 팀 수비 중에 적용됩니다", objectName="Muted"))
        self.defense_strategy = QComboBox()
        self.defense_strategy.addItems(("균형", "공격적 승부", "유인구"))
        command_box.addWidget(self.defense_strategy)
        command_box.addSpacing(12)
        command_box.addWidget(QLabel("불펜 운용", objectName="SectionLabel"))
        self.live_pitcher_combo = QComboBox()
        command_box.addWidget(self.live_pitcher_combo)
        change = QPushButton("선택한 투수로 교체", objectName="CommandButton")
        change.clicked.connect(self._change_pitcher)
        command_box.addWidget(change)
        command_box.addStretch()
        manager_box.addLayout(command_box, 1)
        live_body.addWidget(manager_card)

        field_card = QFrame(objectName="PitchCard")
        field_box = QVBoxLayout(field_card)
        field_box.setContentsMargins(0, 0, 0, 0)
        pitch_head = QFrame(objectName="PitchHeader")
        pitch_head_row = QHBoxLayout(pitch_head)
        pitch_head_row.setContentsMargins(15, 8, 12, 8)
        pitch_head_row.addWidget(QLabel("BROADCAST MATCH VIEW", objectName="DockEyebrow"))
        pitch_head_row.addStretch()
        self.stadium_label = QLabel("구장", objectName="StadiumLabel")
        pitch_head_row.addWidget(self.stadium_label)
        pitch_head_row.addWidget(QLabel("LIVE", objectName="LiveBadge"))
        field_box.addWidget(pitch_head)
        self.field = LiveBaseballField()
        self.field.animation_finished.connect(self._finish_pitch_animation)
        field_box.addWidget(self.field, 1)
        matchup = QFrame(objectName="MatchupBar")
        matchup_row = QHBoxLayout(matchup)
        matchup_row.setContentsMargins(15, 8, 13, 8)
        matchup_text = QVBoxLayout()
        matchup_text.setSpacing(1)
        matchup_text.addWidget(QLabel("CURRENT MATCHUP", objectName="TinyLabel"))
        self.matchup_label = QLabel("타자 -  ·  투수 -", objectName="MatchupLabel")
        matchup_text.addWidget(self.matchup_label)
        matchup_row.addLayout(matchup_text, 1)
        self.pitch_info_label = QLabel("PITCH  -- km/h  ·  대기", objectName="PitchInfo")
        self.pitch_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        matchup_row.addWidget(self.pitch_info_label)
        self.count_board = CountBoardWidget()
        matchup_row.addWidget(self.count_board)
        field_box.addWidget(matchup)
        live_body.addWidget(field_card, 6)

        log_card = QFrame(objectName="CommentaryDock")
        log_card.setMinimumWidth(325)
        log_card.setMaximumWidth(430)
        log_box = QVBoxLayout(log_card)
        log_box.setContentsMargins(0, 0, 0, 0)
        log_head = QFrame(objectName="DockHeader")
        log_head_row = QHBoxLayout(log_head)
        log_head_row.setContentsMargins(15, 10, 13, 9)
        log_title = QVBoxLayout()
        log_title.setSpacing(1)
        log_title.addWidget(QLabel("BATTING ORDER · MATCH FEED", objectName="DockEyebrow"))
        log_title.addWidget(QLabel("타순과 실시간 중계", objectName="DockTitle"))
        log_head_row.addLayout(log_title)
        log_head_row.addStretch()
        log_head_row.addWidget(QLabel("● LIVE", objectName="LiveText"))
        log_box.addWidget(log_head)
        order_head = QFrame(objectName="OrderHeader")
        order_head_row = QHBoxLayout(order_head)
        order_head_row.setContentsMargins(12, 6, 10, 6)
        self.order_team_label = QLabel("공격 팀 타순", objectName="SectionLabel")
        order_head_row.addWidget(self.order_team_label)
        order_head_row.addStretch()
        order_head_row.addWidget(QLabel("POS   NAME      OPS", objectName="TinyLabel"))
        log_box.addWidget(order_head)
        self.order_list = QListWidget()
        self.order_list.setObjectName("BattingOrder")
        self.order_list.setMinimumHeight(190)
        log_box.addWidget(self.order_list, 5)
        feed_title = QLabel("PLAY BY PLAY", objectName="FeedTitle")
        log_box.addWidget(feed_title)
        self.play_log = QListWidget()
        self.play_log.setObjectName("PlayLog")
        log_box.addWidget(self.play_log, 4)
        log_box.addWidget(QLabel("투구 단위로 경기 상황이 기록됩니다", objectName="LogHint"))
        live_body.addWidget(log_card, 4)
        outer.addLayout(live_body, 1)

        playback = QFrame(objectName="PlaybackBar")
        controls = QHBoxLayout(playback)
        controls.setContentsMargins(14, 8, 11, 8)
        controls.addWidget(QLabel("MATCH CONTROL", objectName="ToolbarTitle"))
        controls.addWidget(QLabel("한 투구씩 진행하거나 자동 재생합니다", objectName="Muted"))
        controls.addStretch()
        self.playback_speed = QComboBox()
        for label, speed in (("중계 속도 1×", 1.0), ("빠르게 2×", 2.0), ("빠르게 4×", 4.0)):
            self.playback_speed.addItem(label, speed)
        controls.addWidget(self.playback_speed)
        self.next_play_button = QPushButton("다음 투구  ›", objectName="NextPitchButton")
        self.next_play_button.clicked.connect(self._show_next_play)
        controls.addWidget(self.next_play_button)
        self.fast_button = QPushButton("▶  자동 재생", objectName="PrimaryButton")
        self.fast_button.clicked.connect(self._toggle_fast)
        controls.addWidget(self.fast_button)
        self.result_button = QPushButton("경기 결과  →", objectName="ResultButton")
        self.result_button.clicked.connect(self._show_result)
        self.result_button.setEnabled(False)
        controls.addWidget(self.result_button)
        outer.addWidget(playback)
        return page

    def _result_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(12)

        result_card = QFrame(objectName="ResultCard")
        result_box = QVBoxLayout(result_card)
        result_box.setContentsMargins(26, 20, 26, 20)
        self.result_status = QLabel(objectName="ResultStatus")
        self.result_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_box.addWidget(self.result_status)
        self.result_score = QLabel(objectName="FinalScore")
        self.result_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_box.addWidget(self.result_score)
        self.result_note = QLabel(
            "연습경기 결과는 정규시즌 승패에 포함되지 않습니다.",
            objectName="Muted",
        )
        self.result_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_box.addWidget(self.result_note)
        outer.addWidget(result_card)

        self.stat_tabs = QTabWidget()
        self.batting_stats = QTableWidget(0, 10)
        self.batting_stats.setHorizontalHeaderLabels(
            ("타순", "선수", "군", "포지션", "타수", "득점", "안타", "홈런", "타점", "볼넷")
        )
        self.pitching_stats = QTableWidget(0, 8)
        self.pitching_stats.setHorizontalHeaderLabels(
            ("투수", "군", "이닝", "피안타", "실점", "볼넷", "탈삼진", "투구수")
        )
        for table in (self.batting_stats, self.pitching_stats):
            self._polish_table(table, 40)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stat_tabs.addTab(self.batting_stats, "우리 팀 타자")
        self.stat_tabs.addTab(self.pitching_stats, "우리 팀 투수")
        outer.addWidget(self.stat_tabs, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        close = QPushButton("일정으로 돌아가기", objectName="PrimaryButton")
        close.clicked.connect(self._finish)
        actions.addWidget(close)
        outer.addLayout(actions)
        return page

    def set_game(self, game_id):
        self.field.cancel_animation()
        self._pending_progress = None
        self.fast_timer.stop()
        self.intro_motion_timer.stop()
        self.intro_scene_timer.stop()
        self._stop_intro_transition()
        self.intro_starting = False
        self.match_header.setVisible(True)
        self.game_id = int(game_id)
        self.game = self.service.game_details(game_id)
        self.header_title.setText(
            f"{self.game['managed_team']} vs {self.game['opponent_team']}"
        )
        self.lineup_match_title.setText(
            f"{self.game['managed_team']}  vs  {self.game['opponent_team']}"
        )
        self.game_summary.setText(
            f"{self.game['game_date']}  {self.game['start_time']}  ·  "
            f"{self.game['stadium']}  ·  {self.game['innings']}이닝  ·  "
            f"{self.game['purpose']}  ·  {self.game['lineup_policy']}  ·  "
            f"{self.game['pitching_plan']}"
        )
        if self.game["status"] == "completed":
            self.match = self.service.load_game_result(game_id)
            self._render_result()
            self.stack.setCurrentIndex(3)
            self._set_stage(4)
            return
        self.players = self.service.available_players()
        opponent_players = self.service.available_players(self.game["opponent_team"])
        self.player_maps = {
            self.game["managed_team"]: {
                int(player["id"]): player for player in self.players
            },
            self.game["opponent_team"]: {
                int(player["id"]): player for player in opponent_players
            },
        }
        self._fill_rosters()
        if self.game["status"] == "live":
            self.live_state = self.service.load_live_state(game_id)
            self._open_live_view(resume=True)
            return
        saved = self.service.prepared_lineup(game_id)
        saved_batters = sorted(
            (
                row for row in saved
                if row["team"] == self.game["managed_team"]
                and row["role"] == "batter"
            ),
            key=lambda row: int(row["batting_order"]),
        )
        saved_pitcher = next(
            (
                row for row in saved
                if row["team"] == self.game["managed_team"]
                and row["role"] == "pitcher"
            ),
            None,
        )
        if len(saved_batters) == 9 and saved_pitcher is not None:
            self.lineup = []
            for row in saved_batters:
                player = dict(
                    self.player_maps[self.game["managed_team"]][int(row["player_id"])]
                )
                player["selected_position"] = row["position"]
                self.lineup.append(player)
            self._render_lineup()
            pitcher_index = self.pitcher_combo.findData(int(saved_pitcher["player_id"]))
            if pitcher_index >= 0:
                self.pitcher_combo.setCurrentIndex(pitcher_index)
        else:
            self._auto_lineup("mixed")
        self.stack.setCurrentIndex(0)
        self._set_stage(1)

    def _fill_rosters(self):
        for table, squad in ((self.first_table, "1군"), (self.second_table, "2군")):
            rows = [
                player for player in self.players
                if player["squad_group"] == squad
                and player["position_group"] != "P"
            ]
            table.setRowCount(len(rows))
            for row, player in enumerate(rows):
                values = (
                    player["name"], player.get("pos") or player["position_group"],
                    player["rating"], player["condition"], player["fatigue"],
                    player["match_sharpness"],
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, player)
                    if player["injury_days"]:
                        item.setForeground(QColor("#e57373"))
                        item.setToolTip(f"부상 · {player['injury_days']}일")
                    table.setItem(row, column, item)
        pitchers = [
            player for player in self.players
            if player["position_group"] == "P" and not player["injury_days"]
        ]
        pitchers.sort(
            key=lambda player: (
                player["squad_group"] != "1군", -float(player["rating"])
            )
        )
        self.pitcher_combo.clear()
        for player in pitchers:
            self.pitcher_combo.addItem(
                f"[{player['squad_group']}] {player['name']}  ·  능력 {player['rating']}"
                f"  ·  컨디션 {player['condition']}",
                int(player["id"]),
            )

    def _auto_lineup(self, mode):
        hitters, starter = self.service.suggest_lineup(mode)
        self.lineup = hitters
        self._render_lineup()
        if starter is not None:
            index = self.pitcher_combo.findData(int(starter["id"]))
            if index >= 0:
                self.pitcher_combo.setCurrentIndex(index)

    def _add_selected_player(self, table):
        row = table.currentRow()
        if row < 0:
            return
        item = table.item(row, 0)
        player = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not player or player["injury_days"]:
            QMessageBox.warning(self, "라인업", "부상 선수는 선발로 등록할 수 없습니다.")
            return
        if any(int(existing["id"]) == int(player["id"]) for existing in self.lineup):
            return
        if len(self.lineup) >= 9:
            QMessageBox.information(self, "라인업", "선발 타자 9명이 이미 등록되어 있습니다.")
            return
        self.lineup.append(player)
        self._render_lineup()

    def _render_lineup(self):
        defaults = self.service._positions_for(self.lineup) if self.lineup else []
        self.lineup_table.setRowCount(len(self.lineup))
        for row, player in enumerate(self.lineup):
            season = _season_hitting_records().get(
                str(player.get("kbo_player_id") or ""), {}
            )
            average = str(season.get("AVG") or "-").removeprefix("0")
            ops = str(season.get("OPS") or "-").removeprefix("0")
            values = (
                row + 1, player["name"], average, ops, player["squad_group"],
                "", player["rating"],
            )
            for column, value in enumerate(values):
                self.lineup_table.setItem(row, column, QTableWidgetItem(str(value)))
            position = str(
                player.get("selected_position")
                or player.get("defensive_position")
                or defaults[row]
            )
            player["selected_position"] = position
            selector = QComboBox()
            selector.addItems(("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"))
            selector.setCurrentText(position)
            selector.currentTextChanged.connect(
                lambda selected, target=player: target.__setitem__(
                    "selected_position", selected
                )
            )
            self.lineup_table.setCellWidget(row, 5, selector)
        first = sum(player["squad_group"] == "1군" for player in self.lineup)
        second = len(self.lineup) - first
        self.lineup_count.setText(
            f"{len(self.lineup)}/9명  ·  1군 {first}명 / 2군 {second}명"
        )
        self.start_button.setEnabled(
            len(self.lineup) == 9 and self.pitcher_combo.count() > 0
        )

    def _move_lineup(self, direction):
        row = self.lineup_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self.lineup):
            return
        self.lineup[row], self.lineup[target] = self.lineup[target], self.lineup[row]
        self._render_lineup()
        self.lineup_table.selectRow(target)

    def _remove_lineup(self):
        row = self.lineup_table.currentRow()
        if 0 <= row < len(self.lineup):
            self.lineup.pop(row)
            self._render_lineup()

    def _start_game(self):
        if len(self.lineup) != 9:
            QMessageBox.warning(self, "경기 시작", "선발 타자 9명을 확정하세요.")
            return
        try:
            self.service.save_lineup(
                self.game_id,
                [player["id"] for player in self.lineup],
                self.pitcher_combo.currentData(),
                [player["selected_position"] for player in self.lineup],
            )
        except PracticeGameError as error:
            QMessageBox.warning(self, "연습경기", str(error))
            return
        self._prepare_intro()

    def _intro_player(self, row):
        team = row["team"]
        player = dict(
            self.player_maps.get(team, {}).get(int(row["player_id"]), {})
        )
        player.update({
            "id": int(row["player_id"]),
            "name": row["player_name"],
            "team": team,
            "position": row["position"],
            "batting_order": int(row["batting_order"]),
            "squad_group": row.get("squad_group") or player.get("squad_group", ""),
        })
        season = _season_hitting_records().get(
            str(player.get("kbo_player_id") or ""), {}
        )
        player.update({
            "season_avg": season.get("AVG") or "-",
            "season_obp": season.get("OBP") or "-",
            "season_ops": season.get("OPS") or "-",
        })
        return player

    def _intro_lineup(self, team):
        return [
            self._intro_player(row)
            for row in sorted(
                (
                    row for row in self.live_roster
                    if row["team"] == team and row["role"] == "batter"
                ),
                key=lambda row: int(row["batting_order"]),
            )
        ]

    def _intro_starter(self, team):
        row = next(
            (
                row for row in self.live_roster
                if row["team"] == team and row["role"] == "pitcher"
            ),
            None,
        )
        if row is None:
            return {"id": 0, "name": "미정", "team": team, "position": "P"}
        return self._intro_player(row)

    def _prepare_intro(self):
        self.live_roster = self.service.prepared_lineup(self.game_id)
        managed_home = self.game["venue_type"] != "away"
        away_team = (
            self.game["opponent_team"] if managed_home else self.game["managed_team"]
        )
        home_team = (
            self.game["managed_team"] if managed_home else self.game["opponent_team"]
        )
        home_info = TEAM_INFO.get(home_team, {})
        away_lineup = self._intro_lineup(away_team)
        home_lineup = self._intro_lineup(home_team)
        away_starter = self._intro_starter(away_team)
        home_starter = self._intro_starter(home_team)
        watchlist = [
            player for player in (*away_lineup, *home_lineup)
            if player.get("squad_group") == "2군"
        ]
        roster_summary = (
            f"1군 {18 - len(watchlist)}명과 2군 {len(watchlist)}명이 선발 명단에 포함됐습니다."
            if watchlist
            else "양 팀 모두 1군 중심의 선발 명단으로 실전 감각을 점검합니다."
        )
        self.intro_scenes = [
            {
                "kind": "venue",
                "title": self.game["stadium"],
                "subtitle": f"{home_info.get('city', '')} · 경기 시작을 기다리는 그라운드",
                "matchup": f"{away_team}  vs  {home_team}",
                "away_team": away_team,
                "home_team": home_team,
                "meta": f"{self.game['game_date']} · {self.game['start_time']} · {self.game['innings']}이닝",
                "stadium": self.game["stadium"],
                "duration": 3100,
                "caster": (
                    f"야구팬 여러분 안녕하십니까. {self.game['stadium']}입니다. "
                    f"{away_team}와 {home_team}의 연습경기를 함께하겠습니다."
                ),
            },
            {
                "kind": "story",
                "title": "오늘의 관전 포인트",
                "stadium": self.game["stadium"],
                "stories": (
                    {"title": self.game["purpose"], "body": "오늘 경기에서 감독이 가장 먼저 확인할 핵심 목표입니다."},
                    {"title": self.game["lineup_policy"], "body": roster_summary},
                    {"title": self.game["pitching_plan"], "body": "선발과 불펜의 투구 수, 교체 시점과 위기 대응을 점검합니다."},
                ),
                "duration": 3700,
                "caster": (
                    "연습경기는 스코어만 보는 경기가 아닙니다. "
                    f"오늘은 {self.game['purpose']}과 선수 조합의 완성도를 중점적으로 보겠습니다."
                ),
            },
            {
                "kind": "pitchers",
                "players": (away_starter, home_starter),
                "stadium": self.game["stadium"],
                "duration": 3900,
                "caster": (
                    f"{away_team}는 {away_starter['name']}, {home_team}는 "
                    f"{home_starter['name']} 선수가 선발로 나섭니다. "
                    "당일 구위와 제구가 경기 초반 흐름을 좌우합니다."
                ),
            },
            {
                "kind": "lineups",
                "away_team": away_team,
                "home_team": home_team,
                "away_lineup": away_lineup,
                "home_lineup": home_lineup,
                "stadium": self.game["stadium"],
                "duration": 4900,
                "caster": (
                    f"{away_team}와 {home_team}의 선발 타순입니다. "
                    "상위 타선의 출루와 중심 타선의 해결 능력을 함께 살펴보겠습니다."
                ),
            },
        ]
        preview_stories = []
        if self.game["purpose"] != "전력 점검":
            preview_stories.append({
                "title": self.game["purpose"],
                "body": "오늘 경기에서 감독이 가장 먼저 확인할 핵심 목표입니다.",
            })
        if self.game["lineup_policy"] != "주전 중심" or watchlist:
            preview_stories.append({
                "title": self.game["lineup_policy"],
                "body": roster_summary,
            })
        if self.game["pitching_plan"] != "선발 3이닝 제한":
            preview_stories.append({
                "title": self.game["pitching_plan"],
                "body": "투구 수와 교체 시점, 위기 대응을 중심으로 마운드를 점검합니다.",
            })
        if int(self.game["innings"]) != 9:
            preview_stories.append({
                "title": f"{self.game['innings']}이닝 경기",
                "body": "정규 경기보다 짧아 초반 선수 평가와 빠른 교체 판단이 중요합니다.",
            })
        preview_scene = next(
            scene for scene in self.intro_scenes if scene["kind"] == "story"
        )
        if preview_stories:
            preview_scene["stories"] = tuple(preview_stories[:3])
        else:
            self.intro_scenes.remove(preview_scene)

        if watchlist:
            self.intro_scenes.append({
                "kind": "watchlist",
                "players": tuple(watchlist[:4]),
                "stadium": self.game["stadium"],
                "duration": 3500,
                "caster": (
                    f"오늘 선발 명단에는 2군 선수 {len(watchlist)}명이 포함됐습니다. "
                    "제한된 기회에서 경쟁력을 보여줘야 하는 선수들입니다."
                ),
            })
        self.intro_scenes.append({
            "kind": "play_ball",
            "stadium": self.game["stadium"],
            "subtitle": (
                f"첫 타자 {away_lineup[0]['name']}  ·  선발투수 {home_starter['name']}"
            ),
            "duration": 2700,
            "caster": (
                "수비가 자리를 잡았고 첫 타자가 타석에 들어섭니다. "
                "이제 경기를 시작하겠습니다."
            ),
        })
        stadium_file = STADIUM_IMAGE_FILES.get(home_team, "")
        stadium_path = (
            resource_path("image", "Stadium", stadium_file)
            if stadium_file else None
        )
        self.intro_canvas.set_stadium(stadium_path)
        self._stop_intro_transition()
        self.intro_scene_index = 0
        self._show_intro_scene()
        self.match_header.setVisible(False)
        self.stack.setCurrentIndex(1)
        self._set_stage(2)
        self.intro_motion_timer.start()
        self.intro_scene_timer.start()

    def _show_intro_scene(self):
        if not self.intro_scenes:
            return
        scene = self.intro_scenes[self.intro_scene_index]
        total = len(self.intro_scenes)
        self.intro_canvas.set_scene(scene, self.intro_scene_index, total)
        self.intro_caster.setText(scene["caster"])
        self.intro_counter.setText("ON AIR")
        self.intro_next_button.setText(
            "경기 시작  →"
            if self.intro_scene_index == total - 1
            else "장면 넘기기  ›"
        )
        self.intro_scene_timer.setInterval(int(scene.get("duration", 2800)))

    def _advance_intro_frame(self):
        if self.stack.currentIndex() == 1:
            self.intro_canvas.advance_frame()

    def _advance_intro_scene(self):
        if (
            self.intro_starting
            or self.intro_transitioning
            or self.stack.currentIndex() != 1
        ):
            return
        self.intro_scene_timer.stop()
        if self.intro_scene_index >= len(self.intro_scenes) - 1:
            self._begin_live_game()
            return
        self.intro_transitioning = True
        self.intro_next_button.setEnabled(False)
        self.intro_fade_out.setStartValue(self.intro_opacity.opacity())
        self.intro_fade_out.start()

    def _swap_intro_scene(self):
        if not self.intro_transitioning or self.stack.currentIndex() != 1:
            return
        self.intro_scene_index += 1
        self._show_intro_scene()
        self.intro_fade_in.start()

    def _finish_intro_transition(self):
        if not self.intro_transitioning:
            return
        self.intro_transitioning = False
        self.intro_next_button.setEnabled(True)
        if self.stack.currentIndex() == 1 and not self.intro_starting:
            self.intro_scene_timer.start()

    def _stop_intro_transition(self):
        if self.intro_fade_out is not None:
            self.intro_fade_out.stop()
        if self.intro_fade_in is not None:
            self.intro_fade_in.stop()
        self.intro_transitioning = False
        if hasattr(self, "intro_opacity"):
            self.intro_opacity.setOpacity(1.0)
        if hasattr(self, "intro_next_button"):
            self.intro_next_button.setEnabled(True)

    def _begin_live_game(self):
        if self.intro_starting:
            return
        self.intro_starting = True
        self.intro_scene_timer.stop()
        self.intro_motion_timer.stop()
        self._stop_intro_transition()
        try:
            self.live_state = self.service.start_live_game(self.game_id)
        except PracticeGameError as error:
            self.intro_starting = False
            QMessageBox.warning(self, "경기 시작", str(error))
            return
        self._open_live_view(resume=False)
        self.intro_starting = False

    def _open_live_view(self, resume=False):
        self.match_header.setVisible(True)
        self.play_log.clear()
        self.live_roster = self.service.prepared_lineup(self.game_id)
        if resume and self.live_state:
            for play in self.live_state.get("plays", ()):
                self._append_live_event(play)
        self.managed_name.setText(self.game["managed_team"])
        self.opponent_name.setText(self.game["opponent_team"])
        self.next_play_button.setEnabled(True)
        self.fast_button.setEnabled(True)
        self.result_button.setEnabled(False)
        self.fast_button.setText("▶  자동 재생")
        self._fill_live_pitchers()
        self._configure_inning_score()
        self._apply_live_state(self.live_state)
        self.stack.setCurrentIndex(2)
        self._set_stage(3)

    def _show_next_play(self):
        if self.field.active or self._pending_progress is not None:
            return
        if not self.live_state or self.live_state.get("status") == "completed":
            self._finish_live_controls()
            return
        try:
            progress = self.service.advance_live_pitch(
                self.game_id,
                self.offense_strategy.currentText(),
                self.defense_strategy.currentText(),
            )
        except PracticeGameError as error:
            self.fast_timer.stop()
            QMessageBox.warning(self, "연습경기 진행", str(error))
            return
        self._pending_progress = progress
        self.next_play_button.setEnabled(False)
        self.offense_strategy.setEnabled(False)
        self.defense_strategy.setEnabled(False)
        self.steal_button.setEnabled(False)
        self.live_pitcher_combo.setEnabled(False)
        event = progress["event"]
        self.pitch_info_label.setText(
            f"PITCH  {event.get('pitch_speed', 0)} km/h  ·  {event.get('pitch_type') or '상황 진행'}"
        )
        self.field.animate_play(self.live_state, progress["state"], progress["event"], float(self.playback_speed.currentData()))

    def _finish_pitch_animation(self):
        progress = self._pending_progress
        if progress is None:
            return
        self._pending_progress = None
        self.live_state = progress["state"]
        self._append_live_event(progress["event"])
        self._apply_live_state(self.live_state)
        self.next_play_button.setEnabled(True)
        if self.live_state.get("status") == "completed":
            self.match = self.service.load_game_result(self.game_id)
            self._finish_live_controls()

    def _append_live_event(self, play):
        inning = f"{play['inning']}회{play['half']}"
        pitch = ""
        if int(play.get("pitch_speed") or 0):
            pitch = f"  ·  {play.get('pitch_type') or '구종'} {int(play['pitch_speed'])}km/h"
        item = QListWidgetItem(f"{inning}{pitch}\n{play['description']}")
        item.setSizeHint(QSize(0, 54))
        if play["runs_scored"]:
            item.setForeground(QColor("#ffca6a"))
            item.setBackground(QColor("#2b2518"))
        elif play["result_code"] in {"PITCH_CHANGE", "SB", "CS"}:
            item.setForeground(QColor("#78a9c5"))
            item.setBackground(QColor("#132633"))
        self.play_log.addItem(item)
        self.play_log.scrollToBottom()

    def _configure_inning_score(self, innings=None):
        innings = innings or int(self.game.get("innings") or 9)
        headers = ("TEAM",) + tuple(str(index) for index in range(1, innings + 1)) + ("R", "H", "E")
        self.inning_table.setColumnCount(len(headers))
        self.inning_table.setHorizontalHeaderLabels(headers)
        self.inning_table.fit_scoreboard()

    def _roster_entry(self, team, player_id):
        return next(
            (
                row for row in self.live_roster
                if row["team"] == team and int(row["player_id"]) == int(player_id)
            ),
            {},
        )

    def _update_inning_score(self, state):
        innings = max(
            int(self.game.get("innings") or 9), int(state["inning"]),
            max((len(scores) for scores in (state.get("line_score") or {}).values()), default=0),
        )
        if self.inning_table.columnCount() != innings + 4:
            self._configure_inning_score(innings)
        stats = state.get("stats") or {}
        for row_index, team in enumerate((state["away_team"], state["home_team"])):
            team_item = QTableWidgetItem(team)
            team_item.setForeground(QColor("#eef4f7"))
            self.inning_table.setItem(row_index, 0, team_item)
            completed = list((state.get("line_score") or {}).get(team, ()))
            for inning in range(1, innings + 1):
                value = ""
                if inning <= len(completed):
                    value = str(completed[inning - 1])
                elif inning == int(state["inning"]) and team == state["offense_team"]:
                    value = str(int(state["scores"][team]) - int(state.get("half_start_score", 0)))
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if inning == int(state["inning"]):
                    item.setBackground(QColor("#183246"))
                self.inning_table.setItem(row_index, inning, item)
            team_stats = [value for value in stats.values() if value.get("team") == team]
            totals = (
                int(state["scores"].get(team, 0)),
                sum(int(value.get("hits", 0)) for value in team_stats),
                0,
            )
            for offset, total in enumerate(totals):
                item = QTableWidgetItem(str(total))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor("#67c9e6") if offset < 2 else QColor("#94a4ae"))
                self.inning_table.setItem(row_index, innings + 1 + offset, item)

    def _update_broadcast_panels(self, state):
        offense = state["offense_team"]
        defense = state["defense_team"]
        batter_id = int(state.get("batter_id") or 0)
        pitcher_id = int(state.get("pitcher_id") or 0)
        batter = dict(self.player_maps.get(offense, {}).get(batter_id, {}))
        pitcher = self.player_maps.get(defense, {}).get(pitcher_id, {})
        batter_roster = self._roster_entry(offense, batter_id)
        batter["live_position"] = batter_roster.get("position") or batter.get("pos") or "-"
        batter["live_order"] = int(batter_roster.get("batting_order") or 0)
        season = _season_hitting_records().get(str(batter.get("kbo_player_id") or ""), {})
        game_stat = (state.get("stats") or {}).get(f"{offense}|{batter_id}", {})
        stadium_team = state.get("home_team") or self.game["managed_team"]
        stadium_file = STADIUM_IMAGE_FILES.get(stadium_team, "")
        stadium_path = resource_path("image", "Stadium", stadium_file) if stadium_file else None
        self.field.set_broadcast_context(stadium_path, batter, season, game_stat)
        self.field.set_defenders(self.live_roster, self.player_maps)
        self.stadium_label.setText(f"{self.game.get('stadium') or stadium_team}  ·  2D 경기 중계")

        pitcher_stat = (state.get("stats") or {}).get(f"{defense}|{pitcher_id}", {})
        self.current_pitcher_label.setText(
            f"{pitcher.get('name') or state.get('pitcher_name') or '-'}  ·  {defense}"
        )
        innings_outs = int(pitcher_stat.get("innings_outs", 0))
        innings_text = f"{innings_outs // 3}.{innings_outs % 3}이닝"
        self.current_pitcher_stat.setText(
            f"{innings_text}  ·  {int(pitcher_stat.get('pitches', 0))}구  ·  "
            f"{int(pitcher_stat.get('strikeouts_pitched', 0))}K  ·  "
            f"{int(pitcher_stat.get('runs_allowed', 0))}실점"
        )

        self.order_team_label.setText(f"{offense} 공격 타순")
        self.order_list.clear()
        for order, player_id in enumerate(state["batting_orders"].get(offense, ()), 1):
            player = self.player_maps.get(offense, {}).get(int(player_id), {})
            roster = self._roster_entry(offense, player_id)
            record = _season_hitting_records().get(str(player.get("kbo_player_id") or ""), {})
            ops = str(record.get("OPS") or "-")
            item = QListWidgetItem(
                f"{order:>2}    {str(roster.get('position') or '-'):>2}    "
                f"{player.get('name') or roster.get('player_name') or '-'}    {ops}"
            )
            item.setData(Qt.ItemDataRole.UserRole, int(player_id))
            item.setSizeHint(QSize(0, 31))
            if int(player_id) == batter_id:
                item.setForeground(QColor("#ffffff"))
                item.setBackground(QColor("#17648a"))
            self.order_list.addItem(item)
        current_row = next(
            (index for index in range(self.order_list.count())
             if int(self.order_list.item(index).data(Qt.ItemDataRole.UserRole)) == batter_id),
            -1,
        )
        if current_row >= 0:
            self.order_list.scrollToItem(self.order_list.item(current_row))

    def _apply_live_state(self, state):
        if not state:
            return
        self.managed_score.setText(str(state.get("managed_score", 0)))
        self.opponent_score.setText(str(state.get("opponent_score", 0)))
        self.match_state.setText(
            f"{state['inning']}회{state['half']}  ·  "
            f"{state['offense_team']} 공격"
        )
        self.count_board.set_count(state["balls"], state["strikes"], state["outs"])
        speed = int(state.get("last_pitch_speed") or 0)
        pitch_type = state.get("last_pitch_type") or "대기"
        self.pitch_info_label.setText(
            f"PITCH  {speed} km/h  ·  {pitch_type}" if speed else "PITCH  -- km/h  ·  대기"
        )
        self.matchup_label.setText(
            f"타자  {state.get('batter_name', '-')}   ·   "
            f"투수  {state.get('pitcher_name', '-')}"
        )
        self.field.set_state(state)
        self._update_inning_score(state)
        self._update_broadcast_panels(state)
        managed_offense = state["offense_team"] == self.game["managed_team"]
        self.offense_strategy.setEnabled(managed_offense)
        self.steal_button.setEnabled(
            managed_offense
            and state["bases"].get("1") is not None
            and state["bases"].get("2") is None
        )
        self.defense_strategy.setEnabled(not managed_offense)
        self.live_pitcher_combo.setEnabled(not managed_offense)

    def _finish_live_controls(self):
        self.fast_timer.stop()
        self.fast_button.setText("▶  자동 재생")
        self.next_play_button.setEnabled(False)
        self.fast_button.setEnabled(False)
        self.result_button.setEnabled(True)
        self.match_state.setText("경기 종료")

    def _fill_live_pitchers(self):
        self.live_pitcher_combo.clear()
        for player in self.players:
            if player["position_group"] != "P" or player["injury_days"]:
                continue
            self.live_pitcher_combo.addItem(
                f"[{player['squad_group']}] {player['name']} · "
                f"능력 {player['rating']} · 컨디션 {player['condition']}",
                int(player["id"]),
            )

    def _request_steal(self):
        if self.field.active:
            return
        try:
            self.live_state = self.service.request_steal(self.game_id)
        except PracticeGameError as error:
            QMessageBox.information(self, "도루 지시", str(error))
            return
        self.steal_button.setEnabled(False)

    def _change_pitcher(self):
        if self.field.active:
            return
        player_id = self.live_pitcher_combo.currentData()
        if player_id is None:
            return
        try:
            self.live_state = self.service.change_pitcher(self.game_id, player_id)
        except PracticeGameError as error:
            QMessageBox.information(self, "투수 교체", str(error))
            return
        event = self.live_state.get("last_event")
        if event:
            self._append_live_event(event)
        self._apply_live_state(self.live_state)

    def _toggle_fast(self):
        if self.fast_timer.isActive():
            self.fast_timer.stop()
            self.fast_button.setText("▶  자동 재생")
        else:
            self.fast_timer.start()
            self.fast_button.setText("Ⅱ  일시정지")

    def _show_result(self):
        self.fast_timer.stop()
        if self.match is None:
            self.match = self.service.load_game_result(self.game_id)
        self._render_result()
        self.stack.setCurrentIndex(3)
        self._set_stage(4)

    def _render_result(self):
        game = self.match["game"]
        managed = int(game["managed_score"])
        opponent = int(game["opponent_score"])
        verdict = "승리" if managed > opponent else "패배" if managed < opponent else "무승부"
        self.result_status.setText(f"연습경기 {verdict}")
        self.result_score.setText(
            f"{game['managed_team']}  {managed}  —  {opponent}  {game['opponent_team']}"
        )
        stats = [
            stat for stat in self.match["stats"]
            if stat["team"] == game["managed_team"]
        ]
        batters = [stat for stat in stats if int(stat["batting_order"]) > 0]
        pitchers = [stat for stat in stats if int(stat["innings_outs"]) > 0]
        self.batting_stats.setRowCount(len(batters))
        for row, stat in enumerate(batters):
            values = (
                stat["batting_order"], stat["player_name"], stat["squad_group"],
                stat["position"], stat["at_bats"], stat["runs"], stat["hits"],
                stat["home_runs"], stat["rbi"], stat["walks"],
            )
            for column, value in enumerate(values):
                self.batting_stats.setItem(row, column, QTableWidgetItem(str(value)))
        self.pitching_stats.setRowCount(len(pitchers))
        for row, stat in enumerate(pitchers):
            innings = f"{int(stat['innings_outs']) // 3}.{int(stat['innings_outs']) % 3}"
            values = (
                stat["player_name"], stat["squad_group"], innings,
                stat["hits_allowed"], stat["runs_allowed"], stat["walks_allowed"],
                stat["strikeouts_pitched"], stat["pitches"],
            )
            for column, value in enumerate(values):
                self.pitching_stats.setItem(row, column, QTableWidgetItem(str(value)))

    def _set_stage(self, stage):
        labels = []
        for index, name in enumerate(("LINEUP", "INTRO", "MATCH", "RESULT"), 1):
            labels.append(f"[{index} {name}]" if index == stage else f"{index} {name}")
        self.stage_label.setText("   ›   ".join(labels))

    def _back(self):
        self.fast_timer.stop()
        self.field.cancel_animation()
        self._finish_pitch_animation()
        self.intro_motion_timer.stop()
        self.intro_scene_timer.stop()
        self._stop_intro_transition()
        self.back_requested.emit()

    def hideEvent(self, event):
        self.fast_timer.stop()
        self.field.cancel_animation()
        self._finish_pitch_animation()
        super().hideEvent(event)

    def _finish(self):
        self.intro_motion_timer.stop()
        self.intro_scene_timer.stop()
        self._stop_intro_transition()
        self.completed.emit()
        self.back_requested.emit()

    def _style(self):
        accent = self.colors["accent"]
        accent_light = self.colors["accent_light"]
        return f"""
            PracticeGameMatchPage {{ background:#0b1014; }}
            QLabel {{ color:#edf2f6; font-family:'Malgun Gothic','Segoe UI'; }}

            QFrame#MatchHeader {{ background:#0c1217; border:0; border-bottom:1px solid #222e36; }}
            QPushButton#BackButton {{ min-width:70px; background:transparent; border:0; color:#9badbb; text-align:left; }}
            QPushButton#BackButton:hover {{ color:#ffffff; background:#1c2730; }}
            QLabel#MatchEyebrow, QLabel#HeroEyebrow, QLabel#DockEyebrow {{ color:#e5ad4f; font-size:13px; font-weight:900; letter-spacing:1px; }}
            QLabel#MatchTitle {{ font-size:17px; font-weight:900; }}
            QLabel#StageLabel {{ color:#9eacb6; background:#141d24; border:1px solid #2a363f; border-radius:16px; padding:7px 15px; font-size:13px; font-weight:900; letter-spacing:.5px; }}

            QFrame#LineupHero {{ background:#111c24; border:1px solid #2a3a45; border-left:4px solid {accent_light}; border-radius:10px; }}
            QFrame#HeroDivider {{ background:#2a3842; border:0; }}
            QLabel#HeroTitle {{ color:#ffffff; font-size:23px; font-weight:900; }}
            QLabel#GameSummary {{ color:#aab9c4; font-size:14px; font-weight:600; }}
            QLabel#ReadyStatus {{ color:#62d597; font-size:15px; font-weight:900; }}
            QLabel#TinyLabel {{ color:#71828f; font-size:13px; font-weight:900; letter-spacing:1px; }}
            QLabel#ToolbarTitle {{ color:#dce6ed; font-size:13px; font-weight:900; }}
            QLabel#SectionLabel, QLabel#CardTitle {{ color:#f1f5f8; font-size:15px; font-weight:900; }}
            QLabel#CardMeta {{ color:#738794; font-size:13px; font-weight:700; }}
            QLabel#Muted {{ color:#7e8f9b; font-size:13px; }}

            QFrame#BroadcastCaption {{ background:rgba(4,10,15,238); border:1px solid rgba(255,255,255,42); border-left:4px solid {accent_light}; border-radius:10px; min-height:82px; max-height:96px; }}
            QLabel#BroadcastLiveDot {{ color:#ef445a; font-size:15px; font-weight:900; padding-top:2px; }}
            QLabel#BroadcastCaptionLabel {{ color:#e5ad4f; font-size:13px; font-weight:900; letter-spacing:1px; }}
            QLabel#BroadcastCasterText {{ color:#e5edf2; font-size:14px; font-weight:700; }}
            QLabel#BroadcastSequenceDots {{ color:#6bcfe7; font-size:13px; min-width:70px; font-weight:900; letter-spacing:1px; }}
            QPushButton#BroadcastSkipButton {{ color:#c5d0d6; background:rgba(4,10,15,210); border:1px solid rgba(255,255,255,58); border-radius:15px; min-width:125px; min-height:30px; font-size:13px; }}
            QPushButton#BroadcastSkipButton:hover {{ color:#ffffff; background:rgba(19,36,47,235); }}
            QPushButton#BroadcastNextButton {{ color:#ffffff; background:{accent}; border:1px solid {accent_light}; border-radius:6px; min-width:110px; min-height:38px; }}

            QFrame#LineupToolbar, QFrame#PlaybackBar {{ background:#11181e; border:1px solid #26323a; border-radius:8px; }}
            QFrame#RosterCard, QFrame#LineupCard, QFrame#ManagerDock,
            QFrame#PitchCard, QFrame#CommentaryDock {{ background:#10171c; border:1px solid #27343d; border-radius:10px; }}
            QFrame#CardHeader, QFrame#DockHeader {{ background:#151e25; border:0; border-bottom:1px solid #27343d; }}
            QFrame#LineupFooter {{ background:#151e25; border:0; border-top:1px solid #2d3943; }}
            QLabel#DockTitle {{ font-size:15px; font-weight:900; }}

            QTableWidget, QListWidget {{ background:#0e1419; alternate-background-color:#11191f; color:#dbe4ea; border:0; selection-background-color:#21465b; selection-color:#ffffff; outline:0; }}
            QTableWidget::item {{ padding-left:9px; border-bottom:1px solid #1d272e; }}
            QTableWidget::item:selected {{ border-left:3px solid {accent_light}; }}
            QHeaderView::section {{ color:#8295a2; background:#151e25; border:0; border-bottom:1px solid #2b3740; padding:8px 6px; font-size:13px; font-weight:900; }}
            QTabWidget::pane {{ border:0; background:#0e1419; }}
            QTabBar::tab {{ color:#788b98; background:#11181e; border:0; border-bottom:2px solid transparent; padding:10px 24px; font-weight:800; }}
            QTabBar::tab:hover {{ color:#d9e3e9; }}
            QTabBar::tab:selected {{ color:#ffffff; background:#172129; border-bottom:2px solid {accent_light}; }}

            QComboBox {{ min-height:34px; padding:0 10px; color:#eef3f7; background:#1a242c; border:1px solid #354550; border-radius:4px; }}
            QComboBox:hover {{ border-color:#5d798a; }}
            QComboBox:disabled {{ color:#596873; background:#131a20; border-color:#263139; }}
            QComboBox::drop-down {{ width:28px; border:0; border-left:1px solid #33414b; }}
            QComboBox QAbstractItemView {{ background:#19232b; color:#e9eff3; selection-background-color:#28516a; border:1px solid #42525e; }}
            QPushButton {{ min-height:34px; padding:0 14px; color:#d4dee5; background:#1c262e; border:1px solid #35444f; border-radius:4px; font-weight:800; }}
            QPushButton:hover {{ color:#ffffff; border-color:{accent_light}; background:#24323b; }}
            QPushButton:pressed {{ background:#111920; }}
            QPushButton:disabled {{ color:#53616c; background:#141b21; border-color:#252f37; }}
            QPushButton#SegmentButton {{ min-height:28px; padding:0 13px; background:#172027; border-color:#303d47; font-size:13px; }}
            QPushButton#IconButton {{ min-width:34px; max-width:34px; padding:0; font-size:16px; }}
            QPushButton#DangerGhostButton {{ color:#d79a9a; }}
            QPushButton#CommandButton {{ text-align:left; padding-left:12px; }}
            QPushButton#PrimaryButton {{ color:#ffffff; background:{accent}; border-color:{accent_light}; min-width:160px; min-height:38px; }}
            QPushButton#PrimaryButton:hover {{ background:{accent_light}; }}
            QPushButton#NextPitchButton {{ color:#dce9f1; background:#263641; border-color:#486072; min-width:115px; }}
            QPushButton#ResultButton {{ color:#ffffff; background:#275b46; border-color:#3a8a67; min-width:135px; }}

            QFrame#Scoreboard {{ background:#111a21; border:1px solid #314552; border-left:4px solid {accent_light}; border-radius:6px; }}
            QLabel#ScoreTeam {{ font-size:18px; font-weight:900; padding:0 16px; }}
            QLabel#ScoreNumber {{ color:#ffffff; font-size:39px; font-weight:900; min-width:64px; qproperty-alignment:AlignCenter; }}
            QLabel#ScoreDivider {{ color:#546c7c; font-size:13px; font-weight:900; min-width:70px; }}
            QLabel#MatchState {{ color:#f0b84b; font-size:14px; font-weight:900; min-width:100px; }}
            QTableWidget#InningScore {{ background:#08121b; alternate-background-color:#0b1721; border:1px solid #2b4353; color:#e9eff3; font-size:14px; font-weight:800; }}
            QTableWidget#InningScore::item {{ padding:0 4px; border-right:1px solid #1c3342; border-bottom:1px solid #1c3342; }}
            QTableWidget#InningScore QHeaderView::section {{ color:#66bed9; background:#0d1e2b; border-right:1px solid #234154; padding:3px; font-size:13px; }}

            QFrame#PitchHeader {{ background:#101a1f; border:0; border-bottom:1px solid #29383f; }}
            QLabel#StadiumLabel {{ color:#8ca4b2; font-size:13px; padding-right:8px; }}
            QLabel#LiveBadge {{ color:#08120d; background:#4bd187; border-radius:9px; padding:3px 9px; font-size:13px; font-weight:900; }}
            QFrame#MatchupBar {{ background:#111a20; border:0; border-top:1px solid #2a373f; }}
            QLabel#MatchupLabel {{ color:#f4f7f9; font-size:15px; font-weight:900; }}
            QLabel#PitchInfo {{ color:#69d4ed; background:#0a141b; border:1px solid #274556; border-radius:4px; padding:7px 12px; font-size:13px; font-weight:900; min-width:155px; }}
            QFrame#CountBoard {{ background:#0b1115; border:1px solid #2c3942; border-radius:5px; }}
            QLabel#CountB {{ color:#44c377; font-weight:900; }}
            QLabel#CountS {{ color:#f0b84b; font-weight:900; }}
            QLabel#CountO {{ color:#ef6262; font-weight:900; }}

            QFrame#PitcherPanel {{ background:#0d1820; border:0; border-bottom:1px solid #293740; }}
            QLabel#CurrentPitcher {{ color:#ffffff; font-size:15px; font-weight:900; }}
            QLabel#PitcherStat {{ color:#65b8d5; font-size:13px; font-weight:800; }}

            QLabel#LiveText {{ color:#4bd187; font-size:13px; font-weight:900; }}
            QFrame#OrderHeader {{ background:#0d171e; border:0; border-bottom:1px solid #263640; }}
            QListWidget#BattingOrder {{ background:#091119; border:0; padding:4px 6px; font-size:13px; font-weight:800; }}
            QListWidget#BattingOrder::item {{ color:#b7c5ce; border:0; border-bottom:1px solid #192730; padding:3px 8px; }}
            QListWidget#BattingOrder::item:selected {{ color:#ffffff; background:#17648a; border-left:3px solid #67dcf2; }}
            QLabel#FeedTitle {{ color:#7e919e; background:#111b22; border-top:1px solid #293842; border-bottom:1px solid #293842; padding:6px 12px; font-size:13px; font-weight:900; letter-spacing:1px; }}
            QListWidget#PlayLog {{ font-size:14px; padding:7px; }}
            QListWidget#PlayLog::item {{ padding:6px 9px; margin:2px 1px; border:0; border-left:2px solid #32434e; border-radius:3px; }}
            QListWidget#PlayLog::item:selected {{ background:#182731; border-left:2px solid {accent_light}; }}
            QLabel#LogHint {{ color:#667783; background:#10171c; border-top:1px solid #27333b; padding:9px 13px; font-size:13px; }}

            QFrame#ResultCard {{ background:#13212b; border:1px solid #315064; border-radius:8px; }}
            QLabel#ResultStatus {{ color:#f0b84b; font-size:15px; font-weight:900; }}
            QLabel#FinalScore {{ font-size:31px; font-weight:900; padding:4px; }}

            QScrollBar:vertical {{ background:#0e1419; width:8px; margin:0; }}
            QScrollBar::handle:vertical {{ background:#34434e; min-height:28px; border-radius:4px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """
