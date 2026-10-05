# Template — large-scale overhauls

The pipeline Phase 0 ran (2026-10-04 to 2026-10-05), written down so every
large-scale overhaul runs the same way. Phase 0's own files are the worked
example: `Phase 0/phase0.md`, `phase0-decisions.md`, `phase0-runbook.md`.

---

## When to use it

Use this template for **large-scale** work. Something is large-scale when **any**
of these holds (confirmed by the owner, 2026-10-05):
- It is a phase of `account-vision.md`, or a slice of one with its own exit
  criteria.
- It changes the production schema in more than an additive column, or changes
  roles, grants, secrets or infrastructure.
- It touches the isolation boundary: who can see which rows.
- It spans several rooms, or both backend and frontend across more than one
  deploy.
- It will take more than a few days, or produce decisions the owner will want to
  review later.

Everything smaller is a normal feature: build it, ship it, and record it in
`shipped.md` and `next.md`.

**When it isn't clear which side something falls on, ask the owner before
starting.** That is the owner's standing instruction. A small feature buried in
this process is slower for no gain. An overhaul run as a feature loses the
decisions log and runbook the owner relies on to review work done while they're
away.

---

## The folder

```
Ideas/overhaul/
  template.md                  this file
  Phase N/
    phaseN.md                  the plan and its status
    phaseN-decisions.md        every decision, written as it is made
    phaseN-runbook.md          the production steps, in order
```

The vision is the source; these files are where it is brought up to date and
carried out.

---

## The pipeline

### 1. Draft the phase document from the vision

Write `Phase N/phaseN.md` using the skeleton at the end of this file.
- **Bring it up to date before planning.** The vision is a snapshot. Check every
  item against the code as it stands and mark what has since shipped or partly
  exists. Phase 1's draft found four of its items already done.
- **List the facts to settle** for each item: what must be true, or decided,
  before building. Phase 0's included which role the API connects as, the pooler
  mode, and the fact that SQLite has no row-level security.
- **Pull the cross-cutting decisions out**, so they are made once rather than per
  item. Examples: the first LLM, file storage, the first non-per-user table.
- **Give each item a "Done when"** that can be checked, not just felt.
- **Record what the vision got wrong or what has moved,** so the vision can be
  corrected.

The owner reads this draft before work starts.

### 2. Work on a phase branch

- Create a `phaseN` branch from `main`. CI runs on every push to it.
- **Frontend-only items may ship early.** Cherry-pick them to `main` when
  they're done, as Phase 0's onboarding checklist did. A later rebase drops the
  duplicate automatically.
- **Backend changes wait for the phase deploy,** or for the owner's go-ahead.
  That rule doesn't change for an overhaul.

### 3. Build safety first, and prove the invariants

The order inside a phase puts whatever closes a data-safety gap ahead of
measurement and features (`data-safety` rule; Phase 0's suggested order).

Tests prove invariants rather than examples:
- **Enumerate rather than list.** Walk every route from `app.routes`, and fail on
  a route with no case. A hand count misses one in ten.
- **Mutation-test the safety-critical lines.** Remove each guard in a scratch
  copy, and confirm a test fails. A run that errors rather than fails is invalid
  and doesn't count as caught. Always restore in a `finally`.
- **Guard against vacuous passes.** Assert that the test actually exercised
  something, for example that rows existed and requests returned 2xx before
  checking the leak.
- **Prove database-level rules on Postgres.** SQLite can't. CI's
  `backend-postgres` job runs them, and a step fails if they were skipped.
- **Model the production platform, not just Postgres.** Supabase grants every new
  function and table to `anon` and `authenticated` by name. A test against plain
  Postgres missed that in Phase 0 (D11).

Never run anything against `data/app.db` or production to "check". Use a copy, or
a throwaway container.

### 4. Keep the decisions log as the work happens

`phaseN-decisions.md`, one entry per decision: **D1, D2, …**. Each entry says:
- **What was decided,** and the alternatives rejected.
- **Why,** in terms the owner can disagree with.
- **What it costs or risks,** with any trade of safety for speed named and priced.
- **Corrections in place.** When a claim turns out wrong, say so in the entry
  rather than quietly editing it. Phase 0's D1 corrected a mutation result.
- **Owner calls as decisions too.** For example, Phase 0 D12: a criterion
  deferred, with the reason.

Write each entry when the decision is made, not at the end. It is how the owner
reviews work done while they're away.

### 5. Write the runbook before anything production-side

`phaseN-runbook.md` puts the production steps in order. Each step says:
- **What it changes,** and whether the live app notices.
- **The exact commands,** copy-paste ready. Secrets are read with `read -rs`,
  never echoed, never put in shell history, and **stored without a trailing
  newline** (`printf '%s'`, or `print(..., end="")`). Phase 0's push went down on
  a newline.
- **How to verify it,** including a negative control (a made-up route should 404,
  a wrong secret should get 403).
- **How to undo it,** and whether undoing is instant.

**The order** is pre-flight and backup, then roles, then schema, then API, then
frontend, then switches (connection, secrets, schedulers). Each step leaves the
live app working if the next one never happens.

**Mark the owner-only steps.** Creating roles, granting permissions, creating
secrets and changing shared infrastructure are done by the owner, or need their
explicit permission rule. Give them step-by-step instructions rather than
assuming the steps can be automated.

### 6. Deploy, step by step, verifying each one

The owner says "deploy". Backend deploys always need that go-ahead.

1. **Pre-flight, read-only.** Check the catalog: table owners, roles, current
   state. Take a backup.
2. **Schema.** Apply it. Then **read production back**: the grants, the policies,
   and who else can reach what. Don't trust that the code did what the tests
   said.
3. **API.** Push `ship`. The workflow runs a backup, the schema gate, a smoke
   test, a digest check, health and CORS. Then probe the new routes against a
   404 control, and read the logs.
4. **Frontend.** Push `main`. Byte-compare the live files with a local
   production-URL build.
5. **Switches.** The owner runs them; then read the logs for errors and confirm
   real traffic succeeds.

Stop at any step that doesn't verify. Nothing later depends on hurrying.

### 7. After each deploy

- Record it in `Ideas/shipped.md`: what shipped, the evidence, the revision, and
  what isn't live yet. Close its `Ideas/next.md` entries.
- Update `Ideas/ROLLBACK.md`: the current and previous revisions, and **anything
  that must be undone before rolling back**. In Phase 0 that was switching the
  database login back before any pre-phase image.
- Prune local Docker images. The registry copies are the rollback path, so keep
  them.

### 8. Close the phase

- Tick each exit criterion with its date and evidence.
- A criterion deferred by the owner stays unticked, with the reason, and gets a
  decision entry.
- Update the status table, then draft the next phase from this template.

---

## Skeleton: `phaseN.md`

```markdown
# Phase N — <name from the vision>

Taken from `account-vision.md` (§…), brought up to date on <date> against the
code as it stands. Follows `Ideas/overhaul/template.md`.

## What Phase N is for
<the purpose, and the vision's rules that apply directly>

## Exit criteria: Phase N → Phase N+1
- [ ] <from §11>
**Which of these can be read today:** <what measures each, and what's missing>

## Status at a glance (<date>)
| # | Item | Status |
|---|---|---|

## Cross-cutting facts to settle before building
<decisions shared by several items>

## 1. <Item>
**What** (§…). **What exists.** **Facts to settle.** **Trust cost**, if any.
**Done when** <checkable>.

## Suggested order
<numbered, with the trade it makes named>

## Open questions
## What the vision says that has since moved
```

## Skeleton: a decisions entry

```markdown
## D<n>. <the decision, stated as a fact>

<What was decided and what was rejected. Why. What it costs. Evidence: tests,
commits, numbers. Corrections stay in place, marked as corrections.>
```

## Skeleton: a runbook step

```markdown
## <n>. <What this step does> (<reversible? / live app affected?>)

<commands>

**Verify:** <checks, with a negative control>
**Undo:** <command, and whether it is instant>
```
