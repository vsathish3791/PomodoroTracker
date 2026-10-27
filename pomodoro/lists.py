"""What each list in the To-Do view contains, and its summary numbers.

Smart lists (by due date):
  Today      - open tasks due today or overdue
  Tomorrow   - open tasks due tomorrow
  This week  - open tasks due by Sunday (including overdue)
  Planned    - open tasks with any due date
  Tasks      - every open task
  Completed  - finished tasks, newest first
Plus one list per project.

Plain Python on top of the database, so it can be tested without the UI.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pomodoro.database import Database

SMART_LISTS = [
    ("today", "Today"),
    ("tomorrow", "Tomorrow"),
    ("week", "This Week"),
    ("planned", "Planned"),
    ("recurring", "Recurring"),
    ("completed", "Completed"),
    ("all", "Tasks"),
]
SMART_NAMES = dict(SMART_LISTS)

SORTS = [
    ("score", "Focus Score"),
    ("due", "Due date"),
    ("priority", "Priority"),
    ("title", "Name"),
    ("created", "Newest first"),
]


def _due(task: dict) -> date | None:
    return date.fromisoformat(task["due_date"][:10]) if task.get("due_date") else None


def end_of_week(today: date) -> date:
    return today + timedelta(days=6 - today.weekday())     # Sunday


def matches(view: str, task: dict, today: date) -> bool:
    """Does this task belong in a smart list (ignoring done/open)?"""
    due = _due(task)
    if view in ("all", "completed"):
        return True
    if view == "recurring":
        return task.get("recurrence_id") is not None
    planned = task.get("planned_date")
    if view == "today" and planned == today.isoformat():
        return True                       # on today's plan, whatever its due date
    if view == "tomorrow" and planned == (today + timedelta(days=1)).isoformat():
        return True
    if due is None:
        return False
    if view == "today":
        return due <= today
    if view == "tomorrow":
        return due == today + timedelta(days=1)
    if view == "week":
        return due <= end_of_week(today)
    return view == "planned"


def completed_on(task: dict, day: date) -> bool:
    return bool(task.get("completed_at")) and task["completed_at"][:10] == day.isoformat()


@dataclass
class ListContent:
    open_tasks: list[dict]
    done_tasks: list[dict]     # finished today (for Completed: all finished tasks)


def list_content(db: Database, view: str, today: date | None = None) -> ListContent:
    """view is a smart list key, or 'project:<id>'."""
    today = today or date.today()
    if view.startswith("project:"):
        project_id = int(view.split(":")[1])
        open_tasks = db.list_tasks("open", project_id=project_id)
        done = [t for t in db.list_tasks("done", project_id=project_id)
                if completed_on(t, today)]
        return ListContent(open_tasks, done)
    if view == "completed":
        return ListContent([], db.list_tasks("done"))
    open_tasks = [t for t in db.list_tasks("open") if matches(view, t, today)]
    done = [t for t in db.list_tasks("done") if completed_on(t, today) and matches(view, t, today)]
    return ListContent(open_tasks, done)


def coming_up(db: Database, view: str, today: date | None = None) -> list[dict]:
    """Preview of recurring occurrences not created yet, for Tomorrow and This Week."""
    today = today or date.today()
    if view == "tomorrow":
        day = today + timedelta(days=1)
        return db.upcoming_occurrences(day, day, today)
    if view == "week":
        return db.upcoming_occurrences(today + timedelta(days=1), end_of_week(today), today)
    return []


def remaining_estimate(task: dict) -> int:
    if not task.get("estimate_pomodoros"):
        return 0
    return max(task["estimate_pomodoros"] - task.get("pomodoros", 0), 0)


@dataclass
class ListStats:
    estimated_minutes: int     # estimated pomodoros still to do x focus length
    to_complete: int
    elapsed_minutes: int       # focus time logged today on tasks in this list
    completed: int             # tasks finished today in this list


def list_stats(db: Database, content: ListContent, focus_minutes: int,
               today: date | None = None) -> ListStats:
    today = today or date.today()
    minutes_today = db.focus_minutes_by_task(today)
    tasks = content.open_tasks + content.done_tasks
    done_today = [t for t in content.done_tasks if completed_on(t, today)]
    return ListStats(
        estimated_minutes=sum(remaining_estimate(t) for t in content.open_tasks) * focus_minutes,
        to_complete=len(content.open_tasks),
        elapsed_minutes=round(sum(minutes_today.get(t["id"], 0) for t in tasks)),
        completed=len(done_today),
    )


def sidebar_counts(db: Database, focus_minutes: int, today: date | None = None
                   ) -> dict[str, tuple[int, int]]:
    """{list key: (open task count, estimated minutes left)} for the sidebar."""
    today = today or date.today()
    open_tasks = db.list_tasks("open")
    counts = {}
    for key, _ in SMART_LISTS:
        if key == "completed":
            done_today = sum(1 for t in db.list_tasks("done") if completed_on(t, today))
            counts[key] = (done_today, 0)
            continue
        if key == "recurring":
            counts[key] = (len(db.list_recurrences(include_stopped=False, today=today)), 0)
            continue
        tasks = [t for t in open_tasks if matches(key, t, today)]
        # Recurring occurrences still to come this week count too (they will appear).
        upcoming = coming_up(db, key, today)
        counts[key] = (len(tasks) + len(upcoming),
                       (sum(remaining_estimate(t) for t in tasks)
                        + sum(u["estimate_pomodoros"] or 0 for u in upcoming)) * focus_minutes)
    for project in db.list_projects():
        tasks = [t for t in open_tasks if t["project_id"] == project["id"]]
        counts[f"project:{project['id']}"] = (
            len(tasks), sum(remaining_estimate(t) for t in tasks) * focus_minutes)
    return counts


def sort_tasks(tasks: list[dict], sort: str, score_order: dict[int, int]) -> list[dict]:
    """score_order maps task id -> position in the Focus Score ranking."""
    far = date.max.isoformat()
    keys = {
        "score": lambda t: (score_order.get(t["id"], len(score_order)), t["id"]),
        "due": lambda t: (t["due_date"] or far, t["priority"], t["id"]),
        "priority": lambda t: (t["priority"], t["due_date"] or far, t["id"]),
        "title": lambda t: (t["title"].lower(), t["id"]),
        "created": lambda t: (-_timestamp(t["created_at"]), -t["id"]),
    }
    return sorted(tasks, key=keys[sort])


def _timestamp(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def group_by_project(tasks: list[dict], projects: list[dict]) -> list[tuple[str, str, list]]:
    """[(project name, colour, tasks)] in project order; tasks without a project last."""
    groups = []
    for project in projects:
        members = [t for t in tasks if t["project_id"] == project["id"]]
        if members:
            groups.append((project["name"], project["color"], members))
    loose = [t for t in tasks if t["project_id"] is None]
    if loose:
        groups.append(("No project", "#B9BBC6", loose))
    return groups


def format_minutes(minutes: float) -> str:
    """'0m', '45m', '1h 40m'."""
    hours, mins = divmod(round(minutes), 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"
