# Combo Manager

**New here? Start with `Quick Start.pdf`** (one page, for the director; its text is `QUICK_START.md`, rebuilt
with `python dev/make_quick_start.py`). This README is the full reference.

Keeps a semester's combos and assigns them to show nights (e.g. Tuesdays Upstairs, Fridays Clara), then handles
swaps. Combos and conflicts are entered in the app, or come from two Microsoft Forms (the combo sign-up form and the
conflicts form) through sheets that Power Automate fills, linked in the app.

## The app (for the director)

**`Combo Manager.exe`** (Windows) or **`Combo Manager.app`** (Mac): the packaged apps, below. From source (Linux,
for testing): **`./combo-manager.sh`**. The window's tabs:

- **Combos** (opens first): every combo and its people. **Linked sheets...** chooses whether the forms' sheets
  are read (and which files); **Sync** reads them again. **Check combos** lists what to look at in the combos and
  conflicts, in a fold-out box under the list. Edits wait until **Confirm changes**. **Open PDF / Open Excel**: the
  combo list.
- **Schedule**: every show night and its sets. **Make schedule** (once per semester), **Check schedule** (the
  rule check first, then a few stats at a glance; tick **All stats** on the results box for every section), **Lock schedule** (tick it once the schedule is sent to students: no new schedule can be made while it's ticked), **Open
  PDF / Open Excel**; results in a fold-out box.
- **Swaps**: **Swap**, **Give away**, **Claim** (see [swaps](#during-the-semester-swaps)).
- **Settings**, **Appearance** (dark mode, text size 85% to 175%, remembered on that computer), **About** (contact,
  **Open the log**).

Under the hood each step is `app/solve.py`: Check combos = `--check`, Make schedule = `--export`, Check schedule =
`--stats` (and after changes `--stats --export`). Lists that are wider than the window get a horizontal scrollbar.
It works on the **data
folder** shown at the top; **Change folder...** picks another (remembered on that computer), **Backup...** and
**Restore...** are below.

**Where things live:** the **program** is installed on each computer (this folder, unzipped locally; it has no
data in it, and can be thrown away and reinstalled). The **data folder** (e.g. `Combo Manager data`) has
everything that matters. It can be any folder: one on this computer, or one kept in sync by OneDrive, SharePoint,
Dropbox or a network drive when several computers use the app; the app treats them all the same and never
needs a Microsoft login. At the top, what people open: `Approvals.xlsx` and `Conflicts.xlsx` (point both
flows at it, or pick them under any name, anywhere: Combos tab > Linked sheets...; a folder with the older name
`Combo Approvals.xlsx` still works), `Schedule.xlsx` and the PDFs (exports to read and print), `Contact
lists.xlsx`, and `Archive/` with past semesters. In **`App data/`**, what the program manages: `settings.json`,
`scheduler_data.json` (each with a `.bak` copy), `schedule.json` (the schedule itself) and `Schedule backups/` (a data folder from before is moved into this layout the first time it's
opened). The layout, and every path into it, is in `app/data_folder.py`. On first run the app asks where the data
folder is (choose one, make a new one, or restore a backup); a folder that can't be found later is asked for
again, never silently swapped. Per-computer preferences (the folder, text size, dark mode, input files picked
elsewhere, where backups go) are in `~/.combo_scheduler.json`.

**Backups** (`app/backup.py`): **Backup...** zips the whole data folder (spreadsheets, `App data` with the `.bak`
copies and schedule backups, `Archive`; an input file picked from elsewhere goes in under its usual name) into
`Combo Manager backup 2026-10-06 1405.zip`, wherever you choose: keep it off this computer when the data folder
is local. **Restore...** opens a window that shows what's in a backup (when and where it was made, its semester,
schedule and past semesters) and where it goes:
- **Into this data folder** (the usual case: go back to an earlier state): every computer and the forms keep using
  the same folder. What's in it is first saved to `App data/Before restore` (restoring that undoes it), and the
  current `Approvals.xlsx` / `Conflicts.xlsx` are kept by default (the forms keep adding to them). Another computer
  with the folder open is pointed out first.
- **Into a new folder** (the data folder itself is lost; the only choice on the first-run screen): this computer
  switches to it; other computers and the flows have to be pointed at it. After a dead computer: install the program, then pick the surviving data
folder, or restore the latest backup.

**Several computers on one data folder** (`app/shared_folder.py`): best one at a time, but it's guarded. The app
writes `App data/In use.json` (computer, user, since when; updated every 3 minutes, ignored after 15 without an
update); a second computer is told who has it open and can open it anyway, and the first is then told once. Saves
never overwrite what another computer saved meanwhile: `scheduler_data.json` and `settings.json` are compared with
what was read (combo edits: "try again"; settings: keep yours / load theirs / cancel), and pending swaps are only
saved if the schedule still holds what they were planned on (otherwise reload and redo them). The JSON
files, the exports and backups are written to a temp file and renamed (never half a file). Sync apps' conflict
copies (`Schedule-OFFICE-PC.xlsx`, `settings (1).json`, Dropbox's `... (conflicted copy ...)`) are pointed out when
the app opens the folder. All of this works the same on a folder only one computer uses. The program folder never
holds data (to try things, make a demo data folder: see [Testing without real data](#testing-without-real-data)).

**What's in the folder:**

| | |
|---|---|
| `combo-manager.sh` | Opens the app from source (Linux, for testing). |
| `app/` | The program. Nothing to open or change in here. |
| `dev/` | Tests, fake data and the build, for whoever maintains the app. |

**From source on Linux (testing):** `./combo-manager.sh` sets up a private Python environment in
`~/.combo-scheduler-python` (once; needs `sudo apt install python3-venv python3-tk`), and the window shows a
one-time **Setup** screen: click **Install** (needs internet, about a minute) and the app reopens by itself.

## The packaged apps (Windows and Mac)

GitHub builds them on every push to `main` (`.github/workflows/build.yml`): on each system it runs the tests,
builds the app with PyInstaller (`dev/build_exe.py`), and checks the built app can load every part it needs
(`--selftest`). Download from the repo's **Actions** tab: the latest "Build the apps" run > **Artifacts** (kept 30
days): `Combo-Manager-windows`, `Combo-Manager-mac-arm64` (Apple Silicon: M1 and later) or `Combo-Manager-mac-intel`
(older Macs; Apple menu > About This Mac says which). Pushing a tag like `v1.0` also attaches the zips to a GitHub
**Release**, a lasting download link. No Python, no Setup screen. The data folder is chosen as usual and isn't
inside the program, so a newer version just replaces the old one.

- **Windows:** unzip anywhere and double-click `Combo Manager.exe`. The first time, Windows may say "Windows
  protected your PC" (the app isn't signed): **More info > Run anyway**. About 330 MB unzipped (mostly the solver).
- **Mac:** unzip, drag `Combo Manager.app` into Applications, double-click it. It isn't signed with an Apple
  Developer ID ($99/year), so the first time the Mac says it can't check it: **System Settings > Privacy & Security
  > Open Anyway** (once). The Mac zip is made with `ditto`, which keeps the app intact; a plain zip would break it.

To build one yourself, on the system it's for: `pip install -r requirements.txt pyinstaller`, then `python
dev/build_exe.py` (the result is in `dist/`).

The package versions are pinned in `requirements.txt`: the app's Install button, the build and GitHub use them.

## Setup (once)

    pip install -r requirements.txt

`reportlab` is only needed for the PDFs; `tkcalendar` (optional) gives the app its pop-up calendars; without it
the app still works, with typed dates.

## Running it each semester

**1. Settings.** In the app's **Settings** tab (saved in `App data/settings.json` in the data folder; the
previous version is kept as `settings.json.bak`):

| Tab | What to fill in |
|---|---|
| General | Semester name, first and last possible show day, and the rules (see [Settings explained](#settings-explained)). Dates have a pop-up calendar. |
| Show days | One row per weekly show day: weekday, venue, sets per night, minimum shows per combo there, set times (below), and **Supervised nights preferred here** (e.g. Tuesdays). |
| Skip dates | Dates with no show (reading week, holidays), with a reason. The reason appears on the calendar. |
| Extra dates | One-off shows on days that aren't a regular show day. Usually empty. Set times are optional: blank uses the venue's usual times. |

**Save settings** checks everything first and says what to fix. Without the app: `python app/settings_file.py --new FOLDER`
writes `FOLDER/App data/settings.json` with example values (plain text, YYYY-MM-DD dates).

**Set times.** For each show day, **first set starts** (e.g. `19:00` or `7:00 PM`), **set length** and
**break** (minutes) give every set its start and end time: 19:00, 45, 15 gives 7:00–7:45, 8:00–8:45, 9:00–9:45, ...
The times appear on the calendar PDF and in `Schedule.xlsx`. Leave all three blank to
show set numbers instead.

`semester_name` must match exactly what students choose in the form's Semester question (e.g. `Winter 2027`).
Responses for other semesters are ignored.

**2. The combos and conflicts.** Enter them in the Combos tab (right-click > **New combo**, and on a person **Edit
conflicts**), or link the sheets the forms fill: **Linked sheets...** ticks which are read; each is the data folder's
usual file, or any file under any name (**Choose...**, e.g. straight from a synced OneDrive or SharePoint folder;
remembered on that computer: a sheet outside the data folder is chosen once on each computer). **Sync** reads them again (new sign-ups and conflicts).
Combos entered in the app and from a sheet sit side by side; the sheets' own warnings (rows, Pending combos) show in
**Check combos** only when a sheet is linked. A new data folder starts with none linked. From the command line:
`--approvals` and `--conflicts` take a path.
- **`Approvals.xlsx`** (formerly `Combo Approvals.xlsx`, still read): the approvals table the approval flow fills in, one row per combo submission, with
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
write only the schedule (`App data/schedule.json`), its exports (`Schedule.pdf`, `Schedule.xlsx`) and
`scheduler_data.json`.

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

    python app/solve.py --export

It asks you to confirm first, and warns if there is a schedule already (it's backed up, but swaps made in it aren't
in the new one; add `-y` to skip the question). It prints the same warnings as `--check`, including a **WARNING**
for any combo still Pending.

**The schedule itself is `App data/schedule.json`** (`app/schedule_file.py`): who plays which set, text typed into
sets, the supervised nights and the nights' dates, venues and times. Only the app (and `solve.py`) change it: a new
schedule, swaps, give-aways and claims, text in a set (Schedule tab), withdrawn combos. Every change backs it up first
into `App data/Schedule backups`. `Schedule.pdf` and `Schedule.xlsx` are **exports**, rebuilt after every change
(and with **Export PDF** / **Export Excel**, Schedule tab) and never read back: editing them changes nothing. One
open in Excel when it's rebuilt is skipped with a warning (the schedule is saved anyway); close it and export again.
Print `Schedule.pdf` with `Combos.pdf` (Combos tab): the combo numbers on the calendar match the list.

`Schedule.xlsx` sheets:
- **By night**: one table per show night (supervised nights marked): set, time, combo, each member (liaison
  marked) with their instrument, in the Combos tab's order, and the supervisor; lines between the columns and under
  each set. Open sets and text in a set too.
- **All sets**: one row per set (date, venue, set, start, end, combo, supervised), for sorting and filtering.
- **Supervision**: the supervised nights and the combos playing them.
- **Changes**: every change since the schedule was made, newest first (when, on which computer, what, and each
  set's before and after): the swap history, for "your show moved" questions.
- **Report**: warnings from when the schedule was made.

A data folder from before 2026-10-06 has the old, hand-editable `Schedule.xlsx` instead: the app turns it into
`schedule.json` the first time it loads it (swaps, text in sets and supervised nights included) and moves the old
file into `App data/Schedule backups`.

**A new semester:** the schedule records the semester it was made for. Change the semester name in Settings and
Save: the app offers to move last semester's files (the schedule, its exports, `Combos.pdf` / `.xlsx`, `Contact lists.xlsx`,
`Schedule backups`) into `Archive/<semester>` in the data folder. A schedule from another semester is never shown or
checked as this one's, and Make schedule moves it away first if it's still there. Combo numbers, member edits and
instruments are kept per semester in `scheduler_data.json`, so the new semester starts at Combo 01.

Once a schedule exists, **it decides which nights there are** (dates, venues, sets, times): the app, the check
and the exports use the schedule's own. Changing dates, show days, skip or extra dates in Settings only
affects the next schedule made (Save settings says so). Moving a supervised night, or changing a published night's
times or venue, isn't possible in the app yet (TODO).

The same input always gives the same schedule.

**5. Stats.**

    python app/solve.py --stats

Reads the schedule as it is (after swaps; no solving) and prints:
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
within the same night. Options that keep every hard rule come first; soft side effects are shown in orange
(a student playing twice in a night, shows close together, a first-year combo before the first-year date), and
an option that fixes an existing problem is marked in green. **Options that break a hard rule are listed
too, last and in red**, saying which rule ("✖ Breaks a rule: Combo 05 plays Tue Oct 13, when Ana Ruiz has a
conflict"): a manual override for when it's agreed (the student can make it after all, a combo gives up a show it
needs, ...). Adding one asks first, the pending list marks it ✖, and the rule check
(Check schedule) keeps flagging it. The same goes for "who could take this set" (Schedule tab). Combos are shown with their liaison
("Combo 07 (Ana Ruiz)"), and a person whose name isn't unique is shown with their email. For a picked option
(buttons under the list, or right-click on it), **Copy liaison emails** copies the liaisons of every combo it touches
(both sides of a trade or a give-away; just the one combo for an open set), and **Copy swap summary** copies it in
words, ready to email the liaisons: what changes for each combo (new set, new number of shows), heads-ups about
their own members (playing twice that night, or on a night they'd marked as a conflict) and the liaisons' names; no
rule names, settings or emails.
**Add to pending changes** collects it without touching any file: the tab then shows the
schedule as if it were done, so you can make several swaps in a row (each checked against the earlier ones), with
**Undo last** and **Discard all**. **Confirm changes** saves them all into the schedule at once (a copy of
it as it was goes to `App data/Schedule backups`) and rebuilds the PDF and xlsx in the background; you stay on the
Swaps tab, and it says when they're done. Closing the app with unsaved changes asks first.
A swap that would take a combo off its only supervised night is one of the red ones. Three-way swaps aren't
tried (do them as two swaps in a row).

The tabs load the data folder's files by themselves (at start, after **Change folder...**, and after each step or
swap); **Sync** (Combos tab) reads the linked sheets and anything synced in from another computer again.

**Schedule tab:** every show night (PROF = supervised) with its sets, including swap changes not saved yet
(highlighted, with their nights opened), a search box and "only nights with open sets". While changes are
unsaved, a bar at the top offers **Confirm changes** (save them into the schedule and rebuild the exports), **Undo
last** and **Discard all**. Double-click a combo's set to jump to the Swaps tab
with that show picked (right-click: also "Give it away", and **Go to combo** to see it on the Combos tab); double-click an open set to see **every combo that could
take it** and add one as a pending change. **Right-click a night** to copy, ready to paste into Outlook: the
liaisons' emails, the combo emails (every student playing, then the supervisors; separated by `;`), or a short
summary of the night (sets, times, combos, members' names; no emails). **Right-click an open set** to type text into
it instead of a combo (e.g. `Jam session`, `Guest: Trio X`): it's shown on the calendar in italics (cut to about 10
characters there, printed in full under the month) and the set counts as taken; change or clear it the same way.
Saved straight away (backup first), unlike swaps. **Export contact lists** writes `Contact lists.xlsx`: one row per night
with its sets and everyone's emails, for printing or sharing. Both use the schedule as shown, including unsaved
changes. **Export PDF** / **Export Excel** rebuild `Schedule.pdf` and `Schedule.xlsx`
from the schedule and open one; with unsaved changes they ask: save them first, export the saved schedule only, or
cancel.

**Unsaved changes in the Combos tab:** every edit there (names, emails, instruments, members, liaison, first-year
tag, withdraw / put back) waits until it's confirmed, and the tab shows it as if done (the combo is marked "● unsaved
changes"); a bar under the table says how many there are. **Confirm changes** saves them all at once into `scheduler_data.json`
(read again first, so nothing saved meanwhile on another computer is lost); **Undo last** and **Discard all** as in
the Swaps tab. Closing the app, changing folder or exporting with unsaved changes asks first. The other tabs see the
changes once they're confirmed.

**Changing a combo's members** (Combos tab: pick a combo or a person, then **Actions ▾** below the list, or right-click; the menu shows what fits the row picked): **Copy liaison email** copies the liaison's email, and **Copy emails** the combo's students (liaison
first) and supervisor, ready to paste into Outlook. (Schedule tab, right-click a night: **Copy liaison emails** and
**Copy combo emails**, everyone playing that night with the supervisors.) **Add a member** finds someone the scheduler
already knows (type part of a name or email) or takes a new email, guesses the name from it (change it if needed) and
optionally sets the instrument; it warns if they're in another combo or, once a schedule exists, have a conflict or a
second show on one of this combo's nights. **Remove** takes someone out; removing the liaison first asks who takes
over. Removed people stay listed in grey: Actions > **Put back**. **Make liaison** (on a person) or **Change the liaison** (on a combo) changes the liaison. None of
this touches `Approvals.xlsx`: the changes are kept in `scheduler_data.json` (by Response Id, so they stay
attached to the right combo as new responses come in), applied whenever the approvals are read, and listed by
**Check combos**. A combo with fewer members than the "Warn: members per combo" setting (default 4) shows ⚠ and is
flagged by the check. After the schedule is out, run **Check the schedule** after a change: a new member's conflicts
count from then on.

**Withdrawing a combo** (Combos tab: Actions > **Withdraw**): the combo stops being scheduled and its
number stays reserved, so the numbering keeps a gap and no other combo's number changes (like setting Status to
Withdrawn in the approvals, without opening Excel). If the schedule is out, its sets become OPEN in the schedule
right away (a backup goes to `App data/Schedule backups`) and the exports are rebuilt; nothing is given to another combo
automatically. Volunteers can claim the open sets, or give one to a combo from the Schedule tab ("who could take
it"). A set on a **supervised night** must be filled (supervised nights are full): the confirmation says so and the
rule check flags it until it is. Withdrawing waits until pending swaps are confirmed or discarded. Withdrawn combos
stay listed in grey; Actions > **Put back** returns the combo with its old number but no shows (its sets may be
taken by then): it can claim open sets in the Swaps tab.

**New combo...** (Combos tab, Actions or right-click anywhere, even on an empty list): a combo that isn't in the approvals (accepted after the form
closed): liaison, other members and supervisor by email. It gets the next number and is then edited, withdrawn and
put back like any other; it starts with no shows (give it sets, Schedule tab, or let it claim open sets, Swaps tab).
Kept in `scheduler_data.json`.

**Overruling a conflict** (Combos tab, right-click a person > **Conflicts...**): their conflict dates, each with a
"counts" tick; untick one when they can make it after all. It stops counting everywhere (swaps, the check), the
conflicts sheet isn't changed, and Check combos lists it. (Overruling a whole submission is still the
spreadsheet's Status column.)

**The log** (About tab > **Open the log**): `App data/Logs/<computer>.txt` in the data folder, one file per
computer: every step's output, saves, backups, folder changes and every error with its details. When something
goes wrong the app says so and points to it: send that file. Kept to about 1 MB.

**Pending combos and the first-year tag** (Combos tab): combos still waiting for a decision are listed in grey
("Waiting for a decision · liaison", with their members); approve or reject them with the approval email's buttons
in Outlook, which also records the decision and (once built) emails the liaison. Keep using **Accept -
first-year combo** there: it's the moment the director knows. To fix a tag afterwards, Actions > **Mark as a
first-year combo** / **Remove the first-year tag**: kept in `scheduler_data.json`, it wins over the approvals' First
year column, and Check combos lists it. If the schedule is out it isn't made again; the message names any show
before the first-year date (swap it in the Swaps tab). Pop-up menus close with Escape or a click elsewhere.

**Member order** (Combos tab and `Combos.pdf`): by instrument, top to bottom: any other instrument (e.g.
Vibraphone), Voice, Trumpet, Saxophone, Trombone, Guitar, Piano, Bass, Drums, then people with no instrument set
yet; alphabetical within one instrument. The liaison is marked, not moved to the top. The order is
`INSTRUMENTS` in `app/util.py` (also the instrument menu's order).

**Combos tab:** every accepted combo (with its liaison and shows) and its people, in columns: Instrument, Also in
(other combos), Conflicts (dates submitted), Email; with a search box. **Click an Instrument cell** to pick one
(Saxophone, Trumpet, Trombone, Guitar, Piano, Bass, Drums, or Other: type anything); it's per person per combo and
kept in `scheduler_data.json`. It's chosen once: a person's later combos (this semester or the next) start with the
instrument last set for them (by email), until changed. **Export PDF** writes `Combos.pdf` (every combo with its supervisor and
members, instruments when set; numbered like the calendar); **Export Excel** writes `Combos.xlsx` (one table per
combo, like the schedule's: each member with instrument and email, the liaison marked, then the supervisor). Double-click a person
(or Actions > **Change name**) to correct their name, or double-click their email (or Actions > **Change email**) to fix a typo'd
address: the spreadsheets aren't changed, the fix is applied whenever they're read, to the combos *and* the
conflicts, so a member whose conflicts didn't count because of a typo is matched again (corrected emails show ✎;
typing the original back removes the fix); it's kept in `scheduler_data.json` and used everywhere (PDFs, checks,
Swaps tab).

The Swaps tab has three modes, switched at the top:
- **Swap:** trade or move (above).
- **Give away:** a combo hands one of its shows to another combo (which gains a show) or leaves it open.
  When the combo needs that show (its minimum shows, a venue minimum, its supervised night), these are red ones.
- **Claim:** a combo volunteers for an open set; the list shows every open set it can legally take
  (no show needs to be picked).

**Check schedule** (Schedule tab; `solve.py --stats`) re-checks the schedule as it is: it
catches a combo on a night one of its members marked as a conflict (conflicts can arrive after the schedule is
out), a combo playing twice in one night, a combo that isn't accepted any more, a combo left without its required
show at a venue or without a supervised night, and an open set on a supervised night. Don't re-run `solve.py`
without `--stats` after the schedule is published: it builds a fresh schedule (the old one is backed up, but the
swaps made in it are gone from the new one).

## What the solver does

Hard rules, never broken:
- A combo never plays a night that any of its members marked as a conflict.
- Every combo gets at least the minimum shows per combo at each venue (Settings > Show days).
- Every combo gets at least `min_shows_per_combo` shows in total, at any venues. Together with the venue minimums:
  with Upstairs 1 / Clara 0 and a total of 2, "Upstairs + Clara" and "Upstairs twice" are fine, "Clara twice" never
  happens. The solver prefers one show at each venue (goal 6), so "Upstairs twice" only happens when a combo
  can't make any Clara night (or there's no other way); the Report lists those combos.
- No combo goes over `max_shows_per_combo`.
- In `open` mode, each combo gets exactly `min_shows_per_combo` shows (more is volunteering). In `auto` mode,
  first-year combos get exactly that many too (no extras).
- Every combo plays at least `min_supervised_per_combo` **supervised nights** (nights a professor attends;
  usually 1, 0 = none). A supervised night is always **full**: no open sets. The solver picks those nights: at most `max_supervised_nights`, and within
  that as few as possible (it weighs this against spacing, so it may use one or two more than the minimum).
  It doesn't assign professors: the Supervision sheet lists the nights, with a column to fill in who's coming.

Goals, in order of importance (the solver gives up a lower goal to meet a higher one):
1. Give every combo its shows. Usually possible; it fails when a
   combo's members' conflicts cover every night at a venue, or a venue has fewer sets than there are combos.
2. First-year combos don't play before `first_year_earliest_date`. Only broken when it's the only way to give
   a first-year combo its show; the Report flags it.
3. Keep the number of shows equal between combos.
4. A first-year combo's **first show is on a supervised night**, so they get feedback on their first set
   (`first_year_first_show_supervised`). Worth an extra supervised night, but never unequal show counts; the
   Report names any first-year combo it couldn't do this for.
5. Supervised nights on a show day marked **Supervised nights preferred here** (Settings > Show days, e.g. Tuesdays), so
   professors come on the night that suits them. Other nights are used only when there's no other way.
6. Use as few supervised nights as possible (within `max_supervised_nights`).
7. Each combo plays at every venue it can: one Upstairs and one Clara show rather than two Upstairs. The Swaps
   tab warns when a swap would take this away.
8. Supervised nights earlier or later in the semester (`supervision_timing`), when chosen. A light preference: it
   moves supervised nights around but never adds one.
9. Spread each combo's shows apart (see [Tuning](#tuning)).
10. Avoid a student playing twice in one night (two of their combos on the same night). A minor goal: if it
   happens, the Report says who and when, and the two sets are placed back-to-back in the running order.
11. Within a night, a combo that went late last time tends to go early this time.

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
| `first_year_first_show_supervised` | **First show supervised** (First-year section): a first-year combo's first show is on a supervised night (goal 4). Only with both first-year combos and supervised nights on. Missing = On. |
| `max_blocked_dates_per_person` | Warning only: flags students who blocked many show nights. |
| `min_usable_nights_per_combo` | Warning only: flags combos whose members' conflicts leave fewer usable nights than this. |
| `min_members_per_combo` | Warning only (default 4): flags combos with fewer members than this, e.g. after someone is removed in the Combos tab. Blank = no warning. |
| `extra_slot_policy` | **Leftover sets** in the app. `open` = Leave open (recommended): each combo gets its shows; the sets left over stay open for volunteers, or you fill them by hand (Schedule or Swaps tab). `auto` = Fill every set: the solver fills every set, so some combos get extra shows. |
| `min_shows_per_combo` | Every combo gets at least this many shows in total, at any venues, as long as each venue's "Min per combo" is met. In `open` mode: exactly this many. Required. |
| `max_shows_per_combo` | Cap on total shows per combo. Blank = no cap. |
| `min_supervised_per_combo` | **Supervised nights per combo**: how many nights each combo plays with a professor attending (usually 1). 0 = no supervised nights at all; `max_supervised_nights` and the show days' "Supervised nights preferred here" are ignored, and the exports show no supervised nights. Older settings' `every_combo_supervised` Yes / No reads as 1 / 0. |
| `max_supervised_nights` | **Max supervised nights (all professors)**: the total for the whole semester, counting all professors together, not per professor (one supervised night covers every combo playing it). At most this many supervised nights. Blank = no limit (still as few as possible). Each night fits its number of sets, so 33 combos at 4 sets a night need at least 9. |
| `supervision_timing` | **Supervised nights preferred**: `none` (Any time), `early` (Earlier in the semester) or `late` (Later in the semester). A light preference (goal 8): each supervised night costs a little more the further it is from the preferred end. `--stats` says how many fell in the preferred half. Missing = none. |
| `solver_time_limit_sec` | How long the solver searches (roughly seconds). 90 is plenty (it stops as soon as it has proven the best schedule), unless the Report says FEASIBLE instead of OPTIMAL. |
| `student_email_domain` | Students' email domain (`mail.mcgill.ca`). Members with other addresses are fine; they're just listed in the check, and a supervisor on this domain gets a "student address?" warning. Blank = don't check. |
| `professor_email_domain` | Supervisors' email domain (`mcgill.ca`): a supervisor with another address, and a student on this domain (a slip for `mail.mcgill.ca`?), are pointed out in Check combos. Blank = don't check. (Domain fixes are no longer a setting: fix an address in the Combos tab. Settings files that still have `email_domain_fixes` keep using them.) |

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
(28 above, Fall 2026 test data), then set it in the Settings tab and run `solve.py --export`.

### `solver_time_limit_sec`

If the Report or the console says `FEASIBLE` rather than `OPTIMAL`, the solver ran out of time before
proving it found the best schedule. The schedule is still valid (usually as good). Raise the limit (e.g. 180) if you want it
to keep looking. `open` mode usually solves in a few seconds.

### Weights (advanced)

The relative importance of the goals is set by the `W_...` constants at the top of `core/solver.py`.
You shouldn't need to touch them. If you do, run `python dev/test_rules.py` afterwards.

## Testing without real data

Run these from the top folder. Demo data goes in a folder of its own, outside the program folder; switch to it in
the app with **Change folder...** (and back to the real one the same way). `app/solve.py` works on the data folder
chosen in the app on this computer unless you add `--folder`.

    python dev/make_fake_forms.py ~/Documents/"Combo Manager demo"   # example settings + fake forms + instruments
    python dev/test_rules.py         # read -> solve on several fake scenarios, checks every hard rule


Run `python dev/test_rules.py` after any code change. `make_fake_forms.py` won't overwrite existing input files
unless you add `--force`; `test_rules.py` works in a temporary folder and never touches your files.

## Files

| File | Job |
|---|---|
| `app/inputs.py` | The ONLY file that knows what `Approvals.xlsx` and `Conflicts.xlsx` look like (and the approval rules). Reads them into the solver's input; writes nothing. |
| `app/solve.py` | Reads `settings.json` + the two downloads, runs the solver, saves the schedule (+ `Schedule.pdf` and `Schedule.xlsx`). |
| `app/schedule_file.py` | The schedule (`App data/schedule.json`): load, save changes (backup first), archive; turns an old `Schedule.xlsx` into it once. |
| `app/scheduler_app.py` + `combo-manager.sh` | The window around `solve.py`, and the Linux launcher. |
| `app/schedule_panel.py` | The app's Schedule tab (nights and sets, who could take an open set, Export PDF). |
| `app/store.py` | `scheduler_data.json`: combo numbers, corrected names and emails, instruments. |
| `app/data_folder.py` | What's in the data folder and where: every path into it is made here; whether a folder can be used. |
| `app/app_config.py` | This computer's own choices (`~/.combo_scheduler.json`): which data folder, text size, dark mode. |
| `app/shared_folder.py` | Several computers on one data folder: lock file, crash-safe writes, changed-on-disk checks, conflict copies. |
| `app/backup.py` | Backup... / Restore...: the data folder as one zip, and back into a new folder. |
| `app/app_log.py` | The log: `App data/Logs/<computer>.txt`. |
| `app/outputs/combos_pdf.py`, `combos_xlsx.py` | Write `Combos.pdf` and `Combos.xlsx` (the Combos tab's Export buttons). |
| `app/combos_panel.py` | The app's Combos tab (all combos and people; names, emails, instruments, members, liaison). |
| `app/swap_panel.py`, `app/core/swaps.py` | The app's Swaps tab, and the swap finder behind it (pure, tested in `test_rules.py`). |
| `app/theme.py` | The app's look (Tk's built-in theme, recoloured light and dark). The About tab (author and contact) is in `scheduler_app.py`. |
| `app/settings_file.py` | Reads, checks and saves `settings.json` (defaults and help texts live here). |
| `app/settings_panel.py` | The app's Settings tab. |
| `app/core/stats.py` | Stats and the rule check behind `solve.py --stats`. |
| `app/core/` | The scheduling logic. Plain Python objects only: no Excel, no Forms. `model.py` is the contract. |
| `app/outputs/excel_schedule.py` | Writes the `Schedule.xlsx` export (and reads an old hand-editable one, once). |
| `app/outputs/schedule_pdf.py` | Writes `Schedule.pdf`, numbered to match `Combos.pdf` (Combo 05 -> 05). |
| `dev/make_fake_forms.py`, `dev/test_rules.py` | Fake data and an independent rule checker. |

## Collecting data a different way later

Replace `inputs.py` with something that returns the same `ScheduleInput` (combos and each student's blocked
dates; see `core/model.py`). The solver doesn't change.
