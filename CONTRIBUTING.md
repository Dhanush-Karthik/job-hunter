# Contributing

Small, focused pull requests are easiest to review.

## Set up

```bash
git clone --recurse-submodules <repo> && cd job-hunter
uv sync                      # Python deps
(cd web && npm ci)           # web deps
./start.sh dev               # API with reload on :8787 + Vite on :5173
(cd web && npm run dev:mock) # web only, API served from in-browser mocks (no backend, no data)
```

## Before you push

```bash
uv run ruff check src tests
uv run pytest
uv run python -m jobhunter.api.dump_openapi     # regenerate contracts/openapi.json after any API/schema change
(cd web && npm run gen:api && npm run typecheck && npm run lint && npm test)
```

CI runs the same checks (`.github/workflows/ci.yml`).

## Ground rules

- **The app never sends or submits anything on its own.** Anything that emails a person or submits a form needs an explicit user click, a `confirm` flag in the API, and a test proving it refuses without it.
- **No personal data in the repo.** Everything personal lives under `data/` (git-ignored). Test fixtures use made-up people and `example.com`.
- **The API contract is generated.** Change `src/jobhunter/schemas.py`, regenerate `contracts/openapi.json` and `web/src/api/schema.d.ts`, never hand-edit them. `web/src/mocks/` must follow the contract (the web tests use it).
- **Everything a user may want to change is a setting**, not a constant: add it to `Settings` in `schemas.py`, the example config, the Settings page, and [docs/configuration.md](docs/configuration.md).
- Tests never touch the network, Gmail, the keychain or the user's `data/`; use the seams in `tests/apihelpers.py` (and `finder.http_get` / `reachout.smtp_factory` for Email HR).

## Optional: agent workflow

`AGENTS.md`, `CLAUDE.md`, `agents.conf` and `scripts/agent.sh` describe the maintainer's multi-agent setup (herdr + Claude / Codex). You do not need any of it to contribute.
