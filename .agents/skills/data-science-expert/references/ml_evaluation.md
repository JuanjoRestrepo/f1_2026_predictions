# ML Model Evaluation Reference

## Table of Contents

0. [Environment Setup (uv)](#environment)
1. [ML Algorithm Taxonomy — Selection Reference](#algorithm-taxonomy)
2. [Gradient Boosting Selection Guide — XGBoost vs LightGBM vs CatBoost](#gbm-guide)
3. [Classification Metrics](#classification)
4. [Regression Metrics](#regression)
5. [Clustering Metrics](#clustering)
6. [Model Explainability](#explainability)
7. [Evaluation Checklist](#checklist)

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

## 1. ML Algorithm Taxonomy — Selection Reference {#algorithm-taxonomy}

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

| Algorithm                     | Key Characteristics                                           | When to Use                                                        |
| ----------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
| K-Means                       | Centroid-based; assumes spherical clusters; requires k        | Well-separated, roughly equal-sized clusters; large datasets       |
| DBSCAN                        | Density-based; finds arbitrary shapes; detects noise/outliers | Irregular cluster shapes; unknown number of clusters; spatial data |
| Hierarchical Clustering       | Builds a dendrogram; no k required; deterministic             | Small datasets; cluster hierarchy matters; interpretability needed |
| Gaussian Mixture Models (GMM) | Probabilistic; soft assignments; assumes Gaussian components  | Overlapping clusters; probabilistic cluster membership needed      |

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

### Algorithm Selection Decision Logic

Apply this as Step 1 of the Workflow Decision Logic defined in SKILL.md:

```
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
   See Section 2 (GBM Selection Guide) for detailed criteria.
```

---

## 2. Gradient Boosting Selection Guide — XGBoost vs LightGBM vs CatBoost {#gbm-guide}

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

## 2. Regression Metrics {#regression}

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

## 3. Clustering Metrics {#clustering}

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

## 4. Model Explainability {#explainability}

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

## 5. Evaluation Checklist {#checklist}

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
