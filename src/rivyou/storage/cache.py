"""Small cache adapter used by the asynchronous crawler."""

from __future__ import annotations

from rivyou.storage.sqlite_store import CachedResponse, SQLiteStore


class SQLiteHTTPCache:
    def __init__(self, store: SQLiteStore, ttl_hours: float = 24.0):
        self.store = store
        self.ttl_hours = ttl_hours

    def get(self, url: str) -> CachedResponse | None:
        return self.store.cache_get(url, self.ttl_hours)

    def set(self, url: str, final_url: str, status_code: int, content_type: str, body: bytes, headers: dict[str, str]) -> None:
        self.store.cache_set(url, final_url, status_code, content_type, body, headers)
