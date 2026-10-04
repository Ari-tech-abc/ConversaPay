"""Bounded catalog cleanup independent of email delivery configuration."""
import asyncio
import logging
from supabase import create_client
from backend.config import settings

logger = logging.getLogger(__name__)


async def run_product_deletions():
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    while True:
        delay = 2
        try:
            result = await asyncio.to_thread(lambda: client.rpc('process_product_delete_job', {}).execute())
            if result.data is True:
                delay = 0.1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error('Product deletion worker unavailable (%s)', type(exc).__name__)
            delay = 15
        await asyncio.sleep(delay)
