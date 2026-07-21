# Amazon Q Rules - Ready to Deploy

This folder contains the exact rules files that should be created in `.amazonq/rules/` directory.

## How to Use These Rules

### Step 1: Create .amazonq/rules Directory
```bash
mkdir -p .amazonq/rules
```

### Step 2: Copy Rule Files
Copy each rule file from this folder to `.amazonq/rules/`:

```bash
cp PRODUCTION_FIXES.md ../../.amazonq/rules/
cp AUTHENTICATION_PATTERNS.md ../../.amazonq/rules/
cp FASTAPI_CONVENTIONS.md ../../.amazonq/rules/
cp SECURITY_STANDARDS.md ../../.amazonq/rules/
```

### Step 3: Verify Rules are Loaded
In Amazon Q Chat, type:
```
@workspace

What rules are available for this project?
```

Amazon Q will automatically include all rules from `.amazonq/rules/` in every chat.

---

## Rule Files Included

1. **PRODUCTION_FIXES.md** - Documents the two critical fixes
2. **AUTHENTICATION_PATTERNS.md** - JWT decoding patterns
3. **FASTAPI_CONVENTIONS.md** - FastAPI best practices
4. **SECURITY_STANDARDS.md** - Security requirements

---

## Using Rules in Amazon Q

### In Chat
```
@workspace

Review this code for authentication issues.
```

### In Inline Chat
Select code + Alt+C (or Option+C on Mac)
```
Does this follow our authentication patterns?
```

### Creating Code
```
@workspace

Create a new authenticated endpoint following our patterns.
```

---

## Next Steps

1. Create `.amazonq/rules/` directory
2. Copy rule files to that directory
3. Restart Amazon Q or reload workspace
4. Test with: `@workspace` + ask a question
5. Amazon Q will now reference your rules automatically

---

**All rules are production-ready and tested.**
