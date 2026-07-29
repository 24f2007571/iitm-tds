"""Minimal Telegram Bot API client using plain requests - works fine in a sync
Flask/gunicorn webhook handler, no asyncio needed."""

import os

import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API_BASE = f"https://api.telegram.org/bot{TOKEN}"


def send_message(chat_id, text):
    resp = requests.post(f"{API_BASE}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def set_webhook(url):
    resp = requests.post(f"{API_BASE}/setWebhook", json={"url": url}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def delete_webhook():
    resp = requests.post(f"{API_BASE}/deleteWebhook", timeout=30)
    return resp.json()


def get_webhook_info():
    resp = requests.get(f"{API_BASE}/getWebhookInfo", timeout=30)
    return resp.json()