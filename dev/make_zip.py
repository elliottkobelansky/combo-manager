"""Builds a zip of the program to hand out: the files in git (the launchers, app/, dev/, the guides), in a
'Combo Manager' folder, run permissions kept. No data: the program lives on each computer and the data folder wherever
the director chooses (the app asks for it on first run).

    python dev/make_zip.py [--demo] [--mac] [--out PATH]

--demo  adds a 'Demo data' folder, made fresh by make_fake_forms.py (example settings, fake forms), to try the app
        with: choose it as the data folder
--mac   leaves out the Windows launcher (.bat): Gmail refuses zips that contain one
--out   where to write it (default: next to the project folder, combo-manager.zip)
"""
import argparse
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def add(zf, path, name):
    info = zipfile.ZipInfo.from_file(path, name)
    info.compress_type = zipfile.ZIP_DEFLATED
    if path.is_dir():
        zf.writestr(info, b"")
    else:
        zf.writestr(info, path.read_bytes())          # from_file keeps the permissions (the launchers' run bit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--mac", action="store_true")
    ap.add_argument("--out", default=str(ROOT.parent / "combo-manager.zip"))
    a = ap.parse_args()
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    files = [f for f in files if f and not (a.mac and f.endswith(".bat")) and not f.startswith(".github/")]
    out = Path(a.out)
    with zipfile.ZipFile(out, "w") as zf:
        for f in files:
            add(zf, ROOT / f, f"Combo Manager/{f}")
        if a.demo:
            from make_fake_forms import make_demo         # dev/, next to this file
            with tempfile.TemporaryDirectory() as tmp:
                make_demo(tmp)
                for p in sorted(Path(tmp).rglob("*")):
                    rel = p.relative_to(tmp)
                    add(zf, p, f"Demo data/{rel.as_posix()}" + ("/" if p.is_dir() else ""))
    with zipfile.ZipFile(out) as zf:
        bad = zf.testzip()
        n = len(zf.namelist())
    if bad:
        raise SystemExit(f"{out}: {bad} is damaged.")
    print(f"Wrote {out} ({n} entries, {out.stat().st_size // 1024} KB)"
          + (", with Demo data" if a.demo else "") + (", without the .bat" if a.mac else "") + ".")


if __name__ == "__main__":
    main()
