# Dashboard Design & Business Data Storytelling

> This reference covers dashboard design, chart selection for business intelligence,
> and data storytelling in Power BI and Tableau. For statistical visualization
> in analytical/EDA contexts (box plots, violin plots, heatmaps, distribution plots),
> see `eda_templates.md`.

## Table of Contents

1. [Foundational Principles — Perceptual Hierarchy](#perception)
2. [Audience and Purpose Framework](#audience)
3. [Chart Selection for Business Intelligence](#chart-selection)
4. [Dashboard Layout Principles](#layout)
5. [Color Strategy for Business Dashboards](#color)
6. [Data Storytelling Framework](#storytelling)
7. [Power BI — Design Guidelines](#powerbi)
8. [Tableau — Design Guidelines](#tableau)
9. [Anti-patterns Quick Reference](#antipatterns)
10. [References](#references)

---

## 1. Foundational Principles — Perceptual Hierarchy {#perception}

> **Primary reference**: Cleveland, W. S., & McGill, R. (1985). Graphical perception and
> graphical methods for analyzing scientific data. *Science*, 229(4716), 828–833.

The human visual system does not perceive all chart encodings with equal accuracy.
Cleveland and McGill (1985) established the following hierarchy from most accurate
(easiest to decode) to least accurate (most error-prone):

| Rank | Encoding | Typical Chart Type |
|---|---|---|
| 1 (most accurate) | Position along a common scale | Bar chart, scatter plot |
| 2 | Position along a non-aligned scale | Multiple bar charts, small multiples |
| 3 | Length | Bar chart (unstacked) |
| 4 | Angle and slope | Pie chart, line chart |
| 5 | Area | Bubble chart, treemap |
| 6 | Volume, density, color saturation | 3D charts, choropleth maps |
| 7 (least accurate) | Color hue | Categorical color encoding |

**Practical implication**: A bar chart (rank 1–3) is always more perceptually accurate
than a pie chart (rank 4) or bubble chart (rank 5) for comparing magnitudes. Default
to the most accurate encoding that communicates the intended message.

**Jacques Bertin's efficiency principle** (*Sémiologie Graphique*, 1967): An efficient
chart requires the shortest period of perception to obtain a correct and complete answer
to a given question. Every design decision should reduce perception time, not add to it.

---

## 2. Audience and Purpose Framework {#audience}

Before selecting any visual, answer these questions explicitly:

1. Who is the audience? (executive leadership / operational managers / analysts / public)
2. What decisions will they make using this dashboard?
3. What is the single most important thing they must see immediately?
4. What level of statistical literacy can be assumed?
5. Where and how will the dashboard be viewed? (large monitor / tablet / embedded report)

**Audience-driven design rules:**

| Audience | Design approach | Chart complexity |
|---|---|---|
| Executive / C-suite | KPIs dominant, one-screen, minimal drill-down | Low — bars, lines, KPI cards |
| Operational managers | Comparison to plan/prior period, trend lines, variances | Medium — bars with variance, waterfall |
| Analysts / data scientists | Statistical distributions, drill-through, filters | High — scatter, histogram, heatmap |
| Public / general audience | Annotated, context-rich, limited color | Low-medium — bar, line, map |

> **Reference**: Few, S. (2013). *Information Dashboard Design* (2nd ed.). Analytics Press.
> Alberto Cairo (2016). *The Truthful Art*. New Riders Press.

---

## 3. Chart Selection for Business Intelligence {#chart-selection}

### Orientation rule (applies to all chart types)

- **Time on the horizontal axis**: use charts with a left-to-right horizontal axis
  (column chart, line chart, area chart) when the dimension is temporal
  (days, months, quarters, years).
- **Categories on the vertical axis**: use charts with a top-to-bottom vertical axis
  (horizontal bar chart) when the dimension is categorical
  (products, business units, regions, cost types).

This is not a stylistic preference — it is a readability rule. Long category labels
displayed on a horizontal axis will render tilted and become unreadable. Switch to
a horizontal bar chart.

### Task-based chart selection

Determine the analytical task before selecting the chart. Ask: what does the reader
need to know?

| Analytical Task | Recommended Chart | Avoid | Notes |
|---|---|---|---|
| Compare magnitudes across categories | Horizontal bar chart, ordered by value | Pie chart, 3D chart | Sort descending unless natural order exists (e.g., age groups) |
| Show trend over time (dense data) | Line chart | Bar chart | Lines show continuity; bars fragment it |
| Show trend over time (few periods, < 8) | Column chart | Line chart | Columns allow discrete period comparison |
| Show part-to-whole composition | Donut chart (< 6 categories) / Treemap (hierarchical) | 3D pie, stacked bar | Limit pie/donut to < 6 clearly distinct slices |
| Show variance to plan / prior year | Waterfall chart / integrated variance bar | Clustered bar | Waterfall explains the "why" behind a net change |
| Show contribution to a total | Waterfall chart | Stacked bar | Waterfall preserves subtotals and hierarchy |
| Show correlation between two metrics | Scatter plot + trend line + r² annotation | Dual-axis line | Always annotate with correlation statistic |
| Show distribution of a measure | Histogram / Box plot | Bar chart | Use for quality control, outlier detection, normality check |
| Show progress against a goal | Gauge / Bullet chart | Donut used as gauge | Bullet chart (Few, 2006) is more space-efficient than gauge |
| Show geographic data | Map (filled / bubble) | Bar chart for geographic comparison | Use bubble maps for magnitude; filled maps for rate/density |
| Compare many series simultaneously | Small multiples (trellis) | Single overcrowded chart | All panels must share the same scale |

### Chart type descriptions

**Bar / Column chart**: The default choice for categorical comparison. Effective because
it uses position along a common scale — the most accurate human encoding. Always start
the Y-axis at zero. Order bars by value unless a natural order exists.

**Line chart**: The correct choice for continuous temporal data. The eye follows the
line and perceives the angle (rate of change) intuitively. Use for dense time series
(> 8 periods). Do not use more than 4–5 lines simultaneously — beyond that, use small
multiples instead.

**Waterfall chart**: The correct chart for explaining how a total is built from
contributing factors (e.g., revenue bridge from prior year to actuals, P&L income
statement). Shows both the direction (positive/negative) and magnitude of each
component.

**Bullet chart** (Few, 2006): A compact replacement for gauges, meters, and
thermometers. Shows a single measure against a target and contextual range in
minimal space.

**Scatter plot**: Reveals correlations, clusters, and outliers between two numeric
variables. Always include a trend line and annotate with Pearson r or R². Note that
scatter plots are unfamiliar to non-technical audiences — add clear axis labels and
a one-sentence annotation explaining what the trend means.

**Treemap**: Best for showing hierarchical part-to-whole relationships with many
categories (where pie/donut becomes unreadable). Area encoding is less accurate than
bar length (Cleveland & McGill rank 5 vs. rank 1), so use only when hierarchy matters
more than precise comparison.

**Small multiples**: Render the same chart type across multiple categories or segments,
all to the same scale. Enables comparison across panels without overloading a single
chart. The scale must be identical across all panels — panels at different scales
produce false comparisons.

---

## 4. Dashboard Layout Principles {#layout}

### The 3-30-300 Rule

Design every dashboard for three levels of reading attention:

| Level | Time budget | Content | Examples |
|---|---|---|---|
| 3 seconds | At-a-glance | High-level KPIs, traffic light indicators | Revenue vs. target, MoM growth |
| 30 seconds | Engaged scan | Primary charts, trends, key comparisons | Time series, variance analysis |
| 300 seconds | Deep analysis | Drill-through, detailed tables, filters | Transaction-level data, segmentation |

Design implication: KPI cards and headline metrics belong in the top-left of the
dashboard. Detail tables and drill-through pages belong at the bottom or on secondary
pages.

### Reading pattern and visual hierarchy

Most audiences read top-to-bottom, left-to-right (F-pattern or Z-pattern for Western
languages). The eye is drawn to the top-left corner first.

Rules:
- Place the most important metric or insight in the top-left.
- Move from summary (top) to detail (bottom).
- Move from context (left) to specifics (right).
- Place interactive filters and slicers in a consistent, predictable location —
  top or left panel — across all pages of the report.

### Density and cognitive load

> **Reference**: Miller, G. A. (1956). The magical number seven, plus or minus two.
> *Psychological Review*, 63(2), 81–97. — Cognitive load theory applied to dashboard design.

- Limit visible content to 5–8 visuals per page. Beyond 8, cognitive load degrades
  reading speed and decision quality.
- Each visual should answer exactly one question. If a single chart is trying to answer
  two questions, split it into two charts or reconsider the question.
- One screen, no scroll: a dashboard is an overview. If critical information requires
  scrolling to find, it belongs on a drill-through page, not the summary dashboard.

### White space and visual separation

White space is not wasted space — it reduces cognitive load and visually groups related
content. Apply these rules:

- Leave deliberate margins between all visual elements.
- Use white space (or thin borders) to group related visuals into logical sections.
- Do not fill every pixel. A dashboard with breathing room reads faster than a dense one.
- Align visuals on a grid. Misaligned elements signal unprofessionalism and create
  visual noise.

---

## 5. Color Strategy for Business Dashboards {#color}

> **Reference**: Ware, C. (2012). *Information Visualization: Perception for Design*
> (3rd ed.). Morgan Kaufmann. — The authoritative scientific treatment of color in visualization.

### Functional color principles

Color in business dashboards is a communication tool, not decoration. Every color
must carry explicit meaning.

**Rules:**

1. **One dominant palette color, one accent color.** Using 5+ colors without semantic
   meaning creates visual noise. Keep the palette constrained.

2. **Reserve red/green for performance context only.** Red = below target / negative
   variance. Green = above target / positive variance. Never use red/green for neutral
   categorical encoding — it triggers false performance interpretation.

3. **Maintain color consistency across the entire report.** If "Product A" is blue in
   chart 1, it must be blue in chart 2, chart 3, and every filter. Inconsistent color
   assignment for the same dimension forces the viewer to re-read the legend on every chart.

4. **Use divergent color scales for variance and correlation data.** A sequential
   single-color scale cannot distinguish positive from negative. Use blue–white–red
   (or equivalent) centered at zero. (See `eda_templates.md` for heatmap-specific guidance.)

5. **Account for color blindness.** Approximately 8% of men have red-green color
   deficiency (deuteranopia/protanopia). Never rely on red vs. green as the sole
   differentiator. Add a secondary cue (icon, label, pattern) alongside color.

6. **Use color saturation to encode intensity.** Within a single color family, lighter
   = lower value, darker = higher value. This is more accurate for the viewer than
   switching hue.

### Semantic color conventions

| Color | Conventional meaning in BI dashboards |
|---|---|
| Green | Positive performance, above target, favorable variance |
| Red | Negative performance, below target, unfavorable variance |
| Grey | Neutral, prior period, background, secondary context |
| Blue | Actuals, primary metric, current period |
| Orange / Yellow | Warning, near threshold, attention required |
| Dark blue / Navy | Plan, budget, forecast |

---

## 6. Data Storytelling Framework {#storytelling}

A dashboard is not a spreadsheet. It is a narrative. Every design decision should
serve the story — the insight the data is trying to communicate.

### The McCandless hierarchy of information visualization

> **Reference**: McCandless, D. (2012). *Information is Beautiful* (2nd ed.). Collins.

Effective data visualizations combine four properties:

1. **Information**: the data itself is accurate and complete
2. **Function**: the chart type matches the analytical task
3. **Visual form**: the encoding is perceptually appropriate
4. **Story/meaning**: the chart communicates an insight, not just numbers

A chart that has information and function but no story is a data dump.
A chart that has story but poor function misleads.

### Practical storytelling rules

- **Lead with the insight, not the data.** Title the chart with the conclusion, not
  the variable name. "Revenue grew 14% YoY driven by APAC" is a better title than
  "Revenue by Region by Year."
- **Annotate the decisive moment.** If a line chart shows a spike or drop, annotate
  the cause directly on the chart. Do not make the viewer search for it.
- **Compare to something.** Raw numbers have no meaning without context. Compare
  actual to plan, actual to prior year, or actual to benchmark. Variance is the story.
- **Show the exception, not the average.** Executives act on outliers and variances,
  not averages. Design dashboards to surface what is unusual, not what is normal.

---

## 7. Power BI — Design Guidelines {#powerbi}

> **Primary reference**: Microsoft Learn (2024). *Dashboard design best practices in
> Power BI*. https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards-design-tips

### Core structural rules

- **One dashboard = one screen.** The Power BI dashboard is an overview layer.
  Details belong in reports (PBIX pages), not on the dashboard canvas.
- **Use drill-through pages** for detail-level analysis. Configure drill-through on
  dimension values so users move from summary to detail without leaving the report.
- **Mobile layout**: Design a separate mobile layout for dashboards shared on phones
  or tablets. Power BI's default canvas is optimized for desktop — a mobile layout
  requires explicit configuration.
- **Performance Analyzer**: Always run Performance Analyzer (View tab) before
  publishing. Identify visuals with query durations > 3 seconds and optimize the
  underlying DAX or reduce visual complexity.

### Chart-specific Power BI notes

- **Line charts**: Power BI auto-scales the Y-axis, which can make small variances
  appear dramatic. Always check "Start Y-axis at 0" for column and bar charts.
  For line charts, consider whether the auto-scaled range accurately represents
  business significance.
- **Matrix visuals vs. tables**: Use Matrix for cross-tabulation with row/column
  subtotals. Use Table for flat lists. Do not use either as the primary visual on a
  summary dashboard — they communicate no story.
- **KPI card visual**: The correct choice for headline metrics. Pair each KPI card
  with a target value and a trend indicator (sparkline or variance percentage).
- **Gauge charts**: Acceptable for single-metric progress against a fixed goal.
  For multiple metrics, use bullet charts (available via custom visual marketplace)
  to save space.
- **Slicers**: Group all slicers in one visual region (top or left panel) with a
  visible border. Do not scatter slicers across the canvas. Label each slicer clearly.

### DAX and data model performance

- Avoid calculated columns for aggregations that can be expressed as measures.
  Measures execute at query time and scale with filters; calculated columns are
  stored in memory and inflate the data model.
- Use `CALCULATE` and context transitions correctly — improper filter context is
  the most common source of incorrect KPI values in Power BI reports.
- Disable auto date/time unless specifically needed — it generates hidden date tables
  for every date column and inflates model size.

---

## 8. Tableau — Design Guidelines {#tableau}

> **Primary reference**: Tableau (2024). *Visual Best Practices*.
> https://help.tableau.com/current/blueprint/en-us/bp_visual_best_practices.htm

### Core structural rules

- **Dashboard actions**: Use filter actions, highlight actions, and URL actions to
  create interactivity. Filter actions that pass context from a summary chart to a
  detail chart replace the need for excessive visible filters.
- **Layout containers**: Use horizontal and vertical layout containers to build
  responsive dashboards. Avoid fixed pixel positioning — it breaks on different
  screen sizes. Use the Tiled layout for structure; Floating only for annotations
  or KPI overlays.
- **Device designer**: Build separate layouts for desktop, tablet, and phone in
  Tableau's Device Designer. Do not assume the desktop layout renders acceptably
  on mobile.

### Chart-specific Tableau notes

- **Dual-axis charts**: Use for displaying two related but differently-scaled metrics
  on the same time axis (e.g., revenue in millions and growth rate in percentage).
  Always label both axes clearly and use distinct mark types for each measure
  (bar + line is the standard pairing).
- **Calculated fields vs. Level of Detail (LOD) expressions**: Use LOD expressions
  (`FIXED`, `INCLUDE`, `EXCLUDE`) when the aggregation level differs from the view
  level. This is Tableau's most powerful and most misused feature — incorrect LOD
  scope produces silent data errors.
- **Extract vs. live connection**: Use an extract for large datasets or external
  databases with high query latency. Use a live connection only when real-time data
  is a hard requirement — extracts refresh on schedule and are significantly faster
  for interactive dashboards.
- **Show/Hide containers**: Use show/hide button containers to create collapsible
  filter panels, reducing visual density without removing functionality.

---

## 9. Anti-patterns Quick Reference {#antipatterns}

The following patterns consistently produce dashboards that mislead, confuse, or
fail to support decisions. Avoid them without exception.

| Anti-pattern | Correct practice | Authority |
|---|---|---|
| Pie chart with > 5 categories | Horizontal bar chart, ordered by value | Cleveland & McGill (1985); Few (2012) |
| 3D charts of any type | Flat 2D equivalent | Tufte (2001); Cairo (2016) |
| Y-axis not starting at zero on bar chart | Always start at zero for bars | Few (2012); Microsoft Learn |
| Line chart with > 4–5 lines | Small multiples | Tufte (1990) *Envisioning Information* |
| Mean reported without distribution context | Mean + variance + histogram or box plot | Cleveland (1993) |
| Scatter plot without trend line and r² | Add OLS line and correlation annotation | Wilke (2019) |
| Inconsistent color for the same dimension | One color per dimension value, enforced globally | Ware (2012) |
| Red/green used for non-performance encoding | Reserve red/green for target comparison only | Ware (2012) |
| Stacked bar for magnitude comparison | Grouped bar chart | Few (2012) |
| Sequential color scale on divergent data | Divergent scale centered at zero | Ware (2012) |
| Dashboard requiring scroll to see key metrics | Restructure to one-screen summary + drill-through | Microsoft Learn |
| > 8 visuals per dashboard page | Max 5–8 visuals; move detail to drill-through pages | Miller (1956); Few (2013) |
| Chart titled with variable name | Title states the insight ("Revenue up 14% YoY") | Cairo (2016) |
| Data without comparison (plan/prior year) | Always provide context — variance is the story | Few (2013) |

---

## 10. References {#references}

**Books — foundational:**
- Few, S. (2006). *Show Me the Numbers: Designing Tables and Graphs to Enlighten* (2nd ed.). Analytics Press.
- Few, S. (2013). *Information Dashboard Design* (2nd ed.). Analytics Press.
- Few, S. (2009). *Now You See It: Simple Visualization Techniques for Quantitative Analysis*. Analytics Press.
- Tufte, E. R. (2001). *The Visual Display of Quantitative Information* (2nd ed.). Graphics Press.
- Tufte, E. R. (1990). *Envisioning Information*. Graphics Press.
- Cairo, A. (2012). *The Functional Art: An Introduction to Information Graphics and Visualization*. New Riders Press.
- Cairo, A. (2016). *The Truthful Art: Data, Charts, and Maps for Communication*. New Riders Press.
- Ware, C. (2012). *Information Visualization: Perception for Design* (3rd ed.). Morgan Kaufmann.
- Wilke, C. O. (2019). *Fundamentals of Data Visualization*. O'Reilly Media.

**Seminal academic papers:**
- Cleveland, W. S., & McGill, R. (1985). Graphical perception and graphical methods for analyzing scientific data. *Science*, 229(4716), 828–833.
- Bertin, J. (1967). *Sémiologie Graphique*. Gauthier-Villars. (English: *Semiology of Graphics*, 1983, University of Wisconsin Press.)
- Miller, G. A. (1956). The magical number seven, plus or minus two. *Psychological Review*, 63(2), 81–97.

**Official documentation:**
- Microsoft Learn (2024). Dashboard design best practices in Power BI. https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards-design-tips
- Tableau (2024). Visual Best Practices. https://help.tableau.com/current/blueprint/en-us/bp_visual_best_practices.htm
- IBM (2024). Chart Selection Guide. https://www.ibm.com/design/language/data-visualization/chart-types/

**Practitioner references:**
- Zebra BI (2024). How to choose the correct chart type for your Power BI report. https://zebrabi.com/guide/how-to-choose-the-correct-chart-for-your-power-bi-report/
- Berkeley Library (2024). Choosing a Chart Type. https://guides.lib.berkeley.edu/data-visualization/type
