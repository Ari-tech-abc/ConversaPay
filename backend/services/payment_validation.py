"""Validate provider amounts before changing an order's payment state."""
from decimal import Decimal

ZERO_DECIMAL_CURRENCIES = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}


def checkout_amount(session: dict) -> tuple[str, str]:
    amount = session.get("amount_total")
    currency = str(session.get("currency") or "").upper()
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("Provider checkout has no positive integer amount_total")
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError("Provider checkout has no valid currency")
    factor = Decimal(1) if currency in ZERO_DECIMAL_CURRENCIES else Decimal(100)
    return str(Decimal(amount) / factor), currency
