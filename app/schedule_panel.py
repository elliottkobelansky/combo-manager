"""The Schedule tab of scheduler_app.py: every show night and its sets, including changes still pending in the
Swaps tab (highlighted), with shortcuts into the Swaps tab and an Export PDF button (exports, then opens it).

It shows the Swaps tab's schedule (Schedule.xlsx plus pending changes), so the two tabs always agree, and it never
writes anything by itself: adding a claim only adds a pending change, and Export PDF asks what to do with unsaved
changes first.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from core.model import make_label
from core.swaps import claimers
from data_folder import CONTACTS_XLSX
from theme import in_background, popup, scrolled_tree


class SchedulePanel:
    def __init__(self, parent, swaps, goto_swaps, export, open_pdf, get_palette=lambda: {}, open_file=None):
        self.swaps, self.goto_swaps, self.export, self.open_pdf = swaps, goto_swaps, export, open_pdf
        self.open_file = open_file or (lambda path: None)
        self.get_palette = get_palette
        self.rows = {}                                    # tree item -> (night, set number)
        self.night_rows = {}                              # tree item -> night (the bold rows)
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(top, textvariable=self.search, width=28).pack(side="left", padx=(6, 0))
        self.only_open = tk.BooleanVar()
        ttk.Checkbutton(top, text="Only nights with open sets", variable=self.only_open,
                        command=self.refresh).pack(side="left", padx=14)
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
                                          "see who could take it; right-click a night to copy its emails or a summary. Changes not saved yet are "
                                          "highlighted.", style="Hint.TLabel", justify="left")
        hint.pack(anchor="w", fill="x", pady=(8, 0))
        self.frame.bind("<Configure>", lambda e: hint.configure(wraplength=max(e.width - 20, 200)), add="+")

        table, self.tree = scrolled_tree(self.frame, [("#0", "Night / set", 230, False), ("time", "Time", 120, False),
                                                      ("who", "Playing", 320, True), ("note", "", 200, True)])
        table.pack(fill="both", expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", self.double_click)
        self.tree.bind("<Button-3>", self.right_click)

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Export PDF", style="Accent.TButton", command=self.export_pdf).pack(side="right")
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
                                                "typed in by hand" if kind == "text" else ""))
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
        menu.add_command(label=f"Copy student emails ({label})", command=lambda: self.copy(night, "students"))
        menu.add_command(label=f"Copy supervisor emails ({label})", command=lambda: self.copy(night, "supervisors"))
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
        elif k not in st["typed"].get(d, {}):
            menu.add_command(label="Who could take this set?", command=lambda: self.show_claimers(item, d, k))
        else:
            menu.add_command(label="(Typed in by hand: change it in Schedule.xlsx)", state="disabled")
        popup(menu, event.x_root, event.y_root)

    # contact lists
    def night_info(self, d):
        """Who plays on night d (as shown, with unsaved changes): sets, student and supervisor emails."""
        st = self.swaps.state
        n = next(x for x in st["nights"] if x.date == d)
        row, combos, name_of = st["sets"].get(d, {}), st["combos"], st["name_of"]
        sets, students, supervisors = [], [], []
        for k in range(1, n.n_slots + 1):
            c = row.get(k)
            if c:
                combo = combos[c]
                people = [combo.liaison] + sorted(combo.members - {combo.liaison}, key=lambda e: name_of(e).lower())
                sets.append((k, n.set_range(k), combo.name, [name_of(e) for e in people]))
                students += [e for e in people if e not in students]
                if combo.professor and combo.professor not in supervisors:
                    supervisors.append(combo.professor)
            else:
                text = st["typed"].get(d, {}).get(k)
                sets.append((k, n.set_range(k), text or "open", []))
        return dict(night=n, sets=sets, students=students, supervisors=supervisors,
                    supervised=bool(st["supervised"] and d in st["supervised"]))

    def copy(self, d, what):
        info = self.night_info(d)
        def count(n, word):
            return f"{n} {word} email{'' if n == 1 else 's'}"
        if what == "students":
            text, msg = "; ".join(info["students"]), count(len(info["students"]), "student")
        elif what == "supervisors":
            text, msg = "; ".join(info["supervisors"]), count(len(info["supervisors"]), "supervisor")
        else:
            n = info["night"]
            lines = [f"{make_label(d)}, {n.venue}" + (" (a professor attends)" if info["supervised"] else "")]
            for k, when, who, names in info["sets"]:
                lines.append(f"  {when or f'Set {k}'}  {who}" + (f": {', '.join(names)}" if names else ""))
            lines += ["", "Students: " + "; ".join(info["students"])]
            if info["supervisors"]:
                lines.append("Supervisors: " + "; ".join(info["supervisors"]))
            text, msg = "\n".join(lines), "the night summary"
        from clipboard import copy_text
        if not copy_text(self.frame, text):
            self.show_text(f"{msg} for {make_label(d)}", text)
        unsaved = any((d, k) in self.swaps.changed_cells() for k, _, _, _ in info["sets"])
        self.status.configure(text=f"Copied {msg} for {make_label(d)}: paste with Ctrl+V."
                                   + (" (Includes unsaved changes.)" if unsaved else ""))
        self.last_copied = text                       # (kept for tests)

    def show_text(self, title, text):
        """Fallback when the system clipboard can't keep the text: show it, selected, to copy by hand."""
        win = tk.Toplevel(self.frame)
        win.title("Copied: " + title)
        win.transient(self.frame.winfo_toplevel())
        box = ttk.Frame(win, padding=14)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Copied. If pasting doesn't work, select the text below (it's already selected) and press "
                            "Ctrl+C (Cmd+C on a Mac).", wraplength=520, justify="left").pack(anchor="w")
        p = self.get_palette() or {}
        txt = tk.Text(box, wrap="word", height=min(18, max(4, text.count("\n") + 2)), width=80, relief="flat",
                      background=p.get("panel", "white"), foreground=p.get("text", "black"), padx=8, pady=6)
        txt.insert("1.0", text)
        txt.tag_add("sel", "1.0", "end")
        txt.pack(fill="both", expand=True, pady=10)
        txt.focus_set()
        ttk.Button(box, text="Close", style="Accent.TButton", command=win.destroy).pack(anchor="e")

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
            menu.add_command(label="No combo can take this set (conflicts or rules)", state="disabled")
        for o in options[:25]:
            cid = o.changes[(d, k)]
            label = self.swaps.labels.get(cid, cid) + (f"   ⚠ {o.warnings[0]}" if o.warnings else "")
            menu.add_command(label=label, command=lambda o=o: self.swaps.add_pending(o))
        self.claim_menu = menu                         # (kept for tests)
        x, y, w, h = self.tree.bbox(item, "who") or (0, 0, 0, 0)
        popup(menu, self.tree.winfo_rootx() + x, self.tree.winfo_rooty() + y + h)

    def export_pdf(self):
        if self.swaps.pending:
            answer = messagebox.askyesnocancel(
                "Unsaved changes", f"There are {len(self.swaps.pending)} unsaved change(s).\n\n"
                "Yes: save them into Schedule.xlsx first, then export.\nNo: export the saved schedule only (your "
                "changes stay pending).\nCancel: do nothing.")
            if answer is None:
                return
            if answer:
                self.swaps.save_all(then=lambda code: self.open_pdf())   # saving also exports the PDF
                return
        self.status.configure(text="Exporting Schedule.pdf...")

        def done(code):
            self.status.configure(text="Schedule.pdf exported; all hard rules hold." if code == 0 else
                                  "Schedule.pdf exported, but the rule check found problems: see the Run tab.")
            self.open_pdf()
        self.export(done)
