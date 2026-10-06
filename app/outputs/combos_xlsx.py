"""Writes Combos.xlsx (the Combos tab's Export Excel): the combo list, looking like the Schedule.xlsx export.

    Combos      one table per combo (first-year combos and shows in its heading): each member in the Combos tab's
                order (by instrument) with instrument, liaison, email and other combos, then the supervisor
    Everyone    one row per person per combo, for sorting and filtering

An export: never read back, so editing it changes nothing.
"""
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Border, Font

from outputs.excel_schedule import BLOCK_LINE, COL_LINE, FONT, GREY, HEAD_FILL, NIGHT_FILL, header
from shared_folder import save_workbook
from util import by_instrument


def write_combos_xlsx(path, combos, name_of, semester, instruments=None, shows=None):
    """combos in the order to list; name_of(email) -> name; instruments = {(combo name, email): instrument};
    shows = {combo id: ['Tue Oct 13', 'Fri Nov 6*', ...]} (* = supervised night). PermissionError: open in Excel."""
    instruments, shows = instruments or {}, shows or {}
    in_combos = {}
    for c in combos:
        for e in c.members:
            in_combos.setdefault(e, []).append(c.name)

    def font(**kw):
        return Font(name=FONT, **kw)

    def people(c):
        """(name, instrument, role, email, also in) per member (liaison marked), then the supervisor."""
        rows = [(name_of(e), instruments.get((c.name, e), ""), "liaison" if e == c.liaison else "", e,
                 ", ".join(n for n in in_combos.get(e, []) if n != c.name))
                for e in by_instrument(c.members, lambda e: instruments.get((c.name, e), ""), name_of)]
        if c.professor:
            rows.append((name_of(c.professor), "", "supervisor", c.professor, ""))
        return rows

    wb = Workbook()
    wb.properties.subject = semester
    ws = wb.active
    ws.title = "Combos"
    ws.append([f"{semester}: combos"])
    ws["A1"].font = font(bold=True, size=14)
    ws.append([f"Exported from the Combo Scheduler on {datetime.now():%Y-%m-%d %H:%M}. Editing this file changes "
               "nothing: make changes in the app (Combos tab), then export again."])
    ws["A2"].font = font(italic=True, color=GREY)
    for c in combos:
        ws.append([])
        dates = [d.replace("*", " (supervised)") for d in shows.get(c.id, [])]
        ws.append([c.name + ("  ·  first-year combo" if c.first_year else "")
                   + (f"  ·  shows: {', '.join(dates)}" if dates else "")])
        for col in range(1, 6):
            ws.cell(ws.max_row, col).fill = NIGHT_FILL
        ws.cell(ws.max_row, 1).font = font(bold=True, size=11)
        header(ws, ["Name", "Instrument", "Role", "Email", "Also in"])
        rows = people(c)
        for i, row in enumerate(rows):
            ws.append(list(row))
            last = i == len(rows) - 1
            for cell in ws[ws.max_row]:
                cell.font = font(bold=cell.column == 1 and row[2] == "liaison",
                                 italic=row[2] == "supervisor", color=GREY if cell.column == 3 else None)
                cell.border = Border(left=COL_LINE, right=COL_LINE, bottom=BLOCK_LINE if last else COL_LINE)
        if not c.professor:
            ws.append(["No supervisor yet"])
            ws.cell(ws.max_row, 1).font = font(italic=True, color="C00000")
    for letter, w in zip("ABCDE", (28, 16, 12, 34, 22)):
        ws.column_dimensions[letter].width = w
    ws.page_setup.fitToWidth, ws.sheet_properties.pageSetUpPr.fitToPage = 1, True
    ws.page_setup.fitToHeight = 0

    s = wb.create_sheet("Everyone")
    header(s, ["Combo", "Name", "Instrument", "Role", "Email", "Also in"])
    for c in combos:
        for row in people(c):
            s.append([c.name] + list(row))
    for row in s.iter_rows(min_row=2):
        for cell in row:
            cell.font = font()
    for letter, w in zip("ABCDEF", (14, 28, 16, 12, 34, 22)):
        s.column_dimensions[letter].width = w
    s.freeze_panes = "A2"
    s.auto_filter.ref = s.dimensions
    save_workbook(wb, path)
