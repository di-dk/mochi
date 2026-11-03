"""Small Markdown -> PDF renderer on top of reportlab (headings, bullets, numbered lists,
bold/italic/code, tables, images, horizontal rules, page breaks via '---pagebreak---')."""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (HRFlowable, Image, ListFlowable, ListItem, PageBreak, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle)


def _inline(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)
    t = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r"<link href='\2' color='blue'>\1</link>", t)
    return t


def markdown_to_pdf(md: str, out: Path, title: str = "", base_dir: Path | None = None) -> int:
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=10.5, leading=14.5, spaceAfter=6)
    code = ParagraphStyle("code", parent=ss["Code"], fontSize=8.5, leading=11, backColor=colors.whitesmoke)
    hs = {1: ss["Heading1"], 2: ss["Heading2"], 3: ss["Heading3"], 4: ss["Heading4"]}
    story: list = []
    first_heading = next((re.sub(r"^#+\s*", "", l).strip() for l in md.splitlines() if l.strip()), "")
    if title and title.strip().lower() != first_heading.lower():
        story += [Paragraph(_inline(title), ss["Title"]), Spacer(1, 6)]

    lines = md.replace("\r\n", "\n").split("\n")
    i, para, items, ordered = 0, [], [], False

    def flush_para():
        nonlocal para
        if para:
            story.append(Paragraph(_inline(" ".join(para)), body))
            para = []

    def flush_list():
        nonlocal items
        if items:
            story.append(ListFlowable([ListItem(Paragraph(_inline(x), body)) for x in items],
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
            flush_para(); flush_list(); story.append(Paragraph(_inline(m.group(2)), hs[len(m.group(1))]))
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
            data = [[Paragraph(_inline(c), body) for c in r] for r in rows]
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
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{doc.page}")

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=title or out.stem)
    doc.build(story or [Paragraph("", body)], onFirstPage=on_page, onLaterPages=on_page)
    return pages["n"]
