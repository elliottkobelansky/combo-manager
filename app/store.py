"""scheduler_data.json in the data folder: what the scheduler keeps between runs.

    numbers      {semester: {response id: combo number}}   combo numbers never change once given out
    names        {email: name}                              corrected names (the Combos tab); others are guessed
    instruments  {semester: {"Combo 05|email": instrument}} per person per combo (the Combos tab)
    emails       {email as typed: corrected email}          fixes applied when reading both spreadsheets

Written by the app and by solve.py (when a new combo gets its number). Keep it with the other files (the synced
OneDrive folder is ideal).
"""
import json
from pathlib import Path

DATA_FILE = "scheduler_data.json"


class Store:
    def __init__(self, folder):
        self.path = Path(folder) / DATA_FILE
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {}
        except ValueError:
            raise ValueError(f"{self.path} is damaged. Restore it from a backup (it's in the data folder).")
        for key in ("numbers", "names", "instruments", "emails"):
            self.data.setdefault(key, {})
        self.changed = False

    def save(self):
        if self.path.exists():
            self.path.with_name(self.path.name + ".bak").write_text(self.path.read_text(encoding="utf-8"),
                                                                    encoding="utf-8")
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                             encoding="utf-8")
        self.changed = False

    # combo numbers
    def numbers(self, semester):
        return self.data["numbers"].setdefault(semester, {})

    def set_number(self, semester, ref, number):
        self.numbers(semester)[str(ref)] = number
        self.changed = True

    # names
    @property
    def names(self):
        return self.data["names"]

    def set_name(self, email, name):
        self.names[email.lower()] = name
        self.changed = True

    # instruments
    def instruments(self, semester):
        """{(combo name, email): instrument}"""
        return {tuple(k.split("|", 1)): v for k, v in self.data["instruments"].get(semester, {}).items()}

    def set_instrument(self, semester, combo, email, instrument):
        table = self.data["instruments"].setdefault(semester, {})
        key = f"{combo}|{email.lower()}"
        if instrument:
            table[key] = instrument
        else:
            table.pop(key, None)
        self.changed = True

    # email fixes
    @property
    def emails(self):
        return self.data["emails"]

    def fix_email(self, e):
        return self.emails.get(e, e)

    def set_email(self, shown, new):
        """Corrects the email now shown as `shown` to `new` (both already lowercase). Typing an original address back
        removes the fix. Corrected names and instruments move to the new address."""
        if shown == new:
            return
        originals = [k for k, v in self.emails.items() if v == shown] or [shown]
        for k in originals:
            if k == new:
                self.emails.pop(k, None)
            else:
                self.emails[k] = new
        if shown in self.names:
            self.names.setdefault(new, self.names.pop(shown))
        for table in self.data["instruments"].values():
            for key in [k for k in table if k.split("|", 1)[1] == shown]:
                table[key.split("|", 1)[0] + "|" + new] = table.pop(key)
        self.changed = True
