# TODO

Where the combo scheduler stands, and what's left. First real use: **Winter 2027**. (Tidied 2026-10-05.)

## Where it stands

The app does the whole semester: check the inputs, make the schedule, the Schedule / Combos / Swaps tabs, swaps
with backups, PDFs and contact lists, combo edits (members, liaison, first-year tag, withdraw), settings with
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
- [ ] **Ownership:** forms, flows and the two spreadsheets owned by a shared / role account or with co-owners, in
  shared OneDrive / SharePoint, so nothing stops when one person leaves. Write down who has access.

### 2. Winter 2027 settings (Settings tab)
- [ ] Semester name, first / last show day, skip dates (reading week, holidays; the defaults are placeholders).
- [ ] Show days: venues, weekdays, sets per night, minimums, set times (now Tue Upstairs 7 pm 45 + 15 min, Fri
  Clara 7 pm 30 + 15 min), "supervised nights preferred here".
- [ ] Once real sign-ups are in: tune "Ideal days between shows" with `python app/solve.py --compare-gaps 14 21 28 35`.
- [ ] Solver time: 90 (the new default; the current fake `settings.json` still says 30).

### 3. Hand-over: program local, data in OneDrive (decided 2026-10-05)
- **Synced (OneDrive), one shared folder e.g. `Combo Scheduler data`:** `Combo Approvals.xlsx` and `Conflicts.xlsx`
  (the flows write there), `settings.json`, `scheduler_data.json`, `Schedule.xlsx` + `Schedule backups/`, the PDFs
  and contact lists, and `Archive/` with past semesters.
- **Local (each computer):** the program (unzipped folder now, the packaged app later), `~/.combo-scheduler-python`
  (rebuilt if missing), `~/.combo_scheduler.json` (which data folder, text size, dark mode: per computer on purpose).
- [ ] First run with no data folder chosen and no `data/` next to the program: ask for the data folder (today an
  empty `data/` is quietly made next to the program).
- [ ] The zip (and the packaged app) ship without `data/`; the fake data becomes a separate demo folder.
- [ ] Quick Start + README: install the program locally, pick the OneDrive data folder, flows write into it.
- [ ] Point both flows at the shared data folder.
- [ ] Try it on the **director's** computer (Windows or Mac), including the Mac "Open Anyway" step.
- [ ] Walk the director through `Quick Start.pdf` once.

### 4. Safety (small, worth doing)
- [x] Backed up: private GitHub repo `elliottkobelansky/combo-scheduler` (2026-10-05; `data/` is never pushed).
- [ ] Pin package versions (`requirements.txt`, used by the Install button).
- [ ] Crash-safe saves (temp file + rename) for `scheduler_data.json`, `settings.json`, `Schedule.xlsx`.
- [ ] A log file in the data folder, for "send this to whoever maintains it".
- [ ] Warn about OneDrive conflict copies and two computers editing at once (a lock file).

---

## Later (optional)

- **A real app** (PyInstaller): `Combo Scheduler.app` / `.exe`, no Python install. Built on GitHub Actions (or
  the Mac app on a Mac); default data folder `~/Documents/Combo Scheduler`; ~150-250 MB; unsigned = "Open Anyway"
  once (signing needs an Apple Developer account).
- **Per-instrument limits** on combos per student (asked 2026-10-05): horn players in at most 1 combo, rhythm
  section (piano, guitar, bass, drums) in at most 2. A warning in Check, the Combos tab and Add member, set in the
  settings by group. Open questions: count all of a student's combos or only those on that instrument? Voice and
  Other: what limit?
- **Ready-to-send emails** after the schedule is final (per combo: its dates, the swap policy, contacts; per
  supervisor), as To / Cc / Subject / Body rows, from `Schedule.xlsx` so they follow swaps.
- **Swap history:** a Swaps sheet in `Schedule.xlsx` (date, combos, from -> to, reason) for "your show moved"
  emails; maybe a swap-request form shown as an inbox in the Swaps tab.
- **Supervisors:** which professor attends each supervised night, their availability, a names sheet.
- **Messy member entries** on the combo form: report text that isn't an email ("TBD", a name alone), unknown
  domain typos (close to `mail.mcgill.ca`), spaces / doubled `@`, member counts outside the form's range, and the
  same person under two addresses. Then decide whether the **Student email domain fixes** setting stays (proposal:
  drop it for a "same name on two domains" warning).
- **New combo...** in the Combos tab for late combos after the form closed; **overrule a conflict** in the app.
- **Warnings** when an approvals row changes after the combo was edited in the app, and when a Response Id comes
  back with completely different members (form responses reset mid-semester).
- **Apply night changes to an existing schedule** (add a night as open sets, cancel a night and name the combos
  that lose a show). Today such settings changes only affect the next schedule, and Save settings says so.
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
- **Schedule file:** `Schedule.xlsx` is hand-editable, records its semester, and decides the nights once it
  exists; a new semester files the old files into `Archive/<semester>`.
- **Project:** git + private GitHub repo, `app/` `data/` `dev/` layout, launchers that find a Python with tkinter, the Mac zip,
  realistic fake data (instruments, supervisors), `Quick Start.pdf`.

## Decisions (so they aren't re-opened)
- Volunteer mode: each combo gets the same number of shows; leftover sets stay open.
- The schedule is made once and not re-solved; students swap among themselves (Swaps tab).
- Edits made in the app live in `scheduler_data.json`; the approvals spreadsheet is never written to.
- Approving stays in Outlook (it closes the request and will send the decision email).
- A Python app for Winter 2027; maybe a web app afterwards.
