# Statistical Test Selection Guide

## Table of Contents

1. [Test Selection Decision Tree](#decision-tree)
2. [Parametric Tests](#parametric)
3. [Non-Parametric Tests](#non-parametric)
4. [Correlation & Association](#correlation)
5. [Time Series Tests](#time-series)
6. [Power Analysis](#power)
7. [Reporting Standards](#reporting)
8. [Variance and Standard Deviation — Foundations and ML Applications](#variance-std)

---

## 1. Test Selection Decision Tree {#decision-tree}

```
Are you comparing groups or testing relationships?
│
├── COMPARING GROUPS
│   ├── How many groups?
│   │   ├── 2 groups
│   │   │   ├── Is data normally distributed?
│   │   │   │   ├── YES → Are variances equal? (Levene test)
│   │   │   │   │         ├── YES → Independent t-test
│   │   │   │   │         └── NO  → Welch t-test
│   │   │   │   └── NO  → Mann-Whitney U test
│   │   │   └── Are samples paired?
│   │   │           ├── YES + Normal → Paired t-test
│   │   │           └── YES + Non-normal → Wilcoxon signed-rank
│   │   └── 3+ groups
│   │           ├── Normal + Equal variance → One-way ANOVA
│   │           │     └── Post-hoc: Tukey HSD
│   │           ├── Normal + Unequal variance → Welch ANOVA
│   │           └── Non-normal → Kruskal-Wallis
│   │                 └── Post-hoc: Dunn's test
│
└── TESTING RELATIONSHIPS
    ├── Both variables continuous?
    │   ├── Normal → Pearson correlation
    │   └── Non-normal / Ordinal → Spearman or Kendall
    ├── One continuous, one categorical → Point-biserial correlation
    └── Both categorical → Chi-Square (or Fisher's Exact if n < 5 per cell)
```

---

## 2. Parametric Tests {#parametric}

```python
from scipy import stats
import numpy as np
import logging

logger = logging.getLogger(__name__)

SIGNIFICANCE_LEVEL: float = 0.05


def check_normality(data: np.ndarray, alpha: float = SIGNIFICANCE_LEVEL) -> dict:
    """
    Shapiro-Wilk normality test (n < 5000).
    For larger samples, use D'Agostino-Pearson.

    Returns dict with test name, statistic, p-value, and conclusion.
    """
    if len(data) < 5000:
        stat, p = stats.shapiro(data)
        test_name = "Shapiro-Wilk"
    else:
        stat, p = stats.normaltest(data)
        test_name = "D'Agostino-Pearson"

    is_normal = p > alpha
    result = {
        "test": test_name,
        "statistic": round(stat, 4),
        "p_value": round(p, 4),
        "is_normal": is_normal,
        "conclusion": "Normal distribution assumed" if is_normal else "Non-normal: use non-parametric test"
    }
    logger.info("Normality test: %s", result)
    return result


def check_equal_variance(*groups: np.ndarray, alpha: float = SIGNIFICANCE_LEVEL) -> dict:
    """Levene's test for equality of variances across groups."""
    stat, p = stats.levene(*groups)
    return {
        "test": "Levene",
        "statistic": round(stat, 4),
        "p_value": round(p, 4),
        "equal_variance": p > alpha,
        "conclusion": "Equal variances assumed" if p > alpha else "Unequal variances: use Welch correction"
    }


def independent_ttest(group_a: np.ndarray, group_b: np.ndarray,
                       alpha: float = SIGNIFICANCE_LEVEL) -> dict:
    """
    Independent-samples t-test with automatic Welch correction if variances unequal.
    Always includes Cohen's d effect size.
    """
    lev = check_equal_variance(group_a, group_b, alpha=alpha)
    equal_var = lev["equal_variance"]

    stat, p = stats.ttest_ind(group_a, group_b, equal_var=equal_var)

    # Cohen's d effect size
    pooled_std = np.sqrt(
        ((len(group_a) - 1) * group_a.std(ddof=1) ** 2 +
         (len(group_b) - 1) * group_b.std(ddof=1) ** 2) /
        (len(group_a) + len(group_b) - 2)
    )
    cohen_d = (group_a.mean() - group_b.mean()) / pooled_std

    return {
        "test": "Welch t-test" if not equal_var else "Student t-test",
        "statistic": round(stat, 4),
        "p_value": round(p, 4),
        "significant": p < alpha,
        "cohen_d": round(cohen_d, 4),
        "effect_size_interpretation": _interpret_cohens_d(cohen_d),
        "conclusion": "Reject H₀ (significant difference)" if p < alpha else "Fail to reject H₀"
    }


def one_way_anova(*groups: np.ndarray, alpha: float = SIGNIFICANCE_LEVEL) -> dict:
    """One-way ANOVA with eta-squared effect size."""
    stat, p = stats.f_oneway(*groups)
    all_data = np.concatenate(groups)
    grand_mean = all_data.mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
    ss_total = sum((x - grand_mean) ** 2 for x in all_data)
    eta_squared = ss_between / ss_total

    return {
        "test": "One-way ANOVA",
        "f_statistic": round(stat, 4),
        "p_value": round(p, 4),
        "significant": p < alpha,
        "eta_squared": round(eta_squared, 4),
        "conclusion": "Significant group differences detected" if p < alpha else "No significant difference"
    }


def _interpret_cohens_d(d: float) -> str:
    """Interpret Cohen's d magnitude per Cohen (1988) conventions."""
    d = abs(d)
    if d < 0.2:   return "Negligible"
    if d < 0.5:   return "Small"
    if d < 0.8:   return "Medium"
    return "Large"
```

---

## 3. Non-Parametric Tests {#non-parametric}

```python
def mann_whitney_u(group_a: np.ndarray, group_b: np.ndarray,
                   alpha: float = SIGNIFICANCE_LEVEL) -> dict:
    """
    Mann-Whitney U test with rank-biserial correlation effect size.
    Use when normality cannot be assumed.
    """
    stat, p = stats.mannwhitneyu(group_a, group_b, alternative="two-sided")
    n1, n2 = len(group_a), len(group_b)
    r = 1 - (2 * stat) / (n1 * n2)  # rank-biserial correlation

    return {
        "test": "Mann-Whitney U",
        "statistic": round(stat, 4),
        "p_value": round(p, 4),
        "significant": p < alpha,
        "rank_biserial_r": round(r, 4),
        "effect_size_interpretation": "Small" if abs(r) < 0.3 else "Medium" if abs(r) < 0.5 else "Large"
    }


def kruskal_wallis(*groups: np.ndarray, alpha: float = SIGNIFICANCE_LEVEL) -> dict:
    """Kruskal-Wallis H test for 3+ independent non-normal groups."""
    stat, p = stats.kruskal(*groups)
    return {
        "test": "Kruskal-Wallis H",
        "statistic": round(stat, 4),
        "p_value": round(p, 4),
        "significant": p < alpha,
        "note": "Run Dunn's post-hoc test with Bonferroni correction if significant"
    }
```

---

## 4. Correlation & Association {#correlation}

```python
def compute_correlation(x: np.ndarray, y: np.ndarray,
                        method: str = "auto") -> dict:
    """
    Compute correlation with automatic method selection.

    Args:
        method: 'auto' selects based on normality; or 'pearson', 'spearman', 'kendall'
    """
    if method == "auto":
        norm_x = check_normality(x)
        norm_y = check_normality(y)
        method = "pearson" if (norm_x["is_normal"] and norm_y["is_normal"]) else "spearman"

    method_map = {
        "pearson": stats.pearsonr,
        "spearman": stats.spearmanr,
        "kendall": stats.kendalltau
    }

    stat, p = method_map[method](x, y)
    return {
        "method": method,
        "correlation": round(stat, 4),
        "p_value": round(p, 4),
        "r_squared": round(stat ** 2, 4) if method == "pearson" else None,
        "interpretation": _interpret_correlation(stat)
    }


def _interpret_correlation(r: float) -> str:
    r = abs(r)
    if r < 0.1:   return "Negligible"
    if r < 0.3:   return "Small"
    if r < 0.5:   return "Moderate"
    if r < 0.7:   return "Large"
    return "Very large"
```

---

## 5. Time Series Tests {#time-series}

```python
from statsmodels.tsa.stattools import adfuller, kpss, grangercausalitytests


def adf_test(series, alpha: float = 0.05) -> dict:
    """Augmented Dickey-Fuller test for unit roots (stationarity)."""
    result = adfuller(series.dropna(), autolag="AIC")
    return {
        "test": "Augmented Dickey-Fuller",
        "adf_statistic": round(result[0], 4),
        "p_value": round(result[1], 4),
        "critical_values": {k: round(v, 4) for k, v in result[4].items()},
        "is_stationary": result[1] < alpha,
        "conclusion": "Stationary" if result[1] < alpha else "Non-stationary (unit root present)"
    }
```

---

## 6. Power Analysis {#power}

```python
from statsmodels.stats.power import TTestIndPower, FTestAnovaPower


def compute_sample_size(effect_size: float, alpha: float = 0.05,
                        power: float = 0.8, test: str = "ttest") -> int:
    """
    Compute required sample size per group for a given effect size and power.

    Args:
        effect_size: Cohen's d (t-test) or Cohen's f (ANOVA)
        power: Desired statistical power (0.8 = 80% standard)
        test: 'ttest' or 'anova'

    Returns:
        Required sample size per group (rounded up).
    """
    import math
    if test == "ttest":
        analysis = TTestIndPower()
    else:
        analysis = FTestAnovaPower()

    n = analysis.solve_power(effect_size=effect_size, alpha=alpha, power=power)
    return math.ceil(n)
```

---

## 7. Reporting Standards {#reporting}

Every statistical result MUST be reported with the following components:

| Component                    | Example                                                                          |
| ---------------------------- | -------------------------------------------------------------------------------- |
| Test name                    | "Welch's independent t-test"                                                     |
| Test statistic               | t(df) = 3.42                                                                     |
| p-value                      | p = .003                                                                         |
| Effect size + interpretation | d = 0.61 (medium)                                                                |
| Confidence interval          | 95% CI [1.2, 5.8]                                                                |
| Sample sizes                 | n₁ = 120, n₂ = 118                                                               |
| Conclusion                   | "There was a statistically significant and practically meaningful difference..." |

**Critical reminder**: Statistical significance (p < α) does NOT imply practical significance.
Always report and interpret the effect size alongside the p-value.

---

## 8. Variance and Standard Deviation — Foundations and ML Applications {#variance-std}

> **References**: Fisher, R. A. (1925). _Statistical Methods for Research Workers_. Oliver & Boyd.
> Montgomery, D. C., & Runger, G. C. (2014). _Applied Statistics and Probability for Engineers_ (6th ed.). Wiley.
> Hastie, T., Tibshirani, R., & Friedman, J. (2009). _The Elements of Statistical Learning_ (2nd ed.). Springer.
> Goodfellow, I., Bengio, Y., & Courville, A. (2016). _Deep Learning_. MIT Press.

### Conceptual Foundation

Both variance and standard deviation quantify dispersion — how far observations spread
around the mean. They measure the same underlying property but serve different purposes
in practice.

**Population variance** (σ²):

    σ² = Σ(xᵢ - μ)² / n

**Sample variance** (s²) — used when estimating from a sample (n-1 in denominator, Bessel's correction):

    s² = Σ(xᵢ - x̄)² / (n - 1)

**Standard deviation** (σ or s): the square root of variance, restoring the original unit of measurement.

### Key Distinction: Units and Purpose

| Property                | Variance (σ²)                                                               | Standard Deviation (σ)                                                    |
| ----------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Unit of measurement     | Squared (e.g., USD², hours²)                                                | Original (e.g., USD, hours)                                               |
| Human interpretability  | Low — squared units are not intuitive                                       | High — directly comparable to the data scale                              |
| Primary use             | Mathematical optimization, PCA, ANOVA, loss functions                       | Business communication, outlier detection (Z-score), confidence intervals |
| Sensitivity to outliers | Very high — squaring amplifies extreme deviations                           | High, but more moderate                                                   |
| Additivity              | Variances of independent variables are additive: Var(X+Y) = Var(X) + Var(Y) | Standard deviations are NOT directly additive                             |

**Rule of thumb for communication**: Use variance when operating inside mathematical
machinery (algorithms, proofs, optimization). Use standard deviation when reporting
results to stakeholders or interpreting model uncertainty in original units.

Example: if a model predicts delivery time with mean = 10 hours and σ = 2 hours,
report "10 ± 2 hours" — not "variance = 4 hours²."

### The Empirical Rule (68-95-99.7 Rule)

For a normally distributed variable with mean μ and standard deviation σ:

| Interval | Probability | Practical Interpretation                               |
| -------- | ----------- | ------------------------------------------------------ | --- | ---- |
| μ ± 1σ   | 68.27%      | The central majority of observations                   |
| μ ± 2σ   | 95.45%      | Standard threshold for "unusual" values in many fields |
| μ ± 3σ   | 99.73%      | Basis for the Z-score outlier detection rule (         | Z   | > 3) |

This rule applies strictly to normal distributions. For non-normal data (skewed,
heavy-tailed, bimodal), apply Chebyshev's inequality instead: at least 1 - 1/k²
of observations fall within k standard deviations of the mean for any distribution.

### Variance in Machine Learning

Variance has two distinct roles in ML that must not be confused:

**Role 1 — Descriptive statistic**: Quantifies the spread of a feature or target.
Features with near-zero variance carry no information and should be removed
(use `VarianceThreshold` in scikit-learn). PCA finds the directions of maximum
variance in the feature space because variance represents the information content.

**Role 2 — Bias-Variance Tradeoff (generalization error)**: In the context of model
evaluation, variance refers to the sensitivity of a model's predictions to fluctuations
in the training set. The expected prediction error decomposes as:

    E[(y - ŷ)²] = Bias² + Variance + Irreducible Noise

| Term              | Definition                                                     | Symptom                               |
| ----------------- | -------------------------------------------------------------- | ------------------------------------- |
| Bias²             | Error from incorrect assumptions in the model (underfitting)   | High training error + high test error |
| Variance          | Error from over-sensitivity to training data (overfitting)     | Low training error + high test error  |
| Irreducible noise | Error from inherent randomness in the data — cannot be reduced | Persists regardless of model          |

Strategies to reduce **high variance** (overfitting):

- Regularization: L1 (Lasso), L2 (Ridge), Elastic Net — penalize large coefficient magnitudes
- Ensemble methods: Random Forests, gradient boosting — average over many trees
- Dropout (neural networks): randomly deactivate neurons during training
- Reduce model complexity: fewer parameters, shallower trees, smaller networks
- Increase training data: more data reduces variance by providing more signal

### Decision Guide: Variance vs Standard Deviation

```
Is the operation inside a mathematical algorithm or optimization?
  YES → Use variance (σ²): PCA, ANOVA, loss functions, feature selection
  NO  → Continue

Will the result be communicated to stakeholders or interpreted in original units?
  YES → Use standard deviation (σ): reports, confidence intervals, outlier flagging
  NO  → Continue

Are you combining the spread of two independent variables?
  YES → Use variance: Var(X + Y) = Var(X) + Var(Y)
  NO  → Either is valid; prefer standard deviation for interpretability
```

### Implementation

```python
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# --- Constants ---
OUTLIER_ZSCORE_THRESHOLD: float = 3.0  # Based on empirical 99.73% rule


def descriptive_spread(series: pd.Series) -> dict:
    """
    Compute variance, standard deviation, and related spread statistics.

    Returns both population and sample estimates. Uses sample (ddof=1) by default
    for inferential contexts; use ddof=0 for population-level descriptive summaries.

    Args:
        series: Numeric column to analyze.

    Returns:
        Dictionary of spread statistics with units noted.
    """
    data = series.dropna()
    mean = data.mean()

    return {
        "mean": round(mean, 4),
        "sample_variance": round(data.var(ddof=1), 4),       # s² — use for inference
        "population_variance": round(data.var(ddof=0), 4),   # σ² — use for full population
        "sample_std": round(data.std(ddof=1), 4),            # s
        "population_std": round(data.std(ddof=0), 4),        # σ
        "cv_pct": round(data.std(ddof=1) / mean * 100, 2) if mean != 0 else None,  # Coefficient of variation
        "skewness": round(data.skew(), 4),
        "kurtosis": round(data.kurtosis(), 4),  # Excess kurtosis; 0 = normal
    }


def detect_outliers_zscore(
    series: pd.Series,
    threshold: float = OUTLIER_ZSCORE_THRESHOLD,
) -> pd.Series:
    """
    Flag outliers using Z-score method (assumes approximate normality).

    Z-score = (x - mean) / std. Points with |Z| > threshold are flagged.
    The threshold of 3.0 corresponds to the 99.73% empirical rule boundary.

    Args:
        threshold: Z-score magnitude above which a point is considered an outlier.
                   Standard: 3.0. Stricter: 2.5. More lenient: 3.5.

    Returns:
        Boolean Series: True where the observation is an outlier.

    Note:
        For non-normal distributions, use IQR-based detection (box plot method)
        or Isolation Forest instead.
    """
    z_scores = np.abs(stats.zscore(series.dropna()))
    outlier_mask = pd.Series(z_scores > threshold, index=series.dropna().index)
    n_outliers = outlier_mask.sum()
    logger.info(
        "Z-score outlier detection (threshold=%.1f): %d outliers detected (%.2f%%)",
        threshold, n_outliers, 100 * n_outliers / len(series)
    )
    return outlier_mask


def variance_threshold_filter(
    df: pd.DataFrame,
    threshold: float = 0.01,
) -> pd.DataFrame:
    """
    Remove features with variance below threshold.

    Near-zero variance features carry negligible information and should be
    removed before ML model training. This is the statistical basis for
    scikit-learn's VarianceThreshold transformer.

    Args:
        threshold: Minimum variance to retain a feature.

    Returns:
        DataFrame with low-variance columns removed.
    """
    variances = df.var(ddof=1)
    retained = variances[variances >= threshold].index.tolist()
    dropped = variances[variances < threshold].index.tolist()
    logger.info(
        "Variance threshold filter (%.4f): retained %d features, dropped %d: %s",
        threshold, len(retained), len(dropped), dropped
    )
    return df[retained]
```
