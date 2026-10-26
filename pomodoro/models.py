"""Task constants and small formatting helpers shared by the database and the UI."""

from datetime import date

PRIORITIES = {
    1: "P1 Critical",
    2: "P2 High",
    3: "P3 Medium",
    4: "P4 Low",
}
DEFAULT_PRIORITY = 3

STATUSES = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "on_hold": "On Hold",
    "done": "Done",
}

TASK_TYPES = {
    "coding": "Coding",
    "non-coding": "Non-coding",
}

# Created the first time the app runs; you can add more from the task dialog.
DEFAULT_CATEGORIES = [
    ("Development", "#E5484D"),
    ("Code Review", "#8E4EC6"),
    ("Meetings", "#F76B15"),
    ("Learning", "#30A46C"),
    ("Documentation", "#0090FF"),
    ("Planning", "#12A594"),
    ("Admin", "#8B8D98"),
]

PRIORITY_COLORS = {1: "#CE2C31", 2: "#DC6B19", 3: "#60646C", 4: "#8B8D98"}


def due_label(due: str | None, today: date | None = None) -> str:
    """Friendly due date, e.g. 'Overdue (2 d)', 'Today', 'Tomorrow', 'Fri 30 Oct'."""
    if not due:
        return ""
    today = today or date.today()
    due_day = date.fromisoformat(due[:10])
    days = (due_day - today).days
    if days < 0:
        return f"Overdue ({-days} d)"
    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    if days < 7:
        return due_day.strftime("%a %d %b")
    if due_day.year == today.year:
        return due_day.strftime("%d %b")
    return due_day.strftime("%d %b %Y")


def is_overdue(due: str | None, today: date | None = None) -> bool:
    return bool(due) and date.fromisoformat(due[:10]) < (today or date.today())


def pomodoro_progress(done: int, estimate: int | None) -> str:
    """'3 / 8' when there's an estimate, otherwise just '3'."""
    return f"{done} / {estimate}" if estimate else str(done)
