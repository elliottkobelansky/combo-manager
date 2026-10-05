# TODO

Planned work for the combo scheduler, roughly in the order it's needed before Winter 2027.

---

## 1. Combo approval: accepted / rejected / withdrawn (Power Automate)

**Goal:** the director approves each combo **as it is submitted**, without running any scripts. Only Accepted
combos are scheduled and appear in `Combos.pdf`.

**Decided:** use Power Automate (access with a McGill account confirmed). Ownership: see #6.

**Setup (in Microsoft 365, no code):**
- [x] Excel workbook `Combo Approvals.xlsx` in shared OneDrive / SharePoint, with a table named `Approvals`:
  Response Id | Submitted | Semester | Liaison | Members | Supervisor | First year | Status | Decided by |
  Decided on | Notes. Dropdowns on Status (Pending / Accepted / Rejected / Withdrawn) and First year (Yes / No).
- [x] Flow: new combo form response -> add a row (Status = Pending) -> approval request to the director ->
  Status = Accepted or Rejected, with who decided, when, and their comment.
- [ ] Decision email: after the approval, the flow sends an email (Office 365 Outlook "Send an email (V2)")
  to the liaison, Cc the other members and the supervisor, saying the combo was accepted or rejected, with the
  director's comment. Write the wording first (accepted: what happens next and when the schedule comes out;
  rejected: why, and who to contact). With no branches, one email step can pick its subject and text with
  `if(startsWith(outputs('Decision'), 'Accept'), '...', '...')`.
- [ ] Test with a few test submissions, then delete the test rows.

**Director's routine:** click Accept / Accept - first-year combo / Reject in Outlook or Teams (custom responses;
the flow turns the click into Status = Accepted / Rejected and First year = Yes / No). To withdraw a combo or fix its first-year
tag, edit that row in the workbook. Rows still Pending = waiting for a decision. The flow gives up after 30 days
(Power Automate's limit), so a row older than that stays Pending until it's typed in by hand (in README step 2).

**Combo Info retired (2026-10-04).** Python reads `Combo Approvals.xlsx` directly again (`inputs.py`: only Accepted
rows of the settings' semester, clean emails, latest of identical submissions, warnings incl. Pending). Combo numbers
(per semester, never reused), corrected names and instruments live in `scheduler_data.json` in the data folder
(`store.py`). The combo list PDF is exported from the
app's Combos tab. Tested in `test_rules.py` (exact read vs. what make_fake_forms put in; numbers stay put).
- [x] Removed in Microsoft 365 too (flow, scripts, Combo Info.xlsx). The only spreadsheets are now
  `Combo Approvals.xlsx` and `Conflicts.xlsx`; only the approval flow and the conflict flow remain.
- [ ] **Conflict flow** (decided 2026-10-04): new conflict-form response -> Get response details -> Add a row into
  a table: `Conflicts.xlsx`, table `Conflicts` (Response ID | Submitted | Semester | Email | Date 1 | Date 2 |
  Date 3 | Date 4 | Reason | Additional Info | Status | Notes), Status = `Active`. No approval step: conflicts count by default;
  the director sets Status = `Overruled` to reject one. Email = the typed McGill email, or the responder's email
  if that's blank. Python reads it (`inputs.py`, default `--conflicts Conflicts.xlsx`). Maybe later: email the
  student when a conflict is overruled.

**Still to do:** add the **first-year question** to the form (#4) and map it to the First year column in the flow.

---

## 2. Supervisor availability and scheduling (if we decide to do it)

**Done (2026-10-04): supervised nights.** Every combo plays at least one night a professor attends; the solver
picks those nights (at most `max_supervised_nights`, as few as possible), marks them PROF on the calendar, and
lists them in a Supervision sheet with a column to fill in the professor. Not done: which professor, or their
availability (below).

**Goal:** make sure a supervisor (professor or other supervisor) can be at each combo's shows, or at each show
night.

**Decide first:** which of these do we need?
- **(a) Each combo's own supervisor attends its shows.** Collect supervisor conflicts (another form, or a sheet)
  and treat them like student conflicts: a combo can't play a night its supervisor can't make. Easy: the solver
  already pools member conflicts, so the supervisor just becomes one more person whose conflicts count. Maybe as
  a soft rule, so one unavailable supervisor can't make a combo impossible to schedule.
- **(b) One supervisor on duty per show night**, not tied to particular combos. This is a separate assignment: spread
  the nights fairly among the available supervisors (like a small second schedule). Shown on the calendar PDF.
- Both need supervisor availability. Supervisor names currently come from the email address; a Supervisors sheet
  (email | name | conflicts) would fix the names too.

---

## 3. Semi-automatic emails (copy and paste)

**Goal:** after the schedule is final, generate ready-to-send email text, so sending is just copy, paste, send.

**Notes:**
- Output an `Emails.xlsx` (or `.txt`) with one row per email: **To** | **Cc** | **Subject** | **Body**.
  - **Per combo:** to all members (Cc the supervisor). Combo number and members, each show's date, venue,
    set number (and time), the swap policy, and who to contact.
  - **Per supervisor:** the combos they supervise and all their show dates.
  - Optionally **one to everyone**, with the full calendar attached (`Schedule.pdf`).
- Email templates with placeholders (`{combo}`, `{shows}`, ...) in the settings or a text file,
  so the wording can change without touching code.
- Maybe a `mailto:` link per row that opens a pre-filled Outlook email (watch out for length limits on long bodies).
- The "your combo was accepted / rejected" email is sent by the approval flow (#1), not by this.
- Could be `python solve.py --emails` or a separate `make_emails.py` that reads `Schedule.xlsx`, so emails match
  the schedule *after* any swaps.

---

## 4. Finish writing the form descriptions

**Goal:** finish the instructions and question text on both Microsoft Forms (combo sign-up and conflicts).

**Notes:**
- **Combo form:** nothing reads it directly; the flow copies its answers into the approvals table. So
  question titles can change freely, but after changing a question, check the flow still maps it to the right
  column. **Don't rename the approvals table's headers**: `inputs.py` finds them by the words "Response Id",
  "Semester", "Liaison", "Members", "Supervisor", "First year" and "Status". To be added to the form:
  a first-year question (and optionally a combo name; add a "Combo name" column to the table for it).
- **Conflict form:** `inputs.py` finds columns by **words in the question titles**, so keep "Semester", "Email"
  (the typed McGill email question) and "Date" (every conflicting-date question).
- The Semester answer must match the semester name in the settings exactly. A dropdown or choice question avoids
  typos.
- Explain clearly: students only submit the conflict form if they have conflicts; list all the dates they can't play;
  McGill students use their `@mail.mcgill.ca` address (members from outside McGill can use any address, but the
  **same** one on both forms); the first member listed is the liaison.
- After changing a form, submit a test response and run `python solve.py --check` to check it's still read correctly.

---

## 5. Change settings to proper defaults

**Goal:** fill in the real Winter 2027 values in the app's Settings tab (`settings.json`). The defaults in
`settings_file.py` (DEFAULTS) are guesses for Winter 2027: check them too, since a new folder starts from them.

**Notes:**
- `semester_name`, `start_date`, `end_date`, `first_year_earliest_date`: Winter 2027 dates.
- Skip dates: the real reading week / holidays (the defaults are placeholders).
- Show days: confirm the venues, weekdays, sets per night and minimums (currently Tue Upstairs and Fri Clara, 4
  sets each, 1 required Upstairs show).
- `min_days_between_shows`: re-tune with `python solve.py --compare-gaps 14 21 28 35` on the real data (28 was
  best for the Fall test data).
- Show day set times: confirm Upstairs 7:00 PM, 45 min sets, 15 min breaks and Clara 7:00 PM, 30 min, 15 min.
- Check the warning thresholds (`max_blocked_dates_per_person`, `min_usable_nights_per_combo`), the
  `max_shows_per_combo` cap, and `solver_time_limit_sec`.
- Update the help texts in `settings_file.py` (HELP) if anything changes, and the example values in the README.

---

## 6. Ownership: make sure nothing belongs to one person

**Goal:** everything the scheduler depends on keeps working after whoever set it up graduates or leaves.

**Notes:**
- **Microsoft Forms** (combo sign-up and conflicts): owned by a shared or role account, or moved into a group
  (e.g. a Microsoft 365 group or Teams team for the combo program). Responses stay with the form.
- **Power Automate flow** (approvals): created on the shared account, or with co-owners added. A flow stops
  running if its owner's account is deleted.
- **Approvals spreadsheet** (the Excel file the flow writes to) and the **form response files**: stored in shared
  OneDrive / SharePoint storage, not a personal OneDrive.
- **The scheduler itself** (these scripts, `settings.json`, `README.md`): kept somewhere shared too, so the next
  director can find and run it.
- Write down who has access to each, and how to hand it over at the end of a term.

---

## 7. Test members with non-McGill emails (e.g. Gmail)

**Goal:** a combo member who isn't from McGill, or who signs up with a personal Gmail address, should be
handled without problems. This happens sometimes, and it shouldn't be an issue.

**Fixed in the code (2026-10-04):**
- [x] The parser keeps any valid email (it used to remove non-`@mail.mcgill.ca` members). The report lists
  non-McGill members as INFO.
- [x] A bare `@mcgill.ca` is still rewritten to `@mail.mcgill.ca` (a common student slip); other domains are
  kept as typed (lowercased, so `Jamie@Gmail.com` = `jamie@gmail.com`).
- [x] A supervisor with a non-McGill address is fine; only a student address (`@mail.mcgill.ca`) is flagged.
- [x] Fake data has a Gmail member and a Gmail liaison with conflicts; `test_rules.py` checks they're kept.
- Already there: a warning when someone submits conflicts but isn't in any combo (catches one person using a
  Gmail address on one form and a McGill address on the other).

**Still to test for real:**
- [ ] Submit the combo form with a Gmail member and liaison, through the flow, and check the approvals row and
  the `solve.py --check` warnings.
- [ ] Decide on the conflict form: if it's restricted to "Only people in my organization", non-McGill people
  can't submit it. Either open it to anyone, or the director submits it for them (see #8).
- [ ] Names from Gmail addresses (`jsmith1987@gmail.com` -> "Jsmith") will look odd; fix by hand in the
  app's Combos tab (kept in `scheduler_data.json`).

---

## 8. Documentation for the director (everything, including manual fallbacks)

**Goal:** a director who doesn't code can run the whole semester from one guide, and knows what to do **by
hand** when something doesn't fit or breaks.

**Cover the normal path:** the forms (what students see, when they open and close, changing the Semester
option), the approval flow (what the director clicks), the approvals table (Status / First year / Notes),
downloading the two files, `solve.py`, the PDFs, swaps, `--stats`, and the start-of-semester
checklist (settings values, set times, numbering restarts).

**Cover manual ways to do things:**
- **Add a combo yourself:** fill in the combo form on the combo's behalf, then approve it. Or, if the flow
  isn't working, add a row directly in the approvals table (Status = Accepted; use a made-up unique Response Id
  such as `9001`).
- **Accept / reject / withdraw without the approval email:** type the Status into the table (e.g. the request
  expired after 30 days, or went to the wrong person). Already in README step 2; move it to the guide.
- **Fix a mistake in a submission:** edit the Members / Liaison / First year cell in the table (the script reads
  the table, not the form). Or have them resubmit and reject the old row (see the withdraw / correction idea).
- **Conflicts for someone who can't use the form** (non-McGill member, form closed, sent by email): submit the
  conflict form for them with their email typed in.
- **Late combo after the schedule is out:** accept it (it gets the next number; existing numbers
  are kept), and give it open sets in the app (Schedule tab: double-click an open set) in `Schedule.xlsx`; check with `solve.py --stats`. Don't re-run `solve.py`.
- **Swaps and withdrawals after publishing:** edit the Combo column in `Schedule.xlsx` (`OPEN` for a freed set),
  then `solve.py --stats`.
- **The flow is broken or its owner left:** how to rebuild it (the step-by-step setup), and where the
  ownership notes are (#6). Meanwhile, approve by typing into the table.
- **Python not available on this computer:** what to install (README Setup), or who to ask.

**Where:** probably a `DIRECTOR_GUIDE.md` (or a shared Word / Claude doc) next to the scripts, linked from the
README; the README stays the technical reference.

---

## 9. Instruments: track each combo's instrumentation and check restrictions

**Started (2026-10-04):** the director can set each person's instrument per combo in the app's Combos tab (saved in
`scheduler_data.json`, per semester: "Combo 05|email" -> instrument). Not used yet by the checks, the solver or
the PDFs; next steps below (and maybe show instruments on the combo list PDF).

**Goal:** the director currently keeps track of which instruments each combo has, and of instrument
restrictions, by hand. Could this be automatic?

**Decide first:** what are the restrictions? For example:
- **Combo rules:** e.g. each combo needs a rhythm section, or limits on certain instruments per combo.
- **Venue rules:** e.g. a venue has no drum kit or piano, so some combos can't play there. This affects the
  schedule itself.
- **Student rules:** e.g. a student can be in at most N combos, or play a given instrument in only one.
- **Program-wide limits:** e.g. at most N combos with a given instrument.

**Possible approach:**
- **Collect it:** on the combo form, each member question gets an instrument next to it (a dropdown, plus
  "Other"). The flow copies it into the approvals table, e.g. an **Instruments** column ("Ana Ruiz - piano") so
  the director sees the instrumentation when approving, with the approval request showing it too.
- **Check it:** `inputs.py` / the app reads the instruments and warns about broken combo, student or program rules in
  its report. Rules live in the settings, so they can change without code.
- **Schedule with it:** venue rules become a solver rule (a combo only plays venues that fit its instruments),
  the same way member conflicts already block nights.
- **Overview:** a per-instrument summary (how many combos have drums, bass, ...) in the parse report or in
  `Combos.pdf`.

---

## 10. Messy member entries on the combo form

**Goal:** members type things like `piano: first.last@mail.mcgill.ca`, `Ana Ruiz (bass) - ana.ruiz@...`, a name
with no email, or a misspelled address. The parser should take what it can and report the rest, not drop people
silently.

**Already handled:** `inputs.py` finds every email anywhere in the text (`EMAIL_RE`), so labels, names,
instruments, brackets and any separator around a valid address are ignored. Duplicates, upper case and a bare
`@mcgill.ca` are fixed too.

**Not handled yet (these members are silently left out):**
- [ ] Text with no email at all (e.g. a name alone, "same as above", "TBD"): report every leftover word or chunk
  of the Members cell that isn't an email, so the director can spot a missing member.
- [ ] Typos in the domain (`@mail.mcgil.ca`, `@mail.mcgill.com`, `@gmial.com`, `@mailmcgill.ca`): warn, and
  suggest the likely right address. Known slips can already be corrected automatically with the `email_domain_fixes`
  setting (2026-10-05); still to do: spot unknown ones (e.g. close to `student_email_domain`) and suggest a fix.
- [ ] A missing or doubled `@`, or spaces inside an address (`first.last @mail.mcgill.ca`).
- [ ] The same person under two addresses (McGill in one combo, Gmail in another): only the conflict-form check
  in #7 covers this now.
- [ ] Check the member count against what the form says (e.g. if the form asks for 3-6 members, warn about 1 or 9).
- [ ] Add these cases to `make_fake_forms.py` and `test_rules.py`.

**Prevent it on the form instead:** one question per member (email only, with Forms' email validation if
available), plus a separate instrument dropdown (see #9), so there's nothing to clean up afterwards.

---

## 11. Per-night contact list in the schedule

**Done (2026-10-04):** in the app's Schedule tab, right-click a night to copy its students' emails, supervisors'
emails or a night summary; **Export contact lists** writes `Contact lists.xlsx` (one row per night). Still open:
the email *texts* (#3), e.g. per combo "your show dates".

**Goal:** for each show night, a ready-to-copy list of everyone playing, so reminders or last-minute changes are
one copy-paste into Outlook.

**Notes:**
- Per night: date, venue, and for each set: time, combo, member names, emails, liaison, supervisor, first-year tag.
- A ready-to-paste **emails cell**: every student playing that night, joined with `; ` (pastes straight into
  Outlook's To field), plus a separate one for that night's supervisors (Cc).
- Where: a **Nights** sheet in `Schedule.xlsx` (one block or row per night), and maybe a page per night in a
  separate PDF. Names come from `scheduler_data.json` (corrected in the Combos tab).
- Must follow **swaps**: rebuild it from the Schedule sheet as it is on disk (e.g. in `solve.py --stats`, or the
  app's "Check after swaps" button), not only when the schedule is first made.
- Related to #3 (semi-automatic emails): same data, so build them together.

---

## 12. One-click app for the director

**Done (2026-10-04):** `scheduler_app.py` (tkinter window: Check inputs / Make schedule / After edits: check +
rebuild PDF) and launchers for Windows, Mac and Linux, which set up a private Python environment in the home
folder on first run. Tested on Linux with fake data (actions and window).

**Still to do:**
- [ ] Try it on a real Windows computer and a real Mac (ideally the director's), from the synced OneDrive folder.
  Things to watch: the Mac "unidentified developer" block (right-click > Open), the Windows Store "python" stub
  (the launcher prefers `py`), and OneDrive syncing the `.command` file without its run permission (if so:
  `chmod +x "Make Schedule.command"` once).
- [ ] Maybe later: a no-install version (PyInstaller builds per platform, e.g. built automatically on GitHub).

---

## 13. Swaps

**Stage 1 done (2026-10-04):** the app's Swaps tab (`swap_panel.py`, `core/swaps.py`): pick a combo's show, see every
legal trade / move / reorder best first with side effects, apply with a backup and an automatic PDF rebuild.
Defaults: soft-rule side effects allowed with a warning; losing a combo's only supervised night blocked; no
three-way swaps.

Also done: a **Schedule tab** (nights and sets incl. pending changes, jump to swaps, who could take an open set, Export PDF).
Also done: changes are collected as **pending** and saved together with **Confirm changes** (Swaps or Schedule tab; one backup, PDF rebuilt in the background). Run's step 3 is now a check only.
Also done: **give it away** (to another combo, or leave it open; only when not needed) and **claim an open set**.

**Next:**
- [ ] Stage 2: a Swaps sheet in `Schedule.xlsx`, written by Apply (date, combos, from -> to, reason, who), for a
  history and for "your show moved" emails (#3, #11). Add a reason field to the Swaps tab.
- [ ] Maybe: "move the supervision too" when a swap would take a combo off its only supervised night.
- [ ] Maybe (Stage 3): a swap-request form + flow + table, shown in the Swaps tab as an inbox (legal / not legal,
  Apply).

---

## Ideas for later
- **Swaps feature:** students currently swap among themselves and the swap is recorded in `Schedule.xlsx`, then
  checked with `solve.py --stats`. Could become: suggest valid swap partners for a combo, or a simple swap request form.
- **Supervisor names sheet:** see #2; also needed for correct names in `Combos.pdf`.
- **Duplicate student names:** two students with the same name look identical in the PDFs (emails aren't shown).
  Could add a hint only when names clash.
