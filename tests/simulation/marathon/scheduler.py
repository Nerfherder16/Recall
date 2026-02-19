"""
RateLimitScheduler — Token-bucket rate limiter for API endpoint classes.

Each bucket refills at a configured rate. Personas call
`await scheduler.acquire("search")` before each API call.
Auto back-off on 429 responses.
"""

import asyncio
import time


class TokenBucket:
    """Simple token-bucket rate limiter."""

    def __init__(self, rate_per_minute: int):
        self.rate = rate_per_minute
        self.interval = 60.0 / rate_per_minute if rate_per_minute > 0 else 0
        self.tokens = float(rate_per_minute)
        self.max_tokens = float(rate_per_minute)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * (self.rate / 60.0))
        self.last_refill = now

    async def acquire(self):
        """Wait until a token is available, then consume it."""
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            # Wait a fraction of the interval before retrying
            await asyncio.sleep(self.interval * 0.5)


# Bucket configs: name -> usable budget per minute (with headroom from API limits)
DEFAULT_BUDGETS = {
    "default": 50,   # store/get/pin/feedback — API limit 60/min
    "search": 25,    # browse/query/timeline — API limit 30/min
    "ingest": 16,    # turns/signals — API limit 20/min
    "admin": 8,      # decay/consolidate/retrain — API limit 10/min
}


class RateLimitScheduler:
    """Manages token buckets for different API endpoint classes."""

    def __init__(self, budgets: dict[str, int] | None = None):
        self._budgets = budgets or DEFAULT_BUDGETS
        self._buckets: dict[str, TokenBucket] = {
            name: TokenBucket(rate) for name, rate in self._budgets.items()
        }
        self.total_waits: int = 0
        self._backoff_until: float = 0.0
        self._backoff_lock = asyncio.Lock()

    async def acquire(self, bucket_name: str = "default"):
        """Acquire a token from the named bucket. Blocks until available."""
        # Check global backoff (from 429 responses)
        async with self._backoff_lock:
            now = time.monotonic()
            if now < self._backoff_until:
                wait = self._backoff_until - now
                self.total_waits += 1
                await asyncio.sleep(wait)

        bucket = self._buckets.get(bucket_name)
        if bucket is None:
            bucket = self._buckets["default"]
        await bucket.acquire()

    async def report_429(self):
        """Called when a 429 response is received. Applies global backoff."""
        async with self._backoff_lock:
            self._backoff_until = time.monotonic() + 15.0  # 15s global pause
            self.total_waits += 1
