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
QWidget#root, QWidget#root > QWidget { background: #FAFAFA; }
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
