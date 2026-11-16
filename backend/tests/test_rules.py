"""Unit tests: every rule R01-R16 has at least one passing and one failing case, plus band edges (spec 8.6)."""
import copy
from datetime import date

import pytest

from app import rules as R
from app.catalogue import default_config

AS_OF = date(2026, 11, 16)


def field(value, conf=0.98, **kw):
    return {"name": "", "label": kw.pop("label", "Field"), "value": value, "raw_text": value, "model_confidence": conf,
            "effective_confidence": conf, "boosted": False, "source": "text layer", **kw}


def make_ctx(**over):
    """A clean invoice: 100 units at ₹1,000 + 18% GST = ₹1,18,000, PO-2026-9001 for 100 units, nothing billed."""
    canon = {
        "fields": {
            "vendor_name": field("Acme Pvt Ltd", label="Vendor"), "vendor_gstin": field("27AAFCB4821K1Z3", label="Vendor GSTIN"),
            "invoice_no": field("AC/2026/0101", label="Invoice no."), "invoice_date": field("10 Nov 2026", label="Invoice date"),
            "po_reference": field("PO-2026-9001", label="PO reference"), "currency": field("INR", label="Currency"),
            "subtotal": field("100000.00", label="Subtotal"), "tax_total": field("18000.00", label="Tax (GST)"),
            "total": field("118000.00", label="Total"),
        },
        "lines": [{"line_no": 1, "description": "Widget", "desc_norm": "widget", "item_code": "W-1", "qty": 100.0,
                   "uom": "nos", "unit_price_paise": 100000, "amount_paise": 10000000, "pretax_amount_paise": 10000000,
                   "pretax_unit_paise": 100000, "tax_rate_pct": 18.0, "confidence": 0.98}],
        "vendor_gstin": "27AAFCB4821K1Z3", "invoice_no": "AC/2026/0101", "invoice_date": date(2026, 11, 10),
        "date_ambiguous": False, "currency": "INR", "subtotal_paise": 10000000, "tax_paise": 1800000,
        "tax_printed_paise": 1800000, "total_paise": 11800000, "tax_inclusive": False, "tax_rate_pct": 18.0,
        "other_charges_paise": 0, "discount_paise": 0, "bank": {"name": "Harbor Union Bank", "account": "0123 4567 8901",
                                                                 "ifsc": "HUBK0000214"},
        "bank_change_notice": False, "po_reference": "PO-2026-9001",
    }
    vendor = {"id": "V-900", "name": "Acme Pvt Ltd", "short": "Acme", "gstin": "27AAFCB4821K1Z3", "status": "approved",
              "bank_name": "Harbor Union Bank", "bank_account_no": "0123 4567 8901", "bank_ifsc": "HUBK0000214"}
    po = {"id": "PO-2026-9001", "vendor_id": "V-900", "issue_date": "2026-10-01", "valid_to": "2026-12-31", "status": "open",
          "currency": "INR", "lines": [{"id": 1, "line_no": 1, "item_code": "W-1", "description": "Widget", "uom": "nos",
                                        "ordered_qty": 100.0, "unit_price_paise": 100000, "tax_rate_pct": 18.0,
                                        "billed_qty": 0.0, "pending_qty": 0.0, "remaining_qty": 100.0}],
          "subtotal_paise": 10000000, "billed_subtotal_paise": 0, "pending_subtotal_paise": 0, "history": []}
    ctx = {"cfg": default_config(), "as_of": AS_OF, "extraction_status": "ok", "canon": canon,
           "vendor_match": {"vendor": vendor, "method": "gstin", "score": 1.0, "gstin_conflict": False},
           "bank": {"status": "match", "match": True}, "dup": {"score": 0.1, "exact": None, "closest": None, "compared": 3},
           "po_res": {"method": "explicit", "po": po, "score": 1.0, "matched_text": "PO-2026-9001", "candidates": []},
           "alignment": [{"line_no": 1, "po_line_ids": [1], "method": "sku", "score": 1.0,
                          "alloc": [{"po_line_id": 1, "qty": 100.0, "amount_paise": 10000000}]}]}
    for k, v in over.items():
        ctx[k] = v
    return ctx


def set_line(ctx, qty=None, unit=None):
    l = ctx["canon"]["lines"][0]
    if qty is not None:
        l["qty"] = qty
    if unit is not None:
        l["pretax_unit_paise"] = unit
    l["pretax_amount_paise"] = int(round(l["qty"] * l["pretax_unit_paise"]))
    ctx["alignment"][0]["alloc"] = [{"po_line_id": 1, "qty": l["qty"], "amount_paise": l["pretax_amount_paise"]}]
    return ctx


# ------------------------------------------------------------------ R01
def test_r01_pass():
    assert R.r01(make_ctx())["severity"] == "pass"


def test_r01_missing_invoice_number_holds():
    c = make_ctx()
    c["canon"]["fields"]["invoice_no"]["value"] = None
    r = R.r01(c)
    assert r["severity"] == "hold" and "invoice number" in r["message"]


def test_r01_scanned_without_key_holds():
    r = R.r01(make_ctx(extraction_status="unavailable"))
    assert r["severity"] == "hold" and "set ANTHROPIC_API_KEY" in r["message"]


# ------------------------------------------------------------------ R02
def test_r02_pass():
    assert R.r02(make_ctx())["severity"] == "pass"


def test_r02_note_between_075_and_090():
    c = make_ctx()
    c["canon"]["fields"]["invoice_date"]["effective_confidence"] = 0.80
    assert R.r02(c)["severity"] == "note"


def test_r02_hold_below_075():
    c = make_ctx()
    c["canon"]["fields"]["total"]["effective_confidence"] = 0.62
    assert R.r02(c)["severity"] == "hold"


# ------------------------------------------------------------------ R03
def test_r03_pass():
    assert R.r03(make_ctx())["severity"] == "pass"


def test_r03_future_date_holds():
    c = make_ctx()
    c["canon"]["invoice_date"] = date(2026, 12, 11)
    assert R.r03(c)["severity"] == "hold"


def test_r03_before_po_date_reviews():
    assert R.r03(make_ctx(), po_issue=date(2026, 11, 12))["severity"] == "review"


def test_r03_old_invoice_notes():
    c = make_ctx()
    c["canon"]["invoice_date"] = date(2026, 4, 1)
    assert R.r03(c)["severity"] == "note"


# ------------------------------------------------------------------ R04
def test_r04_pass():
    assert R.r04(make_ctx())["severity"] == "pass"


def test_r04_fuzzy_only_reviews():
    c = make_ctx()
    c["vendor_match"]["method"] = "fuzzy"
    assert R.r04(c)["severity"] == "review"


def test_r04_one_char_gstin_misread_on_scan_is_a_note():
    from app import matching
    vendors = [{"id": "V-104", "name": "Greenleaf Pantry Supplies", "gstin": "27AAJFG9054R1Z2", "aliases": []}]
    # scan: 'G' read as '0' (OCR-confusable) -> likely misread, not a conflict
    vm = matching.match_vendor(vendors, "GREENLEAF PANTRY SUPPLIES", "27AAJF09054R1Z2", scanned=True)
    assert vm["method"] == "name" and not vm["gstin_conflict"] and vm["gstin_misread"]["position"] == 7
    c = make_ctx()
    c["vendor_match"] = {**vm, "vendor": {**c["vendor_match"]["vendor"], "gstin": "27AAJFG9054R1Z2"}}
    c["canon"]["vendor_gstin"] = "27AAJF09054R1Z2"
    r = R.r04(c)
    assert r["severity"] == "note" and "character 7" in r["message"]
    # the same difference on a text PDF stays a conflict
    assert matching.match_vendor(vendors, "Greenleaf Pantry Supplies", "27AAJF09054R1Z2")["gstin_conflict"]
    # a non-confusable difference (G vs X) or two differences stays a conflict even on a scan
    assert matching.match_vendor(vendors, "Greenleaf Pantry Supplies", "27AAJFX9054R1Z2", scanned=True)["gstin_conflict"]
    assert matching.match_vendor(vendors, "Greenleaf Pantry Supplies", "27AAJF09054R1Z3", scanned=True)["gstin_conflict"]


def test_r04_pending_holds_and_blocked_rejects():
    c = make_ctx()
    c["vendor_match"]["vendor"]["status"] = "pending"
    assert R.r04(c)["severity"] == "hold"
    c["vendor_match"]["vendor"]["status"] = "blocked"
    assert R.r04(c)["severity"] == "reject"


def test_r04_unknown_vendor_rejects():
    c = make_ctx()
    c["vendor_match"] = {"vendor": None, "method": "none", "score": 0.0}
    assert R.r04(c)["severity"] == "reject"


# ------------------------------------------------------------------ R05
def test_r05_pass_when_bank_matches_or_absent():
    assert R.r05(make_ctx())["severity"] == "pass"
    assert R.r05(make_ctx(bank={"status": "not_applicable"}))["severity"] == "pass"


def test_r05_mismatch_holds():
    c = make_ctx(bank={"status": "mismatch", "match": False})
    c["canon"]["bank"] = {"name": "Riverbend Co-operative Bank", "account": "5020 0091 2334 7", "ifsc": "RBCB0000412"}
    r = R.r05(c)
    assert r["severity"] == "hold" and r["exposure_paise"] == 11800000


# ------------------------------------------------------------------ R06
CLOSEST = {"id": "INV-1", "invoice_no": "AC/2026/0055", "total_paise": 11800000, "invoice_date": "2026-11-01",
           "outcome": "auto_approve", "decided_at": "2026-11-02T10:00:00Z", "paid_at": None}


def test_r06_pass():
    assert R.r06(make_ctx())["severity"] == "pass"


def test_r06_review_band():
    c = make_ctx(dup={"score": 0.72, "exact": None, "closest": CLOSEST, "signals": {}, "compared": 3})
    assert R.r06(c)["severity"] == "review"


def test_r06_reject_band_and_exact():
    c = make_ctx(dup={"score": 0.85, "exact": None, "closest": CLOSEST, "signals": {"amount": 1}, "compared": 3})
    assert R.r06(c)["severity"] == "reject"
    c = make_ctx(dup={"score": 1.0, "exact": "file", "closest": CLOSEST, "compared": 3})
    assert R.r06(c)["severity"] == "reject"


# ------------------------------------------------------------------ R07
def test_r07_explicit_pass():
    assert R.r07(make_ctx())["severity"] == "pass"


def test_r07_implied_strong_small_is_note():
    c = make_ctx()
    c["po_res"].update(method="implied", score=0.96, runner_up=0.14, runner_up_po="PO-2026-9002", gap=0.82)
    c["canon"]["total_paise"] = 7875000
    assert R.r07(c)["severity"] == "note"


def test_r07_implied_above_ceiling_reviews():
    c = make_ctx()
    c["po_res"].update(method="implied", score=0.96, runner_up=0.14, runner_up_po="PO-2026-9002", gap=0.82)
    assert R.r07(c)["severity"] == "review"   # ₹1,18,000 > ₹1,00,000


def test_r07_no_candidate_holds_and_other_vendor_reviews():
    c = make_ctx(po_res={"method": "none", "po": None, "candidates": []})
    assert R.r07(c)["severity"] == "hold"
    c = make_ctx()
    c["po_res"]["method"] = "other_vendor"
    assert R.r07(c)["severity"] == "review"


# ------------------------------------------------------------------ R08
def test_r08_pass():
    assert R.r08(make_ctx())["severity"] == "pass"


def test_r08_closed_or_fully_billed_rejects():
    c = make_ctx()
    c["po_res"]["po"]["status"] = "closed"
    assert R.r08(c)["severity"] == "reject"
    c["po_res"]["po"]["status"] = "fully_billed"
    assert R.r08(c)["severity"] == "reject"


def test_r08_outside_validity_reviews():
    c = make_ctx()
    c["po_res"]["po"]["valid_to"] = "2026-11-05"
    assert R.r08(c)["severity"] == "review"


# ------------------------------------------------------------------ R09
def test_r09_pass():
    assert R.r09(make_ctx())["severity"] == "pass"


def _with_extra_line(value_paise):
    c = make_ctx()
    c["canon"]["lines"].append({"line_no": 2, "description": "Gift hamper", "qty": 1.0, "pretax_amount_paise": value_paise,
                                "pretax_unit_paise": value_paise, "tax_rate_pct": 18.0, "confidence": 0.98})
    c["alignment"].append({"line_no": 2, "po_line_ids": [], "method": "none", "score": 0.0, "alloc": []})
    return c


def test_r09_small_unordered_reviews_large_rejects():
    assert R.r09(_with_extra_line(500000))["severity"] == "review"     # 4.8% of invoice
    assert R.r09(_with_extra_line(5000000))["severity"] == "reject"    # 33% of invoice


# ------------------------------------------------------------------ R10 (variance bands)
@pytest.mark.parametrize("unit,expected", [
    (100000, "pass"), (100500, "pass"),      # exact, +0.5% passes
    (101500, "note"),                        # +1.5%, ₹1,500 on the line: note
    (102000, "note"),                        # +2.0% and ₹2,000: note (edge)
    (103000, "review"),                      # +3%: review
    (111000, "reject"),                      # +11%: different transaction
    (95000, "note"),                         # undercharge -5%: capped at note
])
def test_r10_bands(unit, expected):
    assert R.r10(set_line(make_ctx(), unit=unit))["severity"] == expected


def test_r10_two_percent_but_over_5000_rupees_reviews():
    c = make_ctx()
    c["po_res"]["po"]["lines"][0]["ordered_qty"] = 1000.0
    c["po_res"]["po"]["lines"][0]["remaining_qty"] = 1000.0
    assert R.r10(set_line(c, qty=1000.0, unit=101500))["severity"] == "review"  # 1.5% but ₹15,000


# ------------------------------------------------------------------ R11
def test_r11_pass():
    assert R.r11(make_ctx())["severity"] == "pass"


def test_r11_cumulative_over_remaining_reviews():
    c = make_ctx()
    pl = c["po_res"]["po"]["lines"][0]
    pl["ordered_qty"], pl["billed_qty"], pl["remaining_qty"] = 10000.0, 7500.0, 2500.0
    c["canon"]["lines"][0]["qty"] = 3000.0
    c["alignment"][0]["alloc"][0]["qty"] = 3000.0
    r = R.r11(c)
    assert r["severity"] == "review" and r["facts"]["lines"][0]["over"] == 500


def test_r11_far_over_rejects():
    c = make_ctx()
    pl = c["po_res"]["po"]["lines"][0]
    pl["billed_qty"], pl["remaining_qty"] = 100.0, 0.0
    assert R.r11(c)["severity"] == "reject"


# ------------------------------------------------------------------ R12
def test_r12_pass():
    assert R.r12(make_ctx())["severity"] == "pass"


def test_r12_ec1_cumulative_overbilling_reviews():
    c = make_ctx()
    po = c["po_res"]["po"]
    po["subtotal_paise"], po["billed_subtotal_paise"] = 42000000, 32000000
    c["alignment"][0]["alloc"][0]["amount_paise"] = 12000000
    r = R.r12(c)
    assert r["severity"] == "review" and r["facts"]["delta_paise"] == 2000000 and r["exposure_paise"] == 2360000


def test_r12_small_over_is_note():
    c = make_ctx()
    c["alignment"][0]["alloc"][0]["amount_paise"] = 10150000   # +₹1,500 (1.5%)
    assert R.r12(c)["severity"] == "note"


# ------------------------------------------------------------------ R13
def test_r13_pass():
    assert R.r13(make_ctx())["severity"] == "pass"


@pytest.mark.parametrize("shown,expected", [(1800500, "note"), (1805000, "review"), (800000, "reject")])
def test_r13_tax_steps(shown, expected):
    c = make_ctx()
    c["canon"]["tax_printed_paise"] = shown
    assert R.r13(c)["severity"] == expected


def test_r13_wrong_rate_reviews():
    c = make_ctx()
    c["po_res"]["po"]["lines"][0]["tax_rate_pct"] = 12.0
    assert R.r13(c)["severity"] == "review"


# ------------------------------------------------------------------ R14
def test_r14_pass():
    assert R.r14(make_ctx())["severity"] == "pass"


def test_r14_mismatch_rejects_when_confident_holds_when_not():
    c = make_ctx()
    c["canon"]["total_paise"] = 12000000
    assert R.r14(c)["severity"] == "reject"
    c["canon"]["fields"]["total"]["effective_confidence"] = 0.70
    assert R.r14(c)["severity"] == "hold"


def test_r14_small_difference_notes():
    c = make_ctx()
    c["canon"]["total_paise"] = 11800500
    assert R.r14(c)["severity"] == "note"


# ------------------------------------------------------------------ R15
def test_r15_pass():
    assert R.r15(make_ctx())["severity"] == "pass"


def test_r15_above_cap_reviews():
    c = make_ctx()
    c["canon"]["total_paise"] = 100000001
    assert R.r15(c)["severity"] == "review"


# ------------------------------------------------------------------ R16
def test_r16_pass():
    assert R.r16(make_ctx())["severity"] == "pass"


def test_r16_currency_mismatch_reviews():
    c = make_ctx()
    c["canon"]["currency"] = "USD"
    assert R.r16(c)["severity"] == "review"


# ------------------------------------------------------------------ decision engine
def _res(**sev):
    out = {}
    for rid in [f"R{i:02d}" for i in range(1, 17)]:
        out[rid] = {"rule_id": rid, "severity": sev.get(rid, "pass"), "skipped": False, "exposure_paise": 0, "facts": {}}
    return out


def test_decision_worst_severity_wins():
    cfg = default_config()
    assert R.decide(_res(), cfg, 100)["outcome"] == "auto_approve"
    assert R.decide(_res(R10="note"), cfg, 100)["outcome"] == "approve_with_note"
    assert R.decide(_res(R10="note", R11="review"), cfg, 100)["outcome"] == "route_for_review"
    assert R.decide(_res(R11="review", R05="hold"), cfg, 100)["outcome"] == "hold_request_info"
    d = R.decide(_res(R05="hold", R06="reject"), cfg, 100)
    assert d["outcome"] == "reject" and d["driving_rule_ids"] == ["R06"]


def test_disabled_rule_is_skipped_and_auto_approve_toggle():
    cfg = copy.deepcopy(default_config())
    cfg["enabled"]["R15"] = False
    r = R.apply_enabled({"rule_id": "R15", "severity": "review", "skipped": False, "message": "x", "exposure_paise": 5}, cfg)
    assert r["skipped"] and r["severity"] == "pass"
    cfg["global"]["auto"] = False
    assert R.decide(_res(), cfg, 100)["outcome"] == "route_for_review"
