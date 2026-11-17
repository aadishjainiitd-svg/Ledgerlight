"""Stage 3: turn raw extraction into a canonical invoice with effective confidence per field (spec 2.3).

effective = 0.50 * model_confidence + 0.30 * evidence + 0.20 * format_valid
  evidence: 1.0 found verbatim in the text layer (or, for an image-only scan, both independent reads agree);
            0.5 found with minor differences; 0.0 not found.
Refinements: reconciliation boost (numbers add up), ambiguous-date cap, self-consistency cap."""
from __future__ import annotations

import re
from datetime import date

from .textutil import (GSTIN_RE, IFSC_RE, canonical_invoice_no, digits_only, fmt_date, invoice_prefix,
                       norm_desc, norm_uom, parse_date, parse_money, parse_number, serial_token)

FIELD_LABELS = {
    "vendor_name": "Vendor", "vendor_gstin": "Vendor GSTIN", "invoice_no": "Invoice no.", "invoice_date": "Invoice date",
    "po_reference": "PO reference", "currency": "Currency", "subtotal": "Subtotal", "tax_total": "Tax (GST)",
    "total": "Total", "bank_name": "Bank name", "bank_account": "Bank account", "bank_ifsc": "IFSC",
}
MONEY_FIELDS = {"subtotal", "tax_total", "total"}


def _squash(s: str) -> str:
    return re.sub(r"[\s,]", "", str(s or "")).upper()


def _evidence(raw, text_layer_sq: str, digits_layer: str) -> float:
    if raw is None or raw == "":
        return 0.0
    if "+" in str(raw):  # a value read as several printed parts (e.g. CGST + SGST): every part must be present
        return min(_evidence(p, text_layer_sq, digits_layer) for p in str(raw).split("+"))
    sq = _squash(raw).replace("₹", "").replace("RS.", "").replace("INR", "")
    if sq and sq in text_layer_sq:
        return 1.0
    d = digits_only(raw)
    if len(d) >= 3 and d in digits_layer:
        return 0.5
    return 0.0


def _format_valid(name: str, value, parsed) -> float:
    if value is None:
        return 0.0
    if name in MONEY_FIELDS:
        return 1.0 if isinstance(parsed, int) else 0.0
    if name == "invoice_date":
        return 1.0 if isinstance(parsed, date) else 0.0
    if name == "vendor_gstin":
        return 1.0 if GSTIN_RE.fullmatch(str(value).replace(" ", "").upper()) else 0.0
    if name == "bank_ifsc":
        return 1.0 if IFSC_RE.fullmatch(str(value).replace(" ", "").upper()) else 0.0
    if name == "bank_account":
        return 1.0 if 8 <= len(digits_only(value)) <= 20 else 0.0
    if name == "po_reference":
        return 1.0 if re.search(r"\d{3,}", str(value)) else 0.0
    if name == "invoice_no":
        return 1.0 if re.search(r"\d", str(value)) and len(str(value)) <= 30 else 0.0
    if name == "currency":
        return 1.0 if str(value).upper() in ("INR", "USD", "EUR", "GBP") else 0.0
    return 1.0 if str(value).strip() else 0.0


def normalise(extraction: dict, *, text_layer: str, scanned_no_text: bool, cfg: dict, as_of: date,
              corrections: dict | None = None) -> dict:
    adv = cfg["advanced"]
    corrections = corrections or {}
    tl_sq = _squash(text_layer)
    tl_digits = digits_only(text_layer)
    agree = extraction.get("self_consistency") or {}
    day_first = cfg["global"].get("dateOrder", "Day first") == "Day first"
    fields: dict[str, dict] = {}
    notes: list[str] = []

    for name, f in extraction["fields"].items():
        raw_val = f.get("value")
        mc = float(f.get("confidence") or 0.0)
        src = "image read" if scanned_no_text else (
            "OCR text layer" if extraction.get("text_source") == "ocr_layer" else "text layer")
        if name in corrections:
            raw_val = corrections[name]["value"]
        parsed = None
        extra: dict = {}
        if name in MONEY_FIELDS:
            parsed = parse_money(raw_val)
        elif name == "invoice_date":
            pd = parse_date(raw_val, as_of=as_of, day_first=day_first)
            parsed = pd["value"]
            if pd["ambiguous"]:
                extra = {"ambiguous": True, "alternative": pd["alternative"].isoformat() if pd["alternative"] else None,
                         "note": pd["note"]}
        if scanned_no_text:
            ev = (1.0 if agree.get(name) else 0.0) if agree else 0.0
        elif name == "currency":
            sym = str(f.get("raw_text") or raw_val or "")
            ev = 1.0 if sym and (sym in text_layer or sym.upper() in text_layer.upper()) else 0.0
        else:
            ev = _evidence(f.get("raw_text") or raw_val, tl_sq, tl_digits)
        fv = _format_valid(name, raw_val, parsed)
        eff = 0.5 * mc + 0.3 * ev + 0.2 * fv
        why = []
        if raw_val is None:
            eff = 0.0
        if extra.get("ambiguous") and eff > adv["ambiguous_date_cap"]:
            eff = adv["ambiguous_date_cap"]
            why.append(extra["note"])
        if agree and agree.get(name) is False and raw_val is not None:
            eff = min(eff, adv["disagree_cap"])
            why.append("The two independent reads of the scan disagree on this value.")
        rec = {
            "name": name, "label": FIELD_LABELS.get(name, name), "value": raw_val, "parsed": parsed,
            "raw_text": f.get("raw_text"), "model_confidence": round(mc, 3), "evidence": ev, "format_valid": fv,
            "effective_confidence": round(eff, 3), "boosted": False, "source": src if raw_val is not None else "not found",
            "why": " ".join(why) or None, **extra,
        }
        if name in corrections:
            rec.update({"source": "corrected by user", "effective_confidence": 1.0, "model_confidence": 1.0,
                        "corrected_by": corrections[name].get("by"), "original_value": f.get("value"),
                        "why": f"Corrected by {corrections[name].get('by')}: {corrections[name].get('reason') or 'no reason given'}"})
        fields[name] = rec

    # ---- tax rate and inclusive handling
    tax_inclusive = bool(extraction.get("tax_inclusive"))
    doc_rate = extraction.get("tax_rate_pct")
    lines = []
    for i, it in enumerate(extraction.get("line_items") or [], 1):
        qty = parse_number(it.get("qty"))
        unit = parse_money(it.get("unit_price"))
        amount = parse_money(it.get("amount"))
        rate = it.get("tax_rate_pct")
        rate = float(rate) if isinstance(rate, (int, float)) else (float(doc_rate) if doc_rate is not None else None)
        calc = None
        if amount is None and qty is not None and unit is not None:
            amount, calc = int(round(qty * unit)), "amount"
        if unit is None and amount is not None and qty:
            unit, calc = int(round(amount / qty)), "unit_price"
        if not qty and unit and amount is not None:
            # No quantity printed: derive it from amount / rate so the price and quantity checks still run.
            # R10 and R11 send a line whose quantity cannot be worked out to review; they never pass it.
            qty, calc = round(amount / unit, 3), "qty"
        uom = it.get("uom")
        if not uom and it.get("qty"):
            m = re.search(r"[A-Za-z]+\.?$", str(it.get("qty")).strip())
            uom = m.group(0) if m else None
        pretax_amount = amount
        pretax_unit = unit
        if tax_inclusive and rate is not None and amount is not None:
            pretax_amount = int(round(amount / (1 + rate / 100.0)))
            pretax_unit = int(round(pretax_amount / qty)) if qty else None
        lc = float(it.get("confidence") or 0.0)
        ev = 1.0 if scanned_no_text and agree.get("line_items") else (
            0.0 if scanned_no_text else _evidence(it.get("amount"), tl_sq, tl_digits))
        eff = 0.5 * lc + 0.3 * ev + 0.2 * (1.0 if amount is not None else 0.0)
        if scanned_no_text and agree and agree.get("line_items") is False:
            eff = min(eff, adv["disagree_cap"])
        code = it.get("item_code")
        lines.append({
            "line_no": i, "description": (it.get("description") or "").strip(), "desc_norm": norm_desc(it.get("description")),
            "item_code": code.strip() if isinstance(code, str) and code.strip() else None,
            "qty": qty, "uom": norm_uom(uom) or uom, "uom_raw": uom, "unit_price_paise": unit, "amount_paise": amount,
            "pretax_amount_paise": pretax_amount, "pretax_unit_paise": pretax_unit, "tax_rate_pct": rate,
            "confidence": round(eff, 3), "model_confidence": lc, "calculated": calc,
        })

    total = fields["total"]["parsed"]
    printed_sub = fields["subtotal"]["parsed"]
    tax_printed = fields["tax_total"]["parsed"]
    line_sum = sum(l["pretax_amount_paise"] or 0 for l in lines) if lines else None
    subtotal, tax = printed_sub, tax_printed
    if tax_inclusive and doc_rate is not None and total is not None:
        base = int(round(total / (1 + float(doc_rate) / 100.0)))
        subtotal = base
        fields["subtotal"].update({"parsed": base, "value": f"{base / 100:.2f}", "source": "calculated",
                                   "effective_confidence": fields["total"]["effective_confidence"],
                                   "why": f"Prices were tax-inclusive. Backed out GST: {total / 100:,.2f} / "
                                          f"{1 + float(doc_rate) / 100:.2f} = {base / 100:,.2f}."})
        if tax is None:
            tax = total - base
            fields["tax_total"].update({"parsed": tax, "value": f"{tax / 100:.2f}", "source": "calculated",
                                        "effective_confidence": fields["total"]["effective_confidence"]})
        notes.append("Prices are tax-inclusive; the pre-tax base was calculated.")
    if subtotal is None and line_sum:
        subtotal = line_sum
        fields["subtotal"].update({"parsed": line_sum, "value": f"{line_sum / 100:.2f}", "source": "calculated",
                                   "effective_confidence": min([l["confidence"] for l in lines] or [0]),
                                   "why": "Not printed; calculated as the sum of the lines."})
    if tax is None and subtotal is not None and total is not None and not tax_inclusive:
        tax = total - subtotal
        fields["tax_total"].update({"parsed": tax, "value": f"{tax / 100:.2f}", "source": "calculated",
                                    "effective_confidence": fields["total"]["effective_confidence"],
                                    "why": "Not printed; calculated as total minus subtotal."})

    # ---- reconciliation boost
    reconciled = False
    if total is not None and subtotal is not None and tax is not None:
        lines_ok = (line_sum is None) or abs(line_sum - subtotal) <= 100
        if abs(subtotal + tax - total) <= 100 and lines_ok and (lines or printed_sub is not None):
            reconciled = True
            for k in ("subtotal", "tax_total", "total"):
                r = fields[k]
                if r["effective_confidence"] < adv["boost_to"] and r["source"] != "corrected by user":
                    before = r["effective_confidence"]
                    r["effective_confidence"] = adv["boost_to"]
                    r["boosted"] = True
                    r["boosted_from"] = before
                    r["why"] = (f"Read at {before:.2f}, raised to {adv['boost_to']:.2f} because the lines plus tax "
                                f"equal the total.")
            for l in lines:
                if l["confidence"] < adv["boost_to"]:
                    l["boosted_from"] = l["confidence"]
                    l["confidence"] = adv["boost_to"]

    # ---- canonical values
    inv_raw = fields["invoice_no"]["value"]
    d = fields["invoice_date"]["parsed"]
    year = d.year if d else as_of.year
    gst = fields["vendor_gstin"]["value"]
    gst = str(gst).replace(" ", "").upper() if gst else None
    currency = fields["currency"]["value"]
    canon = {
        "fields": fields,
        "lines": lines,
        "vendor_name": fields["vendor_name"]["value"],
        "vendor_gstin": gst,
        "invoice_no": inv_raw,
        "invoice_no_canonical": canonical_invoice_no(inv_raw),
        "invoice_prefix": invoice_prefix(inv_raw),
        "serial_token": serial_token(inv_raw, year),
        "invoice_date": d,
        "date_ambiguous": bool(fields["invoice_date"].get("ambiguous")),
        "po_reference": fields["po_reference"]["value"],
        "po_reference_candidates": extraction.get("po_reference_candidates") or [],
        "currency": str(currency).upper() if currency else None,
        "subtotal_paise": subtotal,
        "tax_paise": tax,
        "tax_printed_paise": tax_printed if tax_printed is not None else tax,
        "total_paise": total,
        "line_sum_paise": line_sum,
        "tax_inclusive": tax_inclusive,
        "tax_rate_pct": float(doc_rate) if doc_rate is not None else None,
        "tax_lines": extraction.get("tax_lines") or [],
        "other_charges_paise": parse_money(extraction.get("other_charges")) or 0,
        "discount_paise": parse_money(extraction.get("discount")) or 0,
        "other_charge_labels": list(extraction.get("other_charge_labels") or []),
        "bank": {"name": fields["bank_name"]["value"], "account": fields["bank_account"]["value"],
                 "ifsc": (str(fields["bank_ifsc"]["value"]).upper() if fields["bank_ifsc"]["value"] else None)},
        "bank_entries": list(extraction.get("bank_entries") or []),
        "bank_change_notice": bool(extraction.get("bank_change_notice")),
        "bank_change_text": extraction.get("bank_change_text"),
        "reconciled": reconciled,
        "notes": notes,
        "contains_instructions": bool(extraction.get("contains_instructions")),
    }
    return canon


def critical_confidences(canon: dict) -> list[tuple[str, float]]:
    f = canon["fields"]
    out = []
    vendor_key = "vendor_gstin" if f["vendor_gstin"]["value"] else "vendor_name"
    for k in (vendor_key, "invoice_no", "invoice_date", "total", "currency"):
        if f[k]["value"] is not None:
            out.append((f[k]["label"], f[k]["effective_confidence"]))
    if f["po_reference"]["value"] is not None:
        out.append((f["po_reference"]["label"], f["po_reference"]["effective_confidence"]))
    for l in canon["lines"]:
        out.append((f"Line {l['line_no']} amount", l["confidence"]))
    return out


def describe_date(canon: dict) -> str:
    return fmt_date(canon["invoice_date"]) if canon.get("invoice_date") else "n/a"
