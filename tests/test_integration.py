"""
Real integration tests using FastAPI TestClient.

These tests send actual HTTP requests through the ASGI stack and validate
status codes, headers, and JSON payloads. They replace the old text-grep
contract tests that only checked source file strings.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from main import app
from backend.middleware.auth import AuthUser, get_current_user

client = TestClient(app)


# ============================================
# Helpers
# ============================================

def _override_auth(user_id: str = "user-test-123", email: str = "test@example.com"):
    """Create an auth override returning a fake authenticated user."""
    fake_user = AuthUser(user_id=user_id, email=email)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    return fake_user


def _clear_overrides():
    app.dependency_overrides.clear()


# ============================================
# Infrastructure / Readiness
# ============================================

class TestHealthAndReadiness:
    """Verify the health and readiness probes respond correctly."""

    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_readiness_returns_200(self):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "environment" in data

    def test_public_config_exposes_only_anon_key(self):
        response = client.get("/api/v1/config/public")
        assert response.status_code == 200
        data = response.json()
        assert "supabase_url" in data
        assert "supabase_anon_key" in data
        # Must never expose the service role key
        assert "service_role" not in str(data).lower()


# ============================================
# Auth Enforcement (401/403 on protected routes)
# ============================================

class TestAuthEnforcement:
    """Protected endpoints must reject unauthenticated requests."""

    def test_auth_me_requires_token(self):
        response = client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)

    def test_payments_profile_requires_token(self):
        response = client.get("/api/v1/payments/profile")
        assert response.status_code in (401, 403)

    def test_dashboard_profile_requires_token(self):
        response = client.get("/api/v1/dashboard/profile")
        assert response.status_code in (401, 403)

    def test_admin_panel_requires_token(self):
        response = client.get("/api/v1/admin/users")
        assert response.status_code in (401, 403)

    def test_logout_requires_token(self):
        response = client.post("/api/v1/auth/logout")
        assert response.status_code in (401, 403)

    def test_invalid_bearer_token_rejected(self):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token-abc123"}
        )
        assert response.status_code == 401


# ============================================
# Positive-Path Tests (authenticated success)
# ============================================

class TestPositivePaths:
    """Verify that authenticated requests succeed for protected endpoints."""

    def setup_method(self):
        _override_auth()

    def teardown_method(self):
        _clear_overrides()

    def test_auth_me_returns_user_info(self):
        """GET /auth/me returns current user even when profile DB is unreachable."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-test-123"
        assert data["email"] == "test@example.com"

    def test_logout_succeeds(self):
        """POST /auth/logout always returns success for authenticated users."""
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"

    def test_dashboard_profile_with_verified_user(self):
        """GET /dashboard/profile returns plan info for verified user."""
        mock_profile = {
            "user_id": "user-test-123",
            "email": "test@example.com",
            "plan_type": "pro",
            "email_verified": True,
            "subscription_expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with patch("backend.routers.dashboard.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_profile])
            response = client.get("/api/v1/dashboard/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == "user-test-123"
            assert data["plan_type"] == "pro"

    def test_payments_profile_returns_user_data(self):
        """GET /payments/profile returns profile for authenticated user."""
        mock_row = {
            "id": "profile-uuid",
            "user_id": "user-test-123",
            "email": "test@example.com",
            "full_name": "Test User",
            "plan_type": "free",
            "subscription_expires_at": None,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        with patch("backend.routers.payments.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_row])
            response = client.get("/api/v1/payments/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == "user-test-123"
            assert data["plan_type"] == "free"

    def test_dashboard_features_returns_plan_gates(self):
        """GET /dashboard/features returns feature flags for user plan."""
        mock_profile = {
            "user_id": "user-test-123",
            "plan_type": "premium",
            "email_verified": True,
            "subscription_expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        with patch("backend.routers.dashboard.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_profile])
            response = client.get("/api/v1/dashboard/features")
            assert response.status_code == 200
            data = response.json()
            assert data["plan_type"] == "premium"
            assert data["whatsapp"] is True
            assert data["site_builder"] is True


# ============================================
# Cross-Tenant Isolation
# ============================================

class TestCrossTenantIsolation:
    """Verify that tenant-scoped endpoints enforce ownership."""

    def setup_method(self):
        _override_auth(user_id="user-a-111", email="usera@example.com")

    def teardown_method(self):
        _clear_overrides()

    def test_tenant_guard_rejects_non_owner(self):
        """verify_tenant_ownership raises 404 when user is not the owner."""
        from backend.middleware.tenant_guard import verify_tenant_ownership
        from fastapi import HTTPException

        mock_supabase = MagicMock()
        # Simulate empty result (user does not own this business)
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        with pytest.raises(HTTPException) as exc_info:
            verify_tenant_ownership(
                supabase=mock_supabase,
                user_id="user-a-111",
                business_id="biz-owned-by-user-b"
            )
        assert exc_info.value.status_code == 404

    def test_tenant_guard_accepts_owner(self):
        """verify_tenant_ownership returns business row for valid owner."""
        from backend.middleware.tenant_guard import verify_tenant_ownership

        mock_supabase = MagicMock()
        business_row = {"id": "biz-uuid", "business_name": "My Biz", "is_active": True, "settings": {}, "owner_id": "user-a-111"}
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[business_row])

        result = verify_tenant_ownership(
            supabase=mock_supabase,
            user_id="user-a-111",
            business_id="biz-uuid"
        )
        assert result["id"] == "biz-uuid"
        assert result["owner_id"] == "user-a-111"

    def test_resource_owner_rejects_wrong_user(self):
        """verify_resource_owner raises 404 for resources not owned by the caller."""
        from backend.middleware.tenant_guard import verify_resource_owner
        from fastapi import HTTPException

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        with pytest.raises(HTTPException) as exc_info:
            verify_resource_owner(
                supabase=mock_supabase,
                table="orders",
                resource_id="order-xyz",
                user_id="user-a-111",
                owner_column="user_id"
            )
        assert exc_info.value.status_code == 404

    def test_cross_tenant_payments_access_denied(self):
        """User A cannot list payments for User B's business via HTTP."""
        with patch("backend.routers.payments.supabase") as mock_sb:
            # Simulate: business lookup returns empty (user-a-111 does not own biz-of-user-b)
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            response = client.get("/api/v1/payments?business_id=biz-of-user-b")
            assert response.status_code == 404

    def test_cross_tenant_single_payment_access_denied(self):
        """User A cannot read a specific payment belonging to User B's business."""
        with patch("backend.routers.payments.supabase") as mock_sb:
            # First call: payment exists
            payment_row = {"id": "pay-123", "business_id": "biz-of-user-b", "amount": 100, "status": "succeeded"}
            # Second call: business ownership check fails
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[payment_row])
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            response = client.get("/api/v1/payments/pay-123")
            assert response.status_code in (403, 404)


# ============================================
# Verify Email / Login Flow
# ============================================

class TestVerifyEmailFlow:
    """Test the email verification and login flow."""

    def test_verify_email_invalid_token_returns_error(self):
        """GET /auth/verify with non-existent token returns 400 HTML."""
        with patch("backend.routers.auth.supabase") as mock_sb:
            # Token not found in DB
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            response = client.get("/api/v1/auth/verify?token=invalid-token-abc")
            assert response.status_code == 400
            assert "Verification Failed" in response.text

    def test_verify_email_expired_token_returns_error(self):
        """GET /auth/verify with expired token returns 400 HTML."""
        expired_profile = {
            "user_id": "user-exp",
            "email": "expired@example.com",
            "email_verified": False,
            "email_verification_token": "expired-token",
            "email_verification_expires_at": (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
        }
        with patch("backend.routers.auth.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[expired_profile])
            response = client.get("/api/v1/auth/verify?token=expired-token")
            assert response.status_code == 400
            assert "Expired" in response.text or "expired" in response.text.lower()

    def test_verify_email_already_verified_returns_info(self):
        """GET /auth/verify with already-verified profile returns informational page."""
        verified_profile = {
            "user_id": "user-ver",
            "email": "verified@example.com",
            "email_verified": True,
            "email_verification_token": "already-used",
            "email_verification_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        with patch("backend.routers.auth.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[verified_profile])
            response = client.get("/api/v1/auth/verify?token=already-used")
            assert response.status_code == 200
            assert "Already Verified" in response.text

    def test_verify_email_success_marks_verified(self):
        """GET /auth/verify with valid token calls mark_email_verified RPC."""
        valid_profile = {
            "user_id": "user-new",
            "email": "new@example.com",
            "email_verified": False,
            "email_verification_token": "valid-token-123",
            "email_verification_expires_at": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        }
        with patch("backend.routers.auth.supabase") as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[valid_profile])
            mock_sb.rpc.return_value.execute.return_value = MagicMock(data=[{"success": True}])
            response = client.get("/api/v1/auth/verify?token=valid-token-123")
            assert response.status_code == 200
            assert "Email Verified Successfully" in response.text
            # Confirm the RPC was called with correct user_id
            mock_sb.rpc.assert_called_once_with("mark_email_verified", {"p_user_id": "user-new"})

    def test_login_missing_credentials_returns_422(self):
        """POST /auth/login without body returns 422 validation error."""
        response = client.post("/api/v1/auth/login")
        assert response.status_code == 422

    def test_login_invalid_credentials_returns_401(self):
        """POST /auth/login with bad credentials returns 401."""
        with patch("backend.routers.auth.supabase") as mock_sb:
            mock_sb.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "bad@example.com", "password": "wrongpass"}
            )
            assert response.status_code == 401


# ============================================
# Confirm-Session Read-Only Contract
# ============================================

class TestConfirmSessionReadOnly:
    """The confirm-session endpoint must never mutate state."""

    def test_confirm_session_requires_auth(self):
        response = client.get("/api/v1/payments/confirm-session?session_id=cs_test_123")
        assert response.status_code in (401, 403)

    def test_confirm_session_rejects_empty_session_id(self):
        # Even if somehow authed, empty session_id should fail validation
        response = client.get(
            "/api/v1/payments/confirm-session?session_id=",
            headers={"Authorization": "Bearer fake"}
        )
        # Should be either 401 (no valid auth) or 422 (validation) or 400
        assert response.status_code in (401, 422, 400)


# ============================================
# Security Headers
# ============================================

class TestSecurityHeaders:
    """Verify security headers are present on responses."""

    def test_health_has_security_headers(self):
        response = client.get("/health")
        headers = response.headers
        assert "x-content-type-options" in headers
        assert headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in headers
        assert "content-security-policy" in headers
        assert "referrer-policy" in headers

    def test_cors_vary_header_present(self):
        response = client.get("/health")
        assert "vary" in response.headers


# ============================================
# 404 Handler
# ============================================

class TestNotFoundHandler:
    """Custom 404 handler returns JSON, not default HTML."""

    def test_unknown_api_route_returns_json_404(self):
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data


# ============================================
# Webhook Endpoints (public, no auth required)
# ============================================

class TestWebhookEndpoints:
    """Webhook endpoints must be reachable without auth but validate signatures."""

    def test_stripe_webhook_rejects_missing_signature(self):
        response = client.post(
            "/api/v1/webhooks/stripe",
            content=b'{"type": "test"}',
            headers={"Content-Type": "application/json"}
        )
        # Should reject: no stripe-signature header
        assert response.status_code == 400

    def test_stripe_webhook_rejects_invalid_signature(self):
        response = client.post(
            "/api/v1/webhooks/stripe",
            content=b'{"type": "test"}',
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=123,v1=invalid"
            }
        )
        assert response.status_code == 400
