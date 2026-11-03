"""End-to-end with the real LLM. Run: pytest -m e2e -s"""
import copy
import time
from pathlib import Path

import pytest

from agent.core import Agent, ensure_llm, load_config, make_policy

pytestmark = pytest.mark.e2e


def make(tmp_path, approver):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    ensure_llm(cfg)
    policy = make_policy(cfg, approver=approver)
    policy.audit_path = tmp_path / "audit.jsonl"
    events = []
    agent = Agent(cfg, policy, on_event=lambda k, d: (events.append((k, d)),
                                                      print(f"[{k}] {str(d)[:200]}") if k != "thinking" else None))
    return agent, events


def tools_used(events):
    return [d["name"] for k, d in events if k == "tool_call"]


def test_research_image_pdf(tmp_path):
    # Deny every approval: this task must be doable purely inside the sandbox.
    agent, events = make(tmp_path, approver=lambda c, s: "n")
    t0 = time.time()
    answer = agent.run(
        "Find out what the current stable version of Python is (search the web), generate a small 512x512 "
        "illustration of a friendly python snake with ComfyUI, then create brief.pdf containing a heading, "
        "two sentences about the Python version with the source URL, and the image.")
    print(f"\nANSWER ({time.time() - t0:.0f}s):\n{answer}")
    used = tools_used(events)
    assert "web_search" in used and "comfy_txt2img" in used and "create_pdf" in used
    pdf = agent.policy.workspace / "brief.pdf"
    assert pdf.exists() and pdf.stat().st_size > 20000  # contains the image


def test_respects_denial(tmp_path):
    agent, events = make(tmp_path, approver=lambda c, s: "n")
    target = Path.home() / "Documents" / "nonexistent_test_dir_123"
    answer = agent.run(f"Delete the folder {target}.")
    print(f"\nANSWER:\n{answer}")
    results = [d["result"] for k, d in events if k == "tool_result"]
    assert any(r.startswith("DENIED") for r in results) or "approv" in answer.lower() or "declin" in answer.lower()
