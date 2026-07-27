"""Optional Sentry bootstrap with explicit secret-safe defaults."""
from __future__ import annotations
import logging
from backend.config import settings

logger = logging.getLogger(__name__)


def initialize_error_tracking() -> bool:
    if not settings.SENTRY_DSN:
        logger.info('error_tracking_disabled')
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            send_default_pii=False,
            traces_sample_rate=0.1 if settings.is_production else 0.0,
        )
        return True
    except ImportError:
        logger.warning('sentry_dsn_configured_but_sdk_missing')
        return False
