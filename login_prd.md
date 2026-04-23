# PRD: User Login & Password Reset

## Overview
We are adding email/password authentication to the web app.
Target release: Q2 2026.

## Requirements

### REQ-1: User Login
Users can log in with email and password on `/login`.
- Email field: valid email format required, max 254 chars
- Password field: min 8 chars, max 128 chars
- On success: redirect to `/dashboard`, set `session` cookie (HttpOnly, Secure, SameSite=Lax), expiry 7 days
- On failure: show "Invalid credentials" — never reveal whether email exists
- Passwords stored as bcrypt (cost 12)

### REQ-2: Input Validation
- Both fields required; submit button disabled until both are filled
- Client-side email format check before submit
- Server must re-validate all inputs; never trust client

### REQ-3: Rate Limiting
- Max 5 failed login attempts per email within 60 seconds
- 6th attempt returns HTTP 429 with `Retry-After` header
- Limiter resets after 15 minutes of no failed attempts
- Successful login resets the counter

### REQ-4: Password Reset
- "Forgot password?" link on login page → `/forgot-password`
- User enters email → system always returns "If the email exists, a reset link was sent" (no enumeration)
- Reset email sent within 30 seconds (SLA)
- Reset token: 32-byte random, single-use, expires in 1 hour
- Reset page: `/reset-password?token=...` — new password must meet same rules as REQ-1

### REQ-5: Accessibility
- All form fields have labels
- Error messages announced to screen readers (aria-live)
- Keyboard navigation works (tab, enter to submit)
- Color contrast meets WCAG AA

## API Endpoints
- `POST /api/auth/login` — body: `{email, password}`, returns `{user, sessionExpiresAt}` or 401
- `POST /api/auth/forgot` — body: `{email}`, always 200
- `POST /api/auth/reset` — body: `{token, password}`, returns 200 or 400

## Out of Scope
- SSO / OAuth (Phase 2)
- 2FA (Phase 2)
- Account lockout notifications via email
