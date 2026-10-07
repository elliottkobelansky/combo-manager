# TODO

(The app is called **Combo Manager** since 2026-10-07; the name may still change.)

Where the combo scheduler stands, and what's left. First real use: **Winter 2027**. (Tidied 2026-10-05.)

## Where it stands

The app does the whole semester: check the inputs, make the schedule, the Schedule / Combos / Swaps tabs, swaps
with backups, PDFs, combo edits (members, liaison, first-year tag, withdraw), settings with
plain-language checks, a new-semester hand-over. Tested on Linux (`dev/test_rules.py`, all passing) and launched
on a Mac. The director's one-page guide is `Quick Start.pdf`; `README.md` is the full reference.

---

## Before Winter 2027 (needed)

### 1. Microsoft 365 (forms and flows)
- [ ] **Decision email:** after the Accept / Reject click, the approval flow emails the liaison (Cc the members and
  the supervisor) with the director's comment. Write the wording first (accepted: what happens next and when the
  schedule comes out; rejected: why, who to contact). One step can pick the text with
  `if(startsWith(outputs('Decision'), 'Accept'), '...', '...')`.
- [ ] **Conflict flow:** new conflict-form response -> add a row to `Conflicts.xlsx`, table `Conflicts`
  (Response ID | Submitted | Semester | Email | Date 1-4 | Reason | Additional Info | Status | Notes), Status =
  `Active`. Email = the typed address, or the responder's if blank. The director sets `Overruled` to reject one.
- [ ] **First-year question** on the combo form, mapped to the First year column (the email's "Accept - first-year
  combo" button stays the main way).
- [ ] **Form texts:** finish both forms' instructions. Keep the words the app looks for in the table headers
  ("Response Id", "Semester", "Liaison", "Members", "Supervisor", "First year", "Status") and the conflict form's
  questions ("Semester", "Email", "Date"). Semester answer = a choice question (must match the settings exactly).
  Say: conflicts only if you have some; McGill students use `@mail.mcgill.ca`, others any address but the **same**
  one on both forms; the first member listed is the liaison.
- [ ] **Test** with a few submissions (including a Gmail member, and the conflict form from outside McGill: open
  it to anyone, or the director submits for them), run Check, then delete the test rows.
- [ ] **Document who can approve:** how to add (and remove) a person on the approval flow's approver list, so the
  director can hand approving over or share it without the flow's owner. Put it in the README / Quick Start.
- [ ] **Ownership:** forms, flows and the two spreadsheets owned by a shared / role account or with co-owners, in
  shared OneDrive / SharePoint, so nothing stops when one person leaves. Write down who has access.

### 2. Winter 2027 settings (Semester tab)
- [ ] Semester name, first / last show day, skip dates (reading week, holidays; the defaults are placeholders).
- [ ] Show days: venues, weekdays, sets per night, minimums, set times (now Tue Upstairs 7 pm 45 + 15 min, Fri
  Clara 7 pm 30 + 15 min), "supervised nights preferred here".
- [ ] Once real sign-ups are in: tune "Ideal days between shows" with `python app/solve.py --compare-gaps 14 21 28 35`.
- [ ] Solver time: 90 (the new default; the current fake `semester.json` still says 30).

### 3. Hand-over: program local, data in one data folder (decided 2026-10-05; any folder since 2026-10-06)
- **The data folder, e.g. `ComboManagerData`:** any folder; shared through OneDrive / SharePoint when several
  computers use it, but the app doesn't care (`app/data_folder.py`). At the top `Approvals.xlsx` and
  `Conflicts.xlsx` (the flows write there), `Schedule.xlsx` and the PDFs (exports), `Archive/` (past
  semesters); in `AppFiles/` the program's own files: `semester.json`, `scheduler_data.json`, `schedule.json`, `ScheduleBackups/`.
- **Local (each computer):** the packaged app (Windows `.exe` folder or Mac `.app`), `~/.combo-scheduler-python`
  (rebuilt if missing), `~/.combo_scheduler.json` (which data folder, text size, dark mode: per computer on purpose).
- [x] First run with no data folder chosen asks for it (choose / make a new one / restore a backup); the
  program folder holds no data (the old `data/` there is gone; demo data is made anywhere with `make_fake_forms.py`); a folder that has gone (sync not connected) is asked for again,
  never silently swapped. A folder that can't be written to, or has other things in it, is pointed out.
- [x] **Backup... / Restore...** (2026-10-06, `app/backup.py`): the whole data folder as one zip; restore goes into
  a new folder, never over the current one.
- [x] Quick Start + README describe it (program local, data folder anywhere, new computer = pick it again or
  restore a backup).
- [ ] Point both flows at the shared data folder.
- [ ] Try it on the **director's** computer (Windows or Mac), including the Mac "Open Anyway" step.
- [ ] Walk the director through `Quick Start.pdf` once.

### 4. Safety (small, worth doing)
- [x] Backed up: private GitHub repo `elliottkobelansky/combo-scheduler` (2026-10-05; no data in it).
- [x] Pin package versions (`requirements.txt`, used by the Install button and the build; 2026-10-06).
- [x] Crash-safe saves (temp file + rename) for `scheduler_data.json`, `semester.json` and swap saves of
  the schedule (2026-10-05); a brand-new schedule, `schedule.json` and backups too (2026-10-06). The PDFs (rebuilt
  any time) still save directly.
- [x] A log file (2026-10-06): `AppFiles/Logs/<computer>.txt`, About tab > Open the log; errors in the window are
  caught, logged and explained.
- [x] **Several computers on one shared data folder** (2026-10-05, `app/shared_folder.py`): lock file
  `AppFiles/in_use.json` (told who has it open, open anyway = take over, the other is told once; stale after 15
  min); saves refused when the file changed on disk since it was read (combo edits, settings: yours / theirs /
  cancel; pending swaps checked against the schedule as it is now); sync apps' conflict copies pointed out at
  start (OneDrive / SharePoint, Dropbox). Not done: a real read-only mode for the second computer (it's warned instead). Try it with two real
  computers on OneDrive.

### 5. The schedule in the app only (since 2026-10-06: `AppFiles/schedule.json`; `Schedule.xlsx` is an export)
- [ ] **Move supervised nights** without making the whole schedule again: mark a night supervised / not, with
  the rule check (every combo still on one, supervised nights full, the cap), like a swap. Was possible by hand in
  the old `Schedule.xlsx` (the Supervised column); not in the app yet.
- [ ] Maybe: change a published night's set times or venue in the app (also only possible in the old
  `Schedule.xlsx`). Rare.

### 6. Later from testing (2026-10-07)
- [ ] **Instrument restrictions** in Check combos (e.g. horn players in at most 1 combo, rhythm section in 2):
  see "Per-instrument limits" under Later.
- [ ] **The Windows crash log** emailed on 2026-10-06: go through it.
- [ ] **The name:** "Combo Manager" for now.
- [x] **App icon** (2026-10-07): a calendar page with an eighth note, drawn by `dev/make_icon.py` into
  `app/assets/` (`icon.png` for the window, `.ico` for Windows, `.icns` for the Mac); the builds use them.

### 7. Wording
- [ ] **Decide on the summary wording** for the night and swap summaries (Schedule tab "Copy night summary", Swaps
  tab "Copy swap summary"): what to call the person at a supervised night and what they do there: professor vs
  combo cop vs supervisor vs "supervised" vs feedback, etc. Today: the night summary says "(a professor attends)";
  the app elsewhere says "supervisor" (Combos tab, "Copy supervisor emails") and "prof" (Swaps tab show list). Then
  use the same words everywhere, the PDFs included.

---

## Later (optional)

- **A real app** (PyInstaller): the Windows `.exe` (since 2026-10-06) and the Mac `.app` (Apple Silicon and Intel,
  since 2026-10-07) are built on GitHub Actions; the source launchers (.bat, .command, make_zip.py) are gone, only
  `combo-manager.sh` stays for testing on Linux. The `.app` works on a real Mac (tested 2026-10-07). Unsigned = "Open Anyway" once;
  signing + notarizing needs an Apple Developer account ($99/year).
- **Per-instrument limits** on combos per student (asked 2026-10-05): horn players in at most 1 combo, rhythm
  section (piano, guitar, bass, drums) in at most 2. A warning in Check, the Combos tab and Add member, set in the
  settings by group. Open questions: count all of a student's combos or only those on that instrument? Voice and
  Other: what limit?
- **Ready-to-send emails** after the schedule is final (per combo: its dates, the swap policy, contacts; per
  supervisor), as To / Cc / Subject / Body rows, from the schedule so they follow swaps.
- **Swap requests:** a swap-request form shown as an inbox in the Swaps tab. (The swap history is done: the
  Changes sheet, 2026-10-06.)
- **Supervisors:** which professor attends each supervised night, their availability, a names sheet.
- **Messy member entries** on the combo form: report text that isn't an email ("TBD", a name alone), unknown
  domain typos (close to `mail.mcgill.ca`), spaces / doubled `@`, member counts outside the form's range, and the
  same person under two addresses. Then decide whether the **Student email domain fixes** setting stays (proposal:
  drop it for a "same name on two domains" warning).
- **Warnings** when an approvals row changes after the combo was edited in the app, and when a Response Id comes
  back with completely different members (form responses reset mid-semester).
- **Apply night changes to an existing schedule** (add a night as open sets, cancel a night and name the combos
  that lose a show). Today such settings changes only affect the next schedule, and Save says so.
- **Instruments:** venue rules (no drum kit at a venue), per-instrument counts in `Combos.pdf`.
- **Web app** (browser-only, HiGHS solver) after Winter 2027, if the HiGHS experiment keeps up with CP-SAT.

---

## Done (for reference)

- **Microsoft 365:** the approval flow (Accept / Accept - first-year combo / Reject in Outlook -> `Combo
  Approvals.xlsx`). Combo Info and its scripts retired; only the two spreadsheets remain.
- **Inputs** (`inputs.py`): read the two spreadsheets directly; combo numbers per semester never change
  (`scheduler_data.json`); Gmail and other non-McGill members kept (tested end to end 2026-10-05); spreadsheets
  can be picked from anywhere (Run tab); a half-synced file gives a "try again" message.
- **Solver:** every combo gets its shows; first-year date; equal counts; supervision (every combo on a supervised
  night, preferred day, fewest nights); one show at each venue a combo can make; spacing; student twice in a night
  last. Deterministic. Supervision and first-year can be switched off.
- **App:** Run (3 steps, progress lines), Schedule, Combos (Actions menu: members, liaison, first-year tag,
  withdraw / put back; pending combos in grey; members by instrument), Swaps (trades, moves, give-aways, claims;
  pending changes, one backup per save; searches in the background), Settings (sections, switches, unsaved-changes
  warning, year check), About. Setup screen on first run, text size, dark mode, horizontal scrollbars.
- **Schedule file:** the schedule is `AppFiles/schedule.json`, changed only in the app (2026-10-06; before, a
  hand-editable `Schedule.xlsx`, converted once). `Schedule.xlsx` / `.pdf` are exports, rebuilt after every change,
  never read back. It records its semester and decides the nights once it exists; a new semester files the old files
  into `Archive/<semester>`.
- **Project:** git + private GitHub repo, `app/` `dev/` layout (data in the chosen data folder), launchers that find a Python with tkinter, the Mac zip,
  realistic fake data (instruments, supervisors), `Quick Start.pdf`.

## Decisions (so they aren't re-opened)
- Volunteer mode: each combo gets the same number of shows; leftover sets stay open.
- The schedule is made once and not re-solved; students swap among themselves (Swaps tab).
- Edits made in the app live in `scheduler_data.json`; the approvals spreadsheet is never written to.
- Approving stays in Outlook (it closes the request and will send the decision email).
- A Python app for Winter 2027; maybe a web app afterwards.
