# job-hunter

A local app that hunts jobs for you, so you spend your time on the few that matter.

- **Finds** jobs every few hours: LinkedIn, Naukri, Indeed, Glassdoor, remote boards, your target companies' career pages, and the alert emails job sites send to your Gmail.
- **Ranks** them against your CV: rules first, then an AI fit score (1-5) for the best ones.
- **Prepares** each application: a tailored CV (fact-checked against your own CV), an apply checklist, a pre-filled form you review.
- **Emails HR in one click**: open a job, the recruiter / HR address is found for you (job post, job page, company site, or type one), the email is already written with the job ID and your CV attached. You press Send.
- **Tracks** everything: applications by stage, recruiter replies read from Gmail, follow-up reminders, and what is actually getting you calls.

Everything runs on your machine. Your CV, emails and database stay in `data/` (git-ignored). The app **never submits an application or sends a message on its own**: every send is one click from you.

## Quick start

You need macOS or Linux, [uv](https://docs.astral.sh/uv/), Node 22.13+, and (for AI scoring and CV writing) the [Claude CLI](https://docs.claude.com/en/docs/claude-code) logged in or the Codex CLI.

```bash
git clone --recurse-submodules <this repo>
cd job-hunter
./start.sh doctor     # lists anything missing, with the exact command to fix it
./start.sh            # installs, migrates, builds and opens http://127.0.0.1:8787
```

On first open the app gives you a short tour of the screens. Then:

1. **Settings → CVs & email**: upload your CV (markdown), connect Gmail (an *app password*, not your Google password), upload a resume PDF, and check who signs your emails.
2. **Settings → Job search**: titles, locations and the rules that filter out jobs you would not take.
3. **Settings → Companies**: companies whose career pages are scanned.
4. Press **Run intake now** (Settings → System) and open **Jobs**.

Full walkthrough: [docs/setup.md](docs/setup.md). Every setting, file and environment variable: [docs/configuration.md](docs/configuration.md). How the HR email works and how to word it: [docs/email-hr.md](docs/email-hr.md).

## Everyday commands

```bash
./start.sh status          # is it running, are the job boards healthy
./start.sh logs -f         # follow the server log
./start.sh stop            # stop it
./start.sh autostart on    # start at login (macOS launchd)
./start.sh dev             # API with reload + Vite dev server, for hacking on the app
```

## Configure it your way

Nothing about *you* is hard-coded. Search terms, cities, experience range, salary floor, schedules, weekly goals, AI engines and models, notification quiet hours, the HR email's wording, daily send cap and cool-down are all settings: edit them in the dashboard (**Settings**) or seed them from [`config/jobhunter.example.yml`](config/jobhunter.example.yml). Environment variables cover ports, data location, binaries and Gmail credentials on machines without a keychain. See [docs/configuration.md](docs/configuration.md).

The shipped defaults describe one developer's search (Java backend roles in Chennai / Bengaluru). **Change them first**, otherwise you will be shown that person's jobs.

## Privacy and safety

- Data stays local (`data/`). Gmail is read over IMAP with an app password stored in your OS keychain; the app only writes to Gmail when you press Send (SMTP) or "Save as Gmail draft".
- The AI steps run through the Claude / Codex CLI you are signed in to; job text and your CV are sent to that provider. Skip an engine in Settings → Goals & automation if you do not want that.
- Email HR is capped (default 25 / day), refuses to email the same address twice inside 14 days, and never picks a *guessed* address for you.
- Be a good citizen: job boards rate-limit scrapers; the app paces itself and pauses a source after repeated failures. Use it for your own job search only.

## Project layout

```
src/jobhunter/   FastAPI app, scheduler, intake, scoring, Gmail, reach-out (Python 3.12+)
web/             React dashboard (Vite, Tailwind, shadcn/ui, TanStack Query)
vendor/          career-ops (git submodule): career-page scanning, evaluation, CV PDFs
config/          example settings and the seed company list
contracts/       openapi.json, the API contract the web app is generated from
tests/           pytest (uv run pytest)    web/src/**/*.test.tsx (cd web && npm test)
data/            YOUR data: database, CVs, reports, logs (git-ignored)
```

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). License: [MIT](LICENSE).
