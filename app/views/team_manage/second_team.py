from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, \
    QHeaderView, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class SecondTeamTab(QWidget):
    def __init__(self, parent_manager):
        super().__init__()
        self.manager = parent_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        info_layout = QHBoxLayout()
        info_label = QLabel("🌱 C팀(2군) 육성 명단 (부상 복귀 및 유망주 육성)")
        info_label.setStyleSheet("color: #af9154; font-size: 14px; font-weight: bold;")
        info_layout.addWidget(info_label)

        self.btn_promote = QPushButton("🔺 선택 선수 1군 콜업")
        self.btn_promote.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; border: none; padding: 8px 15px;")
        self.btn_promote.clicked.connect(self.promote_player)
        info_layout.addWidget(self.btn_promote)
        layout.addLayout(info_layout)

        # [1] C팀 투수진
        pitcher_title = QLabel("🔮 C팀 투수진 (육성/재활)")
        pitcher_title.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        layout.addWidget(pitcher_title)

        self.table_pitchers = QTableWidget()
        self.table_pitchers.setColumnCount(7)
        self.table_pitchers.setHorizontalHeaderLabels(["이름", "포지션", "나이", "구속", "제구", "변화구", "스태미나"])
        self.table_pitchers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_pitchers.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_pitchers.cellClicked.connect(
            lambda row, col: self.open_profile(self.table_pitchers, row) if col == 0 else None
        )
        layout.addWidget(self.table_pitchers)

        # [2] C팀 야수진
        batter_title = QLabel("⚾ C팀 야수진 (타격/수비 훈련)")
        batter_title.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        layout.addWidget(batter_title)

        self.table_batters = QTableWidget()
        self.table_batters.setColumnCount(7)
        self.table_batters.setHorizontalHeaderLabels(["이름", "포지션", "나이", "컨택", "파워", "선구안", "수비력"])
        self.table_batters.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_batters.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_batters.cellClicked.connect(
            lambda row, col: self.open_profile(self.table_batters, row) if col == 0 else None
        )
        layout.addWidget(self.table_batters)

    def open_profile(self, table, row):
        player_id = table.item(row, 0).data(Qt.UserRole)
        player = next((item for item in self.manager.players if item["id"] == player_id), None)
        if player:
            self.manager.show_player_profile(player)

    def refresh(self):
        second_team = [p for p in self.manager.players if p["status"] == 0]
        pitchers = [p for p in second_team if p["pos"] == "P"]
        batters = [p for p in second_team if p["pos"] != "P"]

        # 투수 채우기
        self.table_pitchers.setRowCount(len(pitchers))
        for row, p in enumerate(pitchers):
            name_item = QTableWidgetItem(p["name"])
            name_item.setData(Qt.UserRole, p["id"])
            self.table_pitchers.setItem(row, 0, name_item)
            self.table_pitchers.setItem(row, 1, QTableWidgetItem(p["pos"]))
            self.table_pitchers.setItem(row, 2, QTableWidgetItem(str(p["age"])))
            self.set_stat_item(self.table_pitchers, row, 3, p["con"])
            self.set_stat_item(self.table_pitchers, row, 4, p["pow"])
            self.set_stat_item(self.table_pitchers, row, 5, p["eye"])
            self.set_stat_item(self.table_pitchers, row, 6, p["def"])

        # 야수 채우기
        self.table_batters.setRowCount(len(batters))
        for row, p in enumerate(batters):
            name_item = QTableWidgetItem(p["name"])
            name_item.setData(Qt.UserRole, p["id"])
            self.table_batters.setItem(row, 0, name_item)
            self.table_batters.setItem(row, 1, QTableWidgetItem(p["pos"]))
            self.table_batters.setItem(row, 2, QTableWidgetItem(str(p["age"])))
            self.set_stat_item(self.table_batters, row, 3, p["con"])
            self.set_stat_item(self.table_batters, row, 4, p["pow"])
            self.set_stat_item(self.table_batters, row, 5, p["eye"])
            self.set_stat_item(self.table_batters, row, 6, p["def"])

    def set_stat_item(self, table, row, col, score):
        item = QTableWidgetItem(str(score))
        item.setTextAlignment(Qt.AlignCenter)
        font = QFont("Malgun Gothic")
        font.setBold(True)
        item.setFont(font)

        if score >= 80:
            item.setForeground(Qt.GlobalColor.green)
        elif score >= 60:
            item.setForeground(Qt.GlobalColor.yellow)
        else:
            item.setForeground(Qt.GlobalColor.red)
        table.setItem(row, col, item)

    def promote_player(self):
        p_rows = self.table_pitchers.selectionModel().selectedRows()
        b_rows = self.table_batters.selectionModel().selectedRows()
        
        if not p_rows and not b_rows:
            QMessageBox.warning(self, "알림", "1군으로 콜업할 선수를 선택해 주세요.")
            return
            
        row = p_rows[0].row() if p_rows else b_rows[0].row()
        table = self.table_pitchers if p_rows else self.table_batters
        player_item = table.item(row, 0)
        player_name = player_item.text()
        player_id = player_item.data(Qt.UserRole)
        
        # 💡 DB에 1군 승격 상태 업데이트
        self.manager.update_player_status_in_db(player_id, status=1, lineup_pos=0)
        QMessageBox.information(self, "완료", f"{player_name} 선수가 1군 엔트리에 합류했습니다 (DB 저장 완료).")
                
        self.manager.refresh_all()
