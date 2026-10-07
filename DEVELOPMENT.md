# Development

- **Run from source (Linux):** `./combo-manager.sh`. It sets up a private Python the first time.
- **Tests:** `python dev/test_rules.py`. Run them after every change.
- **Fake data to try things:** `python dev/make_fake_forms.py FOLDER`, then **Settings** tab > **Change folder...**
- **Build:** GitHub builds Windows and Mac on every push (and puts them on a Release for tags like `v0.2.0`).
  Locally: `pip install -r requirements.txt pyinstaller`, then `python dev/build_exe.py`.
- **Version:** `VERSION` in `app/scheduler_app.py`.
- **Quick Start:** edit `QUICK_START.md`, then `python dev/make_quick_start.py`.
- **Icon:** `python dev/make_icon.py`.

## Where things are

| | |
|---|---|
| `app/scheduler_app.py` | The window, and one `*_panel.py` file per tab. |
| `app/core/` | The scheduling, swap and rule-check logic. |
| `app/inputs.py` | Reads the two spreadsheets. |
| `app/outputs/` | Writes the PDFs and Excel files. |
| `app/solve.py` | Runs the solver (also from the command line: `--help`). |
| `app/data_folder.py` | Where everything goes in the data folder. |
