#!/usr/bin/env bash
# job-hunter: the only command the owner runs (plan section 10).
# Wave 0 skeleton: `doctor` and `dev` work; `up/stop/status/logs/autostart` land in Waves 2 and 4.
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

usage() {
  cat <<EOF
usage: ./start.sh [command]
  doctor            check prerequisites, print exact fixes (exit 1 on a blocking problem)
  dev               api (reload) + vite dev server in the foreground, for agents
  up | stop | restart | status | logs [-f] | autostart on|off | foreground
                    not yet: arrive in Wave 2 (up) and Wave 4 (the rest)
EOF
}

case "${1:-up}" in
  doctor) doctor ;;
  dev) dev ;;
  -h | --help | help) usage ;;
  up | stop | restart | status | logs | autostart | foreground)
    echo "'$1' is not implemented yet (Wave 2/4). For now: ./start.sh dev" >&2; exit 2 ;;
  *) usage; exit 2 ;;
esac
