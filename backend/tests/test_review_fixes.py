"""Regression tests for the verified review findings (docs/review/LOOPHOLES.md C1-C6, OFFICE_HOURS.md L2/L5).

Each PDF in tests/fixtures/review/ is the exact adversarial file that exposed the hole; it goes through the real
nine-stage pipeline against the seeded demo data."""
import json
import threading
from pathlib import Path

from app import admin, config, db, matching, pipeline, repo, services
from app.extract_text import classify_document

FIX = Path(__file__).resolve().parent / "fixtures" / "review"


def new_run(name: str) -> str:
    data = (FIX / name).read_bytes()
    _, rid = services.new_run(file_name=name, data=data, source="upload", sample_id=None, pace=0, use_cache=True,
                              triggered_by="pytest")
    return rid


def decision(rid: str) -> dict:
    with db.conn() as con:
        d = dict(con.execute("SELECT * FROM decisions WHERE run_id=? AND made_by='system'", (rid,)).fetchone())
        rules = {r["rule_id"]: dict(r) for r in con.execute("SELECT * FROM rule_results WHERE run_id=?", (rid,))}
    d["rules"] = rules
    d["driving"] = json.loads(d["driving_rule_ids"])
    return d


def run(name: str) -> dict:
    rid = new_run(name)
    res = pipeline.run_sync(rid, publish=False)
    assert res["status"] == "completed", res
    return decision(rid)


# ------------------------------------------------------------------ control
def test_clean_invoice_still_auto_approves(fresh_db):
    assert run("K01_clean.pdf")["outcome"] == "auto_approve"


# ------------------------------------------------------------------ C2, C3: bank check
def test_c2_second_bank_account_further_down_is_held(fresh_db):
    d = run("A02_second_bank_line.pdf")
    assert d["outcome"] == "hold_request_info" and d["driving"][0] == "R05"
    facts = json.loads(d["rules"]["R05"]["facts"])
    assert facts["invoice_account"].endswith("3347")          # the Riverbend account, not the master one


def test_c2_invisible_master_account_is_ignored(fresh_db):
    d = run("A04_hidden_bank.pdf")
    assert d["outcome"] == "hold_request_info" and d["driving"][0] == "R05"


def test_c3_hyphenated_account_is_read_and_held(fresh_db):
    d = run("A03_hyphen_account.pdf")
    assert d["outcome"] == "hold_request_info" and d["driving"][0] == "R05"


def test_bank_compare_checks_every_entry_and_unreadable_bank():
    vendor = {"bank_name": "Harbor Union Bank", "bank_account_no": "0001 2345 6789", "bank_ifsc": "HUBK0000101"}
    ok = {"name": "Harbor Union Bank", "account": "0001 2345 6789", "ifsc": "HUBK0000101"}
    bad = {"name": "Riverbend Co-operative Bank", "account": "5020-0091-23347", "ifsc": None}
    assert matching.bank_compare(ok, False, vendor, [ok])["status"] == "match"
    r = matching.bank_compare(ok, False, vendor, [ok, bad])
    assert r["status"] == "mismatch" and r["offending"] is bad
    named_only = {"name": "Riverbend Co-operative Bank", "account": None, "ifsc": None}
    assert matching.bank_compare(named_only, False, vendor, [named_only])["status"] == "unreadable"
    same_bank = {"name": "HARBOR UNION BANK LTD", "account": None, "ifsc": None}
    assert matching.bank_compare(same_bank, False, vendor, [same_bank])["status"] == "not_applicable"


# ------------------------------------------------------------------ C4: same invoice twice in one batch
def test_c4_two_copies_in_flight_pay_at_most_once(fresh_db):
    r1, r2 = new_run("A05_copy1.pdf"), new_run("A05_copy2.pdf")
    threads = [threading.Thread(target=pipeline.run_sync, args=(r,), kwargs={"publish": False}) for r in (r1, r2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    outcomes = sorted(decision(r)["outcome"] for r in (r1, r2))
    assert outcomes == ["auto_approve", "reject"], outcomes
    rejected = next(decision(r) for r in (r1, r2) if decision(r)["outcome"] == "reject")
    assert rejected["driving"][0] == "R06"


# ------------------------------------------------------------------ C5: document type
def test_c5_credit_note_and_proforma_are_held_not_paid(fresh_db):
    for name, kind in (("A07_credit_note.pdf", "credit_note"), ("A08_proforma.pdf", "proforma"),
                       ("K15_statement.pdf", "statement")):
        d = run(name)
        assert d["outcome"] == "hold_request_info", (name, d["headline"])
        facts = json.loads(d["rules"]["R01"]["facts"])
        assert facts["reason"] == "wrong_doc_type" and facts["doc_kind"] == kind


def test_c5_genuine_invoice_after_credit_note_is_not_a_duplicate(fresh_db):
    run("A07_credit_note.pdf")
    s = services.sample_by_id("SI-03")
    data = (config.SAMPLES_DIR / s["file"]).read_bytes()
    _, rid = services.new_run(file_name="upload.pdf", data=data, source="upload", sample_id=None, pace=0,
                              use_cache=True, triggered_by="pytest")
    pipeline.run_sync(rid, publish=False)
    d = decision(rid)
    assert d["outcome"] == "route_for_review" and "R06" not in d["driving"], (d["outcome"], d["driving"])


def test_classify_document_titles_only():
    assert classify_document("Kestrel Print & Pack\nCREDIT NOTE\nAgainst Invoice No: K/1241") == "credit_note"
    assert classify_document("Greenleaf\nPROFORMA INVOICE\nProforma Invoice No: PI/1") == "proforma"
    assert classify_document("Brightline\nTAX INVOICE\nInvoice No: BL/1\nAgainst Invoice No: X") is None
    assert classify_document("Corevolt\nINVOICE\nPURCHASE ORDER\nPO-2026-1008") is None   # SI-06 layout: a PO label under the INVOICE title
    for sample in ("SI-01", "SI-02", "SI-03", "SI-04", "SI-06", "SI-07"):
        from app import pdfio
        s = services.sample_by_id(sample)
        text = pdfio.inspect((config.SAMPLES_DIR / s["file"]).read_bytes())["text"]
        assert classify_document(text) is None, sample


# ------------------------------------------------------------------ C6, C1: line checks
def test_c6_line_without_quantity_still_gets_price_checked(fresh_db):
    d = run("A09_no_qty.pdf")
    assert d["outcome"] in ("reject", "route_for_review"), d["headline"]
    assert d["rules"]["R10"]["severity"] in ("reject", "review")
    assert "₹0.00 matches" not in (d["rules"]["R10"]["message_plain"] or "")


def test_c1_charge_on_no_line_goes_to_review(fresh_db):
    d = run("A01_subtotal_gap.pdf")
    assert d["outcome"] == "route_for_review" and d["driving"][0] == "R14"
    facts = json.loads(d["rules"]["R14"]["facts"])
    assert facts["unexplained_paise"] == 1500000


# ------------------------------------------------------------------ L2: mark reviewed resolves the queue item
def test_mark_reviewed_moves_item_to_resolved(fresh_db):
    q = repo.review_queue(tab="review")
    before = q["counts"]["review"]
    item = q["items"][0]
    admin.accept(item["invoice_id"], user="Priya Nair", role="manager")
    after = repo.review_queue(tab="review")
    assert after["counts"]["review"] == before - 1
    assert item["invoice_id"] in {i["invoice_id"] for i in repo.review_queue(tab="resolved")["items"]}
    assert repo.metrics(30)["tiles"]["open_exceptions"]["value_all_time"] == after["open_exceptions"]


# ------------------------------------------------------------------ L5: AI cache survives a demo reset
def test_demo_reset_keeps_extraction_cache(fresh_db):
    with db.tx() as con:
        con.execute("INSERT OR REPLACE INTO extraction_cache (cache_key, file_sha256, prompt_version, model, result, "
                    "created_at) VALUES ('k1', 'sha', 'v', 'm', '{}', '2026-11-16T00:00:00Z')")
    db.reset_schema()
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) AS n FROM extraction_cache WHERE cache_key='k1'").fetchone()["n"] == 1


# ------------------------------------------------------------------ H1: pending invoices use up the PO
def test_h1_second_invoice_cannot_use_quantity_claimed_by_a_pending_one(fresh_db):
    first = run("A06_a_pending.pdf")              # all 30 docks + keyboard sets at +3% -> review (pending)
    assert first["outcome"] == "route_for_review"
    second = run("A06_b_second.pdf")              # 30 docks again: fits only if the pending invoice is ignored
    assert second["outcome"] == "route_for_review", second["headline"]
    r11 = second["rules"]["R11"]
    assert r11["severity"] == "review" and "CV-9140" in r11["message_plain"]


# ------------------------------------------------------------------ H2: re-billed goods are not "recurring"
def test_h2_same_goods_rebilled_a_month_later_is_a_possible_duplicate(fresh_db):
    assert run("A15_original.pdf")["outcome"] in ("auto_approve", "approve_with_note")
    d = run("A15_rebill.pdf")
    assert d["outcome"] == "route_for_review" and "R06" in d["driving"], (d["outcome"], d["driving"])


def test_h2_recurring_service_bills_keep_the_guard():
    from datetime import date
    w = {"amount": 0.30, "number": 0.25, "date": 0.15, "po": 0.10, "lines": 0.20}
    lines = [{"description": "Office rent for the month", "desc_norm": "office rent month", "qty": 1,
              "pretax_amount_paise": 15000000, "amount_paise": 15000000}]
    goods = [{"description": "Toner cartridge black", "desc_norm": "toner cartridge black", "qty": 10,
              "pretax_amount_paise": 3450000, "amount_paise": 3450000}]
    for ls, guarded in ((lines, True), (goods, False)):
        cur = {"invoice_no": "BLS/26-27/0655", "invoice_date": date(2026, 11, 14), "total_paise": 100, "lines": ls}
        prior = {"invoice_no": "BLS/26-27/0590", "invoice_date": date(2026, 10, 10), "total_paise": 100, "lines": ls}
        assert matching.duplicate_score(cur, prior, w)["recurring_guard"] is guarded


# ------------------------------------------------------------------ H3: line table continues on page 2
def test_h3_two_page_invoice_reads_all_lines_and_approves(fresh_db):
    d = run("B02_two_pages.pdf")
    assert d["outcome"] == "auto_approve", (d["outcome"], d["headline"])
    with db.conn() as con:
        n = con.execute("SELECT COUNT(*) AS n FROM line_items li JOIN decisions d ON d.invoice_id = li.invoice_id "
                        "WHERE d.id = ?", (d["id"],)).fetchone()["n"]
    assert n == 2
