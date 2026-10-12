# Users and Auth

## Context

Who is signed in, what they can reach, and the settings every other module reads.
Small in surface and the only module where a mistake is a security bug rather
than a wrong number. The database's half of isolation, row security and the
identity each request carries, is in
[isolation-and-sharing.md](isolation-and-sharing.md). This note is the
application's half.

**Decisions taken:** two ways in — Google and a local password — and an account
may end up with both; a session is a stateless JWT, revoked by an epoch counter
rather than a session table; settings live in one JSON column parsed through a
Pydantic model, so a new preference needs no migration.

## What it is built from

| Piece | Where | What it does |
|---|---|---|
| `create_access_token` / `decode_access_token` | `Auth/services/session_service.py` | mint and read a JWT, with its epoch |
| `is_revoked` | `Auth/services/session_service.py:67` | epoch comparison, the whole revocation scheme |
| `hash_password` / `verify_password` | `Auth/services/password_service.py` | bcrypt, with a 72-byte ceiling |
| `burn_one_verification` | `Auth/services/password_service.py:40` | constant-time behaviour for an unknown address |
| `SlidingWindowLimiter` | `Auth/services/login_throttle.py` | 8 attempts per key, bounded at 4096 keys |
| `client_of` | `Auth/services/client_address.py` | the caller's address, for the limiters and the audit log (D18) |
| `may_sign_up` | `Auth/services/signup_policy.py` | the signup allowlist, on both ways in |
| `get_current_user` | `Auth/dependencies.py` | the token's user, and `act_as` so the database knows who is asking |
| `verify_user_access` | `Auth/services/access.py` | `VerifiedUserId`, on every route in the app |
| `get_preferences` | `Users/services/user_service.py` | stored settings, defaults filled in |
| `delete_user` / `restore_user` / `purge_expired_users` | `Users/services/user_service.py` | deletion with a 30-day way back |

## Data model

`users` — name, email (normalised: trimmed and lower-cased on the way in, so
`A@b.com` and `a@b.com` are not two accounts), `password_hash` (nullable),
`google_id` (nullable), `email_verified`, `session_epoch`,
`current_school_year` / `current_semester`, `first_year_calendar_year` (the
anchor every term date and heading derive from), `term_label` (the fallback for
a user with no anchor, and due to be dropped), `deleted_at`, and `preferences`
(JSON).

`push_subscriptions` — one row per device that turned notifications on. The
endpoint is unique across users: a browser handed from one account to another is
released from the first by a definer function
(`account_release_push_endpoint`), since nothing in the second account can see
the first's row.

`auth_provider` records how the account was *originally* created. What it can
sign in with *today* is `has_password` / `has_google`, two properties derived from
the columns — because an account created with Google and later given a password
can do both, and the original provider stops being the answer.

## Sessions, and why there is no session table

A JWT carrying `sub` and an epoch. `users.session_epoch` increments on any
security-relevant change, and a token whose epoch is not equal to the user's is
refused.

That gives revocation without storing sessions: one integer comparison, already
loaded alongside the user, so it costs no extra query. Setting a password revokes
every outstanding session; a token minted immediately after carries the new epoch
and still works. An epoch from the *future* is refused as well — not equality by
accident, but because a token claiming an epoch the account has never reached is
forged or stale in a way worth rejecting.

A missing epoch claim reads as zero, so tokens minted before the column existed
behave predictably rather than crashing.

`decode_access_token` rejects a token with no `sub`, no `exp`, or a `sub` that is
not a UUID — **rejects, not 500s**. Each has a test, because a malformed token
reaching an unhandled exception is an availability bug reachable by anyone.

## The rules that are security, not style

**Two levels of check, two different answers, and the difference is deliberate.**

At the *path* level, `VerifiedUserId` compares the URL's `user_id` against the
token's and raises **403**. You are asking for someone else's namespace outright,
and there is nothing to conceal: you already know that user id.

At the *resource* level, every service filters by `user_id`, so another user's
course or transaction simply is not found and the route raises **404** — the same
answer as a row that does not exist. That one must stay indistinguishable, or the
API confirms which ids are real.

**Every route takes `VerifiedUserId`.** A route taking a raw `UUID` is a hole,
and it is the first thing to look for in review.

**An unknown address still burns a verification.** `burn_one_verification` hashes
a placeholder so a login for an address with no account takes about as long as
one for an address with a password. Without it, response time enumerates users.

**Login throttling is per (email, client)**, case- and whitespace-insensitive on
the address, so the same address from a different client is a different key. The
key table is capped at 4096, because an unbounded one is itself the denial of
service.

> **"Client" was the platform's proxy until 2026-10-08.** Behind Cloud Run every
> request's peer is the same internal address (99 of 99 in the logs), so every
> caller shared one budget. `client_of` now reads `X-Forwarded-For`, counting
> `TRUSTED_PROXY_HOPS` entries in from the **right**, because the left end is
> whatever the client wrote. With 0 (the default) the header is ignored, so a
> local run behaves as before. Production runs with 1, set only after a forged
> header was shown to be ignored.

**Signup is by allowlist; sign-in is not.** `ALLOWED_SIGNUP_EMAILS` gates
*creating* an account, on `/register` and on `/auth/google`, which creates
accounts too. An allowlist on the password path alone would have left the
other way in open. An account that exists keeps working whether or not it is
listed, because taking access away is a deletion and deletion has its own path.
Unset means open, so a fresh clone can make its first account. `./invite.sh`
adds addresses to the deployed list.

**Deleting an account is marked, not done.** `delete_user` stamps `deleted_at`
and bumps the session epoch in the same moment, so a stolen token that asked for
the deletion can't keep using the account during the grace period. The owner
signs in again, sees the date, and can undo it. `purge_expired_users` removes
the account 30 days later, one account at a time and acting as that user:
- Under row security the cascade can only see that user's rows, which is
  exactly the set that should go.
- Kept syllabus files go first, since no database cascade reaches storage. If
  storage can't confirm the delete, the account waits for the next purge.
- A refused delete rolls back and waits, rather than taking down the startup
  it runs in (D33).

**Changing an email clears `email_verified`.** Repeating the *same* address does
not, so saving Settings without touching the address does not silently
de-verify it.

**Linking Google to an address that already has a password drops the password.**
An address someone else may have claimed first must not keep a credential from
before the link.

## Preferences

One JSON column, parsed through `UserPreferences`. New keys are additive and need
no migration — which is how the study window (`study_day_start`,
`study_day_end`, `min_free_block_minutes`) arrived for free.

What is in it, and who reads it:
- **`timezone`**: "today" everywhere, on the server (`shared/dates`) and in the
  browser (`setClockZone`), plus completion timing, reminders and the now-line
- **`credit_target`, `gpa_scale_enabled`, `default_target_grade`**: Grades, and
  the at-risk bands in Tasks
- **The study window**: free blocks
- **`event_colors`**: the calendar, only for the kinds you changed
- **`use_estimate_ratio`**: whether the workload forecast scales estimates (D36)
- **`exam_buffer_hours`**: how close before an exam a shift is flagged, 0 to 48
  (D21)
- **`cash_tip_account_id`**: where cash tips are filed. It is read here but
  deliberately absent from `UserPreferencesPatch`, because choosing it files
  every held tip, and that has its own endpoint with its own ownership check
- **Unread**: currency, week start, theme, date and time format, and default
  reminder minutes. Nothing reads these

> **The bug this column caused.** `model_dump()` in Python mode puts `datetime.time`
> objects into a JSON column, which raises at commit rather than at assignment —
> and took out *every* Settings save with a 500. The fix is
> `model_dump(mode="json")`, and to merge and reassign the whole dict, since
> SQLAlchemy does not track mutation inside JSON. Third occurrence of that bug
> class in this codebase; the other two were `events.skipped_dates` and a
> recurring rule's.

> **Audit #58 is closed, and its wording was misleading.** "Seven preferences
> have no control" read as seven controls to build. It was one bug, one control
> and the rest. The bug: every Settings save reset the preferences it didn't
> mention, timezone included, because the update took the full model, whose
> every field has a default. It now takes `UserPreferencesPatch`, merged with
> `exclude_unset`. The control was the time zone, in Settings → Calendar. The
> rest are the six unread keys above, kept unexposed on purpose: a control that
> changes nothing is worse than none.
>
> The time zone control is seeded from the **stored** zone, never the browser's
> guess. The guess is offered by a button instead, so opening Settings in
> another city can't quietly repoint every reminder on the next save.
> `currency` is validated as ISO 4217 and still ignored: `money.ts` hardcodes
> `$`.

## Academic status

`current_school_year` + `current_semester` are what `term_bucket` compares a
course against. With neither set, **everything reads as current** — a student who
has not filled it in sees their courses rather than an empty page.

`first_year_calendar_year` is the anchor term dates and the term heading derive
from (Settings → Academic, which suggests one from your courses' dates).
`term_label` predates it. It has no editor anywhere, which is how it went a
year stale, and is due to be dropped once every user has an anchor.

## Settings, the page

Account and Password side by side, then three tabs shown one at a time
(Academic, the default, then Calendar and Financial), and `?tab=` opens one
directly. Calendar holds the study window, the time zone, event colours, the
exam buffer and Blocked periods. Financial holds the income split, categories,
cash tips and the counted-accounts list. Notifications are switched on per
device from there too.

## Notes

- Never widen `VerifiedUserId` to a raw `UUID` on a route.
- Preferences: `model_dump(mode="json")`, and reassign the whole dict.
- Email is normalised on the way in; lookups also use ILIKE.
- `auth_provider` is history. Ask `has_password` / `has_google` for what works now.
- The throttle is in-process. It resets on restart and is not shared across
  Cloud Run instances. That is acceptable at this scale, and the first thing
  to revisit if traffic grows.
- Never key a limiter on the leftmost `X-Forwarded-For` entry, or on "the first
  public address". Both are the client's to write.
- `ALLOWED_SIGNUP_EMAILS` is comma-separated, so `invite.sh` sets it with
  `--update-env-vars "^|^…"`. A plain `--update-env-vars` splits on the commas
  and keeps only the first address.
