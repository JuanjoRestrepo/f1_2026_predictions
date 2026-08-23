# Analytics Engineering & Data Modeling Reference

> **References**: Kimball, R., & Ross, M. (2013). _The Data Warehouse Toolkit_
> (3rd ed.). Wiley. — The definitive reference on dimensional modeling.
> dbt Labs Documentation. https://docs.getdbt.com · Inmon, W. H. (2005).
> _Building the Data Warehouse_ (4th ed.). Wiley. · Mazur, A., & Natarajan, J. (2021).
> _Analytics Engineering with dbt_. dbt Labs. · Fishtown Analytics (2016).
> _The dbt Viewpoint_. https://www.getdbt.com/analytics-engineering/viewpoint
> · Codd, E. F. (1970). A Relational Model of Data. _CACM_, 13(6), 377–387.

## Table of Contents

1. [Analytics Engineering — Discipline Definition](#discipline)
2. [dbt — Transformation Framework](#dbt)
3. [Semantic Layer and Metrics Layer](#semantic-layer)
4. [Dimensional Modeling — Kimball Methodology](#dimensional-modeling)
5. [Fact Tables](#fact-tables)
6. [Dimension Tables](#dimension-tables)
7. [Slowly Changing Dimensions (SCDs)](#scd)
8. [Star Schema vs. Snowflake Schema](#schemas)
9. [Data Catalogs](#data-catalogs)
10. [Business Metrics Governance](#metrics-governance)
11. [References](#references)

---

## 1. Analytics Engineering — Discipline Definition {#discipline}

> **Source**: Fishtown Analytics (2016). _The dbt Viewpoint_.
> https://www.getdbt.com/analytics-engineering/viewpoint

### What Analytics Engineering Is

Analytics Engineering is the discipline that sits between data engineering and
data analysis. Analytics engineers apply software engineering best practices
(version control, testing, documentation, modularity) to the transformation layer
of the data stack — the step that converts raw or lightly processed data in the
warehouse into clean, modeled, business-ready datasets.

Before analytics engineering existed as a named discipline, the transformation layer
was split between two groups with opposing weaknesses:

- **Data engineers** built robust, scalable pipelines but were disconnected from
  business semantics — they could load data reliably but did not deeply understand
  what `revenue` means to the finance team.
- **Data analysts** understood business semantics but wrote ad hoc SQL that was
  not version-controlled, tested, documented, or reproducible — every analyst had
  their own definition of `active_user`.

Analytics engineering formalizes this layer: transformation logic is written as
modular, version-controlled SQL models (in dbt), tested with data quality assertions,
documented with business context, and compiled into artifacts that serve the entire
organization with a single authoritative definition of every business metric.

### The Modern Data Stack Architecture

```
Sources (operational DBs, SaaS APIs, files)
  │
  ▼  [Ingestion: Fivetran / Airbyte / Kafka / Spark]
Raw / Bronze Layer (Data Lake / Warehouse landing zone)
  │
  ▼  [Analytics Engineering: dbt]
Staging → Intermediate → Marts (Silver → Gold)
  │
  ▼  [Semantic Layer: dbt Semantic Layer / Cube / LookML]
Metrics Layer (consistent metric definitions)
  │
  ▼  [Consumption]
BI Tools (Power BI, Tableau, Looker) · ML Feature Stores · APIs
```

The analytics engineer owns the dbt layer. The data engineer owns ingestion and
infrastructure. The data analyst consumes the mart layer via SQL or BI tools.

---

## 2. dbt — Transformation Framework {#dbt}

> **Source**: dbt Labs Documentation. https://docs.getdbt.com
> dbt Core is open source (Apache 2.0). dbt Cloud is the managed commercial offering.

### What dbt Is

dbt (data build tool) is a transformation framework that enables analysts and
analytics engineers to write SELECT statements that dbt compiles into DDL/DML
and executes in the target warehouse or lakehouse. dbt does not move data — it
only transforms data that already exists in the warehouse.

dbt provides:

- **SQL-based modeling**: each model is a `.sql` file with a SELECT statement
- **Materialization control**: models can be views, tables, or incremental tables
- **Dependency resolution**: `{{ ref('model_name') }}` creates a DAG of model dependencies
- **Testing**: built-in and custom tests on columns and models
- **Documentation**: auto-generated lineage and data dictionary
- **Macros**: Jinja templating for reusable SQL logic
- **Packages**: community-built reusable models (dbt-utils, dbt-expectations)

### Project Structure

```
dbt_project/
├── dbt_project.yml          # Project configuration: name, version, materialization defaults
├── profiles.yml             # Connection profiles (kept outside the project, not in git)
├── packages.yml             # External package dependencies
├── models/
│   ├── staging/             # 1-to-1 with source tables: rename, recast, light cleaning only
│   │   ├── _staging.yml     # Source definitions and column tests
│   │   ├── stg_orders.sql
│   │   └── stg_customers.sql
│   ├── intermediate/        # Multi-source joins and business logic (not exposed to BI)
│   │   └── int_orders_enriched.sql
│   └── marts/               # Business-domain datasets: fact and dimension tables
│       ├── finance/
│       │   ├── fct_orders.sql
│       │   └── dim_customers.sql
│       └── marketing/
│           └── fct_campaigns.sql
├── tests/                   # Custom singular tests (SQL that returns rows on failure)
│   └── assert_positive_revenue.sql
├── macros/                  # Reusable Jinja macros
│   └── generate_surrogate_key.sql
└── seeds/                   # Static CSV files loaded as tables (small reference data)
    └── country_codes.csv
```

### Model Layers and Responsibilities

**Staging models**: one-to-one with a source table. Apply only: rename columns to
consistent conventions, cast types, add `_loaded_at` metadata. No joins. No
business logic. These are the foundation that all other models build on.

```sql
-- models/staging/stg_orders.sql
-- Convention: stg_ prefix, snake_case, explicit column list (never SELECT *)
WITH source AS (
    SELECT * FROM {{ source('raw', 'orders') }}
),
renamed AS (
    SELECT
        order_id                                    AS order_id,
        customer_id                                 AS customer_id,
        CAST(created_at AS TIMESTAMP)              AS order_created_at,
        CAST(amount AS NUMERIC)                    AS order_amount_usd,
        LOWER(TRIM(status))                        AS order_status,
        region                                     AS region,
        _fivetran_synced                           AS _loaded_at
    FROM source
)
SELECT * FROM renamed
```

**Intermediate models**: multi-source joins and complex business logic. Not
directly consumed by BI tools — exist to break complex transformations into
readable, testable units. Prefix `int_`.

```sql
-- models/intermediate/int_orders_enriched.sql
WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),
customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
)
SELECT
    o.order_id,
    o.order_amount_usd,
    o.order_created_at,
    o.order_status,
    c.customer_segment,
    c.acquisition_channel,
    c.country_code
FROM orders o
LEFT JOIN customers c USING (customer_id)
```

**Mart models**: business-domain tables consumed by BI, APIs, and ML. Structured
as fact and dimension tables. Prefix `fct_` for facts and `dim_` for dimensions.

### Materializations

```yaml
# dbt_project.yml — set materialization defaults per layer
models:
  my_project:
    staging:
      +materialized: view # staging = always fresh, no storage cost
    intermediate:
      +materialized: ephemeral # intermediate = compiled inline, not materialized
    marts:
      +materialized: table # marts = pre-computed for fast BI queries
```

**Incremental materialization** — the most important pattern for large tables:

```sql
-- models/marts/fct_orders.sql
-- Incremental: only process new records added since last run
{{
    config(
        materialized='incremental',
        unique_key='order_id',
        on_schema_change='fail',
        incremental_strategy='merge'    -- INSERT + UPDATE; use 'append' only if no updates
    )
}}

WITH enriched AS (
    SELECT * FROM {{ ref('int_orders_enriched') }}
)
SELECT
    {{ dbt_utils.generate_surrogate_key(['order_id']) }}    AS order_sk,
    order_id,
    order_amount_usd,
    order_created_at,
    order_status,
    customer_segment,
    country_code,
    CURRENT_TIMESTAMP                                        AS _dbt_updated_at
FROM enriched

{% if is_incremental() %}
    -- Only process records newer than the latest record already in the table
    WHERE order_created_at > (SELECT MAX(order_created_at) FROM {{ this }})
{% endif %}
```

### dbt Tests

```yaml
# models/marts/schema.yml
version: 2

models:
  - name: fct_orders
    description: 'One row per order. Grain: order_id.'
    columns:
      - name: order_sk
        description: 'Surrogate key. Unique, non-null.'
        tests:
          - unique
          - not_null

      - name: order_id
        tests:
          - unique
          - not_null
          - relationships: # Referential integrity check
              to: ref('stg_orders')
              field: order_id

      - name: order_amount_usd
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0

      - name: order_status
        tests:
          - accepted_values:
              values: ['completed', 'pending', 'refunded', 'cancelled']
```

### dbt Macros

```sql
-- macros/date_spine.sql
-- Reusable macro that generates a date series between two dates
{% macro date_spine(start_date, end_date) %}
    WITH dates AS (
        {{ dbt_utils.date_spine(
            datepart="day",
            start_date="cast('" ~ start_date ~ "' as date)",
            end_date="cast('" ~ end_date ~ "' as date)"
        ) }}
    )
    SELECT
        date_day,
        EXTRACT(YEAR FROM date_day)  AS year,
        EXTRACT(MONTH FROM date_day) AS month,
        EXTRACT(DOW FROM date_day)   AS day_of_week
    FROM dates
{% endmacro %}
```

---

## 3. Semantic Layer and Metrics Layer {#semantic-layer}

> **Source**: dbt Labs (2022). _The dbt Semantic Layer_.
> https://docs.getdbt.com/docs/build/about-metricflow
> Atlan (2023). _What is a Semantic Layer?_
> Looker Documentation. https://cloud.google.com/looker/docs/lookml-terms-and-concepts

### What the Semantic Layer Is

The semantic layer is a logical abstraction between raw data and consumption tools
that translates physical data structures (table names, column names, join paths)
into business concepts (metrics, dimensions, entities) defined once and reused
across all tools.

Without a semantic layer, every BI tool, dashboard, and report defines its own
version of `revenue` in its own query. Different teams produce different numbers
for the same metric — a chronic trust problem in data organizations.

The semantic layer provides a **single authoritative definition** of every metric,
centrally governed and versioned, that all tools query consistently.

### MetricFlow — dbt's Semantic Layer Implementation

dbt's semantic layer uses MetricFlow to define metrics and dimensions as YAML
configurations compiled into optimized SQL.

```yaml
# models/marts/finance/semantic_models.yml

semantic_models:
  - name: orders
    description: 'Order-level semantic model. Grain: one row per order.'
    model: ref('fct_orders')

    # Entities define the keys for joining semantic models
    entities:
      - name: order
        type: primary
        expr: order_id
      - name: customer
        type: foreign
        expr: customer_id

    # Dimensions available for slicing metrics
    dimensions:
      - name: order_status
        type: categorical
      - name: order_created_at
        type: time
        type_params:
          time_granularity: day
      - name: region
        type: categorical

    # Measures are the building blocks for metrics
    measures:
      - name: order_count
        agg: count
        expr: order_id
      - name: total_revenue
        agg: sum
        expr: order_amount_usd
      - name: avg_order_value
        agg: average
        expr: order_amount_usd

metrics:
  - name: revenue
    label: 'Total Revenue (USD)'
    description: 'Sum of order_amount_usd for completed orders.'
    type: simple
    type_params:
      measure: total_revenue
    filter: "{{ Dimension('order__order_status') }} = 'completed'"

  - name: revenue_growth_mom
    label: 'Revenue Growth MoM (%)'
    description: 'Month-over-month revenue growth percentage.'
    type: derived
    type_params:
      expr: '(revenue - lag_revenue) / lag_revenue * 100'
      metrics:
        - name: revenue
        - name: revenue
          offset_window: 1 month
          alias: lag_revenue

  - name: conversion_rate
    label: 'Order Conversion Rate'
    type: ratio
    type_params:
      numerator:
        name: order_count
        filter: "{{ Dimension('order__order_status') }} = 'completed'"
      denominator:
        name: order_count
```

**Querying the semantic layer** (Python client):

```python
from dbt_semantic_interfaces.parsing.objects import MetricQueryParameters
# Via dbt Cloud Semantic Layer API or local MetricFlow CLI:
# mf query --metrics revenue --group-by order_created_at__month,region
```

### Semantic Layer vs. Metrics Layer Distinction

**Semantic layer**: the full abstraction including entities, dimensions, joins, and
metrics. Answers "what does this data mean?"

**Metrics layer**: the subset focused specifically on metric definitions —
standardized, versioned, governed business KPIs. Answers "what is our authoritative
definition of revenue, MAU, churn rate?"

The metrics layer is conceptually contained within the semantic layer. Some
organizations implement only the metrics layer (using a tool like dbt metrics or
Cube) without the full semantic layer (entity and join modeling).

---

## 4. Dimensional Modeling — Kimball Methodology {#dimensional-modeling}

> **Source**: Kimball, R., & Ross, M. (2013). _The Data Warehouse Toolkit_ (3rd ed.).
> Wiley. — The foundational text on dimensional modeling. All dimensional modeling
> standards in this section derive directly from Kimball & Ross.

### What Dimensional Modeling Is

Dimensional modeling is a data design methodology optimized for analytical queries —
specifically designed for Data Warehouses and the Gold layer of Lakehouse architectures.
Developed by Ralph Kimball in the 1970s and formalized in _The Data Warehouse Toolkit_,
it organizes data into two types of tables: **fact tables** (measurements) and
**dimension tables** (context), connected in a star or snowflake schema.

Dimensional modeling prioritizes query performance and business intuitiveness over
storage efficiency and normalized form. A dimensional model should be understandable
by a business user without a data engineering background.

### Four-Step Dimensional Design Process (Kimball & Ross, 2013)

Every dimensional model is built by answering four questions in order:

**Step 1 — Select the business process**: the analytical question drives the model.
"What business process do we want to measure?" (e.g., order fulfillment, website
sessions, support ticket resolution)

**Step 2 — Declare the grain**: the grain defines exactly what one row in the fact
table represents. The grain must be stated in business terms before any other design
decision is made. Example: "One row per order line item." This decision determines
every other aspect of the model.

**Step 3 — Identify the dimensions**: for the declared grain, what descriptive
context is available? (Who? What? Where? When? Why?) Each answer is a dimension.

**Step 4 — Identify the facts**: what numeric measurements are recorded at the
declared grain? Facts must be consistent with the grain — they must make sense at
the level of detail defined in Step 2.

### Bus Matrix — The Enterprise Data Warehouse Architecture

The bus matrix is Kimball's tool for planning the enterprise dimensional model.
Rows are business processes; columns are dimensions. An X marks which dimensions
apply to each process. Shared, conformed dimensions (appearing in multiple processes)
enable cross-process analysis.

```
Business Process    | Date | Customer | Product | Store | Order | Campaign
--------------------|------|----------|---------|-------|-------|--------
Order Fulfillment   |  X   |    X     |    X    |   X   |   X   |
Marketing Campaigns |  X   |    X     |         |       |       |   X
Customer Service    |  X   |    X     |    X    |   X   |   X   |
Inventory           |  X   |          |    X    |   X   |       |
```

Conformed dimension: `Customer` appears in all four processes. The same `dim_customers`
table is used in every fact table — changes to customer attributes propagate everywhere.

---

## 5. Fact Tables {#fact-tables}

> **Source**: Kimball & Ross (2013), Ch. 3–4.

### What Fact Tables Are

Fact tables store the quantitative measurements (facts) of a business process at the
declared grain. They are the central tables in a dimensional model. Every row in a
fact table corresponds to exactly one occurrence of the business event at the grain.

Fact tables are typically narrow (few columns), tall (many rows), and are never
browsed directly — they are always queried in combination with dimension tables.

### Types of Facts

| Type              | Definition                                       | Example                                                                                                          |
| ----------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **Additive**      | Can be summed across any dimension               | Revenue, quantity, duration                                                                                      |
| **Semi-additive** | Can be summed across some dimensions but not all | Account balance (additive across accounts, NOT across time — summing daily balances over 30 days is meaningless) |
| **Non-additive**  | Cannot be summed across any dimension            | Ratios, percentages, temperatures                                                                                |

**Key rule**: never store derived ratios (e.g., `conversion_rate`) in a fact table.
Store the component numerator and denominator as additive facts; compute ratios at
query time. This ensures correct aggregation at any grain.

### Types of Fact Tables

**Transaction fact table** (most common): one row per business event.
Grain: one row per order line item. Tall, narrow, fully additive.

```sql
-- models/marts/finance/fct_orders.sql
-- Grain: one row per order line item
-- All facts are additive across all dimensions

SELECT
    {{ dbt_utils.generate_surrogate_key(['order_id', 'line_item_id']) }} AS order_line_sk,

    -- Foreign keys to dimension tables (surrogate keys only — never natural keys)
    customer_sk,
    product_sk,
    date_sk,
    store_sk,

    -- Degenerate dimension (no corresponding dim table — lives in fact)
    order_id,
    line_item_id,

    -- Additive facts
    quantity_ordered                                AS quantity,
    unit_price_usd                                 AS unit_price_usd,
    quantity_ordered * unit_price_usd              AS gross_revenue_usd,
    discount_amount_usd                            AS discount_usd,
    quantity_ordered * unit_price_usd
        - discount_amount_usd                      AS net_revenue_usd,

    -- Audit columns
    CURRENT_TIMESTAMP                              AS _dbt_updated_at

FROM {{ ref('int_order_lines_enriched') }}
```

**Periodic snapshot fact table**: one row per entity per time period.
Grain: one row per account per day. Used for measuring state at regular intervals.

```sql
-- models/marts/finance/fct_account_daily_balance.sql
-- Grain: one row per account per day
-- Note: balance is SEMI-ADDITIVE — only sum across accounts, not across days

SELECT
    account_sk,
    date_sk,
    account_balance_usd    -- Semi-additive: SUM across accounts is valid;
                           -- SUM across dates is not (use MAX or last-period value)
FROM {{ ref('int_account_snapshots') }}
```

**Accumulating snapshot fact table**: one row per business process lifecycle instance.
Grain: one row per order (tracking it through all fulfillment stages).
Multiple date foreign keys — one per milestone.

```sql
-- models/marts/operations/fct_order_fulfillment.sql
-- Grain: one row per order — updated as the order progresses through stages
-- Multiple date FKs model the lifecycle milestones

SELECT
    order_sk,
    customer_sk,
    placed_date_sk,          -- FK to dim_date: when order was placed
    shipped_date_sk,         -- FK to dim_date: when order shipped (NULL until shipped)
    delivered_date_sk,       -- FK to dim_date: when order delivered (NULL until delivered)
    cancelled_date_sk,       -- FK to dim_date: when order cancelled (NULL if not cancelled)
    order_amount_usd,
    -- Derived lag metrics (valid here — derived from same grain)
    DATEDIFF('day', placed_date, shipped_date)   AS days_to_ship,
    DATEDIFF('day', shipped_date, delivered_date) AS days_in_transit
FROM {{ ref('int_order_lifecycle') }}
```

---

## 6. Dimension Tables {#dimension-tables}

> **Source**: Kimball & Ross (2013), Ch. 2, 5–6.

### What Dimension Tables Are

Dimension tables provide the descriptive context (who, what, where, when, why, how)
for the measurements stored in fact tables. They are typically wide (many descriptive
columns) and relatively short (fewer rows than fact tables).

Every dimension table must have a **surrogate key** — a system-generated integer or
UUID that uniquely identifies each row independently of the source system's natural
key. Natural keys (e.g., `customer_id` from the CRM) can change, be reused across
systems, or carry no consistent meaning — surrogate keys are stable, system-independent
identifiers.

### Date Dimension — The Most Important Dimension

The date dimension is present in virtually every dimensional model. Pre-populating
it with all attributes of every date eliminates complex date logic from queries
and enables filtering and grouping by fiscal periods, holidays, and custom attributes.

```sql
-- models/marts/shared/dim_date.sql
-- Grain: one row per calendar day
-- This dimension is a seed or generated table — not derived from a source system

SELECT
    CAST(TO_CHAR(date_day, 'YYYYMMDD') AS INTEGER)  AS date_sk,   -- surrogate key: YYYYMMDD int
    date_day                                          AS full_date,
    EXTRACT(YEAR  FROM date_day)                     AS year,
    EXTRACT(MONTH FROM date_day)                     AS month_number,
    TO_CHAR(date_day, 'Month')                       AS month_name,
    EXTRACT(DOW   FROM date_day)                     AS day_of_week_number,
    TO_CHAR(date_day, 'Day')                         AS day_of_week_name,
    CASE WHEN EXTRACT(DOW FROM date_day) IN (0, 6)
         THEN FALSE ELSE TRUE END                    AS is_weekday,
    EXTRACT(QUARTER FROM date_day)                   AS quarter,
    TO_CHAR(date_day, 'YYYY-Q')                      AS year_quarter,
    TO_CHAR(date_day, 'YYYY-MM')                     AS year_month,
    -- Fiscal year (example: fiscal year starts April 1)
    CASE WHEN EXTRACT(MONTH FROM date_day) >= 4
         THEN EXTRACT(YEAR FROM date_day)
         ELSE EXTRACT(YEAR FROM date_day) - 1
    END                                              AS fiscal_year,
    -- Relative date flags (computed at query time via a view, not stored)
    date_day = CURRENT_DATE                          AS is_today,
    date_day = CURRENT_DATE - 1                      AS is_yesterday
FROM {{ ref('date_spine') }}
```

### Customer Dimension Example

```sql
-- models/marts/shared/dim_customers.sql
-- Grain: one row per customer (current version — see SCDs for history)
-- All natural keys are preserved alongside the surrogate key

SELECT
    {{ dbt_utils.generate_surrogate_key(['customer_id']) }}  AS customer_sk,
    customer_id                                               AS customer_natural_key,
    customer_name,
    email_domain,                                    -- derived: SPLIT_PART(email,'@',2)
    country_code,
    customer_segment,                                -- Bronze, Silver, Gold
    acquisition_channel,
    CAST(first_order_date AS DATE)                  AS first_order_date,
    CAST(created_at AS TIMESTAMP)                   AS customer_created_at,
    is_active,
    CURRENT_TIMESTAMP                               AS _dbt_updated_at
FROM {{ ref('int_customers_enriched') }}
```

---

## 7. Slowly Changing Dimensions (SCDs) {#scd}

> **Source**: Kimball & Ross (2013), Ch. 5. — SCDs are Kimball's most cited contribution
> to dimensional modeling practice.

### The Problem SCDs Solve

Dimension attributes change over time. A customer moves from "Silver" to "Gold" segment.
A product changes its category. A store changes its region.

The question SCDs answer is: **when a dimension attribute changes, what do we do with
the historical records that referenced the old value?**

The answer determines whether historical analysis is possible and how. This is not a
technical question — it is a business question that must be decided by the data consumer.

### SCD Type 0 — Fixed Attributes

The attribute never changes. If the source changes it, the change is ignored.
Used for attributes that are definitionally immutable (e.g., date of birth, original
acquisition channel).

### SCD Type 1 — Overwrite (No History)

The old value is overwritten with the new value. Historical records now reflect the
current attribute value. No history is preserved.

Use when: the old value was incorrect (data quality fix) or historical analysis by
this attribute is not needed.

```sql
-- SCD Type 1: simply update the record in dim_customers
-- dbt handles this via the 'table' materialization with a merge strategy
-- Historical queries will show the CURRENT segment for all past orders
UPDATE dim_customers
SET    customer_segment = 'Gold'
WHERE  customer_id = 'CUST-001';
```

### SCD Type 2 — Add New Row (Full History)

A new row is added for each change, with `valid_from` and `valid_to` date columns
marking the effective period. The old row is closed (valid_to set to the change date).
One surrogate key per version — different surrogate keys for the same natural key
across different time periods.

The fact table's foreign key to the dimension references the surrogate key of the
version that was current **at the time of the event** — this is what enables correct
historical analysis.

```sql
-- models/marts/shared/dim_customers_scd2.sql
-- SCD Type 2: full history with valid_from / valid_to

WITH source AS (
    SELECT * FROM {{ ref('stg_customers') }}
),
-- Detect attribute changes using dbt_utils.generate_surrogate_key on tracked columns
snapshot_data AS (
    SELECT
        customer_id,
        customer_name,
        customer_segment,
        country_code,
        LAG(customer_segment) OVER (PARTITION BY customer_id ORDER BY updated_at)
            AS prev_segment
    FROM source
),
changes AS (
    SELECT *,
        -- A new version starts when any tracked attribute changes
        CASE WHEN customer_segment != prev_segment OR prev_segment IS NULL
             THEN 1 ELSE 0 END AS is_new_version
    FROM snapshot_data
)
SELECT
    {{ dbt_utils.generate_surrogate_key(['customer_id', 'valid_from']) }} AS customer_sk,
    customer_id                                  AS customer_natural_key,
    customer_segment,
    country_code,
    valid_from,
    COALESCE(
        LEAD(valid_from) OVER (PARTITION BY customer_id ORDER BY valid_from),
        '9999-12-31'::DATE
    )                                            AS valid_to,
    valid_to = '9999-12-31'::DATE               AS is_current
FROM changes
WHERE is_new_version = 1
```

**dbt Snapshots** — the standard mechanism for implementing SCD Type 2 in dbt:

```sql
-- snapshots/customer_snapshot.sql
{% snapshot customer_snapshot %}
{{
    config(
        target_schema='snapshots',
        unique_key='customer_id',
        strategy='check',               -- 'check': detect changes in listed columns
        check_cols=['customer_segment', 'country_code', 'customer_name'],
        invalidate_hard_deletes=True,   -- close rows when the source record is deleted
    )
}}
SELECT * FROM {{ source('crm', 'customers') }}
{% endsnapshot %}
-- dbt adds: dbt_scd_id, dbt_valid_from, dbt_valid_to, dbt_updated_at
```

### SCD Type 3 — Add New Column (Limited History)

Adds a new column for the previous value. Only the current and one prior value are
retained. Rarely used in practice because it only supports one period of history
and requires schema changes for each tracked attribute.

```sql
-- SCD Type 3: only current and previous segment are retained
-- Cannot answer "what segment was this customer in March 2022?" beyond the one prior period
ALTER TABLE dim_customers
ADD COLUMN previous_segment VARCHAR(50),
ADD COLUMN segment_change_date DATE;

UPDATE dim_customers
SET    previous_segment = customer_segment,
       segment_change_date = CURRENT_DATE,
       customer_segment = 'Gold'
WHERE  customer_id = 'CUST-001';
```

### SCD Summary

| Type   | History preserved                | Storage cost | Use case                                                                |
| ------ | -------------------------------- | ------------ | ----------------------------------------------------------------------- |
| Type 0 | None — fixed                     | Lowest       | Immutable attributes (DOB, original source)                             |
| Type 1 | None — overwrite                 | Low          | Data corrections; attribute history not needed                          |
| Type 2 | Full — new row per change        | Higher       | Most historical analysis (customer segment, product category)           |
| Type 3 | One prior value only             | Low          | Rare — limited historical need, simple schema                           |
| Type 4 | Current + separate history table | Medium       | High-query frequency on current; occasional history queries             |
| Type 6 | Combined 1+2+3                   | Highest      | Current value (Type 1) + history (Type 2) + prior value column (Type 3) |

**Default choice**: SCD Type 2 is the correct default for any dimension attribute
where historical accuracy in analysis is important. Use Type 1 only for data quality
corrections or where the business explicitly confirms history is not needed.

---

## 8. Star Schema vs. Snowflake Schema {#schemas}

> **Source**: Kimball & Ross (2013), Ch. 2, 12. · Inmon (2005), Ch. 3.

### Star Schema

The star schema places fact tables at the center, surrounded by fully denormalized
dimension tables. Each dimension is a single flat table — all attributes of a
dimension are in one table, regardless of normalization violations.

```
                    dim_date
                       │
dim_product ── fct_order_lines ── dim_customer
                       │
                   dim_store
```

**Why Kimball recommends denormalized dimensions**: analytical queries join the fact
table to dimension tables. Each additional join in a normalized snowflake adds
latency and complexity. Denormalized dimensions eliminate joins within the dimension
at the cost of some redundant storage. Since modern warehouses (Snowflake, BigQuery,
Redshift) have cheap storage, the query simplicity and performance of denormalized
dimensions consistently outweigh the storage cost.

**Advantages**:

- Fewer joins — faster analytical queries
- Simpler SQL — analysts can query without deep schema knowledge
- Self-documenting — all context for a dimension in one table
- Better performance on column-store warehouses

### Snowflake Schema

The snowflake schema normalizes dimension tables into multiple related tables,
reducing redundancy at the cost of additional joins.

```
dim_product_category
        │
dim_product ── fct_order_lines ── dim_customer ── dim_geography
                       │
               dim_date ── dim_fiscal_period
```

**When snowflake schema is appropriate**:

- Very large dimension tables where redundancy has meaningful storage cost (rare in
  modern warehouses)
- When the dimension is maintained by a separate system and normalization aligns
  with that system's model
- When ETL updates to a shared attribute (e.g., product category name) would require
  updating thousands of rows in a denormalized table

**Kimball's position**: prefer the star schema. The snowflake schema's storage
savings are rarely worth the added query complexity in analytical workloads. The
dominant use case for snowflake schemas is when dimension storage is genuinely
expensive — which is uncommon in cloud warehouses with columnar compression.

### Implementation Decision Rule

```
Are any dimension attributes updated frequently AND shared across many rows?
  YES → Consider snowflake for that specific hierarchy (e.g., dim_product → dim_category)
  NO  → Use star schema (denormalized dimension)

Is the dimension table extremely large (> 100M rows with wide attributes)?
  YES → Evaluate snowflake to reduce storage; measure actual query performance impact
  NO  → Star schema

Is the primary consumer a BI tool used by non-technical analysts?
  YES → Star schema — fewer joins, simpler SQL
  NO  → Either is acceptable
```

---

## 9. Data Catalogs {#data-catalogs}

> **Source**: Atlan Documentation. https://atlan.com/what-is-a-data-catalog/
> Databricks Unity Catalog. https://docs.databricks.com/en/data-governance/unity-catalog
> Apache Atlas. https://atlas.apache.org · AWS Glue Data Catalog.
> https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html

### What a Data Catalog Is

A data catalog is a metadata management system that provides:

1. **Discoverability**: search for datasets by name, description, business term, or owner
2. **Understanding**: documentation, column-level descriptions, sample data, data profile
3. **Trust**: data quality scores, freshness metrics, lineage to source
4. **Governance**: ownership, sensitivity classification (PII, PCI), access policies
5. **Lineage**: upstream sources and downstream consumers of each dataset

Without a data catalog, data teams spend significant time answering questions like
"Where is the customer table?", "What does the `revenue` column mean?", and
"Who do I contact if this data is wrong?" — questions that should be self-serviceable.

### Catalog Components

| Component            | Purpose                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------ |
| Technical metadata   | Schema, data types, row counts, storage location, partition keys                           |
| Business metadata    | Business owner, data steward, description, business terms, classification (PII, sensitive) |
| Operational metadata | Freshness (last updated), pipeline job ID, SLA status, quality score                       |
| Social metadata      | User ratings, usage frequency, comments, "trusted by X teams" signals                      |
| Lineage              | Column-to-column and table-to-table lineage graph                                          |

### Data Catalog Tools by Stack

| Stack              | Recommended Catalog                                                                |
| ------------------ | ---------------------------------------------------------------------------------- |
| Databricks         | Unity Catalog (native; integrates lineage, access control, and governance)         |
| AWS                | AWS Glue Data Catalog + optionally DataZone for business metadata                  |
| GCP                | Dataplex + Data Catalog                                                            |
| Multi-cloud / open | Apache Atlas (Hadoop-native), OpenMetadata (open source), Atlan, Alation           |
| dbt-centric        | dbt docs (auto-generated from models + schema.yml); integrates with Atlan, DataHub |

### dbt-Generated Documentation as a Lightweight Catalog

```yaml
# models/marts/finance/schema.yml
version: 2

models:
  - name: fct_orders
    description: |
      One row per order. Grain: order_id.
      Source: stg_orders joined with stg_customers via int_orders_enriched.
      Owner: Data Engineering (data-eng@company.com)
      SLA: Updated every hour. Data available within 90 minutes of transaction.
    meta:
      owner: 'data-engineering'
      classification: 'internal'

    columns:
      - name: order_sk
        description: 'Surrogate key. Generated from order_id.'
      - name: order_amount_usd
        description: |
          Net revenue in USD. Excludes taxes and shipping.
          Definition: gross revenue minus discounts applied at checkout.
          Note: this is NET revenue, not gross. Use gross_revenue_usd for gross figures.
        meta:
          pii: false
          classification: 'financial'
```

---

## 10. Business Metrics Governance {#metrics-governance}

> **Source**: Caserta, J. (2023). _The Metrics Store_. O'Reilly.
> dbt Labs (2023). _The Metrics Layer_. https://docs.getdbt.com/docs/build/metrics-overview
> Transform (2022). _Headless BI and the Metrics Store_.

### Why Metrics Governance Exists

In most data organizations, the same metric is computed differently by different
teams. The finance team computes `revenue` as net of refunds from the ERP. The
sales team computes `revenue` as gross from the CRM. The data team computes
`revenue` from the order database. All three produce different numbers for the
same business question — and no one is wrong within their own context.

Business metrics governance establishes:

1. A single authoritative definition of every business metric
2. A versioning and change management process for metric definitions
3. A governance body (or automated contract) that approves changes
4. A delivery mechanism that propagates the definition to all consuming tools

### Metric Definition Standard

Every governed metric must document:

```yaml
# metrics/revenue.yml
metric:
  name: revenue
  label: 'Net Revenue (USD)'
  version: '2.1.0'
  status: active

  # Authoritative business definition
  definition: |
    Total order value after discounts and refunds, in USD.
    Excludes taxes, shipping, and cancelled orders.
    Source of truth: fct_orders.net_revenue_usd WHERE order_status = 'completed'.

  # What this metric is NOT (prevents misinterpretation)
  not_to_be_confused_with:
    - 'gross_revenue: revenue before discounts are applied'
    - 'gmv (gross merchandise value): total transaction value before any deductions'

  owner:
    team: finance
    contact: finance-analytics@company.com

  computation:
    model: fct_orders
    measure: net_revenue_usd
    filter: "order_status = 'completed'"
    aggregation: SUM

  dimensions:
    - order_created_at
    - region
    - customer_segment
    - product_category

  sla:
    freshness: 'Updated within 30 minutes of transaction'
    accuracy: 'Reconciled daily against finance ERP; tolerance ±0.01%'

  versioning:
    current: '2.1.0'
    changelog:
      - version: '2.1.0'
        date: '2024-06-01'
        change: 'Excluded shipping revenue from definition (previously included)'
        breaking: true
        migration: 'Consumers using v2.0.0 will see ~3% lower revenue figures'
      - version: '2.0.0'
        date: '2024-01-01'
        change: 'Changed from gross to net revenue definition'
        breaking: true
```

### The Three Layers of Metrics Governance

**1. Definition governance**: who decides what `revenue` means?
Typically a cross-functional data governance committee with representatives from
finance, product, and data engineering. Changes to metric definitions require
committee approval and follow the semantic versioning policy.

**2. Technical governance**: how is the definition enforced in code?
The metric definition in dbt's semantic layer (MetricFlow) or a headless BI tool
(Cube, LookML) is the single source of truth. Any query for `revenue` routes through
this definition. BI tools are configured to use the semantic layer rather than writing
their own `SUM(amount)` queries.

**3. Consumption governance**: who can access which metrics?
Unity Catalog, Apache Ranger, or row-level security in the warehouse enforces that
sensitive metrics (compensation data, PII-derived metrics) are accessible only to
authorized teams.

### Metric Certification Tiers

| Tier           | Description                               | Requirements                                                      |
| -------------- | ----------------------------------------- | ----------------------------------------------------------------- |
| **Certified**  | Authoritative, governed, production-ready | Reviewed by governance committee; tested; documented; SLA defined |
| **Validated**  | Accurate but not yet fully governed       | Tested; documented; pending governance approval                   |
| **Draft**      | Under development                         | Not for production use; may change without notice                 |
| **Deprecated** | Being phased out                          | Replacement certified metric identified; sunset date communicated |

---

## 11. References {#references}

**Books:**

- Kimball, R., & Ross, M. (2013). _The Data Warehouse Toolkit_ (3rd ed.). Wiley. — The definitive reference on dimensional modeling.
- Inmon, W. H. (2005). _Building the Data Warehouse_ (4th ed.). Wiley.
- Reis, J., & Housley, M. (2022). _Fundamentals of Data Engineering_. O'Reilly.
- Dehghani, Z. (2022). _Data Mesh_. O'Reilly.
- Caserta, J. (2023). _The Metrics Store_. O'Reilly.

**Official Documentation:**

- dbt Labs Documentation. https://docs.getdbt.com
- dbt Semantic Layer / MetricFlow. https://docs.getdbt.com/docs/build/about-metricflow
- Databricks Unity Catalog. https://docs.databricks.com/en/data-governance/unity-catalog
- Apache Atlas. https://atlas.apache.org
- AWS Glue Data Catalog. https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html
- OpenMetadata. https://open-metadata.org

**Papers:**

- Armbrust, M., et al. (2021). Lakehouse: A New Generation of Open Platforms. _CIDR 2021_.
- Codd, E. F. (1970). A Relational Model of Data for Large Shared Data Banks. _CACM_, 13(6).

**Practitioner references:**

- Fishtown Analytics (2016). The dbt Viewpoint. https://www.getdbt.com/analytics-engineering/viewpoint
- Dehghani, Z. (2019). How to Move Beyond a Monolithic Data Lake to a Distributed Data Mesh. https://martinfowler.com/articles/data-monolith-to-mesh.html
