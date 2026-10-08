# Oracle family — cryptographic maturity (honest)

This document states what the **seventeen-oracle family** is — and is not — from a
cryptography and production-hardening perspective. Read it before treating oracle outputs as
the sole trust anchor for high-value money flows.

**Related:** [Chronos SECURITY.md](../oracles/chronos/SECURITY.md) ·
[oracle-core SIGNING.md](../core/docs/SIGNING.md) ·
[Factory known-issues (KI-6)](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)

---

## Executive summary

| Claim in marketing | Honest status (2026-07) |
|--------------------|-------------------------|
| Seventeen verifiable-math oracles | **True** — live capabilities, unit tests, AIMarket v2 integration |
| Ed25519-signed manifests & receipts | **True** — canonical forms match the Hub |
| Hybrid post-quantum (Ed25519 + ML-DSA-65) | **Partial** — implemented in `oracle-core`, **off by default**; Hub verifies Ed25519 only; no external crypto review |
| Chronos Wesolowski VDF | **Research-grade primitive** — standard construction, parameters in source, **not independently audited**, no formal verification |
| Hardened production cryptographic service | **False today** — see below |

The family was built in roughly **two months** of focused engineering. That is enough for a
**strong research / prototype** stack (correct math, tests, demos, lottery integration) — not
enough for a **fully hardened** cryptographic service with published setup ceremonies, external
audits, and proof-of-correctness artifacts reviewers expect before mainnet-scale TVL.

---

## Chronos (Wesolowski VDF)

**What exists in-repo**

- Fixed **RSA-2048 challenge modulus** (not per-request generation) — see
  [`chronos/vdf.py`](../oracles/chronos/chronos/vdf.py).
- Documented parameters: generator derivation, `T` clamp `[1, 1_000_000]`, 128-bit Fiat–Shamir
  challenge prime, verification equation.
- Unit tests including adversarial cases; Foundry test-vector alignment for on-chain consumers.
- [SECURITY.md](../oracles/chronos/SECURITY.md) with setup transparency and threat model.

**What a hardened production VDF service would still publish — and we do not yet**

| Gap | Why it matters |
|-----|----------------|
| **Published parameter-selection guide** | Operators need `T` ↔ wall-clock mapping on reference hardware, security margin vs ASIC/GPU speedups, and recommended values per use case (lottery vs ordering). Today `T` is caller-chosen within a cap. |
| **Standalone security analysis** | A reviewer-facing document (assumptions, adaptive-root usage, RSA-2048 anchor, grinding bounds) separate from README prose — suitable for citation in an audit scope letter. |
| **External cryptographic audit** | No Trail of Bits / NCC / similar report; no public audit PDF. |
| **Formal verification** | No Coq/Lean/TLA+ (or third-party) proofs tying implementation to Wesolowski semantics. |
| **Operational transparency** | No public attestation log of modulus fingerprint, deployed `T` policies, or hardware profiles used in production. |

**Until closed:** use Chronos for **demos, testnet lottery, and grinding-resistance experiments**.
Do not treat it as the only trust anchor for large real-money flows without an independent review.

---

## Signing & oracle-core

**What exists**

- Shared [`oracle_core/signing.py`](../core/oracle_core/signing.py): Ed25519 for manifests and
  receipts; optional **additive** ML-DSA-65 (FIPS 204 via `dilithium-py`) when `ORACLE_PQC=1`.
- Hybrid verify requires **both** signatures when PQ fields are present.
- Tests in `core/tests/test_core.py` and Platon signing tests (skipped if `dilithium-py` absent).

**What is still thin**

| Gap | Detail |
|-----|--------|
| **Normative hybrid spec** | AIMarket Protocol v2 documents Ed25519 receipts; the PQ extension (`pq_algorithm`, `pq_public_key`, `pq_value`) is **implementation-defined** in oracle-core, not a frozen RFC with test vectors in `aimarket-protocol`. |
| **Hub parity** | Live Hub verification path checks **Ed25519 only**; PQ fields are ignored unless the consumer implements `verify_signature_object`. |
| **Default posture** | PQC is **off** in production configs; the README badge describes capability, not deployment state. |
| **Proof-of-correctness** | No independent review of canonical string formats, key lifecycle, or hybrid composition (e.g. binding PQ key to Ed25519 identity). |
| **Key management** | File-based keys (`data/*_signing_key`, chmod 600) — no HSM/KMS integration guide for oracle operators. |

**Specification:** [core/docs/SIGNING.md](../core/docs/SIGNING.md) — describes what the code
does today; not a substitute for audit or protocol freeze.

---

## Seventeen oracles — scope vs depth

Each oracle ships **domain math + invoke handler + tests + portal scene**. Shared infrastructure
(protocol, signing, metrics, rate limits) is real and reused.

What **cannot** be done credibly in a short sprint for all seventeen:

- Per-oracle cryptographic threat models reviewed by outsiders
- Side-channel analysis of hot paths
- Constant-time guarantees on non-crypto oracles (many are numerical, not constant-time by design)
- Unified security incident response and key-rotation runbooks

**Honest tier:** **research / prototype** with production-*style* integration (Hub, lottery,
on-chain vectors for Chronos/Sortes). **Not** a bank-grade or L1-grade crypto service.

---

## Acceptance criteria (path to “hardened”)

We will treat the oracle crypto layer as **production-hardened** only when **all** of the
following are true (tracked as [KI-6](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)):

1. External cryptographic audit report published (scope: `oracle-core` signing, Chronos VDF,
   Sortes ECVRF at minimum).
2. Chronos: published parameter guide + operator attestation checklist.
3. Hybrid PQC: normative extension in `aimarket-protocol` with negative test vectors; Hub
   verifies both layers when present.
4. Key-management runbook (rotation, compromise, multisig or HSM option) for oracle operators.

Until then: **testnet, demos, and bounded pilots only** — aligned with the Factory
[pre-mainnet checklist](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md).

---

## Reporting

Cryptographic issues: open a GitHub issue on [alexar76/oracles](https://github.com/alexar76/oracles)
with `[crypto]` in the title. Do not post working exploits publicly before a fix.

**Other languages:** [crypto-maturity.ru.md](crypto-maturity.ru.md)
