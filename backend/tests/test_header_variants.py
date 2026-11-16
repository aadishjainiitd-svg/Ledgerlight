"""The no-API-key text-layer extractor must read line tables whatever (reasonable) wording the column
headings use, and must still fail safely to Review when a table truly cannot be read."""
import json

import pytest

from app import db, extract_text, pipeline, services
from app.extract_text import header_kind
from tests import invoice_factory as inv


def run_pdf(data: bytes) -> dict:
    """Upload PDF bytes through the real nine-stage pipeline (no sample id, no file-name hints)."""
    iid, rid = services.new_run(file_name="upload.pdf", data=data, source="upload", sample_id=None, pace=0,
                                use_cache=True, triggered_by="pytest")
    res = pipeline.run_sync(rid, publish=False)
    with db.conn() as con:
        d = dict(con.execute("SELECT * FROM decisions WHERE run_id=? AND made_by='system'", (rid,)).fetchone())
        rules = {r["rule_id"]: dict(r) for r in con.execute("SELECT * FROM rule_results WHERE run_id=?", (rid,))}
    return {"run": res, "decision": d, "rules": rules, "driving": json.loads(d["driving_rule_ids"])}


def lines_of(data: bytes) -> list[tuple]:
    ex = extract_text.extract(data)
    return [(it["description"], it["qty"], it["unit_price"], it["amount"], it["tax_rate_pct"]) for it in ex["line_items"]]


# (factory, expected extracted lines, expected outcome, expected driving rules)
CASES = {
    "taxable-amt": (
        inv.greenleaf_taxable_amt,
        [("Paper cup 150 ml (PNT-CUP)", 10000.0, "1.65", "16,500.00", 12.0),
         ("Wooden stirrer (PNT-STR)", 5000.0, "0.40", "2,000.00", 12.0)],
        # lines are read; the cup price (1.65) is genuinely above the PO price (1.60), so R10 sends it to Review
        "route_for_review", ["R10"]),
    "hsn-sac-unit-price-line-total": (
        inv.brightline_line_total,
        [("Black toner cartridge (TNR-BK)", 30.0, "3,450.00", "1,03,500.00", 18.0)],
        "auto_approve", []),
    "two-line-headings-igst-columns": (
        inv.corevolt_igst_two_line_headings,
        [("24-port managed switch (NS-24P)", 6.0, "21,000.00", "1,26,000.00", 18.0),
         ("Cat6 patch cable 2 m (PC-CAT6)", 60.0, "250.00", "15,000.00", 18.0)],
        "auto_approve", []),
    "units-price-gst-pct-net-amt": (
        inv.brightline_gst_pct_units,
        [("Ergonomic mesh chair (CH-ERG-01)", 10.0, "6,500.00", "65,000.00", 18.0),
         ("Height-adjustable standing desk (DK-STD-02)", 5.0, "12,000.00", "60,000.00", 18.0)],
        "auto_approve", []),
}


@pytest.mark.parametrize("name", list(CASES))
def test_line_items_read_for_header_variant(name):
    factory, expected, _, _ = CASES[name]
    assert lines_of(factory()) == expected


@pytest.mark.parametrize("name", list(CASES))
def test_header_variant_reaches_expected_rule_outcome(name, fresh_db):
    factory, _, outcome, driving = CASES[name]
    out = run_pdf(factory())
    assert out["run"]["status"] == "completed", out["run"]
    assert out["rules"]["R09"]["severity"] == "pass", out["rules"]["R09"]["message_plain"]
    assert out["decision"]["outcome"] == outcome, (out["decision"]["outcome"], out["decision"]["headline"])
    assert out["driving"] == driving


def test_unreadable_table_fails_safely_to_review(fresh_db):
    data = inv.unreadable_headings()
    ex = extract_text.extract(data)
    assert ex["line_items"] == []
    assert "line-item table could not be read" in ex["document_notes"]
    out = run_pdf(data)
    assert out["run"]["status"] == "completed"
    assert out["decision"]["outcome"] == "route_for_review"
    assert out["driving"][0] == "R09"
    assert out["rules"]["R09"]["severity"] == "review"
    assert "No line items could be read" in out["rules"]["R09"]["message_plain"]
    assert out["decision"]["headline"] == "Review needed: we could not read the line items."


HEADERS = {
    "amount": ["Amount", "Amt", "Taxable Amt", "Taxable Amt.", "Taxable Value", "Taxable Amount", "Line Total", "Net Amt",
               "Net Amount", "Value", "Total", "Amount (Rs.)", "Amount (excl. GST)", "Total Amount", "Net Value"],
    "qty": ["Qty", "Qty.", "Quantity", "QTY", "Nos", "Pcs", "Trips", "Hours"],
    "rate": ["Rate", "Unit Price", "Price", "Rate (Rs.)", "Unit Rate", "Rate/Unit", "Price (excl. GST)"],
    "hsn": ["HSN", "SAC", "HSN/SAC", "HSN / SAC Code", "HSN Code"],
    "desc": ["Description", "Description of Goods", "Item Description", "Particulars", "Product", "Product Name",
             "Item Name", "Details", "Goods and Services"],
    "taxrate": ["GST %", "GST%", "Tax Rate", "Tax %", "GST Rate", "IGST %", "IGST Rate"],
    "taxpart": ["CGST", "SGST", "IGST", "CGST %", "SGST Amt", "CGST Rate", "IGST Amt", "GST Amt", "Tax Amount"],
    "sno": ["#", "S.No.", "Sl. No.", "Sr", "Sr. No.", "Sl"],
    "uom": ["UoM", "Unit", "Per"],
    "code": ["Item Code", "SKU", "Part No"],
    "other": ["Discount", "Disc %"],
}


@pytest.mark.parametrize("kind,text", [(k, t) for k, ts in HEADERS.items() for t in ts])
def test_header_synonyms(kind, text):
    assert header_kind(text)[0] == kind


def test_gross_total_column_never_beats_taxable_column():
    from app.extract_text import Cell, classify_header

    def cell(x, t):
        return Cell([(x, 0, x + 40, 10, t)])
    heads = [("Description", 40), ("Qty", 200), ("Rate", 250), ("Taxable Value", 300), ("Total (incl. GST)", 400)]
    cols = classify_header([cell(x, t) for t, x in heads])
    kinds = {c.text: k for k, c in cols}
    assert kinds["Taxable Value"] == "amount" and kinds["Total (incl. GST)"] == "taxpart"


def test_headings_with_no_meaning_are_not_guessed():
    from app.extract_text import Cell, classify_header
    cells = [Cell([(x, 0, x + 30, 10, t)]) for t, x in [("Col A", 40), ("Col B", 200), ("Col C", 300), ("Col D", 400)]]
    assert classify_header(cells) is None
