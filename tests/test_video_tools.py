"""Offline tests for the video tools (fake studio command) and the repeat-call loop guard."""
import copy
import json
import sys
from types import SimpleNamespace

import pytest

from agent.core import Agent, load_config, make_policy
from agent.tools import build_tools

FAKE_STUDIO = r'''
import json, os, sys
a = sys.argv[1:]
if a[0] == "--list":
    print("1 videos made.\n2026-11-06 10:00  2d    20.0s  Test  ->  X:/v.mp4"); sys.exit(0)
check = a[0] == "--check"
spec = json.load(open(a[-1], encoding="utf-8"))
if not spec["scenes"] and not spec["questions"]:
    print('RESULT {"ok": false, "error": "Fix the script and call again: needs scenes"}'); sys.exit(2)
if check:
    print('RESULT {"ok": true, "checked": true}'); sys.exit(0)
if spec["title"] == "boom":
    print('RESULT {"ok": false, "error": "render failed: kaboom"}'); sys.exit(2)
folder = os.path.join(os.path.dirname(a[-1]), "out")
os.makedirs(folder, exist_ok=True)
print("[ 1.0s] voice done")
print("RESULT " + json.dumps({"ok": True, "video": os.path.join(folder, "t.mp4"), "folder": folder,
                              "seconds": 21.5, "style": spec["style"], "look": "", "note": ""}))
'''


@pytest.fixture
def env(tmp_path):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    studio = tmp_path / "fake_studio.py"
    studio.write_text(FAKE_STUDIO, encoding="utf-8")
    cfg["video"] = {"command": [sys.executable, str(studio)], "timeout_s": 60}
    answers = []
    policy = make_policy(cfg, approver=lambda c, s: answers.pop(0) if answers else "n")
    policy.audit_path = tmp_path / "audit.jsonl"
    policy.auto_allow = set()
    return cfg, policy, build_tools(policy, cfg), answers


def call(reg, policy, tool, **kw):
    return reg.call(tool, kw, policy)


def test_video_tools_hidden_without_command(env):
    cfg, policy, _, _ = env
    cfg = copy.deepcopy(cfg)
    cfg["video"] = {"command": []}
    reg = build_tools(policy, cfg)
    assert "make_video" not in reg.tools and "list_my_videos" not in reg.tools


def test_make_video_done(env):
    cfg, policy, reg, answers = env
    answers.append("y")
    r = call(reg, policy, "make_video", title="Bees", style="2d",
             scenes=[{"say": "Why hexagons?", "text": "Why *hexagons?*", "emoji": "🐝"}, "Wax is costly."])
    assert r.startswith("DONE") and "t.mp4" in r and "21.5 s" in r and "don't render it again" in r
    saved = list((policy.workspace / "video_scripts").glob("*_bees.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text(encoding="utf-8"))["scenes"][1] == "Wax is costly."


def test_make_video_bad_script_fails_fast_without_approval(env):
    cfg, policy, reg, answers = env
    r = call(reg, policy, "make_video", title="Empty", style="2d")
    assert r.startswith("ERROR") and "needs scenes" in r
    log = policy.audit_path.read_text(encoding="utf-8")
    assert '"category": "video"' not in log          # validation failed before any approval / render


def test_make_video_needs_approval_and_reports_render_errors(env):
    cfg, policy, reg, answers = env
    r = call(reg, policy, "make_video", title="Bees", style="2d", scenes=["one"])
    assert r.startswith("DENIED")                     # approver said no
    policy.auto_allow = {"video"}
    r = call(reg, policy, "make_video", title="boom", style="3d", scenes=["one"])
    assert r.startswith("ERROR") and "kaboom" in r


def test_list_my_videos(env):
    cfg, policy, reg, _ = env
    assert "1 videos made" in call(reg, policy, "list_my_videos", count=5)


def test_repeat_guard_blocks_fourth_identical_call(env, tmp_path):
    cfg, policy, reg, _ = env
    runs = []
    reg.add("probe", "test tool", {})(lambda: runs.append(1) or "same listing")
    tc = SimpleNamespace(id="c", type="function", function=SimpleNamespace(name="probe", arguments="{}"))
    replies = [SimpleNamespace(content="", tool_calls=[tc])] * 6 + [SimpleNamespace(content="ok, done", tool_calls=None)]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    return SimpleNamespace(choices=[SimpleNamespace(message=replies.pop(0))])

    agent = Agent.__new__(Agent)
    agent.cfg, agent.policy, agent.registry, agent.vision = cfg, policy, reg, False
    agent.client, agent.on_event = FakeClient, (lambda k, d: None)
    agent.messages = [{"role": "system", "content": "s"}]
    assert agent.run("go") == "ok, done"
    assert len(runs) == 3                             # calls 4-6 were blocked, not executed
    tool_msgs = [m["content"] for m in agent.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 6 and all(m.startswith("BLOCKED") for m in tool_msgs[3:])
