"""Goals, the control panel and learned estimates.

Falconi: a goal = objective + value + deadline, and results (control items) are
tracked together with the causes that drive them (verification items).
Clear: systems over goals - the weekly rhythm matters more than the end target.

Two kinds of goal:
  * weekly  - "at least N pomodoros a week on <scope>"   (a rhythm / lead measure)
  * by_date - "N pomodoros on <scope> by <date>"         (a target, with a forecast)
A scope is all work, a project, a category or a kind of work.

Statuses: 'good' (on track), 'warning' (a bit behind), 'critical' (off track),
'done' (target reached), 'none' (not enough data yet).
"""

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pomodoro.database import Database
from pomodoro.models import NATURES

STATUS_LABELS = {"good": "● On track", "warning": "▲ Behind", "critical": "■ Off track",
                 "done": "✓ Reached", "none": "– No data yet"}
DEFAULT_SPLIT = {"routine": 50, "habit": 20, "improvement": 30}


# ---------- counting pomodoros ----------

def _scope_sql(scope: tuple) -> tuple[str, list]:
    kind, value = scope
    if kind == "all":
        return "", []
    column = {"project": "t.project_id", "category": "t.category_id", "nature": "t.nature"}[kind]
    if kind in ("project", "category"):
        value = int(value)                 # stored as text in the goals table
    return f" AND {column} = ?", [value]


def pomodoros(db: Database, start: date, end: date, scope: tuple = ("all", None)) -> int:
    """Completed pomodoros on days start..end (inclusive) within a scope."""
    extra, params = _scope_sql(scope)
    begin = datetime.combine(start, datetime.min.time()).isoformat(timespec="seconds")
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time()).isoformat(
        timespec="seconds")
    row = db.conn.execute(
        "SELECT COALESCE(SUM(s.completed), 0) FROM sessions s "
        "LEFT JOIN tasks t ON t.id = s.task_id "
        f"WHERE s.kind = 'focus' AND s.start_time >= ? AND s.start_time < ?{extra}",
        [begin, finish, *params]).fetchone()
    return int(row[0])


def working_days_between(start: date, end: date, working_days: set[int]) -> int:
    days, day = 0, start
    while day <= end:
        days += day.weekday() in working_days
        day += timedelta(days=1)
    return days


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def scope_label(db: Database, scope: tuple) -> str:
    kind, value = scope
    if kind == "all":
        return "All work"
    if kind == "nature":
        return NATURES.get(value, value)
    table = {"project": "projects", "category": "categories"}[kind]
    row = db.conn.execute(f"SELECT name FROM {table} WHERE id = ?", (int(value),)).fetchone()
    return row[0] if row else "(deleted)"


# ---------- goals ----------

@dataclass
class GoalProgress:
    done: int
    target: int
    status: str
    text: str            # e.g. "6 / 10 🍅 this week"
    detail: str          # e.g. "Expected 5 by today" / "At this pace: reached 24 Nov"
    fraction: float      # 0..1 for a progress bar


def _ratio_status(actual: float, expected: float) -> str:
    if expected <= 0:
        return "good"
    ratio = actual / expected
    return "good" if ratio >= 1 else "warning" if ratio >= 0.7 else "critical"


def goal_progress(db: Database, goal: dict, today: date | None = None,
                  working_days: set[int] | None = None) -> GoalProgress:
    today = today or date.today()
    working_days = db.get_working_days() if working_days is None else working_days
    scope = (goal["scope_kind"], goal["scope_value"])
    target = goal["value"]

    if goal["kind"] == "weekly":
        start = week_start(today)
        done = pomodoros(db, start, today, scope)
        week_days = working_days_between(start, start + timedelta(days=6), working_days) or 7
        elapsed = working_days_between(start, today, working_days)
        expected = target * elapsed / week_days
        status = "done" if done >= target else _ratio_status(done, expected)
        return GoalProgress(done, target, status, f"{done} / {target} 🍅 this week",
                            f"Expected about {expected:.0f} by today" if done < target
                            else "Weekly target reached", min(done / target, 1) if target else 1)

    # by_date: count from the goal's start until today
    start = date.fromisoformat(goal["start_date"])
    deadline = date.fromisoformat(goal["deadline"])
    done = pomodoros(db, start, today, scope)
    fraction = min(done / target, 1) if target else 1
    if done >= target:
        return GoalProgress(done, target, "done", f"{done} / {target} 🍅",
                            "Target reached", 1)
    if today > deadline:
        return GoalProgress(done, target, "critical", f"{done} / {target} 🍅",
                            f"Deadline passed ({deadline:%d %b}) – {target - done} 🍅 short",
                            fraction)
    # Pace over the last 14 days (or since the start, if more recent)
    window_start = max(start, today - timedelta(days=13))
    recent = pomodoros(db, window_start, today, scope)
    recent_days = working_days_between(window_start, today, working_days) or 1
    pace = recent / recent_days                               # pomodoros per working day
    days_left = working_days_between(today, deadline, working_days) or 1
    needed_pace = (target - done) / days_left
    if pace <= 0:
        detail = f"Needs {needed_pace:.1f} 🍅 per working day – no recent progress"
        status = "critical" if done == 0 and (deadline - today).days < 14 else "warning"
    else:
        days_to_finish = (target - done) / pace
        finish, counted = today, 0
        while counted < days_to_finish:
            finish += timedelta(days=1)
            counted += finish.weekday() in working_days
        detail = (f"At this pace: reached {finish:%d %b}"
                  + (" (after the deadline)" if finish > deadline else ""))
        status = _ratio_status(pace, needed_pace)
    return GoalProgress(done, target, status, f"{done} / {target} 🍅 by {deadline:%d %b}",
                        detail, fraction)


# ---------- time split (Routine / Habit / Improvement) ----------

def nature_split(db: Database, start: date, end: date) -> tuple[dict[str, float], int]:
    """Share of pomodoros per kind of work in the period, and pomodoros without a kind."""
    counts = {key: pomodoros(db, start, end, ("nature", key)) for key in NATURES}
    total_set = sum(counts.values())
    unset = pomodoros(db, start, end) - total_set
    shares = {k: (v / total_set if total_set else 0.0) for k, v in counts.items()}
    return shares, unset


def split_status(actual_share: float, target_percent: float) -> str:
    gap = abs(actual_share * 100 - target_percent)
    return "good" if gap <= 5 else "warning" if gap <= 15 else "critical"


# ---------- control panel ----------

@dataclass
class ControlItem:
    name: str
    group: str        # 'lead' (your system) or 'lag' (results)
    value: str
    target: str
    status: str
    hint: str


def _occurrence_rate(db: Database, nature: str, start: date, end: date) -> tuple[int, int]:
    row = db.conn.execute(
        "SELECT SUM(status = 'done'), SUM(status IN ('done', 'missed')) FROM tasks "
        "WHERE recurrence_id IS NOT NULL AND nature = ? AND occurrence_date >= ? "
        "AND occurrence_date <= ?", (nature, start.isoformat(), end.isoformat())).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def control_items(db: Database, today: date | None = None,
                  working_days: set[int] | None = None) -> list[ControlItem]:
    today = today or date.today()
    working_days = db.get_working_days() if working_days is None else working_days
    items = []

    # --- lead measures: the system ---
    week_ago = today - timedelta(days=6)
    days = working_days_between(week_ago, today, working_days) or 1
    per_day = pomodoros(db, week_ago, today) / days
    goal = db.get_int("daily_goal")
    items.append(ControlItem(
        "Focus per working day", "lead", f"{per_day:.1f} 🍅", f"goal {goal}",
        _ratio_status(per_day, goal), "Average over the last 7 days."))

    for nature, name, target in (("habit", "Habit consistency", 0.8),
                                 ("routine", "Routine done", 0.9)):
        done, closed = _occurrence_rate(db, nature, today - timedelta(days=13), today)
        if closed:
            rate = done / closed
            status = "good" if rate >= target else "warning" if rate >= target - 0.2 \
                else "critical"
            items.append(ControlItem(name, "lead", f"{rate:.0%}", f"target {target:.0%}",
                                     status, f"{done} of {closed} in the last 14 days."))
        else:
            items.append(ControlItem(name, "lead", "–", f"target {target:.0%}", "none",
                                     f"No {nature} occurrences in the last 14 days."))

    sessions = pomodoros(db, week_ago, today)
    distractions = db.conn.execute(
        "SELECT COUNT(*) FROM anomalies WHERE kind = 'distraction' AND happened_at >= ?",
        (week_ago.isoformat(),)).fetchone()[0]
    if sessions:
        rate = distractions / sessions
        items.append(ControlItem(
            "Distractions per pomodoro", "lead", f"{rate:.1f}", "target ≤ 0.5",
            "good" if rate <= 0.5 else "warning" if rate <= 1 else "critical",
            f"{distractions} distractions in {sessions} pomodoros (7 days)."))
    else:
        items.append(ControlItem("Distractions per pomodoro", "lead", "–", "target ≤ 0.5",
                                 "none", "No pomodoros in the last 7 days."))

    # --- results ---
    month_ago = today - timedelta(days=29)
    finished = db.conn.execute(
        "SELECT due_date, completed_at FROM tasks WHERE status = 'done' AND due_date IS NOT NULL "
        "AND completed_at >= ?", (month_ago.isoformat(),)).fetchall()
    if finished:
        on_time = sum(1 for t in finished if t[1][:10] <= t[0][:10]) / len(finished)
        items.append(ControlItem(
            "Finished on time", "lag", f"{on_time:.0%}", "target 80%",
            "good" if on_time >= 0.8 else "warning" if on_time >= 0.6 else "critical",
            f"{len(finished)} tasks with a due date finished in the last 30 days."))
    else:
        items.append(ControlItem("Finished on time", "lag", "–", "target 80%", "none",
                                 "No tasks with a due date finished in the last 30 days."))

    estimated = [t for t in db.list_tasks("done")
                 if t["estimate_pomodoros"] and (t["completed_at"] or "") >= month_ago.isoformat()]
    if estimated:
        close = sum(1 for t in estimated
                    if abs(t["pomodoros"] - t["estimate_pomodoros"])
                    <= max(1, 0.25 * t["estimate_pomodoros"])) / len(estimated)
        items.append(ControlItem(
            "Estimate accuracy", "lag", f"{close:.0%}", "target 70%",
            "good" if close >= 0.7 else "warning" if close >= 0.5 else "critical",
            "Finished tasks within ±1 🍅 (or ±25%) of their estimate, last 30 days."))
    else:
        items.append(ControlItem("Estimate accuracy", "lag", "–", "target 70%", "none",
                                 "No finished tasks with an estimate in the last 30 days."))

    shares, _unset = nature_split(db, week_start(today), today)
    targets = split_targets(db)
    if any(shares.values()):
        share = shares["improvement"]
        items.append(ControlItem(
            "Improvement share", "lag", f"{share:.0%}", f"target {targets['improvement']}%",
            split_status(share, targets["improvement"]),
            "Share of this week's pomodoros spent moving things forward."))
    else:
        items.append(ControlItem("Improvement share", "lag", "–",
                                 f"target {targets['improvement']}%", "none",
                                 "No pomodoros with a kind of work this week."))
    return items


def split_targets(db: Database) -> dict[str, int]:
    saved = db.get_json("nature_targets")
    targets = {k: int(saved.get(k, v)) for k, v in DEFAULT_SPLIT.items()}
    return targets


# ---------- learned estimates ----------

def suggest_estimate(db: Database, category_id: int | None, type_key: str | None,
                     min_samples: int = 3) -> tuple[int, int, str] | None:
    """(suggested pomodoros, how many finished tasks it's based on, what they share).

    Uses the median actual pomodoros of finished tasks in the same category, else of
    the same type. Only tasks that took at least one pomodoro count.
    """
    candidates = []
    if category_id is not None:
        candidates.append(("category_id", category_id))
    if type_key:
        candidates.append(("type", type_key))
    for column, value in candidates:
        rows = [t for t in db.list_tasks("done") if t[column] == value and t["pomodoros"] > 0
                and not t["recurrence_id"]]
        if len(rows) >= min_samples:
            median = round(statistics.median(t["pomodoros"] for t in rows))
            label = rows[0]["category"] if column == "category_id" else \
                db.type_names().get(value, value)
            return max(median, 1), len(rows), label
    return None
