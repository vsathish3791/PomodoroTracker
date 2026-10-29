"""Minimal Notion connection (optional): the day's facts to a "Day Log" database, the
weekly review to a page. The app keeps facts and actions; your journal entry itself is
written in Notion (e.g. by your Notion AI journaling assistant reading the Day Log).

Setup (once): create an *internal integration* at https://www.notion.so/profile/integrations,
copy its token into Settings -> Notion, and add the integration to the page that holds your
Journal and Day Log (••• -> Connections), and to your weekly-review page.
"""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TEXT_LIMIT = 2000          # Notion's limit per rich-text piece
# Energy signal (energy.py) -> Day Log select option (name, colour)
ENERGY_OPTIONS = [("High", "green"), ("Steady", "blue"), ("Low", "orange"),
                  ("Rest day", "gray"), ("No data", "default")]
ENERGY_NAMES = {"high": "High", "steady": "Steady", "low": "Low", "rest": "Rest day",
                "none": "No data"}


class NotionError(Exception):
    """A problem talking to Notion, with a message fit to show the user."""


def parse_id(url_or_id: str) -> str:
    """Notion page/database id from a link or an id (with or without dashes)."""
    text = (url_or_id or "").strip()
    # Ids are 32 hex characters; in links they're the last such run before any '?'
    match = re.findall(r"[0-9a-fA-F]{32}", text.split("?")[0].replace("-", ""))
    if not match:
        raise NotionError("That doesn't look like a Notion link.")
    raw = match[-1].lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[i:i + TEXT_LIMIT]}}
            for i in range(0, max(len(text), 1), TEXT_LIMIT)] if text else []


def plain_text(parts: list[dict]) -> str:
    return "".join(p.get("plain_text") or p.get("text", {}).get("content", "") for p in parts)


class NotionClient:
    def __init__(self, token: str, transport=None, timeout: int = 15):
        if not token:
            raise NotionError("Add your Notion integration token in Settings -> Notion first.")
        self.token = token
        self.timeout = timeout
        self.transport = transport or self._urllib

    def _urllib(self, method: str, url: str, headers: dict, body: bytes | None):
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise NotionError(f"Can't reach Notion – check your internet connection. ({error})")

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION,
                   "Content-Type": "application/json"}
        status, raw = self.transport(method, API + path, headers,
                                     json.dumps(body).encode("utf-8") if body is not None else None)
        data = json.loads(raw or b"{}")
        if status == 401:
            raise NotionError("Notion didn't accept the token. Check it in Settings -> Notion.")
        if status == 404:
            raise NotionError("Notion can't find that page or database. Add your integration "
                              "to it (••• -> Connections) and check the link. "
                              f"(Notion: {data.get('message', 'not found')})")
        if status >= 400:
            raise NotionError(f"Notion error {status}: {data.get('message', 'unknown error')}")
        return data

    # ---------- checks ----------

    def whoami(self) -> str:
        """The integration's name and workspace, e.g. 'Pomodoro Tracker in My Workspace'."""
        data = self.request("GET", "/users/me")
        workspace = data.get("bot", {}).get("workspace_name") or "your workspace"
        return f"“{data.get('name') or 'integration'}” in {workspace}"

    def database_title(self, database_id: str) -> str:
        data = self.request("GET", f"/databases/{database_id}")
        return plain_text(data.get("title", [])) or "(untitled)"

    def page_title(self, page_id: str) -> str:
        data = self.request("GET", f"/pages/{page_id}")
        for prop in data.get("properties", {}).values():
            if prop.get("type") == "title":
                return plain_text(prop["title"]) or "(untitled)"
        return "(untitled)"

    # ---------- day log ----------

    def parent_page(self, database_id: str) -> tuple[str, str]:
        """(id, title) of the page that holds a database - e.g. where your Journal lives."""
        parent = self.request("GET", f"/databases/{database_id}").get("parent", {})
        if parent.get("type") == "block_id":          # inline in a page, inside a block
            parent = self.request("GET", f"/blocks/{parent['block_id']}").get("parent", {})
        if parent.get("type") != "page_id":
            raise NotionError("Couldn't find the page that holds your Journal. "
                              "Paste the link of the page to put the Day Log in.")
        return parent["page_id"], self.page_title(parent["page_id"])

    def create_day_log_database(self, parent_page_id: str,
                                journal_id: str | None = None) -> tuple[str, str]:
        """Create the "Day Log" database under a page. Returns (id, link).

        With `journal_id`, it is linked both ways with your Journal: Day Log gets
        "Journal entry", and your Journal gets a "Day Log" property. Nothing else in the
        Journal changes.
        """
        text = {"rich_text": {}}
        properties = {
            "Name": {"title": {}}, "Date": {"date": {}},
            "Pomodoros": {"number": {}}, "Daily goal": {"number": {}},
            "Focus minutes": {"number": {}}, "Tasks done": {"number": {}},
            "Today's focus": text, "Habits": text, "Routines": text, "Interruptions": text,
            "Energy signal": {"select": {"options": [
                {"name": name, "color": color} for name, color in ENERGY_OPTIONS]}},
            "Energy reason": text, "Sent at": {"date": {}},
        }
        if journal_id:
            properties["Journal entry"] = {"relation": {
                "database_id": journal_id, "type": "dual_property", "dual_property": {}}}
        created = self.request("POST", "/databases", {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": rich_text("Day Log"), "icon": {"type": "emoji", "emoji": "🍅"},
            "properties": properties})
        if journal_id:          # name the Journal's side of the link "Day Log"
            relation = created["properties"].get("Journal entry", {}).get("relation", {})
            synced = relation.get("dual_property", {}).get("synced_property_name")
            if synced and synced != "Day Log":
                try:
                    self.request("PATCH", f"/databases/{journal_id}", {
                        "properties": {synced: {"name": "Day Log"}}})
                except NotionError:
                    pass        # the link works either way; only its name differs
        return created["id"], created.get("url", "")

    def send_day_log(self, database_id: str, log) -> str:
        """Create or update the day's page in the Day Log database. Returns its link.

        One page per date: sending again refreshes the facts and the page body, and
        leaves the link to your Journal entry alone. `log` is a daylog.DayLog.
        """
        properties = {
            "Name": {"title": rich_text(log.title)},
            "Date": {"date": {"start": log.day.isoformat()}},
            "Pomodoros": {"number": log.pomodoros},
            "Daily goal": {"number": log.goal},
            "Focus minutes": {"number": log.focus_minutes},
            "Tasks done": {"number": len(log.completed)},
            "Today's focus": {"rich_text": rich_text(log.focus_text)},
            "Habits": {"rich_text": rich_text(f"{log.habits[0]}/{log.habits[1]}")},
            "Routines": {"rich_text": rich_text(f"{log.routines[0]}/{log.routines[1]}")},
            "Interruptions": {"rich_text": rich_text(log.interruptions_text())},
            "Energy signal": {"select": {"name": ENERGY_NAMES[log.energy]}},
            "Energy reason": {"rich_text": rich_text(log.energy_reason)},
            "Sent at": {"date": {"start": datetime.now().isoformat(timespec="minutes")}},
        }
        blocks = markdown_blocks(log.markdown())
        found = self.request("POST", f"/databases/{database_id}/query", {
            "filter": {"property": "Date", "date": {"equals": log.day.isoformat()}},
            "page_size": 1})["results"]
        if found:
            page = found[0]
            self.request("PATCH", f"/pages/{page['id']}", {"properties": properties})
            self._replace_children(page["id"], blocks)
            return page.get("url", "")
        page = self.request("POST", "/pages", {"parent": {"database_id": database_id},
                                               "properties": properties,
                                               "children": blocks[:100]})
        self._append_children(page["id"], blocks[100:])
        return page.get("url", "")

    def _replace_children(self, block_id: str, blocks: list[dict]):
        old, cursor = [], None
        while True:
            data = self.request("GET", f"/blocks/{block_id}/children?page_size=100"
                                + (f"&start_cursor={cursor}" if cursor else ""))
            old += [b["id"] for b in data.get("results", [])]
            cursor = data.get("next_cursor")
            if not data.get("has_more") or not cursor:
                break
        for child in old:
            self.request("DELETE", f"/blocks/{child}")
        self._append_children(block_id, blocks)

    def _append_children(self, block_id: str, blocks: list[dict]):
        for start in range(0, len(blocks), 100):                # Notion's limit per request
            self.request("PATCH", f"/blocks/{block_id}/children",
                         {"children": blocks[start:start + 100]})

    # ---------- weekly review ----------

    def send_weekly(self, parent_page_id: str, title: str, markdown: str) -> str:
        """Create a page under `parent_page_id` from the review's Markdown. Returns its link."""
        blocks = markdown_blocks(markdown)
        page = self.request("POST", "/pages", {
            "parent": {"page_id": parent_page_id},
            "properties": {"title": {"title": rich_text(title)}},
            "children": blocks[:100]})                      # Notion's limit per request
        self._append_children(page["id"], blocks[100:])
        return page.get("url", "")


def markdown_blocks(markdown: str) -> list[dict]:
    """Notion blocks from simple Markdown: '## ' headings, '- ' bullets, paragraphs.
    The '# ' title line is skipped (it's the page title)."""
    blocks = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": rich_text(line[3:])}})
        elif line.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": rich_text(line[2:])}})
        elif line.strip():
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": rich_text(line)}})
    return blocks
