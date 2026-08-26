"""Distributed rate limiting with Redis/Upstash and a safe local fallback."""
from __future__ import annotations

import ipaddress
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import HTTPException, Request

from backend.config import settings

logger = logging.getLogger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover, requirements installs redis-py
    redis = None

_TRUSTED_PROXY_CIDRS: List[ipaddress.IPv4Network] = [
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
]


def _is_trusted_proxy(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _TRUSTED_PROXY_CIDRS)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    if _is_trusted_proxy(direct_ip):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            candidate = forwarded_for.split(",")[0].strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            try:
                ipaddress.ip_address(real_ip)
                return real_ip
            except ValueError:
                pass
    return direct_ip


class RateLimiter:
    """Sliding-window limiter using Redis when REDIS_URL is configured.

    Redis failures fail open to the same process-local limiter rather than
    taking authentication or recovery endpoints down. The local fallback is
    intentionally retained for development and test environments.
    """

    _REDIS_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
        redis.call('EXPIRE', key, window)
        return {0, count}
    end
    redis.call('ZADD', key, now, ARGV[4])
    redis.call('EXPIRE', key, window)
    return {1, count + 1}
    """

    def __init__(self, requests_per_minute: int = 10, window_seconds: int = 60, name: str = "default"):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.name = name
        self.requests: Dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300
        self._redis: Optional[object] = None
        self._redis_script = None
        if settings.REDIS_URL and redis is not None:
            try:
                self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
                self._redis.ping()
                self._redis_script = self._redis.register_script(self._REDIS_SCRIPT)
                logger.info("Redis rate limiting enabled for %s", name)
            except Exception as exc:
                logger.warning("Redis unavailable for %s, using in-memory fallback: %s", name, exc)
                self._redis = None

    def _cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            cutoff = now - self.window_seconds
            for ip in list(self.requests):
                self.requests[ip] = [ts for ts in self.requests[ip] if ts > cutoff]
                if not self.requests[ip]:
                    del self.requests[ip]
            self._last_cleanup = now

    def _memory_allowed(self, key: str) -> tuple[bool, int]:
        now = time.time()
        self._cleanup()
        cutoff = now - self.window_seconds
        self.requests[key] = [ts for ts in self.requests[key] if ts > cutoff]
        if len(self.requests[key]) >= self.requests_per_minute:
            return False, len(self.requests[key])
        self.requests[key].append(now)
        return True, len(self.requests[key])

    def _redis_allowed(self, key: str) -> tuple[bool, int]:
        now = time.time()
        member = f"{now}:{time.time_ns()}"
        result = self._redis_script(keys=[f"conversapay:ratelimit:{self.name}:{key}"], args=[now, self.window_seconds, self.requests_per_minute, member])
        return bool(int(result[0])), int(result[1])

    def is_allowed(self, key: str) -> bool:
        try:
            if self._redis_script is not None:
                allowed, _ = self._redis_allowed(key)
                if not allowed:
                    logger.warning("Rate limit exceeded for %s", key)
                return allowed
        except Exception as exc:
            logger.warning("Redis rate-limit operation failed for %s, falling back locally: %s", self.name, exc)
            self._redis = None
            self._redis_script = None
        allowed, _ = self._memory_allowed(key)
        if not allowed:
            logger.warning("Rate limit exceeded for %s", key)
        return allowed

    def remaining(self, key: str) -> int:
        try:
            if self._redis is not None:
                redis_key = f"conversapay:ratelimit:{self.name}:{key}"
                count = int(self._redis.zcount(redis_key, time.time() - self.window_seconds, "+inf"))
                return max(0, self.requests_per_minute - count)
        except Exception:
            pass
        now = time.time()
        cutoff = now - self.window_seconds
        recent = [ts for ts in self.requests.get(key, []) if ts > cutoff]
        return max(0, self.requests_per_minute - len(recent))


# Chat hits the Gemini API (real $$ per request) — keep this the strictest.
chat_rate_limiter = RateLimiter(requests_per_minute=10, name="chat")

# Free-plan session cap: 5 messages per hour per session_id.
free_chat_session_limiter = RateLimiter(requests_per_minute=5, window_seconds=3600, name="free_chat_session")

# Widget config is cheap to serve but was previously *unlimited*, making it
# a free enumeration/scraping target. 30/min/key is generous for a normal
# page load (one widget load = one config fetch) but stops scripted abuse.
widget_config_rate_limiter = RateLimiter(requests_per_minute=30, name="widget_config")


def check_rate_limit(request: Request, limiter: RateLimiter = chat_rate_limiter, extra_key: str | None = None) -> bool:
    """Check + enforce a rate limit for this request.

    `extra_key` lets callers scope the limit to something beyond raw IP —
    e.g. business_id, so one noisy business can't exhaust the quota shared
    by every other tenant behind the same NAT/IP.
    """
    key = get_client_ip(request)
    if extra_key:
        key = f"{key}:{extra_key}"
    if not limiter.is_allowed(key):
        rem = limiter.remaining(key)
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded", "message": "Too many requests. Please try again later.", "remaining_requests": rem, "limit": limiter.requests_per_minute},
            headers={"X-RateLimit-Limit": str(limiter.requests_per_minute), "X-RateLimit-Remaining": str(rem), "Retry-After": str(limiter.window_seconds)},
        )
    return True