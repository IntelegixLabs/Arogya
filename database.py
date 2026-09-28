"""Arogya persistence layer.

Primary store: PostgreSQL (JSONB documents per collection) in database $DB_NAME (ArogyaDB).
Fallback: local JSON file (data/db.json) when Postgres is unreachable.
"""
import json
import os
import threading
import time
import random
import string
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("AROGYA_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_FILE = os.path.join(DATA_DIR, "db.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_NAME = os.environ.get("DB_NAME", "ArogyaDB").strip()

_LOCK = threading.RLock()
_CACHE = None
_PG = None          # live psycopg connection (or None -> file fallback)
_PG_TRIED = False

COLLECTIONS = ["patients", "consultations", "investigations", "reports", "biopsies",
               "referrals", "prescriptions", "advices", "followups", "users", "sessions", "meta"]

EMPTY = {
    "patients": [], "consultations": [], "investigations": [], "reports": [],
    "biopsies": [], "referrals": [], "prescriptions": [], "advices": [],
    "followups": [], "users": [], "sessions": [],
    "meta": {"seeded_at": None},
}


def uid(prefix: str = "") -> str:
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}{rnd}{int(time.time() * 1000) % 100000}"


# ---------------------------------------------------------------- postgres plumbing
def _url_for_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def _connect_pg():
    """Connect to $DB_NAME, creating the database if needed. Returns conn or None."""
    global _PG_TRIED
    _PG_TRIED = True
    if not DATABASE_URL:
        return None
    try:
        import psycopg
    except ImportError:
        print("[arogya-db] psycopg not installed - using local JSON file")
        return None
    try:
        # 1) ensure ArogyaDB exists (connect to maintenance db from the URL)
        with psycopg.connect(DATABASE_URL, connect_timeout=8, autocommit=True) as admin:
            exists = admin.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)
            ).fetchone()
            if not exists:
                admin.execute(f'CREATE DATABASE "{DB_NAME}"')
                print(f"[arogya-db] created database {DB_NAME}")
        # 2) connect to ArogyaDB and ensure the store table
        conn = psycopg.connect(_url_for_db(DATABASE_URL, DB_NAME), connect_timeout=8, autocommit=True)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS arogya_store (
                collection TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
        print(f"[arogya-db] connected to PostgreSQL / {DB_NAME}")
        return conn
    except Exception as e:
        print(f"[arogya-db] PostgreSQL unavailable ({e.__class__.__name__}: {e}) - using local JSON file")
        return None


def _pg_read_all(conn) -> dict:
    data = json.loads(json.dumps(EMPTY))
    for coll, doc in conn.execute("SELECT collection, data FROM arogya_store").fetchall():
        data[coll] = doc
    return data


def _pg_write_all(conn, data: dict) -> None:
    with conn.cursor() as cur:
        for coll in COLLECTIONS:
            cur.execute(
                """INSERT INTO arogya_store (collection, data, updated_at)
                   VALUES (%s, %s::jsonb, now())
                   ON CONFLICT (collection)
                   DO UPDATE SET data = EXCLUDED.data, updated_at = now()""",
                (coll, json.dumps(data.get(coll, EMPTY.get(coll)), default=str)),
            )


# ---------------------------------------------------------------- file fallback
def _file_read() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return json.loads(json.dumps(EMPTY))


def _file_write(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)
    os.replace(tmp, DB_FILE)


# ---------------------------------------------------------------- public API
def backend_name() -> str:
    return f"postgresql/{DB_NAME}" if _PG else "json-file"


def load() -> dict:
    global _CACHE, _PG
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        if not _PG_TRIED:
            _PG = _connect_pg()
        if _PG:
            try:
                _CACHE = _pg_read_all(_PG)
            except Exception as e:
                print(f"[arogya-db] read failed ({e}) - falling back to file")
                _PG = None
                _CACHE = _file_read()
        else:
            _CACHE = _file_read()
        for key, val in EMPTY.items():
            _CACHE.setdefault(key, json.loads(json.dumps(val)))
        return _CACHE


def save() -> None:
    global _PG
    with _LOCK:
        if _CACHE is None:
            return
        if _PG:
            try:
                _pg_write_all(_PG, _CACHE)
                return
            except Exception as e:
                print(f"[arogya-db] write failed ({e}) - falling back to file")
                _PG = None
        _file_write(_CACHE)


def reset(new_data: dict) -> None:
    global _CACHE
    with _LOCK:
        _CACHE = new_data
        for key, val in EMPTY.items():
            _CACHE.setdefault(key, json.loads(json.dumps(val)))
        save()
