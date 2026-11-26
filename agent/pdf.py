"""Small Markdown -> PDF renderer on top of reportlab (headings, bullets, numbered lists,
bold/italic/code, tables, images, horizontal rules, page breaks via '---pagebreak---')."""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from . import fonts
from reportlab.platypus import (HRFlowable, Image, ListFlowable, ListItem, PageBreak, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle)


NOTES: list[str] = []          # things the caller should tell the user about the last document (fonts, scripts)
_MONO = "Courier"


_CJK: dict = {}


def _inline(text: str) -> str:
    t = fonts.wrap_cjk(html.escape(fonts.rtl_display(text)), _CJK)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", lambda m: f"<font face='{_MONO}'>{m.group(1)}</font>", t)
    t = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r"<link href='\2' color='blue'>\1</link>", t)
    return t


def markdown_to_pdf(md: str, out: Path, title: str = "", base_dir: Path | None = None) -> int:
    global _MONO, _CJK
    if "complex" in fonts.scripts_in(md + "\n" + title):          # Nepali, Hindi, Thai...: needs real shaping
        try:
            pages = markdown_to_pdf_browser(md, out, title, base_dir)
            NOTES[:] = ["Printed with the browser engine so Devanagari/Thai letters are shaped correctly."]
            return pages
        except Exception as e:  # noqa: BLE001
            fallback = f"the browser engine was not available ({type(e).__name__}); "
        else:
            fallback = ""
    else:
        fallback = ""
    fx = fonts.setup(md + "\n" + title)             # Helvetica for Western text, Unicode/CJK fonts otherwise
    if fallback:
        fx["notes"].insert(0, "Complex-script text could not be shaped: " + fallback + "install Chromium "
                           "(playwright install chromium) or use create_docx.")
    NOTES[:] = fx["notes"]
    _MONO, _CJK = fx["mono"], fx["cjk"]
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=fx["base"], fontSize=10.5, leading=14.5, spaceAfter=6)
    code = ParagraphStyle("code", parent=ss["Code"], fontName=fx["mono"], fontSize=8.5, leading=11, backColor=colors.whitesmoke)
    hs = {n: ParagraphStyle(f"h{n}", parent=ss[f"Heading{n}"], fontName=fx["bold"]) for n in (1, 2, 3, 4)}
    title_style = ParagraphStyle("title", parent=ss["Title"], fontName=fx["bold"])

    def P(text: str, style):                          # right-to-left paragraphs are right-aligned
        if fonts.is_rtl(text):
            style = ParagraphStyle(style.name + "_rtl", parent=style, alignment=TA_RIGHT)
        return Paragraph(_inline(text), style)

    story: list = []
    first_heading = next((re.sub(r"^#+\s*", "", l).strip() for l in md.splitlines() if l.strip()), "")
    if title and title.strip().lower() != first_heading.lower():
        story += [P(title, title_style), Spacer(1, 6)]

    lines = md.replace("\r\n", "\n").split("\n")
    i, para, items, ordered = 0, [], [], False

    def flush_para():
        nonlocal para
        if para:
            story.append(P(" ".join(para), body))
            para = []

    def flush_list():
        nonlocal items
        if items:
            story.append(ListFlowable([ListItem(P(x, body)) for x in items],
                                      bulletType="1" if ordered else "bullet", leftIndent=14))
            items = []

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush_para(); flush_list()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i]); i += 1
            story.append(Preformatted("\n".join(block), code))
        elif s == "---pagebreak---":
            flush_para(); flush_list(); story.append(PageBreak())
        elif re.fullmatch(r"(-{3,}|\*{3,})", s):
            flush_para(); flush_list(); story.append(HRFlowable(width="100%", color=colors.grey))
        elif m := re.match(r"^(#{1,4})\s+(.*)", s):
            flush_para(); flush_list(); story.append(P(m.group(2), hs[len(m.group(1))]))
        elif m := re.match(r"^!\[(.*?)\]\((.+?)\)", s):
            flush_para(); flush_list()
            p = Path(m.group(2))
            if not p.is_absolute() and base_dir:
                p = base_dir / p
            if p.exists():
                img = Image(str(p))
                scale = min(1.0, (A4[0] - 4 * cm) / img.drawWidth, (A4[1] / 2) / img.drawHeight)
                img.drawWidth *= scale; img.drawHeight *= scale
                story.append(img)
            else:
                story.append(Paragraph(f"<i>[missing image: {html.escape(str(p))}]</i>", body))
        elif s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush_para(); flush_list()
            rows = [[c.strip() for c in s.strip("|").split("|")]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            i -= 1
            data = [[P(c, body) for c in r] for r in rows]
            t = Table(data, repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef6")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [t, Spacer(1, 8)]
        elif m := re.match(r"^\s*[-*+]\s+(.*)", line):
            flush_para()
            if items and ordered: flush_list()
            ordered = False; items.append(m.group(1))
        elif m := re.match(r"^\s*\d+[.)]\s+(.*)", line):
            flush_para()
            if items and not ordered: flush_list()
            ordered = True; items.append(m.group(1))
        elif not s:
            flush_para(); flush_list()
        else:
            flush_list(); para.append(s)
        i += 1
    flush_para(); flush_list()

    pages = {"n": 0}

    def on_page(canvas, doc):
        pages["n"] = doc.page
        canvas.setFont(fx["base"], 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{doc.page}")

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=title or out.stem)
    doc.build(story or [Paragraph("", body)], onFirstPage=on_page, onLaterPages=on_page)
    return pages["n"]


# ---------------------------------------------------------------------------------------------------------------
# Scripts that need complex shaping (Devanagari/Nepali/Hindi, Thai, Khmer...) cannot be laid out by reportlab. The
# browser engine (Chromium via Playwright, already used for her web tools) shapes them correctly, so those documents
# are printed from HTML instead.
def _html_page(md: str, title: str, base_dir: Path | None) -> str:
    import markdown as md_lib
    first = next((re.sub(r"^#+\s*", "", l).strip() for l in md.splitlines() if l.strip()), "")
    heading = "" if title and title.strip().lower() == first.lower() else title   # the text may already start with its title
    body = md_lib.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    fdir = Path(fonts.FONT_DIR).resolve().as_uri()
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<base href="{(base_dir.resolve().as_uri() + '/') if base_dir else ''}">
<style>
@font-face {{ font-family: "MochiDeva"; src: url("{fdir}/NotoSansDevanagari-Regular.ttf"); font-weight: normal; }}
@font-face {{ font-family: "MochiDeva"; src: url("{fdir}/NotoSansDevanagari-Bold.ttf"); font-weight: bold; }}
@font-face {{ font-family: "MochiSansBundled"; src: url("{fdir}/DejaVuSans.ttf"); font-weight: normal; }}
@font-face {{ font-family: "MochiSansBundled"; src: url("{fdir}/DejaVuSans-Bold.ttf"); font-weight: bold; }}
body {{ font-family: "MochiDeva", "MochiSansBundled", "Noto Sans", "Nirmala UI", "Mangal", sans-serif; font-size: 10.5pt;
       line-height: 1.55; color: #222; }}
h1 {{ font-size: 20pt; }} h2 {{ font-size: 15pt; }} h3 {{ font-size: 12.5pt; }}
p, li, td, th, h1, h2, h3, h4 {{ unicode-bidi: plaintext; }}
table {{ border-collapse: collapse; margin: 8px 0; }} td, th {{ border: 1px solid #999; padding: 4px 8px; }}
th {{ background: #e8eef6; }} code, pre {{ font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; background: #f4f4f4; }}
pre {{ padding: 8px; }} img {{ max-width: 100%; }} hr {{ border: 0; border-top: 1px solid #999; }}
</style></head><body>{('<h1>' + html.escape(heading) + '</h1>') if heading else ''}{body.replace('---pagebreak---', '<div style="page-break-after:always"></div>')}</body></html>"""


def markdown_to_pdf_browser(md: str, out: Path, title: str = "", base_dir: Path | None = None) -> int:
    """Print the Markdown as a PDF with Chromium (correct Devanagari, Thai, ...). Raises if it is not available."""
    from playwright.sync_api import sync_playwright
    page_html = _html_page(md, title, base_dir)
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page()
            tmp = out.with_suffix(".tmp.html")
            tmp.write_text(page_html, encoding="utf-8")             # file:// so the bundled fonts and images load
            pg.goto(tmp.resolve().as_uri())
            pg.pdf(path=str(out), format="A4", print_background=True, display_header_footer=True,
                   header_template="<span></span>",
                   footer_template='<div style="font-size:8px;color:#888;width:100%;text-align:right;margin-right:2cm">'
                                   '<span class="pageNumber"></span></div>',
                   margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"})
            tmp.unlink(missing_ok=True)
        finally:
            b.close()
    from pypdf import PdfReader
    return len(PdfReader(str(out)).pages)
