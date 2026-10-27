"""Colours, the tray/window icon, and the app stylesheet."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from pomodoro.timer import Phase

PHASE_COLORS = {
    Phase.IDLE: "#8B8D98",
    Phase.FOCUS: "#E5484D",
    Phase.BREAK: "#30A46C",
    Phase.LONG_BREAK: "#0090FF",
}


def make_icon(color: str, text: str = "", dimmed: bool = False) -> QIcon:
    """A round coloured badge, optionally with a number (minutes left) on it."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fill = QColor(color)
    if dimmed:
        fill.setAlpha(140)
    painter.setBrush(fill)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)

    if text:
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(38 if len(text) <= 2 else 28)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


STYLESHEET = """
QWidget#root, QWidget#root > QWidget, QWidget#timerWrapper { background: #FAFAFA; }
QComboBox#projectPicker, QFrame#todoCard QComboBox#projectPicker {
    background: white; color: #1C2024; border: 1px solid #D9D9E0; border-radius: 6px;
    padding: 5px 8px; font-size: 13px; }
QComboBox#projectPicker:disabled, QFrame#todoCard QComboBox#projectPicker:disabled {
    background: #F0F0F3; color: #8B8D98; }
QComboBox#projectPicker QAbstractItemView { background: white; color: #1C2024;
    selection-background-color: #FFE5E5; selection-color: #1C2024; }
QTabBar::tab { padding: 8px 22px; font-size: 13px; color: #60646C; }
QTabBar::tab:selected { color: #1C2024; font-weight: 600; border-bottom: 2px solid #E5484D; }
QTableWidget { background: white; border: 1px solid #E8E8EC; border-radius: 6px;
               font-size: 13px; alternate-background-color: #F9F9FB; }
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background: #FFE5E5; color: #1C2024; }
QHeaderView::section { background: white; border: none; border-bottom: 1px solid #E8E8EC;
                       padding: 6px; font-weight: 600; color: #60646C; }
QLineEdit, QComboBox { padding: 5px 8px; }
QPushButton#small { font-size: 12px; padding: 3px 10px; }
QFrame#focusNext { background: white; border: 1px solid #E8E8EC; border-radius: 8px; }
QFrame#focusNext QWidget { background: transparent; }
QLabel#panelTitle { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #8B8D98; }
QLabel#summary { font-size: 12px; color: #60646C; }
QLabel#rank { font-size: 12px; font-weight: 700; color: #B9BBC6; }
QLabel#taskName { font-size: 13px; font-weight: 600; color: #1C2024; }
QLabel#reason { font-size: 11px; color: #8B8D98; }
QPushButton#play { color: white; border: none; border-radius: 15px; padding: 0 0 0 2px;
                   font-size: 14px; }
QPushButton#play:disabled { background: #E8E8EC; }
QWidget#reportsContent { background: #FAFAFA; }
QFrame#card, QFrame#tile { background: white; border: 1px solid #E8E8EC; border-radius: 8px; }
QFrame#card QLabel, QFrame#tile QLabel { background: transparent; border: none; }
QLabel#cardTitle { font-size: 13px; font-weight: 700; color: #1C2024; }
QLabel#cardNote { font-size: 11px; color: #8B8D98; }
QLabel#tileCaption { font-size: 11px; font-weight: 600; color: #60646C; }
QLabel#tileValue { font-size: 26px; font-weight: 600; color: #1C2024; }
QLabel#tileDetail { font-size: 11px; color: #8B8D98; }
QFrame#boardColumn { background: #F0F0F3; border-radius: 8px; }
QLabel#boardHeader { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #60646C;
                     background: transparent; }
QFrame#taskCard { background: white; border: 1px solid #E8E8EC; border-radius: 6px; }
QFrame#taskCard QLabel { background: transparent; border: none; }
QFrame#todoSidebar { background: #F7F7F8; border-right: 1px solid #E8E8EC; }
QLineEdit#todoSearch { background: #ECECEF; border: none; border-radius: 6px; padding: 7px 10px;
                       font-size: 13px; }
QListWidget#todoNav { background: transparent; border: none; outline: none; }
QListWidget#todoNav::item { border-radius: 6px; margin: 1px 0; }
QListWidget#todoNav::item:selected { background: #E6E6EA; }
QListWidget#todoNav::item:hover:!selected { background: #EFEFF2; }
QListWidget#todoNav QLabel { background: transparent; }
QLabel#navName { font-size: 14px; color: #1C2024; }
QLabel#navMeta { font-size: 12px; color: #8B8D98; }
QLabel#navHeader { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #8B8D98; }
QToolButton#navAdd { border: none; background: transparent; color: #60646C; font-size: 18px;
                     padding: 0 6px; }
QToolButton#navAdd:hover { background: #E6E6EA; border-radius: 4px; }
QLabel#navNew { font-size: 13px; color: #60646C; }
QWidget#todoMain, QWidget#todoList { background: #F2F2F4; }
QLabel#todoHeading { font-size: 24px; font-weight: 600; color: #1C2024; }
QToolButton#todoSort { border: none; background: white; border-radius: 6px; font-size: 16px;
                       padding: 4px 10px; color: #60646C; }
QToolButton#todoSort::menu-indicator { image: none; }
QFrame#todoCard { background: white; border-radius: 8px; border: none; }
QFrame#todoCard QWidget, QFrame#todoCard QLabel { background: transparent; }
QLabel#todoStatValue { font-size: 32px; font-weight: 300; color: #E5484D; }
QLabel#todoStatCaption { font-size: 12px; color: #8B8D98; }
QLabel#todoPlus { font-size: 22px; color: #8B8D98; padding-right: 4px; }
QLineEdit#todoAdd { border: none; background: transparent; font-size: 14px; padding: 8px 2px; }
QToolButton#estimateDot { border: none; background: transparent; font-size: 16px; padding: 0 1px; }
QFrame#todoRow { background: white; border-radius: 8px; }
QFrame#todoRow:hover { background: #FBFBFC; }
QFrame#todoRow QLabel { background: transparent; }
QLabel#todoTitle { font-size: 14px; color: #1C2024; }
QLabel#todoComing { font-size: 13px; color: #8B8D98; background: #F7F7F9; border-radius: 8px;
                    padding: 9px 14px; border: 1px dashed #E0E1E6; }
QLabel#seriesIcon { font-size: 18px; background: transparent; }
QLabel#intention { font-size: 12px; color: #18794E; background: #EAF7EF; border-radius: 6px;
                   padding: 6px 8px; }
QLabel#todoMeta { font-size: 12px; }
QLabel#todoDue { font-size: 12px; color: #8B8D98; }
QLabel#todoGroup { font-size: 13px; color: #1C2024; background: transparent; }
QLabel#todoEmpty { font-size: 13px; color: #8B8D98; padding: 24px; background: transparent; }
QToolButton#rowPlay { border: none; border-radius: 12px; background: #FFE5E5; color: #E5484D;
                      font-size: 10px; padding-left: 2px; }
QToolButton#rowPlay:hover { background: #E5484D; color: white; }
QToolButton#rowPlay:disabled { background: #F0F0F3; color: #C9CAD1; }
QPushButton#todoDoneToggle { text-align: left; border: none; background: transparent;
                             color: #60646C; font-size: 13px; padding: 10px 4px 2px 4px; }
QLabel#phase { font-size: 16px; font-weight: 600; letter-spacing: 1px; }
QLabel#time  { font-size: 72px; font-weight: 300; color: #1C2024; }
QLabel#stats { font-size: 13px; color: #60646C; }
QLabel#hint  { font-size: 12px; color: #8B8D98; }
QLabel#taskStats { font-size: 12px; color: #60646C; }
QComboBox#task {
    font-size: 15px; padding: 7px 10px; border: 1px solid #D9D9E0;
    border-radius: 6px; background: white; color: #1C2024;
}
QComboBox#task:focus { border-color: #E5484D; }QComboBox#task:disabled { background: #F0F0F3; color: #1C2024; }
QProgressBar { border: none; background: #E8E8EC; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { border-radius: 3px; }
QPushButton {
    font-size: 14px; padding: 8px 18px; border-radius: 6px;
    border: 1px solid #D9D9E0; background: white; color: #1C2024;
}
QPushButton:hover { background: #F0F0F3; }
QPushButton#primary { color: white; border: none; font-weight: 600; min-width: 110px; }
"""
