"""Video tools: one call turns a short script into a finished, voiced short (2D, 3D or quiz).

The heavy lifting (voice, drawing, Blender, mixing, filing) is done by an external "studio" command configured in
config.local.yaml -> video.command, e.g. ["C:/.../python.exe", "C:/.../mochi-studio/studio.py"]. The studio takes a
JSON script path, prints progress, and ends with one line:  RESULT {"ok": true, "video": ..., ...}
Mochi only writes the script (the creative part) and calls make_video once.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from .policy import Policy
from .registry import Registry

S = {"type": "string"}
I = {"type": "integer"}

SCENE = {"type": "object", "properties": {
    "say": {"type": "string", "description": "What the voice says (one or two short sentences, max 40 words)."},
    "text": {"type": "string", "description": "Short on-screen text (3-8 words). Wrap 1-3 key words in *stars* to highlight."},
    "emoji": {"type": "string", "description": "Optional single emoji shown above the text (2D only)."},
    "label": {"type": "string", "description": "Optional tiny caps label, e.g. 'FACT 1'."}},
    "required": ["say"]}
QUESTION = {"type": "object", "properties": {
    "q": S, "options": {"type": "array", "items": S, "description": "2 to 4 short options"},
    "answer": {"type": "string", "description": "The correct option, written exactly as in options"},
    "why": {"type": "string", "description": "One short reason shown with the answer"}},
    "required": ["q", "options", "answer"]}


def _run(cmd: list[str], timeout: int) -> tuple[dict | None, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    m = re.findall(r"^RESULT (\{.*\})\s*$", r.stdout or "", re.M)
    return (json.loads(m[-1]) if m else None), out


def add_video_tools(reg: Registry, policy: Policy, cfg: dict) -> None:
    vc = cfg.get("video") or {}
    command = [str(c) for c in (vc.get("command") or [])]
    if not command:
        return                                   # not configured on this PC: don't offer the tools
    timeout = int(vc.get("timeout_s", 1800))
    scripts = policy.workspace / "video_scripts"

    @reg.add("make_video",
             "Make a finished vertical short video WITH voice-over in ONE call: writes, voices, renders, mixes and files "
             "it in an organized folder. style: '2d' (animated cards + emoji), '3d' (cinematic Blender background) or "
             "'quiz' (questions with options, countdown and answer reveal). Give 4-8 scenes (first = the hook) or 1-5 "
             "questions. Timing is automatic from the voice. Takes about 1 minute (first use of a 3D look: longer). "
             "Read the make-video skill first if unsure.",
             {"title": S,
              "style": {"type": "string", "enum": ["2d", "3d", "quiz"]},
              "scenes": {"type": "array", "items": SCENE,
                         "description": "Spoken lines in order. For a quiz, give one hook scene only."},
              "questions": {"type": "array", "items": QUESTION, "description": "Quiz only."},
              "end": {"type": "string", "description": "Comment-bait question for the end card."},
              "look": {"type": "string", "description": "Optional. 3d: orbs | planet | cubes | crystal. "
                                                        "2d: midnight ocean forest ember grape steel rose teal navy charcoal plum olive."},
              "caption": {"type": "string", "description": "Optional post caption."},
              "hashtags": {"type": "array", "items": S}},
             ["title", "style"])
    def make_video(title: str, style: str, scenes: list | None = None, questions: list | None = None,
                   end: str = "", look: str = "", caption: str = "", hashtags: list | None = None):
        spec = {"title": title, "style": style, "scenes": scenes or [], "questions": questions or [], "end": end,
                "look": look, "caption": caption, "hashtags": hashtags or []}
        scripts.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or "video"
        path = scripts / f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}.json"
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        # cheap validation first, so a bad script costs seconds, not a render
        res, out = _run(command + ["--check", str(path)], 60)
        if not res or not res.get("ok"):
            return "ERROR: " + ((res or {}).get("error") or out[-800:])
        policy.require("video", f"Make {style} video '{title}' ({len(spec['scenes'])} scenes, "
                                f"{len(spec['questions'])} questions)")
        t0 = time.time()
        try:
            res, out = _run(command + [str(path)], timeout)
        except subprocess.TimeoutExpired:
            return f"ERROR: the studio took longer than {timeout}s. Tell the user; do not retry automatically."
        if not res or not res.get("ok"):
            return "ERROR: " + ((res or {}).get("error") or out[-800:])
        thumb = Path(res["folder"]) / "thumb.jpg"
        msg = (f"DONE. Video: {res['video']}\nLength {res['seconds']} s, style {res['style']}"
               f"{' / ' + res['look'] if res.get('look') else ''}, made in {round(time.time() - t0)} s.\n"
               f"Folder (video, script.json, caption.txt, thumb.jpg): {res['folder']}")
        if res.get("note"):
            msg += f"\nNote: {res['note']}"
        if thumb.exists():
            msg += reg.attach_image(thumb, "thumbnail of the new video")
        return msg + "\nThe video is finished. Tell the user where it is; don't render it again."

    @reg.add("list_my_videos",
             "List the videos you made with make_video (newest last): date, style, length, title, path. Use this "
             "instead of listing folders.", {"count": I})
    def list_my_videos(count: int = 15):
        _, out = _run(command + ["--list", str(max(1, min(int(count), 100)))], 60)
        return out.strip() or "No videos yet."
