"""Offline tests: sandbox, approvals, shell policy, file tools, PDF, memory, registry errors."""
import copy
import sys
from pathlib import Path

import pytest

from agent.core import load_config, make_policy
from agent.policy import Denied
from agent.tools import build_tools


@pytest.fixture
def env(tmp_path):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["sandbox"]["read_allow"] = [str(tmp_path / "shared")]
    (tmp_path / "shared").mkdir()
    (tmp_path / "outside").mkdir()
    answers = []
    policy = make_policy(cfg, approver=lambda c, s: answers.pop(0) if answers else "n")
    policy.audit_path = tmp_path / "audit.jsonl"
    return cfg, policy, build_tools(policy, cfg), answers, tmp_path


def call(reg, policy, name, **kw):
    return reg.call(name, kw, policy)


def test_workspace_write_read_no_approval(env):
    cfg, policy, reg, answers, tmp = env
    assert "Wrote" in call(reg, policy, "write_file", path="notes/a.txt", content="hello\nworld")
    assert "2: world" in call(reg, policy, "read_file", path="notes/a.txt")
    assert "Edited" in call(reg, policy, "edit_file", path="notes/a.txt", old="world", new="there")


def test_path_traversal_needs_approval(env):
    cfg, policy, reg, answers, tmp = env
    r = call(reg, policy, "write_file", path="../outside/x.txt", content="x")
    assert r.startswith("DENIED") and not (tmp / "outside" / "x.txt").exists()
    answers.append("y")
    assert "Wrote" in call(reg, policy, "write_file", path="../outside/x.txt", content="x")


def test_read_allow_list(env):
    cfg, policy, reg, answers, tmp = env
    (tmp / "shared" / "img.txt").write_text("ok")
    (tmp / "outside" / "s.txt").write_text("secret-ish")
    assert "ok" in call(reg, policy, "read_file", path=str(tmp / "shared" / "img.txt"))
    assert call(reg, policy, "read_file", path=str(tmp / "outside" / "s.txt")).startswith("DENIED")


def test_credentials_always_blocked_even_if_approved(env):
    cfg, policy, reg, answers, tmp = env
    (policy.workspace / ".env").write_text("TOKEN=<REDACTED>")
    answers.extend(["y"] * 5)
    assert call(reg, policy, "read_file", path=".env").startswith("DENIED")
    assert call(reg, policy, "read_file", path=str(Path.home() / ".ssh" / "id_rsa")).startswith("DENIED")
    assert ".env" not in call(reg, policy, "list_dir")


def test_delete_requires_approval_and_protects_root(env):
    cfg, policy, reg, answers, tmp = env
    call(reg, policy, "write_file", path="d.txt", content="x")
    assert call(reg, policy, "delete_path", path="d.txt").startswith("DENIED")
    answers.append("y")
    assert "Deleted" in call(reg, policy, "delete_path", path="d.txt")
    answers.append("y")
    assert call(reg, policy, "delete_path", path=".").startswith("DENIED")


WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell policy test")
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="bash policy test")


@POSIX_ONLY
def test_shell_policy_posix(env):
    cfg, policy, reg, answers, tmp = env
    assert "exit=0" in call(reg, policy, "run_shell", command="uname | head -n 1")     # read-only pipeline runs
    assert call(reg, policy, "run_shell", command="touch x.txt").startswith("DENIED")     # mutation needs approval
    assert call(reg, policy, "run_shell", command="ls | head /etc/passwd").startswith("DENIED")  # filter + path
    assert call(reg, policy, "run_shell", command="ls; touch y").startswith("DENIED")      # chaining needs approval
    answers.append("y")
    assert "hard-deny" in call(reg, policy, "run_shell", command="rm -rf /*")
    answers.append("y")
    assert "secret" in call(reg, policy, "run_shell", command="cat ~/.ssh/id_rsa")


@POSIX_ONLY
def test_session_always_allow_posix(env):
    cfg, policy, reg, answers, tmp = env
    answers.append("a")
    assert "exit=0" in call(reg, policy, "run_shell", command="echo hi > out.txt")
    assert "exit=0" in call(reg, policy, "run_shell", command="echo again > out.txt")   # no prompt needed


@POSIX_ONLY
def test_unattended_refuses_approvals_posix(env):
    cfg, policy, reg, answers, tmp = env
    policy.approver = None
    assert "unattended" in call(reg, policy, "run_shell", command="touch x.txt")


@POSIX_ONLY
def test_windows_only_tools_are_not_offered(env):
    cfg, policy, reg, answers, tmp = env
    # the Windows implementations are gone; Linux ones are only registered when their backend exists
    assert "run_shell" in reg.tools and "run_powershell" not in reg.tools
    assert {"list_apps", "launch_app", "screenshot"} <= set(reg.tools)
    import shutil
    assert ("schedule_task" in reg.tools) == bool(shutil.which("systemctl"))
    assert "win32" not in repr(reg.tools["launch_app"].fn.__code__.co_names)


@WIN_ONLY
def test_shell_policy(env):
    cfg, policy, reg, answers, tmp = env
    assert "exit=0" in call(reg, policy, "run_powershell", command="Get-Date | Select-Object Year")
    # mutation without approval -> denied
    assert call(reg, policy, "run_powershell", command="New-Item x.txt").startswith("DENIED")
    # script block in an allowed pipeline -> needs approval
    assert call(reg, policy, "run_powershell", command="Get-Process | Where-Object { $_ }").startswith("DENIED")
    # hard-deny even with approval
    answers.append("y")
    assert "hard-deny" in call(reg, policy, "run_powershell", command="diskpart /s x")
    answers.append("y")
    assert "secret" in call(reg, policy, "run_powershell", command="Get-Content C:/Users/x/.env")


@WIN_ONLY
def test_session_always_allow(env):
    cfg, policy, reg, answers, tmp = env
    answers.append("a")
    assert "exit=0" in call(reg, policy, "run_powershell", command="Write-Output hi")
    assert "exit=0" in call(reg, policy, "run_powershell", command="Write-Output again")  # no prompt needed


@WIN_ONLY
def test_unattended_refuses_approvals(env):
    cfg, policy, reg, answers, tmp = env
    policy.approver = None
    r = call(reg, policy, "run_powershell", command="New-Item x.txt")
    assert "unattended" in r
    assert "Wrote" in call(reg, policy, "write_file", path="ok.txt", content="fine")


def test_pdf_and_memory(env):
    cfg, policy, reg, answers, tmp = env
    md = "# Title\n\nSome **bold** text.\n\n- a\n- b\n\n1. one\n2. two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```\ncode\n```"
    r = call(reg, policy, "create_pdf", path="out/report", markdown=md, title="Test")
    assert "Created" in r
    pdf = policy.workspace / "out" / "report.pdf"
    assert pdf.read_bytes()[:4] == b"%PDF"
    call(reg, policy, "remember", note="User prefers A4 PDFs")
    assert "A4" in call(reg, policy, "recall", query="pdf")


def test_registry_bad_input(env):
    cfg, policy, reg, answers, tmp = env
    assert "unknown tool" in reg.call("nope", "{}", policy)
    assert "not valid JSON" in reg.call("read_file", "{bad", policy)
    assert "bad arguments" in reg.call("read_file", {"wrong": 1}, policy)
    assert policy.audit_path.exists()


def test_save_local_setting_keeps_other_keys(tmp_path, monkeypatch):
    import yaml
    from agent import core
    monkeypatch.setattr(core, "ROOT", tmp_path)
    (tmp_path / "config.local.yaml").write_text("comfyui:\n  default_checkpoint: x.safetensors\n", encoding="utf-8")
    core.save_local_setting("llm", "model", "some-model")
    core.save_local_setting("llm", "model", "other-model")
    data = yaml.safe_load((tmp_path / "config.local.yaml").read_text(encoding="utf-8"))
    assert data == {"comfyui": {"default_checkpoint": "x.safetensors"}, "llm": {"model": "other-model"}}


def test_auto_mode_skips_asking_but_keeps_hard_stops(env):
    pol = env[1]
    asked = []
    pol.approver = lambda c, s: asked.append(c) or "n"
    pol.auto_mode = True
    pol.require("write_outside", "x")                       # auto-approved: nobody asked
    assert asked == []
    for cat, sens in (("delete", False), ("skill_import", False), ("desktop", True)):
        try:
            pol.require(cat, "x", sensitive=sens)
            raise AssertionError(cat)
        except Exception as e:                              # the (declining) human was asked
            assert "declined" in str(e)
    assert asked == ["delete", "skill_import", "desktop"]
    pol.auto_mode, pol.approver = True, None                 # unattended runs never get auto mode
    try:
        pol.require("write_outside", "x"); raise AssertionError("unattended")
    except Exception as e:
        assert "unattended" in str(e)


def test_voice_text_cleaning_and_blend_settings():
    from agent import voice
    t = voice.speakable("**Done!** See [the doc](https://x.io/a) and `rm -rf`\n```py\nprint(1)\n```\n- one 😀 two")
    assert "http" not in t and "`" not in t and "print" not in t and "*" not in t and "😀" not in t
    assert t.startswith("Done!") and "the doc" in t and "one" in t
    assert voice.settings({"voice": {"speed": 1.2}})["speed"] == 1.2 and voice.settings({})["enabled"] is True


def test_her_name_is_said_moh_chee():
    from agent import voice
    assert voice.speakable("Hi, I'm Mochi! Mochi's here, and MOCHI too.") == "Hi, I'm Mohchee! Mohchee's here, and Mohchee too."
