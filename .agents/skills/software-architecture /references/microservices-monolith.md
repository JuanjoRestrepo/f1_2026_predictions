# Microservices vs Modular Monolith

**Sources:** Sam Newman, _Building Microservices_ (2015, 2nd ed. 2021) — the canonical
industry reference; Martin Fowler's writing on the "Monolith First" strategy and the
"Distributed Monolith" anti-pattern; Melvin Conway's Conway's Law (1967) — team structure
inevitably shapes system architecture. Language-agnostic at the decision level; the trade-offs
discussed apply whether services are written in TypeScript, Python, Java, Go, or any mix.

---

## The Decision Is About Organization, Not Technology

The most common mistake in this decision is treating it as a technical choice ("microservices
are more scalable") when it is primarily an **organizational and operational** choice. A single
well-architected monolith can scale to enormous load (Shopify, GitHub, and Stack Overflow all
ran/run substantially monolithic for years at large scale). Microservices solve a coordination
problem between teams more than they solve a technical scaling problem.

---

## Modular Monolith

A single deployable application, internally organized into strict modules with enforced
boundaries — each module owns its own data access and exposes only a defined interface to
other modules. It is a monolith at the deployment level and (ideally) a well-bounded set of
domains at the code level.

```
┌─────────────────────────────────────────────────────────┐
│                  Single Deployable Application              │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  │
│  │  Orders Module  │  │ Inventory Module│  │ Billing Module │  │
│  │                │  │                │  │                │  │
│  │  - own tables   │  │  - own tables   │  │  - own tables   │  │
│  │  - own service  │  │  - own service  │  │  - own service  │  │
│  │  - public API   │◀─┼─ calls via     │  │  - public API   │  │
│  │    (interface)  │  │    interface   │  │                │  │
│  └───────────────┘  └───────────────┘  └───────────────┘  │
│         ▲                                        ▲          │
│         └────────────────────────────────────────┘          │
│              modules call each other's PUBLIC interface       │
│              only — never reach into another module's data    │
└─────────────────────────────────────────────────────────┘
                  Single database, single deploy
```

### Enforcing Module Boundaries in Code

```typescript
// src/modules/orders/index.ts — the ONLY file other modules may import from
export { OrderService } from './order-service';
export type { Order, OrderStatus } from './types';
// Everything else in this module (repositories, internal helpers) is NOT exported

// src/modules/billing/invoice-service.ts
// ✅ CORRECT — imports only the public interface
import { OrderService } from '@/modules/orders';

// ❌ WRONG — reaching into another module's internals
// import { OrderRepository } from "@/modules/orders/internal/order-repository";
```

Enforce this at the tooling level, not just by convention — ESLint's `import/no-restricted-paths`
or a dedicated tool like `dependency-cruiser` can fail the build if a module imports another
module's internals directly:

```javascript
// .dependency-cruiser.js
module.exports = {
  forbidden: [
    {
      name: 'no-cross-module-internals',
      severity: 'error',
      from: { path: '^src/modules/([^/]+)' },
      to: {
        path: '^src/modules/([^/]+)/(?!index)',
        pathNot: '^src/modules/$1', // allow importing your OWN module's internals
      },
    },
  ],
};
```

### Why Start Here

- Single deployment, single database transaction spanning multiple modules when genuinely
  needed (e.g., placing an order and decrementing inventory atomically) — no distributed
  transaction complexity
- Refactoring module boundaries is a code change, not a service migration project
- One CI/CD pipeline, one set of logs, one process to monitor — dramatically lower operational
  overhead for small-to-medium teams
- If module boundaries turn out wrong, they're cheap to fix; wrong microservice boundaries are
  expensive to fix (requires data migration, API versioning, coordinated deploys)

---

## Microservices

Multiple independently deployable services, each owning its own data store, communicating over
the network (REST, gRPC, or asynchronously via events — see `references/cqrs-event-driven.md`).

```
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│  Order Service  │      │ Inventory Service│      │ Billing Service │
│                │      │                │      │                │
│  own DB         │      │  own DB         │      │  own DB         │
│  own deploy     │      │  own deploy     │      │  own deploy     │
│  own team       │      │  own team       │      │  own team       │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │      REST / gRPC / events over the network     │
        └──────────────────────┼──────────────────────────┘
                                ▼
                      API Gateway / Service Mesh
```

### The Distributed Monolith Anti-Pattern

The single most common failure mode when adopting microservices too early: services are split
by deployment but remain tightly coupled at the logic and data level — synchronous call chains
several services deep, shared databases between "independent" services, or a deploy of Service
A requiring a coordinated deploy of Service B. This configuration has **all the operational
cost of microservices with none of the independence benefit**.

```
❌ DISTRIBUTED MONOLITH (the failure mode):

Order Service ──sync call──▶ Inventory Service ──sync call──▶ Pricing Service ──sync call──▶ Tax Service

One request to place an order now requires 4 services to all be up, all respond in time,
and none of them can deploy a breaking change independently — this is a monolith with
network calls between its function boundaries, and all the network calls have made it
SLOWER and LESS reliable than the monolith it replaced.
```

**Diagnostic questions to detect this in an existing system:**

- Can each service be deployed independently, on its own schedule, without coordinating with
  other teams? If not — distributed monolith.
- Does a single user-facing request require a deep synchronous chain across 4+ services? If
  so — reconsider whether those should be one service, or whether the chain should become
  asynchronous/event-driven.
- Do two "independent" services share a database or tables? If so, they are not actually
  independent — this is the most damaging version of the anti-pattern.

### When Microservices Genuinely Earn Their Cost

- **Team size and Conway's Law:** once an engineering org grows past roughly 8-10 engineers
  per domain area, a single monolith codebase becomes a coordination bottleneck — merge
  conflicts, deploy queues, unclear ownership. Splitting along the bounded contexts already
  identified via DDD (see `references/ddd.md`) gives each team true deployment independence.
- **Genuinely different scaling profiles:** a video transcoding service and a user profile
  service have wildly different resource needs (CPU-heavy batch vs. lightweight request/
  response) — splitting them allows independent, appropriately-sized infrastructure.
- **Independent technology needs:** a machine learning inference service justifiably wants
  Python; the main web app is TypeScript — microservices allow this without forcing one
  language across the whole system.
- **Regulatory/compliance isolation:** a payments processing component may need PCI-DSS scope
  isolation that's cleaner to achieve as a genuinely separate, network-isolated service.

### Migration Path — Monolith to Microservices (Strangler Fig)

Never attempt a full rewrite. Extract one bounded context at a time, behind a routing layer
that gradually shifts traffic from the monolith to the new service.

```
Step 1: Monolith handles everything, including Billing
┌──────────────────────────────────┐
│           Monolith                 │
│  Orders │ Inventory │  Billing      │
└──────────────────────────────────┘

Step 2: New Billing Service built alongside; router directs SOME traffic to it
┌──────────────────────────────────┐    ┌───────────────┐
│           Monolith                 │    │ Billing Service │
│  Orders │ Inventory │ [Billing]     │◀──▶│   (new)         │
└──────────────────────────────────┘    └───────────────┘
      Router gradually shifts 100% of Billing traffic to the new service

Step 3: Billing fully extracted; monolith's Billing module is deleted
┌──────────────────────────────────┐    ┌───────────────┐
│           Monolith                 │    │ Billing Service │
│      Orders │ Inventory           │───▶│                │
└──────────────────────────────────┘    └───────────────┘
```

This is the Strangler Fig pattern (Fowler) — the new service grows around the old
functionality until the old code path can be safely removed, with the ability to roll back to
the monolith path at any point during the transition if issues arise.

---

## Integration Patterns Between Services

### Synchronous — REST / gRPC

Use when the caller needs an immediate response to proceed (e.g., checking payment
authorization before confirming an order).

```typescript
// gRPC is preferred over REST for internal service-to-service calls:
// strongly-typed contracts (protobuf), lower latency, native streaming support
// REST remains preferred for public-facing / external APIs (see api-first-integration-nfrs.md)
```

**Resilience is mandatory for synchronous inter-service calls** — see the Circuit Breaker and
Retry patterns in `references/api-first-integration-nfrs.md` (NFR: Reliability section). A
synchronous call chain without these patterns turns one service's outage into a cascading
failure across every service that calls it.

### Asynchronous — Events

Use when the caller doesn't need to wait for the result, or when decoupling deploy/failure
domains matters more than immediate consistency. Full pattern and message broker comparison in
`references/cqrs-event-driven.md`.

### API Gateway

A single entry point that routes external requests to the appropriate internal service,
often also handling cross-cutting concerns (auth, rate limiting, request logging) so
individual services don't each reimplement them.

```
Client ──▶ API Gateway ──┬──▶ Order Service
                          ├──▶ Inventory Service
                          └──▶ Billing Service

Gateway handles: auth verification, rate limiting, request routing, response aggregation
```

### Backend for Frontend (BFF)

When multiple client types (web, mobile, third-party partners) need different shapes of the
same underlying data, a BFF is a thin service per client type that aggregates and reshapes
calls to the backend services — avoiding one generic API trying to serve every client's needs
awkwardly.

---

## When NOT to Use Microservices (Over-Engineering Check)

This is the most over-adopted pattern in modern software architecture — reached for based on
what large companies do publicly, not based on the requirements of the system actually being
built.

**Do not use microservices when:**

- The team is smaller than ~8-10 engineers — a modular monolith gives nearly all the code
  organization benefit without any of the distributed systems tax (network failures,
  distributed tracing, service discovery, data consistency across service boundaries)
- The domain boundaries are not yet well understood — splitting into services locks in
  boundaries that are expensive to change; get the boundaries right inside a monolith first
  (using DDD's bounded contexts), then extract services once boundaries have proven stable
- There's no genuine scaling asymmetry or team-coordination problem driving the decision —
  "microservices are the modern way to build software" is not a valid justification
- The team has no experience operating distributed systems (service discovery, distributed
  tracing, eventual consistency, network partition handling) — the learning curve is real and
  mistakes here cause production incidents, not just slower feature delivery

**Warning sign of over-application:** a team of 4 engineers running 15 microservices, each in
its own repo, each requiring its own CI/CD pipeline, its own on-call rotation understanding,
and its own database — for a product with modest traffic and a single, cohesive domain. This
consumes the majority of engineering time on operational overhead (deploying, monitoring,
debugging cross-service issues) rather than building features. The correct fix is almost
always consolidation back toward a modular monolith, not further splitting.

**The single best heuristic (Newman, paraphrased):** if you can't clearly articulate which
team owns which service and why that team needs independent deployment — you don't need
microservices yet. Start with a modular monolith with clean internal boundaries; those
boundaries are also exactly what you'll extract into services later, if and when the
organizational need genuinely arises.
