"""JSONL run logger - one file per chat, written under LOG_DIR."""

import json
import os
import threading
import time

LOG_DIR = os.environ.get("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_lock = threading.Lock()


class RunLogger:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.filename = f"chat_{chat_id}.jsonl"
        self.path = os.path.join(LOG_DIR, self.filename)

    def log(self, entry: dict):
        entry = {"ts": time.time(), "chat_id": self.chat_id, **entry}
        line = json.dumps(entry, default=str)
        with _lock:
            with open(self.path, "a") as f:
                f.write(line + "\n")

    def public_filename(self):
        return self.filename