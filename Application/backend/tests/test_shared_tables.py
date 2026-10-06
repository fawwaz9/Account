"""The policy generator's rules for shared tables (Phase 2 item 1, D9).

These run everywhere, SQLite included, because they are about what the
generator writes, not what Postgres does with it. tests/test_rls.py proves the
written policy on Postgres.
"""
import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table
from sqlalchemy.types import Uuid

from app._database import rls
from app._database.models import Base


def test_an_ownerless_table_off_the_list_still_raises():
    stray = Table("stray_world_facts", MetaData(), Column("id", Integer, primary_key=True),
                  Column("fact", String))
    with pytest.raises(ValueError, match="no user_id and no single owning parent"):
        rls.owner_predicate(stray)
    assert rls.is_shared(stray) is False


def test_a_per_user_table_cannot_be_shared_by_naming_it(monkeypatch):
    monkeypatch.setattr(rls, "SHARED_READ_TABLES", rls.SHARED_READ_TABLES | {"accounts"})
    with pytest.raises(ValueError, match="has an owner"):
        rls.policy_statements()
    with pytest.raises(ValueError, match="has an owner"):
        rls.grant_statements()


def test_a_child_of_a_per_user_table_cannot_be_shared_by_naming_it(monkeypatch):
    monkeypatch.setattr(rls, "SHARED_READ_TABLES", rls.SHARED_READ_TABLES | {"grades"})
    with pytest.raises(ValueError, match="has an owner"):
        rls.policy_statements()


def test_users_cannot_be_shared_by_naming_it(monkeypatch):
    monkeypatch.setattr(rls, "SHARED_READ_TABLES", rls.SHARED_READ_TABLES | {"users"})
    with pytest.raises(ValueError, match="has an owner"):
        rls.policy_statements()


def test_a_misspelt_shared_name_raises(monkeypatch):
    monkeypatch.setattr(rls, "SHARED_READ_TABLES", rls.SHARED_READ_TABLES | {"catalog_courses"})
    with pytest.raises(ValueError, match="no model builds"):
        rls.policy_statements()


def test_every_shared_name_is_a_model_table_without_an_owner():
    for name in rls.SHARED_READ_TABLES:
        table = Base.metadata.tables[name]
        assert "user_id" not in table.columns
        assert rls.is_shared(table)


def _for(statements, table):
    return [s for s in statements if f" {table} " in f"{s} " or f"public.{table}" in s]


@pytest.mark.parametrize("table", sorted(rls.SHARED_READ_TABLES))
def test_a_shared_table_gets_a_select_policy_and_nothing_else(table):
    policies = [s for s in _for(rls.policy_statements(), table) if s.startswith("CREATE POLICY")]
    assert len(policies) == 1
    assert f"FOR SELECT TO {rls.APP_ROLE}" in policies[0]
    assert "WITH CHECK" not in policies[0]
    assert rls.SHARED_PREDICATE in policies[0]


@pytest.mark.parametrize("table", sorted(rls.SHARED_READ_TABLES))
def test_a_shared_table_is_granted_select_only(table):
    grants = [s for s in _for(rls.grant_statements(), table) if s.startswith("GRANT")]
    assert grants == [f"GRANT SELECT ON {table} TO {rls.APP_ROLE}"]
    revokes = _for(rls.grant_statements(), table)
    assert f"REVOKE {rls.WRITE_PRIVILEGES} ON {table} FROM {rls.APP_ROLE}" in revokes
    assert f"REVOKE ALL ON {table} FROM PUBLIC" in revokes


def test_per_user_tables_keep_their_four_verbs():
    grants = rls.grant_statements()
    for table in Base.metadata.sorted_tables:
        if table.name in rls.SHARED_READ_TABLES:
            continue
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table.name} TO {rls.APP_ROLE}" in grants


def test_the_shared_predicate_still_needs_an_identity():
    """Not `true`: an un-identified query sees nothing, shared table or not."""
    assert rls.SHARED_PREDICATE == "account_current_user() IS NOT NULL"


def test_a_shared_child_of_a_shared_table_is_not_mistaken_for_owned():
    """catalogue_prerequisites hangs off catalogue_courses, which has no user_id,
    so it has no owning parent -- the generator must not see one."""
    meta = MetaData()
    parent = Table("p", meta, Column("id", Uuid, primary_key=True))
    child = Table("c", meta, Column("id", Uuid, primary_key=True),
                  Column("p_id", Uuid, ForeignKey("p.id"), nullable=False))
    assert rls._owner_parent(child) is None
    _ = parent
