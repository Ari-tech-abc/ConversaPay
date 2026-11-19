"""Full app boundaries and real SDK empty results; external providers stay offline."""
import asyncio
import io
import zipfile
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,AsyncMock,patch
import test_application_security as fixture
from fastapi.testclient import TestClient
from backend.routers import onboarding,auth,widget,payments,profile,stripe_webhook
from backend.models.schemas import BusinessResponse,ProductUpdate
from backend.services.database import optional_result
from backend.services import widget_auth,account_deletion
from backend.services.payment_adapters import get_checkout_adapter,PaymentAdapterError
from backend.services.stripe_service import stripe_service
from backend.services.checkout_contact import contact_for_checkout

USER='00000000-0000-4000-8000-000000000001'
BID='00000000-0000-4000-8000-000000000002'

class ProductionRepairsTests(unittest.TestCase):
 def setUp(self):
  self.client=TestClient(fixture.app,client=("repairs-"+self._testMethodName,50000))
  self.user=fixture.AuthUser(USER,'owner@example.com',True)
  fixture.app.dependency_overrides[fixture.require_auth]=lambda:self.user
  fixture.app.dependency_overrides[fixture.get_current_user]=lambda:self.user
 def tearDown(self):
  self.client.close();fixture.app.dependency_overrides.clear()

 def test_new_email_registers_then_verifies_and_logs_in_through_actual_routes(self):
  db=MagicMock()
  db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
  db.auth.admin.create_user.return_value=SimpleNamespace(user=SimpleNamespace(id=USER))
  row={'user_id':USER,'email':'new@example.com','email_verified':False,'email_verification_token':onboarding._code_hash('new@example.com','123456'),'email_verification_expires_at':(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()}
  with patch.object(onboarding,'supabase',db),patch.object(onboarding,'create_user_profile',return_value=row),patch.object(onboarding,'_new_code',return_value='123456'),patch.object(onboarding.email_service,'send_verification_code',return_value=True) as email,patch.object(onboarding,'check_rate_limit'):
   response=self.client.post('/api/v1/auth/signup-code',json={'email':'NEW@example.com','password':'Distinct phrase 6739','full_name':'Owner','business_name':'Shop'})
   self.assertEqual(response.status_code,201,response.text)
   email.assert_called_once_with('new@example.com','123456','Owner')
   db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data=row
   db.rpc.return_value.execute.return_value.data=True
   response=self.client.post('/api/v1/auth/verify-code',json={'email':'new@example.com','code':'123456'})
   self.assertEqual(response.status_code,200,response.text)
   db.auth.admin.update_user_by_id.assert_called_once_with(USER,{'email_confirm':True})
  provider=MagicMock();provider.auth.sign_in_with_password.return_value=SimpleNamespace(user=SimpleNamespace(id=USER,email='new@example.com',user_metadata={}),session=SimpleNamespace(access_token='verified-login'))
  with patch.object(auth,'create_auth_client',return_value=provider),patch.object(auth,'get_user_profile',return_value={**row,'email_verified':True}),patch.object(auth,'initialize_user_workspace',AsyncMock(return_value={})):
   response=self.client.post('/api/v1/auth/login',json={'email':'new@example.com','password':'Distinct phrase 6739'})
   self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['access_token'],'verified-login')

 def test_actual_sdk_empty_optional_response_is_safe(self):
  # The installed SDK returns None for an empty result, which broke first registration.
  import httpx
  from postgrest import SyncPostgrestClient
  db=SyncPostgrestClient('https://offline.invalid',http_client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=[]))))
  try:
   result=db.from_('profiles').select('*').maybe_single().execute()
   self.assertIsNone(result);self.assertIsNone(optional_result(result).data)
  finally:db.aclose() if hasattr(db,'aclose') else db.close()

 def test_unverified_registration_can_resume_after_reload(self):
  db=MagicMock();db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'user_id':USER,'email_verified':False}]
  with patch.object(onboarding,'supabase',db),patch.object(onboarding,'check_rate_limit'):
   response=self.client.post('/api/v1/auth/signup-code',json={'email':'owner@example.com','password':'Distinct phrase 6739','full_name':'Owner','business_name':'Shop'})
  self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail'],'verification_pending')
  db.auth.admin.create_user.assert_not_called()

 def test_auth_trigger_profile_is_initialized_without_billing_reset(self):
  db=MagicMock();db.table.return_value.insert.return_value.execute.side_effect=RuntimeError('duplicate user_id')
  db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'user_id':USER,'email_verified':False,'plan_type':'pro'}]
  db.table.return_value.update.return_value.eq.return_value.execute.return_value.data=[{'user_id':USER,'plan_type':'pro'}]
  with patch.object(auth,'supabase',db):result=auth.create_user_profile(USER,'owner@example.com','Owner','verification-token','2099-01-01T00:00:00Z')
  self.assertEqual(result['plan_type'],'pro');self.assertNotIn('plan_type',db.table.return_value.update.call_args.args[0])

 def test_widget_real_url_uses_only_schema_columns_and_cors(self):
  db=MagicMock();db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data={'id':BID,'settings':{'bot_name':'Store'}}
  with patch.object(widget,'_supabase',db),patch.object(widget,'plan_info',return_value={'plan_type':'pro'}),patch.object(widget,'authorize_widget_request',AsyncMock()):
   response=self.client.get('/api/v1/widget/config/'+BID,headers={'Origin':'https://merchant.example','X-Widget-Key':'key'})
  self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['bot_name'],'Store')
  self.assertEqual(response.headers['access-control-allow-origin'],'*')
  self.assertEqual(db.table.return_value.select.call_args.args[0],'id,settings')

 def test_paid_statuses_serialize_after_cancel(self):
  for state in ['pending_cancellation','trialing','incomplete','unpaid','paused']:
   row=BusinessResponse(id=BID,owner_id=USER,business_id='shop',business_name='Shop',subscription_tier='pro',subscription_status=state,is_active=True,created_at='2026-11-16T00:00:00Z',updated_at='2026-11-16T00:00:00Z')
   self.assertEqual(row.subscription_status.value,state)

 def test_expired_or_unprivileged_widget_key_rejected(self):
  for row in [{'id':'k','expires_at':'2000-01-01T00:00:00Z','permissions':['widget']},{'id':'k','permissions':['read']},{'id':'k','expires_at':'bad','permissions':['widget']}]:
   db=MagicMock();db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data=row
   self.assertFalse(widget_auth._valid_widget_key(db,BID,'secret'))

 def test_contact_required_for_shipping_and_urls_can_be_cleared(self):
  with self.assertRaises(ValueError):contact_for_checkout({'name':'Buyer','email':'buyer@example.com','phone':'0501234567'},'delivery')
  self.assertEqual(ProductUpdate(payment_link='').model_dump(exclude_unset=True),{'payment_link':None})
  with self.assertRaises(PaymentAdapterError):get_checkout_adapter('payme')

 def test_direct_checkout_scopes_charge_to_merchant(self):
  with patch.object(stripe_service,'_ensure_configured'),patch.object(stripe_service,'_create_session',return_value=SimpleNamespace(id='cs_1',url='https://checkout.stripe.com/test',mode='payment',payment_status='unpaid')) as create:
   stripe_service.create_checkout_session(amount=20,product_name='Product',metadata={'order_id':'o1'},stripe_account_id='acct_merchant')
  params=create.call_args.args[0]
  self.assertEqual(params['stripe_account'],'acct_merchant')
  self.assertIn('guest_token=',params['success_url']);self.assertIn('order_id=o1',params['success_url'])
  self.assertNotIn('transfer_data',params['payment_intent_data'])

 def test_wordpress_download_is_installable_zip(self):
  db=MagicMock();db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data=[{'id':BID}]
  with patch.object(payments,'supabase',db):response=self.client.get('/api/v1/payments/wordpress-plugin/shop')
  self.assertEqual(response.status_code,200,response.text)
  with zipfile.ZipFile(io.BytesIO(response.content)) as archive:self.assertIn('conversapay-chat/conversapay-chat.php',archive.namelist())

 def test_deletion_stops_on_billing_failure_before_identity_removal(self):
  db=MagicMock();db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'stripe_subscription_id':'sub_active'}]
  with patch.object(account_deletion,'get_subscription_gateway') as factory:
   factory.return_value.cancel_renewal.side_effect=RuntimeError('offline')
   with self.assertRaises(RuntimeError):account_deletion.delete_account_data(db,USER)
  db.auth.admin.delete_user.assert_not_called()
  self.assertEqual(db.rpc.call_args.args[0],'begin_account_deletion')

 def test_deletion_purges_only_after_identity_removal(self):
  db=MagicMock();db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
  db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data=[]
  calls=[];db.auth.admin.delete_user.side_effect=lambda _:calls.append('identity')
  db.rpc.side_effect=lambda name,args:SimpleNamespace(execute=lambda:calls.append(name))
  account_deletion.delete_account_data(db,USER)
  self.assertEqual(calls,['begin_account_deletion','identity','purge_account_data'])
