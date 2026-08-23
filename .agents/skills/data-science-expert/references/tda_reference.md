# Topological Data Analysis (TDA)

> **References**: Edelsbrunner, H., & Harer, J. (2010). _Computational Topology: An
> Introduction_. AMS. · Carlsson, G. (2009). Topology and data. _Bulletin of the AMS_,
> 46(2), 255–308. · Cohen-Steiner, D., Edelsbrunner, H., & Harer, J. (2007). Stability
> of persistence diagrams. _Discrete & Computational Geometry_, 37(1), 103–120. ·
> Takens, F. (1981). Detecting strange attractors in turbulence. _Lecture Notes in
> Mathematics_, 898, 366–381. · Tauzin, G., et al. (2021). giotto-tda: A topological
> data analysis toolkit for machine learning and data exploration. _JMLR_, 22(39).

## Table of Contents

1. [What is TDA and When to Use It](#what-is-tda)
2. [Mathematical Foundations — Simplicial Complexes and Homology](#math-foundations)
3. [Persistent Homology — Theory](#persistent-homology)
4. [Stability Theorem and Statistical Foundations](#stability)
5. [TDA for Time Series — Takens Embedding and Periodicity](#time-series)
6. [Higher-Order TDA — Simplicial Complexes and Sheaves](#higher-order)
7. [Persistence-Based ML — Topological Features for Models](#ml-features)
8. [Implementation with giotto-tda](#implementation)
9. [Applications in Data Science](#applications)
10. [References](#references)

---

## 1. What is TDA and When to Use It {#what-is-tda}

Topological Data Analysis studies the **shape** of data — global geometric and
topological structure that persists across scales. Where statistics asks "what are
the mean and variance?", TDA asks "does the data have holes, loops, or voids? At
what scale do they appear, and how long do they persist?"

**Core principle** (Carlsson, 2009): topological features — connected components,
loops, voids — that persist across a wide range of scales are signal; features that
appear briefly are noise. This gives TDA natural robustness to noise and deformation.

### When TDA is the right tool

| Data scenario                                 | TDA detects                                 | Alternative would miss                           |
| --------------------------------------------- | ------------------------------------------- | ------------------------------------------------ |
| Periodic time series                          | Persistent H₁ loop (1-cycle)                | FFT detects only stationary periodicity          |
| Multimodal point cloud                        | Persistent H₀ components                    | Gaussian mixture requires assumed k              |
| Branching structures (phylogeny, vasculature) | H₀ tree topology                            | Clustering requires metric assumption            |
| Molecular geometry (drugs, proteins)          | Ring systems, voids via H₁, H₂              | Fingerprint methods miss 3D topology             |
| Brain connectivity (fMRI, EEG)                | Persistent loops in functional connectivity | Correlation ignores higher-order structure       |
| Market contagion networks                     | Topological phase transitions               | Pairwise correlation misses global topology      |
| Anomaly detection                             | Points that change the diagram              | Distance-based methods miss topological outliers |

### When TDA is NOT the right tool

- The data has no geometric or relational structure (purely tabular, independent rows)
- You need point-level predictions (TDA produces global/shape-level summaries)
- Interpretability of individual features is required and topology is unintuitive to stakeholders
- The dataset is very small (n < 50): persistence diagrams become unstable

---

## 2. Mathematical Foundations — Simplicial Complexes and Homology {#math-foundations}

### Simplicial Complexes

A **simplex** is the convex hull of a set of affinely independent points:

```
0-simplex: a point (vertex)
1-simplex: a line segment (edge)
2-simplex: a filled triangle (face)
3-simplex: a filled tetrahedron
k-simplex: [v₀, v₁, ..., v_k]  (k+1 vertices)
```

A **simplicial complex** K is a finite collection of simplices such that:

1. If σ ∈ K and τ is a face of σ (τ ≤ σ), then τ ∈ K
2. If σ, τ ∈ K, then σ ∩ τ is either empty or a face of both

Simplicial complexes are the combinatorial structures on which topological features
are measured. They generalize graphs: a graph is a 1-dimensional simplicial complex
(vertices + edges); TDA extends this to higher dimensions.

### Boundary Operators

The boundary operator ∂_k maps k-simplices to their (k−1)-dimensional faces:

```
∂_k[v₀, v₁, ..., v_k] = Σ_{i=0}^{k} (−1)^i [v₀, ..., v̂_i, ..., v_k]
```

where v̂_i means vertex i is omitted, and the signs (−1)^i encode orientation.

**Fundamental property**: ∂\_{k−1} ∘ ∂_k = 0 (boundary of boundary = 0).
This is the algebraic foundation of homology.

Examples:

```
∂₁[v₀, v₁] = v₁ − v₀              (edge boundary = head − tail)
∂₂[v₀, v₁, v₂] = [v₁,v₂] − [v₀,v₂] + [v₀,v₁]   (triangle boundary = 3 edges)
```

### Homology Groups

The k-th chain group C_k is the vector space (over F₂ = {0,1} or R) generated by
the k-simplices of K.

**k-cycles**: Z*k = ker(∂_k) — chains with no boundary (closed loops)
**k-boundaries**: B_k = im(∂*{k+1}) — chains that are boundaries of higher simplices
Since ∂² = 0: B_k ⊆ Z_k

**k-th homology group**: H*k = Z_k / B_k = ker(∂_k) / im(∂*{k+1})

Intuition: H_k counts k-dimensional "holes" that are cycles (∂ = 0) but not
the boundary of anything (they are not "filled in").

```
H₀:  connected components — β₀ = number of connected components
H₁:  independent loops / 1-cycles — β₁ = number of independent loops
H₂:  enclosed voids / 2-cavities — β₂ = number of enclosed 3D voids
H_k: k-dimensional holes
```

**Betti numbers**: β_k = rank(H_k) = dim(H_k) over F₂ or R

Examples:

```
Point:               β₀=1, β₁=0, β₂=0
Line segment:        β₀=1, β₁=0, β₂=0  (no loops)
Circle S¹:           β₀=1, β₁=1, β₂=0  (one loop)
Sphere S²:           β₀=1, β₁=0, β₂=1  (one void)
Torus T²:            β₀=1, β₁=2, β₂=1  (two independent loops, one void)
Klein bottle:        β₀=1, β₁=2, β₂=0  (non-orientable — no void)
```

---

## 3. Persistent Homology — Theory {#persistent-homology}

### Filtrations

A **filtration** of a simplicial complex K is a nested sequence:

```
∅ = K₀ ⊆ K₁ ⊆ K₂ ⊆ ... ⊆ K_m = K
```

As simplices are added to the complex at increasing parameter values ε₁ ≤ ε₂ ≤ ...,
topological features appear (are "born") and disappear (are "killed").

### Vietoris-Rips Filtration

Given a finite point cloud X ⊂ R^d and a scale parameter ε > 0:

```
VR(X, ε) = {σ = [x₀,...,x_k] ⊆ X : d(x_i, x_j) ≤ ε  ∀ i, j}
```

A k-simplex is added when all pairwise distances between its vertices are ≤ ε.

**Filtration property**: VR(X, ε₁) ⊆ VR(X, ε₂) for ε₁ ≤ ε₂ — the complex
grows monotonically. This creates the filtration as ε increases from 0 to ∞.

**Computational note**: building the full Vietoris-Rips complex is expensive for
large n (O(n^k) k-simplices). In practice:

- Use the **Rips approximation** (build up to dimension 2 or 3)
- Or use **Alpha complexes** for point clouds in R^d ≤ 3 (more efficient)

### Persistence: Birth and Death

As ε increases through the filtration, homological features undergo:

- **Birth** at ε = b: a new feature (connected component, loop, void) appears that
  was not the boundary of anything in the previous complex
- **Death** at ε = d: the feature is "filled in" — it becomes a boundary of a
  higher-dimensional simplex added at ε = d, and is no longer an independent cycle

**Persistence** of a feature: pers = d − b (lifetime in the filtration)

### Persistence Diagrams

The **k-th persistence diagram** dgm_k is the multiset of birth-death pairs:

```
dgm_k = {(b_i, d_i) : i = 1, ..., m_k}  ∪  {(b, b) : b ∈ R}  (diagonal copy)
```

- Each point (b_i, d_i) lies strictly above the diagonal: d_i > b_i
- The diagonal {(b, b)} represents ephemeral (zero-persistence) features
- Points far from the diagonal = persistent features = signal
- Points near the diagonal = low-persistence features = noise

**Persistence barcodes**: equivalent representation as horizontal bars [b_i, d_i]
on the ε-axis — long bars are persistent features, short bars are noise.

### Reading a Persistence Diagram

```
death
  │
  │          ✦ ← persistent H₁ loop (periodicity / real structure)
  │
  │   ·  · ← near-diagonal: noise
  │ · ·
  └──────────────── birth
```

- A prominent point far from the diagonal in dgm₁ indicates a **persistent loop**
  — strongly suggests periodicity or a circular structure in the data
- Multiple well-separated points in dgm₀ indicate **multiple clusters**
- A point far from the diagonal in dgm₂ indicates a **persistent void**

---

## 4. Stability Theorem and Statistical Foundations {#stability}

### Cohen-Steiner Stability Theorem (2007)

Let f, g: K → R be two tame functions on the same simplicial complex K.
Define the bottleneck distance between persistence diagrams:

```
d_B(dgm(f), dgm(g)) = inf_γ  sup_{x ∈ dgm(f)} ‖x − γ(x)‖_∞
```

where γ ranges over all bijections between dgm(f) and dgm(g)
(diagonal points are included to handle diagrams of different sizes).

**Stability theorem**:

```
d_B(dgm(f), dgm(g)) ≤ ‖f − g‖_∞
```

**Interpretation**: if two functions differ by at most δ everywhere, then their
persistence diagrams differ by at most δ in bottleneck distance. Small perturbations
in data → small perturbations in the persistence diagram.

This is the foundational result that makes TDA statistically meaningful: persistence
diagrams are robust to noise, missing data, and small deformations.

### Wasserstein Distance

For comparing persistence diagrams in ML pipelines (computing losses):

```
d_W^p(dgm₁, dgm₂) = (inf_γ Σ_x ‖x − γ(x)‖_∞^p)^(1/p)
```

d_W^2 (2-Wasserstein) is differentiable w.r.t. birth/death coordinates —
enabling gradient-based optimization of topological objectives.

### Statistical Testing with TDA

**Permutation test for topological significance**:

1. Compute dgm_k(X) for the observed data
2. Randomly permute labels or shuffle coordinates N = 1000 times
3. Compute dgm_k(X^(π)) for each permutation
4. P-value = fraction of permutations with larger maximum persistence than observed
5. Reject H₀ (no structure) if p < α

**Bootstrap confidence intervals** for persistence:
Resample the point cloud with replacement B times; compute dgm_k for each;
construct empirical distribution of persistence values. Features whose 95% CI
of persistence lies above the noise threshold are statistically significant.

---

## 5. TDA for Time Series — Takens Embedding and Periodicity {#time-series}

### Takens' Delay Embedding Theorem (1981)

A scalar time series x: T → R observed from a d_box-dimensional dynamical system
can be reconstructed as a smooth manifold in R^d using the delay map:

```
Φ_{τ,d}: R → R^d
x(t) ↦ (x(t), x(t+τ), x(t+2τ), ..., x(t+(d−1)τ))
```

**Takens' theorem**: for generic (f, τ), Φ\_{f,τ} is a smooth embedding
(diffeomorphism onto its image) when d ≥ 2 d_box + 1.

The image Φ(T) ⊂ R^d is a **point cloud** that encodes the topology of the
underlying dynamical attractor. A periodic orbit (cycle) becomes a loop (S¹) in R^d.

**Parameter selection**:

```
Delay τ:     choose τ such that autocorrelation(τ) ≈ 0
             OR  first minimum of the Average Mutual Information (AMI)
             τ ≈ T_period / 4  for periodic signals

Dimension d: minimum d such that the point cloud has no false nearest neighbors
             for periodic signals, d = 2 or d = 3 is typically sufficient
             Cao's method: increase d until the fraction of false nearest neighbors ≈ 0
```

### TDA-Based Periodicity Detection — 5-Step Pipeline

```
Step 1 — Time series x(t)
  Raw signal: x(t), t = 0, 1, ..., T_obs
  Preprocessing: detrend, normalize to zero mean unit variance

Step 2 — Point cloud via delay embedding
  PC = {(x(t), x(t+τ)) : t = 0, ..., T_obs − τ}  ∈ R²
  For a periodic signal with period T_period:
    the delay embedding traces a closed loop (circle) if τ = T_period/4

Step 3 — Vietoris-Rips filtration on PC
  Build VR(PC, ε) for ε ∈ [0, ε_max]
  Track birth and death of H₀ (components) and H₁ (loops)
  as ε increases from 0 to ε_max

Step 4 — Persistence diagram dgm₁
  Plot all (birth, death) pairs for H₁ (1-cycles / loops)
  A point far from the diagonal = persistent loop = periodicity present

Step 5 — Conclusion
  pers(σ*) = d* − b* >> noise level  ⟹  periodicity confirmed
  The ratio pers(σ*) / (max over diagonal noise) is the signal-to-noise ratio
```

### Why TDA detects periodicity better than FFT in some regimes

| Criterion                | FFT                                   | TDA (persistent H₁)                    |
| ------------------------ | ------------------------------------- | -------------------------------------- |
| Stationary requirement   | Requires stationarity                 | No stationarity assumption             |
| Noise robustness         | Sensitive to impulse noise            | Robust (stability theorem)             |
| Multi-period signals     | Identifies all periods simultaneously | Identifies dominant cycle topology     |
| Quasi-periodic signals   | Produces smeared spectrum             | Detects approximate loop structure     |
| Short, noisy segments    | Poor spectral resolution              | Topology persists even with few points |
| Non-sinusoidal waveforms | Full Fourier basis needed             | Shape-agnostic                         |

**Limitations**: TDA periodicity detection is computationally heavier than FFT
(O(n³) in the worst case for VR filtration). For long stationary signals where FFT
is applicable, FFT is faster and more interpretable. TDA excels on short, noisy, or
non-stationary time series from physiological signals, financial data, or ICU monitoring.

---

## 6. Higher-Order TDA — Simplicial Complexes and Sheaves {#higher-order}

### Beyond H₁: Higher-Dimensional Topological Features

Standard persistent homology captures up to H₁ (loops) in most applications.
Higher-order TDA captures structure at dimension k > 1:

- **H₂**: enclosed voids — relevant in protein binding cavities, drug discovery
- **H₃+**: increasingly rare in practice; relevant in cosmological data (3D voids)

For cognitive networks and functional brain data (working memory, feedback circuits),
the relevant structure is in H₁ (feedback loops) and possibly H₂ (coordinated cycles).

### Clique Complexes and Weighted Networks

For a weighted graph G = (V, E, w): build the clique complex (flag complex)
where every clique of size k+1 fills in a k-simplex. This allows extracting
higher-order topological structure from network data (e.g., financial networks,
brain connectivity matrices, social networks).

```
Clique filtration:
  Add edge (u,v) when weight w_uv ≥ ε (threshold filtration)
  Add triangle [u,v,w] when all three edges w ≥ ε
  Add tetrahedron when all six edges w ≥ ε
  → persistence diagram captures which cliques are long-lived vs. transient
```

**Application to market contagion** (research agenda): compute the clique complex
on correlation networks of Latin American emerging market assets. Persistent H₁ loops
indicate groups of assets that maintain correlated cycles. Changes in the persistence
diagram (topological phase transitions) serve as early-warning indicators of contagion
before classical pairwise correlation measures detect them.

### Simplicial Complexes for High-Order Interactions

Standard graphs model pairwise interactions. Many systems (neuroscience,
social networks, drug combinations) have k-way interactions for k > 2.
Simplicial complexes natively represent k-way interactions as k-simplices.

**Hodge Laplacian on simplicial complexes**:

```
L_k = B_k^T B_k + B_{k+1} B_{k+1}^T
```

where B_k is the incidence matrix between (k−1)-simplices and k-simplices.
L_0 is the standard graph Laplacian. L_1 is the edge Laplacian — its harmonic
space (ker(L_1)) corresponds exactly to H₁ (independent cycles in the graph).

The Hodge decomposition theorem states that any k-chain decomposes into:

```
C_k = im(B_{k+1}) ⊕ im(B_k^T) ⊕ ker(L_k)
       (boundaries)  (coboundaries)  (harmonic — topology)
```

This is the foundation of Topological Signal Processing on simplicial complexes —
generalizing graph signal processing from nodes to edges, triangles, and beyond.

### Sheaves on Graphs and Simplicial Complexes

A **cellular sheaf** assigns vector spaces (stalks) to vertices, edges, and faces
of a complex, with linear restriction maps between them. The sheaf Laplacian
L_F generalizes both the graph Laplacian and Hodge Laplacian.

**Application**: cognitive networks (working memory feedback circuits). Assign
neural activity vectors to brain regions (vertices); restriction maps encode how
signals propagate along connections (edges). The sheaf cohomology H⁰(F) captures
globally consistent patterns across the network — the mathematical formalization
of "coordinated activity across brain regions."

This is a frontier research area. Libraries: `PySheavesX` (research), `coboundary`
(experimental). Not yet in production ML pipelines.

---

## 7. Persistence-Based ML — Topological Features for Models {#ml-features}

Topological features extracted from persistence diagrams can be used as input
to standard ML models (GBM, SVM, neural networks).

### Feature Extraction Methods

**Betti curves**: for each dimension k, the Betti curve β_k(ε) counts the number
of persistent features alive at scale ε:

```
β_k(ε) = |{i : b_i ≤ ε < d_i}|
```

Discretize over a grid of ε values → finite-dimensional feature vector.

**Persistence landscapes** (Bubenik, 2015): a functional summary of the persistence
diagram, defined as a sequence of piecewise-linear functions λ_k: R → R.
Persistence landscapes lie in a Hilbert space — enabling computation of means,
variances, and statistical tests on persistence diagrams.

**Persistence entropy**:

```
H(dgm) = −Σᵢ pᵢ log pᵢ    where pᵢ = pers(σᵢ) / Σⱼ pers(σⱼ)
```

Measures the complexity / disorder of the topological structure. Highly periodic
signals have low entropy (one dominant feature); noisy signals have high entropy.

**Persistence images** (Adams et al., 2017): map the persistence diagram to a
2D grayscale image by placing a Gaussian kernel at each (b, d) point:

```
ρ_σ(z) = Σᵢ pers(σᵢ) · N(z; pᵢ, σ²)
```

Discretize to a grid → flatten to a feature vector. Compatible with CNNs.

### Topological Loss for Neural Networks

For learning tasks where topological structure is the objective (e.g., segmenting
cells in microscopy where each cell should correspond to one connected component):

**Topological loss** (Hu et al., 2019):

```
L_topo = Σ_{σᵢ ∈ critical pairs} ‖pers(σᵢ) − pers*(σᵢ)‖²
```

where pers\*(σᵢ) is the target persistence (e.g., 0 for noise, max for signal).
The gradient of L_topo w.r.t. the network output is well-defined via the
implicit function theorem — enabling end-to-end training with topological objectives.

---

## 8. Implementation with giotto-tda {#implementation}

### Environment Setup

```bash
uv init tda_project && cd tda_project
uv python pin 3.12
uv venv .venv --python 3.12 && source .venv/bin/activate

uv add gtda scikit-learn numpy scipy matplotlib plotly
uv add ripser persim gudhi    # Lower-level alternatives to gtda

uv add --dev ruff mypy pytest
uv sync
```

### Complete TDA Pipeline for Time Series Periodicity Detection

```python
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
from gtda.time_series import SingleTakensEmbedding, TakensEmbedding
from gtda.homology import VietorisRipsPersistence
from gtda.diagrams import (
    PersistenceEntropy,
    BettiCurve,
    PersistenceLandscape,
    Scaler,
)
from gtda.plotting import plot_diagram
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

# --- Constants ---
HOMOLOGY_DIMENSIONS: list[int] = [0, 1, 2]   # H₀, H₁, H₂
MAX_EDGE_LENGTH: float = 2.0                   # ε_max for Vietoris-Rips
N_JOBS: int = -1                               # Use all CPU cores


def detect_periodicity(
    time_series: np.ndarray,
    tau: int | None = None,
    embedding_dimension: int = 2,
    persistence_threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Detect periodicity in a time series via Takens embedding + persistent H₁.

    Pipeline:
    1. Delay embedding: time series → point cloud in R^d
    2. Vietoris-Rips filtration: point cloud → filtration
    3. Persistent homology: filtration → persistence diagram (dgm₁)
    4. Decision: persistent H₁ loop far from diagonal → periodicity

    Args:
        time_series: 1D array of signal values, shape (T,)
        tau: delay parameter. If None, estimated from first AMI minimum.
        embedding_dimension: d in the delay map. Use 2 for periodic signals.
        persistence_threshold: minimum persistence (d - b) to consider a feature
                               significant (noise floor heuristic).

    Returns:
        Dictionary with persistence diagram, Betti curve, and periodicity decision.
    """
    # Normalize
    x = (time_series - time_series.mean()) / (time_series.std() + 1e-8)

    # Estimate tau if not provided (first zero of autocorrelation)
    if tau is None:
        acf = np.correlate(x, x, mode="full")[len(x) - 1:]
        acf /= acf[0]
        zero_crossings = np.where(np.diff(np.sign(acf)))[0]
        tau = int(zero_crossings[0]) if len(zero_crossings) > 0 else len(x) // 8
        logger.info("Estimated delay tau = %d", tau)

    # Step 1: Takens delay embedding → point cloud shape (n_windows, d)
    embedder = SingleTakensEmbedding(
        parameters_type="fixed",
        time_delay=tau,
        dimension=embedding_dimension,
        n_jobs=N_JOBS,
    )
    # gtda expects shape (1, T) for single time series
    X = x.reshape(1, -1)
    X_embedded = embedder.fit_transform(X)   # shape: (1, n_windows, d)
    logger.info("Embedded shape: %s", X_embedded.shape)

    # Step 2 & 3: Vietoris-Rips persistent homology
    vr = VietorisRipsPersistence(
        metric="euclidean",
        homology_dimensions=HOMOLOGY_DIMENSIONS,
        max_edge_length=MAX_EDGE_LENGTH,
        n_jobs=N_JOBS,
    )
    diagrams = vr.fit_transform(X_embedded)  # shape: (1, n_points, 3) [birth, death, dim]

    # Extract H₁ features (dim = 1)
    h1_features = diagrams[0][diagrams[0, :, 2] == 1]   # (b, d, 1) for H₁
    h1_persistence = h1_features[:, 1] - h1_features[:, 0]   # d - b

    # Step 4: Periodicity decision
    max_h1_persistence = float(h1_persistence.max()) if len(h1_persistence) > 0 else 0.0
    is_periodic = max_h1_persistence > persistence_threshold

    result = {
        "diagram": diagrams[0],
        "h1_persistence": h1_persistence,
        "max_h1_persistence": max_h1_persistence,
        "is_periodic": is_periodic,
        "tau": tau,
        "embedding_dimension": embedding_dimension,
    }

    logger.info(
        "Max H₁ persistence: %.4f (threshold: %.4f) → periodic: %s",
        max_h1_persistence, persistence_threshold, is_periodic
    )
    return result


def extract_topological_features(
    diagrams: np.ndarray,
) -> dict[str, np.ndarray]:
    """
    Extract ML-ready topological features from persistence diagrams.

    Computes Betti curves, persistence entropy, and persistence landscapes —
    all of which can be used as feature vectors in downstream ML models.

    Args:
        diagrams: Output of VietorisRipsPersistence, shape (n_samples, n_points, 3)

    Returns:
        Dictionary of feature arrays, each shape (n_samples, n_features).
    """
    # Scale diagrams to [0, 1] for comparability
    scaler = Scaler()
    diagrams_scaled = scaler.fit_transform(diagrams)

    # Betti curves: β_k(ε) over a discretized ε grid
    betti = BettiCurve(n_bins=100, n_jobs=N_JOBS)
    betti_features = betti.fit_transform(diagrams_scaled)   # (n_samples, n_bins, n_dims)

    # Persistence entropy: scalar complexity per dimension
    entropy = PersistenceEntropy(normalize=True, n_jobs=N_JOBS)
    entropy_features = entropy.fit_transform(diagrams_scaled)  # (n_samples, n_dims)

    # Persistence landscapes: functional summary in Hilbert space
    landscape = PersistenceLandscape(n_layers=5, n_bins=100, n_jobs=N_JOBS)
    landscape_features = landscape.fit_transform(diagrams_scaled)

    return {
        "betti_curves": betti_features,
        "entropy": entropy_features,
        "landscapes": landscape_features,
    }


def build_tda_ml_pipeline() -> Pipeline:
    """
    scikit-learn Pipeline combining TDA feature extraction with a classifier.
    Suitable for time series classification tasks using topological features.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from gtda.time_series import SingleTakensEmbedding
    from gtda.homology import VietorisRipsPersistence
    from gtda.diagrams import PersistenceEntropy, Scaler
    from gtda.pipeline import Pipeline as GtdaPipeline

    return GtdaPipeline([
        ("embedder", SingleTakensEmbedding(parameters_type="search")),
        ("vr",       VietorisRipsPersistence(homology_dimensions=[0, 1])),
        ("scaler",   Scaler()),
        ("entropy",  PersistenceEntropy(normalize=True)),
        ("clf",      GradientBoostingClassifier(n_estimators=200, max_depth=4)),
    ])
```

### Direct Ripser Interface (Faster for Point Clouds)

```python
from ripser import ripser
from persim import plot_diagrams
import numpy as np


def compute_persistent_homology(
    point_cloud: np.ndarray,
    max_dim: int = 2,
    max_eps: float = 2.0,
) -> dict[str, np.ndarray]:
    """
    Compute persistent homology directly via ripser (faster than giotto-tda for
    standalone point cloud inputs).

    Args:
        point_cloud: Array of shape (n_points, d) — the embedded point cloud.
        max_dim: Maximum homology dimension to compute (0=H₀, 1=H₁, 2=H₂).
        max_eps: Maximum filtration value.

    Returns:
        Dictionary mapping dimension k → array of (birth, death) pairs.
    """
    result = ripser(point_cloud, maxdim=max_dim, thresh=max_eps)
    diagrams = result["dgms"]

    return {
        f"H{k}": dgm for k, dgm in enumerate(diagrams)
        if not np.all(np.isinf(dgm))
    }


def plot_persistence_diagram(diagrams: list[np.ndarray], title: str = "") -> None:
    """Visualize persistence diagrams using persim."""
    plot_diagrams(diagrams, title=title)
    plt.tight_layout()
    plt.show()
```

---

## 9. Applications in Data Science {#applications}

### Clinical Biomarkers and Physiological Signals

**Fetal heart rate variability (HRV)**: HRV time series from fetal CTG monitoring
embed as near-circular point clouds when normal (periodic cardiac rhythm). Pathological
patterns (hypoxia, distress) alter the topology: H₁ persistence drops, H₀ components
fragment. TDA detects these topological changes before conventional HRV metrics.

**ICU signal monitoring**: multivariate physiological signals (ECG, SpO₂, ICP)
modeled as trajectories in phase space. Topological changes in the trajectory
(H₁ birth/death transitions) precede clinical deterioration events by minutes.

**Reference**: Gidea, M., & Katz, Y. (2018). Topological data analysis of financial
time series: Landscapes of crashes. _Physica A_, 491, 820–834. (Methodology
applicable to physiological signals.)

### Financial Networks and Market Contagion

Model asset return correlations as a weighted graph; build clique complex filtration.
Persistent H₁ loops in the clique complex correspond to correlated cycles among
asset groups. A topological phase transition — abrupt change in the persistence
diagram — precedes market crashes and regional contagion events.

**Ollivier-Ricci curvature** on the correlation network: negative curvature on
edges ↔ bottleneck / information flow concentration → early warning of cascade
failure. Combines with TDA via the Ricci flow framework.

### Drug Discovery and Molecular Science

Molecules represented as atom graphs (atoms = nodes, bonds = edges). The topology
of the molecular graph (ring systems = H₁ loops; cage structures = H₂ voids)
correlates with chemical properties. Persistent homology features improve QSAR
(quantitative structure-activity relationship) models beyond classical fingerprints.

### Brain Connectivity and Cognitive Networks

Functional connectivity matrices (fMRI, EEG) modeled as clique complexes.
Persistent topological features capture the organization of functional networks
(default mode network loops, working memory circuits) that pairwise correlation
matrices cannot represent. H₁ features from brain connectivity correlate with
cognitive performance and neurodegeneration biomarkers.

---

## 10. References {#references}

**Foundational:**

- Edelsbrunner, H., & Harer, J. (2010). _Computational Topology: An Introduction_. AMS.
- Carlsson, G. (2009). Topology and data. _Bulletin of the AMS_, 46(2), 255–308.
- Cohen-Steiner, D., Edelsbrunner, H., & Harer, J. (2007). Stability of persistence diagrams. _Discrete & Computational Geometry_, 37(1), 103–120.
- Edelsbrunner, H., Letscher, D., & Zomorodian, A. (2002). Topological persistence and simplification. _Discrete & Computational Geometry_, 28(4), 511–533.

**Time series and Takens:**

- Takens, F. (1981). Detecting strange attractors in turbulence. _Lecture Notes in Mathematics_, 898, 366–381.
- Perea, J. A., & Harer, J. (2015). Sliding windows and persistence: An application of topological methods to signal analysis. _Foundations of Computational Mathematics_, 15(3), 799–838.

**ML with TDA:**

- Bubenik, P. (2015). Statistical topological data analysis using persistence landscapes. _JMLR_, 16(3), 77–102.
- Adams, H., et al. (2017). Persistence images: A stable vector representation of persistent homology. _JMLR_, 18(8), 1–35.
- Hu, X., et al. (2019). Topology-preserving deep image segmentation. _NeurIPS_.

**Higher-order TDA:**

- Barbarossa, S., & Sardellitti, S. (2020). Topological signal processing over simplicial complexes. _IEEE TSP_, 68, 2992–3007.
- Hansen, J., & Ghrist, R. (2021). Toward a spectral theory of cellular sheaves. _Journal of Applied and Computational Topology_, 3(4), 315–358.

**Software:**

- Tauzin, G., et al. (2021). giotto-tda: A topological data analysis toolkit for machine learning. _JMLR_, 22(39). https://giotto-ai.github.io/gtda-docs/
- Bauer, U. (2021). Ripser: Efficient computation of Vietoris-Rips persistence barcodes. _Journal of Applied and Computational Topology_, 5(3), 391–423. https://github.com/Ripser/ripser
