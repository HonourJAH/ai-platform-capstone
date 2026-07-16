import fakeredis
import pytest

from app.config import settings
from app.services.rate_limit import RateLimiter


@pytest.fixture
def limiter():
    return RateLimiter(fakeredis.FakeRedis(decode_responses=True))


def test_allows_requests_within_capacity(limiter):
    for _ in range(settings.rate_limit_tiers["free"]["capacity"]):
        allowed, _, _ = limiter.check(user_id=1, tier="free")
        assert allowed is True


def test_rejects_requests_beyond_capacity(limiter):
    capacity = settings.rate_limit_tiers["free"]["capacity"]
    for _ in range(capacity):
        limiter.check(user_id=2, tier="free")

    allowed, tokens_remaining, retry_after = limiter.check(user_id=2, tier="free")
    assert allowed is False
    assert tokens_remaining == 0
    assert retry_after >= 0


def test_buckets_are_independent_per_user(limiter):
    capacity = settings.rate_limit_tiers["free"]["capacity"]
    for _ in range(capacity):
        limiter.check(user_id=3, tier="free")

    allowed, _, _ = limiter.check(user_id=4, tier="free")
    assert allowed is True


def test_pro_tier_has_higher_capacity_than_free(limiter):
    free_capacity = settings.rate_limit_tiers["free"]["capacity"]
    pro_capacity = settings.rate_limit_tiers["pro"]["capacity"]
    assert pro_capacity > free_capacity

    for _ in range(free_capacity):
        limiter.check(user_id=5, tier="pro")

    allowed, _, _ = limiter.check(user_id=5, tier="pro")
    assert allowed is True
