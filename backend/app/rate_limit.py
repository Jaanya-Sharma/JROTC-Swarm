"""Small in-memory sliding-window rate limiter for direct client IPs."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class PerIpRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, ip_address: str) -> bool:
        now = time.monotonic()
        with self._lock:
            requests = self._requests[ip_address]
            while requests and requests[0] <= now - self.window_seconds:
                requests.popleft()
            if len(requests) >= self.max_requests:
                return False
            requests.append(now)
            return True
