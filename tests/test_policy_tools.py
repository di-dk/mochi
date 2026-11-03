"""Offline tests: sandbox, approvals, shell policy, file tools, PDF, memory, registry errors."""
import copy
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


def test_session_always_allow(env):
    cfg, policy, reg, answers, tmp = env
    answers.append("a")
    assert "exit=0" in call(reg, policy, "run_powershell", command="Write-Output hi")
    assert "exit=0" in call(reg, policy, "run_powershell", command="Write-Output again")  # no prompt needed


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
