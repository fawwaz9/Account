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


## D9. The policy for shared tables: a named allowlist, read with an identity, written by nobody but the owner (2026-10-06)

Item 1, built as the plan's fact A describes, with one change, marked below.

**What `rls.py` now does for a table on `SHARED_READ_TABLES`:**
- **The policy is `FOR SELECT TO account_app`,** and nothing else. Under
  row-level security a command with no policy is refused, so every write fails.
- **The grant is `SELECT` only.** Install also revokes `INSERT`, `UPDATE`,
  `DELETE`, `TRUNCATE`, `REFERENCES` and `TRIGGER` from the app role, so a grant
  left over from an earlier shape of the table, or made by hand, is taken back. A
  write is refused twice: by the grant, then by the policy.
- **Every other grantee loses everything:** `PUBLIC`, and any role granted by
  name. That covers Supabase's `anon` and `authenticated`. It matters more here
  than for per-user tables, because Supabase's default grant includes
  `TRUNCATE`, and **row-level security does not cover `TRUNCATE`.** It is the
  same lockdown the definer functions got in Phase 0 D11.
- **The generator refuses mistakes.** If a table on the list has a `user_id`,
  or an owning parent, or is `users`, it raises rather than sharing every
  user's rows in it. A name on the list with no model behind it also raises. An
  ownerless table not on the list still raises, as before.

**The change from the plan: `USING (account_current_user() IS NOT NULL)`,
not `USING (true)`.** A query that hasn't said who it is still sees no rows,
which is the fail-closed rule every other table follows. It costs nothing,
because every catalogue read happens inside a signed-in request.

**The isolation walk now covers shared rows.** Both worlds get one catalogue
course and one prerequisite. Any request that changes either fails the walk as
`SHARED WRITE`, which is item 2's "no route writes them". On Postgres it runs
again as the app role.

**Evidence:**
- `tests/test_shared_tables.py` covers the generator's rules and runs
  everywhere.
- `tests/test_rls.py` has six new Postgres tests:
  - The app role holds exactly `SELECT`.
  - A leftover `GRANT ALL` is taken back.
  - Each of five writes (insert, update on each table, delete, truncate) is
    refused with the rows unchanged.
  - Both users read the same rows.
  - Supabase's grants to `anon` and `authenticated` are modelled, and both end
    with no privilege.
  - A stray login with `GRANT ALL` can neither read nor truncate.
- **Mutation check:** each guard was removed in turn, and every removal was
  caught (restored in a `finally` each time). Two are checks in the generator,
  caught by `test_shared_tables.py`:
  - the names on the list are real tables
  - a listed table has no owner

  The other six are database rules. Each was also caught by a Postgres test
  alone, with the generator tests left out:

  | Guard removed | Caught on Postgres by |
  |---|---|
  | `SELECT`-only grant | `test_the_app_role_may_only_read_shared_tables` |
  | revoking writes from the app role | `test_a_write_grant_left_on_a_shared_table_is_taken_back` |
  | locking out other grantees | `test_supabase_default_grants_on_a_shared_table_are_taken_away` |
  | revoking from `PUBLIC` | the same |
  | `SELECT`-only policy | `test_every_table_has_row_security_and_a_policy` |
  | needing an identity to read | `test_no_identity_sees_no_rows_at_all` |

  **Correction, kept in place:** the first Postgres mutation run hung. The test
  seed read its ids after committing, which left a transaction holding a lock,
  and `rls.install`'s `ALTER TABLE` waited on it forever. The seed now reads
  them before the commit. The run that hung was thrown out, and that mutation
  was re-run and caught.

**What it costs or risks:**
- **Every catalogue write needs you,** through the review script (item 6).
  The plan already priced this.
- **A short window on first deploy.** `create_all` makes the tables a moment
  before `rls.install` locks them. On Supabase, `anon` holds the default grant
  in between, and the Data API is on, so for those seconds an empty table could
  be written through it. The runbook therefore reads the two tables back right
  after the schema step: both must be empty, and `anon` must hold nothing. The
  same window has existed for every table since Phase 0. It only matters here
  because a stray row would be shown to everyone.

## D10. The catalogue's two tables, built with item 1 (2026-10-06)

Items 1 and 2 were built together. The policy can't be proven on Postgres
without a real shared table, and nothing ships between them, because backend
work waits for the phase deploy.

**`catalogue_courses`** has campus, subject, number, title and credits. It is
unique on (campus, subject, number), and the campus must be `UBCV` or `UBCO`
(D7).
- **The subject is stored without the campus suffix:** `CPSC`, not `CPSC_V`.
  The campus column already says which campus it is, and
  `course_lookup.code_parts` drops the underscore when matching.
- **The number is text,** because some numbers carry a letter (`ENGL 100A`).
  `code_parts` already allows that.

**`catalogue_prerequisites`** has the course, kind, session, rule (JSON), note,
source, source text and when it was reviewed. There is one row per course, kind
and session, because the tree holds the whole condition. Deleting a course
deletes its rules.

**The syllabus's wording can't reach the shared table.** Only a row whose
source is `ubc-calendar` may carry `source_text`. A check constraint holds this,
so a review script that forgot would be refused by the database itself (D6).
**Refinement of the plan:** item 2 listed "source sentence" as a column with no
such rule.

**Rejected:**
- **One row per alternative instead of a tree:** "one of" groups would need
  their own table, and nothing queries inside a rule.
- **A foreign key from `courses` now:** that is item 3, with its own
  non-interference test.

## D11. Your course's catalogue link is computed when read; only your override is stored (2026-10-06)

**What the plan said (fact F):** a nullable `courses.catalogue_course_id`,
filled in on create and on applying a syllabus.

**What I built instead:**
- **The automatic link is a match, not a stored value.** Each time it's read,
  the app matches your course by campus and code. A code with `_V` means UBC
  Vancouver and `_O` means UBC Okanagan. A code with no campus suffix matches
  only if exactly one campus offers it. An ambiguous code links nothing, the
  same rule `course_lookup` uses.
- **Only your own decision is stored,** in two new columns on `courses`:
  - `catalogue_course_id`: a catalogue course you picked by hand.
  - `catalogue_unlinked`: you said there is none.

  Either one beats the match, and both survive a change to the course's code.

**Why:** the catalogue starts empty. Nothing enters it until you approve
something in the review (item 6). A link stored at create time would find
nothing for every course made before that, and never update afterwards.
Matching on read links your course the moment the catalogue gains it, and
needs no write during a read.

**The exit criterion still reads the same:** each current course is
`matched` or `chosen`, or deliberately `none_chosen`.

**If a catalogue course you picked is later deleted,** your choice falls back
to matching, rather than leaving your course linked to nothing.

**Routes,** all under your own path, so the isolation and non-interference
walks cover them:
- `GET /grades/{u}/catalogue?q=` searches by how people type a code (`cpsc 2`,
  `221`, `cosc_o`).
- `GET` and `PUT /grades/{u}/courses/{c}/catalogue` read and set the link.

The course page gets a "Catalogue" line with Change, None of these, and Match
by code.

**Evidence:**
- `tests/test_catalogue_link.py`, 26 tests. One of them reads every grade
  figure before and after each kind of link: the dashboard, the course list,
  each course's detail and the degree audit. All are identical.
- Mutation check: all 5 removals were caught (ownership filter, ambiguity
  rule, campus filter, the chosen course must exist, "none" beats the match).
- `CatalogueLine.test.tsx`, 6 tests.

**Correction, kept in place:** the first version of the "nothing moves" test
read the degree audit from a route that doesn't exist. Both reads were the same
404, so that comparison was vacuous. It now reads `/degree/{u}`, and every read
must return 200.

**Also fixed in the tests:** the shared catalogue rows now have fixed ids, and
both non-interference databases hold them. The walk can then name a real
catalogue course in the `chosen` body, so that write path actually runs.

**What it costs:** one indexed catalogue query per link read, on the course
page only. The course list doesn't read links.

## D12. Your own prerequisites, the rule language, and met or not (items 4 and 7, 2026-10-06)

Items 4 and 7 were built together, because the course page (7) is how your own
rules (4) are entered and seen. The suggested order had 4 and 7 next to each
other anyway.

**Your rule, `prerequisite_proposals`:** an ordinary per-user table, so the
existing policy generator covers it.
- **One row per course and kind** (prerequisite or co-requisite). The tree
  holds the whole condition.
- **It applies to you at once,** and is also a proposal for the review (item
  6). Editing it puts it back to "pending", because what a reviewer saw is no
  longer what you hold.
- **What else it keeps:** the session the course was in, as UBC names it
  (`2026W`, `2027S`), when your first-year setting is filled in. And your
  syllabus's own sentence, which stays with you. The plan already said this
  (D6).

**The rule language,** `app/Grades/utils/prerequisites.py` (fact D):
- **The tree** is a course (optionally with a minimum grade), a credit count
  (optionally by subject or level), and `all` / `any` groups. It is capped at
  4 deep, 40 parts, and 12 per group.
- **A typed form, because nobody types JSON.** For example: `CPSC 210 and one
  of MATH 200, MATH 217`, `6 credits of MATH 1xx`, or `CPSC 210 with 64%`.
  `or` binds tighter than `and`, and parentheses work. The page shows every
  rule in the same form, and reading a rule back always gives the same tree.
- **Anything a tree can't hold goes in the note.** Year standing and "or
  permission" are examples. The text parser refuses such phrases with a
  reason, rather than guessing.

**Met, on track, or not met.** Your record is your courses plus equivalences,
read with the degree audit's own statuses.
- **A prerequisite counts only from a term before the course.** A co-requisite
  may also be the same term, but a course never satisfies its own rule.
- **On track** means something is in progress or planned before the course: it
  will be met if it goes to plan.
- **A minimum grade is checked when the result is known.** Transfer credit and
  equivalences carry no grade, so they meet it.
- **A course you didn't pass is not met,** and the detail says "not passed".
- **Archived courses are left out,** as the degree audit leaves them out, so
  the two pages never disagree.

**The course page:**
- **A Prerequisites panel.** Each part is ✓, … or ✗, in words as well as
  colour, with why ("CPSC_V 210 done (82%)", "3 of 6 credits"). "Not met"
  always reads "Not met, and exceptions are sometimes made" (D3).
- **Yours comes first.** The shared version sits under it, folded, labelled
  "Shared, reviewed" or "Shared, from the UBC calendar". Yours shows where it
  stands in review.
- **Removing yours asks first.** The existing check that every permanent
  delete is confirmed caught that it didn't.

**Adding a course to a current or future term** previews the shared rule its
code matches. Where it's unmet, the dialog says so, and adds "You can still add
it". The Add button is never disabled.

**Which shared rule is used:** the latest one at or before the session your
course was in. If none is that old, or the session is unknown, the latest one.
That's fact C, applied to the course page.

**Evidence:**
- `tests/test_prerequisites.py`, 73 tests. They cover the language, met or not
  in every case above, yours against the shared one, picking the session, a
  transfer credit and an equivalence. One test edits, re-terms and grades a
  course whose rule is unmet: nothing is refused (item 7's "Done when").
- Mutation check: 12 removals. 11 were caught. The 12th ("a course doesn't
  meet its own rule") was missed, so a test now covers it, and that mutation
  was then caught.
- Frontend: `PrerequisitesPanel.test.tsx` (7) and
  `PrerequisiteWarning.test.tsx` (3).
- The isolation and non-interference walks cover the four new routes.

**Not done here:** reading prerequisites from a syllabus (item 5), and the
review that shares a rule (item 6).

## D13. The owner review is a script you run; it shows counts and shares only the tree (item 6, 2026-10-06)

`scripts/catalogue_review.py`, built as the plan describes, with three details
settled:

**What a listing shows.** Pending proposals are grouped by course (campus,
subject, number), kind and rule. The rule is compared as a normalised tree, not
as wording.
- **Each group shows how many different accounts proposed it.** Two proposals
  by one account count once.
- **No names, emails, ids, notes or syllabus wording appear.** A tree holds
  only codes and numbers.
- **It marks agreement and disagreement:** "N accounts agree", "disagrees with
  another proposal", "same as the catalogue". It shows what the catalogue says
  now beside them.

**What an approval writes:**
- **The catalogue course,** if it's missing.
- **The rule,** marked `reviewed-proposal`, with **no note and no wording**.
  Both are things a person typed, or their syllabus said, so neither is world
  knowledge (D6).
- **The session** is the most common one among the group's proposals. If none
  says, the script asks for `--session`.
- **An existing rule** for that course, kind and session is replaced only with
  `--replace`.
- **A code with no campus suffix** needs `--campus`.

Every proposal in the group becomes accepted. A rejection leaves the rule
applying to its author, as yours always does.

**Stable group ids.** An id is a hash of the course, kind and rule, so the id a
listing prints still names the same group when you approve it later.

**Who may run it.** It refuses `account_app`, and any role that can't insert
into the catalogue. On Supabase that leaves the tables' owner, the role the
schema step runs as. It reads other users' proposals as the owner, which
row-level security doesn't bind (D9), and prints only counts.

**Evidence:**
- `tests/test_catalogue_review.py`, 11 tests. They include the item's "Done
  when":
  - An approved rule reaches a user who proposed nothing.
  - A rejected one stays with its author only.
  - The listing contains no email, id, note or sentence.
- `tests/test_rls.py`, 3 Postgres tests:
  - The script refuses the app role.
  - It refuses a role that can't write the catalogue.
  - An owner's approval is read by another user through the app role, while
    that user still can't see the proposal itself.
- Mutation check: all 6 removals were caught (refuse the app role, refuse a
  non-writer, count accounts not proposals, replace only when asked, pending
  only, mark accepted).

**Automatic approval stays unbuilt** (D5).

## D14. The syllabus reader picks up prerequisites, and files only what you confirm (item 5, 2026-10-06)

**What changed in the reader:**
- **The prompt asks for prerequisites and co-requisites.** Each comes as a
  tree in the rule language (D12), a note for what a tree can't say, and the
  syllabus's own sentence, copied. It also asks for prerequisites only as the
  syllabus states them, never what the course usually requires.
- **Reading is lenient, like the rest of the extract.** A tree that doesn't
  hold up becomes empty, and its sentence is kept. The check screen then says
  "couldn't be read as a rule; type them in, or leave them out".
- **Nothing more is sent.** It is still only the syllabus and the term's dates.
  `test_what_is_sent_carries_nothing_about_the_person` still passes.

**The check screen** shows each rule the syllabus states, in the typed form,
editable, with a note field and the syllabus's sentence quoted beneath.
- **Confirming files a rule as yours,** with source `syllabus` and the sentence
  kept beside it, privately (D6).
- **Clearing a field files nothing.** That's the reader's existing rule:
  nothing becomes a record without confirmation (Phase 1 D16).
- **A rule that can't be read is refused** before anything is built (422).

**Adding a syllabus to a course you already have** (Phase 1 D27) offers the
same rules.
- **Where you have your own rule, the field starts empty,** and says "Yours
  stays: … Type a rule here to replace it". A syllabus never quietly replaces
  your rule.
- **Where you have none,** the field starts with what the syllabus says.

**Not counted in the no-change measure.** The measure is about assessments
(§15), and adding rule fields would change what earlier parses' figures mean.

**Evidence:**
- `tests/test_syllabus_prerequisites.py`, 17 tests. One end-to-end test runs
  read, confirm and owner approval: the shared row holds the tree with no note
  and no sentence.
- Mutation check: all 5 removals were caught (files only what was confirmed,
  the sentence kept with you, a confirmation must read, the extracted tree is
  checked, apply files at all).
- The isolation and non-interference walks now send a confirmed rule through
  both syllabus routes.
- Frontend: 5 new tests across `SyllabusModal` and `SyllabusAddModal`.

**Still bound by the owner's rule** on personal documents: no real syllabus
goes to a model until that rule is decided. Every test uses the fake adapter.
