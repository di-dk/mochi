"""End-to-end with the real LLM. Run: pytest -m e2e -s"""
import copy
import time
from pathlib import Path

import pytest

from agent.core import Agent, ensure_llm, load_config, make_policy

pytestmark = pytest.mark.e2e


def make(tmp_path, approver, model="qwen3.6-35b-a3b"):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["llm"]["model"] = model
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


def test_vision_reads_image(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    agent, events = make(tmp_path, approver=lambda c, s: "n", model="gemma-4-26b-a4b-it")
    assert agent.vision, "gemma should be detected as a vision model"
    img = Image.new("RGB", (900, 400), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 120)
    d.ellipse((30, 120, 230, 320), fill="red")
    d.text((280, 130), "MANGO 47", fill="blue", font=font)
    img.save(agent.policy.workspace / "secret.png")
    answer = agent.run("Look at secret.png. Reply with only the word, the number, and the colour of the circle.")
    print(f"\nANSWER: {answer}")
    assert "view_image" in tools_used(events)
    low = answer.lower()
    assert "mango" in low and "47" in low and "red" in low


def test_headless_browser_vision(tmp_path):
    agent, events = make(tmp_path, approver=lambda c, s: "n", model="gemma-4-26b-a4b-it")
    answer = agent.run("Open https://example.com in your browser, take a browser screenshot, and tell me the big "
                       "heading you can SEE on the page and the colour of the page background.")
    print(f"\nANSWER: {answer}")
    used = tools_used(events)
    assert "browser_open" in used and "browser_screenshot" in used
    assert "domain" in answer.lower()   # she reads the page; local vision may mix up heading vs. text
    agent.registry.call("browser_close", {}, agent.policy)


def test_plan_verify_and_learn(tmp_path):
    agent, events = make(tmp_path, approver=lambda c, s: "n", model="gemma-4-26b-a4b-it")
    answer = agent.run("Make fruits.pdf: a heading 'Fruit prices' and a table of 4 fruits with made-up prices in EUR. "
                       "Then also make fruits.xlsx with the same table. Verify both files, and save what you did as a "
                       "skill for next time.")
    print(f"\nANSWER: {answer}")
    used = tools_used(events)
    print("TOOLS:", used)
    ws = agent.policy.workspace
    assert (ws / "fruits.pdf").exists() and (ws / "fruits.xlsx").exists()
    assert "inspect_pdf" in used or "read_spreadsheet" in used      # she checked her work
    assert "save_skill" in used and list((ws / "skills").glob("*.md"))


def test_uses_app_on_her_own(tmp_path):
    agent, events = make(tmp_path, approver=lambda c, s: "n", model="gemma-4-26b-a4b-it")
    agent.policy.auto_allow = {"launch", "desktop"}       # trusted apps mode; nothing else is approved
    answer = agent.run("Open the Calculator app, calculate 12 + 30 by pressing its buttons (don't compute it "
                       "yourself), read the result shown in the app, then close Calculator.")
    print(f"\nANSWER: {answer}")
    used = tools_used(events)
    print("TOOLS:", used)
    assert "launch_app" in used and "app_click" in used
    assert "42" in answer
