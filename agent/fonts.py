"""Fonts and text direction for documents in any language.

reportlab's built-in Helvetica only covers Western European text (cp1252). For anything else this module registers
  * DejaVu Sans (bundled in assets/fonts): Latin Extended, Cyrillic, Greek, Armenian, Georgian, Hebrew, Arabic forms
  * reportlab's CID fonts for Chinese, Japanese and Korean (the PDF viewer supplies the glyphs)
and shapes right-to-left text (Arabic, Hebrew) with arabic-reshaper + python-bidi. Scripts that need complex shaping
(Thai, Devanagari and other Indic scripts, Khmer, Myanmar...) cannot be laid out by reportlab: the caller is told.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

SCRIPTS = {
    "kana": r"[぀-ヿㇰ-ㇿ]",
    "hangul": r"[ᄀ-ᇿ㄰-㆏가-힯]",
    "han": r"[㐀-䶿一-鿿豈-﫿]",
    "arabic": r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]",
    "hebrew": r"[֐-׿יִ-ﭏ]",
    "complex": r"[ऀ-෿฀-໿ༀ-࿿က-႟ក-៿]",
}
_RTL = re.compile(SCRIPTS["arabic"] + "|" + SCRIPTS["hebrew"])
_registered: dict = {}


def scripts_in(text: str) -> set[str]:
    return {name for name, rx in SCRIPTS.items() if re.search(rx, text)}


def needs_unicode_font(text: str) -> bool:
    """True when Helvetica (cp1252) cannot show the text."""
    try:
        text.encode("cp1252")
        return False
    except UnicodeEncodeError:
        return True


def is_rtl(text: str) -> bool:
    """The first strongly directional letter is Arabic or Hebrew."""
    for ch in text:
        if _RTL.match(ch):
            return True
        if ch.isalpha():
            return False
    return False


def rtl_display(text: str) -> str:
    """Shape and reorder right-to-left text for a renderer that draws left to right."""
    if not _RTL.search(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return text
    return get_display(arabic_reshaper.reshape(text))


def setup(text: str) -> dict:
    """Register what the text needs and return {'base', 'bold', 'mono', 'cjk', 'notes'}: font names for reportlab.
    'cjk' maps a script ('han', 'kana', 'hangul') to the CID font for runs of that script."""
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    found = scripts_in(text)
    out = {"base": "Helvetica", "bold": "Helvetica-Bold", "mono": "Courier", "cjk": {}, "notes": []}
    if not needs_unicode_font(text):
        return out
    files = {"MochiSans": "DejaVuSans.ttf", "MochiSans-Bold": "DejaVuSans-Bold.ttf", "MochiMono": "DejaVuSansMono.ttf"}
    if all((FONT_DIR / f).is_file() for f in files.values()):
        if "MochiSans" not in _registered:
            for name, f in files.items():
                pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f)))
            _registered["MochiSans"] = True
        for b, i, n in ((0, 0, "MochiSans"), (1, 0, "MochiSans-Bold"), (0, 1, "MochiSans"), (1, 1, "MochiSans-Bold")):
            addMapping("MochiSans", b, i, n)
        out.update(base="MochiSans", bold="MochiSans-Bold", mono="MochiMono")
    else:
        out["notes"].append("The Unicode font files are missing (assets/fonts); special characters may not show.")
    if found & {"kana", "hangul", "han"}:
        # Japanese kanji follow the Japanese font when kana is present; Han alone is treated as Chinese
        pick = {"kana": "HeiseiMin-W3", "hangul": "HYSMyeongJo-Medium",
                "han": "HeiseiMin-W3" if "kana" in found else "STSong-Light"}
        for script in found & set(pick):
            if pick[script] not in _registered:
                pdfmetrics.registerFont(UnicodeCIDFont(pick[script]))
                _registered[pick[script]] = True
            for b in (0, 1):
                for i in (0, 1):
                    addMapping(pick[script], b, i, pick[script])
            out["cjk"][script] = pick[script]
        out["notes"].append("Chinese/Japanese/Korean text uses the PDF viewer's own fonts (not embedded).")
    if "complex" in found:
        out["notes"].append("Thai, Indic, Khmer and similar scripts need complex shaping that PDF output here cannot do: "
                            "their letters may be missing or wrong. Use create_docx for those languages.")
    if found & {"arabic", "hebrew"}:
        try:
            import arabic_reshaper  # noqa: F401
            from bidi.algorithm import get_display  # noqa: F401
        except ImportError:
            out["notes"].append("Arabic/Hebrew needs the arabic-reshaper and python-bidi packages: letters would be "
                                "disconnected and in the wrong order.")
    return out


def wrap_cjk(markup: str, cjk: dict) -> str:
    """Put runs of Han / kana / Hangul into their own <font> so one document can mix them with other scripts."""
    if not cjk:
        return markup
    rx = {"hangul": SCRIPTS["hangul"], "han_kana": SCRIPTS["kana"][:-1] + SCRIPTS["han"][1:]}
    def run(rx_class, font, s):
        return re.sub(f"({rx_class}+)", lambda m: f"<font face='{font}'>{m.group(1)}</font>", s)
    if "hangul" in cjk:
        markup = run(SCRIPTS["hangul"], cjk["hangul"], markup)
    jp_zh = cjk.get("kana") or cjk.get("han")
    if jp_zh:   # kana and han runs (CJK punctuation joins them)
        markup = run("[\u3000-\u303f\uff00-\uffef\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", jp_zh, markup)
    return markup
