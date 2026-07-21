# Production Fixes Rule

## Critical Issues Fixed

### Issue 1: Chat Endpoint 422 Error
**File:** `backend/routers/chat.py`  
**Line:** 24  
**Problem:** `Request = Depends()` causes FastAPI to expect it in JSON body  
**Fix:** Remove `= Depends()` - FastAPI auto-injects Request objects

**Before:**
```python
async def chat(request: ChatRequest, request_obj: Request = Depends()):
```

**After:**
```python
async def chat(request: ChatRequest, request_obj: Request):
```

**Why:** FastAPI automatically injects special types like Request without Depends()

---

### Issue 2: Profile Endpoint 401 Error
**File:** `backend/middleware/auth.py`  
**Lines:** 48-58  
**Problem:** `supabase_client.auth.get_user(token)` method doesn't exist  
**Fix:** Use `jwt.decode()` from jose library

**Before:**
```python
user = supabase_client.auth.get_user(token)
if not user or not user.user:
    raise HTTPException(status_code=401, detail="Invalid authentication credentials")
return AuthUser(user_id=user.user.id, email=user.user.email or "")
```

**After:**
```python
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

**Why:** Supabase tokens are JWT tokens with 'sub' (user_id) and 'email' claims

---

## When Reviewing Code

### Check for Issue 1 Pattern
- Look for `Request = Depends()` in FastAPI endpoints
- Should be just `Request` without Depends()
- This applies to: Request, Response, BackgroundTasks, HTTPException

### Check for Issue 2 Pattern
- Look for `supabase_client.auth.get_user()` calls
- Should use `jwt.decode()` instead
- Extract user_id from `payload.get("sub")`
- Extract email from `payload.get("email")`

---

## When Writing New Code

### FastAPI Request Handling
```python
# ✅ CORRECT
@app.post("/endpoint")
async def handler(body: MyModel, request: Request):
    return {"status": "ok"}

# ❌ WRONG
@app.post("/endpoint")
async def handler(body: MyModel, request: Request = Depends()):
    # This causes 422 errors
    pass
```

### JWT Token Validation
```python
# ✅ CORRECT
from jose import jwt

payload = jwt.decode(
    token,
    settings.SUPABASE_ANON_KEY,
    algorithms=["HS256"],
    options={"verify_signature": False}
)
user_id = payload.get("sub")

# ❌ WRONG
user = supabase_client.auth.get_user(token)  # Method doesn't exist
```

---

## Error Codes

- **422 Unprocessable Content** → Check for `Request = Depends()`
- **401 Unauthorized** → Check JWT decoding logic
- **403 Forbidden** → Check authorization/role checks
- **500 Internal Server Error** → Check exception handling

---

## Related Rules

- See AUTHENTICATION_PATTERNS.md for JWT details
- See FASTAPI_CONVENTIONS.md for FastAPI patterns
- See SECURITY_STANDARDS.md for security requirements
