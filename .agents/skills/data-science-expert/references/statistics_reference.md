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
9. [Bayesian Reasoning and Inference](#bayesian)

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

---

## 9. Bayesian Reasoning and Inference {#bayesian}

> **References**: Gelman, A., Carlin, J. B., Stern, H. S., Dunson, D. B., Vehtari, A.,
> & Rubin, D. B. (2013). _Bayesian Data Analysis_ (3rd ed.). CRC Press. [BDA3 — the
> > definitive graduate-level reference.] · Bayes, T. (1763). An essay toward solving a
> problem in the doctrine of chances. _Philosophical Transactions of the Royal Society_.
> · Jaynes, E. T. (2003). _Probability Theory: The Logic of Science_. Cambridge.
> · Murphy, K. P. (2022). _Probabilistic Machine Learning: An Introduction_. MIT Press.
> · Neal, R. M. (2011). MCMC using Hamiltonian dynamics. In _Handbook of Markov Chain
> Monte Carlo_. CRC Press. · PyMC Documentation. https://www.pymc.io/

### Conceptual Foundation

The Bayesian paradigm treats probability as a degree of belief about uncertain events,
updated as new evidence arrives. This contrasts with the frequentist paradigm, which
treats probability as a long-run frequency of repeatable experiments.

**Frequentist**: parameters are fixed but unknown constants; data are random.
Inference uses the sampling distribution of an estimator over hypothetical repetitions.

**Bayesian**: parameters are random variables with a probability distribution; data
are fixed (we observed them). Inference uses the posterior distribution of parameters
given the observed data.

The choice between paradigms is not philosophical in practice — it is determined by
the structure of the problem: what is known before data collection? What is the
inferential goal? What computation is feasible?

### Bayes' Theorem — Formulation

For hypothesis A and evidence B:

```
P(A|B) = P(B|A) * P(A) / P(B)
```

In statistical inference, replacing events with parameters θ and data D:

```
P(θ|D) = P(D|θ) * P(θ) / P(D)
```

Component definitions:

| Component | Symbol              | Name                            | Role                                   |
| --------- | ------------------- | ------------------------------- | -------------------------------------- |
| P(θ\|D)   | Posterior           | Updated belief                  | The inferential target — what we want  |
| P(D\|θ)   | Likelihood          | Data-generating model           | How probable is the data under each θ? |
| P(θ)      | Prior               | Prior belief                    | Knowledge about θ before seeing D      |
| P(D)      | Marginal likelihood | Evidence / normalizing constant | Ensures posterior integrates to 1      |

**Unnormalized form** (used in computation): posterior is proportional to likelihood × prior:

```
P(θ|D) ∝ P(D|θ) * P(θ)
```

P(D) = ∫ P(D|θ) P(θ) dθ is a constant with respect to θ and typically intractable.
MCMC methods sample from the unnormalized posterior, avoiding the need to compute P(D).

**Iterative learning**: in sequential Bayesian updating, the posterior from one
analysis becomes the prior for the next. This formalizes the principle of learning
from data without requiring the full dataset to be re-analyzed each time.

### Bayesian Workflow

```
Prior P(θ)  →  Data D  →  Posterior P(θ|D)  →  Decisions / Predictions
     ↑                           │
     └─── next prior ────────────┘    (sequential updating)
```

1. **Specify prior P(θ)**: encodes domain knowledge or uncertainty before seeing data.
   Strong prior + little data → posterior ≈ prior.
   Weak prior + lots of data → posterior ≈ likelihood.

2. **Specify likelihood P(D|θ)**: the probabilistic model for how data are generated.
   This is identical to frequentist model specification.

3. **Compute posterior P(θ|D)**: analytically (conjugate priors) or via MCMC / VI.

4. **Posterior predictive P(D_new|D)**: integrate over uncertainty in θ:
   ```
   P(D_new|D) = ∫ P(D_new|θ) P(θ|D) dθ
   ```
   This naturally propagates parameter uncertainty into predictions — frequentist
   plug-in estimators (substituting the MLE for θ) ignore this uncertainty.

### Frequentist vs. Bayesian Decision Guide

| Question                                        | Frequentist approach                | Bayesian approach                           |
| ----------------------------------------------- | ----------------------------------- | ------------------------------------------- |
| Is there prior knowledge about θ?               | Ignored by design                   | Encoded in prior                            |
| Is the sample size small?                       | Relies on asymptotic approximations | Exact finite-sample inference               |
| Is sequential updating needed?                  | Requires full re-analysis           | Prior → posterior → next prior              |
| Is parameter uncertainty needed in predictions? | Plug-in estimate (point)            | Posterior predictive (full distribution)    |
| Is the model complex with many parameters?      | MLE / regularization                | Hierarchical Bayes with MCMC                |
| Is computation time critical?                   | Fast (closed-form MLE)              | Slower (MCMC or VI required)                |
| Is interpretability critical?                   | p-values, CIs                       | Credible intervals, posterior probabilities |

### Prior Distributions — Selection

The prior encodes beliefs before observing data. Selection requires justification.

**Informative prior**: strong belief or historical data supports a specific distribution
and parameter values. Example: previous clinical trial results constrain a treatment
effect prior.

**Weakly informative prior** (Gelman et al., 2013, recommended default):
constrains the prior to a plausible range without dominating the likelihood.
Prevents pathological behavior (e.g., a Normal(0, 10) prior on a log-odds scale
allows effects from exp(-10) to exp(10) — already very wide but bounded).

**Non-informative / flat prior**: uniform P(θ) ∝ 1. Can be improper (does not
integrate to 1) but still yields a proper posterior when data are informative.
Jeffreys prior P(θ) ∝ √|I(θ)| (square root of Fisher information) is the canonical
non-informative choice: invariant to reparameterization.

**Conjugate prior**: a prior is conjugate to a likelihood if the posterior is in the
same distributional family as the prior. This yields closed-form posteriors without
numerical integration or MCMC.

### Conjugate Prior Table

| Likelihood              | Conjugate prior | Posterior                         | Sufficient statistic |
| ----------------------- | --------------- | --------------------------------- | -------------------- |
| Bernoulli(θ)            | Beta(α, β)      | Beta(α + Σxᵢ, β + n − Σxᵢ)        | Σxᵢ (successes)      |
| Binomial(n, θ)          | Beta(α, β)      | Beta(α + x, β + n − x)            | x (successes)        |
| Poisson(λ)              | Gamma(α, β)     | Gamma(α + Σxᵢ, β + n)             | Σxᵢ (total count)    |
| Normal(θ, σ²), σ² known | Normal(μ₀, τ₀²) | Normal(μₙ, τₙ²)                   | x̄ (sample mean)      |
| Normal(μ, θ), μ known   | InvGamma(α, β)  | InvGamma(α + n/2, β + Σ(xᵢ−μ)²/2) | Σ(xᵢ−μ)²             |
| Exponential(λ)          | Gamma(α, β)     | Gamma(α + n, β + Σxᵢ)             | Σxᵢ                  |
| Categorical(θ)          | Dirichlet(α)    | Dirichlet(α + count vector)       | Class counts         |

**Normal-Normal update** (most important for continuous data):

```
Prior:     θ ~ Normal(μ₀, τ₀²)     (prior mean μ₀, prior variance τ₀²)
Likelihood: x̄|θ ~ Normal(θ, σ²/n)   (sample mean from n observations)

Posterior:  θ|x̄ ~ Normal(μₙ, τₙ²)
  where:
    τₙ² = 1 / (1/τ₀² + n/σ²)                         (posterior precision = sum of precisions)
    μₙ  = τₙ² * (μ₀/τ₀² + n*x̄/σ²)                    (precision-weighted average of prior and data)
```

As n → ∞: μₙ → x̄ (data dominate); τₙ² → 0 (posterior concentrates).
As τ₀² → ∞ (flat prior): μₙ → x̄, τₙ² → σ²/n (posterior = sampling distribution of mean).

**Beta-Binomial update** (key for proportions and A/B testing):

```
Prior:     θ ~ Beta(α, β)            α = prior successes, β = prior failures (pseudo-counts)
Likelihood: X|θ ~ Binomial(n, θ)
Posterior: θ|X ~ Beta(α + x, β + n − x)

Posterior mean = (α + x) / (α + β + n)   (shrinks MLE x/n toward prior mean α/(α+β))
```

### Bayesian Credible Intervals vs. Frequentist Confidence Intervals

These are fundamentally different quantities — commonly confused:

**Frequentist 95% confidence interval [L, U]**: if the experiment were repeated
many times, 95% of the constructed intervals would contain the true θ.
Once computed, [L, U] either contains θ or it does not — there is no probability
statement about this specific interval.

**Bayesian 95% credible interval [L, U]**: given the observed data, there is 95%
posterior probability that θ ∈ [L, U]. This is the direct, intuitive statement.

Two variants of credible intervals:

- **Equal-tailed interval**: 2.5th to 97.5th posterior percentile
- **Highest Posterior Density (HPD) interval**: shortest interval containing 95%
  of posterior mass — preferred when the posterior is skewed

### Computational Methods for Posterior Inference

When conjugate priors are unavailable (the common case for realistic models),
the posterior cannot be derived analytically. Three computational approaches exist:

**1. Markov Chain Monte Carlo (MCMC)**

MCMC generates a Markov chain whose stationary distribution is the target posterior.
After a burn-in period, samples approximate draws from P(θ|D).

**Metropolis-Hastings** (Metropolis et al., 1953; Hastings, 1970): propose θ* from
a proposal distribution Q(θ*|θ_t); accept with probability min(1, P(θ*|D)Q(θ_t|θ*) /
P(θ_t|D)Q(θ\*|θ_t)). General but slow in high dimensions.

**Gibbs sampling**: when full conditional distributions P(θᵢ|θ\_{-i}, D) are tractable
(often the case with conjugate priors), sample each parameter in turn from its
conditional. Efficient when conditionals are conjugate; slow when parameters are
highly correlated.

**Hamiltonian Monte Carlo (HMC) / NUTS** (Neal, 2011; Hoffman & Gelman, 2014):
introduces auxiliary momentum variables and uses the gradient of log P(θ|D) to
simulate Hamiltonian dynamics. Proposes distant, high-probability states with
high acceptance rates. The No-U-Turn Sampler (NUTS) adapts step size and number
of leapfrog steps automatically. This is the default sampler in both PyMC and Stan.

<cite index="18">Stan uses NUTS — currently the most efficient and scalable MCMC method for
smooth target densities — and cannot use standard Monte Carlo methods for most
Bayesian problems because independent draws from the posterior are unavailable
except in conjugate-prior exponential-family models.</cite>

**MCMC diagnostics** (must check before reporting results):

```
R̂ (Gelman-Rubin statistic): < 1.01 for all parameters → chains have converged
Bulk-ESS:  effective sample size for central estimates → > 400 recommended
Tail-ESS:  effective sample size for tail quantiles → > 400 recommended
Trace plots: visually inspect chains for stationarity and good mixing
```

**2. Variational Inference (VI)**

Approximate the posterior P(θ|D) with a tractable distribution q(θ) from a
variational family, minimizing KL divergence KL(q ∥ P(θ|D)). Much faster than
MCMC but may underestimate posterior variance. Use when MCMC is computationally
infeasible at scale.

Automatic Differentiation Variational Inference (ADVI): accessible in PyMC via
`pm.fit()` and in Stan via `variational inference` mode.

**3. Laplace Approximation**

Approximate the posterior as a Gaussian centered at the MAP (maximum a posteriori)
estimate, with covariance equal to the negative inverse Hessian of the log posterior.
Fast but only valid near a unimodal, approximately Gaussian posterior.

### Bayesian A/B Testing

The Bayesian approach to A/B testing directly answers the business question —
"what is the probability that B is better than A?" — without requiring a fixed
sample size or p-value threshold.

```python
from __future__ import annotations

import numpy as np
from scipy import stats


def bayesian_ab_test(
    n_a: int,
    conversions_a: int,
    n_b: int,
    conversions_b: int,
    alpha_prior: float = 1.0,
    beta_prior: float = 1.0,
    n_samples: int = 100_000,
) -> dict:
    """
    Bayesian A/B test for conversion rates using Beta-Binomial conjugate model.

    Prior: Beta(alpha_prior, beta_prior)
      Default Beta(1,1) = Uniform[0,1] — non-informative.
      Use Beta(successes+1, failures+1) to encode historical conversion data.

    Posterior:
      theta_A | data ~ Beta(alpha_prior + conversions_a,
                            beta_prior + n_a - conversions_a)
      theta_B | data ~ Beta(alpha_prior + conversions_b,
                            beta_prior + n_b - conversions_b)

    Args:
        n_a: Total visitors in variant A.
        conversions_a: Conversions in variant A.
        n_b: Total visitors in variant B.
        conversions_b: Conversions in variant B.
        alpha_prior: Beta prior alpha parameter (pseudo-successes).
        beta_prior: Beta prior beta parameter (pseudo-failures).
        n_samples: Monte Carlo samples for numerical integration.

    Returns:
        Dictionary with posterior means, credible intervals, and P(B > A).
    """
    # Posterior parameters (Beta-Binomial conjugate update)
    alpha_a = alpha_prior + conversions_a
    beta_a  = beta_prior  + n_a - conversions_a
    alpha_b = alpha_prior + conversions_b
    beta_b  = beta_prior  + n_b - conversions_b

    # Sample from posteriors
    rng = np.random.default_rng(42)
    samples_a = rng.beta(alpha_a, beta_a, size=n_samples)
    samples_b = rng.beta(alpha_b, beta_b, size=n_samples)

    prob_b_better = float(np.mean(samples_b > samples_a))
    lift = samples_b / samples_a - 1.0

    return {
        "posterior_mean_a": alpha_a / (alpha_a + beta_a),
        "posterior_mean_b": alpha_b / (alpha_b + beta_b),
        "credible_interval_95_a": tuple(np.percentile(samples_a, [2.5, 97.5])),
        "credible_interval_95_b": tuple(np.percentile(samples_b, [2.5, 97.5])),
        "prob_b_better_than_a": prob_b_better,
        "expected_lift_pct_median": float(np.median(lift) * 100),
        "expected_lift_95ci": tuple(np.percentile(lift * 100, [2.5, 97.5])),
    }
```

### Naive Bayes Classifier — Bayesian Foundation

Naive Bayes applies Bayes' theorem to classification, with the "naive" assumption
that features are conditionally independent given the class:

```
P(y|x₁,...,xₙ) ∝ P(y) * ∏ᵢ P(xᵢ|y)
```

Decision rule: ŷ = argmax_y P(y) \* ∏ᵢ P(xᵢ|y)

Variants by likelihood model:

- **GaussianNB**: P(xᵢ|y) = Normal(μ_iy, σ²_iy) — for continuous features
- **MultinomialNB**: P(xᵢ|y) ∝ θ^xᵢ_iy — for word counts (text classification)
- **BernoulliNB**: P(xᵢ|y) = Bernoulli(θ_iy) — for binary features

Despite the independence assumption (almost always violated in practice), Naive Bayes
classifiers are competitive in text classification and spam detection, and perform
well when features are approximately conditionally independent.

### Full Bayesian Model with PyMC

```python
from __future__ import annotations

import numpy as np
import pymc as pm
import arviz as az


def bayesian_linear_regression(
    X: np.ndarray,
    y: np.ndarray,
    n_draws: int = 2000,
    n_tune: int = 1000,
    target_accept: float = 0.9,
) -> az.InferenceData:
    """
    Bayesian linear regression: y = alpha + beta * X + epsilon,  epsilon ~ Normal(0, sigma)

    Priors (weakly informative, per Gelman et al. 2013 recommendations):
      alpha ~ Normal(y_mean, 2.5 * y_std)   — intercept near data center
      beta  ~ Normal(0, 2.5)                 — regularizing prior on slope (standardized X)
      sigma ~ HalfNormal(y_std)              — positive, bounded near data scale

    Uses NUTS (No-U-Turn Sampler) via PyMC — same algorithm as Stan.

    Args:
        X: Feature matrix, shape (n, p). Should be standardized before passing.
        y: Target vector, shape (n,).
        n_draws: Posterior samples per chain after tuning.
        n_tune: Tuning (warm-up) steps discarded before sampling.
        target_accept: NUTS target acceptance rate (0.8-0.99; higher = smaller steps).

    Returns:
        ArviZ InferenceData object with posterior samples, diagnostics, and log-likelihood.
    """
    y_mean, y_std = float(y.mean()), float(y.std())

    with pm.Model() as model:
        # Weakly informative priors (Gelman et al., 2013)
        alpha = pm.Normal("alpha", mu=y_mean, sigma=2.5 * y_std)
        beta  = pm.Normal("beta",  mu=0,      sigma=2.5, shape=X.shape[1])
        sigma = pm.HalfNormal("sigma", sigma=y_std)

        # Likelihood
        mu = alpha + pm.math.dot(X, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y)

        # NUTS sampling (HMC with automatic step size)
        trace = pm.sample(
            draws=n_draws,
            tune=n_tune,
            target_accept=target_accept,
            return_inferencedata=True,
            progressbar=True,
        )

    return trace


def check_mcmc_convergence(trace: az.InferenceData) -> None:
    """
    Print MCMC convergence diagnostics. All R̂ < 1.01 and ESS > 400 required.
    Failing these checks invalidates posterior inference.
    """
    summary = az.summary(trace)
    print(summary[["mean", "sd", "hdi_3%", "hdi_97%", "r_hat", "ess_bulk", "ess_tail"]])

    rhat_max = float(summary["r_hat"].max())
    ess_min  = float(summary["ess_bulk"].min())

    if rhat_max >= 1.01:
        print(f"WARNING: Max R̂ = {rhat_max:.4f} ≥ 1.01 — chains have NOT converged")
    else:
        print(f"R̂ OK: max = {rhat_max:.4f}")

    if ess_min < 400:
        print(f"WARNING: Min bulk-ESS = {ess_min:.0f} < 400 — run more samples")
    else:
        print(f"ESS OK: min bulk-ESS = {ess_min:.0f}")
```

### Bayesian vs. Frequentist — Practical Decision Rule

```
Does the problem have meaningful prior information (domain knowledge, historical data)?
  YES → Bayesian: encode as informative or weakly informative prior
  NO  → Either; default frequentist for speed

Is the sample size very small (n < 30)?
  YES → Bayesian: avoids asymptotic approximations that fail at small n
  NO  → Either

Does the decision require a probability statement about a parameter?
  YES → Bayesian: "P(θ > 0.5 | data)" is a posterior probability, valid
        Frequentist: "p < 0.05" is NOT a probability about θ
  NO  → Either

Is the model hierarchical (groups within groups, random effects)?
  YES → Bayesian hierarchical model (Gelman et al., BDA3 Ch. 5)
  NO  → Either

Is speed critical and the model simple?
  YES → Frequentist (MLE + bootstrap); Bayesian MCMC adds cost
  NO  → Bayesian preferred for uncertainty quantification
```
