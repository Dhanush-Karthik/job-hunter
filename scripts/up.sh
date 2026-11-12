#!/usr/bin/env bash
# One command to bring up the job-hunter setup: workspace + lead agent only.
# Sub-agents are spawned later, on demand, by the lead via scripts/agent.sh.
# Run inside any herdr pane:  scripts/up.sh        (add --down to close the workspace)
set -euo pipefail
test "${HERDR_ENV:-}" = 1 || { echo "run this inside a herdr pane" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
. "$DIR/agents.conf"

ws=$(herdr workspace list | jq -r --arg l "$WORKSPACE_LABEL" '.result.workspaces[]|select(.label==$l)|.workspace_id' | head -1)

if [ "${1:-}" = --down ]; then
  [ -n "$ws" ] && herdr workspace close "$ws" && echo "closed $ws" || echo "no workspace '$WORKSPACE_LABEL'"
  exit 0
fi

if [ -z "$ws" ]; then
  res=$(herdr workspace create --cwd "$DIR" --label "$WORKSPACE_LABEL" --no-focus)
  ws=$(echo "$res" | jq -r .result.workspace.workspace_id)
  pane=$(echo "$res" | jq -r .result.root_pane.pane_id)
else
  pane=$(herdr pane list --workspace "$ws" | jq -r '.result.panes[0].pane_id')
fi

if herdr agent get lead >/dev/null 2>&1; then
  echo "lead already running"
else
  args=()
  [ -n "$LEAD_MODEL" ]  && args+=(--model "$LEAD_MODEL")
  [ -n "$LEAD_EFFORT" ] && args+=(--effort "$LEAD_EFFORT")
  sleep 1  # let the new pane's shell prompt come up
  herdr agent start lead --kind "$LEAD_KIND" --pane "$pane" --timeout "$STARTUP_TIMEOUT_MS" -- "${args[@]}" >/dev/null \
    || { echo "lead blocked on a prompt (first run: trust this folder). Answer it in workspace $ws, then re-run." >&2; exit 1; }
fi
herdr workspace focus "$ws" >/dev/null
echo "ready: workspace $ws, lead in $pane ($LEAD_MODEL/$LEAD_EFFORT). Give it the goal; it spawns helpers via scripts/agent.sh."
