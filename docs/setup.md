# Setup guide

Goal: get interview calls with the least manual effort. This page lists what **you** do once, then what a normal day looks like. The app never submits applications or sends messages for you.

---

## 1. One-time machine setup (10 min)

```bash
git clone --recurse-submodules <repo> && cd job-hunter
./start.sh doctor        # lists anything missing with the exact install command
```

Fix every red ✗ it prints. Typical ones:

| Missing | Fix |
|---|---|
| uv | `brew install uv` or <https://docs.astral.sh/uv/> |
| node ≥ 22.13 | `brew install node@22 && brew link --overwrite node@22` |
| AI CLI (claude and/or codex) | `npm install -g @anthropic-ai/claude-code` then `claude login`; or install Codex and sign in. Needed for AI scoring, tailored CVs, contact search |
| career-ops submodule | `git submodule update --init` |
| Playwright chromium | `(cd web && npx playwright install chromium)` |

Then start everything:

```bash
./start.sh               # installs what changed, migrates the DB, builds the dashboard, serves http://127.0.0.1:8787
./start.sh status        # pid, uptime, health of db / scheduler / AI / career-ops / each job board
./start.sh logs -f       # follow the server log
./start.sh stop          # stop it
./start.sh autostart on  # start at login (macOS)
```

Leave it running: the scheduler fetches job boards every few hours, scans your tracked companies twice a day, reads Gmail, and evaluates the best new jobs each night. Different port: `JOBHUNTER_PORT=9000 ./start.sh`.

## 2. Your inputs

1. **Your CV** as markdown: Settings → CVs & email (variant A required, B optional), or save `data/cv/cv_a.md`. Tailored CVs are written from it and fact-checked against it, so keep it truthful and current.
2. **Your profile** for the AI evaluator and the email signature:

   ```bash
   mkdir -p data/careerops/config
   cp vendor/career-ops/config/profile.example.yml data/careerops/config/profile.yml
   $EDITOR data/careerops/config/profile.yml
   cp data/cv/cv_a.md data/careerops/cv.md      # the master CV career-ops reads
   ```
3. **A resume PDF**: Settings → CVs & email → Resume for emails. It is attached to HR emails when a job has no tailored CV.
4. **Gmail app password** (section 6).

## 3. Settings (10 min, Settings page)

Defaults describe one person's search: change them. See [configuration.md](configuration.md) for every field.

- **Job search**: titles × locations × sites; cities, experience range, salary floor, stack words.
- **Companies**: career pages to scan. Add the employers you would love to work at.
- **Goals & automation**: weekly targets, how many AI fit reports per day (each costs model quota; start at 5-10), which AI engines and models.
- **CVs & email**: who signs your emails, the email wording, daily cap.
- **System → Run intake now**: do it once after the first start so you do not wait hours for the first jobs.

## 4. Inbound profiles: make recruiters find you (60-90 min, once)

Many interview calls come from recruiters searching profiles. **Settings → Profiles** tracks a checklist per platform (Naukri, LinkedIn, Instahyre, Hirist, Cutshort, Wellfound, Uplers, foundit, Turing, Arc). Complete the profiles, upload your CV, set notice period and expected pay, and **refresh Naukri daily** (the dashboard reminds you).

## 5. Job alerts → Gmail (30 min, once)

Some sites cannot be scraped without logging in as you, so the app reads their **alert emails** instead (Hirist, Instahyre, Cutshort, foundit, Wellfound, Uplers, plus LinkedIn and Naukri alerts). Create daily alerts on each for your target titles and locations. Optional Gmail filter so alerts do not clutter your inbox: label them `job-alerts` and skip the inbox; the app reads all mail either way.

## 6. Gmail app password

1. Turn on 2-Step Verification: <https://myaccount.google.com/security>.
2. Create an app password: <https://myaccount.google.com/apppasswords>, name it `job-hunter`, copy the 16 characters.
3. IMAP is on by default in Gmail.
4. Settings → CVs & email → Gmail: paste the address and password, **Save to keychain**, then **Test Gmail**. (Headless machine without a keychain: set `JOBHUNTER_GMAIL_ADDRESS` and `JOBHUNTER_GMAIL_APP_PASSWORD` instead.)

Gmail access is read-only except for two things you trigger: **Send** and **Save as Gmail draft** on a job's Email HR card.

## 7. Your daily routine (~30 min)

1. **Home**: interview calls this week, applications vs target, today's picks, the action queue.
2. **Jobs**: ranked, fresh first. Shortlist or skip (with a reason). *Evaluate with AI* anything you are unsure about. Aim for jobs scoring ≥ your minimum (default 3.5).
3. **Quick apply** tab: Naukri / LinkedIn Easy Apply jobs grouped. Open each, apply on the site, *Mark applied*.
4. **A job page** for a company-site job: *Generate CV* → preview → *Approve* → *Assist apply* (opens the form pre-filled; **you** press Submit) → *Mark applied*. Then use **Email HR about this job**: check the address, press **Send**. Details in [email-hr.md](email-hr.md).
5. **Applications**: drag cards when something happens (Screening = an interview call; that is the KPI).
6. **Inbox**: confirm recruiter mail and status updates the app read from Gmail.
7. **Weekly**: Insights shows which sources and titles produce calls; adjust the search and companies.

Speed tips: apply within 24-48 h of posting (fresh badge); email HR right after applying; batch quick-applies in one sitting.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| Dashboard will not open | `./start.sh status`, then `./start.sh logs` |
| No new jobs | Settings → System → Sources: a board paused after repeated failures (rate limits) → wait or unpause |
| Evaluate / CV runs fail | The run log on the job page; is the AI CLI logged in, quota left? |
| Assist apply opens nothing | `(cd web && npx playwright install chromium)` |
| Email HR says Gmail is not connected | Settings → CVs & email → Gmail → Test Gmail (app password, not your Google password) |
| Email HR found no address | Type one; or enable `look_up_web`; some postings simply have none |
| Anything else | `./start.sh doctor` |

Your data lives in `data/` (SQLite `data/jobhunter.sqlite`, reports and PDFs under `data/careerops/`, CVs in `data/cv/`). Back it up by copying the folder; it is never committed.
