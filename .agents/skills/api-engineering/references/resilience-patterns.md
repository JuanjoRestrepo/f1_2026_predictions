# Resilience Patterns — Retries, Circuit Breakers, Idempotency, Rate Limiting

The highest-value reference in this skill for integration and automation work. Every pattern
here defends against a specific, named failure mode — never apply one without understanding
which failure it prevents.

**Sources:** RFC 6585 (Additional HTTP Status Codes — defines 429); IETF
draft-ietf-httpqos-rate-limit-headers (RateLimit header fields); AWS Architecture Blog,
"Exponential Backoff and Jitter" (Marc Brooker, 2015 — the canonical algorithm); Google SRE
Book, Chapter 22 (Addressing Cascading Failures); Martin Fowler, "CircuitBreaker" (2014);
Michael Nygard, _Release It!_ (2007, 2nd ed. 2018 — origin of the Circuit Breaker pattern in
software); Stripe API documentation on idempotent requests (the reference implementation);
IETF draft-ietf-httpapi-idempotency-key-header (standardizing the Idempotency-Key header,
2025–2026, based directly on Stripe's design).

---

## 1. Retry Policies — Exponential Backoff with Jitter

**Defends against:** transient failures — a momentary network blip, a brief overload on the
other side, a load balancer mid-failover. Retrying immediately, or retrying without a growing
delay, is worse than not retrying at all: it turns one client's failure into synchronized
retry storms that keep the target service down (the "thundering herd" problem).

### Why Naive Retry Is Actively Harmful

```
❌ NAIVE RETRY — fixed delay, no jitter:
   1000 clients hit a struggling server. It fails. All 1000 retry after exactly 1 second.
   All 1000 requests arrive again in the same instant — the server never gets a chance
   to recover. This is a self-inflicted DDoS.

✅ EXPONENTIAL BACKOFF WITH JITTER:
   Each client waits a randomized, growing interval. Retries spread out over time instead
   of arriving in synchronized waves — giving the failing service room to recover.
```

### The Algorithm (AWS "Full Jitter" — the recommended variant)

```typescript
interface RetryOptions {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
}

async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {
    maxRetries: 5,
    baseDelayMs: 200,
    maxDelayMs: 10_000,
  },
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt <= options.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;

      if (!isRetryable(err) || attempt === options.maxRetries) {
        throw err; // don't retry non-transient errors or exhaust the budget silently
      }

      // "Full Jitter" formula (AWS): random delay between 0 and the exponential cap.
      // This spreads retries far more evenly than "equal jitter" or no jitter at all.
      const exponentialCap = Math.min(
        options.maxDelayMs,
        options.baseDelayMs * 2 ** attempt,
      );
      const delay = Math.random() * exponentialCap;

      await sleep(delay);
    }
  }
  throw lastError;
}

function isRetryable(err: unknown): boolean {
  // Retry: network errors, timeouts, 429 (rate limited), 500/502/503/504
  // NEVER retry: 400 (bad request), 401/403 (auth), 404 (not found), 422 (validation)
  // Retrying a 4xx client error just repeats the same failure — it will never succeed.
  if (err instanceof HTTPError) {
    return err.status === 429 || err.status >= 500;
  }
  return err instanceof NetworkError || err instanceof TimeoutError;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

```python
import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 5,
    base_delay: float = 0.2,
    max_delay: float = 10.0,
) -> T:
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as err:
            last_error = err

            if not _is_retryable(err) or attempt == max_retries:
                raise

            # AWS "Full Jitter" — random delay between 0 and the exponential cap
            exponential_cap = min(max_delay, base_delay * (2**attempt))
            delay = random.uniform(0, exponential_cap)
            await asyncio.sleep(delay)

    raise last_error  # unreachable, satisfies type checker


def _is_retryable(err: Exception) -> bool:
    if isinstance(err, httpx.HTTPStatusError):
        return err.response.status_code == 429 or err.response.status_code >= 500
    return isinstance(err, (httpx.TimeoutException, httpx.NetworkError))
```

### Respecting `Retry-After` (When the Server Tells You Explicitly)

```typescript
// When a 429 or 503 includes Retry-After, honor it exactly — it overrides your own backoff
async function callWithRetryAfterSupport(url: string): Promise<Response> {
  const response = await fetch(url);

  if (response.status === 429 || response.status === 503) {
    const retryAfter = response.headers.get('Retry-After');
    if (retryAfter) {
      // Retry-After can be seconds (e.g., "120") or an HTTP date
      const delayMs = /^\d+$/.test(retryAfter)
        ? parseInt(retryAfter, 10) * 1000
        : new Date(retryAfter).getTime() - Date.now();
      await sleep(Math.max(0, delayMs));
      return callWithRetryAfterSupport(url); // one retry attempt shown; wrap in your budget
    }
  }
  return response;
}
```

### Retry Anti-Patterns

```
❌ Retrying indefinitely with no cap — a permanently down dependency causes unbounded
   resource consumption (open connections, memory, queued work) on the caller
❌ Retrying non-idempotent operations without an idempotency key (see Section 3) — a POST
   that already succeeded, retried after a timeout, may create a duplicate resource
❌ Retrying 4xx client errors — the request is malformed or unauthorized; retrying doesn't
   change that, it just wastes calls (and can trigger abuse detection on the other end)
❌ No jitter — synchronized retry storms recreate the outage you were trying to survive
```

---

## 2. Circuit Breakers

**Defends against:** cascading failure — repeatedly calling a dependency that is already
failing wastes resources, adds latency to every caller waiting for a timeout, and can prevent
the failing service from ever recovering (it never stops receiving load long enough to
stabilize). Introduced to mainstream software practice by Michael Nygard in _Release It!_
(2007) and formalized by Martin Fowler.

### The State Machine

```
     ┌─────────────────────────────────────────────────────────────┐
     │                                                                 │
     ▼                                                                 │
┌─────────┐   failure threshold exceeded    ┌──────────┐   timeout elapses   ┌──────────┐
│  CLOSED   │ ──────────────────────────────▶│   OPEN     │────────────────────▶│ HALF-OPEN  │
│ (normal)  │                                 │ (failing)  │                     │ (testing)  │
└─────────┘                                 └──────────┘                     └──────────┘
     ▲                                                                              │
     │                    success on trial request                                  │
     └──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ trial request also fails
                                     ▼
                               back to OPEN

CLOSED:    Requests flow normally. Failures are counted.
OPEN:      Requests fail IMMEDIATELY without calling the dependency at all —
           this is the entire point: stop wasting resources on a known-failing call.
HALF-OPEN: After a cooldown, allow ONE trial request through. Success → CLOSED.
           Failure → back to OPEN, cooldown resets.
```

### Implementation

```typescript
type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

class CircuitBreaker {
  private state: CircuitState = 'CLOSED';
  private failureCount = 0;
  private lastFailureTime = 0;

  constructor(
    private readonly failureThreshold: number = 5,
    private readonly cooldownMs: number = 30_000,
  ) {}

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime > this.cooldownMs) {
        this.state = 'HALF_OPEN'; // cooldown elapsed — allow one trial
      } else {
        // Fail fast — do NOT call the dependency at all
        throw new CircuitOpenError('Circuit breaker is open — failing fast');
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      throw err;
    }
  }

  private onSuccess(): void {
    this.failureCount = 0;
    this.state = 'CLOSED';
  }

  private onFailure(): void {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    if (
      this.failureCount >= this.failureThreshold ||
      this.state === 'HALF_OPEN'
    ) {
      this.state = 'OPEN';
    }
  }
}

// Usage — wrap any call to a potentially-unreliable dependency
const partnerApiBreaker = new CircuitBreaker(5, 30_000);

async function callPartnerApi(orderId: string) {
  return partnerApiBreaker.execute(() => fetchPartnerOrder(orderId));
}
```

```python
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    async def execute(self, fn: Callable[[], Awaitable[T]]) -> T:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time > self._cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError("Circuit breaker is open — failing fast")

        try:
            result = await fn()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold or self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
```

**Production-grade libraries** (prefer these over hand-rolled implementations for anything
beyond prototyping): `opossum` (Node.js), `resilience4j` (Java — the modern successor to
Netflix Hystrix, which is now in maintenance mode), `pybreaker` (Python), `Polly` (.NET).

### When NOT to Use a Circuit Breaker

- **Low-stakes, infrequent calls** — the operational complexity (tuning thresholds, monitoring
  breaker state, alerting on trips) isn't justified for a background job that runs once daily
- **Dependencies with their own robust availability guarantees** and where a simple timeout +
  bounded retry already provides adequate protection — not every external call needs a full
  state machine
- **When failing fast has no benefit** — if there's no fallback behavior and no meaningful way
  to shed load, a circuit breaker just changes _how_ you fail, not whether you fail gracefully

---

## 3. Idempotency Keys

**Defends against:** duplicate side effects. This is the single most important pattern in
this file for RPA and integration work specifically — retries and network failures are
routine, and without idempotency, a retried "create order" or "charge card" call can execute
the operation twice.

### The Failure Mode This Prevents

```
1. Client sends POST /charges { amount: 100 }
2. Server processes the charge successfully — money is moved
3. Network fails BEFORE the response reaches the client
4. Client sees a timeout, has no idea if the charge succeeded, and retries
5. WITHOUT an idempotency key: server processes a SECOND charge — customer is charged twice
6. WITH an idempotency key: server recognizes this retry as the same logical operation
   and returns the ORIGINAL result — no duplicate charge
```

### The Standard (Stripe's design, now becoming an IETF standard)

Stripe pioneered the `Idempotency-Key` header pattern; it is now being standardized by the
IETF (`draft-ietf-httpapi-idempotency-key-header`, published October 2025) — meaning this is
converging into a formal HTTP standard, not just a vendor-specific convention.

**As a consumer (calling someone else's API):**

```typescript
import crypto from 'crypto';

async function createOrder(orderData: OrderInput) {
  // Generate ONE key per logical operation attempt — reuse it across retries of
  // the SAME logical request, generate a NEW one for a genuinely different request
  const idempotencyKey = crypto.randomUUID();

  return retryWithBackoff(() =>
    fetch('https://api.partner.com/orders', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey, // SAME key on every retry of this attempt
      },
      body: JSON.stringify(orderData),
    }),
  );
}
```

**As a provider (implementing idempotency in your own API):**

```typescript
// Express middleware — cache responses by idempotency key
async function idempotencyMiddleware(
  req: Request,
  res: Response,
  next: NextFunction,
) {
  const key = req.headers['idempotency-key'] as string | undefined;
  if (!key || req.method !== 'POST') return next(); // only applies to unsafe methods

  const cached = await redis.get(`idempotency:${key}`);
  if (cached) {
    const { status, body } = JSON.parse(cached);
    return res.status(status).json(body); // return the ORIGINAL result — don't re-execute
  }

  // Wrap res.json to cache the response before sending it
  const originalJson = res.json.bind(res);
  res.json = (body: unknown) => {
    redis.setex(
      `idempotency:${key}`,
      86400,
      JSON.stringify({ status: res.statusCode, body }),
    );
    return originalJson(body);
  };

  next();
}
```

```python
# FastAPI dependency — server-side idempotency enforcement
from fastapi import Header, HTTPException

async def enforce_idempotency(
    idempotency_key: Annotated[str | None, Header()] = None,
) -> str | None:
    if not idempotency_key:
        return None

    cached = await redis.get(f"idempotency:{idempotency_key}")
    if cached:
        cached_response = json.loads(cached)
        raise HTTPException(
            status_code=cached_response["status"],
            detail=cached_response["body"],
            headers={"Idempotency-Replayed": "true"},
        )
    return idempotency_key


@router.post("/orders")
async def create_order(
    payload: OrderCreate,
    idempotency_key: Annotated[str | None, Depends(enforce_idempotency)],
) -> OrderResponse:
    order = await order_service.create(payload)
    if idempotency_key:
        await redis.setex(
            f"idempotency:{idempotency_key}",
            86400,
            json.dumps({"status": 201, "body": order.model_dump()}),
        )
    return order
```

**Key generation rule:** the idempotency key must be generated **once per logical operation
attempt** by the client, and reused across all retries of that same attempt. A new key for
every retry defeats the entire purpose — it would let each retry through as if it were a new
operation.

### When Idempotency Keys Are Mandatory vs Optional

```
MANDATORY:
- Any POST that creates a resource with a real-world side effect (charge, order, email send,
  RPA bot triggering a downstream system action)
- Any operation you will retry automatically
- Any operation where "it might have already happened" has real cost (financial, irreversible)

OPTIONAL (often unnecessary):
- GET requests — already idempotent by HTTP semantics, no key needed
- PUT/DELETE — already idempotent by HTTP semantics (see protocols.md), though some providers
  still support idempotency keys for extra safety
- Read-only or side-effect-free operations
```

---

## 4. Rate Limiting

### As a Provider — Protecting Your Own API

**Defends against:** one client (accidental or malicious) consuming disproportionate
resources and degrading service for everyone else.

```typescript
import rateLimit from 'express-rate-limit';

const apiLimiter = rateLimit({
  windowMs: 60_000,
  max: 100, // 100 requests per minute per key
  standardHeaders: true, // sends RateLimit-* headers (IETF draft standard)
  legacyHeaders: false,
  keyGenerator: (req) => (req.headers['x-api-key'] as string) ?? req.ip,
  handler: (req, res) => {
    res.status(429).json({ error: 'Rate limit exceeded' });
    // Always include Retry-After — see the callWithRetryAfterSupport example above
  },
});

app.use('/api/', apiLimiter);
```

**Standard response headers (IETF draft, widely adopted):**

```http
HTTP/1.1 429 Too Many Requests
RateLimit-Limit: 100
RateLimit-Remaining: 0
RateLimit-Reset: 42
Retry-After: 42
```

### As a Consumer — Respecting Someone Else's Limits

```typescript
class RateLimitAwareClient {
  private remaining = Infinity;
  private resetAt = 0;

  async call(url: string, options?: RequestInit): Promise<Response> {
    // Proactively slow down BEFORE hitting the limit, not just react to 429s
    if (this.remaining <= 1 && Date.now() < this.resetAt) {
      await sleep(this.resetAt - Date.now());
    }

    const response = await fetch(url, options);

    const remaining = response.headers.get('RateLimit-Remaining');
    const reset = response.headers.get('RateLimit-Reset');
    if (remaining) this.remaining = parseInt(remaining, 10);
    if (reset) this.resetAt = Date.now() + parseInt(reset, 10) * 1000;

    if (response.status === 429) {
      // Fall back to Retry-After handling — see Section 1
      throw new RateLimitedError(response);
    }

    return response;
  }
}
```

**For RPA specifically:** many target systems (Salesforce, SAP, government portals) enforce
strict per-minute or per-day API call quotas. A bot that doesn't track and proactively throttle
against these limits will get temporarily banned mid-workflow — always read and respect
rate-limit response headers rather than relying on trial-and-error backoff alone.

### When NOT to Rate Limit

- **Purely internal service-to-service calls within a trusted network boundary** where the
  callers are known, finite, and already capacity-planned — rate limiting adds overhead for a
  problem that capacity planning and monitoring already address
- **Very low-traffic APIs** where the operational cost of implementing and tuning rate limiting
  exceeds any realistic abuse risk in the near term — note as a documented future addition
  rather than building it prematurely
