# Chronos — security & transparency

Chronos is a **Wesolowski verifiable delay function** (proof-of-elapsed-sequential-work).
This document is the setup transparency, parameters, and honest security analysis a reviewer
needs before trusting it with value. Implementation: [`chronos/vdf.py`](chronos/vdf.py).

## Setup transparency — no trusted setup, no trapdoor

`N` is the **canonical RSA-2048 challenge number** (RSA Factoring Challenge). RSA Labs
generated it and **discarded the primes `p, q`**, so the group order `φ(N)` is unknown to
*everyone — including this operator*. That is exactly what makes the VDF trustless: there is
**no setup ceremony** and **no trapdoor**, because nobody can shortcut `g^(2^T)` via
`2^T mod φ(N)`.

Anyone can verify the code uses the canonical modulus, not a self-generated one (a
self-generated `N` would let its author bias every result):

```bash
python -c "import hashlib,chronos.vdf as v; print(v.RSA_2048.bit_length(), len(str(v.RSA_2048)), hashlib.sha256(str(v.RSA_2048).encode()).hexdigest())"
# → 2048 617 b3c2468add10e2a0c4a251d9d2bac4ba04d4b3527156ceead43a1305e03f1fc0
```

`vdf.py` also carries an **import-time assert** (`bit_length == 2048`) so a corrupted modulus
fails fast rather than silently voiding security. (This caught a real 2-digit transcription
corruption — the constant was 2055-bit; now pinned by test to the canonical 2048-bit value.)

## Parameters

| Item | Value |
|------|-------|
| Group | `(Z/NZ)*`, `N` = RSA-2048 (unknown order) |
| Generator | `g = hash_to_group(seed)` — SHA-256 (domain `chronos-g\|`) expanded to 256 B, `mod N`, `≥ 2` |
| Delay | `y = g^(2^T) mod N`, `T` **sequential** squarings |
| Difficulty `T` | `difficulty`, clamped to `[1, 1_000_000]` (`MAX_DIFFICULTY`) |
| Challenge prime `ℓ` | `hash_to_prime(g,y,T)` — **128-bit**, SHA-256 (domain `chronos-l\|`) + counter, Miller–Rabin (deterministic small-base witnesses); Fiat–Shamir → non-interactive |
| Proof | `π = g^(⌊2^T / ℓ⌋) mod N`; prover returns `(y, π, ℓ, T)` |

## Verification (constant, ~15 ms)

1. Recompute `ℓ' = hash_to_prime(g,y,T)`; **reject if `ℓ' ≠ ℓ`** — binds the proof to the
   exact transcript (no chosen-challenge forgery).
2. `r = 2^T mod ℓ`.
3. Accept **iff `π^ℓ · g^r ≡ y (mod N)`** — two modular exponentiations.

Plus input validation: `T ∈ [1, MAX_DIFFICULTY]`, group elements in `[0, N)`, `ℓ` a plausible
128-bit prime, integer types. Tampered `y` / `π` / `ℓ` / `T` and malformed inputs are rejected
(see [`tests/test_chronos.py`](tests/test_chronos.py) → `TestVDFHardening`).

## Security analysis (honest)

- **Soundness ≈ 128-bit** — Wesolowski, under the adaptive-root assumption, from the 128-bit
  challenge prime `ℓ`.
- **Sequentiality** — RSW time-lock assumption: no known parallel speed-up for repeated
  squaring in a group of unknown order; wall-clock depth ∝ `T`.
- **Hardness anchor ≈ 112-bit classical** — RSA-2048 factoring / unknown-order (NIST level).
- **Grinding resistance** — even the operator cannot bias the output without redoing all `T`
  squarings; this is what makes the Chronos×Platon randomness beacon unbiasable.

## Threat model

- **No secret exists in the system.** `N`'s factorization is unknown to *everyone* (incl. the
  operator); `g, y, π, ℓ, T` are all public. Therefore **timing / side-channel attacks on the
  squaring are not applicable** — there is no secret key to leak (unlike signatures/KEMs).
- **Malformed / forged proofs** — rejected by transcript binding + input validation (tested).
- **Resource abuse (DoS)** — `T` capped at `MAX_DIFFICULTY`; capability is priced per call;
  deploy behind the oracle-core rate limit + a request timeout.
- **Corrupted modulus** — import-time assert + a pinned canonical-fingerprint test.
- **Quantum** — Shor factors `N` and breaks the unknown-order assumption; class-group VDFs are
  the post-quantum successor. RSA-2048 is the standard *classical* hardness anchor today.

## Maturity & audit status (honest)

- Constructions are **standard and unit-tested** (Wesolowski VDF, Fiat–Shamir, canonical RSA
  challenge modulus; valid + adversarial tests pass).
- **Not independently audited.** No published audit PDF, no formal verification artifacts, no
  third-party security analysis document separate from this repo.
- **Parameter publication gap:** modulus and algorithm constants are in [`chronos/vdf.py`](chronos/vdf.py),
  but there is **no operator-facing guide** mapping `T` (iteration count) to wall-clock delay on
  reference hardware, security margin vs hardware speedups, or recommended policies per use case
  (lottery beacon vs fair ordering).
- **Ecosystem context:** the full seventeen-oracle family was built in roughly two months — strong
  for research/demo integration, **not** credible as a fully hardened cryptographic service without
  the items above. See [`docs/crypto-maturity.en.md`](../../docs/crypto-maturity.en.md).

For high-value money flows, get an external cryptographic review before relying on Chronos as the
sole trust anchor. Until then, treat it as a well-constructed but **unaudited research-grade**
primitive — useful for grinding-resistance experiments and testnet lottery, not a substitute for a
reviewed production VDF service.

## Reporting

Found a cryptographic issue? Open a GitHub issue on the oracle family repo (or contact the
maintainer) — please do not post working exploits publicly before a fix.
