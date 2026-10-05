"""The Swaps tab of scheduler_app.py: pick a combo and one of its shows, see every legal swap (core/swaps.py), and
collect changes in a pending list. Nothing is written until "Confirm changes": then Schedule.xlsx is written once (a copy
of the old file goes to 'Schedule backups') and Schedule.pdf is rebuilt in the background. While changes are
pending, the tab shows the schedule as if they were done, so the next swap is checked against them too.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from app_config import input_files
from core import generate_nights
from core.model import make_label
from core.swaps import apply_option, swap_options
from inputs import InputError, load_input, name_from_email
from store import Store
from outputs.excel_schedule import ScheduleFileError, read_schedule, write_swap
from settings_file import SETTINGS_FILE, SettingsError, load_settings


class SwapPanel:
    def __init__(self, parent, get_folder, after_apply, get_palette=lambda: {}):
        self.get_folder, self.after_apply, self.get_palette = get_folder, after_apply, get_palette
        self.state, self.options, self.shows, self.visible = None, [], [], []
        self.labels, self.by_name = {}, {}
        self.pending, self.base_sets = [], None       # changes not saved yet; the schedule as it is on disk
        self.listeners = []                           # called whenever the (pending) schedule changes
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        ttk.Button(top, text="Reload", command=self.load).pack(side="left")
        self.info = ttk.Label(top, text="Reads Schedule.xlsx as it is now (with any edits), plus the approvals and "
                                        "Conflicts.", style="Hint.TLabel")
        self.info.pack(side="left", padx=12)

        body = ttk.Frame(self.frame)
        body.pack(fill="both", expand=True, pady=(12, 0))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Combo", style="CardTitle.TLabel").pack(anchor="w")
        self.combo = ttk.Combobox(left, state="readonly", width=30)
        self.combo.pack(anchor="w", pady=(4, 10))
        self.combo.bind("<<ComboboxSelected>>", lambda _: (self.show_combo(), self.list_options()))
        ttk.Label(left, text="Its shows (pick one; not needed to claim)", style="CardTitle.TLabel").pack(anchor="w")
        self.show_list = ttk.Treeview(left, columns=("when", "where"), show="headings", height=8, selectmode="browse")
        self.show_list.heading("when", text="Night")
        self.show_list.heading("where", text="Venue, set")
        self.show_list.column("when", width=100)
        self.show_list.column("where", width=160)
        self.show_list.pack(anchor="w", pady=(4, 0), fill="y", expand=True)
        self.show_list.bind("<<TreeviewSelect>>", lambda _: self.find())

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        mode = ttk.Frame(right)
        mode.pack(fill="x")
        self.mode = tk.StringVar(value="swap")
        for value, text in (("swap", "Can't make it"), ("give", "Give it away"), ("claim", "Claim an open set")):
            ttk.Radiobutton(mode, text=text, value=value, variable=self.mode,
                            command=self.list_options).pack(side="left", padx=(0, 16))
        ttk.Label(right, text="Legal options, best first", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        table = ttk.Frame(right)
        table.pack(fill="both", expand=True, pady=(4, 0))
        bar = ttk.Scrollbar(table, orient="vertical")
        bar.pack(side="right", fill="y")
        self.option_list = ttk.Treeview(table, columns=("with", "place", "effects"), show="headings",
                                        selectmode="browse", yscrollcommand=bar.set)
        bar.configure(command=self.option_list.yview)
        for col, text, width in (("with", "Swap with", 200), ("place", "Plays instead", 280),
                                 ("effects", "Side effects", 300)):
            self.option_list.heading(col, text=text, anchor="w")
            self.option_list.column(col, width=width, anchor="w", stretch=col != "with")
        self.option_list.pack(side="left", fill="both", expand=True)
        self.option_list.bind("<<TreeviewSelect>>", lambda _: self.describe())
        self.details = ttk.Label(right, text="", justify="left", anchor="w", wraplength=560)
        self.details.pack(fill="x", pady=(8, 0))
        right.bind("<Configure>", lambda e: self.details.configure(wraplength=max(e.width - 10, 200)))
        self.apply_button = ttk.Button(right, text="Add to pending changes", style="Accent.TButton",
                                       command=self.apply, state="disabled")
        self.apply_button.pack(anchor="w", pady=(8, 0))

        # pending changes: collected here, written all at once
        box = ttk.Frame(right, style="Card.TFrame", padding=(12, 10))
        box.pack(fill="x", pady=(14, 0))
        self.pending_title = ttk.Label(box, text="Pending changes (none)", style="CardTitle.TLabel")
        self.pending_title.pack(anchor="w")
        self.pending_list = ttk.Treeview(box, columns=("change",), show="", height=4, selectmode="none")
        self.pending_list.column("change", anchor="w")
        self.pending_list.pack(fill="x", pady=(6, 6))
        bar = ttk.Frame(box)
        bar.pack(fill="x")
        self.save_button = ttk.Button(bar, text="Confirm changes", style="Accent.TButton", command=self.save_all,
                                      state="disabled")
        self.save_button.pack(side="left")
        self.undo_button = ttk.Button(bar, text="Undo last", command=self.undo_last, state="disabled")
        self.undo_button.pack(side="left", padx=6)
        self.discard_button = ttk.Button(bar, text="Discard all", command=self.discard_all, state="disabled")
        self.discard_button.pack(side="left")
        self.save_status = ttk.Label(box, text="", style="Hint.TLabel", justify="left")
        self.save_status.pack(anchor="w", pady=(6, 0))
        self.recolor()

    def recolor(self):
        p = self.get_palette()
        if p:
            self.option_list.tag_configure("warn", foreground=p["warn"])
            self.option_list.tag_configure("fix", foreground=p["good"])

    # loading
    def load(self, quiet=False):
        """quiet: when loading by itself (app start, folder change), a problem is shown in the tab, not a pop-up.
        Pending changes are never thrown away by a quiet reload (it refreshes the combos' members and names and
        keeps the pending schedule); a Reload click asks first."""
        keep = bool(self.pending) and quiet and self.state is not None
        if self.pending and not keep:
            if not messagebox.askyesno("Discard pending changes?", f"{len(self.pending)} change(s) haven't "
                                       "been saved. Reload anyway and lose them?", icon="warning"):
                return
        if not keep:
            self.pending = []
            self.refresh_pending()
        folder = self.get_folder()
        try:
            settings, _ = load_settings(folder / SETTINGS_FILE)
            files = input_files(folder)
            inp = load_input(folder, settings, files["approvals"], files["conflicts"])
            combos = {c.id: c for c in inp.combos}
            if keep:                          # members changed (Combos tab) while swaps are pending: keep the schedule
                if any(c and c not in combos for row in self.state["sets"].values() for c in row.values()):
                    return                    # a combo is gone: wait until the pending changes are confirmed
                sets, supervised, typed = self.state["sets"], self.state["supervised"], self.state["typed"]
                problems = []
            else:
                if quiet and not (folder / "Schedule.xlsx").exists():
                    raise ScheduleFileError("No Schedule.xlsx yet: make the schedule first (Run tab, step 2).")
                sets, problems, supervised, typed = read_schedule(folder / "Schedule.xlsx", combos)
        except (SettingsError, InputError, ScheduleFileError) as e:
            if keep:
                return
            if not quiet:
                messagebox.showerror("Can't load the schedule", str(e))
            self.state = None
            self.combo.configure(values=[])
            self.combo.set("")
            self.clear(self.show_list, self.option_list)
            self.info.configure(text="Not loaded: " + str(e).strip().splitlines()[0])
            self.notify()
            return
        names = Store(folder).names
        plain = {e: names.get(e) or name_from_email(e) for c in combos.values() for e in c.members}
        clash = {n for n in plain.values() if list(plain.values()).count(n) > 1}

        def name_of(e):                       # adds the email when two people would look the same
            n = names.get(e) or name_from_email(e)
            return f"{n} ({e})" if n in clash else n
        if not keep:
            self.base_sets = {d: dict(row) for d, row in sets.items()}
        self.state = dict(settings=settings, inp=inp, combos=combos, sets=sets, supervised=supervised, typed=typed,
                          nights=generate_nights(settings), name_of=name_of)
        # "Combo 07 (Ana Ruiz)": the liaison, so the director recognises the combo
        def who(e):                           # the liaison's name, or their email if the name isn't unique
            n = plain.get(e) or name_from_email(e)
            return e if n in clash else n
        self.labels = {cid: f"{c.name} ({who(c.liaison)})" if c.liaison else c.name for cid, c in combos.items()}
        self.by_name = {c.name: cid for cid, c in combos.items()}
        self.combo.configure(values=[self.labels[cid] for cid in sorted(combos, key=lambda c: combos[c].name)])
        self.info.configure(text=f"Loaded {len(combos)} combos." + (
            f" Schedule.xlsx has {len(problems)} problem(s) already; swaps that fix one are marked." if problems else ""))
        if self.combo.get() in self.combo.cget("values"):
            self.show_combo()
        else:
            self.combo.set("")
            self.clear(self.show_list, self.option_list)
        self.notify()

    def clear(self, *trees):
        for t in trees:
            t.delete(*t.get_children())
        self.details.configure(text="")
        self.apply_button.configure(state="disabled")

    def cid(self):
        return next((c for c, label in self.labels.items() if label == self.combo.get()), None)

    def short(self):
        """The chosen combo's name without the liaison, for headings."""
        cid = self.cid()
        return self.state["combos"][cid].name if cid else ""

    def show_combo(self):
        st, cid = self.state, self.cid()
        self.clear(self.show_list, self.option_list)
        nmap = {n.date: n for n in st["nights"]}
        self.shows = sorted((d, k) for d, row in st["sets"].items() for k, c in row.items() if c == cid)
        for i, (d, k) in enumerate(self.shows):
            n = nmap.get(d)
            sup = " · prof" if st["supervised"] and d in st["supervised"] else ""
            self.show_list.insert("", "end", iid=str(i), values=(make_label(d), f"{n.venue if n else '?'}, set {k}{sup}"))

    def find(self):
        sel = self.show_list.selection()
        if not sel:
            return
        d, k = self.shows[int(sel[0])]
        st = self.state
        self.frame.configure(cursor="watch")
        self.frame.update_idletasks()
        try:
            self.options = swap_options(st["sets"], st["nights"], st["combos"], st["inp"], st["settings"],
                                        st["supervised"], st["typed"], self.cid(), d, k, st["name_of"])
        finally:
            self.frame.configure(cursor="")
        self.list_options()

    def list_options(self):
        if not self.state:
            return
        self.clear(self.option_list)
        mode = self.mode.get()
        give, claim = mode == "give", mode == "claim"
        if claim:
            if not self.cid():
                return
            st = self.state
            options = swap_options(st["sets"], st["nights"], st["combos"], st["inp"], st["settings"],
                                   st["supervised"], st["typed"], self.cid(), name_of=st["name_of"])
        elif not self.show_list.selection():
            return
        else:
            options = [o for o in self.options if (o.kind in ("give", "drop")) == give]
        self.visible = options
        self.option_list.heading("with", text="Give to" if give else "Take" if claim else "Swap with")
        self.option_list.heading("place", text="The show" if give else f"{self.short()} plays instead"
                                 if not claim else f"{self.short()} also plays")
        for i, o in enumerate(options):
            tag = "fix" if any(n.startswith("Fixes:") for n in o.notes) else "warn" if o.warnings else ""
            effects = "⚠ " + o.warnings[0] if o.warnings else o.notes[0] if o.notes else "none"
            more = len(o.warnings) + len(o.notes) - 1
            if more > 0:
                effects += f"  (+{more} more)"
            partner = self.labels.get(self.by_name.get(o.partner), o.partner) + (" (reorder)" if o.same_night else "")
            self.option_list.insert("", "end", iid=str(i), values=(partner, o.place, effects), tags=(tag,))
        if not self.option_list.get_children():
            self.details.configure(text=(
                f"No open set {self.short()} can take: every one is on a night a member can't make, the night "
                "it already plays, or would break another rule." if claim else
                f"{self.short()} can't give this show away: it needs it (its minimum shows, a venue minimum or "
                "its supervised night), or no combo can take it." if give else
                "No legal swap for this show: every other place would break a rule (a member's conflict, "
                "supervision, venue minimum, ...)."))

    def describe(self):
        sel = self.option_list.selection()
        if not sel:
            return
        o = self.visible[int(sel[0])]
        lines = [o.title] + [f"⚠ {w}" for w in o.warnings] + [f"• {n}" for n in o.notes]
        self.details.configure(text="\n".join(lines) if len(lines) > 1 else
                               o.title + "\nNo side effects: every rule and preference still holds.")
        self.apply_button.configure(state="normal")

    def apply(self):
        """Adds the selected option to the pending changes (nothing is written yet)."""
        sel = self.option_list.selection()
        if not sel:
            return
        o, st = self.visible[int(sel[0])], self.state
        self.pending.append(o)
        st["sets"] = apply_option(st["sets"], o)
        self.after_change(f"Added: {o.title}")

    def notify(self):
        for f in self.listeners:
            f()

    def add_pending(self, option, message=None):
        """Adds an option found elsewhere (e.g. the Schedule tab) to the pending changes."""
        self.pending.append(option)
        self.state["sets"] = apply_option(self.state["sets"], option)
        self.after_change(message or f"Added: {option.title}")

    def changed_cells(self):
        """(night, set) of every set that differs from Schedule.xlsx because of pending changes."""
        if not self.state or self.base_sets is None:
            return set()
        sets = self.state["sets"]
        return {(d, k) for d in set(sets) | set(self.base_sets) for k in set(sets.get(d, {})) | set(self.base_sets.get(d, {}))
                if sets.get(d, {}).get(k) != self.base_sets.get(d, {}).get(k)}

    def preselect(self, cid, d, k, mode="swap"):
        """Shows the options for combo cid's show on night d, set k (used by the Schedule tab)."""
        self.mode.set(mode)
        self.combo.set(self.labels.get(cid, ""))
        self.show_combo()
        if (d, k) in self.shows:
            i = str(self.shows.index((d, k)))
            self.show_list.selection_set(i)
            self.show_list.see(i)
            self.find()

    def after_change(self, message):
        self.refresh_pending()
        self.notify()
        keep = self.combo.get()
        if keep:
            self.show_combo()                         # its shows may have moved
        self.clear(self.option_list)
        self.save_status.configure(text="")
        self.details.configure(text=message + "\nPick a show (or another combo) to keep going, then Confirm changes.")

    def refresh_pending(self):
        self.pending_list.delete(*self.pending_list.get_children())
        for i, o in enumerate(self.pending, start=1):
            self.pending_list.insert("", "end", values=(f"{i}. " + ("\u26a0 " if o.warnings else "") + o.title,))
        n = len(self.pending)
        self.pending_title.configure(text=f"Pending changes ({n})" if n else "Pending changes (none)")
        self.pending_list.configure(height=min(max(n, 2), 6))
        for b in (self.save_button, self.undo_button, self.discard_button):
            b.configure(state="normal" if n else "disabled")

    def rebuild_sets(self):
        sets = {d: dict(row) for d, row in self.base_sets.items()}
        for o in self.pending:
            sets = apply_option(sets, o)
        self.state["sets"] = sets

    def undo_last(self):
        if self.pending:
            o = self.pending.pop()
            self.rebuild_sets()
            self.after_change(f"Undone: {o.title}")

    def discard_all(self):
        if self.pending and messagebox.askyesno("Discard all?", f"Throw away all {len(self.pending)} pending "
                                                "change(s)? Schedule.xlsx hasn't been changed."):
            self.pending = []
            self.rebuild_sets()
            self.after_change("All pending changes discarded.")

    def save_all(self):
        """Writes every pending change into Schedule.xlsx at once, then rebuilds the PDF in the background.
        (The "Confirm changes" button of both the Swaps and the Schedule tab.)"""
        st = self.state
        if not self.pending:
            return
        changes = {(d, k): c for d, row in st["sets"].items() for k, c in row.items()
                   if self.base_sets.get(d, {}).get(k) != c}
        if not changes:
            messagebox.showinfo("Nothing to save", "The pending changes cancel each other out.")
            self.pending = []
            self.after_change("Nothing to save.")
            return
        warns = sum(1 for o in self.pending if o.warnings)
        if not messagebox.askyesno("Confirm changes?", f"Save {len(self.pending)} change(s) into Schedule.xlsx "
                                   f"({len(changes)} set(s) change)?" + (f"\n\n{warns} of them have a heads-up (\u26a0)."
                                                                       if warns else "")
                                   + "\n\nA copy of the current file goes to 'Schedule backups' first."):
            return
        open_label = "OPEN - volunteer" if st["settings"].extra_slot_policy == "open" else "(empty)"
        try:
            backup = write_swap(self.get_folder() / "Schedule.xlsx", changes, st["combos"], open_label)
        except ScheduleFileError as e:
            messagebox.showerror("Couldn't save", str(e))
            return
        n = len(self.pending)
        self.pending = []
        self.load(quiet=True)
        self.save_status.configure(text=f"Saved {n} change(s) to Schedule.xlsx (backup in 'Schedule backups'). "
                                        "Rebuilding Schedule.pdf...")
        self.after_apply(f"Saved {n} change(s). Backup of the old file: {backup}\n", self.pdf_done)

    def pdf_done(self, code):
        self.save_status.configure(text="Saved. Schedule.pdf rebuilt; all hard rules hold." if code == 0 else
                                   "Saved and Schedule.pdf rebuilt, but the rule check found problems: see the Run tab.")
