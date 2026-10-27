"""Minimal Notion connection (optional): today's numbers to your Journal, the weekly review
to a page. The app keeps numbers and actions; Notion keeps words and reflection.

Setup (once): create an *internal integration* at https://www.notion.so/profile/integrations,
copy its token into Settings -> Notion, and share your Journal database and your weekly-review
page with the integration (••• -> Connections -> add it).
"""

import json
import re
import urllib.error
import urllib.request
from datetime import date

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TEXT_LIMIT = 2000          # Notion's limit per rich-text piece
APP_LINE = "Pomodoro Tracker –"


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
            raise NotionError("Notion can't find that page or database. Share it with your "
                              "integration (••• -> Connections) and check the link.")
        if status >= 400:
            raise NotionError(f"Notion error {status}: {data.get('message', 'unknown error')}")
        return data

    # ---------- checks ----------

    def database_title(self, database_id: str) -> str:
        data = self.request("GET", f"/databases/{database_id}")
        return plain_text(data.get("title", [])) or "(untitled)"

    def page_title(self, page_id: str) -> str:
        data = self.request("GET", f"/pages/{page_id}")
        for prop in data.get("properties", {}).values():
            if prop.get("type") == "title":
                return plain_text(prop["title"]) or "(untitled)"
        return "(untitled)"

    # ---------- journal ----------

    def journal_fields(self, database_id: str) -> dict:
        """Find the journal's title, date, type ('Daily') and 'What happened?' properties."""
        props = self.request("GET", f"/databases/{database_id}")["properties"]
        fields = {"title": None, "date": None, "type": None, "happened": None}
        for name, prop in props.items():
            kind = prop["type"]
            if kind == "title":
                fields["title"] = name
            elif kind == "date" and fields["date"] is None:
                fields["date"] = name
            elif kind == "select" and any(o["name"].lower() == "daily"
                                          for o in prop["select"].get("options", [])):
                fields["type"] = name
            elif kind == "rich_text" and "happen" in name.lower():
                fields["happened"] = name
        if fields["happened"] is None:   # fall back to the first text property
            fields["happened"] = next((n for n, p in props.items() if p["type"] == "rich_text"),
                                      None)
        if not fields["title"] or not fields["date"] or not fields["happened"]:
            raise NotionError("The journal needs a title, a date and a text property "
                              "(e.g. 'What happened?').")
        return fields

    def send_journal(self, database_id: str, day: date, summary: str) -> str:
        """Put today's numbers in the day's journal entry. Returns the entry's link.

        If an entry for the day exists, only the app's own line is added or replaced –
        anything you wrote stays untouched. Otherwise a new 'Daily' entry is created.
        """
        fields = self.journal_fields(database_id)
        conditions = [{"property": fields["date"], "date": {"equals": day.isoformat()}}]
        if fields["type"]:
            conditions.append({"property": fields["type"], "select": {"equals": "Daily"}})
        found = self.request("POST", f"/databases/{database_id}/query",
                             {"filter": {"and": conditions}, "page_size": 1})["results"]
        if found:
            page = found[0]
            current = plain_text(page["properties"][fields["happened"]]["rich_text"])
            kept = [line for line in current.split("\n") if not line.startswith(APP_LINE)]
            text = "\n".join([*[line for line in kept if line.strip()], summary])
            self.request("PATCH", f"/pages/{page['id']}", {"properties": {
                fields["happened"]: {"rich_text": rich_text(text)}}})
            return page.get("url", "")
        properties = {
            fields["title"]: {"title": rich_text(f"{day:%d %b %Y} – Daily check-in")},
            fields["date"]: {"date": {"start": day.isoformat()}},
            fields["happened"]: {"rich_text": rich_text(summary)},
        }
        if fields["type"]:
            properties[fields["type"]] = {"select": {"name": "Daily"}}
        page = self.request("POST", "/pages", {"parent": {"database_id": database_id},
                                               "properties": properties})
        return page.get("url", "")

    # ---------- weekly review ----------

    def send_weekly(self, parent_page_id: str, title: str, markdown: str) -> str:
        """Create a page under `parent_page_id` from the review's Markdown. Returns its link."""
        blocks = []
        for line in markdown.splitlines():
            if line.startswith("# "):
                continue                                    # the page title
            if line.startswith("## "):
                blocks.append({"object": "block", "type": "heading_2",
                               "heading_2": {"rich_text": rich_text(line[3:])}})
            elif line.startswith("- "):
                blocks.append({"object": "block", "type": "bulleted_list_item",
                               "bulleted_list_item": {"rich_text": rich_text(line[2:])}})
            elif line.strip():
                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": rich_text(line)}})
        page = self.request("POST", "/pages", {
            "parent": {"page_id": parent_page_id},
            "properties": {"title": {"title": rich_text(title)}},
            "children": blocks[:100]})                      # Notion's limit per request
        if len(blocks) > 100:
            self.request("PATCH", f"/blocks/{page['id']}/children", {"children": blocks[100:200]})
        return page.get("url", "")
