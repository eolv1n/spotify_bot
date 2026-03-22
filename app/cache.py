import json
import os
import sqlite3
import time
from contextlib import closing

from app.config import CACHE_DB_PATH, CACHE_TTL_SECONDS


def init_cache_db():
    cache_dir = os.path.dirname(CACHE_DB_PATH)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def get_cached_track(url: str):
    now = int(time.time())
    with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
        row = conn.execute(
            "SELECT payload_json, expires_at FROM url_cache WHERE url = ?",
            (url,),
        ).fetchone()

        if not row:
            return None

        payload_json, expires_at = row
        if expires_at <= now:
            conn.execute("DELETE FROM url_cache WHERE url = ?", (url,))
            conn.commit()
            return None

    try:
        return json.loads(payload_json)
    except json.JSONDecodeError:
        return None


def set_cached_track(url: str, payload: dict):
    expires_at = int(time.time()) + CACHE_TTL_SECONDS
    with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
        conn.execute(
            """
            INSERT INTO url_cache (url, payload_json, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                payload_json = excluded.payload_json,
                expires_at = excluded.expires_at
            """,
            (url, json.dumps(payload, ensure_ascii=False), expires_at),
        )
        conn.commit()
