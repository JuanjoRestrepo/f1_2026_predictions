# Agentic Platform — Unity AI Gateway and Agent Governance

> **Sources**: Unity AI Gateway GA Announcement (August 4, 2026).
> https://www.databricks.com/blog/unity-ai-gateway-generally-available
> AI Governance at Data + AI Summit 2026.
> https://www.databricks.com/blog/ai-governance-data-ai-summit-2026-whats-new-unity-ai-gateway
> Unity AI Gateway Product Page. https://www.databricks.com/product/artificial-intelligence/unity-ai-gateway
> Omnigent. https://databricks.com/product/artificial-intelligence/omnigent

## Table of Contents

1. [The Agent Context Problem](#context-problem)
2. [The Four Enterprise AI Challenges](#four-challenges)
3. [Model vs Harness Architecture](#model-harness)
4. [Unity AI Gateway — Overview](#unity-ai-gateway)
5. [AI Spend Visibility and Budgets](#budgets)
6. [Smart Routing](#smart-routing)
7. [Contextual Service Policies](#policies)
8. [Agent Tracing and Guardrails](#tracing-guardrails)
9. [Omnigent — Meta-Harness](#omnigent)
10. [Document Intelligence (ai_parse_document)](#document-intelligence)
11. [Lakebase — Transactional + Analytical Convergence](#lakebase)
12. [Platform Architecture: Four Layers](#platform-layers)

---

## 1. The Agent Context Problem {#context-problem}

The core thesis from Databricks Data + AI Summit 2026 (Ali Ghodsi keynote):

> "The problem is not that agents lack intelligence. Agents lack context."

Foundation models are highly capable within their training distribution. The failure mode
in enterprise deployments is not reasoning ability — it is the absence of grounding in:
- Business-specific terminology (what does "churn" mean in this company's data model?)
- Organizational data (which tables contain what, their relationships, their freshness)
- Governance context (what data can this agent access? on whose behalf?)
- Cost and operational constraints (which model is appropriate for this task?)

The Databricks agentic platform addresses the context problem through four coordinated
capabilities: **Choice** (model/harness flexibility), **Context** (Genie Ontology,
Feature Store, RAG), **Control** (Unity AI Gateway policies, budgets, guardrails), and
**Cost** (spend visibility, smart routing).

---

## 2. The Four Enterprise AI Challenges {#four-challenges}

| Challenge | Description | Databricks solution |
|---|---|---|
| **Context** | Agents need grounding in enterprise data, business semantics, and memory to produce correct, useful outputs. | Genie Ontology, Unity Catalog semantics, Feature Store, Document Intelligence, RAG via AgentBricks |
| **Cost** | AI spend is opaque — multiple tools, models, and teams each with their own billing. Runaway spend with no visibility. | Unity AI Gateway Budgets, spend attribution, Smart Routing to cheaper models |
| **Control** | Agents access sensitive data, invoke tools, and take actions on behalf of users. Traditional RBAC governs *access*, not *actions*. | Unity AI Gateway Contextual Service Policies, guardrails (PII, prompt injection), audit logs, Lakewatch |
| **Choice** | Model innovation moves fast. Lock-in to one provider prevents using the best model for each task. | AnyModel support (Claude, GPT-4o, Gemini, Grok, Llama, Qwen), any harness (LangGraph, CrewAI, Claude Code SDK, OpenAI Agent SDK) |

---

## 3. Model vs Harness Architecture {#model-harness}

A **Model** is the foundation model — the raw inference engine:
- Anthropic Claude (claude-3-5-sonnet, claude-opus-4, etc.)
- OpenAI GPT-4o, o3
- Google Gemini (Flash, Pro, Ultra)
- xAI Grok
- Meta Llama (3.1, 3.3, 3.4)
- Mistral, Qwen, DBRX

A **Harness** packages a model with context, tools, skills, and MCPs — making it
useful for a specific type of work:

| Harness | Provider | Foundation model(s) |
|---|---|---|
| Claude Code | Anthropic | Claude (claude-opus-4, claude-sonnet-4-6) |
| Codex / OpenAI Agent SDK | OpenAI | GPT-4o, o3 |
| Copilot | Microsoft | Multiple (GPT-4o via Azure OpenAI) |
| Genie Code | Databricks | Multiple (Claude, GPT-4o, Gemini — selectable) |
| Cursor | Anysphere | Multiple |
| Custom agents | User-built | Any model |

**The key insight**: a model alone is not useful without context. The harness provides:
- Skills (task-specific prompting)
- MCP servers (tool connections: databases, APIs, file systems)
- Memory (conversation history, user preferences)
- Policies (what the agent can and cannot do)

**Omnigent** is Databricks's open-source meta-harness that sits *above* individual
harnesses — composing them, governing them, and routing between them (see §9).

---

## 4. Unity AI Gateway — Overview {#unity-ai-gateway}

Unity AI Gateway (GA: August 4, 2026) is Databricks's runtime governance layer for
enterprise AI. It extends Unity Catalog from governing *data* to governing what agents,
models, MCP services, and skills *do at runtime*.

**What it governs**:

| Asset type | Governance capability |
|---|---|
| Foundation models (hosted + external) | Access control, spend attribution, routing |
| AI agents (custom, coding) | Token usage, policy enforcement, action audit |
| MCP servers | Which tools an agent can invoke, with what permissions |
| Skills | Access control, versioning |
| Coding agents (Claude Code, Codex, Copilot) | Budget caps, policy enforcement, session tracing |
| Agent Memory / sessions | Governed storage in Lakebase |

**Unity AI Gateway vs Unity Catalog**:

| | Unity Catalog | Unity AI Gateway |
|---|---|---|
| Governs | Data assets (tables, files, models, volumes) | AI actions at runtime (prompts, tool calls, agent actions) |
| Enforcement time | At query / data access time | At inference / agent invocation time |
| Analogy | Org chart + key-card system | Live security operations center |

Both work together: Unity Catalog defines *who can access what data*; Unity AI Gateway
defines *what agents can do* during a specific interaction.

**Over 1 quadrillion tokens** were processed through the gateway in the 12 months
preceding GA, across customers including Rivian, Asana, Edmunds, Udemy, and Volkswagen
Group Technologies.

---

## 5. AI Spend Visibility and Budgets {#budgets}

### Spend Visibility ("See It → Show It → Act on It")

```
See it:  Unified AI spend view across all models, providers, tools, teams
Show it: Per-user, per-team, per-application cost dashboards in Unity Catalog
Act on it: Budgets + Smart Routing + Contextual Policies
```

**Spend attribution dimensions**:
- By user or service principal
- By team / group
- By tool (Claude Code, Codex, Copilot, custom agent)
- By model (claude-opus-4, gpt-4o, gemini-pro)
- By use case / application tag

### Budgets

Budgets set token-level spend limits that automatically block requests when exceeded.
Databricks uses budgets internally to manage spend across thousands of employees with
access to multiple coding agent tools.

```python
# Unity AI Gateway SDK (Databricks SDK — Python)
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.aigateway import (
    AiGatewayGuardrails,
    RateLimit,
    RateLimitPeriod,
    UsageTrackingConfig,
)

client = WorkspaceClient()

# Create a budget-enforced AI Gateway route for a team
client.serving_endpoints.put_ai_gateway(
    name="data-engineering-ai-gateway",
    guardrails=AiGatewayGuardrails(
        pii={"behavior": "BLOCK"},                        # block PII in prompts
        safety={"behavior": "BLOCK"},                     # block unsafe content
    ),
    rate_limits=[
        RateLimit(
            key="user",                                   # per-user limit
            renewal_period=RateLimitPeriod.MINUTE,
            calls=60,                                     # 60 calls/minute/user
        ),
        RateLimit(
            key="endpoint",                               # hard cap per endpoint
            renewal_period=RateLimitPeriod.DAY,
            calls=100000,                                 # 100k calls/day across all users
        ),
    ],
    usage_tracking_config=UsageTrackingConfig(enabled=True),
)
```

**Budget design principles** (from Databricks internal practice):
- Separate **runaway spend protection** (per-request cap) from **monthly spend limits**
  (periodic budget). Different reset cycles, different enforcement actions.
- Most limit hits are normal engineers doing normal work — the unblock path should be
  self-service (not an approval queue). Reserve manual approvals for exceptional cases.
- Make approvals time-limited. A one-month project approval should not become a
  permanent entitlement.
- Route ALL agent traffic through one control point (the gateway). Per-tool admin
  consoles provide no consolidated view.

---

## 6. Smart Routing {#smart-routing}

Smart Routing (Beta as of DAIS 2026) dynamically routes each AI request to the most
appropriate model based on task complexity, quality requirements, cost, availability,
and current budget status.

**Routing strategy**:

```
Incoming request → Task complexity assessment → Model selection
   |
   ├── Simple task (classification, short generation) → lightweight model (Mixtral, Llama-3-3-70b)
   ├── Medium task (summarization, code review) → mid-tier model (GPT-4o-mini, claude-haiku)
   └── Complex task (multi-step reasoning, architecture, novel code) → frontier model (claude-opus-4, GPT-4o)

Budget headroom check → if budget exceeded → route to cheaper fallback model
Availability check → if primary model unavailable → route to equivalent from another provider
```

```python
# Serving endpoint configuration with Smart Routing (REST API / SDK)
endpoint_config = {
    "name": "de-team-ai-gateway",
    "config": {
        "served_entities": [
            # Primary: Claude Opus for complex tasks
            {
                "name": "claude-opus-4",
                "external_model": {
                    "name": "claude-opus-4",
                    "provider": "anthropic",
                    "task": "llm/v1/chat",
                    "anthropic_config": {
                        "anthropic_api_key": "{{secrets/ai-secrets/anthropic-key}}",
                    },
                },
                "traffic_percentage": 0,     # routing managed by Smart Routing, not fixed %
            },
            # Fallback: cost-efficient model for simple tasks / budget-constrained requests
            {
                "name": "llama-3-3-70b",
                "external_model": {
                    "name": "meta-llama-3-3-70b-instruct",
                    "provider": "databricks",
                    "task": "llm/v1/chat",
                },
                "traffic_percentage": 0,
            },
        ],
        "ai_gateway": {
            "smart_routing": {
                "enabled": True,
                "quality_vs_cost_tradeoff": 0.7,   # 0.0 = maximize cost savings; 1.0 = maximize quality
            },
        },
    },
}
```

---

## 7. Contextual Service Policies {#policies}

Contextual Service Policies (Beta as of DAIS 2026) control what an agent can *do* during
a specific interaction — not just what data it can access. They are defined as Unity
Catalog SQL functions and evaluated at runtime against the live request context.

**Traditional RBAC governs access**: "Can this user query this table?"
**Contextual policies govern actions**: "Can this agent publish to this website given
the current user's role and the content of the request?"

```sql
-- Define a contextual service policy as a Unity Catalog SQL function
CREATE FUNCTION prod_infra.policies.code_agent_write_policy(
    user_group    STRING,    -- group membership of the invoking user
    action_type   STRING,    -- action the agent is attempting (e.g., "git_push", "file_write")
    target_path   STRING,    -- target resource path
    content_tags  STRING     -- tags on the content being acted upon
)
RETURNS STRING    -- "ALLOW", "DENY", or "REQUIRE_APPROVAL"
LANGUAGE SQL
RETURN
  CASE
    -- Allow: engineers pushing to non-main branches
    WHEN action_type = 'git_push'
     AND target_path NOT LIKE '%/main'
     AND user_group = 'engineers'
    THEN 'ALLOW'

    -- Require approval: pushing to main
    WHEN action_type = 'git_push'
     AND target_path LIKE '%/main'
    THEN 'REQUIRE_APPROVAL'

    -- Deny: any agent touching production database write operations
    WHEN action_type = 'db_write'
     AND target_path LIKE 'prod_%'
     AND content_tags LIKE '%customer_pii%'
    THEN 'DENY'

    -- Default: deny all unspecified actions
    ELSE 'DENY'
  END;

-- Assign the policy to an AI Gateway endpoint
-- (via Databricks AI Gateway configuration in the SDK or UI)
```

**Policy trigger dimensions** (any combination):
- User identity or group membership
- Agent identity / endpoint name
- Model being invoked
- MCP server or tool being called
- Content of the request or response (inspected at runtime)
- Time of day / business hours enforcement
- Budget remaining

---

## 8. Agent Tracing and Guardrails {#tracing-guardrails}

### Agent Tracing

Unity AI Gateway captures governed audit logs for all AI activity routing through it:
prompt content, tool invocations, model responses, token counts, latency, policy
enforcement decisions. Logs land in Unity Catalog Delta tables — governed, queryable
with SQL, and integrated with Genie for conversational analysis.

```sql
-- Query Unity AI Gateway audit logs in Unity Catalog (system tables)
SELECT
    event_time,
    user_identity,
    endpoint_name,
    model_name,
    token_count_prompt,
    token_count_completion,
    latency_ms,
    policy_decision,            -- ALLOW / DENY / REQUIRE_APPROVAL
    guardrail_triggered,        -- PII / SAFETY / PROMPT_INJECTION or NULL
    estimated_cost_usd
FROM system.aigateway.audit_logs
WHERE event_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAYS
  AND guardrail_triggered IS NOT NULL    -- filter for sessions where guardrails fired
ORDER BY event_time DESC;

-- Cost attribution by team over the last 30 days
SELECT
    team_tag,
    model_name,
    SUM(token_count_prompt + token_count_completion) AS total_tokens,
    SUM(estimated_cost_usd) AS total_cost_usd,
    COUNT(*) AS request_count
FROM system.aigateway.audit_logs
WHERE event_time >= CURRENT_TIMESTAMP - INTERVAL 30 DAYS
GROUP BY team_tag, model_name
ORDER BY total_cost_usd DESC;
```

### Guardrails

Built-in guardrails inspect all content flowing through the gateway:

| Guardrail | What it detects | Default action |
|---|---|---|
| PII detection | Names, emails, SSNs, credit cards in prompts/responses | Block or redact |
| Prompt injection | Instructions embedded in user content attempting to override system prompt | Block |
| Safety filters | Harmful content, CSAM, policy violations | Block |
| Content moderation | Offensive or inappropriate content | Block or flag |

**Integration with Lakewatch**: gateway events and guardrail triggers stream to
Lakewatch (Databricks agentic security product) for threat detection and incident response.

---

## 9. Omnigent — Meta-Harness {#omnigent}

Omnigent is Databricks's open-source (Apache 2.0) meta-harness for composing, governing,
and routing across multiple coding agents and LLM frameworks in a single unified workflow.

**What Omnigent solves**: teams running multiple coding agents (Claude Code, Codex, custom
LangGraph agents) each have their own budget consoles, policy surfaces, and session state.
Omnigent sits above them all, providing:

| Capability | Description |
|---|---|
| Multi-harness composition | Compose Claude Code, Codex, CrewAI, LangGraph agents in one workflow with one-line swapping |
| Unified governance | All agent sessions governed through Unity AI Gateway (contextual policies, budgets, tracing) |
| Session sharing | Live agent sessions shareable via URL — previously local-only sessions become collaborative |
| MCP integration | Unified MCP server connections (databases, APIs, GitHub, Jira) across all composed agents |
| Skills management | Define and share reusable agent skills across the organization |
| Cross-framework routing | Route specific tasks to the harness best suited to them |

**Omnigent tiers**:
- **Open source** (Apache 2.0): self-hosted, community-supported, no Databricks dependency
- **Managed on Databricks** (Beta at DAIS 2026): fully managed, integrated with Unity AI
  Gateway for governance, Unity Catalog for context, and Lakebase for session memory

**Session URL sharing** (key differentiator from local harnesses):

```
Without Omnigent:
  Agent session → local machine → session state lost on disconnect, not shareable

With Omnigent (managed):
  Agent session → Omnigent cloud → session URL generated
  → Share URL with colleague or manager
  → Session state preserved, all MCPs/tools active, collaborative review possible
```

**Accessing Omnigent on Databricks**:
Navigate to `https://<workspace>.azuredatabricks.net/omnigent` within a Unity Catalog-enabled
workspace. (Beta; availability varies by workspace configuration.)

---

## 10. Document Intelligence (ai_parse_document) {#document-intelligence}

Document Intelligence (GA at DAIS 2026) provides SQL and Python functions for extracting
structured information from unstructured documents (PDFs, images, contracts, invoices,
receipts, medical records).

```sql
-- Batch document parsing via SQL AI function
SELECT
    document_id,
    document_type,
    ai_parse_document(
        document_content,    -- BINARY column containing the document bytes
        'Extract as JSON: {
           "vendor_name": string,
           "invoice_number": string,
           "invoice_date": date,
           "line_items": [{"description": string, "quantity": int, "unit_price": float}],
           "total_amount": float,
           "currency": string,
           "payment_due_date": date
        }',
        model => 'databricks-meta-llama-3-1-405b-instruct'
    ) AS extracted_fields
FROM prod_sales.raw.invoice_documents
WHERE processing_status = 'pending';
```

```python
# Python API for document intelligence (Mosaic AI)
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

client = WorkspaceClient()

# Process a document via the model serving endpoint
with open("/Volumes/prod_infra/uploads/invoice_001.pdf", "rb") as f:
    doc_bytes = f.read()

response = client.serving_endpoints.query(
    name="document-intelligence-endpoint",
    messages=[
        ChatMessage(
            role=ChatMessageRole.USER,
            content=[
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": doc_bytes,
                    },
                },
                {
                    "type": "text",
                    "text": "Extract: vendor_name, total_amount, invoice_date, line_items",
                },
            ],
        )
    ],
)
```

**Document Intelligence in DLT (batch pipeline)**:

```python
import dlt
from pyspark.sql import functions as F


@dlt.table(
    comment="Parsed invoice fields extracted via Databricks Document Intelligence.",
    table_properties={"quality": "silver"},
)
def silver_parsed_invoices() -> "DataFrame":
    """Parses raw invoice PDFs from Bronze into structured fields."""
    return (
        dlt.read_stream("bronze_invoice_documents")
        .withColumn(
            "parsed_fields",
            F.expr("""
                ai_parse_document(
                    document_content,
                    'Extract JSON: vendor_name, invoice_number, total_amount, invoice_date',
                    model => 'databricks-meta-llama-3-1-405b-instruct'
                )
            """),
        )
        .withColumn("vendor_name",    F.get_json_object("parsed_fields", "$.vendor_name"))
        .withColumn("invoice_number", F.get_json_object("parsed_fields", "$.invoice_number"))
        .withColumn("total_amount",   F.get_json_object("parsed_fields", "$.total_amount").cast("double"))
        .withColumn("invoice_date",   F.get_json_object("parsed_fields", "$.invoice_date").cast("date"))
        .drop("document_content", "parsed_fields")
    )
```

---

## 11. Lakebase — Transactional + Analytical Convergence {#lakebase}

Lakebase (announced DAIS 2026) is Databricks's serverless Postgres-compatible transactional
database layer, enabling OLTP workloads directly on the Lakehouse alongside OLAP workloads.

**The problem Lakebase solves**: traditional architectures maintain separate OLTP databases
(PostgreSQL, MySQL) and analytical stores (data warehouses), connected by ETL pipelines.
This creates data duplication, latency between operational and analytical views, and
governance fragmentation.

**LTAP — Lake Transactional/Analytical Processing**:

```
Traditional:
  PostgreSQL (OLTP) → ETL → Data Warehouse (OLAP)
  Problem: data duplication, ETL latency, governance split

With LTAP:
  Lakebase (OLTP/Postgres) ↔ Lakehouse (OLAP/Delta Lake)
  One copy of data in open formats (Delta Lake + Iceberg)
  Transactional writes via Lakebase; analytical reads via Lakehouse
  No ETL pipeline between them
```

| Feature | Lakebase |
|---|---|
| Interface | PostgreSQL-compatible (standard Postgres drivers) |
| Compute | Serverless — Databricks manages all infrastructure |
| Storage | Delta Lake / Iceberg (open formats) |
| Durability | Cross-cloud and cross-region disaster recovery |
| Branching | Sub-second branching for isolated testing and CI |
| Governance | Unity Catalog — same governance surface as Lakehouse data |
| Latency | Near real-time (sub-second for point reads; batch for analytics) |

**Key use cases**:
- **Agent Memory Services**: Omnigent and Genie agent sessions store memory (conversation
  history, user preferences, session state) in Lakebase — governed, persistent, and
  queryable via SQL.
- **Operational analytics**: run both transactional writes and analytical queries on the
  same dataset without ETL.
- **Feature Store** (real-time): Lakebase as the online store for ML Feature Store lookups
  at low latency (replaces Redis or custom online stores).

```python
# Connect to Lakebase using standard PostgreSQL driver (psycopg2)
import psycopg2

conn = psycopg2.connect(
    host="<lakebase-endpoint>.databricks.com",
    port=5432,
    database="prod_sales_lakebase",
    user="<service-principal-client-id>",
    password="<databricks-token>",
    sslmode="require",
)

cursor = conn.cursor()

# Standard PostgreSQL DML — transactional, ACID-compliant
cursor.execute("""
    INSERT INTO agent_sessions (session_id, user_id, session_state, updated_at)
    VALUES (%s, %s, %s, NOW())
    ON CONFLICT (session_id) DO UPDATE
        SET session_state = EXCLUDED.session_state,
            updated_at = NOW()
""", (session_id, user_id, session_state_json))

conn.commit()
conn.close()
```

---

## 12. Platform Architecture: Four Layers {#platform-layers}

The full Databricks Lakehouse architecture as presented at DAIS 2026:

```
Layer 4: AGENTIC APPS
├── Genie Suite (One, Agents, Code, App Builder, ZeroOps, AI/BI)
├── Apps (Vibe coding + governed enterprise data app deployment)
├── Lakewatch (agentic security against AI-native threats)
├── CustomerLake (1:1 personalized customer experiences)
└── Omnigent (meta-harness for composing and governing agents)

Layer 3: UNIFIED GOVERNANCE
├── Unity Catalog (data assets: tables, files, volumes, models)
└── Unity AI Gateway (AI assets: models, agents, MCPs, skills — runtime governance)
    ├── Hard spend caps and budget management
    ├── Smart Routing (model selection by task/cost/quality)
    ├── Contextual Service Policies (action-level control)
    ├── Guardrails (PII, prompt injection, safety)
    └── Governed audit logs → Delta tables → Lakewatch

Layer 2: AGENTIC DATA
├── Lakeflow (Connect + Declarative Pipelines + Jobs + Designer)
├── Lakehouse (Delta Lake OLAP — structured + unstructured data)
└── Lakebase (OLTP/Postgres — transactional workloads + agent memory)
    └── LTAP: transactional and analytical on the same open-format copy

Layer 1: OPEN INFRASTRUCTURE
├── Delta Lake (open table format — ACID transactions, time travel)
├── Apache Iceberg v3 (interoperability with non-Databricks engines)
└── AnyCloud · AnyModel · AnyData (no vendor lock-in at the infrastructure level)
```

**The governance insight**: Unity Catalog (Layer 3) governs *all* assets across all
layers — tables, files, volumes, models, agents, MCP servers, skills. It is the single
governance plane for both data and AI. Unity AI Gateway handles the runtime enforcement
at inference time, while Unity Catalog handles the identity and access control plane.
