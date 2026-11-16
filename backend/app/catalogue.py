"""Rule catalogue (spec 3.4), stage list (spec 2.2), default thresholds (spec 3.3-3.5, mock s7.js),
validation and plain-English sentences for S7."""
from __future__ import annotations

import copy

from .textutil import inr

SEVERITIES = ["pass", "note", "review", "hold", "reject"]
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
SEV_TO_OUTCOME = {
    "pass": "auto_approve",
    "note": "approve_with_note",
    "review": "route_for_review",
    "hold": "hold_request_info",
    "reject": "reject",
}
OUTCOME_LABEL = {
    "auto_approve": "Approved",
    "approve_with_note": "Approved, note",
    "route_for_review": "Needs review",
    "hold_request_info": "On hold",
    "reject": "Rejected",
}
OUTCOME_LONG = {
    "auto_approve": "Auto-approve",
    "approve_with_note": "Approve with note",
    "route_for_review": "Route for review",
    "hold_request_info": "Hold: request info",
    "reject": "Reject",
}
APPROVED_OUTCOMES = ("auto_approve", "approve_with_note")
OPEN_EXCEPTION_OUTCOMES = ("route_for_review", "hold_request_info")

STAGES = [
    {"no": 1, "name": "Ingest", "desc": "Store the file, hash it, detect text or scan"},
    {"no": 2, "name": "Extract", "desc": "Read fields and line items with confidence"},
    {"no": 3, "name": "Normalise and field checks", "desc": "Dates, money, tax, required fields"},
    {"no": 4, "name": "Vendor check", "desc": "Approved vendor? Do the bank details match?"},
    {"no": 5, "name": "Duplicate check", "desc": "Is this an invoice we have seen before?"},
    {"no": 6, "name": "PO match", "desc": "Find the PO and align every line"},
    {"no": 7, "name": "Validation rules", "desc": "Price, quantity, cumulative value, tax, total"},
    {"no": 8, "name": "Decision", "desc": "Worst severity across all rules wins"},
    {"no": 9, "name": "Explain and output", "desc": "Plain-English reasons and drafts"},
]
STAGE_NAME = {s["no"]: s["name"] for s in STAGES}

RULES = [
    {"id": "R01", "name": "Required fields present", "stage": 3, "group": "Fields"},
    {"id": "R02", "name": "Extraction confidence", "stage": 3, "group": "Fields"},
    {"id": "R03", "name": "Invoice date sanity", "stage": 3, "group": "Fields"},
    {"id": "R04", "name": "Vendor approved and active", "stage": 4, "group": "Vendor", "hard": True},
    {"id": "R05", "name": "Bank details match master", "stage": 4, "group": "Vendor", "hard": True},
    {"id": "R06", "name": "Duplicate invoice", "stage": 5, "group": "Duplicate", "hard": True},
    {"id": "R07", "name": "PO resolved", "stage": 6, "group": "Purchase order"},
    {"id": "R08", "name": "PO status and validity", "stage": 6, "group": "Purchase order"},
    {"id": "R09", "name": "Every line maps to the PO", "stage": 6, "group": "Purchase order"},
    {"id": "R10", "name": "Unit price vs PO", "stage": 7, "group": "Numbers", "band": True},
    {"id": "R11", "name": "Quantity vs PO remaining", "stage": 7, "group": "Numbers", "band": True},
    {"id": "R12", "name": "Cumulative billed vs PO value", "stage": 7, "group": "Numbers", "band": True},
    {"id": "R13", "name": "Tax maths", "stage": 7, "group": "Numbers"},
    {"id": "R14", "name": "Total reconciles", "stage": 7, "group": "Numbers"},
    {"id": "R15", "name": "High-value cap", "stage": 7, "group": "Numbers"},
    {"id": "R16", "name": "Currency matches PO", "stage": 7, "group": "Numbers"},
]
RULE_BY_ID = {r["id"]: r for r in RULES}
HARD_STOP_RULES = {"R04", "R05", "R06"}

# Exception categories (S5 filters, S1 "top reasons" chart)
CATEGORY_BY_RULE = {
    "R01": "Missing information", "R02": "Missing information", "R03": "Date problem",
    "R04": "Vendor problem", "R05": "Bank change", "R06": "Duplicate",
    "R07": "Missing information", "R08": "PO problem", "R09": "Quantity or price above PO",
    "R10": "Quantity or price above PO", "R11": "Quantity or price above PO",
    "R12": "Quantity or price above PO", "R13": "Tax or total", "R14": "Tax or total",
    "R15": "High value", "R16": "Currency",
}

BAND0 = {"pass_pct": 0.5, "pass_abs": 50, "note_pct": 2, "note_abs": 5000, "review_pct": 10}

DEFAULT_CONFIG = {
    "rules": {
        "R02": {"ok": 0.90, "min": 0.75},
        "R03": {"days": 180},
        "R06": {"review": 0.60, "reject": 0.85},
        "R07": {"score": 0.90, "gap": 0.20, "ceil": 100000},
        "R09": {"pct": 10},
        "R10": dict(BAND0),
        "R11": {**BAND0, "pass_abs": 0, "note_abs": 0},
        "R12": dict(BAND0),
        "R13": {"pass": 1, "note": 10, "review": 100},
        "R14": {"pass": 1, "note": 10},
        "R15": {"cap": 1000000},
    },
    "enabled": {r["id"]: True for r in RULES},
    "global": {
        "cap": 1000000, "split": 10000, "sample": 10, "sla": 3, "auto": True, "baseline": 9,
        "dateOrder": "Day first", "currency": "₹",
    },
    # Advanced constants from spec 2.3 (shown read-only in S7, editable via API).
    "advanced": {
        "boost_to": 0.92, "ambiguous_date_cap": 0.80, "disagree_cap": 0.60, "fuzzy_vendor": 0.85,
        "dup_weights": {"amount": 0.30, "number": 0.25, "date": 0.15, "po": 0.10, "lines": 0.20},
        "implied_weights": {"desc": 0.35, "price": 0.30, "qty": 0.15, "total": 0.10, "date": 0.10},
        "implied_review_floor": 0.50, "line_fuzzy": 0.80,
    },
}

PARAM_LABELS = {
    "ok": "Fine at or above", "min": "Hold below", "days": "Note when older than (days)",
    "review": "Send to review from", "reject": "Reject from", "score": "Best score needed",
    "gap": "Runner-up gap needed", "ceil": "Invoice ceiling (₹)", "pct": "Review up to (% of invoice)",
    "pass_pct": "Passes silently up to (%)", "pass_abs": "...or up to (₹)", "note_pct": "Note up to (%)",
    "note_abs": "...and no more than (₹)", "review_pct": "Review up to (%)", "pass": "Passes up to (₹)",
    "note": "Note up to (₹)", "cap": "Manager sign-off above (₹)",
}


def default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


def _f(n, d=2) -> str:
    t = f"{float(n):.{d}f}"
    return t.rstrip("0").rstrip(".") if "." in t else t


def _r(rupees) -> str:
    return inr(int(round(float(rupees) * 100)), 0)


def sentence(rule_id: str, cfg: dict) -> str:
    p = cfg["rules"].get(rule_id, {})
    if rule_id in ("R10", "R11", "R12"):
        lab = {"R10": "unit price", "R11": "quantity over what remains", "R12": "cumulative billed value"}[rule_id]
        abs_note = "" if rule_id == "R11" or not p.get("note_abs") else f", and no more than {_r(p['note_abs'])}"
        abs_pass = "" if rule_id == "R11" or not p.get("pass_abs") else f" or {_r(p['pass_abs'])}"
        return (f"Allow a {lab} up to {_f(p['note_pct'])}% above the PO{abs_note}, with a note. "
                f"Up to {_f(p['pass_pct'])}%{abs_pass} passes silently. Up to {_f(p['review_pct'])}% goes "
                f"to review. Above that is rejected.")
    if rule_id == "R01":
        return ("Invoice number, date, vendor, total and currency must all be present. If one is missing "
                "we hold the invoice and ask the vendor.")
    if rule_id == "R02":
        return (f"Key fields need confidence of {_f(p['ok'])} or more. Between {_f(p['min'])} and {_f(p['ok'])} "
                f"we approve with a note. Below {_f(p['min'])} we hold the invoice.")
    if rule_id == "R03":
        return (f"The date cannot be in the future or before the PO date. Dates older than {int(p['days'])} "
                f"days get a note.")
    if rule_id == "R04":
        return ("The vendor must be an approved vendor. Name-only matches go to review, pending vendors are "
                "held, blocked or unknown vendors are rejected.")
    if rule_id == "R05":
        return ("The bank account on the invoice must equal the one on file. Any change, or a note saying "
                "the details changed, puts the invoice on hold.")
    if rule_id == "R06":
        return (f"Reject if the invoice is {_f(p['reject'] * 100, 0)}% or more similar to an earlier one. "
                f"Send to review from {_f(p['review'] * 100, 0)}% up to {_f(p['reject'] * 100, 0)}%.")
    if rule_id == "R07":
        return (f"Use the PO on the invoice. With no PO, infer it only when the best match scores "
                f"{_f(p['score'] * 100, 0)}% or more, beats the runner-up by {_f(p['gap'] * 100, 0)} points "
                f"and the invoice is up to {_r(p['ceil'])}.")
    if rule_id == "R08":
        return ("The PO must be open or partly billed and the invoice date must fall inside its validity "
                "window.")
    if rule_id == "R09":
        return (f"Lines that are not on the PO go to review when they are up to {_f(p['pct'])}% of the "
                f"invoice, and are rejected above that.")
    if rule_id == "R13":
        return (f"GST must equal the taxable value times the rate. Up to {_r(p['pass'])} passes, up to "
                f"{_r(p['note'])} gets a note, up to {_r(p['review'])} goes to review and more is rejected.")
    if rule_id == "R14":
        return (f"Subtotal plus tax must equal the stated total. Up to {_r(p['pass'])} passes, up to "
                f"{_r(p['note'])} gets a note. Above that we reject, or hold if we may have misread.")
    if rule_id == "R15":
        return f"Any invoice above {_r(p['cap'])} needs a manager to sign it off."
    if rule_id == "R16":
        return "The invoice currency must be the same as the PO currency, otherwise it goes to review."
    return ""


def allowed_text(rule_id: str, cfg: dict) -> str | None:
    p = cfg["rules"].get(rule_id, {})
    if rule_id in ("R10", "R12"):
        return (f"Allowed: {_f(p['pass_pct'])}% or {_r(p['pass_abs'])} passes; {_f(p['note_pct'])}% and "
                f"{_r(p['note_abs'])} notes")
    if rule_id == "R11":
        return f"Allowed: {_f(p['pass_pct'])}% passes; {_f(p['note_pct'])}% notes"
    if rule_id in ("R13", "R14"):
        return f"Allowed: {_r(p['pass'])} passes; {_r(p['note'])} notes"
    if rule_id == "R06":
        return f"Review at {_f(p['review'])}, reject at {_f(p['reject'])}"
    if rule_id == "R02":
        return f"Fine at {_f(p['ok'])}, note at {_f(p['min'])}"
    if rule_id == "R15":
        return f"Limit {_r(p['cap'])}"
    if rule_id == "R07":
        return f"Implied match needs {_f(p['score'])} and a gap of {_f(p['gap'])}, up to {_r(p['ceil'])}"
    return None


def validate_config(cfg: dict) -> dict[str, str]:
    """Return {'R10.note_pct': 'message', ...}. Empty dict means valid."""
    errs: dict[str, str] = {}
    rules = cfg.get("rules", {})
    for rid, params in DEFAULT_CONFIG["rules"].items():
        p = rules.get(rid)
        if not isinstance(p, dict):
            errs[rid] = "Missing thresholds."
            continue
        for k in params:
            v = p.get(k)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                errs[f"{rid}.{k}"] = "Enter a number of zero or more."
    if errs:
        return errs
    for rid in ("R10", "R11", "R12"):
        p = rules[rid]
        if p["pass_pct"] > p["note_pct"]:
            errs[f"{rid}.pass_pct"] = "Passes-silently limit cannot be above the note limit."
        if p["note_pct"] > p["review_pct"]:
            errs[f"{rid}.note_pct"] = "The note limit cannot be above the review limit."
        if p["pass_abs"] > p["note_abs"] and p["note_abs"] > 0:
            errs[f"{rid}.pass_abs"] = "Cannot be above the note amount."
    if rules["R02"]["min"] >= rules["R02"]["ok"]:
        errs["R02.min"] = "Hold limit must be below the fine limit."
    if rules["R02"]["ok"] > 1:
        errs["R02.ok"] = "Confidence is between 0 and 1."
    if rules["R06"]["review"] >= rules["R06"]["reject"]:
        errs["R06.review"] = "Review line must be below the reject line."
    if rules["R06"]["reject"] > 1:
        errs["R06.reject"] = "Similarity is between 0 and 1."
    if rules["R07"]["score"] > 1 or rules["R07"]["gap"] > 1:
        errs["R07.score"] = "Scores are between 0 and 1."
    r13 = rules["R13"]
    if not (r13["pass"] <= r13["note"] <= r13["review"]):
        errs["R13.note"] = "Steps must increase: pass, note, review."
    if rules["R14"]["pass"] > rules["R14"]["note"]:
        errs["R14.pass"] = "Passes limit cannot be above the note limit."
    enabled = cfg.get("enabled", {})
    for rid in HARD_STOP_RULES:
        if enabled.get(rid) is False:
            errs[f"enabled.{rid}"] = "Hard-stop rules cannot be switched off."
    g = cfg.get("global", {})
    for k in ("cap", "split", "sample", "sla", "baseline"):
        v = g.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            errs[f"global.{k}"] = "Enter a number of zero or more."
    if g.get("dateOrder") not in ("Day first", "Month first"):
        errs["global.dateOrder"] = "Choose Day first or Month first."
    return errs
