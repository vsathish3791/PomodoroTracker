"""Notion client tests with a fake transport - no network, no real token."""

import json
import unittest
from datetime import date

from pomodoro.notion import NotionClient, NotionError, parse_id, rich_text
from pomodoro.secret_store import protect, unprotect

JOURNAL = "5ab4bfab-ff69-43a6-aab1-eda3d3ac2b17"


def sample_log():
    from pomodoro.daylog import DayLog, TaskLine
    return DayLog(date(2026, 10, 29), 8, 3, 75, "low", "3/8 🍅",
                  completed=[TaskLine("Report", "Work", 2, 50)],
                  focus=[("Report", True)], habits=(1, 2), routines=(2, 3))


class FakeNotion:
    """Answers like Notion for the calls the app makes."""

    def __init__(self, existing=None, status=200, children=()):
        self.calls, self.existing, self.status = [], existing, status
        self.children = list(children)

    def __call__(self, method, url, headers, body):
        payload = json.loads(body) if body else None
        path = url.split("/v1")[1]
        self.calls.append((method, path, payload, headers))
        if self.status != 200:
            return self.status, b'{"message": "nope"}'
        if method == "POST" and path == "/databases":
            return 200, json.dumps({"id": "new-db", "url": "https://www.notion.so/Day-Log-11112222333344445555666677778888",
                                    "properties": {"Journal entry": {"relation": {
                                        "dual_property": {"synced_property_name":
                                                          "Related to Day Log (Journal entry)"}}}}
                                    }).encode()
        if method == "GET" and path.startswith("/databases/"):
            return 200, json.dumps({"title": [{"plain_text": "Journal"}],
                                    "parent": {"type": "page_id", "page_id": "hub-page"}}).encode()
        if method == "GET" and path.startswith("/pages/"):
            return 200, json.dumps({"properties": {"title": {"type": "title", "title": [
                {"plain_text": "06 Personal Life & Well-being"}]}}}).encode()
        if method == "GET" and "/children" in path:
            return 200, json.dumps({"results": [{"id": c} for c in self.children],
                                    "has_more": False}).encode()
        if path.endswith("/query"):
            return 200, json.dumps({"results": [self.existing] if self.existing else []}).encode()
        return 200, json.dumps({"id": "new-page", "url": "https://notion.so/new"}).encode()


class NotionTests(unittest.TestCase):
    def test_parse_id_from_links(self):
        self.assertEqual(parse_id("https://app.notion.com/p/0123456789abcdef0123456789abcdef?pvs=4"),
                         "01234567-89ab-cdef-0123-456789abcdef")
        self.assertEqual(parse_id("Journal-0123456789abcdef0123456789abcdef"),
                         "01234567-89ab-cdef-0123-456789abcdef")
        with self.assertRaises(NotionError):
            parse_id("not a link")

    def test_create_day_log_database_linked_to_journal(self):
        fake = FakeNotion()
        db_id, url = NotionClient("token", fake).create_day_log_database("parent", JOURNAL)
        self.assertEqual((db_id, url), ("new-db", "https://www.notion.so/Day-Log-11112222333344445555666677778888"))
        method, path, body, _ = fake.calls[0]
        self.assertEqual((method, path, body["parent"]["page_id"]), ("POST", "/databases", "parent"))
        self.assertEqual(body["properties"]["Journal entry"]["relation"]["database_id"], JOURNAL)
        self.assertEqual([o["name"] for o in body["properties"]["Energy signal"]["select"]["options"]],
                         ["High", "Steady", "Low", "Rest day", "No data"])
        # The Journal's side of the link is renamed "Day Log"; nothing else is changed
        self.assertEqual(fake.calls[1][:3], ("PATCH", f"/databases/{JOURNAL}", {
            "properties": {"Related to Day Log (Journal entry)": {"name": "Day Log"}}}))

    def test_send_day_log_creates_then_updates_the_same_page(self):
        log = sample_log()
        fake = FakeNotion()
        NotionClient("token", fake).send_day_log("daylog-db", log)
        method, path, body, _ = fake.calls[-1]
        self.assertEqual((method, path), ("POST", "/pages"))
        props = body["properties"]
        self.assertEqual(props["Energy signal"], {"select": {"name": "Low"}})
        self.assertEqual(props["Pomodoros"], {"number": 3})
        self.assertNotIn("Journal entry", props)            # the assistant sets that link
        self.assertEqual(body["children"][0]["type"], "paragraph")

        existing = {"id": "page-1", "url": "https://notion.so/p1", "properties": {}}
        fake = FakeNotion(existing, children=["old-1", "old-2"])
        url = NotionClient("token", fake).send_day_log("daylog-db", log)
        self.assertEqual(url, "https://notion.so/p1")
        calls = [(m, p) for m, p, _, _ in fake.calls]
        self.assertIn(("PATCH", "/pages/page-1"), calls)
        self.assertIn(("DELETE", "/blocks/old-1"), calls)
        self.assertIn(("DELETE", "/blocks/old-2"), calls)
        self.assertEqual(calls[-1], ("PATCH", "/blocks/page-1/children"))
        self.assertNotIn(("POST", "/pages"), calls)          # one page per date

    def test_parent_page_of_the_journal(self):
        fake = FakeNotion()
        self.assertEqual(NotionClient("token", fake).parent_page(JOURNAL),
                         ("hub-page", "06 Personal Life & Well-being"))

    def test_weekly_page_blocks(self):
        fake = FakeNotion()
        md = "# Weekly review\n\n## 1. Planned\n- Goal A\n\n## 3. Problems\n- Late"
        NotionClient("token", fake).send_weekly("parent-id", "Weekly review – 26 Oct", md)
        body = fake.calls[-1][2]
        self.assertEqual(body["parent"], {"page_id": "parent-id"})
        self.assertEqual([b["type"] for b in body["children"]],
                         ["heading_2", "bulleted_list_item", "heading_2", "bulleted_list_item"])

    def test_friendly_errors(self):
        with self.assertRaisesRegex(NotionError, "token"):
            NotionClient("bad", FakeNotion(status=401)).database_title(JOURNAL)
        with self.assertRaisesRegex(NotionError, "Add your integration"):
            NotionClient("ok", FakeNotion(status=404)).database_title(JOURNAL)
        with self.assertRaises(NotionError):
            NotionClient("")

    def test_long_text_is_split_and_secrets_round_trip(self):
        self.assertEqual([len(p["text"]["content"]) for p in rich_text("x" * 4500)],
                         [2000, 2000, 500])
        stored = protect("secret_abc")
        self.assertNotIn("secret_abc", stored)
        self.assertEqual(unprotect(stored), "secret_abc")


class NotionOptionalTests(unittest.TestCase):
    """Notion is off for new users and stays on for people who already set it up."""

    def test_new_user_has_notion_off(self):
        from pomodoro.database import Database
        from pomodoro.ui.notion_ui import is_connected, notion_enabled
        db = Database(":memory:")
        self.assertFalse(notion_enabled(db))
        self.assertFalse(is_connected(db))
        db.close()

    def test_existing_setup_turns_it_on_until_chosen(self):
        from pomodoro.database import Database
        from pomodoro.ui.notion_ui import is_connected, notion_enabled
        db = Database(":memory:")
        db.create_task("Plan", notion_url="https://www.notion.so/Plan-0123")
        self.assertTrue(notion_enabled(db))
        db.set_setting("notion_token", protect("secret_x"))
        self.assertTrue(is_connected(db))
        db.set_setting("notion_enabled", False)          # switched off in Settings
        self.assertFalse(notion_enabled(db))
        self.assertFalse(is_connected(db))
        db.close()

    def test_other_links_do_not_count_as_notion(self):
        from pomodoro.database import Database
        from pomodoro.ui.notion_ui import notion_enabled
        db = Database(":memory:")
        db.create_task("Read doc", notion_url="https://docs.google.com/document/d/1")
        self.assertFalse(notion_enabled(db))
        db.close()


if __name__ == "__main__":
    unittest.main()
