"""Offline tests: the audit log is private (owner-only), rolls over, and can leave out message text."""
import copy
import json
import os
import stat

import pytest

from agent.core import load_config, make_policy


def _policy(tmp_path, **privacy):
    cfg = copy.deepcopy(load_config())
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["privacy"] = privacy
    p = make_policy(cfg)
    p.audit_path = tmp_path / "logs" / "audit.jsonl"
    return p


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX only")
def test_audit_log_is_owner_only(tmp_path):
    p = _policy(tmp_path)
    p.audit("user", text="hello")
    assert stat.S_IMODE(p.audit_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(p.audit_path.parent.stat().st_mode) == 0o700


def test_audit_text_can_be_left_out(tmp_path):
    p = _policy(tmp_path, audit_text=False)
    p.audit("user", text="my secret plan", files=["a.txt"])
    p.audit("assistant", text="the answer")
    p.audit("deny", op="read", path="/x")
    rows = [json.loads(line) for line in p.audit_path.read_text(encoding="utf-8").splitlines()]
    assert "secret" not in p.audit_path.read_text(encoding="utf-8") and "answer" not in p.audit_path.read_text(encoding="utf-8")
    assert rows[0]["text"].startswith("<omitted") and rows[0]["files"] == ["a.txt"]
    assert rows[2]["op"] == "read"                           # actions are still recorded


def test_audit_text_kept_by_default(tmp_path):
    p = _policy(tmp_path)
    p.audit("user", text="hello there")
    assert "hello there" in p.audit_path.read_text(encoding="utf-8")


def test_audit_rolls_over(tmp_path):
    p = _policy(tmp_path, audit_max_mb=0.0005)               # ~500 bytes
    for i in range(40):
        p.audit("user", text=f"message number {i} " + "x" * 40)
    old = p.audit_path.with_name("audit.jsonl.1")
    assert old.exists() and p.audit_path.stat().st_size < 1500
    if os.name == "posix":
        assert stat.S_IMODE(old.stat().st_mode) == 0o600
