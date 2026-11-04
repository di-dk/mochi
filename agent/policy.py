"""Sandbox, approval gate and audit log.

Every tool goes through Policy:
  * paths are resolved and classified (workspace / read-allowed / outside / denied)
  * risky actions call `require()` which asks the human (interactive) or refuses (unattended)
  * everything is appended to logs/audit.jsonl
"""
from __future__ import annotations

import fnmatch
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


import re as _re

# Windows where keyboard/mouse input could run commands or change system settings -> always ask.
SENSITIVE_WINDOW = _re.compile(
    r"powershell|command prompt|cmd\.exe|\bterminal\b|windows terminal|^run$|registry editor|regedit|task manager|"
    r"task scheduler|user account control|credential|password|bitlocker|services|group policy|"
    r"device manager|disk management|mochi", _re.I)
# Programs that are effectively shells/installers -> launching them always asks.
SENSITIVE_PROGRAMS = {"powershell", "pwsh", "cmd", "wt", "bash", "wsl", "python", "pythonw", "py", "node", "reg",
                      "regedit", "msiexec", "schtasks", "rundll32", "mshta", "wscript", "cscript", "certutil",
                      "bitsadmin", "diskpart", "bcdedit", "netsh", "sc", "taskkill", "format", "msconfig",
                      "gpedit", "secpol", "mmc", "control", "ms-settings"}


def is_sensitive_window(title: str) -> bool:
    return bool(SENSITIVE_WINDOW.search((title or "").strip()))


def is_sensitive_program(program: str) -> bool:
    stem = _re.split(r"[\\/]", program.strip().strip('"'))[-1].lower()
    stem = _re.sub(r"\.(exe|cmd|bat|com|ps1|msc)$", "", stem)
    return stem in SENSITIVE_PROGRAMS or program.lower().startswith(("ms-settings", "shell:"))


PIPE_FILTERS = {"select-object", "where-object", "sort-object", "format-table", "format-list",
                "measure-object", "select-string", "group-object", "out-string"}
SECRET_MARKERS = (".env", "id_rsa", "id_ed25519", ".ssh", ".pem", ".pfx", ".git-credentials",
                  "credentials", ".aws")


class Denied(Exception):
    """Raised when an action is refused by policy or by the user."""


# approver(category, summary) -> "y" | "n" | "a"   (a = allow this category for the session)
Approver = Callable[[str, str], str]


@dataclass
class Policy:
    workspace: Path
    read_allow: list[Path]
    deny_globs: list[str]
    shell_auto_allow: list[str]
    shell_hard_deny: list[str]
    audit_path: Path
    approver: Approver | None = None          # None => unattended: approvals are refused
    session_allowed: set[str] = field(default_factory=set)
    # Categories the user trusts Mochi to do on her own (config approvals.auto_allow), e.g. {"launch", "desktop"}.
    # Sensitive targets (terminals, Run box, registry, installers...) still ask.
    auto_allow: set[str] = field(default_factory=set)

    # ---------- audit ----------
    def audit(self, event: str, **data) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **data}
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    # ---------- approvals ----------
    def require(self, category: str, summary: str, sensitive: bool = False) -> None:
        """Block until the human approves, or raise Denied.
        sensitive=True means the target could be used to get around other rules (e.g. typing into a terminal),
        so trusted auto-approval doesn't apply."""
        if category in self.auto_allow and not sensitive:
            self.audit("approval", category=category, summary=summary, result="trusted-auto")
            return
        if sensitive:
            summary = "⚠ sensitive target — " + summary
        if category in self.session_allowed and not sensitive:
            self.audit("approval", category=category, summary=summary, result="session-allowed")
            return
        if self.approver is None:
            self.audit("approval", category=category, summary=summary, result="refused-unattended")
            raise Denied(f"'{category}' needs human approval, but the agent is running unattended. "
                         "Do this inside the workspace instead, or report that it needs a human.")
        answer = (self.approver(category, summary) or "n").strip().lower()
        self.audit("approval", category=category, summary=summary, result=answer)
        if answer.startswith("a"):
            self.session_allowed.add(category)
            return
        if not answer.startswith("y"):
            raise Denied(f"User declined: {summary}")

    # ---------- paths ----------
    def resolve(self, p: str | Path) -> Path:
        path = Path(p).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        return path.resolve()

    def is_denied(self, path: Path) -> bool:
        """Globs are '**/<name-pattern>' (matches the file name) or '**/<dir>/**' (any folder on the path)."""
        parts = [p.lower() for p in path.parts]
        for g in self.deny_globs:
            g = g.lower().removeprefix("**/")
            if g.endswith("/**"):
                if any(fnmatch.fnmatch(p, g[:-3]) for p in parts[:-1]):
                    return True
            elif fnmatch.fnmatch(parts[-1], g):
                return True
        return False

    def in_workspace(self, path: Path) -> bool:
        return path == self.workspace or path.is_relative_to(self.workspace)

    def check_read(self, p: str | Path) -> Path:
        path = self.resolve(p)
        if self.is_denied(path):
            self.audit("deny", op="read", path=str(path))
            raise Denied(f"Reading {path} is blocked (credential/secret file).")
        if self.in_workspace(path) or any(path.is_relative_to(r) for r in self.read_allow):
            return path
        self.require("read_outside", f"Read outside workspace: {path}")
        return path

    def check_write(self, p: str | Path, *, delete: bool = False) -> Path:
        path = self.resolve(p)
        if self.is_denied(path):
            self.audit("deny", op="write", path=str(path))
            raise Denied(f"Writing {path} is blocked (credential/secret file).")
        if delete:
            self.require("delete", f"Delete: {path}")
        elif not self.in_workspace(path):
            self.require("write_outside", f"Write outside workspace: {path}")
        return path

    # ---------- shell ----------
    def check_shell(self, command: str) -> None:
        low = command.lower()
        for bad in self.shell_hard_deny:
            if bad.lower() in low:
                self.audit("deny", op="shell", command=command, rule=bad)
                raise Denied(f"Command refused by hard-deny rule: {bad!r}")
        # Auto-allow only plain read-only pipelines: every segment starts with an allowed
        # command and there is no chaining, redirection or sub-expression.
        for secret in SECRET_MARKERS:
            if secret in low:
                self.audit("deny", op="shell", command=command, rule=secret)
                raise Denied("Command touches a credential/secret file and is refused.")
        if command.strip() and not any(t in command for t in (";", "&", ">", "<", "`", "$(", "{", "\n")):
            allowed = {a.lower() for a in self.shell_auto_allow} | PIPE_FILTERS
            segs = [s.strip() for s in command.split("|")]
            if all(s and s.split()[0].lower() in allowed for s in segs):
                return
        self.require("shell", f"Run PowerShell: {command}")
