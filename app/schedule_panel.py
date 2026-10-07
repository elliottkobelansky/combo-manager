"""The Schedule tab of scheduler_app.py: every show night and its sets, including changes still pending in the
Swaps tab (highlighted), with shortcuts into the Swaps tab and Export PDF / Export Excel buttons (export, then open).

It shows the Swaps tab's schedule (the saved schedule plus pending changes), so the two tabs always agree. Adding a
claim only adds a pending change, and the exports ask what to do with unsaved changes first. The one thing saved
straight away: text typed into an open set (e.g. "Jam session"), or clearing it.
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_log
from core.model import make_label
from core.swaps import claimers
from data_folder import CONTACTS_XLSX, SCHEDULE_PDF, SCHEDULE_XLSX
from theme import in_background, popup, scrolled_tree


class SchedulePanel:
    def __init__(self, parent, swaps, goto_swaps, export, open_export, get_palette=lambda: {}, open_file=None,
                 make=None, check=None):
        """export(done): rebuilds Schedule.pdf and .xlsx, then done(code); open_export(name) opens one of them;
        make / check: the Make schedule and Check schedule steps."""
        self.swaps, self.goto_swaps, self.export, self.open_export = swaps, goto_swaps, export, open_export
        self.make, self.check = make or (lambda: None), check or (lambda: None)
        self.open_file = open_file or (lambda path: None)
        self.get_palette = get_palette
        self.rows = {}                                    # tree item -> (night, set number)
        self.night_rows = {}                              # tree item -> night (the bold rows)
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        # the steps: make (once), check (any time), the lock once it's out, and the files
        tools = ttk.Frame(self.frame)
        tools.pack(fill="x", pady=(0, 12))
        self.make_button = ttk.Button(tools, text="Make schedule", style="Accent.TButton", command=self.make)
        self.make_button.pack(side="left")
        self.check_button = ttk.Button(tools, text="Check schedule", command=self.check)
        self.check_button.pack(side="left", padx=(6, 0))
        self.sent = tk.BooleanVar()
        self.sent_box = ttk.Checkbutton(tools, text="Sent to students (no new schedule can be made)",
                                        variable=self.sent, command=self.set_sent)
        self.sent_box.pack(side="left", padx=(16, 0))
        ttk.Button(tools, text="Open Excel", style="Accent.TButton",
                   command=lambda: self.export_file(SCHEDULE_XLSX)).pack(side="right")
        ttk.Button(tools, text="Open PDF", style="Accent.TButton",
                   command=lambda: self.export_file(SCHEDULE_PDF)).pack(side="right", padx=(0, 6))
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
        ttk.Button(self.pending_bar, text="Confirm changes", style="Accent.TButton",
                   command=lambda: self.swaps.save_all()).pack(side="right")
        self.pending_anchor = ttk.Frame(self.frame)      # keeps the bar's place between the search row and the hint
        self.pending_anchor.pack(fill="x")

        hint = ttk.Label(self.frame, text="Double-click a combo's set to find swaps for it; double-click an open set to "
                                          "see who could take it; right-click a night to copy its emails or a summary, or an open set to type text "
                                          "in it (e.g. Jam session). Changes not saved yet are highlighted.", style="Hint.TLabel", justify="left")
        hint.pack(anchor="w", fill="x", pady=(8, 0))
        self.frame.bind("<Configure>", lambda e: hint.configure(wraplength=max(e.width - 20, 200)), add="+")

        table, self.tree = scrolled_tree(self.frame, [("#0", "Night / set", 230, False), ("time", "Time", 120, False),
                                                      ("who", "Playing", 320, True), ("note", "", 200, True)])
        table.pack(fill="both", expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", self.double_click)
        self.tree.bind("<Button-3>", self.right_click)

        bottom = self.bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Expand all", command=lambda: self.expand(True)).pack(side="left")
        ttk.Button(bottom, text="Collapse all", command=lambda: self.expand(False)).pack(side="left", padx=6)
        ttk.Button(bottom, text="Export contact lists", command=self.export_contacts).pack(side="left", padx=(12, 0))
        self.status = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.status.pack(side="left", padx=10)
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
        self.tree.tag_configure("pending", foreground=p["accent"], font=(ui_font(), size(10), "bold"))

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
            title = f"{make_label(n.date)}  ·  {n.venue}" + ("  ·  PROF" if n.date in sup else "")
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
            self.pending_label.configure(text=f"{pending} unsaved change{'s' if pending > 1 else ''} (highlighted below)")
            self.pending_bar.pack(fill="x", pady=(10, 0), after=self.pending_anchor)
        else:
            self.pending_bar.pack_forget()
        self.info.configure(text=f"{shown} of {len(st['nights'])} nights · {open_total} open sets"
                                 + (f" · {pending} unsaved change(s)" if pending else ""))

    def refresh_tools(self):
        """The Make button is the main one only before there's a schedule; after that it's a plain 'Make a new
        schedule...', and off while the schedule is marked as sent to students."""
        st = self.swaps.state
        exists, sent = bool(st), bool(st and st.get("published"))
        self.sent.set(sent)
        self.sent_box.configure(state="normal" if exists else "disabled")
        self.make_button.configure(text="Make a new schedule..." if exists else "Make schedule",
                                   style="TButton" if exists else "Accent.TButton",
                                   state="disabled" if sent else "normal")
        self.check_button.configure(style="Accent.TButton" if exists else "TButton",
                                    state="normal" if exists else "disabled")
        if sent:
            self.tools_hint.configure(text="The schedule is out: Make a new schedule is off. Changes from now on: "
                                           "Swaps tab (or untick 'Sent to students' to start over).")
            self.tools_hint.pack(fill="x", pady=(0, 8), after=self.tools_anchor)
        else:
            self.tools_hint.pack_forget()

    def set_sent(self):
        """The 'Sent to students' tick: saved with the schedule (every computer sees it). Unticking asks first: it
        lets a new schedule be made again."""
        from schedule_file import set_published
        if not self.sent.get() and not messagebox.askyesno(
                "Unlock the schedule?", "The schedule is marked as sent to students. Unticking this lets a brand-new "
                "schedule be made again, which would replace the one students have: almost every show would move.\n\n"
                "For changes to the schedule students already have, use the Swaps tab instead.\n\nUnlock it anyway?",
                icon="warning", default="no"):
            self.sent.set(True)
            return
        try:
            set_published(self.swaps.get_folder(), self.sent.get())
        except OSError as e:
            messagebox.showerror("Couldn't save", str(e))
        if self.swaps.state:
            self.swaps.state["published"] = self.sent.get()
        app_log.write("Schedule marked as sent to students" if self.sent.get() else
                      "Schedule unmarked as sent to students")
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
        night = self.night_rows.get(item) or (slot[0] if slot else None)
        if not night:
            return
        menu = self.menu()
        label = make_label(night)
        menu.add_command(label=f"Copy liaison emails ({label})", command=lambda: self.copy(night, "liaisons"))
        menu.add_command(label=f"Copy combo emails ({label}: students and supervisors)",
                         command=lambda: self.copy(night, "everyone"))
        menu.add_command(label=f"Copy night summary ({label})", command=lambda: self.copy(night, "summary"))
        if not slot:
            popup(menu, event.x_root, event.y_root)
            return
        menu.add_separator()
        d, k = slot
        st = self.swaps.state
        c = st["sets"].get(d, {}).get(k)
        if c:
            menu.add_command(label="Find swaps / moves...", command=lambda: self.goto_swaps(c, d, k, "swap"))
            menu.add_command(label="Give it away...", command=lambda: self.goto_swaps(c, d, k, "give"))
        else:
            text = st["typed"].get(d, {}).get(k)
            if not text:
                menu.add_command(label="Who could take this set?", command=lambda: self.show_claimers(item, d, k))
            if (self.swaps.base_sets or {}).get(d, {}).get(k) is not None:   # opened by a change not saved yet
                menu.add_command(label="(Confirm the pending changes first to type text in this set)",
                                 state="disabled")
            elif text:
                menu.add_command(label="Change the text in this set...", command=lambda: self.edit_text(d, k))
                menu.add_command(label="Clear the text (the set is open again)",
                                 command=lambda: self.edit_text(d, k, clear=True))
            else:
                menu.add_command(label="Type text in this set (e.g. Jam session)...",
                                 command=lambda: self.edit_text(d, k))
        popup(menu, event.x_root, event.y_root)

    def edit_text(self, d, k, clear=False):
        """Types text into an open set (it's shown on the calendar and the set counts as taken), changes it, or
        clears it. Saved straight away (a backup first), then the exports are rebuilt."""
        from schedule_file import ScheduleFileError, save_changes
        st = self.swaps.state
        current = st["typed"].get(d, {}).get(k, "")
        if clear:
            text = ""
        else:
            text = simpledialog.askstring(
                "Text in a set", f"{make_label(d)}, set {k}: the text to show instead of a combo (e.g. Jam session). "
                "The set then counts as taken. Leave it empty to open the set again.", initialvalue=current,
                parent=self.frame)
            if text is None or text.strip() == current:
                return
        try:
            save_changes(self.swaps.get_folder(), st["combos"], typed={(d, k): text},
                         what=[f"Text in {make_label(d)} set {k}: " + (f"'{text.strip()}'" if text.strip() else "cleared")])
        except ScheduleFileError as e:
            messagebox.showerror("Couldn't save", str(e))
            return
        app_log.write(f"Schedule tab: {make_label(d)} set {k} " + (f"says '{text.strip()}'" if text.strip() else
                                                                    "is open again"))
        if text.strip():
            st["typed"].setdefault(d, {})[k] = text.strip()
        else:
            st["typed"].get(d, {}).pop(k, None)
        self.refresh()
        self.status.configure(text=(f"Saved: {make_label(d)} set {k} says '{text.strip()}'." if text.strip() else
                                    f"Saved: {make_label(d)} set {k} is open again.") + " Rebuilding the exports...")
        self.export(lambda code: self.status.configure(text=self.status.cget("text").replace(
            " Rebuilding the exports...", " Exports rebuilt.")))

    # contact lists
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
            lines = [f"{make_label(d)}, {n.venue}" + (" (a professor attends)" if info["supervised"] else "")]
            for k, when, who, names in info["sets"]:
                lines.append(f"  {when or f'Set {k}'}  {who}" + (f": {', '.join(names)}" if names else ""))
            text, msg = "\n".join(lines), "the night summary"
        from clipboard import copy
        copy(self.frame, text, f"{msg} for {make_label(d)}", self.get_palette())
        unsaved = any((d, k) in self.swaps.changed_cells() for k, _, _, _ in info["sets"])
        self.status.configure(text=f"Copied {msg} for {make_label(d)}: paste with Ctrl+V."
                                   + (" (Includes unsaved changes.)" if unsaved else ""))
        self.last_copied = text                       # (kept for tests)

    def export_contacts(self):
        """Contact lists.xlsx: one row per night with everyone's emails, for printing or sharing."""
        st = self.swaps.state
        if not st:
            messagebox.showinfo("Contact lists", "Nothing loaded yet.")
            return
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Nights"
        ws.append(["Date", "Day", "Venue", "Supervised", "Sets (time, combo: members)", "Student emails",
                   "Supervisor emails"])
        for n in st["nights"]:
            info = self.night_info(n.date)
            sets = "\n".join(f"{when or f'Set {k}'}  {who}" + (f": {', '.join(names)}" if names else "")
                             for k, when, who, names in info["sets"])
            ws.append([n.date, n.weekday, n.venue, "Yes" if info["supervised"] else "", sets,
                       "; ".join(info["students"]), "; ".join(info["supervisors"])])
        for c in ws[1]:
            c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="DDEBF7")
        for row in ws.iter_rows(min_row=2):
            row[0].number_format = "yyyy-mm-dd"
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        for col, w in zip("ABCDEFG", (12, 11, 12, 11, 70, 60, 30)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
        path = self.swaps.get_folder() / CONTACTS_XLSX
        try:
            wb.save(path)
        except PermissionError:
            messagebox.showerror("Contact lists", f"Can't write {path.name}: it's open in Excel. Close it and try again.")
            return
        self.status.configure(text=f"Wrote {path.name}" + (" (includes unsaved changes)" if self.swaps.pending else "")
                                   + ".")
        self.open_file(path)

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
            answer = messagebox.askyesnocancel(
                "Unsaved changes", f"There are {len(self.swaps.pending)} unsaved change(s).\n\n"
                "Yes: save them into the schedule first, then export.\nNo: export the saved schedule only (your "
                "changes stay pending).\nCancel: do nothing.")
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
