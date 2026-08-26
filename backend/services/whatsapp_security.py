"""Versioned encryption and redaction helpers for WhatsApp credentials."""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
from typing import Any
from cryptography.fernet import Fernet, InvalidToken
from backend.config import settings

_SECRET_FIELDS = {"whatsapp_access_token","whatsapp_verify_token","whatsapp_access_token_encrypted","whatsapp_verify_token_encrypted","whatsapp_verify_token_hash"}
_CURRENT_VERSION = "v2"

def _key_materials() -> list[tuple[str, str]]:
    current = os.getenv("SECRET_KEY_CURRENT") or settings.SECRET_KEY
    previous = os.getenv("SECRET_KEY_PREVIOUS", "")
    keys = [("v2", current)]
    if previous and previous != current:
        keys.append(("v1", previous))
    return keys

def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)

def encrypt_secret(value: Any) -> str | None:
    if value is None or str(value) == "": return None
    secret = dict(_key_materials())[_CURRENT_VERSION]
    return f"{_CURRENT_VERSION}:{_fernet(secret).encrypt(str(value).encode('utf-8')).decode('ascii')}"

def decrypt_secret(value: Any) -> str | None:
    if value is None or str(value) == "": return None
    raw = str(value); version, token = (raw.split(":", 1) if ":" in raw else ("legacy", raw))
    candidates = _key_materials() if version == "legacy" else [(v, k) for v, k in _key_materials() if v == version]
    for _, secret in candidates:
        try: return _fernet(secret).decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError): continue
    return None

def secret_hash(value: Any) -> str | None:
    if value is None or str(value) == "": return None
    secret = dict(_key_materials())[_CURRENT_VERSION]
    return hmac.new(secret.encode("utf-8"), str(value).encode("utf-8"), hashlib.sha256).hexdigest()

def redact_profile(profile: dict | None) -> dict | None:
    if profile is None: return None
    return {key: value for key, value in profile.items() if key not in _SECRET_FIELDS}

def secure_get_user_profile(original_get, original_update, user_id: str) -> dict | None:
    profile = original_get(user_id)
    if not profile: return None
    legacy_access = profile.get("whatsapp_access_token")
    legacy_verify = profile.get("whatsapp_verify_token")
    if legacy_access or legacy_verify:
        encrypted = {"whatsapp_access_token_encrypted": encrypt_secret(legacy_access),"whatsapp_verify_token_encrypted": encrypt_secret(legacy_verify),"whatsapp_verify_token_hash": secret_hash(legacy_verify),"whatsapp_access_token": None,"whatsapp_verify_token": None}
        try: original_update(user_id, encrypted)
        except Exception: pass
    return redact_profile(profile)

def secure_update_profile_row(original_update, user_id: str, changes: dict, select_fields: str = "*") -> dict | None:
    payload = dict(changes); access = payload.pop("whatsapp_access_token", None); verify = payload.pop("whatsapp_verify_token", None)
    if access is not None: payload.update({"whatsapp_access_token_encrypted": encrypt_secret(access),"whatsapp_access_token": None})
    if verify is not None: payload.update({"whatsapp_verify_token_encrypted": encrypt_secret(verify),"whatsapp_verify_token_hash": secret_hash(verify),"whatsapp_verify_token": None})
    return redact_profile(original_update(user_id, payload, select_fields))
