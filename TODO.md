# TODO

First real use: **Winter 2027**.

## Before Winter 2027

### Microsoft 365 (forms and flows)
- [ ] **Decision email:** after the Accept / Reject click, the approval flow emails the liaison (Cc the members and
  the coach) with the director's comment. Write the wording first (accepted: what happens next and when the
  schedule comes out; rejected: why, who to contact). One step can pick the text with
  `if(startsWith(outputs('Decision'), 'Accept'), '...', '...')`.
- [ ] **Form texts:** finish both forms' instructions. Keep the words the app looks for in the table headers
  ("Response Id", "Semester", "Liaison", "Members", "Supervisor", "First year", "Status") and the conflict form's
  questions ("Semester", "Email", "Date"). Semester = a choice question (must match the Semester tab exactly).
  Say: conflicts only if you have some; McGill students use `@mail.mcgill.ca`, others any address but the **same**
  one on both forms; the first member listed is the liaison.
- [ ] **Test** with a few submissions (including a Gmail member, and the conflict form from outside McGill), run
  Check combos, then delete the test rows.
- [ ] **Document who can approve:** how to add (and remove) a person on the approval flow's approver list. Put it in
  the Quick Start.
- [ ] **Ownership:** forms, flows and the two spreadsheets owned by a shared account or with co-owners, so nothing
  stops when one person leaves. Write down who has access.

### Winter 2027 settings (Semester tab)
- [ ] Semester name, first / last show day, skip dates (reading week, holidays; the defaults are placeholders).
- [ ] Show days: venues, weekdays, sets per night, minimums, set times, "feedback nights preferred here".
- [ ] Solver time: 90.
- [ ] Once real sign-ups are in: tune "Ideal days between shows" (`python app/solve.py --compare-gaps 14 21 28 35`).

### Hand-over
- [ ] **Release v0.1.0:** tag it, so the apps are on the Releases page.
- [ ] **Windows:** run the newest build on your own PC (Extract All, then the .exe in the folder): the fix for
  "DLL load failed while importing cp_model_helper" passed GitHub's check but not yet a real PC.
- [ ] Try it on the **director's** computer, including the "Open Anyway" / "Run anyway" step.
- [ ] Try **two computers** on the shared OneDrive folder at once.
- [ ] **"How do I…" guide** (after the Microsoft 365 items): one or two pages next to the Quick Start, by task,
  2–4 lines each: a combo wants another date (swap / give away / claim); a combo drops out or a member changes;
  undo a mistake (Earlier versions...); a new semester (or back to an old one); lock the final schedule; let a
  coworker approve combos; something looks wrong (Check combos / Check schedule, who to contact). Link it in the README.
- [ ] Walk the director through `Quick Start.pdf` once.

## Features

- [ ] **Guitarists:** rhythm section or not, for "Warn: combos per rhythm player"? (Today: rhythm section, with
  piano, bass and drums.)

## Later (ideas)

- **Schedule email per combo** once the schedule is final (its dates, the swap policy, contacts), as a third email
  template. (The reminder and change emails are done.)
- **Faculty availability:** which nights each faculty member can attend, offered when picking one. (Picking a
  faculty member per feedback night is done.)
- **Messy form entries:** point out member entries that aren't emails ("TBD", a name alone), domain typos, and the
  same person under two addresses.
- **Warnings** when an approvals row changes after the combo was edited in the app.
- **Night changes on an existing schedule:** add a night as open sets, or cancel one and name the combos that lose a
  show; change a night's times or venue.
- **Instruments:** counts per instrument in `Combos.pdf`.
- **Web app** after Winter 2027, if it's worth it.

## Decisions (so they aren't re-opened)

- Each combo gets the same number of shows; leftover sets stay open for volunteers.
- The schedule is made once and not re-solved; students swap among themselves (Swaps tab).
- Edits made in the app live in the app's own files; the approvals spreadsheet is never written to.
- Approving stays in Outlook (it closes the request and will send the decision email).
- Feedback nights (a faculty member attends); each combo's own professor is its coach. The form's "Supervisor"
  column keeps its name.
- First-year combos are marked when approving ("Accept - first-year combo"), not by a question on the form.
- The name is **Combo Manager**.
- Feedback nights stay where the schedule put them (every combo is on one, so moving one strands its combos): when a
  faculty member can't come, pick another. (A Move feedback night version is on the `feedback-moves` branch.)
