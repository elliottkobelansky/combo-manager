"""The Combos tab of scheduler_app.py: every accepted combo with its members' names, liaison, supervisor and shows;
correct a name, set each person's instrument, add or remove members, change the liaison, and export the combo list
PDF.

Corrected names, instruments (per person per combo: someone can play piano in one combo and bass in another) and
member changes are kept in scheduler_data.json in the data folder (store.py), so the PDFs, the checks and the Swaps
tab all use them. The approvals spreadsheet itself is never changed.
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_log
from app_config import input_files
from core.model import make_label
from data_folder import COMBOS_PDF, COMBOS_XLSX, settings_path
from inputs import EMAIL_RE, EmailRules, InputError, load_input, name_from_email
from schedule_file import ScheduleFileError, has_schedule, load as load_schedule, open_sets_of
from settings_file import SettingsError, load_settings
from store import Store
from theme import popup, scrolled_tree
from util import INSTRUMENTS, by_instrument



class CombosPanel:
    def __init__(self, parent, get_folder, get_palette=lambda: {}, open_path=None, on_change=None,
                 get_swaps=lambda: None, after_schedule_change=None):
        self.get_folder, self.get_palette, self.open_path = get_folder, get_palette, open_path
        self.on_change = on_change                        # reloads the other tabs after an email fix
        self.get_swaps = get_swaps                        # the Swaps tab (its pending changes)
        self.after_schedule_change = after_schedule_change  # rebuilds the PDF and xlsx after the schedule changed
        self.people = {}                                  # tree item id -> (combo name, email); combo None = supervisor
        self.removed = {}                                 # tree item id -> (combo name, email) of a removed member
        self.combo_items = {}                             # tree item id -> combo name
        self.withdrawn_items = {}                         # tree item id -> Combo withdrawn in the app
        self.pending_items = {}                           # tree item id -> Combo waiting for a decision
        self.pending = []                                 # edits not saved yet (queue): shown as if done
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Button(top, text="Reload", command=self.reload).pack(side="left")
        ttk.Label(top, text="Search").pack(side="left", padx=(16, 6))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.fill())
        ttk.Entry(top, textvariable=self.search, width=28).pack(side="left")
        self.info = ttk.Label(top, text="", style="Hint.TLabel")
        self.info.pack(side="left", padx=12)

        hint = ttk.Label(self.frame, text="Click an instrument to change it; double-click a name or email to fix it. "
                                          "Right-click (or Actions) for everything else. Nothing is saved until "
                                          "Confirm changes.",
                         style="Hint.TLabel", justify="left")
        hint.pack(anchor="w", fill="x", pady=(8, 0))
        self.frame.bind("<Configure>", lambda e: hint.configure(wraplength=max(e.width - 20, 200)), add="+")
        table, self.tree = scrolled_tree(self.frame, [
            ("#0", "Combo / person", 330, True), ("shows", "Shows", 210, True), ("instrument", "Instrument", 120, False),
            ("also", "Also in", 70, False), ("conflicts", "Conflicts", 75, False), ("email", "Email", 200, True)])
        table.pack(fill="both", expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", self.double_click)
        self.tree.bind("<Button-1>", self.click, add="+")
        for ev in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):        # right-click (Mac: also Ctrl-click)
            self.tree.bind(ev, self.context_menu)

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        # unsaved changes: a bar shown only while there are some (like the Schedule tab's), saved all at once
        self.pending_box = ttk.Frame(self.frame, style="Card.TFrame", padding=(12, 8))
        self.pending_title = ttk.Label(self.pending_box, text="", style="CardTitle.TLabel")
        self.pending_title.pack(side="left")
        ttk.Button(self.pending_box, text="Discard all", command=self.discard_all).pack(side="right")
        ttk.Button(self.pending_box, text="Undo last", command=self.undo_last).pack(side="right", padx=6)
        ttk.Button(self.pending_box, text="Confirm changes", style="Accent.TButton",
                   command=self.confirm).pack(side="right")
        self.bottom = bottom
        ttk.Button(bottom, text="Expand all", command=lambda: self.expand(True)).pack(side="left")
        ttk.Button(bottom, text="Collapse all", command=lambda: self.expand(False)).pack(side="left", padx=6)
        self.actions = ttk.Button(bottom, text="Actions \u25be", command=self.actions_menu)   # = the right-click menu
        self.actions.pack(side="left", padx=(6, 0))
        self.actions_hint = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.actions_hint.pack(side="left", padx=10)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_actions_hint(), add="+")
        ttk.Button(bottom, text="Export Excel", style="Accent.TButton",
                   command=self.export_xlsx).pack(side="right")
        ttk.Button(bottom, text="Export PDF", style="Accent.TButton",
                   command=self.export_pdf).pack(side="right", padx=(0, 6))

        self.data = None
        self.recolor()

    def load(self, quiet=False):
        """quiet: when loading by itself (app start, folder change), a problem is shown in the tab, not a pop-up.
        Pending edits are applied on top of what's saved (a preview: nothing is written)."""
        folder = self.get_folder()
        try:
            settings, _ = load_settings(settings_path(folder))
            files = input_files(folder)
            store = Store(folder)
            if self.pending:
                for p in self.pending:
                    p["change"](store)
                store.save = lambda: None                 # a preview: Confirm changes saves
            inp = load_input(folder, settings, files["approvals"], files["conflicts"], store=store)
            self.store = store
        except (SettingsError, InputError, ValueError) as e:
            if not quiet:
                messagebox.showerror("Can't load the combos", str(e))
            self.data = None
            self.tree.delete(*self.tree.get_children())
            self.info.configure(text="Not loaded: " + str(e).strip().splitlines()[0])
            return
        combos = {c.id: c for c in inp.combos}
        shows, sets, supervised, nights = {}, {}, None, None
        if has_schedule(folder):
            try:
                sched = load_schedule(folder, combos, settings)
                sets, supervised, nights = sched.sets, sched.supervised, sched.nights
                for d, row in sets.items():
                    for k, c in row.items():
                        if c:
                            shows.setdefault(c, []).append(make_label(d) + ("*" if supervised and d in supervised else ""))
            except ScheduleFileError:
                pass
        if nights is None:                            # no schedule yet: the nights the settings would give
            from core import generate_nights
            nights = generate_nights(settings)
        self.data = dict(combos=combos, shows=shows, sets=sets, supervised=supervised or set(), nights=nights,
                         withdrawn={c.name: c for c in inp.withdrawn}, pending=inp.pending, names=self.store.names,
                         blocked=inp.blocked,
                         instruments=self.store.instruments(settings.semester_name, combos.values()), settings=settings,
                         rules=EmailRules.from_settings(settings))
        n_people = len({e for c in combos.values() for e in c.members})
        self.info.configure(text=f"{len(combos)} combos, {n_people} students." + (
            " * = supervised night." if shows else " (No schedule yet: shows aren't listed.)"))
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
        self.pending_items.clear()
        sem, few = self.data["settings"].semester_name, self.data["settings"].min_members_per_combo
        q = self.search.get().strip().lower()
        combos = self.data["combos"]
        touched = {n for p in self.pending for n in p["combos"]}   # combos with changes not saved yet
        member_of = {}
        for c in combos.values():
            for e in c.members:
                member_of.setdefault(e, []).append(c.name)
        band = 0
        for cid in sorted(combos, key=lambda c: combos[c].name):
            c = combos[cid]
            people = self.member_order(c)
            text = " ".join([c.name] + [self.name(e) + " " + e for e in people] + [c.professor]).lower()
            if q and q not in text:
                continue
            shows = ", ".join(self.data["shows"].get(cid, []))
            label = (f"{c.name} ({self.name(c.liaison)})" if c.liaison else c.name) + ("  \u00b7 first year" if c.first_year
                                                                                     else "")
            if few and len(c.members) < few:
                label += f"   \u26a0 {len(c.members)} member{'s' if len(c.members) != 1 else ''}"
            band ^= 1                                 # alternate the background per combo
            shade = f"band{band}"
            item = self.tree.insert("", "end", text=label, values=(shows, "", "", "", ""),
                                    open=bool(q) or self.tree_key(label) in open_items, tags=("combo", shade))
            if c.name in touched:
                self.mark(item)
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
                pid = self.tree.insert(item, "end", text=f"    {self.name(e)}  \u00b7 removed (Actions: put back)",
                                       values=("", "", "", "", e), tags=(shade, "removed"))
                self.removed[pid] = (c.name, e)
            if c.professor:
                pid = self.tree.insert(item, "end", text="    " + self.name(c.professor) + "  (supervisor)",
                                       values=("", "", "", "", self.mail(c.professor)), tags=(shade,))
                self.people[pid] = (None, c.professor)
        for c in self.data["pending"]:                    # submitted, no decision yet: shown, not editable
            who = self.name(c.liaison) if c.liaison else "no liaison"
            label = f"Waiting for a decision \u00b7 {who}"
            if q and q not in (label + " " + " ".join(c.members)).lower():
                continue
            item = self.tree.insert("", "end", text=label, values=("approve or reject it in Outlook", "", "",
                                                                   "", ""),
                                    open=bool(q) or self.tree_key(label) in open_items, tags=("removed",))
            self.pending_items[item] = c
            for e in self.member_order(c) + ([c.professor] if c.professor else []):
                pid = self.tree.insert(item, "end", text="    " + self.name(e) + ("  (supervisor)" if e == c.professor
                                                                                 else ""),
                                       values=("", "", "", len(self.data["blocked"].get(e, ())) or "", e),
                                       tags=("removed",))
                self.pending_items[pid] = c
        for c in sorted(self.data["withdrawn"].values(), key=lambda c: c.name):
            label = (f"{c.name} ({self.name(c.liaison)})" if c.liaison else c.name) + "  \u00b7 withdrawn" + (
                self.UNSAVED if c.name in touched else "")
            if q and q not in (label + " " + " ".join(c.members)).lower():
                continue
            item = self.tree.insert("", "end", text=label, values=("Actions: put back", "", "", "", ""),
                                    open=bool(q) or self.tree_key(label) in open_items, tags=("removed",))
            self.withdrawn_items[item] = c
            people = self.member_order(c)
            for e in people:
                instrument = self.data["instruments"].get((c.name, e), "")
                pid = self.tree.insert(item, "end", text="    " + self.name(e) + ("  \u00b7 liaison" if e == c.liaison
                                                                                 else ""),
                                       values=("", instrument, "", "", e), tags=("removed",))
                self.withdrawn_items[pid] = c          # right-click on a member: put the combo back
            if c.professor:
                pid = self.tree.insert(item, "end", text="    " + self.name(c.professor) + "  (supervisor)",
                                       values=("", "", "", "", c.professor), tags=("removed",))
                self.withdrawn_items[pid] = c

    UNSAVED = "   \u25cf unsaved changes"

    def mark(self, item):
        """Marks a combo's row: it has changes not saved yet."""
        text = self.tree.item(item, "text")
        if not text.endswith(self.UNSAVED):
            self.tree.item(item, text=text + self.UNSAVED, tags=tuple(self.tree.item(item, "tags")) + ("pending",))

    def member_order(self, c):
        """The combo's members, by instrument (see util.INSTRUMENTS)."""
        return by_instrument(c.members, lambda e: self.data["instruments"].get((c.name, e), ""), self.name)

    @staticmethod
    def tree_key(label):
        """'Combo 05 (Ana Ruiz)  · first year   ⚠ 3 members' -> 'Combo 05': stays the same when the label changes."""
        return label.split(" (")[0].split("  ")[0]

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
        from theme import size, size_columns, ui_font
        self.tree.tag_configure("band0", background=p["panel"])
        self.tree.tag_configure("band1", background=p["band"])
        size_columns(self.tree)
        self.tree.tag_configure("combo", font=(ui_font(), size(10), "bold"))
        self.tree.tag_configure("removed", foreground=p["muted"], font=(ui_font(), size(10), "italic"))
        self.tree.tag_configure("pending", foreground=p["accent"])

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
        back = new in self.store.emails and self.store.emails.get(new) == email   # typing an original back
        self.queue(lambda s: s.set_email(email, new), f"{email} becomes {new}" + (" (back to the original)" if back
                                                                                  else "") + ".",
                   combo=self.combos_of(email))

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
        choice = tk.StringVar(value=current if current in INSTRUMENTS else ("other" if current else "none"))
        # the same order members are listed in: Other, the instruments, no instrument
        menu.add_radiobutton(label=f"Other: {current}" if current and current not in INSTRUMENTS else "Other (type)...",
                             value="other", variable=choice, command=lambda: self.type_instrument(item))
        menu.add_separator()
        for name in INSTRUMENTS:
            menu.add_radiobutton(label=name, value=name, variable=choice,
                                 command=lambda n=name: self.set_instrument(item, n))
        menu.add_separator()
        menu.add_radiobutton(label="No instrument", value="none", variable=choice,
                             command=lambda: self.set_instrument(item, ""))
        self.menu = menu                              # (kept for tests)
        popup(menu, self.tree.winfo_rootx() + x, self.tree.winfo_rooty() + y + h)

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
        sem = self.data["settings"].semester_name
        self.queue(lambda s: s.set_instrument(sem, combo, email, value),
                   f"{self.name(email)} plays {value or 'no instrument'} in {combo}.", combo=combo, view="none")
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
        old = self.name(email)
        self.queue(lambda s: s.set_name(email, new.strip()), f"{old} is now called '{new.strip()}'.", view="fill",
                   combo=self.combos_of(email))

    def combos_of(self, email):
        """The names of the combos email is in (or supervises), withdrawn ones too."""
        every = list(self.data["combos"].values()) + list(self.data["withdrawn"].values())
        return [c.name for c in every if email in c.members or email == c.professor]

    # ------------------------------------------------------------ members and liaison
    def selected(self):
        """(kind, combo, email) for the selected row: kind is 'person', 'removed', 'supervisor' or 'combo'."""
        sel = self.tree.selection()
        if not sel or not self.data:
            return None, None, None
        item = sel[0]
        if item in self.pending_items:
            return "pending", self.pending_items[item], None
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
        menu = self.build_menu()
        menu.update_idletasks()
        win = self.frame.winfo_toplevel()                 # the window's edges, not the screen's: with two monitors
        bottom = win.winfo_rooty() + win.winfo_height()   # the "screen" can be taller than the one the app is on
        up = event.y_root + menu.winfo_reqheight() > bottom
        popup(menu, event.x_root, event.y_root - menu.winfo_reqheight() if up else event.y_root)

    def actions_menu(self):
        """The Actions button: the same menu as a right-click, for the selected row, opened under the button."""
        b, menu = self.actions, self.build_menu()
        menu.update_idletasks()                           # the button is at the bottom of the window: open upward
        popup(menu, b.winfo_rootx(), max(0, b.winfo_rooty() - menu.winfo_reqheight()))

    def show_actions_hint(self):
        kind, combo, email = self.selected()
        what = {"pending": "a combo waiting for a decision","combo": combo and combo.name, "person": email and self.name(email),
                "supervisor": email and self.name(email), "removed": email and self.name(email) + " (removed)",
                "withdrawn": combo and combo.name + " (withdrawn)"}.get(kind)
        self.actions_hint.configure(text=f"for {what}" if what else "")

    def build_menu(self):
        """What can be done with the selected row (a combo, a person, a removed person, a withdrawn combo)."""
        kind, combo, email = self.selected()
        sel = self.tree.selection()
        item = sel[0] if sel else None
        p = self.get_palette() or {}
        menu = tk.Menu(self.tree, tearoff=0, background=p.get("panel"), foreground=p.get("text"),
                       activebackground=p.get("accent"), activeforeground=p.get("accent_text"))
        if combo is not None:
            if combo.liaison:
                menu.add_command(label=f"Copy liaison email of {combo.name} ({self.name(combo.liaison)})",
                                 command=lambda: self.copy_emails(combo, liaison=True))
            else:
                menu.add_command(label=f"Copy liaison email of {combo.name} (no liaison)", state="disabled")
            menu.add_command(label=f"Copy emails of {combo.name} (students and supervisor)",
                             command=lambda: self.copy_emails(combo))
            menu.add_separator()
        if kind == "person":
            if email != combo.liaison:
                menu.add_command(label="Make liaison", command=self.make_liaison)
            menu.add_command(label="Change name...", command=self.rename)
            menu.add_command(label="Change email...", command=self.edit_email)
            menu.add_command(label="Set instrument...", command=lambda: self.edit_instrument(item))
            n = sum(1 for _, counts in self.conflict_dates(email).values() if counts)
            menu.add_command(label=f"Conflicts ({n})..." if n else "Conflicts... (none: add one)",
                             command=lambda: ConflictsDialog(self, email))
            menu.add_separator()
            menu.add_command(label=f"Remove from {combo.name}...", command=self.remove_member)
        elif kind == "removed":
            menu.add_command(label=f"Put back in {combo.name}", command=self.restore_member)
        elif kind == "supervisor":
            menu.add_command(label="Change name...", command=self.rename)
            menu.add_command(label="Change email...", command=self.edit_email)
        if kind is None:
            menu.add_command(label="Pick a combo or a person in the list first", state="disabled")
        elif kind == "pending":
            menu.add_command(label="Waiting for a decision: approve or reject it in Outlook", state="disabled")
        elif kind == "withdrawn":
            menu.add_command(label=f"Put back {combo.name}...", command=self.put_back)
        else:
            if kind == "combo":
                menu.add_command(label=f"Change the liaison of {combo.name}...", command=self.make_liaison)
            else:
                menu.add_separator()
            menu.add_command(label=f"Add a member to {combo.name}...", command=self.add_member)
            if not self.data["settings"].use_first_year:
                pass                                  # first-year combos are off (Settings): no tag, no option
            elif combo.first_year:
                menu.add_command(label=f"Remove the first-year tag from {combo.name}",
                                 command=lambda: self.set_first_year(combo, False))
            else:
                menu.add_command(label=f"Mark {combo.name} as a first-year combo",
                                 command=lambda: self.set_first_year(combo, True))
            menu.add_separator()
            menu.add_command(label=f"Withdraw {combo.name}...", command=self.withdraw)
        if self.data:
            menu.add_separator()
            menu.add_command(label="New combo... (one not in the approvals)", command=self.new_combo)
        self.menu = menu                              # (kept for tests)
        return menu

    def new_combo(self):
        if not self.data:
            messagebox.showinfo("New combo", "Nothing loaded yet.")
            return
        NewComboDialog(self)

    def conflict_dates(self, email):
        """{date: (source, counts)} of someone's conflicts: source 'form' (the conflict form; counts False when
        overruled in the app) or 'app' (added in the app)."""
        sem = self.data["settings"].semester_name
        added = self.store.added_conflicts(sem).get(email, set())
        out = {d: ("form", True) for d in self.data["blocked"].get(email, ()) if d not in added}
        out.update({d: ("form", False) for d in self.store.overruled(sem).get(email, ())})
        out.update({d: ("app", True) for d in added})
        return dict(sorted(out.items()))

    def copy_emails(self, combo, liaison=False):
        """The combo's emails, ready to paste into Outlook: the liaison, the other members by name, the supervisor.
        liaison: only the liaison's."""
        from clipboard import copy
        if liaison:
            copy(self.frame, combo.liaison, f"the liaison email of {combo.name}", self.get_palette())
            self.info.configure(text=f"Copied the liaison email of {combo.name} ({self.name(combo.liaison)}): paste "
                                     "with Ctrl+V.")
            self.last_copied = combo.liaison          # (kept for tests)
            return
        people = ([combo.liaison] if combo.liaison else []) + sorted(combo.members - {combo.liaison},
                                                                     key=lambda e: self.name(e).lower())
        emails = people + ([combo.professor] if combo.professor and combo.professor not in people else [])
        what = f"{len(emails)} email{'' if len(emails) == 1 else 's'} of {combo.name}"
        copy(self.frame, "; ".join(emails), what, self.get_palette())
        self.info.configure(text=f"Copied {what} (students{' and supervisor' if combo.professor else ''}): paste "
                                 "with Ctrl+V.")
        self.last_copied = "; ".join(emails)          # (kept for tests)

    # ------------------------------------------------------------ pending changes
    def queue(self, change, message, combo=None, view="load", withdraw=None):
        """Adds an edit to the pending changes (nothing is saved until Confirm changes) and shows the tab as if it
        were done. change(store) applies it to scheduler_data.json; combo: the name(s) of the combo(s) it touches,
        marked while pending; view: 'load' (members change: read everything again), 'fill' (only names /
        instruments) or 'none' (the caller updates the cell; the combo's row is marked here); withdraw: (name, ref)
        of a combo withdrawn (its sets open on Confirm)."""
        names = [combo] if isinstance(combo, str) else list(combo or [])
        self.pending.append(dict(change=change, text=message, combos=names, withdraw=withdraw))
        if view == "load":
            self.load(quiet=True)
        else:
            change(self.store)
            self.data["names"] = self.store.names
            self.data["instruments"] = self.store.instruments(self.data["settings"].semester_name,
                                                              self.data["combos"].values())
            if view == "fill":
                self.fill()
            else:
                for item, cid in self.combo_items.items():
                    if self.data["combos"][cid].name in names:
                        self.mark(item)
        self.refresh_pending()
        self.info.configure(text=f"Not saved yet: {message} (Confirm changes, below)")

    def refresh_pending(self):
        n = len(self.pending)
        if n:
            self.pending_title.configure(text=f"{n} unsaved change{'s' if n > 1 else ''} (marked \u25cf above)")
            self.pending_box.pack(fill="x", pady=(10, 0), before=self.bottom)
        else:
            self.pending_box.pack_forget()

    def undo_last(self):
        if self.pending:
            p = self.pending.pop()
            self.load(quiet=True)
            self.refresh_pending()
            self.info.configure(text=f"Undone: {p['text']}")

    def discard_all(self, ask=True):
        if self.pending and (not ask or messagebox.askyesno(
                "Discard all?", f"Throw away all {len(self.pending)} pending change(s)? Nothing has been saved.")):
            self.pending = []
            self.load(quiet=True)
            self.refresh_pending()
            self.info.configure(text="Pending changes discarded.")

    def reload(self):
        """The Reload button: reads what's saved again; pending changes stay pending, on top of it."""
        self.load()

    def ask_to_save(self):
        """For closing the app or changing folder with pending changes: save, discard, or stay. True = go ahead."""
        if not self.pending:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved combo changes", f"{len(self.pending)} change(s) in the Combos tab haven't been saved.\n\n"
            "Yes: save them now.\nNo: throw them away.\nCancel: go back.", icon="warning")
        if answer is None:
            return False
        if answer:
            return self.confirm()
        self.discard_all(ask=False)
        return True

    def confirm(self):
        """Saves every pending change at once (scheduler_data.json, read again first so nothing saved meanwhile is
        lost); a withdrawn combo's sets become open in the schedule (backup first) and the exports are rebuilt.
        True = saved."""
        if not self.pending:
            return True
        sem, folder = self.data["settings"].semester_name, self.get_folder()
        withdrawals = [p["withdraw"] for p in self.pending if p["withdraw"]]
        swaps = self.get_swaps()
        if withdrawals and swaps and swaps.pending:
            messagebox.showinfo("Confirm changes", f"A combo is withdrawn, and there are {len(swaps.pending)} unsaved "
                                "swap change(s). Confirm or discard those first (Swaps tab), then confirm here.")
            return False
        try:
            store = Store(folder)
            for p in self.pending:
                p["change"](store)
            store.save()
        except (OSError, ValueError) as e:
            messagebox.showerror("Couldn't save", f"{e}\n\nThe changes are still pending.")
            return False
        opened, backup = [], None
        for name, ref in dict.fromkeys(withdrawals):  # once each; not one that was put back again
            if store.member_changes(sem, ref)["withdrawn"]:
                try:
                    cells, copy = open_sets_of(folder, name)
                except (OSError, ScheduleFileError) as e:
                    messagebox.showerror("Couldn't open the sets", f"{name} is withdrawn, but its sets couldn't be "
                                         f"opened in the schedule: {e}\nThe rule check (Run tab, step 3) shows them.")
                    continue
                opened += [(name, d, k) for d, k in cells]
                backup = backup or copy
        n = len(self.pending)
        app_log.write(f"Combos tab: saved {n} change(s)\n" + "\n".join(p["text"] for p in self.pending)
                      + "".join(f"\nOpened {make_label(d)} set {k} ({name})" for name, d, k in opened))
        self.pending = []
        self.load(quiet=True)
        self.refresh_pending()
        if self.on_change:
            self.on_change()
        self.info.configure(text=f"Saved {n} change(s)." + (f" {len(opened)} set(s) opened." if opened else ""))
        if opened and self.after_schedule_change:
            self.after_schedule_change("Opened " + ", ".join(f"{make_label(d)} set {k} ({name})" for name, d, k in
                                                              opened) + f". Backup of the schedule before: {backup}\n")
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
        self.queue(change, f"Remove {self.name(email)} from {combo.name}"
                   + (f"; {self.name(new_liaison)} becomes the liaison" if new_liaison else "") + ".", combo=combo.name)

    def restore_member(self):
        kind, combo, email = self.selected()
        if kind != "removed":
            return
        self.queue(lambda s: s.add_member(self.data["settings"].semester_name, combo.ref, email),
                   f"Put {self.name(email)} back in {combo.name}.", combo=combo.name)

    def make_liaison(self):
        kind, combo, email = self.selected()
        if kind == "combo" and combo.members:                     # a combo picked: choose from its members
            email = self.choose_liaison(combo, sorted(combo.members), f"Liaison of {combo.name}:", combo.liaison)
        elif kind != "person":
            messagebox.showinfo("Make liaison", "Open a combo and pick the member who should be its liaison.")
            return
        if not email or email == combo.liaison:
            return
        self.queue(lambda s: s.set_liaison(self.data["settings"].semester_name, combo.ref, email),
                   f"{self.name(email)} becomes the liaison of {combo.name}.", combo=combo.name)

    def set_first_year(self, combo, value):
        """Tags or untags a first-year combo (kept in scheduler_data.json; wins over the approvals' First year)."""
        settings = self.data["settings"]
        msg = f"{combo.name} {'becomes' if value else 'is no longer'} a first-year combo."
        if self.data["sets"]:
            early = [d for d, row in self.data["sets"].items() if combo.id in row.values()
                     and value and settings.first_year_earliest_date and d < settings.first_year_earliest_date]
            msg += (" The schedule isn't made again" + (": it plays " + ", ".join(make_label(d) for d in sorted(early))
                    + ", before the first-year date (swap it in the Swaps tab)." if early else "."))
        self.queue(lambda s: s.set_first_year(settings.semester_name, combo.ref, value), msg, combo=combo.name)

    def withdraw(self):
        """Withdraws the selected combo (a pending change; kept in scheduler_data.json, its number stays reserved).
        On Confirm, if the schedule is out, its sets become open (backup first) and the exports are rebuilt."""
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
            text += ("\n\nIts shows: " + ", ".join(f"{make_label(d)} (set {k})" for d, k in shows) + ". When you "
                     "confirm, these sets become OPEN in the schedule (a backup is kept): volunteers can claim them, or give one to a "
                     "combo in the Schedule tab (who could take it).")
        if sup:
            text += ("\n\n\u26a0 " + ", ".join(make_label(d) for d in sup) + (" is a supervised night" if len(sup) == 1
                     else " are supervised nights") + ", which must be full: give that set to another combo.")
        text += "\n\nThe approvals spreadsheet isn't changed; you can put the combo back here."
        if not messagebox.askyesno("Withdraw a combo", text, icon="warning"):
            return
        settings = self.data["settings"]
        self.queue(lambda s: s.set_withdrawn(settings.semester_name, combo.ref, True),
                   f"Withdraw {combo.name}" + (f" ({len(shows)} set(s) become open)." if shows else "."),
                   combo=combo.name, withdraw=(combo.name, combo.ref))

    def put_back(self):
        kind, combo, _ = self.selected()
        if kind != "withdrawn":
            return
        if self.data["sets"] and not messagebox.askyesno(
                "Put a combo back", f"Put {combo.name} back?\n\n\u26a0 This does NOT give it its shows back: the schedule "
                "isn't made again. Its sets were opened when it was withdrawn (others may have taken them since), so "
                f"{combo.name} will have no shows. It can then claim open sets (Swaps tab), or you can give it sets "
                "(Schedule tab).", icon="warning"):
            return
        self.queue(lambda s: s.set_withdrawn(self.data["settings"].semester_name, combo.ref, False),
                   f"Put {combo.name} back" + (" (no shows yet: it can claim open sets in the Swaps tab)."
                                               if self.data["sets"] else "."), combo=combo.name)

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

    def saved_first(self):
        """Before an export with pending changes: save them first? True = saved, go ahead."""
        return messagebox.askokcancel(
            "Unsaved changes", f"{len(self.pending)} change(s) here aren't saved yet. Save them first, then export?"
        ) and self.confirm()

    def export_pdf(self):
        if not self.data:
            messagebox.showinfo("Combo list", "Nothing loaded yet.")
            return
        if self.pending and not self.saved_first():
            return
        try:
            from outputs.combos_pdf import write_combos_pdf
        except ImportError:
            messagebox.showerror("Combo list", "The PDF needs the reportlab package: Run tab > Install missing packages.")
            return
        path = self.get_folder() / COMBOS_PDF
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

    def export_xlsx(self):
        """Combos.xlsx: one table per combo (members by instrument with emails, the liaison marked, the supervisor),
        then opens it."""
        if not self.data:
            messagebox.showinfo("Combo list", "Nothing loaded yet.")
            return
        if self.pending and not self.saved_first():
            return
        from outputs.combos_xlsx import write_combos_xlsx
        path = self.get_folder() / COMBOS_XLSX
        combos = sorted(self.data["combos"].values(), key=lambda c: c.name)
        try:
            write_combos_xlsx(path, combos, self.name, self.data["settings"].semester_name, self.data["instruments"],
                              self.data["shows"])
        except PermissionError:
            messagebox.showerror("Combo list", f"Can't write {path.name}: it's open in Excel. Close it and try again.")
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
        self.warn = ttk.Label(box, text="", wraplength=420, justify="left", style="Warn.TLabel")
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
        panel.queue(change, f"Add {name or panel.name(e)} to {self.combo.name}."
                    + (f" Note: {' '.join(clashes)}" if clashes else ""), combo=self.combo.name)


class NewComboDialog:
    """A combo that isn't in the approvals (accepted late, after the form closed): its liaison, other members and
    supervisor by email. A pending change like the others; after Confirm it's numbered and edited like any combo."""

    def __init__(self, panel):
        self.panel = panel
        win = self.win = tk.Toplevel(panel.frame)
        win.title("New combo")
        win.transient(panel.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=16)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="New combo", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(box, text="For a combo that isn't in the approvals spreadsheet (e.g. accepted after the form "
                            "closed). It gets the next number.", style="Hint.TLabel", wraplength=440,
                  justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))
        self.liaison, self.supervisor = ttk.Entry(box, width=46), ttk.Entry(box, width=46)
        self.members = tk.Text(box, width=46, height=6, relief="solid", borderwidth=1, wrap="word")
        self.first_year = tk.BooleanVar()
        rows = [("Liaison", self.liaison, "Their email."),
                ("Other members", self.members, "Emails: one per line, or pasted from anywhere."),
                ("Supervisor", self.supervisor, "Their email (optional now).")]
        for r, (label, widget, hint) in enumerate(rows, start=1):
            ttk.Label(box, text=label).grid(row=2 * r, column=0, sticky="nw", padx=(0, 12), pady=(6, 0))
            widget.grid(row=2 * r, column=1, sticky="w", pady=(6, 0))
            ttk.Label(box, text=hint, style="Hint.TLabel").grid(row=2 * r + 1, column=1, sticky="w")
        if panel.data["settings"].use_first_year:
            ttk.Checkbutton(box, text="First-year combo", variable=self.first_year).grid(row=8, column=1, sticky="w",
                                                                                        pady=(8, 0))
        bar = ttk.Frame(box)
        bar.grid(row=9, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Add", style="Accent.TButton", command=self.add).pack(side="right", padx=(0, 6))
        self.liaison.focus_set()
        win.grab_set()

    def clean(self, text):
        p = self.panel
        return [p.store.fix_email(p.data["rules"].norm(m)) for m in EMAIL_RE.findall(text)]

    def add(self):
        p = self.panel
        liaison = self.clean(self.liaison.get())
        if not liaison:
            messagebox.showerror("New combo", "Type the liaison's email.", parent=self.win)
            return
        members = [e for e in dict.fromkeys(self.clean(self.members.get("1.0", "end"))) if e != liaison[0]]
        sup = self.clean(self.supervisor.get())
        if self.supervisor.get().strip() and not sup:
            messagebox.showerror("New combo", "The supervisor's email doesn't look like an email address.",
                                 parent=self.win)
            return
        liaison, sup, fy = liaison[0], sup[0] if sup else "", self.first_year.get()
        sem = p.data["settings"].semester_name
        others = sorted({c.name for c in p.data["combos"].values() for e in [liaison] + members if e in c.members})
        self.win.destroy()
        n = 1 + max((int(r[3:]) for r in p.store.new_combos(sem) if r[3:].isdigit()), default=0)
        p.queue(lambda s: s.add_combo(sem, [liaison] + members, liaison, sup, fy),
                f"New combo: {p.name(liaison)} (liaison) and {len(members)} other member(s)."
                + (f" Note: some are also in {', '.join(others)}." if others else "")
                + (" It has no shows yet: give it sets (Schedule tab) or let it claim open sets (Swaps tab)."
                   if p.data["sets"] else ""))
        new = next((c.name for c in p.data["combos"].values() if c.ref == f"app{n}"), None)
        if new:                                       # now numbered (in the preview): mark it
            p.pending[-1]["combos"] = [new]
            p.pending[-1]["text"] = p.pending[-1]["text"].replace("New combo:", f"New combo {new}:")
            p.fill()
            p.info.configure(text=f"Not saved yet: {p.pending[-1]['text']} (Confirm changes, below)")


class ConflictsDialog:
    """Someone's conflicts: the conflict form's dates, each with a 'counts' tick (untick to overrule it, e.g. they can
    make it after all), dates added in the app (untick to take one back), and a night to add (told to the director,
    not sent through the form). A pending change; the conflicts spreadsheet isn't changed."""

    def __init__(self, panel, email):
        self.panel, self.email = panel, email
        self.dates = panel.conflict_dates(email)
        self.plays = {}
        for d, row in panel.data["sets"].items():
            for c in row.values():
                if c and email in panel.data["combos"][c].members:
                    self.plays.setdefault(d, []).append(panel.data["combos"][c].name)
        win = self.win = tk.Toplevel(panel.frame)
        win.title("Conflicts")
        win.transient(panel.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=16)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=f"Conflicts of {panel.name(email)}", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(box, text="Ticked nights count as nights they can't play. Untick one to overrule it (e.g. they can "
                            "make it after all). The conflicts spreadsheet isn't changed.", style="Hint.TLabel",
                  wraplength=440, justify="left").pack(anchor="w", pady=(2, 10))
        self.rows = ttk.Frame(box)
        self.rows.pack(fill="x")
        self.vars, self.new = {}, set()
        if not self.dates:
            self.none = ttk.Label(self.rows, text="None so far.", style="Hint.TLabel")
            self.none.pack(anchor="w")
        for d, (source, counts) in self.dates.items():
            self.row(d, counts, source)
        taken = set(self.dates)
        self.choices = {f"{make_label(n.date)}, {n.venue}": n.date for n in panel.data["nights"] if n.date not in taken}
        add = ttk.Frame(box)
        add.pack(fill="x", pady=(12, 0))
        ttk.Label(add, text="Add a night they can't make:").pack(side="left")
        self.pick = ttk.Combobox(add, values=list(self.choices), state="readonly", width=24)
        self.pick.pack(side="left", padx=6)
        ttk.Button(add, text="Add", command=self.add).pack(side="left")
        bar = ttk.Frame(box)
        bar.pack(fill="x", pady=(14, 0))
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="OK", style="Accent.TButton", command=self.ok).pack(side="right", padx=(0, 6))
        win.grab_set()

    def row(self, d, counts, source):
        self.vars[d] = tk.BooleanVar(value=counts)
        text = make_label(d) + ("   (added here)" if source == "app" else "") + (
            f"   ({', '.join(self.plays[d])} plays that night)" if d in self.plays else "")
        ttk.Checkbutton(self.rows, text=text, variable=self.vars[d]).pack(anchor="w", pady=1)

    def add(self):
        d = self.choices.pop(self.pick.get(), None)
        if d is None:
            return
        if getattr(self, "none", None):
            self.none.destroy()
            self.none = None
        self.new.add(d)
        self.row(d, True, "app")
        self.pick.configure(values=list(self.choices))
        self.pick.set("")

    def ok(self):
        p, email = self.panel, self.email
        sem = p.data["settings"].semester_name
        overrule = {d: not v.get() for d, v in self.vars.items()           # the form's: overruled or not
                    if d in self.dates and self.dates[d][0] == "form" and v.get() != self.dates[d][1]}
        added = {d: v.get() for d, v in self.vars.items()                  # added here: kept or taken back
                 if (d in self.new and v.get()) or (d in self.dates and self.dates[d][0] == "app" and not v.get())}
        self.win.destroy()
        if not overrule and not added:
            return

        def change(s):
            for d, on in overrule.items():
                s.set_overruled(sem, email, d, on)
            for d, on in added.items():
                s.set_added_conflict(sem, email, d, on)
        words = ([f"{make_label(d)} {'overruled' if on else 'counts again'}" for d, on in sorted(overrule.items())]
                 + [f"{make_label(d)} {'added' if on else 'taken back'}" for d, on in sorted(added.items())])
        p.queue(change, f"{p.name(email)}'s conflicts: {', '.join(words)}.", combo=p.combos_of(email))
