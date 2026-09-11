#!/usr/bin/env bash
#
# dev.run.sh — launch the Account app for local development.
#
#   ./dev.run.sh             start backend + frontend together (default)
#   ./dev.run.sh backend     backend only  (uvicorn)
#   ./dev.run.sh frontend    frontend only (vite)
#   ./dev.run.sh docker      full stack via docker compose
#   ./dev.run.sh install     install/refresh dependencies, then exit
#   ./dev.run.sh --help
#
# Each service prints its URL on startup. Override a port with BACKEND_PORT or
# FRONTEND_PORT. Dependencies are installed on first run and skipped
# afterwards. Ctrl+C stops every service it started.

set -euo pipefail
set -m   # job control: each service gets its own process group, so a single
         # kill takes down uvicorn/vite and their children together

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$APP_DIR/backend"
FRONTEND="$APP_DIR/frontend"
VENV="$BACKEND/.venv"

BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# ---------------------------------------------------------------- output ----

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_CYAN=$'\033[36m'; C_MAGENTA=$'\033[35m'
else
    C_RESET=''; C_DIM=''; C_BOLD=''
    C_RED=''; C_GREEN=''; C_YELLOW=''; C_CYAN=''; C_MAGENTA=''
fi

info() { printf '%s==>%s %s\n' "$C_CYAN"   "$C_RESET" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$C_GREEN"  "$C_RESET" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()  { printf '%s fail%s %s\n' "$C_RED"   "$C_RESET" "$*" >&2; exit 1; }

# Print the header comment block (everything from line 3 to the first
# non-comment line) as help text.
usage() {
    awk 'NR > 2 { if ($0 !~ /^#/) exit; sub(/^#[ ]?/, ""); print }' "${BASH_SOURCE[0]}"
}

# ---------------------------------------------------------------- checks ----

need() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required but not installed."
}

port_busy() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

port_holder() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 { print $1" (pid "$2")" }'
}

require_port() {
    local port=$1 what=$2
    if port_busy "$port"; then
        die "Port $port is already in use by $(port_holder "$port") — stop it first, or run with ${what}_PORT=<other> set."
    fi
}

# Is KEY present in FILE with a non-empty value?
env_has() {
    [ -f "$1" ] || return 1
    grep -Eq "^[[:space:]]*$2[[:space:]]*=[[:space:]]*[^[:space:]]" "$1"
}

check_backend_env() {
    local f="$BACKEND/.env"
    [ -f "$f" ] || die "Missing backend/.env — it needs GOOGLE_CLIENT_ID and JWT_SECRET. See the README."
    # app/config.py builds Settings() at import time, so a missing key crashes
    # uvicorn on startup with a Pydantic error rather than anything readable.
    env_has "$f" GOOGLE_CLIENT_ID || die "backend/.env is missing GOOGLE_CLIENT_ID."
    env_has "$f" JWT_SECRET       || die "backend/.env is missing JWT_SECRET."
}

# Checks what the frontend needs, and pins the one value that must agree with
# this script's own choice of backend port.
prepare_frontend_env() {
    local f="$FRONTEND/.env"
    if ! env_has "$f" VITE_GOOGLE_CLIENT_ID; then
        warn "frontend/.env has no VITE_GOOGLE_CLIENT_ID — the Google sign-in button will not render."
    fi

    # apiClient.ts falls back to port 8000 when this is unset, while the backend
    # defaults to 8001 — so a fresh clone (frontend/.env is gitignored) loads,
    # renders its shell, and fails every fetch with no useful diagnostic. Deriving
    # it from BACKEND_PORT means the two cannot disagree. Vite lets the process
    # environment win over .env files, so this also corrects a stale .env; an
    # explicit value in the caller's environment still wins over both.
    local derived="http://localhost:$BACKEND_PORT/api"
    if [ -n "${VITE_API_BASE_URL:-}" ]; then
        info "Using VITE_API_BASE_URL from the environment: $VITE_API_BASE_URL"
    else
        if env_has "$f" VITE_API_BASE_URL \
           && ! grep -Eq "^[[:space:]]*VITE_API_BASE_URL[[:space:]]*=[[:space:]]*${derived}[[:space:]]*$" "$f"; then
            warn "frontend/.env sets a different VITE_API_BASE_URL; using $derived to match the backend port."
        fi
        export VITE_API_BASE_URL="$derived"
    fi
}

hash_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        sha256sum "$1" | cut -d' ' -f1
    fi
}

# ------------------------------------------------------------- installing ---

setup_backend() {
    need python3
    if [ ! -d "$VENV" ]; then
        info "Creating virtualenv at backend/.venv"
        python3 -m venv "$VENV"
    fi

    local stamp="$VENV/.requirements.sha256" want
    want=$(hash_file "$BACKEND/requirements.txt")

    if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$want" ]; then
        info "Installing backend dependencies ${C_DIM}(first run pulls a large requirements.txt — give it a few minutes)${C_RESET}"
        "$VENV/bin/python" -m pip install --quiet --upgrade pip
        "$VENV/bin/python" -m pip install --quiet -r "$BACKEND/requirements.txt"
        printf '%s\n' "$want" >"$stamp"
        ok "Backend dependencies installed"
    fi
}

setup_frontend() {
    need node
    need npm
    if [ ! -d "$FRONTEND/node_modules" ] \
       || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules" ]; then
        info "Installing frontend dependencies"
        if [ -f "$FRONTEND/package-lock.json" ]; then
            ( cd "$FRONTEND" && npm ci )
        else
            ( cd "$FRONTEND" && npm install )
        fi
        touch "$FRONTEND/node_modules"
        ok "Frontend dependencies installed"
    fi
}

# --------------------------------------------------------------- services ---

PIDS=''

# start_service LABEL COLOR WORKDIR CMD...
start_service() {
    local label=$1 color=$2 dir=$3
    shift 3
    (
        cd "$dir" || exit 1
        "$@" 2>&1 | awk -v p="${color}[${label}]${C_RESET} " '{ print p $0; fflush() }'
    ) &
    PIDS="$PIDS $!"
    # Drop the job from the table so bash does not print its own
    # "[1]+ Terminated" notice over the service output on shutdown.
    disown 2>/dev/null || true
}

start_backend() {
    check_backend_env
    require_port "$BACKEND_PORT" BACKEND
    setup_backend
    info "Backend  → http://localhost:$BACKEND_PORT  ${C_DIM}(docs at /docs)${C_RESET}"
    start_service "backend " "$C_CYAN" "$BACKEND" \
        "$VENV/bin/python" -m uvicorn app.main:app --reload \
        --host 127.0.0.1 --port "$BACKEND_PORT"
}

start_frontend() {
    prepare_frontend_env
    require_port "$FRONTEND_PORT" FRONTEND
    setup_frontend
    info "Frontend → http://localhost:$FRONTEND_PORT"
    start_service "frontend" "$C_MAGENTA" "$FRONTEND" \
        npm run dev -- --port "$FRONTEND_PORT" --strictPort
}

CLEANED=0

cleanup() {
    [ "$CLEANED" = 1 ] && return 0
    CLEANED=1
    trap '' INT TERM EXIT
    [ -n "${PIDS// /}" ] || return 0
    printf '\n'
    info "Shutting down"
    local pid
    for pid in $PIDS; do
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in $PIDS; do
        kill -KILL -- "-$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    ok "Stopped"
}

on_signal() {
    cleanup
    exit 0
}

# Block until any service exits, then tear the rest down. bash 3.2 (the macOS
# system bash) has no `wait -n`, so poll instead.
supervise() {
    printf '%sReady — press Ctrl+C to stop.%s\n\n' "$C_BOLD" "$C_RESET"
    local pid
    while :; do
        for pid in $PIDS; do
            if ! kill -0 "$pid" 2>/dev/null; then
                warn "A service exited unexpectedly."
                exit 1
            fi
        done
        sleep 1
    done
}

run_docker() {
    need docker
    local compose
    if docker compose version >/dev/null 2>&1; then
        compose="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        compose="docker-compose"
    else
        die "Docker Compose is not available."
    fi
    [ -f "$APP_DIR/.env" ] \
        || die "Missing Application/.env — compose reads GOOGLE_CLIENT_ID and JWT_SECRET from it."
    env_has "$APP_DIR/.env" GOOGLE_CLIENT_ID || die "Application/.env is missing GOOGLE_CLIENT_ID."
    env_has "$APP_DIR/.env" JWT_SECRET       || die "Application/.env is missing JWT_SECRET."
    info "Starting the stack with $compose"
    cd "$APP_DIR"
    exec $compose up --build
}

# ------------------------------------------------------------------- main ---

# Installed before any service starts, not inside supervise: start_frontend can
# spend minutes in `npm ci`, and a port clash, a missing node, a failed install or
# a Ctrl+C in that window all used to exit with uvicorn already running and
# unreaped — leaving the next run to die on "Port 8001 is already in use".
# cleanup is a no-op while nothing has been started, so this is safe for every
# target, including install and --help.
trap on_signal INT TERM
trap cleanup EXIT

case "${1:-all}" in
    all|'')
        start_backend
        start_frontend
        supervise
        ;;
    backend|be)
        start_backend
        supervise
        ;;
    frontend|fe)
        start_frontend
        supervise
        ;;
    docker)
        run_docker
        ;;
    install|setup)
        setup_backend
        setup_frontend
        ok "Dependencies ready. Run './dev.run.sh' to start the app."
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        die "Unknown target '$1'. Try: all | backend | frontend | docker | install"
        ;;
esac
