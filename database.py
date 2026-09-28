"""Arogya - lightweight JSON-file persistence layer (zero external deps)."""
import json
import os
import threading
import time
import random
import string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("AROGYA_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_FILE = os.path.join(DATA_DIR, "db.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

_LOCK = threading.RLock()
_CACHE = None

EMPTY = {
    "patients": [],
    "consultations": [],
    "investigations": [],
    "reports": [],
    "biopsies": [],
    "referrals": [],
    "prescriptions": [],
    "advices": [],
    "followups": [],
    "meta": {"seeded_at": None},
}


def uid(prefix: str = "") -> str:
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}{rnd}{int(time.time() * 1000) % 100000}"


def load() -> dict:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    _CACHE = json.load(f)
            except Exception:
                _CACHE = json.loads(json.dumps(EMPTY))
        else:
            _CACHE = json.loads(json.dumps(EMPTY))
        for key, val in EMPTY.items():
            _CACHE.setdefault(key, json.loads(json.dumps(val)))
        return _CACHE


def save() -> None:
    with _LOCK:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, indent=1, default=str)
        os.replace(tmp, DB_FILE)


def reset(new_data: dict) -> None:
    global _CACHE
    with _LOCK:
        _CACHE = new_data
        save()
