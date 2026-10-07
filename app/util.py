"""Tiny helpers shared by the Excel-facing modules (settings loader and adapters)."""
import re
from datetime import date, datetime, time, timedelta

# Instruments in the order members are listed (Combos tab and Combos.pdf): any other instrument first, then these;
# people with no instrument set yet last.
INSTRUMENTS = ["Voice", "Trumpet", "Saxophone", "Trombone", "Guitar", "Piano", "Bass", "Drums"]
RHYTHM = {"Guitar", "Piano", "Bass", "Drums"}      # the rhythm section (Semester tab: "Warn: combos per rhythm player")


def by_instrument(emails, instrument_of, name_of):
    """emails sorted Other, Voice, Trumpet, Saxophone, Trombone, Guitar, Piano, Bass, Drums, then no instrument; by name
    within one instrument. instrument_of(email) -> instrument or ''."""
    known = [i.casefold() for i in INSTRUMENTS]

    def rank(e):
        inst = (instrument_of(e) or "").strip().casefold()
        return (len(known) + 1 if not inst else known.index(inst) + 1 if inst in known else 0, name_of(e).lower(), e)
    return sorted(emails, key=rank)


EXCEL_EPOCH = date(1899, 12, 30)


def blank(v):
    """True for None, empty text, and 0 (the Combos/Conflicts sheets use 0 for empty cells)."""
    return v is None or str(v).strip() in ("", "0")


def to_date(v):
    """Real date, Excel serial number (e.g. 46329), or text -> date. Slash dates are month-first (11/3/2026 = Nov 3),
    which is what Microsoft Forms exports in this setup.
    Returns None for blank/0. Raises ValueError if it can't be read."""
    if blank(v) or v is False:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) or re.fullmatch(r"\d{5}(\.\d+)?", str(v).strip()):
        n = float(v)
        if 30000 < n < 80000:
            return EXCEL_EPOCH + timedelta(days=int(n))
        raise ValueError(f"number {v} is not a plausible date")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%m/%d/%Y %H:%M", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"can't read '{s}' as a date")


def to_time(v):
    """Excel time, fraction of a day (0.8333 = 8:00 pm), or text like '20:00', '8:00 PM', '8pm' -> time.
    Returns None for blank. Raises ValueError if it can't be read."""
    if v is None or str(v).strip() == "":
        return None
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, time):
        return v
    if isinstance(v, (int, float)):
        if 0 <= v < 1:
            m = round(v * 24 * 60)
            return time(m // 60 % 24, m % 60)
        raise ValueError(f"number {v} is not a time of day")
    s = re.sub(r"\s+", "", str(v)).lower().replace(".", "")
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M%p", "%I%p", "%Hh%M", "%Hh"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"can't read '{v}' as a time")
