"""Removed: Stripe is now the sole test/development payment provider."""
from fastapi import APIRouter
router = APIRouter(prefix="/webhooks/cardcom", tags=["deprecated-cardcom"])
