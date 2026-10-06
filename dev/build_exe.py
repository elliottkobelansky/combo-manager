"""Builds the packaged app with PyInstaller: dist/Combo Scheduler/, a folder with the program (Combo Scheduler.exe
on Windows) and everything it needs, so no Python install and no Setup screen. Plus the Quick Start, and a zip of the
folder to hand out. Build on the system it's for (Windows for the .exe); GitHub Actions does it on every push
(.github/workflows/build.yml).

    pip install -r requirements.txt pyinstaller
    python dev/build_exe.py            # then check it:  "dist/Combo Scheduler/Combo Scheduler.exe" --selftest t.txt

A folder, not a single .exe: it starts faster and antivirus programs flag it less.
"""
import platform
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
NAME = "Combo Scheduler"
DIST, BUILD = ROOT / "dist", ROOT / "build"


def main():
    PyInstaller.__main__.run([
        str(ROOT / "app" / "scheduler_app.py"),
        "--name", NAME, "--noconfirm", "--clean",
        "--windowed",                                  # no console window behind the app
        "--paths", str(ROOT / "app"),                  # the app's own modules
        "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
        "--collect-all", "ortools",                    # the solver: native libraries PyInstaller doesn't see
        "--collect-data", "sv_ttk",                    # the look (theme files)
        "--collect-data", "tkcalendar",
        "--collect-data", "babel",                     # the pop-up calendar's date formats
        "--hidden-import", "babel.numbers",
        "--collect-data", "reportlab",                 # PDF fonts
        "--exclude-module", "matplotlib", "--exclude-module", "IPython", "--exclude-module", "pytest",
    ])
    folder = DIST / NAME
    shutil.copy2(ROOT / "Quick Start.pdf", folder / "Quick Start.pdf")
    system = {"Windows": "windows", "Darwin": "mac"}.get(platform.system(), platform.system().lower())
    zip_path = shutil.make_archive(str(DIST / f"Combo-Scheduler-{system}"), "zip", DIST, NAME)
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) // 2**20
    print(f"\nBuilt {folder} ({size} MB) and {zip_path}.")


if __name__ == "__main__":
    sys.exit(main())
