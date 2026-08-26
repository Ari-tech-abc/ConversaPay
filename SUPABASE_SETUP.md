# Supabase Dashboard Configuration

## Current Issue
The Google OAuth flow is returning tokens via hash fragment (implicit flow) to `www.conversapay.org` instead of redirecting to `/auth/callback` with a code (PKCE flow).

## Required Changes in Supabase Dashboard

### 1. Authentication → URL Configuration

**Site URL:**
```
https://conversapay.org
```

**Redirect URLs** (add both):
```
https://conversapay.org/auth/callback
https://www.conversapay.org/auth/callback
```

### 2. Authentication → Settings

**Auth flow type:**
- Change from: `Implicit flow`
- Change to: `PKCE flow`

This ensures tokens are returned as query parameters (`?code=...`) instead of hash fragments (`#access_token=...`).

### 3. Authentication → Providers → Google

**Enable Google provider:**
- Toggle: ON
- Client ID: (from Google Cloud Console)
- Client Secret: (from Google Cloud Console)
- Authorized Client IDs: (optional, leave empty unless needed)

**Google Cloud Console Setup:**
1. Go to https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client ID (Web application)
3. Authorized JavaScript origins:
   ```
   https://conversapay.org
   https://www.conversapay.org
   ```
4. Authorized redirect URIs:
   ```
   https://uldbxzarukmrpujayigg.supabase.co/auth/v1/callback
   ```
   (Replace `uldbxzarukmrpujayigg` with your actual Supabase project ID)

### 4. After Configuration

Once you've updated the Supabase dashboard:
1. Test the Google login flow
2. It should now redirect to `https://conversapay.org/auth/callback?code=...`
3. The `auth-callback.html` will exchange the code for a session
4. User will be redirected to `/dashboard`

## Files Modified

- `frontend/html/home.html` - Added redirect script to handle hash fragment tokens
- `frontend/html/auth-callback.html` - Already supports both PKCE and implicit flow

## Fallback Behavior

If Supabase still uses implicit flow, the redirect script in `home.html` will:
1. Detect `access_token` or `refresh_token` in the hash fragment
2. Redirect to `/auth/callback` with the same hash
3. `auth-callback.html` will process the tokens and complete authentication