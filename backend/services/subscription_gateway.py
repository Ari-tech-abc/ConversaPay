"""Subscription gateway boundary. An unconfigured provider never falls back."""
from __future__ import annotations

from typing import Protocol, Any
import stripe

from backend.config import settings
from backend.services.stripe_service import stripe_service, StripeServiceError, PLACEHOLDER_SECRET_KEY_PREFIX
from backend.services.subscription_catalog import SubscriptionPlan


class SubscriptionGatewayUnavailable(RuntimeError):
    pass


class SubscriptionGateway(Protocol):
    provider: str
    def ensure_ready(self) -> None: ...
    def create_checkout(self, plan: SubscriptionPlan, user_id: str, email: str, attempt_id: str) -> dict[str, Any]: ...
    def retrieve_checkout(self, session_id: str) -> dict[str, Any]: ...
    def retrieve_subscription(self, subscription_id: str) -> dict[str, Any]: ...
    def cancel_renewal(self, subscription_id: str, request_id: str) -> dict[str, Any]: ...


class StripeSubscriptionGateway:
    provider = "stripe"

    def ensure_ready(self) -> None:
        key = (settings.STRIPE_SECRET_KEY or "").strip()
        if not key or key.startswith(PLACEHOLDER_SECRET_KEY_PREFIX):
            raise SubscriptionGatewayUnavailable("billing_provider_unavailable")

    def create_checkout(self, plan: SubscriptionPlan, user_id: str, email: str, attempt_id: str) -> dict[str, Any]:
        self.ensure_ready()
        metadata = {"user_id": user_id, "plan_type": plan.key, "checkout_attempt_id": attempt_id}
        price_id = settings.STRIPE_PRO_PRICE_ID if plan.key == "pro" else settings.STRIPE_PREMIUM_PRICE_ID
        options = dict(mode="subscription", customer_email=email, metadata=metadata, idempotency_key=f"subscription-checkout:{attempt_id}")
        if price_id:
            return stripe_service.create_checkout_session_with_price(price_id=price_id, expected_unit_amount=plan.amount_minor, **options)
        return stripe_service.create_checkout_session(amount=plan.amount, product_name=f"Talk2Pay {plan.key.upper()}", currency=plan.currency, **options)

    def retrieve_checkout(self, session_id: str) -> dict[str, Any]:
        self.ensure_ready()
        return stripe_service.retrieve_checkout_session(session_id)

    def retrieve_subscription(self, subscription_id: str) -> dict[str, Any]:
        self.ensure_ready()
        return stripe_service.retrieve_subscription(subscription_id)

    def cancel_renewal(self, subscription_id: str, request_id: str) -> dict[str, Any]:
        self.ensure_ready()
        stripe_service._ensure_configured()
        result = stripe.Subscription.modify(subscription_id, cancel_at_period_end=True, idempotency_key=f"subscription-cancel:{request_id}")
        result = stripe_service.serialize_stripe_object(result)
        if result.get("id") != subscription_id or not (result.get("cancel_at_period_end") is True or result.get("status") == "canceled"):
            raise StripeServiceError("Cancellation was not confirmed")
        return result


def get_subscription_gateway(provider: str | None = None) -> SubscriptionGateway:
    selected = (provider or settings.SUBSCRIPTION_PROVIDER).strip().lower()
    if selected == "stripe":
        return StripeSubscriptionGateway()
    # Isracard's exact terminal/API must be confirmed. Do not invent a charge API,
    # use a test terminal in production, or silently bill through another provider.
    raise SubscriptionGatewayUnavailable("billing_provider_unavailable")
