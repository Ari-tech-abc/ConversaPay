"""Encryption and redaction helpers for WhatsApp credentials."""
from __future__ import annotations
import base64
import hashlib
import hmac
from typing import Any
from cryptography.fernet import Fernet, InvalidToken
from backend.config import settings

_SECRET_FIELDS = {
    "whatsapp_access_token",
    "whatsapp_verify_token",
    "whatsapp_access_token_encrypted",
    "whatsapp_verify_token_encrypted",
    "whatsapp_verify_token_hash",
}

def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)

def encrypt_secret(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None
    return _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")

def decrypt_secret(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None
    try:
        return _fernet().decrypt(str(value).encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        return None

def secret_hash(value: Any) -> str | None:
    if value is None or str(value) == "":
        return None
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), str(value).encode("utf-8"), hashlib.sha256).hexdigest()

def redact_profile(profile: dict | None) -> dict | None:
    if profile is None:
        return None
    return {key: value for key, value in profile.items() if key not in _SECRET_FIELDS}

def secure_get_user_profile(original_get, original_update, user_id: str) -> dict | None:
    profile = original_get(user_id)
    if not profile:
        return None
    legacy_access = profile.get("whatsapp_access_token")
    legacy_verify = profile.get("whatsapp_verify_token")
    if legacy_access or legacy_verify:
        encrypted = {
            "whatsapp_access_token_encrypted": encrypt_secret(legacy_access),
            "whatsapp_verify_token_encrypted": encrypt_secret(legacy_verify),
            "whatsapp_verify_token_hash": secret_hash(legacy_verify),
            "whatsapp_access_token": None,
            "whatsapp_verify_token": None,
        }
        try:
            original_update(user_id, encrypted)
        except Exception:
            pass
    return redact_profile(profile)

def secure_update_profile_row(original_update, user_id: str, changes: dict, select_fields: str = "*") -> dict | None:
    payload = dict(changes)
    access = payload.pop("whatsapp_access_token", None)
    verify = payload.pop("whatsapp_verify_token", None)
    if access is not None:
        payload["whatsapp_access_token_encrypted"] = encrypt_secret(access)
        payload["whatsapp_access_token"] = None
    if verify is not None:
        payload["whatsapp_verify_token_encrypted"] = encrypt_secret(verify)
        payload["whatsapp_verify_token_hash"] = secret_hash(verify)
        payload["whatsapp_verify_token"] = None
    result = original_update(user_id, payload, select_fields)
    return redact_profile(result)
