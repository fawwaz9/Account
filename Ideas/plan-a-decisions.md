# Plan A, decision by decision

Every choice in deploying Account to Cloud Run + Supabase + Cloudflare Pages, with
the reasoning, the alternatives I rejected, and **what would change my mind**.

That last part is the point. A plan you can argue with is worth more than one you
follow. Where I say "what would change my mind", that is a genuine falsifier — if
it turns out to be true, the decision should flip.

Written against `main` at `a93e54e`, when 619 tests were green. Kept current as
steps land: **740 green on SQLite, 730 + 2 skipped against Supabase itself.**

**All of this has now been run.** The app is live — steps 1 to 37 of
`deployment.md` are done and a second person is using it. The decisions below
therefore divide into three kinds, and it is worth knowing which you are reading:

- **Confirmed by doing it.** Most of them.
- **Changed by doing it.** D2.0 (Neon → Supabase, reversed after review), D2.2
  (no longer applies), D3.0 (added afterwards; Phase 0 found it and nothing else
  would have).
- **Still unfalsified, because the measurement was never taken.** D3.2's
  cold-start figure is the significant one — see the note there.

Where a decision has been tested by reality, it now says so under **What
happened**.

---

## Phase 0 — Prove the container, before touching any cloud

### D0.1 · Build and run locally first

**Decision.** `docker compose up --build` on your Mac, and do not create a single
cloud resource until sign-in works end to end against the containers.

**Why.** Two Dockerfiles, a compose file and an nginx config have been written
and never once executed. The odds that all of it is correct first time are low.
The question is only *where* you find out. Locally the feedback loop is seconds
and you have a shell; on Cloud Build it is several minutes and you are reading
logs.

**Alternative: deploy straight to Cloud Run.** Genuinely tempting, because Cloud
Run builds from a Dockerfile and you would find out either way. Rejected because
you would be debugging two new things at once — your container *and* Cloud Run's
deployment model — with no way to tell which one broke.

**What would change my mind.** Nothing, honestly. This is the cheapest step in
the plan and it de-risks every later one.

---

## Phase 1 — The Postgres port

The largest phase, and the only one that touches application code.

### D1.1 · Fix the `connect_args` bug by parsing the URL, not sniffing the string

**Decision.** In `app/_database/db.py`, use SQLAlchemy's own URL parser to decide
whether the SQLite-only connect argument applies:

```python
from sqlalchemy.engine import make_url

url = make_url(DATABASE_URL)
connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, ...)
```

**Why.** `check_same_thread` is a SQLite DBAPI argument and psycopg rejects it, so
today **any non-SQLite `DATABASE_URL` crashes at import** — which is a live bug,
since `docker-compose.yml` advertises the variable as configurable. Parsing the
URL is exact: it handles `sqlite+pysqlite://`, `postgresql+psycopg://` and
anything else without a list of prefixes to maintain.

**Alternative: `DATABASE_URL.startswith("sqlite")`.** Works today. Rejected
because it is a string guess about a structured value, and it silently does the
wrong thing for a driver-qualified URL you have not thought of.

**Alternative: check `engine.dialect.name` after construction.** Too late —
`connect_args` has to be passed *into* `create_engine`. The pragma hook a few
lines below can do this because it runs later, which is exactly why that one was
already correct and this one was missed.

**What would change my mind.** Nothing. This is the smallest correct fix.

### D1.2 · Use `psycopg` (version 3), not `psycopg2`

**Decision.** Add `psycopg[binary]` and use `postgresql+psycopg://` URLs.

**Why.** It is the current generation, actively developed, and first-class in
SQLAlchemy 2.0 which this project already uses. The `[binary]` extra ships
prebuilt wheels, so there is no compiler needed in the Docker build.

**Alternative: `psycopg2-binary`.** Far more StackOverflow answers and tutorials
assume it, which genuinely matters when you are learning. Rejected because it is
in maintenance mode, and the thing you would be buying is other people's older
examples.

**Alternative: `asyncpg`.** The fastest option, but it requires an *async*
SQLAlchemy engine, and every service function in this codebase is synchronous.
That is not a driver swap, it is rewriting the data layer. Firmly rejected.

**What would change my mind.** If a dependency turned out to pin `psycopg2`, or
if you hit a psycopg3 bug and the workaround cost more than the modernity is
worth.

### D1.3 · Keep the hand-rolled migrations for now; adopt Alembic as a follow-up

**Decision.** Deploy on the existing `migrations.py`. Schedule Alembic
afterwards, as its own piece of work.

**Why.** On a *fresh* Postgres database `create_all` builds every table from the
models, so `ensure_schema()` finds nothing missing and its SQLite-shaped DDL
never executes. The port therefore does not require touching it. And there is a
sequencing argument: the Postgres move is already a large, risky change, and
bundling a migrations-framework change into the same deploy means that when
something breaks you will not know which half did it.

**Alternative — and this is the strongest counter-argument in this document:
adopt Alembic now, while the database is empty.** Migrations are never cheaper to
introduce than before there is production data. Doing it later means writing a
baseline migration that reflects an existing schema, which is fiddlier than
starting clean. If you would rather take that cost now, I think that is a
defensible call and I would not argue hard against it.

I still lean to deferring, because `create_all` genuinely does the job for the
first deploy and one risky change at a time is a good rule. But this is the
decision in this plan I hold most loosely.

**What would change my mind.** If Phase 1 turns out to need *any* schema change
that `create_all` cannot express — a column type change, a rename, a backfill —
then Alembic should come first, because you would be hand-writing migration DDL
anyway.

### D1.4 · Move the data with a Python script through the ORM

**Decision.** A script that opens both databases through SQLAlchemy, reads every
model from SQLite, and writes it to Postgres in foreign-key order. Run against a
**copy** of `data/app.db`, never the original.

**Why.** The ORM already knows the type mappings, and the important one is UUID:
`sqlalchemy.types.Uuid` stores as `CHAR(32)` on SQLite and as native `uuid` on
Postgres. A raw SQL dump would carry the SQLite representation across and produce
either type errors or, worse, valid-looking wrong data. Going through the ORM
means the conversion is the one the application itself uses.

**Alternative: `pgloader`.** Purpose-built and handles type mapping well.
Rejected mostly on learning cost — a whole tool, its config language, and its own
failure modes, for a one-time move of about 400 rows.

**Alternative: `.dump` and hand-edit the SQL.** Feasible at this size, and
instructive. Rejected because it is exactly the kind of manual transformation
where a single wrong `0` for `false` passes silently.

**Verification, non-negotiable:** count rows per table on both sides before and
after, and diff a full dashboard payload from each. A migration that "looks fine"
is how you discover a missing table in March.

### D1.6 · Reset the sequence behind the one integer primary key

**Decision.** After copying rows, advance the Postgres sequence for every
integer autoincrement primary key past the highest id copied — and derive that
list from the models rather than naming the table.

**Why.** `course_category_weights.id` is the only such column in the schema;
every other table keys on a UUID the application generates. On Postgres an
autoincrement integer is backed by a sequence, and **inserting explicit ids does
not advance it**. So the migration completes, every row count matches, every
value matches, and the database is in perfect shape — until the first person
adds a category weight, at which point Postgres hands out `id = 1`, collides
with a row that has existed since the move, and keeps colliding forever. The
table becomes permanently unwritable, and nothing about the migration report
hints at it.

Demonstrated rather than reasoned about: against a real copy, with the reset the
next insert took id 224; with the sequence left where the move found it, the same
insert raised `duplicate key value violates unique constraint`.

**Why derived rather than written down.** A hardcoded `("course_category_weights",
"id")` is correct today and silently wrong the first time somebody adds a table
with an integer key — and the consequence is invisible until a write. Walking
the metadata for integer primary keys costs four lines and cannot go stale.

**Alternative: change the column to a UUID as part of the move.** It would make
the schema uniform and remove the problem rather than manage it. Rejected as the
wrong thing to bundle into a data migration — it is a schema change with its own
risks, and it would mean the thing being moved is not the thing that was tested.
Worth doing later if the uniformity is wanted.

**What would change my mind.** Nothing about the fix. But if more integer keys
appear, the schema question above becomes worth asking properly.

### D1.5 · Make the test database configurable, and run the suite both ways

**Decision.** `TEST_DATABASE_URL` in `tests/conftest.py`, defaulting to the
current SQLite setup. Run the 619 tests against Postgres before deploying.

**Why.** **This is the actual work of the port** and the thing that makes it
safe. The suite is the only description of the app's behaviour you have; if it
has never run against Postgres, you do not know the port worked, you only know it
imported. Keeping SQLite as the default means your day-to-day loop stays fast.

**Alternative: only ever test against Postgres from now on.** More faithful to
production. Rejected because every test run then needs a live database, which
makes the fast local loop slow and the suite less likely to be run.

**What to expect.** Some failures are likely and most will be legitimate:
ordering that SQLite happened to give you without an `ORDER BY`, integer-vs-boolean
comparisons, and stricter type handling. Each one is a real latent bug that SQLite
was hiding.

---

## Phase 2 — The database

### D2.0 · Supabase, not Neon — **reversed after review**

**Decision.** Use Supabase for the Postgres database. This reverses the original
pick, and the reasoning for the reversal is more useful than the conclusion.

**Why the original pick was Neon.** Scale-to-zero symmetry: Cloud Run scales to
zero, so a database that scales to zero felt like the matching choice. That is an
aesthetic argument, not an engineering one, and it does not survive contact with
the numbers.

**Why Supabase is better here.**

| | Neon free | Supabase free |
|---|---|---|
| Compute budget | **100 CU-hours/month** (~400 wall-clock hours) | **none — always on** |
| Database cold start | wakes after 5 min idle | none |
| Pause | never | after **7 days** with no activity, manual restore |
| Provider restore | 6-hour window | **none at all** |
| Branching | yes, genuinely good | limited on free |
| Storage | 0.5 GB | 500 MB |

The decisive line is the first. **D2.2 identified Neon's compute budget as the
limit that binds before storage or requests** — the thing most likely to end
Plan A's free-ness. On Supabase that constraint does not exist. Removing your
most likely failure mode outright beats managing it.

The second line matters too: Cloud Run already has a cold start. With Neon you
stack a second one behind it, so the first request after a quiet spell wakes both.
Supabase's compute is always on, so there is only ever one.

**What Neon is better at, honestly.** Two things. Its **6-hour restore window**
is thin but real, where **Supabase free has no automated backups whatsoever** —
none, and PITR is a $100/month feature. And Neon's **branching** is genuinely
excellent for rehearsing a migration, which is exactly what D1.5 needs.

**Why that does not change the answer.** D2.5 already requires your own
`pg_dump` regardless of provider, on the grounds that a backup living inside the
system it protects you from is not a backup. If that discipline exists — and it
must — then Neon's 6-hour window is a pleasant extra rather than load-bearing.
The compute budget, by contrast, *is* load-bearing.

**What would change my mind.**
- If you will not reliably run your own backups, Neon's 6-hour window becomes
  the only safety net there is, and that tips it back.
- If the app plausibly goes **more than 7 days unused** — a summer break, say —
  Supabase pauses and needs a manual dashboard restore. Annoying rather than
  dangerous, and no data is lost, but if that is a regular pattern Neon suits it
  better.
- If rehearsing the Postgres migration on branches turns out to be how you want
  to do D1.5, Neon earns its place for that alone.

**One non-issue worth naming.** Supabase bundles auth, storage and realtime that
this app will never use — it has its own JWT, bcrypt and Google flow. That is
unused surface area, not a conflict. Use the Postgres and ignore the rest.

### D2.1 · Put Supabase and Cloud Run in the same region

**Decision.** Pick the Supabase region first, then deploy Cloud Run into the
matching one.

**Why.** Every request makes several database round trips. Cross-region adds
perhaps 50–100 ms *per round trip*, and the dashboard makes five queries — so a
careless region choice can cost half a second on a page the performance work
already got down to five queries. This costs nothing to get right and is
irritating to change later.

**What would change my mind.** Nothing, but note the constraint runs both ways:
choose whichever region is nearest your twenty users, then match the other
service to it.

### D2.2 · ~~Pin the maximum compute size to 0.25 CU~~ — **no longer applies**

**Superseded by D2.0.** Supabase has no compute-hour budget, so there is nothing
to pin. Kept here because it is the reason the provider changed — and because if
you ever go back to Neon, this becomes the single most important setting on the
account. The original reasoning:

**Why.** The free allowance is 100 **CU-hours**, not hours. At 0.25 CU that is
about 400 wall-clock hours a month against 730 in a month — workable. At 2 CU it
is 50 hours, which a real month of twenty users would exhaust in under three
days. This is the single easiest way to accidentally leave the free tier, and it
is a checkbox.

**Alternative: allow autoscaling for headroom.** Sensible on a paid plan, where
you want a traffic spike absorbed rather than queued. On the free plan it just
converts a slow minute into an exhausted month.

**What would change my mind.** Evidence that 0.25 CU is actually too small —
queries queuing under normal use. Then the honest answer is a paid plan, not a
bigger free ceiling.

### D2.3 · Use the **pooled** connection string

**Decision.** Supabase's pooled connection string (Supavisor), not the direct
one. Same reasoning as Neon's pooler — the advice survives the provider change
intact.

**Why.** This is the classic serverless-plus-Postgres failure and it is worth
understanding properly. Cloud Run runs *many independent instances*, each with
its own SQLAlchemy connection pool. Postgres has a hard connection limit. Ten
instances holding five connections each is fifty connections for what is
genuinely a handful of concurrent queries — and when you hit the ceiling, new
requests fail with a connection error rather than merely being slow. Supabase's
pooler (Supavisor) sits in front and multiplexes, which is precisely the shape
this architecture needs.

**Alternative: direct connection with a tiny pool.** Workable if you also cap
`max-instances` hard (see D3.3). Rejected as the primary defence because it makes
correctness depend on remembering a second setting.

**What would change my mind.** If you hit a feature the pooler does not support
in transaction mode — `LISTEN`/`NOTIFY`, some prepared-statement patterns,
session-level advisory locks. This app uses none of them.

### D2.4 · `pool_pre_ping=True`, and a small `pool_size`

**Decision.** Turn on pre-ping; set `pool_size` to something like 2–5 with a
modest `max_overflow`.

**Why.** The original argument was Neon's five-minute suspend killing pooled
connections. Supabase does not suspend that way, so **this is now a weaker
recommendation than it was** — but still the right default. Cloud Run instances
are themselves torn down and recreated, connections through a pooler can be
dropped at the pooler's discretion, and Supabase *does* pause after seven days.
Pre-ping costs one trivial round trip per checkout and removes a whole class of
intermittent, hard-to-reproduce error. Cheap insurance rather than, as before,
a necessity.

**Alternative: aggressive `pool_recycle` instead.** Recycles on a timer rather
than checking liveness. Rejected because you are guessing a number against a
suspend you do not control, and the failure mode of guessing wrong is the exact
error you were trying to prevent.

**What would change my mind.** Nothing. The cost is negligible and the failure it
prevents is the most likely operational problem in this whole design.

### D2.5 · Back it up yourself — on Supabase free, nothing else will

**Decision.** Nightly logical dump (`pg_dump`) to storage you control. On
Supabase this is **not optional** — it is the only backup that will exist.

**Why.** This was already the right advice with Neon, where a 6-hour restore
window gave you a thin safety net underneath it. **Supabase free has no automated
backups at all**, and point-in-time recovery is a $100/month feature. So the
consequence of skipping this step changes from "you lose more than six hours" to
"you lose everything", and D2.0 is only a good decision if this one actually
gets done.

**Alternative: rely on the provider.** There is nothing to rely on. This is the
one decision in the document with no viable alternative.

**And then restore one.** Into a scratch Supabase project — the free plan allows
two — opened with the real app. An unrestored backup is a belief.

### D2.6 · Disable prepared statements, and rewrite the URL the dashboard gives you

**Decision.** For psycopg connections, pass `prepare_threshold=None`. For a bare
`postgresql://` URL, rewrite the driver to `postgresql+psycopg` rather than
letting SQLAlchemy pick.

**Why the first.** psycopg starts using server-side prepared statements
automatically after the **fifth** execution of a query. Supavisor in transaction
mode — the pooler D2.3 chose — hands each transaction whichever backend
connection happens to be free, so the connection that issued the PREPARE is
usually not the one asked to EXECUTE it. The error is `prepared statement ...
does not exist`. What makes it worth a decision rather than a line of config is
*when* it appears: never on the first four runs of a query, so it passes every
smoke test, every manual click-through and quite possibly the first day of real
use. The cost of turning it off is re-planning each query, which at this size is
immaterial.

**Why the second.** Supabase gives you `postgresql://...` with no driver named,
and SQLAlchemy resolves that to psycopg2 — which D1.2 deliberately did not
install. Pasted verbatim, the connection string produces `ModuleNotFoundError:
No module named 'psycopg2'`, an error that says nothing about the actual problem
at the exact moment of first connecting to a real database.

**Alternative: document it and let the person edit the string.** The honest
version, and what most projects do. Rejected because the edit is invisible — the
string looks complete, and nothing about it suggests it needs changing. A
correction you have to remember is a correction you will forget at 1am.

**Alternative: rewrite any `postgresql+*` driver to psycopg.** Rejected. An
explicit `postgresql+psycopg2://` is someone stating a preference rather than
omitting one, and silently overriding it is worse than failing where they can
see why. Only the bare form is touched.

**One trap inside the fix.** `str(URL)` masks the password as literal asterisks.
Rendering the rewritten URL the obvious way produces a string that parses
perfectly and cannot authenticate — which reads as "wrong password" and sends you
to reset a password that was correct all along. It needs
`render_as_string(hide_password=False)`, and there is a test named for it.

**What would change my mind.** Moving to the session pooler or a direct
connection, where prepared statements are safe and worth keeping. The setting is
unnecessary there rather than harmful, so it would be a small optimisation, not a
bug.

---

## Phase 3 — Cloud Run

### D3.0 · Build for `linux/amd64` explicitly — **found the hard way in Phase 0**

**Decision.** `docker build --platform linux/amd64`, or a `buildx` multi-arch
manifest, for anything destined for Cloud Run.

**Why.** Your Mac is Apple Silicon, so the Phase 0 build produced `linux/arm64`
images — verified, not assumed. **Cloud Run runs `linux/amd64`.** Push what was
built locally and you deploy an image the platform cannot execute, and you find
out at deploy time rather than build time. Nothing about the successful local
build hints at this.

**This complicates D3.1 rather than contradicting it.** The point of deploying a
prebuilt image was that production runs the artefact you validated. On Apple
Silicon that is no longer strictly true: you validate arm64 locally and deploy
amd64. The gap is small for pure-Python code — but it is a gap, and it is worth
knowing it is there.

**Alternative: build on Cloud Build (`--source`).** It builds amd64 natively, so
the problem disappears. This is a real point in `--source`'s favour that I did
not credit it with when I wrote D3.1, and it makes the choice closer than I
presented it.

**Alternative: `buildx` multi-arch.** Builds both, so local and deployed images
come from one manifest. Slower, since the amd64 half is emulated — but it keeps
"the thing I tested is the thing I shipped" honest.

**What would change my mind.** If the emulated amd64 build turns out slow enough
to be annoying, `--source` becomes the better trade.

### D3.1 · Deploy a prebuilt image, not `--source`

**Decision.** Build the image, push it to Artifact Registry, deploy that.

**Why.** You will have already built and tested that exact image in Phase 0. The
thing that runs in production should be the artefact you validated, not a second
one produced by a different builder from the same source. It also makes rollback
trivial: redeploy the previous tag.

**Alternative: `gcloud run deploy --source .`** Fewer steps and genuinely nice
for a first deploy. Rejected because it rebuilds remotely on every deploy, which
is both slower and a second build environment to reason about when something
differs from local.

**What would change my mind.** If the registry setup proves annoying enough to
stall you, `--source` for the very first deploy to prove the path works, then
switch. Momentum has value.

### D3.2 · `min-instances = 0`, and accept cold starts

**Decision.** Scale to zero.

**Why.** It is the whole reason Cloud Run fits the requirements. A warm instance
bills continuously and would consume the free CPU allowance doing nothing. Cold
starts here are roughly 200 ms to 2 seconds — noticeable, not painful, and vastly
better than Render's 30–60.

**Alternative: `min-instances = 1`.** Eliminates cold starts and would be the
right call on a paid plan for a user-facing app. Rejected because it directly
contradicts "free".

**What would change my mind.** Users actually complaining. Then compare the cost
of one warm instance against the annoyance — it is not much money, and "free" was
a requirement, not a religion.

> **What happened: nothing, and that is the problem with this one.** The
> 200 ms–2 s figure above is still an estimate. **Every latency measured so far
> was against a warm container**, so the number this decision rests on has never
> been observed. No one has complained either — but at three users, two of whom
> are the author, that is not evidence.
>
> There is now also a confound: UptimeRobot polls `/health` every five minutes,
> which may be keeping the instance warm permanently. If so the cold start is
> both unmeasurable and irrelevant, which would be a good outcome arrived at by
> accident. Measuring it honestly means pausing the monitor, waiting 15 minutes,
> and timing one request — see step 38.

### D3.3 · Set `max-instances` low — **the default of 100 is a trap**

**Decision.** Cap it at something like 3.

**Why.** Two independent reasons, either sufficient. First, cost: 100 instances
is the default, and a traffic spike — or a crawler, or a bug — could burn a
month's free allowance in an afternoon with nothing to stop it. Second,
connections: every instance holds a pool, so uncapped instances means uncapped
database connections. For twenty users, three instances is already generous
headroom.

**Alternative: leave it at the default and rely on the pooler.** The pooler does
protect the database. It does nothing about the bill.

**What would change my mind.** Requests actually queuing at the cap. That is a
real signal and it is visible in the metrics — raise it deliberately, having seen
the number.

### D3.4 · Set `concurrency` to match the FastAPI threadpool, not above it

**Decision.** Concurrency around 40, not the default 80.

**Why.** This is subtle and worth understanding. Every route in this app is a
**synchronous** `def`, and FastAPI runs those in an `anyio` worker threadpool
that defaults to **40 threads**. If Cloud Run hands one instance 80 simultaneous
requests, forty of them are executing and forty are sitting in a queue *inside*
your process — where Cloud Run's autoscaler cannot see them. It thinks the
instance is coping and does not start another one. Matching the numbers means
backpressure is visible where the scaler can act on it.

**Alternative: raise the threadpool to 80 instead.** Also defensible, and it uses
each instance more fully. Rejected for now because more threads all making
database calls multiplies connections against the very limit D2.3 and D2.4 are
managing, and because the smaller number is the safer default when nobody has
measured anything yet.

**What would change my mind.** Measurement. If instances are CPU-idle while
requests queue, the threadpool is the bottleneck and should go up.

### D3.5 · Secrets in Secret Manager, not environment variables

**Decision.** `JWT_SECRET` and the Supabase connection string as secrets, mounted
into the service.

**Why.** Plain environment variables are visible in the console, in
`gcloud run services describe`, and in deploy logs — so the connection string and
the token-signing key end up in places that get screenshotted and pasted into
chat. Secret Manager also versions them, which makes rotating `JWT_SECRET` a
deliberate, revertible act.

**Alternative: plain env vars.** Simpler, one less service to learn, and for a
personal project it is a defensible shortcut. Rejected because the two values
involved are the two that matter most: one reads all the data, the other forges
any session.

**What would change my mind.** Nothing for these two. Non-sensitive config —
`ALLOWED_ORIGINS`, log level — should stay plain env vars precisely because it is
*not* secret.

### D3.6 · Accept that the login throttle weakens, and say so

**Decision.** Ship it as is, with a comment recording the limitation.

**Why.** `login_throttle.py` keeps state in process memory. With up to three
Cloud Run instances, an attacker's attempts spread across them, so the effective
limit is roughly three times looser than the constant says. That is a real
weakening — but bcrypt still costs real time per attempt, `max-instances` bounds
the multiplier at three, and the alternative is introducing a shared store to a
deployment that currently has none.

**Alternative: move the throttle to Redis or a database table.** The correct
long-term answer, and what you would do at scale. Rejected for now as the wrong
thing to bundle into a first deploy — it adds a dependency, a failure mode, and
an outage path for a service whose absence would block all sign-ins.

**What would change my mind.** Any evidence of actual credential-guessing in the
audit log, or raising `max-instances` much above three. Both make the multiplier
matter.

### D3.7 · A service account of its own, with two grants and nothing else

**Decision.** Run the Cloud Run service as a dedicated `account-api` service
account holding `secretmanager.secretAccessor` on exactly two secrets, rather
than as the Compute Engine default.

**Why.** Checked rather than assumed: on this project the default compute
service account holds **`roles/editor`**. That is what a compromised container
would be running as — able to read every secret in the project, delete the
Artifact Registry repository, and create resources that cost money. D3.5 put
`JWT_SECRET` and the database URL behind Secret Manager specifically so they
were not casually readable; running as Editor hands them straight back, and adds
the rest of the project on top.

The replacement has **no project-level roles at all**. If the container is
compromised, the attacker gets the two values the application already has in its
own memory, and nothing further.

**Alternative: use the default and move on.** One fewer thing to create, and it
is what most tutorials do — which is exactly why the default deserves checking
rather than inheriting. Three commands is not a meaningful cost.

**Alternative: grant `secretAccessor` at the project level.** Simpler to write
and grows silently: every secret added later is readable by the service without
anyone deciding that. Per-secret bindings mean adding a secret is a deliberate
act.

**What would change my mind.** Nothing for the access level. If the service
later needs to write to Cloud Storage or publish to Pub/Sub, those get their own
narrow bindings on the same account — not a broader role.

---

## Phase 4 — The frontend

### D4.1 · Cloudflare Pages

**Decision.** Pages for the static bundle.

**Why.** Free, no card, unlimited static hosting, a hostname included, and it
does not pull the rest of the stack into one vendor's orbit. The bundle is 462 KB
raw and 130 KB gzipped — any CDN handles that, so the tiebreakers are cost and
friction.

**Alternative: Vercel.** Equally good at this, and arguably nicer to use.
Genuinely close. I lean Pages only because Cloudflare is also where a domain and
tunnel would live if you ever move to Option D.

**Alternative: serve the frontend from Cloud Run too.** One fewer service, and it
makes everything same-origin, which would remove the CORS configuration entirely.
Rejected because it burns your request allowance on static files that a CDN
serves free — but note it is the option that makes D5.2 disappear.

### D4.2 · Security headers via a `_headers` file

**Decision.** A `_headers` file in the build output, since Pages serves the
static bundle and there is no nginx in this architecture.

**Why.** The audit's S1 called for headers in `nginx.conf` — but in Plan A nginx
is gone. The headers still matter and Pages implements the same thing
declaratively. Worth noticing that the *finding* survived while its *fix*
changed, which is what happens when architecture moves under an audit.

### D4.3 · `_headers` is generated at build time, not checked in

**Decision.** A Vite plugin (`securityHeaders.ts`) writes `dist/_headers`, taking
`connect-src` from the same `VITE_API_BASE_URL` the bundle is built with.

**Why.** Every directive in that file is fixed except one. `connect-src` has to
name the API's origin, and that origin is different for local development, for a
preview deploy and for production. A checked-in file can only be right for one of
them — and the failure mode for the other two is the worst kind available: the
browser refuses the request *before sending it*, so the API's logs show nothing
at all and the app simply looks down. That is exactly the shape of the CORS bug
Phase 0 found, and the lesson from that bug was that two places holding the same
address will eventually hold different addresses. Deriving both from one variable
means they cannot.

**Alternative: a static `public/_headers` with the production origin hardcoded.**
Simpler to read, and wrong for every local build. The CSP would block the dev
API, so either the file is wrong or people learn to ignore CSP errors — both bad.

**Alternative: no `connect-src` at all.** Would let the file be static. It also
removes most of the value: `connect-src` is what stops injected script from
posting your data somewhere else.

**What would change my mind.** Serving the API from the same hostname as the
frontend. Then `'self'` covers it, the directive is constant, and a plain file is
the right answer.

### D4.4 · The error boundary sits outside `AuthProvider`

**Decision.** One boundary, wrapping the provider *and* the router, rather than
one per route.

**Why.** A boundary only catches what renders **below** it. Placed inside
`AuthProvider`, it cannot catch the provider itself throwing — and "the app broke
while working out whether you are signed in" is precisely the failure a person
would otherwise meet as a white screen, since it happens before any page renders.
Outermost catches strictly more for the same one component.

**The cost, taken deliberately.** From outside the router there is no way to
offer "go back to the previous page" — the boundary has no router context. So the
actions are a hard reload and a link to `/`, both through `window.location`. A
reload rather than a state reset is also the honest choice: re-rendering the same
tree from the same props almost always throws again immediately, which reads to a
user as a button that does nothing.

**Alternative: a second boundary inside `MainLayout`.** Would keep the sidebar
alive when one page crashes, which is a nicer experience. Worth adding later; it
is an addition to this, not an alternative to it.

**What would change my mind.** Any evidence that page-level crashes are common.
Then the inner boundary earns its place, because losing only the page beats
losing the app.

---

## Phase 5 — Wiring it together

### D5.1 · The invite gate goes in the application

**Decision.** `ALLOWED_SIGNUP_EMAILS` checked in `create_local_user` — and in the
Google path too.

**Why.** Cloudflare Access was the elegant answer when everything sat on one
origin: an email allowlist in front, no code. It does not survive the split,
because Access gates a browser by *redirecting* it to a login page, and a
cross-origin `fetch` from Pages to Cloud Run follows that redirect into a
response with no CORS headers for your origin — so the call fails as a CORS error
rather than an auth prompt. Roughly fifteen lines in the app is the cheaper fix.

**Do not forget the Google path.** An allowlist that only guards
`create_local_user` leaves `POST /auth/google` wide open, and
`get_or_create_user_by_google_id` creates accounts too. Same list, both doors.

**Alternative: make Access work with `credentials: "include"` and
`allow_credentials=True`.** Possible, but it partly reverses the CORS hardening
from PR #34 and adds a cookie dimension to an app that deliberately has none.

**What would change my mind.** Serving the frontend from Cloud Run instead
(D4.1's third option). Same origin, and Access becomes viable again.

### D5.2 · `ALLOWED_ORIGINS` is exactly the Pages URL

**Decision.** The literal origin, no wildcard, no trailing slash.

**Why.** It is currently absent from both `.env` files and falls back to
`http://localhost:5173`, so **every request from the real frontend will be
blocked** until this is set. Expect to hit this; it presents as "the API is down"
and appears nowhere in the API's own logs, only in the browser console.

**A trap worth naming:** Pages gives you both a permanent URL and a per-deploy
preview URL. Previews are different origins and will fail CORS. That is correct
behaviour, not a bug — but it is confusing the first time.

### D5.3 · Add the Pages hostname to Google's authorised origins

**Decision.** Do it in the same sitting as D5.2, because they fail the same way.

**Why.** Google Identity Services checks the calling origin against the client
ID's authorised list. Miss it and sign-in fails with a message that does not
mention origins at all. It is a console setting, it takes a minute, and it is the
second most likely thing to lose an hour to after CORS.

### D5.4 · Registration counts every attempt; login counts only failures

**Decision.** `/login` records a failure and clears the key on success.
`/register` records *every* call, successful or not.

**Why.** They are guarding different things. Login protects a secret, so
succeeding proves the caller was entitled to try and there is no reason to hold
it against them. Registration has no secret to protect: what it spends is a
database row and a ~200 ms bcrypt hash, and an *accepted* signup spends both. If
only failures counted, the enumeration problem would be bounded and the flood —
the larger of the two — would stay unbounded, which is the wrong way round.

**Why 20 an hour and not 5.** Every key is the peer address, so a shared network
is a single key, and behind a proxy everybody is a single key (D5.5). A ceiling
tuned for one person per address is a ceiling for the whole invited group signing
up on the same evening. Twenty still turns "unbounded" into "480 a day", and the
invitation list is the control that actually decides who gets an account — this
is depth behind it, not a replacement for it.

**Alternative: a shared limiter for both routes.** Fewer moving parts, and it
would let a registration flood lock out the people who already have accounts.
That converts a nuisance into a denial of service against exactly the users the
limit exists to protect.

**What would change my mind.** Anyone hitting the ceiling legitimately. The fix
then is D5.5 first — a correct key — and only then a lower number.

### D5.5 · Not reading `X-Forwarded-For` yet

**Decision.** Deploy with limiters keyed on `request.client.host`, knowing that
on Cloud Run that is Google's front end and not the caller.

**Why not fix it now.** The fix is to trust a forwarded-for header, and an
unvalidated one is attacker-controlled: trusting it hands anyone an unlimited
supply of fresh throttle keys, which is strictly *worse* than one shared budget.
Doing it properly means knowing exactly how many hops the platform appends and
trusting only that many — a fact about Cloud Run specifically, best checked
against the deployed thing rather than guessed at from here.

**What it costs in the meantime.** The limiters degrade from per-caller to
roughly global. An unbounded loop still stops, which is the property they were
added for; one person can inconvenience the others. At twenty invited users that
is a nuisance, not an outage.

**This is not new, only newly visible.** `/login` has keyed on the peer address
since it was written. It has simply never run behind a proxy before, and
deploying is what makes the assumption load-bearing.

**Measured after deploying.** Cloud Run's logs show 99 of 99 requests arriving
from `169.254.169.126`. The degradation is not partial or probabilistic: it is
one key for everybody, exactly as predicted. The limits still bound a runaway
loop, which is what they were added for, and they no longer distinguish between
people at all.

**What would change my mind.** The first time someone is throttled who should not
have been — or opening this to anyone beyond the invited list, at which point the
shared budget stops being tolerable.

---

## Phase 6 — Operations

### D6.1 · `/health` touches the database

**Decision.** `SELECT 1` inside the handler, not just `{"status": "ok"}`.

**Why.** A health check that only proves the process is listening will report
healthy while every real request fails on a dead connection. That is still the
failure worth catching — a pooler can drop a connection, credentials can be
rotated, Supabase pauses after seven idle days — and a check that does not
exercise the dependency you are worried about is decoration.

**Alternative: separate liveness and readiness endpoints.** Correct in
Kubernetes, where the distinction drives different actions. Cloud Run has no such
distinction, so one honest endpoint is the right size.

### D6.2 · External uptime monitoring — **the tension went away with D2.0**

**Decision.** A free monitor hitting `/health` every five minutes.

**Why.** You will not otherwise find out it is broken — your twenty users will,
and most of them will simply stop using it rather than tell you.

**This used to be a genuine dilemma, and it is worth recording why it stopped
being one.** With Neon, five-minute polling would have kept the database
permanently awake and burned the compute budget from D2.2 — so you had to choose
between detection and staying free, with no clean answer. Supabase has no compute
budget and is always on, so poll as often as you like.

**A second-order effect of D2.0 that I did not anticipate when making it.**
Choosing a provider on its primary constraint also dissolved an unrelated
operational problem downstream. That happens more often than it seems to when you
*remove* a limit rather than manage one.

**One residual:** frequent polling counts as activity, so the seven-day pause
will never trigger either. Convenient — but do not let a monitor become the
reason the app looks alive.

> **What happened, and it is a lesson about monitoring rather than about hosting.**
> Ten monitors were created and **eight of them cannot fail.** Cloudflare Pages
> serves the SPA fallback for every unmatched path, so `/grades`, `/budget` and an
> invented path that has never existed all return an identical 466-byte 200. A
> monitor on any of those is testing that Cloudflare is up, which it is, and will
> stay green through any outage this app is capable of having.
>
> Two are real: **`/health`**, because it touches the database and can therefore
> answer `unhealthy`, and the frontend root. Delete the rest — a dashboard of ten
> green checks that cannot go red is worse than two, because it reads as coverage.
>
> `/health` also needed a code change to be monitorable at all: UptimeRobot sends
> **HEAD**, and `@app.get` registers GET only, so it answered 405 on every poll.
> Plain Starlette routes add HEAD automatically; FastAPI's do not. Fixed with
> `@app.api_route(..., methods=["GET", "HEAD"])`.

---

## Phase 7 — Rollout

### D7.1 · Two or three people first, not twenty

**Decision.** A week with a handful of real users before the rest.

**Why.** Everything above is reasoning; none of it is measurement. A week of real
use tells you what the cold starts actually feel like, how fast the compute
budget really drains, and which of these decisions was wrong — while the blast
radius is three people who will forgive you.

**And watch three numbers in that week:** Cloud Run request count, Supabase
database size against the 500 MB ceiling, and the cold-start latency your users
actually experience. Those decide whether Plan A holds, or whether Option D
arrives sooner than expected.

> **What happened.** Three addresses went into `ALLOWED_SIGNUP_EMAILS` and one
> other person signed in. Two of the three numbers turned out not to be worth
> watching at this size: 588 rows against a 500 MB ceiling, and a request count
> that rounds to nothing against 2M/month. The third was never measured (D3.2).
>
> **What the week did buy was the thing not on the list.** The second person's
> sign-in ran the account-seeding path for someone who had not built the app —
> the only part of this that had never been exercised by anyone but its author.
> It worked. That is a better test than any of the three numbers, and it is an
> argument for keeping D7.1 rather than going straight to twenty next time.
>
> It also surfaced the one thing that genuinely blocks step 39: the rate
> limiters key on Google's front end rather than the caller (D5.5), so twenty
> people would share one login budget.
