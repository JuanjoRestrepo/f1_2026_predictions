# Domain-Driven Design (DDD)

**Source:** Eric Evans, _Domain-Driven Design: Tackling Complexity in the Heart of Software_
(2003); refined by Vaughn Vernon, _Implementing Domain-Driven Design_ (2013). DDD is
language-agnostic by definition — it is a modeling discipline, not a framework. Examples below
use TypeScript and Python; the same tactical patterns (entities, value objects, aggregates)
are equally canonical in Java, C#, and any language with encapsulation and type systems.

DDD has two halves that are often confused: **strategic design** (how to organize large
domains and teams) and **tactical design** (how to model individual pieces of business logic
in code). Most teams that "try DDD and hate it" only adopted the tactical patterns without the
strategic thinking that justifies them — resulting in ceremony without benefit.

---

## Strategic DDD — Organizing the Domain

### Ubiquitous Language

The single most important and most skipped DDD practice: the vocabulary used in code must be
**identical** to the vocabulary domain experts use — no translation layer between what the
business calls something and what the variable/class is named.

```typescript
// ❌ WRONG — generic technical naming, no domain vocabulary
class Record {
  status: number; // 0, 1, 2 — meaning lives only in a comment somewhere
}

// ✅ CORRECT — matches exactly what underwriters call it in meetings
class InsurancePolicy {
  underwritingStatus: UnderwritingStatus; // "Pending Review", "Bound", "Declined" — real terms
}
```

If your domain experts call something a "Claim" and your code calls it a "Ticket", every
conversation between engineering and the business requires mental translation — and that
translation gap is where requirements get lost.

### Bounded Contexts

A large domain (e.g., "e-commerce") cannot have one unified model — the concept of a
"Product" means something different to Catalog, Inventory, Shipping, and Pricing. Rather than
forcing one god-model, DDD defines explicit **boundaries** where a model is internally
consistent, and different models are allowed to exist on either side of the boundary.

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Catalog Context     │     │  Inventory Context    │     │  Shipping Context      │
│                       │     │                       │     │                       │
│  Product {            │     │  Product {            │     │  Product {            │
│    name, description,  │     │    sku, quantityInStock,│     │    weight, dimensions,│
│    images, category    │     │    warehouseLocation   │     │    fragile: bool       │
│  }                    │     │  }                    │     │  }                    │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

Each context has its own database, its own model, its own team ownership (ideally). This is
the strategic-level decision that later determines microservice boundaries, if and when you
introduce microservices (see `references/microservices-monolith.md`) — bounded contexts are
the correct unit of decomposition; arbitrary technical splitting is not.

### Context Mapping

Documents how bounded contexts relate to and integrate with each other. The canonical
relationship patterns:

| Pattern                         | Meaning                                                                           | When to use                                                                      |
| ------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **Shared Kernel**               | Two contexts share a small, jointly-owned subset of the model                     | Tightly collaborating teams, small shared concept (e.g., `Money` value object)   |
| **Customer/Supplier**           | Upstream context's team commits to serving downstream's needs                     | Clear internal dependency with negotiation power                                 |
| **Conformist**                  | Downstream simply accepts upstream's model as-is, no negotiation                  | Integrating with a third-party or a team you have no influence over              |
| **Anti-Corruption Layer (ACL)** | Downstream translates upstream's model into its own, protecting its domain purity | Integrating with legacy systems or external APIs whose model doesn't match yours |
| **Open Host Service**           | Upstream publishes a well-defined protocol/API for many downstream consumers      | Public APIs, platform services used by many teams                                |
| **Published Language**          | A shared, well-documented interchange format (e.g., a standard schema)            | Cross-organization integration, industry-standard data formats                   |

The Anti-Corruption Layer is the pattern used most often in production and deserves a concrete
example — see `references/api-first-integration-nfrs.md` for the implementation pattern.

---

## Tactical DDD — Modeling in Code

### Entities

An object defined by a persistent **identity**, not by its attributes. Two entities with
identical attributes but different IDs are different entities. Identity survives attribute
changes across the object's lifetime.

```typescript
export class Customer {
  constructor(
    public readonly id: CustomerId, // identity — never changes
    private email: Email, // attribute — can change
    private loyaltyTier: LoyaltyTier, // attribute — can change
  ) {}

  changeEmail(newEmail: Email): void {
    // Business rule enforcement lives INSIDE the entity, not in a service that mutates it
    if (this.loyaltyTier === 'SUSPENDED') {
      throw new DomainError('Cannot change email on a suspended account');
    }
    this.email = newEmail;
  }

  equals(other: Customer): boolean {
    return this.id.equals(other.id); // identity comparison, not attribute comparison
  }
}
```

```python
from dataclasses import dataclass, field


@dataclass
class Customer:
    id: CustomerId               # identity — never changes
    email: Email                 # attribute — can change
    loyalty_tier: LoyaltyTier    # attribute — can change

    def change_email(self, new_email: Email) -> None:
        if self.loyalty_tier == LoyaltyTier.SUSPENDED:
            raise DomainError("Cannot change email on a suspended account")
        self.email = new_email

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Customer) and self.id == other.id  # identity, not attributes
```

### Value Objects

An object defined entirely by its **attributes**, with no identity. Two value objects with the
same attributes are interchangeable and equal. Value objects should be immutable.

```typescript
export class Money {
  private constructor(
    private readonly amount: number,
    private readonly currency: string,
  ) {
    if (amount < 0) throw new DomainError('Money cannot be negative');
  }

  static of(amount: number, currency: string): Money {
    return new Money(amount, currency);
  }

  static zero(currency = 'USD'): Money {
    return new Money(0, currency);
  }

  add(other: Money): Money {
    if (this.currency !== other.currency) {
      throw new DomainError(`Cannot add ${other.currency} to ${this.currency}`);
    }
    return new Money(this.amount + other.amount, this.currency); // returns NEW instance
  }

  equals(other: Money): boolean {
    return this.amount === other.amount && this.currency === other.currency;
  }
}

// Usage — no setters, every operation returns a new value
const price = Money.of(29.99, 'USD');
const tax = Money.of(2.4, 'USD');
const total = price.add(tax); // price and tax are unchanged; total is a new Money
```

```python
from dataclasses import dataclass


@dataclass(frozen=True)  # frozen=True enforces immutability at the language level
class Money:
    amount: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DomainError("Money cannot be negative")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise DomainError(f"Cannot add {other.currency} to {self.currency}")
        return Money(self.amount + other.amount, self.currency)  # new instance
```

**Why this distinction matters:** modeling something as an entity when it should be a value
object introduces unnecessary identity tracking (database IDs, equality-by-reference bugs).
Modeling a value object as an entity is the most common DDD tactical mistake — `Address`,
`Money`, `DateRange`, `EmailAddress` are almost always value objects, never entities.

### Aggregates & Aggregate Roots

A cluster of entities and value objects treated as a single consistency boundary. One entity
in the cluster is the **aggregate root** — the only object external code is allowed to
reference directly. All modifications to objects inside the aggregate go through the root,
which enforces invariants across the whole cluster.

```typescript
// Order is the aggregate root; OrderLine is an entity that only exists within Order
export class Order {
  private lines: OrderLine[] = [];

  private constructor(
    public readonly id: OrderId,
    private status: OrderStatus,
  ) {}

  static create(id: OrderId): Order {
    return new Order(id, 'DRAFT');
  }

  // ✅ External code calls THIS — never manipulates lines directly
  addLine(product: ProductId, quantity: number, unitPrice: Money): void {
    if (this.status !== 'DRAFT') {
      throw new DomainError('Cannot modify a submitted order');
    }
    if (this.lines.length >= 100) {
      throw new DomainError('Order cannot exceed 100 line items'); // invariant enforced HERE
    }
    this.lines.push(OrderLine.create(product, quantity, unitPrice));
  }

  submit(): void {
    if (this.lines.length === 0) {
      throw new DomainError('Cannot submit an empty order'); // aggregate-level invariant
    }
    this.status = 'SUBMITTED';
  }

  // Read access is fine — mutation access is not
  get lineItems(): ReadonlyArray<OrderLine> {
    return [...this.lines];
  }
}

// ❌ WRONG — never do this; bypasses the root's invariant enforcement
// order.lines.push(new OrderLine(...));  // lines is private — this shouldn't even compile

// ✅ CORRECT — always go through the root
order.addLine(productId, 2, Money.of(19.99, 'USD'));
```

**Aggregate design rule (Vernon):** keep aggregates small. A common mistake is designing one
giant `Order` aggregate that includes `Customer`, `Payment`, `ShippingAddress`, and
`Inventory` — this creates massive contention under concurrent writes and couples unrelated
consistency concerns. Reference other aggregates **by ID only**, never by direct object
reference:

```typescript
export class Order {
  // ✅ CORRECT — reference by ID, Customer is a separate aggregate
  private customerId: CustomerId;

  // ❌ WRONG — direct reference couples the Order aggregate to the full Customer aggregate
  // private customer: Customer;
}
```

### Domain Events

A record of something significant that happened in the domain, expressed in past tense,
raised by an aggregate, and used to trigger side effects in other parts of the system without
coupling the aggregate to those side effects directly.

```typescript
export interface DomainEvent {
  readonly occurredAt: Date;
  readonly eventName: string;
}

export class OrderSubmitted implements DomainEvent {
  readonly occurredAt = new Date();
  readonly eventName = 'OrderSubmitted';
  constructor(
    public readonly orderId: string,
    public readonly customerId: string,
    public readonly total: Money,
  ) {}
}

export class Order {
  private domainEvents: DomainEvent[] = [];

  submit(): void {
    if (this.lines.length === 0)
      throw new DomainError('Cannot submit an empty order');
    this.status = 'SUBMITTED';
    // Record the event — doesn't know or care who will react to it
    this.domainEvents.push(
      new OrderSubmitted(this.id, this.customerId, this.total),
    );
  }

  pullDomainEvents(): DomainEvent[] {
    const events = [...this.domainEvents];
    this.domainEvents = [];
    return events;
  }
}

// In the application layer / use case — after persisting, dispatch the events
export class SubmitOrderUseCase {
  async execute(orderId: string): Promise<void> {
    const order = await this.orderRepo.findById(orderId);
    order.submit();
    await this.orderRepo.save(order);

    const events = order.pullDomainEvents();
    for (const event of events) {
      await this.eventBus.publish(event); // decoupled — inventory, email, analytics all react independently
    }
  }
}
```

This is the natural bridge into Event-Driven Architecture — see
`references/cqrs-event-driven.md` for how domain events become integration events consumed by
other bounded contexts or services.

### Repositories

An abstraction that gives the illusion of an in-memory collection of aggregates, hiding all
persistence details. Defined as an interface in the domain/application layer, implemented in
the infrastructure layer (see `references/clean-hexagonal-onion.md`).

```typescript
export interface OrderRepository {
  findById(id: OrderId): Promise<Order | null>;
  save(order: Order): Promise<void>;
  // ❌ Do NOT expose query builders, SQL, or ORM-specific methods here —
  // that leaks infrastructure concerns into the domain layer
}
```

### Domain Services

When an operation doesn't naturally belong to any single entity or value object — often
because it involves coordinating multiple aggregates — model it as a domain service instead
of forcing it awkwardly onto one entity.

```typescript
// A transfer between two accounts doesn't belong to either Account alone
export class MoneyTransferService {
  transfer(from: Account, to: Account, amount: Money): void {
    from.withdraw(amount); // each aggregate still enforces its own invariants
    to.deposit(amount);
  }
}
```

---

## When NOT to Use DDD (Over-Engineering Check)

DDD's tactical patterns add real overhead: more classes, more indirection between "the data"
and "the object holding the data," and a steeper onboarding curve for engineers unfamiliar with
the discipline. It earns that cost when:

- The domain has genuinely complex business rules with many invariants to protect
  (insurance underwriting, financial transaction processing, complex scheduling/logistics)
- Domain experts and engineers need a shared, precise vocabulary because miscommunication has
  historically caused expensive bugs or rework
- The system will be maintained by a growing team over years, where implicit knowledge
  ("everyone just knows how orders work") doesn't scale

**Do not use it when:**

- The domain is simple CRUD with minimal business rules — "create a blog post, list blog
  posts, delete a blog post" does not need entities, value objects, and aggregates; a Prisma
  model and a thin service function are sufficient and clearer
- The team is small and the domain owner is also the sole engineer — the communication
  problem DDD's ubiquitous language solves doesn't exist yet
- Applying strategic DDD (bounded contexts) to a system with one obvious, unified domain and
  no plan to split teams or services — bounded contexts without multiple contexts is ceremony

**Warning sign of over-application:** if every table in your database has a corresponding
Entity class, Value Object wrappers for every string and number field, and a Repository
interface — regardless of whether any of those fields have actual business rules attached —
you have adopted DDD's vocabulary without its judgment. Apply tactical patterns selectively,
only where genuine domain complexity exists; a `User` entity might deserve rich DDD modeling
while a `NewsletterSubscription` next to it might just be a database row with a save function.
