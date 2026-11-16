"""Golden tests: each sample PDF through the real nine-stage pipeline gives its expected decision (spec 9.4)."""
import json

import pytest

from app import config, db
from tests.conftest import run_sample

EXPECTED = json.loads((config.SAMPLES_DIR / "expected.json").read_text(encoding="utf-8"))["samples"]


@pytest.mark.parametrize("sample", EXPECTED, ids=[s["id"] for s in EXPECTED])
def test_sample_decision(sample, fresh_db):
    if sample["requires_llm"] and not config.llm_available():
        pytest.skip(f"{sample['id']} is an image-only scan: it needs Claude vision extraction and ANTHROPIC_API_KEY "
                    f"is not set (see test_scan_without_key_is_held)")
    out = run_sample(sample["id"])
    assert out["run"]["status"] == "completed", out["run"]
    d = out["decision"]
    assert d["outcome"] == sample["expected_outcome"], (d["outcome"], d["headline"])
    driving = json.loads(d["driving_rule_ids"])
    assert set(sample["driving_rules"]) <= set(driving), (sample["driving_rules"], driving)
    if sample["driving_rules"]:
        assert driving[0] == sample["driving_rules"][0]
    # every one of the 16 rules has a stored result
    assert len(out["rules"]) == 16


def test_si01_happy_path_details(fresh_db):
    out = run_sample("SI-01")
    with db.conn() as con:
        inv = dict(con.execute("SELECT * FROM invoices WHERE id=?", (out["invoice_id"],)).fetchone())
    fields = json.loads(inv["fields"])
    assert inv["total_paise"] == 59000000 and inv["po_id"] == "PO-2026-1001" and inv["vendor_id"] == "V-101"
    assert all(f["effective_confidence"] >= 0.95 for f in fields.values() if f["value"] is not None)
    assert all(r["severity"] == "pass" for r in out["rules"].values())


def test_si03_ec1_numbers(fresh_db):
    out = run_sample("SI-03")
    d = out["decision"]
    assert d["exposure_paise"] == 2360000 and d["assigned_to"] == "manager"
    r11 = json.loads(out["rules"]["R11"]["facts"])["lines"][0]
    assert (r11["ordered"], r11["billed_before"], r11["remaining"], r11["over"]) == (10000, 7500, 2500, 500)
    r12 = json.loads(out["rules"]["R12"]["facts"])
    assert r12["after_paise"] == 44000000 and r12["po_subtotal_paise"] == 42000000
    expl = json.loads(d["explanation"])
    assert "10,500 cartons" in expl["attention"][0] and "₹23,600" in expl["attention"][0]
    assert expl["next_step"].startswith("Approve ₹1,18,000 (2,500 cartons)")


def test_si04_ec2_duplicate_of_paid_invoice(fresh_db):
    out = run_sample("SI-04")
    f = json.loads(out["rules"]["R06"]["facts"])
    assert f["score"] == 1.0 and f["closest"]["invoice_no"] == "BL/2026/0377" and not f["exact"]
    assert out["decision"]["exposure_paise"] == 11800000


def test_si06_ec4_bank_change(fresh_db):
    out = run_sample("SI-06")
    assert out["rules"]["R05"]["severity"] == "hold"
    others = [r for k, r in out["rules"].items() if k != "R05"]
    assert all(r["severity"] == "pass" for r in others)
    assert out["decision"]["exposure_paise"] == 16638000


def test_scan_without_key_is_held(fresh_db, monkeypatch):
    """EC3 without a key: the image-only scan must not crash; it is held with a plain-English reason."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = run_sample("SI-05")
    assert out["run"]["status"] == "completed"
    d = out["decision"]
    assert d["outcome"] == "hold_request_info"
    assert "scanned invoice needs AI extraction; set ANTHROPIC_API_KEY" in d["headline"]
    assert "scanned invoice needs AI extraction; set ANTHROPIC_API_KEY" in out["rules"]["R01"]["message_plain"]
    assert json.loads(d["driving_rule_ids"]) == ["R01"]


def test_same_file_twice_is_exact_duplicate(fresh_db):
    run_sample("SI-01")
    second = run_sample("SI-01")
    assert second["decision"]["outcome"] == "reject"
    assert json.loads(second["rules"]["R06"]["facts"])["exact"] == "file"
