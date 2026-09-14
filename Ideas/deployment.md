# Deployment

Every step from where this is now to running on the web, in order.

**The target:** Google Cloud Run (the API) + Supabase (Postgres) + Cloudflare
Pages (the frontend), free, for about twenty invited people.

**Why that target,** and every alternative rejected along the way, is in
`Ideas/plan-a-decisions.md` — 26 decisions with their reasoning and what would
change my mind. This file is the *doing*; that one is the *why*. Where a step
below is contestable it names the decision, so `D2.3` means go and argue there.

---

## Where this stands

| | |
|---|---|
| Backend tests | **692 on SQLite; 690 + 2 skipped on Postgres 16** |
| Frontend | `tsc --noEmit` and `vite build` clean |
| Docker | **Phase 0 done — both images build, full stack verified end to end** |
| Database | SQLite locally; **must become Postgres** to deploy (nothing free has a persistent disk) |
| Open PRs | **none — all seven merged** |
| Deployed anywhere | No |

Phase 0 was run against a `VACUUM INTO` copy on ports 8200/5273. It confirmed the
images build, the stack works, auth works end to end, data survives
`down && up`, the image carries no real data or secrets, and the container runs
as non-root. It also found **B8** below, which nothing else would have.

---

## The architecture, in one paragraph

Cloudflare Pages serves the built JavaScript to the browser and holds no data and
no secrets. The browser then calls Cloud Run, on a different origin, with a
bearer token. Cloud Run holds all the logic and is the only thing that knows the
database password. Supabase holds all 23 tables and is the only thing that
remembers anything. **The browser never talks to Supabase** — this is deliberate,
and `plan-a-decisions.md` D2.0 explains why using Supabase the usual way would be
wrong here. A full trace of one request is in the "How Account Moves Data"
artifact.

---

## Before you start

Accounts you will need, all free, none needing a card except Google Cloud:

- **Google Cloud** — a billing account with a card is required even for the
  always-free tier. It is used for identity verification and is not charged while
  you stay inside the free limits.
- **Supabase** — no card.
- **Cloudflare** — no card.

Have to hand: the Google OAuth client ID this app already uses, and access to its
console to add an origin later (step 32).

**Work through this in order.** Parts 1 and 2 happen entirely on your machine and
are reversible. Nothing reaches the internet until Part 3.

---

## Part 1 — Code changes, all local

Nothing here needs a cloud account. Do it all before creating one, because every
one of these is easier now than over SSH or through a console.

### 1. Land PR #39 (soft delete) — **DONE**

**Do:** merge it, rebase as usual.

**Why it is first:** until it lands, `DELETE /users/{id}` is an immediate,
irreversible cascade across every table. That is the wrong thing to have live the
moment somebody other than you has an account. This is audit finding **S11**.

**Verify:** suite still green.

### 2. Decide on the other six PRs — **DONE, all merged**

**#40** (accessibility) is small and worth taking. **#28–#32** are feature work —
subscriptions, blind spots, PDF export, the priority badge, the recurring split.
None blocks deployment.

**Recommendation:** land #40, and decide #28–#32 on whether you would rather your
friends see them now or later. Landing them after deployment is a good way to
prove the deploy path works twice.

### 3. Fix `connect_args` so a Postgres URL does not crash — **DONE** (`361c2a5`)

**Do:** in `app/_database/db.py`, parse the URL rather than passing the
SQLite-only argument unconditionally.

```python
from sqlalchemy.engine import make_url

url = make_url(DATABASE_URL)
connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
```

**Why:** `check_same_thread` is SQLite-only and psycopg rejects it, so *any*
non-SQLite `DATABASE_URL` currently crashes at import — despite
`docker-compose.yml` advertising the variable as configurable. This is a live
bug. See **D1.1**.

**Verify:** `DATABASE_URL=postgresql://x python -c "import app.main"` should fail
on *connection*, not on an invalid argument.

### 4. Add the Postgres driver — **DONE** (`361c2a5`, done with step 3 since it is what verifies it)

**Do:** add `psycopg[binary]==3.*` to `requirements.txt`.

**Why psycopg 3 and not psycopg2 or asyncpg:** **D1.2**.

**Verify:** rebuild the venv from `requirements.txt` alone and run the suite. This
also fixes the stale-venv problem (**S9**) — yours currently has 64 packages
installed against 9 declared.

### 5. Make the test database configurable — **DONE** (`6a1926f`)

**Do:** in `tests/conftest.py`, read `TEST_DATABASE_URL`, defaulting to the
current SQLite setup so the fast local loop is unchanged.

**Why:** step 19 runs the whole suite against Postgres, and that is the step that
makes the port trustworthy rather than merely importable. **D1.5**.

**Verify:** 669 still pass with the variable unset.

### 6. Add `/health` — **DONE** (`6a1926f`)

**Do:** a route that runs `SELECT 1` and returns `{"status": "ok"}`.

**Why it must touch the database:** a check that only proves the process is
listening reports healthy while every request fails on a dead connection. **D6.1**.
Audit finding **B6**.

**Verify:** `curl localhost:8000/health` returns 200; stop the database and
confirm it returns 503 rather than 200.

### 7. Turn off the docs endpoints in production — **DONE** (`6a1926f`)

**Do:** `FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)`
when an environment variable says production, keeping them on locally.

**Why:** they are public today — Phase 0 confirmed `/docs` returns 200 — which
publishes the shape of all 133 routes to anyone. Audit finding **B3**.

**Verify:** with the variable set, `/docs` returns 404; without it, 200.

### 8. Stop re-checking the schema on every cold start — **DONE** (`0a09615`)

**Do:** gate the `lifespan` body behind an environment variable, so
`create_all`, `ensure_schema` and `ensure_indexes` run when you ask them to
rather than on every boot. Run them as a deploy step instead.

**Why:** measured, those three issue **278 statements** — 247 of them from
checking all 49 indexes. Against a local SQLite file that is free. Against
Postgres over a network at 2 ms a round trip it adds roughly **half a second to
every cold start**, paid by whoever arrives first after a quiet spell, to
re-confirm a schema that was already correct four minutes ago.

**Verify:** with the variable unset the server starts without issuing DDL; with
it set, it does.

### 9. Make `ALLOWED_ORIGINS` actually configurable — **DONE**

**Do:** in `docker-compose.yml`, change the hardcoded
`ALLOWED_ORIGINS: http://localhost:5173` to `${ALLOWED_ORIGINS}`, and add the
variable to `.env.example` with a comment saying what breaks when it is wrong.

**Why:** it is not merely unset — it is *hardcoded*, so it cannot be changed per
environment without editing the compose file. Audit finding **B2**, and Phase 0
reproduced the failure live: serving the frontend on 5273 while this said 5173
gave HTTP 400 on the preflight from the real origin and 200 from the stale one.
It presents as "the API is down" and appears nowhere in the API's logs.

**Verify:** set it to a wrong value and confirm the preflight fails; set it right
and confirm it passes.

### 10. Collapse the two `.env` files into one

**Do:** keep one, have both the compose file and local runs read it.

**Why:** `Application/.env` and `Application/backend/.env` hold the same secrets
and are byte-identical today with nothing keeping them so. When they drift, the
symptom is tokens signed with one key and verified with another — which reads to
a user as being randomly logged out. Audit finding **B7**.

### 11. Add the invite gate

**Do:** an `ALLOWED_SIGNUP_EMAILS` environment variable, checked in
`create_local_user` **and in the Google sign-in path**.

**Why both doors:** an allowlist that only guards `create_local_user` leaves
`POST /auth/google` wide open, because `get_or_create_user_by_google_id` creates
accounts too. Audit finding **B5**; reasoning and the rejected Cloudflare Access
alternative in **D5.1**.

**Verify:** an address on the list can register, one off it gets a clear refusal,
and the same is true through Google.

### 12. Rate-limit `/register`

**Do:** apply the existing `SlidingWindowLimiter` to the register route.

**Why:** only `/login` is limited today. The mechanism already exists. Audit
finding **S4**.

### 13. Add a React error boundary

**Do:** wrap the router in one, showing something a person can act on.

**Why:** any render exception is currently a white screen. On your own machine
you read the console; a friend just sees a broken app and stops using it. Audit
finding **S3**.

### 14. Write the security headers for Pages

**Do:** a `_headers` file in the frontend build output with HSTS, CSP,
`X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`.

**Why a `_headers` file and not `nginx.conf`:** in this architecture nginx is
gone — Pages serves the bundle. The finding survived; its fix moved. **D4.2**,
audit finding **S1**.

### 15. Green light

**Do:** run the whole suite, `npx tsc --noEmit`, `npm run build`, and one
`docker compose up --build` to confirm nothing here broke the image.

**Stop here if anything is red.** Everything after this point is harder to debug.

---

## Part 2 — The Postgres port, still local

### 16. Create the Supabase project

**Do:** new project, free plan. **Choose the region nearest your users and write
it down** — Cloud Run goes in the matching one at step 27.

**Why region matters:** every request makes several round trips, and the
dashboard makes five queries. A careless pairing can cost half a second on a page
the performance work already got down to five queries. **D2.1**.

### 17. Take the **pooled** connection string

**Do:** copy the pooled connection string (Supavisor), not the direct one.

**Why:** Cloud Run runs many independent instances, each with its own pool.
Without a pooler, three instances at five connections each is fifteen connections
for a handful of concurrent queries — and at the limit, requests are *refused*
rather than merely slow. **D2.3**.

### 18. Configure the engine for a connection that can go away

**Do:** `pool_pre_ping=True`, `pool_size` around 2–5, a modest `max_overflow`.

**Why:** poolers drop connections at their own discretion, Cloud Run instances
are torn down constantly, and Supabase pauses after seven idle days. Pre-ping
costs one trivial round trip per checkout and removes a whole class of
intermittent error. **D2.4**.

### 19. Run the 669 tests against Postgres

**Do:** `TEST_DATABASE_URL=<supabase pooled url>` and run the suite.

**This is the real work of the port.** The suite is the only description of the
app's behaviour you have; if it has never run against Postgres you know the port
imported, not that it works.

**Expect failures, and expect most to be real:** ordering that SQLite happened to
give you without an `ORDER BY`, integer-versus-boolean comparisons, stricter type
handling. Each is a latent bug SQLite was hiding.

**Verify:** green against Postgres *and* still green against SQLite.

> **Already proven, ahead of schedule.** While doing step 5 a throwaway
> Postgres 16 container was running, so the whole suite was pointed at it:
> **683 passed and 2 skipped on the first attempt**, against 685 on SQLite. The
> two skips are tests about SQLite itself rather than about the app. No
> application code needed changing — only three pieces of test scaffolding.
>
> That is a much better result than this step assumed, and it means the port is
> a known quantity rather than a risk. What remains is to repeat it against
> *Supabase* specifically, since a pooled connection over a network is not the
> same thing as a local container.

### 20. Move the data

**Do:** a script that opens both databases through SQLAlchemy and copies every
model in foreign-key order. **Run it against a `VACUUM INTO` copy of
`data/app.db`, never the original.**

**Why through the ORM rather than a SQL dump:** `sqlalchemy.types.Uuid` stores as
`CHAR(32)` on SQLite and as native `uuid` on Postgres. A raw dump carries the
SQLite representation across and produces either type errors or, worse,
valid-looking wrong data. **D1.4**.

### 21. Verify the move

**Do:** count rows per table on both sides, and diff a full dashboard payload
from each.

**The numbers to match** (as of the last check — re-count first, they move):
3 users, 27 courses, 126 grades, 95 transactions, 10 accounts, 43 spend
categories, 223 category weights.

A migration that "looks fine" is how you discover a missing table in March.

---

## Part 3 — Deploy

### 22. Create the Google Cloud project

**Do:** new project, attach a billing account, enable the Cloud Run and Artifact
Registry APIs.

**Note:** the card is required even for the always-free tier. It verifies
identity and is not charged inside the free limits.

### 23. Create an Artifact Registry repository

In the **same region** you chose at step 16.

### 24. Build for `linux/amd64` and push

**Do:** `docker build --platform linux/amd64`, tag for Artifact Registry, push.

**Why the flag matters:** your Mac is Apple Silicon, so Phase 0's images were
`linux/arm64` — verified, not assumed. **Cloud Run runs `amd64`.** Push what was
built locally without this flag and you deploy an image the platform cannot
execute, and you find out at deploy time. Audit finding **B8**, decision **D3.0**.

**Verify:** `docker image inspect <tag> --format '{{.Architecture}}'` says
`amd64`.

### 25. Put the secrets in Secret Manager

**Do:** `JWT_SECRET` and the Supabase connection string as secrets.

**Generate a fresh `JWT_SECRET`.** Not the one that has been in your working tree
since August. Rotating it signs everyone out once, which is correct and costs
nothing right now.

**Why not plain environment variables:** they are visible in the console, in
`gcloud run services describe` and in deploy logs. These two values are the ones
that matter most — one reads all the data, the other forges any session.
Non-secret config stays a plain variable. **D3.5**.

### 26. Run the schema creation once

**Do:** run `python -m app._database.schema` against Supabase once, with
`DATABASE_URL` pointing at it. It builds the 23 tables and 49 indexes and is
idempotent, so a retried deploy is harmless. The deployed service then runs with
`RUN_SCHEMA_ON_STARTUP=0`.

### 27. Deploy to Cloud Run

Settings that are not the defaults, and why:

| Setting | Value | Why |
|---|---|---|
| Region | same as Supabase | step 16 |
| `min-instances` | **0** | scale to zero is the whole point; cold starts are 200 ms–2 s (**D3.2**) |
| `max-instances` | **3** | the default is **100** — a crawler or a bug could burn a month's allowance in an afternoon, and every instance holds a connection pool (**D3.3**) |
| `concurrency` | **40** | the default is 80, but FastAPI runs your synchronous routes in a 40-thread pool. At 80, forty requests queue *inside your process* where the autoscaler cannot see them, so it never starts another instance (**D3.4**) |
| Secrets | from step 25 | |
| `ALLOWED_ORIGINS` | placeholder for now | corrected at step 30 |
| `RUN_SCHEMA_ON_STARTUP` | **0** | the schema was built at step 26; re-checking it costs 278 statements per cold start (**step 8**) |
| `ENABLE_DOCS` | unset | off is the default, but set nothing rather than something wrong |

### 28. Confirm the API is alive

**Do:** `curl https://<cloud-run-url>/health`.

**Verify:** 200 with `{"status": "ok"}`. If it is 503 the container is running but
cannot reach Supabase — which is exactly what step 6 was for.

### 29. Deploy the frontend to Cloudflare Pages

**Do:** connect the repo or upload the build. Set the build-time variables:
`VITE_API_BASE_URL` to your Cloud Run URL plus `/api`, and
`VITE_GOOGLE_CLIENT_ID`.

**These are inlined at build time, not read at runtime.** Changing either needs a
rebuild, not a restart. Phase 0 confirmed this behaves as expected.

**Verify:** the deployed bundle contains your Cloud Run URL:
`curl -s <pages-url>/assets/index-*.js | grep -o 'https://[^"]*run.app/api'`

### 30. Point `ALLOWED_ORIGINS` at the Pages URL

**Do:** set it to the exact origin — no wildcard, no trailing slash — and
redeploy Cloud Run.

**Expect to get this wrong once.** It is the single most likely hour-loser in
this document, and Phase 0 already reproduced the exact failure locally.

**A trap:** Pages gives you a permanent URL *and* a per-deploy preview URL.
Previews are different origins and will fail CORS. That is correct behaviour, not
a bug, but it is confusing the first time.

### 31. Add the Pages origin to Google OAuth

**Do:** in the Google Cloud console, add the Pages URL to the client ID's
authorised JavaScript origins.

**Why now:** Google checks the calling origin. Miss this and sign-in fails with a
message that never mentions origins. Second most likely hour-loser, and it fails
the same way as step 30. **D5.3**.

### 32. Test it properly

**Do:** open the Pages URL on your phone **with wifi off, on mobile data.** Sign
in, load the dashboard, add a grade, reload.

**Why mobile data:** testing from your own network proves nothing about whether
the thing is actually reachable from the internet.

---

## Part 4 — Before anyone else touches it

Do not skip this part to get friends in a day earlier.

### 33. Set up backups

**Do:** a scheduled nightly `pg_dump` to storage you control, off Supabase.

**This is not optional on Supabase free.** There are **no automated backups** on
that plan and point-in-time recovery is a $100/month feature. Skipping this means
the consequence of any mistake is "you lose everything" rather than "you lose a
day". **D2.5** — and D2.0's choice of Supabase over Neon is only a good decision
if this step actually happens.

### 34. Restore one

**Do:** restore last night's dump into a second Supabase project — the free plan
allows two — and open the real app against it.

**An unrestored backup is a belief, not a backup.** This is the step everyone
skips and the only one that proves the others.

### 35. Put a monitor on `/health`

**Do:** a free external monitor — UptimeRobot, Better Stack — every five minutes.

**Why five minutes is fine now:** it would not have been on Neon, where polling
kept the database awake and burned the compute budget. Supabase is always on with
no compute budget, so poll freely. Side benefit: regular polling counts as
activity, so the seven-day pause will never trigger. **D6.2**.

### 36. Write down how to roll it back

**Do:** one short note — the previous image tag, the command to redeploy it, and
where the backups are.

**Why:** you will need this while something is broken and you are stressed, which
is the worst time to work it out. Keep it next to this file.

---

## Part 5 — Let people in

### 37. Add yourself and two friends

**Do:** put three addresses in `ALLOWED_SIGNUP_EMAILS`. Not twenty.

### 38. Watch for a week

**Three numbers:**

- **Cloud Run request count** against 2M/month
- **Supabase database size** against 500 MB
- **Cold-start latency** as your friends actually experience it

And read the audit log — `auth.*` lines at WARNING are failed sign-ins.

**Why three people first:** everything in this plan is reasoning, not
measurement. A week of real use tells you which parts were wrong while the blast
radius is three people who will forgive you.

### 39. Invite the rest

Add the remaining addresses. You are live.

---

## Reference — audit findings, and where each is handled

| | Finding | Step |
|---|---|---|
| B1 | Docker never run end to end | **Done** — Phase 0 |
| B2 | `ALLOWED_ORIGINS` hardcoded and wrong | **Done** — step 9; step 30 sets the real value |
| B3 | `/docs` and `/openapi.json` public | **Done** — step 7 |
| B4 | No TLS | Free from Cloud Run and Pages |
| B5 | `/register` open to anyone | 11 |
| B6 | No health endpoint | **Done** — step 6 |
| B7 | Two `.env` files with duplicate secrets | 10 |
| B8 | Images build arm64; Cloud Run needs amd64 | 24 |
| S1 | No security headers | 14 |
| S2 | No backup discipline | 33, 34 |
| S3 | No React error boundary | 13 |
| S4 | `/register` unthrottled | 12 |
| S5 | No pagination on 27 list endpoints | **Deferred** — fine at this size, revisit if data grows |
| S6 | Migrations additive-only, unversioned | **Deferred** — see D1.3; step 8 strengthens the case for Alembic |
| S7 | README's "Still open" table is stale | **Deferred** — four of eight rows were fixed by merged PRs |
| S8 | Throttle state is per-process | **Accepted** — D3.6, bounded by `max-instances` 3 |
| S9 | Local venv stale vs `requirements.txt` | **Done** — step 4; a clean venv from the file alone is 42 packages and 669 green |
| S10 | Pydantic v3 deprecation | **Deferred** — `app/Tasks/schemas/task.py:77` |
| S11 | Hard user deletion live | **Done** — step 1 |

## Reference — capacity

| Limit | Ceiling | Users |
|---|---|---|
| Cloud Run requests | 2M/month | **~1,100** at ~60 requests per user per day |
| Supabase storage | 500 MB | ~1,900 at ~260 KB per active user |
| Supabase compute | none — always on | not a limit |

Twenty users is comfortable with a great deal of room. Requests bind first.

## Deliberately not doing

- **Pagination** (S5) — 95 transactions does not need it.
- **Alembic** (S6) — but step 8 makes the case stronger than when D1.3 was
  written. Revisit after the first deploy.
- **A shared throttle store** (S8) — adds a dependency and an outage path for a
  service whose absence would block all sign-ins.
- **Moving the JWT out of `sessionStorage`** — an httpOnly cookie introduces a
  CSRF requirement, and there is no XSS vector today.

## History

This plan was Oracle Cloud + SQLite, then Cloud Run + Neon, before arriving here.
Both changes are recorded in `plan-a-decisions.md` rather than quietly edited
away — D2.0 in particular, where the question "why can't we use Supabase?"
reversed a decision and dissolved an unrelated problem downstream. How a plan
changed is usually more instructive than what it changed to.

**Option D — self-hosting on a cheap mini PC — is deferred, not rejected.** It is
the only shape that keeps SQLite, removes every free-tier ceiling, and has no
cold starts. The trigger for revisiting is any of the three numbers in step 38
approaching its limit. Everything you would need is kept in the appendix below
rather than discarded.

---

# Appendix — Option D, if you revisit self-hosting

Kept because this decision is deferred rather than closed, and because the
research behind it does not survive anywhere else.

Worth separating from the rented-VM path that the requirements ruled out. Buying
hardware is a different proposition, and for *this* app it has one decisive
advantage: **it is the only option that keeps SQLite**, so it skips the Postgres
port entirely.

**What to buy.** A **used mini PC** — Dell OptiPlex Micro, HP EliteDesk Mini,
Lenovo ThinkCentre Tiny — is the best value. Roughly £50–100 second-hand, x86 so
the existing images run without an architecture rebuild, usually 8–16 GB of RAM
and an SSD already fitted, and about 10–15 W at idle. A **Raspberry Pi 5** works
too and draws less (~5 W), but once a case, PSU and SSD are added it typically
costs *more* than the used mini PC and is slower. An **old laptop you already
own** is free and has a built-in UPS in its battery.

**What to look for second-hand.** The Lenovo ThinkCentre Tiny / Dell OptiPlex
Micro / HP EliteDesk Mini families are all ex-corporate and all fine. Ranked by
what actually matters for a box that runs continuously:

| Priority | What | Why |
|---|---|---|
| 1 | **Power adapter included** | Proprietary barrel connectors. Sourcing one afterwards costs a third of the machine. |
| 2 | **No BIOS supervisor password** | Ex-lease machines sometimes ship locked. You need BIOS access to set *power on after AC loss*, which Phase 2 depends on. Ask explicitly. |
| 3 | **NVMe SSD**, 256 GB or more | Not a spinning disk, and not an SD card. Most of these have an M.2 slot *and* a 2.5in bay, so OS and data can live apart. |
| 4 | **16 GB RAM**, or 8 GB with a free slot | 8 GB runs this app several times over; 16 GB is what makes the box comfortable for future projects. Usually two SODIMM slots. |
| 5 | **A T-suffix CPU** — i5-8500T, i5-9500T | The 35 W variants rather than 65 W. Most Tiny/Micro/Mini units ship with them, and it is the difference that matters over a year of uptime. |
| 6 | 9th or 10th gen over 8th, if close in price | Marginally better efficiency. Not worth paying much for. |

**Do not pay extra for an i7.** An i5-8500T is already enormous overkill for a
Python web server with twenty users; the money is better spent on RAM or the
SSD. Expect roughly 7–12 W at idle, so about £8–15 a year in electricity.

> **Do not put the database on an SD card.** SQLite in WAL mode writes
> constantly, and SD cards fail from write cycles — usually silently, and
> usually as corruption rather than a clean death. Use an SSD, internal or USB.

**Getting it on the internet.** Two ways, and they differ on cost and on whether
the invite gate needs code:

| | Cloudflare Tunnel | Tailscale Funnel |
|---|---|---|
| Hostname | `app.yourdomain.com` | `box.tailnet.ts.net`, given to you |
| Domain needed | **Yes** — named tunnels require a zone on Cloudflare, about £8/yr at their at-cost registrar | **No** |
| TLS | included | included, real Let's Encrypt |
| Open ports | none | none |
| Invite gate | **Cloudflare Access, free to 50 users — no code** | in the app, `ALLOWED_SIGNUP_EMAILS`, ~15 lines |
| Caveats | quick `trycloudflare.com` tunnels are *not* a substitute — the URL changes on every restart and they are documented as non-production | ports 443/8443/10000 only, and non-configurable bandwidth limits |

Neither needs port forwarding, a static IP, or anything touched on your router.

**Software.** Ubuntu Server LTS or Debian, headless. Docker and Compose. The
tunnel client. `unattended-upgrades` so security patches land without you.
SSH by key only, password auth off. Set the BIOS to power on after a power cut,
and the existing `restart: unless-stopped` in `docker-compose.yml` brings the
stack back by itself.

**Backups — the part self-hosting makes genuinely yours.** Nightly
`VACUUM INTO` to a timestamped file, then **off the machine**: `rclone` to
Backblaze B2 (10 GB free) or similar. A backup sitting on the same disk as the
database is not a backup. Restore one and open the app against it before
believing any of it.

**Watching it.** A free external monitor — UptimeRobot, Better Stack — hitting
`/health` every few minutes, so you find out it is down before the twenty people
do. Self-hosted monitoring on the same box cannot tell you the box is off.

**What it really costs.** £50–100 once, plus about £3–6 a year of electricity,
plus £8/yr for a domain if you take the Cloudflare route. And your time: you are
now the sysadmin, your home internet is the uptime, and a power cut is an
outage.

**What it buys.** No Postgres port. No cold starts, ever. No card anywhere. The
invite gate free and codeless if you take the Cloudflare route. And the app runs
exactly as it was built, which is not nothing after 619 tests written against
that shape.

## The steps would differ from Part 3 onward

Parts 1, 4 and 5 above apply unchanged. What changes:

- **Part 2 disappears entirely.** No Postgres port: SQLite stays, so steps 3–5
  and 16–21 are unnecessary. This is the single biggest argument for Option D.
- **Part 3 becomes:** install Ubuntu Server, Docker, and a reverse proxy; run the
  existing compose stack; put a tunnel in front.
- **Step 8 stops mattering** — the 278 startup statements hit a local file again,
  which costs nothing, and there are no cold starts to pay them on.
- **Step 33 changes** from `pg_dump` to `VACUUM INTO`, still copied off the
  machine.
- **The invite gate (step 11) becomes optional** if you use Cloudflare Access,
  because a single origin makes Access viable again.

## And the multi-project groundwork

If the box is ever to host more than this app, four decisions are cheap now and
annoying later: a reverse proxy (Traefik) owning ports 80 and 443 rather than any
one app; one shared Docker network; a predictable `/srv/<project>/` layout so one
backup script covers everything; and `mem_limit` on every service so a runaway
project starves itself rather than the others.
