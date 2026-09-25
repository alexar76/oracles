"""Wesolowski Verifiable Delay Function (RSA group of unknown order).

y = g^(2^T) mod N requires T *sequential* squarings (cannot be parallelized while
the order of the group is unknown). The Wesolowski proof π lets anyone verify
y = g^(2^T) with a single cheap check — without redoing the T squarings — so the
result is **publicly verifiable, no trust in the prover required.**

Setup is trustless: N is the public RSA-2048 challenge modulus, whose factorization
is unknown to everyone (so nobody knows the group order → nobody can shortcut the
squaring). This makes Chronos a proof-of-elapsed-sequential-work oracle: fair
ordering, timeouts, and an unbiasable randomness beacon (VDF over Platon's output).
"""

from __future__ import annotations

import hashlib
from typing import Any

# RSA-2048 challenge modulus (RSA Factoring Challenge) — factorization publicly unknown:
# RSA Labs discarded the primes, so NO ONE (including this operator) knows the group order.
# That is what makes the VDF trustless — no setup ceremony, no trapdoor. Canonical value is
# 617 decimal digits, EXACTLY 2048 bits. Independently verifiable:
#   python -c "import hashlib,chronos.vdf as v; print(hashlib.sha256(str(v.RSA_2048).encode()).hexdigest())"
#   → b3c2468add10e2a0c4a251d9d2bac4ba04d4b3527156ceead43a1305e03f1fc0
RSA_2048 = int(
    "25195908475657893494027183240048398571429282126204032027777137836043662020"
    "70759555626401852588078440691829064124951508218929855914917618450280848912"
    "00728449926873928072877767359714183472702618963750149718246911650776133798"
    "59095700097330459748808428401797429100642458691817195118746121515172654632"
    "28221686998754918242243363725908514186546204357679842338718477444792073993"
    "42365848238242811981638150106748104516603773060562016196762561338441436038"
    "33904414952634432190114657544454178424020924616515723350778707749817125772"
    "46796292638635637328991215483143816789988504044536402352738195137863656439"
    "1212010397122822120720357"
)
# Fail-fast guard: a corrupted modulus would silently void the unknown-factorization
# security assumption (a non-canonical N may have known/small factors).
assert RSA_2048.bit_length() == 2048, "RSA-2048 modulus corrupted — must be exactly 2048 bits"

MAX_DIFFICULTY = 1_000_000  # cap on sequential squarings (T)


def _is_probable_prime(n: int, rounds: int = 20) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    # The fixed first-12-primes base set is deterministic only below ~3.3e24 (~2^81), NOT
    # for the 128-bit candidates used here — the old comment claiming otherwise was wrong.
    # With publicly known bases an adversary can grind seeds looking for a composite l that
    # passes them all, and a composite challenge breaks Wesolowski soundness. So half the
    # bases are derived from the candidate itself: still fully deterministic (Fiat-Shamir
    # needs verify to recompute the same l), but unknowable before n is fixed, so they
    # cannot be targeted in advance.
    derived = []
    for i in range(rounds // 2 or 1):
        h = hashlib.sha256(b"chronos-mr|" + i.to_bytes(4, "big") + b"|" + str(n).encode()).digest()
        derived.append(2 + int.from_bytes(h[:8], "big") % (n - 4))
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, *derived):
        if a >= n:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def hash_to_group(seed: str, N: int = RSA_2048) -> int:
    """Deterministically map a seed to a group element g in [2, N-2].

    Hashes 128 bits MORE than the modulus before reducing. Reducing exactly 2048 bits mod a
    2048-bit N is not a negligible bias: 2^2048/N ≈ 1.28, so ~28% of residues get two
    preimages and are twice as likely as the rest. With 2176 bits the ratio is within
    2^-128 of uniform, which is the standard hash-to-range construction and avoids the
    variable-time loop that rejection sampling introduces.

    The range excludes 0, 1 and N-1: those are degenerate elements for which g^(2^T) is
    independent of T, so a VDF over them proves nothing (see the guard in `verify`).
    """
    need = (N.bit_length() + 128 + 7) // 8
    acc = b""
    while len(acc) < need:
        acc += hashlib.sha256(b"chronos-g|" + str(len(acc)).encode() + b"|" + seed.encode()).digest()
    return 2 + int.from_bytes(acc[:need], "big") % (N - 3)


def hash_to_prime(g: int, y: int, T: int) -> int:
    """Derive a deterministic ~128-bit prime l from the transcript (Fiat-Shamir)."""
    transcript = f"{g}|{y}|{T}".encode()
    counter = 0
    while True:
        h = hashlib.sha256(b"chronos-l|" + counter.to_bytes(8, "big") + b"|" + transcript).digest()
        cand = int.from_bytes(h[:16], "big") | 1  # 128-bit, odd
        if _is_probable_prime(cand):
            return cand
        counter += 1


def evaluate(g: int, T: int, N: int = RSA_2048) -> int:
    """y = g^(2^T) mod N via T sequential squarings (the delay)."""
    y = g % N
    for _ in range(T):
        y = (y * y) % N
    return y


def prove(g: int, y: int, T: int, N: int = RSA_2048) -> dict[str, Any]:
    """Wesolowski proof: l = H2P(g,y,T); π = g^(⌊2^T/l⌋) mod N."""
    l = hash_to_prime(g, y, T)
    q = (1 << T) // l
    pi = pow(g, q, N)
    return {"pi": pi, "l": l}


def verify(g: int, y: int, T: int, pi: int, l: int, N: int = RSA_2048) -> bool:
    """Check π^l · g^r ≡ y (mod N) with r = 2^T mod l, and that l = H2P(g,y,T).

    Input is validated before the crypto (defense-in-depth against malformed-proof false
    positives and resource abuse): T in range, group elements in [0, N), l a plausible
    128-bit prime bound to the exact transcript via Fiat-Shamir.
    """
    try:
        g, y, T, pi, l = int(g), int(y), int(T), int(pi), int(l)
    except (TypeError, ValueError):
        return False
    if not (1 <= T <= MAX_DIFFICULTY):
        return False
    if not (0 <= g < N and 0 <= y < N and 0 <= pi < N):
        return False
    # Degenerate group elements make the verification equation an identity, so a proof
    # claiming ANY T verifies with no work at all:
    #   g=0 → y=0, and π^l·0^r ≡ 0 holds for every π
    #   g=1 → y=1, and 1·1 ≡ 1
    #   g=N-1 has order 2, so y is 1 or N-1 regardless of T
    # `0 <= g < N` admitted all three. The honest path never produces them —
    # hash_to_group returns ≥ 2 — but verify is a public capability that accepts g from
    # the caller, so it must reject them itself. Confirmed against production before the
    # fix: verify(g=0, y=0, T=1_000_000, π=0) answered valid.
    if not (2 <= g <= N - 2):
        return False
    if l < 3 or l.bit_length() > 200:          # a 128-bit challenge prime is expected
        return False
    if l != hash_to_prime(g, y, T):            # binds the proof to the exact (g,y,T) transcript
        return False
    r = pow(2, T, l)
    return (pow(pi, l, N) * pow(g, r, N)) % N == y % N


def run(seed: str, difficulty: int, N: int = RSA_2048) -> dict[str, Any]:
    """Full eval+prove for the capability handler."""
    T = max(1, min(int(difficulty), MAX_DIFFICULTY))
    g = hash_to_group(seed, N)
    y = evaluate(g, T, N)
    proof = prove(g, y, T, N)
    return {
        "scheme": "wesolowski-vdf/rsa-2048",
        "seed": seed,
        "difficulty": T,
        "g": str(g),
        "y": str(y),
        "proof": {"pi": str(proof["pi"]), "l": str(proof["l"])},
        "modulus": "RSA-2048",
    }
