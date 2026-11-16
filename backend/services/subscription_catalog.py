"""Server-owned monthly subscription catalog, separate from merchant orders."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SubscriptionPlan:
    key: str
    amount_minor: int
    currency: str = "ILS"
    interval: str = "month"

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_minor) / 100


PLANS = {"pro": SubscriptionPlan("pro", 20000), "premium": SubscriptionPlan("premium", 35000)}


def subscription_plan(key: str) -> SubscriptionPlan:
    try:
        return PLANS[key.strip().lower()]
    except (KeyError, AttributeError):
        raise ValueError("Only PRO and PREMIUM can be purchased") from None


def paid_subscription_period(subscription: dict, plan: SubscriptionPlan) -> tuple[int, int] | None:
    """Find the paid service period, not merely the provider's current period."""
    invoice = subscription.get("latest_invoice")
    if not (isinstance(invoice, dict) and invoice.get("status") == "paid"
            and type(invoice.get("amount_paid")) is int and invoice["amount_paid"] == plan.amount_minor
            and str(invoice.get("currency") or "").upper() == plan.currency):
        return None
    periods = []
    for line in (invoice.get("lines") or {}).get("data", []):
        parent = (line.get("parent") or {}).get("subscription_item_details") or {}
        owner = line.get("subscription") or parent.get("subscription")
        period = line.get("period") or {}
        start, end = period.get("start"), period.get("end")
        if (owner == subscription.get("id") and not line.get("proration", parent.get("proration", False))
                and line.get("amount") == plan.amount_minor and str(line.get("currency") or "").upper() == plan.currency
                and type(start) is int and type(end) is int and 0 < start < end):
            periods.append((start, end))
    return min(periods, key=lambda period: period[1]) if periods else None


def invoice_confirms_subscription(subscription: dict, plan: SubscriptionPlan) -> bool:
    return paid_subscription_period(subscription, plan) is not None
