# Oracle key management — runbook for operators

*KI-6 item 4. Written 2026-10-12 against `oracle_core` and the hub as they run. [Русская версия](key-management.ru.md).*

## 1. The keys an oracle holds

| Key | Where it lives | Created | Published as |
|---|---|---|---|
| **Ed25519 signing key** (signs every response, manifest and receipt) | the file at the oracle's signing-key path (e.g. `SORTES_SIGNING_KEY`, default `data/<oracle>_signing_key`): 64 bytes, seed ‖ public key | on first start, mode `0600`, `O_EXCL` | `signature.public_key` / the manifest's signer key |
| — override | `ORACLE_SIGNING_SEED_B64` (a 32-byte seed) in the environment | — | **wins over the file** |
| **ML-DSA-65 key** (post-quantum half, when `ORACLE_PQC=1`) | `<signing-key path>_mldsa`: two hex lines, public then secret | on first start with PQC on, `0600` | `signature.pq_public_key` |
| **Sortes VRF secret** (decides every draw) | `SORTES_VRF_SK` (64 hex) or the file at `SORTES_VRF_SK_PATH` (default `data/sortes_vrf_sk`) | on first start, `0600` from the first byte (fixed 2026-10-12; it used to be written, then chmod-ed) | the `public_key` in every draw |

Hubs pin an oracle's Ed25519 key the first time they crawl it, and its ML-DSA key on first
sight. Every hub that pinned a key refuses — fail closed — anything signed by another one.

## 2. Storage rules

- Keys live only on the oracle's data volume (or in a root-only env file). Never in git, never in
  an image layer, never printed: logs and support output name variables, not values.
- **One source of truth.** An env seed silently beats the key file. On 2026-08-27 a seed added to
  `.env` re-published ATLAS under a new identity; both hubs that had pinned the old key rejected
  every crawl and served a catalogue missing a capability for five days, with nothing red
  anywhere. ATLAS now refuses to start when env seed and file disagree unless
  `ATLAS_SIGNING_ALLOW_KEY_ROTATION=1`. Apply the same rule by hand to every oracle: if you set
  the seed, delete or reconcile the file in the same change, and keep the laptop copy in step.
- Back the volume up encrypted and off-host (the ecosystem's borg backups do), so a lost disk is
  not a forced rotation.
- Run the oracle as a non-root user (the images use uid `10001`) with no shell on the host for
  anyone who does not need one.

## 3. Planned rotation

1. **Find every pin.** `GET /ai-market/v2/federation/peers` on every hub that indexes the oracle.
   The direction of the fix depends on it: when more hubs pin the old key than the new one,
   reverting is cheaper than re-pinning (the ATLAS case).
2. **Make the new key.** Stop the oracle, move the old key file to offline storage (do not delete
   it — §5), start the oracle so it creates a fresh one, or set a new seed and reconcile the file.
3. **Expect `key_mismatch`.** Each pinning hub now rejects the oracle and keeps serving the last
   catalogue it indexed. Nothing else goes red; check the hubs' peer status, not the oracle.
4. **Re-pin.** Each hub operator calls `POST /ai-market/v2/federation/peers/repin`, with
   `pq_public_key` too when PQC is on.
5. **VRF key (Sortes).** A new VRF key changes every future draw's public key. Draws issued under
   the old key stay verifiable only against the old public key: keep publishing it, with the
   time window it was valid for, and announce the change before it happens.
6. **Verify.** A fresh crawl succeeds on every hub, no peer shows `key_mismatch`, and a fresh
   response verifies under the new key with the strict rule (§6).

## 4. Suspected compromise

1. **Stop signing now**: take the oracle offline or rotate immediately (§3, steps 2–4) — speed
   over ceremony.
2. **Fix the window.** Everything signed by the old key since the earliest possible exposure is
   forgeable: receipts, attestations, manifests. Tell every hub operator the window, so receipts
   from it are not accepted as evidence.
3. **VRF.** Whoever holds the VRF secret can compute any draw in advance, and therefore choose
   inputs that favour them. Treat draws whose input was chosen after the exposure as suspect.
4. **Publish** a short incident note: key fingerprints (old and new), the window, what callers
   should do. If the ecosystem's transparency log records the rotation, link the entry.

## 5. What exists and what does not

- **HSM / KMS:** not supported. `oracle_core` signs in-process with a key from a file or the
  environment. The closest available pattern is the escrow signer (HORKOS): the key in a separate
  process under a separate user, reached over loopback with a token. Oracles do not use it yet.
- **Threshold or multi-party signing** (e.g. FROST for Ed25519): not implemented. Per-response
  signatures are produced by one key.
- **Multisig** applies to contract ownership (a Safe owning the contracts), not to oracle
  responses.

## 6. The verifying side

A signature is only as binding as its verifier. Every verifier in this ecosystem now applies the
strict Ed25519 rule — no small-order public key or `R`, canonical `S` — because OpenSSL,
tweetnacl and WebCrypto accept, under the identity key, a signature valid for every message
(aimarket-protocol §7.3.7). Hybrid signatures follow §7.3.8: Ed25519 first, a present ML-DSA half
must verify, and the PQ key is pinned. Implementers outside this repository should do the same.

What stays open (KI-6): no external review of these procedures or of the keys' handling in
production has been published.
