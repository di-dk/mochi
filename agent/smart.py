"""Speed and focus helpers: tool groups (send the model fewer tools), skill auto-matching, context condensing."""
from __future__ import annotations

import re

# Tools that are always sent. Everything else belongs to a group that is loaded when the task needs it.
CORE = {  # documentation of the always-on set; anything without a group is always sent
    "list_dir", "read_file", "write_file", "edit_file", "copy_path", "delete_path", "find_files", "search_files",
    "web_search", "fetch_url", "download_file", "set_plan", "update_plan", "find_skills", "read_skill",
    "save_skill", "save_lesson", "remember", "recall", "wait", "use_tools",
}
GROUPS: dict[str, set[str]] = {
    "code": {"run_powershell", "run_python"},
    "browser": {"browser_open", "browser_read", "browser_click", "browser_fill", "browser_screenshot",
                "browser_close", "http_request"},
    "desktop": {"list_windows", "screenshot", "focus_window", "mouse_click", "type_text", "hotkey", "list_apps",
                "launch_app", "open_with_default_app", "app_inspect", "app_read", "app_click", "app_set_text",
                "app_keys", "app_close", "clipboard_get", "clipboard_set"},
    "docs": {"create_pdf", "inspect_pdf", "create_docx", "read_document", "read_spreadsheet", "create_spreadsheet"},
    "media": {"comfy_status", "comfy_list_models", "comfy_txt2img", "comfy_run_workflow", "image_edit",
              "view_image", "media_convert", "media_info", "make_video", "list_my_videos"},
    "system": {"schedule_task", "list_scheduled_tasks", "delete_scheduled_task", "system_info", "list_processes",
               "kill_process", "notify", "zip_files", "unzip"},
}
GROUP_HELP = {
    "code": "run PowerShell commands and Python code",
    "browser": "her own headless browser (open, read, click, fill, screenshot) and raw HTTP/API requests",
    "desktop": "Windows apps and windows: launch, inspect, click, type, hotkeys, screenshots, clipboard",
    "docs": "create and read PDF, Word and Excel/CSV files",
    "media": "ComfyUI images, image editing, viewing images, ffmpeg audio/video, make_video",
    "system": "scheduled tasks, notifications, processes, system info, zip/unzip",
}
# Words in a request that load a group straight away (whole words, lower case).
KEYWORDS: dict[str, set[str]] = {
    "code": {"python", "script", "powershell", "command", "code", "pytest", "test", "tests", "debug", "bug", "git",
             "gh", "github", "pip", "compile", "calculate", "regex", "function", "program"},
    "browser": {"browser", "website", "site", "webpage", "login", "form", "api", "endpoint", "http", "https",
                "reddit", "youtube", "map", "route", "directions", "stock", "stocks", "ticker", "crypto", "rss",
                "feed", "arxiv", "scrape"},
    "desktop": {"app", "apps", "window", "windows", "launch", "notepad", "calculator", "clipboard", "desktop",
                "screenshot", "paste", "explorer", "program", "paint", "keyboard", "mouse"},
    "docs": {"pdf", "word", "docx", "excel", "xlsx", "spreadsheet", "csv", "report", "document", "documents",
             "sheet", "table", "invoice", "minutes"},
    "media": {"image", "images", "picture", "pictures", "photo", "draw", "drawing", "art", "banner", "logo",
              "video", "videos", "audio", "gif", "mp3", "mp4", "comfy", "comfyui", "meme", "convert", "resize",
              "crop", "thumbnail", "wallpaper", "quiz", "short", "shorts"},
    "system": {"schedule", "scheduled", "every", "daily", "weekly", "hourly", "remind", "reminder", "monitor",
               "watch", "alert", "notify", "process", "processes", "cpu", "ram", "disk", "gpu", "zip", "unzip",
               "battery"},
}
STOP = set("""a an and are as at be but by can could do does for from get give go has have help how i if in into is it
its just let like make me my need of on one or our out please put she should show so some tell that the their them
then there these this to up us use want was we what when where which who will with would you your about all also
any been did had her him his more most new no not now only other over same than too very via using based""".split())

_WORD = re.compile(r"[a-z0-9]+")


def group_of(tool: str) -> str | None:
    """Group name of a tool; None for core tools and tools this module does not know (those are always sent)."""
    for g, names in GROUPS.items():
        if tool in names:
            return g
    return None


def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def words(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in STOP and len(w) > 1}


def groups_for_text(text: str) -> set[str]:
    """Groups whose trigger words appear in the text."""
    found = set(_WORD.findall(text.lower()))
    return {g for g, kws in KEYWORDS.items() if found & kws}


def groups_for_tools(text: str, known: set[str]) -> set[str]:
    """Groups of every known tool name mentioned in a piece of text (e.g. a skill recipe)."""
    mentioned = set(re.findall(r"[a-z_]+", text)) & known
    return {g for g in (group_of(t) for t in mentioned) if g}


def match_skill(text: str, skills: list[dict]) -> dict | None:
    """Best skill for a request, or None. Scores overlap of meaningful words with the skill name + description;
    a word from the name counts double. Needs a clear lead so a vague request matches nothing."""
    req = words(text)
    if len(req) < 2:
        return None
    scored = []
    for s in skills:
        name_w = words(s["name"].replace("-", " "))
        desc_w = words(s["description"])
        score = 2 * len(req & name_w) + len(req & (desc_w - name_w))
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < 3:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 1:
        return None                      # two skills fit equally well: let the model choose
    return scored[0][1]


CONDENSE_PROMPT = """Task the assistant is working on:
{task}

Below is the output of the tool `{tool}`. Rewrite it as compact notes for that task, at most {words} words.
Keep exactly: numbers, dates, names, URLs, file paths, error messages and any sentence worth quoting.
Drop navigation, ads, boilerplate and anything unrelated to the task. Plain text, no preamble.

{content}"""


def condense(client, model: str, task: str, tool: str, content: str, max_words: int = 250) -> str | None:
    """Ask a model to shorten a long tool result. Returns None if the call fails or does not actually shorten."""
    try:
        r = client.chat.completions.create(
            model=model, temperature=0.1,
            messages=[{"role": "user", "content": CONDENSE_PROMPT.format(task=task[:1500], tool=tool,
                                                                         words=max_words, content=content)}])
        out = (r.choices[0].message.content or "").strip()
    except Exception:  # noqa: BLE001 - condensing is best effort; the caller falls back to plain trimming
        return None
    if not out or len(out) > len(content) * 0.7:
        return None
    return f"[condensed from {len(content)} chars; call the tool again if you need the exact text]\n{out}"
