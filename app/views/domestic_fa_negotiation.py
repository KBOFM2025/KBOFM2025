"""루트 스택에서 여는 국내 FA 전체 화면 계약 협상 페이지."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.views.contract_negotiation import AgentContractNegotiationWidget


class DomesticFAContractPage(QWidget):
    back_requested = Signal()
    contract_completed = Signal()

    def __init__(self, colors=None, parent=None):
        super().__init__(parent)
        self.setObjectName("DomesticFAContractPage")
        self.colors = colors or {}
        self.player = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        top = QFrame(objectName="FullContractTop")
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(12, 7, 16, 7)
        back = QPushButton("‹  이적 및 FA 센터", objectName="ContractBack")
        back.clicked.connect(self.back_requested.emit)
        self.page_title = QLabel("국내 FA 계약 협상", objectName="FullContractTitle")
        top_row.addWidget(back)
        top_row.addWidget(self.page_title)
        top_row.addStretch()
        top_row.addWidget(QLabel("실시간", objectName="LiveBadge"))
        root.addWidget(top)
        self.negotiation = AgentContractNegotiationWidget(self.colors, self)
        self.negotiation.contract_completed.connect(self.contract_completed.emit)
        root.addWidget(self.negotiation, 1)
        self.setStyleSheet("""
            QWidget#DomesticFAContractPage { background:#101214; }
            QFrame#FullContractTop { background:#181a1d; border-bottom:1px solid #30353a; }
            QPushButton#ContractBack { color:#dce3e8; background:transparent; border:0; padding:8px 11px; font-weight:800; }
            QPushButton#ContractBack:hover { color:#e8f300; }
            QLabel#FullContractTitle { color:white; font-size:15px; font-weight:900; }
            QLabel#LiveBadge { color:white; background:#d64242; border-radius:8px; padding:4px 8px; font-size:13px; font-weight:900; }
        """)

    def set_context(self, service, player):
        self.player = dict(player or {})
        self.page_title.setText(f"{self.player.get('name', '-')} · 국내 FA 계약 협상")
        self.negotiation.set_context(service, self.player)
