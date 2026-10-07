"""The Schedule tab of scheduler_app.py: every show night and its sets, including changes still pending in the
Swaps tab (highlighted), with shortcuts into the Swaps tab and Export PDF / Export Excel buttons (export, then open).

It shows the Swaps tab's schedule (the saved schedule plus pending changes), so the two tabs always agree. Adding a
claim only adds a pending change, and the exports ask what to do with unsaved changes first. The one thing saved
straight away: text typed into an open set (e.g. "Jam session"), or clearing it.
"""
import tkinter as tk
from tkinter import simpledialog, ttk

import app_log
import dialogs
from core.model import make_label
from core.swaps import claimers
from data_folder import SCHEDULE_PDF, SCHEDULE_XLSX
from theme import RIGHT_CLICK, in_background, popup, scrolled_tree


class SchedulePanel:
    def __init__(self, parent, swaps, goto_swaps, export, open_export, get_palette=lambda: {}, open_file=None,
                 make=None, check=None, goto_combo=None):
        """export(done): rebuilds Schedule.pdf and .xlsx, then done(code); open_export(name) opens one of them;
        make / check: the Make schedule and Check schedule steps; goto_combo(id): shows a combo on the Combos tab."""
        self.swaps, self.goto_swaps, self.export, self.open_export = swaps, goto_swaps, export, open_export
        self.make, self.check = make or (lambda: None), check or (lambda: None)
        self.open_file = open_file or (lambda path: None)
        self.goto_combo = goto_combo or (lambda cid: None)
        self.is_busy = lambda: False                      # set by the app: a step is running in the background
        self.get_palette = get_palette
        self.rows = {}                                    # tree item -> (night, set number)
        self.night_rows = {}                              # tree item -> night (the bold rows)
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        # the steps: make (once), check (any time), the lock once it's out
        tools = ttk.Frame(self.frame)
        tools.pack(fill="x", pady=(0, 12))
        self.make_button = ttk.Button(tools, text="Make schedule", style="Accent.TButton", command=self.make)
        self.make_button.pack(side="left")
        self.check_button = ttk.Button(tools, text="Check schedule", command=self.check)
        self.check_button.pack(side="left", padx=(6, 0))
        self.versions_button = ttk.Button(tools, text="Earlier versions...", command=self.show_versions)
        self.versions_button.pack(side="left", padx=(6, 0))
        self.sent = tk.BooleanVar()
        self.sent_box = ttk.Checkbutton(tools, text="Lock schedule",
                                        variable=self.sent, command=self.set_sent)
        self.sent_box.pack(side="left", padx=(16, 0))
        self.tools_hint = ttk.Label(self.frame, text="", style="Hint.TLabel")   # shown while it's locked
        self.tools_anchor = tools

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(top, textvariable=self.search, width=28).pack(side="left", padx=(6, 0))
        self.only_open = tk.BooleanVar()
        ttk.Checkbutton(top, text="Only nights with open sets", variable=self.only_open,
                        command=self.toggle_only_open).pack(side="left", padx=14)
        self.info = ttk.Label(top, text="", style="Hint.TLabel")
        self.info.pack(side="left", padx=6)
        # shown only while swap changes are waiting to be saved
        self.pending_bar = ttk.Frame(self.frame, style="Card.TFrame", padding=(12, 8))
        self.pending_label = ttk.Label(self.pending_bar, text="", style="CardTitle.TLabel")
        self.pending_label.pack(side="left")
        ttk.Button(self.pending_bar, text="Discard all", command=lambda: self.swaps.discard_all()).pack(side="right")
        ttk.Button(self.pending_bar, text="Undo last", command=lambda: self.swaps.undo_last()).pack(side="right", padx=6)
        self.confirm_button = ttk.Button(self.pending_bar, text="Confirm changes", style="Accent.TButton",
                                         command=lambda: self.swaps.save_all())
        self.confirm_button.pack(side="right")
        self.pending_anchor = ttk.Frame(self.frame)      # keeps the bar's place between the search row and the hint
        self.pending_anchor.pack(fill="x")


        table, self.tree = scrolled_tree(self.frame, [("#0", "Night / set", 230, False), ("time", "Time", 120, False),
                                                      ("who", "Playing", 320, True), ("note", "", 200, True)])
        table.pack(fill="both", expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", self.double_click)

        bottom = self.bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Expand all", command=lambda: self.expand(True)).pack(side="left")
        ttk.Button(bottom, text="Collapse all", command=lambda: self.expand(False)).pack(side="left", padx=6)
        self.actions = ttk.Button(bottom, text="Actions \u25be", command=self.actions_menu)   # = the right-click menu
        self.actions.pack(side="left", padx=(6, 0))
        self.file_buttons = [
            ttk.Button(bottom, text="Open Excel", style="Accent.TButton", command=lambda: self.export_file(SCHEDULE_XLSX)),
            ttk.Button(bottom, text="Open PDF", style="Accent.TButton", command=lambda: self.export_file(SCHEDULE_PDF))]
        self.file_buttons[0].pack(side="right")
        self.file_buttons[1].pack(side="right", padx=(0, 6))
        self.status = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.status.pack(side="left", padx=10)
        for ev in RIGHT_CLICK:                            # on the list only: the tab's own steps stay buttons
            self.tree.bind(ev, self.right_click)
        self.recolor()
        swaps.listeners.append(self.refresh)

    def recolor(self):
        p = self.get_palette()
        if not p:
            return
        from theme import size, size_columns, ui_font
        self.tree.tag_configure("band0", background=p["panel"])
        self.tree.tag_configure("band1", background=p["band"])
        size_columns(self.tree)
        self.tree.tag_configure("night", font=(ui_font(), size(10), "bold"))
        self.tree.tag_configure("open", foreground=p["muted"])
        self.tree.tag_configure("pending", foreground=p["accent_fg"], font=(ui_font(), size(10), "bold"))

    # the table
    def refresh(self):
        st = self.swaps.state
        expanded = {self.tree.item(i, "text") for i in self.tree.get_children() if self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.night_rows.clear()
        self.refresh_tools()
        if not st:
            self.info.configure(text=self.swaps.info.cget("text"))
            self.pending_bar.pack_forget()
            return
        sets, typed, sup = st["sets"], st["typed"], st["supervised"] or set()
        changed, labels = self.swaps.changed_cells(), self.swaps.labels
        q = self.search.get().strip().lower()
        band, shown, open_total = 0, 0, 0
        for n in st["nights"]:
            row = sets.get(n.date, {})
            lines = []
            for k in range(1, n.n_slots + 1):
                c = row.get(k)
                if c:
                    who, kind = labels.get(c, st["combos"][c].name), "combo"
                elif k in typed.get(n.date, {}):
                    who, kind = typed[n.date][k], "text"
                else:
                    who, kind = "open", "open"
                lines.append((k, who, kind))
            n_open = sum(1 for _, _, kind in lines if kind == "open")
            open_total += n_open
            title = f"{make_label(n.date)}  ·  {n.venue}" + ("  ·  FEEDBACK" if n.date in sup else "")
            if self.only_open.get() and not n_open:
                continue
            if q and q not in (title + " " + " ".join(w for _, w, _ in lines)).lower():
                continue
            band ^= 1
            shade = f"band{band}"
            note = f"{n_open} open" if n_open else ""
            if any((n.date, k) in changed for k, _, _ in lines):
                note = ("unsaved changes" + (f" · {note}" if note else ""))
            night = self.tree.insert("", "end", text=title, values=("", "", note), tags=("night", shade),
                                     open=bool(q) or self.only_open.get() or title in expanded
                                     or any((n.date, k) in changed for k, _, _ in lines))
            self.night_rows[night] = n.date
            for k, who, kind in lines:
                tags = [shade] + (["pending"] if (n.date, k) in changed else ["open"] if kind == "open" else [])
                item = self.tree.insert(night, "end", text=f"    Set {k}", tags=tuple(tags),
                                        values=(n.set_range(k), who, "unsaved" if (n.date, k) in changed else
                                                "text, not a combo" if kind == "text" else ""))
                self.rows[item] = (n.date, k)
            shown += 1
        pending = len(self.swaps.pending)
        if pending:
            self.pending_label.configure(text="\u25cf Unsaved changes")
            self.pending_bar.pack(fill="x", pady=(10, 0), after=self.pending_anchor)
        else:
            self.pending_bar.pack_forget()
        self.info.configure(text=f"{shown} of {len(st['nights'])} nights · {open_total} open sets")

    def refresh_tools(self):
        """The Make button: 'Make schedule' before there's a schedule, 'Make a new schedule...' after; blue, and grey
        (off) while the schedule is locked or a step runs."""
        st = self.swaps.state
        exists, sent = bool(st), bool(st and st.get("published"))
        self.sent.set(sent)
        self.sent_box.configure(state="normal" if exists else "disabled")
        self.make_button.configure(text="Make a new schedule..." if exists else "Make schedule",
                                   style="Accent.TButton",     # blue; grey while locked or a step runs
                                   state="disabled" if sent else "normal")
        self.check_button.configure(style="Accent.TButton" if exists else "TButton",
                                    state="normal" if exists else "disabled")
        self.versions_button.configure(state="normal" if exists else "disabled")
        if self.is_busy():                                # a step is running: these wait for it
            for b in (self.make_button, self.check_button, self.versions_button, self.sent_box):
                b.configure(state="disabled")
        if sent:
            self.tools_hint.configure(text="Locked: Make a new schedule is off. Changes from now on: Swaps tab "
                                           "(or untick 'Lock schedule' to start over).")
            self.tools_hint.pack(fill="x", pady=(0, 8), after=self.tools_anchor)
        else:
            self.tools_hint.pack_forget()

    def set_sent(self):
        """The 'Lock schedule' tick (e.g. once the schedule is final): saved with the schedule (every
        computer sees it). Unticking asks first: it lets a new schedule be made again."""
        from schedule_file import set_published
        if not self.sent.get() and not dialogs.askyesno(
                "Unlock the schedule?", "Unticking this lets a brand-new schedule be made again, which would replace this one: "
                "almost every show would move.\n\nFor changes to this schedule, use the Swaps tab instead.",
                yes="Unlock", no="Keep locked",
                icon="warning", default="no"):
            self.sent.set(True)
            return
        try:
            set_published(self.swaps.get_folder(), self.sent.get())
        except OSError as e:
            dialogs.showerror("Couldn't save", str(e))
        if self.swaps.state:
            self.swaps.state["published"] = self.sent.get()
        app_log.write("Schedule locked" if self.sent.get() else "Schedule unlocked")
        self.refresh_tools()

    def toggle_only_open(self):
        """Ticked: just the nights with open sets, opened. Unticked: every night again, closed (except nights with
        unsaved changes)."""
        self.refresh()
        if not self.only_open.get():
            for item in self.tree.get_children():
                if "unsaved" not in str(self.tree.set(item, "note")):
                    self.tree.item(item, open=False)

    def expand(self, yes):
        for i in self.tree.get_children():
            self.tree.item(i, open=yes)

    # actions
    def slot(self, event=None):
        item = self.tree.identify_row(event.y) if event else (self.tree.selection() or [None])[0]
        if item:
            self.tree.selection_set(item)
        return item, self.rows.get(item)

    def double_click(self, event):
        item, slot = self.slot(event)
        if not slot:
            return
        d, k = slot
        c = self.swaps.state["sets"].get(d, {}).get(k)
        if c:
            self.goto_swaps(c, d, k, "swap")
        elif k not in self.swaps.state["typed"].get(d, {}):
            self.show_claimers(item, d, k)

    def right_click(self, event):
        item, slot = self.slot(event)
        menu = self.build_menu(item, slot)
        if menu:
            popup(menu, event.x_root, event.y_root)

    def actions_menu(self):
        """The Actions button: the right-click menu for the picked night or set, opened above the button."""
        item, slot = self.slot()
        menu = self.build_menu(item, slot)
        if menu is None:
            menu = self.menu()
            menu.add_command(label="Select a night or a set first", state="disabled")
        menu.update_idletasks()
        b = self.actions
        popup(menu, b.winfo_rootx(), max(0, b.winfo_rooty() - menu.winfo_reqheight()))

    def build_menu(self, item, slot):
        """What can be done with a night (copy its emails or a summary) or a set (swaps, who could take it, text
        in it). None when nothing is picked."""
        night = self.night_rows.get(item) or (slot[0] if slot else None)
        if not night:
            return None
        menu = self.menu()
        label = make_label(night)
        menu.add_command(label=f"Copy liaison emails ({label})", command=lambda: self.copy(night, "liaisons"))
        menu.add_command(label=f"Copy all emails ({label})",
                         command=lambda: self.copy(night, "everyone"))
        menu.add_command(label=f"Copy night summary ({label})", command=lambda: self.copy(night, "summary"))
        if not slot:
            return menu
        menu.add_separator()
        d, k = slot
        st = self.swaps.state
        c = st["sets"].get(d, {}).get(k)
        if c:
            menu.add_command(label=f"Go to combo ({st['combos'][c].name})", command=lambda: self.goto_combo(c))
            menu.add_separator()
            menu.add_command(label="Find swaps...", command=lambda: self.goto_swaps(c, d, k, "swap"))
            menu.add_command(label="Give away set...", command=lambda: self.goto_swaps(c, d, k, "give"))
        else:
            text = st["typed"].get(d, {}).get(k)
            if not text:
                menu.add_command(label="Fill set...", command=lambda: self.show_claimers(item, d, k))
            if (self.swaps.base_sets or {}).get(d, {}).get(k) is not None:   # opened by a change not saved yet
                menu.add_command(label="Add text... (confirm changes first)",
                                 state="disabled")
            elif text:
                menu.add_command(label="Edit text...", command=lambda: self.edit_text(d, k))
                menu.add_command(label="Clear text",
                                 command=lambda: self.edit_text(d, k, clear=True))
            else:
                menu.add_command(label="Add text...", command=lambda: self.edit_text(d, k))
        return menu

    def edit_text(self, d, k, clear=False):
        """Types text into an open set (it's shown on the calendar and the set counts as taken), changes it, or
        clears it: an unsaved change, confirmed with the others (Confirm changes)."""
        current = self.swaps.state["typed"].get(d, {}).get(k, "")
        if clear:
            text = ""
        else:
            text = simpledialog.askstring(
                "Text in a set", f"{make_label(d)}, set {k}: the text to show instead of a combo (e.g. Jam session). "
                "The set then counts as taken. Leave it empty to open the set again.", initialvalue=current,
                parent=self.frame)
            if text is None or text.strip() == current:
                return
        self.swaps.add_text(d, k, text)
        self.status.configure(text=f"Not saved yet: {make_label(d)} set {k} "
                                   + (f"says '{text.strip()}'." if text.strip() else "is open again.")
                                   + " (Confirm changes, above)")

    # earlier versions (AppFiles/ScheduleBackups)
    def show_versions(self):
        """The Earlier versions window: the copies kept before each change, what restoring one would undo, and
        Restore."""
        from schedule_file import ScheduleFileError, restore_version, versions
        folder = self.swaps.get_folder()
        found = versions(folder) if self.swaps.state else []
        win = tk.Toplevel(self.frame)
        win.title("Earlier versions")
        win.transient(self.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=20)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Earlier versions of the schedule", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(box, text="A copy is kept each time the schedule changes. Pick one to see what restoring it would "
                            "undo.", style="Hint.TLabel", wraplength=640, justify="left").pack(anchor="w", pady=(2, 10))
        table, tree = scrolled_tree(box, [("#0", "Version", 140, False), ("next", "The change made next", 500, True)])
        table.pack(fill="both", expand=True)
        tree.configure(height=10)
        tree.tag_configure("other", foreground=(self.get_palette() or {}).get("muted"))
        details = ttk.Label(box, text="", wraplength=640, justify="left")
        details.pack(anchor="w", fill="x", pady=(10, 0))
        bar = ttk.Frame(box)
        bar.pack(fill="x", pady=(14, 0))
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
        restore = ttk.Button(bar, text="Restore this version", style="Accent.TButton", state="disabled")
        restore.pack(side="right", padx=(0, 6))

        def when(t):
            return f"{t:%a %b} {t.day}, {t:%H:%M}"
        rows = {}
        for v in found:
            if v.same:
                then = "; ".join(v.since[0]) if v.since else ""
                rows[tree.insert("", "end", text=when(v.replaced), values=(then,))] = v
            else:
                made = v.made[:10]
                rows[tree.insert("", "end", text=when(v.replaced), values=(f"(an earlier schedule, made {made})",),
                                 tags=("other",))] = v
        if not found:
            details.configure(text="No earlier versions yet: one is kept each time the schedule changes.")

        def picked(_=None):
            sel = tree.selection()
            v = rows.get(sel[0]) if sel else None
            restore.configure(state="normal" if v and not self.is_busy() else "disabled")
            if not v:
                return
            if not v.same:
                details.configure(text=f"A different schedule, made {v.made[:10]}, from before Make a new schedule. "
                                       "Restoring it replaces the whole schedule: almost every show would move.")
                return
            done = ["; ".join(w) for w in v.since]
            lines = "\n".join(f"\u2022 {w}" for w in done[:8]) + (f"\n\u2022 ...and {len(done) - 8} more"
                                                                   if len(done) > 8 else "")
            details.configure(text="Restoring it undoes what was done since:\n" + lines if done else
                              "The same as the schedule now.")
        tree.bind("<<TreeviewSelect>>", picked)

        def do_restore():
            sel = tree.selection()
            v = rows.get(sel[0]) if sel else None
            if not v:
                return
            if self.swaps.pending:
                dialogs.showinfo("Earlier versions", "The schedule has unsaved changes: confirm or discard them "
                                    "first.", parent=win)
                return
            if not dialogs.askyesno(
                    "Restore this version?", f"Put back the schedule as it was on {when(v.replaced)}?\n\nThe "
                    "schedule as it is now is kept as a version too, so this can be undone here.",
                    yes="Restore", no="Cancel", icon="warning", default="no", parent=win):
                return
            try:
                restore_version(folder, v)
            except ScheduleFileError as e:
                dialogs.showerror("Couldn't restore", str(e), parent=win)
                return
            app_log.write(f"Schedule tab: restored the version from {when(v.replaced)} ({v.path.name})")
            win.destroy()
            self.swaps.load(quiet=True)
            self.status.configure(text=f"Restored the version from {when(v.replaced)}. Rebuilding the exports...")
            self.export(lambda code: self.status.configure(text=self.status.cget("text").replace(
                " Rebuilding the exports...", " Exports rebuilt.")))
        restore.configure(command=do_restore)
        win.grab_set()

    # a night's emails and summary (copied)
    def night_info(self, d):
        """Who plays on night d (as shown, with unsaved changes): sets, student, liaison and supervisor emails (a combo
        without a liaison: its members as liaisons, named in no_liaison)."""
        st = self.swaps.state
        n = next(x for x in st["nights"] if x.date == d)
        row, combos, name_of = st["sets"].get(d, {}), st["combos"], st["name_of"]
        sets, students, supervisors, liaisons, no_liaison = [], [], [], [], []
        for k in range(1, n.n_slots + 1):
            c = row.get(k)
            if c:
                combo = combos[c]
                people = ([combo.liaison] if combo.liaison else []) + sorted(combo.members - {combo.liaison},
                                                                             key=lambda e: name_of(e).lower())
                sets.append((k, n.set_range(k), combo.name, [name_of(e) for e in people]))
                students += [e for e in people if e not in students]
                if not combo.liaison:
                    no_liaison.append(combo.name)
                liaisons += [e for e in ([combo.liaison] if combo.liaison else people) if e not in liaisons]
                if combo.professor and combo.professor not in supervisors:
                    supervisors.append(combo.professor)
            else:
                text = st["typed"].get(d, {}).get(k)
                sets.append((k, n.set_range(k), text or "open", []))
        return dict(night=n, sets=sets, students=students, supervisors=supervisors, liaisons=liaisons,
                    no_liaison=no_liaison,
                    supervised=bool(st["supervised"] and d in st["supervised"]))

    def copy(self, d, what):
        info = self.night_info(d)
        def count(n, word):
            return f"{n} {word} email{'' if n == 1 else 's'}"
        if what == "everyone":                        # the students (in set order), then the supervisors
            emails = info["students"] + [e for e in info["supervisors"] if e not in info["students"]]
            text, msg = "; ".join(emails), count(len(emails), "combo")
        elif what == "liaisons":
            text, msg = "; ".join(info["liaisons"]), count(len(info["liaisons"]), "liaison") + (
                f" (no liaison for {', '.join(info['no_liaison'])}: all its members instead)" if info["no_liaison"]
                else "")
        else:
            n = info["night"]
            lines = [f"{make_label(d)}, {n.venue}" + (" (a faculty member attends)" if info["supervised"] else "")]
            for k, when, who, names in info["sets"]:
                lines.append(f"  {when or f'Set {k}'}  {who}" + (f": {', '.join(names)}" if names else ""))
            text, msg = "\n".join(lines), "the night summary"
        from clipboard import copy
        copy(self.frame, text, f"{msg} for {make_label(d)}", self.get_palette())
        unsaved = any((d, k) in self.swaps.changed_cells() for k, _, _, _ in info["sets"])
        self.status.configure(text=f"Copied {msg} for {make_label(d)}: paste with Ctrl+V."
                                   + (" (Includes unsaved changes.)" if unsaved else ""))
        self.last_copied = text                       # (kept for tests)

    def menu(self):
        p = self.get_palette() or {}
        return tk.Menu(self.tree, tearoff=0, background=p.get("panel"), foreground=p.get("text"),
                       activebackground=p.get("accent"), activeforeground=p.get("accent_text"))

    def show_claimers(self, item, d, k):
        st = self.swaps.state
        self.frame.configure(cursor="watch")
        in_background(self.frame, lambda: claimers(st["sets"], st["nights"], st["combos"], st["inp"], st["settings"],
                                                   st["supervised"], st["typed"], d, k, st["name_of"]),
                      lambda options: self.claimers_menu(item, d, k, options))

    def claimers_menu(self, item, d, k, options):
        self.frame.configure(cursor="")
        menu = self.menu()
        if not options:
            menu.add_command(label="No combo can take this set", state="disabled")
        legal = [o for o in options if not o.breaks]
        for o in legal[:25] + [o for o in options if o.breaks][:max(0, 25 - len(legal))]:
            cid = o.changes[(d, k)]
            label = self.swaps.labels.get(cid, cid) + (f"   \u2716 breaks a rule: {o.breaks[0]}" if o.breaks else
                                                      f"   ⚠ {o.warnings[0]}" if o.warnings else "")
            menu.add_command(label=label, command=lambda o=o: self.swaps.add_pending(o),
                             foreground=(self.get_palette() or {}).get("bad") if o.breaks else None)
        self.claim_menu = menu                         # (kept for tests)
        x, y, w, h = self.tree.bbox(item, "who") or (0, 0, 0, 0)
        popup(menu, self.tree.winfo_rootx() + x, self.tree.winfo_rooty() + y + h)

    def export_file(self, name):
        """Rebuilds Schedule.pdf and Schedule.xlsx, then opens `name` (one of them)."""
        if self.swaps.pending:
            answer = dialogs.askyesnocancel(
                "Unsaved changes", "Some changes haven't been saved yet. Save them into the schedule first, or "
                "export the saved schedule only (your changes stay unsaved)?", yes="Save and export",
                no="Export saved only")
            if answer is None:
                return
            if answer:
                self.swaps.save_all(then=lambda code: self.open_export(name))   # saving also exports
                return
        self.status.configure(text="Exporting Schedule.pdf and Schedule.xlsx...")

        def done(code):
            self.status.configure(text="Exported; all hard rules hold." if code == 0 else
                                  "Exported, but the rule check found problems: see the Run tab.")
            self.open_export(name)
        self.export(done)
