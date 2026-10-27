"""Settings: timer lengths, daily goal, working days, Focus Score points and the shortcut."""

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QKeySequenceEdit, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from pomodoro.database import Database
from pomodoro.priority import DEFAULT_WEIGHTS, ScoreWeights
from pomodoro.ui.list_editor import editor_page

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

WEIGHT_LABELS = [
    ("p1", "P1 Critical"), ("p2", "P2 High"), ("p3", "P3 Medium"), ("p4", "P4 Low"),
    ("overdue", "Overdue"), ("due_today", "Due today"), ("due_tomorrow", "Due tomorrow"),
    ("within_3_days", "Due within 3 days"), ("within_7_days", "Due within 7 days"),
    ("at_risk", "At risk (bonus)"),
    ("never_miss_twice", "Missed last time"),
    ("energy_match", "Fits the time of day"),
]


def spin(minimum: int, maximum: int, suffix: str = "") -> QSpinBox:
    box = QSpinBox(minimum=minimum, maximum=maximum)
    box.setSuffix(suffix)
    return box


def note(text: str) -> QLabel:
    return QLabel(text, objectName="cardNote", wordWrap=True)


class SettingsDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        tabs = QTabWidget()
        tabs.addTab(self._timer_page(), "Timer")
        tabs.addTab(self._goals_page(), "Goals")
        self.lists_page = editor_page(db)
        tabs.addTab(self.lists_page, "Categories && Types")
        tabs.addTab(self._score_page(), "Focus Score")
        tabs.addTab(self._shortcut_page(), "Shortcut")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self._load()

    # ---------- pages ----------

    def _timer_page(self) -> QWidget:
        page = QWidget()
        self.focus_minutes = spin(1, 120, " min")
        self.break_minutes = spin(1, 60, " min")
        self.long_break_enabled = QCheckBox("Take a long break")
        self.long_break_minutes = spin(1, 60, " min")
        self.long_break_every = spin(2, 12, " pomodoros")
        self.auto_start_break = QCheckBox("Start breaks automatically")
        self.auto_start_focus = QCheckBox("Start the next pomodoro automatically after a break")
        self.sound_enabled = QCheckBox("Play a sound when a block ends")
        self.long_break_enabled.toggled.connect(self.long_break_minutes.setEnabled)
        self.long_break_enabled.toggled.connect(self.long_break_every.setEnabled)

        long_row = QHBoxLayout()
        long_row.addWidget(self.long_break_minutes)
        long_row.addWidget(QLabel("every"))
        long_row.addWidget(self.long_break_every)

        form = QFormLayout(page)
        form.addRow("Focus", self.focus_minutes)
        form.addRow("Break", self.break_minutes)
        form.addRow(self.long_break_enabled, long_row)
        form.addRow(self.auto_start_break)
        form.addRow(self.auto_start_focus)
        form.addRow(self.sound_enabled)
        form.addRow(note("Changes apply from the next block; a block in progress keeps its length."))
        return page

    def _goals_page(self) -> QWidget:
        page = QWidget()
        self.daily_goal = spin(1, 30, " 🍅 a day")
        self.day_boxes = [QCheckBox(name) for name in DAY_NAMES]
        days = QHBoxLayout()
        for box in self.day_boxes:
            days.addWidget(box)

        form = QFormLayout(page)
        form.addRow("Daily goal", self.daily_goal)
        form.addRow("Working days", days)
        form.addRow(note("Used to work out which deadlines are at risk: only working days "
                         "count as time you can spend on tasks."))
        return page

    def _score_page(self) -> QWidget:
        page = QWidget()
        self.weight_boxes: dict[str, QSpinBox] = {}
        grid = QGridLayout()
        for i, (key, label) in enumerate(WEIGHT_LABELS):
            box = spin(0, 100, " pts")
            self.weight_boxes[key] = box
            column = 0 if i < 4 else 2
            row = i if i < 4 else i - 4
            grid.addWidget(QLabel(label), row, column)
            grid.addWidget(box, row, column + 1)
        grid.setColumnMinimumWidth(1, 90)

        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(lambda: self._show_weights(DEFAULT_WEIGHTS))

        layout = QVBoxLayout(page)
        layout.addWidget(note("Focus Score = priority points + due-date points + at-risk bonus. "
                              "The highest score is suggested first."))
        layout.addLayout(grid)
        layout.addWidget(reset, 0, Qt.AlignLeft)
        layout.addStretch()
        return page

    def _shortcut_page(self) -> QWidget:
        page = QWidget()
        self.hotkey_enabled = QCheckBox("Use a keyboard shortcut for Start / Pause")
        self.hotkey_input = QKeySequenceEdit()
        self.hotkey_input.setMaximumSequenceLength(1)
        self.hotkey_enabled.toggled.connect(self.hotkey_input.setEnabled)

        form = QFormLayout(page)
        form.addRow(self.hotkey_enabled)
        form.addRow("Shortcut", self.hotkey_input)
        form.addRow(note("Works from any app, even when Pomodoro Tracker is in the tray. "
                         "Click the box and press the keys, e.g. Ctrl+Alt+P. Use Ctrl and/or "
                         "Alt with a letter, number or F-key."))
        return page

    # ---------- load / save ----------

    def _load(self):
        db = self.db
        self.focus_minutes.setValue(db.get_int("focus_minutes"))
        self.break_minutes.setValue(db.get_int("break_minutes"))
        self.long_break_enabled.setChecked(db.get_bool("long_break_enabled"))
        self.long_break_minutes.setValue(db.get_int("long_break_minutes"))
        self.long_break_every.setValue(db.get_int("pomodoros_before_long_break"))
        self.long_break_minutes.setEnabled(self.long_break_enabled.isChecked())
        self.long_break_every.setEnabled(self.long_break_enabled.isChecked())
        self.auto_start_break.setChecked(db.get_bool("auto_start_break"))
        self.auto_start_focus.setChecked(db.get_bool("auto_start_focus"))
        self.sound_enabled.setChecked(db.get_bool("sound_enabled"))

        self.daily_goal.setValue(db.get_int("daily_goal"))
        working = db.get_working_days()
        for day, box in enumerate(self.day_boxes):
            box.setChecked(day in working)

        self._show_weights(ScoreWeights.from_dict(db.get_json("score_weights")))

        self.hotkey_enabled.setChecked(db.get_bool("hotkey_enabled"))
        self.hotkey_input.setKeySequence(QKeySequence(db.get_setting("hotkey")))
        self.hotkey_input.setEnabled(self.hotkey_enabled.isChecked())

    def _show_weights(self, weights: ScoreWeights):
        for key, value in weights.to_dict().items():
            self.weight_boxes[key].setValue(value)

    def _save(self):
        working = [day for day, box in enumerate(self.day_boxes) if box.isChecked()]
        if not working:
            QMessageBox.warning(self, "Working days", "Pick at least one working day.")
            return
        hotkey = self.hotkey_input.keySequence().toString(QKeySequence.PortableText)
        if self.hotkey_enabled.isChecked() and not hotkey:
            QMessageBox.warning(self, "Shortcut", "Press a key combination, or turn the "
                                                  "shortcut off.")
            return

        db = self.db
        db.set_setting("focus_minutes", self.focus_minutes.value())
        db.set_setting("break_minutes", self.break_minutes.value())
        db.set_setting("long_break_enabled", self.long_break_enabled.isChecked())
        db.set_setting("long_break_minutes", self.long_break_minutes.value())
        db.set_setting("pomodoros_before_long_break", self.long_break_every.value())
        db.set_setting("auto_start_break", self.auto_start_break.isChecked())
        db.set_setting("auto_start_focus", self.auto_start_focus.isChecked())
        db.set_setting("sound_enabled", self.sound_enabled.isChecked())
        db.set_setting("daily_goal", self.daily_goal.value())
        db.set_setting("working_days", ",".join(str(day) for day in working))
        weights = ScoreWeights(**{k: box.value() for k, box in self.weight_boxes.items()})
        db.set_setting("score_weights", json.dumps(weights.to_dict()))
        db.set_setting("hotkey_enabled", self.hotkey_enabled.isChecked())
        if hotkey:
            db.set_setting("hotkey", hotkey)
        self.accept()
