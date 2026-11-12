"""Files the user hands to Mochi (terminal: @file or --file, window: paperclip / drag and drop / paste).

prepare() copies each file into her workspace (uploads/), writes a short summary of what is in it, and queues
pictures for a vision model: photos as they are, videos as a few frames. She can then dig deeper with her tools.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg"}
AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus", ".wma"}
SHEET = {".xlsx", ".xlsm", ".csv", ".tsv"}
ARCHIVE = {".zip"}
MAX_FRAMES = 4
UPLOADS = "uploads"
TEXT_CHARS = 2000


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .") or "file"
    return name[:120]


def unique(dirpath: Path, name: str) -> Path:
    p = dirpath / name
    i = 2
    while p.exists():
        p = dirpath / f"{Path(name).stem} ({i}){Path(name).suffix}"
        i += 1
    return p


def _ff(tool: str) -> str | None:
    return shutil.which(tool)


def _probe(path: Path) -> str:
    ffprobe = _ff("ffprobe")
    if not ffprobe:
        return "(ffprobe not installed, so no details)"
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,channels",
                        "-of", "compact=p=0", str(path)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    out = (r.stdout or "").strip().replace("\n", "; ")
    return out[:400] or "(no details)"


def _duration(path: Path) -> float:
    ffprobe = _ff("ffprobe")
    if not ffprobe:
        return 0.0
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def video_frames(path: Path, out_dir: Path, count: int = MAX_FRAMES) -> list[Path]:
    """A few frames spread evenly across the video."""
    ffmpeg = _ff("ffmpeg")
    dur = _duration(path)
    if not ffmpeg or dur <= 0:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(count):
        t = dur * (i + 0.5) / count
        f = out_dir / f"frame_{i + 1}.jpg"
        r = subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                            "-vf", "scale='min(960,iw)':-2", "-q:v", "4", str(f)], capture_output=True, timeout=120)
        if r.returncode == 0 and f.exists():
            frames.append(f)
    return frames


def _text_of(path: Path) -> str | None:
    raw = path.read_bytes()[:60000]
    if b"\x00" in raw[:4000]:
        return None
    return raw.decode("utf-8", errors="replace")


def _pdf(path: Path) -> str:
    from pypdf import PdfReader
    rd = PdfReader(str(path))
    text = " ".join((rd.pages[i].extract_text() or "") for i in range(min(3, len(rd.pages))))
    text = re.sub(r"\s+", " ", text).strip()
    return f"PDF, {len(rd.pages)} page(s). Start: {text[:TEXT_CHARS]}" if text else \
        f"PDF, {len(rd.pages)} page(s), no selectable text (a scan? use inspect_pdf with render_page to look at it)."


def _docx(path: Path) -> str:
    import docx
    d = docx.Document(str(path))
    text = "\n".join(p.text for p in d.paragraphs if p.text.strip())
    return f"Word document, {len(d.paragraphs)} paragraph(s), {len(d.tables)} table(s). Start: {text[:TEXT_CHARS]}"


def _sheet(path: Path) -> str:
    if path.suffix.lower() in (".csv", ".tsv"):
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.reader(f, delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
        total = len(rows)
        rows = rows[:6]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [[("" if c is None else str(c)) for c in r] for r in ws.iter_rows(max_row=6, values_only=True)]
        total = ws.max_row
        names = ", ".join(wb.sheetnames[:8])
        wb.close()
        return f"Excel workbook, sheets: {names}. First sheet has about {total} row(s). First rows: " + \
               " | ".join(", ".join(r)[:200] for r in rows)
    return f"Table with {total} row(s). First rows: " + " | ".join(", ".join(r)[:200] for r in rows)


def describe(path: Path, rel_dir: Path) -> tuple[str, list[tuple[str, str]]]:
    """(one-paragraph summary, images to show a vision model) for one file."""
    ext = path.suffix.lower()
    size = path.stat().st_size
    try:
        if ext in IMAGE:
            from PIL import Image
            with Image.open(path) as im:
                dims = f"{im.width}x{im.height}"
            return f"Image {dims}. You can look at it.", [(str(path), path.name)]
        if ext in VIDEO:
            frames = video_frames(path, rel_dir / f"{path.stem}_frames")
            info = _probe(path)
            extra = f" {len(frames)} frames from across the video are shown to you." if frames else ""
            return (f"Video. {info}.{extra} For more: media_info, or media_convert to cut or extract audio or "
                    f"more frames. You cannot hear audio."), [(str(f), f"{path.name} frame {i + 1}")
                                                              for i, f in enumerate(frames)]
        if ext in AUDIO:
            return f"Audio. {_probe(path)}. You cannot listen to it, but media_info and media_convert work.", []
        if ext == ".pdf":
            return _pdf(path), []
        if ext == ".docx":
            return _docx(path), []
        if ext in SHEET:
            return _sheet(path), []
        if ext in ARCHIVE:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            return f"Zip with {len(names)} item(s): {', '.join(names[:25])}. Use unzip to open it.", []
        text = _text_of(path)
        if text is not None:
            return f"Text file. Start:\n{text[:TEXT_CHARS]}", []
    except Exception as e:  # noqa: BLE001
        return f"Could not preview it ({type(e).__name__}: {e}). Try the matching tool.", []
    return f"{size / 1024:.0f} KB binary file of type {ext or 'unknown'}. Try the matching tool.", []


def prepare(paths: list[str | Path], workspace: Path, denied=lambda p: False) -> tuple[str, list[tuple[str, str]]]:
    """Copy files into workspace/uploads (unless already inside), describe them. Returns (note, images)."""
    ws = workspace.resolve()
    up = ws / UPLOADS
    notes, images = [], []
    for raw in paths:
        src = Path(raw).expanduser()
        try:
            src = src.resolve()
        except OSError:
            notes.append(f"- {raw}: could not be opened.")
            continue
        if not src.is_file():
            notes.append(f"- {raw}: not a file, skipped.")
            continue
        if denied(src):
            notes.append(f"- {src.name}: blocked (looks like a credential or secret file), skipped.")
            continue
        try:
            src.relative_to(ws)
            dest = src
        except ValueError:
            up.mkdir(parents=True, exist_ok=True)
            dest = unique(up, safe_name(src.name))
            shutil.copy2(src, dest)
        summary, imgs = describe(dest, up)
        images += imgs
        notes.append(f"- {dest.relative_to(ws).as_posix()} ({dest.stat().st_size / 1024:.0f} KB): {summary}")
    if not notes:
        return "", []
    return "\n\n(Files the user attached, saved in your workspace:\n" + "\n".join(notes) + "\n)", images


# ---- terminal: @file mentions and pasted/dragged paths
_AT_QUOTED = re.compile(r'@"([^"]+)"')
_AT_PLAIN = re.compile(r"@(\S+)")
_QUOTED_WIN = re.compile(r'"([A-Za-z]:[\\/][^"]+)"')


def extract_paths(text: str) -> tuple[str, list[str]]:
    """Pull attached files out of a typed line. Understands @file, @"file with spaces" and a quoted path that was
    dragged into the terminal. Only paths that exist are taken; the rest of the line stays as typed."""
    found: list[str] = []

    def take(m, group=1):
        p = m.group(group).rstrip(".,;:!?)")
        if Path(p).expanduser().is_file():
            found.append(str(Path(p).expanduser()))
            return ""
        return m.group(0)

    text = _AT_QUOTED.sub(take, text)
    text = _QUOTED_WIN.sub(take, text)
    text = _AT_PLAIN.sub(take, text)
    return re.sub(r"\s{2,}", " ", text).strip(), found
