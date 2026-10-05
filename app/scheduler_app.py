"""One-click window for the director: check the inputs, make the schedule, rebuild the PDF after hand edits (Run
tab), and change the settings (Settings tab, saved in settings.json).

    Double-click "Make Schedule.bat" (Windows), "Make Schedule.command" (Mac) or "make-schedule.sh" (Linux),
    or run:  python app/scheduler_app.py

It runs solve.py inside this window, on the data folder shown at the top (by default data/ next to app/;
"Change..." picks another one and is remembered). Needs Python 3 with tkinter (standard on Windows and the
python.org Mac installer) plus openpyxl, ortools and reportlab; the window offers to install those.
"""
import contextlib
import importlib
import io
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from app_config import input_files, is_picked, load_config, pick_input_file, save_config  # noqa: E402
from util import APPROVALS_FILE, CONFLICTS_FILE, DATA_FOLDER  # noqa: E402  (both standard library only, safe before packages are installed)
AUTHOR, EMAIL = "Elliott Kobelansky", "elliottkobelansky@gmail.com"
PACKAGES = {"openpyxl": "openpyxl", "ortools": "ortools", "reportlab": "reportlab"}   # import name -> pip name
OPTIONAL = {"tkcalendar": "tkcalendar", "sv_ttk": "sv-ttk"}   # pop-up calendars; the modern look

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:                                   # e.g. Homebrew Python on a Mac without python-tk
    print("This Python has no tkinter (the window toolkit). Install Python from https://www.python.org/downloads/"
          " (it includes tkinter), or on Linux: sudo apt install python3-tk")
    sys.exit(1)


# ---------------------------------------------------------------- work that doesn't need the window (testable)

def missing_packages(include_optional=False):
    importlib.invalidate_caches()                     # so packages installed a moment ago are seen
    missing = []
    for mod, pip_name in list(PACKAGES.items()) + (list(OPTIONAL.items()) if include_optional else []):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    return missing


def run_solve(args, folder, write):
    """Runs solve.py's main() with these arguments on `folder`; everything it prints goes to write(text).
    Returns its exit code (0 = fine)."""
    import solve                                      # imported here so a missing package shows up in the window

    class Writer(io.TextIOBase):
        def write(self, s):
            write(s)
            return len(s)
    with contextlib.redirect_stdout(Writer()), contextlib.redirect_stderr(Writer()):
        try:
            files = input_files(folder)
            return solve.main(["--folder", str(folder), "--approvals", str(files["approvals"]),
                               "--conflicts", str(files["conflicts"])] + args) or 0
        except SystemExit as e:                       # argparse errors
            return e.code or 0
        except Exception:
            print("\nSomething went wrong. Please send this to whoever maintains the scheduler:\n")
            traceback.print_exc()
            return 1


def install_packages(names, write):
    cmd = [sys.executable, "-m", "pip", "install"] + ([] if sys.prefix != sys.base_prefix else ["--user"]) + names
    write("$ " + " ".join(cmd) + "\n")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # no console flashing on Windows
    for line in p.stdout:
        write(line)
    return p.wait()


def open_path(path):
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)                            # noqa: the Windows way to open a file or folder
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def load_folder():
    folder = load_config().get("folder")
    if folder and Path(folder).is_dir():
        return Path(folder)
    DATA_FOLDER.mkdir(exist_ok=True)
    return DATA_FOLDER


def save_folder(folder):
    save_config(folder=str(folder))


def shorten(text, room):
    """Long paths shortened in the middle: '/home/.../OneDrive/Combos'."""
    return text if len(text) <= room else text[:room // 3] + " \u2026 " + text[-(room - room // 3 - 3):]


# ---------------------------------------------------------------- the window

class App:
    def __init__(self, root):
        self.root, self.folder, self.queue, self.busy = root, load_folder(), queue.Queue(), False
        import theme
        self.theme = theme
        self.mode = load_config().get("theme", "light")
        self.palette = theme.apply(root, self.mode)
        root.title("Combo Scheduler")
        root.minsize(940, 640)

        shell = ttk.Frame(root, padding=(20, 16, 20, 10))
        shell.pack(fill="both", expand=True)

        # header: title, folder, dark mode
        head = ttk.Frame(shell)                       # row 1: title and dark mode
        head.pack(fill="x")
        self.dark = tk.BooleanVar(value=self.mode == "dark")
        ttk.Checkbutton(head, text="Dark mode", variable=self.dark, command=self.toggle_theme,
                        style="Switch.TCheckbutton" if theme.sv_ttk else "TCheckbutton").pack(side="right")
        ttk.Label(head, text="Combo Scheduler", style="Title.TLabel").pack(side="left")
        self.shell = shell
        self.settings = self.swaps = self.combos = self.schedule = None
        self.buttons = []
        self.root.after(100, self.drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        missing = missing_packages(include_optional=True)
        if missing:
            self.build_setup(missing)
        else:
            self.build_main()

    def build_main(self):
        """The full app: data folder, Run tab, and the other tabs."""
        shell = self.shell
        where = ttk.Frame(shell)                      # row 2: data folder and its buttons
        where.pack(fill="x", pady=(4, 0))
        ttk.Button(where, text="Open folder", command=lambda: open_path(self.folder)).pack(side="right", padx=(6, 0))
        ttk.Button(where, text="Change folder...", command=self.change_folder).pack(side="right")
        self.folder_label = ttk.Label(where, text=self.folder_text(), style="Sub.TLabel")
        self.folder_label.pack(side="left", fill="x", expand=True)

        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True, pady=(14, 0))
        run_tab = ttk.Frame(self.tabs, padding=(4, 12, 4, 4))
        self.tabs.add(run_tab, text="Run")
        from settings_panel import SettingsPanel
        from swap_panel import SwapPanel
        from combos_panel import CombosPanel
        self.combos = CombosPanel(self.tabs, lambda: self.folder, lambda: self.palette, open_path,
                                  on_change=lambda: self.swaps and self.swaps.load(quiet=True))
        self.tabs.add(self.combos.frame, text="Combos")
        self.swaps = SwapPanel(self.tabs, lambda: self.folder, self.after_swap, lambda: self.palette)
        self.tabs.add(self.swaps.frame, text="Swaps")
        from schedule_panel import SchedulePanel
        self.schedule = SchedulePanel(self.tabs, self.swaps, self.goto_swaps,
                                      lambda done: self.run(["--stats", "--pdf"], "Exporting Schedule.pdf...",
                                                            on_done=done),
                                      lambda: self.open_file("Schedule.pdf"), lambda: self.palette, open_path)
        self.tabs.insert(1, self.schedule.frame, text="Schedule")
        self.settings = SettingsPanel(self.tabs, lambda: self.folder, lambda: self.palette)
        self.tabs.add(self.settings.frame, text="Settings")
        self.tabs.add(self.about_tab(), text="About")

        # which input spreadsheets are read (usually the data folder's; Choose... picks another file)
        sources = ttk.Frame(run_tab)
        sources.pack(fill="x", pady=(0, 12))
        self.source_labels = {}
        for r, (which, title) in enumerate([("approvals", "Combo approvals"), ("conflicts", "Conflicts")]):
            ttk.Label(sources, text=title + ":", width=17, anchor="w").grid(row=r, column=0, sticky="w", pady=2)
            label = ttk.Label(sources, text="", style="Hint.TLabel", anchor="w")
            label.grid(row=r, column=1, sticky="ew", padx=(0, 8))
            ttk.Button(sources, text="Choose...", command=lambda w=which: self.choose_input(w)).grid(row=r, column=2, pady=2)
            reset = ttk.Button(sources, text="Use data folder", command=lambda w=which: self.choose_input(w, reset=True))
            reset.grid(row=r, column=3, padx=(6, 0), pady=2)
            self.source_labels[which] = (label, reset)
        sources.columnconfigure(1, weight=1)
        self.show_sources()

        # the three steps, as cards
        cards = ttk.Frame(run_tab)
        cards.pack(fill="x")
        for col, (num, title, hint, label, cmd) in enumerate([
            ("1", "Check inputs", "Reads Combo Approvals.xlsx and Conflicts.xlsx and lists anything to look at. "
             "Changes nothing.", "Check", lambda: self.run(["--check"], "Checking the inputs...")),
            ("2", "Make schedule", "Builds a new Schedule.xlsx and Schedule.pdf. Once per semester.",
             "Make schedule", self.make_schedule),
            ("3", "Check the schedule", "Rule check and stats for Schedule.xlsx as it is now (after swaps or edits "
             "in Excel). Export the PDF from the Schedule tab.", "Check",
             lambda: self.run(["--stats"], "Checking Schedule.xlsx...")),
        ]):
            card = ttk.Frame(cards, style="Card.TFrame", padding=(16, 14))
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
            cards.columnconfigure(col, weight=1, uniform="card")
            ttk.Label(card, text=f"Step {num}", style="Step.TLabel").pack(anchor="w")
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(2, 4))
            hint_label = ttk.Label(card, text=hint, style="Hint.TLabel", justify="left")
            hint_label.pack(anchor="w", fill="x")
            card.bind("<Configure>", lambda e, l=hint_label: l.configure(wraplength=max(e.width - 34, 120)))
            b = ttk.Button(card, text=label, style="Accent.TButton", command=cmd)
            b.pack(anchor="w", pady=(12, 0))
            self.buttons.append(b)

        files = ttk.Frame(run_tab)
        files.pack(fill="x", pady=(14, 8))
        for name in ("Schedule.pdf", "Schedule.xlsx"):
            ttk.Button(files, text=f"Open {name}", command=lambda n=name: self.open_file(n)).pack(side="left", padx=(0, 8))

        self.output_panel(run_tab)
        self.status = ttk.Label(shell, text="Ready.", style="Hint.TLabel")
        self.status.pack(fill="x", pady=(8, 0))
        self.write("Ready. Make sure the two spreadsheets above are the latest (OneDrive can keep them synced), "
                   "then start with step 1.\n")
        self.root.after(300, self.autoload)

    def output_panel(self, parent):
        """The box that shows what a step printed (self.out)."""
        box = ttk.Frame(parent, style="Card.TFrame", padding=1)
        box.pack(fill="both", expand=True)
        bar = ttk.Scrollbar(box, orient="vertical")
        bar.pack(side="right", fill="y")
        self.out = tk.Text(box, wrap="word", state="disabled", relief="flat", borderwidth=0, highlightthickness=0,
                           padx=14, pady=10, font=(self.theme.mono_font(), 10), yscrollcommand=bar.set)
        self.out.pack(side="left", fill="both", expand=True)
        bar.configure(command=self.out.yview)
        self.color_output()

    # ------------------------------------------------------------ first run: install the packages, nothing else
    def build_setup(self, missing):
        """Only what's needed to install the packages (and the About tab). The full app opens by itself after."""
        self.tabs = ttk.Notebook(self.shell)
        self.tabs.pack(fill="both", expand=True, pady=(14, 0))
        tab = ttk.Frame(self.tabs, padding=(24, 20))
        self.tabs.add(tab, text="Setup")
        self.tabs.add(self.about_tab(), text="About")
        ttk.Label(tab, text="One-time setup", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(tab, text="The scheduler needs a few free add-ons for Python (" + ", ".join(missing) + "). "
                            "Installing them takes about a minute and needs an internet connection. This happens "
                            "only once on this computer, and the scheduler opens by itself when it's done.",
                  wraplength=760, justify="left").pack(anchor="w", pady=(8, 16))
        row = ttk.Frame(tab)
        row.pack(anchor="w", pady=(0, 16))
        self.setup_button = ttk.Button(row, text="Install", style="Accent.TButton", command=self.install)
        self.setup_button.pack(side="left")
        self.skip_button = ttk.Button(row, text="Continue without them", command=self.skip_setup)
        if not missing_packages():                    # only the look (sv-ttk) and the pop-up calendar are missing
            self.skip_button.pack(side="left", padx=8)
        self.output_panel(tab)
        self.status = ttk.Label(self.shell, text="", style="Hint.TLabel")
        self.status.pack(fill="x", pady=(8, 0))

    def install(self):
        self.setup_button.configure(state="disabled")
        self.skip_button.pack_forget()
        self.status.configure(text="Installing... (about a minute)")

        def job():
            code = install_packages(missing_packages(include_optional=True), self.write)
            self.queue.put(lambda: self.after_install(code))
        threading.Thread(target=job, daemon=True).start()

    def after_install(self, code):
        if code == 0 and not missing_packages(include_optional=True):
            self.write("\nInstalled. Opening the scheduler...\n")
            self.root.after(800, self.restart)
            return
        self.write("\nInstalling didn't work (see above). Check the internet connection and try again, or get in "
                   "touch (About tab).\n")
        self.status.configure(text="")
        self.setup_button.configure(state="normal", text="Try again")
        if not missing_packages():
            self.skip_button.pack(side="left", padx=8)

    def restart(self):
        """Opens a fresh copy of the app, which can use the new packages, and closes this one."""
        subprocess.Popen([sys.executable, str(HERE / "scheduler_app.py")])
        self.root.destroy()

    def skip_setup(self):
        """Without the optional packages: the full app, with typed dates and the plainer look."""
        self.tabs.destroy()
        self.status.destroy()
        self.build_main()

    def on_close(self):
        if self.swaps and self.swaps.pending and not messagebox.askyesno(
                "Unsaved swaps", f"{len(self.swaps.pending)} swap change(s) haven't been saved to Schedule.xlsx. "
                "Close anyway and lose them?", icon="warning"):
            return
        self.root.destroy()

    def autoload(self):
        """Loads the Combos and Swaps tabs from the data folder (at start, after a folder change, after a run)."""
        for panel in (self.combos, self.swaps):
            if panel:
                panel.load(quiet=True)

    def about_tab(self):
        tab = ttk.Frame(self.tabs, padding=(28, 28))
        ttk.Label(tab, text="Combo Scheduler", style="Title.TLabel").pack(anchor="w")
        ttk.Label(tab, text=f"Made by {AUTHOR}.", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(tab, text="Questions, ideas, or something not working the way it should? Get in touch, happy to "
                            "help:", wraplength=640, justify="left").pack(anchor="w", pady=(14, 4))
        row = ttk.Frame(tab)
        row.pack(anchor="w")
        email = ttk.Label(row, text=EMAIL, style="Link.TLabel", cursor="hand2")   # click: opens the mail app
        email.pack(side="left")
        email.bind("<Button-1>", lambda _: __import__("webbrowser").open(f"mailto:{EMAIL}?subject=Combo%20Scheduler"))

        def copy(_=None):
            from clipboard import copy_text
            copy_text(self.root, EMAIL)
            copy_link.configure(text="Copied")
            self.root.after(2000, lambda: copy_link.configure(text="Copy"))
        copy_link = ttk.Label(row, text="Copy", style="Hint.TLabel", cursor="hand2")
        copy_link.pack(side="left", padx=(12, 0))
        copy_link.bind("<Button-1>", copy)
        ttk.Label(tab, text="Every set on that calendar is a group of students getting up on stage to play music "
                            "together. Thanks for making it happen, and I hope this leaves you a little less time in "
                            "spreadsheets and a little more time listening. Have a great semester of shows!",
                  wraplength=640, justify="left").pack(anchor="w", pady=(24, 0))
        ttk.Label(tab, text="Free to use, share and change.", style="Hint.TLabel").pack(anchor="w", pady=(24, 0))
        return tab

    def show_sources(self):
        """The Run tab's two input lines: which file each one is, and whether it's there."""
        for which, (label, reset) in self.source_labels.items():
            path, picked = input_files(self.folder)[which], is_picked(self.folder, which)
            text = shorten(str(path), 70) if picked else f"{path.name} in the data folder"
            label.configure(text=text + ("" if path.exists() else "   (not there yet)"))
            if picked:
                reset.grid()
            else:
                reset.grid_remove()

    def choose_input(self, which, reset=False):
        if reset:
            pick_input_file(self.folder, which, None)
        else:
            current = input_files(self.folder)[which]
            picked = filedialog.askopenfilename(
                title="Combo approvals spreadsheet" if which == "approvals" else "Conflicts spreadsheet",
                initialdir=str(current.parent if current.parent.is_dir() else self.folder),
                filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
            if not picked:
                return
            picked = Path(picked)
            usual = self.folder / (APPROVALS_FILE if which == "approvals" else CONFLICTS_FILE)
            pick_input_file(self.folder, which, None if picked == usual else picked)   # the usual file: nothing to remember
        self.show_sources()
        self.autoload()

    def folder_text(self, room=60):
        """The data folder, shortened in the middle when long: 'Data folder:  /home/.../OneDrive/Combos'."""
        return f"Data folder:  {shorten(str(self.folder), room)}"

    def color_output(self):
        p, mono = self.palette, self.theme.mono_font()
        self.out.configure(background=p["panel"], foreground=p["text"], insertbackground=p["text"],
                           selectbackground=p["accent"], selectforeground=p["accent_text"])
        self.out.tag_configure("warn", foreground=p["warn"])
        self.out.tag_configure("bad", foreground=p["bad"], font=(mono, 10, "bold"))
        self.out.tag_configure("good", foreground=p["good"], font=(mono, 10, "bold"))

    def toggle_theme(self):
        self.mode = "dark" if self.dark.get() else "light"
        self.palette = self.theme.apply(self.root, self.mode)
        self.color_output()
        if self.settings:
            self.settings.recolor()
        if self.swaps:
            self.swaps.recolor()
        if self.combos:
            self.combos.recolor()
        if self.schedule:
            self.schedule.recolor()
        save_config(theme=self.mode)

    # output
    def write(self, text):
        self.queue.put(text)

    def drain(self):
        """Moves text from the worker thread into the window (tkinter may only be touched from this thread)."""
        try:
            while True:
                item = self.queue.get_nowait()
                if callable(item):
                    item()
                    continue
                self.out.configure(state="normal")
                for line in item.splitlines(keepends=True):
                    tag = ("bad" if ("PROBLEM" in line or "Can't continue" in line or "went wrong" in line) else
                           "warn" if ("WARN" in line) else
                           "good" if ("All hard rules hold" in line or line.startswith("Wrote")) else None)
                    self.out.insert("end", line, tag)
                self.out.see("end")
                self.out.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    # actions
    def change_folder(self):
        picked = filedialog.askdirectory(initialdir=str(self.folder), title="Folder with Combo Approvals.xlsx, "
                                         "Conflicts.xlsx and settings.json")
        if picked:
            self.folder = Path(picked)
            self.folder_label.configure(text=self.folder_text())
            save_folder(self.folder)
            self.show_sources()
            if self.settings:
                self.settings.reload()
            self.autoload()

    def open_file(self, name):
        path = self.folder / name
        if path.exists():
            open_path(path)
        else:
            messagebox.showinfo("Not there yet", f"There is no {name} in the data folder yet.")

    def make_schedule(self):
        existing = [n for n in ("Schedule.xlsx", "Schedule.pdf") if (self.folder / n).exists()]
        if existing and not messagebox.askyesno(
                "Replace the schedule?",
                f"{' and '.join(existing)} already exist and will be REPLACED by a brand-new schedule.\n\n"
                "Any swaps or edits recorded in the old Schedule.xlsx will be lost. To keep it, cancel and rename "
                "or copy it first.\n\nAfter the schedule is published, use button 3 instead.\n\nMake a new schedule?",
                icon="warning", default="no"):
            return
        self.run(["-y", "--pdf"], "Making the schedule (this can take up to a minute)...")

    def goto_swaps(self, cid, d, k, mode="swap"):
        self.tabs.select(self.swaps.frame)
        self.swaps.preselect(cid, d, k, mode)

    def after_swap(self, message, on_done=None):
        """After the Swaps tab saved: check and rebuild the PDF in the background, staying on the Swaps tab."""
        self.run(["--stats", "--pdf"], "Checking the rules and rebuilding Schedule.pdf...", intro=message,
                 on_done=on_done)

    def run(self, args, message, intro="", on_done=None):
        missing = missing_packages()
        if missing:
            messagebox.showwarning("Missing packages", f"Install these first: {', '.join(missing)}.")
            return
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")
        if intro:
            self.write(intro)

        def job():
            code = run_solve(args, self.folder, self.write)
            self.write("\n" + ("Done." if code == 0 else "Done, but there are problems: see the red lines above.") + "\n")
            if on_done:
                self.queue.put(lambda: on_done(code))
        self.start(job, message)

    def start(self, job, message):
        if self.busy:
            return
        self.busy = True
        self.status.configure(text=message)
        for b in self.buttons:
            b.configure(state="disabled")

        def wrapped():
            try:
                job()
            finally:
                self.queue.put(self.finish)
        threading.Thread(target=wrapped, daemon=True).start()

    def finish(self):
        self.busy = False
        self.show_sources()
        self.autoload()                               # the schedule may have changed
        self.status.configure(text="Ready.")
        for b in self.buttons:
            b.configure(state="normal")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
