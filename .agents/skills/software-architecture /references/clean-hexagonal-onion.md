# Clean Architecture, Hexagonal Architecture & Onion Architecture

**Scope note:** the dependency rule below is language-agnostic — it originates from Robert C.
Martin's (Clean Architecture, 2017) and Alistair Cockburn's (Hexagonal Architecture, 2005)
canonical writing, predating any specific framework. Examples here use TypeScript and Python,
but the identical structure applies in Java (Spring), C# (.NET), Go, Rust, Kotlin, or any
language supporting interfaces and dependency inversion — only the syntax for defining an
interface/protocol and injecting a dependency changes; the layering and dependency direction
do not.

These three patterns are variations of the same core idea: **isolate business logic from
infrastructure**. They differ in terminology and emphasis, but share one non-negotiable rule.

---

## The Shared Rule: The Dependency Rule

Source code dependencies must point only inward. Nothing in an inner layer can know anything
about an outer layer. The database, the web framework, the UI — none of these can be
referenced by your business logic. Business logic depends on nothing; everything else depends
on business logic (via interfaces it defines).

```
┌─────────────────────────────────────────────────┐
│  Frameworks & Drivers (DB, Web, UI, External APIs) │  ← outermost, most volatile
│  ┌─────────────────────────────────────────────┐  │
│  │  Interface Adapters (Controllers, Presenters, │  │
│  │  Repository implementations)                  │  │
│  │  ┌───────────────────────────────────────┐   │  │
│  │  │  Application / Use Cases               │   │  │
│  │  │  (Application-specific business rules)  │   │  │
│  │  │  ┌─────────────────────────────────┐   │   │  │
│  │  │  │  Domain / Entities               │   │   │  │
│  │  │  │  (Enterprise-wide business rules) │   │   │  │
│  │  │  └─────────────────────────────────┘   │   │  │
│  │  └───────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         Dependencies point INWARD only →
```

**Why this matters in practice:** if your domain logic imports `PrismaClient` or `express`
directly, you cannot unit test that logic without a real database or HTTP server, you cannot
swap Prisma for Drizzle without touching business rules, and you cannot reason about the
business rules without also understanding the ORM's API surface.

---

## Clean Architecture (Robert C. Martin)

Four concentric layers, each with a specific responsibility:

| Layer                    | Contains                                                                                 | Depends on                            |
| ------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------- |
| **Entities**             | Enterprise-wide business rules and data structures                                       | Nothing                               |
| **Use Cases**            | Application-specific business rules, orchestrates entities                               | Entities only                         |
| **Interface Adapters**   | Controllers, presenters, gateways — converts data between use cases and external formats | Use Cases, Entities                   |
| **Frameworks & Drivers** | Web framework, database, UI, external services                                           | Everything (it's the outermost layer) |

### TypeScript Implementation

```typescript
// ============================================
// LAYER 1: Entities (domain/entities/order.ts)
// Zero external dependencies — pure business logic
// ============================================
export class Order {
  private constructor(
    public readonly id: string,
    public readonly customerId: string,
    private items: OrderItem[],
    private status: OrderStatus,
  ) {}

  static create(customerId: string, items: OrderItem[]): Order {
    if (items.length === 0) {
      throw new DomainError('Order must have at least one item');
    }
    return new Order(crypto.randomUUID(), customerId, items, 'PENDING');
  }

  get total(): Money {
    return this.items.reduce(
      (sum, item) => sum.add(item.subtotal),
      Money.zero(),
    );
  }

  confirm(): void {
    if (this.status !== 'PENDING') {
      throw new DomainError(`Cannot confirm order in status ${this.status}`);
    }
    this.status = 'CONFIRMED';
  }
}

// ============================================
// LAYER 2: Use Cases (application/use-cases/place-order.ts)
// Depends only on Entities + interfaces it defines itself
// ============================================
export interface OrderRepository {
  save(order: Order): Promise<void>;
  findById(id: string): Promise<Order | null>;
}

export interface PaymentGateway {
  charge(amount: Money, customerId: string): Promise<PaymentResult>;
}

export class PlaceOrderUseCase {
  constructor(
    private readonly orderRepo: OrderRepository, // interface — not a concrete DB class
    private readonly paymentGateway: PaymentGateway, // interface — not Stripe SDK directly
  ) {}

  async execute(input: PlaceOrderInput): Promise<PlaceOrderOutput> {
    const order = Order.create(input.customerId, input.items);

    const payment = await this.paymentGateway.charge(
      order.total,
      input.customerId,
    );
    if (!payment.success) {
      throw new ApplicationError('Payment failed', payment.reason);
    }

    order.confirm();
    await this.orderRepo.save(order);

    return { orderId: order.id, status: 'CONFIRMED' };
  }
}

// ============================================
// LAYER 3: Interface Adapters (adapters/repositories/prisma-order-repository.ts)
// Implements the interfaces defined by the use case layer — depends INWARD
// ============================================
import { PrismaClient } from '@prisma/client';
import type { OrderRepository } from '@/application/use-cases/place-order';
import { Order } from '@/domain/entities/order';

export class PrismaOrderRepository implements OrderRepository {
  constructor(private readonly prisma: PrismaClient) {}

  async save(order: Order): Promise<void> {
    // Map domain entity → Prisma model — this translation lives HERE, not in the domain
    await this.prisma.order.upsert({
      where: { id: order.id },
      create: {
        /* ... */
      },
      update: {
        /* ... */
      },
    });
  }

  async findById(id: string): Promise<Order | null> {
    const record = await this.prisma.order.findUnique({ where: { id } });
    return record ? this.toDomain(record) : null; // reconstruct entity from persistence
  }

  private toDomain(record: /* Prisma type */ any): Order {
    // ...
  }
}

// ============================================
// LAYER 4: Frameworks & Drivers (adapters/http/order-controller.ts)
// The outermost layer — wires everything together
// ============================================
import { Router } from 'express';
import { PlaceOrderUseCase } from '@/application/use-cases/place-order';
import { PrismaOrderRepository } from '@/adapters/repositories/prisma-order-repository';
import { StripePaymentGateway } from '@/adapters/payments/stripe-gateway';

const router = Router();

router.post('/orders', async (req, res) => {
  // Dependency injection happens at the outermost layer — the "composition root"
  const useCase = new PlaceOrderUseCase(
    new PrismaOrderRepository(prisma),
    new StripePaymentGateway(stripeClient),
  );

  try {
    const result = await useCase.execute(req.body);
    res.status(201).json(result);
  } catch (err) {
    if (err instanceof DomainError)
      return res.status(400).json({ error: err.message });
    if (err instanceof ApplicationError)
      return res.status(422).json({ error: err.message });
    throw err; // let the global error handler catch unexpected errors
  }
});
```

### Python (FastAPI) Implementation

```python
# ============================================
# LAYER 1: Entities (domain/entities/order.py)
# ============================================
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"


class DomainError(Exception):
    pass


@dataclass
class Order:
    id: UUID
    customer_id: UUID
    items: list["OrderItem"]
    status: OrderStatus = OrderStatus.PENDING

    @classmethod
    def create(cls, customer_id: UUID, items: list["OrderItem"]) -> "Order":
        if not items:
            raise DomainError("Order must have at least one item")
        return cls(id=uuid4(), customer_id=customer_id, items=items)

    @property
    def total(self) -> "Money":
        return sum((item.subtotal for item in self.items), Money.zero())

    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise DomainError(f"Cannot confirm order in status {self.status}")
        self.status = OrderStatus.CONFIRMED


# ============================================
# LAYER 2: Use Cases (application/use_cases/place_order.py)
# Depends on Protocol interfaces — not concrete implementations
# ============================================
from typing import Protocol


class OrderRepository(Protocol):
    async def save(self, order: Order) -> None: ...
    async def find_by_id(self, order_id: UUID) -> Order | None: ...


class PaymentGateway(Protocol):
    async def charge(self, amount: "Money", customer_id: UUID) -> "PaymentResult": ...


class PlaceOrderUseCase:
    def __init__(self, order_repo: OrderRepository, payment_gateway: PaymentGateway) -> None:
        self._order_repo = order_repo
        self._payment_gateway = payment_gateway

    async def execute(self, input_data: "PlaceOrderInput") -> "PlaceOrderOutput":
        order = Order.create(input_data.customer_id, input_data.items)

        payment = await self._payment_gateway.charge(order.total, input_data.customer_id)
        if not payment.success:
            raise ApplicationError(f"Payment failed: {payment.reason}")

        order.confirm()
        await self._order_repo.save(order)

        return PlaceOrderOutput(order_id=order.id, status="CONFIRMED")


# ============================================
# LAYER 3: Interface Adapters (adapters/repositories/sqlalchemy_order_repository.py)
# ============================================
from sqlalchemy.ext.asyncio import AsyncSession


class SQLAlchemyOrderRepository:  # implicitly satisfies the OrderRepository Protocol
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, order: Order) -> None:
        model = self._to_model(order)  # translation lives here, not in the domain
        await self._session.merge(model)
        await self._session.commit()

    async def find_by_id(self, order_id: UUID) -> Order | None:
        model = await self._session.get(OrderModel, order_id)
        return self._to_domain(model) if model else None

    def _to_domain(self, model: "OrderModel") -> Order: ...
    def _to_model(self, order: Order) -> "OrderModel": ...


# ============================================
# LAYER 4: Frameworks & Drivers (api/v1/orders.py)
# ============================================
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/orders")


def get_place_order_use_case(db: DBSession) -> PlaceOrderUseCase:
    """Composition root — wires concrete adapters into the use case."""
    return PlaceOrderUseCase(
        order_repo=SQLAlchemyOrderRepository(db),
        payment_gateway=StripePaymentGateway(),
    )


@router.post("/", status_code=201)
async def place_order(
    payload: PlaceOrderRequest,
    use_case: Annotated[PlaceOrderUseCase, Depends(get_place_order_use_case)],
):
    try:
        return await use_case.execute(payload.to_input())
    except DomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ApplicationError as e:
        raise HTTPException(status_code=422, detail=str(e))
```

---

## Hexagonal Architecture / Ports & Adapters (Alistair Cockburn)

Conceptually identical to Clean Architecture's dependency rule, but described differently:
the application core exposes **ports** (interfaces) that **adapters** plug into — from either
side. There is no inherent "top" or "bottom"; driving adapters (HTTP controllers, CLI, message
consumers) call INTO the application; driven adapters (database, external APIs) are called
BY the application.

```
        Driving Adapters                    Driven Adapters
    (things that call the app)          (things the app calls)

┌──────────────┐                                          ┌──────────────┐
│  HTTP API     │──┐                                    ┌──│  PostgreSQL   │
└──────────────┘  │                                     │  └──────────────┘
┌──────────────┐  │   ┌─────────────────────────┐       │  ┌──────────────┐
│  CLI          │──┼──▶│   Application Core       │◀──────┼──│  Stripe API   │
└──────────────┘  │   │   (Ports = interfaces)   │       │  └──────────────┘
┌──────────────┐  │   └─────────────────────────┘       │  ┌──────────────┐
│  Message Queue│──┘                                     └──│  Email Service│
└──────────────┘         Driving Port          Driven Port  └──────────────┘
                          (implemented BY       (implemented FOR
                           the core)              the core to call)
```

**The distinction that matters in practice:** Hexagonal makes explicit that the same
application core can be driven by multiple entry points (REST API today, a CLI tool
tomorrow, a message consumer next month) without any change to business logic — because
all of them talk to the core through the same ports.

```typescript
// Driving port — the core exposes this; adapters call it
export interface PlaceOrderPort {
  execute(input: PlaceOrderInput): Promise<PlaceOrderOutput>;
}

// Driven port — the core defines this; adapters implement it
export interface NotifyCustomerPort {
  notify(customerId: string, message: string): Promise<void>;
}

// The core implements the driving port and depends on the driven port
export class PlaceOrderUseCase implements PlaceOrderPort {
  constructor(
    private readonly orderRepo: OrderRepository,
    private readonly notifier: NotifyCustomerPort, // driven port
  ) {}
  async execute(input: PlaceOrderInput): Promise<PlaceOrderOutput> {
    // ...
    await this.notifier.notify(input.customerId, 'Order confirmed');
    // ...
  }
}

// Two different driven adapters implementing the same port —
// swap freely without touching the core
class EmailNotifier implements NotifyCustomerPort {
  async notify(customerId: string, message: string) {
    /* SendGrid, SES, etc. */
  }
}
class SlackNotifier implements NotifyCustomerPort {
  async notify(customerId: string, message: string) {
    /* Slack webhook */
  }
}

// Two different driving adapters calling the same core through the same port
class HttpOrderController {
  constructor(private readonly placeOrder: PlaceOrderPort) {}
  async handle(req: Request) {
    return this.placeOrder.execute(req.body);
  }
}
class CliPlaceOrderCommand {
  constructor(private readonly placeOrder: PlaceOrderPort) {}
  async run(args: string[]) {
    return this.placeOrder.execute(parseArgs(args));
  }
}
```

---

## Onion Architecture (Jeffrey Palermo)

A third framing of the same dependency rule, emphasizing concentric rings with domain model
at the absolute center, domain services in the next ring, then application services, then the
outermost ring of infrastructure and UI. The practical difference from Clean Architecture is
mostly terminology; Onion places slightly more emphasis on **domain services** as their own
ring, distinct from application-level use cases — relevant primarily when using DDD tactical
patterns alongside this structure (see `references/ddd.md`).

In practice, most production codebases don't need to distinguish rigorously between Clean,
Hexagonal, and Onion — they converge on the same rule. Pick whichever vocabulary your team
already understands and be consistent.

---

## Project Structure (applies to all three)

```
src/
├── domain/                    # Innermost — zero external dependencies
│   ├── entities/
│   ├── value-objects/
│   └── errors.ts
├── application/                # Use cases + ports (interfaces)
│   ├── use-cases/
│   └── ports/
│       ├── order-repository.ts    # driven port
│       └── payment-gateway.ts     # driven port
├── adapters/                   # Implements ports; converts formats
│   ├── repositories/          # driven adapters — DB implementations
│   ├── gateways/               # driven adapters — external API implementations
│   └── http/                   # driving adapters — controllers
├── infrastructure/              # Framework wiring, DI container, config
│   ├── di-container.ts
│   └── server.ts
└── main.ts                     # Composition root — the only place that wires everything
```

---

## When NOT to Use This Pattern (Over-Engineering Check)

This layering has a real cost: more files, more indirection, more upfront design time before
writing the first feature. It earns that cost when:

- Business logic is genuinely complex and needs to be unit-tested independent of infrastructure
- You expect to swap infrastructure (database, payment provider) during the project's life
- Multiple entry points will drive the same business logic (API + CLI + worker)
- The team is large enough that clear boundaries prevent accidental coupling

**Do not use it when:**

- Building a CRUD app with thin logic that's basically "validate → save to DB" — the extra
  layers add ceremony without adding testability that matters
- A solo developer or small team prototyping an MVP where speed matters more than long-term
  flexibility — you can always introduce this structure later, once the domain stabilizes
- The "business logic" is really just orchestrating third-party API calls with minimal
  decision-making of its own
- You're using a framework (like a T3 Stack app with tRPC) where the framework's own
  conventions (routers, procedures) already provide adequate separation for the project's size

**Warning sign of over-application:** if implementing a single new field requires touching five
layers (entity, use case, port, adapter, controller) for a project with three team members and
low domain complexity, the architecture is fighting the team rather than helping it. Collapse
layers pragmatically — a "services" folder calling the ORM directly is often entirely
appropriate for small-to-medium applications.
