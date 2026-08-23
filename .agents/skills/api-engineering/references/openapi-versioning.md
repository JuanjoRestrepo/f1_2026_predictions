# OpenAPI & API Versioning

**Sources:** OpenAPI Initiative (Linux Foundation), OpenAPI Specification v3.1.0 (aligned with
JSON Schema 2020-12); Stripe API versioning documentation (industry-recognized reference
implementation); Microsoft REST API Guidelines; Google API Design Guide (AIP — API Improvement
Proposals).

---

## 1. OpenAPI 3.1 — The Contract

OpenAPI (formerly "Swagger") is the de facto standard for describing REST APIs in a
machine-readable format. Version 3.1 (2021) aligned fully with JSON Schema, closing a long
standing mismatch between OpenAPI's schema dialect and standard JSON Schema.

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.4.0
  description: Manages customer orders
servers:
  - url: https://api.example.com/v1
paths:
  /orders/{orderId}:
    get:
      summary: Retrieve an order
      operationId: getOrder
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          description: Order not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
components:
  schemas:
    Order:
      type: object
      required: [id, status, total]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [pending, confirmed, shipped, cancelled]
        total:
          type: number
          format: decimal
    Error:
      type: object
      properties:
        error:
          type: string
        requestId:
          type: string
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
```

### Generating Code From the Spec (the real payoff of API-First)

```bash
# Generate a TypeScript client from the spec
npx openapi-typescript openapi.yaml -o src/types/api.d.ts

# Generate a FastAPI server stub from the spec
pip install datamodel-code-generator
datamodel-codegen --input openapi.yaml --output models.py

# Validate a spec for correctness
npx @redocly/cli lint openapi.yaml

# Generate interactive docs
npx @redocly/cli build-docs openapi.yaml -o docs.html
```

**FastAPI generates OpenAPI automatically** from your Pydantic models and route decorators
(covered in `web-devops/references/python-api.md`) — for FastAPI projects, the spec is a
byproduct of well-typed code rather than a hand-authored artifact. For non-Python/non-FastAPI
projects, or when the contract must be agreed before any code exists (true API-First), author
the YAML directly or with a design tool (Stoplight, Postman).

---

## 2. API Versioning Strategies

Every API that will be consumed by more than one client (internal or external) will eventually
need to make a breaking change. Versioning is how you make that change without breaking
existing consumers overnight.

### What Counts as a Breaking Change

```
BREAKING (requires a new version):
- Removing a field from a response
- Renaming a field
- Changing a field's type (string → number)
- Adding a new required field to a request
- Removing an endpoint
- Changing authentication requirements

NON-BREAKING (safe within the same version):
- Adding a new optional field to a response
- Adding a new endpoint
- Adding a new optional request parameter
- Adding a new enum value (if clients are expected to handle unknown values gracefully —
  document this expectation explicitly)
```

### Strategy Comparison

| Strategy                                 | Example                                   | Pros                                                                                                                                   | Cons                                                                                                                             |
| ---------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **URI versioning**                       | `/v1/orders`, `/v2/orders`                | Simple, visible, cacheable per version                                                                                                 | URL "pollution"; encourages big-bang version jumps                                                                               |
| **Header versioning**                    | `Api-Version: 2`                          | Clean URLs; version is metadata, not identity                                                                                          | Less discoverable; harder to test in a browser                                                                                   |
| **Media-type versioning**                | `Accept: application/vnd.example.v2+json` | RESTfully "correct" (version is a representation detail)                                                                               | Most complex to implement and document; low adoption outside specific communities                                                |
| **Date-based versioning (Stripe model)** | `Stripe-Version: 2024-06-20`              | Extremely granular — each account pins to the exact date it integrated; enables per-field migrations, not just per-major-version jumps | Requires significant internal tooling to maintain many concurrent "versions" as transformations over one internal representation |

**Practical recommendation:** URI versioning (`/v1/`, `/v2/`) for most APIs — simplest to
reason about, document, and route. Reserve date-based versioning for APIs with a large,
long-lived integration surface where Stripe-style granularity pays for its complexity (mature
platforms with thousands of integrators, not early-stage APIs).

### Stripe's Date-Based Model (Reference Implementation)

Stripe's approach is worth understanding even if you don't adopt it directly, because it
solves the "N major versions to maintain forever" problem elegantly:

```
Internal representation: always the latest, single source of truth.
Each API account pins to a specific version date (e.g., "2024-06-20") at signup.
Every field-level breaking change gets a version "changeset."
Incoming/outgoing data for an older-pinned account is transformed through the chain of
changesets between their pinned date and the current internal representation — at the
edge, not by maintaining N parallel codebases.
```

This lets Stripe ship breaking changes constantly without ever breaking an existing
integration, and without maintaining `v1`, `v2`, `v3`... `v47` as separate deployed services.

### Deprecation Policy (Mandatory Once You Version)

```http
GET /v1/orders/123 HTTP/1.1

HTTP/1.1 200 OK
Sunset: Sat, 31 Dec 2026 23:59:59 GMT
Deprecation: true
Link: <https://api.example.com/v2/orders/123>; rel="successor-version"
```

`Sunset` (RFC 8594) and `Deprecation` are standard HTTP headers for signaling that an endpoint
or version will stop working. Always:

- Announce deprecation with a fixed sunset date, communicated well in advance (industry norm:
  6–12 months for external APIs with real integrators)
- Return the `Sunset` header on every response from the deprecated version
- Provide a clear migration guide linking old fields/endpoints to their new equivalents
- Monitor actual usage of the deprecated version before removing it — "we announced it" is not
  the same as "no one is still calling it"

### When NOT to Version Formally

- **Pre-launch / no external consumers yet** — internal APIs still under active design can
  change freely; formal versioning overhead isn't earned until someone outside your immediate
  team depends on stability
- **Single first-party client you fully control** (e.g., a mobile app and its API, both
  deployed by the same team in lockstep) — you can often coordinate breaking changes via
  deployment sequencing instead of maintaining parallel versions
- **Internal microservice-to-microservice calls within one team's ownership** — a shared
  contract-testing suite (e.g., Pact) is often lighter-weight than full version management
