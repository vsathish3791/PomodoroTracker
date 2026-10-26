"""SQLite storage for tasks, pomodoro sessions and settings.

All data lives in a single file (by default %APPDATA%/PomodoroTracker/pomodoro.db),
so backing up the app is just copying that file.

The full schema (including priority, due dates and overrides) is created now,
even though Phase 1 only uses `sessions` and `settings`, so later phases
don't need a migration.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from pomodoro.models import (CATEGORY_PALETTE, DEFAULT_CATEGORIES, DEFAULT_PRIORITY,
                             EXTRA_CATEGORY_COLOR, OLD_DEFAULT_COLORS, PRIORITIES, STATUSES,
                             TASK_TYPES)

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#888888'
);

CREATE TABLE IF NOT EXISTS tasks (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT NOT NULL,
    category_id        INTEGER REFERENCES categories(id),
    type               TEXT NOT NULL DEFAULT 'coding'
                       CHECK (type IN ('coding', 'non-coding')),
    priority           INTEGER NOT NULL DEFAULT 3
                       CHECK (priority BETWEEN 1 AND 4),   -- 1 = Critical ... 4 = Low
    due_date           TEXT,                                -- ISO date/datetime, optional
    estimate_pomodoros INTEGER,
    status             TEXT NOT NULL DEFAULT 'todo'
                       CHECK (status IN ('todo', 'in_progress', 'on_hold', 'done')),
    notes              TEXT,
    created_at         TEXT NOT NULL,
    completed_at       TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER REFERENCES tasks(id),
    kind         TEXT NOT NULL CHECK (kind IN ('focus', 'break', 'long_break')),
    start_time   TEXT NOT NULL,
    end_time     TEXT NOT NULL,
    duration_min REAL NOT NULL,
    completed    INTEGER NOT NULL      -- 1 = ran the full length, 0 = stopped/skipped early
);

CREATE TABLE IF NOT EXISTS overrides (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER REFERENCES sessions(id),
    chosen_task_id    INTEGER REFERENCES tasks(id),
    suggested_task_id INTEGER REFERENCES tasks(id),
    timestamp         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_task  ON sessions(task_id);
"""

DEFAULT_SETTINGS = {
    "focus_minutes": "25",
    "break_minutes": "5",
    "long_break_minutes": "15",
    "long_break_enabled": "0",      # off by default: plain 25/5 cycle
    "pomodoros_before_long_break": "4",
    "auto_start_break": "1",        # break starts automatically after a focus block
    "auto_start_focus": "0",        # next focus block waits for you to press Start
    "daily_goal": "8",
    "working_days": "0,1,2,3,4",    # Monday=0 ... Sunday=6; used for at-risk deadlines
    "last_summary_date": "",        # the day the morning summary was last shown
    "sound_enabled": "1",
}


def default_db_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "PomodoroTracker" / "pomodoro.db"


class Database:
    def __init__(self, path: str | Path | None = None):
        """Open (and create if needed) the database. Pass ':memory:' for tests."""
        if path is None:
            path = default_db_path()
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._seed_settings()
        self._seed_categories()

    def close(self):
        self.conn.close()

    # ---------- settings ----------

    def _seed_settings(self):
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                DEFAULT_SETTINGS.items(),
            )

    def get_setting(self, key: str) -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else DEFAULT_SETTINGS[key]

    def get_int(self, key: str) -> int:
        return int(self.get_setting(key))

    def get_bool(self, key: str) -> bool:
        return self.get_setting(key) == "1"

    def get_working_days(self) -> set[int]:
        return {int(day) for day in self.get_setting("working_days").split(",") if day.strip()}

    def set_setting(self, key: str, value):
        if isinstance(value, bool):
            value = "1" if value else "0"
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

    # ---------- categories ----------

    def _seed_categories(self):
        if self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            with self.conn:
                self.conn.executemany(
                    "INSERT INTO categories (name, color) VALUES (?, ?)", DEFAULT_CATEGORIES)
            return
        # Upgrade colours from older versions: the old defaults, and categories
        # created before new ones got a palette colour.
        new_colors = dict(DEFAULT_CATEGORIES)
        with self.conn:
            for name, old in OLD_DEFAULT_COLORS.items():
                self.conn.execute("UPDATE categories SET color = ? WHERE name = ? AND color = ?",
                                  (new_colors[name], name, old))
            for row in self.conn.execute(
                    "SELECT id FROM categories WHERE color = '#888888' ORDER BY id").fetchall():
                self.conn.execute("UPDATE categories SET color = ? WHERE id = ?",
                                  (self._next_category_color(), row["id"]))

    def _next_category_color(self) -> str:
        """The first palette colour no category uses yet (grey once all 8 are taken)."""
        used = {row["color"].lower() for row in self.conn.execute("SELECT color FROM categories")}
        return next((c for c in CATEGORY_PALETTE if c.lower() not in used), EXTRA_CATEGORY_COLOR)

    def list_categories(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, name, color FROM categories ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def get_or_create_category(self, name: str) -> int | None:
        """Category id for this name (case-insensitive); creates it if new. Blank -> None."""
        name = " ".join(name.split())
        if not name:
            return None
        row = self.conn.execute(
            "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        if row:
            return row["id"]
        with self.conn:
            return self.conn.execute("INSERT INTO categories (name, color) VALUES (?, ?)",
                                     (name, self._next_category_color())).lastrowid

    # ---------- tasks ----------

    # Columns that create_task/update_task are allowed to set.
    TASK_FIELDS = ("title", "category_id", "type", "priority", "due_date",
                   "estimate_pomodoros", "status", "notes")

    def _clean_task_fields(self, fields: dict) -> dict:
        unknown = set(fields) - set(self.TASK_FIELDS)
        if unknown:
            raise ValueError(f"Unknown task fields: {sorted(unknown)}")
        fields = dict(fields)
        if "title" in fields:
            fields["title"] = " ".join((fields["title"] or "").split())
            if not fields["title"]:
                raise ValueError("Task title is required")
        if "priority" in fields and fields["priority"] not in PRIORITIES:
            raise ValueError(f"Priority must be one of {list(PRIORITIES)}")
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"Status must be one of {list(STATUSES)}")
        if "type" in fields and fields["type"] not in TASK_TYPES:
            raise ValueError(f"Type must be one of {list(TASK_TYPES)}")
        if fields.get("estimate_pomodoros") == 0:
            fields["estimate_pomodoros"] = None   # 0 means "no estimate"
        return fields

    def create_task(self, title: str, **fields) -> int:
        fields = self._clean_task_fields({"title": title, **fields})
        fields.setdefault("priority", DEFAULT_PRIORITY)
        fields["created_at"] = datetime.now().isoformat(timespec="seconds")
        if fields.get("status") == "done":
            fields["completed_at"] = fields["created_at"]
        columns = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.conn:
            return self.conn.execute(
                f"INSERT INTO tasks ({columns}) VALUES ({marks})", list(fields.values())).lastrowid

    def update_task(self, task_id: int, **fields):
        fields = self._clean_task_fields(fields)
        if not fields:
            return
        if "status" in fields:
            # Record when a task is finished; clear it again if the task is reopened.
            done = fields["status"] == "done"
            fields["completed_at"] = datetime.now().isoformat(timespec="seconds") if done else None
            if done:
                current = self.get_task(task_id)
                if current and current["status"] == "done":
                    fields["completed_at"] = current["completed_at"]  # already done; keep date
        assignments = ", ".join(f"{column} = ?" for column in fields)
        with self.conn:
            self.conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?",
                              [*fields.values(), task_id])

    def set_task_status(self, task_id: int, status: str):
        self.update_task(task_id, status=status)

    def delete_task(self, task_id: int):
        """Delete a task. Its logged time is kept (unassigned) so daily totals stay right."""
        with self.conn:
            self.conn.execute("UPDATE sessions SET task_id = NULL WHERE task_id = ?", (task_id,))
            self.conn.execute("DELETE FROM overrides WHERE chosen_task_id = ? "
                              "OR suggested_task_id = ?", (task_id, task_id))
            self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    _TASK_SELECT = """
        SELECT t.*, c.name AS category, c.color AS category_color,
               COALESCE(SUM(CASE WHEN s.kind = 'focus' THEN s.completed END), 0) AS pomodoros,
               COALESCE(SUM(CASE WHEN s.kind = 'focus' THEN s.duration_min END), 0) AS focus_minutes
        FROM tasks t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN sessions s ON s.task_id = t.id
    """

    def get_task(self, task_id: int) -> dict | None:
        row = self.conn.execute(
            self._TASK_SELECT + " WHERE t.id = ? GROUP BY t.id", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, show: str = "open", category_id: int | None = None,
                   search: str = "") -> list[dict]:
        """Tasks with their pomodoro totals.

        show: 'open' (not done), 'done', or 'all'.
        Open tasks are sorted by priority, then due date (no date last).
        """
        where, params = [], []
        if show == "open":
            where.append("t.status != 'done'")
        elif show == "done":
            where.append("t.status = 'done'")
        if category_id is not None:
            where.append("t.category_id = ?")
            params.append(category_id)
        if search.strip():
            where.append("(t.title LIKE ? OR t.notes LIKE ?)")
            params += [f"%{search.strip()}%"] * 2
        sql = self._TASK_SELECT
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY t.id "
        if show == "done":
            sql += "ORDER BY t.completed_at DESC"
        else:
            sql += ("ORDER BY t.status = 'done', t.priority, "
                    "t.due_date IS NULL, t.due_date, t.created_at")
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def find_open_task(self, title: str) -> int | None:
        """Id of the open task with this title (case-insensitive, extra spaces ignored)."""
        title = " ".join(title.split())
        if not title:
            return None
        row = self.conn.execute(
            "SELECT id FROM tasks WHERE title = ? COLLATE NOCASE AND status != 'done' "
            "ORDER BY id DESC LIMIT 1",
            (title,),
        ).fetchone()
        return row["id"] if row else None

    def get_or_create_task(self, title: str) -> int:
        """Return the open task with this title (case-insensitive), creating it if needed.

        The task is marked 'in_progress' since you're about to work on it.
        """
        task_id = self.find_open_task(title)
        if task_id is None:
            return self.create_task(title, status="in_progress")
        with self.conn:
            self.conn.execute(
                "UPDATE tasks SET status = 'in_progress' WHERE id = ? AND status IN ('todo', 'on_hold')",
                (task_id,),
            )
        return task_id

    def recent_open_tasks(self, limit: int = 15) -> list[str]:
        """Titles of tasks not yet done, most recently worked on first."""
        rows = self.conn.execute(
            "SELECT t.title, MAX(COALESCE(s.start_time, t.created_at)) AS last_used "
            "FROM tasks t LEFT JOIN sessions s ON s.task_id = t.id "
            "WHERE t.status != 'done' GROUP BY t.id ORDER BY last_used DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row["title"] for row in rows]

    def task_stats(self, task_id: int) -> dict:
        """All-time pomodoros completed and focus minutes for one task."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(completed), 0) AS pomodoros, "
            "       COALESCE(SUM(duration_min), 0) AS minutes "
            "FROM sessions WHERE kind = 'focus' AND task_id = ?",
            (task_id,),
        ).fetchone()
        return {"pomodoros": int(row["pomodoros"]), "focus_minutes": round(row["minutes"])}

    def add_override(self, chosen_task_id: int, suggested_task_id: int):
        """Remember that you chose a different task than the one the app suggested."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO overrides (chosen_task_id, suggested_task_id, timestamp) "
                "VALUES (?, ?, ?)",
                (chosen_task_id, suggested_task_id, datetime.now().isoformat(timespec="seconds")),
            )

    # ---------- sessions ----------

    def add_session(self, kind: str, start: datetime, end: datetime, duration_min: float,
                    completed: bool, task_id: int | None = None) -> int:
        """Log one focus/break block. duration_min is time actually counted (pauses excluded)."""
        duration_min = round(duration_min, 2)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions (task_id, kind, start_time, end_time, duration_min, completed) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, kind, start.isoformat(timespec="seconds"),
                 end.isoformat(timespec="seconds"), duration_min, int(completed)),
            )
        return cur.lastrowid

    def day_stats(self, day: date | None = None) -> dict:
        """Pomodoros completed and focus minutes (incl. partial blocks) for one day."""
        day = day or date.today()
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        row = self.conn.execute(
            "SELECT COALESCE(SUM(completed), 0) AS pomodoros, "
            "       COALESCE(SUM(duration_min), 0) AS minutes "
            "FROM sessions WHERE kind = 'focus' AND start_time >= ? AND start_time < ?",
            (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
        ).fetchone()
        return {"pomodoros": int(row["pomodoros"]), "focus_minutes": round(row["minutes"])}
