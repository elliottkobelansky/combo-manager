"""The Combos tab of scheduler_app.py: every accepted combo with its members' names, liaison, supervisor and shows;
correct a name, set each person's instrument, add or remove members, change the liaison, and export the combo list
PDF.

Corrected names, instruments (per person per combo: someone can play piano in one combo and bass in another) and
member changes are kept in scheduler_data.json in the data folder (store.py), so the PDFs, the checks and the Swaps
tab all use them. The approvals spreadsheet itself is never changed.
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from app_config import input_files
from core.model import make_label
from inputs import EMAIL_RE, EmailRules, InputError, load_input, name_from_email
from outputs.excel_schedule import ScheduleFileError, open_label, read_schedule, write_swap
from settings_file import SETTINGS_FILE, SettingsError, load_settings
from store import Store

INSTRUMENTS = ["Saxophone", "Trumpet", "Trombone", "Guitar", "Piano", "Bass", "Drums"]


class CombosPanel:
    def __init__(self, parent, get_folder, get_palette=lambda: {}, open_path=None, on_change=None,
                 get_swaps=lambda: None, after_schedule_change=None):
        self.get_folder, self.get_palette, self.open_path = get_folder, get_palette, open_path
        self.on_change = on_change                        # reloads the other tabs after an email fix
        self.get_swaps = get_swaps                        # the Swaps tab (its pending changes)
        self.after_schedule_change = after_schedule_change  # rebuilds Schedule.pdf after Schedule.xlsx changed
        self.people = {}                                  # tree item id -> (combo name, email); combo None = supervisor
        self.removed = {}                                 # tree item id -> (combo name, email) of a removed member
        self.combo_items = {}                             # tree item id -> combo name
        self.withdrawn_items = {}                         # tree item id -> Combo withdrawn in the app
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Button(top, text="Reload", command=self.load).pack(side="left")
        ttk.Button(top, text="Collapse all", command=lambda: self.expand(False)).pack(side="right")
        ttk.Button(top, text="Expand all", command=lambda: self.expand(True)).pack(side="right", padx=(0, 6))
        ttk.Label(top, text="Search").pack(side="left", padx=(16, 6))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.fill())
        ttk.Entry(top, textvariable=self.search, width=28).pack(side="left")
        self.info = ttk.Label(top, text="", style="Hint.TLabel")
        self.info.pack(side="left", padx=12)

        hint = ttk.Label(self.frame, text="Click an Instrument cell (\u25be) to pick one; double-click a name to correct "
                                          "it, or an email to fix it (\u270e = corrected). Right-click for more: add or "
                                          "remove members, change the liaison. All kept in scheduler_data.json in the "
                                          "data folder; the approvals spreadsheet isn't changed.",
                         style="Hint.TLabel", justify="left")
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
        for ev in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):        # right-click (Mac: also Ctrl-click)
            self.tree.bind(ev, self.context_menu)

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Add member...", command=self.add_member).pack(side="left")
        ttk.Button(bottom, text="Remove...", command=self.remove_member).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Make liaison", command=self.make_liaison).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Withdraw...", command=self.withdraw).pack(side="left", padx=(6, 0))
        ttk.Separator(bottom, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bottom, text="Rename...", command=self.rename).pack(side="left")
        ttk.Button(bottom, text="Fix email...", command=self.edit_email).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Instrument...", command=self.edit_instrument).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Export combo list", style="Accent.TButton",
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
        shows, sets, supervised = {}, {}, None
        if (folder / "Schedule.xlsx").exists():
            try:
                sets, _, supervised, _ = read_schedule(folder / "Schedule.xlsx", combos)
                for d, row in sets.items():
                    for k, c in row.items():
                        if c:
                            shows.setdefault(c, []).append(make_label(d) + ("*" if supervised and d in supervised else ""))
            except ScheduleFileError:
                pass
        self.data = dict(combos=combos, shows=shows, sets=sets, supervised=supervised or set(),
                         withdrawn={c.name: c for c in inp.withdrawn}, names=self.store.names, blocked=inp.blocked,
                         instruments=self.store.instruments(settings.semester_name), settings=settings,
                         rules=EmailRules.from_settings(settings))
        n_people = len({e for c in combos.values() for e in c.members})
        self.info.configure(text=f"{len(combos)} combos, {n_people} students." + (
            " * = supervised night." if shows else " (No Schedule.xlsx yet: shows aren't listed.)"))
        self.fill()

    def name(self, email):
        return self.data["names"].get(email) or name_from_email(email)

    def fill(self):
        if not self.data:
            return
        open_items = {self.tree_key(self.tree.item(i, "text")) for i in self.tree.get_children()
                      if self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        self.people.clear()
        self.removed.clear()
        self.combo_items.clear()
        self.withdrawn_items.clear()
        sem, few = self.data["settings"].semester_name, self.data["settings"].min_members_per_combo
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
            if few and len(c.members) < few:
                label += f"   \u26a0 {len(c.members)} member{'s' if len(c.members) != 1 else ''}"
            band ^= 1                                 # alternate the background per combo
            shade = f"band{band}"
            item = self.tree.insert("", "end", text=label, values=(shows, "", "", "", ""),
                                    open=bool(q) or self.tree_key(label) in open_items, tags=("combo", shade))
            self.combo_items[item] = cid
            changes = self.store.member_changes(sem, c.ref)
            for e in people:
                others = [n.replace("Combo ", "") for n in member_of[e] if n != c.name]
                n_conf = len(self.data["blocked"].get(e, ()))
                marks = (["liaison"] if e == c.liaison else []) + (["added in the app"] if e in changes["add"] else [])
                pid = self.tree.insert(item, "end", text="    " + self.name(e) + "".join(f"  \u00b7 {m}" for m in marks),
                                       values=("", self.cell(self.data["instruments"].get((c.name, e), "")),
                                               ", ".join(others), n_conf or "", self.mail(e)), tags=(shade,))
                self.people[pid] = (c.name, e)
            for e in changes["remove"]:
                pid = self.tree.insert(item, "end", text=f"    {self.name(e)}  \u00b7 removed (right-click to put back)",
                                       values=("", "", "", "", e), tags=(shade, "removed"))
                self.removed[pid] = (c.name, e)
        for c in sorted(self.data["withdrawn"].values(), key=lambda c: c.name):
            label = (f"{c.name} ({self.name(c.liaison)})" if c.liaison else c.name) + "  \u00b7 withdrawn"
            if q and q not in (label + " " + " ".join(c.members)).lower():
                continue
            item = self.tree.insert("", "end", text=label, values=("right-click to put back", "", "", "", ""),
                                    tags=("removed",))
            self.withdrawn_items[item] = c
            if c.professor:
                pid = self.tree.insert(item, "end", text="    " + self.name(c.professor) + "  (supervisor)",
                                       values=("", "", "", "", self.mail(c.professor)), tags=(shade,))
                self.people[pid] = (None, c.professor)

    @staticmethod
    def tree_key(label):
        """'Combo 05 (Ana Ruiz)   ⚠ 3 members' -> 'Combo 05': stays the same when the label changes."""
        return label.split(" (")[0].split("   ")[0]

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
        self.tree.tag_configure("removed", foreground=p["muted"], font=(ui_font(), 10, "italic"))

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
        if not self.change_store(lambda s: s.set_email(email, new)):
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
        if not self.change_store(lambda s: s.set_instrument(self.data["settings"].semester_name, combo, email, value)):
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
        if not self.change_store(lambda s: s.set_name(email, new.strip())):
            return
        self.fill()
        self.info.configure(text=f"Saved: {email} is now '{new.strip()}'. Export the combo list PDF again to "
                                 "update it.")

    # ------------------------------------------------------------ members and liaison
    def selected(self):
        """(kind, combo, email) for the selected row: kind is 'person', 'removed', 'supervisor' or 'combo'."""
        sel = self.tree.selection()
        if not sel or not self.data:
            return None, None, None
        item = sel[0]
        if item in self.withdrawn_items:
            return "withdrawn", self.withdrawn_items[item], None
        if item in self.combo_items:
            return "combo", self.data["combos"][self.combo_items[item]], None
        if item in self.removed:
            name, email = self.removed[item]
            return "removed", self.data["combos"][name], email
        if item in self.people:
            name, email = self.people[item]
            if name is None:
                return "supervisor", self.data["combos"][self.combo_items[self.tree.parent(item)]], email
            return "person", self.data["combos"][name], email
        return None, None, None

    def context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self.tree.selection_set(item)
        kind, combo, email = self.selected()
        p = self.get_palette() or {}
        menu = tk.Menu(self.tree, tearoff=0, background=p.get("panel"), foreground=p.get("text"),
                       activebackground=p.get("accent"), activeforeground=p.get("accent_text"))
        if kind == "person":
            if email != combo.liaison:
                menu.add_command(label="Make liaison", command=self.make_liaison)
            menu.add_command(label="Change name...", command=self.rename)
            menu.add_command(label="Change email...", command=self.edit_email)
            menu.add_command(label="Set instrument...", command=lambda: self.edit_instrument(item))
            menu.add_separator()
            menu.add_command(label=f"Remove from {combo.name}...", command=self.remove_member)
        elif kind == "removed":
            menu.add_command(label=f"Put back in {combo.name}", command=self.restore_member)
        elif kind == "supervisor":
            menu.add_command(label="Change name...", command=self.rename)
            menu.add_command(label="Change email...", command=self.edit_email)
        if kind == "withdrawn":
            menu.add_command(label=f"Put back {combo.name}", command=self.put_back)
        else:
            if kind != "combo":
                menu.add_separator()
            menu.add_command(label=f"Add a member to {combo.name}...", command=self.add_member)
            menu.add_separator()
            menu.add_command(label=f"Withdraw {combo.name}...", command=self.withdraw)
        self.menu = menu                              # (kept for tests)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def change_store(self, change):
        """Re-reads scheduler_data.json, applies change(store) and saves it. Reading it again first means an edit
        here never overwrites what was saved since this tab loaded (e.g. numbers for combos approved meanwhile,
        given out by a check or the Swaps tab)."""
        try:
            store = Store(self.get_folder())
            change(store)
            store.save()
        except (OSError, ValueError) as e:
            messagebox.showerror("Couldn't save", str(e))
            return False
        self.store = store
        if self.data:
            self.data["names"] = store.names              # names are shown from here
        return True

    def save_changes(self, change, message):
        """Applies change(store) to scheduler_data.json, reloads this tab and the others, and says what changed."""
        if not self.change_store(change):
            return False
        self.load()
        if self.on_change:
            self.on_change()
        self.info.configure(text=message)
        return True

    def add_member(self):
        kind, combo, _ = self.selected()
        if not combo:
            messagebox.showinfo("Add a member", "Pick a combo (or one of its members) first.")
            return
        AddMemberDialog(self, combo)

    def remove_member(self):
        kind, combo, email = self.selected()
        if kind != "person":
            messagebox.showinfo("Remove a member", "Open a combo and pick the member to remove.")
            return
        sem, rest = self.data["settings"].semester_name, sorted(combo.members - {email})
        new_liaison = None
        if email == combo.liaison and rest:
            new_liaison = self.choose_liaison(combo, rest, f"{self.name(email)} is the liaison of {combo.name}. "
                                                           "Who takes over?")
            if not new_liaison:
                return
        few, warn = self.data["settings"].min_members_per_combo, ""
        if not rest:
            warn = f"\n\n{combo.name} will have no members left."
        elif few and len(rest) < few:
            warn = f"\n\n{combo.name} will have {len(rest)} member{'s' if len(rest) != 1 else ''}, fewer than {few}."
        if not messagebox.askyesno("Remove a member", f"Remove {self.name(email)} from {combo.name}?{warn}\n\n"
                                   "The approvals spreadsheet isn't changed; you can put them back here."):
            return
        def change(s):
            s.remove_member(sem, combo.ref, email)
            if new_liaison:
                s.set_liaison(sem, combo.ref, new_liaison)
        self.save_changes(change, f"Removed {self.name(email)} from {combo.name}"
                          + (f"; {self.name(new_liaison)} is the liaison now" if new_liaison else "") + ".")

    def restore_member(self):
        kind, combo, email = self.selected()
        if kind != "removed":
            return
        self.save_changes(lambda s: s.add_member(self.data["settings"].semester_name, combo.ref, email),
                          f"{self.name(email)} is back in {combo.name}.")

    def make_liaison(self):
        kind, combo, email = self.selected()
        if kind == "combo" and combo.members:                     # a combo picked: choose from its members
            email = self.choose_liaison(combo, sorted(combo.members), f"Liaison of {combo.name}:", combo.liaison)
        elif kind != "person":
            messagebox.showinfo("Make liaison", "Open a combo and pick the member who should be its liaison.")
            return
        if not email or email == combo.liaison:
            return
        self.save_changes(lambda s: s.set_liaison(self.data["settings"].semester_name, combo.ref, email),
                          f"{self.name(email)} is now the liaison of {combo.name}.")

    def withdraw(self):
        """Withdraws the selected combo (kept in scheduler_data.json; its number stays reserved). If the schedule is
        out, its sets become open in Schedule.xlsx (backup first) and Schedule.pdf is rebuilt."""
        kind, combo, _ = self.selected()
        if kind in (None, "withdrawn"):
            messagebox.showinfo("Withdraw a combo", "Pick the combo to withdraw (or one of its members).")
            return
        swaps = self.get_swaps()
        if swaps and swaps.pending:
            messagebox.showinfo("Withdraw a combo", f"There are {len(swaps.pending)} unsaved swap change(s). Confirm "
                                                   "or discard them first (Swaps tab), then withdraw.")
            return
        shows = sorted((d, k) for d, row in self.data["sets"].items() for k, c in row.items() if c == combo.id)
        sup = [d for d, _ in shows if d in self.data["supervised"]]
        text = f"Withdraw {combo.name}? It won't be scheduled; its number stays reserved (the numbering keeps a gap)."
        if shows:
            text += ("\n\nIts shows: " + ", ".join(f"{make_label(d)} (set {k})" for d, k in shows) + ". These sets "
                     "become OPEN in Schedule.xlsx (a backup is kept): volunteers can claim them, or give one to a "
                     "combo in the Schedule tab (who could take it).")
        if sup:
            text += ("\n\n\u26a0 " + ", ".join(make_label(d) for d in sup) + (" is a supervised night" if len(sup) == 1
                     else " are supervised nights") + ", which must be full: give that set to another combo.")
        text += "\n\nThe approvals spreadsheet isn't changed; you can put the combo back here."
        if not messagebox.askyesno("Withdraw a combo", text, icon="warning"):
            return
        folder, settings = self.get_folder(), self.data["settings"]
        backup = None
        if shows:
            try:
                backup = write_swap(folder / "Schedule.xlsx", {s: None for s in shows}, self.data["combos"],
                                    open_label(settings))
            except ScheduleFileError as e:
                messagebox.showerror("Couldn't withdraw", str(e))
                return
        if not self.save_changes(lambda s: s.set_withdrawn(settings.semester_name, combo.ref, True),
                                 f"Withdrew {combo.name}." + (f" {len(shows)} set(s) opened." if shows else "")):
            return
        if shows and self.after_schedule_change:
            self.after_schedule_change(f"Withdrew {combo.name}: opened " + ", ".join(
                f"{make_label(d)} set {k}" for d, k in shows) + f". Backup of the old file: {backup}\n")

    def put_back(self):
        kind, combo, _ = self.selected()
        if kind != "withdrawn":
            return
        self.save_changes(lambda s: s.set_withdrawn(self.data["settings"].semester_name, combo.ref, False),
                          f"{combo.name} is back" + (" with no shows (its sets were opened when it was withdrawn): it "
                                                     "can claim open sets in the Swaps tab." if self.data["sets"] else "."))

    def choose_liaison(self, combo, emails, question, current=None):
        """A small window listing the members; returns the chosen email, or None when cancelled."""
        win = tk.Toplevel(self.frame)
        win.title("Choose the liaison")
        win.transient(self.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=16)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=question, wraplength=380, justify="left").pack(anchor="w", pady=(0, 10))
        choice = tk.StringVar(value=current if current in emails else emails[0])
        for e in sorted(emails, key=lambda e: self.name(e).lower()):
            ttk.Radiobutton(box, text=f"{self.name(e)}   ({e})", value=e, variable=choice).pack(anchor="w", pady=2)
        picked = []
        bar = ttk.Frame(box)
        bar.pack(fill="x", pady=(14, 0))
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="OK", style="Accent.TButton",
                   command=lambda: (picked.append(choice.get()), win.destroy())).pack(side="right", padx=(0, 6))
        win.grab_set()
        self.frame.wait_window(win)
        return picked[0] if picked else None

    def known_people(self):
        """{email: name} of everyone the scheduler knows: combo members, conflict-form senders, corrected names."""
        emails = {e for c in self.data["combos"].values() for e in c.members} | set(self.data["blocked"]) | set(
            self.data["names"])
        return {e: self.name(e) for e in emails if EMAIL_RE.fullmatch(e)}

    def warnings_for(self, combo, email):
        """What adding email to combo would clash with: other combos, and its conflicts on this combo's shows."""
        out = []
        others = sorted(c.name for c in self.data["combos"].values() if email in c.members and c.name != combo.name)
        if others:
            out.append(f"Also in {', '.join(others)}.")
        blocked = self.data["blocked"].get(email, set())
        for d, row in sorted(self.data["sets"].items()):
            if combo.id not in row.values():
                continue
            if d in blocked:
                out.append(f"Has a conflict on {make_label(d)}, when {combo.name} plays.")
            twice = sorted(c for c in row.values() if c and c != combo.id and email in self.data["combos"][c].members)
            if twice:
                out.append(f"Would play twice on {make_label(d)} (also with {', '.join(twice)}).")
        return out

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


class AddMemberDialog:
    """Adds a member to a combo: find someone the scheduler already knows, or type a new email (the name is guessed
    from it and can be changed); the instrument is optional."""

    def __init__(self, panel, combo):
        self.panel, self.combo = panel, combo
        self.known = panel.known_people()
        self.choices = sorted(f"{name}  <{e}>" for e, name in self.known.items() if e not in combo.members)
        self.name_typed = False
        win = self.win = tk.Toplevel(panel.frame)
        win.title(f"Add a member to {combo.name}")
        win.transient(panel.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=16)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=f"Add a member to {combo.name}", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.find = ttk.Combobox(box, values=self.choices, width=44)
        self.email, self.name = ttk.Entry(box, width=46), ttk.Entry(box, width=46)
        self.instrument = ttk.Combobox(box, values=INSTRUMENTS, width=44)
        rows = [("Find someone", self.find, "Type part of a name or email, then pick from the list."),
                ("Email", self.email, "Someone new: type their email."),
                ("Name", self.name, "Guessed from the email; change it if needed."),
                ("Instrument", self.instrument, "Optional.")]
        for r, (label, widget, hint) in enumerate(rows, start=1):
            ttk.Label(box, text=label).grid(row=2 * r - 1, column=0, sticky="w", padx=(0, 12), pady=(6, 0))
            widget.grid(row=2 * r - 1, column=1, sticky="w", pady=(6, 0))
            ttk.Label(box, text=hint, style="Hint.TLabel").grid(row=2 * r, column=1, sticky="w")
        self.warn = ttk.Label(box, text="", wraplength=420, justify="left", foreground=panel.get_palette().get("warn"))
        self.warn.grid(row=9, column=0, columnspan=2, sticky="w", pady=(10, 0))
        bar = ttk.Frame(box)
        bar.grid(row=10, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Add", style="Accent.TButton", command=self.add).pack(side="right", padx=(0, 6))

        self.find.bind("<KeyRelease>", self.filter)
        self.find.bind("<<ComboboxSelected>>", self.picked)
        self.email.bind("<KeyRelease>", lambda _: self.email_changed())
        self.name.bind("<Key>", lambda _: setattr(self, "name_typed", True))
        self.find.focus_set()
        win.grab_set()

    def filter(self, event=None):
        """Narrows the list to what's typed; typing a whole email fills in the Email field too."""
        q = self.find.get().strip().lower()
        self.find.configure(values=[c for c in self.choices if q in c.lower()] if q else self.choices)
        if EMAIL_RE.fullmatch(q):
            self.set_email(q)

    def picked(self, _=None):
        text = self.find.get()
        if "<" in text:
            self.set_email(text.rsplit("<", 1)[1].rstrip(">"))
            self.name_typed = False
            self.email_changed()

    def set_email(self, email):
        self.email.delete(0, "end")
        self.email.insert(0, email)
        self.email_changed()

    def clean_email(self):
        e = self.email.get().strip()
        return self.panel.store.fix_email(self.panel.data["rules"].norm(e)) if e else ""

    def email_changed(self):
        """Fills in the name (unless one was typed) and shows what the addition would clash with."""
        e = self.clean_email()
        if not self.name_typed:
            self.name.delete(0, "end")
            if EMAIL_RE.fullmatch(e):
                self.name.insert(0, self.known.get(e) or name_from_email(e))
        warnings = []
        if EMAIL_RE.fullmatch(e):
            if e in self.combo.members:
                warnings = [f"Already in {self.combo.name}."]
            else:
                warnings = self.panel.warnings_for(self.combo, e)
        self.warn.configure(text="\n".join(warnings))

    def add(self):
        e, panel = self.clean_email(), self.panel
        if not EMAIL_RE.fullmatch(e):
            messagebox.showerror("Add a member", "Type an email address (or pick someone from the list).",
                                 parent=self.win)
            return
        if e in self.combo.members:
            messagebox.showinfo("Add a member", f"{panel.name(e)} is already in {self.combo.name}.", parent=self.win)
            return
        sem, name, instrument = panel.data["settings"].semester_name, self.name.get().strip(), self.instrument.get().strip()

        def change(store):
            store.add_member(sem, self.combo.ref, e)
            if name and name != (panel.data["names"].get(e) or name_from_email(e)):
                store.set_name(e, name)
            if instrument:
                store.set_instrument(sem, self.combo.name, e, instrument)
        clashes = panel.warnings_for(self.combo, e)
        self.win.destroy()
        panel.save_changes(change, f"Added {name or panel.name(e)} to {self.combo.name}."
                           + (f" Note: {' '.join(clashes)}" if clashes else ""))
