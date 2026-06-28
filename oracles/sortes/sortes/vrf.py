"""ECVRF-EDWARDS25519-SHA512-TAI — a true verifiable random function (RFC 9381).

Sortes draws lots: the output beta is a uniform pseudorandom string bound to a
public key Y and an input alpha. It is **verifiable offline** by anyone holding Y
and the 80-byte proof pi — and, crucially, the prover **cannot grind it**. For a
fixed (Y, alpha) there is exactly ONE valid (pi, beta); the secret key x selects
it deterministically, so the oracle has no freedom to bias the draw. That is the
property a trusted randomness beacon cannot offer: a beacon can re-roll until it
likes the result, a VRF cannot.

This file is pure Python (hashlib, int math) — no numpy, no external crypto. The
edwards25519 group arithmetic (RFC 8032 §5.1) is implemented from scratch, and the
ECVRF construction (RFC 9381 §5, suite ECVRF-EDWARDS25519-SHA512-TAI, suite octet
0x03) is implemented exactly so the published Appendix test vectors reproduce
bit-for-bit (see tests/test_sortes.py).
"""

from __future__ import annotations

import hashlib
from typing import Tuple

# --- field & curve constants (edwards25519, RFC 8032 §5.1) -----------------
P = 2**255 - 19  # field prime
# group order of the base point B
L = 2**252 + 27742317777372353535851937790883648493
COFACTOR = 8
# twist constant d = -121665/121666 mod p
D = (-121665 * pow(121666, P - 2, P)) % P
# sqrt(-1) mod p, used in point decompression
SQRT_M1 = pow(2, (P - 1) // 4, P)

SUITE = b"\x03"  # ECVRF-EDWARDS25519-SHA512-TAI suite_string
PT_LEN = 32  # encoded point length (bytes)
C_LEN = 16  # challenge length (bytes)
Q_LEN = 32  # scalar length (bytes)


# --- low-level field helpers ----------------------------------------------
def _inv(z: int) -> int:
    """Field inverse via Fermat's little theorem (p is prime)."""
    return pow(z, P - 2, P)


def _sha512(*chunks: bytes) -> bytes:
    h = hashlib.sha512()
    for c in chunks:
        h.update(c)
    return h.digest()


# --- extended twisted-Edwards point arithmetic ------------------------------
# Points are kept in extended homogeneous coordinates (X, Y, Z, T) with
# x = X/Z, y = Y/Z and T = XY/Z. Addition formulas are the unified ones from
# RFC 8032 §5.1.4 (Hisil-Wong-Carter-Dawson), valid for all input pairs.
Point = Tuple[int, int, int, int]


def _base_point() -> Point:
    # B = (x, 4/5) with the standard recovered x (RFC 8032 §5.1).
    by = (4 * _inv(5)) % P
    bx = _recover_x(by, 0)
    return (bx, by, 1, (bx * by) % P)


def _recover_x(y: int, sign: int) -> int:
    """Recover the x-coordinate from y and its sign bit (RFC 8032 §5.1.3)."""
    if y >= P:
        return -1  # malformed
    x2 = ((y * y - 1) * _inv(D * y * y + 1)) % P
    if x2 == 0:
        if sign:
            return -1  # x = 0 cannot have a set sign bit
        return 0
    # candidate sqrt
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = (x * SQRT_M1) % P
    if (x * x - x2) % P != 0:
        return -1  # not a square -> not on curve
    if (x & 1) != sign:
        x = (P - x) % P
    return x


def point_add(a: Point, b: Point) -> Point:
    """Unified extended-coordinate addition (RFC 8032 §5.1.4)."""
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    aa = ((y1 - x1) * (y2 - x2)) % P
    bb = ((y1 + x1) * (y2 + x2)) % P
    cc = (t1 * 2 * D * t2) % P
    dd = (z1 * 2 * z2) % P
    e = (bb - aa) % P
    f = (dd - cc) % P
    g = (dd + cc) % P
    h = (bb + aa) % P
    x3 = (e * f) % P
    y3 = (g * h) % P
    t3 = (e * h) % P
    z3 = (f * g) % P
    return (x3, y3, z3, t3)


def scalar_mul(s: int, pt: Point) -> Point:
    """Constant-shape double-and-add scalar multiplication."""
    # neutral element (0, 1, 1, 0)
    result: Point = (0, 1, 1, 0)
    addend = pt
    s = s % (L * COFACTOR) if s >= L * COFACTOR else s
    while s > 0:
        if s & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        s >>= 1
    return result


def point_equal(a: Point, b: Point) -> bool:
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    if (x1 * z2 - x2 * z1) % P != 0:
        return False
    if (y1 * z2 - y2 * z1) % P != 0:
        return False
    return True


def point_encode(pt: Point) -> bytes:
    """Compress to 32 bytes (RFC 8032 §5.1.2): y with x's sign in the top bit."""
    x, y, z, _ = pt
    zi = _inv(z)
    x = (x * zi) % P
    y = (y * zi) % P
    out = bytearray(y.to_bytes(32, "little"))
    out[31] |= (x & 1) << 7
    return bytes(out)


def point_decode(data: bytes) -> Point | None:
    """Decompress a 32-byte point; return None if it is not a valid curve point."""
    if len(data) != 32:
        return None
    b = bytearray(data)
    sign = (b[31] >> 7) & 1
    b[31] &= 0x7F
    y = int.from_bytes(b, "little")
    if y >= P:
        return None
    x = _recover_x(y, sign)
    if x < 0:
        return None
    return (x, y, 1, (x * y) % P)


def is_on_curve(pt: Point) -> bool:
    """-x^2 + y^2 = 1 + d x^2 y^2 (curve equation, affine, via Z)."""
    x, y, z, t = pt
    zi = _inv(z)
    xa = (x * zi) % P
    ya = (y * zi) % P
    lhs = (-xa * xa + ya * ya) % P
    rhs = (1 + D * xa * xa * ya * ya) % P
    return lhs == rhs


# --- scalar / integer string helpers (RFC 9381 §2.x) -----------------------
def int_to_string(x: int, length: int) -> bytes:
    """I2OSP — big-endian fixed-length octet string."""
    return x.to_bytes(length, "big")


def string_to_int(b: bytes) -> int:
    """OS2IP — big-endian octet string to nonnegative integer."""
    return int.from_bytes(b, "big")


def _clamp_scalar(h32: bytes) -> int:
    """RFC 8032 Ed25519 scalar clamping of the first 32 bytes of SHA512(SK)."""
    a = bytearray(h32)
    a[0] &= 0xF8
    a[31] &= 0x7F
    a[31] |= 0x40
    return int.from_bytes(a, "little")


# --- key expansion (RFC 8032 §5.1.5) ---------------------------------------
def expand_sk(sk: bytes) -> Tuple[int, bytes, bytes]:
    """SK (32 bytes) -> (x scalar, truncated_hashed_sk, PK bytes)."""
    if len(sk) != 32:
        raise ValueError("secret key must be 32 bytes")
    h = _sha512(sk)
    x = _clamp_scalar(h[0:32])
    truncated = h[32:64]
    pk = point_encode(scalar_mul(x, _base_point()))
    return x, truncated, pk


def sk_to_pk(sk: bytes) -> bytes:
    """Derive the 32-byte Ed25519/VRF public key from a 32-byte secret key."""
    return expand_sk(sk)[2]


# --- ECVRF core (RFC 9381 §5.4 / §5.1) -------------------------------------
def hash_to_curve_tai(pk: bytes, alpha: bytes) -> Point:
    """ECVRF_hash_to_curve_try_and_increment (§5.4.1.1).

    H = cofactor * (first decodable point of SHA512(suite||0x01||PK||alpha||ctr||0x00)).
    """
    for ctr in range(256):
        h = _sha512(SUITE, b"\x01", pk, alpha, int_to_string(ctr, 1), b"\x00")
        pt = point_decode(h[0:PT_LEN])
        if pt is not None:
            # cofactor clearing: H <- 8 * H
            return scalar_mul(COFACTOR, pt)
    raise ValueError("hash_to_curve failed (no point found in 256 tries)")


def _challenge_generation(points: list[Point]) -> int:
    """ECVRF_challenge_generation (§5.4.3): c = int(SHA512(suite||0x02||P1..Pn||0x00)[0:16])."""
    parts = [SUITE, b"\x02"]
    for p in points:
        parts.append(point_encode(p))
    parts.append(b"\x00")
    c_string = _sha512(*parts)
    return string_to_int(c_string[0:C_LEN])


def _nonce_generation(truncated_hashed_sk: bytes, h_point: Point) -> int:
    """ECVRF_nonce_generation_RFC8032 (§5.4.2.2)."""
    k_string = _sha512(truncated_hashed_sk, point_encode(h_point))
    return string_to_int(k_string) % L


def _gamma_to_hash(gamma: Point) -> bytes:
    """ECVRF_proof_to_hash beta = SHA512(suite||0x03||encode(cofactor*Gamma)||0x00)."""
    cofactor_gamma = scalar_mul(COFACTOR, gamma)
    return _sha512(SUITE, b"\x03", point_encode(cofactor_gamma), b"\x00")


def prove(sk: bytes, alpha: bytes) -> bytes:
    """ECVRF_prove (§5.1): return the 80-byte proof pi for (SK, alpha)."""
    x, truncated_hashed_sk, pk = expand_sk(sk)
    base = _base_point()
    h = hash_to_curve_tai(pk, alpha)
    gamma = scalar_mul(x, h)
    k = _nonce_generation(truncated_hashed_sk, h)
    u = scalar_mul(k, base)  # k*B
    v = scalar_mul(k, h)  # k*H
    y = scalar_mul(x, base)  # public-key point Y = x*B
    # RFC 9381 §5.1 step 6: c = challenge_generation(Y, H, Gamma, k*B, k*H).
    # The public key Y MUST be the first transcript point — omitting it yields
    # proofs a conformant RFC-9381 verifier would reject (output beta is the same,
    # but interop breaks), which would defeat the whole point of a standard VRF.
    c = _challenge_generation([y, h, gamma, u, v])
    s = (k + c * x) % L
    return point_encode(gamma) + int_to_string(c, C_LEN) + int_to_string(s, Q_LEN)


def proof_to_hash(pi: bytes) -> bytes | None:
    """ECVRF_proof_to_hash (§5.2): decode pi and return the 64-byte beta (or None)."""
    decoded = decode_proof(pi)
    if decoded is None:
        return None
    gamma, _c, _s = decoded
    return _gamma_to_hash(gamma)


def decode_proof(pi: bytes) -> Tuple[Point, int, int] | None:
    """ECVRF_decode_proof (§5.4.4): pi (80 bytes) -> (Gamma, c, s) or None if malformed."""
    if len(pi) != PT_LEN + C_LEN + Q_LEN:
        return None
    gamma = point_decode(pi[0:PT_LEN])
    if gamma is None:
        return None
    c = string_to_int(pi[PT_LEN:PT_LEN + C_LEN])
    s = string_to_int(pi[PT_LEN + C_LEN:PT_LEN + C_LEN + Q_LEN])
    if s >= L:  # scalar must be reduced (non-malleable)
        return None
    return gamma, c, s


def verify(pk: bytes, alpha: bytes, pi: bytes) -> bytes | None:
    """ECVRF_verify (§5.3): return beta (64 bytes) iff pi is valid for (PK, alpha), else None."""
    y = point_decode(pk)
    if y is None:
        return None
    decoded = decode_proof(pi)
    if decoded is None:
        return None
    gamma, c, s = decoded
    base = _base_point()
    h = hash_to_curve_tai(pk, alpha)
    # U = s*B - c*Y ; V = s*H - c*Gamma
    u = point_add(scalar_mul(s, base), _negate(scalar_mul(c, y)))
    v = point_add(scalar_mul(s, h), _negate(scalar_mul(c, gamma)))
    # RFC 9381 §5.3 step 10: c' = challenge_generation(Y, H, Gamma, U, V).
    c_prime = _challenge_generation([y, h, gamma, u, v])
    if c_prime != c:
        return None
    return _gamma_to_hash(gamma)


def _negate(pt: Point) -> Point:
    x, y, z, t = pt
    return ((-x) % P, y, z, (-t) % P)


# --- output stretching ------------------------------------------------------
def expand_output(beta: bytes, num_bytes: int) -> bytes:
    """Derive `num_bytes` of uniform output from the 64-byte beta.

    For num_bytes <= 64 this is a prefix of beta; for larger requests beta is
    used as a key in a SHA512 counter-mode stream so the result stays uniform
    and fully determined by beta (hence still verifiable & ungrindable).
    """
    if num_bytes <= len(beta):
        return beta[:num_bytes]
    out = bytearray()
    ctr = 0
    while len(out) < num_bytes:
        out += _sha512(beta, int_to_string(ctr, 4))
        ctr += 1
    return bytes(out[:num_bytes])
