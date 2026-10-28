"""Every route, two users: nothing of B's reaches A, and nothing A does touches B.

Phase 0 of the vision (account-vision.md §4, Ideas/overhaul/phase0.md item 3).
Isolation is enforced in application code -- each query filters on ``user_id``
or reaches its rows through a parent that does -- and until this file, coverage
of that was per feature and depended on someone having remembered.

This suite does not depend on remembering. It **enumerates the routes from the
app itself**, so a new route is tested the day it is added, and a route nobody
has classified fails collection rather than passing silently -- the same shape
as the frontend's ``deleteConfirmations.test.ts``, after a hand count of deletes
missed one in ten.

The victim, B, owns one row in every table (``isolation_world.seed_world``),
and every text column of B's carries ``MARK_B``. The caller, A, owns a world of
their own. For each route the suite makes the requests an attacker would --

* **foreign-user**: B's id in the path. Must be refused with 403 outright.
* **foreign-objects**: A's own path, but every object id in it is B's.
* **foreign-leaf**: on nested paths, a parent of A's with a child of B's --
  ``/courses/{A's course}/grades/{B's grade}`` -- the case a parent-only check
  gets wrong.
* **foreign-refs**: A's own path, with every id-shaped field of the body and
  every id-shaped query parameter set to one of B's rows -- "file this expense
  into B's account".
* **own-read**: a plain read of A's own data, which must contain nothing of B's.

-- and after every one checks the same three invariants, whatever the route is:

1. **No leak.** ``MARK_B`` appears nowhere in the response.
2. **No damage.** Every row of B's is byte-for-byte what it was.
3. **No cross-link.** No row that changed points at any row of B's. Filing an
   expense into B's account changes nothing of B's and leaks nothing -- the
   only trace is A's new row holding B's account id.

Status codes are not asserted beyond foreign-user (and "no 500"). A route may
answer 404, 422 or an empty 200 to a foreign id; what matters is the three
invariants, which are what a leak actually violates.

**Vacuity is tracked, not assumed.** A foreign-refs request that dies in
validation proves nothing about the service behind it. Those routes must be
listed in ``VALIDATION_ONLY`` with the reason, so a gap is a line someone wrote
rather than a case that quietly passed.

Runs on SQLite by default and unchanged on Postgres (``TEST_DATABASE_URL``),
which is where the database-level policies of Phase 0 item 2 are proven.
"""
import enum
import json
import os
import re
import types
import typing
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

import app.main
from app._database.db import get_db
from app.Auth.services.session_service import create_access_token
from tests.conftest import make_user
from app.shared.dates import user_today
from app._database.rls import SEALED_TABLES, SHARED_READ_TABLES
from tests.isolation_world import CATALOGUE_IDS, PAIRED_TABLES, seed_catalogue, seed_pair, seed_world, snapshot

MARK_A = "zzownera"
MARK_B = "zzvictimb"

#: Routes with no per-user path. Each is still called, and still checked for
#: damage to B, where it can be called at all.
PUBLIC = {
    ("GET", "/health"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    # The scheduler's door: no user in it, refused without the cron secret
    # (and absent entirely when none is configured, as in the suite).
    ("POST", "/api/internal/reminders/dispatch"),
    # The daily grade recount (Phase 2 item 13): the same door, the same rule.
    ("POST", "/api/internal/distributions/recount"),
}
#: Routes about the caller themselves, resolved from the token rather than from
#: the path, so there is no foreign id to put in it.
SELF = {
    ("GET", "/api/users/me"),
    ("POST", "/api/auth/password"),
}
#: Not exercised, with the reason. Kept as short as possible.
SKIPPED = {
    ("POST", "/api/auth/google"): "verifies a Google credential over the network; "
    "it takes no user id and resolves the account from Google's answer",
}

#: Which of B's rows a path parameter names. ``(prefix, param)`` entries win
#: over bare ``param`` ones, for names that mean different tables in different
#: modules.
PATH_SOURCES = {
    ("/api/tasks/", "rule_id"): "recurring_tasks",
    # Phase 2 item 9b: sharing needs a one-off event, so these routes name the
    # world's study group rather than its weekly lecture -- otherwise A's own
    # requests stop at "can't be shared" and never reach the write.
    ("/api/calendar/{user_id}/events/{event_id}/sharing", "event_id"): "events_personal",
    ("/api/calendar/{user_id}/shared-events/", "event_id"): "events_personal",
    # An event's membership row; bare member_id is a task's.
    ("/api/calendar/", "member_id"): "event_members",
    # A team's membership row (Phase 2 item 11).
    ("/api/teams/", "member_id"): "team_members",
    # Phase 3 item 10: a club's membership row, and a club's event.
    ("/api/clubs/", "member_id"): "club_members",
    ("/api/clubs/", "event_id"): "club_events",
    ("/api/finances/", "rule_id"): "recurring_transactions",
    ("/api/jobs/", "event_id"): "events_shift",
    "account_id": "accounts",
    "blackout_id": "term_blackouts",
    "category_id": "spend_categories",
    "contribution_id": "sinking_contributions",
    "course_id": "courses",
    "event_id": "events",
    "fund_id": "sinking_funds",
    "grade_id": "grades",
    "import_id": "imports",
    "job_id": "jobs",
    "paycheque_id": "paycheques",
    "parse_id": "syllabus_parses",
    "payment_id": "tuition_payments",
    "reminder_id": "reminders",
    "requirement_id": "degree_requirements",
    "equivalence_id": "course_equivalences",
    "scheme_id": "grading_schemes",
    "task_id": "tasks",
    "transaction_id": "transactions",
    "invite_id": "invites",
    # A row id, never a person: A and B are partners in the world, so naming
    # B here would end the partnership both agreed to -- not a leak, and not
    # this walk's question. Ending is tested in tests/test_partners.py.
    "partner_id": "partnerships",
    "team_id": "teams",
    "game_id": "games",
    # Phase 3 item 1. The world's step is its interview, never its first
    # "applied" step, so deleting it reaches the write.
    "application_id": "job_applications",
    "step_id": "application_steps",
    "season_id": "application_seasons",
    # Phase 3 item 11: a check-in at office hours.
    "checkin_id": "office_hour_checkins",
    # Phase 3 item 6: a logged activity.
    "activity_id": "activities",
    # Phase 3 item 9: a request to join a team.
    "request_id": "team_join_requests",
    "club_id": "clubs",
    "post_id": "club_posts",
    "poll_id": "club_polls",
    # A membership row's own id (Phase 2 item 9a), as the owner removes it.
    "member_id": "task_members",
}

#: Which of B's rows an id-shaped body or query field names.
FIELD_SOURCES = {
    "account_id": "accounts",
    "from_account_id": "accounts",
    "to_account_id": "accounts_second",
    "category_id": "spend_categories",
    "course_id": "courses",
    "grade_id": "grades",
    "job_id": "jobs",
    "event_id": "events",
    "task_id": "tasks",
    "fund_id": "sinking_funds",
    "transaction_id": "transactions",
    "paycheque_id": "paycheques",
    # A scheme picked as a course's grade (Phase 1 D25).
    "scheme_id": "grading_schemes",
    # A season the tracker is filtered by (Phase 3 D7).
    "season_id": "application_seasons",
}

#: Date parameters that open and close a window, by name.
#: Query parameters only: a body's starts_on/ends_on keep the world's day, or a
#: blackout or event would be created spanning four months and be refused.
WINDOW_STARTS = {"start", "period_start"}
WINDOW_ENDS = {"end", "period_end"}

#: Fix-ups for bodies the generator cannot get right on its own: cross-field
#: rules ("an hourly job needs a rate"). Each entry is a list of patches, and
#: each patch is one request, so a route whose ids depend on a mode -- a
#: recurring rule is an expense with a category OR a transfer with a destination
#: -- is attacked in every mode. Keys are dotted paths; None removes the key.
BODY_PATCHES: dict[tuple[str, str], list[dict]] = {
    ("POST", "/api/tasks/{user_id}/reminders"): [{"remind_at": "2026-09-14T09:00:00"}],
    ("POST", "/api/jobs/{user_id}/jobs"): [{"hourly_rate": 20.0}],
    # Phase 3 item 1: "applied" is only ever the first step.
    ("POST", "/api/jobs/{user_id}/applications/{application_id}/steps"): [{"status": "interview"}],
    # Phase 3 D7: a season's months are written YYYY-MM.
    ("POST", "/api/jobs/{user_id}/applications/seasons"): [{"starts": "2026-09", "ends": "2026-12"}],
    ("PUT", "/api/jobs/{user_id}/applications/seasons/{season_id}"): [{"starts": "2026-09", "ends": "2026-12"}],
    ("POST", "/api/jobs/{user_id}/jobs/{job_id}/shifts"): [{"end_time": "17:00:00"}],
    ("PUT", "/api/finances/{user_id}/accounts/{account_id}/month-value"): [{"market_value": 100.0}],
    ("POST", "/api/finances/{user_id}/recurring"): [
        {"kind": "expense", "to_account_id": None},
        {"kind": "transfer", "category_id": None},
    ],
    # limit_amount omitted means "clear the limit", which writes nothing and so
    # could never show a cross-link. Setting one is the attack worth trying.
    ("PUT", "/api/finances/{user_id}/account-category-limits"): [{"limit_amount": 50.0}],
    ("POST", "/api/push/{user_id}/subscriptions"): [
        {"endpoint": "https://push.invalid/zzownera/new-device",
         "keys": {"p256dh": "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                  "auth": "BTBZMqHH6r4Tts7J_aSIgg"}},
    ],
    # A real file and mapping, so the commit reaches the write path -- with B's
    # account named in the body by the foreign-refs variant.
    ("POST", "/api/finances/{user_id}/imports"): [{
        "csv_text": "Date,Description,Amount\n2026-09-14,zzownera import,-4.50\n",
        "mapping": {"has_header": True, "date": 0, "description": [1], "amount": 2,
                    "debit": None, "credit": None, "date_order": "mdy", "invert": False},
        "lines": [2],
    }],
    ("POST", "/api/finances/{user_id}/imports/preview"): [{
        "csv_text": "Date,Description,Amount\n2026-09-14,zzownera import,-4.50\n",
        "mapping": None,
    }],
    ("POST", "/api/grades/{user_id}/courses/{course_id}/schemes"): [{
        "label": "zzownera scheme", "components": [{"category": "Final", "weight": 100.0}],
    }],
    ("PUT", "/api/grades/{user_id}/courses/{course_id}/schemes/{scheme_id}"): [{
        "label": "zzownera scheme", "components": [{"category": "Final", "weight": 100.0}],
    }],
    ("POST", "/api/intake/{user_id}/syllabus"): [{
        "filename": "s.pdf", "media_type": "application/pdf", "content_base64": "JVBERi0xLjQgdGVzdA==",
    }],
    ("POST", "/api/intake/{user_id}/syllabus/{parse_id}/apply"): [{
        "course_code": "ZZOWN 101", "course_name": "zzownera built", "year": 3, "semester": "Fall",
        "credits": 3.0, "professor": None,
        "assessments": [{"name": "Final", "category": "Final", "weight": 100.0, "count": 1,
                         "due_date": None, "date_tba": True}],
        # Phase 2 item 5: a confirmed rule, so the filing path runs too.
        "prerequisites": {"text": "CPSC 210", "note": "zzownera note"},
    }],
    ("POST", "/api/intake/{user_id}/syllabus/{parse_id}/add-to/{course_id}"): [
        {"rows": [{"name": "zzownera added", "category": "Quiz"}], "prerequisites": {"text": "CPSC 210"}},
    ],
    ("POST", "/api/degree/{user_id}/requirements"): [{
        "name": "zzownera requirement", "kind": "credits", "items": ["CPSC"], "credits_needed": 3.0,
    }],
    ("PUT", "/api/degree/{user_id}/requirements/{requirement_id}"): [{
        "name": "zzownera requirement", "kind": "credits", "items": ["CPSC"], "credits_needed": 3.0,
    }],
    ("POST", "/api/degree/{user_id}/equivalences"): [{"from_codes": ["COSC 111"], "counts_as": ["CPSC 110"]}],
    ("PUT", "/api/degree/{user_id}/equivalences/{equivalence_id}"): [
        {"from_codes": ["COSC 111"], "counts_as": ["CPSC 110"]}],
    # Every mode, so each write path runs: a chosen id (B's, under foreign-refs),
    # and the two that carry none.
    ("PUT", "/api/grades/{user_id}/courses/{course_id}/catalogue"): [
        {"mode": "chosen"},
        {"mode": "none", "catalogue_course_id": None},
        {"mode": "auto", "catalogue_course_id": None},
    ],
    # A readable rule each way, so the write runs: typed, and as a tree.
    ("PUT", "/api/grades/{user_id}/courses/{course_id}/prerequisites"): [
        {"text": "CPSC 210 and one of MATH 200, MATH 217", "rule": None},
        {"text": None, "rule": {"course": "CPSC 210"}},
    ],
    ("POST", "/api/grades/{user_id}/prerequisites/check"): [{"text": "CPSC 210"}],
    # A's own live invite (isolation_world): preview answers with A's name,
    # and accepting your own link answers "own" -- both reach the functions.
    ("POST", "/api/partners/{user_id}/invites/preview"): [{"token": "zzownera invite token"}],
    ("POST", "/api/partners/{user_id}/invites/accept"): [{"token": "zzownera invite token"}],
    # A's own task link (isolation_world): preview answers with A's task, and
    # accepting your own answers "own" -- both reach the functions.
    ("POST", "/api/tasks/{user_id}/shared-tasks/invites/preview"): [{"token": "zzownera task invite token"}],
    ("POST", "/api/tasks/{user_id}/shared-tasks/invites/accept"): [{"token": "zzownera task invite token"}],
    ("POST", "/api/calendar/{user_id}/shared-events/invites/preview"): [{"token": "zzownera event invite token"}],
    ("POST", "/api/calendar/{user_id}/shared-events/invites/accept"): [{"token": "zzownera event invite token"}],
    ("POST", "/api/teams/{user_id}/invites/preview"): [{"token": "zzownera team invite token"}],
    ("POST", "/api/teams/{user_id}/invites/accept"): [{"token": "zzownera team invite token"}],
    # Phase 3 item 10: A's own club link, and a valid poll.
    ("POST", "/api/clubs/{user_id}/invites/preview"): [{"token": "zzownera club invite token"}],
    ("POST", "/api/clubs/{user_id}/invites/accept"): [{"token": "zzownera club invite token"}],
    ("POST", "/api/clubs/{user_id}/{club_id}/polls"): [{"options": ["zzownera yes", "zzownera no"]}],
    ("POST", "/api/finances/{user_id}/subscriptions/confirm"): [
        {"instruction.kind": "expense", "instruction.to_account_id": None},
        {"instruction.kind": "transfer", "instruction.category_id": None},
    ],
}


def _patched(body, patch: dict):
    body = json.loads(json.dumps(body))
    for dotted, value in patch.items():
        *parents, last = dotted.split(".")
        node = body
        for part in parents:
            node = node[part]
        if value is None:
            node.pop(last, None)
        else:
            node[last] = value
    return body


#: foreign-refs cases whose request is rejected by validation before any
#: service code runs, so they prove nothing about isolation. Each needs a reason.
VALIDATION_ONLY: dict[tuple[str, str], str] = {}


# --------------------------------------------------------------------------
# Enumeration
# --------------------------------------------------------------------------

def _routes() -> list[APIRoute]:
    return [r for r in app.main.app.routes if isinstance(r, APIRoute)]


def _keys(route: APIRoute) -> list[tuple[str, str]]:
    return [(method, route.path) for method in sorted(route.methods - {"HEAD"})]


def _path_params(path: str) -> list[str]:
    return re.findall(r"{(\w+)}", path)


def _object_params(path: str) -> list[str]:
    return [p for p in _path_params(path) if p not in ("user_id", "on_date")]


def _source(path: str, param: str) -> str:
    for key, table in PATH_SOURCES.items():
        if isinstance(key, tuple) and path.startswith(key[0]) and param == key[1]:
            return table
    if param not in PATH_SOURCES:
        raise KeyError(f"no table known for path parameter {param!r} in {path}")
    return PATH_SOURCES[param]


def _cases():
    cases = []
    for route in _routes():
        flat = get_flat_dependant(route.dependant)
        has_body = bool(flat.body_params)
        id_queries = [q.name for q in flat.query_params if _is_uuid(q.field_info.annotation)]
        for method, path in _keys(route):
            key = (method, path)
            if key in SKIPPED:
                continue
            params = _path_params(path)
            if "user_id" not in params:
                assert key in PUBLIC or key in SELF, (
                    f"{method} {path} takes no user_id and is not classified. Add it to "
                    "PUBLIC or SELF in test_isolation.py, after checking it really "
                    "holds nothing per user."
                )
                cases.append(pytest.param(method, path, "own-read", None, id=f"{method} {path} own-read"))
                continue
            objects = _object_params(path)
            cases.append(pytest.param(method, path, "foreign-user", None, id=f"{method} {path} foreign-user"))
            if objects:
                cases.append(pytest.param(method, path, "foreign-objects", None,
                                          id=f"{method} {path} foreign-objects"))
            if len(objects) > 1:
                for leaf in objects:
                    cases.append(pytest.param(method, path, "foreign-leaf", leaf,
                                              id=f"{method} {path} foreign-leaf:{leaf}"))
            if has_body or id_queries:
                cases.append(pytest.param(method, path, "foreign-refs", None,
                                          id=f"{method} {path} foreign-refs"))
            if method == "GET" and not objects:
                cases.append(pytest.param(method, path, "own-read", None, id=f"{method} {path} own-read"))
    return cases


# --------------------------------------------------------------------------
# Building requests
# --------------------------------------------------------------------------

def _unwrap(annotation):
    """Optional[X] / X | None -> X. Other unions -> their first member."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return args[0] if args else annotation
    if origin is typing.Annotated:
        return _unwrap(typing.get_args(annotation)[0])
    return annotation


def _is_uuid(annotation) -> bool:
    inner = _unwrap(annotation)
    if typing.get_origin(inner) in (list, set, tuple):
        args = typing.get_args(inner)
        return bool(args) and _is_uuid(args[0])
    return inner is uuid.UUID


def _sample(annotation, name: str, refs: dict[str, str]):
    inner = _unwrap(annotation)
    origin = typing.get_origin(inner)
    if inner is uuid.UUID:
        return refs.get(name, refs["accounts"])
    if origin in (list, set, tuple):
        args = typing.get_args(inner)
        if args and _is_uuid(args[0]):
            return [refs.get(name.removesuffix("s") if name.endswith("_ids") else name, refs["accounts"])]
        return [_sample(args[0], name, refs)] if args and isinstance(args[0], type) and issubclass(args[0], BaseModel) else []
    if origin is dict:
        return {}
    if origin is typing.Literal:
        return typing.get_args(inner)[0]
    if isinstance(inner, type):
        if issubclass(inner, BaseModel):
            return _build(inner, refs)
        if issubclass(inner, enum.Enum):
            return next(iter(inner)).value
        if issubclass(inner, bool):
            return False
        if issubclass(inner, int):
            # A calendar year (the tax packet) is the world's own year, so the
            # read covers the world's rows; any other int is a small count.
            if name == "calendar_year":
                return date.fromisoformat(refs["__day__"]).year
            return 1
        if issubclass(inner, float):
            return 1.0
        if issubclass(inner, datetime):
            return datetime.combine(date.fromisoformat(refs["__day__"]), time(9, 0), tzinfo=timezone.utc).isoformat()
        if issubclass(inner, date):
            # A window has to contain the world, or a list that leaked every
            # user's rows would return nothing and pass: start=end=today is a
            # one-day window, and "upcoming" rightly excludes today. Found by
            # mutation -- an unfiltered recurring projection went unnoticed.
            day = date.fromisoformat(refs["__day__"])
            if name in WINDOW_STARTS:
                return (day - timedelta(days=30)).isoformat()
            if name in WINDOW_ENDS:
                return (day + timedelta(days=90)).isoformat()
            return refs["__day__"]
        if issubclass(inner, time):
            return "09:00:00"
        if issubclass(inner, str):
            return f"{MARK_A} {name}" if name not in ("email",) else "isolation-a@example.com"
    return None


def _build(model: type[BaseModel], refs: dict[str, str]) -> dict:
    body = {}
    for name, field in model.model_fields.items():
        key = field.alias or name
        if field.is_required() or _is_uuid(field.annotation):
            body[key] = _sample(field.annotation, name, refs)
    return body


def _field_refs(world: dict[str, uuid.UUID], day: date) -> dict[str, str]:
    refs = {name: str(world[table]) for name, table in FIELD_SOURCES.items()}
    refs["accounts"] = str(world["accounts"])
    # A shared row, the same in every world: naming it is never a foreign
    # reference, and it is what a valid catalogue choice names.
    refs["catalogue_course_id"] = str(CATALOGUE_IDS["catalogue_courses"])
    refs["__day__"] = day.isoformat()
    return refs


def _request(route, method, path, variant, leaf, a, b, world_a, world_b, day, refs_world=None):
    """The URL, query and body for one case.

    ``refs_world`` chooses whose ids fill the body and the id-shaped query
    parameters; by default B's, except on own-read.
    """
    params = _path_params(path)
    url = path
    for param in params:
        if param == "user_id":
            value = b.id if variant == "foreign-user" else a.id
        elif param == "on_date":
            value = day.isoformat()
        else:
            table = _source(path, param)
            if variant in ("foreign-user", "foreign-objects"):
                value = world_b[table]
            elif variant == "foreign-leaf":
                value = world_b[table] if param == leaf else world_a[table]
            else:
                value = world_a[table]
        url = url.replace("{" + param + "}", str(value))

    if refs_world is None:
        # On foreign-objects and foreign-leaf the path object is the attack,
        # so the body is A's own: with B's ids in the body too, the body's
        # ownership checks refused the request before the path object was ever
        # looked up, and an edit that would have reached B's row went unseen.
        # (B's ids in a body are foreign-refs' job.)
        own_body = variant in ("own-read", "foreign-objects", "foreign-leaf")
        refs_world = world_a if own_body else world_b
    refs = _field_refs(refs_world, day)
    flat = get_flat_dependant(route.dependant)

    query = {}
    for q in flat.query_params:
        annotation = q.field_info.annotation
        # An own-read sends only what is required: an optional filter set to
        # A's own row narrows the answer, and a list that ignored user_id
        # entirely would then still look clean.
        wanted = q.field_info.is_required() or (_is_uuid(annotation) and variant != "own-read")
        if wanted:
            value = _sample(annotation, q.name, refs)
            if value is not None:
                query[q.alias or q.name] = value

    body = None
    if flat.body_params and method in ("POST", "PUT", "PATCH"):
        if len(flat.body_params) == 1:
            field = flat.body_params[0]
            body = _sample(field.field_info.annotation, field.name, refs)
        else:
            body = {f.alias or f.name: _sample(f.field_info.annotation, f.name, refs) for f in flat.body_params}
    return url, query, body


# --------------------------------------------------------------------------
# The invariants
# --------------------------------------------------------------------------

def _leaves(value, prefix=""):
    """Every leaf of a JSON-shaped value, as {dotted path: value}."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(_leaves(item, f"{prefix}{key}."))
        return out
    if isinstance(value, list):
        out = {}
        for index, item in enumerate(value):
            out.update(_leaves(item, f"{prefix}{index}."))
        return out
    return {prefix.rstrip("."): value}


def _with_leaf(value, dotted: str, new):
    value = json.loads(json.dumps(value))
    *parents, last = dotted.split(".")
    node = value
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(last)] = new
    else:
        node[last] = new
    return value


def _owned_by_b(before: dict, b_id: uuid.UUID, world_b: dict) -> set[tuple[str, uuid.UUID]]:
    keys = {("users", b_id)}
    b_pks = set(world_b.values())
    for table, rows in before.items():
        for pk in rows:
            if pk in b_pks:
                keys.add((table, pk))
    return keys


def _b_id_strings(b_id, world_b) -> set[str]:
    # UUIDs only. course_category_weights has an integer key, and "1" would be
    # found in every row of the database.
    ids = {i for i in (b_id, *world_b.values()) if isinstance(i, uuid.UUID)}
    return {str(i) for i in ids} | {i.hex for i in ids}


def _cell(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


#: Columns whose whole job is to name another person, set by a definer
#: function both people agreed through. A changed row of A's naming B there
#: is the partnership, not a cross-link.
DELIBERATE_LINKS = {("partnerships", "partner_id")}


def _check(before, after, b, world_b, response, sent: str):
    problems = []

    if MARK_B in response.text:
        problems.append(f"LEAK: response contains B's data: {response.text[:300]}")

    for table, pk in sorted(_owned_by_b(before, b.id, world_b), key=str):
        if pk not in after.get(table, {}):
            problems.append(f"DAMAGE: B's {table} row {pk} is gone")
        elif after[table][pk] != before[table][pk]:
            changed = {k for k in before[table][pk] if before[table][pk][k] != after[table][pk].get(k)}
            problems.append(f"DAMAGE: B's {table} row {pk} changed: {sorted(changed)}")

    b_strings = _b_id_strings(b.id, world_b)
    b_keys = _owned_by_b(before, b.id, world_b)
    for table, rows in after.items():
        for pk, row in rows.items():
            if (table, pk) in b_keys or before.get(table, {}).get(pk) == row:
                continue
            for column, value in row.items():
                if column == "id" or value is None or (table, column) in DELIBERATE_LINKS:
                    continue
                text = _cell(value)
                if any(s in text for s in b_strings):
                    problems.append(f"CROSS-LINK: {table}.{column} of a changed row points at B's data")

    # Shared rows belong to nobody, so no request may change them at all --
    # only the owner-run review script writes them (Phase 2 D9).
    for table in SHARED_READ_TABLES:
        if after.get(table) != before.get(table):
            problems.append(f"SHARED WRITE: a request changed {table}")
    # Sealed rows (Phase 2 D25) likewise: only the scheduler's recount writes
    # them, and the walk never holds its secret.
    for table in SEALED_TABLES:
        if after.get(table) != before.get(table):
            problems.append(f"SEALED WRITE: a request changed {table}")

    if response.status_code >= 500:
        problems.append(f"CRASH: {response.status_code} {response.text[:200]}")
    return problems


# --------------------------------------------------------------------------
# The test
# --------------------------------------------------------------------------

def _route_for(method: str, path: str) -> APIRoute:
    for route in _routes():
        if route.path == path and method in route.methods:
            return route
    raise LookupError(f"{method} {path}")


@pytest.fixture
def two_worlds(db):
    a = make_user(db, "isolation-a@example.com")
    b = make_user(db, "isolation-b@example.com")
    # A Google-authenticated user without a google_id fails the response model,
    # so every read of a user would be a 500 and prove nothing.
    a.google_id = "google-isolation-a"
    b.google_id = f"google-{MARK_B}"
    b.name = f"{MARK_B} person"
    db.commit()
    # The user's today, not the machine's: the fixture user's time zone is not
    # the CI runner's, and a world dated on the wrong side of midnight falls
    # outside every "this week" window.
    day = user_today(db, a.id)
    world_a = seed_world(db, a.id, MARK_A, day)
    world_b = seed_world(db, b.id, MARK_B, day)
    seed_catalogue(db)
    # A and B are partners: what A may see of B is B's figure, and only that.
    pair_a, pair_b = seed_pair(db, a.id, b.id, MARK_A, MARK_B)
    world_a.update(pair_a)
    world_b.update(pair_b)
    return a, b, world_a, world_b, day


@pytest.fixture
def client(db):
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        # Not entered as a context manager: that runs the app's lifespan, which
        # issues DDL and the expired-account purge through the application
        # engine. None of that is under test here, and conftest has already
        # pointed that engine at a scratch file.
        yield TestClient(app.main.app, raise_server_exceptions=bool(os.getenv("ISOLATION_RAISE")))
    finally:
        app.main.app.dependency_overrides.clear()


@pytest.mark.parametrize(("method", "path", "variant", "leaf"), _cases())
def test_route_isolation(db, client, two_worlds, method, path, variant, leaf):
    a, b, world_a, world_b, day = two_worlds
    token = create_access_token(a.id, a.session_epoch or 0)

    for url, query, body in _expanded_requests(method, path, variant, leaf, a, b, world_a, world_b, day):
        before = snapshot(db)
        response = client.request(
            method, url, params=query, json=body, headers={"Authorization": f"Bearer {token}"},
        )
        db.rollback()
        after = snapshot(db)

        problems = _check(before, after, b, world_b, response, url)
        assert not problems, (
            f"{method} {url} [{variant}] -> {response.status_code}\n"
            f"query: {query}\nbody: {body}\n" + "\n".join(problems)
        )
        _check_status(method, path, variant, response)


def _expanded_requests(method, path, variant, leaf, a, b, world_a, world_b, day):
    """Every (url, query, body) one case sends. Shared with test_rls.py."""
    route = _route_for(method, path)
    url, query, body = _request(route, method, path, variant, leaf, a, b, world_a, world_b, day)

    requests = [(query, body)]
    if variant == "foreign-refs":
        # All of B's ids at once, then each one alone among A's. All at once is
        # not enough: the first foreign id a service checks refuses the whole
        # request, which hides whether the checks after it exist at all.
        _, query_a, body_a = _request(route, method, path, variant, leaf, a, b, world_a, world_b, day,
                                      refs_world=world_a)
        for dotted, value in _leaves(body).items():
            if value != _leaves(body_a).get(dotted):
                requests.append((query_a, _with_leaf(body_a, dotted, value)))
        for name, value in query.items():
            if value != query_a.get(name):
                requests.append(({**query_a, name: value}, body_a))

    expanded = []
    for query, body in requests:
        if body is not None and (method, path) in BODY_PATCHES:
            expanded += [(query, _patched(body, patch)) for patch in BODY_PATCHES[(method, path)]]
        else:
            expanded.append((query, body))

    return [(url, query, body) for query, body in expanded]


def _check_status(method, path, variant, response):
    # Not vacuous: a read of the caller's own data has to succeed. Without
    # this, a suite whose requests all failed authentication -- a wrong token,
    # the app on the wrong database -- would leak nothing and pass.
    if variant == "own-read" and method == "GET":
        assert 200 <= response.status_code < 300, (
            f"{method} {path}: reading your own data answered {response.status_code}, so "
            f"this run is not exercising the route. {response.text[:300]}"
        )

    if variant == "foreign-user":
        assert response.status_code == 403, (
            f"{method} {path} answered {response.status_code} to a request for another "
            f"user's path; every per-user route must refuse it through VerifiedUserId"
        )

    if variant == "foreign-refs" and response.status_code == 422:
        assert (method, path) in VALIDATION_ONLY, (
            f"{method} {path}: the foreign-refs request never got past validation, so "
            f"this case proves nothing. Make _request build a valid body for it, or list "
            f"it in VALIDATION_ONLY with the reason.\n{response.text[:400]}"
        )


def test_every_route_is_covered():
    """The enumeration itself: every route is a case, skipped with a reason, or public."""
    covered = {(c.values[0], c.values[1]) for c in _cases()}
    for route in _routes():
        for key in _keys(route):
            assert key in covered or key in SKIPPED, f"{key} produced no isolation case"
    # A skip list that only grows is how coverage erodes; keep it honest.
    assert len(SKIPPED) <= 1


def test_the_world_covers_every_table(db, user):
    from app._database.models import Base
    world = seed_world(db, user.id, MARK_B, user_today(db, user.id))
    tables = ({t.name for t in Base.metadata.sorted_tables} - {"users"} - SHARED_READ_TABLES - SEALED_TABLES
              - PAIRED_TABLES)
    assert tables <= set(world)
    assert SHARED_READ_TABLES | SEALED_TABLES <= set(seed_catalogue(db))
