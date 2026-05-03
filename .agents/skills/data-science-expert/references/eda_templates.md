# EDA Templates Reference

## Table of Contents

0. [Environment Setup (uv)](#environment)
1. [Tabular / Flat File EDA](#tabular)
2. [Time Series EDA](#time-series)
3. [Text / NLP EDA](#nlp)
4. [Image Data EDA](#image)
5. [SQL-Based EDA](#sql)

---

## 0. Environment Setup (uv) {#environment}

```bash
uv init eda_project && cd eda_project
uv python pin 3.12
uv venv .venv --python 3.12 && source .venv/bin/activate

# Core EDA stack
uv add pandas polars numpy scipy statsmodels \
       matplotlib seaborn plotly bokeh altair \
       ydata-profiling scikit-learn ipykernel jupyterlab

# Dev tools
uv add --dev ruff mypy pytest
uv sync
```

## 1. Tabular / Flat File EDA {#tabular}

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

```python
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.seasonal import seasonal_decompose
import logging

logger = logging.getLogger(__name__)


def check_stationarity(series: pd.Series, significance: float = 0.05) -> dict:
    """
    Augmented Dickey-Fuller test for stationarity.

    Args:
        series: Time series values.
        significance: Alpha level for hypothesis test.

    Returns:
        Dictionary with ADF statistic, p-value, and stationarity conclusion.
    """
    result = adfuller(series.dropna())
    is_stationary = result[1] < significance
    output = {
        "adf_statistic": result[0],
        "p_value": result[1],
        "is_stationary": is_stationary,
        "conclusion": "Stationary" if is_stationary else "Non-stationary (differencing recommended)"
    }
    logger.info("ADF Test: %s", output)
    return output


def decompose_series(series: pd.Series, model: str = "additive", period: int = 12) -> None:
    """
    Seasonal decomposition: trend, seasonal, residual components.

    Args:
        model: 'additive' or 'multiplicative'
        period: Seasonal period (e.g., 12 for monthly data)
    """
    decomposition = seasonal_decompose(series.dropna(), model=model, period=period)
    decomposition.plot()
    plt.suptitle("Seasonal Decomposition", y=1.02)
    plt.tight_layout()
    plt.show()
```

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
