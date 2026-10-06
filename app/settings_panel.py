"""The Settings tab of scheduler_app.py: edits settings.json (see settings_file.py) with forms and lists.

Dates use a pop-up calendar when the tkcalendar package is installed (the app's Install button adds it); without
it, dates are typed as YYYY-MM-DD.
"""
import json
import sys
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from core import generate_nights
from core.model import WEEKDAYS, make_label
from data_folder import SCHEDULE_XLSX, SETTINGS_FILE, settings_path
from settings_file import DEFAULTS, HELP, SettingsError, read_data, save_data, validate
from shared_folder import fingerprint
from util import to_date

try:
    from tkcalendar import Calendar
except ImportError:
    Calendar = None

GENERAL = [  # (key, label, kind)  kind: text, wide (longer text), date, date?, int, int?, policy, timing, bool; section = a heading
    (None, "Semester", "section"),
    ("semester_name", "Semester name", "text"),
    ("start_date", "First possible show day", "date"),
    ("end_date", "Last possible show day", "date"),
    (None, "Shows per combo", "section"),
    ("extra_slot_policy", "Leftover sets", "policy"),
    ("min_shows_per_combo", "Minimum shows per combo", "int"),
    ("max_shows_per_combo", "Maximum shows per combo", "int?"),
    ("min_days_between_shows", "Ideal days between shows", "int"),
    (None, "First-year combos", "section"),
    ("use_first_year", "First-year combos", "bool"),
    ("first_year_earliest_date", "First-year combos play from", "date"),
    ("first_year_first_show_supervised", "First show supervised", "bool"),
    (None, "Supervision", "section"),
    ("every_combo_supervised", "Supervised nights", "bool"),
    ("max_supervised_nights", "Max supervised nights (all profs)", "int?"),
    ("supervision_timing", "Supervised nights preferred", "timing"),
    (None, "Emails", "section"),
    ("student_email_domain", "Student email domain", "text"),
    ("email_domain_fixes", "Student email domain fixes", "wide"),
    (None, "Warnings and solver", "section"),
    ("max_blocked_dates_per_person", "Warn: conflicts per person", "int?"),
    ("min_usable_nights_per_combo", "Warn: usable nights per combo", "int?"),
    ("min_members_per_combo", "Warn: members per combo", "int?"),
    ("solver_time_limit_sec", "Solver time (seconds)", "int"),
]
POLICIES = {"open": "Leave open", "auto": "Fill every set"}      # settings.json value -> what the menu shows
TIMINGS = {"none": "Any time", "early": "Earlier in the semester", "late": "Later in the semester"}
MENUS = {"policy": (POLICIES, "open", 14), "timing": (TIMINGS, "none", 22)}   # kind -> (choices, default, width)


class ScrollFrame(ttk.Frame):
    """A frame whose contents (self.inner) scroll vertically, with the mouse wheel too."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, padding=(8, 4, 16, 12))
        window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.bind("<Enter>", lambda _: self.wheel(True))
        self.bind("<Leave>", lambda _: self.wheel(False))

    def wheel(self, on):
        events = ("<MouseWheel>", "<Button-4>", "<Button-5>")
        for ev in events:
            if on:
                self.bind_all(ev, self.scroll)
            else:
                self.unbind_all(ev)

    def scroll(self, e):
        if self.canvas.yview() == (0.0, 1.0):
            return                                    # everything fits: nothing to scroll
        step = -1 if getattr(e, "num", 0) == 4 else 1 if getattr(e, "num", 0) == 5 else \
            (-1 if e.delta > 0 else 1) * max(1, abs(e.delta) // (1 if sys.platform == "darwin" else 120))
        self.canvas.yview_scroll(step, "units")

    def recolor(self, palette):
        self.canvas.configure(background=palette.get("bg", "white"))


def set_enabled(widget, on):
    """Enables or disables a widget and everything inside it (e.g. a DateField's entry and buttons)."""
    try:
        widget.state(["!disabled"] if on else ["disabled"])
    except (AttributeError, tk.TclError):
        pass
    for child in widget.winfo_children():
        set_enabled(child, on)


def weekday_of(text):
    try:
        d = to_date(text)
        return f"{d:%a}" if d else ""
    except ValueError:
        return "?"


PALETTE = {}                  # set by SettingsPanel: theme colours for the calendar pop-up


class DateField(ttk.Frame):
    """A YYYY-MM-DD entry with a calendar button (when tkcalendar is installed) and the weekday next to it."""

    def __init__(self, parent, value="", optional=False):
        super().__init__(parent)
        self.var = tk.StringVar(value=value or "")
        ttk.Entry(self, textvariable=self.var, width=12).pack(side="left")
        ttk.Button(self, text="Pick", command=self.pick).pack(side="left", padx=(6, 0))
        if optional:
            ttk.Button(self, text="Clear", command=lambda: self.var.set("")).pack(side="left", padx=(6, 0))
        self.day = ttk.Label(self, width=4, anchor="w", style="Hint.TLabel")
        self.day.pack(side="left", padx=3)
        self.var.trace_add("write", lambda *_: self.day.configure(text=weekday_of(self.var.get())))
        self.day.configure(text=weekday_of(self.var.get()))

    def pick(self):
        if Calendar is None:
            messagebox.showinfo("Calendar not installed", "The pop-up calendar needs the tkcalendar package.\n\n"
                                "On the Run tab, click 'Install missing packages', then close and reopen this "
                                "window. Until then, type dates as YYYY-MM-DD (e.g. 2027-03-02).", parent=self)
            return
        top = tk.Toplevel(self)
        top.title("Pick a date")
        top.transient(self.winfo_toplevel())
        try:
            start = to_date(self.var.get()) or date.today()
        except ValueError:
            start = date.today()
        from theme import calendar_colors
        cal = Calendar(top, selectmode="day", year=start.year, month=start.month, day=start.day,
                       date_pattern="yyyy-mm-dd", firstweekday="monday", showweeknumbers=False,
                       **(calendar_colors(PALETTE) if PALETTE else {}))
        cal.pack(padx=12, pady=12)

        def done(_=None):
            self.var.set(cal.get_date())
            top.destroy()
        cal.bind("<<CalendarSelected>>", done)
        ttk.Button(top, text="Cancel", command=top.destroy).pack(pady=(0, 12))
        top.grab_set()

    def get(self):
        return self.var.get().strip() or None


def as_int(text):
    text = str(text).strip()
    return int(text) if text else None


class ListEditor:
    """A table of rows (list of dicts) with Add / Edit / Remove; each row is edited in a small form."""

    def __init__(self, parent, columns, fields, title, sort_key=None):
        # columns: [(key, heading, width)]; fields: [(key, label, kind)] for the form; kind as in GENERAL, plus
        # "weekday" and "time"
        self.columns, self.fields, self.title, self.sort_key, self.rows = columns, fields, title, sort_key, []
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))
        self.tree = ttk.Treeview(self.frame, columns=[c[0] for c in columns], show="headings", height=10)
        for key, heading, width in columns:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _: self.edit())
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Add...", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(bar, text="Edit...", command=self.edit).pack(side="left", padx=6)
        ttk.Button(bar, text="Remove", command=self.remove).pack(side="left")

    def set(self, rows):
        self.rows = [dict(r) for r in rows]
        self.refresh()

    def refresh(self):
        if self.sort_key:
            self.rows.sort(key=self.sort_key)
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            values = []
            for key, _, _ in self.columns:
                v = r.get(key)
                if key == "_weekday":
                    v = weekday_of(r.get("date"))
                values.append("Yes" if v is True else "" if v is None or v is False else v)
            self.tree.insert("", "end", iid=str(i), values=values)

    def selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def add(self):
        self.form({}, None)

    def edit(self):
        i = self.selected()
        if i is not None:
            self.form(self.rows[i], i)

    def remove(self):
        i = self.selected()
        if i is not None:
            del self.rows[i]
            self.refresh()

    def form(self, row, index):
        win = tk.Toplevel(self.frame)
        win.title(self.title)
        win.transient(self.frame.winfo_toplevel())
        top = ttk.Frame(win, padding=16)
        top.pack(fill="both", expand=True)
        widgets = {}
        for r, (key, label, kind) in enumerate(self.fields):
            ttk.Label(top, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=(0, 12), pady=4)
            v = row.get(key)
            if kind in ("date", "date?"):
                w = DateField(top, v, optional=kind == "date?")
            elif kind == "weekday":
                w = ttk.Combobox(top, values=WEEKDAYS, state="readonly", width=12)
                w.set(v or "")
            elif kind == "bool":
                var = tk.BooleanVar(value=bool(v))
                w = ttk.Checkbutton(top, variable=var)
                w.var = var
            else:
                w = ttk.Entry(top, width=26)
                w.insert(0, "" if v is None else str(v))
            w.grid(row=r, column=1, sticky="w", pady=4)
            widgets[key] = (w, kind)
        hint = {"time": "Times: e.g. 19:00 or 7:00 PM. Leave the three set-time fields blank for set numbers."}
        if any(k == "time" for _, _, k in self.fields):
            ttk.Label(top, text=hint["time"], style="Hint.TLabel", wraplength=380, justify="left").grid(
                row=len(self.fields), column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok():
            new = dict(row)
            try:
                for key, (w, kind) in widgets.items():
                    if kind in ("date", "date?"):
                        new[key] = w.get()
                    elif kind == "bool":
                        new[key] = bool(w.var.get())
                    elif kind in ("int", "int?"):
                        new[key] = as_int(w.get())
                    else:
                        new[key] = w.get().strip() or None
            except ValueError:
                messagebox.showerror("Not a number", "Numbers must be whole numbers.", parent=win)
                return
            if index is None:
                self.rows.append(new)
            else:
                self.rows[index] = new
            self.refresh()
            win.destroy()
        bar = ttk.Frame(top)
        bar.grid(row=len(self.fields) + 1, column=0, columnspan=2, pady=(14, 0), sticky="e")
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="OK", style="Accent.TButton", command=ok).pack(side="right", padx=(0, 6))
        win.grab_set()


class SettingsPanel:
    def __init__(self, parent, get_folder, get_palette=lambda: {}, on_save=None, on_dirty=None):
        self.get_folder = get_folder
        self.on_save = on_save                            # reloads the other tabs (they read the settings too)
        self.on_dirty = on_dirty                          # on_dirty(True/False): marks the tab "Settings •"
        self.saved, self.dirty = None, False              # what was last loaded or saved; differs from it now?
        PALETTE.update(get_palette())
        self.get_palette = get_palette
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))
        inner = ttk.Notebook(self.frame)
        inner.pack(fill="both", expand=True)

        # general: sections of settings, each with its help text on the right
        self.scroller = ScrollFrame(inner)
        self.scroller.recolor(PALETTE)
        inner.add(self.scroller, text="General")
        gen = self.scroller.inner
        gen.columnconfigure(2, weight=1)
        self.widgets = {}
        for r, (key, label, kind) in enumerate(GENERAL):
            if kind == "section":
                ttk.Label(gen, text=label, style="CardTitle.TLabel").grid(row=r, column=0, columnspan=3, sticky="w",
                                                                         pady=(18 if r else 4, 2))
                ttk.Separator(gen).grid(row=r, column=0, columnspan=3, sticky="sew")
                continue
            ttk.Label(gen, text=label, anchor="w").grid(row=r, column=0, sticky="nw", padx=(0, 16), pady=(9, 0))
            if kind in ("date", "date?"):
                w = DateField(gen, optional=kind == "date?")
            elif kind in MENUS:
                choices, _, width = MENUS[kind]
                w = ttk.Combobox(gen, values=list(choices.values()), state="readonly", width=width)
                w.bind("<<ComboboxSelected>>", lambda _: self.update_dependents())
            elif kind == "bool":
                var = tk.BooleanVar()
                w = ttk.Checkbutton(gen, variable=var, command=self.update_dependents)
                w.var = var
            else:
                w = ttk.Entry(gen, width={"text": 22, "wide": 34}.get(kind, 8))
                w.bind("<KeyRelease>", lambda _: self.update_dependents())
            w.grid(row=r, column=1, sticky="nw", pady=(6, 6))
            hint = ttk.Label(gen, text=HELP[key], anchor="w", justify="left", style="Hint.TLabel")
            hint.grid(row=r, column=2, sticky="new", padx=(20, 0), pady=(9, 6))
            hint.bind("<Configure>", lambda e, h=hint: h.configure(wraplength=max(e.width, 200)))
            self.widgets[key] = (w, kind)

        # lists
        self.show_days = ListEditor(inner, [
            ("weekday", "Day", 90), ("venue", "Venue", 110), ("sets", "Sets", 45), ("min_per_combo", "Min/combo", 75),
            ("first_set", "First set", 70), ("set_length", "Set (min)", 70), ("break", "Break", 55),
            ("supervision_preferred", "Prof. night", 80)],
            [("weekday", "Weekday", "weekday"), ("venue", "Venue", "text"), ("sets", "Sets per night", "int"),
             ("min_per_combo", "Min shows per combo here", "int"), ("first_set", "First set starts", "time"),
             ("set_length", "Set length (min)", "int?"), ("break", "Break between sets (min)", "int?"),
             ("supervision_preferred", "Supervised nights preferred here", "bool")],
            "Show day", sort_key=lambda r: WEEKDAYS.index(r["weekday"]) if r.get("weekday") in WEEKDAYS else 9)
        inner.add(self.show_days.frame, text="Show days")
        self.skip_dates = ListEditor(inner, [("date", "Date", 100), ("_weekday", "Day", 50), ("reason", "Reason", 400)],
                                     [("date", "Date", "date"), ("reason", "Reason (shown on the calendar)", "text")],
                                     "Date with no show", sort_key=lambda r: str(r.get("date") or ""))
        inner.add(self.skip_dates.frame, text="Skip dates")
        self.extra_dates = ListEditor(inner, [
            ("date", "Date", 100), ("_weekday", "Day", 50), ("venue", "Venue", 110), ("sets", "Sets", 45),
            ("reason", "Reason", 160), ("first_set", "First set", 70), ("set_length", "Set (min)", 70),
            ("break", "Break", 55)],
            [("date", "Date", "date"), ("venue", "Venue", "text"), ("sets", "Sets", "int"), ("reason", "Reason", "text"),
             ("first_set", "First set starts (blank = venue's usual)", "time"), ("set_length", "Set length (min)", "int?"),
             ("break", "Break between sets (min)", "int?")],
            "Extra show date", sort_key=lambda r: str(r.get("date") or ""))
        inner.add(self.extra_dates.frame, text="Extra dates")

        bar = ttk.Frame(self.frame)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="Save settings", style="Accent.TButton", command=self.save).pack(side="left")
        ttk.Button(bar, text="Undo changes", command=self.reload).pack(side="left", padx=6)
        self.unsaved = ttk.Label(bar, text="", style="Warn.TLabel")
        self.unsaved.pack(side="left", padx=(10, 0))
        self.status = ttk.Label(bar, text="", style="Hint.TLabel")
        self.status.pack(side="left", padx=10)
        if Calendar is None:
            self.status.configure(text="Tip: install the missing packages (Run tab) to pick dates from a calendar.")
        self.reload()
        self.watch()

    @property
    def path(self):
        return settings_path(self.get_folder())

    def reload(self):
        note = ""
        self.read_as = fingerprint(self.path)         # to tell, when saving, that another computer saved meanwhile
        if self.path.exists():
            try:
                data = read_data(self.path)
            except SettingsError as e:
                messagebox.showerror("Settings", str(e))
                data = dict(DEFAULTS)
        else:
            data, note = dict(DEFAULTS), "No settings yet: these are example values. Check them, then Save."
        for key, (w, kind) in self.widgets.items():
            v = data.get(key, DEFAULTS.get(key))
            if kind in ("date", "date?"):
                w.var.set(v or "")
            elif kind in MENUS:
                choices, default, _ = MENUS[kind]
                w.set(choices.get(v or default, choices[default]))
            elif kind == "bool":
                w.var.set(bool(v))
            else:
                w.delete(0, "end")
                w.insert(0, "" if v is None else str(v))
        self.show_days.set(data.get("show_days") or [])
        self.skip_dates.set(data.get("skip_dates") or [])
        self.extra_dates.set(data.get("extra_dates") or [])
        self.update_dependents()
        self.status.configure(text=note)
        self.saved = self.snapshot() if self.path.exists() else None    # no settings.json yet: unsaved
        self.check_unsaved()

    def update_dependents(self):
        """Greys out the settings that have no effect with the others as they are."""
        w = {key: widget for key, (widget, _) in self.widgets.items()}
        set_enabled(w["first_year_earliest_date"], w["use_first_year"].var.get())
        supervised = w["every_combo_supervised"].var.get()
        set_enabled(w["max_supervised_nights"], supervised)
        set_enabled(w["supervision_timing"], supervised)
        set_enabled(w["first_year_first_show_supervised"], supervised and w["use_first_year"].var.get())

    def recolor(self):
        PALETTE.update(self.get_palette())
        self.scroller.recolor(PALETTE)

    def collect(self):
        data = {}
        for key, (w, kind) in self.widgets.items():
            if kind in ("date", "date?"):
                data[key] = w.get()
            elif kind == "bool":
                data[key] = bool(w.var.get())
            elif kind in ("int", "int?"):
                data[key] = as_int(w.get())
            elif kind in MENUS:
                data[key] = next(k for k, shown in MENUS[kind][0].items() if shown == w.get())
            else:
                data[key] = w.get().strip() or None
        data["show_days"] = self.show_days.rows
        data["skip_dates"] = self.skip_dates.rows
        data["extra_dates"] = self.extra_dates.rows
        return data

    def snapshot(self):
        """The settings as shown, comparable with an earlier snapshot (None while a number field can't be read)."""
        try:
            return json.dumps(self.collect(), sort_keys=True, default=str)
        except ValueError:
            return None

    def check_unsaved(self):
        """Are there unsaved changes? Shows it next to the buttons and on the tab."""
        dirty = self.saved is None or self.snapshot() != self.saved
        if dirty != self.dirty:
            self.dirty = dirty
            self.unsaved.configure(text="\u25cf Unsaved changes: click Save settings" if dirty else "")
            if self.on_dirty:
                self.on_dirty(dirty)

    def watch(self):
        """Checks for unsaved changes every half second (started once)."""
        self.check_unsaved()
        self.frame.after(500, self.watch)

    def new_semester(self, new):
        """When the semester name changes and the old semester's schedule is in the data folder: offers to move its
        files into Archive/<semester> in the data folder. True = move, False = leave them, 'cancel' = don't save, None = no
        semester change (or nothing to move)."""
        if not self.path.exists():
            return None
        try:
            old, _ = validate(read_data(self.path))
        except SettingsError:
            return None
        if old.semester_name == new.semester_name:
            return None
        from outputs.excel_schedule import record_semester, schedule_semester, semester_paths
        folder = self.get_folder()
        if not semester_paths(folder):
            return None
        on_file = schedule_semester(folder / SCHEDULE_XLSX, old) if (folder / SCHEDULE_XLSX).exists() else None
        if on_file == new.semester_name:              # the schedule is already the new semester's
            return None
        if on_file == old.semester_name:              # an older file that only matched by its dates: say so in it,
            record_semester(folder / SCHEDULE_XLSX, on_file)   # or it would pass for the new semester's
        self.old_semester = on_file or old.semester_name
        answer = messagebox.askyesnocancel(
            "New semester", f"The semester changes from {old.semester_name} to {new.semester_name}.\n\n"
            f"Move {self.old_semester}'s files (Schedule.xlsx, the PDFs, contact lists, schedule backups) into "
            f"'Archive/{self.old_semester}' in the data folder?\n\nYes: move them (recommended).\nNo: leave them (the "
            f"app ignores a schedule from another semester; making the {new.semester_name} schedule moves them "
            "then).\nCancel: don't save.")
        return "cancel" if answer is None else answer

    def nights_ok(self, new):
        """When a schedule already exists and these settings change the nights, says that they only apply to the
        next schedule made: the current one keeps its own nights (the app reads them from Schedule.xlsx)."""
        if not (self.get_folder() / SCHEDULE_XLSX).exists() or not self.path.exists():
            return True
        try:
            old, _ = validate(read_data(self.path))
        except SettingsError:
            return True

        def nights(s):
            return {n.date: (n.venue, n.n_slots, n.first_set, n.set_length, n.break_minutes) for n in generate_nights(s)}
        before, after = nights(old), nights(new)
        added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
        changed = [d for d in before.keys() & after.keys() if before[d] != after[d]]
        if not (added or removed or changed):
            return True

        def dates(ds):
            return ", ".join(make_label(d) for d in ds[:8]) + (f" and {len(ds) - 8} more" if len(ds) > 8 else "")
        lines = ([f"\u2022 New nights: {dates(added)}."] if added else []) + (
            [f"\u2022 Nights removed: {dates(removed)}."] if removed else []) + (
            [f"\u2022 Sets or set times change on {len(changed)} night(s)."] if changed else [])
        return messagebox.askyesno(
            "For the next schedule", "These changes affect the show nights:\n\n" + "\n".join(lines)
            + "\n\nThey apply to the next schedule you make (Run tab, step 2). The current schedule keeps its own "
            "nights, shows and times: the app, the check and the PDF all follow Schedule.xlsx.\n\nSave?",
            icon="info", default="yes")

    def ask_to_save(self):
        """For leaving the tab, changing folder or closing with unsaved changes. True = go ahead, False = stay."""
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved settings", "The settings have changes that aren't saved.\n\nYes: save them now.\nNo: undo them."
            "\nCancel: go back to the Settings tab.", icon="warning")
        if answer is None:
            return False
        if answer:
            return self.save()
        self.reload()
        return True

    def save(self):
        try:
            data = self.collect()
        except ValueError:
            messagebox.showerror("Not a number", "The number fields must hold whole numbers (or be blank).")
            return False
        try:
            new, warnings = validate(data)
        except SettingsError as e:
            messagebox.showerror("Can't save yet", f"Please fix these first:\n\n{e}")
            return False
        if fingerprint(self.path) != self.read_as:
            answer = messagebox.askyesnocancel(
                "Settings changed elsewhere", f"{SETTINGS_FILE} was changed on another computer since this tab "
                "loaded it.\n\nYes: save yours anyway (replaces those changes).\nNo: load those settings instead "
                "(your unsaved changes here are lost).\nCancel: go back.", icon="warning", default="cancel")
            if answer is None:
                return False
            if not answer:
                self.reload()
                return False
        archive = self.new_semester(new)              # None: same semester; True / False: move the old files?
        if archive == "cancel" or (archive is None and not self.nights_ok(new)):
            return False
        save_data(self.path, data)
        self.read_as = fingerprint(self.path)
        if archive:
            from outputs.excel_schedule import archive_semester
            moved = archive_semester(self.get_folder(), self.old_semester)
            warnings = [f"{self.old_semester}'s files moved to 'Archive/{moved.name}'."] + warnings
        self.saved = self.snapshot()
        self.check_unsaved()
        self.status.configure(text=f"Saved to {SETTINGS_FILE}." + (f" Note: {' '.join(warnings)}" if warnings else ""),
                              style="Warn.TLabel" if warnings else "Hint.TLabel")
        if self.on_save:
            self.on_save()
        return True
