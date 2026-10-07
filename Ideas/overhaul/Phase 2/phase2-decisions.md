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

## D15. Part B's order: safety and single-user first, signup last (yours, 2026-10-07)

**What I asked (Q1):** my order, or the vision's, which leads with teams as
the acquisition loop. **Your answer:** "your order seems good".

So Part B runs:
1. 12a, the rate limiter
2. 14, conflict flags and the tax packet
3. 10, partners
4. 9, shared tasks
5. 11, teams
6. 13, end-of-term collection
7. 12b, open signup, if it ships (Q4)

**The trade, as priced in the draft:** the growth features come last, so more
users arrive later. In exchange, every shared write lands on a policy and an
invite that are already proven. Item 13 moves earlier if a term's end comes
first.

## D16. People connect by invite link, not by email address (yours, 2026-10-07)

**Q2, your answer:** "yes". An invite is an unguessable token in a link that
the inviter sends themselves (B2). It needs no email service, and it never
reveals whether an address has an account. Tokens expire after 7 days, the
inviter can revoke them, and they are looked up through a definer function
that returns only what the invite is for.

## D17. A shared task goes when its owner's account goes (yours, 2026-10-07)

**Q3, your answer:** "yes it goes away". When an owner's account is purged,
their shared tasks and events are deleted for every member, by the same
cascade that deletes everything else they own. A member's account going
removes only their membership. **Rejected:** passing the task to a member,
which is an ownership transfer nobody asked for.

## D18. The rate limiter reads one trusted forwarded entry, behind a switch you flip after a logged check (item 12a, 2026-10-07)

**The problem:** the limiters key on the peer address, and behind Cloud Run
that is the platform's proxy. So sign-in and sign-up throttling is one budget
shared by everyone (vision §4).

**What decides the fix:** which `X-Forwarded-For` entry can be trusted. Each
proxy appends the address it saw, so a caller can write anything at the left
end, and only the right end is written by Google's front end.
- **Google's own page** on request headers says only that the first entry is
  "generally" the client, which is the forgeable end.
- **The one public report** of a Cloud Run deployment
  ([markgoho/mbu#296](https://github.com/markgoho/mbu/issues/296)) reasons the
  same way, but never logged a real request.

**So the code doesn't guess the number of proxies. It reads it from a setting,
and the setting is confirmed against production:**
- **`TRUSTED_PROXY_HOPS`:** count that many entries in from the right and use
  that one. Never the leftmost, never "the first public address".
  `client_address.py` replaces `client_of` in `auth.py`.
- **`0`, the default, ignores the header,** exactly as before. So deploying the
  code changes nothing.
- **Anything that doesn't hold up falls back to the peer:** no header, too few
  entries, or an entry that isn't an IP address. Falling back can only merge
  callers into the shared budget, never hand anyone a fresh one.
- **You set `1` on Cloud Run, then send one sign-in carrying a forged header.**
  The audit line's `client=` must equal Cloud Run's own logged `remoteIp` for
  that request, and must not be the forged address. If it's wrong, set it back
  to `0`, which is instant. If it shows a Google address instead, the front end
  appends a second entry, and the answer is `2`. Runbook, 12a batch.

**Rejected:**
- **Trusting the leftmost entry,** the common mistake. It gives an unlimited
  supply of fresh throttle keys.
- **Hard-coding `1`.** Unconfirmed, it is either right or a silent bypass, and
  a setting confirmed in production costs nothing more.

**Evidence:** `tests/test_client_address.py`, 13 tests, through the real
sign-in route:
- With the switch on, two callers get two budgets.
- A new forged address on every request still hits the same budget.
- With the switch off, behaviour is unchanged.
- Mutation check: all 4 removals were caught (rightmost not leftmost, must be
  an IP address, off means ignored, too few entries falls back).

**Unchanged, and still stated in `login_throttle.py`:** the limiters live in
each instance's memory. With up to 3 instances, a caller's budget is at most
three times the limit. That is acceptable before open signup, and to revisit
if 12b ships.

## D19. Open signup is pushed out of Phase 2 (yours, 2026-10-07)

**Q4, your answer:** "no push back". Item 12b, open signup with its
verification email and email provider, does not ship in Phase 2. **12a, the
rate limiter, still ships** (D18), because it fixes throttling for the people
already here.

**What it costs:** the Phase 2 exit criterion "registrations from outside the
invited group retaining at week two" can't be met without open signup. Per the
template, it stays unticked with this decision as the reason. It isn't failed.
The invite links (D16) still bring people in: an invited address can sign up
as today, through `ALLOWED_SIGNUP_EMAILS`.

**Note for the invite links:** someone who opens an invite and whose address
isn't on the list can't create an account. When item 10 is built, the invite
page has to say that plainly, rather than fail. Adding invited addresses to
the list stays your step.

**The vision is edited to match:** a marked note on §4's open-signup bullet.

## D20. T4s are scrapped; the tax packet uses only what you record (yours, 2026-10-07)

**Q5, your answer:** "yes and we should probably scrap t4s. its the most
personal document and the privacy laws."

So:
- **The app never reads, stores or sends a T4,** to a model or anywhere else.
  That also takes them out of the open question on personal documents (vision
  §10).
- **The tax packet (item 14) is built from your recorded paycheques,** shifts
  and tips. Its per-employer totals are sums of what you entered.
- **It says so on the page:** "From what you recorded. Check it against your
  T4s; this is not tax advice."

**The vision is edited to match:** §10's open question, §13.11's tax packet,
§13.12's document list (struck through, with the reason), and the atlas row.
There's a backup of the vision in the scratchpad.

## D21. Shifts near exams, and the tax packet from recorded pay (item 14, 2026-10-07)

**Shift-versus-exam flags.** `conflict_service` reads the calendar's own
occurrences, so it agrees with what the calendar shows: repeating shifts,
skipped dates and blackouts included. It writes nothing; Jobs reading the
calendar is the allowed direction (§13.11).
- **Overlap:** a shift shares any time with a midterm or final.
- **Crowds:** a shift ends before the exam, but by less than your buffer.
  - The buffer is a new preference, "Keep clear before an exam", default 12
    hours, in Settings under Calendar. 0 flags only real overlaps.
  - It is stored in the preferences JSON, so there is no schema change.
- **Overnight shifts** (22:00–02:00) end the next morning.
- **Untimed items:**
  - An exam with no time is taken to start at 08:00, the earliest a UBC exam
    sits.
  - A shift with no times runs all day.
  - Both can only flag more, never hide a clash.
- **Only exams are checked.** Lectures, labs, deadlines and your own events
  near a shift are not flagged.
- **Shown on the Jobs page and the Calendar page,** as one "Shifts near exams"
  panel looking 60 days ahead. It says nothing when there is nothing to flag.
  It is a page-level panel rather than a mark on each card in the month and
  week grids, which say the same thing at a fraction of the wiring.

**The tax packet.** One calendar year, from recorded paycheques (by the date
the cheque arrived), shift tips, and tuition payments (by their own payment
date). Never from a T4 (D20).
- **Per employer:**
  - gross pay and the number of cheques
  - deductions, sorted by name into income tax, CPP and EI; anything else
    keeps its own name
  - net pay, cash tips, and tips through payroll
- **Totals,** plus tuition paid.
- **It says:** "Check it against your T4s and your school's tuition slip; this
  is a summary for your records, not tax advice."
- **The year defaults to last year before May,** when people are filing.
- **The route takes `calendar_year`, not `year`,** because everywhere else in
  the API a year is a school year (1–10). The isolation walk was taught the
  new name.

**Evidence:**
- `tests/test_shift_conflicts.py`, 25 tests. One checks that the packet's
  totals equal the year's recorded paycheques, with cheques from the years
  either side excluded (the item's "Done when").
- Mutation check: 9 removals. 8 were caught. The 9th ("only exams count") was
  missed, so a test now covers it, and that mutation was then caught.
- Frontend: 5 tests across the two panels. The existing Settings test that
  pins which keys each tab saves now includes `exam_buffer_hours`.

## D22. Accountability partners: your figure in your own row, read across a mutual pair (item 10, 2026-10-07)

The first feature where one person sees something of another's. Built on
invite links (D16). It narrows the draft in one place, marked below.

**What a partner sees:** two numbers, and a date.
- **The share of this week's due tasks you've done.**
- **Your run of good weeks,** meaning 80% or more done, counted back up to 26
  weeks. A week with nothing due neither breaks nor extends a run.
- **As of when.**

Never a task's name, a grade or money (vision §13.7).

**Where it lives (the change from the draft):** the draft had a scheduled job
write a shared partnership row. Instead:
- **Each person has their own `partnerships` row.** It is ordinary per-user
  data under the usual policy, and holds *their own* figure.
- **Only you write your figure,** whenever you open the Partners panel.
- **Your partner reads it through `account_partner_figures()`.** That
  function returns the numbers only while both rows point at each other.

So no job reads across users, and no row is ever written by anyone but its
owner. The one exception is `account_accept_partner_invite`, the only thing
that writes a row for someone else: both sides, together, for the signed-in
caller and the invite's owner.

**The four functions,** each `SECURITY DEFINER`, revoked from everyone but
`account_app`, and keyed on `account_current_user()`, never on a parameter:
- **`account_invite_preview(hash)`** returns the inviter's display name, for a
  live invite.
- **`account_accept_partner_invite(hash)`** returns a status word: `accepted`,
  `invalid`, `own` or `already`.
- **`account_end_partnership(partner)`** lets either side end it, and removes
  both rows.
- **`account_partner_figures()`** returns three numbers per mutual partner.

**Invite links:**
- **Only a SHA-256 of the token is stored.** The token is shown once, in the
  link.
- **The token rides in the link's fragment** (`/invite#…`), which browsers
  never send to a server. It reaches the API in request bodies, so it stays out
  of URLs and logs.
- **Each link works once, for 7 days,** with at most 5 open per person. They
  can be cancelled.
- **Sign-in now returns you to the page that sent you there,** so a link
  opened while signed out survives. Only same-site paths are followed, so this
  is no open redirect.

**What one person sees of the other:** a name copied when the partnership
starts (B3), never an email.

**When an account is purged,** the partner's mirror row goes by the
database's `ON DELETE CASCADE`. Under row-level security the purge can't see
it, and a referential action is the one thing row security doesn't block.

**For your step (D19):** someone invited must be able to sign in. Until open
signup, their address has to be on `ALLOWED_SIGNUP_EMAILS`.

**Evidence:**
- `tests/test_partners.py`, 20 tests, run on both SQLite and Postgres, because
  each cross-user step has a function path and a plain-query path.
- 5 new Postgres proofs in `test_rls.py`:
  - Accepting as the app role writes both sides.
  - The app role can't insert a row for someone else.
  - Figures are read only across a mutual pair.
  - A stranger can't end someone's partnership.
  - With no identity, all four functions do nothing.
  - An outsider role can't call any of them.
- The walks seed a partnership between A and B. A partner's row naming the
  other is marked as the one deliberate cross-link, and B's own text in it is
  checked never to reach A.
- **Mutation check:** 7 removals across the SQL and its SQLite twin.
- **Correction, kept in place:** 3 of the 7 were missed on the first run, and
  each exposed a test that wasn't testing what it claimed:
  - The no-identity test passed the raw token where the function takes its
    hash, so it found nothing either way.
  - The mutual-pair tests deleted the partner's own row, which removes the
    data in question, instead of the reader's.

  All three tests now check the real case, and all 7 mutations are caught.
- Frontend: 10 tests (the panel, the invite page, the sign-in return path).
