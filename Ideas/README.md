# Ideas

The thinking behind Account: what it is for, how each part works, why the
decisions went the way they did, and how it got on the web.

Reviewed and brought current on **2026-09-28**. Where a file is a historical
record rather than live work, it says so in its own first lines.

---

## Start here

| If you want to | Read |
|---|---|
| Pick the project up cold | [session-handoff.md](session-handoff.md) |
| Understand how a module works, and why | [design/](design/README.md) |
| Know what to build next | [whats_next.txt](whats_next.txt) |
| **Build a feature and put it live** | **[shipping.md](shipping.md)** |
| Fix something that is broken **right now** | [ROLLBACK.md](ROLLBACK.md) |

## Everything, and what it is for

**[design/](design/README.md)** — the standing reference. An overview plus one
note per module: [grades](design/grades.md), [finances](design/finances.md),
[calendar](design/calendar.md), [tasks](design/tasks.md), [jobs](design/jobs.md),
[users-and-auth](design/users-and-auth.md), and a
[template](design/TEMPLATE.md) for the next one. These carry the reasoning behind
every decision that had a real alternative, which is what stops the next session
reversing one for looking inconvenient. **Keep them current as part of landing a
change, not afterwards.**

**[session-handoff.md](session-handoff.md)** — where the project actually is:
branch, live URLs, production row counts, and the three things genuinely left.
State only; the reasoning lives in `design/`.

**[whats_next.txt](whats_next.txt)** — what has shipped (do not re-propose it),
what is left per module, and the accumulated hard-won notes. The longest file
here and the one that grows.

**[shipping.md](shipping.md)** — the loop you run every time: build it, verify
it, deploy it, write down what is live. Ordered the way the steps actually have
to happen, and every rule in it names the day it was learned the hard way.

**[ROLLBACK.md](ROLLBACK.md)** — written to be read while something is down and
you are stressed. Commands first, reasoning second.

**[deployment.md](deployment.md)** — the 39-step runbook that put this on the
web. Steps 1–37 are done. Kept because the commands, and the seven things that
went wrong, are what you need when you change any of it.

**[plan-a-decisions.md](plan-a-decisions.md)** — every deployment choice with its
alternatives and **what would change my mind**. That last part is the point.
Several have since been tested by reality and say what happened.

**[audit.md](audit.md)** — 56 findings, tiered, each with how it was verified.
A record, not a to-do list: one item is still open. The status passes at the top
say what closed when, and three entries record fixes that were made *differently*
from what the audit recommended, with the reasons.

**[jobs-plan.md](jobs-plan.md)** — the worked example. One module planned, built
and logged across three stages, including where the plan was wrong. Finished.

**[core.txt](core.txt)** — the original brief, unedited, in the author's own
words. Six lines written before any of this existed. Kept exactly as it was.

---

## What was removed, and why

`to_do.txt`, `fix.txt` and `features.txt` are gone. Each was superseded rather
than abandoned: `fix.txt`'s findings were re-verified into `audit.md` (including
seven that did not survive checking, recorded so they are not raised again),
`to_do.txt` became `whats_next.txt`, and `features.txt` was a day-one module tree
that had stopped being true — it never listed Jobs, a whole shipped module. Its
one surviving idea, the unbuilt Notes / Goals / Study Analytics, is recorded at
the end of `whats_next.txt`, and the tree itself is still quoted in the root
`README.md`.

A superseded document is worse than no document: it is read with the same trust
as a current one.
