# API Gateway & Integration Patterns

**Sources:** AWS API Gateway documentation; Azure API Management documentation; Kong Gateway
documentation; Gregor Hohpe & Bobby Woolf, _Enterprise Integration Patterns_ (2003) — the
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

| Product                  | Best for                                    | Notes                                                              |
| ------------------------ | ------------------------------------------- | ------------------------------------------------------------------ |
| **AWS API Gateway**      | AWS-native architectures                    | Tight Lambda integration; usage-based pricing                      |
| **Azure API Management** | Azure-native, enterprise API programs       | Strong developer portal, policy XML for transforms                 |
| **Kong Gateway**         | Cloud-agnostic, self-hosted or Kong Konnect | Plugin ecosystem; open-source core                                 |
| **Cloudflare**           | Edge-first, DDoS/WAF-integrated             | Runs at the edge, closest to the client globally                   |
| **NGINX (as gateway)**   | Simple routing/rate-limiting needs          | Lower-level; more configuration required for full gateway features |

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

## 2. Webhooks — Push-Based Event Notification

**Use when:** you need near-real-time notification of events, and the sending system supports
outbound HTTP callbacks. This is the preferred pattern whenever available — it's efficient
(no wasted polling requests) and timely.

```
Your System                              Partner System
     │                                          │
     │  1. Register webhook URL                  │
     │────────────────────────────────────────▶│
     │                                          │
     │              (time passes — an event happens on their side)
     │                                          │
     │  2. POST /your-webhook-endpoint            │
     │     { event: "order.shipped", data: {...} }│
     │◀────────────────────────────────────────│
     │                                          │
     │  3. 200 OK (acknowledge receipt)           │
     │────────────────────────────────────────▶│
```

### Receiving Webhooks Correctly — Signature Verification (Mandatory)

Never trust an incoming webhook payload without verifying it actually came from the claimed
sender — webhook endpoints are public URLs, and anyone can POST to them.

```typescript
import crypto from 'crypto';

function verifyWebhookSignature(
  payload: string,
  signatureHeader: string,
  webhookSecret: string,
): boolean {
  const expectedSignature = crypto
    .createHmac('sha256', webhookSecret)
    .update(payload)
    .digest('hex');

  // Timing-safe comparison — prevents timing attacks that could leak the signature
  return crypto.timingSafeEqual(
    Buffer.from(signatureHeader),
    Buffer.from(expectedSignature),
  );
}

app.post(
  '/webhooks/partner',
  express.raw({ type: 'application/json' }),
  (req, res) => {
    const signature = req.headers['x-partner-signature'] as string;
    const payload = req.body.toString('utf8'); // raw body — signature is computed over raw bytes

    if (
      !verifyWebhookSignature(payload, signature, process.env.WEBHOOK_SECRET!)
    ) {
      return res.status(401).json({ error: 'Invalid signature' });
    }

    const event = JSON.parse(payload);
    // Process asynchronously — acknowledge receipt FAST, then process
    queue.enqueue(event);
    res.status(200).send(); // acknowledge within a few seconds — most providers time out and retry otherwise
  },
);
```

```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature_header: str, webhook_secret: str) -> bool:
    expected_signature = hmac.new(
        webhook_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    # Timing-safe comparison
    return hmac.compare_digest(signature_header, expected_signature)


@router.post("/webhooks/partner")
async def receive_webhook(request: Request) -> Response:
    raw_body = await request.body()
    signature = request.headers.get("x-partner-signature", "")

    if not verify_webhook_signature(raw_body, signature, settings.WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(raw_body)
    await queue.enqueue(event)  # process asynchronously, acknowledge fast
    return Response(status_code=200)
```

### Webhook Reliability Concerns

**Idempotency (webhooks retry on failure — expect duplicates):**

```typescript
// Most webhook providers retry on non-2xx responses or timeouts — the SAME event
// may arrive more than once. Deduplicate using the event's own ID.
async function processWebhookEvent(event: WebhookEvent) {
  const alreadyProcessed = await redis.get(`webhook:processed:${event.id}`);
  if (alreadyProcessed) return; // already handled this exact event — skip

  await handleEvent(event);
  await redis.setex(`webhook:processed:${event.id}`, 604800, '1'); // 7-day dedup window
}
```

**Ordering is not guaranteed** — webhooks can arrive out of order (e.g., `order.shipped`
before `order.confirmed` due to retry timing). Design handlers to be order-independent, or
include a sequence number/timestamp in the payload and reconcile explicitly.

**Replay protection** — verify the event's timestamp is recent (reject anything older than a
few minutes) to prevent replay attacks using a captured, previously-valid signed payload.

### When NOT to Rely on Webhooks

- **The sending system doesn't support them** — common in RPA integration work with legacy
  systems, government portals, and older enterprise software; polling is the only option
- **You need a guaranteed, ordered, complete event log** — webhooks can be missed (network
  failure during the provider's retry window) or arrive out of order; for critical financial
  or compliance-relevant event streams, pair webhooks with a periodic reconciliation job that
  polls for the authoritative state, rather than trusting webhooks alone

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

    await sleep(POLL_INTERVAL_MS); // never poll in a tight loop — always a deliberate interval
  }
}
```

**Polling with adaptive backoff** — reduce load on the source system when nothing is changing:

```typescript
let currentInterval = MIN_INTERVAL_MS;

async function adaptivePoll() {
  const changes = await fetchChangesSince(lastCheckedAt);

  if (changes.length === 0) {
    currentInterval = Math.min(currentInterval * 1.5, MAX_INTERVAL_MS); // back off when idle
  } else {
    currentInterval = MIN_INTERVAL_MS; // reset to fast polling when activity is detected
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
app.get('/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const listener = (event: DomainEvent) => {
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  };
  eventEmitter.on('order.updated', listener);

  req.on('close', () => eventEmitter.off('order.updated', listener));
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
