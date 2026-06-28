# Sortes — true ECVRF verifiable-randomness oracle

Sortes draws lots you can verify. It is a **true Verifiable Random Function**
implementing **ECVRF-EDWARDS25519-SHA512-TAI** exactly per
[RFC 9381](https://www.rfc-editor.org/rfc/rfc9381) (suite octet `0x03`, over the
`edwards25519` curve).

For a fixed `(public_key, alpha)` there is **exactly one** valid output `beta`.
The oracle's secret key selects it deterministically, so — unlike a trusted
randomness beacon — the oracle **cannot grind or bias the result**, and anyone
holding the VRF public key can **verify the draw offline** from the 80-byte proof.

## Capabilities

| capability | price | what it does |
|---|---|---|
| `sortes.draw@v1` | $0.006 | Draw verifiable randomness for `alpha`. Returns `public_key`, proof (`gamma`, `c`, `s`, `pi`), `beta`, and `output` (uniform `num_bytes`). The secret key is never returned. |
| `sortes.verify@v1` | $0.001 | Verify `(public_key, alpha, pi)` offline and trustlessly → `{valid, beta}`. |

`alpha` is UTF-8 by default; prefix with `hex:` to pass raw bytes.

## Why it is correct

The implementation is pure Python (`hashlib` + integer math) — the `edwards25519`
group arithmetic (RFC 8032 §5.1) and the ECVRF construction (RFC 9381 §5) are
written from scratch, no external crypto libraries. Correctness is proven by the
**RFC 9381 Appendix A.4 test vectors**: the tests assert that our implementation
reproduces the published `SK→PK`, the hash-to-curve point `H`, the proof
commitment `Gamma`, and the VRF output `beta` bit-for-bit for all three vectors,
and that every proof we emit verifies. See `tests/test_sortes.py`.

## VRF keypair

The oracle holds one VRF keypair. The 32-byte secret key is resolved from
`SORTES_VRF_SK` (64 hex chars), else a persisted key at `SORTES_VRF_SK_PATH`
(default `data/sortes_vrf_sk`), else generated once and persisted so the public
key stays stable across restarts. The secret key never leaves the process; the
public key is published in every draw and in the manifest description.

## Run

```bash
# tests (from the monorepo root)
PYTHONPATH="oracles/core:oracles/oracles/sortes" \
  platon/backend/.venv/bin/python -m pytest oracles/oracles/sortes/tests/ -q

# serve (port 9310 by default)
PYTHONPATH="oracles/core:oracles/oracles/sortes" python -m sortes.main
```

### Environment

| var | default | meaning |
|---|---|---|
| `SORTES_PORT` | `9310` | listen port |
| `SORTES_PUBLIC_URL` | `http://localhost:9310` | advertised base URL |
| `SORTES_SIGNING_KEY` | `data/sortes_signing_key` | manifest/receipt signing key path |
| `SORTES_VRF_SK` | _(unset)_ | explicit 32-byte VRF secret key (hex) |
| `SORTES_VRF_SK_PATH` | `data/sortes_vrf_sk` | persisted VRF secret key path |
| `SORTES_CORS_ORIGINS` | `*` | allowed CORS origins |
