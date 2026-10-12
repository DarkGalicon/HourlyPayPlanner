"""Visual style shared by the desktop workspace."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableView, QWidget

PRIMARY_BUTTONS = frozenset({
    "selectXlsxButton",
    "confirmImportButton",
    "confirmEffectiveRateButton",
    "saveSourceInclusionsButton",
    "saveHourlySelectionButton",
    "saveMonthlyPlanButton",
    "saveAvailabilityButton",
    "saveCalendarButton",
    "generateScheduleButton",
    "exportStatementButton",
})
DANGER_BUTTONS = frozenset({"clearMonthlyPlanButton", "clearScheduleMonthButton"})

WORKSPACE_STYLE = """
QMainWindow, QWidget#appShell { background: #f3f6fb; color: #1d2b3f; }
QWidget#headerCard {
    background: #ffffff;
    border: 1px solid #dce5f0;
    border-radius: 14px;
}
QLabel { color: #26364b; }
QLabel#headerEyebrow { color: #52729d; font-size: 10px; font-weight: 700; }
QLabel#headerTitle { color: #172b47; font-size: 23px; font-weight: 700; }
QLabel#headerDescription { color: #64748b; font-size: 12px; }
QLabel[uiRole="section"] { color: #244c7c; font-size: 12px; font-weight: 700; }
QLabel#stepBadge {
    color: #225c9e;
    background: #eaf2fd;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 11px;
    font-weight: 700;
}
QLabel[uiRole="status"] {
    color: #465d79;
    background: #f1f5fa;
    border: 1px solid #e2e9f2;
    border-radius: 8px;
    padding: 9px 12px;
}
QLabel#selectionSummary {
    color: #155a9f;
    background: #eaf3fc;
    border: 1px solid #d0e4f8;
    border-radius: 8px;
    padding: 10px 12px;
    font-weight: 700;
}
QLabel#calculation_hourly_limit { color: #1762ad; font-size: 19px; font-weight: 700; }
QTabWidget#mainNavigation::pane {
    background: #ffffff;
    border: 1px solid #dce5f0;
    border-radius: 12px;
    top: -1px;
}
QTabBar#mainTabBar::tab {
    background: transparent;
    color: #52647c;
    border: none;
    border-radius: 8px;
    padding: 10px 13px;
    margin: 0 4px 7px 0;
    font-weight: 600;
}
QTabBar#mainTabBar::tab:hover { background: #e6edf7; color: #244f84; }
QTabBar#mainTabBar::tab:selected { background: #245fa7; color: #ffffff; }
QTabWidget#planTabs::pane, QTabWidget#scheduleTabs::pane,
QTabWidget#settingsTabs::pane { border: none; background: #ffffff; }
QTabBar::tab {
    background: #f2f5f9;
    color: #5b6f88;
    border: 1px solid #dfe7f0;
    border-bottom: none;
    border-radius: 7px 7px 0 0;
    padding: 8px 15px;
    margin-right: 4px;
}
QTabBar::tab:selected { background: #ffffff; color: #205eaa; font-weight: 700; }
QPushButton {
    background: #ffffff;
    color: #2c4c72;
    border: 1px solid #cad7e5;
    border-radius: 7px;
    padding: 7px 13px;
    min-height: 23px;
    font-weight: 600;
}
QPushButton:hover { background: #eef4fc; border-color: #9db9db; }
QPushButton:pressed { background: #dceaf9; }
QPushButton:disabled {
    color: #9aa8b9;
    background: #f1f4f8;
    border-color: #e0e6ed;
}
QPushButton[uiRole="primary"] { background: #245fa7; color: #ffffff; border-color: #245fa7; }
QPushButton[uiRole="primary"]:hover { background: #174f91; border-color: #174f91; }
QPushButton[uiRole="primary"]:disabled {
    background: #afc5dd; color: #f6f9fc; border-color: #afc5dd;
}
QPushButton[uiRole="danger"] { color: #a43443; border-color: #e8bec4; }
QPushButton[uiRole="danger"]:hover { background: #fff0f1; border-color: #d78c97; }
QLineEdit, QComboBox, QSpinBox, QDateEdit, QPlainTextEdit {
    color: #23344a;
    background: #ffffff;
    border: 1px solid #cad7e5;
    border-radius: 7px;
    padding: 5px 8px;
    selection-background-color: #c7dffd;
}
QLineEdit, QComboBox, QSpinBox, QDateEdit { min-height: 23px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus,
QPlainTextEdit:focus { border: 1px solid #3682d1; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled {
    color: #9aa8b9; background: #f3f6f9; border-color: #e3e9ef;
}
QComboBox QAbstractItemView {
    color: #23344a;
    background: #ffffff;
    border: 1px solid #cad7e5;
    selection-color: #183a62;
    selection-background-color: #d8eafd;
    outline: none;
}
QTableView, QTableWidget {
    background: #ffffff;
    alternate-background-color: #f7f9fc;
    color: #25374d;
    gridline-color: #e5ebf3;
    border: 1px solid #dce5f0;
    border-radius: 8px;
    selection-background-color: #d8eafd;
    selection-color: #183a62;
}
QHeaderView::section {
    background: #edf2f8;
    color: #48627f;
    border: none;
    border-right: 1px solid #dce5f0;
    border-bottom: 1px solid #dce5f0;
    padding: 9px 10px;
    font-weight: 700;
}
QTableCornerButton::section { background: #edf2f8; border: none; }
QScrollArea#documentsScrollArea, QScrollArea#teacherScrollArea {
    background: #ffffff; border: none;
}
QWidget#documentsContent { background: #ffffff; }
QToolTip {
    color: #24344c;
    background: #ffffff;
    border: 1px solid #c7d6e8;
    padding: 6px;
}
"""


def apply_application_appearance(application: QApplication) -> None:
    application.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#f3f6fb"),
        (QPalette.ColorRole.WindowText, "#1d2b3f"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, "#f7f9fc"),
        (QPalette.ColorRole.Text, "#23344a"),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.ButtonText, "#2c4c72"),
        (QPalette.ColorRole.Highlight, "#d8eafd"),
        (QPalette.ColorRole.HighlightedText, "#183a62"),
        (QPalette.ColorRole.ToolTipBase, "#ffffff"),
        (QPalette.ColorRole.ToolTipText, "#24344c"),
    ):
        palette.setColor(role, QColor(color))
    application.setPalette(palette)
    application.setStyleSheet(WORKSPACE_STYLE)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(10)
    application.setFont(font)
    application.setWindowIcon(_application_icon())


def apply_workspace_appearance(window: QWidget) -> None:
    for button in window.findChildren(QPushButton):
        name = button.objectName()
        if name in PRIMARY_BUTTONS or name.startswith("saveSemesterStart"):
            button.setProperty("uiRole", "primary")
        elif name in DANGER_BUTTONS:
            button.setProperty("uiRole", "danger")
    for label in window.findChildren(QLabel):
        name = label.objectName().lower()
        if name.endswith("status") or name.endswith("statuslabel"):
            label.setProperty("uiRole", "status")
    for table in window.findChildren(QTableView):
        table.verticalHeader().setDefaultSectionSize(38)
        if table.objectName() == "weeklyAvailabilityTable":
            table.verticalHeader().show()
        else:
            table.verticalHeader().hide()
        table.setShowGrid(False)
    window.setStyleSheet(WORKSPACE_STYLE)


def _application_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#245fa7"))
    painter.drawRoundedRect(2, 2, 60, 60, 15, 15)
    painter.setPen(QPen(QColor("#ffffff"), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(13, 13, 38, 38)
    painter.drawLine(32, 19, 32, 33)
    painter.drawLine(32, 33, 41, 39)
    painter.end()
    return QIcon(pixmap)
