# API Protocols — REST, GraphQL, SOAP

**Sources:** Roy Fielding, _Architectural Styles and the Design of Network-based Software
Architectures_ (doctoral dissertation, UC Irvine, 2000) — the origin of REST; GraphQL
Foundation / graphql.org specification (Linux Foundation project since 2018); W3C SOAP
Version 1.2 Specification; Leonard Richardson's Maturity Model (popularized by Martin
Fowler); Google API Design Guide; Microsoft REST API Guidelines.

---

## 1. REST — Representational State Transfer

REST is an architectural style, not a protocol or a standard — there is no "REST RFC." Fielding
defined it as a set of constraints: client-server separation, statelessness, cacheability,
uniform interface, layered system, and (optionally) code-on-demand. Most APIs calling
themselves "RESTful" only partially satisfy these constraints — which is fine in practice, but
worth knowing when someone insists an API "isn't really REST."

### The Richardson Maturity Model

A practical way to assess how "RESTful" an API actually is:

```
Level 0: The Swamp of POX
  Single endpoint, single HTTP verb (usually POST), operation encoded in the body.
  Example: POST /api with { "action": "getUser", "id": 123 }
  This is RPC over HTTP — not REST by any meaningful definition.

Level 1: Resources
  Multiple endpoints, one per resource — but still using one HTTP verb (often just POST).
  Example: POST /users/123, POST /orders/456
  Progress: resources are addressable. Still not using HTTP semantics.

Level 2: HTTP Verbs
  Resources + proper use of GET/POST/PUT/PATCH/DELETE + correct status codes.
  Example: GET /users/123 → 200, POST /users → 201, DELETE /users/123 → 204
  This is what the vast majority of production "REST APIs" actually are — and it's
  a perfectly legitimate, production-appropriate level. Most APIs should target this level.

Level 3: HATEOAS (Hypermedia as the Engine of Application State)
  Responses include links describing available next actions.
  Example: { "id": 123, "_links": { "cancel": "/orders/123/cancel" } }
  Rarely implemented in practice — high design and client complexity cost for benefit that
  is only realized when clients are built generically to follow links rather than hardcode
  URLs. Fielding considers Level 3 the only "true" REST; the industry largely disagrees this
  is required for production usefulness.
```

**Practical guidance:** target Level 2. Level 3 is a legitimate academic ideal but rarely
justifies its cost outside specific domains (e.g., some hypermedia-driven admin tooling).

### Correct HTTP Semantics (the part most APIs get subtly wrong)

| Method   | Idempotent?                                                       | Safe? | Correct use                                              |
| -------- | ----------------------------------------------------------------- | ----- | -------------------------------------------------------- |
| `GET`    | Yes                                                               | Yes   | Retrieve a resource — never causes side effects          |
| `POST`   | **No**                                                            | No    | Create a resource, or a non-idempotent action            |
| `PUT`    | Yes                                                               | No    | Replace a resource entirely (full representation)        |
| `PATCH`  | **No** (by spec, though implementations often make it idempotent) | No    | Partial update                                           |
| `DELETE` | Yes                                                               | No    | Remove a resource — calling twice has the same end state |

**"Idempotent" means:** calling the operation N times has the same effect as calling it once.
This is not the same as "safe" (no side effects at all) — `DELETE` has a side effect but is
idempotent because deleting an already-deleted resource still results in "resource is gone."

**Common REST anti-patterns:**

```
❌ GET /deleteUser/123          — GET must never cause a side effect (breaks caching, prefetching, crawlers)
❌ POST /users/123/update       — verb in the URL; the HTTP method already conveys "update"
❌ 200 OK with { "error": "..." } in the body  — use the actual HTTP status code
❌ A single /api endpoint for everything  — Level 0, not REST
❌ Returning 500 for validation errors  — use 422 Unprocessable Entity (or 400)
```

**Correct resource naming (Google/Microsoft guidelines converge here):**

```
✅ GET    /users              — list
✅ GET    /users/123          — retrieve one
✅ POST   /users              — create
✅ PUT    /users/123          — full replace
✅ PATCH  /users/123          — partial update
✅ DELETE /users/123          — remove
✅ GET    /users/123/orders   — nested resource (orders belonging to user 123)
```

Plural nouns, no verbs in the path, nesting reflects genuine ownership (not just relation).

---

## 2. GraphQL

A query language and runtime for APIs, developed at Facebook (2012 internally, open-sourced
2015), now governed by the GraphQL Foundation under the Linux Foundation. The client specifies
exactly what data shape it needs in a single request; the server resolves it from one or more
underlying data sources.

### The Problem It Solves

```
REST — over-fetching / under-fetching:
  Mobile app needs { name, avatarUrl } for a user list.
  GET /users/123 returns the FULL user object — name, email, address, preferences, etc.
  Mobile app discards 90% of the payload. This is over-fetching.

  Web app needs { name, orders: [{ total, date }] } — a nested shape REST doesn't return
  in one call. Requires GET /users/123 + GET /users/123/orders — two round trips.
  This is under-fetching, requiring multiple requests to assemble one view.

GraphQL — client specifies the exact shape, server resolves it in one round trip:
```

```graphql
query {
  user(id: "123") {
    name
    avatarUrl
    orders {
      total
      date
    }
  }
}
```

Server returns exactly this shape — nothing more, nothing less, in a single request.

### Core Concepts

```graphql
# Schema Definition Language (SDL) — the contract, analogous to OpenAPI for REST
type User {
  id: ID!
  name: String!
  email: String!
  orders: [Order!]!
}

type Order {
  id: ID!
  total: Float!
  date: String!
}

type Query {
  user(id: ID!): User
  users(limit: Int = 20): [User!]!
}

type Mutation {
  createOrder(userId: ID!, items: [OrderItemInput!]!): Order!
}
```

```typescript
// Resolver implementation (Apollo Server / Node.js example)
const resolvers = {
  Query: {
    user: async (_parent, { id }, context) => {
      return context.dataSources.userAPI.getUser(id);
    },
  },
  User: {
    // Field-level resolver — runs only if the client actually requested `orders`
    orders: async (user, _args, context) => {
      return context.dataSources.orderAPI.getOrdersForUser(user.id);
    },
  },
};
```

**The N+1 problem (the most common GraphQL production bug):** if 20 users are returned and
each resolves its own `orders` field independently, that's 1 query for users + 20 queries for
orders = 21 database round trips. Solve with **DataLoader** (batches and caches requests
within a single tick):

```typescript
import DataLoader from "dataloader";

const orderLoader = new DataLoader(async (userIds: readonly string[]) => {
  // Single batched query for ALL requested user IDs, not one query per user
  const orders = await db.order.findMany({ where: { userId: { in: [...userIds] } } });
  return userIds.map((id) => orders.filter((o) => o.userId === id));
});

// In the resolver:
orders: (user) => orderLoader.load(user.id),  // batched automatically across the request
```

### When NOT to Use GraphQL

- **Single client, simple resource model** — REST is simpler to build, cache, and debug;
  GraphQL's flexibility solves a problem you don't have
- **Heavy caching requirements at the HTTP/CDN layer** — REST's GET requests cache naturally
  via HTTP semantics and CDNs; GraphQL typically uses POST for all operations, defeating
  standard HTTP caching (requires application-level caching like Apollo's normalized cache)
  or a persisted-query strategy to regain cacheability
- **File uploads** — GraphQL has no native multipart support; requires extensions or a
  separate REST endpoint for uploads
- **Small team, limited GraphQL experience** — the N+1 problem, resolver complexity, and
  schema design discipline have a real learning curve; a REST API built by a team new to
  GraphQL is often more reliable than a first GraphQL API from the same team
- **Public API for many third-party consumers with rate limiting needs** — query complexity
  varies wildly in GraphQL (a single query can be arbitrarily expensive), making rate limiting
  and abuse prevention significantly harder than REST's per-endpoint model

---

## 3. SOAP — Simple Object Access Protocol

SOAP (W3C standard, 2003) is frequently dismissed as "legacy," but it remains the **correct,
current, mandated** choice in specific domains — not a mistake to be modernized away casually.

### Where SOAP Is Still the Right Answer (Not Legacy Debt)

- **Financial services**: SWIFT messaging, many banking core systems, ISO 20022 in some
  legacy rails still use SOAP/XML-based interfaces
- **Healthcare**: HL7 v2/v3 interfaces in many hospital systems, insurance claim processing
- **Government/enterprise legacy**: many government API mandates and enterprise ERPs
  (SAP, older Oracle systems) expose SOAP as the primary or only integration option
- **When you need built-in transactionality**: WS-AtomicTransaction and related WS-\*
  standards provide formal distributed transaction support that REST/GraphQL don't offer
  natively — relevant in some enterprise integration scenarios

**For RPA and integration work specifically:** SOAP is common when integrating with legacy
ERPs, banking systems, or government portals. Treat it as a routine integration requirement,
not a red flag.

### Structure

```xml
<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Header>
    <!-- Auth tokens, transaction IDs, routing info -->
  </soap:Header>
  <soap:Body>
    <GetUserRequest xmlns="http://example.com/users">
      <UserId>123</UserId>
    </GetUserRequest>
  </soap:Body>
</soap:Envelope>
```

The contract is formally described by a **WSDL** (Web Services Description Language) document
— machine-readable, enabling strict client code generation, which is precisely why enterprise
systems favor it: the contract is unambiguous and tooling-enforced in a way that hand-maintained
OpenAPI specs sometimes aren't.

```python
# Python — zeep is the standard modern SOAP client library
from zeep import Client

client = Client("https://example.com/service?wsdl")
response = client.service.GetUser(UserId=123)
print(response.Name, response.Email)
```

```typescript
// Node.js — soap package
import * as soap from 'soap';

const client = await soap.createClientAsync('https://example.com/service?wsdl');
const [result] = await client.GetUserAsync({ UserId: 123 });
```

### When NOT to Use SOAP (Building New)

- Building a brand-new API with no legacy constraint — REST or GraphQL will always be simpler
  to build, document, test, and onboard new developers to
- No requirement for WS-\* enterprise features (formal transactions, WS-Security) — the extra
  complexity (XML parsing, WSDL, envelope overhead) buys nothing
- The consuming clients are primarily web/mobile — SOAP's XML verbosity and tooling are a poor
  fit for browser-based and mobile consumption compared to JSON-based REST/GraphQL
