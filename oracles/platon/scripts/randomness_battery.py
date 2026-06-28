#!/usr/bin/env python3
"""Formal randomness battery (NIST SP 800-22 core) for Platon output.

Computes real p-values (PASS if p >= 0.01, the NIST threshold) for:
Monobit, Block-Frequency, Runs, Cumulative-Sums, Approximate-Entropy, Serial,
Spectral-DFT — plus byte chi-square, Shannon entropy and a zlib compression
ratio. Run on a sample file, or with --compare to also run the SAME battery on an
equal-size os.urandom control.

Usage:
    python scripts/randomness_battery.py <sample.bin> [--compare]
"""

from __future__ import annotations

import math
import sys
import zlib

import numpy as np

ALPHA = 0.01  # NIST significance threshold


# --- special functions (regularized upper incomplete gamma Q(a,x)) ----------
def _gser(a: float, x: float) -> float:
    if x <= 0:
        return 0.0
    ap, s, dele = a, 1.0 / a, 1.0 / a
    for _ in range(500):
        ap += 1
        dele *= x / ap
        s += dele
        if abs(dele) < abs(s) * 1e-14:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    FPMIN = 1e-300
    b, c, d = x + 1 - a, 1 / FPMIN, 1 / (x + 1 - a)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1 / d
        dele = d * c
        h *= dele
        if abs(dele - 1) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def igamc(a: float, x: float) -> float:
    if x < 0 or a <= 0:
        return 1.0
    return 1.0 - _gser(a, x) if x < a + 1 else _gcf(a, x)


def _normcdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


# --- tests -------------------------------------------------------------------
def monobit(bits: np.ndarray) -> float:
    s = abs(int(bits.sum()) * 2 - len(bits)) / math.sqrt(len(bits))
    return math.erfc(s / math.sqrt(2))


def block_frequency(bits: np.ndarray, M: int = 128) -> float:
    n = len(bits) // M
    blocks = bits[: n * M].reshape(n, M).mean(axis=1)
    chi = 4.0 * M * float(np.sum((blocks - 0.5) ** 2))
    return igamc(n / 2, chi / 2)


def runs(bits: np.ndarray) -> float:
    pi = bits.mean()
    if abs(pi - 0.5) >= 2 / math.sqrt(len(bits)):
        return 0.0
    vobs = int(np.sum(bits[:-1] != bits[1:])) + 1
    n = len(bits)
    num = abs(vobs - 2 * n * pi * (1 - pi))
    den = 2 * math.sqrt(2 * n) * pi * (1 - pi)
    return math.erfc(num / den)


def cumulative_sums(bits: np.ndarray) -> float:
    x = 2 * bits.astype(np.int64) - 1
    z = int(np.max(np.abs(np.cumsum(x))))
    n = len(bits)
    if z == 0:
        return 1.0
    start = int((-n / z + 1) / 4)
    end = int((n / z - 1) / 4)
    s1 = sum(_normcdf((4 * k + 1) * z / math.sqrt(n)) - _normcdf((4 * k - 1) * z / math.sqrt(n)) for k in range(start, end + 1))
    start = int((-n / z - 3) / 4)
    s2 = sum(_normcdf((4 * k + 3) * z / math.sqrt(n)) - _normcdf((4 * k + 1) * z / math.sqrt(n)) for k in range(start, end + 1))
    return max(0.0, min(1.0, 1.0 - s1 + s2))


def _phi(bits: np.ndarray, m: int) -> float:
    n = len(bits)
    if m == 0:
        return 0.0
    ext = np.concatenate([bits, bits[: m - 1]])
    counts: dict[int, int] = {}
    powers = 1 << np.arange(m - 1, -1, -1)
    for i in range(n):
        key = int(np.dot(ext[i : i + m], powers))
        counts[key] = counts.get(key, 0) + 1
    return sum((c / n) * math.log(c / n) for c in counts.values())


def approximate_entropy(bits: np.ndarray, m: int = 2) -> float:
    n = len(bits)
    apen = _phi(bits, m) - _phi(bits, m + 1)
    chi = 2 * n * (math.log(2) - apen)
    return igamc(2 ** (m - 1), chi / 2)


def serial(bits: np.ndarray, m: int = 2) -> float:
    n = len(bits)
    p1 = _serial_psi2(bits, m)
    p2 = _serial_psi2(bits, m - 1)
    p3 = _serial_psi2(bits, m - 2)
    d1 = p1 - p2
    return igamc(2 ** (m - 2), d1 / 2) if m >= 2 else 1.0


def _serial_psi2(bits: np.ndarray, m: int) -> float:
    if m <= 0:
        return 0.0
    n = len(bits)
    ext = np.concatenate([bits, bits[: m - 1]])
    counts: dict[int, int] = {}
    powers = 1 << np.arange(m - 1, -1, -1)
    for i in range(n):
        key = int(np.dot(ext[i : i + m], powers))
        counts[key] = counts.get(key, 0) + 1
    return (2 ** m / n) * sum(c * c for c in counts.values()) - n


def spectral_dft(bits: np.ndarray) -> float:
    x = 2 * bits.astype(np.float64) - 1
    n = len(bits)
    mags = np.abs(np.fft.rfft(x))[1 : n // 2]
    thresh = math.sqrt(math.log(1 / 0.05) * n)
    n0 = 0.95 * n / 2
    n1 = float(np.sum(mags < thresh))
    d = (n1 - n0) / math.sqrt(n * 0.95 * 0.05 / 4)
    return math.erfc(abs(d) / math.sqrt(2))


def run_battery(data: bytes) -> list[tuple[str, float, bool]]:
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8)).astype(np.int64)
    bytes_arr = np.frombuffer(data, dtype=np.uint8)

    results = [
        ("Monobit frequency", monobit(bits)),
        ("Block frequency (M=128)", block_frequency(bits)),
        ("Runs", runs(bits)),
        ("Cumulative sums", cumulative_sums(bits)),
        ("Approximate entropy (m=2)", approximate_entropy(bits)),
        ("Serial (m=2)", serial(bits)),
        ("Spectral DFT", spectral_dft(bits)),
    ]
    out = [(name, p, p >= ALPHA) for name, p in results]

    # descriptive extras (not p-value tests)
    counts = np.bincount(bytes_arr, minlength=256)
    H = -sum((c / len(bytes_arr)) * math.log2(c / len(bytes_arr)) for c in counts if c)
    comp = len(zlib.compress(data, 9)) / len(data)
    out.append((f"Shannon entropy = {H:.5f}/8.0 bits/byte", 1.0 if H > 7.99 else 0.0, H > 7.99))
    out.append((f"zlib compression ratio = {comp:.4f} (>=1.0 = incompressible)", 1.0 if comp >= 0.99 else 0.0, comp >= 0.99))
    return out


def _print(title: str, data: bytes) -> bool:
    print(f"\n=== {title} ({len(data)} bytes) ===")
    all_pass = True
    for name, p, ok in run_battery(data):
        all_pass &= ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:42s} p={p:.4f}")
    print(f"  -> {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return all_pass


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sample = open(args[0], "rb").read() if args else __import__("os").urandom(1_000_000)
    _print("Platon randomness" if args else "os.urandom", sample)
    if "--compare" in sys.argv:
        import os

        _print("os.urandom control (same size)", os.urandom(len(sample)))
