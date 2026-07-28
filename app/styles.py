"""애플리케이션 공통 타이포그래피와 Qt 스타일시트."""

UI_FONT_FAMILY = "Malgun Gothic"
NUMERIC_FONT_FAMILY = "Malgun Gothic"

GLOBAL_STYLE = """
    QWidget {
        font-family: 'Malgun Gothic', 'Segoe UI';
        font-size: 13px;
    }
    QToolTip {
        color: #eef2f6;
        background-color: #171d24;
        border: 1px solid #4a5561;
        border-radius: 1px;
        padding: 5px 8px;
        font-size: 12px;
    }
    QTableWidget, QTableView {
        font-size: 12px;
        selection-color: white;
        outline: none;
    }
    QTableWidget::item, QTableView::item { padding: 4px 7px; }
    QHeaderView::section {
        min-height: 27px;
        padding: 4px 7px;
        font-size: 12px;
        font-weight: 600;
    }
    QComboBox {
        min-height: 30px;
        padding: 0 9px;
        font-size: 12px;
        border-radius: 1px;
    }
    QPushButton {
        min-height: 31px;
        padding: 0 12px;
        color: #d7dde4;
        background-color: #1a2129;
        border: 1px solid #38424d;
        border-radius: 1px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover { background-color: #242d36; border-color: #647180; }
    QPushButton:pressed { background-color: #11171d; }
    QPushButton:disabled { color: #65717d; background-color: #171c22; border-color: #2b333c; }
    QLineEdit, QTextEdit, QPlainTextEdit {
        color: #e6ebf0;
        background-color: #11171d;
        border: 1px solid #3a444f;
        border-radius: 1px;
        selection-color: white;
        selection-background-color: #4b5968;
    }
    QMessageBox QLabel { min-width: 280px; font-size: 13px; }
    QMessageBox QPushButton { min-width: 86px; min-height: 31px; font-size: 12px; }
    QScrollBar:vertical {
        width: 8px;
        background: #11161c;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        min-height: 28px;
        background: #46515d;
        border-radius: 0;
    }
    QScrollBar::handle:vertical:hover { background: #65717e; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

START_STYLE = """
    QWidget#StartRoot, QDialog { background-color: #07111f; }
    QFrame#StartCard {
        background-color: #0d1b2a;
        border: 1px solid #24364b;
        border-radius: 18px;
    }
    QLabel { color: #f8fafc; font-family: 'Malgun Gothic', 'Segoe UI'; }
    QLabel#Subtitle { color: #9bafc3; font-size: 17px; }
    QLabel#FieldLabel { color: #d6e0ea; font-size: 15px; font-weight: 600; }
    QLineEdit, QSpinBox {
        min-height: 46px;
        padding: 0 14px;
        color: #f8fafc;
        background-color: #101f31;
        border: 1px solid #30445c;
        border-radius: 8px;
        font-family: 'Malgun Gothic', 'Segoe UI';
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
        font-family: 'Malgun Gothic', 'Segoe UI';
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
