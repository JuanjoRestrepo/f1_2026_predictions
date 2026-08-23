# MLflow and Feature Store

> **Sources**: MLflow 3 Documentation (Databricks).
> https://docs.databricks.com/aws/en/mlflow3/genai/
> Mosaic AI Model Serving. https://docs.databricks.com/en/machine-learning/model-serving/index.html
> Databricks Feature Store. https://docs.databricks.com/en/machine-learning/feature-store/index.html
> MLflow 3.0 Announcement. https://databricks.com/blog/mlflow-30-unified-ai-experimentation-observability-and-governance

## Table of Contents

1. [MLflow 3 Overview](#mlflow3)
2. [Experiment Tracking](#tracking)
3. [Model Registry (Unity Catalog)](#registry)
4. [Mosaic AI Model Serving](#serving)
5. [Feature Store — Simplified (UC Tables with PK)](#feature-store)
6. [Agent Evaluation and Quality Loop](#agent-quality)
7. [MLflow Tracing — OTEL-Native](#tracing)
8. [Production Monitoring](#monitoring)
9. [Full ML Pipeline Template](#template)

---

## 1. MLflow 3 Overview {#mlflow3}

MLflow 3 is the current version of MLflow, redesigned from the ground up for Generative AI
workloads while retaining full backward compatibility with classical ML tracking. Key
architectural changes in MLflow 3 vs MLflow 2:

| Capability | MLflow 2 | MLflow 3 |
|---|---|---|
| Primary focus | Classical ML experiment tracking | GenAI + classical ML unified lifecycle |
| Agent tracing | Manual, limited | Auto-tracing via OTEL (one line of code) |
| Evaluation | `mlflow.evaluate()` | Unified: LLM judges, human feedback, code-based scorers |
| Model registry | Workspace-scoped | Unity Catalog (catalog.schema.model_name) |
| Stage transitions | Staging → Production → Archived | Deprecated. Use aliases: `@champion`, `@challenger` |
| Cross-platform monitoring | Databricks only | Any deployment (AWS Bedrock, Azure OpenAI, OSS) |
| SDK | `mlflow` | `mlflow[databricks]>=3.1` for Databricks-specific features |

**Install**:

```bash
# uv (project-level)
uv add "mlflow[databricks]>=3.1"
```

---

## 2. Experiment Tracking {#tracking}

```python
from __future__ import annotations

import logging
import mlflow
import mlflow.sklearn
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier

logger = logging.getLogger(__name__)

# Set experiment — Unity Catalog path or /Shared/<team>/<project>
mlflow.set_experiment("/Shared/churn-model/baseline-comparison")


def train_and_log(
    X_train, y_train, X_val, y_val, params: dict, model_name: str
) -> float:
    """
    Train a model, log all artifacts to MLflow, and return validation AUC.

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_val: Validation features.
        y_val: Validation labels.
        params: Hyperparameter dictionary.
        model_name: Identifier string for the run name.

    Returns:
        Validation ROC-AUC score.
    """
    with mlflow.start_run(run_name=model_name):
        # Log hyperparameters
        mlflow.log_params(params)
        mlflow.log_param("model_type", model_name)
        mlflow.log_param("train_rows", len(X_train))

        # Per GBM benchmark requirement: always train all three before neural networks
        if model_name == "xgboost":
            model = xgb.XGBClassifier(**params, eval_metric="auc", use_label_encoder=False)
        elif model_name == "lightgbm":
            model = lgb.LGBMClassifier(**params)
        elif model_name == "catboost":
            model = CatBoostClassifier(**params, verbose=0)
        else:
            raise ValueError(f"Unsupported model_name: {model_name}")

        model.fit(X_train, y_train)
        preds = model.predict(X_val)
        proba = model.predict_proba(X_val)[:, 1]

        val_auc   = roc_auc_score(y_val, proba)
        val_acc   = accuracy_score(y_val, preds)

        # Log metrics
        mlflow.log_metric("val_roc_auc", val_auc)
        mlflow.log_metric("val_accuracy", val_acc)

        # Log model — registered to Unity Catalog on log
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name="prod_sales.ml.churn_classifier",  # UC three-level name
        )

        logger.info("%s — val AUC: %.4f", model_name, val_auc)
        return val_auc
```

### Autolog

`mlflow.autolog()` automatically logs parameters, metrics, and models for supported
frameworks (sklearn, XGBoost, LightGBM, CatBoost, TensorFlow, PyTorch, Spark MLlib).

```python
mlflow.autolog(
    log_input_examples=True,   # log a sample of training data
    log_model_signatures=True, # infer input/output schema
    silent=True,               # suppress verbose logging
)

# All subsequent sklearn/XGBoost/etc. training calls auto-log
model = xgb.XGBClassifier(n_estimators=100, max_depth=6)
model.fit(X_train, y_train)   # automatically logged
```

---

## 3. Model Registry (Unity Catalog) {#registry}

In MLflow 3 on Databricks, models are registered in Unity Catalog using the three-level
namespace: `catalog.schema.model_name`. The deprecated workspace-scoped registry and
Stage transitions (Staging → Production → Archived) have been replaced by **aliases**.

### Aliases (replace Stage transitions)

| Alias | Replaces | Meaning |
|---|---|---|
| `@champion` | Production | Current production-serving version |
| `@challenger` | Staging | Candidate version being evaluated for promotion |
| (none) | Archived | Old versions without an alias — retained for rollback |

```python
import mlflow
from mlflow import MlflowClient

MODEL_URI = "prod_sales.ml.churn_classifier"
client = MlflowClient()

# Assign @challenger alias to a specific version
client.set_registered_model_alias(
    name=MODEL_URI,
    alias="challenger",
    version="5",
)

# Promote challenger to champion after A/B evaluation
client.set_registered_model_alias(
    name=MODEL_URI,
    alias="champion",
    version="5",
)

# Load model by alias
model = mlflow.sklearn.load_model(f"models:/{MODEL_URI}@champion")

# Load model by version number (for rollback)
model_v4 = mlflow.sklearn.load_model(f"models:/{MODEL_URI}/4")
```

### Model Lineage

MLflow + Unity Catalog automatically records model lineage: which training dataset,
experiment run, and notebook produced each model version. Queryable in the Catalog
Explorer or via the Unity Catalog lineage API (see `references/unity-catalog.md` §9).

---

## 4. Mosaic AI Model Serving {#serving}

Mosaic AI Model Serving deploys MLflow models as real-time REST API endpoints with
autoscaling, A/B traffic splitting, and GPU/CPU compute selection.

```python
import mlflow.deployments

# Deploy @champion version as a real-time serving endpoint
deploy_client = mlflow.deployments.get_deploy_client("databricks")

deploy_client.create_endpoint(
    name="churn-classifier-prod",
    config={
        "served_models": [
            {
                "name": "churn-v5",
                "model_name": "prod_sales.ml.churn_classifier",
                "model_version": "5",
                "workload_size": "Small",        # Small | Medium | Large
                "scale_to_zero_enabled": True,   # scale to 0 when idle (saves cost)
                "environment_vars": {
                    "DATABRICKS_TOKEN": "{{secrets/de-secrets/databricks-token}}",
                },
            }
        ],
        "auto_capture_config": {                 # log inference inputs/outputs to Delta
            "catalog_name": "prod_sales",
            "schema_name": "ml",
            "table_name_prefix": "churn_classifier_inference",
            "enabled": True,
        },
    },
)
```

### Querying a Serving Endpoint

```python
import mlflow.deployments

client = mlflow.deployments.get_deploy_client("databricks")

response = client.predict(
    endpoint="churn-classifier-prod",
    inputs={"dataframe_records": [
        {"age": 35, "tenure_months": 24, "monthly_charges": 79.50},
    ]},
)
print(response["predictions"])
```

### A/B Traffic Splitting

```python
# Split traffic: 80% champion, 20% challenger
deploy_client.update_endpoint(
    endpoint="churn-classifier-prod",
    config={
        "served_models": [
            {
                "name": "churn-v5",
                "model_name": "prod_sales.ml.churn_classifier",
                "model_version": "5",
                "traffic_percentage": 80,
                "workload_size": "Small",
            },
            {
                "name": "churn-v6-challenger",
                "model_name": "prod_sales.ml.churn_classifier",
                "model_version": "6",
                "traffic_percentage": 20,
                "workload_size": "Small",
            },
        ]
    },
)
```

---

## 5. Feature Store — Simplified (UC Tables with PK) {#feature-store}

**As of Databricks Runtime 14.x / Unity Catalog**: any Delta table registered in Unity
Catalog with a **primary key constraint** is automatically a Feature Store table — no
separate Feature Store API registration step is required. The traditional `FeatureStoreClient`
API for creating feature tables is still supported but no longer the primary approach.

### Creating Feature Tables (UC-native approach)

```sql
-- Any Delta table with a PRIMARY KEY is a Feature Store table in Unity Catalog
CREATE TABLE prod_sales.features.customer_features (
  customer_id  STRING  NOT NULL,         -- primary key = feature store key
  age          INT,
  tenure_months INT,
  total_spend  DOUBLE,
  churn_risk   DOUBLE,
  feature_timestamp TIMESTAMP,
  PRIMARY KEY (customer_id)
)
USING DELTA
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',   -- required for online store sync
  'delta.feature.allowColumnDefaults' = 'supported'
);
```

```python
from pyspark.sql import SparkSession, functions as F

spark = SparkSession.getActiveSession()

# Write features to the feature table (standard Delta write)
feature_df = (
    spark.table("prod_sales.silver.silver_customers")
    .groupBy("customer_id")
    .agg(
        F.avg("monthly_charges").alias("avg_monthly_charges"),
        F.sum("total_spend").alias("total_spend"),
        F.count("order_id").alias("order_count"),
        F.current_timestamp().alias("feature_timestamp"),
    )
)

(
    feature_df.write
    .format("delta")
    .mode("merge")     # or overwrite for full refresh
    .option("mergeSchema", "false")
    .saveAsTable("prod_sales.features.customer_features")
)
```

### Training with Point-in-Time Lookup

```python
from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()

# Training set: join labels with features at a point in time
training_set = fe.create_training_set(
    df=labels_df,                         # DataFrame with label + keys + timestamp
    feature_lookups=[
        FeatureLookup(
            table_name="prod_sales.features.customer_features",
            feature_names=["avg_monthly_charges", "total_spend", "order_count"],
            lookup_key="customer_id",
            timestamp_lookup_key="label_date",    # point-in-time: use feature as of label_date
        )
    ],
    label="churned",
    exclude_columns=["label_date"],
)

training_df = training_set.load_df()

# Log the training set — creates lineage from model → features
model = xgb.XGBClassifier(n_estimators=100)
model.fit(training_df.drop("churned", axis=1), training_df["churned"])

fe.log_model(
    model=model,
    artifact_path="churn_model_with_features",
    flavor=mlflow.sklearn,
    training_set=training_set,
    registered_model_name="prod_sales.ml.churn_classifier",
)
```

### Batch Inference with Automatic Feature Retrieval

```python
# Batch inference: provide only primary keys — feature values retrieved automatically
predictions = fe.score_batch(
    model_uri="models:/prod_sales.ml.churn_classifier@champion",
    df=customer_ids_df,    # DataFrame with customer_id only
)
# Feature values are automatically retrieved from the feature table at inference time
```

---

## 6. Agent Evaluation and Quality Loop {#agent-quality}

MLflow 3 implements the **Capture → Judge → Align → Optimize** quality loop for AI agents
(introduced at Data + AI Summit 2026). This transforms production agent traces into a
continuous improvement pipeline.

```
Capture → Judge → Align → Optimize
   |          |        |         |
   |       LLM judge  MemAlign  GEPA
   |       scorers    (domain   (prompt
 MLflow    & metrics  calibration)  optimization)
 Traces
 (OTEL)
```

| Stage | Tool | Description |
|---|---|---|
| **Capture** | MLflow Tracing (OTEL-native) | Every agent interaction logged as a trace (spans, tool calls, responses, latency). Traces are stored in Unity Catalog Delta tables — immediately queryable as eval datasets. |
| **Judge** | LLM Judges / MLflow scorers | Automated evaluation of trace quality: correctness, faithfulness, toxicity, latency. Built-in and custom judges via `mlflow.evaluate()`. |
| **Align** | **MemAlign** | Calibrates judges to the specific business domain. Requires ~20 SME-labeled examples to align the judge's scoring to domain-specific correctness criteria. Prevents judge drift over time. |
| **Optimize** | **GEPA** (Guided Evaluation with Prompt Adaptation) | Uses aligned judge scores to automatically generate improved prompts for the agent. Closes the loop without manual prompt engineering. |

```python
import mlflow
from mlflow.evaluation import make_metric

mlflow.set_experiment("/Shared/churn-agent/quality-loop")

# --- Stage: Capture ---
# Production traces are automatically logged (see §7 for tracing setup)
# Query traces as a Delta table:
traces_df = spark.table("prod_sales.ml.churn_agent_traces")

# --- Stage: Judge ---
with mlflow.start_run(run_name="quality_evaluation"):
    results = mlflow.evaluate(
        data=traces_df.toPandas(),
        model_type="databricks-agent",
        evaluator_config={
            "databricks-agent": {
                "metrics": [
                    "response/correctness",
                    "response/groundedness",
                    "retrieval/precision",
                    "agent/token_count",
                ]
            }
        },
    )
    mlflow.log_metrics(results.metrics)
```

---

## 7. MLflow Tracing — OTEL-Native {#tracing}

MLflow 3 auto-tracing instruments popular agent frameworks with a single line of code.
Traces follow the OpenTelemetry (OTEL) standard — zero re-instrumentation required when
switching between MLflow and OTEL-native infrastructure.

```python
import mlflow

# Auto-tracing: one line enables full span capture for supported frameworks
# Supported: LangGraph, OpenAI, Anthropic, CrewAI, LlamaIndex, AutoGen, DSPy, Groq
mlflow.langchain.autolog()      # LangChain / LangGraph
mlflow.openai.autolog()         # OpenAI SDK
mlflow.anthropic.autolog()      # Anthropic SDK

# Manual span instrumentation for custom logic
with mlflow.start_span(name="retrieve_customer_context") as span:
    span.set_inputs({"customer_id": customer_id})
    context = retrieve_from_vector_store(customer_id)
    span.set_outputs({"chunk_count": len(context)})
    span.set_attribute("retrieval.latency_ms", 42)
```

### OTEL to Unity Catalog (Production Traces)

```python
import mlflow

# Configure MLflow to write OTEL traces directly to a Unity Catalog Delta table
mlflow.set_tracking_uri("databricks")

# Enable production monitoring — stores traces in UC for long-term retention
mlflow.enable_system_metrics_logging()

# Set the UC table where traces are persisted (governed, queryable via SQL/Genie)
mlflow.set_experiment(
    experiment_id="<experiment_id>",
    # Optional: configure long-term trace storage in UC
)

# With production monitoring enabled:
# - Traces flow to MLflow experiment AND to Delta table at prod_sales.ml.churn_agent_traces
# - Apply row filters and column masks for PII protection in the UC table
# - Query traces with SQL: SELECT * FROM prod_sales.ml.churn_agent_traces WHERE latency_ms > 2000
```

---

## 8. Production Monitoring {#monitoring}

```python
from databricks.sdk import WorkspaceClient
import mlflow

# Configure production monitoring for a deployed endpoint
client = WorkspaceClient()

# Production monitoring: run the same judges on live traffic
# (traces stored in UC → judge runs on schedule → results in experiment)
monitor_config = {
    "endpoint_name": "churn-classifier-prod",
    "monitor_table": "prod_sales.ml.churn_agent_traces",
    "evaluation_metrics": [
        "response/correctness",
        "response/groundedness",
    ],
    "schedule": {"quartz_cron_expression": "0 0 6 * * ?"},  # daily at 06:00
}

# Production monitoring alerts if judge score drops below threshold
# integrated with Lakeflow Jobs for automated remediation
```

---

## 9. Full ML Pipeline Template {#template}

```python
"""
churn_ml_pipeline.py — End-to-end ML pipeline with MLflow 3.

Steps: feature engineering → GBM benchmark → register → serve.
Per user preferences: XGBoost/LightGBM/CatBoost benchmarked per Grinsztajn et al. (2022)
before any neural network consideration.
"""
from __future__ import annotations

import logging
import mlflow
import mlflow.sklearn
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from typing import Any

logger = logging.getLogger(__name__)

MODEL_REGISTRY_NAME: str = "prod_sales.ml.churn_classifier"
EXPERIMENT_PATH: str = "/Shared/churn-model/gbm-benchmark"
FEATURE_TABLE: str = "prod_sales.features.customer_features"

# Benchmark all three per Grinsztajn et al. (2022) before considering neural networks
GBM_CONFIGS: dict[str, tuple[type, dict[str, Any]]] = {
    "xgboost": (
        xgb.XGBClassifier,
        {"n_estimators": 500, "max_depth": 6, "learning_rate": 0.05,
         "subsample": 0.8, "colsample_bytree": 0.8, "eval_metric": "auc",
         "use_label_encoder": False},
    ),
    "lightgbm": (
        lgb.LGBMClassifier,
        {"n_estimators": 500, "max_depth": 6, "learning_rate": 0.05,
         "subsample": 0.8, "colsample_bytree": 0.8, "verbose": -1},
    ),
    "catboost": (
        CatBoostClassifier,
        {"iterations": 500, "depth": 6, "learning_rate": 0.05, "verbose": 0},
    ),
}


def run_gbm_benchmark(X_train, y_train, X_val, y_val) -> str:
    """
    Benchmark XGBoost, LightGBM, and CatBoost. Register the best model.

    Args:
        X_train: Training feature matrix.
        y_train: Training labels.
        X_val: Validation feature matrix.
        y_val: Validation labels.

    Returns:
        Name of the best-performing model type.
    """
    mlflow.set_experiment(EXPERIMENT_PATH)
    best_model_name: str = ""
    best_auc: float = 0.0

    for model_name, (ModelClass, params) in GBM_CONFIGS.items():
        with mlflow.start_run(run_name=f"{model_name}_baseline"):
            mlflow.log_params(params)
            mlflow.log_param("model_type", model_name)

            model = ModelClass(**params)
            model.fit(X_train, y_train)

            proba = model.predict_proba(X_val)[:, 1]
            val_auc = roc_auc_score(y_val, proba)
            mlflow.log_metric("val_roc_auc", val_auc)

            mlflow.sklearn.log_model(
                model,
                artifact_path="model",
                registered_model_name=MODEL_REGISTRY_NAME,
            )

            logger.info("[%s] val AUC: %.4f", model_name, val_auc)

            if val_auc > best_auc:
                best_auc = val_auc
                best_model_name = model_name

    logger.info("Best model: %s (AUC: %.4f)", best_model_name, best_auc)
    return best_model_name
```
