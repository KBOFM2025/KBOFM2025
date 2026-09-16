"""외국인 선수 재계약·방출 및 FA 시장 페이지."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.services.foreign_players import (
    FOREIGN_CAP_SOURCE, NEW_FOREIGN_CAP_USD, TEAM_FOREIGN_CAP_USD,
)
from app.views.agent_consultation import AgentConsultationDialog


class ForeignPlayerMarketPage(QWidget):
    roster_changed = Signal()
    player_requested = Signal(dict)
    domestic_contract_requested = Signal(dict)

    def __init__(self, colors, service, domestic_fa_service=None, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.service = service
        self.domestic_fa_service = domestic_fa_service
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("ForeignHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 13, 18, 13)
        copy = QVBoxLayout()
        eyebrow = QLabel("KBO FOREIGN PLAYER CENTRE")
        eyebrow.setObjectName("ForeignEyebrow")
        title = QLabel("이적 및 FA 센터")
        title.setObjectName("ForeignTitle")
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(QLabel(
            "KBO 국내 FA 에이전트 협상과 외국인 선수 계약을 한 화면에서 관리합니다."
        ))
        self.domestic_status_label = QLabel()
        self.domestic_status_label.setObjectName("MarketStatus")
        copy.addWidget(self.domestic_status_label)
        row.addLayout(copy)
        row.addStretch()
        self.slot_label = QLabel()
        self.slot_label.setObjectName("SlotBadge")
        row.addWidget(self.slot_label)
        root.addWidget(header)

        budget_strip = QHBoxLayout()
        budget_strip.setSpacing(10)
        self.budget_cap = self._budget_card("KBO 구단 한도", "cap")
        self.budget_spent = self._budget_card("현재 계약 지출", "spent")
        self.budget_available = self._budget_card("추가 사용 가능", "available")
        budget_strip.addWidget(self.budget_cap[0])
        budget_strip.addWidget(self.budget_spent[0])
        budget_strip.addWidget(self.budget_available[0])
        root.addLayout(budget_strip)

        self.tabs = QTabWidget()
        self.current_table = self._table(
            ("선수", "주 포지션", "나이", "종합", "2025 계약 총액", "재계약 요구액",
             "계약 만료", "상태", "결정")
        )
        self.market_table = self._table(
            ("선수", "국적", "구분", "주 포지션", "나이", "예상 능력", "신뢰도",
             "요구 총액", "스카우팅 요약", "협상")
        )
        self.league_budget_table = self._table(
            ("구단", "외국인", "KBO 한도", "현재 지출", "사용 가능", "계약 내역")
        )
        self.domestic_fa_table = self._table((
            "선수", "원소속팀", "포지션", "나이", "종합", "FA 등급",
            "전년도 연봉", "보상 부담", "희망 위상", "에이전트 협상",
        ))
        if self.domestic_fa_service is not None:
            self.tabs.addTab(self.domestic_fa_table, "KBO 국내 FA")
        self.tabs.addTab(self.current_table, "보유 외국인 · 재계약/방출")
        self.tabs.addTab(self.market_table, "외국인 FA 시장")
        self.tabs.addTab(self.league_budget_table, "10개 구단 외인 예산")
        root.addWidget(self.tabs, 1)

        rule = QLabel(
            f"KBO 규정 · 일반 외국인 3명 / 투수 최대 2명 · "
            f"신규 선수 1인 계약 총액 상한 ${NEW_FOREIGN_CAP_USD:,} · "
            f"구단 계약 총액 한도 ${TEAM_FOREIGN_CAP_USD:,}  ·  "
            f'<a style="color:#72bce8" href="{FOREIGN_CAP_SOURCE}">KBO 근거</a><br>'
            "※ 구단 내부 현금예산은 비공개이므로 사용 가능액은 KBO 한도에서 공개 계약액을 차감한 금액입니다."
        )
        rule.setObjectName("RuleNote")
        rule.setOpenExternalLinks(True)
        root.addWidget(rule)
        profile = self.service.scouting_profile()
        self.scout_label = QLabel(
            f"{profile['team']} 국제 스카우트팀 · "
            f"발굴력 {profile['discovery']}/20 · 평가 정확도 {profile['accuracy']}/20 · "
            f"해외 네트워크 {profile['network']}/20"
        )
        self.scout_label.setObjectName("ScoutNote")
        root.addWidget(self.scout_label)
        self.setStyleSheet(self._style())
        self.current_table.cellDoubleClicked.connect(self._open_current_row)
        self.market_table.cellDoubleClicked.connect(self._open_market_row)
        self.refresh()

    def _budget_card(self, title, kind):
        card = QFrame()
        card.setObjectName("BudgetCard")
        card.setProperty("kind", kind)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("BudgetTitle")
        value = QLabel("$0")
        value.setObjectName("BudgetValue")
        progress = QProgressBar()
        progress.setObjectName("BudgetBar")
        progress.setRange(0, 100)
        progress.setTextVisible(False)
        caption = QLabel("0%")
        caption.setObjectName("BudgetCaption")
        layout.addWidget(label)
        layout.addWidget(value)
        layout.addWidget(progress)
        layout.addWidget(caption)
        return card, value, progress, caption

    def _table(self, headers):
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(50)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = table.horizontalHeader()
        for column in range(len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        widths = (
            (122, 82, 52, 62, 122, 116, 96, 76, 174)
            if headers[-1] == "결정"
            else (122, 72, 58, 82, 52, 94, 72, 112, 250, 108)
            if headers[-1] == "협상"
            else (130, 65, 110, 110, 110, 360)
        )
        for column, width in enumerate(widths):
            table.setColumnWidth(column, width)
        stretch_column = len(headers) - 1 if headers[-1] == "계약 내역" else len(headers) - 2
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(48)
        return table

    def refresh(self):
        if self.domestic_fa_service is not None:
            market_status = self.domestic_fa_service.market_status()
            self.domestic_status_label.setText(
                "KBO 국내 FA · " + market_status["label"]
            )
            self.domestic_status_label.setProperty(
                "open", market_status["open"]
            )
            self.domestic_status_label.style().unpolish(
                self.domestic_status_label
            )
            self.domestic_status_label.style().polish(
                self.domestic_status_label
            )
        total, pitchers = self.service.slot_state()
        self.slot_label.setText(f"외국인 슬롯  {total}/3  ·  투수 {pitchers}/2")
        self.current_players = self.service.current_players()
        self._populate_current(self.current_players)
        market_players = self.service.market_players()
        self.visible_market_players = market_players
        profile = self.service.scouting_profile()
        discovered = sum(
            player["status"] == "available" for player in market_players
        )
        self.scout_label.setText(
            f"{profile['team']} 국제 스카우트팀 · 현재 발굴 {discovered}명 · "
            f"발굴력 {profile['discovery']}/20 · 평가 정확도 {profile['accuracy']}/20 · "
            f"해외 네트워크 {profile['network']}/20"
        )
        self._populate_market(market_players)
        budget = self.service.budget_summary()
        self.budget_cap[1].setText(f"${budget['cap_usd']:,}")
        self.budget_spent[1].setText(f"${budget['spent_usd']:,}")
        self.budget_available[1].setText(f"${budget['available_usd']:,}")
        cap = max(1, int(budget["cap_usd"]))
        spent_percent = min(100, round(int(budget["spent_usd"]) / cap * 100))
        available_percent = min(100, round(int(budget["available_usd"]) / cap * 100))
        for card, percent, caption in (
            (self.budget_cap, 100, "리그 규정 한도"),
            (self.budget_spent, spent_percent, f"한도의 {spent_percent}% 사용"),
            (self.budget_available, available_percent, f"한도의 {available_percent}% 가용"),
        ):
            card[2].setValue(percent)
            card[3].setText(caption)
        self._populate_league_budgets(self.service.league_budget_rows())
        if self.domestic_fa_service is not None:
            self.domestic_fa_players = self.domestic_fa_service.market_players()
            self._populate_domestic_fa(self.domestic_fa_players)

    def _populate_domestic_fa(self, players):
        service = self.domestic_fa_service
        if service is None:
            self.domestic_fa_table.setRowCount(0)
            return
        self.domestic_fa_table.setRowCount(len(players))
        for row, player in enumerate(players):
            compensation = f"{int(player['compensation']):,}만원"
            if player.get("player_compensation"):
                compensation += " + 보상선수"
            values = (
                player["name"], player["team"], self._position_text(player),
                player.get("age", "-"), player.get("overall", "-"),
                player.get("fa_grade", "-"), f"{int(player.get('salary') or 0):,}만원",
                compensation, player.get("desired_role", "-"),
            )
            for column, value in enumerate(values):
                self._item(self.domestic_fa_table, row, column, value, column in (3, 4, 5))
            ready = service.contract_talk_ready(player["id"])
            market_open = service.market_is_open()
            button = QPushButton(
                "계약 협상" if ready else
                "에이전트 접촉" if market_open else "11/09 개장"
            )
            button.setObjectName("OfferButton")
            button.setEnabled(bool(player.get("available")))
            if not market_open:
                button.setToolTip("KBO 국내 FA 협상은 11월 9일부터 가능합니다.")
            button.clicked.connect(
                lambda _checked=False, p=player: self._open_domestic_fa(p)
            )
            self.domestic_fa_table.setCellWidget(row, 9, button)

    def _open_domestic_fa(self, player):
        service = self.domestic_fa_service
        if service is None:
            return
        if not service.contract_talk_ready(player["id"]):
            consultation = AgentConsultationDialog(
                service, dict(player), self
            )
            consultation.exec()
            self.refresh()
            if not service.contract_talk_ready(player["id"]):
                return
        self.domestic_contract_requested.emit(dict(player))

    def _populate_current(self, players):
        self.current_table.setRowCount(len(players))
        status_names = {
            "undecided": "미결정", "renewed": "재계약 완료", "released": "방출",
        }
        for row, player in enumerate(players):
            values = (
                player["name"],
                self._position_text(player),
                player.get("age", "-"),
                player["overall"],
                f"${int(player.get('current_contract_usd') or 0):,}",
                f"${int(player['asking_salary']):,}",
                player.get("contract_end_date") or "2025-11-30",
                status_names.get(player["contract_decision"], player["contract_decision"]),
            )
            for column, value in enumerate(values):
                self._item(self.current_table, row, column, value, column in (2, 3))
            actions = QWidget()
            layout = QHBoxLayout(actions)
            layout.setContentsMargins(3, 3, 3, 3)
            if player["contract_decision"] == "renewed":
                done = QLabel("계약 완료")
                done.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(done)
            else:
                renew = QPushButton(
                    "계약 협상"
                    if self.service.contract_talk_ready(player["id"])
                    else "에이전트 접촉"
                )
                renew.setObjectName("OfferButton")
                renew.clicked.connect(
                    lambda _checked=False, p=player: self.player_requested.emit(dict(p))
                )
                release = QPushButton("방출")
                release.setObjectName("ReleaseButton")
                release.clicked.connect(
                    lambda _checked=False, p=player: self._release(p)
                )
                renew.setMinimumWidth(78)
                release.setMinimumWidth(48)
                layout.addWidget(renew)
                layout.addWidget(release)
            contract = self.current_table.item(row, 4)
            contract.setToolTip(self._contract_breakdown(player))
            self.current_table.setCellWidget(row, 8, actions)

    def _populate_market(self, players):
        self.market_table.setRowCount(len(players))
        for row, player in enumerate(players):
            values = (
                player["name"], player["nationality"],
                "투수" if player.get("position_group", player["pos"]) == "P" else "야수",
                self._position_text(player), player["age"],
                player.get("overall_display", player["overall"]),
                player.get("scout_confidence", "보통"),
                f"${int(player['asking_salary']):,}",
                f"{player.get('archetype', '외국인 FA')} · {player['summary']}",
            )
            for column, value in enumerate(values):
                self._item(self.market_table, row, column, value, column in (4, 5))
            self.market_table.item(row, 8).setToolTip(values[8])
            if player["status"] == "available":
                button = QPushButton(
                    "계약 협상"
                    if self.service.contract_talk_ready(player["id"])
                    else "에이전트 접촉"
                )
                button.setObjectName("OfferButton")
                button.clicked.connect(
                    lambda _checked=False, p=player: self.player_requested.emit(dict(p))
                )
            else:
                button = QPushButton(f"{player['signed_team']} 계약")
                button.setEnabled(False)
            self.market_table.setCellWidget(row, 9, button)

    def _populate_league_budgets(self, rows):
        self.league_budget_table.setRowCount(len(rows))
        for row, data in enumerate(rows):
            values = (
                data["team"], data["player_count"], f"${data['cap_usd']:,}",
                f"${data['spent_usd']:,}", f"${data['available_usd']:,}", data["contracts"],
            )
            for column, value in enumerate(values):
                self._item(self.league_budget_table, row, column, value, column in (1, 2, 3, 4))
            self.league_budget_table.item(row, 5).setToolTip(data["contracts"])

    def _open_current_row(self, row, _column):
        if 0 <= row < len(getattr(self, "current_players", [])):
            self.player_requested.emit(dict(self.current_players[row]))

    def _open_market_row(self, row, _column):
        if 0 <= row < len(getattr(self, "visible_market_players", [])):
            self.player_requested.emit(dict(self.visible_market_players[row]))

    @staticmethod
    def _position_text(player):
        labels = {
            "SP": "선발투수", "RP": "불펜투수", "P": "투수",
            "C": "포수", "1B": "1루수", "2B": "2루수", "3B": "3루수",
            "SS": "유격수", "LF": "좌익수", "CF": "중견수", "RF": "우익수",
            "IF": "내야수", "OF": "외야수",
        }
        position = player.get("primary_position") or player.get("pos") or player.get("position_group")
        return labels.get(position, position or "-")

    @staticmethod
    def _contract_breakdown(player):
        if player.get("contract_currency") != "USD":
            return "2025 KBO 선수 연봉계약"
        if not int(player.get("contract_salary") or 0):
            return (
                f"발표 계약 총액 ${int(player.get('contract_total') or 0):,}\n"
                "계약금·기본연봉·옵션의 세부 분해 내역은 공개되지 않았습니다."
            )
        return (
            f"총액 ${int(player.get('contract_total') or 0):,}\n"
            f"기본연봉 ${int(player.get('contract_salary') or 0):,} · "
            f"계약금 ${int(player.get('contract_bonus') or 0):,}\n"
            f"옵션 ${int(player.get('contract_option') or 0):,} · "
            f"이적료 ${int(player.get('contract_transfer_fee') or 0):,}"
        )

    @staticmethod
    def _item(table, row, column, value, center=False):
        item = QTableWidgetItem(str(value))
        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if column == 0:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QColor("#f3f6f8"))
        table.setItem(row, column, item)

    def _release(self, player):
        answer = QMessageBox.question(
            self, "외국인 선수 방출",
            f"{player['name']}을 방출할까요?\n방출 후 외국인 FA 시장에서 대체 선수를 영입할 수 있습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = self.service.release(player["id"])
        QMessageBox.information(self, "방출 결과", message)
        if success:
            self.roster_changed.emit()
        self.refresh()

    def _style(self):
        accent = self.colors["accent"]
        return f"""
        QFrame#ForeignHeader {{ background:#111a22; border:1px solid #394b58;
            border-left:4px solid {accent}; border-radius:5px; }}
        QFrame#BudgetCard {{ background:#171f27; border:1px solid #354650;
            border-radius:5px; }}
        QFrame#BudgetCard[kind="cap"] {{ border-top:3px solid #559dca; }}
        QFrame#BudgetCard[kind="spent"] {{ border-top:3px solid #e2aa57; }}
        QFrame#BudgetCard[kind="available"] {{ border-top:3px solid #58c998; }}
        QLabel#BudgetTitle {{ color:#8e9ca7; font-size:13px; }}
        QLabel#BudgetValue {{ color:#edf5f8; font-size:22px; font-weight:850; }}
        QLabel#BudgetCaption {{ color:#778995; font-size:13px; }}
        QProgressBar#BudgetBar {{ min-height:6px; max-height:6px; background:#26323a;
            border:0; border-radius:3px; }}
        QProgressBar#BudgetBar::chunk {{ background:#58c998; border-radius:3px; }}
        QLabel {{ color:#dbe5eb; font-family:'Malgun Gothic'; }}
        QLabel#ForeignEyebrow {{ color:#68b9ea; font-size:13px; font-weight:850; }}
        QLabel#MarketStatus {{ color:#e7b85b; font-size:13px; font-weight:800; }}
        QLabel#MarketStatus[open="true"] {{ color:#78d3a6; }}
        QLabel#ForeignTitle {{ color:white; font-size:21px; font-weight:850; }}
        QLabel#SlotBadge {{ color:#7fe0b3; background:#17372d; border:1px solid #2e7259;
            border-radius:10px; padding:7px 13px; font-weight:800; }}
        QLabel#RuleNote {{ color:#8d9ca8; background:#111820; border:1px solid #303d47;
            padding:8px 11px; }}
        QLabel#ScoutNote {{ color:#83c8ee; background:#102331; border:1px solid #28516a;
            padding:8px 11px; font-weight:700; }}
        QTabWidget::pane {{ background:#10171d; border:1px solid #344550; top:-1px; }}
        QTabBar::tab {{ color:#94a4ae; background:#182129; border:1px solid #344550;
            border-bottom:0; padding:9px 18px; margin-right:2px; font-weight:750; }}
        QTabBar::tab:selected {{ color:white; background:#24323d; border-top:3px solid {accent}; }}
        QTabBar::tab:hover:!selected {{ color:#dce6ed; background:#202c35; }}
        QTableWidget {{ background:#10171d; alternate-background-color:#182129;
            color:#dce5ea; border:0; selection-background-color:#285878;
            selection-color:white; outline:0; }}
        QTableWidget::item {{ padding:5px; border-bottom:1px solid #202c34; }}
        QTableWidget::item:hover {{ background:#21303a; }}
        QHeaderView::section {{ background:#202b34; color:#cbd6dc; border:0;
            border-right:1px solid #35434d; border-bottom:1px solid #43545f;
            padding:9px; font-weight:800; }}
        QPushButton {{ padding:7px 10px; border-radius:3px; font-weight:750; }}
        QPushButton#OfferButton {{ color:white; background:{accent}; border:1px solid {accent}; }}
        QPushButton#OfferButton:hover {{ background:#3b97d0; }}
        QPushButton#ReleaseButton {{ color:#f0c0c0; background:#3b2428; border:1px solid #714047; }}
        QPushButton:disabled {{ color:#78858f; background:#242d34; border:1px solid #35414a; }}
        """
