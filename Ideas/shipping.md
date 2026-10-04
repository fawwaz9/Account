# Shipping a feature

How a change gets from an idea to production, in the order the steps actually
have to happen. `deployment.md` is the history of how this deployment was built
and why it is shaped the way it is; `ROLLBACK.md` is what to read when something
is down. **This one is the loop you run every time.**

Every rule below is here because it cost something. Where a step looks like
paranoia, the paragraph under it names the day it was not.

---

## Where things live

| | |
|---|---|
| Frontend | https://account-2a7.pages.dev — Cloudflare Pages, **builds from `main`** |
| API | https://account-api-210502804146.us-west1.run.app — Cloud Run `account-api`, `us-west1` |
| Database | Supabase project `kujxxairehpwhxhnkbct` |
| Registry | `us-west1-docker.pkg.dev/account-504419/account/backend` |
| Local dev | backend **:8001**, frontend **:5173** — `Application/dev.run.sh` |

> **Port :8000 locally is a different project.** If something answers there and
> calls itself "Red String API (dev stub)", you are talking to the wrong thing.

---

# Part 1 — Build it

### 1. Find the narrowest design that delivers the outcome

Check for a smaller pattern before calling something a re-architecture. Most of
what has shipped here is one column, one service function and one component.

Prefer leaving choices open to the person using the app over encoding a rule
that forbids them — the accounts feature seeds five pots and lets you invent
any others, rather than shipping a taxonomy.

### 2. If it needs a column, add it in two places

```python
# app/_database/models.py       -- the mapped column
# app/_database/migrations.py   -- ADDED_COLUMNS[table][column] = "DDL"
```

`Base.metadata.create_all` only creates missing **tables**. An existing database
keeps its old shape, so every new column on an existing table needs an
`ADDED_COLUMNS` entry or production breaks on exactly one endpoint.

**`ensure_schema` emits literal DDL with no dialect awareness.** It runs against
SQLite locally and Postgres in production, and they do not accept the same text:

- `BOOLEAN NOT NULL DEFAULT 0` — SQLite fine, **Postgres rejects it**. Use
  `DEFAULT false`.
- `JSON NOT NULL DEFAULT '[]'` — works on both. Verified, not assumed.
- Adding a nullable column on Postgres 11+ is metadata-only, so it is safe on a
  live table.

A one-off data fix goes in `BACKFILLS`, keyed `(table, column)`. It runs once,
inside the same transaction as the `ALTER`.

### 3. If it touches a JSON column, reassign the whole value

```python
course.links = [*course.links, new_link]   # yes
course.links.append(new_link)              # no -- silently never persists
```

**SQLAlchemy does not track a mutation made inside a JSON column.** This has
caused three separate bugs here: `users.preferences`, a recurring event's
`skipped_dates`, and `tasks.tags`. It never raises. The write simply does not
happen, and only on the code path that mutates in place.

### 4. Write the test that fails without the change

Then **revert the change and watch it fail**. A guard with no failing test is
decoration, and this has caught real nothing-burgers:

- A URL scheme check whose `.lower()` could be deleted with every test still
  green, because `JavaScript:` was refused by the allowlist either way.
- A no-mutation guarantee whose test passed against the bug, because the
  mutate-and-restore version puts the value back before anything looks. The
  assertion had to move to `db.dirty`.
- A `/me` fix that reverted cleanly with 880 tests green, because every test
  called the service directly and the bug was that the **route** never did.

> **Test through the ASGI app when the bug could live in the wiring.**
> `tests/test_user_routes.py` exists because a service can be correct, tested,
> and never called. A `response_model` that does not match what the service
> returns is a 500 that no service-level test can see.

### 5. Update the docs as part of the change, not after

`Ideas/design/*.md` and `Ideas/shipped.md` — plus `next.md` if this closes an entry
there — in the same commit. A design doc
describing the rule you just replaced is worse than no doc — two design docs
were found stale only because a deploy went looking.

---

# Part 2 — Verify locally

### 6. The three green lights

```sh
cd Application/backend  && .venv/bin/python -m pytest tests/ -q -W error::sqlalchemy.exc.SAWarning
cd Application/frontend && npm test && ./node_modules/.bin/tsc --noEmit && npm run build
```

CI runs exactly these on every push. Running them locally first is still
faster than waiting for it.

> **CI runs on UTC; the test user lives in America/Regina.** A test that compares
> against `date.today()` passes on your Mac and fails on CI every evening after
> 6pm Regina time. Expect `user_today(db, user.id)`, the app's own clock.

> **`npm test` is deliberately not part of `npm run build`.** Cloudflare Pages
> runs the build script, so a red test there would take away your ability to
> deploy a hotfix. The gate belongs here, in front of a person, not in the
> deploy path.

> **Use `./node_modules/.bin/tsc`, not `npx tsc`.** With no local TypeScript on
> the path, `npx tsc` prints *"This is not the tsc command you are looking
> for"* and **exits 0**. A `&& echo CLEAN` after it prints CLEAN. That happened
> here; the typecheck had not run at all.

### 7. Run it against a copy of the real database, never the real one

```sh
sqlite3 data/app.db "VACUUM INTO '$SCRATCH/probe.db'"   # never cp -- WAL
```

Then set `DATABASE_URL` to the copy **before importing anything**, and assert
the engine URL is the copy.

> A verification script once imported `SessionLocal`, which points at the real
> `data/app.db`, and its cleanup block computed a delete filter that collapsed
> to `DELETE FROM course_category_weights`. It wiped 218 rows across all 27
> courses and printed success. **Never compute a delete filter** — write the
> literal condition for the literal model. **Count the rows before and after.**

### 8. Do not let a check pass vacuously

The most expensive failures here were not wrong answers. They were checks that
never ran:

- **Seeds that guess column names.** A fixture threw on
  `RecurringTaskModel(freq=...)` — the real columns are `recur_freq` /
  `recur_interval` — so every assertion afterwards passed against **zero rows**.
  Read the columns; do not guess them.
- **zsh does not word-split unquoted parameters.** `set -- $t` left every
  column check querying table `'tasks occurrence_date'` for column `''`, which
  returns 0 whatever the truth is.
- **Assertions that assume an empty slate.** A sweep reported "links leaked to
  another course"; the link had been added by hand during testing. Assert the
  property you mean — *writing one course changed no other row* — not a
  starting state you did not establish.

If a check cannot fail, it is not a check. Make it fail on purpose once.

### 9. If the schema changed, rehearse the migration on a throwaway Postgres

```sh
docker run -d --name pg-check -e POSTGRES_PASSWORD=test -e POSTGRES_DB=acct \
  -p 55433:5432 postgres:17-alpine
```

Apply the full schema, **drop the new columns**, insert a row against the old
shape, then run `ensure_schema()` and assert the columns appear and the
pre-existing row carries the default. Dropping first is the point: against a
database `create_all` just built, the migration path is never exercised.

---

# Part 3 — Deploy

**The order is schema → API → `main`, and it is not interchangeable.** A new
column is invisible to the running image, so it can land early and safely. New
code against a missing column is a 500. And pushing `main` is what builds the
frontend, so it goes last, after the API it depends on is proven.

### The automated path — use this

```sh
git push origin HEAD:ship    # the API: backup, schema gate, build, deploy, verify (~3 min)
# read the run: gh run watch, or the Actions tab
git push origin main         # the frontend, last, when the API run is green
```

`.github/workflows/deploy-api.yml` does steps 10, 12 and 13 below, and checks
what step 13 asks you to check: that the revision taking 100% of traffic runs
the digest just pushed, `/health`, and CORS against a stranger's origin as well
as yours. Its summary prints the four facts step 16 wants for `ROLLBACK.md`.

**Step 11 is still yours.** The workflow never applies the schema. It compares
the models against production's catalogue first and refuses to deploy if a table
or column is missing, printing the command to run. So: if the deploy stops at
*schema-gate*, do step 11 by hand, then re-run the deploy.

`main` keeps its meaning — pushing it builds the frontend — so the order holds:
`ship` deploys the API on its own, and the push to `main` stays a person's call
at the last reversible moment. CI (`.github/workflows/ci.yml`) runs the three
green lights on every push, `ship` included; it reports and blocks nothing.

Auth is Workload Identity Federation: there is no key. GCP mints tokens only for
`refs/heads/ship` of this repository, to `github-deployer@account-504419`, which
holds three roles, each on one resource. If it is ever refused, that binding is
the first place to look.

**The steps below are the manual fallback** — for when Actions is down or the
GCP binding breaks. They are what the workflow does, in the same order.

### 10. Back up first

```sh
gh workflow run backup.yml --repo fawwaz9/Account
gh run list --workflow=backup.yml --repo fawwaz9/Account --limit 1
```

Wait for `completed success`.

### 11. Schema — only if `app/_database/` changed

```sh
git diff <deployed-sha>..HEAD --stat -- Application/backend/app/_database/
```

Empty output means skip this step. Otherwise, **assert the columns are absent
first**, or "present after" proves nothing:

```sh
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

Then read the columns back and check the defaults reached existing rows.

> The service runs with `RUN_SCHEMA_ON_STARTUP=0`. **Deploying does not change
> the database.** That is deliberate — it keeps the schema check off the cold
> path of every request — but it means this step is yours to remember.

> `SUPABASE_DATABASE_URL` is the cloud string. **Never set `DATABASE_URL` to it
> in your shell profile** — that is what the app reads, so local dev would
> point at production.

### 12. Build, smoke-test, push the image

```sh
cd Application/backend
IMG=us-west1-docker.pkg.dev/account-504419/account/backend
SHA=$(git rev-parse --short HEAD)

docker build --platform linux/amd64 --provenance=false \
  -t "${IMG}:${SHA}" -t "${IMG}:latest" .
```

- **`--platform linux/amd64`** — this Mac builds arm64, Cloud Run runs amd64.
- **`--provenance=false`** — otherwise one push creates three registry versions
  and an untagged-cleanup rule can delete manifests the tagged index needs.
- **`${IMG}` with braces.** In zsh `$IMG:latest` parses `:l` as the lowercase
  modifier and silently creates a tag named `...backendatest`.

Run it before pushing — a successful build proves the layers assembled, not
that the process starts:

```sh
docker run -d --name api-smoke --platform linux/amd64 -p 127.0.0.1:8302:8000 \
  -e DATABASE_URL="sqlite:////app/data/app.db" \
  -e JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  -e GOOGLE_CLIENT_ID="placeholder.apps.googleusercontent.com" \
  -e RUN_SCHEMA_ON_STARTUP=1 "${IMG}:${SHA}"
```

`GOOGLE_CLIENT_ID` has no default; without it `Settings()` raises at import and
the container exits 1 before serving. On Cloud Run that reads only as "failed to
start and listen on the port".

Confirm the image carries what you think — `docker exec api-smoke grep ...` for
a string only the new code has — then push:

```sh
docker push "${IMG}:${SHA}" && docker push "${IMG}:latest"
docker manifest inspect "${IMG}:${SHA}" | grep -m1 mediaType   # image.manifest
```

### 13. Deploy the API

```sh
gcloud run deploy account-api --region=us-west1 --port=8000 \
  --image="${IMG}:${SHA}"
```

- **`--port=8000` every time.** The image hardcodes uvicorn there; Cloud Run
  expects 8080 by default.
- **`--image=` alone preserves env vars and secrets.** Do not pass
  `--update-env-vars` unless you mean it — it replaces a variable whole.

**Verify what is actually serving:**

```sh
gcloud run services describe account-api --region=us-west1 \
  --format="value(status.traffic[].revisionName, status.traffic[].percent, spec.traffic[].latestRevision)"
curl -s https://account-api-210502804146.us-west1.run.app/health
```

`latestRevision: True` is healthy. **A bare revision name means the service is
pinned** and every later deploy will report success and change nothing. Fix with
`--to-latest`.

### 14. Push `main` — this builds the frontend

```sh
git push origin main
```

> **The Cloudflare asset hash will never match your local build.** Pages builds
> with its own `VITE_API_URL`, so the same commit produces a different bundle
> and a different filename — `index-CMufIwGH.js` live against `index-Z3zKn_hj.js`
> locally. Polling for the local hash waits forever.

Verify by **content**, downloading the bundle and grepping the file:

```sh
hash=$(curl -s https://account-2a7.pages.dev/ | grep -o 'index-[A-Za-z0-9_-]*\.js' | head -1)
curl -s "https://account-2a7.pages.dev/assets/$hash" -o /tmp/live.js
grep -c "a string only the new code has" /tmp/live.js
```

Grep the **file**, never a shell variable — a 475 KB bundle in a variable gave a
false negative once.

> **For an exact answer, build what Pages builds.** Minification strips names
> and comments, so new logic often has no greppable string. Build locally with
> the production API URL into a scratch directory and compare chunks with the
> sibling-import hashes normalised:
>
> ```sh
> VITE_API_BASE_URL=https://account-api-210502804146.us-west1.run.app/api \
>   ./node_modules/.bin/vite build --outDir /tmp/prodbuild --emptyOutDir
> ```
>
> Comparing against your ordinary local build is not enough: the different API
> URL string shifts esbuild's character frequencies, and minified identifiers
> come out renamed (`ig` vs `i0`) even when the code is the same.

> **The bundle is split, so `index-*.js` is not the app.** Routes are lazy since
> the code-splitting work, and a new string lands in whichever chunk owns it. A
> grep of the entry chunk that finds nothing has proved nothing. Find the chunk
> that owns the code you changed, and read the **stylesheet separately** — CSS
> is its own file and travels on its own schedule.

> **Checking that a chunk exists by its status code is vacuous.** Pages serves
> `index.html` — status **200**, `text/html` — for any asset it does not have,
> so every URL you try comes back 200 whether the file is there or not. Check
> `content-type` instead:
>
> ```sh
> curl -sI "https://account-2a7.pages.dev/assets/$chunk" | grep -i content-type
> # text/javascript = there. text/html = missing, and the 200 was a lie.
> ```

> **Read it twice.** A mid-propagation edge once served the new JS beside the
> old CSS, which looks exactly like a broken deploy. A second cache-busted read
> a minute later showed the correct pair.

> ### `cssCodeSplit: false` preserves the CONTENTS of the CSS, not its ORDER
>
> This cost a day and is the least obvious thing in this file. Making routes
> lazy changed the module graph, which changed the order rules are emitted in,
> which flipped a specificity **tie** that had always been decided by emission
> order. `.budgetPage { max-width: 980px }` had never applied; after the split
> it did, and the budget page came out narrow with nothing in the diff to
> explain it.
>
> **"The rule multiset is identical" is true and insufficient.** It was true,
> and the page still broke. When a build config touches chunking, diff the
> emitted CSS by **order** as well as by content, and check any two rules that
> target the same element with equal specificity.
>
> **No component test can catch this.** jsdom has no layout engine and no
> cascade, so a rendering test sees nothing. The guard has to read the built
> stylesheet — and read it with `node:fs`, because **vitest stubs CSS imports as
> empty strings**: `import.meta.glob` over `.css` hands back filenames with no
> content, and a test written that way passes without ever looking at a rule.

### 15. Check it end to end

```sh
gcloud run services logs read account-api --region=us-west1 --limit=40 \
  | grep -iE "error|traceback|column|relation"
```

`UndefinedColumn` or `relation ... does not exist` means step 11 was skipped.
Also confirm CORS, which fails silently from the server's side:

```sh
curl -s -D- -o /dev/null -X OPTIONS \
  https://account-api-210502804146.us-west1.run.app/api/users/me \
  -H "Origin: https://account-2a7.pages.dev" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
```

---

# Part 4 — After

### 16. Write down what is now live

- **`ROLLBACK.md`** — the current and previous image tags and revision names.
  It went two deploys stale once and would have sent someone rolling back to
  the wrong thing during an outage.
- **`shipped.md`** — what shipped, and anything the feature needs from the
  user before it does anything (a setting to fill in, estimates to add).

### 17. Say whether the API can be rolled back on its own

This is **not** a general property — it depends on how each feature fetches, and
it has gone both ways:

- `18205eb` **could not**. Net worth was fetched inside a shared `Promise.all`,
  so one 404 blanked the budget page and the dashboard.
- `18e3376` **could**. Every new read either catches its own failure or is
  defaulted at the call site (`course.links ?? []`).

Check it while the code is in front of you and record the answer.

### 18. If you REMOVED a feature, say what its table is now

> **A removal deletes the code. It does not delete the table, and nobody
> notices.** `394cb7c` took whole-budget category limits out — model, service,
> routes, frontend — and `category_budgets` is still in production with four
> indexes and two rows of real data. It was found four days later by counting
> tables, not by anything failing, because nothing fails: no code selects from
> it and no foreign key points at it.
>
> The cost is that production now has **one table more than the schema builds**,
> so the file every other document treats as the description of this database has
> quietly stopped being it.
>
> **Do not reflexively drop it** — dropping destroys data that rolling the code
> back does not, which is exactly why this is a decision and not a cleanup. Write
> the answer down instead:
>
> ```sh
> # what production actually has, against what the schema builds
> SELECT table_name FROM information_schema.tables
> WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name;
> ```
>
> Name the orphaned table in `next.md` with its row count, and say whether
> it is kept for the data or waiting to be dropped. Either is fine; not knowing
> which is not.

### 19. Prune Docker, locally only

```sh
docker builder prune -f      # the only one that reclaims anything here
docker system df             # confirm
```

Every deploy, not when the disk complains — build cache is never cleared on its
own and it reached 5.5 GB once. First run took 295 MB.

**Not `docker image prune`.** It removes dangling `<none>` images, and step 12
tags every image with its commit sha, so there are never any: it reports 0 B. The
image space `docker system df` calls reclaimable is superseded local copies, and
clearing those is a named `docker image rm`, done occasionally — never
`prune -a`, which would take the image now in production with it.

**When you do clear those, do it BEFORE the cache prune.** An image reference pins
the cache entries that built it, so the same `builder prune` reclaimed 295 MB with
the images present and 629 MB once they were gone. And confirm the registry holds
each tag first — that is the entire reason removing the local copy is safe.

**Local only.** The registry tags are the rollback path, `ROLLBACK.md` requires
keeping at least two, and all fifteen occupy 0.22 GB anyway because they share
base layers. Deleting a local tag does not touch the registry copy. Full
reasoning and the measurements are in `deployment.md` under *Housekeeping*.

---

## The short version

1. Narrowest design. Column goes in `models.py` **and** `migrations.py`.
2. Reassign JSON columns whole.
3. Write the test, then revert the fix and watch it fail.
4. Docs in the same commit.
5. Tests, `./node_modules/.bin/tsc`, build.
6. Exercise it against a **copy** of the database.
7. `git push origin HEAD:ship` — backup, build, deploy and verify, automated.
8. If it stops at the schema gate: schema to Supabase by hand, then re-run it.
9. (Manual fallback for 7, if Actions or GCP auth is broken: steps 10–13.)
10. Read the run green before going on.
11. Push `main`, verify the frontend **by content**, and by chunk — the bundle is
    split, and a 200 on a missing asset is Pages serving `index.html`.
12. Update `ROLLBACK.md` and `shipped.md` (and `next.md`, if an entry is now closed).
13. If you removed a feature, name the table it orphaned and say what happens to it.
14. `docker builder prune -f` — **local only**, never the registry. (`image prune` is a no-op here.)
