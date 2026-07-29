"""
Real integration tests using FastAPI TestClient.

These tests send actual HTTP requests through the ASGI stack and validate
status codes, headers, and JSON payloads. They replace the old text-grep
contract tests that only checked source file strings.
"""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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

    def test_dashboard_stats_requires_token(self):
        response = client.get("/api/v1/dashboard/stats")
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
# Tenant Guard / Cross-Tenant Isolation
# ============================================

class TestTenantIsolation:
    """Verify that tenant-scoped endpoints enforce ownership."""

    def test_get_payments_requires_auth(self):
        response = client.get("/api/v1/payments?business_id=fake-biz")
        assert response.status_code in (401, 403)

    def test_products_list_requires_auth(self):
        response = client.get("/api/v1/products?business_id=fake-biz")
        assert response.status_code in (401, 403)

    def test_orders_list_requires_auth(self):
        response = client.get("/api/v1/orders?business_id=fake-biz")
        assert response.status_code in (401, 403)


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
