"""Distributed limits for credential and recovery endpoints."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.middleware.rate_limiter import RateLimiter, get_client_ip
from backend.config import settings


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    WINDOWS = {
        "/auth/login": (12, 300),
        "/auth/signup": (5, 300),
        "/auth/register": (5, 300),
        "/auth/signup-code": (5, 300),
        "/auth/verify-code": (12, 300),
        "/auth/verify": (12, 300),
        "/auth/resend-code": (5, 300),
        "/auth/resend-verification": (5, 300),
        "/auth/password-reset/request": (5, 300),
        "/auth/password-reset/confirm": (5, 300),
        "/auth/password-reset/verify-identity": (5, 300),
        "/profile/password": (5, 300),
        "/admin/login": (5, 300),
    }

    def __init__(self, app):
        super().__init__(app)
        self.limiters = {
            settings.API_PREFIX + path: RateLimiter(requests_per_minute=limit, window_seconds=window, name=f"auth:{path}")
            for path, (limit, window) in self.WINDOWS.items()
        }

    async def dispatch(self, request: Request, call_next):
        limiter = self.limiters.get(request.url.path.rstrip("/")) if request.method in {"POST", "GET"} else None
        if limiter is not None:
            key = get_client_ip(request)
            if not limiter.is_allowed(key):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(limiter.window_seconds), "X-RateLimit-Limit": str(limiter.requests_per_minute), "X-RateLimit-Remaining": str(limiter.remaining(key))},
                )
        return await call_next(request)
