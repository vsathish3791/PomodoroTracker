"""The daily and weekly cycle: plan the day, close the day, review the week.

  * Morning   - plan: today's routines/habits are automatic; pick a few focus tasks
                and check them against what your daily goal allows.
  * Evening   - check: today's numbers, move unfinished planned tasks, plan tomorrow,
                and copy a short summary for your Notion Journal ("What happened?").
  * Weekly    - review (Falconi's three-generation report):
                1. Planned  2. Done & results  3. Problems & next actions.

Plain Python on top of the database.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from pomodoro import goals, reports
from pomodoro.database import Database
from pomodoro.lists import remaining_estimate
from pomodoro.models import NATURES


# ---------- the day ----------

def day_tasks(db: Database, day: date) -> tuple[list[dict], list[dict]]:
    """(recurring occurrences for the day, tasks planned for the day) - both incl. done."""
    iso = day.isoformat()
    every = db.list_tasks("all")
    routine = [t for t in every if t["recurrence_id"] and t["occurrence_date"] == iso
               and t["status"] != "missed"]
    routine.sort(key=lambda t: (t["cue_time"] or "99:99", t["title"].lower()))
    planned = [t for t in every if t["planned_date"] == iso and not t["recurrence_id"]
               and (t["status"] != "done" or (t["completed_at"] or "")[:10] == iso)]
    return routine, planned


@dataclass
class Capacity:
    goal: int
    done: int            # pomodoros already done today
    routine: int         # estimated pomodoros still to do on today's routines/habits
    planned: int         # estimated pomodoros still to do on planned tasks

    @property
    def available(self) -> int:
        return max(self.goal - self.done, 0)

    @property
    def needed(self) -> int:
        return self.routine + self.planned

    @property
    def over(self) -> int:
        return max(self.needed - self.available, 0)


def capacity(db: Database, day: date) -> Capacity:
    routine, planned = day_tasks(db, day)
    open_ = lambda tasks: [t for t in tasks if t["status"] not in ("done", "missed")]
    done = db.day_stats(day)["pomodoros"]
    return Capacity(db.get_int("daily_goal"), done,
                    sum(remaining_estimate(t) for t in open_(routine)),
                    sum(remaining_estimate(t) for t in open_(planned)))


@dataclass
class DaySummary:
    day: date
    pomodoros: int
    focus_minutes: int
    finished: list[str]
    habits: tuple[int, int]          # done, scheduled
    routines: tuple[int, int]
    stopped: int
    minutes_lost: int
    distractions: int
    top_cause: str | None
    unfinished_planned: list[dict] = field(default_factory=list)

    def journal_text(self) -> str:
        """A short "What happened?" for the Notion Journal: numbers only."""
        hours, mins = divmod(self.focus_minutes, 60)
        focus = f"{hours} h {mins} min" if hours else f"{mins} min"
        parts = [f"Pomodoro Tracker – {self.day:%a %d %b}: {self.pomodoros} pomodoros "
                 f"({focus} focus)"]
        if self.finished:
            parts.append(f"{len(self.finished)} task(s) done: " + "; ".join(self.finished))
        if self.habits[1]:
            parts.append(f"Habits {self.habits[0]}/{self.habits[1]}")
        if self.routines[1]:
            parts.append(f"Routines {self.routines[0]}/{self.routines[1]}")
        if self.stopped or self.distractions:
            parts.append(f"Interruptions: {self.stopped} stopped early "
                         f"({self.minutes_lost} min lost), {self.distractions} distraction(s)"
                         + (f" – top cause: {self.top_cause}" if self.top_cause else ""))
        if self.unfinished_planned:
            parts.append("Not finished: " + "; ".join(t["title"] for t in self.unfinished_planned))
        return ". ".join(parts) + "."


def day_summary(db: Database, day: date) -> DaySummary:
    iso = day.isoformat()
    stats = db.day_stats(day)
    finished = [r[0] for r in db.conn.execute(
        "SELECT title FROM tasks WHERE status = 'done' AND substr(completed_at, 1, 10) = ? "
        "ORDER BY completed_at", (iso,))]

    def rate(nature):
        row = db.conn.execute(
            "SELECT SUM(status = 'done'), COUNT(*) FROM tasks WHERE recurrence_id IS NOT NULL "
            "AND nature = ? AND occurrence_date = ?", (nature, iso)).fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    rows, summary = reports.anomaly_pareto(db, day, day)
    _routine, planned = day_tasks(db, day)
    return DaySummary(
        day, stats["pomodoros"], stats["focus_minutes"], finished, rate("habit"),
        rate("routine"), summary["stopped"], summary["minutes_lost"], summary["distraction"],
        rows[0].reason if rows else None,
        [t for t in planned if t["status"] not in ("done", "missed")])


def move_to(db: Database, task_ids: list[int], day: date):
    for task_id in task_ids:
        db.plan_task(task_id, day)


# ---------- the week (three-generation report) ----------

@dataclass
class WeekReport:
    start: date
    end: date
    planned: list[str]          # 1. what was planned
    done: list[str]             # 2. what was done and the results
    problems: list[str]         # 3. problems ...
    next_actions: list[str]     # ... and proposals for next week

    def markdown(self) -> str:
        lines = [f"# Weekly review – {self.start:%d %b} to {self.end:%d %b %Y}", ""]
        for title, items in (("1. Planned", self.planned),
                             ("2. Done and results", self.done),
                             ("3. Problems", self.problems),
                             ("Next actions", self.next_actions)):
            lines.append(f"## {title}")
            lines += [f"- {item}" for item in items] or ["- (nothing)"]
            lines.append("")
        return "\n".join(lines)


def week_report(db: Database, monday: date, today: date | None = None) -> WeekReport:
    today = today or date.today()
    start, end = monday, min(monday + timedelta(days=6), today)
    working = db.get_working_days()

    # 1. Planned
    planned = []
    for goal in db.list_goals():
        scope = goals.scope_label(db, (goal["scope_kind"], goal["scope_value"]))
        planned.append(f"Goal: {goal['title']} ({scope}) – "
                       + (f"{goal['value']} 🍅 a week" if goal["kind"] == "weekly"
                          else f"{goal['value']} 🍅 by {goal['deadline']}"))
    targets = goals.split_targets(db)
    planned.append("Time split target: " + ", ".join(
        f"{NATURES[k]} {v}%" for k, v in targets.items()))
    planned_tasks = db.conn.execute(
        "SELECT COUNT(*), SUM(status = 'done') FROM tasks WHERE planned_date >= ? "
        "AND planned_date <= ? AND recurrence_id IS NULL",
        (start.isoformat(), end.isoformat())).fetchone()
    if planned_tasks[0]:
        planned.append(f"{planned_tasks[0]} focus task(s) planned on day plans")
    planned.append(f"Daily goal: {db.get_int('daily_goal')} 🍅 "
                   f"({goals.working_days_between(start, end, working)} working days)")

    # 2. Done and results
    total = goals.pomodoros(db, start, end)
    minutes = sum(db.day_stats(start + timedelta(days=n))["focus_minutes"]
                  for n in range((end - start).days + 1))
    done = [f"{total} pomodoros, {minutes // 60} h {minutes % 60} min of focus"]
    shares, _unset = goals.nature_split(db, start, end)
    if any(shares.values()):
        done.append("Time split: " + ", ".join(
            f"{NATURES[k]} {shares[k]:.0%} (target {targets[k]}%)" for k in NATURES))
    finished = [r[0] for r in db.conn.execute(
        "SELECT title FROM tasks WHERE status = 'done' AND recurrence_id IS NULL "
        "AND substr(completed_at, 1, 10) >= ? AND substr(completed_at, 1, 10) <= ?",
        (start.isoformat(), end.isoformat()))]
    if finished:
        done.append(f"{len(finished)} task(s) finished: " + "; ".join(finished))
    if planned_tasks[0]:
        done.append(f"Planned tasks done: {planned_tasks[1] or 0} of {planned_tasks[0]}")
    for row in reports.recurring_summary(db, start, end):
        rate = f"{row['rate']:.0%}" if row["rate"] is not None else "–"
        done.append(f"{NATURES.get(row['nature'], 'Recurring')} “{row['title']}”: "
                    f"{row['done']} done, {row['missed']} missed ({rate})")
    for goal in db.list_goals():
        progress = goals.goal_progress(db, goal, end)
        done.append(f"Goal “{goal['title']}”: {progress.text} – "
                    f"{goals.STATUS_LABELS[progress.status]}")

    # 3. Problems and next actions
    problems, next_actions = [], []
    rows, summary = reports.anomaly_pareto(db, start, end)
    if summary["stopped"] or summary["distraction"]:
        problems.append(f"{summary['stopped']} pomodoro(s) stopped early "
                        f"({summary['minutes_lost']} min lost), "
                        f"{summary['distraction']} distraction(s)")
    for row in rows[:3]:
        problems.append(f"Cause: {row.reason} – {row.count} time(s), {row.share:.0%}")
    if rows:
        next_actions.append(f"Countermeasure for the top cause “{rows[0].reason}”")
    if summary["unlabelled"]:
        next_actions.append(f"Give reasons to {summary['unlabelled']} unlabelled event(s)")
    for goal in db.list_goals():
        progress = goals.goal_progress(db, goal, end)
        if progress.status in ("warning", "critical"):
            problems.append(f"Goal behind: {goal['title']} ({progress.text})")
            next_actions.append(f"Plan pomodoros for “{goal['title']}” early next week")
    for row in reports.recurring_summary(db, start, end):
        if row["missed"]:
            problems.append(f"Missed {row['missed']}× “{row['title']}”")
    carry = db.conn.execute(
        "SELECT title FROM tasks WHERE planned_date >= ? AND planned_date <= ? "
        "AND status NOT IN ('done', 'missed') AND recurrence_id IS NULL",
        (start.isoformat(), end.isoformat())).fetchall()
    if carry:
        problems.append(f"{len(carry)} planned task(s) not finished: "
                        + "; ".join(r[0] for r in carry))
        next_actions.append("Re-plan the unfinished tasks (or drop them)")
    overdue = db.conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('done', 'missed') "
        "AND due_date < ?", (today.isoformat(),)).fetchone()[0]
    if overdue:
        problems.append(f"{overdue} overdue task(s)")
        next_actions.append("Review overdue tasks: re-date, finish or drop")
    if any(shares.values()) and goals.split_status(shares["improvement"],
                                                   targets["improvement"]) != "good":
        next_actions.append(f"Move time towards improvement (now {shares['improvement']:.0%}, "
                            f"target {targets['improvement']}%)")
    return WeekReport(start, end, planned, done, problems, next_actions)


def last_monday(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=today.weekday())
