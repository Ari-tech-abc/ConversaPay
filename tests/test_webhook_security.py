from backend.services.webhook_security import extract_event_id, payload_sha256, verify_hmac_sha256
import hashlib
import hmac


def test_hmac_sha256_accepts_valid_signature_and_rejects_invalid():
    payload = b'{"event_id":"evt_1"}'
    secret = "test-secret"
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_hmac_sha256(payload, signature, secret)
    assert not verify_hmac_sha256(payload, "bad", secret)


def test_event_id_prefers_signed_transport_header():
    assert extract_event_id({"id": "body-id"}, {"X-Event-Id": "header-id"}) == "header-id"
    assert extract_event_id({"event_id": "body-id"}) == "body-id"


def test_payload_hash_is_stable():
    assert payload_sha256(b"payload") == hashlib.sha256(b"payload").hexdigest()
