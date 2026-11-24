# Scoring and evaluation: audit and plan (v2, nightly picks)

Date: 23 Nov 2026. v2 reshapes v1 around the owner's goal: **every morning the dashboard shows a short list of highly
relevant jobs with the best chance of an interview call (about 10; more when many are strong), prepared overnight, each
evaluation fast.**

Scope: ranking (`pipeline/score.py`), selection (`jobs/scheduler.py::auto_evaluate`), the career-ops evaluation, and the
dashboard list. Data: `data/jobhunter.sqlite` as of today, 15,184 leads, 3,900 pass the prefilter, 25 scored evaluations.

## 0. Status (23 Nov, evening): implemented and run live

What shipped, simpler than sections 4–5 (no `daily_picks` table, no separate fit v2 stage):
- **Lean evaluation** (`careerops/lean.py`): one structured-JSON call per posting, no tools, no web research.
  Codex `gpt-6.2-sol` effort low first, Claude `sonnet` effort low as fallback; an engine at its usage limit is
  skipped for 3 h. `settings.evaluator.mode: full` brings back the career-ops A–H report.
- **Nightly funnel** (`jobs/nightly.py`): 00:00 IST intake (boards + career-ops scan) → up to 40 candidates
  (posted ≤72 h, minimum experience ≤4 yrs, P1/P2 role or a strong quick score, ≤2 per company) → lean evaluation →
  Today's picks (score ≥3.5, a "low" call chance needs 4.0+, ranked by score + call chance + posted ≤24 h, max 20).
  Catch-up every 30 min until noon, so a Mac that slept through midnight runs when it wakes. Keep-awake via
  `caffeinate` from 23:50. `POST /api/nightly/run` runs it on demand.
- **24 h window → weighting, not a hard filter**: date-only boards made a strict 24 h cutoff lossy, and one missed
  night would drop postings. Posts from the last 24 h get +0.08 in the quick score and +0.06 in selection.
- Day scans no longer spend tokens (auto-evaluation after every scan is gone).

Live run on 23 Nov after clearing the dashboard (old DB backed up under `data/backups/`): 6,975 leads ingested →
20 candidates (thin pool: only one board intake since the clear) → 20 lean evaluations in 62 s wall time,
about 9 s each, about 7.9k codex tokens each (157k in total) → 11 picks. Before: about 100 s per evaluation,
with a third failing on the markdown envelope.

## 1. Goal and success measures

| Goal | Measure |
|---|---|
| Open the dashboard, the list is already there | Picks for today exist before 07:00 IST, with live-checked postings |
| About 10 picks/day, each highly relevant | Owner shortlists or applies to at least 6 of 10 picks (precision of picks); 0 picks outside the experience band or location policy |
| Highest chance of an interview call | Call rate of applied picks beats call rate of applied non-picks (needs outcome data; see Step 8) |
| Each evaluation takes well under 3 min | Lean evaluation p50 <= 45 s, p95 <= 90 s, measured per run |
| Whole night finishes unattended | Pipeline start to picks ready <= 90 min |

## 2. How it works today

```
ingest -> prefilter -> quick score (free, 0-1) -> auto_evaluate -> career-ops A-H (claude -p) -> Evaluation 1-5
                                                  top 10/day with quick_score >= 0.45, found <= 3 days
```

- **Quick score** (`score.py`): .28 keyword overlap + .20 role family + .15 freshness + .05 hot + .20 title fit + .07 exp + .03 ctc + .02 iam, minus seniority / mixed-stack, times `exp_factor`, times a per-source weight, +0.30 for inbound.
- **Selection** (`auto_evaluate`): `prefilter_pass`, primary of its dedupe group, quick_score >= 0.45, found in last 3 days, not evaluated in 14 days. Triggered after each scan success (08:00 and 17:00), `auto_evaluate_top_n` per day.
- **Evaluation**: full career-ops `oferta` mode, holistic 1-5 with no formula (`modes/_shared.md`), owner rules in `data/careerops/modes/_profile.md`. Gate 3.5.
- **Dashboard**: Home shows fresh matches by quick score; there is no notion of "today's best jobs".

## 3. What the data says

| # | Finding | Evidence |
|---|---|---|
| F1 | Quick score barely predicts the evaluation | Spearman 0.30 vs eval score (n=25, range-restricted by the 0.45 gate, so the real figure is likely lower). Rubrik scored 3.8 at quick 0.295; Enterprise Minds scored 3.0 at quick 0.637 |
| F2 | Experience is the strongest signal and is under-used | Mean eval by stated min years: 0-2 -> 3.79 (n=7), 3-4 -> 3.44 (n=10), 5+ -> 3.05 (n=4). In the quick score exp is 7% weight plus a multiplier |
| F3 | The best source is starved | 39% of passing leads have no JD (1,531 of 3,900): careerops_scan 510 of 859, Glassdoor 363 of 363. Keyword overlap is then 0, so career-page leads average 0.065 and **0 of 859 reach 0.45** |
| F4 | The gate is narrow and duplicate-heavy | Only 135 leads clear 0.45 (3.5%): 116 dedupe groups, 89 companies, **19 Infosys**. 6 of the 25 evaluations are Infosys |
| F5 | The LLM score has little spread and no written anchors | All 25 scores in 2.8-4.2 (mean 3.49); the 3.5 gate is the median (13 of 25 pass). The 6 Infosys postings scored 2.8 to 4.0 but differ in stated years (2-3 yrs -> 4.0, 5-9 yrs -> 2.8), so that spread looks like real signal. Same-posting noise is unmeasured |
| F6 | Freshness is double-counted in the fit ranking | 20% of the score, though everything in the window is fresh. It belongs to ordering, not to "is this a good job" |
| F7 | **A full evaluation is slow because it writes a book, not because it thinks long** | Spike (plan.md section 13): 216 s, 20 turns, 22 K output tokens, 3 web searches. A finished report is about 4,500 words (blocks A-G, STAR stories, cover-letter draft, archived JD). Output generation and web research dominate. Only the Machine Summary (score, grade, archetype, legitimacy, evidence) is needed to rank |
| F8 | career-ops already supports a scoped evaluation | `web/src/lib/evaluation-options.mjs`: the fit score, evidence and posting checks are mandatory; the rest (research, interview prep, drafts, keywords, strategy) are optional sections, and `ESSENTIAL_EVALUATION = ["summary"]`. `buildPrompt` accepts `evaluationInstructions`; our `careerops/node/prompt.mjs` does not pass it, so every run is full |
| F9 | Nothing models "chance of a call" | The ranking measures fit only. Freshness, employer type, referral availability and posting legitimacy all affect callbacks and are not combined anywhere |
| F10 | No outcome loop | 9 applied, 1 screening, 1 rejected, 1 ghosted. Cut-offs (0.45, 3.5) are guesses |

Caveat: n=25 evaluations, all P1 titles. F1 and F2 are direction, not fitted numbers; Step 0 widens the sample.

## 4. Target design

### 4.1 Nightly pipeline (starts 00:00 IST, one run kind `nightly`, stages logged separately)

```
00:00  intake      boards (full matrix pass) + career-ops scan + Gmail           no LLM   ~15 min
00:15  window      keep leads posted in the last 24 h (4.7), enrich missing JDs  no LLM   ~10 min
00:25  fit         deterministic fit score v2 over every new/changed lead        no LLM   <1 min
00:30  lean eval   top K (default 40) -> career-ops lean evaluation, 3 parallel  LLM     ~15-20 min
00:55  picks       call-chance ranking, quality bar, liveness check, write picks no LLM   ~5 min
07:00  re-verify   liveness of today's picks (postings that closed overnight drop out)
07:30  notify      "N picks ready" (existing notifier, quiet hours respected)
```

- Only leads **not yet evaluated** enter lean eval; yesterday's unactioned picks carry over (Section 4.4) without re-evaluating.
- **Mac asleep at midnight**: see 4.1b. APScheduler's missed-run grace is 1 h today, so add catch-up: a 5-minute check job (it fires right after a wake) plus a startup check start `nightly` at once when no run completed in the last 20 h. The window then widens to `max(24 h, time since last successful run + 2 h)`, capped at 72 h, so a missed night loses no posting; the list shows yesterday's picks with a "refreshing" note.
- Daytime boards (every 3 h) and Gmail (30 min) keep ingesting so the night run only fetches deltas. Inbound recruiter leads keep their immediate notification and always join the picks; they bypass the night wait.

### 4.1b Running with the lid closed (checked on this Mac, 23 Nov)

What the machine shows:
- MacBook (Apple M2) on AC with a **BenQ external monitor, a USB Ethernet adapter and a Bluetooth mouse attached**. That is the hardware macOS clamshell mode needs (lid closed + power + external display + input device).
- `pmset` idle system sleep is **1 minute** on AC; right now it is held off only by the Claude app and an open display. No jobhunter LaunchAgent is installed (`autostart` is off), so nothing starts the server unattended.
- The sleep log shows what happens when the Mac is *not* docked: on 20 Nov at 13:00-15:48 it cycled through 2-6 second dark wakes (Power Nap) at 1% battery, then hibernated for 2.8 days until the lid was opened on 23 Nov 11:27. A dark wake of a few seconds cannot run a 30-minute job.
- Battery was at **1%**: a night run on battery can die mid-run. The nightly run must check power.

What research says (secondary sources, partly conflicting; none from Apple, so every option below is *tested on this Mac before it is trusted*): clamshell mode with power + external display is Apple's supported route. `caffeinate` does not override lid-close sleep. `sudo pmset disablesleep 1` is undocumented, widely reported to work on Apple Silicon (more reliably on AC), with reports that it fails on some macOS versions. A scheduled `pmset` wake plus a launchd job is reported unreliable on recent macOS, and launchd gives no guarantee about the power state at start.

**Ranked options (the app uses the first that the probe proves works)**

| # | Option | Owner action | Fits when | Risk |
|---|---|---|---|---|
| A | **Clamshell mode**: lid closed at the desk, charger in, BenQ powered on, mouse/keyboard connected. App wraps the server in `caffeinate -s` (holds off idle sleep on AC) | none beyond leaving the monitor on | you leave it docked at night | if the monitor turns itself off or loses signal, clamshell ends and the Mac sleeps |
| B | **`sudo pmset -c disablesleep 1`** (AC only): no sleep with lid closed even without the monitor. Reverse with `sudo pmset -c disablesleep 0`. App shows a Setup checklist line "Sleep disabled on AC: yes/no" from `pmset -g` | one `sudo` command, once | monitor may be off | heat if the lid is closed in a bag or on bedding; keep it on a desk, on the charger. Undocumented, may change with updates |
| C | Scheduled wake: `sudo pmset repeat wakeorpoweron MTWRFSU 23:55:00` plus a launchd job at 00:00 that runs `caffeinate -s jobhunter run nightly --wait` | one `sudo` command | A and B are not acceptable | reported unreliable; dark wake may not run the job; probe decides |
| D | **Fallback, always on**: catch-up and streaming. If the Mac slept, the nightly run starts at once when it wakes (or the dashboard is first opened) and picks stream into Home as each lean evaluation finishes | none | everything else failed | picks are not ready at open: about 15 min for the first ~10 evaluations, about 25 min for all 40 (estimate from 45 s p50 x 40 / 3 workers) |

Safeguards that apply to every option: run only when on AC power or battery >= 40% (else skip and say so on Home); hold a `caffeinate` assertion for the duration of the run and release it after; Gmail and Claude credentials live in the login keychain, so the probe also checks they are readable while the screen is locked; the dashboard states when the picks were built and whether the run was on time, delayed or caught up.

**Step 5a probe (build first, about 1 hour): `scripts/overnight_probe.sh`.** A LaunchAgent that writes a timestamp, power source, `pmset -g assertions` summary and `pmset -g log` tail to `data/logs/overnight-probe.log` at 00:00, 02:00 and 05:00, and reads one keychain item and makes one HTTPS request each time. The owner closes the lid with option A (then B if needed) set up, and the next morning the log shows which times fired, whether the network and keychain worked, and what slept when. That one night decides A, B, C or D; no more guessing.

### 4.2 Lean evaluation: how it gets from 3.5 minutes to about 45 seconds

| Lever | Change | Why it should help | Risk |
|---|---|---|---|
| L1 (biggest) | Pass `evaluationInstructions` for the essential scope (`summary` only) from `prompt.mjs`: no salary/company research, no interview prep, no STAR stories, no cover letter, no keyword table. Keep the score, score evidence, legitimacy and Machine Summary | Cuts output from about 22 K tokens to an expected 2-4 K and turns from 20 to about 4-6 (F7, F8) | Score drift versus the full report: Step 4 checks agreement |
| L2 | No web search and no fetching in the lean run: JD is always pre-fetched (Step 1); research budget 0. Company-type facts come from our own seed list | Removes 3-5 network round trips | Less comp/culture evidence: score marked `evidence=partial`, never silently neutral |
| L3 | Back-to-back runs share the cached prompt prefix (`cv.md`, profile, mode files, about 88 K tokens written once, then cache-read) | The first run pays the cache write; the rest read it | Cache time-to-live is limited, so a night run keeps one worker pool busy instead of spacing runs out |
| L4 | Concurrency 3 at night (setting `claude_concurrency_night`, default 3; day stays 2) | 40 runs at 45 s over 3 workers is about 10 min | Subscription quota: owner can set it back to 2 |
| L5 | Model and effort for lean runs configurable (`evaluate_model`, `evaluate_effort`, passed as `--model` / `--effort` in `_claude()`), default to the faster tier at medium effort if Step 4 shows score agreement | Faster tokens and shorter thinking | Quality: only adopt if agreement holds |
| L6 | Full A-H report becomes **on demand**: the Job page's "Full report" button (and automatically when the owner shortlists), reusing the same lead and cache | Overnight spends time only on ranking; depth is paid for jobs the owner actually pursues | One extra click, then 3 min for that one job |

Targets are estimates until Step 4 measures them. If lean p50 lands above 90 s after L1-L5, the fallback is career-ops' `triage` mode (reads one compact `_brief.md`, no CV) as a pre-filter for the top 40 before lean eval.

### 4.3 Picks: highly relevant and likely to produce a call

`call_chance` combines evidence; it is an ordering score, shown to the owner as **High / Medium**, not as a probability, until Step 8 calibrates it on outcomes.

| Input | Source | Initial weight (prior, to be fitted) |
|---|---|---|
| Lean eval score (CV match, North Star, red flags) | career-ops lean run | 0.40 |
| Experience band fit (stated years vs owner 2-4) | parser, deterministic | 0.20 |
| Early-applicant window (posted under 48 h, no "closing soon", no huge applicant count when shown) | posted_at, listing metadata | 0.10 |
| Employer response likelihood: product/GCC list +, mass-hiring service firm -, inbound recruiter ++ | seed list, config | 0.10 |
| ATS keyword coverage of the owner's CV against the JD | deterministic, `keyword-match.mjs` logic | 0.10 |
| Referral route exists (saved contact at the company) | contacts, `data/contacts.tsv` | 0.05 |
| Apply channel (platform quick-apply vs company ATS: speed to apply) | lead.apply_channel | 0.05 |

Hard gates (a lead failing any is never a pick, and the reason is stored): live check not closed; location policy; experience stated minimum two or more years above the band; blacklist; eval legitimacy "High Risk"; score evidence `unknown` for CV match.

**How many picks**: a quality bar, not a fixed count.
- Bar: lean eval >= `pick_min_eval` (default 3.5, the existing target) and all gates passed.
- Show the best `daily_picks_target` (default 10) that clear the bar, plus any extra with eval >= 4.0, up to `daily_picks_max` (default 25).
- If fewer than 5 clear the bar, show what exists with a note ("quiet day: 3 strong matches"). It never pads the list with weak jobs.

### 4.4 Dashboard

- **New table `daily_picks`** (lead-owned contract): `date`, `lead_id`, `rank`, `call_chance` (0-1), `call_label`, `eval_score`, `reasons` (3 short bullets, e.g. "2-3 yrs asked, you have 3.4", "Spring Boot + Keycloak in JD", "posted 6 h ago, product company"), `warnings`, `run_id`, `live_verified_at`.
- **API**: `GET /api/picks?date=` (default today, includes carried-over picks), `POST /api/picks/refresh` (run the nightly now), `GET /api/picks/status` (last night run, stage times, counts).
- **Home**: a "Today's picks" list is the top section. Each row: rank, title and company, call label, eval score, the 3 reasons, "live checked 07:02", apply channel, buttons Shortlist / Skip (with reason) / Open. A header line: "12 picks, built 00:52, 38 jobs evaluated, 3,905 scanned". Unactioned picks from yesterday stay, tagged "from yesterday", until skipped, shortlisted or closed; they never silently vanish.
- **Jobs page**: "To review" opens sorted by picks first, then by fit.
- Skip reasons feed Step 8 (a skip with "too senior" is a label).

### 4.5 Fit score v2 (free stage that feeds the lean eval)

Replaces the quick score; `fit` (0-1) and `urgency` are separate.
- **Experience band** is the main factor (about 0.25): in band 1.0, one year over 0.7, two over 0.4, three or more 0.15 (F2). Unknown years 0.6, not 0.
- **Stack evidence from the JD body**, not only the title: Java/Spring/Kafka/Keycloak in the first 600 characters counts as title-level evidence (the Rubrik case). A lead with no JD is scored on what exists, tagged `evidence=low`, and sent to enrichment; the keyword term is dropped from the weighted mean rather than counted as 0.
- **Role family** stays, with P2 titles matched to the owner's four archetypes.
- **Employer type**: mass-hiring service firms get a small penalty, seed-list product/GCC companies a small bonus; config-driven.
- **Source weights removed from fit**: they mixed source quality with data completeness (F3). A learned per-source prior can return in Step 8.
- **Freshness, hot, inbound** move to `urgency` (ordering and notifications only).
- Weights are initial guesses; fit by ridge regression against labels once n >= 60 and keep only if Spearman and precision@20 beat baseline.

### 4.6 Selection into lean eval

Top K=40 (setting) by `fit`, after: near-duplicate collapse (same company + normalized title, or JD similarity > 0.9: keep the freshest), at most 2 per company, 20% of slots reserved for careerops_scan p1/p2 leads, inbound always. Minimum fit floor only to drop clear non-fits.

### 4.7 The funnel with real numbers (DB on 23 Nov, 24-hour window)

**Window rule: only leads posted in the last 24 h are candidates** (setting `candidate_max_age_hours`, default 24). Caveat that changes the rule: Naukri, Indeed, LinkedIn and Glassdoor store a **date only** (every `posted_at` is 00:00:00), about 5,300 of the 7,000 dated leads. A literal 24 h cutoff cannot be applied to them, so the rule is: *dated yesterday or today in IST* (the run starts at 00:00, so "yesterday" is exactly the last 24 h; a catch-up run widens it, see 4.1). career-ops and remote boards carry real timestamps and use the exact 24 h. Gmail alerts have no date at all (57 of 57 in the last day): they fall back to first-seen time, are tagged "posting date unknown", and rely on the liveness check.

| Stage | Leads left | AI used? | What removes leads |
|---|---|---|---|
| Fetched, all time | 15,184 | no | |
| Prefilter pass, all time | 3,900 | no | 11,284 dropped: location, 6+ years, intern, stale |
| **Passing and posted in last 24 h** | **333** | no | everything older. The 3,500+ older leads stay in All jobs, never AI-evaluated, never picks |
| Not yet evaluated, no application or New/Shortlisted | 326 | no | applied, skipped, rejected |
| One per dedupe group | 249 | no | duplicate postings |
| Stated min experience unknown or <= 5 | 248 | no | (6+ already dropped by prefilter) |
| of those: P1/P2 | 63 (21 without JD) | no | |
| of those: `other` family | 185 | no | some real engineering roles ("Software Dev Engineer II"), much junk the recall-first prefilter let through ("Enterprise Account Executive", "Deal Desk (Night Shift)", "SAP EWM Consultant", "Tableau Developer"). Fit v2 adds a non-engineering title gate to remove junk free |
| Fit v2 rank, max 2 per company, reserved slots -> **top 40** | **40** | no | everything below stays visible, labelled "not AI-evaluated" |
| **Lean AI evaluation** | **40** | **yes** | |
| Gates + call-chance ranking | about 10 to 20 picks | no | historically 13 of 25 evaluated leads scored >= 3.5; estimate, not a measurement |

- **AI evaluates about 40 of about 250 fresh candidates per night (16%)**, and none of the older backlog. The 24 h window turns the "3,700+ queued" problem into a daily problem: each night is a new ~250-lead pool, not a pile that grows.
- **Daily size varies**: passing leads per day were 43 to 155 on normal days (3 to 54 P1/P2), with spikes of 270 to 750 on the first scan days. On a light day fewer than 40 clear the fit floor and fewer are evaluated; the AI never evaluates leads below the floor just to fill K.
- **No second chances for old leads**: a lead not evaluated tonight is older than 24 h tomorrow and drops out. To reduce misses, the evaluate step runs in fit order, so a time-limited night loses only the weakest. A daytime "Evaluate 20 more" button works on the same 24 h pool.
- **Today's real numbers**: 46 leads clear the current rule and the cap is 10/day. Over 11 days only **28 evaluations succeeded and 14 failed** (11 "malformed report-md envelope", 2 `exit status 1`, 1 usage limit). Step 4 fixes the failure rate.

## 5. Work plan

Each step names files, an acceptance check and what not to touch. Lead edits the contract files first (`models.py`, `schemas.py`, settings, `contracts/openapi.json`, `web/src/api/**`, MSW mocks); builders implement.

| Step | Owner | What | Files | Acceptance |
|---|---|---|---|---|
| 0 | lead + builder | Baseline and label harness: Spearman, precision@10/20, gate recall, per-source and exp-band means, JD coverage; golden labels from owner (80 postings, about 20 min) | `scripts/eval_scoring.py`, `tests/test_eval_scoring.py` | Prints baseline table into section 8; test passes. Baseline taken on the current working tree |
| 1 | codex_builder | JD enrichment, no LLM: ATS API via `fetch-jd.mjs`, HTTP detail fetch where allowed; rate-capped, failure-isolated | `pipeline/enrich.py`, `careerops/node/jd.mjs`, `tests/test_enrich.py` | JD coverage of passing careerops_scan leads 41% -> 90% on the real DB; tests pass |
| 2 | builder | Fit score v2 + urgency (4.5), including the 24 h age window (date-only rule for Naukri/Indeed/LinkedIn/Glassdoor, exact hours for the rest) and the non-engineering title gate (4.7) | `pipeline/score.py`, `tests/test_pipeline.py` | pytest + `scripts/eval_golden.py` keep recall 1.000 / dedupe 1.000; `eval_scoring.py` precision@20 at least baseline +15 points |
| 3 | builder | Selection (4.6) | `jobs/scheduler.py` (selection function only), `pipeline/dedupe.py` helper, `tests/test_jobs.py` | Real DB: at most 2 per company; at least 8 careerops_scan leads in 40 |
| 4 | codex_builder | **Lean evaluation**: `prompt.mjs` passes `evaluationInstructions` (essential scope, research budget 0); `evaluate(... mode="lean"|"full")`; per-run timing and token counts stored in `Run.summary`; model/effort settings; **fix the 33% failure rate** (14 of 42 runs: 11 "malformed report-md envelope"): inspect the 11 failed logs, make envelope parsing tolerant of the observed shapes, retry once on a malformed or empty envelope, and never retry on a usage limit | `careerops/node/prompt.mjs`, `careerops/__init__.py` (evaluate only), `careerops/_parsing.py`, `tests/test_careerops.py` | Failure rate under 5% on a 40-lead run; re-evaluate the 25 stored leads in lean mode: p50 <= 45 s, p95 <= 90 s, same side of 3.5 as the full score for at least 21 of 25 and mean absolute score difference <= 0.3. If it fails, tune L2-L5, then fall back to triage |
| 5a | builder | Overnight probe (4.1b), power/battery guard, `caffeinate` wrapper, Setup checklist line for sleep settings; owner runs one real night | `scripts/overnight_probe.sh`, `jobs/power.py`, `tests/test_power.py` | Probe log has entries at 00:00, 02:00 and 05:00 with network and keychain OK, or the log shows which option fails and D is chosen |
| 5 | builder | Nightly orchestrator: `RunKind.nightly`, stages, catch-up on start/wake/first dashboard load, night concurrency, stage timings, `POST /api/picks/refresh`, status route | `jobs/runner.py`, `jobs/scheduler.py`, `api/picks.py`, `tests/test_jobs.py`, `tests/test_api_picks.py` | Fake-claude e2e: nightly runs all stages, is idempotent on rerun, resumes after a mid-run restart, catch-up fires when last run is 25 h old |
| 6 | builder | Picks engine (4.3): call_chance, gates, bar, reasons, carry-over, liveness re-verify | `pipeline/picks.py`, `tests/test_picks.py` | Unit tests for each gate and for the count rules (quiet day, strong extras, max 25); golden "apply" labels never fall below the gates |
| 7 | builder2 | Dashboard: Today's picks on Home, Jobs "To review" ordering, status header, "Full report" button on Job page | `web/src/pages/today/**`, `web/src/pages/leads/**`, `web/src/pages/job/**`, `web/src/components/**` | `cd web && npm run build && npm run test`; Playwright on mocks shows picks, carry-over tag, empty and quiet-day states |
| 8 | builder | Feedback: weekly call rate by pick / call_label / eval band / source; skip reasons as labels; refit fit weights and `call_chance` weights at 30+ outcomes; surfaces as an Insight, never auto-changes | `analytics/**`, `tests/test_analytics.py` | Insight appears on synthetic data |
| 9 | lead | Owner rubric: explicit experience caps in `_profile.md` after measuring same-posting noise (re-evaluate 3 postings twice, about 3 min each in lean mode) | `data/careerops/modes/_profile.md` | Same-posting spread <= 0.2, else add anchors and retest |
| 10 | tester | Full pass: pytest, golden, vitest, Playwright; a real overnight run on the real DB | `tests/integration/**`, `web/e2e/**` | One real night: picks ready by 07:00, lean p50/p95 recorded, owner opens the dashboard and sees the list |

Order: 0 -> 5a (owner's first night, in parallel with everything) -> (1, 2 in parallel) -> (3, 4 in parallel) -> 5 -> (6, 7 in parallel) -> 9 -> 10; 8 after 30 applications.
Step 4 is the one that decides whether the speed goal is met, so it runs as soon as Step 0 exists, ahead of Steps 5-7.

## 6. Cost and quota (estimates)

- Lean run: output about 1/6 of a full run, no web search, cached prefix. If cost lands near $0.2-0.3 API-equivalent, 40 per night is about $8-12 against about $13 for 10 full runs today, for 4x the leads judged. **Not measured**: Step 4 records real tokens per run; if lean costs more than 1/3 of a full run, cut K from 40 to 25.
- Full reports only for jobs the owner shortlists (about 3-6 per day): about $4-8, spent where it matters.
- All runs stay on the owner's subscription via `claude -p`, isolated from user settings (unchanged).

## 7. Risks

1. **Thin labels**: 25 evaluations. Mitigated by Step 0 golden labels, the "keep only if it beats baseline" rule, and by calling `call_chance` a label rather than a probability.
2. **Lean scores drift from full scores**: measured on the 25 stored leads before anything gates on it (Step 4).
3. **No-JD leads** still exist after enrichment: they get `evidence=low` and a visible warning in the pick; they are not hidden.
4. **Mac asleep or server stopped overnight**: option A/B/C by probe, catch-up and streaming picks as the floor, a battery/AC guard (the Mac was at 1% on 20 Nov), and `./start.sh autostart on` so the server exists at all; the dashboard states when the picks were built.
4b. **Date-only sources**: the 24 h rule is calendar-based for 4 of the 5 main boards, so a posting from 00:05 yesterday can reach the list nearly 48 h after posting if a run is delayed. The pick shows the posting date and "posted yesterday", never a made-up hour.
5. **Closed postings**: liveness is re-checked at 07:00 and again on Shortlist.
6. **Uncommitted work in `pipeline/` and `store.py`**: land or set it aside before Step 2.
7. Unchanged guardrails: no auto-submit, no message sending, prefilter recall gate, vendor submodule untouched.

## 8. Baseline (fill in at Step 0, update after each step)

| Metric | Baseline 23 Nov | After |
|---|---|---|
| Spearman quick vs eval | 0.30 (n=25) | |
| precision@20 vs eval >= 3.5 | | |
| JD coverage, careerops_scan passing leads | 41% | |
| careerops_scan leads in daily evaluate set | 0 | |
| Max leads per company in daily set | 19 eligible Infosys | |
| Evaluation time per job | 216 s (spike), 196 s (Wayfair) | p50 / p95 lean: |
| Output tokens per evaluation | about 22 K | |
| Leads judged per day | 10 | 40 |
| Same-posting re-evaluation spread | not measured | |
| Picks precision (shortlisted or applied of shown) | n/a | |
| Picks ready by | n/a | 07:00 IST |
