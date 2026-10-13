# Phase 3 — decisions

Written for: you, reviewing what was decided for Phase 3 and why. Each entry
says what was decided, what was rejected, and what it costs. Follows
`Ideas/overhaul/template.md`.

## D1. Phase 3 opens before Phase 2 closes, with the tracker (yours, 2026-10-12)

**What I asked:** the tracker is Phase 3 in the vision, and Phase 2's exit
criteria aren't met yet. Open Phase 3 with it, or build it outside the phases?
**Your answer:** open Phase 3 with the tracker.

Why it holds:
- **Phase 2's remaining criteria need use, not code.** Five active teams, a
  partnership surviving a month, outside registrations (deferred, D19), and
  moderation load. No build closes them, so holding Phase 3 until they're met
  would only hold up a feature that needs none of them.
- **The tracker needs no density.** The vision says it "can ship as soon as the
  phase opens".
- **It is large-scale by the template's own test.** It spans backend and
  frontend, adds tables, and you will want its decisions to review.

**What it costs:** two phases open at once. Phase 2 stays open for its usage
criteria, ticked as they happen. The density features of Phase 3 (Part B) still
wait on contributors, so opening the phase early unlocks nothing that needs
people.

**Rejected:** building the tracker outside the phases. It would lose the
decisions log and runbook the template exists for.

## D2. An application's history is kept, step by step, and its statuses include "accepted" (yours, 2026-10-12)

**Your answer:** applied, screening, interview (each round its own step),
offer, **accepted**, rejected, no reply, withdrawn.

Each change is a row in `application_steps` with its date, never an overwrite of
the status. The Sankey and "how long replies take" are both read from the
history, so overwriting would leave neither anything to read. "Accepted"
separates the offers you took from the ones you turned down; turning one down
is "withdrawn" after "offer".

## D3. "No reply" is suggested after 30 quiet days, never set on its own (yours, 2026-10-12)

An application still at applied, screening or interview, with no new step for
30 days, is flagged "no reply yet?" with one tap to mark it. Nothing changes
until you tap. **Rejected:** setting it automatically, because a figure that
moves on its own is one you stop trusting, and a late reply would have to undo
it; and no flag at all, because a forgotten application then sits "applied"
forever and inflates the waiting count.

## D4. Deadlines and follow-ups appear on the calendar, not in Tasks (yours, 2026-10-12)

Both show on the tracker and as all-day items on your calendar, the way a
shared task's due date does. Clicking one points back to the tracker. They are
not tasks: there is nothing to tick off, and the application itself is where
the next step is recorded.

## D5. An offer can carry its pay, privately (yours, 2026-10-12)

An optional amount and period (hourly, monthly or yearly) on an application,
visible only to you. Later it is what you could choose to submit to co-op
salary transparency (item 12), opt-in. Nothing reads it across users, and no
aggregate exists yet.
