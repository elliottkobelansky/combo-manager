"""One-click window for the director: check the inputs, make the schedule, rebuild the PDF after hand edits (Run
tab), and change the settings (Settings tab, saved in settings.json).

    Double-click "Make Schedule.bat" (Windows), "Make Schedule.command" (Mac) or "make-schedule.sh" (Linux),
    or run:  python app/scheduler_app.py

It runs solve.py inside this window, on the data folder shown at the top: any folder, on this computer or kept in
sync (OneDrive, SharePoint, a network drive), picked on first run and remembered on this computer ("Change folder..."
picks another; data_folder.py says what's in it, backup.py zips it). Needs Python 3 with tkinter (standard on Windows and the
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
import time
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# these three are standard library only: safe before the packages are installed
from app_config import input_files, is_picked, load_config, pick_input_file, save_config, saved_folder  # noqa: E402
from data_folder import (APP_DATA, APPROVALS_FILE, CONFLICTS_FILE, OLD_APPROVALS_FILE, SCHEDULE_PDF,  # noqa: E402
                         SCHEDULE_XLSX, app_data, looks_like_data_folder, problem, settings_path, usual_inputs)
import shared_folder  # noqa: E402
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
    """The data folder picked before on this computer, when it can be used; else None, and the app asks. A picked
    folder that's gone (a sync app or network drive not connected yet, say) is asked for again, never silently
    swapped for another."""
    folder = saved_folder()
    return folder if not problem(folder) else None


def save_folder(folder):
    save_config(folder=str(folder))


def default_parent():
    """Where to suggest a new data folder or a backup: Documents, else the home folder."""
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


def shorten(text, room):
    """Long paths shortened in the middle: '/home/.../Shared/Combos'."""
    return text if len(text) <= room else text[:room // 3] + " \u2026 " + text[-(room - room // 3 - 3):]


# ---------------------------------------------------------------- the window

class App:
    def __init__(self, root):
        self.root, self.folder, self.queue, self.busy = root, load_folder(), queue.Queue(), False
        self.exported = set()                         # folders whose missing exports were made (autoload)
        import theme
        self.theme = theme
        self.mode = load_config().get("theme", "light")
        scale = load_config().get("text_size", 1.0)
        self.palette = theme.apply(root, self.mode, scale if scale in theme.SCALES else 1.0)
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
        sizes = ttk.Frame(head)                       # text size: A- 100% A+
        sizes.pack(side="right", padx=(0, 18))
        ttk.Button(sizes, text="A\u2212", width=3, command=lambda: self.text_size(-1)).pack(side="left")
        self.size_label = ttk.Label(sizes, text="", width=5, anchor="center")
        self.size_label.pack(side="left", padx=4)
        ttk.Button(sizes, text="A+", width=3, command=lambda: self.text_size(+1)).pack(side="left")
        ttk.Label(sizes, text="Text size", style="Hint.TLabel").pack(side="left", padx=(8, 0))
        self.size_label.configure(text=f"{round(theme.SCALE * 100)}%")
        ttk.Label(head, text="Combo Scheduler", style="Title.TLabel").pack(side="left")
        self.shell = shell
        self.settings = self.swaps = self.combos = self.schedule = None
        self.buttons, self.runs = [], 0
        self.root.after(100, self.drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        missing = missing_packages(include_optional=True)
        if missing:
            self.build_setup(missing)
        else:
            self.build_main()

    # ------------------------------------------------------------ no data folder yet: ask where it is
    def folder_screen(self):
        """First run, or the folder picked before can't be used: where the data folder is (an existing one, a new
        one, or one restored from a backup). The full app opens once one is chosen."""
        gone = saved_folder()
        frame = ttk.Frame(self.shell, padding=(24, 20))
        frame.pack(fill="both", expand=True, pady=(14, 0))
        if gone:
            title = "The data folder can't be opened"
            text = (f"The data folder used before on this computer can't be used: {problem(gone)}.\n\n    {gone}\n\n"
                    "If it's in a synced or shared folder (OneDrive, SharePoint, a network drive), check that it's "
                    "connected and finished syncing, then choose it again. Otherwise choose another folder, or "
                    "restore a backup.")
        else:
            title = "Where should the scheduler keep its files?"
            text = ("The scheduler keeps everything in one data folder: the two spreadsheets from the forms "
                    "(Approvals.xlsx and Conflicts.xlsx), the settings, the schedule, the PDFs and the past "
                    "semesters. The program itself can be installed again any time; the data folder is what matters."
                    "\n\n\u2022  Only this computer will use the scheduler: any folder on it works, e.g. "
                    "Documents/Combo Scheduler data. Make a backup now and then (the Back up... button) and keep "
                    "it somewhere else.\n\u2022  Several computers, or someone taking over later: use a folder "
                    "that's shared and kept in sync, e.g. in OneDrive, SharePoint or on a network drive. Each "
                    "computer chooses the same folder once.\n\nThe choice is remembered on this computer; "
                    "\"Change folder...\" picks another later.")
        ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(frame, text=text, wraplength=760, justify="left").pack(anchor="w", pady=(8, 20))
        row = ttk.Frame(frame)
        row.pack(anchor="w")

        def use(folder):
            if folder and self.accept_folder(folder):
                frame.destroy()
                self.folder = folder
                save_folder(folder)
                self.build_main(taken=True)

        def existing():
            picked = filedialog.askdirectory(title="The Combo Scheduler data folder",
                                             initialdir=str(gone.parent if gone and gone.parent.is_dir() else
                                                            default_parent()))
            use(Path(picked) if picked else None)

        def new():
            parent = filedialog.askdirectory(title="Where to make the new 'Combo Scheduler data' folder",
                                             initialdir=str(default_parent()))
            if parent:
                from backup import new_folder
                folder = new_folder(parent, "Combo Scheduler data")
                try:
                    folder.mkdir()
                except OSError as e:
                    messagebox.showerror("Can't make the folder", f"Can't make {folder}:\n{e}")
                    return
                use(folder)

        def quit_():
            self.closed = True
            self.root.destroy()
        ttk.Button(row, text="Choose existing folder...", style="Accent.TButton", command=existing).pack(side="left")
        ttk.Button(row, text="Make a new folder...", command=new).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Restore from a backup...", command=lambda: use(self.restore())).pack(side="left",
                                                                                              padx=(8, 0))
        ttk.Button(row, text="Quit", command=quit_).pack(side="left", padx=(24, 0))

    def accept_folder(self, folder):
        """Checks a folder before it becomes the data folder: it can be used, it's meant to be one, and no one else
        has it open (or the user opens it anyway). True = go ahead (it's marked as open here)."""
        why = problem(folder)
        if why:
            messagebox.showerror("Can't use this folder", f"{folder}\n\nThis folder can't be the data folder: {why}.")
            return False
        if not looks_like_data_folder(folder) and not messagebox.askyesno(
                "Use this folder?", f"{folder}\n\nThis folder has other things in it and no scheduler files. The "
                "scheduler's files would be added among them.\n\nUse it anyway? (Usually better: a folder of its "
                "own, e.g. 'Combo Scheduler data'.)", icon="warning", default="no"):
            return False
        return self.take_folder(folder)

    def build_main(self, taken=False):
        """The full app: data folder, Run tab, and the other tabs. taken: the folder was just checked and marked."""
        shell = self.shell
        if self.folder is None:
            self.folder_screen()
            return
        if not taken and not self.take_folder(self.folder):
            self.closed = True
            self.root.destroy()
            return
        where = ttk.Frame(shell)                      # row 2: data folder and its buttons
        where.pack(fill="x", pady=(4, 0))
        ttk.Button(where, text="Open folder", command=lambda: open_path(self.folder)).pack(side="right", padx=(6, 0))
        ttk.Button(where, text="Change folder...", command=self.change_folder).pack(side="right")
        ttk.Button(where, text="Restore...", command=self.restore_and_switch).pack(side="right", padx=(0, 6))
        ttk.Button(where, text="Back up...", command=self.make_backup).pack(side="right", padx=(0, 6))
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
                                  on_change=lambda: self.swaps and self.swaps.load(quiet=True),
                                  get_swaps=lambda: self.swaps,
                                  after_schedule_change=lambda message: self.run(
                                      ["--stats", "--export"], "Checking the rules and rebuilding the PDF and xlsx...",
                                      intro=message))
        self.tabs.add(self.combos.frame, text="Combos")
        self.swaps = SwapPanel(self.tabs, lambda: self.folder, self.after_swap, lambda: self.palette)
        self.tabs.add(self.swaps.frame, text="Swaps")
        from schedule_panel import SchedulePanel
        self.schedule = SchedulePanel(self.tabs, self.swaps, self.goto_swaps,
                                      lambda done: self.run(["--stats", "--export"],
                                                            "Exporting Schedule.pdf and Schedule.xlsx...", on_done=done),
                                      self.open_file, lambda: self.palette, open_path)
        self.tabs.insert(1, self.schedule.frame, text="Schedule")
        self.settings = SettingsPanel(self.tabs, lambda: self.folder, lambda: self.palette, on_save=self.autoload,
                                      on_dirty=lambda dirty: self.settings and self.tabs.tab(
                                          self.settings.frame, text="Settings \u25cf" if dirty else "Settings"))
        # (a new data folder has no settings yet: unsaved from the start, before self.settings is set)
        self.tabs.add(self.settings.frame, text="Settings \u25cf" if self.settings.dirty else "Settings")
        self.current_tab = None
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)
        self.tabs.add(self.about_tab(), text="About")

        # which input spreadsheets are read (usually the data folder's; Choose... picks another file)
        sources = ttk.Frame(run_tab)
        sources.pack(fill="x", pady=(0, 12))
        self.source_labels = {}
        for r, (which, title) in enumerate([("approvals", "Approvals"), ("conflicts", "Conflicts")]):
            ttk.Label(sources, text=title + ":", width=17, anchor="w").grid(row=r, column=0, sticky="w", pady=2)
            label = ttk.Label(sources, text="", style="Hint.TLabel", anchor="w")
            label.grid(row=r, column=1, sticky="ew", padx=(0, 8))
            ttk.Button(sources, text="Choose...", command=lambda w=which: self.choose_input(w)).grid(row=r, column=2, pady=2)
            reset = ttk.Button(sources, text="Use data folder", command=lambda w=which: self.choose_input(w, reset=True))
            reset.grid(row=r, column=3, padx=(6, 0), pady=2)
            self.source_labels[which] = (label, reset)
        sources.columnconfigure(1, weight=1)

        # the three steps, as cards
        cards = ttk.Frame(run_tab)
        cards.pack(fill="x")
        for col, (num, title, hint, label, cmd) in enumerate([
            ("1", "Check inputs", "", "Check",             # hint: the input files' names (show_sources)
             lambda: self.run(["--check"], "Checking the inputs...")),
            ("2", "Make schedule", "Makes a new schedule (and Schedule.pdf and Schedule.xlsx). Once per semester.",
             "Make schedule", self.make_schedule),
            ("3", "Check the schedule", "Rule check and stats for the schedule as it is now (after swaps). "
             "Export the PDF or xlsx from the Schedule tab.", "Check",
             lambda: self.run(["--stats"], "Checking the schedule...")),
        ]):
            card = ttk.Frame(cards, style="Card.TFrame", padding=(16, 14))
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
            cards.columnconfigure(col, weight=1, uniform="card")
            ttk.Label(card, text=f"Step {num}", style="Step.TLabel").pack(anchor="w")
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(2, 4))
            hint_label = ttk.Label(card, text=hint, style="Hint.TLabel", justify="left")
            hint_label.pack(anchor="w", fill="x")
            if num == "1":
                self.step1_hint = hint_label
            card.bind("<Configure>", lambda e, l=hint_label: l.configure(wraplength=max(e.width - 34, 120)))
            b = ttk.Button(card, text=label, style="Accent.TButton", command=cmd)
            b.pack(anchor="w", pady=(12, 0))
            self.buttons.append(b)
        self.show_sources()

        files = ttk.Frame(run_tab)
        files.pack(fill="x", pady=(14, 8))
        for name in (SCHEDULE_PDF, SCHEDULE_XLSX):
            ttk.Button(files, text=f"Open {name}", command=lambda n=name: self.open_file(n)).pack(side="left", padx=(0, 8))

        self.output_panel(run_tab)
        self.status = ttk.Label(shell, text="Ready.", style="Hint.TLabel")
        self.status.pack(fill="x", pady=(8, 0))
        self.write("Ready. Make sure the two spreadsheets above are the latest, then start with step 1.\n")
        self.root.after(300, self.autoload)
        self.root.after(shared_folder.REFRESH * 1000, self.keep_folder)
        self.root.after(800, self.check_copies)

    # several computers on one data folder (shared_folder.py)
    def take_folder(self, folder):
        """Marks folder as open here. When another computer has it open: says so, and asks whether to open it
        anyway. False = don't."""
        other = shared_folder.holder(folder)
        if other and not messagebox.askyesno(
                "Data folder in use", f"This data folder is open in the Combo Scheduler on "
                f"{shared_folder.describe(other)}.\n\nTwo computers changing it at the same time can lose changes: "
                "best close the app there first.\n\nOpen it here anyway?", icon="warning", default="no"):
            return False
        shared_folder.claim(folder)
        self.told_taken = False
        return True

    def keep_folder(self):
        """Every few minutes: still here (the lock file). Says once when another computer opened the folder since."""
        other = shared_folder.refresh(self.folder)
        if other and not self.told_taken:
            self.told_taken = True
            messagebox.showwarning(
                "Data folder opened elsewhere", f"The data folder was also opened on {shared_folder.describe(other)}."
                "\n\nChanges saved on both at the same time can be lost: best close the app on one of them. (Saving "
                "here still checks that nothing changed underneath.)")
        self.root.after(shared_folder.REFRESH * 1000, self.keep_folder)

    def check_copies(self):
        """A sync app's conflict copies in the data folder ('Schedule-OFFICE-PC.xlsx'): says which to sort out."""
        copies = shared_folder.conflict_copies(self.folder)
        if copies:
            lines = "\n".join(f"  {c.relative_to(self.folder)}  (next to {u.name})" for c, u in copies)
            messagebox.showwarning(
                "Two versions of a file", "The sync app (OneDrive, Dropbox, ...) kept two versions of these files, "
                "probably because two computers "
                f"saved them at the same time:\n\n{lines}\n\nThe app only reads the file with the usual name. Open "
                "the data folder, compare the two, keep the right one under the usual name and delete the other.")

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
        if self.folder:
            shared_folder.release(self.folder)
        subprocess.Popen([sys.executable, str(HERE / "scheduler_app.py")])
        self.root.destroy()

    def skip_setup(self):
        """Without the optional packages: the full app, with typed dates and the plainer look."""
        self.tabs.destroy()
        self.status.destroy()
        self.build_main()

    def tab_changed(self, _=None):
        """Leaving the Settings tab with unsaved changes: save, undo, or stay."""
        now = self.tabs.select()
        left_settings = self.settings and self.current_tab == str(self.settings.frame) and now != self.current_tab
        self.current_tab = now
        if left_settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)

    def on_close(self):
        if self.settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)
            return
        if self.combos and not self.combos.ask_to_save():
            self.tabs.select(self.combos.frame)
            return
        if self.swaps and self.swaps.pending and not messagebox.askyesno(
                "Unsaved swaps", f"{len(self.swaps.pending)} swap change(s) haven't been saved. "
                "Close anyway and lose them?", icon="warning"):
            return
        if self.folder and self.settings:
            shared_folder.release(self.folder)
        self.root.destroy()

    def autoload(self):
        """Loads the Combos and Swaps tabs from the data folder (at start, after a folder change, after a run). When
        the schedule's exports aren't there (an old Schedule.xlsx was just converted, or they were deleted), makes them
        (once per folder)."""
        for panel in (self.combos, self.swaps):
            if panel:
                panel.load(quiet=True)
        if (self.swaps and self.swaps.state and self.folder not in self.exported
                and not all((self.folder / n).exists() for n in (SCHEDULE_PDF, SCHEDULE_XLSX))):
            self.exported.add(self.folder)
            self.run(["--stats", "--export"], "Making Schedule.pdf and Schedule.xlsx...")

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
        """The Run tab's two input lines: which file each one is, and whether it's there; and Step 1 names them."""
        files = input_files(self.folder)
        self.step1_hint.configure(text=f"Reads {files['approvals'].name} and {files['conflicts'].name} and lists "
                                       "anything to look at. Changes nothing.")
        for which, (label, reset) in self.source_labels.items():
            path, picked = files[which], is_picked(self.folder, which)
            try:                                      # any name; in the data folder (or a folder in it), or anywhere
                text = f"{path.relative_to(self.folder).as_posix()} in the data folder"
            except ValueError:
                text = shorten(str(path), 70)
            if not path.exists():                     # 'App data' sounds like the place for it, but isn't
                text += (f"   (not there: it's in {APP_DATA}, move it up one level)"
                         if not picked and (app_data(self.folder) / path.name).exists() else "   (not there yet)")
            label.configure(text=text)
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
                title="Approvals spreadsheet" if which == "approvals" else "Conflicts spreadsheet",
                initialdir=str(current.parent if current.parent.is_dir() else self.folder),
                filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
            if not picked:
                return
            picked = Path(picked)
            other = "conflicts" if which == "approvals" else "approvals"
            others = [CONFLICTS_FILE] if which == "approvals" else [APPROVALS_FILE, OLD_APPROVALS_FILE]
            if picked.name.lower() in [n.lower() for n in others] or picked == input_files(self.folder)[other]:
                messagebox.showerror("Wrong spreadsheet", f"{picked.name} is the {other} spreadsheet. Choose the "
                                     + ("approvals" if which == "approvals" else "conflicts") + " one here.")
                return
            usual = usual_inputs(self.folder)[which]
            pick_input_file(self.folder, which, None if picked == usual else picked)   # the usual file: nothing to remember
        self.show_sources()
        self.autoload()

    def folder_text(self, room=60):
        """The data folder, shortened in the middle when long: 'Data folder:  /home/.../Shared/Combos'."""
        return f"Data folder:  {shorten(str(self.folder), room)}"

    def color_output(self):
        p, mono, size = self.palette, self.theme.mono_font(), self.theme.size(10)
        self.out.configure(font=(mono, size), background=p["panel"], foreground=p["text"], insertbackground=p["text"],
                           selectbackground=p["accent"], selectforeground=p["accent_text"])
        self.out.tag_configure("warn", foreground=p["warn"])
        self.out.tag_configure("bad", foreground=p["bad"], font=(mono, size, "bold"))
        self.out.tag_configure("good", foreground=p["good"], font=(mono, size, "bold"))

    def text_size(self, step):
        """A- / A+: the next smaller or bigger text size; remembered on this computer."""
        steps = self.theme.SCALES
        now = min(range(len(steps)), key=lambda i: abs(steps[i] - self.theme.SCALE))
        new = steps[max(0, min(len(steps) - 1, now + step))]
        if new == self.theme.SCALE:
            return
        self.size_label.configure(text=f"{round(new * 100)}%")
        save_config(text_size=new)
        self.restyle(scale=new)

    def toggle_theme(self):
        self.mode = "dark" if self.dark.get() else "light"
        save_config(theme=self.mode)
        self.restyle()

    def restyle(self, scale=None):
        """After a dark mode or text size change: the theme, then the parts ttk doesn't draw."""
        self.palette = self.theme.apply(self.root, self.mode, scale)
        self.color_output()
        if self.settings:
            self.settings.recolor()
        if self.swaps:
            self.swaps.recolor()
        if self.combos:
            self.combos.recolor()
        if self.schedule:
            self.schedule.recolor()

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
                           "good" if ("All hard rules hold" in line or line.startswith(("Wrote", "Saved the schedule"))) else None)
                    self.out.insert("end", line, tag)
                self.out.see("end")
                self.out.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    # actions
    def change_folder(self):
        if self.settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)
            return
        if self.combos and not self.combos.ask_to_save():
            self.tabs.select(self.combos.frame)
            return
        picked = filedialog.askdirectory(initialdir=str(self.folder), title="The Combo Scheduler data folder")
        if picked:
            self.switch_folder(Path(picked))

    def switch_folder(self, folder):
        """Makes folder the data folder from now on (after checking it), and loads everything from it."""
        if folder == self.folder or not self.accept_folder(folder):
            return
        shared_folder.release(self.folder)
        self.folder = folder
        self.folder_label.configure(text=self.folder_text())
        save_folder(self.folder)
        self.show_sources()
        if self.settings:
            self.settings.reload()
        self.autoload()
        self.check_copies()

    # backups (backup.py)
    def make_backup(self):
        """Zips the data folder to a place the user picks (remembered on this computer)."""
        from backup import backup_name, create_backup
        start = Path(load_config().get("backup_dir") or default_parent())
        picked = filedialog.asksaveasfilename(
            title="Save a backup of the data folder", initialdir=str(start if start.is_dir() else default_parent()),
            initialfile=backup_name(), defaultextension=".zip", filetypes=[("Zip file", "*.zip")])
        if not picked:
            return
        dest = Path(picked)
        self.status.configure(text="Making the backup...")

        def work():
            try:
                return create_backup(self.folder, dest, input_files(self.folder))
            except OSError as e:
                return e

        def done(n):
            if isinstance(n, OSError):
                self.status.configure(text="")
                messagebox.showerror("Backup", f"Couldn't make the backup:\n{n}")
                return
            save_config(backup_dir=str(dest.parent))
            self.status.configure(text=f"Backup saved: {dest} ({n} files).")
            inside = dest.resolve().is_relative_to(self.folder.resolve())
            messagebox.showinfo("Backup saved", f"Saved {dest.name} ({n} files) in:\n{dest.parent}\n\n" + (
                "It's inside the data folder, so it's lost along with it: copy it somewhere else too (another "
                "drive, a USB stick, an email to yourself)." if inside else
                "Keep it somewhere that wouldn't be lost along with this computer or the data folder. To use it: "
                "Restore... (or the first-run screen on a new computer)."))
        from theme import in_background
        in_background(self.root, work, done)

    def restore(self):
        """Asks for a backup zip and where to put it; unpacks it into a new folder there. -> that folder, or None.
        The current data folder is never touched."""
        from backup import BackupError, new_folder, read_backup, restore_backup
        start = Path(load_config().get("backup_dir") or default_parent())
        picked = filedialog.askopenfilename(title="The backup to restore",
                                            initialdir=str(start if start.is_dir() else default_parent()),
                                            filetypes=[("Zip file", "*.zip"), ("All files", "*.*")])
        if not picked:
            return None
        try:
            info = read_backup(picked)
        except BackupError as e:
            messagebox.showerror("Restore", str(e))
            return None
        made = info.get("made", "").replace("T", " ")[:16]
        about = (f"made {made} on {info.get('computer', '?')}, " if made else "") + f"{info['files']} files"
        if not messagebox.askokcancel(
                "Restore", f"{Path(picked).name}\n({about})\n\nNext, choose where to put it: it's unpacked into a "
                "new folder there, which becomes the data folder. Nothing that exists now is changed.\n\n"
                "Several computers? Put it in the shared/synced folder they all use."):
            return None
        parent = filedialog.askdirectory(title="Where to put the restored data folder",
                                         initialdir=str(default_parent()))
        if not parent:
            return None
        dest = new_folder(parent, f"Combo Scheduler data (restored {datetime.now():%Y-%m-%d})")
        try:
            restore_backup(picked, dest)
        except (BackupError, OSError) as e:
            messagebox.showerror("Restore", f"Couldn't restore the backup:\n{e}")
            return None
        return dest

    def restore_and_switch(self):
        if self.settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)
            return
        if self.combos and not self.combos.ask_to_save():
            self.tabs.select(self.combos.frame)
            return
        folder = self.restore()
        if folder:
            self.switch_folder(folder)
            if self.folder == folder:
                messagebox.showinfo("Restored", f"Restored into:\n{folder}\n\nThe scheduler uses it from now on. "
                                    "The folder used before is still there, unchanged.")

    def open_file(self, name):
        """Opens a file in the data folder. Schedule.pdf / .xlsx that aren't there but can be made: made first."""
        path = self.folder / name
        if path.exists():
            open_path(path)
        elif name in (SCHEDULE_PDF, SCHEDULE_XLSX) and self.swaps and self.swaps.state:
            self.run(["--stats", "--export"], f"Making {name}...",
                     on_done=lambda code: path.exists() and open_path(path))
        else:
            messagebox.showinfo("Not there yet", f"There is no {name} in the data folder yet.")

    def make_schedule(self):
        from schedule_file import has_schedule
        other = self.other_semester()
        if other is not None:                         # last semester's files: filed away, nothing is lost
            if not messagebox.askyesno(
                    "New semester", f"The schedule is {('for ' + other) if other else 'from another semester'}. "
                    f"Its files (schedule, PDFs, contact lists, backups) will be moved into "
                    f"'Archive/{other or 'Old schedule'}' in the data folder, then a new schedule is made.\n\nGo ahead?"):
                return
        elif has_schedule(self.folder) and not messagebox.askyesno(
                "Replace the schedule?",
                "There is a schedule already. It will be REPLACED by a brand-new one, and any swaps or text made in "
                "it won't be in the new one (a copy goes to 'App data/Schedule backups').\n\nAfter the schedule is "
                "published, use button 3 instead.\n\nMake a new schedule?", icon="warning", default="no"):
            return
        self.run(["-y", "--export"], "Making the schedule (this can take up to a minute)...", ticker=True)

    def other_semester(self):
        """None when there's no schedule or it's for the settings' semester; otherwise the semester it's for
        ('' when unknown)."""
        try:
            from schedule_file import ScheduleFileError, has_schedule, semester_of
            from settings_file import SettingsError, load_settings
            if not has_schedule(self.folder):
                return None
            settings, _ = load_settings(settings_path(self.folder))
            sem = semester_of(self.folder, settings)
        except (ImportError, SettingsError, ScheduleFileError):
            return None
        return None if sem == settings.semester_name else (sem or "")

    def goto_swaps(self, cid, d, k, mode="swap"):
        self.tabs.select(self.swaps.frame)
        self.swaps.preselect(cid, d, k, mode)

    def after_swap(self, message, on_done=None):
        """After the Swaps tab saved: check and rebuild the exports in the background, staying on the Swaps tab."""
        self.run(["--stats", "--export"], "Checking the rules and rebuilding the PDF and xlsx...", intro=message,
                 on_done=on_done)

    def run(self, args, message, intro="", on_done=None, ticker=False):
        """Runs solve.py with these arguments in the background, its output in the box. ticker: a 'still working'
        line every 10 seconds, so a long solve doesn't look frozen."""
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
        if ticker and self.busy:
            self.runs += 1
            self.root.after(10000, self.tick, self.runs, time.monotonic())

    def tick(self, run, started):
        if not self.busy or run != self.runs:         # finished, or another run started since
            return
        self.write(f"  ...still working ({int(time.monotonic() - started)} s)\n")
        self.root.after(10000, self.tick, run, started)

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


def bring_to_front(root):
    """Started from Terminal (Mac) or a file manager, the window can open behind it: raise it once."""
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()


def main():
    root = tk.Tk()
    app = App(root)
    if getattr(app, "closed", False):               # quit at the "pick the data folder" question
        return
    root.after(200, bring_to_front, root)
    root.mainloop()


if __name__ == "__main__":
    main()
