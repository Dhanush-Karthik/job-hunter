# job-hunter

Goal: build an application that hunts jobs cleverly (engineering-driven: sourcing, matching, tailoring, outreach, tracking) so the owner lands a job as early as possible.

## Multi-agent setup (herdr)

Workspace `job-hunter`. Panes:
- `lead`    claude, `--model opus --effort high`. Owns planning and decomposition. Plans are written to `docs/plan.md` BEFORE any worker is dispatched. Never codes big things itself; delegates.
- `work-a`  claude, `--model sonnet --effort high`. Implementation worker.
- `work-b`  claude, `--model sonnet --effort high`. Implementation worker.
- `codex`   codex, gpt-6.1-sol (high, from ~/.codex/config.toml). Implementation worker; good for self-contained modules, scripts, scrapers.

No reviewer agents. Lead verifies by running the code/tests itself.

## Lead protocol
1. Plan with Opus: write `docs/plan.md` (goals, architecture, milestones, task list with file ownership per worker).
2. Dispatch: `herdr agent prompt <name> "<task, exact files, acceptance check>" --wait --timeout 600000`
3. Read results: `herdr agent read <name> --source recent-unwrapped --lines 120`
4. Workers get disjoint files. Never two workers on one file.
5. Commit small, on a branch per milestone. No Co-Authored-By / attribution lines.
6. Never auto-submit applications or send messages to people without owner confirmation.
