"""Durable Resend delivery with immutable messages and preference checks."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from supabase import create_client
from backend.config import settings
from backend.services.notification_templates import render_notification

logger = logging.getLogger(__name__)
DEFAULTS = {"payment_success": True, "weekly_digest": True, "security_alerts": True, "product_updates": False}
_runtime = {"running": False, "ready": False}


def delivery_configured() -> bool:
    return bool(settings.NOTIFICATION_EMAILS_ENABLED and settings.RESEND_API_KEY and settings.EMAIL_FROM_ADDRESS)


def delivery_status() -> dict:
    enabled = delivery_configured() and _runtime["running"] and _runtime["ready"]
    return {"enabled": enabled, "reason": None if enabled else "delivery_not_ready"}


class NotificationWorker:
    def __init__(self, client=None):
        self.client = client or create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        self.last_week = None

    def _update(self, row, changes):
        return self.client.table("notification_outbox").update(changes).eq("id", row["id"]).eq("attempts", row["attempts"]).eq("status", "sending").execute()

    async def deliver(self, row, transport: httpx.AsyncClient):
        try:
            profiles = await asyncio.to_thread(lambda: self.client.table("profiles").select("notification_preferences,email_verified").eq("user_id", row["user_id"]).limit(1).execute())
            profile = (profiles.data or [None])[0]
            prefs = {**DEFAULTS, **((profile or {}).get("notification_preferences") or {})}
            if not profile or not profile.get("email_verified") or prefs.get(row["category"]) is not True:
                await asyncio.to_thread(self._update, row, {"status": "skipped"})
                return
            user_response = await asyncio.to_thread(self.client.auth.admin.get_user_by_id, row["user_id"])
            user = user_response.user
            if not user or not user.email or not user.email_confirmed_at:
                await asyncio.to_thread(self._update, row, {"status": "skipped"})
                return
            # Stop ambiguous retries before the provider's 24-hour key expiry.
            first_attempt = datetime.fromisoformat(str(row["first_attempt_at"]).replace("Z", "+00:00"))
            if row["attempts"] > 1 and (datetime.now(timezone.utc) - first_attempt).total_seconds() >= 23 * 3600:
                await asyncio.to_thread(self._update, row, {"status": "failed", "last_error": "retry_window_expired"})
                return
            message = row.get("message")
            if message and message.get("to") != [user.email]:
                await asyncio.to_thread(self._update, row, {"status": "skipped", "last_error": "recipient_changed"})
                return
            if not message:
                subject, text, html = render_notification(row["category"], row["payload"], settings.FRONTEND_URL)
                message = {"from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>", "to": [user.email], "subject": subject, "text": text, "html": html}
                saved = await asyncio.to_thread(self._update, row, {"message": message})
                if not saved.data:
                    return
            response = await transport.post("https://api.resend.com/emails", headers={"Authorization": "Bearer " + settings.RESEND_API_KEY, "Idempotency-Key": "notification/" + str(row["id"])}, json=message)
            response.raise_for_status()
            provider_id = response.json().get("id")
            if not provider_id:
                raise ValueError("Missing provider message ID")
            await asyncio.to_thread(self._update, row, {"status": "sent", "provider_id": provider_id, "sent_at": datetime.now(timezone.utc).isoformat(), "last_error": None})
        except Exception as exc:
            # Log identifiers and error classes, never message bodies or tokens.
            logger.warning("Notification %s delivery failed (%s)", row["id"], type(exc).__name__)
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            permanent = status in {400, 404, 409, 422}
            failed = permanent or row["attempts"] >= 8
            delay = min(3600, 60 * 2 ** row["attempts"])
            await asyncio.to_thread(self._update, row, {"status": "failed" if failed else "pending", "last_error": f"provider_{status}" if status else type(exc).__name__, "available_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()})
            if status in {401, 403}:
                raise RuntimeError("Notification provider configuration is unavailable") from None

    async def run_once(self, transport):
        week = datetime.now(timezone.utc).strftime("%G-%V")
        if week != self.last_week:
            await asyncio.to_thread(lambda: self.client.rpc("enqueue_weekly_digests", {}).execute())
            self.last_week = week
        claimed = await asyncio.to_thread(lambda: self.client.rpc("claim_notifications", {"p_limit": 1}).execute())
        for row in claimed.data or []:
            await self.deliver(row, transport)
        return bool(claimed.data)

    async def run(self):
        _runtime.update(running=True, ready=False)
        try:
            async with httpx.AsyncClient(timeout=20) as transport:
                while True:
                    delay = 30
                    try:
                        has_work = await self.run_once(transport)
                        _runtime["ready"] = True
                        if has_work:
                            delay = 0.6
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        _runtime["ready"] = False
                        logger.error("Notification worker unavailable (%s)", type(exc).__name__)
                    await asyncio.sleep(delay)
        finally:
            _runtime.update(running=False, ready=False)


def enqueue_security_event(client, user_id: str, action: str):
    """Provider session revocation has no public row trigger."""
    try:
        client.rpc("enqueue_notification", {"p_user_id": user_id, "p_category": "security_alerts", "p_event_key": action + ":" + str(uuid4()), "p_payload": {"action": action, "occurred_at": datetime.now(timezone.utc).isoformat()}}).execute()
    except Exception as exc:
        logger.error("Security notification could not be queued for %s (%s)", user_id, type(exc).__name__)
