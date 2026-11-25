"""Linux versions of the Windows desktop tools (same names, same arguments, same approval rules).

  apps          list_apps, launch_app          XDG .desktop files + `gio launch`
  scheduling    schedule_task & co             systemd user timers
  vision        screenshot                     grim / cosmic-screenshot / gnome-screenshot / spectacle / scrot
  app control   list_windows, focus_window,    AT-SPI accessibility (works on Wayland and X11 for apps that
                app_inspect/read/click/          expose accessibility: GTK, Qt, Electron/Chromium with a11y on)
                set_text/close
  input         mouse_click, type_text,        a virtual keyboard + absolute pointer through /dev/uinput
                hotkey, app_keys

A tool is only registered when its backend works on this machine, so the model is never offered something that
cannot run. Everything that acts on the desktop asks first, exactly as on Windows.
"""
from __future__ import annotations

import atexit
import configparser
import fcntl
import os
import re
import shutil
import struct
import subprocess
import time
from pathlib import Path

from .policy import Policy, is_sensitive_program, is_sensitive_window
from .registry import Registry

S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}

# ----------------------------------------------------------------------------------------------- XDG apps


def desktop_entries() -> list[dict]:
    """Installed graphical apps from the XDG .desktop files (the Linux equivalent of the Start menu)."""
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    dirs = [data_home] + [Path(d) for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
    seen: dict[str, dict] = {}
    for base in dirs:
        root = base / "applications"
        if not root.is_dir():
            continue
        for f in root.rglob("*.desktop"):
            app_id = f.relative_to(root).as_posix().replace("/", "-")
            if app_id in seen:
                continue
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
                continue
            if e.get("Type", "Application") != "Application" or e.get("NoDisplay", "").lower() == "true" \
                    or e.get("Hidden", "").lower() == "true" or not e.get("Name"):
                continue
            seen[app_id] = {"name": e["Name"], "id": app_id, "path": str(f),
                            "categories": e.get("Categories", ""), "exec": e.get("Exec", "")}
    return list(seen.values())


SENSITIVE_APP_NAME = re.compile(r"terminal|konsole|console|shell|settings|software|installer|polkit|password|keyring", re.I)


# ------------------------------------------------------------------------------------------ screenshots
def capture_screen(path: Path) -> None:
    """Save a full-screen screenshot to `path` using whichever tool this desktop has."""
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    tools = [["grim", str(path)], ["cosmic-screenshot"], ["gnome-screenshot", "-f", str(path)],
             ["spectacle", "-b", "-n", "-f", "-o", str(path)], ["scrot", "-o", str(path)],
             ["import", "-window", "root", str(path)]]
    if not wayland:
        tools = tools[4:] + tools[:4]
    tried: list[str] = []
    for cmd in tools:
        if not shutil.which(cmd[0]):
            continue
        if cmd[0] == "cosmic-screenshot":
            tmp = path.parent / ".cosmic-shot"
            tmp.mkdir(exist_ok=True)
            r = subprocess.run(["cosmic-screenshot", "--interactive=false", "--modal=false", "--notify=false",
                                "-s", str(tmp)], capture_output=True, text=True, timeout=30)
            pngs = sorted(tmp.glob("*.png"), key=lambda p: p.stat().st_mtime)
            if r.returncode == 0 and pngs:
                shutil.move(str(pngs[-1]), path)
                shutil.rmtree(tmp, ignore_errors=True)
                return
            shutil.rmtree(tmp, ignore_errors=True)
            tried.append(f"cosmic-screenshot: {(r.stderr or r.stdout).strip()[:120]}")
            continue
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and path.exists() and path.stat().st_size > 0:
            return
        tried.append(f"{cmd[0]}: {(r.stderr or r.stdout).strip()[:120]}")
    hint = "sudo apt install grim" if wayland else "sudo apt install scrot"
    raise RuntimeError("Could not take a screenshot" + (f" ({'; '.join(tried)})" if tried else "")
                       + f". Install a screenshot tool, e.g. `{hint}`. For web pages use browser_screenshot.")


# ------------------------------------------------------------------------------------- uinput keyboard/mouse
_UI_SET_EVBIT, _UI_SET_KEYBIT, _UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045567
_UI_DEV_CREATE, _UI_DEV_DESTROY, _UI_DEV_SETUP, _UI_ABS_SETUP = 0x5501, 0x5502, 0x405C5503, 0x401C5504
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
ABS_X, ABS_Y, ABS_MAX = 0, 1, 32767
BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}

KEYS = {"esc": 1, "escape": 1, "-": 12, "=": 13, "backspace": 14, "tab": 15, "[": 26, "]": 27, "enter": 28, "return": 28,
        "ctrl": 29, "control": 29, ";": 39, "'": 40, "`": 41, "shift": 42, "\\": 43, ",": 51, ".": 52, "/": 53,
        "alt": 56, "space": 57, " ": 57, "capslock": 58, "home": 102, "up": 103, "pageup": 104, "left": 105,
        "right": 106, "end": 107, "down": 108, "pagedown": 109, "insert": 110, "delete": 111, "del": 111,
        "super": 125, "win": 125, "meta": 125, "cmd": 125, "altgr": 100}
for _i, _c in enumerate("1234567890"):
    KEYS[_c] = 2 + _i
for _i, _c in enumerate("qwertyuiop"):
    KEYS[_c] = 16 + _i
for _i, _c in enumerate("asdfghjkl"):
    KEYS[_c] = 30 + _i
for _i, _c in enumerate("zxcvbnm"):
    KEYS[_c] = 44 + _i
for _i in range(1, 11):
    KEYS[f"f{_i}"] = 58 + _i
KEYS["f11"], KEYS["f12"] = 87, 88
SHIFTED = dict(zip('!@#$%^&*()_+{}|:"~<>?', "1234567890-=[]\\;'`,./"))
# keyboard layouts whose letter/symbol keys sit where the US ones do (type_text sends physical key codes)
US_LIKE_LAYOUTS = {"us", "au", "nz", "ie"}
RISKY_HOTKEYS = {"super+l", "ctrl+alt+delete", "ctrl+alt+t", "alt+f2", "alt+f4", "super+t", "ctrl+alt+backspace",
                 "super+r", "ctrl+shift+escape", "super+x"}


def keyboard_layout() -> str:
    """Active XKB layout name (first one), from COSMIC's config or setxkbmap; '' when unknown."""
    cfg = Path.home() / ".config/cosmic/com.system76.CosmicComp/v1/xkb_config"
    try:
        m = re.search(r'layout:\s*"([^"]*)"', cfg.read_text(encoding="utf-8"))
        if m:
            return m.group(1).split(",")[0].strip().lower()
    except OSError:
        pass
    if shutil.which("setxkbmap"):
        r = subprocess.run(["setxkbmap", "-query"], capture_output=True, text=True)
        m = re.search(r"layout:\s*(\S+)", r.stdout)
        if m:
            return m.group(1).split(",")[0].lower()
    return ""


class UInput:
    """A virtual keyboard and an absolute pointer. Created on first use, removed at exit."""

    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, _UI_SET_EVBIT, EV_KEY)
            for code in set(KEYS.values()) | set(BTN.values()):
                fcntl.ioctl(self.fd, _UI_SET_KEYBIT, code)
            fcntl.ioctl(self.fd, _UI_SET_EVBIT, EV_ABS)
            for axis in (ABS_X, ABS_Y):
                fcntl.ioctl(self.fd, _UI_SET_ABSBIT, axis)
                fcntl.ioctl(self.fd, _UI_ABS_SETUP, struct.pack("<H2x6i", axis, 0, 0, ABS_MAX, 0, 0, 0))
            fcntl.ioctl(self.fd, _UI_DEV_SETUP, struct.pack("<HHHH80sI", 3, 0x1209, 0x4D43, 1, b"Mochi virtual input", 0))
            fcntl.ioctl(self.fd, _UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        time.sleep(0.4)          # let the compositor notice the new device before the first event
        atexit.register(self.close)

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, _UI_DEV_DESTROY)
            os.close(self.fd)
        except OSError:
            pass

    def _emit(self, etype: int, code: int, value: int) -> None:
        t = time.time()
        os.write(self.fd, struct.pack("llHHi", int(t), int((t % 1) * 1e6), etype, code, value))

    def _sync(self) -> None:
        self._emit(EV_SYN, 0, 0)

    def key(self, code: int, down: bool) -> None:
        self._emit(EV_KEY, code, 1 if down else 0)
        self._sync()

    def combo(self, codes: list[int], pause: float = 0.02) -> None:
        for c in codes:
            self.key(c, True)
            time.sleep(pause)
        for c in reversed(codes):
            self.key(c, False)
            time.sleep(pause)

    def type_char(self, ch: str) -> None:
        shift = ch.isupper() or ch in SHIFTED
        base = SHIFTED.get(ch, ch.lower())
        if base not in KEYS:
            raise RuntimeError(f"Cannot type {ch!r} (no key for it); use app_set_text or the clipboard instead.")
        self.combo([KEYS["shift"], KEYS[base]] if shift else [KEYS[base]], pause=0.004)

    def move(self, x: float, y: float, width: int, height: int) -> None:
        self._emit(EV_ABS, ABS_X, max(0, min(ABS_MAX, round(x / width * ABS_MAX))))
        self._emit(EV_ABS, ABS_Y, max(0, min(ABS_MAX, round(y / height * ABS_MAX))))
        self._sync()

    def click(self, button: str = "left", times: int = 1) -> None:
        code = BTN.get(button, BTN["left"])
        for _ in range(times):
            self._emit(EV_KEY, code, 1)
            self._sync()
            time.sleep(0.03)
            self._emit(EV_KEY, code, 0)
            self._sync()
            time.sleep(0.05)


def parse_keys(spec: str) -> list[list[int]]:
    """pywinauto-style key string -> list of key chords. '^s' Ctrl+S, '%f' Alt+F, '+a' Shift+A, '{ENTER}' Enter,
    other characters are typed as they are."""
    out: list[list[int]] = []
    i, mods = 0, []
    while i < len(spec):
        ch = spec[i]
        if ch in "^%+" and i + 1 < len(spec):
            mods.append({"^": KEYS["ctrl"], "%": KEYS["alt"], "+": KEYS["shift"]}[ch])
            i += 1
            continue
        if ch == "{":
            j = spec.find("}", i)
            if j == -1:
                raise RuntimeError("Unclosed { in keys")
            name = spec[i + 1:j].lower()
            i = j + 1
            if name not in KEYS:
                raise RuntimeError(f"Unknown key {{{name.upper()}}}")
            out.append(mods + [KEYS[name]])
        else:
            i += 1
            base = SHIFTED.get(ch, ch.lower())
            if base not in KEYS:
                raise RuntimeError(f"Cannot send {ch!r}")
            shift = [KEYS["shift"]] if (ch.isupper() or ch in SHIFTED) and KEYS["shift"] not in mods else []
            out.append(mods + shift + [KEYS[base]])
        mods = []
    return out


# ------------------------------------------------------------------------------------------------ AT-SPI
ROLE_ALIASES = {"button": "push button", "edit": "text", "checkbox": "check box", "combobox": "combo box",
                "menuitem": "menu item", "tabitem": "page tab", "listitem": "list item", "hyperlink": "link",
                "radiobutton": "radio button", "window": "frame"}
TOP_ROLES = {"frame", "dialog", "window", "alert", "file chooser"}


def _atspi():
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    return Atspi


def atspi_available() -> bool:
    try:
        A = _atspi()
        A.get_desktop(0)
        return True
    except Exception:  # noqa: BLE001
        return False


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def top_windows() -> list[dict]:
    A = _atspi()
    desk = A.get_desktop(0)
    wins = []
    for i in range(desk.get_child_count()):
        app = _safe(lambda: desk.get_child_at_index(i))
        if app is None:
            continue
        for j in range(_safe(app.get_child_count, 0)):
            w = _safe(lambda: app.get_child_at_index(j))
            if w is None or _safe(w.get_role_name, "") not in TOP_ROLES:
                continue
            states = _safe(w.get_state_set)
            wins.append({"title": _safe(w.get_name, "") or "", "app": _safe(app.get_name, "") or "", "obj": w,
                         "active": bool(states and states.contains(A.StateType.ACTIVE)),
                         "showing": bool(states and states.contains(A.StateType.SHOWING))})
    return wins


def active_window_title() -> str:
    try:
        return next((w["title"] or w["app"] for w in top_windows() if w["active"]), "")
    except Exception:  # noqa: BLE001
        return ""


def find_window(title: str) -> dict:
    t = str(title).lower()
    wins = top_windows()
    for w in wins:
        if t and t in w["title"].lower():
            return w
    for w in wins:
        if t and t in w["app"].lower():
            return w
    raise RuntimeError(f"No window whose title contains {title!r}. Use list_windows (only apps that expose "
                       "accessibility are visible).")


def walk(root, limit: int = 4000):
    """Breadth-first over an accessible tree."""
    queue, n = [root], 0
    while queue and n < limit:
        node = queue.pop(0)
        for i in range(_safe(node.get_child_count, 0)):
            c = _safe(lambda: node.get_child_at_index(i))
            if c is not None:
                n += 1
                yield c
                queue.append(c)


def _info(e) -> tuple[str, str, str]:
    return (_safe(e.get_role_name, "") or "", (_safe(e.get_name, "") or "").strip(),
            _safe(e.get_accessible_id, "") or "")


def find_control(win: dict, name="", control_type="", automation_id="", index=0):
    name, ct, aid = str(name or "").lower(), str(control_type or "").lower(), str(automation_id or "")
    ct = ROLE_ALIASES.get(ct.replace(" ", ""), ct)
    hits = []
    for e in walk(win["obj"]):
        role, n, eid = _info(e)
        if name and name not in n.lower():
            continue
        if ct and ct != role.lower() and ct not in role.lower():
            continue
        if aid and aid != eid:
            continue
        hits.append(e)
    if not hits and name:                       # fall back to accessible ids
        hits = [e for e in walk(win["obj"]) if name in _info(e)[2].lower()]
    if not hits:
        raise RuntimeError(f"No control matching name={name!r} type={control_type!r} id={automation_id!r}. "
                           "Use app_inspect to see what's there.")
    exact = [e for e in hits if name and _info(e)[1].lower() == name]
    hits = exact or hits
    A = _atspi()
    enabled = [e for e in hits if (s := _safe(e.get_state_set)) and s.contains(A.StateType.ENABLED)]
    hits = enabled or hits
    if int(index or 0) >= len(hits):
        raise RuntimeError(f"Only {len(hits)} matching controls; index {index} is out of range.")
    return hits[int(index or 0)], len(hits)


def control_text(e) -> str:
    A = _atspi()
    txt = _safe(lambda: A.Text.get_text(e, 0, -1))
    if txt:
        return txt
    val = _safe(lambda: A.Value.get_current_value(e))
    return "" if val is None else str(val)


# -------------------------------------------------------------------------------------------------- tools
def add_linux_tools(reg: Registry, policy: Policy, cfg: dict) -> None:
    from .tools import ROOT, VIEW_MAX      # late import: tools.py imports this module lazily
    ws = policy.workspace
    shot: dict = {"scale": 1.0, "left": 0, "top": 0, "size": None}   # last screenshot: pixels -> screen mapping

    # ---------------------------------------------------------------- apps
    @reg.add("list_apps", "List apps installed on this PC (app menu), optionally filtered by name.", {"filter": S})
    def list_apps(filter: str = ""):  # noqa: A002
        names = sorted({a["name"] for a in desktop_entries() if filter.lower() in a["name"].lower()})
        return "\n".join(names[:200]) or "No matching apps."

    @reg.add("launch_app",
             "Start an app by its name as shown in the app menu (e.g. 'Calculator', 'Files', 'Firefox'), or by "
             "program path / command, with optional arguments. Then wait a moment and use list_windows / app_inspect.",
             {"program": S, "args": {"type": "array", "items": S}}, ["program"])
    def launch_app(program: str, args: list | None = None):
        args = args or []
        sensitive = is_sensitive_program(program) or any(is_sensitive_program(a) for a in args[:1])
        exe = program if Path(program).is_file() else shutil.which(program)
        if exe:
            policy.require("launch", f"Launch {exe} {' '.join(args)}", sensitive=sensitive)
            subprocess.Popen([exe, *args], cwd=ws, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Started {exe}"
        apps = desktop_entries()
        exact = [a for a in apps if a["name"].lower() == program.lower()]
        hits = exact or [a for a in apps if program.lower() in a["name"].lower()]
        if not hits:
            return f"No app or program named {program!r}. Use list_apps to see what's installed."
        if len(hits) > 1 and not exact:
            return "Several apps match: " + ", ".join(a["name"] for a in hits[:15]) + ". Use the exact name."
        app = hits[0]
        sensitive = sensitive or bool(SENSITIVE_APP_NAME.search(app["name"])) or "TerminalEmulator" in app["categories"] \
            or "Settings" in app["categories"]
        policy.require("launch", f"Launch app {app['name']}", sensitive=sensitive)
        if args:
            return "Menu apps can't take arguments here; use a program path or command for that."
        subprocess.Popen(["gio", "launch", app["path"]], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Started {app['name']} (give it a second or two to open)"

    # ---------------------------------------------------------------- scheduling (systemd user timers)
    if shutil.which("systemctl"):
        unit_dir = Path.home() / ".config/systemd/user"
        prefix = "mochi-"

        def sysd(*a):
            return subprocess.run(["systemctl", "--user", *a], capture_output=True, text=True)

        def calendar(frequency: str, time_s: str, days: str, interval: int, date: str) -> str:
            f = frequency.upper()
            if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_s or ""):
                raise RuntimeError("time must be HH:MM (24 hour)")
            hh, mm = (int(x) for x in time_s.split(":"))
            interval = max(1, int(interval or 1))
            if f == "ONCE":
                d = date or time.strftime("%Y-%m-%d")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                    raise RuntimeError("date must be YYYY-MM-DD")
                return f"{d} {hh:02d}:{mm:02d}:00"
            if f == "DAILY":
                return f"*-*-{'1/' + str(interval) if interval > 1 else '*'} {hh:02d}:{mm:02d}:00"
            if f == "WEEKLY":
                names = [d.strip().upper()[:3] for d in (days or "MON").split(",") if d.strip()]
                if not names or any(n not in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN") for n in names):
                    raise RuntimeError("days must be like MON,WED,FRI")
                return f"{','.join(n.title() for n in names)} *-*-* {hh:02d}:{mm:02d}:00"
            if f == "HOURLY":
                return f"*-*-* {'0/' + str(interval) if interval > 1 else '*'}:{mm:02d}:00"
            if f == "MINUTE":
                return f"*-*-* *:{'0/' + str(interval) if interval > 1 else '*'}:00"
            raise RuntimeError("frequency must be ONCE, DAILY, WEEKLY, HOURLY or MINUTE")

        def quote(p: Path) -> str:
            return '"' + str(p).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'

        @reg.add("schedule_task",
                 "Schedule the agent to run a prompt unattended via a systemd user timer. In unattended runs, "
                 "anything that needs approval is refused, so keep scheduled work inside the workspace. "
                 "frequency: ONCE|DAILY|WEEKLY|HOURLY|MINUTE. time: HH:MM. days (WEEKLY): MON,TUE,... "
                 "date: start date YYYY-MM-DD (ONCE, optional). Runs only while the user is logged in "
                 "(unless lingering is enabled).",
                 {"name": S, "prompt": S, "frequency": S, "time": S, "days": S, "interval": I, "date": S},
                 ["name", "prompt", "frequency"])
        def schedule_task(name: str, prompt: str, frequency: str, time: str = "09:00", days: str = "",
                          interval: int = 1, date: str = ""):  # noqa: A002
            name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
            when = calendar(frequency, time, days, interval, date)
            ok = subprocess.run(["systemd-analyze", "calendar", when], capture_output=True, text=True)
            if ok.returncode != 0:
                return f"ERROR: systemd rejected the schedule {when!r}: {ok.stderr.strip()[:200]}"
            policy.require("schedule", f"Create scheduled task '{name}' ({frequency} {time} {days}): {prompt[:300]}")
            tdir = ROOT / "tasks"
            tdir.mkdir(exist_ok=True)
            tfile = tdir / f"{name}.txt"
            tfile.write_text(prompt, encoding="utf-8")
            unit_dir.mkdir(parents=True, exist_ok=True)
            (unit_dir / f"{prefix}{name}.service").write_text(
                "[Unit]\nDescription=Mochi scheduled task " + name + "\n\n[Service]\nType=oneshot\n"
                f"WorkingDirectory={quote(ROOT)}\n"
                "Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin\n"
                f"ExecStart={quote(ROOT / 'mochi')} --unattended --task-file {quote(tfile)}\n", encoding="utf-8")
            (unit_dir / f"{prefix}{name}.timer").write_text(
                f"[Unit]\nDescription=Mochi schedule for {name}\n\n[Timer]\nOnCalendar={when}\nPersistent=true\n\n"
                "[Install]\nWantedBy=timers.target\n", encoding="utf-8")
            sysd("daemon-reload")
            r = sysd("enable", "--now", f"{prefix}{name}.timer")
            if r.returncode != 0:
                return f"ERROR: could not enable the timer: {(r.stderr or r.stdout).strip()[:300]}"
            nxt = sysd("list-timers", f"{prefix}{name}.timer", "--no-legend").stdout.strip()
            return f"Scheduled '{name}' ({when}).\n{nxt}"

        @reg.add("list_scheduled_tasks", "List the agent's scheduled tasks.", {})
        def list_scheduled_tasks():
            r = sysd("list-timers", f"{prefix}*", "--all", "--no-pager")
            lines = [l for l in r.stdout.splitlines() if prefix in l]
            return "\n".join(lines) or "No scheduled agent tasks."

        @reg.add("delete_scheduled_task", "Delete one of the agent's scheduled tasks. Asks the user first.",
                 {"name": S}, ["name"])
        def delete_scheduled_task(name: str):
            name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
            if not (unit_dir / f"{prefix}{name}.timer").exists():
                return f"No scheduled task named {name!r}."
            policy.require("schedule", f"Delete scheduled task '{name}'")
            sysd("disable", "--now", f"{prefix}{name}.timer")
            for ext in ("timer", "service"):
                (unit_dir / f"{prefix}{name}.{ext}").unlink(missing_ok=True)
            sysd("daemon-reload")
            (ROOT / "tasks" / f"{name}.txt").unlink(missing_ok=True)
            return f"Deleted scheduled task {name!r}."

    # ---------------------------------------------------------------- screenshot
    @reg.add("screenshot",
             "Take a screenshot of the screen (or a region [left, top, width, height]) and LOOK at it (vision models). "
             "To click something you see, call mouse_click with the image coordinates and from_screenshot=true.",
             {"path": S, "region": {"type": "array", "items": I, "description": "[left, top, width, height]"}})
    def screenshot(path: str = "", region: list | None = None):
        from PIL import Image
        p = policy.check_write(path or f"screenshots/shot_{time.strftime('%Y%m%d_%H%M%S')}.png")
        p.parent.mkdir(parents=True, exist_ok=True)
        capture_screen(p)
        with Image.open(p) as im:
            full = im.size
            img = im.crop((region[0], region[1], region[0] + region[2], region[1] + region[3])) if region else im.copy()
        if region:
            img.save(p)
        shot.update(size=full, left=region[0] if region else 0, top=region[1] if region else 0,
                    scale=max(img.size) / VIEW_MAX if max(img.size) > VIEW_MAX else 1.0)
        vw, vh = round(img.width / shot["scale"]), round(img.height / shot["scale"])
        return (f"Saved screenshot to {p} (screen {full[0]}x{full[1]}; you see it as {vw}x{vh})"
                + reg.attach_image(p, "screenshot"))

    # ---------------------------------------------------------------- AT-SPI window / app control
    if atspi_available():
        @reg.add("list_windows", "List visible top-level windows with title, position and size "
                                 "(apps that expose accessibility).", {})
        def list_windows():
            A = _atspi()
            rows = []
            for w in top_windows():
                if (not w["showing"] and not w["active"]) or (not w["title"] and not w["active"]):
                    continue          # hidden windows and untitled helper popups
                ext = _safe(lambda: w["obj"].get_extents(A.CoordType.SCREEN))
                geo = f" at ({ext.x},{ext.y}) {ext.width}x{ext.height}" if ext and ext.width > 0 else ""
                rows.append(f"{(w['title'] or '(untitled)')!r} [{w['app']}]{geo}{' [active]' if w['active'] else ''}")
            return "\n".join(rows) or "No accessible windows found."

        @reg.add("focus_window", "Bring a window to the front by (partial) title (not every Wayland compositor "
                                "allows this).", {"title": S}, ["title"])
        def focus_window(title: str):
            w = find_window(title)
            policy.require("desktop", f"Focus window {w['title']!r}", sensitive=is_sensitive_window(w["title"]))
            A = _atspi()
            _safe(lambda: A.Component.grab_focus(w["obj"]))
            time.sleep(0.3)
            now = next((x for x in top_windows() if x["title"] == w["title"] and x["app"] == w["app"]), None)
            return (f"Focused {w['title']!r}" if now and now["active"]
                    else f"Asked the desktop to focus {w['title']!r}; it did not confirm (Wayland may refuse "
                         "focus changes). Click the window or use app_* tools that need no focus.")

        @reg.add("app_inspect",
                 "Read the controls of an app window via accessibility (AT-SPI). Shows role, name, id. "
                 "Use before app_click.",
                 {"window": S, "filter": S, "max_items": I}, ["window"])
        def app_inspect(window: str, filter: str = "", max_items: int = 150):  # noqa: A002
            win = find_window(window)
            f, rows = filter.lower(), []
            for e in walk(win["obj"]):
                role, name, eid = _info(e)
                if not (name or eid) or role in ("panel", "filler", "section") and not name:
                    continue
                line = f"{role:<14} name={name[:60]!r}" + (f" id={eid!r}" if eid else "")
                if f and f not in line.lower():
                    continue
                rows.append(line)
                if len(rows) >= max_items:
                    rows.append("... (more; use filter)")
                    break
            return f"Window: {win['title']!r} [{win['app']}]\n" + "\n".join(rows)

        @reg.add("app_read", "Read the text/value of an app control (by name / control_type / automation_id).",
                 {"window": S, "name": S, "control_type": S, "automation_id": S, "index": I}, ["window"])
        def app_read(window: str, name: str = "", control_type: str = "", automation_id: str = "", index: int = 0):
            win = find_window(window)
            if not (name or control_type or automation_id):
                bits = [control_text(e) or _info(e)[1] for e in walk(win["obj"])
                        if _info(e)[0] in ("label", "text", "static", "heading", "paragraph", "entry")]
                return "\n".join(b for b in bits if b)[:4000]
            e, total = find_control(win, name, control_type, automation_id, index)
            role, nm, _ = _info(e)
            return f"{role} {nm!r}: {control_text(e) or nm}  ({total} match(es))"

        @reg.add("app_click",
                 "Press/toggle/select an app control via accessibility (no mouse; usually works in the background). "
                 "Asks the user first.",
                 {"window": S, "name": S, "control_type": S, "automation_id": S, "index": I}, ["window"])
        def app_click(window: str, name: str = "", control_type: str = "", automation_id: str = "", index: int = 0):
            win = find_window(window)
            e, _ = find_control(win, name, control_type, automation_id, index)
            role, nm, _ = _info(e)
            label = f"{role} {nm!r} in {win['title']!r}"
            policy.require("desktop", f"Click {label}", sensitive=is_sensitive_window(win["title"]))
            A = _atspi()
            n = _safe(lambda: A.Action.get_n_actions(e), 0)
            names = [_safe(lambda i=i: A.Action.get_action_name(e, i), "") for i in range(n)]
            for want in ("click", "press", "activate", "toggle", "select", "expand or contract", "open"):
                for i, an in enumerate(names):
                    if (an or "").lower() == want and _safe(lambda i=i: A.Action.do_action(e, i), False):
                        return f"Clicked {label} via {an}"
            if n and _safe(lambda: A.Action.do_action(e, 0), False):
                return f"Clicked {label} via {names[0]}"
            raise RuntimeError(f"{label} has no clickable action. Try mouse_click with a screenshot.")

        @reg.add("app_set_text",
                 "Set the text of an input/edit control via accessibility (no typing; usually works in the "
                 "background). Asks the user first.",
                 {"window": S, "text": S, "name": S, "control_type": S, "automation_id": S, "index": I},
                 ["window", "text"])
        def app_set_text(window: str, text: str, name: str = "", control_type: str = "", automation_id: str = "",
                         index: int = 0):
            win = find_window(window)
            e, _ = find_control(win, name, control_type or ("" if name or automation_id else "text"),
                                automation_id, index)
            role, nm, _ = _info(e)
            label = f"{role} {nm!r} in {win['title']!r}"
            policy.require("desktop", f"Set text of {label} to {text[:150]!r}",
                           sensitive=is_sensitive_window(win["title"]))
            if not _safe(lambda: _atspi().EditableText.set_text_contents(e, text), False):
                raise RuntimeError(f"{label} is not an editable text control (try app_click then type_text).")
            return f"Set text of {label}"

        @reg.add("app_close", "Close an app window politely (like clicking X). Asks the user first.",
                 {"window": S}, ["window"])
        def app_close(window: str):
            win = find_window(window)
            policy.require("desktop", f"Close window {win['title']!r}", sensitive=is_sensitive_window(win["title"]))
            A = _atspi()
            obj = win["obj"]
            n = _safe(lambda: A.Action.get_n_actions(obj), 0)
            for i in range(n):
                if (_safe(lambda i=i: A.Action.get_action_name(obj, i), "") or "").lower() == "close":
                    if _safe(lambda i=i: A.Action.do_action(obj, i), False):
                        return f"Closed {win['title']!r}"
            if uinput_ok():
                _safe(lambda: A.Component.grab_focus(obj))
                time.sleep(0.3)
                get_uinput().combo([KEYS["alt"], KEYS["f4"]])
                return f"Sent Alt+F4 to {win['title']!r} (it may ask to save first)"
            raise RuntimeError("This window offers no close action and keyboard input is unavailable.")

    # ---------------------------------------------------------------- keyboard / mouse (uinput)
    state: dict = {}

    def uinput_ok() -> bool:
        return os.access("/dev/uinput", os.W_OK)

    def get_uinput() -> UInput:
        if "ui" not in state:
            state["ui"] = UInput()
        return state["ui"]

    def screen_size() -> tuple[int, int]:
        if shot["size"]:
            return shot["size"]
        if shutil.which("xrandr"):
            m = re.search(r"current (\d+) x (\d+)", subprocess.run(["xrandr", "--current"], capture_output=True,
                                                                   text=True).stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
        raise RuntimeError("Screen size unknown: call screenshot first, then mouse_click with from_screenshot=true.")

    if uinput_ok():
        @reg.add("mouse_click",
                 "Click at screen coordinates. Set from_screenshot=true when x,y come from the last screenshot image. "
                 "Prefer app_click (no mouse needed) when the target is a normal app control. Asks the user first. "
                 "Uses a virtual pointer; on multi-monitor setups the position may be off: check with a screenshot.",
                 {"x": I, "y": I, "button": S, "double": B, "from_screenshot": B}, ["x", "y"])
        def mouse_click(x: int, y: int, button: str = "left", double: bool = False, from_screenshot: bool = False):
            if from_screenshot:
                x, y = round(shot["left"] + x * shot["scale"]), round(shot["top"] + y * shot["scale"])
            w, h = screen_size()
            policy.require("desktop", f"{'Double-' if double else ''}{button}-click at screen ({x},{y})",
                           sensitive=True)        # what is under the pointer is unknown on Wayland, so always ask
            ui = get_uinput()
            ui.move(x, y, w, h)
            time.sleep(0.15)
            ui.click(button, 2 if double else 1)
            return f"Clicked ({x},{y})"

        @reg.add("type_text", "Type text into the focused window. Asks the user first.",
                 {"text": S, "press_enter": B}, ["text"])
        def type_text(text: str, press_enter: bool = False):
            layout = keyboard_layout()
            if layout and layout not in US_LIKE_LAYOUTS:
                raise RuntimeError(f"type_text sends US-layout key codes, but your layout is {layout!r}, so the text "
                                   "would come out wrong. Use app_set_text instead.")
            active = active_window_title()
            policy.require("desktop", f"Type into {active or 'the focused window'!r}: {text[:200]!r}"
                                      f"{' + Enter' if press_enter else ''}",
                           sensitive=is_sensitive_window(active) or not active)
            ui = get_uinput()
            for ch in text:
                if ch == "\n":
                    ui.combo([KEYS["enter"]], pause=0.004)
                else:
                    ui.type_char(ch)
            if press_enter:
                ui.combo([KEYS["enter"]])
            return "Typed."

        @reg.add("hotkey", "Press a key combination, e.g. ['ctrl','s']. Asks the user first.",
                 {"keys": {"type": "array", "items": S}}, ["keys"])
        def hotkey(keys: list):
            names = [k.lower() for k in keys]
            unknown = [k for k in names if k not in KEYS]
            if unknown:
                raise RuntimeError(f"Unknown key(s): {', '.join(unknown)}")
            active = active_window_title()
            combo = "+".join(names)
            policy.require("desktop", f"Press {combo} in {active or 'the focused window'!r}",
                           sensitive=is_sensitive_window(active) or not active or combo in RISKY_HOTKEYS)
            get_uinput().combo([KEYS[k] for k in names])
            return f"Pressed {'+'.join(keys)}"

        if atspi_available():
            @reg.add("app_keys",
                     "Send keystrokes to an app window (brings it to the front). Syntax: '^s' = Ctrl+S, "
                     "'{ENTER}', '%f' = Alt+F. Asks the user first.",
                     {"window": S, "keys": S}, ["window", "keys"])
            def app_keys(window: str, keys: str):
                win = find_window(window)
                chords = parse_keys(keys)
                policy.require("desktop", f"Send keys {keys!r} to {win['title']!r}",
                               sensitive=is_sensitive_window(win["title"]))
                _safe(lambda: _atspi().Component.grab_focus(win["obj"]))
                time.sleep(0.3)
                ui = get_uinput()
                for chord in chords:
                    ui.combo(chord, pause=0.01)
                return f"Sent {keys!r}"
