"""Writes Combos.pdf: every combo as a box with its supervisor and members (by instrument, see util.INSTRUMENTS;
the liaison marked).
Three columns per page. Combo names match the calendar (Combo 05 there = 05 on Schedule.pdf).
Needs: pip install reportlab
"""
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

from core.model import make_label
from shared_folder import read_only_after
from util import by_instrument

HEAD_BG = colors.HexColor("#DDEBF7")
GRID = colors.HexColor("#B4C6E7")
GREY = colors.HexColor("#555555")
MARGIN, GUTTER, TITLE_H, COLS = 0.5 * inch, 0.2 * inch, 0.45 * inch, 3
COMBO = ParagraphStyle("combo", fontName="Helvetica-Bold", fontSize=9.5, leading=11)
SUPER = ParagraphStyle("super", fontName="Helvetica", fontSize=7.5, leading=9, textColor=GREY)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=10)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def combo_block(c, name_of, instruments, width):
    sup = esc(name_of(c.professor)) if c.professor else "<font color='#C00000'>No coach</font>"
    title = esc(c.name) + ("  <font size=7 color='#555555'>(first year)</font>" if c.first_year else "")
    rows = [[[Paragraph(title, COMBO), Paragraph(sup, SUPER)]]]
    for e in by_instrument(c.members, lambda e: instruments.get((c.name, e), ""), name_of):
        inst = instruments.get((c.name, e))
        extra = [f"<font size=7 color='#555555'>{esc(inst)}</font>"] if inst else []
        if e == c.liaison:
            extra.append("<font size=6.5 color='#555555'>(liaison)</font>")
        rows.append([Paragraph(esc(name_of(e)) + (" &nbsp;" + " ".join(extra) if extra else ""), CELL)])
    t = Table(rows, colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, 0), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
    ]))
    return KeepTogether([t, Spacer(1, 7)])


def write_combos_pdf(path, combos, name_of, semester, instruments=None):
    """combos in the order to print; name_of(email) -> name; instruments = {(combo name, email): instrument}."""
    instruments = instruments or {}
    pw, ph = letter
    col_w = (pw - 2 * MARGIN - (COLS - 1) * GUTTER) / COLS

    def frames(top_reserved):
        h = ph - 2 * MARGIN - top_reserved
        return [Frame(MARGIN + i * (col_w + GUTTER), MARGIN, col_w, h, 0, 0, 0, 0) for i in range(COLS)]

    n_students = len(set().union(*[c.members for c in combos])) if combos else 0
    subtitle = f"{len(combos)} combos, {n_students} students. Made {make_label(date.today())}, {date.today().year}."

    def first_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(MARGIN, ph - MARGIN - 13, f"{semester} Combos")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN, ph - MARGIN - 25, subtitle)
        canvas.restoreState()
        footer(canvas, doc)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(pw - MARGIN, MARGIN / 2, f"{semester} combos, page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=letter, title=f"{semester} combos",
                          leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN)
    doc.addPageTemplates([PageTemplate("first", frames(TITLE_H), onPage=first_page),
                          PageTemplate("rest", frames(0), onPage=footer)])
    with read_only_after(path):                       # (an export: read-only, see shared_folder.py)
        doc.build([NextPageTemplate("rest")] + [combo_block(c, name_of, instruments, col_w) for c in combos])
