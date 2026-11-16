"""Offline subscription lifecycle regressions. No payment or email is sent."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

import test_application_security
from fastapi.testclient import TestClient
from backend.middleware.auth import AuthUser, require_auth
from backend.routers import payments, subscription, stripe_webhook
from backend.services import subscription_checkout as checkout
from backend.services import subscription_gateway as gateways
from backend.services import subscription_reconciliation as reconciliation
from backend.services import subscription_service
from backend.services.stripe_service import stripe_service
from backend.services.subscription_catalog import PLANS, invoice_confirms_subscription
from main import app

USER = '00000000-0000-4000-8000-000000000001'
ATTEMPT = '00000000-0000-4000-8000-000000000010'


def attempt(**changes):
    return dict(id=ATTEMPT, user_id=USER, provider='stripe', plan_type='pro', status='creating',
                provider_session_id=None, created_at=datetime.now(timezone.utc).isoformat(), **changes)


def provider_subscription(**changes):
    return dict(id='sub_one', status='active', customer='cus_one', current_period_end=4070908800,
                metadata={'user_id':USER, 'plan_type':'pro', 'checkout_attempt_id':ATTEMPT},
                latest_invoice={'status':'paid', 'amount_paid':20000, 'currency':'ils', 'lines':{'data':[{'subscription':'sub_one','amount':20000,'currency':'ils','period':{'start':4068230400,'end':4070908800}}]}}, **changes)


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.gateway=MagicMock(provider='stripe')
        self.gateway.create_checkout.return_value={'session_id':'cs_one', 'url':'https://checkout.stripe.com/c/pay/one'}
        self.rpc=MagicMock(side_effect=lambda db,name,args: attempt() if name=='claim_subscription_checkout' else {'status':'open'})
        self.patches=[patch.object(checkout,'get_subscription_gateway',return_value=self.gateway), patch.object(checkout,'billing_rpc',self.rpc)]
        for item in self.patches:item.start()
        self.addCleanup(lambda:[item.stop() for item in self.patches])

    def create(self):
        return checkout.create_subscription_checkout(self.db,user_id=USER,email='owner@example.com',plan_type='pro')

    def test_retry_after_timeout_reuses_the_durable_attempt_identity(self):
        self.gateway.create_checkout.side_effect=[TimeoutError('unknown outcome'), {'session_id':'cs_one','url':'https://checkout.stripe.com/c/pay/one'}]
        with self.assertRaises(TimeoutError):self.create()
        self.assertEqual(self.create()['session_id'],'cs_one')
        self.assertEqual([call.args[-1] for call in self.gateway.create_checkout.call_args_list],[ATTEMPT,ATTEMPT])

    def test_storage_failure_never_starts_a_provider_operation(self):
        self.rpc.side_effect=checkout.BillingStorageUnavailable('billing_storage_unavailable')
        with self.assertRaises(checkout.BillingStorageUnavailable):self.create()
        self.gateway.create_checkout.assert_not_called()

    def test_existing_subscription_is_not_purchased_again(self):
        self.rpc.side_effect=lambda *a:{'error':'billing_subscription_exists'}
        with self.assertRaisesRegex(checkout.BillingConflict,'billing_subscription_exists'):self.create()
        self.gateway.create_checkout.assert_not_called()

    def test_old_unknown_operation_is_not_replayed_outside_retention_window(self):
        old=attempt();old['created_at']=(datetime.now(timezone.utc)-timedelta(hours=21)).isoformat()
        self.rpc.side_effect=lambda *a:old
        with self.assertRaisesRegex(checkout.BillingConflict,'billing_confirmation_pending'):self.create()
        self.gateway.create_checkout.assert_not_called()

    def test_open_checkout_is_verified_and_reused(self):
        row=attempt();row.update(status='open',provider_session_id='cs_one')
        self.rpc.side_effect=lambda db,name,args:row if name=='claim_subscription_checkout' else {'status':'open'}
        self.gateway.retrieve_checkout.return_value={'id':'cs_one','mode':'subscription','status':'open','metadata':{'user_id':USER},'amount_total':20000,'currency':'ils','url':'https://checkout.stripe.com/c/pay/one'}
        self.assertEqual(self.create()['session_id'],'cs_one')
        self.gateway.create_checkout.assert_not_called()
        self.gateway.retrieve_checkout.return_value['metadata']={'user_id':'another-user'}
        with self.assertRaisesRegex(checkout.BillingConflict,'billing_session_mismatch'):self.create()

    def test_redirect_to_an_untrusted_host_is_never_returned(self):
        self.gateway.create_checkout.return_value['url']='https://attacker.example/pay'
        with self.assertRaisesRegex(checkout.BillingConflict,'billing_invalid_checkout'):self.create()

    def test_unconfirmed_isracard_configuration_never_falls_back_to_stripe(self):
        with patch.object(gateways.settings,'SUBSCRIPTION_PROVIDER','isracard'), patch.object(gateways,'StripeSubscriptionGateway') as stripe_gateway:
            with self.assertRaises(gateways.SubscriptionGatewayUnavailable):gateways.get_subscription_gateway()
        stripe_gateway.assert_not_called()

    def test_provider_request_uses_idempotency_and_copies_operation_metadata(self):
        session=SimpleNamespace(id='cs_one',url='https://checkout.stripe.com/c/pay/one',mode='subscription',payment_status='unpaid')
        with patch.object(stripe_service,'_ensure_configured'), patch('backend.services.stripe_service.stripe.checkout.Session.create',return_value=session) as create:
            stripe_service.create_checkout_session(amount=PLANS['pro'].amount,product_name='Talk2Pay PRO',mode='subscription',metadata={'user_id':USER,'plan_type':'pro','checkout_attempt_id':ATTEMPT},idempotency_key='subscription:'+ATTEMPT)
        self.assertEqual(create.call_args.kwargs['idempotency_key'],'subscription:'+ATTEMPT)
        self.assertEqual(create.call_args.kwargs['subscription_data']['metadata']['checkout_attempt_id'],ATTEMPT)

    def test_misconfigured_price_is_rejected_before_checkout_creation(self):
        bad={'active':True,'unit_amount':200,'currency':'usd','recurring':{'interval':'month'}}
        with patch.object(stripe_service,'_ensure_configured'), patch('backend.services.stripe_service.stripe.Price.retrieve',return_value=bad), patch.object(stripe_service,'_create_session') as create:
            with self.assertRaises(ValueError):stripe_service.create_checkout_session_with_price(price_id='price_bad',mode='subscription',expected_unit_amount=20000,metadata={'user_id':USER,'plan_type':'pro'})
        create.assert_not_called()

    def test_cancellation_requires_the_provider_to_confirm_the_exact_subscription(self):
        gateway=gateways.StripeSubscriptionGateway()
        with patch.object(gateway,'ensure_ready'),patch.object(stripe_service,'_ensure_configured'),patch.object(gateways.stripe.Subscription,'modify',return_value={'id':'sub_other','cancel_at_period_end':True}):
            with self.assertRaises(Exception):gateway.cancel_renewal('sub_one',ATTEMPT)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[require_auth]=lambda:AuthUser(USER,'owner@example.com',True)
        self.client=TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(self.client.close)
        self.profile={'user_id':USER,'plan_type':'pro','subscription_status':'active','stripe_subscription_id':'sub_one','subscription_expires_at':'2099-01-01T00:00:00Z','auto_renew':True}

    def confirm(self, amount=20000, invoice=None):
        session={'id':'cs_one','mode':'subscription','status':'complete','payment_status':'paid','amount_total':amount,'currency':'ils','subscription':'sub_one','metadata':{'user_id':USER,'plan_type':'pro'}}
        current=provider_subscription()
        if invoice is not None:current['latest_invoice']=invoice
        apply=MagicMock(return_value=True)
        with patch.object(payments.stripe_service,'retrieve_checkout_session',return_value=session),patch.object(payments.stripe_service,'retrieve_subscription',return_value=current),patch.object(payments,'apply_subscription_state',apply):
            response=self.client.get('/api/v1/payments/confirm-session?session_id=cs_one')
        return response,apply

    def test_verified_paid_checkout_confirms_and_applies_once_through_atomic_storage(self):
        response,apply=self.confirm()
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['confirmed'])
        self.assertTrue(apply.call_args.kwargs['payment_confirmed'])

    def test_confirmation_rejects_a_paid_but_wrong_amount(self):
        response,apply=self.confirm(amount=200)
        self.assertEqual(response.status_code,409)
        apply.assert_not_called()

    def test_old_checkout_cannot_fund_a_later_unpaid_renewal(self):
        response,apply=self.confirm(invoice={'status':'open','amount_paid':0,'currency':'ils'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['confirmed'])
        apply.assert_not_called()

    def test_expired_access_does_not_falsely_report_stopped_recurring_billing(self):
        self.profile['subscription_expires_at']='2020-01-01T00:00:00Z'
        status=subscription._status_payload(self.profile)
        self.assertFalse(status['is_paid'])
        self.assertTrue(status['auto_renew'])
        self.assertTrue(status['can_cancel'])

    def test_failed_provider_cancellation_does_not_change_renewal_state(self):
        gateway=MagicMock();gateway.cancel_renewal.side_effect=TimeoutError('unknown result')
        rpc=MagicMock(return_value={'id':ATTEMPT,'status':'requested'})
        with patch.object(subscription,'_load_profile',return_value=self.profile),patch.object(subscription,'get_subscription_gateway',return_value=gateway),patch.object(subscription,'billing_rpc',rpc),patch.object(subscription,'supabase') as db:
            response=self.client.post('/api/v1/subscription/cancel',json={'reason':'Cancel renewal','request_refund':True})
        self.assertEqual(response.status_code,502)
        self.assertEqual(response.json()['detail'],'billing_cancellation_unconfirmed')
        self.assertEqual(rpc.call_count,1)
        db.table.assert_not_called()

    def test_confirmed_cancellation_preserves_paid_access_and_does_not_claim_refund(self):
        gateway=MagicMock()
        rpc=MagicMock(side_effect=[{'id':ATTEMPT,'status':'requested'},{'status':'confirmed','refund_request_id':'review-one'}])
        with patch.object(subscription,'_load_profile',return_value=self.profile),patch.object(subscription,'get_subscription_gateway',return_value=gateway),patch.object(subscription,'billing_rpc',rpc):
            response=self.client.post('/api/v1/subscription/cancel',json={'reason':'Cancel renewal','request_refund':True})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['cancellation_confirmed'])
        self.assertFalse(response.json()['auto_renew'])
        self.assertTrue(response.json()['is_paid'])
        self.assertFalse(response.json()['refund_completed'])
        self.assertEqual(gateway.cancel_renewal.call_args.args,('sub_one',ATTEMPT))

    def test_expired_access_does_not_prevent_stopping_a_recurring_contract(self):
        self.profile['subscription_expires_at']='2020-01-01T00:00:00Z'
        with patch.object(subscription,'_load_profile',return_value=self.profile),patch.object(subscription,'get_subscription_gateway') as gateway,patch.object(subscription,'billing_rpc',side_effect=[{'id':ATTEMPT,'status':'requested'},{'status':'confirmed'}]):
            response=self.client.post('/api/v1/subscription/cancel',json={'reason':'Stop future charges'})
        self.assertEqual(response.status_code,200)
        gateway.return_value.cancel_renewal.assert_called_once()

    def webhook(self,event):
        with patch.object(stripe_webhook.stripe.Webhook,'construct_event',return_value=event),patch.object(stripe_webhook.settings,'STRIPE_WEBHOOK_SECRET','offline'),patch.object(stripe_webhook,'_claim',return_value=True),patch.object(stripe_webhook,'mark_webhook_processed'),patch.object(stripe_webhook,'mark_webhook_failed'),patch.object(stripe_webhook,'apply_subscription_state') as apply,patch.object(stripe_webhook,'_lookup_user') as lookup:
            result=self.client.post('/api/v1/webhooks/stripe',content=b'{}',headers={'stripe-signature':'offline'})
        return result,apply,lookup

    def test_order_refund_does_not_cancel_a_subscription_with_the_same_customer(self):
        response,apply,lookup=self.webhook({'id':'evt_refund','type':'charge.refunded','data':{'object':{'id':'ch_order','customer':'cus_one','amount_refunded':24900}}})
        self.assertEqual(response.status_code,200)
        apply.assert_not_called();lookup.assert_not_called()

    def test_unpaid_checkout_does_not_grant_access_or_require_a_subscription_fetch(self):
        with patch.object(stripe_webhook,'_retrieve_subscription') as retrieve:
            response,apply,_=self.webhook({'id':'evt_pending','type':'checkout.session.completed','data':{'object':{'id':'cs_one','mode':'subscription','payment_status':'unpaid','subscription':'sub_one'}}})
        self.assertEqual(response.status_code,200)
        apply.assert_not_called();retrieve.assert_not_called()

    def test_failed_fresh_state_lookup_does_not_apply_a_stale_active_event(self):
        with patch.object(stripe_webhook,'_retrieve_subscription',return_value=None):
            response,apply,_=self.webhook({'id':'evt_stale','type':'customer.subscription.updated','data':{'object':provider_subscription()}})
        self.assertEqual(response.status_code,500)
        apply.assert_not_called()

    def test_invoice_proof_requires_full_amount_currency_and_current_paid_invoice(self):
        self.assertTrue(invoice_confirms_subscription(provider_subscription(),PLANS['pro']))
        for invoice in [{'status':'open','amount_paid':20000,'currency':'ils'},{'status':'paid','amount_paid':200,'currency':'ils'},{'status':'paid','amount_paid':20000,'currency':'usd'},'invoice_id']:
            sub=provider_subscription();sub['latest_invoice']=invoice
            self.assertFalse(invoice_confirms_subscription(sub,PLANS['pro']))

    def test_provider_period_advance_does_not_extend_the_paid_invoice_period(self):
        current=provider_subscription()
        current['current_period_end']=4102444800  # Provider has advanced into a later billing period.
        transaction=MagicMock(return_value={'applied':True})
        with patch.object(subscription_service,'billing_rpc',transaction):
            subscription_service.apply_subscription_state(user_id=USER,plan_type='pro',subscription_status='active',subscription_expires_at='2100-01-01T00:00:00+00:00',stripe_subscription=current,payment_confirmed=True)
        self.assertTrue(transaction.call_args.args[2]['p_period_end'].startswith('2099-01-01'))

    def test_missed_confirmation_reconciliation_never_creates_a_payment(self):
        row=attempt();row.update(provider_session_id='cs_one',status='open')
        gateway=MagicMock()
        gateway.retrieve_checkout.return_value={'id':'cs_one','mode':'subscription','status':'complete','payment_status':'paid','amount_total':20000,'currency':'ils','subscription':'sub_one','metadata':{'user_id':USER,'checkout_attempt_id':ATTEMPT}}
        gateway.retrieve_subscription.return_value=provider_subscription()
        with patch.object(subscription_service,'apply_subscription_state',return_value=True) as apply:
            self.assertEqual(reconciliation.reconcile_attempt(MagicMock(),row,gateway),'confirmed')
        apply.assert_called_once();gateway.create_checkout.assert_not_called();gateway.cancel_renewal.assert_not_called()
        row['provider_session_id']=None
        self.assertEqual(reconciliation.reconcile_attempt(MagicMock(),row,gateway),'needs_review')

    def test_cancellation_timeout_is_repaired_by_reading_provider_confirmation(self):
        gateway=MagicMock()
        gateway.retrieve_subscription.return_value={'id':'sub_one','cancel_at_period_end':True}
        row={'id':ATTEMPT,'user_id':USER,'provider':'stripe','provider_subscription_id':'sub_one'}
        with patch.object(reconciliation,'billing_rpc',return_value={'status':'confirmed'}) as finalize:
            self.assertEqual(reconciliation.reconcile_cancellation(MagicMock(),row,gateway),'confirmed')
        finalize.assert_called_once();gateway.cancel_renewal.assert_not_called();gateway.create_checkout.assert_not_called()
        gateway.retrieve_subscription.return_value['cancel_at_period_end']=False
        with patch.object(reconciliation,'billing_rpc') as finalize:
            self.assertEqual(reconciliation.reconcile_cancellation(MagicMock(),row,gateway),'pending')
        finalize.assert_not_called()


if __name__=='__main__':unittest.main()
