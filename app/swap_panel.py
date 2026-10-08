"""The Swaps tab of scheduler_app.py: pick a combo and one of its shows, see every legal swap (core/swaps.py), and
collect changes in a pending list. Nothing is written until "Confirm changes": then the schedule (schedule_file.py) is
saved once (a copy of the old one goes to 'AppFiles/ScheduleBackups') and Schedule.pdf / .xlsx are rebuilt in the
background. While changes are
pending, the tab shows the schedule as if they were done, so the next swap is checked against them too.
For a picked option (buttons, or right-click on it): copy the liaisons' emails of the combos it touches, or a summary
of it in words (core.swaps.swap_summary) to send them.
"""
import tkinter as tk
from tkinter import ttk

import app_log
from app_config import input_files
import dialogs
from core.model import make_label
from data_folder import settings_path
from core.swaps import apply_option, involved, swap_options, swap_summary
from inputs import InputError, load_input, name_from_email
from store import Store
from schedule_file import ScheduleFileError, load as load_schedule, save_changes
from settings_file import SettingsError, load_settings
from theme import in_background, popup


class TextChange:
    """An unsaved change of the text in a set (Schedule tab: Add text / Edit text / Clear text); it sits in the
    pending list next to the swaps and is confirmed with them. text "" = cleared (the set is open again)."""
    breaks = warnings = ()

    def __init__(self, d, k, text):
        self.d, self.k, self.text = d, k, text.strip()
        self.title = (f"Text in {make_label(d)} set {k}: '{self.text}'" if self.text else
                      f"Text in {make_label(d)} set {k} cleared")


class SwapPanel:
    def __init__(self, parent, get_folder, after_apply, get_palette=lambda: {}):
        self.get_folder, self.after_apply, self.get_palette = get_folder, after_apply, get_palette
        self.state, self.options, self.shows, self.visible = None, [], [], []
        self.labels, self.by_name = {}, {}
        self.pending, self.base_sets = [], None       # changes not saved yet; the schedule as it is on disk
        self.base_typed = {}                          # ...and the text in its sets, on disk
        self.search_id = 0                            # the latest option search (an older one's results are dropped)
        self.listeners = []                           # called whenever the (pending) schedule changes
        self.is_busy = lambda: False                  # set by the app: a step is running in the background
        self.on_pending = lambda: None                # set by the app: unsaved changes came or went (tab dots)
        self.frame = ttk.Frame(parent, padding=(4, 12, 4, 4))

        # a line only when there's something to say (it couldn't load; the schedule has problems already)
        self.info = ttk.Label(self.frame, text="", style="Hint.TLabel")

        body = self.body = ttk.Frame(self.frame)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Combo", style="CardTitle.TLabel").pack(anchor="w")
        self.combo = ttk.Combobox(left, state="readonly", width=30)
        self.combo.pack(anchor="w", pady=(4, 10))
        self.combo.bind("<<ComboboxSelected>>", lambda _: (self.show_combo(), self.list_options()))
        ttk.Label(left, text="Shows", style="CardTitle.TLabel").pack(anchor="w")
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
        for value, text in (("swap", "Swap"), ("give", "Give away"), ("claim", "Claim")):
            ttk.Radiobutton(mode, text=text, value=value, variable=self.mode,
                            command=self.list_options).pack(side="left", padx=(0, 16))
        ttk.Label(right, text="Options", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
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
        for ev in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):        # right-click (Mac: also Ctrl-click)
            self.option_list.bind(ev, self.option_menu)
        self.details = ttk.Label(right, text="", justify="left", anchor="w", wraplength=560)
        self.details.pack(fill="x", pady=(8, 0))
        right.bind("<Configure>", lambda e: self.details.configure(wraplength=max(e.width - 10, 200)))
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(8, 0))
        self.apply_button = ttk.Button(buttons, text="Add this change", style="Accent.TButton",
                                       command=self.apply, state="disabled")
        self.apply_button.pack(side="left")
        self.copy_buttons = [ttk.Button(buttons, text="Copy liaison emails", state="disabled",
                                        command=lambda: self.copy_option("liaisons")),
                             ttk.Button(buttons, text="Copy change email", state="disabled",
                                        command=lambda: self.copy_option("summary"))]
        for b in self.copy_buttons:
            b.pack(side="left", padx=(6, 0))
        self.copy_status = ttk.Label(buttons, text="", style="Hint.TLabel")
        self.copy_status.pack(side="left", padx=(12, 0))

        # pending changes: collected here, written all at once
        box = ttk.Frame(right, style="Card.TFrame", padding=(12, 10))
        box.pack(fill="x", pady=(14, 0))
        self.pending_title = ttk.Label(box, text="No unsaved changes", style="CardTitle.TLabel")
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
            self.option_list.tag_configure("breaks", foreground=p["bad"])

    # loading
    def load(self, quiet=False):
        """quiet: when loading by itself (app start, folder change), a problem is shown in the tab, not a pop-up.
        Pending changes are never thrown away by a quiet reload (it refreshes the combos' members and names and
        keeps the pending schedule); a Reload click asks first."""
        keep = bool(self.pending) and quiet and self.state is not None
        if self.pending and not keep:
            if not dialogs.askyesno("Discard unsaved changes?", "Some changes haven't been saved. "
                                       "Reloading loses them.", yes="Reload anyway", no="Cancel",
                                       default="no", icon="warning"):
                return
        if not keep:
            self.pending = []
            self.refresh_pending()
        folder = self.get_folder()
        try:
            settings, _ = load_settings(settings_path(folder))
            files = input_files(folder)
            inp = load_input(folder, settings, files["approvals"], files["conflicts"])
            combos = {c.id: c for c in inp.combos}
            if keep:                          # members changed (Combos tab) while swaps are pending: keep the schedule
                if any(c and c not in combos for row in self.state["sets"].values() for c in row.values()):
                    return                    # a combo is gone: wait until the pending changes are confirmed
                sets, supervised, typed = self.state["sets"], self.state["supervised"], self.state["typed"]
                problems = []
            else:
                sched = load_schedule(folder, combos, settings)
                sets, problems, supervised, typed = sched.sets, sched.problems, sched.supervised, sched.typed
        except (SettingsError, InputError, ScheduleFileError) as e:
            if keep:
                return
            if not quiet:
                dialogs.showerror("Can't load the schedule", str(e))
            self.state = None
            self.combo.configure(values=[])
            self.combo.set("")
            self.clear(self.show_list, self.option_list)
            self.say("Not loaded: " + str(e).strip().splitlines()[0])
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
            self.base_typed = {d: dict(row) for d, row in typed.items()}
        self.state = dict(settings=settings, inp=inp, combos=combos, sets=sets, supervised=supervised, typed=typed,
                          nights=sched.nights if not keep else self.state["nights"], name_of=name_of,
                          published=sched.published if not keep else self.state.get("published", False))
        # "Combo 07 (Ana Ruiz)": the liaison, so the director recognises the combo
        def who(e):                           # the liaison's name, or their email if the name isn't unique
            n = plain.get(e) or name_from_email(e)
            return e if n in clash else n
        self.labels = {cid: f"{c.name} ({who(c.liaison)})" if c.liaison else c.name for cid, c in combos.items()}
        self.by_name = {c.name: cid for cid, c in combos.items()}
        self.combo.configure(values=[self.labels[cid] for cid in sorted(combos, key=lambda c: combos[c].name)])
        self.say(f"The schedule has {len(problems)} problem(s) already; swaps that fix one are marked in green."
                 if problems else "")
        if self.combo.get() in self.combo.cget("values"):
            self.show_combo()
        else:
            self.combo.set("")
            self.clear(self.show_list, self.option_list)
        self.notify()

    def say(self, text):
        """The line above the lists: shown only with something in it."""
        self.info.configure(text=text)
        if text:
            self.info.pack(fill="x", pady=(0, 10), before=self.body)
        else:
            self.info.pack_forget()

    def clear(self, *trees):
        for t in trees:
            t.delete(*t.get_children())
        self.details.configure(text="")
        for b in [self.apply_button] + self.copy_buttons:
            b.configure(state="disabled")
        self.copy_status.configure(text="")

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
            sup = " · FB" if st["supervised"] and d in st["supervised"] else ""
            self.show_list.insert("", "end", iid=str(i), values=(make_label(d), f"{n.venue if n else '?'}, set {k}{sup}"))

    def find(self):
        sel = self.show_list.selection()
        if not sel:
            return
        d, k = self.shows[int(sel[0])]
        st, cid = self.state, self.cid()
        self.options = []
        self.clear(self.option_list)
        self.details.configure(text="Finding options...")
        self.search_id += 1
        search = self.search_id

        def done(options):
            if search == self.search_id:              # not overtaken by another pick meanwhile
                self.options = options
                self.list_options()
        in_background(self.frame, lambda: swap_options(st["sets"], st["nights"], st["combos"], st["inp"],
                                                       st["settings"], st["supervised"], st["typed"], cid, d, k,
                                                       st["name_of"]), done)

    def list_options(self):
        if not self.state:
            return
        self.clear(self.option_list)
        mode = self.mode.get()
        give, claim = mode == "give", mode == "claim"
        if claim:
            if not self.cid():
                return
            st, cid = self.state, self.cid()
            self.details.configure(text="Finding open sets...")
            self.search_id += 1
            search = self.search_id

            def done(options):
                if search == self.search_id and self.mode.get() == "claim":
                    self.show_options(options)
            in_background(self.frame, lambda: swap_options(st["sets"], st["nights"], st["combos"], st["inp"],
                                                           st["settings"], st["supervised"], st["typed"], cid,
                                                           name_of=st["name_of"]), done)
            return
        if not self.show_list.selection():
            return
        shown = [o for o in self.options if (o.kind in ("give", "drop")) == give]
        if give:                                      # "nobody (leave open)" always first, whatever its colour
            shown = [o for o in shown if o.kind == "drop"] + [o for o in shown if o.kind != "drop"]
        self.show_options(shown)

    def show_options(self, options):
        """Fills the options table (best first) for the current mode."""
        self.clear(self.option_list)
        mode = self.mode.get()
        give, claim = mode == "give", mode == "claim"
        self.visible = options
        self.option_list.heading("with", text="Give to" if give else "Take" if claim else "Swap with")
        self.option_list.heading("place", text="The show" if give else f"{self.short()} plays instead"
                                 if not claim else f"{self.short()} also plays")
        for i, o in enumerate(options):
            tag = ("breaks" if o.breaks else "fix" if any(n.startswith("Fixes:") for n in o.notes) else
                   "warn" if o.warnings else "")
            effects = ("✖ Breaks a rule: " + o.breaks[0] if o.breaks else "⚠ " + o.warnings[0] if o.warnings
                       else o.notes[0] if o.notes else "none")
            more = len(o.breaks) + len(o.warnings) + len(o.notes) - 1
            if more > 0:
                effects += f"  (+{more} more)"
            partner = self.labels.get(self.by_name.get(o.partner), o.partner) + (" (reorder)" if o.same_night else "")
            self.option_list.insert("", "end", iid=str(i), values=(partner, o.place, effects), tags=(tag,))
        if not self.option_list.get_children():
            self.details.configure(text="Nothing to list here." if claim else "Nothing to list for this show.")
        elif all(o.breaks for o in options):          # (in Give away, "leave open" comes first whatever it breaks)
            self.details.configure(text=(
                f"No open set {self.short()} can take without breaking a rule." if claim else
                f"{self.short()} can't give this show away without breaking a rule (it needs it for its minimum "
                "shows, a venue minimum or its feedback night)." if give else
                "No swap for this show keeps every rule.")
                + " The options in red break one (it's named): pick one only when it's agreed, e.g. the student "
                  "can make it after all. The app asks first, and the rule check keeps flagging it.")

    def describe(self):
        sel = self.option_list.selection()
        if not sel:
            return
        o = self.visible[int(sel[0])]
        lines = ([o.title] + [f"✖ Breaks a rule: {b}" for b in o.breaks] + [f"⚠ {w}" for w in o.warnings]
                 + [f"• {n}" for n in o.notes])
        self.details.configure(text="\n".join(lines) if len(lines) > 1 else
                               o.title + "\nNo side effects: every rule and preference still holds.")
        for b in [self.apply_button] + self.copy_buttons:
            b.configure(state="normal")
        self.copy_status.configure(text="")

    def picked_option(self):
        sel = self.option_list.selection()
        return self.visible[int(sel[0])] if sel and self.state else None

    def option_menu(self, event):
        """Right-click on an option: the same as the buttons under the list."""
        item = self.option_list.identify_row(event.y)
        if not item:
            return
        self.option_list.selection_set(item)
        p = self.get_palette() or {}
        menu = tk.Menu(self.option_list, tearoff=0, background=p.get("panel"), foreground=p.get("text"),
                       activebackground=p.get("accent"), activeforeground=p.get("accent_text"))
        menu.add_command(label="Add this change", command=self.apply)
        menu.add_separator()
        menu.add_command(label="Copy liaison emails", command=lambda: self.copy_option("liaisons"))
        menu.add_command(label="Copy change email", command=lambda: self.copy_option("summary"))
        self.menu = menu                              # (kept for tests)
        popup(menu, event.x_root, event.y_root)

    def liaison_emails(self, ids):
        """(emails, names of combos without a liaison) for these combos: each one's liaison, or all its members."""
        emails, no_liaison = [], []
        for c in ids:
            combo = self.state["combos"][c]
            if not combo.liaison:
                no_liaison.append(combo.name)
            for e in [combo.liaison] if combo.liaison else sorted(combo.members):
                if e not in emails:
                    emails.append(e)
        return emails, no_liaison

    def change_email(self, options, sets, first=None):
        """(combo ids involved, the change email) for these options, done one after the other starting from sets.
        The text: Semester tab > Email Templates."""
        from settings_file import fill_email
        st, ids, parts = self.state, [], []
        for o in options:
            for c in involved(sets, o, st["combos"], first):
                if c not in ids:
                    ids.append(c)
            parts.append(swap_summary(sets, st["nights"], st["combos"], o, first, st["name_of"], st["inp"].blocked))
            sets = apply_option(sets, o)
        names = [st["combos"][c].name for c in ids]
        combos = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""
        return ids, fill_email(st["settings"].change_email, {
            "change": "\n\n".join(parts), "combos": combos, "semester": st["settings"].semester_name})

    def copy_option(self, what):
        """Copies the picked option's liaison emails (every combo it touches; a combo without a liaison: all its
        members) or its change email."""
        o, st = self.picked_option(), self.state
        if not o:
            return
        if what == "liaisons":
            emails, no_liaison = self.liaison_emails(involved(st["sets"], o, st["combos"], self.cid()))
            text = "; ".join(emails)
            msg = (f"Copied {len(emails)} liaison email{'' if len(emails) == 1 else 's'}"
                   + (f" (no liaison for {', '.join(no_liaison)}: all its members instead)" if no_liaison else ""))
        else:
            text, msg = self.change_email([o], st["sets"], self.cid())[1], "Copied the change email"
        from clipboard import copy
        copy(self.frame, text, msg[len("Copied "):], self.get_palette())
        self.copy_status.configure(text=msg + ": paste with Ctrl+V.")
        self.last_copied = text                       # (kept for tests)

    def apply(self):
        """Adds the selected option to the pending changes (nothing is written yet)."""
        sel = self.option_list.selection()
        if not sel:
            return
        o, st = self.visible[int(sel[0])], self.state
        if not self.override_ok(o):
            return
        self.pending.append(o)
        st["sets"] = apply_option(st["sets"], o)
        self.after_change(f"Added: {o.title}")

    def override_ok(self, option):
        """An option that breaks a hard rule: says which, and asks. True = go ahead (or it breaks none)."""
        if not option.breaks:
            return True
        return dialogs.askyesno(
            "Break a rule?", f"{option.title}\n\nThis breaks " + ("a hard rule" if len(option.breaks) == 1 else
                                                                  f"{len(option.breaks)} hard rules") + ":\n"
            + "\n".join(f"\u2716 {b}" for b in option.breaks)
            + "\n\nOnly do this when it's agreed (e.g. the student can make it after all). Check schedule keeps "
            "flagging it.", yes="Add it anyway", no="Cancel", icon="warning", default="no")

    def notify(self):
        for f in self.listeners:
            f()

    def add_pending(self, option, message=None):
        """Adds an option found elsewhere (e.g. the Schedule tab) to the pending changes."""
        if not self.override_ok(option):
            return
        self.pending.append(option)
        self.state["sets"] = apply_option(self.state["sets"], option)
        self.after_change(message or f"Added: {option.title}")

    def add_text(self, d, k, text):
        """Text typed into a set (or cleared), as an unsaved change."""
        change = TextChange(d, k, text)
        self.pending.append(change)
        self.rebuild_sets()
        self.after_change(f"Added: {change.title}")

    def typed_changes(self):
        """{(night, set): text ('' = cleared)} where the text differs from the saved schedule."""
        typed, base = self.state["typed"], self.base_typed
        return {(d, k): typed.get(d, {}).get(k, "") for d in set(typed) | set(base)
                for k in set(typed.get(d, {})) | set(base.get(d, {}))
                if typed.get(d, {}).get(k, "") != base.get(d, {}).get(k, "")}

    def changed_cells(self):
        """(night, set) of every set that differs from the saved schedule because of pending changes (its combo or
        its text)."""
        if not self.state or self.base_sets is None:
            return set()
        sets = self.state["sets"]
        return {(d, k) for d in set(sets) | set(self.base_sets) for k in set(sets.get(d, {})) | set(self.base_sets.get(d, {}))
                if sets.get(d, {}).get(k) != self.base_sets.get(d, {}).get(k)} | set(self.typed_changes())

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
            mark = "\u2716 " if o.breaks else "\u26a0 " if o.warnings else ""
            self.pending_list.insert("", "end", values=(f"{i}. {mark}{o.title}",))
        n = len(self.pending)
        self.pending_title.configure(text="\u25cf Unsaved changes" if n else "No unsaved changes")
        self.pending_list.configure(height=min(max(n, 2), 6))
        for b in (self.save_button, self.undo_button, self.discard_button):
            b.configure(state="normal" if n else "disabled")
        if self.is_busy():                                # a step is running: Confirm waits for it
            self.save_button.configure(state="disabled")
        self.on_pending()

    def rebuild_sets(self):
        sets = {d: dict(row) for d, row in self.base_sets.items()}
        typed = {d: dict(row) for d, row in self.base_typed.items()}
        for o in self.pending:
            if isinstance(o, TextChange):
                if o.text:
                    typed.setdefault(o.d, {})[o.k] = o.text
                else:
                    typed.get(o.d, {}).pop(o.k, None)
            else:
                sets = apply_option(sets, o)
        self.state["sets"] = sets
        self.state["typed"] = {d: row for d, row in typed.items() if row}

    def undo_last(self):
        if self.pending:
            o = self.pending.pop()
            self.rebuild_sets()
            self.after_change(f"Undone: {o.title}")

    def discard_all(self):
        if self.pending and dialogs.askyesno("Discard all?", "Throw away the unsaved changes? The schedule "
                                                "hasn't been changed.", yes="Discard",
                                             no="Keep them", default="no"):
            self.pending = []
            self.rebuild_sets()
            self.after_change("Unsaved changes discarded.")

    def save_all(self, then=None):
        """Saves every pending change into the schedule at once, then rebuilds the PDF and xlsx in the background.
        (The "Confirm changes" button of both the Swaps and the Schedule tab.) then(code): called after the exports."""
        st = self.state
        if not self.pending:
            return
        changes = {(d, k): c for d, row in st["sets"].items() for k, c in row.items()
                   if self.base_sets.get(d, {}).get(k) != c}
        texts = self.typed_changes()
        if not changes and not texts:
            dialogs.showinfo("Nothing to save", "The unsaved changes cancel each other out.")
            self.pending = []
            self.after_change("Nothing to save.")
            return
        warns = sum(1 for o in self.pending if o.warnings)
        breaks = sum(1 for o in self.pending if o.breaks)
        if not dialogs.askyesno("Confirm changes?", "Save the unsaved changes into the schedule?"
                                   + ("\n\nSome of them have a heads-up (\u26a0)." if warns else "")
                                   + ("\n\n\u2716 Some of them break a hard rule (agreed)." if breaks else "")
                                   + "\n\nYou can undo this later: the schedule as it is now is saved as an earlier version (Schedule tab > "
                                     "Earlier versions...).", yes="Save", no="Cancel"):
            return
        if not self.same_as_on_disk():
            return
        try:
            backup = save_changes(self.get_folder(), st["combos"], sets=changes, typed=texts,
                                  what=[("\u2716 rule overridden: " if o.breaks else "") + o.title for o in self.pending])
        except ScheduleFileError as e:
            dialogs.showerror("Couldn't save", str(e))
            return
        n = len(self.pending)
        app_log.write(f"Swaps tab: saved {n} change(s); backup {backup}\n"
                      + "\n".join(("RULE OVERRIDDEN: " if o.breaks else "") + o.title for o in self.pending))
        self.pending = []
        self.load(quiet=True)
        self.save_status.configure(text=f"Saved {n} change(s) (backup in 'AppFiles/ScheduleBackups'). "
                                        "Rebuilding Schedule.pdf and Schedule.xlsx...")
        self.after_apply(f"Saved {n} change(s). Backup of the schedule before: {backup}\n",
                         lambda code: (self.pdf_done(code), then and then(code)))

    def same_as_on_disk(self):
        """True when the schedule still holds what the pending changes were planned against. Otherwise (another
        computer saved it and the sync brought it in) says so, and offers to reload."""
        st = self.state
        try:
            sched = load_schedule(self.get_folder(), st["combos"], st["settings"])
        except ScheduleFileError as e:
            dialogs.showerror("Couldn't save", str(e))
            return False
        if sched.sets == self.base_sets and sched.typed == self.base_typed:
            return True
        if dialogs.askyesno(
                "Schedule changed elsewhere", "The schedule was changed since these changes were planned (on "
                "another computer), so they might not fit any more. Nothing was saved.\n\n"
                "Reload the schedule as it is now? Your unsaved changes are dropped; redo the ones still "
                "needed.", yes="Reload", no="Cancel", icon="warning"):
            self.pending = []
            self.load()
        return False

    def pdf_done(self, code):
        self.save_status.configure(text="Saved. Schedule.pdf and .xlsx rebuilt; all hard rules hold." if code == 0 else
                                   "Saved and the exports rebuilt, but the rule check found problems: see the Run tab.")
