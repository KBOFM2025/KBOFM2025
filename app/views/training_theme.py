"""Scoped visual system for the training workspace (logical pixel sizes)."""

TRAINING_STYLE = """
QWidget#TrainingCenter { background:#101820; }
QWidget#TrainingCenter QLabel { font-size:14px; color:#d5dfe7; }
QWidget#TrainingCenter QFrame#TrainingHeader { background:transparent; border:0; }
QWidget#TrainingCenter QLabel#TrainingTitle { font-size:30px; font-weight:700; color:#f3f5f7; }
QWidget#TrainingCenter QLabel#TrainingEyebrow { color:#80cbb6; font-size:12px; font-weight:700; }
QWidget#TrainingCenter QLabel#TrainingSummary { color:#b6c7d3; font-size:14px; font-weight:500; }
QWidget#TrainingCenter QLabel#TrainingMuted { color:#9babba; font-size:13px; }
QFrame#TrainingNavigation { background:#18232e; border:1px solid #293745; border-radius:10px; }
QPushButton#TrainingNavButton { background:transparent; color:#9aabb9; border:0; border-radius:6px; padding:9px 6px; font-size:14px; font-weight:600; min-height:22px; }
QPushButton#TrainingNavButton:hover { background:#223340; color:#f4f7f8; }
QPushButton#TrainingNavButton:checked { background:#30473f; color:#c2f1db; }
QWidget#TrainingCenter QTabWidget#TrainingTabs::pane { background:#101820; border:0; }
QWidget#TrainingCenter QScrollArea#DashboardScroll, QWidget#TrainingCenter QWidget#DashboardContent { background:#101820; border:0; }
QWidget#TrainingCenter QFrame#DashboardCard,
QWidget#TrainingCenter QFrame#TrainingCard,
QWidget#TrainingCenter QFrame#TrainingControlPanel,
QWidget#TrainingCenter QFrame#ScheduleBoard { background:#19242e; border:1px solid #2b3945; border-radius:10px; }
QWidget#TrainingCenter QFrame#DashboardStat { background:#1c2b35; border:1px solid #33464f; border-top:3px solid #74bda6; border-radius:9px; }
QWidget#TrainingCenter QLabel#DashboardValue { font-size:25px; font-weight:700; color:#f3f7f5; padding:6px 0; }
QWidget#TrainingCenter QLabel#SectionTitle { font-size:20px; font-weight:700; color:#f0f4f7; }
QWidget#TrainingCenter QLabel#SectionEyebrow { font-size:11px; font-weight:700; color:#7fbea9; }
QWidget#TrainingCenter QLabel#CardTitle { font-size:18px; font-weight:700; color:#eef4f6; }
QWidget#TrainingCenter QLabel#FieldLabel { color:#a8bbc8; font-size:13px; margin-top:8px; }
QWidget#TrainingCenter QLabel#SelectedName { color:#b6e6d3; font-size:23px; font-weight:700; padding:14px 0; }
QWidget#TrainingCenter QLabel#ImpactText { color:#b5c8d4; background:#13212a; border:1px solid #2e4551; border-radius:8px; padding:14px; font-size:14px; }
QWidget#TrainingCenter QFrame#ScheduleLegend { background:transparent; border:0; }
QWidget#TrainingCenter QFrame#TrainingDay { background:#21303c; border:0; border-radius:5px; }
QWidget#TrainingCenter QFrame#TrainingDay[weekend="true"] { background:#30313b; }
QWidget#TrainingCenter QLabel#DayName { color:#e2eaf0; font-size:15px; }
QWidget#TrainingCenter QLabel#DayDate { color:#9cafbf; font-size:13px; padding:0; }
QWidget#TrainingCenter QLabel#SessionLabel { color:#849aab; font-size:12px; padding:4px; }
QWidget#TrainingCenter QLabel#DashboardDay { color:#b5c9d7; font-size:13px; }
QWidget#TrainingCenter QLabel#DashboardSession { background:#253b4a; border:0; border-left:3px solid #719fbe; border-radius:5px; color:#c2dbea; font-size:13px; padding:6px; }
QWidget#TrainingCenter QLabel#DashboardSession[category="recovery"] { background:#203b32; border-left-color:#80bd9e; color:#b9dfca; }
QWidget#TrainingCenter QLabel#DashboardSession[category="load"] { background:#403728; border-left-color:#d1b17b; color:#e7d1aa; }
QWidget#TrainingCenter QLabel#DashboardProtection { color:#a9d2bd; background:#20372e; border:1px solid #365445; border-radius:7px; padding:13px; }
QWidget#TrainingCenter QLabel#DashboardReport { color:#b8c9d3; font-size:14px; }
QWidget#TrainingCenter QLabel#CoachDetail { background:#15232b; border:0; border-left:3px solid #79b5a0; color:#c2d3dc; padding:14px; }
QWidget#TrainingCenter QLineEdit,
QWidget#TrainingCenter QComboBox,
QWidget#TrainingCenter QSpinBox { background:#111d27; color:#e4edf3; border:1px solid #3b4c59; border-radius:6px; min-height:30px; font-size:14px; padding:5px 12px; }
QWidget#TrainingCenter QComboBox { padding-right:28px; }
QWidget#TrainingCenter QComboBox::drop-down { width:24px; border:0; border-left:1px solid #30414e; }
QWidget#TrainingCenter QComboBox:hover,
QWidget#TrainingCenter QSpinBox:hover,
QWidget#TrainingCenter QLineEdit:focus { border-color:#7db59f; }
QWidget#TrainingCenter QComboBox QAbstractItemView { background:#1c2c37; color:#e0e8ed; selection-background-color:#385749; min-width:180px; padding:6px; }
QWidget#TrainingCenter QComboBox#SessionCombo { background:#223947; color:#cce2ee; font-size:14px; border:1px solid #344f60; border-left:3px solid #79a5c0; min-height:32px; }
QWidget#TrainingCenter QComboBox#SessionCombo[category="recovery"] { background:#223c33; border-color:#375647; border-left-color:#8bbca3; color:#c7e4d4; }
QWidget#TrainingCenter QComboBox#SessionCombo[category="load"] { background:#3d3529; border-color:#594a35; border-left-color:#d6b57f; color:#ebd8b7; }
QWidget#TrainingCenter QPushButton#PrimaryButton,
QWidget#TrainingCenter QPushButton#WorkflowButton { background:#acd9c1; color:#15291f; border:1px solid #bddfce; border-radius:6px; padding:6px 14px; min-height:30px; font-size:14px; font-weight:700; }
QWidget#TrainingCenter QPushButton#PrimaryButton:hover { background:#c3e7d3; }
QWidget#TrainingCenter QPushButton#SecondaryButton { color:#c7d6e1; background:#233440; border:1px solid #455a68; border-radius:6px; min-height:30px; padding:6px 12px; font-size:13px; font-weight:600; }
QWidget#TrainingCenter QPushButton#SecondaryButton:hover { background:#304653; border-color:#85b6a2; }
QWidget#TrainingCenter QPushButton:disabled { background:#27323a; color:#657682; border-color:#33414b; }
QWidget#TrainingCenter QTableWidget#TrainingTable { background:#16222c; alternate-background-color:#192833; color:#d2dee6; border:1px solid #2e414e; border-radius:7px; font-size:14px; selection-background-color:#304e49; selection-color:#e3f4ea; }
QWidget#TrainingCenter QTableWidget#TrainingTable::item { padding:6px 9px; border:0; border-bottom:1px solid #253540; }
QWidget#TrainingCenter QTableWidget#TrainingTable::item:hover { background:#243b47; }
QWidget#TrainingCenter QHeaderView::section { background:#20323f; color:#a3bbcc; border:0; border-bottom:1px solid #3a5160; padding:12px 8px; font-size:12px; font-weight:600; }
QWidget#TrainingCenter QTabWidget#StaffSections::pane { border:0; padding-top:12px; }
QWidget#TrainingCenter QTabBar::tab { background:transparent; color:#9db0bf; border:0; border-bottom:2px solid transparent; padding:12px 18px; font-size:14px; }
QWidget#TrainingCenter QTabBar::tab:selected { color:#c8e5d7; border-bottom:2px solid #93c6ab; }
QWidget#TrainingCenter QScrollBar:vertical { background:#14212a; width:8px; border:0; margin:0; }
QWidget#TrainingCenter QScrollBar::handle:vertical { background:#49616f; border-radius:4px; min-height:30px; }
QWidget#TrainingCenter QScrollBar::add-line:vertical, QWidget#TrainingCenter QScrollBar::sub-line:vertical { height:0; }
"""

from pathlib import Path
import sys

_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
_icons = (_root / 'image/ui').as_posix()
TRAINING_STYLE += """
QWidget#TrainingCenter QLabel#TrainingRating { background:#20362f; color:#bfdccc; border:1px solid #3b5548; border-radius:7px; padding:10px; font-size:13px; }
QWidget#TrainingCenter QLabel#TrainingEmpty { background:#19262f; border:1px solid #31454f; border-radius:10px; color:#9bb4c3; font-size:16px; padding:40px; }
QWidget#TrainingCenter QLabel#LegendRecovery { color:#83c8a8; }
QWidget#TrainingCenter QLabel#LegendSkill { color:#87b8d6; }
QWidget#TrainingCenter QLabel#LegendLoad { color:#d7b57e; }
QWidget#TrainingCenter QComboBox::down-arrow { image:url(ICONS/training-chevron.svg); width:12px; height:8px; }
QWidget#TrainingCenter QSpinBox { padding-right:30px; }
QWidget#TrainingCenter QSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:24px; border:0; }
QWidget#TrainingCenter QSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:24px; border:0; }
QWidget#TrainingCenter QSpinBox::up-arrow { image:url(ICONS/training-plus.svg); width:10px; height:10px; }
QWidget#TrainingCenter QSpinBox::down-arrow { image:url(ICONS/training-minus.svg); width:10px; height:10px; }
QWidget#TrainingCenter QTableWidget::indicator { width:16px; height:16px; border:1px solid #617b8c; border-radius:3px; background:#182933; }
QWidget#TrainingCenter QTableWidget::indicator:checked { image:url(ICONS/training-check.svg); border:0; }
""".replace('ICONS', _icons)
