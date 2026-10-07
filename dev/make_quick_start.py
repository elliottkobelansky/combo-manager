"""QUICK_START.md -> 'Quick Start.pdf' (one page, for the director), next to the launchers.

    python dev/make_quick_start.py

Understands what QUICK_START.md uses: '# ' title, '## ' headings, '1. ' steps, '- ' bullets, paragraphs, **bold**
and *italic*. Says so if the result is longer than one page.
"""
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate

ROOT = Path(__file__).resolve().parent.parent
BLUE, GREY = colors.HexColor("#1F4E79"), colors.HexColor("#444444")
TITLE = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=BLUE, spaceAfter=4)
HEAD = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12.5, leading=15, textColor=BLUE, spaceBefore=11,
                      spaceAfter=3)
BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=10.6, leading=13.8, alignment=TA_LEFT)
INTRO = ParagraphStyle("i", parent=BODY, textColor=GREY)


def inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", text)


def build(md, pdf):
    story, items, kind = [], [], None

    def flush():
        nonlocal items, kind
        if items:
            story.append(ListFlowable(
                [ListItem(Paragraph(inline(t), BODY), leftIndent=14, spaceAfter=3) for t in items],
                bulletType="1" if kind == "num" else "bullet", start="1" if kind == "num" else "•",
                bulletFormat="%s." if kind == "num" else None,
                leftIndent=14, bulletFontSize=10.6 if kind == "num" else 11, bulletColor=BLUE))
        items, kind = [], None

    first_para = True
    for line in md.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        num, bullet = re.match(r"^\d+\.\s+(.*)", line), re.match(r"^-\s+(.*)", line)
        if num or bullet:
            if kind != ("num" if num else "bullet"):
                flush()
                kind = "num" if num else "bullet"
            items.append((num or bullet).group(1))
            continue
        flush()
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), TITLE))
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), HEAD))
        elif line:
            story.append(Paragraph(inline(line), INTRO if first_para else BODY))
            first_para = False
    flush()
    pages = []
    doc = SimpleDocTemplate(str(pdf), pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.5 * inch, title="Combo Manager: Quick Start")
    doc.build(story, onFirstPage=lambda c, d: pages.append(1), onLaterPages=lambda c, d: pages.append(1))
    return len(pages)


if __name__ == "__main__":
    out = ROOT / "Quick Start.pdf"
    n = build(ROOT / "QUICK_START.md", out)
    print(f"Wrote {out} ({n} page{'s' if n != 1 else ''}).")
    if n > 1:
        sys.exit("Longer than one page: shorten QUICK_START.md.")
