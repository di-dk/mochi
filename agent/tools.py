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

from .platform_compat import IS_WINDOWS, drop_unsupported_tools, open_default, shell_argv
from .policy import Denied, Policy, is_sensitive_program, is_sensitive_window
from .registry import Registry

ROOT = Path(__file__).resolve().parent.parent
VIEW_MAX = 1280  # longest side of images shown to the model
# Shortcuts that open shells/system tools or lock/log off -> always ask, even in trusted mode
RISKY_HOTKEYS = {"win+r", "win+x", "win+l", "ctrl+alt+delete", "ctrl+shift+esc", "win+i", "alt+f4", "win+e"}


def active_window() -> str:
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow()
        return w.title if w else ""
    except Exception:  # noqa: BLE001
        return ""


def window_at(x: int, y: int) -> str:
    try:
        from pywinauto import Desktop
        e = Desktop(backend="uia").from_point(x, y)
        return e.top_level_parent().window_text() or ""
    except Exception:  # noqa: BLE001
        return ""
S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}
N = {"type": "number"}


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
    @reg.add("run_powershell" if IS_WINDOWS else "run_shell",
             ("Run a PowerShell command" if IS_WINDOWS else "Run a bash command")
             + " (cwd = workspace). Read-only commands run directly; others ask the user.",
             {"command": S, "timeout_s": I}, ["command"])
    def run_shell(command: str, timeout_s: int = 0):
        policy.check_shell(command)
        r = subprocess.run(shell_argv(command),
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
        errors: list[str] = []
        for backend in ("auto", "bing", "brave", "duckduckgo"):      # one flaky engine must not end the search
            try:
                res = DDGS().text(query, max_results=max_results, backend=backend)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{backend}: {type(e).__name__}")
                time.sleep(1)
                continue
            if res:
                return "\n\n".join(f"[{i+1}] {r.get('title')}\n{r.get('href')}\n{r.get('body')}"
                                    for i, r in enumerate(res))
        extra: list[str] = []
        try:                                            # Wikipedia and GitHub answer even when the engines are blocked
            w = httpx.get("https://en.wikipedia.org/w/api.php", timeout=15, headers={"User-Agent": "mochi"},
                          params={"action": "opensearch", "search": query, "limit": 3, "format": "json"}).json()
            extra += [f"[Wikipedia] {t}\n{u}\n{d}" for t, d, u in zip(w[1], w[2], w[3])]
        except Exception:  # noqa: BLE001
            pass
        try:
            g = httpx.get("https://api.github.com/search/repositories", timeout=15, headers={"User-Agent": "mochi"},
                          params={"q": query, "per_page": 4, "sort": "stars"}).json()
            extra += [f"[GitHub repo] {i['full_name']} ({i['stargazers_count']} stars)\n{i['html_url']}\n"
                      f"{i.get('description') or ''}" for i in g.get("items", [])]
        except Exception:  # noqa: BLE001
            pass
        if extra:
            return ("(The search engines failed (" + ", ".join(errors) + "); these come from Wikipedia and GitHub "
                    "instead. fetch_url the best one, or retry with other words.)\n\n" + "\n\n".join(extra))
        return ("ERROR: web search failed on every engine (" + ", ".join(errors or ["no results"]) + "). Try different "
                "words, or fetch_url a site you already know holds the answer (official docs, Wikipedia).")

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

    shot: dict = {"scale": 1.0, "left": 0, "top": 0}   # maps last screenshot pixels -> screen pixels

    @reg.add("screenshot",
             "Take a screenshot of the screen (or a region [left, top, width, height]) and LOOK at it (vision models). "
             "To click something you see, call mouse_click with the image coordinates and from_screenshot=true.",
             {"path": S, "region": {"type": "array", "items": I, "description": "[left, top, width, height]"}})
    def screenshot(path: str = "", region: list | None = None):
        import pyautogui
        p = policy.check_write(path or f"screenshots/shot_{time.strftime('%Y%m%d_%H%M%S')}.png")
        p.parent.mkdir(parents=True, exist_ok=True)
        img = pyautogui.screenshot(region=tuple(region) if region else None)
        img.save(p)
        w, h = pyautogui.size()
        s = max(img.width, img.height) / VIEW_MAX if max(img.width, img.height) > VIEW_MAX else 1.0
        shot.update(scale=s, left=region[0] if region else 0, top=region[1] if region else 0)
        vw, vh = round(img.width / s), round(img.height / s)
        return (f"Saved screenshot to {p} (screen {w}x{h}; you see it as {vw}x{vh})"
                + reg.attach_image(p, "screenshot"))

    @reg.add("focus_window", "Bring a window to the front by (partial) title.", {"title": S}, ["title"])
    def focus_window(title: str):
        import pygetwindow as gw
        wins = [w for w in gw.getWindowsWithTitle(title) if w.visible]
        if not wins:
            return f"No window matching {title!r}"
        policy.require("desktop", f"Focus window {wins[0].title!r}", sensitive=is_sensitive_window(wins[0].title))
        w = wins[0]
        if w.isMinimized:
            w.restore()
        w.activate()
        return f"Focused {w.title!r}"

    @reg.add("mouse_click",
             "Click at screen coordinates. Set from_screenshot=true when x,y come from the last screenshot image. "
             "Prefer app_click (no mouse needed) when the target is a normal app control. Asks the user first.",
             {"x": I, "y": I, "button": S, "double": B, "from_screenshot": B}, ["x", "y"])
    def mouse_click(x: int, y: int, button: str = "left", double: bool = False, from_screenshot: bool = False):
        import pyautogui
        if from_screenshot:
            x, y = round(shot["left"] + x * shot["scale"]), round(shot["top"] + y * shot["scale"])
        target = window_at(x, y)
        policy.require("desktop", f"{'Double-' if double else ''}{button}-click at screen ({x},{y}) on {target!r}",
                       sensitive=is_sensitive_window(target) or not target)
        pyautogui.click(x, y, clicks=2 if double else 1, button=button)
        return f"Clicked ({x},{y})"

    @reg.add("type_text", "Type text into the focused window. Asks the user first.",
             {"text": S, "press_enter": B}, ["text"])
    def type_text(text: str, press_enter: bool = False):
        import pyautogui
        active = active_window()
        policy.require("desktop", f"Type into {active!r}: {text[:200]!r}{' + Enter' if press_enter else ''}",
                       sensitive=is_sensitive_window(active) or not active)
        pyautogui.write(text, interval=0.01)
        if press_enter:
            pyautogui.press("enter")
        return "Typed."

    @reg.add("hotkey", "Press the key combination the user asked for (a list of key names). Asks the user first.",
             {"keys": {"type": "array", "items": S}}, ["keys"])
    def hotkey(keys: list):
        import pyautogui
        active = active_window()
        combo = "+".join(k.lower() for k in keys)
        policy.require("desktop", f"Press {combo} in {active!r}",
                       sensitive=is_sensitive_window(active) or not active or combo in RISKY_HOTKEYS)
        pyautogui.hotkey(*keys)
        return f"Pressed {'+'.join(keys)}"

    # ------------------------------------------------------------------ browser automation
    state: dict = {}

    def page():
        if "page" not in state:
            raise RuntimeError("No browser open. Call browser_open first.")
        return state["page"]

    @reg.add("browser_open",
             "Open a URL in Mochi's own Chromium browser (headless/invisible by default; logins and cookies are kept "
             "between sessions in her private profile). Use browser_screenshot to SEE the page.",
             {"url": S, "visible": B}, ["url"])
    def browser_open(url: str, visible: bool = False):
        if "page" in state and state.get("visible") != visible:
            browser_close()
        if "page" not in state:
            from playwright.sync_api import sync_playwright
            state["pw"] = sync_playwright().start()
            profile = ROOT / ".browser-profile"
            state["browser"] = state["pw"].chromium.launch_persistent_context(
                str(profile), headless=not visible, viewport={"width": 1280, "height": 900})
            state["visible"] = visible
            state["page"] = state["browser"].pages[0] if state["browser"].pages else state["browser"].new_page()
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

    @reg.add("browser_screenshot",
             "Screenshot the current page (visible area, or full_page=true) and LOOK at it (vision models).",
             {"path": S, "full_page": B})
    def browser_screenshot(path: str = "", full_page: bool = False):
        p = policy.check_write(path or f"screenshots/page_{time.strftime('%Y%m%d_%H%M%S')}.png")
        p.parent.mkdir(parents=True, exist_ok=True)
        page().screenshot(path=str(p), full_page=full_page)
        return f"Saved {p}" + reg.attach_image(p, f"browser page {page().url}")

    @reg.add("browser_close", "Close the automated browser.", {})
    def browser_close():
        if "browser" in state:
            state["browser"].close()
            state["pw"].stop()
            state.clear()
        return "Browser closed."

    # ------------------------------------------------------------------ apps
    RUNNABLE = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".lnk", ".scr", ".com", ".hta", ".reg", ".url",
                ".sh", ".desktop", ".appimage", ".run", ".bin", ".py"}

    @reg.add("open_with_default_app",
             "Open a file or URL with its default Windows app (e.g. a PDF in the reader, a URL in the user's browser).",
             {"target": S}, ["target"])
    def open_with_default_app(target: str):
        url = bool(re.match(r"^https?://", target))
        if not url:
            target = str(policy.check_read(target))
        policy.require("launch", f"Open {target}", sensitive=not url and Path(target).suffix.lower() in RUNNABLE)
        open_default(target)
        return f"Opened {target}"

    def start_apps() -> list[dict]:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        try:
            data = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else [data]

    @reg.add("list_apps", "List apps installed on this PC (Start menu), optionally filtered by name.",
             {"filter": S})
    def list_apps(filter: str = ""):  # noqa: A002
        apps = [a for a in start_apps() if filter.lower() in (a.get("Name") or "").lower()]
        return "\n".join(sorted({a["Name"] for a in apps})[:200]) or "No matching apps."

    @reg.add("launch_app",
             "Start an app by its name as shown in the Start menu, or by exe "
             "path / command, with optional arguments. Then wait a moment and use list_windows / app_inspect.",
             {"program": S, "args": {"type": "array", "items": S}}, ["program"])
    def launch_app(program: str, args: list | None = None):
        args = args or []
        sensitive = is_sensitive_program(program) or any(is_sensitive_program(a) for a in args[:1])
        exe = program if Path(program).is_file() else shutil.which(program)
        if exe:
            policy.require("launch", f"Launch {exe} {' '.join(args)}", sensitive=sensitive)
            subprocess.Popen([exe, *args], cwd=ws)
            return f"Started {exe}"
        apps = start_apps()
        exact = [a for a in apps if (a.get("Name") or "").lower() == program.lower()]
        hits = exact or [a for a in apps if program.lower() in (a.get("Name") or "").lower()]
        if not hits:
            return f"No app or program named {program!r}. Use list_apps to see what's installed."
        if len(hits) > 1 and not exact:
            return "Several apps match: " + ", ".join(a["Name"] for a in hits[:15]) + ". Use the exact name."
        app = hits[0]
        sensitive = sensitive or is_sensitive_program(app["Name"]) or bool(
            re.search(r"powershell|terminal|command prompt|registry|task manager|settings", app["Name"], re.I))
        policy.require("launch", f"Launch app {app['Name']}", sensitive=sensitive)
        if args:
            return "Start-menu apps can't take arguments; use an exe path for that."
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['AppID']}"])
        return f"Started {app['Name']} (give it a second or two to open)"

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
        from .pdf import NOTES
        return (f"Created {p} ({pages} page(s), {p.stat().st_size} bytes)"
                + ("".join(f"\nNote: {n}" for n in NOTES)))

    # ------------------------------------------------------------------ ComfyUI
    curl = cfg["comfyui"]["url"].rstrip("/")
    COMFY_DOWN = (f"ComfyUI is not running (nothing at {curl}). Don't try to work around it by drawing images some "
                  "other way. Call comfy_start (it asks the user first), then retry; if that fails, tell the user to start "
                  "ComfyUI.")

    @reg.add("comfy_status", "Check whether ComfyUI is running and show GPU/queue info.", {})
    def comfy_status():
        try:
            st = httpx.get(f"{curl}/system_stats", timeout=5).json()
            q = httpx.get(f"{curl}/queue", timeout=5).json()
        except httpx.HTTPError as e:
            return COMFY_DOWN
        dev = st.get("devices", [{}])[0]
        return (f"ComfyUI {st.get('system', {}).get('comfyui_version')} up. GPU {dev.get('name')}, "
                f"VRAM free {dev.get('vram_free', 0) / 2**30:.1f} GB. Queue running={len(q['queue_running'])} "
                f"pending={len(q['queue_pending'])}")

    NOT_IMAGE_MODEL = re.compile(r"audio|sfx|music|tts|voice|vae|clip|t5|encoder", re.I)
    LOADERS = {"checkpoints": ("CheckpointLoaderSimple", "ckpt_name"), "loras": ("LoraLoader", "lora_name"),
               "unets": ("UNETLoader", "unet_name")}

    def comfy_models(kind: str) -> list[str]:
        node, field = LOADERS.get(kind, LOADERS["checkpoints"])
        try:
            info = httpx.get(f"{curl}/object_info/{node}", timeout=15).json()
        except httpx.ConnectError:
            raise RuntimeError(COMFY_DOWN) from None
        return list(info[node]["input"]["required"][field][0])

    @reg.add("comfy_list_models",
             "List what ComfyUI has. kind: checkpoints (SD/SDXL image models for comfy_txt2img; audio models are "
             "marked), unets (diffusion models such as Qwen-Image-Edit and Wan video: used through workflow "
             "templates), loras, or all.", {"kind": S})
    def comfy_list_models(kind: str = "checkpoints"):
        if kind == "all":
            return "\n\n".join(f"{k}:\n" + ("\n".join(comfy_models(k)) or "(none)") for k in LOADERS)
        return "\n".join(m + ("   (audio/other, not for images)" if kind == "checkpoints" and NOT_IMAGE_MODEL.search(m)
                               else "") for m in comfy_models(kind))

    def free_llm_vram() -> str:
        """Ollama keeps the language model in GPU memory; ComfyUI needs that memory for pictures and video. Unload the
        models now (they load again by themselves on the next message). LM Studio is handled elsewhere."""
        if not cfg["comfyui"].get("free_llm_before", True):
            return ""
        m = re.match(r"(https?://[^/]+)", cfg["llm"].get("base_url", ""))
        if not m:
            return ""
        try:
            names = [x.get("name") for x in httpx.get(f"{m.group(1)}/api/ps", timeout=3).json().get("models", []) if x.get("name")]
            for n in names:
                httpx.post(f"{m.group(1)}/api/generate", json={"model": n, "keep_alive": 0}, timeout=20)
        except Exception:  # noqa: BLE001  (not Ollama, or not reachable: nothing to free)
            return ""
        if names:
            policy.audit("llm_unloaded_for_comfy", models=names)
        return ", ".join(names)

    def explain_comfy(text: str, node_type: str = "") -> str:
        """Turn a ComfyUI error into what to do about it."""
        low = text.lower()
        where = f" (in node {node_type})" if node_type else ""
        if any(k in low for k in ("out of memory", "vram", "cuda error", "allocate")):
            return (f"ComfyUI ran out of GPU memory{where}. Other programs hold it (the language model is unloaded "
                    "automatically; close other GPU apps if it keeps happening). Retry with a smaller size, fewer "
                    "frames or fewer seconds. Do not retry the same settings more than once.")
        if "value not in list" in low:
            return (f"A model or option name is wrong{where}: {text[:400]}. List the valid names with "
                    "comfy_list_models kind=all and use one of those exactly.")
        if "does not exist" in low and "node" in low or "missing_node_type" in low or "unknown node" in low:
            return f"ComfyUI does not have a node this workflow needs: {text[:300]}. Search the installed ones with comfy_node_info."
        return f"ComfyUI error{where}: {text[:500]}"

    def queue_and_wait(workflow: dict, out_prefix: str, timeout_s: int = 900) -> list[str]:
        free_llm_vram()
        try:
            r = httpx.post(f"{curl}/prompt", json={"prompt": workflow, "client_id": "local-agent"}, timeout=30)
        except httpx.ConnectError:
            raise RuntimeError(COMFY_DOWN) from None
        if r.status_code != 200:
            try:
                err = r.json().get("error", {})
                detail = err.get("message", "") + " " + "; ".join(
                    f"{n.get('class_type', '')}: " + ", ".join(e.get("message", "") + " " + e.get("details", "")
                                                              for e in (n.get("errors") or []))
                    for n in (r.json().get("node_errors") or {}).values())
            except ValueError:
                detail = r.text
            raise RuntimeError("ComfyUI rejected the workflow. " + explain_comfy(detail.strip() or r.text[:600]))
        pid = r.json()["prompt_id"]
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            h = httpx.get(f"{curl}/history/{pid}", timeout=15).json()
            if pid in h:
                entry = h[pid]
                if entry.get("status", {}).get("status_str") == "error":
                    ev = next((m[1] for m in entry["status"].get("messages", []) if m[0] == "execution_error"), {})
                    raise RuntimeError(explain_comfy(str(ev.get("exception_message") or entry["status"])[:600],
                                                     str(ev.get("node_type") or "")))
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

    SELF_PROMPT = re.compile(r"self[- ]?portrait|yourself|\bportrait of mochi\b|\bmochi\b[^,.]{0,25}\b(girl|maid|character|"
                             r"avatar|herself|portrait)\b", re.I)

    @reg.add("comfy_txt2img",
             "Generate an image with ComfyUI using a standard SD/SDXL checkpoint. Output is saved into workspace/comfy.",
             {"prompt": S, "negative": S, "checkpoint": S, "width": I, "height": I, "steps": I,
              "guidance": {"type": "number"}, "seed": I}, ["prompt"])
    def comfy_txt2img(prompt: str, negative: str = "lowres, blurry, watermark, text", checkpoint: str = "",
                      width: int = 1024, height: int = 1024, steps: int = 25, guidance: float = 6.0, seed: int = -1,
                      _self: bool = False):
        if not _self and (problem := off_topic(prompt)):
            return problem
        if SELF_PROMPT.search(prompt) and not _self:
            return ("ERROR: this is a picture of YOU. comfy_txt2img does not know your face and will not look like "
                    "you. Use draw_myself(scene=...) instead; it redraws you from your own portrait.")
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
        if cfg["comfyui"].get("default_checkpoint"):
            return cfg["comfyui"]["default_checkpoint"]
        usable = [m for m in comfy_models("checkpoints") if not NOT_IMAGE_MODEL.search(m)]
        if not usable:
            raise RuntimeError("ComfyUI has no image checkpoint (only audio or other models). Do not retry "
                               "comfy_txt2img. Tell the user to add an SD/SDXL checkpoint, or use "
                               "comfy_run_workflow with a template (see comfy_list_models kind=all).")
        return usable[0]

    WORKFLOWS = ROOT / "workflows"

    @reg.add("comfy_node_info",
             "Learn what ComfyUI can do so you can build workflows yourself. search='qwen' lists node names that "
             "contain the word; node='KSampler' shows that node's exact inputs (required ones marked *, with the "
             "allowed values) and outputs; template='qwen-image-edit' shows a ready workflow as JSON to copy from.",
             {"search": S, "node": S, "template": S})
    def comfy_node_info(search: str = "", node: str = "", template: str = ""):
        if template:
            f = WORKFLOWS / f"{re.sub(r'[^A-Za-z0-9_-]', '', template)}.json"
            if not f.is_file():
                return "No such template. Available: " + ", ".join(sorted(x.stem for x in WORKFLOWS.glob("*.json")))
            return f.read_text(encoding="utf-8")
        if not (search or node):
            return "ERROR: give search= (a word), node= (a node name) or template=."
        try:
            info = httpx.get(f"{curl}/object_info" + (f"/{node}" if node else ""), timeout=60).json()
        except httpx.ConnectError:
            raise RuntimeError(COMFY_DOWN) from None
        if node:
            d = info.get(node)
            if not d:
                return f"No node named {node!r}. Use search= to find the exact name."
            lines = [f"{node}: {(d.get('description') or d.get('display_name') or '')[:200]}"]
            for sect in ("required", "optional"):
                for k, v in (d.get("input", {}).get(sect) or {}).items():
                    t = v[0]
                    kind = (f"one of {t[:12]}" + ("…" if len(t) > 12 else "")) if isinstance(t, list) else str(t)
                    opt = v[1] if len(v) > 1 and isinstance(v[1], dict) else {}
                    lines.append(f"  {'*' if sect == 'required' else ' '} {k}: {kind}"
                                 + (f" (default {opt['default']})" if "default" in opt else ""))
            lines.append("outputs: " + ", ".join(d.get("output", [])))
            return "\n".join(lines)
        q = search.lower()
        names = sorted(n for n, d in info.items() if q in n.lower() or q in (d.get("display_name") or "").lower())
        return "\n".join(names[:80]) + (f"\n... {len(names) - 80} more; narrow the search" if len(names) > 80 else "") \
            if names else "No matching nodes."

    @reg.add("comfy_run_workflow",
             "Run a ComfyUI workflow. Use template='qwen-image-edit' (edit an image with an instruction) or "
             "template='wan-image-to-video' (animate an image), or path= a workflow saved in API format. "
             "'set' overrides inputs, e.g. {\"<node>.<field>\": <value>}. 'images' uploads workspace images "
             "into ComfyUI and sets the field, e.g. {\"7.image\": \"<workspace path of the picture>\"}. Outputs are copied into "
             "workspace/comfy. Read the skill comfy-edit-image or comfy-animate-image first.",
             {"template": S, "path": S, "set": {"type": "object"}, "images": {"type": "object"}})
    def comfy_run_workflow(template: str = "", path: str = "", set: dict | None = None,  # noqa: A002
                           images: dict | None = None):
        if template:
            f = WORKFLOWS / f"{re.sub(r'[^A-Za-z0-9_-]', '', template)}.json"
            if not f.is_file():
                have = ", ".join(sorted(x.stem for x in WORKFLOWS.glob("*.json")))
                return f"ERROR: no template {template!r}. Available: {have}"
            name = f.stem
        elif path:
            f, name = policy.check_read(path), Path(path).stem
        else:
            return "ERROR: give template= or path=."
        wf = json.loads(f.read_text(encoding="utf-8"))
        if "nodes" in wf and "links" in wf:
            return "ERROR: that is a UI-format workflow. Export it with 'Export (API)' in ComfyUI."
        help_text = (wf.pop("_mochi", None) or {}).get("help", "")
        overrides = dict(set or {})
        for key, rel in (images or {}).items():
            src = policy.check_read(rel)
            try:
                up = httpx.post(f"{curl}/upload/image", files={"image": (src.name, src.read_bytes(), "image/png")},
                                data={"overwrite": "true"}, timeout=120)
            except httpx.ConnectError:
                raise RuntimeError(COMFY_DOWN) from None
            if up.status_code != 200:
                return f"ERROR: ComfyUI would not take {src.name}: {up.text[:300]}"
            overrides[key] = up.json()["name"]
        for key, val in overrides.items():
            node, _, field = key.partition(".")
            if node not in wf or not field or field not in wf[node].get("inputs", {}):
                return (f"ERROR: this workflow has no input {key!r}. "
                        + (f"How to use this template: {help_text} " if help_text else "Inputs you can set: "
                           + ", ".join(f"{n}.{k}" for n, d in wf.items() for k, v in d.get("inputs", {}).items()
                                       if not isinstance(v, list))[:900])
                        + " (For a plain 'make a video' request use comfy_video instead.)")
            wf[node]["inputs"][field] = val
        needs = [f"{n}.image" for n, d in wf.items() if d.get("class_type") == "LoadImage"
                 and d["inputs"].get("image") == "input.png"]
        if template and needs:
            return (f"ERROR: this template needs an input picture: images={{\"{needs[0]}\": \"path/to/picture.png\"}}. "
                    + (help_text if help_text else "") + " To make a video from text alone use comfy_video or "
                    "template wan-text-to-video.")
        files = queue_and_wait(wf, name)
        return "Outputs:\n" + "\n".join(files)

    node_cache: dict = {"t": 0.0, "info": {}}

    def node_info(fresh: bool = False) -> dict:
        """ComfyUI's node list (several MB). Cached for 10 seconds; an explicit check always asks again."""
        if fresh or time.time() - node_cache["t"] > 10:
            node_cache.update(t=time.time(), info=httpx.get(f"{curl}/object_info", timeout=90).json())
        return node_cache["info"]

    def combo_options(entry) -> list | None:
        """The allowed values of a combo input, in either ComfyUI format; None when it is not a combo."""
        if not entry:
            return None
        if isinstance(entry[0], list):
            return entry[0]
        if entry[0] == "COMBO" and len(entry) > 1 and isinstance(entry[1], dict):
            return entry[1].get("options", [])
        return None

    def check_workflow(wf: dict, fresh: bool = False) -> list[str]:
        """Everything that would make ComfyUI refuse this workflow, found BEFORE running it: node types that do not
        exist, model files that are not installed, required inputs that are missing."""
        info, problems = node_info(fresh), []
        for nid, node in wf.items():
            if nid.startswith("_"):
                continue
            ct, spec = node.get("class_type"), info.get(node.get("class_type"))
            if not spec:
                problems.append(f"node {nid}: ComfyUI has no node type {ct!r}")
                continue
            ins = {**spec["input"].get("required", {}), **spec["input"].get("optional", {})}
            for k in spec["input"].get("required", {}):
                if k not in node.get("inputs", {}):
                    problems.append(f"node {nid} ({ct}) is missing the input {k!r}")
            for k, v in node.get("inputs", {}).items():
                opts = combo_options(ins.get(k))
                if isinstance(v, list) or opts is None or ct == "LoadImage" or v in opts:
                    continue
                problems.append(f"node {nid} ({ct}) input {k} = {v!r} is not installed or not allowed "
                                f"(valid: {', '.join(map(str, opts[:6]))}{'...' if len(opts) > 6 else ''})")
        return problems

    def template_problems(name: str, fresh: bool = False) -> list[str]:
        f = WORKFLOWS / f"{name}.json"
        if not f.is_file():
            return [f"no template {name!r}"]
        wf = json.loads(f.read_text(encoding="utf-8"))
        wf.pop("_mochi", None)
        return check_workflow(wf, fresh)

    @reg.add("comfy_check",
             "Test that a workflow template can run on this PC BEFORE running it: checks every node type and every "
             "model file against what ComfyUI has installed. template: a name from workflows/ (empty = check them all).",
             {"template": S})
    def comfy_check(template: str = ""):
        names = [re.sub(r"[^A-Za-z0-9_-]", "", template)] if template else sorted(x.stem for x in WORKFLOWS.glob("*.json"))
        try:
            rows = []
            for i, n in enumerate(names):
                p = template_problems(n, fresh=(i == 0))
                rows.append(f"OK      {n}" if not p else f"BROKEN  {n}:\n    - " + "\n    - ".join(p[:6]))
        except httpx.ConnectError:
            raise RuntimeError(COMFY_DOWN) from None
        return "\n".join(rows) or "No templates."

    @reg.add("comfy_start",
             "Start ComfyUI when it is not running (asks the user first). It listens only on this PC (127.0.0.1). "
             "Waits until it answers. Use it when a comfy tool says ComfyUI is not running.", {})
    def comfy_start():
        try:
            httpx.get(f"{curl}/system_stats", timeout=3)
            return "ComfyUI is already running."
        except httpx.HTTPError:
            pass
        base = Path(cfg["comfyui"].get("path") or os.environ.get("COMFYUI_PATH") or Path.home() / "ComfyUI").expanduser()
        py = next((base / d / ("Scripts/python.exe" if os.name == "nt" else "bin/python") for d in (".venv", "venv")
                   if (base / d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")).is_file()), None)
        if not (base / "main.py").is_file() or py is None:
            return (f"ERROR: I cannot find ComfyUI (looked in {base}). Ask the user to start it, or set comfyui.path in "
                    "config.local.yaml.")
        port = int(re.search(r":(\d+)", curl).group(1)) if re.search(r":(\d+)", curl) else 8188
        policy.require("launch", f"Start ComfyUI from {base} as a local server on 127.0.0.1:{port}")
        logf = ROOT / "logs"
        logf.mkdir(exist_ok=True)
        with (logf / "comfyui.log").open("ab") as out:
            subprocess.Popen([str(py), "main.py", "--listen", "127.0.0.1", "--port", str(port)], cwd=base, stdout=out,
                             stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(90):
            time.sleep(2)
            try:
                httpx.get(f"{curl}/system_stats", timeout=3)
                return "ComfyUI is running now. Try your request again."
            except httpx.HTTPError:
                continue
        return "ComfyUI was started but is not answering yet (loading takes a while). Wait a minute and call comfy_status; see logs/comfyui.log."

    GENERIC = {"make", "create", "generate", "video", "clip", "animation", "animate", "movie", "film", "image", "picture",
               "photo", "draw", "show", "want", "need", "give", "produce", "render", "short", "pic", "gif"}

    def off_topic(prompt: str) -> str:
        """The prompt must be about what the USER asked for. Returns an error the first time a prompt shares none of the
        subject words of the request (a model that pastes some other subject); an identical repeat is let through, since
        the user may have said 'that one'. Requests in other languages or without a clear subject are not judged."""
        from . import smart
        req = getattr(reg, "user_request", "") or ""
        if not req or not req.isascii() or not prompt.isascii():
            return ""
        subject = smart.words(req) - {smart._stem(g) for g in GENERIC} - GENERIC
        if len(subject) < 1 or subject & smart.words(prompt):
            return ""
        seen = getattr(reg, "off_topic_seen", None)
        if seen is None or prompt in seen:
            return ""
        seen.add(prompt)
        return (f"ERROR: your prompt has nothing to do with what the user asked for. They asked: {req.strip()[:200]!r}. "
                "Write the prompt about THEIR subject, in your own words, and call again.")

    SIZES = {"square": (480, 480), "landscape": (640, 368), "portrait": (368, 640)}

    @reg.add("comfy_video",
             "Make a short video with ComfyUI (Wan 2.2). Use this for ANY request to make a video, animation or clip. "
             "prompt: ONE vivid sentence built from what the USER asked for: the subject they named + what it does + where + "
             "light or camera. Never reuse words that are not in their request. With image= (a picture in your workspace) it "
             "animates that picture and the prompt describes only the MOTION. seconds 1-5 (default 2), size "
             "square|landscape|portrait. Takes 30-90 seconds. The video is saved in comfy/ and shown in the chat.",
             {"prompt": S, "image": S, "seconds": N, "size": S, "seed": I}, ["prompt"])
    def comfy_video(prompt: str, image: str = "", seconds: float = 2, size: str = "square", seed: int = -1):
        if (problem := off_topic(prompt)):
            return problem
        w, h = SIZES.get(size.lower(), SIZES["square"])
        frames = 16 * max(1, min(5, round(float(seconds or 2)))) + 1          # 16 frames per second
        seed = random.randint(1, 2**31) if seed < 0 else seed
        run = reg.tools["comfy_run_workflow"].fn

        def attempt(w: int, h: int, frames: int):
            if image:
                return run(template="wan-image-to-video", images={"9.image": image},
                           set={"10.text": prompt, "12.width": w, "12.height": h, "12.length": frames,
                                "13.noise_seed": seed, "14.noise_seed": seed})
            return run(template="wan-text-to-video",
                       set={"10.text": prompt, "9.width": w, "9.height": h, "9.length": frames,
                            "12.noise_seed": seed, "13.noise_seed": seed})
        retried = ""
        try:
            res = attempt(w, h, frames)
        except RuntimeError as e:
            if "out of GPU memory" not in str(e) or (w, h, frames) == (384, 384, 17):
                raise
            w, h, frames, retried = 384, 384, 17, " It ran out of GPU memory at the first size, so I retried smaller."
            res = attempt(w, h, frames)
        files = re.findall(r"^(/\S+\.(?:webm|mp4))$", str(res), re.M)
        if not files:
            return str(res)[:700]
        return (f"Made a {frames // 16}-second {w}x{h} video ({'from your picture' if image else 'from text'}, seed {seed})."
                f"{retried}\n"
                + reg.tools["share_file"].fn(path=files[0], caption=prompt[:100]))

    # what each installed model is good for, and whether a ready tool covers it
    CAPS = [
        (r"qwen_image_edit", "Edit a picture by instruction", "READY: draw_myself (yourself) or comfy_run_workflow template=qwen-image-edit", "qwen-image-edit"),
        (r"qwen_image_[0-9]", "Text to image with Qwen-Image (strong at text inside pictures)", "needs a workflow (comfy-new-workflow)", ""),
        (r"wan2\.2_t2v", "Text to video (Wan 2.2)", "READY: comfy_video prompt=...", "wan-text-to-video"),
        (r"wan2\.2_i2v", "Image to video (Wan 2.2)", "READY: comfy_video prompt=... image=...", "wan-image-to-video"),
        (r"ltx", "Video with sound (LTX 2.5)", "needs a workflow (comfy-new-workflow)", ""),
        (r"acestep|ace_step", "Music from text (ACE-Step)", "needs a workflow (comfy-new-workflow)", ""),
        (r"flux|hidream|sd3|chroma|z[-_]image", "Text to image (modern model)", "needs a workflow (comfy-new-workflow)", ""),
    ]

    @reg.add("comfy_capabilities",
             "Find out what ComfyUI can really do on this PC: every installed model grouped by purpose, which ones a "
             "ready tool covers, which still need a workflow, plus the GPU. Call it FIRST when asked what you can make "
             "or before an unfamiliar request, instead of guessing from model names.", {})
    def comfy_capabilities():
        try:
            def opts(node: str, field: str) -> list[str]:
                info = httpx.get(f"{curl}/object_info/{node}", timeout=15).json()
                entry = info.get(node, {}).get("input", {}).get("required", {}).get(field)
                return [str(o) for o in (combo_options(entry) or [])]
            ckpts, unets = opts("CheckpointLoaderSimple", "ckpt_name"), opts("UNETLoader", "unet_name")
            ups = opts("UpscaleModelLoader", "model_name")
            cnets = opts("ControlNetLoader", "control_net_name")
            status = comfy_status()
        except httpx.ConnectError:
            raise RuntimeError(COMFY_DOWN) from None
        lines, ready, todo = [status, ""], [], []
        image_ckpts = [m for m in ckpts if not NOT_IMAGE_MODEL.search(m)]
        if image_ckpts:
            ready.append(f"- Text to image, SD/SDXL style ({', '.join(image_ckpts)}): comfy_txt2img")
        for m in ckpts:
            if NOT_IMAGE_MODEL.search(m):
                todo.append(f"- Sound effects ({m}): needs a workflow (comfy-new-workflow)")
        seen, seen_fresh = set(), False
        for pat, what, how, tmpl in CAPS:
            hit = [m for m in unets if re.search(pat, m, re.I)]
            if hit and what not in seen:
                seen.add(what)
                bad = template_problems(tmpl, fresh=not seen_fresh) if tmpl else []
                seen_fresh = seen_fresh or bool(tmpl)
                if bad:                                   # READY only means ready when the template really validates
                    todo.append(f"- {what} ({', '.join(hit)}): BROKEN, template {tmpl} cannot run here: {bad[0]}")
                else:
                    (ready if how.startswith("READY") else todo).append(f"- {what} ({', '.join(hit)}): {how}")
        other = [m for m in unets if not any(re.search(p, m, re.I) for p, _, _, _ in CAPS)]
        if other:
            todo.append(f"- Other diffusion models ({', '.join(other)}): unknown purpose; look them up, then comfy-new-workflow")
        if ups:
            todo.append(f"- Upscale pictures ({', '.join(ups)}): needs a workflow")
        if cnets:
            todo.append(f"- ControlNet ({', '.join(cnets)}): needs a workflow")
        lines += ["READY (one tool does it):"] + (ready or ["- nothing"]) + ["", "INSTALLED, but you must build a workflow first "
                  "(skill comfy-new-workflow; comfy_node_info shows the nodes):"] + (todo or ["- nothing"])
        lines += ["", "Video models are NOT checkpoints. GPU memory is shared with the language model, which is unloaded "
                  "automatically before a job."]
        return "\n".join(lines)

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

    from .tools_extra import add_extra_tools
    add_extra_tools(reg, policy, cfg)
    drop_unsupported_tools(reg)      # drop the Windows implementations on Linux ...
    if not IS_WINDOWS:               # ... and register the Linux ones whose backend works on this machine
        from .tools_linux import add_linux_tools
        add_linux_tools(reg, policy, cfg)
    return reg
