"""scheduler_data.json in the data folder: what the scheduler keeps between runs.

    numbers      {semester: {response id: combo number}}   combo numbers never change once given out
    names        {email: name}                              corrected names (the Combos tab); others are guessed
    instruments  {semester: {"Combo 05|email": instrument}} per person per combo (the Combos tab)
    emails       {email as typed: corrected email}          fixes applied when reading both spreadsheets
    members      {semester: {response id: {"add": [email], "remove": [email], "liaison": email, "withdrawn": true,
                                           "first_year": "yes" or "no"}}}
                                                            members added or removed, the liaison changed and combos
                                                            withdrawn in the app (the Combos tab); the approvals are
                                                            never changed

Written by the app and by solve.py (when a new combo gets its number), in the data folder's App data
(data_folder.py), next to the other files.
"""
import json

from shared_folder import ChangedOnDisk, fingerprint, write_text
from data_folder import STORE_FILE as DATA_FILE, store_path


class Store:
    def __init__(self, folder):
        self.path = store_path(folder)
        self.read_as = fingerprint(self.path)        # to tell, when saving, that another computer saved meanwhile
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {}
        except ValueError:
            raise ValueError(f"{self.path} is damaged. Restore it from {DATA_FILE}.bak next to it, or from a backup.")
        for key in ("numbers", "names", "instruments", "emails", "members"):
            self.data.setdefault(key, {})
        self.changed = False

    def save(self):
        """Raises ChangedOnDisk (nothing saved) when the file changed since it was read: another computer saved it
        and the sync brought it in. Reading it again and redoing the change is then safe."""
        if fingerprint(self.path) != self.read_as:
            raise ChangedOnDisk(f"{DATA_FILE} was changed on another computer a moment ago. Nothing was saved: "
                                "please try again.")
        if self.path.exists():
            write_text(self.path.with_name(self.path.name + ".bak"), self.path.read_text(encoding="utf-8"))
        text = json.dumps(self.data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        write_text(self.path, text)
        self.read_as = fingerprint(self.path)
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

    # members added or removed in the app, per combo (by its response id, which never changes)
    def member_changes(self, semester, ref):
        """{"add": [...], "remove": [...], "liaison": email or "", "withdrawn": bool} for this combo (all empty when
        unchanged)."""
        ch = self.data["members"].get(semester, {}).get(str(ref), {})
        return {"add": list(ch.get("add", [])), "remove": list(ch.get("remove", [])), "liaison": ch.get("liaison", ""),
                "withdrawn": bool(ch.get("withdrawn")),
                "first_year": {"yes": True, "no": False}.get(ch.get("first_year"))}   # None: as the approvals say

    def _save_changes(self, semester, ref, ch):
        table = self.data["members"].setdefault(semester, {})
        if isinstance(ch.get("first_year"), bool):
            ch = {**ch, "first_year": "yes" if ch["first_year"] else "no"}
        kept = {k: v for k, v in ch.items() if v}
        if kept:
            table[str(ref)] = kept
        else:
            table.pop(str(ref), None)
        self.changed = True

    def set_first_year(self, semester, ref, value):
        """The first-year tag from now on: True, False, or None (back to what the approvals say)."""
        ch = self.member_changes(semester, ref)
        ch["first_year"] = value
        self._save_changes(semester, ref, ch)

    def set_withdrawn(self, semester, ref, withdrawn):
        """Withdraws the combo (True) or puts it back (False). Its number stays reserved either way."""
        ch = self.member_changes(semester, ref)
        ch["withdrawn"] = bool(withdrawn)
        self._save_changes(semester, ref, ch)

    def set_liaison(self, semester, ref, email):
        """The combo's liaison from now on ("" = back to the approvals' liaison)."""
        ch = self.member_changes(semester, ref)
        ch["liaison"] = email.lower()
        self._save_changes(semester, ref, ch)

    def add_member(self, semester, ref, email):
        """Adds email to the combo. Someone removed earlier is just put back."""
        email = email.lower()
        ch = self.member_changes(semester, ref)
        if email in ch["remove"]:
            ch["remove"].remove(email)
        elif email not in ch["add"]:
            ch["add"].append(email)
        self._save_changes(semester, ref, ch)

    def remove_member(self, semester, ref, email):
        """Takes email out of the combo. Someone added in the app is simply un-added."""
        email = email.lower()
        ch = self.member_changes(semester, ref)
        if email in ch["add"]:
            ch["add"].remove(email)
        elif email not in ch["remove"]:
            ch["remove"].append(email)
        if ch["liaison"] == email:
            ch["liaison"] = ""
        self._save_changes(semester, ref, ch)

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
        for table in self.data["members"].values():
            for ch in table.values():
                for kind in ("add", "remove"):
                    ch[kind] = [new if e == shown else e for e in ch.get(kind, [])]
                if ch.get("liaison") == shown:
                    ch["liaison"] = new
        self.changed = True
