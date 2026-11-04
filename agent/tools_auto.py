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
             "Edit an image: resize (width/height, keeps aspect if one is 0), crop [l,t,r,b], rotate degrees, "
             "grayscale, convert format via output extension (png/jpg/webp/ico). Saves to output.",
             {"path": S, "output": S, "width": I, "height": I, "crop": {"type": "array", "items": I},
              "rotate": N, "grayscale": B, "quality": I}, ["path", "output"])
    def image_edit(path: str, output: str, width: int = 0, height: int = 0, crop: list | None = None,
                   rotate: float = 0, grayscale: bool = False, quality: int = 90):
        from PIL import Image
        src, dst = policy.check_read(path), policy.check_write(output)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            if crop:
                im = im.crop(tuple(crop))
            if rotate:
                im = im.rotate(-rotate, expand=True)
            if width or height:
                w = width or round(im.width * height / im.height)
                h = height or round(im.height * width / im.width)
                im = im.resize((w, h), Image.LANCZOS)
            if grayscale:
                im = im.convert("L")
            if dst.suffix.lower() in (".jpg", ".jpeg") and im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            kw = {"quality": quality} if dst.suffix.lower() in (".jpg", ".jpeg", ".webp") else {}
            im.save(dst, **kw)
            size = f"{im.width}x{im.height}"
        return f"Saved {dst} ({size})" + reg.attach_image(dst, dst.name)

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
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return r.stdout[:8000] or "(clipboard is empty or not text)"

    @reg.add("clipboard_set", "Put text on the clipboard so the user can paste it.", {"text": S}, ["text"])
    def clipboard_set(text: str):
        subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], input=text,
                       text=True, encoding="utf-8")
        return f"Copied {len(text)} characters to the clipboard."

    @reg.add("notify", "Show a Windows notification (useful when a long or scheduled task finishes).",
             {"title": S, "message": S}, ["title", "message"])
    def notify(title: str, message: str):
        from win11toast import notify as toast
        toast(title[:80], message[:300], app_id="Mochi")
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
