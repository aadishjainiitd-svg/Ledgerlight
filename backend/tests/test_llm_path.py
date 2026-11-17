"""The Claude extraction path, exercised without a network call.

The real extractor (app.extract_llm) is used end to end: request building, two-pass self-consistency for scans,
schema validation, caching, effective confidence, implied PO and the explanation polish fact-check. Only the
HTTP call (_call) is replaced by a test double that returns what a vision model would read from the SI-05 scan,
so the EC3 decision logic is verified even when ANTHROPIC_API_KEY is not set. Product code never looks at
file names."""
import json

from app import explain, extract_llm
from tests.conftest import run_sample


def F(value, conf, raw=None):
    return {"value": value, "raw_text": raw if raw is not None else value, "confidence": conf}


GREENLEAF_READ = {
    "vendor_name": F("Greenleaf Pantry Supplies", 0.95), "vendor_gstin": F("27AAJFG9054R1Z2", 0.93),
    "invoice_no": F("GL-2291", 0.90), "invoice_date": F("12/11/26", 0.90), "po_reference": F(None, 0.0),
    "currency": F("INR", 0.90, "Rs."), "subtotal": F("75,000", 0.83), "tax_total": F("3,750", 0.81, "1,875 + 1,875"),
    "total": F("78,750", 0.78, "78,7?0"), "bank_name": F(None, 0.0), "bank_account": F(None, 0.0), "bank_ifsc": F(None, 0.0),
    "line_items": [
        {"description": "Tea premix (masala)", "item_code": None, "qty": "150 kg", "uom": "kg", "unit_price": "420",
         "amount": "63,000", "tax_rate_pct": None, "confidence": 0.9},
        {"description": "Sugar", "item_code": None, "qty": "250 kg", "uom": "kg", "unit_price": "48", "amount": "12,000",
         "tax_rate_pct": None, "confidence": 0.9}],
    "tax_lines": [{"label": "CGST", "rate_pct": 2.5, "amount": "1,875"}, {"label": "SGST", "rate_pct": 2.5, "amount": "1,875"}],
    "tax_inclusive": False, "bank_change_notice": False, "bank_change_text": None, "po_reference_candidates": [],
    "document_notes": "RECEIVED stamp covers the P.O. No. field; total is smudged.", "contains_instructions": False,
}


def test_ec3_scan_with_simulated_vision_model(fresh_db, monkeypatch):
    calls = []

    def fake_call(content, system, schema, max_tokens=16000):
        calls.append([c["type"] for c in content])
        if schema is extract_llm.POLISH_SCHEMA:
            return json.loads(content[0]["text"].split("\n", 1)[1]) and content[0]["text"].split("\n", 1)[1]
        return json.dumps(GREENLEAF_READ)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(extract_llm, "_call", fake_call)
    out = run_sample("SI-05")
    d = out["decision"]
    assert d["outcome"] == "approve_with_note", d["headline"]
    # The note comes from the inferred PO. "12/11/26" read day first is 12 Nov, a valid past date, so the date is
    # not treated as ambiguous any more.
    assert json.loads(d["driving_rule_ids"]) == ["R07"]
    # two passes for a scan: PDF document block, then a rendered page image in a different reading order
    assert calls[0][0] == "document" and calls[1][0] == "image"
    r07 = json.loads(out["rules"]["R07"]["facts"])
    assert r07["method"] == "implied" and r07["po_id"] == "PO-2026-1005" and r07["score"] >= 0.9 and r07["gap"] >= 0.2
    r02 = json.loads(out["rules"]["R02"]["facts"])
    assert r02["lowest_field"] != "Invoice date"
    assert any(b["field"] == "Total" and b["to"] == 0.92 for b in r02["boosted"])
    expl = json.loads(d["explanation"])
    assert expl["headline"].startswith("Approved with a note: we matched this invoice to a purchase order")
    # The smudged total is confirmed by the arithmetic; R02 says so (it no longer drives the decision).
    assert "raised to 0.92 because lines plus tax equal the total" in out["rules"]["R02"]["message_plain"]


def test_polish_fact_check_rejects_new_numbers():
    base = {"headline": "Reject: GST is off by ₹10,000.", "attention": ["GST should be ₹31,320."], "next_step": "Ask Meridian."}
    ok = {"headline": "Reject: the GST is ₹10,000 too low.", "attention": ["The GST ought to be ₹31,320."],
          "next_step": "Please ask Meridian."}
    bad = dict(ok, attention=["The GST ought to be ₹31,230."])
    assert explain.fact_check(base, ok) and not explain.fact_check(base, bad)


def test_groq_request_translation_offline(monkeypatch):
    """Groq path without network: a PDF document block becomes page images, the compact schema goes in the
    system prompt with JSON mode, and the key is sent only as a bearer header."""
    import base64
    from app import config, pdfio

    sent = {}

    class Resp:
        status_code = 200
        headers = {}
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"finish_reason": "stop", "message": {"content": "<think>x</think>{\"ok\": true}"}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return Resp()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-not-a-real-key")
    assert config.llm_provider() == "groq" and config.llm_model() == "qwen/qwen3.8-27b"

    data = (config.SAMPLES_DIR / "SI-01_bluepeak_BPS-2026-0417.pdf").read_bytes() \
        if (config.SAMPLES_DIR / "SI-01_bluepeak_BPS-2026-0417.pdf").exists() else \
        next(config.SAMPLES_DIR.glob("SI-01*.pdf")).read_bytes()
    doc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                          "data": base64.standard_b64encode(data).decode()}}
    out = extract_llm._call([doc, {"type": "text", "text": "read it"}], "sys", extract_llm.SCHEMA)
    assert out == '{"ok": true}'                                  # reasoning block stripped
    parts = sent["body"]["messages"][1]["content"]
    assert parts[0]["type"] == "image_url" and parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert parts[-1] == {"type": "text", "text": "read it"}
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert "additionalProperties" not in sent["body"]["messages"][0]["content"]
    assert sent["headers"]["Authorization"] == "Bearer test-not-a-real-key"
    assert sent["url"].startswith("https://api.groq.com/")
    assert len(pdfio.render_png(data, 0, dpi=72)) > 0


def test_currency_forms_are_canonicalised_before_agreement():
    for printed in ("Rs.", "Rs", "₹", "Rupees", "TOTAL Rs.", "INR"):
        d = extract_llm._canon_currency({"currency": {"value": printed, "raw_text": printed, "confidence": 0.9}})
        assert d["currency"]["value"] == "INR" and d["currency"]["raw_text"] == printed
    d = extract_llm._canon_currency({"currency": {"value": "XYZ", "raw_text": "XYZ", "confidence": 0.9}})
    assert d["currency"]["value"] == "XYZ"
