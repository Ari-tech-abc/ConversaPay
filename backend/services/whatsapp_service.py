"""Test-number Cloud API transport and a durable, bounded inbox worker.

The test responder searches the existing catalog without calling AI or checkout APIs.
An uncertain outbound result is never retried automatically.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from supabase import create_client

from backend.config import settings
from backend.services.whatsapp_security import decrypt_secret

logger = logging.getLogger(__name__)


def allowed_phone_ids() -> set[str]:
    return {value.strip() for value in settings.WHATSAPP_TEST_PHONE_NUMBER_IDS.split(',') if value.strip()}


def configured() -> bool:
    return bool(settings.WHATSAPP_ENABLED and (settings.WHATSAPP_APP_SECRET or settings.META_APP_SECRET) and allowed_phone_ids())


class MetaError(Exception):
    def __init__(self, code: str, uncertain: bool = False):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)


async def graph_request(method: str, phone_id: str, token: str, body: dict | None = None) -> dict:
    # Host, API version and object ID are not accepted as arbitrary URLs from users.
    version = settings.WHATSAPP_GRAPH_VERSION
    if not re.fullmatch(r'v\d+\.0', version) or not re.fullmatch(r'\d{5,30}', phone_id):
        raise MetaError('invalid_meta_configuration')
    path = f'https://graph.facebook.com/{version}/{phone_id}' + ('/messages' if method == 'POST' else '')
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.request(method, path, headers={'Authorization': f'Bearer {token}'},
                params={'fields': 'id,display_phone_number,verified_name'} if method == 'GET' else None, json=body)
    except httpx.RequestError:
        raise MetaError('meta_unreachable', uncertain=method == 'POST') from None
    try:
        data = response.json()
    except ValueError:
        raise MetaError('meta_invalid_response', uncertain=method == 'POST') from None
    if response.is_error or not isinstance(data, dict) or data.get('error'):
        code = (data.get('error') or {}).get('code') if isinstance(data, dict) and isinstance(data.get('error'), dict) else None
        safe_code = str(code) if isinstance(code, int) else 'rejected'
        raise MetaError('meta_' + safe_code, uncertain=method == 'POST' and response.status_code >= 500)
    return data


def catalog_reply(business: dict, products: list[dict], message_type: str) -> str:
    """No invented stock, payment URLs, or AI calls in the zero-AI-cost test mode."""
    if message_type != 'text':
        return 'בשלב הבדיקה אפשר לשלוח הודעות טקסט בלבד. כתבו שם מוצר ואחפש אותו בקטלוג.'
    if not products:
        return 'לא מצאתי מוצר שמתאים לחיפוש. אפשר לנסות שם מוצר אחר.'
    lines = ['אלה מוצרים מהקטלוג של ' + str(business.get('business_name') or 'העסק')[:120] + ':']
    for product in products[:3]:
        line = str(product.get('name') or product.get('item_key') or 'מוצר')[:180]
        try:
            price = Decimal(str(product.get('price')))
            if price.is_finite():
                line += f" — {price:.2f} {str(product.get('currency') or 'ILS')[:8]}"
        except (InvalidOperation, TypeError, ValueError):
            pass
        if product.get('inventory_count') == 0:
            line += ' (אזל מהמלאי)'
        lines.append(line)
    lines.append('זהו מענה לבדיקת החיבור. לא נוצרה הזמנה או בקשת תשלום.')
    return '\n\n'.join(lines)[:4096]


class WhatsAppWorker:
    def __init__(self, client=None):
        self.client = client or create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    async def rpc(self, name: str, params: dict):
        return (await asyncio.to_thread(lambda: self.client.rpc(name, params).execute())).data

    async def finish(self, job: dict, status: str, error: str | None = None, outbound: str | None = None):
        await self.rpc('finish_whatsapp_message', {'p_id': job['id'], 'p_lease_token': job['lease_token'],
            'p_status': status, 'p_error_code': error, 'p_outbound_id': outbound})

    async def process(self, job: dict):
        sending = False
        try:
            connection = (await asyncio.to_thread(lambda: self.client.table('whatsapp_connections').select('*')
                .eq('id', job['connection_id']).limit(1).execute())).data
            c = connection[0] if connection else None
            if not configured() or not c or not c['enabled'] or not c.get('verified_at') or c['revision'] != job['revision'] \
                    or c['phone_number_id'] not in allowed_phone_ids() or job['sender'] not in c['test_recipients']:
                return await self.finish(job, 'ignored', 'connection_inactive')
            timestamp = datetime.fromisoformat(job['message_timestamp'].replace('Z', '+00:00'))
            # A queue delay must never turn a service reply into an unsolicited/template message.
            if (datetime.now(timezone.utc) - timestamp).total_seconds() >= 23 * 3600:
                return await self.finish(job, 'ignored', 'reply_window_expired')
            token = decrypt_secret(c['access_token_encrypted'])
            if not token:
                return await self.finish(job, 'failed', 'credentials_unreadable')
            businesses = (await asyncio.to_thread(lambda: self.client.table('businesses').select('*')
                .eq('id', c['business_id']).eq('owner_id', c['owner_id']).eq('is_active', True).limit(1).execute())).data
            if not businesses:
                return await self.finish(job, 'ignored', 'business_inactive')
            from backend.routers.chat import _relevant_products, _search_terms
            from backend.services.session_service import session_service
            business = businesses[0]
            products = await _relevant_products(c['business_id'], job['body'], limit=3) if job['message_type'] == 'text' else []
            # The shared chat search falls back to a catalog sample; label that as suggestions.
            reply = catalog_reply(business, products, job['message_type'])
            if products and _search_terms(job['body']):
                terms = _search_terms(job['body'])
                matching = [p for p in products if any(term in str(p.get(field) or '').lower() for term in terms for field in ('name','item_key','description'))]
                reply = catalog_reply(business, matching, job['message_type'])
            conversation = await session_service.get_or_create_conversation(c['business_id'],
                session_id=f"wa_{c['id']}_{job['sender']}", channel='whatsapp')
            # Stable IDs keep lease recovery from adding the same conversation messages twice.
            for role, content in (('user', job['body'] or '[' + job['message_type'] + ']'), ('assistant', reply)):
                message_id = str(uuid.uuid5(uuid.UUID(job['id']), role))
                await asyncio.to_thread(lambda role=role, content=content, message_id=message_id: self.client.table('messages')
                    .upsert({'id': message_id, 'conversation_id': conversation['id'], 'role': role, 'content': content,
                        'metadata': {'whatsapp_inbox_id': job['id'], 'test_mode': True}}, on_conflict='id', ignore_duplicates=True).execute())
            if not await self.rpc('begin_whatsapp_send', {'p_id': job['id'], 'p_lease_token': job['lease_token']}):
                return await self.finish(job, 'ignored', 'connection_changed')
            sending = True
            result = await graph_request('POST', c['phone_number_id'], token, {'messaging_product': 'whatsapp',
                'to': job['sender'], 'type': 'text', 'text': {'body': reply, 'preview_url': False},
                'context': {'message_id': job['meta_message_id']}})
            messages = result.get('messages')
            outbound = messages[0].get('id') if isinstance(messages, list) and messages and isinstance(messages[0], dict) else None
            if not isinstance(outbound, str) or not outbound:
                return await self.finish(job, 'unknown', 'delivery_unknown')
            await self.finish(job, 'accepted', outbound=outbound)
        except asyncio.CancelledError:
            raise
        except MetaError as exc:
            await self.finish(job, 'unknown' if exc.uncertain else 'failed', exc.code)
        except Exception as exc:
            # Never log bodies, recipient numbers, access tokens, or provider error payloads.
            logger.error('WhatsApp worker failure (%s)', type(exc).__name__)
            await self.finish(job, 'unknown' if sending else ('failed' if job['attempts'] >= 5 else 'pending'),
                'delivery_unknown' if sending else 'processing_unavailable')

    async def run(self):
        while True:
            delay = 2
            try:
                job = await self.rpc('claim_whatsapp_message', {})
                if job:
                    await self.process(job)
                    delay = 0.1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error('WhatsApp inbox unavailable (%s)', type(exc).__name__)
                delay = 15
            await asyncio.sleep(delay)
