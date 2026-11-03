"""Live integration tests (need network, desktop, ComfyUI, Task Scheduler). Run: pytest -m live"""
import copy

import pytest

from agent.core import load_config, make_policy
from agent.tools import build_tools

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path_factory.mktemp("livews"))
    policy = make_policy(cfg, approver=lambda c, s: "y")  # auto-approve inside tests
    policy.audit_path = tmp_path_factory.mktemp("logs") / "audit.jsonl"
    return policy, build_tools(policy, cfg)


def call(env, _tool, **kw):
    policy, reg = env
    r = reg.call(_tool, kw, policy)
    print(f"\n{_tool}: {r[:300]}")
    return r


def test_web(env):
    r = call(env, "web_search", query="LM Studio OpenAI compatible API", max_results=3)
    assert "http" in r
    assert len(call(env, "fetch_url", url="https://example.com")) > 50


def test_browser(env):
    assert "Example Domain" in call(env, "browser_open", url="https://example.com")
    assert "INTERACTIVE ELEMENTS" in call(env, "browser_read")
    assert "Saved" in call(env, "browser_screenshot")
    call(env, "browser_close")


def test_desktop_readonly(env):
    assert call(env, "list_windows").strip()
    assert "Saved screenshot" in call(env, "screenshot")


def test_comfyui(env):
    st = call(env, "comfy_status")
    if "not reachable" in st:
        pytest.skip("ComfyUI not running")
    assert "safetensors" in call(env, "comfy_list_models")
    r = call(env, "comfy_txt2img", prompt="a red apple on a wooden table, studio photo", width=512, height=512, steps=12)
    assert ".png" in r


def test_scheduler_roundtrip(env):
    r = call(env, "schedule_task", name="pytest_probe", prompt="write hello.txt", frequency="ONCE",
             time="23:59", date="2099-12-31")
    assert "SUCCESS" in r.upper()
    assert "pytest_probe" in call(env, "list_scheduled_tasks")
    assert "SUCCESS" in call(env, "delete_scheduled_task", name="pytest_probe").upper()
