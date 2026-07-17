"""애플리케이션 공통 타이포그래피와 Qt 스타일시트."""

UI_FONT_FAMILY = "Noto Sans KR"
NUMERIC_FONT_FAMILY = "Segoe UI Variable"

GLOBAL_STYLE = """
    QWidget {
        font-family: 'Noto Sans KR', 'Malgun Gothic';
        font-size: 14px;
    }
    QToolTip {
        color: #f8fafc;
        background-color: #14263a;
        border: 1px solid #40556d;
        border-radius: 5px;
        padding: 7px 10px;
        font-size: 13px;
    }
    QTableWidget, QTableView {
        font-size: 14px;
        selection-color: white;
        outline: none;
    }
    QTableWidget::item, QTableView::item { padding: 7px 9px; }
    QHeaderView::section {
        min-height: 32px;
        padding: 7px 9px;
        font-size: 13px;
        font-weight: 600;
    }
    QComboBox {
        min-height: 38px;
        padding: 0 12px;
        font-size: 14px;
        border-radius: 6px;
    }
    QPushButton {
        min-height: 38px;
        padding: 0 16px;
        color: #dce7f1;
        background-color: #18283a;
        border: 1px solid #35495f;
        border-radius: 7px;
        font-size: 14px;
        font-weight: 600;
    }
    QPushButton:hover { background-color: #21374e; border-color: #5a7795; }
    QPushButton:pressed { background-color: #112133; }
    QPushButton:disabled { color: #65778a; background-color: #17212d; border-color: #293746; }
    QMessageBox QLabel { min-width: 280px; font-size: 14px; }
    QMessageBox QPushButton { min-width: 92px; min-height: 36px; font-size: 14px; }
    QScrollBar:vertical {
        width: 11px;
        background: transparent;
        margin: 3px;
    }
    QScrollBar::handle:vertical {
        min-height: 34px;
        background: #405165;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover { background: #58708a; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

START_STYLE = """
    QWidget#StartRoot, QDialog { background-color: #07111f; }
    QFrame#StartCard {
        background-color: #0d1b2a;
        border: 1px solid #24364b;
        border-radius: 18px;
    }
    QLabel { color: #f8fafc; font-family: 'Noto Sans KR', 'Malgun Gothic'; }
    QLabel#Subtitle { color: #9bafc3; font-size: 17px; }
    QLabel#FieldLabel { color: #d6e0ea; font-size: 15px; font-weight: 600; }
    QLineEdit, QSpinBox {
        min-height: 46px;
        padding: 0 14px;
        color: #f8fafc;
        background-color: #101f31;
        border: 1px solid #30445c;
        border-radius: 8px;
        font-family: 'Noto Sans KR', 'Malgun Gothic';
        font-size: 16px;
    }
    QLineEdit:focus, QSpinBox:focus { border: 1px solid #42a5f5; }
    QPushButton {
        min-height: 50px;
        padding: 0 20px;
        color: #e5edf5;
        background-color: #14263a;
        border: 1px solid #30445c;
        border-radius: 9px;
        font-family: 'Noto Sans KR', 'Malgun Gothic';
        font-size: 16px;
        font-weight: 700;
    }
    QPushButton:hover { background-color: #1b324b; border-color: #42a5f5; }
    QPushButton#PrimaryButton {
        color: white;
        background-color: #1976d2;
        border-color: #42a5f5;
    }
    QPushButton#PrimaryButton:hover { background-color: #2388e8; }
    QPushButton#BackButton { min-height: 42px; color: #aebfd0; }
    QPushButton#StartPointButton {
        min-height: 92px;
        text-align: left;
        padding: 14px 20px;
    }
    QPushButton#StartPointButton:checked {
        color: white;
        background-color: #1976d2;
        border: 2px solid #60a5fa;
    }
    QWidget#AbilityControl {
        background-color: #101f31;
        border: 1px solid #263b52;
        border-radius: 9px;
    }
    QSlider::groove:horizontal {
        height: 7px;
        background-color: #263b52;
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal {
        background-color: #42a5f5;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        width: 18px;
        margin: -6px 0;
        background-color: #e8f4ff;
        border: 3px solid #1976d2;
        border-radius: 9px;
    }
    QSlider::handle:horizontal:hover { background-color: white; border-color: #42a5f5; }
"""
