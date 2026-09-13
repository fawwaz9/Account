# Users and Auth

## Context

Who is signed in, what they can reach, and the settings every other module reads.
Small in surface and the only module where a mistake is a security bug rather
than a wrong number, which is why it carries 22 tests for roughly 400 lines.

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
| `verify_user_access` | `Auth/services/access.py` | `VerifiedUserId`, on every route in the app |
| `get_preferences` | `Users/services/user_service.py:205` | stored settings, defaults filled in |

## Data model

`users` — name, email (normalised: trimmed and lower-cased on the way in, so
`A@b.com` and `a@b.com` are not two accounts), `password_hash` (nullable),
`google_id` (nullable), `email_verified`, `session_epoch`,
`current_school_year` / `current_semester` / `term_label`, and `preferences`
(JSON).

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

What is in it, and who reads it: timezone (the completion-timing figure),
currency, week start, theme, date and time format, default reminder minutes,
`credit_target` and `gpa_scale_enabled` and `default_target_grade` (Grades, and
the at-risk bands in Tasks), and the study window (free blocks).

> **The bug this column caused.** `model_dump()` in Python mode puts `datetime.time`
> objects into a JSON column, which raises at commit rather than at assignment —
> and took out *every* Settings save with a 500. The fix is
> `model_dump(mode="json")`, and to merge and reassign the whole dict, since
> SQLAlchemy does not track mutation inside JSON. Third occurrence of that bug
> class in this codebase; the other two were `events.skipped_dates` and a
> recurring rule's.

## Academic status

`current_school_year` + `current_semester` are what `term_bucket` compares a
course against. With neither set, **everything reads as current** — a student who
has not filled it in sees their courses rather than an empty page.

## Notes

- Never widen `VerifiedUserId` to a raw `UUID` on a route.
- Preferences: `model_dump(mode="json")`, and reassign the whole dict.
- Email is normalised on the way in; lookups also use ILIKE.
- `auth_provider` is history. Ask `has_password` / `has_google` for what works now.
- The throttle is in-process. It resets on restart and is not shared across
  workers — acceptable for a single-process app, and the first thing to revisit
  if that changes.
