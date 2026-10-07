# Combo Manager

Makes the semester's combo show calendar and handles swaps during the semester.

**How to use it: see `Quick Start.pdf`.**

![The Schedule tab](docs/schedule.png)

| Combos | Swaps |
|---|---|
| ![The Combos tab](docs/combos.png) | ![The Swaps tab](docs/swaps.png) |

## What it does

- **Combos:** brings in the approved sign-ups and conflicts from the forms, or lets you add them by hand. Add or
  remove members, change the liaison, fix names and emails, set instruments, mark first-year combos, withdraw a
  combo. **Check combos** points out problems before the schedule is made.
- **Schedule:** makes the whole semester in about a minute. Every combo gets its shows, never on a night one of its
  members can't make, with supervised nights, first-year combos starting later, and shows spread out. Exports a
  calendar PDF and an Excel file, ready to send.
- **Swaps:** when a combo can't make a show, lists every possible trade or move, best first, and warns about side
  effects. Also handles giving a show away and claiming an open set. Copies a ready-to-send email for the liaisons.
- **Safe changes:** nothing is saved until **Confirm changes**. **Earlier versions** brings back the schedule as it
  was before any change, and **Lock schedule** stops it being remade by accident.
- **Semester:** the dates, show nights, venues and rules, each explained in the app.
- **Emails:** copy the liaisons' or everyone's emails for a night or a combo, ready to paste into Outlook.

## Download

Repo **Actions** tab > latest "Build the apps" run > **Artifacts**:

- **Windows:** `Combo-Manager-windows`. First time: **More info > Run anyway**.
- **Mac:** `Combo-Manager-mac-arm64` (M1 and later) or `-mac-intel`. First time: **System Settings > Privacy &
  Security > Open Anyway**.

## The data folder

Everything is kept in one folder (e.g. `ComboManagerData`, can be in OneDrive), chosen when the app first opens.

| | |
|---|---|
| `Approvals.xlsx`, `Conflicts.xlsx` | Sign-ups and conflicts, filled by the Microsoft Forms flows. |
| `Exports/` | The schedule and combo list, as PDF and Excel. Safe to share. |
| `Archive/` | Past semesters. |
| `AppFiles/` | The app's own files. Don't edit them. |

Back it up now and then: **Settings** tab > **Backup...**

Working on the code? See `DEVELOPMENT.md`.
