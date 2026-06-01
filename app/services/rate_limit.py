import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < window_start:
                hits.popleft()
            if len(hits) >= limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            hits.append(now)


rate_limiter = InMemoryRateLimiter()


def rate_limit(request: Request, scope: str, *, limit: int, window_seconds: int) -> None:
    client_host = request.client.host if request.client else "unknown"
    rate_limiter.check(f"{scope}:{client_host}", limit=limit, window_seconds=window_seconds)
