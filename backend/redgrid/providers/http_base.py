from __future__ import annotations

import time

import requests


class HttpProviderBase:
    """Health check cached for 30 s; requests time out after provider_timeout_s."""

    def __init__(self, base_url: str, timeout_s: float, health_timeout_s: float = 5.0, health_cache_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.health_timeout_s = health_timeout_s
        self.health_cache_s = health_cache_s
        self._ready_at = 0.0
        self._ready = False
        self._health: dict = {}

    def is_ready(self) -> bool:
        if not self.base_url:
            return False
        now = time.monotonic()
        if now - self._ready_at < self.health_cache_s:
            return self._ready
        try:
            r = requests.get(f"{self.base_url}/v1/health", timeout=self.health_timeout_s)
            self._health = r.json() if r.ok else {}
            self._ready = r.ok and self._health.get("status") == "READY"
        except Exception:
            self._ready = False
        self._ready_at = now
        return self._ready

    def _post(self, path: str, body: dict) -> dict:
        r = requests.post(f"{self.base_url}{path}", json=body, timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()

    def _get(self, path: str) -> dict:
        r = requests.get(f"{self.base_url}{path}", timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()
