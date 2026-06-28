# Security Audit — Platon UMBRAL

Scope: the cryptographic and protocol mechanism behind Platon's market participation —
manifest signing, the chaos-VRF randomness (`platon.random@v1`), the hash-chained
beacon (`platon.beacon@v1`), invoke receipts, and federation. Honest assessment,
classical **and** quantum, with a hack-probability table and a hardening plan.

> TL;DR — the cryptographic *verifiability* is sound against classical adversaries
> (Ed25519 + SHA-256, correctly used and chain-linked). The realistic classical gaps
> are operational/design, not math: provider-side randomness grinding (no
> commit-reveal), a single on-disk signing key, an un-anchored beacon, and an open
> `/invoke`. The one quantum gap is singular and well-understood: **Ed25519 falls to
> Shor on a future quantum computer** (not today) — fixed by a hybrid → post-quantum
> signature migration. The SHA-256 layer is already quantum-safe (Grover → 2¹²⁸).

---

## 0. Implementation status (what's now in code)

The audit findings below have been acted on:

| Finding | Status |
|---------|--------|
| §2.3 Provider grinding 🔴 | ✅ **Commit-reveal implemented** — `platon.commit@v1` / `platon.reveal@v1` (`commit_reveal.py`): the server signs a commitment to a secret preimage *before* the client seed; output = `H(preimage‖client_seed)`. Neither party can grind. Verifiable; tested. |
| §3 Quantum / Ed25519 🔴 | ✅ **Hybrid PQC implemented** — `pqc_enabled` adds ML-DSA-65 (FIPS 204, via `dilithium-py`) alongside Ed25519; `verify_signature_object` requires both. Additive (Ed25519 unchanged → the hub still verifies). Off by default; tested when on. |
| §2.1 Key on disk 🟠 | ✅ **Env-injected key** — `PLATON_SIGNING_SEED_B64` sources the seed from a secrets manager/KMS, never touching disk. (Per-purpose keys / full HSM remain a deployment step.) |
| §2.4 Beacon not anchored 🟠 | ✅ **Signed checkpoints** — `POST /api/beacon/checkpoint` signs the chain head and pushes it to an optional external transparency log (`beacon_anchor_webhook`). The external log itself is operator-chosen. |
| §2.6 Open `/invoke` 🟠 | ✅ **Rate-limited** — fixed-window limiters on `/invoke` (120/min), `/api/dream` (60/min), `/api/ask` (30/min) → 429. Payment-channel gating stays hub-side. |

Remaining (deployment, not code): KMS/HSM custody, the external anchor log/chain, TLS termination, and the hub-side payment gate.

---

## 1. Assets & trust model

| Asset | Why it matters |
|-------|----------------|
| Ed25519 signing key (`data/platon_signing_key`, seed‖pub, chmod 600) | Signs manifest, receipts, randomness, beacon. Single root of authenticity. |
| Published `signer_public_key` (`/.well-known/ai-market.json`) | Consumers/hub pin it to verify everything. |
| Randomness unpredictability | The product. If predictable/biasable, the beacon is worthless. |
| Beacon chain integrity | Tamper-evidence / non-equivocation of past rounds. |
| Receipts | Payment-channel accounting integrity. |
| Availability | `/invoke` is the service. |

**Trust model.** Platon is a *single-party* signed provider. Consumers trust the pinned
public key (the hub pins it on federation). `/invoke` itself is unauthenticated and
free — the economic gate is the hub's payment channel, not Platon.

---

## 2. Classical attack surface

Rating = residual risk after current mitigations. (L)ow / (M)edium / (H)igh.

### 2.1 Signing-key compromise — **M**
Read `data/platon_signing_key` (host compromise, backup leak, container image) ⇒ forge
**everything**: fake manifests (impersonate Platon to the hub), forge receipts (payment
fraud), forge randomness/beacon (break the product). One key signs all purposes.
- *Now:* file is `0o600`, 64-byte `seed‖pub`, fails fast if wrong size.
- *Fix:* KMS/HSM or env-injected key; **separate keys per purpose** (manifest / receipt /
  randomness); rotation with key-id in the signature object.

### 2.2 Randomness predictability (external attacker) — **M**
`random = SHA256-expand( sha256(full-precision state bytes) ‖ prev_hash ‖ client_seed ‖ round ‖ timestamp )`.
- The only public view of state is `/api/state` + `/ws`, which expose amplitudes/phases
  **rounded to 4 decimals**. Reconstructing the exact `float64` preimage from that is
  infeasible — SHA-256 avalanche means any sub-ULP difference yields a totally different
  hash. So an external attacker **cannot** reproduce `state_hash`.
- ⚠️ This is *incidental* protection (telemetry rounding), not a designed guarantee. If
  the raw full-precision state were ever exposed, randomness becomes fully predictable.
- *Fix:* derive outputs through an explicit CSPRNG/KDF (HKDF over chaotic entropy **+ OS
  entropy**), and never expose full-precision state.

### 2.3 Provider-side grinding / last-look bias — **H** (the main design gap)
Platon sees `client_seed` **before** producing the output and controls `state`,
`tick`, `timestamp`. A malicious/compromised provider could try many `timestamp`/`tick`
values and pick an output biased toward a target — the classic "last revealer" problem.
Client-seed mixing stops *external* prediction but **not** provider bias.
- *Fix (removes the gap):* **commit–reveal** — publish `commit = H(state_hash ‖ round)`
  *before* receiving `client_seed`, then `output = H(commit ‖ client_seed)`; now neither
  party alone controls the result. Or adopt a *proven* construction: **RFC 9381 ECVRF**,
  or **drand-style threshold BLS** (distributed, no single biaser).
- Honest framing: as shipped, this is a *trusted signed beacon* (you trust Platon not to
  grind) — same trust class as any centralized RNG-as-a-service. For *trustless* use,
  adopt one of the above.

### 2.4 Beacon chain rewrite by the operator — **M**
The chain is tamper-evident to a third party *given the rounds*, but the single signer can
mint an alternative valid chain (re-sign from any point). No external anchor ⇒ equivocation
is possible.
- *Fix:* periodically anchor `round_hash` to an external immutable log (public chain /
  transparency log / drand round), so history can't be rewritten silently.

### 2.5 Receipt replay — **L–M**
Receipts carry `nonce` + `timestamp` but Platon keeps no nonce ledger; dedup/accounting is
the hub's responsibility. A replayed receipt could be presented twice.
- *Fix:* short receipt expiry + hub-side nonce store / channel dedup.

### 2.6 Unauthenticated `/invoke` → DoS / free compute — **M**
Open and free. `platon.dream` fits an OLS model (288×65 lstsq), others hash — all cheap,
but unbounded request rate exhausts CPU.
- *Now:* `num_bytes ≤ 64`, `prompt ≤ 500`, capability ids validated; CORS fixed (no
  `*` + credentials).
- *Fix:* rate-limit; run behind the hub so the **payment channel is the gate**.

### 2.7 Transport — **L (if TLS)**
Signatures protect integrity, but the **public key is delivered via `/.well-known`** — a
MITM before pinning could swap it. Serve over **HTTPS**; the hub already pins the key.

### 2.8 Input validation — **L**
`num_bytes` clamped, prompt length-limited, capability ids checked, `input_hash` is real
SHA-256, non-finite surrogate vectors are guarded. Good.

---

## 3. Quantum-cryptography analysis

Primitives: **Ed25519** (all signatures) and **SHA-256** (state/round/input hashes, the
expansion KDF, manifest `tools_hash`).

### 3.1 Shor vs Ed25519 — the principal quantum risk
A cryptographically-relevant quantum computer (CRQC) running **Shor's algorithm** solves
the elliptic-curve discrete log and **recovers the private key from the published public
key**. Consequence: forge manifests (impersonate Platon), forge receipts (payment fraud),
forge randomness/beacon rounds (break verifiability). Because signatures aren't
confidential there is **no "harvest-now, decrypt-later"** angle — the risk is *future
forgery* once a CRQC exists, not retroactive decryption.

- Resource estimate to break Curve25519: ~2330+ logical qubits and ~10⁹ Toffoli gates ⇒
  millions of error-corrected physical qubits. No such machine exists (today: hundreds to
  low-thousands of noisy physical qubits). Mainstream/NIST expectations, if a CRQC arrives
  at all, point to the **2030s+** — deeply uncertain.
- **Probability today: negligible (~0). Over a 10–15-year horizon: planning-relevant.**

### 3.2 Grover vs SHA-256 — safe
**Grover** gives only a quadratic speedup: preimage ≈ 2¹²⁸ (from 2²⁵⁶), and collisions are
bounded near 2¹²⁸ once realistic QRAM/parallelization costs are included. 2¹²⁸ work is
infeasible. ⇒ The **beacon hash-chain, `input_hash`, and the KDF expansion are
quantum-safe**; only the *signatures over them* are exposed. (SHA-384/512 would add margin
if ever desired.)

### 3.3 Net posture & PQC migration
The hashing/chain layer is quantum-safe; the **signature layer (Ed25519) is the single
quantum-exposed component**. Migration plan (NIST FIPS 204/205, Aug 2024):
- Primary: **ML-DSA (Dilithium, FIPS 204)**; or **SLH-DSA (SPHINCS+, FIPS 205)** for
  hash-based conservatism (security rests only on SHA → Grover-only).
- **Hybrid** during transition: sign with Ed25519 **‖** ML-DSA, verify both → safe if
  either holds. Coordinate with the hub (it verifies our manifest) — migration is joint.
- Crypto-agility is already partly in place: the signature object carries an `algorithm`
  field; extend its enum (`ml-dsa-65`, `slh-dsa-sha2-128s`, …) and emit dual signatures.

---

## 4. Hack-probability summary

| Vector | Classical (today) | Quantum (CRQC era) |
|--------|------------------|--------------------|
| Forge signatures (manifest/receipt/beacon) | Very low (needs key theft) | **High without PQC** — Shor recovers the key |
| Predict randomness (external) | Low (secret full-precision state + rounding) | Low (quantum can't predict chaos or un-round state) |
| Provider grinds/biases randomness | **Medium–High** (no commit-reveal) | unchanged (design, not crypto) |
| Beacon rewrite by operator | Medium (single signer, no anchor) | unchanged |
| Hash collision/preimage (chain) | Negligible | Negligible (Grover → 2¹²⁸) |
| DoS on open `/invoke` | Medium | unchanged |
| Key-file theft on host | Medium (chmod 600 only) | unchanged |

---

## 6. Randomness quality — tested

Two axes: statistical quality of the output, and unpredictability of the source.

**Statistical quality — confirmed.** The NIST SP 800-22 core battery
(`scripts/randomness_battery.py`) passes on a 1 MB sample with healthy mid-range
p-values, matching an `os.urandom` control: Monobit 0.26, Block-frequency 0.49,
Runs 0.26, Cumulative-sums 0.50, Approximate-entropy 0.24, Serial 0.28,
Spectral-DFT 0.40; Shannon entropy 7.99983/8.0 bits/byte; incompressible (zlib/bz2/lzma ratio ≥ 1.0).

**Adversarial cross-check — passed.** Six independent blind distinguishers tried
to tell Platon's output from `os.urandom`: compression, autocorrelation
(Ljung-Box), n-gram χ², run-length, spectral/FFT, and birthday-collisions. **5 of
6 could not distinguish** and found Platon clean. The 6th flagged "zero 32-bit
collisions" in one sample — but re-running on 5 fresh samples gives [7,5,6,8,10]
(mean 7.2) vs `os.urandom` [11,7,5,10,7] (mean 8.0): the deficit was one-sample
noise, not a structural bias. (This is exactly why adversarial findings get
verified before being believed.)

**Unpredictability of the source.** As originally shipped the chaos draw was a
*deterministic* function of public inputs (a PRG, not a TRNG). Fresh OS-CSPRNG
entropy is now mixed into every `platon.random`/beacon seed (commit-reveal already
had it via `server_nonce`), with a signed `entropy_commitment` — so the output is
genuinely unpredictable and non-reproducible while staying signature-verifiable.

**Verdict.** Suitable as a statistical/utility RNG and a verifiable beacon
(signed, hash-chained, commit-reveal bias-resistant), and — with OS entropy now
mixed in — for crypto-grade unpredictability. For *trustless* (no-trust-in-Platon)
guarantees, the remaining step is a threshold/ECVRF construction (§2.3).

## 5. Prioritised hardening checklist

1. **Trustless randomness:** commit-reveal, or RFC 9381 ECVRF / drand threshold — closes §2.3.
2. **Key custody:** KMS/HSM or env-injected key; rotation; per-purpose keys — closes §2.1.
3. **Anchor the beacon:** publish `round_hash` to an external transparency log / chain — closes §2.4.
4. **Post-quantum:** hybrid Ed25519 + ML-DSA signatures; extend the `algorithm` enum — closes §3.
5. **Edge hardening:** TLS everywhere; rate-limit `/invoke`; receipt expiry + hub nonce dedup — closes §2.5–2.7.

*Audited against the code in `backend/platon/{signing,randomness,aimarket,main}.py` as of this commit.*
