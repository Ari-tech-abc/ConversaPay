"""Offline regressions using real function bodies and isolated provider doubles."""
import ast
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from pathlib import Path
import secrets
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from decimal import Decimal

from backend.services.billing_reconciliation import active_plan_from_row, ACTIVE_STATUSES
from backend.services.payment_validation import checkout_amount

ROOT = Path(__file__).resolve().parents[1]


class HTTPError(Exception):
    def __init__(self, status_code, detail, **kwargs):
        self.status_code, self.detail = status_code, detail


def functions(path, names, **scope):
    """Compile source functions without loading app settings or contacting providers."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            body.append(node)
    namespace = dict(datetime=datetime, timedelta=timedelta, timezone=timezone,
                     HTTPException=HTTPError, logger=logging.getLogger("security-tests"), **scope)
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), path, "exec"), namespace)
    return namespace


class EmailVerificationTests(unittest.TestCase):
    def setup_route(self, verified=False, confirmed=False, consumed=True):
        profile = {"user_id": "test-user", "email_verified": verified,
                   "email_verification_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = profile
        db.auth.admin.get_user_by_id.return_value = SimpleNamespace(user=SimpleNamespace(email_confirmed_at="now" if confirmed else None))
        db.rpc.side_effect = lambda name, args: SimpleNamespace(execute=lambda: SimpleNamespace(data=consumed if name == "consume_email_verification" else True))
        scope = functions("backend/routers/onboarding.py", {"verify_email_code", "_code_hash"},
                          supabase=db, hashlib=hashlib, secrets=secrets,
                          settings=SimpleNamespace(SECRET_KEY="offline-test-secret"),
                          check_rate_limit=lambda *a, **kw: None,
                          verification_account_limiter=SimpleNamespace(is_allowed=lambda _: True))
        profile["email_verification_token"] = scope["_code_hash"]("owner@example.com", "123456")
        request = SimpleNamespace(email="owner@example.com", code="123456")
        return scope, db, request

    def test_profile_flag_cannot_confirm_auth(self):
        scope, db, request = self.setup_route(verified=True)
        with self.assertRaises(HTTPError) as error:
            asyncio.run(scope["verify_email_code"](request, None))
        self.assertEqual(error.exception.status_code, 400)
        db.auth.admin.update_user_by_id.assert_not_called()
        db.rpc.assert_not_called()

    def test_replayed_token_cannot_confirm_auth(self):
        scope, db, request = self.setup_route(consumed=False)
        with self.assertRaises(HTTPError):
            asyncio.run(scope["verify_email_code"](request, None))
        db.auth.admin.update_user_by_id.assert_not_called()

    def test_wrong_code_cannot_consume_token(self):
        scope, db, request = self.setup_route()
        request.code = "000000"
        with self.assertRaises(HTTPError):
            asyncio.run(scope["verify_email_code"](request, None))
        db.rpc.assert_not_called()
        db.auth.admin.update_user_by_id.assert_not_called()

    def test_correct_code_confirms_after_consumption(self):
        scope, db, request = self.setup_route()
        self.assertEqual(asyncio.run(scope["verify_email_code"](request, None)), {"verified": True})
        self.assertEqual([call.args[0] for call in db.rpc.call_args_list], ["consume_email_verification", "mark_email_verified"])
        db.auth.admin.update_user_by_id.assert_called_once_with("test-user", {"email_confirm": True})


class BillingTests(unittest.TestCase):
    def test_unpaid_and_unknown_states_never_grant_paid_plan(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        for state in ["incomplete", "incomplete_expired", "paused", "unpaid", "canceled", "unknown", None]:
            with self.subTest(state=state):
                self.assertEqual(active_plan_from_row({"plan_type":"premium", "subscription_status":state, "subscription_expires_at":future}), "free")

    def test_paid_plan_requires_valid_future_expiry(self):
        for expiry in [None, "invalid", "2020-01-01T00:00:00Z"]:
            self.assertEqual(active_plan_from_row({"plan_type":"pro", "subscription_status":"active", "subscription_expires_at":expiry}), "free")
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertEqual(active_plan_from_row({"plan_type":"pro", "subscription_status":"pending_cancellation", "subscription_expires_at":future}), "pro")

    def test_incomplete_subscription_has_no_invented_expiry(self):
        db = MagicMock()
        scope = functions("backend/services/subscription_service.py", {"apply_subscription_state", "_as_dict", "_resolve_plan_type", "normalize_plan_type", "_subscription_plan_candidates", "period_end_iso", "subscription_period_end"}, supabase=db, ACTIVE_STATUSES=ACTIVE_STATUSES)
        scope["apply_subscription_state"](user_id="u", plan_type="premium", subscription_status="incomplete", subscription_expires_at=None)
        payload = db.table.return_value.update.call_args_list[0].args[0]
        self.assertEqual(payload["plan_type"], "free")
        self.assertIsNone(payload["subscription_expires_at"])

    def test_provider_amount_validation(self):
        self.assertEqual(checkout_amount({"amount_total":12345,"currency":"ils"}), ("123.45","ILS"))
        self.assertEqual(checkout_amount({"amount_total":123,"currency":"jpy"}), ("123","JPY"))
        for amount in [None, True, -1, 0, "123"]:
            with self.assertRaises(ValueError): checkout_amount({"amount_total":amount,"currency":"ils"})


class WebhookTests(unittest.TestCase):
    def handler(self, payment_status):
        event = {"id":"evt_test", "type":"checkout.session.completed", "data":{"object":{
            "id":"cs_test","mode":"payment","payment_status":payment_status,
            "amount_total":10000,"currency":"ils","metadata":{"order_id":"o"}}}}
        update = MagicMock()
        request = SimpleNamespace(headers={"stripe-signature":"test"}, body=MagicMock())
        async def body(): return b"{}"
        request.body = body
        scope = functions("backend/routers/stripe_webhook.py", {"stripe_webhook"},
            settings=SimpleNamespace(STRIPE_WEBHOOK_SECRET="test"),
            stripe=SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda *args:event)),
            _claim=lambda *a:True, _as_dict=lambda x:x, _update_order=update,
            mark_webhook_processed=lambda *a:None, mark_webhook_failed=lambda *a:None,
            JSONResponse=lambda **kw:kw)
        return scope, request, update

    def test_completed_unpaid_does_not_fulfill(self):
        scope, request, update = self.handler("unpaid")
        asyncio.run(scope["stripe_webhook"](request))
        update.assert_not_called()

    def test_completed_paid_fulfills_with_provider_session(self):
        scope, request, update = self.handler("paid")
        asyncio.run(scope["stripe_webhook"](request))
        self.assertTrue(update.call_args.kwargs["paid"])
        self.assertEqual(update.call_args.kwargs["session"]["id"], "cs_test")

    def test_atomic_update_receives_exact_provider_amount_currency_and_id(self):
        db=MagicMock();db.rpc.return_value.execute.return_value.data=True
        scope=functions("backend/routers/stripe_webhook.py", {"_update_order"}, supabase=db, checkout_amount=checkout_amount)
        scope["_update_order"]("o", session={"id":"cs_test","amount_total":12345,"currency":"ils"}, order_status="paid", payment_status="succeeded", metadata_updates={}, paid=True)
        params=db.rpc.call_args.args[1]
        self.assertEqual((params["p_expected_amount"],params["p_expected_currency"],params["p_provider_session_id"]),("123.45","ILS","cs_test"))
        db.rpc.return_value.execute.return_value.data=False
        with self.assertRaises(RuntimeError):
            scope["_update_order"]("o",session={"id":"wrong","amount_total":12345,"currency":"ils"},order_status="paid",payment_status="succeeded",metadata_updates={},paid=True)


class MFATests(unittest.TestCase):
    def test_unsupported_toggle_cannot_mark_account_protected(self):
        db = MagicMock()
        scope = functions("backend/routers/profile.py", {"toggle_2fa"},
                          Depends=lambda x:None, get_current_user=lambda:None, supabase=db)
        with self.assertRaises(HTTPError) as error:
            asyncio.run(scope["toggle_2fa"](SimpleNamespace(user_id="u")))
        self.assertEqual(error.exception.status_code, 503)
        db.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
