"""The main timer window."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QHBoxLayout, QLabel, QMainWindow,
                               QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from pomodoro.timer import Phase
from pomodoro.ui.focus_next import FocusNextPanel
from pomodoro.ui.theme import PHASE_COLORS, STYLESHEET


def format_mmss(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class MainWindow(QMainWindow):
    # Emitted when the user closes the window; the app decides whether to hide to tray.
    close_requested = Signal()
    # Emitted when the user presses Enter in the task box.
    task_entered = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pomodoro Tracker")
        self.setMinimumSize(520, 640)
        self.resize(1100, 760)
        self.allow_close = False

        # Tabs: "Timer" is built here; the app adds "Tasks" (it needs the database).
        self.tabs = QTabWidget(objectName="root")
        self.tabs.setStyleSheet(STYLESHEET)
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)
        root = QWidget(objectName="timerPage")
        timer_page = QHBoxLayout()   # centres the timer column in a wide window
        timer_page.addStretch()
        timer_page.addWidget(root, 0)
        timer_page.addStretch()
        wrapper = QWidget()
        wrapper.setLayout(timer_page)
        root.setFixedWidth(480)
        self.tabs.addTab(wrapper, "Timer")

        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 4, 8, 4)
        self.mini_button = QPushButton("⧉ Mini timer", objectName="small")
        self.mini_button.setToolTip("Show a small always-on-top timer")
        self.settings_button = QPushButton("⚙ Settings", objectName="small")
        for button in (self.mini_button, self.settings_button):
            button.setCursor(Qt.PointingHandCursor)
            corner_layout.addWidget(button)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        # Type a new task name or pick a recent one from the drop-down.
        self.task_input = QComboBox(objectName="task", editable=True)
        self.task_input.setInsertPolicy(QComboBox.NoInsert)
        self.task_input.lineEdit().setPlaceholderText("What are you working on?")
        self.task_input.lineEdit().returnPressed.connect(self.task_entered.emit)
        self.task_input.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.task_input.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.task_stats_label = QLabel(objectName="taskStats", wordWrap=True)
        self.mark_done_button = QPushButton("✓ Mark done", objectName="small")
        self.mark_done_button.setCursor(Qt.PointingHandCursor)
        self.mark_done_button.setToolTip("Mark this task as completed")
        task_info_row = QHBoxLayout()
        task_info_row.addWidget(self.task_stats_label, 1)
        task_info_row.addWidget(self.mark_done_button)

        self.phase_label = QLabel("READY", objectName="phase", alignment=Qt.AlignCenter)
        self.time_label = QLabel("25:00", objectName="time", alignment=Qt.AlignCenter)
        self.progress = QProgressBar(textVisible=False, maximum=1000)

        self.start_button = QPushButton("Start", objectName="primary")
        self.skip_button = QPushButton("Skip")
        self.stop_button = QPushButton("Stop")
        for button in (self.start_button, self.skip_button, self.stop_button):
            button.setCursor(Qt.PointingHandCursor)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.skip_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()

        self.stats_label = QLabel(objectName="stats", alignment=Qt.AlignCenter)
        self.hint_label = QLabel(objectName="hint", alignment=Qt.AlignCenter)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self.task_input)
        layout.addLayout(task_info_row)
        layout.addSpacing(6)
        layout.addWidget(self.phase_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.progress)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addSpacing(4)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.hint_label)
        layout.addSpacing(8)
        self.focus_next = FocusNextPanel()
        layout.addWidget(self.focus_next)
        layout.addStretch()

    def show_state(self, phase: Phase, running: bool, started: bool,
                   remaining: float, total: float):
        color = PHASE_COLORS[phase]
        status = "" if running or not started else "  ·  PAUSED"
        self.phase_label.setText(phase.label.upper() + status)
        self.phase_label.setStyleSheet(f"color: {color};")
        self.time_label.setText(format_mmss(remaining))
        self.progress.setValue(int(1000 * (1 - remaining / total)) if total else 0)
        self.progress.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")

        if running:
            self.start_button.setText("Pause")
        elif started:
            self.start_button.setText("Resume")
        elif phase in (Phase.BREAK, Phase.LONG_BREAK):
            self.start_button.setText("Start break")
        else:
            self.start_button.setText("Start")
        button_color = PHASE_COLORS[Phase.FOCUS] if phase == Phase.IDLE else color
        self.start_button.setStyleSheet(f"background: {button_color};")
        self.skip_button.setEnabled(phase != Phase.IDLE)
        self.stop_button.setEnabled(started)

        title = f"{format_mmss(remaining)} · {phase.label}" if started else "Pomodoro Tracker"
        self.setWindowTitle(title)

    def show_stats(self, pomodoros: int, goal: int, focus_minutes: int):
        hours, minutes = divmod(focus_minutes, 60)
        focused = f"{hours} h {minutes} min" if hours else f"{minutes} min"
        self.stats_label.setText(f"Today:  🍅 {pomodoros} / {goal}   ·   {focused} focused")

    def show_hint(self, text: str, warning: bool = False):
        self.hint_label.setText(text)
        self.hint_label.setStyleSheet("color: #CE2C31; font-weight: 600;" if warning else "")

    # ---------- task box ----------

    def task_name(self) -> str:
        return " ".join(self.task_input.currentText().split())

    def set_task_choices(self, titles: list[str]):
        """Fill the drop-down with recent tasks, keeping whatever is typed."""
        current = self.task_input.currentText()
        self.task_input.blockSignals(True)
        self.task_input.clear()
        self.task_input.addItems(titles)
        self.task_input.setEditText(current)
        self.task_input.blockSignals(False)

    def set_task_locked(self, locked: bool):
        """The task can't be changed in the middle of a focus block."""
        self.task_input.setEnabled(not locked)

    def show_task_info(self, text: str, can_mark_done: bool):
        self.task_stats_label.setText(text)
        self.mark_done_button.setVisible(can_mark_done)

    def set_task_name(self, title: str):
        self.task_input.setEditText(title)

    def ask_for_task(self):
        self.show_hint("Enter a task name before starting the pomodoro.", warning=True)
        self.task_input.setFocus()

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.close_requested.emit()
