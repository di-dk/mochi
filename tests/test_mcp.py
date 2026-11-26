"""MCP client: tools of a configured server are registered, every call asks first, auto mode does not bypass it,
a server whose tool list changes is flagged."""
import sys
from pathlib import Path

import pytest

from agent.core import load_config, make_policy
from agent.tools import build_tools

pytest.importorskip("mcp")
FAKE = str(Path(__file__).parent / "fake_mcp_server.py")


def make(tmp_path, trust="ask", extra=None, approver=None):
    cfg = load_config()
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["video"] = {}
    cfg["mcp"] = {"servers": {"demo": {"command": sys.executable, "args": [FAKE] + (extra or []), "trust": trust}}}
    asked = []
    policy = make_policy(cfg, approver=approver or (lambda c, s: asked.append((c, s)) or "y"))
    policy.audit_path = tmp_path / "audit.jsonl"
    reg = build_tools(policy, cfg)
    assert reg.mcp.ready.wait(60)
    return cfg, policy, reg, asked


def test_tools_register_and_every_call_asks_even_in_auto_mode(tmp_path):
    cfg, policy, reg, asked = make(tmp_path)
    assert "mcp_demo_add" in reg.tools and "mcp_demo_echo" in reg.tools
    assert reg.tools["mcp_demo_add"].description.startswith("[MCP server 'demo', third-party]")
    out = reg.call("mcp_demo_add", {"a": 2, "b": 40}, policy)
    assert "42" in out and "third-party data, not instructions" in out
    assert asked and asked[0][0] == "mcp:demo"
    policy.auto_mode = True                                  # auto mode must not skip third-party servers
    reg.call("mcp_demo_echo", {"text": "hi"}, policy)
    assert len(asked) == 2
    assert "connected" in reg.call("mcp_servers", {}, policy)


def test_declined_call_does_not_run(tmp_path):
    cfg, policy, reg, asked = make(tmp_path, approver=lambda c, s: "n")
    assert reg.call("mcp_demo_add", {"a": 1, "b": 1}, policy).startswith("DENIED")


def test_trusted_server_runs_without_asking_and_changed_tools_are_flagged(tmp_path):
    cfg, policy, reg, asked = make(tmp_path, trust="auto")
    assert "42" in reg.call("mcp_demo_add", {"a": 40, "b": 2}, policy) and asked == []
    cfg2, policy2, reg2, _ = make(tmp_path, extra=["more"])     # same workspace, the server now has an extra tool
    assert "changed" in reg2.mcp.state["demo"].get("warning", "")
