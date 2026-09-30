"""HTTP-level checks against the composed app, without external credentials."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

# These values override local configuration. All provider operations below are mocked.
os.environ.update({
    "ENVIRONMENT":"test", "SECRET_KEY":"offline-security-test-secret-32-characters",
    "SUPABASE_URL":"https://offline-test.supabase.co", "SUPABASE_ANON_KEY":"offline-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY":"offline-service-key", "GEMINI_API_KEY":"offline-gemini-key",
    "RESEND_API_KEY":"offline-email-key", "EMAIL_FROM_ADDRESS":"test@example.com",
    "REDIS_URL":"", "DATABASE_URL":"", "SENTRY_DSN":"", "MIGRATIONS_AUTO_APPLY":"false",
    "TRUSTED_PROXY_CIDRS":"",
})
import dotenv
dotenv.load_dotenv = lambda *a, **kw: False

from fastapi.testclient import TestClient
from main import app
from backend.middleware.auth import AuthUser, get_current_user, require_auth
from backend.routers import auth, onboarding, profile
from backend.middleware.rate_limiter import get_client_ip
from backend.config import settings
from backend.services.whatsapp_security import decrypt_secret, secure_get_user_profile, secret_hash
from backend.services.migration_runner import encrypt_legacy_whatsapp_credentials
from unittest.mock import AsyncMock
import asyncio


class ApplicationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.user = AuthUser("offline-user", "owner@example.com", True)
        app.dependency_overrides[get_current_user] = lambda:self.user
        app.dependency_overrides[require_auth] = lambda:self.user
        self.client = TestClient(app)  # No lifespan: no migrations or monitoring startup.

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_registered_me_route_does_not_expose_profile_secrets(self):
        raw = {"email":"owner@example.com","full_name":"Owner","plan_type":"free",
               "whatsapp_access_token":"secret","whatsapp_access_token_encrypted":"encrypted",
               "email_verification_token":"verification-secret","role":"admin"}
        with patch.object(onboarding, "get_user_profile", return_value=raw), patch.object(onboarding, "_owned_businesses", return_value=[]):
            response = self.client.get('/api/v1/auth/me')
        self.assertEqual(response.status_code, 200)
        self.assertIn("requires_business_onboarding", response.json())
        for field in ["whatsapp_access_token", "whatsapp_access_token_encrypted", "email_verification_token", "role"]:
            self.assertNotIn(field, response.json()["profile"])

    def test_fake_mfa_flag_is_not_reported_as_protection(self):
        with patch.object(profile, "get_user_profile", return_value={"two_factor_enabled":True}):
            response = self.client.get('/api/v1/profile/security')
        self.assertFalse(response.json()["two_factor_enabled"])
        self.assertFalse(response.json()["two_factor_available"])
        self.assertEqual(self.client.post('/api/v1/profile/2fa/toggle').status_code, 503)

    def test_recovery_token_is_bound_to_new_client_before_password_update(self):
        client = MagicMock()
        with patch.object(auth, "create_auth_client", return_value=client), patch.object(auth, "supabase") as db:
            db.auth.get_user.return_value = None
            response = self.client.post('/api/v1/auth/password-reset/confirm', json={"token":"recovery-jwt", "new_password":"test-password-123"})
        self.assertEqual(response.status_code, 200)
        calls = client.auth.method_calls
        self.assertEqual(calls[0].args, ("recovery-jwt", ""))
        self.assertEqual(calls[1].args, ({"password":"test-password-123"},))
        db.auth.update_user.assert_not_called()

    def test_invalid_recovery_token_never_changes_any_password(self):
        client=MagicMock();client.auth.set_session.side_effect=ValueError('invalid token')
        with patch.object(auth, "create_auth_client", return_value=client):
            response=self.client.post('/api/v1/auth/password-reset/confirm',json={"token":"invalid","new_password":"test-password-123"})
        self.assertEqual(response.status_code,400)
        client.auth.update_user.assert_not_called()

    def test_login_limit_applies_even_with_rotating_forwarded_header(self):
        with patch.object(auth, "create_auth_client") as create:
            create.return_value.auth.sign_in_with_password.side_effect=ValueError('bad login')
            statuses=[self.client.post('/api/v1/auth/login',headers={"X-Forwarded-For":f"203.0.113.{i}"},json={"email":"owner@example.com","password":"invalid"}).status_code for i in range(14)]
        self.assertEqual(statuses[-1],429)
        self.assertLessEqual(create.call_count,12)

    def test_forwarded_chain_stops_at_first_untrusted_hop(self):
        request=SimpleNamespace(client=SimpleNamespace(host="10.1.2.3"), headers={"X-Forwarded-For":"1.2.3.4, 203.0.113.5, 10.2.3.4"})
        with patch.object(settings,"TRUSTED_PROXY_CIDRS","10.0.0.0/8"):
            self.assertEqual(get_client_ip(request),"203.0.113.5")
        with patch.object(settings,"TRUSTED_PROXY_CIDRS",""):
            self.assertEqual(get_client_ip(request),"10.1.2.3")

    def test_whatsapp_updates_store_ciphertext_and_redact_response(self):
        db=MagicMock()
        db.table.return_value.update.return_value.eq.return_value.execute.return_value.data=[{"whatsapp_access_token":"plaintext","email":"owner@example.com"}]
        with patch.object(auth,"supabase",db):
            response=auth.update_profile_row("u",{"whatsapp_access_token":"test-whatsapp-secret","whatsapp_verify_token":"test-verify-secret"})
        payload=db.table.return_value.update.call_args.args[0]
        self.assertIsNone(payload["whatsapp_access_token"])
        self.assertEqual(decrypt_secret(payload["whatsapp_access_token_encrypted"]),"test-whatsapp-secret")
        self.assertEqual(decrypt_secret(payload["whatsapp_verify_token_encrypted"]),"test-verify-secret")
        self.assertNotIn("whatsapp_access_token",response)

    def test_identity_reset_uses_supported_sdk_and_neutral_response(self):
        db=MagicMock()
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data={"user_id":"offline-user"}
        db.auth.admin.get_user_by_id.return_value=SimpleNamespace(user=SimpleNamespace(id="offline-user",user_metadata={}))
        with patch.object(auth,"supabase",db), patch.object(auth,"update_profile_row"), patch.object(auth.email_service,"send_verification_email",return_value=True):
            response=self.client.get('/api/v1/auth/password-reset/verify-identity?email=Owner@example.com')
        self.assertEqual(response.status_code,200)
        db.auth.admin.get_user_by_id.assert_called_once_with("offline-user")
        self.assertTrue(response.json()["message"].startswith("If an account exists"))
        db.auth.admin.get_user_by_email.assert_not_called()

    def test_legacy_profile_read_preserves_verification_hash(self):
        raw={"email":"owner@example.com","whatsapp_verify_token":"legacy-verify"}
        db=MagicMock()
        db.table.return_value.update.return_value.eq.return_value.execute.return_value.data=[raw]
        with patch.object(auth,"supabase",db):
            response=secure_get_user_profile(lambda _:raw,auth.update_profile_row,"u")
        payload=db.table.return_value.update.call_args.args[0]
        self.assertEqual(payload["whatsapp_verify_token_hash"],secret_hash("legacy-verify"))
        self.assertEqual(decrypt_secret(payload["whatsapp_verify_token_encrypted"]),"legacy-verify")
        self.assertNotIn("whatsapp_verify_token",response)

    def test_existing_plaintext_credentials_are_encrypted_during_migration(self):
        db=SimpleNamespace(fetch=AsyncMock(return_value=[{"id":"u","whatsapp_access_token":"legacy-access","whatsapp_verify_token":"legacy-verify"}]),execute=AsyncMock())
        self.assertEqual(asyncio.run(encrypt_legacy_whatsapp_credentials(db)),1)
        args=db.execute.call_args.args
        self.assertEqual(decrypt_secret(args[2]),"legacy-access")
        self.assertEqual(decrypt_secret(args[3]),"legacy-verify")
        self.assertNotIn("legacy-access",args[0])


if __name__ == '__main__': unittest.main()
