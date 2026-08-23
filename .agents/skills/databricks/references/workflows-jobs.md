# Workflows and Jobs Orchestration

> **Sources**: Databricks Workflows Documentation.
> https://docs.databricks.com/en/workflows/index.html
> Jobs API 2.1. https://docs.databricks.com/en/workflows/jobs/jobs-api-2.1.html
> Task Orchestration. https://docs.databricks.com/en/workflows/jobs/jobs.html

## Table of Contents

1. [Orchestration Architecture](#architecture)
2. [Task Types](#task-types)
3. [Multi-Task Job DAG Design](#dag-design)
4. [Task Values: Inter-Task Data Passing](#task-values)
5. [Cluster Configuration per Task](#cluster-config)
6. [Job Parameters and Dynamic Values](#parameters)
7. [Retry Policies and Timeouts](#retry)
8. [Repair Runs](#repair)
9. [Scheduling](#scheduling)
10. [Notifications](#notifications)
11. [Orchestration vs DLT: When to Use Each](#vs-dlt)
12. [Full Job Bundle YAML Template](#template)

---

## 1. Orchestration Architecture {#architecture}

A Databricks **Job** is a named orchestration unit containing one or more **tasks**.
Tasks form a DAG (Directed Acyclic Graph) defined by `depends_on` relationships. Jobs
are submitted as **Runs** — each run is one execution of the job DAG, either triggered
manually, via schedule, or via REST API.

**Databricks Workflows vs Airflow**:

| Dimension | Databricks Workflows | Apache Airflow (MWAA / Composer / OSS) |
|---|---|---|
| Execution environment | Native Databricks — clusters provisioned automatically | External orchestrator calling Databricks via operator |
| Cluster lifecycle | Job cluster per run (automatic) | Databricks Operator submits to existing cluster or creates one |
| Task types | Notebook, Python script, JAR, DLT, dbt, SQL, HTTP, Power BI | Any operator (Python, Bash, HTTP, Databricks, dbt, etc.) |
| Monitoring | Databricks Workflows UI, REST API | Airflow DAG run UI, logs |
| Cross-system orchestration | Limited (HTTP task for REST calls) | Strong — can orchestrate non-Databricks systems natively |
| Recommended for | Databricks-only pipelines | Multi-system orchestration (Databricks + dbt Cloud + Salesforce + etc.) |

---

## 2. Task Types {#task-types}

| Task Type | Description | Use case |
|---|---|---|
| **Notebook** | Runs a Databricks notebook (Python, SQL, Scala, R). | Interactive-style ETL, EDA scripts, ad-hoc pipelines promoted to scheduled jobs. |
| **Python Script** | Runs a `.py` file from a Git repo or workspace. | Production ETL modules with `argparse` parameter injection. Preferred over notebooks for pure Python logic. |
| **Python Wheel** | Installs and runs an entry point from a `.whl` package. | Packaged, versioned ETL libraries with formal entrypoints. Highest production maturity. |
| **JAR** | Runs a Scala/Java `main()` method from a JAR. | Legacy Spark Scala pipelines. Avoid for new development — use Python or DLT. |
| **Delta Live Tables Pipeline** | Triggers a DLT pipeline update. | Embedding a DLT pipeline run within a broader workflow (e.g., ETL → ML → export). |
| **dbt** | Runs a dbt Cloud job or dbt Core project. | Analytics engineering transformation layer. |
| **SQL** | Executes a SQL query on a SQL Warehouse. | Data quality checks, stored procedure equivalents, Gold layer transformations. |
| **For Each** | Iterates a task over a list of inputs (dynamic fan-out). | Running the same transformation over a dynamic list of tables or partitions. |
| **HTTP** | Makes an HTTP request. | Triggering webhooks, external API calls, Slack notifications with custom payloads. |
| **Run Job** | Triggers another Databricks Job. | Composing modular sub-jobs into a parent orchestration job. |

---

## 3. Multi-Task Job DAG Design {#dag-design}

Tasks run in parallel by default unless `depends_on` is specified. Always define
explicit dependencies to enforce ordering and prevent race conditions.

```yaml
# Example: ETL → validation → ML training → model registration
tasks:
  - task_key: ingest_bronze
    description: "Auto Loader ingestion from S3 to Bronze Delta"
    python_wheel_task:
      package_name: orders_etl
      entry_point: ingest
    job_cluster_key: etl_cluster

  - task_key: transform_silver
    depends_on:
      - task_key: ingest_bronze
    pipeline_task:
      pipeline_id: "{{pipeline_id}}"      # DLT pipeline ID from DABs variable
    # No cluster needed — DLT manages its own compute

  - task_key: validate_silver
    depends_on:
      - task_key: transform_silver
    python_wheel_task:
      package_name: orders_etl
      entry_point: validate
      parameters: ["--table", "prod_sales.orders.silver_orders"]
    job_cluster_key: etl_cluster

  - task_key: train_model
    depends_on:
      - task_key: validate_silver
    notebook_task:
      notebook_path: /pipelines/ml/train_churn_model
      base_parameters:
        experiment_name: "/Shared/churn-model"
        data_table: "prod_sales.orders.silver_orders"
    job_cluster_key: ml_cluster      # separate ML cluster with GPU/ML Runtime

  - task_key: register_model
    depends_on:
      - task_key: train_model
    python_wheel_task:
      package_name: orders_etl
      entry_point: register_model
    job_cluster_key: etl_cluster
```

**DAG design principles**:
- Group tasks that share compute onto the same `job_cluster_key` — consecutive tasks
  on the same cluster reuse the warm executor JVMs, dramatically reducing runtime vs
  a per-task cluster.
- Isolate ML training tasks on a separate cluster (ML Runtime, fixed-size) from ETL
  tasks (Standard Runtime, autoscaling).
- Use `For Each` tasks when the number of parallelizable units is data-driven (unknown
  at DAG definition time).

---

## 4. Task Values: Inter-Task Data Passing {#task-values}

Task values allow tasks to pass small amounts of structured data (strings, numbers,
JSON) to downstream tasks within the same run. They are the correct mechanism for
thread-safe inter-task communication — not shared Delta tables or DBFS paths.

```python
# Task A: produce a value and set it
from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()
dbutils = spark._jvm.com.databricks.dbutils_v1.DBUtilsHolder.dbutils()  # type: ignore

# Compute something in task A
processed_count: int = spark.table("prod_sales.orders.bronze_orders").count()
failed_records: int = (
    spark.table("prod_sales.orders.bronze_orders_quarantine").count()
)

# Set task output values — available to downstream tasks
dbutils.jobs.taskValues.set(key="processed_count", value=processed_count)
dbutils.jobs.taskValues.set(key="failed_records", value=failed_records)
```

```python
# Task B (downstream): read values set by Task A
processed = dbutils.jobs.taskValues.get(
    taskKey="ingest_bronze",
    key="processed_count",
    default=0,          # returned if key does not exist (e.g., task was skipped)
    debugValue=100,     # value used when running notebook interactively (not in a job)
)

if processed == 0:
    raise ValueError("Task A processed 0 records — aborting downstream steps.")
```

**Task value constraints**: values must be JSON-serializable scalars or collections
(string, int, float, bool, list, dict). Maximum value size is 48KB. Do not use task
values to pass DataFrames, file paths to large datasets, or binary blobs — those belong
in Delta tables or Volumes.

---

## 5. Cluster Configuration per Task {#cluster-config}

Each task can use:
- A **job cluster** defined in the job's `job_clusters` section (shared across tasks
  in the same job — all tasks with the same `job_cluster_key` share the cluster).
- An **existing all-purpose cluster** (not recommended for production — blocks the
  all-purpose cluster and ties job success to cluster availability).
- **Serverless compute** (simplest; no cluster configuration required).

```yaml
# Job-level cluster definitions (referenced by tasks via job_cluster_key)
job_clusters:
  - job_cluster_key: etl_cluster
    new_cluster:
      spark_version: "15.4.x-scala2.12"
      node_type_id: m5.4xlarge
      num_workers: 8
      aws_attributes:
        first_on_demand: 1
        availability: SPOT_WITH_FALLBACK
      spark_conf:
        "spark.sql.adaptive.enabled": "true"
        "spark.databricks.delta.optimizeWrite.enabled": "true"

  - job_cluster_key: ml_cluster
    new_cluster:
      spark_version: "15.4.x-gpu-ml-scala2.12"
      node_type_id: g4dn.xlarge
      num_workers: 4
      aws_attributes:
        availability: ON_DEMAND    # GPU spot is unreliable
```

---

## 6. Job Parameters and Dynamic Values {#parameters}

Job-level parameters are key-value pairs set at job definition time and overridable at
run-time (e.g., via `databricks jobs run-now --job-parameters`). Use `{{parameter_name}}`
syntax in task configurations to reference them.

```yaml
parameters:
  - name: target_date
    default: "{{current_date}}"         # Databricks dynamic value: today's date (ISO 8601)
  - name: catalog
    default: "prod_sales"
  - name: env
    default: "prod"
```

**Built-in dynamic values**:

| Token | Value |
|---|---|
| `{{current_date}}` | Run date in `YYYY-MM-DD` format |
| `{{current_time}}` | Run time in `HH:mm:ss` format |
| `{{job_id}}` | Numeric job ID |
| `{{run_id}}` | Numeric run ID |
| `{{task_key}}` | Current task key (within task context) |

---

## 7. Retry Policies and Timeouts {#retry}

```yaml
tasks:
  - task_key: ingest_bronze
    max_retries: 3
    min_retry_interval_millis: 60000    # 1 minute between retries
    retry_on_timeout: false
    timeout_seconds: 3600               # fail the task if it runs longer than 1 hour
```

**Retry guidance**:
- Set `max_retries: 2-3` on ETL tasks to handle transient cloud failures (S3 throttle,
  Spark executor loss).
- Set `retry_on_timeout: false` unless the task is purely idempotent — retrying a
  timed-out non-idempotent task can produce duplicate records.
- Set `timeout_seconds` on all production tasks — an unbounded task can hold a job
  cluster open indefinitely, generating cost and blocking downstream runs.
- Do not set retries on ML training tasks — a timed-out training run should be
  investigated, not silently rerun.

---

## 8. Repair Runs {#repair}

A repair run resumes a failed job run from the first failed task, without re-running
tasks that already succeeded. This is the correct recovery mechanism for long multi-task
pipelines where re-running the entire job is expensive.

```bash
# Identify the failed run
databricks runs get --run-id 12345

# Repair the run — re-run only failed tasks
databricks runs repair \
  --run-id 12345 \
  --rerun-tasks ingest_bronze transform_silver    # optional: specify which tasks to rerun
  # omit --rerun-tasks to automatically re-run all failed and downstream tasks
```

**Repair run constraints**:
- Repaired tasks run on a new job cluster (the original cluster was terminated).
- Task values set by successfully completed tasks in the original run are preserved
  and available to repaired tasks.
- If a task that succeeded earlier would produce different output if re-run (e.g., due
  to source data changes), a full re-run is safer than a repair run.

---

## 9. Scheduling {#scheduling}

```yaml
# Cron schedule (Quartz cron format — 6 fields: sec min hour dom month dow)
schedule:
  quartz_cron_expression: "0 0 6 * * ?"       # daily at 06:00 UTC
  timezone_id: "UTC"
  pause_status: UNPAUSED                       # PAUSED to temporarily disable

# Common cron patterns
# "0 0 * * * ?"        — every hour
# "0 0 6 * * ?"        — daily at 06:00
# "0 0 6 ? * MON-FRI"  — weekdays at 06:00
# "0 0 6 1 * ?"        — first of each month at 06:00
```

**Continuous trigger (on new data arrival)**: use Databricks Workflows File Arrival
trigger to start a job when a new file lands in a cloud storage path. This eliminates
polling and provides near-real-time pipeline triggering without maintaining a continuous
streaming cluster.

```yaml
trigger:
  file_arrival:
    url: "s3://company-raw-data/orders/"
    min_time_between_triggers_seconds: 300    # minimum 5 minutes between triggers
    wait_after_last_change_seconds: 30        # wait 30s after last file change before triggering
```

---

## 10. Notifications {#notifications}

```yaml
# Email notifications on job events
email_notifications:
  on_start: []
  on_success: ["de-team@company.com"]
  on_failure: ["de-team@company.com", "oncall@company.com"]
  on_duration_warning_threshold_exceeded: ["de-team@company.com"]
  no_alert_for_skipped_runs: true

# Duration threshold warning (alert if run exceeds N seconds)
health:
  rules:
    - metric: RUN_DURATION_SECONDS
      op: GREATER_THAN
      value: 7200    # alert if run exceeds 2 hours

# Webhook notification (Slack, PagerDuty, custom)
webhook_notifications:
  on_failure:
    - id: "slack-webhook-id"    # registered via Notification Destinations in workspace settings
```

---

## 11. Orchestration vs DLT: When to Use Each {#vs-dlt}

| Criteria | Use DLT | Use Databricks Workflows |
|---|---|---|
| Data quality enforcement on every run | Yes | No (custom code required) |
| Medallion ETL with CDC and SCD | Yes | Possible but verbose |
| Mixed task types (ETL + ML + SQL + dbt) | No | Yes |
| Cross-system orchestration needs | No | Possible via HTTP tasks (limited) |
| Fine-grained task dependency control | Limited (within DLT DAG) | Full DAG control |
| Conditional task execution | Not supported | Supported via run-if conditions |
| Embedding a DLT pipeline in a larger job | Yes — use a DLT pipeline task | — |

**Pattern**: use DLT for the ETL Medallion layers, then wrap the DLT pipeline in a
Workflows Job that adds pre/post steps (data quality reporting, ML training trigger,
Slack notification, dbt run).

---

## 12. Full Job Bundle YAML Template {#template}

```yaml
# bundle.yml (partial — jobs section only)
# See references/cicd-dabs.md for the full bundle structure

resources:
  jobs:
    orders_lakehouse_pipeline:
      name: "[${bundle.target}] Orders Lakehouse Pipeline"
      description: "Full orders pipeline: ingest → DLT → validate → notify"

      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: "UTC"
        pause_status: ${var.schedule_pause_status}   # UNPAUSED for prod, PAUSED for dev

      email_notifications:
        on_failure: ["de-team@company.com"]
        no_alert_for_skipped_runs: true

      job_clusters:
        - job_cluster_key: etl_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: m5.4xlarge
            num_workers: 8
            aws_attributes:
              first_on_demand: 1
              availability: SPOT_WITH_FALLBACK

      tasks:
        - task_key: ingest_bronze
          python_wheel_task:
            package_name: orders_etl
            entry_point: ingest
            parameters:
              - "--catalog"
              - "${var.catalog}"
              - "--date"
              - "{{current_date}}"
          job_cluster_key: etl_cluster
          max_retries: 2
          timeout_seconds: 3600

        - task_key: run_dlt_pipeline
          depends_on:
            - task_key: ingest_bronze
          pipeline_task:
            pipeline_id: ${resources.pipelines.orders_medallion.id}

        - task_key: validate_gold
          depends_on:
            - task_key: run_dlt_pipeline
          python_wheel_task:
            package_name: orders_etl
            entry_point: validate
            parameters: ["--table", "${var.catalog}.gold_revenue.daily_revenue"]
          job_cluster_key: etl_cluster
          max_retries: 1
          timeout_seconds: 1800
```
