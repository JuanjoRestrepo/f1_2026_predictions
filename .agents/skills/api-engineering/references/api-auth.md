# API Authentication — OAuth2/2.1 & JWT for Machine-to-Machine Integration

**Scope note:** this file covers authentication **between systems** — your app calling a
third-party API, a third-party acting on a user's behalf against your API, or service-to-service
calls. For authenticating end users logging into your own application (sessions, cookies,
password/MFA flows), see `web-devops/references/security.md` Sections 2–4 — that content
remains authoritative for that context and is not duplicated here.

**Sources:** RFC 6749 (OAuth 2.0 Authorization Framework, 2012); RFC 7636 (PKCE); RFC 9700
(OAuth 2.0 Security Best Current Practice, IETF, published January 2025); OAuth 2.1
(draft-ietf-oauth-v2-1, IETF Internet-Draft — not yet a final RFC as of 2026, but its
requirements are already the enforced baseline across all major identity providers, and are
mandated by the Model Context Protocol specification for remote servers); RFC 7519 (JWT);
RFC 8725 (JWT Best Current Practices).

---

## 1. OAuth 2.1 — The Current Baseline (2026)

OAuth 2.1 is not a new protocol — it consolidates a decade of security lessons scattered
across RFC 6749, RFC 7636 (PKCE), RFC 8252 (native apps), and the OAuth Security BCP into one
document, while removing flows that were consistently misused in practice. It remains an IETF
Internet-Draft, not a ratified RFC, but treat its requirements as mandatory for any new
integration in 2026 — every major identity provider (Auth0, Okta, Microsoft Entra, Google)
already enforces them.

**What changed from OAuth 2.0:**

```
❌ REMOVED: Implicit Grant (response_type=token)
   Returned tokens directly in the URL fragment — vulnerable to token leakage via
   browser history, referrer headers, and logs. Use Authorization Code + PKCE instead,
   even for single-page apps and mobile apps.

❌ REMOVED: Resource Owner Password Credentials (ROPC) Grant
   Required the client to collect the user's raw username/password. Defeats the entire
   purpose of OAuth (never expose the user's credentials to a third-party client).

✅ MANDATORY: PKCE (Proof Key for Code Exchange) for ALL clients using Authorization Code
   Previously optional/recommended for public clients only — now required universally,
   including confidential (server-side, client-secret-holding) clients.

✅ MANDATORY: Exact redirect URI string matching
   No more partial/prefix matching — closes an open redirect / authorization code
   interception attack vector.
```

### Grant Type Selection — The Decision That Matters Most

Using the wrong grant type is the single most common OAuth2 integration mistake.

| Grant Type                    | Use when                                                                                                                                   | Do NOT use when                                                                                     |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| **Authorization Code + PKCE** | A user is present and authorizes your app to act on their behalf against another service (e.g., "Connect your Google Calendar")            | No user is present — this requires a browser redirect and user interaction                          |
| **Client Credentials**        | Your backend calls another service's API as _itself_, with no user involved (service-to-service, RPA bot calling a partner API)            | A user's specific permissions/identity need to flow through — this grant has no user context at all |
| **Device Code**               | Authorizing on a device with no browser or limited input (CLI tools, smart TVs, IoT)                                                       | A normal browser-based flow is available — Device Code is a fallback, not a default                 |
| **Refresh Token**             | Not a grant type itself — used to obtain a new access token without re-prompting the user, after an Authorization Code or Device Code flow | Never issue long-lived refresh tokens to public clients without rotation                            |

**For RPA and backend integration work, Client Credentials is overwhelmingly the most common
correct choice** — a bot or backend service authenticating to a partner API has no end user
in the loop.

### Client Credentials Grant — Service-to-Service (the RPA-relevant case)

```typescript
// Node.js — obtaining and using a Client Credentials token
async function getAccessToken(): Promise<string> {
  const response = await fetch('https://auth.partner.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: process.env.PARTNER_CLIENT_ID!,
      client_secret: process.env.PARTNER_CLIENT_SECRET!,
      scope: 'orders:read orders:write',
    }),
  });

  if (!response.ok) throw new Error(`Token request failed: ${response.status}`);
  const data = await response.json();
  return data.access_token;
}

// Cache the token — Client Credentials tokens are typically valid for 1 hour;
// re-fetching on every call wastes a round trip and can trigger rate limits
class TokenCache {
  private token: string | null = null;
  private expiresAt = 0;

  async getToken(): Promise<string> {
    if (this.token && Date.now() < this.expiresAt - 60_000) {
      // 60s safety margin
      return this.token;
    }
    const { access_token, expires_in } = await this.fetchNewToken();
    this.token = access_token;
    this.expiresAt = Date.now() + expires_in * 1000;
    return this.token;
  }
}
```

```python
# Python — same pattern with httpx
import time
import httpx


class ClientCredentialsTokenCache:
    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._token: str | None = None
        self._expires_at: float = 0

    async def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:  # 60s safety margin
            return self._token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": self._scope,
                },
            )
            response.raise_for_status()
            data = response.json()

        self._token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]
        return self._token
```

### Authorization Code + PKCE — When a User Authorizes Your App

```typescript
// Step 1 — generate PKCE verifier and challenge, redirect user to authorize
import crypto from 'crypto';

function generatePKCE() {
  const verifier = crypto.randomBytes(32).toString('base64url');
  const challenge = crypto
    .createHash('sha256')
    .update(verifier)
    .digest('base64url');
  return { verifier, challenge };
}

const { verifier, challenge } = generatePKCE();
// Store `verifier` server-side (session or short-lived cache), keyed to this auth attempt

const authUrl = new URL('https://partner.com/oauth/authorize');
authUrl.searchParams.set('response_type', 'code');
authUrl.searchParams.set('client_id', process.env.CLIENT_ID!);
authUrl.searchParams.set('redirect_uri', 'https://myapp.com/oauth/callback');
authUrl.searchParams.set('code_challenge', challenge);
authUrl.searchParams.set('code_challenge_method', 'S256');
authUrl.searchParams.set('scope', 'read write');
// Redirect the user to authUrl

// Step 2 — exchange the returned code for tokens, presenting the original verifier
async function exchangeCodeForToken(code: string, verifier: string) {
  const response = await fetch('https://partner.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: 'https://myapp.com/oauth/callback',
      client_id: process.env.CLIENT_ID!,
      code_verifier: verifier, // proves this client initiated the original request
    }),
  });
  return response.json(); // { access_token, refresh_token, expires_in }
}
```

---

## 2. JWT for API Consumers — Validation, Not Just Issuance

If you consume an API that issues JWTs, or your API accepts JWTs from a third-party identity
provider, validation discipline matters as much as issuance discipline (covered for your own
auth system in `web-devops/security.md`).

**Mandatory validation checklist (RFC 8725 — JWT Best Current Practices):**

```typescript
import { jwtVerify, createRemoteJWKSet } from 'jose';

// Fetch and cache the issuer's public keys (JWKS) — never hardcode a public key
const JWKS = createRemoteJWKSet(
  new URL('https://partner.com/.well-known/jwks.json'),
);

async function validateIncomingToken(token: string) {
  const { payload } = await jwtVerify(token, JWKS, {
    issuer: 'https://partner.com', // MUST match exactly — prevents token substitution
    audience: 'https://myapi.com', // MUST match — this token is for YOU specifically
    // algorithms is implicitly restricted by JWKS key type — never allow "alg: none"
  });

  // Additional checks beyond signature verification:
  if (payload.exp && Date.now() >= payload.exp * 1000) {
    throw new Error('Token expired'); // jose already checks this, shown for clarity
  }

  return payload;
}
```

**The critical mistakes RFC 8725 exists to prevent:**

- **Algorithm confusion attack**: never accept `alg: none`, and never allow the token to
  dictate which algorithm family is used for verification — the verifier must enforce the
  expected algorithm, not trust the token's header
- **Missing `aud` (audience) validation**: without it, a token issued for Service A can be
  replayed against Service B if both trust the same issuer
- **Missing `iss` (issuer) validation**: without it, a token from an untrusted issuer with the
  same signing infrastructure could be accepted
- **Hardcoded public keys**: identity providers rotate signing keys; always fetch from the
  JWKS endpoint and cache with appropriate TTL, never pin a key long-term

---

## 3. Service-to-Service Credential Storage

Client Credentials secrets and API keys used for M2M integration require the same handling
discipline as any other secret (see `web-devops/security.md` Section 1 for the general
principles) — but with integration-specific considerations:

```bash
# Never commit — use a secret manager, scoped per integration
# AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault, Doppler, Infisical

# Rotate on a schedule — client secrets for long-lived integrations should rotate
# quarterly at minimum, more frequently for high-value integrations (payments, banking)

# Scope minimally — request only the OAuth scopes the integration actually needs
# scope: "orders:read"  — not  scope: "*"  or  scope: "admin"
```

**For RPA specifically:** credentials for bot-to-system integrations are often stored in
Windows Credential Manager, an orchestrator's credential vault (UiPath Orchestrator, Power
Automate connections), or environment-specific secret stores — never in plaintext config
files or hardcoded in workflow definitions, regardless of how "internal-only" the automation
appears to be.

---

## 4. When NOT to Use OAuth2

- **A single trusted internal service calling another internal service within the same
  security perimeter** (e.g., inside a private VPC, behind a service mesh) — mutual TLS
  (mTLS) or a simpler static API key over an already-authenticated network boundary is often
  sufficient and avoids OAuth's operational overhead (token endpoint, expiry handling, refresh
  logic) for a problem that network-level trust already solves
- **Simple API key authentication is explicitly appropriate when**: the API has no need for
  fine-grained scopes, the caller identity itself (not delegated user identity) is what matters,
  and the integration surface is small enough that key rotation can be managed manually or via
  simple tooling — many internal and B2B APIs correctly use a static API key rather than OAuth
