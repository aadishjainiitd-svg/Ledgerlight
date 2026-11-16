"""Live AI extraction (network). Runs only when a real key is available in the shell or backend/.env.

SI-05 is the image-only Greenleaf scan (EC3): no text layer and no PO number. A real vision model must read it and
the deterministic rules must reach the expected decision (spec 9.4): approve with a note, the PO implied from the
lines (PO-2026-1005). The model's confidence values vary, so only the decision path is asserted, not exact scores."""
import json

import pytest

from app import config
from tests.conftest import LIVE_KEYS, run_sample

EXPECTED = {s["id"]: s for s in json.loads((config.SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))["samples"]}


@pytest.mark.parametrize("provider,env", [("groq", "GROQ_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")])
def test_live_scan_ec3(provider, env, fresh_db, monkeypatch):
    if not LIVE_KEYS.get(env):
        pytest.skip(f"{env} not set: live {provider} test skipped")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv(env, LIVE_KEYS[env])
    assert config.llm_provider() == provider

    out = run_sample("SI-05")
    assert out["run"]["status"] == "completed", out["run"]
    d = out["decision"]
    assert d["outcome"] == EXPECTED["SI-05"]["expected_outcome"], (d["outcome"], d["headline"])
    r07 = json.loads(out["rules"]["R07"]["facts"])
    assert r07["method"] == "implied" and r07["po_id"] == "PO-2026-1005", r07
    assert out["rules"]["R14"]["severity"] == "pass", out["rules"]["R14"]
    assert len(out["rules"]) == 16
