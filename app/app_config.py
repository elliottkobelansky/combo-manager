"""The app's own settings on this computer (~/.combo_scheduler.json): the data folder, light/dark mode, and which
input spreadsheets to read. Kept per computer, not in settings.json, because the same synced folder has a different
path on each computer.

Standard library only: the app reads this before checking that the other packages are installed.
"""
import json
from pathlib import Path

from util import APPROVALS_FILE, CONFLICTS_FILE

CONFIG = Path.home() / ".combo_scheduler.json"
INPUTS = ("approvals", "conflicts")                 # which input files can be picked


def load_config():
    try:
        data = json.loads(CONFIG.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(**changes):
    try:
        CONFIG.write_text(json.dumps({**load_config(), **changes}))
    except OSError:
        pass                                          # only a convenience


def input_files(folder):
    """{"approvals": Path, "conflicts": Path} to read for this data folder: the file picked for it (the Run tab's
    Choose... buttons), or the usual name in the data folder."""
    picked = load_config().get("inputs", {}).get(str(folder), {})
    usual = {"approvals": APPROVALS_FILE, "conflicts": CONFLICTS_FILE}
    return {k: Path(picked[k]) if picked.get(k) else Path(folder) / usual[k] for k in INPUTS}


def is_picked(folder, which):
    return bool(load_config().get("inputs", {}).get(str(folder), {}).get(which))


def pick_input_file(folder, which, path):
    """Remembers `path` as this data folder's `which` file (None = back to the usual name in the data folder)."""
    inputs = load_config().get("inputs", {})
    mine = {k: v for k, v in inputs.get(str(folder), {}).items() if v}
    if path:
        mine[which] = str(path)
    else:
        mine.pop(which, None)
    save_config(inputs={**inputs, str(folder): mine})
