# Test Cases (24)

## Summary

- **Priority:** P0: 12, P1: 10, P2: 2
- **Type:** security: 8, boundary: 6, functional: 5, accessibility: 3, negative: 1, performance: 1
- **Target:** ui: 15, api: 7, manual: 2

## Overview

| ID | REQ | Title | Type | Target | Priority | Auto |
|----|-----|-------|------|--------|----------|------|
| TC-001 | REQ-1 | Login succeeds with valid email and password | functional | ui | P0 | ✓ |
| TC-002 | REQ-1 | Login fails with correct email but wrong password | negative | ui | P0 | ✓ |
| TC-003 | REQ-1 | Login fails with unregistered email — same message as wrong password (no enumeration) | security | ui | P0 | ✓ |
| TC-004 | REQ-1 | Session cookie has correct security flags | security | ui | P0 | ✓ |
| TC-005 | REQ-2 | Sign In button disabled when email field is empty | functional | ui | P1 | ✓ |
| TC-006 | REQ-2 | Sign In button disabled when password field is empty | functional | ui | P1 | ✓ |
| TC-007 | REQ-2 | Client-side email format validation rejects malformed addresses | boundary | ui | P1 | ✓ |
| TC-008 | REQ-2 | Server rejects 300-character email (exceeds 254 max) | boundary | api | P1 | ✓ |
| TC-009 | REQ-2 | Login rejects SQL injection in email field | security | ui | P0 | ✓ |
| TC-010 | REQ-2 | Login form escapes XSS payload in email field | security | ui | P0 | ✓ |
| TC-011 | REQ-2 | Password with exactly 8 chars is accepted | boundary | api | P1 | ✓ |
| TC-012 | REQ-2 | Password with 129 chars is rejected | boundary | api | P1 | ✓ |
| TC-013 | REQ-3 | 6th failed login within 60s returns 429 with Retry-After | boundary | api | P0 | ✓ |
| TC-014 | REQ-3 | Rate limit is per-email (different email from same IP not blocked) | security | api | P0 | ✓ |
| TC-015 | REQ-3 | Successful login resets the failed-attempt counter | functional | api | P1 | ✓ |
| TC-016 | REQ-4 | Forgot password link on /login navigates to /forgot-password | functional | ui | P1 | ✓ |
| TC-017 | REQ-4 | Forgot-password response is identical for existing and non-existent email | security | ui | P0 | ✓ |
| TC-018 | REQ-4 | Reset token is single-use | security | ui | P0 | ✓ |
| TC-019 | REQ-4 | Reset token older than 1 hour is rejected | boundary | api | P0 | ✓ |
| TC-020 | REQ-4 | Reset link rejects tampered/malformed tokens | security | ui | P0 | ✓ |
| TC-021 | REQ-4 | Reset email arrives within 30 seconds (SLA) | performance | manual | P2 | — |
| TC-022 | REQ-5 | All login form fields have accessible labels | accessibility | ui | P1 | ✓ |
| TC-023 | REQ-5 | Keyboard-only login works (Tab + Enter) | accessibility | ui | P1 | ✓ |
| TC-024 | REQ-5 | Error messages announced via aria-live | accessibility | manual | P2 | — |

## Details

### TC-001: Login succeeds with valid email and password

**Requirement:** REQ-1  
**Type:** functional  |  **Target:** ui  |  **Priority:** P0

**Preconditions:**
- User active@test.com exists
- App reachable at BASE_URL

**Steps:**
1. Navigate to /login
2. Enter email _(data: `active@test.com`)_
3. Enter password _(data: `ValidPass123!`)_
4. Click Sign In

**Expected:** Redirected to /dashboard within 2s; session cookie set (HttpOnly, Secure, SameSite=Lax); cookie expiry ~7 days from now

---

### TC-002: Login fails with correct email but wrong password

**Requirement:** REQ-1  
**Type:** negative  |  **Target:** ui  |  **Priority:** P0

**Preconditions:**
- User active@test.com exists

**Steps:**
1. Navigate to /login
2. Enter email _(data: `active@test.com`)_
3. Enter password _(data: `WrongPass999`)_
4. Click Sign In

**Expected:** Error message 'Invalid credentials' shown; no session cookie set; user stays on /login

---

### TC-003: Login fails with unregistered email — same message as wrong password (no enumeration)

**Requirement:** REQ-1  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Steps:**
1. Navigate to /login
2. Enter email _(data: `ghost@nowhere.com`)_
3. Enter password _(data: `anything123`)_
4. Click Sign In

**Expected:** Error text is EXACTLY 'Invalid credentials' — identical to TC-002. No hint that email doesn't exist.

---

### TC-004: Session cookie has correct security flags

**Requirement:** REQ-1  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Steps:**
1. Perform successful login as active@test.com
2. Inspect cookies for domain

**Expected:** session cookie present; HttpOnly=true; Secure=true; SameSite=Lax; expires ~7 days

---

### TC-005: Sign In button disabled when email field is empty

**Requirement:** REQ-2  
**Type:** functional  |  **Target:** ui  |  **Priority:** P1

**Steps:**
1. Navigate to /login
2. Leave email blank, type password _(data: `ValidPass123!`)_

**Expected:** Sign In button is disabled

---

### TC-006: Sign In button disabled when password field is empty

**Requirement:** REQ-2  
**Type:** functional  |  **Target:** ui  |  **Priority:** P1

**Steps:**
1. Navigate to /login
2. Type email, leave password blank _(data: `active@test.com`)_

**Expected:** Sign In button is disabled

---

### TC-007: Client-side email format validation rejects malformed addresses

**Requirement:** REQ-2  
**Type:** boundary  |  **Target:** ui  |  **Priority:** P1

**Steps:**
1. Navigate to /login
2. Enter invalid email _(data: `not-an-email`)_
3. Tab out of field

**Expected:** Inline validation error appears; form does not submit

---

### TC-008: Server rejects 300-character email (exceeds 254 max)

**Requirement:** REQ-2  
**Type:** boundary  |  **Target:** api  |  **Priority:** P1

**Steps:**
1. POST /api/auth/login with 300-char email

**Expected:** Response 400; error field indicates email length

---

### TC-009: Login rejects SQL injection in email field

**Requirement:** REQ-2  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Steps:**
1. Navigate to /login
2. Enter email _(data: `admin' OR '1'='1`)_
3. Enter password _(data: `anything`)_
4. Click Sign In

**Expected:** Error 'Invalid credentials'; no session cookie; server log shows no DB error

---

### TC-010: Login form escapes XSS payload in email field

**Requirement:** REQ-2  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Steps:**
1. Navigate to /login
2. Enter email _(data: `<script>alert(1)</script>@x.com`)_
3. Click Sign In

**Expected:** No alert dialog; any reflected text is escaped as literal characters

---

### TC-011: Password with exactly 8 chars is accepted

**Requirement:** REQ-2  
**Type:** boundary  |  **Target:** api  |  **Priority:** P1

**Preconditions:**
- User with 8-char password exists

**Steps:**
1. POST /api/auth/login with 8-char password

**Expected:** 200 OK; user object returned

---

### TC-012: Password with 129 chars is rejected

**Requirement:** REQ-2  
**Type:** boundary  |  **Target:** api  |  **Priority:** P1

**Steps:**
1. POST /api/auth/login with 129-char password

**Expected:** 400 Bad Request

---

### TC-013: 6th failed login within 60s returns 429 with Retry-After

**Requirement:** REQ-3  
**Type:** boundary  |  **Target:** api  |  **Priority:** P0

**Preconditions:**
- User active@test.com exists

**Steps:**
1. POST /api/auth/login with wrong password 5 times _(data: `active@test.com`)_
2. POST /api/auth/login 6th time with wrong password

**Expected:** Attempts 1-5 return 401; attempt 6 returns 429; Retry-After header present and numeric

---

### TC-014: Rate limit is per-email (different email from same IP not blocked)

**Requirement:** REQ-3  
**Type:** security  |  **Target:** api  |  **Priority:** P0

**Preconditions:**
- Users a@test.com and b@test.com exist

**Steps:**
1. Fail login 5x for a@test.com
2. Attempt valid login for b@test.com from same test

**Expected:** b@test.com login returns 200, not 429 (limiter must be keyed by email)

---

### TC-015: Successful login resets the failed-attempt counter

**Requirement:** REQ-3  
**Type:** functional  |  **Target:** api  |  **Priority:** P1

**Steps:**
1. Fail login 4 times for active@test.com
2. Successfully log in
3. Fail login 3 more times

**Expected:** No 429 triggered — counter reset after successful login

---

### TC-016: Forgot password link on /login navigates to /forgot-password

**Requirement:** REQ-4  
**Type:** functional  |  **Target:** ui  |  **Priority:** P1

**Steps:**
1. Navigate to /login
2. Click 'Forgot password?' link

**Expected:** URL becomes /forgot-password; email input visible

---

### TC-017: Forgot-password response is identical for existing and non-existent email

**Requirement:** REQ-4  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Steps:**
1. Submit forgot form for active@test.com; capture message + timing
2. Submit forgot form for ghost@nowhere.com; capture message + timing

**Expected:** Both show 'If the email exists, a reset link was sent.' Response time differs by <100ms.

---

### TC-018: Reset token is single-use

**Requirement:** REQ-4  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Preconditions:**
- Valid reset token obtained via test seam or mailbox API

**Steps:**
1. Open /reset-password?token=<valid>
2. Submit new password _(data: `NewValidPass1!`)_
3. Return to /reset-password?token=<same>
4. Attempt to submit another new password

**Expected:** First submit succeeds; second attempt shows 'This link has expired or been used'

---

### TC-019: Reset token older than 1 hour is rejected

**Requirement:** REQ-4  
**Type:** boundary  |  **Target:** api  |  **Priority:** P0

**Preconditions:**
- Test seam to generate expired token

**Steps:**
1. POST /api/auth/reset with token aged 61 minutes

**Expected:** 400 Bad Request; error code indicates expiration

---

### TC-020: Reset link rejects tampered/malformed tokens

**Requirement:** REQ-4  
**Type:** security  |  **Target:** ui  |  **Priority:** P0

**Steps:**
1. Open /reset-password?token=invalid
2. Submit new password _(data: `NewValidPass1!`)_

**Expected:** Error shown; password NOT changed for any user

---

### TC-021: Reset email arrives within 30 seconds (SLA)

**Requirement:** REQ-4  
**Type:** performance  |  **Target:** manual  |  **Priority:** P2

**Preconditions:**
- Live email queue
- Access to real inbox

**Steps:**
1. Request reset for real email address
2. Time stamp arrival in inbox

**Expected:** Email in inbox within 30s; verified manually as flaky in automation

---

### TC-022: All login form fields have accessible labels

**Requirement:** REQ-5  
**Type:** accessibility  |  **Target:** ui  |  **Priority:** P1

**Steps:**
1. Navigate to /login
2. Run axe-core scan

**Expected:** Zero violations for 'label', 'aria-input-field-name', 'form-field-multiple-labels'

---

### TC-023: Keyboard-only login works (Tab + Enter)

**Requirement:** REQ-5  
**Type:** accessibility  |  **Target:** ui  |  **Priority:** P1

**Steps:**
1. Navigate to /login
2. Press Tab to focus email; type
3. Tab to password; type
4. Press Enter

**Expected:** Form submits; dashboard loads without touching mouse

---

### TC-024: Error messages announced via aria-live

**Requirement:** REQ-5  
**Type:** accessibility  |  **Target:** manual  |  **Priority:** P2

**Preconditions:**
- Screen reader (NVDA or VoiceOver) available

**Steps:**
1. Navigate to /login with screen reader on
2. Submit wrong password

**Expected:** Screen reader announces 'Invalid credentials' without requiring user to navigate to error

---
