# Unity Catalog

> **Sources**: Databricks Unity Catalog Documentation.
> https://docs.databricks.com/en/data-governance/unity-catalog/index.html
> Unity Catalog Privileges. https://docs.databricks.com/en/data-governance/unity-catalog/manage-privileges/index.html
> Delta Sharing. https://docs.databricks.com/en/delta-sharing/index.html

## Table of Contents

1. [What Unity Catalog Solves](#overview)
2. [Metastore Architecture](#metastore)
3. [Three-Level Namespace](#namespace)
4. [External Locations and Storage Credentials](#external-locations)
5. [Managed vs External Tables](#managed-external)
6. [Privilege Hierarchy and RBAC](#rbac)
7. [Row-Level Security via Row Filters](#row-filters)
8. [Column-Level Security via Column Masks](#column-masks)
9. [Automated Lineage](#lineage)
10. [Audit Logging](#audit)
11. [Delta Sharing](#delta-sharing)
12. [Unity Catalog + DLT](#dlt-integration)

---

## 1. What Unity Catalog Solves {#overview}

Before Unity Catalog, each Databricks workspace had its own Hive Metastore — creating
isolated data silos, duplicate governance logic, and no cross-workspace lineage. Unity
Catalog provides a single governance plane across all workspaces in a Databricks account,
backed by a centralized metastore per cloud region.

**Capabilities provided**:

| Capability | Mechanism |
|---|---|
| Centralized data catalog | Three-level namespace visible across all workspaces |
| Fine-grained access control | GRANT/REVOKE on catalogs, schemas, tables, views, volumes, functions |
| Row-level security | Row filter functions assigned to tables |
| Column-level security | Column mask functions assigned to columns |
| Automated data lineage | Column-level lineage captured automatically for all SQL and DLT operations |
| Data sharing across organizations | Delta Sharing protocol (open standard) |
| Audit logging | All data access and admin events to cloud audit logs |
| Volumes (unstructured data) | Governed access to files in cloud object storage |

---

## 2. Metastore Architecture {#metastore}

One Unity Catalog **metastore** exists per cloud region per Databricks account. All
workspaces in that region attach to the same metastore, sharing the catalog and governance
plane. The metastore is not a compute resource — it is a metadata store only.

```
Databricks Account
└── Unity Catalog Metastore (one per region)
    ├── Catalog (one per domain/env)
    │   ├── Schema (one per layer/subject)
    │   │   ├── Tables (Delta, external, views)
    │   │   ├── Volumes (unstructured file access)
    │   │   └── Functions (registered UDFs)
    │   └── ...
    └── ...
```

**Workspace attachment**: each workspace is attached to exactly one metastore. Admins can
reassign workspace attachment, but a workspace cannot span metastores.

**Storage**: the metastore has a root storage location (S3/ADLS/GCS) where managed tables
and schema-level managed data are written by default.

---

## 3. Three-Level Namespace {#namespace}

Every object in Unity Catalog is addressed as `catalog.schema.table` (or
`catalog.schema.volume`, `catalog.schema.function`, etc.).

```sql
-- Create catalog (workspace admin or metastore admin)
CREATE CATALOG IF NOT EXISTS prod_sales
  COMMENT 'Production data for the Sales domain';

-- Create schema within catalog
CREATE SCHEMA IF NOT EXISTS prod_sales.orders
  COMMENT 'Bronze/Silver/Gold for the Orders entity'
  MANAGED LOCATION 's3://company-datalake/unity-catalog/prod_sales/orders/';

-- Create a managed Delta table
CREATE TABLE IF NOT EXISTS prod_sales.orders.silver_orders (
  order_id    STRING    NOT NULL,
  customer_id STRING    NOT NULL,
  amount      DOUBLE,
  order_date  DATE,
  region      STRING
)
USING DELTA
COMMENT 'Validated, deduplicated orders. Source: bronze_orders via DLT.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.columnMapping.mode' = 'name'
);

-- Query using three-level namespace
SELECT * FROM prod_sales.orders.silver_orders WHERE region = 'APAC';

-- Set default catalog and schema in a session to avoid repeating the prefix
USE CATALOG prod_sales;
USE SCHEMA orders;
SELECT * FROM silver_orders;
```

**Naming convention**:

| Level | Pattern | Example |
|---|---|---|
| Catalog | `{env}_{domain}` | `prod_sales`, `dev_marketing`, `staging_finance` |
| Schema | `{layer}_{subject}` | `bronze_orders`, `silver_customers`, `gold_revenue` |
| Table | `{entity}` or `{entity}_{qualifier}` | `orders`, `customers_scd2`, `daily_revenue` |

---

## 4. External Locations and Storage Credentials {#external-locations}

An **external location** defines a path in cloud object storage that Unity Catalog governs.
A **storage credential** holds the cloud identity (IAM role, managed identity, service
account) that Databricks uses to access that path.

```sql
-- 1. Create a storage credential (account admin only)
--    The IAM role / managed identity is configured outside Databricks first.
CREATE STORAGE CREDENTIAL raw_data_cred
  WITH AWS_IAM_ROLE ARN 'arn:aws:iam::123456789:role/databricks-uc-role'
  COMMENT 'Access credential for raw-data S3 bucket';

-- 2. Create an external location using the credential
CREATE EXTERNAL LOCATION raw_data_s3
  URL 's3://company-raw-data/'
  WITH (STORAGE CREDENTIAL raw_data_cred)
  COMMENT 'External location for raw ingestion data';

-- 3. Grant EXTERNAL USE to the principal that needs to read from this location
GRANT READ FILES ON EXTERNAL LOCATION raw_data_s3 TO `data_engineers`;
GRANT WRITE FILES ON EXTERNAL LOCATION raw_data_s3 TO `dlt_service_principal`;

-- 4. Validate connectivity
DESCRIBE EXTERNAL LOCATION raw_data_s3;
```

---

## 5. Managed vs External Tables {#managed-external}

| Dimension | Managed Table | External Table |
|---|---|---|
| Storage location | Unity Catalog-managed path (metastore root or schema location) | User-specified external location path |
| DROP TABLE behavior | Drops both metadata AND underlying data files | Drops metadata only; data files remain |
| CLONE / COPY behavior | Data moves with the table when schema is changed | External files unaffected |
| Governance | Full Unity Catalog governance | Full Unity Catalog governance |
| Typical use | Tables created and owned by Databricks pipelines | Tables sharing data with non-Databricks systems; data that must survive DROP TABLE |

```sql
-- Managed table (storage path determined by schema's managed location)
CREATE TABLE prod_sales.orders.silver_orders (...) USING DELTA;

-- External table (data already exists at this path, or will be written there)
CREATE TABLE prod_sales.orders.raw_feed
  USING DELTA
  LOCATION 's3://company-raw-data/feeds/orders/'
  COMMENT 'External Delta table — not managed by Unity Catalog lifecycle.';
```

---

## 6. Privilege Hierarchy and RBAC {#rbac}

Unity Catalog uses a hierarchical privilege model. Privileges granted at a higher level
are inherited by all objects within. Revoking at a lower level overrides inheritance.

```
METASTORE
  └── CATALOG → USE CATALOG, CREATE SCHEMA, USE SCHEMA (inherited), ...
        └── SCHEMA → USE SCHEMA, CREATE TABLE, CREATE VOLUME, ...
              └── TABLE → SELECT, MODIFY, READ VOLUME, WRITE VOLUME
```

**Core privilege reference**:

| Privilege | Applies to | Description |
|---|---|---|
| `USE CATALOG` | Catalog | Required to access any object within a catalog. |
| `USE SCHEMA` | Schema | Required to access any object within a schema. |
| `SELECT` | Table, View | Read data from a table or view. |
| `MODIFY` | Table | INSERT, UPDATE, DELETE, MERGE, OPTIMIZE, VACUUM. |
| `CREATE TABLE` | Schema | Create tables within a schema. |
| `CREATE SCHEMA` | Catalog | Create schemas within a catalog. |
| `READ FILES` | External Location, Volume | Read files from the storage path. |
| `WRITE FILES` | External Location, Volume | Write files to the storage path. |
| `EXECUTE` | Function | Call a registered function or model. |
| `ALL PRIVILEGES` | Any | All applicable privileges on the object. |

```sql
-- Grant a data engineer group read + write access to the orders schema
GRANT USE CATALOG ON CATALOG prod_sales TO `data_engineers`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA prod_sales.orders TO `data_engineers`;

-- Grant analysts read-only access to Gold tables
GRANT USE CATALOG ON CATALOG prod_sales TO `analysts`;
GRANT USE SCHEMA, SELECT ON SCHEMA prod_sales.gold_revenue TO `analysts`;

-- Grant a service principal (used by DLT or Airflow) write access
GRANT USE CATALOG ON CATALOG prod_sales TO `orders-dlt-sp`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA prod_sales.orders TO `orders-dlt-sp`;

-- Review current privileges on a table
SHOW GRANTS ON TABLE prod_sales.orders.silver_orders;
```

---

## 7. Row-Level Security via Row Filters {#row-filters}

A row filter is a SQL function that takes the current user context (via `CURRENT_USER()` or
`IS_ACCOUNT_GROUP_MEMBER()`) and returns a boolean expression. When assigned to a table,
the filter is applied transparently on every SELECT — the user never sees rows they are
not permitted to access.

```sql
-- 1. Create the row filter function
CREATE FUNCTION prod_sales.security.filter_by_region(region STRING)
  RETURN IS_ACCOUNT_GROUP_MEMBER('global_analyst')    -- global analysts see all regions
      OR region = SESSION_CONTEXT('user_region');     -- others see only their region

-- 2. Assign the row filter to the table
ALTER TABLE prod_sales.orders.silver_orders
  SET ROW FILTER prod_sales.security.filter_by_region ON (region);

-- 3. Verify (as a user in a specific region group)
SELECT DISTINCT region FROM prod_sales.orders.silver_orders;
-- Returns only the regions accessible to the current user.

-- 4. Remove the row filter
ALTER TABLE prod_sales.orders.silver_orders DROP ROW FILTER;
```

**Setting user-level session context** (used in filter functions):

```python
# In a notebook or connection string — set the session context variable
spark.sql("SET SESSION_CONTEXT('user_region', 'APAC')")
```

---

## 8. Column-Level Security via Column Masks {#column-masks}

A column mask is a SQL function that returns a masked version of a column value. When
assigned to a column, the mask is applied transparently on every SELECT.

```sql
-- 1. Create the column mask function — returns full PII only for authorized users
CREATE FUNCTION prod_sales.security.mask_customer_email(email STRING)
  RETURN CASE
    WHEN IS_ACCOUNT_GROUP_MEMBER('pii_authorized') THEN email
    ELSE CONCAT(LEFT(email, 2), '***@***.***')
  END;

-- 2. Assign the column mask
ALTER TABLE prod_sales.customers.silver_customers
  ALTER COLUMN email SET MASK prod_sales.security.mask_customer_email;

-- 3. Verify (as a user without pii_authorized group membership)
SELECT email FROM prod_sales.customers.silver_customers LIMIT 5;
-- Returns: ab***@***.***

-- 4. Remove the column mask
ALTER TABLE prod_sales.customers.silver_customers
  ALTER COLUMN email DROP MASK;
```

---

## 9. Automated Lineage {#lineage}

Unity Catalog captures column-level lineage automatically for all SQL queries,
DLT pipelines, notebooks, and jobs executed within workspaces attached to the metastore.
No configuration is required. Lineage is visible in the Catalog Explorer UI and via the
REST API.

```python
import requests

# Query the Unity Catalog lineage API
workspace_url = "https://<workspace>.azuredatabricks.net"
token = dbutils.secrets.get(scope="de-secrets", key="databricks-token")  # type: ignore[name-defined]

# Get downstream lineage from a specific table
response = requests.get(
    f"{workspace_url}/api/2.0/lineage-tracking/table-lineage",
    headers={"Authorization": f"Bearer {token}"},
    params={
        "table_name": "prod_sales.orders.silver_orders",
        "include_entity_lineage": True,
    },
    timeout=30,
)
lineage_data = response.json()

# Downstream tables (what reads from silver_orders)
for downstream in lineage_data.get("downstream_tables", []):
    print(downstream["name"])

# Upstream tables (what silver_orders was derived from)
for upstream in lineage_data.get("upstream_tables", []):
    print(upstream["name"])
```

---

## 10. Audit Logging {#audit}

Unity Catalog emits structured audit events to cloud-native logging services
(AWS CloudTrail, Azure Monitor / Event Hubs, GCP Cloud Logging). Events are also
available in the Databricks system tables under `system.access.audit` (enabled per workspace).

```sql
-- Query audit logs from the system catalog (must be enabled by account admin)
SELECT
  event_time,
  user_identity.email AS user_email,
  event_type,
  request_params.full_name_arg AS table_name,
  response.status_code
FROM system.access.audit
WHERE event_type = 'getTable'
  AND event_time >= CURRENT_TIMESTAMP - INTERVAL 7 DAYS
ORDER BY event_time DESC;

-- Find all users who accessed a specific sensitive table in the last 30 days
SELECT DISTINCT
  user_identity.email,
  MIN(event_time) AS first_access,
  MAX(event_time) AS last_access,
  COUNT(*) AS access_count
FROM system.access.audit
WHERE event_type IN ('getTable', 'runCommand')
  AND request_params.full_name_arg = 'prod_sales.customers.silver_customers'
  AND event_time >= CURRENT_TIMESTAMP - INTERVAL 30 DAYS
GROUP BY user_identity.email
ORDER BY access_count DESC;
```

---

## 11. Delta Sharing {#delta-sharing}

Delta Sharing is an open-source protocol (governed by the Linux Foundation) for sharing
live Delta Lake tables across organizations without copying data. The recipient reads
directly from the provider's cloud storage via a pre-signed URL issued by the provider's
Sharing Server (managed by Unity Catalog).

```sql
-- Provider side: create a share and add tables
CREATE SHARE orders_for_partner
  COMMENT 'Shared Gold revenue data for Acme Corp analyst access';

ALTER SHARE orders_for_partner
  ADD TABLE prod_sales.gold_revenue.daily_revenue
  PARTITION (region = 'APAC');          -- share only APAC partition

-- Create the recipient (external organization)
CREATE RECIPIENT acme_corp_analysts;

-- Generate the activation link for the recipient
DESCRIBE RECIPIENT acme_corp_analysts;  -- contains the activation_link

-- Grant SELECT on the share to the recipient
GRANT SELECT ON SHARE orders_for_partner TO RECIPIENT acme_corp_analysts;

-- Recipient side (in their own Databricks workspace or open-source client)
CREATE CATALOG apac_revenue_from_provider
  USING SHARE provider_workspace.orders_for_partner;

SELECT * FROM apac_revenue_from_provider.gold_revenue.daily_revenue;
```

---

## 12. Unity Catalog + DLT {#dlt-integration}

When a DLT pipeline is configured with a `catalog` and `target`, DLT publishes tables
directly into Unity Catalog. The pipeline's service principal must hold `CREATE TABLE`
and `MODIFY` on the target schema.

**Key behaviors**:
- DLT creates the schema (`catalog.target`) if it does not exist, provided the service
  principal has `CREATE SCHEMA` on the catalog.
- Tables published by DLT are governed by Unity Catalog privileges immediately — no
  separate ACL step is required.
- Column-level lineage from DLT source → target is captured automatically.
- Row filters and column masks applied to source tables are enforced during DLT reads
  if the pipeline's service principal does not hold `pii_authorized` group membership.
  Configure the service principal's group membership carefully for DLT pipelines that
  must read raw PII for transformation before masking in Silver.
