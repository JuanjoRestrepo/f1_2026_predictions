# Application Security Reference

Production security has two mandatory layers: **infrastructure** (covered in SKILL.md) and
**application** (this file). This reference covers authentication, authorization, data protection,
API hardening, and operational security patterns across all stacks in this skill.

---

## 1. Password Security

Never store plaintext passwords. Never use MD5 or SHA-1 for password hashing — they are
cryptographically broken for this purpose.

**Hashing — use Argon2id (preferred) or bcrypt:**

```typescript
// Node.js — argon2 (preferred, winner of Password Hashing Competition)
import argon2 from 'argon2';

const hash = await argon2.hash(password, {
  type: argon2.argon2id,
  memoryCost: 65536, // 64 MB
  timeCost: 3,
  parallelism: 4,
});
const valid = await argon2.verify(hash, candidatePassword);

// Alternatively: bcrypt (widely used, still acceptable)
import bcrypt from 'bcryptjs';
const hash = await bcrypt.hash(password, 12); // cost factor ≥ 12
const valid = await bcrypt.compare(candidatePassword, hash);
```

```python
# Python — passlib with argon2
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
hashed = pwd_context.hash(password)
valid = pwd_context.verify(candidate, hashed)
```

**Password strength validation — enforce on the server, not just the client:**

```typescript
// Use zxcvbn for realistic strength estimation (not just regex rules)
import { zxcvbn } from '@zxcvbn-ts/core';

const result = zxcvbn(password);
if (result.score < 3) {
  throw new Error('Password is too weak');
}

// Minimum baseline rules (apply alongside zxcvbn):
const MIN_LENGTH = 12;
const hasUpper = /[A-Z]/.test(password);
const hasLower = /[a-z]/.test(password);
const hasDigit = /\d/.test(password);
const hasSpecial = /[^A-Za-z0-9]/.test(password);
```

**Breach checking — optional but recommended for high-security apps:**
Use the HaveIBeenPwned Passwords API (k-anonymity model — only sends first 5 chars of SHA-1 hash).

---

## 2. Session Management & Cookie Security

**Never store session tokens in `localStorage` or `sessionStorage`** — they are accessible to
JavaScript and vulnerable to XSS. Always use cookies with the correct flags.

**Secure cookie configuration:**

```typescript
// Express
res.cookie('session_id', token, {
  httpOnly: true, // not accessible via document.cookie — XSS mitigation
  secure: true, // only sent over HTTPS
  sameSite: 'lax', // CSRF mitigation; use "strict" for high-security apps
  maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days in ms
  path: '/',
});

// Next.js (App Router) — via cookies() from next/headers
import { cookies } from 'next/headers';
cookies().set('session_id', token, {
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'lax',
  maxAge: 60 * 60 * 24 * 7,
});
```

**Session invalidation on logout — mandatory:**

```typescript
// Server-side: delete or blacklist the session token from DB/Redis
await db.session.delete({ where: { token } });
// or in Redis:
await redis.del(`session:${token}`);

// Client-side: clear the cookie
res.clearCookie('session_id');
// Clearing the cookie alone is NOT sufficient — always invalidate server-side too
```

**Session fixation prevention:** Regenerate session ID after login — never reuse the pre-auth session token.

---

## 3. JWT Best Practices

JWTs are stateless by design — understand the tradeoffs before choosing them over sessions.

**Do:**

- Use short expiry for access tokens: `15m` to `1h`
- Use longer expiry for refresh tokens: `7d` to `30d`, stored server-side (DB or Redis)
- Sign with asymmetric keys (RS256 / ES256) for multi-service architectures
- Sign with HS256 only for single-service apps where secret rotation is controlled
- Verify signature, expiry, issuer (`iss`), and audience (`aud`) on every request

**Don't:**

- Never store JWTs in `localStorage` — store access token in memory, refresh token in httpOnly cookie
- Never put sensitive data in the payload — it is base64-encoded, not encrypted
- Never use `alg: none`
- Never accept tokens without verifying the signature

**Refresh token rotation pattern:**

```typescript
// On token refresh:
// 1. Validate the incoming refresh token against DB
// 2. Issue a new access token AND a new refresh token
// 3. Invalidate the old refresh token immediately (rotation)
// 4. If an already-used refresh token is presented → revoke the entire family (reuse detection)

async function refreshTokens(incomingRefreshToken: string) {
  const stored = await db.refreshToken.findUnique({
    where: { token: incomingRefreshToken },
  });

  if (!stored || stored.used) {
    // Reuse detected — revoke entire family
    await db.refreshToken.deleteMany({ where: { userId: stored?.userId } });
    throw new UnauthorizedException('Refresh token reuse detected');
  }

  await db.refreshToken.update({
    where: { id: stored.id },
    data: { used: true },
  });

  const newAccessToken = signAccessToken(stored.userId);
  const newRefreshToken = await createRefreshToken(stored.userId);

  return { accessToken: newAccessToken, refreshToken: newRefreshToken };
}
```

---

## 4. Multi-Factor Authentication (MFA)

MFA is the single highest-impact authentication control available. Microsoft's analysis suggests
MFA would have stopped 99.9% of account compromises — but only when implemented correctly on
the **server side**. A flawed MFA implementation can be worse than none, because it creates a
false sense of security while remaining bypassable.

**Source authorities:** OWASP Multifactor Authentication Cheat Sheet, OWASP WSTG Section 4.4.11,
NIST SP800-63B, Synack Red Team documented cases.

### The Core Principle: Server-Side State is the Only Truth

The entire security model of MFA collapses if the server trusts anything the client sends about
the outcome of MFA verification. The server must independently validate the OTP and issue a
new authenticated session only after that validation passes — never before, never based on a
client-reported result.

```
CORRECT FLOW:
1. POST /auth/login { email, password }
   → validate credentials server-side
   → if valid AND mfa_enabled: issue short-lived MFA_PENDING token (signed JWT, 5-min TTL)
   → respond: { mfaPending: true }  ← no session token yet

2. POST /auth/mfa/verify { mfaPendingToken, otpCode }
   → verify MFA_PENDING token signature and expiry (server-side)
   → verify otpCode against stored TOTP secret (server-side, using otpauth/otplib)
   → if BOTH valid: delete pending token, issue full session/access token
   → if either invalid: 401 — never issue session

WRONG FLOW (vulnerable):
1. POST /auth/login → issue full session token
2. POST /auth/mfa/verify → browser checks if response looks like success
   → attacker tampers response → bypassed
```

### Known Bypass Attack Vectors (OWASP WSTG 4.4.11)

These are the most commonly reported MFA vulnerabilities in bug bounty programs. Every one maps
to a specific implementation mistake that must be explicitly prevented.

**1. Response Manipulation (most common)**

The attack: the server returns `{"success": false}` on a wrong OTP. The attacker (via Burp Suite)
intercepts the response and changes it to `{"success": true}` before it reaches the browser.
If the browser's JavaScript decides whether to redirect based on this response value — and the
server has already set a session cookie before verifying MFA — the attacker is in.

Root cause: MFA state tracked client-side; or full session issued before OTP is verified.

Fix: **Never issue a session token until after server-side OTP validation passes.** Use a
short-lived `MFA_PENDING` intermediate token (not a session) between password validation and
OTP validation. The final session token is issued only by the OTP verification endpoint.

```typescript
// ✅ CORRECT — Express/Node.js
import { Router } from 'express';
import { TOTP } from 'otpauth'; // use otpauth, not speakeasy (unmaintained)
import jwt from 'jsonwebtoken';

const router = Router();

// Step 1 — password validation only
router.post('/auth/login', async (req, res) => {
  const { email, password } = req.body;
  const user = await db.user.findUnique({ where: { email } });

  if (!user || !(await argon2.verify(user.passwordHash, password))) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  if (user.mfaEnabled) {
    // Issue a short-lived, signed intermediate token — NOT a session
    const mfaPendingToken = jwt.sign(
      { sub: user.id, purpose: 'mfa_pending' },
      process.env.JWT_SECRET!,
      { expiresIn: '5m' }, // expires in 5 minutes — prevents token hoarding
    );
    // Do NOT set session cookie here
    return res.json({ mfaPending: true, mfaPendingToken });
  }

  // No MFA enabled — issue session directly
  issueSession(res, user.id);
});

// Step 2 — OTP verification only
router.post('/auth/mfa/verify', mfaRateLimiter, async (req, res) => {
  const { mfaPendingToken, otpCode } = req.body;

  // Verify the intermediate token server-side
  let payload: { sub: string; purpose: string };
  try {
    payload = jwt.verify(
      mfaPendingToken,
      process.env.JWT_SECRET!,
    ) as typeof payload;
  } catch {
    return res.status(401).json({ error: 'Invalid or expired MFA session' });
  }

  if (payload.purpose !== 'mfa_pending') {
    return res.status(401).json({ error: 'Invalid token purpose' });
  }

  const user = await db.user.findUnique({ where: { id: payload.sub } });
  if (!user?.mfaSecret)
    return res.status(401).json({ error: 'MFA not configured' });

  // Validate OTP server-side — this is the ONLY place the decision is made
  const totp = new TOTP({
    secret: user.mfaSecret, // stored encrypted in DB
    digits: 6,
    period: 30,
    algorithm: 'SHA1',
  });

  const delta = totp.validate({ token: otpCode, window: 1 }); // window:1 = ±30s clock drift
  if (delta === null) {
    await recordFailedMfaAttempt(user.id); // track for lockout
    return res.status(401).json({ error: 'Invalid OTP' }); // generic — don't say "expired" vs "wrong"
  }

  // OTP valid — now issue full session
  issueSession(res, user.id);
});
```

**2. No Rate Limiting on OTP Endpoint**

A 6-digit TOTP has 1,000,000 possible values, but only ~1.7% are valid at any given 30-second
window (33,333 valid codes). Without rate limiting, an attacker can brute-force the current
valid code in under 30 seconds with automated requests.

Fix: strict rate limiting on the OTP verification endpoint, separate from the login rate limit.

```typescript
import rateLimit from 'express-rate-limit';
import RedisStore from 'rate-limit-redis';
import { redis } from './redis';

// Max 5 OTP attempts per user per 15 minutes — far stricter than the general API limit
export const mfaRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  keyGenerator: (req) => {
    // Key by user ID from the pending token, not by IP (IPs can be shared or rotated)
    const token = req.body.mfaPendingToken;
    try {
      const payload = jwt.decode(token) as { sub?: string };
      return `mfa:${payload?.sub ?? req.ip}`;
    } catch {
      return `mfa:${req.ip}`;
    }
  },
  skipSuccessfulRequests: true,
  standardHeaders: true,
  store: new RedisStore({ sendCommand: (...args) => redis.sendCommand(args) }),
  handler: (req, res) => {
    res
      .status(429)
      .json({ error: 'Too many attempts. Please wait before trying again.' });
  },
});
```

**3. MFA Bypass via Password Reset Flow**

Many applications reset a user's password and then immediately create an authenticated session
without requiring MFA — effectively treating a successful password reset as proof of identity,
bypassing the second factor entirely.

Fix: after a password reset, always force a fresh login with full MFA. Never auto-login.

```typescript
router.post('/auth/reset-password/confirm', async (req, res) => {
  const { token, newPassword } = req.body;
  // validate token, update password...
  await db.user.update({
    where: { id: userId },
    data: { passwordHash: newHash },
  });

  // ✅ CORRECT — never auto-login; force a fresh login including MFA
  return res.json({
    success: true,
    message: 'Password updated. Please log in.',
  });

  // ❌ WRONG — never do this after a password reset
  // issueSession(res, userId);
});
```

**4. MFA Bypass via OAuth / Federated Login**

If a user has local MFA enabled but the application also supports "Login with Google", and
the OAuth flow does not check the `mfaEnabled` flag for that user, an attacker can authenticate
via OAuth and bypass the MFA step entirely.

Fix: MFA enforcement must be tied to the **user record**, not the login method. After any
successful authentication (local OR federated), check `user.mfaEnabled` and enforce accordingly.

```typescript
// OAuth callback — apply same MFA check as local login
router.get(
  '/auth/google/callback',
  passport.authenticate('google'),
  async (req, res) => {
    const user = req.user as User;

    if (user.mfaEnabled) {
      // Same pending token flow as local login — OAuth does not bypass MFA
      const mfaPendingToken = jwt.sign(
        { sub: user.id, purpose: 'mfa_pending' },
        process.env.JWT_SECRET!,
        { expiresIn: '5m' },
      );
      return res.redirect(`/auth/mfa?token=${mfaPendingToken}`);
    }

    issueSession(res, user.id);
  },
);
```

**5. Additional OWASP-Documented Bypass Vectors**

These are less common but equally critical to test and prevent:

- **OIDC flow parameter tampering** — if using Azure B2C or a custom OIDC provider, an attacker may change the `acr_values` parameter from `B2C_1_SignInWithMFA` to `B2C_1_SignIn` to select a flow without MFA. Fix: enforce the MFA flow by name server-side; reject tokens issued by non-MFA policies.
- **X-Forwarded-For IP spoofing** — if MFA is conditionally skipped for trusted IP ranges, verify that `X-Forwarded-For` values come from a trusted reverse proxy, not from the client. Fix: configure Express's `trust proxy` setting correctly; never trust raw `X-Forwarded-For` headers.
- **MFA management CSRF** — disabling MFA should require re-authentication + CSRF token. An attacker with XSS or CSRF can disable MFA silently if not protected.
- **Backup code theft** — recovery/backup codes must be one-time-use and stored hashed (same as passwords). Never store them plaintext.

### TOTP Setup & Enrollment (Production Pattern)

```typescript
import { TOTP, Secret } from 'otpauth'; // npm install otpauth
import QRCode from 'qrcode'; // npm install qrcode

// 1. Generate TOTP secret during MFA enrollment
router.post('/auth/mfa/setup', authenticate, async (req, res) => {
  const user = await db.user.findUnique({ where: { id: req.userId } });
  if (user?.mfaEnabled)
    return res.status(400).json({ error: 'MFA already enabled' });

  const secret = new Secret({ size: 20 }); // 160-bit secret — RFC 4226 minimum

  const totp = new TOTP({
    issuer: 'MyApp',
    label: user!.email,
    secret,
    digits: 6,
    period: 30,
    algorithm: 'SHA1',
  });

  // Store secret temporarily (not committed until user verifies)
  // Encrypt before storing — use AES-256-GCM with a key from your secret manager
  await redis.setex(`mfa:pending:${req.userId}`, 600, encrypt(secret.base32));

  const qrCodeDataUrl = await QRCode.toDataURL(totp.toString());
  return res.json({ qrCode: qrCodeDataUrl, secret: secret.base32 }); // secret for manual entry
});

// 2. Confirm enrollment — user scans QR and enters a valid code
router.post('/auth/mfa/enable', authenticate, async (req, res) => {
  const { otpCode } = req.body;
  const encryptedPending = await redis.get(`mfa:pending:${req.userId}`);
  if (!encryptedPending)
    return res.status(400).json({ error: 'MFA setup session expired' });

  const secretBase32 = decrypt(encryptedPending);
  const totp = new TOTP({
    secret: secretBase32,
    digits: 6,
    period: 30,
    algorithm: 'SHA1',
  });

  if (totp.validate({ token: otpCode, window: 1 }) === null) {
    return res.status(400).json({ error: 'Invalid code — please try again' });
  }

  // Commit: encrypt secret and store in DB
  await db.user.update({
    where: { id: req.userId },
    data: {
      mfaSecret: encrypt(secretBase32), // encrypt at rest — never store plaintext TOTP secrets
      mfaEnabled: true,
      recoveryCodes: await generateHashedRecoveryCodes(), // generate on enrollment
    },
  });

  await redis.del(`mfa:pending:${req.userId}`);

  // Invalidate all existing sessions — force re-login with MFA
  await db.session.deleteMany({ where: { userId: req.userId } });

  return res.json({ success: true });
});
```

### Recovery Codes

Users must have a fallback path if they lose access to their authenticator app. Without it,
MFA becomes a permanent lockout mechanism for legitimate users.

```typescript
import crypto from 'crypto';
import argon2 from 'argon2';

async function generateHashedRecoveryCodes(): Promise<string[]> {
  const codes: string[] = [];

  for (let i = 0; i < 10; i++) {
    // Generate human-readable codes: XXXX-XXXX-XXXX format
    const raw = crypto.randomBytes(6).toString('hex').toUpperCase();
    const formatted = `${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}`;
    codes.push(formatted);
  }

  // Hash each code before storage — treat like passwords
  const hashed = await Promise.all(codes.map((c) => argon2.hash(c)));
  await db.recoveryCode.createMany({
    data: hashed.map((hash) => ({ hash, used: false, userId: req.userId })),
  });

  return codes; // return plaintext ONCE to the user — never show again
}

// Recovery code login — replaces the OTP step
router.post('/auth/mfa/recover', mfaRateLimiter, async (req, res) => {
  const { mfaPendingToken, recoveryCode } = req.body;
  // verify mfaPendingToken...

  const storedCodes = await db.recoveryCode.findMany({
    where: { userId: payload.sub, used: false },
  });

  for (const stored of storedCodes) {
    if (await argon2.verify(stored.hash, recoveryCode)) {
      // Mark as used — one-time only
      await db.recoveryCode.update({
        where: { id: stored.id },
        data: { used: true },
      });
      issueSession(res, payload.sub);
      return;
    }
  }

  return res.status(401).json({ error: 'Invalid recovery code' });
});
```

### MFA Checklist

Add these items to the pre-launch security checklist:

- [ ] MFA state tracked server-side only — full session token issued only after OTP validation
- [ ] Short-lived MFA pending token (≤5 min TTL) used between password check and OTP check
- [ ] Strict rate limiting on OTP endpoint (≤5 attempts per user per 15 min)
- [ ] Password reset does not auto-login — forces fresh login including MFA
- [ ] OAuth/federated login enforces MFA check on the user record, not bypasses it
- [ ] TOTP secrets encrypted at rest in the database (AES-256-GCM or equivalent)
- [ ] Recovery codes hashed before storage (argon2id); single-use; shown to user once
- [ ] MFA disable/change requires re-authentication + CSRF protection
- [ ] Generic error responses — `"Invalid OTP"` only; never `"OTP expired"` vs `"OTP wrong"` (distinguishable by timing oracle)
- [ ] `otpauth` library used (not `speakeasy` — unmaintained since 2021)

---

## 5. Role-Based Access Control (RBAC)

Define roles and permissions explicitly — never rely on frontend-only guards.

**Simple RBAC pattern (DB-backed):**

```typescript
// Prisma schema
model User {
  id    String @id @default(cuid())
  role  Role   @default(USER)
}

enum Role {
  USER
  MODERATOR
  ADMIN
}

// Middleware guard
function requireRole(...roles: Role[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!roles.includes(req.user.role)) {
      return res.status(403).json({ error: "Forbidden" });
    }
    next();
  };
}

// Route usage
router.delete("/posts/:id", authenticate, requireRole("ADMIN", "MODERATOR"), deletePost);
```

**tRPC (T3 Stack) — role-aware procedures:**

```typescript
const adminProcedure = protectedProcedure.use(({ ctx, next }) => {
  if (ctx.session.user.role !== "ADMIN") {
    throw new TRPCError({ code: "FORBIDDEN" });
  }
  return next({ ctx });
});

export const adminRouter = createTRPCRouter({
  deleteUser: adminProcedure.input(z.object({ id: z.string() })).mutation(...),
});
```

**FastAPI — dependency-based RBAC:**

```python
from fastapi import Depends, HTTPException, status

def require_role(*roles: str):
    def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return current_user
    return checker

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, _: User = Depends(require_role("admin"))):
    ...
```

---

## 6. API Rate Limiting

Apply rate limiting at multiple layers: reverse proxy/WAF (preferred) + application level (defense in depth).

**Node.js / Express — `express-rate-limit` + Redis store:**

```typescript
import rateLimit from 'express-rate-limit';
import RedisStore from 'rate-limit-redis';
import { redis } from './redis';

// General API limit
export const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  store: new RedisStore({ sendCommand: (...args) => redis.sendCommand(args) }),
});

// Strict limit for auth endpoints
export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10, // max 10 login attempts per 15 min
  skipSuccessfulRequests: true, // only count failures
  store: new RedisStore({ sendCommand: (...args) => redis.sendCommand(args) }),
});

app.use('/api/', apiLimiter);
app.use('/api/auth/', authLimiter);
```

**FastAPI — `slowapi`:**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/data")
@limiter.limit("100/minute")
async def get_data(request: Request):
    ...

@app.post("/auth/login")
@limiter.limit("10/15minute")
async def login(request: Request):
    ...
```

**WebSocket rate limiting:**

```typescript
// Track message frequency per connection
const messageCount = new Map<string, number>();

wss.on('connection', (ws, req) => {
  const ip = req.socket.remoteAddress!;
  messageCount.set(ip, 0);

  ws.on('message', (data) => {
    const count = (messageCount.get(ip) ?? 0) + 1;
    messageCount.set(ip, count);

    if (count > 60) {
      // max 60 messages/min
      ws.close(1008, 'Rate limit exceeded');
      return;
    }
    // process message
  });

  // Reset counter every minute
  const interval = setInterval(() => messageCount.set(ip, 0), 60_000);
  ws.on('close', () => clearInterval(interval));
});
```

---

## 7. IP Controls (Banning & Whitelisting)

**IP whitelisting — for internal/admin routes:**

```typescript
const ADMIN_WHITELIST = (process.env.ADMIN_IP_WHITELIST ?? '').split(',');

function ipWhitelist(req: Request, res: Response, next: NextFunction) {
  const clientIp = req.ip ?? req.socket.remoteAddress;
  if (!ADMIN_WHITELIST.includes(clientIp!)) {
    return res.status(403).json({ error: 'Access denied' });
  }
  next();
}

app.use('/admin', ipWhitelist);
```

**Dynamic IP banning — Redis-backed:**

```typescript
async function checkIpBan(req: Request, res: Response, next: NextFunction) {
  const ip = req.ip!;
  const banned = await redis.get(`ban:${ip}`);
  if (banned) return res.status(403).json({ error: 'Forbidden' });
  next();
}

// Ban an IP for 24 hours
async function banIp(ip: string, reason: string) {
  await redis.setex(`ban:${ip}`, 86400, reason);
  logger.warn({ ip, reason }, 'IP banned');
}

// Auto-ban after N failed auth attempts (pair with rate limiter)
async function recordFailedAttempt(ip: string) {
  const key = `fail:${ip}`;
  const count = await redis.incr(key);
  await redis.expire(key, 3600);
  if (count >= 20) await banIp(ip, 'Excessive failed login attempts');
}
```

**Production recommendation:** prefer WAF-level IP controls (CloudFlare, AWS WAF, GCP Cloud Armor)
over application-level banning — they block traffic before it reaches your server.

---

## 8. WAF (Web Application Firewall)

A WAF is a mandatory layer for any internet-facing production application. It blocks OWASP Top 10
attacks (SQLi, XSS, RFI, path traversal) at the network edge, before traffic reaches your app.

| Provider                 | Best for          | Notes                                                      |
| ------------------------ | ----------------- | ---------------------------------------------------------- |
| **Cloudflare WAF**       | Most apps         | Free tier available; DDoS + bot protection included        |
| **AWS WAF**              | AWS-hosted apps   | Pair with ALB or CloudFront; managed rule groups available |
| **GCP Cloud Armor**      | GCP-hosted apps   | Adaptive protection with ML-based anomaly detection        |
| **Azure Front Door WAF** | Azure-hosted apps | Integrated with Azure CDN and App Gateway                  |

**Minimum WAF ruleset to enable:**

- OWASP Core Rule Set (CRS)
- Rate limiting rules
- Bot management / challenge pages
- Geo-blocking if your app has no international audience

---

## 9. Generic Error Responses

Never leak internal implementation details in API error responses. Stack traces, ORM error messages,
SQL queries, file paths, and library versions are all exploitable intelligence for an attacker.

```typescript
// ❌ WRONG — leaks Prisma internals
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  res.status(500).json({ error: err.message, stack: err.stack });
});

// ✅ CORRECT — structured generic response, full detail in server logs only
import { logger } from './logger';

app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  const requestId = req.headers['x-request-id'] ?? crypto.randomUUID();

  // Log full detail server-side — never send to client
  logger.error({ err, requestId, path: req.path }, 'Unhandled error');

  // Send generic response with correlation ID for debugging
  res.status(500).json({
    error: 'An unexpected error occurred',
    requestId, // lets you correlate client reports with server logs
  });
});
```

**Distinguish error types — don't treat everything as 500:**

```typescript
// Use a typed error class hierarchy
class AppError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public isOperational = true,
  ) {
    super(message);
  }
}

class ValidationError extends AppError {
  constructor(message: string) {
    super(400, message);
  }
}
class UnauthorizedError extends AppError {
  constructor() {
    super(401, 'Unauthorized');
  }
}
class ForbiddenError extends AppError {
  constructor() {
    super(403, 'Forbidden');
  }
}
class NotFoundError extends AppError {
  constructor(resource: string) {
    super(404, `${resource} not found`);
  }
}

// In error handler:
if (err instanceof AppError) {
  return res.status(err.statusCode).json({ error: err.message });
}
// Anything else is unexpected — log fully, respond generically
```

**FastAPI:**

```python
from fastapi import Request
from fastapi.responses import JSONResponse
import logging, uuid

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.exception("Unhandled error", extra={"request_id": request_id, "path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"error": "An unexpected error occurred", "request_id": request_id},
    )
```

---

## 10. Security Backups

Backups are a security control — ransomware, accidental deletion, and supply chain attacks all require
a working backup strategy to recover from.

**Backup strategy — follow the 3-2-1 rule:**

- **3** copies of the data
- **2** different storage media/services
- **1** copy offsite (different cloud region or provider)

**Automated DB backup (Postgres example — GitHub Actions):**

```yaml
name: Database Backup
on:
  schedule:
    - cron: '0 2 * * *' # daily at 02:00 UTC

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - name: Dump and upload to S3
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          AWS_ACCESS_KEY_ID: ${{ secrets.BACKUP_AWS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.BACKUP_AWS_SECRET }}
        run: |
          DATE=$(date +%Y-%m-%d)
          pg_dump "$DATABASE_URL" | gzip > backup-$DATE.sql.gz
          aws s3 cp backup-$DATE.sql.gz s3://my-backups/db/$DATE.sql.gz \
            --sse aws:kms
          rm backup-$DATE.sql.gz

      - name: Verify backup exists
        run: aws s3 ls s3://my-backups/db/$(date +%Y-%m-%d).sql.gz
```

**Key backup rules:**

- Encrypt backups at rest (AES-256 minimum; KMS-managed keys preferred)
- Test restores on a schedule — an untested backup is not a backup
- Set retention policy: daily for 7 days, weekly for 4 weeks, monthly for 12 months
- Use a dedicated IAM role with write-only access to the backup bucket — compromise of the app cannot delete backups
- For managed DBs (Neon, Supabase, PlanetScale): verify their built-in backup retention matches your RPO

---

## 11. Supply Chain Security (Dependency Attacks)

npm's lifecycle hooks (`preinstall`, `postinstall`) execute arbitrary code from the internet
with full developer privileges the moment you run any install command. You do not need to
**import** a compromised package for it to infect your machine — **installing it is enough**.
This is the primary attack vector for modern JavaScript supply chain attacks across npm, yarn,
bun, and by propagation, PyPI.

### The Threat Landscape

This is not a theoretical risk. Since September 2025, the ecosystem has experienced a
documented wave of escalating attacks confirmed by Wiz, Trend Micro, Splunk, Palo Alto
Unit 42, Snyk, and StepSecurity:

| Incident                  | Date     | Scope                                                                              | Affected ecosystems              |
| ------------------------- | -------- | ---------------------------------------------------------------------------------- | -------------------------------- |
| **Shai-Hulud**            | Sep 2025 | 500+ packages; first self-propagating npm worm                                     | npm                              |
| **Shai-Hulud 2.0**        | Nov 2025 | 796 packages; 132M monthly downloads                                               | npm                              |
| **Axios / Chalk / Debug** | Mar 2026 | High-impact individual packages                                                    | npm                              |
| **Mini Shai-Hulud**       | May 2026 | `@tanstack/*`, `@mistralai/*`, `@bitwarden/cli`, `@opensearch-project/*`, `uipath` | npm → **PyPI** (cross-ecosystem) |

**Cross-ecosystem propagation:** Mini Shai-Hulud demonstrated that a compromised npm maintainer
token can be used to publish malicious packages to PyPI as well, if the same developer maintains
packages on both registries. A single npm install on a developer's machine can expose credentials
that then compromise Python packages used by millions of unrelated users.

**What happens on a compromised install:** the malicious script runs silently, harvests npm
tokens, GitHub tokens, AWS/GCP/Azure credentials, and SSH keys from the local environment;
clones private repositories and makes them public; injects malicious GitHub Actions workflows;
and uses any npm tokens found to publish poisoned versions of every accessible package —
propagating automatically without further attacker involvement.

### Package Manager Risk & Protection Matrix

Not all package managers are equally protected. This is the current state:

| Package manager          | Script execution default | Built-in cooldown              | Recommendation                                            |
| ------------------------ | ------------------------ | ------------------------------ | --------------------------------------------------------- |
| **pnpm v11**             | ❌ Blocked by default    | ✅ 1-day (`minimumReleaseAge`) | **Use this. Best default protection.**                    |
| **pnpm v10**             | ❌ Blocked by default    | ❌ Must configure manually     | Good — add `minimumReleaseAge: "1440"`                    |
| **npm**                  | ✅ Allowed by default    | ❌ None                        | Requires explicit `ignore-scripts=true`                   |
| **yarn (classic/berry)** | ✅ Allowed by default    | ❌ None                        | Requires `enableScripts: false` in `.yarnrc.yml`          |
| **bun**                  | ✅ Allowed by default    | ❌ None                        | Requires `trustedDependencies` allowlist in `bunfig.toml` |

**Primary recommendation:** migrate to pnpm v11. It is the only package manager that ships
with both lifecycle script blocking and version cooldown enabled out of the box — requiring
zero configuration to be protected against the most common attack vector.

### Defense Layer 1 — Block Lifecycle Scripts

#### pnpm v11 (recommended — protected by default, zero config needed)

pnpm v11 blocks all `preinstall`/`postinstall` script execution by default. No configuration
required for the base protection. Maintain an `allowBuilds` allowlist only for packages that
genuinely require native compilation:

```yaml
# pnpm-workspace.yaml — allowBuilds is the ONLY exception mechanism; use it sparingly
allowBuilds:
  - esbuild # compiles its Go binary on install
  - sharp # native libvips image processing
  - bcrypt # native argon/bcrypt addon
  - '@parcel/watcher' # native file system watcher
  - better-sqlite3 # native SQLite bindings
  # justify every entry — "I'm not sure" is not a justification
```

Never use `dangerouslyAllowAllBuilds: true` — this disables the entire protection layer.

#### pnpm v10 (blocked by default — add cooldown manually)

Same script blocking as v11, but `minimumReleaseAge` must be configured explicitly:

```yaml
# pnpm-workspace.yaml
allowBuilds:
  - esbuild
  - sharp

minimumReleaseAge: '1440' # add this — not present by default in v10
blockExoticSubdeps: true
```

#### npm (scripts allowed by default — must opt out)

```ini
# .npmrc — add to project root AND commit to repo
ignore-scripts=true
audit=true
```

For a one-off install without changing global config:

```bash
npm install some-package --ignore-scripts
```

#### yarn berry (scripts allowed by default — must opt out)

```yaml
# .yarnrc.yml
enableScripts: false # blocks all lifecycle scripts

# Per-package exceptions (equivalent to pnpm's allowBuilds):
supportedArchitectures:
  cpu: ['current']
  os: ['current']

# Allowlist packages that need scripts — add only what you've vetted:
packageExtensions:
  'esbuild@*':
    scripts:
      postinstall: 'node install.js'
```

#### bun (scripts allowed by default — must opt out)

```toml
# bunfig.toml
[install]
# List ONLY packages whose scripts you explicitly trust
trustedDependencies = ["esbuild", "sharp"]
# Any package not listed here will have its scripts blocked
```

**Trade-off for all managers:** some legitimate packages require build scripts to compile
native addons (`esbuild`, `sharp`, `bcrypt`, `better-sqlite3`). When scripts are blocked these
will fail with build errors. The fix is always the allowlist — never disabling protection globally.
Treat adding an entry to the allowlist with the same scrutiny as adding a new dependency.

### Defense Layer 2 — Version Cooldown

Most malicious versions are detected and removed from registries within hours. A minimum
release age requirement means you never install a version that was published in the same
window as an active attack.

**pnpm v11 — enabled by default (1440 minutes = 1 day):**

```yaml
# pnpm-workspace.yaml — already active in v11, shown here for explicit documentation
minimumReleaseAge: '1440' # 1 day — pnpm v11 default
# "10080" for 1 week on high-security or enterprise projects
# "0" disables — not recommended
```

**pnpm v10 — must add manually:**

```yaml
# pnpm-workspace.yaml
minimumReleaseAge: '1440' # not present by default — add this
```

**Dependabot — cooldown for automated dependency PRs (supported since July 2025):**

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: 'npm'
    directory: '/'
    schedule:
      interval: 'weekly'
    cooldown:
      default-days: 7 # wait 7 days before raising a PR for any new version
      semver-patch-days: 3 # 3 days for patch-only bumps
```

### Defense Layer 3 — Block Exotic Dependency Sources

Prevent transitive dependencies from resolving via git URLs, direct tarballs, or other
non-registry sources. These bypass all registry-level scanning.

```yaml
# pnpm-workspace.yaml
blockExoticSubdeps: true
```

### Defense Layer 4 — Trust Policy (pnpm v11+)

Prevent installation of a package whose trust level has decreased relative to previous
versions — catches compromised maintainer account takeovers mid-stream:

```yaml
# pnpm-workspace.yaml
trustPolicy: 'no-downgrade'
```

### Defense Layer 5 — Active Scanning

```bash
# Run before every dependency PR merge
pnpm audit --audit-level=high
npm audit --audit-level=high
```

**CI gate — block merges with high/critical findings:**

```yaml
# .github/workflows/audit.yml
- name: Security audit
  run: pnpm audit --audit-level=high
```

**Third-party scanners (strongly recommended for teams):**

| Tool       | Strength                              | Why effective                                                            |
| ---------- | ------------------------------------- | ------------------------------------------------------------------------ |
| **Socket** | PR-level diff analysis                | Flags new/changed `postinstall` scripts before `npm install` is ever run |
| **Snyk**   | Broad vulnerability DB + supply chain | GitHub App + CLI; catches known-bad packages                             |
| **Aikido** | Developer-focused detection           | Fast turnaround on newly compromised packages                            |

Socket is the most effective early-warning tool for this threat class specifically: it compares
the new version's scripts against the previous version at PR review time — before anyone runs
`npm install` — catching injected scripts that weren't there before.

### Defense Layer 6 — Commit and Enforce the Lockfile

A committed lockfile pins every transitive dependency to an exact version and integrity hash.
Without it, `npm install` resolves to "latest compatible" — which can be a freshly published
malicious version.

```bash
# CI: always install from lockfile — never allow fresh resolution
pnpm install --frozen-lockfile
npm ci                           # npm equivalent
yarn install --immutable         # yarn berry equivalent
bun install --frozen-lockfile    # bun equivalent
```

### Minimum Required Configuration by Package Manager

#### pnpm v11 (zero-config baseline — already protected)

```yaml
# pnpm-workspace.yaml — document explicitly even if defaults are active
allowBuilds:
  - esbuild
  - sharp
  # justify every addition

blockExoticSubdeps: true
minimumReleaseAge: '1440' # already default in v11; explicit for clarity
trustPolicy: 'no-downgrade'
```

#### pnpm v10

```yaml
# pnpm-workspace.yaml
allowBuilds:
  - esbuild
  - sharp

blockExoticSubdeps: true
minimumReleaseAge: '1440' # must add manually — not default in v10
trustPolicy: 'no-downgrade'
```

#### npm

```ini
# .npmrc
ignore-scripts=true
audit=true
```

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: 'npm'
    directory: '/'
    schedule:
      interval: 'weekly'
    cooldown:
      default-days: 7
```

#### yarn berry

```yaml
# .yarnrc.yml
enableScripts: false
```

#### bun

```toml
# bunfig.toml
[install]
trustedDependencies = ["esbuild", "sharp"]
```

### If You Suspect Compromise

```bash
# 1. Immediately rotate ALL credentials from your dev environment:
#    npm token, GitHub token/SSH keys, AWS/GCP/Azure credentials, DB passwords, PyPI tokens

# 2. Audit installed packages
pnpm audit
npm audit

# 3. Check for files dropped outside node_modules during install
find . -name "*.sh" -newer package.json -not -path "*/node_modules/*"
find /tmp -maxdepth 1 -newer /tmp 2>/dev/null

# 4. Check for injected GitHub Actions workflows
git log --all --oneline -- .github/workflows/

# 5. Check for repositories unexpectedly made public
#    GitHub → Settings → Repositories → sort by "recently updated"

# 6. Check PyPI packages if you also publish Python — a compromised npm token
#    may have been used to publish malicious PyPI packages under your account

# 7. If a GitHub token was exposed: revoke all tokens, audit org repo access logs
#    GitHub → Settings → Security log → filter by token
```

---

## 13. Active CVEs & Incident Intelligence (2025–2026)

This section tracks critical, confirmed vulnerabilities and real-world incidents directly
relevant to the stacks in this skill. Every entry is sourced from official advisories,
vendor postmortems, or Tier-1 security research. Update this section as new CVEs land.

---

### CVE-2025-29927 — Next.js Middleware Authorization Bypass (CRITICAL, CVSS 9.1)

**Disclosed:** March 21, 2025. **Status:** Patched. **Actively exploited** (GreyNoise confirmed).

**What it is:** Next.js uses an internal HTTP header `x-middleware-subrequest` to mark
requests as internal subrequests, causing middleware to skip execution. This header was
never validated for externally-originating requests. An attacker sends a single crafted
HTTP request with this header — middleware runs zero security checks, and the attacker
reaches any protected route directly.

**Affected versions:**

| Branch | Vulnerable       | Patched                    |
| ------ | ---------------- | -------------------------- |
| 11.x   | 11.1.4+          | No patch — upgrade to 15.x |
| 12.x   | all < 12.3.5     | 12.3.5                     |
| 13.x   | 13.0.0 – 13.5.8  | 13.5.9                     |
| 14.x   | 14.0.1 – 14.2.24 | 14.2.25                    |
| 15.x   | 15.0.1 – 15.2.2  | 15.2.3                     |

**Who is NOT affected:** apps hosted on Vercel or Netlify (headers stripped at the edge);
static export deployments (no middleware execution).

**Immediate fix:**

```bash
# Check current version
cat package.json | grep next

# Upgrade (T3 / Next.js projects)
pnpm add next@latest   # targets 15.x — current safe branch
```

**If immediate upgrade is not feasible — NGINX mitigation:**

```nginx
# nginx.conf — strip the header before it reaches Next.js
server {
    location / {
        # Drop the internal Next.js header from all external requests
        proxy_set_header x-middleware-subrequest "";
        # Or use more_clear_input_headers if ngx_headers_more is installed:
        # more_clear_input_headers "x-middleware-subrequest";
        proxy_pass http://nextjs_upstream;
    }
}
```

**If running behind a Node.js reverse proxy (Express/Fastify):**

```typescript
// Strip the header in your reverse proxy before forwarding to Next.js
app.use((req, res, next) => {
  delete req.headers['x-middleware-subrequest'];
  next();
});
```

**The architectural lesson:** middleware in Next.js centralizes authentication,
logging, and security enforcement across all incoming requests — but this centralization
creates a single point of failure. Critical security checks must be reinforced beyond
middleware, adding redundancy to security layers. Never rely solely on middleware
for authorization. Always validate permissions in route handlers and server actions as well.

---

### CVE-2025-55184 / CVE-2025-55183 — React 19 RSC DoS & Source Code Exposure

**Disclosed:** May 2025 (follow-up to CVE-2025-29927 community research). **Status:** Patched.

**What they are:** a high-severity Denial of Service (CVE-2025-55184) and a
medium-severity Source Code Exposure (CVE-2025-55183) affecting React 19 and frameworks that
use it, including Next.js. Neither allows Remote Code Execution.

**Affected versions:** React 19.0.0 – 19.2.1 and Next.js 13.x – 16.x.

**Fix:** update React to ≥19.3.0 and Next.js to the latest patched version.

```bash
pnpm add react@latest react-dom@latest next@latest
```

---

### CVE-2026-42945 (NGINX Rift) — 18-Year-Old Heap Overflow, RCE (CRITICAL, CVSS 9.2)

**Disclosed:** May 13, 2026. **Status:** Patched. **Actively exploited** (VulnCheck confirmed,
PoC public on GitHub the day patches were released).

**What it is:** a heap buffer overflow in the `ngx_http_rewrite_module`
component, introduced in NGINX 0.6.27 (2008) and undiscovered for 18 years across all versions
up to 1.30.0. The root cause: the script engine uses a two-pass process —
first pass calculates buffer size, second pass writes data — and the internal engine state
changes between these passes, causing a mismatch that overflows the heap.

**Exploitability:** can be exploited remotely, without authentication, via
crafted HTTP requests. On default deployments, exploitation triggers a server restart (DoS).
If ASLR is disabled, exploitation leads to remote code execution.

**Trigger condition:** the vulnerability is triggered when a configuration
uses both `rewrite` and `set` directives together — a common pattern in API gateway configurations.

**Affected versions:** NGINX Plus and NGINX Open Source, all versions 0.6.27 – 1.30.0.

**Additional CVEs in the same disclosure:**

- **CVE-2026-42946** (CVSS 8.3): excessive memory allocation in two modules — causes a ~1 TB key length calculation, crashing the worker
- **CVE-2026-40701** (CVSS 6.3): use-after-free in `ngx_http_ssl_module` during TLS + DNS
- **CVE-2026-42934** (CVSS 6.3): out-of-bounds read in `ngx_http_charset_module`

**Immediate fix:**

```bash
# Check current version
nginx -v

# Ubuntu / Debian
sudo apt update && sudo apt upgrade nginx

# CentOS / RHEL / Amazon Linux
sudo yum update nginx
# or
sudo dnf update nginx

# Verify after upgrade
nginx -v  # must show 1.30.1 or later
```

**If immediate upgrade is not feasible — configuration mitigation:**

```nginx
# Replace unnamed captures with named captures in every affected rewrite directive
# ❌ VULNERABLE — unnamed capture with set directive
rewrite ^/api/(.*)$ /new-api/$1 last;
set $orig_path $1;

# ✅ SAFE — named capture eliminates the state mismatch
rewrite ^/api/(?P<path>.*)$ /new-api/$path last;
set $orig_path $path;
```

**Verify ASLR is enabled on your Linux host** (RCE requires it disabled):

```bash
cat /proc/sys/kernel/randomize_va_space
# Expected output: 2 (full ASLR — default on all modern Linux distros)
# If output is 0: enable immediately
echo 2 > /proc/sys/kernel/randomize_va_space
# Make permanent:
echo "kernel.randomize_va_space = 2" >> /etc/sysctl.conf
sysctl -p
```

---

### GitHub Actions — `pull_request_target` "Pwn Request" (CWE-829)

**Real-world incidents:** Grafana Labs (April 26, 2025 — confirmed; May 17, 2026 — second
incident), TanStack (May 11, 2026 — CVE-2026-45321).

**What it is:** a vulnerable GitHub Action utilizing `pull_request_target`
instead of the safer `pull_request` allows an unauthorized user to execute code from a malicious
branch within a trusted environment.

The critical difference:

| Trigger               | Runs in context of           | Can access secrets? | Safe for forks?  |
| --------------------- | ---------------------------- | ------------------- | ---------------- |
| `pull_request`        | **fork** — no secrets        | ❌ No               | ✅ Yes           |
| `pull_request_target` | **base repo** — full secrets | ✅ Yes              | ❌ **Dangerous** |

`pull_request_target` was designed for trusted operations like labeling and commenting on PRs
from forks, where you need repo write access. It was never designed to check out and run
untrusted fork code with base-repo secrets — but many workflows do exactly this.

**The TanStack attack chain** — the attacker chained three known vulnerability
classes: a `pull_request_target` "Pwn Request" misconfiguration, GitHub Actions cache poisoning
across the fork↔base trust boundary, and runtime memory extraction of the OIDC token from the
Actions runner process — to publish credential-stealing malware under a trusted identity.

**Audit your workflows — find every occurrence:**

```bash
# Find all workflows using pull_request_target in your repo
grep -r "pull_request_target" .github/workflows/

# Find workflows that also check out code (the dangerous combination)
grep -r -A 20 "pull_request_target" .github/workflows/ | grep -i "checkout\|actions/checkout"
```

**The dangerous pattern:**

```yaml
# ❌ CRITICAL — pull_request_target + checkout of fork code = secrets exposed to attacker
on:
  pull_request_target: # runs with base repo secrets

jobs:
  test:
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }} # checks out FORK code with base secrets
      - run: npm test # attacker controls this code
```

**The safe replacement pattern:**

```yaml
# ✅ SAFE — use pull_request for anything that runs untrusted fork code
on:
  pull_request: # runs with fork context — no base secrets exposed
    branches: [main]

jobs:
  test:
    steps:
      - uses: actions/checkout@v4 # checks out fork code safely
      - run: npm test
```

**If you legitimately need `pull_request_target`** (e.g., to label PRs or post comments):

```yaml
# ✅ SAFE — pull_request_target without checking out fork code
on:
  pull_request_target:

jobs:
  label:
    permissions:
      pull-requests: write
    steps:
      # NO checkout step — never run fork code in pull_request_target
      - uses: actions/labeler@v5
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
```

**Cache poisoning defense** — prevent fork PRs from writing to the base-repo cache:

```yaml
# In workflows triggered by pull_request (fork context):
- uses: actions/cache@v4
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    # Add this to prevent fork cache entries from polluting base-repo runs:
    restore-keys: |
      ${{ runner.os }}-node-
```

Additional hardening for all workflows (defense in depth):

```yaml
jobs:
  build:
    permissions:
      contents: read # grant minimum permissions — not write by default
      packages: read
    # Never use: permissions: write-all
```

---

### VS Code Extension Supply Chain Attacks (TeamPCP / UNC6780)

**Incidents:** Nx Console v18.95.0 compromised May 18, 2026 (2.2M installs, live 11 minutes);
GitHub internal breach May 19–20, 2026 (~3,800 internal repositories exfiltrated via poisoned
extension on a developer's device).

**What happens:** the malicious extension executes as soon as a developer
opens any workspace, silently fetching and running an obfuscated payload hidden inside a
dangling orphan commit on the official GitHub repository. The payload harvests GitHub
tokens, npm tokens, AWS/GCP/Azure credentials, SSH keys, and 1Password material from the
workspace.

**Why "11 minutes live" is still dangerous:** the community caught the Nx
Console compromise in 11 minutes — which sounds fast until you realize how many machines
auto-update in that window. VS Code auto-updates extensions in the background without
any prompt. At 2.2 million installs, even 11 minutes represents tens of thousands of
potentially compromised devices.

**Immediate hardening — disable auto-updates in VS Code:**

```json
// .vscode/settings.json (project) or settings.json (global)
{
  "extensions.autoUpdate": false, // never update extensions automatically
  "extensions.autoCheckUpdates": false // don't check in background
}
```

**Review and clean your installed extensions:**

```bash
# List all installed extensions with versions
code --list-extensions --show-versions

# Remove an extension
code --uninstall-extension publisher.extension-name

# Audit: look for extensions recently published that you didn't manually update
# VS Code → Extensions panel → right-click → "Show Extension Version History"
```

**Organizational policy (enforce via settings sync or MDM):**

```json
// VS Code managed policy — restrict extensions to an approved allowlist
{
  "extensions.allowedExtensionsAuthors": [
    "ms-python",
    "ms-vscode",
    "esbenp",
    "dbaeumer",
    "prisma"
    // add only publishers you have vetted
  ]
}
```

**General VS Code extension hygiene:**

- Prefer extensions from Microsoft, verified publishers, or organizations you can audit
- Check the extension's source repository — verify the publisher account matches the repo owner
- Treat any extension that requests workspace file access as high-risk
- Subscribe to security advisories for extensions you depend on (GitHub → Watch → Security alerts)

---

### Incident Summary Table (2025–2026)

| Date     | CVE / Incident              | Component          | Severity    | Status                                  |
| -------- | --------------------------- | ------------------ | ----------- | --------------------------------------- |
| Mar 2025 | CVE-2025-29927              | Next.js middleware | CVSS 9.1    | Patched; actively exploited             |
| May 2025 | CVE-2025-55184/55183        | React 19 + Next.js | High/Medium | Patched                                 |
| Apr 2025 | Grafana Pwn Request         | GitHub Actions     | Critical    | Contained                               |
| May 2026 | CVE-2026-45321              | TanStack npm       | Critical    | Packages deprecated                     |
| May 2026 | CVE-2026-42945 (NGINX Rift) | NGINX ≤1.30.0      | CVSS 9.2    | Patched; actively exploited             |
| May 2026 | Nx Console / GitHub breach  | VS Code extension  | Critical    | Extension pulled; investigation ongoing |

---

## 12. Security Checklist (Pre-launch)

Use this before going to production on any project:

**Multi-Factor Authentication**

- [ ] MFA available for all users; mandatory for admins and high-privilege accounts
- [ ] Full session token issued only after server-side OTP validation — never before
- [ ] Short-lived MFA pending token (≤5 min) bridges password and OTP steps
- [ ] Rate limiting on OTP endpoint (≤5 attempts / user / 15 min)
- [ ] Password reset does not auto-login; forces fresh authentication including MFA
- [ ] OAuth/federated login enforces MFA on the user record
- [ ] TOTP secrets encrypted at rest in DB
- [ ] Recovery codes hashed (argon2id); single-use; shown to user exactly once
- [ ] MFA disable/change requires re-authentication + CSRF token
- [ ] `otpauth` library used — not the unmaintained `speakeasy`

**Active CVEs & Tooling**

- [ ] Next.js ≥15.2.3 (or per-branch patch); `x-middleware-subrequest` header stripped at proxy if on older version
- [ ] Security checks duplicated in route handlers — never rely on middleware alone
- [ ] React ≥19.3.0 if using RSC
- [ ] NGINX ≥1.30.1 (CVE-2026-42945 / Nginx Rift); ASLR enabled (`randomize_va_space = 2`)
- [ ] `pull_request_target` audited in all GitHub Actions workflows; no `checkout` + fork code in `pull_request_target` context
- [ ] VS Code extension auto-update disabled (`extensions.autoUpdate: false`) on all developer machines
- [ ] Installed VS Code extensions audited; no unrecognized recently-updated extensions

**Supply Chain**

- [ ] Using **pnpm v11** (best default protection) or scripts explicitly blocked for npm/yarn/bun
- [ ] pnpm: `allowBuilds` allowlist configured; never `dangerouslyAllowAllBuilds`
- [ ] npm: `ignore-scripts=true` in `.npmrc`; yarn: `enableScripts: false`; bun: `trustedDependencies` allowlist
- [ ] `minimumReleaseAge: "1440"` set (pnpm v10 — already default in v11)
- [ ] `blockExoticSubdeps: true` set (pnpm)
- [ ] `trustPolicy: "no-downgrade"` set (pnpm v11+)
- [ ] Dependabot cooldown configured (`default-days: 7`)
- [ ] Lockfile committed; CI uses `--frozen-lockfile` / `npm ci` / `yarn --immutable`
- [ ] Socket, Snyk, or Aikido integrated for PR-level scanning
- [ ] `pnpm audit` / `npm audit` in CI blocks on high severity

**Authentication & Authorization**

- [ ] Passwords hashed with Argon2id or bcrypt (cost ≥ 12)
- [ ] Password strength enforced server-side
- [ ] Session tokens in httpOnly + Secure + SameSite cookies
- [ ] Session invalidated server-side on logout
- [ ] JWT expiry ≤ 1h; refresh tokens rotated on use
- [ ] RBAC enforced server-side on every sensitive route

**API & Transport**

- [ ] Rate limiting on all endpoints; stricter on auth routes
- [ ] Rate limiting on WebSocket message frequency
- [ ] HTTPS enforced; HTTP redirects to HTTPS
- [ ] Security headers set (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- [ ] WAF enabled (Cloudflare / AWS WAF / GCP Cloud Armor)
- [ ] CORS configured to allowed origins only — never `*` in production

**Data & Error Handling**

- [ ] All user input validated server-side (Zod / Pydantic / Joi)
- [ ] Parameterized queries / ORM used — no raw string SQL interpolation
- [ ] Error responses are generic — no stack traces or internal messages sent to client
- [ ] Sensitive fields excluded from API responses (passwords, tokens, internal IDs)
- [ ] PII minimized — don't store what you don't need

**Infrastructure**

- [ ] Secrets in secret manager — not in `.env` files on servers
- [ ] Dependency audit passing (`npm audit`, `pip-audit`)
- [ ] Backup strategy implemented and restore tested
- [ ] Least-privilege IAM roles — no wildcard permissions in production
- [ ] IP whitelisting on admin/internal routes
- [ ] Logging in place — errors logged with correlation IDs, no sensitive data in logs
