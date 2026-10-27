"""The main timer window."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QCompleter, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QMainWindow, QProgressBar, QPushButton, QScrollArea, QTabWidget,
                               QVBoxLayout, QWidget)

from pomodoro.models import ANOMALY_REASONS, REASON_CHIPS
from pomodoro.timer import Phase
from pomodoro.ui.focus_next import FocusNextPanel
from pomodoro.ui.theme import PHASE_COLORS, STYLESHEET


def format_mmss(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class MainWindow(QMainWindow):
    # Emitted when the user closes the window; the app decides whether to hide to tray.
    close_requested = Signal()
    # A reason was picked for a pomodoro that stopped early (None = skipped).
    reason_chosen = Signal(object)
    # Emitted when the user presses Enter in the task box.
    task_entered = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pomodoro Tracker")
        self.setMinimumSize(480, 420)
        self.allow_close = False
        self._sized = False

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
        wrapper = QWidget(objectName="timerWrapper")
        wrapper.setLayout(timer_page)
        root.setFixedWidth(480)
        self.timer_root = root
        # Scrolls on short screens, so nothing is ever cut off.
        timer_scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        timer_scroll.setWidget(wrapper)
        self.tabs.addTab(timer_scroll, "Timer")

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
        # The task box and (added by the app) the project picker share a row.
        self.task_row = QHBoxLayout()
        self.task_row.setSpacing(6)
        self.task_row.addWidget(self.task_input, 1)
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
        layout.addLayout(self.task_row)
        layout.addLayout(task_info_row)
        layout.addSpacing(6)
        layout.addWidget(self.phase_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.progress)
        layout.addSpacing(10)
        layout.addLayout(buttons)

        # One click while focusing: "I got distracted" (counted, timer keeps going).
        self.distraction_button = QPushButton("⚡ I got distracted", objectName="small")
        self.distraction_button.setCursor(Qt.PointingHandCursor)
        self.distraction_button.setToolTip("Log a distraction without stopping the timer. "
                                           "Reports show what interrupts you most.")
        self.distraction_button.hide()
        distraction_row = QHBoxLayout()
        distraction_row.addStretch()
        distraction_row.addWidget(self.distraction_button)
        distraction_row.addStretch()
        layout.addLayout(distraction_row)

        # After stopping early: "What got in the way?" with one-click reasons.
        self.reason_bar = QFrame(objectName="reasonBar")
        reason_layout = QVBoxLayout(self.reason_bar)
        reason_layout.setContentsMargins(10, 8, 10, 8)
        reason_layout.setSpacing(6)
        reason_layout.addWidget(QLabel("Pomodoro stopped early – what got in the way?",
                                       objectName="reasonTitle"))
        chips = QGridLayout()
        chips.setSpacing(6)
        for i, (key, label) in enumerate([*REASON_CHIPS.items(), (None, "Skip")]):
            chip = QPushButton(label, objectName="chip")
            chip.setMinimumHeight(28)
            if key:
                chip.setToolTip(ANOMALY_REASONS[key])
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, k=key: self.reason_chosen.emit(k))
            chips.addWidget(chip, i // 4, i % 4)
        reason_layout.addLayout(chips)
        self.reason_bar.hide()
        layout.addWidget(self.reason_bar)
        layout.addSpacing(4)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.hint_label)
        layout.addSpacing(8)
        self.focus_next = FocusNextPanel()
        layout.addWidget(self.focus_next)
        layout.addStretch()

    def fit_to_screen(self):
        """First time the window is shown: as big as is comfortable, but never off-screen."""
        if self._sized:
            return
        self._sized = True
        screen = self.screen() or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        width = min(1100, area.width() - 40)
        height = min(760, area.height() - 40)   # leaves room for the title bar
        self.resize(width, height)
        self.move(area.left() + (area.width() - width) // 2,
                  area.top() + max((area.height() - height) // 2 - 10, 0))

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

    def fit_timer_page(self):
        """Let the Timer page grow (and scroll) instead of squashing Focus Next."""
        self.timer_root.setMinimumHeight(self.timer_root.sizeHint().height())

    def show_distractions(self, visible: bool, count: int = 0):
        self.distraction_button.setVisible(visible)
        self.distraction_button.setText(f"⚡ I got distracted ({count})" if count
                                         else "⚡ I got distracted")

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
