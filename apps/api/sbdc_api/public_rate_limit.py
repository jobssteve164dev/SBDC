import hashlib
import threading
import time


class PublicRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        safe_key = hashlib.sha256(key.encode()).hexdigest()
        with self._lock:
            recent = [value for value in self._attempts.get(safe_key, []) if value > cutoff]
            if len(recent) >= limit:
                self._attempts[safe_key] = recent
                return False
            recent.append(now)
            self._attempts[safe_key] = recent
            return True


public_rate_limiter = PublicRateLimiter()
