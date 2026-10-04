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
from backend.routers import auth, onboarding, profile, orders, chat, businesses
from backend.models.schemas import ChatRequest, ProductCreate, ProductUpdate, BusinessCreate
from pydantic import ValidationError
import main
from backend.middleware.rate_limiter import RateLimiter
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

    def test_readiness_errors_do_not_expose_credentials(self):
        with patch.object(main, "_check_database", side_effect=RuntimeError("postgres://user:secret@private-db")), patch.object(main, "get_migration_status", return_value="completed"):
            response = self.client.get('/ready')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['failures']['database'], 'unavailable')
        self.assertNotIn('secret', response.text)

    def test_production_app_disables_all_documentation_routes(self):
        import ast
        from pathlib import Path
        # Evaluate the real composition-root app constructor in production mode.
        tree=ast.parse(Path(main.__file__).read_text(encoding='utf-8'))
        constructor=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='app' for t in n.targets))
        namespace=dict(vars(main))
        with patch.object(settings,'ENVIRONMENT','production'):
            exec(compile(ast.Module(body=[constructor],type_ignores=[]),'main.py','exec'),namespace)
        client=TestClient(namespace['app'])  # Skip workers/migrations and external providers.
        try:
            for path in ['/docs','/redoc','/openapi.json']:
                self.assertEqual(client.get(path).status_code,404)
        finally:
            client.close()

    def test_unverified_owner_cannot_bypass_widget_gate(self):
        from backend.services import widget_auth
        with patch.object(widget_auth,'get_current_user_optional',AsyncMock(return_value=AuthUser('u','u@example.com',False))), patch.object(widget_auth,'require_business_owner_for_business_id') as ownership:
            self.assertFalse(asyncio.run(widget_auth._is_authenticated_owner(None,'business')))
        ownership.assert_not_called()

    def test_order_guest_tokens_handle_binary_delimiters_and_reject_tampering(self):
        import base64
        import time
        tokens = [orders._order_guest_token(f'order-{i}') for i in range(300)]
        self.assertTrue(any(b'.' in base64.urlsafe_b64decode(t+'='*((4-len(t)%4)%4))[-32:] for t in tokens))
        for i, token in enumerate(tokens):
            self.assertTrue(orders._verify_order_guest_token(f'order-{i}', token))
            self.assertFalse(orders._verify_order_guest_token('other-order', token))
        self.assertFalse(orders._verify_order_guest_token('expired', orders._order_guest_token('expired', int(time.time())-60)))
        self.assertFalse(orders._verify_order_guest_token('o', '%%%invalid'))

    def test_order_rejects_other_tenant_relations_before_catalog_write(self):
        for field, table in [('customer_id','customers'), ('conversation_id','conversations')]:
            request = SimpleNamespace(customer_id=None, conversation_id=None)
            setattr(request, field, 'foreign-id')
            db = MagicMock()
            db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
            with patch.object(orders,'supabase',db), patch.object(orders,'_catalog_order') as catalog:
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as error:
                    orders._order_payload(request,'own-business')
            self.assertEqual(error.exception.status_code,400)
            db.table.assert_called_once_with(table)
            self.assertEqual(db.table.return_value.select.return_value.eq.call_args.args,('id','foreign-id'))
            self.assertEqual(db.table.return_value.select.return_value.eq.return_value.eq.call_args.args,('business_id','own-business'))
            catalog.assert_not_called()

    def test_product_writes_reject_executable_urls(self):
        for field in ['image_url','payment_link']:
            for url in ['javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'https://user:password@example.com']:
                with self.subTest(field=field,url=url), self.assertRaises(ValidationError):
                    ProductCreate(business_id='b',item_key='x',name='x',price=1,**{field:url})
                with self.assertRaises(ValidationError): ProductUpdate(**{field:url})
        self.assertEqual(ProductUpdate(payment_link='https://example.com/pay').payment_link,'https://example.com/pay')

    def test_demo_business_id_cannot_be_registered(self):
        with patch.object(businesses,'supabase') as db:
            response=self.client.post('/api/v1/businesses',json={'business_id':'conversapay','business_name':'Fake demo'})
        self.assertEqual(response.status_code,400)
        db.table.assert_not_called()

    def test_free_owner_quota_cannot_be_reset_by_header_or_session(self):
        self._exercise_free_chat_limit(owner=True)

    def test_free_demo_quota_cannot_be_reset_by_missing_or_rotating_session(self):
        self._exercise_free_chat_limit(owner=False)

    def _exercise_free_chat_limit(self,owner):
        from unittest.mock import AsyncMock
        from contextlib import ExitStack
        db=MagicMock()
        business={'id':'demo-uuid','owner_id':self.user.user_id}
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data=[business]
        db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data={}
        service=MagicMock()
        service.get_or_create_conversation=AsyncMock(return_value={'id':'c','session_id':'server-session'})
        service.get_conversation_history=AsyncMock(return_value=[])
        service.add_message=AsyncMock()
        with ExitStack() as stack:
            for name, value in [('supabase',db),('active_plan',lambda _: 'free'),('authorize_widget_request',AsyncMock()),('check_rate_limit',lambda *a,**kw:None),('get_current_user_optional',AsyncMock(return_value=self.user if owner else None)),('free_dashboard_chat_limiter',RateLimiter(5,3600,'test-owner')),('free_chat_session_limiter',RateLimiter(5,3600,'test-demo')),('session_service',service),('_relevant_products',AsyncMock(return_value=[]))]:
                stack.enter_context(patch.object(chat,name,value))
            stack.enter_context(patch.object(chat.gemini_service,'chat',AsyncMock(return_value={'response':'ok','intent':'chat'})))
            responses=[self.client.post('/api/v1/chat',json={'business_id':'conversapay','message':'hi',**({'session_id':f'rotating-{i}'} if i%2 else {})}) for i in range(6)]
        self.assertEqual([r.status_code for r in responses],[200]*5+[429])
        self.assertEqual(service.add_message.await_count,10)

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

    def test_billing_usage_counts_only_the_current_utc_month(self):
        db=MagicMock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{"plan_type":"free"}]
        db.rpc.return_value.execute.return_value.data={"messages":7}
        with patch.object(profile,"supabase",db), patch.object(profile,"get_user_profile",return_value={"plan_type":"free"}):
            response=self.client.get('/api/v1/profile/billing')
        self.assertEqual(response.status_code,200)
        usage=response.json()["usage"]
        self.assertEqual(usage["used"],7)
        self.assertTrue(usage["available"])
        start=usage["period_start"];end=usage["period_end"]
        self.assertIn("-01T00:00:00+00:00",start)
        self.assertGreater(end,start)
        db.rpc.assert_called_once_with("account_activity", {"p_user_id":"offline-user", "p_start":start, "p_end":end})
        self.assertIsNone(usage["limit"])
        self.assertEqual(response.json()["preview"]["limit"],5)

    def test_failed_usage_count_is_unavailable_instead_of_zero(self):
        db=MagicMock()
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{"plan_type":"free"}]
        db.rpc.return_value.execute.side_effect=RuntimeError("offline")
        with patch.object(profile,"supabase",db), patch.object(profile,"get_user_profile",return_value={"plan_type":"free"}):
            response=self.client.get('/api/v1/profile/billing')
        self.assertIsNone(response.json()["usage"]["used"])
        self.assertFalse(response.json()["usage"]["available"])

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
