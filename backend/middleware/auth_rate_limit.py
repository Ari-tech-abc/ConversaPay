"""Dedicated in-process limits for credential and recovery endpoints."""
from __future__ import annotations
import time
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.middleware.rate_limiter import get_client_ip


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    WINDOWS = {
        "/api/v1/auth/password-reset/request": (5, 300),
        "/api/v1/auth/password-reset/verify-identity": (5, 300),
        "/api/v1/admin/login": (5, 300),
    }

    def __init__(self, app):
        super().__init__(app)
        self.hits = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "GET"} and request.url.path in self.WINDOWS:
            limit, window = self.WINDOWS[request.url.path]
            key = f"{request.url.path}:{get_client_ip(request)}"
            now = time.monotonic()
            recent = [stamp for stamp in self.hits[key] if stamp > now - window]
            if len(recent) >= limit:
                return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."}, headers={"Retry-After": str(window)})
            recent.append(now)
            self.hits[key] = recent
        return await call_next(request)
