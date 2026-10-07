# Combo Manager

Keeps a semester's combos, assigns them to show nights (e.g. Tuesdays Upstairs, Fridays Clara), and handles swaps.
**For the director: `Quick Start.pdf`** (one page). This README is the full reference.

Combos and conflicts are entered in the app, or read from two spreadsheets that Microsoft Forms + Power Automate
fill (the combo sign-up form and the conflicts form).

## Getting the app

GitHub builds it on every push: repo's **Actions** tab > latest "Build the apps" run > **Artifacts**
(`Combo-Manager-windows`, `-mac-arm64` for M1 and later, `-mac-intel`). A tag like `v0.1.0` also puts them on a
**Release** page. A newer version just replaces the old one: the data lives elsewhere.

- **Windows:** first time, **More info > Run anyway** (the app isn't signed).
- **Mac:** first time, **System Settings > Privacy & Security > Open Anyway** (signing costs $99/year).
- **Linux (testing):** `./combo-manager.sh`.

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

## A semester, step by step

**1. Settings (Semester tab).** The semester's name and dates, the weekly show days (venue, sets, set times),
and the days off. Each field is explained next to it.

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
so a new one can't be made by accident. Once a schedule exists it decides the nights: changing dates or show days on
the Semester tab only affects the next schedule.

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

Never broken:
- A combo never plays a night one of its members marked as a conflict.
- Every combo gets its minimum shows (in total and at each venue), and no more than the maximum. With **Leftover
  sets: Leave open**, exactly the minimum; the rest stay open for volunteers.
- Every combo plays its **supervised nights** (a professor attends; usually 1). A supervised night is always full.

Goals, most important first:
1. Every combo gets its shows.
2. First-year combos don't play before their date, and their first show is supervised.
3. Equal numbers of shows.
4. Supervised nights on the preferred show days, and as few of them as possible.
5. Each combo plays at every venue it can.
6. Each combo's shows spread apart (**Ideal days between shows**).
7. No student playing twice in one night.

If no schedule is possible, it says why in plain words (e.g. "Combo 10 has 0 usable Upstairs nights but needs 1").
The Report sheet lists any goal it had to give up. Every setting is explained next to it on the Semester tab.

## For developers

**Command line:** `python app/solve.py --help`. Useful once real sign-ups are in: `--compare-gaps 14 21 28 35`
tries several **Ideal days between shows** (writes nothing); pick the smallest where *closest* stops improving and
the solver still says OPTIMAL.

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
