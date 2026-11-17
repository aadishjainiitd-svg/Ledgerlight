"""Per-visitor sandboxes (LEDGERLIGHT_SANDBOXES=1, the public deployment): every visitor gets a private copy of the
demo data, so samples always behave as designed and a reset only affects that visitor."""
import os
import time

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
from tests.test_api import read_sse, wait_done

A = {"X-Ledgerlight-Sandbox": "a" * 24}
B = {"X-Ledgerlight-Sandbox": "b" * 24}


@pytest.fixture()
def sb_client(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "SANDBOXES", True)
    with TestClient(app) as c:           # startup builds the template
        yield c


def run_sample(c, headers, sample_id):
    r = c.post("/api/runs", json={"sample_id": sample_id, "pace": "instant"}, headers=headers)
    assert r.status_code == 201, r.text
    rid = r.json()["runs"][0]["run_id"]
    t0 = time.time()
    while time.time() - t0 < 30:
        d = c.get(f"/api/runs/{rid}", headers=headers).json()
        if d["run"]["status"] in ("completed", "failed"):
            return rid, d
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def outcome(d):
    return (d.get("decision") or {}).get("outcome")


def run_ids(c, headers):
    return {r["run_id"] for r in c.get("/api/runs?range=all&page_size=200&all_runs=true", headers=headers).json()["items"]}


def test_two_visitors_get_the_designed_decision_and_never_see_each_other(sb_client):
    ra, da = run_sample(sb_client, A, "SI-01")
    rb, db_ = run_sample(sb_client, B, "SI-01")
    # without sandboxes the second run would be rejected as a duplicate of the first
    assert outcome(da) == "auto_approve" and outcome(db_) == "auto_approve"
    assert ra in run_ids(sb_client, A) and ra not in run_ids(sb_client, B)
    assert rb in run_ids(sb_client, B) and rb not in run_ids(sb_client, A)
    # the same visitor running it again is still caught as a duplicate
    _, again = run_sample(sb_client, A, "SI-01")
    assert outcome(again) == "reject"


def test_reset_only_affects_that_visitor(sb_client):
    ra, _ = run_sample(sb_client, A, "SI-02")
    rb, _ = run_sample(sb_client, B, "SI-02")
    res = sb_client.post("/api/demo/reset", headers=A).json()
    assert res["runs"] == 60 and res["open_exceptions"] == 14
    assert ra not in run_ids(sb_client, A)
    assert rb in run_ids(sb_client, B)


def test_request_without_id_gets_a_new_sandbox_and_the_id_back(sb_client):
    r = sb_client.get("/api/health")
    sid = r.headers.get("x-ledgerlight-sandbox")
    assert sid and db.SANDBOX_RE.match(sid)
    assert (db.sandbox_dir() / f"{sid}.db").exists()
    # an invalid id is replaced, never used as a file name
    r = sb_client.get("/api/health", headers={"X-Ledgerlight-Sandbox": "../../etc/passwd"})
    assert db.SANDBOX_RE.match(r.headers["x-ledgerlight-sandbox"])


def test_live_stream_and_images_work_with_the_query_parameter(sb_client):
    rid, d = run_sample(sb_client, A, "SI-01")
    sid = A["X-Ledgerlight-Sandbox"]
    events = read_sse(sb_client, f"/api/runs/{rid}/events?sandbox={sid}")
    assert any(e["event"] == "decision" for e in events)
    inv = d["invoice"]["id"]
    assert sb_client.get(f"/api/invoices/{inv}/pages/1.png?dpi=40&sandbox={sid}").status_code == 200
    # another visitor cannot see that run
    assert sb_client.get(f"/api/runs/{rid}", headers=B).status_code == 404


def test_old_sandboxes_are_cleaned_up(sb_client):
    sb_client.get("/api/health", headers=A)
    old = db.sandbox_dir() / f"{'a' * 24}.db"
    past = time.time() - db.SANDBOX_MAX_AGE_S - 60
    os.utime(old, (past, past))
    sb_client.get("/api/health", headers={"X-Ledgerlight-Sandbox": "c" * 24})   # a new visitor triggers clean-up
    assert not old.exists()


def test_ai_extraction_cache_is_shared_by_all_visitors(sb_client):
    with db.use_sandbox("a" * 24), db.shared_conn() as con:
        con.execute("INSERT OR REPLACE INTO extraction_cache (cache_key, file_sha256, prompt_version, model, result, "
                    "created_at) VALUES ('shared-k', 'sha', 'v', 'm', '{}', '2026-11-17T00:00:00Z')")
    with db.use_sandbox("b" * 24), db.shared_conn() as con:
        assert con.execute("SELECT COUNT(*) AS n FROM extraction_cache WHERE cache_key='shared-k'").fetchone()["n"] == 1
