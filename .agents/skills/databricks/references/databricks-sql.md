# Databricks SQL

> **Sources**: Databricks SQL Documentation.
> https://docs.databricks.com/en/sql/index.html
> SQL Warehouse Types. https://docs.databricks.com/en/compute/sql-warehouse/index.html
> Lakeview Dashboards. https://docs.databricks.com/en/dashboards/index.html
> AI Functions. https://docs.databricks.com/en/large-language-models/ai-functions.html

## Table of Contents

1. [SQL Warehouse Types](#warehouses)
2. [Photon and Query Acceleration](#photon)
3. [Query Editor and History](#query-editor)
4. [Lakeview Dashboards](#lakeview)
5. [Alerts and Notification Channels](#alerts)
6. [BI Connectors](#bi-connectors)
7. [AI Functions in SQL](#ai-functions)
8. [SQL Optimization on Delta Lake](#sql-optimization)
9. [Best Practices](#best-practices)

---

## 1. SQL Warehouse Types {#warehouses}

| Type | Description | Best for | Startup time |
|---|---|---|---|
| **Serverless** | Databricks-managed compute. No cluster config. Instant scaling. No cold-start penalty. | Most workloads. Default choice for new deployments. | ~5 seconds |
| **Pro** | Customer-managed VPC/VNet. Photon enabled. Advanced features (result caching, query federation). | Regulated workloads requiring data residency. Large-scale analytics. | 2-5 minutes |
| **Classic** | Legacy managed compute without all Pro features. | Workloads with existing Classic configuration. Avoid for new deployments. | 2-5 minutes |

**Sizing (Serverless and Pro)**:

| Size | Use case |
|---|---|
| `2X-Small` | Lightweight queries, dashboards, development |
| `X-Small` | Small team analytics, light BI workloads |
| `Small` | Medium-scale queries, 5-10 concurrent users |
| `Medium` | Production BI with 10-30 concurrent users |
| `Large` | Heavy analytical workloads, complex joins at scale |
| `X-Large` | Extremely large-scale, data-intensive queries |

**Clustering (Serverless and Pro)**: multiple cluster instances are added automatically
when concurrent query demand exceeds single-cluster capacity. Set `max_num_clusters` to
bound total compute.

```sql
-- SQL warehouse configuration is managed via Databricks UI or REST API
-- Example: query to confirm active warehouse and Photon status
SELECT current_warehouse(), 
       spark_conf('spark.databricks.photon.enabled') AS photon_enabled;
```

---

## 2. Photon and Query Acceleration {#photon}

Photon is enabled by default on all Pro and Serverless SQL Warehouses. It provides
vectorized execution of SQL operations using SIMD instructions, substantially reducing
CPU time for column-scan-heavy queries.

**Photon impact by operation type**:

| Operation | Typical speedup |
|---|---|
| Table scans (column filtering) | 3-8x |
| Aggregations (GROUP BY, COUNT, SUM) | 2-5x |
| Sort-merge joins | 2-4x |
| String operations | 2-3x |
| Window functions | 2-4x |
| OPTIMIZE (file compaction) | 2-6x |

**Result caching**: Databricks SQL caches query results automatically. An identical query
with the same warehouse and table version returns cached results instantly. Cache is
invalidated when the underlying Delta table is modified.

---

## 3. Query Editor and History {#query-editor}

The Databricks SQL Query Editor provides:
- Multi-statement editing with syntax highlighting (SQL, including Delta-specific syntax)
- Query parameters (parameterized queries with `{{parameter_name}}`)
- Query history with full execution metadata (duration, bytes scanned, rows returned)
- Visual Query Profiler (execution plan visualization, bottleneck identification)

**Parameterized queries**:

```sql
-- Parameterized SQL: {{parameter}} syntax for reusable queries
SELECT
    region,
    SUM(total_revenue) AS revenue,
    COUNT(DISTINCT customer_id) AS customers
FROM prod_sales.gold_revenue.daily_revenue
WHERE order_date BETWEEN '{{start_date}}' AND '{{end_date}}'
  AND region = '{{region}}'
GROUP BY region
ORDER BY revenue DESC;
```

**Query Profiler** (Pro and Serverless): access via the query history panel after a
query completes. The profiler shows the physical execution plan as a DAG with per-node
metrics: rows processed, bytes scanned, shuffle bytes, time spent. Use it to identify:
- Missing Delta statistics (ANALYZE TABLE)
- Skewed joins (one partition handling 90%+ of data)
- Unintended full table scans (missing Z-Order or liquid clustering on filter columns)

---

## 4. Lakeview Dashboards {#lakeview}

Lakeview is the native Databricks BI dashboard product (GA, replaces the legacy DBSQL
Dashboards). Lakeview dashboards are assets governed by Unity Catalog and deployable via
Databricks Asset Bundles.

**Capabilities**:
- Drag-and-drop canvas layout with widgets (charts, counters, tables, text, filters)
- Automatic connection to SQL Warehouse for queries
- Dataset layer: define reusable named datasets (SQL queries) referenced by widgets
- Schedule and email delivery
- Publish as a web app for external stakeholders (limited to read-only view)
- Genie integration: embed a Genie conversational AI panel alongside static charts
- DABs deployable: include Lakeview dashboards as bundle resources

**Dashboard as Code (DABs)**:

```yaml
# bundle.yml — Lakeview dashboard resource
resources:
  dashboards:
    revenue_dashboard:
      display_name: "[${bundle.target}] Daily Revenue Dashboard"
      warehouse_id: "${var.sql_warehouse_id}"
      file_path: ./dashboards/revenue_dashboard.lvdash.json    # exported dashboard file
```

**Best practices**:
- Use Lakeview dataset layer to centralize query logic — widgets reference datasets,
  not raw SQL — making maintenance easier and preventing query duplication.
- Point datasets at Gold layer tables only. Never query Bronze or Silver from a dashboard
  — latency, data quality, and access control issues.
- Set a schedule on underlying Lakeflow Jobs to refresh Gold tables before dashboard
  delivery. Do not rely on dashboard auto-refresh for time-sensitive KPIs.

---

## 5. Alerts and Notification Channels {#alerts}

Databricks SQL Alerts run a query on a schedule and send a notification when a condition
is met. They are the correct mechanism for data quality monitoring without a full Great
Expectations setup, and for operational KPI alerting.

```sql
-- Alert query: returns rows when condition is violated
-- If the query returns any rows, the alert fires
SELECT
    'LATE_DELIVERY_RATE_HIGH' AS alert_name,
    region,
    COUNT(*) AS late_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY region), 2) AS late_pct
FROM prod_sales.orders.gold_order_summary
WHERE order_date = CURRENT_DATE - INTERVAL 1 DAY
GROUP BY region
HAVING late_pct > 5.0;   -- alert fires if any region exceeds 5% late rate
```

**Notification Channels** (configured in Workspace Settings → Notification Destinations):
- Email (one or many recipients)
- Slack (webhook)
- PagerDuty
- Microsoft Teams (webhook)
- Generic webhook

---

## 6. BI Connectors {#bi-connectors}

### Power BI (DirectQuery mode — recommended)

DirectQuery sends each Power BI visual as a SQL query to the Databricks SQL Warehouse.
Data is never imported into Power BI's local model — always fresh from Delta.

**Setup**: In Power BI Desktop → Get Data → Azure → Azure Databricks → provide:
- Server hostname: `<workspace>.azuredatabricks.net`
- HTTP path: from SQL Warehouse → Connection Details
- Authentication: Personal Access Token (dev) or Service Principal (prod)
- Mode: **DirectQuery** (always; Import mode loses Delta freshness benefits)

**Performance in DirectQuery**: ensure Gold layer tables have liquid clustering or
Z-Ordering on the columns Power BI filters on (date, region, product). Without data
skipping, every visual interaction triggers a full table scan.

### Tableau

Tableau connects via the Databricks connector (installed via Tableau Exchange or bundled
with Tableau 2023.3+).

**Connection string fields**:
- Server: `<workspace>.azuredatabricks.net`
- HTTP path: SQL Warehouse HTTP path
- Authentication: Personal Access Token or OAuth (Tableau 2023.3+)
- Initial SQL (optional): `SET CATALOG prod_sales; SET SCHEMA gold_revenue;`

### Looker Studio (Google)

Use the Databricks JDBC driver with Looker Studio's BigQuery connector alternative, or
the Simba JDBC driver. Point at SQL Warehouse endpoint. Looker's LookML models on top
of Delta tables benefit significantly from liquid clustering on dimension keys.

---

## 7. AI Functions in SQL {#ai-functions}

Databricks SQL supports built-in AI functions that invoke foundation models directly
inside SQL queries — eliminating the need to extract data, send it to an external API,
and reload results. Model choice is flexible: select the model best suited to the task.

```sql
-- Document parsing and intelligence (GA at DAIS 2026)
SELECT
    file_path,
    ai_parse_document(
        file_content,
        'Extract: invoice_number, vendor_name, total_amount, invoice_date',
        model => 'databricks-meta-llama-3-1-405b-instruct'    -- model choice per task
    ) AS extracted_fields
FROM prod_sales.raw.invoice_files;

-- Text classification
SELECT
    customer_id,
    comment_text,
    ai_classify(
        comment_text,
        ARRAY['positive', 'negative', 'neutral'],
        model => 'databricks-mixtral-8x7b-instruct'
    ) AS sentiment
FROM prod_sales.silver.customer_comments;

-- Named entity extraction
SELECT
    document_id,
    ai_extract(
        body_text,
        ARRAY['company_name', 'person_name', 'dollar_amount'],
        model => 'databricks-meta-llama-3-3-70b-instruct'
    ) AS entities
FROM prod_sales.bronze.contracts;

-- Text generation / summarization
SELECT
    ticket_id,
    ai_gen(
        CONCAT('Summarize in 2 sentences: ', description),
        model => 'databricks-mixtral-8x7b-instruct'
    ) AS summary
FROM prod_sales.silver.support_tickets;

-- Similarity / semantic search (returns score 0-1)
SELECT
    product_id,
    product_description,
    ai_similarity(
        product_description,
        'wireless noise-cancelling headphones'
    ) AS relevance_score
FROM prod_sales.gold.product_catalog
ORDER BY relevance_score DESC
LIMIT 20;
```

**Model selection guidance for AI functions**:

| Task | Recommended model | Rationale |
|---|---|---|
| Document parsing, structured extraction | `databricks-meta-llama-3-1-405b-instruct` | Largest context, best structured output |
| Classification, sentiment | `databricks-mixtral-8x7b-instruct` | Fast, cost-effective for single-label tasks |
| Summarization | `databricks-meta-llama-3-3-70b-instruct` | Good quality/cost balance |
| Code generation | `databricks-meta-llama-3-1-70b-instruct` | Code-optimized |
| Complex reasoning | `databricks-claude-3-5-sonnet` or `databricks-dbrx-instruct` | Complex multi-step logic |

**Batch inference at scale**: AI functions in SQL execute in parallel across Spark
partitions automatically. For tables with millions of rows, use `OPTIMIZE` + liquid
clustering on the primary key first to minimize partition overhead, then run the AI
function in a SQL query or DLT pipeline.

---

## 8. SQL Optimization on Delta Lake {#sql-optimization}

```sql
-- 1. Ensure statistics are collected for query optimizer
ANALYZE TABLE prod_sales.gold_revenue.daily_revenue COMPUTE STATISTICS FOR ALL COLUMNS;

-- 2. OPTIMIZE before querying (scheduled via Lakeflow Jobs, not on-demand per query)
OPTIMIZE prod_sales.gold_revenue.daily_revenue
ZORDER BY (order_date, region);   -- or use liquid clustering instead (see performance-optimization.md)

-- 3. Partition pruning: always filter on partition columns first
SELECT * FROM prod_sales.gold_revenue.daily_revenue
WHERE order_date = CURRENT_DATE    -- reads only today's partition file(s)
  AND region = 'APAC';

-- 4. Predicate pushdown: push filters inside CTEs to minimize data read
WITH filtered_orders AS (
    SELECT * FROM prod_sales.orders.silver_orders
    WHERE order_date >= DATEADD(DAY, -7, CURRENT_DATE)   -- filter pushed to Delta scan
      AND region = 'EMEA'
)
SELECT
    order_date,
    SUM(amount) AS daily_revenue
FROM filtered_orders
GROUP BY order_date;

-- 5. Result caching: identical queries within a session return cached results
-- Use CACHE TABLE for repeatedly scanned lookup tables
CACHE TABLE prod_sales.dimensions.dim_region;
```

---

## 9. Best Practices {#best-practices}

**Warehouse management**:
- Use **Serverless** warehouses for all new workloads unless regulatory requirements
  mandate data residency in a customer-managed VPC.
- Set `auto_stop_mins = 10` on development warehouses. Production BI warehouses connected
  to live dashboards should stay warm — set `auto_stop_mins = 120` or disable.
- Separate warehouses for BI (shared, autoscaling) and data engineering SQL (job-level,
  terminated after each run) to prevent query queue contention.

**Query hygiene**:
- Never `SELECT *` in production SQL. Explicit column lists allow Delta's column-level
  statistics and liquid clustering to skip irrelevant columns.
- Use CTEs over subqueries for all multi-step transformations — readability and the
  optimizer handles them identically.
- Comment all non-trivial query blocks with business context, not just technical description.
- `EXPLAIN ANALYZE` before deploying any query on tables with > 1M rows.

**Cost control**:
- Route scheduled/automated SQL queries to job-specific SQL Warehouses, not shared
  interactive warehouses. This prevents batch loads from competing with analyst queries.
- Use Delta result caching — identical repeated queries cost nothing after the first run.
- Size warehouses based on concurrency (number of simultaneous users), not query complexity.
  A single heavy query benefits from a larger warehouse; 20 concurrent light queries
  benefit from multiple clusters on a smaller warehouse.
