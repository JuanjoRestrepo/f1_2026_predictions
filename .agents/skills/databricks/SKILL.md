---
name: databricks
description: >
  Expert-level Databricks Lakehouse skill: Lakeflow (Connect, Spark Declarative Pipelines,
  Jobs, Designer), cluster compute (Photon, instance pools, autoscaling), Unity Catalog
  (RBAC, row/column security, lineage, UC Metrics), Auto Loader, MLflow 3 and Feature Store,
  Databricks SQL and AI functions, DABs CI/CD, Delta performance (liquid clustering,
  Z-ordering, OPTIMIZE), Unity AI Gateway (budgets, smart routing, contextual policies,
  guardrails), Genie suite (One, Agents, Code, App Builder, ZeroOps, AI/BI), Genie Ontology,
  AgentBricks, Omnigent, Lakebase/LTAP, agent quality loop (MemAlign, GEPA). Trigger for:
  Databricks, DLT, Lakeflow, Unity Catalog, Workflows, Auto Loader, cloudFiles, MLflow,
  Mosaic AI, DABs, Photon, liquid clustering, OPTIMIZE, VACUUM, Unity AI Gateway, contextual
  policies, smart routing, Omnigent, Genie, AgentBricks, Lakebase, LTAP, ai_parse_document,
  MemAlign, GEPA, or any task involving building, deploying, governing, or optimizing on the
  Databricks Lakehouse.
---

# Databricks Platform Skill

Expert-level guidance for building, deploying, governing, and optimizing production data
engineering, ML, analytics, and agentic AI workloads on the Databricks Unified Analytics
Platform. Reflects announcements through Data + AI Summit 2026 (June 2026) including
Lakeflow GA, Unity AI Gateway GA, Genie Ontology, AgentBricks, Omnigent, and Lakebase.

Cross-reference `data-science-expert/references/data_engineering_advanced.md` for Medallion
Architecture layer design, Spark internals (DAG scheduler, wide vs narrow transformations,
memory model), and Delta Lake fundamentals (ACID transactions, time travel, MERGE, VACUUM).
This skill covers the Databricks-specific implementation layer above those foundations.

---

## How to Use This Skill

1. **Identify the concern** across three domains:
   - **Data Engineering**: ingestion (Lakeflow Connect / Auto Loader), transformation
     (Lakeflow Declarative Pipelines), orchestration (Lakeflow Jobs), compute (clusters),
     governance (Unity Catalog), CI/CD (DABs), performance (OPTIMIZE, liquid clustering)
   - **ML Lifecycle**: experiment tracking (MLflow 3), model registry, serving (Mosaic AI),
     Feature Store, agent quality (MemAlign, GEPA, AgentBricks)
   - **Agentic AI**: agent governance (Unity AI Gateway), budgets, smart routing, contextual
     policies, Genie suite, Omnigent, Lakebase, document intelligence
2. **Read the relevant reference file** — each covers one concern end-to-end with production
   templates. Cross-reference between files for cross-cutting tasks.
3. **State cluster type explicitly** in every design. All-purpose clusters cost ~3-4x job
   cluster rates. Production workloads run on job clusters or serverless compute.
4. **Unity Catalog is the governance baseline** for all data AND AI assets. Never recommend
   the legacy Hive Metastore for new implementations.
5. **Lakeflow is the current product name**: Delta Live Tables → Lakeflow Spark Declarative
   Pipelines; Databricks Workflows → Lakeflow Jobs. Code APIs (`import dlt`, `@dlt.table`)
   are unchanged. DABs YAML keys (`resources.pipelines`, `resources.jobs`) are unchanged.
6. **DABs for everything going to production** — any pipeline or job beyond interactive
   development requires a Databricks Asset Bundle with CI/CD. No manual UI deployments.
7. **Unity AI Gateway governs AI at runtime** — not just data access. Any production agent
   must route through Unity AI Gateway for spend caps, policy enforcement, and audit trails.

---

## Quick Decision Guide

### Data Engineering

| Situation | Guidance |
|---|---|
| Ingest from Salesforce, SAP, Workday, Stripe (100+ sources) | Lakeflow Connect |
| Ingest incrementally from S3/ADLS/GCS files | Auto Loader (`cloudFiles`) |
| Build Medallion ETL pipeline with data quality | Lakeflow Spark Declarative Pipelines |
| CDC / SCD Type 1 or 2 from operational DB | `dlt.apply_changes()` (AUTO CDC API) |
| Build a pipeline visually without writing Python | Lakeflow Designer |
| Orchestrate multi-step workflows (ETL → ML → report) | Lakeflow Jobs |
| Parse unstructured documents at scale (PDFs, contracts) | Document Intelligence (`ai_parse_document`) |
| Govern data access, lineage, and cross-workspace sharing | Unity Catalog |
| Deploy pipelines and jobs with CI/CD | Databricks Asset Bundles (DABs) |
| Compact files and enable data skipping | OPTIMIZE + liquid clustering (preferred on DBR 13.2+) |
| Vectorized CPU-bound SQL | Enable Photon on cluster or SQL Warehouse |
| Reduce cluster cold-start | Instance pools |

### ML and AI

| Situation | Guidance |
|---|---|
| Track ML experiments, benchmark GBMs | MLflow 3 (`mlflow.autolog()`) |
| Promote model to production | MLflow model registry with `@champion` alias |
| Deploy real-time ML inference endpoint | Mosaic AI Model Serving |
| Serve features to training and inference | Databricks Feature Store (any UC table with PK) |
| Build a domain-specific agent, auto-optimized | AgentBricks |
| Build RAG over enterprise unstructured data | AgentBricks Knowledge Assistant |
| Monitor agent quality in production | Agent quality loop: Capture → Judge → Align → Optimize |
| Calibrate LLM judge to your domain | MemAlign (~20 SME labels) |
| Auto-improve agent prompt from judge scores | GEPA |

### Agentic Platform and Governance

| Situation | Guidance |
|---|---|
| Govern AI spend across all models and tools | Unity AI Gateway Budgets + Smart Routing |
| Control what an agent can *do* (not just access) | Contextual Service Policies |
| Detect PII in prompts/responses | Unity AI Gateway guardrails |
| Audit all AI activity with SQL-queryable logs | Unity AI Gateway → UC audit tables |
| Route requests to optimal model by task/cost | Smart Routing (Unity AI Gateway) |
| Compose multiple coding agents (Claude Code + Codex) | Omnigent (meta-harness) |
| Provide business users with natural language data access | Genie ONE |
| Ground agents in company-specific business semantics | Genie Ontology + UC Metrics + Business Glossary |
| Build a data app without writing code | Genie App Builder |
| Background autonomous monitoring of Lakehouse health | Genie ZeroOps |
| Run OLTP and OLAP on the same data copy | Lakebase + LTAP |
| Store agent session memory (conversation history) | Lakebase (agent memory services) |
| Share data across organizations without copying | Delta Sharing |

---

## Platform Architecture (Four Layers — DAIS 2026)

```
Layer 4: AGENTIC APPS
  Genie ONE · Genie Agents · Genie Code · Genie App Builder · Genie ZeroOps · Genie AI/BI
  Omnigent (meta-harness) · Apps · Lakewatch · CustomerLake

Layer 3: UNIFIED GOVERNANCE
  Unity Catalog        — data assets: tables, files, volumes, models, metrics, glossary
  Unity AI Gateway     — AI runtime: models, agents, MCPs, skills, budgets, policies, tracing

Layer 2: AGENTIC DATA
  Lakeflow Connect    — managed ingestion (100+ connectors)
  Lakeflow Declarative Pipelines — ETL (formerly Delta Live Tables)
  Lakeflow Jobs       — orchestration (formerly Databricks Workflows)
  Lakeflow Designer   — no-code pipeline builder
  Lakehouse           — Delta Lake OLAP (structured + unstructured)
  Lakebase            — serverless Postgres OLTP + agent memory (LTAP architecture)

Layer 1: OPEN INFRASTRUCTURE
  Delta Lake · Apache Iceberg v3 · AnyCloud · AnyModel · AnyData
```

---

## Terminology Reference (Current as of DAIS 2026)

| Old name | Current name | Notes |
|---|---|---|
| Delta Live Tables (DLT) | Lakeflow Spark Declarative Pipelines | `import dlt` and all decorators unchanged |
| Databricks Workflows | Lakeflow Jobs | DABs YAML keys unchanged |
| (new) | Lakeflow Connect | Managed ingestion, 100+ connectors |
| (new) | Lakeflow Designer | No-code pipeline builder, outputs Python |
| Databricks Asset Bundles | Databricks Asset Bundles (DABs) | Name unchanged |
| MLflow (any version) | MLflow 3 | Redesigned for GenAI; use `mlflow[databricks]>=3.1` |
| Staging/Production stage transitions | `@champion` / `@challenger` aliases | Stage transitions deprecated in UC model registry |
| Feature Store (separate API) | UC table with PRIMARY KEY = Feature Store table | Simplified in DBR 14.x+ |
| (new) | Unity AI Gateway | Runtime governance for AI; GA August 2026 |
| (new) | Genie Ontology | Self-improving semantic context layer |
| (new) | Genie ONE | Agentic coworker; GA DAIS 2026 |
| (new) | Omnigent | Open-source meta-harness (Apache 2.0) |
| (new) | Lakebase | Serverless Postgres + LTAP |

---

## Sections

### Data Engineering

**1. Cluster and Compute Configuration**
All-purpose vs job clusters, Photon, Graviton2, instance pools, autoscaling, spot instances,
cluster policies, init scripts, runtime versions, serverless compute.
→ `references/cluster-compute.md`

**2. Lakeflow — Unified Data Engineering**
Lakeflow product architecture (Connect, Declarative Pipelines, Jobs, Designer), migration
from DLT/Workflows terminology, Spark Declarative Pipelines open standard, AUTO CDC API,
incremental materialized views, enhanced autoscaling, sinks, Lakeflow Designer output.
→ `references/lakeflow.md`

**3. Lakeflow Spark Declarative Pipelines (formerly DLT)**
Streaming tables vs materialized views, pipeline modes (triggered/continuous,
development/production), all four expectation levels, CDC via `dlt.apply_changes()`,
SCD Type 1 and 2, pipeline event monitoring, Unity Catalog integration.
→ `references/delta-live-tables.md`

**4. Unity Catalog**
Metastore architecture, three-level namespace, external locations, storage credentials,
managed vs external tables, RBAC (GRANT/REVOKE), row filters, column masks, automated
lineage, audit logging, Delta Sharing. Business Glossary, Domains, UC Metrics (feeds
Genie Ontology).
→ `references/unity-catalog.md`

**5. Lakeflow Jobs (formerly Workflows)**
Multi-task job DAGs, task types, task values, per-task clusters, repair runs, retry
policies, scheduling, notifications, real-time data triggers, file arrival triggers.
→ `references/workflows-jobs.md`

**6. Auto Loader (cloudFiles)**
Directory listing vs file notification mode, schema inference and evolution modes,
`_rescued_data` column, checkpointing, file formats, Auto Loader + DLT integration,
performance at billion-file scale.
→ `references/auto-loader.md`

**7. CI/CD with Databricks Asset Bundles (DABs)**
`bundle.yml` structure, resource definitions (jobs, pipelines, models, schemas, dashboards),
deployment targets (dev/staging/prod), variable substitution, GitHub Actions CI/CD,
Databricks Connect v2 for local testing, pytest testing strategy.
→ `references/cicd-dabs.md`

**8. Performance Optimization**
OPTIMIZE (file compaction), Z-Ordering, liquid clustering (preferred, DBR 13.2+, supersedes
partitioning + Z-Ordering), VACUUM, Delta cache, Photon, AQE, bloom filters, statistics
collection, write optimization, optimization scheduling.
→ `references/performance-optimization.md`

### ML Lifecycle

**9. MLflow 3 and Feature Store**
MLflow 3 overview (redesigned for GenAI), experiment tracking, autolog, UC model registry
with `@champion`/`@challenger` aliases, Mosaic AI Model Serving (A/B traffic splitting),
Feature Store (any UC table with PK = Feature Store), point-in-time training sets, batch
inference with automatic feature retrieval, agent quality loop (Capture → Judge → Align →
Optimize), MLflow tracing (OTEL-native), production monitoring.
→ `references/mlflow-feature-store.md`

### Analytics

**10. Databricks SQL**
SQL Warehouse types (Serverless/Pro/Classic), Photon, query editor and profiler, Lakeview
Dashboards, alerts, BI connectors (Power BI DirectQuery, Tableau, Looker), AI functions
(`ai_parse_document`, `ai_classify`, `ai_gen`, `ai_similarity`), model selection guidance,
SQL optimization on Delta Lake.
→ `references/databricks-sql.md`

### Agentic AI

**11. Agentic Platform — Unity AI Gateway and Agent Governance**
The four enterprise AI challenges (Context/Cost/Control/Choice), Model vs Harness
architecture, Unity AI Gateway (spend visibility, budgets, Smart Routing, Contextual
Service Policies, guardrails, audit logging), Omnigent (meta-harness, open-source
Apache 2.0), Document Intelligence, Lakebase (LTAP, serverless Postgres, agent memory),
platform four-layer architecture.
→ `references/agentic-platform.md`

**12. Genie Ontology, Genie Suite, and AgentBricks**
Genie Ontology (self-improving semantic context layer, UC Metrics, Business Glossary,
Domains), Genie ONE, Genie Agents, Genie Code, Genie App Builder, Genie ZeroOps, Genie
AI/BI, AgentBricks (Knowledge Assistant RAG, auto-optimization, supported frameworks,
model choice), agent quality loop detail (MemAlign, GEPA, AgentBricks Quality online
monitoring), MLflow 3 integration, Genie MCP access points.
→ `references/genie-ontology.md`

---

## Cross-Skill Boundaries

| Topic | Where to look |
|---|---|
| Medallion Architecture — Bronze/Silver/Gold design | `data-science-expert/references/data_engineering_advanced.md` §1 |
| Spark internals — DAG, shuffles, AQE, memory model | `data-science-expert/references/data_engineering_advanced.md` §3 |
| Delta Lake fundamentals — ACID, time travel, MERGE | `data-science-expert/references/data_formats.md` |
| dbt project structure, models, snapshots, Semantic Layer | `data-science-expert/references/analytics_engineering.md` |
| Kafka / Event Hubs / streaming architecture decisions | `data-science-expert/references/data_engineering_advanced.md` §10 |
| Python standards — type hints, Ruff/mypy, pyproject.toml | `data-science-expert` SKILL.md §Python Code Standards |
| API-level integrations — OAuth2, retries, circuit breakers | `api-engineering` SKILL.md |
| GBM benchmark (XGBoost/LightGBM/CatBoost) | `data-science-expert/references/gradient_boosting_benchmark.md` |

---

## Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Unity Catalog catalog | `{env}_{domain}` | `prod_sales`, `dev_marketing` |
| Unity Catalog schema | `{layer}_{subject}` | `bronze_orders`, `gold_revenue` |
| Delta tables | `snake_case` | `silver_customer_events` |
| DLT pipeline functions | `snake_case` (no prefix clash with `@dlt.table`) | `silver_orders`, `gold_daily_revenue` |
| MLflow experiment | `/Shared/{team}/{project}` | `/Shared/churn-model/gbm-benchmark` |
| MLflow registered model | `{catalog}.{schema}.{model_name}` | `prod_sales.ml.churn_classifier` |
| Job / pipeline names | `[{ENV}] {Name}` | `[PROD] Orders Medallion` |
| Bundle target | `dev`, `staging`, `prod` (lowercase) | — |
| Cluster policy | `{team}_{workload}` | `de_job_cluster`, `ml_interactive` |
| Unity AI Gateway endpoint | `{team}-ai-gateway` | `data-engineering-ai-gateway` |
| Agent / model in registry | `{catalog}.agents.{name}` | `prod_finance.agents.invoice_extractor` |

---

## Reference Files

**Data Engineering**
- `references/cluster-compute.md` — Cluster types, Photon, instance pools, autoscaling, spot, policies, init scripts
- `references/lakeflow.md` — Lakeflow GA: Connect, Declarative Pipelines, Jobs, Designer; terminology migration
- `references/delta-live-tables.md` — DLT/Lakeflow pipeline API, expectations, CDC/SCD, pipeline modes, event monitoring
- `references/unity-catalog.md` — Metastore, RBAC, row/column security, lineage API, UC Metrics, Delta Sharing
- `references/workflows-jobs.md` — Multi-task job DAGs, task types, task values, repair runs, notifications
- `references/auto-loader.md` — cloudFiles, schema evolution, file notification mode, rescued data, checkpointing
- `references/cicd-dabs.md` — bundle.yml, targets, GitHub Actions, Databricks Connect v2, deployment workflow
- `references/performance-optimization.md` — OPTIMIZE, liquid clustering, Z-Ordering, VACUUM, Photon, Delta cache

**ML Lifecycle**
- `references/mlflow-feature-store.md` — MLflow 3, model registry (aliases), Mosaic AI serving, Feature Store, quality loop

**Analytics**
- `references/databricks-sql.md` — Warehouse types, Lakeview, BI connectors, AI functions (ai_parse_document), optimization

**Agentic AI**
- `references/agentic-platform.md` — Unity AI Gateway, Model vs Harness, budgets, smart routing, contextual policies, Omnigent, Lakebase
- `references/genie-ontology.md` — Genie Ontology, Genie suite (ONE/Agents/Code/App Builder/ZeroOps/AI/BI), AgentBricks, quality loop detail
