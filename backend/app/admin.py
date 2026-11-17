"""Write-side operations for humans: overrides and confirmations (spec 3.8), field corrections,
master data (S6) with CSV import, audit queries (S8) and the settings impact preview (S7)."""
from __future__ import annotations

import csv
import io
import re
from datetime import timedelta

from . import db, matching, settings_store
from .catalogue import HARD_STOP_RULES, OUTCOME_LONG, RULES, SEV_RANK, SEV_TO_OUTCOME, sentence, validate_config
from .rules import band
from .textutil import GSTIN_RE, IFSC_RE, digits_only, mask_account, parse_money, to_date

REASON_CODES = ["Vendor confirmed by phone", "PO amended by Procurement", "Credit note promised",
                "Credit note requested", "Price agreed with Procurement", "Extraction corrected", "Not actually a duplicate",
                "Within policy for this vendor", "Other"]
ROLES = {"clerk": "Priya Nair", "manager": "Rahul Mehta"}
ACTION_OUTCOME = {"approve": "auto_approve", "reject": "reject", "hold": "hold_request_info"}


class Forbidden(Exception):
    pass


class Invalid(ValueError):
    pass


def actor(role: str | None, user: str | None) -> tuple[str, str]:
    r = (role or "clerk").lower()
    if r not in ROLES:
        r = "clerk"
    return r, (user or ROLES[r])


# ------------------------------------------------------------------ overrides

def override(invoice_id: str, *, action: str, reason_code: str, reason_text: str, role: str, user: str,
             checklist: dict | None = None) -> dict:
    if action not in ACTION_OUTCOME:
        raise Invalid("action must be one of approve, reject, hold.")
    if reason_code not in REASON_CODES:
        raise Invalid(f"reason_code must be one of: {', '.join(REASON_CODES)}.")
    if not reason_text or len(reason_text.strip()) < 10:
        raise Invalid("reason_text must be at least 10 characters.")
    with db.tx() as con:
        inv = con.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or not inv["current_decision_id"]:
            raise Invalid("This invoice has no decision to override.")
        cur = dict(con.execute("SELECT * FROM decisions WHERE id=?", (inv["current_decision_id"],)).fetchone())
        driving = db.loads(cur["driving_rule_ids"], []) or []
        cfg = settings_store.current(con)[1]
        split = int(cfg["global"].get("split", 10000) * 100)
        new_outcome = ACTION_OUTCOME[action]
        if new_outcome == cur["outcome"]:
            raise Invalid(f"The invoice is already '{OUTCOME_LONG[cur['outcome']]}'.")
        hard = [r for r in driving if r in HARD_STOP_RULES]
        if action == "approve":
            if role == "clerk":
                if cur["outcome"] != "route_for_review":
                    raise Forbidden("A clerk can only approve invoices that need review. Ask a manager.")
                if (cur["exposure_paise"] or 0) > split:
                    raise Forbidden(f"Exposure is above the clerk limit ({split // 100:,} rupees). Ask a manager.")
                if hard:
                    raise Forbidden("This is a hard-stop decision (vendor, bank or duplicate). Only a manager can overturn it.")
            if "R05" in driving:
                items = checklist or {}
                needed = ("called_vendor_on_master_number", "written_request_received", "second_person_confirmed")
                if role != "manager":
                    raise Forbidden("Only a manager can release a bank-change hold.")
                missing = [k for k in needed if not items.get(k)]
                if missing:
                    raise Invalid("Tick every item of the verification checklist first: " + ", ".join(missing) + ".")
        prev_label = OUTCOME_LONG[cur["outcome"]]
        expl = db.loads(cur["explanation"], {}) or {}
        expl = dict(expl)
        expl["override"] = {"from": cur["outcome"], "to": new_outcome, "by": user, "role": role,
                            "reason_code": reason_code, "reason_text": reason_text.strip(), "checklist": checklist}
        head = {"auto_approve": "Approved by a person", "reject": "Rejected by a person",
                "hold_request_info": "Sent back for information by a person"}[new_outcome]
        headline = f"{head}: {reason_code.lower()} ({user})."
        expl["banner"] = (f"Decision changed from {prev_label} to {OUTCOME_LONG[new_outcome]} by {user}, reason: "
                          f"{reason_code}")
        ver = con.execute("SELECT MAX(version) AS v FROM decisions WHERE invoice_id=?", (invoice_id,)).fetchone()["v"] + 1
        c = con.execute("INSERT INTO decisions (run_id, invoice_id, version, outcome, headline, explanation, driving_rule_ids, "
                        "exposure_paise, category, assigned_to, sla_due_at, made_by, actor_name, actor_role, reason_code, "
                        "reason_text, supersedes_decision_id, drafts, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (cur["run_id"], invoice_id, ver, new_outcome, headline, db.dumps(expl), cur["driving_rule_ids"],
                         cur["exposure_paise"], cur["category"], None, None, "user", user, role, reason_code,
                         reason_text.strip(), cur["id"], cur["drafts"], db.now_iso()))
        con.execute("UPDATE invoices SET current_decision_id=? WHERE id=?", (c.lastrowid, invoice_id))
        db.audit(con, actor_type="human", actor_id=user, event_type="decision_overridden", object_type="invoice",
                 object_id=invoice_id, run_id=cur["run_id"], invoice_id=invoice_id, outcome=new_outcome,
                 summary=f"{OUTCOME_LONG[new_outcome]} {inv['invoice_no_raw'] or invoice_id} (was {prev_label}): {reason_code}",
                 payload={"before": cur["outcome"], "after": new_outcome, "reason_code": reason_code,
                          "reason_text": reason_text.strip(), "role": role, "checklist": checklist,
                          "decision_id": c.lastrowid, "supersedes": cur["id"]})
        return {"decision_id": c.lastrowid, "version": ver, "outcome": new_outcome, "previous_outcome": cur["outcome"]}


def accept(invoice_id: str, *, user: str, role: str, note: str | None = None) -> dict:
    with db.tx() as con:
        inv = con.execute("SELECT current_decision_id, invoice_no_raw FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or not inv["current_decision_id"]:
            raise Invalid("This invoice has no decision to accept.")
        d = con.execute("SELECT outcome, explanation, confirmed_by FROM decisions WHERE id=?",
                        (inv["current_decision_id"],)).fetchone()
        if d["confirmed_by"]:
            raise Invalid(f"Already marked reviewed by {d['confirmed_by']}.")
        step = (db.loads(d["explanation"], {}) or {}).get("next_step")
        ts = db.now_iso()
        con.execute("UPDATE decisions SET confirmed_by=?, confirmed_at=? WHERE id=?", (user, ts, inv["current_decision_id"]))
        db.audit(con, actor_type="human", actor_id=user, event_type="decision_confirmed", object_type="invoice",
                 object_id=invoice_id, invoice_id=invoice_id, outcome=d["outcome"],
                 summary=f"Reviewed {inv['invoice_no_raw'] or invoice_id}: agreed with {OUTCOME_LONG[d['outcome']]}"
                         + (f". Recommended next step: {step}" if step else ""),
                 payload={"role": role, "note": note, "recommended_next_step": step})
        return {"decision_id": inv["current_decision_id"], "confirmed_by": user, "confirmed_at": ts}


def mark_info_requested(invoice_id: str, *, user: str) -> dict:
    with db.tx() as con:
        ts = db.now_iso()
        n = con.execute("UPDATE invoices SET info_requested_at=? WHERE id=?", (ts, invoice_id)).rowcount
        if not n:
            raise Invalid("Invoice not found.")
        db.audit(con, actor_type="human", actor_id=user, event_type="info_requested", object_type="invoice",
                 object_id=invoice_id, invoice_id=invoice_id, summary="Marked information requested from the vendor",
                 payload={})
        return {"info_requested_at": ts}


EDITABLE_FIELDS = {"vendor_name", "vendor_gstin", "invoice_no", "invoice_date", "po_reference", "currency", "subtotal",
                   "tax_total", "total", "bank_name", "bank_account", "bank_ifsc"}


def correct_field(invoice_id: str, name: str, *, value: str | None, reason: str | None, user: str) -> None:
    if name not in EDITABLE_FIELDS:
        raise Invalid(f"Field must be one of: {', '.join(sorted(EDITABLE_FIELDS))}.")
    with db.tx() as con:
        inv = con.execute("SELECT fields, corrections, extraction FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise Invalid("Invoice not found.")
        if not inv["extraction"]:
            raise Invalid("Nothing was extracted from this invoice, so there is no field to correct.")
        corr = db.loads(inv["corrections"], {}) or {}
        before = (db.loads(inv["fields"], {}) or {}).get(name, {}).get("value")
        corr[name] = {"value": value, "by": user, "reason": reason, "at": db.now_iso(), "before": before}
        con.execute("UPDATE invoices SET corrections=? WHERE id=?", (db.dumps(corr), invoice_id))
        db.audit(con, actor_type="human", actor_id=user, event_type="field_corrected", object_type="invoice",
                 object_id=invoice_id, invoice_id=invoice_id, summary=f"Corrected {name}: {before} to {value}",
                 payload={"field": name, "before": before, "after": value, "reason": reason, "stages_rerun": "3 to 9"})


# ------------------------------------------------------------------ vendors

VENDOR_FIELDS = ("name", "short", "aliases", "gstin", "status", "payment_terms_days", "contact_phone", "contact_email",
                 "address")


def vendor_view(con, v: dict, detail: bool = False) -> dict:
    out = {k: v.get(k) for k in ("id", "name", "short", "gstin", "status", "payment_terms_days", "bank_name", "bank_ifsc",
                                 "bank_changed_at", "bank_verified_by", "contact_phone", "contact_email", "address")}
    out["aliases"] = db.loads(v.get("aliases"), []) if isinstance(v.get("aliases"), str) else (v.get("aliases") or [])
    out["bank_account_masked"] = mask_account(v.get("bank_account_no"))
    if detail:
        out["bank_account_no"] = v.get("bank_account_no")
        out["purchase_orders"] = [po_summary(con, r["id"]) for r in con.execute(
            "SELECT id FROM purchase_orders WHERE vendor_id=? ORDER BY issue_date DESC", (v["id"],))]
        out["recent_invoices"] = [dict(r) for r in con.execute(
            "SELECT i.id AS invoice_id, i.invoice_no_raw AS invoice_no, i.invoice_date, i.total_paise, i.current_run_id AS run_id, "
            "d.outcome FROM invoices i LEFT JOIN decisions d ON d.id=i.current_decision_id WHERE i.vendor_id=? "
            "ORDER BY i.created_at DESC LIMIT 10", (v["id"],))]
    return out


def list_vendors(q: str | None = None, status: str | None = None) -> list[dict]:
    with db.conn() as con:
        out = [vendor_view(con, dict(r)) for r in con.execute("SELECT * FROM vendors ORDER BY id")]
    if status:
        out = [v for v in out if v["status"] == status]
    if q:
        ql = q.lower()
        out = [v for v in out if ql in (v["name"] or "").lower() or ql in (v["gstin"] or "").lower() or ql in v["id"].lower()]
    return out


def get_vendor(vid: str) -> dict | None:
    with db.conn() as con:
        r = con.execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone()
        return vendor_view(con, dict(r), detail=True) if r else None


def _validate_vendor(d: dict, partial: bool) -> dict:
    errs = {}
    if not partial or "name" in d:
        if not (d.get("name") or "").strip():
            errs["name"] = "Name is required."
    if d.get("gstin") and not GSTIN_RE.fullmatch(str(d["gstin"]).upper()):
        errs["gstin"] = "GSTIN must be 15 characters like 27AAFCB4821K1Z3."
    if "status" in d and d["status"] not in ("approved", "pending", "blocked"):
        errs["status"] = "Status must be approved, pending or blocked."
    if "payment_terms_days" in d and not str(d["payment_terms_days"]).isdigit():
        errs["payment_terms_days"] = "Payment terms must be a whole number of days."
    if d.get("bank_ifsc") and not IFSC_RE.fullmatch(str(d["bank_ifsc"]).upper()):
        errs["bank_ifsc"] = "IFSC must look like HUBK0000214."
    return errs


def create_vendor(d: dict, *, user: str) -> dict:
    errs = _validate_vendor(d, partial=False)
    if errs:
        raise Invalid(errs)
    with db.tx() as con:
        vid = d.get("id") or "V-" + str(100 + 1 + con.execute("SELECT COUNT(*) AS n FROM vendors").fetchone()["n"])
        if con.execute("SELECT 1 FROM vendors WHERE id=?", (vid,)).fetchone():
            raise Invalid({"id": f"Vendor {vid} already exists."})
        if d.get("gstin") and con.execute("SELECT 1 FROM vendors WHERE gstin=?", (d["gstin"].upper(),)).fetchone():
            raise Invalid({"gstin": "Another vendor already has this GSTIN."})
        now = db.now_iso()
        con.execute("INSERT INTO vendors (id, name, short, aliases, gstin, status, payment_terms_days, bank_name, "
                    "bank_account_no, bank_ifsc, contact_phone, contact_email, address, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, d["name"].strip(), d.get("short"), db.dumps(d.get("aliases") or []),
                     (d.get("gstin") or "").upper() or None, d.get("status", "pending"), int(d.get("payment_terms_days") or 30),
                     d.get("bank_name"), d.get("bank_account_no"), (d.get("bank_ifsc") or "").upper() or None,
                     d.get("contact_phone"), d.get("contact_email"), d.get("address"), now, now))
        db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="vendor",
                 object_id=vid, summary=f"Added vendor {vid} {d['name']}", payload={"before": None, "after": {
                     k: d.get(k) for k in VENDOR_FIELDS if k in d}})
    return get_vendor(vid)


def update_vendor(vid: str, d: dict, *, user: str) -> dict:
    d = {k: v for k, v in d.items() if k in VENDOR_FIELDS}
    errs = _validate_vendor(d, partial=True)
    if errs:
        raise Invalid(errs)
    with db.tx() as con:
        cur = con.execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone()
        if not cur:
            raise Invalid("Vendor not found.")
        cur = dict(cur)
        before, after = {}, {}
        for k, v in d.items():
            if k == "aliases":
                v = db.dumps(v or [])
            if k == "gstin" and v:
                v = v.upper()
            if cur.get(k) != v:
                before[k], after[k] = cur.get(k), v
                con.execute(f"UPDATE vendors SET {k}=?, updated_at=? WHERE id=?", (v, db.now_iso(), vid))
        if after:
            db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="vendor",
                     object_id=vid, summary=f"Updated vendor {vid}: {', '.join(after)}",
                     payload={"before": before, "after": after})
    return get_vendor(vid)


def change_bank(vid: str, d: dict, *, user: str, role: str) -> dict:
    if role != "manager":
        raise Forbidden("Only a manager can change vendor bank details.")
    reason = (d.get("reason") or "").strip()
    if len(reason) < 10:
        raise Invalid({"reason": "Give a reason of at least 10 characters."})
    if not d.get("verified_by"):
        raise Invalid({"verified_by": "Record who verified the change."})
    if not d.get("bank_account_no") or len(digits_only(d["bank_account_no"])) < 8:
        raise Invalid({"bank_account_no": "Enter the new account number."})
    if not d.get("bank_ifsc") or not IFSC_RE.fullmatch(d["bank_ifsc"].upper()):
        raise Invalid({"bank_ifsc": "IFSC must look like HUBK0000214."})
    with db.tx() as con:
        cur = con.execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone()
        if not cur:
            raise Invalid("Vendor not found.")
        now = db.now_iso()
        con.execute("UPDATE vendors SET bank_name=?, bank_account_no=?, bank_ifsc=?, bank_changed_at=?, bank_verified_by=?, "
                    "updated_at=? WHERE id=?", (d.get("bank_name"), d["bank_account_no"], d["bank_ifsc"].upper(), now[:10],
                                                d["verified_by"], now, vid))
        db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="vendor",
                 object_id=vid, summary=f"Changed bank details for {cur['name']}",
                 payload={"before": {"bank_name": cur["bank_name"], "account": mask_account(cur["bank_account_no"]),
                                     "ifsc": cur["bank_ifsc"]},
                          "after": {"bank_name": d.get("bank_name"), "account": mask_account(d["bank_account_no"]),
                                    "ifsc": d["bank_ifsc"].upper()},
                          "reason": reason, "verified_by": d["verified_by"]})
    return get_vendor(vid)


# ------------------------------------------------------------------ purchase orders

def po_summary(con, po_id: str) -> dict:
    p = matching.po_position(con, po_id)
    v = con.execute("SELECT name, short FROM vendors WHERE id=?", (p["vendor_id"],)).fetchone()
    return {"id": p["id"], "vendor_id": p["vendor_id"], "vendor_name": v["name"] if v else None,
            "vendor_short": v["short"] if v else None, "issue_date": p["issue_date"], "valid_to": p["valid_to"],
            "status": p["status"], "currency": p["currency"], "subtotal_paise": p["subtotal_paise"], "tax_paise": p["tax_paise"],
            "total_paise": p["total_paise"], "billed_subtotal_paise": p["billed_subtotal_paise"],
            "pending_subtotal_paise": p["pending_subtotal_paise"], "remaining_subtotal_paise": p["remaining_subtotal_paise"],
            "pct_billed": p["pct_billed"], "invoice_count": len(p["history"]), "is_seed": bool(p.get("is_seed"))}


def list_pos(status: str | None = None, vendor_id: str | None = None, q: str | None = None) -> list[dict]:
    with db.conn() as con:
        out = [po_summary(con, r["id"]) for r in con.execute("SELECT id FROM purchase_orders ORDER BY id")]
    if status:
        out = [p for p in out if p["status"] == status]
    if vendor_id:
        out = [p for p in out if p["vendor_id"] == vendor_id]
    if q:
        ql = q.lower()
        out = [p for p in out if ql in p["id"].lower() or ql in (p["vendor_name"] or "").lower()]
    return out


def get_po(po_id: str) -> dict | None:
    with db.conn() as con:
        p = matching.po_position(con, po_id)
        if not p:
            return None
        s = po_summary(con, po_id)
        s["lines"] = [{k: l[k] for k in ("id", "line_no", "item_code", "description", "uom", "ordered_qty", "unit_price_paise",
                                         "tax_rate_pct", "billed_qty", "pending_qty", "remaining_qty", "opening_billed_qty",
                                         "line_value_paise", "billed_value_paise")} for l in p["lines"]]
        s["billing_history"] = p["history"]
        s["locked"] = bool(p["history"])
        s["locked_fields"] = ["vendor_id", "lines.item_code"] if p["history"] else []
        return s


def _validate_po_lines(lines: list[dict]) -> dict:
    errs = {}
    for i, l in enumerate(lines):
        if not (l.get("description") or "").strip():
            errs[f"lines.{i}.description"] = "Description is required."
        try:
            if float(l.get("ordered_qty")) <= 0:
                errs[f"lines.{i}.ordered_qty"] = "Quantity must be above zero."
        except (TypeError, ValueError):
            errs[f"lines.{i}.ordered_qty"] = "Quantity must be a number."
        if parse_money(l.get("unit_price")) is None and l.get("unit_price_paise") is None:
            errs[f"lines.{i}.unit_price"] = "Unit price must be a number."
    return errs


def create_po(d: dict, *, user: str) -> dict:
    errs = {}
    if not re.fullmatch(r"PO-20\d{2}-\d{3,5}", d.get("id") or ""):
        errs["id"] = "PO number must look like PO-2026-1010."
    lines = d.get("lines") or []
    if not lines:
        errs["lines"] = "Add at least one line."
    errs.update(_validate_po_lines(lines))
    if not to_date(d.get("issue_date")):
        errs["issue_date"] = "Issue date is required (YYYY-MM-DD)."
    if not to_date(d.get("valid_to")):
        errs["valid_to"] = "Valid-to date is required (YYYY-MM-DD)."
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM vendors WHERE id=?", (d.get("vendor_id"),)).fetchone():
            errs["vendor_id"] = "Unknown vendor."
        if d.get("id") and con.execute("SELECT 1 FROM purchase_orders WHERE id=?", (d["id"],)).fetchone():
            errs["id"] = "This PO number already exists."
        if errs:
            raise Invalid(errs)
        now = db.now_iso()
        con.execute("INSERT INTO purchase_orders (id, vendor_id, issue_date, valid_to, currency, notes, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)", (d["id"], d["vendor_id"], d["issue_date"], d["valid_to"],
                                                 d.get("currency", "INR"), d.get("notes"), now, now))
        for i, l in enumerate(lines, 1):
            _insert_line(con, d["id"], i, l)
        db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="po",
                 object_id=d["id"], summary=f"Added purchase order {d['id']} ({len(lines)} line{'s' if len(lines) != 1 else ''})",
                 payload={"before": None, "after": d})
    return get_po(d["id"])


def _insert_line(con, po_id, line_no, l):
    price = l.get("unit_price_paise")
    if price is None:
        price = parse_money(l.get("unit_price"))
    con.execute("INSERT INTO po_lines (po_id, line_no, item_code, description, uom, ordered_qty, unit_price_paise, "
                "tax_rate_pct, opening_billed_qty) VALUES (?,?,?,?,?,?,?,?,?)",
                (po_id, line_no, l.get("item_code"), l["description"].strip(), l.get("uom") or "nos", float(l["ordered_qty"]),
                 int(price), float(l.get("tax_rate_pct") or 18), float(l.get("opening_billed_qty") or 0)))


def update_po(po_id: str, d: dict, *, user: str) -> dict:
    with db.tx() as con:
        cur = con.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
        if not cur:
            raise Invalid("PO not found.")
        has_inv = con.execute("SELECT 1 FROM invoices WHERE po_id=? LIMIT 1", (po_id,)).fetchone()
        if "vendor_id" in d and d["vendor_id"] != cur["vendor_id"] and has_inv:
            raise Invalid({"vendor_id": "This PO has invoices, so its vendor cannot change (it would corrupt history)."})
        before, after = {}, {}
        for k in ("vendor_id", "issue_date", "valid_to", "currency", "notes"):
            if k in d and d[k] != cur[k]:
                if k in ("issue_date", "valid_to") and not to_date(d[k]):
                    raise Invalid({k: "Use YYYY-MM-DD."})
                before[k], after[k] = cur[k], d[k]
                con.execute(f"UPDATE purchase_orders SET {k}=?, updated_at=? WHERE id=?", (d[k], db.now_iso(), po_id))
        for l in d.get("lines") or []:
            if not l.get("id"):
                continue
            row = con.execute("SELECT * FROM po_lines WHERE id=? AND po_id=?", (l["id"], po_id)).fetchone()
            if not row:
                raise Invalid({"lines": f"Line {l['id']} is not on {po_id}."})
            if "item_code" in l and l["item_code"] != row["item_code"] and has_inv:
                raise Invalid({"lines.item_code": "Item codes are locked once a PO has invoices."})
            for k in ("item_code", "description", "uom", "ordered_qty", "tax_rate_pct"):
                if k in l and l[k] != row[k]:
                    before[f"line{row['line_no']}.{k}"], after[f"line{row['line_no']}.{k}"] = row[k], l[k]
                    con.execute(f"UPDATE po_lines SET {k}=? WHERE id=?", (l[k], l["id"]))
            if "unit_price" in l or "unit_price_paise" in l:
                p = l.get("unit_price_paise") if l.get("unit_price_paise") is not None else parse_money(l.get("unit_price"))
                if p is None:
                    raise Invalid({"lines.unit_price": "Unit price must be a number."})
                if p != row["unit_price_paise"]:
                    before[f"line{row['line_no']}.unit_price_paise"], after[f"line{row['line_no']}.unit_price_paise"] = row["unit_price_paise"], p
                    con.execute("UPDATE po_lines SET unit_price_paise=? WHERE id=?", (p, l["id"]))
        if after:
            db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="po",
                     object_id=po_id, summary=f"Updated {po_id}: {', '.join(after)}", payload={"before": before, "after": after})
    return get_po(po_id)


def add_po_line(po_id: str, l: dict, *, user: str) -> dict:
    errs = _validate_po_lines([l])
    if errs:
        raise Invalid(errs)
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM purchase_orders WHERE id=?", (po_id,)).fetchone():
            raise Invalid("PO not found.")
        n = con.execute("SELECT COALESCE(MAX(line_no),0) AS n FROM po_lines WHERE po_id=?", (po_id,)).fetchone()["n"] + 1
        _insert_line(con, po_id, n, l)
        db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="po",
                 object_id=po_id, summary=f"Added line {n} to {po_id}: {l.get('description')}", payload={"after": l})
    return get_po(po_id)


def set_po_status(po_id: str, status: str, *, user: str, reason: str | None = None) -> dict:
    if status not in ("closed", "cancelled", "open"):
        raise Invalid("Status must be closed, cancelled or open.")
    with db.tx() as con:
        cur = con.execute("SELECT status_override FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
        if not cur:
            raise Invalid("PO not found.")
        con.execute("UPDATE purchase_orders SET status_override=?, updated_at=? WHERE id=?",
                    (None if status == "open" else status, db.now_iso(), po_id))
        db.audit(con, actor_type="human", actor_id=user, event_type="master_data_changed", object_type="po",
                 object_id=po_id, summary=f"{po_id} marked {status}", payload={"before": cur["status_override"],
                                                                               "after": status, "reason": reason})
    return get_po(po_id)


# ------------------------------------------------------------------ CSV import / export

VENDOR_COLS = ["id", "name", "gstin", "status", "payment_terms_days", "bank_name", "bank_account_no", "bank_ifsc",
               "contact_phone", "contact_email", "aliases", "address"]
PO_COLS = ["po_number", "vendor_id", "issue_date", "valid_to", "currency", "item_code", "description", "uom", "ordered_qty",
           "unit_price", "tax_rate_pct"]


def import_csv(kind: str, text: str, *, commit: bool, user: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(text)))
    problems, preview = [], []
    with db.conn() as con:
        vendors = {r["id"] for r in con.execute("SELECT id FROM vendors")}
        gstins = {r["gstin"]: r["id"] for r in con.execute("SELECT id, gstin FROM vendors") if r["gstin"]}
        pos = {r["id"] for r in con.execute("SELECT id FROM purchase_orders")}
    if kind == "vendors":
        seen = set()
        for i, r in enumerate(rows, 2):
            errs = _validate_vendor({k: v for k, v in r.items() if v not in (None, "")}, partial=False)
            if r.get("id") in seen:
                errs["id"] = "Duplicate vendor id in the file."
            if r.get("gstin") and gstins.get(r["gstin"].upper()) not in (None, r.get("id")):
                errs["gstin"] = "GSTIN belongs to another vendor."
            seen.add(r.get("id"))
            action = "update" if r.get("id") in vendors else "add"
            preview.append({"row": i, "action": action, "data": r, "errors": errs})
            if errs:
                problems.append({"row": i, "errors": errs})
    elif kind == "pos":
        groups: dict[str, list] = {}
        for i, r in enumerate(rows, 2):
            errs = {}
            if not re.fullmatch(r"PO-20\d{2}-\d{3,5}", r.get("po_number") or ""):
                errs["po_number"] = "PO number must look like PO-2026-1010."
            if r.get("vendor_id") not in vendors:
                errs["vendor_id"] = "Unknown vendor."
            if r.get("po_number") in pos:
                errs["po_number"] = "This PO already exists."
            try:
                if float(r.get("ordered_qty") or "x") <= 0:
                    errs["ordered_qty"] = "Quantity must be above zero (no negative quantities)."
            except ValueError:
                errs["ordered_qty"] = "Quantity must be a number."
            if parse_money(r.get("unit_price")) is None:
                errs["unit_price"] = "Unit price must be a number."
            if not to_date(r.get("issue_date")) or not to_date(r.get("valid_to")):
                errs["dates"] = "Dates must be YYYY-MM-DD."
            preview.append({"row": i, "action": "add", "data": r, "errors": errs})
            if errs:
                problems.append({"row": i, "errors": errs})
            groups.setdefault(r.get("po_number"), []).append(r)
    else:
        raise Invalid("kind must be vendors or pos.")
    result = {"kind": kind, "rows": len(rows), "valid": not problems, "problems": problems, "preview": preview,
              "committed": False}
    if commit:
        if problems:
            raise Invalid({"rows": f"{len(problems)} row(s) have problems; nothing was imported."})
        if kind == "vendors":
            for r in rows:
                d = {k: v for k, v in r.items() if v not in (None, "")}
                d["aliases"] = [a.strip() for a in (d.get("aliases") or "").split("|") if a.strip()]
                if d["id"] in vendors:
                    update_vendor(d["id"], d, user=user)
                else:
                    create_vendor(d, user=user)
        else:
            for po_id, ls in groups.items():
                f = ls[0]
                create_po({"id": po_id, "vendor_id": f["vendor_id"], "issue_date": f["issue_date"], "valid_to": f["valid_to"],
                           "currency": f.get("currency") or "INR",
                           "lines": [{"item_code": x.get("item_code"), "description": x.get("description"), "uom": x.get("uom"),
                                      "ordered_qty": x.get("ordered_qty"), "unit_price": x.get("unit_price"),
                                      "tax_rate_pct": x.get("tax_rate_pct") or 18} for x in ls]}, user=user)
        result["committed"] = True
    return result


def export_csv(kind: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    with db.conn() as con:
        if kind == "vendors":
            w.writerow(VENDOR_COLS)
            for r in con.execute("SELECT * FROM vendors ORDER BY id"):
                d = dict(r)
                d["aliases"] = "|".join(db.loads(d["aliases"], []))
                w.writerow([d.get(c) for c in VENDOR_COLS])
        else:
            w.writerow(PO_COLS)
            for r in con.execute("SELECT p.*, l.item_code, l.description, l.uom, l.ordered_qty, l.unit_price_paise, "
                                 "l.tax_rate_pct FROM purchase_orders p JOIN po_lines l ON l.po_id=p.id ORDER BY p.id, l.line_no"):
                w.writerow([r["id"], r["vendor_id"], r["issue_date"], r["valid_to"], r["currency"], r["item_code"],
                            r["description"], r["uom"], r["ordered_qty"], f"{r['unit_price_paise'] / 100:.2f}", r["tax_rate_pct"]])
    return buf.getvalue()


# ------------------------------------------------------------------ audit (S8)

ACTOR_TYPES = ("system", "ai", "human")


def audit_query(*, date_from: str | None = None, date_to: str | None = None, actor_type: str | None = None,
                user: str | None = None, event_type: str | None = None, object_id: str | None = None,
                invoice_id: str | None = None, q: str | None = None, page: int = 1, page_size: int = 100) -> dict:
    where, args = [], []
    if date_from:
        where.append("ts >= ?")
        args.append(date_from)
    if date_to:
        where.append("ts <= ?")
        args.append(date_to + ("T23:59:59.999Z" if len(date_to) == 10 else ""))
    if actor_type:
        where.append("actor_type = ?")
        args.append(actor_type)
    if user:
        where.append("actor_id = ?")
        args.append(user)
    if event_type:
        types = event_type.split(",")
        where.append(f"event_type IN ({','.join('?' * len(types))})")
        args.extend(types)
    if object_id:
        where.append("(object_id = ? OR invoice_id = ? OR run_id = ?)")
        args.extend([object_id] * 3)
    if invoice_id:
        where.append("invoice_id = ?")
        args.append(invoice_id)
    if q:
        where.append("(summary LIKE ? OR object_id LIKE ? OR actor_id LIKE ?)")
        args.extend([f"%{q}%"] * 3)
    sql = "FROM audit_events" + (" WHERE " + " AND ".join(where) if where else "")
    with db.conn() as con:
        total = con.execute("SELECT COUNT(*) AS n " + sql, args).fetchone()["n"]
        items = [dict(r) for r in con.execute("SELECT * " + sql + " ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
                                              args + [page_size, (max(1, page) - 1) * page_size])]
        types = [r["event_type"] for r in con.execute("SELECT DISTINCT event_type FROM audit_events ORDER BY event_type")]
        users = [r["actor_id"] for r in con.execute("SELECT DISTINCT actor_id FROM audit_events WHERE actor_type='human' ORDER BY actor_id")]
    for it in items:
        it["payload"] = db.loads(it["payload"], {})
    return {"items": items, "total": total, "page": page, "page_size": page_size, "event_types": types, "users": users,
            "notice": "Entries cannot be edited or deleted."}


# ------------------------------------------------------------------ settings impact preview (P1)

def impact_preview(patch: dict, days: int = 90) -> dict:
    """Re-evaluate threshold rules from stored rule facts for real (non-synthetic) runs of the last N days and
    count how many decisions would change."""
    from .repo import anchor_now, parse_ts  # noqa: PLC0415
    _, cur = settings_store.current()
    new = settings_store._merge(cur, patch)
    errs = validate_config(new)
    start = anchor_now() - timedelta(days=days)
    flips, checked = [], 0
    with db.conn() as con:
        invs = [dict(r) for r in con.execute(
            "SELECT i.id, i.invoice_no_raw, i.total_paise, i.current_run_id, d.outcome FROM invoices i "
            "JOIN decisions d ON d.id = (SELECT MAX(id) FROM decisions WHERE invoice_id=i.id AND made_by='system') "
            "WHERE i.is_synthetic = 0")]
        for inv in invs:
            rr = {r["rule_id"]: dict(r) for r in con.execute("SELECT * FROM rule_results WHERE run_id=?", (inv["current_run_id"],))}
            run = con.execute("SELECT started_at FROM runs WHERE id=?", (inv["current_run_id"],)).fetchone()
            if not rr or not run or (parse_ts(run["started_at"]) or start) < start:
                continue
            checked += 1
            sev = {k: (v["severity"] if not v["skipped"] else "pass") for k, v in rr.items()}
            for rid, r in rr.items():
                if r["skipped"]:
                    continue
                f = db.loads(r["facts"], {}) or {}
                p = new["rules"].get(rid, {})
                try:
                    if rid == "R10" and f.get("lines"):
                        sev[rid] = max((band(x["delta_paise"], x["delta_pct"], p)[0] for x in f["lines"]), key=SEV_RANK.get)
                    elif rid == "R11" and f.get("lines"):
                        sev[rid] = max(("pass" if x["over"] <= 0 else band(int(x["over"] * x["unit_price_paise"]), x["over_pct"], p)[0]
                                        for x in f["lines"]), key=SEV_RANK.get)
                    elif rid == "R12" and "delta_paise" in f:
                        sev[rid] = "pass" if f["delta_paise"] <= 0 else band(f["delta_paise"], f["delta_pct"], p)[0]
                    elif rid == "R13" and "diff_paise" in f and not f.get("wrong_rate"):
                        d = abs(f["diff_paise"])
                        sev[rid] = "pass" if d <= p["pass"] * 100 else "note" if d <= p["note"] * 100 else "review" if d <= p["review"] * 100 else "reject"
                    elif rid == "R06" and "score" in f and not f.get("exact"):
                        sev[rid] = "reject" if f["score"] >= p["reject"] else "review" if f["score"] >= p["review"] else "pass"
                    elif rid == "R02" and "lowest" in f:
                        sev[rid] = "pass" if f["lowest"] >= p["ok"] else "note" if f["lowest"] >= p["min"] else "hold"
                    elif rid == "R15" and "total_paise" in f:
                        sev[rid] = "review" if f["total_paise"] > p["cap"] * 100 else "pass"
                except (KeyError, TypeError):
                    pass
                if new.get("enabled", {}).get(rid) is False:
                    sev[rid] = "pass"
            worst = max(sev.values(), key=SEV_RANK.get)
            outcome = SEV_TO_OUTCOME[worst]
            if not new["global"].get("auto", True) and outcome in ("auto_approve", "approve_with_note"):
                outcome = "route_for_review"
            if outcome != inv["outcome"]:
                flips.append({"invoice_id": inv["id"], "invoice_no": inv["invoice_no_raw"], "from": inv["outcome"],
                              "to": outcome})
    summary: dict[str, int] = {}
    for f in flips:
        k = f"{f['from']}->{f['to']}"
        summary[k] = summary.get(k, 0) + 1
    return {"valid": not errs, "errors": errs, "days": days, "checked_runs": checked, "would_change": len(flips),
            "changes": summary, "invoices": flips,
            "note": "Re-checked from stored rule facts of real (non-synthetic) runs; seeded history has no facts.",
            "sentences": {r["id"]: sentence(r["id"], new) for r in RULES}}
