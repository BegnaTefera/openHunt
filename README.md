# openHunt

A job-search assistant for remote tech roles of every kind. The current release includes public job-board collectors for Greenhouse, Lever, and Ashby; company discovery; accounts with onboarding and CV upload; per-user scoring and application drafts; Gmail reply tracking; Telegram alerts; and UI company setup. Workable links can be recognized, but collection is disabled because Workable's official jobs API requires an account token. Nothing sends application emails.

## Monorepo layout

- `api/` — FastAPI app, ATS collectors, SQLAlchemy models, Alembic migrations, and API image
- `worker/` — separate APScheduler process that synchronizes configured public job boards
- `web/` — Next.js 14 App Router app and Vercel project configuration
- `docker-compose.yml` — local Postgres, API, worker, and frontend
- `render.yaml` — Render API service (collection runs for free in GitHub Actions)
- `.github/workflows/collect.yml` — hourly free collection, discovery, and migrations

## Local development with Docker Compose

1. Copy `.env.example` to `.env` and replace `SECRET_KEY` with a strong random value (32+ characters). Do not commit `.env`.
2. Start the complete local stack:

   ```powershell
   docker compose up --build
   ```

3. Open the hello page at `http://localhost:3000`, the API health endpoint at `http://localhost:8000/health`, and API docs at `http://localhost:8000/docs`.

The API container runs `alembic upgrade head` before starting FastAPI. Accounts are created through the sign-up screen (see Authentication); the database stores only Argon2id password hash. Compose uses local Postgres credentials from `.env` for development. The worker runs its configured-company collection immediately, then at
`JOB_FETCH_INTERVAL_MINUTES`. Each enabled public-board collector also has an
independent initial run and schedule.

To stop the stack, run `docker compose down`. To also remove local database data, explicitly run `docker compose down --volumes`.

## Local development without Docker

Use Python 3.12 and Node.js 20.

```powershell
Copy-Item .env.example .env
Set-Location api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Run the worker in another terminal from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\api).Path
& .\api\.venv\Scripts\python.exe -m worker.main
```

Run the frontend in another terminal:

```powershell
Set-Location web
npm ci
npm run dev
```

For local non-Docker API use, point `DATABASE_URL` at a running Postgres instance and use the SQLAlchemy driver URL form `postgresql+psycopg://...`.

## Database schema

The Alembic migration chain creates:

- `companies`
- `companies.ats_type` and `companies.ats_slug` with a unique ATS/slug pair
- `jobs` with a unique URL, raw JSONB source payload, a Postgres `text[]` for tags, and discovery/scoring metadata
- `applications` with the requested PostgreSQL status enum and one application per job
- `documents` with JSONB answers
- `emails` with a unique Gmail message ID and optional application link
- `gmail_connections` with encrypted per-user OAuth tokens, `tracked_gmail_threads`, and a Telegram notification outbox
- `events` for audit records
- `profile`, constrained to one row
- `users` (email, Argon2id password hash, admin and lockout state), `refresh_tokens` (hashed, rotating sessions), `profile` and `applications` per user, and `cv_documents`

Apply or inspect migrations from `api/`:

```powershell
alembic upgrade head
alembic downgrade -1
```

Downgrading revision `0003` requires every job to have a company. Before
downgrading, assign unmatched board jobs to companies or remove them; the
migration refuses to discard or silently reassign those jobs.

## Authentication

Anyone allowed to sign up creates an account with an email and a password (10 to 128
characters, not a common password). Passwords are hashed with Argon2id. Older scrypt hashes
still work and are upgraded on the next login.

- **Sessions:** logging in returns a short-lived access token (15 minutes) that the website
  keeps only in memory, and sets a rotating refresh token in an `HttpOnly`, `SameSite=Strict`
  cookie (30 days). Refresh tokens are stored hashed. Using an old token again after it was
  rotated ends that whole session family, which limits the damage of a stolen cookie.
- **Same-origin API:** the browser only talks to `/api` on the website's own address. Next.js
  forwards it to the real API (`API_URL`, set when the frontend is built), so the cookie is
  first-party and the API address is not exposed. CORS is not needed for the website.
- **Lockout:** five wrong passwords lock an account for 15 minutes. Login errors never say
  whether the email exists.
- **Change password** signs out every other device. The Account page also has "sign out
  everywhere" and "delete my account" (removes the profile, CV, drafts and applications).
- **Who may sign up:** `SIGNUP_ENABLED` and `ALLOWED_SIGNUP_EMAILS` (see `.env.example`)
  control account creation. Sign-ups never grant admin privileges, even when an email is on
  the allowlist. Provision an admin explicitly from a trusted shell with
  `python -m app.cli set-credentials you@example.com --admin` (from `api/`, with `DATABASE_URL`
  pointing at the target database). This creates the account or resets its password and signs
  out its existing sessions. Admins manage the shared company list; everyone else can read it.
  Restrict sign-ups with `ALLOWED_SIGNUP_EMAILS` or close them with `SIGNUP_ENABLED=false`.
- **Forgotten password:** there is no email reset, because that needs an email service. Run
  `python -m app.cli set-credentials you@example.com` (from `api/`, with `DATABASE_URL` pointing
  at your database). It creates the account or resets its password and signs it out everywhere.
- **Upgrading an old single-user database:** migration 0005 keeps the old account as an admin
  with the email `<old username>@legacy.invalid`. Run
  `python -m app.cli set-credentials you@example.com --admin` to create or promote an account
  with your real email.

## Gmail reply tracking and Telegram alerts

Gmail is optional and is connected by each user from **Account**. The app requests
read-only Gmail metadata access; it does not read or store message bodies or send mail.
After connecting, mark an application as applied, choose a recent sent Gmail thread, and
link it to that application. Replies arriving after the link are checked by the worker,
stored as message metadata, and move the application to `replied` unless it already has a
later outcome (interview, rejection, or offer). Unlink a thread or disconnect Gmail from
Account at any time. Gmail refresh tokens are encrypted at rest using `SECRET_KEY`; keep
that key stable and identical on the API and worker.
The always-on worker checks at `GMAIL_POLL_INTERVAL_MINUTES`; the GitHub Actions worker
checks once per scheduled hourly run.

To configure Gmail:

1. Enable the Gmail API in Google Cloud and create a Web application OAuth client. Configure
   the consent screen and add test users while the app is in testing.
2. Register `GMAIL_REDIRECT_URI` as an authorized redirect URI. Locally it is
   `http://localhost:8000/integrations/gmail/callback`; in production use your API's public
   URL with `/integrations/gmail/callback`. The value must match exactly.
3. Set `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, and `WEB_APP_URL`
   for the API and worker. Google may require verification before external users can use
   Gmail scopes beyond your configured test users.

To enable Telegram, create a bot with BotFather, add it to the destination chat, and configure
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` on the API and worker. This is a shared destination:
alerts from every account go to that chat. It receives application status changes, newly
collected jobs matching each user's role preferences, and detected Gmail replies. Messages
include job links and relevant titles/status, not Gmail subjects, email bodies, or account
email addresses. Failed deliveries are retried by the worker.

## Onboarding and CV

After the first sign-up a four-step setup collects your CV, the kinds of roles you want, your
level and where you can work, and facts for cover letters. The CV (PDF, `.docx` or text, up to
3 MB) is read locally with no AI to prefill your name and skills, and the file is stored in
Postgres for your account only. Scanned, image-only PDFs are not supported.

## Role types

Jobs are matched to role families instead of two fixed titles: backend, frontend, full-stack,
general software engineering, mobile, DevOps/SRE/cloud, data, ML/AI, QA, security, design/UX,
product and project management, engineering management, support and solutions, developer
relations and technical writing, embedded, games, and web3 (`GET /roles`). An empty selection
means every tech role; non-tech jobs such as sales or marketing are not matched. Extra
job-title words can be added per user. Discovery searches for the union of what all users want.

## Dashboard

The Next.js dashboard provides a score-ranked job list with source, company,
seniority, and new-today filters; job details with score reasons and explicit
Shortlist, Skip, and Mark applied actions; a status pipeline; profile and
company setup pages; and source-level search statistics. The API exposes
authenticated `/jobs`, `/jobs/{id}`, `/jobs/{id}/status`, `/profile`, and
`/stats` endpoints for these views. Job scores are evaluated against the
saved profile when jobs are read, so score changes take effect without a
separate rescoring task.

If changing the login username after initial account creation, update the existing user record deliberately; the API refuses to start with a conflicting configured username. Never store access tokens or plaintext credentials in the database.

## Job-board collectors

Add company boards from the signed-in UI with their ATS and board slug. The worker calls the public listings API, normalizes each source to the `jobs` table, keeps the original source item in `raw_payload`, and deduplicates by canonical listing URL. Existing jobs are marked inactive only after the corresponding collector returns a successfully validated complete snapshot; request or response failures are logged and do not deactivate listings.

Greenhouse, Lever, and Ashby requests use the configured User-Agent, shared per-process rate limiter, request timeout, and robots.txt check. A disallowed robots path or failed request does not update that company's snapshot.

The worker also collects public-board listings from Remotiko, TrulyRemoteWork,
and Dynamite Jobs. Each source runs and fails independently; failures are logged
and recorded in `events`. Outbound requests share a process-wide limiter that
enforces both `REQUESTS_PER_MINUTE` and a minimum two-second gap, including
robots.txt checks. Public HTML/text responses are cached in worker memory for
15 minutes and robots.txt is checked on each use. Remotiko uses the
`africa_inclusive` region filter and captures the job's external Apply URL.
TrulyRemoteWork uses its published
full-corpus and Markdown job pages, retaining the original Apply URL for ATS
matching. Dynamite Jobs uses the public Development category sitemap. Collection
is capped at `MAX_JOBS_PER_RUN` per source. Jobs with a recognized Apply URL are
linked to an already-configured ATS company; unmatched listings remain
unlinked. Existing board listings are deactivated only after a complete source
snapshot, not when a capped or failed run returns only a partial set.

Truly Remote (`trulyremote.co`) is intentionally not automated: its terms
prohibit automated and systematic collection without written permission. Add
it only after obtaining that authorization. Bruntwork Careers and Pavago are
not collected.

## Job scoring

`POST /jobs/score` applies a rules gate before its existing profile-fit score.
The rules gate keeps only titles containing “backend” or “full-stack”, rejects
senior/staff/principal/lead roles unless listed in `allowed_seniority`, and
rejects explicitly stated country, timezone, and work-authorization limits
that conflict with configured profile values. Set `profile_country`,
`profile_timezones`, and `profile_work_authorizations` in the scoring request
to enable those comparisons; leave them unset when the corresponding profile
information is unknown. The response reports rule-based exclusions with a
score of zero and an explanatory reason.

| ATS | Public endpoint used |
| --- | --- |
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true` |
| Lever | `https://api.lever.co/v0/postings/{site}?mode=json&skip={offset}&limit=100` |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{board_slug}?includeCompensation=true` |
| Workable | Not collected. Its documented `/spi/v3/jobs` endpoint requires an account token with `r_jobs`; enable only after deciding how to configure that credential securely. |
| Remotiko | Public Africa-inclusive HTML listings and job pages |
| TrulyRemoteWork | Published `llms-full.txt` corpus and Markdown job pages |
| Dynamite Jobs | Public Development category sitemap and job pages |

Endpoint references: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html), [Lever Postings API](https://github.com/Lever/postings-api), [Ashby Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api), [Workable token setup](https://workable.readme.io/reference/generate-an-access-token), and [Workable jobs response](https://workable.readme.io/reference/jobs).

### Detect ATS from pasted application URLs

From PowerShell, run the detector and paste one apply URL per line; finish input with Ctrl+Z then Enter:

```powershell
Set-Location api
py -3.12 -m scripts.detect_ats
```

Or pass URLs directly:

```powershell
py -3.12 -m scripts.detect_ats "https://jobs.lever.co/acme/abc123/apply"
```

It prints one JSON result per URL with `ats_type` and `ats_slug`. Workable URLs are identified even though its collector is currently disabled.

## Deployment

### Render API

1. Connect the repository in Render and deploy the `render.yaml` Blueprint.
2. Create a Neon Postgres database and set `DATABASE_URL` in Render. Neon's plain `postgresql://` URL works; it is converted to the `psycopg` driver automatically.
3. Set a strong `SECRET_KEY` and, if restricting registrations, `ALLOWED_SIGNUP_EMAILS` in the API service environment. Add `SERPAPI_API_KEY` to show the provider as configured in Discovery. `CORS_ORIGINS` is not needed because the website calls the API through its own `/api` proxy.
4. For Gmail and Telegram, set `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `WEB_APP_URL`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` on the API service. `GMAIL_REDIRECT_URI` must use the public Render API URL and match the Google OAuth client exactly.
5. Provision your administrator from a trusted machine with `DATABASE_URL` set to the Render database URL: from `api/`, run `python -m app.cli set-credentials you@example.com --admin` and enter a strong password when prompted. The command creates the account or resets its password and signs out its existing sessions. Set `SIGNUP_ENABLED=false` in Render after setup if you do not need more registrations.
6. Render builds the API from its Dockerfile. The API applies Alembic migrations before serving traffic; `/health` is its health check.

### Vercel frontend

1. Import the repository in Vercel and set the project root directory to `web`.
2. Set `API_URL` to the deployed Render API URL (no trailing slash). It is read at build time, so redeploy after changing it.
3. Deploy using the Next.js framework preset and the included `web/vercel.json`.

### Free scheduled collection (GitHub Actions)

The always-on worker is not needed in production. GitHub Actions runs the configured ATS
companies, public boards, and Gmail checks hourly via `.github/workflows/collect.yml`.
Company discovery runs separately each day at 6:00 AM East Africa Time
(03:00 UTC) via `.github/workflows/discovery.yml`. Both workflows apply database migrations
before running. Setup:

1. Push the repository to GitHub.
2. Under Settings, Secrets and variables, Actions, add the secret `DATABASE_URL` (your Neon URL).
3. Add `SECRET_KEY` (the same value as Render, used to decrypt Gmail tokens) and
   `SERPAPI_API_KEY`. The SerpApi monthly cap defaults to 250 searches and counts failed
   attempts too. Optional secrets: `SERPER_API_KEY`, `GMAIL_CLIENT_ID`,
   `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `TELEGRAM_BOT_TOKEN`, and
   `TELEGRAM_CHAT_ID`. Optional variables: `WEB_APP_URL` and `USER_AGENT`.
4. Open the Actions tab, choose "Collect jobs", and press "Run workflow" to test hourly
   collection. Choose "Discover companies" to run discovery manually. Discovery uses
   `SERPAPI_API_KEY` and the monthly cap defaults to 250 searches; failed attempts count
   toward the cap. The collection workflow needs the same `SECRET_KEY`, Gmail credentials,
   and Telegram bot/chat values as the API to poll connected inboxes and deliver queued alerts.

GitHub may delay scheduled runs by several minutes, and it disables scheduled workflows in
repositories with no activity for about 60 days; re-enable it from the Actions tab if that
happens. Check GitHub's current free-minute limits for your repository type. Run steps
locally with `python -m worker.run_once discovery|companies|boards|gmail|all` (from the repository
root with `PYTHONPATH=api`).

## Company discovery

Discovery finds new Greenhouse, Lever, and Ashby boards and adds the ones that list at least
one backend or full-stack title. It uses these free sources, each optional:

- **Common Crawl** public URL index. No key. Each run queries one slug-prefix slice per host
  (a-z, 0-9, rotating) so successive runs explore different companies.
- **SerpApi** and optional **Serper**, with Google-style queries such as
  `site:jobs.lever.co "backend engineer" remote`. Each provider has a daily, monthly, or total
  cap stored in Postgres, so a run stops before the free quota is used up. SerpApi is capped at
  250 searches per month by default; attempts count against the cap even when they fail. Set
  `SERPAPI_API_KEY` and, optionally, `SERPER_API_KEY` in `.env`.

Candidates are validated by calling the board's public jobs API once. Dead boards and boards
with no matching roles are remembered and retried after 90 and 30 days. Network errors are not
remembered, so they are retried next run. The Discovery page shows budgets and results.

## Application drafts

Open a job and press "Write draft". Without any AI key the draft comes from a template that
only uses facts you entered on the Profile page (name, headline, summary, projects, skills that
appear in the job text). With a free-tier AI key (`GROQ_API_KEY`, Cloudflare, or Gemini), the
letter is written by the model, then checked by a second call that lists claims not supported
by your profile; those appear as warnings. If every provider is unavailable or over its daily
cap, the template is used. Nothing is ever sent for you.

## Free-tier AI notes

Providers are tried in order Groq, Cloudflare, Gemini. Groq and Cloudflare state that they do
not train on free-tier inputs; Gemini's free tier may. Calls marked `sensitive` (reserved for
future email classification) only go to the no-training providers. Model names change, so every
model is an environment variable.

The repository includes deployment configuration but has not been deployed to your hosting accounts. Deployment requires connecting your own Render, Neon, and Vercel projects and setting their environment secrets.

## Dependencies and tests

Python dependencies are listed in `api/requirements.txt`; the frontend uses Next.js, React, and TypeScript from `web/package.json`. No new dependency beyond the existing scaffold’s dependency list was added for this skeleton.

Run backend tests, including parsing fixtures and snapshot sync behavior:

```powershell
Set-Location api
py -3.12 -m pytest
```

Collector, discovery, and AI tests use saved fixtures and mocked HTTP; they do not call external
services, and they run without a `.env` file. `tests/test_integration_postgres.py` runs against a
real Postgres database and is skipped unless `TEST_DATABASE_URL` is set. It drops and recreates
the `public` schema, so point it at a throwaway database:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://openhunt:PASSWORD@localhost:5432/openhunt_test"
py -3.12 -m pytest tests/test_integration_postgres.py
```

All outbound collector requests respect robots.txt, share the configured rate limiter, use the configured timeout, and send the configured User-Agent. Credentials must remain environment-managed and must never be stored in plaintext in the database.
