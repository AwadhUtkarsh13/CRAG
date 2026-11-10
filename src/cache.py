"""Persistent response cache for paid API calls (OpenAI, Tavily).

Repeating the same prompt or search returns the stored result instead of
spending credits again. Values are plain text or JSON, so cached entries never
depend on SDK object pickling. Thread-safe, so concurrent graph runs and
``batch`` calls can share it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from functools import lru_cache
from pathlib import Path

from config.settings import get_settings


def make_key(namespace: str, *parts: str) -> str:
    """Stable SHA-256 key over a namespace and the request parts."""
    digest = hashlib.sha256(json.dumps([namespace, *parts], ensure_ascii=False).encode("utf-8"))
    return f"{namespace}:{digest.hexdigest()}"


class ResponseCache:
    """Minimal SQLite key/value store with optional per-read max age."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL)"
        )
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, max_age_s: float | None = None) -> str | None:
        """Return the stored value, or ``None`` if absent or older than ``max_age_s``."""
        with self._lock:
            row = self._conn.execute("SELECT value, created FROM cache WHERE key = ?", (key,)).fetchone()
            if row is None or (max_age_s is not None and time.time() - row[1] > max_age_s):
                self.misses += 1
                return None
            self.hits += 1
            return row[0]

    def set(self, key: str, value: str) -> None:
        """Insert or replace a value."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created) VALUES (?, ?, ?)",
                (key, value, time.time()),
            )
            self._conn.commit()

    def clear(self) -> int:
        """Delete every entry. Returns the number removed."""
        with self._lock:
            n = self._conn.execute("DELETE FROM cache").rowcount
            self._conn.commit()
            return n


@lru_cache(maxsize=1)
def get_cache() -> ResponseCache | None:
    """Shared cache, or ``None`` when ``CACHE_ENABLED=false``."""
    settings = get_settings()
    return ResponseCache(settings.cache_path) if settings.cache_enabled else None
