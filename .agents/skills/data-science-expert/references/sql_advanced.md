# Advanced SQL — Data Science & Data Engineering Reference

> This reference covers advanced SQL patterns used in data analysis, data engineering,
> EDA, and BI reporting. Content validated against: PostgreSQL 16/18 official documentation
> (postgresql.org/docs), Microsoft T-SQL SELECT reference (learn.microsoft.com/sql),
> Winand, M. (2012) _SQL Performance Explained_, Kimball, R. & Ross, M. (2013)
> _The Data Warehouse Toolkit_ (3rd ed.), Molinaro, A. (2009) _SQL Cookbook_ (O'Reilly),
> and Itzik Ben-Gan (2016) _T-SQL Fundamentals_ (3rd ed., Microsoft Press).
> All examples use ANSI SQL unless noted.

## Table of Contents

0. [SQL Order of Execution — Logical Processing Order](#execution-order)
1. [SQL Standards for Data Work](#standards)
2. [Subqueries](#subqueries)
3. [Common Table Expressions (CTEs)](#cte)
4. [Window Functions](#window)
5. [Advanced JOINs](#joins)
6. [Advanced Aggregations — GROUPING SETS, ROLLUP, CUBE](#aggregations)
7. [Set Operations — UNION, INTERSECT, EXCEPT](#set-ops)
8. [Practical Analytical Patterns](#patterns)
9. [Query Optimization & Execution Plans](#optimization)
10. [SQL for Data Science — Analytical Workflows](#ds-patterns)

---

## 0. SQL Order of Execution — Logical Processing Order {#execution-order}

> **Primary references**:
> PostgreSQL 18 Documentation. _Section 7 — Queries_. https://www.postgresql.org/docs/current/queries.html
> Microsoft (2024). _Logical Processing Order of the SELECT statement (T-SQL)_.
> https://learn.microsoft.com/en-us/sql/t-sql/queries/select-transact-sql
> Ben-Gan, I. (2016). _T-SQL Fundamentals_ (3rd ed.). Microsoft Press. Chapter 1.

SQL is a declarative language: you describe the result you want, not the steps to
produce it. As a consequence, the written order of clauses in a query does not match
the order in which the database engine evaluates them. This distinction is one of the
most important concepts in SQL — it explains the root cause of a large class of
common errors and is the foundation for writing correct, efficient queries.

### Logical vs. Physical Execution Order

**Logical execution order** defines which clause can reference the output of which
other clause. This order is standardized across all major RDBMS (PostgreSQL, SQL
Server, MySQL, Oracle, BigQuery, Snowflake, Redshift).

**Physical execution order** is determined by the query optimizer and may differ
significantly from the logical order. The optimizer can reorder operations, use
indexes, apply early termination, and exploit parallelism. However, the result must
always be identical to what the logical order would produce.

**The practical implication**: when reasoning about query correctness (is this alias
available here? can this aggregate be used in this clause?), always reason from the
logical order, not the written order.

### The Logical Execution Order

```
Written order (how you type it)    Logical execution order (how the engine evaluates it)
─────────────────────────────────  ──────────────────────────────────────────────────────
  SELECT                          Step 1.  FROM  — identify base tables
  FROM                            Step 2.  JOIN  — apply join conditions, build working set
  WHERE                           Step 3.  WHERE — filter individual rows (pre-aggregation)
  GROUP BY                        Step 4.  GROUP BY — collapse rows into groups
  HAVING                          Step 5.  HAVING — filter groups (post-aggregation)
  ORDER BY                        Step 6.  SELECT — evaluate expressions, assign aliases
  LIMIT                           Step 7.  DISTINCT — remove duplicate rows (if specified)
                                  Step 8.  ORDER BY — sort the result set
                                  Step 9.  LIMIT / OFFSET / TOP — restrict row count
```

Note on window functions: they are evaluated during the SELECT phase (Step 6), after
WHERE and GROUP BY have already been applied. This is why window functions cannot be
used in WHERE, GROUP BY, or HAVING clauses.

Note on CTEs (WITH clause): they are evaluated before FROM, as named temporary result
sets that the main query references. They do not change the internal logical order.

### Detailed Phase Descriptions

**Step 1 — FROM**: The engine identifies all tables, views, subqueries, or CTEs
referenced in the query. This is where the initial working dataset is established.

**Step 2 — JOIN**: Join conditions are evaluated and the matching rows from multiple
tables are combined into a single working set. For `LEFT JOIN`, unmatched rows from
the left table are preserved with `NULL` values for right-table columns.

**Step 3 — WHERE**: Filters are applied to individual rows. The WHERE clause has
access to all columns from the FROM/JOIN working set. It does not have access to
column aliases defined in SELECT (those do not exist yet) and cannot reference
aggregate functions (aggregation has not happened yet).

**Step 4 — GROUP BY**: Rows are collapsed into groups based on the specified columns.
After this step, each group becomes one row in the working set. Individual row values
are no longer accessible except through aggregate functions.

**Step 5 — HAVING**: Filters are applied to groups (not individual rows). HAVING is
evaluated after GROUP BY and therefore can reference aggregate functions (`COUNT`,
`SUM`, `AVG`, `MAX`, `MIN`). HAVING cannot reference SELECT aliases.

**Step 6 — SELECT**: Column expressions are evaluated, computed columns are derived,
and column aliases are assigned. This is the first point where aliases exist.
Window functions are evaluated here — they operate on the result of all previous steps.

**Step 7 — DISTINCT**: Duplicate rows in the result set are removed (if `DISTINCT`
was specified).

**Step 8 — ORDER BY**: The result set is sorted. ORDER BY is the only clause that
can reference SELECT-defined aliases, because it executes after SELECT.

**Step 9 — LIMIT / OFFSET / TOP**: The row count is restricted. Applied after sorting,
so the top N rows reflect the sort order.

### Consequences of the Logical Order — Common Errors Explained

These errors have a single root cause: incorrect assumptions about clause evaluation order.

#### Error 1 — Using a SELECT alias in WHERE

```sql
-- WRONG: alias 'discounted_price' is defined in SELECT (Step 6)
-- WHERE executes at Step 3 — the alias does not exist yet
SELECT price * 0.9 AS discounted_price
FROM products
WHERE discounted_price > 100;  -- ERROR: column "discounted_price" does not exist

-- CORRECT: reference the expression directly in WHERE
SELECT price * 0.9 AS discounted_price
FROM products
WHERE price * 0.9 > 100;

-- CORRECT ALTERNATIVE: wrap in a subquery or CTE
WITH discounted AS (
    SELECT price * 0.9 AS discounted_price
    FROM products
)
SELECT discounted_price
FROM discounted
WHERE discounted_price > 100;
```

#### Error 2 — Using an aggregate function in WHERE

```sql
-- WRONG: AVG() is an aggregate — aggregation happens at Step 4 (GROUP BY)
-- WHERE executes at Step 3 — aggregates are not yet computed
SELECT departamento, AVG(salario)
FROM empleados
WHERE AVG(salario) > 6000;  -- ERROR: aggregate functions not allowed in WHERE

-- CORRECT: use HAVING, which executes after GROUP BY
SELECT departamento, AVG(salario) AS avg_salary
FROM empleados
GROUP BY departamento
HAVING AVG(salario) > 6000;
```

#### Error 3 — Using a window function in WHERE

```sql
-- WRONG: window functions execute at SELECT (Step 6)
-- WHERE executes at Step 3 — window functions are not yet computed
SELECT nombre, salario,
       RANK() OVER (ORDER BY salario DESC) AS rnk
FROM empleados
WHERE RANK() OVER (ORDER BY salario DESC) <= 5;  -- ERROR

-- CORRECT: wrap in a subquery or CTE — filter after the window function executes
SELECT *
FROM (
    SELECT nombre, salario,
           RANK() OVER (ORDER BY salario DESC) AS rnk
    FROM empleados
) ranked
WHERE rnk <= 5;
```

#### Error 4 — WHERE vs. HAVING: wrong clause for the right task

```sql
-- WRONG: using HAVING to filter individual rows (works, but is inefficient —
-- HAVING fires after GROUP BY, so all rows are grouped before being filtered)
SELECT departamento, COUNT(*) AS headcount
FROM empleados
HAVING departamento = 'IT'  -- Incorrect placement
GROUP BY departamento;

-- CORRECT: WHERE filters rows before grouping — reduces the working set early
SELECT departamento, COUNT(*) AS headcount
FROM empleados
WHERE departamento = 'IT'   -- Filters at Step 3 — before grouping
GROUP BY departamento;
```

### WHERE vs. HAVING — Decision Rule

| Use case                                        | Correct clause                   | Reason                                   |
| ----------------------------------------------- | -------------------------------- | ---------------------------------------- |
| Filter on a column value (non-aggregate)        | `WHERE`                          | Fires before GROUP BY — more efficient   |
| Filter on an aggregate result (COUNT, SUM, AVG) | `HAVING`                         | Fires after GROUP BY — aggregates exist  |
| Filter on a window function result              | Subquery / CTE wrapping `SELECT` | Window functions exist only after SELECT |
| Filter on a SELECT alias                        | Subquery / CTE wrapping `SELECT` | Aliases exist only after SELECT          |

### Optimization Implication — Filter as Early as Possible

The logical order of execution is essential for query optimization: it allows you to filter data as early as possible, reducing the dataset size before more resource-intensive operations.

Applying the correct clause at the earliest possible phase minimizes the number of
rows carried through subsequent (more expensive) operations:

- A `WHERE` filter at Step 3 reduces rows before JOIN expansion, GROUP BY grouping,
  and SELECT expression evaluation.
- Moving a condition from `HAVING` to `WHERE` (when it does not involve an aggregate)
  can yield significant performance gains on large tables, because `WHERE` fires
  before the grouping step reduces rows.
- Pre-filtering in a CTE or subquery before a JOIN reduces the join input size,
  which directly reduces join cost.

```sql
-- SLOW: HAVING used for a non-aggregate filter — groups all rows first
SELECT departamento, COUNT(*) AS headcount
FROM empleados
GROUP BY departamento
HAVING departamento IN ('IT', 'Ventas');  -- Unnecessary late filtering

-- FAST: WHERE used — rows are filtered before grouping
SELECT departamento, COUNT(*) AS headcount
FROM empleados
WHERE departamento IN ('IT', 'Ventas')    -- Early filter
GROUP BY departamento;

-- Pre-filter before an expensive JOIN
-- SLOW: join first, then filter
SELECT e.nombre, d.presupuesto
FROM empleados e
INNER JOIN departamentos d ON e.dept_id = d.id
WHERE e.fecha_ingreso > '2022-01-01';

-- BETTER: pre-filter in a CTE before the join (reduces the join input)
WITH recent_hires AS (
    SELECT *
    FROM empleados
    WHERE fecha_ingreso > '2022-01-01'  -- Filter before join
)
SELECT r.nombre, d.presupuesto
FROM recent_hires r
INNER JOIN departamentos d ON r.dept_id = d.id;
```

---

## 1. SQL Standards for Data Work {#standards}

These rules apply to every SQL artifact produced by this skill.

- Uppercase all keywords: `SELECT`, `FROM`, `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY`,
  `HAVING`, `WITH`, `PARTITION BY`, `OVER`, `CASE`, `WHEN`, `THEN`, `ELSE`, `END`
- `snake_case` for all table and column names
- Never `SELECT *` in production — always name columns explicitly
- CTEs over nested subqueries whenever logic involves more than two steps
- Every non-trivial query block gets an explanatory comment
- Explicit `JOIN` type always stated (`INNER JOIN`, `LEFT JOIN`, `FULL OUTER JOIN`) —
  never implicit comma joins
- `EXPLAIN ANALYZE` before deploying any query on tables with > 100k rows

---

## 2. Subqueries {#subqueries}

A subquery (inner query / nested query) is a `SELECT` statement embedded within
another SQL statement. Subqueries execute first; their result feeds the outer query.

### 2.1 Scalar subquery — returns a single value

```sql
-- Employees earning above the company average salary
-- The subquery executes once and returns a single scalar value (AVG)
SELECT
    nombre,
    salario,
    salario - (SELECT AVG(salario) FROM empleados) AS diff_from_avg
FROM empleados
WHERE salario > (SELECT AVG(salario) FROM empleados)
ORDER BY salario DESC;
```

### 2.2 Subquery in FROM (derived table / inline view)

```sql
-- Use when you need to filter or transform an aggregation
-- The inner query produces a derived table; the outer query filters it
SELECT
    categoria_id,
    nombre,
    ventas
FROM (
    SELECT
        categoria_id,
        nombre,
        ventas,
        ROW_NUMBER() OVER (
            PARTITION BY categoria_id
            ORDER BY ventas DESC
        ) AS rn
    FROM productos
) ranked_products
WHERE rn <= 3;
```

### 2.3 Correlated subquery — references the outer query

The subquery is re-evaluated for each row of the outer query. Powerful but can be
slow at scale — validate with `EXPLAIN ANALYZE` and consider a window function or
JOIN as an alternative.

```sql
-- For each department, retrieve the employee with the highest salary
-- e2.departamento = e1.departamento creates the correlation
SELECT
    e1.nombre,
    e1.departamento,
    e1.salario
FROM empleados e1
WHERE e1.salario = (
    SELECT MAX(e2.salario)
    FROM empleados e2
    WHERE e2.departamento = e1.departamento
);
```

### 2.4 EXISTS vs. IN — performance consideration

```sql
-- EXISTS stops at the first match (semi-join): efficient for large outer tables
SELECT nombre
FROM clientes c
WHERE EXISTS (
    SELECT 1
    FROM pedidos p
    WHERE p.cliente_id = c.id
);

-- NOT EXISTS: efficient anti-join (finds customers with no orders)
SELECT nombre
FROM clientes c
WHERE NOT EXISTS (
    SELECT 1
    FROM pedidos p
    WHERE p.cliente_id = c.id
);

-- IN is equivalent to EXISTS when the subquery result set is small
-- Avoid IN with large subquery result sets — it builds the full set in memory
SELECT nombre
FROM clientes
WHERE id IN (SELECT cliente_id FROM pedidos);
```

> **Performance rule** (Winand, 2012): `EXISTS` is a semi-join — the database stops
> scanning as soon as one match is found. `IN` with a subquery materializes the full
> result set. For large tables, `EXISTS` and `LEFT JOIN / IS NULL` (anti-join) are
> consistently faster than `NOT IN`.

---

## 3. Common Table Expressions (CTEs) {#cte}

CTEs (`WITH` clause) define named result sets that are referenced within the same
query. They make complex multi-step transformations readable and maintainable by
separating logic into named layers — like variable declarations for SQL.

> **Rule**: whenever a query requires more than two logical steps, use CTEs.
> Nested subqueries beyond two levels are a maintenance and debugging liability.

### 3.1 Standard multi-step CTE

```sql
-- Step 1: monthly sales totals
-- Step 2: rank months by total
-- Step 3: return the top 3
WITH ventas_por_mes AS (
    SELECT
        DATE_TRUNC('month', fecha)  AS mes,
        SUM(total)                  AS total_ventas
    FROM ventas
    GROUP BY DATE_TRUNC('month', fecha)
),
ranking_ventas AS (
    SELECT
        mes,
        total_ventas,
        RANK() OVER (ORDER BY total_ventas DESC) AS rnk
    FROM ventas_por_mes
)
SELECT
    mes,
    total_ventas,
    rnk
FROM ranking_ventas
WHERE rnk <= 3
ORDER BY rnk;
```

### 3.2 Recursive CTE — hierarchies and tree structures

A recursive CTE references itself and is used for organizational charts, bill-of-materials,
category trees, network graph traversal, and any hierarchical structure.

```sql
-- Traverse an organizational hierarchy from a given employee upward
-- Base case: the starting employee (id = 42)
-- Recursive case: walk up via jefe_id until no parent exists
WITH RECURSIVE org_hierarchy AS (
    -- Base case: anchor member
    SELECT
        id,
        nombre,
        jefe_id,
        1                   AS nivel,
        nombre::TEXT        AS path
    FROM empleados
    WHERE id = 42

    UNION ALL

    -- Recursive member: join parent to current level
    SELECT
        e.id,
        e.nombre,
        e.jefe_id,
        oh.nivel + 1,
        oh.path || ' → ' || e.nombre
    FROM empleados e
    INNER JOIN org_hierarchy oh ON e.jefe_id = oh.id
)
SELECT id, nombre, nivel, path
FROM org_hierarchy
ORDER BY nivel;
```

> **PostgreSQL docs note**: always include a termination condition in the recursive
> member to prevent infinite loops. The `UNION ALL` / `UNION` controls deduplication.
> Use `UNION` (not `ALL`) if cycles in the data are possible.

---

## 4. Window Functions {#window}

Window functions perform calculations across a defined window of rows related to the
current row, without collapsing the result into a single grouped row. The result set
retains one row per input row — this is the key difference from `GROUP BY`.

> **Reference**: PostgreSQL documentation, Section 3.5 "Window Functions"
> (postgresql.org/docs/current/tutorial-window.html).

### Anatomy of a window function

```
function_name(args) OVER (
    [PARTITION BY partition_expression]
    [ORDER BY sort_expression [ASC | DESC]]
    [ROWS | RANGE BETWEEN frame_start AND frame_end]
)
```

- `PARTITION BY`: divides rows into groups (like `GROUP BY` but without collapsing)
- `ORDER BY`: defines order within each partition for ranked and cumulative functions
- Frame clause: `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` is the standard
  cumulative frame

### 4.1 Ranking functions

```sql
SELECT
    nombre,
    departamento,
    salario,
    -- ROW_NUMBER: unique sequential rank (no ties)
    ROW_NUMBER() OVER (
        PARTITION BY departamento
        ORDER BY salario DESC
    )                                           AS row_num,
    -- RANK: tied rows receive the same rank; next rank is skipped (1,1,3)
    RANK() OVER (
        PARTITION BY departamento
        ORDER BY salario DESC
    )                                           AS rnk,
    -- DENSE_RANK: tied rows receive the same rank; no rank is skipped (1,1,2)
    DENSE_RANK() OVER (
        PARTITION BY departamento
        ORDER BY salario DESC
    )                                           AS dense_rnk,
    -- NTILE(4): divides rows into 4 equal buckets (quartiles)
    NTILE(4) OVER (
        ORDER BY salario DESC
    )                                           AS salary_quartile
FROM empleados
ORDER BY departamento, salario DESC;
```

### 4.2 Aggregate window functions

```sql
SELECT
    nombre,
    departamento,
    salario,
    -- Total salary for the department (partition-level sum)
    SUM(salario) OVER (PARTITION BY departamento)       AS total_dept_salary,
    -- Department average
    AVG(salario) OVER (PARTITION BY departamento)       AS avg_dept_salary,
    -- Salary as % of department total
    ROUND(
        100.0 * salario / SUM(salario) OVER (PARTITION BY departamento),
        2
    )                                                   AS pct_of_dept,
    -- Running total across entire company ordered by hire_date
    SUM(salario) OVER (ORDER BY hire_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
FROM empleados
ORDER BY departamento, salario DESC;
```

### 4.3 Lag, Lead, and offset functions

```sql
SELECT
    fecha,
    total_ventas,
    -- Prior period value
    LAG(total_ventas, 1)  OVER (ORDER BY fecha)         AS prev_month,
    -- Next period value
    LEAD(total_ventas, 1) OVER (ORDER BY fecha)         AS next_month,
    -- Month-over-month absolute change
    total_ventas - LAG(total_ventas, 1) OVER (ORDER BY fecha) AS mom_change,
    -- Month-over-month % change
    ROUND(
        100.0 * (total_ventas - LAG(total_ventas, 1) OVER (ORDER BY fecha))
        / NULLIF(LAG(total_ventas, 1) OVER (ORDER BY fecha), 0),
        2
    )                                                   AS mom_pct_change
FROM ventas_mensuales
ORDER BY fecha;
```

### 4.4 Moving average (rolling window)

```sql
-- 3-month rolling average — the standard smoothing technique for time series
SELECT
    fecha,
    total_ventas,
    ROUND(
        AVG(total_ventas) OVER (
            ORDER BY fecha
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS rolling_avg_3m
FROM ventas_mensuales
ORDER BY fecha;
```

---

## 5. Advanced JOINs {#joins}

> **Reference**: Date, C. J. (2011). _SQL and Relational Theory_ (2nd ed.). O'Reilly.

### JOIN type decision guide

| JOIN type         | Rows returned                                          | When to use                                              |
| ----------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| `INNER JOIN`      | Only matching rows from both tables                    | When only complete matches are needed                    |
| `LEFT JOIN`       | All rows from left + matching right (NULL if no match) | Preserve all left-table rows; detect unmatched records   |
| `RIGHT JOIN`      | All rows from right + matching left                    | Equivalent to LEFT JOIN with tables swapped              |
| `FULL OUTER JOIN` | All rows from both tables (NULL where no match)        | Reconciliation; detect records present in one table only |
| `CROSS JOIN`      | Cartesian product — every left × every right row       | Date dimension generation; combination tables            |
| `SELF JOIN`       | A table joined to itself                               | Hierarchies; comparing rows within the same table        |

```sql
-- LEFT JOIN: all employees, with department name if mapped
SELECT
    e.nombre,
    e.salario,
    d.nombre    AS departamento
FROM empleados e
LEFT JOIN departamentos d ON e.dept_id = d.id;

-- Anti-join pattern: employees with NO department mapping
-- Equivalent to NOT EXISTS; often more readable
SELECT e.nombre
FROM empleados e
LEFT JOIN departamentos d ON e.dept_id = d.id
WHERE d.id IS NULL;

-- FULL OUTER JOIN: reconcile two tables; find unmatched records in either
SELECT
    e.nombre    AS empleado,
    d.nombre    AS departamento
FROM empleados e
FULL OUTER JOIN departamentos d ON e.dept_id = d.id
WHERE e.id IS NULL OR d.id IS NULL;   -- Only unmatched records

-- SELF JOIN: employee with their manager's name
SELECT
    e.nombre    AS empleado,
    j.nombre    AS jefe
FROM empleados e
LEFT JOIN empleados j ON e.jefe_id = j.id;

-- JOIN with multiple conditions
SELECT
    p.nombre,
    c.nombre    AS categoria
FROM productos p
INNER JOIN categorias c
    ON  p.cat_id   = c.id
    AND p.activo   = 1
    AND c.vigente  = 1;
```

---

## 6. Advanced Aggregations — GROUPING SETS, ROLLUP, CUBE {#aggregations}

These extensions to `GROUP BY` generate multiple aggregation levels in a single query
pass, replacing multiple `UNION ALL` queries. They are standard features in
PostgreSQL, SQL Server, Oracle, BigQuery, Snowflake, and Redshift.

> **Use case**: data warehouse fact table aggregations, BI reporting subtotals, and
> multidimensional analysis (OLAP-style). Reference: Kimball & Ross (2013) Chapter 4.

```sql
-- GROUPING SETS: explicitly define each combination to aggregate
-- Produces: (departamento + puesto), (departamento only), (grand total)
SELECT
    departamento,
    puesto,
    COUNT(*)        AS total,
    SUM(salario)    AS masa_salarial
FROM empleados
GROUP BY GROUPING SETS (
    (departamento, puesto),   -- most granular
    (departamento),           -- department subtotals
    ()                        -- grand total (empty grouping = all rows)
);

-- ROLLUP: hierarchical subtotals — each level rolls up to the next
-- Produces: (departamento + puesto), (departamento), grand total
SELECT
    departamento,
    puesto,
    SUM(salario)    AS total
FROM empleados
GROUP BY ROLLUP (departamento, puesto);

-- CUBE: all possible combinations of the listed dimensions
-- For (departamento, puesto): produces 4 combinations = 2^n
-- Use for full cross-dimensional analysis (OLAP cube)
SELECT
    departamento,
    puesto,
    COUNT(*)        AS total
FROM empleados
GROUP BY CUBE (departamento, puesto);

-- GROUPING() function: identifies which columns are NULLs from rollup
-- vs. genuine NULL values in the data
SELECT
    CASE WHEN GROUPING(departamento) = 1 THEN 'ALL DEPTS'
         ELSE departamento END          AS departamento,
    CASE WHEN GROUPING(puesto) = 1 THEN 'ALL PUESTOS'
         ELSE puesto END                AS puesto,
    SUM(salario)                        AS total
FROM empleados
GROUP BY ROLLUP (departamento, puesto);
```

---

## 7. Set Operations — UNION, INTERSECT, EXCEPT {#set-ops}

Set operations combine results from two or more `SELECT` statements.

**Rules (ANSI SQL)**:

- Each `SELECT` must return the same number of columns
- Corresponding columns must have compatible data types
- Column names are taken from the first `SELECT`
- `ORDER BY` applies only to the final combined result

```sql
-- UNION: combine and deduplicate (implicit DISTINCT)
SELECT email FROM clientes_2023
UNION
SELECT email FROM clientes_2024;

-- UNION ALL: combine and keep all duplicates (faster — no deduplication step)
SELECT email FROM clientes_2023
UNION ALL
SELECT email FROM clientes_2024;

-- INTERSECT: records present in BOTH queries (set intersection)
SELECT email FROM clientes_2023
INTERSECT
SELECT email FROM clientes_2024;

-- EXCEPT (MINUS in Oracle): records in first query NOT in second (set difference)
-- Use case: churned customers (were in 2023, not in 2024)
SELECT email FROM clientes_2023
EXCEPT
SELECT email FROM clientes_2024;
```

---

## 8. Practical Analytical Patterns {#patterns}

Standard SQL patterns used repeatedly in data analysis and engineering workflows.

### Top N per group

```sql
-- Top 3 best-selling products per category
-- Pattern: ROW_NUMBER() in subquery → filter in outer query
SELECT
    categoria_id,
    nombre,
    ventas
FROM (
    SELECT
        categoria_id,
        nombre,
        ventas,
        ROW_NUMBER() OVER (
            PARTITION BY categoria_id
            ORDER BY ventas DESC
        ) AS rn
    FROM productos
) ranked
WHERE rn <= 3
ORDER BY categoria_id, ventas DESC;
```

### Cumulative sum (running total)

```sql
-- Cumulative monthly sales
SELECT
    fecha,
    total,
    SUM(total) OVER (
        ORDER BY fecha
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS acumulado
FROM ventas
ORDER BY fecha;
```

### Year-over-year comparison

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', fecha)  AS mes,
        SUM(total)                  AS ventas
    FROM ventas
    GROUP BY DATE_TRUNC('month', fecha)
)
SELECT
    mes,
    ventas,
    LAG(ventas, 12) OVER (ORDER BY mes)     AS ventas_prev_year,
    ROUND(
        100.0 * (ventas - LAG(ventas, 12) OVER (ORDER BY mes))
        / NULLIF(LAG(ventas, 12) OVER (ORDER BY mes), 0),
        2
    )                                       AS yoy_pct_change
FROM monthly
ORDER BY mes;
```

### Duplicate detection

```sql
-- Find duplicate emails and how many times each appears
SELECT
    email,
    COUNT(*)    AS occurrences
FROM usuarios
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;

-- Retrieve the full row of duplicates for inspection
SELECT *
FROM usuarios
WHERE email IN (
    SELECT email
    FROM usuarios
    GROUP BY email
    HAVING COUNT(*) > 1
)
ORDER BY email;
```

### Latest record per group (last purchase per customer)

```sql
-- Pattern: ROW_NUMBER() with ORDER BY fecha DESC → filter rn = 1
SELECT *
FROM (
    SELECT
        c.*,
        ROW_NUMBER() OVER (
            PARTITION BY cliente_id
            ORDER BY fecha DESC
        ) AS rn
    FROM compras c
) latest
WHERE rn = 1;
```

### Pivot (cross-tabulation without PIVOT keyword — ANSI compatible)

```sql
-- Monthly sales by region, pivoted to wide format
SELECT
    DATE_TRUNC('month', fecha)          AS mes,
    SUM(CASE WHEN region = 'APAC'  THEN total ELSE 0 END)   AS apac,
    SUM(CASE WHEN region = 'EMEA'  THEN total ELSE 0 END)   AS emea,
    SUM(CASE WHEN region = 'AMER'  THEN total ELSE 0 END)   AS amer,
    SUM(total)                          AS grand_total
FROM ventas
GROUP BY DATE_TRUNC('month', fecha)
ORDER BY mes;
```

### Sessionization (gap-and-island problem)

```sql
-- Assign session IDs to user activity — a gap > 30 minutes starts a new session
-- Classic gap-and-island pattern using LAG + conditional SUM
WITH activity AS (
    SELECT
        user_id,
        event_time,
        LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) AS prev_time
    FROM user_events
),
session_starts AS (
    SELECT
        user_id,
        event_time,
        CASE
            WHEN prev_time IS NULL
              OR event_time - prev_time > INTERVAL '30 minutes'
            THEN 1
            ELSE 0
        END AS is_new_session
    FROM activity
)
SELECT
    user_id,
    event_time,
    SUM(is_new_session) OVER (
        PARTITION BY user_id
        ORDER BY event_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS session_id
FROM session_starts
ORDER BY user_id, event_time;
```

### FILTER clause — conditional aggregation (ANSI SQL:2003)

```sql
-- Count and sum with inline conditions — more readable than CASE WHEN in aggregates
SELECT
    departamento,
    COUNT(*)                            AS total_employees,
    COUNT(*) FILTER (WHERE salario > 7000)  AS high_earners,
    AVG(salario) FILTER (WHERE activo = 1)  AS avg_active_salary
FROM empleados
GROUP BY departamento;
```

---

## 9. Query Optimization & Execution Plans {#optimization}

> **Primary reference**: Winand, M. (2012). _SQL Performance Explained_.
> Use The Index, Luke (use-the-index-luke.com). — The most accessible expert
> reference on SQL indexing and execution plan analysis.

### Always run EXPLAIN ANALYZE before deploying

```sql
-- PostgreSQL: EXPLAIN ANALYZE shows both planned and actual execution
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT e.nombre, d.nombre AS depto
FROM empleados e
INNER JOIN departamentos d ON e.dept_id = d.id
WHERE e.salario > 6000;
```

Key terms in the output:

| Term               | Meaning                                                                            |
| ------------------ | ---------------------------------------------------------------------------------- |
| `Seq Scan`         | Full table scan — no index used. Acceptable for small tables; problematic at scale |
| `Index Scan`       | Index used to locate rows. Fast for selective predicates                           |
| `Index Only Scan`  | All needed columns are in the index — zero heap access. Fastest                    |
| `Hash Join`        | Efficient for large unsorted tables — builds a hash table on the smaller input     |
| `Nested Loop Join` | Fast when the inner loop uses an index; catastrophic without one                   |
| `Merge Join`       | Efficient when both inputs are pre-sorted on the join key                          |
| `cost=X..Y`        | Estimated startup cost .. total cost in arbitrary units                            |
| `actual time=X..Y` | Actual execution time in milliseconds                                              |
| `rows=N`           | Actual row count — compare to `rows=N` estimate to detect stale statistics         |

### Indexing rules

```sql
-- Index foreign key columns — prevents sequential scans on JOIN
CREATE INDEX idx_empleados_dept_id ON empleados (dept_id);

-- Composite index: column order matters — most selective first
-- This index serves: WHERE departamento = X AND salario > Y
CREATE INDEX idx_emp_dept_salary ON empleados (departamento, salario DESC);

-- Partial index: only index rows meeting a condition — smaller, faster
CREATE INDEX idx_active_employees ON empleados (dept_id)
WHERE activo = 1;

-- Covering index: include all columns a query needs — enables Index Only Scan
CREATE INDEX idx_emp_covering ON empleados (dept_id)
INCLUDE (nombre, salario);
```

**Winand (2012) three rules for index design**:

1. The WHERE clause determines which columns need indexing.
2. The ORDER BY clause benefits from index-sorted columns.
3. The SELECT clause benefits from covering indexes (INCLUDE columns).

### Query writing patterns that block index use

```sql
-- BAD: function on indexed column prevents index use
WHERE UPPER(email) = 'USER@EXAMPLE.COM'

-- GOOD: function-based index or normalize at write time
CREATE INDEX idx_email_upper ON usuarios (UPPER(email));
WHERE UPPER(email) = 'USER@EXAMPLE.COM'

-- BAD: leading wildcard prevents B-tree index use
WHERE nombre LIKE '%ana%'

-- GOOD: leading-match wildcard can use index; use full-text search for contains
WHERE nombre LIKE 'ana%'

-- BAD: implicit type cast blocks index
WHERE id = '42'     -- id is INTEGER; '42' is VARCHAR → implicit cast applied

-- GOOD: explicit match on column type
WHERE id = 42
```

### Query anti-patterns in data engineering

```sql
-- NEVER: SELECT * in production pipelines — schema changes break downstream
SELECT * FROM ventas;

-- ALWAYS: explicit columns
SELECT fecha, producto_id, region, total FROM ventas;

-- NEVER: correlated subquery in SELECT list for large tables — N executions
SELECT
    nombre,
    (SELECT COUNT(*) FROM pedidos WHERE cliente_id = c.id) AS total_pedidos
FROM clientes c;  -- Executes once per row in clientes

-- BETTER: LEFT JOIN with aggregation — single pass
SELECT
    c.nombre,
    COUNT(p.id)     AS total_pedidos
FROM clientes c
LEFT JOIN pedidos p ON p.cliente_id = c.id
GROUP BY c.id, c.nombre;

-- NEVER: OR on separate indexed columns — prevents index use
WHERE departamento = 'IT' OR salario > 8000

-- BETTER: UNION ALL (each branch can use its own index)
SELECT * FROM empleados WHERE departamento = 'IT'
UNION ALL
SELECT * FROM empleados WHERE salario > 8000 AND departamento != 'IT';
```

### Update statistics

```sql
-- PostgreSQL: update planner statistics after bulk loads
ANALYZE empleados;

-- Full vacuum + analyze after heavy DML (reclaims space, updates statistics)
VACUUM ANALYZE ventas;
```

---

## 10. SQL for Data Science — Analytical Workflows {#ds-patterns}

Patterns specific to data science workflows: feature engineering in SQL,
cohort analysis, and funnel analysis.

### Feature engineering in SQL

```sql
-- Build a training feature set directly in SQL before ingestion into a model
-- Computes recency, frequency, monetary value (RFM) per customer
WITH rfm AS (
    SELECT
        cliente_id,
        -- Recency: days since last purchase
        DATE_PART('day',
            NOW() - MAX(fecha))                     AS recency_days,
        -- Frequency: total purchase count
        COUNT(*)                                    AS frequency,
        -- Monetary: total spend
        SUM(total)                                  AS monetary,
        -- Average order value
        ROUND(AVG(total), 2)                        AS avg_order_value,
        -- Std dev of order value (feature for model variance)
        ROUND(STDDEV(total), 2)                     AS stddev_order_value
    FROM compras
    GROUP BY cliente_id
)
SELECT
    cliente_id,
    recency_days,
    frequency,
    monetary,
    avg_order_value,
    COALESCE(stddev_order_value, 0)                 AS stddev_order_value,
    -- Percentile rank features (0–1 normalized)
    PERCENT_RANK() OVER (ORDER BY recency_days ASC)     AS recency_pct,
    PERCENT_RANK() OVER (ORDER BY frequency DESC)       AS frequency_pct,
    PERCENT_RANK() OVER (ORDER BY monetary DESC)        AS monetary_pct
FROM rfm
ORDER BY monetary DESC;
```

### Cohort analysis

```sql
-- Retention cohort: what % of users who joined in month M are still active in M+N
WITH cohorts AS (
    SELECT
        user_id,
        DATE_TRUNC('month', MIN(fecha))     AS cohort_month
    FROM compras
    GROUP BY user_id
),
activity AS (
    SELECT
        c.user_id,
        c.cohort_month,
        DATE_TRUNC('month', p.fecha)        AS activity_month,
        DATE_PART('month',
            AGE(DATE_TRUNC('month', p.fecha),
                c.cohort_month))            AS period_number
    FROM cohorts c
    INNER JOIN compras p ON p.user_id = c.user_id
)
SELECT
    cohort_month,
    period_number,
    COUNT(DISTINCT user_id)                 AS active_users
FROM activity
GROUP BY cohort_month, period_number
ORDER BY cohort_month, period_number;
```

### Funnel analysis

```sql
-- Conversion funnel: users progressing through sequential steps
-- FILTER clause computes each stage in one pass
SELECT
    COUNT(DISTINCT user_id)
        FILTER (WHERE step >= 1)    AS step_1_view,
    COUNT(DISTINCT user_id)
        FILTER (WHERE step >= 2)    AS step_2_add_to_cart,
    COUNT(DISTINCT user_id)
        FILTER (WHERE step >= 3)    AS step_3_checkout,
    COUNT(DISTINCT user_id)
        FILTER (WHERE step >= 4)    AS step_4_purchase,
    ROUND(
        100.0 * COUNT(DISTINCT user_id) FILTER (WHERE step >= 4)
        / NULLIF(COUNT(DISTINCT user_id) FILTER (WHERE step >= 1), 0),
        2
    )                               AS overall_conversion_pct
FROM user_funnel_events;
```

---

## References

- PostgreSQL 18 Documentation. _Chapter 7 — Queries_. https://www.postgresql.org/docs/current/queries.html
- PostgreSQL 18 Documentation. _EXPLAIN_. https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL 18 Documentation. _WITH Queries (Common Table Expressions)_. https://www.postgresql.org/docs/current/queries-with.html
- Microsoft (2024). _SELECT — Transact-SQL: Logical Processing Order_. https://learn.microsoft.com/en-us/sql/t-sql/queries/select-transact-sql
- Winand, M. (2012). _SQL Performance Explained_. Markus Winand. [use-the-index-luke.com]
- Ben-Gan, I. (2016). _T-SQL Fundamentals_ (3rd ed.). Microsoft Press.
- Date, C. J. (2011). _SQL and Relational Theory_ (2nd ed.). O'Reilly.
- Kimball, R., & Ross, M. (2013). _The Data Warehouse Toolkit_ (3rd ed.). Wiley.
- Molinaro, A. (2009). _SQL Cookbook_. O'Reilly.
- Beaulieu, A. (2020). _Learning SQL_ (3rd ed.). O'Reilly.
- Garcia-Molina, H., Ullman, J. D., & Widom, J. (2008). _Database Systems: The Complete Book_ (2nd ed.). Pearson.
- ISO/IEC 9075 — SQL Standard. ANSI SQL:2016.
