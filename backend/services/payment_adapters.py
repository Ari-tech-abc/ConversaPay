"""Unified checkout adapters for provider-independent order payments."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

from backend.config import settings
from backend.services.stripe_service import stripe_service

logger = logging.getLogger(__name__)


class PaymentAdapterError(RuntimeError):
    """Raised when a checkout provider cannot create a hosted payment page."""


@dataclass(frozen=True)
class CheckoutOrder:
    order_id: str
    order_number: str
    amount: Decimal
    currency: str
    items: list[dict[str, Any]] = field(default_factory=list)
    customer_email: str | None = None
    customer_name: str | None = None
    success_url: str | None = None
    cancel_url: str | None = None
    callback_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckoutResult:
    provider: str
    checkout_url: str
    provider_session_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class CheckoutAdapter(Protocol):
    provider: str

    async def create_checkout(self, order: CheckoutOrder) -> CheckoutResult:
        """Create a hosted checkout page for an order."""


def _minor_units(amount: Decimal, currency: str) -> int:
    if amount <= 0:
        raise ValueError("Checkout amount must be greater than zero")
    zero_decimal = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
    factor = Decimal("1") if currency.upper() in zero_decimal else Decimal("100")
    return int((amount * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _customer_name_parts(value: str | None) -> tuple[str, str]:
    parts = [part for part in (value or "").strip().split() if part]
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


class StripeCheckoutAdapter:
    provider = "stripe"

    async def create_checkout(self, order: CheckoutOrder) -> CheckoutResult:
        product_name = " / ".join(str(item.get("name") or item.get("item_key") or "Item") for item in order.items) or order.order_number
        metadata = {"order_id": order.order_id, "order_number": order.order_number, **order.metadata}
        try:
            session = await asyncio.to_thread(
                stripe_service.create_checkout_session,
                amount=order.amount,
                product_name=product_name[:250],
                currency=order.currency,
                mode="payment",
                customer_email=order.customer_email,
                metadata=metadata,
            )
        except Exception as exc:
            raise PaymentAdapterError(f"Stripe checkout creation failed: {exc}") from exc
        checkout_url = str(session.get("url") or "").strip()
        if not checkout_url:
            raise PaymentAdapterError("Stripe did not return a checkout URL")
        return CheckoutResult(provider=self.provider, checkout_url=checkout_url, provider_session_id=session.get("session_id"), raw=session)


class PayMeCheckoutAdapter:
    provider = "payme"

    def __init__(self) -> None:
        self.base_url = (settings.PAYME_API_BASE_URL or "https://sandbox.payme.io").rstrip("/")
        self.generate_path = settings.PAYME_GENERATE_PATH or "/api/generate-sale"

    def _payload(self, order: CheckoutOrder) -> dict[str, Any]:
        currency = str(order.currency or "ILS").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code")
        client_key = (settings.PAYME_CLIENT_KEY or "").strip()
        seller_id = (settings.PAYME_SELLER_PAYME_ID or "").strip()
        if not client_key or not seller_id:
            raise PaymentAdapterError("PayMe credentials are not configured")

        first_name, last_name = _customer_name_parts(order.customer_name)
        item_lines = []
        item_keys = []
        for item in order.items:
            item_key = str(item.get("item_key") or "").strip()
            if item_key:
                item_keys.append(item_key)
            name = str(item.get("name") or item_key or "Item").strip()
            quantity = int(item.get("quantity") or 1)
            price = Decimal(str(item.get("price") or "0"))
            item_lines.append(f"{item_key or name} x{quantity} ({price} {currency})")

        description = f"Order {order.order_number}; items: " + "; ".join(item_lines)
        product_name = " / ".join(str(item.get("name") or item.get("item_key") or "Item") for item in order.items) or order.order_number
        amount_minor = _minor_units(Decimal(str(order.amount)), currency)
        payload: dict[str, Any] = {
            "payme_client_key": client_key,
            "seller_payme_id": seller_id,
            "sale_price": amount_minor,
            "sale_currency": currency,
            "sale_description": description[:1000],
            "sale_product_name": product_name[:255],
            "sale_product_id": ",".join(item_keys)[:255],
            "sale_product_price": amount_minor,
            "sale_product_quantity": 1,
            "sale_first_name": first_name,
            "sale_last_name": last_name,
            "sale_email": order.customer_email or "",
            "sale_return_url": order.success_url or settings.PAYME_SUCCESS_URL or f"{settings.BASE_URL.rstrip('/')}/payment/success?provider=payme&order_id={order.order_id}",
            "sale_cancel_url": order.cancel_url or settings.PAYME_CANCEL_URL or f"{settings.BASE_URL.rstrip('/')}/payment/canceled?provider=payme&order_id={order.order_id}",
        }
        callback_url = order.callback_url or settings.PAYME_CALLBACK_URL
        if callback_url:
            payload["sale_callback_url"] = callback_url
        return payload

    @staticmethod
    def _extract_url(data: dict[str, Any]) -> tuple[str | None, str | None]:
        for key in ("payment_url", "sale_url", "redirect_url", "url", "paymentUrl", "saleUrl"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), str(data.get("sale_id") or data.get("id") or "") or None
        nested = data.get("data")
        if isinstance(nested, dict):
            return PayMeCheckoutAdapter._extract_url(nested)
        return None, None

    async def create_checkout(self, order: CheckoutOrder) -> CheckoutResult:
        endpoint = urljoin(f"{self.base_url}/", self.generate_path.lstrip("/"))
        payload = self._payload(order)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(endpoint, json=payload, headers={"Accept": "application/json", "Content-Type": "application/json"})
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error("PayMe checkout request failed for order %s: %s", order.order_id, exc, exc_info=True)
            raise PaymentAdapterError("PayMe checkout request failed") from exc
        except ValueError as exc:
            raise PaymentAdapterError("PayMe returned an invalid checkout response") from exc

        if not isinstance(data, dict):
            raise PaymentAdapterError("PayMe returned an invalid checkout response")
        checkout_url, sale_id = self._extract_url(data)
        if not checkout_url:
            message = data.get("message") or data.get("error") or "PayMe did not return a checkout URL"
            raise PaymentAdapterError(str(message))
        return CheckoutResult(provider=self.provider, checkout_url=checkout_url, provider_session_id=sale_id, raw=data)


def get_checkout_adapter(provider: str | None = None) -> CheckoutAdapter:
    selected = (provider or settings.PAYMENT_PROVIDER or "stripe").strip().lower()
    if selected == "stripe":
        return StripeCheckoutAdapter()
    if selected in {"payme", "payme_il"}:
        return PayMeCheckoutAdapter()
    raise PaymentAdapterError(f"Unsupported payment provider: {selected}")
