---
name: api-engineering
description: >
  Expert-level API design, integration, and resilience engineering skill, language- and
  domain-agnostic. Use whenever the user is designing, consuming, versioning, securing, or
  hardening an API or an integration between systems. Triggers: REST, GraphQL, SOAP, OpenAPI,
  API versioning, OAuth2, OAuth 2.1, JWT for API auth, rate limiting, retry policies, backoff,
  circuit breakers, API gateway, idempotency keys, webhooks, polling, pub/sub integration,
  "design this API", "how should I version this endpoint", "my integration keeps failing",
  "how do I make this call retry safely", "prevent duplicate requests", "protect this API from
  cascading failures". Especially relevant for RPA/automation work integrating with external
  systems via API, and for any backend exposing or consuming APIs. Complements web-devops
  (build/deploy) and software-architecture (system structure) — this skill covers the contract
  and resilience layer between systems.
---

# API Engineering Skill

Protocol selection, contract design, authentication, and resilience patterns for building and
consuming APIs reliably — grounded in IETF RFCs, W3C/OpenAPI/GraphQL Foundation specifications,
and battle-tested industry practice (Stripe, Google, Microsoft, AWS, Netflix). Especially
relevant to integration-heavy work (RPA, ETL, third-party API consumption) where a single
unhandled failure mode can silently corrupt data or duplicate transactions.

---

## How to Use This Skill

1. **Identify the layer of the question**: protocol choice (REST/GraphQL/SOAP), contract design
   (OpenAPI/versioning), auth (OAuth2/JWT for machine-to-machine or third-party), or resilience
   (retries/circuit breakers/idempotency/rate limiting).
2. **For RPA and integration work specifically**: resilience patterns (Section 4) are usually
   the highest-value content — a bot or integration that doesn't handle retries, idempotency,
   and rate limits correctly will eventually duplicate a transaction or silently drop data.
3. **Cross-reference, don't duplicate**: `web-devops/references/security.md` already covers
   JWT/OAuth/rate limiting from the angle of _authenticating users into your own application_.
   This skill covers the same primitives from the angle of _your system calling — or being
   called by — another system_. Point to the right one based on which direction the call flows.
4. **Always state the failure mode being defended against** — a retry policy without idempotency
   is not safety, it's a duplicate-transaction generator. Never present resilience patterns in
   isolation from the failure they prevent.
5. **Always include a "when NOT to use" note** — GraphQL is not automatically better than REST;
   circuit breakers add real operational complexity; not every endpoint needs an idempotency key.

---

## Quick Decision Guide

| Situation                                                                                 | Guidance                                                |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Public API for many unknown consumers, simple resource CRUD                               | REST                                                    |
| Multiple clients need different, evolving views of the same data (mobile vs web)          | GraphQL                                                 |
| Enterprise/legacy integration requiring formal contracts (banking, insurance, government) | SOAP may still be mandated — see when-not-to-avoid note |
| Publishing an API other teams/partners will consume                                       | API-First: write the OpenAPI spec before code           |
| Breaking change needed on a live API                                                      | Version it — never break existing consumers silently    |
| Calling a third-party API on behalf of your app (not a user)                              | OAuth2 Client Credentials grant                         |
| A user authorizes your app to act for them on another service                             | OAuth2 Authorization Code + PKCE (OAuth 2.1 baseline)   |
| Your API/integration is called by outside consumers at volume                             | Rate limiting — protect yourself                        |
| You call external APIs that may be rate-limited or flaky                                  | Retry with exponential backoff + jitter, always bounded |
| A downstream dependency is failing repeatedly                                             | Circuit breaker — stop hammering a dead service         |
| Any POST/PATCH that creates or charges something, especially after a retry                | Idempotency key — mandatory, not optional               |
| You need many services to react to one event, decoupled                                   | Webhook or pub/sub, not synchronous polling             |
| You don't control the other system and it has no webhook support                          | Polling with backoff, as a last resort                  |

---

## 1. Protocol Selection — REST, GraphQL, SOAP

REST (Fielding, 2000) remains the default for the overwhelming majority of new APIs — simple
mental model, cacheable, stateless, wide tooling support. GraphQL (Facebook/GraphQL Foundation, 2015) solves the specific problem of over-fetching/under-fetching when multiple heterogeneous
clients need different shapes of the same data. SOAP (W3C, 2003) persists in specific enterprise
domains (banking via SWIFT/ISO 20022, healthcare via HL7, government/legacy systems) where
formal contracts (WSDL) and built-in transactionality (WS-\* standards) are institutional
requirements — not a technology choice most new projects should make.

→ See `references/protocols.md` for the Richardson Maturity Model, GraphQL schema design,
when SOAP is still the correct (not legacy) answer, and the "REST" APIs that violate REST.

---

## 2. OpenAPI & API Versioning

**API-First**: the OpenAPI specification is written and agreed upon before implementation —
covered in depth in `software-architecture/references/api-first-integration-nfrs.md`. This
skill focuses on the mechanics: OpenAPI 3.1 structure, and the **versioning strategies** that
let an API evolve without breaking existing consumers — a problem every long-lived API faces.

→ See `references/openapi-versioning.md` for OpenAPI 3.1 authoring, URI/header/media-type
versioning strategies compared, Stripe's date-based versioning model, and deprecation policy.

---

## 3. API Authentication — OAuth2/2.1 & JWT for Machine-to-Machine

Covers OAuth2 and JWT specifically for **API-to-API and third-party integration
authentication** — a different context from user login (covered in `web-devops/security.md`).
Grant type selection matters enormously here: using the wrong OAuth2 grant type for a
machine-to-machine integration is one of the most common integration security mistakes.

**Current standard (2026):** OAuth 2.1 (IETF draft, not yet a final RFC, but its
requirements — mandatory PKCE, no implicit grant, no Resource Owner Password Credentials —
are already the baseline enforced by all major identity providers and are required by the
Model Context Protocol specification for remote servers).

→ See `references/api-auth.md` for grant type selection (Client Credentials vs Authorization
Code vs Device Code), PKCE mechanics, JWT validation for API consumers, and token storage
for service-to-service credentials.

---

## 4. Resilience Patterns — Retries, Circuit Breakers, Idempotency, Rate Limiting

This is the highest-value section for integration-heavy work. Every pattern here defends
against a specific, named failure mode:

| Pattern                             | Defends against                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------- |
| Retry with backoff + jitter         | Transient failures (network blip, momentary overload)                           |
| Circuit breaker                     | Cascading failure from hammering an already-failing dependency                  |
| Idempotency key                     | Duplicate side effects (double charge, duplicate record) from a retried request |
| Rate limiting (as a provider)       | Your own API being overwhelmed by one client starving others                    |
| Rate limit handling (as a consumer) | Getting banned/throttled by a third-party API you depend on                     |

**The critical combination:** retries without idempotency keys are dangerous — a retried POST
that already succeeded server-side, but whose response was lost in transit, will create a
duplicate resource or a duplicate charge unless the server can recognize the retry as the same
logical operation.

→ See `references/resilience-patterns.md` for exponential backoff with jitter (AWS
Architecture Blog algorithm), the circuit breaker state machine (Fowler), Stripe's idempotency
key implementation (now IETF draft-ietf-httpapi-idempotency-key-header), and rate limit
handling as both provider and consumer.

---

## 5. API Gateway & Integration Patterns

An **API Gateway** centralizes cross-cutting concerns (auth, rate limiting, routing, request
transformation) in front of one or more backend services — but it is infrastructure, not a
architectural silver bullet, and adds a hop and an operational dependency.

**Integration patterns** for how systems notify each other of events: **Webhooks**
(push, real-time, requires the sender to be reliable), **Polling** (pull, simple, wasteful,
appropriate when webhooks aren't available), **Long Polling / SSE** (semi-real-time without
full duplex), **Pub/Sub** (fully decoupled, appropriate for many-to-many event distribution).

→ See `references/gateway-integration.md` for API Gateway responsibilities and product
comparison (Kong, AWS API Gateway, Azure APIM), webhook delivery reliability (signature
verification, retry-on-failure, replay protection), and polling-vs-webhook decision criteria —
directly relevant to RPA integrations with systems that only support one or the other.

---

## Cross-Cutting: Avoiding Over-Engineering

- Don't adopt GraphQL because it's newer — adopt it because you have a genuine over-fetching
  problem across heterogeneous clients. A single-client REST API gains nothing from GraphQL.
- Don't add a circuit breaker to every external call — reserve it for dependencies whose
  failure is both plausible and expensive to keep retrying against.
- Don't version an API before it has any external consumers — internal, pre-launch APIs can
  change freely; versioning discipline starts the moment someone outside your team depends on it.
- Don't build a custom API Gateway when a managed one (AWS API Gateway, Cloudflare, Kong) meets
  the need — this is infrastructure, not differentiated business logic.

---

## Reference Files

- `references/protocols.md` — REST (Richardson Maturity Model), GraphQL, SOAP, protocol
  selection criteria, common REST anti-patterns
- `references/openapi-versioning.md` — OpenAPI 3.1 authoring, API versioning strategies
  (URI/header/media-type), Stripe's date-based model, deprecation policy
- `references/api-auth.md` — OAuth2/2.1 grant types for machine-to-machine auth, PKCE,
  JWT validation for API consumers, service-to-service credential storage
- `references/resilience-patterns.md` — exponential backoff + jitter, circuit breaker state
  machine, idempotency keys, rate limiting as provider and consumer
- `references/gateway-integration.md` — API Gateway patterns and product comparison, webhooks
  vs polling vs pub/sub, webhook delivery reliability
