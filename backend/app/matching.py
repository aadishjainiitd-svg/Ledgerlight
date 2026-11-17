"""Stages 4 to 6: vendor match, duplicate scoring, PO resolution, line alignment and the cumulative
position of each PO (spec 2.3). Scoring functions are pure; loaders read SQLite."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import date

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from . import db
from .catalogue import APPROVED_OUTCOMES, OPEN_EXCEPTION_OUTCOMES
from .textutil import (canonical_invoice_no, digits_only, invoice_prefix, norm_desc, po_key_of_id, po_keys,
                       serial_token, sig_tokens, to_date)

# ------------------------------------------------------------------ vendor


def _norm_name(s: str | None) -> str:
    s = (s or "").lower().replace("&", " and ")
    for w in ("private limited", "pvt. ltd.", "pvt ltd", "pvt. ltd", "limited", "ltd.", "ltd", "llp", "inc"):
        s = s.replace(w, " ")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


# Character pairs that scanners and vision models commonly confuse in printed IDs.
OCR_CONFUSABLE = {frozenset(p) for p in ("0O", "0G", "0D", "0Q", "1I", "1L", "5S", "8B", "2Z", "6G")}


def gstin_one_char_misread(read: str | None, master: str | None) -> dict | None:
    """The read GSTIN differs from the master in exactly one position, by an OCR-confusable pair."""
    a, b = (read or "").upper(), (master or "").upper()
    if len(a) != 15 or len(b) != 15:
        return None
    diffs = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diffs) == 1 and frozenset(diffs[0][1:]) in OCR_CONFUSABLE:
        i, x, y = diffs[0]
        return {"position": i + 1, "read": x, "master": y}
    return None


def match_vendor(vendors: list[dict], name: str | None, gstin: str | None, fuzzy_min: float = 0.85,
                 scanned: bool = False) -> dict:
    """Match order: exact GSTIN (decisive), exact normalised name or alias, fuzzy token-set >= 0.85.

    On a scanned document only, an exact name match whose GSTIN is one OCR-confusable character away from the
    master's is reported as a likely misread (gstin_misread) instead of a conflict."""
    res = {"vendor": None, "method": "none", "score": 0.0, "gstin_conflict": False, "gstin_misread": None,
           "candidates": []}
    if gstin:
        for v in vendors:
            if v.get("gstin") and v["gstin"].upper() == gstin.upper():
                return {**res, "vendor": v, "method": "gstin", "score": 1.0}
    nn = _norm_name(name)
    if not nn:
        return res
    for v in vendors:
        names = [v["name"], v.get("short") or ""] + list(v.get("aliases") or [])
        if any(_norm_name(x) == nn for x in names if x):
            conflict = bool(gstin and v.get("gstin") and gstin.upper() != v["gstin"].upper())
            misread = gstin_one_char_misread(gstin, v.get("gstin")) if conflict and scanned else None
            return {**res, "vendor": v, "method": "name", "score": 1.0,
                    "gstin_conflict": conflict and not misread, "gstin_misread": misread}
    scored = []
    for v in vendors:
        names = [v["name"]] + list(v.get("aliases") or [])
        s = max(fuzz.token_set_ratio(nn, _norm_name(x)) for x in names if x) / 100.0
        scored.append((s, v))
    scored.sort(key=lambda t: -t[0])
    res["candidates"] = [{"vendor_id": v["id"], "name": v["name"], "score": round(s, 3)} for s, v in scored[:3]]
    if scored and scored[0][0] >= fuzzy_min:
        s, v = scored[0]
        return {**res, "vendor": v, "method": "fuzzy", "score": round(s, 3),
                "gstin_conflict": bool(gstin and v.get("gstin") and gstin != v["gstin"])}
    return res


def recent_siblings(con, *, vendor_id: str | None, po_id: str | None, invoice_id: str, invoice_date,
                    days: int = 7) -> list[dict]:
    """Other invoices from the same vendor on the same PO, dated within `days`, that were not rejected."""
    d0 = to_date(invoice_date)
    if not vendor_id or not po_id or not d0:
        return []
    out = []
    q = ("SELECT i.id, i.invoice_no_raw, i.invoice_date, i.total_paise, d.outcome FROM invoices i "
         "JOIN decisions d ON d.id = i.current_decision_id "
         "WHERE i.vendor_id = ? AND i.po_id = ? AND i.id != ? AND d.outcome != 'reject' AND i.is_synthetic = 0")
    for r in con.execute(q, (vendor_id, po_id, invoice_id)):
        d1 = to_date(r["invoice_date"])
        if d1 and abs((d1 - d0).days) <= days and r["total_paise"]:
            out.append({"invoice_no": r["invoice_no_raw"], "total_paise": r["total_paise"], "days_apart": abs((d1 - d0).days),
                        "outcome": r["outcome"]})
    return out


def load_vendors(con: sqlite3.Connection) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM vendors ORDER BY id"):
        d = dict(r)
        d["aliases"] = db.loads(d.get("aliases"), [])
        out.append(d)
    return out


def _bank_key(name: str | None) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"\b(bank|ltd|limited|co|operative|the)\b", "", (name or "").lower()))


def bank_compare(inv_bank: dict, notice: bool, vendor: dict | None, entries: list[dict] | None = None,
                 notice_date: date | None = None) -> dict:
    """Compare EVERY bank entry printed on the invoice with the vendor master. Any account or IFSC that differs is a
    mismatch. A bank that is named but whose account cannot be read, and that is not the bank on file, is
    'unreadable' (held, never treated as 'no bank details')."""
    entries = [e for e in (entries or []) if e.get("name") or e.get("account") or e.get("ifsc")] or [inv_bank]
    accts = [digits_only(e.get("account")) for e in entries if digits_only(e.get("account"))]
    ifscs = [(e.get("ifsc") or "").upper() for e in entries if e.get("ifsc")]
    names = [e.get("name") for e in entries if e.get("name")]
    if not accts and not ifscs and not notice:
        if names and vendor and any(_bank_key(n) != _bank_key(vendor.get("bank_name")) for n in names):
            other = next(n for n in names if _bank_key(n) != _bank_key(vendor.get("bank_name")))
            return {"status": "unreadable", "match": False, "bank_named": other}
        return {"status": "not_applicable", "match": None}
    if not vendor:
        return {"status": "no_vendor", "match": None}
    m_acct = digits_only(vendor.get("bank_account_no"))
    m_ifsc = (vendor.get("bank_ifsc") or "").upper()
    bad = [e for e in entries if (digits_only(e.get("account")) and digits_only(e.get("account")) != m_acct)
           or (e.get("ifsc") and e["ifsc"].upper() != m_ifsc)]
    if bad:
        return {"status": "mismatch", "match": False, "account_matches": False, "ifsc_matches": False,
                "offending": bad[0], "entries_seen": len(entries)}
    acct = accts[0] if accts else ""
    acct_ok, ifsc_ok = True, True
    if acct_ok and ifsc_ok and not notice:
        return {"status": "match", "match": True}
    verified_on = to_date(vendor.get("bank_changed_at"))
    if acct_ok and ifsc_ok and acct and vendor.get("bank_verified_by") and verified_on and \
            (notice_date is None or verified_on >= notice_date):
        # The change notice describes an account that a manager verified and recorded in the master AFTER the
        # change took effect. An older verification cannot cover a newer notice.
        return {"status": "match_verified_change", "match": True, "verified_by": vendor["bank_verified_by"],
                "changed_at": vendor["bank_changed_at"]}
    return {"status": "mismatch" if not (acct_ok and ifsc_ok) else "notice_only", "match": False,
            "account_matches": acct_ok, "ifsc_matches": ifsc_ok}


# ------------------------------------------------------------------ duplicates

def fingerprint(lines: list[dict]) -> Counter:
    return Counter((l.get("desc_norm") or norm_desc(l.get("description")), round(float(l.get("qty") or 0), 3),
                    int(l.get("pretax_unit_paise") or l.get("unit_price_paise") or 0)) for l in lines)


RECURRING_RE = re.compile(r"\b(rent|rental|lease|retainer|subscription|licen[cs]e|amc|maintenance|monthly|per month|"
                          r"service charges?|fees? for|hosting|support plan)\b", re.I)


def _looks_recurring(lines: list[dict]) -> bool:
    """Every line reads like a recurring service, so an identical bill a month later is expected."""
    descs = [l.get("description") or "" for l in lines]
    return bool(descs) and all(RECURRING_RE.search(d) for d in descs)


def duplicate_score(cur: dict, prior: dict, weights: dict) -> dict:
    """cur/prior: {invoice_no, invoice_date (date), total_paise, po_id, lines, prefix, serial}.
    Returns score and per-signal breakdown (spec 2.3 table)."""
    sig = {}
    ta, tb = cur.get("total_paise"), prior.get("total_paise")
    if ta is not None and tb is not None:
        diff = abs(ta - tb)
        sig["amount"] = 1.0 if diff <= 100 else (0.5 if tb and diff <= 0.005 * abs(tb) else 0.0)
    else:
        sig["amount"] = 0.0
    ca, cb = canonical_invoice_no(cur.get("invoice_no")) or "", canonical_invoice_no(prior.get("invoice_no")) or ""
    da, dbb = to_date(cur.get("invoice_date")), to_date(prior.get("invoice_date"))
    sa = serial_token(cur.get("invoice_no"), da.year if da else None)
    sb = serial_token(prior.get("invoice_no"), dbb.year if dbb else None)
    pa, pb = invoice_prefix(cur.get("invoice_no")), invoice_prefix(prior.get("invoice_no"))
    if sa and sa == sb:
        sig["number"] = 1.0 if pa == pb else 0.8
    elif ca and cb:
        sig["number"] = round(Levenshtein.normalized_similarity(ca, cb) * 0.7, 3)
    else:
        sig["number"] = 0.0
    if da and dbb:
        dd = abs((da - dbb).days)
        sig["date"] = 1.0 if dd == 0 else (0.5 if dd <= 14 else 0.0)
    else:
        sig["date"] = 0.0
    sig["po"] = 1.0 if cur.get("po_id") and cur.get("po_id") == prior.get("po_id") else 0.0
    fa, fb = fingerprint(cur.get("lines") or []), fingerprint(prior.get("lines") or [])
    if fa and fb:
        inter = sum((fa & fb).values())
        sig["lines"] = round(inter / max(sum(fa.values()), sum(fb.values())), 3)
    else:
        sig["lines"] = 0.0
    guard = False
    # Recurring-charge guard: different serials roughly a billing cycle apart are not penalised toward duplicate on
    # number and date. It does not apply when the same goods come back line for line (a re-bill of one delivery),
    # only when the lines differ or are a recurring service such as rent or a monthly retainer.
    same_goods = sig["lines"] >= 0.9 and not _looks_recurring(cur.get("lines") or [])
    if sa and sb and sa != sb and da and dbb and abs((da - dbb).days) >= 25 and not same_goods:
        guard = True
        sig["number"] = 0.0
        sig["date"] = 0.0
    score = sum(weights[k] * sig[k] for k in weights)
    return {"score": round(min(1.0, score), 3), "signals": sig, "recurring_guard": guard,
            "serials": [sa, sb], "prefixes": [pa, pb]}


def load_prior_invoices(con, vendor_id: str, exclude_invoice_id: str) -> list[dict]:
    out = []
    q = ("SELECT i.*, d.outcome AS outcome, d.created_at AS decided_at FROM invoices i "
         "LEFT JOIN decisions d ON d.id = i.current_decision_id "
         "WHERE i.vendor_id = ? AND i.id != ? AND i.current_decision_id IS NOT NULL")
    for r in con.execute(q, (vendor_id, exclude_invoice_id)):
        d = dict(r)
        d["lines"] = [dict(x) for x in con.execute(
            "SELECT description_raw AS description, description_norm AS desc_norm, qty, unit_price_paise, "
            "amount_paise, pretax_amount_paise FROM line_items WHERE invoice_id=? ORDER BY line_no", (d["id"],))]
        for l in d["lines"]:
            if l.get("qty") and l.get("pretax_amount_paise") is not None:
                l["pretax_unit_paise"] = int(round(l["pretax_amount_paise"] / l["qty"]))
        d["invoice_no"] = d["invoice_no_raw"]
        out.append(d)
    return out


def duplicate_check(con, *, vendor_id: str | None, invoice_id: str, sha: str, cur: dict, cfg: dict) -> dict:
    weights = cfg["advanced"]["dup_weights"]
    res = {"score": 0.0, "exact": None, "closest": None, "signals": None, "compared": 0}
    hash_hit = con.execute("SELECT i.id, i.invoice_no_raw, i.total_paise, i.invoice_date, i.vendor_id FROM invoices i "
                           "WHERE i.file_sha256 = ? AND i.id != ? AND i.current_decision_id IS NOT NULL "
                           "ORDER BY i.created_at LIMIT 1", (sha, invoice_id)).fetchone()
    if hash_hit:
        h = dict(hash_hit)
        dec = con.execute("SELECT d.outcome, d.created_at FROM invoices i JOIN decisions d ON d.id=i.current_decision_id "
                          "WHERE i.id=?", (h["id"],)).fetchone()
        res.update({"score": 1.0, "exact": "file", "closest": {
            "id": h["id"], "invoice_no": h["invoice_no_raw"], "total_paise": h["total_paise"],
            "invoice_date": h["invoice_date"], "po_id": None, "outcome": dec["outcome"] if dec else None,
            "decided_at": dec["created_at"] if dec else None, "paid_at": None, "lines": []}})
    if not vendor_id:
        return res
    priors = load_prior_invoices(con, vendor_id, invoice_id)
    res["compared"] = len(priors)
    if res["exact"]:
        return res
    canon = canonical_invoice_no(cur.get("invoice_no"))
    for p in priors:
        if canon and p.get("invoice_no_canonical") == canon and p.get("outcome") != "reject":
            res.update({"score": 1.0, "exact": "number", "closest": _closest(p),
                        "signals": duplicate_score(cur, p, weights)["signals"]})
            return res
    best = None
    for p in priors:
        if p.get("outcome") == "reject":
            continue
        s = duplicate_score(cur, p, weights)
        if best is None or s["score"] > best[0]["score"]:
            best = (s, p)
    if best:
        s, p = best
        res.update({"score": s["score"], "closest": _closest(p), "signals": s["signals"],
                    "recurring_guard": s["recurring_guard"], "serials": s["serials"], "prefixes": s["prefixes"]})
    return res


def _closest(p: dict) -> dict:
    return {"id": p["id"], "invoice_no": p.get("invoice_no_raw") or p.get("invoice_no"),
            "total_paise": p.get("total_paise"), "invoice_date": p.get("invoice_date"), "po_id": p.get("po_id"),
            "outcome": p.get("outcome"), "decided_at": p.get("decided_at"), "paid_at": p.get("paid_at"),
            "is_synthetic": bool(p.get("is_synthetic")),
            "lines": [{"description": l.get("description"), "qty": l.get("qty"),
                       "unit_price_paise": l.get("pretax_unit_paise") or l.get("unit_price_paise")}
                      for l in p.get("lines", [])]}


# ------------------------------------------------------------------ PO positions

def po_position(con, po_id: str, exclude_invoice_id: str | None = None) -> dict | None:
    po = con.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
    if not po:
        return None
    po = dict(po)
    lines = [dict(r) for r in con.execute("SELECT * FROM po_lines WHERE po_id=? ORDER BY line_no", (po_id,))]
    by_id = {l["id"]: l for l in lines}
    for l in lines:
        l["billed_qty"] = float(l.get("opening_billed_qty") or 0)
        l["billed_value_paise"] = int(round(l["billed_qty"] * l["unit_price_paise"]))
        l["pending_qty"] = 0.0
        l["pending_value_paise"] = 0
        l["pending_from"] = []        # invoice numbers waiting in review/hold that claim this line
        l["over_billed_paise"] = 0    # sum billed above the PO price by earlier invoices on this line
        l["over_from"] = []
    history = []
    q = ("SELECT i.id, i.invoice_no_raw, i.invoice_date, i.total_paise, i.subtotal_paise, i.paid_at, i.is_synthetic, "
         "i.current_run_id, d.outcome, d.made_by FROM invoices i LEFT JOIN decisions d ON d.id = i.current_decision_id "
         "WHERE i.po_id = ? ORDER BY i.invoice_date, i.created_at")
    for inv in con.execute(q, (po_id,)):
        inv = dict(inv)
        excluded = inv["id"] == exclude_invoice_id
        history.append({"invoice_id": inv["id"], "invoice_no": inv["invoice_no_raw"], "invoice_date": inv["invoice_date"],
                        "total_paise": inv["total_paise"], "subtotal_paise": inv["subtotal_paise"],
                        "outcome": inv["outcome"], "paid_at": inv["paid_at"], "is_current": excluded,
                        "run_id": inv["current_run_id"]})
        if excluded or inv["is_synthetic"] or inv["outcome"] is None:
            continue
        bucket = "billed" if inv["outcome"] in APPROVED_OUTCOMES else (
            "pending" if inv["outcome"] in OPEN_EXCEPTION_OUTCOMES else None)
        if not bucket:
            continue
        for li in con.execute("SELECT alloc FROM line_items WHERE invoice_id=?", (inv["id"],)):
            for a in db.loads(li["alloc"], []):
                pl = by_id.get(a.get("po_line_id"))
                if not pl:
                    continue
                pl[f"{bucket}_qty"] += float(a.get("qty") or 0)
                pl[f"{bucket}_value_paise"] += int(a.get("amount_paise") or 0)
                if bucket == "pending" and inv["invoice_no_raw"] and inv["invoice_no_raw"] not in pl["pending_from"]:
                    pl["pending_from"].append(inv["invoice_no_raw"])
                # Earlier invoices billed above the PO price on this line (small "noted" overcharges add up).
                q_al, amt = float(a.get("qty") or 0), int(a.get("amount_paise") or 0)
                exp = int(round(q_al * pl["unit_price_paise"]))
                if q_al > 0 and exp and amt - exp > 0.005 * exp:
                    pl["over_billed_paise"] += amt - exp
                    if inv["invoice_no_raw"] and inv["invoice_no_raw"] not in pl["over_from"]:
                        pl["over_from"].append(inv["invoice_no_raw"])
    subtotal = sum(int(round(l["ordered_qty"] * l["unit_price_paise"])) for l in lines)
    tax = sum(int(round(l["ordered_qty"] * l["unit_price_paise"] * (l["tax_rate_pct"] or 0) / 100)) for l in lines)
    billed = sum(l["billed_value_paise"] for l in lines)
    pending = sum(l["pending_value_paise"] for l in lines)
    for l in lines:
        l["remaining_qty"] = round(l["ordered_qty"] - l["billed_qty"], 4)
        l["line_value_paise"] = int(round(l["ordered_qty"] * l["unit_price_paise"]))
    if po.get("status_override") in ("closed", "cancelled"):
        status = po["status_override"]
    elif subtotal and billed >= subtotal:
        status = "fully_billed"
    elif billed > 0:
        status = "partially_billed"
    else:
        status = "open"
    return {**po, "lines": lines, "subtotal_paise": subtotal, "tax_paise": tax, "total_paise": subtotal + tax,
            "billed_subtotal_paise": billed, "pending_subtotal_paise": pending,
            "remaining_subtotal_paise": subtotal - billed, "status": status,
            "pct_billed": round(100.0 * billed / subtotal, 2) if subtotal else 0.0, "history": history}


# ------------------------------------------------------------------ PO resolution

def find_po_by_reference(con, texts: list[str | None]) -> tuple[dict | None, str | None]:
    pos = [dict(r) for r in con.execute("SELECT id, vendor_id FROM purchase_orders")]
    keymap = {}
    for p in pos:
        k = po_key_of_id(p["id"])
        if k:
            keymap[k] = p
    for t in texts:
        if not t:
            continue
        for k in po_keys(t):
            if k in keymap:
                return keymap[k], t
    return None, None


def _desc_sim(a: str, b: str) -> float:
    s = fuzz.token_set_ratio(norm_desc(a), norm_desc(b)) / 100.0
    return s if s >= 0.5 else 0.0  # below 0.5 is noise, not a match


def implied_score(lines: list[dict], pretax_total: int | None, inv_date: date | None, pos: dict, weights: dict) -> dict:
    pls = pos["lines"]
    if not lines or not pls:
        parts = {"desc": 0.0, "price": 0.0, "qty": 0.0, "total": 0.0, "date": 0.0}
    else:
        desc, price, qty = [], [], []
        for l in lines:
            best = max(pls, key=lambda pl: _desc_sim(l["description"], pl["description"]))
            desc.append(_desc_sim(l["description"], best["description"]))
            up = l.get("pretax_unit_paise")
            price.append(1.0 if up and any(abs(up - pl["unit_price_paise"]) <= 0.02 * pl["unit_price_paise"] for pl in pls) else 0.0)
            bq = best if desc[-1] > 0 else None
            qty.append(1.0 if bq and l.get("qty") is not None and l["qty"] <= bq["remaining_qty"] + 1e-9 else 0.0)
        parts = {"desc": sum(desc) / len(desc), "price": sum(price) / len(price), "qty": sum(qty) / len(qty)}
        parts["total"] = 1.0 if pretax_total is not None and pretax_total <= pos["remaining_subtotal_paise"] else 0.0
        idate, vto = to_date(pos.get("issue_date")), to_date(pos.get("valid_to"))
        parts["date"] = 1.0 if inv_date and idate and vto and idate <= inv_date <= vto else 0.0
    score = sum(weights[k] * parts[k] for k in weights)
    return {"po_id": pos["id"], "score": round(score, 3), "parts": {k: round(v, 3) for k, v in parts.items()}}


def resolve_po(con, canon: dict, vendor: dict | None, cfg: dict, invoice_id: str) -> dict:
    texts = [canon.get("po_reference")] + list(canon.get("po_reference_candidates") or [])
    po, matched_text = find_po_by_reference(con, texts)
    if po:
        pos = po_position(con, po["id"], exclude_invoice_id=invoice_id)
        if vendor and po["vendor_id"] != vendor["id"]:
            return {"method": "other_vendor", "po": pos, "score": None, "matched_text": matched_text,
                    "candidates": []}
        return {"method": "explicit", "po": pos, "score": 1.0, "matched_text": matched_text, "candidates": [],
                "normalised": bool(matched_text and matched_text.strip().upper() != po["id"].upper())}
    if not vendor:
        return {"method": "none", "po": None, "score": None, "candidates": [], "reason": "no_vendor",
                "reference_not_found": canon.get("po_reference")}
    weights = cfg["advanced"]["implied_weights"]
    cands = []
    for r in con.execute("SELECT id FROM purchase_orders WHERE vendor_id=? ORDER BY id", (vendor["id"],)):
        pos = po_position(con, r["id"], exclude_invoice_id=invoice_id)
        if pos["status"] not in ("open", "partially_billed"):
            continue
        s = implied_score(canon["lines"], canon.get("subtotal_paise"), canon.get("invoice_date"), pos, weights)
        s["pos"] = pos
        cands.append(s)
    cands.sort(key=lambda c: -c["score"])
    out_cands = [{"po_id": c["po_id"], "score": c["score"], "parts": c["parts"]} for c in cands[:3]]
    if not cands:
        return {"method": "none", "po": None, "score": None, "candidates": [], "reason": "no_open_po",
                "reference_not_found": canon.get("po_reference")}
    top = cands[0]
    runner = cands[1]["score"] if len(cands) > 1 else 0.0
    return {"method": "implied", "po": top["pos"], "score": top["score"], "runner_up": runner,
            "runner_up_po": cands[1]["po_id"] if len(cands) > 1 else None, "gap": round(top["score"] - runner, 3),
            "candidates": out_cands, "reference_not_found": canon.get("po_reference")}


# ------------------------------------------------------------------ line alignment

def _code(s: str | None) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def _coverage(po_desc: str, inv_tokens: set[str]) -> float:
    toks = sig_tokens(po_desc)
    if not toks:
        return 0.0
    hit = 0
    for t in toks:
        if t in inv_tokens or any(fuzz.ratio(t, u) >= 85 for u in inv_tokens):
            hit += 1
    return hit / len(toks)


def _bundle(l: dict, po_lines: list[dict], used: set) -> dict | None:
    inv_tokens = sig_tokens(l["description"])
    covered = [pl for pl in po_lines if pl["id"] not in used and _coverage(pl["description"], inv_tokens) >= 0.5]
    q = l.get("qty")
    if len(covered) < 2 or q is None or not all(q <= pl["ordered_qty"] + 1e-9 for pl in covered):
        return None
    unit_sum = sum(pl["unit_price_paise"] for pl in covered)
    amt = l.get("pretax_amount_paise") or 0
    alloc, given = [], 0
    for i, pl in enumerate(covered):
        part = amt - given if i == len(covered) - 1 else int(round(amt * pl["unit_price_paise"] / unit_sum))
        given += part
        alloc.append({"po_line_id": pl["id"], "qty": q, "amount_paise": part})
    return {"method": "bundle", "score": round(min(_coverage(pl["description"], inv_tokens) for pl in covered), 3),
            "po_line_ids": [pl["id"] for pl in covered], "alloc": alloc}


def align_lines(lines: list[dict], po_lines: list[dict], line_fuzzy: float = 0.80) -> list[dict]:
    """For each invoice line, in order: (a) exact SKU / item code; (b) bundle match when the invoice has fewer
    lines than the PO and one line's description covers several PO lines whose quantities line up; (c) fuzzy
    description match (>= 0.80) corroborated by price or quantity. Returns alignment records with allocations."""
    out = []
    used = set()
    for l in lines:
        rec = {"line_no": l["line_no"], "po_line_ids": [], "method": "none", "score": 0.0, "alloc": []}
        code = _code(l.get("item_code"))
        hit = next((pl for pl in po_lines if code and _code(pl.get("item_code")) == code), None)
        if hit:
            rec.update(method="sku", score=1.0)
        elif len(lines) < len(po_lines):
            b = _bundle(l, po_lines, used)
            if b:
                rec.update(b)
                used.update(b["po_line_ids"])
                out.append(rec)
                continue
        if not hit:
            best, bs = None, 0.0
            for pl in po_lines:
                s = fuzz.token_set_ratio(norm_desc(l["description"]), norm_desc(pl["description"])) / 100.0
                up = l.get("pretax_unit_paise")
                corro = (up is not None and abs(up - pl["unit_price_paise"]) <= 0.10 * pl["unit_price_paise"]) or \
                        (l.get("qty") is not None and l["qty"] <= pl["ordered_qty"])
                if s >= line_fuzzy and corro and s > bs:
                    best, bs = pl, s
            if best:
                hit = best
                rec.update(method="fuzzy", score=round(bs, 3))
        if hit:
            used.add(hit["id"])
            rec["po_line_ids"] = [hit["id"]]
            rec["alloc"] = [{"po_line_id": hit["id"], "qty": l.get("qty") or 0,
                             "amount_paise": l.get("pretax_amount_paise") or 0}]
        out.append(rec)
    return out
