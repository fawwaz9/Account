#!/usr/bin/env bash
# Let people create an account: add their addresses to ALLOWED_SIGNUP_EMAILS
# on Cloud Run.
#
#   ./invite.sh 123@gmail.com, abc@gmail.com
#   ./invite.sh --dry-run 123@gmail.com     # say what would change; change nothing
#   ./invite.sh --list                      # print who is on the list
#
# It ADDS to the list and never replaces it. An empty list means anyone can
# sign up (signup_policy.py), so the script refuses to write if it cannot read
# the current one. The list gates account creation only: removing someone from
# it never locks out an account that already exists, and this script never
# removes anyone.
#
# Each change makes a new Cloud Run revision with the same image, ready in
# about a minute. Later deploys keep the list, because `gcloud run deploy
# --image` leaves environment variables alone.
set -euo pipefail
set -f  # no globbing: an address is never a file pattern

SERVICE=account-api
REGION=us-west1
PROJECT=account-504419
VAR=ALLOWED_SIGNUP_EMAILS

dry_run=0
list_only=0
raw=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --list) list_only=1 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Unknown option: $arg" >&2; exit 2 ;;
    *) raw="$raw,$arg" ;;
  esac
done

# Read the live list. Plain value only: if it ever becomes a secret reference,
# stop rather than overwrite it with a plain one.
current=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format=json |
  python3 -c '
import json, sys
env = json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0].get("env", [])
for e in env:
    if e["name"] == sys.argv[1]:
        if "value" not in e:
            sys.exit("%s is not a plain value on Cloud Run; edit it by hand." % sys.argv[1])
        print(e["value"])
        break
' "$VAR")

if [ -z "$(echo "$current" | tr -d ' ,')" ]; then
  echo "Could not read a current $VAR (it is empty or unset). Refusing to write:" >&2
  echo "a list of only the new addresses would drop everyone already invited." >&2
  exit 1
fi

normalise() { tr ',' '\n' | tr -d ' \t\r' | tr 'A-Z' 'a-z' | sed '/^$/d'; }

if [ "$list_only" = 1 ]; then
  echo "$current" | normalise | sort -u
  exit 0
fi

if [ -z "$(echo "$raw" | tr -d ' ,')" ]; then
  echo "Usage: ./invite.sh someone@example.com, other@example.com" >&2
  exit 2
fi

added=()
already=()
for email in $(echo "$raw" | normalise | sort -u); do
  if ! echo "$email" | grep -Eq '^[^@,[:space:]]+@[^@,[:space:]]+\.[^@,[:space:]]+$'; then
    echo "Not an email address: $email (nothing changed)" >&2
    exit 2
  fi
  if echo "$current" | normalise | grep -Fxq "$email"; then
    already+=("$email")
  else
    added+=("$email")
  fi
done

for email in ${already[@]+"${already[@]}"}; do echo "already on the list: $email"; done
if [ ${#added[@]} -eq 0 ]; then
  echo "Nothing to add."
  exit 0
fi
for email in "${added[@]}"; do echo "adding: $email"; done

merged=$( { echo "$current" | normalise; printf '%s\n' "${added[@]}"; } | sort -u | paste -sd, -)
count=$(echo "$merged" | tr ',' '\n' | wc -l | tr -d ' ')

if [ "$dry_run" = 1 ]; then
  echo "Dry run: the list would go to $count addresses. Nothing changed."
  exit 0
fi

# The value holds commas, gcloud's own separator, so pick another one (^|^).
gcloud run services update "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --update-env-vars "^|^$VAR=$merged" --quiet

# Read it back: every address that was meant to be added must now be there.
after=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --format=json | python3 -c '
import json, sys
env = json.load(sys.stdin)["spec"]["template"]["spec"]["containers"][0].get("env", [])
print(next((e.get("value", "") for e in env if e["name"] == sys.argv[1]), ""))
' "$VAR")
for email in "${added[@]}"; do
  if ! echo "$after" | normalise | grep -Fxq "$email"; then
    echo "WARNING: $email is not on the list after the update. Check Cloud Run." >&2
    exit 1
  fi
done
echo "Done: $count addresses on the list. They can create an account now."
