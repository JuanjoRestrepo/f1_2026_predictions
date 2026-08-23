# Genie Ontology, Genie Suite, and AgentBricks

> **Sources**: Data + AI Summit 2026 Keynote and announcements.
> https://www.databricks.com/blog/unifying-data-and-governance-agentic-era-whats-new-azure-databricks
> Genie One and Genie Ontology announcements.
> AgentBricks Deep Dive. https://databricks.com/blog/mosaic-ai-announcements-data-ai-summit-2025
> MLflow 3.0 for GenAI. https://docs.databricks.com/aws/en/mlflow3/genai/

## Table of Contents

1. [Genie Ontology — The Context Layer](#ontology)
2. [Genie ONE](#genie-one)
3. [Genie AGENTS](#genie-agents)
4. [Genie CODE](#genie-code)
5. [Genie APP BUILDER](#genie-app-builder)
6. [Genie ZERO OPS](#genie-zero-ops)
7. [Genie AI/BI](#genie-aibi)
8. [AgentBricks — Building Domain Agents](#agentbricks)
9. [Agent Quality Loop: Capture → Judge → Align → Optimize](#quality-loop)
10. [MLflow 3 Integration](#mlflow3)
11. [Genie Access Points and MCP](#genie-mcp)

---

## 1. Genie Ontology — The Context Layer {#ontology}

Genie Ontology is Databricks's self-improving semantic context layer, announced at
Data + AI Summit 2026. It addresses the root cause of agent failures in enterprise
environments: lack of grounding in business-specific terminology and organizational
data semantics.

**The problem Genie Ontology solves**:

```
An agent sees: SELECT * FROM silver_customers WHERE churn_score > 0.7
An agent needs to know:
  - What does "churn" mean in this company's context?
  - Which "churn_score" column? (CRM has one, billing has another, ML model has a third)
  - Is 0.7 the right threshold? (Business standard is 0.65 in marketing, 0.80 in finance)
  - What is the trust level of each definition?

Without ontology: agent picks arbitrarily or hallucinates.
With Genie Ontology: agent knows the authoritative, domain-calibrated definitions.
```

### Components

**Unity Catalog Semantic Layer** (feeds the ontology):

| Component | Description |
|---|---|
| **Business Glossary** (Preview) | Authoritative definitions for business terms (e.g., "active customer", "churn", "revenue"), connected to underlying data assets. Co-curated by humans and Genie Code. |
| **Domains** | Organizational groupings for business concepts (e.g., Marketing, Finance, Operations). Disambiguates same term used differently across domains. |
| **UC Metrics** | Trusted, canonical metric definitions (e.g., `monthly_active_users`, `net_revenue`) with agreed-upon SQL logic. Prevents each team from computing KPIs differently. |

**Knowledge sources** (auto-ingested by Genie Ontology):
- Unity Catalog metadata: table schemas, column descriptions, data lineage, quality metrics
- Google Drive, SharePoint, Confluence: product specs, business rules, definitions
- Jira, Linear: project context, domain knowledge in tickets
- Slack, Teams: ad-hoc definitions and business context surfaced from conversations

**How Genie Ontology improves over time**:
1. Initial state: seeded from Unity Catalog metadata and connected knowledge sources.
2. Agents interact with data using the ontology-provided context.
3. User feedback and SME corrections (via Genie AI/BI) update the ontology.
4. MemAlign calibrates ontology-based judge scoring to the domain.
5. The ontology self-improves: the more it is used and corrected, the better it grounds agents.

```sql
-- Define a Unity Catalog Metric (feeds Genie Ontology)
CREATE METRIC prod_sales.metrics.monthly_active_customers AS
  SELECT
    DATE_TRUNC('month', order_date) AS month,
    region,
    COUNT(DISTINCT customer_id) AS value
  FROM prod_sales.gold_revenue.daily_revenue
  WHERE order_count > 0
  COMMENT 'Monthly active customers: distinct customers with at least one order in the month.
           Authoritative definition per Finance and Marketing agreement (2026-01-15).';
```

---

## 2. Genie ONE {#genie-one}

Genie ONE (GA at DAIS 2026) is Databricks's agentic coworker for business teams —
an AI assistant that goes beyond question-answering to autonomously produce documents,
reports, analyses, and artifacts on behalf of users.

**Target personas**: business analysts, marketing, finance, sales, operations. Not
primarily aimed at data engineers or data scientists (those use Genie Code instead).

**Capabilities**:
- Natural language queries over Unity Catalog data (grounded by Genie Ontology)
- Multi-turn conversations with memory across sessions (backed by Lakebase)
- Produces deliverables: written reports, slide decks, spreadsheet analyses, dashboards
- Scheduling and alerting: "Alert me when monthly revenue drops below $2M"
- MCP tool integration: invoke external tools (CRM, ticketing, email) from a conversation
- OpenSharing: share Genie ONE agents across the organization (like Delta Sharing for agents)

**Platform availability**: Web (Databricks workspace), iOS, Android, MS Teams, Slack.

**Access from external platforms** (via Genie MCP):

```
From MS Teams:
  @Genie What was our APAC revenue last quarter vs Q3 2024?
  → Genie ONE queries prod_sales.metrics.monthly_active_customers via Genie Ontology
  → Returns answer grounded in authoritative metric definition, with data lineage link

From the Databricks Genie interface:
  User: Show me customers at high churn risk in the EMEA region
  → Genie Ontology resolves "high churn risk" to churn_score > 0.80 (Finance definition)
  → Genie queries silver_customers filtered by region = 'EMEA' and churn_score > 0.80
  → Returns table + natural language summary + option to schedule weekly refresh
```

---

## 3. Genie AGENTS {#genie-agents}

Genie Agents (GA at DAIS 2026) converts Genie ONE conversations into reusable,
automated workflows. When a business user finds a useful Genie interaction pattern,
they can "save as agent" — creating a parameterized, schedulable agent from the
conversation without writing code.

**Use cases**:
- Weekly APAC revenue summary emailed to the regional VP every Monday
- Customer churn watchlist refreshed daily, triggering outreach workflow in Salesforce
- Automated competitive analysis report from public data + internal data, delivered on demand

**OpenSharing for Genie Agents**: agents can be shared across the organization similarly
to Delta Sharing for data — other teams can subscribe to an agent and receive its outputs
without needing access to the underlying data or logic.

---

## 4. Genie CODE {#genie-code}

Genie Code is Databricks's AI coding assistant for data work — positioned as the
Databricks-native alternative to general coding agents (Claude Code, Copilot, Cursor).

**Why Genie Code vs generic coding agents** (Databricks's framing):

| Dimension | Generic coding agent (Claude Code, Copilot) | Genie Code |
|---|---|---|
| Data context | Must be provided manually in prompts | Automatically grounded in Unity Catalog metadata, schemas, lineage |
| Data governance awareness | None | Knows data ownership, access controls, data quality metrics |
| Databricks API fluency | General knowledge | Native: DLT/Lakeflow, MLflow, Delta, Lakeflow Jobs |
| Business semantics | None | Genie Ontology: canonical metric definitions, business glossary |
| MCP integration | Configured manually | Databricks tools available out of the box |

**Genie Code capabilities**:
- Natural language → PySpark / SQL / dbt code (grounded in UC schema context)
- Debug Lakeflow pipeline failures with Unity Catalog lineage context
- Generate `@dlt.table` functions from natural language descriptions
- Explain data quality issues by reading DLT event logs and expectation metrics
- Integrated in Lakeflow Designer (generates transformation code for no-code pipelines)

**Access**: Databricks workspace notebook, Lakeflow Designer, and via Genie MCP
(programmatic access from external coding agents via the MCP protocol).

```
# Example: Genie Code in a Databricks notebook
# User types (in natural language comment or Genie Code chat panel):
"Create a DLT table that joins silver_orders with dim_customer,
 computing customer lifetime value grouped by region and cohort_month"

# Genie Code generates:
@dlt.table(
    comment="Customer lifetime value aggregated by region and acquisition cohort.",
    table_properties={"quality": "gold"},
)
def gold_customer_ltv() -> DataFrame:
    orders = dlt.read("silver_orders")
    customers = dlt.read("dim_customer")
    return (
        orders.join(customers, "customer_id", "left")
        .groupBy(
            "region",
            date_trunc("month", customers.acquisition_date).alias("cohort_month"),
        )
        .agg(
            F.sum("amount").alias("total_ltv"),
            F.count("order_id").alias("total_orders"),
            F.countDistinct("customer_id").alias("unique_customers"),
        )
    )
```

---

## 5. Genie APP BUILDER {#genie-app-builder}

Genie App Builder enables non-engineers to build and deploy governed data applications
via natural language or visual prompting ("Vibe coding"). Applications are deployed
within the Databricks trust boundary — they inherit Unity Catalog governance without
requiring the developer to write authentication or access control code.

**Key properties**:
- Generated apps are deployed as Databricks Apps (serverless, auto-scaling)
- Data access governed by Unity Catalog (the app user's permissions apply)
- Supports: dashboards, data entry forms, operational UIs, agent-powered interfaces
- Output is reviewable code (Python / React) — not a proprietary no-code artifact

**When to use Genie App Builder vs Lakeflow Designer**:

| Tool | Purpose |
|---|---|
| Lakeflow Designer | Build data *pipelines* (ETL, transformations) without code |
| Genie App Builder | Build data *applications* (UIs, dashboards, forms) without code |

---

## 6. Genie ZERO OPS {#genie-zero-ops}

Genie ZeroOps runs autonomous background monitoring agents that watch Lakehouse data,
Lakeflow pipeline health, and ML model performance — proactively surfacing anomalies
and taking remediation actions without manual intervention.

**Use cases**:
- Monitor data freshness across Gold tables; alert when SLA is missed
- Detect statistical drift in feature store distributions; trigger model retraining
- Auto-optimize slow Lakeflow Jobs (identify bottlenecks; suggest or apply config changes)
- Watch Unity AI Gateway spend; alert when approaching budget threshold

---

## 7. Genie AI/BI {#genie-aibi}

Genie AI/BI is the Databricks-native BI product combining Lakeview dashboards (static
charts) with Genie conversational analysis (natural language questions on top of the
same data). Users can toggle between a traditional dashboard view and a Genie chat view
backed by the same Unity Catalog datasets and Genie Ontology context.

**Key differentiator from traditional BI**: the Genie layer answers ad-hoc questions
that no fixed dashboard can anticipate, using the same authoritative metric definitions
and governed data as the dashboard. No separate semantic model to maintain.

---

## 8. AgentBricks — Building Domain Agents {#agentbricks}

AgentBricks (Beta at DAIS 2025, expanded at DAIS 2026) is Databricks's framework for
building high-quality, domain-specific agents that are automatically optimized on your
data. It handles the research-heavy parts of agent engineering:

- Automatic evaluation generation (no need to hand-craft eval datasets)
- Quality optimization for the specific task and domain
- Cost optimization (routes tasks to cheaper models when quality allows)

**AgentBricks task types**:

| Task type | Description |
|---|---|
| Structured information extraction | Extract typed fields from unstructured documents (invoices, contracts, emails) — pairs with Document Intelligence |
| Knowledge assistance | RAG over enterprise unstructured data (PDF libraries, SharePoint, Confluence) — governed by Unity Catalog |
| Custom text transformation | Domain-specific text generation, summarization, classification |
| Multi-agent systems | Orchestrate multiple specialized agents for complex workflows |

**Supported frameworks**: LangGraph, CrewAI, OpenAI Agent SDK, Claude Code SDK, AutoGen,
DSPy, LlamaIndex. AgentBricks wraps any of these with Databricks-specific optimizations.

**Model support** (AgentBricks model choice at DAIS 2026): OpenAI, Anthropic, Google
Gemini, Meta Llama, Alibaba Qwen, xAI Grok (via SpaceX partnership). All under Unity
AI Gateway governance.

### AgentBricks — Knowledge Assistant (RAG)

The Knowledge Assistant pattern provides governed RAG over enterprise unstructured data:

```python
from databricks.agents import KnowledgeAssistant, VectorSearchConfig

# Configure a Knowledge Assistant over a document corpus stored in Unity Catalog Volumes
assistant = KnowledgeAssistant(
    name="hr-policy-assistant",
    vector_search=VectorSearchConfig(
        catalog="prod_hr",
        schema="knowledge",
        index_name="policy_documents_index",      # Databricks Vector Search index
        source_table="prod_hr.knowledge.policy_documents",  # Delta table with document chunks
    ),
    llm_config={
        "model": "databricks-claude-3-5-sonnet",
        "system_prompt": (
            "You are an HR policy assistant for Acme Corp. "
            "Answer questions using only the provided HR policy documents. "
            "If the answer is not in the documents, say so explicitly."
        ),
    },
    guardrails={
        "pii_detection": True,
        "safety_filter": True,
    },
)

# Register in Unity Catalog — governance applied automatically
assistant.register(model_name="prod_hr.agents.hr_policy_assistant")
```

### AgentBricks — Auto-Optimization Workflow

```python
from databricks.agents import AgentBricks, TaskSpec

# Define the agent task in natural language + connect your data
task = TaskSpec(
    description=(
        "Extract vendor name, total amount, invoice date, and payment terms "
        "from invoice PDFs. Return as structured JSON. "
        "Handle handwritten annotations and multi-page invoices."
    ),
    input_schema={"document": "pdf_binary"},
    output_schema={
        "vendor_name": "string",
        "total_amount": "float",
        "invoice_date": "date",
        "payment_terms": "string",
    },
)

# AgentBricks auto-generates evaluations and optimizes the agent
agent_builder = AgentBricks(task=task)

# Connect your data (AgentBricks uses it to generate eval datasets and optimize)
agent_builder.connect_data(
    table_name="prod_finance.invoices.bronze_invoice_documents",
    sample_size=500,
)

# Build: auto-generates evals, benchmarks models, selects optimal configuration
optimized_agent = agent_builder.build(
    model_candidates=["claude-3-5-sonnet", "meta-llama-3-1-70b", "mixtral-8x7b"],
    quality_threshold=0.90,           # minimum judge score to accept
    cost_optimization=True,           # prefer cheaper model if quality meets threshold
)

# Register and deploy the optimized agent
optimized_agent.register(model_name="prod_finance.agents.invoice_extractor")
```

---

## 9. Agent Quality Loop: Capture → Judge → Align → Optimize {#quality-loop}

The quality loop turns production agent traces into a continuous improvement pipeline.
Context: agents are not static — they drift as the world, data, and business context
change. The quality loop provides a systematic, automated mechanism for continuous
alignment.

```
         ┌─────────────────────────────────────────────────────────┐
         │                QUALITY LOOP                             │
         │                                                         │
  Agent  │  Capture          Judge          Align          Optimize │
  in     │  ──────    ──────────────    ──────────    ─────────────│
  prod   │  MLflow 3  LLM judges +     MemAlign:     GEPA:        │
    │    │  OTEL      scorers (built-   calibrate     auto-improve │
    │    │  traces    in + custom)      judge to      agent prompt │
    ▼    │  → UC      → score each      domain        from aligned │
  Traces │  Delta     trace             ~20 SME       judge scores │
    │    │  tables    → flag bad        labels        → better     │
    └────┼────────────────────────────────────────── agent ────────┘
         │                                                ▲
         │              AgentBricks Quality               │
         │         Runs judge on live traffic (online,    │
         │         not just batch) — governed in UC       │
         └────────────────────────────────────────────────┘
```

### Stage 1: Capture

MLflow 3 auto-traces all agent interactions with OTEL-native spans. One line of code
enables tracing for any supported framework:

```python
import mlflow

# Enable auto-tracing (one line — zero re-instrumentation)
mlflow.langchain.autolog()      # LangGraph / LangChain
mlflow.anthropic.autolog()      # Anthropic SDK (Claude)
mlflow.openai.autolog()         # OpenAI SDK

# All agent runs now produce OTEL traces stored in:
# - MLflow experiment (real-time, short-term)
# - Unity Catalog Delta table (long-term, governed, queryable with SQL)
# "Your traces are already eval datasets" — Databricks DAIS 2026
```

### Stage 2: Judge

LLM judges evaluate each trace against quality criteria:

```python
import mlflow

with mlflow.start_run(run_name="weekly_quality_evaluation"):
    results = mlflow.evaluate(
        data="prod_finance.agents.invoice_extractor_traces",    # UC table of traces
        model_type="databricks-agent",
        evaluator_config={
            "databricks-agent": {
                "metrics": [
                    "response/correctness",          # is the extracted data correct?
                    "response/groundedness",         # is the answer grounded in source docs?
                    "retrieval/precision",           # RAG: are retrieved chunks relevant?
                    "agent/token_count",             # cost tracking
                    "agent/latency_ms",              # performance tracking
                ],
                "custom_metrics": [
                    {
                        "name": "invoice_completeness",
                        "definition": "Score 0-1: fraction of required fields successfully extracted.",
                        "grading_prompt": "Check if vendor_name, total_amount, invoice_date, payment_terms all present and correctly typed.",
                    }
                ],
            }
        },
    )
```

### Stage 3: Align (MemAlign)

Judges drift: an LLM judge calibrated to general correctness may not reflect what
"correct" means in your specific business domain. MemAlign calibrates the judge to the
domain using a small number of SME-labeled examples (~20 is sufficient).

```python
from databricks.agents.quality import MemAlign

# MemAlign calibration — requires ~20 SME-labeled trace examples
calibrator = MemAlign(
    judge_model="databricks-claude-3-5-sonnet",    # model acting as the judge
    domain_context="Accounts payable invoice processing for a manufacturing company.",
)

# SME provides labels: sample 20 traces, mark as correct/incorrect with explanations
sme_labels = [
    {
        "trace_id": "trace_001",
        "correct": True,
        "explanation": "Vendor name correctly extracted despite OCR noise.",
    },
    {
        "trace_id": "trace_002",
        "correct": False,
        "explanation": "Total amount extracted pre-tax; should be post-tax per company policy.",
    },
    # ... (~20 total)
]

calibrated_judge = calibrator.fit(sme_labels)
# calibrated_judge now scores traces using domain-specific correctness criteria
```

### Stage 4: Optimize (GEPA)

GEPA (Guided Evaluation with Prompt Adaptation) uses the aligned judge scores to
automatically generate an improved system prompt for the agent — closing the loop
without manual prompt engineering:

```python
from databricks.agents.quality import GEPA

# GEPA takes the calibrated judge and failing traces → produces a better prompt
optimizer = GEPA(
    judge=calibrated_judge,
    agent_endpoint="prod_finance.agents.invoice_extractor",
)

# Run optimization over the failing traces
improved_prompt = optimizer.optimize(
    failing_traces="prod_finance.agents.invoice_extractor_traces",
    num_candidates=10,           # generate 10 candidate prompts
    evaluation_budget=100,       # evaluate each candidate on 100 sample traces
)

# Deploy the improved prompt to the agent
optimizer.deploy(improved_prompt)
```

**AgentBricks Quality (Online, not just batch)**: runs the judge on live production
traffic rather than periodic batch evaluation, providing real-time quality monitoring.
Governed in Unity Catalog — the live traffic judge scores are stored in Delta tables
alongside the traces.

---

## 10. MLflow 3 Integration {#mlflow3}

See `references/mlflow-feature-store.md` §6-7 for full MLflow 3 tracing and evaluation
code templates.

**Key points for the Genie / AgentBricks context**:

- **MLflow 3 auto-tracing is OTEL-native**: traces written to Unity Catalog Delta tables
  at GBs/second throughput via a serverless ingestion path. No OTEL infrastructure to
  operate.
- **Zero re-instrumentation**: changing from one agent framework to another does not
  require re-implementing tracing — OTEL is the common standard.
- **Traces as eval datasets** (direct quote from DAIS 2026): production traces are
  immediately usable as evaluation data. The eval pipeline runs against the same Delta
  tables where traces land.
- **MLflow 3 + AgentBricks Quality**: `mlflow[databricks]>=3.1` SDK provides access
  to both experiment tracking (classical ML) and agent evaluation (GenAI) under a
  unified API.

---

## 11. Genie Access Points and MCP {#genie-mcp}

Genie has its own MCP (Model Context Protocol) server, making it accessible from any
MCP-compatible client — not only the Databricks workspace.

**Access methods**:

| Method | Description |
|---|---|
| Databricks workspace UI | Primary access: `<workspace>.azuredatabricks.net/genie` |
| Genie MCP | Register Genie's MCP server in any MCP-compatible client (Claude Code, Cursor, custom agents) |
| Microsoft Copilot MCP | Register Genie as a tool in Microsoft Copilot via the Copilot MCP connector |
| MS Teams | Install the Genie Teams app — natural language data queries from Teams channels |
| Lakeview Dashboards | Embed Genie chat panel alongside Lakeview charts in a dashboard |
| REST API | `POST /api/2.0/genie/spaces/{space_id}/start-conversation` |
| iOS / Android | Genie ONE mobile app (GA) |

**Registering Genie as an MCP tool in Claude Code**:

```json
// .mcp.json (Claude Code MCP configuration)
{
  "mcpServers": {
    "databricks-genie": {
      "command": "databricks",
      "args": ["genie", "mcp", "--profile", "DEFAULT"],
      "env": {
        "DATABRICKS_HOST": "https://<workspace>.azuredatabricks.net",
        "DATABRICKS_TOKEN": "<pat-or-sp-token>"
      }
    }
  }
}
```

With Genie registered as an MCP tool, Claude Code (or any other MCP client) can
invoke Genie to query Unity Catalog data using natural language, grounded in
Genie Ontology — without the agent needing to know table names, SQL syntax, or
metric definitions.
