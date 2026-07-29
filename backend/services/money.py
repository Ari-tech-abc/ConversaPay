"""Exact monetary helpers for application and payment boundaries."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CENT = Decimal("0.01")

def money(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)

def multiply_money(value: Any, quantity: int) -> Decimal:
    return (money(value) * Decimal(quantity)).quantize(CENT, rounding=ROUND_HALF_UP)

def money_db(value: Any) -> str:
    return format(money(value), ".2f")
