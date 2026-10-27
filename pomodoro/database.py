"""SQLite storage for tasks, pomodoro sessions and settings.

All data lives in a single file (by default %APPDATA%/PomodoroTracker/pomodoro.db),
so backing up the app is just copying that file.

The full schema (including priority, due dates and overrides) is created now,
even though Phase 1 only uses `sessions` and `settings`, so later phases
don't need a migration.
"""

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from pomodoro.models import (CATEGORY_PALETTE, DEFAULT_CATEGORIES, DEFAULT_PRIORITY,
                             DEFAULT_TYPES, ENERGY_SLOTS, EXTRA_CATEGORY_COLOR, NATURES,
                             OLD_DEFAULT_COLORS, PRIORITIES, STATUSES)
from pomodoro.recurrence import Schedule, schedule_from_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#888888'
);

CREATE TABLE IF NOT EXISTS task_types (
    key      TEXT PRIMARY KEY,                 -- stored on tasks; never changes
    name     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color    TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT NOT NULL,
    category_id        INTEGER REFERENCES categories(id),
    type               TEXT NOT NULL DEFAULT 'coding',      -- a task_types.key
    priority           INTEGER NOT NULL DEFAULT 3
                       CHECK (priority BETWEEN 1 AND 4),   -- 1 = Critical ... 4 = Low
    due_date           TEXT,                                -- ISO date/datetime, optional
    estimate_pomodoros INTEGER,
    status             TEXT NOT NULL DEFAULT 'todo',        -- see models.STATUSES
    notes              TEXT,
    created_at         TEXT NOT NULL,
    completed_at       TEXT
);

CREATE TABLE IF NOT EXISTS recurrences (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    -- the template each occurrence is created from
    title              TEXT NOT NULL,
    project_id         INTEGER REFERENCES projects(id),
    category_id        INTEGER REFERENCES categories(id),
    type               TEXT,
    priority           INTEGER NOT NULL DEFAULT 3,
    estimate_pomodoros INTEGER,
    energy_slot        TEXT,
    nature             TEXT NOT NULL DEFAULT 'routine',
    notes              TEXT,
    notion_url         TEXT,
    checklist          TEXT,                 -- one step per line
    -- the schedule (see recurrence.py)
    frequency          TEXT NOT NULL,        -- daily | weekly | monthly
    workdays_only      INTEGER NOT NULL DEFAULT 1,
    weekdays           TEXT,                 -- "0,3" = Mon, Thu
    month_day          INTEGER,
    start_date         TEXT NOT NULL,
    end_date           TEXT NOT NULL,
    active             INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL
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
    "score_weights": "{}",          # Focus Score points changed in Settings (JSON)
    "hotkey_enabled": "1",
    "hotkey": "Ctrl+Alt+P",         # global shortcut for Start / Pause
    "mini_window_visible": "0",
    "mini_window_pos": "",          # "x,y" of the mini timer
    "last_project_id": "",          # project picked most recently for a new task
    "sound_enabled": "1",
}


def clean_checklist(text: str | None) -> str | None:
    """One step per line; blank lines and stray spaces removed. Empty -> None."""
    steps = [" ".join(line.split()) for line in (text or "").splitlines()]
    steps = [step.lstrip("-*• ").strip() for step in steps]
    return "\n".join(step for step in steps if step) or None


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
        self._migrate()
        self._seed_settings()
        self._seed_categories()
        self._seed_types()

    def _migrate(self):
        """Upgrade databases made by older versions of the app."""
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)")}
        with self.conn:
            if "project_id" not in columns:   # projects were added in v1.1
                self.conn.execute(
                    "ALTER TABLE tasks ADD COLUMN project_id INTEGER REFERENCES projects(id)")
            if "energy_slot" not in columns:  # v1.2.1
                self.conn.execute("ALTER TABLE tasks ADD COLUMN energy_slot TEXT")
            if "notion_url" not in columns:   # v1.2.1: link to the task's Notion page
                self.conn.execute("ALTER TABLE tasks ADD COLUMN notion_url TEXT")
            for column, kind in [("recurrence_id", "INTEGER REFERENCES recurrences(id)"),
                                 ("occurrence_date", "TEXT"), ("nature", "TEXT"),
                                 ("checklist", "TEXT"), ("checklist_done", "TEXT")]:
                if column not in columns:     # v1.3: recurring tasks, kind of work, checklists
                    self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {kind}")
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_occurrence "
                "ON tasks(recurrence_id, occurrence_date) WHERE recurrence_id IS NOT NULL")
        self._relax_task_rules()             # v1.2 types, v1.3 'missed' status
        category_columns = {row["name"] for row in
                            self.conn.execute("PRAGMA table_info(categories)")}
        with self.conn:
            if "position" not in category_columns:
                self.conn.execute(
                    "ALTER TABLE categories ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
                # Keep the alphabetical order older versions showed.
                for position, row in enumerate(self.conn.execute(
                        "SELECT id FROM categories ORDER BY name").fetchall()):
                    self.conn.execute("UPDATE categories SET position = ? WHERE id = ?",
                                      (position, row["id"]))
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")

    def _relax_task_rules(self):
        """Older versions had fixed lists for tasks.type (v1.0/1.1) and tasks.status
        (before v1.3) as CHECK rules. Types are now editable and there is a 'missed'
        status, and the app checks values itself. SQLite can't drop a CHECK rule, so
        the tasks table is copied without them (all data and ids are kept)."""
        sql = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tasks'").fetchone()[0]
        if "CHECK (type IN" not in sql and "CHECK (status IN" not in sql:
            return
        new_sql = re.sub(r"\s*CHECK \((?:type|status) IN \([^)]*\)\)", "", sql)
        # The name may be stored as tasks or "tasks" (after an earlier upgrade).
        new_sql = re.sub(r'CREATE TABLE\s+"?tasks"?', "CREATE TABLE tasks_upgrade", new_sql,
                         count=1)
        columns = ", ".join(row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)"))
        self.conn.execute("PRAGMA foreign_keys = OFF")   # sessions point at tasks
        try:
            with self.conn:
                self.conn.execute(new_sql)
                self.conn.execute(f"INSERT INTO tasks_upgrade ({columns}) "
                                  f"SELECT {columns} FROM tasks")
                self.conn.execute("DROP TABLE tasks")
                self.conn.execute("ALTER TABLE tasks_upgrade RENAME TO tasks")
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")

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

    def get_json(self, key: str) -> dict:
        try:
            return json.loads(self.get_setting(key) or "{}")
        except json.JSONDecodeError:
            return {}

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
                    "INSERT INTO categories (name, color, position) VALUES (?, ?, ?)",
                    [(name, color, i) for i, (name, color) in enumerate(DEFAULT_CATEGORIES)])
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
        """Categories in your chosen order, with how many tasks use each."""
        rows = self.conn.execute(
            "SELECT c.id, c.name, c.color, c.position, COUNT(t.id) AS tasks "
            "FROM categories c LEFT JOIN tasks t ON t.category_id = c.id "
            "GROUP BY c.id ORDER BY c.position, c.id").fetchall()
        return [dict(row) for row in rows]

    def _clean_name(self, table: str, name: str, keep_id=None, id_column="id") -> str:
        """Tidy a category/type name and check it's not blank or already taken."""
        name = " ".join((name or "").split())
        if not name:
            raise ValueError("A name is required")
        clash = self.conn.execute(
            f"SELECT {id_column} AS id FROM {table} WHERE name = ? COLLATE NOCASE",
            (name,)).fetchone()
        if clash and clash["id"] != keep_id:
            raise ValueError(f'"{name}" already exists')
        return name

    def _next_position(self, table: str) -> int:
        return self.conn.execute(f"SELECT COALESCE(MAX(position), -1) + 1 FROM {table}"
                                 ).fetchone()[0]

    def create_category(self, name: str, color: str | None = None) -> int:
        name = self._clean_name("categories", name)
        with self.conn:
            return self.conn.execute(
                "INSERT INTO categories (name, color, position) VALUES (?, ?, ?)",
                (name, color or self._next_category_color(),
                 self._next_position("categories"))).lastrowid

    def get_or_create_category(self, name: str) -> int | None:
        """Category id for this name (case-insensitive); creates it if new. Blank -> None."""
        name = " ".join(name.split())
        if not name:
            return None
        row = self.conn.execute(
            "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        return row["id"] if row else self.create_category(name)

    def rename_category(self, category_id: int, name: str):
        name = self._clean_name("categories", name, keep_id=category_id)
        with self.conn:
            self.conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))

    def set_category_color(self, category_id: int, color: str):
        with self.conn:
            self.conn.execute("UPDATE categories SET color = ? WHERE id = ?", (color, category_id))

    def delete_category(self, category_id: int, move_to: int | None = None):
        """Delete a category; its tasks move to `move_to` (None = no category)."""
        with self.conn:
            self.conn.execute("UPDATE tasks SET category_id = ? WHERE category_id = ?",
                              (move_to, category_id))
            self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    def move_category(self, category_id: int, step: int):
        """Move a category up (-1) or down (+1) in the list."""
        self._move_in_order("categories", "id", category_id, step)

    def _move_in_order(self, table: str, id_column: str, item_id, step: int):
        ids = [row[0] for row in self.conn.execute(
            f"SELECT {id_column} FROM {table} ORDER BY position, {id_column}")]
        index = ids.index(item_id)
        target = index + step
        if not 0 <= target < len(ids):
            return
        ids[index], ids[target] = ids[target], ids[index]
        with self.conn:
            for position, value in enumerate(ids):
                self.conn.execute(f"UPDATE {table} SET position = ? WHERE {id_column} = ?",
                                  (position, value))

    # ---------- task types ----------

    def _seed_types(self):
        if self.conn.execute("SELECT COUNT(*) FROM task_types").fetchone()[0] == 0:
            with self.conn:
                self.conn.executemany(
                    "INSERT INTO task_types (key, name, color, position) VALUES (?, ?, ?, ?)",
                    [(key, name, CATEGORY_PALETTE[i], i)
                     for i, (key, name) in enumerate(DEFAULT_TYPES)])

    def list_types(self) -> list[dict]:
        """Task types in your chosen order, with how many tasks use each."""
        rows = self.conn.execute(
            "SELECT tt.key, tt.name, tt.color, tt.position, COUNT(t.id) AS tasks "
            "FROM task_types tt LEFT JOIN tasks t ON t.type = tt.key "
            "GROUP BY tt.key ORDER BY tt.position, tt.key").fetchall()
        return [dict(row) for row in rows]

    def type_names(self) -> dict[str, str]:
        return {t["key"]: t["name"] for t in self.list_types()}

    def default_type(self) -> str:
        """The type new tasks get unless you choose one: the first in the list."""
        return self.list_types()[0]["key"]

    def create_type(self, name: str, color: str | None = None) -> str:
        name = self._clean_name("task_types", name, id_column="key")
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "type"
        key, n = base, 2
        while self.conn.execute("SELECT 1 FROM task_types WHERE key = ?", (key,)).fetchone():
            key, n = f"{base}-{n}", n + 1
        if color is None:
            used = {row[0].lower() for row in self.conn.execute("SELECT color FROM task_types")}
            color = next((c for c in CATEGORY_PALETTE if c.lower() not in used),
                         EXTRA_CATEGORY_COLOR)
        with self.conn:
            self.conn.execute(
                "INSERT INTO task_types (key, name, color, position) VALUES (?, ?, ?, ?)",
                (key, name, color, self._next_position("task_types")))
        return key

    def rename_type(self, key: str, name: str):
        name = self._clean_name("task_types", name, keep_id=key, id_column="key")
        with self.conn:
            self.conn.execute("UPDATE task_types SET name = ? WHERE key = ?", (name, key))

    def set_type_color(self, key: str, color: str):
        with self.conn:
            self.conn.execute("UPDATE task_types SET color = ? WHERE key = ?", (color, key))

    def delete_type(self, key: str, move_to: str):
        """Delete a type; its tasks change to `move_to`. The last type can't be deleted."""
        keys = [t["key"] for t in self.list_types()]
        if len(keys) <= 1:
            raise ValueError("You need at least one type")
        if move_to not in keys or move_to == key:
            raise ValueError("Pick another type for its tasks")
        with self.conn:
            self.conn.execute("UPDATE tasks SET type = ? WHERE type = ?", (move_to, key))
            self.conn.execute("DELETE FROM task_types WHERE key = ?", (key,))

    def move_type(self, key: str, step: int):
        self._move_in_order("task_types", "key", key, step)

    # ---------- projects ----------

    def list_projects(self) -> list[dict]:
        """Projects in the order they were created."""
        rows = self.conn.execute("SELECT id, name, color FROM projects ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: int) -> dict | None:
        row = self.conn.execute("SELECT id, name, color FROM projects WHERE id = ?",
                                (project_id,)).fetchone()
        return dict(row) if row else None

    def _clean_project_name(self, name: str, project_id: int | None = None) -> str:
        name = " ".join((name or "").split())
        if not name:
            raise ValueError("Project name is required")
        clash = self.conn.execute("SELECT id FROM projects WHERE name = ? COLLATE NOCASE",
                                  (name,)).fetchone()
        if clash and clash["id"] != project_id:
            raise ValueError(f'There is already a project called "{name}"')
        return name

    def _next_project_color(self) -> str:
        used = {row["color"].lower() for row in self.conn.execute("SELECT color FROM projects")}
        return next((c for c in CATEGORY_PALETTE if c.lower() not in used), EXTRA_CATEGORY_COLOR)

    def create_project(self, name: str, color: str | None = None) -> int:
        name = self._clean_project_name(name)
        with self.conn:
            return self.conn.execute(
                "INSERT INTO projects (name, color, created_at) VALUES (?, ?, ?)",
                (name, color or self._next_project_color(),
                 datetime.now().isoformat(timespec="seconds"))).lastrowid

    def rename_project(self, project_id: int, name: str):
        name = self._clean_project_name(name, project_id)
        with self.conn:
            self.conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))

    def set_project_color(self, project_id: int, color: str):
        with self.conn:
            self.conn.execute("UPDATE projects SET color = ? WHERE id = ?", (color, project_id))

    def delete_project(self, project_id: int):
        """Delete a project. Its tasks are kept, just no longer in a project."""
        with self.conn:
            self.conn.execute("UPDATE tasks SET project_id = NULL WHERE project_id = ?",
                              (project_id,))
            self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def last_project_id(self) -> int | None:
        """The project you used last for a new task (None if unset or since deleted)."""
        value = self.get_setting("last_project_id")
        if value and self.get_project(int(value)):
            return int(value)
        return None

    def set_last_project_id(self, project_id: int | None):
        self.set_setting("last_project_id", project_id or "")

    def get_or_create_project(self, name: str) -> int | None:
        """Project id for this name (case-insensitive); creates it if new. Blank -> None."""
        name = " ".join((name or "").split())
        if not name:
            return None
        row = self.conn.execute("SELECT id FROM projects WHERE name = ? COLLATE NOCASE",
                                (name,)).fetchone()
        return row["id"] if row else self.create_project(name)

    # ---------- tasks ----------

    # Columns that create_task/update_task are allowed to set.
    TASK_FIELDS = ("title", "category_id", "project_id", "type", "priority", "due_date",
                   "estimate_pomodoros", "status", "notes", "energy_slot", "notion_url",
                   "nature", "checklist")

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
        if "type" in fields and fields["type"] not in self.type_names():
            raise ValueError(f"Type must be one of {list(self.type_names())}")
        if fields.get("nature") not in (None, *NATURES):
            raise ValueError(f"Kind of work must be one of {list(NATURES)}")
        if "checklist" in fields:
            fields["checklist"] = clean_checklist(fields["checklist"])
        if fields.get("energy_slot") not in (None, *ENERGY_SLOTS):
            raise ValueError(f"Energy slot must be one of {list(ENERGY_SLOTS)}")
        if "notion_url" in fields:
            fields["notion_url"] = (fields["notion_url"] or "").strip() or None
        if fields.get("estimate_pomodoros") == 0:
            fields["estimate_pomodoros"] = None   # 0 means "no estimate"
        return fields

    def create_task(self, title: str, **fields) -> int:
        fields = self._clean_task_fields({"title": title, **fields})
        fields.setdefault("priority", DEFAULT_PRIORITY)
        if not fields.get("type"):
            fields["type"] = self.default_type()
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
               p.name AS project, p.color AS project_color,
               COALESCE(SUM(CASE WHEN s.kind = 'focus' THEN s.completed END), 0) AS pomodoros,
               COALESCE(SUM(CASE WHEN s.kind = 'focus' THEN s.duration_min END), 0) AS focus_minutes
        FROM tasks t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN sessions s ON s.task_id = t.id
    """

    def get_task(self, task_id: int) -> dict | None:
        row = self.conn.execute(
            self._TASK_SELECT + " WHERE t.id = ? GROUP BY t.id", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, show: str = "open", category_id: int | None = None,
                   search: str = "", project_id: int | None = None) -> list[dict]:
        """Tasks with their pomodoro totals.

        show: 'open' (not done), 'done', or 'all'.
        Open tasks are sorted by priority, then due date (no date last).
        """
        where, params = [], []
        if show == "open":
            where.append("t.status NOT IN ('done', 'missed')")
        elif show == "done":
            where.append("t.status = 'done'")
        if category_id is not None:
            where.append("t.category_id = ?")
            params.append(category_id)
        if project_id is not None:
            where.append("t.project_id = ?")
            params.append(project_id)
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

    def set_checklist_done(self, task_id: int, done_steps: list[int]):
        """Remember which checklist steps (by position) are ticked for this task."""
        with self.conn:
            self.conn.execute("UPDATE tasks SET checklist_done = ? WHERE id = ?",
                              (json.dumps(sorted(set(done_steps))), task_id))

    # ---------- recurring tasks ----------

    RECURRENCE_FIELDS = ("title", "project_id", "category_id", "type", "priority",
                         "estimate_pomodoros", "energy_slot", "nature", "notes", "notion_url",
                         "checklist", "frequency", "workdays_only", "weekdays", "month_day",
                         "start_date", "end_date")
    # Template fields copied onto each occurrence
    _COPIED = ("title", "project_id", "category_id", "type", "priority", "estimate_pomodoros",
               "energy_slot", "nature", "notes", "notion_url", "checklist")

    def _clean_recurrence(self, fields: dict, current: dict | None = None) -> dict:
        unknown = set(fields) - set(self.RECURRENCE_FIELDS)
        if unknown:
            raise ValueError(f"Unknown fields: {sorted(unknown)}")
        fields = dict(fields)
        if isinstance(fields.get("weekdays"), (list, tuple, set)):
            fields["weekdays"] = ",".join(str(d) for d in sorted(fields["weekdays"]))
        task_like = {k: v for k, v in fields.items() if k in self.TASK_FIELDS}
        fields.update(self._clean_task_fields(task_like))
        if fields.get("type") is None and current is None:
            fields["type"] = self.default_type()
        merged = {**(current or {}), **fields}
        if not merged.get("start_date") or not merged.get("end_date"):
            raise ValueError("A recurring task needs a start date and an end date")
        schedule_from_row(merged)        # raises ValueError if the schedule is invalid
        return fields

    def create_recurrence(self, title: str, **fields) -> int:
        fields = self._clean_recurrence({"title": title, **fields})
        fields.setdefault("nature", "routine")
        fields["created_at"] = datetime.now().isoformat(timespec="seconds")
        columns = ", ".join(fields)
        with self.conn:
            return self.conn.execute(
                f"INSERT INTO recurrences ({columns}) VALUES ({', '.join('?' * len(fields))})",
                list(fields.values())).lastrowid

    def get_recurrence(self, recurrence_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM recurrences WHERE id = ?",
                                (recurrence_id,)).fetchone()
        return dict(row) if row else None

    def update_recurrence(self, recurrence_id: int, **fields):
        """Change the series. Future occurrences use the new template and schedule."""
        current = self.get_recurrence(recurrence_id)
        fields = self._clean_recurrence(fields, current)
        if not fields:
            return
        with self.conn:
            self.conn.execute(
                f"UPDATE recurrences SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ?",
                [*fields.values(), recurrence_id])

    def stop_recurrence(self, recurrence_id: int):
        """Stop repeating. The current occurrence (if any) and the history are kept."""
        with self.conn:
            self.conn.execute("UPDATE recurrences SET active = 0 WHERE id = ?", (recurrence_id,))

    def resume_recurrence(self, recurrence_id: int):
        with self.conn:
            self.conn.execute("UPDATE recurrences SET active = 1 WHERE id = ?", (recurrence_id,))

    def delete_recurrence(self, recurrence_id: int):
        """Delete the series. Open occurrences without logged time are removed; finished,
        missed and worked-on occurrences stay in your history as ordinary tasks."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM tasks WHERE recurrence_id = ? AND status NOT IN ('done', 'missed') "
                "AND id NOT IN (SELECT task_id FROM sessions WHERE task_id IS NOT NULL)",
                (recurrence_id,))
            self.conn.execute("UPDATE tasks SET recurrence_id = NULL WHERE recurrence_id = ?",
                              (recurrence_id,))
            self.conn.execute("DELETE FROM recurrences WHERE id = ?", (recurrence_id,))

    def schedule(self, recurrence_id: int) -> Schedule:
        return schedule_from_row(self.get_recurrence(recurrence_id))

    def generate_occurrences(self, today: date | None = None,
                             working_days: set[int] | None = None) -> int:
        """Create the occurrences that are due by today. Returns how many were created.

        Only the latest due occurrence is open; one that is still open when a newer
        one appears is marked Missed. Days skipped while the app was closed are
        recorded as Missed too, so the history stays complete.
        """
        today = today or date.today()
        working_days = self.get_working_days() if working_days is None else working_days
        created = 0
        for rec in [dict(r) for r in self.conn.execute(
                "SELECT * FROM recurrences WHERE active = 1").fetchall()]:
            schedule = schedule_from_row(rec)
            last = self.conn.execute(
                "SELECT MAX(occurrence_date) FROM tasks WHERE recurrence_id = ?",
                (rec["id"],)).fetchone()[0]
            first = date.fromisoformat(last) + timedelta(days=1) if last else schedule.start
            due = schedule.dates(first, today, working_days)
            if not due:
                continue
            now = datetime.now().isoformat(timespec="seconds")
            with self.conn:
                self.conn.execute(
                    "UPDATE tasks SET status = 'missed', completed_at = NULL "
                    "WHERE recurrence_id = ? AND status NOT IN ('done', 'missed')", (rec["id"],))
                for day in due:
                    values = {k: rec[k] for k in self._COPIED}
                    values.update(recurrence_id=rec["id"], occurrence_date=day.isoformat(),
                                  due_date=day.isoformat(), created_at=now,
                                  status="todo" if day == due[-1] else "missed")
                    self.conn.execute(
                        f"INSERT INTO tasks ({', '.join(values)}) "
                        f"VALUES ({', '.join('?' * len(values))})", list(values.values()))
                    created += 1
        return created

    def upcoming_occurrences(self, first: date, last: date, today: date | None = None,
                             working_days: set[int] | None = None) -> list[dict]:
        """Occurrences not created yet (after today) between first and last: a preview."""
        today = today or date.today()
        working_days = self.get_working_days() if working_days is None else working_days
        rows = self.conn.execute(
            "SELECT r.*, p.name AS project, p.color AS project_color, "
            "       (SELECT MAX(occurrence_date) FROM tasks t WHERE t.recurrence_id = r.id) AS last "
            "FROM recurrences r LEFT JOIN projects p ON p.id = r.project_id "
            "WHERE r.active = 1").fetchall()
        upcoming = []
        for rec in map(dict, rows):
            schedule = schedule_from_row(rec)
            start = max(first, today + timedelta(days=1))
            if rec["last"]:
                start = max(start, date.fromisoformat(rec["last"]) + timedelta(days=1))
            for day in schedule.dates(start, last, working_days):
                upcoming.append({**rec, "date": day})
        upcoming.sort(key=lambda r: (r["date"], r["title"].lower()))
        return upcoming

    def list_recurrences(self, include_stopped: bool = True, today: date | None = None,
                         working_days: set[int] | None = None) -> list[dict]:
        """Series with their progress: done, missed, open, and the next date."""
        today = today or date.today()
        working_days = self.get_working_days() if working_days is None else working_days
        sql = ("SELECT r.*, p.name AS project, p.color AS project_color, "
               "  SUM(t.status = 'done') AS done, SUM(t.status = 'missed') AS missed, "
               "  SUM(t.status NOT IN ('done', 'missed')) AS open, COUNT(t.id) AS so_far "
               "FROM recurrences r LEFT JOIN projects p ON p.id = r.project_id "
               "LEFT JOIN tasks t ON t.recurrence_id = r.id ")
        if not include_stopped:
            sql += "WHERE r.active = 1 "
        sql += "GROUP BY r.id ORDER BY r.active DESC, r.title COLLATE NOCASE"
        result = []
        for rec in map(dict, self.conn.execute(sql).fetchall()):
            schedule = schedule_from_row(rec)
            rec.update(done=rec["done"] or 0, missed=rec["missed"] or 0, open=rec["open"] or 0)
            rec["total"] = schedule.count(working_days)
            rec["describe"] = schedule.describe()
            rec["next_date"] = (schedule.next_date(today, working_days)
                                if rec["active"] else None)
            result.append(rec)
        return result

    def find_open_task(self, title: str) -> int | None:
        """Id of the open task with this title (case-insensitive, extra spaces ignored)."""
        title = " ".join(title.split())
        if not title:
            return None
        row = self.conn.execute(
            "SELECT id FROM tasks WHERE title = ? COLLATE NOCASE "
            "AND status NOT IN ('done', 'missed') "
            "ORDER BY id DESC LIMIT 1",
            (title,),
        ).fetchone()
        return row["id"] if row else None

    def get_or_create_task(self, title: str, project_id: int | None = None) -> int:
        """Return the open task with this title (case-insensitive), creating it if needed.

        A new task goes into `project_id`. The task is marked 'in_progress' since
        you're about to work on it.
        """
        task_id = self.find_open_task(title)
        if task_id is None:
            return self.create_task(title, status="in_progress", project_id=project_id)
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
            "WHERE t.status NOT IN ('done', 'missed') GROUP BY t.id "
            "ORDER BY last_used DESC LIMIT ?",
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

    def focus_minutes_by_task(self, day: date) -> dict[int, float]:
        """{task id: focus minutes logged that day}."""
        start = datetime.combine(day, datetime.min.time())
        rows = self.conn.execute(
            "SELECT task_id, SUM(duration_min) AS minutes FROM sessions "
            "WHERE kind = 'focus' AND task_id IS NOT NULL AND start_time >= ? AND start_time < ? "
            "GROUP BY task_id",
            (start.isoformat(timespec="seconds"),
             (start + timedelta(days=1)).isoformat(timespec="seconds")),
        ).fetchall()
        return {row["task_id"]: row["minutes"] for row in rows}

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
