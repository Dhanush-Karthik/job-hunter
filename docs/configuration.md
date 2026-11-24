# Configuration reference

Three places hold configuration. Use the first one for almost everything.

| Where | What | How to change |
|---|---|---|
| **Settings page** (stored in the database) | Search, filters, schedules, goals, AI engines, Email HR | Dashboard → Settings |
| **Files under `data/`** | Your CVs, career-ops profile, tracked companies, seed config | Edit the file (or upload in Settings) |
| **Environment variables** | Port, data folder, binaries, Gmail credentials without a keychain | Shell / launchd / `.env` you source yourself |

`data/` is git-ignored. Back it up by copying the folder.

## 1. Settings

`./start.sh` copies [`config/jobhunter.example.yml`](../config/jobhunter.example.yml) to `data/config.yml` on first run. **That file only seeds the settings once**: after the first start the Settings page owns them (stored in the SQLite `settings` table). To reseed from the file, stop the app, delete the `app` row (`sqlite3 data/jobhunter.sqlite "delete from settings where key='app'"`) and start again.

### Job search (`query_matrix`, `prefilter`)

| Key | Meaning |
|---|---|
| `query_matrix.titles` / `locations` | Every title is searched in every location, a few combinations per run |
| `query_matrix.sites` | `linkedin`, `naukri`, `indeed`, `glassdoor` (`google` currently returns nothing) |
| `query_matrix.hours_old`, `results_wanted` | Only postings newer than this (hours); results per query (max 50) |
| `prefilter.cities`, `remote_ok` | Cities you accept; whether remote jobs pass |
| `prefilter.exp_years` | `[low, high]` years you can claim. Jobs asking more than `exp_drop_min_at_least` are dropped |
| `prefilter.ctc_min_lpa`, `usd_inr` | Drop a job only when its **stated maximum** pay is below this (India: LPA); USD pay is converted with the rate |
| `prefilter.max_age_days_pass` / `max_age_days_drop` | Older than the first: shown but not fresh; older than the second: dropped |
| `prefilter.stack_positive` / `stack_negative` | Words in the job that raise or lower its quick score |
| `source_weights` | Quick-score multiplier per source (inbound recruiter mail 1.5, company career pages 1.15 ...) |

Filtered-out jobs are never deleted: **Settings → Job search → Recently filtered out** lets you restore any of them.

### Schedules (`schedules`)

| Key | Default | Meaning |
|---|---|---|
| `boards_every_hours`, `boards_window` | 3, 7-23 | Job-board fetch cadence and the local-hour window it runs in |
| `careerops_scan_times` | 08:00, 17:00 | Career-page scans of your tracked companies (local time) |
| `remote_boards_times` | 08:30, 17:30 | Remote job boards |
| `gmail_every_minutes` | 30 | Read job alerts and recruiter replies from Gmail |

### Goals and AI (`targets`, `auto_evaluate_top_n`, `evaluator`, `nightly`)

| Key | Meaning |
|---|---|
| `targets.applied_per_week`, `referrals_per_week` | Shown on Home |
| `targets.min_eval_score` | AI score (0-5) you treat as "worth applying" |
| `auto_evaluate_top_n`, `claude_concurrency` | AI fit reports per day and how many run at once. Each costs model quota: lower them if you hit limits |
| `evaluator.engines` | `[codex, claude]`, tried in order; an engine at its usage limit is skipped for 3 h. Remove one to never use it |
| `evaluator.codex_model/effort`, `claude_model/effort`, `timeout_seconds`, `jd_max_chars` | Which model and how hard it thinks |
| `nightly.*` | The midnight run: intake, then AI scoring of the best new jobs, then "Today's picks" (`candidates`, `max_age_hours`, `per_company`, `pick_min_eval`, `picks_max` ...) |

### Notifications and follow-ups (`notifications`, `followups`)

`notifications` turns desktop notifications on (macOS only; elsewhere they are silently skipped; `JOBHUNTER_NOTIFY=0` forces them off). `followups` sets business days before a follow-up reminder, the ghosted threshold, quiet hours, how far back the first Gmail read goes, and extra holidays (the built-in calendar is Indian public holidays).

### Email HR (`reachout`)

Settings → CVs & email. Details and examples: [email-hr.md](email-hr.md).

| Key | Default | Meaning |
|---|---|---|
| `enabled` | true | Show the Email HR card on job pages |
| `daily_cap` | 25 | Emails per rolling 24 h (drafts do not count) |
| `cooldown_days` | 14 | Do not email the same address again inside this many days (override per send with "Send anyway") |
| `max_jobs` | 8 | Jobs listed when you add other roles of the same company to one email |
| `default_attach` | `tailored` | `tailored` (the job's CV PDF, else your resume) / `base` / `none` |
| `look_up_web` | true | Open the job page and the company's careers / contact pages to find an address |
| `guess_addresses`, `guess_prefixes` | true, careers hr jobs talent recruitment | Offer these at the company domain as unverified suggestions |
| `subject_one`, `subject_many`, `body` | see below | Email wording with `{placeholders}` |
| `me.name/phone/linkedin/github/headline` | blank | Who signs. Blank fields fall back to the career-ops profile |

## 2. Files under `data/`

| File | Purpose |
|---|---|
| `data/config.yml` | Seed for Settings (first start only) |
| `data/cv/cv_a.md`, `cv_b.md` | Your CV variants as markdown. Tailored CVs are written from these and fact-checked against them. Upload in Settings → CVs & email |
| `data/cv/resume.pdf` | The PDF Email HR attaches when a job has no tailored CV. Upload in Settings |
| `data/careerops/cv.md` | career-ops master CV (what the AI evaluator reads) |
| `data/careerops/config/profile.yml` | Who you are: name, contact, target roles, narrative, compensation. Start from `vendor/career-ops/config/profile.example.yml` |
| `data/careerops/portals.yml` | Companies to scan (edit in Settings → Companies, or build it: `uv run python scripts/build_portals.py`) |
| `data/jobhunter.sqlite` | Everything else: leads, applications, runs, settings, sent emails |
| `data/logs/`, `data/logs/runs/` | Server log and per-task logs (visible in Settings → System) |
| `data/emails/` | Optional: `.eml` samples you export for developing parsers. Never committed |

First-time profile:

```bash
mkdir -p data/careerops/config
cp vendor/career-ops/config/profile.example.yml data/careerops/config/profile.yml
$EDITOR data/careerops/config/profile.yml     # name, phone, location, headline, links
```

## 3. Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `JOBHUNTER_PORT` | `8787` | Port of the server (also read by `./start.sh` and the CLI) |
| `JOBHUNTER_DATA` | `./data` | Where all your data lives. Point it elsewhere to keep several profiles |
| `JOBHUNTER_GMAIL_ADDRESS`, `JOBHUNTER_GMAIL_APP_PASSWORD` | unset | Gmail credentials for machines without an OS keychain. The keychain wins if both exist |
| `JOBHUNTER_CLAUDE_BIN`, `JOBHUNTER_CODEX_BIN`, `JOBHUNTER_NODE_BIN` | `claude`, `codex`, `node` | Binaries to call |
| `JOBHUNTER_SCAN_DEADLINE_S` | `1200` | Cap on one career-page scan |
| `JOBHUNTER_NOTIFY` | on | `0` silences desktop notifications |

## 4. Secrets

Only two: the Gmail address and a 16-character Gmail **app password** (Google Account → Security → 2-Step Verification on → App passwords). Save them in Settings → CVs & email: they go to your OS keychain (macOS Keychain, Windows Credential Locker, Linux Secret Service) and are never shown again or returned by the API. The service/account names are `jobhunter` / `gmail_address` and `gmail_app_password`.

## 5. Platform notes

- **macOS**: everything works, including `./start.sh autostart on` (launchd) and desktop notifications (`osascript`).
- **Linux**: works; no autostart script (use a systemd user unit running `./start.sh foreground`), no desktop notifications, and `./start.sh doctor` suggests Homebrew commands: translate to your package manager. Without a Secret Service keyring use the Gmail environment variables.
- **Windows**: run under WSL.
- Gmail is the only supported mail provider (IMAP to read, SMTP to send, app password). Email HR needs it; everything else works without.
- Defaults are India-centric (LPA, IST business days, Naukri). Other markets work: change the cities, sites and `usd_inr`/`ctc_min_lpa` (set the floor to 0 to disable it).
