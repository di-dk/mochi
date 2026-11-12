"""Saved conversations for the chat window: one JSON file per chat in workspace/chats/.

A chat keeps two things: the transcript (what the window shows) and Mochi's own message history, so opening an
old chat gives her back what she knew, with no need to explain everything again.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

ID_RE = re.compile(r"^[0-9a-z-]{8,48}$")
TITLE_MAX = 60


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)


def clean_messages(messages: list[dict]) -> list[dict]:
    """Her message history without the system prompt, and without bulky image data (kept as a text marker)."""
    out = []
    for m in messages[1:]:
        c = m.get("content")
        if isinstance(c, list):
            text = " ".join(p.get("text", "") for p in c if p.get("type") == "text")
            m = {**m, "content": (text or "[image]") + " (image no longer attached)"}
        out.append(m)
    return out


def title_from(text: str, files: list | None = None) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t and files:
        t = "Files: " + ", ".join(f["name"] for f in files[:3])
    return (t[:TITLE_MAX].rstrip() + ("…" if len(t) > TITLE_MAX else "")) or "New chat"


class ChatStore:
    def __init__(self, workspace: Path):
        self.dir = Path(workspace) / "chats"

    def _path(self, chat_id: str) -> Path | None:
        return self.dir / f"{chat_id}.json" if ID_RE.match(chat_id or "") else None

    def save(self, chat: dict) -> None:
        p = self._path(chat["id"])
        if p is None:
            raise ValueError("bad chat id")
        self.dir.mkdir(parents=True, exist_ok=True)
        chat["updated"] = time.time()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(chat, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)

    def load(self, chat_id: str) -> dict | None:
        p = self._path(chat_id)
        if p is None or not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list(self) -> list[dict]:
        out = []
        if self.dir.is_dir():
            for f in self.dir.glob("*.json"):
                try:
                    c = json.loads(f.read_text(encoding="utf-8"))
                    out.append({"id": c["id"], "title": c.get("title") or "New chat",
                                "updated": c.get("updated", 0), "count": len(c.get("transcript", []))})
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(out, key=lambda c: -c["updated"])

    def delete(self, chat_id: str) -> bool:
        p = self._path(chat_id)
        if p is None or not p.is_file():
            return False
        p.unlink()
        return True

    def rename(self, chat_id: str, title: str) -> bool:
        c = self.load(chat_id)
        title = re.sub(r"\s+", " ", title or "").strip()[:TITLE_MAX]
        if not c or not title:
            return False
        c["title"] = title
        self.save(c)
        return True
