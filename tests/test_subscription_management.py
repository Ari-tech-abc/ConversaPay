"""No network or charges: billing summaries, recovery and request boundaries."""
import unittest
import asyncio
import os
from unittest.mock import MagicMock, patch
import test_application_security
from fastapi.testclient import TestClient
from main import app
from backend.middleware.auth import require_auth, AuthUser
from backend.routers import subscription
from backend.services import subscription_history as history, subscription_worker as worker
from backend.services.notification_templates import render_notification
from test_subscription_operations import USER, provider_subscription


class DeploymentTests(unittest.TestCase):
    def test_production_defaults_use_selected_provider_and_enable_recovery(self):
        from backend.config import Settings
        with patch.dict(os.environ):
            os.environ.pop('SUBSCRIPTION_PROVIDER', None)
            os.environ.pop('SUBSCRIPTION_WORKER_ENABLED', None)
            configured = Settings(ENVIRONMENT='production', _env_file=None)
        self.assertEqual(configured.SUBSCRIPTION_PROVIDER, 'stripe')
        self.assertTrue(configured.SUBSCRIPTION_WORKER_ENABLED)
        explicit = Settings(ENVIRONMENT='production', SUBSCRIPTION_PROVIDER='stripe', SUBSCRIPTION_WORKER_ENABLED=False, _env_file=None)
        self.assertEqual(explicit.SUBSCRIPTION_PROVIDER, 'stripe')
        self.assertFalse(explicit.SUBSCRIPTION_WORKER_ENABLED)

    def test_worker_reports_completed_cycle_and_cleans_up_on_shutdown(self):
        async def stop_after_cycle(_):
            self.assertEqual(worker.worker_status(), {'running':True,'ready':True})
            raise asyncio.CancelledError()
        with patch.object(worker, 'run_cycle', return_value={}), patch.object(worker.asyncio, 'sleep', side_effect=stop_after_cycle):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(worker.run_subscription_worker(MagicMock()))
        self.assertEqual(worker.worker_status(), {'running':False,'ready':False})


class InvoiceTests(unittest.TestCase):
    def test_invoice_binding_is_checked_before_writing(self):
        snapshot = provider_subscription()
        snapshot['latest_invoice'].update(id='in_one', subscription='sub_other', created=1700000000)
        with patch.object(history, 'billing_rpc') as rpc:
            with self.assertRaisesRegex(ValueError, 'billing_invoice_mismatch'):
                history.record_invoice(MagicMock(), USER, snapshot, 'pro')
            rpc.assert_not_called()

    def test_paid_invoice_records_actual_paid_period(self):
        snapshot = provider_subscription()
        snapshot['latest_invoice'].update(id='in_one', subscription='sub_one', created=1700000000)
        with patch.object(history, 'billing_rpc') as rpc:
            history.record_invoice(MagicMock(), USER, snapshot, 'pro')
        args = rpc.call_args.args[2]
        self.assertEqual(args['p_status'], 'paid')
        self.assertEqual(args['p_amount'], 20000)
        self.assertTrue(args['p_end'].startswith('2099-01-01'))

    def test_failed_invoice_does_not_claim_a_paid_period(self):
        snapshot = provider_subscription()
        snapshot['latest_invoice'] = {'id':'in_fail','subscription':'sub_one','created':1700000000,'status':'open','attempted':True,'amount_due':20000,'currency':'ils'}
        with patch.object(history, 'billing_rpc') as rpc:
            history.record_invoice(MagicMock(), USER, snapshot, 'pro')
        self.assertEqual(rpc.call_args.args[2]['p_status'], 'failed')
        self.assertIsNone(rpc.call_args.args[2]['p_end'])

    def test_unattempted_invoice_is_not_a_failed_payment(self):
        snapshot = provider_subscription()
        snapshot['latest_invoice'] = {'id':'in_open','subscription':'sub_one','created':1700000000,'status':'open','attempted':False}
        with patch.object(history, 'billing_rpc') as rpc:
            history.record_invoice(MagicMock(), USER, snapshot, 'pro')
        rpc.assert_not_called()


class ManagementTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[require_auth] = lambda: AuthUser(USER, 'owner@example.com', True)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(app.dependency_overrides.clear)

    def test_plan_request_never_claims_a_provider_change(self):
        with patch.object(subscription, 'billing_rpc', return_value={'id':'request','status':'requested'}) as rpc:
            response = self.client.post('/api/v1/subscription/plan-change', json={'plan_type':'premium','user_id':'attacker'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['provider_confirmed'])
        self.assertFalse(response.json()['charge_created'])
        self.assertIsNone(response.json()['effective_at'])
        self.assertEqual(rpc.call_args.args[2]['p_user_id'], USER)

    def test_past_due_has_no_promised_next_charge(self):
        row = {'plan_type':'pro','subscription_status':'past_due','subscription_expires_at':'2099-01-01T00:00:00Z','auto_renew':True}
        with patch.object(subscription, '_load_profile', return_value=row), patch.object(subscription, 'get_subscription_gateway'):
            response = self.client.get('/api/v1/subscription/status')
        self.assertTrue(response.json()['payment_action_required'])
        self.assertIsNone(response.json()['next_billing_at'])
        self.assertFalse(response.json()['plan_change_request_available'])

    def test_history_queries_always_scope_the_authenticated_user(self):
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        with patch.object(subscription, 'supabase', db):
            response = self.client.get('/api/v1/subscription/history?user_id=someone-else')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.table.return_value.select.return_value.eq.call_count, 3)
        for call in db.table.return_value.select.return_value.eq.call_args_list:
            self.assertEqual(call.args, ('user_id', USER))

    def test_worker_rejects_cross_owner_snapshot_without_applying(self):
        db = MagicMock()
        db.table.return_value.select.return_value.not_.is_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value.data = [{'user_id':USER,'subscription_provider':'stripe','provider_subscription_id':'sub_one'}]
        gateway = MagicMock()
        snapshot = provider_subscription(); snapshot['metadata']['user_id'] = 'other-owner'
        gateway.retrieve_subscription.return_value = snapshot
        with patch.object(worker, 'reconcile_pending', return_value={'needs_review':[]}), patch.object(worker, 'billing_rpc', return_value={'open_alerts':0}), patch.object(worker, 'get_subscription_gateway', return_value=gateway), patch.object(worker, 'apply_subscription_state') as apply:
            report = worker.run_cycle(db)
        self.assertEqual(report['subscription_errors'], 1)
        apply.assert_not_called()
        gateway.create_checkout.assert_not_called()
        gateway.cancel_renewal.assert_not_called()

    def test_failure_notification_escapes_content_and_links_to_management(self):
        subject, text, html = render_notification('subscription_billing', {'action':'failed','access_until':'<script>alert(1)</script>'}, 'https://example.com')
        self.assertIn('https://example.com/upgrade', text)
        self.assertNotIn('<script>', html)


if __name__ == '__main__':
    unittest.main()
