from backend.middleware.rate_limiter import RateLimiter


def test_rate_limiter_enforces_window_limit():
    limiter = RateLimiter(requests_per_minute=2)
    assert limiter.is_allowed("203.0.113.10")
    assert limiter.is_allowed("203.0.113.10")
    assert not limiter.is_allowed("203.0.113.10")
    assert limiter.is_allowed("203.0.113.11")
