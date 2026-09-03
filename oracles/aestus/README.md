# Aestus — RSW Time-Lock Puzzles

**Seal the future for the AI agent economy.** Aestus time-locks data so that **nobody can open it before ~T sequential squarings of wall-clock have elapsed** — and then **anyone** can open it, with no trapdoor holder, no key escrow, no trusted timestamper. Where [Chronos](../chronos) *proves the past elapsed* (a VDF), Aestus *locks the future*.

![tests](https://img.shields.io/badge/tests-passing-brightgreen)
![protocol](https://img.shields.io/badge/AIMarket-v2-6e40c9)
![license](https://img.shields.io/badge/license-MIT-blue)

> **Landing:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · **Oracle family:** [oracles](../../README.md)
Part of the [alexar76 oracle family](../../README.md) — built natively on **`oracle-core`**, discoverable via **AIMarket Protocol v2** (signed manifest, priced invoke, signed receipts, measured metrics).

---

## How it works

Rivest–Shamir–Wagner (1996) time-lock puzzle:

```
b = a^(2^T) mod N            # T SEQUENTIAL squarings — the enforced delay
key = SHA256(b)
ciphertext = plaintext XOR keystream(key)     # SHA256-CTR keystream
key_commitment = SHA256("aestus-commit" | b)  # binds the unlock value b
```

Opening recomputes `b` by redoing the `T` squarings, derives the same key, decrypts, and checks `b` against `key_commitment`. Because the squaring chain `b_i = b_{i-1}^2 mod N` is inherently **sequential** while the order of `Z_N*` is unknown, no amount of parallelism opens the puzzle faster than ~`T` squarings on one core. The delay is enforced by math, not by a clock an attacker controls.

### Crypto honesty — why the oracle can't cheat

The trustless property ("nobody opens early, **not even us**") holds only if the factorisation of `N` — and hence `φ(N)` — is unknown to everyone, **including the oracle**. A holder of `φ(N)` could shortcut `e = 2^T mod φ(N)`, `b = a^e mod N` and open any puzzle instantly. So Aestus, on **every** seal:

1. generates a **fresh** modulus `N = p·q` (never a shared/fixed `N` whose factors it might retain),
2. derives `b` by `T` **sequential squarings** — it deliberately does **not** use the `φ(N)` shortcut even though it momentarily holds `p, q`,
3. **burns** `p, q, φ(N)` before returning — they never appear in the puzzle.

**Honest tradeoff:** because `φ` is burned, **sealing costs the same `T` squarings as opening** (seal-work == open-work). The `φ` shortcut would make sealing `O(1)`, but keeping `φ` around would let the operator decrypt early — which breaks the whole model. We take the slow, honest path on purpose.

Pure Python: a self-contained Miller–Rabin primality test + random-prime generator, `hashlib`, `secrets`, big-int math. No numpy / sympy / scipy.

---

## AIMarket capabilities

| ID | What agents buy | Price |
|----|-----------------|-------|
| `aestus.seal@v1` | **Time-lock data** — fresh `N`, `b = a^(2^T) mod N` via `T` sequential squarings, encrypt under `SHA256(b)`, burn the factorisation. Returns a self-contained puzzle (no trapdoor). | $0.006 |
| `aestus.open@v1` | **Open a puzzle** — redo the `T` squarings to recover `b`, decrypt, verify against the commitment. Anyone can call it once enough time has elapsed. | $0.01 |
| `aestus.verify@v1` | **Cheap trustless check** — confirm a claimed unlock value `b` against `key_commitment` in ~one hash, no `T` squarings. | $0.001 |

> Every `invoke` returns a signed 7-field protocol **receipt** and a `sha256` `input_hash`. The handler clamps `T` to `[1, MAX_T = 5_000_000]` and caps `modulus_bits` — the protocol layer does not validate input, so the oracle enforces the ceilings (a DoS guard, exactly like Chronos clamps difficulty).

---

## Use cases (agent economy)

- **Sealed-bid auctions / commit-reveal without a reveal phase.** Bidders seal bids with a `T` tuned to the auction window; nobody — including the auctioneer — can peek before close, then everyone opens trustlessly.
- **Dead-man switches & timed disclosure.** An agent seals a secret (credentials, a will, a whistleblow payload) that becomes openable only after a verifiable delay, with no escrow agent to compromise.
- **Anti-front-running release.** Lock an action's parameters so they cannot be read until enough sequential work has elapsed for the market to settle.
- **Fair coordinated reveals.** A swarm seals commitments at `t0`; all become openable together at `t0 + delay`, with no trusted coordinator gating the unlock.

---

## Invoke (curl)

```bash
# Discover
curl -s http://localhost:9312/.well-known/ai-market.json | jq .
curl -s http://localhost:9312/ai-market/v2/manifest | jq '.tools[].capability_id'

# Seal — returns a puzzle {N, a, T, ciphertext, key_commitment, ...}
curl -s -X POST http://localhost:9312/ai-market/v2/invoke \
  -H "Content-Type: application/json" \
  -d '{"capability_id":"aestus.seal@v1","input":{"data":"open me later","T":200000}}'

# Open — feed the puzzle straight back in (does the T squarings)
curl -s -X POST http://localhost:9312/ai-market/v2/invoke \
  -H "Content-Type: application/json" \
  -d '{"capability_id":"aestus.open@v1","input":{"puzzle":{ ... }}}'

# Verify — cheap one-hash check that a claimed b matches the commitment
curl -s -X POST http://localhost:9312/ai-market/v2/invoke \
  -H "Content-Type: application/json" \
  -d '{"capability_id":"aestus.verify@v1","input":{"puzzle":{ ... },"b":"..."}}'
```

---

## Run & test

```bash
# From the monorepo root
PYTHONPATH="oracles/core:oracles/oracles/aestus" platon/backend/.venv/bin/python -m pytest oracles/oracles/aestus/tests/ -q

# Serve
PYTHONPATH="oracles/core:oracles/oracles/aestus" platon/backend/.venv/bin/python -m aestus.main   # → http://localhost:9312
```

Tests run with a small `T` (≈2000) so seal/open stay fast.

---

## Visual

**THE THAW VAULT** — a sealed payload (glowing core) encased in a prism of `T` nested translucent glass shells. ~8 ghostly worms spiral in to parallelise the lock and all stall at the same single frozen link (sequentiality). Time elapses; the shells thaw and peel away one-by-one, icy-teal warming to amber, until the last melts and the core ignites and opens. Then it re-seals and loops. See [`frontend/src/scenes/aestus.tsx`](../../frontend/src/scenes/aestus.tsx).

---

## License

MIT — [alexar76](https://github.com/alexar76) oracle family
