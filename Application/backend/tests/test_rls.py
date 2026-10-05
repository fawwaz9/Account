"""Row-level security, proven against a real Postgres as the restricted role.

Phase 0 item 2. ``app/_database/rls.py`` writes the policies; this file is the
evidence that they do what it says. Skipped on SQLite, which has no row-level
security -- run it with a local container:

    docker run -d --name account-pg-test -e POSTGRES_PASSWORD=postgres \\
        -e POSTGRES_DB=account_test -p 127.0.0.1:55432:5432 postgres:17
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/account_test \\
        .venv/bin/python -m pytest tests/test_rls.py

CI runs it against a service container on every push.

Two engines. The **owner** -- the container's superuser, standing in for the
role that owns production's tables -- seeds two users' worlds and commits them,
because a row policy only means something across connections. The **app role**
is a login with no superuser, no BYPASSRLS and no ownership, exactly what the
API will connect as; every assertion about visibility is made through it.

The rest of the suite runs inside a rolled-back transaction and never commits,
so the rows committed here are truncated at the end of each test.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app._database import rls
from app._database.identity import act_as, email_taken, user_id_by_email
from app._database.models import AccountModel, Base, GradeModel, UserModel
from app.shared.dates import user_today
from tests.conftest import TEST_DATABASE_URL, TESTING_SQLITE, connect_args_for, make_user
from tests.isolation_world import seed_world, snapshot

pytestmark = pytest.mark.skipif(TESTING_SQLITE, reason="row-level security is Postgres-only")

APP_PASSWORD = "account_app_test_only"


@pytest.fixture(scope="module")
def owner_engine(_pg_engine):
    """The schema owner, with the app role created and the policies installed."""
    with _pg_engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"),
                              {"r": rls.APP_ROLE}).scalar()
        if not exists:
            conn.execute(text(
                f"CREATE ROLE {rls.APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            ))
    rls.install(_pg_engine)
    return _pg_engine


@pytest.fixture(scope="module")
def app_engine(owner_engine):
    url = make_url(TEST_DATABASE_URL).set(username=rls.APP_ROLE, password=APP_PASSWORD)
    engine = create_engine(url, connect_args=connect_args_for(TEST_DATABASE_URL))
    yield engine
    engine.dispose()


def _truncate(engine):
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def worlds(owner_engine):
    """Two users with one row in every table, committed, then truncated."""
    _truncate(owner_engine)
    session = sessionmaker(bind=owner_engine)()
    try:
        a = make_user(session, "rls-a@example.com")
        b = make_user(session, "rls-b@example.com")
        a.google_id, b.google_id = "google-rls-a", "google-rls-b"
        session.commit()
        day = user_today(session, a.id)
        world_a = seed_world(session, a.id, "zzownera", day)
        world_b = seed_world(session, b.id, "zzvictimb", day)
        yield session, a, b, world_a, world_b
    finally:
        session.close()
        _truncate(owner_engine)


@pytest.fixture
def app_session(app_engine):
    session = sessionmaker(bind=app_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _rows_owned(snap, user_id, world):
    """{table: pks} of the rows belonging to one user in an owner's snapshot."""
    pks = set(world.values()) | {user_id}
    owned = {}
    for table, rows in snap.items():
        owned[table] = {pk for pk in rows if pk in pks}
    # course_category_weights has an integer key the world records only once
    # per user; take its rows by their course instead.
    weights = snap["course_category_weights"]
    owned["course_category_weights"] = {
        pk for pk, row in weights.items() if row["course_id"] == world["courses"]
    }
    return owned


# --------------------------------------------------------------------------
# The policies exist, on every table, and only for the app role.
# --------------------------------------------------------------------------

def test_every_table_has_row_security_and_a_policy(owner_engine):
    with owner_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.roles "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_policies p ON p.tablename = c.relname AND p.policyname = :policy "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        ), {"policy": rls.POLICY}).all()
    by_table = {r.relname: r for r in rows}
    for table in Base.metadata.sorted_tables:
        row = by_table[table.name]
        assert row.relrowsecurity, f"{table.name}: row level security is off"
        assert row.roles == [rls.APP_ROLE], f"{table.name}: policy is for {row.roles}"
        # Not forced: forcing would bind the owner, which is what today's API
        # connects as, and it would see nothing. See rls.py.
        assert not row.relforcerowsecurity, f"{table.name}: FORCE would lock the owner out"


def test_the_app_role_is_not_privileged(app_session):
    row = app_session.execute(text(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
        "FROM pg_roles WHERE rolname = current_user"
    )).one()
    assert tuple(row) == (False, False, False, False)


def test_the_app_role_cannot_change_the_schema(app_session):
    with pytest.raises((ProgrammingError, DBAPIError)):
        app_session.execute(text("ALTER TABLE accounts ADD COLUMN sneaky text"))
    app_session.rollback()
    with pytest.raises((ProgrammingError, DBAPIError)):
        app_session.execute(text("CREATE TABLE sneaky (id int)"))


# --------------------------------------------------------------------------
# Reads: nothing without an identity, exactly your own rows with one.
# --------------------------------------------------------------------------

def test_no_identity_sees_no_rows_at_all(worlds, app_session):
    for table in Base.metadata.sorted_tables:
        count = app_session.execute(text(f"SELECT count(*) FROM {table.name}")).scalar()
        assert count == 0, f"{table.name}: {count} rows visible with no identity set"


def test_an_identity_sees_exactly_its_own_rows_in_every_table(worlds, app_session):
    owner, a, b, world_a, world_b = worlds
    everything = snapshot(owner)
    mine = _rows_owned(everything, a.id, world_a)

    act_as(app_session, a.id)
    for table in Base.metadata.sorted_tables:
        visible = set(app_session.execute(text(f"SELECT id FROM {table.name}")).scalars())
        assert visible == mine[table.name], (
            f"{table.name}: as A, saw {len(visible)} rows, A owns {len(mine[table.name])}"
        )
        assert visible, f"{table.name}: the world should give A at least one row here"


def test_identity_survives_a_commit(worlds, app_session):
    """Services commit mid-request; the next transaction must still be A's."""
    _, a, _, world_a, _ = worlds
    act_as(app_session, a.id)
    app_session.execute(text("SELECT 1"))
    app_session.commit()
    seen = set(app_session.execute(text("SELECT id FROM accounts")).scalars())
    assert world_a["accounts"] in seen


# --------------------------------------------------------------------------
# Writes: another user's rows can be neither changed nor created.
# --------------------------------------------------------------------------

def test_updating_or_deleting_another_users_row_touches_nothing(worlds, app_session):
    owner, a, b, _, world_b = worlds
    act_as(app_session, a.id)
    updated = app_session.execute(
        text("UPDATE accounts SET name = 'stolen' WHERE id = :id"), {"id": world_b["accounts"]}
    ).rowcount
    deleted = app_session.execute(
        text("DELETE FROM transactions WHERE id = :id"), {"id": world_b["transactions"]}
    ).rowcount
    app_session.commit()
    assert (updated, deleted) == (0, 0)
    owner.expire_all()
    assert owner.get(AccountModel, world_b["accounts"]).name.endswith("chequing")


def test_a_row_cannot_be_written_with_another_users_id(worlds, app_session):
    _, a, b, _, _ = worlds
    act_as(app_session, a.id)
    app_session.add(AccountModel(id=uuid.uuid4(), user_id=b.id, name="planted", kind="spending",
                                 income_share=0.0, archived=False, position=9))
    with pytest.raises(DBAPIError, match="row-level security"):
        app_session.flush()


def test_a_row_cannot_be_handed_to_another_user(worlds, app_session):
    _, a, b, world_a, _ = worlds
    act_as(app_session, a.id)
    with pytest.raises(DBAPIError, match="row-level security"):
        app_session.execute(text("UPDATE accounts SET user_id = :b WHERE id = :id"),
                            {"b": b.id, "id": world_a["accounts"]})


def test_a_child_row_cannot_be_hung_under_another_users_parent(worlds, app_session):
    _, a, _, _, world_b = worlds
    act_as(app_session, a.id)
    app_session.add(GradeModel(id=uuid.uuid4(), course_id=world_b["courses"], name="planted",
                               category="Assignment", score=1.0, max_score=1.0, excluded=False))
    with pytest.raises(DBAPIError, match="row-level security"):
        app_session.flush()


# --------------------------------------------------------------------------
# The cross-user questions answer with an id or a yes/no, and nothing else.
# --------------------------------------------------------------------------

def test_sign_in_lookups_work_without_seeing_the_table(worlds, app_session):
    _, a, b, _, _ = worlds
    assert user_id_by_email(app_session, "RLS-B@example.com") == b.id
    assert email_taken(app_session, "rls-a@example.com") is True
    assert email_taken(app_session, "rls-a@example.com", except_user_id=a.id) is False
    assert app_session.query(UserModel).count() == 0


def test_lookups_are_exact_not_patterns(worlds, app_session):
    """An underscore or percent in an address is a character, not a wildcard."""
    assert user_id_by_email(app_session, "rls_a@example.com") is None
    assert user_id_by_email(app_session, "%@example.com") is None
    assert email_taken(app_session, "rls-_@example.com") is False


def test_only_the_app_role_can_call_the_cross_user_functions(owner_engine):
    """They run with the owner's rights, so nobody else may call them.

    A login with no grant -- a stray role, or Supabase's anon -- asking for an
    account by email must be refused outright, not answered.
    """
    with owner_engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'rls_outsider'")).scalar():
            conn.execute(text("CREATE ROLE rls_outsider LOGIN PASSWORD 'outsider_test_only'"))
    url = make_url(TEST_DATABASE_URL).set(username="rls_outsider", password="outsider_test_only")
    outsider = create_engine(url, connect_args=connect_args_for(TEST_DATABASE_URL))
    try:
        for call in (
            "SELECT account_user_id_by_email('a@example.com')",
            "SELECT account_user_id_by_google_id('g')",
            "SELECT account_email_taken('a@example.com', NULL)",
            "SELECT account_expired_user_ids(now()::timestamp)",
            "SELECT account_release_push_endpoint('https://x')",
            "SELECT account_users_with_unpushed_reminders(now()::timestamp)",
        ):
            with outsider.connect() as conn:
                with pytest.raises(ProgrammingError, match="permission denied"):
                    conn.execute(text(call))
    finally:
        outsider.dispose()


# --------------------------------------------------------------------------
# The scheduler, as the app role: each reminder to its owner's devices only.
# --------------------------------------------------------------------------

def test_the_scheduler_delivers_each_reminder_to_its_owner_only(worlds, app_session):
    from datetime import datetime, timedelta, timezone

    from app._database.models import ReminderModel
    from app.Notifications.services.push_service import dispatch_due_reminders

    owner, a, b, _, _ = worlds
    at = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)  # 06:00 in America/Regina
    for person in (a, b):
        owner.add(ReminderModel(id=uuid.uuid4(), user_id=person.id, title=f"due {person.email}",
                                remind_at=datetime(2026, 10, 7, 5, 30)))
    owner.commit()
    deliveries = []

    def capture(endpoint, headers, body):
        deliveries.append(endpoint)
        return 201

    result = dispatch_due_reminders(app_session, capture, at=at)

    assert result["pushed"] == 2
    assert sorted(deliveries) == ["https://push.invalid/zzownera/device",
                                  "https://push.invalid/zzvictimb/device"]


# --------------------------------------------------------------------------
# The whole isolation suite, with the API connected as the app role.
# --------------------------------------------------------------------------

from tests import test_isolation as iso  # noqa: E402


@pytest.mark.parametrize(("method", "path", "variant", "leaf"), iso._cases())
def test_route_isolation_under_rls(worlds, app_engine, method, path, variant, leaf):
    """Every case of test_isolation.py, but every request runs as the app role.

    This is what proves the switch is safe to make: the API behaves the same
    under the policies, nothing it legitimately does is refused, and the three
    invariants still hold. Re-running it with an application filter removed is
    what proves the backstop -- see Ideas/overhaul/phase0-decisions.md.
    """
    from fastapi.testclient import TestClient

    import app.main
    from app._database.db import get_db
    from app.Auth.services.session_service import create_access_token

    owner, a, b, world_a, world_b = worlds
    day = user_today(owner, a.id)
    AppSession = sessionmaker(bind=app_engine)

    def per_request_session():
        session = AppSession()
        try:
            yield session
        finally:
            session.close()

    app.main.app.dependency_overrides[get_db] = per_request_session
    try:
        client = TestClient(app.main.app, raise_server_exceptions=bool(os.getenv("ISOLATION_RAISE")))
        token = create_access_token(a.id, a.session_epoch or 0)
        for url, query, body in iso._expanded_requests(method, path, variant, leaf, a, b,
                                                       world_a, world_b, day):
            before = snapshot(owner)
            response = client.request(method, url, params=query, json=body,
                                      headers={"Authorization": f"Bearer {token}"})
            after = snapshot(owner)
            problems = iso._check(before, after, b, world_b, response, url)
            assert not problems, (
                f"{method} {url} [{variant}] -> {response.status_code}\nbody: {body}\n" + "\n".join(problems)
            )
            iso._check_status(method, path, variant, response)
    finally:
        app.main.app.dependency_overrides.clear()
