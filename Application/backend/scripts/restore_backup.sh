#!/usr/bin/env bash
# Restore a backup artifact into a Postgres database.
#
# Step 34 of Ideas/deployment.md. You will run this while something is broken
# and you are stressed, which is the worst possible time to work out the two
# things below -- so they are handled here rather than remembered.
#
#   ./scripts/restore_backup.sh account-2026-09-15.sql.gz "postgresql://...:5432/postgres"
#
# Get a backup artifact with:
#   gh run download --repo fawwaz9/Account --name account-db-YYYY-MM-DD --dir .
set -euo pipefail

DUMP="${1:?usage: restore_backup.sh <dump.sql[.gz]> <target-url>}"
TARGET="${2:?usage: restore_backup.sh <dump.sql[.gz]> <target-url>}"

# ---------------------------------------------------------------- the guard --
# Checked before anything else, including whether the dump exists. The wrong
# target is the mistake that destroys data; a missing file is an inconvenience.
# Ordering them the other way means you meet the harmless error first, fix it,
# and only then find out you were aimed at production.
# This script drops a schema. Pointed at production it destroys exactly what it
# was run to rescue. The comparison is on the Supabase project reference, which
# is the username -- not on the whole string, since host and port are identical
# between a project's two poolers and between projects in the same region.
if [ -n "${SUPABASE_DATABASE_URL:-}" ]; then
  prod_ref=$(printf '%s' "$SUPABASE_DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
  targ_ref=$(printf '%s' "$TARGET"                | sed -n 's|.*://\([^:]*\):.*|\1|p')
  if [ "$prod_ref" = "$targ_ref" ]; then
    echo "REFUSING: the target is the production project ($prod_ref)." >&2
    echo "Restore into a second project, then repoint the app once it checks out." >&2
    exit 3
  fi
  echo "production: $prod_ref"
  echo "target:     $targ_ref   (different -- proceeding)"
else
  echo "WARNING: SUPABASE_DATABASE_URL is not set, so the production guard cannot run." >&2
  echo "Confirm by eye that the target is NOT production, then re-run with it set." >&2
  exit 3
fi

# Port 5432 is the session pooler. A restore runs DDL and long COPYs inside one
# transaction, which transaction-mode pooling (6543) may split across backends.
case "$TARGET" in
  *:6543/*) echo "WARNING: that is the transaction pooler. Use port 5432 for a restore." >&2 ;;
esac

[ -f "$DUMP" ] || { echo "no such dump: $DUMP" >&2; exit 2; }

WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
case "$DUMP" in
  *.gz) gzip -dc "$DUMP" > "$WORK/dump.sql" ;;
  *)    cp "$DUMP" "$WORK/dump.sql" ;;
esac
echo "dump: $(wc -c < "$WORK/dump.sql") bytes, $(grep -c '^CREATE TABLE' "$WORK/dump.sql") tables"

# The server is Postgres 17 and most client images ship 16, which refuses a
# newer server outright. Run the client from the matching image.
PG=postgres:17-alpine

# DROP only -- do NOT recreate. The dump carries its own CREATE SCHEMA public,
# and recreating it here makes that line fail, which aborts the whole restore
# under --single-transaction. This is the exact error step 34 was written to
# catch: "schema public already exists", from a backup that is perfectly good.
echo "dropping the target's public schema…"
docker run --rm "$PG" psql --set=ON_ERROR_STOP=1 -q "$TARGET" \
  -c "DROP SCHEMA IF EXISTS public CASCADE;"

echo "restoring…"
docker run --rm -i -v "$WORK:/d" "$PG" \
  psql --single-transaction --set=ON_ERROR_STOP=1 -q "$TARGET" -f /d/dump.sql

echo "verifying row counts against the dump…"
docker run --rm -i -v "$WORK:/d" "$PG" psql -At "$TARGET" \
  -c "SELECT sum(n) FROM (SELECT (xpath('/row/c/text()', query_to_xml(
        format('select count(*) as c from %I.%I', table_schema, table_name),
        false, true, '')))[1]::text::int AS n
      FROM information_schema.tables
      WHERE table_schema='public' AND table_type='BASE TABLE') t" > "$WORK/actual"

expected=$(awk '/^COPY public\./{f=1;next} /^\\\.$/{f=0;next} f' "$WORK/dump.sql" | wc -l | tr -d ' ')
actual=$(tr -d '[:space:]' < "$WORK/actual")
echo "  dump: ${expected} rows   restored: ${actual} rows"
[ "$expected" = "$actual" ] || { echo "ROW COUNT MISMATCH" >&2; exit 1; }
echo "restore complete and verified."
