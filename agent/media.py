"""File kinds for the chat: what can be shown inline (thumbnail + big view) and what becomes a download card."""
from __future__ import annotations

from pathlib import Path

IMAGE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".gif": "image/gif", ".bmp": "image/bmp", ".avif": "image/avif"}
VIDEO = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
         ".mkv": "video/x-matroska", ".ogv": "video/ogg"}
AUDIO = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".m4a": "audio/mp4",
         ".flac": "audio/flac", ".opus": "audio/ogg", ".aac": "audio/aac"}
PDF = {".pdf": "application/pdf"}
ARCHIVE = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
TEXT = {".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml", ".xml", ".py", ".js", ".ts", ".html", ".css",
        ".ini", ".toml", ".sql", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".odt", ".ods", ".rtf"}

# Only these are ever served inline; everything else (including SVG and HTML) is forced to download so a file in
# the workspace can never run as a web page inside the chat window's origin.
INLINE = {**IMAGE, **VIDEO, **AUDIO, **PDF}


def kind_of(p: str | Path) -> str:
    ext = Path(p).suffix.lower()
    if ext in IMAGE:
        return "image"
    if ext in VIDEO:
        return "video"
    if ext in AUDIO:
        return "audio"
    if ext in PDF:
        return "pdf"
    if ext in ARCHIVE:
        return "archive"
    if ext in TEXT:
        return "doc"
    return "other"


def inline_mime(p: str | Path) -> str | None:
    return INLINE.get(Path(p).suffix.lower())
