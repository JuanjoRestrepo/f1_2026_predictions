# Lakeflow

> **Sources**: Databricks Lakeflow GA Announcement.
> https://www.databricks.com/blog/announcing-general-availability-databricks-lakeflow
> Lakeflow Declarative Pipelines (AWS). https://docs.databricks.com/aws/en/ldp/
> Apache Spark Declarative Pipelines. https://docs.databricks.com/aws/en/ldp/
> Lakeflow Connect. https://docs.databricks.com/en/ingestion/managed-ingestion/index.html
> Data + AI Summit 2025 keynote.

## Table of Contents

1. [What Lakeflow Is](#overview)
2. [Lakeflow Connect — Managed Ingestion](#connect)
3. [Lakeflow Spark Declarative Pipelines (formerly DLT)](#declarative)
4. [Lakeflow Jobs (formerly Workflows)](#jobs)
5. [Lakeflow Designer — No-Code Pipeline Builder](#designer)
6. [Lakeflow vs Individual Components](#comparison)
7. [Migration: DLT and Workflows Terminology Update](#migration)

---

## 1. What Lakeflow Is {#overview}

Lakeflow is Databricks's unified data engineering product, announced at Data + AI Summit
2025 and GA. It consolidates three previously separate Databricks capabilities under a
single product name and unified experience:

```
Lakeflow
├── Connect          — Managed ingestion: 100+ enterprise connectors
├── Declarative Pipelines — ETL transformation (previously Delta Live Tables / DLT)
└── Jobs             — Orchestration (previously Databricks Workflows)
         └── Designer — AI-powered no-code pipeline builder (on top of Declarative Pipelines)
```

**Why the consolidation**: before Lakeflow, teams stitched together separate tools for
ingestion (Fivetran, Airbyte, custom Auto Loader scripts), transformation (DLT, dbt,
manual PySpark), and orchestration (Databricks Workflows, Airflow). Lakeflow provides
an integrated end-to-end experience with unified observability, governance (Unity Catalog),
and a single operational surface.

**Terminology mapping** (official, from Databricks):

| Old name | New name |
|---|---|
| Delta Live Tables (DLT) | Lakeflow Spark Declarative Pipelines |
| Databricks Workflows | Lakeflow Jobs |
| (new) | Lakeflow Connect |
| (new) | Lakeflow Designer |

Both old and new names appear in documentation. In practice, the APIs and Python decorators
are unchanged — `import dlt` and `@dlt.table` are still the correct Python imports for
Lakeflow Spark Declarative Pipelines.

---

## 2. Lakeflow Connect — Managed Ingestion {#connect}

Lakeflow Connect provides 100+ managed, no-code connectors for popular enterprise data
sources. It replaces the need for third-party ingestion tools (Fivetran, Stitch, Airbyte)
for supported sources, with data governed natively in Unity Catalog.

**Source categories**:

| Category | Examples |
|---|---|
| Enterprise applications | Salesforce, ServiceNow, Workday, SAP, HubSpot, Zendesk |
| Databases (JDBC-based) | MySQL, PostgreSQL, SQL Server, Oracle, Snowflake |
| File systems | S3, ADLS Gen2, GCS (via managed Auto Loader) |
| Real-time streams | Apache Kafka, Amazon Kinesis, Azure Event Hub, Google Pub/Sub |
| SaaS / APIs | Stripe, Shopify, Google Analytics, Meta Ads, LinkedIn Ads |

**Key properties of Lakeflow Connect**:
- No infrastructure to manage — fully managed by Databricks
- Incremental and CDC-aware connectors (database connectors use log-based CDC where
  the source supports it)
- Unity Catalog governance applies immediately on ingested data
- Lineage captured automatically from source through to target Delta tables
- Scheduling and monitoring via Lakeflow Jobs (unified pipeline observability)

**Setting up a Lakeflow Connect connector**:

```
1. In the Databricks workspace: Ingestion → Add connection
2. Select connector (e.g., Salesforce)
3. Configure authentication (OAuth, API key, service account)
4. Select objects/tables to ingest
5. Set target catalog and schema (Unity Catalog)
6. Configure schedule (cron or continuous)
7. Monitor via Lakeflow Jobs observability
```

**When to use Lakeflow Connect vs Auto Loader**:

| Scenario | Use |
|---|---|
| Source is a supported enterprise app or SaaS | Lakeflow Connect |
| Source is cloud object storage (S3/ADLS/GCS) with custom files | Auto Loader (`cloudFiles`) |
| Source is a database not in Connect's catalog | Auto Loader + JDBC or Debezium CDC |
| Custom connector needed | Auto Loader or manual PySpark with JDBC |

---

## 3. Lakeflow Spark Declarative Pipelines (formerly DLT) {#declarative}

Lakeflow Spark Declarative Pipelines is the new official name for Delta Live Tables.
Built on the open-source **Apache Spark™ Declarative Pipelines (SDP)** standard, it
provides the Databricks-specific extensions on top of the open standard.

**Open standard compatibility**: Lakeflow Declarative Pipelines extend and are fully
interoperable with Apache Spark Declarative Pipelines. Code written to the open standard
runs on Databricks without modification.

**Databricks-specific extensions over the open standard**:

| Feature | Open SDP | Lakeflow (Databricks) |
|---|---|---|
| Basic streaming tables | Yes | Yes |
| Materialized views | Yes | Yes |
| Expectations | Yes | Yes — plus `expect_or_quarantine` |
| AUTO CDC API (SCD 1/2) | No | Yes |
| Unity Catalog integration | No | Yes |
| Enhanced auto-scaling | No | Yes |
| Pipeline monitoring dashboard | No | Yes |
| Lakeflow Designer (no-code) | No | Yes |

### Key New Features in Lakeflow Declarative Pipelines

**AUTO CDC API**: the simplest way to handle SCD Type 1 and Type 2 without manual
watermark logic or out-of-order event handling:

```python
import dlt
from pyspark.sql import functions as F

# Lakeflow's AUTO CDC API — replaces dlt.apply_changes() for common patterns
# Handles: out-of-order events, SCD 1/2, delete markers — automatically

@dlt.table
def bronze_customer_cdc():
    """Raw CDC events from source database via Lakeflow Connect."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("s3://raw/cdc/customers/")
    )


# SCD Type 1 upsert — most concise form
dlt.apply_changes(
    target="silver_customers",
    source="bronze_customer_cdc",
    keys=["customer_id"],
    sequence_by="ts_ms",
    apply_as_deletes=F.expr("op = 'D'"),
    stored_as_scd_type="1",
)

# SCD Type 2 with full history
dlt.apply_changes(
    target="silver_customers_history",
    source="bronze_customer_cdc",
    keys=["customer_id"],
    sequence_by="ts_ms",
    apply_as_deletes=F.expr("op = 'D'"),
    stored_as_scd_type="2",
    # Adds __START_AT and __END_AT columns automatically
)
```

**Enhanced Auto-Scaling**: Lakeflow Declarative Pipelines use a specialized autoscaling
strategy that scales down more aggressively than standard Spark autoscaling. Nodes are
removed based on task queue depth and slot utilization ratio, not idle time. On by default
for new pipelines:

```yaml
# DABs pipeline config: explicitly set scaling mode
resources:
  pipelines:
    orders_medallion:
      clusters:
        - label: default
          autoscale:
            min_workers: 1
            max_workers: 20
            mode: ENHANCED     # ENHANCED (default) or LEGACY
```

**Incremental processing engine for materialized views**: Gold layer aggregations
(materialized views) are now incrementally updated — the engine rewrites only the portion
of the materialized view affected by new source data, not the full view:

```python
import dlt
from pyspark.sql import functions as F


@dlt.materialized_view(    # explicit materialized_view decorator (alias for @dlt.table with batch read)
    comment="Daily revenue — incrementally maintained as new Silver orders arrive.",
    table_properties={"quality": "gold"},
)
def gold_daily_revenue():
    """
    Incrementally updated daily revenue aggregation.

    The Lakeflow incremental processing engine rewrites only the date partitions
    affected by newly arrived Silver records, not the entire Gold table.
    """
    return (
        dlt.read("silver_orders")
        .groupBy(F.to_date("order_date").alias("order_date"), "region")
        .agg(
            F.sum("amount").alias("total_revenue"),
            F.count("order_id").alias("order_count"),
        )
    )
```

**Sinks (new in Lakeflow Declarative Pipelines)**: write pipeline output to external
systems (Kafka, Event Hub) in addition to Delta tables:

```python
import dlt
from pyspark.sql import functions as F


@dlt.table
def silver_order_events():
    return dlt.read_stream("bronze_orders").filter(F.col("amount") > 1000)


# Publish high-value order events to Kafka
dlt.create_sink(
    name="high_value_orders_kafka",
    format="kafka",
    options={
        "kafka.bootstrap.servers": "kafka.company.com:9092",
        "topic": "high-value-orders",
    },
)
```

---

## 4. Lakeflow Jobs (formerly Workflows) {#jobs}

Lakeflow Jobs is the new official name for Databricks Workflows. All capabilities,
APIs, and DABs YAML syntax from `references/workflows-jobs.md` apply unchanged — only
the product name changed.

**New capabilities added in the Lakeflow rebranding**:

**Real-time data triggers**: trigger a Lakeflow Job on new data arrival without polling:

```yaml
# File arrival trigger (continuous monitoring)
trigger:
  file_arrival:
    url: "s3://raw-data/orders/"
    min_time_between_triggers_seconds: 60

# Table trigger: trigger when a Delta table receives new data
trigger:
  table:
    table_name: "prod_sales.orders.silver_orders"
    condition: "1=1"   # or a specific partition condition
    min_time_between_triggers_seconds: 300
```

**End-to-end observability dashboard**: Lakeflow Jobs provides a unified pipeline health
view showing: task latency trends, failure rates, cost per run, and data freshness
metrics. Accessible in the Lakeflow Jobs UI → Pipeline Health.

**Advanced control flow**:

```yaml
# Conditional task execution (run_if)
tasks:
  - task_key: validate_data
    ...

  - task_key: send_failure_alert
    depends_on:
      - task_key: validate_data
        outcome: FAILED             # run only if validate_data failed
    notification_task:
      email: "de-team@company.com"
      subject: "Data validation failed for ${run_id}"
```

---

## 5. Lakeflow Designer — No-Code Pipeline Builder {#designer}

Lakeflow Designer is an AI-powered visual pipeline builder for non-developers and for
rapid pipeline prototyping. Key design principles:

- **No-code interface**: drag-and-drop data sources, transformations, and targets to
  compose a Medallion pipeline visually.
- **Production-grade output**: the resulting "boxes" in the visual canvas generate real
  Python code (Lakeflow Spark Declarative Pipelines / `@dlt.table` functions) — not a
  proprietary DSL. The generated code is reviewable, editable, and versionable in Git.
- **Genie Code integration**: natural language instructions in Lakeflow Designer call
  Genie Code to generate transformation logic, which is then embedded in the pipeline
  function.
- **Unity Catalog aware**: sources and targets are selected from the Unity Catalog
  browser, enforcing governance from pipeline creation.

**Designer workflow**:

```
1. Open Lakeflow Designer (Databricks workspace → Lakeflow → Designer)
2. Add a source (Lakeflow Connect connector or Delta table)
3. Add transformation steps (filter, join, aggregate, AI transform via Genie Code)
4. Set the target (Unity Catalog table path)
5. Review generated Python code
6. Deploy as a Lakeflow Spark Declarative Pipelines pipeline
7. Monitor via Lakeflow Jobs observability
```

**When to use Lakeflow Designer**:
- Rapid prototyping of a new Medallion pipeline before formalizing in code
- Non-engineer data analysts building curated Gold tables from Silver
- Generating a pipeline skeleton that will be refined by engineers in code

**When not to use Lakeflow Designer**:
- Complex transformation logic requiring full Python control (use hand-written
  `@dlt.table` functions instead)
- Pipelines requiring conditional logic, loops, or programmatic DAG construction
- Enterprise CI/CD workflows — Designer outputs code that should be committed to Git
  and deployed via DABs, not managed directly in the Designer canvas

---

## 6. Lakeflow vs Individual Components {#comparison}

| Scenario | Recommended approach |
|---|---|
| Ingest from Salesforce, SAP, or other enterprise SaaS | Lakeflow Connect |
| Ingest from S3/ADLS/GCS files | Auto Loader (`cloudFiles`) in Lakeflow Declarative Pipelines |
| Build Medallion ETL with data quality and CDC | Lakeflow Spark Declarative Pipelines |
| Orchestrate Medallion → ML → report as a DAG | Lakeflow Jobs |
| Build a pipeline without writing Python | Lakeflow Designer |
| Mix Databricks with non-Databricks systems in one DAG | Airflow + Databricks operators |
| Full observability across the entire Lakehouse pipeline | Lakeflow unified monitoring dashboard |

---

## 7. Migration: DLT and Workflows Terminology Update {#migration}

All existing DLT pipelines and Databricks Workflows are automatically available as
Lakeflow Declarative Pipelines and Lakeflow Jobs respectively. No migration steps are
required — the rename is product-level only.

**Code impact**: none. The following are all still correct:
- `import dlt`
- `@dlt.table`, `@dlt.view`, `@dlt.expect`, `dlt.apply_changes()`
- `dlt.read()`, `dlt.read_stream()`
- Existing DABs `resources.pipelines` and `resources.jobs` YAML keys

**Documentation impact**: Databricks documentation uses both names during the transition.
"Lakeflow pipelines" and "Delta Live Tables" may appear on the same documentation page.
When in doubt, the official current name is "Lakeflow Spark Declarative Pipelines" (or
simply "Lakeflow pipelines" in shorthand). "Lakeflow Jobs" = "Databricks Workflows".

**Note on Apache Spark Declarative Pipelines (SDP)**: the open-source standard that
Lakeflow builds on. Code compatible with SDP runs on Databricks without modification,
but Databricks-specific extensions (`expect_or_quarantine`, Unity Catalog integration,
AUTO CDC API) require Databricks Runtime.
