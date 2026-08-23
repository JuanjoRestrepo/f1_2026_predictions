# Advanced Data Engineering Reference

> **References**: Reis, J., & Housley, M. (2022). _Fundamentals of Data Engineering_.
> O'Reilly. · Dehghani, Z. (2022). _Data Mesh_. O'Reilly. · Kleppmann, M. (2017).
> _Designing Data-Intensive Applications_. O'Reilly. · Kimball, R., & Ross, M. (2013).
> _The Data Warehouse Toolkit_ (3rd ed.). Wiley. · Delta Lake Documentation.
> https://docs.delta.io · Apache Kafka Documentation. https://kafka.apache.org/documentation
> · Databricks Documentation. https://docs.databricks.com · Microsoft Azure Event Hubs.
> https://learn.microsoft.com/en-us/azure/event-hubs · Apache Spark Documentation.
> https://spark.apache.org/docs/latest · dbt Labs Documentation. https://docs.getdbt.com

## Table of Contents

1. [Medallion Architecture — Depth Reference](#medallion)
2. [Batch vs. Streaming — Architecture Decision](#batch-streaming)
3. [Apache Spark — Architecture and Internals](#spark)
4. [Databricks — Platform Reference](#databricks)
5. [Delta Lake — Beyond the Basics](#delta-lake)
6. [Lakehouse Architecture](#lakehouse)
7. [Change Data Capture (CDC)](#cdc)
8. [Data Contracts](#data-contracts)
9. [Data Lineage](#data-lineage)
10. [Apache Kafka and Azure Event Hubs](#kafka-eventhubs)
11. [Data Mesh](#data-mesh)
12. [Data Fabric](#data-fabric)
13. [Data Observability](#observability)
14. [References](#references)

---

## 1. Medallion Architecture — Depth Reference {#medallion}

> **Source**: Databricks (2021). _The Medallion Architecture_.
> https://www.databricks.com/glossary/medallion-architecture
> Coined by Databricks; now adopted across AWS, GCP, Azure, and open-source Lakehouse
> implementations as the de facto standard for Lakehouse layer design.

The Medallion Architecture is a data design pattern that organizes data in a Lakehouse
into three progressive quality layers. Each layer represents an increasing degree of
structure, cleanliness, and business-readiness. Data flows unidirectionally:
Raw → Cleaned → Business-ready.

### Layer Definitions and Responsibilities

**Bronze — Raw Ingestion Layer**

The Bronze layer is an exact, immutable copy of source data. Its purpose is
preservation, not transformation. Every source record lands here exactly as it arrived.

Responsibilities:

- Ingest from all sources: databases (via CDC), files (CSV, JSON, Avro, Parquet), APIs, streams
- Append-only or insert-only — never update or delete source records
- Preserve original schema, encoding, and values (including nulls, malformed records)
- Store provenance metadata: ingestion timestamp, source system ID, pipeline run ID
- Enable full replay of any downstream processing (the source of truth for recovery)

Storage format: Avro or JSON for streaming sources (schema preserved alongside data);
Parquet or Delta Lake for batch file sources.

**Silver — Conformed and Validated Layer**

The Silver layer applies transformations that make data usable: type coercion, null
handling, deduplication, cross-source joins, and schema validation. The result is
clean, typed, deduplicated data at row level.

Responsibilities:

- Apply business validation rules and schema enforcement (Pandera, Great Expectations, or Delta constraints)
- Deduplicate records (row-level deduplication using natural keys)
- Resolve and join data from multiple Bronze sources into conformed entities
- Apply Slowly Changing Dimension logic where applicable (see analytics_engineering.md)
- Tag data quality failures — do not silently drop bad records (route to a quarantine table)
- Support time travel and upsert via Delta Lake or Apache Iceberg

Storage format: Delta Lake or Iceberg (ACID transactions required for upsert/deduplication).

**Gold — Business-Ready Aggregation Layer**

The Gold layer contains data structured for direct consumption by analysts, BI tools,
ML feature stores, and APIs. It represents the business domain, not the source system.

Responsibilities:

- Apply business aggregations: daily revenue, monthly active users, churn rate
- Model data in dimensional form: fact and dimension tables (see analytics_engineering.md)
- Compute derived metrics: rolling averages, period-over-period comparisons, KPIs
- Enforce access control — Gold tables are the authorized view of business data
- Serve ML feature stores, dashboards, operational APIs, and semantic layers

Storage format: Delta Lake or Iceberg; Parquet for static, non-updated exports.

### Medallion in Code — PySpark + Delta Lake

```python
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

logger = logging.getLogger(__name__)

# --- Constants ---
BRONZE_PATH: str = "s3://datalake/bronze/orders"
SILVER_PATH: str = "s3://datalake/silver/orders"
GOLD_PATH:   str = "s3://datalake/gold/daily_revenue"


def ingest_to_bronze(spark: SparkSession, source_path: str) -> None:
    """
    Bronze layer: raw ingestion with provenance metadata appended.
    No transformations applied — preserves source exactly.
    Uses Delta Lake APPEND mode for immutable audit trail.
    """
    df = (
        spark.read.format("parquet").load(source_path)
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_path", F.lit(source_path))
        .withColumn("_pipeline_run_id", F.lit(datetime.utcnow().isoformat()))
    )
    df.write.format("delta").mode("append").save(BRONZE_PATH)
    logger.info("Bronze: appended %d rows from %s", df.count(), source_path)


def transform_to_silver(spark: SparkSession) -> None:
    """
    Silver layer: clean, validate, deduplicate.
    Uses MERGE (upsert) to handle late-arriving and duplicate records.
    Quarantines invalid records rather than dropping silently.
    """
    from delta.tables import DeltaTable

    raw = spark.read.format("delta").load(BRONZE_PATH)

    # Type coercion + null handling
    cleaned = (
        raw
        .withColumn("order_date", F.to_date("order_date", "yyyy-MM-dd"))
        .withColumn("amount", F.col("amount").cast("double"))
        .withColumn("amount", F.coalesce(F.col("amount"), F.lit(0.0)))
        .filter(F.col("order_id").isNotNull())
    )

    # Quarantine invalid records — never drop silently
    valid   = cleaned.filter(F.col("amount") >= 0)
    invalid = cleaned.filter(F.col("amount") <  0)

    if invalid.count() > 0:
        invalid.write.format("delta").mode("append").save(SILVER_PATH + "_quarantine")
        logger.warning("Quarantined %d invalid records", invalid.count())

    # Upsert into Silver (handles duplicates and late arrivals)
    if DeltaTable.isDeltaTable(spark, SILVER_PATH):
        dt = DeltaTable.forPath(spark, SILVER_PATH)
        dt.alias("target").merge(
            valid.alias("source"),
            "target.order_id = source.order_id"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    else:
        valid.write.format("delta").mode("overwrite").save(SILVER_PATH)

    logger.info("Silver upsert complete")


def aggregate_to_gold(spark: SparkSession) -> None:
    """
    Gold layer: business aggregation for BI consumption.
    Written as overwrite with partition by date for efficient downstream queries.
    """
    silver = spark.read.format("delta").load(SILVER_PATH)

    gold = (
        silver
        .groupBy(F.to_date("order_date").alias("date"), "region")
        .agg(
            F.sum("amount").alias("total_revenue"),
            F.count("order_id").alias("total_orders"),
            F.avg("amount").alias("avg_order_value"),
        )
    )

    gold.write.format("delta").mode("overwrite").partitionBy("date").save(GOLD_PATH)
    logger.info("Gold aggregation complete")
```

---

## 2. Batch vs. Streaming — Architecture Decision {#batch-streaming}

> **Source**: Kleppmann, M. (2017). _Designing Data-Intensive Applications_. O'Reilly.
> Ch. 10–11 (Batch and Stream Processing). · Flink Documentation. https://flink.apache.org
> · Spark Structured Streaming. https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html

### Conceptual Distinction

**Batch processing**: operates on a bounded, finite dataset — all data is available
before processing begins. The output is produced after the full input is consumed.
Latency is measured in minutes to hours. Throughput is maximized at the cost of latency.

**Stream processing**: operates on an unbounded, continuously arriving dataset. Each
record (or micro-batch) is processed as it arrives. Latency is measured in
milliseconds to seconds. Correctness depends on handling out-of-order and late data.

### Decision Framework

| Criterion                  | Batch                                                | Streaming                                                       |
| -------------------------- | ---------------------------------------------------- | --------------------------------------------------------------- |
| Data availability          | All data available before processing                 | Data arrives continuously                                       |
| Acceptable latency         | Minutes to hours                                     | Milliseconds to seconds                                         |
| Throughput priority        | High — process large historical datasets efficiently | Lower — latency takes priority                                  |
| Out-of-order data handling | Not applicable (static input)                        | Required — define watermarks                                    |
| Use cases                  | ETL, reporting, model training, historical analysis  | Fraud detection, IoT monitoring, real-time dashboards, alerting |
| Tooling                    | Spark, dbt, Airflow, SQL                             | Spark Structured Streaming, Apache Flink, Kafka Streams         |
| Operational complexity     | Lower                                                | Higher — requires stateful processing, checkpointing            |

### Lambda Architecture

Lambda combines both paradigms with a serving layer that merges outputs:

```
Batch Layer:   historical, accurate, high-latency batch views
Speed Layer:   low-latency, approximate, recent stream views
Serving Layer: merges batch + speed views to answer queries
```

Limitation: maintaining two codepaths (one for batch, one for streaming) that must
produce identical results for the same data creates significant engineering overhead.
Modern Lakehouse architectures with Delta Lake / Iceberg + Spark Structured Streaming
eliminate Lambda's need for a separate batch layer.

### Kappa Architecture

A single stream-processing layer handles all data. Historical reprocessing is achieved
by replaying stored events from Kafka or a message log. Simpler than Lambda but
requires the stream processor to handle large-scale reprocessing efficiently.

### Watermarks and Windows in Streaming

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("streaming_pipeline").getOrCreate()

# Read from Kafka source
stream_df = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "localhost:9092")
    .option("subscribe", "orders")
    .load()
)

events = (
    stream_df
    .select(F.from_json(F.col("value").cast("string"), schema).alias("data"))
    .select("data.*")
    .withColumn("event_time", F.to_timestamp("event_timestamp"))
)

# Watermark: tolerate late data up to 10 minutes behind the maximum observed event time
# Tumbling window: 5-minute non-overlapping aggregation windows
windowed = (
    events
    .withWatermark("event_time", "10 minutes")
    .groupBy(
        F.window("event_time", "5 minutes"),
        "region"
    )
    .agg(F.sum("amount").alias("revenue_5min"))
)

query = (
    windowed.writeStream
    .format("delta")
    .option("checkpointLocation", "/checkpoints/orders_windowed")
    .outputMode("append")
    .start("/delta/gold/orders_windowed")
)
```

---

## 3. Apache Spark — Architecture and Internals {#spark}

> **Source**: Apache Spark Documentation (3.5).
> https://spark.apache.org/docs/latest/cluster-overview.html
> Zaharia, M. et al. (2012). Resilient Distributed Datasets. _NSDI_. (Original RDD paper.)

### Spark Architecture

```
Driver Program
  ├── SparkContext / SparkSession
  ├── DAG Scheduler (logical plan → physical plan)
  └── Task Scheduler

Cluster Manager (YARN / Kubernetes / Standalone)
  └── Executors (one per node)
        ├── Task Threads (--executor-cores)
        └── JVM Memory
              ├── Execution Memory (shuffles, aggregations)
              └── Storage Memory (cached RDDs/DataFrames)
```

**Driver**: coordinates the application. Translates user code into a Directed Acyclic
Graph (DAG) of stages and tasks. Collects results. Single point of failure — if the
driver dies, the application fails.

**Executor**: runs tasks on worker nodes. Stores cached data. Each executor hosts
multiple task threads (one per core). Executors communicate results back to the driver.

**DAG Scheduler**: translates logical transformations into a physical execution plan.
Groups operations into stages separated by shuffle boundaries (wide dependencies).

### Transformations and Actions

Spark is lazy: transformations build a logical plan but do not execute until an action
is called.

**Narrow transformations** (no shuffle — single partition input → single partition output):
`map`, `filter`, `flatMap`, `select`, `withColumn`, `drop`, `na.fill`

**Wide transformations** (shuffle — data redistribution across partitions):
`groupBy`, `join`, `distinct`, `repartition`, `sort`, `reduceByKey`

**Actions** (trigger execution):
`count`, `collect`, `show`, `write`, `save`, `first`, `take(n)`

### Key Optimizations

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = (
    SparkSession.builder
    .appName("optimized_pipeline")
    .config("spark.sql.adaptive.enabled", "true")           # AQE: re-optimizes at runtime
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true")  # Reduces shuffle partitions
    .config("spark.sql.shuffle.partitions", "200")          # Baseline; AQE will adjust
    .config("spark.sql.adaptive.skewJoin.enabled", "true")  # Handles data skew in joins
    .getOrCreate()
)

# Broadcast join: for small tables (< 10MB default), avoid shuffle entirely
large_df = spark.table("orders")
small_df  = spark.table("country_codes")  # small lookup table

result = large_df.join(F.broadcast(small_df), "country_code")

# Partition pruning: always filter on partition columns BEFORE joins
orders = (
    spark.read.format("delta").load("/delta/silver/orders")
    .filter(F.col("order_date") >= "2024-01-01")   # partition pruning — reads only relevant files
)

# Cache when a DataFrame is reused in multiple operations
reused_df = orders.filter(F.col("status") == "completed").cache()
count_a = reused_df.count()
agg_a   = reused_df.agg(F.sum("amount"))
reused_df.unpersist()  # release cache after use
```

### Spark Memory Management

```
Unified Memory Model (Spark 1.6+):
  Total JVM Heap
    └── Spark Memory Pool (spark.memory.fraction, default 0.6)
          ├── Execution Memory (shuffle sort, aggregations)
          │     elastic boundary — borrows from Storage if available
          └── Storage Memory (RDD/DataFrame cache, broadcast vars)
                elastic boundary — borrows from Execution if available
    └── User Memory (UDFs, application data structures)
    └── Reserved Memory (300MB system reserve)
```

Out-of-memory errors typically indicate: data skew (a few partitions are much larger
than others), insufficient `executor.memory`, or too many cached DataFrames.
Diagnose via Spark UI → Executors tab → GC time and memory usage.

---

## 4. Databricks — Platform Reference {#databricks}

> **Source**: Databricks Documentation. https://docs.databricks.com
> Unity Catalog: https://docs.databricks.com/en/data-governance/unity-catalog/index.html

Databricks is a cloud-based unified analytics platform built on Apache Spark and
Delta Lake, with integrated ML (MLflow), SQL analytics, and data governance (Unity Catalog).

### Databricks Workspace Components

| Component               | Purpose                                                                                       |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| Clusters                | Spark compute resources. Interactive (notebooks) or job clusters (pipelines).                 |
| Notebooks               | Collaborative Python/SQL/Scala/R development environment with Spark integration               |
| Workflows / Jobs        | Orchestration of multi-task pipelines; DAG of notebooks, JARs, Python scripts                 |
| Delta Live Tables (DLT) | Declarative ETL framework for building Medallion pipelines with automated data quality        |
| Unity Catalog           | Centralized governance: data catalog, access control, lineage, and auditing across workspaces |
| MLflow                  | Integrated experiment tracking, model registry, and model serving                             |
| SQL Warehouse           | Serverless or provisioned compute for SQL analytics (photon-optimized)                        |

### Delta Live Tables — Declarative Medallion Pipelines

```python
import dlt
from pyspark.sql import functions as F

# Bronze — raw ingestion (DLT streaming table)
@dlt.table(
    comment="Raw orders ingested from S3. Append-only, no transformations.",
    table_properties={"quality": "bronze"},
)
def bronze_orders():
    return (
        spark.readStream.format("cloudFiles")   # Auto Loader — efficient incremental ingest
        .option("cloudFiles.format", "json")
        .load("s3://raw-data/orders/")
    )

# Silver — validated and deduplicated
@dlt.table(
    comment="Cleaned orders: typed, deduped, validated.",
    table_properties={"quality": "silver"},
)
@dlt.expect_or_quarantine("valid_amount", "amount >= 0")   # Data quality rule
@dlt.expect_or_fail("non_null_order_id", "order_id IS NOT NULL")  # Pipeline fails if violated
def silver_orders():
    return (
        dlt.read_stream("bronze_orders")
        .withColumn("order_date", F.to_date("order_date"))
        .withColumn("amount", F.col("amount").cast("double"))
        .dropDuplicates(["order_id"])
    )

# Gold — business aggregation
@dlt.table(
    comment="Daily revenue by region for BI consumption.",
    table_properties={"quality": "gold"},
)
def gold_daily_revenue():
    return (
        dlt.read("silver_orders")
        .groupBy(F.to_date("order_date").alias("date"), "region")
        .agg(F.sum("amount").alias("total_revenue"), F.count("order_id").alias("n_orders"))
    )
```

### Unity Catalog — Three-Level Namespace

```sql
-- Unity Catalog: catalog.schema.table
-- All assets governed by a single metastore across all Databricks workspaces

-- Create a catalog
CREATE CATALOG IF NOT EXISTS analytics_prod;

-- Create a schema (database)
CREATE SCHEMA IF NOT EXISTS analytics_prod.sales;

-- Grant access using fine-grained permissions
GRANT SELECT ON TABLE analytics_prod.sales.gold_daily_revenue TO `data_analyst_group`;
GRANT MODIFY ON SCHEMA analytics_prod.sales TO `data_engineer_group`;

-- Lineage is automatically tracked — every read and write recorded
-- View lineage in the Unity Catalog UI or via REST API
```

---

## 5. Delta Lake — Beyond the Basics {#delta-lake}

> See `data_formats.md` for Delta Lake fundamentals (ACID, time travel, upsert, vacuum).
> This section covers advanced features not covered there.

### Schema Evolution and Enforcement

```python
from delta.tables import DeltaTable

# Schema enforcement (default): writes with incompatible schema are rejected
# Schema evolution: allow adding new columns automatically

df_with_new_col = spark.sql("SELECT *, 'USD' AS currency FROM orders")

(
    df_with_new_col.write
    .format("delta")
    .mode("append")
    .option("mergeSchema", "true")   # Allows schema evolution (additive only)
    .save("/delta/silver/orders")
)

# For destructive schema changes (rename, delete, type change) — requires overwriteSchema
(
    df_reshaped.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .save("/delta/silver/orders")
)
```

### Delta Change Data Feed (CDF)

Delta Lake's Change Data Feed captures row-level changes (insert, update, delete)
for incremental downstream processing — similar to CDC from source databases.

```python
# Enable CDF on a table
spark.sql("""
    ALTER TABLE delta.`/delta/silver/orders`
    SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")

# Read only the changes since version 10
changes = (
    spark.read.format("delta")
    .option("readChangeFeed", "true")
    .option("startingVersion", 10)
    .load("/delta/silver/orders")
)
# _change_type column: "insert", "update_preimage", "update_postimage", "delete"
changes.select("order_id", "amount", "_change_type", "_commit_version").show()
```

### Z-Ordering — Multi-Dimensional Clustering

Z-ordering co-locates related data in the same files, enabling efficient data skipping
for multi-column filter predicates. Most effective when queries filter on multiple
columns simultaneously.

```sql
-- Co-locate data by region and order_date in the same Delta files
-- Subsequent queries filtering on both columns skip most files
OPTIMIZE delta.`/delta/gold/daily_revenue`
ZORDER BY (region, order_date);
```

---

## 6. Lakehouse Architecture {#lakehouse}

> **Source**: Armbrust, M., et al. (2021). Lakehouse: A New Generation of Open Platforms
> that Unify Data Warehousing and Advanced Analytics. _CIDR_. (Databricks research.)
> https://www.cidrdb.org/cidr2021/papers/cidr2021_paper17.pdf

The Lakehouse is an architectural pattern that combines the cost-efficiency and
flexibility of a Data Lake with the performance, reliability, and structure of a
Data Warehouse — on a single platform.

### Why the Lakehouse Emerged

**Data Warehouse problems**: expensive storage, proprietary formats, poor support for
unstructured data (images, text, logs), cannot run ML workloads directly on warehouse data.

**Data Lake problems**: no schema enforcement, no ACID transactions, poor query
performance (full file scans), governance and data quality problems at scale.

**Lakehouse solution**: open file formats (Parquet + Delta Lake / Iceberg) on cheap
object storage (S3, GCS, ADLS) with a metadata layer providing ACID transactions,
schema enforcement, indexing, and governance. SQL analytics, ML, and data science
all operate directly on the same data.

### Lakehouse vs. Warehouse vs. Lake

| Dimension          | Data Warehouse                | Data Lake           | Lakehouse                                   |
| ------------------ | ----------------------------- | ------------------- | ------------------------------------------- |
| Storage format     | Proprietary                   | Open (Parquet, ORC) | Open (Parquet + Delta/Iceberg)              |
| Storage cost       | High                          | Low                 | Low                                         |
| ACID transactions  | Yes                           | No                  | Yes (Delta/Iceberg layer)                   |
| Schema enforcement | Strong                        | None                | Configurable                                |
| Query performance  | High (optimized)              | Low (full scans)    | High (Z-order, bloom filters, caching)      |
| ML workloads       | Limited                       | Native              | Native                                      |
| Streaming          | Limited                       | Limited             | Native (Structured Streaming)               |
| Governance         | Strong                        | Weak                | Strong (Unity Catalog / AWS Glue)           |
| Typical stack      | Snowflake, Redshift, BigQuery | S3 + Hive           | Databricks, AWS Lake Formation, GCP BigLake |

---

## 7. Change Data Capture (CDC) {#cdc}

> **Source**: Kleppmann (2017), Ch. 11. · Debezium Documentation.
> https://debezium.io/documentation · Airbyte CDC Guide.
> https://docs.airbyte.com/understanding-airbyte/cdc

### What CDC Is

Change Data Capture continuously captures row-level changes (INSERT, UPDATE, DELETE)
from a source database and propagates them to downstream systems. CDC reads from the
database's transaction log (WAL in PostgreSQL, binlog in MySQL) rather than polling
the table — making it non-intrusive and consistent.

CDC is the preferred method for replicating operational database data into a Data
Lake or Data Warehouse, replacing batch full-table extracts that miss deletes,
are slow, and put load on the source database.

### CDC Mechanisms

| Mechanism               | How it works                                      | Pros                                                  | Cons                                                     |
| ----------------------- | ------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| **Log-based CDC**       | Reads database transaction log (WAL / binlog)     | Low latency; captures deletes; minimal source DB load | Requires DB-level access; log format varies by DB        |
| **Trigger-based CDC**   | Database triggers write changes to an audit table | No special DB permissions needed                      | Adds write overhead to source DB; misses bulk operations |
| **Timestamp-based CDC** | Queries rows WHERE updated_at > last_run          | Simple to implement                                   | Cannot detect deletes; requires updated_at column        |
| **Full snapshot**       | Complete table export on every run                | No dependency on DB features                          | Slow; misses deletes between snapshots                   |

**Production recommendation**: log-based CDC via Debezium (PostgreSQL, MySQL, MongoDB,
Oracle, SQL Server) publishing to Kafka topics. Downstream consumers (Spark, Flink)
read from Kafka and apply changes to Delta Lake using MERGE.

### CDC Pipeline — Debezium + Kafka + Delta Lake

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, LongType
from delta.tables import DeltaTable

spark = SparkSession.builder.appName("cdc_pipeline").getOrCreate()

# Debezium wraps changes in an envelope schema:
# op: "c" = create, "u" = update, "d" = delete, "r" = snapshot read
# before: row state before the change (null for inserts)
# after:  row state after the change (null for deletes)

cdc_stream = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "postgres.public.orders")   # Debezium topic: server.schema.table
    .option("startingOffsets", "latest")
    .load()
)

parsed = cdc_stream.select(
    F.from_json(F.col("value").cast("string"), debezium_schema).alias("cdc")
).select("cdc.op", "cdc.before.*", "cdc.after.*", "cdc.ts_ms")

def upsert_from_cdc(batch_df, batch_id: int) -> None:
    """Apply CDC events to the Delta silver table using MERGE."""
    target = DeltaTable.forPath(spark, "/delta/silver/orders")

    # Apply inserts and updates from "after" state
    upserts = batch_df.filter(F.col("op").isin(["c", "u", "r"])).select("after.*")

    target.alias("t").merge(
        upserts.alias("s"), "t.order_id = s.order_id"
    ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()

    # Apply deletes — soft delete recommended (set is_deleted = true)
    deletes = batch_df.filter(F.col("op") == "d").select("before.order_id")
    (
        target.alias("t").merge(
            deletes.alias("s"), "t.order_id = s.order_id"
        ).whenMatchedUpdate(set={"is_deleted": F.lit(True), "deleted_at": F.current_timestamp()})
        .execute()
    )

(
    parsed.writeStream
    .foreachBatch(upsert_from_cdc)
    .option("checkpointLocation", "/checkpoints/cdc_orders")
    .start()
)
```

---

## 8. Data Contracts {#data-contracts}

> **Source**: Jones, A. (2023). _Fundamentals of Data Observability_. O'Reilly.
> Dehghani, Z. (2022). _Data Mesh_. O'Reilly, Ch. 9. · Andrew Jones (2023).
> _Driving Data Quality with Data Contracts_. O'Reilly.
> Google Internal Paper: Data Contracts at Google Scale (VLDB 2023).

### What Data Contracts Are

A data contract is a formal, versioned, machine-readable agreement between a data
producer and one or more data consumers specifying:

1. The schema of the data (column names, types, constraints)
2. Semantic definitions (what each field means in business terms)
3. Quality SLOs (completeness, freshness, accuracy thresholds)
4. Ownership, stewardship, and support contact
5. SLA for data availability and update frequency
6. Versioning and backward-compatibility policy

Data contracts shift data quality left: instead of consumers discovering quality
problems after ingestion, contracts define expectations upfront and failures surface
at the producer before data is published.

### Why Data Contracts Solve a Real Problem

Without contracts, data pipelines break silently when producers change schemas,
rename columns, or change semantics (e.g., `revenue` changes from gross to net)
without notifying consumers. In large organizations with many independent teams,
this causes cascading failures across dependent pipelines and dashboards.

### Data Contract Structure (YAML — Open Data Contract Standard)

```yaml
# orders_contract.yaml
# Open Data Contract Standard (ODCS) v2.2
# https://bitol-io.github.io/open-data-contract-standard/

kind: DataContract
id: orders-v1
name: orders
version: '1.2.0' # Semantic versioning: MAJOR.MINOR.PATCH
status: active

description:
  purpose: 'Transactional order records from the e-commerce platform.'
  limitations: 'Does not include cancelled or draft orders.'
  usage: 'Gold-layer analytics, revenue reporting, churn modeling.'

owner:
  team: data-engineering
  email: data-eng@company.com
  escalation: platform-oncall@company.com

sla:
  availability: '99.5%'
  freshness: 'Data available within 30 minutes of transaction'
  latency: 'P99 query latency < 2 seconds on the Gold table'

schema:
  - name: order_id
    type: string
    required: true
    unique: true
    pii: false
    description: 'Globally unique order identifier. Format: ORD-{UUID4}.'

  - name: customer_id
    type: string
    required: true
    pii: true
    description: 'Anonymized customer identifier. Raw PII is not stored.'

  - name: order_date
    type: date
    format: 'YYYY-MM-DD'
    required: true
    description: 'UTC date when the order was placed.'

  - name: amount
    type: decimal(18, 2)
    required: true
    minimum: 0
    description: 'Net revenue in USD. Excludes taxes and shipping.'

  - name: region
    type: string
    required: true
    allowed_values: ['APAC', 'EMEA', 'AMER', 'LATAM']
    description: "Geographic region of the customer's billing address."

quality:
  completeness:
    - column: order_id
      threshold: 100%
    - column: amount
      threshold: 99.9%

  freshness:
    - column: order_date
      max_age_hours: 1

  validity:
    - column: amount
      rule: 'amount >= 0'
    - column: region
      rule: "region IN ('APAC','EMEA','AMER','LATAM')"

versioning:
  backward_compatible_changes:
    - 'Adding new non-required columns'
    - 'Expanding allowed_values for existing columns'
  breaking_changes:
    - 'Removing existing columns'
    - 'Renaming columns'
    - 'Changing column types'
    - 'Changing semantics of existing fields'
  breaking_change_policy: |
    Breaking changes require a new major version (v2.0.0) published 30 days
    before v1.x.x is deprecated. Consumers must migrate within the window.
```

### Validating a Contract Programmatically

```python
from __future__ import annotations

import yaml
import logging
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_against_contract(
    df: pd.DataFrame,
    contract_path: str | Path,
) -> dict:
    """
    Validate a DataFrame against a YAML data contract.

    Checks: required columns present, types match, null constraints,
    allowed values, and minimum value constraints.

    Returns:
        Dictionary with 'passed' (bool) and 'violations' (list of strings).
    """
    with open(contract_path) as f:
        contract = yaml.safe_load(f)

    violations: list[str] = []
    schema = {col["name"]: col for col in contract.get("schema", [])}

    for col_name, spec in schema.items():
        if spec.get("required") and col_name not in df.columns:
            violations.append(f"MISSING required column: {col_name}")
            continue

        if col_name not in df.columns:
            continue

        # Null check
        null_count = df[col_name].isnull().sum()
        if spec.get("required") and null_count > 0:
            violations.append(f"NULL violation in required column '{col_name}': {null_count} nulls")

        # Uniqueness check
        if spec.get("unique") and df[col_name].duplicated().any():
            violations.append(f"UNIQUENESS violation in column '{col_name}'")

        # Allowed values check
        if "allowed_values" in spec:
            invalid = ~df[col_name].isin(spec["allowed_values"])
            if invalid.any():
                violations.append(
                    f"INVALID VALUES in '{col_name}': {df.loc[invalid, col_name].unique().tolist()}"
                )

        # Minimum value check
        if "minimum" in spec and pd.api.types.is_numeric_dtype(df[col_name]):
            below_min = (df[col_name] < spec["minimum"]).sum()
            if below_min > 0:
                violations.append(
                    f"VALUE below minimum {spec['minimum']} in '{col_name}': {below_min} rows"
                )

    result = {"passed": len(violations) == 0, "violations": violations}

    if violations:
        for v in violations:
            logger.error("Contract violation: %s", v)
    else:
        logger.info("Contract validation passed for %s", contract["name"])

    return result
```

---

## 9. Data Lineage {#data-lineage}

> **Source**: Reis & Housley (2022), Ch. 9. · Apache Atlas. https://atlas.apache.org
> · OpenLineage. https://openlineage.io · Marquez. https://marquezproject.ai

### What Data Lineage Is

Data lineage tracks the origin, movement, and transformation of data across a pipeline —
from source system to final consumption. It answers the questions:

- Where did this data come from?
- What transformations were applied?
- Which downstream datasets and dashboards depend on this table?
- What is the blast radius if this source changes or fails?

### Types of Lineage

**Column-level lineage**: tracks which source columns contributed to each column in
the output. Critical for impact analysis (if `orders.amount` changes semantics,
which dashboards show affected numbers?) and for understanding derived metrics.

**Table-level lineage**: tracks which tables a given table was built from and which
tables consume it. Sufficient for most impact analysis and pipeline debugging.

**Job-level lineage**: tracks which pipeline jobs read from and write to each dataset.
Links the data artifact to the code that produced it.

### OpenLineage — Open Standard for Lineage Events

OpenLineage (https://openlineage.io) is an open specification for collecting lineage
metadata from data pipelines. Supported by Airflow, Spark, dbt, Flink, and most
modern data tools via a common API.

```python
from openlineage.client import OpenLineageClient
from openlineage.client.run import (
    RunEvent, RunState, Run, Job,
    InputDataset, OutputDataset
)
from openlineage.client.facet import SchemaDatasetFacet, SchemaField
import uuid
from datetime import datetime

client = OpenLineageClient.from_environment()

run_id = str(uuid.uuid4())

# Emit START event when the job begins
client.emit(RunEvent(
    eventType=RunState.START,
    eventTime=datetime.utcnow().isoformat() + "Z",
    run=Run(runId=run_id),
    job=Job(namespace="data-engineering", name="silver_orders_transform"),
    inputs=[InputDataset(namespace="s3://datalake", name="bronze/orders")],
    outputs=[OutputDataset(namespace="s3://datalake", name="silver/orders")],
))

# ... run the transformation ...

# Emit COMPLETE event when the job finishes
client.emit(RunEvent(
    eventType=RunState.COMPLETE,
    eventTime=datetime.utcnow().isoformat() + "Z",
    run=Run(runId=run_id),
    job=Job(namespace="data-engineering", name="silver_orders_transform"),
    inputs=[InputDataset(namespace="s3://datalake", name="bronze/orders")],
    outputs=[
        OutputDataset(
            namespace="s3://datalake",
            name="silver/orders",
            facets={
                "schema": SchemaDatasetFacet(fields=[
                    SchemaField(name="order_id", type="STRING"),
                    SchemaField(name="amount", type="DOUBLE"),
                    SchemaField(name="order_date", type="DATE"),
                ])
            }
        )
    ],
))
```

---

## 10. Apache Kafka and Azure Event Hubs {#kafka-eventhubs}

> **Source**: Apache Kafka Documentation 3.7. https://kafka.apache.org/documentation
> Microsoft Azure Event Hubs. https://learn.microsoft.com/en-us/azure/event-hubs
> Kleppmann (2017), Ch. 11.

### Apache Kafka — Core Architecture

Kafka is a distributed event streaming platform designed for high-throughput,
fault-tolerant, durable publish-subscribe messaging.

```
Producer → [Kafka Cluster] → Consumer Group
              │
              ├── Broker 1
              │     ├── Topic A — Partition 0 (Leader)
              │     └── Topic B — Partition 1 (Follower replica)
              ├── Broker 2
              │     ├── Topic A — Partition 1 (Leader)
              │     └── Topic B — Partition 0 (Follower replica)
              └── ZooKeeper / KRaft (metadata management)
```

**Key concepts**:

| Concept            | Definition                                                                                                                          |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| Topic              | Named logical channel. Producers write to topics; consumers read from topics.                                                       |
| Partition          | A topic is divided into N partitions for parallelism. Each partition is an ordered, immutable log.                                  |
| Offset             | Each message in a partition has a monotonically increasing integer offset. Consumers track their own offset.                        |
| Consumer Group     | A group of consumers that collectively read all partitions of a topic. Each partition is read by exactly one consumer in the group. |
| Replication Factor | Number of brokers that store copies of each partition. Replication = 3 is standard for production.                                  |
| Retention          | Messages are retained for a configurable duration (default 7 days) regardless of whether they have been consumed.                   |
| Log Compaction     | For changelog topics: retain only the latest message per key. Enables rebuilding state from the topic.                              |

### Kafka Producer and Consumer in Python

```python
from confluent_kafka import Producer, Consumer, KafkaException
import json
import logging

logger = logging.getLogger(__name__)

KAFKA_CONFIG = {
    "bootstrap.servers": "kafka:9092",
    "security.protocol": "SASL_SSL",
    "sasl.mechanisms": "PLAIN",
    "sasl.username": "{{ KAFKA_USERNAME }}",
    "sasl.password": "{{ KAFKA_PASSWORD }}",
}

# --- Producer ---
producer = Producer(KAFKA_CONFIG)

def delivery_callback(err, msg) -> None:
    if err:
        logger.error("Delivery failed: %s", err)
    else:
        logger.debug("Delivered to %s [%d] at offset %d",
                     msg.topic(), msg.partition(), msg.offset())

def publish_event(topic: str, key: str, payload: dict) -> None:
    """Publish a JSON-serialized event to a Kafka topic."""
    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
        callback=delivery_callback,
    )
    producer.poll(0)   # trigger delivery callbacks without blocking

publish_event("orders", key="ORD-001", payload={"order_id": "ORD-001", "amount": 99.99})
producer.flush()  # block until all pending messages are delivered

# --- Consumer ---
consumer_config = {**KAFKA_CONFIG,
    "group.id": "silver_pipeline",
    "auto.offset.reset": "earliest",    # start from beginning if no committed offset
    "enable.auto.commit": False,         # manual commit for at-least-once semantics
}

consumer = Consumer(consumer_config)
consumer.subscribe(["orders"])

try:
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            raise KafkaException(msg.error())
        payload = json.loads(msg.value().decode("utf-8"))
        logger.info("Received: %s", payload)
        consumer.commit(message=msg, asynchronous=False)  # commit after successful processing
finally:
    consumer.close()
```

### Azure Event Hubs

Azure Event Hubs is a fully managed cloud event streaming service compatible with
the Kafka protocol. Applications that use the Kafka client can connect to Event Hubs
by changing only the bootstrap server and authentication configuration — no code
changes to the producer/consumer logic.

```python
# Event Hubs Kafka-compatible endpoint configuration
# Replace the Kafka bootstrap.servers config with:
EVENTHUBS_CONFIG = {
    "bootstrap.servers": "NAMESPACE.servicebus.windows.net:9093",
    "security.protocol": "SASL_SSL",
    "sasl.mechanisms": "PLAIN",
    "sasl.username": "$ConnectionString",
    "sasl.password": "Endpoint=sb://NAMESPACE.servicebus.windows.net/;SharedAccessKeyName=...",
    "group.id": "consumer_group_name",
    "auto.offset.reset": "earliest",
}
# All producer/consumer code is identical to the Kafka example above.
# Event Hubs maps Kafka 'topics' to Event Hubs 'event hubs'.
```

**When to choose Event Hubs over Kafka**: when running on Azure and preferring a
fully managed service without cluster management. Event Hubs handles scaling,
replication, and infrastructure automatically. Use Kafka (self-managed or Confluent)
when multi-cloud portability, advanced features (Kafka Streams, ksqlDB, Schema
Registry, log compaction), or deep ecosystem integration is required.

---

## 11. Data Mesh {#data-mesh}

> **Source**: Dehghani, Z. (2022). _Data Mesh: Delivering Data-Driven Value at Scale_.
> O'Reilly. — The authoritative reference on Data Mesh.
> Dehghani, Z. (2019). How to Move Beyond a Monolithic Data Lake to a Distributed
> Data Mesh. Martin Fowler blog. https://martinfowler.com/articles/data-monolith-to-mesh.html

### What Data Mesh Is

Data Mesh is a sociotechnical approach to data architecture and organizational design
based on four core principles (Dehghani, 2022). It is a response to the failure mode
of centralized data platforms: as organizations grow, a single data engineering team
cannot understand, process, and serve data from all business domains at the quality
and speed that domain teams require.

Data Mesh is not a technology — it is an organizational and architectural paradigm.
The technology stack (Delta Lake, dbt, data catalogs) is the same; what changes is
who owns and operates the data.

### Four Principles of Data Mesh

**1. Domain Ownership**: data is owned and published by the domain team that
understands it best. The team responsible for `orders` in the e-commerce platform
owns the `orders` domain data product — not a central data engineering team.
Each domain team is responsible for producing, maintaining, and serving its data.

**2. Data as a Product**: domain teams treat their data outputs as products with
defined consumers, SLAs, documentation, and quality guarantees. A data product has:

- Discoverable: findable in a catalog with metadata, lineage, and documentation
- Addressable: accessible via a stable, versioned endpoint
- Trustworthy: quality SLOs defined and monitored
- Self-describing: schema and semantics documented
- Interoperable: follows platform-wide standards (common formats, contracts)
- Secure: access control enforced

**3. Self-Serve Data Platform**: a central platform team provides infrastructure
capabilities that domain teams use to build, deploy, and operate their data products
independently — without requiring the platform team's direct involvement for each
pipeline. Examples: managed Delta Lake storage, a self-service dbt environment,
a shared data catalog, a governed Kafka cluster.

**4. Federated Computational Governance**: global standards are enforced
programmatically (data contracts, schema registries, access control policies) while
local implementation decisions remain with domain teams. Global standards must be
automatable — governance that requires manual review does not scale.

### Data Mesh vs. Centralized Architecture

| Dimension              | Centralized Data Platform            | Data Mesh                                  |
| ---------------------- | ------------------------------------ | ------------------------------------------ |
| Data ownership         | Central data engineering team        | Domain teams                               |
| Pipeline development   | Central team builds all pipelines    | Domain teams build their own               |
| Quality accountability | Central team (bottleneck)            | Domain team (producer)                     |
| Scalability            | Bottleneck as domains grow           | Scales with domain teams                   |
| Domain expertise       | Central team must learn every domain | Domain experts own their data              |
| Governance             | Enforced by central team             | Federated computational governance         |
| Platform investment    | Data warehouse / central lake        | Self-serve platform infrastructure         |
| Suitable for           | Small organizations, few domains     | Large organizations, many autonomous teams |

---

## 12. Data Fabric {#data-fabric}

> **Source**: Gartner (2022). _Magic Quadrant for Data Integration Tools_.
> IBM Data Fabric Overview. https://www.ibm.com/topics/data-fabric
> Forrester Research (2023). _The Data Fabric Landscape_.

### What Data Fabric Is

Data Fabric is an architectural approach that provides a unified, intelligent, and
automated layer for data integration, governance, and access across heterogeneous
environments — on-premise, multi-cloud, and hybrid. The defining characteristic is
the use of **active metadata** and **AI/ML-driven automation** to reduce the manual
effort of data integration and governance.

Data Fabric is technology-centric: it emphasizes using tools (data catalogs, knowledge
graphs, ML-driven data quality) to automate what Data Mesh achieves through
organizational change.

### Data Mesh vs. Data Fabric

These two approaches are frequently confused. They solve related but different problems:

| Dimension         | Data Mesh                                                            | Data Fabric                                                 |
| ----------------- | -------------------------------------------------------------------- | ----------------------------------------------------------- |
| Primary focus     | Organizational design and domain ownership                           | Technology integration and automation                       |
| Core driver       | Decentralized ownership; domain expertise                            | Unified metadata; AI-driven automation                      |
| Governance model  | Federated computational governance                                   | Centralized governance via metadata                         |
| Suitable when     | Organization has many autonomous domain teams                        | Organization has heterogeneous, siloed systems to integrate |
| Key technologies  | Data contracts, domain-owned pipelines, self-serve platform          | Data catalogs, knowledge graphs, ML-driven data integration |
| They can coexist? | Yes — Data Fabric can be the platform infrastructure for a Data Mesh |

---

## 13. Data Observability {#observability}

> **Source**: Jones, A. (2023). _Fundamentals of Data Observability_. O'Reilly.
> Barr, B. (2021). _The Data Engineering Podcast: Data Observability_ (Monte Carlo).
> Great Expectations Documentation. https://docs.greatexpectations.io
> dbt Tests. https://docs.getdbt.com/docs/build/tests

### What Data Observability Is

Data observability is the ability to understand, diagnose, and resolve data issues
across a pipeline — equivalent to software observability (monitoring, logging, tracing)
applied to data systems. A data pipeline without observability is a black box: you
discover data quality problems only when a stakeholder reports an incorrect dashboard.

### Five Pillars of Data Observability (Monte Carlo)

| Pillar           | What it monitors                                         | Example metric                                                   |
| ---------------- | -------------------------------------------------------- | ---------------------------------------------------------------- |
| **Freshness**    | When was the table last updated?                         | `max(updated_at)` > expected freshness threshold                 |
| **Volume**       | Does the table have the expected number of rows?         | Row count is within 2 standard deviations of historical baseline |
| **Schema**       | Has the schema changed unexpectedly?                     | Column added, removed, renamed, or type changed                  |
| **Distribution** | Are column value distributions within expected bounds?   | % nulls, min/max, unique ratio — compared to historical baseline |
| **Lineage**      | Which upstream dependencies caused a downstream failure? | Trace broken table back to source via lineage graph              |

### Implementation with Great Expectations

```python
import great_expectations as gx

context = gx.get_context()

# Define a Data Source
datasource = context.sources.add_spark("spark_source", spark=spark)
asset = datasource.add_dataframe_asset("orders")
batch_request = asset.build_batch_request(dataframe=df)

# Define an Expectation Suite (the contract for this table)
suite = context.add_expectation_suite("orders.silver.suite")

validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

# Schema expectations
validator.expect_column_to_exist("order_id")
validator.expect_column_to_exist("amount")
validator.expect_column_to_exist("order_date")

# Completeness
validator.expect_column_values_to_not_be_null("order_id")
validator.expect_column_values_to_not_be_null("amount")

# Volume — freshness proxy
validator.expect_table_row_count_to_be_between(min_value=1000, max_value=10_000_000)

# Distribution / validity
validator.expect_column_values_to_be_between("amount", min_value=0, max_value=1_000_000)
validator.expect_column_values_to_be_in_set("region", ["APAC", "EMEA", "AMER", "LATAM"])
validator.expect_column_values_to_match_regex("order_id", r"^ORD-[0-9a-f-]{36}$")

# Uniqueness
validator.expect_column_values_to_be_unique("order_id")

# Run validation
results = validator.validate()

if not results.success:
    failed = [r for r in results.results if not r.success]
    for r in failed:
        print(f"FAILED: {r.expectation_config.expectation_type} on {r.expectation_config.kwargs}")
    raise ValueError(f"Data quality validation failed: {len(failed)} expectations not met")

validator.save_expectation_suite()
```

### dbt Tests for Gold Layer Observability

```yaml
# models/gold/schema.yml
version: 2

models:
  - name: gold_daily_revenue
    description: 'Daily revenue aggregated by region.'
    columns:
      - name: date
        tests:
          - not_null
          - unique # each date-region combination must be unique

      - name: region
        tests:
          - not_null
          - accepted_values:
              values: ['APAC', 'EMEA', 'AMER', 'LATAM']

      - name: total_revenue
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              inclusive: true

    tests:
      - dbt_utils.recency:
          datepart: hour
          field: date
          interval: 2 # Table must have data from within the last 2 hours
```

---

## 14. References {#references}

- Reis, J., & Housley, M. (2022). _Fundamentals of Data Engineering_. O'Reilly.
- Dehghani, Z. (2022). _Data Mesh: Delivering Data-Driven Value at Scale_. O'Reilly.
- Kleppmann, M. (2017). _Designing Data-Intensive Applications_. O'Reilly.
- Armbrust, M., et al. (2021). Lakehouse: A New Generation of Open Platforms. _CIDR 2021_.
- Zaharia, M., et al. (2012). Resilient Distributed Datasets. _USENIX NSDI_.
- Jones, A. (2023). _Fundamentals of Data Observability_. O'Reilly.
- Apache Kafka Documentation 3.7. https://kafka.apache.org/documentation
- Apache Spark Documentation 3.5. https://spark.apache.org/docs/latest
- Delta Lake Documentation. https://docs.delta.io
- Databricks Documentation. https://docs.databricks.com
- Microsoft Azure Event Hubs. https://learn.microsoft.com/en-us/azure/event-hubs
- Debezium CDC Documentation. https://debezium.io/documentation
- OpenLineage Specification. https://openlineage.io
- Great Expectations Documentation. https://docs.greatexpectations.io
- dbt Documentation. https://docs.getdbt.com
