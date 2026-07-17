"""저장된 구단 선택 및 삭제 대화상자."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.constants import APP_TITLE
from app.config import DEFAULT_START_POINT, start_point_title
from app.styles import START_STYLE


class LoadGameDialog(QDialog):
    def __init__(self, saves, save_database, parent=None):
        super().__init__(parent)
        self.selected_save_id = None
        self.save_database = save_database
        self.setWindowTitle(f"{APP_TITLE} - 불러오기")
        self.setMinimumSize(620, 480)
        self.setStyleSheet(START_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 36, 42, 36)
        layout.setSpacing(14)

        title = QLabel("저장된 구단")
        title.setFont(QFont("Noto Sans KR", 28, QFont.Bold))
        layout.addWidget(title)

        subtitle = QLabel("계속 운영할 구단을 선택하세요.")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self.save_list = QListWidget()
        self.save_list.setStyleSheet("""
            QListWidget {
                color: #e5edf5;
                background-color: #101f31;
                border: 1px solid #30445c;
                border-radius: 9px;
                padding: 8px;
                font-family: 'Noto Sans KR', 'Malgun Gothic';
                font-size: 16px;
            }
            QListWidget::item { padding: 14px 12px; border-radius: 6px; }
            QListWidget::item:selected { background-color: #1976d2; color: white; }
            QListWidget::item:hover { background-color: #1b324b; }
        """)
        for save in saves:
            updated = save["updated_at"].replace("T", " ")
            record = (
                f'{save["club_name"]}  ·  {save["base_team"]}  ·  {save["season"]} 시즌\n'
                f'{save.get("manager_name", "무명 감독")} 감독  ·  '
                f'{start_point_title(save.get("start_point", DEFAULT_START_POINT))}\n'
                f'최근 저장 {updated}'
            )
            item = QListWidgetItem(record)
            item.setData(Qt.UserRole, save["id"])
            self.save_list.addItem(item)
        self.save_list.itemDoubleClicked.connect(lambda _item: self.load_selected())
        if self.save_list.count():
            self.save_list.setCurrentRow(0)
        layout.addWidget(self.save_list)

        buttons = QHBoxLayout()
        cancel_button = QPushButton("돌아가기")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        self.delete_button = QPushButton("저장 삭제")
        self.delete_button.setStyleSheet(
            "QPushButton { color: #ff8a8a; border-color: #71383d; }"
            "QPushButton:hover { background-color: #54242a; border-color: #ef5350; }"
        )
        self.delete_button.clicked.connect(self.delete_selected)
        buttons.addWidget(self.delete_button)

        self.load_button = QPushButton("선택한 구단 불러오기")
        self.load_button.setObjectName("PrimaryButton")
        self.load_button.clicked.connect(self.load_selected)
        buttons.addWidget(self.load_button, 2)
        layout.addLayout(buttons)

    def load_selected(self):
        item = self.save_list.currentItem()
        if item is None:
            return
        self.selected_save_id = item.data(Qt.UserRole)
        self.accept()

    def delete_selected(self):
        item = self.save_list.currentItem()
        if item is None:
            return

        save_id = item.data(Qt.UserRole)
        save = self.save_database.get_save(save_id)
        if save is None:
            QMessageBox.warning(self, "삭제 실패", "저장 정보를 찾을 수 없습니다.")
            return

        answer = QMessageBox.question(
            self,
            "저장 삭제",
            f'"{save["club_name"]}" 저장을 삭제하시겠습니까?\n삭제한 저장은 복구할 수 없습니다.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if not self.save_database.delete_save(save_id):
            QMessageBox.warning(self, "삭제 실패", "저장 정보를 삭제하지 못했습니다.")
            return

        row = self.save_list.row(item)
        self.save_list.takeItem(row)
        if self.save_list.count():
            self.save_list.setCurrentRow(min(row, self.save_list.count() - 1))
        else:
            self.load_button.setEnabled(False)
            self.delete_button.setEnabled(False)
