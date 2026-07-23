"""Cardcom v11 Low Profile payment service."""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

import httpx


class CardcomError(RuntimeError):
    """Raised when Cardcom rejects a request or returns an invalid response."""


class CardcomService:
    def __init__(self) -> None:
        self.terminal_number = int(os.getenv("CARDCOM_TERMINAL_NUMBER", "1000"))
        self.user_name = os.getenv("CARDCOM_USER_NAME", "Cardcomtest26")
        self.base_url = os.getenv("CARDCOM_BASE_URL", "https://cardcom.solutions").rstrip("/")
        self.api_token = os.getenv("CARDCOM_API_TOKEN")
        self.create_path = os.getenv("CARDCOM_LOW_PROFILE_CREATE_PATH", "/api/v11/LowProfile/Create")
        self.get_path = os.getenv("CARDCOM_LOW_PROFILE_GET_PATH", "/api/v11/LowProfile/Get")
        self.indicator_url = os.getenv("CARDCOM_INDICATOR_URL", "https://conversapay.org/api/v1/webhooks/cardcom")
        self.success_url = os.getenv("CARDCOM_SUCCESS_URL", "https://conversapay.org/pay.html?status=success")
        self.failure_url = os.getenv("CARDCOM_FAILURE_URL", "https://conversapay.org/pay.html?status=failed")
        self.cancel_url = os.getenv("CARDCOM_CANCEL_URL", "https://conversapay.org/pay.html?status=canceled")
        self.timeout = float(os.getenv("CARDCOM_TIMEOUT_SECONDS", "30"))

    @staticmethod
    def _agorot(amount: Decimal | int | float | str) -> int:
        value = Decimal(str(amount))
        if value <= 0:
            raise ValueError("Amount must be greater than zero")
        return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_token and self.api_token != "YOUR_TOKEN_HERE":
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/{path.lstrip('/')}", json=dict(payload), headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise CardcomError("Cardcom request failed") from exc
        except ValueError as exc:
            raise CardcomError("Cardcom returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise CardcomError("Unexpected Cardcom response")
        return data

    @staticmethod
    def _code(data: Mapping[str, Any]) -> str | None:
        value = data.get("ResponseCode", data.get("responseCode"))
        return None if value is None else str(value)

    @staticmethod
    def _value(data: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            if data.get(key) not in (None, ""):
                return data[key]
        return None

    async def create_payment_page(
        self,
        amount: Decimal | int | float | str,
        product_name: str,
        currency: str = "ILS",
        return_value: str | None = None,
    ) -> str:
        currency = currency.upper()
        if currency not in {"ILS", "USD", "EUR"}:
            raise ValueError(f"Unsupported currency: {currency}")
        if not product_name.strip():
            raise ValueError("Product name is required")
        payload: dict[str, Any] = {
            "TerminalNumber": self.terminal_number,
            "UserName": self.user_name,
            "Amount": self._agorot(amount),
            "Currency": currency,
            "ProductName": product_name.strip(),
            "IndicatorUrl": self.indicator_url,
            "SuccessUrl": self.success_url,
            "ErrorUrl": self.failure_url,
            "CancelUrl": self.cancel_url,
        }
        if return_value:
            payload["ReturnValue"] = return_value
        data = await self._post(self.create_path, payload)
        if self._code(data) not in {None, "", "0"}:
            raise CardcomError(str(self._value(data, "Description", "description", "ErrorMessage") or data))
        url = self._value(data, "url", "Url", "PaymentUrl", "paymentUrl", "LowProfileUrl", "lowProfileUrl")
        if not url:
            raise CardcomError("Cardcom did not return a payment URL")
        return str(url)

    async def verify_transaction(self, low_profile_code: str) -> dict[str, Any]:
        if not low_profile_code.strip():
            raise ValueError("LowProfileCode is required")
        data = await self._post(self.get_path, {"TerminalNumber": self.terminal_number, "UserName": self.user_name, "LowProfileCode": low_profile_code.strip()})
        return {
            "verified": self._code(data) == "0",
            "response_code": self._code(data),
            "transaction_id": self._value(data, "InternalDealNumber", "internalDealNumber", "DealNumber", "dealNumber", "TransactionId", "transactionId"),
            "amount": self._value(data, "Amount", "amount", "Sum", "sum"),
            "currency": self._value(data, "Currency", "currency"),
            "raw": data,
        }


cardcom_service = CardcomService()
