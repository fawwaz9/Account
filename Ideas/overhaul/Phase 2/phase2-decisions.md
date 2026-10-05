# Phase 2 — decisions

Written for: you, reviewing what was decided for Phase 2 and why. Part A, the
shared course catalogue, was planned first (2026-10-05). Each
entry says what was decided, what was rejected, and what it costs. Follows
`Ideas/overhaul/template.md`.

## D1. The catalogue is a large-scale overhaul, planned with the template (yours, 2026-10-05)

**What I asked:** whether a shared course catalogue counts as large-scale.
**Your answer:** "yes".

It meets two of the template's tests:
- It **moves the isolation boundary.** It is the first table that every user
  reads and no user owns.
- It **spans several deploys,** backend and frontend.

It lives in `Ideas/overhaul/Catalogue/` rather than under a phase number,
because it cuts across Phase 1 and Phase 3. That's open question 1 in
`catalogue.md`.

**Correction (yours, 2026-10-05):** "no name it a phase for continuity, edit
the vision if you have to or combine with phase 2." The catalogue is now
**Phase 2, Part A**, in `Ideas/overhaul/Phase 2/`. See D8 for why Phase 2 and not
a new phase.

## D2. No bulk copy of UBC's calendar without UBC's written consent (from the terms of use, 2026-10-05)

**What I checked:** whether reading the whole Academic Calendar into the app is
allowed. The calendar's footer links "Terms of Use" to
[ubc.ca/site/legal](https://www.ubc.ca/site/legal.html), which covers "the
material provided under the ubc.ca domain … and several hundred subdomains". It
grants "a limited license to use (display or print) short extracts of the
information for your own personal, non-commercial use only", and says:

> "None of the information may be otherwise reproduced, republished or
> re-disseminated in any manner or form without the prior written consent of
> the University of British Columbia."

Copying the calendar into a table shown to every user is that redistribution.
Automated access as such isn't forbidden. The same page only bars an
"unreasonable or disproportionately large load".

**Decided (my recommendation; you agreed to send the request, 2026-10-05):**
- **Ask UBC.** The draft is `Ideas/overhaul/calender-request.md`.
- **Build the rest on users' own documents and typing.**
- **Import only if UBC agrees.**

**Rejected:**
- **Scraping anyway.** It breaks the terms, and the app would be redistributing
  the calendar's text to every user.
- **Waiting for manual entry alone.** About 20 users cover few courses, and
  shared rows written directly by users would spread one person's typo to
  everyone.

**What it costs:** prerequisites appear only for courses someone has brought in,
until UBC answers. **The scale it would replace:** an open-source snapshot of the
Vancouver calendar holds about 9,500 courses
([ubc-prereq-visualizer](https://github.com/AsarMichil/ubc-prereq-visualizer)).
Cost isn't the obstacle; permission is.

**Correction to earlier advice:** Phase 1 D19 recommended reading the
calendar's pages "after checking the terms of use". They are now checked, and
that recommendation is withdrawn until UBC consents.

## D3. Prerequisites are advisory, never a block (yours, 2026-10-05)

**Your words:** "prereqs are not a hard limit for the app because exceptions
are made sometimes."

So an unmet prerequisite is shown as "not met, and exceptions are sometimes
made", and no action anywhere is disabled by one. It is an exit criterion and
item 7's "Done when".

## D4. Courses and their prerequisites are shared world knowledge (yours, 2026-10-05)

**Your words:** prerequisites are "shared between all users like all courses
are."

So the catalogue is one table for everyone, not a copy per user. What you took,
and your own overrides, stay per-user (§13.3: world knowledge compounds,
personal facts never leave the user).

## D5. Every addition is approved by you, for now; automatic approval at about five people is planned, not built (yours, 2026-10-05)

**Your words:** "No not yet but add a plan to say maybe 5 different people."

During the beta, nothing enters the shared catalogue without your approval in
the review script. The plan for later is in `phase2.md` item 6: a rule is
approved automatically once about five different people have proposed the same
one for the same course. Before it's built, four things need settling:
- **Distinct accounts, and verified ones before open signup.** Otherwise one
  person with five accounts could approve anything.
- **"The same rule"** means the same structured tree, not the same wording.
- **A separate job with its own narrow role** writes the row, because the API
  can't.
- **A log you can revert from.**

The threshold is a setting, so it can move.

## D6. Syllabus prerequisites are the source for now (yours, 2026-10-05)

**What I asked:** whether to share structured facts from syllabi, with source
sentences kept private, or wait for UBC before sharing anything.
**Your answer:** "use syllabus prerequisites for now."

So:
- **Prerequisites come from the syllabi people upload,** and from what they
  type.
- **Once reviewed, the structured fact is shared;** the syllabus's own sentence
  stays with the person who uploaded it.
- **The calendar is used only if UBC agrees** (D2).

This is my reading of UBC's terms, not legal advice.

## D7. Both campuses, UBC Vancouver and UBC Okanagan (yours, 2026-10-05)

**Your answer:** "yes both campuses."

A catalogue course is keyed by campus, subject and number. The campus is a
plain `UBCV` or `UBCO` value rather than the vision's `organizations` tree
(§5.3), which can replace it when leagues need one. The calendar request asks
about both calendars.

## D8. The catalogue joins Phase 2 rather than becoming a new phase (2026-10-05)

You offered two ways to keep continuity: edit the vision with a new phase, or
combine it with Phase 2. **I combined it with Phase 2:**
- **It fits Phase 2's own test.** "Everything here needs two people or a team,
  none of it needs a cohort." One reviewed prerequisite helps everyone taking
  the course, from the second user on.
- **It is the safe half of Phase 2's sharing.** A table everyone reads and
  nobody writes comes before shared tasks, which are the first place one user
  writes another's row (§5.6).
- **No renumbering.** A new phase would shift Phases 2–4 and every reference to
  them in the vision, the ledger (§15) and the atlas (§16).

**The vision is edited to match:** §4's Phase 1 and Phase 2 entries, and a line
in "What moved". There's a backup in the scratchpad.

Part B, the rest of the vision's Phase 2, is listed in `phase2.md` but not yet
drafted.

