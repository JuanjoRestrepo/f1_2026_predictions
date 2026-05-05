# EDA Templates Reference

## Table of Contents

0. [Environment Setup (uv)](#environment)
1. [Visualization Strategy Guide — Plot Selection](#viz-strategy)
2. [Tabular / Flat File EDA](#tabular)
3. [Time Series EDA](#time-series)
4. [Text / NLP EDA](#nlp)
5. [Image Data EDA](#image)
6. [SQL-Based EDA](#sql)

---

## 0. Environment Setup (uv) {#environment}

```bash
uv init eda_project && cd eda_project
uv python pin 3.12
uv venv .venv --python 3.12 && source .venv/bin/activate

# Core EDA stack
uv add pandas polars numpy scipy statsmodels \
       matplotlib seaborn plotly bokeh altair \
       ydata-profiling scikit-learn ipykernel jupyterlab \
       arch                                  # ARCH/GARCH volatility modeling

# Dev tools
uv add --dev ruff mypy pytest
uv sync
```

---

## 1. Visualization Strategy Guide — Plot Selection {#viz-strategy}

Selecting the wrong plot type does not just affect aesthetics — it can conceal or
misrepresent the statistical structure of the data entirely. Apply the following
decision framework before producing any distribution visualization.

### Distribution Visualization: Box Plot vs. Violin Plot

Both plots describe the distribution of a continuous variable. They answer different
questions and are not interchangeable.

#### Box Plot (Tukey, 1977)

The box plot is a non-parametric summary based on order statistics. It makes no
assumption about the underlying distribution shape.

Components:

- Median (Q2): the center line inside the box
- Interquartile range (IQR): the box spans Q1 to Q3, containing the middle 50% of data
- Whiskers: extend to Q1 - 1.5*IQR and Q3 + 1.5*IQR (Tukey fences)
- Outliers: individual points beyond the whisker fences

Strengths:

- Robust outlier detection using a principled, formula-based rule
- Fast, unambiguous comparison of medians and spread across many groups
- Compact — scales cleanly to 10, 20, or 50 side-by-side groups

Limitations:

- Completely hides distributional shape — a bimodal distribution and a uniform
  distribution with identical quartiles are indistinguishable in a box plot
- Misrepresents sample size — a box with n=15 looks identical to one with n=15,000

#### Violin Plot (Hintze & Nelson, 1998)

The violin plot wraps a Kernel Density Estimate (KDE) around each group, mirrored
on both sides. Width at any point on the y-axis represents the density of observations
at that value.

Strengths:

- Reveals full distributional shape: skewness, multimodality (multiple peaks), heavy tails
- The KDE is a mathematically smoothed representation of the histogram — it exposes
  structure that quartile summaries suppress
- Effective for detecting bimodal distributions, which are invisible in box plots

Limitations:

- KDE requires bandwidth selection — a poorly chosen bandwidth over-smooths or
  under-smooths the distribution, potentially creating phantom peaks or hiding real ones
- Misleading at small sample sizes (n < 30) — the KDE implies smooth density where
  the data does not support it
- Less effective for comparing many groups simultaneously due to width

#### Hybrid Approach — Recommended Default for EDA

The best practice in professional EDA is the hybrid: render the violin plot for
distributional shape, and overlay a thin box plot inside it for the summary statistics.
This eliminates the trade-off entirely.

> Wilke (2019) in _Fundamentals of Data Visualization_ (O'Reilly) explicitly recommends
> the hybrid as the preferred approach for continuous distributions, noting that the
> combination conveys more information than either plot alone without adding visual clutter.

#### Decision Table

| Objective                                             | Recommended Plot                             |
| ----------------------------------------------------- | -------------------------------------------- |
| Detect outliers, compare medians across many groups   | Box plot                                     |
| Understand distributional shape, detect multimodality | Violin plot                                  |
| Complete EDA — shape + summary statistics             | Hybrid (violin + inner box plot)             |
| Small sample size (n < 30)                            | Box plot only — KDE is unreliable at small n |
| Publication with space constraints                    | Box plot                                     |
| Interactive EDA for data exploration                  | Violin plot or hybrid                        |

#### Implementation

```python
from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# --- Constants ---
FIGURE_SIZE_SINGLE: tuple[int, int] = (10, 6)
FIGURE_SIZE_COMPARISON: tuple[int, int] = (14, 6)
SMALL_N_THRESHOLD: int = 30  # Below this, violin plots are unreliable


def plot_box(
    df: pd.DataFrame,
    value_col: str,
    group_col: str | None = None,
    title: str | None = None,
) -> None:
    """
    Box plot for outlier detection and median comparison.
    Preferred when comparing many groups or when n < 30 per group.

    Args:
        value_col: Continuous variable to visualize.
        group_col: Optional categorical grouping variable.
        title: Plot title.
    """
    plt.figure(figsize=FIGURE_SIZE_SINGLE)
    sns.boxplot(data=df, x=group_col, y=value_col, palette="Set2")
    plt.title(title or f"Box Plot: {value_col}")
    plt.tight_layout()
    plt.show()


def plot_violin(
    df: pd.DataFrame,
    value_col: str,
    group_col: str | None = None,
    title: str | None = None,
) -> None:
    """
    Violin plot for distributional shape analysis.
    Use when n >= 30 per group and shape (skew, bimodality) matters.

    Args:
        value_col: Continuous variable to visualize.
        group_col: Optional categorical grouping variable.
        title: Plot title.
    """
    if group_col:
        min_n = df.groupby(group_col)[value_col].count().min()
        if min_n < SMALL_N_THRESHOLD:
            logger.warning(
                "Violin plot requested but minimum group n=%d < %d. "
                "KDE may be unreliable. Consider box plot instead.",
                min_n, SMALL_N_THRESHOLD
            )

    plt.figure(figsize=FIGURE_SIZE_SINGLE)
    sns.violinplot(data=df, x=group_col, y=value_col, palette="Set2")
    plt.title(title or f"Violin Plot: {value_col}")
    plt.tight_layout()
    plt.show()


def plot_hybrid(
    df: pd.DataFrame,
    value_col: str,
    group_col: str | None = None,
    title: str | None = None,
) -> None:
    """
    Hybrid: violin plot (distributional shape) with inner box plot (summary statistics).
    Recommended default for EDA. Combines shape visibility with robust outlier markers.

    Uses inner='box' to render quartile box inside the violin, and scale='width'
    so all violins are equal width regardless of sample size — preventing
    visual misinterpretation of group sizes.

    Args:
        value_col: Continuous variable to visualize.
        group_col: Optional categorical grouping variable.
        title: Plot title.
    """
    plt.figure(figsize=FIGURE_SIZE_SINGLE)
    sns.violinplot(
        data=df,
        x=group_col,
        y=value_col,
        inner="box",       # Overlay box plot statistics inside the violin
        scale="width",     # Normalize widths — do not encode sample size visually
        palette="Set2",
    )
    plt.title(title or f"Distribution (Hybrid): {value_col}")
    plt.tight_layout()
    plt.show()


def plot_distribution_comparison(
    df: pd.DataFrame,
    value_col: str,
    group_col: str | None = None,
) -> None:
    """
    Side-by-side comparison: box plot (left) vs. hybrid violin (right).
    Use during EDA to audit what each plot reveals before choosing one for reporting.
    """
    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_COMPARISON)

    sns.boxplot(data=df, x=group_col, y=value_col, palette="Set2", ax=axes[0])
    axes[0].set_title(f"Box Plot: {value_col}\n(Outliers + Median)")

    sns.violinplot(
        data=df, x=group_col, y=value_col,
        inner="box", scale="width", palette="Set2", ax=axes[1]
    )
    axes[1].set_title(f"Hybrid Violin: {value_col}\n(Shape + Summary Statistics)")

    plt.suptitle("Distribution Comparison", y=1.02, fontsize=13)
    plt.tight_layout()
    plt.show()
```

### General Plot Selection Guide

Apply this table when choosing any EDA visualization — not just for distributions:

| Data structure                   | Analysis goal          | Recommended plot                                                                |
| -------------------------------- | ---------------------- | ------------------------------------------------------------------------------- |
| One continuous variable          | Distribution shape     | Histogram + KDE (small n); violin (large n)                                     |
| One continuous variable          | Outlier detection      | Box plot                                                                        |
| One continuous variable          | Full picture           | Hybrid violin                                                                   |
| One continuous + one categorical | Group comparison       | Box plot (many groups) / Hybrid violin (few groups)                             |
| Two continuous variables         | Relationship           | Scatter plot + regression line                                                  |
| Two continuous variables         | Density at scale       | Hex bin or 2D KDE (when n > 10k and scatter overplotting occurs)                |
| Many continuous variables        | Pairwise relationships | `seaborn.pairplot()`                                                            |
| Many continuous variables        | Correlation structure  | Heatmap (Pearson or Spearman)                                                   |
| One categorical variable         | Frequency              | Horizontal bar chart, ordered by value (never pie chart in analytical contexts) |
| Time series                      | Trend + seasonality    | Line chart; decomposition plot                                                  |
| High-dimensional data            | Structure / clusters   | PCA scatter (2D projection)                                                     |

### Visualization Integrity Rules — Anti-patterns and Corrections

The credibility of a data analysis depends on the accuracy of its visual communication.
Each rule below addresses a documented cognitive bias or perceptual limitation.

> **Reference**: Cairo, A. (2016). _The Truthful Art: Data, Charts, and Maps for Communication_.
> New Riders Press. Wilke, C. O. (2019). _Fundamentals of Data Visualization_. O'Reilly.
> Tufte, E. R. (2001). _The Visual Display of Quantitative Information_ (2nd ed.). Graphics Press.

**Rule 1 — Categorical comparison: use ordered horizontal bar charts, not pie charts.**
The human visual system compares lengths along a common baseline with high precision.
It compares angles and circular arc areas with low precision. Pie charts become
unreadable beyond four categories when proportions are similar. Horizontal bar charts
ordered from largest to smallest allow immediate rank identification without reading labels.

**Rule 2 — Temporal trends: use line charts, not bar charts.**
Bar charts treat each time period as a discrete, independent event. Line charts connect
observations, making acceleration, deceleration, volatility, and directional change
visible as continuous phenomena. For time series with more than six periods, use a line
chart. A shaded area variant (area chart) adds emphasis to cumulative magnitude.

**Rule 3 — Distribution: never summarize with the mean alone.**
Two datasets can share an identical mean while having diametrically opposite distributional
structures — one unimodal symmetric, another bimodal or heavily skewed. Reporting only
the mean conceals this. Always accompany a mean with at minimum: standard deviation,
sample size, and a distribution visualization (histogram or box plot).

**Rule 4 — Y-axis integrity: bar charts must start at zero.**
Truncating the Y-axis of a bar chart (starting at a value above zero) distorts perceived
magnitude. A 1% difference can appear as a 10× difference visually when the axis is
truncated. This rule applies specifically to bar charts where bar length encodes
magnitude. Line charts may use a non-zero baseline when showing fine-grained variation
within a narrow range, provided the axis range is clearly labeled.

**Rule 5 — Scatter plots: always include a trend line and correlation statistic.**
A scatter plot without a regression line invites subjective pattern attribution. Always
overlay the OLS trend line and annotate with the Pearson r (or Spearman ρ for
non-normal data) and R². This quantifies the relationship mathematically, eliminates
visual ambiguity, and prevents incorrect causal inference from visual noise.

**Rule 6 — 3D charts: never use for statistical data.**
3D perspective introduces systematic optical distortion: elements in the foreground
appear larger than elements of identical magnitude in the background. This is not
a stylistic issue — it is a perceptual bias that produces incorrect magnitude
estimates. Use flat 2D charts exclusively. For proportions requiring a circular
form, use a 2D donut chart (ring chart), which allows the center to display a KPI.

**Rule 7 — Heatmaps for correlation: use divergent color scales.**
A sequential (single-color) scale maps both positive and negative correlation values
onto the same color progression. This makes it impossible to visually distinguish a
strong negative correlation from a near-zero correlation if they produce similar color
intensity. Use a divergent scale (e.g., blue–white–red) centered at zero. This
immediately reveals polarity: strong positive, strong negative, and neutral correlations
are each visually distinct.

**Rule 8 — Subgroup comparison: use grouped bar charts over 100% stacked bars.**
In a 100% stacked bar chart, only the bottom segment has a stable zero baseline.
Every higher segment floats on a shifting baseline, requiring the viewer to perform
mental subtraction to compare values. For comparing absolute magnitudes across
subgroups, use grouped (side-by-side) bar charts. Use 100% stacked bars only when
the explicit goal is showing part-to-whole composition across categories.

#### Anti-pattern Quick Reference

| Anti-pattern                                  | Correct alternative              | Reason                                          |
| --------------------------------------------- | -------------------------------- | ----------------------------------------------- |
| Pie chart with > 4 categories                 | Horizontal bar chart, ordered    | Length comparison is more accurate than angle   |
| Bar chart for time series trends              | Line chart                       | Bars fragment continuity; lines show flow       |
| Mean reported alone                           | Mean + std dev + histogram       | Mean conceals distributional shape              |
| Y-axis not starting at zero (bar chart)       | Y-axis from 0                    | Truncation exaggerates magnitude differences    |
| Scatter plot with no trend line               | Scatter + OLS line + r/R²        | Prevents subjective pattern attribution         |
| 3D chart                                      | 2D flat equivalent               | 3D perspective introduces perceptual distortion |
| Sequential color scale on correlation heatmap | Divergent scale (blue–white–red) | Sequential scale hides polarity                 |
| 100% stacked bars for magnitude comparison    | Grouped bar chart                | Floating baselines prevent accurate comparison  |

```python
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from ydata_profiling import ProfileReport
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- Constants ---
FIGURE_SIZE_DEFAULT: tuple[int, int] = (12, 6)
CORRELATION_THRESHOLD: float = 0.8
MISSING_THRESHOLD: float = 0.5  # Drop columns with > 50% missing


def load_and_inspect(filepath: str | Path, target_col: Optional[str] = None) -> pd.DataFrame:
    """
    Load a flat file and perform initial inspection.

    Args:
        filepath: Path to CSV or Excel file.
        target_col: Optional target variable name for supervised context.

    Returns:
        Loaded DataFrame with basic inspection logged.
    """
    path = Path(filepath)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path)
    logger.info("Shape: %s", df.shape)
    logger.info("Dtypes:\n%s", df.dtypes)
    logger.info("Missing values:\n%s", df.isnull().sum())
    return df


def describe_all(df: pd.DataFrame) -> dict:
    """
    Full descriptive statistics: numeric + categorical.

    Returns:
        Dictionary with 'numeric' and 'categorical' summary DataFrames.
    """
    numeric_summary = df.describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99]).T
    categorical_summary = df.select_dtypes(include="object").describe().T
    return {"numeric": numeric_summary, "categorical": categorical_summary}


def plot_distributions(df: pd.DataFrame, cols: Optional[list[str]] = None) -> None:
    """Plot histograms + KDE for all numeric columns."""
    numeric_cols = cols or df.select_dtypes(include=np.number).columns.tolist()
    for col in numeric_cols:
        fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_DEFAULT)
        sns.histplot(df[col].dropna(), kde=True, ax=axes[0])
        axes[0].set_title(f"Distribution: {col}")
        sns.boxplot(y=df[col].dropna(), ax=axes[1])
        axes[1].set_title(f"Boxplot: {col}")
        plt.tight_layout()
        plt.show()


def plot_correlation_matrix(df: pd.DataFrame, method: str = "pearson") -> None:
    """
    Plot correlation heatmap for numeric features.

    Args:
        method: 'pearson', 'spearman', or 'kendall'
    """
    corr = df.select_dtypes(include=np.number).corr(method=method)
    mask = np.triu(np.ones_like(corr, dtype=bool))
    plt.figure(figsize=(14, 10))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
                center=0, linewidths=0.5)
    plt.title(f"{method.capitalize()} Correlation Matrix")
    plt.tight_layout()
    plt.show()


def generate_profile_report(df: pd.DataFrame, output_path: str = "eda_report.html") -> None:
    """Generate full ydata-profiling HTML report."""
    profile = ProfileReport(df, title="EDA Report", explorative=True)
    profile.to_file(output_path)
    logger.info("Profile report saved to %s", output_path)
```

---

## 2. Time Series EDA {#time-series}

### Theoretical Foundations

A time series is a sequence of observations Y_t measured at successive, uniformly
spaced time intervals. Unlike cross-sectional data (multiple subjects at one point in
time), a time series is a single subject observed across time — formally modeled as a
realization of a stochastic process {Y_t, t ∈ T}.

**Why time series violates standard ML assumptions:**
Most classical statistical models and ML algorithms assume observations are
Independent and Identically Distributed (IID). Time series data breaks this
assumption entirely: each observation Y*t is statistically dependent on its
past values Y*{t-1}, Y*{t-2}, ..., Y*{t-k}. Ignoring this dependence in a
standard regression model causes underestimated standard errors, producing
artificially narrow confidence intervals and invalid significance tests.

**Three statistical properties that must be assessed in every time series EDA:**

| Property                       | Definition                                                     | Consequence if Ignored                                              |
| ------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------- |
| Autocorrelation                | Correlation of Y*t with its own lagged values Y*{t-k}          | Standard regression errors are underestimated; p-values are invalid |
| Stationarity                   | Mean and variance of Y_t are constant over time                | Models fit spurious relationships; forecasts are unreliable         |
| Conditional Heteroskedasticity | Variance of Y_t depends on past values (volatility clustering) | Risk is underquantified; model confidence intervals are wrong       |

**On stationarity in depth:** A non-stationary series has a time-varying mean,
variance, or both. Fitting a model to a non-stationary series risks discovering
a spurious correlation — two unrelated series that both trend upward will appear
correlated even if they share no causal relationship. Achieving stationarity
(via differencing, log transformation, or detrending) is a prerequisite for
ARIMA, VAR, and most classical forecasting models.

**Additive decomposition model:**

    Y_t = T_t + S_t + R_t

Where:

- T_t — Trend: the underlying long-term movement in the mean level
- S_t — Seasonality: periodic, repeating fluctuations (e.g., weekly, monthly, annual)
- R_t — Residual (noise): what remains after removing trend and seasonality

If R_t is white noise (zero mean, constant variance, no autocorrelation), the
decomposition is complete. If R_t retains autocorrelation structure, signal remains
unexploited and the model is incomplete. Always verify with an ACF plot of residuals.

Use the multiplicative model (Y_t = T_t × S_t × R_t) when seasonal amplitude
grows proportionally with the trend level (common in economic and sales data).

**Business domains where time series is the primary analytical tool:**

| Domain                | Application                                                       | Key Challenge                                                  |
| --------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------- |
| Supply Chain / Retail | Demand forecasting, inventory optimization                        | Seasonality, promotional events, intermittent demand           |
| Energy / Smart Grids  | Load forecasting, renewable integration                           | High-frequency data, weather dependency, real-time constraints |
| Fintech / Trading     | Regime detection, algorithmic execution, risk modeling            | Non-stationarity, volatility clustering, market microstructure |
| Healthcare            | ECG/EEG signal analysis, patient monitoring, disease surveillance | Non-stationarity, irregular sampling, noise                    |

### Implementation

```python
from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller, acf

logger = logging.getLogger(__name__)

# --- Constants ---
SIGNIFICANCE_LEVEL: float = 0.05
FIGURE_SIZE_WIDE: tuple[int, int] = (14, 4)
FIGURE_SIZE_DECOMP: tuple[int, int] = (14, 10)
WHITE_NOISE_LAGS: int = 40  # Number of lags to inspect in ACF diagnostics


def check_stationarity(series: pd.Series, significance: float = SIGNIFICANCE_LEVEL) -> dict:
    """
    Augmented Dickey-Fuller test for stationarity (unit root test).

    H0: The series has a unit root (non-stationary).
    Reject H0 when p-value < significance → series is stationary.

    Non-stationary series must be differenced or transformed before modeling
    with ARIMA, VAR, or regression — otherwise results are spurious.

    Args:
        series: Time series values.
        significance: Alpha level for hypothesis test.

    Returns:
        Dictionary with ADF statistic, p-value, critical values, and conclusion.
    """
    result = adfuller(series.dropna(), autolag="AIC")
    is_stationary = result[1] < significance
    output = {
        "adf_statistic": round(result[0], 4),
        "p_value": round(result[1], 4),
        "critical_values": {k: round(v, 4) for k, v in result[4].items()},
        "is_stationary": is_stationary,
        "conclusion": (
            "Stationary — safe to model directly."
            if is_stationary else
            "Non-stationary — apply differencing (d=1) or log transformation before modeling."
        ),
    }
    logger.info("ADF Test result: %s", output)
    return output


def decompose_series(
    series: pd.Series,
    model: str = "additive",
    period: int = 12,
) -> None:
    """
    Decompose a time series into Trend, Seasonality, and Residual components.

    Model selection:
    - 'additive': Y_t = T_t + S_t + R_t — use when seasonal amplitude is constant.
    - 'multiplicative': Y_t = T_t * S_t * R_t — use when seasonal amplitude grows
      proportionally with the trend (common in sales, economic data).

    After decomposition, always inspect the residual component visually and with
    ACF to verify it approximates white noise. Residual autocorrelation indicates
    unexploited signal.

    Args:
        model: 'additive' or 'multiplicative'.
        period: Seasonal period in time units (e.g., 12 = monthly with annual cycle).
    """
    decomposition = seasonal_decompose(series.dropna(), model=model, period=period)
    fig = decomposition.plot()
    fig.set_size_inches(FIGURE_SIZE_DECOMP)
    plt.suptitle(f"Seasonal Decomposition ({model.capitalize()} Model)", y=1.02)
    plt.tight_layout()
    plt.show()

    # Immediately check residuals for white noise
    residuals = decomposition.resid.dropna()
    check_white_noise(residuals)


def plot_acf_pacf(series: pd.Series, lags: int = WHITE_NOISE_LAGS) -> None:
    """
    Plot Autocorrelation Function (ACF) and Partial Autocorrelation Function (PACF).

    Diagnostic use for ARIMA order identification:
    - ACF tails off slowly + PACF cuts off at lag p → AR(p) process
    - ACF cuts off at lag q + PACF tails off slowly   → MA(q) process
    - Both tail off gradually                          → ARMA(p, q) process
    - Spikes at seasonal lags (e.g., 12, 24)           → Seasonal component present

    Always run on the stationary series (after differencing if required).

    Args:
        series: Stationary time series values.
        lags: Number of lags to display.
    """
    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_WIDE)
    plot_acf(series.dropna(), lags=lags, ax=axes[0], title="ACF — Autocorrelation Function")
    plot_pacf(series.dropna(), lags=lags, ax=axes[1], title="PACF — Partial Autocorrelation Function")
    plt.suptitle("ACF / PACF Diagnostic Plots", y=1.02)
    plt.tight_layout()
    plt.show()


def check_white_noise(residuals: pd.Series, lags: int = WHITE_NOISE_LAGS) -> dict:
    """
    Check whether decomposition residuals approximate white noise.

    A white noise process has: zero mean, constant variance, and no autocorrelation.
    Residuals that are NOT white noise contain unexploited signal — the model
    is incomplete and a more complex specification is required.

    Uses the Ljung-Box test:
    H0: Residuals are white noise (no autocorrelation up to lag k).
    Reject H0 (p < 0.05) → significant autocorrelation remains → model inadequate.

    Args:
        residuals: Residual component from decomposition or model fit.
        lags: Number of lags for Ljung-Box test.

    Returns:
        Dictionary with Ljung-Box Q-statistic, p-value, and conclusion.
    """
    from statsmodels.stats.diagnostic import acorr_ljungbox

    lb_result = acorr_ljungbox(residuals.dropna(), lags=[lags], return_df=True)
    p_value = float(lb_result["lb_pvalue"].iloc[0])
    is_white_noise = p_value > SIGNIFICANCE_LEVEL

    result = {
        "ljung_box_p_value": round(p_value, 4),
        "is_white_noise": is_white_noise,
        "conclusion": (
            "Residuals approximate white noise — decomposition is adequate."
            if is_white_noise else
            f"Residuals contain autocorrelation (p={p_value:.4f}) — "
            "model is incomplete. Consider ARIMA or higher-order seasonal model."
        ),
    }
    logger.info("White noise check: %s", result)

    # Visual confirmation
    fig, axes = plt.subplots(1, 2, figsize=FIGURE_SIZE_WIDE)
    residuals.plot(ax=axes[0], title="Residuals over Time")
    axes[0].axhline(0, color="red", linestyle="--", linewidth=1)
    plot_acf(residuals.dropna(), lags=min(lags, len(residuals) // 2 - 1), ax=axes[1],
             title="ACF of Residuals (should be within bounds)")
    plt.suptitle("Residual White Noise Diagnostic", y=1.02)
    plt.tight_layout()
    plt.show()

    return result


def fit_arch_garch(series: pd.Series, p: int = 1, q: int = 1) -> object:
    """
    Fit a GARCH(p, q) model to capture conditional heteroskedasticity.

    Conditional heteroskedasticity (volatility clustering) is a defining feature
    of financial time series: large price changes tend to be followed by large
    changes (of either sign), and calm periods cluster together. Standard ARIMA
    models assume constant variance and are inadequate for this.

    ARCH (Engle, 1982) and GARCH (Bollerslev, 1986) model the conditional variance:
        sigma^2_t = omega + alpha_1 * epsilon^2_{t-1} + beta_1 * sigma^2_{t-1}

    Args:
        series: Return or log-return series (should be stationary).
        p: Order of GARCH (lagged conditional variance terms).
        q: Order of ARCH (lagged squared residual terms).

    Returns:
        Fitted GARCH model result object.

    Note:
        Requires: uv add arch
    """
    try:
        from arch import arch_model
    except ImportError as exc:
        raise ImportError("Install arch: uv add arch") from exc

    model = arch_model(series.dropna(), vol="Garch", p=p, q=q, dist="normal")
    result = model.fit(disp="off")
    logger.info("GARCH(%d, %d) fit:\n%s", p, q, result.summary())

    # Plot conditional volatility
    fig = result.plot(annualize="D")
    plt.suptitle(f"GARCH({p},{q}) — Conditional Volatility")
    plt.tight_layout()
    plt.show()

    return result
```

### References

- Hyndman, R. J., & Athanasopoulos, G. (2021). _Forecasting: Principles and Practice_ (3rd ed.). OTexts. [Available free at otexts.com/fpp3]
- Box, G. E. P., Jenkins, G. M., & Reinsel, G. C. (2015). _Time Series Analysis: Forecasting and Control_. Wiley.
- Hamilton, J. D. (1994). _Time Series Analysis_. Princeton University Press.
- Taylor, S. J., & Letham, B. (2018). Forecasting at Scale. _The American Statistician_, 72(1), 37–45. [Facebook Prophet]
- Brockwell, P. J., & Davis, R. A. (2016). _Introduction to Time Series and Forecasting_. Springer.
- Engle, R. F. (1982). Autoregressive Conditional Heteroskedasticity with Estimates of the Variance of United Kingdom Inflation. _Econometrica_, 50(4), 987–1007. [Original ARCH paper]
- Bollerslev, T. (1986). Generalized Autoregressive Conditional Heteroskedasticity. _Journal of Econometrics_, 31(3), 307–327. [Original GARCH paper]

---

## 3. Text / NLP EDA {#nlp}

```python
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)


def text_basic_stats(series: pd.Series) -> pd.DataFrame:
    """
    Compute basic text statistics: length, word count, unique words.

    Args:
        series: Column of raw text strings.

    Returns:
        DataFrame with per-document statistics.
    """
    stats = pd.DataFrame({
        "char_count": series.str.len(),
        "word_count": series.str.split().str.len(),
        "unique_words": series.apply(lambda x: len(set(str(x).lower().split())) if pd.notna(x) else 0),
        "avg_word_length": series.apply(
            lambda x: sum(len(w) for w in str(x).split()) / max(len(str(x).split()), 1)
        )
    })
    return stats


def plot_top_ngrams(series: pd.Series, n: int = 1, top_k: int = 20) -> None:
    """
    Plot top-k n-grams from a text column.

    Args:
        n: 1 = unigrams, 2 = bigrams, etc.
        top_k: Number of top n-grams to display.
    """
    from nltk.util import ngrams
    tokens = " ".join(series.dropna().str.lower()).split()
    ng = [" ".join(g) for g in ngrams(tokens, n)]
    top = Counter(ng).most_common(top_k)
    labels, counts = zip(*top)
    plt.figure(figsize=(12, 6))
    plt.barh(labels[::-1], counts[::-1], color="steelblue")
    plt.title(f"Top {top_k} {n}-grams")
    plt.xlabel("Frequency")
    plt.tight_layout()
    plt.show()
```

---

## 4. Image Data EDA {#image}

```python
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def inspect_image_dataset(image_dir: str | Path, sample_size: int = 9) -> dict:
    """
    Inspect a directory of images: sizes, channels, sample grid.

    Returns:
        Dictionary with shape statistics and sample grid figure.
    """
    image_dir = Path(image_dir)
    paths = list(image_dir.glob("**/*.jpg")) + list(image_dir.glob("**/*.png"))
    sample = paths[:sample_size]

    sizes = []
    for p in paths[:500]:  # Limit scan for performance
        img = Image.open(p)
        sizes.append(img.size)

    widths, heights = zip(*sizes)
    stats = {
        "total_images": len(paths),
        "mean_width": np.mean(widths),
        "mean_height": np.mean(heights),
        "unique_sizes": len(set(sizes))
    }
    logger.info("Image dataset stats: %s", stats)

    # Sample grid
    fig, axes = plt.subplots(3, 3, figsize=(10, 10))
    for ax, path in zip(axes.flatten(), sample):
        img = Image.open(path)
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(path.name[:20], fontsize=8)
    plt.suptitle("Sample Images")
    plt.tight_layout()
    plt.show()

    return stats
```

---

## 5. SQL-Based EDA {#sql}

```sql
-- Profile a table: row count, null rates, distinct counts
SELECT
    COUNT(*)                                        AS total_rows,
    COUNT(column_name)                              AS non_null_count,
    COUNT(*) - COUNT(column_name)                   AS null_count,
    ROUND(100.0 * (COUNT(*) - COUNT(column_name))
          / COUNT(*), 2)                            AS null_pct,
    COUNT(DISTINCT column_name)                     AS distinct_values,
    MIN(column_name)                                AS min_value,
    MAX(column_name)                                AS max_value
FROM your_table;

-- Distribution of a categorical column
SELECT
    category_column,
    COUNT(*)                                        AS frequency,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
FROM your_table
GROUP BY category_column
ORDER BY frequency DESC;

-- Detect duplicates
SELECT
    key_column_1,
    key_column_2,
    COUNT(*)                                        AS duplicate_count
FROM your_table
GROUP BY key_column_1, key_column_2
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```
