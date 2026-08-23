# Performance Optimization

> **Sources**: Delta Lake Optimization. https://docs.databricks.com/en/delta/optimize.html
> Liquid Clustering. https://docs.databricks.com/en/delta/clustering.html
> Z-Ordering. https://docs.databricks.com/en/delta/data-skipping.html
> Photon. https://docs.databricks.com/en/compute/photon.html

## Table of Contents

1. [Optimization Strategy Selection](#strategy)
2. [OPTIMIZE — File Compaction](#optimize)
3. [Z-Ordering — Column Co-location](#zorder)
4. [Liquid Clustering — Adaptive Partitioning](#liquid)
5. [Liquid Clustering vs Z-Ordering vs Static Partitioning](#comparison)
6. [VACUUM — File Cleanup](#vacuum)
7. [Delta Cache — Disk-Level Caching](#delta-cache)
8. [Photon — Vectorized Execution](#photon)
9. [Adaptive Query Execution (AQE)](#aqe)
10. [Bloom Filters](#bloom-filters)
11. [Statistics Collection](#statistics)
12. [Write Optimization](#write-optimization)
13. [Optimization Scheduling Template](#scheduling)

---

## 1. Optimization Strategy Selection {#strategy}

Apply strategies in this priority order — each builds on the previous:

| Priority | Strategy | Impact | When to apply |
|---|---|---|---|
| 1 | **Write optimization** (`optimizeWrite`, `autoCompact`) | Prevents small-file creation | Always on. Enable via Spark config. |
| 2 | **ANALYZE TABLE** | Enables cost-based query optimization | After initial data load; repeat when data distribution changes significantly. |
| 3 | **Liquid clustering** (preferred) | Data skipping on multiple columns; adaptive | New tables or tables with evolving query patterns. Requires DBR 13.2+. |
| 4 | **Z-Ordering** (legacy) | Data skipping on specific columns; static | Existing tables not yet migrated to liquid clustering; stable, known query patterns. |
| 5 | **OPTIMIZE** (compaction) | Reduces file count for scan efficiency | Scheduled regularly (daily for active tables). |
| 6 | **VACUUM** | Reclaims storage from deleted files | Scheduled (weekly or per retention policy). |
| 7 | **Delta cache** | Disk-level cache for repeated reads | Auto on Databricks; verify cluster has SSDs. |
| 8 | **Photon** | Vectorized CPU execution | Enable on cluster/SQL Warehouse for SQL-heavy ETL. |
| 9 | **Bloom filters** | Point-lookup data skipping | Tables with high-cardinality key lookups (UUID, email). |

---

## 2. OPTIMIZE — File Compaction {#optimize}

Delta tables accumulate small files from streaming micro-batches and incremental writes.
`OPTIMIZE` compacts these into larger files (target: 1GB per file), improving scan
throughput by reducing file-open overhead.

```sql
-- Compact all files in the table
OPTIMIZE prod_sales.orders.silver_orders;

-- Compact with Z-Ordering (combined in one command)
OPTIMIZE prod_sales.orders.silver_orders
ZORDER BY (order_date, region);

-- Compact a specific partition only (for partitioned tables)
OPTIMIZE prod_sales.orders.silver_orders
WHERE order_date >= CURRENT_DATE - INTERVAL 7 DAYS;
```

**Target file size**: Databricks default target is 1GB per file. For tables queried with
highly selective filters on small date ranges, smaller target files (128-256MB) can
improve individual query speed at the cost of more files to scan. Adjust via table property:

```sql
ALTER TABLE prod_sales.orders.silver_orders
SET TBLPROPERTIES ('delta.targetFileSize' = '134217728');   -- 128MB
```

**When to run**: schedule `OPTIMIZE` via a Lakeflow Job after the primary write pipeline
completes (e.g., after the Silver DLT pipeline update). Do not run `OPTIMIZE` inside the
DLT pipeline itself — DLT runs `OPTIMIZE` automatically via its maintenance tasks.

---

## 3. Z-Ordering — Column Co-location {#zorder}

Z-Ordering physically co-locates related data within files based on specified column
values, improving data skipping effectiveness. The query planner skips entire files if
their min/max statistics do not overlap the query filter.

```sql
-- Z-Order on the columns most commonly used as filters
OPTIMIZE prod_sales.orders.silver_orders
ZORDER BY (order_date, customer_id);

-- Verify data skipping effectiveness via Delta metrics
DESCRIBE DETAIL prod_sales.orders.silver_orders;
-- Look at: numFilesAdded, numFilesRemoved, numBytesAdded, numBytesRemoved
```

**Z-Ordering limitations**:
- Static: the ZORDER BY columns are specified at OPTIMIZE time. Changing them requires
  a full rewrite.
- Limited cardinality: Z-Ordering degrades with more than 3-4 columns (curse of
  dimensionality in the Z-curve).
- Requires re-running `OPTIMIZE ... ZORDER BY` periodically as new data arrives — stale
  files added since the last OPTIMIZE are not ordered.

**Superseded by liquid clustering for new tables** (see §4).

---

## 4. Liquid Clustering — Adaptive Partitioning {#liquid}

Liquid clustering (GA as of Databricks Runtime 13.2) replaces both static partitioning
and Z-Ordering with an adaptive, partition-free approach. Data is clustered incrementally
on every write — no periodic full rewrite required.

```sql
-- Enable liquid clustering when creating a new table
CREATE TABLE prod_sales.orders.silver_orders_v2 (
  order_id    STRING NOT NULL,
  customer_id STRING,
  amount      DOUBLE,
  order_date  DATE,
  region      STRING
)
USING DELTA
CLUSTER BY (order_date, region);   -- cluster by columns used in frequent filters

-- Enable on an existing table (migrates from static partitioning or Z-Ordering)
ALTER TABLE prod_sales.orders.silver_orders
CLUSTER BY (order_date, region);

-- Run OPTIMIZE to cluster existing unordered data (incremental writes are auto-clustered)
OPTIMIZE prod_sales.orders.silver_orders;
```

**Changing cluster columns**: liquid clustering columns can be changed without rewriting
the entire table — only newly written files use the new cluster columns.

```sql
-- Change cluster columns (e.g., add customer_id for a new query pattern)
ALTER TABLE prod_sales.orders.silver_orders
CLUSTER BY (order_date, region, customer_id);

-- Verify clustering status
DESCRIBE DETAIL prod_sales.orders.silver_orders;
-- Look at: clusteringColumns field
```

**Liquid clustering automatically applies during writes** when `OPTIMIZE` is triggered.
On Databricks (not OSS Delta Lake), the platform triggers automatic incremental
`OPTIMIZE` for tables with liquid clustering enabled — reducing the need for scheduled
`OPTIMIZE` jobs.

---

## 5. Liquid Clustering vs Z-Ordering vs Static Partitioning {#comparison}

| Dimension | Static Partitioning | Z-Ordering | Liquid Clustering |
|---|---|---|---|
| Column change cost | Full rewrite required | Full rewrite (re-OPTIMIZE) | Incremental (no full rewrite) |
| Column cardinality limits | Low (< 10K distinct values) | 1-3 columns practical | 3-4 columns practical |
| Query pattern adaptability | Rigid — partition column fixed at DDL | Rigid — re-OPTIMIZE on new patterns | Adaptive — change columns without rewrite |
| Write overhead | None at write time | None at write time; OPTIMIZE required later | Incremental clustering at write time |
| Small file handling | Manual OPTIMIZE required | Manual OPTIMIZE required | Auto-OPTIMIZE on Databricks |
| DBR requirement | Any | Any Delta | DBR 13.2+ |
| Recommendation | Avoid for new tables | Use only if DBR < 13.2 | Default for all new tables on DBR 13.2+ |

**Migration from static partitioning to liquid clustering**:

```sql
-- Step 1: Add liquid clustering to a partitioned table
ALTER TABLE prod_sales.orders.silver_orders
CLUSTER BY (order_date, region);    -- same columns as old partition

-- Step 2: Remove the partition (optional — liquid clustering works with or without partitions)
-- Note: removing partitions requires a full rewrite in Delta
-- If the partition is coarse (year, month), keep it alongside liquid clustering for scan efficiency

-- Step 3: Run OPTIMIZE to cluster all existing data
OPTIMIZE prod_sales.orders.silver_orders;
```

---

## 6. VACUUM — File Cleanup {#vacuum}

`VACUUM` removes Delta table files that are no longer referenced by any table version
within the retention period. Without VACUUM, deleted or overwritten files accumulate
indefinitely on cloud storage.

```sql
-- Default retention: 7 days (168 hours). Files within this window are preserved for time travel.
VACUUM prod_sales.orders.silver_orders;

-- Explicit retention (must be >= 7 days unless safety check is disabled — do not disable)
VACUUM prod_sales.orders.silver_orders RETAIN 720 HOURS;   -- 30 days

-- Dry run: see which files would be deleted without deleting them
VACUUM prod_sales.orders.silver_orders DRY RUN;
```

**VACUUM and time travel**: after `VACUUM`, you cannot time-travel to versions older than
the retention period. Balance retention against storage cost:

| Use case | Recommended retention |
|---|---|
| Development / staging | 7 days (default) |
| Production ETL tables | 30-90 days |
| Audit-critical tables | 365 days or archival to separate storage |
| Feature Store tables | 7-30 days (point-in-time lookups use timestamp, not version) |

```python
# Schedule VACUUM via Lakeflow Jobs
# Run weekly, after OPTIMIZE, on a small cluster (single-node sufficient)
spark.sql("""
    VACUUM prod_sales.orders.silver_orders
    RETAIN 720 HOURS
""")
```

---

## 7. Delta Cache — Disk-Level Caching {#delta-cache}

Delta cache (disk-based, distinct from Spark's in-memory cache) stores decompressed
Parquet data from Delta table files on local SSD attached to Databricks worker nodes.
Subsequent reads of the same data are served from disk rather than cloud object storage,
substantially reducing I/O latency.

**Delta cache is enabled automatically on Databricks** for instance types with local SSDs
(e.g., AWS `i3`, `d3`; Azure `L` series). Standard instance types without local SSD do
not benefit from Delta cache.

```python
# Verify Delta cache is active
spark.conf.get("spark.databricks.io.cache.enabled")    # "true" if active

# Check cache hit rate in Spark UI → Storage tab
# High cache miss rate on repeatedly scanned tables → consider instance type with local SSD

# Explicitly cache a frequently joined lookup table in memory (Spark cache, not Delta cache)
spark.table("prod_sales.dimensions.dim_region").cache()
spark.table("prod_sales.dimensions.dim_region").count()   # materialize the cache

# Release after use
spark.table("prod_sales.dimensions.dim_region").unpersist()
```

---

## 8. Photon — Vectorized Execution {#photon}

Photon (covered in `references/cluster-compute.md` §4) accelerates SQL and Spark SQL
operations via C++ vectorized execution. From a performance tuning perspective:

```python
# Verify Photon is active
spark.conf.get("spark.databricks.photon.enabled")   # "true"

# Photon accelerates: SQL SELECT/GROUP BY/JOIN/ORDER BY, Delta scans, OPTIMIZE
# Photon does NOT accelerate: Python/Pandas UDFs, custom RDD operations

# Force Photon-compatible query: replace Python UDFs with built-in Spark SQL functions
# BAD: Python UDF (bypasses Photon)
from pyspark.sql.functions import udf
from pyspark.sql.types import DoubleType

@udf(returnType=DoubleType())
def apply_discount(amount: float, discount: float) -> float:
    return amount * (1 - discount)

# GOOD: Built-in SQL expression (Photon-accelerated)
from pyspark.sql import functions as F
df.withColumn("discounted_amount", F.col("amount") * (1 - F.col("discount")))
```

---

## 9. Adaptive Query Execution (AQE) {#aqe}

AQE (enabled by default in Spark 3.x / Databricks) re-optimizes the physical query plan
at runtime based on actual data statistics collected during execution.

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# AQE is on by default in Databricks — verify:
spark.conf.get("spark.sql.adaptive.enabled")                         # "true"
spark.conf.get("spark.sql.adaptive.coalescePartitions.enabled")      # "true"
spark.conf.get("spark.sql.adaptive.skewJoin.enabled")                # "true"

# AQE features:
# - Coalesces shuffle partitions: reduces 200 default partitions to the actual data size
# - Converts sort-merge joins to broadcast joins when one side is small at runtime
# - Handles data skew: splits oversized partitions into smaller ones

# When to tune manually:
# Skewed join causing one task to run 10x longer than others → diagnose via Spark UI
# Solution: AQE handles automatically, but set skewJoin threshold if needed
spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionFactor", "5")    # default: 5
spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "256MB")
```

---

## 10. Bloom Filters {#bloom-filters}

Bloom filters are probabilistic data structures that enable fast point lookups on
high-cardinality columns (UUIDs, email addresses, order IDs). They allow the reader
to skip entire files for rows that definitely do not match the filter predicate.

```sql
-- Create bloom filter index on a high-cardinality column
CREATE BLOOMFILTER INDEX ON TABLE prod_sales.orders.silver_orders
FOR COLUMNS (order_id OPTIONS (fpp=0.1, numItems=10000000));
-- fpp: false positive probability (0.1 = 10% false positive rate)
-- numItems: expected distinct values (set to ~2x actual distinct count)

-- Bloom filter benefits:
-- Query: SELECT * FROM silver_orders WHERE order_id = 'ORD-abc123'
-- Without bloom: scans all files checking if order_id exists
-- With bloom: skips files where bloom filter indicates order_id is absent (90% skip rate)

-- Drop a bloom filter index
DROP BLOOMFILTER INDEX ON TABLE prod_sales.orders.silver_orders
FOR COLUMNS (order_id);
```

**When to use bloom filters**: point lookups on high-cardinality string columns that are
NOT good candidates for Z-Ordering or liquid clustering (e.g., UUIDs — too many distinct
values for effective range skipping, but bloom filter enables effective equality skipping).

---

## 11. Statistics Collection {#statistics}

Delta table statistics (min/max per column per file) power data skipping. Statistics are
collected automatically on write for the first 32 columns. `ANALYZE TABLE` collects
full column statistics for the query optimizer.

```sql
-- Collect statistics for all columns (enables cost-based join reordering, filter pushdown)
ANALYZE TABLE prod_sales.orders.silver_orders COMPUTE STATISTICS FOR ALL COLUMNS;

-- Collect statistics for specific columns only (faster for wide tables)
ANALYZE TABLE prod_sales.orders.silver_orders
COMPUTE STATISTICS FOR COLUMNS (order_id, order_date, region, amount);

-- Configure how many columns Delta tracks statistics for automatically
ALTER TABLE prod_sales.orders.silver_orders
SET TBLPROPERTIES ('delta.dataSkippingNumIndexedCols' = '64');   -- default: 32
```

---

## 12. Write Optimization {#write-optimization}

Prevent small files from accumulating in the first place:

```python
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")
# Auto-coalesces output files to ~128MB during write, preventing small-file accumulation

spark.conf.set("spark.databricks.delta.autoCompact.enabled", "true")
# Automatically runs OPTIMIZE after significant small-file accumulation
# Threshold: default 50 files; configurable via delta.autoOptimize.autoCompact.minNumFiles

# Set at the table level (persists across sessions)
ALTER TABLE prod_sales.orders.silver_orders
SET TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact'   = 'true'
);
```

---

## 13. Optimization Scheduling Template {#scheduling}

```yaml
# Lakeflow Job: daily optimization run after primary ETL pipeline
# Separate from ETL to avoid OPTIMIZE blocking ETL writes

resources:
  jobs:
    orders_optimize_job:
      name: "[${bundle.target}] Orders Table Optimization"
      schedule:
        quartz_cron_expression: "0 0 8 * * ?"   # 08:00 UTC daily (after 06:00 ETL)
        timezone_id: "UTC"
        pause_status: ${var.schedule_pause_status}
      job_clusters:
        - job_cluster_key: optimize_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: m5.xlarge             # small single-node sufficient for OPTIMIZE
            num_workers: 2
      tasks:
        - task_key: optimize_silver_orders
          sql_task:
            warehouse_id: ${var.sql_warehouse_id}
            query:
              query: |
                OPTIMIZE ${var.catalog}.orders.silver_orders;
                ANALYZE TABLE ${var.catalog}.orders.silver_orders COMPUTE STATISTICS FOR ALL COLUMNS;
          job_cluster_key: optimize_cluster

        - task_key: vacuum_silver_orders
          depends_on:
            - task_key: optimize_silver_orders
          sql_task:
            warehouse_id: ${var.sql_warehouse_id}
            query:
              query: |
                VACUUM ${var.catalog}.orders.silver_orders RETAIN 720 HOURS;
```
