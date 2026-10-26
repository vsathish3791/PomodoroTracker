import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta

from pomodoro import reports
from pomodoro.database import Database


class CategoryEditingTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def names(self):
        return [c["name"] for c in self.db.list_categories()]

    def test_default_order_and_usage_counts(self):
        self.assertEqual(self.names()[:3], ["Development", "Code Review", "Meetings"])
        dev = self.db.get_or_create_category("Development")
        self.db.create_task("A", category_id=dev)
        counts = {c["name"]: c["tasks"] for c in self.db.list_categories()}
        self.assertEqual((counts["Development"], counts["Meetings"]), (1, 0))

    def test_add_rename_recolour(self):
        new = self.db.create_category("Research")
        self.assertEqual(self.names()[-1], "Research")
        task = self.db.create_task("Paper", category_id=new)
        self.db.rename_category(new, "Deep research")
        self.assertEqual(self.db.get_task(task)["category"], "Deep research")
        self.db.set_category_color(new, "#123456")
        self.assertEqual(self.db.get_task(task)["category_color"], "#123456")
        with self.assertRaises(ValueError):
            self.db.rename_category(new, "development")      # name taken
        with self.assertRaises(ValueError):
            self.db.create_category("  ")

    def test_delete_moves_tasks(self):
        meetings = self.db.get_or_create_category("Meetings")
        admin = self.db.get_or_create_category("Admin")
        a = self.db.create_task("Standup", category_id=meetings)
        self.db.delete_category(meetings, move_to=admin)
        self.assertEqual(self.db.get_task(a)["category"], "Admin")
        self.assertNotIn("Meetings", self.names())
        self.db.delete_category(admin)                        # no target = no category
        self.assertIsNone(self.db.get_task(a)["category_id"])

    def test_reorder(self):
        meetings = self.db.get_or_create_category("Meetings")
        self.db.move_category(meetings, -1)
        self.assertEqual(self.names()[:3], ["Development", "Meetings", "Code Review"])
        self.db.move_category(meetings, -1)
        self.db.move_category(meetings, -1)                  # already first: no change
        self.assertEqual(self.names()[0], "Meetings")


class TypeEditingTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_defaults(self):
        self.assertEqual(self.db.type_names(), {"coding": "Coding", "non-coding": "Non-coding"})
        self.assertEqual(self.db.default_type(), "coding")
        self.assertEqual(self.db.get_task(self.db.create_task("x"))["type"], "coding")

    def test_add_use_rename(self):
        key = self.db.create_type("Research & Reading")
        self.assertEqual(key, "research-reading")
        self.assertEqual(self.db.create_type("Research/Reading"), "research-reading-2")
        task = self.db.create_task("Read paper", type=key)
        self.db.rename_type(key, "Research")
        self.assertEqual(self.db.get_task(task)["type"], key)          # key never changes
        self.assertEqual(self.db.type_names()[key], "Research")
        with self.assertRaises(ValueError):
            self.db.create_type("coding")                               # name taken
        with self.assertRaises(ValueError):
            self.db.create_task("Bad", type="nonexistent")

    def test_delete_moves_tasks_and_keeps_one(self):
        meetings = self.db.create_type("Meetings")
        task = self.db.create_task("Sync", type=meetings)
        self.db.delete_type(meetings, move_to="non-coding")
        self.assertEqual(self.db.get_task(task)["type"], "non-coding")
        with self.assertRaises(ValueError):
            self.db.delete_type("coding", move_to="coding")             # needs another type
        self.db.delete_type("coding", move_to="non-coding")
        with self.assertRaises(ValueError):
            self.db.delete_type("non-coding", move_to="non-coding")     # last one stays

    def test_default_follows_order(self):
        research = self.db.create_type("Research")
        self.db.move_type(research, -1)
        self.db.move_type(research, -1)
        self.assertEqual(self.db.default_type(), research)
        self.assertEqual(self.db.get_task(self.db.create_task("y"))["type"], research)

    def test_report_uses_type_names_colours_and_order(self):
        research = self.db.create_type("Research", color="#abcdef")
        self.db.move_type(research, -1)
        self.db.move_type(research, -1)
        day = date(2026, 10, 28)
        start = datetime.combine(day, datetime.min.time())
        for title, kind in [("Code", "coding"), ("Read", research)]:
            task = self.db.create_task(title, type=kind)
            self.db.add_session("focus", start, start + timedelta(minutes=25), 25, True,
                                task_id=task)
        rows = reports.effort_by(self.db, day, day, "type")
        self.assertEqual([(r.label, r.color) for r in rows],
                         [("Research", "#abcdef"), ("Coding", "#2a78d6")])


class UpgradeTests(unittest.TestCase):
    def test_v11_database_drops_the_type_rule_and_keeps_data(self):
        path = os.path.join(tempfile.mkdtemp(), "v11.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE, color TEXT NOT NULL DEFAULT '#888888');
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                category_id INTEGER REFERENCES categories(id),
                type TEXT NOT NULL DEFAULT 'coding'
                     CHECK (type IN ('coding', 'non-coding')),
                priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
                due_date TEXT, estimate_pomodoros INTEGER,
                status TEXT NOT NULL DEFAULT 'todo'
                     CHECK (status IN ('todo', 'in_progress', 'on_hold', 'done')),
                notes TEXT, created_at TEXT NOT NULL, completed_at TEXT,
                project_id INTEGER);
            CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id), kind TEXT NOT NULL,
                start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                duration_min REAL NOT NULL, completed INTEGER NOT NULL);
            INSERT INTO categories (name, color) VALUES ('Zeta', '#111111'), ('Alpha', '#222222');
            INSERT INTO tasks (title, type, category_id, created_at)
                VALUES ('Old', 'non-coding', 1, '2026-01-01');
            INSERT INTO sessions (task_id, kind, start_time, end_time, duration_min, completed)
                VALUES (1, 'focus', '2026-01-01T09:00:00', '2026-01-01T09:25:00', 25, 1);
        """)
        conn.commit()
        conn.close()

        db = Database(path)
        task = db.list_tasks("all")[0]
        self.assertEqual((task["title"], task["type"], task["pomodoros"]), ("Old", "non-coding", 1))
        research = db.create_type("Research")
        db.update_task(task["id"], type=research)                # was blocked before
        self.assertEqual(db.get_task(task["id"])["type"], research)
        # Old category order (alphabetical) is kept
        self.assertEqual([c["name"] for c in db.list_categories()][:2], ["Alpha", "Zeta"])
        self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        new = db.create_task("New task")                         # ids still increase
        self.assertGreater(new, task["id"])
        db.close()
        Database(path).close()                                    # opening again is fine


if __name__ == "__main__":
    unittest.main()
