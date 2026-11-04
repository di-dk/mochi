"""Extra tools: vision helpers, self-check, code/file search, planning, skills & lessons, Windows UI Automation."""
from __future__ import annotations

import fnmatch
import re
import time
from pathlib import Path

from .policy import Denied, Policy, is_sensitive_window
from .registry import Registry

ROOT = Path(__file__).resolve().parent.parent
BUILTIN_SKILLS = ROOT / "skills"
S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv", ".html", ".css", ".ps1",
            ".bat", ".cmd", ".ini", ".toml", ".xml", ".log", ".sql", ".java", ".cs", ".cpp", ".c", ".h", ".rs", ".go"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "skill"


def skill_dirs(ws: Path) -> list[Path]:
    return [ws / "skills", BUILTIN_SKILLS]


def parse_skill(f: Path) -> dict:
    text = f.read_text(encoding="utf-8", errors="replace")
    name = f.stem
    desc = ""
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    if m:
        desc = m.group(1).strip()
    m = re.search(r"^name:\s*(.+)$", text, re.M)
    if m:
        name = m.group(1).strip()
    return {"name": name, "description": desc, "path": f, "text": text,
            "builtin": BUILTIN_SKILLS in f.parents}


def all_skills(ws: Path) -> list[dict]:
    seen, out = set(), []
    for d in skill_dirs(ws):                     # user skills override built-in ones with the same file name
        for f in sorted(d.glob("*.md")) if d.exists() else []:
            if f.stem not in seen:
                seen.add(f.stem)
                out.append(parse_skill(f))
    return out


def skills_index(ws: Path, limit: int = 40) -> str:
    sk = all_skills(ws)[:limit]
    return "\n".join(f"- {s['name']}: {s['description']}" for s in sk)


def recent_lessons(ws: Path, limit: int = 25) -> str:
    f = ws / "lessons.md"
    if not f.exists():
        return ""
    return "\n".join([l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("- ")][-limit:])


def add_extra_tools(reg: Registry, policy: Policy, cfg: dict) -> None:
    ws = policy.workspace

    # ------------------------------------------------------------------ vision
    @reg.add("view_image", "LOOK at an image file (png/jpg/webp) — e.g. a generated picture, a chart, a photo.",
             {"path": S}, ["path"])
    def view_image(path: str):
        p = policy.check_read(path)
        if not p.exists():
            return f"ERROR: {p} not found"
        from PIL import Image
        with Image.open(p) as im:
            size = f"{im.width}x{im.height}"
        return f"Image {p} ({size})" + reg.attach_image(p, p.name)

    # ------------------------------------------------------------------ self-check
    @reg.add("inspect_pdf",
             "Check a PDF: page count and its text. render_page=N also renders that page as an image so you can "
             "SEE the layout (vision models). Use this to verify PDFs you created.",
             {"path": S, "max_chars": I, "render_page": I}, ["path"])
    def inspect_pdf(path: str, max_chars: int = 4000, render_page: int = 0):
        from pypdf import PdfReader
        p = policy.check_read(path)
        reader = PdfReader(str(p))
        n = len(reader.pages)
        text = "\n---page---\n".join((pg.extract_text() or "") for pg in reader.pages[:10])[:max_chars]
        out = f"{p}: {n} page(s), {p.stat().st_size} bytes, images on page 1: {len(reader.pages[0].images) if n else 0}\n{text}"
        if render_page:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(p))
            idx = min(max(render_page, 1), len(doc)) - 1
            img = doc[idx].render(scale=1.3).to_pil()
            shot = ws / ".scratch" / f"{p.stem}_page{idx + 1}.png"
            shot.parent.mkdir(exist_ok=True)
            img.save(shot)
            doc.close()
            out += f"\n\nRendered page {idx + 1} to {shot}" + reg.attach_image(shot, f"{p.name} page {idx + 1}")
        return out

    # ------------------------------------------------------------------ search
    @reg.add("find_files", "Find files by glob pattern (e.g. '**/*.py', '*.pdf') under a folder.",
             {"pattern": S, "path": S}, ["pattern"])
    def find_files(pattern: str, path: str = "."):
        base = policy.check_read(path)
        hits = [f for f in base.glob(pattern) if f.is_file() and not policy.is_denied(f)][:300]
        return "\n".join(str(f.relative_to(base)) for f in hits) or "No matches."

    @reg.add("search_files",
             "Search inside text files for a regex (like grep). Returns file:line: text. Optional glob filter.",
             {"regex": S, "path": S, "glob": S, "ignore_case": B, "max_results": I}, ["regex"])
    def search_files(regex: str, path: str = ".", glob: str = "*", ignore_case: bool = True, max_results: int = 80):
        base = policy.check_read(path)
        rx = re.compile(regex, re.I if ignore_case else 0)
        out = []
        for f in base.rglob("*"):
            if len(out) >= max_results:
                break
            if (not f.is_file() or f.suffix.lower() not in TEXT_EXT or policy.is_denied(f)
                    or not fnmatch.fnmatch(f.name, glob) or any(p in {".venv", "node_modules", ".git"} for p in f.parts)
                    or f.stat().st_size > 2_000_000):
                continue
            try:
                for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        out.append(f"{f.relative_to(base)}:{n}: {line.strip()[:200]}")
                        if len(out) >= max_results:
                            break
            except OSError:
                continue
        return "\n".join(out) or "No matches."

    # ------------------------------------------------------------------ planning
    plan: list[dict] = []
    reg.plan = plan  # the agent loop checks for unfinished steps

    def render_plan() -> str:
        icon = {"todo": "[ ]", "doing": "[>]", "done": "[x]", "skipped": "[-]"}
        return "\n".join(f"{i}. {icon.get(s['status'], '[ ]')} {s['step']}" for i, s in enumerate(plan, 1))

    @reg.add("set_plan",
             "For any task with 3+ steps: write a short numbered plan FIRST. Replaces the current plan.",
             {"steps": {"type": "array", "items": S}}, ["steps"])
    def set_plan(steps: list):
        plan.clear()
        plan.extend({"step": s, "status": "todo"} for s in steps[:15])
        return "Plan:\n" + render_plan()

    @reg.add("update_plan", "Mark a plan step (1-based) as doing / done / skipped.",
             {"step": I, "status": S}, ["step", "status"])
    def update_plan(step: int, status: str):
        if not 1 <= step <= len(plan):
            return f"ERROR: no step {step}"
        plan[step - 1]["status"] = status if status in ("todo", "doing", "done", "skipped") else "done"
        return render_plan()

    # ------------------------------------------------------------------ skills & lessons
    @reg.add("find_skills",
             "Search your saved skills (reusable recipes for tasks you've done before). Check this before "
             "starting an unfamiliar multi-step task.", {"query": S})
    def find_skills(query: str = ""):
        words = [w for w in query.lower().split() if len(w) > 2]
        sk = all_skills(ws)
        scored = sorted(((sum(w in (s["name"] + " " + s["description"] + " " + s["text"]).lower() for w in words), s)
                         for s in sk), key=lambda t: -t[0])
        hits = [s for score, s in scored if score > 0 or not words][:10]
        return "\n".join(f"- {s['name']}{' (built-in)' if s['builtin'] else ''}: {s['description']}" for s in hits) \
            or "No matching skills."

    @reg.add("read_skill", "Read a saved skill's full steps by name.", {"name": S}, ["name"])
    def read_skill(name: str):
        for s in all_skills(ws):
            if s["name"].lower() == name.lower() or s["path"].stem == slug(name):
                return s["text"]
        return f"No skill named {name!r}. Use find_skills."

    @reg.add("save_skill",
             "After you SUCCESSFULLY finish a multi-step task that could come up again, save how you did it as a "
             "reusable skill: concrete steps, which tools and settings worked, pitfalls. Same name = update.",
             {"name": S, "description": S, "steps": S}, ["name", "description", "steps"])
    def save_skill(name: str, description: str, steps: str):
        d = ws / "skills"
        d.mkdir(exist_ok=True)
        f = d / f"{slug(name)}.md"
        body = (f"name: {name.strip()}\ndescription: {description.strip()[:200]}\nupdated: {time.strftime('%Y-%m-%d')}\n\n"
                f"{steps.strip()[:6000]}\n")
        existed = f.exists()
        f.write_text(body, encoding="utf-8")
        return f"{'Updated' if existed else 'Saved'} skill '{name}' at {f}"

    @reg.add("save_lesson",
             "When something failed and you found the fix (or the user corrected you), save a one-line lesson so "
             "you don't repeat the mistake. Example: 'anima checkpoints fail in comfy_txt2img; use nova3DCGXL'.",
             {"lesson": S}, ["lesson"])
    def save_lesson(lesson: str):
        f = ws / "lessons.md"
        existing = f.read_text(encoding="utf-8") if f.exists() else ""
        line = lesson.strip().replace("\n", " ")[:300]
        if line.lower() in existing.lower():
            return "Already known."
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"- [{time.strftime('%Y-%m-%d')}] {line}\n")
        return "Lesson saved."

    # ------------------------------------------------------------------ Windows UI Automation
    def find_window(title: str):
        from pywinauto import Desktop
        t = str(title).lower()
        wins = [w for w in Desktop(backend="uia").windows() if t in (w.window_text() or "").lower()]
        if not wins:
            raise RuntimeError(f"No window whose title contains {title!r}. Use list_windows.")
        return wins[0]

    DIGIT_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
                   "7": "seven", "8": "eight", "9": "nine", "+": "plus", "-": "minus", "*": "multiply by",
                   "x": "multiply by", "/": "divide by", "=": "equals", ".": "decimal separator"}

    def find_control(win, name="", control_type="", automation_id="", index=0):
        # models sometimes pass numbers (name=1) — normalise everything to strings
        name, control_type, automation_id = str(name or ""), str(control_type or ""), str(automation_id or "")
        index = int(index or 0)
        ct, aid = control_type.lower(), automation_id
        elems = win.descendants()

        def match(n: str, by_id: bool = False):
            out = []
            for e in elems:
                info = e.element_info
                if n and n not in ((info.automation_id or "") if by_id else (info.name or "")).lower():
                    continue
                if ct and ct != (info.control_type or "").lower():
                    continue
                if aid and aid != (info.automation_id or ""):
                    continue
                out.append(e)
            return out

        n = name.lower()
        hits = match(n)
        if not hits and n in DIGIT_WORDS:            # "1" -> "One", "+" -> "Plus" (Calculator-style names)
            n = DIGIT_WORDS[n]
            hits = match(n)
        if not hits and n:                           # fall back to automation ids, e.g. "num1Button"
            hits = match(n, by_id=True)
        if not hits:
            raise RuntimeError(f"No control matching name={name!r} type={control_type!r} id={automation_id!r}. "
                               "Use app_inspect to see what's there.")
        exact = [e for e in hits if n and (e.element_info.name or "").lower() == n]
        if exact:                       # "Clear" should mean the "Clear" button, not "Clear all memory"
            hits = exact
        enabled = [e for e in hits if e.is_enabled()]
        hits = enabled or hits
        if index >= len(hits):
            raise RuntimeError(f"Only {len(hits)} matching controls; index {index} is out of range.")
        return hits[index], len(hits)

    @reg.add("app_inspect",
             "Read the controls of an app window via Windows UI Automation (works without moving the mouse and often "
             "while the window is in the background). Shows type, name, automation id. Use before app_click.",
             {"window": S, "filter": S, "max_items": I}, ["window"])
    def app_inspect(window: str, filter: str = "", max_items: int = 150):  # noqa: A002
        win = find_window(window)
        f = filter.lower()
        rows = []
        for e in win.descendants():
            info = e.element_info
            name, ct, aid = (info.name or "").strip(), info.control_type or "", info.automation_id or ""
            if not (name or aid) or ct in ("Pane", "Group", "Custom") and not name:
                continue
            line = f"{ct:<12} name={name[:60]!r}" + (f" id={aid!r}" if aid else "")
            if f and f not in line.lower():
                continue
            rows.append(line)
            if len(rows) >= max_items:
                rows.append("... (more; use filter)")
                break
        return f"Window: {win.window_text()!r}\n" + "\n".join(rows)

    @reg.add("app_read", "Read the text/value of an app control (by name / control_type / automation_id).",
             {"window": S, "name": S, "control_type": S, "automation_id": S, "index": I}, ["window"])
    def app_read(window: str, name: str = "", control_type: str = "", automation_id: str = "", index: int = 0):
        win = find_window(window)
        if not (name or control_type or automation_id):
            return "\n".join(t for t in win.texts() if t)[:4000]
        e, total = find_control(win, name, control_type, automation_id, index)
        val = ""
        try:
            val = e.iface_value.CurrentValue
        except Exception:  # noqa: BLE001
            pass
        return f"{e.element_info.control_type} {e.element_info.name!r}: {val or e.window_text()}  ({total} match(es))"

    @reg.add("app_click",
             "Press/toggle/select an app control via UI Automation (no mouse; usually works in the background). "
             "Asks the user first.",
             {"window": S, "name": S, "control_type": S, "automation_id": S, "index": I}, ["window"])
    def app_click(window: str, name: str = "", control_type: str = "", automation_id: str = "", index: int = 0):
        win = find_window(window)
        e, _ = find_control(win, name, control_type, automation_id, index)
        label = f"{e.element_info.control_type} {e.element_info.name!r} in {win.window_text()!r}"
        policy.require("desktop", f"Click {label}", sensitive=is_sensitive_window(win.window_text()))
        for method in ("invoke", "toggle", "select", "expand"):
            try:
                getattr(e, method)()
                return f"Clicked {label} via {method}"
            except Exception:  # noqa: BLE001
                continue
        e.click_input()  # last resort: real mouse click
        return f"Clicked {label} with the mouse (no automation pattern available)"

    @reg.add("app_set_text",
             "Set the text of an input/edit control via UI Automation (no typing; usually works in the background). "
             "Asks the user first.",
             {"window": S, "text": S, "name": S, "control_type": S, "automation_id": S, "index": I},
             ["window", "text"])
    def app_set_text(window: str, text: str, name: str = "", control_type: str = "", automation_id: str = "",
                     index: int = 0):
        win = find_window(window)
        e, _ = find_control(win, name, control_type or ("" if name or automation_id else "Edit"), automation_id, index)
        label = f"{e.element_info.control_type} {e.element_info.name!r} in {win.window_text()!r}"
        policy.require("desktop", f"Set text of {label} to {text[:150]!r}",
                       sensitive=is_sensitive_window(win.window_text()))
        try:
            e.iface_value.SetValue(text)
        except Exception:  # noqa: BLE001
            e.set_edit_text(text)
        return f"Set text of {label}"

    @reg.add("app_keys",
             "Send keystrokes to an app window (brings it to the front). pywinauto syntax: '^s' = Ctrl+S, "
             "'{ENTER}', '%f' = Alt+F. Asks the user first.",
             {"window": S, "keys": S}, ["window", "keys"])
    def app_keys(window: str, keys: str):
        win = find_window(window)
        policy.require("desktop", f"Send keys {keys!r} to {win.window_text()!r}",
                       sensitive=is_sensitive_window(win.window_text()))
        win.set_focus()
        win.type_keys(keys, with_spaces=True, pause=0.02)
        return f"Sent {keys!r}"

    @reg.add("app_close", "Close an app window politely (like clicking X). Asks the user first.",
             {"window": S}, ["window"])
    def app_close(window: str):
        win = find_window(window)
        policy.require("desktop", f"Close window {win.window_text()!r}",
                       sensitive=is_sensitive_window(win.window_text()))
        win.close()
        return f"Closed {win.window_text()!r}"

    from .tools_auto import add_auto_tools
    add_auto_tools(reg, policy, cfg)
