import base64
import os

import pytest

from platon.signing import Signer, pqc_available


class TestEnvInjectedKey:
    def test_env_seed_is_used_and_deterministic(self, monkeypatch, tmp_path):
        seed = os.urandom(32)
        monkeypatch.setenv("PLATON_SIGNING_SEED_B64", base64.b64encode(seed).decode())
        a = Signer(tmp_path / "a")  # path is ignored when env seed is present
        b = Signer(tmp_path / "b")
        assert a.public_key_b64 == b.public_key_b64  # derived from the same seed
        assert not (tmp_path / "a").exists()  # nothing written to disk
        sig = a.sign_payload("x|y")
        assert Signer.verify("x|y", sig["value"], a.public_key_b64) is True

    def test_bad_env_seed_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PLATON_SIGNING_SEED_B64", base64.b64encode(b"too-short").decode())
        with pytest.raises(RuntimeError):
            Signer(tmp_path / "k")


class TestPQCHybrid:
    def test_off_by_default(self, tmp_path):
        sig = Signer(tmp_path / "k").sign_payload("hello")
        assert "pq_value" not in sig
        assert Signer.verify_signature_object("hello", sig) is True

    @pytest.mark.skipif(not pqc_available(), reason="dilithium-py not installed")
    def test_hybrid_requires_both(self, monkeypatch, tmp_path):
        monkeypatch.setattr("platon.signing.settings.pqc_enabled", True)
        s = Signer(tmp_path / "k")
        sig = s.sign_payload("hello|world")
        assert sig["algorithm"] == "ed25519" and sig["pq_algorithm"] == "ml-dsa-65"
        assert Signer.verify_signature_object("hello|world", sig) is True
        # tamper either signature -> hybrid fails
        bad_pq = dict(sig)
        bad_pq["pq_value"] = "AA" + sig["pq_value"][2:]
        assert Signer.verify_signature_object("hello|world", bad_pq) is False
        bad_ed = dict(sig)
        bad_ed["value"] = "AA" + sig["value"][2:]
        assert Signer.verify_signature_object("hello|world", bad_ed) is False
