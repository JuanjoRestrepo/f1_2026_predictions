# Data File Formats — Selection Guide & Code Reference

> **Core principle**: Format selection is an architectural decision, not a preference.
> The wrong format at scale costs compute, time, and money. Choose based on access
> pattern (row vs. column), schema stability, pipeline stage, and ecosystem fit.

## Table of Contents

0. [Environment Setup (uv)](#environment)
1. [Format Comparison Matrix](#matrix)
2. [Selection Decision Guide](#decision-guide)
3. [Format-per-Layer: Bronze / Silver / Gold](#layer-guide)
4. [CSV](#csv)
5. [JSON](#json)
6. [Parquet](#parquet)
7. [ORC](#orc)
8. [Avro](#avro)
9. [Delta Lake](#delta)
10. [Apache Iceberg](#iceberg)
11. [Quick Reference Card](#quick-ref)

---

## 0. Environment Setup (uv) {#environment}

```bash
uv init data_formats_project && cd data_formats_project
uv python pin 3.12
uv venv .venv --python 3.12 && source .venv/bin/activate

# Core format libraries
uv add pandas polars pyarrow fastparquet        # CSV, JSON, Parquet
uv add fastavro apache-beam                     # Avro
uv add delta-spark deltalake                    # Delta Lake (Python + PySpark)
uv add pyiceberg                                # Apache Iceberg

# PySpark (for ORC, large-scale Parquet, Delta, Iceberg)
uv add pyspark

# Dev tools — mandatory
uv add --dev ruff mypy pytest
uv sync
```

---

## 1. Format Comparison Matrix {#matrix}

| Format | Type | Encoding | Schema | Compression | Splittable | Best Access Pattern |
|---|---|---|---|---|---|---|
| **CSV** | Text | Row-based | None | None / Gzip | ✅ Yes | Small datasets, human-readable exchange |
| **JSON** | Text | Row-based | None | None / Gzip | ⚠️ Partial | APIs, semi-structured, config files |
| **Parquet** | Binary | Columnar | Embedded | Snappy / Zstd | ✅ Yes | Analytics, OLAP, Data Lakes |
| **ORC** | Binary | Columnar | Embedded | Zlib / Snappy | ✅ Yes | Hive/Hadoop ecosystems, OLAP |
| **Avro** | Binary | Row-based | External (JSON) | Snappy / Deflate | ✅ Yes | Streaming, schema evolution, Kafka |
| **Delta Lake** | Binary + JSON log | Columnar (Parquet) | Enforced + versioned | Snappy / Zstd | ✅ Yes | Lakehouse, ACID transactions, time travel |
| **Apache Iceberg** | Binary + metadata | Columnar (Parquet/ORC/Avro) | Enforced + versioned | Snappy / Zstd | ✅ Yes | Open Lakehouse, multi-engine, cloud-native |

### Performance Characteristics

| Format | Write Speed | Read Speed (full) | Read Speed (filtered) | Storage Efficiency | Schema Evolution |
|---|---|---|---|---|---|
| **CSV** | ⚡ Fast | 🐢 Slow | 🐢 Slow (full scan) | ❌ Poor | ❌ None |
| **JSON** | ⚡ Fast | 🐢 Slow | 🐢 Slow (full scan) | ❌ Poor | ⚠️ Manual |
| **Parquet** | 🔶 Moderate | ⚡ Fast | ⚡ Fast (predicate pushdown) | ✅ Excellent | ✅ Additive columns |
| **ORC** | 🔶 Moderate | ⚡ Fast | ⚡ Fast | ✅ Excellent | ✅ Additive columns |
| **Avro** | ⚡ Fast | 🔶 Moderate | 🐢 Slow (row scan) | ✅ Good | ✅ Full (reader/writer schema) |
| **Delta Lake** | 🔶 Moderate | ⚡ Fast | ⚡ Fast | ✅ Excellent | ✅ Full + enforced |
| **Apache Iceberg** | 🔶 Moderate | ⚡ Fast | ⚡ Fast | ✅ Excellent | ✅ Full + enforced |

---

## 2. Selection Decision Guide {#decision-guide}

Apply this decision tree when selecting a format for any new dataset or pipeline output:

```
1. Is the data primarily for human readability or rapid prototyping?
   ├── YES → CSV (small datasets, reports, quick exports)
   └── NO  → Continue

2. Is the data semi-structured or coming from / going to an API / event stream?
   ├── API / web service → JSON
   ├── Kafka / message queue / streaming pipeline → Avro
   └── NO  → Continue

3. Is the primary access pattern analytics / OLAP (column scans, aggregations)?
   ├── YES → Continue to question 4
   └── NO (row-by-row access, serialization) → Avro or JSON

4. Does the pipeline require ACID transactions, time travel, or schema enforcement?
   ├── YES → Continue to question 5
   └── NO  → Parquet (general OLAP standard)
              ORC (if Hive/Hadoop ecosystem is the primary engine)

5. Which compute ecosystem owns this data?
   ├── Databricks / Azure / open-source Spark → Delta Lake
   ├── AWS Glue / Athena / Snowflake / multi-engine open → Apache Iceberg
   └── Both / undecided → Apache Iceberg (more engine-agnostic)
```

### Categorical Summary

| Scenario | Recommended Format | Reason |
|---|---|---|
| Small dataset, quick share | CSV | Simplicity, universal compatibility |
| REST API response / config | JSON | Native structure, flexible schema |
| Kafka messaging, schema versioning | Avro | Row serialization, schema registry support |
| Data Lake analytics, OLAP queries | Parquet | Columnar, compressed, predicate pushdown |
| Hadoop/Hive-centric warehouse | ORC | Optimized for Hive execution engine |
| Databricks Lakehouse, ACID pipelines | Delta Lake | Parquet + transaction log + time travel |
| Multi-engine / AWS / open Lakehouse | Apache Iceberg | Engine-agnostic, hidden partitioning, branching |

---

## 3. Format-per-Layer: Bronze / Silver / Gold {#layer-guide}

Align format selection with the Medallion Architecture layers already defined in
`etl_patterns.md`. Format choice must match the processing stage and access pattern
of each layer.

| Layer | Purpose | Recommended Format | Rationale |
|---|---|---|---|
| 🥉 **Bronze (Raw)** | Exact copy of source data, no transformation | **Avro** (streaming sources) / **Parquet** (batch files) / **JSON** (API dumps) | Preserve original structure and schema. Avro for Kafka ingestion; Parquet for batch; JSON for semi-structured APIs |
| 🥈 **Silver (Cleaned)** | Deduplicated, typed, validated data | **Delta Lake** or **Apache Iceberg** | ACID guarantees for upserts and deduplication jobs. Schema enforcement prevents data quality drift. Time travel enables rollback on bad runs |
| 🥇 **Gold (Business-ready)** | Aggregated, modeled, BI-ready tables | **Delta Lake** or **Apache Iceberg** (underlying) via **dbt** | dbt transforms read from Silver Delta/Iceberg tables; output Gold tables consumed by BI tools. Parquet acceptable for static, non-updated exports |

**Key rule**: Never keep Gold-layer data in CSV or raw JSON. By the time data reaches
Gold, it must be stored in a format that enforces schema, supports efficient column
scans, and is reproducible.

---

## 4. CSV {#csv}

**When to use**: Small-to-medium datasets (< 1 GB uncompressed), human-readable exchange,
quick exports, reports, interoperability with non-technical stakeholders.

**When NOT to use**: Any dataset exceeding a few GB; any pipeline requiring schema enforcement;
any production analytics workload.

```python
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import polars as pl

logger = logging.getLogger(__name__)

# --- Constants ---
CHUNK_SIZE: int = 100_000  # rows per chunk for memory-constrained reads


def read_csv_pandas(filepath: str | Path, **kwargs: object) -> pd.DataFrame:
    """
    Read a CSV file with pandas. Prefer polars for files > 500MB.

    Args:
        filepath: Path to the CSV file.
        **kwargs: Additional arguments forwarded to pd.read_csv().

    Returns:
        Loaded DataFrame with inferred dtypes.
    """
    path = Path(filepath)
    df = pd.read_csv(path, **kwargs)
    logger.info("Loaded CSV: %s rows, %s cols from %s", *df.shape, path)
    return df


def read_csv_chunked(filepath: str | Path, chunk_size: int = CHUNK_SIZE) -> pd.DataFrame:
    """
    Read a large CSV in chunks to avoid OOM errors.

    Args:
        filepath: Path to the CSV file.
        chunk_size: Number of rows per chunk.

    Returns:
        Concatenated DataFrame.
    """
    chunks = pd.read_csv(filepath, chunksize=chunk_size)
    df = pd.concat(chunks, ignore_index=True)
    logger.info("Chunked CSV read complete: %d rows", len(df))
    return df


def read_csv_polars(filepath: str | Path) -> pl.DataFrame:
    """Read CSV with Polars — preferred for files > 500MB."""
    df = pl.read_csv(filepath, infer_schema_length=10_000)
    logger.info("Polars CSV read: %s rows, %s cols", df.height, df.width)
    return df


def write_csv(df: pd.DataFrame, output_path: str | Path, index: bool = False) -> None:
    """Write DataFrame to CSV. Never include index unless explicitly required."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=index)
    logger.info("Written CSV: %s", output_path)
```

---

## 5. JSON {#json}

**When to use**: API responses, event data, configuration files, semi-structured or
nested data that does not fit a flat schema.

**When NOT to use**: Analytics workloads, large-scale batch processing, or any context
where schema consistency is required across records.

```python
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def read_json_records(filepath: str | Path) -> pd.DataFrame:
    """
    Read a newline-delimited JSON (NDJSON) file — the standard for large JSON datasets.
    Each line must be a valid JSON object.

    Args:
        filepath: Path to the NDJSON file.

    Returns:
        Flattened DataFrame.
    """
    df = pd.read_json(filepath, lines=True)
    logger.info("Loaded NDJSON: %d rows from %s", len(df), filepath)
    return df


def read_nested_json(filepath: str | Path, record_path: list[str] | None = None) -> pd.DataFrame:
    """
    Read and flatten nested JSON (e.g., API responses with nested objects/arrays).

    Args:
        filepath: Path to JSON file.
        record_path: Key path to the array of records within the JSON structure.

    Returns:
        Normalized, flattened DataFrame.
    """
    with open(filepath) as f:
        raw: Any = json.load(f)

    df = pd.json_normalize(raw, record_path=record_path, sep="_")
    logger.info("Normalized JSON: %d rows, %d cols", *df.shape)
    return df


def write_json(df: pd.DataFrame, output_path: str | Path, orient: str = "records") -> None:
    """
    Write DataFrame to JSON.

    Args:
        orient: 'records' (list of dicts) recommended for interoperability.
                Use 'lines' for NDJSON (streaming-friendly).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_json(output_path, orient=orient, lines=(orient == "lines"), indent=2 if orient != "lines" else None)
    logger.info("Written JSON: %s", output_path)
```

---

## 6. Parquet {#parquet}

**When to use**: The default format for all analytical workloads, Data Lakes, and
pipeline intermediates. Columnar storage enables predicate pushdown, column pruning,
and high compression — making it dramatically faster than CSV for analytics.

**When NOT to use**: Streaming ingestion (use Avro), or when the consumer cannot
read binary formats (use CSV).

```python
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# --- Constants ---
PARQUET_COMPRESSION: str = "snappy"   # 'snappy' (fast), 'zstd' (better ratio), 'gzip'
PARQUET_ROW_GROUP_SIZE: int = 128 * 1024 * 1024  # 128 MB — optimal for Spark/Athena reads


def read_parquet_pandas(filepath: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    """
    Read Parquet with pandas + PyArrow. Use `columns` for column pruning —
    this is the primary performance advantage of Parquet over CSV.

    Args:
        filepath: Path to Parquet file or directory of partitioned Parquet files.
        columns: Subset of columns to read. Omit to read all.

    Returns:
        DataFrame with only the requested columns loaded into memory.
    """
    df = pd.read_parquet(filepath, engine="pyarrow", columns=columns)
    logger.info("Loaded Parquet: %d rows, %d cols from %s", *df.shape, filepath)
    return df


def read_parquet_polars(filepath: str | Path, columns: list[str] | None = None) -> pl.DataFrame:
    """Read Parquet with Polars — preferred for large files or when chaining transforms."""
    df = pl.read_parquet(filepath, columns=columns)
    logger.info("Polars Parquet read: %d rows, %d cols", df.height, df.width)
    return df


def write_parquet(
    df: pd.DataFrame,
    output_path: str | Path,
    compression: str = PARQUET_COMPRESSION,
    partition_cols: list[str] | None = None,
) -> None:
    """
    Write DataFrame to Parquet with optional partitioning.

    Args:
        partition_cols: Columns to partition by (e.g., ['year', 'month']).
            Hive-style partitioning improves query performance on large datasets.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df)
    pq.write_to_dataset(
        table,
        root_path=str(output_path),
        partition_cols=partition_cols,
        compression=compression,
        row_group_size=PARQUET_ROW_GROUP_SIZE,
    )
    logger.info("Written Parquet to %s (partitioned by %s)", output_path, partition_cols)


def inspect_parquet_schema(filepath: str | Path) -> None:
    """Print Parquet schema and metadata without loading data into memory."""
    schema = pq.read_schema(filepath)
    metadata = pq.read_metadata(filepath)
    logger.info("Schema:\n%s", schema)
    logger.info("Row groups: %d | Rows: %d", metadata.num_row_groups, metadata.num_rows)
```

---

## 7. ORC {#orc}

**When to use**: Hive/Hadoop-centric ecosystems where ORC's native Hive optimizations
(bloom filters, predicate pushdown, Hive ACID) provide a meaningful advantage over Parquet.
If your infrastructure is not Hive-centric, default to Parquet instead.

**When NOT to use**: Outside Hive/Spark ecosystems. Parquet has broader tool support
(Athena, BigQuery, pandas, Polars, DuckDB) and should be the default everywhere else.

```python
from __future__ import annotations

import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.orc as orc
import pandas as pd

logger = logging.getLogger(__name__)


def read_orc(filepath: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    """
    Read an ORC file using PyArrow.

    Args:
        filepath: Path to the ORC file.
        columns: Optional column subset for column pruning.

    Returns:
        Loaded DataFrame.
    """
    orc_file = orc.ORCFile(str(filepath))
    table: pa.Table = orc_file.read(columns=columns)
    df = table.to_pandas()
    logger.info("Loaded ORC: %d rows, %d cols from %s", *df.shape, filepath)
    return df


def write_orc(df: pd.DataFrame, output_path: str | Path) -> None:
    """Write DataFrame to ORC format via PyArrow."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df)
    orc.write_table(table, str(output_path))
    logger.info("Written ORC: %s", output_path)


# PySpark ORC — preferred for production Hive/Spark workloads
PYSPARK_ORC_EXAMPLE: str = """
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("orc_pipeline").getOrCreate()

# Read ORC
df = spark.read.format("orc").load("s3://bucket/path/to/orc/")

# Write ORC with partitioning
df.write.format("orc") \\
    .mode("overwrite") \\
    .partitionBy("year", "month") \\
    .save("s3://bucket/output/orc/")
"""
```

---

## 8. Avro {#avro}

**When to use**: Streaming pipelines (Kafka), message serialization, or any scenario
requiring robust schema evolution (adding/removing fields without breaking consumers).
Avro stores the schema alongside the data, enabling reader/writer schema compatibility.

**When NOT to use**: Analytical queries (row-based format is slow for column scans);
use Parquet/Delta/Iceberg for analytics.

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import fastavro
import pandas as pd

logger = logging.getLogger(__name__)

# --- Avro schema definition (stored separately from data) ---
USER_EVENT_SCHEMA: dict[str, Any] = {
    "type": "record",
    "name": "UserEvent",
    "namespace": "com.company.events",
    "fields": [
        {"name": "event_id",   "type": "string"},
        {"name": "user_id",    "type": "long"},
        {"name": "event_type", "type": "string"},
        {"name": "timestamp",  "type": "long"},
        {"name": "payload",    "type": ["null", "string"], "default": None},
    ],
}


def write_avro(
    records: list[dict[str, Any]],
    output_path: str | Path,
    schema: dict[str, Any] = USER_EVENT_SCHEMA,
    codec: str = "snappy",
) -> None:
    """
    Serialize records to Avro format.

    Args:
        records: List of dicts conforming to the schema.
        schema: Avro schema definition dict.
        codec: Compression codec — 'snappy', 'deflate', or 'null'.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    parsed_schema = fastavro.parse_schema(schema)
    with open(output_path, "wb") as f:
        fastavro.writer(f, parsed_schema, records, codec=codec)
    logger.info("Written %d Avro records to %s", len(records), output_path)


def read_avro(filepath: str | Path) -> pd.DataFrame:
    """
    Deserialize an Avro file into a DataFrame.

    Note: Schema is embedded in the file — no external schema required for reading.
    """
    with open(filepath, "rb") as f:
        records = list(fastavro.reader(f))
    df = pd.DataFrame(records)
    logger.info("Loaded Avro: %d rows from %s", len(df), filepath)
    return df


# Kafka + Avro + Schema Registry pattern
KAFKA_AVRO_EXAMPLE: str = """
# Requires: confluent-kafka, confluent-kafka[avro]
from confluent_kafka.avro import AvroProducer, AvroConsumer

producer = AvroProducer(
    {"bootstrap.servers": "localhost:9092",
     "schema.registry.url": "http://localhost:8081"},
    default_value_schema=parsed_schema,
)
producer.produce(topic="user-events", value=record)
producer.flush()
"""
```

---

## 9. Delta Lake {#delta}

**When to use**: Lakehouse architectures requiring ACID transactions, upserts (merge),
schema enforcement, and time travel (data versioning) on top of a Data Lake. The
default table format in Databricks. Ideal for Silver and Gold layers.

**Key features not available in plain Parquet**:
- **ACID transactions**: Concurrent reads and writes without corruption
- **Time travel**: Query any previous version of a table by timestamp or version number
- **Merge/Upsert**: `MERGE INTO` semantics — insert new, update existing, delete stale records
- **Schema enforcement**: Rejects writes that violate the table schema
- **Schema evolution**: Controlled addition of new columns with `overwriteSchema`
- **Vacuum**: Remove old file versions to reclaim storage

```python
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from deltalake import DeltaTable, write_deltalake
from deltalake.writer import write_deltalake

logger = logging.getLogger(__name__)

# --- Constants ---
DELTA_STORAGE_PATH: str = "s3://bucket/delta/table_name"  # or local path
DELTA_RETENTION_HOURS: int = 168  # 7 days — minimum recommended retention


def write_delta(
    df: pd.DataFrame,
    table_path: str | Path,
    mode: str = "append",
    partition_by: list[str] | None = None,
    overwrite_schema: bool = False,
) -> None:
    """
    Write a DataFrame to a Delta Lake table.

    Args:
        mode: 'append', 'overwrite', or 'error' (fail if table exists).
        partition_by: Columns to partition by for query optimization.
        overwrite_schema: Allow schema evolution on overwrite. Use with caution.
    """
    write_deltalake(
        str(table_path),
        df,
        mode=mode,
        partition_by=partition_by,
        overwrite_schema=overwrite_schema,
    )
    logger.info("Written Delta table (%s mode) to %s", mode, table_path)


def read_delta(
    table_path: str | Path,
    version: int | None = None,
    timestamp: str | None = None,
) -> pd.DataFrame:
    """
    Read a Delta Lake table, with optional time travel.

    Args:
        version: Specific version number to read (e.g., version=5).
        timestamp: ISO timestamp string to read table as of that point in time
                   (e.g., "2024-01-15T10:00:00").

    Returns:
        DataFrame at the specified version or latest if neither is provided.
    """
    dt = DeltaTable(str(table_path))

    if version is not None:
        dt.load_as_version(version)
        logger.info("Reading Delta table version %d from %s", version, table_path)
    elif timestamp is not None:
        dt.load_as_version(timestamp)
        logger.info("Reading Delta table as of %s from %s", timestamp, table_path)

    return dt.to_pandas()


def upsert_delta(
    source_df: pd.DataFrame,
    table_path: str | Path,
    merge_keys: list[str],
) -> None:
    """
    Merge (upsert) source data into a Delta table.
    Inserts new records; updates existing ones matched on merge_keys.

    Args:
        merge_keys: Columns that uniquely identify a record (e.g., ['id', 'date']).
    """
    from deltalake import write_deltalake
    import pyarrow as pa

    dt = DeltaTable(str(table_path))
    source_table = pa.Table.from_pandas(source_df)

    predicate = " AND ".join(
        [f"source.{k} = target.{k}" for k in merge_keys]
    )

    (
        dt.merge(
            source=source_table,
            predicate=predicate,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )
    logger.info("Upsert complete on Delta table at %s", table_path)


def vacuum_delta(table_path: str | Path, retention_hours: int = DELTA_RETENTION_HOURS) -> None:
    """
    Remove old Parquet files no longer referenced by the Delta log.
    Reclaims storage. Do NOT set retention below 168h (7 days) in production
    to avoid breaking concurrent readers.
    """
    dt = DeltaTable(str(table_path))
    dt.vacuum(retention_hours=retention_hours, dry_run=False)
    logger.info("Vacuum complete on %s (retention: %dh)", table_path, retention_hours)


def inspect_delta_history(table_path: str | Path, limit: int = 10) -> pd.DataFrame:
    """Return the operation history of a Delta table (last N versions)."""
    dt = DeltaTable(str(table_path))
    history = pd.DataFrame(dt.history(limit=limit))
    logger.info("Delta history:\n%s", history[["version", "timestamp", "operation"]].to_string())
    return history
```

### PySpark + Delta Lake

```python
# PySpark Delta — required for large-scale production workloads
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("delta_pipeline")
    .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.1.0")
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    .getOrCreate()
)

# Write Delta
df.write.format("delta").mode("overwrite").partitionBy("year", "month") \
    .save("s3://bucket/silver/events")

# Read with time travel
df_v3 = spark.read.format("delta").option("versionAsOf", 3) \
    .load("s3://bucket/silver/events")

# Merge / upsert
spark.sql("""
    MERGE INTO silver.events AS target
    USING source_updates AS source
    ON target.event_id = source.event_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")
```

---

## 10. Apache Iceberg {#iceberg}

**When to use**: Multi-engine open Lakehouse architectures where data must be read
and written by different engines (Spark, Trino, Flink, Athena, Snowflake, Hive) without
vendor lock-in. AWS Glue, AWS Athena, and Snowflake have native Iceberg support.
The open-source alternative to Delta Lake.

**Key features vs. Delta Lake**:
- **Engine-agnostic**: Native support across Spark, Trino, Flink, Athena, Hive, Snowflake
- **Hidden partitioning**: Iceberg computes partition values automatically — no partition
  column transforms needed in queries
- **Partition evolution**: Change partitioning strategy on existing tables without rewriting data
- **Row-level deletes**: Supports positional and equality deletes without full file rewrites
- **Branching & tagging**: Create named snapshots (branches/tags) for audit, testing, and rollback
- **Underlying file format**: Can use Parquet, ORC, or Avro as the physical file format

```python
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    LongType, StringType, TimestampType, NestedField
)

logger = logging.getLogger(__name__)

# --- Constants ---
ICEBERG_CATALOG_NAME: str = "default"
ICEBERG_NAMESPACE: str   = "analytics"
ICEBERG_TABLE_NAME: str  = "user_events"


def get_iceberg_catalog(catalog_name: str = ICEBERG_CATALOG_NAME) -> object:
    """
    Load an Iceberg catalog. Supports REST, Hive Metastore, AWS Glue, and local.

    Catalog configuration is externalized in ~/.pyiceberg.yaml or environment variables.
    Example REST catalog config:
        catalog:
          default:
            type: rest
            uri: https://catalog.example.com
            warehouse: s3://bucket/warehouse
    """
    return load_catalog(catalog_name)


def read_iceberg(
    namespace: str = ICEBERG_NAMESPACE,
    table_name: str = ICEBERG_TABLE_NAME,
    snapshot_id: int | None = None,
) -> pd.DataFrame:
    """
    Read an Iceberg table into a DataFrame.

    Args:
        snapshot_id: Optional snapshot ID for time travel.
                     Omit to read the current (latest) snapshot.

    Returns:
        DataFrame with all or snapshot-specific data.
    """
    catalog = get_iceberg_catalog()
    table = catalog.load_table(f"{namespace}.{table_name}")

    scan = table.scan(snapshot_id=snapshot_id) if snapshot_id else table.scan()
    df = scan.to_pandas()
    logger.info("Loaded Iceberg table %s.%s: %d rows", namespace, table_name, len(df))
    return df


def write_iceberg_overwrite(
    df: pd.DataFrame,
    namespace: str = ICEBERG_NAMESPACE,
    table_name: str = ICEBERG_TABLE_NAME,
) -> None:
    """
    Overwrite an Iceberg table with a new DataFrame.
    Creates the table if it does not exist (infers schema from DataFrame).
    """
    import pyarrow as pa
    catalog = get_iceberg_catalog()
    full_name = f"{namespace}.{table_name}"

    arrow_table = pa.Table.from_pandas(df)
    try:
        table = catalog.load_table(full_name)
        table.overwrite(arrow_table)
        logger.info("Overwrote Iceberg table %s", full_name)
    except Exception:
        catalog.create_table(full_name, schema=arrow_table.schema)
        table = catalog.load_table(full_name)
        table.append(arrow_table)
        logger.info("Created and populated Iceberg table %s", full_name)


# PySpark + Iceberg — production pattern
PYSPARK_ICEBERG_EXAMPLE: str = """
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("iceberg_pipeline")
    .config("spark.jars.packages",
            "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0")
    .config("spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .config("spark.sql.catalog.glue_catalog",
            "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.glue_catalog.catalog-impl",
            "org.apache.iceberg.aws.glue.GlueCatalog")
    .config("spark.sql.catalog.glue_catalog.warehouse", "s3://bucket/warehouse")
    .getOrCreate()
)

# Write Iceberg
df.writeTo("glue_catalog.analytics.user_events") \\
    .partitionedBy("days(event_date)") \\
    .createOrReplace()

# Time travel — read specific snapshot
df_snapshot = spark.read.format("iceberg") \\
    .option("snapshot-id", "8270633197232459489") \\
    .load("glue_catalog.analytics.user_events")

# Schema evolution — add a column safely
spark.sql(\"\"\"
    ALTER TABLE glue_catalog.analytics.user_events
    ADD COLUMN session_duration BIGINT
\"\"\")

# Partition evolution — change strategy without rewriting data
spark.sql(\"\"\"
    ALTER TABLE glue_catalog.analytics.user_events
    REPLACE PARTITION FIELD days(event_date) WITH months(event_date)
\"\"\")
"""
```

### Delta Lake vs. Apache Iceberg — Head-to-Head

| Dimension | Delta Lake | Apache Iceberg |
|---|---|---|
| **Primary ecosystem** | Databricks, Azure | AWS, multi-cloud, open-source |
| **Engine support** | Spark (native), Trino (connector), Flink (connector) | Spark, Trino, Flink, Athena, Snowflake, Hive (all native) |
| **Vendor lock-in risk** | Moderate (Databricks-originated) | Low (Apache Foundation) |
| **Hidden partitioning** | ❌ Manual partition columns | ✅ Automatic, query-transparent |
| **Partition evolution** | ⚠️ Limited | ✅ Full, no data rewrite required |
| **Branching / tagging** | ❌ Not supported | ✅ Native |
| **Row-level deletes** | ✅ Supported | ✅ Supported (more efficient) |
| **AWS Glue / Athena native** | ⚠️ Connector needed | ✅ Native support |
| **Maturity** | ✅ Production-proven at massive scale | ✅ Rapidly maturing, Netflix/Apple/LinkedIn scale |
| **Community** | Linux Foundation Delta | Apache Software Foundation |

**Decision rule**: Choose **Delta Lake** if your primary compute is Databricks or Azure Synapse.
Choose **Apache Iceberg** if you need multi-engine compatibility, are on AWS, or want to
avoid vendor dependency.

---

## 11. Quick Reference Card {#quick-ref}

```
FORMAT SELECTION — ONE-LINE RULES

CSV      → Human needs to open it in Excel, or it's < 100MB and schema doesn't matter
JSON     → API payload, config file, or the data is genuinely semi-structured
Parquet  → Default for all batch analytics. When in doubt, use Parquet.
ORC      → Your team runs Hive queries and the Hadoop/Hive ecosystem owns the data
Avro     → Kafka message, streaming event, or you need schema versioning between services
Delta    → You need ACID + upserts + time travel and your compute is Databricks / Azure
Iceberg  → You need ACID + upserts + time travel and you need multi-engine or AWS native

COMPRESSION GUIDE
Snappy   → Default. Balanced speed vs. ratio. Best for Spark workloads.
Zstd     → Better compression ratio than Snappy. Use for cold storage / archival.
Gzip     → High compression, slower. Use for CSV exports sent to external parties.
Deflate  → Avro-specific. Comparable to Gzip for streaming payloads.

NEVER DO THIS
✗ Store Gold-layer data as CSV
✗ Use JSON for analytical queries (full row scan = no predicate pushdown)
✗ Use Parquet when you need schema evolution in streaming (use Avro)
✗ Use plain Parquet when you need upserts (use Delta or Iceberg instead)
✗ Use ORC outside a Hive/Hadoop ecosystem — Parquet has better universal support
```
