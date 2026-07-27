from backend.services.webhook_security import expected_hmac, verify_signature


def test_valid_hmac_signature_is_accepted():
    payload = b'{"event":"paid"}'
    signature = expected_hmac("secret", payload)
    assert verify_signature(payload, signature, "secret")


def test_invalid_or_missing_signature_is_rejected():
    payload = b'{"event":"paid"}'
    assert not verify_signature(payload, "bad", "secret")
    assert not verify_signature(payload, None, "secret")
    assert not verify_signature(payload, expected_hmac("secret", payload), None)
