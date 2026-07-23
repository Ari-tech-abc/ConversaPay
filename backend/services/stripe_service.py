"""Stripe Checkout service for one-time payments and subscriptions."""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import stripe


class StripeServiceError(RuntimeError):
    """Raised when Stripe cannot create or retrieve a payment."""


class StripeService:
    def __init__(self) -> None:
        self.secret_key = os.getenv("STRIPE_SECRET_KEY")
        if not self.secret_key or self.secret_key.startswith("sk_test_EXAMPLE"):
            raise StripeServiceError("STRIPE_SECRET_KEY is not configured")
        stripe.api_key = self.secret_key
        self.success_url = os.getenv("STRIPE_SUCCESS_URL", "https://conversapay.org")
        self.cancel_url = os.getenv("STRIPE_CANCEL_URL", "https://conversapay.org")

    @staticmethod
    def _minor_units(amount: Decimal | int | float | str, currency: str) -> int:
        value = Decimal(str(amount))
        if value <= 0:
            raise ValueError("Amount must be greater than zero")
        zero_decimal = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
        factor = Decimal("1") if currency.upper() in zero_decimal else Decimal("100")
        return int((value * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _currency(currency: str) -> str:
        value = currency.lower()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code")
        return value

    def create_checkout_session(self, *, amount: Decimal | int | float | str, product_name: str, currency: str = "ILS", mode: str = "payment", customer_email: str | None = None, metadata: dict[str, str] | None = None) -> dict[str, Any]:
        if mode not in {"payment", "subscription"}:
            raise ValueError("Mode must be payment or subscription")
        if not product_name.strip():
            raise ValueError("Product name is required")
        unit_amount = self._minor_units(amount, currency)
        params: dict[str, Any] = {
            "mode": mode,
            "line_items": [{"price_data": {"currency": self._currency(currency), "product_data": {"name": product_name.strip()}, "unit_amount": unit_amount}, "quantity": 1}],
            "success_url": self.success_url,
            "cancel_url": self.cancel_url,
            "metadata": metadata or {},
        }
        if customer_email:
            params["customer_email"] = customer_email
        try:
            session = stripe.checkout.Session.create(**params)
        except stripe.error.StripeError as exc:
            raise StripeServiceError("Stripe Checkout session creation failed") from exc
        return {"id": session.id, "url": session.url, "mode": session.mode, "payment_status": session.payment_status}

    def create_checkout_session_with_price(self, *, price_id: str, mode: str, metadata: dict[str, str] | None = None, customer_email: str | None = None) -> dict[str, Any]:
        if not price_id.strip() or mode not in {"payment", "subscription"}:
            raise ValueError("Valid price_id and mode are required")
        params: dict[str, Any] = {"mode": mode, "line_items": [{"price": price_id, "quantity": 1}], "success_url": self.success_url, "cancel_url": self.cancel_url, "metadata": metadata or {}}
        if customer_email:
            params["customer_email"] = customer_email
        try:
            session = stripe.checkout.Session.create(**params)
        except stripe.error.StripeError as exc:
            raise StripeServiceError("Stripe Checkout session creation failed") from exc
        return {"id": session.id, "url": session.url, "mode": session.mode, "payment_status": session.payment_status}


stripe_service = StripeService()
