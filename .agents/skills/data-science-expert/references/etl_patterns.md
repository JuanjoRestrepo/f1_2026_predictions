# ETL Design Patterns & Pipeline Templates

## Table of Contents

0. [PySpark vs. dbt — Architectural Decision Guide](#decision-guide)
1. [Environment Setup (uv + pyproject.toml)](#environment)
2. [Pandas / Polars Pipeline](#pandas-polars)
3. [PySpark Pipeline](#pyspark)
4. [dbt Model Pattern](#dbt)
5. [Airflow DAG Template](#airflow)
6. [Data Validation with Pandera / Great Expectations](#validation)

---

## 0. PySpark vs. dbt — Architectural Decision Guide {#decision-guide}

> **Core premise**: PySpark and dbt are not competing tools — they solve fundamentally
> different problems at different layers of the data architecture. The engineering decision
> is not _which one_, but _which one at which layer_, and whether the project warrants both.

### Strengths & Failure Modes

| Dimension             | PySpark                                                                  | dbt                                                                        |
| --------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| **Primary layer**     | Ingestion, raw processing, Data Lake                                     | Transformation, modeling, Data Warehouse                                   |
| **Data scale**        | Petabyte-scale distributed processing                                    | GB → low-TB structured data in a Warehouse                                 |
| **Data structure**    | Raw, semi-structured, unstructured, nested JSON, images, text, streaming | Clean, structured, relational data already in the Warehouse                |
| **Execution engine**  | Distributed cluster (YARN, Kubernetes, Databricks)                       | Delegates to the Warehouse engine (Snowflake, BigQuery, Redshift)          |
| **Streaming**         | Native (Structured Streaming, Kafka integration)                         | Not designed for streaming or near-real-time                               |
| **Complex joins**     | Handles multi-TB joins via partitioning and broadcast                    | Struggles with massive cross-table scans — saturates the Warehouse         |
| **Business logic**    | Low-level; verbose for pure SQL transformations                          | First-class SQL + Jinja; ideal for business rules, metrics, and Data Marts |
| **Testing & lineage** | Manual; requires custom test harness                                     | Built-in: `dbt test`, DAG lineage, documentation auto-generation           |
| **Team profile**      | Data engineers, ML engineers (Python/Scala)                              | Analytics engineers, data analysts (SQL-first)                             |

### Data Volume Decision Thresholds

| Zone                     | Data Range                                                     | Recommendation                                                         |
| ------------------------ | -------------------------------------------------------------- | ---------------------------------------------------------------------- |
| 🟢 **dbt Sweet Spot**    | GBs → a few TBs of clean, structured data                      | dbt only — incremental models, warehouse-native execution              |
| 🟡 **Warning Zone**      | Multi-TB joins, full-table scans, unoptimized models           | Audit dbt model design; consider pre-aggregating with PySpark upstream |
| 🔴 **PySpark Territory** | Raw TB → PB scale; semi/unstructured; queries exceeding 30 min | PySpark for ingestion and heavy lifting; dbt for downstream modeling   |

**Rule of thumb**: If your dbt model scans billions of rows on every run, you are not
scaling — you are surviving. Move that computation upstream to PySpark.

### Project-Context Decision Matrix

Apply this logic when assessing a new project or pipeline:

```
1. Where does the data live?
   ├── Raw files (S3, GCS, ADLS, HDFS) at scale → PySpark
   └── Already in a Warehouse (Snowflake, BigQuery, Redshift) → dbt

2. What is the data volume?
   ├── < a few TBs, structured → dbt
   └── Multi-TB, raw, or growing rapidly → PySpark → then dbt

3. What is the transformation complexity?
   ├── Business logic, aggregations, joins on clean data → dbt
   ├── Heavy parsing, nested JSON flattening, regex, NLP → PySpark
   └── ML feature engineering at scale → PySpark (or Spark MLlib)

4. Does the pipeline require real-time or near-real-time processing?
   ├── YES → PySpark Structured Streaming + Kafka (dbt is not viable)
   └── NO  → Batch pipeline; evaluate volume to choose dbt vs. PySpark

5. Who owns and maintains the pipeline?
   ├── Data / ML engineering team → PySpark (Python-native, code-first)
   └── Analytics engineering / SQL-first team → dbt
```

### Recommended Production Architecture — Combined Pattern

For scalable production pipelines, enforce a strict separation of concerns across layers:

```
Raw Sources
    │
    ▼
[Bronze Layer]  ← PySpark
    Raw ingestion, schema inference, format conversion (Parquet/Delta),
    deduplication, initial quality checks. Output to Data Lake.
    │
    ▼
[Silver Layer]  ← PySpark
    Heavy transformations: unnesting, joining large datasets, cleaning,
    ML feature engineering. Output clean, typed tables to the Warehouse.
    │
    ▼
[Gold Layer]    ← dbt
    Business logic, metric definitions, Data Mart modeling,
    aggregations, BI-ready tables. Consumed by dashboards and reports.
    │
    ▼
BI / Analytics / ML Feature Store
```

**Orchestration**: Airflow (or Prefect/Dagster) coordinates the full flow —
PySpark jobs run first, dbt models run after warehouse load completes.

**Data flow summary**:
`Data Sources → Data Lake [PySpark] → Warehouse [PySpark load] → dbt transforms → BI / Analytics`

**Storage format per layer** — always align format to the layer's access pattern and guarantees required:

| Layer                        | Recommended Format                              | Rationale                                                                               |
| ---------------------------- | ----------------------------------------------- | --------------------------------------------------------------------------------------- |
| 🥉 **Bronze (Raw)**          | Avro (streaming) / Parquet (batch) / JSON (API) | Preserve source structure; Avro for Kafka; Parquet for batch files                      |
| 🥈 **Silver (Cleaned)**      | Delta Lake or Apache Iceberg                    | ACID guarantees for upserts/deduplication; schema enforcement; time travel for rollback |
| 🥇 **Gold (Business-ready)** | Delta Lake / Iceberg (via dbt)                  | Schema-enforced, versioned, BI-consumable; never CSV or raw JSON at this layer          |

See `references/data_formats.md` for the full format decision guide and read/write code.

### When to Use Only One Tool

**dbt only** — appropriate when:

- All source data already resides in a mature Warehouse
- Data volumes are manageable within Warehouse compute budgets
- The team is SQL-first with no distributed compute infrastructure
- The project is analytics-focused: reporting, dashboards, Data Marts

**PySpark only** — appropriate when:

- The project is a pure Data Lake / Lakehouse architecture (no Warehouse)
- All transformations are engineering-heavy (streaming, ML pipelines, unstructured data)
- The output is consumed directly by ML models or operational systems, not BI tools

---

## 1. Environment Setup (uv + pyproject.toml) {#environment}

All data engineering projects use `uv` for environment and dependency management.
Never use `pip`, `conda`, or `requirements.txt`.

```bash
# Initialize project
uv init etl_project && cd etl_project
uv python pin 3.12

# Create .venv
uv venv .venv --python 3.12
source .venv/bin/activate

# Add ETL-specific dependencies
uv add pandas polars sqlalchemy pandera great-expectations \
       apache-airflow pyspark dbt-core pydantic pyyaml httpx

# Add dev tools (Ruff + mypy mandatory)
uv add --dev ruff mypy pytest pytest-cov ipykernel

# Sync all dependencies
uv sync
```

**Standard `pyproject.toml` for ETL projects** — include `[tool.ruff]` and `[tool.mypy]`
sections as defined in the main SKILL.md Code Quality & Environment Standards section.

---

## 1. Pandas / Polars Pipeline {#pandas-polars}

```python
import pandas as pd
import polars as pl
import logging
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import pandera as pa
from pandera import Column, DataFrameSchema

logger = logging.getLogger(__name__)

# --- Configuration ---
@dataclass
class PipelineConfig:
    """Externalized pipeline configuration."""
    input_path: str
    output_path: str
    target_column: str
    missing_threshold: float = 0.5
    categorical_encoding: str = "onehot"  # or 'label', 'target'

    @classmethod
    def from_yaml(cls, path: str) -> "PipelineConfig":
        with open(path) as f:
            return cls(**yaml.safe_load(f))


# --- Schema Validation ---
INPUT_SCHEMA = DataFrameSchema({
    "id": Column(int, nullable=False),
    "date": Column(str, nullable=False),
    "value": Column(float, nullable=True),
})


# --- Pipeline Steps (modular, idempotent) ---
def ingest(config: PipelineConfig) -> pd.DataFrame:
    """Load raw data and validate against input schema."""
    path = Path(config.input_path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path)
    INPUT_SCHEMA.validate(df)
    logger.info("Ingested %d rows from %s", len(df), path)
    return df


def clean(df: pd.DataFrame, missing_threshold: float) -> pd.DataFrame:
    """Drop high-null columns, fill remaining nulls, deduplicate."""
    null_rate = df.isnull().mean()
    cols_to_drop = null_rate[null_rate > missing_threshold].index.tolist()
    df = df.drop(columns=cols_to_drop)
    logger.info("Dropped columns (>%.0f%% missing): %s", missing_threshold * 100, cols_to_drop)

    df = df.drop_duplicates()
    df = df.fillna(df.median(numeric_only=True))
    return df


def transform(df: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """Apply feature engineering transformations."""
    # Encode categoricals
    categorical_cols = df.select_dtypes(include="object").columns.difference([config.target_column])
    if config.categorical_encoding == "onehot":
        df = pd.get_dummies(df, columns=categorical_cols, drop_first=True)

    # Parse dates if present
    date_cols = df.filter(like="date").columns
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df[f"{col}_year"] = df[col].dt.year
        df[f"{col}_month"] = df[col].dt.month
        df[f"{col}_dayofweek"] = df[col].dt.dayofweek

    return df


def load(df: pd.DataFrame, output_path: str) -> None:
    """Persist transformed data to disk."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    logger.info("Saved %d rows to %s", len(df), output_path)


def run_pipeline(config_path: str) -> pd.DataFrame:
    """Orchestrate the full ETL pipeline."""
    config = PipelineConfig.from_yaml(config_path)
    df = ingest(config)
    df = clean(df, config.missing_threshold)
    df = transform(df, config)
    load(df, config.output_path)
    return df
```

---

## 2. PySpark Pipeline {#pyspark}

```python
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StructType
import logging

logger = logging.getLogger(__name__)

SPARK_APP_NAME: str = "etl_pipeline"
INPUT_FORMAT: str = "parquet"
OUTPUT_FORMAT: str = "delta"  # or 'parquet'


def create_spark_session(app_name: str = SPARK_APP_NAME) -> SparkSession:
    """Initialize SparkSession with sensible defaults."""
    return (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.shuffle.partitions", "200")
        .getOrCreate()
    )


def ingest_spark(spark: SparkSession, path: str, schema: StructType = None) -> DataFrame:
    """Read data with optional schema enforcement."""
    reader = spark.read.format(INPUT_FORMAT)
    if schema:
        reader = reader.schema(schema)
    df = reader.load(path)
    logger.info("Loaded %d rows from %s", df.count(), path)
    return df


def clean_spark(df: DataFrame, null_threshold: float = 0.5) -> DataFrame:
    """Remove high-null columns and deduplicate."""
    total = df.count()
    null_rates = {c: df.filter(F.col(c).isNull()).count() / total for c in df.columns}
    cols_to_drop = [c for c, r in null_rates.items() if r > null_threshold]
    df = df.drop(*cols_to_drop)
    df = df.dropDuplicates()
    return df


def write_spark(df: DataFrame, output_path: str, partition_cols: list[str] = None) -> None:
    """Write to output with optional partitioning."""
    writer = df.write.format(OUTPUT_FORMAT).mode("overwrite")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.save(output_path)
    logger.info("Written to %s", output_path)
```

---

## 3. dbt Model Pattern {#dbt}

```sql
-- models/marts/core/fact_orders.sql
-- Materialization: table (use 'incremental' for large datasets)
{{ config(
    materialized='incremental',
    unique_key='order_id',
    on_schema_change='fail'
) }}

WITH source AS (
    SELECT * FROM {{ source('raw', 'orders') }}
),

cleaned AS (
    SELECT
        order_id,
        customer_id,
        order_date::DATE                            AS order_date,
        COALESCE(total_amount, 0)                   AS total_amount,
        status
    FROM source
    WHERE order_id IS NOT NULL
),

enriched AS (
    SELECT
        c.*,
        DATE_TRUNC('month', c.order_date)           AS order_month,
        EXTRACT(DOW FROM c.order_date)              AS day_of_week
    FROM cleaned c
)

SELECT * FROM enriched
{% if is_incremental() %}
WHERE order_date > (SELECT MAX(order_date) FROM {{ this }})
{% endif %}
```

---

## 4. Airflow DAG Template {#airflow}

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
import logging

logger = logging.getLogger(__name__)

DEFAULT_ARGS: dict = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
}

with DAG(
    dag_id="etl_pipeline",
    default_args=DEFAULT_ARGS,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["etl", "data-engineering"],
) as dag:

    start = EmptyOperator(task_id="start")

    ingest_task = PythonOperator(
        task_id="ingest",
        python_callable=lambda: logger.info("Ingesting data..."),
    )

    transform_task = PythonOperator(
        task_id="transform",
        python_callable=lambda: logger.info("Transforming data..."),
    )

    load_task = PythonOperator(
        task_id="load",
        python_callable=lambda: logger.info("Loading data..."),
    )

    end = EmptyOperator(task_id="end")

    start >> ingest_task >> transform_task >> load_task >> end
```

---

## 5. Data Validation {#validation}

```python
import pandera as pa
from pandera import Column, DataFrameSchema, Check
import pandas as pd


# Define schema with business rules
ORDERS_SCHEMA = DataFrameSchema(
    columns={
        "order_id": Column(int, Check.greater_than(0), nullable=False),
        "total_amount": Column(float, Check.in_range(0, 1_000_000), nullable=False),
        "status": Column(str, Check.isin(["pending", "completed", "cancelled"])),
        "order_date": Column("datetime64[ns]", nullable=False),
    },
    checks=Check(lambda df: df["order_date"].max() <= pd.Timestamp.now()),
    coerce=True,
    strict=False,
)


def validate_dataframe(df: pd.DataFrame, schema: pa.DataFrameSchema) -> pd.DataFrame:
    """Validate DataFrame against schema; raise on violation."""
    try:
        validated = schema.validate(df, lazy=True)
        return validated
    except pa.errors.SchemaErrors as e:
        raise ValueError(f"Schema validation failed:\n{e.failure_cases}") from e
```
