"""Stripe Checkout service for one-time payments and subscriptions."""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import stripe

from backend.config import settings

logger = logging.getLogger(__name__)
STRIPE_KEY_MISSING_MESSAGE = "Stripe secret key is missing"
PLACEHOLDER_SECRET_KEY_PREFIX = "sk_test_EXAMPLE"


class StripeServiceError(RuntimeError):
    """Raised when Stripe cannot create or retrieve a payment."""


def describe_stripe_error(exc: BaseException) -> str:
    if not isinstance(exc, stripe.error.StripeError):
        return f"{type(exc).__name__}: {exc}"
    body = getattr(exc, "json_body", None)
    error = body.get("error") if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {}
    message = error.get("message") or getattr(exc, "user_message", None) or str(exc)
    fields = {"error_type": error.get("type") or type(exc).__name__, "code": error.get("code") or getattr(exc, "code", None), "param": error.get("param"), "http_status": getattr(exc, "http_status", None), "request_id": getattr(exc, "request_id", None)}
    described = ", ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    return f"{message} ({described})" if described else str(message)


class StripeService:
    def _ensure_configured(self) -> None:
        secret_key = (settings.STRIPE_SECRET_KEY or "").strip()
        if not secret_key or secret_key.startswith(PLACEHOLDER_SECRET_KEY_PREFIX):
            logger.error("%s: STRIPE_SECRET_KEY is unset or still a placeholder (value not logged).", STRIPE_KEY_MISSING_MESSAGE)
            raise StripeServiceError(STRIPE_KEY_MISSING_MESSAGE)
        if stripe.api_key != secret_key:
            stripe.api_key = secret_key

    @staticmethod
    def serialize_stripe_object(obj: Any) -> Any:
        if obj is None or isinstance(obj, (dict, list, str, int, float, bool)):
            return obj
        if hasattr(obj, "to_dict_recursive"):
            return obj.to_dict_recursive()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return obj

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
        value = currency.lower().strip()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code")
        return value

    @staticmethod
    def _success_url() -> str:
        configured = (settings.STRIPE_SUCCESS_URL or "").strip()
        url = configured if configured and configured.rstrip("/") not in {"https://conversapay.org", "https://www.conversapay.org"} else f"{settings.BASE_URL.rstrip('/')}/payment/success"
        if "{CHECKOUT_SESSION_ID}" in url:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}session_id={{CHECKOUT_SESSION_ID}}"

    @staticmethod
    def _cancel_url() -> str:
        configured = (settings.STRIPE_CANCEL_URL or "").strip()
        return configured if configured and configured.rstrip("/") not in {"https://conversapay.org", "https://www.conversapay.org"} else f"{settings.BASE_URL.rstrip('/')}/payment/canceled"

    @staticmethod
    def _serialize_session(session: Any) -> dict[str, Any]:
        return {"session_id": session.id, "url": session.url, "mode": session.mode, "payment_status": session.payment_status}

    @staticmethod
    def _metadata(metadata: dict[str, str] | None, *, subscription: bool = False) -> dict[str, str]:
        values = {str(key): str(value) for key, value in (metadata or {}).items() if value is not None}
        if subscription:
            if not values.get("user_id") or not values.get("plan_type"):
                raise ValueError("Subscription checkout requires metadata user_id and plan_type")
            # Keep these keys explicit on the Stripe Subscription, not only on Checkout Session.
            values["user_id"] = values["user_id"]
            values["plan_type"] = values["plan_type"]
        return values

    def _create_session(self, params: dict[str, Any], *, context: str) -> Any:
        try:
            return stripe.checkout.Session.create(**params)
        except stripe.error.StripeError as exc:
            reason = describe_stripe_error(exc)
            logger.error("Stripe rejected checkout session creation (%s): %s", context, reason, exc_info=True)
            raise StripeServiceError(f"Stripe Checkout session creation failed: {reason}") from exc
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            logger.error("Unexpected error during checkout session creation (%s): %s", context, reason, exc_info=True)
            raise StripeServiceError(f"Stripe Checkout session creation failed: {reason}") from exc

    def create_checkout_session(self, *, amount: Decimal | int | float | str, product_name: str, currency: str = "ILS", mode: str = "payment", customer_email: str | None = None, metadata: dict[str, str] | None = None) -> dict[str, Any]:
        self._ensure_configured()
        if mode not in {"payment", "subscription"}:
            raise ValueError("Mode must be payment or subscription")
        if not product_name.strip():
            raise ValueError("Product name is required")
        metadata_values = self._metadata(metadata, subscription=mode == "subscription")
        unit_amount = self._minor_units(amount, currency)
        price_data: dict[str, Any] = {"currency": self._currency(currency), "product_data": {"name": product_name.strip()}, "unit_amount": unit_amount}
        if mode == "subscription":
            price_data["recurring"] = {"interval": "month"}
        params: dict[str, Any] = {"mode": mode, "line_items": [{"price_data": price_data, "quantity": 1}], "success_url": self._success_url(), "cancel_url": self._cancel_url(), "metadata": metadata_values}
        if customer_email:
            params["customer_email"] = customer_email
        if mode == "payment":
            params["payment_intent_data"] = {"metadata": metadata_values}
        else:
            params["subscription_data"] = {"metadata": {"user_id": metadata_values["user_id"], "plan_type": metadata_values["plan_type"]}}
        session = self._create_session(params, context=f"mode={mode} price=inline_price_data currency={currency}")
        return self._serialize_session(session)

    def create_checkout_session_with_price(self, *, price_id: str, mode: str, metadata: dict[str, str] | None = None, customer_email: str | None = None) -> dict[str, Any]:
        self._ensure_configured()
        if not price_id.strip() or mode not in {"payment", "subscription"}:
            raise ValueError("Valid price_id and mode are required")
        metadata_values = self._metadata(metadata, subscription=mode == "subscription")
        params: dict[str, Any] = {"mode": mode, "line_items": [{"price": price_id, "quantity": 1}], "success_url": self._success_url(), "cancel_url": self._cancel_url(), "metadata": metadata_values}
        if customer_email:
            params["customer_email"] = customer_email
        if mode == "payment":
            params["payment_intent_data"] = {"metadata": metadata_values}
        else:
            params["subscription_data"] = {"metadata": {"user_id": metadata_values["user_id"], "plan_type": metadata_values["plan_type"]}}
        session = self._create_session(params, context=f"mode={mode} price_id={price_id}")
        return self._serialize_session(session)

    def retrieve_checkout_session(self, session_id: str) -> dict[str, Any]:
        self._ensure_configured()
        if not session_id:
            raise ValueError("session_id is required")
        try:
            session = stripe.checkout.Session.retrieve(session_id, expand=["subscription", "payment_intent"])
        except stripe.error.StripeError as exc:
            logger.error("Stripe checkout session retrieval failed (session_id=%s): %s", session_id, describe_stripe_error(exc), exc_info=True)
            raise StripeServiceError("Stripe checkout session retrieval failed") from exc
        return self.serialize_stripe_object(session)

    def retrieve_subscription(self, subscription_id: str) -> dict[str, Any]:
        self._ensure_configured()
        if not subscription_id:
            raise ValueError("subscription_id is required")
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as exc:
            logger.error("Stripe subscription retrieval failed (subscription_id=%s): %s", subscription_id, describe_stripe_error(exc), exc_info=True)
            raise StripeServiceError("Stripe subscription retrieval failed") from exc
        return self.serialize_stripe_object(subscription)


stripe_service = StripeService()
