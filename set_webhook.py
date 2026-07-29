"""
Run this once after your Render service is live, to point Telegram at it.

Usage:
    python set_webhook.py https://your-app.onrender.com
(or just `python set_webhook.py` if PUBLIC_BASE_URL / RENDER_EXTERNAL_URL is set)
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from telegram_api import get_webhook_info, set_webhook

if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else (
        os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    )
    if not base_url:
        raise SystemExit("Usage: python set_webhook.py https://your-app.onrender.com")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"{base_url.rstrip('/')}/webhook/{token}"
    print("Setting webhook to:", url)
    print(set_webhook(url))
    print("Current webhook info:", get_webhook_info())