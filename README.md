# Combo Manager

Makes the semester's combo show calendar and handles swaps during the semester.

**How to use it: see `Quick Start.pdf`.**

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

## Development

- Run from source (Linux): `./combo-manager.sh`
- Tests: `python dev/test_rules.py` (run after every change)
- Fake data to try things: `python dev/make_fake_forms.py FOLDER`
- Build: GitHub does it on every push. Locally: `pip install -r requirements.txt pyinstaller`, then
  `python dev/build_exe.py`
- Version: `VERSION` in `app/scheduler_app.py`
- Quick Start: edit `QUICK_START.md`, then `python dev/make_quick_start.py`

Code: `app/scheduler_app.py` is the window (one `*_panel.py` file per tab), `app/core/` the scheduling and swap
logic, `app/inputs.py` reads the spreadsheets, `app/outputs/` writes the PDFs and Excel files.

## License

MIT (see `LICENSE`).
