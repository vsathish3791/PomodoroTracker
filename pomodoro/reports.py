"""Numbers behind the Reports and Deadlines tabs, plus CSV export.

Everything here reads the database (or ranked tasks) and returns plain Python
data, so it can be tested without any UI.

Effort counts focus blocks only:
  * pomodoros = completed 25-minute blocks
  * minutes   = all focus time, including partial blocks you stopped early
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pomodoro.database import Database
from pomodoro.models import PRIORITIES, STATUSES
from pomodoro.priority import ScoredTask, capacity_until

UNASSIGNED = "Unassigned"


@dataclass
class EffortRow:
    label: str
    pomodoros: int
    minutes: float
    color: str | None = None


def _range_params(start: date, end: date) -> tuple[str, str]:
    """[start, end] as ISO datetimes for `start_time >= ? AND start_time < ?`."""
    begin = datetime.combine(start, datetime.min.time())
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return begin.isoformat(timespec="seconds"), finish.isoformat(timespec="seconds")


_FOCUS_IN_RANGE = """
    FROM sessions s
    LEFT JOIN tasks t ON t.id = s.task_id
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN projects p ON p.id = t.project_id
    WHERE s.kind = 'focus' AND s.start_time >= ? AND s.start_time < ?
"""


def effort_by(db: Database, start: date, end: date, group: str) -> list[EffortRow]:
    """Effort split by 'category', 'project', 'type' or 'priority'.

    Category and project rows are sorted biggest first; type and priority keep their
    natural order.
    Time not linked to a task (e.g. a deleted task) shows as 'Unassigned'.
    """
    # '~unassigned' = no task at all (deleted task); '~none' = task without a category.
    column = {
        "category": "CASE WHEN t.id IS NULL THEN '~unassigned' "
                    "WHEN c.id IS NULL THEN '~none' ELSE c.name END",
        "project": "CASE WHEN t.id IS NULL THEN '~unassigned' "
                   "WHEN p.id IS NULL THEN '~none' ELSE p.name END",
        "type": "CASE WHEN t.id IS NULL THEN '~unassigned' ELSE t.type END",
        "priority": "CASE WHEN t.id IS NULL THEN '~unassigned' ELSE t.priority END",
    }[group]
    rows = db.conn.execute(
        f"SELECT {column} AS key, MAX({'p' if group == 'project' else 'c'}.color) AS color, "
        f"       COALESCE(SUM(s.completed), 0) AS pomodoros, SUM(s.duration_min) AS minutes "
        f"{_FOCUS_IN_RANGE} GROUP BY key",
        _range_params(start, end),
    ).fetchall()

    types = {t["key"]: t for t in db.list_types()}
    result = []
    for row in rows:
        key, color = row["key"], None
        if key == "~unassigned":
            label = UNASSIGNED
        elif group in ("category", "project"):
            empty = "No category" if group == "category" else "No project"
            label, color = (empty, None) if key == "~none" else (key, row["color"])
        elif group == "type":
            known = types.get(key)
            label, color = (known["name"], known["color"]) if known else (key, None)
        else:
            label = PRIORITIES[int(key)]
        result.append(EffortRow(label, int(row["pomodoros"]), round(row["minutes"], 1), color))

    if group in ("category", "project"):
        result.sort(key=lambda r: (-r.minutes, r.label))
    elif group == "type":
        order = [t["name"] for t in types.values()]
        result.sort(key=lambda r: order.index(r.label) if r.label in order else len(order))
    else:
        order = list(PRIORITIES.values()) + [UNASSIGNED]
        result.sort(key=lambda r: order.index(r.label))
    return result


def daily_trend(db: Database, start: date, end: date) -> list[tuple[date, int, float]]:
    """(day, pomodoros, minutes) for every day in the range, including empty days."""
    rows = db.conn.execute(
        "SELECT substr(s.start_time, 1, 10) AS day, COALESCE(SUM(s.completed), 0) AS pomodoros, "
        f"      SUM(s.duration_min) AS minutes {_FOCUS_IN_RANGE} GROUP BY day",
        _range_params(start, end),
    ).fetchall()
    by_day = {row["day"]: (int(row["pomodoros"]), round(row["minutes"], 1)) for row in rows}
    days, day = [], start
    while day <= end:
        pomodoros, minutes = by_day.get(day.isoformat(), (0, 0.0))
        days.append((day, pomodoros, minutes))
        day += timedelta(days=1)
    return days


def summary(db: Database, start: date, end: date) -> dict:
    """Headline numbers for the range."""
    begin, finish = _range_params(start, end)
    focus = db.conn.execute(
        f"SELECT COALESCE(SUM(s.completed), 0) AS pomodoros, "
        f"       COALESCE(SUM(s.duration_min), 0) AS minutes {_FOCUS_IN_RANGE}",
        (begin, finish),
    ).fetchone()
    done = db.conn.execute(
        "SELECT due_date, completed_at FROM tasks "
        "WHERE status = 'done' AND completed_at >= ? AND completed_at < ?",
        (begin, finish),
    ).fetchall()
    on_time = sum(1 for t in done if t["due_date"] and t["completed_at"][:10] <= t["due_date"][:10])
    late = sum(1 for t in done if t["due_date"] and t["completed_at"][:10] > t["due_date"][:10])
    overrides = db.conn.execute(
        "SELECT COUNT(*) FROM overrides WHERE timestamp >= ? AND timestamp < ?",
        (begin, finish),
    ).fetchone()[0]
    days = (end - start).days + 1
    return {
        "pomodoros": int(focus["pomodoros"]),
        "minutes": round(focus["minutes"]),
        "daily_average": round(focus["pomodoros"] / days, 1),
        "tasks_done": len(done),
        "on_time": on_time,
        "late": late,
        "overrides": overrides,
    }


def estimate_accuracy(db: Database, start: date, end: date) -> list[dict]:
    """Done tasks (finished in range) that had an estimate: estimate vs actual pomodoros."""
    begin, finish = _range_params(start, end)
    tasks = [t for t in db.list_tasks("done")
             if t["estimate_pomodoros"] and begin <= (t["completed_at"] or "") < finish]
    return [{"title": t["title"], "estimate": t["estimate_pomodoros"], "actual": t["pomodoros"]}
            for t in tasks]


# ---------- deadline board ----------

BOARD_COLUMNS = ["Overdue", "Today", "This week", "Later", "No date"]


def deadline_board(ranked: list[ScoredTask], today: date) -> dict[str, list[ScoredTask]]:
    """Open tasks grouped by when they're due; each group keeps Focus Score order."""
    board = {name: [] for name in BOARD_COLUMNS}
    for scored in ranked:
        due = scored.due
        if due is None:
            board["No date"].append(scored)
        elif due < today:
            board["Overdue"].append(scored)
        elif due == today:
            board["Today"].append(scored)
        elif due <= today + timedelta(days=7):
            board["This week"].append(scored)
        else:
            board["Later"].append(scored)
    return board


@dataclass
class WorkloadDay:
    day: date
    needed: int              # pomodoros left on tasks due this day (today includes overdue)
    available: int           # what you can do that day at your daily goal
    cumulative_needed: int   # everything due up to and including this day
    cumulative_available: int

    @property
    def overloaded(self) -> bool:
        """More work due by this day than you can fit in by then."""
        return self.cumulative_needed > self.cumulative_available


def workload(ranked: list[ScoredTask], today: date, daily_goal: int, done_today: int,
             working_days: set[int], days: int = 7) -> list[WorkloadDay]:
    """Pomodoros needed vs available for each of the next `days` days."""
    result, cumulative = [], 0
    for offset in range(days):
        day = today + timedelta(days=offset)
        due_here = [s for s in ranked if s.due and
                    (s.due == day or (offset == 0 and s.due < today))]
        needed = sum(s.remaining or 0 for s in due_here)
        cumulative += needed
        if offset == 0:
            available = max(daily_goal - done_today, 0)
        else:
            available = daily_goal if day.weekday() in working_days else 0
        result.append(WorkloadDay(
            day, needed, available, cumulative,
            capacity_until(day, today, daily_goal, done_today, working_days)))
    return result


# ---------- CSV export ----------

def export_sessions_csv(db: Database, start: date, end: date, path: str) -> int:
    """Every focus and break block in the range, with its task details. Returns row count."""
    rows = db.conn.execute(
        "SELECT s.start_time, s.end_time, s.kind, s.duration_min, s.completed, "
        "       t.title, c.name AS category, t.type, t.priority, t.status, t.due_date "
        "FROM sessions s LEFT JOIN tasks t ON t.id = s.task_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE s.start_time >= ? AND s.start_time < ? ORDER BY s.start_time",
        _range_params(start, end),
    ).fetchall()
    type_names = db.type_names()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # BOM so Excel reads UTF-8
        writer = csv.writer(f)
        writer.writerow(["Date", "Start", "End", "Kind", "Minutes", "Full pomodoro",
                         "Task", "Category", "Type", "Priority", "Task status", "Due date"])
        for r in rows:
            writer.writerow([
                r["start_time"][:10], r["start_time"][11:16], r["end_time"][11:16],
                r["kind"].replace("_", " "), r["duration_min"], "Yes" if r["completed"] else "No",
                r["title"] or "", r["category"] or "",
                type_names.get(r["type"], r["type"] or ""), PRIORITIES.get(r["priority"], ""),
                STATUSES.get(r["status"], ""), r["due_date"] or "",
            ])
    return len(rows)


def export_tasks_csv(db: Database, path: str) -> int:
    """All tasks with their totals. Returns row count."""
    tasks = db.list_tasks("all")
    type_names = db.type_names()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Task", "Category", "Type", "Priority", "Due date", "Estimate",
                         "Pomodoros", "Focus minutes", "Status", "Created", "Completed", "Notes"])
        for t in tasks:
            writer.writerow([
                t["title"], t["category"] or "", type_names.get(t["type"], t["type"]),
                PRIORITIES[t["priority"]],
                t["due_date"] or "", t["estimate_pomodoros"] or "", t["pomodoros"],
                round(t["focus_minutes"], 1), STATUSES[t["status"]], t["created_at"][:10],
                (t["completed_at"] or "")[:10], t["notes"] or "",
            ])
    return len(tasks)
