"""Correlation-ID helpers for request and integration tracing."""
from __future__ import annotations
import json
import logging
from contextvars import ContextVar
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def get_correlation_id() -> str:
    return correlation_id.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")
        value = (incoming or str(uuid4()))[:128]
        token = correlation_id.set(value)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = value
            return response
        finally:
            correlation_id.reset(token)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        return json.dumps(payload, ensure_ascii=False)
