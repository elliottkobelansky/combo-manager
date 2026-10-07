# TODO

First real use: **Winter 2027**.

## Before Winter 2027

### Microsoft 365 (forms and flows)
- [ ] **Decision email:** after the Accept / Reject click, the approval flow emails the liaison (Cc the members and
  the supervisor) with the director's comment. Write the wording first (accepted: what happens next and when the
  schedule comes out; rejected: why, who to contact). One step can pick the text with
  `if(startsWith(outputs('Decision'), 'Accept'), '...', '...')`.
- [ ] **Conflict flow:** new conflict-form response -> add a row to `Conflicts.xlsx`, table `Conflicts`
  (Response ID | Submitted | Semester | Email | Date 1-4 | Reason | Additional Info | Status | Notes), Status =
  `Active`. Email = the typed address, or the responder's if blank.
- [ ] **First-year question** on the combo form, mapped to the First year column (the email's "Accept - first-year
  combo" button stays the main way).
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
- [ ] Show days: venues, weekdays, sets per night, minimums, set times, "supervised nights preferred here".
- [ ] Solver time: 90.
- [ ] Once real sign-ups are in: tune "Ideal days between shows" (`python app/solve.py --compare-gaps 14 21 28 35`).

### Hand-over
- [ ] **Release v0.1.0:** tag it, so the apps are on the Releases page.
- [ ] Point both flows at the shared data folder.
- [ ] Try it on the **director's** computer, including the "Open Anyway" / "Run anyway" step.
- [ ] Try **two computers** on the shared OneDrive folder at once.
- [ ] Walk the director through `Quick Start.pdf` once.

## Features

- [ ] **Check a pending combo before approving it:** a right-click **Check this combo** on a combo waiting for a
  decision, saying whether it would break a rule (members in too many combos, conflicts leaving too few nights, a
  missing supervisor...), so the director can decide in Outlook knowing that.
- [ ] **Move supervised nights** without making a new schedule: mark a night supervised or not, with the rule check
  (every combo still on one, supervised nights full, the cap), like a swap.
- [ ] **Instrument limits** in Check combos, the Combos tab and Add member (e.g. horn players in at most 1 combo,
  rhythm section in at most 2), set by group on the Semester tab. Open questions: count all of a student's combos
  or only those on that instrument? Voice and Other: what limit?
- [ ] **Summary wording:** what to call the person at a supervised night (professor, supervisor, "combo cop"...), and
  use the same word everywhere: the night and swap summaries, the tabs, the PDFs. Today it's a mix.

## Later (ideas)

- **Ready-to-send emails** once the schedule is final (per combo: its dates, the swap policy, contacts).
- **Swap requests:** a swap-request form shown as an inbox in the Swaps tab.
- **Supervisors:** which professor attends each supervised night, and their availability.
- **Messy form entries:** point out member entries that aren't emails ("TBD", a name alone), domain typos, and the
  same person under two addresses.
- **Warnings** when an approvals row changes after the combo was edited in the app.
- **Night changes on an existing schedule:** add a night as open sets, or cancel one and name the combos that lose a
  show; change a night's times or venue.
- **Instruments:** venue rules (no drum kit at a venue), counts per instrument in `Combos.pdf`.
- **Web app** after Winter 2027, if it's worth it.

## Decisions (so they aren't re-opened)

- Each combo gets the same number of shows; leftover sets stay open for volunteers.
- The schedule is made once and not re-solved; students swap among themselves (Swaps tab).
- Edits made in the app live in the app's own files; the approvals spreadsheet is never written to.
- Approving stays in Outlook (it closes the request and will send the decision email).
- The name is **Combo Manager**.
