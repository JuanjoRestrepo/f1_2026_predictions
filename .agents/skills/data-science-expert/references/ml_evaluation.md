# ML Model Evaluation Reference

## Table of Contents

0. [Environment Setup (uv)](#environment)
1. [Feature Scaling and Normalization](#feature-scaling)
2. [ML Algorithm Taxonomy — Selection Reference](#algorithm-taxonomy)
3. [Gradient Boosting Selection Guide — XGBoost vs LightGBM vs CatBoost](#gbm-guide)
4. [Classification Metrics](#classification)
5. [Regression Metrics](#regression)
6. [Clustering Metrics](#clustering)
7. [Model Explainability](#explainability)
8. [Evaluation Checklist](#checklist)

---

## 0. Environment Setup (uv) {#environment}

```bash
uv init ml_project && cd ml_project
uv python pin 3.12
uv venv .venv --python 3.12 && source .venv/bin/activate

# ML evaluation stack — full gradient boosting trio
uv add scikit-learn xgboost lightgbm catboost shap lime \
       matplotlib seaborn plotly pandas numpy scipy

# Deep learning (add as needed)
uv add torch torchvision          # PyTorch
uv add tensorflow                 # TensorFlow / Keras

# Dev tools
uv add --dev ruff mypy pytest
uv sync
```

---

## 1. Feature Scaling and Normalization {#feature-scaling}

> **References**: Géron, A. (2022). _Hands-On Machine Learning with Scikit-Learn,
> Keras, and TensorFlow_ (3rd ed.). O'Reilly, Ch. 2. · Hastie, T., Tibshirani, R.,
> & Friedman, J. (2009). _The Elements of Statistical Learning_ (2nd ed.). Springer.
> · scikit-learn Documentation. _Preprocessing data_.
> https://scikit-learn.org/stable/modules/preprocessing.html

### Conceptual Foundation

Feature scaling transforms numeric variables onto a comparable scale so that no
single feature dominates a model purely due to the magnitude of its units. Comparing
`annual_income` ($0–200,000) against `age` (18–70) without scaling means income
differences of a few hundred dollars can numerically overwhelm a full decade of age
difference in any distance-based or gradient-based computation — a spurious
dominance that has nothing to do with actual predictive importance.

Model quality depends as much on preprocessing quality as on algorithm selection.
Scaling is not optional polish — for scale-sensitive algorithms, it is a correctness
requirement, not a performance tweak.

**What scaling fixes**:

- Numerical instability (overflow/underflow) in matrix and vector computations
- Slow or unstable convergence in gradient-based optimizers
- One feature's scale dominating distance metrics or regularization penalties
- Reduced generalization from models sensitive to arbitrary unit choices
- Impaired comparability of feature coefficients or importances

### Feature Scaling Technique Comparison

| Technique                             | Formula                            | Output Range                  | Outlier Sensitivity                                            | Best Use Case                                                                            |
| ------------------------------------- | ---------------------------------- | ----------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Min-Max Scaling**                   | X' = (X − X_min) / (X_max − X_min) | Fixed [0, 1] (or custom)      | High — a single extreme value compresses the rest of the range | Bounded features; neural network inputs; when the exact range matters                    |
| **Z-Score Standardization**           | Z = (X − μ) / σ                    | Mean 0, std 1, unbounded      | Moderate                                                       | General-purpose default; distance-based and gradient-based algorithms                    |
| **Robust Scaling**                    | X' = (X − median) / IQR            | Unbounded, centered on median | Low — explicitly designed to resist outliers                   | Skewed distributions or datasets with heavy outlier contamination                        |
| **Max Absolute Scaling**              | X' = X / \|X\|\_max                | [−1, 1]                       | High                                                           | Sparse matrices — preserves zero entries exactly                                         |
| **Unit Vector Normalization (L1/L2)** | x' = x / \|x\|                     | Norm = 1 per row              | Depends on norm                                                | NLP, recommendation systems, cosine similarity — scales per-observation, not per-feature |

**Key distinction**: the first four techniques scale each _feature_ (column)
independently. Unit Vector Normalization scales each _observation_ (row) — it
answers a fundamentally different question (direction of a feature vector, not
comparability across features) and is not interchangeable with the other four.

### Which Algorithms Require Scaling

Scaling matters specifically for algorithms that compute distances, gradients, or
inner products — the geometry of the feature space directly enters the computation.

**Scale-sensitive — scaling required**:

| Category                  | Algorithms                             | Why scale matters                                                                                                                                                     |
| ------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Distance-based            | K-Means, K-Nearest Neighbors           | Euclidean/Manhattan distance is dominated by the largest-magnitude feature                                                                                            |
| Margin-based              | Support Vector Machines                | The margin and kernel computations are scale-dependent                                                                                                                |
| Neural networks           | MLP, deep learning architectures       | Unscaled inputs slow or destabilize backpropagation convergence                                                                                                       |
| Linear models             | Linear Regression, Logistic Regression | Especially critical with L1/L2 regularization — penalty is applied uniformly across coefficients, which is only meaningful if features are on comparable scales       |
| Dimensionality reduction  | PCA                                    | Directions of maximum variance are scale-dependent; an unscaled high-magnitude feature will dominate the principal components regardless of its actual signal content |
| Gradient-based optimizers | Any model trained via gradient descent | Scale differences distort the loss surface geometry, slowing convergence                                                                                              |

**Scale-invariant — scaling not required**:

| Algorithms                                                 | Why scale doesn't matter                                                                                                                                                                                                                                  |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Decision Trees, Random Forest, XGBoost, LightGBM, CatBoost | Tree-based models split on per-feature thresholds (X_i > c). A monotonic transformation of a feature does not change which observations fall on which side of any threshold — the split points shift but the resulting partition of the data is identical |

**Practical implication**: when benchmarking GBMs against linear models or neural
networks on the same dataset (see Section 3, GBM Selection Guide), do not scale
features for the GBM run — it is unnecessary work with zero effect on tree-based
model performance. Scaling is still required for any linear, distance-based, or
neural baseline used in the same comparison.

### Preprocessing Pipeline Placement and Data Leakage Prevention

```
Collection → Cleaning → Missing Values → Feature Engineering → Train/Test Split
                                                                       │
                                                                       ▼
                                                         Scaler .fit() on TRAIN ONLY
                                                                       │
                                                                       ▼
                                              .transform() on Train, Test, and Production data
                                                                       │
                                                                       ▼
                                                    Training → Evaluation → Deployment
```

**Critical rule against data leakage**: fit the scaler exclusively on the training
set. Apply `.transform()` (never `.fit()` again) to the validation set, test set,
and any new production data. Fitting on the full dataset before splitting leaks
information about the test set's distribution (its mean, std, min, max, or median)
into the training process — inflating validation performance in a way that will not
replicate in production.

This rule applies identically to every scaler in the comparison table above, and to
any other `fit`-based preprocessing step: imputers, encoders, and dimensionality
reducers all carry the same leakage risk if fit on data outside the training set.

### Implementation

```python
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import (
    MaxAbsScaler,
    MinMaxScaler,
    Normalizer,
    RobustScaler,
    StandardScaler,
)

logger = logging.getLogger(__name__)

# --- Constants ---
RANDOM_STATE: int = 42
TEST_SIZE: float = 0.2

SCALER_REGISTRY: dict[str, type] = {
    "minmax": MinMaxScaler,
    "standard": StandardScaler,
    "robust": RobustScaler,
    "maxabs": MaxAbsScaler,
}


def scale_features_correctly(
    X: pd.DataFrame,
    y: pd.Series,
    method: str = "standard",
    test_size: float = TEST_SIZE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, object]:
    """
    Split data and scale features with correct fit/transform separation.

    Demonstrates the mandatory leakage-safe pattern: the scaler is fit
    exclusively on X_train, then applied via transform() to both splits.

    Args:
        X: Feature matrix (unscaled).
        y: Target vector.
        method: One of 'minmax', 'standard', 'robust', 'maxabs'.
        test_size: Proportion of data held out for testing.

    Returns:
        Tuple of (X_train_scaled, X_test_scaled, y_train, y_test, fitted_scaler).
    """
    if method not in SCALER_REGISTRY:
        raise ValueError(f"Unknown method '{method}'. Choose from {list(SCALER_REGISTRY)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_STATE
    )

    scaler = SCALER_REGISTRY[method]()
    X_train_scaled = scaler.fit_transform(X_train)   # fit + transform on TRAIN only
    X_test_scaled = scaler.transform(X_test)          # transform ONLY on TEST — no fit

    logger.info(
        "Scaled with %s: train shape=%s, test shape=%s",
        method, X_train_scaled.shape, X_test_scaled.shape
    )
    return X_train_scaled, X_test_scaled, y_train.values, y_test.values, scaler


def unit_vector_normalize(X: np.ndarray, norm: str = "l2") -> np.ndarray:
    """
    Normalize each observation (row) to unit norm — distinct from feature scaling.

    Use for text/TF-IDF vectors, embeddings, or any context where cosine
    similarity is the downstream metric. Unlike the other scalers, this
    operates per-row and does not require a train/test fit distinction —
    each observation is normalized independently of all others.

    Args:
        norm: 'l1' (Manhattan norm) or 'l2' (Euclidean norm, most common).

    Returns:
        Row-normalized array, each row with the specified norm equal to 1.
    """
    normalizer = Normalizer(norm=norm)
    return normalizer.fit_transform(X)   # stateless — fit_transform is safe on any split


def recommend_scaler(
    has_outliers: bool,
    is_sparse: bool,
    bounded_output_required: bool,
) -> str:
    """
    Recommend a scaling method from dataset characteristics.

    Args:
        has_outliers: Whether the feature distribution has heavy outlier contamination.
        is_sparse: Whether the feature matrix is sparse (many exact zeros).
        bounded_output_required: Whether downstream use requires a fixed output range
            (e.g., certain neural network activation functions).

    Returns:
        Recommended scaler name from SCALER_REGISTRY.
    """
    if is_sparse:
        return "maxabs"   # preserves sparsity — zeros remain exactly zero
    if has_outliers:
        return "robust"   # median/IQR based — resistant to extreme values
    if bounded_output_required:
        return "minmax"   # guarantees output in a fixed range
    return "standard"     # general-purpose default for the common case
```

---

## 2. ML Algorithm Taxonomy — Selection Reference {#algorithm-taxonomy}

> **Authoritative basis**: This taxonomy follows the classification established in
> Bishop (2006) _Pattern Recognition and Machine Learning_, Hastie et al. (2009)
> _The Elements of Statistical Learning_, Murphy (2012) _Machine Learning: A Probabilistic
> Perspective_, and Goodfellow et al. (2016) _Deep Learning_. It represents the
> consensus categorization used across academic and industry practice.

This section provides a structured reference for algorithm selection by learning paradigm
and task type. Use it at Step 1 of the Workflow Decision Logic in SKILL.md:
"Understand the problem type."

### 1.1 Supervised Learning

Supervised learning requires labeled training data — each observation has a known output.
The model learns a mapping from input features to output labels or values.

#### Classification — predicting discrete class labels

| Algorithm                     | Key Characteristics                                                  | When to Use                                                             |
| ----------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Logistic Regression           | Linear decision boundary; probabilistic output; L1/L2 regularization | Baseline for binary/multiclass; interpretable; sparse features          |
| Naive Bayes                   | Assumes feature independence; fast; works well at small n            | Text classification, NLP, high-dimensional sparse data                  |
| K-Nearest Neighbors (KNN)     | Instance-based; no training phase; sensitive to scale                | Small datasets; non-linear boundaries; interpretable locally            |
| Support Vector Machine (SVM)  | Maximum-margin classifier; kernel trick for non-linearity            | High-dimensional spaces; small-to-medium datasets; text/image           |
| Decision Tree                 | Hierarchical splits; interpretable; prone to overfitting             | Rule extraction; interpretability requirement; feature interaction      |
| Random Forest                 | Ensemble of decorrelated trees; robust; handles missing values       | General-purpose; feature importance; tabular data at moderate scale     |
| XGBoost / LightGBM / CatBoost | Gradient boosting ensembles; state-of-the-art on tabular data        | Production tabular classification — see GBM Selection Guide (Section 2) |

#### Regression — predicting continuous values

| Algorithm                     | Key Characteristics                                    | When to Use                                                  |
| ----------------------------- | ------------------------------------------------------ | ------------------------------------------------------------ |
| Simple Linear Regression      | Single predictor; OLS closed-form solution             | Baseline; interpretable; linearity assumption holds          |
| Multiple Linear Regression    | Multiple predictors; OLS; assumes no multicollinearity | Linear relationships; low-dimensional; inference required    |
| Ridge Regression (L2)         | Shrinks all coefficients; handles multicollinearity    | Many correlated features; all features likely relevant       |
| Lasso Regression (L1)         | Sparse solution; performs feature selection            | Many features; expect only a subset to be predictive         |
| Elastic Net                   | L1 + L2 combined; balances sparsity and grouping       | Correlated features + sparsity needed simultaneously         |
| XGBoost / LightGBM / CatBoost | Gradient boosting for regression; non-linear; robust   | Non-linear relationships; tabular data; production pipelines |

### 1.2 Unsupervised Learning

Unsupervised learning operates on unlabeled data. The model discovers inherent
structure, patterns, or compact representations.

#### Clustering — grouping similar observations

| Algorithm                     | Key Characteristics                                                | When to Use                                                           |
| ----------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------- |
| K-Means                       | Centroid-based; assumes spherical clusters; requires k             | Well-separated, roughly equal-sized clusters; large datasets          |
| DBSCAN                        | Density-based; finds arbitrary shapes; detects noise/outliers      | Irregular cluster shapes; unknown number of clusters; spatial data    |
| Hierarchical Clustering       | Builds a dendrogram; no k required; deterministic                  | Small datasets; cluster hierarchy matters; interpretability needed    |
| Gaussian Mixture Models (GMM) | Probabilistic; soft assignments; fits K Gaussian components via EM | Overlapping or elliptical clusters; probabilistic membership required |

##### Gaussian Mixture Models (GMM) — Extended Reference

> **References**: McLachlan, G., & Peel, D. (2000). _Finite Mixture Models_. Wiley.
> Bishop, C. M. (2006). _Pattern Recognition and Machine Learning_ (Ch. 9). Springer.
> Dempster, A. P., Laird, N. M., & Rubin, D. B. (1977). Maximum Likelihood from Incomplete
> Data via the EM Algorithm. _Journal of the Royal Statistical Society_, Series B, 39(1), 1–38.

A GMM assumes observed data is generated from a mixture of K Gaussian distributions,
each with its own mean vector μ_k, covariance matrix Σ_k, and mixing weight π_k
(where Σ π_k = 1). Unlike K-Means, which assigns each point to exactly one cluster
(hard assignment), GMM computes the posterior probability that each point belongs to
each component — a soft assignment. This makes GMM a generative probabilistic model:
it explicitly models the density of the data, not just cluster membership.

**The EM Algorithm (Expectation-Maximization):**
GMM parameters are estimated via EM, which alternates between two steps until convergence:

- E-step (Expectation): Compute the posterior probability (responsibility) r_nk — the
  probability that observation x_n was generated by component k, given current parameters.
- M-step (Maximization): Update μ_k, Σ_k, and π_k to maximize the log-likelihood,
  using the responsibilities computed in the E-step as soft weights.

EM is guaranteed to monotonically increase the log-likelihood at each iteration but
converges to a local maximum, not necessarily the global one. Run multiple random
initializations (n_init) and retain the solution with the highest log-likelihood.

**GMM vs. K-Means — decision criteria:**

| Dimension                     | K-Means                          | GMM                                           |
| ----------------------------- | -------------------------------- | --------------------------------------------- |
| Cluster shape                 | Spherical (equal-radius Voronoi) | Elliptical (arbitrary covariance)             |
| Assignment                    | Hard (one cluster per point)     | Soft (probability distribution over clusters) |
| Output                        | Cluster labels                   | Posterior probabilities per component         |
| Interpretability              | Simple centroid                  | Full density model (mean + covariance)        |
| Sensitivity to initialization | High                             | High (use n_init > 1)                         |
| Outlier handling              | Sensitive                        | Sensitive — consider DBSCAN for noisy data    |
| Computational cost            | Low                              | Higher (EM iterations)                        |

**Component selection with AIC and BIC:**
The number of components K is a hyperparameter. Selecting K by visual inspection
alone is unreliable. Use information criteria:

- AIC (Akaike, 1974): AIC = 2k - 2ln(L), where k = number of parameters.
  Penalizes complexity less aggressively. Tends to select more components.
- BIC (Schwarz, 1978): BIC = k·ln(n) - 2ln(L). Penalizes complexity more strongly
  as sample size grows. Generally preferred for GMM model selection in practice.

Select the K that minimizes BIC. If AIC and BIC disagree, prefer BIC for
predictive purposes; prefer AIC when the goal is density estimation.

```python
from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# --- Constants ---
GMM_MAX_COMPONENTS: int = 10
GMM_N_INIT: int = 10          # Multiple restarts to avoid local optima
GMM_RANDOM_STATE: int = 42
GMM_COVARIANCE_TYPE: str = "full"  # 'full', 'tied', 'diag', 'spherical'


def select_gmm_components(
    X: np.ndarray,
    max_components: int = GMM_MAX_COMPONENTS,
    covariance_type: str = GMM_COVARIANCE_TYPE,
) -> dict:
    """
    Select optimal number of GMM components using AIC and BIC.

    AIC tends to overestimate components; BIC is preferred for model selection
    when the true number of components is the goal. If goals differ, compare both.

    Args:
        X: Feature matrix (should be standardized before fitting).
        max_components: Maximum K to evaluate.
        covariance_type: Covariance structure — 'full' is most flexible but
            requires more data; 'diag' assumes independent features; 'tied'
            constrains all components to share one covariance matrix.

    Returns:
        Dictionary with AIC array, BIC array, and optimal K per criterion.
    """
    aic_scores: list[float] = []
    bic_scores: list[float] = []
    k_range = range(1, max_components + 1)

    for k in k_range:
        gmm = GaussianMixture(
            n_components=k,
            covariance_type=covariance_type,
            n_init=GMM_N_INIT,
            random_state=GMM_RANDOM_STATE,
        )
        gmm.fit(X)
        aic_scores.append(gmm.aic(X))
        bic_scores.append(gmm.bic(X))

    optimal_aic = int(np.argmin(aic_scores)) + 1
    optimal_bic = int(np.argmin(bic_scores)) + 1
    logger.info("Optimal K — AIC: %d | BIC: %d (prefer BIC)", optimal_aic, optimal_bic)

    # Plot AIC and BIC curves
    plt.figure(figsize=(9, 5))
    plt.plot(list(k_range), aic_scores, marker="o", label="AIC", linewidth=2)
    plt.plot(list(k_range), bic_scores, marker="s", label="BIC", linewidth=2)
    plt.axvline(optimal_bic, color="gray", linestyle="--", label=f"Optimal BIC (K={optimal_bic})")
    plt.xlabel("Number of Components (K)")
    plt.ylabel("Information Criterion Score (lower = better)")
    plt.title("GMM Component Selection — AIC and BIC")
    plt.legend()
    plt.tight_layout()
    plt.show()

    return {
        "aic_scores": aic_scores,
        "bic_scores": bic_scores,
        "optimal_k_aic": optimal_aic,
        "optimal_k_bic": optimal_bic,
    }


def fit_gmm(
    X: np.ndarray,
    n_components: int,
    covariance_type: str = GMM_COVARIANCE_TYPE,
) -> tuple[GaussianMixture, np.ndarray, np.ndarray]:
    """
    Fit a GMM and return labels and soft membership probabilities.

    Always standardize features before fitting. GMM is sensitive to scale
    because covariance estimation is scale-dependent.

    Args:
        n_components: Number of Gaussian components (use select_gmm_components first).
        covariance_type: Covariance structure.

    Returns:
        Tuple of (fitted model, hard labels, soft probability matrix [n_samples x K]).
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    gmm = GaussianMixture(
        n_components=n_components,
        covariance_type=covariance_type,
        n_init=GMM_N_INIT,
        random_state=GMM_RANDOM_STATE,
    )
    gmm.fit(X_scaled)

    labels = gmm.predict(X_scaled)
    probabilities = gmm.predict_proba(X_scaled)  # Shape: (n_samples, K)
    log_likelihood = gmm.score(X_scaled)

    logger.info(
        "GMM(%d components) fit — log-likelihood: %.4f | converged: %s",
        n_components, log_likelihood, gmm.converged_
    )
    return gmm, labels, probabilities


def score_gmm_anomalies(
    gmm: GaussianMixture,
    X_scaled: np.ndarray,
    threshold_percentile: float = 2.5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Use GMM log-likelihood as a density-based anomaly score.

    A fitted GMM is a generative model — it defines a probability density
    over the feature space. Points with very low log p(x) are in low-density
    regions and can be treated as anomalies without training a separate detector.

    This approach naturally handles elliptical cluster shapes and multi-modal
    distributions, which distance-based anomaly detectors cannot model.

    Args:
        gmm: A fitted GaussianMixture instance.
        X_scaled: Standardized feature matrix (same scale as training data).
        threshold_percentile: Points below this percentile of log p(x) are flagged.
                              Default 2.5 flags the bottom 2.5% as anomalies.

    Returns:
        Tuple of (log_scores array, boolean anomaly mask).
    """
    log_scores = gmm.score_samples(X_scaled)
    threshold = np.percentile(log_scores, threshold_percentile)
    anomaly_mask = log_scores < threshold
    logger.info(
        "GMM anomaly detection: %d anomalies flagged (bottom %.1f%% of log p(x), threshold=%.4f)",
        anomaly_mask.sum(), threshold_percentile, threshold
    )
    return log_scores, anomaly_mask
```

**Covariance type selection guide:**

| Type          | Structure                                                       | Parameters                    | When to Use                                                                               |
| ------------- | --------------------------------------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------- |
| `'full'`      | Each component has its own unrestricted covariance matrix       | Most — scales as O(K \* d²)   | Default; use when clusters may have different shapes, orientations, and sizes             |
| `'tied'`      | All components share one covariance matrix                      | Fewest — one matrix for all K | Use when you expect clusters of similar shape but different locations                     |
| `'diag'`      | Each component has a diagonal covariance (independent features) | Moderate                      | Use when features are approximately independent after standardization; faster than 'full' |
| `'spherical'` | Each component has a single scalar variance (isotropic)         | Fewest per component          | Equivalent to soft K-Means; use only when clusters are approximately spherical            |

Rule: start with `'full'` for maximum flexibility. If data is high-dimensional (d > 20),
prefer `'diag'` or `'tied'` — full covariance estimation becomes unreliable as d grows
(the curse of dimensionality).

**PCA + GMM pipeline for high-dimensional data:**

When the feature space is high-dimensional (d > 20), fitting a full-covariance GMM
becomes statistically unreliable — each d×d covariance matrix requires O(d²) parameters,
and the available data per component is insufficient to estimate them accurately.
The standard approach is to reduce dimensionality with PCA first, retaining enough
components to explain 90–95% of variance, then fit GMM in the reduced space.

```python
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
import numpy as np


def pca_gmm_pipeline(
    X: np.ndarray,
    n_components_gmm: int,
    explained_variance_ratio: float = 0.95,
    covariance_type: str = "full",
) -> tuple[Pipeline, np.ndarray, np.ndarray]:
    """
    PCA dimensionality reduction followed by GMM clustering.

    Recommended when the input feature space has d > 20 dimensions.
    PCA is fit on standardized data; GMM is fit on PCA-projected data.

    Args:
        n_components_gmm: Number of GMM components (determined by BIC on reduced data).
        explained_variance_ratio: Fraction of variance to retain in PCA reduction.
        covariance_type: GMM covariance type — 'full' is safe after PCA reduces d.

    Returns:
        Tuple of (fitted Pipeline, hard cluster labels, soft probability matrix).
    """
    pca = PCA(n_components=explained_variance_ratio, svd_solver="full")
    X_pca = pca.fit_transform(StandardScaler().fit_transform(X))
    n_pca_components = X_pca.shape[1]
    logger.info(
        "PCA reduced %d features to %d components (%.1f%% variance retained)",
        X.shape[1], n_pca_components, explained_variance_ratio * 100
    )

    gmm = GaussianMixture(
        n_components=n_components_gmm,
        covariance_type=covariance_type,
        n_init=GMM_N_INIT,
        random_state=GMM_RANDOM_STATE,
    )
    gmm.fit(X_pca)
    labels = gmm.predict(X_pca)
    probabilities = gmm.predict_proba(X_pca)
    return gmm, labels, probabilities
```

**Additional GMM capabilities (practical notes from applied use):**

- **Data synthesis**: A fitted GMM is generative — `gmm.sample(n_samples)` draws new
  observations from the learned distribution. Useful for simulation, stress-testing
  pipelines, or augmenting underrepresented segments.
- **Scoring new observations**: `gmm.predict_proba(X_new)` assigns soft cluster
  membership to unseen data at inference time, enabling real-time segmentation.
- **Limitations checklist**:
  - EM converges to local optima — always use n_init >= 10 and compare log-likelihoods
  - Assumes Gaussian components — if clusters are non-Gaussian, consider kernel density estimation
  - High dimensionality degrades covariance estimation — apply PCA before GMM when d > 20
  - K must be specified — use BIC for selection; domain knowledge to validate

#### Dimensionality Reduction — compressing feature space

| Algorithm                            | Key Characteristics                                        | When to Use                                                           |
| ------------------------------------ | ---------------------------------------------------------- | --------------------------------------------------------------------- |
| Principal Component Analysis (PCA)   | Linear; maximizes variance; orthogonal components          | High-dimensional tabular data; preprocessing before ML; visualization |
| Independent Component Analysis (ICA) | Finds statistically independent components; non-Gaussian   | Signal separation (e.g., EEG, audio); latent source recovery          |
| t-SNE                                | Non-linear; 2D/3D visualization; preserves local structure | Visualization only — not suitable as a preprocessing step for ML      |
| UMAP                                 | Non-linear; faster than t-SNE; better global structure     | Visualization + preprocessing; large datasets; cluster inspection     |

#### Association Rule Mining — finding co-occurrence patterns

| Algorithm | Key Characteristics                                      | When to Use                                            |
| --------- | -------------------------------------------------------- | ------------------------------------------------------ |
| Apriori   | Breadth-first search; generates candidate itemsets       | Small-to-medium item sets; market basket analysis      |
| FP-Growth | Tree-based; no candidate generation; faster than Apriori | Large transaction datasets; scales better than Apriori |

#### Anomaly Detection — identifying unusual observations

| Algorithm                  | Key Characteristics                                                      | When to Use                                                                       |
| -------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Z-score                    | Univariate; assumes normality; flags points beyond N standard deviations | Simple univariate outlier detection; normally distributed features                |
| Isolation Forest           | Ensemble of random trees; model-free; scales well                        | Multivariate anomaly detection; high-dimensional data; no distribution assumption |
| Local Outlier Factor (LOF) | Density-based; detects local anomalies                                   | Anomalies in regions of varying density; spatial data                             |
| One-Class SVM              | Boundary-based; trained on normal class only                             | When only normal examples are available during training                           |

### 1.3 Semi-Supervised Learning

Semi-supervised learning uses a small labeled dataset combined with a large unlabeled
dataset. Applicable when labeling is expensive or time-consuming.

| Algorithm         | Task           | Key Characteristics                                                                                              | When to Use                                                                     |
| ----------------- | -------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Self-Training     | Classification | Trains on labeled data; iteratively labels high-confidence unlabeled examples                                    | Simple baseline; any classifier can be wrapped                                  |
| Co-Training       | Classification | Two classifiers trained on two independent feature views; each labels data for the other (Blum & Mitchell, 1998) | Natural feature splits exist (e.g., text + metadata); redundant views available |
| Label Propagation | Classification | Graph-based; propagates labels through similarity graph                                                          | Graph-structured data; local cluster assumption holds                           |

Note: Co-Training is a classification method — not a regression technique. Its
theoretical guarantee requires two conditionally independent, sufficient feature views.

### 1.4 Reinforcement Learning

Reinforcement learning trains an agent to take actions in an environment to maximize
cumulative reward. No labeled dataset — the signal comes from environmental feedback.

| Paradigm                         | Algorithm                             | Key Characteristics                                             | When to Use                                                         |
| -------------------------------- | ------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------- |
| Model-Free / Policy Optimization | Policy Gradient (REINFORCE, PPO, A3C) | Directly optimizes the policy; handles continuous action spaces | Robotics, game playing, continuous control                          |
| Model-Free / Value-Based         | Q-Learning, Deep Q-Network (DQN)      | Learns a value function; off-policy; discrete action spaces     | Game playing (Atari); discrete decision problems                    |
| Model-Based                      | World Model + Planner                 | Learns environment dynamics; uses model for planning            | Data-efficient learning; environments where simulation is available |

### 1.5 Deep Learning Architecture Selection by Data Geometry

> **Reference**: Bronstein et al. (2021). Geometric Deep Learning: Grids, Groups,
> Graphs, Geodesics, and Gauges. arXiv:2104.13478.

Standard ML algorithm selection (Sections 1.1–1.4) assumes tabular or vector data.
When the data has geometric structure, architecture selection must start from the
data shape. Bronstein et al. (2021) unify CNN, RNN, Transformer, and GNN under a
single framework: each architecture exploits a specific symmetry group of its data domain.

| Data structure                             | Symmetry                            | Architecture                        | Task examples                                                |
| ------------------------------------------ | ----------------------------------- | ----------------------------------- | ------------------------------------------------------------ |
| Regular spatial grid (images, video)       | Translation equivariance            | CNN                                 | Object detection, medical imaging, satellite imagery         |
| Ordered sequence (short-to-medium)         | Time-shift equivariance             | RNN / LSTM                          | Time series, IoT sensors, short NLP                          |
| Sequence with long-range dependencies      | Global permutation equivariance     | Transformer                         | Language, code generation, summarization                     |
| Graph — nodes + edges (arbitrary topology) | Neighborhood permutation invariance | GNN                                 | Molecules, fraud detection, recommendation, knowledge graphs |
| Tabular — no geometric structure           | None                                | GBM (XGBoost / LightGBM / CatBoost) | Business analytics, structured datasets                      |

**GNN is the correct architecture only when**: the data is explicitly structured as a
graph (V nodes, E edges) and the connectivity pattern carries predictive signal beyond
what node features alone provide. See `references/gnn_reference.md` for the complete
GNN reference including GCN, GAT, GraphSAGE, GIN architectures, PyTorch Geometric
implementation, and known failure modes (over-smoothing, over-squashing).

### Algorithm Selection Decision Logic

Apply this as Step 1 of the Workflow Decision Logic defined in SKILL.md:

```
0. What is the structure of the data?
   Graph (nodes + explicit edges with relational meaning) → GNN
     → See references/gnn_reference.md for architecture selection (GCN/GAT/GraphSAGE/GIN)
   Spatial grid (pixels, voxels) → CNN
   Ordered sequence → LSTM (short) / Transformer (long-range)
   Tabular / vector → Continue to Step 1

1. Is the target variable known for training examples?
   YES → Supervised Learning
   NO  → Unsupervised Learning
   PARTIAL (some labeled, mostly unlabeled) → Semi-Supervised Learning
   NONE (reward signal only) → Reinforcement Learning

2. For Supervised Learning — what type is the target?
   Discrete categories → Classification
   Continuous value    → Regression

3. For Unsupervised Learning — what is the goal?
   Group similar observations       → Clustering
   Reduce feature dimensionality    → Dimensionality Reduction
   Find co-occurrence patterns      → Association Rule Mining
   Detect anomalies / outliers      → Anomaly Detection

4. For tabular data (Classification or Regression):
   Always benchmark XGBoost, LightGBM, and CatBoost first.
   See Section 3 (GBM Selection Guide) for detailed criteria.
```

---

## 3. Gradient Boosting Selection Guide — XGBoost vs LightGBM vs CatBoost {#gbm-guide}

> **Scientific basis**: Gradient Boosting was formalized by Friedman (2001). Modern
> implementations (XGBoost, LightGBM, CatBoost) dominate tabular ML.
> Grinsztajn et al. (2022) — _"Why tree-based models still outperform deep learning
> on tabular data"_ — empirically confirms that tree-based models are the default
> state-of-the-art for structured/tabular problems. Always benchmark all three
> before considering neural networks on tabular data.

### Framework Comparison Matrix

| Dimension                | XGBoost                  | LightGBM                         | CatBoost                            |
| ------------------------ | ------------------------ | -------------------------------- | ----------------------------------- |
| **Authors**              | Chen & Guestrin, 2016    | Microsoft / Ke et al., 2017      | Yandex / Prokhorenkova et al., 2018 |
| **Tree growth**          | Level-wise (depth-first) | Leaf-wise (best-first)           | Symmetric (oblivious) trees         |
| **Training speed**       | Moderate                 | ⚡ Fastest                       | Moderate–Slow (more epochs)         |
| **Memory usage**         | Moderate                 | Low                              | Moderate                            |
| **Categorical features** | Manual encoding required | Manual encoding required         | ✅ Native, no encoding needed       |
| **Data leakage risk**    | Standard                 | Standard                         | ✅ Reduced via ordered boosting     |
| **Regularization**       | L1 + L2                  | L1 + L2                          | Built-in + ordered boosting         |
| **Overfitting control**  | Strong                   | Good (needs careful leaf tuning) | Strong                              |
| **GPU support**          | ✅ Yes                   | ✅ Yes                           | ✅ Yes (optimized)                  |
| **SHAP integration**     | ✅ Native                | ✅ Native                        | ✅ Native (highly optimized)        |
| **Kaggle dominance**     | ✅ Very strong           | ✅ Very strong                   | Moderate                            |
| **Production maturity**  | ✅ Excellent             | ✅ Excellent                     | ✅ Good                             |

### Decision Criteria — When to Use Each

**Use XGBoost when:**

- You need a robust, well-regularized baseline on any structured dataset
- The dataset is moderate size (up to ~10M rows with standard hardware)
- You want the most battle-tested, widely supported gradient boosting library
- Interpretability via SHAP is a requirement
- You are competing in Kaggle or benchmarking against literature

**Use LightGBM when:**

- Training speed is a hard constraint (large datasets, frequent retraining, production pipelines)
- Dataset exceeds tens of millions of rows — LightGBM's histogram-based algorithm handles this efficiently
- Memory is constrained — LightGBM uses significantly less RAM than XGBoost at scale
- Real-time or near-real-time model retraining is required
- You need fast hyperparameter search across many iterations

**Use CatBoost when:**

- The dataset contains many high-cardinality categorical features (e.g., user IDs, product codes, geographic codes)
- You want to eliminate manual encoding pipelines (`OrdinalEncoder`, `OneHotEncoder`, `TargetEncoder`) entirely
- Reducing data leakage risk is a priority — CatBoost's ordered boosting computes target statistics in a way that prevents the target leakage common in naive target encoding
- The dataset has mixed types (numeric + categorical) with minimal preprocessing budget
- SHAP explainability needs to be computed efficiently at scale

**Default recommendation**: When the task is tabular and you have no strong prior on
data characteristics, start with LightGBM (speed + scale) and CatBoost (if categoricals
are present), then validate against XGBoost as a regularization baseline.

### Standard Benchmarking Template

```python
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

# --- Constants ---
N_SPLITS: int = 5
RANDOM_STATE: int = 42
EVAL_METRIC: str = "roc_auc"


def benchmark_gradient_boosters(
    X: pd.DataFrame,
    y: pd.Series,
    categorical_features: list[str] | None = None,
) -> pd.DataFrame:
    """
    Benchmark XGBoost, LightGBM, and CatBoost with cross-validation.

    All three models are evaluated under identical CV folds to ensure
    fair comparison. CatBoost receives categorical feature indices
    directly; XGBoost and LightGBM receive ordinally-encoded data.

    Args:
        X: Feature matrix.
        y: Binary or multiclass target vector.
        categorical_features: Column names of categorical features.
            CatBoost handles these natively; others use ordinal encoding.

    Returns:
        DataFrame with mean and std CV AUC per model.
    """
    cat_cols: list[str] = categorical_features or []
    cat_indices: list[int] = [X.columns.get_loc(c) for c in cat_cols]

    # Encode categoricals for XGBoost and LightGBM
    X_encoded = X.copy()
    for col in cat_cols:
        X_encoded[col] = X_encoded[col].astype("category").cat.codes

    models: dict[str, Any] = {
        "XGBoost": XGBClassifier(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "LightGBM": LGBMClassifier(
            n_estimators=500,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbose=-1,
        ),
        "CatBoost": CatBoostClassifier(
            iterations=500,
            learning_rate=0.05,
            depth=6,
            cat_features=cat_indices if cat_indices else None,
            random_seed=RANDOM_STATE,
            verbose=0,
        ),
    }

    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    results: dict[str, list[float]] = {name: [] for name in models}

    for fold, (train_idx, val_idx) in enumerate(cv.split(X, y)):
        logger.info("Fold %d / %d", fold + 1, N_SPLITS)
        for name, model in models.items():
            X_tr = X_encoded if name != "CatBoost" else X
            model.fit(X_tr.iloc[train_idx], y.iloc[train_idx])
            y_prob = model.predict_proba(X_tr.iloc[val_idx])[:, 1]
            auc = roc_auc_score(y.iloc[val_idx], y_prob)
            results[name].append(auc)
            logger.info("  %s AUC: %.4f", name, auc)

    summary = pd.DataFrame({
        "Model": list(results.keys()),
        "Mean AUC": [np.mean(v) for v in results.values()],
        "Std AUC":  [np.std(v)  for v in results.values()],
    }).sort_values("Mean AUC", ascending=False).reset_index(drop=True)

    logger.info("Benchmark results:\n%s", summary.to_string())
    return summary
```

### Why Benchmark All Three (Not Just the Best-Known)

1. **No free lunch**: Data characteristics (cardinality, scale, missing rate, feature interactions) consistently shift which model wins. Assuming XGBoost or LightGBM is always best is an anti-pattern.
2. **CatBoost's leakage reduction** is a genuine algorithmic advantage, not a marketing claim. On datasets with many categoricals, CatBoost frequently outperforms the other two without any preprocessing.
3. **SHAP is equally native** across all three — there is no interpretability cost to using CatBoost or LightGBM over XGBoost.
4. **Pipeline simplification**: CatBoost's native categorical handling eliminates the `ColumnTransformer` + encoding step, which reduces code complexity and a common source of data leakage in ML pipelines.

---

## 4. Classification Metrics {#classification}

```python
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score,
    roc_curve, precision_recall_curve, average_precision_score,
    matthews_corrcoef, cohen_kappa_score, log_loss
)
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def evaluate_classifier(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: Optional[np.ndarray] = None,
    class_names: Optional[list[str]] = None
) -> dict:
    """
    Comprehensive classification evaluation.

    Args:
        y_true: Ground truth labels.
        y_pred: Predicted labels.
        y_prob: Predicted probabilities (for AUC, log loss).
        class_names: Optional display names for classes.

    Returns:
        Dictionary of all computed metrics.
    """
    report = classification_report(y_true, y_pred, target_names=class_names, output_dict=True)
    mcc = matthews_corrcoef(y_true, y_pred)
    kappa = cohen_kappa_score(y_true, y_pred)

    metrics = {
        "classification_report": report,
        "matthews_corrcoef": mcc,
        "cohen_kappa": kappa,
    }

    if y_prob is not None:
        is_binary = y_prob.ndim == 1 or y_prob.shape[1] == 2
        proba = y_prob[:, 1] if (y_prob.ndim == 2 and is_binary) else y_prob
        metrics["roc_auc"] = roc_auc_score(y_true, proba, multi_class="ovr" if not is_binary else "raise")
        metrics["log_loss"] = log_loss(y_true, y_prob)
        metrics["average_precision"] = average_precision_score(y_true, proba) if is_binary else None

    logger.info("Evaluation complete: AUC=%.4f, MCC=%.4f, Kappa=%.4f",
                metrics.get("roc_auc", 0), mcc, kappa)
    return metrics


def plot_confusion_matrix(y_true, y_pred, class_names=None) -> None:
    """Normalized + raw confusion matrix side by side."""
    cm = confusion_matrix(y_true, y_pred)
    cm_norm = cm.astype(float) / cm.sum(axis=1)[:, np.newaxis]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, data, fmt, title in zip(
        axes, [cm, cm_norm], ["d", ".2%"], ["Raw Counts", "Normalized"]
    ):
        sns.heatmap(data, annot=True, fmt=fmt, cmap="Blues",
                    xticklabels=class_names, yticklabels=class_names, ax=ax)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        ax.set_title(f"Confusion Matrix — {title}")
    plt.tight_layout()
    plt.show()


def plot_roc_curve(y_true, y_prob) -> None:
    """ROC curve with AUC annotation."""
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    auc = roc_auc_score(y_true, y_prob)
    plt.figure(figsize=(8, 6))
    plt.plot(fpr, tpr, label=f"ROC AUC = {auc:.4f}", linewidth=2)
    plt.plot([0, 1], [0, 1], "k--", linewidth=1)
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curve")
    plt.legend()
    plt.tight_layout()
    plt.show()
```

---

## 5. Regression Metrics {#regression}

```python
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    mean_absolute_percentage_error
)
import numpy as np
import matplotlib.pyplot as plt


def evaluate_regressor(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    Comprehensive regression evaluation.

    Returns:
        Dictionary with MAE, RMSE, MAPE, R², adjusted R².
    """
    n = len(y_true)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = mean_absolute_percentage_error(y_true, y_pred) * 100
    r2 = r2_score(y_true, y_pred)

    return {
        "MAE": mae,
        "RMSE": rmse,
        "MAPE (%)": mape,
        "R2": r2,
        "n_samples": n
    }


def plot_residuals(y_true: np.ndarray, y_pred: np.ndarray) -> None:
    """Residual plot + distribution of errors."""
    residuals = y_true - y_pred
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    axes[0].scatter(y_pred, residuals, alpha=0.5)
    axes[0].axhline(0, color="red", linestyle="--")
    axes[0].set(xlabel="Predicted", ylabel="Residuals", title="Residuals vs Predicted")

    import seaborn as sns
    sns.histplot(residuals, kde=True, ax=axes[1])
    axes[1].set_title("Residual Distribution")

    from scipy import stats
    stats.probplot(residuals, plot=axes[2])
    axes[2].set_title("Q-Q Plot")
    plt.tight_layout()
    plt.show()
```

---

## 6. Clustering Metrics {#clustering}

```python
from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score
import numpy as np
import matplotlib.pyplot as plt


def evaluate_clustering(X: np.ndarray, labels: np.ndarray) -> dict:
    """
    Evaluate clustering quality using internal validation indices.

    Note: These metrics assume no ground truth is available.
    Higher Calinski-Harabasz = better. Lower Davies-Bouldin = better.
    Silhouette in [-1, 1]; closer to 1 = better.
    """
    return {
        "silhouette_score": silhouette_score(X, labels),
        "davies_bouldin_score": davies_bouldin_score(X, labels),
        "calinski_harabasz_score": calinski_harabasz_score(X, labels),
        "n_clusters": len(set(labels)) - (1 if -1 in labels else 0)
    }


def plot_elbow_curve(inertias: list[float], k_range: range) -> None:
    """Plot elbow curve for K-Means cluster selection."""
    plt.figure(figsize=(8, 5))
    plt.plot(list(k_range), inertias, marker="o", linewidth=2)
    plt.xlabel("Number of Clusters (k)")
    plt.ylabel("Inertia (Within-Cluster SSE)")
    plt.title("Elbow Method for Optimal k")
    plt.tight_layout()
    plt.show()
```

---

## 7. Model Explainability {#explainability}

```python
import shap
import matplotlib.pyplot as plt
import numpy as np


def shap_summary(model, X_train, X_test=None, model_type: str = "tree") -> None:
    """
    SHAP summary plot for feature importance.

    Args:
        model_type: 'tree' (sklearn/XGBoost), 'linear', or 'kernel' (model-agnostic)
    """
    explainer_map = {
        "tree": shap.TreeExplainer,
        "linear": shap.LinearExplainer,
        "kernel": lambda m: shap.KernelExplainer(m.predict, shap.sample(X_train, 100))
    }
    explainer = explainer_map[model_type](model)
    shap_values = explainer.shap_values(X_test if X_test is not None else X_train)
    shap.summary_plot(shap_values, X_test if X_test is not None else X_train)
    plt.tight_layout()
    plt.show()
```

---

## 8. Evaluation Checklist {#checklist}

Before finalizing any model evaluation, verify:

**Data Leakage**

- [ ] No target-derived features in the feature set
- [ ] Train/test split performed BEFORE any preprocessing fitted on training data only
- [ ] No temporal leakage in time series (always use walk-forward validation)

**Class Imbalance**

- [ ] Check class distribution in train and test sets
- [ ] Report precision, recall, F1 per class — not just accuracy
- [ ] Consider SMOTE, class weighting, or threshold tuning if imbalanced

**Statistical Validity**

- [ ] Cross-validation strategy matches problem type (Stratified K-Fold for classification)
- [ ] Report confidence intervals on key metrics (use bootstrap if needed)
- [ ] Perform paired statistical tests when comparing models (Wilcoxon signed-rank)

**Business Interpretation**

- [ ] Translate metrics into business impact (cost of false positives vs. false negatives)
- [ ] Document model limitations and failure modes
- [ ] Specify monitoring strategy for production deployment
