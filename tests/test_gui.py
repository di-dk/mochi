"""Offline tests for the chat window's server: auth, chat flow, approvals, stop, image serving."""
import copy
import json
import queue
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from agent.core import STOPPED, load_config
from agent.gui import GuiApp, serve


class FakeAgent:
    def __init__(self, app, ws):
        self.app = app
        self.stop = threading.Event()
        self.inbox = queue.Queue()
        self.registry = SimpleNamespace(tools={"a": 1, "b": 2})
        self.policy = SimpleNamespace(workspace=ws, resolve=lambda p: (ws / p) if not str(p).startswith("/") else ws / p,
                                      is_denied=lambda p: p.name.startswith("secret"), session_allowed={"x"})
        self.reset_called = False

    def run(self, text):
        self.stop.clear()
        if text == "ask":
            ans = self.app.approve("write_outside", "Write C:/x")
            return f"approval was {ans}"
        if text == "slow":
            for _ in range(100):
                if self.stop.is_set():
                    return STOPPED
                time.sleep(0.05)
        if text == "pic":
            (self.policy.workspace / "out.png").write_bytes(b"\x89PNG fake")
            (self.policy.workspace / "secret.png").write_bytes(b"x")
            self.app.on_event("tool_result", {"name": "comfy_txt2img", "result": "saved out.png and secret.png"})
            return "done pic"
        self.app.on_event("tool_call", {"name": "wait", "args": '{"seconds": 1}'})
        self.app.on_event("token", {"text": "hello "})
        self.app.on_event("token", {"text": text})
        return "hello " + text

    def reset(self):
        self.reset_called = True


@pytest.fixture
def gui(tmp_path):
    cfg = copy.deepcopy(load_config())
    ws = tmp_path / "ws"
    ws.mkdir()
    app = GuiApp(cfg, make_agent=lambda a: FakeAgent(a, ws))
    srv, url = serve(app)
    base = url.split("/?")[0]
    h = {"X-Mochi-Token": app.token}
    app.start_agent()
    for _ in range(100):
        if app.agent:
            break
        time.sleep(0.02)
    yield app, base, h
    srv.shutdown()


def poll(base, h, since=0, until=None, tries=60):
    seen = []
    for _ in range(tries):
        evs = httpx.get(f"{base}/poll?since={since}", headers=h, timeout=30).json()["events"]
        for e in evs:
            since = e["id"]
            seen.append(e)
        if until and any(e["kind"] == until for e in seen):
            return seen
    return seen


def test_requires_token_and_local_host(gui):
    app, base, h = gui
    assert httpx.get(f"{base}/info").status_code == 403
    assert httpx.get(f"{base}/info", headers={"X-Mochi-Token": "nope"}).status_code == 403
    assert httpx.get(f"{base}/info", headers={**h, "Host": "evil.example"}).status_code == 403
    assert httpx.get(f"{base}/info", headers=h).json()["ready"] is True
    page = httpx.get(f"{base}/?t={app.token}").text
    assert app.token in page and "__TOKEN__" not in page


def test_chat_round_trip_streams_and_finishes(gui):
    app, base, h = gui
    assert httpx.post(f"{base}/send", headers=h, json={"text": "world"}).json()["status"] == "started"
    kinds = [e["kind"] for e in poll(base, h, until="idle")]
    for k in ("ready", "user", "busy", "tool_call", "token", "done", "idle"):
        assert k in kinds
    done = [e for e in poll(base, h, until="idle") if e["kind"] == "done"][0]
    assert done["answer"] == "hello world"


def test_approval_buttons_decide(gui):
    app, base, h = gui
    httpx.post(f"{base}/send", headers=h, json={"text": "ask"})
    evs = poll(base, h, until="approval")
    ap = [e for e in evs if e["kind"] == "approval"][0]
    assert ap["category"] == "write_outside"
    assert isinstance(ap["id"], int) and ap["aid"] != ap["id"]        # the event counter is never overwritten
    pending = list(app._approvals)[0]
    assert httpx.post(f"{base}/approve", headers=h, json={"id": pending, "answer": "maybe"}).json()["ok"] is False
    assert httpx.post(f"{base}/approve", headers=h, json={"id": pending, "answer": "y"}).json()["ok"] is True
    done = [e for e in poll(base, h, until="done") if e["kind"] == "done"][0]
    assert done["answer"] == "approval was y"


def test_stop_ends_a_slow_task_and_denies_pending_approval(gui):
    app, base, h = gui
    httpx.post(f"{base}/send", headers=h, json={"text": "slow"})
    time.sleep(0.2)
    assert httpx.post(f"{base}/send", headers=h, json={"text": "also this"}).json()["status"] == "queued"
    assert app.agent.inbox.get_nowait() == "also this"
    httpx.post(f"{base}/stop", headers=h, json={})
    done = [e for e in poll(base, h, until="done") if e["kind"] == "done"][0]
    assert done["stopped"] is True
    time.sleep(0.2)
    httpx.post(f"{base}/send", headers=h, json={"text": "ask"})
    poll(base, h, until="approval")
    httpx.post(f"{base}/stop", headers=h, json={})
    done = [e for e in poll(base, h, until="idle") if e["kind"] == "approval_done"]
    assert done and done[-1]["answer"] == "n"


def test_pictures_are_served_only_from_workspace_and_not_secret(gui):
    app, base, h = gui
    httpx.post(f"{base}/send", headers=h, json={"text": "pic"})
    evs = poll(base, h, until="idle")
    pics = [e["rel"] for e in evs if e["kind"] == "picture"]
    assert "out.png" in pics
    assert httpx.get(f"{base}/file?p=out.png", headers=h).status_code == 200
    assert httpx.get(f"{base}/file?p=secret.png", headers=h).status_code == 404
    assert httpx.get(f"{base}/file?p=../ws.txt", headers=h).status_code == 403
    assert httpx.get(f"{base}/file?p=out.txt", headers=h).status_code == 403


def test_reset_command_and_busy_guard(gui):
    app, base, h = gui
    assert httpx.post(f"{base}/send", headers=h, json={"text": "/reset"}).json()["status"] == "ok"
    assert app.agent.reset_called
    assert httpx.post(f"{base}/send", headers=h, json={"text": "  "}).json()["status"] == "empty"
