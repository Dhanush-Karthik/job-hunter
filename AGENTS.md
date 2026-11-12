# AGENTS.md — sub-agent orchestration (read by Codex, and by Claude via CLAUDE.md)

Project: job-hunter — an application that hunts jobs cleverly (sourcing, matching, tailoring, outreach, tracking) so the owner lands a job as early as possible.

## Quick start
`scripts/up.sh` (inside any herdr pane) creates/reuses the workspace and starts the lead. `scripts/up.sh --down` closes it.

## Model
- One persistent **lead** (Opus, high effort) plans and delegates. Sub-agents are spawned **only when needed**, used, then killed.
- No reviewer agent. The lead verifies by running code and tests.
- Roles and models live in `agents.conf` (every option is commented there). Edit that file to change a model, effort or role; never hardcode models elsewhere.

| Role | Default | Use for |
|---|---|---|
| `builder`, `builder2` | claude sonnet high | feature implementation (give them disjoint files) |
| `codex_builder` | codex gpt-6.1-sol high | self-contained modules, scrapers, scripts |
| `tester` | codex gpt-6.1-sol medium (or claude sonnet medium) | write and run tests, report failures with output |

## Commands (run from the lead's pane; requires HERDR_ENV=1)
```bash
scripts/agent.sh spawn <role> [name]      # new pane + agent; prints its name
scripts/agent.sh task  <name> "<prompt>"  # send work, wait until it settles (10 min cap)
scripts/agent.sh read  <name> [lines]     # read its output
scripts/agent.sh list                     # live agents
scripts/agent.sh kill  <name>             # close its pane when done
```

## Rules for the lead
1. Plan first: write `docs/plan.md` (goal, architecture, task list, file ownership). Spawn nothing before the plan exists.
2. Spawn the minimum number of agents; reuse an idle one for follow-ups instead of spawning another. Kill agents when their task is accepted.
3. Every task prompt must name exact files, the acceptance check (a command that passes), and what NOT to touch.
4. Parallel agents never edit the same file. One owner per file.
5. After a task: `read` the output, run the acceptance command yourself, then commit (small commits, no Co-Authored-By / attribution lines).
6. If `spawn` reports blocked (trust/update prompt), run `herdr pane read <pane> --source visible`; ask the owner before answering a trust or approval dialog.
7. Never auto-submit job applications or message people without explicit owner confirmation.

## Rules for sub-agents
- Do only the assigned task; stay inside the files you were given.
- Finish with a short report: what changed, the command you ran to check it, its result. No long summaries.
- Do not spawn further agents. Do not commit unless told to.
