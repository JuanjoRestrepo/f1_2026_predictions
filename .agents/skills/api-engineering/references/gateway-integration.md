# API Gateway & Integration Patterns

**Sources:** AWS API Gateway documentation; Azure API Management documentation; Kong Gateway
documentation; Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (2003) — the
canonical reference for messaging/integration patterns, still the standard vocabulary used
across the industry; W3C WebSub (formerly PubSubHubbub) for webhook standardization patterns.

---

## 1. API Gateway

An API Gateway is a single entry point that sits in front of one or more backend services,
centralizing cross-cutting concerns so individual services don't each reimplement them.

```
                        ┌───────────────────────────┐
   Client Requests  ───▶│        API Gateway           │
                        │                             │
                        │  • Authentication            │
                        │  • Rate limiting              │
                        │  • Request routing            │
                        │  • Request/response transform │
                        │  • Logging & metrics           │
                        │  • TLS termination             │
                        └─────────┬───────┬───────────┘
                                   │       │
                      ┌───────────┘       └────────────┐
                      ▼                                 ▼
              ┌──────────────┐                  ┌──────────────┐
              │  Orders Service │                  │  Users Service  │
              └──────────────┘                  └──────────────┘
```

**What it correctly centralizes:** authentication/token validation (one place, not
reimplemented per service), rate limiting, request logging, TLS termination, and routing —
genuinely cross-cutting concerns that don't belong duplicated across every backend service.

**What it should NOT become:** a place where business logic accumulates. A gateway that
starts making business decisions (rather than routing, transforming, and enforcing policy)
has become a hidden, hard-to-test service in disguise — keep business logic in the services
themselves.

### Product Comparison

| Product | Best for | Notes |
|---|---|---|
| **AWS API Gateway** | AWS-native architectures | Tight Lambda integration; usage-based pricing |
| **Azure API Management** | Azure-native, enterprise API programs | Strong developer portal, policy XML for transforms |
| **Kong Gateway** | Cloud-agnostic, self-hosted or Kong Konnect | Plugin ecosystem; open-source core |
| **Cloudflare** | Edge-first, DDoS/WAF-integrated | Runs at the edge, closest to the client globally |
| **NGINX (as gateway)** | Simple routing/rate-limiting needs | Lower-level; more configuration required for full gateway features |

### When NOT to Introduce an API Gateway

- **A single backend service, no fan-out to multiple services** — a gateway in front of one
  service adds a network hop and an operational dependency for no architectural benefit; put
  auth/rate-limiting directly in that service or its reverse proxy
- **Early-stage projects still discovering their service boundaries** — introducing a gateway
  before you know how many services you'll actually have (see `software-architecture/
  microservices-monolith.md` on preferring a modular monolith initially) adds infrastructure
  ahead of the need it serves
- **When a simpler reverse proxy (NGINX, Caddy) already meets the actual requirement** — full
  API Gateway products add capability (usage plans, developer portals, complex transforms)
  that many projects never use; don't pay the complexity cost for unused capability

---

## 2. Webhooks — Production-Grade Push Notifications

**Webhooks** are HTTP callbacks: your system registers a URL with a provider, and the provider
POSTs an HTTP request to that URL whenever an event occurs. Simple to understand, non-trivial
to operate reliably at scale.

**Sources:** CNCF CloudEvents specification v1.0 (CNCF Graduated project, January 2024;
ThoughtWorks Tech Radar "Adopt" category, April 2024); CNCF HTTP Webhook specification; W3C
WebSub (push subscription over HTTP); Stripe webhook documentation (the reference production
implementation); Svix open-source webhook delivery infrastructure.

### The Delivery Problem

The fundamental challenge with webhooks is that neither party has guaranteed delivery. Your
endpoint can be down, slow, or return an error; the provider may retry or may not. **Webhooks
are "at-least-once" delivery, not exactly-once** — design every receiver for idempotency.

```
Failure modes you must handle:
  - Your endpoint is down → provider retries (maybe)
  - Your endpoint times out (response takes > 5s) → provider treats as failure, retries
  - Your endpoint returns 5xx → provider retries
  - Your endpoint returns 2xx but processing fails internally → event is "lost" (your problem)
  - Same event arrives twice → MUST be idempotent
  - Events arrive out of order → MUST be order-independent or use sequence numbers
```

### Event Schema — CloudEvents Standard (CNCF Graduated 2024)

CloudEvents is a CNCF-graduated specification for describing event data in a common format —
adopted by Azure Event Grid, Google Cloud Eventarc, AWS EventBridge, the European Commission,
Adobe I/O Events, and IBM Cloud Code Engine. ThoughtWorks moved it to "Adopt" in April 2024.

Use CloudEvents as your event schema when building your own webhook system — it provides a
standard envelope that downstream consumers can parse without understanding your specific
domain:

```json
{
  "specversion": "1.0",
  "type": "com.example.order.shipped",
  "source": "https://api.example.com/orders",
  "subject": "order-12345",
  "id": "unique-event-id-uuid",
  "time": "2026-05-19T14:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "order-12345",
    "customerId": "customer-789",
    "shippedAt": "2026-05-19T14:28:00Z",
    "trackingNumber": "1Z999AA10123456784"
  }
}
```

**CloudEvents HTTP delivery headers (binary content mode — preferred):**

```http
POST /webhook HTTP/1.1
ce-specversion: 1.0
ce-type: com.example.order.shipped
ce-source: https://api.example.com/orders
ce-id: unique-event-id-uuid
ce-time: 2026-05-19T14:30:00Z
Content-Type: application/json

{ "orderId": "order-12345", ... }
```

**Event type naming convention:**

```
<reverse-domain>.<noun>.<past-tense-verb>
com.example.order.created
com.example.order.shipped
com.example.user.password-changed
com.example.payment.failed
```

### Receiving Webhooks Correctly — Signature Verification (Mandatory)

Never trust an incoming webhook payload without verifying it came from the claimed sender.

```typescript
import crypto from "crypto";

function verifyWebhookSignature(
  rawBody: string, // MUST be raw bytes — parse after verification, not before
  signatureHeader: string,
  webhookSecret: string,
): boolean {
  const expectedSig = crypto
    .createHmac('sha256', webhookSecret)
    .update(rawBody)
    .digest('hex');

  return crypto.timingSafeEqual(
    // timing-safe — prevents timing oracle attacks
    Buffer.from(signatureHeader),
    Buffer.from(expectedSig),
  );
}

// Express — critical: use express.raw() BEFORE express.json() for webhook routes
// The signature is computed over the raw body bytes — parsing to JSON first corrupts the check
app.post(
  "/webhooks/partner",
  express.raw({ type: "application/json" }),
  (req, res) => {
    const signature = req.headers['x-partner-signature'] as string;
    const rawBody = req.body.toString('utf8');

    if (
      !verifyWebhookSignature(rawBody, signature, process.env.WEBHOOK_SECRET!)
    ) {
      return res.status(401).json({ error: 'Invalid signature' });
    }

    // Timestamp validation — reject stale payloads (prevents replay attacks)
    const timestamp = Number(req.headers['x-partner-timestamp']);
    if (Math.abs(Date.now() / 1000 - timestamp) > 300) {
      // 5-minute window
      return res.status(400).json({ error: 'Timestamp too old' });
    }

    const event = JSON.parse(rawBody);
    // Acknowledge FAST — process asynchronously to prevent timeout retries
    queue.enqueue(event);
    res.status(200).send();
  },
);
```

```python
import hashlib, hmac, json, time
from fastapi import Header, HTTPException, Request, Response


async def receive_webhook(request: Request) -> Response:
    raw_body = await request.body()
    signature = request.headers.get("x-partner-signature", "")
    timestamp = request.headers.get("x-partner-timestamp", "0")

    # Verify signature
    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Reject stale timestamps (replay protection)
    if abs(time.time() - int(timestamp)) > 300:
        raise HTTPException(status_code=400, detail="Stale timestamp")

    event = json.loads(raw_body)
    await queue.enqueue(event)    # async processing — never block the response
    return Response(status_code=200)
```

### Idempotent Processing — Handle Duplicates (Mandatory)

Most providers retry on non-2xx responses and on timeouts. The same event WILL arrive more
than once. Use the event ID as a deduplication key:

```typescript
async function processWebhookEvent(event: CloudEvent): Promise<void> {
  const lockKey = `webhook:lock:${event.id}`;

  // SET NX (set if not exists) with TTL — atomic check-and-set
  const acquired = await redis.set(lockKey, '1', { NX: true, EX: 86400 }); // 24h
  if (!acquired) {
    logger.info('Duplicate webhook event — skipping', { eventId: event.id });
    return;
  }

  try {
    await handleEvent(event);
  } catch (err) {
    await redis.del(lockKey); // release lock on failure so the event can be retried
    throw err;
  }
}
```

### Ordering Is Not Guaranteed

Webhooks can arrive out of order — `order.shipped` before `order.confirmed` due to retry
timing, network routes, or parallel delivery. Two defensive strategies:

```typescript
// Strategy 1 — event timestamp comparison (if provider includes reliable timestamps)
async function handleOrderEvent(event: CloudEvent): Promise<void> {
  const existing = await db.orderEvent.findFirst({
    where: { orderId: event.data.orderId },
    orderBy: { occurredAt: 'desc' },
  });

  if (existing && new Date(event.time) <= existing.occurredAt) {
    logger.warn('Out-of-order event — ignoring', { eventId: event.id });
    return;
  }
  await applyEvent(event);
}

// Strategy 2 — sequence numbers (if provider supports them)
// Store the last processed sequence; reject lower ones
```

### Webhook Registration Handshake (CNCF HTTP Webhook Spec)

When **you** are the webhook sender, protect your delivery infrastructure from being used to
flood arbitrary URLs. The CNCF HTTP Webhook specification defines a standard handshake:

```typescript
// Before delivering events to a newly registered webhook URL, send a validation challenge
async function validateWebhookRegistration(
  webhookUrl: string,
): Promise<boolean> {
  const challenge = crypto.randomBytes(32).toString('base64url');

  const response = await fetch(webhookUrl, {
    method: 'OPTIONS',
    headers: {
      'WebHook-Request-Callback': `${process.env.API_BASE}/webhooks/validate?challenge=${challenge}`,
      'WebHook-Request-Rate': '120', // max events per minute we'll send
    },
  });

  // Receiver must respond 200 OK — confirms they control the endpoint
  return response.ok;
}
```

### Building Your Own Webhook Delivery System

For teams sending webhooks (not just receiving them), reliable delivery requires a queue:

```
EVENT OCCURS → Persist to outbox table → Queue worker picks it up →
Attempt delivery → 2xx? → Mark delivered
                    → 4xx? → Do NOT retry (client error; tell the user)
                    → 5xx / timeout? → Retry with exponential backoff
                               → Exhausted retries? → Mark failed, alert user
```

```typescript
// Outbox pattern — atomically record the event and enqueue for delivery
async function emitEvent(event: CloudEvent, db: Transaction): Promise<void> {
  // Within the SAME database transaction as the state change that caused the event:
  await db.webhookOutbox.create({
    data: {
      eventId: event.id,
      type: event.type,
      payload: event,
      status: 'PENDING',
      attempts: 0,
      nextAttemptAt: new Date(),
    },
  });
  // Worker polls the outbox table and delivers — never fire-and-forget from the request handler
}

async function deliverWebhook(outboxEntry: WebhookOutbox): Promise<void> {
  const response = await fetch(outboxEntry.targetUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-signature-sha256': sign(
        outboxEntry.payload,
        outboxEntry.signingSecret,
      ),
      'x-timestamp': String(Math.floor(Date.now() / 1000)),
    },
    body: JSON.stringify(outboxEntry.payload),
    signal: AbortSignal.timeout(10_000), // 10s timeout — enforce strictly
  });

  if (response.ok) {
    await db.webhookOutbox.update({
      where: { id: outboxEntry.id },
      data: { status: 'DELIVERED' },
    });
  } else if (response.status < 500) {
    // 4xx — client error; mark as permanently failed, notify the endpoint owner
    await db.webhookOutbox.update({
      where: { id: outboxEntry.id },
      data: { status: 'CLIENT_ERROR' },
    });
  } else {
    // 5xx — retry with backoff
    const nextAttempt = new Date(Date.now() + backoffMs(outboxEntry.attempts));
    await db.webhookOutbox.update({
      where: { id: outboxEntry.id },
      data: {
        attempts: { increment: 1 },
        nextAttemptAt: nextAttempt,
        status: outboxEntry.attempts >= 10 ? 'EXHAUSTED' : 'PENDING',
      },
    });
  }
}
```

**Managed webhook delivery (strongly recommended over building from scratch):**

- **Svix** (open-source core, hosted option) — the production-grade open-source webhook
  delivery infrastructure used by many SaaS companies; handles retries, signing, delivery
  logs, dashboard, and consumer management
- **Hookdeck** — managed webhook delivery and event gateway; useful for both sending and
  receiving with built-in retry, inspection, and replay

### When NOT to Rely on Webhooks

- **The sending system doesn't support them** — common for legacy ERPs, government portals,
  older enterprise systems in RPA work; polling is the only alternative
- **You need guaranteed exactly-once delivery** — webhooks are at-least-once; for critical
  financial operations or audit trails, pair webhooks with periodic reconciliation jobs that
  fetch the authoritative state from the provider's API, rather than relying solely on
  webhook delivery

---

## 3. Polling — Pull-Based, Simple, Wasteful

**Use when:** the source system has no webhook support (common for RPA targets: legacy ERPs,
government portals, older SaaS products), or when you need a guaranteed periodic
reconciliation check regardless of webhook reliability.

```typescript
async function pollForChanges() {
  let lastCheckedAt = await getLastPollTimestamp();

  while (true) {
    const changes = await fetchChangesSince(lastCheckedAt);
    for (const change of changes) {
      await processChange(change);
    }
    lastCheckedAt = new Date();
    await savePollTimestamp(lastCheckedAt);

    await sleep(POLL_INTERVAL_MS);  // never poll in a tight loop — always a deliberate interval
  }
}
```

**Polling with adaptive backoff** — reduce load on the source system when nothing is changing:
```typescript
let currentInterval = MIN_INTERVAL_MS;

async function adaptivePoll() {
  const changes = await fetchChangesSince(lastCheckedAt);

  if (changes.length === 0) {
    currentInterval = Math.min(currentInterval * 1.5, MAX_INTERVAL_MS);  // back off when idle
  } else {
    currentInterval = MIN_INTERVAL_MS;  // reset to fast polling when activity is detected
  }

  await sleep(currentInterval);
}
```

### When NOT to Poll

- **A webhook alternative exists** — polling wastes requests (most polls find nothing changed),
  adds latency (average delay is half the poll interval), and puts unnecessary load on the
  source system; always prefer webhooks when the source system supports them
- **Very high-frequency change detection needed** — polling frequently enough to approximate
  real-time defeats its own efficiency advantage over webhooks and may trigger the source
  system's own rate limiting

---

## 4. Long Polling & Server-Sent Events (SSE) — The Middle Ground

For near-real-time updates when full webhook infrastructure isn't available on the source side,
but the client can maintain an open connection:

```typescript
// Server-Sent Events — one-directional server → client stream over plain HTTP
app.get("/events", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const listener = (event: DomainEvent) => {
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  };
  eventEmitter.on("order.updated", listener);

  req.on("close", () => eventEmitter.off("order.updated", listener));
});
```

Appropriate for dashboards and UI updates; less commonly used for system-to-system RPA
integration, where webhooks or polling are more standard.

---

## 5. Pub/Sub — Fully Decoupled, Many-to-Many

**Use when:** multiple independent consumers need to react to the same event, and producers
and consumers should not know about each other directly (see also
`software-architecture/cqrs-event-driven.md` for the architectural treatment of Event-Driven
Architecture).

```
                              ┌──────────────┐
                        ┌────▶│  Consumer A    │
                        │     │ (send email)   │
┌──────────┐    ┌──────────┐│     └──────────────┘
│  Producer  │───▶│  Message   │┤
│(Order svc) │    │  Broker    │┤     ┌──────────────┐
└──────────┘    │(Kafka/SNS/ │└────▶│  Consumer B    │
                  │ RabbitMQ)  │      │ (update CRM)   │
                  └──────────┘      └──────────────┘
```

The producer publishes "order.created" once; it has no knowledge of how many consumers exist
or what they do with the event. Consumers can be added or removed without changing the
producer. Common brokers: Kafka (high-throughput, log-based), AWS SNS/SQS, RabbitMQ,
Azure Service Bus, Google Pub/Sub.

### When NOT to Use Pub/Sub

- **A single consumer, simple point-to-point integration** — a direct API call or webhook is
  simpler to build, trace, and debug than introducing a message broker for one consumer
- **The team has no existing message broker infrastructure and the integration is small-scale**
  — the operational cost of running/maintaining Kafka or RabbitMQ is substantial; a managed
  queue (SQS, Cloud Tasks) or even direct webhooks may be entirely adequate
- **Strict, immediate consistency is required** — pub/sub is inherently asynchronous and
  eventually consistent; if the receiving system must reflect the change before the caller's
  request completes, a synchronous call is the correct choice, not an event
