"""Offline tests for vision plumbing, self-check, search, planning, skills/lessons and automation tools."""
import copy
import zipfile

import pytest

from agent.core import Agent, load_config, make_policy
from agent.tools import build_tools


@pytest.fixture
def env(tmp_path):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    answers = []
    policy = make_policy(cfg, approver=lambda c, s: answers.pop(0) if answers else "n")
    policy.audit_path = tmp_path / "audit.jsonl"
    reg = build_tools(policy, cfg)
    return cfg, policy, reg, answers


def call(reg, policy, tool, **kw):
    return reg.call(tool, kw, policy)


def test_pdf_inspect_and_render_attaches_image(env):
    cfg, policy, reg, _ = env
    call(reg, policy, "create_pdf", path="r.pdf", markdown="# Hello\n\nWorld text here.")
    reg.vision = False
    r = call(reg, policy, "inspect_pdf", path="r.pdf", render_page=1)
    assert "1 page(s)" in r and "World text" in r and "cannot view images" in r
    assert reg.drain_images() == []
    reg.vision = True
    r = call(reg, policy, "inspect_pdf", path="r.pdf", render_page=1)
    imgs = reg.drain_images()
    assert "attached" in r and len(imgs) == 1 and imgs[0][0].endswith(".png")


def test_agent_image_message_and_trim(env):
    cfg, policy, reg, _ = env
    from PIL import Image
    p = policy.workspace / "a.png"
    Image.new("RGB", (3000, 1500), "red").save(p)
    agent = Agent.__new__(Agent)          # no LLM needed
    agent.cfg, agent.policy, agent.registry, agent.vision = cfg, policy, reg, True
    agent.messages = [{"role": "system", "content": "x"}]
    for _ in range(4):
        agent.messages.append(agent._image_message([(str(p), "test")]))
    url = agent.messages[-1]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    agent._trim()
    with_images = [m for m in agent.messages[1:] if any(pp.get("type") == "image_url" for pp in m["content"])]
    assert len(with_images) == 2                     # only the newest images are kept
    assert not Agent._is_turn_start(agent.messages[1])


def test_search_and_find(env):
    cfg, policy, reg, _ = env
    call(reg, policy, "write_file", path="src/a.py", content="def hello():\n    return 42\n")
    call(reg, policy, "write_file", path="notes.md", content="nothing here")
    assert "src" in call(reg, policy, "find_files", pattern="**/*.py")
    r = call(reg, policy, "search_files", regex=r"return \d+")
    assert "a.py:2:" in r


def test_plan(env):
    cfg, policy, reg, _ = env
    assert "1. [ ] research" in call(reg, policy, "set_plan", steps=["research", "write"])
    assert "1. [x] research" in call(reg, policy, "update_plan", step=1, status="done")
    assert "ERROR" in call(reg, policy, "update_plan", step=9, status="done")


def test_skills_and_lessons(env):
    cfg, policy, reg, _ = env
    assert "pdf-report" in call(reg, policy, "find_skills", query="pdf report")          # built-in
    call(reg, policy, "save_skill", name="Weekly news digest", description="Collect AI news into a PDF",
         steps="1. search\n2. pdf")
    assert "Weekly news digest" in call(reg, policy, "find_skills", query="news")
    assert "1. search" in call(reg, policy, "read_skill", name="Weekly news digest")
    assert "saved" in call(reg, policy, "save_lesson", lesson="Anima checkpoints fail; use nova").lower()
    assert "Already" in call(reg, policy, "save_lesson", lesson="anima checkpoints fail; use nova")
    from agent.tools_extra import recent_lessons, skills_index
    assert "Weekly news digest" in skills_index(policy.workspace)
    assert "Anima" in recent_lessons(policy.workspace)


def test_docx_xlsx_csv(env):
    cfg, policy, reg, _ = env
    assert "Created" in call(reg, policy, "create_docx", path="d", markdown="# T\n\n- a\n- **b**\n\n| x | y |\n|---|---|\n| 1 | 2 |")
    assert "| x | y |" not in call(reg, policy, "read_document", path="d.docx")  # table is read as cells
    assert "1 | 2" in call(reg, policy, "read_document", path="d.docx")
    assert "Created" in call(reg, policy, "create_spreadsheet", path="s.xlsx", rows=[["n", "v"], ["a", 1], ["b", 2], ["sum", "=SUM(B2:B3)"]])
    assert "a | 1" in call(reg, policy, "read_spreadsheet", path="s.xlsx")
    call(reg, policy, "create_spreadsheet", path="s.csv", rows=[["n", "v"], ["a", 1]])
    assert "a | 1" in call(reg, policy, "read_spreadsheet", path="s.csv")


def test_image_edit(env):
    cfg, policy, reg, _ = env
    from PIL import Image
    Image.new("RGBA", (400, 200), (255, 0, 0, 128)).save(policy.workspace / "i.png")
    r = call(reg, policy, "image_edit", path="i.png", output="o.jpg", width=100, grayscale=True)
    assert "(100x50)" in r


def test_zip_roundtrip_and_zipslip(env):
    cfg, policy, reg, _ = env
    call(reg, policy, "write_file", path="pack/a.txt", content="A")
    assert "1 file" in call(reg, policy, "zip_files", paths=["pack"], output="p.zip")
    assert "Extracted" in call(reg, policy, "unzip", path="p.zip", output_dir="out")
    assert (policy.workspace / "out" / "pack" / "a.txt").read_text() == "A"
    with zipfile.ZipFile(policy.workspace / "evil.zip", "w") as z:
        z.writestr("../../escaped.txt", "x")
    assert call(reg, policy, "unzip", path="evil.zip", output_dir="out2").startswith("DENIED")


def test_approval_gates_on_new_tools(env):
    cfg, policy, reg, _ = env
    assert call(reg, policy, "clipboard_get").startswith("DENIED")
    assert call(reg, policy, "http_request", url="https://example.com", method="POST", body="x").startswith("DENIED")
    assert call(reg, policy, "kill_process", pid=4).startswith(("DENIED", "ERROR"))
    assert "CPU" in call(reg, policy, "system_info")


def test_trusted_mode_guards(tmp_path):
    from agent.core import NEVER_AUTO
    from agent.policy import Denied, is_sensitive_program, is_sensitive_window
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["approvals"] = {"auto_allow": ["launch", "desktop", "shell", "delete"]}
    policy = make_policy(cfg, approver=None)          # nobody to ask: anything that needs approval is refused
    policy.audit_path = tmp_path / "audit.jsonl"
    assert policy.auto_allow == {"launch", "desktop"}  # shell/delete can never be trusted
    assert NEVER_AUTO >= {"shell", "delete", "python"}
    policy.require("launch", "Launch Calculator")                       # trusted -> no prompt
    policy.require("desktop", "Click 'One' in 'Calculator'")
    with pytest.raises(Denied):
        policy.require("launch", "Launch powershell", sensitive=True)    # sensitive still asks
    with pytest.raises(Denied):
        policy.require("shell", "Run PowerShell: New-Item x")
    for title in ("Windows PowerShell", "Command Prompt", "Run", "Registry Editor", "Task Manager",
                  "User Account Control", "Mochi"):
        assert is_sensitive_window(title), title
    for title in ("Calculator", "Untitled - Notepad", "ComfyUI", "Spotify Premium"):
        assert not is_sensitive_window(title), title
    for prog in ("powershell", "C:\Windows\System32\cmd.exe", "regedit.exe", "msiexec", "ms-settings:"):
        assert is_sensitive_program(prog), prog
    assert not is_sensitive_program("notepad") and not is_sensitive_program("calc.exe")


def test_trusted_hotkey_guard(env):
    cfg, policy, reg, _ = env
    policy.auto_allow = {"desktop"}
    r = call(reg, policy, "hotkey", keys=["win", "r"])                   # Run box -> still needs approval
    assert r.startswith("DENIED")


def test_disk_usage_and_duplicates(env):
    cfg, policy, reg, _ = env
    ws = policy.workspace
    (ws / "a").mkdir(parents=True, exist_ok=True)
    (ws / "b").mkdir(exist_ok=True)
    (ws / "a" / "x.bin").write_bytes(b"1" * 300_000)
    (ws / "b" / "copy.bin").write_bytes(b"1" * 300_000)
    (ws / "b" / "other.bin").write_bytes(b"2" * 300_000)
    r = call(reg, policy, "disk_usage", path=".")
    assert "Biggest folders" in r and "x.bin" in r
    d = call(reg, policy, "find_duplicates", path=".", min_kb=100)
    assert "1 duplicate set" in d and "copy.bin" in d and "other.bin" not in d and "Nothing was deleted" in d
    assert (ws / "b" / "copy.bin").exists()


def test_weather_parses_open_meteo(env, monkeypatch):
    cfg, policy, reg, _ = env
    import httpx

    class R:
        def __init__(self, data): self.data = data
        def json(self): return self.data

    def fake_get(url, **kw):
        if "geocoding" in url:
            return R({"results": [{"name": "Kathmandu", "country": "Nepal", "latitude": 27.7, "longitude": 85.3}]})
        return R({"current": {"temperature_2m": 21, "apparent_temperature": 20, "weather_code": 2,
                              "wind_speed_10m": 5, "relative_humidity_2m": 60},
                  "daily": {"time": ["d1", "d2", "d3"], "weather_code": [0, 61, 3], "temperature_2m_max": [24, 22, 20],
                            "temperature_2m_min": [14, 13, 12], "precipitation_sum": [0, 4, 1]}})
    monkeypatch.setattr(httpx, "get", fake_get)
    r = call(reg, policy, "weather", city="Kathmandu")
    assert "Kathmandu, Nepal" in r and "partly cloudy" in r and "light rain" in r
