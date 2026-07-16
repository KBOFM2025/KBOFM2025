"""애플리케이션 공통 Qt 스타일시트."""

START_STYLE = """
    QWidget#StartRoot, QDialog { background-color: #07111f; }
    QFrame#StartCard {
        background-color: #0d1b2a;
        border: 1px solid #24364b;
        border-radius: 18px;
    }
    QLabel { color: #f8fafc; font-family: 'Malgun Gothic'; }
    QLabel#Subtitle { color: #8fa3b8; font-size: 15px; }
    QLabel#FieldLabel { color: #cbd5e1; font-size: 13px; font-weight: bold; }
    QLineEdit, QSpinBox {
        min-height: 46px;
        padding: 0 14px;
        color: #f8fafc;
        background-color: #101f31;
        border: 1px solid #30445c;
        border-radius: 8px;
        font-family: 'Malgun Gothic';
        font-size: 14px;
    }
    QLineEdit:focus, QSpinBox:focus { border: 1px solid #42a5f5; }
    QPushButton {
        min-height: 50px;
        padding: 0 20px;
        color: #e5edf5;
        background-color: #14263a;
        border: 1px solid #30445c;
        border-radius: 9px;
        font-family: 'Malgun Gothic';
        font-size: 15px;
        font-weight: bold;
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
