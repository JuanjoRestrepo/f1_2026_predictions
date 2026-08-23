# Cluster and Compute Configuration

> **Sources**: Databricks Documentation — Compute.
> https://docs.databricks.com/en/compute/index.html
> Databricks Photon. https://docs.databricks.com/en/compute/photon.html
> Instance Pools. https://docs.databricks.com/en/compute/pool-index.html

## Table of Contents

1. [Cluster Type Selection](#types)
2. [Cluster Modes](#modes)
3. [Runtime Versions](#runtimes)
4. [Photon Acceleration](#photon)
5. [Instance Pools](#pools)
6. [Autoscaling](#autoscaling)
7. [Spot / Preemptible Instances](#spot)
8. [Cluster Policies](#policies)
9. [Init Scripts](#init-scripts)
10. [Serverless Compute](#serverless)
11. [Configuration Templates](#templates)

---

## 1. Cluster Type Selection {#types}

| Type | Purpose | Pricing model | Recommendation |
|---|---|---|---|
| **All-purpose cluster** | Interactive notebook development, ad-hoc exploration | DBUs billed per second while running | Development only. Never run production ETL on all-purpose clusters. |
| **Job cluster** | Single-job execution — created at job start, terminated at job end | DBUs billed only during job run | All production pipelines. ~3-4x cheaper than equivalent all-purpose. |
| **SQL Warehouse** | SQL analytics, BI dashboards, Databricks SQL queries | Serverless, Pro, or Classic DBU rates | SQL queries, Lakeview dashboards, BI connector endpoints. |
| **Serverless (Jobs/DLT)** | Managed compute — no cluster config required | Serverless DBU rate (premium over job cluster) | Fastest startup; eliminates cluster management overhead. Appropriate for teams without a dedicated platform engineer. |

**Rule**: Production ETL pipelines use job clusters (cost efficiency) or serverless compute
(operational simplicity). All-purpose clusters in production are a cost and stability risk.

---

## 2. Cluster Modes {#modes}

| Mode | Description | When to use |
|---|---|---|
| **Single Node** | Driver only, no worker nodes. Spark runs in local mode. | Small datasets (<10GB), ML training on single-node frameworks (sklearn, XGBoost), notebook dev without Spark. |
| **Standard (Fixed-size)** | Driver + N worker nodes, fixed count. | Predictable workloads with known resource requirements. |
| **Standard (Autoscaling)** | Driver + workers scale between min and max. | Workloads with variable data volume or concurrent query load. |
| **High Concurrency** | Optimized for multiple users sharing a single cluster. Supports table access control and credential passthrough (Hive Metastore only). | Shared interactive analytics environments. Avoid with Unity Catalog — use separate job clusters per user instead. |

**Note on High Concurrency + Unity Catalog**: High Concurrency mode with table ACLs is a
Hive Metastore feature. Under Unity Catalog, fine-grained access is enforced at the catalog
level — any Standard cluster can safely share Unity Catalog tables with per-user governance.

---

## 3. Runtime Versions {#runtimes}

| Runtime | Description | When to use |
|---|---|---|
| **Standard LTS** | Long-term support (two-year support window). E.g., DBR 15.4 LTS. | All production pipelines. Pin to an LTS version for stability. |
| **ML Runtime LTS** | Standard LTS + pre-installed ML libraries (MLflow, PyTorch, TensorFlow, scikit-learn, XGBoost, LightGBM, CatBoost, Hugging Face). | ML training and serving clusters. Eliminates installing common ML libraries via init scripts. |
| **Photon Runtime** | Standard LTS + Photon vectorized engine (see §4). Applies automatically when Photon is enabled. | CPU-bound SQL and ETL workloads. |
| **GPU Runtime** | Standard LTS + CUDA/cuDNN + GPU-optimized ML libraries. | Deep learning training (PyTorch, TF). Requires GPU instance types. |

**Policy**: always pin production clusters to an LTS version. Non-LTS runtimes are deprecated
faster and introduce instability. Upgrade runtime in staging first, then promote.

---

## 4. Photon Acceleration {#photon}

Photon is Databricks's native vectorized query execution engine, written in C++. It
executes operations on columnar data using SIMD instruction sets, bypassing JVM overhead.

**What Photon accelerates**: SQL queries (SELECT, JOIN, aggregate), Delta table scans,
OPTIMIZE, COPY INTO. Most SQL and ETL operations benefit substantially (2-6x speedup
depending on operation mix and data volume).

**What Photon does not accelerate**: Python/Pandas UDFs (still executed in JVM or Python
worker processes), arbitrary PySpark RDD operations, ML training operations.

**Enabling Photon**:

```python
# Cluster configuration — enable via UI or cluster API
# Databricks Runtime must be a Photon-enabled version (appended with " (Photon)")

# Verify Photon is active in a notebook
spark.conf.get("spark.databricks.photon.enabled")   # "true" if Photon is running

# Photon on SQL Warehouse is always on for Pro and Serverless tiers
```

**Cost**: Photon clusters carry a Photon DBU rate (~1.5-2x Standard DBU rate). The economics
are favorable when query runtimes are reduced by more than the DBU premium — evaluate on a
representative workload before committing.

---

## 5. Instance Pools {#pools}

Instance pools maintain a set of idle, ready-to-use VM instances. Clusters attached to a
pool skip the VM provisioning step (typically 2-5 minutes) and start in ~30 seconds.

**When to use**: high-frequency short-duration jobs (streaming micro-batch triggers,
ML inference pipelines, ETL jobs running every 5-15 minutes) where cold-start latency
represents a significant fraction of total runtime.

**When not to use**: long-running jobs (≥ 30 minutes) where cold-start amortizes;
clusters requiring GPU instances (pool GPU inventory costs are high when idle).

```json
// Pool configuration (Databricks REST API / DABs resource)
{
  "instance_pool_name": "de_job_pool_m5xlarge",
  "min_idle_instances": 2,
  "max_capacity": 50,
  "idle_instance_autotermination_minutes": 30,
  "node_type_id": "m5.xlarge",
  "preloaded_spark_versions": ["15.4.x-scala2.12"],
  "aws_attributes": {
    "availability": "SPOT_WITH_FALLBACK",
    "spot_bid_price_percent": 100
  }
}
```

```yaml
# DABs resource definition (bundle.yml)
resources:
  instance_pools:
    de_job_pool:
      instance_pool_name: "[${bundle.target}] DE Job Pool"
      min_idle_instances: 2
      max_capacity: 50
      idle_instance_autotermination_minutes: 30
      node_type_id: m5.xlarge
      preloaded_spark_versions:
        - 15.4.x-scala2.12
```

---

## 6. Autoscaling {#autoscaling}

| Mode | Behavior | Best for |
|---|---|---|
| **Standard autoscaling** | Scales based on Spark task backlog. Scales down after idle period. | ETL batch jobs with variable data volume. |
| **Enhanced autoscaling** | Databricks-managed; scales based on query queue depth in addition to task backlog. Better for SQL Warehouses and mixed workloads. | SQL Warehouses, shared interactive clusters. |
| **Fixed size** | No scaling. Predictable cost. | ML training (Spark MLlib, Horovod) — autoscaling causes training instability. Streaming jobs — node removal interrupts micro-batches. |

**Autoscaling anti-patterns**:
- Autoscaling on Structured Streaming jobs causes task failures when executors are removed
  mid-micro-batch. Use fixed-size clusters for streaming.
- Autoscaling on Spark MLlib distributed training is disruptive. Fix worker count to match
  the training parallelism strategy.
- Setting `min_workers = 0` causes full cluster termination between tasks in a multi-task
  job, losing the warm executor benefit. Set `min_workers >= 1` for multi-task pipelines.

---

## 7. Spot / Preemptible Instances {#spot}

| Cloud | Term | Savings |
|---|---|---|
| AWS | Spot Instances | 60-90% vs on-demand |
| Azure | Spot VMs | 60-90% vs pay-as-you-go |
| GCP | Preemptible VMs | 60-91% vs on-demand |

**Best practice**: `SPOT_WITH_FALLBACK` (AWS) / `SPOT_WITH_FALLBACK_AZURE` — use spot
instances if available; fall back to on-demand if spot capacity is unavailable. Never use
spot-only for production pipelines without a fallback strategy.

**Spot for driver nodes**: do not run the Spark driver on a spot instance in production.
Driver termination kills the entire job with no recovery. Use on-demand for the driver,
spot for workers.

```json
// AWS cluster config: on-demand driver, spot workers with fallback
{
  "aws_attributes": {
    "first_on_demand": 1,
    "availability": "SPOT_WITH_FALLBACK",
    "spot_bid_price_percent": 100
  }
}
```

---

## 8. Cluster Policies {#policies}

Cluster policies enforce organizational standards on cluster configuration. They restrict or
fix values (instance types, autoscaling bounds, runtime versions, init scripts) and prevent
users from provisioning non-compliant clusters.

**Typical policy strategy**:

| Policy | Fixed values | Allowed ranges |
|---|---|---|
| `de_job_cluster` | `spot_with_fallback`, approved instance family (m5/r5), LTS runtime | Worker count 1–100, autoscaling allowed |
| `ml_interactive` | ML Runtime LTS, no Photon | Instance: g4dn/p3 for GPU or m5.4xlarge for CPU; min 1 worker |
| `sql_analytics` | SQL Warehouse only (enforced separately) | — |

```json
// Policy definition (Databricks Policies API)
{
  "name": "de_job_cluster",
  "definition": {
    "spark_version": {
      "type": "regex",
      "pattern": "^(\\d+\\.\\d+\\.x-scala2\\.12)$",
      "defaultValue": "15.4.x-scala2.12"
    },
    "aws_attributes.availability": {
      "type": "fixed",
      "value": "SPOT_WITH_FALLBACK"
    },
    "autoscale.min_workers": {"type": "range", "minValue": 1, "maxValue": 4},
    "autoscale.max_workers": {"type": "range", "minValue": 4, "maxValue": 100}
  }
}
```

---

## 9. Init Scripts {#init-scripts}

Init scripts run on every cluster node at startup, before the Spark driver and executors
start. Use for: installing OS-level dependencies, configuring system environment variables,
installing Python packages not available on PyPI (custom wheels), configuring network
settings.

**Scope options**: cluster-scoped (applied to one cluster), global (applied to all clusters
in the workspace — requires admin privileges), policy-scoped (applied via cluster policy).

```bash
#!/bin/bash
# init_script.sh — cluster init script stored in Unity Catalog Volume or DBFS

set -euxo pipefail  # fail fast; log every command

# Install a private Python package from a wheel stored in a Volume
pip install /Volumes/prod_infra/shared/packages/my_package-1.0.0-py3-none-any.whl

# Set environment variable available to Spark workers
echo "export MY_API_ENDPOINT=https://api.internal.example.com" >> /etc/environment
```

**Best practice**: store init scripts in Unity Catalog Volumes (not DBFS), which provides
governance and version control. Reference via the Volume path:
`/Volumes/catalog/schema/volume/init_scripts/script.sh`.

**Minimize init script use**: each init script extends cluster startup time. Prefer
cluster-scoped Python library installations via the cluster's `libraries` configuration
(PyPI packages, .whl files) over init scripts where possible.

---

## 10. Serverless Compute {#serverless}

Serverless compute (GA for Jobs and DLT as of Databricks Runtime 14.x) eliminates all
cluster configuration. Databricks provisions, sizes, and terminates compute transparently.

**Serverless tradeoffs**:

| Dimension | Serverless | Job Cluster |
|---|---|---|
| Startup time | ~5-10 seconds | 2-5 minutes (or ~30s with pool) |
| Configuration | None | Full control |
| Cost | Serverless DBU premium (~20-30% over job cluster) | Lower DBU rate |
| Spot support | Managed by Databricks (opaque) | Explicit spot config |
| Recommended for | Teams without platform engineering capacity | Teams requiring cost optimization and fine-grained control |

---

## 11. Configuration Templates {#templates}

### Production Job Cluster (DABs cluster spec)

```yaml
# Reusable cluster spec for production ETL jobs (referenced in bundle.yml)
job_cluster_key: de_etl_cluster
new_cluster:
  spark_version: "15.4.x-scala2.12"
  node_type_id: m5.4xlarge
  driver_node_type_id: m5.xlarge       # smaller driver — not running tasks
  num_workers: 8
  aws_attributes:
    first_on_demand: 1                  # driver on on-demand; workers on spot
    availability: SPOT_WITH_FALLBACK
    spot_bid_price_percent: 100
  spark_conf:
    "spark.sql.adaptive.enabled": "true"
    "spark.sql.adaptive.coalescePartitions.enabled": "true"
    "spark.databricks.delta.optimizeWrite.enabled": "true"
    "spark.databricks.delta.autoCompact.enabled": "true"
  custom_tags:
    team: data-engineering
    env: "{{bundle.target}}"
    project: orders-lakehouse
```

### Autoscaling Cluster for Mixed ETL Workloads

```yaml
new_cluster:
  spark_version: "15.4.x-scala2.12"
  node_type_id: m5.2xlarge
  autoscale:
    min_workers: 2
    max_workers: 20
  aws_attributes:
    first_on_demand: 1
    availability: SPOT_WITH_FALLBACK
    spot_bid_price_percent: 100
  enable_elastic_disk: true
  spark_conf:
    "spark.sql.adaptive.enabled": "true"
    "spark.databricks.delta.optimizeWrite.enabled": "true"
```

### ML Training Cluster (Fixed Size, GPU)

```yaml
new_cluster:
  spark_version: "15.4.x-gpu-ml-scala2.12"   # GPU + ML Runtime
  node_type_id: g4dn.xlarge                   # NVIDIA T4 GPU
  num_workers: 4                               # Fixed — autoscaling breaks distributed ML
  aws_attributes:
    availability: ON_DEMAND                    # GPU spot availability is unreliable
  spark_conf:
    "spark.task.resource.gpu.amount": "1"
```
