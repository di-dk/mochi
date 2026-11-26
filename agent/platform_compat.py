"""Platform helpers: Windows keeps its original behavior, Linux gets equivalents.

Anything here is only used when the original Windows-only call would not work. Tools that cannot be ported
(Windows UI Automation, Task Scheduler, mouse/keyboard control under Wayland) are simply not offered on Linux.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
OS_NAME = "Windows PC" if IS_WINDOWS else "Linux PC"

# The Windows implementations of these tools (UI Automation, Win32 windows, Task Scheduler, Start-menu apps).
# On Linux they are replaced by agent/tools_linux.py, which registers only what works on this machine.
WINDOWS_ONLY_TOOLS = {
    "list_windows", "screenshot", "focus_window", "mouse_click", "type_text", "hotkey",
    "list_apps", "launch_app",
    "app_inspect", "app_read", "app_click", "app_set_text", "app_keys", "app_close",
    "schedule_task", "list_scheduled_tasks", "delete_scheduled_task",
}


def drop_unsupported_tools(reg) -> None:
    """Remove the Windows-only implementations so the model is never offered something that cannot run."""
    if IS_WINDOWS:
        return
    for name in WINDOWS_ONLY_TOOLS:
        reg.tools.pop(name, None)


def _first(*cmds: str) -> str | None:
    return next((c for c in cmds if shutil.which(c)), None)


def clipboard_read() -> str:
    if IS_WINDOWS:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return r.stdout
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"]):
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return r.stdout
    raise RuntimeError("No clipboard tool found. Install wl-clipboard (Wayland) or xclip (X11).")


def clipboard_write(text: str) -> None:
    if IS_WINDOWS:
        subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], input=text,
                       text=True, encoding="utf-8")
        return
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text, text=True, encoding="utf-8")
            return
    raise RuntimeError("No clipboard tool found. Install wl-clipboard (Wayland) or xclip (X11).")


def notify(title: str, message: str) -> None:
    if IS_WINDOWS:
        from win11toast import notify as toast
        toast(title[:80], message[:300], app_id="Mochi")
        return
    if not shutil.which("notify-send"):
        raise RuntimeError("notify-send not found. Install libnotify-bin (Debian/Ubuntu) or libnotify.")
    subprocess.run(["notify-send", "--app-name=Mochi", "--", title[:80], message[:300]], check=False)


def open_default(target: str) -> None:
    if IS_WINDOWS:
        os.startfile(target)  # noqa: S606
        return
    opener = _first("xdg-open", "gio")
    if not opener:
        raise RuntimeError("xdg-open not found (install xdg-utils).")
    cmd = [opener, target] if opener == "xdg-open" else ["gio", "open", target]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


LANG_CODE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})?$")


def speak(text: str, language: str = "") -> tuple[bool, str]:
    """Say text aloud, with a voice for `language` (ISO code like nl, fr, ja) when one is installed.
    Returns (ok, error message)."""
    language = language.strip()
    if language and not LANG_CODE.match(language):
        return False, f"{language!r} is not a language code (use e.g. nl, fr, de, es, ja)"
    language = language.replace("_", "-")
    if IS_WINDOWS:
        pick = (f"try {{ $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet, "
                f"[System.Speech.Synthesis.VoiceAge]::NotSet, 0, [System.Globalization.CultureInfo]::GetCultureInfo('{language}')) }} "
                "catch {}; ") if language else ""
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  + pick + "$s.Speak([Console]::In.ReadToEnd())")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], input=text, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180)
        return r.returncode == 0, r.stderr.strip()[:200]
    if shutil.which("spd-say"):
        r = subprocess.run(["spd-say", "--wait"] + (["-l", language.split("-")[0]] if language else []) + ["--", text],
                           capture_output=True, text=True, timeout=180)
    elif shutil.which("espeak-ng"):
        r = subprocess.run(["espeak-ng", "--stdin"] + (["-v", language] if language else []), input=text,
                           capture_output=True, text=True, timeout=180)
    else:
        return False, "No text-to-speech found. Install speech-dispatcher (spd-say) or espeak-ng."
    return r.returncode == 0, r.stderr.strip()[:200]


def shell_argv(command: str) -> list[str]:
    """argv that runs one shell command: PowerShell on Windows, bash (or sh) on Linux."""
    if IS_WINDOWS:
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
    return [shutil.which("bash") or "/bin/sh", "-c", command]
