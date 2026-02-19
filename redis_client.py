"""Redis helper utilities for sessions/rate-limit/cache migration."""
from __future__ import annotations

import json
import os
import time

try:
    import redis
except Exception:  # pragma: no cover - optional during migration
    redis = None


class RedisClient:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client = None
        if redis is not None:
            try:
                self._client = redis.Redis.from_url(self.url, decode_responses=True)
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def ping(self) -> bool:
        if not self.enabled:
            return False
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def set_json(self, key: str, value, ttl_seconds: int = 0) -> bool:
        if not self.enabled:
            return False
        try:
            payload = json.dumps(value)
            if ttl_seconds > 0:
                self._client.setex(key, ttl_seconds, payload)
            else:
                self._client.set(key, payload)
            return True
        except Exception:
            return False

    def get_json(self, key: str):
        if not self.enabled:
            return None
        try:
            raw = self._client.get(key)
        except Exception:
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set_text(self, key: str, value: str, ttl_seconds: int = 0) -> bool:
        if not self.enabled:
            return False
        try:
            payload = str(value or "")
            if ttl_seconds > 0:
                self._client.setex(key, ttl_seconds, payload)
            else:
                self._client.set(key, payload)
            return True
        except Exception:
            return False

    def get_text(self, key: str) -> str | None:
        if not self.enabled:
            return None
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return str(raw)
        except Exception:
            return None

    def delete(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            self._client.delete(key)
            return True
        except Exception:
            return False

    def delete_many(self, keys: list[str]) -> int:
        if not self.enabled or not keys:
            return 0
        try:
            return int(self._client.delete(*keys))
        except Exception:
            return 0

    def delete_by_prefix(self, prefix: str, batch_size: int = 500) -> int:
        if not self.enabled:
            return 0
        removed = 0
        chunk = []
        try:
            for key in self._client.scan_iter(match=f"{prefix}*"):
                chunk.append(key)
                if len(chunk) >= max(1, int(batch_size)):
                    removed += int(self._client.delete(*chunk))
                    chunk = []
            if chunk:
                removed += int(self._client.delete(*chunk))
        except Exception:
            return removed
        return removed

    def rate_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        if not self.enabled:
            return True, 0
        try:
            bucket = f"rl:{key}:{int(time.time() // max(1, window_seconds))}"
            count = self._client.incr(bucket)
            if count == 1:
                self._client.expire(bucket, max(1, window_seconds))
            if count > limit:
                ttl = self._client.ttl(bucket)
                return False, max(1, int(ttl if ttl and ttl > 0 else window_seconds))
            return True, 0
        except Exception:
            return True, 0

