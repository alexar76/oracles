"""Rivest-Shamir-Wagner (RSW) time-lock puzzles — seal the FUTURE.

Chronos *proves the past elapsed* (a VDF over the public, unfactored RSA-2048
modulus). Aestus does the opposite: it **time-LOCKS** data so that NOBODY can
open it before ~T sequential squarings of wall-clock have elapsed, after which
ANYONE can open it — no trapdoor holder, no key escrow, no trusted third party.

The construction (Rivest, Shamir, Wagner 1996):

    b = a^(2^T) mod N       (T *sequential* squarings — the delay)
    key = SHA256(b)
    ciphertext = plaintext XOR keystream(key)          (SHA256-CTR keystream)

Opening recomputes b by redoing the T squarings, derives the same key, and
decrypts. Because the squaring chain b_i = b_{i-1}^2 mod N is inherently
sequential while the order of Z_N* is unknown, no amount of parallelism opens
the puzzle faster than ~T squarings of one core: the delay is enforced by math.

CRYPTO HONESTY — why this oracle CANNOT cheat
---------------------------------------------
The trustless property ("nobody can open early, not even us") holds ONLY if the
factorization of N — and hence φ(N) — is unknown to everyone, INCLUDING the
oracle that sealed it. A trapdoor holder who knows φ(N) can compute the shortcut

    e = 2^T mod φ(N)          (needs φ(N) = (p-1)(q-1))
    b = a^e mod N             (one fast exponentiation, NO T squarings)

and so could open any puzzle instantly. To stay honest Aestus therefore:

  1. generates a FRESH RSA modulus N = p·q on EVERY seal (never a shared/fixed N
     whose factors it might retain),
  2. derives b by T *sequential squarings* on the SLOW path — it deliberately
     does NOT use the φ(N) shortcut even though it momentarily holds p, q,
  3. BURNS p, q, φ(N) (deletes the local variables) before returning, and never
     puts them in the puzzle.

Tradeoff (stated honestly): because we burn φ(N), sealing costs the SAME T
sequential squarings as opening — seal-work == open-work. The φ shortcut would
make sealing O(1), but keeping φ around would let the oracle open early, which
breaks the whole trust model. We take the slow, honest path on purpose.

Pure Python only (hashlib, secrets, int math): a self-contained Miller-Rabin
primality test and random-prime generator, no numpy / sympy / scipy.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

# Cap on sequential squarings (T) — the protocol layer does NOT validate input
# against input_schema, so the handler must clamp this. Without a ceiling a
# caller could request an unbounded T and pin a CPU for an arbitrarily long
# time (a trivial DoS), exactly the concern Chronos guards with MAX_DIFFICULTY.
MAX_T = 5_000_000

# Modulus size bounds. ~1024-bit N (two ~512-bit primes) is a sane PoC default;
# capped so a caller cannot ask us to grind 8192-bit prime generation forever.
DEFAULT_MODULUS_BITS = 1024
MIN_MODULUS_BITS = 256
MAX_MODULUS_BITS = 3072

SCHEME = "rsw-timelock/sha256-ctr"

# Miller-Rabin small-prime trial-division wheel + bases.
_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)
_MR_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def _is_probable_prime(n: int, rounds: int = 24) -> bool:
    """Miller-Rabin primality test (fixed small bases + random bases)."""
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1

    def _witness(a: int) -> bool:
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            return False  # not a witness
        for _ in range(r - 1):
            x = (x * x) % n
            if x == n - 1:
                return False
        return True  # composite witness

    for a in _MR_BASES:
        if a >= n:
            continue
        if _witness(a):
            return False
    # extra random-base rounds for the larger (cryptographic-size) candidates
    for _ in range(rounds):
        a = 2 + secrets.randbelow(n - 3)
        if _witness(a):
            return False
    return True


def _gen_prime(bits: int) -> int:
    """A fresh random probable prime of exactly ``bits`` bits."""
    if bits < 8:
        raise ValueError("prime bits too small")
    while True:
        # force top bit (full width) and bottom bit (odd)
        cand = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(cand):
            return cand


def gen_modulus(modulus_bits: int) -> tuple[int, int, int]:
    """Generate a FRESH RSA modulus N = p·q with two distinct primes.

    Returns (N, p, q). The caller MUST burn p, q immediately after deriving the
    puzzle — they are the trapdoor and are never to be persisted or returned.
    """
    bits = max(MIN_MODULUS_BITS, min(int(modulus_bits), MAX_MODULUS_BITS))
    half = bits // 2
    p = _gen_prime(half)
    q = _gen_prime(bits - half)
    while q == p:
        q = _gen_prime(bits - half)
    return p * q, p, q


def _pick_base(N: int) -> int:
    """Pick a base a in [2, N-1]. (a=2 would do; a random unit is a touch nicer
    and avoids any pathological small-order corner.)"""
    a = 2 + secrets.randbelow(N - 3)
    return a if a >= 2 else 2


def squarings(a: int, T: int, N: int) -> int:
    """b = a^(2^T) mod N via T *sequential* squarings (the honest slow path).

    This is the delay. We never use e = 2^T mod φ(N): φ is unknown by the time
    open/verify run, and is deliberately burned at seal time so this is the only
    path anyone — including the oracle — can take.
    """
    b = a % N
    for _ in range(T):
        b = (b * b) % N
    return b


def _int_to_bytes(x: int) -> bytes:
    """Minimal big-endian byte encoding of a non-negative int (>=1 byte)."""
    if x == 0:
        return b"\x00"
    return x.to_bytes((x.bit_length() + 7) // 8, "big")


def _keystream(key: bytes, n: int) -> bytes:
    """SHA256-CTR keystream of ``n`` bytes (no external AES dependency)."""
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(key + b"|ctr|" + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:n])


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(d ^ s for d, s in zip(data, stream))


def _decode_data(data: str, encoding: str) -> bytes:
    if encoding == "hex":
        try:
            return bytes.fromhex(data)
        except ValueError as exc:
            raise ValueError(f"data is not valid hex: {exc}") from exc
    if encoding == "utf8":
        return data.encode("utf-8")
    raise ValueError(f"unknown encoding: {encoding!r} (use 'utf8' or 'hex')")


def _derive(b: int) -> tuple[bytes, str]:
    """key = SHA256(int_to_bytes(b)); key_commitment = SHA256(int_to_bytes(b))?
    No — the commitment is SHA256(b)'s *own* digest of the encryption key so a
    verifier can check b WITHOUT being given the plaintext. We bind:

        key            = SHA256( int_to_bytes(b) )
        key_commitment = SHA256( b"aestus-commit|" + int_to_bytes(b) )

    Using a domain-separated commitment means the commitment never equals the
    key itself (so publishing key_commitment leaks nothing about the keystream).
    """
    bb = _int_to_bytes(b)
    key = hashlib.sha256(b"aestus-key|" + bb).digest()
    commitment = hashlib.sha256(b"aestus-commit|" + bb).hexdigest()
    return key, commitment


def commitment_of_b(b: int) -> str:
    """The key_commitment a verifier checks: SHA256('aestus-commit|' + bytes(b))."""
    return hashlib.sha256(b"aestus-commit|" + _int_to_bytes(b)).hexdigest()


def seal(data: str, T: int, encoding: str = "utf8", modulus_bits: int = DEFAULT_MODULUS_BITS) -> dict[str, Any]:
    """Time-lock ``data`` for ~T sequential squarings.

    Generates a fresh N = p·q, derives b = a^(2^T) mod N by T honest squarings,
    encrypts the plaintext under SHA256(b) with a SHA256-CTR keystream, and
    BURNS p, q, φ. The returned puzzle contains NO trapdoor — only what an
    opener needs to redo the work.
    """
    T = max(1, min(int(T), MAX_T))
    plaintext = _decode_data(data, encoding)

    # 1. fresh modulus (we briefly hold the factors)
    N, p, q = gen_modulus(modulus_bits)
    actual_bits = N.bit_length()
    a = _pick_base(N)

    # 2. honest slow path — T sequential squarings (NOT the φ shortcut).
    #    We could compute e = pow(2, T, (p-1)*(q-1)); b = pow(a, e, N) here in
    #    O(1), but that would mean we *could* open early. We refuse to.
    b = squarings(a, T, N)

    # 3. derive key + commitment, encrypt
    key, commitment = _derive(b)
    ciphertext = _xor(plaintext, _keystream(key, len(plaintext)))

    # 4. BURN the trapdoor — delete p, q, φ so neither we nor anyone can shortcut.
    del p, q  # φ(N) = (p-1)(q-1) is now uncomputable without re-factoring N
    del b, key  # also drop the answer itself; opening must redo the work

    return {
        "scheme": SCHEME,
        "N": str(N),
        "a": str(a),
        "T": T,
        "ciphertext": ciphertext.hex(),
        "key_commitment": commitment,
        "modulus_bits": actual_bits,
        "encoding": encoding,
    }


def _parse_puzzle(puzzle: dict[str, Any]) -> tuple[int, int, int, bytes, str, str]:
    if not isinstance(puzzle, dict):
        raise ValueError("puzzle must be an object")
    try:
        N = int(puzzle["N"])
        a = int(puzzle["a"])
        T = int(puzzle["T"])
        ciphertext = bytes.fromhex(puzzle["ciphertext"])
        commitment = str(puzzle["key_commitment"])
    except KeyError as exc:
        raise ValueError(f"puzzle missing field: {exc}") from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(f"malformed puzzle: {exc}") from exc
    if N < 3 or a < 1 or T < 1:
        raise ValueError("puzzle has out-of-range N/a/T")
    if T > MAX_T:
        raise ValueError(f"puzzle T exceeds MAX_T={MAX_T}")
    encoding = str(puzzle.get("encoding", "utf8"))
    return N, a, T, ciphertext, commitment, encoding


def _encode_data(plaintext: bytes, encoding: str) -> str:
    if encoding == "hex":
        return plaintext.hex()
    # utf8 (default): decode loosely so a tampered/garbled puzzle still returns
    # *something*, while ``valid`` carries the real success signal.
    return plaintext.decode("utf-8", errors="replace")


def open_puzzle(puzzle: dict[str, Any]) -> dict[str, Any]:
    """Recompute b by T sequential squarings, decrypt, and verify the commitment.

    ``valid`` is True iff the recomputed b matches the puzzle's key_commitment —
    i.e. the puzzle is internally consistent (N, a, T unmodified). A tampered
    ciphertext still decrypts (XOR always produces bytes) but the plaintext is
    garbage; the commitment is over b (not the ciphertext), so a ciphertext-only
    tamper leaves ``valid`` True while the recovered ``data`` is corrupted. A
    tamper to N/a/T flips ``valid`` to False.
    """
    N, a, T, ciphertext, commitment, encoding = _parse_puzzle(puzzle)

    b = squarings(a, T, N)  # the delay — redone honestly
    key, recomputed = _derive(b)
    valid = (recomputed == commitment)

    plaintext = _xor(ciphertext, _keystream(key, len(ciphertext)))
    return {
        "data": _encode_data(plaintext, encoding),
        "b": str(b),
        "valid": valid,
    }


def verify(puzzle: dict[str, Any], b: str) -> dict[str, Any]:
    """Cheap one-hash check that a *claimed* result ``b`` of the squarings matches
    the puzzle's key_commitment — no T squarings required.

    This lets a worker who already did the (slow) open publish b so that anyone
    else can confirm the unlock value in ~one SHA256, without redoing the delay.
    """
    N, a, T, ciphertext, commitment, encoding = _parse_puzzle(puzzle)
    try:
        b_int = int(b)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"claimed b is not an integer: {exc}") from exc
    if b_int < 0 or b_int >= N:
        return {"valid": False}
    return {"valid": commitment_of_b(b_int) == commitment}
