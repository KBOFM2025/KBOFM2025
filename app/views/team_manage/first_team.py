from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, \
    QHeaderView, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# 💡 프로필 다이얼로그 임포트
from .player_profile import PlayerProfileDialog


class FirstTeamTab(QWidget):
    def __init__(self, parent_manager):
        super().__init__()
        self.manager = parent_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        info_layout = QHBoxLayout()
        info_label = QLabel("📢 1군 엔트리 (선수를 더블클릭하면 FM 세부 보고서가 열립니다.)")
        info_label.setStyleSheet("color: #af9154; font-size: 14px; font-weight: bold;")
        info_layout.addWidget(info_label)

        self.btn_demote = QPushButton("🔻 선택 선수 C팀(2군) 강등")
        self.btn_demote.setStyleSheet("background-color: #991b1b; color: #fca5a5; border: none; padding: 8px 15px;")
        self.btn_demote.clicked.connect(self.demote_player)
        info_layout.addWidget(self.btn_demote)
        layout.addLayout(info_layout)

        # [1] 투수진 테이블 구역
        pitcher_title = QLabel("🔮 1군 투수진 (마운드)")
        pitcher_title.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        layout.addWidget(pitcher_title)

        self.table_pitchers = QTableWidget()
        self.table_pitchers.setColumnCount(8)
        self.table_pitchers.setHorizontalHeaderLabels(["이름", "포지션", "나이", "구속", "제구", "변화구", "스태미나", "보직"])
        self.table_pitchers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_pitchers.setSelectionBehavior(QTableWidget.SelectRows)
        # 💡 더블클릭 이벤트 연결
        self.table_pitchers.cellDoubleClicked.connect(lambda row, col: self.open_profile(self.table_pitchers, row))
        layout.addWidget(self.table_pitchers)

        # [2] 야수진 테이블 구역
        batter_title = QLabel("⚾ 1군 야수진 (타석/수비)")
        batter_title.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        layout.addWidget(batter_title)

        self.table_batters = QTableWidget()
        self.table_batters.setColumnCount(8)
        self.table_batters.setHorizontalHeaderLabels(["이름", "포지션", "나이", "컨택", "파워", "선구안", "수비력", "타순"])
        self.table_batters.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_batters.setSelectionBehavior(QTableWidget.SelectRows)
        # 💡 더블클릭 이벤트 연결
        self.table_batters.cellDoubleClicked.connect(lambda row, col: self.open_profile(self.table_batters, row))
        layout.addWidget(self.table_batters)

    # 💡 [팝업 오픈 로직] 더블클릭한 대상 선수 오브젝트를 매칭해 모달창 로드
    def open_profile(self, table, row):
        player_name = table.item(row, 0).text()
        player_data = next((p for p in self.manager.players if p["name"] == player_name), None)

        if player_data:
            dialog = PlayerProfileDialog(player_data, self)
            dialog.exec()

    def refresh(self):
        first_team = [p for p in self.manager.players if p["status"] == 1]
        pitchers = [p for p in first_team if p["pos"] == "P"]
        batters = [p for p in first_team if p["pos"] != "P"]

        self.table_pitchers.setRowCount(len(pitchers))
        for row, p in enumerate(pitchers):
            self.table_pitchers.setItem(row, 0, QTableWidgetItem(p["name"]))
            self.table_pitchers.setItem(row, 1, QTableWidgetItem(p["pos"]))
            self.table_pitchers.setItem(row, 2, QTableWidgetItem(str(p["age"])))
            self.set_stat_item(self.table_pitchers, row, 3, p["con"])
            self.set_stat_item(self.table_pitchers, row, 4, p["pow"])
            self.set_stat_item(self.table_pitchers, row, 5, p["eye"])
            self.set_stat_item(self.table_pitchers, row, 6, p["def"])

            role_item = QTableWidgetItem(p.get("role", "투수"))
            role_item.setForeground(Qt.GlobalColor.cyan)
            self.table_pitchers.setItem(row, 7, role_item)

        self.table_batters.setRowCount(len(batters))
        for row, p in enumerate(batters):
            self.table_batters.setItem(row, 0, QTableWidgetItem(p["name"]))
            self.table_batters.setItem(row, 1, QTableWidgetItem(p["pos"]))
            self.table_batters.setItem(row, 2, QTableWidgetItem(str(p["age"])))
            self.set_stat_item(self.table_batters, row, 3, p["con"])
            self.set_stat_item(self.table_batters, row, 4, p["pow"])
            self.set_stat_item(self.table_batters, row, 5, p["eye"])
            self.set_stat_item(self.table_batters, row, 6, p["def"])

            order_text = f"선발 {p['lineup_pos']}번" if p["lineup_pos"] > 0 else "벤치 대기"
            order_item = QTableWidgetItem(order_text)
            if p["lineup_pos"] > 0:
                order_item.setForeground(Qt.GlobalColor.green)
            self.table_batters.setItem(row, 7, order_item)

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

    def demote_player(self):
        p_rows = self.table_pitchers.selectionModel().selectedRows()
        b_rows = self.table_batters.selectionModel().selectedRows()
        
        if not p_rows and not b_rows:
            QMessageBox.warning(self, "알림", "2군으로 보낼 선수를 선택해 주세요.")
            return
            
        row = p_rows[0].row() if p_rows else b_rows[0].row()
        table = self.table_pitchers if p_rows else self.table_batters
        player_name = table.item(row, 0).text()
        
        # 💡 기존 배열 수정 방식에서 DB 저장 방식으로 세련되게 수정!
        self.manager.update_player_status_in_db(player_name, status=0, lineup_pos=0)
        QMessageBox.information(self, "완료", f"{player_name} 선수를 C팀으로 강등했습니다 (DB 저장 완료).")
                
        self.manager.refresh_all()
