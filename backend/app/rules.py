"""The 16 deterministic rules (spec 3.4) and the decision engine (spec 3.1). No LLM is involved here.

Every rule returns a RuleResult dict: severity, plain-English message with numbers, facts (the only
numbers the explanation may use), the threshold used, and the exposure in paise."""
from __future__ import annotations

import re
from datetime import date

from .catalogue import RULE_BY_ID, SEV_RANK, SEV_TO_OUTCOME, allowed_text
from .normalize import critical_confidences
from .textutil import fmt_date, fmt_qty, inr, inr0, mask_account, to_date


def rr(rule_id: str, severity: str, message: str, *, facts: dict | None = None, threshold: dict | None = None,
       exposure: int = 0, skipped: bool = False, ok: str | None = None, headline: str | None = None,
       next_step: str | None = None, alternative: str | None = None, attention: str | None = None) -> dict:
    meta = RULE_BY_ID[rule_id]
    return {"rule_id": rule_id, "rule_name": meta["name"], "stage_no": meta["stage"], "severity": severity,
            "skipped": skipped, "message": message, "facts": facts or {}, "threshold_used": threshold or {},
            "exposure_paise": int(exposure or 0), "ok": ok, "headline": headline, "next_step": next_step,
            "alternative": alternative, "attention": attention or message}


def skip(rule_id: str, why: str) -> dict:
    return rr(rule_id, "pass", f"Not checked: {why}", skipped=True)


def pct_str(p: float) -> str:
    a = abs(p)
    s = f"{a:.1f}" if abs(a * 10 - round(a * 10)) < 1e-6 else f"{a:.2f}"
    return s + "%"


def band(delta_paise: int, delta_pct: float, p: dict) -> tuple[str, str]:
    """Variance bands (spec 3.3). delta > 0 is overbilling. An absolute cap of 0 means 'not used'."""
    a, ap = abs(delta_paise) / 100.0, abs(delta_pct)
    pass_abs, note_abs = p.get("pass_abs", 0) or 0, p.get("note_abs", 0) or 0
    if ap <= p["pass_pct"] or (pass_abs and a <= pass_abs):
        return "pass", "exact enough"
    if delta_paise < 0:  # undercharge: capped at NOTE until -review_pct
        return ("note", "undercharge") if ap <= p["review_pct"] else ("review", "large undercharge")
    if ap <= p["note_pct"] and (not note_abs or a <= note_abs):
        return "note", "within allowed difference"
    if ap <= p["review_pct"]:
        return "review", "needs a human"
    return "reject", "different transaction"


def _plural(w: str, n: float | None = 2) -> str:
    if n is not None and abs(n - 1) < 1e-9:
        return w
    if re.search(r"(s|x|ch|sh)$", w):
        return w + "es"
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    return w + "s"


def unit_noun(desc: str | None, uom: str | None, n: float | None = 2) -> str:
    u = (uom or "").lower()
    if u in ("kg", "l"):
        return u
    if u in ("trips", "reams", "boxes", "sets"):
        return _plural(u.rstrip("s") if u != "boxes" else "box", n)
    if u == "lot":
        return _plural("lot", n)
    head = re.split(r"[,(]", desc or "")[0]
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]*", head) if len(w) >= 3 and not re.search(r"\d", w)]
    if not words:
        return "units" if n != 1 else "unit"
    return _plural(words[-1].lower(), n)


# ------------------------------------------------------------------ stage 3

def r01(ctx) -> dict:
    status = ctx["extraction_status"]
    if status == "unavailable":
        msg = ("We could not read this file: scanned invoice needs AI extraction; set ANTHROPIC_API_KEY or GROQ_API_KEY. "
               "It is an image with no text layer, so the AI vision model is needed to read it.")
        return rr("R01", "hold", msg, facts={"reason": "scanned_no_key"},
                  headline="scanned invoice needs AI extraction; set ANTHROPIC_API_KEY or GROQ_API_KEY.",
                  next_step="Set ANTHROPIC_API_KEY or GROQ_API_KEY on the server and re-run this invoice, or ask the vendor for a "
                            "text PDF of the same invoice.")
    if status == "wrong_doc_type":
        from .extract_text import DOC_KIND_LABEL  # noqa: PLC0415
        kind = ctx.get("doc_kind")
        label = DOC_KIND_LABEL.get(kind, "document")
        ref = ctx.get("doc_ref")
        why, step = {
            "credit_note": ("A credit note reduces what we owe the vendor. Paying it would pay them money they owe us",
                            f"Record it in the ledger as a credit{' against invoice ' + ref if ref else ''}. Do not pay it."),
            "debit_note": ("A debit note asks us to pay more on an earlier invoice, so it needs a person to check it",
                           "Check the debit note against the original invoice and the PO before anything is paid."),
            "proforma": ("A proforma invoice is a request for an advance, not a tax invoice, and cannot be paid as one",
                         "Pay advances only through an approved advance request, then wait for the tax invoice."),
            "quotation": ("A quotation is an offer, not a bill", "Send it to Procurement. Nothing to pay."),
            "statement": ("A statement of account lists invoices; each one is paid on its own",
                          "Reconcile the statement against our ledger. Nothing to pay from it directly."),
            "delivery_challan": ("A delivery challan records goods sent; it is not a bill",
                                 "Match it with the goods received note. Wait for the tax invoice."),
            "purchase_order": ("This is a purchase order, not an invoice", "Nothing to pay. Check why it was sent to AP."),
        }.get(kind, ("This document is not a tax invoice", "Check the file."))
        return rr("R01", "hold", f"This is a {label}, not a tax invoice. {why}.",
                  facts={"reason": "wrong_doc_type", "doc_kind": kind, "doc_label": label, "reference": ref},
                  headline=f"this is a {label}, not a tax invoice, so it was not processed for payment.",
                  next_step=step)
    if status == "not_invoice":
        return rr("R01", "hold", "This file does not look like an invoice: no invoice number, date or total was found.",
                  facts={"reason": "not_invoice"}, headline="this file does not look like an invoice.",
                  next_step="Check the file. If it is an invoice, ask the sender for a readable copy.")
    if status == "failed":
        return rr("R01", "hold", "The invoice could not be read.", facts={"reason": "extraction_failed"},
                  headline="we could not read this invoice.", next_step="Retry the run, or ask for a clearer copy.")
    c = ctx["canon"]
    f = c["fields"]
    missing = []
    if not f["invoice_no"]["value"]:
        missing.append("invoice number")
    if not c.get("invoice_date"):
        missing.append("invoice date")
    if not (f["vendor_name"]["value"] or f["vendor_gstin"]["value"]):
        missing.append("vendor")
    if c.get("total_paise") is None:
        missing.append("total")
    if not c.get("currency"):
        missing.append("currency")
    if missing:
        lst = ", ".join(missing)
        return rr("R01", "hold", f"The invoice is missing: {lst}.", facts={"missing": missing},
                  headline=f"the invoice is missing the {lst}.",
                  next_step=f"Ask the vendor for a copy that shows the {lst}. The invoice re-runs when it arrives.")
    return rr("R01", "pass", "Invoice number, date, vendor, total and currency are all present.",
              ok="All required fields are present")


def r02(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R02", "nothing was extracted")
    p = ctx["cfg"]["rules"]["R02"]
    crit = critical_confidences(ctx["canon"])
    if not crit:
        return skip("R02", "no fields to score")
    low_label, low = min(crit, key=lambda t: t[1])
    f = ctx["canon"]["fields"]
    boosted = [r for r in f.values() if r.get("boosted")]
    boost_txt = " ".join(f"The {r['label'].lower()} was read at {r['boosted_from']:.2f} and raised to "
                         f"{r['effective_confidence']:.2f} because lines plus tax equal the total." for r in boosted)
    facts = {"lowest_field": low_label, "lowest": round(low, 2),
             "below_ok": [{"field": k, "confidence": round(v, 2)} for k, v in crit if v < p["ok"]],
             "boosted": [{"field": r["label"], "from": r["boosted_from"], "to": r["effective_confidence"]} for r in boosted]}
    thr = {"ok": p["ok"], "min": p["min"]}
    why = ""
    for r in f.values():
        if r["label"] == low_label and r.get("ambiguous"):
            why = " (it could be read two ways)"
    if low >= p["ok"]:
        return rr("R02", "pass", f"All key fields were read with confidence of {p['ok']:.2f} or more (lowest "
                                 f"{low:.2f}).{(' ' + boost_txt) if boost_txt else ''}", facts=facts, threshold=thr,
                  ok="Every key field was read clearly")
    if low >= p["min"]:
        msg = f"Lowest confidence is the {low_label.lower()} at {low:.2f}{why}.{(' ' + boost_txt) if boost_txt else ''}"
        return rr("R02", "note", msg, facts=facts, threshold=thr,
                  headline=("the invoice date could be read two ways; we used the reading that is not in the future."
                            if why else "some fields were hard to read, but the numbers check out."),
                  next_step="None needed. You can correct any field if you disagree and the invoice will be re-checked.")
    return rr("R02", "hold", f"We could not read the {low_label.lower()} with confidence ({low:.2f}, needs "
                             f"{p['min']:.2f}).", facts=facts, threshold=thr, exposure=ctx["canon"].get("total_paise") or 0,
              headline=f"we could not read the {low_label.lower()} with confidence.",
              next_step="Check the value against the document and correct it, or ask the vendor for a clearer copy.")


def r03(ctx, po_issue: date | None = None) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R03", "nothing was extracted")
    c = ctx["canon"]
    d = c.get("invoice_date")
    if not d:
        return skip("R03", "no invoice date (see R01)")
    as_of = ctx["as_of"]
    days = ctx["cfg"]["rules"]["R03"]["days"]
    amb = c["fields"]["invoice_date"].get("note")
    facts = {"invoice_date": d.isoformat(), "as_of": as_of.isoformat(), "ambiguous": c.get("date_ambiguous"),
             "po_issue_date": po_issue.isoformat() if po_issue else None}
    extra = f" {amb}" if amb else ""
    if d > as_of:
        return rr("R03", "hold", f"The invoice date {fmt_date(d)} is in the future.{extra}", facts=facts,
                  exposure=c.get("total_paise") or 0, headline="the invoice date is in the future.",
                  next_step="Ask the vendor to confirm the invoice date.")
    if po_issue and d < po_issue:
        return rr("R03", "review", f"The invoice date {fmt_date(d)} is before the PO date {fmt_date(po_issue)}.{extra}",
                  facts=facts, headline="the invoice is dated before the purchase order.",
                  next_step="Check with Procurement that this invoice belongs to this PO.")
    if (as_of - d).days > days:
        return rr("R03", "note", f"The invoice is dated {fmt_date(d)}, more than {int(days)} days ago.{extra}",
                  facts=facts, threshold={"days": days}, headline="the invoice is more than 180 days old.")
    tail = " and after the PO date" if po_issue else ""
    msg = f"Invoice date {fmt_date(d)} is not in the future{tail}." + (f"{extra}" if amb else "")
    return rr("R03", "pass", msg, facts=facts, ok=f"Date read as {fmt_date(d)}" if amb else "Invoice date is valid")


# ------------------------------------------------------------------ stage 4

def r04(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R04", "nothing was extracted")
    c = ctx["canon"]
    vm = ctx["vendor_match"]
    total = c.get("total_paise") or 0
    if not (c["fields"]["vendor_name"]["value"] or c.get("vendor_gstin")):
        return skip("R04", "no vendor on the invoice (see R01)")
    v = vm.get("vendor")
    facts = {"method": vm["method"], "score": vm["score"], "vendor_id": v["id"] if v else None,
             "vendor_name": v["name"] if v else c["fields"]["vendor_name"]["value"],
             "gstin_on_invoice": c.get("vendor_gstin"), "status": v["status"] if v else None}
    if not v:
        return rr("R04", "reject", f"{c['fields']['vendor_name']['value'] or c.get('vendor_gstin')} is not in the vendor "
                                   f"master.", facts=facts, exposure=total,
                  headline="this vendor is not on our approved vendor list.",
                  next_step="Do not pay. Ask Procurement whether this vendor should be onboarded.")
    short = v.get("short") or v["name"]
    if v["status"] == "blocked":
        return rr("R04", "reject", f"{v['name']} is blocked in the vendor master.", facts=facts, exposure=total,
                  headline=f"{short} is a blocked vendor.", next_step="Do not pay. Send the return notice.")
    if v["status"] == "pending":
        return rr("R04", "hold", f"{v['name']} is still pending onboarding.", facts=facts, exposure=total,
                  headline=f"{short} has not finished vendor onboarding.",
                  next_step="Finish onboarding the vendor, then re-run this invoice.")
    if vm["method"] == "fuzzy" or vm.get("gstin_conflict"):
        why = "the GSTIN did not match" if vm.get("gstin_conflict") else "there is no GSTIN match"
        return rr("R04", "review", f"Looks like {v['name']} (name match {vm['score']:.2f}), but {why}. Please confirm.",
                  facts=facts, exposure=total, headline=f"the vendor looks like {short} but we could not confirm it.",
                  next_step="Confirm the vendor with Procurement, then accept or override.")
    if not c.get("vendor_gstin") and (c.get("tax_paise") or 0) > 0 and v.get("gstin"):
        return rr("R04", "review", f"The invoice charges GST but does not show {v['name']}'s GSTIN "
                                   f"({v['gstin']} on file). We matched the vendor by name only.", facts=facts,
                  exposure=total, headline=f"the invoice does not show {short}'s GSTIN, so the vendor and the GST "
                                           f"credit are unconfirmed.",
                  next_step=f"Ask {short} for a corrected tax invoice that shows its GSTIN, then re-run it.")
    mis = vm.get("gstin_misread")
    if mis:
        facts["gstin_misread"] = mis
        return rr("R04", "note", f"{v['name']} matched by exact name. The GSTIN read from the scan "
                                 f"({c.get('vendor_gstin')}) differs from the one on file ({v['gstin']}) only in "
                                 f"character {mis['position']} ('{mis['read']}' vs '{mis['master']}'), a common scanning "
                                 f"misread, so we used the GSTIN on file.", facts=facts, exposure=total,
                  headline=f"the vendor is {short}; one smudged character of its GSTIN was misread on the scan.",
                  next_step="No action needed unless the vendor's GSTIN has actually changed.")
    how = f"matched by GSTIN {v['gstin']}" if vm["method"] == "gstin" else "matched by name"
    return rr("R04", "pass", f"{v['name']} is an approved vendor ({how}).", facts=facts, ok=f"Vendor approved ({how})")


def r05(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R05", "nothing was extracted")
    c = ctx["canon"]
    v = ctx["vendor_match"].get("vendor")
    b = ctx["bank"]
    total = c.get("total_paise") or 0
    if b["status"] == "no_vendor":
        return skip("R05", "vendor not identified")
    inv_b = c["bank"]
    facts = {"invoice_bank": inv_b.get("name"), "invoice_account": mask_account(inv_b.get("account")),
             "invoice_ifsc": inv_b.get("ifsc"), "master_bank": v.get("bank_name") if v else None,
             "master_account": mask_account(v.get("bank_account_no")) if v else None,
             "master_ifsc": v.get("bank_ifsc") if v else None, "change_notice": c.get("bank_change_notice"),
             "change_text": c.get("bank_change_text")}
    if b["status"] == "not_applicable":
        return rr("R05", "pass", "No bank details printed on the invoice. Nothing to compare.", facts=facts,
                  ok="No bank details on the invoice to compare")
    if b["status"] == "unreadable":
        short = (v.get("short") or v["name"]) if v else "the vendor"
        facts["bank_named"] = b.get("bank_named")
        return rr("R05", "hold", f"The invoice names {b.get('bank_named')} for payment, but we could not read the "
                                 f"account number. We have {v.get('bank_name')} on file.", facts=facts, exposure=total,
                  headline="the invoice names a different bank and we could not read its account number.",
                  next_step=f"Call {short} on the phone number in our vendor file (not the one on the invoice) and "
                            f"confirm where they want to be paid before releasing this invoice.")
    if b.get("offending"):
        inv_b = {**inv_b, **{k: b["offending"].get(k) for k in ("name", "account", "ifsc")}}
        facts["invoice_bank"], facts["invoice_account"] = inv_b.get("name"), mask_account(inv_b.get("account"))
        facts["invoice_ifsc"], facts["bank_entries_seen"] = inv_b.get("ifsc"), b.get("entries_seen")
    if b["status"] == "match":
        return rr("R05", "pass", f"Bank account {mask_account(inv_b.get('account'))} on the invoice matches the account "
                                 f"on file.", facts=facts, ok="Bank account matches the one on file")
    if b["status"] == "match_verified_change":
        facts["verified_by"], facts["changed_at"] = b.get("verified_by"), b.get("changed_at")
        return rr("R05", "pass", f"The invoice mentions a bank change. The new account "
                                 f"{mask_account(inv_b.get('account'))} matches the vendor record, which "
                                 f"{b.get('verified_by')} verified on {fmt_date(b.get('changed_at'))}.", facts=facts,
                  ok="Bank account matches the verified record on file")
    notice = " The invoice also says the bank details have changed." if c.get("bank_change_notice") else ""
    short = (v.get("short") or v["name"]) if v else "the vendor"
    if b["status"] == "notice_only":
        when = (f" Our record was last verified on {fmt_date(v.get('bank_changed_at'))}, before that notice."
                if v and v.get("bank_changed_at") else "")
        return rr("R05", "hold", f"The invoice says {short}'s bank details have changed, but the account it prints "
                                 f"({mask_account(inv_b.get('account'))}) is the one we already have.{when}",
                  facts=facts, exposure=total,
                  headline="the vendor says its bank details changed, but we have no verified new account.",
                  next_step=f"Call {short} on the phone number in our vendor file (not the one on the invoice) and ask "
                            f"whether the account changed before paying.")
    msg = (f"The invoice asks us to pay {inv_b.get('name') or 'a different bank'} (account "
           f"{mask_account(inv_b.get('account'))}). We have {v.get('bank_name')} (account "
           f"{mask_account(v.get('bank_account_no'))}).{notice}")
    att = (f"The invoice asks us to pay {inv_b.get('name') or 'a different bank'} (account "
           f"{mask_account(inv_b.get('account'))}). Our records have {v.get('bank_name')} (account "
           f"{mask_account(v.get('bank_account_no'))}) for {short}. A changed bank account on an invoice is a common "
           f"sign of payment fraud, so we never pay on the invoice alone.")
    return rr("R05", "hold", msg, facts=facts, exposure=total, attention=att,
              headline="the bank account on this invoice is different from the one we have on file.",
              next_step=f"Call {short} on the phone number in our vendor file (not the one on the invoice) and confirm "
                        f"the change. Ask for the change on company letterhead. A manager will update the vendor "
                        f"record and release the hold.")


# ------------------------------------------------------------------ stage 5

def r06(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R06", "nothing was extracted")
    p = ctx["cfg"]["rules"]["R06"]
    d = ctx["dup"]
    c = ctx["canon"]
    total = c.get("total_paise") or 0
    cl = d.get("closest")
    facts = {"score": d["score"], "exact": d.get("exact"), "closest": cl, "signals": d.get("signals"),
             "compared": d.get("compared", 0), "recurring_guard": d.get("recurring_guard", False)}
    thr = {"review": p["review"], "reject": p["reject"]}
    if cl and (d.get("exact") or d["score"] >= p["review"]):
        when = ""
        if cl.get("decided_at") and cl.get("outcome") in ("auto_approve", "approve_with_note"):
            when = f", which was approved on {fmt_date(cl['decided_at'])}"
            if cl.get("paid_at"):
                when += f" and paid on {fmt_date(cl['paid_at'])}"
        vend = ctx["vendor_match"].get("vendor") or {}
        frm = f" from {vend.get('short') or vend.get('name')}" if vend else ""
        ref = (f"invoice {cl.get('invoice_no')}{frm} ({inr(cl.get('total_paise'))}, dated "
               f"{fmt_date(cl.get('invoice_date'))}){when}")
    if d.get("exact") == "file":
        return rr("R06", "reject", f"Exact copy of a file we already processed (same file hash), {ref}.", facts=facts,
                  threshold=thr, exposure=total, headline="this exact file was already processed.",
                  next_step="Do not pay. Send the return notice. A manager can overturn this if it is genuinely new.")
    if d.get("exact") == "number":
        return rr("R06", "reject", f"Same vendor and invoice number as {ref}.", facts=facts, threshold=thr,
                  exposure=total, headline="we have already received an invoice with this number.",
                  next_step="Do not pay. A manager can overturn this if it is genuinely a different invoice.")
    if cl and d["score"] >= p["reject"]:
        paid = bool(cl.get("paid_at"))
        sig = d.get("signals") or {}
        same = [n for k, n in (("amount", "amount"), ("date", "date"), ("po", "PO"), ("lines", "items")) if sig.get(k, 0) >= 1]
        diff_no = cl.get("invoice_no") != c.get("invoice_no")
        att = (f"This matches {ref}. "
               + (f'The invoice number is written differently ("{c.get("invoice_no")}"), but the ' if diff_no else "The ")
               + (", ".join(same[:-1]) + " and " + same[-1] if len(same) > 1 else (same[0] if same else "details"))
               + " are identical.")
        return rr("R06", "reject", f"This is {d['score'] * 100:.0f}% similar to {ref}.", facts=facts, threshold=thr,
                  exposure=total, attention=att,
                  headline=("this looks like an invoice we have already paid." if paid else
                            "this looks like an invoice we have already received."),
                  next_step=(f"Do not pay. Reply to the vendor that this was paid on {fmt_date(cl['paid_at'])} (draft ready). "
                             if paid else "Do not pay. Reply to the vendor (draft ready). ")
                  + "If this is genuinely a different invoice, a manager can overturn this decision.")
    if cl and d["score"] >= p["review"]:
        return rr("R06", "review", f"Possible duplicate: {d['score'] * 100:.0f}% similar to {ref}.", facts=facts,
                  threshold=thr, exposure=total, headline="this may be a duplicate of an earlier invoice.",
                  next_step="Compare the two invoices side by side, then accept or reject.")
    hi = f" (highest similarity {d['score']:.2f}" + (f", {cl.get('invoice_no')}" if cl else "") + ")"
    return rr("R06", "pass", f"Not similar to any earlier invoice{hi}. Allowed below {p['review']:.2f}.", facts=facts,
              threshold=thr, ok="Not a duplicate")


# ------------------------------------------------------------------ stage 6

def r07(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R07", "nothing was extracted")
    p = ctx["cfg"]["rules"]["R07"]
    res = ctx["po_res"]
    c = ctx["canon"]
    total = c.get("total_paise") or 0
    v = ctx["vendor_match"].get("vendor")
    short = (v.get("short") or v["name"]) if v else "the vendor"
    facts = {"method": res["method"], "po_id": res["po"]["id"] if res.get("po") else None, "score": res.get("score"),
             "runner_up": res.get("runner_up"), "runner_up_po": res.get("runner_up_po"), "gap": res.get("gap"),
             "candidates": res.get("candidates"), "written_as": res.get("matched_text"),
             "reference_not_found": res.get("reference_not_found")}
    thr = {"score": p["score"], "gap": p["gap"], "ceil": p["ceil"]}
    if res["method"] == "explicit":
        po = res["po"]["id"]
        if res.get("normalised"):
            msg = f'{po} found. The invoice wrote it as "{res["matched_text"]}", which we normalised.'
            ok = f'{po} found (written as "{res["matched_text"]}" and normalised)'
        else:
            msg, ok = f"{po} was written on the invoice and belongs to {short}.", f"{po} found on the invoice"
        return rr("R07", "pass", msg, facts=facts, threshold=thr, ok=ok)
    if res["method"] == "other_vendor":
        po = res["po"]
        return rr("R07", "review", f"{po['id']} belongs to a different vendor ({po['vendor_id']}).", facts=facts,
                  threshold=thr, exposure=total, headline="the PO on the invoice belongs to a different vendor.",
                  next_step="Ask Procurement which PO was meant.")
    if res["method"] == "implied" and res.get("reference_not_found"):
        po, ref = res["po"]["id"], res["reference_not_found"]
        return rr("R07", "review", f"The invoice quotes {ref}, which we do not have. Its items match {po} at "
                                   f"{res['score'] * 100:.0f}%.", facts=facts, threshold=thr, exposure=total,
                  headline=f"the invoice quotes {ref}, a purchase order we do not have.",
                  next_step=f"Ask {short} which order this is for, or confirm with Procurement that {po} is meant.")
    if res["method"] == "implied":
        po = res["po"]["id"]
        sc, ru, gap = res["score"], res["runner_up"], res["gap"]
        other = (f"; the other open order scores {ru * 100:.0f}%" if res.get("runner_up_po") else "")
        if sc >= p["score"] and gap >= p["gap"] - 1e-9:
            ceil_paise = int(p["ceil"] * 100)
            sib = ctx.get("siblings") or []
            together = total + sum(s["total_paise"] for s in sib)
            if total <= ceil_paise < together:
                names = ", ".join(s["invoice_no"] for s in sib)
                facts.update({"siblings": sib, "together_paise": together})
                return rr("R07", "review", f"No PO number on the invoice. {po} matches at {sc * 100:.0f}%, but with "
                                           f"invoice {names} on the same inferred PO this week the total is "
                                           f"{inr0(together)}, above the {inr0(ceil_paise)} limit for an inferred PO.",
                          facts=facts, threshold=thr, exposure=total,
                          headline="the PO was inferred and, together with another invoice, the amount is too large to "
                                   "approve on an inferred PO.",
                          next_step=f"Confirm with Procurement that {po} is the right order for both invoices.")
            if total <= ceil_paise:
                msg = f"No PO number on the invoice. {po} is the best match at {sc * 100:.0f}%{other}."
                att = (f"The PO number was missing. {po} is the only open order that matches these items and prices "
                       f"({sc * 100:.0f}% match{other.replace('; ', '; ')}).")
                return rr("R07", "note", msg, facts=facts, threshold=thr, attention=att,
                          headline="we matched this invoice to a purchase order that the vendor did not mention.",
                          next_step="None needed. You can correct any field if you disagree and the invoice will be re-checked.")
            return rr("R07", "review", f"No PO number on the invoice. {po} matches at {sc * 100:.0f}%{other}, but the "
                                       f"invoice is above {inr0(ceil_paise)}, so a person must confirm.",
                      facts=facts, threshold=thr, exposure=total,
                      headline="the PO was inferred and the amount is too large to approve on an inferred PO.",
                      next_step=f"Confirm with Procurement that {po} is the right order.")
        if sc >= ctx["cfg"]["advanced"]["implied_review_floor"]:
            cands = ", ".join(f"{x['po_id']} {x['score'] * 100:.0f}%" for x in res["candidates"])
            return rr("R07", "review", f"No PO number on the invoice. No single PO is a clear match ({cands}); we need "
                                       f"{p['score'] * 100:.0f}% and a gap of {p['gap'] * 100:.0f} points.",
                      facts=facts, threshold=thr, exposure=total,
                      headline="we could not tell which purchase order this invoice belongs to.",
                      next_step="Pick the right PO from the candidates, or ask Procurement.")
    ref = res.get("reference_not_found")
    msg = (f'The PO reference "{ref}" does not match any PO, and no open PO is a plausible match.' if ref else
           "No PO on the invoice and no plausible match among open POs.")
    return rr("R07", "hold", msg, facts=facts, threshold=thr, exposure=total,
              headline="we could not find a purchase order for this invoice.",
              next_step=f"Ask Procurement or {short} for the PO number.")


def _po_noun(po: dict) -> str | None:
    if len(po["lines"]) == 1:
        l = po["lines"][0]
        return unit_noun(l["description"], l["uom"])
    return None


def r08(ctx) -> dict:
    po = ctx["po_res"].get("po") if ctx["extraction_status"] == "ok" else None
    if not po:
        return skip("R08", "no PO to check")
    c = ctx["canon"]
    total = c.get("total_paise") or 0
    facts = {"po_id": po["id"], "status": po["status"], "issue_date": po.get("issue_date"), "valid_to": po.get("valid_to"),
             "billed_subtotal_paise": po["billed_subtotal_paise"], "po_subtotal_paise": po["subtotal_paise"]}
    if po["status"] in ("closed", "cancelled"):
        return rr("R08", "reject", f"{po['id']} is {po['status']}.", facts=facts, exposure=total,
                  headline=f"the purchase order is {po['status']}.", next_step="Do not pay. Ask Procurement.")
    if po["status"] == "fully_billed":
        noun = _po_noun(po)
        if noun:
            l = po["lines"][0]
            detail = f"{fmt_qty(l['billed_qty'])} of {fmt_qty(l['ordered_qty'])} {noun}"
        else:
            detail = f"{inr0(po['billed_subtotal_paise'])} of {inr0(po['subtotal_paise'])}"
        return rr("R08", "reject", f"{po['id']} is already fully billed ({detail}).", facts=facts, exposure=total,
                  attention=f"{po['id']} is already fully billed ({detail}).",
                  headline="the purchase order is already fully billed.",
                  next_step="Do not pay. Ask the vendor which order this invoice is for.")
    d = c.get("invoice_date")
    a, b = to_date(po.get("issue_date")), to_date(po.get("valid_to"))
    if d and a and b and not (a <= d <= b):
        return rr("R08", "review", f"The invoice date {fmt_date(d)} is outside {po['id']}'s validity "
                                   f"({fmt_date(a)} to {fmt_date(b)}).", facts=facts, exposure=total,
                  headline="the invoice date is outside the PO's validity window.",
                  next_step="Ask Procurement whether the PO was extended.")
    state = "open" if po["status"] == "open" else "partly billed"
    return rr("R08", "pass", f"{po['id']} is {state} and the invoice date is inside its validity window.", facts=facts,
              ok=f"{po['id']} is {state}")


def r09(ctx) -> dict:
    po = ctx["po_res"].get("po") if ctx["extraction_status"] == "ok" else None
    if not po:
        return skip("R09", "no PO to align to")
    c = ctx["canon"]
    al = ctx["alignment"]
    p = ctx["cfg"]["rules"]["R09"]
    lines = {l["line_no"]: l for l in c["lines"]}
    pre_total = sum(l["pretax_amount_paise"] or 0 for l in c["lines"]) or (c.get("subtotal_paise") or 0)
    unordered = [a for a in al if a["method"] == "none"]
    un_val = sum(lines[a["line_no"]]["pretax_amount_paise"] or 0 for a in unordered)
    share = 100.0 * un_val / pre_total if pre_total else 0.0
    bundles = [a for a in al if a["method"] == "bundle"]
    pl_by_id = {l["id"]: l for l in po["lines"]}
    facts = {"unordered_lines": [lines[a["line_no"]]["description"] for a in unordered], "unordered_value_paise": un_val,
             "share_pct": round(share, 2), "bundles": [{"line_no": a["line_no"], "po_lines": [pl_by_id[i]["item_code"] for i in a["po_line_ids"]]} for a in bundles]}
    if not c["lines"]:
        return rr("R09", "review", "No line items could be read, so the lines cannot be matched to the PO.", facts=facts,
                  exposure=c.get("total_paise") or 0, headline="we could not read the line items.",
                  next_step="Check the lines against the document.")
    if not unordered:
        if bundles:
            names = " and ".join(pl_by_id[i]["description"].split(",")[0].lower() for i in bundles[0]["po_line_ids"])
            n = len(bundles[0]["po_line_ids"])
            msg = (f"One invoice line covers {n} PO lines ({names}). Matched as a bundle." if len(bundles) == 1 else
                   f"{len(bundles)} bundled invoice lines matched across several PO lines.")
            return rr("R09", "pass", msg, facts=facts, ok=f"The bundled line covers {n} PO lines")
        return rr("R09", "pass", "Every invoice line maps to a line on the PO.", facts=facts,
                  ok="Every line is on the PO")
    names = ", ".join(f'"{x}"' for x in facts["unordered_lines"])
    thr = {"pct": p["pct"]}
    sev = "review" if share <= p["pct"] else "reject"
    return rr("R09", sev, f"{names} {'is' if len(unordered) == 1 else 'are'} not on {po['id']}: {inr0(un_val)}, "
                          f"{pct_str(share)} of the invoice.", facts=facts, threshold=thr,
              exposure=int(un_val * 1.18) if sev else 0,
              headline="the invoice includes items that are not on the purchase order.",
              next_step="Ask Procurement whether these items were ordered, or ask the vendor to remove them.")


# ------------------------------------------------------------------ stage 7

def _aligned(ctx):
    po = ctx["po_res"]["po"]
    pl_by_id = {l["id"]: l for l in po["lines"]}
    lines = {l["line_no"]: l for l in ctx["canon"]["lines"]}
    for a in ctx["alignment"]:
        if a["method"] == "none":
            continue
        yield a, lines[a["line_no"]], [pl_by_id[i] for i in a["po_line_ids"]]


def r10(ctx) -> dict:
    po = ctx["po_res"].get("po") if ctx["extraction_status"] == "ok" else None
    if not po:
        return skip("R10", "no PO to compare prices with")
    p = ctx["cfg"]["rules"]["R10"]
    rows, worst, exposure = [], "pass", 0
    for a, l, pls in _aligned(ctx):
        q = l.get("qty") or 0
        po_unit = sum(pl["unit_price_paise"] for pl in pls)
        if not q:
            # Without a quantity the price cannot be checked; never treat that as a match.
            rows.append({"line_no": l["line_no"], "bundle": False, "po_unit_paise": po_unit, "invoice_unit_paise": None,
                         "delta_paise": 0, "delta_pct": 0.0, "severity": "review", "band": "quantity not readable",
                         "qty": None, "noun": unit_noun(pls[0]["description"], pls[0].get("uom"), 1)})
            worst = "review" if SEV_RANK["review"] > SEV_RANK[worst] else worst
            continue
        expected = int(round(q * po_unit))
        actual = l.get("pretax_amount_paise") or 0
        delta = actual - expected
        pct = 100.0 * delta / expected if expected else 0.0
        sev, bname = band(delta, pct, p)
        inv_unit = actual / q if q else 0
        rate = (pls[0].get("tax_rate_pct") or 0) / 100.0
        if delta > 0 and sev != "pass":
            exposure += int(round(delta * (1 + rate)))
        rows.append({"line_no": l["line_no"], "bundle": a["method"] == "bundle", "po_unit_paise": po_unit,
                     "invoice_unit_paise": int(round(inv_unit)), "delta_paise": delta, "delta_pct": round(pct, 3),
                     "severity": sev, "band": bname, "qty": q,
                     "noun": unit_noun(pls[0]["description"] if len(pls) == 1 else "set",
                                       (pls[0].get("uom") or l.get("uom")) if len(pls) == 1 else "sets", 1),
                     "over_from": list(pls[0].get("over_from") or []) if len(pls) == 1 else [],
                     "over_before_paise": int(pls[0].get("over_billed_paise") or 0) if len(pls) == 1 else 0,
                     "tax_rate": rate})
        if SEV_RANK[sev] > SEV_RANK[worst]:
            worst = sev
    if not rows:
        return skip("R10", "no line matched the PO")
    facts = {"lines": rows}
    thr = {**p, "allowed": allowed_text("R10", ctx["cfg"])}
    allowed = f"Allowed: up to {p['note_pct']:g}% and {inr0(int(p['note_abs'] * 100))}."
    # Repeated small overcharges on the same PO line (each one inside the "note" band) go to a person.
    repeat = [r for r in rows if r["severity"] == "note" and r["delta_paise"] > 0 and r["over_from"]]
    if repeat and SEV_RANK[worst] <= SEV_RANK["note"]:
        r = repeat[0]
        together = r["over_before_paise"] + r["delta_paise"]
        who = ", ".join(r["over_from"])
        facts["repeat_overcharge"] = {"line_no": r["line_no"], "earlier_invoices": r["over_from"],
                                      "together_paise": together}
        return rr("R10", "review", f"Price per {r['noun']} is {inr(r['invoice_unit_paise'])} against "
                                   f"{inr(r['po_unit_paise'])} on the PO ({pct_str(r['delta_pct'])} above). Invoice {who} "
                                   f"on the same PO line was also billed above the PO price: together {inr0(together)} "
                                   f"over.", facts=facts, threshold=thr,
                  exposure=int(round(together * (1 + r["tax_rate"]))),
                  headline="the vendor keeps billing slightly above the PO price on the same line.",
                  next_step="Ask Procurement whether the price changed. If not, ask the vendor for a credit note for "
                            "the overcharge on all the invoices.")
    # The ₹ floor that makes a tiny difference "exact enough" applies to the whole invoice, not to each line:
    # five lines each ₹49 over a ₹40 price are not five rounding differences.
    small = [r for r in rows if r["band"] == "exact enough" and r["delta_paise"] > 0 and r["delta_pct"] > p["pass_pct"]]
    agg = sum(r["delta_paise"] for r in small)
    if worst == "pass" and small and agg > (p.get("pass_abs") or 0) * 100:
        base = sum(int(round(r["qty"] * r["po_unit_paise"])) for r in small) or 1
        apct = 100.0 * agg / base
        sev, _ = band(agg, apct, {**p, "pass_abs": 0})
        sev = "review" if SEV_RANK[sev] > SEV_RANK["review"] else sev
        if sev != "pass":
            facts["small_lines_over_paise"] = agg
            return rr("R10", sev, f"{len(small)} small lines are priced above the PO. Each is only a few rupees over, but "
                                  f"together they are {inr0(agg)} ({pct_str(apct)}) over.", facts=facts, threshold=thr,
                      exposure=agg if sev == "review" else 0,
                      headline="several small lines are priced well above the purchase order.",
                      next_step=("None needed. The difference is noted." if sev == "note" else
                                 "Ask Procurement to confirm the prices, then accept or override."))
    if worst == "pass":
        if len(rows) == 1:
            r = rows[0]
            return rr("R10", "pass", f"Price per {r['noun']} {inr(r['invoice_unit_paise'])} matches the PO.", facts=facts,
                      threshold=thr, ok=f"Price per {r['noun']} matches ({inr0(r['po_unit_paise'])})")
        return rr("R10", "pass", f"Unit prices match the PO on all {len(rows)} lines.", facts=facts, threshold=thr,
                  ok="Prices match the PO")
    r = max(rows, key=lambda x: SEV_RANK[x["severity"]] * 1e12 + abs(x["delta_paise"]))
    if r["band"] == "quantity not readable":
        return rr("R10", "review", f"We could not read the quantity on line {r['line_no']}, so its price could not be "
                                   f"checked against the PO ({inr(r['po_unit_paise'])} per {r['noun']}).",
                  facts=facts, threshold=thr, headline="we could not read a quantity, so the price could not be checked.",
                  next_step="Check the quantity on the invoice against the goods received, then accept or override.")
    if r["bundle"]:
        what = f"The bundle is priced {inr0(abs(r['delta_paise']))} ({pct_str(r['delta_pct'])}) {'above' if r['delta_paise'] > 0 else 'below'} the PO lines it covers."
    else:
        what = (f"Price per {r['noun']} is {inr(r['invoice_unit_paise'])} against {inr(r['po_unit_paise'])} on the PO: "
                f"{pct_str(r['delta_pct'])} {'above' if r['delta_paise'] > 0 else 'below'} ({inr0(abs(r['delta_paise']))} on "
                f"this invoice).")
    msg = f"{what} {allowed}"
    heads = {"note": f"the vendor billed {pct_str(r['delta_pct'])} more than the PO, which is within the allowed difference.",
             "review": "the price is higher than the purchase order allows.",
             "reject": "the price is so far from the purchase order that this looks like a different transaction."}
    if r["delta_paise"] < 0:
        heads["note"] = f"the vendor billed {pct_str(r['delta_pct'])} less than the PO."
        heads["review"] = "the vendor billed much less than the PO, which may mean a partial delivery."
    att = None
    if worst == "note" and r["delta_paise"] > 0:
        att = (f"The vendor billed {inr0(abs(r['delta_paise']))} ({pct_str(r['delta_pct'])}) more than the PO. That is "
               f"inside the allowed difference of {p['note_pct']:g}% and {inr0(int(p['note_abs'] * 100))}, so we approved "
               f"it and attached a note.")
    nxt = {"note": "None needed. The invoice is in the payment queue with the note attached. About 1 in 10 noted "
                   "invoices is sampled for the monthly audit.",
           "review": "Ask Procurement to confirm the new price, then accept or override.",
           "reject": "Send the return notice and ask the vendor to reissue the invoice at the PO price."}[worst]
    return rr("R10", worst, msg, facts=facts, threshold=thr, exposure=exposure, headline=heads[worst], next_step=nxt,
              attention=att)


def r11(ctx) -> dict:
    po = ctx["po_res"].get("po") if ctx["extraction_status"] == "ok" else None
    if not po:
        return skip("R11", "no PO to compare quantities with")
    p = ctx["cfg"]["rules"]["R11"]
    this_qty: dict[int, float] = {}
    for a, l, pls in _aligned(ctx):
        for al in a["alloc"]:
            this_qty[al["po_line_id"]] = this_qty.get(al["po_line_id"], 0) + float(al["qty"] or 0)
    if not this_qty:
        return skip("R11", "no line matched the PO")
    no_qty = [l["line_no"] for a, l, pls in _aligned(ctx) if not l.get("qty")]
    if no_qty:
        return rr("R11", "review", f"We could not read the quantity on line {no_qty[0]}, so we cannot tell how much of "
                                   f"the PO this invoice uses.", facts={"lines_without_qty": no_qty},
                  headline="we could not read a quantity, so the PO balance could not be checked.",
                  next_step="Check the quantity against the goods received, then accept or override.")
    rows, worst, exposure = [], "pass", 0
    for pl in po["lines"]:
        if pl["id"] not in this_qty:
            continue
        q = this_qty[pl["id"]]
        rem = pl["remaining_qty"]
        over = q - rem
        pct = 100.0 * over / pl["ordered_qty"] if pl["ordered_qty"] else 100.0
        pend = pl.get("pending_qty") or 0
        if over <= 1e-9 and pend and q - (rem - pend) > 1e-9:
            # Fits only if an invoice waiting in review/hold for the same PO line is ignored. If that one is approved
            # later, the line is over-billed, so a person must see both together (spec 2.3).
            sev, bname = "review", "claimed by a pending invoice"
        elif over <= 1e-9:
            sev, bname = "pass", "within remaining"
        else:
            sev, bname = band(int(round(over * pl["unit_price_paise"])), pct, p)
        if sev != "pass" and over > 0:
            exposure += int(round(over * pl["unit_price_paise"] * (1 + (pl["tax_rate_pct"] or 0) / 100)))
        rows.append({"po_line_id": pl["id"], "item_code": pl["item_code"], "ordered": pl["ordered_qty"],
                     "billed_before": pl["billed_qty"], "pending": pl["pending_qty"], "this_invoice": q,
                     "remaining": rem, "over": round(max(0.0, over), 4), "over_pct": round(pct, 3), "severity": sev,
                     "band": bname, "unit_price_paise": pl["unit_price_paise"], "tax_rate_pct": pl["tax_rate_pct"],
                     "noun": unit_noun(pl["description"], pl["uom"]), "pending_from": list(pl.get("pending_from") or [])})
        if SEV_RANK[sev] > SEV_RANK[worst]:
            worst = sev
    facts = {"lines": rows}
    thr = {**p, "allowed": allowed_text("R11", ctx["cfg"])}
    claimed = [x for x in rows if x["band"] == "claimed by a pending invoice"]
    if claimed and worst == "review" and not any(x["severity"] == "review" and x not in claimed for x in rows):
        r = claimed[0]
        who = ", ".join(r["pending_from"]) or "another invoice"
        free = max(0.0, r["remaining"] - r["pending"])
        return rr("R11", "review", f"{fmt_qty(r['this_invoice'])} {r['noun']} billed. {fmt_qty(r['remaining'])} remain on "
                                   f"the PO, but invoice {who} (waiting in the review queue) already claims "
                                   f"{fmt_qty(r['pending'])} of them, leaving {fmt_qty(free)}.", facts=facts,
                  threshold=thr, headline=f"invoice {who}, still in review, already claims part of this PO.",
                  next_step=f"Decide invoice {who} first, then accept or override this one.")
    if worst == "pass":
        if len(rows) == 1:
            r = rows[0]
            return rr("R11", "pass", f"{fmt_qty(r['this_invoice'])} {r['noun']} billed; {fmt_qty(r['remaining'])} remained "
                                     f"on the PO.", facts=facts, threshold=thr,
                      ok="Quantities are within what is left on the order")
        return rr("R11", "pass", "Quantities are within what remains on the PO.", facts=facts, threshold=thr,
                  ok="Quantities are within what is left on the order")
    r = max((x for x in rows if x["severity"] == worst), key=lambda x: x["over"])
    msg = (f"{fmt_qty(r['this_invoice'])} {r['noun']} billed against {fmt_qty(r['remaining'])} remaining: "
           f"{fmt_qty(r['over'])} over, which is {pct_str(r['over_pct'])} of the {fmt_qty(r['ordered'])} ordered. "
           f"Allowed: up to {p['note_pct']:g}%.")
    return rr("R11", worst, msg, facts=facts, threshold=thr, exposure=exposure,
              headline="this invoice would bill more than the purchase order allows.",
              next_step="Ask the vendor for a credit note for the extra quantity, or ask Procurement to increase the PO.")


def r12(ctx) -> dict:
    po = ctx["po_res"].get("po") if ctx["extraction_status"] == "ok" else None
    if not po:
        return skip("R12", "no PO to compare values with")
    p = ctx["cfg"]["rules"]["R12"]
    this = sum(al["amount_paise"] for a, _l, _p in _aligned(ctx) for al in a["alloc"])
    if not this:
        return skip("R12", "no line matched the PO")
    before = po["billed_subtotal_paise"]
    after = before + this
    po_sub = po["subtotal_paise"]
    delta = after - po_sub
    pct = 100.0 * delta / po_sub if po_sub else 100.0
    rate = (po["lines"][0].get("tax_rate_pct") or 0) / 100 if po["lines"] else 0
    facts = {"po_id": po["id"], "billed_before_paise": before, "pending_paise": po["pending_subtotal_paise"],
             "this_invoice_paise": this, "after_paise": after, "po_subtotal_paise": po_sub,
             "pct_before": round(100.0 * before / po_sub, 2) if po_sub else 0,
             "pct_after": round(100.0 * after / po_sub, 2) if po_sub else 0, "delta_paise": delta,
             "delta_pct": round(pct, 3), "tax_rate_pct": rate * 100}
    thr = {**p, "allowed": allowed_text("R12", ctx["cfg"])}
    pending = po.get("pending_subtotal_paise") or 0
    if delta <= 0 and pending and delta + pending > 0:
        pd = delta + pending
        psev, _ = band(pd, 100.0 * pd / po_sub if po_sub else 100.0, p)
        if psev not in ("pass", "note"):
            who = sorted({n for l in po["lines"] for n in (l.get("pending_from") or [])})
            names = ", ".join(who) or "another invoice"
            facts["pending_invoices"] = who
            return rr("R12", "review", f"Billed so far {inr0(before)} plus this invoice {inr0(this)} fits the PO value of "
                                       f"{inr0(po_sub)}, but invoice {names} (waiting in the review queue) adds "
                                       f"{inr0(pending)}. Together they are {inr0(pd)} over.", facts=facts, threshold=thr,
                      exposure=int(round(pd * (1 + rate))),
                      headline=f"together with invoice {names}, still in review, this would bill more than the PO.",
                      next_step=f"Decide invoice {names} first, then accept or override this one.")
    if delta <= 0:
        return rr("R12", "pass", f"Billed so far {inr0(before)} plus this invoice {inr0(this)} is within the PO value of "
                                 f"{inr0(po_sub)}.", facts=facts, threshold=thr,
                  ok="Invoice value fits within what is left on the PO")
    sev, bname = band(delta, pct, p)
    facts["band"] = bname
    msg = (f"Cumulative pre-tax billed would be {inr0(after)} against {inr0(po_sub)} on the PO: {inr0(delta)} "
           f"({pct_str(pct)}) over.")
    if sev == "pass":
        return rr("R12", "pass", msg + " That is within rounding.", facts=facts, threshold=thr,
                  ok="Invoice value fits within the PO")
    exposure = int(round(delta * (1 + rate)))
    heads = {"note": f"the vendor billed {pct_str(pct)} more than the PO, which is within the allowed difference.",
             "review": "this invoice would bill more than the purchase order allows.",
             "reject": "this invoice would bill far more than the purchase order allows."}
    nxt = {"note": "None needed. The invoice is in the payment queue with the note attached.",
           "review": "Approve what fits on the PO and ask the vendor for a credit note, or ask Procurement to increase the PO.",
           "reject": "Do not pay. Send the return notice and ask the vendor which order this is for."}[sev]
    return rr("R12", sev, msg, facts=facts, threshold=thr, exposure=exposure if sev != "note" else exposure,
              headline=heads[sev], next_step=nxt)


def r13(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R13", "nothing was extracted")
    c = ctx["canon"]
    p = ctx["cfg"]["rules"]["R13"]
    po = ctx["po_res"].get("po")
    lines = c["lines"]
    if not lines and c.get("subtotal_paise") is None:
        return skip("R13", "no taxable value")
    slabs: dict[float, int] = {}
    if lines:
        for l in lines:
            r = l.get("tax_rate_pct")
            if r is None:
                r = c.get("tax_rate_pct")
            slabs[float(r) if r is not None else -1.0] = slabs.get(float(r) if r is not None else -1.0, 0) + (l["pretax_amount_paise"] or 0)
    else:
        slabs[float(c.get("tax_rate_pct") or -1)] = c["subtotal_paise"]
    if -1.0 in slabs:
        # no rate printed anywhere: use the PO's rate when known
        po_rate = po["lines"][0]["tax_rate_pct"] if po and po["lines"] else None
        if po_rate is None:
            return skip("R13", "no GST rate on the invoice or the PO")
        slabs[float(po_rate)] = slabs.pop(-1.0) + slabs.get(float(po_rate), 0)
    expected = sum(int(round(v * r / 100.0)) for r, v in slabs.items())
    shown = c.get("tax_printed_paise")
    if shown is None:
        shown = 0
    diff = shown - expected
    ad = abs(diff)
    taxable = sum(slabs.values())
    rates = sorted(slabs)
    rate_txt = "/".join(f"{r:g}%" for r in rates)
    facts = {"taxable_paise": taxable, "rates": rates, "expected_paise": expected, "shown_paise": shown,
             "diff_paise": diff, "tax_inclusive": c.get("tax_inclusive")}
    thr = {"pass": p["pass"], "note": p["note"], "review": p["review"]}
    # rate must match the PO line's rate
    wrong_rate = None
    if po:
        pl_by_id = {l["id"]: l for l in po["lines"]}
        for a in ctx["alignment"]:
            l = next(x for x in lines if x["line_no"] == a["line_no"])
            for pid in a["po_line_ids"]:
                pr = pl_by_id[pid]["tax_rate_pct"]
                lr = l.get("tax_rate_pct")
                if pr is not None and lr is not None and abs(float(pr) - float(lr)) > 0.01:
                    wrong_rate = (lr, pr, pl_by_id[pid]["item_code"])
    if ad <= p["pass"] * 100:
        sev = "pass"
    elif ad <= p["note"] * 100:
        sev = "note"
    elif ad <= p["review"] * 100:
        sev = "review"
    else:
        sev = "reject"
    if wrong_rate and SEV_RANK[sev] < SEV_RANK["review"]:
        facts["wrong_rate"] = {"invoice": wrong_rate[0], "po": wrong_rate[1], "item_code": wrong_rate[2]}
        return rr("R13", "review", f"GST rate is {wrong_rate[0]:g}% but the PO line {wrong_rate[2]} says {wrong_rate[1]:g}%.",
                  facts=facts, threshold=thr, exposure=ad, headline="the GST rate is different from the purchase order.",
                  next_step="Ask the vendor which rate applies.")
    if sev == "pass":
        incl = " once the tax-inclusive prices are backed out" if c.get("tax_inclusive") else ""
        return rr("R13", "pass", f"GST of {inr0(shown)} is correct at {rate_txt}{incl}.", facts=facts, threshold=thr,
                  ok=f"GST at {rate_txt} is calculated correctly")
    low_high = "too low" if diff < 0 else "too high"
    msg = (f"GST shown is {inr0(shown)} but {rate_txt} of {inr0(taxable)} is {inr0(expected)}. Off by {inr0(ad)}. "
           f"Allowed: up to {inr0(int(p['pass'] * 100))}.")
    att = None
    if sev == "reject":
        consistent = c.get("total_paise") is not None and c.get("subtotal_paise") is not None and \
            abs(c["subtotal_paise"] + shown - c["total_paise"]) <= 100
        att = (f"GST should be {inr0(expected)} ({rate_txt} of {inr0(taxable)}) but the invoice shows {inr0(shown)}, which "
               f"is {inr0(ad)} {low_high}."
               + (" The total on the invoice is consistent with the wrong tax, so the error is in the tax line." if consistent else "")
               + " GST amounts must be right for input credit.")
    heads = {"note": "the GST is off by a few rupees of rounding.",
             "review": "the GST amount does not match the rate.",
             "reject": "the GST on this invoice is wrong and the vendor must send a corrected one."}
    vend = ctx["vendor_match"].get("vendor")
    vshort = (vend.get("short") or vend["name"]) if vend else "the vendor"
    nxt = {"note": "None needed; the difference is rounding.",
           "review": "Ask the vendor to confirm the GST calculation.",
           "reject": f"Send {vshort} the return notice (draft ready) and ask for a corrected invoice. Nothing is paid "
                     f"until it arrives."}[sev]
    return rr("R13", sev, msg, facts=facts, threshold=thr, exposure=ad, headline=heads[sev], next_step=nxt, attention=att)


def r14(ctx) -> dict:
    if ctx["extraction_status"] != "ok":
        return skip("R14", "nothing was extracted")
    c = ctx["canon"]
    p = ctx["cfg"]["rules"]["R14"]
    # The invoice's own arithmetic: printed quantity x printed rate must equal the printed line amount.
    for l in c.get("lines") or []:
        q, unit, amt = l.get("qty"), l.get("unit_price_paise"), l.get("amount_paise")
        if l.get("calculated") or not q or not unit or amt is None:
            continue
        calc = int(round(q * unit))
        off = amt - calc
        if abs(off) > max(100, 0.0005 * abs(amt)):
            sure = (l.get("confidence") or 0) >= 0.85
            facts = {"line_no": l["line_no"], "qty": q, "unit_price_paise": unit, "printed_amount_paise": amt,
                     "calculated_paise": calc, "difference_paise": off}
            msg = (f"Line {l['line_no']}: {fmt_qty(q)} x {inr(unit)} is {inr(calc)}, but the invoice says {inr(amt)} "
                   f"({inr(abs(off))} {'more' if off > 0 else 'less'}).")
            if sure:
                return rr("R14", "reject", msg, facts=facts, exposure=max(0, off),
                          headline="the invoice's own line arithmetic is wrong.",
                          next_step="Send the return notice and ask the vendor for a corrected invoice.")
            return rr("R14", "hold", msg + " Some values were hard to read, so we may have misread them.", facts=facts,
                      exposure=max(0, off), headline="a line's arithmetic does not add up, so we need to re-check it.",
                      next_step="Check the line against the document and correct it, or ask the vendor.")
    sub, tax, total = c.get("subtotal_paise"), c.get("tax_printed_paise"), c.get("total_paise")
    if sub is None or tax is None or total is None:
        return skip("R14", "subtotal, tax or total missing")
    computed = sub + tax + (c.get("other_charges_paise") or 0) - (c.get("discount_paise") or 0)
    diff = abs(computed - total)
    f = c["fields"]
    confs = {k: f[k]["effective_confidence"] for k in ("subtotal", "tax_total", "total")}
    facts = {"subtotal_paise": sub, "tax_paise": tax, "other_paise": c.get("other_charges_paise") or 0,
             "discount_paise": c.get("discount_paise") or 0, "computed_paise": computed, "stated_total_paise": total,
             "diff_paise": diff, "confidences": confs}
    thr = {"pass": p["pass"], "note": p["note"], "confidence": 0.85}
    lines = c.get("lines") or []
    if diff <= p["note"] * 100 and lines and all(l.get("amount_paise") is not None for l in lines):
        # The total can add up while the subtotal includes a charge that is on no line we read (an amount-only row,
        # or a line the parser skipped). That charge has not been checked against the PO, so a person must look.
        sums = [sum(l.get("pretax_amount_paise") or l["amount_paise"] for l in lines), sum(l["amount_paise"] for l in lines)]
        gap = min(abs(sub - s) for s in sums)
        if gap > p["note"] * 100:
            line_sum = sums[0]
            facts.update({"line_sum_paise": line_sum, "unexplained_paise": sub - line_sum})
            return rr("R14", "review", f"The line items we read add up to {inr0(line_sum)}, but the subtotal is "
                                       f"{inr0(sub)}. {inr0(abs(sub - line_sum))} is not on any line we could check "
                                       f"against the PO.", facts=facts, threshold=thr, exposure=abs(sub - line_sum),
                      headline=f"{inr0(abs(sub - line_sum))} of the subtotal is not on any line we could check.",
                      next_step="Find the extra charge on the invoice and confirm it was agreed, then accept or "
                                "override.")
    other = c.get("other_charges_paise") or 0
    if diff <= p["note"] * 100 and other > 100:
        # Freight, packing etc. make the total add up, but they are not on the PO: small amounts get a note, larger
        # ones a person (the same ₹ limit as a price difference that gets a note, R10).
        labels = "; ".join(c.get("other_charge_labels") or []) or "other charges"
        cap = int(ctx["cfg"]["rules"]["R10"]["note_abs"] * 100)
        sev = "note" if other <= cap else "review"
        return rr("R14", sev, f"The total adds up, including {inr0(other)} of charges that are not on the PO "
                              f"({labels}).", facts={**facts, "other_labels": c.get("other_charge_labels")},
                  threshold=thr, exposure=other if sev == "review" else 0,
                  headline=(f"the invoice adds {inr0(other)} of charges such as freight that are not on the PO."),
                  next_step=("None needed. The charge is within the allowed difference and is noted." if sev == "note"
                             else "Confirm the extra charge was agreed with Procurement, then accept or override."))
    if diff <= p["pass"] * 100:
        return rr("R14", "pass", f"Subtotal {inr0(sub)} plus tax {inr0(tax)} equals the stated total {inr0(total)}.",
                  facts=facts, threshold=thr, ok="Total adds up")
    if diff <= p["note"] * 100:
        return rr("R14", "note", f"Subtotal plus tax is {inr(computed)}; the stated total is {inr(total)} (off by "
                                 f"{inr(diff)}).", facts=facts, threshold=thr,
                  headline="the total is off by a few rupees of rounding.")
    if min(confs.values()) >= 0.85:
        return rr("R14", "reject", f"Subtotal {inr0(sub)} plus tax {inr0(tax)} is {inr0(computed)}, but the invoice total "
                                   f"is {inr0(total)}: off by {inr0(diff)}.", facts=facts, threshold=thr, exposure=diff,
                  headline="the invoice total does not add up.",
                  next_step="Send the return notice and ask the vendor for a corrected invoice.")
    return rr("R14", "hold", f"The numbers we read do not add up (off by {inr0(diff)}), and some were hard to read. We "
                             f"may have misread them.", facts=facts, threshold=thr, exposure=total,
              headline="the numbers we read do not add up, so we need to re-check them.",
              next_step="Check subtotal, tax and total against the document and correct them.")


def r15(ctx) -> dict:
    if ctx["extraction_status"] != "ok" or ctx["canon"].get("total_paise") is None:
        return skip("R15", "no total")
    total = ctx["canon"]["total_paise"]
    cap = int(ctx["cfg"]["rules"]["R15"]["cap"] * 100)
    facts = {"total_paise": total, "cap_paise": cap}
    sib = ctx.get("siblings") or []
    together = total + sum(s["total_paise"] for s in sib)
    if total <= cap < together:
        names = ", ".join(s["invoice_no"] for s in sib)
        facts.update({"siblings": sib, "together_paise": together})
        return rr("R15", "review", f"This invoice is {inr0(total)}, but with invoice {names} from the same vendor on the "
                                   f"same PO this week the total is {inr0(together)}, above the {inr0(cap)} manager "
                                   f"sign-off limit.", facts=facts, threshold={"cap": cap / 100}, exposure=total,
                  headline="together with another invoice on the same PO this week, this needs a manager.",
                  next_step="A manager reviews both invoices together and signs off.")
    if total > cap:
        return rr("R15", "review", f"Total {inr0(total)} is above {inr0(cap)}, so a manager must sign it off.", facts=facts,
                  threshold={"cap": cap / 100}, exposure=total, headline="this is a high-value invoice that needs a manager.",
                  next_step="A manager reviews and signs off.")
    return rr("R15", "pass", f"Total {inr0(total)} is below the {inr0(cap)} manager sign-off limit.", facts=facts,
              threshold={"cap": cap / 100})


def r16(ctx) -> dict:
    po = ctx["po_res"].get("po") if ctx["extraction_status"] == "ok" else None
    if not po:
        return skip("R16", "no PO to compare currency with")
    cur = ctx["canon"].get("currency")
    if not cur:
        return skip("R16", "no currency on the invoice (see R01)")
    facts = {"invoice_currency": cur, "po_currency": po.get("currency")}
    if cur == (po.get("currency") or "INR"):
        return rr("R16", "pass", f"Invoice currency ({cur}) matches the PO currency.", facts=facts)
    return rr("R16", "review", f"Invoice currency {cur} differs from the PO currency {po.get('currency')}.", facts=facts,
              exposure=ctx["canon"].get("total_paise") or 0, headline="the invoice is in a different currency from the PO.",
              next_step="Ask Procurement how this should be paid.")


STAGE_RULES = {3: [r01, r02, r03], 4: [r04, r05], 5: [r06], 6: [r07, r08, r09], 7: [r10, r11, r12, r13, r14, r15, r16]}


def apply_enabled(result: dict, cfg: dict) -> dict:
    if cfg.get("enabled", {}).get(result["rule_id"], True) is False and not result["skipped"]:
        return {**result, "severity": "pass", "skipped": True,
                "message": "Not checked: this rule is switched off in Rules and tolerances.", "exposure_paise": 0}
    return result


# ------------------------------------------------------------------ decision

LEAD_PRIORITY = ["R01", "R06", "R05", "R04", "R13", "R14", "R11", "R10", "R12", "R09", "R07", "R08", "R02", "R03",
                 "R15", "R16"]


def decide(rule_results: dict[str, dict], cfg: dict, total_paise: int | None) -> dict:
    active = [r for r in rule_results.values() if not r["skipped"]]
    worst = "pass"
    for r in active:
        if SEV_RANK[r["severity"]] > SEV_RANK[worst]:
            worst = r["severity"]
    driving = [r["rule_id"] for r in active if r["severity"] == worst and worst != "pass"]
    driving.sort(key=lambda rid: LEAD_PRIORITY.index(rid))
    outcome = SEV_TO_OUTCOME[worst]
    auto_off = False
    if not cfg["global"].get("auto", True) and outcome in ("auto_approve", "approve_with_note"):
        outcome, auto_off = "route_for_review", True
    exposure = 0
    if outcome in ("route_for_review", "hold_request_info", "reject"):
        exposure = max([rule_results[r]["exposure_paise"] for r in driving] or [0])
        if not exposure or outcome == "hold_request_info":
            exposure = max(exposure, total_paise or 0)
    split = int(cfg["global"].get("split", 10000) * 100)
    assigned = None
    if outcome == "route_for_review":
        assigned = "manager" if (exposure > split or "R15" in driving or rule_results.get("R15", {}).get("severity") == "review") else "clerk"
    elif outcome == "hold_request_info":
        assigned = "manager" if "R05" in driving else "clerk"
    elif outcome == "reject":
        assigned = "manager" if any(r in driving for r in ("R04", "R06")) else "clerk"
    from .catalogue import CATEGORY_BY_RULE  # noqa: PLC0415
    category = CATEGORY_BY_RULE.get(driving[0]) if driving else None
    if driving and driving[0] == "R07" and outcome == "route_for_review":
        category = "Vendor problem" if rule_results["R07"]["facts"].get("method") == "other_vendor" else "PO problem"
    if driving and driving[0] in ("R01",) and rule_results["R01"]["facts"].get("reason") == "scanned_no_key":
        category = "Needs AI extraction"
    return {"outcome": outcome, "worst": worst, "driving_rule_ids": driving, "exposure_paise": exposure,
            "assigned_to": assigned, "category": category, "auto_approve_off": auto_off}
