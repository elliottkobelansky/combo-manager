"""The Combos tab of scheduler_app.py: every accepted combo with its members' names, liaison, supervisor and shows;
correct a name, set each person's instrument, add or remove members, change the liaison, and export the combo list
PDF.

Corrected names, instruments (per person per combo: someone can play piano in one combo and bass in another) and
member changes are kept in scheduler_data.json in the data folder (store.py), so the PDFs, the checks and the Swaps
tab all use them. The linked sheets themselves are never changed.
"""
import tkinter as tk
from tkinter import ttk

import app_log
from app_config import input_files
import dialogs
from core.model import make_label
from data_folder import COMBOS_PDF, COMBOS_XLSX, export_path, settings_path
from inputs import EMAIL_RE, EmailRules, InputError, email_warnings, load_input, name_from_email
from schedule_file import ScheduleFileError, has_schedule, load as load_schedule, open_sets_of
from settings_file import SettingsError, load_settings
from store import Store
from theme import bind_right_click, popup, scrolled_tree, search_box
from util import INSTRUMENTS, by_instrument



class CombosPanel:
    def __init__(self, parent, get_folder, get_palette=lambda: {}, open_path=None, on_change=None,
                 get_swaps=lambda: None, after_schedule_change=None, on_check=None):
        self.get_folder, self.get_palette, self.open_path = get_folder, get_palette, open_path
        self.on_change = on_change                        # reloads the other tabs after an email fix
        self.get_swaps = get_swaps                        # the Swaps tab (its pending changes)
        self.after_schedule_change = after_schedule_change  # rebuilds the PDF and xlsx after the schedule changed
        self.on_check = on_check or (lambda: None)       # Check combos (the warnings, in the results box below)
        self.people = {}                                  # tree item id -> (combo name, email); combo None = supervisor
        self.removed = {}                                 # tree item id -> (combo name, email) of a removed member
        self.combo_items = {}                             # tree item id -> combo name
        self.withdrawn_items = {}                         # tree item id -> Combo withdrawn in the app
        self.pending_items = {}                           # tree item id -> Combo waiting for a decision
        self.pending = []                                 # edits not saved yet (queue): shown as if done
        self.on_pending = lambda: None                    # set by the app: unsaved changes came or went (tab dots)
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        # the sheets the forms fill (optional): which are linked, Sync to read them again
        links = ttk.Frame(self.frame, style="Card.TFrame", padding=(10, 6))
        links.pack(fill="x", pady=(0, 10))
        self.links_label = ttk.Label(links, text="")
        self.links_label.pack(side="left")
        ttk.Button(links, text="Linked sheets...", command=lambda: LinkDialog(self)).pack(side="right")
        self.sync_button = ttk.Button(links, text="Sync", command=self.reload)
        self.sync_button.pack(side="right", padx=(0, 6))

        # Check combos and Lock combos (like the Schedule tab's buttons)
        tools = ttk.Frame(self.frame)
        tools.pack(fill="x", pady=(0, 12))
        self.check_button = ttk.Button(tools, text="Check combos", style="Accent.TButton",
                                       command=lambda: self.on_check())
        self.check_button.pack(side="left")
        self.locked = tk.BooleanVar()
        self.lock_box = ttk.Checkbutton(tools, text="Lock combos", variable=self.locked, command=self.set_locked)
        self.lock_box.pack(side="left", padx=(16, 0))
        self.lock_hint = ttk.Label(tools, text="Locked: nothing here can be changed (untick to edit).",
                                   style="Hint.TLabel")

        top = self.search_row = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left", padx=(0, 6))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.fill())
        search_box(top, self.search, on_clear=lambda: self.expand(False)).pack(side="left")
        self.info = ttk.Label(top, text="", style="Hint.TLabel")
        self.info.pack(side="left", padx=12)

        table, self.tree = scrolled_tree(self.frame, [
            ("#0", "Combo / person", 330, True), ("shows", "Shows", 210, True), ("instrument", "Instrument", 120, False),
            ("also", "Also in", 70, False), ("conflicts", "Conflicts", 75, False), ("email", "Email", 200, True)])
        table.pack(fill="both", expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", self.double_click)
        self.tree.bind("<Button-1>", self.click, add="+")

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        # unsaved changes: a bar under the search row, shown only while there are some (like the Schedule tab's)
        self.pending_box = ttk.Frame(self.frame, style="Card.TFrame", padding=(12, 8))
        self.pending_title = ttk.Label(self.pending_box, text="", style="CardTitle.TLabel")
        self.pending_title.pack(side="left")
        ttk.Button(self.pending_box, text="Discard all", command=self.discard_all).pack(side="right")
        ttk.Button(self.pending_box, text="Undo last", command=self.undo_last).pack(side="right", padx=6)
        self.confirm_button = ttk.Button(self.pending_box, text="Confirm changes", style="Accent.TButton",
                                         command=self.confirm)
        self.confirm_button.pack(side="right")
        self.bottom = bottom
        ttk.Button(bottom, text="Expand all", command=lambda: self.expand(True)).pack(side="left")
        ttk.Button(bottom, text="Collapse all", command=lambda: self.expand(False)).pack(side="left", padx=6)
        self.actions = ttk.Button(bottom, text="Actions \u25be", command=self.actions_menu)   # = the right-click menu
        self.actions.pack(side="left", padx=(6, 0))
        self.actions_hint = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.actions_hint.pack(side="left", padx=10)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_actions_hint(), add="+")
        self.file_buttons = [ttk.Button(bottom, text="Open Excel", style="Accent.TButton", command=self.export_xlsx),
                             ttk.Button(bottom, text="Open PDF", style="Accent.TButton", command=self.export_pdf)]
        self.file_buttons[0].pack(side="right")
        self.file_buttons[1].pack(side="right", padx=(0, 6))

        self.data = None
        bind_right_click(self.frame, self.context_menu)   # anywhere on the tab (empty space: New combo...)
        self.recolor()

    def set_locked(self):
        """The 'Lock combos' tick: saved for this semester (every computer sees it). Nothing on the tab can be changed
        while it's on."""
        on = self.locked.get()
        if not self.data:
            self.locked.set(False)
            return
        if on and self.pending:
            dialogs.showinfo("Lock combos", "There are unsaved changes. Confirm or discard them first, then lock.")
            self.locked.set(False)
            return
        if not on and not dialogs.askyesno(
                "Unlock the combos?", "Unlocking lets the combos be changed again: members, liaisons, coaches, "
                "withdrawals and new combos.\n\nIf the schedule is already out, let the combos involved know about "
                "any change you make.", yes="Unlock", no="Keep locked"):
            self.locked.set(True)
            return
        sem = self.data["settings"].semester_name
        try:
            store = Store(self.get_folder())
            store.set_combos_locked(sem, on)
            store.save()
        except (OSError, ValueError) as e:
            dialogs.showerror("Couldn't save", str(e))
            self.locked.set(not on)
            return
        self.store.set_combos_locked(sem, on)
        app_log.write("Combos locked" if on else "Combos unlocked")
        self.show_lock()

    def show_lock(self):
        if self.locked.get():
            self.lock_hint.pack(side="left", padx=(12, 0))
        else:
            self.lock_hint.pack_forget()

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
            self.locked.set(store.combos_locked(settings.semester_name))
            self.show_lock()
        except (SettingsError, InputError, ValueError) as e:
            if not quiet:
                dialogs.showerror("Can't load the combos", str(e))
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
        self.show_links()
        n_people = len({e for c in combos.values() for e in c.members})
        self.summary = f"{len(combos)} combos, {n_people} students." + (
            " * = feedback night." if shows else " (No schedule yet: shows aren't listed.)")
        self.fill()

    def show_links(self):
        """The linked-sheets bar: which sheets are read (Sync reads them again)."""
        try:
            store = Store(self.get_folder())
        except (OSError, ValueError):
            return
        files = input_files(self.get_folder())
        on = [files[w].name for w in ("approvals", "conflicts") if store.linked(w)]
        if on:
            self.links_label.configure(text="Linked sheets: " + ", ".join(on))
            self.sync_button.pack(side="right", padx=(0, 6))
        else:
            self.links_label.configure(text="No sheets linked")
            self.sync_button.pack_forget()

    def name(self, email):
        return self.data["names"].get(email) or name_from_email(email)

    def coach_name(self, email):
        """'Prof. Yuki Tanabe': the coach's title (if set) and name."""
        return f"{self.store.titles.get(email.lower(), '')} {self.name(email)}".strip()

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
        touched_people = {(n, e) for p in self.pending for n in p["combos"] for e in p.get("people", ())}
        member_of = {}
        for c in combos.values():
            for e in c.members:
                member_of.setdefault(e, []).append(c.name)
        band = 0
        for cid in sorted(combos, key=lambda c: combos[c].name):
            c = combos[cid]
            people = self.member_order(c)
            text = " ".join([c.name] + [self.name(e) + " " + e for e in people]
                            + ([self.coach_name(c.professor), c.professor] if c.professor else [])).lower()
            if q and not all(word in text for word in q.split()):     # every word, anywhere (names, emails, coach)
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
                if (c.name, e) in touched_people:
                    self.mark(pid)
            for e in changes["remove"]:
                pid = self.tree.insert(item, "end", text=f"    {self.name(e)}  \u00b7 removed (Actions: put back)",
                                       values=("", "", "", "", e), tags=(shade, "removed"))
                self.removed[pid] = (c.name, e)
                if (c.name, e) in touched_people:
                    self.mark(pid)
            if c.professor:
                pid = self.tree.insert(item, "end", text="    " + self.coach_name(c.professor) + "  (coach)",
                                       values=("", "", "", "", self.mail(c.professor)), tags=(shade,))
                self.people[pid] = (None, c.professor)
        for c in self.data["pending"]:                    # submitted, no decision yet: shown, not editable
            who = self.name(c.liaison) if c.liaison else "no liaison"
            label = f"Waiting for a decision \u00b7 {who}"
            if q and not all(w in (label + " " + " ".join(self.name(e) + " " + e for e in c.members)).lower()
                             for w in q.split()):
                continue
            item = self.tree.insert("", "end", text=label, values=("approve or reject it in Outlook", "", "",
                                                                   "", ""),
                                    open=bool(q) or self.tree_key(label) in open_items, tags=("removed",))
            self.pending_items[item] = c
            for e in self.member_order(c) + ([c.professor] if c.professor else []):
                pid = self.tree.insert(item, "end", text="    " + (self.coach_name(e) + "  (coach)" if e == c.professor
                                                                      else self.name(e)),
                                       values=("", "", "", len(self.data["blocked"].get(e, ())) or "", e),
                                       tags=("removed",))
                self.pending_items[pid] = c
        for c in sorted(self.data["withdrawn"].values(), key=lambda c: c.name):
            label = (f"{c.name} ({self.name(c.liaison)})" if c.liaison else c.name) + "  \u00b7 withdrawn" + (
                self.UNSAVED if c.name in touched else "")
            if q and not all(w in (label + " " + " ".join(self.name(e) + " " + e for e in c.members)).lower()
                             for w in q.split()):
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
                pid = self.tree.insert(item, "end", text="    " + self.coach_name(c.professor) + "  (coach)",
                                       values=("", "", "", "", c.professor), tags=("removed",))
                self.withdrawn_items[pid] = c
        q = self.search.get().strip()
        if q:                                         # searching: how many match, not the totals
            n = len(self.combo_items)
            self.info.configure(text=f"{n} of {len(combos)} combos match '{q}'." if n else f"Nothing matches '{q}'.")
        else:
            self.info.configure(text=getattr(self, "summary", ""))

    UNSAVED = "   \u25cf unsaved changes"

    def mark(self, item):
        """Marks a combo's or a member's row: it has changes not saved yet."""
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
        self.tree.tag_configure("pending", foreground=p["accent_fg"])

    def expand(self, yes):
        for i in self.tree.get_children():
            self.tree.item(i, open=yes)

    def click(self, event):
        """A click on a person's Instrument cell opens the dropdown there."""
        if self.locked.get():
            return
        item, col = self.tree.identify_row(event.y), self.tree.identify_column(event.x)
        if item in self.people and col == "#2" and self.people[item][0]:
            self.tree.selection_set(item)
            self.tree.after_idle(lambda: self.edit_instrument(item))

    def double_click(self, event):
        if self.locked.get():
            return
        col = self.tree.identify_column(event.x)
        if col == "#5":
            self.edit_email()
        elif col != "#2":
            self.rename()

    def edit_email(self):
        sel = self.tree.selection()
        email = self.people.get(sel[0], (None, None))[1] if sel else None
        if not email:
            dialogs.showinfo("Change an email", "Open a combo and pick a person (double-click their email works "
                                                   "too).")
            return
        new = dialogs.askstring(
            "Change email", f"Correct email for {self.name(email)}:\n(Used everywhere: their combos and their "
            "conflicts.)", initialvalue=email, ok="Change", parent=self.frame)
        if new is None:
            return
        new = new.strip().lower()
        if not EMAIL_RE.fullmatch(new):
            dialogs.showerror("Change email", f"'{new}' doesn't look like an email address.")
            return
        if new == email:
            return
        back = new in self.store.emails and self.store.emails.get(new) == email   # typing an original back
        self.queue(lambda s: s.set_email(email, new), f"{email} becomes {new}" + (" (back to the original)" if back
                                                                                  else "") + ".",
                   combo=self.combos_of(email), people=[email, new])
        if self.pending and self.pending[-1]["people"] == [email, new]:
            self.pending[-1]["email"] = (email, new)       # (Confirm: the schedule's faculty members follow)

    def edit_instrument(self, item=None):
        """Opens the instrument menu at the person's Instrument cell; picking an item saves it straight away."""
        sel = self.tree.selection()
        item = item or (sel[0] if sel else None)
        if item not in self.people or not self.people[item][0]:
            dialogs.showinfo("Set an instrument", "Open a combo and pick one of its members first.")
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
        typed = dialogs.askstring("Other instrument", f"Instrument for {self.name(email)} in {combo}:",
                                       initialvalue="" if current in INSTRUMENTS else current, ok="Set",
                                       parent=self.frame)
        if typed is not None:
            self.set_instrument(item, typed.strip())

    def set_instrument(self, item, value):
        combo, email = self.people[item]
        if value == self.data["instruments"].get((combo, email), ""):
            return
        sem = self.data["settings"].semester_name
        self.queue(lambda s: s.set_instrument(sem, combo, email, value),
                   f"{self.name(email)} plays {value or 'no instrument'} in {combo}.", combo=combo, view="none",
                   people=[email])
        self.tree.set(item, "instrument", self.cell(value))

    def rename(self):
        sel = self.tree.selection()
        email = self.people.get(sel[0], (None, None))[1] if sel else None
        if not email:
            dialogs.showinfo("Change a name", "Open a combo and pick a person (double-click works too).")
            return
        new = dialogs.askstring("Change name", f"Name for {email}:", initialvalue=self.name(email), ok="Change",
                                parent=self.frame)
        if not new or not new.strip() or new.strip() == self.name(email):
            return
        old = self.name(email)
        self.queue(lambda s: s.set_name(email, new.strip()), f"{old} is now called '{new.strip()}'.", view="fill",
                   combo=self.combos_of(email), people=[email])

    def retitle(self, email):
        """A coach's title (Prof., Dr., ...; anything can be typed, or nothing)."""
        from util import TITLES
        current = self.store.titles.get(email.lower(), "")
        new = dialogs.askstring("Change title", f"Title for {self.name(email)} (e.g. Prof.; leave it empty for none):",
                                initialvalue=current, ok="Change", choices=TITLES, parent=self.frame)
        if new is None or new.strip() == current:
            return
        new = new.strip()
        self.queue(lambda s: s.set_title(email, new),
                   f"{self.name(email)}'s title is now '{new}'." if new else f"{self.name(email)} has no title now.",
                   view="fill", combo=self.combos_of(email), people=[email])

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
        item = self.tree.identify_row(event.y) if event.widget is self.tree else None
        if item:
            self.tree.selection_set(item)
        else:                                             # empty space: what fits nothing picked (New combo...)
            self.tree.selection_set(())
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
        if kind in ("person", "supervisor", "removed"):    # a person: only what's about them
            menu.add_command(label="Copy email", command=lambda: self.copy_person(email))
            menu.add_separator()
        elif combo is not None:
            if combo.liaison:
                menu.add_command(label="Copy liaison email",
                                 command=lambda: self.copy_emails(combo, liaison=True))
            else:
                menu.add_command(label="Copy liaison email", state="disabled")
            menu.add_command(label="Copy all emails",
                             command=lambda: self.copy_emails(combo))
            menu.add_separator()
        if self.locked.get():                             # only copying (and looking) while locked
            if kind == "pending":
                menu.add_command(label="Check this combo...", command=lambda: self.check_pending(combo))
            menu.add_command(label="Locked: untick 'Lock combos' to edit", state="disabled")
            self.menu = menu
            return menu
        if kind == "person":
            if email != combo.liaison:
                menu.add_command(label="Make liaison", command=self.make_liaison)
            menu.add_command(label="Change name...", command=self.rename)
            menu.add_command(label="Change email...", command=self.edit_email)
            menu.add_command(label="Set instrument...", command=lambda: self.edit_instrument(item))
            menu.add_command(label="Edit conflicts...", command=lambda: ConflictsDialog(self, email))
            menu.add_separator()
            menu.add_command(label="Remove from combo...", command=self.remove_member)
        elif kind == "removed":
            menu.add_command(label="Put back in combo", command=self.restore_member)
        elif kind == "supervisor":
            menu.add_command(label="Change title...", command=lambda: self.retitle(email))
            menu.add_command(label="Change name...", command=self.rename)
            menu.add_command(label="Change email...", command=self.edit_email)
        if kind in ("person", "supervisor", "removed"):
            pass
        elif kind is None:
            menu.add_command(label="New combo...", command=self.new_combo)
        elif kind == "pending":
            menu.add_command(label="Check this combo...", command=lambda: self.check_pending(combo))
            menu.add_command(label="Approve or reject it in Outlook", state="disabled")
        elif kind == "withdrawn":
            menu.add_command(label="Put back combo...", command=self.put_back)
        else:
            menu.add_command(label="Change liaison...", command=self.make_liaison)
            menu.add_command(label="Add member...", command=self.add_member)
            if not self.data["settings"].use_first_year:
                pass                                  # first-year combos are off (Semester tab): no tag, no option
            elif combo.first_year:
                menu.add_command(label="Unmark as first-year",
                                 command=lambda: self.set_first_year(combo, False))
            else:
                menu.add_command(label="Mark as first-year",
                                 command=lambda: self.set_first_year(combo, True))
            menu.add_separator()
            menu.add_command(label="Withdraw combo...", command=self.withdraw)
        if kind in ("combo", "withdrawn", "pending"):
            menu.add_separator()
            menu.add_command(label="New combo...", command=self.new_combo)
        self.menu = menu                              # (kept for tests)
        return menu

    def check_pending(self, combo):
        """A combo waiting for a decision: would it fit, next to the accepted ones? Says what would stop it being
        scheduled, and what's worth knowing before approving it in Outlook."""
        from core.checks import check_new_combo
        from util import RHYTHM
        d = self.data
        usual = self.store.usual_instruments()
        instruments = {**d["instruments"], **{(combo.name, e): usual[e] for e in combo.members if usual.get(e)}}
        problems, heads = check_new_combo(combo, list(d["combos"].values()), d["blocked"], d["nights"], d["settings"],
                                          instruments, RHYTHM, self.name)
        who = self.name(combo.liaison) if combo.liaison else "no liaison"
        text = f"{who}'s combo ({len(combo.members)} members), waiting for a decision.\n\n"
        if problems:
            text += "\u2716 It couldn't be scheduled as things are:\n" + "".join(f"\u2022 {t}\n" for t in problems) + "\n"
        if heads:
            text += "\u26a0 Worth knowing:\n" + "".join(f"\u2022 {t}\n" for t in heads) + "\n"
        if not problems and not heads:
            text += "\u2713 No problems found: it can be approved.\n\n"
        if d["sets"]:
            text += ("The schedule is already made: once approved, this combo starts with no shows and can claim "
                     "open sets (Swaps tab).\n\n")
        text += "Approve or reject it in Outlook, then Sync."
        (dialogs.showwarning if problems else dialogs.showinfo)("Check this combo", text.strip(),
                                                                       parent=self.frame)
        self.last_check = (problems, heads)            # (kept for tests)

    def show_combo(self, cid):
        """Picks a combo in the list (from the Schedule tab's Go to combo): opened, scrolled to, selected. The
        search is cleared if it hides it."""
        if not self.data:
            self.load()
        if self.search.get() and cid not in self.combo_items.values():
            self.search.set("")                           # (fills the list again)
        item = next((i for i, c in self.combo_items.items() if c == cid), None)
        if item is None:
            return False
        self.tree.item(item, open=True)
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree.see(item)
        self.tree.focus_set()
        return True

    def new_combo(self):
        if not self.data:
            self.load()                                   # not loaded yet (a blank folder): load first
        if not self.data:
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

    def copy_person(self, email):
        from clipboard import copy
        copy(self.frame, email, f"the email of {self.name(email)}", self.get_palette())
        self.info.configure(text=f"Copied the email of {self.name(email)}: paste with Ctrl+V.")
        self.last_copied = email                      # (kept for tests)

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
        self.info.configure(text=f"Copied {what} (students{' and coach' if combo.professor else ''}): paste "
                                 "with Ctrl+V.")
        self.last_copied = "; ".join(emails)          # (kept for tests)

    # ------------------------------------------------------------ pending changes
    def queue(self, change, message, combo=None, view="load", withdraw=None, people=()):
        """Adds an edit to the pending changes (nothing is saved until Confirm changes) and shows the tab as if it
        were done. change(store) applies it to scheduler_data.json; combo: the name(s) of the combo(s) it touches,
        marked while pending; view: 'load' (members change: read everything again), 'fill' (only names /
        instruments) or 'none' (the caller updates the cell; the combo's row is marked here); withdraw: (name, ref)
        of a combo withdrawn (its sets open on Confirm); people: the emails of the members it's about, marked too."""
        if self.locked.get():                             # (the menus don't offer edits while locked)
            dialogs.showinfo("Combos locked", "The combos are locked. Untick 'Lock combos' (top of the tab) to "
                             "change them.")
            return
        names = [combo] if isinstance(combo, str) else list(combo or [])
        self.pending.append(dict(change=change, text=message, combos=names, withdraw=withdraw, people=list(people)))
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
                for item, (cname, e) in self.people.items():
                    if cname in names and e in people:
                        self.mark(item)
        self.refresh_pending()
        self.info.configure(text=f"Not saved yet: {message} (Confirm changes, below)")

    def refresh_pending(self):
        n = len(self.pending)
        if n:
            self.pending_title.configure(text="\u25cf Unsaved changes")
            self.pending_box.pack(fill="x", pady=(10, 0), after=self.search_row)
        else:
            self.pending_box.pack_forget()
        self.on_pending()

    def undo_last(self):
        if self.pending:
            p = self.pending.pop()
            self.load(quiet=True)
            self.refresh_pending()
            self.info.configure(text=f"Undone: {p['text']}")

    def discard_all(self, ask=True):
        if self.pending and (not ask or dialogs.askyesno(
                "Discard all?", "Throw away the unsaved changes? Nothing has been saved.", yes="Discard",
                no="Keep them", default="no")):
            self.pending = []
            self.load(quiet=True)
            self.refresh_pending()
            self.info.configure(text="Unsaved changes discarded.")

    def reload(self):
        """The Reload button: reads what's saved again; pending changes stay pending, on top of it."""
        self.load()

    def ask_to_save(self):
        """For closing the app or changing folder with pending changes: save, discard, or stay. True = go ahead."""
        if not self.pending:
            return True
        answer = dialogs.askyesnocancel(
            "Unsaved combo changes", "Some changes in the Combos tab haven't been saved.", yes="Save",
            no="Discard", cancel="Go back", icon="warning")
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
            dialogs.showinfo("Confirm changes", "A combo is withdrawn, and the schedule has unsaved changes "
                                "(Schedule and Swaps tabs). Confirm or discard those first, then confirm here.")
            return False
        try:
            store = Store(folder)
            titles_before, names_before = dict(store.titles), dict(store.names)
            for p in self.pending:
                p["change"](store)
            store.save()
        except (OSError, ValueError) as e:
            dialogs.showerror("Couldn't save", f"{e}\n\nThe changes are still pending.")
            return False
        titles = {e: store.titles.get(e, "") for e in set(titles_before) | set(store.titles)
                  if titles_before.get(e, "") != store.titles.get(e, "")}
        names = {e: n for e, n in store.names.items() if names_before.get(e) != n}
        emails = dict(p["email"] for p in self.pending if p.get("email"))
        if (titles or names or emails) and has_schedule(folder):   # a person's new title, name or email: also on
            from schedule_file import sync_faculty                 # the feedback nights they're the faculty member of
            try:
                sync_faculty(folder, emails=emails, names=names, titles=titles)
            except (OSError, ScheduleFileError) as e:
                dialogs.showerror("Couldn't update the schedule", f"Saved, but the feedback nights' faculty members "
                                  f"couldn't be updated: {e}")
        opened, backup = [], None
        for name, ref in dict.fromkeys(withdrawals):  # once each; not one that was put back again
            if store.member_changes(sem, ref)["withdrawn"]:
                try:
                    cells, copy = open_sets_of(folder, name)
                except (OSError, ScheduleFileError) as e:
                    dialogs.showerror("Couldn't open the sets", f"{name} is withdrawn, but its sets couldn't be "
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
        self.write_exports()
        if self.after_schedule_change and has_schedule(folder):    # names, instruments, members show there too
            self.after_schedule_change("Opened " + ", ".join(f"{make_label(d)} set {k} ({name})" for name, d, k in
                                                              opened) + f". Backup of the schedule before: {backup}\n")
        return True

    def add_member(self):
        kind, combo, _ = self.selected()
        if not combo:
            dialogs.showinfo("Add a member", "Pick a combo (or one of its members) first.")
            return
        AddMemberDialog(self, combo)

    def remove_member(self):
        kind, combo, email = self.selected()
        if kind != "person":
            dialogs.showinfo("Remove a member", "Open a combo and pick the member to remove.")
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
        if not dialogs.askyesno("Remove a member", f"Remove {self.name(email)} from {combo.name}?{warn}\n\n"
                                   "You can put them back here.", yes="Remove", no="Cancel"):
            return
        def change(s):
            s.remove_member(sem, combo.ref, email)
            if new_liaison:
                s.set_liaison(sem, combo.ref, new_liaison)
        self.queue(change, f"Remove {self.name(email)} from {combo.name}"
                   + (f"; {self.name(new_liaison)} becomes the liaison" if new_liaison else "") + ".", combo=combo.name,
                   people=[email, new_liaison])

    def restore_member(self):
        kind, combo, email = self.selected()
        if kind != "removed":
            return
        self.queue(lambda s: s.add_member(self.data["settings"].semester_name, combo.ref, email),
                   f"Put {self.name(email)} back in {combo.name}.", combo=combo.name, people=[email])

    def make_liaison(self):
        kind, combo, email = self.selected()
        if kind == "combo" and combo.members:                     # a combo picked: choose from its members
            email = self.choose_liaison(combo, sorted(combo.members), f"Liaison of {combo.name}:", combo.liaison)
        elif kind != "person":
            dialogs.showinfo("Make liaison", "Open a combo and pick the member who should be its liaison.")
            return
        if not email or email == combo.liaison:
            return
        self.queue(lambda s: s.set_liaison(self.data["settings"].semester_name, combo.ref, email),
                   f"{self.name(email)} becomes the liaison of {combo.name}.", combo=combo.name,
                   people=[email, combo.liaison])

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
            dialogs.showinfo("Withdraw a combo", "Pick the combo to withdraw (or one of its members).")
            return
        swaps = self.get_swaps()
        if swaps and swaps.pending:
            dialogs.showinfo("Withdraw a combo", "The schedule has unsaved changes (Schedule and Swaps tabs). "
                                                   "Confirm or discard them first, then withdraw.")
            return
        shows = sorted((d, k) for d, row in self.data["sets"].items() for k, c in row.items() if c == combo.id)
        sup = [d for d, _ in shows if d in self.data["supervised"]]
        text = f"Withdraw {combo.name}? It won't be scheduled; its number stays reserved (the numbering keeps a gap)."
        if shows:
            text += ("\n\nIts shows: " + ", ".join(f"{make_label(d)} (set {k})" for d, k in shows) + ". When you "
                     "confirm, these sets become OPEN in the schedule (a backup is kept): volunteers can claim them, or give one to a "
                     "combo in the Schedule tab (who could take it).")
        if sup:
            text += ("\n\n\u26a0 " + ", ".join(make_label(d) for d in sup) + (" is a feedback night" if len(sup) == 1
                     else " are feedback nights") + ", which must be full: give that set to another combo.")
        text += "\n\nYou can put the combo back here."
        if not dialogs.askyesno("Withdraw a combo", text, yes="Withdraw", no="Cancel", icon="warning"):
            return
        settings = self.data["settings"]
        self.queue(lambda s: s.set_withdrawn(settings.semester_name, combo.ref, True),
                   f"Withdraw {combo.name}" + (f" ({len(shows)} set(s) become open)." if shows else "."),
                   combo=combo.name, withdraw=(combo.name, combo.ref))

    def put_back(self):
        kind, combo, _ = self.selected()
        if kind != "withdrawn":
            return
        if self.data["sets"] and not dialogs.askyesno(
                "Put a combo back", f"Put {combo.name} back?\n\n\u26a0 This does NOT give it its shows back: the schedule "
                "isn't made again. Its sets were opened when it was withdrawn (others may have taken them since), so "
                f"{combo.name} will have no shows. It can then claim open sets (Swaps tab), or you can give it sets "
                "(Schedule tab).", yes="Put it back", no="Cancel", icon="warning"):
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
        dialogs.grab(win)
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

    def write_exports(self):
        """Combos.pdf and Combos.xlsx brought up to date (after saved changes), quietly: one open elsewhere is left."""
        from outputs.combos_xlsx import write_combos_xlsx
        combos = sorted(self.data["combos"].values(), key=lambda c: c.name)
        args = (combos, self.coach_name, self.data["settings"].semester_name, self.data["instruments"])   # (titles)
        try:
            write_combos_xlsx(export_path(self.get_folder(), COMBOS_XLSX), *args, self.data["shows"])
        except (OSError, PermissionError):
            pass
        try:
            from outputs.combos_pdf import write_combos_pdf
            write_combos_pdf(export_path(self.get_folder(), COMBOS_PDF), *args)
        except (ImportError, OSError, PermissionError):
            pass

    def saved_first(self):
        """Before an export with pending changes: save them first? True = saved, go ahead."""
        return dialogs.askokcancel(
            "Unsaved changes", "Some changes here aren't saved yet. Save them first, then export?",
            ok="Save and export") and self.confirm()

    def export_pdf(self):
        if not self.data:
            dialogs.showinfo("Combo list", "Nothing loaded yet.")
            return
        if self.pending and not self.saved_first():
            return
        try:
            from outputs.combos_pdf import write_combos_pdf
        except ImportError:
            dialogs.showerror("Combo list", "The PDF needs the reportlab package: Run tab > Install missing packages.")
            return
        path = export_path(self.get_folder(), COMBOS_PDF)
        combos = sorted(self.data["combos"].values(), key=lambda c: c.name)
        try:
            write_combos_pdf(path, combos, self.coach_name, self.data["settings"].semester_name, self.data["instruments"])
        except PermissionError:
            dialogs.showerror("Combo list", f"Can't write {path.name}: it's open in another program. Close it and "
                                               "try again.")
            return
        self.info.configure(text=f"Wrote {path.name}.")
        if self.open_path:
            self.open_path(path)

    def export_xlsx(self):
        """Combos.xlsx: one table per combo (members by instrument with emails, the liaison marked, the supervisor),
        then opens it."""
        if not self.data:
            dialogs.showinfo("Combo list", "Nothing loaded yet.")
            return
        if self.pending and not self.saved_first():
            return
        from outputs.combos_xlsx import write_combos_xlsx
        path = export_path(self.get_folder(), COMBOS_XLSX)
        combos = sorted(self.data["combos"].values(), key=lambda c: c.name)
        try:
            write_combos_xlsx(path, combos, self.coach_name, self.data["settings"].semester_name, self.data["instruments"],
                              self.data["shows"])
        except PermissionError:
            dialogs.showerror("Combo list", f"Can't write {path.name}: it's open in Excel. Close it and try again.")
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
        self.shown = {e for c in panel.data["combos"].values() for e in c.members | {c.professor}}   # on the tab
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
        self.hints = {}
        for r, (label, widget, hint) in enumerate(rows, start=1):
            ttk.Label(box, text=label).grid(row=2 * r - 1, column=0, sticky="w", padx=(0, 12), pady=(6, 0))
            widget.grid(row=2 * r - 1, column=1, sticky="w", pady=(6, 0))
            self.hints[label] = ttk.Label(box, text=hint, style="Hint.TLabel", wraplength=420, justify="left")
            self.hints[label].grid(row=2 * r, column=1, sticky="w")
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
        self.usual = panel.store.usual_instruments()       # someone known: their instrument is filled in
        self.instrument_typed = False
        self.instrument.bind("<Key>", lambda _: setattr(self, "instrument_typed", True))
        self.instrument.bind("<<ComboboxSelected>>", lambda _: setattr(self, "instrument_typed", True))
        self.find.focus_set()
        dialogs.grab(win)

    def filter(self, event=None):
        """Narrows the list to what's typed; typing a whole email fills in the Email field too."""
        q = self.find.get().strip().lower()
        self.find.configure(values=[c for c in self.choices if all(w in c.lower() for w in q.split())] if q
                            else self.choices)
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
        known = EMAIL_RE.fullmatch(e) and e in self.shown
        self.name.configure(state="normal")
        if known:                                     # someone already known: their name is changed on the tab
            self.name.delete(0, "end")
            self.name.insert(0, self.known[e])
            self.name.configure(state="readonly")
            self.name_typed = False
            self.hints["Name"].configure(text="Already known. To change their name, right-click them on the Combos "
                                              "tab > Change name.")
        else:
            self.hints["Name"].configure(text="Guessed from the email; change it if needed.")
        if not self.instrument_typed:                 # their usual instrument (can still be changed)
            self.instrument.set(self.usual.get(e, "") if EMAIL_RE.fullmatch(e) else "")
            if not self.name_typed:
                self.name.delete(0, "end")
                if EMAIL_RE.fullmatch(e):
                    self.name.insert(0, name_from_email(e))
        warnings = []
        if EMAIL_RE.fullmatch(e):
            if e in self.combo.members:
                warnings = [f"Already in {self.combo.name}."]
            else:
                warnings = (email_warnings(e, self.panel.data["rules"], self.known)
                            + self.panel.warnings_for(self.combo, e))
        self.warn.configure(text="\n".join(warnings))

    def add(self):
        e, panel = self.clean_email(), self.panel
        if not EMAIL_RE.fullmatch(e):
            dialogs.showerror("Add a member", "Type an email address (or pick someone from the list).",
                                 parent=self.win)
            return
        if e in self.combo.members:
            dialogs.showinfo("Add a member", f"{panel.name(e)} is already in {self.combo.name}.", parent=self.win)
            return
        typos = email_warnings(e, panel.data["rules"], self.known)
        if typos and not dialogs.askyesno("Add a member", "\n".join(typos), yes="Add anyway", no="Go back",
                                          icon="warning", default="no", parent=self.win):
            return
        sem, name, instrument = panel.data["settings"].semester_name, self.name.get().strip(), self.instrument.get().strip()

        def change(store):
            store.add_member(sem, self.combo.ref, e)
            if e not in self.shown and name and name != (panel.data["names"].get(e) or name_from_email(e)):
                store.set_name(e, name)
            if instrument:
                store.set_instrument(sem, self.combo.name, e, instrument)
        clashes = panel.warnings_for(self.combo, e)
        self.win.destroy()
        panel.queue(change, f"Add {name or panel.name(e)} to {self.combo.name}."
                    + (f" Note: {' '.join(clashes)}" if clashes else ""), combo=self.combo.name, people=[e])


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
        ttk.Label(box, text="Its liaison, other members and coach by email. It gets the next number.",
                  style="Hint.TLabel", wraplength=440,
                  justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))
        self.liaison, self.supervisor = ttk.Entry(box, width=46), ttk.Entry(box, width=46)
        self.members = tk.Text(box, width=46, height=6, relief="solid", borderwidth=1, wrap="word")
        self.first_year = tk.BooleanVar()
        rows = [("Liaison", self.liaison, "Their email."),
                ("Other members", self.members, "Emails: one per line, or pasted from anywhere."),
                ("Coach", self.supervisor, "Their email (optional now).")]
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
        dialogs.grab(win)

    def clean(self, text, supervisor=False):
        """The emails in text, lowercased, with the app's email fixes. Students' also get the settings' domain fixes
        (older settings may have some, e.g. mcgill.ca -> mail.mcgill.ca); a supervisor's never do: that would turn a
        professor's mcgill.ca address into a student one (the approvals sheet is read the same way)."""
        p = self.panel
        norm = (lambda m: m.strip().lower()) if supervisor else p.data["rules"].norm
        return [p.store.fix_email(norm(m)) for m in EMAIL_RE.findall(text)]

    def add(self):
        p = self.panel
        liaison = self.clean(self.liaison.get())
        if not liaison:
            dialogs.showerror("New combo", "Type the liaison's email.", parent=self.win)
            return
        members = [e for e in dict.fromkeys(self.clean(self.members.get("1.0", "end"))) if e != liaison[0]]
        sup = self.clean(self.supervisor.get(), supervisor=True)
        if self.supervisor.get().strip() and not sup:
            dialogs.showerror("New combo", "The coach's email doesn't look like an email address.",
                                 parent=self.win)
            return
        liaison, sup, fy = liaison[0], sup[0] if sup else "", self.first_year.get()
        sem = p.data["settings"].semester_name
        known, rules = p.known_people(), p.data["rules"]
        warns = [w for e in [liaison] + members for w in email_warnings(e, rules, known)]
        warns += email_warnings(sup, rules, known, supervisor=True) if sup else []
        few = p.data["settings"].min_members_per_combo
        if few and 1 + len(members) < few:
            warns.append(f"{1 + len(members)} member(s): fewer than the {few} the settings expect.")
        if warns and not dialogs.askyesno("New combo", "Check these first:\n\n" + "\n".join(
                f"\u2022 {w}" for w in warns), yes="Add anyway", no="Go back", icon="warning", default="no",
                parent=self.win):
            return
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
    not sent through the form). A pending change."""

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
                            "make it after all).", style="Hint.TLabel",
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
        dialogs.grab(win)

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
        p.queue(change, f"{p.name(email)}'s conflicts: {', '.join(words)}.", combo=p.combos_of(email),
                people=[email])


class LinkDialog:
    """Which sheets the forms fill are read: Approvals (accepted combos) and Conflicts. Each can be linked or not
    (not: combos and conflicts are only the ones entered in the app). Each is the data folder's file with the usual
    name until another is chosen (any file, any name). Linking is kept for the data folder (every computer); a chosen
    file is this computer's (the same file has another path on each computer)."""

    WHAT = {"approvals": ("Approvals", "the combos accepted through the sign-up form"),
            "conflicts": ("Conflicts", "the nights students said they can't play, from the conflict form")}

    def __init__(self, panel):
        from app_config import is_picked
        self.panel = panel
        folder = panel.get_folder()
        store = Store(folder)
        self.files = input_files(folder)
        self.picked = {w: is_picked(folder, w) for w in self.WHAT}
        self.vars = {w: tk.BooleanVar(value=store.linked(w)) for w in self.WHAT}
        win = self.win = tk.Toplevel(panel.frame)
        win.title("Linked sheets")
        win.transient(panel.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=18)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Linked sheets", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(box, text="The forms can fill two sheets. Linked ones are read on Sync and their combos and conflicts "
                            "show up here, along with the ones entered in the app. Not linked: only what's entered "
                            "here. The sheets themselves are never changed.", style="Hint.TLabel", wraplength=520,
                  justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))
        self.labels = {}
        for r, (which, (title, about)) in enumerate(self.WHAT.items()):
            row = 2 + 3 * r
            ttk.Checkbutton(box, text=f"Link the {title} sheet: {about}", variable=self.vars[which]).grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self.labels[which] = ttk.Label(box, text="", style="Hint.TLabel")
            self.labels[which].grid(row=row + 1, column=0, sticky="w", padx=(26, 0))
            ttk.Button(box, text="Choose...", command=lambda w=which: self.choose(w)).grid(row=row + 1, column=2,
                                                                                         padx=(8, 0))
        bar = ttk.Frame(box)
        bar.grid(row=9, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="OK", style="Accent.TButton", command=self.ok).pack(side="right", padx=(0, 6))
        box.columnconfigure(0, weight=1)
        self.show()
        dialogs.grab(win)

    def show(self):
        folder = self.panel.get_folder()
        for which, label in self.labels.items():
            path = self.files[which]
            try:
                text = f"{path.relative_to(folder).as_posix()} in the data folder"
            except ValueError:
                text = str(path)
            label.configure(text=text + ("" if path.exists() else "   (not there yet)"))

    def choose(self, which):
        from tkinter import filedialog
        from data_folder import APPROVALS_FILE, CONFLICTS_FILE, OLD_APPROVALS_FILE
        current = self.files[which]
        path = filedialog.askopenfilename(parent=self.win, title=f"The {self.WHAT[which][0]} sheet",
                                          initialdir=str(current.parent if current.parent.is_dir() else
                                                         self.panel.get_folder()),
                                          filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
        if not path:
            return
        from pathlib import Path
        path = Path(path)
        other = "conflicts" if which == "approvals" else "approvals"
        others = [CONFLICTS_FILE] if which == "approvals" else [APPROVALS_FILE, OLD_APPROVALS_FILE]
        if path.name.lower() in [n.lower() for n in others] or path == self.files[other]:
            dialogs.showerror("Wrong sheet", f"{path.name} is the {other} sheet. Choose the "
                                 f"{self.WHAT[which][0].lower()} one here.", parent=self.win)
            return
        self.files[which], self.picked[which] = path, True
        self.vars[which].set(True)
        self.show()

    def ok(self):
        from app_config import pick_input_file
        from data_folder import usual_inputs
        folder = self.panel.get_folder()
        try:
            store = Store(folder)
            for which, var in self.vars.items():
                store.set_linked(which, var.get())
            store.save()
        except (OSError, ValueError) as e:
            dialogs.showerror("Linked sheets", str(e), parent=self.win)
            return
        for which in self.WHAT:
            usual = usual_inputs(folder)[which]
            pick_input_file(folder, which, None if not self.picked[which] or self.files[which] == usual
                            else self.files[which])
        app_log.write("Linked sheets: " + ", ".join(f"{w} {'on' if v.get() else 'off'} ({self.files[w]})"
                                                    for w, v in self.vars.items()))
        self.win.destroy()
        self.panel.load()
        if self.panel.on_change:
            self.panel.on_change()
