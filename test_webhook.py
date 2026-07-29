import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.environ["TELEGRAM_BOT_TOKEN"]
url = f"http://localhost:5000/webhook/{token}"

body = {
    "update_id": 1,
    "message": {
        "chat": {"id": 12345},
        "text": 'What is 2 + 2? Reply with ONLY this JSON object and nothing else: {"answer": <number>, "log_url": "<url>"}',
    },
}

resp = requests.post(url, json=body, timeout=10)
print("Status:", resp.status_code)
print("Response:", resp.text)