# CQRS & Event-Driven Architecture

**Sources:** Greg Young popularized CQRS (Command Query Responsibility Segregation, building on
Bertrand Meyer's Command-Query Separation principle, 1988); Event Sourcing is documented
extensively by Martin Fowler and Greg Young; Event-Driven Architecture draws on decades of
enterprise messaging patterns (Gregor Hohpe & Bobby Woolf, _Enterprise Integration Patterns_,
2003). All are language-agnostic — implemented natively in Java (Axon Framework), .NET
(MediatR, EventStoreDB), and every other major ecosystem. Examples below use TypeScript and
Python.

---

## CQRS — Command Query Responsibility Segregation

### The Core Idea

Separate the model used to **write** data (Commands) from the model used to **read** data
(Queries). In standard CRUD, one model serves both — the same `Order` class is used to both
validate business rules on write and shape API responses on read. CQRS splits these into two
independent paths.

```
┌──────────────┐         ┌─────────────────────┐         ┌───────────────┐
│   Command      │────────▶│   Write Model         │────────▶│  Write DB       │
│   (PlaceOrder) │         │   (rich domain model,  │         │  (normalized,   │
└──────────────┘         │    enforces invariants)│         │   optimized for │
                          └─────────────────────┘         │   consistency)  │
                                                             └───────────────┘
                                      │
                                      │ sync or async
                                      ▼
┌──────────────┐         ┌─────────────────────┐         ┌───────────────┐
│   Query        │◀────────│   Read Model          │◀────────│  Read DB        │
│   (GetOrderList)│         │   (denormalized, flat,│         │  (denormalized, │
└──────────────┘         │    shaped for display) │         │   optimized for │
                          └─────────────────────┘         │   query speed)  │
                                                             └───────────────┘
```

### Why Separate Them

Write operations need to enforce invariants (see the Aggregate pattern in `references/ddd.md`)
— they benefit from a normalized schema and rich domain objects. Read operations need to be
fast and shaped exactly for the UI — they benefit from denormalized, pre-joined, sometimes
even pre-aggregated data. Forcing one model to serve both leads to either an over-normalized
API response (requiring client-side joins) or a domain model littered with display-only
computed properties that have nothing to do with business rules.

### Implementation — Simplest Form (Same Database, Separate Models)

This is the level of CQRS most production systems should stop at. No event bus, no
eventual consistency — just two different code paths querying the same database differently.

```typescript
// ============================================
// WRITE SIDE — Commands
// ============================================
export interface PlaceOrderCommand {
  customerId: string;
  items: { productId: string; quantity: number }[];
}

export class PlaceOrderCommandHandler {
  constructor(
    private readonly orderRepo: OrderRepository, // rich domain model
    private readonly eventBus: EventBus,
  ) {}

  async handle(command: PlaceOrderCommand): Promise<{ orderId: string }> {
    const order = Order.create(command.customerId, command.items); // full invariant checking
    await this.orderRepo.save(order);
    await this.eventBus.publish(order.pullDomainEvents());
    return { orderId: order.id };
  }
}

// ============================================
// READ SIDE — Queries (separate, denormalized, no domain logic)
// ============================================
export interface OrderListItemDTO {
  orderId: string;
  customerName: string; // denormalized — joined at query time or pre-computed
  itemCount: number;
  total: string; // pre-formatted for display — never done on the write side
  placedAt: string;
}

export class GetCustomerOrdersQueryHandler {
  constructor(private readonly db: DatabaseClient) {}

  // Direct SQL/query — bypasses the domain model entirely; this is intentional
  async handle(customerId: string): Promise<OrderListItemDTO[]> {
    return this.db.query<OrderListItemDTO>(
      `
      SELECT
        o.id as "orderId",
        c.name as "customerName",
        COUNT(oi.id) as "itemCount",
        TO_CHAR(o.total, 'FM$999,999.00') as "total",
        TO_CHAR(o.placed_at, 'YYYY-MM-DD') as "placedAt"
      FROM orders o
      JOIN customers c ON c.id = o.customer_id
      JOIN order_items oi ON oi.order_id = o.id
      WHERE o.customer_id = $1
      GROUP BY o.id, c.name, o.total, o.placed_at
      ORDER BY o.placed_at DESC
    `,
      [customerId],
    );
  }
}
```

```python
# Python / FastAPI equivalent

# Write side — command handler uses the rich domain model
class PlaceOrderCommandHandler:
    def __init__(self, order_repo: OrderRepository, event_bus: EventBus) -> None:
        self._order_repo = order_repo
        self._event_bus = event_bus

    async def handle(self, command: PlaceOrderCommand) -> dict:
        order = Order.create(command.customer_id, command.items)  # full invariant checking
        await self._order_repo.save(order)
        await self._event_bus.publish(order.pull_domain_events())
        return {"order_id": str(order.id)}


# Read side — raw query, denormalized, no domain model involved
class GetCustomerOrdersQueryHandler:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def handle(self, customer_id: UUID) -> list[OrderListItemDTO]:
        result = await self._session.execute(
            text("""
                SELECT o.id, c.name as customer_name, COUNT(oi.id) as item_count,
                       o.total, o.placed_at
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                JOIN order_items oi ON oi.order_id = o.id
                WHERE o.customer_id = :customer_id
                GROUP BY o.id, c.name, o.total, o.placed_at
                ORDER BY o.placed_at DESC
            """),
            {"customer_id": customer_id},
        )
        return [OrderListItemDTO(**row._mapping) for row in result]
```

### Implementation — Full Form (Separate Read Database)

Reserved for systems with a real, measured read/write scaling asymmetry. The write model
publishes domain events; a projector consumes them and maintains a separate, denormalized
read store (often a different database technology entirely — e.g., Postgres for writes,
Elasticsearch or a materialized view store for reads).

```typescript
// Event handler that maintains the read model — runs asynchronously, decoupled from the command
export class OrderPlacedProjector {
  constructor(private readonly readDb: ReadDatabaseClient) {}

  async on(event: OrderPlaced): Promise<void> {
    // Build the exact shape the UI needs — pre-joined, pre-computed
    await this.readDb.upsert('order_summaries', {
      orderId: event.orderId,
      customerName: await this.lookupCustomerName(event.customerId),
      total: event.total.toDisplayString(),
      placedAt: event.occurredAt,
    });
  }
}
```

**The cost of the full form:** the read model is only _eventually_ consistent with the write
model — there is a window (usually milliseconds, but not zero) where a just-placed order
doesn't yet appear in the read model. Every team introducing this must explicitly decide how
the UI handles that window (optimistic UI updates, polling, or accepting the lag).

---

## Event-Driven Architecture (EDA)

### The Core Idea

Services/components communicate by publishing and subscribing to events rather than calling
each other directly. A service that changes state publishes an event describing what happened;
any number of other services can react to it without the publisher knowing or caring who is
listening.

```
┌──────────────┐   publishes    ┌──────────────┐   consumed by   ┌──────────────┐
│  Order Service │──────────────▶│  Message Broker│───────────────▶│ Inventory Svc  │
└──────────────┘   OrderPlaced  │ (Kafka/RabbitMQ/│                └──────────────┘
                                 │  SQS/EventBridge)│───────────────▶┌──────────────┐
                                 └──────────────┘                 │  Email Service  │
                                                                    └──────────────┘
                                                     ───────────────▶┌──────────────┐
                                                                     │  Analytics Svc  │
                                                                     └──────────────┘
```

**Contrast with direct/synchronous calls:** without EDA, `OrderService` would need to call
`InventoryService.reserve()`, `EmailService.send()`, and `AnalyticsService.track()` directly —
coupling it to all three, and failing the whole operation if any one of them is down. With
EDA, `OrderService` publishes one event and moves on; each consumer handles its own failures
independently.

### Message Broker Comparison

| Broker                      | Model                                            | Best for                                                                                        |
| --------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| **Kafka**                   | Distributed log, consumer groups, replay-capable | High-throughput event streaming, event sourcing, multiple consumers needing independent offsets |
| **RabbitMQ**                | Traditional message queue, routing via exchanges | Task queues, RPC-style messaging, complex routing rules                                         |
| **AWS SQS + SNS**           | Managed queue (SQS) + pub/sub fan-out (SNS)      | AWS-native systems avoiding self-hosted broker operations                                       |
| **AWS EventBridge**         | Managed event bus with content-based routing     | Serverless architectures, SaaS integrations, schema registry built-in                           |
| **Redis Streams / Pub/Sub** | Lightweight, in-memory (Streams add persistence) | Low-latency, smaller-scale systems already using Redis                                          |

### Event Schema Design

Events should describe **what happened** (past tense, immutable fact), not **what should
happen next** (that's a command, a different message type entirely).

```typescript
// ✅ CORRECT — an event, describing a fact
interface OrderPlaced {
  eventType: 'OrderPlaced';
  eventVersion: 1; // always version your event schemas
  occurredAt: string; // ISO 8601
  orderId: string;
  customerId: string;
  items: { productId: string; quantity: number }[];
  totalCents: number; // use integers for money — never floats
}

// ❌ WRONG — this is a command disguised as an event; it tells consumers what to DO
interface ShouldReserveInventory {
  productId: string;
  quantity: number;
}
```

**Schema evolution rule:** always add an `eventVersion` field. When the event shape changes,
increment the version and support both versions in consumers during the migration window —
never silently break the schema of an event already being consumed in production.

```typescript
// Consumer handling multiple event versions during a migration
function handleOrderPlaced(event: OrderPlacedV1 | OrderPlacedV2) {
  if (event.eventVersion === 1) {
    // handle legacy shape
  } else {
    // handle current shape
  }
}
```

### Idempotency — Mandatory for Event Consumers

Message brokers generally guarantee **at-least-once** delivery, not exactly-once. Every
consumer must be idempotent — processing the same event twice must not cause duplicate side
effects.

```typescript
export class ReserveInventoryOnOrderPlaced {
  async handle(event: OrderPlaced): Promise<void> {
    // Idempotency check — has this event already been processed?
    const alreadyProcessed = await this.db.exists(
      'processed_events',
      event.eventId,
    );
    if (alreadyProcessed) return; // safe no-op on redelivery

    await this.inventoryService.reserve(event.items);
    await this.db.insert('processed_events', {
      eventId: event.eventId,
      processedAt: new Date(),
    });
  }
}
```

---

## Event Sourcing (Often Paired with CQRS, but a Distinct Pattern)

Rather than storing current state (a row that gets UPDATEd), store the full sequence of
events that led to that state. Current state is derived by replaying events — never stored as
the primary source of truth.

```typescript
// Instead of: orders table with a `status` column that gets overwritten
// Store: an append-only event log
type OrderEvent =
  | { type: 'OrderCreated'; orderId: string; customerId: string }
  | { type: 'ItemAdded'; orderId: string; productId: string; quantity: number }
  | { type: 'OrderSubmitted'; orderId: string }
  | { type: 'OrderCancelled'; orderId: string; reason: string };

// Current state is REBUILT by folding over the event history
function reconstructOrder(events: OrderEvent[]): Order {
  return events.reduce((order, event) => {
    switch (event.type) {
      case 'OrderCreated':
        return Order.empty(event.orderId, event.customerId);
      case 'ItemAdded':
        return order.withItemAdded(event.productId, event.quantity);
      case 'OrderSubmitted':
        return order.withStatus('SUBMITTED');
      case 'OrderCancelled':
        return order.withStatus('CANCELLED');
    }
  }, Order.uninitialized());
}
```

**What this buys you:** a complete, immutable audit trail for free; the ability to answer "what
did this order look like at 3pm yesterday" by replaying events up to that point; the ability to
fix a bug in projection logic and rebuild all read models from scratch, from history.

**What it costs:** every query for current state requires either replaying the full event
history (slow without snapshotting) or maintaining a separate, continuously-updated snapshot/
projection — meaning Event Sourcing almost always implies CQRS as well, since you need a
denormalized read model to query efficiently. Debugging "what is the current state" requires
understanding the full fold logic, not just reading a row.

---

## When NOT to Use CQRS / Event-Driven / Event Sourcing (Over-Engineering Check)

**CQRS** earns its cost when:

- Read and write workloads have measurably different scaling needs (e.g., 1000x more reads
  than writes, or reads need complex denormalized aggregation that would be slow against the
  normalized write schema)
- The read-side shape genuinely diverges from the write-side domain model (dashboards,
  reports, search — very different from the entity used to enforce business rules)

**Do not use CQRS when:**

- The application is small-to-medium CRUD where the same model serves reads and writes fine
- "We might need to scale reads separately someday" — without a measured current bottleneck,
  this is speculative complexity; the simple form (same DB, different query functions) already
  gives 90% of the benefit with none of the eventual-consistency cost

**Event-Driven Architecture** earns its cost when:

- Multiple independent services/teams need to react to the same state change without being
  coupled to the publisher's release cycle or uptime
- The system genuinely has fire-and-forget side effects that don't need to block the primary
  operation (sending a confirmation email should not fail the checkout flow)

**Do not use EDA when:**

- A direct function call or synchronous API call would work fine and the operation needs an
  immediate, consistent response (e.g., checking inventory availability during checkout —
  the customer needs to know NOW, not eventually)
- Introducing a message broker purely for "decoupling" in a monolith with 2 services — this
  adds an entire piece of infrastructure to operate, monitor, and debug, for a coupling
  problem that an interface/dependency injection already solves within a single process

**Event Sourcing** earns its cost when:

- Regulatory or business requirements demand a complete, tamper-evident audit trail
- The domain genuinely benefits from historical replay (financial ledgers, inventory
  reconciliation, understanding exactly how a state was reached)

**Do not use Event Sourcing when:**

- You only want "an audit log" — a simple `AuditLog` table with before/after snapshots on
  each write achieves this without rebuilding your entire persistence model around it
- The team has no prior experience with it — it is the highest-learning-curve pattern in this
  file, and mistakes in projection logic are notoriously hard to debug in production

**Warning sign of over-application:** if a team adopts Kafka, event sourcing, and full CQRS
with separate read/write databases for an internal admin tool used by 12 people, the
operational burden (running and monitoring a message broker, reasoning about eventual
consistency, debugging replay logic) vastly exceeds any benefit. These three patterns are
frequently reached for because they are technically interesting, not because the problem
requires them — that instinct should be treated with suspicion, not celebrated.
