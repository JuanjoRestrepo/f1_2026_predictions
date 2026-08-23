# Graph Neural Networks & Neural Architecture Selection

> **References**: Bronstein et al. (2021). _Geometric Deep Learning: Grids, Groups,
> Graphs, Geodesics, and Gauges_. arXiv:2104.13478. · Wu et al. (2021). A Comprehensive
> Survey on Graph Neural Networks. _IEEE TNNLS_, 32(1). · Kipf & Welling (2017). Semi-
> Supervised Classification with Graph Convolutional Networks. _ICLR_. · Veličković et al.
> (2018). Graph Attention Networks. _ICLR_. · Hamilton et al. (2017). Inductive
> Representation Learning on Large Graphs. _NeurIPS_. · Xu et al. (2019). How Powerful
> are Graph Neural Networks? _ICLR_. · Singh (2024). Over-Squashing in GNNs: A
> Comprehensive Survey. arXiv:2308.15568.

## Table of Contents

1. [The Geometry of Data — Why Architecture Starts with Data Shape](#data-shape)
2. [Neural Architecture Selection Framework](#architecture-selection)
3. [Graph Neural Networks — Foundations](#gnn-foundations)
4. [Mathematical Foundations of GNN Architectures](#gnn-math)
5. [Neural Architecture Pipelines — Comparative Computation Flow](#arch-pipelines)
6. [GNN Architectures — Selection Guide](#gnn-architectures)
7. [GNN Task Types](#gnn-tasks)
8. [Implementation with PyTorch Geometric](#implementation)
9. [GNN Limitations and Failure Modes](#limitations)
10. [When NOT to Use a GNN](#when-not)
11. [Real-World Applications](#applications)
12. [References](#references)

---

## 1. The Geometry of Data — Why Architecture Starts with Data Shape {#data-shape}

> **Bronstein et al. (2021)**: "The key insight of geometric deep learning is that the
> inductive biases of a neural architecture should match the symmetries and structure
> of the data domain."

Before selecting any neural architecture, the first question is structural: **what
shape is the data?** Different data geometries require fundamentally different
inductive biases — assumptions baked into the architecture about how information
is organized and how it should be processed.

### Data Geometry Map

| Data shape                       | Structure                        | Canonical architecture              | Examples                                     |
| -------------------------------- | -------------------------------- | ----------------------------------- | -------------------------------------------- |
| Regular grid                     | Euclidean, shift-invariant       | CNN                                 | Images, video frames, satellite data         |
| Sequence                         | Ordered, temporal dependency     | RNN / LSTM                          | Time series, sensor logs, short text         |
| Sequence with long-range context | Ordered, global attention needed | Transformer                         | NLP, long sequences, code, audio             |
| Graph (nodes + edges)            | Non-Euclidean, relational        | GNN                                 | Molecules, social networks, knowledge graphs |
| Unstructured tabular             | No geometric structure           | GBM (XGBoost / LightGBM / CatBoost) | Structured business data                     |

**The fundamental insight** (Bronstein et al., 2021): CNNs, RNNs, and Transformers
are special cases of GNNs operating on specific graph topologies. A CNN layer applies
convolution on a grid graph (pixels connected to adjacent pixels). A Transformer applies
self-attention on a complete graph (every token connected to every other token). GNNs
generalize to arbitrary graph topologies.

This unification, called **Geometric Deep Learning**, provides a principled framework
for selecting architectures by matching the symmetry group of the data:

- Grid → translation symmetry → CNN
- Sequence → time-shift symmetry → RNN
- Complete graph → permutation invariance → Transformer
- Arbitrary graph → permutation invariance over neighborhoods → GNN

---

## 2. Neural Architecture Selection Framework {#architecture-selection}

Apply this decision logic before selecting any deep learning architecture. Always
start from the data structure, not from what is currently popular.

### Five-question decision tree

```
Question 1: Is your data structured as a graph (nodes + edges with explicit relationships)?
  YES → GNN (proceed to Section 3)
  NO  → Continue

Question 2: Does the spatial arrangement of your data carry meaning (pixels, voxels, maps)?
  YES → CNN
  NO  → Continue

Question 3: Does the ORDER of observations matter (temporal dependency, sequences)?
  YES → Does the task require capturing dependencies > ~500 steps apart?
          YES → Transformer (or CNN+Transformer hybrid)
          NO  → LSTM / GRU (more efficient for short-to-medium sequences)
  NO  → Continue

Question 4: Is the task a language, reasoning, or generation task?
  YES → Transformer
  NO  → Continue

Question 5: Is the data structured/tabular with no geometric structure?
  YES → Gradient Boosting (XGBoost / LightGBM / CatBoost) — see ml_evaluation.md
  NO  → Default to Transformer (2026 baseline for ambiguous cases)
```

### Architecture comparison table

| Dimension                       | CNN                                                 | RNN / LSTM                                | Transformer                                           | GNN                                                                       |
| ------------------------------- | --------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------- |
| **Data type**                   | Grid (images, video)                                | Ordered sequences                         | Sequences, text, long context                         | Graphs (nodes + edges)                                                    |
| **Key strength**                | Local spatial pattern detection                     | Sequential temporal dependency            | Global attention across all positions                 | Relational structure, neighbor aggregation                                |
| **Inductive bias**              | Translation equivariance                            | Time-shift equivariance                   | Permutation equivariance (full graph)                 | Permutation invariance over neighborhoods                                 |
| **Scalability**                 | Excellent (parallel)                                | Poor for long sequences (sequential)      | Quadratic in sequence length (O(n²))                  | Scales with edge count; large graphs are challenging                      |
| **Handles irregular structure** | No — requires fixed grid                            | No — requires fixed sequence              | No — requires fixed-length sequences                  | Yes — native irregular topology                                           |
| **Real applications**           | Object detection, medical imaging, face recognition | Stock forecasting, IoT sensors, short NLP | Chatbots, code generation, summarization, translation | Drug discovery, fraud detection, recommendation systems, knowledge graphs |
| **Primary frameworks**          | PyTorch, TensorFlow/Keras                           | PyTorch, TensorFlow/Keras                 | HuggingFace Transformers, PyTorch                     | PyTorch Geometric (PyG), DGL                                              |

---

## 3. Graph Neural Networks — Foundations {#gnn-foundations}

### What is a graph?

A graph G = (V, E) consists of:

- V — a set of nodes (vertices), each potentially carrying a feature vector x_v
- E — a set of edges (u, v) connecting nodes, each potentially carrying edge features e_uv
- A — the adjacency matrix encoding connectivity

Graphs are the correct data structure when **relationships between entities are as
important as the entities themselves**. In a tabular dataset, each row is an
independent observation. In a graph, each node's context is defined by its neighbors.

### The Message Passing Framework (Gilmer et al., 2017)

All major GNN architectures are instances of the Message Passing Neural Network
(MPNN) framework. Each layer performs three operations:

```
Step 1 — Message: for each node v, compute messages from all neighbors u ∈ N(v)
  m_uv = MESSAGE(h_u, h_v, e_uv)

Step 2 — Aggregate: combine all incoming messages for node v
  M_v = AGGREGATE({m_uv : u ∈ N(v)})

Step 3 — Update: update node v's representation using aggregated messages
  h_v' = UPDATE(h_v, M_v)
```

After L layers, each node's representation incorporates information from its
L-hop neighborhood. This is the graph analogue of a receptive field in CNNs.

### Why GNNs cannot be replaced by standard neural networks

Standard neural networks (MLP, CNN, RNN) operate on Euclidean data with a fixed
input structure. They cannot handle:

- Variable-sized, irregularly connected neighborhoods
- Permutation invariance: the prediction should not change if nodes are relabeled
- Long-range relational reasoning across arbitrarily connected entities

A molecule with 20 atoms cannot be fed into a CNN — atoms have no fixed spatial
arrangement. Two molecules with identical atoms but different bond structures
(connectivity) are chemically distinct; only a GNN captures this distinction.

---

## 3.5. Mathematical Foundations of GNN Architectures {#gnn-math}

> **References**: Kipf & Welling (2017) arXiv:1609.02907. Veličković et al. (2018)
> arXiv:1710.10903. Hamilton et al. (2017) arXiv:1706.02216. Xu et al. (2019)
> arXiv:1810.00826. Defferrard et al. (2016) _ChebNet_. NeurIPS. arXiv:1606.09375.

### Spectral Graph Theory — Mathematical Prerequisites

A graph signal is a function x: V → R assigning a scalar to each node.
The graph Laplacian is the operator that measures how much x varies across edges.

**Graph Laplacian matrices:**

```
L = D − A                                  (combinatorial Laplacian)
L_sym = D^(−1/2) L D^(−1/2)               (normalized — used in GCN)
      = I − D^(−1/2) A D^(−1/2)
```

where A is the adjacency matrix and D_ii = Σ_j A_ij is the degree matrix.

**Eigendecomposition:**

```
L_sym = U Λ U^T
```

- U = [u₁, ..., uₙ] ∈ R^(n×n): orthonormal eigenvectors (graph Fourier basis)
- Λ = diag(λ₁, ..., λₙ): eigenvalues with 0 = λ₁ ≤ λ₂ ≤ ... ≤ λₙ ≤ 2
- λ₂ (Fiedler eigenvalue / algebraic connectivity): measures graph connectivity.
  Small λ₂ → graph is a near-bottleneck → over-squashing.
  Large λ₂ → well-connected → faster mixing → over-smoothing accelerates.

**Graph Fourier Transform:**

```
x̂ = U^T x          (forward: project node signal onto eigenbasis)
x  = U x̂            (inverse: reconstruct from spectral coefficients)
```

Interpretation: eigenvectors with small λ encode low-frequency (smooth) variation;
eigenvectors with large λ encode high-frequency (sharp boundary) variation.

**Spectral convolution** (Bruna et al., 2014):

```
x *_G g_θ = U · diag(θ₁,...,θₙ) · U^T x
```

Problem: n learnable parameters per filter — does not generalize to new graphs;
O(n) computation; eigenvectors change when graph changes.

**Chebyshev approximation** (ChebNet, Defferrard et al., 2016):
Approximate the spectral filter with a K-th order polynomial of the Laplacian:

```
g_θ(L̃) ≈ Σ_{k=0}^{K} θ_k T_k(L̃)        where L̃ = 2L/λₘₐₓ − I_n ∈ [−1, 1]
T_k(x) = 2x T_{k−1}(x) − T_{k−2}(x),    T₀ = 1,  T₁ = x    (recurrence)
```

Result: K learnable parameters per filter; K-localized (only uses K-hop neighborhoods);
computation O(K|E|) — linear in edges. This is the origin of "graph convolution."

### GCN Derivation — From Spectral to Spatial

Kipf & Welling (2017) simplify ChebNet to K = 1 and λₘₐₓ ≈ 2:

```
g_θ *_G x ≈ θ₀ x + θ₁ (L_sym − I_n) x = θ₀ x − θ₁ D^(−1/2) A D^(−1/2) x
```

Tie parameters θ = θ₀ = −θ₁ to reduce overfitting:

```
g_θ *_G x ≈ θ (I_n + D^(−1/2) A D^(−1/2)) x
```

**Renormalization trick**: replace I_n + D^(−1/2) A D^(−1/2) with the renormalized form
to stabilize gradients (the original has eigenvalues in [0, 2] — problematic for deep networks):

```
Ã = A + I_N    (add self-loops)
D̃_ii = Σ_j Ã_ij    (degree of Ã)
propagation rule: H^(l+1) = σ(D̃^(−1/2) Ã D̃^(−1/2) H^(l) W^(l))
```

Eigenvalues of D̃^(−1/2) Ã D̃^(−1/2) lie in [0, 1] — numerically stable for
gradient propagation through multiple layers.

**Spatial interpretation**: each node aggregates its own features and its neighbors'
features, weighted by 1/√(deg(u)·deg(v)) for edge (u, v). High-degree nodes
contribute less per edge — normalization prevents dominant hubs.

### GAT — Full Attention Mechanism Derivation

Veličković et al. (2018) replace fixed normalization with learned attention:

**Step 1 — Linear transformation**: project all node features into a shared space:

```
z_v = W h_v    for all v ∈ V,  W ∈ R^(F'×F)
```

**Step 2 — Attention coefficient**: measure importance of neighbor u to node v:

```
e_ij = LeakyReLU(a^T [z_i ∥ z_j])
```

where a ∈ R^(2F') is a learnable attention vector, ∥ is concatenation.

**Step 3 — Normalization** (softmax over each node's neighborhood):

```
α_ij = exp(e_ij) / Σ_{k ∈ N(i) ∪ {i}} exp(e_ik)
```

These are the attention coefficients: α_ij ≥ 0 and Σ_j α_ij = 1.

**Step 4 — Aggregation**:

```
h_i' = σ(Σ_{j ∈ N(i)} α_ij W h_j)    (single head)
```

**Multi-head attention** (K independent heads for stability):

```
h_i' = ∥_{k=1}^{K} σ(Σ_{j ∈ N(i)} α_ij^k W^k h_j)    (intermediate layers — concatenate)
h_i' = σ((1/K) Σ_{k=1}^{K} Σ_{j ∈ N(i)} α_ij^k W^k h_j)  (final layer — average)
```

Veličković et al. use K = 8 in intermediate layers and K = 1 in the output layer.

**Attention interpretability**: α_ij is the learned contribution of neighbor j to node i's
representation. After training, α_ij can be visualized to explain which neighbors
drove a prediction — a built-in explainability mechanism absent in GCN.

### GIN — Expressiveness Theory (Xu et al., 2019)

**Core question**: how well can a GNN distinguish non-isomorphic graphs?

**Weisfeiler-Lehman (WL) graph isomorphism test**: iteratively hash node neighborhoods.
Two graphs are WL-indistinguishable iff they appear identical under WL iteration.
WL is the theoretical upper bound for MPNNs.

**Key theorem** (Xu et al., 2019): A GNN is maximally expressive (WL-equivalent)
if and only if its aggregation function is **injective** over multisets.

**Why injectivity matters**: two distinct neighborhoods must produce distinct
representations. If AGGREGATE collapses distinct multisets to the same output,
the GNN cannot distinguish them.

**Aggregation expressiveness ranking**:

```
AGGREGATE function    Injective over multisets?    Counterexample
─────────────────────────────────────────────────────────────────────────────
SUM                   YES — maximally expressive    none (injective)
MEAN                  NO                            {a, a} vs {a} if same mean
MAX                   NO                            {a, a, b} vs {a, b} — same max
```

**GIN update rule**:

```
h_v^(l) = MLP^(l)((1 + ε^(l)) · h_v^(l−1) + Σ_{u ∈ N(v)} h_u^(l−1))
```

ε is a learnable scalar (or fixed to 0); the MLP ensures injectivity of the full update.
Sum aggregation + MLP = the most expressive MPNN within the WL framework.

### GraphSAGE — Aggregator Variants

Hamilton et al. (2017) define three aggregator choices:

```
MEAN:  h_v^(l) = σ(W · MEAN({h_v^(l−1)} ∪ {h_u^(l−1) : u ∈ N(v)}))
MAX:   h_v^(l) = σ(W · MAX({ReLU(W_pool h_u^(l−1) + b) : u ∈ N(v)}))
LSTM:  h_v^(l) = σ(W · LSTM(h_v^(l−1), {h_u^(l−1) : u ∈ π(N(v))}))
```

LSTM is most expressive but assumes an arbitrary (random) ordering of neighbors —
valid only if the aggregation is applied consistently at training and inference.
For production, MEAN aggregation is preferred: deterministic, interpretable, and
scales to large graphs via mini-batch sampling.

### Backpropagation Through Graph Layers

The loss L(θ) is defined on output node embeddings h_v^(L) (node tasks),
decoded edge scores (link prediction), or a global readout (graph classification).

**Gradient flow through one GCN layer:**

```
H^(l+1) = σ(S H^(l) W^(l))    where S = D̃^(−1/2) Ã D̃^(−1/2)

∂L/∂W^(l) = (S H^(l))^T · (∂L/∂H^(l+1) ⊙ σ'(S H^(l) W^(l)))
∂L/∂H^(l) = S^T · (∂L/∂H^(l+1) ⊙ σ'(S H^(l) W^(l))) · W^(l)^T
```

Since S is symmetric (S = S^T), the gradient back-propagates through the same
graph structure as the forward pass — information flows backward along the same
edges, weighted by the same normalization factors.

**Key consequence**: vanishing gradients are tied to the spectral gap.
A graph with near-zero λ₂ (bottleneck) passes little gradient signal through
the bottleneck edges — the graph structure creates gradient flow bottlenecks.

**BPTT analogy**: backpropagation through L GNN layers on a graph with poor
connectivity is analogous to BPTT through long sequences in RNNs — gradients
decay through the bottleneck edges at each layer.

### Loss Functions by Task Type

```
Task                Loss function
────────────────────────────────────────────────────────────────────────────────
Node classification  L = −Σ_{v∈V_L} Σ_{c} y_vc log ŷ_vc    (cross-entropy over labeled nodes)

Link prediction      L = −Σ_{(u,v)∈E_+} log σ(z_u^T z_v)
                       − Σ_{(u,v)∈E_−} log(1 − σ(z_u^T z_v))
                     where E_+ = positive edges, E_− = sampled negative edges

Graph classification L = −Σ_{G∈D} y_G log ŷ_G              (cross-entropy on graph embeddings)

Graph regression     L = Σ_{G∈D} (y_G − ŷ_G)²              (MSE on graph-level readout)
```

Negative sampling for link prediction: sample k negative edges (non-existing) per
positive edge. k ∈ [1, 5] is standard; higher k increases specificity at the cost
of training time.

### Over-Smoothing — Spectral Analysis

**GCN filter after L layers:**

```
P̂^L where P̂ = D̃^(−1/2) Ã D̃^(−1/2),  eigenvalues λ̂_i ∈ [0, 1]
```

Repeatedly applying P̂ is a low-pass filter: λ̂_i^L → 0 for high-frequency components
(large λ̂_i close to... wait: eigenvalues of P̂ are in [0,1]; λ̂_i^L → 0 for λ̂_i < 1)
After many layers: all node representations converge to the principal eigenvector
(corresponding to λ̂ = 1), weighted by node degree. Nodes in the same connected
component become indistinguishable.

**Dirichlet energy** measures representation diversity:

```
E(H^(l)) = (1/|E|) Σ_{(u,v)∈E} ‖h_u^(l) − h_v^(l)‖²
```

Over-smoothing ≡ E(H^(l)) → 0 as l → ∞. Monitor this during training:
if E drops precipitously with layer depth, the GNN is over-smoothing.

### Optimization Best Practices

```
Hyperparameter      Recommended range      Notes
────────────────────────────────────────────────────────────────────────────────
Learning rate       0.001 – 0.01           Adam; start at 0.01, decay on plateau
Weight decay        1e−4 – 5e−4            L2 regularization; controls over-fitting
Dropout             0.3 – 0.6              Apply after each conv layer AND on input
Gradient clipping   max_norm = 1.0 – 5.0  Critical for deep GNNs and large sparse graphs
Hidden dimension    64 – 256               Increase with graph size; diminishing returns > 256
Number of layers    2 – 4                  Rarely exceed 5; over-smoothing accelerates
Batch size          32 – 256 graphs        For graph classification; use NeighborLoader for node tasks
```

**Layer normalization strategy**: apply BatchNorm after each conv layer for GIN and
GraphSAGE; apply PairNorm if over-smoothing is observed (PairNorm explicitly
prevents the Dirichlet energy from collapsing to zero).

---

## 3.6. Neural Architecture Pipelines — Comparative Computation Flow {#arch-pipelines}

The following shows the full forward computation pipeline for each architecture,
enabling direct comparison of how information is transformed from input to output.

### CNN — Spatial Hierarchical Processing

```
Input image (H×W×C)
  ↓ Convolution: feature maps via learned filters k×k
    extracts local patterns: edges, textures, gradients
  ↓ Activation: ReLU(·) — introduces non-linearity
  ↓ Pooling: max or average over spatial region
    reduces spatial dimension; preserves dominant activations
  ↓ [repeat conv+activation+pooling for L layers — hierarchical features]
  ↓ Flatten: reshape 3D tensor to 1D vector
  ↓ Fully connected layer(s): combine all features globally
  ↓ Softmax → class probabilities
```

Inductive bias: translation equivariance — the same pattern detected anywhere in
the image activates the same filter. Inappropriate for non-grid data.

### RNN / LSTM — Sequential State Propagation

```
Input sequence (x₁, x₂, ..., x_T)
  ↓ Process step-by-step: t = 1, 2, ..., T
    at each t: read token x_t, update hidden state
  ↓ LSTM update:
    f_t = σ(W_f [h_{t−1}, x_t] + b_f)         (forget gate)
    i_t = σ(W_i [h_{t−1}, x_t] + b_i)         (input gate)
    g_t = tanh(W_g [h_{t−1}, x_t] + b_g)       (candidate cell)
    c_t = f_t ⊙ c_{t−1} + i_t ⊙ g_t           (cell state update)
    o_t = σ(W_o [h_{t−1}, x_t] + b_o)         (output gate)
    h_t = o_t ⊙ tanh(c_t)                      (hidden state)
  ↓ Output: h_T (sequence-to-one) or (h₁,...,h_T) (sequence-to-sequence)
  ↓ Backpropagation through time (BPTT):
    gradients flow back through every timestep
    vanishing/exploding gradients for T >> 100
```

Inductive bias: time-shift equivariance — the same pattern at any time step
activates the same weights. The cell state c_t is the explicit memory mechanism.

### Transformer — Global Attention Mechanism

```
Input sequence (w₁, w₂, ..., w_T)
  ↓ Tokenize & embed: wᵢ → eᵢ ∈ R^d_model
  ↓ Positional encoding: eᵢ' = eᵢ + PE(i)
    PE(i, 2k)   = sin(i / 10000^(2k/d_model))
    PE(i, 2k+1) = cos(i / 10000^(2k/d_model))
    (injects position information — Transformer has no built-in sequence order)
  ↓ Self-attention (one head):
    Q = E W_Q,  K = E W_K,  V = E W_V        (project to query, key, value)
    Attention(Q,K,V) = softmax(QK^T / √d_k) V
    scores QK^T/√d_k: each token compares to every other token (O(T²) cost)
  ↓ Multi-head attention: h independent heads concatenated
    MultiHead = Concat(head₁,...,head_h) W_O
  ↓ Feed-forward network: applied per-position independently
    FFN(x) = max(0, xW₁ + b₁)W₂ + b₂
  ↓ Add & LayerNorm: residual connection after each sub-layer
  ↓ Repeat for N layers
  ↓ Generate output (decoder uses cross-attention to encoder output)
```

Inductive bias: none on sequence order (added via positional encoding).
Full attention = complete graph — every token is connected to every other.
Quadratic memory and compute O(T²) in sequence length.

### GNN — Relational Neighborhood Propagation

```
Input graph G = (V, E) with node features X ∈ R^(|V|×F)
  ↓ Node feature initialization: h_v^(0) = x_v  ∀v ∈ V
  ↓ Define connectivity: adjacency A — which nodes communicate
  ↓ For l = 1, ..., L layers:
    Message: m_uv^(l) = MESSAGE(h_u^(l−1), h_v^(l−1), e_uv)
    Aggregate: M_v^(l) = AGGREGATE({m_uv^(l) : u ∈ N(v)})
    Update: h_v^(l) = UPDATE(h_v^(l−1), M_v^(l))
    → After l layers: h_v^(l) encodes the l-hop subgraph around v
  ↓ Task-specific readout:
    Node tasks:       ŷ_v = f(h_v^(L))
    Edge tasks:       ŷ_uv = f(h_u^(L) ∥ h_v^(L))
    Graph tasks:      h_G = READOUT({h_v^(L) : v ∈ V})  then ŷ = f(h_G)
    READOUT options: global mean pool, global sum pool, differentiable pooling (DiffPool)
```

Inductive bias: permutation invariance over neighborhoods — the same subgraph
structure produces the same embedding regardless of node labeling.

### Architecture Decision — Computational Complexity

| Architecture | Memory            | Forward pass | Key bottleneck     |
| ------------ | ----------------- | ------------ | ------------------ |
| CNN          | O(F·K²) per layer | O(H·W·F·K²)  | Spatial resolution |
| LSTM         | O(4·d²) per step  | O(T·d²)      | Sequence length T  |
| Transformer  | O(T²·d)           | O(T²·d)      | Quadratic in T     |
| GNN          | O(\|E\|·F)        | O(\|E\|·F)   | Edge count \|E\|   |

Transformers scale poorly to long sequences (T > 4096 without approximations).
GNNs scale poorly to dense graphs (\|E\| = O(\|V\|²)) without sampling.

---

## 4. GNN Architectures — Selection Guide {#gnn-architectures}

### GCN — Graph Convolutional Network (Kipf & Welling, 2017)

**Mechanism**: each node aggregates features from its neighbors using normalized
adjacency weighting. Simple, fast, and effective as a baseline.

**Formula**: H' = σ(D^(-1/2) A D^(-1/2) H W), where A is the adjacency matrix
with self-loops, D is the degree matrix, H is the node feature matrix, W is a
learned weight matrix.

**When to use**:

- Baseline for any node classification task on a static, known graph
- Homophilic graphs (connected nodes tend to have the same label)
- Transductive setting (all nodes are known at training time)

**Limitations**:

- All neighbors are weighted equally — cannot distinguish important from unimportant neighbors
- Transductive: does not generalize to new nodes not seen at training time
- Prone to over-smoothing at depth > 3–4 layers (see Section 7)

### GAT — Graph Attention Network (Veličković et al., 2018)

**Mechanism**: learns attention coefficients α_uv for each edge — importance of
neighbor u to node v is learned from the data, not fixed by graph structure.
Multi-head attention provides stable, expressive representations.

**When to use**:

- Heterophilic graphs (connected nodes may have different labels — attention can
  down-weight noisy neighbors)
- When distinguishing informative from uninformative neighbors is critical
- Node classification where neighbor importance varies by context (e.g., citation
  networks where some citations are more relevant than others)

**Advantages over GCN**:

- Attention scores are interpretable — which neighbors influenced a prediction?
- Can run both transductively and inductively

### GraphSAGE — Sample and Aggregate (Hamilton et al., 2017)

**Mechanism**: instead of using the full neighborhood, GraphSAGE samples a fixed-size
subset of neighbors and aggregates their features (mean, max, or LSTM aggregation).
Learns an inductive embedding function — not the embedding itself.

**When to use**:

- Inductive setting: new nodes appear at inference time (e.g., new users, new products)
- Large-scale graphs where full neighborhood aggregation is computationally infeasible
- Dynamic graphs where the structure evolves (e.g., social networks, transaction graphs)
- Production recommendation systems (Pinterest, Uber)

**Key advantage**: the only major GNN architecture that natively handles new,
unseen nodes at inference time. This is the standard choice for production systems.

### GIN — Graph Isomorphism Network (Xu et al., 2019)

**Mechanism**: uses a sum aggregation with a learnable epsilon parameter.
Theoretically proven to be as expressive as the Weisfeiler-Lehman (WL) graph
isomorphism test — the theoretical upper bound on distinguishing graph structures.

**When to use**:

- Graph classification tasks where distinguishing graph structure is paramount
- Molecular property prediction (molecules as graphs)
- When you need the most expressive possible GNN within the MPNN framework
- Benchmark comparisons where theoretical expressivity matters

### Architecture selection summary

| Architecture | Setting       | Best task                                     | Distinguishing property                    |
| ------------ | ------------- | --------------------------------------------- | ------------------------------------------ |
| GCN          | Transductive  | Node classification (homophilic)              | Simple, fast baseline                      |
| GAT          | Both          | Node classification (heterophilic)            | Learned neighbor importance                |
| GraphSAGE    | **Inductive** | Node classification, link prediction at scale | Handles unseen nodes — production standard |
| GIN          | Both          | **Graph classification**                      | Maximum WL expressivity                    |

---

## 5. GNN Task Types {#gnn-tasks}

GNNs solve three categories of tasks, each operating at a different level of the graph:

### Node-level tasks

Each node receives a prediction. The GNN learns node embeddings by aggregating
neighborhood information.

- **Node classification**: predict a label for each node (e.g., classify a research
  paper by topic in a citation graph; classify a user as fraudulent in a transaction graph)
- **Node regression**: predict a continuous value per node (e.g., predict traffic speed
  at each road segment)

### Edge-level tasks

Predictions are made about pairs of nodes.

- **Link prediction**: predict whether an edge should exist between two nodes — the
  core task in recommendation systems (will user u interact with item v?) and
  knowledge graph completion (does this relation hold between entity A and entity B?)
- **Edge classification**: classify existing edges (e.g., classify bond types in molecules)

### Graph-level tasks

A single prediction is made for an entire graph. Requires a readout / pooling
function to aggregate all node representations into a graph-level vector.

- **Graph classification**: predict a property of the whole graph (e.g., is this
  molecule toxic? does this protein fold into a functional shape?)
- **Graph regression**: predict a continuous value for the graph (e.g., predict the
  binding affinity of a drug-target pair)

---

## 6. Implementation with PyTorch Geometric {#implementation}

PyTorch Geometric (PyG) is the standard production library for GNNs.
(Fey & Lenssen, 2019. _Fast Graph Representation Learning with PyTorch Geometric_.
ICLR Workshop. https://pytorch-geometric.readthedocs.io)

### Environment setup

```bash
uv init gnn_project && cd gnn_project
uv python pin 3.12
uv venv .venv --python 3.12 && source .venv/bin/activate

# PyTorch first (required before PyG)
uv add torch torchvision

# PyTorch Geometric
uv add torch-geometric

# Optional: sparse tensor acceleration
uv add torch-scatter torch-sparse torch-cluster

# Dev tools
uv add --dev ruff mypy pytest
uv sync
```

### Graph data structure in PyG

```python
from __future__ import annotations

import torch
from torch_geometric.data import Data

# A graph in PyG is a Data object with:
# x:         node feature matrix of shape [num_nodes, num_node_features]
# edge_index: connectivity in COO format of shape [2, num_edges]
# edge_attr:  edge feature matrix of shape [num_edges, num_edge_features] (optional)
# y:          target labels — shape [num_nodes] for node tasks,
#             shape [num_edges] for edge tasks, shape [1] for graph tasks

# Example: a simple graph with 4 nodes, each with 3 features, and 4 directed edges
x = torch.tensor(
    [[1.0, 0.0, 2.0],   # node 0 features
     [0.0, 1.0, 1.5],   # node 1 features
     [2.0, 2.0, 0.5],   # node 2 features
     [1.5, 0.0, 1.0]],  # node 3 features
    dtype=torch.float
)

# edge_index: [2, num_edges] — row 0 = source nodes, row 1 = target nodes
edge_index = torch.tensor(
    [[0, 1, 2, 3],
     [1, 2, 3, 0]],
    dtype=torch.long
)

y = torch.tensor([0, 1, 0, 1], dtype=torch.long)   # node labels

data = Data(x=x, edge_index=edge_index, y=y)

print(f"Nodes: {data.num_nodes}")       # 4
print(f"Edges: {data.num_edges}")       # 4
print(f"Node features: {data.num_node_features}")  # 3
print(f"Contains self-loops: {data.has_self_loops()}")
print(f"Is undirected: {data.is_undirected()}")
```

### GCN for node classification

```python
from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.nn import GCNConv
from torch_geometric.datasets import Planetoid


class GCN(nn.Module):
    """
    Two-layer Graph Convolutional Network for node classification.
    Kipf & Welling (2017). Semi-Supervised Classification with GCNs. ICLR.

    Args:
        in_channels: Number of input node features.
        hidden_channels: Number of hidden units.
        out_channels: Number of output classes.
        dropout: Dropout rate applied between layers.
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        out_channels: int,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, out_channels)
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Forward pass: two message-passing layers with ReLU and dropout."""
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.conv2(x, edge_index)
        return x   # Raw logits — apply softmax or log_softmax externally


def train_gcn(epochs: int = 200) -> None:
    """Training loop for GCN on Cora citation network dataset."""
    dataset = Planetoid(root="/tmp/Cora", name="Cora")
    data = dataset[0]

    model = GCN(
        in_channels=dataset.num_node_features,
        hidden_channels=64,
        out_channels=dataset.num_classes,
        dropout=0.5,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        # train_mask selects only labeled training nodes
        loss = F.cross_entropy(out[data.train_mask], data.y[data.train_mask])
        loss.backward()
        optimizer.step()

    # Evaluation
    model.eval()
    with torch.no_grad():
        pred = model(data.x, data.edge_index).argmax(dim=1)
        correct = (pred[data.test_mask] == data.y[data.test_mask]).sum()
        accuracy = float(correct) / int(data.test_mask.sum())
        print(f"Test accuracy: {accuracy:.4f}")
```

### GAT for node classification

```python
from torch_geometric.nn import GATConv


class GAT(nn.Module):
    """
    Graph Attention Network for node classification.
    Veličković et al. (2018). Graph Attention Networks. ICLR.

    Multi-head attention in layer 1; single head in output layer.
    head_dim * heads must equal hidden_channels.
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        out_channels: int,
        heads: int = 8,
        dropout: float = 0.6,
    ) -> None:
        super().__init__()
        head_dim = hidden_channels // heads
        self.conv1 = GATConv(
            in_channels, head_dim, heads=heads, dropout=dropout, concat=True
        )
        # Output layer: single head, no concatenation
        self.conv2 = GATConv(
            head_dim * heads, out_channels, heads=1, dropout=dropout, concat=False
        )
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = F.elu(self.conv1(x, edge_index))
        x = F.dropout(x, p=self.dropout, training=self.training)
        return self.conv2(x, edge_index)
```

### GraphSAGE for inductive node classification

```python
from torch_geometric.nn import SAGEConv


class GraphSAGE(nn.Module):
    """
    GraphSAGE for inductive node embedding.
    Hamilton et al. (2017). Inductive Representation Learning on Large Graphs. NeurIPS.

    Handles unseen nodes at inference time — the standard choice for
    production systems with dynamic graphs (new users, new items).
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        out_channels: int,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels, aggr="mean")
        self.conv2 = SAGEConv(hidden_channels, out_channels, aggr="mean")
        self.dropout = dropout

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        return self.conv2(x, edge_index)
```

### Graph classification with GIN and global pooling

```python
from torch_geometric.nn import GINConv, global_add_pool


class GIN(nn.Module):
    """
    Graph Isomorphism Network for graph classification.
    Xu et al. (2019). How Powerful are Graph Neural Networks? ICLR.

    Uses sum aggregation — proven to be as expressive as WL graph isomorphism test.
    Standard choice for molecular property prediction and graph-level tasks.
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        out_channels: int,
        num_layers: int = 5,
    ) -> None:
        super().__init__()
        self.convs = nn.ModuleList()

        for i in range(num_layers):
            mlp = nn.Sequential(
                nn.Linear(in_channels if i == 0 else hidden_channels, hidden_channels),
                nn.BatchNorm1d(hidden_channels),
                nn.ReLU(),
                nn.Linear(hidden_channels, hidden_channels),
                nn.ReLU(),
            )
            self.convs.append(GINConv(mlp, train_eps=True))

        self.classifier = nn.Linear(hidden_channels, out_channels)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        batch: torch.Tensor,
    ) -> torch.Tensor:
        for conv in self.convs:
            x = conv(x, edge_index)

        # Global sum pooling: aggregate all node embeddings into one graph vector
        x = global_add_pool(x, batch)
        return self.classifier(x)
```

### Custom message passing layer

```python
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import add_self_loops, degree


class CustomMPLayer(MessagePassing):
    """
    Custom message passing layer following the MPNN framework.
    Gilmer et al. (2017). Neural Message Passing for Quantum Chemistry. ICML.

    Extend this class to implement any novel GNN layer:
    - Override message() to define what information flows along edges
    - Override aggregate() to change how messages are combined
    - Override update() to define how node representations are updated
    """

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__(aggr="add")   # "add", "mean", or "max" aggregation
        self.linear = nn.Linear(in_channels, out_channels)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        edge_index, _ = add_self_loops(edge_index, num_nodes=x.size(0))
        x = self.linear(x)

        # Compute normalization: 1 / sqrt(deg_u * deg_v) for each edge
        row, col = edge_index
        deg = degree(col, x.size(0), dtype=x.dtype)
        deg_inv_sqrt = deg.pow(-0.5)
        norm = deg_inv_sqrt[row] * deg_inv_sqrt[col]

        return self.propagate(edge_index, x=x, norm=norm)

    def message(self, x_j: torch.Tensor, norm: torch.Tensor) -> torch.Tensor:
        """x_j: features of the source node for each edge."""
        return norm.view(-1, 1) * x_j
```

---

## 7. GNN Limitations and Failure Modes {#limitations}

Understanding these failure modes is essential for deciding whether a GNN is the
right architecture and for debugging poor performance.

### Over-smoothing (Li et al., 2018)

As the number of GNN layers L increases, node representations converge to the same
value — they become indistinguishable regardless of their original features. This
occurs because each layer mixes features across neighborhoods; after many layers,
every node's representation is a weighted average of the entire graph.

**Effect**: performance degrades with depth. Most GNNs peak at 2–4 layers.

**Mitigation**:

- Use 2–3 layers as the default; rarely exceed 5
- Apply residual connections (skip connections between layers)
- Use DropEdge (randomly remove edges during training)
- Use PairNorm or GroupNorm for normalization

**Reference**: ud din & Qureshi (2024). Limits of Depth: Over-Smoothing and
Over-Squashing in GNNs. _Big Data Mining and Analytics_, 7(1).

### Over-squashing (Alon & Yahav, 2021)

When a node needs to aggregate information from a distant node through a narrow
graph bottleneck (a single edge connecting two dense subgraphs), the exponentially
growing neighborhood information must be compressed into a fixed-size vector. This
compression causes loss of long-range information.

**Effect**: GNNs struggle with tasks that require reasoning over long distances in
the graph (e.g., detecting a pattern that requires looking 10 hops away).

**Mitigation**:

- Graph rewiring: add edges between distant nodes that should communicate
- Use Graph Transformers (combine GNN with self-attention for global connectivity)

**Reference**: Singh (2024). Over-Squashing in GNNs: A Comprehensive Survey.
arXiv:2308.15568.

### The over-smoothing / over-squashing tradeoff

Giraldo et al. (2022) prove that over-smoothing and over-squashing are intrinsically
linked to the spectral gap of the graph Laplacian. They cannot both be alleviated
simultaneously with standard architectures — mitigating one worsens the other.
The practical implication: keep GNN depth shallow (2–4 layers) and use graph
rewiring or Graph Transformers for long-range tasks.

### Scalability

Full neighborhood aggregation for very large graphs (millions of nodes, billions
of edges) is computationally prohibitive. Approaches:

- **Mini-batch sampling** (GraphSAGE, ClusterGCN): sample fixed-size neighborhoods
- **Graph partitioning**: divide the graph and train on subgraphs
- **Scalable GNN frameworks**: PyG with `NeighborLoader`, DGL with `NodeDataLoader`

---

## 8. When NOT to Use a GNN {#when-not}

A GNN is the correct choice only when explicit relational structure is present and
meaningful. It is the wrong choice in these situations:

**The data is tabular with no natural graph structure.** Forcing arbitrary k-nearest-
neighbor graphs onto tabular data to "use a GNN" is an anti-pattern. Errica et al.
(2024) showed that for tabular data without natural graph structure, GBMs
(XGBoost / LightGBM) consistently outperform GNNs. Use GBMs for tabular data.

**The relationship between entities is fully captured by their features.** If there
is no meaningful signal in the connectivity pattern — only in node features — an MLP
or GBM will match or exceed GNN performance with a fraction of the complexity.

**The graph topology is essentially a complete graph.** If every node is connected to
every other node (or near-complete), a Transformer with self-attention is equivalent
and more efficient. No information is gained from explicit graph modeling.

**The graph is too large for the GNN architecture.** If the graph has billions of edges
and mini-batch sampling is not appropriate for the task, reconsider whether GNNs are
operationally feasible.

**The task requires temporal reasoning across sequences.** Use RNN / LSTM / Transformer
for sequential data, not temporal GNNs unless the data has an explicit graph structure
that evolves over time.

---

## 9. Real-World Applications {#applications}

### Drug discovery and molecular science

**AlphaFold 2** (Jumper et al., 2021. _Nature_, 596) uses attention mechanisms over
amino acid graphs to predict 3D protein structure. GNNs are the standard for
molecular property prediction: predicting toxicity, solubility, binding affinity.
Graph = atoms (nodes) + chemical bonds (edges).

**Current use**: Pfizer, Schrödinger, and DeepMind use GNNs for virtual screening
of drug candidates — GNNs score millions of candidate molecules against a target
protein without physical synthesis.

### Fraud detection

Transaction graphs: nodes = users/merchants, edges = financial transactions.
GNNs detect fraudulent patterns through relational context — a node that looks
legitimate in isolation may be part of a ring when its second-order neighborhood
is inspected. PayPal and Visa use GNN-based fraud detection.

Key property: GNNs aggregate evidence from the transaction neighborhood of an entity.
A legitimate-looking account connected to many confirmed fraudulent accounts receives
suspicious signals through message passing.

### Recommendation systems

**PinSage** (Ying et al., 2018. _KDD_. Pinterest) is the canonical production GNN
for recommendation. The graph = users + items, edges = interactions.
GraphSAGE-based inductive embedding handles billions of new items per day.

Amazon, Netflix, and Spotify use GNN-based recommendation to model user-item-item
relationships beyond simple collaborative filtering.

### Knowledge graphs and reasoning

Knowledge graphs (entities as nodes, relations as edges): entity alignment,
fact completion, question answering over structured knowledge. GNNs like R-GCN
(Relational GCN) handle heterogeneous graphs with multiple edge types.

Applications: Google Knowledge Graph, Wikidata reasoning, biomedical knowledge graphs.

### Traffic and physical systems

Traffic forecasting: road network as a graph, sensors at nodes, edges = connectivity.
DCRNN (Diffusion Convolutional Recurrent Neural Network) combines GNN with RNN for
spatiotemporal traffic prediction.

Physics simulations: particle systems, fluid dynamics, mesh-based simulations.
GNNs learn to simulate physical interactions by treating particles / mesh nodes
as graph nodes.

---

## 10. References {#references}

**Foundational papers:**

- Bronstein, M. M., Bruna, J., Cohen, T., & Veličković, P. (2021). Geometric deep learning: Grids, groups, graphs, geodesics, and gauges. arXiv:2104.13478.
- Wu, Z., Pan, S., Chen, F., Long, G., Zhang, C., & Yu, P. S. (2021). A comprehensive survey on graph neural networks. _IEEE Transactions on Neural Networks and Learning Systems_, 32(1), 4–24.
- Gilmer, J., Schütt, A., Riley, P., Vinyals, O., & Dahl, G. (2017). Neural message passing for quantum chemistry. _ICML_. arXiv:1704.01212.

**Core GNN architectures:**

- Kipf, T. N., & Welling, M. (2017). Semi-supervised classification with graph convolutional networks. _ICLR_. arXiv:1609.02907.
- Veličković, P., Cucurull, G., Casanova, A., Romero, A., Liò, P., & Bengio, Y. (2018). Graph attention networks. _ICLR_. arXiv:1710.10903.
- Hamilton, W. L., Ying, R., & Leskovec, J. (2017). Inductive representation learning on large graphs. _NeurIPS_. arXiv:1706.02216.
- Xu, K., Hu, W., Leskovec, J., & Jegelka, S. (2019). How powerful are graph neural networks? _ICLR_. arXiv:1810.00826.

**Limitations:**

- Singh, A. (2024). Over-squashing in graph neural networks: A comprehensive survey. arXiv:2308.15568.
- Giraldo, J. H., Skianis, K., Bouwmans, T., & Malliaros, F. D. (2023). On the trade-off between over-smoothing and over-squashing in deep graph neural networks. _CIKM_. arXiv:2212.02374.

**Production and applications:**

- Ying, R., He, R., Chen, K., Eksombatchai, P., Hamilton, W. L., & Leskovec, J. (2018). Graph convolutional neural networks for web-scale recommender systems. _KDD_. arXiv:1806.01973.
- Jumper, J., Evans, R., Pritzel, A., et al. (2021). Highly accurate protein structure prediction with AlphaFold. _Nature_, 596, 583–589.
- Fey, M., & Lenssen, J. E. (2019). Fast graph representation learning with PyTorch Geometric. _ICLR Workshop_. https://pytorch-geometric.readthedocs.io
