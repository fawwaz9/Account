#!/usr/bin/env bash
# Run the CI/CD pipeline from one command, and come back with the logs when
# something fails.
#
#   ./Application/deploy.run.sh ci            wait for CI on the current commit
#   ./Application/deploy.run.sh api  [--yes]  CI, then push to `ship`: the API deploy
#   ./Application/deploy.run.sh web  [--yes]  CI, then push to `main`: Pages builds the frontend
#   ./Application/deploy.run.sh all  [--yes]  CI -> API -> frontend, stopping at the first failure
#   ./Application/deploy.run.sh check-web     read-only: is the live site this commit's build?
#
# What it does is what was done by hand: push the commit (its own branch first,
# when GitHub does not have it yet, so CI runs), find the GitHub Actions run for
# that exact commit, watch it to the end, and on failure print
# the failed steps' logs (and keep them in Application/.deploy-logs/). The
# frontend has no run to watch -- Cloudflare Pages builds it -- so instead the
# live site is compared, file by file, against a production build of the same
# commit, with content hashes in file names set aside.
#
# What it will not do, on purpose:
#   - Apply the schema. That stays a person's step (the phase runbooks, step 0);
#     the deploy's schema gate refuses code that needs a column production lacks.
#   - Force-push, or push a commit that is not a fast-forward of `ship`/`main`.
#   - Deploy a dirty tree, or a commit CI has not passed.
#   - Push without asking, unless --yes is given. Pushing `ship` deploys the API
#     and pushing `main` deploys the frontend; the question is the last
#     reversible moment.
#   - Push `main` before `ship` in `all`: the frontend calls the new API, so the
#     API goes first.
#
# A commit that changes only Markdown or Ideas/ gets no CI run (ci.yml ignores
# those paths). It stands on CI's result for the newest commit beneath it that
# changed anything else -- the code it ships is that commit's code.

set -euo pipefail

API_URL="https://account-api-210502804146.us-west1.run.app"
SITE_URL="https://account-2a7.pages.dev"
# The Pages build's two variables, so a local build of the same commit is the
# same build. Both are public by nature: they ship in the page itself.
GOOGLE_CLIENT_ID="210502804146-1388joi9e4g6ljtses6cs9aeec7lb5fh.apps.googleusercontent.com"
RUN_APPEARS_SECONDS=120   # how long a pushed commit may take to show up as a run
DOCS_RUN_SECONDS=30       # how long to look for a run on a docs-only commit
PAGES_TIMEOUT_SECONDS=900 # how long Pages may take to serve the new build

ROOT="$(git rev-parse --show-toplevel)"
LOG_DIR="$ROOT/Application/.deploy-logs"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
SHORT="${SHA:0:7}"

say()  { printf '\n== %s\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

# ---------------------------------------------------------------- arguments --

TARGET="${1:-}"
YES=0
for arg in "${@:2}"; do
  case "$arg" in
    --yes) YES=1 ;;
    *) usage ;;
  esac
done
case "$TARGET" in ci|api|web|all|check-web) ;; *) usage ;; esac

# ---------------------------------------------------------------- preflight --

command -v gh >/dev/null || fail "the GitHub CLI (gh) is not installed"
gh auth status >/dev/null 2>&1 || fail "gh is not signed in: run 'gh auth login'"

# Tracked changes only: untracked notes and scratch files do not ship.
if [ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]; then
  fail "uncommitted changes. Commit or stash them first; a deploy ships the commit, not the working tree."
fi

git -C "$ROOT" fetch -q origin

confirm() {
  [ "$YES" = 1 ] && return 0
  printf '%s [y/N] ' "$1"
  read -r answer
  [ "$answer" = "y" ] || [ "$answer" = "Y" ] || fail "cancelled; nothing was pushed"
}

# Refuse anything that would need a force-push.
fast_forward_of() {
  local branch="$1"
  if git -C "$ROOT" rev-parse -q --verify "origin/$branch" >/dev/null; then
    git -C "$ROOT" merge-base --is-ancestor "origin/$branch" "$SHA" \
      || fail "$SHORT is not a fast-forward of origin/$branch. Rebase onto it first; this script never force-pushes."
  fi
}

# ------------------------------------------------------- watching a run --

# The run of <workflow file> for <commit>, waiting up to <seconds> for it to appear.
find_run() {
  local workflow="$1" commit="$2" seconds="$3" waited=0 id
  while [ "$waited" -lt "$seconds" ]; do
    id="$(gh run list --workflow "$workflow" --commit "$commit" --limit 1 \
          --json databaseId --jq '.[0].databaseId // empty' 2>/dev/null || true)"
    if [ -n "$id" ]; then echo "$id"; return 0; fi
    sleep 5; waited=$((waited + 5))
  done
  return 1
}

# Watch the run for <commit> (default: this one) to the end.
# On failure: the failed steps' logs, printed and kept.
watch_run() {
  local workflow="$1" label="$2" commit="${3:-$SHA}" id log
  id="$(find_run "$workflow" "$commit" "$RUN_APPEARS_SECONDS")" || return 3
  say "$label: run $id for ${commit:0:7}"
  echo "   $(gh run view "$id" --json url --jq .url)"
  if gh run watch "$id" --exit-status --interval 10 >/dev/null; then
    echo "   passed"
    return 0
  fi
  mkdir -p "$LOG_DIR"
  log="$LOG_DIR/$(date +%Y%m%d-%H%M%S)-$label-$SHORT.log"
  gh run view "$id" --log-failed > "$log" 2>&1 || true
  # The error lines first: a failed step's log ends in the runner's cleanup,
  # so its last lines are rarely the ones that say what broke.
  printf '\n----- errors in %s (full log: %s) -----\n' "$label" "$log" >&2
  grep -E '##\[error\]|^[^	]*	[^	]*	[^ ]+ (E |FAILED|ERROR)|Traceback|Error:|[0-9]+ failed' "$log" \
    | cut -c1-400 | head -n 60 >&2 || true
  printf -- '----- last 60 lines -----\n' >&2
  tail -n 60 "$log" | cut -c1-400 >&2
  # A job GitHub cancelled or never started (no runner, a timeout) has no step
  # logs at all; its reason is in the job's outcome and annotations.
  printf -- '----- jobs, and what GitHub said about them -----\n' >&2
  gh api "repos/{owner}/{repo}/actions/runs/$id/jobs" \
    --jq '.jobs[] | "\(.name): \(.conclusion // .status)"' >&2 || true
  for job in $(gh api "repos/{owner}/{repo}/actions/runs/$id/jobs" \
                 --jq '.jobs[] | select(.conclusion != "success" and .conclusion != "skipped") | .id' 2>/dev/null); do
    gh api "repos/{owner}/{repo}/check-runs/$job/annotations" \
      --jq '.[] | select(.annotation_level != "notice") | "  \(.annotation_level): \(.message)"' >&2 || true
  done
  printf -- '----- end of log -----\n' >&2
  fail "$label failed for $SHORT. Summary: gh run view $id"
}

# CI starts when a branch is pushed, so the commit has to be on GitHub first.
# Push it on its own branch -- never main or ship, since pushing those is the
# deploy itself, and never with force.
ensure_pushed() {
  [ -n "$(git -C "$ROOT" branch -r --contains "$SHA" 2>/dev/null)" ] && return 0
  local branch
  branch="$(git -C "$ROOT" symbolic-ref -q --short HEAD || true)"
  case "$branch" in
    "") fail "$SHORT is on no branch and GitHub does not have it. Check out a branch first." ;;
    main|ship) fail "GitHub does not have $SHORT, and pushing $branch is itself a deploy. Push it to another branch first (git push origin HEAD:refs/heads/<name>) so CI runs before anything ships." ;;
  esac
  confirm "GitHub does not have $SHORT yet. Push $branch so CI runs on it?"
  say "Pushing $branch so CI runs on $SHORT"
  git -C "$ROOT" push origin "$SHA:refs/heads/$branch" \
    || fail "GitHub refused the push of $branch: it has commits this one lacks, or this branch was rebased. Push it by hand; this script never force-pushes."
}

# CI runs on every push, but skips commits that change only Markdown or Ideas/.
# Such a commit stands on CI's result for the code beneath it: the newest
# commit that changed anything else. CI runs only on the last commit of each
# push, so that result may sit on any commit from there up to this one -- they
# all hold the same code. A run on this commit itself is looked for first.
wait_for_ci() {
  ensure_pushed
  local status=0 ci_sha="$SHA" code_sha c
  code_sha="$(git -C "$ROOT" log -1 --format=%H "$SHA" -- . ':(exclude,glob)**/*.md' ':(exclude)Ideas')"
  if [ "$code_sha" != "$SHA" ] && ! find_run ci.yml "$SHA" "$DOCS_RUN_SECONDS" >/dev/null; then
    ci_sha="$code_sha"
    for c in $(git -C "$ROOT" rev-list "$code_sha..$SHA^"); do
      if find_run ci.yml "$c" 1 >/dev/null; then ci_sha="$c"; break; fi
    done
    say "CI: $SHORT changes only docs; it stands on CI's run for ${ci_sha:0:7}, which tested the same code (${code_sha:0:7})"
  fi
  watch_run ci.yml CI "$ci_sha" || status=$?
  if [ "$status" = 3 ]; then
    say "CI: no run for ${ci_sha:0:7} after ${RUN_APPEARS_SECONDS}s"
    echo "   Is the CI workflow enabled, and did the push reach GitHub? $(gh run list --workflow ci.yml --limit 1 --json url --jq '.[0].url // empty' 2>/dev/null)"
    fail "no CI result to deploy on"
  fi
}

# ---------------------------------------------------------- the frontend --

# Pages has no run to watch. Instead: build this commit the way Pages does,
# then poll the live site until every file it serves matches, hashes aside.
verify_site() {
  local build
  build="$(mktemp -d)"
  say "Frontend: building $SHORT locally to compare with the live site"
  (
    cd "$ROOT/Application/frontend"
    VITE_API_BASE_URL="$API_URL/api" VITE_GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
      npx --no-install vite build --outDir "$build" --emptyOutDir >/dev/null
  ) || fail "the local production build failed; run 'npm run build' in Application/frontend to see why"

  if ! python3 - "$build" "$SITE_URL" "$PAGES_TIMEOUT_SECONDS" <<'PY'
import pathlib, re, subprocess, sys, time

build, site, timeout = pathlib.Path(sys.argv[1]), sys.argv[2].rstrip("/"), int(sys.argv[3])
HASHED = re.compile(rb"-[A-Za-z0-9_-]{8}\.(js|css)")
REF = re.compile(rb"assets/[A-Za-z0-9_.-]+\.(?:js|css)")
# A chunk importing a sibling: import("./BudgetPage-AbCd1234.js").
SIBLING = re.compile(rb"\./([A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8}\.(?:js|css))")

# One- and two-letter names are the minifier's, and it picks them partly by
# the file's character frequencies -- so the hashes inside the entry chunk,
# which differ between machines, reshuffle them. Set aside like the hashes;
# strings, property names and structure, where a real change shows, are kept.
# A name after one dot is a property (kept); after three it is a spread.
MANGLED = re.compile(rb"(?<![A-Za-z0-9_$])(?:(?<=\.\.\.)|(?<!\.))[A-Za-z_$][A-Za-z0-9_$]?(?![A-Za-z0-9_$])")

def norm(data: bytes) -> bytes:
    return MANGLED.sub(b"_", HASHED.sub(rb"-H.\1", data))

def fetch(path: str) -> bytes:
    # A query string past the CDN's cache of the old index.
    # Pages serves the index at "/" (it redirects /index.html there); the query
    # string gets past the CDN's cache of the old one.
    url = f"{site}/?v={int(time.time())}" if path == "index.html" else f"{site}/{path}"
    # curl rather than urllib: it uses the system's certificates, where a
    # python.org Python on macOS ships with none.
    return subprocess.run(["curl", "-fsSL", "--max-time", "30", "-H", "Cache-Control: no-cache", url],
                          check=True, capture_output=True).stdout

def live_files() -> dict[str, bytes]:
    files, queue = {}, ["index.html"]
    while queue:
        path = queue.pop()
        if path in files:
            continue
        files[path] = fetch(path)
        for ref in REF.findall(files[path]):
            queue.append(ref.decode())
        if path.startswith("assets/"):
            for name in SIBLING.findall(files[path]):
                queue.append(f"assets/{name.decode()}")
    return files

def local_files() -> dict[str, bytes]:
    files = {"index.html": (build / "index.html").read_bytes()}
    for f in (build / "assets").glob("*"):
        if f.suffix in (".js", ".css"):
            files[f"assets/{f.name}"] = f.read_bytes()
    return files

def key(path: str) -> str:
    return HASHED.sub(rb"-H.\1", path.encode()).decode()

local = {}
for path, data in local_files().items():
    local.setdefault(key(path), set()).add(norm(data))

deadline, last = time.time() + timeout, None
while True:
    try:
        live = {}
        for path, data in live_files().items():
            live.setdefault(key(path), set()).add(norm(data))
        # Every file the live site reaches must match one built here.
        diff = sorted(k for k in live if live[k] != local.get(k))
        if not diff:
            print(f"   live site matches this commit's build ({sum(len(v) for v in live.values())} files)")
            sys.exit(0)
        last = diff
    except Exception as exc:  # the site mid-deploy, a network blip
        last = [f"(fetch failed: {exc})"]
    if time.time() > deadline:
        print("\n----- files the live site serves that differ from this commit's build -----", file=sys.stderr)
        for k in last:
            print(f"   {k}", file=sys.stderr)
        print("----- end -----", file=sys.stderr)
        print("Pages build logs are in the Cloudflare dashboard: Workers & Pages -> account -> Deployments.",
              file=sys.stderr)
        sys.exit(1)
    time.sleep(15)
PY
  then
    rm -rf "$build"
    fail "the live site did not match $SHORT within ${PAGES_TIMEOUT_SECONDS}s"
  fi
  rm -rf "$build"
}

# ------------------------------------------------------------------ steps --

deploy_api() {
  fast_forward_of ship
  confirm "Deploy the API from $SHORT ($(git -C "$ROOT" log -1 --format=%s "$SHA"))? This pushes ship."
  say "API: pushing $SHORT to ship"
  git -C "$ROOT" push origin "$SHA:refs/heads/ship"
  local status=0
  watch_run deploy-api.yml "Deploy API" || status=$?
  [ "$status" = 0 ] || fail "the push to ship started no Deploy API run within ${RUN_APPEARS_SECONDS}s"
}

deploy_web() {
  fast_forward_of main
  confirm "Deploy the frontend from $SHORT? This pushes main, and Pages builds it."
  say "Frontend: pushing $SHORT to main"
  git -C "$ROOT" push origin "$SHA:refs/heads/main"
  verify_site
}

say "Pipeline '$TARGET' for $SHORT: $(git -C "$ROOT" log -1 --format=%s "$SHA")"

case "$TARGET" in
  ci)
    wait_for_ci
    ;;
  api)
    wait_for_ci
    deploy_api
    ;;
  web)
    wait_for_ci
    deploy_web
    ;;
  all)
    wait_for_ci
    deploy_api
    deploy_web
    ;;
  check-web)
    PAGES_TIMEOUT_SECONDS=0
    verify_site
    ;;
esac

say "Done: '$TARGET' for $SHORT"
