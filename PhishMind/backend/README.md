# PhishMind Backend

FastAPI backend for PhishMind — parses an email, runs deterministic technical
and URL heuristics, sends the cleaned content to Gemini for semantic/social-
engineering analysis, verifies the claimed brand against the sender domain,
and combines everything into a single 0–100 phishing risk score.

The AI never outputs the final score — `app/risk/scorer.py` always computes
it deterministically from Gemini's structured evidence plus the heuristic
checks, so results are consistent and reproducible.

## Setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux
```

Open `.env` and set:

```
GEMINI_API_KEY=your_real_key_here
```

Get a key from https://aistudio.google.com/apikey — without it, scans still
run (technical + URL heuristics only) but semantic/social-engineering
analysis is skipped and clearly labeled as unavailable in the response.

## Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Check it's alive:

```bash
curl http://localhost:8000/api/v1/health
```

## Test a scan

```bash
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d "{\"raw_email_text\": \"$(cat tests/samples/phishing_sample.eml | sed 's/"/\\"/g' | tr '\n' '\\n')\"}"
```

Or from Python:

```python
import requests
raw = open("tests/samples/phishing_sample.eml").read()
r = requests.post("http://localhost:8000/api/v1/scan", json={"raw_email_text": raw})
print(r.json())
```

## Run the test suite

```bash
pytest
```

## API endpoints

| Method | Path                     | Purpose                                             |
|--------|--------------------------|------------------------------------------------------|
| GET    | `/api/v1/health`         | Liveness check                                        |
| POST   | `/api/v1/scan`           | Scan a raw email (`.eml` base64 or pasted text)       |
| GET    | `/api/v1/history`        | Recent scan results                                   |
| POST   | `/api/v1/listener/start` | Start the live IMAP IDLE inbox listener               |
| POST   | `/api/v1/listener/stop`  | Stop the listener                                     |
| GET    | `/api/v1/listener/status`| Whether the listener is running                       |
| GET    | `/api/v1/listener/events`| Server-Sent Events stream of new scans as they happen |

## Live demo (IMAP listener)

1. Generate a Gmail **App Password**: Google Account → Security → 2-Step
   Verification → App Passwords.
2. `POST /api/v1/listener/start` with `{"host": "imap.gmail.com", "username": "you@gmail.com", "app_password": "..."}`.
3. Send yourself a test email from a second account. Within a few seconds it
   will be scanned automatically and pushed to any client listening on
   `/api/v1/listener/events`.

## Running it silently in the background (Windows)

Instead of starting the listener by hand every time, you can have PhishMind
run invisibly in the background and watch your real inbox continuously —
see the three scripts at the project root (one level above `backend/`):

1. Fill in `IMAP_HOST`, `IMAP_USERNAME`, and `IMAP_APP_PASSWORD` in `.env`.
   By default (`EMAIL_WATCH_ENABLED=true`), PhishMind does **not** scan 24/7 —
   it watches for a window whose title contains "gmail", "outlook", or "mail"
   (a browser tab or the desktop app), starts scanning the moment one shows
   up, and stops again ~30 seconds after none are visible. Check
   `EMAIL_WATCH_KEYWORDS` / `EMAIL_WATCH_GRACE_SECONDS` in `.env.example` to
   tune this, or set `EMAIL_WATCH_ENABLED=false` for old-school always-on
   scanning from boot instead.
2. From the project root, run `start_phishmind.bat`. This launches the
   backend with `pythonw` (no console window at all), so it keeps running
   even after you close the terminal. It writes its PID to
   `backend/phishmind.pid` and its logs to `backend/phishmind_out.log` /
   `backend/phishmind_err.log`.
3. Check on it any time with `status_phishmind.bat`.
4. Stop it with `stop_phishmind.bat`.
5. Want it to start automatically every time you log into Windows? Run
   `install_autostart.bat` once (undo with `uninstall_autostart.bat`).

When `DESKTOP_NOTIFICATIONS=true` (the default) and a live-scanned email
comes back SUSPICIOUS or PHISHING, a native Windows toast notification pops
up immediately — you don't need the dashboard open to know it caught
something.

## Project layout

```
backend/
  main.py                    FastAPI app + routes
  app/
    config.py                 env-driven settings
    pipeline.py                shared scan pipeline (used by /scan and the listener)
    parsing/
      email_parser.py           .eml -> structured dict (text/plain + text/html fallback)
      technical.py               SPF/DKIM/DMARC + Reply-To mismatch + lookalike link domain
    utils/
      url_utils.py               URL extraction + heuristic scoring
    ai/
      prompt.py                  Pydantic schema + prompts for Gemini
      gemini_analyzer.py         Gemini call with structured output + safe fallback
    verification/
      brand_verifier.py          claimed brand vs sender domain
    risk/
      scorer.py                  deterministic 0-100 aggregation
    listeners/
      imap_listener.py           background IMAP IDLE watcher + SSE event queue
    db/
      database.py, models.py     SQLite scan history
  tests/                        pytest unit tests + sample .eml fixtures
```
