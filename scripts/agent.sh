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
# Lead keeps ~2/3 width, full height; helpers fill a right column (1 right of lead, 2-3 down, 4 right of 3).
place_pane() {
  local layout lead n target dir ratio=()
  layout=$(herdr pane layout --current)
  lead=$(jq -r '.result.layout.focused_pane_id' <<<"$layout")
  n=$(jq --arg l "$lead" '[.result.layout.panes[]|select(.pane_id!=$l)]|length' <<<"$layout")
  case "$n" in
    0) target=$lead; dir=right; ratio=(--ratio 0.67) ;;
    1|2) dir=down  # split the tallest helper
       target=$(jq -r --arg l "$lead" '[.result.layout.panes[]|select(.pane_id!=$l)]|max_by(.rect.height).pane_id' <<<"$layout") ;;
    3) target=$(jq -r --arg l "$lead" '[.result.layout.panes[]|select(.pane_id!=$l)]|max_by(.rect.y).pane_id' <<<"$layout")
       # bottom helper gets a side-by-side neighbour only if both halves keep >= 60 columns
       if [ "$(jq --arg t "$target" '.result.layout.panes[]|select(.pane_id==$t).rect.width' <<<"$layout")" -ge 120 ]; then
         dir=right
       else
         dir=down
         target=$(jq -r --arg l "$lead" '[.result.layout.panes[]|select(.pane_id!=$l)]|max_by(.rect.height).pane_id' <<<"$layout")
       fi ;;
    *) echo "4 helpers already in this tab; kill one first" >&2; return 1 ;;
  esac
  herdr pane split "$target" --direction "$dir" ${ratio[@]+"${ratio[@]}"} --cwd "$DIR" --no-focus | jq -r .result.pane.pane_id
}
cmd="${1:-}"; shift || true
case "$cmd" in
  spawn)
    role="${1:?role}"; name="${2:-$role-$(date +%H%M%S)}"
    case " $ROLES " in *" $role "*) ;; *) echo "unknown role '$role' (ROLES: $ROLES)" >&2; exit 1;; esac
    v() { eval "echo \"\${ROLE_${role}_$1:-}\""; }
    kind=$(v KIND); model=$(v MODEL); effort=$(v EFFORT)
    pane=$(place_pane)
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
