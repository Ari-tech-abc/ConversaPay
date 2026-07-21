"""
Rate limiter middleware for public API endpoints.

SECURITY FIXES:
  C5 - X-Forwarded-For is only trusted when the direct connection comes from
       a known trusted proxy CIDR range.  Clients can no longer spoof their IP
       by injecting arbitrary X-Forwarded-For headers.
  M8 - In-memory store is documented as single-process only.  For multi-worker
       deployments replace RateLimiter with a Redis-backed implementation
       (e.g. slowapi + redis).
"""
import ipaddress
import time
import logging
from collections import defaultdict
from typing import Dict, List

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trusted proxy CIDRs — only connections from these addresses may set
# X-Forwarded-For / X-Real-IP headers.
# Adjust to match your actual load-balancer / reverse-proxy IP ranges.
# ---------------------------------------------------------------------------
_TRUSTED_PROXY_CIDRS: List[ipaddress.IPv4Network] = [
    ipaddress.IPv4Network("127.0.0.0/8"),    # loopback (local dev)
    ipaddress.IPv4Network("10.0.0.0/8"),     # RFC-1918 private
    ipaddress.IPv4Network("172.16.0.0/12"),  # RFC-1918 private
    ipaddress.IPv4Network("192.168.0.0/16"), # RFC-1918 private
]


def _is_trusted_proxy(ip: str) -> bool:
    """Return True if *ip* belongs to a trusted proxy CIDR."""
    try:
        addr = ipaddress.IPv4Address(ip)
        return any(addr in net for net in _TRUSTED_PROXY_CIDRS)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from the request.

    FIX C5: X-Forwarded-For / X-Real-IP are only honoured when the TCP
    connection originates from a trusted proxy.  Otherwise the direct
    connection IP is used, preventing header-injection spoofing.
    """
    direct_ip = request.client.host if request.client else "unknown"

    if _is_trusted_proxy(direct_ip):
        # Trust the leftmost (client-supplied) entry in X-Forwarded-For.
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            candidate = forwarded_for.split(",")[0].strip()
            try:
                ipaddress.ip_address(candidate)   # validate it is a real IP
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
    """
    Simple in-process sliding-window rate limiter.

    NOTE (M8): This store is per-process.  Under Gunicorn with multiple
    workers each worker maintains its own counter, so the effective limit
    is (requests_per_minute * num_workers).  Replace with a Redis-backed
    implementation (e.g. slowapi) for accurate multi-worker rate limiting.
    """

    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, list] = defaultdict(list)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # seconds

    def _cleanup(self):
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            cutoff = now - 60
            for ip in list(self.requests.keys()):
                self.requests[ip] = [ts for ts in self.requests[ip] if ts > cutoff]
                if not self.requests[ip]:
                    del self.requests[ip]
            self._last_cleanup = now

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self._cleanup()
        cutoff = now - 60
        self.requests[ip] = [ts for ts in self.requests[ip] if ts > cutoff]
        if len(self.requests[ip]) >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for IP: {ip}")
            return False
        self.requests[ip].append(now)
        return True

    def remaining(self, ip: str) -> int:
        now = time.time()
        cutoff = now - 60
        recent = [ts for ts in self.requests.get(ip, []) if ts > cutoff]
        return max(0, self.requests_per_minute - len(recent))


# Global instance for the chat endpoint
chat_rate_limiter = RateLimiter(requests_per_minute=10)


def check_rate_limit(request: Request, limiter: RateLimiter = chat_rate_limiter):
    """FastAPI dependency: raises 429 when the rate limit is exceeded."""
    ip = get_client_ip(request)
    if not limiter.is_allowed(ip):
        rem = limiter.remaining(ip)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please try again later.",
                "remaining_requests": rem,
                "limit": limiter.requests_per_minute,
            },
            headers={
                "X-RateLimit-Limit": str(limiter.requests_per_minute),
                "X-RateLimit-Remaining": str(rem),
                "Retry-After": "60",
            },
        )
    return True
