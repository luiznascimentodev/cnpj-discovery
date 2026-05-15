from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    ok: bool
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self, redis, *, bucket_key: str, window: int, max_count: int):
        if window <= 0:
            raise ValueError("window must be positive")
        if max_count <= 0:
            raise ValueError("max_count must be positive")
        self._redis = redis
        self._bucket_key = bucket_key
        self._window = window
        self._max_count = max_count

    async def try_acquire(self) -> RateLimitResult:
        if self._redis is None:
            return RateLimitResult(ok=True, remaining=self._max_count - 1, retry_after=0)

        count = await self._redis.incr(self._bucket_key)
        if count == 1:
            await self._redis.expire(self._bucket_key, self._window)

        ttl = await self._redis.ttl(self._bucket_key)
        retry_after = ttl if ttl and ttl > 0 else self._window
        remaining = max(self._max_count - count, 0)
        return RateLimitResult(
            ok=count <= self._max_count,
            remaining=remaining,
            retry_after=0 if count <= self._max_count else retry_after,
        )
