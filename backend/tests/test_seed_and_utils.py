"""Seed data (spec 9.3) and the deterministic helpers (normalisation, duplicate scoring, PO references)."""
import json
from datetime import date

from app import db, matching
from app.catalogue import default_config
from app.textutil import inr, parse_date, parse_money, po_keys, serial_token


def test_seed_gives_60_runs_and_14_open_exceptions(fresh_db):
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"] == 60
        counts = {r["outcome"]: r["n"] for r in con.execute(
            "SELECT d.outcome, COUNT(*) AS n FROM invoices i JOIN decisions d ON d.id=i.current_decision_id GROUP BY d.outcome")}
    assert counts == {"auto_approve": 32, "approve_with_note": 10, "route_for_review": 9, "hold_request_info": 5, "reject": 4}
    assert counts["route_for_review"] + counts["hold_request_info"] == 14
    assert round(100 * (32 + 10) / 60) == 70


def test_seed_named_history_and_po_positions(fresh_db):
    with db.conn() as con:
        named = {r["invoice_no_raw"]: dict(r) for r in con.execute(
            "SELECT i.invoice_no_raw, i.paid_at, i.file_path, d.outcome FROM invoices i JOIN decisions d "
            "ON d.id=i.current_decision_id WHERE i.is_synthetic=0")}
        assert set(named) == {"BL/2026/0377", "K/1187", "K/1203"}
        assert all(n["outcome"] == "auto_approve" and n["file_path"] for n in named.values())
        assert named["BL/2026/0377"]["paid_at"] == "2026-11-05"
        p1004 = matching.po_position(con, "PO-2026-1004")
        p1005 = matching.po_position(con, "PO-2026-1005")
        p0998 = matching.po_position(con, "PO-2026-0998")
        p1001 = matching.po_position(con, "PO-2026-1001")
    assert p1004["status"] == "partially_billed" and round(p1004["pct_billed"]) == 76
    assert p1004["lines"][0]["billed_qty"] == 7500
    assert p1005["status"] == "open" and p1005["billed_subtotal_paise"] == 0
    assert p0998["status"] == "fully_billed"
    assert p1001["status"] == "open"


def test_parse_money_indian_and_decimal_comma():
    assert parse_money("₹1,18,000.00") == 11800000
    assert parse_money("Rs. 3,23,379.00") == 32337900
    assert parse_money("INR 1,66,380.00") == 16638000
    assert parse_money("1.18.000,00") == 11800000
    assert inr(11800000) == "₹1,18,000.00"


def test_dates_day_first_and_ambiguity():
    r = parse_date("12/11/26", as_of=date(2026, 11, 16))
    assert r["value"] == date(2026, 11, 12) and r["ambiguous"]
    assert parse_date("09-Nov-2026")["value"] == date(2026, 11, 9)
    assert parse_date("11 November 2026")["value"] == date(2026, 11, 11)


def test_serial_token_and_po_references():
    assert serial_token("BL/2026/0377", 2026) == "377"
    assert serial_token("BL-0377-26", 2026) == "377"
    assert po_keys("Ref your PO 1002/2026 dated 12 Oct 2026") == [(2026, 1002)]
    assert po_keys("PO-2026-1001")[0] == (2026, 1001)


def _inv(no, d, total, po, desc):
    return {"invoice_no": no, "invoice_date": d, "total_paise": total, "po_id": po,
            "lines": [{"description": desc, "desc_norm": desc.lower(), "qty": 400, "pretax_unit_paise": 25000}]}


def test_duplicate_score_rescan_is_one():
    w = default_config()["advanced"]["dup_weights"]
    a = _inv("BL-0377-26", date(2026, 10, 20), 11800000, "PO-2026-0998", "copier paper a4 75gsm")
    b = _inv("BL/2026/0377", date(2026, 10, 20), 11800000, "PO-2026-0998", "copier paper a4 75gsm")
    assert matching.duplicate_score(a, b, w)["score"] == 1.0


def test_duplicate_monthly_lookalike_scores_below_060():
    """Same amount a month later, serial 0415, different service period: must not be a duplicate (spec 9.5)."""
    w = default_config()["advanced"]["dup_weights"]
    a = _inv("BL/2026/0415", date(2026, 11, 19), 11800000, "PO-2026-0998", "copier paper supply november 2026")
    b = _inv("BL/2026/0377", date(2026, 10, 20), 11800000, "PO-2026-0998", "copier paper supply october 2026")
    s = matching.duplicate_score(a, b, w)
    assert s["score"] < 0.60 and s["recurring_guard"]


def test_bundle_alignment_covers_two_po_lines():
    po_lines = [{"id": 1, "item_code": "DS-USB-C", "description": "USB-C docking station", "ordered_qty": 30,
                 "unit_price_paise": 720000},
                {"id": 2, "item_code": "KM-W1", "description": "Wireless keyboard and mouse set", "ordered_qty": 30,
                 "unit_price_paise": 180000}]
    line = {"line_no": 1, "description": "IT peripherals supply: docking stations and wireless keyboard-mouse sets, 30 each",
            "qty": 30, "pretax_amount_paise": 27405000, "pretax_unit_paise": 913500}
    al = matching.align_lines([line], po_lines)
    assert al[0]["method"] == "bundle" and al[0]["po_line_ids"] == [1, 2]
    assert sum(a["amount_paise"] for a in al[0]["alloc"]) == 27405000
