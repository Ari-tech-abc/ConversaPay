from datetime import datetime, timezone
from pathlib import Path
from backend.routers.safe_auth import SafeMeResponse


def test_me_response_allowlist_excludes_secrets():
    raw_profile = {
        "email": "user@example.com",
        "full_name": "User",
        "plan_type": "free",
        "email_verified": True,
        "whatsapp_access_token": "must-not-leak",
        "whatsapp_verify_token": "must-not-leak",
        "api_key": "must-not-leak",
        "secret": "must-not-leak",
        "created_at": datetime.now(timezone.utc),
    }
    safe = SafeMeResponse(user_id="user-1", email=raw_profile["email"], profile={key: raw_profile[key] for key in ("email", "full_name", "plan_type", "email_verified", "created_at")})
    payload = safe.model_dump(mode="json")
    assert "whatsapp_access_token" not in payload["profile"]
    assert "whatsapp_verify_token" not in payload["profile"]
    assert "api_key" not in payload["profile"]
    assert "secret" not in payload["profile"]


def test_sensitive_auth_paths_have_dedicated_limits():
    source = Path("backend/middleware/auth_rate_limit.py").read_text()
    assert "/api/v1/auth/password-reset/request" in source
    assert "/api/v1/admin/login" in source
    assert "429" in source


def test_safe_me_route_is_explicitly_allowlisted():
    source = Path("backend/routers/safe_auth.py").read_text()
    assert "extra=\"forbid\"" in source
    assert "whatsapp_access_token" not in source
