"""Test-only fault injection: make the following API requests slow or failing.

Set it with POST /_admin/faults. The settings stay until you change them, call
POST /_admin/reset, or restart the server. The admin endpoints themselves are never
slowed down or failed, so you can always switch faults off again.
"""
import threading
import time

from errors import ServiceError


class FaultInjector:
    def __init__(self):
        self.lock = threading.Lock()
        self.clear()

    def clear(self):
        self.configure(None, 0.0, 0)

    def configure(self, status, rate, latency_ms):
        with self.lock:
            self.status = status                      # 429, 503 or None
            self.rate = rate                          # 0.0 to 1.0: the share of requests that fail
            self.latency_ms = latency_ms              # added to every request
            self.rate_per_1000 = round(rate * 1000)   # whole numbers keep the counting exact
            self.credit = 0

    def settings(self):
        return {"status": self.status, "rate": self.rate, "latency_ms": self.latency_ms}

    def apply(self):
        """Called at the start of every API request. Sleeps, then maybe raises."""
        fail_now = False
        with self.lock:
            latency_ms = self.latency_ms
            status = self.status
            # Deterministic, not random: rate 0.5 fails every 2nd request, 0.25 every 4th, 1.0 all.
            if status is not None and self.rate_per_1000 > 0:
                self.credit = self.credit + self.rate_per_1000
                if self.credit >= 1000:
                    self.credit = self.credit - 1000
                    fail_now = True

        if latency_ms > 0:
            time.sleep(latency_ms / 1000)

        if fail_now and status == 429:
            raise ServiceError(429, "rate_limited",
                               "Too many requests (injected by POST /_admin/faults)",
                               "Wait for the number of seconds in the Retry-After header, then retry",
                               headers={"Retry-After": "1"})
        if fail_now and status == 503:
            raise ServiceError(503, "unavailable",
                               "Service temporarily unavailable (injected by POST /_admin/faults)",
                               "Retry after a short wait; give up after a few attempts",
                               headers={"Retry-After": "1"})


FAULTS = FaultInjector()
