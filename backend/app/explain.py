"""Stage 9: plain-English explanation (spec 3.7) built only from rule facts, vendor drafts, and an
optional LLM polish that is rejected if it introduces any number or ID not in the template."""
from __future__ import annotations

import logging
import re

from . import config
from .catalogue import OUTCOME_LONG, SEV_RANK
from .rules import LEAD_PRIORITY, unit_noun
from .textutil import fmt_date, fmt_qty, inr, inr0

log = logging.getLogger("ledgerlight.explain")

HEAD_PREFIX = {"auto_approve": "Approved", "approve_with_note": "Approved with a note",
               "route_for_review": "Review needed", "hold_request_info": "Hold", "reject": "Reject"}


def _ec1_overbilling(rules: dict, ctx: dict) -> tuple[str, str] | None:
    """Combined R11 + R12 explanation for a split PO (EC1)."""
    r11, r12 = rules.get("R11"), rules.get("R12")
    if not r11 or not r12 or r11["skipped"] or SEV_RANK[r11["severity"]] < SEV_RANK["review"]:
        return None
    rows = [x for x in r11["facts"].get("lines", []) if x["over"] > 0]
    if not rows:
        return None
    r = max(rows, key=lambda x: x["over"])
    po = ctx["po_res"]["po"]
    earlier = [h for h in po.get("history", []) if not h.get("is_current") and h.get("outcome") in ("auto_approve", "approve_with_note")]
    v = ctx["vendor_match"].get("vendor") or {}
    short = v.get("short") or v.get("name") or "The vendor"
    total_billed = r["billed_before"] + r["this_invoice"]
    noun = r["noun"]
    exposure = max(r11["exposure_paise"], r12["exposure_paise"] if not r12["skipped"] else 0)
    n = len(earlier)
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    with_earlier = (f"Together with the {words.get(n, str(n))} earlier invoice{'s' if n != 1 else ''}, " if n else "")
    att = (f"{with_earlier}{short} has now billed for {fmt_qty(total_billed)} {noun}, but only {fmt_qty(r['ordered'])} "
           f"were ordered. This invoice asks for {fmt_qty(r['this_invoice'])} {noun} and only {fmt_qty(r['remaining'])} "
           f"remain on the order. That is {fmt_qty(r['over'])} {noun}, or {inr0(exposure)} including GST, more than agreed.")
    fit = int(round(max(0.0, r["remaining"]) * r["unit_price_paise"] * (1 + (r["tax_rate_pct"] or 0) / 100)))
    nxt = (f"Approve {inr0(fit)} ({fmt_qty(r['remaining'])} {noun}) and ask {short} for a credit note of {inr0(exposure)}. "
           f"Or ask Procurement to increase the PO if the extra {noun} were really delivered.")
    return att, nxt


def build(ctx: dict, rules: dict, decision: dict) -> dict:
    outcome = decision["outcome"]
    driving = decision["driving_rule_ids"]
    non_pass = [r for r in rules.values() if not r["skipped"] and r["severity"] != "pass"]
    non_pass.sort(key=lambda r: (-SEV_RANK[r["severity"]], LEAD_PRIORITY.index(r["rule_id"])))
    lead = rules[driving[0]] if driving else None

    # headline
    if outcome == "auto_approve":
        headline = "Approved: everything checks out and it is safe to pay."
    elif decision.get("auto_approve_off"):
        headline = "Review needed: automatic approval is switched off, so a person must confirm this invoice."
    else:
        headline = f"{HEAD_PREFIX[outcome]}: {lead['headline'] if lead and lead.get('headline') else lead['message'][0].lower() + lead['message'][1:]}"

    # ok list (passed checks, short phrases)
    ok = []
    for rid in ("R04", "R07", "R10", "R11", "R12", "R09", "R13", "R14", "R05", "R06", "R03"):
        r = rules.get(rid)
        if r and not r["skipped"] and r["severity"] == "pass" and r.get("ok"):
            if rid == "R12" and any(x.startswith("Quantities") for x in ok):
                continue
            ok.append(r["ok"])

    # attention list
    attention, used = [], set()
    ec1 = _ec1_overbilling(rules, ctx) if lead and lead["rule_id"] in ("R11", "R12") else None
    if lead and lead["rule_id"] == "R06" and rules.get("R08") and rules["R08"]["severity"] == "reject":
        # EC2: lead with the duplicate; the fully billed PO is the same story, told once.
        attention.append(lead["attention"] + " Also, that PO is already fully billed.")
        used.update({"R06", "R08", "R11", "R12"})
    for r in non_pass:
        if r["rule_id"] in used:
            continue
        if ec1 and r["rule_id"] in ("R11", "R12"):
            attention.append(ec1[0])
            used.update({"R11", "R12"})
            continue
        if r["rule_id"] == "R12" and r["severity"] == "note" and rules.get("R10", {}).get("severity") == "note":
            continue  # the R10 note already tells the same over-billing in friendlier words
        attention.append(r["attention"])
        used.add(r["rule_id"])
    # EC3 style notes: extraction confidence and date ambiguity
    c = ctx.get("canon") or {}
    boosted = [f for f in (c.get("fields") or {}).values() if f.get("boosted")]
    if rules.get("R02") and rules["R02"]["severity"] == "note":
        attention = [a for a in attention if a != rules["R02"]["attention"]]
        if boosted and c.get("subtotal_paise") is not None:
            attention.append(f"The scan was blurry. We checked the total by adding up the lines and tax "
                             f"({inr0(c['subtotal_paise'])} plus {inr0(c['tax_paise'])} equals {inr0(c['total_paise'])}), "
                             f"so we trust it.")
        dfield = (c.get("fields") or {}).get("invoice_date") or {}
        if dfield.get("ambiguous") and c.get("invoice_date"):
            attention.append(f'The date "{dfield.get("raw_text") or dfield.get("value")}" was read as '
                             f"{fmt_date(c['invoice_date']).replace(' Nov ', ' November ')}.")
        if not boosted and not dfield.get("ambiguous"):
            attention.append(rules["R02"]["attention"])

    # next step
    if ec1 and lead and lead["rule_id"] in ("R11", "R12"):
        next_step = ec1[1]
    elif lead and lead.get("next_step"):
        next_step = lead["next_step"]
    elif outcome == "auto_approve":
        next_step = "None needed. The invoice is in the payment queue."
    elif outcome == "approve_with_note":
        next_step = "None needed. The invoice is in the payment queue with the note attached."
    elif outcome == "route_for_review":
        next_step = "Review the evidence and accept or override."
    elif outcome == "hold_request_info":
        next_step = "Chase the vendor for the missing information. The invoice re-runs when it arrives."
    else:
        next_step = "Send the return notice. Nothing is paid."
    if outcome == "reject" and lead and lead["rule_id"] == "R06":
        alternative = "If this is genuinely a different invoice, a manager can overturn this decision."
    else:
        alternative = lead.get("alternative") if lead else None

    # confidence note
    fields = c.get("fields") or {}
    confs = [f["effective_confidence"] for f in fields.values() if f.get("value") is not None]
    if confs:
        low = min(confs)
        if boosted:
            confidence_note = (f"{len(boosted)} field{'s were' if len(boosted) > 1 else ' was'} below 0.90 before the "
                               f"arithmetic check. The total is trusted because lines plus tax equal it.")
        elif low < 0.9:
            confidence_note = f"Lowest field confidence is {low:.2f}. Check the amber fields."
        else:
            confidence_note = f"All fields read at {low:.2f} or higher."
    else:
        confidence_note = "No fields could be read from this document."

    main_reason = (attention[0] if attention and outcome != "auto_approve" else
                   ("All 16 checks passed." + (f" Prices, quantities, GST and total match {ctx['po_res']['po']['id']}."
                                               if ctx.get("po_res", {}).get("po") else "")))
    short_reason = _short_reason(lead, decision, rules, ctx)
    return {"headline": headline, "ok": ok, "attention": attention, "next_step": next_step,
            "alternative_step": alternative, "confidence_note": confidence_note, "main_reason": main_reason,
            "short_reason": short_reason, "polished": False, "decision_label": OUTCOME_LONG[outcome]}


def _short_reason(lead, decision, rules, ctx) -> str:
    """One line for tables (S1 'Main reason', S5 rows)."""
    if decision["outcome"] == "auto_approve":
        po = ctx.get("po_res", {}).get("po")
        return "All 16 checks passed" + (f". Prices, quantities, GST and total match {po['id']}." if po else ".")
    if not lead:
        return decision.get("category") or ""
    rid = lead["rule_id"]
    f = lead["facts"]
    if rid == "R06" and f.get("closest"):
        cl = f["closest"]
        tail = f", already paid on {fmt_date(cl['paid_at'])}" if cl.get("paid_at") else ""
        return f"Same invoice as {cl.get('invoice_no')}{tail}."
    if rid in ("R11", "R12") and rules.get("R11") and rules["R11"]["facts"].get("lines"):
        rows = [x for x in rules["R11"]["facts"]["lines"] if x["over"] > 0]
        if rows:
            r = max(rows, key=lambda x: x["over"])
            exp = decision["exposure_paise"]
            return f"Would bill {fmt_qty(r['over'])} more {r['noun']} than were ordered ({inr0(exp)} with GST)."
    if rid == "R13":
        return f"GST on the invoice is {inr0(abs(f['diff_paise']))} {'too low' if f['diff_paise'] < 0 else 'too high'}. It should be {inr0(f['expected_paise'])}."
    if rid == "R05":
        return "Bank account on the invoice differs from the one on file."
    if rid == "R07" and lead["severity"] == "note":
        return f"PO number was missing. Matched to {f['po_id']} with {f['score'] * 100:.0f}% confidence."
    if rid in ("R10", "R12") and lead["severity"] == "note":
        if rid == "R12":
            return f"Billed {abs(f['delta_pct']):.1f}% above the PO ({inr0(f['delta_paise'])}), inside the allowed 2%."
        rows = f.get("lines") or []
        if rows:
            r = max(rows, key=lambda x: abs(x["delta_paise"]))
            return f"Billed {abs(r['delta_pct']):.1f}% above the PO ({inr0(r['delta_paise'])}), inside the allowed 2%."
    if rid == "R01":
        return "Scanned invoice needs AI extraction; set ANTHROPIC_API_KEY or GROQ_API_KEY." if lead["facts"].get("reason") == "scanned_no_key" else lead["message"]
    return lead["message"]


# ------------------------------------------------------------------ drafts

def drafts(ctx: dict, rules: dict, decision: dict, expl: dict) -> list[dict]:
    out = []
    c = ctx.get("canon") or {}
    v = (ctx.get("vendor_match") or {}).get("vendor") or {}
    short = v.get("short") or v.get("name") or "vendor"
    to = v.get("contact_email") or f"accounts@{re.sub(r'[^a-z]', '', short.lower()) or 'vendor'}.example"
    inv_no = c.get("invoice_no") or "(no number)"
    po = (ctx.get("po_res") or {}).get("po")
    po_id = po["id"] if po else "(no PO)"
    total = c.get("total_paise")
    outcome = decision["outcome"]
    lead = decision["driving_rule_ids"][0] if decision["driving_rule_ids"] else None
    sign = "\n\nRegards,\nAccounts Payable, " + config.BUYER["name"]
    if outcome == "hold_request_info" and lead == "R05":
        f = rules["R05"]["facts"]
        out.append({"kind": "verify", "title": "Drafted vendor verification request", "to": to,
                    "subject": f"Please confirm change of bank details (invoice {inv_no})",
                    "body": (f"Hello {short} accounts team,\n\nInvoice {inv_no} dated {fmt_date(c.get('invoice_date'))} "
                             f"({po_id}, {inr(total)}) asks us to pay {f.get('invoice_bank') or 'a new bank'}, account "
                             f"{f.get('invoice_account')}.\nOur records show {f.get('master_bank')}, account "
                             f"{f.get('master_account')}.\n\nBefore we can release payment, please send:\n1. A written "
                             f"request on company letterhead, signed by an authorised person.\n2. A bank letter or "
                             f"cancelled cheque for the new account.\n\nWe will also call you on the number held in our "
                             f"vendor file to confirm the change. No payment will be made to the new account until this "
                             f"is complete.\n\nThank you,\nAccounts Payable, {config.BUYER['name']}")})
        out.append({"kind": "checklist", "title": "Verification checklist (manager releases the hold)",
                    "items": [f"Called {short} on the number in our vendor master ({v.get('contact_phone') or 'on file'}), "
                              "not the number on the invoice",
                              "Written change request on company letterhead received",
                              "A second person confirmed the new details"]})
    elif outcome == "reject" and lead == "R06":
        cl = rules["R06"]["facts"].get("closest") or {}
        paid = f", which we approved on {fmt_date(cl.get('decided_at'))} and paid on {fmt_date(cl.get('paid_at'))}" if cl.get("paid_at") else ""
        out.append({"kind": "return", "title": "Drafted reply to vendor", "to": to,
                    "subject": f"Invoice {inv_no} was already {'paid' if cl.get('paid_at') else 'received'}",
                    "body": (f"Hello {short} accounts team,\n\nThank you for your message. Invoice {inv_no} "
                             f"({inr(total)}, dated {fmt_date(c.get('invoice_date'))}, {po_id}) is the same invoice as "
                             f"{cl.get('invoice_no')}{paid}.\n\nNo further payment is due for this invoice. If you believe "
                             f"this is a different invoice, please reply with the invoice number, service dates and the "
                             f"PO it relates to." + sign)})
    elif outcome == "reject" and lead == "R13":
        f = rules["R13"]["facts"]
        rate = "/".join(f"{r:g}%" for r in f["rates"])
        out.append({"kind": "return", "title": "Drafted return notice", "to": to,
                    "subject": f"Invoice {inv_no} needs a corrected GST amount",
                    "body": (f"Hello {short} billing team,\n\nInvoice {inv_no} ({po_id}) shows GST of {inr(f['shown_paise'])}. "
                             f"At {rate} of the taxable value of {inr(f['taxable_paise'])} the GST should be "
                             f"{inr(f['expected_paise'])}, so the total should be {inr((c.get('subtotal_paise') or 0) + f['expected_paise'])}."
                             f"\n\nPlease send a corrected invoice. We cannot pay the current one because the GST must be "
                             f"right for input credit." + sign)})
    elif outcome == "route_for_review" and lead in ("R11", "R12") and po:
        ec1 = _ec1_overbilling(rules, ctx)
        exp = decision["exposure_paise"]
        earlier = [h["invoice_no"] for h in po.get("history", []) if h.get("outcome") in ("auto_approve", "approve_with_note")]
        rows = [x for x in rules["R11"]["facts"].get("lines", []) if x["over"] > 0] if rules.get("R11") else []
        body_mid = ""
        if rows:
            r = max(rows, key=lambda x: x["over"])
            fit = int(round(r["remaining"] * r["unit_price_paise"] * (1 + (r["tax_rate_pct"] or 0) / 100)))
            body_mid = (f"With invoices {', '.join(earlier + [inv_no])} you have billed "
                        f"{fmt_qty(r['billed_before'] + r['this_invoice'])} {r['noun']} against {po_id}, which allows "
                        f"{fmt_qty(r['ordered'])}.\n\nWe will pay {inv_no} for the {fmt_qty(r['remaining'])} {r['noun']} "
                        f"that remain on the order ({inr(fit)} with GST). Please send a credit note of {inr(exp)} for the "
                        f"extra {fmt_qty(r['over'])} {r['noun']}, or tell us if a PO change was agreed.")
        elif ec1:
            body_mid = ec1[0]
        out.append({"kind": "credit", "title": "Drafted credit note request", "to": to,
                    "subject": f"Credit note request for invoice {inv_no} ({po_id})",
                    "body": f"Hello {short} accounts team,\n\n{body_mid}" + sign})
    elif outcome == "hold_request_info":
        out.append({"kind": "info", "title": "Drafted message to vendor", "to": to,
                    "subject": f"Information needed for invoice {inv_no}",
                    "body": (f"Hello,\n\nWe could not process invoice {inv_no} yet: "
                             f"{expl['headline'].split(':', 1)[-1].strip().rstrip('.')}.\n\nPlease reply with a corrected or "
                             f"clearer copy. We will re-check it as soon as it arrives." + sign)})
    elif outcome == "reject":
        out.append({"kind": "return", "title": "Drafted return notice", "to": to,
                    "subject": f"Invoice {inv_no} cannot be paid as sent",
                    "body": (f"Hello,\n\nInvoice {inv_no} cannot be paid as it stands: "
                             f"{expl['headline'].split(':', 1)[-1].strip().rstrip('.')}.\n\nPlease reissue the invoice or "
                             f"reply if you believe this is wrong." + sign)})
    return out


# ------------------------------------------------------------------ LLM polish (fact-checked)

TOKEN_RE = re.compile(r"[A-Z]{1,5}[-/][A-Z0-9][A-Z0-9/\-]*|\d[\d,]*(?:\.\d+)?")


def _tokens(text: str) -> set[str]:
    out = set()
    for t in TOKEN_RE.findall(text or ""):
        t = t.rstrip(".,")
        if re.fullmatch(r"[\d,]+(?:\.\d+)?", t):
            t = t.replace(",", "")
            if "." in t:
                t = t.rstrip("0").rstrip(".")
        out.add(t)
    return out


def fact_check(original: dict, polished: dict) -> bool:
    """Every number and ID in the polished text must already exist in the template text."""
    allowed = _tokens(" ".join([original["headline"], original["next_step"], *original["attention"]]))
    got = _tokens(" ".join([polished["headline"], polished["next_step"], *polished["attention"]]))
    return got <= allowed


def maybe_polish(expl: dict, enabled: bool) -> tuple[dict, str]:
    if not enabled or not config.llm_available():
        return expl, "template (no AI key)" if not config.llm_available() else "template"
    try:
        from . import extract_llm  # noqa: PLC0415
        p = extract_llm.polish(expl["headline"], expl["attention"], expl["next_step"])
    except Exception as e:  # any failure falls back to the template text
        log.warning("explanation polish failed: %s", type(e).__name__)
        return expl, "template (AI polish failed)"
    if not fact_check(expl, p):
        return expl, "template (AI wording changed a number, so it was discarded)"
    out = dict(expl)
    out.update({"headline": p["headline"], "attention": p["attention"], "next_step": p["next_step"], "polished": True,
                "template": {"headline": expl["headline"], "attention": expl["attention"], "next_step": expl["next_step"]}})
    return out, "AI-polished, numbers checked"


def unit_word(desc, uom, n=2):
    return unit_noun(desc, uom, n)
