# Authentication Patterns Rule

## Supabase JWT Token Structure

Supabase generates JWT tokens with these standard claims:

```json
{
  "sub": "user-uuid-here",
  "email": "user@example.com",
  "aud": "authenticated",
  "exp": 1234567890,
  "iat": 1234567800,
  "auth_time": 1234567800,
  "user_metadata": {},
  "app_metadata": {}
}
```

### Key Claims
- `sub` - Subject (User ID) - **Always use this for user_id**
- `email` - User email address
- `exp` - Expiration timestamp (Unix time)
- `iat` - Issued at timestamp
- `aud` - Audience (usually "authenticated")

---

## Correct JWT Decoding Pattern

### Standard Decoding
```python
from jose import jwt
from backend.config import settings

payload = jwt.decode(
    token,
    settings.SUPABASE_ANON_KEY,
    algorithms=["HS256"],
    options={"verify_signature": False}
)

user_id = payload.get("sub")
email = payload.get("email")

if not user_id:
    raise HTTPException(status_code=401, detail="Invalid token: missing user ID")

return AuthUser(user_id=user_id, email=email or "")
```

### With Error Handling
```python
from jose import jwt, JWTError

try:
    payload = jwt.decode(
        token,
        settings.SUPABASE_ANON_KEY,
        algorithms=["HS256"],
        options={"verify_signature": False}
    )
    user_id = payload.get("sub")
    email = payload.get("email")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return AuthUser(user_id=user_id, email=email or "")
    
except JWTError as e:
    logger.warning(f"JWT validation error: {str(e)}")
    raise HTTPException(status_code=401, detail="Could not validate credentials")
except Exception as e:
    logger.error(f"Authentication error: {str(e)}")
    raise HTTPException(status_code=401, detail="Authentication failed")
```

---

## Incorrect Patterns to Avoid

### ❌ Non-existent SDK Methods
```python
# WRONG - This method doesn't exist in Supabase Python SDK
user = supabase_client.auth.get_user(token)
```

### ❌ Wrong Claim Names
```python
# WRONG - Should be "sub", not "user_id"
user_id = payload.get("user_id")

# WRONG - Should be "sub", not "id"
user_id = payload.get("id")
```

### ❌ Missing Error Handling
```python
# WRONG - No try/except for JWT errors
payload = jwt.decode(token, key, algorithms=["HS256"])
user_id = payload.get("sub")  # Could fail if token invalid
```

### ❌ Forgetting to Validate Claims
```python
# WRONG - Doesn't check if user_id exists
payload = jwt.decode(token, key, algorithms=["HS256"])
return AuthUser(user_id=payload.get("sub"), email=payload.get("email"))
# If "sub" is missing, user_id will be None
```

---

## FastAPI Integration

### Correct Dependency Pattern
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthUser:
    token = credentials.credentials
    # Decode JWT here
    return AuthUser(user_id=user_id, email=email)

# Usage in endpoint
@app.get("/profile")
async def get_profile(current_user: AuthUser = Depends(get_current_user)):
    return {"user_id": current_user.user_id}
```

---

## Token Expiration Handling

### Check Token Expiration
```python
from datetime import datetime, timezone

payload = jwt.decode(token, key, algorithms=["HS256"])

# Check expiration
exp = payload.get("exp")
if exp:
    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    now_utc = datetime.now(tz=timezone.utc)
    if exp_dt < now_utc:
        raise HTTPException(status_code=401, detail="Token expired")
```

---

## Security Considerations

### ✅ DO
- Validate token signature (or trust Supabase infrastructure)
- Extract user_id from 'sub' claim
- Check token expiration
- Return 401 for invalid tokens
- Log authentication failures
- Use HTTPS for token transmission

### ❌ DON'T
- Log tokens or credentials
- Trust client-provided user IDs
- Skip error handling
- Use wrong claim names
- Expose token details in error messages
- Store tokens in plain text

---

## Testing Authentication

### Test Valid Token
```python
# Create a test token with valid claims
test_payload = {
    "sub": "test-user-id",
    "email": "test@example.com",
    "exp": int(time.time()) + 3600
}
test_token = jwt.encode(test_payload, key, algorithm="HS256")

# Test endpoint
response = client.get(
    "/api/v1/payments/profile",
    headers={"Authorization": f"Bearer {test_token}"}
)
assert response.status_code == 200
```

### Test Invalid Token
```python
# Test with invalid token
response = client.get(
    "/api/v1/payments/profile",
    headers={"Authorization": "Bearer invalid-token"}
)
assert response.status_code == 401
```

### Test Expired Token
```python
# Create expired token
test_payload = {
    "sub": "test-user-id",
    "email": "test@example.com",
    "exp": int(time.time()) - 3600  # Expired 1 hour ago
}
test_token = jwt.encode(test_payload, key, algorithm="HS256")

response = client.get(
    "/api/v1/payments/profile",
    headers={"Authorization": f"Bearer {test_token}"}
)
assert response.status_code == 401
```

---

## Related Rules

- See PRODUCTION_FIXES.md for the specific issues fixed
- See FASTAPI_CONVENTIONS.md for FastAPI patterns
- See SECURITY_STANDARDS.md for security requirements
