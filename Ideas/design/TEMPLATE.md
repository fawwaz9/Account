# Module design template

Copy this for a new module. It is the shape `jobs-plan.md` grew into over three
stages, generalised — every heading here earned its place by being something
that went wrong, or nearly did, when it was left out.

Keep it short. A design note nobody reads is worse than none, because it looks
like the question was settled.

---

## Context

Why this exists. The problem, what prompted it, and what it should be true of
the app once it lands.

State the **decisions already taken** here, in one paragraph, before any code is
described. A reader who disagrees with a decision should be able to stop at this
paragraph rather than discovering it in the data model.

## What already exists

A table, not prose: existing thing → where it lives → what it is being used for.

This section is the one that saves the most work and is the one most often
skipped. Three of the four features in this app that came in cheap did so because
something already did most of the job — the recurrence engine, `split_income`,
`list_occurrences`. Write this section **before** designing anything, because
finding a second caller for an existing function usually changes the design.

If this table is empty, be suspicious. In a codebase this size it usually means
the search was not thorough rather than that the ground is new.

## Data model

Tables and columns, with the reasoning attached to the ones that had a choice
behind them. Say what a column means, not what type it is — the type is in the
model.

Two things to be explicit about:

- **Why a value is stored rather than derived.** Every stored derived value is a
  chance for two things to disagree. It needs a reason: usually that it records
  what was true at a moment (`expected_gross`, `credits_counted`) rather than
  what is true now.
- **What identifies a row** when it is not an id. A recurring thing expanded on
  read has no row per occurrence, so something like `(event_id, on_date)` is the
  identity, and that has to be said or someone will add a duplicate.

## Stages

Break anything larger than a few days into stages that each land working.

A stage that cannot be shipped on its own is not a stage, it is a checkpoint,
and it will be merged half-done. The test is whether the app is better with the
stage and without the rest.

Per stage: what it adds, what it touches, and its tests.

## Tests

List the assertions, not the test names. An assertion you can read is one you
can argue with before it is written.

Include, specifically, the ones that would **fail silently** — the case where a
wrong answer still looks like an answer. Those are the tests worth naming in a
design document; the obvious ones will get written anyway.

## Verification

Beyond the suite. What convinces you it works on real data.

The recurring items in this project:

- the full suite passes, with a count so a regression is visible
- migrations tested against a **copy** with the new columns dropped first
- mutation-test each guard: revert it, confirm the named test fails
- `tsc --noEmit`, a build, and every new CSS class confirmed in the bundle
- an end-to-end run on a copy of the real database, printing figures to check
  by eye

## Notes

Anything a person picking this up would otherwise learn the hard way. Short
bullets. This is where the project's accumulated scar tissue goes.

## Progress

Appended as stages land. Per stage: what was built, and — the valuable part —
**what the plan got wrong**. Every stage of Jobs turned up something the design
had not anticipated, and those notes are worth more afterwards than the original
plan was.
