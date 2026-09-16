"""In-game event QA console, visible only in a debug save."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


class DebugConsolePage(QWidget):
    event_requested = Signal(int)
    practice_game_requested = Signal()

    def __init__(self, colors, service, current_date, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.service = service
        self.current_date = current_date
        self._catalog = service.catalog()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(10)

        header = QFrame(objectName="DebugHeader")
        header_row = QHBoxLayout(header)
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("DEBUG MODE · EVENT QA", objectName="DebugEyebrow"))
        title_box.addWidget(QLabel("이벤트 디버그 콘솔", objectName="DebugTitle"))
        title_box.addWidget(QLabel(
            "날짜 진행 없이 실제 이벤트 생성·대화·선택·결과 반영 경로를 검사합니다. 변경은 이 디버그 세이브에만 저장됩니다.",
            objectName="DebugMuted",
        ))
        header_row.addLayout(title_box)
        header_row.addStretch()
        practice_button = QPushButton("새 연습경기 테스트", objectName="DebugPrimary")
        practice_button.setToolTip(
            "기존 테스트 결과와 중계 상태를 초기화하고 새 연습경기를 시작합니다."
        )
        practice_button.clicked.connect(self.practice_game_requested.emit)
        header_row.addWidget(practice_button)
        self.status_label = QLabel(objectName="DebugStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.status_label)
        root.addWidget(header)

        content = QHBoxLayout()
        catalog_card = QFrame(objectName="DebugCard")
        catalog_box = QVBoxLayout(catalog_card)
        catalog_box.addWidget(QLabel("테스트할 기능", objectName="DebugCardTitle"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("이벤트명·분류 검색")
        self.search.textChanged.connect(self._fill_catalog)
        catalog_box.addWidget(self.search)
        self.catalog_list = QListWidget()
        self.catalog_list.itemSelectionChanged.connect(self._show_catalog_detail)
        self.catalog_list.itemDoubleClicked.connect(self._create_selected)
        catalog_box.addWidget(self.catalog_list, 1)
        self.catalog_detail = QLabel(objectName="DebugDetail")
        self.catalog_detail.setWordWrap(True)
        self.catalog_detail.setMinimumHeight(70)
        catalog_box.addWidget(self.catalog_detail)
        create_button = QPushButton("이벤트 생성 후 즉시 열기", objectName="DebugPrimary")
        create_button.clicked.connect(self._create_selected)
        catalog_box.addWidget(create_button)
        content.addWidget(catalog_card, 2)

        history_card = QFrame(objectName="DebugCard")
        history_box = QVBoxLayout(history_card)
        history_header = QHBoxLayout()
        history_header.addWidget(QLabel("디버그 실행 기록", objectName="DebugCardTitle"))
        history_header.addStretch()
        clear_button = QPushButton("기록 비우기", objectName="DebugSecondary")
        clear_button.clicked.connect(self._clear_records)
        history_header.addWidget(clear_button)
        history_box.addLayout(history_header)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ("ID", "날짜", "분류", "이벤트", "상태")
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.doubleClicked.connect(lambda _index: self._open_history())
        history_box.addWidget(self.history_table, 1)
        open_button = QPushButton("선택한 이벤트 다시 열기", objectName="DebugSecondary")
        open_button.clicked.connect(self._open_history)
        history_box.addWidget(open_button)
        warning = QLabel(
            "기록 비우기는 디버그 이벤트 목록만 삭제합니다. 이미 선택한 계약·이적·선수 상태 변화는 전용 디버그 선수 DB에 남습니다.",
            objectName="DebugWarning",
        )
        warning.setWordWrap(True)
        history_box.addWidget(warning)
        content.addWidget(history_card, 3)
        root.addLayout(content, 1)
        self.setStyleSheet(self._style())

    def set_game_date(self, current_date):
        self.current_date = current_date
        self.refresh()

    def refresh(self):
        self._fill_catalog()
        rows = self.service.recent_events()
        self.history_table.setRowCount(len(rows))
        for row_index, event in enumerate(rows):
            values = (
                event["id"], event["event_date"], event["category"],
                event["headline"], "미처리" if event["status"] == "open" else "처리 완료",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(event["id"]))
                self.history_table.setItem(row_index, column, item)
        self.status_label.setText(
            f"QA 세이브 #{self.service.save_id}\n현재 날짜 {self.current_date} · 실행 {len(rows)}건"
        )

    def _fill_catalog(self, *_args):
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""
        selected_key = self._selected_catalog_key() if hasattr(self, "catalog_list") else None
        self.catalog_list.clear()
        last_group = None
        selected_item = None
        for event in self._catalog:
            haystack = " ".join((event["group"], event["title"], event["description"])).lower()
            if query and query not in haystack:
                continue
            if event["group"] != last_group:
                group_item = QListWidgetItem(f"── {event['group']} ──")
                group_item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.catalog_list.addItem(group_item)
                last_group = event["group"]
            item = QListWidgetItem(f"{event['title']}   ·   {event['source_date']}")
            item.setData(Qt.ItemDataRole.UserRole, event)
            self.catalog_list.addItem(item)
            if event["key"] == selected_key:
                selected_item = item
        if selected_item:
            self.catalog_list.setCurrentItem(selected_item)

    def _selected_catalog_key(self):
        item = self.catalog_list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data.get("key") if isinstance(data, dict) else None

    def _show_catalog_detail(self):
        item = self.catalog_list.currentItem()
        event = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(event, dict):
            self.catalog_detail.setText("이벤트를 선택하세요.")
            return
        self.catalog_detail.setText(
            f"{event['group']} · 원래 기준 {event['source_date']}\n{event['description']}"
        )

    def _create_selected(self, *_signal_args):
        key = self._selected_catalog_key()
        if not key:
            QMessageBox.information(self, "이벤트 디버그", "테스트할 이벤트를 선택하세요.")
            return
        try:
            event_id = self.service.create_event(key, str(self.current_date))
        except Exception as error:
            QMessageBox.warning(self, "이벤트 생성 실패", str(error))
            return
        self.refresh()
        self.event_requested.emit(event_id)

    def _selected_history_id(self):
        row = self.history_table.currentRow()
        item = self.history_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _open_history(self):
        event_id = self._selected_history_id()
        if event_id is None:
            QMessageBox.information(self, "이벤트 디버그", "실행 기록을 선택하세요.")
            return
        self.event_requested.emit(event_id)

    def _clear_records(self):
        answer = QMessageBox.question(
            self,
            "디버그 기록 비우기",
            "디버그 이벤트 기록을 모두 삭제할까요?\n이미 적용된 선수단 변화는 되돌리지 않습니다.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        count = self.service.clear_event_records()
        self.refresh()
        QMessageBox.information(self, "디버그 기록", f"디버그 이벤트 {count}건을 삭제했습니다.")

    def _style(self):
        accent = self.colors.get("accent", "#2c8ed6")
        light = self.colors.get("accent_light", "#68c7f0")
        return f"""
            QWidget {{ color:#e8eef3; font-family:'Malgun Gothic','Segoe UI'; }}
            QFrame#DebugHeader {{ background:#14191e; border:1px solid #3c4852; border-radius:8px; }}
            QLabel#DebugEyebrow {{ color:#ffb74d; font-size:13px; font-weight:900; }}
            QLabel#DebugTitle {{ color:white; font-size:22px; font-weight:900; }}
            QLabel#DebugMuted {{ color:#93a1ac; font-size:13px; }}
            QLabel#DebugStatus {{ color:#ffd180; font-weight:800; }}
            QFrame#DebugCard {{ background:#10171d; border:1px solid #34434e; border-radius:8px; }}
            QLabel#DebugCardTitle {{ color:white; font-size:15px; font-weight:900; }}
            QLabel#DebugDetail {{ color:#d5e1e8; background:#0b1116; border-left:3px solid {accent}; padding:9px; }}
            QLabel#DebugWarning {{ color:#d4a76a; font-size:13px; }}
            QLineEdit,QListWidget,QTableWidget {{ background:#0b1116; border:1px solid #34434e; color:#dbe5eb; selection-background-color:{accent}; }}
            QLineEdit {{ min-height:30px; padding:2px 8px; border-radius:5px; }}
            QListWidget::item {{ min-height:29px; padding:2px 7px; }}
            QHeaderView::section {{ background:#1a242c; color:#aebbc4; border:none; padding:7px; font-weight:800; }}
            QPushButton#DebugPrimary {{ color:white; background:{accent}; border:1px solid {light}; border-radius:6px; min-height:35px; font-weight:900; }}
            QPushButton#DebugSecondary {{ color:#dbe5eb; background:#222e37; border:1px solid #4a5c69; border-radius:6px; min-height:31px; padding:2px 10px; font-weight:800; }}
        """
