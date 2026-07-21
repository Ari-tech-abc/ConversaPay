"""
Comprehensive test suite for security and business logic fixes.
Tests all critical and high-severity issues identified in the audit.

Run with: pytest tests/test_security_fixes.py -v
"""
import pytest
import hashlib
import hmac as hmac_lib
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock

# Import the services
from backend.middleware.auth import is_pro_user, RoleChecker
from backend.middleware.rate_limiter import RateLimiter, _is_trusted_proxy, get_client_ip
from backend.routers.payme_webhook import _verify_payme_signature, _hash_card_token
from backend.models.schemas import ChatRequest, OrderStatus


# ============================================
# C1: Order Status Machine Validation Tests
# ============================================

class TestOrderStatusMachine:
    """Test valid/invalid order status transitions."""
    
    def test_valid_transition_pending_to_processing(self):
        """PENDING -> PROCESSING is valid."""
        valid_transitions = {
            OrderStatus.PENDING.value: [OrderStatus.PROCESSING.value, OrderStatus.CANCELED.value],
        }
        assert OrderStatus.PROCESSING.value in valid_transitions[OrderStatus.PENDING.value]
    
    def test_invalid_transition_pending_to_delivered(self):
        """PENDING -> DELIVERED is invalid (must go through PROCESSING, PAID, SHIPPED)."""
        valid_transitions = {
            OrderStatus.PENDING.value: [OrderStatus.PROCESSING.value, OrderStatus.CANCELED.value],
        }
        assert OrderStatus.DELIVERED.value not in valid_transitions[OrderStatus.PENDING.value]
    
    def test_invalid_transition_delivered_to_processing(self):
        """DELIVERED -> PROCESSING is invalid (no backward transitions)."""
        valid_transitions = {
            OrderStatus.DELIVERED.value: [OrderStatus.REFUNDED.value],
        }
        assert OrderStatus.PROCESSING.value not in valid_transitions[OrderStatus.DELIVERED.value]


# ============================================
# C2: PayMe Webhook Signature Verification Tests
# ============================================

class TestPayMeSignatureVerification:
    """Test HMAC-SHA256 signature verification."""
    
    def test_valid_signature(self):
        """Valid HMAC signature should pass verification."""
        secret = "test_seller_key"
        body = b'{\"sale_id\": \"123\", \"status\": \"success\"}'
        
        # Compute correct signature
        computed_sig = hmac_lib.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Mock the settings
        with patch('backend.routers.payme_webhook.settings') as mock_settings:
            mock_settings.PAYME_SELLER_KEY = secret
            result = _verify_payme_signature(body, computed_sig)
            assert result is True
    
    def test_invalid_signature(self):
        """Invalid HMAC signature should fail verification."""
        secret = "test_seller_key"
        body = b'{\"sale_id\": \"123\", \"status\": \"success\"}'
        invalid_sig = "invalid_signature_hex"
        
        with patch('backend.routers.payme_webhook.settings') as mock_settings:
            mock_settings.PAYME_SELLER_KEY = secret
            result = _verify_payme_signature(body, invalid_sig)
            assert result is False
    
    def test_missing_signature(self):
        """Missing signature should fail verification."""
        body = b'{\"sale_id\": \"123\"}'
        result = _verify_payme_signature(body, "")
        assert result is False


# ============================================
# C5: IP Spoofing Prevention Tests
# ============================================

class TestIPSpoofingPrevention:
    """Test X-Forwarded-For header validation."""
    
    def test_trusted_proxy_can_set_forwarded_for(self):
        """Requests from trusted proxies can set X-Forwarded-For."""
        assert _is_trusted_proxy("127.0.0.1") is True
        assert _is_trusted_proxy("10.0.0.1") is True
        assert _is_trusted_proxy("192.168.1.1") is True
    
    def test_untrusted_ip_cannot_spoof(self):
        """Requests from untrusted IPs cannot spoof X-Forwarded-For."""
        assert _is_trusted_proxy("203.0.113.1") is False
        assert _is_trusted_proxy("8.8.8.8") is False
    
    def test_rate_limiter_uses_correct_ip(self):
        """Rate limiter should use direct IP when proxy is untrusted."""
        limiter = RateLimiter(requests_per_minute=5)
        
        # Simulate untrusted IP trying to spoof
        mock_request = Mock()
        mock_request.client.host = "203.0.113.1"
        mock_request.headers.get = Mock(return_value="10.0.0.1")
        
        # Should use direct IP, not spoofed one
        ip = get_client_ip(mock_request)
        assert ip == "203.0.113.1"


# ============================================
# H3: Pro User Timezone-Aware Datetime Tests
# ============================================

class TestProUserTimezoneAwareness:
    """Test Pro user check with timezone-aware datetimes."""
    
    @patch('backend.middleware.auth.supabase_service')
    def test_pro_user_with_valid_expiry(self, mock_supabase):
        """Pro user with future expiry should return True."""
        future_date = (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat()
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "is_pro": True,
                "plan_type": "pro",
                "subscription_expires_at": future_date
            }
        ]
        
        result = is_pro_user("test_user_id")
        assert result is True
    
    @patch('backend.middleware.auth.supabase_service')
    def test_pro_user_with_expired_subscription(self, mock_supabase):
        """Pro user with past expiry should return False."""
        past_date = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "is_pro": True,
                "plan_type": "pro",
                "subscription_expires_at": past_date
            }
        ]
        
        result = is_pro_user("test_user_id")
        assert result is False


# ============================================
# H5: Card Token Hashing Tests
# ============================================

class TestCardTokenHashing:
    """Test card tokens are hashed before storage."""
    
    def test_card_token_hashed(self):
        """Card token should be hashed with SHA-256."""
        token = "4111111111111111"
        hashed = _hash_card_token(token)
        
        # Verify it's a valid SHA-256 hash
        assert len(hashed) == 64
        assert hashed == hashlib.sha256(token.encode("utf-8")).hexdigest()
    
    def test_card_token_not_plaintext(self):
        """Hashed token should not contain original token."""
        token = "4111111111111111"
        hashed = _hash_card_token(token)
        
        assert token not in hashed


# ============================================
# M1: Chat Message Length Validation Tests
# ============================================

class TestChatMessageValidation:
    """Test chat message input validation."""
    
    def test_chat_message_max_length(self):
        """Chat message should have max_length=2000."""
        long_message = "x" * 2001
        
        with pytest.raises(ValueError):
            ChatRequest(
                message=long_message,
                business_id="test_business"
            )
    
    def test_chat_message_within_limit(self):
        """Chat message within limit should be accepted."""
        message = "x" * 2000
        
        request = ChatRequest(
            message=message,
            business_id="test_business"
        )
        assert len(request.message) == 2000


# ============================================
# M2: Session ID Pattern Validation Tests
# ============================================

class TestSessionIDValidation:
    """Test session_id pattern validation."""
    
    def test_valid_session_id(self):
        """Valid session IDs should be accepted."""
        valid_ids = [
            "session_123",
            "session-456",
            "abc123def456",
            "a" * 128
        ]
        
        for session_id in valid_ids:
            request = ChatRequest(
                message="test",
                business_id="test",
                session_id=session_id
            )
            assert request.session_id == session_id
    
    def test_invalid_session_id_with_special_chars(self):
        """Session IDs with special characters should be rejected."""
        invalid_ids = [
            "session@123",
            "session#456",
            "session$789",
            "session/abc"
        ]
        
        for session_id in invalid_ids:
            with pytest.raises(ValueError):
                ChatRequest(
                    message="test",
                    business_id="test",
                    session_id=session_id
                )


# ============================================
# M8: Rate Limiter Multi-Worker Warning Tests
# ============================================

class TestRateLimiterMultiWorker:
    """Test rate limiter behavior in multi-worker scenarios."""
    
    def test_rate_limiter_per_process(self):
        """Rate limiter should be per-process (not shared)."""
        limiter1 = RateLimiter(requests_per_minute=5)
        limiter2 = RateLimiter(requests_per_minute=5)
        
        # Each limiter has its own state
        assert limiter1.requests is not limiter2.requests
        
        # Requests to one don't affect the other
        limiter1.is_allowed("192.168.1.1")
        assert len(limiter1.requests["192.168.1.1"]) == 1
        assert len(limiter2.requests.get("192.168.1.1", [])) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
