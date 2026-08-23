# Delta Live Tables (DLT)

> **Sources**: Databricks DLT Documentation. https://docs.databricks.com/en/delta-live-tables/index.html
> Delta Live Tables API Reference. https://docs.databricks.com/en/delta-live-tables/python-ref.html
> Apply Changes API (CDC). https://docs.databricks.com/en/delta-live-tables/cdc.html

## Table of Contents

1. [Core Concepts](#concepts)
2. [Table Types: Streaming Tables vs Materialized Views](#table-types)
3. [Pipeline Modes](#modes)
4. [Expectations — All Four Levels](#expectations)
5. [CDC via apply_changes()](#cdc)
6. [SCD Type 2 in DLT](#scd2)
7. [Auto Loader Integration](#autoloader)
8. [Unity Catalog Integration](#unity-catalog)
9. [Pipeline Monitoring and Events API](#monitoring)
10. [Full Medallion Pipeline Template](#template)

---

## 1. Core Concepts {#concepts}

DLT is a declarative ETL framework layered over Spark Structured Streaming. Instead of
writing imperative Spark code to manage state, checkpoints, and schema evolution, the
developer declares *what* each dataset should contain using Python decorators or SQL
`CREATE OR REFRESH` statements. DLT handles execution order, dependency resolution,
incremental processing, checkpointing, retries, and data quality enforcement.

**Key terminology**:

| Term | Definition |
|---|---|
| **Pipeline** | The unit of deployment. One pipeline contains one or more notebooks/files defining datasets. |
| **Dataset** | A streaming table or materialized view defined by a DLT decorator. |
| **Expectation** | A data quality rule attached to a dataset. Determines whether violations block, drop, or quarantine records. |
| **Flow** | An internal DAG edge — the data flow from one dataset to another. |
| **Update** | A single execution of the pipeline (equivalent to a DAG run in Airflow). |

**DLT vs manual PySpark Structured Streaming**:

| Concern | DLT | Manual Structured Streaming |
|---|---|---|
| Checkpoint management | Automatic | Manual (`checkpointLocation`) |
| Schema evolution | Automatic with `mergeSchema` | Manual |
| Data quality enforcement | Built-in via expectations | Custom logic |
| Dependency ordering | Automatic DAG resolution | Manual orchestration |
| Medallion pattern | First-class citizen | Boilerplate |
| Programmatic DAG construction | Not supported | Full flexibility |

**When to choose manual PySpark**: when the pipeline logic requires runtime-determined
dataset counts (e.g., fan-out over a dynamic list of tables), complex stateful operations
beyond DLT's model, or tight integration with non-Delta outputs.

---

## 2. Table Types: Streaming Tables vs Materialized Views {#table-types}

| Type | Processing model | Source requirement | Incremental? | Typical use |
|---|---|---|---|---|
| **Streaming Table** (`@dlt.table` with streaming source) | Processes only new records since last checkpoint. | Append-only source (Auto Loader, Kafka, another streaming table). | Yes — append-only. | Bronze and Silver layers ingesting live or batch-file sources. |
| **Materialized View** (`@dlt.table` with batch read or `dlt.read()`) | Full recompute on each pipeline update, or incremental if DLT can derive it. | Any — Delta table, streaming table, or external source. | Partial — DLT optimizes where possible. | Gold aggregations, joins, and transformations that do not have append-only semantics. |

**Practical rule**: use streaming tables for Bronze and Silver; use materialized views for
Gold aggregations. Mixing streaming tables with non-append sources in a single `@dlt.table`
raises a runtime error — use `dlt.read()` (batch) or `dlt.read_stream()` (streaming)
explicitly to match the source type.

---

## 3. Pipeline Modes {#modes}

### Triggered vs Continuous

| Mode | Behavior | Suitable for |
|---|---|---|
| **Triggered** | Processes all available new data, then stops. Compute terminates after the update. | Scheduled ETL (hourly, daily), cost-sensitive workloads. |
| **Continuous** | Runs indefinitely; processes data as it arrives with low latency (seconds). Compute stays live. | Near-real-time streaming pipelines requiring < 1 minute latency. |

### Development vs Production

| Mode | Behavior | Purpose |
|---|---|---|
| **Development** | Reuses the existing cluster across pipeline runs (avoids 2-5 min cluster startup). Errors surface immediately — pipeline does not retry on failure. | Fast iteration during pipeline authoring. |
| **Production** | Creates a new cluster per update (job cluster isolation). Retries on failure per retry policy. | All deployed pipelines. |

---

## 4. Expectations — All Four Levels {#expectations}

Expectations are data quality rules applied per dataset. Each level defines the action taken
when a record violates the rule.

| Decorator | Violation action | Row fate | Pipeline fate | Use case |
|---|---|---|---|---|
| `@dlt.expect("name", "condition")` | Metric logged to event log. | Passes through. | Continues. | Soft monitoring — track quality without blocking. |
| `@dlt.expect_or_drop("name", "condition")` | Metric logged; row dropped. | Removed from output. | Continues. | Filter out known noise or null records that must not propagate to Silver. |
| `@dlt.expect_or_fail("name", "condition")` | Metric logged; pipeline fails. | N/A — pipeline stops. | Fails immediately. | Critical business rules — a violation means the source data is corrupt and downstream tables must not be written. |
| `@dlt.expect_or_quarantine("name", "condition")` | Invalid rows routed to a quarantine table. Valid rows continue. | Split: valid → target, invalid → quarantine. | Continues. | Gold standard for Silver — preserves all data, separates invalid records for triage without blocking the pipeline. |

```python
import dlt
from pyspark.sql import functions as F


@dlt.table(
    comment="Silver orders: typed, deduplicated, with quarantine for invalid records.",
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
@dlt.expect_or_fail("non_null_order_id", "order_id IS NOT NULL")
@dlt.expect_or_quarantine("valid_amount", "amount >= 0.0")
@dlt.expect("valid_region", "region IN ('APAC', 'EMEA', 'AMER', 'LATAM')")
def silver_orders() -> "DataFrame":
    """
    Silver layer for the orders entity.

    Reads from bronze_orders streaming table. Applies type coercion,
    deduplication, and three-tier data quality rules.

    Returns:
        Streaming DataFrame of validated orders.
    """
    return (
        dlt.read_stream("bronze_orders")
        .withColumn("order_date", F.to_date("order_date", "yyyy-MM-dd"))
        .withColumn("amount", F.col("amount").cast("double"))
        .dropDuplicates(["order_id"])
    )
```

**Expectation naming convention**: `<adjective>_<field>` — e.g., `non_null_order_id`,
`valid_amount`, `valid_region`. Names appear in the DLT event log and pipeline monitoring UI.

---

## 5. CDC via apply_changes() {#cdc}

`dlt.apply_changes()` processes Change Data Capture (CDC) events from a source (e.g.,
Debezium-formatted Kafka/Event Hub stream, or a Bronze table with `op` column) into a
target Delta table, applying inserts, updates, and deletes correctly — including out-of-order
event handling via a sequence column.

```python
import dlt
from pyspark.sql import functions as F


@dlt.table(
    comment="Bronze CDC events from Debezium — raw operation log, append-only.",
    table_properties={"quality": "bronze"},
)
def bronze_customer_cdc() -> "DataFrame":
    """
    Ingests raw CDC events from the customers source table.

    The Debezium payload includes: op (I/U/D), before, after, ts_ms.

    Returns:
        Streaming DataFrame of raw CDC events.
    """
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load("s3://raw-data/cdc/customers/")
    )


# SCD Type 1 (last-write-wins upsert — no history retained)
dlt.apply_changes(
    target="silver_customers",
    source="bronze_customer_cdc",
    keys=["customer_id"],                          # natural key(s) for merge
    sequence_by=F.col("ts_ms"),                    # order events; latest wins on conflict
    apply_as_deletes=F.expr("op = 'D'"),           # delete marker condition
    apply_as_truncates=F.expr("op = 'T'"),         # optional: full truncate event
    except_column_list=["op", "ts_ms", "_rescued_data"],  # columns to exclude from target
    stored_as_scd_type="1",
)
```

**apply_changes() parameters**:

| Parameter | Description |
|---|---|
| `target` | Name of the target DLT streaming table (created automatically). |
| `source` | Name of the source streaming table feeding CDC events. |
| `keys` | Column(s) forming the natural key for merge operations. |
| `sequence_by` | Column used to order events. Out-of-order events with a lower sequence value than the current max are ignored. |
| `apply_as_deletes` | Spark expression evaluating to `True` for delete events. |
| `apply_as_truncates` | Spark expression for full-table truncate events (optional). |
| `except_column_list` | Columns to exclude from the target (metadata columns). |
| `stored_as_scd_type` | `"1"` for Type 1 upsert; `"2"` for Type 2 history. |

---

## 6. SCD Type 2 in DLT {#scd2}

SCD Type 2 retains full history: each change creates a new row with `__START_AT` and
`__END_AT` columns tracking the validity period.

```python
# SCD Type 2 — retains full change history per customer_id
dlt.apply_changes(
    target="silver_customers_scd2",
    source="bronze_customer_cdc",
    keys=["customer_id"],
    sequence_by=F.col("ts_ms"),
    apply_as_deletes=F.expr("op = 'D'"),
    stored_as_scd_type="2",
    # DLT automatically adds __START_AT (bigint) and __END_AT (bigint) columns.
    # __END_AT is NULL for the current active row.
)
```

**Querying SCD Type 2 tables**:

```sql
-- Current active records only
SELECT * FROM catalog.silver.silver_customers_scd2
WHERE __END_AT IS NULL;

-- Point-in-time snapshot at a specific event timestamp
SELECT * FROM catalog.silver.silver_customers_scd2
WHERE __START_AT <= 1704067200000   -- Unix ms timestamp
  AND (__END_AT > 1704067200000 OR __END_AT IS NULL);
```

---

## 7. Auto Loader Integration {#autoloader}

Auto Loader is the standard Bronze ingestion source for file-based data in DLT. The
`cloudFiles` format provides incremental, fault-tolerant ingestion without explicit file
list management.

```python
import dlt
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType


# Explicit schema preferred over inference in production (prevents schema drift surprises)
ORDER_SCHEMA = StructType([
    StructField("order_id",   StringType(),    nullable=False),
    StructField("customer_id",StringType(),    nullable=False),
    StructField("amount",     DoubleType(),    nullable=True),
    StructField("order_date", TimestampType(), nullable=True),
    StructField("region",     StringType(),    nullable=True),
])


@dlt.table(
    comment="Bronze orders: raw ingestion from S3 via Auto Loader. Append-only.",
    table_properties={"quality": "bronze", "delta.enableChangeDataFeed": "true"},
    partition_cols=["region"],
)
def bronze_orders() -> "DataFrame":
    """
    Ingests order JSON files from S3 incrementally using Auto Loader.

    Appends _ingested_at and _source_file metadata columns for lineage.
    Uses file notification mode (SQS) for scale > 10M files.

    Returns:
        Streaming DataFrame of raw order records.
    """
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", "/Volumes/prod_infra/checkpoints/bronze_orders/schema")
        .option("cloudFiles.includeExistingFiles", "true")
        .option("cloudFiles.validateOptions", "true")
        .schema(ORDER_SCHEMA)
        .load("s3://raw-data/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.input_file_name())
    )
```

---

## 8. Unity Catalog Integration {#unity-catalog}

DLT pipelines publish tables to Unity Catalog by setting the `catalog` and `target` in the
pipeline configuration. Tables become queryable as `catalog.schema.table` immediately after
the first pipeline update.

```json
// Pipeline configuration (via Databricks UI, REST API, or DABs)
{
  "name": "[PROD] Orders Medallion",
  "catalog": "prod_sales",
  "target": "orders",
  "configuration": {
    "pipelines.enableTrackHistory": "true"
  },
  "clusters": [{"label": "default", "num_workers": 4}],
  "libraries": [{"notebook": {"path": "/pipelines/orders/bronze"}},
                {"notebook": {"path": "/pipelines/orders/silver"}},
                {"notebook": {"path": "/pipelines/orders/gold"}}]
}
```

**Table access after DLT publishing**: tables are governed by Unity Catalog permissions.
Grant access using standard `GRANT` SQL on the published tables — DLT does not require
special permissions beyond write access to the target schema.

---

## 9. Pipeline Monitoring and Events API {#monitoring}

DLT emits structured events to the pipeline event log, queryable as a Delta table at
`{storage_location}/system/events` or via the Events API.

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.getActiveSession()

# Query DLT event log for a specific pipeline
events = (
    spark.read.format("delta")
    .load("/pipelines/orders-medallion/system/events")
    .select(
        "timestamp",
        "event_type",
        "level",
        F.col("details.flow_progress.data_quality").alias("data_quality"),
        F.col("details.flow_progress.metrics").alias("metrics"),
    )
)

# Filter for data quality violations across all expectations
quality_failures = events.filter(
    (F.col("event_type") == "flow_progress")
    & (F.col("data_quality.dropped_records") > 0)
)

# Aggregated quality report
quality_report = (
    events
    .filter(F.col("event_type") == "flow_progress")
    .select(
        "timestamp",
        F.explode("data_quality.expectations").alias("expectation"),
    )
    .select(
        "timestamp",
        F.col("expectation.name").alias("expectation_name"),
        F.col("expectation.passed_records").alias("passed"),
        F.col("expectation.failed_records").alias("failed"),
    )
)
```

**Key event types**:

| event_type | Meaning |
|---|---|
| `update_progress` | Pipeline-level status changes (RUNNING, COMPLETED, FAILED). |
| `flow_progress` | Per-dataset status. Contains `metrics` (rows written) and `data_quality` (expectation results). |
| `maintenance_progress` | OPTIMIZE and VACUUM operations triggered automatically by DLT. |
| `create_update` | Triggered when a new pipeline update starts. |

---

## 10. Full Medallion Pipeline Template {#template}

```python
"""
orders_pipeline.py — Complete Medallion pipeline for the orders entity.

Deploy as a DLT pipeline with:
  catalog:  prod_sales
  target:   orders
  mode:     triggered (scheduled hourly)
"""
from __future__ import annotations

import dlt
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import (
    DoubleType, StringType, StructField, StructType, TimestampType,
)

# ---------- Schema ----------
ORDER_SCHEMA = StructType([
    StructField("order_id",    StringType(),    nullable=False),
    StructField("customer_id", StringType(),    nullable=False),
    StructField("amount",      DoubleType(),    nullable=True),
    StructField("order_date",  TimestampType(), nullable=True),
    StructField("region",      StringType(),    nullable=True),
])

VALID_REGIONS: list[str] = ["APAC", "EMEA", "AMER", "LATAM"]


# ---------- Bronze ----------
@dlt.table(
    comment="Raw orders from S3. Append-only, no transformations.",
    table_properties={"quality": "bronze", "delta.enableChangeDataFeed": "true"},
)
def bronze_orders() -> DataFrame:
    """Ingests order JSON files via Auto Loader (cloudFiles)."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation",
                "/Volumes/prod_infra/checkpoints/bronze_orders/schema")
        .schema(ORDER_SCHEMA)
        .load("s3://raw-data/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.input_file_name())
    )


# ---------- Silver ----------
@dlt.table(
    comment="Validated, deduplicated orders. Quarantines negative amounts.",
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
@dlt.expect_or_fail("non_null_order_id", "order_id IS NOT NULL")
@dlt.expect_or_quarantine("valid_amount", "amount >= 0.0")
@dlt.expect("valid_region",
            f"region IN ({', '.join(repr(r) for r in VALID_REGIONS)})")
def silver_orders() -> DataFrame:
    """Cleans and validates bronze_orders for Gold consumption."""
    return (
        dlt.read_stream("bronze_orders")
        .withColumn("order_date", F.to_date("order_date"))
        .withColumn("amount", F.col("amount").cast("double"))
        .dropDuplicates(["order_id"])
        .drop("_ingested_at", "_source_file")    # strip Bronze metadata
    )


# ---------- Gold ----------
@dlt.table(
    comment="Daily revenue by region. Business-ready for BI and reporting.",
    table_properties={"quality": "gold"},
    partition_cols=["order_date"],
)
def gold_daily_revenue() -> DataFrame:
    """Aggregates silver_orders into daily revenue KPIs."""
    return (
        dlt.read("silver_orders")              # batch read — Gold is a materialized view
        .groupBy(F.to_date("order_date").alias("order_date"), "region")
        .agg(
            F.sum("amount").alias("total_revenue"),
            F.count("order_id").alias("order_count"),
            F.avg("amount").alias("avg_order_value"),
            F.countDistinct("customer_id").alias("unique_customers"),
        )
    )
```
