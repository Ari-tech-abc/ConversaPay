"""Delivery contracts with an in-memory database and mocked HTTP transport."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
import unittest

import test_application_security  # Isolated environment; no real credentials.
import httpx
from backend.services.notification_service import NotificationWorker


class MemoryWorker(NotificationWorker):
    def __init__(self, preferences=None, verified=True):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"email_verified": verified, "notification_preferences": preferences or {}}]
        client.auth.admin.get_user_by_id.return_value = SimpleNamespace(user=SimpleNamespace(email="owner@example.com", email_confirmed_at="2026-01-01" if verified else None))
        super().__init__(client)
        self.changes = []
        self.state = {}
        self.lease = True

    def _update(self, row, changes):
        self.changes.append(changes.copy())
        if self.lease:
            self.state.update(changes)
        return SimpleNamespace(data=[self.state] if self.lease else [])


def event(**changes):
    return {"id": "notification-1", "user_id": "owner-id", "category": "payment_success", "attempts": 1, "first_attempt_at": datetime.now(timezone.utc).isoformat(), "payload": {"order_number": "ORD-1", "total": "249.00", "currency": "ILS"}, "message": None, **changes}


class NotificationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_acceptance_stores_receipt_and_immutable_message(self):
        worker = MemoryWorker(); requests = []
        def handler(request):
            requests.append(request)
            self.assertTrue(worker.state.get("message"))
            return httpx.Response(200, json={"id": "email-1"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            await worker.deliver(event(), transport)
        self.assertEqual(worker.state["status"], "sent")
        self.assertEqual(worker.state["provider_id"], "email-1")
        self.assertEqual(requests[0].headers["Idempotency-Key"], "notification/notification-1")

    async def test_timeout_retry_uses_exactly_the_same_message_and_key(self):
        worker = MemoryWorker(); requests = []
        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                raise httpx.ReadTimeout("Ambiguous provider result", request=request)
            return httpx.Response(200, json={"id": "email-1"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            first = event()
            await worker.deliver(first, transport)
            self.assertEqual(worker.state["status"], "pending")
            await worker.deliver(event(attempts=2, message=worker.state["message"], payload={"total": "CHANGED"}), transport)
        self.assertEqual(requests[0].content, requests[1].content)
        self.assertEqual(requests[0].headers["Idempotency-Key"], requests[1].headers["Idempotency-Key"])
        self.assertEqual(worker.state["status"], "sent")

    async def test_opt_out_and_unverified_user_never_call_provider(self):
        for worker in [MemoryWorker({"payment_success": False}), MemoryWorker(verified=False)]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Unexpected external send"))) as transport:
                await worker.deliver(event(), transport)
            self.assertEqual(worker.state["status"], "skipped")

    async def test_product_updates_require_explicit_opt_in(self):
        worker = MemoryWorker()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Unexpected promotional email"))) as transport:
            await worker.deliver(event(category="product_updates"), transport)
        self.assertEqual(worker.state["status"], "skipped")

    async def test_recipient_change_skips_old_snapshot(self):
        worker = MemoryWorker()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Email sent to old address"))) as transport:
            await worker.deliver(event(message={"to": ["old@example.com"]}), transport)
        self.assertEqual(worker.state["last_error"], "recipient_changed")

    async def test_expired_retry_window_never_resends_ambiguous_email(self):
        worker = MemoryWorker()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Expired resend"))) as transport:
            await worker.deliver(event(attempts=2, first_attempt_at=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()), transport)
        self.assertEqual(worker.state["status"], "failed")
        self.assertEqual(worker.state["last_error"], "retry_window_expired")

    async def test_lost_claim_does_not_send(self):
        worker = MemoryWorker(); worker.lease = False
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Stale worker sent email"))) as transport:
            await worker.deliver(event(), transport)
        self.assertNotIn("status", worker.state)

    async def test_permanent_provider_rejection_is_not_retried(self):
        worker = MemoryWorker()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(422, json={"message": "invalid sender"}))) as transport:
            await worker.deliver(event(), transport)
        self.assertEqual(worker.state["status"], "failed")
        self.assertEqual(worker.state["last_error"], "provider_422")

    async def test_weekly_scheduler_runs_once_per_week_and_claims_are_private(self):
        worker = MemoryWorker(); worker.client.rpc.return_value.execute.return_value.data = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Empty queue sent email"))) as transport:
            await worker.run_once(transport); await worker.run_once(transport)
        calls = worker.client.rpc.call_args_list
        self.assertEqual(sum(call.args[0] == "enqueue_weekly_digests" for call in calls), 1)
        self.assertEqual(sum(call.args[0] == "claim_notifications" for call in calls), 2)

    async def test_worker_starts_after_migrations_and_is_cancelled_at_shutdown(self):
        import main
        started, stopped = asyncio.Event(), asyncio.Event()
        async def run():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        worker = SimpleNamespace(run=run)
        with patch.object(main, 'apply_migrations', new=AsyncMock()), patch.object(main.monitoring_service, 'initialize'), patch.object(main, 'initialize_error_tracking'), patch('backend.services.notification_service.delivery_configured', return_value=True), patch('backend.services.notification_service.NotificationWorker', return_value=worker):
            async with main.lifespan(main.app):
                await asyncio.wait_for(started.wait(), timeout=1)
                main.apply_migrations.assert_awaited_once()
            self.assertTrue(stopped.is_set())


if __name__ == '__main__':
    unittest.main()
