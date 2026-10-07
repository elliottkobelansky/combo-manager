"""Builds the packaged app with PyInstaller, with everything it needs (no Python install, no Setup screen), plus
the Quick Start, zipped to hand out. Build on the system it's for; GitHub Actions does both on every push
(.github/workflows/build.yml):

- Windows: dist/Combo Manager/ (Combo Manager.exe and its files) -> dist/Combo-Manager-windows.zip
- Mac: dist/Combo Manager.app -> dist/Combo-Manager-mac-arm64.zip (Apple Silicon) or -mac-intel.zip, a folder
  with the .app and the Quick Start. Not signed with an Apple Developer ID (only ad hoc), so the first time the Mac
  says it can't check it: System Settings > Privacy & Security > Open Anyway (once).

    pip install -r requirements.txt pyinstaller
    python dev/build_exe.py            # then check it:  "dist/Combo Manager/Combo Manager.exe" --selftest t.txt
                                       # on a Mac:  "dist/Combo Manager.app/Contents/MacOS/Combo Manager" --selftest t.txt

A folder, not a single .exe: it starts faster and antivirus programs flag it less.

On Windows the Microsoft C++ runtime (msvcp140.dll and co.) goes in too: the solver needs it, and a computer
without "Microsoft Visual C++ Redistributable" doesn't have it (Microsoft allows shipping it next to an app). Then
every DLL in the build is checked: each one it needs must be in the build or part of every Windows; anything else
fails the build, so a missing piece shows up here, not as "DLL load failed" on the director's computer.
"""
import os
import platform
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
NAME = "Combo Manager"
DIST, BUILD = ROOT / "dist", ROOT / "build"
ASSETS = ROOT / "app" / "assets"
# The Microsoft C++ runtime (app-local copies are allowed): PyInstaller leaves out what it finds in System32
MSVC_RUNTIME = ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll"]
# DLLs every Windows 10/11 has (plus api-ms-win-* / ext-ms-*, the Universal C runtime): no need to bring them
WINDOWS_DLLS = {n.lower() for n in """kernel32.dll kernelbase.dll ntdll.dll advapi32.dll user32.dll gdi32.dll
    gdi32full.dll shell32.dll shlwapi.dll ole32.dll oleaut32.dll comctl32.dll comdlg32.dll ws2_32.dll wsock32.dll
    crypt32.dll bcrypt.dll ncrypt.dll secur32.dll sspicli.dll rpcrt4.dll dbghelp.dll version.dll winmm.dll
    imm32.dll psapi.dll userenv.dll iphlpapi.dll netapi32.dll msimg32.dll uxtheme.dll dwmapi.dll setupapi.dll
    cfgmgr32.dll winspool.drv mpr.dll powrprof.dll propsys.dll dnsapi.dll ucrtbase.dll msvcrt.dll
    win32u.dll combase.dll shcore.dll wintrust.dll normaliz.dll""".split()}


def runtime_binaries():
    """--add-binary for the C++ runtime DLLs this Windows has (from System32), into the build's main folder."""
    if platform.system() != "Windows":
        return []
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    found = [system32 / n for n in MSVC_RUNTIME if (system32 / n).exists()]
    missing = sorted(set(MSVC_RUNTIME[:2] + MSVC_RUNTIME[3:]) - {p.name.lower() for p in found})
    if missing:
        raise SystemExit(f"Can't find {', '.join(missing)} in {system32}: install the Microsoft Visual C++ "
                         "Redistributable (x64) on this computer, then build again.")
    return [a for p in found for a in ("--add-binary", f"{p}{os.pathsep}.")]


def missing_dlls(folder):
    """{dll: [files needing it]} for DLLs that files in the build need but that are neither in it nor part of
    every Windows. (Windows only: reads each .dll / .pyd's import table.)"""
    import pefile                                      # comes with PyInstaller on Windows
    files = [p for p in folder.rglob("*") if p.suffix.lower() in (".dll", ".pyd")]
    present = {p.name.lower() for p in files}
    missing = {}
    for p in files:
        pe = pefile.PE(str(p), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
            dll = entry.dll.decode(errors="replace").lower()
            if dll not in present and dll not in WINDOWS_DLLS and not dll.startswith(("api-ms-win-", "ext-ms-")):
                missing.setdefault(dll, []).append(str(p.relative_to(folder)))
        pe.close()
    return missing


def main():
    PyInstaller.__main__.run([
        str(ROOT / "app" / "scheduler_app.py"),
        "--name", NAME, "--noconfirm", "--clean",
        "--windowed",                                  # no console window behind the app
        "--paths", str(ROOT / "app"),                  # the app's own modules
        "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
        "--collect-all", "ortools",                    # the solver: native libraries PyInstaller doesn't see
        "--collect-data", "tkcalendar",
        "--collect-data", "babel",                     # the pop-up calendar's date formats
        "--hidden-import", "babel.numbers",
        "--collect-data", "reportlab",                 # PDF fonts
        "--exclude-module", "matplotlib", "--exclude-module", "IPython", "--exclude-module", "pytest",
        "--icon", str(ASSETS / ("icon.icns" if platform.system() == "Darwin" else "icon.ico")),   # dev/make_icon.py
        "--add-data", f"{ASSETS}{os.pathsep}assets",   # icon.png: the window's own icon
    ] + runtime_binaries() + (["--osx-bundle-identifier", "app.combomanager"] if platform.system() == "Darwin"
                              else []))
    if platform.system() == "Darwin":
        return package_mac()
    folder = DIST / NAME
    if platform.system() == "Windows":
        missing = missing_dlls(folder)
        if missing:
            for dll, needed_by in sorted(missing.items()):
                print(f"MISSING {dll}, needed by {', '.join(needed_by[:3])}" + (" ..." if len(needed_by) > 3 else ""))
            raise SystemExit(f"{len(missing)} DLL(s) missing from the build (above): it would fail on a computer "
                             "that doesn't have them.")
        print("Every DLL in the build has what it needs.")
    shutil.copy2(ROOT / "Quick Start.pdf", folder / "Quick Start.pdf")
    system = {"Windows": "windows", "Darwin": "mac"}.get(platform.system(), platform.system().lower())
    zip_path = shutil.make_archive(str(DIST / f"Combo-Manager-{system}"), "zip", DIST, NAME)
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) // 2**20
    print(f"\nBuilt {folder} ({size} MB) and {zip_path}.")


def package_mac():
    """dist/Combo-Manager-mac-<arch>.zip: a 'Combo Manager' folder with the .app and the Quick Start. Zipped with
    ditto, which keeps what's inside the .app as it is (symlinks, the signature); a plain zip breaks it."""
    import subprocess
    app = DIST / f"{NAME}.app"
    stage = DIST / "mac" / NAME
    shutil.rmtree(stage.parent, ignore_errors=True)
    stage.mkdir(parents=True)
    subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
    shutil.copy2(ROOT / "Quick Start.pdf", stage / "Quick Start.pdf")
    arch = "arm64" if platform.machine() == "arm64" else "intel"
    zip_path = DIST / f"Combo-Manager-mac-{arch}.zip"
    zip_path.unlink(missing_ok=True)
    subprocess.run(["ditto", "-c", "-k", "--keepParent", str(stage), str(zip_path)], check=True)
    size = sum(p.stat().st_size for p in app.rglob("*") if p.is_file() and not p.is_symlink()) // 2**20
    print(f"\nBuilt {app} ({size} MB) and {zip_path}.")


if __name__ == "__main__":
    sys.exit(main())
