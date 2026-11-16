import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolated database for the test session; no auto-seed on app start; no display pacing.
_TMP = Path(tempfile.mkdtemp(prefix="ledgerlight-test-"))
os.environ["LEDGERLIGHT_DATA_DIR"] = str(_TMP)
os.environ["LEDGERLIGHT_DB"] = str(_TMP / "test.db")
os.environ["LEDGERLIGHT_AUTOSEED"] = "0"
os.environ["LEDGERLIGHT_PACE"] = "instant"
os.environ.setdefault("LEDGERLIGHT_AS_OF", "2026-11-16")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The main suite is offline and deterministic: AI keys are removed and backend/.env is not loaded.
# Keys from the shell or backend/.env are kept aside for the opt-in live tests (tests/test_live_ai.py).
os.environ["LEDGERLIGHT_DOTENV"] = "0"
from app.config import load_dotenv  # noqa: E402

_DOTENV = load_dotenv(Path(__file__).resolve().parent.parent / ".env")
LIVE_KEYS = {k: (os.environ.pop(k, "") or _DOTENV.get(k, "")).strip() for k in ("ANTHROPIC_API_KEY", "GROQ_API_KEY")}

from app import config, db, pipeline, seed, services  # noqa: E402


_TEMPLATE = _TMP / "seeded-template.db"


@pytest.fixture()
def fresh_db():
    """A freshly seeded database. Seeding runs the real pipeline once; later tests restore a copy of it."""
    import sqlite3
    if not _TEMPLATE.exists():
        seed.reset_and_seed()
        src, dst = db.connect(), sqlite3.connect(str(_TEMPLATE))
    else:
        src, dst = sqlite3.connect(str(_TEMPLATE)), db.connect()
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    yield


def run_sample(sample_id: str) -> dict:
    """Upload a sample's PDF bytes (the pipeline never sees the sample id) and run all nine stages."""
    s = services.sample_by_id(sample_id)
    data = (config.SAMPLES_DIR / s["file"]).read_bytes()
    iid, rid = services.new_run(file_name="upload.pdf", data=data, source="upload", sample_id=None, pace=0,
                                use_cache=True, triggered_by="pytest")
    res = pipeline.run_sync(rid, publish=False)
    with db.conn() as con:
        d = con.execute("SELECT * FROM decisions WHERE run_id=? AND made_by='system'", (rid,)).fetchone()
        rules = {r["rule_id"]: dict(r) for r in con.execute("SELECT * FROM rule_results WHERE run_id=?", (rid,))}
    return {"run": res, "decision": dict(d) if d else None, "rules": rules, "invoice_id": iid, "run_id": rid}
