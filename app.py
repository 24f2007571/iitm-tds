"""
Main app for Render deployment: a single Flask app that
  - receives Telegram updates via webhook (POST /webhook/<token>)
  - serves run logs publicly (GET /logs/<filename>)
so the whole thing runs as one Render web service on one port - no local
machine, no ngrok, no polling loop needed.

Local dev:  python app.py            (runs Flask's built-in dev server)
Render:     gunicorn app:app         (see Procfile)

After deploying, run set_webhook.py once to point Telegram at your Render URL.
"""

import json
import logging
import os
import threading

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory

from agent import run_agent
from run_logger import LOG_DIR, RunLogger
from telegram_api import send_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("app")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "6"))

# Render sets RENDER_EXTERNAL_URL automatically for every web service.
# Fall back to PUBLIC_BASE_URL if you're deploying somewhere else.
BASE_URL = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")

# Secret path segment (the bot token itself) so randoms can't POST fake
# updates to your webhook.
WEBHOOK_PATH = f"/webhook/{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__)
os.makedirs(LOG_DIR, exist_ok=True)

_chat_histories: dict = {}


@app.route("/")
def index():
    return "Data-analyst Telegram bot is running."


@app.route("/logs/<path:filename>")
def get_log(filename):
    return send_from_directory(LOG_DIR, filename, mimetype="application/x-ndjson")


@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return jsonify({"ok": True})  # ignore non-text updates (photos, stickers, etc.)

    chat_id = message["chat"]["id"]
    text = message["text"]
    log.info("[%s] received: %r", chat_id, text)

    history = _chat_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": text})
    del history[:-HISTORY_LIMIT]

    def work():
        logger = RunLogger(chat_id)
        try:
            answer = run_agent(history, logger)
        except Exception as e:
            log.exception("agent failed")
            logger.log({"event": "error", "error": str(e)})
            answer = {"error": "agent failed to produce an answer"}

        history.append({"role": "assistant", "content": json.dumps(answer, default=str)})
        log_url = f"{BASE_URL}/logs/{logger.public_filename()}"
        reply = json.dumps({"answer": answer, "log_url": log_url})
        logger.log({"event": "reply", "reply": reply})
        send_message(chat_id, reply)

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    # Local dev only - Render runs this via gunicorn (see Procfile).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))