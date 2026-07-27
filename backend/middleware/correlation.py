"""Correlation-ID middleware with safe request logging."""
from __future__ import annotations
import logging
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger('talk2pay.request')


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = correlation_id
        logger.info('request_complete', extra={
            'correlation_id': correlation_id,
            'method': request.method,
            'path': request.url.path,
            'status_code': response.status_code,
        })
        return response
