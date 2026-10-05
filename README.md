# Combo show scheduler

Assigns combos to show nights (e.g. Tuesdays Upstairs, Fridays Clara) using the two Microsoft Forms:
the combo sign-up form and the conflicts form. Microsoft 365 (Forms, Power Automate, Excel) collects and approves; Python on a laptop makes the schedule from two
downloaded files.

## The one-click app (for the director)

Double-click **`Make Schedule.bat`** (Windows), **`Make Schedule.command`** (Mac) or **`make-schedule.sh`**
(Linux). A window opens with three buttons that do everything below without typing commands (plus a **Swaps**
tab, see [swaps](#during-the-semester-swaps)):

1. **Check inputs** = `solve.py --check`
2. **Make schedule** = `solve.py --pdf` (asks before replacing an existing schedule)
3. **Check the schedule** = `solve.py --stats` (rule check and stats; the PDF is exported from the Schedule tab)

plus buttons to open the folder, `Schedule.pdf` and `Schedule.xlsx`, a **Settings** tab (below), and a dark
mode switch (remembered). It works on the **data
folder** shown at the top: by default the `data` folder next to the launchers; **Change...** picks another
(remembered). The easiest setup: keep this whole folder in OneDrive, synced to the director's computer, with
`Combo Approvals.xlsx`, `Conflicts.xlsx` and `settings.json` in `data`, so there's nothing to download.

**What's in the folder:**

| | |
|---|---|
| `Make Schedule.bat` / `.command` / `make-schedule.sh` | Double-click one of these to open the app. |
| `data/` | The spreadsheets, settings, schedule, PDFs and backups. Everything the director works with. |
| `app/` | The program. Nothing to open or change in here. |
| `dev/` | Tests and fake data, for whoever maintains the scheduler. |

**First run on a new computer:** Python 3 must be installed (python.org; on Windows tick "Add python.exe to
PATH"). The launcher then sets up a private Python environment in the user's home folder (once, outside OneDrive),
and the window offers **Install missing packages** (needs internet, about a minute). On a Mac, if double-clicking
is blocked, right-click the file > Open. On Linux you may need `sudo apt install python3-venv python3-tk`.

## Setup (once)

    pip install openpyxl ortools reportlab tkcalendar sv-ttk

`reportlab` is only needed for the PDFs; `tkcalendar` and `sv-ttk` (both optional) give the app its pop-up calendars and its modern look (light and
dark mode); without them it still works, with typed dates and a plainer look.

## Running it each semester

**1. Settings.** In the app's **Settings** tab (saved in `settings.json` in the data folder; the previous
version is kept as `settings.json.bak`):

| Tab | What to fill in |
|---|---|
| General | Semester name, first and last possible show day, and the rules (see [Settings explained](#settings-explained)). Dates have a pop-up calendar. |
| Show days | One row per weekly show day: weekday, venue, sets per night, minimum shows per combo there, set times (below), and **Supervised nights preferred here** (e.g. Tuesdays). |
| Skip dates | Dates with no show (reading week, holidays), with a reason. The reason appears on the calendar. |
| Extra dates | One-off shows on days that aren't a regular show day. Usually empty. Set times are optional: blank uses the venue's usual times. |

**Save settings** checks everything first and says what to fix. Without the app: `python app/settings_file.py --new`
writes a `data/settings.json` with example values (plain text, YYYY-MM-DD dates).

**Set times.** For each show day, **first set starts** (e.g. `19:00` or `7:00 PM`), **set length** and
**break** (minutes) give every set its start and end time: 19:00, 45, 15 gives 7:00–7:45, 8:00–8:45, 9:00–9:45, ...
The times appear on the calendar PDF and in `Schedule.xlsx` (Start and End columns). Leave all three blank to
show set numbers instead.

`semester_name` must match exactly what students choose in the form's Semester question (e.g. `Winter 2027`).
Responses for other semesters are ignored.

**2. Download the inputs.** Save both in the `data` folder. Or, on the app's Run tab, **Choose...** a file
anywhere and under any name (e.g. straight from a synced OneDrive or SharePoint folder); the choice is remembered on
that computer for that data folder, and **Use data folder** goes back to the usual file. From the command line:
`--approvals` and `--conflicts` take a path.
- **`Combo Approvals.xlsx`**: the approvals table the approval flow fills in, one row per combo submission, with
  the director's decision (Status: Pending / Accepted / Rejected / Withdrawn) and First year. Only **Accepted** combos
  of this semester (`semester_name` in the settings) are scheduled; rows still **Pending** are reported. In
  OneDrive: File > Save as > Download a copy (or use a synced folder).

  **Decide within 30 days.** Power Automate stops waiting for an approval after 30 days: the Accept / Reject
  buttons stop working and the row stays **Pending** for good. For a combo past that limit (or an approval sent
  to the wrong person, or a broken flow), type the decision into the row yourself: Status = `Accepted` or
  `Rejected`, First year = `Yes` / `No`, and fill in Decided by / Decided on / Notes. No reply email is sent
  then, so tell the liaison yourself.
- **`Conflicts.xlsx`**: the conflicts table the conflict flow fills in, one row per conflict-form submission
  (Response ID | Submitted | Semester | Email | Date 1-4 | Reason | Additional Info | Status | Notes). Every submission counts
  automatically: **Status = Active**. To overrule one, set its Status to **Overruled** (and say why in Notes); to
  drop a single date, clear that cell. A student's newest submission replaces their earlier ones (if the newest is
  Overruled, they have no conflicts). Download it like the other one (or use a synced folder).

The combo form's own responses aren't needed: the approvals workbook already has everything the scheduler uses.
**After this download, nothing else touches Microsoft:** the Python scripts read these two files as they are and
write only `Schedule.xlsx`, the PDFs and `scheduler_data.json`.

Combo numbers (Combo 01, 02, ...) are given in submission order the first time a combo is read, and **never
change**: they're kept in `scheduler_data.json` in the data folder (with corrected names and instruments), so keep
that file with the others. A combo withdrawn after the schedule is out just leaves a gap: set its Status to
Withdrawn and give its sets away or open them in the app (Schedule or Swaps tab). A new semester starts again at
Combo 01. Student names are guessed from emails; correct one in the app's Combos tab.

**3. Check.**

    python app/solve.py --check

Reads both downloads and **prints their warnings first**: combos still Pending, a combo accepted twice, combos
without a supervisor, conflict form problems. Then it validates everything else (e.g. a combo whose members'
conflicts leave few usable nights) without solving. Fix problems at the source (the approvals table or the conflict
responses), download again, and re-check. If no submission matches the settings' semester, it says so and lists the
semesters it found.

**4. Solve.**

    python app/solve.py --pdf

It asks you to confirm first, and warns if `Schedule.xlsx` / `Schedule.pdf` already exist and would be
overwritten (add `-y` to skip the question). It prints the same warnings as `--check`, including a **WARNING** for
any combo still Pending. Writes `Schedule.xlsx` and `Schedule.pdf` (printable calendar). Print `Schedule.pdf` with
`Combos.pdf` (made by the flow): the combo numbers on the calendar match the list.

`Schedule.xlsx` sheets:
- **Schedule**: every set of every night (with its start time, if set times are filled in). **This is the sheet
  you edit** (swaps, text in open sets); the PDF can be rebuilt from it (see swaps below).
- **Supervision**: the supervised nights (a professor needs to attend), with a column to fill in which professor
  comes.
- **Report**: warnings and stats from when the schedule was made. Read the WARN lines.

The old ByCombo and OpenSlots sheets are gone: they went out of date after the first edit. `python app/solve.py --stats`
reads the file as it is now (shows per combo, open sets nobody can take, and the rule check).

The **Schedule** sheet's last column, **Supervised**, says Yes on every set of a supervised night. To move
supervision to another night, change those Yes cells; `--stats` re-checks that every combo is still covered.

The same input always gives the same schedule.

**5. Stats.**

    python app/solve.py --stats

Reads the `Schedule.xlsx` on disk (no solving) and prints:
- **Overview:** sets filled and open, per venue.
- **Shows per combo** and **shows per student.**
- **Spacing:** the closest gaps between a combo's shows, and the closest pairs.
- **Running order:** who opens and closes nights, and anyone who opens or closes every one of their shows.
- **Students playing twice in one night.**
- **First-year combos playing before the first-year date.**
- **Open sets** that no combo could take.
- **Supervision:** the supervised nights, and combos on more than one.
- **Rule check:** every hard rule, re-checked from scratch, including every combo playing a supervised night.

## During the semester: swaps

Students arrange swaps between themselves. The easiest way to record one is the app's **Swaps** tab (it
loads the current schedule by itself): pick the combo and the show it can't make, and the app lists **every legal option, best first**:
trades with another combo's show (both play each other's slot), moves to an open set, and (last) reordering
within the same night. An option is only listed if it breaks no hard rule; soft side effects are shown in orange
(a student playing twice in a night, shows close together, a first-year combo before the first-year date), and
an option that fixes an existing problem is marked in green. Combos are shown with their liaison
("Combo 07 (Ana Ruiz)"), and a person whose name isn't unique is shown with their email. **Add to pending changes** collects it without touching any file: the tab then shows the
schedule as if it were done, so you can make several swaps in a row (each checked against the earlier ones), with
**Undo last** and **Discard all**. **Confirm changes** writes them all into `Schedule.xlsx` at once (a copy of
the old file goes to the `Schedule backups` folder) and rebuilds the PDF in the background; you stay on the Swaps
tab, and it says when the PDF is done. Closing the app or clicking Reload with unsaved changes asks first.
A swap that would take a combo off its only supervised night isn't offered, and three-way swaps aren't tried:
for those, edit by hand as below.

The Combos and Swaps tabs load the data folder's files by themselves (at start, after **Change folder...**, and after
each step or swap); **Reload** picks up files OneDrive synced while the app was open.

**Schedule tab:** every show night (PROF = supervised) with its sets, including swap changes not saved yet
(highlighted, with their nights opened), a search box and "only nights with open sets". While changes are
unsaved, a bar at the top offers **Confirm changes** (save them into `Schedule.xlsx` and export the PDF), **Undo
last** and **Discard all**. Double-click a combo's set to jump to the Swaps tab
with that show picked (right-click: also "Give it away"); double-click an open set to see **every combo that could
take it** and add one as a pending change. **Right-click a night** to copy, ready to paste into Outlook: the
students' emails (separated by `;`), the supervisors' emails (for Cc), or a short summary of the night (sets, times,
combos, members' names, then the emails). **Export contact lists** writes `Contact lists.xlsx`: one row per night
with its sets and everyone's emails, for printing or sharing. Both use the schedule as shown, including unsaved
changes. **Export PDF** rebuilds `Schedule.pdf` from `Schedule.xlsx` (the same
as Run's step 3); with unsaved changes it asks: save them first, export the saved schedule only, or cancel.
Nothing in this tab writes a file by itself.

**Combos tab:** every accepted combo (with its liaison and shows) and its people, in columns: Instrument, Also in
(other combos), Conflicts (dates submitted), Email; with a search box. **Click an Instrument cell** to pick one
(Saxophone, Trumpet, Trombone, Guitar, Piano, Bass, Drums, or Other: type anything); it's per person per combo and
kept in `scheduler_data.json`. **Export combo list PDF** writes `Combos.pdf` (every combo with its supervisor and
members, liaison first, instruments when set; numbered like the calendar). Double-click a person
(or **Change name...**) to correct their name, or double-click their email (or **Change email...**) to fix a typo'd
address: the spreadsheets aren't changed, the fix is applied whenever they're read, to the combos *and* the
conflicts, so a member whose conflicts didn't count because of a typo is matched again (corrected emails show ✎;
typing the original back removes the fix); it's kept in `scheduler_data.json` and used everywhere (PDFs, checks,
Swaps tab).

The Swaps tab has three modes, switched at the top:
- **Can't make it:** trade or move (above).
- **Give it away:** a combo hands one of its shows to another combo (which gains a show) or leaves it open.
  Only offered when the combo doesn't need that show (its minimum shows, a venue minimum, its supervised night).
- **Claim an open set:** a combo volunteers for an open set; the list shows every open set it can legally take
  (no show needs to be picked).

To record a swap by hand instead, edit the Combo column of the Schedule sheet in `Schedule.xlsx`, then run

    python app/solve.py --stats --pdf

It checks the edited file and **rebuilds `Schedule.pdf` from it** (no re-solving). What you can type in a set:
- **a combo name** (exactly, e.g. `Combo 05`): that combo plays;
- **`OPEN`** or nothing: open for volunteers;
- **anything else** (e.g. `Jam session`, `Guest: Trio X`): shown on the PDF as written, in italics, and the set
  counts as taken. A cell only fits about 10 characters next to the time, so longer text is cut there and printed
  in full under that month. `--stats` lists these entries; text that looks like a mistyped combo name
  (`Combo 5`) is flagged instead of printed.

The rule check catches a swap that puts a combo on a night one of its members marked as a conflict, a combo
playing twice in one night, a mistyped combo name, a combo left without its required show at a venue, a combo
left without a supervised night, and an open set on a supervised night.
Don't re-run `solve.py` without `--stats` after the schedule is published: it builds a fresh schedule and
overwrites your edits.

## What the solver does

Hard rules, never broken:
- A combo never plays a night that any of its members marked as a conflict.
- Every combo gets at least the minimum shows per combo at each venue (Settings > Show days).
- Every combo gets at least `min_shows_per_combo` shows in total, at any venues. Together with the venue minimums:
  with Upstairs 1 / Clara 0 and a total of 2, "Upstairs + Clara" and "Upstairs twice" are fine, "Clara twice" never
  happens. The solver still prefers an even split (goal 3), so "Upstairs twice" only happens when a combo can't
  make any Clara night; the Report lists those combos.
- No combo goes over `max_shows_per_combo`.
- In `open` mode, each combo gets exactly `min_shows_per_combo` shows (more is volunteering). Without that
  setting: at most `core_shows_per_venue` shows per venue.
- Every combo plays at least one **supervised night** (a night a professor attends), when
  `every_combo_supervised` is Yes. A supervised night is always **full**: no open sets. The solver picks those nights: at most `max_supervised_nights`, and within
  that as few as possible (it weighs this against spacing, so it may use one or two more than the minimum).
  It doesn't assign professors: the Supervision sheet lists the nights, with a column to fill in who's coming.

Goals, in order of importance (the solver gives up a lower goal to meet a higher one):
1. Give every combo its shows (in `open` mode: its core shows at each venue). Usually possible; it fails when a
   combo's members' conflicts cover every night at a venue, or a venue has fewer sets than there are combos.
2. First-year combos don't play before `first_year_earliest_date`. Only broken when it's the only way to give
   a first-year combo its show; the Report flags it.
3. Keep the number of shows equal between combos.
4. Supervised nights on a show day marked **Supervised nights preferred here** (Settings > Show days, e.g. Tuesdays), so
   professors come on the night that suits them. Other nights are used only when there's no other way.
5. Avoid a student playing twice in one night (two of their combos on the same night). If it happens, the Report
   says who and when, and the two sets are placed back-to-back in the running order.
6. Spread each combo's shows apart (see [Tuning](#tuning)).
7. Within a night, a combo that went late last time tends to go early this time.

If no schedule is possible, `solve.py` says why in plain language (e.g. "Combo 10 has 0 usable Upstairs
nights but needs 1").

## Settings explained

| Setting | Meaning |
|---|---|
| `semester_name` | Must match the form's Semester answer exactly. |
| `start_date`, `end_date` | Show nights are generated between these dates. |
| `min_days_between_shows` | Ideal gap between one combo's shows. **Tune this**, see below. |
| `use_first_year` | The **First-year combos** switch. On: combos marked First year = Yes in the approvals avoid playing before `first_year_earliest_date` (strong preference, see goals), and in fill-every-set mode get no extra shows. Off: every combo is treated the same, whatever the approvals say. Settings saved before this switch existed: on when there's a date. |
| `first_year_earliest_date` | The first day first-year combos can play. Required while the switch is on; kept but ignored while it's off. |
| `max_blocked_dates_per_person` | Warning only: flags students who blocked many show nights. |
| `min_usable_slots_per_combo` | Warning only: flags combos whose members' conflicts leave fewer usable nights than this. |
| `extra_slot_policy` | **Leftover sets** in the app. `open` = Leave open (recommended): each combo gets its shows; the sets left over stay open for volunteers, or you fill them by hand (Schedule or Swaps tab). `auto` = Fill every set: the solver fills every set, so some combos get extra shows. |
| `min_shows_per_combo` | Every combo gets at least this many shows in total, at any venues, as long as each venue's "Min per combo" is met. In `open` mode: exactly this many. Blank = no total minimum (then `core_shows_per_venue` applies). |
| `core_shows_per_venue` | **Shows per venue (if no minimum)** in the app, greyed out when it has no effect. Only used when `min_shows_per_combo` is blank: each combo then gets this many shows at every venue (`open`). In `auto` mode with first-year combos on, it's also the most a first-year combo plays at each venue. |
| `max_shows_per_combo` | Cap on total shows per combo. Blank = no cap. |
| `every_combo_supervised` | The **Supervised nights** switch. On: every combo plays at least one supervised night (a professor attends). Off: no supervised nights at all; `max_supervised_nights` and the show days' "Supervised nights preferred here" are ignored, and `Schedule.xlsx` has no Supervised column. Missing = On. |
| `max_supervised_nights` | **Maximum nights with a professor**: the total for the whole semester, all combos together (one supervised night covers every combo playing it). At most this many supervised nights. Blank = no limit (still as few as possible). Each night fits its number of sets, so 33 combos at 4 sets a night need at least 9. |
| `solver_time_limit_sec` | How long the solver searches (roughly seconds). 30 is plenty unless the Report says FEASIBLE instead of OPTIMAL. |
| `student_email_domain` | Students' email domain (`mail.mcgill.ca`). Members with other addresses are fine; they're just listed in the check, and a supervisor on this domain gets a "student address?" warning. Blank = don't check. |
| `email_domain_fixes` | Domain slips corrected when reading both spreadsheets, e.g. `mcgill.ca -> mail.mcgill.ca, gmial.com -> gmail.com`. Blank = none. Note: the McGill fix also rewrites real `@mcgill.ca` staff addresses if a staff member plays in a combo (supervisor addresses are never rewritten). |

## Tuning

### `min_days_between_shows` (the main one)

The solver tries to spread each combo's shows apart. Closer pairs cost more (3 days apart is penalised much
more than 14), and pairs at least `min_days_between_shows` apart cost nothing. Spacing never costs a combo a
show: filling sets and equal show counts always win.

- **Too low**: shows end up closer than they could be, because "good enough" is reached early.
- **Too high**: the solver gets slow and stops before finishing (FEASIBLE instead of OPTIMAL), for almost no
  extra spread.

The best value depends on the semester's length and the number of shows per combo. A good starting point is
about a third of the semester length. To find it for your real data:

    python app/solve.py --compare-gaps 14 21 28 35

This solves once per value, writes nothing, and prints:

    ideal gap | closest | median | < 14 days | sets filled | solver
         14 d |    17 d |   31 d |         0 |    66/76    | OPTIMAL
         21 d |    24 d |   32 d |         0 |    66/76    | OPTIMAL
         28 d |    31 d |   38 d |         0 |    66/76    | OPTIMAL
         35 d |    32 d |   39 d |         0 |    66/76    | FEASIBLE

- *closest*: the closest pair of shows any combo got.
- *median*: the typical gap.
- *< 14 days*: how many combos have shows less than two weeks apart.

**Pick the smallest value where *closest* stops improving and the solver still says OPTIMAL**
(28 above, Fall 2026 test data), then set it in the Settings tab and run `solve.py --pdf`.

### `solver_time_limit_sec`

If the Report or the console says `FEASIBLE` rather than `OPTIMAL`, the solver ran out of time before
proving it found the best schedule. The schedule is still valid. Raise the limit (e.g. 120) if you want it
to keep looking. `open` mode usually solves in a few seconds.

### Weights (advanced)

The relative importance of the goals is set by the `W_...` constants at the top of `core/solver.py`.
You shouldn't need to touch them. If you do, run `python dev/test_rules.py` afterwards.

## Testing without real data

Run these from the top folder. `app/solve.py` works on `data/` unless you add `--folder`.

    python dev/make_fake_forms.py    # fake Combo Approvals.xlsx and Conflicts.xlsx, in data/
    python dev/test_rules.py         # read -> solve on several fake scenarios, checks every hard rule


Run `python dev/test_rules.py` after any code change. `make_fake_forms.py` won't overwrite existing input files
unless you add `--force`; `test_rules.py` works in a temporary folder and never touches your files.

## Files

| File | Job |
|---|---|
| `app/inputs.py` | The ONLY file that knows what `Combo Approvals.xlsx` and `Conflicts.xlsx` look like (and the approval rules). Reads them into the solver's input; writes nothing. |
| `app/solve.py` | Reads `settings.json` + the two downloads, runs the solver, writes `Schedule.xlsx` (+ `Schedule.pdf`). |
| `app/scheduler_app.py` + `Make Schedule.bat` / `.command` / `make-schedule.sh` | The one-click window around `solve.py`, and its launchers. |
| `app/schedule_panel.py` | The app's Schedule tab (nights and sets, who could take an open set, Export PDF). |
| `app/store.py` | `scheduler_data.json`: combo numbers, corrected names and emails, instruments. |
| `app/outputs/combos_pdf.py` | Writes `Combos.pdf` (the Combos tab's Export button). |
| `app/combos_panel.py` | The app's Combos tab (all combos and people; correct a name). |
| `app/swap_panel.py`, `app/core/swaps.py` | The app's Swaps tab, and the swap finder behind it (pure, tested in `test_rules.py`). |
| `app/theme.py` | The app's look (Sun Valley theme, light and dark). The About tab (author and contact) is in `scheduler_app.py`. |
| `app/settings_file.py` | Reads, checks and saves `settings.json` (defaults and help texts live here). |
| `app/settings_panel.py` | The app's Settings tab. |
| `app/core/stats.py` | Stats and the rule check behind `solve.py --stats`. |
| `app/core/` | The scheduling logic. Plain Python objects only: no Excel, no Forms. `model.py` is the contract. |
| `app/outputs/excel_schedule.py` | Writes `Schedule.xlsx`. |
| `app/outputs/schedule_pdf.py` | Writes `Schedule.pdf`, numbered to match `Combos.pdf` (Combo 05 -> 05). |
| `dev/make_fake_forms.py`, `dev/test_rules.py` | Fake data and an independent rule checker. |

## Collecting data a different way later

Replace `inputs.py` with something that returns the same `ScheduleInput` (combos and each student's blocked
dates; see `core/model.py`). The solver doesn't change.
