# Chronos — parameter guide and operator checklist

*KI-6 item 2. Measured 2026-10-12. [Русская версия](PARAMETERS.ru.md).*

Chronos is a Wesolowski verifiable delay function in the RSA group of unknown order: it computes
`y = g^(2^T) mod N` by `T` sequential squarings and proves it with a Fiat–Shamir challenge prime.
This page says what `T` buys, measured, and what an operator must check before calling the output
a delay or a randomness beacon.

## 1. What is fixed in code

| Parameter | Value | Why |
|---|---|---|
| Modulus `N` | RSA-2048 challenge number (2048 bits) | Its factorization is unknown to anyone (RSA Labs discarded the primes), so nobody knows the group order and nobody can shortcut the squarings. No setup ceremony, no trapdoor. `sha256(str(N)) = b3c2468a…f1fc0`. |
| `T` range | `1 … 1 000 000` (`MAX_DIFFICULTY`) | Caps the CPU one request can take. |
| Challenge prime `l` | 128-bit, from `sha256("chronos-l"‖counter‖g‖y‖T)` | Fiat–Shamir binds `l` to the exact transcript. Miller–Rabin uses 12 fixed bases plus 10 bases derived from the candidate, because fixed bases alone are not deterministic at 128 bits and could be ground against. |
| `g` | `hash_to_group(seed)`, 2176 hashed bits reduced mod `N`, range `[2, N−2]` | 128 extra bits make the reduction uniform to within 2⁻¹²⁸; `0, 1, N−1` are degenerate (their powers do not depend on `T`) and are excluded. |
| Output | `y_canonical = min(y, N − y)`; `output = sha256("chronos-out"‖g‖T‖y_canonical)` | See §3: `y` and `N − y` both verify. |

## 2. Measured cost

Pure-Python big integers, as Chronos runs today:

| Machine | per squaring | `T = 100 000` evaluate | prove | verify |
|---|---|---|---|---|
| production oracle host (x86_64, Python 3.11) | **10.5 µs** | 1.05 s | 1.24 s | 4.7 ms |
| Apple M-series laptop (arm64, Python 3.12) | 7.9–8.3 µs | 0.83 s | 0.92 s | 3.2 ms |
| same laptop, GMP (`gmpy2` 2.3.2) | **0.88 µs** | 0.09 s | — | — |

So `T = 1 000 000` takes the honest prover about **10.5 s to evaluate and ~12 s to prove** on the
production host, while **an adversary with an ordinary laptop and GMP needs ~0.9 s**. Dedicated
hardware is faster again; this page does not guess by how much.

## 3. Choosing `T` — the delay is set by the fastest adversary, not by us

A VDF promises that the output could not be known **before `T` sequential squarings had been
done by the fastest party that wanted it early**. The guaranteed delay is therefore

```
delay_guaranteed  =  T × t_adversary          (t_adversary = fastest per-squaring time you must assume)
delay_honest      =  T × t_prover             (what your callers wait)
```

With the measurements above, `t_prover / t_adversary ≈ 12` against commodity GMP. Consequences:

- **`difficulty` is not a wall-clock promise.** At the cap, Chronos guarantees roughly one second
  against a laptop with GMP, while the honest call takes about ten. Never advertise "≥ 10 s" from
  `T = 1 000 000`.
- **Ordering and short fairness windows** (who committed first, a sub-second sealed interval) are
  what the current parameters support honestly.
- **Longer guaranteed delays need a faster prover, not a larger cap.** Raising `MAX_DIFFICULTY`
  with the Python prover raises the honest cost linearly and widens nothing else; moving the
  squaring loop to GMP closes most of the 12× gap first.
- **Beacons:** the seed must be fixed and unpredictable before the delay starts (e.g. a committed
  value or another oracle's output). A seed the requester chooses can be ground: they can try
  many seeds and keep the one whose output they like.

### `y` versus `N − y` (found 2026-10-12)

`−1` has order 2 in `Z_N*`, and Wesolowski's check cannot distinguish `y` from `N − y`: binding
`l` to the transcript does not help, because the prover derives `l′` for `N − y` and presents
`N − π′`, at the cost of one ordinary proof and no secret. Both proofs are valid. A raw `y` is
therefore **not** unique — a prover could show either and keep the one it prefers, one bit of
bias in a beacon. Chronos now reports `y_canonical` and `output`, which are the same for both
signs; **consumers MUST bind to `output` (or `y_canonical`), never to raw `y`.** Both proofs keep
verifying, so nothing already issued breaks. Tests: `tests/test_vdf_sign_ambiguity.py`.

## 4. Operator checklist

Before advertising Chronos output as a delay or a beacon, an operator confirms and publishes:

1. **Modulus** — `sha256(str(vdf.RSA_2048)) == b3c2468add10e2a0c4a251d9d2bac4ba04d4b3527156ceead43a1305e03f1fc0`
   and `N.bit_length() == 2048` (the module asserts the second at import).
2. **Code** — the commit of `chronos/vdf.py` that is serving, and that `verify` refuses the
   degenerate `g ∈ {0, 1, N−1}` and `T` outside `[1, MAX_DIFFICULTY]` (both in `tests/`).
3. **Measured `t_prover`** on the serving hardware (`T = 100 000`, three runs, median), and the
   `t_adversary` it assumes, with its source. Publish the ratio; it is the honest statement of
   what `T` means.
4. **Claimed delay** = `T × t_adversary`, never `T × t_prover`.
5. **Output binding** — clients are told to use `output`, and the beacon's seed source is named
   and shown to be fixed before evaluation starts.
6. **Signing** — the response signature key's fingerprint, and that verifiers apply the strict
   Ed25519 rule (aimarket-protocol §7.3.7). Key handling: `../../../docs/key-management.en.md`.
7. **Re-run** items 1–3 after every deploy that touches `vdf.py` or the host.

## 5. What remains outside the code (KI-6)

No external cryptographic review of this implementation has been published, and no formal
verification exists. The checks above are self-verification: they find and fix what can be found
in-repo, and they do not substitute for an independent audit before a high-value use.
