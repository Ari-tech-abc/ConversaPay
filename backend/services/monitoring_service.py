"""
Monitoring and logging service for ConversaPay.
Integrates with Sentry for error tracking and provides centralized logging.
"""
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from backend.config import settings

# Optional Sentry SDK - only used if installed
try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    sentry_sdk = None
    SENTRY_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.info("ℹ️  sentry-sdk not installed - Sentry monitoring disabled")

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service for monitoring, logging, and error tracking."""

    @staticmethod
    def initialize():
        """Initialize monitoring services (Sentry, etc.)."""
        try:
            if settings.SENTRY_DSN:
                if SENTRY_AVAILABLE:
                    sentry_sdk.init(
                        dsn=settings.SENTRY_DSN,
                        environment=settings.ENVIRONMENT,
                        traces_sample_rate=1.0 if settings.is_development else 0.1,
                        profiles_sample_rate=1.0 if settings.is_development else 0.1,
                        send_default_pii=False,
                        attach_stacktrace=True,
                    )
                    logger.info("✅ Sentry monitoring initialized")
                else:
                    logger.warning("⚠️  SENTRY_DSN configured but sentry-sdk not installed - skipping")
            else:
                logger.info("ℹ️  Sentry DSN not configured - monitoring disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {str(e)}")

    @staticmethod
    def capture_exception(
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None
    ):
        """Capture an exception with context."""
        if not SENTRY_AVAILABLE:
            return
        try:
            with sentry_sdk.push_scope() as scope:
                if context:
                    for key, value in context.items():
                        scope.set_context(key, value)
                if user:
                    scope.set_user(user)
                if tags:
                    for key, value in tags.items():
                        scope.set_tag(key, value)
                sentry_sdk.capture_exception(error)
        except Exception as e:
            logger.error(f"Failed to capture exception in Sentry: {str(e)}")

    @staticmethod
    def capture_message(
        message: str,
        level: str = "info",
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None
    ):
        """Capture a message/event."""
        if not SENTRY_AVAILABLE:
            return
        try:
            with sentry_sdk.push_scope() as scope:
                if context:
                    for key, value in context.items():
                        scope.set_context(key, value)
                if tags:
                    for key, value in tags.items():
                        scope.set_tag(key, value)
                sentry_sdk.capture_message(message, level=level)
        except Exception as e:
            logger.error(f"Failed to capture message in Sentry: {str(e)}")

    @staticmethod
    def log_error(
        message: str,
        error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None
    ):
        """Log an error with full context."""
        extra = {
            "business_id": business_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        if context:
            extra.update(context)
        logger.error(message, exc_info=error, extra=extra)
        if settings.SENTRY_DSN and SENTRY_AVAILABLE:
            MonitoringService.capture_exception(
                error or Exception(message),
                context=context,
                tags={"business_id": business_id} if business_id else None
            )

    @staticmethod
    def log_warning(
        message: str,
        context: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None
    ):
        """Log a warning."""
        extra = {
            "business_id": business_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        if context:
            extra.update(context)
        logger.warning(message, extra=extra)
        if settings.SENTRY_DSN and SENTRY_AVAILABLE:
            MonitoringService.capture_message(
                message,
                level="warning",
                context=context,
                tags={"business_id": business_id} if business_id else None
            )

    @staticmethod
    def log_info(
        message: str,
        context: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None
    ):
        """Log an info message."""
        extra = {
            "business_id": business_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        if context:
            extra.update(context)
        logger.info(message, extra=extra)

    @staticmethod
    def log_debug(
        message: str,
        context: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None
    ):
        """Log a debug message."""
        if not settings.DEBUG:
            return
        extra = {
            "business_id": business_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        if context:
            extra.update(context)
        logger.debug(message, extra=extra)

    @staticmethod
    def track_event(
        event_name: str,
        properties: Optional[Dict[str, Any]] = None,
        business_id: Optional[str] = None
    ):
        """Track a custom event."""
        context = properties or {}
        context["business_id"] = business_id
        context["timestamp"] = datetime.utcnow().isoformat()
        MonitoringService.log_info(
            f"Event tracked: {event_name}",
            context=context,
            business_id=business_id
        )
        if settings.SENTRY_DSN and SENTRY_AVAILABLE:
            MonitoringService.capture_message(
                f"Event: {event_name}",
                level="info",
                context=context,
                tags={"event": event_name, "business_id": business_id} if business_id else {"event": event_name}
            )

    @staticmethod
    def measure_performance(
        operation_name: str,
        duration_ms: float,
        business_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log performance metrics."""
        context = {
            "operation": operation_name,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat()
        }
        if metadata:
            context.update(metadata)
        if duration_ms > 1000:
            MonitoringService.log_warning(
                f"Slow operation detected: {operation_name}",
                context=context,
                business_id=business_id
            )
        else:
            MonitoringService.log_debug(
                f"Performance: {operation_name}",
                context=context,
                business_id=business_id
            )


# Global service instance
monitoring_service = MonitoringService()