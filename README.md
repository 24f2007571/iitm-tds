# Data-Analyst Telegram Bot

An LLM agent that answers data-analysis questions over Telegram. Each message gets
a single JSON reply: `{"answer": ..., "log_url": "https://.../run.jsonl"}`.

Deploys as a single Flask web service on **Render** — no local machine needs to
stay running, no ngrok.

## How it works

- **app.py** — the whole service: a Flask app that
  - receives Telegram updates via webhook at `POST /webhook/<bot-token>`
  - serves run logs publicly at `GET /logs/<filename>`
  - health check at `GET /`
- **agent.py** — the ReAct-style agent loop. The LLM gets two tools:
  - `run_python` — execute code in a persistent sandbox (pandas/numpy/requests etc.)
  - `submit_answer` — call once, with the final answer value, to finish
- **sandbox.py** — the Python execution sandbox the agent's code runs in.
- **run_logger.py** — writes one JSONL file per chat under `logs/`.
- **telegram_api.py** — thin wrapper over the raw Telegram Bot API (plain
  `requests` calls — no async framework needed for a sync webhook handler).
- **set_webhook.py** — one-off script to tell Telegram where your bot lives.

## Setup

### 1. Create your Telegram bot
Message [@BotFather](https://t.me/BotFather) → `/newbot`. Pick a username ending
in `bot`. Save the token.

### 2. Get an LLM API key
Defaults to **aipipe.org** (the LLM proxy the TDS course provides) via
`AIPIPE_TOKEN`. To use a different provider, change `OPENAI_BASE_URL` and the
key in your env vars — anything OpenAI-compatible works.

### 3. Push this to a public GitHub repo
```bash
git init
git add .
git commit -m "Data-analyst Telegram bot"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 4. Deploy on Render
- Go to https://render.com → **New +** → **Web Service**
- Connect your GitHub repo
- Render should auto-detect `render.yaml`. If not, set manually:
  - **Build command:** `pip install -r requirements.txt`
  - **Start command:** `gunicorn app:app`
- Add environment variables (Render dashboard → Environment):
  - `TELEGRAM_BOT_TOKEN`
  - `AIPIPE_TOKEN`
  - `OPENAI_BASE_URL` = `https://aipipe.org/openai/v1`
  - `AGENT_MODEL` = `gpt-4o-mini`
- Deploy. Render gives you a URL like `https://your-app.onrender.com` and sets
  `RENDER_EXTERNAL_URL` to that automatically — the app reads it at runtime, so
  you don't need to set it yourself.

### 5. Register the webhook (one-time, after each redeploy to a new URL)
Once the service is live:
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN
python set_webhook.py https://your-app.onrender.com
```
This tells Telegram to POST incoming messages to your Render app.

### 6. Test it
Message your bot on Telegram. It should reply with exactly one JSON object.
Visit `https://your-app.onrender.com/logs/chat_<id>.jsonl` in a browser to see
the run log.

Clone the official grading harness to test more thoroughly before submitting:
```bash
git clone https://github.com/Jivraj-18/tds-p1-t2-2026-telegram-bot
```
Point it at your bot and add your own questions to `evals/questions.json`.

## Local testing (optional, before deploying)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, AIPIPE_TOKEN
python app.py          # runs on http://localhost:5000
```
Note: without a public HTTPS URL, Telegram can't reach a locally-run webhook —
this is just for exercising the Flask routes directly (e.g. `curl` a fake
webhook payload), not for receiving real Telegram messages. For that, deploy
to Render first.

## Important: Render's free tier and log persistence

Render's **free** web services:
- **Spin down after ~15 minutes of no traffic**, and take ~30-60s to wake back
  up on the next request (the grading account's first message after idle time
  may see a delay, but should still get answered).
- Use an **ephemeral filesystem** — if the service restarts (redeploy, or a
  cold start after spin-down in some cases), files written to `logs/` may be
  lost.

For this assignment, logs only need to be reachable *while the grader is
checking* — if that's within the same session the questions were answered in,
you're fine. If you want logs to survive restarts/redeploys reliably, the
cleanest fix is to write each log line to a persistent store instead of local
disk — e.g. the Google Cloud Storage bucket you already set up earlier in this
course, appending each entry with `gcloud storage cp` or the GCS Python client.
Ask if you want `run_logger.py` adapted to write to GCS instead of local disk.

## Security note

`sandbox.py` runs LLM-generated Python via `exec`/`eval` — it isolates state
per chat but is **not a hardened security sandbox**. Render's containers are
isolated per-service, which is a reasonable amount of isolation for this use
case, but don't extend this pattern to run arbitrary *user-submitted* code.