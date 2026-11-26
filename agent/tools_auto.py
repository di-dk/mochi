"""Everyday automation tools: documents, spreadsheets, images, media, archives, system, clipboard, notifications, HTTP."""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import httpx

from . import platform_compat as pc
from .policy import Denied, Policy
from .registry import Registry

S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}
N = {"type": "number"}


def add_auto_tools(reg: Registry, policy: Policy, cfg: dict) -> None:
    ws = policy.workspace

    def out_path(path: str, ext: str) -> Path:
        p = policy.check_write(path if path.lower().endswith(ext) else path + ext)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # ------------------------------------------------------------------ documents
    @reg.add("create_docx",
             "Create a Word document from Markdown-style text (# headings, - bullets, 1. lists, **bold**, *italic*, "
             "| tables |, ![](image.png)).", {"path": S, "markdown": S, "title": S}, ["path", "markdown"])
    def create_docx(path: str, markdown: str, title: str = ""):
        from docx import Document
        from docx.oxml import OxmlElement

        from . import fonts
        from docx.shared import Inches
        p = out_path(path, ".docx")
        doc = Document()
        first = next((l for l in markdown.splitlines() if l.strip()), "")
        if title and title.strip().lower() != re.sub(r"^#+\s*", "", first).strip().lower():
            doc.add_heading(title, 0)

        def runs(par, text):
            for part in re.split(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)", text):
                if part.startswith("**") and part.endswith("**"):
                    par.add_run(part[2:-2]).bold = True
                elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                    par.add_run(part[1:-1]).italic = True
                elif part.startswith("`") and part.endswith("`"):
                    par.add_run(part[1:-1]).font.name = "Consolas"
                elif part:
                    par.add_run(part)

        lines = markdown.replace("\r\n", "\n").split("\n")
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if m := re.match(r"^(#{1,4})\s+(.*)", s):
                doc.add_heading(m.group(2), len(m.group(1)))
            elif m := re.match(r"^!\[.*?\]\((.+?)\)", s):
                img = policy.check_read(m.group(1))
                if img.exists():
                    doc.add_picture(str(img), width=Inches(6))
            elif s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
                rows = [[c.strip() for c in s.strip("|").split("|")]]
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
                i -= 1
                t = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
                t.style = "Table Grid"
                for r, row in enumerate(rows):
                    for c, val in enumerate(row):
                        t.cell(r, c).text = val
                        if r == 0:
                            for run in t.cell(r, c).paragraphs[0].runs:
                                run.bold = True
            elif m := re.match(r"^\s*[-*+]\s+(.*)", lines[i]):
                runs(doc.add_paragraph(style="List Bullet"), m.group(1))
            elif m := re.match(r"^\s*\d+[.)]\s+(.*)", lines[i]):
                runs(doc.add_paragraph(style="List Number"), m.group(1))
            elif s:
                runs(doc.add_paragraph(), s)
            i += 1

        def mark_rtl(par):                       # Arabic / Hebrew paragraphs read right to left in Word
            if not fonts.is_rtl(par.text):
                return
            par._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
            for r in par.runs:
                r._r.get_or_add_rPr().append(OxmlElement("w:rtl"))
        for par in doc.paragraphs:
            mark_rtl(par)
        for tbl in doc.tables:
            for row in tbl.rows:
                for cell in row.cells:
                    for par in cell.paragraphs:
                        mark_rtl(par)
        doc.save(p)
        return f"Created {p} ({p.stat().st_size} bytes)"

    @reg.add("read_document", "Read the text of a .docx Word document.", {"path": S, "max_chars": I}, ["path"])
    def read_document(path: str, max_chars: int = 8000):
        from docx import Document
        d = Document(str(policy.check_read(path)))
        text = "\n".join(par.text for par in d.paragraphs)
        for t in d.tables:
            text += "\n" + "\n".join(" | ".join(c.text for c in row.cells) for row in t.rows)
        return text[:max_chars]

    # ------------------------------------------------------------------ spreadsheets
    @reg.add("read_spreadsheet", "Read a .xlsx or .csv file as rows (first sheet unless sheet is given).",
             {"path": S, "sheet": S, "max_rows": I}, ["path"])
    def read_spreadsheet(path: str, sheet: str = "", max_rows: int = 200):
        p = policy.check_read(path)
        if p.suffix.lower() == ".csv":
            with p.open(encoding="utf-8-sig", errors="replace", newline="") as f:
                rows = [r for _, r in zip(range(max_rows), csv.reader(f))]
            return "\n".join(" | ".join(r) for r in rows)
        from openpyxl import load_workbook
        wb = load_workbook(p, read_only=True, data_only=True)
        sh = wb[sheet] if sheet else wb.worksheets[0]
        rows = []
        for r, row in enumerate(sh.iter_rows(values_only=True)):
            if r >= max_rows:
                rows.append("..."); break
            rows.append(" | ".join("" if v is None else str(v) for v in row))
        return f"Sheets: {', '.join(wb.sheetnames)} — showing {sh.title}\n" + "\n".join(rows)

    @reg.add("create_spreadsheet",
             "Create an .xlsx (or .csv) from rows. First row = header (bold). Values starting with '=' are formulas.",
             {"path": S, "rows": {"type": "array", "items": {"type": "array", "items": {}}}, "sheet": S},
             ["path", "rows"])
    def create_spreadsheet(path: str, rows: list, sheet: str = "Sheet1"):
        if path.lower().endswith(".csv"):
            p = out_path(path, ".csv")
            with p.open("w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(rows)
            return f"Created {p} ({len(rows)} rows)"
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
        p = out_path(path, ".xlsx")
        wb = Workbook()
        sh = wb.active
        sh.title = sheet[:31]
        for row in rows:
            sh.append(row)
        for c in sh[1]:
            c.font = Font(bold=True)
        for col in range(1, sh.max_column + 1):
            width = max(len(str(sh.cell(r, col).value or "")) for r in range(1, min(sh.max_row, 200) + 1))
            sh.column_dimensions[get_column_letter(col)].width = min(max(10, width + 2), 60)
        sh.freeze_panes = "A2"
        wb.save(p)
        return f"Created {p} ({len(rows)} rows)"

    # ------------------------------------------------------------------ images
    @reg.add("image_edit",
             "Edit a photo or image and save the result (the original is never changed). Operations are applied in "
             "this order: auto-orient (phone photos), crop [left,top,right,bottom], rotate degrees (clockwise), flip "
             "('horizontal'|'vertical'), resize (width/height, keeps aspect if one is 0), then looks: brightness / "
             "contrast / saturation / sharpness (1.0 = unchanged, 1.3 = 30% more), blur (radius), grayscale, sepia, "
             "invert, auto_contrast. Output format follows the extension (png/jpg/webp/gif/bmp/ico). "
             "The edited picture is shown in the chat automatically.",
             {"path": S, "output": S, "width": I, "height": I, "crop": {"type": "array", "items": I},
              "rotate": N, "flip": S, "brightness": N, "contrast": N, "saturation": N, "sharpness": N, "blur": N,
              "grayscale": B, "sepia": B, "invert": B, "auto_contrast": B, "quality": I}, ["path", "output"])
    def image_edit(path: str, output: str, width: int = 0, height: int = 0, crop: list | None = None,
                   rotate: float = 0, flip: str = "", brightness: float = 1.0, contrast: float = 1.0,
                   saturation: float = 1.0, sharpness: float = 1.0, blur: float = 0, grayscale: bool = False,
                   sepia: bool = False, invert: bool = False, auto_contrast: bool = False, quality: int = 90):
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        src, dst = policy.check_read(path), policy.check_write(output)
        if src.resolve() == dst.resolve():
            raise Denied("Output must be a different file than the input; the original is never overwritten.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im0:
            im = ImageOps.exif_transpose(im0) or im0
            if crop:
                im = im.crop(tuple(crop))
            if rotate:
                im = im.rotate(-rotate, expand=True)
            if flip.lower().startswith("h"):
                im = ImageOps.mirror(im)
            elif flip.lower().startswith("v"):
                im = ImageOps.flip(im)
            if width or height:
                w = width or round(im.width * height / im.height)
                h = height or round(im.height * width / im.width)
                im = im.resize((w, h), Image.LANCZOS)
            rgba = im.mode in ("RGBA", "LA", "P")
            alpha = im.convert("RGBA").getchannel("A") if rgba else None
            if rgba or im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if auto_contrast:
                im = ImageOps.autocontrast(im)
            for factor, enhancer in ((brightness, ImageEnhance.Brightness), (contrast, ImageEnhance.Contrast),
                                     (saturation, ImageEnhance.Color), (sharpness, ImageEnhance.Sharpness)):
                if factor != 1.0 and im.mode == "RGB":
                    im = enhancer(im).enhance(float(factor))
            if blur:
                im = im.filter(ImageFilter.GaussianBlur(float(blur)))
            if invert and im.mode in ("RGB", "L"):
                im = ImageOps.invert(im)
            if sepia:
                g = ImageOps.grayscale(im)
                im = ImageOps.colorize(g, black="#2b1a0a", white="#ffe9c4", mid="#a67c52")
            if grayscale:
                im = im.convert("L")
            if alpha is not None and dst.suffix.lower() in (".png", ".webp", ".gif", ".ico") and im.mode in ("RGB", "L"):
                im = im.convert("RGBA")
                im.putalpha(alpha)
            if dst.suffix.lower() in (".jpg", ".jpeg") and im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            kw = {"quality": quality} if dst.suffix.lower() in (".jpg", ".jpeg", ".webp") else {}
            im.save(dst, **kw)
            size = f"{im.width}x{im.height}"
        return f"Saved {dst} ({size})" + reg.attach_image(dst, dst.name)

    # ------------------------------------------------------------------ pictures of herself
    @reg.add("draw_myself",
             "Draw or edit a picture of YOURSELF (Mochi) so that it really looks like you. ALWAYS use this when asked "
             "to draw, show, imagine or change yourself; never comfy_txt2img (it does not know your face). scene: what "
             "should change or happen: the outfit, place or activity the USER asked for, in your own short words. "
             "closeup=true makes a face close-up (set expression: relaxed|happy|excited|thinking|working|asking|"
             "worried|sad|sleepy). Saves into comfy/ and shows it in the chat.",
             {"scene": S, "closeup": B, "expression": S, "seed": I}, ["scene"])
    def draw_myself(scene: str, closeup: bool = False, expression: str = "", seed: int = -1):
        import random as _r
        from PIL import Image
        from .identity import LOCK, MOODS as _MOODS, TAGS
        root = Path(__file__).resolve().parent.parent
        mood = {"relaxed": "neutral"}.get(expression.lower(), expression.lower())
        if closeup:
            src = root / "assets" / "expressions" / f"{mood if mood in _MOODS else 'neutral'}.webp"
        else:
            src = root / "assets" / "mochi.png"
        if src.suffix.lower() == ".webp":                       # ComfyUI wants a png
            scratch = ws / ".scratch"
            scratch.mkdir(exist_ok=True)
            png = scratch / f"self_{src.stem}.png"
            Image.open(src).convert("RGB").save(png)
            src = png
        prompt = f"{scene.strip().rstrip('.')}. {LOCK}" + (" Keep it a close-up of her face." if closeup else "")
        seed = _r.randint(1, 2**31) if seed < 0 else seed
        run = reg.tools["comfy_run_workflow"].fn
        res = run(template="qwen-image-edit", images={"7.image": str(src)},
                  set={"9.prompt": prompt, "12.seed": seed, "14.filename_prefix": "mochi-self"})
        note = ""
        if str(res).startswith("ERROR") or "Outputs:" not in str(res):
            # no edit model: fall back to a normal checkpoint with her tags (looks less like her)
            res = reg.tools["comfy_txt2img"].fn(prompt=f"{TAGS}, {scene}", width=832 if closeup else 832,
                                                height=832 if closeup else 1216, _self=True)
            note = "\n(This is only an approximation: the picture-editing model was not available.)"
        files = re.findall(r"^(/\S+\.(?:png|jpe?g|webp))$", str(res), re.M)
        if not files:
            return str(res)[:600]
        return (f"Drew myself: {scene[:120]} (seed {seed}).{note}\n"
                + reg.tools["share_file"].fn(path=files[0], caption=f"Me: {scene[:100]}"))

    # ------------------------------------------------------------------ sharing files in the chat
    @reg.add("share_file",
             "Show or send a file to the user in the chat. Images and videos appear as a small thumbnail the user can "
             "click to see big; audio plays in the chat; PDFs, documents, archives and any other file get a "
             "download card. Use it when the user asks to see, share, send or give them a file (also after you "
             "make or edit one). A file outside the workspace is copied into workspace/shared first.",
             {"path": S, "caption": S}, ["path"])
    def share_file(path: str, caption: str = ""):
        from . import media
        src = policy.check_read(path)                      # secrets are refused; outside the workspace it asks
        if not src.is_file():
            raise Denied(f"{src} is not a file.")
        dst = src
        if not policy.in_workspace(src):
            dst = policy.check_write(ws / "shared" / src.name)
            n = 1
            while dst.exists():
                dst = ws / "shared" / f"{src.stem}-{n}{src.suffix}"
                n += 1
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        rel = dst.resolve().relative_to(ws.resolve()).as_posix()
        cap = re.sub(r"[\]|\[]", "", caption)[:200]
        return (f"Shared {rel} ({media.kind_of(dst)}, {dst.stat().st_size} bytes) in the chat."
                f"\n[[shared:{rel}|{cap}]]")

    @reg.add("find_my_files",
             "Find files by what they are, a name word and how recent they are, newest first. Use it for requests "
             "to show a picture she made, find the latest video or locate a PDF. kind: image|video|audio|pdf|doc|"
             "archive|any. where: 'mine' (default: her workspace except the user's uploads), 'uploads' (files the "
             "user gave her), 'all' (whole workspace) or a folder path. days: only files changed in the last N "
             "days (0 = any). share=true also shows up to 6 of the results in the chat (thumbnail + path).",
             {"kind": S, "query": S, "where": S, "days": N, "limit": I, "share": B})
    def find_my_files(kind: str = "any", query: str = "", where: str = "mine", days: float = 0, limit: int = 10,
                      share: bool = False):
        from . import media
        kind, limit = (kind or "any").lower(), max(1, min(int(limit or 10), 30))
        if where in ("mine", "uploads", "all", ""):
            base = ws
        else:
            base = policy.check_read(where)
        skip = {".scratch", ".browser-profile", ".cosmic-shot", "__pycache__", ".git", "node_modules", ".venv"}
        cutoff = time.time() - days * 86400 if days else 0
        rows = []
        for f in base.rglob("*"):
            try:
                if not f.is_file() or any(part in skip for part in f.relative_to(base).parts) or policy.is_denied(f):
                    continue
                rel_parts = f.relative_to(ws).parts if policy.in_workspace(f) else ()
                if base == ws and where in ("mine", "") and rel_parts[:1] == ("uploads",):
                    continue
                if where == "uploads" and rel_parts[:1] != ("uploads",):
                    continue
                if kind not in ("any", "") and media.kind_of(f) != kind:
                    continue
                if query and query.lower() not in f.name.lower():
                    continue
                st = f.stat()
                if cutoff and st.st_mtime < cutoff:
                    continue
                rows.append((st.st_mtime, f, st.st_size))
            except (OSError, ValueError):
                continue
        rows.sort(key=lambda r: r[0], reverse=True)
        if not rows:
            return "No matching files."
        lines = [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(m))}  {media.kind_of(f):<7} {s:>10} B  {f}"
                 for m, f, s in rows[:limit]]
        out = f"{len(rows)} match(es), newest first:\n" + "\n".join(lines)
        if share:
            out += "\n" + "\n".join(reg.tools["share_file"].fn(path=str(f)) for _, f, _ in rows[:min(limit, 6)])
        return out

    # ------------------------------------------------------------------ media (ffmpeg)
    @reg.add("media_convert",
             "Convert/trim video or audio with ffmpeg. Output format follows the extension (mp4, webm, gif, mp3, wav…). "
             "Options: start/end in seconds, width (keeps aspect), fps, audio_only, mute.",
             {"input": S, "output": S, "start": N, "end": N, "width": I, "fps": I, "audio_only": B, "mute": B},
             ["input", "output"])
    def media_convert(input: str, output: str, start: float = 0, end: float = 0, width: int = 0,  # noqa: A002
                      fps: int = 0, audio_only: bool = False, mute: bool = False):
        ff = shutil.which("ffmpeg")
        if not ff:
            return "ffmpeg is not installed (winget install Gyan.FFmpeg)."
        src, dst = policy.check_read(input), policy.check_write(output)
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"]
        if start:
            cmd += ["-ss", str(start)]
        cmd += ["-i", str(src)]
        if end:
            cmd += ["-t", str(end - start)]
        vf = []
        if width:
            vf.append(f"scale={width}:-2")
        if fps:
            vf.append(f"fps={fps}")
        if vf and not audio_only:
            cmd += ["-vf", ",".join(vf)]
        if audio_only:
            cmd += ["-vn"]
        if mute:
            cmd += ["-an"]
        cmd.append(str(dst))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode:
            return f"ffmpeg failed: {r.stderr[-1500:]}"
        return f"Created {dst} ({dst.stat().st_size} bytes)"

    @reg.add("media_info", "Show duration, resolution and codecs of a video/audio file (ffprobe).",
             {"path": S}, ["path"])
    def media_info(path: str):
        probe = shutil.which("ffprobe")
        if not probe:
            return "ffprobe is not installed."
        r = subprocess.run([probe, "-v", "error", "-show_entries",
                            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
                            "-of", "json", str(policy.check_read(path))], capture_output=True, text=True)
        return r.stdout or r.stderr

    # ------------------------------------------------------------------ archives
    @reg.add("zip_files", "Zip files/folders into an archive.",
             {"paths": {"type": "array", "items": S}, "output": S}, ["paths", "output"])
    def zip_files(paths: list, output: str):
        dst = out_path(output, ".zip")
        n = 0
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
            for item in paths:
                src = policy.check_read(item)
                files = [src] if src.is_file() else [f for f in src.rglob("*") if f.is_file()]
                for f in files:
                    if policy.is_denied(f):
                        continue
                    z.write(f, f.relative_to(src.parent)); n += 1
        return f"Created {dst} with {n} file(s), {dst.stat().st_size} bytes"

    @reg.add("unzip", "Extract a .zip archive into a folder.", {"path": S, "output_dir": S}, ["path", "output_dir"])
    def unzip(path: str, output_dir: str):
        src, dst = policy.check_read(path), policy.check_write(output_dir)
        dst.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():  # block zip-slip (../ paths escaping the target)
                target = (dst / name).resolve()
                if not target.is_relative_to(dst):
                    raise Denied(f"Archive entry escapes the target folder: {name}")
            z.extractall(dst)
            return f"Extracted {len(z.namelist())} entries to {dst}"

    # ------------------------------------------------------------------ system
    @reg.add("system_info", "CPU, RAM, disks, GPU and battery status of this PC.", {})
    def system_info():
        import psutil
        vm = psutil.virtual_memory()
        lines = [f"CPU: {psutil.cpu_count()} threads, {psutil.cpu_percent(interval=0.5)}% busy",
                 f"RAM: {vm.used / 2**30:.1f} / {vm.total / 2**30:.1f} GB used ({vm.percent}%)"]
        for part in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(part.mountpoint)
                lines.append(f"Disk {part.device} {u.free / 2**30:.0f} GB free of {u.total / 2**30:.0f} GB")
            except (PermissionError, OSError):
                pass
        try:
            g = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                                "--format=csv,noheader"], capture_output=True, text=True, timeout=10).stdout.strip()
            lines.append(f"GPU: {g}")
        except (OSError, subprocess.TimeoutExpired):
            pass
        b = psutil.sensors_battery()
        if b:
            lines.append(f"Battery: {b.percent}% {'charging' if b.power_plugged else 'on battery'}")
        lines.append(f"Uptime: {(time.time() - psutil.boot_time()) / 3600:.1f} h")
        return "\n".join(lines)

    @reg.add("list_processes", "List running processes (optionally filtered by name), sorted by memory.",
             {"filter": S, "limit": I})
    def list_processes(filter: str = "", limit: int = 30):  # noqa: A002
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            if filter.lower() in (p.info["name"] or "").lower():
                procs.append(p.info)
        procs.sort(key=lambda i: -(i["memory_info"].rss if i["memory_info"] else 0))
        return "\n".join(f"{i['pid']:>7} {i['name']:<40} {(i['memory_info'].rss if i['memory_info'] else 0) / 2**20:>8.0f} MB"
                         for i in procs[:limit]) or "No matching processes."

    @reg.add("kill_process", "End a process by PID. Asks the user first.", {"pid": I}, ["pid"])
    def kill_process(pid: int):
        import psutil
        p = psutil.Process(pid)
        policy.require("process", f"End process {p.name()} (PID {pid})")
        p.terminate()
        try:
            p.wait(5)
        except psutil.TimeoutExpired:
            p.kill()
        return f"Ended {pid}"

    # ------------------------------------------------------------------ clipboard & notifications
    @reg.add("clipboard_get", "Read the text on the clipboard. Asks the user first (it may hold private data).", {})
    def clipboard_get():
        policy.require("clipboard", "Read the clipboard")
        return pc.clipboard_read()[:8000] or "(clipboard is empty or not text)"

    @reg.add("clipboard_set", "Put text on the clipboard so the user can paste it.", {"text": S}, ["text"])
    def clipboard_set(text: str):
        pc.clipboard_write(text)
        return f"Copied {len(text)} characters to the clipboard."

    @reg.add("notify", "Show a desktop notification (useful when a long or scheduled task finishes).",
             {"title": S, "message": S}, ["title", "message"])
    def notify(title: str, message: str):
        pc.notify(title, message)
        return "Notification shown."

    @reg.add("wait", "Pause for a number of seconds (max 120), e.g. while an app or page loads.", {"seconds": N},
             ["seconds"])
    def wait(seconds: float):
        time.sleep(max(0.0, min(float(seconds), 120.0)))
        return f"Waited {seconds}s"

    # ------------------------------------------------------------------ HTTP / APIs
    @reg.add("http_request",
             "Call a web API. GET/HEAD run directly; POST/PUT/PATCH/DELETE change things on another service, so they "
             "ask the user first. Returns status and body (JSON pretty-printed).",
             {"url": S, "method": S, "json": {"type": "object"}, "body": S, "headers": {"type": "object"}},
             ["url"])
    def http_request(url: str, method: str = "GET", json: dict | None = None, body: str = "",  # noqa: A002
                     headers: dict | None = None):
        method = method.upper()
        if method not in ("GET", "HEAD"):
            policy.require("network_write", f"{method} {url}" + (f"\nbody: {str(json or body)[:500]}" if json or body else ""))
        r = httpx.request(method, url, json=json, content=body or None, headers=headers or {}, timeout=60,
                          follow_redirects=True)
        ct = r.headers.get("content-type", "")
        text = r.text
        if "json" in ct:
            try:
                import json as _j
                text = _j.dumps(r.json(), indent=1, ensure_ascii=False)
            except ValueError:
                pass
        return f"HTTP {r.status_code} {ct}\n{text[:8000]}"
