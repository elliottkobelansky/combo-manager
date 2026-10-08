"""Writes a printable month-by-month calendar of the shows: each night's sets as combo numbers.
The numbers match the combo list (Combos.pdf, exported from the app's Combos tab). Needs: pip install reportlab

It draws from `entries` = {date: {set number: ("combo", combo id) or ("text", anything typed)}}; a set that isn't
there is open. schedule_file.entries() makes them from the saved schedule, so swaps and text typed into open sets
show up.
"""
import calendar
import re
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.model import WEEKDAY_ABBR, make_label
from shared_folder import read_only_after

# Fixed English names so a French-language machine can't change the output.
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
HEAD_BG = colors.HexColor("#DDEBF7")
GRID = colors.HexColor("#B4C6E7")
GREY = colors.HexColor("#555555")
SHOW_BG = colors.HexColor("#F3F8FC")
OUTSIDE_BG = colors.HexColor("#F2F2F2")
SKIP_BG = colors.HexColor("#FBEFEF")

MARGIN = 0.5 * inch
PAD = 3                     # cell left/right padding
ROW_H = 0.6 * inch          # usual height of a week row; taller only when a night needs more lines
TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=18)
SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=8, leading=10, textColor=GREY)
MONTH = ParagraphStyle("month", fontName="Helvetica-Bold", fontSize=11, leading=13, spaceAfter=3)
DAYHEAD = ParagraphStyle("dayhead", fontName="Helvetica-Bold", fontSize=8, leading=9.5, alignment=1)
DAYNUM = ParagraphStyle("daynum", fontName="Helvetica-Bold", fontSize=8, leading=9.5)
VENUE = ParagraphStyle("venue", fontName="Helvetica", fontSize=6.5, leading=8, textColor=GREY)
SETS = ParagraphStyle("sets", fontName="Helvetica", fontSize=8.5, leading=10.5)
NOTE = ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=6.5, leading=8, textColor=GREY)


def short(text, n=32):
    text = str(text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "\u2026"


def set_label(night, k, suffix):
    """What goes before the combo number: the set's time ('7:00\u20137:45') if known, else the set number."""
    return night.set_range(k, suffix).replace(" ", "") or str(k)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def combo_numbers(combos):
    """combo id -> what the calendar shows: 'Combo 05' -> '05', the same number as on the combo list. A combo
    renamed by hand shows its name."""
    out = {}
    for c in combos:
        m = re.fullmatch(r"Combo (\d+)", c.name.strip())
        out[c.id] = m.group(1) if m else esc(c.name)
    return out


def fit(text, max_w, font, size):
    """Cut text with an ellipsis so it fits max_w points."""
    if stringWidth(text, font, size) <= max_w:
        return text
    while text and stringWidth(text + "\u2026", font, size) > max_w:
        text = text[:-1]
    return text.rstrip() + "\u2026"


def night_cell(d, night, playing, nums, open_word, suffix, inner, supervised=False, notes=None):
    """notes: a list to add (set label, full text) to for typed entries that had to be cut."""
    """Returns (cell content, number of set lines). Two sets per line ("1 05   2 12") when they fit in the cell's
    inner width, otherwise one per line ("7:00\u20137:45 05")."""
    venue = fit(night.venue, inner - stringWidth(f"{d.day}  ", "Helvetica-Bold", 8) - 1
                - (stringWidth(" FB", "Helvetica-Bold", 6) if supervised else 0), "Helvetica", 6.5)
    prof = ""
    if supervised:                                    # the mark on the day's line, after the venue
        prof = " <font name='Helvetica-Bold' size=6 color='#9C2A00'>FB</font>"
    out = [Paragraph(f"{d.day} &nbsp;<font name='Helvetica' size=6.5 color='#555555'>{esc(venue)}</font>{prof}",
                     DAYNUM)]
    sets, widths = [], []
    space, gap = stringWidth(" ", "Helvetica", 8.5), stringWidth("   ", "Helvetica", 8.5)
    for k in range(1, night.n_slots + 1):
        label = set_label(night, k, suffix)
        kind, value = playing.get(k, (None, None))
        if kind == "combo":
            body, w = f"<b>{nums[value]}</b>", stringWidth(nums[value], "Helvetica-Bold", 8.5)
        elif kind == "text":                   # typed into an open set: shown as written, cut to fit the cell
            room = inner - 1 - stringWidth(label, "Helvetica", 6.5) - space
            text = fit(str(value), room, "Helvetica-Oblique", 7)
            if text != str(value) and notes is not None:
                notes.append((d, label, str(value)))
            body, w = f"<font name='Helvetica-Oblique' size=7>{esc(text)}</font>", stringWidth(text, "Helvetica-Oblique", 7)
        else:
            body = f"<font color='#555555' size=6.5>{open_word}</font>"
            w = stringWidth(open_word.replace("&mdash;", "\u2014"), "Helvetica", 6.5)
        sets.append(f"<font color='#555555' size=6.5>{label}</font>&nbsp;{body}")
        widths.append(stringWidth(label, "Helvetica", 6.5) + space + w)
    lines, i = [], 0
    while i < len(sets):
        if i + 1 < len(sets) and widths[i] + gap + widths[i + 1] <= inner - 1:
            lines.append("&nbsp;&nbsp;&nbsp;".join(sets[i:i + 2]))
            i += 2
        else:
            lines.append(sets[i])
            i += 1
    out.append(Paragraph("<br/>".join(lines), SETS))
    return out, len(lines)


def month_block(year, month, nights, lineup, nums, skips, show_weekdays, open_word, suffix, width, supervised=()):
    first, last = min(nights), max(nights)
    weeks = [w for w in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
             if w[-1] >= first and w[0] <= last]          # leave out weeks before the first / after the last show
    notes = []                                            # typed entries cut short: printed in full below
    rows = [[Paragraph(d, DAYHEAD) for d in WEEKDAY_ABBR]]
    style = [("BACKGROUND", (0, 0), (-1, 0), HEAD_BG)]
    heights = []
    for r, week in enumerate(weeks, start=1):
        row, most = [], 0
        for col, d in enumerate(week):
            cell = (col, r)
            if d.month != month:
                row.append("")
                style.append(("BACKGROUND", cell, cell, OUTSIDE_BG))
            elif d in nights:
                content, n_lines = night_cell(d, nights[d], lineup.get(d, {}), nums, open_word, suffix,
                                              width / 7 - 2 * PAD, d in supervised, notes)
                row.append(content)
                most = max(most, n_lines)
                style.append(("BACKGROUND", cell, cell, SHOW_BG))
            elif d in skips and d.weekday() in show_weekdays:
                row.append([Paragraph(str(d.day), DAYNUM), Paragraph(f"No show: {esc(short(skips[d]))}", NOTE)])
                style.append(("BACKGROUND", cell, cell, SKIP_BG))
            else:
                row.append(Paragraph(f"<font color='#999999'>{d.day}</font>", DAYNUM))
        rows.append(row)
        heights.append(max(ROW_H, 2 + DAYNUM.leading + most * SETS.leading + 2))
    t = Table(rows, colWidths=[width / 7] * 7, rowHeights=[None] + heights)
    t.setStyle(TableStyle(style + [
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    after = [Paragraph("<br/>".join(f"<i>{esc(make_label(d))}, {esc(label)}:</i> {esc(text)}" for d, label, text in notes),
                       SUB)] if notes else []
    return KeepTogether([Paragraph(f"{MONTHS[month - 1]} {year}", MONTH), t] + after + [Spacer(1, 10)])


def write_schedule_pdf(path, nights, entries, combos, supervised, settings):
    """nights: list of Night; entries: see the top of this file; combos: {id: Combo}; supervised: set of dates."""
    semester = settings.semester_name
    nights = {n.date: n for n in nights}
    nums = combo_numbers(combos.values())
    open_word = "open" if settings.extra_slot_policy == "open" else "&mdash;"
    show_weekdays = {sd.weekday for sd in settings.show_days}
    skips = {d: why for d, why in settings.skip_dates.items() if settings.start_date <= d <= settings.end_date}

    doc = SimpleDocTemplate(str(path), pagesize=letter, title=f"{semester} show calendar",
                            leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN)
    times = [t for n in nights.values() if n.first_set is not None
             for k in range(1, n.n_slots + 1) for t in (n.set_time(k), n.set_end(k))]
    all_pm = bool(times) and all(t.hour >= 12 for t in times)
    suffix = not all_pm                     # "7:00\u20137:45" when every set is in the evening, else with am / pm
    if times:
        legend = ("Each show night lists its sets in order: when the set starts and ends (small) and the combo "
                  "playing it (bold). " + ("All times are p.m. " if all_pm else ""))
        if len(times) < sum(n.n_slots for n in nights.values()):
            legend += "Nights without set times show the set number instead. "
    else:
        legend = "Each show night lists its sets in order (small number) and the combo playing it (bold). "
    legend += "Combo numbers match the combo list."
    if settings.extra_slot_policy == "open":
        legend += " <b>open</b> = set open for volunteers."
    if supervised:
        legend += " <b>FB</b> = a feedback night: a faculty member attends."
    if any(kind == "text" for row in entries.values() for kind, _ in row.values()):
        legend += " <i>Italics</i> = not a combo (typed in by hand)."
    story = [Paragraph(f"{esc(semester)} Show Calendar", TITLE),
             Paragraph(f"{len(nights)} show nights. Generated {make_label(date.today())}, {date.today().year}. "
                       + legend, SUB),
             Spacer(1, 8)]
    first, last = min(nights), max(nights)
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        story.append(month_block(y, m, nights, entries, nums, skips, show_weekdays, open_word, suffix,
                                 doc.width, supervised))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(letter[0] - MARGIN, MARGIN / 2, f"{semester} show calendar, page {d.page}")
        canvas.restoreState()
    with read_only_after(path):                       # (an export: read-only, see shared_folder.py)
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
