from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, \
    QHeaderView, QComboBox, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class SetLineupTab(QWidget):
    def __init__(self, parent_manager):
        super().__init__()
        self.manager = parent_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        info_layout = QHBoxLayout()
        info_label = QLabel("1군 타자들의 선발 타순과 수비 포지션을 매칭하세요.")
        info_label.setStyleSheet("color: #9ca3af; font-size: 13px;")
        info_layout.addWidget(info_label)

        btn_save_lineup = QPushButton("💾 전술 및 타순 최종 저장")
        btn_save_lineup.setStyleSheet("background-color: #22c55e; color: #030712;")
        btn_save_lineup.clicked.connect(self.save_lineup)
        info_layout.addWidget(btn_save_lineup)
        layout.addLayout(info_layout)

        self.table_lineup = QTableWidget()
        self.table_lineup.setColumnCount(5)
        self.table_lineup.setHorizontalHeaderLabels(["타순", "선수 선택", "수비 포지션", "컨택", "파워"])
        self.table_lineup.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_lineup)

    def refresh(self):
        self.table_lineup.setRowCount(9)
        first_team_batters = [p for p in self.manager.players if p["status"] == 1 and p["pos"] != "P"]

        for idx in range(9):
            order = idx + 1
            order_item = QTableWidgetItem(f"{order}번 타자")
            order_item.setTextAlignment(Qt.AlignCenter)
            order_item.setFont(QFont("Malgun Gothic", 9, QFont.Bold))
            self.table_lineup.setItem(idx, 0, order_item)

            combo = QComboBox()
            combo.addItem("- 선택 없음 -", None)

            current_selected_idx = -1
            for c_idx, p in enumerate(first_team_batters):
                combo.addItem(f"{p['name']} ({p['pos']})", p["name"])
                if p["lineup_pos"] == order:
                    current_selected_idx = c_idx + 1

            combo.setCurrentIndex(current_selected_idx if current_selected_idx != -1 else 0)
            combo.currentIndexChanged.connect(lambda _, row=idx, cb=combo: self.update_lineup_stats(row, cb))
            self.table_lineup.setCellWidget(idx, 1, combo)

            pos_combo = QComboBox()
            positions = ["DH", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
            pos_combo.addItems(positions)

            selected_player_name = combo.currentData()
            if selected_player_name:
                p_data = next((p for p in self.manager.players if p["name"] == selected_player_name), None)
                if p_data and p_data["pos"] in positions:
                    pos_combo.setCurrentText(p_data["pos"])

            self.table_lineup.setCellWidget(idx, 2, pos_combo)
            self.table_lineup.setItem(idx, 3, QTableWidgetItem("-"))
            self.table_lineup.setItem(idx, 4, QTableWidgetItem("-"))

            self.update_lineup_stats(idx, combo)

    def update_lineup_stats(self, row, combo):
        player_name = combo.currentData()
        if player_name:
            player = next((p for p in self.manager.players if p["name"] == player_name), None)
            if player:
                self.set_stat_item(row, 3, player["con"])
                self.set_stat_item(row, 4, player["pow"])
                return
        self.table_lineup.setItem(row, 3, QTableWidgetItem("-"))
        self.table_lineup.setItem(row, 4, QTableWidgetItem("-"))

    def set_stat_item(self, row, col, score):
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
        self.table_lineup.setItem(row, col, item)

    def save_lineup(self):
        for p in self.manager.players:
            if p["status"] == 1:
                p["lineup_pos"] = 0

        selected_names = set()
        for idx in range(9):
            combo = self.table_lineup.cellWidget(idx, 1)
            player_name = combo.currentData()

            if player_name:
                if player_name in selected_names:
                    QMessageBox.critical(self, "오류", f"중복 배치된 선수가 있습니다: {player_name}\n타순을 다시 조정해 주세요.")
                    return
                selected_names.add(player_name)

                for p in self.manager.players:
                    if p["name"] == player_name:
                        p["lineup_pos"] = idx + 1

        QMessageBox.information(self, "성공", "라인업과 수비 배치가 구단 클럽하우스에 반영되었습니다!")
        self.manager.refresh_all()