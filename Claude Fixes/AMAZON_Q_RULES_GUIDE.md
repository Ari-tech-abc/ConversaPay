# How to Use These Fixes with Amazon Q AI Chatbot

## Overview
This guide explains how to leverage Amazon Q's capabilities to understand, apply, and maintain these production fixes using custom rules and prompts.

---

## Part 1: Creating Custom Rules for Amazon Q

### What are Amazon Q Rules?
Amazon Q rules are stored in `.amazonq/rules/` directory and are automatically included in every chat and inline chat request. They help Amazon Q understand your codebase patterns, conventions, and specific requirements.

### Step 1: Create Rules Directory Structure
```
ConversaPay Project/
├── .amazonq/
│   └── rules/
│       ├── PRODUCTION_FIXES.md
│       ├── AUTHENTICATION_PATTERNS.md
│       ├── FASTAPI_CONVENTIONS.md
│       └── SECURITY_STANDARDS.md
```

### Step 2: Create PRODUCTION_FIXES.md Rule
**Location:** `.amazonq/rules/PRODUCTION_FIXES.md`

```markdown
# Production Fixes Rule

## Context
This codebase has two critical production issues that were fixed:

### Issue 1: Chat Endpoint 422 Error
- **File:** backend/routers/chat.py
- **Problem:** Request parameter had `= Depends()` which caused FastAPI to expect it in JSON body
- **Fix:** Remove `= Depends()` from Request parameter
- **Pattern:** FastAPI automatically injects Request objects without Depends()

### Issue 2: Profile Endpoint 401 Error
- **File:** backend/middleware/auth.py
- **Problem:** Used non-existent `supabase_client.auth.get_user(token)` method
- **Fix:** Use `jwt.decode()` from jose library to decode JWT tokens
- **Pattern:** Supabase tokens are JWT tokens with 'sub' (user_id) and 'email' claims

## When Reviewing Code
- Check for `Request = Depends()` patterns - should be just `Request`
- Check for Supabase auth calls - should use JWT decoding, not SDK methods
- Verify JWT payload extraction uses 'sub' for user_id
- Ensure error handling returns appropriate HTTP status codes

## When Writing New Code
- Use FastAPI's automatic Request injection
- Decode JWT tokens using jose.jwt.decode()
- Always validate token claims before using them
- Return 401 for auth failures, 403 for permission failures
```

### Step 3: Create AUTHENTICATION_PATTERNS.md Rule
**Location:** `.amazonq/rules/AUTHENTICATION_PATTERNS.md`

```markdown
# Authentication Patterns Rule

## Supabase JWT Token Structure
Supabase tokens are JWT tokens with these claims:
- `sub`: User ID (UUID)
- `email`: User email address
- `aud`: Audience (usually "authenticated")
- `exp`: Expiration timestamp

## Correct JWT Decoding Pattern
```python
from jose import jwt

payload = jwt.decode(
    token,
    settings.SUPABASE_ANON_KEY,
    algorithms=["HS256"],
    options={"verify_signature": False}
)
user_id = payload.get("sub")
email = payload.get("email")
```

## Incorrect Patterns to Avoid
- ❌ `supabase_client.auth.get_user(token)` - method doesn't exist
- ❌ Using `payload.get("user_id")` - should be `payload.get("sub")`
- ❌ Forgetting to handle missing claims
- ❌ Not catching JWTError exceptions

## FastAPI Request Injection
- ✅ `async def endpoint(request: Request):` - automatic injection
- ❌ `async def endpoint(request: Request = Depends()):` - causes 422 errors
- ✅ `async def endpoint(request: ChatRequest, request_obj: Request):` - both work
```

### Step 4: Create FASTAPI_CONVENTIONS.md Rule
**Location:** `.amazonq/rules/FASTAPI_CONVENTIONS.md`

```markdown
# FastAPI Conventions Rule

## Request Parameter Handling

### Special Types (Auto-Injected)
These types are automatically injected by FastAPI without Depends():
- `Request` - HTTP request object
- `Response` - HTTP response object
- `BackgroundTasks` - background task queue
- `HTTPException` - for raising HTTP errors

### Correct Usage
```python
# ✅ CORRECT - Request is auto-injected
@app.post("/endpoint")
async def handler(body: MyModel, request: Request):
    client_ip = request.client.host
    return {"status": "ok"}

# ❌ WRONG - Depends() causes FastAPI to expect it in body
@app.post("/endpoint")
async def handler(body: MyModel, request: Request = Depends()):
    # FastAPI tries to resolve Request from JSON body
    # Results in 422 error
    pass
```

### Dependency Injection Pattern
```python
# ✅ CORRECT - Use Depends() for custom dependencies
@app.post("/endpoint")
async def handler(
    body: MyModel,
    current_user: AuthUser = Depends(require_auth)
):
    return {"user": current_user.user_id}
```

## Error Handling
- Return 401 for authentication failures
- Return 403 for authorization failures
- Return 422 for validation errors (Pydantic)
- Return 500 for server errors
- Always log errors with full stack trace
```

### Step 5: Create SECURITY_STANDARDS.md Rule
**Location:** `.amazonq/rules/SECURITY_STANDARDS.md`

```markdown
# Security Standards Rule

## Authentication
- ✅ Validate JWT tokens before using them
- ✅ Extract user_id from 'sub' claim
- ✅ Handle expired tokens (check 'exp' claim)
- ✅ Return 401 for invalid tokens
- ❌ Don't trust client-provided user IDs
- ❌ Don't log tokens or sensitive data

## Authorization
- ✅ Verify business ownership before operations
- ✅ Check user roles from database
- ✅ Return 403 for permission denied
- ✅ Log authorization failures
- ❌ Don't assume authenticated = authorized

## Data Validation
- ✅ Use Pydantic models for request validation
- ✅ Set max_length on string fields
- ✅ Validate numeric ranges
- ✅ Sanitize user input
- ❌ Don't trust client data

## Error Handling
- ✅ Return generic error messages to clients
- ✅ Log detailed errors server-side
- ✅ Never expose internal details
- ✅ Use appropriate HTTP status codes
- ❌ Don't expose stack traces to clients
- ❌ Don't log credentials or tokens
```

---

## Part 2: Using Amazon Q to Apply Fixes

### Method 1: Direct Chat with Context

**Step 1:** Open Amazon Q Chat in your IDE

**Step 2:** Reference the rules:
```
@workspace

I need to understand the production fixes that were applied. 
Can you explain the two issues and their solutions?
```

**Step 3:** Amazon Q will:
- Read the rules from `.amazonq/rules/`
- Understand the context of the fixes
- Provide accurate explanations

### Method 2: Inline Chat for Code Review

**Step 1:** Select code in your editor

**Step 2:** Press `Alt+C` (or `Option+C` on Mac) for inline chat

**Step 3:** Ask:
```
Is this authentication code following the production fix patterns?
Check if it uses proper JWT decoding.
```

**Step 4:** Amazon Q will:
- Review the selected code
- Compare against your rules
- Suggest improvements

### Method 3: Creating New Code with Rules

**Step 1:** Open Amazon Q Chat

**Step 2:** Ask:
```
@workspace

I need to create a new authenticated endpoint that:
1. Accepts a POST request with JSON body
2. Validates the user is authenticated
3. Returns user profile data

Follow the authentication patterns from our rules.
```

**Step 3:** Amazon Q will:
- Generate code following your patterns
- Use proper JWT decoding
- Include error handling
- Match your security standards

---

## Part 3: Maintaining Fixes with Amazon Q

### Weekly Code Review Prompt

Save this as `.amazonq/prompts/weekly_review.md`:

```markdown
# Weekly Code Review Prompt

Review the following areas for regressions:

1. **Authentication Endpoints**
   - Check all endpoints using `require_auth` dependency
   - Verify JWT decoding uses 'sub' claim
   - Ensure 401 errors are returned for invalid tokens

2. **FastAPI Request Handling**
   - Search for `Request = Depends()` patterns
   - Verify all Request parameters are auto-injected
   - Check for 422 errors in chat endpoint

3. **Error Handling**
   - Verify no credentials logged
   - Check error messages are generic
   - Ensure stack traces not exposed

4. **Database Queries**
   - Verify business ownership checks
   - Check role-based access control
   - Ensure no IDOR vulnerabilities

Use the rules in `.amazonq/rules/` as reference.
```

**Usage:**
```
@prompt weekly_review

Review the codebase for regressions.
```

### Regression Detection Prompt

Save this as `.amazonq/prompts/regression_check.md`:

```markdown
# Regression Check Prompt

Check if these production fixes are still in place:

## Fix 1: Chat Endpoint
- File: backend/routers/chat.py
- Line: 24
- Expected: `async def chat(request: ChatRequest, request_obj: Request):`
- Should NOT have: `= Depends()`

## Fix 2: Authentication
- File: backend/middleware/auth.py
- Expected: Uses `jwt.decode()` from jose library
- Should NOT have: `supabase_client.auth.get_user(token)`

Report any deviations found.
```

**Usage:**
```
@prompt regression_check

Check if the production fixes are still in place.
```

---

## Part 4: Team Collaboration with Rules

### Onboarding New Developers

**Step 1:** Create `.amazonq/prompts/onboarding.md`:

```markdown
# Onboarding Prompt

Welcome to ConversaPay! Here's what you need to know:

## Critical Production Fixes
1. Chat endpoint: Use `Request` without `Depends()`
2. Auth endpoint: Use JWT decoding, not SDK methods

## Key Rules
- Read `.amazonq/rules/AUTHENTICATION_PATTERNS.md`
- Read `.amazonq/rules/FASTAPI_CONVENTIONS.md`
- Read `.amazonq/rules/SECURITY_STANDARDS.md`

## Common Mistakes to Avoid
- Don't add `= Depends()` to Request parameters
- Don't use non-existent Supabase SDK methods
- Don't log tokens or credentials
- Don't trust client-provided user IDs

Ask me questions about any of these!
```

**Usage:**
```
@prompt onboarding

I'm new to the team. What should I know?
```

### Code Review Checklist

**Step 1:** Create `.amazonq/prompts/review_checklist.md`:

```markdown
# Code Review Checklist

Before approving PRs, check:

## Authentication
- [ ] Uses JWT decoding with jose library
- [ ] Extracts user_id from 'sub' claim
- [ ] Returns 401 for invalid tokens
- [ ] No credentials in logs

## FastAPI
- [ ] Request parameters don't have `= Depends()`
- [ ] Proper error status codes (401, 403, 422, 500)
- [ ] All exceptions caught and logged

## Security
- [ ] Business ownership verified
- [ ] Role-based access control checked
- [ ] Input validation with Pydantic
- [ ] No IDOR vulnerabilities

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Error cases tested
```

**Usage:**
```
@prompt review_checklist

Review this PR against our checklist.
```

---

## Part 5: Continuous Improvement

### Monthly Audit Prompt

```
@workspace

Perform a monthly security audit:
1. Check all authentication endpoints
2. Verify JWT handling is correct
3. Look for any Request = Depends() patterns
4. Review error handling
5. Check for credential leaks in logs

Report findings and recommendations.
```

### Performance Review Prompt

```
@workspace

Review performance of:
1. Chat endpoint - check for N+1 queries
2. Auth middleware - verify caching
3. Database queries - look for inefficiencies

Suggest optimizations.
```

---

## Summary: Using Amazon Q with Your Rules

### Quick Reference

| Task | Command |
|------|---------|
| Understand fixes | `@workspace` + ask about issues |
| Review code | Select code + `Alt+C` + ask |
| Create new code | `@workspace` + describe requirements |
| Weekly review | `@prompt weekly_review` |
| Check regressions | `@prompt regression_check` |
| Onboard developer | `@prompt onboarding` |
| Review PR | `@prompt review_checklist` |

### Best Practices

1. **Keep rules updated** - Update `.amazonq/rules/` as patterns evolve
2. **Use prompts for repetitive tasks** - Save common reviews as prompts
3. **Reference rules in chat** - Use `@workspace` to include context
4. **Document decisions** - Add comments explaining why patterns exist
5. **Review Amazon Q suggestions** - Always verify generated code

### Files to Create

```
.amazonq/
├── rules/
│   ├── PRODUCTION_FIXES.md
│   ├── AUTHENTICATION_PATTERNS.md
│   ├── FASTAPI_CONVENTIONS.md
│   └── SECURITY_STANDARDS.md
└── prompts/
    ├── weekly_review.md
    ├── regression_check.md
    ├── onboarding.md
    └── review_checklist.md
```

---

## Conclusion

By creating these rules and prompts, Amazon Q becomes a specialized assistant for your ConversaPay codebase that:

✅ Understands your production fixes  
✅ Enforces your coding patterns  
✅ Catches regressions automatically  
✅ Helps onboard new developers  
✅ Maintains security standards  
✅ Improves code quality  

**The rules are your team's collective knowledge, encoded for AI assistance.**

---

**Created:** 2024  
**For:** ConversaPay Development Team  
**Status:** Ready to Implement
