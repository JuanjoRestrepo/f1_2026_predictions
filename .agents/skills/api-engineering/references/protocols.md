# API Protocols — REST, GraphQL, SOAP

**Sources:** Roy Fielding, _Architectural Styles and the Design of Network-based Software
Architectures_ (doctoral dissertation, UC Irvine, 2000); GraphQL Foundation / graphql.org
specification (Linux Foundation project since 2018); W3C SOAP Version 1.2 Specification;
Leonard Richardson's Maturity Model (Martin Fowler, 2010); IETF RFC 9457 _Problem Details for
HTTP APIs_ (July 2023, obsoletes RFC 7807 — M. Nottingham/Akamai); RFC 8288 (Web Linking,
for pagination Link headers); Relay Cursor Connections Specification (GraphQL Foundation);
Google API Design Guide; Microsoft REST API Guidelines; Stripe API Reference (pagination and
error format reference implementations).

---

## 1. REST — Representational State Transfer

REST is an architectural style, not a protocol or standard — there is no "REST RFC." Fielding
defined it as a set of constraints: client-server separation, statelessness, cacheability,
uniform interface, layered system, and (optionally) code-on-demand. Most APIs calling
themselves "RESTful" only partially satisfy these constraints — which is fine in practice, but
worth knowing when someone insists an API "isn't really REST."

### 1.1 The Richardson Maturity Model

```
Level 0: The Swamp of POX
  Single endpoint, single verb (usually POST), operation encoded in the body.
  Example: POST /api with { "action": "getUser", "id": 123 }
  This is RPC over HTTP — not REST by any meaningful definition.

Level 1: Resources
  Multiple endpoints, one per resource — but still one HTTP verb (often POST).
  Example: POST /users/123, POST /orders/456

Level 2: HTTP Verbs
  Resources + proper GET/POST/PUT/PATCH/DELETE + correct status codes.
  This is what the vast majority of production "REST APIs" actually are,
  and it's a perfectly legitimate, production-appropriate target.

Level 3: HATEOAS (Hypermedia as the Engine of Application State)
  Responses include links describing available next actions.
  Example: { "id": 123, "_links": { "cancel": "/orders/123/cancel" } }
  Rarely justified in practice — high design and client complexity for benefit
  that only materialises when clients follow links generically.
```

**Practical guidance:** target Level 2. Level 3 is a legitimate academic ideal but rarely
justifies its cost outside specific hypermedia-driven domains.

### 1.2 HTTP Verb Semantics (the part most APIs get subtly wrong)

| Method   | Idempotent?                                                       | Safe? | Correct use                                       |
| -------- | ----------------------------------------------------------------- | ----- | ------------------------------------------------- |
| `GET`    | Yes                                                               | Yes   | Retrieve — never causes side effects              |
| `POST`   | **No**                                                            | No    | Create a resource, or a non-idempotent action     |
| `PUT`    | Yes                                                               | No    | Replace a resource entirely (full representation) |
| `PATCH`  | **No** (by spec, though implementations often make it idempotent) | No    | Partial update                                    |
| `DELETE` | Yes                                                               | No    | Remove — calling twice has the same end state     |

**"Idempotent"** means calling N times has the same effect as calling once. `DELETE` has a
side effect but is idempotent because deleting an already-deleted resource still results in
"resource is gone."

**Common REST anti-patterns:**
```
❌ GET /deleteUser/123          — GET must never cause a side effect
❌ POST /users/123/update       — verb in the URL; the HTTP method already conveys this
❌ 200 OK with { "error": "..." } in the body  — use the actual HTTP status code
❌ A single /api endpoint for everything  — Level 0, not REST
❌ Returning 500 for validation errors  — use 422 Unprocessable Entity
```

**Correct resource naming:**

```
✅ GET    /users              — list
✅ GET    /users/123          — retrieve one
✅ POST   /users              — create
✅ PUT    /users/123          — full replace
✅ PATCH  /users/123          — partial update
✅ DELETE /users/123          — remove
✅ GET    /users/123/orders   — nested resource (orders belonging to user 123)
```

Plural nouns, no verbs in the path, nesting reflects genuine ownership.

### 1.3 HTTP Status Codes — Selection Guide

Status code selection is one of the most-violated REST practices. The wrong status code forces
clients to parse bodies to understand what happened.

| Code  | Name                  | When to use                                                                        |
| ----- | --------------------- | ---------------------------------------------------------------------------------- |
| `200` | OK                    | Successful GET, PUT, PATCH; also DELETE when the response includes a body          |
| `201` | Created               | Successful POST that created a resource; include `Location: /resources/123` header |
| `202` | Accepted              | Request queued for async processing — not yet complete                             |
| `204` | No Content            | Successful DELETE, or PUT/PATCH with no body to return                             |
| `301` | Moved Permanently     | Resource URL changed permanently — update your bookmarks                           |
| `304` | Not Modified          | Conditional GET matched ETag/Last-Modified — body omitted (use cached copy)        |
| `400` | Bad Request           | Malformed request syntax, invalid JSON, missing required fields                    |
| `401` | Unauthorized          | Not authenticated — credentials missing or invalid                                 |
| `403` | Forbidden             | Authenticated, but not authorized for this resource                                |
| `404` | Not Found             | Resource does not exist                                                            |
| `409` | Conflict              | State conflict — e.g., duplicate unique key, concurrent modification               |
| `410` | Gone                  | Resource permanently deleted — stronger signal than 404                            |
| `422` | Unprocessable Entity  | Syntactically valid request, but semantically wrong (validation failure)           |
| `429` | Too Many Requests     | Rate limit exceeded; include `Retry-After` header                                  |
| `500` | Internal Server Error | Unexpected server-side error — never expose stack traces                           |
| `503` | Service Unavailable   | Temporarily unavailable (maintenance, overload); include `Retry-After`             |

**The 401 vs 403 distinction** is consistently confused:

- `401` = "Who are you? Prove your identity first."
- `403` = "I know who you are, but you can't access this."

**The 400 vs 422 distinction** per RFC 9110:

- `400` = the request is syntactically malformed (unparseable JSON, missing required field
  entirely) — the server couldn't even understand the intent
- `422` = the request is syntactically valid but the semantic content is wrong (email
  format invalid, date in the past, amount negative) — the server understood the intent but
  cannot process it

### 1.4 Error Response Format — RFC 9457 Problem Details (Current Standard)

RFC 9457 (July 2023, IETF Standards Track) defines a standard machine-readable error response
format for HTTP APIs. It obsoletes RFC 7807 (2016) — RFC 9457 is the current version.
Backward-compatible: existing RFC 7807 responses remain valid. RFC 9457 adds an IANA problem
type registry, an `errors` array for multiple problems, and clearer guidance on type URIs.

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation Failed",
  "status": 422,
  "detail": "The request body contains invalid fields.",
  "instance": "/orders/create",
  "errors": [
    { "field": "email", "message": "Invalid email format" },
    { "field": "amount", "message": "Must be greater than zero" }
  ]
}
```

**The five standard members:**

- `type` — a URI identifying the problem type (dereferenceable to documentation, or abstract)
- `title` — a short, human-readable summary of the type (same for all instances of this type)
- `status` — the HTTP status code (should match the actual response code)
- `detail` — a human-readable explanation of this specific occurrence
- `instance` — a URI identifying the specific occurrence (useful for correlation/logging)

`errors` is an extension array (RFC 9457 §3.1) for reporting multiple problems at once —
especially valuable for validation errors where every field that failed should be reported
rather than stopping at the first error.

```typescript
// TypeScript — RFC 9457-compliant error response helper
function problemDetail(
  status: number,
  type: string,
  title: string,
  detail: string,
  extensions?: Record<string, unknown>,
): object {
  return { type, title, status, detail, ...extensions };
}

// Express error handler using RFC 9457
app.use((err: AppError, req: Request, res: Response, _next: NextFunction) => {
  res
    .status(err.statusCode)
    .json(
      problemDetail(
        err.statusCode,
        `https://api.example.com/problems/${err.code}`,
        err.title,
        err.detail,
        err.extensions,
      ),
    );
});
```

```python
# FastAPI — RFC 9457 helper
from fastapi.responses import JSONResponse

def problem_detail(
    status: int,
    type_uri: str,
    title: str,
    detail: str,
    **extensions,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": type_uri, "title": title, "status": status, "detail": detail, **extensions},
        media_type="application/problem+json",
    )

# Usage in an exception handler:
@app.exception_handler(ValidationError)
async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return problem_detail(
        status=422,
        type_uri="https://api.example.com/problems/validation-failed",
        title="Validation Failed",
        detail="One or more fields did not pass validation.",
        errors=[{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()],
    )
```

### 1.5 Filtering, Sorting, and Pagination

#### Standard Query Parameters (Google/Stripe/GitHub conventions)

```
GET /orders?status=shipped&created_after=2026-01-01   — filtering
GET /users?sort=created_at&order=desc                  — sorting
GET /orders?limit=20&starting_after=ord_xyz123         — cursor pagination (Stripe style)
GET /users?per_page=30&page=2                          — offset pagination (simpler, has trade-offs)
GET /orders?fields=id,status,total                     — sparse fieldsets (reduces payload)
```

#### Pagination Patterns — The Critical Trade-offs

**Offset/Limit (simple, common, not recommended for large datasets):**

```
GET /users?limit=10&offset=30

SELECT * FROM users ORDER BY created_at DESC LIMIT 10 OFFSET 30;
```

Problems:

- **Performance degrades exponentially** at large offsets — the DB scans and discards all
  offset rows on every request. `OFFSET 1000000` reads a million rows to return ten.
- **Data drift** — if a record is inserted on page 1 while a client is on page 3, all
  subsequent pages shift. The client will either see a record twice or miss one entirely.

**Cursor-based (Stripe, GitHub, Twitter, Shopify — the production-ready default):**

Cursor-based pagination anchors the next request to a specific record, not a numerical
position. Stripe's implementation uses `starting_after` and `ending_before` with the record's
ID. GitHub uses opaque base64 cursors. Both avoid OFFSET entirely.

```
GET /orders?limit=20&starting_after=ord_xyz123

SQL equivalent (keyset pagination):
SELECT * FROM orders WHERE id > 'ord_xyz123' ORDER BY id ASC LIMIT 20;
```

```typescript
// TypeScript — cursor pagination implementation
interface CursorPage<T> {
  data: T[];
  has_more: boolean;
  next_cursor: string | null;
}

async function getOrdersPage(
  limit: number,
  startingAfter?: string,
): Promise<CursorPage<Order>> {
  const orders = await db.order.findMany({
    take: limit + 1, // fetch one extra to detect has_more
    where: startingAfter ? { id: { gt: startingAfter } } : undefined,
    orderBy: { id: 'asc' },
  });

  const hasMore = orders.length > limit;
  const data = hasMore ? orders.slice(0, limit) : orders;

  return {
    data,
    has_more: hasMore,
    next_cursor: hasMore ? data[data.length - 1].id : null,
  };
}
```

```python
# Python — cursor pagination with FastAPI + SQLAlchemy
@router.get("/orders")
async def list_orders(
    limit: int = Query(default=20, le=100),
    starting_after: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> OrdersPage:
    query = select(Order).order_by(Order.id.asc()).limit(limit + 1)
    if starting_after:
        query = query.where(Order.id > starting_after)

    result = await db.execute(query)
    orders = result.scalars().all()

    has_more = len(orders) > limit
    data = orders[:limit]

    return OrdersPage(
        data=data,
        has_more=has_more,
        next_cursor=data[-1].id if has_more else None,
    )
```

**Pagination Link header (RFC 8288 — GitHub's approach):**

```http
GET /users?per_page=30&page=2

Link: <https://api.example.com/users?page=3>; rel="next",
      <https://api.example.com/users?page=1>; rel="prev",
      <https://api.example.com/users?page=10>; rel="last"
```

RFC 8288 defines standard `rel` values: `next`, `prev`, `first`, `last`. Clients that parse
Link headers can paginate without hardcoding URL construction logic.

**When to use which:**

| Scenario                                    | Recommendation                                         |
| ------------------------------------------- | ------------------------------------------------------ |
| New API, medium-to-large dataset            | Cursor-based (opaque token, Stripe-style)              |
| Small dataset, rarely exceeds 1000 rows     | Offset is fine — simplicity wins                       |
| Need "jump to page N" UX                    | Offset is the only option — cursor can't random-access |
| Real-time or frequently-updated collections | Cursor mandatory — offset causes drift                 |
| GraphQL API                                 | Relay Cursor Connections Spec — see Section 2.5        |

### 1.6 HTTP Caching (a Core REST Constraint — frequently ignored)

Cacheability is one of Fielding's six REST constraints — not a bonus feature. REST APIs that
bypass HTTP caching mechanisms miss a significant scalability lever.

**Two caching mechanisms:**

**`ETag` (Entity Tag) — content-based validation:**

```http
GET /orders/123 HTTP/1.1

HTTP/1.1 200 OK
ETag: "v1_abc123"
Cache-Control: max-age=60

--- Second request, after cache expires ---
GET /orders/123 HTTP/1.1
If-None-Match: "v1_abc123"

HTTP/1.1 304 Not Modified   ← no body; client uses cached copy
```

**`Last-Modified` — time-based validation:**

```http
HTTP/1.1 200 OK
Last-Modified: Mon, 19 May 2026 10:00:00 GMT

--- Subsequent request ---
GET /orders/123 HTTP/1.1
If-Modified-Since: Mon, 19 May 2026 10:00:00 GMT

HTTP/1.1 304 Not Modified
```

**`Cache-Control` directives:**

| Directive         | Meaning                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| `max-age=N`       | Cache is fresh for N seconds                                                           |
| `no-cache`        | Must revalidate with server before using cached copy (ETag/Last-Modified still useful) |
| `no-store`        | Never cache — for sensitive, personalized data                                         |
| `private`         | Browser may cache, shared caches (CDN, proxy) must not                                 |
| `public`          | Shared caches may cache                                                                |
| `must-revalidate` | Expired cache must revalidate — don't serve stale content                              |

```typescript
// Express — setting cache headers
router.get('/products/:id', async (req, res) => {
  const product = await productService.findById(req.params.id);
  const etag = `"${product.updatedAt.getTime()}"`; // or a content hash

  if (req.headers['if-none-match'] === etag) {
    return res.status(304).send(); // client's cached copy is still valid
  }

  res.setHeader('ETag', etag);
  res.setHeader('Cache-Control', 'private, max-age=60');
  res.json(product);
});
```

```python
# FastAPI — ETag validation
from fastapi import Response

@router.get("/products/{product_id}")
async def get_product(product_id: str, request: Request, response: Response) -> Product:
    product = await product_service.get(product_id)
    etag = f'"{hash(product.updated_at)}"'

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=60"
    return product
```

**What NOT to cache:** personalized data, auth endpoints, anything with financial side effects.
These must include `Cache-Control: no-store`.

---

## 2. GraphQL

A query language and runtime for APIs, developed at Facebook (2012 internally, open-sourced
2015), now governed by the GraphQL Foundation under the Linux Foundation. The client specifies
exactly what data shape it needs in a single request; the server resolves it from one or more
underlying data sources.

### 2.1 The Problem It Solves

```
REST — over-fetching and under-fetching:

  Mobile app needs { name, avatarUrl } for a user list.
  GET /users/123 returns the full user object — name, email, address, preferences, etc.
  Mobile app discards 90% of the payload. This is over-fetching.

  Web dashboard needs { name, orders: [{ total, date }] }.
  REST requires GET /users/123 + GET /users/123/orders — two round trips.
  This is under-fetching.

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

Server returns exactly this shape — nothing more, in a single request.

### 2.2 Schema — Queries, Mutations, Subscriptions

```graphql
# Schema Definition Language (SDL) — the contract, analogous to OpenAPI for REST

type User {
  id: ID!
  name: String!
  email: String!
  orders(limit: Int = 20, after: String): OrderConnection!
}

type Order {
  id: ID!
  total: Float!
  status: OrderStatus!
  createdAt: String!
}

enum OrderStatus { PENDING CONFIRMED SHIPPED CANCELLED }

# Relay Cursor Connection — the standard pagination shape for GraphQL (see 2.5)
type OrderConnection {
  edges: [OrderEdge!]!
  pageInfo: PageInfo!
}
type OrderEdge { node: Order!; cursor: String! }
type PageInfo { hasNextPage: Boolean!; endCursor: String }

# Queries — read operations (analogous to GET in REST)
type Query {
  user(id: ID!): User
  users(limit: Int = 20, after: String): UserConnection!
}

# Mutations — write operations (analogous to POST/PUT/PATCH/DELETE in REST)
type Mutation {
  createOrder(input: CreateOrderInput!): CreateOrderPayload!
  cancelOrder(orderId: ID!): CancelOrderPayload!
}

# Subscriptions — real-time push (analogous to WebSocket)
type Subscription {
  orderStatusChanged(orderId: ID!): Order!
}

input CreateOrderInput {
  userId: ID!
  items: [OrderItemInput!]!
}

type CreateOrderPayload {
  order: Order
  errors: [UserError!]!   # mutations return errors in the payload, not as HTTP errors
}

type UserError {
  field: [String!]!
  message: String!
}
```

### 2.3 Resolvers — TypeScript Implementation

```typescript
// Apollo Server 4 implementation
import { ApolloServer } from '@apollo/server';
import { startStandaloneServer } from '@apollo/server/standalone';
import DataLoader from 'dataloader';

const resolvers = {
  Query: {
    user: async (
      _parent: unknown,
      { id }: { id: string },
      context: Context,
    ) => {
      return context.loaders.user.load(id); // DataLoader-batched
    },
    users: async (
      _parent: unknown,
      { limit, after }: Args,
      context: Context,
    ) => {
      return userService.listPaginated({ limit, after });
    },
  },

  User: {
    // Field resolver — runs ONLY if the client requested the `orders` field
    // Without DataLoader: 1 user list + N order queries = N+1 problem
    orders: async (user: User, { limit, after }: Args, context: Context) => {
      return context.loaders.ordersByUser.load({
        userId: user.id,
        limit,
        after,
      });
    },
  },

  Mutation: {
    createOrder: async (
      _parent: unknown,
      { input }: { input: CreateOrderInput },
      context: Context,
    ) => {
      try {
        const order = await orderService.create(input);
        return { order, errors: [] };
      } catch (err) {
        if (err instanceof ValidationError) {
          // Mutation errors go in the payload, not as GraphQL errors — client can handle gracefully
          return { order: null, errors: err.fieldErrors };
        }
        throw err; // unexpected errors become GraphQL errors → HTTP 200 with errors array
      }
    },
  },
};

// DataLoader — solves the N+1 problem by batching within a single tick
function createLoaders() {
  return {
    user: new DataLoader(async (ids: readonly string[]) => {
      const users = await db.user.findMany({ where: { id: { in: [...ids] } } });
      return ids.map((id) => users.find((u) => u.id === id) ?? null);
    }),
    ordersByUser: new DataLoader(
      async (keys: readonly { userId: string; limit: number }[]) => {
        const userIds = [...new Set(keys.map((k) => k.userId))];
        const orders = await db.order.findMany({
          where: { userId: { in: userIds } },
        });
        return keys.map((k) =>
          orders.filter((o) => o.userId === k.userId).slice(0, k.limit),
        );
      },
    ),
  };
}
```

### 2.4 Subscriptions — Real-Time over WebSocket

GraphQL subscriptions send data to clients when events occur. The transport protocol is not
specified by the GraphQL spec — `graphql-ws` (using the `graphql-transport-ws` subprotocol)
is the current community standard, replacing the deprecated `subscriptions-transport-ws`.

```graphql
subscription {
  orderStatusChanged(orderId: "order-123") {
    id
    status
    updatedAt
  }
}
```

```typescript
// Apollo Server 4 with graphql-ws for subscription transport
import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { useServer } from 'graphql-ws/lib/use/ws';
import { makeExecutableSchema } from '@graphql-tools/schema';
import { PubSub } from 'graphql-subscriptions';

const pubsub = new PubSub();

const resolvers = {
  Subscription: {
    orderStatusChanged: {
      subscribe: (_parent, { orderId }, context) => {
        // Authorization for subscriptions — same discipline as mutations
        if (!context.user) throw new Error('Unauthorized');
        return pubsub.asyncIterableIterator(`ORDER_STATUS_CHANGED:${orderId}`);
      },
      resolve: (payload) => payload.order,
    },
  },
};

const schema = makeExecutableSchema({ typeDefs, resolvers });
const httpServer = createServer(app);
const wsServer = new WebSocketServer({ server: httpServer, path: '/graphql' });

useServer(
  {
    schema,
    context: async (ctx) => ({
      user: await verifyToken(ctx.connectionParams?.token),
    }),
  },
  wsServer,
);

// Publishing an event (from your mutation or domain event):
await pubsub.publish(`ORDER_STATUS_CHANGED:${order.id}`, { order });
```

**For production at scale:** `graphql-subscriptions` PubSub is in-memory — it doesn't work
across multiple server instances. Use `graphql-redis-subscriptions` for Redis-backed pub/sub,
or `graphql-subscriptions` with a Kafka adapter for high-throughput event streams.

**SSE as an alternative transport:** WunderGraph and others have documented that for most
GraphQL subscription use cases, SSE over HTTP/2 is simpler (no WebSocket upgrade complexity,
multiplexing, works through HTTP/2 proxies) and should be preferred when bidirectional
communication from the client isn't needed. The `graphql-sse` library implements this.

### 2.5 Relay Cursor Connections — Pagination Standard for GraphQL

The GraphQL Foundation's Relay Cursor Connections Specification defines a standard pagination
shape. Adopted by GitHub's GraphQL API v4, Shopify, and most large-scale GraphQL APIs. The
spec defines `edges`, `node`, `cursor`, and `pageInfo` with `hasNextPage`/`endCursor`.

```graphql
# Standard query using the Connections spec:
query {
  users(first: 20, after: "cursor-from-previous-response") {
    edges {
      node {
        id
        name
        email
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

This is cursor-based pagination at the GraphQL layer — same database-efficiency benefits as
REST cursor pagination (Section 1.5), with a standardized, tooling-compatible shape.

### 2.6 Security — Query Depth, Complexity, and Persisted Queries

**The abuse surface of GraphQL:** a REST API has a fixed URL surface (each endpoint is a
known cost); a GraphQL API has an infinite query surface (a client can construct an
arbitrarily deep, arbitrarily expensive query in a single request).

**Depth limiting — prevent deeply nested queries:**

```typescript
import depthLimit from 'graphql-depth-limit'; // npm: graphql-depth-limit

const server = new ApolloServer({
  schema,
  validationRules: [
    depthLimit(7), // reject queries nested deeper than 7 levels
  ],
});
```

**Complexity limiting — assign cost to fields, reject over-budget queries:**

```typescript
import { createComplexityLimitRule } from 'graphql-validation-complexity';

const server = new ApolloServer({
  schema,
  validationRules: [
    createComplexityLimitRule(1000, {
      // Each field costs 1 by default; list fields cost more
      listFactor: 10,
      scalarCost: 1,
      objectCost: 1,
    }),
  ],
});
```

**Persisted queries — restore HTTP caching and prevent arbitrary queries in production:**

A persisted query replaces the full query text with a hash. The client sends only the hash;
the server looks up the full query. This restores GET caching (hash goes in the URL) and
acts as an implicit allowlist — only registered queries can execute.

```typescript
// Apollo Server with persisted queries (Automatic Persisted Queries — APQ)
import { ApolloServerPluginCacheControl } from '@apollo/server/plugin/cacheControl';
import { KeyValueCache } from '@apollo/utils.keyvaluecache';

// Client sends: { "extensions": { "persistedQuery": { "version": 1, "sha256Hash": "abc..." } } }
// If the server doesn't have it: 404 → client sends the full query → server caches it by hash
// Subsequent requests from any client: only the hash needed
```

For internal or closed APIs, a stricter allowlist (only pre-registered queries can execute,
no arbitrary query strings from clients) is more secure than APQ's "cache on first use."

### 2.7 When NOT to Use GraphQL

- **Single client, simple resource model** — REST is simpler to build, cache, and debug;
  GraphQL's flexibility solves a problem you don't have
- **Heavy CDN/HTTP caching requirements** — REST's GET requests cache naturally at the
  network layer; GraphQL POST requests do not without persisted queries + GET transport
- **File uploads** — GraphQL has no native multipart support; use a separate REST endpoint
- **Small team, limited GraphQL experience** — N+1, resolver complexity, and schema design
  discipline have a real learning curve; a well-structured REST API is often more reliable
  from a team new to GraphQL than a first GraphQL implementation
- **Public third-party API with strict rate limiting** — query cost varies wildly (a single
  query can be arbitrarily expensive); per-endpoint rate limiting is much harder

---

## 3. SOAP — Simple Object Access Protocol

SOAP (W3C standard, 2003) is frequently dismissed as "legacy," but it remains the **correct,
current, mandated** choice in specific domains — not a mistake to modernize casually.

### When SOAP Is the Right Answer

- **Financial services**: SWIFT messaging, banking core systems, ISO 20022 in some rails
- **Healthcare**: HL7 v2/v3 interfaces in hospital systems, insurance claim processing
- **Government/enterprise legacy**: many government API mandates and ERPs (SAP, older Oracle)
  expose SOAP as the primary or only integration option
- **Built-in transactionality**: WS-AtomicTransaction provides formal distributed transaction
  support REST/GraphQL don't offer natively

**For RPA and integration work:** SOAP is common when integrating with legacy ERPs, banking
systems, and government portals. Treat it as a routine requirement, not a red flag.

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
— machine-readable, enabling strict client code generation. This is precisely why enterprise
systems favor it: the contract is unambiguous and tooling-enforced.

```python
from zeep import Client  # pip / uv add zeep
client = Client("https://example.com/service?wsdl")
response = client.service.GetUser(UserId=123)
```

```typescript
import * as soap from 'soap';
const client = await soap.createClientAsync('https://example.com/service?wsdl');
const [result] = await client.GetUserAsync({ UserId: 123 });
```

### When NOT to Use SOAP (Building New)

- Building a new API with no legacy constraint — REST or GraphQL will always be simpler to
  build, document, test, and onboard new developers to
- No requirement for WS-\* features (formal distributed transactions, WS-Security)
- Consuming clients are primarily web/mobile — SOAP's XML verbosity is a poor fit

---

## 4. REST vs GraphQL — Direct Comparison

| Criterion              | REST                                             | GraphQL                                                   |
| ---------------------- | ------------------------------------------------ | --------------------------------------------------------- |
| **Data fetching**      | Fixed shape per endpoint (over/under-fetch risk) | Client-specified shape (no over/under-fetch)              |
| **Multiple resources** | Multiple round trips                             | Single round trip (one query, multiple types)             |
| **HTTP caching**       | Native — GET is cacheable at CDN/proxy level     | Requires persisted queries + GET transport                |
| **Learning curve**     | Low — standard HTTP semantics                    | Moderate — SDL, resolvers, DataLoader, N+1                |
| **Type safety**        | Via OpenAPI code generation                      | Native — schema is the source of truth                    |
| **File uploads**       | Native multipart                                 | Requires extension or separate endpoint                   |
| **Rate limiting**      | Per-endpoint (predictable cost)                  | Per-query complexity (variable cost)                      |
| **Real-time**          | Polling / SSE / WebSocket separately             | Subscriptions over WebSocket/SSE built-in                 |
| **Tooling maturity**   | Excellent — 25+ years of HTTP tooling            | Good — growing ecosystem                                  |
| **Error handling**     | HTTP status codes + RFC 9457 Problem Details     | HTTP 200 always; errors in response body                  |
| **Browser caching**    | Native (ETag, Cache-Control, 304)                | Application-layer only                                    |
| **Public API**         | Easier to rate-limit and document                | Harder to rate-limit; needs complexity limits             |
| **Best for**           | Simple resources, public APIs, CDN-heavy         | Many clients, heterogeneous views, internal platform APIs |

### Real-World Protocol Choices at Scale

| Company                | Choice                                | Why                                                                                                                                                    |
| ---------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Stripe**             | REST                                  | Public API with thousands of integrators; predictable per-endpoint rate limiting; cursor pagination; strong cacheability                               |
| **GitHub**             | REST (v3) + GraphQL (v4)              | Both maintained; REST for simple integrations, GraphQL for complex data (pull request + review + CI + labels in one query)                             |
| **Shopify**            | GraphQL primary                       | Multiple heterogeneous clients (mobile, web, storefront, admin); one graph serves all                                                                  |
| **Twitter / X**        | REST                                  | Went back to REST for v2 after v1's inconsistencies — simpler to rate-limit and scale                                                                  |
| **Amazon Prime Video** | Consolidated microservices → monolith | The switching-away-from-microservices case study that went viral; nothing to do with REST vs GraphQL, but frequently cited in architecture discussions |
| **Facebook**           | GraphQL (inventor)                    | Multiple clients (mobile/web/VR) with radically different data needs; the problem GraphQL was built to solve                                           |

**The most important factor in the REST vs GraphQL decision:** how many heterogeneous clients
need different views of your data. One client → REST is almost certainly correct. Multiple
clients with different data shapes → GraphQL's flexibility earns its complexity.
