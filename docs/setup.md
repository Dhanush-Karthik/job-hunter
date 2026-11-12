# job-hunter: owner setup guide

Goal: get the most interview calls with the least manual effort. This page lists everything **you** do once,
then what a normal day looks like. The app never submits applications or sends messages for you.

State: written at the end of Wave 2 (12 Nov 2026). Gmail capture, follow-up engine, notifications, analytics
and the Setup wizard arrive in Wave 3; the steps marked **(prep for Wave 3)** make that wave usable on day one.

---

## 1. One-time machine setup (10 min)

```bash
cd ~/IdeaProjects/job-hunter
./start.sh doctor        # lists anything missing with the exact install command
```

Fix every red ✗ it prints. Typical ones:

| Missing | Fix |
|---|---|
| uv | `brew install uv` |
| node ≥ 22.13 | `brew install node@22 && brew link --overwrite node@22` |
| claude CLI | `npm install -g @anthropic-ai/claude-code`, then `claude login` (your Claude subscription) |
| career-ops submodule | `git submodule update --init` |
| Playwright chromium | `(cd web && npx playwright install chromium)` |

Then start everything:

```bash
./start.sh               # installs what changed, migrates the DB, builds the dashboard, opens http://127.0.0.1:8787
./start.sh status        # pid, uptime, health of db / scheduler / claude / career-ops / each job board
./start.sh logs -f       # follow the server log
./start.sh stop          # stop it (restart = stop + start)
```

Leave it running. The scheduler fetches job boards every 3 h (07:00-23:00), scans ~170 company career pages
and the remote boards at 08:00 and 17:00, and auto-evaluates the top 10 new leads per day.
Autostart at login arrives in Wave 4 (`./start.sh autostart on`); until then run `./start.sh` after a reboot.

## 2. Your inputs (already done, check once)

| Input | Where | Status |
|---|---|---|
| CV variant A (Java/Spring backend) | `data/cv/cv_a.md` | ✅ |
| CV variant B (adds AI developer tooling) | `data/cv/cv_b.md` | ✅ approved 12 Nov |
| career-ops master CV + profile (CTC 15 LPA expected, 30-day notice) | `data/careerops/cv.md`, `data/careerops/config/profile.yml` | ✅ |
| Target companies | `data/careerops/portals.yml` (173 companies + 4 remote boards) | ✅, extend anytime |

Edit the CV markdown directly when your facts change; tailored CVs are always generated from these files and
fact-checked against them.

## 3. Dashboard settings (5 min, Settings page)

Settings are stored in the database after the first start. Editing `data/config.yml` later has no effect, use
the **Settings** page:

- **Auto-evaluate top N**: 10/day. Each evaluation costs ~3.5 min and a noticeable slice of your Claude quota
  (~$1.3 API-equivalent). Lower it if you hit Claude usage limits; raise it if the queue stays good.
- **Claude concurrency**: keep 2.
- **Query matrix**: titles × locations × sites. Add titles you would accept (e.g. "Java Backend Engineer",
  "Software Engineer II"); remove ones that bring noise. Google Jobs stays off (returns nothing).
- **Targets**: 60 applications + 15 referral requests per week.
- **Sources**: pause any board that keeps failing; unpause after a day.
- **Run intake now**: use it once after the first start so you don't wait 3 h for the first leads.

## 4. Inbound profiles: make recruiters find you (60-90 min, once)

In India many interview calls come from recruiters searching profiles. The **Settings → Profiles** checklist
tracks these; tick items as you finish them.

| Platform | Do this |
|---|---|
| **Naukri** | Headline + key skills (Java, Spring Boot, Microservices, Keycloak/IAM, REST, Kafka), upload CV A, notice period 30 days, preferred locations Chennai/Bengaluru/Remote, expected CTC. **Refresh daily** (edit any field and save): the dashboard reminds you and opens the page, ~2 min |
| **LinkedIn** | Open to Work (recruiters only), headline from the plan PDF, location + remote, skills; turn on job alerts (section 5) |
| **Instahyre** | Complete profile, set "actively looking", CTC + notice |
| **Hirist** (tech) | Profile + CV A, Java category, alerts on |
| **Cutshort** | Profile, skills, set open to opportunities |
| **Wellfound** | Profile, India/remote, "actively looking" |
| **Uplers** | Profile + skill test if offered (remote roles) |
| **foundit** (Monster India) | Profile + CV A |
| **Turing / Arc** (remote) | Profile; take their vetting test when you have 1-2 h |

## 5. Job alerts → Gmail (30 min, once) **(prep for Wave 3)**

Hirist, Instahyre, Cutshort, foundit, Wellfound and Uplers can't be scraped without logging in as you, so the app
reads their **alert emails** instead. Use the Gmail address you'll give the app.

For each platform, create alerts for: Java Developer, Backend Engineer, Spring Boot, Microservices; locations
Chennai, Bengaluru, Remote; experience 2-5 years; frequency **daily** (instant if offered). Also create
LinkedIn job alerts and Naukri job alerts with the same terms.

Recommended Gmail filter so they don't clutter your inbox: Gmail → search box → *Show search options* →
From: `hirist OR instahyre OR cutshort OR foundit OR wellfound OR uplers OR jobalerts-noreply@linkedin.com OR naukri`
→ *Create filter* → *Apply the label* `job-alerts` (+ *Skip the Inbox* if you like). The app reads all mail,
so the label is only for you.

## 6. Export sample emails as `.eml` (20 min) **(prep for Wave 3)**

Wave 3's parsers are built and tested on real examples of each email type. You export them once; they stay on
your Mac under `data/` (gitignored, never committed). The builder agent turns them into sanitized test fixtures
(names, emails, phone numbers and links replaced) before anything enters the repo.

### 6.1 How to download one email as `.eml` in Gmail (web)

1. Open the email in Gmail (browser, desktop).
2. In the message header, top right, click the **⋮ (More)** button next to the Reply arrow.
3. Click **Download message**. Your browser saves `<subject>.eml` to `~/Downloads`.

Alternatives: *⋮ → Show original → Download original* (same content, `.txt`; rename to `.eml`), or in Apple Mail
drag the message onto a Finder folder (creates a `.eml`).

### 6.2 What to export (aim for 3 per row, more is better; recent ones first)

| Folder (`data/emails/raw/…`) | Gmail search to find them | What |
|---|---|---|
| `linkedin/` | `from:jobalerts-noreply@linkedin.com` | LinkedIn job alert digests |
| `naukri/` | `from:naukri.com "jobs"` | Naukri job alert / "jobs for you" |
| `hirist/` | `from:hirist` | Hirist job alerts |
| `instahyre/` | `from:instahyre` | Instahyre job matches / interest mails |
| `cutshort/` | `from:cutshort` | Cutshort matches |
| `foundit/` | `from:foundit OR from:monsterindia` | foundit alerts |
| `wellfound/` | `from:wellfound OR from:angel.co` | Wellfound job digests |
| `uplers/` | `from:uplers` | Uplers job mails |
| `inbound/` | `from:naukri.com recruiter`, `"InMail"`, `from:linkedin.com "sent you a message"` | A recruiter reaching out (Naukri recruiter mail, LinkedIn InMail notification, consultancy mail) |
| `ack/` | `"thank you for applying" OR "application received"` | ATS acknowledgements (Workday, Greenhouse, Lever, ...) |
| `rejection/` | `"unfortunately" "application"` | Rejections |
| `interview/` | `"interview" ("schedule" OR "invite")` | Interview invites / recruiter call requests |

If you just created the alert accounts, the first alert mails take 1-3 days to arrive: export the ones you have,
add the rest later. Fewer than 3 for a sender is fine; tell the lead which ones are missing.

### 6.3 Put them in place

```bash
cd ~/IdeaProjects/job-hunter
mkdir -p data/emails/raw/{linkedin,naukri,hirist,instahyre,cutshort,foundit,wellfound,uplers,inbound,ack,rejection,interview}
mv ~/Downloads/*.eml data/emails/raw/linkedin/    # repeat per sender, or drag in Finder: open data/emails/raw
ls data/emails/raw/*/ | head -50                   # check
```

Privacy note: during Wave 3 a coding agent reads these files to write parsers and sanitized fixtures; the email
content passes through that agent's model provider. Skip any email you don't want read (e.g. salary negotiations).

## 7. Gmail app password **(prep for Wave 3)**

1. Turn on 2-Step Verification: <https://myaccount.google.com/security>.
2. Create an app password: <https://myaccount.google.com/apppasswords> → name it `job-hunter` → copy the 16 characters.
3. IMAP is on by default in Gmail. If *Settings → See all settings → Forwarding and POP/IMAP* still shows an IMAP toggle, enable it.
4. Store it in the macOS Keychain (the app only reads it; Gmail access is read-only in code):

```bash
security add-generic-password -U -s jobhunter -a gmail_address -w 'you@gmail.com'
security add-generic-password -U -s jobhunter -a gmail_app_password -w   # prompts; paste the 16 chars
./start.sh doctor                                                     # shows "Gmail app password in Keychain"
```

(Wave 3 adds a Setup page form that does the same.)

## 8. Your daily routine (~30 min, dashboard only)

1. **Today**: interview calls this week (headline), applied vs 60, referrals vs 15, fresh hot leads, action queue.
2. **Leads**: ranked, fresh first. Shortlist or Skip (reason). *Evaluate* anything you're unsure about (A-H report,
   score 1-5, legitimacy). Apply only to score ≥ 3.5 unless you override.
3. **Quick apply** tab: Naukri / LinkedIn Easy Apply jobs grouped. Open each, apply on the platform, *Mark applied*.
4. **Company ATS jobs** (Job detail): *Generate CV A or B* → preview → *Approve* → *Find contacts* → copy the
   referral draft and send it yourself on LinkedIn → *Assist apply* opens the form pre-filled in a browser window:
   check every field, attach/confirm the CV, **you press Submit** → *Mark applied* (follow-up date set +5 working days).
5. **Tracker**: drag cards when something happens (Screening = an interview call; that's the KPI).
6. **Naukri**: refresh the profile when Today shows the reminder.
7. **Sunday**: look at which sources and titles produce calls; adjust the query matrix and companies.

Speed tips: apply within 24-48 h of posting (fresh badge) — early applicants get far more recruiter views; send
referral requests before applying to the same company; batch quick-applies in one sitting.

## 9. Getting the most out of it

| Lever | Do |
|---|---|
| Coverage | Add companies you'd love to work at to `data/careerops/portals.yml` (career-ops detects their ATS). Add titles to the query matrix |
| Quality | Keep CV A/B truthful and current; fact-check blocks invented claims |
| Freshness | Keep the server running all day so the 3-hourly fetch catches new posts early |
| Inbound | Naukri refresh daily; all platform profiles complete; reply fast to inbound recruiters |
| Referrals | 15/week; warm intros convert far better than cold applies |
| Quota | If Claude limits bite, lower auto-evaluate N to 5 and evaluate manually only what you'd apply to |
| Accuracy | Label the golden set (`data/golden/*.jsonl`, apply / skip per posting) when asked — it keeps the filters honest |

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Dashboard won't open | `./start.sh status`, then `./start.sh logs` |
| No new leads | Settings → Sources: a board paused after repeated failures (LinkedIn rate limits) → wait or unpause |
| Evaluate / CV runs fail | Job detail run log; `claude` logged in? (`claude login`), quota left? |
| Assist apply opens nothing | `(cd web && npx playwright install chromium)` |
| Anything else | `./start.sh doctor` |

Data lives in `data/` (SQLite `data/jobhunter.sqlite`, reports and PDFs under `data/careerops/`, CVs in
`data/cv/`). Back it up by copying the folder; it's never committed.
