"""Signed Cloud API contracts and worker behavior, all providers/storage mocked."""
import asyncio
import hashlib
import hmac
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from test_application_security import app, AuthUser, get_current_user, require_auth, TestClient, settings
from backend.routers import whatsapp
from backend.services import whatsapp_service as service
from backend.services.whatsapp_security import decrypt_secret, encrypt_secret

BID='00000000-0000-4000-8000-000000000001'
CID='00000000-0000-4000-8000-000000000002'
JID='00000000-0000-4000-8000-000000000003'
REV='00000000-0000-4000-8000-000000000004'
PHONE='123456789012345'
SENDER='972501234567'
SECRET='offline-meta-app-secret'


def connection():
    return dict(id=CID,business_id=BID,owner_id='owner-id',phone_number_id=PHONE,revision=REV,
        enabled=True,verified_at='2026-10-04T00:00:00Z',test_recipients=[SENDER],
        access_token_encrypted=encrypt_secret('offline-access-token-123456'),verify_token_encrypted=encrypt_secret('verify-secret'))


def payload(phone=PHONE,sender=SENDER):
    return {'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{
        'metadata':{'phone_number_id':phone},'messages':[{'id':'wamid.inbound','from':sender,
        'timestamp':str(int(datetime.now(timezone.utc).timestamp())),'type':'text','text':{'body':'תיק'}}]}}]}]}


class WhatsAppApiTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[require_auth]=lambda: AuthUser('owner-id','owner@example.com',True)
        self.client=TestClient(app)
        self.config=patch.multiple(settings,WHATSAPP_ENABLED=True,WHATSAPP_APP_SECRET=SECRET,WHATSAPP_TEST_PHONE_NUMBER_IDS=PHONE)
        self.config.start()
        self.owner=patch.object(whatsapp,'require_business_owner_for_business_id',return_value=BID);self.owner.start()
        self.rate=patch.object(whatsapp.connect_limiter,'is_allowed',return_value=True);self.rate.start()

    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.config.stop();self.owner.stop();self.rate.stop()

    def post(self,data,signature=True):
        raw=json.dumps(data).encode()
        sig='sha256='+hmac.new(SECRET.encode(),raw,hashlib.sha256).hexdigest() if signature else 'sha256=bad'
        return self.client.post('/api/v1/webhooks/whatsapp/'+CID,content=raw,headers={'X-Hub-Signature-256':sig})

    def test_status_redacts_all_secrets_and_requires_business_owner(self):
        c=connection();db=MagicMock();db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data=[]
        with patch.object(whatsapp,'connection_for',AsyncMock(return_value=c)),patch.object(whatsapp,'supabase',db):
            response=self.client.get('/api/v1/integrations/whatsapp?business_id='+BID)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['configured'])
        self.assertNotIn('encrypted',response.text);self.assertNotIn('verify-secret',response.text);self.assertNotIn('access_token',response.text)
        self.owner.target.require_business_owner_for_business_id.assert_called_once()

    def test_save_validates_meta_encrypts_credentials_and_rotates_verification(self):
        db=MagicMock();db.table.return_value.upsert.return_value.execute.return_value.data=[connection()]
        data={'business_id':BID,'phone_number_id':PHONE,'access_token':'offline-access-token-123456','test_recipients':['+'+SENDER]}
        graph=AsyncMock(return_value={'id':PHONE,'display_phone_number':'+1 555 0100'})
        with patch.object(whatsapp,'supabase',db),patch.object(whatsapp,'graph_request',graph):
            response=self.client.put('/api/v1/integrations/whatsapp',json=data)
        self.assertEqual(response.status_code,200)
        row=db.table.return_value.upsert.call_args.args[0]
        self.assertEqual(decrypt_secret(row['access_token_encrypted']),data['access_token'])
        self.assertEqual(decrypt_secret(row['verify_token_encrypted']),response.json()['verify_token'])
        self.assertIsNone(row['verified_at']);self.assertNotEqual(row['revision'],REV)
        self.assertEqual(row['test_recipients'],[SENDER]);self.assertNotIn(data['access_token'],response.text)

    def test_non_test_phone_never_calls_meta(self):
        with patch.object(whatsapp,'graph_request',AsyncMock()) as graph:
            r=self.client.put('/api/v1/integrations/whatsapp',json={'business_id':BID,'phone_number_id':'999999','access_token':'offline-access-token-123456','test_recipients':[SENDER]})
        self.assertEqual(r.status_code,403);graph.assert_not_called()

    def test_invalid_recipients_rejected(self):
        for values in [[],[SENDER,SENDER],['050-1234567'],[SENDER]*6]:
            r=self.client.put('/api/v1/integrations/whatsapp',json={'business_id':BID,'phone_number_id':PHONE,'access_token':'offline-access-token-123456','test_recipients':values})
            self.assertEqual(r.status_code,422)

    def test_foreign_owner_and_unverified_user_cannot_connect(self):
        from fastapi import HTTPException
        with patch.object(whatsapp,'require_business_owner_for_business_id',side_effect=HTTPException(403)),patch.object(whatsapp,'graph_request',AsyncMock()) as graph:
            self.assertEqual(self.client.get('/api/v1/integrations/whatsapp?business_id='+BID).status_code,403)
            self.assertEqual(self.client.delete('/api/v1/integrations/whatsapp?business_id='+BID).status_code,403)
        graph.assert_not_called()
        app.dependency_overrides.clear()
        self.assertIn(self.client.get('/api/v1/integrations/whatsapp?business_id='+BID).status_code,[401,403])
        app.dependency_overrides[get_current_user]=lambda: AuthUser('owner-id','owner@example.com',False)
        self.assertEqual(self.client.get('/api/v1/integrations/whatsapp?business_id='+BID).status_code,403)

    def test_rate_limited_configuration_never_calls_meta(self):
        with patch.object(whatsapp.connect_limiter,'is_allowed',return_value=False),patch.object(whatsapp,'graph_request',AsyncMock()) as graph:
            r=self.client.put('/api/v1/integrations/whatsapp',json={'business_id':BID,'phone_number_id':PHONE,'access_token':'offline-access-token-123456','test_recipients':[SENDER]})
        self.assertEqual(r.status_code,429);graph.assert_not_called()

    def test_meta_failure_does_not_save_or_expose_provider_secrets(self):
        with patch.object(whatsapp,'graph_request',AsyncMock(side_effect=service.MetaError('meta_190'))),patch.object(whatsapp,'supabase') as db:
            r=self.client.put('/api/v1/integrations/whatsapp',json={'business_id':BID,'phone_number_id':PHONE,'access_token':'offline-access-token-123456','test_recipients':[SENDER]})
        self.assertEqual(r.status_code,422);self.assertEqual(r.json()['detail']['code'],'meta_190');db.table.assert_not_called()

    def test_receipts_are_persisted_with_connection_scope(self):
        data=payload();value=data['entry'][0]['changes'][0]['value'];value.pop('messages');value['statuses']=[{'id':'wamid.outbound','status':'failed','errors':[{'code':190,'message':'provider-secret'}]}]
        db=MagicMock()
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=connection())),patch.object(whatsapp,'supabase',db):
            self.assertEqual(self.post(data).status_code,200)
        db.rpc.assert_called_once_with('whatsapp_delivery_status',{'p_connection_id':CID,'p_outbound_id':'wamid.outbound','p_status':'failed','p_error_code':'meta_190'})

    def test_oversized_body_is_bounded_before_processing(self):
        with patch.object(whatsapp,'webhook_connection',AsyncMock()) as lookup:
            r=self.client.post('/api/v1/webhooks/whatsapp/'+CID,content=b'x'*262145)
        self.assertEqual(r.status_code,413);lookup.assert_not_called()

    def test_unconfigured_server_has_no_fake_connection(self):
        with patch.object(settings,'WHATSAPP_ENABLED',False),patch.object(whatsapp,'connection_for',AsyncMock(return_value=None)):
            r=self.client.get('/api/v1/integrations/whatsapp?business_id='+BID)
        self.assertEqual(r.json()['server_ready'],False);self.assertFalse(r.json()['configured'])

    def test_disabled_server_still_exposes_disconnectable_connection_without_secrets(self):
        with patch.object(settings,'WHATSAPP_ENABLED',False),patch.object(whatsapp,'connection_for',AsyncMock(return_value=connection())),patch.object(whatsapp,'db_call',AsyncMock(return_value=[])):
            r=self.client.get('/api/v1/integrations/whatsapp?business_id='+BID)
        self.assertFalse(r.json()['server_ready']);self.assertTrue(r.json()['configured']);self.assertNotIn('access_token',r.text)

    def test_challenge_requires_exact_token_and_returns_plaintext(self):
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=connection())),patch.object(whatsapp,'db_call',AsyncMock(return_value=[])) as db:
            base='/api/v1/webhooks/whatsapp/'+CID
            self.assertEqual(self.client.get(base,params={'hub.mode':'subscribe','hub.verify_token':'wrong','hub.challenge':'1234'}).status_code,403)
            self.assertEqual(self.client.get(base,params={'hub.mode':'subscribe','hub.verify_token':'טעות','hub.challenge':'1234'}).status_code,403)
            db.assert_not_called()
            r=self.client.get(base,params={'hub.mode':'subscribe','hub.verify_token':'verify-secret','hub.challenge':'1234'})
        self.assertEqual(r.text,'1234');self.assertTrue(r.headers['content-type'].startswith('text/plain'))

    def test_forged_payload_rejected_before_storage(self):
        with patch.object(whatsapp,'webhook_connection',AsyncMock()) as lookup:
            self.assertEqual(self.post(payload(),False).status_code,401)
        lookup.assert_not_called()

    def test_valid_payload_is_durably_deduplicated_before_ack(self):
        db=MagicMock()
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=connection())),patch.object(whatsapp,'supabase',db):
            self.assertEqual(self.post(payload()).status_code,200)
        args=db.table.return_value.upsert.call_args
        self.assertTrue(args.kwargs['ignore_duplicates']);self.assertEqual(args.kwargs['on_conflict'],'connection_id,meta_message_id')
        self.assertEqual(args.args[0][0]['body'],'תיק');self.assertEqual(args.args[0][0]['revision'],REV)

    def test_storage_failure_returns_retryable_503(self):
        db=MagicMock();db.table.return_value.upsert.return_value.execute.side_effect=RuntimeError('offline')
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=connection())),patch.object(whatsapp,'supabase',db):
            self.assertEqual(self.post(payload()).status_code,503)

    def test_wrong_phone_outside_recipient_list_and_old_messages_are_ignored(self):
        old=payload();old['entry'][0]['changes'][0]['value']['messages'][0]['timestamp']='1'
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=connection())),patch.object(whatsapp,'supabase') as db:
            for data in [payload(phone='99999'),payload(sender='972509999999'),old]:
                self.assertEqual(self.post(data).status_code,200)
        db.table.assert_not_called()

    def test_malformed_signed_payload_and_unverified_connection(self):
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=connection())):
            self.assertEqual(self.post({'object':'whatsapp_business_account','entry':[None]}).status_code,400)
        c=connection();c['verified_at']=None
        with patch.object(whatsapp,'webhook_connection',AsyncMock(return_value=c)):
            self.assertEqual(self.post(payload()).status_code,409)

    def test_disconnect_scopes_delete_to_owner(self):
        db=MagicMock()
        with patch.object(whatsapp,'supabase',db):
            self.assertEqual(self.client.delete('/api/v1/integrations/whatsapp?business_id='+BID).status_code,200)
        db.table.return_value.delete.return_value.eq.return_value.eq.assert_called_once_with('owner_id','owner-id')


class WhatsAppWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config=patch.multiple(settings,WHATSAPP_ENABLED=True,WHATSAPP_APP_SECRET=SECRET,WHATSAPP_TEST_PHONE_NUMBER_IDS=PHONE);self.config.start()
        self.c=connection();self.db=MagicMock();self.worker=service.WhatsAppWorker(self.db)
        self.worker.rpc=AsyncMock(return_value=True);self.worker.finish=AsyncMock()
        self.job=dict(id=JID,connection_id=CID,revision=REV,lease_token=REV,sender=SENDER,body='תיק',message_type='text',
            meta_message_id='wamid.inbound',attempts=1,message_timestamp=datetime.now(timezone.utc).isoformat())
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[self.c]
        self.db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'id':BID,'owner_id':'owner-id','business_name':'Store'}]
        self.search=patch('backend.routers.chat._relevant_products',AsyncMock(return_value=[{'name':'תיק','price':10,'currency':'ILS'}]));self.search.start()
        self.session=patch('backend.services.session_service.session_service.get_or_create_conversation',AsyncMock(return_value={'id':BID}));self.session.start()
        self.graph=patch.object(service,'graph_request',AsyncMock(return_value={'messages':[{'id':'wamid.outbound'}]}));self.graph.start()

    async def asyncTearDown(self):
        self.config.stop();self.search.stop();self.session.stop();self.graph.stop()

    async def test_reply_uses_catalog_no_checkout_or_ai_and_records_acceptance(self):
        with patch('backend.services.gemini_service.gemini_service.chat',AsyncMock()) as ai,patch('backend.routers.chat._create_order_checkout',AsyncMock()) as checkout:
            await self.worker.process(self.job)
        ai.assert_not_called();checkout.assert_not_called()
        self.worker.finish.assert_awaited_once_with(self.job,'accepted',outbound='wamid.outbound')
        body=service.graph_request.call_args.args[3];self.assertEqual(body['to'],SENDER);self.assertIn('10.00 ILS',body['text']['body'])

    async def test_disconnect_rotation_expiry_and_allowlist_prevent_send(self):
        for changes in [{'enabled':False},{'revision':JID},{'test_recipients':[]},{'phone_number_id':'99999'}]:
            self.c.update(changes);await self.worker.process(self.job);self.c=connection()
            self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[self.c]
        self.job['message_timestamp']='2000-01-01T00:00:00+00:00';await self.worker.process(self.job)
        service.graph_request.assert_not_called()

    async def test_expired_lease_or_disconnect_during_processing_prevents_send(self):
        self.worker.rpc.return_value=False
        await self.worker.process(self.job)
        service.graph_request.assert_not_called();self.worker.finish.assert_awaited_once_with(self.job,'ignored','connection_changed')

    async def test_ambiguous_send_is_not_retried(self):
        service.graph_request.side_effect=service.MetaError('meta_unreachable',uncertain=True)
        await self.worker.process(self.job)
        self.worker.finish.assert_awaited_once_with(self.job,'unknown','meta_unreachable')

    async def test_rejected_credentials_are_failed_not_claimed_delivered(self):
        service.graph_request.side_effect=service.MetaError('meta_190')
        await self.worker.process(self.job)
        self.worker.finish.assert_awaited_once_with(self.job,'failed','meta_190')

    async def test_crash_after_send_starts_never_requeues(self):
        service.graph_request.side_effect=RuntimeError('offline')
        await self.worker.process(self.job)
        self.worker.finish.assert_awaited_once_with(self.job,'unknown','delivery_unknown')

    async def test_missing_outbound_id_is_unknown(self):
        service.graph_request.return_value={}
        await self.worker.process(self.job)
        self.worker.finish.assert_awaited_once_with(self.job,'unknown','delivery_unknown')

    async def test_failure_before_send_has_bounded_retries(self):
        self.db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect=RuntimeError('offline')
        await self.worker.process(self.job)
        self.worker.finish.assert_awaited_once_with(self.job,'pending','processing_unavailable')
        self.worker.finish.reset_mock();self.job['attempts']=5
        await self.worker.process(self.job)
        self.worker.finish.assert_awaited_once_with(self.job,'failed','processing_unavailable')
        service.graph_request.assert_not_called()

    async def test_media_gets_text_only_explanation(self):
        self.job['message_type']='image';self.job['body']=''
        await self.worker.process(self.job)
        self.assertIn('טקסט בלבד',service.graph_request.call_args.args[3]['text']['body'])


if __name__=='__main__':
    unittest.main()
