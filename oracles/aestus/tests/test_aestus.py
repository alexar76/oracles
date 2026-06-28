import pytest
from httpx import ASGITransport, AsyncClient

from aestus import rsw
from aestus.main import app

# Small T keeps the suite fast: seal and open each cost T sequential squarings
# (φ is burned, so there is no fast-seal shortcut), so we keep T modest.
T_SMALL = 2000


class TestRSW:
    def test_prime_gen_is_prime(self):
        p = rsw._gen_prime(160)
        assert rsw._is_probable_prime(p)
        assert p.bit_length() == 160 and p % 2 == 1

    def test_miller_rabin_rejects_composites(self):
        assert not rsw._is_probable_prime(561)  # Carmichael number
        assert not rsw._is_probable_prime(1000)
        assert rsw._is_probable_prime(2) and rsw._is_probable_prime(97)

    def test_modulus_is_product_of_two_distinct_primes(self):
        N, p, q = rsw.gen_modulus(512)
        assert p != q and p * q == N
        assert rsw._is_probable_prime(p) and rsw._is_probable_prime(q)

    def test_squarings_matches_double_exponent(self):
        # b = a^(2^T) mod N must equal pow(a, 2**T, N) for small T
        N, _, _ = rsw.gen_modulus(256)
        a = 5
        assert rsw.squarings(a, 10, N) == pow(a, 2 ** 10, N)

    def test_seal_open_roundtrip(self):
        # fresh randomness each call → N differs; assert open(seal(x)) == x.
        msg = "the launch code is 8842-thaw"
        puzzle = rsw.seal(msg, T_SMALL, encoding="utf8", modulus_bits=512)
        opened = rsw.open_puzzle(puzzle)
        assert opened["data"] == msg
        assert opened["valid"] is True

    def test_seal_burns_trapdoor(self):
        # The puzzle must NEVER contain p, q, or φ — only the public puzzle data.
        puzzle = rsw.seal("x", 500, modulus_bits=512)
        assert set(puzzle) == {
            "scheme", "N", "a", "T", "ciphertext", "key_commitment", "modulus_bits", "encoding",
        }
        assert "p" not in puzzle and "q" not in puzzle and "phi" not in puzzle

    def test_fresh_modulus_each_seal(self):
        p1 = rsw.seal("same", 300, modulus_bits=512)
        p2 = rsw.seal("same", 300, modulus_bits=512)
        assert p1["N"] != p2["N"]  # fresh primes every seal

    def test_hex_encoding_roundtrip(self):
        data = "deadbeef00ff"
        puzzle = rsw.seal(data, T_SMALL, encoding="hex", modulus_bits=512)
        assert rsw.open_puzzle(puzzle)["data"] == data

    def test_verify_correct_b_true_wrong_b_false(self):
        puzzle = rsw.seal("hello", T_SMALL, modulus_bits=512)
        b = rsw.open_puzzle(puzzle)["b"]
        assert rsw.verify(puzzle, b)["valid"] is True
        wrong = str((int(b) + 1) % int(puzzle["N"]))
        assert rsw.verify(puzzle, wrong)["valid"] is False

    def test_tampered_ciphertext_decrypts_to_garbage(self):
        # Commitment binds b (not the ciphertext): a ciphertext-only tamper keeps
        # valid True (b is unchanged) but corrupts the recovered plaintext.
        puzzle = rsw.seal("top secret", T_SMALL, modulus_bits=512)
        ct = bytearray.fromhex(puzzle["ciphertext"])
        ct[0] ^= 0xFF
        puzzle["ciphertext"] = ct.hex()
        opened = rsw.open_puzzle(puzzle)
        assert opened["valid"] is True
        assert opened["data"] != "top secret"

    def test_tampered_T_flips_valid_false(self):
        # Tampering N/a/T changes the recomputed b → commitment mismatch.
        puzzle = rsw.seal("payload", T_SMALL, modulus_bits=512)
        puzzle["T"] = puzzle["T"] + 1
        assert rsw.open_puzzle(puzzle)["valid"] is False

    def test_T_clamped_to_max(self):
        puzzle = rsw.seal("x", rsw.MAX_T + 10, modulus_bits=512)
        assert puzzle["T"] == rsw.MAX_T


class TestAestusApp:
    @pytest.mark.asyncio
    async def test_seal_open_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            sealed = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.seal@v1",
                "input": {"data": "sealed-by-agent", "T": T_SMALL, "modulus_bits": 512},
            })).json()
            assert sealed["ok"] is True
            puzzle = sealed["output"]
            assert puzzle["scheme"] == rsw.SCHEME
            assert "key_commitment" in puzzle

            opened = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.open@v1",
                "input": {"puzzle": puzzle},
            })).json()
            assert opened["ok"] is True
            assert opened["output"]["data"] == "sealed-by-agent"
            assert opened["output"]["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            puzzle = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.seal@v1",
                "input": {"data": "x", "T": T_SMALL, "modulus_bits": 512},
            })).json()["output"]
            b = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.open@v1", "input": {"puzzle": puzzle},
            })).json()["output"]["b"]

            good = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.verify@v1", "input": {"puzzle": puzzle, "b": b},
            })).json()
            assert good["ok"] is True and good["output"]["valid"] is True

            bad = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.verify@v1",
                "input": {"puzzle": puzzle, "b": str((int(b) + 1) % int(puzzle["N"]))},
            })).json()
            assert bad["output"]["valid"] is False

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "aestus.seal@v1", "input": {},
            })).json()
            assert r["ok"] is False and "data" in r["error"]

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"aestus.seal@v1", "aestus.open@v1", "aestus.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True
