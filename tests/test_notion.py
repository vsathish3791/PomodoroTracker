"""Notion client tests with a fake transport - no network, no real token."""

import json
import unittest
from datetime import date

from pomodoro.notion import NotionClient, NotionError, parse_id, rich_text
from pomodoro.secret_store import protect, unprotect

JOURNAL = "5ab4bfab-ff69-43a6-aab1-eda3d3ac2b17"
SCHEMA = {"properties": {
    "Entry Name": {"type": "title"}, "Date": {"type": "date"},
    "Type": {"type": "select", "select": {"options": [{"name": "Daily"}, {"name": "Weekly"}]}},
    "What happened?": {"type": "rich_text"}, "What did I learn?": {"type": "rich_text"}}}


class FakeNotion:
    def __init__(self, existing=None, status=200):
        self.calls, self.existing, self.status = [], existing, status

    def __call__(self, method, url, headers, body):
        payload = json.loads(body) if body else None
        self.calls.append((method, url.split("/v1")[1], payload, headers))
        if self.status != 200:
            return self.status, b'{"message": "nope"}'
        if method == "GET" and "/databases/" in url:
            return 200, json.dumps(SCHEMA).encode()
        if url.endswith("/query"):
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

    def test_new_journal_entry(self):
        fake = FakeNotion()
        url = NotionClient("token", fake).send_journal(JOURNAL, date(2026, 10, 27),
                                                       "Pomodoro Tracker – Tue: 6 pomodoros.")
        self.assertEqual(url, "https://notion.so/new")
        method, path, body, headers = fake.calls[-1]
        self.assertEqual((method, path), ("POST", "/pages"))
        self.assertEqual(headers["Authorization"], "Bearer token")
        props = body["properties"]
        self.assertEqual(props["Type"], {"select": {"name": "Daily"}})
        self.assertEqual(props["Date"]["date"]["start"], "2026-10-27")
        self.assertEqual(props["What happened?"]["rich_text"][0]["text"]["content"],
                         "Pomodoro Tracker – Tue: 6 pomodoros.")

    def test_existing_entry_keeps_your_text_and_replaces_only_the_app_line(self):
        existing = {"id": "abc", "url": "https://notion.so/abc", "properties": {
            "What happened?": {"rich_text": [{"plain_text":
                "Good meeting with the team.\nPomodoro Tracker – Tue: 3 pomodoros."}]}}}
        fake = FakeNotion(existing)
        NotionClient("token", fake).send_journal(JOURNAL, date(2026, 10, 27),
                                                 "Pomodoro Tracker – Tue: 6 pomodoros.")
        method, path, body, _ = fake.calls[-1]
        self.assertEqual((method, path), ("PATCH", "/pages/abc"))
        text = body["properties"]["What happened?"]["rich_text"][0]["text"]["content"]
        self.assertEqual(text, "Good meeting with the team.\nPomodoro Tracker – Tue: 6 pomodoros.")

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


if __name__ == "__main__":
    unittest.main()
