"""FM 스타일 타순·수비·투수 운용 전술 편집 화면."""

from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.utils import resource_path
from app.views.team_manage.player_profile import _player_photo_path


DEFENSIVE_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
STARTER_ROLES = ("1선발", "2선발", "3선발", "4선발", "5선발")
BULLPEN_ROLES = (
    "롱릴리프", "추격조 1", "추격조 2", "필승조 1", "필승조 2", "셋업맨", "마무리"
)
STADIUM_IMAGE_FILES = {
    "KIA 타이거즈": "kia.jpg",
    "삼성 라이온즈": "samsung.jpg",
    "LG 트윈스": "jamsil.jpg",
    "두산 베어스": "jamsil.jpg",
    "KT 위즈": "kt.jpg",
    "SSG 랜더스": "ssg.jpg",
    "롯데 자이언츠": "lotte.jpg",
    "한화 이글스": "hanwha.jpg",
    "NC 다이노스": "NC파크.png",
    "키움 히어로즈": "kiwoom.jpg",
}
GAME_PLAN_PHASES = (
    ("early", "경기 초반", "1~3회", "#4a9fd5"),
    ("middle", "경기 중반", "4~7회", "#48bd8b"),
    ("late", "경기 마지막", "8~9회", "#d3a94f"),
)
GAME_PLAN_OPTIONS = (
    (
        "offense",
        "공격 성향",
        ("신중", "균형", "공격"),
        "타석에서 기다릴지, 초구부터 적극적으로 승부할지 결정합니다.",
    ),
    (
        "bunt",
        "번트 지시",
        ("최소", "상황별", "적극"),
        "무사·1사 주자 상황에서 희생번트를 시도하는 빈도입니다.",
    ),
    (
        "steal",
        "도루 시도",
        ("자제", "보통", "적극"),
        "주력과 포수 송구 능력을 비교해 도루를 시도하는 기준입니다.",
    ),
    (
        "hit_and_run",
        "히트앤런",
        ("사용 안 함", "상황별", "적극"),
        "주자를 먼저 움직여 병살을 줄이고 빈 공간을 노리는 빈도입니다.",
    ),
    (
        "pinch_hit",
        "대타 기용",
        ("보존", "매치업", "적극"),
        "좌우 매치업과 타자 컨디션에 따라 대타를 투입하는 기준입니다.",
    ),
    (
        "starter_hook",
        "선발 교체",
        ("길게", "표준", "빠르게"),
        "실점·투구 수·타순 세 번째 대면 시 선발을 교체하는 속도입니다.",
    ),
    (
        "bullpen",
        "불펜 운용",
        ("보존", "매치업", "총력"),
        "필승조를 아낄지, 유리한 매치업마다 빠르게 투입할지 결정합니다.",
    ),
    (
        "defense",
        "수비 운영",
        ("표준", "데이터 시프트", "리드 보호"),
        "타구 방향 데이터와 점수 상황을 반영한 수비 위치 조정입니다.",
    ),
)
DEFAULT_GAME_PLAN = {
    "early": {
        "offense": "신중", "bunt": "최소", "steal": "보통",
        "hit_and_run": "상황별", "pinch_hit": "보존",
        "starter_hook": "길게", "bullpen": "보존", "defense": "표준",
    },
    "middle": {
        "offense": "균형", "bunt": "상황별", "steal": "보통",
        "hit_and_run": "상황별", "pinch_hit": "매치업",
        "starter_hook": "표준", "bullpen": "매치업", "defense": "데이터 시프트",
    },
    "late": {
        "offense": "공격", "bunt": "상황별", "steal": "적극",
        "hit_and_run": "상황별", "pinch_hit": "적극",
        "starter_hook": "빠르게", "bullpen": "총력", "defense": "리드 보호",
    },
}


def _player_visual(player):
    if not player:
        return {"name": "미정", "photo": ""}
    photo_path = _player_photo_path(
        player.get("kbo_player_id"),
        player.get("name"),
        player.get("team"),
    )
    return {
        "name": player.get("name") or "미정",
        "photo": str(photo_path) if photo_path else "",
    }


PLAYER_MIME_TYPE = "application/x-kbo-player-id"


class FirstTeamPlayerPool(QListWidget):
    """1군 선수를 타순표와 수비 위치로 끌어갈 수 있는 선수 풀."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("firstTeamPool")
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setIconSize(QSize(34, 34))
        self.setSpacing(2)

    def set_players(self, players):
        self.clear()
        for player in sorted(players, key=lambda item: (item.get("pos") == "P", item.get("pos") or "", item.get("name") or "")):
            condition = int(player.get("sim_condition") or 100)
            item = QListWidgetItem(
                f"{player.get('name') or '-'}   {player.get('pos') or '-'}   컨디션 {condition}"
            )
            item.setData(Qt.ItemDataRole.UserRole, int(player["id"]))
            visual = _player_visual(player)
            if visual["photo"]:
                item.setIcon(QIcon(visual["photo"]))
            item.setSizeHint(QSize(210, 42))
            self.addItem(item)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(PLAYER_MIME_TYPE, str(item.data(Qt.ItemDataRole.UserRole)).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        if not item.icon().isNull():
            drag.setPixmap(item.icon().pixmap(34, 34))
        drag.exec(Qt.DropAction.CopyAction)


class LineupDropTable(QTableWidget):
    player_dropped = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            super().dropEvent(event)
            return
        try:
            player_id = int(bytes(event.mimeData().data(PLAYER_MIME_TYPE)).decode("ascii"))
        except (TypeError, ValueError):
            event.ignore()
            return
        row = self.indexAt(event.position().toPoint()).row()
        if row < 0:
            row = max(0, self.rowCount() - 1)
        self.player_dropped.emit(player_id, row)
        event.acceptProposedAction()


class BaseballFieldWidget(QWidget):
    """타순 표의 수비 위치를 야구장 위에 표시하는 전술 보드."""

    POSITIONS = {
        "LF": (0.18, 0.25),
        "CF": (0.50, 0.14),
        "RF": (0.82, 0.25),
        "SS": (0.37, 0.43),
        "2B": (0.63, 0.43),
        "3B": (0.25, 0.59),
        "1B": (0.75, 0.59),
        "C": (0.50, 0.82),
        "DH": (0.15, 0.80),
    }
    player_dropped = Signal(int, str)

    def __init__(self, team_name, parent=None):
        super().__init__(parent)
        self.lineup = {}
        self.starter = {}
        stadium_file = STADIUM_IMAGE_FILES.get(team_name, "")
        self._stadium = QPixmap(
            str(resource_path("image", "Stadium", stadium_file))
        )
        self._photo_cache = {}
        self.setAcceptDrops(True)
        self.setMinimumSize(480, 500)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            super().dropEvent(event)
            return
        try:
            player_id = int(bytes(event.mimeData().data(PLAYER_MIME_TYPE)).decode("ascii"))
        except (TypeError, ValueError):
            event.ignore()
            return
        point = event.position()
        x = point.x() / max(1, self.width())
        y = point.y() / max(1, self.height())
        position = min(
            self.POSITIONS,
            key=lambda key: (self.POSITIONS[key][0] - x) ** 2 + (self.POSITIONS[key][1] - y) ** 2,
        )
        self.player_dropped.emit(player_id, position)
        event.acceptProposedAction()

    def set_lineup(self, lineup, starter=None):
        self.lineup = dict(lineup)
        self.starter = starter or {}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()

        background = QLinearGradient(0, 0, 0, height)
        background.setColorAt(0, QColor("#0b5c43"))
        background.setColorAt(1, QColor("#063b32"))
        painter.setBrush(QBrush(background))
        painter.setPen(QPen(QColor("#2e8068"), 1))
        painter.drawRoundedRect(QRectF(1, 1, width - 2, height - 2), 7, 7)
        if not self._stadium.isNull():
            self._draw_cover_pixmap(
                painter,
                QRectF(2, 2, width - 4, height - 4),
                self._stadium,
                opacity=0.56,
            )
            painter.fillRect(
                QRectF(2, 2, width - 4, height - 4),
                QColor(3, 38, 31, 104),
            )

        center = QPointF(width * 0.5, height * 0.79)
        radius = min(width * 0.47, height * 0.69)
        painter.setPen(QPen(QColor("#8bd0a8"), 2))
        painter.setBrush(QBrush(QColor(20, 115, 77, 86)))
        painter.drawPie(
            QRectF(center.x() - radius, center.y() - radius,
                   radius * 2, radius * 2),
            0,
            180 * 16,
        )

        home = QPointF(width * 0.5, height * 0.78)
        first = QPointF(width * 0.72, height * 0.59)
        second = QPointF(width * 0.5, height * 0.39)
        third = QPointF(width * 0.28, height * 0.59)
        infield = QPolygonF([home, first, second, third])
        painter.setBrush(QBrush(QColor(170, 131, 86, 178)))
        painter.setPen(QPen(QColor("#e7d6b8"), 2))
        painter.drawPolygon(infield)
        painter.setBrush(QBrush(QColor(22, 132, 90, 138)))
        inner = QPolygonF(
            [
                QPointF(width * 0.5, height * 0.70),
                QPointF(width * 0.63, height * 0.59),
                QPointF(width * 0.5, height * 0.47),
                QPointF(width * 0.37, height * 0.59),
            ]
        )
        painter.drawPolygon(inner)

        painter.setPen(QPen(QColor("#f4e7cf"), 2))
        for point in (home, first, second, third):
            painter.setBrush(QBrush(QColor("#f4e7cf")))
            painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))
        painter.drawLine(home, QPointF(width * 0.05, height * 0.22))
        painter.drawLine(home, QPointF(width * 0.95, height * 0.22))

        self._draw_player_card(
            painter, "P", self.starter, 0.50, 0.58, accent="#d1aa55"
        )
        for position, (x_ratio, y_ratio) in self.POSITIONS.items():
            self._draw_player_card(
                painter,
                position,
                self.lineup.get(position, {}),
                x_ratio,
                y_ratio,
            )

        painter.setPen(QColor("#a7d8c4"))
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.drawText(
            QRectF(14, 12, width - 28, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "DEFENSIVE ALIGNMENT  ·  수비 포메이션",
        )

    def _draw_player_card(self, painter, position, player, x_ratio, y_ratio, accent="#46c995"):
        width = painter.device().width()
        height = painter.device().height()
        name = player.get("name", "미정") if isinstance(player, dict) else str(player or "미정")
        photo_path = player.get("photo", "") if isinstance(player, dict) else ""
        card_width = min(138.0, width * 0.28)
        card_height = 56.0
        rect = QRectF(
            width * x_ratio - card_width / 2,
            height * y_ratio - card_height / 2,
            card_width,
            card_height,
        )
        painter.setBrush(QBrush(QColor("#17242c")))
        painter.setPen(QPen(QColor(accent), 1.5))
        painter.drawRoundedRect(rect, 5, 5)
        portrait = QRectF(rect.left() + 6, rect.top() + 7, 40, 40)
        self._draw_portrait(painter, portrait, name, photo_path, accent)
        badge = QRectF(rect.right() - 34, rect.top() + 5, 28, 17)
        painter.setBrush(QBrush(QColor(accent)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge, 3, 3)
        painter.setPen(QColor("#0b161b"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, position)
        painter.setPen(QColor("#f2f6f8") if name != "미정" else QColor("#75838e"))
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.drawText(
            QRectF(rect.left() + 51, rect.top() + 22, rect.width() - 57, 25),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )

    def _draw_portrait(self, painter, rect, name, photo_path, accent):
        path = QPainterPath()
        path.addEllipse(rect)
        painter.save()
        painter.setClipPath(path)
        pixmap = self._photo_cache.get(photo_path)
        if photo_path and pixmap is None:
            pixmap = QPixmap(photo_path)
            self._photo_cache[photo_path] = pixmap
        if pixmap is not None and not pixmap.isNull():
            self._draw_cover_pixmap(painter, rect, pixmap)
        else:
            painter.fillRect(rect, QColor("#2a3b45"))
            painter.setPen(QColor("#e8f0f3"))
            painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name[-2:])
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(accent), 1.5))
        painter.drawEllipse(rect)

    @staticmethod
    def _draw_cover_pixmap(painter, target, pixmap, opacity=1.0):
        if pixmap.isNull() or target.width() <= 0 or target.height() <= 0:
            return
        target_ratio = target.width() / target.height()
        source_ratio = pixmap.width() / pixmap.height()
        if source_ratio > target_ratio:
            source_width = pixmap.height() * target_ratio
            source = QRectF(
                (pixmap.width() - source_width) / 2,
                0,
                source_width,
                pixmap.height(),
            )
        else:
            source_height = pixmap.width() / target_ratio
            source = QRectF(
                0,
                max(0, (pixmap.height() - source_height) * 0.22),
                pixmap.width(),
                source_height,
            )
        painter.save()
        painter.setOpacity(opacity)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, pixmap, source)
        painter.restore()


class PitchingPlanWidget(QWidget):
    """선발 순서와 불펜 계층을 한눈에 보여주는 투수 운용 보드."""

    def __init__(self, team_name, parent=None):
        super().__init__(parent)
        self.rotation = []
        self.bullpen = {}
        stadium_file = STADIUM_IMAGE_FILES.get(team_name, "")
        self._stadium = QPixmap(
            str(resource_path("image", "Stadium", stadium_file))
        )
        self._photo_cache = {}
        self.setMinimumSize(500, 520)

    def set_plan(self, rotation, bullpen):
        self.rotation = list(rotation)
        self.bullpen = dict(bullpen)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0, QColor("#18313b"))
        gradient.setColorAt(1, QColor("#0e2028"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor("#38505b"), 1))
        painter.drawRoundedRect(QRectF(1, 1, width - 2, height - 2), 7, 7)
        if not self._stadium.isNull():
            BaseballFieldWidget._draw_cover_pixmap(
                painter,
                QRectF(2, 2, width - 4, height - 4),
                self._stadium,
                opacity=0.30,
            )
            painter.fillRect(
                QRectF(2, 2, width - 4, height - 4),
                QColor(8, 23, 30, 178),
            )

        painter.setPen(QColor("#dce8ed"))
        painter.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        painter.drawText(20, 30, "STARTING FIVE  ·  선발 로테이션")
        card_width = min(205.0, (width - 56) / 2)
        rotation_rects = (
            QRectF((width - 220) / 2, 43, 220, 52),
            QRectF(20, 111, card_width, 49),
            QRectF(width - 20 - card_width, 111, card_width, 49),
            QRectF(20, 176, card_width, 49),
            QRectF(width - 20 - card_width, 176, card_width, 49),
        )
        painter.setPen(QPen(QColor(210, 170, 82, 120), 2))
        ace_center = rotation_rects[0].center()
        for rect in rotation_rects[1:]:
            painter.drawLine(ace_center, rect.center())
        for index, rect in enumerate(rotation_rects):
            player = self.rotation[index] if index < len(self.rotation) else {}
            self._draw_role_card(
                painter, rect,
                f"{index + 1}선발", player, "#d2aa52",
            )

        bullpen_top = 259
        painter.setPen(QColor("#dce8ed"))
        painter.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        painter.drawText(20, bullpen_top, "BULLPEN MAP  ·  상황별 불펜 체인")
        column_gap = 12
        bullpen_width = (width - 52) / 2
        low_x = 20
        high_x = low_x + bullpen_width + column_gap
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#83a4b5"))
        painter.drawText(low_x, bullpen_top + 22, "LONG / LOW LEVERAGE")
        painter.setPen(QColor("#66d2a4"))
        painter.drawText(high_x, bullpen_top + 22, "WINNING CHAIN")

        low_roles = ("롱릴리프", "추격조 1", "추격조 2")
        high_roles = ("필승조 1", "필승조 2", "셋업맨", "마무리")
        for index, role in enumerate(low_roles):
            y = bullpen_top + 34 + index * 48
            rect = QRectF(low_x, y, bullpen_width, 39)
            self._draw_role_card(
                painter, rect, role, self.bullpen.get(role, {}), "#6f9daf"
            )
        for index, role in enumerate(high_roles):
            y = bullpen_top + 34 + index * 48
            rect = QRectF(high_x, y, bullpen_width, 39)
            color = "#df6565" if role == "마무리" else "#45bd91"
            self._draw_role_card(
                painter, rect, role, self.bullpen.get(role, {}), color
            )
            if index:
                painter.setPen(QPen(QColor(color), 1.5))
                painter.drawLine(
                    QPointF(rect.center().x(), rect.top() - 9),
                    QPointF(rect.center().x(), rect.top()),
                )

    def _draw_role_card(self, painter, rect, role, player, accent):
        name = player.get("name", "미정") if isinstance(player, dict) else str(player or "미정")
        photo_path = player.get("photo", "") if isinstance(player, dict) else ""
        painter.setBrush(QBrush(QColor("#17232b")))
        painter.setPen(QPen(QColor(accent), 1))
        painter.drawRoundedRect(rect, 4, 4)
        portrait_size = min(34.0, rect.height() - 8)
        portrait = QRectF(
            rect.left() + 6,
            rect.top() + (rect.height() - portrait_size) / 2,
            portrait_size,
            portrait_size,
        )
        self._draw_portrait(painter, portrait, name, photo_path, accent)
        text_left = portrait.right() + 8
        painter.setPen(QColor(accent))
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.drawText(
            QRectF(text_left, rect.top() + 3, rect.right() - text_left - 6, 17),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            role,
        )
        painter.setPen(QColor("#eef3f5") if name != "미정" else QColor("#74828d"))
        painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        painter.drawText(
            QRectF(text_left, rect.top() + 20, rect.right() - text_left - 6, rect.height() - 21),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )

    def _draw_portrait(self, painter, rect, name, photo_path, accent):
        path = QPainterPath()
        path.addEllipse(rect)
        painter.save()
        painter.setClipPath(path)
        pixmap = self._photo_cache.get(photo_path)
        if photo_path and pixmap is None:
            pixmap = QPixmap(photo_path)
            self._photo_cache[photo_path] = pixmap
        if pixmap is not None and not pixmap.isNull():
            BaseballFieldWidget._draw_cover_pixmap(painter, rect, pixmap)
        else:
            painter.fillRect(rect, QColor("#2a3b45"))
            painter.setPen(QColor("#edf3f5"))
            painter.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name[-2:])
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(accent), 1))
        painter.drawEllipse(rect)


class SetLineupTab(QWidget):
    def __init__(self, parent_manager):
        super().__init__()
        self.manager = parent_manager
        self.current_tactic_id = None
        self.current_tactic_name = ""
        self.current_is_active = False
        self._loading = False
        self._initialized = False
        self._build_ui()

    @property
    def save_context(self):
        window = self.manager.parent_window
        if not window or window.save_id is None:
            return None
        return window.save_database, window.save_id, self.manager.team_key

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(7)

        toolbar = QFrame()
        toolbar.setObjectName("tacticToolbar")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(6)
        title = QLabel("전술 버전")
        title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        row.addWidget(title)
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(180)
        self.version_combo.currentIndexChanged.connect(self._version_changed)
        row.addWidget(self.version_combo)
        self.active_label = QLabel("편집 중")
        self.active_label.setObjectName("activeBadge")
        row.addWidget(self.active_label)
        for text, handler in (
            ("＋ 새 전술", self.create_version),
            ("복제", self.duplicate_version),
            ("이름 변경", self.rename_version),
            ("삭제", self.delete_version),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch()
        save_button = QPushButton("전술 저장")
        save_button.clicked.connect(lambda: self.save_version())
        row.addWidget(save_button)
        apply_button = QPushButton("저장 및 적용")
        apply_button.setObjectName("primaryAction")
        apply_button.clicked.connect(self.apply_version)
        row.addWidget(apply_button)
        root.addWidget(toolbar)

        hint = QLabel(
            "여러 전술을 저장해 상대 선발 유형과 경기 상황에 맞춰 교체할 수 있습니다. "
            "저장은 초안만 보관하며, ‘저장 및 적용’해야 실제 1군 배치가 변경됩니다."
        )
        hint.setObjectName("tacticHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.addTab(self._build_batting_page(), "타순 · 수비")
        self.editor_tabs.addTab(self._build_pitching_page(), "선발 · 불펜")
        self.editor_tabs.addTab(self._build_game_plan_page(), "경기 운영")
        root.addWidget(self.editor_tabs, 1)
        self.setStyleSheet(self._style())

    @staticmethod
    def _style():
        return """
        QFrame#tacticToolbar {
            background: #151d25; border: 1px solid #34424e; border-radius: 3px;
        }
        QLabel#activeBadge {
            color: #78d8ad; background: #18382e; border: 1px solid #28604c;
            border-radius: 8px; padding: 2px 8px; font-size: 13px; font-weight: 700;
        }
        QLabel#countBadge {
            color: #d8e2e8; background: #26343e; border: 1px solid #475661;
            border-radius: 8px; padding: 2px 9px; font-size: 13px; font-weight: 800;
        }
        QFrame#visualHeader {
            background: #17232b; border: 1px solid #344650; border-radius: 3px;
        }
        QFrame#visualHeader QLabel { color: #dce7eb; }
        QLabel#visualStatus { color: #65d5a5; font-size: 13px; }
        QFrame#approachPanel {
            background: #121c23; border: 1px solid #30414b; border-radius: 3px;
        }
        QFrame#approachPanel QLabel {
            color: #aebcc5; border-right: 1px solid #2f3d46;
            padding: 2px 8px; font-size: 13px; font-weight: 650;
        }
        QFrame#phaseCard {
            background: #121a21; border: 1px solid #34434e; border-radius: 5px;
        }
        QLabel[phaseTitle="true"] {
            color: #f0f4f6; font-size: 15px; font-weight: 800;
        }
        QLabel[phaseInnings="true"] {
            color: #8fa0ac; font-size: 13px; font-weight: 700;
        }
        QLabel[planLabel="true"] {
            color: #b9c5cc; font-size: 13px; font-weight: 650;
        }
        QComboBox[planControl="true"] {
            min-width: 100px; background: #1b2730; border-color: #41515d;
        }
        QFrame#gamePlanBanner {
            background: #15232b; border: 1px solid #3a4d58; border-radius: 4px;
        }
        QLabel#gamePlanSummary {
            color: #b8c7cf; background: #111920; border: 1px solid #33424c;
            border-radius: 3px; padding: 8px 12px; font-size: 13px;
        }
        QLabel#tacticHint { color: #91a2b1; padding: 1px 3px; font-size: 13px; }
        QLabel#poolTitle { color: #f0f4f6; font-size: 14px; font-weight: 850; padding-top: 4px; }
        QLabel#poolHelp { color: #7f929f; font-size: 13px; padding-top: 4px; }
        QListWidget#firstTeamPool {
            color: #dce6eb; background: #0e171e; border: 1px solid #344650;
            border-radius: 4px; outline: none; padding: 4px;
        }
        QListWidget#firstTeamPool::item {
            background: #18242c; border: 1px solid #2f414c; border-radius: 3px;
            margin: 1px; padding: 3px 8px; font-size: 13px; font-weight: 700;
        }
        QListWidget#firstTeamPool::item:hover { background: #223642; border-color: #587183; }
        QListWidget#firstTeamPool::item:selected { background: #29577a; border-color: #6d9abb; }
        QPushButton {
            background: #26323d; color: #dce5eb; border: 1px solid #43515e;
            border-radius: 2px; padding: 6px 11px; font-weight: 650;
        }
        QPushButton:hover { background: #334453; border-color: #607486; }
        QPushButton#primaryAction {
            background: #b89342; color: #111820; border-color: #d0ad5b;
            font-weight: 800;
        }
        QPushButton#primaryAction:hover { background: #d0aa50; }
        QComboBox {
            background: #10171e; color: #eef3f6; border: 1px solid #3c4a56;
            border-radius: 2px; padding: 5px 7px; min-height: 24px;
        }
        QComboBox::drop-down {
            border: 0; border-left: 1px solid #344550; width: 24px;
        }
        QTableWidget {
            background: #11181f; alternate-background-color: #182129;
            color: #e7edf1; border: 1px solid #34424e; gridline-color: #26333d;
            selection-background-color: #29577a;
        }
        QHeaderView::section {
            background: #202a33; color: #c9d3da; border: none;
            border-right: 1px solid #35434e; border-bottom: 1px solid #46545f;
            padding: 6px; font-size: 13px; font-weight: 700;
        }
        QTabWidget::pane { border: 1px solid #34424e; }
        """

    def _new_table(self, headers, accepts_players=False):
        table = LineupDropTable() if accepts_players else QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return table

    def _build_batting_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        visual_column = QVBoxLayout()
        visual_column.setSpacing(6)
        visual_header = QFrame()
        visual_header.setObjectName("visualHeader")
        visual_header_layout = QHBoxLayout(visual_header)
        visual_header_layout.setContentsMargins(10, 6, 10, 6)
        visual_title = QLabel("수비 포메이션")
        visual_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        visual_header_layout.addWidget(visual_title)
        visual_header_layout.addStretch()
        visual_status = QLabel("균형 수비  ·  표준 시프트")
        visual_status.setObjectName("visualStatus")
        visual_header_layout.addWidget(visual_status)
        visual_column.addWidget(visual_header)
        self.field_widget = BaseballFieldWidget(self.manager.team_key)
        self.field_widget.player_dropped.connect(self._drop_player_on_field)
        visual_column.addWidget(self.field_widget, 1)

        approach = QFrame()
        approach.setObjectName("approachPanel")
        approach_row = QHBoxLayout(approach)
        approach_row.setContentsMargins(10, 7, 10, 7)
        for title, detail in (
            ("공격 성향", "균형"),
            ("주루 판단", "상황 중심"),
            ("수비 시프트", "표준"),
        ):
            label = QLabel(f"{title}\n{detail}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            approach_row.addWidget(label, 1)
        visual_column.addWidget(approach)
        layout.addLayout(visual_column, 11)

        lineup_column = QVBoxLayout()
        lineup_column.setSpacing(5)
        lineup_header = QHBoxLayout()
        lineup_title = QLabel("선발 라인업")
        lineup_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        lineup_header.addWidget(lineup_title)
        lineup_header.addStretch()
        self.lineup_count_label = QLabel("0 / 9")
        self.lineup_count_label.setObjectName("countBadge")
        lineup_header.addWidget(self.lineup_count_label)
        lineup_column.addLayout(lineup_header)
        self.batting_table = self._new_table(
            ("타순", "선수", "수비 위치", "컨택", "파워", "선구", "컨디션"),
            accepts_players=True,
        )
        self.batting_table.player_dropped.connect(self._drop_player_on_batting_order)
        self.batting_table.setRowCount(9)
        self._stretch_table(self.batting_table, 1)
        lineup_column.addWidget(self.batting_table, 7)
        pool_header = QHBoxLayout()
        pool_title = QLabel("1군 선수 풀")
        pool_title.setObjectName("poolTitle")
        pool_header.addWidget(pool_title)
        pool_header.addStretch()
        pool_help = QLabel("선수를 끌어 타순 또는 수비 위치에 놓으세요")
        pool_help.setObjectName("poolHelp")
        pool_header.addWidget(pool_help)
        lineup_column.addLayout(pool_header)
        self.first_team_pool = FirstTeamPlayerPool()
        lineup_column.addWidget(self.first_team_pool, 3)
        self.lineup_note = QLabel(
            "투수는 수비 포메이션과 타순에 배치할 수 없습니다. 중복 선수는 새 위치로 자동 이동합니다."
        )
        self.lineup_note.setObjectName("tacticHint")
        lineup_column.addWidget(self.lineup_note)
        layout.addLayout(lineup_column, 13)
        return page

    def _build_pitching_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        visual_column = QVBoxLayout()
        visual_header = QFrame()
        visual_header.setObjectName("visualHeader")
        visual_header_row = QHBoxLayout(visual_header)
        visual_header_row.setContentsMargins(10, 6, 10, 6)
        visual_title = QLabel("투수 운용도")
        visual_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        visual_header_row.addWidget(visual_title)
        visual_header_row.addStretch()
        visual_header_row.addWidget(QLabel("선발 → 승리조 → 마무리"))
        visual_column.addWidget(visual_header)
        self.pitching_plan_widget = PitchingPlanWidget(self.manager.team_key)
        visual_column.addWidget(self.pitching_plan_widget, 1)
        layout.addLayout(visual_column, 10)

        editor_column = QVBoxLayout()
        editor_column.setSpacing(6)
        conversion_note = QLabel('선발 전환: 기존 보직과 관계없이 1군 투수를 선택할 수 있습니다.\n'
                                 '기존 불펜 배정을 비운 뒤 선발 슬롯에 배치하고 라인업을 저장하세요. 체력·구종도 확인하세요.')
        conversion_note.setWordWrap(True)
        editor_column.addWidget(conversion_note)
        starter_header = QHBoxLayout()
        starter_title = QLabel("선발 로테이션")
        starter_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        starter_title.setToolTip("1선발부터 5선발까지 등판 순서를 지정합니다.")
        starter_header.addWidget(starter_title)
        starter_header.addStretch()
        self.rotation_count_label = QLabel("0 / 5")
        self.rotation_count_label.setObjectName("countBadge")
        starter_header.addWidget(self.rotation_count_label)
        editor_column.addLayout(starter_header)
        self.starter_table = self._pitching_table(STARTER_ROLES)
        editor_column.addWidget(self.starter_table, 5)

        bullpen_header = QHBoxLayout()
        bullpen_title = QLabel("불펜 역할")
        bullpen_title.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        bullpen_title.setToolTip("추격조와 승리조를 분리해 경기 상황별 투입 순서를 정합니다.")
        bullpen_header.addWidget(bullpen_title)
        bullpen_header.addStretch()
        self.bullpen_count_label = QLabel("0 / 7")
        self.bullpen_count_label.setObjectName("countBadge")
        bullpen_header.addWidget(self.bullpen_count_label)
        editor_column.addLayout(bullpen_header)
        self.bullpen_table = self._pitching_table(BULLPEN_ROLES)
        editor_column.addWidget(self.bullpen_table, 7)
        layout.addLayout(editor_column, 14)
        return page

    def _build_game_plan_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(7, 7, 7, 7)
        root.setSpacing(8)

        banner = QFrame()
        banner.setObjectName("gamePlanBanner")
        banner_row = QHBoxLayout(banner)
        banner_row.setContentsMargins(13, 8, 13, 8)
        banner_copy = QVBoxLayout()
        banner_title = QLabel("이닝별 경기 운영 플랜")
        banner_title.setFont(QFont("Malgun Gothic", 12, QFont.Weight.Bold))
        banner_copy.addWidget(banner_title)
        banner_detail = QLabel(
            "점수와 선수 상태가 같아도 경기 구간에 따라 작전 선택 기준이 달라집니다."
        )
        banner_detail.setObjectName("tacticHint")
        banner_copy.addWidget(banner_detail)
        banner_row.addLayout(banner_copy)
        banner_row.addStretch()
        for _key, title, innings, color in GAME_PLAN_PHASES:
            badge = QLabel(f"{innings}\n{title}")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"color: {color}; background: #10181e; border: 1px solid {color}; "
                "border-radius: 4px; padding: 4px 12px; font-weight: 750;"
            )
            banner_row.addWidget(badge)
        root.addWidget(banner)

        self.game_plan_controls = {}
        cards = QHBoxLayout()
        cards.setSpacing(8)
        for phase_key, title, innings, color in GAME_PLAN_PHASES:
            card = QFrame()
            card.setObjectName("phaseCard")
            card.setStyleSheet(
                f"QFrame#phaseCard {{ border-top: 3px solid {color}; }}"
            )
            column = QVBoxLayout(card)
            column.setContentsMargins(11, 9, 11, 11)
            column.setSpacing(6)
            heading = QHBoxLayout()
            title_label = QLabel(title)
            title_label.setProperty("phaseTitle", True)
            heading.addWidget(title_label)
            heading.addStretch()
            innings_label = QLabel(innings)
            innings_label.setProperty("phaseInnings", True)
            innings_label.setStyleSheet(f"color: {color};")
            heading.addWidget(innings_label)
            column.addLayout(heading)

            divider = QFrame()
            divider.setFixedHeight(1)
            divider.setStyleSheet(f"background: {color};")
            column.addWidget(divider)

            phase_controls = {}
            for setting_key, label_text, options, description in GAME_PLAN_OPTIONS:
                setting_row = QHBoxLayout()
                setting_row.setSpacing(6)
                label = QLabel(label_text)
                label.setProperty("planLabel", True)
                label.setToolTip(description)
                setting_row.addWidget(label, 1)
                combo = QComboBox()
                combo.setProperty("planControl", True)
                combo.addItems(options)
                combo.setToolTip(description)
                combo.currentTextChanged.connect(self._update_game_plan_summary)
                setting_row.addWidget(combo, 1)
                column.addLayout(setting_row)
                phase_controls[setting_key] = combo
            column.addStretch()
            self.game_plan_controls[phase_key] = phase_controls
            cards.addWidget(card, 1)
        root.addLayout(cards, 1)

        self.game_plan_summary = QLabel()
        self.game_plan_summary.setObjectName("gamePlanSummary")
        self.game_plan_summary.setWordWrap(True)
        root.addWidget(self.game_plan_summary)
        self._load_game_plan(DEFAULT_GAME_PLAN)
        return page

    def _pitching_table(self, roles):
        table = self._new_table(("보직", "선수", "구위", "제구", "체력", "컨디션"))
        table.setRowCount(len(roles))
        table.verticalHeader().setDefaultSectionSize(43)
        self._stretch_table(table, 1)
        for row, role in enumerate(roles):
            self._set_center_item(table, row, 0, role, True)
            item = table.item(row, 0)
            if role == "마무리":
                color = QColor("#6d2f35")
            elif role.startswith(("필승조", "셋업맨")):
                color = QColor("#245645")
            elif role.endswith("선발"):
                color = QColor("#66542d")
            else:
                color = QColor("#2d4e5d")
            item.setBackground(color)
            item.setForeground(QColor("#f2f5f6"))
        return table

    @staticmethod
    def _stretch_table(table, stretch_column):
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)

    def refresh(self):
        if self._initialized:
            return
        self._initialized = True
        self._ensure_initial_version()
        self._reload_version_list()

    def reload(self):
        """메인 전술 페이지를 다시 열 때 최신 선수단과 저장 전술을 읽는다."""
        self.manager.load_players_from_db()
        if not self._initialized:
            self.refresh()
            return
        self._reload_version_list(self.current_tactic_id)

    def _ensure_initial_version(self):
        context = self.save_context
        if not context:
            self.current_tactic_name = "전술 1"
            self._populate_editor(*self._current_assignments())
            return
        database, save_id, team = context
        if not database.list_tactic_versions(save_id, team):
            batting, pitching = self._current_assignments()
            database.create_tactic_version(
                save_id, team, "전술 1", batting, pitching, DEFAULT_GAME_PLAN
            )

    def _reload_version_list(self, select_id=None):
        self._loading = True
        self.version_combo.clear()
        context = self.save_context
        versions = (
            context[0].list_tactic_versions(context[1], context[2])
            if context else [{"id": 0, "name": "전술 1", "is_active": 1}]
        )
        target = 0
        for index, version in enumerate(versions):
            suffix = "  · 적용 중" if version["is_active"] else ""
            self.version_combo.addItem(version["name"] + suffix, version["id"])
            if select_id is not None and version["id"] == select_id:
                target = index
        self.version_combo.setCurrentIndex(target)
        self._loading = False
        self._load_selected_version()

    def _version_changed(self, _index):
        if not self._loading:
            self._load_selected_version()

    def _load_selected_version(self):
        tactic_id = self.version_combo.currentData()
        context = self.save_context
        if context and tactic_id is not None:
            tactic = context[0].get_tactic_version(context[1], context[2], tactic_id)
            if not tactic:
                return
            self.current_tactic_id = tactic_id
            self.current_tactic_name = tactic["name"]
            self.current_is_active = bool(tactic["is_active"])
            self.active_label.setText("적용 중" if self.current_is_active else "편집 중")
            self._populate_editor(
                tactic["batting"], tactic["pitching"], tactic.get("game_plan")
            )
        elif not context:
            self.current_tactic_id = 0
            self.current_is_active = True
            self.active_label.setText("임시 전술")
            self._populate_editor(*self._current_assignments())

    def _current_assignments(self):
        batters = sorted(
            (p for p in self._batters() if int(p.get("lineup_pos") or 0) > 0),
            key=lambda p: int(p.get("lineup_pos") or 0),
        )
        batting, used_positions = [], set()
        for player in batters[:9]:
            raw_position = player.get("pos") or player.get("position_group") or ""
            candidates = {
                "IF": ("SS", "2B", "3B", "1B"),
                "OF": ("CF", "RF", "LF"),
            }.get(raw_position, (raw_position,))
            position = next(
                (
                    candidate for candidate in candidates
                    if candidate in DEFENSIVE_POSITIONS
                    and candidate not in used_positions
                ),
                None,
            )
            if position is None:
                position = next(
                    candidate for candidate in DEFENSIVE_POSITIONS
                    if candidate not in used_positions
                )
            used_positions.add(position)
            batting.append(
                {
                    "order": int(player["lineup_pos"]),
                    "player_id": player["id"],
                    "name": player["name"],
                    "position": position,
                }
            )
        pitching, assigned = [], set()
        pitchers = self._pitchers()
        for order, role in enumerate(STARTER_ROLES + BULLPEN_ROLES, 1):
            player = next(
                (p for p in pitchers
                 if p["id"] not in assigned and p.get("role") == role),
                None,
            )
            if player is None:
                preferred = []
                if role in STARTER_ROLES:
                    preferred = [
                        p for p in pitchers
                        if p["id"] not in assigned
                        and str(p.get("role") or "").startswith("선발")
                    ]
                    preferred.sort(
                        key=lambda p: (
                            float(p.get("pitcher_stamina") or 0),
                            float(p.get("pitcher_command") or 0),
                        ),
                        reverse=True,
                    )
                elif role == "마무리":
                    preferred = [
                        p for p in pitchers
                        if p["id"] not in assigned and p.get("role") == "마무리"
                    ]
                elif role.startswith(("필승조", "셋업맨")):
                    preferred = [
                        p for p in pitchers
                        if p["id"] not in assigned
                        and p.get("role") in ("필승조", "셋업맨")
                    ]
                elif role.startswith(("추격조", "롱릴리프")):
                    preferred = [
                        p for p in pitchers
                        if p["id"] not in assigned
                        and p.get("role") in ("불펜", "추격조", "롱릴리프")
                    ]
                player = preferred[0] if preferred else None
            if player is None:
                remaining = [p for p in pitchers if p["id"] not in assigned]
                remaining.sort(
                    key=lambda p: (
                        float(p.get("pitcher_stuff") or 0),
                        float(p.get("pitcher_command") or 0),
                    ),
                    reverse=True,
                )
                player = remaining[0] if remaining else None
            if player:
                assigned.add(player["id"])
                pitching.append(
                    {"role_order": order, "role": role, "player_id": player["id"], "name": player["name"]}
                )
        return batting, pitching

    def _populate_editor(self, batting, pitching, game_plan=None):
        if hasattr(self, "first_team_pool"):
            self.first_team_pool.set_players(
                [
                    player for player in self.manager.players
                    if int(player.get("status") or 0) == 1
                ]
            )
        batting_by_order = {int(item["order"]): item for item in batting}
        for row in range(9):
            order = row + 1
            self._set_center_item(self.batting_table, row, 0, order, True)
            combo = self._player_combo(self._batters())
            item = batting_by_order.get(order)
            self._select_player(combo, item.get("player_id") if item else None)
            combo.currentIndexChanged.connect(
                lambda _index, r=row, cb=combo: self._batter_changed(r, cb)
            )
            self.batting_table.setCellWidget(row, 1, combo)
            position = QComboBox()
            position.addItems(DEFENSIVE_POSITIONS)
            if item and item.get("position") in DEFENSIVE_POSITIONS:
                position.setCurrentText(item["position"])
            position.currentTextChanged.connect(self._update_batting_visual)
            self.batting_table.setCellWidget(row, 2, position)
            self._update_batter_stats(row, combo)

        by_role = {item["role"]: item for item in pitching}
        for table, roles in ((self.starter_table, STARTER_ROLES), (self.bullpen_table, BULLPEN_ROLES)):
            for row, role in enumerate(roles):
                combo = self._player_combo(self._pitchers())
                item = by_role.get(role)
                self._select_player(combo, item.get("player_id") if item else None)
                combo.currentIndexChanged.connect(
                    lambda _index, t=table, r=row, cb=combo:
                    self._pitcher_changed(t, r, cb)
                )
                table.setCellWidget(row, 1, combo)
                self._update_pitcher_stats(table, row, combo)
        self._update_batting_visual()
        self._update_pitching_visual()
        self._load_game_plan(game_plan or DEFAULT_GAME_PLAN)

    @staticmethod
    def _select_player(combo, player_id):
        index = combo.findData(player_id)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _player_combo(self, players):
        combo = QComboBox()
        combo.setIconSize(QSize(28, 28))
        combo.addItem("— 미정 —", None)
        for player in players:
            visual = _player_visual(player)
            text = f"{player['name']}  ·  {player.get('pos') or '-'}"
            if visual["photo"]:
                combo.addItem(QIcon(visual["photo"]), text, player["id"])
            else:
                combo.addItem(text, player["id"])
        return combo

    def _batters(self):
        return [
            p for p in self.manager.players
            if int(p.get("status") or 0) == 1
            and p.get("pos") != "P" and p.get("position_group") != "P"
        ]

    def _pitchers(self):
        return [
            p for p in self.manager.players
            if int(p.get("status") or 0) == 1
            and (p.get("pos") == "P" or p.get("position_group") == "P")
        ]

    def _find_player(self, player_id):
        return next((p for p in self.manager.players if p["id"] == player_id), None)

    def _drop_player_on_batting_order(self, player_id, row):
        player = self._find_player(player_id)
        if not player:
            return
        if player.get("pos") == "P" or player.get("position_group") == "P":
            self.lineup_note.setText("투수는 타순·수비 선수 풀에 배치할 수 없습니다. 투수 운용 탭을 이용하세요.")
            return
        self._assign_batter(player_id, max(0, min(row, 8)))
        self.lineup_note.setText(f"{player['name']}을(를) {row + 1}번 타순에 배치했습니다.")

    def _drop_player_on_field(self, player_id, position):
        player = self._find_player(player_id)
        if not player:
            return
        if player.get("pos") == "P" or player.get("position_group") == "P":
            self.lineup_note.setText("투수는 별도의 선발·불펜 탭에서 배치합니다.")
            return
        target_row = None
        for row in range(self.batting_table.rowCount()):
            combo = self.batting_table.cellWidget(row, 1)
            if combo and combo.currentData() == player_id:
                target_row = row
                break
        if target_row is None:
            for row in range(self.batting_table.rowCount()):
                position_combo = self.batting_table.cellWidget(row, 2)
                if position_combo and position_combo.currentText() == position:
                    target_row = row
                    break
        if target_row is None:
            target_row = next(
                (
                    row for row in range(self.batting_table.rowCount())
                    if self.batting_table.cellWidget(row, 1).currentData() is None
                ),
                0,
            )
        self._assign_batter(player_id, target_row, position)
        self.lineup_note.setText(f"{player['name']}을(를) {position} 수비 위치에 배치했습니다.")

    def _assign_batter(self, player_id, target_row, position=None):
        for row in range(self.batting_table.rowCount()):
            combo = self.batting_table.cellWidget(row, 1)
            if combo and combo.currentData() == player_id and row != target_row:
                combo.setCurrentIndex(0)
        target_combo = self.batting_table.cellWidget(target_row, 1)
        if target_combo:
            index = target_combo.findData(player_id)
            if index >= 0:
                target_combo.setCurrentIndex(index)
        if position:
            position_combo = self.batting_table.cellWidget(target_row, 2)
            if position_combo:
                previous_position = position_combo.currentText()
                for row in range(self.batting_table.rowCount()):
                    if row == target_row:
                        continue
                    other_position = self.batting_table.cellWidget(row, 2)
                    if other_position and other_position.currentText() == position:
                        other_position.setCurrentText(previous_position)
                        break
                position_combo.setCurrentText(position)
        self._update_batting_visual()

    def _update_batter_stats(self, row, combo):
        player = self._find_player(combo.currentData())
        values = (
            (player.get("contact", player.get("con")), player.get("power", player.get("pow")),
             player.get("plate_discipline", player.get("eye")), player.get("sim_condition"))
            if player else (None, None, None, None)
        )
        for column, value in enumerate(values, 3):
            self._set_rating_item(self.batting_table, row, column, value)

    def _batter_changed(self, row, combo):
        self._update_batter_stats(row, combo)
        self._update_batting_visual()

    def _update_pitcher_stats(self, table, row, combo):
        player = self._find_player(combo.currentData())
        values = (
            (player.get("pitcher_stuff"), player.get("pitcher_command"),
             player.get("pitcher_stamina"), player.get("sim_condition"))
            if player else (None, None, None, None)
        )
        for column, value in enumerate(values, 2):
            self._set_rating_item(table, row, column, value)

    def _pitcher_changed(self, table, row, combo):
        self._update_pitcher_stats(table, row, combo)
        self._update_pitching_visual()

    def _update_batting_visual(self, *_args):
        lineup = {}
        selected_count = 0
        if not hasattr(self, "batting_table"):
            return
        for row in range(self.batting_table.rowCount()):
            player_combo = self.batting_table.cellWidget(row, 1)
            position_combo = self.batting_table.cellWidget(row, 2)
            if not player_combo or not position_combo:
                continue
            player = self._find_player(player_combo.currentData())
            if player:
                selected_count += 1
                lineup[position_combo.currentText()] = _player_visual(player)
        starter = {}
        if hasattr(self, "starter_table"):
            starter_combo = self.starter_table.cellWidget(0, 1)
            starter_player = (
                self._find_player(starter_combo.currentData())
                if starter_combo else None
            )
            starter = _player_visual(starter_player)
        self.lineup_count_label.setText(f"{selected_count} / 9")
        self.field_widget.set_lineup(lineup, starter)

    def _update_pitching_visual(self):
        if not hasattr(self, "starter_table"):
            return
        rotation = []
        rotation_count = 0
        for row in range(self.starter_table.rowCount()):
            combo = self.starter_table.cellWidget(row, 1)
            player = self._find_player(combo.currentData()) if combo else None
            rotation.append(_player_visual(player))
            rotation_count += 1 if player else 0
        bullpen = {}
        bullpen_count = 0
        for row, role in enumerate(BULLPEN_ROLES):
            combo = self.bullpen_table.cellWidget(row, 1)
            player = self._find_player(combo.currentData()) if combo else None
            if player:
                bullpen[role] = _player_visual(player)
                bullpen_count += 1
        self.rotation_count_label.setText(f"{rotation_count} / 5")
        self.bullpen_count_label.setText(f"{bullpen_count} / 7")
        self.pitching_plan_widget.set_plan(rotation, bullpen)
        self._update_batting_visual()

    def _load_game_plan(self, game_plan):
        if not hasattr(self, "game_plan_controls"):
            return
        for phase_key, controls in self.game_plan_controls.items():
            phase_values = game_plan.get(phase_key, {})
            defaults = DEFAULT_GAME_PLAN[phase_key]
            for setting_key, combo in controls.items():
                value = phase_values.get(setting_key, defaults[setting_key])
                index = combo.findText(value)
                combo.setCurrentIndex(index if index >= 0 else 0)
        self._update_game_plan_summary()

    def _game_plan_payload(self):
        return {
            phase_key: {
                setting_key: combo.currentText()
                for setting_key, combo in controls.items()
            }
            for phase_key, controls in self.game_plan_controls.items()
        }

    def _update_game_plan_summary(self, *_args):
        if not hasattr(self, "game_plan_summary"):
            return
        phase_titles = {
            phase_key: f"{title}({innings})"
            for phase_key, title, innings, _color in GAME_PLAN_PHASES
        }
        summaries = []
        for phase_key, controls in self.game_plan_controls.items():
            summaries.append(
                f"{phase_titles[phase_key]}  "
                f"{controls['offense'].currentText()} 공격 · "
                f"번트 {controls['bunt'].currentText()} · "
                f"선발 교체 {controls['starter_hook'].currentText()} · "
                f"불펜 {controls['bullpen'].currentText()}"
            )
        self.game_plan_summary.setText("     →     ".join(summaries))

    @staticmethod
    def _set_center_item(table, row, column, text, bold=False):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        table.setItem(row, column, item)

    @staticmethod
    def _set_rating_item(table, row, column, value):
        item = QTableWidgetItem("—" if value is None else str(int(float(value))))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if value is not None:
            score = float(value)
            if column == table.columnCount() - 1:
                color = "#49c58b" if score >= 80 else "#e2bd58" if score >= 60 else "#df6d6d"
            else:
                color = "#49c58b" if score >= 15 else "#e2bd58" if score >= 10 else "#df6d6d"
            item.setForeground(QColor(color))
        table.setItem(row, column, item)

    def _collect_assignments(self, require_complete=False):
        batting, batter_ids, positions = [], set(), set()
        for row in range(9):
            player_id = self.batting_table.cellWidget(row, 1).currentData()
            if player_id is None:
                if require_complete:
                    raise ValueError(f"{row + 1}번 타자를 지정해 주세요.")
                continue
            player = self._find_player(player_id)
            if player_id in batter_ids:
                raise ValueError(f"{player['name']} 선수가 타순에 중복 배치되었습니다.")
            position = self.batting_table.cellWidget(row, 2).currentText()
            if position in positions:
                raise ValueError(f"{position} 수비 위치가 중복되었습니다.")
            batter_ids.add(player_id)
            positions.add(position)
            batting.append(
                {"order": row + 1, "player_id": player_id, "name": player["name"], "position": position}
            )

        pitching, pitcher_ids, role_order = [], set(), 0
        for table, roles in ((self.starter_table, STARTER_ROLES), (self.bullpen_table, BULLPEN_ROLES)):
            for row, role in enumerate(roles):
                role_order += 1
                player_id = table.cellWidget(row, 1).currentData()
                if player_id is None:
                    if require_complete:
                        raise ValueError(f"{role} 투수를 지정해 주세요.")
                    continue
                player = self._find_player(player_id)
                if player_id in pitcher_ids:
                    raise ValueError(f"{player['name']} 투수가 여러 보직에 중복 배치되었습니다.")
                pitcher_ids.add(player_id)
                pitching.append(
                    {"role_order": role_order, "role": role, "player_id": player_id, "name": player["name"]}
                )
        return batting, pitching

    def _suggest_name(self):
        context = self.save_context
        count = len(context[0].list_tactic_versions(context[1], context[2])) if context else 0
        return f"전술 {count + 1}"

    def create_version(self):
        context = self.save_context
        if not context:
            QMessageBox.information(self, "전술", "게임을 시작한 뒤 전술 버전을 저장할 수 있습니다.")
            return
        name, accepted = QInputDialog.getText(self, "새 전술", "전술 이름", text=self._suggest_name())
        if not accepted or not name.strip():
            return
        try:
            tactic_id = context[0].create_tactic_version(
                context[1], context[2], name.strip(), [], [],
                DEFAULT_GAME_PLAN,
            )
        except Exception as error:
            QMessageBox.warning(self, "생성 실패", f"같은 이름의 전술이 이미 있습니다.\n{error}")
            return
        self._reload_version_list(tactic_id)

    def duplicate_version(self):
        context = self.save_context
        if not context or self.current_tactic_id is None:
            return
        try:
            batting, pitching = self._collect_assignments(False)
        except ValueError as error:
            QMessageBox.warning(self, "확인 필요", str(error))
            return
        name, accepted = QInputDialog.getText(
            self, "전술 복제", "복제본 이름", text=f"{self.current_tactic_name} 복사본"
        )
        if not accepted or not name.strip():
            return
        try:
            tactic_id = context[0].create_tactic_version(
                context[1], context[2], name.strip(), batting, pitching,
                self._game_plan_payload(),
            )
        except Exception as error:
            QMessageBox.warning(self, "복제 실패", f"전술 이름을 확인해 주세요.\n{error}")
            return
        self._reload_version_list(tactic_id)

    def rename_version(self):
        context = self.save_context
        if not context or self.current_tactic_id is None:
            return
        name, accepted = QInputDialog.getText(
            self, "전술 이름 변경", "새 이름", text=self.current_tactic_name
        )
        if not accepted or not name.strip():
            return
        try:
            batting, pitching = self._collect_assignments(False)
            context[0].update_tactic_version(
                context[1], context[2], self.current_tactic_id,
                name.strip(), batting, pitching, self._game_plan_payload()
            )
        except Exception as error:
            QMessageBox.warning(self, "변경 실패", f"전술 이름을 확인해 주세요.\n{error}")
            return
        self.current_tactic_name = name.strip()
        self._reload_version_list(self.current_tactic_id)

    def delete_version(self):
        context = self.save_context
        if not context or self.current_tactic_id is None:
            return
        if len(context[0].list_tactic_versions(context[1], context[2])) <= 1:
            QMessageBox.information(self, "삭제 불가", "최소 한 개의 전술은 남겨야 합니다.")
            return
        if self.current_is_active:
            QMessageBox.information(
                self,
                "삭제 불가",
                "현재 적용 중인 전술입니다. 다른 전술을 먼저 적용한 뒤 삭제해 주세요.",
            )
            return
        answer = QMessageBox.question(
            self, "전술 삭제", f"‘{self.current_tactic_name}’ 전술을 삭제할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        context[0].delete_tactic_version(context[1], context[2], self.current_tactic_id)
        self._reload_version_list()

    def save_version(self, show_message=True):
        context = self.save_context
        if not context or self.current_tactic_id is None:
            return False
        try:
            batting, pitching = self._collect_assignments(False)
            context[0].update_tactic_version(
                context[1], context[2], self.current_tactic_id,
                self.current_tactic_name, batting, pitching,
                self._game_plan_payload(),
            )
        except Exception as error:
            QMessageBox.warning(self, "저장 실패", str(error))
            return False
        if show_message:
            QMessageBox.information(self, "전술 저장", "전술 초안을 저장했습니다.")
        return True

    def apply_version(self):
        context = self.save_context
        if not context or self.current_tactic_id is None:
            return
        try:
            batting, pitching = self._collect_assignments(True)
            context[0].update_tactic_version(
                context[1], context[2], self.current_tactic_id,
                self.current_tactic_name, batting, pitching,
                self._game_plan_payload(),
            )
            self.manager.apply_tactic_to_db(batting, pitching)
            context[0].activate_tactic_version(context[1], context[2], self.current_tactic_id)
        except Exception as error:
            QMessageBox.warning(self, "적용 실패", str(error))
            return
        self._reload_version_list(self.current_tactic_id)
        QMessageBox.information(
            self, "전술 적용 완료", f"‘{self.current_tactic_name}’ 전술을 현재 1군 배치에 적용했습니다."
        )
