"""Non-interference: what A gets back cannot depend on what B has.

``test_isolation.py`` proves nothing of B's *appears* in A's responses. That
misses a quieter failure, found by mutation testing: B's data *influencing*
A's answers without ever showing up in them. Without its user filter,
``blackout_dates`` subtracted B's term breaks from A's timetable -- A's classes
vanished on B's holidays, and A could read B's holidays off the gaps -- and the
"last account of its kind" guard counted B's accounts as A's survivors. Neither
put a byte of B's into a response.

So: every route, run twice from identical starting points -- once in a database
holding A's world and B's, once in a database holding A's world alone, with the
same ids -- and the two runs must agree: the same status, the same response,
the same rows of A's afterwards. B is built on the same days as A, so wherever
B's rows could leak into a window or a count, they are in it.

SQLite only. The two databases are separate in-memory engines, which Postgres
cannot mirror inside one rolled-back transaction; and on Postgres, row-level
security makes B's rows invisible to A's session in the first place, which
``test_rls.py`` proves directly.
"""
import json
import re
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.main
from app._database.db import get_db
from app._database.models import (
    AccountModel, Base, CourseModel, SpendCategoryModel, TermBlackoutModel, TransactionModel, UserModel,
)
from app.Auth.services.session_service import create_access_token
from app.shared.dates import user_today
from tests import test_isolation as iso
from tests.conftest import TESTING_SQLITE, _make_engine
from tests.isolation_world import seed_catalogue, seed_world, snapshot

pytestmark = pytest.mark.skipif(not TESTING_SQLITE, reason="compares two in-memory databases")

A_ID = uuid.uuid5(uuid.NAMESPACE_URL, "account-isolation-world/user-a")
INFLUENCERS = {
    name: uuid.uuid5(uuid.NAMESPACE_URL, f"account-isolation-world/b-influencer-{name}")
    for name in ("blackout", "account", "category", "course")
}
#: B's past rows. Everything in the seeded world is dated today, and some
#: answers read only history (the forecast's pace, runway and run-rates); with
#: no past rows, mutation testing removed the forecast's user filters unseen.
#: B's history starts earlier than A's and shares A's merchant, so leaking any
#: of it would move A's figures.
B_HISTORY = {
    name: uuid.uuid5(uuid.NAMESPACE_URL, f"account-isolation-world/b-history-{name}")
    for name in ("income", "coffee-1", "coffee-2", "big")
}
A_HISTORY = {
    name: uuid.uuid5(uuid.NAMESPACE_URL, f"account-isolation-world/a-history-{name}")
    for name in ("income", "coffee-1", "coffee-2")
}
B_ID = uuid.uuid5(uuid.NAMESPACE_URL, "account-isolation-world/user-b")

TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")


def _build(with_b: bool):
    engine = _make_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    a = UserModel(id=A_ID, name="a", email="ni-a@example.com", email_verified=True, google_id="g-a")
    session.add(a)
    if with_b:
        session.add(UserModel(id=B_ID, name="zzvictimb", email="ni-b@example.com",
                              email_verified=True, google_id="g-b"))
    session.commit()
    day = user_today(session, A_ID)
    world_a = seed_world(session, A_ID, iso.MARK_A, day)
    world_b = seed_world(session, B_ID, iso.MARK_B, day) if with_b else None
    # A names no partner here (see DOMAIN_404); a fixed id so the path resolves.
    world_a["partnerships"] = uuid.uuid5(uuid.NAMESPACE_URL, "account-ni/no-partnership")
    # Likewise nobody is on A's task here, and A is on nobody's (DOMAIN_404).
    world_a["task_members"] = uuid.uuid5(uuid.NAMESPACE_URL, "account-ni/no-task-member")
    world_a["event_members"] = uuid.uuid5(uuid.NAMESPACE_URL, "account-ni/no-event-member")
    # Shared rows belong to nobody, so both runs hold them, with the same ids.
    seed_catalogue(session)

    def past(row_id, user_id, account_id, kind, amount, days, description):
        session.add(TransactionModel(
            id=row_id, user_id=user_id, account_id=account_id, kind=kind, amount=amount,
            description=description, occurred_on=day - timedelta(days=days),
        ))

    # A's history, the same in both runs.
    past(A_HISTORY["income"], A_ID, world_a["accounts"], "income", 400.0, 30, f"{iso.MARK_A} history")
    past(A_HISTORY["coffee-1"], A_ID, world_a["accounts"], "expense", -12.0, 3, f"{iso.MARK_A} coffee")
    past(A_HISTORY["coffee-2"], A_ID, world_a["accounts"], "expense", -12.0, 10, f"{iso.MARK_A} coffee")
    session.commit()
    if with_b:
        # Influencers: rows of B's placed where they would change A's answers
        # if they leaked into A's queries, but which A's identical world cannot
        # mask. A's weekly lecture falls on `day`; a break of B's over it would
        # take A's class off A's timetable.
        past(B_HISTORY["income"], B_ID, world_b["accounts"], "income", 7000.0, 50, f"{iso.MARK_B} history")
        past(B_HISTORY["coffee-1"], B_ID, world_b["accounts"], "expense", -12.0, 4, f"{iso.MARK_A} coffee")
        past(B_HISTORY["coffee-2"], B_ID, world_b["accounts"], "expense", -12.0, 11, f"{iso.MARK_A} coffee")
        past(B_HISTORY["big"], B_ID, world_b["accounts"], "expense", -900.0, 6, f"{iso.MARK_B} big spend")
        session.add(TermBlackoutModel(
            id=INFLUENCERS["blackout"],
            user_id=B_ID, label="zzvictimb influencer", starts_on=day - timedelta(days=1),
            ends_on=day + timedelta(days=1),
        ))
        # B already holds the names A's generated requests will try to create
        # ("zzownera name", "zzownera code"). A duplicate check that forgot its
        # user filter would refuse A -- and tell A that B has one by that name.
        session.add(AccountModel(id=INFLUENCERS["account"], user_id=B_ID, name=f"{iso.MARK_A} name",
                                 kind="other", income_share=0.0, archived=False, position=9))
        session.add(SpendCategoryModel(id=INFLUENCERS["category"], user_id=B_ID,
                                       name=f"{iso.MARK_A} name", archived=False, position=9))
        session.add(CourseModel(id=INFLUENCERS["course"], user_id=B_ID, code=f"{iso.MARK_A} code",
                                name=f"{iso.MARK_A} name", semester="Fall", year=3, credits=3.0,
                                required=True, final_grade=0.0, average=0.0, no_final=False,
                                transfer_credit=False, archived=False, links=[]))
        session.commit()
    return engine, session, a, world_a, world_b, day


#: A fresh invite token in a response, and the hash of one in a row: random by
#: design, so two runs differ there whatever B does (Phase 2 item 10).
SECRET = re.compile(r'("token"\s*:\s*")[A-Za-z0-9_-]{20,}(")|("token_hash"\s*:\s*")[0-9a-f]{64}(")')


def _normalise(text: str, known: set[str]) -> str:
    """Mask what legitimately differs between two runs: clocks, new ids, and
    fresh secrets."""
    text = TIMESTAMP.sub("<ts>", text)
    text = SECRET.sub(lambda m: (m.group(1) or m.group(3)) + "<secret>" + (m.group(2) or m.group(4)), text)
    return UUID.sub(lambda m: m.group(0) if m.group(0) in known else "<new>", text)


def _a_rows(snap: dict, b_keys: set, b_course, known: set[str]) -> dict:
    out = {}
    for table, rows in snap.items():
        kept = []
        for pk, row in rows.items():
            if table == "course_category_weights":
                # An integer counter: B's rows shift every later number, so the
                # same number is B's in one database and A's in the other.
                # Whose a weight is comes from its course instead.
                if row["course_id"] == b_course:
                    continue
                row = dict(row)
                row.pop("id")
            elif pk in b_keys:
                continue
            else:
                row = dict(row)
            kept.append(_normalise(json.dumps(row, default=str, sort_keys=True), known))
        out[table] = sorted(kept)
    return out


#: Routes whose 404 is an answer about A's own state, not a missed request.
DOMAIN_404 = {
    ("POST", "/api/users/{user_id}/restore"): "no pending deletion to restore",
    # No partnership in either run, on purpose: a partner is influence both
    # people agreed to, which is not this walk's question. Ending one is
    # tested in tests/test_partners.py.
    ("DELETE", "/api/partners/{user_id}/partners/{partner_id}"): "no partnership to end",
    # Shared tasks (Phase 2 item 9a): nobody is a member of anything in either
    # run, for the same reason. A is the owner of the world's task, not a
    # member, so the member's routes find nothing. Tested in
    # tests/test_shared_tasks.py.
    ("DELETE", "/api/tasks/{user_id}/tasks/{task_id}/sharing/members/{member_id}"): "nobody on the task to remove",
    ("PATCH", "/api/tasks/{user_id}/shared-tasks/{task_id}"): "A is on nobody's task",
    ("DELETE", "/api/tasks/{user_id}/shared-tasks/{task_id}"): "A is on nobody's task",
    # Shared events (Phase 2 item 9b), likewise. The path's event is A's own
    # study group, which A owns rather than attends. Tested in
    # tests/test_shared_events.py.
    ("DELETE", "/api/calendar/{user_id}/events/{event_id}/sharing/members/{member_id}"): "nobody on the event to remove",
    ("DELETE", "/api/calendar/{user_id}/shared-events/{event_id}"): "A is on nobody's event",
}


def _yielding(session):
    """A get_db override returning ``session``, with no parameters of its own.

    Not a lambda with a default argument: FastAPI inspects an override's
    signature, takes a defaulted parameter for a query parameter, and tries to
    deep-copy the session as its default.
    """
    def override():
        return session
    return override


def _cases():
    seen = set()
    for case in iso._cases():
        method, path, *_ = case.values
        if "{user_id}" not in path or (method, path) in seen:
            continue
        seen.add((method, path))
        yield pytest.param(method, path, id=f"{method} {path}")


@pytest.mark.parametrize(("method", "path"), list(_cases()))
def test_b_cannot_influence_a(method, path, _no_push_network):
    runs = {}
    for with_b in (True, False):
        engine, session, a, world_a, world_b, day = _build(with_b)
        runs[with_b] = (engine, session, a, world_a, world_b, day)

    _, _, a, world_a, world_b, day = runs[True]
    b_stub = type("B", (), {"id": B_ID})()
    requests = iso._expanded_requests(
        method, path, "noninterference", None, a, b_stub, world_a, world_a, day,
    )
    known = {str(i) for i in (A_ID, *world_a.values()) if isinstance(i, uuid.UUID)}
    known |= {i.hex for i in (A_ID, *world_a.values()) if isinstance(i, uuid.UUID)}
    b_keys = {
        B_ID, *(v for v in world_b.values() if isinstance(v, uuid.UUID)),
        *INFLUENCERS.values(), *B_HISTORY.values(),
    }
    b_course = world_b["courses"]
    token = create_access_token(A_ID, 0)

    try:
        for url, query, body in requests:
            answers = {}
            pushed_to = {}
            for with_b, (engine, session, *_rest) in runs.items():
                before_sends = len(_no_push_network)
                app.main.app.dependency_overrides[get_db] = _yielding(session)
                response = TestClient(app.main.app, raise_server_exceptions=bool(__import__("os").getenv("ISOLATION_RAISE"))).request(
                    method, url, params=query, json=body, headers={"Authorization": f"Bearer {token}"},
                )
                session.rollback()
                pushed_to[with_b] = sorted(e for e, _h, _b in _no_push_network[before_sends:])
                answers[with_b] = (
                    response.status_code,
                    _normalise(response.text, known),
                    _a_rows(snapshot(session), b_keys, b_course, known),
                )
            with_b, alone = answers[True], answers[False]
            # Push: A's request may only ever reach A's devices, B or no B.
            assert pushed_to[True] == pushed_to[False], (
                f"{method} {url}: sent to {pushed_to[True]} with B present, {pushed_to[False]} without"
            )
            # Not vacuous. The first version of this file overrode get_db with
            # `lambda s=session: s`; FastAPI read the default as a query
            # parameter and every request in both runs was the same 500, so
            # every case "agreed" and passed.
            assert alone[0] < 500, f"{method} {url}: {alone[0]} {alone[1][:300]}"
            # 401/403/404 on A's own path means the request never reached the
            # code under test (a token or wiring fault). A domain refusal such as
            # "Course has no final exam" is a real answer and compares fine.
            if (method, path) not in DOMAIN_404:
                assert alone[0] not in (401, 403, 404), f"{method} {url}: {alone[0]} {alone[1][:300]}"
            assert with_b[0] == alone[0], (
                f"{method} {url}: {with_b[0]} with B present, {alone[0]} without -- B's data "
                f"changed the outcome.\nbody: {body}\nwith B: {with_b[1][:300]}\nalone: {alone[1][:300]}"
            )
            assert with_b[1] == alone[1], (
                f"{method} {url}: the response differs when B exists.\nbody: {body}\n"
                f"with B: {with_b[1][:600]}\nalone:  {alone[1][:600]}"
            )
            for table in with_b[2]:
                assert with_b[2][table] == alone[2][table], (
                    f"{method} {url}: A's {table} rows end up different when B exists."
                )
    finally:
        app.main.app.dependency_overrides.clear()
        for engine, session, *_rest in runs.values():
            session.close()
            engine.dispose()
