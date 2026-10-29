"""The Day Log: the facts of one day, for your journal.

Built from the app's data (tasks finished and worked on, today's focus, habits and
routines, interruptions, stretch and practice) plus an inferred Energy signal. It's
copied as text (Close the day -> Copy day log) or sent to a Notion "Day Log" database,
where your journaling assistant reads it. Only task titles and numbers - never notes.

Plain Python on top of the database.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pomodoro import planning, reports
from pomodoro.database import Database
from pomodoro.energy import ENERGY, DayFacts, EnergyThresholds, infer_energy
from pomodoro.lists import remaining_estimate
from pomodoro.models import STRETCH


@dataclass
class TaskLine:
    title: str
    project: str | None
    pomodoros: int          # completed that day
    minutes: int            # focus minutes that day (incl. partial blocks)
    left: int | None = None  # pomodoros still to do (worked-on tasks with an estimate)

    def text(self) -> str:
        parts = [self.title]
        if self.project:
            parts.append(f"({self.project})")
        if self.pomodoros or self.minutes:
            parts.append(f"– {self.pomodoros} 🍅, {self.minutes} min")
        if self.left:
            parts.append(f"· {self.left} 🍅 left")
        return " ".join(parts)


@dataclass
class DayLog:
    day: date
    goal: int
    pomodoros: int
    focus_minutes: int
    energy: str                                   # ENERGY key
    energy_reason: str
    completed: list[TaskLine] = field(default_factory=list)
    worked_on: list[TaskLine] = field(default_factory=list)
    focus: list[tuple[str, bool]] = field(default_factory=list)    # (title, done)
    missed: list[str] = field(default_factory=list)                # repeating tasks missed
    habits: tuple[int, int] = (0, 0)
    routines: tuple[int, int] = (0, 0)
    stopped: int = 0
    minutes_lost: int = 0
    distractions: int = 0
    causes: list[tuple[str, int]] = field(default_factory=list)    # (cause, count)
    stretch: dict[str, int] = field(default_factory=dict)          # STRETCH key -> count
    practice: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{self.day:%a %d %b %Y} – Day log"

    @property
    def focus_text(self) -> str:
        if not self.focus:
            return "Nothing planned"
        return f"{len(self.focus)} planned · {sum(done for _, done in self.focus)} done"

    def interruptions_text(self, with_cause: bool = True) -> str:
        parts = []
        if self.stopped:
            parts.append(f"{self.stopped} stopped early ({self.minutes_lost} min lost)")
        if self.distractions:
            parts.append(f"{self.distractions} distraction(s)")
        if with_cause and self.causes:
            parts.append(f"top cause: {self.causes[0][0]}")
        return " · ".join(parts) or "None"

    def sections(self) -> list[tuple[str, list[str]]]:
        """The page body: (heading, bullet lines). Empty sections are left out."""
        rows = [
            ("✅ Completed", [t.text() for t in self.completed]),
            ("🔄 Worked on, not finished", [t.text() for t in self.worked_on]),
            ("🎯 Today's focus", [("✓ " if done else "○ not done – ") + title
                                 for title, done in self.focus]),
            ("↪ Repeating tasks missed", self.missed),
            ("⚡ Interruptions & distractions",
             [self.interruptions_text(with_cause=False)]
             + [f"Cause – {cause}: {n}" for cause, n in self.causes]
             if self.stopped or self.distractions else []),
            ("💪 Stretch & practice",
             ([" · ".join(f"{STRETCH[k]} {n}" for k, n in self.stretch.items())]
              if self.stretch else []) + self.practice),
        ]
        return [(heading, lines) for heading, lines in rows if lines]

    def markdown(self) -> str:
        hours, mins = divmod(self.focus_minutes, 60)
        lines = [f"# {self.title}", "",
                 f"{self.pomodoros}/{self.goal} 🍅 · {hours} h {mins} min focus · "
                 f"Energy: {ENERGY[self.energy]} ({self.energy_reason})",
                 f"Today's focus: {self.focus_text} · Habits {self.habits[0]}/{self.habits[1]}"
                 f" · Routines {self.routines[0]}/{self.routines[1]}", ""]
        for heading, items in self.sections():
            lines.append(f"## {heading}")
            lines += [f"- {item}" for item in items]
            lines.append("")
        if not self.sections():
            lines.append("No tracked work this day.")
        return "\n".join(lines).rstrip() + "\n"


def _per_task(db: Database, day: date) -> dict[int, tuple[int, int]]:
    """task id -> (pomodoros completed, focus minutes) for the day."""
    start = datetime.combine(day, datetime.min.time())
    rows = db.conn.execute(
        "SELECT task_id, COALESCE(SUM(completed), 0), COALESCE(SUM(duration_min), 0) "
        "FROM sessions WHERE kind = 'focus' AND task_id IS NOT NULL "
        "AND start_time >= ? AND start_time < ? GROUP BY task_id",
        (start.isoformat(timespec="seconds"),
         (start + timedelta(days=1)).isoformat(timespec="seconds"))).fetchall()
    return {r[0]: (int(r[1]), round(r[2])) for r in rows}


def build_day_log(db: Database, day: date,
                  limits: EnergyThresholds | None = None) -> DayLog:
    iso = day.isoformat()
    summary = planning.day_summary(db, day)
    per_task = _per_task(db, day)
    tasks = {t["id"]: t for t in db.list_tasks("all")}

    completed, worked_on = [], []
    finished_ids = [t["id"] for t in tasks.values()
                    if t["status"] == "done" and (t["completed_at"] or "")[:10] == iso]
    finished_ids.sort(key=lambda i: tasks[i]["completed_at"])
    for task_id in finished_ids:
        pomos, minutes = per_task.get(task_id, (0, 0))
        completed.append(TaskLine(tasks[task_id]["title"], tasks[task_id]["project"],
                                  pomos, minutes))
    for task_id, (pomos, minutes) in sorted(per_task.items(), key=lambda kv: -kv[1][1]):
        task = tasks.get(task_id)
        if task is None or task_id in finished_ids:
            continue
        left = remaining_estimate(task) if task["estimate_pomodoros"] else None
        worked_on.append(TaskLine(task["title"], task["project"], pomos, minutes, left))

    _routine, planned = planning.day_tasks(db, day)
    focus = [(t["title"], t["status"] == "done") for t in planned]
    missed = [t["title"] for t in tasks.values()
              if t["recurrence_id"] and t["occurrence_date"] == iso and t["status"] == "missed"]
    rows, events = reports.anomaly_pareto(db, day, day)
    stretch: dict[str, int] = {}
    for task_id in finished_ids:
        if tasks[task_id]["stretch"]:
            stretch[tasks[task_id]["stretch"]] = stretch.get(tasks[task_id]["stretch"], 0) + 1
    practice = []
    start = datetime.combine(day, datetime.min.time()).isoformat(timespec="seconds")
    end = datetime.combine(day + timedelta(days=1),
                           datetime.min.time()).isoformat(timespec="seconds")
    for skill, target, difficulty in db.conn.execute(
            "SELECT practice_skill, practice_target, difficulty FROM sessions "
            "WHERE practice_skill IS NOT NULL AND start_time >= ? AND start_time < ? "
            "ORDER BY start_time", (start, end)):
        practice.append(f"Practice: {skill}" + (f" – {target}" if target else "")
                        + (f" (difficulty {difficulty}/5)" if difficulty else ""))

    goal = db.get_int("daily_goal")
    facts = DayFacts(
        summary.pomodoros, goal, summary.stopped, summary.minutes_lost, summary.distractions,
        stretch.get("panic", 0), day.weekday() in db.get_working_days(),
        used=bool(per_task or finished_ids or events["stopped"] or events["distraction"]))
    energy, reason = infer_energy(facts, limits or EnergyThresholds.from_dict(
        db.get_json("energy_thresholds")))

    return DayLog(
        day, goal, summary.pomodoros, summary.focus_minutes, energy, reason, completed,
        worked_on, focus, missed,
        summary.habits, summary.routines, summary.stopped, summary.minutes_lost,
        summary.distractions, [(r.reason, r.count) for r in rows], stretch, practice)
