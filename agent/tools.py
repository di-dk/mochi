"""All agent tools. Every side effect goes through Policy (sandbox + approval + audit)."""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .policy import Denied, Policy
from .registry import Registry

ROOT = Path(__file__).resolve().parent.parent
S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}


def build_tools(policy: Policy, cfg: dict) -> Registry:
    reg = Registry()
    ws = policy.workspace

    # ------------------------------------------------------------------ files
    @reg.add("list_dir", "List a directory (default: workspace root). Shows type, size, name.",
             {"path": S, "recursive": B})
    def list_dir(path: str = ".", recursive: bool = False):
        p = policy.check_read(path)
        items = p.rglob("*") if recursive else p.iterdir()
        out = []
        for i, f in enumerate(sorted(items)):
            if i >= 500:
                out.append("... (more than 500 entries)")
                break
            if policy.is_denied(f):
                continue
            rel = f.relative_to(p)
            out.append(f"{'D' if f.is_dir() else 'F'} {f.stat().st_size if f.is_file() else '':>10} {rel}")
        return f"{p}\n" + ("\n".join(out) or "(empty)")

    @reg.add("read_file", "Read a text file. Optional 1-based line range.",
             {"path": S, "start_line": I, "end_line": I}, ["path"])
    def read_file(path: str, start_line: int = 1, end_line: int = 0):
        p = policy.check_read(path)
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        end = end_line or len(lines)
        return "\n".join(f"{n}: {l}" for n, l in enumerate(lines[start_line - 1:end], start_line))

    @reg.add("write_file", "Create or overwrite a text file (relative paths are inside the workspace).",
             {"path": S, "content": S}, ["path", "content"])
    def write_file(path: str, content: str):
        p = policy.check_write(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {p}"

    @reg.add("edit_file", "Replace an exact, unique snippet in a text file.",
             {"path": S, "old": S, "new": S}, ["path", "old", "new"])
    def edit_file(path: str, old: str, new: str):
        p = policy.check_write(path)
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            return f"ERROR: snippet found {n} times; it must be unique."
        p.write_text(text.replace(old, new), encoding="utf-8")
        return f"Edited {p}"

    @reg.add("copy_path", "Copy a file or folder (e.g. bring an outside file into the workspace).",
             {"src": S, "dst": S}, ["src", "dst"])
    def copy_path(src: str, dst: str):
        s, d = policy.check_read(src), policy.check_write(dst)
        if d.exists():
            policy.require("overwrite", f"Overwrite existing {d}")
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree(s, d, dirs_exist_ok=True) if s.is_dir() else shutil.copy2(s, d))
        return f"Copied {s} -> {d}"

    @reg.add("delete_path", "Delete a file or folder. ALWAYS asks the user first.", {"path": S}, ["path"])
    def delete_path(path: str):
        p = policy.check_write(path, delete=True)
        if p == ws:
            raise Denied("Refusing to delete the workspace root.")
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        return f"Deleted {p}"

    # ------------------------------------------------------------------ shell / python
    @reg.add("run_powershell",
             "Run a PowerShell command (cwd = workspace). Read-only commands run directly; others ask the user.",
             {"command": S, "timeout_s": I}, ["command"])
    def run_powershell(command: str, timeout_s: int = 0):
        policy.check_shell(command)
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                           cwd=ws, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout_s or cfg["shell"]["timeout_s"])
        return f"exit={r.returncode}\n{r.stdout[-8000:]}" + (f"\nSTDERR:\n{r.stderr[-3000:]}" if r.stderr.strip() else "")

    @reg.add("run_python",
             "Run a Python script in the agent's venv (cwd = workspace). Has reportlab, httpx, pillow, pyautogui, "
             "trafilatura, markdown. Asks the user first.",
             {"code": S, "timeout_s": I}, ["code"])
    def run_python(code: str, timeout_s: int = 0):
        policy.require("python", "Run Python script:\n" + code[:1500])
        scratch = ws / ".scratch"
        scratch.mkdir(exist_ok=True)
        f = scratch / f"script_{int(time.time())}.py"
        f.write_text(code, encoding="utf-8")
        r = subprocess.run([sys.executable, str(f)], cwd=ws, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout_s or cfg["shell"]["timeout_s"])
        return f"exit={r.returncode}\n{r.stdout[-8000:]}" + (f"\nSTDERR:\n{r.stderr[-3000:]}" if r.stderr.strip() else "")

    # ------------------------------------------------------------------ web
    @reg.add("web_search", "Search the web (DuckDuckGo). Returns title, url, snippet.",
             {"query": S, "max_results": I}, ["query"])
    def web_search(query: str, max_results: int = 6):
        from ddgs import DDGS
        res = DDGS().text(query, max_results=max_results)
        return "\n\n".join(f"[{i+1}] {r.get('title')}\n{r.get('href')}\n{r.get('body')}" for i, r in enumerate(res)) or "No results."

    @reg.add("fetch_url", "Fetch a web page and return its main readable text.",
             {"url": S, "max_chars": I}, ["url"])
    def fetch_url(url: str, max_chars: int = 8000):
        import trafilatura
        r = httpx.get(url, follow_redirects=True, timeout=30,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LocalAgent/1.0"})
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_links=False) or r.text
        return text[:max_chars]

    @reg.add("download_file", "Download a URL into the workspace.", {"url": S, "path": S}, ["url", "path"])
    def download_file(url: str, path: str):
        p = policy.check_write(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with p.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return f"Saved {p.stat().st_size} bytes to {p}"

    # ------------------------------------------------------------------ desktop control
    @reg.add("list_windows", "List visible top-level windows with title, position and size.", {})
    def list_windows():
        import pygetwindow as gw
        rows = [f"{w.title!r} at ({w.left},{w.top}) {w.width}x{w.height}{' [active]' if w.isActive else ''}"
                for w in gw.getAllWindows() if w.title.strip() and w.visible and w.width > 50]
        return "\n".join(rows)

    @reg.add("screenshot", "Take a screenshot of the screen (or a region) and save it in the workspace.",
             {"path": S, "region": {"type": "array", "items": I, "description": "[left, top, width, height]"}})
    def screenshot(path: str = "", region: list | None = None):
        import pyautogui
        p = policy.check_write(path or f"screenshots/shot_{time.strftime('%Y%m%d_%H%M%S')}.png")
        p.parent.mkdir(parents=True, exist_ok=True)
        pyautogui.screenshot(str(p), region=tuple(region) if region else None)
        w, h = pyautogui.size()
        return f"Saved screenshot to {p} (screen {w}x{h})"

    @reg.add("focus_window", "Bring a window to the front by (partial) title.", {"title": S}, ["title"])
    def focus_window(title: str):
        import pygetwindow as gw
        wins = [w for w in gw.getWindowsWithTitle(title) if w.visible]
        if not wins:
            return f"No window matching {title!r}"
        policy.require("desktop", f"Focus window {wins[0].title!r}")
        w = wins[0]
        if w.isMinimized:
            w.restore()
        w.activate()
        return f"Focused {w.title!r}"

    @reg.add("mouse_click", "Click at screen coordinates. Asks the user first.",
             {"x": I, "y": I, "button": S, "double": B}, ["x", "y"])
    def mouse_click(x: int, y: int, button: str = "left", double: bool = False):
        import pyautogui
        policy.require("desktop", f"{'Double-' if double else ''}{button}-click at ({x},{y})")
        pyautogui.click(x, y, clicks=2 if double else 1, button=button)
        return f"Clicked ({x},{y})"

    @reg.add("type_text", "Type text into the focused window. Asks the user first.",
             {"text": S, "press_enter": B}, ["text"])
    def type_text(text: str, press_enter: bool = False):
        import pyautogui
        policy.require("desktop", f"Type into focused window: {text[:200]!r}{' + Enter' if press_enter else ''}")
        pyautogui.write(text, interval=0.01)
        if press_enter:
            pyautogui.press("enter")
        return "Typed."

    @reg.add("hotkey", "Press a key combination, e.g. ['ctrl','s']. Asks the user first.",
             {"keys": {"type": "array", "items": S}}, ["keys"])
    def hotkey(keys: list):
        import pyautogui
        policy.require("desktop", f"Press {'+'.join(keys)}")
        pyautogui.hotkey(*keys)
        return f"Pressed {'+'.join(keys)}"

    # ------------------------------------------------------------------ browser automation
    state: dict = {}

    def page():
        if "page" not in state:
            raise RuntimeError("No browser open. Call browser_open first.")
        return state["page"]

    @reg.add("browser_open", "Open a URL in an automated Chromium browser (headless by default).",
             {"url": S, "visible": B}, ["url"])
    def browser_open(url: str, visible: bool = False):
        if "page" not in state:
            from playwright.sync_api import sync_playwright
            state["pw"] = sync_playwright().start()
            state["browser"] = state["pw"].chromium.launch(headless=not visible)
            state["page"] = state["browser"].new_page()
        page().goto(url, timeout=45000)
        return f"Opened {page().url} — title: {page().title()}"

    @reg.add("browser_read", "Return the visible text of the current page plus its links/buttons/inputs.",
             {"max_chars": I})
    def browser_read(max_chars: int = 8000):
        pg = page()
        text = pg.inner_text("body")[:max_chars]
        els = pg.eval_on_selector_all(
            "a,button,input,textarea,select",
            "els => els.slice(0,80).map(e => `${e.tagName.toLowerCase()} ${e.id ? '#' + e.id : ''} "
            "${e.name ? 'name=' + e.name : ''} ${(e.innerText || e.value || e.placeholder || '').trim().slice(0,60)}`)")
        return f"URL: {pg.url}\n\n{text}\n\nINTERACTIVE ELEMENTS:\n" + "\n".join(els)

    @reg.add("browser_click", "Click an element by CSS selector or visible text. Asks the user first.",
             {"selector": S, "text": S})
    def browser_click(selector: str = "", text: str = ""):
        policy.require("browser_action", f"Click {selector or text!r} on {page().url}")
        (page().get_by_text(text).first if text else page().locator(selector).first).click(timeout=15000)
        page().wait_for_load_state()
        return f"Clicked. Now at {page().url}"

    @reg.add("browser_fill", "Fill an input by CSS selector. Asks the user first.",
             {"selector": S, "value": S, "submit": B}, ["selector", "value"])
    def browser_fill(selector: str, value: str, submit: bool = False):
        policy.require("browser_action", f"Fill {selector!r} with {value[:100]!r} on {page().url}")
        loc = page().locator(selector).first
        loc.fill(value, timeout=15000)
        if submit:
            loc.press("Enter")
            page().wait_for_load_state()
        return "Filled."

    @reg.add("browser_screenshot", "Save a screenshot of the current page to the workspace.", {"path": S})
    def browser_screenshot(path: str = ""):
        p = policy.check_write(path or f"screenshots/page_{time.strftime('%Y%m%d_%H%M%S')}.png")
        p.parent.mkdir(parents=True, exist_ok=True)
        page().screenshot(path=str(p), full_page=True)
        return f"Saved {p}"

    @reg.add("browser_close", "Close the automated browser.", {})
    def browser_close():
        if "browser" in state:
            state["browser"].close()
            state["pw"].stop()
            state.clear()
        return "Browser closed."

    # ------------------------------------------------------------------ apps
    @reg.add("open_with_default_app", "Open a file or URL with its default Windows app. Asks the user first.",
             {"target": S}, ["target"])
    def open_with_default_app(target: str):
        if not re.match(r"^https?://", target):
            target = str(policy.check_read(target))
        policy.require("launch", f"Open {target}")
        os.startfile(target)  # noqa: S606
        return f"Opened {target}"

    @reg.add("launch_app", "Start a program (exe path or name on PATH) with arguments. Asks the user first.",
             {"program": S, "args": {"type": "array", "items": S}}, ["program"])
    def launch_app(program: str, args: list | None = None):
        policy.require("launch", f"Launch {program} {' '.join(args or [])}")
        subprocess.Popen([program, *(args or [])], cwd=ws)
        return f"Started {program}"

    # ------------------------------------------------------------------ PDF
    @reg.add("create_pdf",
             "Create a PDF from Markdown-style text (# headings, - bullets, **bold**, blank-line paragraphs, "
             "![](image.png) images from the workspace).",
             {"path": S, "markdown": S, "title": S}, ["path", "markdown"])
    def create_pdf(path: str, markdown: str, title: str = ""):
        from .pdf import markdown_to_pdf
        p = policy.check_write(path if path.lower().endswith(".pdf") else path + ".pdf")
        p.parent.mkdir(parents=True, exist_ok=True)
        pages = markdown_to_pdf(markdown, p, title=title, base_dir=ws)
        return f"Created {p} ({pages} page(s), {p.stat().st_size} bytes)"

    # ------------------------------------------------------------------ ComfyUI
    curl = cfg["comfyui"]["url"].rstrip("/")

    @reg.add("comfy_status", "Check whether ComfyUI is running and show GPU/queue info.", {})
    def comfy_status():
        try:
            st = httpx.get(f"{curl}/system_stats", timeout=5).json()
            q = httpx.get(f"{curl}/queue", timeout=5).json()
        except httpx.HTTPError as e:
            return f"ComfyUI not reachable at {curl}: {e}. Ask the user to start ComfyUI Desktop."
        dev = st.get("devices", [{}])[0]
        return (f"ComfyUI {st.get('system', {}).get('comfyui_version')} up. GPU {dev.get('name')}, "
                f"VRAM free {dev.get('vram_free', 0) / 2**30:.1f} GB. Queue running={len(q['queue_running'])} "
                f"pending={len(q['queue_pending'])}")

    @reg.add("comfy_list_models", "List ComfyUI checkpoints (or another loader's options).", {"kind": S})
    def comfy_list_models(kind: str = "checkpoints"):
        node, field = {"checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
                       "loras": ("LoraLoader", "lora_name"),
                       "unets": ("UNETLoader", "unet_name")}.get(kind, ("CheckpointLoaderSimple", "ckpt_name"))
        info = httpx.get(f"{curl}/object_info/{node}", timeout=15).json()
        return "\n".join(info[node]["input"]["required"][field][0])

    def queue_and_wait(workflow: dict, out_prefix: str, timeout_s: int = 900) -> list[str]:
        r = httpx.post(f"{curl}/prompt", json={"prompt": workflow, "client_id": "local-agent"}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI rejected workflow: {r.text[:1500]}")
        pid = r.json()["prompt_id"]
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            h = httpx.get(f"{curl}/history/{pid}", timeout=15).json()
            if pid in h:
                entry = h[pid]
                if entry.get("status", {}).get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI error: {json.dumps(entry['status'])[:1500]}")
                saved = []
                dest = ws / "comfy"
                dest.mkdir(exist_ok=True)
                for node_out in entry.get("outputs", {}).values():
                    for kind in ("images", "gifs", "videos", "audio"):
                        for im in node_out.get(kind, []):
                            if im.get("type") != "output":
                                continue
                            data = httpx.get(f"{curl}/view", params=im, timeout=60).content
                            f = dest / f"{out_prefix}_{im['filename']}"
                            f.write_bytes(data)
                            saved.append(str(f))
                # hand VRAM back to the LLM
                httpx.post(f"{curl}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
                return saved
            time.sleep(2)
        raise TimeoutError(f"ComfyUI job {pid} not finished after {timeout_s}s")

    @reg.add("comfy_txt2img",
             "Generate an image with ComfyUI using a standard SD/SDXL checkpoint. Output is saved into workspace/comfy.",
             {"prompt": S, "negative": S, "checkpoint": S, "width": I, "height": I, "steps": I,
              "guidance": {"type": "number"}, "seed": I}, ["prompt"])
    def comfy_txt2img(prompt: str, negative: str = "lowres, blurry, watermark, text", checkpoint: str = "",
                      width: int = 1024, height: int = 1024, steps: int = 25, guidance: float = 6.0, seed: int = -1):
        ckpt = checkpoint or cfg_default_ckpt()
        seed = random.randint(0, 2**31) if seed < 0 else seed
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                        "latent_image": ["4", 0], "seed": seed, "steps": steps,
                                                        "cfg": guidance, "sampler_name": "euler_ancestral",
                                                        "scheduler": "normal", "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "local-agent"}},
        }
        files = queue_and_wait(wf, "txt2img")
        return f"Generated with {ckpt} seed={seed}:\n" + "\n".join(files)

    def cfg_default_ckpt() -> str:
        return cfg["comfyui"].get("default_checkpoint") or comfy_list_models().splitlines()[0]

    @reg.add("comfy_run_workflow",
             "Run a ComfyUI workflow saved in API format (JSON file). 'set' overrides inputs, e.g. "
             "{\"6.text\": \"a cat\", \"3.seed\": 42}. Outputs are copied into workspace/comfy.",
             {"path": S, "set": {"type": "object"}}, ["path"])
    def comfy_run_workflow(path: str, set: dict | None = None):  # noqa: A002
        wf = json.loads(policy.check_read(path).read_text(encoding="utf-8"))
        if "nodes" in wf and "links" in wf:
            return "ERROR: that is a UI-format workflow. Export it with 'Export (API)' in ComfyUI."
        for key, val in (set or {}).items():
            node, field = key.split(".", 1)
            wf[node]["inputs"][field] = val
        files = queue_and_wait(wf, Path(path).stem)
        return "Outputs:\n" + "\n".join(files)

    # ------------------------------------------------------------------ scheduling
    folder = cfg["scheduler"]["task_folder"]

    @reg.add("schedule_task",
             "Schedule the agent to run a prompt unattended via Windows Task Scheduler. In unattended runs, "
             "anything that needs approval is refused, so keep scheduled work inside the workspace. "
             "frequency: ONCE|DAILY|WEEKLY|HOURLY|MINUTE. time: HH:MM. days (WEEKLY): MON,TUE,... "
             "date: start date YYYY-MM-DD (optional). Runs only while the user is logged on.",
             {"name": S, "prompt": S, "frequency": S, "time": S, "days": S, "interval": I, "date": S},
             ["name", "prompt", "frequency"])
    def schedule_task(name: str, prompt: str, frequency: str, time: str = "09:00", days: str = "",
                      interval: int = 1, date: str = ""):
        name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
        policy.require("schedule", f"Create scheduled task '{folder}\\{name}' ({frequency} {time} {days}): {prompt[:300]}")
        tdir = ROOT / "tasks"
        tdir.mkdir(exist_ok=True)
        (tdir / f"{name}.txt").write_text(prompt, encoding="utf-8")
        tr = f'"{ROOT / "mochi.cmd"}" --unattended --task-file "{tdir / (name + ".txt")}"'
        cmd = ["schtasks", "/Create", "/F", "/TN", f"{folder}\\{name}", "/TR", tr, "/SC", frequency.upper()]
        if frequency.upper() in ("ONCE", "DAILY", "WEEKLY"):
            cmd += ["/ST", time]
        if frequency.upper() == "WEEKLY" and days:
            cmd += ["/D", days]
        if frequency.upper() in ("HOURLY", "MINUTE", "DAILY") and interval > 1:
            cmd += ["/MO", str(interval)]
        if date:  # accept ISO YYYY-MM-DD, convert to the locale format schtasks expects
            y, m, d = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date).groups()
            pat = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-Culture).DateTimeFormat.ShortDatePattern"],
                                 capture_output=True, text=True).stdout.strip().lower()
            cmd += ["/SD", {"d": f"{d}/{m}/{y}", "m": f"{m}/{d}/{y}"}.get(pat[:1], f"{y}/{m}/{d}")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return (r.stdout + r.stderr).strip()

    @reg.add("list_scheduled_tasks", "List the agent's scheduled tasks.", {})
    def list_scheduled_tasks():
        r = subprocess.run(["schtasks", "/Query", "/FO", "LIST"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        blocks = [b for b in r.stdout.split("\n\n") if f"\\{folder}\\" in b]
        return "\n\n".join(b.strip() for b in blocks) or "No scheduled agent tasks."

    @reg.add("delete_scheduled_task", "Delete one of the agent's scheduled tasks. Asks the user first.",
             {"name": S}, ["name"])
    def delete_scheduled_task(name: str):
        policy.require("schedule", f"Delete scheduled task '{folder}\\{name}'")
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", f"{folder}\\{name}"], capture_output=True, text=True)
        if r.returncode == 0:
            (ROOT / "tasks" / f"{name}.txt").unlink(missing_ok=True)
        return (r.stdout + r.stderr).strip()

    # ------------------------------------------------------------------ memory
    mem = ws / "memory.md"

    @reg.add("remember", "Save a durable note for future sessions (preferences, facts, paths).", {"note": S}, ["note"])
    def remember(note: str):
        with mem.open("a", encoding="utf-8") as f:
            f.write(f"- [{time.strftime('%Y-%m-%d')}] {note.strip()}\n")
        return "Saved to memory."

    @reg.add("recall", "Search saved memory notes (empty query = all).", {"query": S})
    def recall(query: str = ""):
        if not mem.exists():
            return "No memories yet."
        lines = mem.read_text(encoding="utf-8").splitlines()
        hits = [l for l in lines if all(w in l.lower() for w in query.lower().split())]
        return "\n".join(hits[-50:]) or "No matching memories."

    return reg
