"""Mochi's own window: a small local web page (chat bubbles, her avatar, approval buttons) shown in a native
window with pywebview. It drives the same Agent as the terminal.

  mochi --gui

Safety: the server listens on 127.0.0.1 only, every request needs a random per-run token, and the Host header
must be the local address (stops other web pages from talking to her). Files are served only from her workspace
and only if they are images.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import attach
from .history import ChatStore, clean_messages, new_id, title_from
from .core import ROOT, STOPPED, Agent, ensure_llm, list_models, make_policy, save_local_setting

WEB = Path(__file__).parent / "web"
IMAGE_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
             ".gif": "image/gif"}
PATH_RE = re.compile(r"""(?:[A-Za-z]:[\\/]|\.{0,2}[\\/])?[^\s"'<>|*?:]+\.(?:png|jpe?g|webp|gif)""", re.I)
MAX_EVENTS = 20000
THEMES = ("auto", "mochi-dark", "mochi-light", "sakura", "lavender", "mint", "midnight", "ocean",
          "forest", "sunset", "graphite")
MAX_UPLOAD = 2 * 1024**3          # 2 GB per file


class Bus:
    """Append-only event log that the page reads with long polling."""

    def __init__(self):
        self.events: list[dict] = []
        self.base = 0
        self.cv = threading.Condition()

    def push(self, kind: str, **data) -> None:
        with self.cv:
            if len(self.events) >= MAX_EVENTS:
                drop = MAX_EVENTS // 2
                del self.events[:drop]
                self.base += drop
            self.events.append({"id": self.base + len(self.events) + 1, "kind": kind, **data})
            self.cv.notify_all()

    def since(self, last: int, timeout: float = 20.0) -> list[dict]:
        with self.cv:
            if self.base + len(self.events) <= last:
                self.cv.wait(timeout)
            return self.events[max(0, last - self.base):]


class GuiApp:
    """Everything the window needs, with no HTTP or window code in it so it can be tested directly."""

    def __init__(self, cfg: dict, make_agent=None):
        self.cfg = cfg
        self.bus = Bus()
        self.token = secrets.token_urlsafe(24)
        self.agent: Agent | None = None
        self.busy = False
        self.error = ""
        self._make_agent = make_agent
        self.store: ChatStore | None = None
        self.chat_id: str | None = None
        self.created = 0.0
        self.title = ""
        self.transcript: list[dict] = []
        self._approvals: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ start-up
    def start_agent(self) -> None:
        def boot():
            try:
                self.bus.push("status", text="Waking her up…")
                if self._make_agent:
                    self.agent = self._make_agent(self)
                else:
                    ensure_llm(self.cfg, log=lambda s: self.bus.push("status", text=s))
                    self.agent = Agent(self.cfg, make_policy(self.cfg, approver=self.approve),
                                       on_event=self.on_event)
                self.store = ChatStore(self.agent.policy.workspace)
                self.bus.push("ready", model=self.cfg["llm"]["model"], tools=len(self.agent.registry.tools),
                              workspace=str(self.agent.policy.workspace))
            except Exception as e:  # noqa: BLE001
                self.error = f"{type(e).__name__}: {e}"
                self.bus.push("fatal", text=self.error)
        threading.Thread(target=boot, daemon=True).start()

    def info(self) -> dict:
        return {"name": self.cfg["agent"]["name"], "model": self.cfg["llm"]["model"], "ready": self.agent is not None,
                "busy": self.busy, "error": self.error}

    # ------------------------------------------------------------------ agent -> page
    def on_event(self, kind: str, data: dict) -> None:
        if kind == "token":
            self.bus.push("token", text=data["text"])
        elif kind == "thinking":
            self.bus.push("thinking")
        elif kind == "tool_call":
            self.bus.push("tool_call", name=data["name"], args=str(data["args"])[:600])
            self.transcript.append({"t": "step", "name": data["name"], "args": str(data["args"])[:600],
                                    "result": "", "error": False})
        elif kind == "tool_result":
            result = str(data["result"])
            err = result.startswith(("ERROR", "DENIED"))
            self.bus.push("tool_result", name=data["name"], result=result[:1500], error=err)
            for item in reversed(self.transcript):
                if item["t"] == "step":
                    item["result"], item["error"] = result[:1500], err
                    break
            self._pictures(result)
        elif kind == "note":
            self.transcript.append({"t": "bot", "text": data["text"]})
        elif kind in ("skill", "steer", "check", "nudge", "condense", "image"):
            self.bus.push("info", what=kind, text=str(data.get("name") or data.get("text") or ""))

    def _pictures(self, text: str) -> None:
        """Show images the tools just made, when they sit inside her workspace."""
        if not self.agent:
            return
        seen = set()
        for m in PATH_RE.findall(text):
            try:
                p = self.agent.policy.resolve(m)
                rel = p.relative_to(self.agent.policy.workspace.resolve()).as_posix()
            except Exception:  # noqa: BLE001
                continue
            if rel not in seen and p.is_file():
                seen.add(rel)
                self.bus.push("picture", rel=rel, name=p.name)
                self.transcript.append({"t": "picture", "rel": rel, "name": p.name})
                if len(seen) >= 4:
                    break

    # ------------------------------------------------------------------ approvals
    def approve(self, category: str, summary: str) -> str:
        aid = secrets.token_hex(6)
        slot = {"event": threading.Event(), "answer": "n"}
        with self._lock:
            self._approvals[aid] = slot
        self.bus.push("approval", aid=aid, category=category, summary=summary)
        while not slot["event"].wait(0.5):
            if self.agent is not None and self.agent.stop.is_set():
                slot["answer"] = "n"
                break
        with self._lock:
            self._approvals.pop(aid, None)
        self.bus.push("approval_done", aid=aid, answer=slot["answer"])
        return slot["answer"]

    def answer(self, aid: str, answer: str) -> bool:
        with self._lock:
            slot = self._approvals.get(aid)
        if not slot or answer not in ("y", "n", "a"):
            return False
        slot["answer"] = answer
        slot["event"].set()
        return True

    # ------------------------------------------------------------------ page -> agent
    def _upload_paths(self, rels: list) -> list[Path]:
        """Turn the page's uploaded-file names into real paths, only ones inside workspace/uploads."""
        up = (self.agent.policy.workspace / attach.UPLOADS).resolve()
        out = []
        for rel in rels or []:
            p = (self.agent.policy.workspace / str(rel)).resolve()
            try:
                p.relative_to(up)
            except ValueError:
                continue
            if p.is_file():
                out.append(p)
        return out

    def save_upload(self, name: str, reader, length: int) -> dict:
        """Store one uploaded file under workspace/uploads and report where."""
        if self.agent is None:
            raise RuntimeError("starting")
        if length <= 0 or length > MAX_UPLOAD:
            raise ValueError("file is empty or over 2 GB")
        up = self.agent.policy.workspace / attach.UPLOADS
        up.mkdir(parents=True, exist_ok=True)
        dest = attach.unique(up, attach.safe_name(name))
        left = length
        with dest.open("wb") as f:
            while left > 0:
                chunk = reader(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            dest.unlink(missing_ok=True)
            raise ValueError("upload was cut short")
        rel = dest.relative_to(self.agent.policy.workspace.resolve()).as_posix()
        return {"rel": rel, "name": dest.name, "image": dest.suffix.lower() in IMAGE_EXT, "size": length}

    def send(self, text: str, files: list | None = None) -> str:
        text = (text or "").strip()
        paths = self._upload_paths(files) if self.agent is not None else []
        if not text and not paths:
            return "empty"
        if self.agent is None:
            return "starting"
        if text.lower() in ("/stop", "stop"):
            self.stop()
            return "stopping"
        if text == "/reset":
            if self.busy:
                return "busy"
            return self.new_chat()
        shown = [{"name": p.name, "rel": p.relative_to(self.agent.policy.workspace.resolve()).as_posix(),
                  "image": p.suffix.lower() in IMAGE_EXT} for p in paths]
        if self.busy:
            note = self.agent.attach_note(paths)[0] if paths else ""
            self.agent.inbox.put(text + note)
            self.bus.push("user", text=text, queued=True, files=shown)
            self.transcript.append({"t": "user", "text": text, "files": shown, "queued": True})
            return "queued"
        self.bus.push("user", text=text, queued=False, files=shown)
        self.transcript.append({"t": "user", "text": text, "files": shown})
        self.busy = True
        threading.Thread(target=self._run, args=(text, paths), daemon=True).start()
        return "started"

    def _run(self, text: str, paths: list | None = None) -> None:
        t0 = time.time()
        self.bus.push("busy")
        try:
            answer = self.agent.run(text, attachments=paths or None)
            secs = round(time.time() - t0)
            last = self.transcript[-1] if self.transcript else None
            if answer.strip() and not (last and last["t"] == "bot" and last["text"].strip() == answer.strip()):
                self.transcript.append({"t": "bot", "text": answer})
            self.transcript.append({"t": "meta", "text": f"{secs}s" + (" · stopped" if answer == STOPPED else "")})
            self.bus.push("done", answer=answer, secs=secs, stopped=answer == STOPPED)
        except Exception as e:  # noqa: BLE001
            self.bus.push("error", text=f"{type(e).__name__}: {e}")
        finally:
            self.busy = False
            self._save()
            self.bus.push("idle")

    # ------------------------------------------------------------------ saved chats
    def _save(self) -> None:
        """Write the current chat (what the window shows + what she remembers) to workspace/chats."""
        if not self.transcript or self.store is None or self.agent is None:
            return
        try:
            if self.chat_id is None:
                self.chat_id, self.created = new_id(), time.time()
            if not self.title:
                first = next((i for i in self.transcript if i["t"] == "user"), {})
                self.title = title_from(first.get("text", ""), first.get("files"))
            self.store.save({"id": self.chat_id, "title": self.title, "created": self.created,
                             "transcript": self.transcript, "messages": clean_messages(self.agent.messages)})
            self.bus.push("chats")
        except Exception as e:  # noqa: BLE001
            self.bus.push("status", text=f"Could not save this chat: {e}")

    def chats(self) -> dict:
        return {"chats": self.store.list() if self.store else [], "current": self.chat_id}

    def state(self) -> dict:
        """Everything a freshly opened page needs, plus where to start listening for new events."""
        with self.bus.cv:
            since = self.bus.base + len(self.bus.events)
        return {**self.info(), "theme": self.theme(), "since": since, "chat_id": self.chat_id, "transcript": list(self.transcript),
                "workspace": str(self.agent.policy.workspace) if self.agent else "",
                "tools": len(self.agent.registry.tools) if self.agent else 0}

    def theme(self) -> str:
        t = (self.cfg.get("ui") or {}).get("theme", "auto")
        return t if t in THEMES else "auto"

    def set_theme(self, name: str) -> str:
        if name not in THEMES:
            return "unknown theme"
        self.cfg.setdefault("ui", {})["theme"] = name
        try:
            save_local_setting("ui", "theme", name)
        except OSError as e:
            return f"could not save: {e}"
        return "ok"

    def new_chat(self) -> str:
        if self.busy or self.agent is None:
            return "busy"
        self._save()
        self.agent.reset()
        self.agent.policy.session_allowed.clear()
        self.chat_id, self.title, self.created, self.transcript = None, "", 0.0, []
        self.bus.push("loaded", chat_id=None, transcript=[])
        return "ok"

    def open_chat(self, chat_id: str) -> str:
        if self.busy or self.agent is None or self.store is None:
            return "busy"
        chat = self.store.load(chat_id)
        if not chat:
            return "not found"
        if chat_id != self.chat_id:
            self._save()
        self.agent.messages = [self.agent.system_message()] + list(chat.get("messages") or [])
        self.agent.policy.session_allowed.clear()
        self.chat_id, self.title, self.created = chat["id"], chat.get("title", ""), chat.get("created", time.time())
        self.transcript = list(chat.get("transcript") or [])
        self.bus.push("loaded", chat_id=self.chat_id, transcript=self.transcript)
        return "ok"

    def delete_chat(self, chat_id: str) -> str:
        if self.store is None:
            return "starting"
        if chat_id == self.chat_id:
            if self.busy:
                return "busy"
            self.transcript = []               # do not re-save a chat that is being deleted
            self.new_chat()
        ok = self.store.delete(chat_id)
        self.bus.push("chats")
        return "ok" if ok else "not found"

    def rename_chat(self, chat_id: str, title: str) -> str:
        if self.store is None or not self.store.rename(chat_id, title):
            return "could not rename"
        if chat_id == self.chat_id:
            self.title = title.strip()[:60]
        self.bus.push("chats")
        return "ok"

    def stop(self) -> None:
        if self.agent is not None:
            self.agent.stop.set()
        with self._lock:
            for slot in self._approvals.values():
                slot["answer"] = "n"
                slot["event"].set()

    def models(self) -> list[dict]:
        out = []
        for m in list_models(self.cfg):
            out.append({"key": m["modelKey"], "tools": bool(m.get("trainedForToolUse")), "vision": bool(m.get("vision")),
                        "gb": round(m.get("sizeBytes", 0) / 2**30, 1), "current": m["modelKey"] == self.cfg["llm"]["model"]})
        return out

    def set_model(self, key: str) -> str:
        if self.busy or self.agent is None:
            return "busy"
        keys = {m["modelKey"] for m in list_models(self.cfg)}
        if key not in keys:
            return "unknown model"
        old = self.cfg["llm"]["model"]
        if key == old:
            return "ok"
        self.cfg["llm"]["model"] = key
        self.bus.push("status", text=f"Loading {key} (about a minute)…")
        try:
            ensure_llm(self.cfg, log=lambda s: None)
        except Exception as e:  # noqa: BLE001
            self.cfg["llm"]["model"] = old
            return f"Could not load {key}: {e}"
        save_local_setting("llm", "model", key)
        self.agent.refresh_model_info()
        self.agent.messages[0] = self.agent.system_message()
        self.bus.push("ready", model=key, tools=len(self.agent.registry.tools),
                      workspace=str(self.agent.policy.workspace))
        return "ok"


def make_handler(app: GuiApp, host_header: str):
    page = (WEB / "index.html").read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # quiet
            pass

        # -- helpers
        def _send(self, code: int, body: bytes, ctype: str = "application/json", extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode("utf-8"))

        def _ok(self) -> bool:
            if self.headers.get("Host", "") != host_header:
                self._json({"error": "bad host"}, 403)
                return False
            q = parse_qs(urlparse(self.path).query)
            tok = self.headers.get("X-Mochi-Token") or (q.get("t") or [""])[0]
            if not secrets.compare_digest(tok, app.token):
                self._json({"error": "bad token"}, 403)
                return False
            return True

        # -- routes
        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._ok():
                return
            if u.path == "/":
                theme = app.theme()
                html = (page.replace("__TOKEN__", app.token).replace("__NAME__", app.cfg["agent"]["name"])
                        .replace("__THEMEATTR__", "" if theme == "auto" else f'data-theme="{theme}"'))
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/avatar.png":
                f = ROOT / "assets" / "mochi_small.png"
                self._send(200, f.read_bytes() if f.exists() else b"", "image/png")
            elif u.path == "/info":
                self._json(app.info())
            elif u.path == "/state":
                self._json(app.state())
            elif u.path == "/chats":
                self._json(app.chats())
            elif u.path == "/poll":
                last = int((q.get("since") or ["0"])[0])
                self._json({"events": app.bus.since(last)})
            elif u.path == "/models":
                try:
                    self._json({"models": app.models()})
                except Exception as e:  # noqa: BLE001
                    self._json({"models": [], "error": str(e)})
            elif u.path == "/file":
                self._file((q.get("p") or [""])[0])
            else:
                self._json({"error": "not found"}, 404)

        def _file(self, rel: str):
            ext = Path(rel).suffix.lower()
            if app.agent is None or ext not in IMAGE_EXT:
                return self._json({"error": "not allowed"}, 403)
            ws = app.agent.policy.workspace.resolve()
            try:
                p = (ws / rel).resolve()
                p.relative_to(ws)
            except Exception:  # noqa: BLE001
                return self._json({"error": "not allowed"}, 403)
            if not p.is_file() or app.agent.policy.is_denied(p):
                return self._json({"error": "not found"}, 404)
            self._send(200, p.read_bytes(), IMAGE_EXT[ext])

        def do_POST(self):
            if not self._ok():
                return
            n = int(self.headers.get("Content-Length") or 0)
            if urlparse(self.path).path == "/upload":
                name = unquote((parse_qs(urlparse(self.path).query).get("name") or ["file"])[0])
                try:
                    return self._json(app.save_upload(name, self.rfile.read, n))
                except Exception as e:  # noqa: BLE001
                    self.close_connection = True
                    return self._json({"error": str(e)}, 400)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            path = urlparse(self.path).path
            if path == "/send":
                self._json({"status": app.send(str(body.get("text", "")), body.get("files") or [])})
            elif path == "/stop":
                app.stop()
                self._json({"status": "stopping"})
            elif path == "/approve":
                self._json({"ok": app.answer(str(body.get("id", "")), str(body.get("answer", "")))})
            elif path == "/theme":
                self._json({"status": app.set_theme(str(body.get("name", "")))})
            elif path == "/chat/new":
                self._json({"status": app.new_chat()})
            elif path == "/chat/open":
                self._json({"status": app.open_chat(str(body.get("id", "")))})
            elif path == "/chat/delete":
                self._json({"status": app.delete_chat(str(body.get("id", "")))})
            elif path == "/chat/rename":
                self._json({"status": app.rename_chat(str(body.get("id", "")), str(body.get("title", "")))})
            elif path == "/model":
                self._json({"status": app.set_model(str(body.get("key", "")))})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(app: GuiApp) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: None)
    port = srv.server_address[1]
    host = f"127.0.0.1:{port}"
    srv.RequestHandlerClass = make_handler(app, host)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{host}/?t={app.token}"


def run_gui(cfg: dict) -> int:
    app = GuiApp(cfg)
    srv, url = serve(app)
    app.start_agent()
    try:
        import webview
    except ImportError:
        import webbrowser
        print(f"pywebview is not installed; opening your browser instead.\n{url}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    icon = ROOT / "assets" / "mochi.ico"
    webview.create_window(cfg["agent"]["name"], url, width=1000, height=760, min_size=(520, 480),
                          background_color="#17121c")
    webview.start(icon=str(icon) if icon.exists() else None)
    app.stop()
    srv.shutdown()
    return 0
