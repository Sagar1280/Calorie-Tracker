import time
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException


@dataclass
class _Window:
    started_at: float
    count: int
    window_seconds: int


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    def _prune(self, now: float) -> None:
        if len(self._windows) < 10_000:
            return
        self._windows = {
            key: window
            for key, window in self._windows.items()
            if now - window.started_at < window.window_seconds
        }

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            window = self._windows.get(key)
            if window is None or now - window.started_at >= window_seconds:
                self._windows[key] = _Window(
                    started_at=now,
                    count=1,
                    window_seconds=window_seconds,
                )
                return True, 0
            if window.count >= limit:
                retry_after = max(1, int(window_seconds - (now - window.started_at)))
                return False, retry_after
            window.count += 1
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


limiter = FixedWindowLimiter()


def reset_rate_limits() -> None:
    limiter.reset()


def enforce_rate_limit(
    namespace: str,
    key: str | int,
    limit: int,
    window_seconds: int,
    message: str = "Too many requests. Please wait a moment and try again.",
) -> None:
    allowed, retry_after = limiter.allow(
        f"{namespace}:{key}", limit, window_seconds
    )
    if allowed:
        return
    raise HTTPException(
        status_code=429,
        detail={
            "code": "rate_limited",
            "message": message,
        },
        headers={"Retry-After": str(retry_after)},
    )
