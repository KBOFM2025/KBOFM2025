"""FM 스타일의 고밀도 선수단 관리 테이블."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.player_ratings import overall_rating


NAME_COLUMN = 4


class SortableItem(QTableWidgetItem):
    """표시 문자열과 별개로 실제 숫자를 기준으로 정렬한다."""

    def __init__(self, text, sort_value=None):
        super().__init__(str(text))
        self.sort_value = sort_value

    def __lt__(self, other):
        if (
            isinstance(other, SortableItem)
            and self.sort_value is not None
            and other.sort_value is not None
        ):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class DenseRosterTable(QTableWidget):
    HEADERS = (
        "구분",
        "포지션",
        "현재 능력",
        "잠재력",
        "선수",
        "국적",
        "컨디션",
        "경기 감각",
        "사기",
        "피로",
        "현재 상태",
        "역할 / 보직",
        "종합",
        "나이",
        "투타",
        "가능 포지션",
        "연봉",
    )

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(27)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setMinimumSectionSize(42)
        self.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        self._configure_widths()
        self.setStyleSheet(self._style(colors))

    def _configure_widths(self):
        header = self.horizontalHeader()
        for column in range(len(self.HEADERS)):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
        widths = (
            58, 66, 92, 92, 140, 52, 102, 102, 88,
            88, 112, 120, 58, 48, 72, 128, 92,
        )
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)
        header.setStretchLastSection(False)
        for column in (4, 10, 11, 15):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
        self.horizontalHeaderItem(2).setToolTip(
            "현재 종합 능력을 5단계 별점으로 환산합니다."
        )
        self.horizontalHeaderItem(3).setToolTip(
            "현재 능력과 나이·신인 여부를 반영한 게임 내 성장 전망입니다."
        )

    def populate(self, players, roster_status):
        self.setSortingEnabled(False)
        self.clearContents()
        self.setRowCount(len(players))
        for row, player in enumerate(players):
            self._populate_row(row, player, roster_status)
        self.setSortingEnabled(True)
        self.sortItems(0, Qt.SortOrder.AscendingOrder)

    def _populate_row(self, row, player, roster_status):
        overall = float(overall_rating(player))
        potential = self._potential(player, overall)
        condition = self._number(player, "sim_condition", None)
        sharpness = self._number(
            player, "sim_match_sharpness", None
        )
        morale = self._number(player, "sim_morale", None)
        fatigue = self._number(player, "sim_fatigue", None)
        slot, slot_color = self._slot(player, roster_status)
        position = player.get("pos") or player.get(
            "position_group", "-"
        )
        nationality = "외" if player.get("is_foreign") else "KOR"
        injury_days = int(player.get("sim_injury_days") or 0)
        status = (
            f"{player.get('sim_injury_type') or '부상'} "
            f"{injury_days}일"
            if injury_days
            else player.get("sim_squad_group")
            or ("1군" if roster_status else "육성")
        )
        assignment = (
            player.get("simulation_assignment")
            or player.get("role")
            or "보직 미정"
        )
        if assignment == "선수":
            assignment = "보직 미정"

        slot_item = SortableItem(slot, self._slot_order(slot))
        slot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        slot_item.setBackground(QColor(slot_color))
        slot_item.setForeground(QColor("#ffffff"))
        self.setItem(row, 0, slot_item)

        position_item = QTableWidgetItem(str(position))
        position_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        position_item.setForeground(
            QColor(self._position_color(position))
        )
        self.setItem(row, 1, position_item)

        self._star_item(row, 2, overall, "#f0c94f")
        self._star_item(row, 3, potential, "#d9b84b")

        name_item = QTableWidgetItem(player.get("name", "-"))
        name_item.setData(Qt.ItemDataRole.UserRole, player)
        name_item.setToolTip(
            f"{player.get('name', '-')} 선수 전체 보고서 열기"
        )
        font = name_item.font()
        font.setBold(True)
        name_item.setFont(font)
        name_item.setForeground(QColor("#f3f6f8"))
        self.setItem(row, NAME_COLUMN, name_item)

        self._center_item(row, 5, nationality)
        self._set_bar(row, 6, condition, "#42c89a")
        self._set_bar(row, 7, sharpness, "#50b878")
        self._center_item(
            row,
            8,
            self._morale_text(morale),
            morale if morale is not None else -1,
        )
        self._set_bar(
            row,
            9,
            fatigue,
            "#d98b42"
            if fatigue is None or fatigue < 70
            else "#d54d4d",
        )

        status_item = QTableWidgetItem(str(status))
        status_item.setForeground(
            QColor("#e06161" if injury_days else "#85cba8")
        )
        self.setItem(row, 10, status_item)
        self.setItem(row, 11, QTableWidgetItem(str(assignment)))
        self._rating_item(row, 12, overall)
        self._center_item(
            row, 13, player.get("age", "-"),
            int(player.get("age") or 0),
        )
        self._center_item(
            row, 14, player.get("bats_throws") or "-"
        )
        self.setItem(
            row, 15, QTableWidgetItem(str(position))
        )
        salary = int(player.get("salary") or 0)
        self.setItem(
            row,
            16,
            SortableItem(self._salary_text(salary), salary),
        )

    def _star_item(self, row, column, value, color):
        item = SortableItem(self._stars(value), float(value))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(color))
        font = item.font()
        font.setBold(True)
        font.setPointSize(11)
        item.setFont(font)
        self.setItem(row, column, item)

    def selected_player(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.item(rows[0].row(), NAME_COLUMN)
        return (
            item.data(Qt.ItemDataRole.UserRole)
            if item is not None else None
        )

    def player_at(self, row):
        item = self.item(row, NAME_COLUMN)
        return (
            item.data(Qt.ItemDataRole.UserRole)
            if item is not None else None
        )

    def _set_bar(self, row, column, value, color):
        if value is None:
            item = SortableItem("—", -1)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor("#65727e"))
            self.setItem(row, column, item)
            return
        numeric = max(0, min(100, int(value)))
        item = SortableItem(str(numeric), numeric)
        self.setItem(row, column, item)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(numeric)
        bar.setFormat(f"{numeric}%")
        bar.setTextVisible(True)
        bar.setStyleSheet(
            "QProgressBar {"
            "color: #dbe5ec;"
            "background: #10151a;"
            "border: none;"
            "text-align: center;"
            "font-size: 9px;"
            "font-weight: 700;"
            "}"
            "QProgressBar::chunk {"
            f"background: {color};"
            "}"
        )
        self.setCellWidget(row, column, bar)

    def _rating_item(self, row, column, value):
        item = SortableItem(f"{float(value):.1f}", float(value))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(self._rating_color(value)))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.setItem(row, column, item)

    def _center_item(self, row, column, text, sort_value=None):
        item = SortableItem(text, sort_value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, column, item)

    @staticmethod
    def _number(player, key, default):
        value = player.get(key)
        if value is not None:
            return int(value)
        return int(default) if default is not None else None

    @staticmethod
    def _potential(player, overall):
        age = int(player.get("age") or 27)
        growth = max(0.0, min(4.5, (28 - age) * 0.45))
        if player.get("is_rookie"):
            growth += 1.0
        return min(20.0, round(overall + growth, 1))

    @staticmethod
    def _stars(value):
        filled = max(0, min(5, round(float(value) / 4)))
        return "★" * filled + "☆" * (5 - filled)

    @staticmethod
    def _morale_text(value):
        if value is None:
            return "— 미측정"
        if value >= 85:
            return f"▲ 매우 좋음 {value}"
        if value >= 70:
            return f"● 좋음 {value}"
        if value >= 50:
            return f"─ 보통 {value}"
        return f"▼ 낮음 {value}"

    @staticmethod
    def _slot(player, roster_status):
        if not roster_status:
            if int(player.get("sim_injury_days") or 0) > 0:
                return "재활", "#7d343b"
            return "2군", "#293849"
        assignment = str(
            player.get("simulation_assignment")
            or player.get("role")
            or ""
        )
        lineup = int(player.get("lineup_pos") or 0)
        is_pitcher = (
            player.get("position_group") == "P"
            or player.get("pos") == "P"
        )
        if is_pitcher and assignment not in ("", "선수", "보직 미정"):
            return assignment[:4], "#40577c"
        if lineup > 0:
            return f"S{lineup}", "#8b292d"
        return "B", "#59472b"

    @staticmethod
    def _slot_order(slot):
        if slot.startswith("S") and slot[1:].isdigit():
            return int(slot[1:])
        order = {
            "선발": 20,
            "불펜": 30,
            "마무리": 40,
            "B": 50,
            "재활": 80,
            "2군": 90,
        }
        return order.get(slot, 35)

    @staticmethod
    def _position_color(position):
        text = str(position)
        if text == "P":
            return "#68b2e8"
        if text == "C":
            return "#df7f91"
        if "OF" in text or text in ("LF", "CF", "RF"):
            return "#5ed2c7"
        return "#7fa8ee"

    @staticmethod
    def _rating_color(value):
        value = float(value)
        if value >= 15:
            return "#4fe18f"
        if value >= 12:
            return "#d6c655"
        if value >= 9:
            return "#e39950"
        return "#df6262"

    @staticmethod
    def _salary_text(amount):
        if amount >= 10000:
            return f"{amount / 10000:.1f}억원"
        return f"{amount:,}만원"

    @staticmethod
    def _style(colors):
        return f"""
            QTableWidget {{
                color: #cfd8df;
                background-color: #12161b;
                alternate-background-color: #1a1f25;
                border: 1px solid #343e47;
                outline: none;
                font-size: 10px;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid #262d34;
                padding: 2px 5px;
            }}
            QTableWidget::item:selected {{
                color: white;
                background-color: {colors['tab_selected']};
            }}
            QHeaderView::section {{
                color: #aeb9c3;
                background-color: #20262d;
                border: none;
                border-right: 1px solid #343e47;
                border-bottom: 2px solid {colors['accent']};
                padding: 6px 5px;
                font-size: 10px;
                font-weight: 800;
            }}
        """


class DenseRosterTab(QWidget):
    """1군과 퓨처스가 공유하는 검색·필터·선수 이동 화면."""

    def __init__(
        self,
        manager,
        roster_status,
        action_text,
        action_color,
        parent=None,
    ):
        super().__init__(parent)
        self.manager = manager
        self.roster_status = int(roster_status)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        toolbar = QFrame()
        toolbar.setObjectName("RosterToolbar")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(9, 6, 9, 6)
        tools.setSpacing(7)
        self.info_label = QLabel()
        self.info_label.setObjectName("RosterInfo")
        tools.addWidget(self.info_label)
        tools.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("선수 검색")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(150)
        self.search.textChanged.connect(self.refresh)
        tools.addWidget(self.search)
        self.position_filter = QComboBox()
        self.position_filter.addItem("모든 포지션", "")
        self.position_filter.addItem("투수", "P")
        self.position_filter.addItem("포수", "C")
        self.position_filter.addItem("내야수", "IF")
        self.position_filter.addItem("외야수", "OF")
        self.position_filter.currentIndexChanged.connect(self.refresh)
        tools.addWidget(self.position_filter)
        self.action_button = QPushButton(action_text)
        self.action_button.setStyleSheet(
            "QPushButton {"
            f"background: {action_color};"
            "color: white;"
            "border: 1px solid rgba(255,255,255,45);"
            "border-radius: 2px;"
            "padding: 7px 13px;"
            "font-size: 11px;"
            "font-weight: 800;"
            "}"
            "QPushButton:hover {"
            "border-color: white;"
            "}"
        )
        tools.addWidget(self.action_button)
        root.addWidget(toolbar)

        hint = QLabel(
            "선수명을 누르면 전체 보고서  ·  열 제목을 누르면 정렬  ·  "
            "열 경계를 드래그하면 폭 조절"
        )
        hint.setObjectName("RosterHint")
        root.addWidget(hint)

        self.table = DenseRosterTable(manager.colors)
        self.table.cellClicked.connect(self._cell_clicked)
        self.table.cellDoubleClicked.connect(
            lambda row, _column: self._open_player(row)
        )
        root.addWidget(self.table, 1)
        self.setStyleSheet(
            """
            QFrame#RosterToolbar {
                background-color: #181e25;
                border: 1px solid #35404a;
            }
            QLabel#RosterInfo {
                color: #e5ebf0;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#RosterHint {
                color: #778694;
                padding: 1px 4px;
                font-size: 9px;
            }
            QLineEdit, QComboBox {
                color: #e5ebf0;
                background-color: #10151a;
                border: 1px solid #3a4651;
                border-radius: 2px;
                padding: 5px 7px;
                font-size: 10px;
            }
            """
        )

    def refresh(self, *_args):
        players = [
            player for player in self.manager.players
            if int(player.get("status") or 0) == self.roster_status
        ]
        query = self.search.text().strip().lower()
        position = self.position_filter.currentData()
        if query:
            players = [
                player for player in players
                if query in str(player.get("name") or "").lower()
            ]
        if position:
            players = [
                player for player in players
                if self._matches_position(player, position)
            ]
        pitchers = sum(
            self._matches_position(player, "P")
            for player in players
        )
        injured = sum(
            int(player.get("sim_injury_days") or 0) > 0
            for player in players
        )
        label = "1군 엔트리" if self.roster_status else (
            self.manager.reserve_team_label
        )
        self.info_label.setText(
            f"{label}  {len(players)}명  |  "
            f"투수 {pitchers} · 야수 {len(players) - pitchers} · "
            f"부상 {injured}"
        )
        self.table.populate(players, self.roster_status)

    def selected_player(self):
        return self.table.selected_player()

    def _cell_clicked(self, row, column):
        if column == NAME_COLUMN:
            self._open_player(row)

    def _open_player(self, row):
        player = self.table.player_at(row)
        if player:
            self.manager.show_player_profile(player)

    @staticmethod
    def _matches_position(player, position):
        group = player.get("position_group")
        pos = str(player.get("pos") or "")
        if position == "P":
            return group == "P" or pos == "P"
        if position == "C":
            return group == "C" or pos == "C"
        if position == "IF":
            return group == "IF" or pos in (
                "1B", "2B", "3B", "SS", "IF"
            )
        if position == "OF":
            return group == "OF" or pos in (
                "LF", "CF", "RF", "OF"
            )
        return True
