# Statistical Test Selection Guide

## Table of Contents

1. [Test Selection Decision Tree](#decision-tree)
2. [Parametric Tests](#parametric)
3. [Non-Parametric Tests](#non-parametric)
4. [Correlation & Association](#correlation)
5. [Time Series Tests](#time-series)
6. [Power Analysis](#power)
7. [Reporting Standards](#reporting)

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
