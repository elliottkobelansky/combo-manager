"""The Combos tab of scheduler_app.py: every accepted combo with its members' names, liaison, supervisor and shows;
correct a name, set each person's instrument, and export the combo list PDF.

Corrected names and instruments (per person per combo: someone can play piano in one combo and bass in another) are
kept in scheduler_data.json in the data folder (store.py), so the PDFs, the checks and the Swaps tab all use them.
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from app_config import input_files
from core.model import make_label
from inputs import EMAIL_RE, InputError, load_input, name_from_email
from outputs.excel_schedule import ScheduleFileError, read_schedule
from settings_file import SETTINGS_FILE, SettingsError, load_settings
from store import Store

INSTRUMENTS = ["Saxophone", "Trumpet", "Trombone", "Guitar", "Piano", "Bass", "Drums"]


class CombosPanel:
    def __init__(self, parent, get_folder, get_palette=lambda: {}, open_path=None, on_change=None):
        self.get_folder, self.get_palette, self.open_path = get_folder, get_palette, open_path
        self.on_change = on_change                        # reloads the other tabs after an email fix
        self.people = {}                                  # tree item id -> (combo name, email)
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Button(top, text="Reload", command=self.load).pack(side="left")
        ttk.Label(top, text="Search").pack(side="left", padx=(16, 6))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.fill())
        ttk.Entry(top, textvariable=self.search, width=28).pack(side="left")
        self.info = ttk.Label(top, text="", style="Hint.TLabel")
        self.info.pack(side="left", padx=12)

        hint = ttk.Label(self.frame, text="Click an Instrument cell (\u25be) to pick one; double-click a name to correct "
                                          "it, or an email to fix it (\u270e = corrected). All kept in scheduler_data.json in the data folder.", style="Hint.TLabel", justify="left")
        hint.pack(anchor="w", fill="x", pady=(8, 0))
        self.frame.bind("<Configure>", lambda e: hint.configure(wraplength=max(e.width - 20, 200)), add="+")
        table = ttk.Frame(self.frame)
        table.pack(fill="both", expand=True, pady=(6, 0))
        bar = ttk.Scrollbar(table, orient="vertical")
        bar.pack(side="right", fill="y")
        self.tree = ttk.Treeview(table, columns=("shows", "instrument", "also", "conflicts", "email"),
                                 yscrollcommand=bar.set)
        bar.configure(command=self.tree.yview)
        for col, text, width, stretch in (("#0", "Combo / person", 230, True), ("shows", "Shows", 210, True),
                                          ("instrument", "Instrument", 120, False), ("also", "Also in", 70, False),
                                          ("conflicts", "Conflicts", 75, False), ("email", "Email", 240, True)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, stretch=stretch, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.double_click)
        self.tree.bind("<Button-1>", self.click, add="+")

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Change name...", command=self.rename).pack(side="left")
        ttk.Button(bottom, text="Change email...", command=self.edit_email).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Set instrument...", command=self.edit_instrument).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Expand all", command=lambda: self.expand(True)).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Collapse all", command=lambda: self.expand(False)).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Export combo list PDF", style="Accent.TButton",
                   command=self.export_pdf).pack(side="right")

        self.data = None
        self.recolor()

    def load(self, quiet=False):
        """quiet: when loading by itself (app start, folder change), a problem is shown in the tab, not a pop-up."""
        folder = self.get_folder()
        try:
            settings, _ = load_settings(folder / SETTINGS_FILE)
            files = input_files(folder)
            inp = load_input(folder, settings, files["approvals"], files["conflicts"])
            self.store = Store(folder)
        except (SettingsError, InputError, ValueError) as e:
            if not quiet:
                messagebox.showerror("Can't load the combos", str(e))
            self.data = None
            self.tree.delete(*self.tree.get_children())
            self.info.configure(text="Not loaded: " + str(e).strip().splitlines()[0])
            return
        combos = {c.id: c for c in inp.combos}
        shows = {}
        if (folder / "Schedule.xlsx").exists():
            try:
                sets, _, supervised, _ = read_schedule(folder / "Schedule.xlsx", combos)
                for d, row in sets.items():
                    for k, c in row.items():
                        if c:
                            shows.setdefault(c, []).append(make_label(d) + ("*" if supervised and d in supervised else ""))
            except ScheduleFileError:
                pass
        self.data = dict(combos=combos, shows=shows, names=self.store.names, blocked=inp.blocked,
                         instruments=self.store.instruments(settings.semester_name), settings=settings)
        n_people = len({e for c in combos.values() for e in c.members})
        self.info.configure(text=f"{len(combos)} combos, {n_people} students." + (
            " * = supervised night." if shows else " (No Schedule.xlsx yet: shows aren't listed.)"))
        self.fill()

    def name(self, email):
        return self.data["names"].get(email) or name_from_email(email)

    def fill(self):
        if not self.data:
            return
        open_items = {self.tree.item(i, "text") for i in self.tree.get_children() if self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        self.people.clear()
        q = self.search.get().strip().lower()
        combos = self.data["combos"]
        member_of = {}
        for c in combos.values():
            for e in c.members:
                member_of.setdefault(e, []).append(c.name)
        band = 0
        for cid in sorted(combos, key=lambda c: combos[c].name):
            c = combos[cid]
            people = [c.liaison] + sorted(c.members - {c.liaison}, key=lambda e: self.name(e).lower())
            text = " ".join([c.name] + [self.name(e) + " " + e for e in people] + [c.professor]).lower()
            if q and q not in text:
                continue
            shows = ", ".join(self.data["shows"].get(cid, [])) + ("  · first year" if c.first_year else "")
            label = f"{c.name} ({self.name(c.liaison)})" if c.liaison else c.name
            band ^= 1                                 # alternate the background per combo
            shade = f"band{band}"
            item = self.tree.insert("", "end", text=label, values=(shows, "", "", "", ""),
                                    open=bool(q) or label in open_items, tags=("combo", shade))
            for e in people:
                others = [n.replace("Combo ", "") for n in member_of[e] if n != c.name]
                n_conf = len(self.data["blocked"].get(e, ()))
                pid = self.tree.insert(item, "end", text="    " + self.name(e),
                                       values=("", self.cell(self.data["instruments"].get((c.name, e), "")),
                                               ", ".join(others), n_conf or "", self.mail(e)), tags=(shade,))
                self.people[pid] = (c.name, e)
            if c.professor:
                pid = self.tree.insert(item, "end", text="    " + self.name(c.professor) + "  (supervisor)",
                                       values=("", "", "", "", self.mail(c.professor)), tags=(shade,))
                self.people[pid] = (None, c.professor)

    def mail(self, email):
        """The email as shown: marked when it was corrected in the app."""
        return f"\u270e {email}" if email in self.store.emails.values() else email

    @staticmethod
    def cell(instrument):
        """What an Instrument cell shows: a dropdown marker, so it's clear the cell can be clicked."""
        return f"\u25be  {instrument}" if instrument else "\u25be  choose"

    def recolor(self):
        p = self.get_palette()
        if not p:
            return
        from theme import ui_font
        self.tree.tag_configure("band0", background=p["panel"])
        self.tree.tag_configure("band1", background=p["band"])
        self.tree.tag_configure("combo", font=(ui_font(), 10, "bold"))

    def expand(self, yes):
        for i in self.tree.get_children():
            self.tree.item(i, open=yes)

    def click(self, event):
        """A click on a person's Instrument cell opens the dropdown there."""
        item, col = self.tree.identify_row(event.y), self.tree.identify_column(event.x)
        if item in self.people and col == "#2" and self.people[item][0]:
            self.tree.selection_set(item)
            self.tree.after_idle(lambda: self.edit_instrument(item))

    def double_click(self, event):
        col = self.tree.identify_column(event.x)
        if col == "#5":
            self.edit_email()
        elif col != "#2":
            self.rename()

    def edit_email(self):
        sel = self.tree.selection()
        email = self.people.get(sel[0], (None, None))[1] if sel else None
        if not email:
            messagebox.showinfo("Change an email", "Open a combo and pick a person (double-click their email works "
                                                   "too).")
            return
        new = simpledialog.askstring(
            "Change email", f"Correct email for {self.name(email)}:\n(The spreadsheets aren't changed; the fix is "
            "applied whenever they're read, to the combos and the conflicts.)", initialvalue=email, parent=self.frame)
        if new is None:
            return
        new = new.strip().lower()
        if not EMAIL_RE.fullmatch(new):
            messagebox.showerror("Change email", f"'{new}' doesn't look like an email address.")
            return
        if new == email:
            return
        try:
            self.store.set_email(email, new)
            self.store.save()
        except OSError as e:
            messagebox.showerror("Couldn't save the email", str(e))
            return
        self.load()
        if self.on_change:
            self.on_change()
        self.info.configure(text=f"Saved: {email} is now {new}" + (" (back to the original)" if new not in
                                                                   self.store.emails.values() else "") + ".")

    def edit_instrument(self, item=None):
        """Opens the instrument menu at the person's Instrument cell; picking an item saves it straight away."""
        sel = self.tree.selection()
        item = item or (sel[0] if sel else None)
        if item not in self.people or not self.people[item][0]:
            messagebox.showinfo("Set an instrument", "Open a combo and pick one of its members first.")
            return
        combo, email = self.people[item]
        current = self.data["instruments"].get((combo, email), "")
        self.tree.see(item)
        self.tree.update_idletasks()
        x, y, w, h = self.tree.bbox(item, "instrument") or (0, 0, 0, 0)
        p = self.get_palette() or {}
        menu = tk.Menu(self.tree, tearoff=0, background=p.get("panel"), foreground=p.get("text"),
                       activebackground=p.get("accent"), activeforeground=p.get("accent_text"),
                       selectcolor=p.get("accent"))
        choice = tk.StringVar(value=current if current in INSTRUMENTS else ("other" if current else ""))
        for name in INSTRUMENTS:
            menu.add_radiobutton(label=name, value=name, variable=choice,
                                 command=lambda n=name: self.set_instrument(item, n))
        menu.add_separator()
        menu.add_radiobutton(label=f"Other: {current}" if current and current not in INSTRUMENTS else "Other (type)...",
                             value="other", variable=choice, command=lambda: self.type_instrument(item))
        if current:
            menu.add_command(label="Clear", command=lambda: self.set_instrument(item, ""))
        self.menu = menu                              # (kept for tests)
        try:
            menu.tk_popup(self.tree.winfo_rootx() + x, self.tree.winfo_rooty() + y + h)
        finally:
            menu.grab_release()

    def type_instrument(self, item):
        combo, email = self.people[item]
        current = self.data["instruments"].get((combo, email), "")
        typed = simpledialog.askstring("Other instrument", f"Instrument for {self.name(email)} in {combo}:",
                                       initialvalue="" if current in INSTRUMENTS else current, parent=self.frame)
        if typed is not None:
            self.set_instrument(item, typed.strip())

    def set_instrument(self, item, value):
        combo, email = self.people[item]
        if value == self.data["instruments"].get((combo, email), ""):
            return
        try:
            self.store.set_instrument(self.data["settings"].semester_name, combo, email, value)
            self.store.save()
        except OSError as e:
            messagebox.showerror("Couldn't save the instrument", str(e))
            return
        if value:
            self.data["instruments"][(combo, email)] = value
        else:
            self.data["instruments"].pop((combo, email), None)
        self.tree.set(item, "instrument", self.cell(value))

    def rename(self):
        sel = self.tree.selection()
        email = self.people.get(sel[0], (None, None))[1] if sel else None
        if not email:
            messagebox.showinfo("Change a name", "Open a combo and pick a person (double-click works too).")
            return
        new = simpledialog.askstring("Change name", f"Name for {email}:", initialvalue=self.name(email),
                                     parent=self.frame)
        if not new or not new.strip() or new.strip() == self.name(email):
            return
        try:
            self.store.set_name(email, new.strip())
            self.store.save()
        except OSError as e:
            messagebox.showerror("Couldn't save the name", str(e))
            return
        self.fill()
        self.info.configure(text=f"Saved: {email} is now '{new.strip()}'. Export the combo list PDF again to "
                                 "update it.")

    def export_pdf(self):
        if not self.data:
            messagebox.showinfo("Combo list", "Nothing loaded yet.")
            return
        try:
            from outputs.combos_pdf import write_combos_pdf
        except ImportError:
            messagebox.showerror("Combo list", "The PDF needs the reportlab package: Run tab > Install missing packages.")
            return
        path = self.get_folder() / "Combos.pdf"
        combos = sorted(self.data["combos"].values(), key=lambda c: c.name)
        try:
            write_combos_pdf(path, combos, self.name, self.data["settings"].semester_name, self.data["instruments"])
        except PermissionError:
            messagebox.showerror("Combo list", f"Can't write {path.name}: it's open in another program. Close it and "
                                               "try again.")
            return
        self.info.configure(text=f"Wrote {path.name}.")
        if self.open_path:
            self.open_path(path)
