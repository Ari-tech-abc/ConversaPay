"""Owner-managed test connections and signed Meta callbacks; secrets never in GET responses."""
import asyncio
import hmac
import json
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, SecretStr, field_validator
from supabase import create_client

from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.middleware.rate_limiter import RateLimiter
from backend.services.webhook_security import verify_signature
from backend.services.whatsapp_security import decrypt_secret, encrypt_secret
from backend.services.whatsapp_service import MetaError, allowed_phone_ids, configured, graph_request

router = APIRouter(tags=['whatsapp'])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
connect_limiter = RateLimiter(requests_per_minute=5, name='whatsapp_connect')


def unavailable():
    return HTTPException(503, detail={'code': 'whatsapp_unavailable'})


class ConnectionInput(BaseModel):
    business_id: UUID
    phone_number_id: str = Field(pattern=r'^\d{5,30}$')
    access_token: SecretStr = Field(min_length=20, max_length=4096)
    test_recipients: list[str] = Field(min_length=1, max_length=5)

    @field_validator('test_recipients')
    @classmethod
    def recipients(cls, values):
        import re
        normalized = []
        for value in values:
            value = value.strip().removeprefix('+')
            if not re.fullmatch(r'[1-9]\d{7,14}', value) or value in normalized:
                raise ValueError('Use unique international numbers, without spaces or dashes')
            normalized.append(value)
        return normalized


async def db_call(call):
    try:
        return (await asyncio.to_thread(call)).data
    except Exception:
        raise unavailable() from None


async def connection_for(business_id: str, owner_id: str):
    rows = await db_call(lambda: supabase.table('whatsapp_connections').select('*')
        .eq('business_id', business_id).eq('owner_id', owner_id).limit(1).execute())
    return rows[0] if rows else None


def safe_connection(c: dict | None) -> dict:
    result = {'server_ready': configured(), 'configured': bool(c), 'mode': 'test', 'responder': 'catalog'}
    if c:
        result.update({key: c.get(key) for key in ('id','phone_number_id','display_phone_number','test_recipients','enabled','verified_at','last_inbound_at')})
        result['webhook_url'] = f"{settings.BACKEND_URL.rstrip('/')}{settings.API_PREFIX}/webhooks/whatsapp/{c['id']}"
    return result


@router.get('/integrations/whatsapp')
async def status(business_id: UUID, user: AuthUser = Depends(require_auth)):
    bid = str(business_id)
    require_business_owner_for_business_id(bid, user)
    try:
        c = await connection_for(bid, user.user_id)
    except HTTPException:
        if configured():
            raise
        # An unprepared deployment cannot reliably report whether credentials exist.
        return {'server_ready': False, 'configured': None, 'state_available': False, 'mode': 'test', 'responder': 'catalog'}
    result = safe_connection(c)
    if c:
        rows = await db_call(lambda: supabase.table('whatsapp_inbox').select('status,error_code,updated_at')
            .eq('connection_id', c['id']).eq('revision', c['revision']).order('created_at', desc=True).limit(1).execute())
        result['last_message'] = rows[0] if rows else None
    return result


@router.put('/integrations/whatsapp')
async def connect(data: ConnectionInput, user: AuthUser = Depends(require_auth)):
    bid = str(data.business_id)
    require_business_owner_for_business_id(bid, user)
    if not connect_limiter.is_allowed(user.user_id):
        raise HTTPException(429, detail={'code': 'whatsapp_rate_limited'}, headers={'Retry-After': '60'})
    if not configured():
        raise HTTPException(503, detail={'code': 'whatsapp_not_configured'})
    if data.phone_number_id not in allowed_phone_ids():
        raise HTTPException(403, detail={'code': 'whatsapp_test_number_required'})
    try:
        phone = await graph_request('GET', data.phone_number_id, data.access_token.get_secret_value())
    except MetaError as exc:
        raise HTTPException(422, detail={'code': exc.code}) from None
    if str(phone.get('id')) != data.phone_number_id:
        raise HTTPException(422, detail={'code': 'whatsapp_phone_mismatch'})
    verify_token = secrets.token_urlsafe(32)
    # Rotation invalidates queued events and requires a fresh Meta verification.
    row = {'business_id': bid, 'owner_id': user.user_id, 'phone_number_id': data.phone_number_id,
        'display_phone_number': phone.get('display_phone_number'), 'access_token_encrypted': encrypt_secret(data.access_token.get_secret_value()),
        'verify_token_encrypted': encrypt_secret(verify_token), 'revision': str(uuid4()), 'test_recipients': data.test_recipients,
        'enabled': True, 'verified_at': None, 'last_inbound_at': None}
    rows = await db_call(lambda: supabase.table('whatsapp_connections').upsert(row, on_conflict='business_id').execute())
    if not rows:
        raise unavailable()
    response = safe_connection(rows[0])
    response['verify_token'] = verify_token  # Shown once, never returned by GET.
    return response


@router.delete('/integrations/whatsapp')
async def disconnect(business_id: UUID, user: AuthUser = Depends(require_auth)):
    bid = str(business_id)
    require_business_owner_for_business_id(bid, user)
    await db_call(lambda: supabase.table('whatsapp_connections').delete().eq('business_id', bid).eq('owner_id', user.user_id).execute())
    return {'disconnected': True}


async def webhook_connection(connection_id: UUID):
    if not configured():
        raise HTTPException(503, detail={'code': 'whatsapp_not_configured'})
    rows = await db_call(lambda: supabase.table('whatsapp_connections').select('*').eq('id', str(connection_id)).eq('enabled', True).limit(1).execute())
    if not rows or rows[0]['phone_number_id'] not in allowed_phone_ids():
        raise HTTPException(404)
    return rows[0]


@router.get('/webhooks/whatsapp/{connection_id}', response_class=PlainTextResponse)
async def verify(connection_id: UUID, mode: str = Query('', alias='hub.mode'),
                 token: str = Query('', alias='hub.verify_token'), challenge: str = Query('', alias='hub.challenge', max_length=256)):
    c = await webhook_connection(connection_id)
    expected = decrypt_secret(c['verify_token_encrypted'])
    if mode != 'subscribe' or not expected or not challenge or not hmac.compare_digest(token.encode('utf-8'), expected.encode('utf-8')):
        raise HTTPException(403, detail='Invalid verification token')
    await db_call(lambda: supabase.table('whatsapp_connections').update({'verified_at': datetime.now(timezone.utc).isoformat()})
        .eq('id', c['id']).eq('revision', c['revision']).execute())
    return PlainTextResponse(challenge)


@router.post('/webhooks/whatsapp/{connection_id}')
async def receive(connection_id: UUID, request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise HTTPException(413)
    signature = request.headers.get('X-Hub-Signature-256')
    if not signature or not signature.startswith('sha256=') or not verify_signature(bytes(raw), signature, settings.WHATSAPP_APP_SECRET or settings.META_APP_SECRET):
        raise HTTPException(401, detail='Invalid webhook signature')
    c = await webhook_connection(connection_id)
    if not c.get('verified_at'):
        raise HTTPException(409, detail={'code': 'whatsapp_verification_required'})
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
            raise ValueError()
        events, receipts = [], []
        now = datetime.now(timezone.utc)
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                if change.get('field') != 'messages':
                    continue
                value = change.get('value', {})
                if value.get('metadata', {}).get('phone_number_id') != c['phone_number_id']:
                    continue
                for message in value.get('messages', []):
                    sender = message.get('from')
                    if sender not in c['test_recipients']:
                        continue
                    message_id, kind = message['id'], message['type']
                    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 512 or not isinstance(kind, str) or len(kind) > 40:
                        raise ValueError()
                    stamp = datetime.fromtimestamp(int(message['timestamp']), timezone.utc)
                    if not -300 <= (now - stamp).total_seconds() < 23 * 3600:
                        continue
                    body = message.get('text', {}).get('body', '') if kind == 'text' else ''
                    if not isinstance(body, str) or len(body) > 4096:
                        raise ValueError()
                    events.append({'connection_id': c['id'], 'revision': c['revision'], 'meta_message_id': message_id,
                        'sender': sender, 'message_type': kind, 'body': body, 'message_timestamp': stamp.isoformat()})
                for receipt in value.get('statuses', []):
                    if receipt.get('status') not in {'sent','delivered','read','failed'} or not isinstance(receipt.get('id'), str):
                        continue
                    error = (receipt.get('errors') or [{}])[0].get('code')
                    receipts.append({'p_connection_id': c['id'], 'p_outbound_id': receipt['id'], 'p_status': receipt['status'],
                        'p_error_code': 'meta_' + str(error) if isinstance(error, int) else None})
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
        raise HTTPException(400, detail='Invalid WhatsApp payload') from None
    if events:
        # Acknowledge only after durable storage. Meta can retry a storage failure.
        await db_call(lambda: supabase.table('whatsapp_inbox').upsert(events, on_conflict='connection_id,meta_message_id', ignore_duplicates=True).execute())
        await db_call(lambda: supabase.table('whatsapp_connections').update({'last_inbound_at': now.isoformat()})
            .eq('id', c['id']).eq('revision', c['revision']).execute())
    for receipt in receipts:
        await db_call(lambda receipt=receipt: supabase.rpc('whatsapp_delivery_status', receipt).execute())
    return {'received': True}
