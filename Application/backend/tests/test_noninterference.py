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
from app._database.models import Base, TermBlackoutModel, UserModel
from app.Auth.services.session_service import create_access_token
from app.shared.dates import user_today
from tests import test_isolation as iso
from tests.conftest import TESTING_SQLITE, _make_engine
from tests.isolation_world import seed_world, snapshot

pytestmark = pytest.mark.skipif(not TESTING_SQLITE, reason="compares two in-memory databases")

A_ID = uuid.uuid5(uuid.NAMESPACE_URL, "account-isolation-world/user-a")
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
    if with_b:
        # Influencers: rows of B's placed where they would change A's answers
        # if they leaked into A's queries, but which A's identical world cannot
        # mask. A's weekly lecture falls on `day`; a break of B's over it would
        # take A's class off A's timetable.
        session.add(TermBlackoutModel(
            id=uuid.uuid5(uuid.NAMESPACE_URL, "account-isolation-world/b-influencer-blackout"),
            user_id=B_ID, label="zzvictimb influencer", starts_on=day - timedelta(days=1),
            ends_on=day + timedelta(days=1),
        ))
        session.commit()
    return engine, session, a, world_a, world_b, day


def _normalise(text: str, known: set[str]) -> str:
    """Mask what legitimately differs between two runs: clocks, and new ids."""
    text = TIMESTAMP.sub("<ts>", text)
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
    b_keys = {B_ID, *(v for v in world_b.values() if isinstance(v, uuid.UUID)),
              uuid.uuid5(uuid.NAMESPACE_URL, "account-isolation-world/b-influencer-blackout")}
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
