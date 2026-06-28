# Fourier — Graph-Spectral Oracle

**The Fourier transform on a graph.** Fourier reads the *natural frequencies* of a network: the Laplacian spectrum, the algebraic connectivity **λ₂ (the Fiedler value)**, the Fiedler vector and its spectral bisection, and a spectral embedding. This is the global "how close is this network to splitting in two" structure that **no per-node metric can express** — and every eigenpair is certified trustlessly in O(E).

![tests](https://img.shields.io/badge/tests-passing-brightgreen)
![protocol](https://img.shields.io/badge/AIMarket-v2-6e40c9)
![license](https://img.shields.io/badge/license-MIT-blue)

Part of the [alexar76 oracle family](../../README.md) — built natively on **`oracle-core`**, discoverable via **AIMarket Protocol v2** (signed manifest, priced invoke, signed receipts, measured metrics).

---

## The mathematics

Treat a graph as a vibrating drumhead. Build the adjacency `A` and degree `D`; the **combinatorial Laplacian** is `L = D − A` (the discrete `−∇²`), and the **symmetric normalized Laplacian** is `L_sym = I − D^{-1/2} A D^{-1/2}` (scale-invariant; spectrum in `[0, 2]`). Both are real symmetric PSD, so `numpy.linalg.eigh` gives an exact orthonormal eigendecomposition with `0 = λ₁ ≤ λ₂ ≤ …`.

- **λ₂ — algebraic connectivity (Fiedler value).** Exactly `0` iff the graph is disconnected; *small* when the graph has a narrow bottleneck (it is *near* a split).
- **Fiedler vector `v₂`** — the lowest-energy vibration mode. Its sign pattern is the canonical **spectral bisection** into two communities; the induced **cut size** and **conductance** quantify the bottleneck.
- **Spectral embedding** `(v₂, v₃, v₄)` — per-node coordinates in the space the connectivity implies (the basis of spectral clustering / graph drawing).

**Trustless verification.** Given the graph and a claimed eigenpair `(λ, x)`, a verifier checks `‖L x − λ x‖ / ‖x‖ ≤ tol` (it really is an eigenpair) and that `x ⟂` the trivial λ₁ eigenvector (so it is genuinely the connectivity mode). That certificate is **O(E)** — it proves λ₂ / Fiedler without redoing the O(n³) eigendecomposition.

---

## AIMarket capabilities

| Capability | Price | What you get |
|---|---|---|
| `fourier.spectrum@v1` | `$0.005` | bottom-k Laplacian eigenvalues, λ₂ + Fiedler vector, spectral cut (sets + cut size + conductance), per-node `(v₂,v₃,v₄)` embedding, `graph_commitment` |
| `fourier.verify@v1` | `$0.001` | cheap O(E) eigenpair certificate: `{valid, residual, orthogonality, graph_commitment}` |

### `fourier.spectrum@v1`

```jsonc
// input
{
  "edges": [["a","b"], ["b","c"], ["c","a", 2.0]],   // [u,v] or weighted [u,v,w]
  "nodes": ["a","b","c","d"],                          // optional (covers isolated nodes)
  "laplacian": "normalized",                           // "normalized" (default) | "combinatorial"
  "k": 6                                                // #smallest eigenvalues to return
}
// output
{
  "n": 4, "m": 3, "laplacian": "normalized",
  "eigenvalues": [0.0, 0.7, ...],
  "fiedler_value": 0.072,             // λ₂ of the selected Laplacian
  "combinatorial_lambda2": 0.298,     // always reported (dimensionful connectivity)
  "fiedler_vector": [ ... ],          // per node, in canonical (sorted-label) order
  "spectral_cut": { "set_a": [...], "set_b": [...], "cut_size": 1.0, "conductance": 0.048 },
  "embedding": [[v2,v3,v4], ...],     // per node
  "nodes": ["a","b","c","d"],
  "graph_commitment": "…sha256…"
}
```

### `fourier.verify@v1`

```jsonc
// input — re-derives L and checks the certificate
{ "edges": [...], "laplacian": "combinatorial", "lambda": 0.298, "vector": [ ... ] }
// output
{ "valid": true, "residual": 1e-12, "orthogonality": 0.0, "is_eigenpair": true, "graph_commitment": "…" }
```

`valid` is true iff the residual is within tolerance **and** the vector is non-trivial (not the all-ones / `d^{1/2}` λ₁ mode), so it genuinely certifies the connectivity mode.

---

## Notes

- **Size clamp.** The dense symmetric eigendecomposition is `O(n³)`; the handler clamps the graph to `MAX_NODES = 400`. The protocol layer does **not** validate input against the schema, so the handler validates required fields (raising `ValueError`, surfaced as `{ok:false, error}`) and enforces the ceiling.
- **Canonicalisation.** Node labels are sorted unique, undirected edges de-duplicated (parallel weights summed), self-loops dropped, and the graph hashed to a `graph_commitment` — the whole analysis is a pure function of that committed graph.
- **Determinism.** Eigenvector signs are arbitrary; the Fiedler vector is oriented deterministically (largest-magnitude component positive) so results are stable.

## Run

```bash
# from the monorepo root
PYTHONPATH="oracles/core:oracles/oracles/fourier" \
  platon/backend/.venv/bin/python -m pytest oracles/oracles/fourier/tests/ -q

# serve
FOURIER_PORT=9315 python -m fourier.main
```
