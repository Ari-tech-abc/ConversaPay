"""Integration coverage for the protected-endpoint rate limiter."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_password_reset_endpoint_returns_429_after_limit():
    """Six requests from one client identity must hit the 5-request limit."""
    headers = {"X-Forwarded-For": "203.0.113.77"}
    responses = [
        client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": f"rate-limit-{index}@example.com"},
            headers=headers,
        )
        for index in range(6)
    ]

    assert responses[-1].status_code == 429
    assert responses[-1].headers["retry-after"] == "300"
    assert all(response.status_code != 429 for response in responses[:5])
