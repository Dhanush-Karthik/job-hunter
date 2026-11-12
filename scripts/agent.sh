#!/usr/bin/env bash
# On-demand sub-agent control inside herdr. Config: ../agents.conf
#   scripts/agent.sh spawn <role> [name]     split a pane, start the role's agent, print its name
#   scripts/agent.sh task  <name> "<prompt>" send work and wait until it settles (timeout 10 min)
#   scripts/agent.sh read  <name> [lines]    read recent output
#   scripts/agent.sh list                    live agents
#   scripts/agent.sh kill  <name>            close that agent's pane
set -euo pipefail
test "${HERDR_ENV:-}" = 1 || { echo "not inside herdr" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
. "$DIR/agents.conf"
cmd="${1:-}"; shift || true
case "$cmd" in
  spawn)
    role="${1:?role}"; name="${2:-$role-$(date +%H%M%S)}"
    case " $ROLES " in *" $role "*) ;; *) echo "unknown role '$role' (ROLES: $ROLES)" >&2; exit 1;; esac
    v() { eval "echo \"\${ROLE_${role}_$1:-}\""; }
    kind=$(v KIND); model=$(v MODEL); effort=$(v EFFORT)
    pane=$(herdr pane split --current --direction "$SPLIT_DIRECTION" --cwd "$DIR" --no-focus | jq -r .result.pane.pane_id)
    args=()
    if [ "$kind" = claude ]; then
      [ -n "$model" ]  && args+=(--model "$model")
      [ -n "$effort" ] && args+=(--effort "$effort")
    elif [ "$kind" = codex ]; then
      [ -n "$model" ]  && args+=(-m "$model")
      [ -n "$effort" ] && args+=(-c "model_reasoning_effort=\"$effort\"")
    fi
    ok=0
    for _ in 1 2 3 4 5 6; do  # new pane's shell prompt may not be up yet
      sleep 1
      out=$(herdr agent start "$name" --kind "$kind" --pane "$pane" --timeout "$STARTUP_TIMEOUT_MS" -- "${args[@]}" 2>&1) && { ok=1; break; }
      case "$out" in *agent_pane_busy*) ;; *) break;; esac   # only retry while shell is not ready
    done
    if [ "$ok" != 1 ] && herdr pane read "$pane" --source visible --lines 30 | grep -q "Update available"; then
      # codex update nag: dismiss with Esc (skip, never upgrades), then wait for the agent to come up
      herdr pane send-keys "$pane" esc >/dev/null
      herdr agent wait "$pane" --timeout 30000 >/dev/null 2>&1 && ok=1
    fi
    [ "$ok" = 1 ] || {
      echo "start failed: $out" >&2
      echo "agent may be blocked on a prompt (trust/update). Inspect: herdr pane read $pane --source visible" >&2; exit 1; }
    echo "$name"
    ;;
  task) herdr agent prompt "${1:?name}" "${2:?prompt}" --wait --timeout 600000 | jq -r '.result // .' | head -c 600; echo ;;
  read) herdr agent read "${1:?name}" --source recent-unwrapped --lines "${2:-120}" ;;
  list) herdr agent list | jq -r '.result.agents[]|[.pane_id,(.name // "-"),.agent,.agent_status]|@tsv' ;;
  kill) p=$(herdr agent get "${1:?name}" | jq -r '.result.agent.pane_id // .result.pane_id'); herdr pane close "$p" ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
