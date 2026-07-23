"""Stripe Checkout service for one-time payments and subscriptions."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import stripe

from backend.config import settings


class StripeServiceError(RuntimeError):
    """Raised when Stripe cannot create or retrieve a payment."""


class StripeService:
    def _ensure_configured(self) -> None:
        secret_key = settings.STRIPE_SECRET_KEY
        if not secret_key or secret_key.startswith("sk_test_EXAMPLE"):
            raise StripeServiceError("STRIPE_SECRET_KEY is not configured")
        if stripe.api_key != secret_key:
            stripe.api_key = secret_key

    @staticmethod
    def _minor_units(amount: Decimal | int | float | str, currency: str) -> int:
        value = Decimal(str(amount))
        if value <= 0:
            raise ValueError("Amount must be greater than zero")
        zero_decimal = {
            "BIF",
            "CLP",
            "DJF",
            "GNF",
            "JPY",
            "KMF",
            "KRW",
            "MGA",
            "PYG",
            "RWF",
            "UGX",
            "VND",
            "VUV",
            "XAF",
            "XOF",
            "XPF",
        }
        factor = Decimal("1") if currency.upper() in zero_decimal else Decimal("100")
        return int((value * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _currency(currency: str) -> str:
        value = currency.lower()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code")
        return value

    @staticmethod
    def _success_url() -> str:
        url = settings.STRIPE_SUCCESS_URL
        if "{CHECKOUT_SESSION_ID}" in url:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}session_id={{CHECKOUT_SESSION_ID}}"

    @staticmethod
    def _cancel_url() -> str:
        return settings.STRIPE_CANCEL_URL

    @staticmethod
    def _serialize_session(session: Any) -> dict[str, Any]:
        return {
            "session_id": session.id,
            "url": session.url,
            "mode": session.mode,
            "payment_status": session.payment_status,
        }

    def create_checkout_session(
        self,
        *,
        amount: Decimal | int | float | str,
        product_name: str,
        currency: str = "ILS",
        mode: str = "payment",
        customer_email: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._ensure_configured()
        if mode not in {"payment", "subscription"}:
            raise ValueError("Mode must be payment or subscription")
        if not product_name.strip():
            raise ValueError("Product name is required")

        unit_amount = self._minor_units(amount, currency)
        price_data: dict[str, Any] = {
            "currency": self._currency(currency),
            "product_data": {"name": product_name.strip()},
            "unit_amount": unit_amount,
        }
        if mode == "subscription":
            price_data["recurring"] = {"interval": "month"}

        params: dict[str, Any] = {
            "mode": mode,
            "line_items": [{"price_data": price_data, "quantity": 1}],
            "success_url": self._success_url(),
            "cancel_url": self._cancel_url(),
            "metadata": metadata or {},
        }
        if customer_email:
            params["customer_email"] = customer_email
        if mode == "payment":
            params["payment_intent_data"] = {"metadata": metadata or {}}
        else:
            params["subscription_data"] = {"metadata": metadata or {}}

        try:
            session = stripe.checkout.Session.create(**params)
        except stripe.error.StripeError as exc:
            raise StripeServiceError("Stripe Checkout session creation failed") from exc
        return self._serialize_session(session)

    def create_checkout_session_with_price(
        self,
        *,
        price_id: str,
        mode: str,
        metadata: dict[str, str] | None = None,
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_configured()
        if not price_id.strip() or mode not in {"payment", "subscription"}:
            raise ValueError("Valid price_id and mode are required")

        params: dict[str, Any] = {
            "mode": mode,
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": self._success_url(),
            "cancel_url": self._cancel_url(),
            "metadata": metadata or {},
        }
        if customer_email:
            params["customer_email"] = customer_email
        if mode == "payment":
            params["payment_intent_data"] = {"metadata": metadata or {}}
        else:
            params["subscription_data"] = {"metadata": metadata or {}}

        try:
            session = stripe.checkout.Session.create(**params)
        except stripe.error.StripeError as exc:
            raise StripeServiceError("Stripe Checkout session creation failed") from exc
        return self._serialize_session(session)

    def retrieve_checkout_session(self, session_id: str) -> Any:
        self._ensure_configured()
        if not session_id:
            raise ValueError("session_id is required")
        try:
            return stripe.checkout.Session.retrieve(
                session_id,
                expand=["subscription", "payment_intent"],
            )
        except stripe.error.StripeError as exc:
            raise StripeServiceError("Stripe checkout session retrieval failed") from exc

    def retrieve_subscription(self, subscription_id: str) -> Any:
        self._ensure_configured()
        if not subscription_id:
            raise ValueError("subscription_id is required")
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as exc:
            raise StripeServiceError("Stripe subscription retrieval failed") from exc


stripe_service = StripeService()
