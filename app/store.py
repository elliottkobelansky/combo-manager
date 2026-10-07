"""scheduler_data.json in the data folder: what the scheduler keeps between runs.

    numbers      {semester: {response id: combo number}}   combo numbers never change once given out
    names        {email: name}                              corrected names (the Combos tab); others are guessed
    instruments  {semester: {"Combo 05|email": instrument}} per person per combo (the Combos tab); "" = set to
                                                            no instrument
    last_instrument {email: instrument}                     the instrument last set for someone: the default for
                                                            their other combos, this semester and later ones
    emails       {email as typed: corrected email}          fixes applied when reading both spreadsheets
    members      {semester: {response id: {"add": [email], "remove": [email], "liaison": email, "withdrawn": true,
                                           "first_year": "yes" or "no"}}}
                                                            members added or removed, the liaison changed and combos
                                                            withdrawn in the app (the Combos tab); the approvals are
                                                            never changed
    new_combos   {semester: {"app1": {"members": [email], "liaison": email, "supervisor": email, "first_year": bool}}}
                                                            combos made in the app (late, after the form closed);
                                                            numbered and edited like the others
    overruled    {semester: {email: ["2026-10-13", ...]}}   conflict dates overruled in the app: they don't count
    added_conflicts {semester: {email: ["2026-10-13", ...]}} conflicts added in the app (told to the director, not
                                                            sent through the form): they count like the form's
    linked       {"approvals": bool, "conflicts": bool}     which sheets are read (Combos tab > Linked sheets); a
                                                            folder from before has both (missing = linked)

Written by the app and by solve.py (when a new combo gets its number), in the data folder's AppFiles
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
        for key in ("numbers", "names", "instruments", "emails", "members", "new_combos", "overruled",
                    "added_conflicts", "last_instrument", "linked"):
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
    def instruments(self, semester, combos=()):
        """{(combo name, email): instrument}: the ones set for this semester; with combos, also each member's usual
        instrument where none was set (the one last set for them, in any combo or semester), so it's chosen once."""
        set_here = {tuple(k.split("|", 1)): v for k, v in self.data["instruments"].get(semester, {}).items()}
        out = {k: v for k, v in set_here.items() if v}
        usual = self.usual_instruments()
        for c in combos:
            for e in c.members:
                if (c.name, e) not in set_here and usual.get(e):
                    out[(c.name, e)] = usual[e]
        return out

    def usual_instruments(self):
        """{email: instrument}: the one last set for each person (older data: any one set for them)."""
        usual = {}
        for table in self.data["instruments"].values():
            for key, inst in table.items():
                if inst:
                    usual.setdefault(key.split("|", 1)[1], inst)
        usual.update(self.data["last_instrument"])
        return usual

    def set_instrument(self, semester, combo, email, instrument):
        """instrument "" = no instrument (kept, so the person's usual one isn't filled in instead)."""
        table = self.data["instruments"].setdefault(semester, {})
        table[f"{combo}|{email.lower()}"] = instrument or ""
        if instrument:
            self.data["last_instrument"][email.lower()] = instrument
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

    # the sheets the forms fill: optional
    def linked(self, which):
        """Is the 'approvals' / 'conflicts' sheet read? (Missing = yes: folders from before had both.)"""
        return bool(self.data["linked"].get(which, True))

    def set_linked(self, which, on):
        self.data["linked"][which] = bool(on)
        self.changed = True

    # combos made in the app (not in the approvals)
    def new_combos(self, semester):
        return self.data["new_combos"].get(semester, {})

    def add_combo(self, semester, members, liaison, supervisor="", first_year=False):
        """A combo the approvals don't have (e.g. accepted after the form closed). -> its ref ('app1', 'app2', ...),
        which keeps its number, member edits and withdrawal like a Forms response Id."""
        table = self.data["new_combos"].setdefault(semester, {})
        n = 1 + max((int(r[3:]) for r in table if r[3:].isdigit()), default=0)
        ref = f"app{n}"
        table[ref] = {"members": [e.lower() for e in members], "liaison": liaison.lower(),
                      "supervisor": supervisor.lower(), "first_year": bool(first_year)}
        self.changed = True
        return ref

    # conflicts overruled in the app
    def overruled(self, semester):
        """{email: {date}}: conflict dates that don't count."""
        from datetime import date
        return {e: {date.fromisoformat(d) for d in ds} for e, ds in self.data["overruled"].get(semester, {}).items()}

    def added_conflicts(self, semester):
        """{email: {date}}: conflicts added in the app."""
        from datetime import date
        return {e: {date.fromisoformat(d) for d in ds}
                for e, ds in self.data["added_conflicts"].get(semester, {}).items()}

    def set_added_conflict(self, semester, email, d, added=True):
        """Adds (or takes back) a conflict for email on date d, as if they'd sent it through the form."""
        self._set_date(self.data["added_conflicts"].setdefault(semester, {}), email, d, added)

    def set_overruled(self, semester, email, d, overruled=True):
        """Overrules (or counts again) email's conflict on date d."""
        self._set_date(self.data["overruled"].setdefault(semester, {}), email, d, overruled)

    def _set_date(self, table, email, d, on):
        ds = set(table.get(email.lower(), [])) | {d.isoformat()} if on else \
            set(table.get(email.lower(), [])) - {d.isoformat()}
        if ds:
            table[email.lower()] = sorted(ds)
        else:
            table.pop(email.lower(), None)
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
        if shown in self.data["last_instrument"]:
            self.data["last_instrument"].setdefault(new, self.data["last_instrument"].pop(shown))
        for table in self.data["members"].values():
            for ch in table.values():
                for kind in ("add", "remove"):
                    ch[kind] = [new if e == shown else e for e in ch.get(kind, [])]
                if ch.get("liaison") == shown:
                    ch["liaison"] = new
        for table in self.data["new_combos"].values():
            for spec in table.values():
                spec["members"] = [new if e == shown else e for e in spec.get("members", [])]
                for k in ("liaison", "supervisor"):
                    if spec.get(k) == shown:
                        spec[k] = new
        for table in list(self.data["overruled"].values()) + list(self.data["added_conflicts"].values()):
            if shown in table:
                table[new] = sorted(set(table.pop(shown)) | set(table.get(new, [])))
        self.changed = True
