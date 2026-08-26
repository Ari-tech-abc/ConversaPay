"""Named rate-limit profiles for security-sensitive endpoint groups."""
from backend.middleware.rate_limiter import RateLimiter

auth_rate_limiter = RateLimiter(requests_per_minute=12)
payment_rate_limiter = RateLimiter(requests_per_minute=20)
webhook_rate_limiter = RateLimiter(requests_per_minute=120)
