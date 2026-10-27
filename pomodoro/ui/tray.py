"""System tray icon: shows minutes left, offers quick controls, pops notifications."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from pomodoro.timer import Phase
from pomodoro.ui.main_window import format_mmss
from pomodoro.ui.theme import PHASE_COLORS, make_icon


class TrayIcon(QSystemTrayIcon):
    show_window = Signal()
    toggle_timer = Signal()
    skip_phase = Signal()
    toggle_mini = Signal()
    open_settings = Signal()
    open_help = Signal()
    quit_app = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_icon_key = None

        menu = QMenu()
        self.show_action = QAction("Show window", menu, triggered=self.show_window.emit)
        self.toggle_action = QAction("Start", menu, triggered=self.toggle_timer.emit)
        self.skip_action = QAction("Skip", menu, triggered=self.skip_phase.emit)
        self.mini_action = QAction("Mini timer", menu, checkable=True,
                                   triggered=lambda _: self.toggle_mini.emit())
        settings_action = QAction("Settings…", menu, triggered=self.open_settings.emit)
        help_action = QAction("Help", menu, triggered=self.open_help.emit)
        quit_action = QAction("Quit", menu, triggered=self.quit_app.emit)
        menu.addAction(self.show_action)
        menu.addSeparator()
        menu.addAction(self.toggle_action)
        menu.addAction(self.skip_action)
        menu.addSeparator()
        menu.addAction(self.mini_action)
        menu.addAction(settings_action)
        menu.addAction(help_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self._menu = menu  # keep a reference so it isn't garbage-collected

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window.emit()

    def show_state(self, phase: Phase, running: bool, started: bool, remaining: float):
        # Icon shows whole minutes left (rounded up), e.g. "18"; redraw only when it changes.
        minutes = str(int((remaining + 59) // 60)) if started else ""
        key = (phase, running, minutes)
        if key != self._last_icon_key:
            self.setIcon(make_icon(PHASE_COLORS[phase], minutes, dimmed=started and not running))
            self._last_icon_key = key

        if started:
            state = "" if running else " (paused)"
            self.setToolTip(f"{phase.label}{state}: {format_mmss(remaining)} left")
        else:
            self.setToolTip(f"Pomodoro Tracker - {phase.label}")

        self.toggle_action.setText("Pause" if running else ("Resume" if started else "Start"))
        self.skip_action.setEnabled(phase != Phase.IDLE)

    def notify(self, title: str, message: str):
        self.showMessage(title, message, QSystemTrayIcon.Information, 8000)
