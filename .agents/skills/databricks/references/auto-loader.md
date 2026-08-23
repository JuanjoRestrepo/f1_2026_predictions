# Auto Loader (cloudFiles)

> **Sources**: Databricks Auto Loader Documentation.
> https://docs.databricks.com/en/ingestion/cloud-object-storage/auto-loader/index.html
> Auto Loader Schema Evolution. https://docs.databricks.com/en/ingestion/cloud-object-storage/auto-loader/schema.html
> Auto Loader File Notification. https://docs.databricks.com/en/ingestion/cloud-object-storage/auto-loader/file-notification-mode.html

## Table of Contents

1. [What Auto Loader Solves](#overview)
2. [Directory Listing vs File Notification Mode](#modes)
3. [Core Configuration Options](#config)
4. [Schema Inference, Hints, and Evolution](#schema)
5. [Rescued Data Column](#rescued)
6. [Checkpointing](#checkpointing)
7. [File Format Support](#formats)
8. [Auto Loader + DLT Integration](#dlt)
9. [Performance at Scale](#performance)
10. [Production Templates](#templates)

---

## 1. What Auto Loader Solves {#overview}

Auto Loader replaces glob-path batch reads with stateful incremental ingestion. On every
trigger (streaming micro-batch), it processes only files that have arrived since the last
checkpoint — not the full directory. This makes it efficient at any scale and tolerant of
source data accumulating while the pipeline is paused.

**Auto Loader vs glob-based `spark.read`**:

| Dimension | Auto Loader (`cloudFiles`) | Glob-based `spark.read` |
|---|---|---|
| Incremental processing | Yes — checkpoint tracks processed files | No — reads all files on every run |
| Schema evolution | Automatic with configurable policy | Manual |
| Fault tolerance | Checkpoint enables resume after failure | Full re-read on failure |
| File notification mode | AWS SQS / Azure Event Grid for sub-second detection | Not available |
| Scale (file count) | Designed for billions of files | Degrades with millions of files |
| Integration with DLT | First-class (`readStream` in DLT) | DLT supports, but no incremental benefit |

---

## 2. Directory Listing vs File Notification Mode {#modes}

### Directory Listing Mode (default)

Auto Loader lists all files in the source directory on each micro-batch trigger and
computes the set of new files by diffing against the checkpoint. Listing scales to
millions of files but incurs LIST API cost and latency with large directories.

```python
from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()

df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", "/Volumes/prod_infra/checkpoints/orders/schema")
    # mode defaults to "directory" — explicit declaration for clarity
    .option("cloudFiles.useNotifications", "false")
    .load("s3://raw-data/orders/")
)
```

### File Notification Mode (recommended for > 1M files or high-frequency arrival)

Auto Loader subscribes to cloud-native event notification services that push file
arrival events in real time. Eliminates the LIST API call on every trigger.

| Cloud | Event service | Setup requirement |
|---|---|---|
| AWS | SQS + SNS (S3 Event Notifications) | IAM role with SQS publish + consume permissions; SNS → SQS subscription |
| Azure | Azure Event Grid + Storage Queue | Event Grid System Topic on storage account; Storage Queue subscription |
| GCP | GCS Pub/Sub Notifications | Pub/Sub topic on bucket; subscriber service account |

```python
df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.useNotifications", "true")
    # AWS: Auto Loader creates and manages SQS queue automatically if permissions allow
    .option("cloudFiles.region", "us-east-1")
    .option("cloudFiles.schemaLocation", "/Volumes/prod_infra/checkpoints/orders/schema")
    .load("s3://raw-data/orders/")
)
```

**Auto-provisioning**: if the Databricks IAM role has `sqs:CreateQueue` and
`sns:Subscribe` permissions, Auto Loader creates and wires the SQS/SNS resources
automatically on first run. Otherwise, pre-create them and provide the queue ARN via
`cloudFiles.sqsArn`.

---

## 3. Core Configuration Options {#config}

| Option | Default | Description |
|---|---|---|
| `cloudFiles.format` | — | Required. File format: `json`, `csv`, `parquet`, `avro`, `orc`, `text`, `binaryFile`. |
| `cloudFiles.schemaLocation` | — | Required for JSON/CSV/Avro. Path where Auto Loader stores the inferred schema and schema evolution history. |
| `cloudFiles.inferColumnTypes` | `false` | If `true`, infers column types during schema inference (JSON/CSV). If `false`, all columns inferred as `STRING`. |
| `cloudFiles.schemaEvolutionMode` | `addNewColumns` | See §4. |
| `cloudFiles.useNotifications` | `false` | Enable file notification mode (SQS/Event Grid). |
| `cloudFiles.includeExistingFiles` | `true` | Process files already present in the directory on first run. |
| `cloudFiles.maxFilesPerTrigger` | unlimited | Limit files processed per micro-batch. Useful for backfill rate control. |
| `cloudFiles.maxBytesPerTrigger` | unlimited | Limit bytes processed per micro-batch. |
| `cloudFiles.validateOptions` | `true` | Validate all options at stream start and fail fast on unknown options. |
| `cloudFiles.pathGlobFilter` | `*` | Glob pattern to filter files by name: `*.json`, `year=2024/**/*.parquet`. |
| `cloudFiles.modifiedAfter` | none | Only process files modified after this timestamp (for one-time historical backfill). |
| `cloudFiles.recursive` | `true` | Recursively list subdirectories. |

---

## 4. Schema Inference, Hints, and Evolution {#schema}

### Schema Inference

Auto Loader infers the schema from a sample of files on first run and persists it to
`cloudFiles.schemaLocation`. Subsequent runs use the persisted schema.

```python
# Schema hints: override inferred types for specific columns
# Format: "col_name TYPE, col_name TYPE, ..."
df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", "/Volumes/prod_infra/checkpoints/orders/schema")
    .option("cloudFiles.schemaHints", "amount DOUBLE, order_date DATE")
    .load("s3://raw-data/orders/")
)
```

**Best practice**: in production, provide an explicit schema via `.schema()` rather than
relying on inference. Inference requires an extra file read on startup and is non-deterministic
if the sample files are not representative. Use inference only during initial development
to discover the schema, then codify it.

```python
from pyspark.sql.types import (
    DateType, DoubleType, StringType, StructField, StructType,
)

ORDER_SCHEMA = StructType([
    StructField("order_id",    StringType(), nullable=False),
    StructField("customer_id", StringType(), nullable=False),
    StructField("amount",      DoubleType(), nullable=True),
    StructField("order_date",  DateType(),   nullable=True),
    StructField("region",      StringType(), nullable=True),
])

df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", "/Volumes/prod_infra/checkpoints/orders/schema")
    .schema(ORDER_SCHEMA)
    .load("s3://raw-data/orders/")
)
```

### Schema Evolution Modes

| Mode | Behavior on new column | Behavior on type mismatch |
|---|---|---|
| `addNewColumns` (default) | New columns added to schema; stream restarts. | Column cast to string; stored in `_rescued_data`. |
| `rescue` | New columns not added to schema. | New/mismatched data captured in `_rescued_data`. |
| `failOnNewColumns` | Stream fails on any schema change. | — |
| `none` | Schema never updated. New columns silently dropped. | Silently dropped. |

```python
# Rescue mode: most conservative for production Bronze
# New or mismatched columns go to _rescued_data; schema never changes automatically
df = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", "/Volumes/prod_infra/checkpoints/orders/schema")
    .option("cloudFiles.schemaEvolutionMode", "rescue")
    .schema(ORDER_SCHEMA)
    .load("s3://raw-data/orders/")
)
```

---

## 5. Rescued Data Column {#rescued}

The `_rescued_data` column is a JSON string capturing any data that could not be parsed
into the defined schema — either because the column was not in the schema, or because the
value could not be cast to the declared type.

```python
from pyspark.sql import functions as F

# After reading with rescue mode, inspect _rescued_data for schema violations
rescued_records = (
    df.filter(F.col("_rescued_data").isNotNull())
    .select(
        "order_id",
        "_source_file",
        F.from_json("_rescued_data", schema="MAP<STRING,STRING>").alias("rescued_fields"),
    )
)

# In a DLT pipeline: route rescued records to a quarantine table
@dlt.table(comment="Rescued records with schema violations from bronze ingestion.")
def bronze_orders_rescued() -> "DataFrame":
    return (
        dlt.read_stream("bronze_orders_raw")
        .filter(F.col("_rescued_data").isNotNull())
    )
```

---

## 6. Checkpointing {#checkpointing}

The checkpoint directory stores the state of the stream — which files have been processed,
the current schema version, and Structured Streaming offset metadata. Without a valid
checkpoint, Auto Loader re-processes all files from scratch.

```python
query = (
    df.writeStream
    .format("delta")
    .option("checkpointLocation", "/Volumes/prod_infra/checkpoints/orders/bronze")
    .trigger(availableNow=True)    # process all available files, then stop (batch equivalent)
    .outputMode("append")
    .start("s3://datalake/bronze/orders/")
)
query.awaitTermination()
```

**Checkpoint storage rules**:
- Store checkpoints in Unity Catalog Volumes (governed) or a dedicated storage path,
  not in DBFS.
- Use a unique checkpoint path per stream. Sharing a checkpoint between streams causes
  data corruption.
- Do not delete the checkpoint directory unless intentionally triggering a full re-process.
  Deleting the checkpoint and reprocessing from scratch is the standard recovery for
  corrupted checkpoint state.

**`trigger` options**:

| Trigger | Behavior |
|---|---|
| `.trigger(processingTime="5 minutes")` | Micro-batch every 5 minutes. |
| `.trigger(availableNow=True)` | Process all available data in one or more micro-batches, then stop. Equivalent to a batch job. |
| `.trigger(once=True)` | Deprecated. Use `availableNow=True`. |
| No trigger (default) | Continuous micro-batches as fast as possible. |

---

## 7. File Format Support {#formats}

| Format | Notes |
|---|---|
| `json` | Line-delimited JSON (NDJSON). Multi-line JSON requires `.option("multiLine", "true")` — disable for large files (high memory). |
| `csv` | Requires header row or explicit schema. Use `.option("header", "true")` and `.option("sep", ",")`. |
| `parquet` | Schema-on-read. Auto Loader reads Parquet metadata for column types. |
| `avro` | Schema embedded in each file or supplied via `.option("avroSchema", ...)`. |
| `orc` | Schema-on-read from ORC metadata. |
| `text` | Each line becomes a row in a `value STRING` column. Useful for free-form logs. |
| `binaryFile` | Each file becomes a row: `path`, `modificationTime`, `length`, `content BINARY`. Useful for image/audio pipelines. |

---

## 8. Auto Loader + DLT Integration {#dlt}

In a DLT pipeline, Auto Loader is always used via `spark.readStream.format("cloudFiles")`
inside a `@dlt.table` function. DLT manages the checkpoint automatically — do not specify
`checkpointLocation` when using Auto Loader inside DLT.

```python
import dlt
from pyspark.sql.types import DateType, DoubleType, StringType, StructField, StructType

ORDER_SCHEMA = StructType([
    StructField("order_id",    StringType(), nullable=False),
    StructField("customer_id", StringType(), nullable=False),
    StructField("amount",      DoubleType(), nullable=True),
    StructField("order_date",  DateType(),   nullable=True),
    StructField("region",      StringType(), nullable=True),
])


@dlt.table(
    comment="Raw orders — Auto Loader ingestion via cloudFiles.",
    table_properties={"quality": "bronze"},
)
def bronze_orders():
    """Bronze ingestion using Auto Loader inside DLT. DLT manages the checkpoint."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation",
                "/Volumes/prod_infra/checkpoints/bronze_orders/schema")
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .schema(ORDER_SCHEMA)
        .load("s3://raw-data/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.input_file_name())
    )
```

**DLT checkpoint location**: DLT stores checkpoints in the pipeline's storage location
(`{pipeline_storage}/checkpoints/{flow_name}/`). The `cloudFiles.schemaLocation` must
be set separately — it is NOT the Structured Streaming checkpoint; it stores only the
Auto Loader schema history.

---

## 9. Performance at Scale {#performance}

| Scenario | Recommendation |
|---|---|
| > 10 million files in directory | Enable file notification mode (`useNotifications=true`). Directory listing at this scale causes multi-minute delays per trigger. |
| High-frequency file arrival (< 1 min) | File notification mode + `maxFilesPerTrigger` to bound micro-batch size and memory. |
| Mixed file sizes (some large, some small) | `maxBytesPerTrigger` bounds by data volume rather than file count. Prevents oversized micro-batches from large files. |
| Backfill of historical data | `cloudFiles.modifiedAfter` to start from a specific date. `maxFilesPerTrigger=1000` to process in controlled batches. |
| Many small files from the source | Consider compacting source files before ingestion, or accept small-file overhead and rely on DLT's auto-compaction at the target Delta table. |

---

## 10. Production Templates {#templates}

### Standalone Auto Loader Stream (non-DLT)

```python
from __future__ import annotations

import logging
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DateType, DoubleType, StringType, StructField, StructType

logger = logging.getLogger(__name__)

ORDER_SCHEMA = StructType([
    StructField("order_id",    StringType(), nullable=False),
    StructField("customer_id", StringType(), nullable=False),
    StructField("amount",      DoubleType(), nullable=True),
    StructField("order_date",  DateType(),   nullable=True),
    StructField("region",      StringType(), nullable=True),
])

CHECKPOINT_PATH: str = "/Volumes/prod_infra/checkpoints/orders/bronze"
TARGET_TABLE: str = "prod_sales.orders.bronze_orders"
SOURCE_PATH: str = "s3://raw-data/orders/"


def run_bronze_ingestion(spark: SparkSession) -> None:
    """
    Run Auto Loader ingestion from S3 to bronze_orders Delta table.

    Uses availableNow trigger for scheduled (non-continuous) operation.
    Writes to Unity Catalog managed table using three-level namespace.

    Args:
        spark: Active SparkSession.
    """
    df = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{CHECKPOINT_PATH}/schema")
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .option("cloudFiles.useNotifications", "false")
        .option("cloudFiles.validateOptions", "true")
        .schema(ORDER_SCHEMA)
        .load(SOURCE_PATH)
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.input_file_name())
    )

    query = (
        df.writeStream
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", CHECKPOINT_PATH)
        .trigger(availableNow=True)
        .toTable(TARGET_TABLE)    # Unity Catalog three-level name
    )

    query.awaitTermination()
    logger.info(
        "Auto Loader ingestion complete. Rows processed: %d",
        spark.table(TARGET_TABLE).count(),
    )


if __name__ == "__main__":
    spark = SparkSession.builder.appName("orders_bronze_ingestion").getOrCreate()
    run_bronze_ingestion(spark)
```
