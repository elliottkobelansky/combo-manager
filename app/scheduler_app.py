"""One-click window for the director: check the inputs, make the schedule, rebuild the PDF after hand edits (Run
tab), and change the settings (Semester tab, saved in semester.json).

    Packaged (dev/build_exe.py, built by GitHub): "Combo Manager.exe" (Windows) or "Combo Manager.app" (Mac),
    with everything included (no Setup screen).
    From source (Linux, for testing): ./combo-manager.sh, or run:  python app/scheduler_app.py
    python app/scheduler_app.py --selftest FILE   loads every part the app needs, writes what it found to FILE,
                                                  exit code 0 = all there (used to check a build)

It runs solve.py inside this window, on the data folder shown at the top: any folder, on this computer or kept in
sync (OneDrive, SharePoint, a network drive), picked on first run and remembered on this computer ("Change folder..."
picks another; data_folder.py says what's in it, backup.py zips it). Needs Python 3 with tkinter (standard on Windows and the
python.org Mac installer) plus openpyxl, ortools and reportlab; the window offers to install those.
"""
import atexit
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
FROZEN = getattr(sys, "frozen", False)                # the packaged app (PyInstaller): every package is included
sys.path.insert(0, str(HERE))
# these three are standard library only: safe before the packages are installed
from app_config import input_files, load_config, save_config, saved_folder  # noqa: E402
from data_folder import (DEFAULT_NAME, SCHEDULE_PDF, SCHEDULE_XLSX, export_path, looks_like_data_folder, problem,  # noqa: E402
                         settings_path)
import shared_folder  # noqa: E402
import app_log  # noqa: E402
AUTHOR, EMAIL = "Elliott Kobelansky", "elliottkobelansky@gmail.com"
APP_NAME = "Combo Manager"
VERSION = "0.1.0"                                 # up by 0.1 per release; 1.0 once it is trusted for real use
PACKAGES = {"openpyxl": "openpyxl", "ortools": "ortools", "reportlab": "reportlab"}   # import name -> pip name
OPTIONAL = {"tkcalendar": "tkcalendar"}   # the pop-up calendars

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:                                   # e.g. Homebrew Python on a Mac without python-tk
    print("This Python has no tkinter (the window toolkit). Install Python from https://www.python.org/downloads/"
          " (it includes tkinter), or on Linux: sudo apt install python3-tk")
    sys.exit(1)


# ---------------------------------------------------------------- work that doesn't need the window (testable)

def missing_packages(include_optional=False):
    if FROZEN:
        return []
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
            print("\nSomething went wrong. Please send this to whoever maintains Combo Manager (it's in the log "
                  "too: About tab > Open the log):\n")
            traceback.print_exc()
            return 1


def pinned(names):
    """pip names -> 'name==version' from requirements.txt (the versions the scheduler is tested with)."""
    try:
        lines = (HERE.parent / "requirements.txt").read_text().splitlines()
    except OSError:
        return names
    pins = {l.split("==")[0].strip().lower().replace("_", "-"): l.strip() for l in lines if "==" in l
            and not l.lstrip().startswith("#")}
    return [pins.get(n.lower().replace("_", "-"), n) for n in names]


def install_packages(names, write):
    cmd = [sys.executable, "-m", "pip", "install"] + ([] if sys.prefix != sys.base_prefix else ["--user"]) + pinned(names)
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


def start_folder(folder):
    """A new data folder's first files: the example settings, and no sheets linked (combos are entered in the app
    until some are)."""
    from settings_file import DEFAULTS, save_data
    from store import Store
    save_data(settings_path(folder), DEFAULTS)
    store = Store(folder)
    for which in ("approvals", "conflicts"):
        store.set_linked(which, False)
    store.save()


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
        root.report_callback_exception = self.tk_error
        set_icon(root)
        import theme
        self.theme = theme
        self.mode = load_config().get("theme", "light")
        scale = load_config().get("text_size", 1.0)
        self.palette = theme.apply(root, self.mode, scale if scale in theme.SCALES else 1.0)
        root.title(APP_NAME)
        root.minsize(940, 640)

        shell = ttk.Frame(root, padding=(20, 16, 20, 10))
        shell.pack(fill="both", expand=True)
        head = ttk.Frame(shell)                       # row 1: the title (dark mode, text size: Settings tab)
        head.pack(fill="x")
        ttk.Label(head, text=APP_NAME, style="Title.TLabel").pack(side="left")
        self.dark = tk.BooleanVar(value=self.mode == "dark")
        self.shell = shell
        self.results = {}                             # "combos" / "schedule": the tabs' results boxes
        self.settings = self.swaps = self.combos = self.schedule = None
        self.buttons, self.runs = [], 0
        self.root.after(100, self.drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        try:                                          # a Mac's Cmd+Q / Quit menu / Dock Quit: the same checks
            self.root.createcommand("::tk::mac::Quit", self.on_close)
            if sys.platform == "darwin":
                self.root.createcommand("exit", self.on_close)
        except tk.TclError:
            pass
        atexit.register(self.let_go)                  # any other way out: the lock is still removed, and logged
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
            title = f"Where should {APP_NAME} keep its files?"
            text = (f"{APP_NAME} keeps everything in one data folder: the combos and conflicts, the settings, the "
                    "schedule, its PDF and Excel files, and past semesters (and, if you use them, the sheets the "
                    "sign-up and conflict forms fill). The program itself can be installed again any time; the data "
                    "folder is what matters."
                    f"\n\n\u2022  Only this computer will use it: any folder on it works, e.g. "
                    f"Documents/{APP_NAME} data. Make a backup now and then (the Backup... button) and keep "
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
            picked = filedialog.askdirectory(title=f"The {APP_NAME} data folder",
                                             initialdir=str(gone.parent if gone and gone.parent.is_dir() else
                                                            default_parent()))
            use(Path(picked) if picked else None)

        def new():
            parent = filedialog.askdirectory(title=f"Where to make the new '{APP_NAME} data' folder",
                                             initialdir=str(default_parent()))
            if parent:
                from backup import new_folder
                folder = new_folder(parent, DEFAULT_NAME)
                try:
                    folder.mkdir()
                    start_folder(folder)
                except (OSError, ValueError) as e:
                    messagebox.showerror("Can't make the folder", f"Can't make {folder}:\n{e}")
                    return
                use(folder)
                messagebox.showinfo(
                    "Your new data folder", f"{folder}\n\nIt's ready, with example settings. Next:\n\n"
                    "1. Semester tab: the semester's name and dates, the show nights and venues. Save.\n"
                    "2. Combos tab: the combos. Enter them (right-click > New combo), or link the sheets the "
                    "sign-up and conflict forms fill (Linked sheets...).\n"
                    "3. Combos tab: Check combos, and fix what it lists.\n"
                    "4. Schedule tab: Make schedule.")

        def quit_():
            self.closed = True
            self.root.destroy()
        ttk.Button(row, text="Choose existing folder...", style="Accent.TButton", command=existing).pack(side="left")
        ttk.Button(row, text="Make a new folder...", command=new).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Restore from a backup...",
                   command=lambda: use((self.restore() or (None, None))[1])).pack(side="left",
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
                "Use this folder?", f"{folder}\n\nThis folder has other things in it and no Combo Manager files. The "
                "app's files would be added among them.\n\nUse it anyway? (Usually better: a folder of its "
                f"own, e.g. '{APP_NAME} data'.)", icon="warning", default="no"):
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
        where = ttk.Frame(shell)                      # row 2: the data folder (changing it, backups: Settings tab)
        where.pack(fill="x", pady=(4, 0))
        ttk.Button(where, text="Open folder", command=lambda: open_path(self.folder)).pack(side="right", padx=(6, 0))
        self.folder_label = ttk.Label(where, text=self.folder_text(), style="Sub.TLabel")
        self.folder_label.pack(side="left", fill="x", expand=True)

        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True, pady=(14, 0))
        from settings_panel import SettingsPanel
        from swap_panel import SwapPanel
        from combos_panel import CombosPanel
        from schedule_panel import SchedulePanel
        self.combos = CombosPanel(self.tabs, lambda: self.folder, lambda: self.palette, open_path,
                                  on_change=lambda: self.swaps and self.swaps.load(quiet=True),
                                  get_swaps=lambda: self.swaps,
                                  after_schedule_change=lambda message: self.run(
                                      ["--stats", "--export"], "Checking the rules and rebuilding the PDF and xlsx...",
                                      intro=message),
                                  on_check=lambda: self.run(["--check"], "Checking the combos...", target="combos"))
        self.tabs.add(self.combos.frame, text="Combos")
        self.results["combos"] = self.results_box(self.combos, "Check results: what to look at in the combos and "
                                                               "conflicts")
        self.swaps = SwapPanel(self.tabs, lambda: self.folder, self.after_swap, lambda: self.palette)
        self.schedule = SchedulePanel(self.tabs, self.swaps, self.goto_swaps,
                                      lambda done: self.run(["--stats", "--export"],
                                                            "Exporting Schedule.pdf and Schedule.xlsx...", on_done=done),
                                      self.open_file, lambda: self.palette, open_path, make=self.make_schedule,
                                      check=lambda: self.run(["--stats", "--full"], "Checking the schedule..."),
                                      goto_combo=self.goto_combo)
        self.tabs.add(self.schedule.frame, text="Schedule")
        self.results["schedule"] = self.results_box(self.schedule, "Results of the last Make schedule or Check")
        self.full_stats = tk.BooleanVar(value=bool(load_config().get("full_stats")))   # remembered on this computer
        self.results["schedule"].add_option("All stats", self.full_stats)
        self.full_stats.trace_add("write", lambda *_: (save_config(full_stats=self.full_stats.get()),
                                                       self.show_check()))
        self.last_check = None                        # the last Check schedule's output: All stats shows or hides
        self.tabs.add(self.swaps.frame, text="Swaps")
        self.settings = SettingsPanel(self.tabs, lambda: self.folder, lambda: self.palette, on_save=self.autoload,
                                      on_dirty=lambda dirty: self.mark_tabs())
        self.tabs.add(self.settings.frame, text="Semester")
        self.combos.on_pending = self.swaps.on_pending = self.mark_tabs
        self.mark_tabs()                              # (a new data folder has no settings yet: unsaved from the start)
        self.current_tab = None
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)
        self.tabs.add(self.computer_tab(), text="Settings")
        self.tabs.add(self.about_tab(), text="About")
        self.out = self.results["schedule"].text
        self.color_output()
        # off while a step runs in the background (each back to how it was after)
        self.buttons += [self.schedule.make_button, self.schedule.check_button, self.schedule.versions_button,
                         self.schedule.sent_box,
                         self.schedule.confirm_button, self.combos.check_button, self.combos.sync_button,
                         self.combos.confirm_button, self.swaps.save_button]
        self.buttons += self.schedule.file_buttons + self.combos.file_buttons     # the files are being rewritten
        self.schedule.is_busy = self.swaps.is_busy = lambda: self.busy
        self.status = ttk.Label(shell, text="Ready.", style="Hint.TLabel")
        self.status.pack(fill="x", pady=(8, 0))
        self.root.after(300, self.autoload)
        self.root.after(shared_folder.REFRESH * 1000, self.keep_folder)
        self.root.after(800, self.check_copies)

    # several computers on one data folder (shared_folder.py)
    def take_folder(self, folder):
        """Marks folder as open here. When another computer has it open: says so, and asks whether to open it
        anyway. False = don't."""
        other = shared_folder.holder(folder)
        if other and not messagebox.askyesno(
                "Data folder in use", f"This data folder is open in {APP_NAME} on "
                f"{shared_folder.describe(other)}.\n\nTwo computers changing it at the same time can lose changes: "
                "best close the app there first.\n\nOpen it here anyway?", icon="warning", default="no"):
            return False
        shared_folder.claim(folder)
        self.told_taken = False
        app_log.set_folder(folder)
        app_log.write(f"Opened the data folder {folder} (version {VERSION})" + (f" (taken over from {shared_folder.describe(other)})"
                                                             if other else ""))
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

    def results_box(self, panel, title):
        """A tab's fold-out results box, just above its bottom bar."""
        box = self.theme.ResultsBox(panel.frame, title)
        box.pack(fill="x", pady=(8, 0), before=panel.bottom)
        return box

    def mark_tabs(self):
        """A dot on each tab with unsaved changes: "Combos \u25cf" (combo edits), "Schedule \u25cf" and "Swaps \u25cf" (swaps,
        shown on both), "Semester \u25cf" (settings)."""
        if not all((self.combos, self.swaps, self.schedule, self.settings)):
            return
        swaps = bool(self.swaps.pending)
        for panel, name, dirty in ((self.combos, "Combos", bool(self.combos.pending)), (self.schedule, "Schedule", swaps),
                                   (self.swaps, "Swaps", swaps), (self.settings, "Semester", self.settings.dirty)):
            self.tabs.tab(panel.frame, text=f"{name} \u25cf" if dirty else name)

    def computer_tab(self):
        """The Settings tab: this computer's own (the look, which data folder) and backups. Saved right away; the
        semester's settings, shared by every computer, are the Semester tab."""
        tab = ttk.Frame(self.tabs, padding=(28, 24))
        ttk.Label(tab, text="Data folder", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(tab, text="Where everything is kept. Every computer that uses it picks the same folder.",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 8))
        self.folder_label2 = ttk.Label(tab, text=str(self.folder))
        self.folder_label2.pack(anchor="w")
        row = ttk.Frame(tab)
        row.pack(anchor="w", pady=(8, 0))
        ttk.Button(row, text="Change folder...", command=self.change_folder).pack(side="left")
        ttk.Button(row, text="Open folder", command=lambda: open_path(self.folder)).pack(side="left", padx=6)

        ttk.Label(tab, text="Backups", style="CardTitle.TLabel").pack(anchor="w", pady=(28, 0))
        ttk.Label(tab, text="The whole data folder as one zip: keep it somewhere else. Restore brings one back (what's "
                            "there now is saved first).", style="Hint.TLabel").pack(anchor="w", pady=(2, 8))
        row = ttk.Frame(tab)
        row.pack(anchor="w")
        ttk.Button(row, text="Backup...", command=self.make_backup).pack(side="left")
        ttk.Button(row, text="Restore...", command=self.restore_and_switch).pack(side="left", padx=6)

        ttk.Label(tab, text="Appearance", style="CardTitle.TLabel").pack(anchor="w", pady=(28, 0))
        ttk.Label(tab, text="Remembered on this computer.", style="Hint.TLabel").pack(anchor="w", pady=(2, 8))
        sizes = ttk.Frame(tab)
        sizes.pack(anchor="w")
        ttk.Label(sizes, text="Text size", width=12).pack(side="left")
        ttk.Button(sizes, text="A\u2212", width=3, command=lambda: self.text_size(-1)).pack(side="left")
        self.size_label = ttk.Label(sizes, text=f"{round(self.theme.SCALE * 100)}%", width=6, anchor="center")
        self.size_label.pack(side="left", padx=4)
        ttk.Button(sizes, text="A+", width=3, command=lambda: self.text_size(+1)).pack(side="left")
        ttk.Checkbutton(tab, text="Dark mode", variable=self.dark, command=self.toggle_theme).pack(anchor="w",
                                                                                                pady=(16, 0))
        return tab

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
        ttk.Label(tab, text=f"{APP_NAME} needs a few free add-ons for Python (" + ", ".join(missing) + "). "
                            "Installing them takes about a minute and needs an internet connection. This happens "
                            "only once on this computer, and the app opens by itself when it's done.",
                  wraplength=760, justify="left").pack(anchor="w", pady=(8, 16))
        row = ttk.Frame(tab)
        row.pack(anchor="w", pady=(0, 16))
        self.setup_button = ttk.Button(row, text="Install", style="Accent.TButton", command=self.install)
        self.setup_button.pack(side="left")
        self.skip_button = ttk.Button(row, text="Continue without them", command=self.skip_setup)
        if not missing_packages():                    # only the pop-up calendar is missing
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
            self.write("\nInstalled. Opening the app...\n")
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
        subprocess.Popen([sys.executable] if FROZEN else [sys.executable, str(HERE / "scheduler_app.py")])
        self.root.destroy()

    def skip_setup(self):
        """Without the optional packages: the full app, with typed dates and the plainer look."""
        self.tabs.destroy()
        self.status.destroy()
        self.build_main()

    def tab_changed(self, _=None):
        """Leaving the Semester tab with unsaved changes: save, undo, or stay."""
        now = self.tabs.select()
        left_settings = self.settings and self.current_tab == str(self.settings.frame) and now != self.current_tab
        self.current_tab = now
        if left_settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)

    def on_close(self, *_):
        if self.settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)
            return
        if self.combos and not self.combos.ask_to_save():
            self.tabs.select(self.combos.frame)
            return
        if self.swaps and self.swaps.pending and not messagebox.askyesno(
                "Unsaved changes", "The schedule has unsaved changes (Schedule and Swaps tabs). "
                "Close anyway and lose them?", icon="warning"):
            return
        self.let_go()
        self.root.destroy()

    def let_go(self):
        """Closing: the data folder's lock removed (so the next start doesn't think it's open elsewhere), logged. Once."""
        if getattr(self, "let_go_done", False):
            return
        self.let_go_done = True
        if self.folder and self.settings:
            shared_folder.release(self.folder)
            app_log.write("Closed the app")

    def autoload(self):
        """Loads the Combos and Swaps tabs from the data folder (at start, after a folder change, after a run). When
        the schedule's exports aren't there (an old Schedule.xlsx was just converted, or they were deleted), makes them
        (once per folder)."""
        for panel in (self.combos, self.swaps):
            if panel:
                panel.load(quiet=True)
        if (self.swaps and self.swaps.state and self.folder not in self.exported
                and not all(export_path(self.folder, n).exists() for n in (SCHEDULE_PDF, SCHEDULE_XLSX))):
            self.exported.add(self.folder)
            self.run(["--stats", "--export"], "Making Schedule.pdf and Schedule.xlsx...")

    def about_tab(self):
        tab = ttk.Frame(self.tabs, padding=(28, 28))
        title = ttk.Frame(tab)
        title.pack(anchor="w")
        ttk.Label(title, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(title, text=f"Version {VERSION}", style="Hint.TLabel").pack(side="left", padx=(12, 0), anchor="s",
                                                                           pady=(0, 4))
        ttk.Label(tab, text=f"Made by {AUTHOR}.", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(tab, text="Questions, ideas, or something not working the way it should? Get in touch, happy to "
                            "help:", wraplength=640, justify="left").pack(anchor="w", pady=(14, 4))
        row = ttk.Frame(tab)
        row.pack(anchor="w")
        email = ttk.Label(row, text=EMAIL, style="Link.TLabel", cursor="hand2")   # click: opens the mail app
        email.pack(side="left")
        email.bind("<Button-1>", lambda _: __import__("webbrowser").open(f"mailto:{EMAIL}?subject=Combo%20Manager%20{VERSION}"))

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
        row = ttk.Frame(tab)
        row.pack(anchor="w", pady=(24, 0))
        ttk.Label(row, text="Something not working? Send the log file with your email:").pack(side="left")
        ttk.Button(row, text="Open the log", command=self.open_log).pack(side="left", padx=(10, 0))
        ttk.Label(tab, text="Free to use, share and change.", style="Hint.TLabel").pack(anchor="w", pady=(24, 0))
        return tab

    def open_log(self):
        """Opens the folder with this computer's log file (AppFiles/Logs in the data folder)."""
        if not self.folder:
            messagebox.showinfo("The log", "No data folder chosen yet, so there's no log.")
            return
        log = app_log.path(self.folder)
        log.parent.mkdir(parents=True, exist_ok=True)
        open_path(log.parent)

    def tk_error(self, exc, value, tb):
        """An error in the window (a button that crashed): into the log, and said once, plainly."""
        app_log.error("in the window", value)
        where = f"\n\nThe details are in the log ({app_log.path(self.folder)}): please send that file to whoever " \
                "maintains the app (About tab)." if self.folder else ""
        messagebox.showerror("Something went wrong", f"{value}{where}")

    def folder_text(self, room=60):
        """The data folder, shortened in the middle when long: 'Data folder:  /home/.../Shared/Combos'."""
        return f"Data folder:  {shorten(str(self.folder), room)}"

    def color_output(self):
        p, mono, size = self.palette, self.theme.mono_font(), self.theme.size(10)
        boxes = [b.text for b in self.results.values()] or [self.out]
        for out in boxes:
            out.configure(font=(mono, size), background=p["panel"], foreground=p["text"], insertbackground=p["text"],
                          selectbackground=p["accent"], selectforeground=p["accent_text"])
            out.tag_configure("warn", foreground=p["warn"])
            out.tag_configure("bad", foreground=p["bad"], font=(mono, size, "bold"))
            out.tag_configure("good", foreground=p["good"], font=(mono, size, "bold"))

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
                    tag = ("bad" if ("\u2716" in line or "PROBLEM" in line or "Can't continue" in line
                                     or "went wrong" in line) else
                           "warn" if ("\u26a0" in line or "WARN" in line) else
                           "good" if ("All hard rules hold" in line or line.startswith(("Wrote", "Saved the schedule", "Made a schedule", "Nothing to look at"))) else None)
                    self.out.insert("end", line, tag)
                self.out.see("end")
                self.out.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    # actions
    def wait_for_step(self):
        """True (and says so) while a step runs in the background: it's writing into the data folder."""
        if self.busy:
            messagebox.showinfo("Still working", "Wait for the current step to finish (see the bottom of the "
                                "window), then try again.")
        return self.busy

    def change_folder(self):
        if self.wait_for_step():
            return
        if self.settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)
            return
        if self.combos and not self.combos.ask_to_save():
            self.tabs.select(self.combos.frame)
            return
        picked = filedialog.askdirectory(initialdir=str(self.folder), title=f"The {APP_NAME} data folder")
        if picked:
            self.switch_folder(Path(picked))

    def switch_folder(self, folder):
        """Makes folder the data folder from now on (after checking it), and loads everything from it."""
        if folder == self.folder or not self.accept_folder(folder):
            return
        shared_folder.release(self.folder)
        self.folder = folder
        self.folder_label.configure(text=self.folder_text())
        self.folder_label2.configure(text=str(self.folder))
        save_folder(self.folder)
        if self.combos:
            self.combos.show_links()
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
            app_log.write(f"Backup saved: {dest} ({n} files)")
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
        """The Restore window: pick a backup (what's in it is shown), then restore it into this data folder (the
        usual case: it's backed up first, the forms' spreadsheets are kept, every computer and flow keeps the same
        folder) or into a new folder (when the data folder is lost; the only choice before one is chosen).
        -> ("here", the safety backup) or ("new", the new folder), or None when cancelled."""
        from backup import BEFORE_RESTORE, BackupError, new_folder, read_backup, restore_backup, restore_in_place
        win = tk.Toplevel(self.root)
        win.title("Restore a backup")
        win.transient(self.root)
        box = ttk.Frame(win, padding=20)
        box.pack(fill="both", expand=True)
        wrap = 600
        ttk.Label(box, text="Restore a backup", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3,
                                                                             sticky="w")
        picked, dest_parent, result = {}, [Path(self.folder).parent if self.folder else default_parent()], []
        mode = tk.StringVar(value="here" if self.folder else "new")
        keep_inputs = tk.BooleanVar(value=True)
        ttk.Label(box, text="1. The backup", style="Step.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 0))
        name = ttk.Label(box, text="(none chosen yet)", style="Hint.TLabel")
        name.grid(row=2, column=0, columnspan=2, sticky="w")
        about = ttk.Label(box, text="", wraplength=wrap - 140, justify="left")
        about.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(box, text="2. Where to restore it", style="Step.TLabel").grid(row=4, column=0, sticky="w",
                                                                               pady=(16, 4))
        here = ttk.Frame(box)
        here.grid(row=5, column=0, columnspan=3, sticky="w")
        if self.folder:
            ttk.Radiobutton(here, text="Into this data folder (usually the right choice)", value="here",
                            variable=mode, command=lambda: update()).pack(anchor="w")
            ttk.Label(here, text="Everyone keeps using the same folder, and the forms keep writing to it. What's in "
                                 f"it now is saved first (AppFiles > {BEFORE_RESTORE}), so this can be undone by "
                                 "restoring that.", style="Hint.TLabel", wraplength=wrap, justify="left").pack(
                anchor="w", padx=(26, 0))
            keep = ttk.Checkbutton(here, text="Keep the current Approvals.xlsx and Conflicts.xlsx (recommended: "
                                              "the forms keep adding to them)",
                                   variable=keep_inputs)
            keep.pack(anchor="w", padx=(26, 0), pady=(4, 10))
            ttk.Radiobutton(here, text="Into a new folder", value="new", variable=mode,
                            command=lambda: update()).pack(anchor="w")
            ttk.Label(here, text="For when the data folder itself is lost or damaged. This computer switches to the "
                                 "new folder; other computers and the forms don't: each has to be pointed at it.",
                      style="Hint.TLabel", wraplength=wrap, justify="left").pack(anchor="w", padx=(26, 0))
        else:
            ttk.Label(here, text="Into a new folder (nothing is overwritten), which becomes the data folder.",
                      wraplength=wrap, justify="left").pack(anchor="w")
        where = ttk.Label(box, text="", style="Hint.TLabel", wraplength=wrap - 140, justify="left")
        where.grid(row=6, column=0, columnspan=2, sticky="w", padx=(26, 0), pady=(4, 0))
        change = ttk.Button(box, text="Change...", command=lambda: change_place())
        change.grid(row=6, column=2, sticky="ne", pady=(4, 0))

        def target():
            return new_folder(dest_parent[0], f"{DEFAULT_NAME}-restored-{datetime.now():%Y-%m-%d}")

        def update():
            new = mode.get() == "new"
            where.configure(text=f"The new folder: {target()}" if new else "")
            change.grid() if new else change.grid_remove()
            if self.folder:
                keep.configure(state="disabled" if new else "normal")
            go.configure(text="Restore and switch to it" if new else "Restore into this folder",
                         state="normal" if picked else "disabled")

        def choose():
            start = Path(load_config().get("backup_dir") or default_parent())
            path = filedialog.askopenfilename(parent=win, title="The backup to restore",
                                              initialdir=str(start if start.is_dir() else default_parent()),
                                              filetypes=[("Backup (zip)", "*.zip"), ("All files", "*.*")])
            if not path:
                return
            try:
                info = read_backup(path)
            except BackupError as e:
                messagebox.showerror("Restore", str(e), parent=win)
                return
            picked.update(path=path, info=info)
            made = info.get("made", "")
            when = datetime.fromisoformat(made).strftime("%a %b %d, %Y at %H:%M") if made else "at an unknown time"
            lines = [f"\u2022 Made {when}" + (f" on {info['computer']}" if info.get("computer") else ""),
                     f"\u2022 Semester: {info.get('semester') or 'no settings in it'}",
                     f"\u2022 Schedule: {info['schedule']}" if info.get("schedule") else "\u2022 No schedule yet",
                     f"\u2022 Past semesters: {', '.join(info['past'])}" if info.get("past") else "",
                     f"\u2022 {info['files']} files"]
            name.configure(text=Path(path).name)
            about.configure(text="\n".join(l for l in lines if l))
            update()

        def change_place():
            path = filedialog.askdirectory(parent=win, title="Where to put the restored data folder",
                                           initialdir=str(dest_parent[0]))
            if path:
                dest_parent[0] = Path(path)
                update()

        def restore():
            try:
                if mode.get() == "here":
                    other = shared_folder.holder(self.folder)
                    if other and not messagebox.askyesno(
                            "Restore", f"This data folder is also open on {shared_folder.describe(other)}. Restoring "
                            "changes it for them too, and anything they save meanwhile may be lost.\n\nRestore "
                            "anyway?", icon="warning", default="no", parent=win):
                        return
                    safety = restore_in_place(picked["path"], self.folder, keep_inputs.get())
                    app_log.write(f"Restored {picked['path']} into this folder (kept the input spreadsheets: "
                                  f"{keep_inputs.get()}); what was here is in {safety}")
                    result.append(("here", safety))
                else:
                    dest = target()
                    restore_backup(picked["path"], dest)
                    app_log.set_folder(dest)
                    app_log.write(f"Restored {picked['path']} into this new folder")
                    result.append(("new", dest))
            except (BackupError, OSError) as e:
                messagebox.showerror("Restore", f"Couldn't restore the backup:\n{e}", parent=win)
                return
            win.destroy()
        ttk.Button(box, text="Choose a backup...", command=choose).grid(row=2, column=2, sticky="e")
        bar = ttk.Frame(box)
        bar.grid(row=7, column=0, columnspan=3, sticky="e", pady=(20, 0))
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right")
        go = ttk.Button(bar, text="", style="Accent.TButton", command=restore)
        go.pack(side="right", padx=(0, 6))
        box.columnconfigure(1, weight=1)
        update()
        win.grab_set()
        self.root.wait_window(win)
        return result[0] if result else None

    def restore_and_switch(self):
        if self.wait_for_step():
            return
        if self.settings and not self.settings.ask_to_save():
            self.tabs.select(self.settings.frame)
            return
        if self.combos and not self.combos.ask_to_save():
            self.tabs.select(self.combos.frame)
            return
        if self.swaps and self.swaps.pending and not messagebox.askyesno(
                "Unsaved changes", "The schedule has unsaved changes (Schedule and Swaps tabs): restoring "
                "throws them away. Go on?", icon="warning"):
            return
        before = self.folder
        got = self.restore()
        if not got:
            return
        how, path = got
        if how == "new":
            self.switch_folder(path)
            if self.folder == path:
                messagebox.showinfo("Restored", f"Restored into:\n{path}\n\nThis computer uses it from now on. "
                                    f"The folder used before is unchanged:\n{before}\n(Change folder... goes back "
                                    "to it.) Other computers and the forms still use that one until pointed here.")
            return
        if self.swaps:
            self.swaps.pending = []
            self.swaps.refresh_pending()
        if self.combos:
            self.combos.show_links()
        if self.settings:
            self.settings.reload()
        self.autoload()
        self.check_copies()
        messagebox.showinfo("Restored", "The backup is now in this data folder. Other computers get it through "
                            f"the sync.\n\nWhat was in the folder before is saved in:\n{path}\n(To undo: "
                            "Restore... that file.)")

    def open_file(self, name):
        """Opens an export (in the data folder's Exports). Schedule.pdf / .xlsx that aren't there but can be made:
        made first."""
        path = export_path(self.folder, name)
        if path.exists():
            open_path(path)
        elif name in (SCHEDULE_PDF, SCHEDULE_XLSX) and self.swaps and self.swaps.state:
            self.run(["--stats", "--export"], f"Making {name}...",
                     on_done=lambda code: path.exists() and open_path(path))
        else:
            messagebox.showinfo("Not there yet", f"There is no {name} in the Exports folder yet.")

    def make_schedule(self):
        """Makes a brand-new schedule. Once one exists it says what would be lost, and it's off entirely while the
        schedule is locked (Schedule tab)."""
        from schedule_file import has_schedule, summary
        other = self.other_semester()
        if other is not None:                         # last semester's files: filed away, nothing is lost
            if not messagebox.askyesno(
                    "New semester", f"The schedule is {('for ' + other) if other else 'from another semester'}. "
                    f"Its files (schedule, PDFs, backups) will be moved into "
                    f"'Archive/{other or 'Old schedule'}' in the data folder, then a new schedule is made.\n\nGo ahead?"):
                return
        elif has_schedule(self.folder):
            info = summary(self.folder)
            if info.get("published"):
                messagebox.showinfo("Make a new schedule", "The schedule is locked, so a new one "
                                    "can't be made. Use swaps for changes (Swaps tab). To really start over, "
                                    "untick 'Lock schedule' on the Schedule tab first.")
                return
            made = info.get("made", "")
            when = f" (made {datetime.fromisoformat(made):%a %b %d at %H:%M})" if made else ""
            lost = ["\u2022 Every combo's shows are worked out again from scratch: most will move."]
            if info.get("changes"):
                lost.append(f"\u2022 {info['changes']} change(s) saved since it was made (swaps, give-aways, "
                            "withdrawn combos) won't be in the new one.")
            if info.get("typed"):
                lost.append(f"\u2022 {info['typed']} set(s) with text typed in (e.g. Jam session) will be empty.")
            if not messagebox.askyesno(
                    "Replace the schedule?", f"This replaces the current schedule{when}:\n\n" + "\n".join(lost)
                    + "\n\nA copy is kept in AppFiles > ScheduleBackups. Only do this before the schedule goes to "
                    "students; after that, use swaps.\n\nMake a new schedule?", icon="warning", default="no"):
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

    def goto_combo(self, cid):
        self.tabs.select(self.combos.frame)
        self.combos.show_combo(cid)

    def goto_swaps(self, cid, d, k, mode="swap"):
        self.tabs.select(self.swaps.frame)
        self.swaps.preselect(cid, d, k, mode)

    def after_swap(self, message, on_done=None):
        """After the Swaps tab saved: check and rebuild the exports in the background, staying on the Swaps tab."""
        self.run(["--stats", "--export"], "Checking the rules and rebuilding the PDF and xlsx...", intro=message,
                 on_done=on_done)

    def run(self, args, message, intro="", on_done=None, ticker=False, target="schedule"):
        """Runs a step (solve.py's main with these arguments) in the background, its output in a tab's results box
        (target: "combos" or "schedule"), opened. ticker: a 'still working' line every 10 seconds, so a long solve
        doesn't look frozen."""
        missing = missing_packages()
        if missing:
            messagebox.showwarning("Missing packages", f"Install these first: {', '.join(missing)}.")
            return
        if self.busy:
            return
        self.top_first = "-y" not in args             # a check: what matters is at the top (a make: follow along)
        checking = "--full" in args                   # Check schedule: shown once done, with or without All stats
        if target == "schedule":
            self.last_check = None
        box = self.results.get(target)
        if box:
            self.out = box.text
            box.clear()
            box.show(True)
        if intro:
            self.write(intro)

        def job():
            out = []
            code = run_solve(args, self.folder, (lambda t: out.append(t)) if checking else
                             (lambda t: (out.append(t), self.write(t))))
            if code != 0:
                out.append("\nThere are problems: see the red lines.\n")
                if not checking:
                    self.write(out[-1])
            if checking:
                self.queue.put(lambda: self.show_check("".join(out)))
            app_log.write(f"{message} (solve.py {' '.join(args)}): " + ("done" if code == 0 else f"exit code {code}")
                          + "\n" + (intro or "") + "".join(out))
            if on_done:
                self.queue.put(lambda: on_done(code))
        self.start(job, message)
        if ticker and self.busy:
            self.runs += 1
            self.root.after(10000, self.tick, self.runs, time.monotonic())

    def show_check(self, text=None):
        """The last Check schedule's output in the Schedule tab's results box: the sections between the solve.py
        ALL_STATS markers only while All stats is ticked (so the tick works without checking again)."""
        if text is not None:
            self.last_check = text
        box = self.results.get("schedule")
        if not self.last_check or not box or (self.busy and text is None):
            return
        start, end = "--- all stats ---", "--- end of all stats ---"
        shown, hide = [], False
        for line in self.last_check.splitlines(keepends=True):
            if line.strip() == start:
                hide = not self.full_stats.get()
            elif line.strip() == end:
                hide = False
            elif not hide:
                shown.append(line)
        box.clear()
        self.out = box.text
        self.write("".join(shown))
        self.queue.put(lambda: self.out.see("1.0"))

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
        self.button_states = {b: str(b.cget("state")) for b in self.buttons}
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
        if getattr(self, "top_first", False):
            self.queue.put(lambda: self.out.see("1.0"))   # after the last lines are drawn
        if self.combos:
            self.combos.show_links()
        self.autoload()                               # the schedule may have changed
        self.status.configure(text="Ready.")
        for b, state in getattr(self, "button_states", {}).items():
            b.configure(state=state)
        self.schedule.refresh_tools()                 # (the schedule may be new, or locked)
        self.swaps.refresh_pending()


def set_icon(root):
    """The app icon (app/assets/icon.png, from dev/make_icon.py) on this window and every pop-up: title bar,
    taskbar, and the Dock when run from source (the packaged apps carry it too)."""
    path = Path(getattr(sys, "_MEIPASS", HERE)) / "assets" / "icon.png"
    try:
        root.icon_image = tk.PhotoImage(file=str(path)).subsample(4)     # 256 px; kept, or Tk drops it
        root.iconphoto(True, root.icon_image)
    except (tk.TclError, OSError):
        pass                                          # no icon is no reason not to open


def bring_to_front(root):
    """Started from Terminal (Mac) or a file manager, the window can open behind it: raise it once."""
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()


def selftest(out):
    """Loads every part the app needs (its modules, the solver, the PDF and Excel writers, the look, the pop-up
    calendar) and writes what happened to the file `out`. -> 0 when everything works. For checking a build: a
    missing piece shows up here instead of on the director's computer."""
    lines, failed = [f"{APP_NAME} {VERSION}"], 0

    def step(what, fn):
        nonlocal failed
        try:
            fn()
            lines.append(f"ok    {what}")
        except Exception as e:                        # noqa: BLE001  (report everything)
            failed += 1
            lines.append(f"FAIL  {what}: {type(e).__name__}: {e}")
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    for mod in ("solve", "inputs", "settings_file", "schedule_file", "backup", "app_log", "clipboard", "theme",
                "settings_panel", "swap_panel", "combos_panel", "schedule_panel", "outputs.excel_schedule",
                "outputs.schedule_pdf", "outputs.combos_pdf", "outputs.combos_xlsx", "core.solver", "core.swaps"):
        step(f"import {mod}", lambda m=mod: importlib.import_module(m))

    def solver():
        from ortools.sat.python import cp_model
        m = cp_model.CpModel()
        x = m.new_int_var(0, 10, "x")
        m.add(x >= 3)
        m.minimize(x)
        s = cp_model.CpSolver()
        assert s.solve(m) == cp_model.OPTIMAL and s.value(x) == 3
    step("the solver (ortools)", solver)

    def pdf():
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(tmp / "t.pdf"))
        c.drawString(72, 720, APP_NAME)
        c.save()
    step("a PDF (reportlab)", pdf)

    def xlsx():
        from openpyxl import Workbook
        from shared_folder import save_workbook
        wb = Workbook()
        wb.active["A1"] = APP_NAME
        save_workbook(wb, tmp / "t.xlsx")
    step("an Excel file (openpyxl)", xlsx)

    def window():
        root = tk.Tk()
        import theme
        theme.apply(root, "dark")
        theme.apply(root, "light")
        from tkcalendar import Calendar
        Calendar(root, locale="en_US").pack()
        set_icon(root)
        if not getattr(root, "icon_image", None):
            raise RuntimeError("the app icon (assets/icon.png) is missing")
        root.update()
        root.destroy()
    step("the window, its look, the icon and the pop-up calendar (tkinter, tkcalendar)", window)
    lines.append("ALL OK" if not failed else f"{failed} FAILED")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0


def main():
    if sys.argv[1:2] == ["--selftest"]:
        sys.exit(selftest(sys.argv[2] if len(sys.argv) > 2 else "selftest.txt"))
    root = tk.Tk()
    app = App(root)
    if getattr(app, "closed", False):               # quit at the "pick the data folder" question
        return
    root.after(200, bring_to_front, root)
    root.mainloop()


if __name__ == "__main__":
    main()
