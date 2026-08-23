# CI/CD with Databricks Asset Bundles (DABs)

> **Sources**: Databricks Asset Bundles Documentation.
> https://docs.databricks.com/en/dev-tools/bundles/index.html
> DABs YAML Reference. https://docs.databricks.com/en/dev-tools/bundles/reference.html
> Databricks CLI. https://docs.databricks.com/en/dev-tools/cli/index.html

## Table of Contents

1. [What Are Databricks Asset Bundles](#overview)
2. [Bundle Project Structure](#structure)
3. [bundle.yml — Root Configuration](#root-config)
4. [Resource Definitions](#resources)
5. [Deployment Targets](#targets)
6. [Variables and Environment Overrides](#variables)
7. [Databricks Connect v2 for Local Testing](#databricks-connect)
8. [Testing Strategy](#testing)
9. [GitHub Actions CI/CD Pipeline](#github-actions)
10. [Deployment Workflow](#deployment)
11. [Complete Bundle Example](#full-example)

---

## 1. What Are Databricks Asset Bundles {#overview}

Databricks Asset Bundles (DABs) are the CI/CD standard for Databricks. A bundle is a
collection of YAML configuration files that declare all Databricks resources (jobs,
pipelines, models, schemas, SQL warehouses, dashboards) for a project, together with the
source code they reference. Bundles are validated, deployed, and run via the Databricks CLI.

**What DABs replace**:
- Manual "Deploy to Production" clicks in the Databricks UI
- Custom deployment scripts using the Databricks REST API
- Separate orchestration of notebook uploads, job creation, and pipeline configuration

**What DABs enable**:
- Infrastructure-as-code for all Databricks resources — reviewable in pull requests
- Multi-target deployments (dev/staging/prod) from a single bundle definition
- CI/CD pipeline integration (GitHub Actions, Azure DevOps, GitLab CI)
- Version-controlled resource configuration with environment variable substitution
- Databricks-side validation before deployment (`databricks bundle validate`)

---

## 2. Bundle Project Structure {#structure}

```
my-project/
├── bundle.yml                          # Root bundle configuration (required)
├── databricks.yml                      # Alias for bundle.yml (either name works)
├── src/
│   ├── pipelines/
│   │   ├── bronze_ingestion.py         # Lakeflow pipeline notebook/script
│   │   ├── silver_transform.py
│   │   └── gold_aggregation.py
│   ├── jobs/
│   │   └── validate_pipeline.py
│   └── ml/
│       └── train_churn_model.py
├── tests/
│   ├── unit/
│   │   ├── conftest.py
│   │   └── test_transformations.py     # pytest unit tests (no cluster required)
│   └── integration/
│       └── test_pipeline_end_to_end.py # pytest integration tests via Databricks Connect
├── dashboards/
│   └── revenue_dashboard.lvdash.json   # Lakeview dashboard definition
├── resources/
│   ├── jobs.yml                        # Job resource definitions (optional split)
│   ├── pipelines.yml                   # Pipeline resource definitions
│   └── clusters.yml                    # Cluster policy / pool definitions
├── pyproject.toml                      # Python project config (uv, ruff, mypy)
└── .github/
    └── workflows/
        └── databricks-cicd.yml         # GitHub Actions workflow
```

**Split vs single file**: for small projects, all resources can be declared in one
`bundle.yml`. For large projects, split resource definitions into files under `resources/`
and `include` them in `bundle.yml`.

---

## 3. bundle.yml — Root Configuration {#root-config}

```yaml
# bundle.yml — root bundle configuration

bundle:
  name: orders-lakehouse    # unique bundle name; appears in resource names via ${bundle.name}

# Include resource files defined in separate YAML files
include:
  - resources/*.yml

# Workspace-level settings per target
workspace:
  host: ${workspace.host}    # resolved per target (see §5)

# Variables (overridable per target)
variables:
  catalog:
    description: "Unity Catalog name for this deployment target"
    default: "dev_sales"
  sql_warehouse_id:
    description: "SQL Warehouse ID for Lakeview dashboards"
    default: ""
  schedule_pause_status:
    description: "PAUSED for non-prod, UNPAUSED for prod"
    default: "PAUSED"

# Deployment targets
targets:
  dev:
    mode: development        # adds [dev <username>] prefix to resource names
    default: true
    workspace:
      host: https://adb-<dev-workspace-id>.azuredatabricks.net
    variables:
      catalog: dev_sales
      schedule_pause_status: PAUSED

  staging:
    mode: development
    workspace:
      host: https://adb-<staging-workspace-id>.azuredatabricks.net
    variables:
      catalog: staging_sales
      schedule_pause_status: PAUSED

  prod:
    mode: production         # removes dev prefix; enforces production defaults
    workspace:
      host: https://adb-<prod-workspace-id>.azuredatabricks.net
    variables:
      catalog: prod_sales
      schedule_pause_status: UNPAUSED
    run_as:
      service_principal_name: orders-lakehouse-sp@company.com
```

---

## 4. Resource Definitions {#resources}

### Lakeflow Pipeline (Declarative Pipelines)

```yaml
# resources/pipelines.yml

resources:
  pipelines:
    orders_medallion:
      name: "[${bundle.target}] Orders Medallion Pipeline"
      catalog: ${var.catalog}
      target: orders                              # schema within the catalog
      development: ${bundle.target != 'prod'}    # development mode for non-prod
      configuration:
        pipelines.enableTrackHistory: "true"
        spark.databricks.delta.optimizeWrite.enabled: "true"
      clusters:
        - label: default
          num_workers: 4
          node_type_id: m5.4xlarge
          aws_attributes:
            availability: SPOT_WITH_FALLBACK
      libraries:
        - notebook:
            path: ./src/pipelines/bronze_ingestion.py
        - notebook:
            path: ./src/pipelines/silver_transform.py
        - notebook:
            path: ./src/pipelines/gold_aggregation.py
      notifications:
        - email_recipients: ["de-team@company.com"]
          alerts: ["on-update-failure"]
```

### Lakeflow Job

```yaml
# resources/jobs.yml

resources:
  jobs:
    orders_pipeline_job:
      name: "[${bundle.target}] Orders Pipeline Orchestration"
      description: "DLT pipeline → validation → ML trigger → notification"

      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: "UTC"
        pause_status: ${var.schedule_pause_status}

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
            custom_tags:
              project: orders-lakehouse
              env: ${bundle.target}

      tasks:
        - task_key: run_dlt_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.orders_medallion.id}

        - task_key: validate_silver
          depends_on:
            - task_key: run_dlt_pipeline
          notebook_task:
            notebook_path: ./src/jobs/validate_pipeline.py
            base_parameters:
              catalog: ${var.catalog}
              schema: orders
          job_cluster_key: etl_cluster
          max_retries: 2
          timeout_seconds: 1800
```

### MLflow Model

```yaml
# resources/models.yml

resources:
  registered_models:
    churn_classifier:
      name: "${var.catalog}.ml.churn_classifier"
      catalog_name: ${var.catalog}
      schema_name: ml
      comment: "Customer churn classification model — XGBoost/LightGBM/CatBoost benchmarked."
      grants:
        - privileges: ["EXECUTE"]
          principal: data_scientists
```

---

## 5. Deployment Targets {#targets}

| Target | `mode` | Resource name prefix | Typical use |
|---|---|---|---|
| `dev` | `development` | `[dev <username>]` | Individual developer iteration. Resources are user-scoped. |
| `staging` | `development` | `[staging]` (custom) | Integration testing. Shared, but isolated from prod data. |
| `prod` | `production` | None (clean names) | Production deployment. Runs as service principal. |

**`mode: development`**: automatically prefixes all resource names with `[dev <username>]`
(or a custom prefix), ensuring developer deployments do not conflict with each other or
with production. Pauses all schedules by default.

**`mode: production`**: enforces production defaults: no dev prefix, `run_as` service
principal, stricter validation. Fails if any resource references a personal access token
instead of a service principal.

---

## 6. Variables and Environment Overrides {#variables}

```yaml
# Variable lookup order (highest precedence first):
# 1. --var flag on CLI: databricks bundle deploy --var="catalog=override_sales"
# 2. Environment variable: BUNDLE_VAR_catalog=override_sales
# 3. Target-level override in bundle.yml
# 4. Variable default value in bundle.yml

# Complex variable with lookup
variables:
  sql_warehouse_id:
    description: "SQL Warehouse ID (from workspace)"
    lookup:
      warehouse: "Shared Serverless Warehouse"    # look up by name, not hard-code ID
```

---

## 7. Databricks Connect v2 for Local Testing {#databricks-connect}

Databricks Connect v2 (DBR 13.0+) allows running PySpark code from a local machine or
CI runner against a remote Databricks cluster — without uploading notebooks. This enables
fast unit test iteration without full cluster provisioning.

```python
# conftest.py — pytest fixtures for Databricks Connect v2
from __future__ import annotations

import os
import pytest
from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    """
    Returns a SparkSession connected to a Databricks cluster via Databricks Connect v2.

    For CI: set DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_CLUSTER_ID env vars.
    For local dev: uses ~/.databrickscfg DEFAULT profile.

    Returns:
        SparkSession connected to remote Databricks cluster.
    """
    if os.getenv("CI"):
        # CI: use environment variables
        session = (
            DatabricksSession.builder
            .host(os.environ["DATABRICKS_HOST"])
            .token(os.environ["DATABRICKS_TOKEN"])
            .clusterId(os.environ["DATABRICKS_CLUSTER_ID"])
            .getOrCreate()
        )
    else:
        # Local dev: uses default Databricks CLI profile
        session = DatabricksSession.builder.getOrCreate()

    yield session
    session.stop()
```

---

## 8. Testing Strategy {#testing}

| Test level | Framework | Cluster required | When to run |
|---|---|---|---|
| **Unit tests** | `pytest` + `chispa` (DataFrame equality) | No — local PySpark or mocked | Pre-commit, every PR |
| **Integration tests** | `pytest` + Databricks Connect v2 | Yes — shared dev cluster | On PR merge to `develop` |
| **Pipeline validation** | `databricks bundle validate` | No | Every CI run before deploy |
| **End-to-end test** | Lakeflow Job run in staging | Yes — staging environment | On PR merge to `main` |

```python
# tests/unit/test_transformations.py
from __future__ import annotations

import pytest
from chispa import assert_df_equality
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

from src.pipelines.silver_transform import apply_silver_transformations


ORDER_SCHEMA = StructType([
    StructField("order_id", StringType(), nullable=False),
    StructField("amount",   StringType(), nullable=True),    # raw string (pre-cast)
])

EXPECTED_SCHEMA = StructType([
    StructField("order_id", StringType(), nullable=False),
    StructField("amount",   DoubleType(), nullable=True),    # cast to double
])


def test_silver_type_coercion(spark: SparkSession) -> None:
    """
    Verify that apply_silver_transformations correctly casts amount to DOUBLE.
    """
    input_df = spark.createDataFrame(
        [("ORD-001", "99.99"), ("ORD-002", None), ("ORD-003", "invalid")],
        schema=ORDER_SCHEMA,
    )

    result_df = apply_silver_transformations(input_df)

    expected_df = spark.createDataFrame(
        [("ORD-001", 99.99), ("ORD-002", None), ("ORD-003", None)],
        schema=EXPECTED_SCHEMA,
    )

    assert_df_equality(result_df, expected_df, ignore_nullable=True)


def test_silver_deduplication(spark: SparkSession) -> None:
    """
    Verify that duplicate order_ids are removed, keeping one record per order_id.
    """
    input_df = spark.createDataFrame(
        [("ORD-001", "50.00"), ("ORD-001", "50.00"), ("ORD-002", "30.00")],
        schema=ORDER_SCHEMA,
    )
    result_df = apply_silver_transformations(input_df)
    assert result_df.count() == 2
```

---

## 9. GitHub Actions CI/CD Pipeline {#github-actions}

```yaml
# .github/workflows/databricks-cicd.yml
name: Databricks CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  DATABRICKS_HOST: ${{ secrets.DATABRICKS_STAGING_HOST }}
  DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_STAGING_TOKEN }}
  DATABRICKS_CLUSTER_ID: ${{ secrets.DATABRICKS_STAGING_CLUSTER_ID }}

jobs:
  lint-and-test:
    name: Code Quality + Unit Tests
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: latest

      - name: Set up Python 3.12
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Ruff lint
        run: uv run ruff check .

      - name: Ruff format check
        run: uv run ruff format --check .

      - name: mypy type check
        run: uv run mypy src/ --strict

      - name: Unit tests (no cluster)
        run: uv run pytest tests/unit/ -v --tb=short --cov=src --cov-report=term-missing

  validate-bundle:
    name: Validate DABs Bundle
    runs-on: ubuntu-latest
    needs: lint-and-test

    steps:
      - uses: actions/checkout@v4

      - name: Install Databricks CLI
        uses: databricks/setup-cli@main

      - name: Validate bundle (staging target)
        run: databricks bundle validate --target staging
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_STAGING_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_STAGING_TOKEN }}

  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: validate-bundle
    if: github.ref == 'refs/heads/develop'

    steps:
      - uses: actions/checkout@v4

      - name: Install Databricks CLI
        uses: databricks/setup-cli@main

      - name: Deploy bundle to staging
        run: databricks bundle deploy --target staging
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_STAGING_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_STAGING_TOKEN }}

      - name: Run integration pipeline in staging
        run: databricks bundle run --target staging orders_pipeline_job
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_STAGING_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_STAGING_TOKEN }}

  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: deploy-staging
    if: github.ref == 'refs/heads/main'
    environment: production            # requires manual approval in GitHub Environments

    steps:
      - uses: actions/checkout@v4

      - name: Install Databricks CLI
        uses: databricks/setup-cli@main

      - name: Deploy bundle to production
        run: databricks bundle deploy --target prod
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_PROD_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_PROD_SP_TOKEN }}    # service principal
```

---

## 10. Deployment Workflow {#deployment}

```bash
# --- Local development ---

# 1. Authenticate (one-time setup)
databricks configure --host https://<workspace>.azuredatabricks.net

# 2. Validate bundle before any deployment
databricks bundle validate --target dev

# 3. Deploy to dev (creates/updates all resources in dev target)
databricks bundle deploy --target dev

# 4. Run a specific job in dev to test
databricks bundle run --target dev orders_pipeline_job

# 5. Run a specific pipeline update
databricks bundle run --target dev orders_medallion

# --- Override a variable at deploy time ---
databricks bundle deploy --target staging --var="catalog=staging_sales_v2"

# --- Destroy dev resources when done (prevents cost accumulation)
databricks bundle destroy --target dev

# --- Production deployment (normally via CI/CD, not manual)
databricks bundle deploy --target prod

# --- Check deployment status
databricks bundle summary --target prod
```

---

## 11. Complete Bundle Example {#full-example}

```yaml
# bundle.yml — minimal complete example for an orders data pipeline

bundle:
  name: orders-lakehouse

include:
  - resources/*.yml

variables:
  catalog:
    default: dev_sales
  schedule_pause_status:
    default: PAUSED
  sql_warehouse_id:
    default: ""
    lookup:
      warehouse: "Shared Serverless Warehouse"

targets:
  dev:
    mode: development
    default: true
    workspace:
      host: https://adb-111111111111.1.azuredatabricks.net
    variables:
      catalog: dev_sales

  prod:
    mode: production
    workspace:
      host: https://adb-222222222222.2.azuredatabricks.net
    variables:
      catalog: prod_sales
      schedule_pause_status: UNPAUSED
    run_as:
      service_principal_name: orders-lakehouse-sp@company.onmicrosoft.com

resources:
  pipelines:
    orders_medallion:
      name: "[${bundle.target}] Orders Medallion"
      catalog: ${var.catalog}
      target: orders
      libraries:
        - notebook:
            path: ./src/pipelines/bronze_ingestion.py
        - notebook:
            path: ./src/pipelines/silver_transform.py
        - notebook:
            path: ./src/pipelines/gold_aggregation.py

  jobs:
    orders_job:
      name: "[${bundle.target}] Orders Orchestration"
      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: UTC
        pause_status: ${var.schedule_pause_status}
      email_notifications:
        on_failure: ["de-team@company.com"]
      tasks:
        - task_key: run_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.orders_medallion.id}
```
