import time

import redis

from app.config import settings

_TOKEN_BUCKET_SCRIPT = """
local bucket_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call('HMGET', bucket_key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = now - last_refill
if elapsed >= window then
    local windows_passed = math.floor(elapsed / window)
    tokens = math.min(capacity, tokens + (windows_passed * refill))
    last_refill = last_refill + (windows_passed * window)
end

local allowed = 0
if tokens > 0 then
    allowed = 1
    tokens = tokens - 1
end

redis.call('HMSET', bucket_key, 'tokens', tokens, 'last_refill', last_refill)
redis.call('EXPIRE', bucket_key, window * 2)

local retry_after = window - (now - last_refill)
if retry_after < 0 then retry_after = 0 end

return {allowed, tokens, retry_after}
"""


class RateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._script = self.redis.register_script(_TOKEN_BUCKET_SCRIPT)

    def check(self, user_id: int, tier: str) -> tuple[bool, int, float]:
        tier_config = settings.rate_limit_tiers.get(
            tier, settings.rate_limit_tiers["free"]
        )
        bucket_key = f"ratelimit:{user_id}"

        allowed, tokens_remaining, retry_after = self._script(
            keys=[bucket_key],
            args=[
                tier_config["capacity"],
                tier_config["refill"],
                tier_config["window_seconds"],
                time.time(),
            ],
        )
        return bool(allowed), int(tokens_remaining), float(retry_after)


def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)
