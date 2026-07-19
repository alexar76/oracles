# Gauss — Gaussian-Process Regression Oracle

**A principled posterior over functions for the AI agent economy.** Gauss turns sparse, noisy observations into a calibrated predictive distribution — a mean *and* an honest uncertainty everywhere — and tells an agent the single best next point to sample. It is the principled replacement for hand-rolled UCB / bandit exploration: the uncertainty is computed, not tuned.

![tests](https://img.shields.io/badge/tests-passing-brightgreen)
![protocol](https://img.shields.io/badge/AIMarket-v2-6e40c9)
![license](https://img.shields.io/badge/license-MIT-blue)

> **Landing:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · **Oracle family:** [oracles](../../README.md)
Part of the [alexar76 oracle family](../../README.md) — built natively on **`oracle-core`**, discoverable via **AIMarket Protocol v2** (signed manifest, priced invoke, signed receipts, measured metrics). Pure **numpy** (no scipy).

---

## The mathematics

A Gaussian process places a distribution over functions: every finite set of points is jointly Gaussian, specified by a zero mean and the **RBF / squared-exponential kernel**

```
k(x, x') = σ_f² · exp( −‖x − x'‖² / (2 · l²) )
```

with signal variance `σ_f²` (vertical scale), length-scale `l` (how far correlations reach), and i.i.d. observation noise `σ_n²`. Given training inputs `X` (n×d) and targets `y`, the noisy covariance is `K = k(X,X) + σ_n²·I`. We never invert `K` — following Rasmussen & Williams (Algorithm 2.1) we Cholesky-factor `K = L Lᵀ`, solve `α = Lᵀ \ (L \ y)`, and at query points `Xq`:

```
mean = K_qx · α
v    = L \ K_qxᵀ
var  = diag(K_qq) − Σ (v ⊙ v)      (clamped ≥ 0)
```

The posterior variance is the calibrated uncertainty: it collapses to the noise floor `σ_n²` at an observation and rises to the prior `σ_f²` far from any data. **Expected Improvement** turns that posterior into the next experiment to run:

```
EI(x) = (μ − f_best − ξ)·Φ(z) + σ·φ(z),   z = (μ − f_best − ξ) / σ
```

with Φ/φ implemented from `math.erf` (no scipy). The arg-max candidate is the suggestion.

---

## AIMarket capabilities

| ID | What agents buy | Price |
|----|-----------------|-------|
| `gauss.field@v1`   | **GP posterior field** — predictive `mean`, `var`, `std` at every query point | $0.006 |
| `gauss.suggest@v1` | **Best next experiment** — Expected Improvement over candidates or a bounds+grid (max/min) | $0.006 |
| `gauss.verify@v1`  | **Trustless replay** — recompute the posterior at a few points and check claimed mean/var | $0.001 |

> Every `invoke` returns a signed protocol **receipt** + `sha256` `input_hash`. The protocol layer does **not** validate `input_schema`, so the handlers validate required fields and **clamp** sizes (≤ 200 observations, ≤ 2048 query/candidate points) to stay DoS-safe.

---

## Use cases (agent economy)

- **Bayesian optimization / active learning.** An agent tuning a costly black box (a prompt, a fee, a controller gain) calls `gauss.suggest@v1` to get the EI-optimal next trial — calibrated exploration instead of a hand-tuned `ε`-greedy or UCB constant.
- **Uncertainty-aware decisions.** `gauss.field@v1` gives an agent the variance, not just a point estimate, so it can abstain / ask-for-data where the model is unsure (the fog is fat).
- **Trustless model audit.** A counterparty re-derives the posterior at a few points with `gauss.verify@v1` and confirms the claimed mean/variance bit-for-bit — no trust in the oracle.

---

## Invoke (curl)

```bash
curl -s http://localhost:9311/ai-market/v2/manifest | jq '.tools[].capability_id'

# Posterior field
curl -s -X POST http://localhost:9311/ai-market/v2/invoke -H 'Content-Type: application/json' \
  -d '{"capability_id":"gauss.field@v1","input":{"X":[[0],[1],[2]],"y":[0,0.84,0.91],"query":[[0.5],[1.5]]}}'

# Best next experiment by Expected Improvement
curl -s -X POST http://localhost:9311/ai-market/v2/invoke -H 'Content-Type: application/json' \
  -d '{"capability_id":"gauss.suggest@v1","input":{"X":[[0],[1],[2]],"y":[0,0.4,0.8],"bounds":[[-1,5]],"grid":64}}'
```

---

## Run & test

```bash
# From the monorepo root
PYTHONPATH="oracles/core:oracles/oracles/gauss" platon/backend/.venv/bin/python -m pytest oracles/oracles/gauss/tests -q

# Serve
PYTHONPATH="oracles/core:oracles/oracles/gauss" platon/backend/.venv/bin/python -m gauss.main   # → :9311
```

Env: `GAUSS_PORT` (9311), `GAUSS_PUBLIC_URL`, `GAUSS_SIGNING_KEY`, `GAUSS_CORS_ORIGINS`.

---

## Visual — "The Breathing Posterior"

A live cosmic scene (`oracles/frontend/src/scenes/gauss.tsx`): a 1D function on a curved sheet wrapped in a translucent indigo **±2σ fog band** that *breathes* — fat where there is no data. Glowing observation points rain in one by one; as each lands the fog **deflates** into a tight pinch and the cyan posterior-mean ribbon re-fits through the data. The real RBF/Cholesky posterior is recomputed every frame.

## License

MIT — [alexar76](https://github.com/alexar76) oracle family
