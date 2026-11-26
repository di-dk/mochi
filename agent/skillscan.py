"""Safety scan for skills, using NVIDIA SkillSpector (https://github.com/NVIDIA/SkillSpector, Apache-2.0).

Every skill that comes from outside (imported from git, or written from web research) is scanned BEFORE it is installed,
and an imported skill is fingerprinted so that it cannot be changed after it was scanned. The scanner runs from its own
virtual environment (`.skillspector/`, made by setup) because it brings many dependencies; Mochi only runs its CLI and reads
the JSON report.

Verdicts (SkillSpector's own bands): score 0-20 SAFE, 21-50 CAUTION, 51+ DO_NOT_INSTALL.
  block  -> never installed (DO_NOT_INSTALL, or the scan could not be completed while `require` is on)
  ask    -> installed only if the user approves, with the findings shown (CAUTION, SAFE, or not scanned with require off)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = os.name == "nt"
EXE = "skillspector.exe" if WIN else "skillspector"
BLOCKING = {"DO_NOT_INSTALL"}
CODE_EXT = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts", ".ps1", ".bat", ".cmd", ".rb", ".pl", ".php", ".go", ".rs"}
MIN_COVERAGE = 80.0            # percent of the skill's files that must have been inspected


def settings(cfg: dict) -> dict:
    s = dict(cfg.get("skillspector") or {})
    s.setdefault("enabled", True)
    s.setdefault("require", True)
    s.setdefault("llm", False)
    s.setdefault("timeout_s", 300)
    s.setdefault("on_danger", "block")           # block | ask: what to do with a DO_NOT_INSTALL verdict
    return s


def scanner_path(cfg: dict) -> str | None:
    """The skillspector executable: configured path, the private venv made by setup, or PATH."""
    s = settings(cfg)
    for cand in (s.get("path") or "", str(ROOT / ".skillspector" / ("Scripts" if WIN else "bin") / EXE)):
        if cand and Path(cand).is_file():
            return cand
    return shutil.which("skillspector")


_VERSIONS: dict[str, str] = {}


def version(exe: str) -> str:
    """The scanner's version, asked once (e.g. '2.13.7')."""
    if exe not in _VERSIONS:
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
            m = re.search(r"(\d+\.\d+\.\d+\S*)", r.stdout + r.stderr)
            _VERSIONS[exe] = m.group(1) if m else ""
        except (OSError, subprocess.SubprocessError):
            _VERSIONS[exe] = ""
    return _VERSIONS[exe]


def scan_dir(cfg: dict, folder: Path, deep: bool | None = None) -> dict:
    """Scan one skill folder. Always returns a dict: ok, score, severity, recommendation, issues, complete, version,
    error. ok=False means the scan could not be trusted (missing scanner, crash, timeout, incomplete coverage).
    The verdict always comes from the fast static scan. With deep=True (or skillspector.llm) SkillSpector's LLM stage
    also runs on the local Ollama model and its result is attached as res['deep'] for the user to read: a small local
    model raises false alarms, so it is advisory and can never block or approve anything by itself."""
    use_llm = settings(cfg)["llm"] if deep is None else deep
    res = _run(cfg, folder, False)
    if use_llm and res.get("ok"):
        d = _run(cfg, folder, True)
        res["deep"] = {k: d.get(k) for k in ("ok", "score", "severity", "recommendation", "issues", "error", "complete")}
    return res


def _run(cfg: dict, folder: Path, use_llm: bool) -> dict:
    s = settings(cfg)
    exe = scanner_path(cfg)
    if not exe:
        return {"ok": False, "error": "SkillSpector is not installed (run ./setup.sh, or setup.ps1 on Windows)."}
    out = Path(tempfile.mkdtemp(prefix="skillscan_")) / "report.json"
    cmd = [exe, "scan", str(folder), "--format", "json", "--output", str(out)] + ([] if use_llm else ["--no-llm"])
    env = {k: os.environ[k] for k in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG") if k in os.environ}
    env["PYTHONUTF8"] = "1"
    if use_llm:                                   # the deeper stage runs on the local Ollama: nothing leaves the PC
        llm = cfg.get("llm") or {}
        env.update(SKILLSPECTOR_PROVIDER="ollama", OLLAMA_BASE_URL=llm.get("base_url", "http://localhost:11434/v1"),
                   SKILLSPECTOR_MODEL=s.get("model") or llm.get("model", ""))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=int(s["timeout_s"]), env=env,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"the scan took longer than {s['timeout_s']} seconds"}
    except OSError as e:
        return {"ok": False, "error": f"could not run SkillSpector: {e}"}
    try:
        rep = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": f"SkillSpector gave no report (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}"}
    finally:
        shutil.rmtree(out.parent, ignore_errors=True)
    risk, comp = rep.get("risk_assessment") or {}, rep.get("analysis_completeness") or {}
    complete, caveats = coverage(rep.get("execution_successful", True), comp)
    issues = [{"id": i.get("id"), "category": i.get("category"), "severity": i.get("severity"),
               "finding": str(i.get("finding") or "")[:240], "fix": str(i.get("remediation") or "")[:200],
               "where": str(i.get("location") or "")[:80]} for i in rep.get("issues") or []]
    return {"ok": r.returncode in (0, 1) and "score" in risk, "score": int(risk.get("score", 0)),
            "severity": risk.get("severity", "?"), "recommendation": risk.get("recommendation", "?"),
            "issues": issues, "complete": complete, "caveats": caveats, "llm": use_llm,
            "version": (rep.get("metadata") or {}).get("version") or version(exe), "report": rep,
            "error": "" if r.returncode in (0, 1) else f"exit {r.returncode}"}


def coverage(execution_ok: bool, comp: dict) -> tuple[bool, list[str]]:
    """Was the skill inspected well enough to trust the verdict? Returns (ok, notes).
    Not ok: the scan failed, a file was not inspected at all, a CODE file was only partly inspected, or coverage is
    low. Partly inspected documentation (e.g. a long expression the parser could not resolve) and mentions of files
    that are not bundled ("reference missing") are only noted."""
    notes: list[str] = []
    ok = bool(execution_ok)
    if not execution_ok:
        notes.append("the scan did not finish")
    if comp.get("entirely_uninspected_files", 0) > 0:
        ok = False
        notes.append(f"{comp['entirely_uninspected_files']} file(s) were not inspected at all")
    if float(comp.get("coverage_percent", 100.0)) < MIN_COVERAGE:
        ok = False
        notes.append(f"only {comp.get('coverage_percent')}% of the files were inspected")
    for e in comp.get("ledger_exceptions") or []:
        if e.get("reason_code") == "reference_missing" or e.get("outcome") not in ("partial", "uninspected", "failed"):
            continue
        path = str(e.get("path") or "")
        if Path(path).suffix.lower() in CODE_EXT:
            ok = False
            notes.append(f"code file {path} was only partly inspected")
        elif path and f"{path} (partly inspected)" not in notes:
            notes.append(f"{path} (partly inspected)")
    return ok, notes


def verdict(cfg: dict, res: dict) -> tuple[str, str]:
    """('block'|'ask', reason). A scan that cannot be trusted blocks while `require` is on."""
    s = settings(cfg)
    if not s["enabled"]:
        return "ask", "scanning is switched off (skillspector.enabled: false)"
    if not res.get("ok") or not res.get("complete", True):
        why = res.get("error") or "the scan was incomplete"
        if s["require"]:
            return "block", f"it could not be safety-checked: {why}"
        return "ask", f"NOT SCANNED: {why}"
    if res["recommendation"] in BLOCKING:
        msg = f"SkillSpector says {res['recommendation'].replace('_', ' ')} (score {res['score']}/100, {res['severity']})"
        if s.get("on_danger") == "ask":                       # the user decided to review dangerous verdicts themselves
            return "ask", f"DANGEROUS: {msg}. Only approve if you understand every finding"
        return "block", msg
    d = res.get("deep") or {}
    if d.get("ok") and d.get("recommendation") in BLOCKING:
        return "ask", (f"the deeper review on the local model disagreed and says {d['recommendation'].replace('_', ' ')} "
                       f"(score {d['score']}/100). It is advisory and small models raise false alarms, but read its findings")
    return "ask", ""


def summary(res: dict, limit: int = 6) -> str:
    """Short, human-readable result for approvals and tool output."""
    if not res.get("ok"):
        return f"Scan: not completed ({res.get('error') or 'unknown error'})"
    head = (f"SkillSpector {res.get('version', '')}: {res['recommendation'].replace('_', ' ')} "
            f"(score {res['score']}/100, {res['severity']}"
            f"{', deep scan with the local model' if res.get('llm') else ', static scan'})")
    rows = []
    for i in res["issues"][:limit]:
        rows.append(f"  - [{i['severity']}] {i['category']} ({i['id']}): {i['finding'][:150]}"
                    + (f"  Fix: {i['fix'][:100]}" if i["fix"] else ""))
    more = len(res["issues"]) - limit
    if res.get("deep"):
        d = res["deep"]
        if d.get("ok"):
            rows.append(f"  Deeper review on the local model (advisory only): {d['recommendation'].replace('_', ' ')}, "
                        f"score {d['score']}/100, {len(d['issues'])} finding(s)")
            rows += [f"    - [{i['severity']}] {i['category']}: {i['finding'][:110]}" for i in d["issues"][:3]]
        else:
            rows.append(f"  Deeper review on the local model did not complete ({d.get('error') or 'unknown'})")
    return head + ("\n" + "\n".join(rows) if rows else "") + (f"\n  ... and {more} more" if more > 0 else "") + \
        ("\n  Coverage: " + "; ".join(res["caveats"]) if res.get("caveats") else "")


def fingerprint(md: Path) -> str:
    """sha256 over a skill's instructions (below the header) and its supporting files."""
    text = md.read_text(encoding="utf-8", errors="replace")
    body = text.split("\n\n", 1)[1] if "\n\n" in text else text
    h = hashlib.sha256(body.encode("utf-8"))
    sup = md.with_suffix("")
    if sup.is_dir():
        for f in sorted(p for p in sup.rglob("*") if p.is_file() and not p.name.startswith(".skillspector")):
            h.update(f.relative_to(sup).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def trust(cfg: dict, skill: dict) -> tuple[bool, str]:
    """May this skill be handed to the model? Built-in and her own skills: yes. Imported skills: only if they carry
    a scan stamp, the stamp is not a blocking verdict, and nothing has changed since it was scanned."""
    if skill.get("builtin"):
        return True, ""
    text = skill.get("text", "")
    if not re.search(r"^imported_from:", text, re.M):
        return True, ""
    if not settings(cfg)["enabled"]:
        return True, ""
    m = re.search(r"^scan: .*?\| (\w+) \|", text, re.M)
    sha = re.search(r"^scan_sha256: ([0-9a-f]{64})", text, re.M)
    if not m or not sha:
        return False, "it was imported without a SkillSpector scan"
    if m.group(1) in BLOCKING and settings(cfg).get("on_danger") != "ask":
        return False, f"its scan verdict was {m.group(1)}"
    try:
        if fingerprint(Path(skill["path"])) != sha.group(1):
            return False, "it changed after it was scanned"
    except OSError:
        return False, "it could not be verified"
    return True, ""
