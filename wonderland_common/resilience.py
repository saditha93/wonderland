from threading import Lock
from time import monotonic
from fastapi import HTTPException


class CircuitBreaker:
    """Per-process breaker: bounded calls, cooldown, one half-open probe."""

    def __init__(self, threshold=3, cooldown=30, clock=monotonic):
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.failures = 0
        self.opened_at = None
        self.probing = False
        self.lock = Lock()

    def call(self, operation):
        with self.lock:
            if self.opened_at is not None:
                if self.clock() - self.opened_at < self.cooldown or self.probing:
                    raise HTTPException(
                        503, "Payment provider cooling down; booking remains pending"
                    )
                self.probing = True
        try:
            result = operation()
        except Exception:
            with self.lock:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = self.clock()
                self.probing = False
            raise
        with self.lock:
            self.failures = 0
            self.opened_at = None
            self.probing = False
        return result
