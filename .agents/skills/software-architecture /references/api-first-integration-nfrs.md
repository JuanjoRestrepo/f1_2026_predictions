# API-First Design, Integration Patterns & Non-Functional Requirements

**Sources:** OpenAPI Initiative (Linux Foundation) for API-first tooling standards; Gregor
Hohpe & Bobby Woolf, _Enterprise Integration Patterns_ (2003) for integration patterns; ISO/IEC
25010 (Systems and Software Quality Requirements and Evaluation — SQuaRE) for the formal NFR
taxonomy used by enterprise architecture review boards. All concepts are language and
framework agnostic; examples use TypeScript/Python and OpenAPI YAML, which is itself
language-neutral by design.

---

## API-First Design

### The Core Idea

Design and agree on the API contract (typically an OpenAPI specification) **before** writing
implementation code — the contract becomes the source of truth that frontend, backend, and
third-party teams all build against in parallel, rather than the API being an afterthought
extracted from whatever the backend happened to implement.

```
❌ CODE-FIRST (API emerges from implementation):
   Backend writes code → API shape is whatever came out → docs generated after the fact →
   frontend team waits for backend to finish before starting → contract changes are informal
   and often break consumers silently

✅ API-FIRST (contract precedes implementation):
   Team agrees on OpenAPI spec → frontend mocks against the spec and starts building
   immediately → backend implements against the same spec → contract tests verify both sides
   match → breaking changes are caught at the spec level, not in production
```

### OpenAPI Specification as Contract

```yaml
# openapi.yaml — the source of truth, versioned in git, reviewed like code
openapi: 3.1.0
info:
  title: Order API
  version: 1.2.0
paths:
  /orders:
    post:
      summary: Place a new order
      operationId: placeOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PlaceOrderRequest'
      responses:
        '201':
          description: Order placed successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '422':
          description: Validation error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ValidationErrorResponse'
components:
  schemas:
    PlaceOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId:
          type: string
          format: uuid
        items:
          type: array
          minItems: 1
          items:
            type: object
            required: [productId, quantity]
            properties:
              productId: { type: string, format: uuid }
              quantity: { type: integer, minimum: 1 }
```

### Generating Code from the Contract (Both Directions)

**FastAPI generates OpenAPI automatically from Pydantic models** — code-first in this specific
case, but the generated spec becomes the contract other teams consume, achieving the same
alignment benefit without hand-writing YAML:

```python
# FastAPI derives the OpenAPI spec from this — teams consume /openapi.json as the contract
class PlaceOrderRequest(BaseModel):
    customer_id: UUID
    items: list[OrderItemRequest] = Field(min_length=1)
```

**True API-first — generate TypeScript types and client code FROM a hand-written spec:**

```bash
# Generate a typed client from openapi.yaml — frontend never hand-writes fetch calls
npx openapi-typescript openapi.yaml -o src/types/api.d.ts

# Or generate a full typed SDK
npx @openapitools/openapi-generator-cli generate \
  -i openapi.yaml -g typescript-fetch -o src/generated-client
```

```typescript
// Frontend now has compile-time-checked API calls — a contract mismatch is a TypeScript error,
// caught in the IDE, not discovered at runtime in production
import type { paths } from '@/types/api';

type PlaceOrderRequest =
  paths['/orders']['post']['requestBody']['content']['application/json'];
type OrderResponse =
  paths['/orders']['post']['responses']['201']['content']['application/json'];
```

### Contract Testing

Verifies that the API implementation actually matches the published contract — catches drift
between spec and reality automatically in CI, rather than relying on manual review.

```typescript
// Using a tool like Dredd or Schemathesis to validate implementation against spec
// CI step — fails the build if the running API doesn't match openapi.yaml
```

```bash
# Schemathesis (Python) — property-based testing directly from the OpenAPI spec
uv add --dev schemathesis
uv run schemathesis run openapi.yaml --base-url http://localhost:8000
```

---

## Integration Patterns

Drawn from Hohpe & Woolf's _Enterprise Integration Patterns_ — the canonical catalog, still the
reference vocabulary used across the industry regardless of specific messaging technology.

### Anti-Corruption Layer (ACL)

Introduced in `references/ddd.md` as a strategic DDD pattern — the implementation detail
belongs here. Translates an external or legacy system's model into your own domain's model,
preventing the external system's quirks and inconsistencies from leaking into your codebase.

```typescript
// External legacy system's response — inconsistent naming, mixed units, nullable everything
interface LegacyInventoryResponse {
  prod_id: string;
  qty_avail: string; // string, not number — legacy system quirk
  whs_loc: string | null;
  last_upd_ts: number; // unix timestamp, not ISO string
}

// The ACL — the ONLY place that knows about the legacy system's shape
export class LegacyInventoryAdapter implements InventoryPort {
  constructor(private readonly legacyClient: LegacySystemClient) {}

  async getAvailability(productId: string): Promise<InventoryAvailability> {
    const raw = await this.legacyClient.fetchInventory(productId);
    // Translate to OUR domain model — legacy quirks stop here, never propagate further
    return {
      productId: raw.prod_id,
      quantityAvailable: parseInt(raw.qty_avail, 10),
      warehouseLocation: raw.whs_loc ?? 'UNKNOWN',
      lastUpdated: new Date(raw.last_upd_ts * 1000),
    };
  }
}
```

### Strangler Fig

Covered in depth in `references/microservices-monolith.md` — gradually replacing a legacy
system or monolith module by routing an increasing share of traffic to the new implementation
until the old one can be safely retired.

### Saga Pattern (Distributed Transactions)

When a business operation spans multiple services (each with its own database — see
`references/microservices-monolith.md`), a traditional ACID transaction isn't possible. A saga
coordinates the operation as a sequence of local transactions, each with a defined compensating
action to undo it if a later step fails.

```typescript
// Choreography-based saga — each service reacts to the previous service's event
// Order Service: creates order, publishes OrderCreated
// Inventory Service: reserves stock, publishes StockReserved (or StockReservationFailed)
// Payment Service: charges card, publishes PaymentCompleted (or PaymentFailed)
// On any failure event, prior services run their COMPENSATING action:

export class OrderSagaCompensation {
  async onStockReservationFailed(event: StockReservationFailed): Promise<void> {
    // Compensating action — undo the order creation
    await this.orderService.cancel(event.orderId, 'Inventory unavailable');
  }

  async onPaymentFailed(event: PaymentFailed): Promise<void> {
    // Compensating action — undo the stock reservation AND the order
    await this.inventoryService.releaseReservation(event.orderId);
    await this.orderService.cancel(event.orderId, 'Payment failed');
  }
}
```

**Orchestration-based alternative:** a central saga orchestrator explicitly calls each step and
handles failures, rather than each service reacting independently. Orchestration is easier to
reason about and debug (one place to look); choreography is more decoupled but harder to trace
end-to-end without distributed tracing tooling in place.

### Idempotency Keys (Critical for Any Retryable Integration)

Any integration point that might be retried (client-side retry, network timeout, saga
compensation retry) must be idempotent to avoid duplicate side effects — e.g., double-charging
a customer.

```typescript
router.post('/payments', async (req, res) => {
  const idempotencyKey = req.headers['idempotency-key'] as string;
  if (!idempotencyKey) {
    return res
      .status(400)
      .json({ error: 'Idempotency-Key header is required' });
  }

  const existing = await db.idempotencyKeys.findUnique({
    where: { key: idempotencyKey },
  });
  if (existing) {
    return res.status(existing.statusCode).json(existing.responseBody); // return cached result
  }

  const result = await paymentService.charge(req.body);
  await db.idempotencyKeys.create({
    data: { key: idempotencyKey, statusCode: 201, responseBody: result },
  });
  return res.status(201).json(result);
});
```

---

## Non-Functional Requirements (NFRs)

**Formal source:** ISO/IEC 25010 defines eight quality characteristics (functional suitability,
performance efficiency, compatibility, usability, reliability, security, maintainability,
portability). The three emphasized here — scalability, reliability, security — are the ones
most directly shaped by architectural decisions.

### Scalability

| Technique                                    | What it addresses                                             |
| -------------------------------------------- | ------------------------------------------------------------- |
| Horizontal scaling (more instances)          | Handling increased request volume                             |
| Caching (Redis, CDN, HTTP cache headers)     | Reducing redundant computation/DB load                        |
| Database read replicas                       | Read-heavy workload scaling without write contention          |
| CQRS (see `references/cqrs-event-driven.md`) | Read/write workloads with different scaling profiles          |
| Async processing / queues                    | Decoupling slow operations from the request/response cycle    |
| Database sharding                            | Write throughput beyond a single database instance's capacity |

**Measure before optimizing.** Load test with realistic traffic patterns (k6, Locust,
Artillery) before introducing scaling complexity — premature horizontal scaling or sharding
solves a problem that profiling might reveal doesn't exist yet, or exists somewhere entirely
different (an unindexed query, not a fundamental architecture limit).

### Reliability

**Circuit Breaker** — stop calling a failing downstream dependency after it fails repeatedly,
failing fast instead of piling up slow/hanging requests:

```typescript
import CircuitBreaker from 'opossum';

const options = {
  timeout: 3000,
  errorThresholdPercentage: 50,
  resetTimeout: 30000,
};
const breaker = new CircuitBreaker(callInventoryService, options);

breaker.fallback(() => ({
  available: false,
  reason: 'Inventory service unavailable',
}));

const result = await breaker.fire(productId);
```

**Retry with Exponential Backoff** — for transient failures (network blips, momentary
overload), retry with increasing delay rather than hammering a struggling service:

```typescript
async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries = 3,
): Promise<T> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === maxRetries - 1) throw err;
      const delay = Math.min(1000 * 2 ** attempt, 10000) + Math.random() * 1000; // jitter
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw new Error('Unreachable');
}
```

**Bulkhead** — isolate resource pools per dependency so one failing/slow dependency can't
exhaust resources needed by unrelated operations (e.g., separate connection pools per external
service, separate thread/worker pools per critical vs. non-critical operation).

**Graceful Degradation** — define explicitly what the system does when a non-critical
dependency fails (e.g., show the product page without personalized recommendations if the
recommendation service is down, rather than failing the whole page load).

### Security (as an Architectural Property)

This file covers security at the **architectural** level — trust boundaries and defense in
depth by layer. For implementation-level security (password hashing, JWT, MFA, rate limiting,
supply chain defense, active CVEs), see the `web-devops` skill's `references/security.md`.

**Trust boundary mapping** — for any system, explicitly diagram where data crosses from a less
trusted context into a more trusted one (public internet → API gateway → internal services →
database), and apply validation/authentication at every crossing, not just the outermost one:

```
Internet (untrusted)
    │  ← validate + authenticate HERE
    ▼
API Gateway (semi-trusted)
    │  ← re-validate + authorize HERE — never assume the gateway already did it correctly
    ▼
Internal Services (trusted, but NOT implicitly — see Zero Trust below)
    │  ← still validate inputs HERE — a compromised internal service shouldn't cascade
    ▼
Database (most trusted, still parameterize every query)
```

**Zero Trust principle:** do not assume internal network traffic is safe by virtue of being
internal. Each service should authenticate and authorize requests from other internal services,
not just from external clients — a compromised internal service should not have unrestricted
access to every other internal service by default.

---

## Enterprise Architecture Review Checklist

Use this when formally reviewing a proposed or existing architecture — for a new system design,
a major refactor proposal, or an architecture decision record (ADR) review.

**Problem Fit**

- [ ] The chosen patterns solve a problem this system actually has — not a problem a similar,
      larger company had
- [ ] Simpler alternatives were explicitly considered and rejected with stated reasoning
- [ ] The team has the operational experience to run what's being proposed (distributed
      systems, event-driven debugging, etc.)

**Domain & Boundaries**

- [ ] Bounded contexts are identified and documented, even if the system remains a monolith
- [ ] Module/service boundaries align with team ownership (Conway's Law) — no shared ownership
      of a single module by multiple teams without a clear coordination process
- [ ] The ubiquitous language is consistent between code, documentation, and stakeholder
      conversations

**Scalability**

- [ ] Expected load (current and 12-24 month projection) is documented and the architecture is
      sized against it — not against an arbitrary "web scale" assumption
- [ ] Bottlenecks have been load-tested, not just theorized
- [ ] Caching strategy is explicit — what's cached, invalidation strategy, staleness tolerance

**Reliability**

- [ ] Every synchronous inter-service call has a defined timeout, retry policy, and fallback
      behavior
- [ ] Single points of failure are identified and either accepted explicitly or mitigated
- [ ] Disaster recovery and backup strategy exist and have been tested (see `web-devops` skill's
      `references/security.md` Section 10 for backup implementation)

**Security**

- [ ] Trust boundaries are diagrammed; validation happens at every boundary crossing, not just
      the perimeter
- [ ] Zero Trust applied to internal service-to-service communication
- [ ] See `web-devops` skill's `references/security.md` for the full implementation checklist

**Maintainability**

- [ ] A new engineer can understand the system's major components within a reasonable
      onboarding period — architecture complexity is proportional to team size and domain
      complexity, not maximized for its own sake
- [ ] Architecture Decision Records (ADRs) exist for major structural choices, documenting the
      context and trade-offs considered at the time
- [ ] Technical debt from deliberate shortcuts is tracked, not silently accumulated

**Cost**

- [ ] Infrastructure cost is proportional to actual load, not provisioned for a hypothetical
      future scale that may never materialize
- [ ] Operational cost (on-call burden, number of services to monitor, deployment complexity)
      has been weighed against the benefit the architecture provides

---

## When NOT to Formalize (Over-Engineering Check)

**API-First** earns its cost when multiple teams (frontend, backend, third-party partners)
need to work in parallel against a stable contract, or when the API is genuinely public and
external consumers depend on stability. It is unnecessary ceremony for a single full-stack
developer building an internal tool where the frontend and backend deploy together and a type
error would be caught immediately in development (a T3 Stack app with tRPC already gets
end-to-end type safety without a separate OpenAPI authoring step).

**Formal Integration Patterns (Saga, ACL)** earn their cost when genuinely integrating across
service or system boundaries with real consistency and legacy-quirk challenges. Do not
introduce a saga orchestrator for a single-service operation that fits inside one database
transaction — that's what `BEGIN`/`COMMIT`/`ROLLBACK` is for.

**The Enterprise Architecture Review Checklist** itself is meant for genuinely significant
decisions — a new system, a major refactor, a cross-team architecture change. Running a full
review for every pull request or minor feature is process for its own sake; reserve it for
decisions that are expensive to reverse.
