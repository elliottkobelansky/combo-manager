# Combo Manager

Keeps a semester's combos, assigns them to show nights (e.g. Tuesdays Upstairs, Fridays Clara), and handles swaps.
**For the director: `Quick Start.pdf`** (one page). This README is the full reference.

Combos and conflicts are entered in the app, or read from two spreadsheets that Microsoft Forms + Power Automate
fill (the combo sign-up form and the conflicts form).

## Getting the app

GitHub builds it on every push (`.github/workflows/build.yml`): tests, then a PyInstaller build
(`dev/build_exe.py`), then a self-check of the built app. Download from the repo's **Actions** tab > latest "Build
the apps" run > **Artifacts**: `Combo-Manager-windows`, `Combo-Manager-mac-arm64` (M1 and later) or
`Combo-Manager-mac-intel`. A tag like `v0.1.0` also attaches them to a GitHub **Release** (a lasting link).
No Python needed; a newer version just replaces the old one (the data lives elsewhere).

- **Windows:** unzip anywhere, double-click `Combo Manager.exe`; first time: **More info > Run anyway** (unsigned).
- **Mac:** unzip, drag to Applications, double-click; first time: **System Settings > Privacy & Security > Open
  Anyway** (not signed with an Apple Developer ID, $99/year). The zip is made with `ditto`; a plain zip breaks it.
- **Linux, from source (testing):** `./combo-manager.sh` (needs `python3-venv python3-tk`); it makes a private
  Python in `~/.combo-scheduler-python` and offers to install the packages (`requirements.txt`, pinned versions).

The version is `VERSION` in `app/scheduler_app.py` (About tab, the log, the self-check).

## The window

- **Combos:** every combo and its people (instrument, other combos, conflicts, email). **Sync** reads the linked
  sheets again; **Linked sheets...** picks which. **Check combos** lists what to look at. Right-click (or
  **Actions ▾**) a combo or a person for everything else. **Open PDF / Open Excel**: the combo list.
- **Schedule:** every night and its sets (PROF = supervised). **Make schedule**, **Check schedule**, **Earlier
  versions...**, **Lock schedule**, **Open PDF / Open Excel**. Right-click a night or a set for emails, swaps, text.
- **Swaps:** **Swap**, **Give away**, **Claim** (below).
- **Semester:** the semester's settings, shared by every computer; **Save** checks them first.
- **Settings:** this computer's own: the data folder, **Backup... / Restore...**, dark mode, text size.
- **About:** contact, version, **Open the log**.

**Unsaved changes** work the same everywhere: edits show in blue (and a dot on the tab) until **Confirm changes**;
**Undo last** and **Discard all** take them back. Combo edits are one list; swaps and text in sets are another,
shared by the Schedule and Swaps tabs. Closing the app with unsaved changes asks first.

## The data folder

Everything that matters is in one folder (default name `ComboManagerData`), chosen the first time the app opens. It
can be local or synced (OneDrive, SharePoint, Dropbox, a network drive); the app never needs a Microsoft login.

| | |
|---|---|
| `Approvals.xlsx`, `Conflicts.xlsx` | The inputs, filled by the forms' flows (or link files from elsewhere: Combos tab > Linked sheets...). |
| `Exports/` | What the app makes for people: `Schedule.pdf` / `.xlsx`, `Combos.pdf` / `.xlsx`. Safe to share on its own. |
| `Archive/<semester>/` | Past semesters' schedules and exports. |
| `AppFiles/` | The app's own: `semester.json` (settings), `scheduler_data.json` (combo numbers and edits), `schedule.json` (the schedule), `.bak` copies, `ScheduleBackups/`, `Logs/`, `in_use.json`. |

- **Read-only on purpose:** the app's files in `AppFiles/` and `Exports/` are read-only and the exports' sheets
  protected (no password), so nobody edits them by mistake; the app unlocks a file just to save it.
- **Several computers:** best one at a time, but guarded. `in_use.json` says who has it open (a second computer is
  warned); saves never overwrite what another computer saved meanwhile; sync apps' conflict copies are pointed out.
- **Backups:** **Backup...** zips the whole folder. **Restore...** puts one back into this folder (what's there is
  saved first to `AppFiles/BeforeRestore`, and the input spreadsheets are kept) or into a new folder (when the
  folder itself is lost).
- **Earlier versions...** (Schedule tab): a copy of the schedule is kept before every change; restore any of them
  (undoable the same way).
- **The log:** `AppFiles/Logs/<computer>.txt`: every step, save and error. When something goes wrong, send it.
- Per-computer choices (which folder, text size, dark mode) are in `~/.combo_scheduler.json`.

## A semester, step by step

**1. Settings (Semester tab).** Semester name, first and last show day, the show days (weekday, venue, sets, set
times, minimum shows there, "supervised nights preferred here"), skip dates (with a reason, shown on the calendar)
and rare extra dates. Set times: first set, length and break give every set's time (19:00, 45, 15 gives 7:00–7:45,
8:00–8:45, ...); blank shows set numbers instead. See [Settings explained](#settings-explained).

**2. Combos and conflicts (Combos tab).** Link the forms' sheets and **Sync**, or enter them by hand (right-click >
**New combo**; on a person, **Edit conflicts...**). Both can be mixed. **Check combos** before making the schedule.

- **`Approvals.xlsx`:** one row per combo submission, with the director's decision (Status: Pending / Accepted /
  Rejected / Withdrawn) and First year. Only **Accepted** rows whose Semester is exactly the semester name count;
  Pending ones are listed. Power Automate gives up on an approval after **30 days**: past that, type the decision
  into the row yourself (and tell the liaison, since no email goes out).
- **`Conflicts.xlsx`:** one row per conflict submission (Email, Date 1–4, Reason, Status). Status **Active**
  counts; **Overruled** doesn't. A student's newest submission replaces their earlier ones.

Combo numbers are given in submission order the first time a combo is read and **never change** (a withdrawn combo
leaves a gap). Edits made in the app (names, emails, instruments, members, liaison, first-year tag, withdrawals,
overruled conflicts) are kept in `scheduler_data.json`, never written into the spreadsheets, and applied every time
they're read.

**3. Make the schedule (Schedule tab).** **Make schedule** takes a minute and always gives the same result for the
same input. Then **Open PDF** (print it with `Combos.pdf`: the numbers match) and **Lock schedule** once it's final,
so a new one can't be made by accident. Once a schedule exists it decides the nights: changing dates or show days in
Settings only affects the next schedule.

**4. During the semester.**
- **Swaps tab:** pick a combo and a show. **Swap** lists every trade and move, best first: green fixes a problem,
  orange has a side effect (e.g. a student playing twice that night), red breaks a hard rule and is only for when
  it's agreed (it asks first, and Check schedule keeps flagging it). **Give away** hands a show to another combo or
  leaves it open; **Claim** lists the open sets a combo can take. **Copy swap summary** and **Copy liaison
  emails** give an email ready to send. Three-way swaps: do two in a row.
- **Schedule tab, right-click:** a night: copy its liaison emails, all emails, or a summary. An open set: **Fill
  set...** (every combo that could take it) or **Add text...** (e.g. *Jam session*: shown on the calendar, and the
  set counts as taken). A filled set: **Go to combo**, **Find swaps...**, **Give away set...**.
- **Combos tab, right-click:** add or remove members (removed people stay in grey: **Put back**), change the
  liaison, fix a name or email (the fix also applies to conflicts), set instruments (remembered for a person's
  later combos), mark first-year, **Withdraw combo...** (its sets open up; supervised nights must be refilled), and
  **New combo...** for one accepted after the form closed.
- **Check schedule** re-checks every rule after changes; conflicts that arrived late show up here.

Every confirmed change rebuilds the exports. `Schedule.xlsx` has a sheet per view: By night, All sets,
Supervision, **Changes** (every change since the schedule was made: for "my show moved?" questions) and Report.

**5. A new semester.** Change the semester name and **Save**: the app offers to move last semester's files into
`Archive/<semester>`. Combo numbers start again at Combo 01.

## What the solver does

Hard rules, never broken:
- A combo never plays a night one of its members marked as a conflict.
- Every combo gets at least its minimum shows at each venue, and `min_shows_per_combo` in total (at most
  `max_shows_per_combo`). In `open` mode exactly that many; leftover sets stay open for volunteers.
- Every combo plays at least `min_supervised_per_combo` supervised nights (a professor attends; usually 1). A
  supervised night is always full. At most `max_supervised_nights` of them, and as few as possible.

Goals, most important first (a lower one gives way to a higher one):
1. Give every combo its shows.
2. First-year combos don't play before `first_year_earliest_date`.
3. Equal numbers of shows.
4. A first-year combo's first show is on a supervised night.
5. Supervised nights on the show days marked "supervised nights preferred here".
6. As few supervised nights as possible.
7. Each combo plays at every venue it can.
8. Supervised nights earlier or later in the semester, if chosen.
9. Each combo's shows spread apart (see [Tuning](#tuning)).
10. No student playing twice in one night (if it happens, their two sets are back-to-back).
11. A combo that went late last time goes early this time.

If no schedule is possible, it says why in plain words (e.g. "Combo 10 has 0 usable Upstairs nights but needs 1").
The Report sheet lists any goal it had to give up.

## Settings explained

| Setting | Meaning |
|---|---|
| `semester_name` | The semester being scheduled (e.g. `Winter 2027`); titles the exports. Only spreadsheet rows with exactly this Semester are read. |
| `start_date`, `end_date` | Show nights are generated between these dates. |
| `min_days_between_shows` | Ideal gap between one combo's shows. **Tune this** (below). |
| `use_first_year`, `first_year_earliest_date` | First-year combos (First year = Yes in the approvals, or tagged in the app) don't play before this date. Off: every combo is treated the same. |
| `first_year_first_show_supervised` | A first-year combo's first show is on a supervised night (goal 4). |
| `extra_slot_policy` | `open` (recommended): each combo gets its shows, leftover sets stay open. `auto`: every set is filled, some combos get extra shows. |
| `min_shows_per_combo`, `max_shows_per_combo` | Shows per combo in total, at any venues (each venue's own minimum still applies). Max blank = no cap. |
| `min_supervised_per_combo` | Supervised nights per combo (usually 1; 0 = none at all). |
| `max_supervised_nights` | Total supervised nights in the semester, all professors together. Blank = no limit (still as few as possible). |
| `supervision_timing` | Supervised nights preferred `early`, `late`, or `none`. A light preference. |
| `max_blocked_dates_per_person`, `min_usable_nights_per_combo`, `min_members_per_combo` | Warnings only, in Check combos. |
| `solver_time_limit_sec` | How long the solver searches. 90 is plenty unless the Report says FEASIBLE instead of OPTIMAL. |
| `student_email_domain`, `professor_email_domain` | Used only to point out likely typos (a student on the professors' domain, ...). Blank = don't check. |

## Tuning

**`min_days_between_shows`** is the one to tune. Too low and shows end up closer than they need to be; too high and
the solver runs out of time (FEASIBLE instead of OPTIMAL) for no real gain. About a third of the semester is a good
start. With real data, compare a few values (nothing is written):

    python app/solve.py --compare-gaps 14 21 28 35

Pick the smallest value where *closest* stops improving and the solver still says OPTIMAL.

**`solver_time_limit_sec`:** FEASIBLE means the solver stopped before proving it found the best schedule. The
schedule is still valid; raise the limit (e.g. 180) to let it keep looking.

The goals' weights are the `W_...` constants in `app/core/solver.py`; you shouldn't need them.

## For developers

**Command line** (what the buttons run): `python app/solve.py` makes a new schedule (asks first; `-y` skips) and
`--export` also writes the exports; `--check` is Check combos; `--stats` is Check schedule (`--full` for every
stat; with `--export` it rebuilds the exports). `--folder PATH` for another data folder; `--approvals` /
`--conflicts PATH` for other input files.

**Tests:** `python dev/test_rules.py` after any change (fake scenarios, every hard rule checked independently; works
in a temporary folder). Demo data: `python dev/make_fake_forms.py FOLDER`, then **Change folder...** to it.

**Build:** `pip install -r requirements.txt pyinstaller`, then `python dev/build_exe.py` on the system it's for
(result in `dist/`). The icon is drawn by `dev/make_icon.py`; `Quick Start.pdf` is built from `QUICK_START.md` by
`dev/make_quick_start.py`.

| File | Job |
|---|---|
| `app/scheduler_app.py` | The window: tabs, data folder, backups, running steps; About and `VERSION`. |
| `app/combos_panel.py`, `schedule_panel.py`, `swap_panel.py`, `settings_panel.py` | The Combos, Schedule, Swaps and Semester tabs. |
| `app/solve.py` | Reads the inputs, runs the solver, saves the schedule and exports; the command line. |
| `app/inputs.py` | The only code that knows the spreadsheets' layout. Replace it to collect data another way: it just has to return the same `ScheduleInput` (`app/core/model.py`). |
| `app/core/` | The scheduling logic (solver, swaps, stats, rule check): plain Python, no files. |
| `app/outputs/` | The PDF and Excel exports. |
| `app/schedule_file.py` | `schedule.json`: load, save changes (backup first), earlier versions, archive. |
| `app/store.py` | `scheduler_data.json`: combo numbers and every edit made in the app. |
| `app/settings_file.py` | `semester.json`: defaults, checks, help texts. |
| `app/data_folder.py` | The data folder's layout: every path into it. |
| `app/shared_folder.py` | Safe writes, read-only files, the lock, changed-on-disk checks, conflict copies. |
| `app/backup.py`, `app/app_log.py`, `app/app_config.py` | Backups, the log, per-computer choices. |
| `app/theme.py`, `app/assets/` | The look (light and dark) and the icon. |

## License

MIT (`LICENSE`): free to use, copy, change and share; keep the copyright notice; no warranty. The packaged apps
also contain other packages under their own licences (MIT, BSD and Apache for most; tkcalendar, the pop-up date
picker, is GPL v3).
