"""
Simple in-memory rate limiter for public API endpoints.
Limits requests per IP address to prevent abuse.
"""
import time
import logging
from collections import defaultdict
from fastapi import Request, HTTPException
from typing import Dict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple memory-based rate limiter using token bucket algorithm.
    Limits requests per IP address.
    """
    
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        # Store request timestamps per IP: {ip: [timestamp1, timestamp2, ...]}
        self.requests: Dict[str, list] = defaultdict(list)
        # Clean up old entries periodically
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
    
    def _cleanup_old_requests(self):
        """Remove request timestamps older than 1 minute."""
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            for ip in list(self.requests.keys()):
                # Keep only requests from the last minute
                self.requests[ip] = [
                    ts for ts in self.requests[ip] 
                    if now - ts < 60
                ]
                # Remove empty entries
                if not self.requests[ip]:
                    del self.requests[ip]
            self.last_cleanup = now
    
    def is_allowed(self, ip: str) -> bool:
        """Check if request from IP is allowed."""
        now = time.time()
        
        # Clean up old entries periodically
        self._cleanup_old_requests()
        
        # Remove requests older than 1 minute for this IP
        self.requests[ip] = [
            ts for ts in self.requests[ip] 
            if now - ts < 60
        ]
        
        # Check if under limit
        if len(self.requests[ip]) >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for IP: {ip}")
            return False
        
        # Add current request timestamp
        self.requests[ip].append(now)
        return True
    
    def get_remaining_requests(self, ip: str) -> int:
        """Get remaining requests for IP."""
        now = time.time()
        self._cleanup_old_requests()
        
        # Remove requests older than 1 minute for this IP
        self.requests[ip] = [
            ts for ts in self.requests[ip] 
            if now - ts < 60
        ]
        
        return max(0, self.requests_per_minute - len(self.requests[ip]))


# Global rate limiter instance for chat endpoint
chat_rate_limiter = RateLimiter(requests_per_minute=10)


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request headers.
    Handles proxies and load balancers.
    """
    # Check for forwarded headers (proxies, load balancers)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fall back to direct connection IP
    if request.client:
        return request.client.host
    
    return "unknown"


def check_rate_limit(request: Request, limiter: RateLimiter = chat_rate_limiter):
    """
    Dependency to check rate limit for an endpoint.
    Raises HTTPException if rate limit is exceeded.
    """
    ip = get_client_ip(request)
    
    if not limiter.is_allowed(ip):
        remaining = limiter.get_remaining_requests(ip)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Please try again later.",
                "remaining_requests": remaining,
                "limit": limiter.requests_per_minute
            },
            headers={
                "X-RateLimit-Limit": str(limiter.requests_per_minute),
                "X-RateLimit-Remaining": str(remaining),
                "Retry-After": "60"
            }
        )
    
    return True
