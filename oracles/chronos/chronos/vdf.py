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

# RSA-2048 challenge modulus — factorization publicly unknown (trustless setup).
RSA_2048 = int(
    "251959084756578934940271832400483985714292821262040320277771378360436620207075"
    "95556264018525880784406918290641249515082189298559149176184502808489120072844"
    "99268739280728777673597141834727026189637501497182469116507761337985909570009"
    "73304597488084284017974291006424586918171951187461215151726546326822821686998"
    "75491824224336372590851418654620435767984233871847744479207399342365848238242"
    "81198163815010674810451660377306056201619676256133844143603833904414952634432"
    "190114657544454178424020924616515723350778707749817125772467962926386356373289"
    "912154831438167899885040445364023527381951378636564391212010397122822120720357"
)

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
    # deterministic small-base witnesses are enough for 128-bit candidates
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
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
    """Deterministically map a seed to a group element g in [2, N-1]."""
    acc = b""
    while len(acc) < 256:
        acc += hashlib.sha256(b"chronos-g|" + str(len(acc)).encode() + b"|" + seed.encode()).digest()
    g = int.from_bytes(acc, "big") % N
    return g if g >= 2 else 2


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
    """Check π^l · g^r ≡ y (mod N) with r = 2^T mod l, and that l = H2P(g,y,T)."""
    if l != hash_to_prime(g, y, T):
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
