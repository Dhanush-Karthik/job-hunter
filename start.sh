#!/usr/bin/env bash
# job-hunter: the only command the owner runs (plan section 10).
# One server owns the API, dashboard, scheduler and background workers.
set -uo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
PORT=${JOBHUNTER_PORT:-8787}
export CAREER_OPS_DATA_DIR="$ROOT/data/careerops"

if [ -t 1 ]; then G=$'\e[32m' R=$'\e[31m' Y=$'\e[33m' D=$'\e[2m' N=$'\e[0m'; else G= R= Y= D= N=; fi
fails=0 warns=0
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
bad()  { printf '  %s✗%s %s\n      %sfix:%s %s\n' "$R" "$N" "$1" "$D" "$N" "$2"; fails=$((fails + 1)); }
warn() { printf '  %s!%s %s\n      %sfix:%s %s\n' "$Y" "$N" "$1" "$D" "$N" "$2"; warns=$((warns + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

# version_ge 22.13.0 22.12.1 -> true if $1 >= $2
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }

doctor() {
  echo "job-hunter doctor"
  echo "tools"
  [ "$(uname)" = Darwin ] && ok "macOS $(sw_vers -productVersion)" || warn "not macOS: notifications/autostart unavailable" "run on macOS"
  have git && ok "git $(git --version | awk '{print $3}')" || bad "git missing" "xcode-select --install"
  have brew && ok "brew" || warn "brew missing (only needed to install the tools below)" '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  have uv && ok "uv $(uv --version | awk '{print $2}')" || bad "uv missing" "brew install uv"
  if have node; then
    v=$(node -v | tr -d v)
    version_ge "$v" 22.13.0 && ok "node $v" || bad "node $v < 22.13 (career-ops needs >= 22.13)" "brew install node@22 && brew link --overwrite node@22"
  else
    bad "node missing" "brew install node@22"
  fi
  have npm && ok "npm $(npm -v)" || bad "npm missing" "brew install node@22"
  have claude && ok "claude CLI $(claude --version 2>/dev/null | awk '{print $1}')" \
    || bad "claude CLI not on PATH (evaluate / CV / drafts need it)" "npm install -g @anthropic-ai/claude-code && claude login"

  echo "project"
  [ -f vendor/career-ops/package.json ] && ok "career-ops submodule" || bad "career-ops submodule not checked out" "git submodule update --init"
  [ -d vendor/career-ops/node_modules ] && ok "career-ops deps" || warn "career-ops deps not installed" "(cd vendor/career-ops && npm ci)"
  [ -d .venv ] && ok "python venv" || warn "python deps not installed" "uv sync"
  [ -d web/node_modules ] && ok "web deps" || warn "web deps not installed" "(cd web && npm ci)"
  if ls "$HOME/Library/Caches/ms-playwright" 2>/dev/null | grep -q '^chromium'; then ok "playwright chromium"
  else warn "playwright chromium missing (form-fill assist, liveness checks)" "(cd web && npx playwright install chromium)"; fi
  [ -d data ] && ok "data/ present" || warn "data/ not created yet" "./start.sh   (creates it on first run)"
  [ -f data/config.yml ] && ok "data/config.yml" || warn "no data/config.yml yet" "cp config/jobhunter.example.yml data/config.yml"

  echo "owner inputs"
  [ -f data/cv/cv_a.md ] && ok "CV variant A" || warn "CV variant A missing" "save it as data/cv/cv_a.md (or upload in the dashboard Setup page)"
  [ -f data/cv/cv_b.md ] && ok "CV variant B" || warn "CV variant B missing" "save it as data/cv/cv_b.md (or upload in the dashboard Setup page)"
  if security find-generic-password -s jobhunter -a gmail_app_password >/dev/null 2>&1; then ok "Gmail app password in Keychain"
  else warn "Gmail app password not in Keychain (alerts, inbound, replies)" "enter it in the dashboard Setup page"; fi

  echo
  if [ "$fails" -gt 0 ]; then printf '%s%d problem(s)%s, %d warning(s)\n' "$R" "$fails" "$N" "$warns"; return 1; fi
  printf '%sready%s (%d warning(s))\n' "$G" "$N" "$warns"
}

dev() {
  doctor >/dev/null || { doctor; exit 1; }
  mkdir -p data/logs data/run data/careerops data/cv
  [ -f data/config.yml ] || cp config/jobhunter.example.yml data/config.yml
  uv run python -c "from jobhunter.db import migrate; migrate()"
  trap 'kill 0' EXIT INT TERM
  uv run uvicorn jobhunter.api.app:app --host 127.0.0.1 --port "$PORT" --reload --reload-dir src &
  (cd web && npm run dev -- --host 127.0.0.1) &
  echo "api http://127.0.0.1:$PORT/api/docs · web http://127.0.0.1:5173"
  wait
}

PIDFILE="$ROOT/data/run/server.pid"
SERVER_LOG="$ROOT/data/logs/server.log"
URL="http://127.0.0.1:$PORT"

read_pid() {
  [ -f "$PIDFILE" ] || return 1
  server_pid=$(cat "$PIDFILE")
  case "$server_pid" in '' | *[!0-9]*) return 1 ;; esac
  [ "$server_pid" -gt 1 ]
}

running() {
  read_pid && kill -0 "$server_pid" 2>/dev/null || return 1
  # A stale pidfile must never stop an unrelated process after PID reuse.
  ps -p "$server_pid" -o command= | grep -q 'jobhunter.api.app:app'
}

prepare() {
  doctor >/dev/null || { doctor; return 1; }
  mkdir -p data/logs/runs data/run data/careerops data/cv || return 1
  [ -f data/config.yml ] || cp config/jobhunter.example.yml data/config.yml || return 1

  local stamp
  stamp=$(shasum -a 256 uv.lock) || return 1
  if [ ! -d .venv ] || [ ! -f data/run/uv.sha256 ] || [ "$(cat data/run/uv.sha256)" != "$stamp" ]; then
    uv sync || return 1
    printf '%s\n' "$stamp" > data/run/uv.sha256
  fi
  stamp=$(shasum -a 256 web/package-lock.json) || return 1
  if [ ! -d web/node_modules ] || [ ! -f data/run/web.sha256 ] || [ "$(cat data/run/web.sha256)" != "$stamp" ]; then
    (cd web && npm ci) || return 1
    printf '%s\n' "$stamp" > data/run/web.sha256
  fi
  if [ ! -d vendor/career-ops/node_modules ]; then
    (cd vendor/career-ops && npm install --no-package-lock) || return 1
  fi
  if ! ls "$HOME/Library/Caches/ms-playwright" 2>/dev/null | grep -q '^chromium'; then
    (cd web && npx playwright install chromium) || return 1
  fi
  uv run python -c 'from jobhunter.db import migrate; migrate()' || return 1
  if [ ! -f web/dist/index.html ] || [ web/index.html -nt web/dist/index.html ] \
      || [ web/package.json -nt web/dist/index.html ] \
      || [ -n "$(find web/src -type f -newer web/dist/index.html -print -quit 2>/dev/null)" ]; then
    (cd web && npm run build) || return 1
  fi
}

stop() {
  local stopped_pid deadline
  if ! running; then
    # uv may have exited while its uvicorn child is still in the managed group.
    if ! read_pid || ! ps -axo pgid=,command= | awk -v group="$server_pid" \
        '$1 == group && /jobhunter.api.app:app/ { found=1 } END { exit !found }'; then
      [ ! -f "$PIDFILE" ] || rm -f "$PIDFILE"
      echo "job-hunter is not running"
      return 0
    fi
  fi
  stopped_pid=$server_pid
  # The background wrapper makes the server a session/process-group leader.
  kill -TERM -- "-$stopped_pid" 2>/dev/null || kill -TERM "$stopped_pid" 2>/dev/null || true
  deadline=$((SECONDS + 10))
  while kill -0 -- "-$stopped_pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.2; done
  if kill -0 -- "-$stopped_pid" 2>/dev/null; then
    kill -KILL -- "-$stopped_pid" 2>/dev/null || true
  fi
  if kill -0 "$stopped_pid" 2>/dev/null; then kill -KILL "$stopped_pid" 2>/dev/null || true; fi
  rm -f "$PIDFILE"
  echo "job-hunter stopped (pid $stopped_pid)"
}

up() {
  local deadline ready=0
  prepare || return 1
  if running; then
    echo "job-hunter is already running (pid $server_pid): $URL"
    return 0
  fi
  if ! .venv/bin/python -c 'import socket, sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' \
      "$PORT" 2>/dev/null; then
    echo "Port $PORT is already in use without a managed pidfile; stop that server or set JOBHUNTER_PORT." >&2
    return 1
  fi
  # exec preserves the pid while setsid gives stop a group containing uvicorn and its children.
  nohup .venv/bin/python -c 'import os, sys; os.setsid(); os.execvp("uv", ["uv", "run", "uvicorn", "jobhunter.api.app:app", "--host", "127.0.0.1", "--port", sys.argv[1]])' \
    "$PORT" >> "$SERVER_LOG" 2>&1 < /dev/null &
  server_pid=$!
  printf '%s\n' "$server_pid" > "$PIDFILE"
  deadline=$((SECONDS + 30))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl --noproxy '*' -fsS --max-time 1 "$URL/api/health" >/dev/null 2>&1; then ready=1; break; fi
    kill -0 "$server_pid" 2>/dev/null || break
    sleep 0.2
  done
  if [ "$ready" -ne 1 ]; then
    echo "job-hunter did not become healthy within 30 seconds; see $SERVER_LOG" >&2
    tail -n 30 "$SERVER_LOG" >&2
    stop
    return 1
  fi
  echo "job-hunter started (pid $server_pid): $URL"
  if [ "${JOBHUNTER_NO_OPEN:-0}" != 1 ]; then open "$URL"; fi
}

status() {
  if ! running; then echo "job-hunter is not running"; return 1; fi
  echo "job-hunter running · pid $server_pid · uptime $(ps -p "$server_pid" -o etime= | xargs) · $URL"
  if have jq; then
    curl --noproxy '*' -fsS --max-time 3 "$URL/api/health" | jq '{ok, db, scheduler, services}'
  else
    curl --noproxy '*' -fsS --max-time 3 "$URL/api/health" | .venv/bin/python -m json.tool
  fi
}

logs() {
  if [ ! -f "$SERVER_LOG" ]; then echo "No server log yet: $SERVER_LOG"; return 0; fi
  case "${1:-}" in
    '') tail -n 100 "$SERVER_LOG" ;;
    -f) tail -n 100 -f "$SERVER_LOG" ;;
    *) echo 'usage: ./start.sh logs [-f]' >&2; return 2 ;;
  esac
}

foreground() {
  prepare || return 1
  if running; then echo "job-hunter is already running (pid $server_pid)" >&2; return 1; fi
  exec uv run uvicorn jobhunter.api.app:app --host 127.0.0.1 --port "$PORT"
}

usage() {
  cat <<EOF
usage: ./start.sh [command]
  doctor            check prerequisites, print exact fixes (exit 1 on a blocking problem)
  dev               api (reload) + vite dev server in the foreground, for agents
  up                install changed dependencies, migrate, build and start (default)
  stop | restart    stop the server and its children, or restart it
  status            show pid, uptime and service health
  logs [-f]         tail the server log, optionally following it
  foreground        prepare and run the server in the foreground
  autostart on|off   not yet: arrives in Wave 4
EOF
}

case "${1:-up}" in
  doctor) doctor ;;
  dev) dev ;;
  -h | --help | help) usage ;;
  up) up ;;
  stop) stop ;;
  restart) stop && up ;;
  status) status ;;
  logs) logs "${2:-}" ;;
  foreground) foreground ;;
  autostart) echo "'autostart' is not implemented yet (Wave 4)." >&2; exit 2 ;;
  *) usage; exit 2 ;;
esac
