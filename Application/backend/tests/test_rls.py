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

from app._database import rls, teams
from app._database.identity import act_as, email_taken, user_id_by_email
from app._database.models import AccountModel, Base, GradeModel, UserModel
from app.shared.dates import user_today
from tests.conftest import TEST_DATABASE_URL, TESTING_SQLITE, connect_args_for, make_course, make_user
from tests.isolation_world import seed_catalogue, seed_pair, seed_world, snapshot

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
        seed_catalogue(session)
        pair_a, pair_b = seed_pair(session, a.id, b.id, "zzownera", "zzvictimb")
        world_a.update(pair_a)
        world_b.update(pair_b)
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
    # Shared rows are everyone's to read.
    for table in rls.SHARED_READ_TABLES:
        owned[table] = set(snap[table])
    return owned


# --------------------------------------------------------------------------
# The policies exist, on every table, and only for the app role.
# --------------------------------------------------------------------------

def test_every_table_has_row_security_and_a_policy(owner_engine):
    with owner_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.roles, p.cmd "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_policies p ON p.tablename = c.relname AND p.policyname = :policy "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        ), {"policy": rls.POLICY}).all()
    by_table = {r.relname: r for r in rows}
    for table in Base.metadata.sorted_tables:
        row = by_table[table.name]
        assert row.relrowsecurity, f"{table.name}: row level security is off"
        if table.name in rls.SEALED_TABLES:
            # Sealed (Phase 2 D25): row security on and no policy at all.
            assert row.roles is None, f"{table.name}: a sealed table has a policy for {row.roles}"
            assert not row.relforcerowsecurity
            continue
        assert row.roles == [rls.APP_ROLE], f"{table.name}: policy is for {row.roles}"
        # Shared tables are read, never written: a policy for SELECT alone.
        expected = "SELECT" if table.name in rls.SHARED_READ_TABLES else "ALL"
        assert row.cmd == expected, f"{table.name}: policy covers {row.cmd}, not {expected}"
        # Not forced: forcing would bind the owner, which is what today's API
        # connects as, and it would see nothing. See rls.py.
        assert not row.relforcerowsecurity, f"{table.name}: FORCE would lock the owner out"


def test_the_app_role_is_granted_the_model_tables_and_nothing_else(owner_engine):
    """A table no model builds gets no policy, so it must get no grant either.

    Production held ``category_budgets``, left by a rollback, until it was
    dropped on 2026-10-19. A blanket ``GRANT ... ON ALL TABLES`` would have
    handed the app role every user's rows in it, with no row policy in the way
    -- and the next leftover would be the same.
    """
    with owner_engine.begin() as conn:
        conn.execute(text("CREATE TABLE rls_stray (id int, user_id uuid)"))
    try:
        rls.install(owner_engine)
        with owner_engine.connect() as conn:
            def granted(table):
                return conn.execute(
                    text("SELECT has_table_privilege(:r, :t, 'SELECT')"),
                    {"r": rls.APP_ROLE, "t": table},
                ).scalar()
            assert not granted("rls_stray")
            for table in Base.metadata.sorted_tables:
                if table.name in rls.SEALED_TABLES:
                    assert not granted(table.name), f"{table.name}: sealed, but the app role can read it"
                    continue
                assert granted(table.name), f"{table.name}: the app role cannot read it"
    finally:
        with owner_engine.begin() as conn:
            conn.execute(text("DROP TABLE rls_stray"))


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
# Shared tables (Phase 2 item 1): read by everyone identified, written by no
# one but their owner.
# --------------------------------------------------------------------------

SHARED_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def _privileges(conn, role, table):
    return {
        p for p in SHARED_PRIVILEGES
        if conn.execute(text("SELECT has_table_privilege(:r, :t, :p)"),
                        {"r": role, "t": table, "p": p}).scalar()
    }


def test_the_app_role_may_only_read_shared_tables(owner_engine):
    with owner_engine.connect() as conn:
        for table in sorted(rls.SHARED_READ_TABLES):
            assert _privileges(conn, rls.APP_ROLE, table) == {"SELECT"}, table


def test_a_write_grant_left_on_a_shared_table_is_taken_back(owner_engine):
    """A grant from an earlier shape of the table, or made by hand, must not survive install."""
    table = sorted(rls.SHARED_READ_TABLES)[0]
    with owner_engine.begin() as conn:
        conn.execute(text(f"GRANT ALL ON {table} TO {rls.APP_ROLE}"))
    rls.install(owner_engine)
    with owner_engine.connect() as conn:
        assert _privileges(conn, rls.APP_ROLE, table) == {"SELECT"}


@pytest.mark.parametrize("statement", [
    "INSERT INTO catalogue_courses (id, campus, subject, number, created_at) "
    "VALUES (gen_random_uuid(), 'UBCV', 'PLNT', '101', now())",
    "UPDATE catalogue_courses SET title = 'planted'",
    "DELETE FROM catalogue_prerequisites",
    "TRUNCATE catalogue_prerequisites",
    "UPDATE catalogue_prerequisites SET rule = '{}'",
])
def test_the_app_role_cannot_write_a_shared_table(worlds, app_session, statement):
    owner, a, *_ = worlds
    act_as(app_session, a.id)
    before = snapshot(owner)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text(statement))
    app_session.rollback()
    after = snapshot(owner)
    for table in rls.SHARED_READ_TABLES:
        assert after[table] == before[table] and after[table], table


def test_every_identified_user_reads_the_same_shared_rows(worlds, app_session):
    owner, a, b, _, _ = worlds
    everything = snapshot(owner)
    for person in (a, b):
        act_as(app_session, person.id)
        for table in sorted(rls.SHARED_READ_TABLES):
            seen = set(app_session.execute(text(f"SELECT id FROM {table}")).scalars())
            assert seen == set(everything[table]) and seen, table
        app_session.rollback()


SUPABASE_ROLES = ("anon", "authenticated", "service_role")


def test_supabase_default_grants_on_a_shared_table_are_taken_away(owner_engine):
    """Supabase grants every new table to anon and authenticated by name, with
    TRUNCATE among the privileges -- and TRUNCATE ignores row-level security.

    Modelled here, as plain Postgres has neither role: grant them everything,
    install again, and they must be left with nothing.
    """
    with owner_engine.begin() as conn:
        for role in SUPABASE_ROLES:
            if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar():
                conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        for table in rls.SHARED_READ_TABLES:
            conn.execute(text(f"GRANT ALL ON {table} TO PUBLIC"))
            for role in SUPABASE_ROLES:
                conn.execute(text(f"GRANT ALL ON {table} TO {role}"))
    rls.install(owner_engine)
    with owner_engine.connect() as conn:
        for table in sorted(rls.SHARED_READ_TABLES):
            for role in SUPABASE_ROLES:
                assert _privileges(conn, role, table) == set(), f"{role} on {table}"


def test_supabase_default_grants_on_every_table_are_taken_away(owner_engine):
    """Phase 3 D6. The same default grants sat on every per-user table: the
    install locked down shared and sealed tables only, and batch 1's read-back
    showed anon, authenticated and service_role holding everything on the two
    new ones. Every model table now, not a sample, and the app role keeps
    exactly what its kind allows -- the revoke must not take that too.
    """
    with owner_engine.begin() as conn:
        for role in SUPABASE_ROLES:
            if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar():
                conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        for table in Base.metadata.sorted_tables:
            conn.execute(text(f"GRANT ALL ON {table.name} TO PUBLIC"))
            for role in SUPABASE_ROLES:
                conn.execute(text(f"GRANT ALL ON {table.name} TO {role}"))
    rls.install(owner_engine)

    full = {"SELECT", "INSERT", "UPDATE", "DELETE"}
    with owner_engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for role in (*SUPABASE_ROLES, "public"):
                assert _privileges(conn, role, table.name) == set(), f"{role} on {table.name}"
            expected = (
                set() if table.name in rls.SEALED_TABLES
                else {"SELECT"} if table.name in rls.SHARED_READ_TABLES
                else {"SELECT", "DELETE"} if table.name in rls.NO_DIRECT_WRITE_TABLES
                else full
            )
            assert _privileges(conn, rls.APP_ROLE, table.name) == expected, table.name


def test_a_stray_login_cannot_truncate_a_users_table(owner_engine):
    """TRUNCATE is the one thing row-level security does not stop, so a role
    granted it by default could empty every user's rows at once."""
    with owner_engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'rls_outsider'")).scalar():
            conn.execute(text("CREATE ROLE rls_outsider LOGIN PASSWORD 'outsider_test_only'"))
        conn.execute(text("GRANT ALL ON job_applications TO rls_outsider"))
    rls.install(owner_engine)
    url = make_url(TEST_DATABASE_URL).set(username="rls_outsider", password="outsider_test_only")
    outsider = create_engine(url, connect_args=connect_args_for(TEST_DATABASE_URL))
    try:
        for statement in ("SELECT count(*) FROM job_applications", "TRUNCATE job_applications CASCADE"):
            with outsider.connect() as conn:
                with pytest.raises(ProgrammingError, match="permission denied"):
                    conn.execute(text(statement))
    finally:
        outsider.dispose()


def test_a_stray_login_cannot_read_or_write_a_shared_table(owner_engine):
    with owner_engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'rls_outsider'")).scalar():
            conn.execute(text("CREATE ROLE rls_outsider LOGIN PASSWORD 'outsider_test_only'"))
        conn.execute(text("GRANT ALL ON catalogue_courses TO rls_outsider"))
    rls.install(owner_engine)
    url = make_url(TEST_DATABASE_URL).set(username="rls_outsider", password="outsider_test_only")
    outsider = create_engine(url, connect_args=connect_args_for(TEST_DATABASE_URL))
    try:
        for statement in ("SELECT count(*) FROM catalogue_courses", "TRUNCATE catalogue_courses"):
            with outsider.connect() as conn:
                with pytest.raises(ProgrammingError, match="permission denied"):
                    conn.execute(text(statement))
    finally:
        outsider.dispose()


# --------------------------------------------------------------------------
# Reads: nothing without an identity, exactly your own rows with one.
# --------------------------------------------------------------------------

def test_no_identity_sees_no_rows_at_all(worlds, app_session):
    owner = worlds[0]
    for table in Base.metadata.sorted_tables:
        # Not vacuous: the rows are there, for the owner.
        assert owner.execute(text(f"SELECT count(*) FROM {table.name}")).scalar(), table.name
        if table.name in rls.SEALED_TABLES:
            continue  # refused outright, not merely empty: see the sealed tests below
        count = app_session.execute(text(f"SELECT count(*) FROM {table.name}")).scalar()
        assert count == 0, f"{table.name}: {count} rows visible with no identity set"


def test_an_identity_sees_exactly_its_own_rows_in_every_table(worlds, app_session):
    owner, a, b, world_a, world_b = worlds
    everything = snapshot(owner)
    mine = _rows_owned(everything, a.id, world_a)

    act_as(app_session, a.id)
    for table in Base.metadata.sorted_tables:
        if table.name in rls.SEALED_TABLES:
            continue  # refused outright: see the sealed tests below
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


DEFINER_SIGNATURES = (
    "account_user_id_by_email(text)",
    "account_user_id_by_google_id(text)",
    "account_email_taken(text, uuid)",
    "account_expired_user_ids(timestamp)",
    "account_release_push_endpoint(text)",
    "account_users_with_unpushed_reminders(timestamp)",
    "account_invite_preview(text)",
    "account_accept_partner_invite(text)",
    "account_end_partnership(uuid)",
    "account_partner_figures()",
    "account_task_invite_preview(text)",
    "account_accept_task_invite(text)",
    "account_shared_tasks()",
    "account_set_shared_task_done(uuid, boolean)",
    "account_edit_shared_task(uuid, text, text)",
    "account_leave_shared_task(uuid)",
    "account_event_invite_preview(text)",
    "account_accept_event_invite(text)",
    "account_shared_events()",
    "account_leave_shared_event(uuid)",
    "account_recount_grade_distributions()",
    "account_grade_distribution(text)",
    "account_recount_course_intel()",
    "account_course_intel(text)",
    "account_on_team(uuid)",
    "account_team_invite_preview(text)",
    "account_accept_team_invite(text)",
    "account_my_teams()",
    "account_team_games(uuid)",
    "account_record_team_game(uuid, date, text, integer, integer)",
    "account_confirm_team_game(uuid)",
    "account_dispute_team_game(uuid, integer, integer)",
    "account_correct_team_game(uuid, date, text, integer, integer)",
    "account_delete_team_game(uuid)",
    "account_leave_team(uuid)",
)


def test_only_the_app_role_can_call_the_cross_user_functions(owner_engine):
    """They run with the owner's rights, so nobody else may call them.

    A login with no grant -- a stray role, or Supabase's anon -- asking for an
    account by email must be refused outright, not answered.
    """
    with owner_engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'rls_outsider'")).scalar():
            conn.execute(text("CREATE ROLE rls_outsider LOGIN PASSWORD 'outsider_test_only'"))
        # Supabase's default privileges grant every new function to anon by
        # name, which a REVOKE FROM PUBLIC does not touch. Model that grant,
        # then install again: it must be taken away.
        for fn in DEFINER_SIGNATURES:
            conn.execute(text(f"GRANT EXECUTE ON FUNCTION {fn} TO rls_outsider"))
    rls.install(owner_engine)
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
            "SELECT * FROM account_invite_preview('x')",
            "SELECT account_accept_partner_invite('x')",
            "SELECT account_end_partnership(gen_random_uuid())",
            "SELECT * FROM account_partner_figures()",
            "SELECT * FROM account_task_invite_preview('x')",
            "SELECT account_accept_task_invite('x')",
            "SELECT * FROM account_shared_tasks()",
            "SELECT account_set_shared_task_done(gen_random_uuid(), true)",
            "SELECT account_edit_shared_task(gen_random_uuid(), 'x', NULL)",
            "SELECT account_leave_shared_task(gen_random_uuid())",
            "SELECT * FROM account_event_invite_preview('x')",
            "SELECT account_accept_event_invite('x')",
            "SELECT * FROM account_shared_events()",
            "SELECT account_leave_shared_event(gen_random_uuid())",
            "SELECT account_recount_grade_distributions()",
            "SELECT * FROM account_grade_distribution('x')",
            "SELECT account_recount_course_intel()",
            "SELECT * FROM account_course_intel('x')",
            "SELECT account_term_counted('2020W1')",
            "SELECT account_on_team(gen_random_uuid())",
            "SELECT * FROM account_team_invite_preview('x')",
            "SELECT account_accept_team_invite('x')",
            "SELECT * FROM account_my_teams()",
            "SELECT * FROM account_team_games(gen_random_uuid())",
            "SELECT account_record_team_game(gen_random_uuid(), current_date, 'x', 1, 1)",
            "SELECT account_confirm_team_game(gen_random_uuid())",
            "SELECT account_dispute_team_game(gen_random_uuid(), 1, 1)",
            "SELECT account_correct_team_game(gen_random_uuid(), current_date, 'x', 1, 1)",
            "SELECT account_delete_team_game(gen_random_uuid())",
            "SELECT account_leave_team(gen_random_uuid())",
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


# --------------------------------------------------------------------------
# The owner review script (Phase 2 item 6): the catalogue's only writer.
# --------------------------------------------------------------------------

def _review_module():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import catalogue_review
    return catalogue_review


def test_the_review_refuses_the_app_role(app_session):
    review = _review_module()
    with pytest.raises(review.Refused, match="the API's role"):
        review.check_connection(app_session)


def test_the_review_refuses_a_role_that_cannot_write_the_catalogue(owner_engine):
    review = _review_module()
    with owner_engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'rls_outsider'")).scalar():
            conn.execute(text("CREATE ROLE rls_outsider LOGIN PASSWORD 'outsider_test_only'"))
    url = make_url(TEST_DATABASE_URL).set(username="rls_outsider", password="outsider_test_only")
    outsider = create_engine(url, connect_args=connect_args_for(TEST_DATABASE_URL))
    session = sessionmaker(bind=outsider)()
    try:
        with pytest.raises(review.Refused, match="cannot write"):
            review.check_connection(session)
    finally:
        session.close()
        outsider.dispose()


def test_an_approval_by_the_owner_reaches_every_user_through_the_app_role(worlds, app_session):
    from app.Grades.schemas.prerequisite import RuleWrite
    from app.Grades.services.prerequisite_service import set_own

    review = _review_module()
    owner, a, b, world_a, world_b = worlds
    review.check_connection(owner)
    _truncate_catalogue(owner)
    course = make_course(owner, a.id, "CPSC_V 313")
    set_own(owner, a.id, course.id, RuleWrite(text="CPSC 213"), source="typed")
    [group] = [g for g in review.pending_groups(owner) if g.rule == {"course": "CPSC 213"}]
    review.approve(owner, group.id, session_name="2026W")

    act_as(app_session, b.id)
    rules = app_session.execute(text("SELECT rule FROM catalogue_prerequisites")).scalars().all()
    assert {"course": "CPSC 213"} in rules
    # B still cannot see A's proposal itself, only the reviewed rule.
    assert app_session.execute(text("SELECT count(*) FROM prerequisite_proposals WHERE user_id = :a"),
                               {"a": a.id}).scalar() == 0


def _truncate_catalogue(owner):
    owner.execute(text("DELETE FROM catalogue_prerequisites"))
    owner.execute(text("DELETE FROM catalogue_courses"))
    owner.commit()



# --------------------------------------------------------------------------
# Partners (Phase 2 item 10): the accept function is the only way a row is
# written for someone else, and a figure is read only across a mutual pair.
# --------------------------------------------------------------------------

def _app_invite(app_session, owner, user):
    from app.Partners.services import partner_service
    act_as(app_session, user.id)
    return partner_service.create_invite(app_session, user.id)


def test_accepting_as_the_app_role_writes_both_sides(worlds, app_session):
    from app.Partners.services import partner_service
    owner, a, b, _, _ = worlds
    owner.execute(text("DELETE FROM partnerships"))
    owner.commit()
    new = _app_invite(app_session, owner, a)
    act_as(app_session, b.id)
    assert partner_service.accept(app_session, b.id, new.token) == "accepted"
    rows = owner.execute(text("SELECT user_id, partner_id FROM partnerships")).all()
    assert {(r.user_id, r.partner_id) for r in rows} == {(a.id, b.id), (b.id, a.id)}


def test_the_app_role_cannot_write_a_partnership_row_for_someone_else(worlds, app_session):
    owner, a, b, _, _ = worlds
    act_as(app_session, a.id)
    with pytest.raises(DBAPIError, match="row-level security"):
        app_session.execute(text(
            "INSERT INTO partnerships (id, user_id, partner_id, partner_name, created_at, streak_weeks) "
            "VALUES (gen_random_uuid(), :b, :a, 'forged', now(), 0)"), {"a": a.id, "b": b.id})


def test_a_partners_figure_is_read_only_across_a_mutual_pair(worlds, app_session):
    from app._database.sharing import partner_figures
    owner, a, b, _, _ = worlds
    act_as(app_session, a.id)
    figures = partner_figures(app_session, a.id)
    assert set(figures) == {b.id} and figures[b.id].week_percent == 75.0
    app_session.rollback()
    # A's side gone -- A never agreed, or ended it -- while B's row still names
    # A and holds B's figure. A must see nothing of it.
    owner.execute(text("DELETE FROM partnerships WHERE user_id = :a"), {"a": a.id})
    owner.commit()
    act_as(app_session, a.id)
    assert partner_figures(app_session, a.id) == {}


def test_nobody_outside_a_partnership_can_end_it(worlds, app_session):
    from app._database.sharing import end_partnership
    owner, a, b, _, _ = worlds
    stranger = make_user(owner, "rls-stranger@example.com")
    owner.commit()
    act_as(app_session, stranger.id)
    assert end_partnership(app_session, stranger.id, a.id) is False
    assert owner.execute(text("SELECT count(*) FROM partnerships")).scalar() == 2


def test_with_no_identity_the_partner_functions_do_nothing(worlds, app_session):
    import hashlib
    owner = worlds[0]
    # A live invite of A's: the functions take the token's hash, as the app sends.
    live = hashlib.sha256(b"zzownera invite token").hexdigest()
    act_as(app_session, worlds[2].id)
    assert app_session.execute(text("SELECT * FROM account_invite_preview(:h)"), {"h": live}).all(), \
        "not vacuous: with an identity the invite is found"
    app_session.rollback()
    app_session.info.clear()
    assert app_session.execute(text("SELECT * FROM account_partner_figures()")).all() == []
    assert app_session.execute(text("SELECT account_accept_partner_invite(:h)"), {"h": live}).scalar() == "invalid"
    assert app_session.execute(text("SELECT * FROM account_invite_preview(:h)"), {"h": live}).all() == []
    assert app_session.execute(text("SELECT account_end_partnership(gen_random_uuid())")).scalar() is False
    app_session.rollback()
    assert owner.execute(text("SELECT count(*) FROM partnerships")).scalar() == 2


# --------------------------------------------------------------------------
# Shared tasks (Phase 2 item 9a, D23): membership is written only by the
# accept function, and a member reaches the owner's task only through the
# functions -- never through the tasks table.
# --------------------------------------------------------------------------

def _shared_task(worlds):
    """A's task, which the world has shared with B (isolation_world.seed_pair)."""
    owner, a, b, world_a, _ = worlds
    return owner.execute(text("SELECT task_id FROM task_members WHERE id = :m"),
                         {"m": world_a["task_members"]}).scalar()


def test_the_app_role_cannot_put_anyone_on_a_task_or_rename_them(worlds, app_session):
    """Not even the task's owner: a membership row exists only because its
    member accepted a link."""
    owner, a, b, world_a, _ = worlds
    task_id = _shared_task(worlds)
    stranger = make_user(owner, "rls-planted@example.com")
    owner.commit()
    act_as(app_session, a.id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text(
            "INSERT INTO task_members (id, task_id, member_id, member_name, owner_name, joined_at) "
            "VALUES (gen_random_uuid(), :t, :s, 'planted', 'A', now())"), {"t": task_id, "s": stranger.id})
    app_session.rollback()
    act_as(app_session, a.id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text("UPDATE task_members SET member_name = 'renamed'"))
    app_session.rollback()
    # Removing someone from your own task is the owner's to do.
    act_as(app_session, a.id)
    removed = app_session.execute(text("DELETE FROM task_members WHERE id = :m"),
                                  {"m": world_a["task_members"]}).rowcount
    app_session.commit()
    assert removed == 1


def test_accepting_a_task_link_as_the_app_role_adds_only_the_caller(worlds, app_session):
    from app.Tasks.services import task_sharing_service as shares
    owner, a, b, _, _ = worlds
    task_id = _shared_task(worlds)
    joiner = make_user(owner, "rls-joiner@example.com")
    owner.commit()
    act_as(app_session, a.id)
    new = shares.new_link(app_session, a.id, task_id)
    act_as(app_session, joiner.id)
    assert shares.accept(app_session, joiner.id, new.token) == "accepted"
    members = owner.execute(text("SELECT member_id FROM task_members WHERE task_id = :t"), {"t": task_id}).scalars()
    assert set(members) == {b.id, joiner.id}


def test_a_member_reaches_the_task_only_through_the_functions(worlds, app_session):
    from app._database import sharing
    owner, a, b, _, _ = worlds
    task_id = _shared_task(worlds)
    act_as(app_session, b.id)
    # The table itself stays A's alone.
    assert app_session.execute(text("SELECT count(*) FROM tasks WHERE id = :t"), {"t": task_id}).scalar() == 0
    assert app_session.execute(text("UPDATE tasks SET title = 'b was here' WHERE id = :t"),
                               {"t": task_id}).rowcount == 0
    app_session.rollback()
    act_as(app_session, b.id)
    assert [t.task_id for t in sharing.shared_tasks(app_session, b.id)] == [task_id]
    act_as(app_session, b.id)
    assert sharing.set_shared_task_done(app_session, b.id, task_id, True) is True
    done, title = owner.execute(text("SELECT done, title FROM tasks WHERE id = :t"), {"t": task_id}).one()
    assert done is True and "b was here" not in title


def test_a_member_of_one_task_reaches_no_other(worlds, app_session):
    from app._database import sharing
    owner, a, b, world_a, world_b = worlds
    other = uuid.uuid4()
    owner.execute(text("INSERT INTO tasks (id, user_id, title, tags, priority, done, archived, created_at) "
                       "VALUES (:id, :a, 'not shared', '[]', 3, false, false, now())"), {"id": other, "a": a.id})
    owner.commit()
    act_as(app_session, b.id)
    assert sharing.set_shared_task_done(app_session, b.id, other, True) is False
    act_as(app_session, b.id)
    assert sharing.edit_shared_task(app_session, b.id, other, "mine", None) is False
    assert owner.execute(text("SELECT done FROM tasks WHERE id = :t"), {"t": other}).scalar() is False
    # And a stranger, on the shared one.
    stranger = make_user(owner, "rls-task-stranger@example.com")
    owner.commit()
    act_as(app_session, stranger.id)
    assert sharing.shared_tasks(app_session, stranger.id) == []
    act_as(app_session, stranger.id)
    assert sharing.leave_shared_task(app_session, stranger.id, _shared_task(worlds)) is False
    assert owner.execute(text("SELECT count(*) FROM task_members")).scalar() == 2


def test_with_no_identity_the_task_functions_do_nothing(worlds, app_session):
    import hashlib
    owner, a, b, _, _ = worlds
    task_id = _shared_task(worlds)
    live = hashlib.sha256(b"zzownera task invite token").hexdigest()
    act_as(app_session, b.id)
    assert app_session.execute(text("SELECT * FROM account_task_invite_preview(:h)"), {"h": live}).all(), \
        "not vacuous: with an identity the link is found"
    assert app_session.execute(text("SELECT * FROM account_shared_tasks()")).all(), \
        "not vacuous: with an identity B sees A's shared task"
    app_session.rollback()
    app_session.info.clear()
    assert app_session.execute(text("SELECT * FROM account_task_invite_preview(:h)"), {"h": live}).all() == []
    assert app_session.execute(text("SELECT account_accept_task_invite(:h)"), {"h": live}).scalar() == "invalid"
    assert app_session.execute(text("SELECT * FROM account_shared_tasks()")).all() == []
    for call in ("SELECT account_set_shared_task_done(:t, true)",
                 "SELECT account_edit_shared_task(:t, 'x', NULL)",
                 "SELECT account_leave_shared_task(:t)"):
        assert app_session.execute(text(call), {"t": task_id}).scalar() is False, call
    app_session.rollback()
    assert owner.execute(text("SELECT count(*) FROM task_members")).scalar() == 2
    assert owner.execute(text("SELECT done FROM tasks WHERE id = :t"), {"t": task_id}).scalar() is False


# --------------------------------------------------------------------------
# Shared events (Phase 2 item 9b, D24): the same boundary, and a member only
# ever reads the event.
# --------------------------------------------------------------------------

def _shared_event(worlds):
    """A's study group, which the world has shared with B."""
    owner, a, b, world_a, _ = worlds
    return owner.execute(text("SELECT event_id FROM event_members WHERE id = :m"),
                         {"m": world_a["event_members"]}).scalar()


def test_the_app_role_cannot_put_anyone_on_an_event(worlds, app_session):
    owner, a, b, world_a, _ = worlds
    event_id = _shared_event(worlds)
    stranger = make_user(owner, "rls-planted-event@example.com")
    owner.commit()
    act_as(app_session, a.id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text(
            "INSERT INTO event_members (id, event_id, member_id, member_name, owner_name, joined_at) "
            "VALUES (gen_random_uuid(), :e, :s, 'planted', 'A', now())"), {"e": event_id, "s": stranger.id})
    app_session.rollback()
    act_as(app_session, a.id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text("UPDATE event_members SET member_name = 'renamed'"))
    app_session.rollback()
    act_as(app_session, a.id)
    assert app_session.execute(text("DELETE FROM event_members WHERE id = :m"),
                               {"m": world_a["event_members"]}).rowcount == 1
    app_session.commit()


def test_a_member_sees_the_event_only_through_the_function(worlds, app_session):
    from app._database import sharing
    owner, a, b, _, _ = worlds
    event_id = _shared_event(worlds)
    act_as(app_session, b.id)
    assert app_session.execute(text("SELECT count(*) FROM events WHERE id = :e"), {"e": event_id}).scalar() == 0
    assert app_session.execute(text("UPDATE events SET title = 'b was here' WHERE id = :e"),
                               {"e": event_id}).rowcount == 0
    app_session.rollback()
    act_as(app_session, b.id)
    assert [e.event_id for e in sharing.shared_events(app_session, b.id)] == [event_id]
    assert "b was here" not in owner.execute(text("SELECT title FROM events WHERE id = :e"), {"e": event_id}).scalar()


def test_a_stranger_sees_no_event_and_cannot_take_anyone_off(worlds, app_session):
    from app._database import sharing
    owner, a, b, _, _ = worlds
    stranger = make_user(owner, "rls-event-stranger@example.com")
    owner.commit()
    act_as(app_session, stranger.id)
    assert sharing.shared_events(app_session, stranger.id) == []
    act_as(app_session, stranger.id)
    assert sharing.leave_shared_event(app_session, stranger.id, _shared_event(worlds)) is False
    assert owner.execute(text("SELECT count(*) FROM event_members")).scalar() == 2


def test_with_no_identity_the_event_functions_do_nothing(worlds, app_session):
    import hashlib
    owner, a, b, _, _ = worlds
    event_id = _shared_event(worlds)
    live = hashlib.sha256(b"zzownera event invite token").hexdigest()
    act_as(app_session, b.id)
    assert app_session.execute(text("SELECT * FROM account_event_invite_preview(:h)"), {"h": live}).all(), \
        "not vacuous: with an identity the link is found"
    assert app_session.execute(text("SELECT * FROM account_shared_events()")).all(), \
        "not vacuous: with an identity B sees A's shared event"
    app_session.rollback()
    app_session.info.clear()
    assert app_session.execute(text("SELECT * FROM account_event_invite_preview(:h)"), {"h": live}).all() == []
    assert app_session.execute(text("SELECT account_accept_event_invite(:h)"), {"h": live}).scalar() == "invalid"
    assert app_session.execute(text("SELECT * FROM account_shared_events()")).all() == []
    assert app_session.execute(text("SELECT account_leave_shared_event(:e)"), {"e": event_id}).scalar() is False
    app_session.rollback()
    assert owner.execute(text("SELECT count(*) FROM event_members")).scalar() == 2


# --------------------------------------------------------------------------
# The sealed grade counts (Phase 2 item 13, D25): no request reads or writes
# them, and the recount writes only groups at or above the floor.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("statement", [
    "SELECT * FROM grade_distributions",
    "INSERT INTO grade_distributions (id, course_key, term_code, bucket, contributors, computed_at) "
    "VALUES (gen_random_uuid(), 'X', '2025W1', 80, 9, now())",
    "UPDATE grade_distributions SET contributors = 99",
    "DELETE FROM grade_distributions",
    "TRUNCATE grade_distributions",
])
def test_the_app_role_can_neither_read_nor_write_the_grade_counts(worlds, app_session, statement):
    act_as(app_session, worlds[1].id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text(statement))


def test_supabase_style_grants_on_the_grade_counts_are_taken_away(owner_engine):
    with owner_engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'rls_outsider'")).scalar():
            conn.execute(text("CREATE ROLE rls_outsider LOGIN PASSWORD 'outsider_test_only'"))
        conn.execute(text("GRANT ALL ON grade_distributions TO rls_outsider"))
        conn.execute(text(f"GRANT ALL ON grade_distributions TO {rls.APP_ROLE}"))
    rls.install(owner_engine)
    with owner_engine.connect() as conn:
        for role in ("rls_outsider", rls.APP_ROLE):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert not conn.execute(text("SELECT has_table_privilege(:r, 'grade_distributions', :p)"),
                                        {"r": role, "p": privilege}).scalar(), (role, privilege)


def _contributors(owner, n, course_key, grade):
    """n people, each with a course graded `grade` and a review opted in."""
    from app._database.models import CourseModel, TermReviewModel
    for i in range(n):
        person = make_user(owner, f"rls-contrib-{course_key[-3:]}-{grade}-{i}@example.com")
        course = CourseModel(id=uuid.uuid4(), user_id=person.id, code="CPSC 221", name="Algorithms",
                             semester="Fall", year=2, credits=4.0, final_grade=grade)
        owner.add(course)
        owner.flush()
        owner.add(TermReviewModel(id=uuid.uuid4(), user_id=person.id, course_id=course.id,
                                  course_key=course_key, term_code="2025W1", contribute_grade=True))
    owner.commit()


def test_the_recount_writes_counts_only_at_or_above_the_floor(worlds, app_session):
    from app._database import distributions
    owner = worlds[0]
    _contributors(owner, 3, "UBCV CPSC 221", 82.0)
    _contributors(owner, 2, "UBCV CPSC 221", 91.0)
    _contributors(owner, 4, "UBCV CPSC 310", 75.0)  # one short of the floor
    act_as(app_session, worlds[1].id)
    written = distributions.recount(app_session)
    rows = owner.execute(text("SELECT course_key, term_code, bucket, contributors FROM grade_distributions "
                              "ORDER BY bucket")).all()
    assert [tuple(r) for r in rows] == [("UBCV CPSC 221", "2025W1", 80, 3), ("UBCV CPSC 221", "2025W1", 90, 2)]
    assert written == 2
    columns = set(owner.execute(text("SELECT column_name FROM information_schema.columns "
                                     "WHERE table_name = 'grade_distributions'")).scalars())
    assert columns == {"id", "course_key", "term_code", "bucket", "contributors", "computed_at"}, \
        "the counts table holds no user id and nothing per contribution"


def _seal(owner, key, term, bands):
    """Rows straight into the sealed counts, as the owner, as a recount would."""
    for bucket, n in bands.items():
        owner.execute(text("INSERT INTO grade_distributions (id, course_key, term_code, bucket, contributors, "
                           "computed_at) VALUES (gen_random_uuid(), :k, :t, :b, :n, now())"),
                      {"k": key, "t": term, "b": bucket, "n": n})
    owner.commit()


def test_the_app_role_reads_a_courses_counts_only_through_the_floor_and_the_wait(worlds, app_session):
    """Phase 3 item 3 (D11): the sealed table's one door. Closed terms at the
    floor only, and only for the key asked about."""
    from datetime import date
    owner = worlds[0]
    year = date.today().year
    _seal(owner, "UBCV CPSC 110", f"{year - 2}W1", {70: 2, 80: 3})   # closed, at the floor
    _seal(owner, "UBCV CPSC 110", f"{year - 2}W2", {80: 4})          # closed, one short
    _seal(owner, "UBCV CPSC 110", f"{year}W1", {90: 9})              # still being answered
    _seal(owner, "UBCV CPSC 121", f"{year - 2}W1", {60: 9})          # another course
    act_as(app_session, worlds[1].id)
    rows = app_session.execute(text("SELECT * FROM account_grade_distribution('UBCV CPSC 110')")).all()
    assert [tuple(r) for r in rows] == [(f"{year - 2}W1", 70, 2), (f"{year - 2}W1", 80, 3)]
    app_session.rollback()
    app_session.info.clear()
    assert app_session.execute(text("SELECT * FROM account_grade_distribution('UBCV CPSC 110')")).all() == [], \
        "with no identity the door answers nothing"


@pytest.mark.parametrize("table", sorted(rls.SEALED_TABLES))
@pytest.mark.parametrize("statement", ["SELECT * FROM {t}", "UPDATE {t} SET id = id", "DELETE FROM {t}",
                                       "TRUNCATE {t}"])
def test_no_sealed_table_can_be_read_or_written_by_the_app_role(worlds, app_session, table, statement):
    """Phase 3 D11: every aggregate is sealed, whatever it holds."""
    act_as(app_session, worlds[1].id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text(statement.format(t=table)))


def test_the_course_figures_are_rebuilt_at_the_floor_and_read_only_through_it(worlds, app_session):
    """Phase 3 item 5: the recount, run as the app role, writes a course only at
    5 answers; the door answers it to a signed-in caller, and nothing without one."""
    from datetime import date
    from app._database.models import CourseModel, TermReviewModel
    owner = worlds[0]
    counted = f"{date.today().year - 2}W1"
    for key, n in (("UBCV CPSC 110", 5), ("UBCV CPSC 121", 4)):
        for i in range(n):
            person = make_user(owner, f"rls-intel-{key[-3:]}-{i}@example.com")
            course = CourseModel(id=uuid.uuid4(), user_id=person.id, code=key[5:], name="x", semester="Fall",
                                 year=2, credits=4.0)
            owner.add(course)
            owner.flush()
            owner.add(TermReviewModel(id=uuid.uuid4(), user_id=person.id, course_id=course.id, course_key=key,
                                      term_code=counted, hours_per_week=6 + i, difficulty=3, clarity=4,
                                      would_take_again=True))
    owner.commit()
    act_as(app_session, worlds[1].id)
    assert app_session.execute(text("SELECT account_recount_course_intel()")).scalar() == 1
    app_session.commit()
    act_as(app_session, worlds[1].id)
    row = app_session.execute(text("SELECT * FROM account_course_intel('UBCV CPSC 110')")).one()
    assert (row.hours_answers, row.hours_median, row.again_share) == (5, 8.0, 100.0)
    assert app_session.execute(text("SELECT * FROM account_course_intel('UBCV CPSC 121')")).all() == []
    app_session.rollback()
    app_session.info.clear()
    assert app_session.execute(text("SELECT * FROM account_course_intel('UBCV CPSC 110')")).all() == []


def test_with_no_identity_the_recount_still_reveals_nothing(worlds, app_session):
    """It needs no identity -- the scheduler has none -- and answers with a
    number of rows, never their contents."""
    app_session.info.clear()
    answer = app_session.execute(text("SELECT account_recount_grade_distributions()")).scalar()
    assert isinstance(answer, int)


# --------------------------------------------------------------------------
# Teams (Phase 2 item 11, D26): memberships and games are written only by
# the functions -- the captain's included -- and a player reaches the team
# only through them.
# --------------------------------------------------------------------------

def _a_team(worlds):
    """A's team, which B plays on (isolation_world.seed_pair)."""
    owner, a, b, world_a, _ = worlds
    return owner.execute(text("SELECT team_id FROM team_members WHERE id = :m"),
                         {"m": world_a["team_members"]}).scalar()


@pytest.mark.parametrize("statement", [
    "INSERT INTO team_members (id, team_id, member_id, member_name, owner_name, joined_at) "
    "VALUES (gen_random_uuid(), :t, :someone, 'planted', 'A', now())",
    "UPDATE team_members SET member_name = 'renamed'",
    "INSERT INTO games (id, team_id, played_on, opponent, our_score, their_score, recorded_by, recorded_by_name, "
    "created_at) VALUES (gen_random_uuid(), :t, current_date, 'x', 9, 0, :someone, 'A', now())",
    "UPDATE games SET our_score = 99, confirmed_by = :someone, confirmed_by_name = 'A'",
])
def test_not_even_the_captain_writes_a_membership_or_a_game_directly(worlds, app_session, statement):
    owner, a, b, _, _ = worlds
    act_as(app_session, a.id)
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_session.execute(text(statement), {"t": _a_team(worlds), "someone": a.id})


def test_the_captain_can_still_take_someone_off_and_remove_a_game(worlds, app_session):
    owner, a, b, world_a, _ = worlds
    act_as(app_session, a.id)
    assert app_session.execute(text("DELETE FROM team_members WHERE id = :m"),
                               {"m": world_a["team_members"]}).rowcount == 1
    assert app_session.execute(text("DELETE FROM games WHERE id = :g"), {"g": world_a["games"]}).rowcount == 1
    app_session.commit()


def test_a_player_reaches_the_team_only_through_the_functions(worlds, app_session):
    owner, a, b, _, _ = worlds
    team_id = _a_team(worlds)
    act_as(app_session, b.id)
    for table, column in (("teams", "id"), ("games", "team_id"), ("team_members", "team_id")):
        assert app_session.execute(text(f"SELECT count(*) FROM {table} WHERE {column} = :t"),
                                   {"t": team_id}).scalar() == 0, table
    app_session.rollback()
    act_as(app_session, b.id)
    assert [t.team_id for t in teams.member_teams(app_session, b.id)] == [team_id]
    act_as(app_session, b.id)
    [game] = teams.games(app_session, b.id, team_id)
    act_as(app_session, b.id)
    assert teams.confirm_game(app_session, b.id, game.game_id) is True
    assert owner.execute(text("SELECT confirmed_by FROM games WHERE id = :g"), {"g": game.game_id}).scalar() == b.id


def test_a_stranger_reaches_no_team(worlds, app_session):
    owner, a, b, world_a, _ = worlds
    team_id = _a_team(worlds)
    stranger = make_user(owner, "rls-team-stranger@example.com")
    owner.commit()
    act_as(app_session, stranger.id)
    assert teams.games(app_session, stranger.id, team_id) == []
    act_as(app_session, stranger.id)
    assert teams.record_game(app_session, stranger.id, team_id, user_today(owner, a.id), "x", 1, 1) is None
    act_as(app_session, stranger.id)
    assert teams.confirm_game(app_session, stranger.id, world_a["games"]) is False
    act_as(app_session, stranger.id)
    assert teams.leave_team(app_session, stranger.id, team_id) is False
    assert owner.execute(text("SELECT count(*) FROM games")).scalar() == 2


def test_with_no_identity_the_team_functions_do_nothing(worlds, app_session):
    import hashlib
    owner, a, b, world_a, _ = worlds
    team_id = _a_team(worlds)
    live = hashlib.sha256(b"zzownera team invite token").hexdigest()
    act_as(app_session, b.id)
    assert app_session.execute(text("SELECT account_on_team(:t)"), {"t": team_id}).scalar() is True, \
        "not vacuous: with an identity B is on A's team"
    app_session.rollback()
    app_session.info.clear()
    p = {"t": team_id, "g": world_a["games"], "h": live}
    assert app_session.execute(text("SELECT account_on_team(:t)"), p).scalar() is False
    assert app_session.execute(text("SELECT * FROM account_team_invite_preview(:h)"), p).all() == []
    assert app_session.execute(text("SELECT account_accept_team_invite(:h)"), p).scalar() == "invalid"
    assert app_session.execute(text("SELECT * FROM account_my_teams()")).all() == []
    assert app_session.execute(text("SELECT * FROM account_team_games(:t)"), p).all() == []
    assert app_session.execute(text("SELECT account_record_team_game(:t, current_date, 'x', 1, 1)"), p).scalar() is None
    for call in ("SELECT account_confirm_team_game(:g)", "SELECT account_dispute_team_game(:g, 1, 1)",
                 "SELECT account_correct_team_game(:g, current_date, 'x', 1, 1)",
                 "SELECT account_delete_team_game(:g)", "SELECT account_leave_team(:t)"):
        assert app_session.execute(text(call), p).scalar() is False, call
    app_session.rollback()
    assert owner.execute(text("SELECT count(*) FROM games")).scalar() == 2
    assert owner.execute(text("SELECT count(*) FROM team_members")).scalar() == 2
