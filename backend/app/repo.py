"""Read models for the screens: runs list (S1), run detail (S4), review queue (S5), master data (S6),
audit (S8) and dashboard metrics (S1)."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from . import config, db, matching, settings_store
from .catalogue import (APPROVED_OUTCOMES, CATEGORY_BY_RULE, OUTCOME_LABEL, OUTCOME_LONG, RULES, STAGES,
                        allowed_text)
from .textutil import mask_account

IST = timezone(timedelta(hours=5, minutes=30))


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(s[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def anchor_now() -> datetime:
    """The dashboard's 'now': the later of the real clock and the end of the configured as-of day."""
    now = datetime.now(timezone.utc)
    if config.AS_OF:
        a = datetime.fromisoformat(config.AS_OF).replace(hour=23, minute=59, tzinfo=IST).astimezone(timezone.utc)
        return max(now, a)
    return now


# ------------------------------------------------------------------ runs list (S1)

RUN_SQL = """
SELECT r.id AS run_id, r.invoice_id, r.status AS run_status, r.current_stage, r.started_at, r.finished_at,
       r.duration_ms, r.created_at AS run_created_at, r.source, r.parent_run_id, r.error, r.extraction_mode,
       i.vendor_id, i.vendor_name_raw, i.invoice_no_raw, i.po_id, i.po_ref_raw, i.po_match_method, i.total_paise,
       i.fields, i.is_synthetic, i.file_name, i.file_path, i.doc_type, i.current_run_id, i.sample_id,
       v.name AS vendor_name, v.short AS vendor_short,
       cd.id AS cur_dec_id, cd.outcome AS cur_outcome, cd.made_by AS cur_made_by, cd.headline AS cur_headline,
       cd.explanation AS cur_expl, cd.exposure_paise AS cur_exposure, cd.assigned_to AS cur_assigned,
       cd.category AS cur_category, cd.created_at AS cur_decided_at, cd.version AS cur_version,
       rd.outcome AS run_outcome, rd.headline AS run_headline, rd.explanation AS run_expl
FROM runs r
JOIN invoices i ON i.id = r.invoice_id
LEFT JOIN vendors v ON v.id = i.vendor_id
LEFT JOIN decisions cd ON cd.id = i.current_decision_id
LEFT JOIN decisions rd ON rd.id = (SELECT MAX(id) FROM decisions WHERE run_id = r.id AND made_by = 'system')
"""


def _lowest_conf(fields_json) -> float | None:
    f = db.loads(fields_json, {}) or {}
    vals = [x.get("effective_confidence") for x in f.values()
            if isinstance(x, dict) and x.get("value") is not None and x.get("effective_confidence") is not None]
    return round(min(vals), 2) if vals else None


def run_row(r: dict) -> dict:
    is_current = r["run_id"] == r["current_run_id"]
    if r["run_status"] in ("queued", "running"):
        outcome = "running"
    elif r["run_status"] in ("failed", "cancelled"):
        outcome = r["run_status"]
    else:
        outcome = (r["cur_outcome"] if is_current else r["run_outcome"]) or "error"
    expl = db.loads(r["cur_expl"] if is_current else r["run_expl"], {}) or {}
    overridden = bool(is_current and r["cur_made_by"] == "user")
    return {
        "run_id": r["run_id"], "invoice_id": r["invoice_id"], "received_at": r["started_at"] or r["run_created_at"],
        "finished_at": r["finished_at"], "status": r["run_status"], "outcome": outcome,
        "outcome_label": OUTCOME_LABEL.get(outcome, outcome.capitalize()),
        "current_stage": r["current_stage"],
        "stage_label": (f"Stage {r['current_stage']} of 9: {STAGES[r['current_stage'] - 1]['name']}"
                        if r["run_status"] == "running" and r["current_stage"] else None),
        "vendor_id": r["vendor_id"], "vendor_name": r["vendor_name"] or r["vendor_name_raw"],
        "vendor_short": r["vendor_short"] or r["vendor_name_raw"], "invoice_no": r["invoice_no_raw"],
        "po_id": r["po_id"], "po_inferred": r["po_match_method"] == "implied", "gross_paise": r["total_paise"],
        "main_reason": expl.get("short_reason") or expl.get("main_reason") or (r["error"] or ""),
        "headline": (r["cur_headline"] if is_current else r["run_headline"]) or expl.get("headline"),
        "lowest_confidence": _lowest_conf(r["fields"]), "duration_ms": r["duration_ms"], "overridden": overridden,
        "exposure_paise": r["cur_exposure"] if is_current else None, "assigned_to": r["cur_assigned"] if is_current else None,
        "category": r["cur_category"] if is_current else None, "is_synthetic": bool(r["is_synthetic"]),
        "has_pdf": bool(r["file_path"]), "file_name": r["file_name"], "doc_type": r["doc_type"], "source": r["source"],
        "sample_id": r["sample_id"], "is_latest_run": is_current, "error": r["error"],
    }


SORTS = {"time": "received_at", "amount": "gross_paise", "vendor": "vendor_short", "invoice_no": "invoice_no",
         "duration": "duration_ms", "confidence": "lowest_confidence", "outcome": "outcome", "po": "po_id"}


def list_runs(*, statuses: list[str] | None = None, q: str | None = None, range_days: int | None = None,
              vendor_id: str | None = None, overridden: bool | None = None, all_runs: bool = False,
              sort: str = "time", order: str = "desc", page: int = 1, page_size: int = 25) -> dict:
    with db.conn() as con:
        rows = [run_row(dict(r)) for r in con.execute(RUN_SQL)]
    if not all_runs:
        rows = [r for r in rows if r["is_latest_run"]]
    if range_days:
        start = anchor_now() - timedelta(days=range_days)
        rows = [r for r in rows if (parse_ts(r["received_at"]) or start) >= start]
    counts = {k: 0 for k in ("all", "auto_approve", "approve_with_note", "route_for_review", "hold_request_info",
                             "reject", "running", "failed", "cancelled")}
    for r in rows:
        counts["all"] += 1
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    if vendor_id:
        rows = [r for r in rows if r["vendor_id"] == vendor_id]
    if q:
        ql = q.lower()
        rows = [r for r in rows if any(ql in str(r.get(k) or "").lower()
                                       for k in ("vendor_name", "vendor_short", "invoice_no", "po_id", "run_id", "invoice_id"))]
    if statuses:
        rows = [r for r in rows if r["outcome"] in statuses]
    if overridden is not None:
        rows = [r for r in rows if r["overridden"] == overridden]
    key = SORTS.get(sort, "received_at")
    rows.sort(key=lambda r: (r.get(key) is None, r.get(key) if r.get(key) is not None else 0), reverse=(order == "desc"))
    if order == "desc":  # keep None last when descending
        rows.sort(key=lambda r: r.get(key) is None)
    total = len(rows)
    page = max(1, page)
    items = rows[(page - 1) * page_size: page * page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "counts": counts}


# ------------------------------------------------------------------ run detail (S4)

def _rules_view(con, run_id: str, cfg: dict) -> list[dict]:
    res = {r["rule_id"]: dict(r) for r in con.execute("SELECT * FROM rule_results WHERE run_id=?", (run_id,))}
    out = []
    for meta in RULES:
        r = res.get(meta["id"])
        out.append({"rule_id": meta["id"], "name": meta["name"], "stage_no": meta["stage"], "group": meta["group"],
                    "hard_stop": bool(meta.get("hard")), "severity": r["severity"] if r else None,
                    "skipped": bool(r["skipped"]) if r else True, "message": r["message_plain"] if r else "Not evaluated.",
                    "facts": db.loads(r["facts"], {}) if r else {}, "threshold_used": db.loads(r["threshold_used"], {}) if r else {},
                    "exposure_paise": r["exposure_paise"] if r else 0, "allowed": allowed_text(meta["id"], cfg)})
    return out


def _decision_view(d: dict | None) -> dict | None:
    if not d:
        return None
    d = dict(d)
    d["explanation"] = db.loads(d.get("explanation"), {})
    d["driving_rule_ids"] = db.loads(d.get("driving_rule_ids"), [])
    d["drafts"] = db.loads(d.get("drafts"), [])
    d["outcome_label"] = OUTCOME_LABEL.get(d["outcome"])
    d["outcome_long"] = OUTCOME_LONG.get(d["outcome"])
    return d


def invoice_detail(invoice_id: str, run_id: str | None = None) -> dict | None:
    with db.conn() as con:
        inv = con.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            return None
        inv = dict(inv)
        run_id = run_id or inv["current_run_id"]
        run = dict(con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone() or {})
        cfg = settings_store.get_version(run.get("config_version") or 0) or settings_store.current(con)[1]
        stages = [dict(r) for r in con.execute("SELECT * FROM stage_results WHERE run_id=? ORDER BY stage_no", (run_id,))]
        for s in stages:
            s["input_summary"] = db.loads(s["input_summary"], {})
            s["output_summary"] = db.loads(s["output_summary"], {})
        by_no = {s["stage_no"]: s for s in stages}
        stages = [by_no.get(s["no"], {"stage_no": s["no"], "stage_name": s["name"], "status": "pending"}) for s in STAGES]
        rules = _rules_view(con, run_id, cfg)
        decisions = [_decision_view(dict(d)) for d in con.execute(
            "SELECT * FROM decisions WHERE invoice_id=? ORDER BY version", (invoice_id,))]
        current = next((d for d in decisions if d["id"] == inv["current_decision_id"]), None)
        run_decision = next((d for d in reversed(decisions) if d["run_id"] == run_id and d["made_by"] == "system"), None)
        lines = [dict(r) for r in con.execute("SELECT * FROM line_items WHERE invoice_id=? ORDER BY line_no", (invoice_id,))]
        for l in lines:
            l["matched_po_line_ids"] = db.loads(l["matched_po_line_ids"], [])
            l["alloc"] = db.loads(l["alloc"], [])
        vendor = None
        if inv["vendor_id"]:
            v = con.execute("SELECT * FROM vendors WHERE id=?", (inv["vendor_id"],)).fetchone()
            vendor = dict(v) if v else None
        po = matching.po_position(con, inv["po_id"], exclude_invoice_id=invoice_id) if inv["po_id"] else None
        timeline = [dict(a) for a in con.execute(
            "SELECT id, ts, actor_type, actor_id, event_type, summary, outcome, run_id FROM audit_events "
            "WHERE invoice_id=? ORDER BY ts, id", (invoice_id,))]
    fields = db.loads(inv["fields"], {}) or {}
    extraction = db.loads(inv["extraction"], {}) or {}
    rmap = {r["rule_id"]: r for r in rules}

    # PO match table (one row per PO line, spec S4 component 6)
    po_panel = None
    if po:
        this_by_line: dict[int, dict] = {}
        for l in lines:
            for a in l["alloc"]:
                t = this_by_line.setdefault(a["po_line_id"], {"qty": 0.0, "amount_paise": 0, "invoice_lines": [],
                                                              "method": l["match_method"]})
                t["qty"] += float(a["qty"] or 0)
                t["amount_paise"] += int(a["amount_paise"] or 0)
                t["invoice_lines"].append(l["line_no"])
        price_rows = {x["line_no"]: x for x in (rmap.get("R10", {}).get("facts", {}) or {}).get("lines", [])}
        qty_rows = {x["po_line_id"]: x for x in (rmap.get("R11", {}).get("facts", {}) or {}).get("lines", [])}
        table = []
        for pl in po["lines"]:
            t = this_by_line.get(pl["id"])
            inv_line = next((l for l in lines if t and l["line_no"] in t["invoice_lines"]), None)
            pr = price_rows.get(inv_line["line_no"]) if inv_line else None
            qr = qty_rows.get(pl["id"])
            this_qty = t["qty"] if t else 0
            inv_unit = int(round(t["amount_paise"] / this_qty)) if t and this_qty else None
            expected = int(round(this_qty * pl["unit_price_paise"]))
            table.append({
                "po_line_id": pl["id"], "item_code": pl["item_code"], "po_description": pl["description"],
                "invoice_line_no": inv_line["line_no"] if inv_line else None,
                "invoice_description": inv_line["description_raw"] if inv_line else None,
                "match_method": t["method"] if t else None, "bundle": bool(t and t["method"] == "bundle"),
                "uom": pl["uom"], "ordered_qty": pl["ordered_qty"], "billed_before_qty": pl["billed_qty"],
                "pending_qty": pl["pending_qty"], "this_invoice_qty": this_qty,
                "remaining_before_qty": pl["remaining_qty"], "remaining_after_qty": round(pl["remaining_qty"] - this_qty, 4),
                "po_unit_price_paise": pl["unit_price_paise"], "invoice_unit_price_paise": inv_unit,
                "unit_price_delta_pct": round(100.0 * (inv_unit - pl["unit_price_paise"]) / pl["unit_price_paise"], 3)
                if inv_unit is not None and pl["unit_price_paise"] else None,
                "amount_variance_paise": (t["amount_paise"] - expected) if t else None,
                "amount_variance_pct": round(100.0 * (t["amount_paise"] - expected) / expected, 3) if t and expected else None,
                "over_qty": qr["over"] if qr else 0, "tax_rate_pct": pl["tax_rate_pct"],
                "status": (max([x for x in (pr and pr["severity"], qr and qr["severity"]) if x],
                               key=lambda s: ["pass", "note", "review", "hold", "reject"].index(s), default="pass")
                           if t else "none"),
            })
        this_val = sum(t["amount_paise"] for t in this_by_line.values())
        po_panel = {
            "po": {k: po[k] for k in ("id", "vendor_id", "issue_date", "valid_to", "status", "currency", "subtotal_paise",
                                      "tax_paise", "total_paise", "billed_subtotal_paise", "pending_subtotal_paise",
                                      "remaining_subtotal_paise", "pct_billed")},
            "match_method": inv["po_match_method"], "match_score": inv["po_match_score"],
            "runner_up": db.loads(inv["po_runner_up"], {}), "written_as": inv["po_ref_raw"],
            "table": table,
            "cumulative": {"before_pct": po["pct_billed"],
                           "after_pct": round(100.0 * (po["billed_subtotal_paise"] + this_val) / po["subtotal_paise"], 2)
                           if po["subtotal_paise"] else None,
                           "before_paise": po["billed_subtotal_paise"], "this_invoice_paise": this_val,
                           "po_subtotal_paise": po["subtotal_paise"], "pending_paise": po["pending_subtotal_paise"]},
            "timeline": po["history"],
        }
    elif inv["po_match_method"]:
        po_panel = {"po": None, "match_method": inv["po_match_method"], "runner_up": db.loads(inv["po_runner_up"], {}),
                    "table": [], "cumulative": None, "timeline": []}

    r05 = rmap.get("R05", {})
    vendor_panel = {
        "vendor": ({k: vendor[k] for k in ("id", "name", "short", "gstin", "status", "payment_terms_days", "contact_phone",
                                           "bank_changed_at", "bank_verified_by")} if vendor else None),
        "match": (rmap.get("R04") or {}).get("facts", {}),
        "bank_on_invoice": {"bank_name": inv["bank_name_raw"], "account": inv["bank_account_raw"],
                            "account_masked": mask_account(inv["bank_account_raw"]), "ifsc": inv["bank_ifsc_raw"],
                            "change_notice": bool(inv["bank_change_notice"]),
                            "change_text": (extraction or {}).get("bank_change_text")} if (inv["bank_account_raw"] or inv["bank_name_raw"] or inv["bank_change_notice"]) else None,
        "bank_on_file": {"bank_name": vendor["bank_name"], "account": vendor["bank_account_no"],
                         "account_masked": mask_account(vendor["bank_account_no"]), "ifsc": vendor["bank_ifsc"]} if vendor else None,
        "bank_match": None if r05.get("skipped") or not r05 else (r05.get("severity") == "pass"),
    }
    r06 = (rmap.get("R06") or {}).get("facts", {}) or {}
    dup_panel = {"score": r06.get("score"), "thresholds": (rmap.get("R06") or {}).get("threshold_used"),
                 "exact": r06.get("exact"), "closest": r06.get("closest"), "signals": r06.get("signals"),
                 "recurring_guard": r06.get("recurring_guard"), "compared": r06.get("compared")}
    if dup_panel["closest"] and dup_panel["signals"]:
        cl = dup_panel["closest"]
        dup_panel["compare"] = [
            {"signal": "amount", "label": "Total amount", "weight": 0.30, "this": inv["total_paise"],
             "other": cl.get("total_paise"), "score": dup_panel["signals"].get("amount")},
            {"signal": "number", "label": "Invoice number", "weight": 0.25, "this": inv["invoice_no_raw"],
             "other": cl.get("invoice_no"), "score": dup_panel["signals"].get("number")},
            {"signal": "date", "label": "Invoice date", "weight": 0.15, "this": inv["invoice_date"],
             "other": cl.get("invoice_date"), "score": dup_panel["signals"].get("date")},
            {"signal": "po", "label": "PO reference", "weight": 0.10, "this": inv["po_id"], "other": cl.get("po_id"),
             "score": dup_panel["signals"].get("po")},
            {"signal": "lines", "label": "Line items", "weight": 0.20, "this": [
                {"description": l["description_raw"], "qty": l["qty"], "unit_price_paise": l["unit_price_paise"]} for l in lines],
             "other": cl.get("lines"), "score": dup_panel["signals"].get("lines")}]
    drafts = (current or {}).get("drafts") or (run_decision or {}).get("drafts") or []
    return {
        "invoice": {k: inv[k] for k in ("id", "file_name", "file_sha256", "page_count", "doc_type", "text_source", "source",
                                        "sample_id", "vendor_id", "vendor_name_raw", "vendor_gstin_raw", "invoice_no_raw",
                                        "invoice_no_canonical", "serial_token", "invoice_date", "date_ambiguous",
                                        "po_ref_raw", "po_id", "po_match_method", "po_match_score", "currency",
                                        "subtotal_paise", "tax_paise", "total_paise", "tax_inclusive", "paid_at",
                                        "info_requested_at", "is_synthetic", "created_at", "current_run_id")},
        "has_pdf": bool(inv["file_path"]),
        "pdf_url": f"/api/invoices/{invoice_id}/pdf" if inv["file_path"] else None,
        "pdf_note": None if inv["file_path"] else "PDF not stored for demo history.",
        "run": run, "stages": stages,
        "fields": fields, "corrections": db.loads(inv["corrections"], {}) or {},
        "lines": lines, "vendor_panel": vendor_panel, "duplicate_panel": dup_panel, "po_panel": po_panel,
        "rules": rules, "decision": current, "system_decision": run_decision, "decision_history": decisions,
        "overridden": bool(current and current["made_by"] == "user"),
        "drafts": drafts, "timeline": timeline,
        "technical": {"extraction": extraction, "config_version": run.get("config_version"),
                      "model_name": run.get("model_name"), "prompt_version": run.get("prompt_version"),
                      "extraction_mode": run.get("extraction_mode")},
    }


def run_detail(run_id: str) -> dict | None:
    with db.conn() as con:
        r = con.execute("SELECT invoice_id FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        return None
    return invoice_detail(r["invoice_id"], run_id)


# ------------------------------------------------------------------ review queue (S5)

TAB_OUTCOMES = {"review": ("route_for_review",), "hold": ("hold_request_info",), "rejected": ("reject",)}


def review_queue(*, tab: str = "review", assigned: str | None = None, min_exposure_paise: int | None = None,
                 vendor_id: str | None = None, category: str | None = None, sort: str = "priority") -> dict:
    now = anchor_now()
    with db.conn() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT i.id AS invoice_id, i.current_run_id AS run_id, i.invoice_no_raw, i.vendor_id, i.total_paise, i.po_id, "
            "i.info_requested_at, i.is_synthetic, v.name AS vendor_name, v.short AS vendor_short, d.* "
            "FROM invoices i JOIN decisions d ON d.id = i.current_decision_id LEFT JOIN vendors v ON v.id = i.vendor_id")]
        first_dec = {r["invoice_id"]: r["created_at"] for r in con.execute(
            "SELECT invoice_id, MIN(created_at) AS created_at FROM decisions GROUP BY invoice_id")}
    counts = {"review": 0, "hold": 0, "rejected": 0, "resolved": 0}
    items = []
    for r in rows:
        # A person has dealt with it: either overrode the decision, or marked it reviewed (accepted the recommendation).
        human = r["made_by"] == "user" or bool(r.get("confirmed_by"))
        resolved = human and (parse_ts(r.get("confirmed_at") or r["created_at"]) or now) >= now - timedelta(days=30)
        tabs = [t for t, outs in TAB_OUTCOMES.items() if r["outcome"] in outs and not (human and t != "rejected")]
        if human:
            tabs = ["resolved"]
        for t in tabs:
            counts[t] += 1
        if tab not in tabs:
            continue
        expl = db.loads(r["explanation"], {}) or {}
        started = parse_ts(first_dec.get(r["invoice_id"])) or now
        age_days = max(0, (now - started).days)
        sla = parse_ts(r["sla_due_at"])
        items.append({
            "invoice_id": r["invoice_id"], "run_id": r["run_id"], "decision_id": r["id"], "outcome": r["outcome"],
            "outcome_label": OUTCOME_LABEL.get(r["outcome"]), "vendor_id": r["vendor_id"],
            "vendor_name": r["vendor_name"], "vendor_short": r["vendor_short"], "invoice_no": r["invoice_no_raw"],
            "po_id": r["po_id"], "gross_paise": r["total_paise"], "exposure_paise": r["exposure_paise"],
            "assigned_to": r["assigned_to"], "category": r["category"],
            "reason": expl.get("short_reason") or expl.get("main_reason") or r["headline"], "headline": r["headline"],
            "recommended_action": expl.get("next_step"), "age_days": age_days,
            "age_badge": ("red" if sla and now > sla and r["outcome"] == "hold_request_info" else
                          ("amber" if age_days >= 1 else None)),
            "sla_due_at": r["sla_due_at"], "sla_breached": bool(sla and now > sla),
            "info_requested_at": r["info_requested_at"], "made_by": r["made_by"], "actor_name": r["actor_name"],
            "reason_code": r["reason_code"], "decided_at": r["created_at"], "is_synthetic": bool(r["is_synthetic"]),
            "driving_rule_ids": db.loads(r["driving_rule_ids"], []),
        })
    if assigned:
        items = [i for i in items if (i["assigned_to"] or "") == assigned]
    if min_exposure_paise:
        items = [i for i in items if (i["exposure_paise"] or 0) > min_exposure_paise]
    if vendor_id:
        items = [i for i in items if i["vendor_id"] == vendor_id]
    if category:
        items = [i for i in items if (i["category"] or "") == category]
    if sort == "age":
        items.sort(key=lambda i: -i["age_days"])
    elif sort == "exposure":
        items.sort(key=lambda i: -(i["exposure_paise"] or 0))
    else:  # exposure times age priority
        items.sort(key=lambda i: -((i["exposure_paise"] or 0) * (1 + i["age_days"])))
    return {"tab": tab, "counts": counts, "open_exceptions": counts["review"] + counts["hold"], "items": items,
            "categories": sorted({i["category"] for i in items if i["category"]})}


# ------------------------------------------------------------------ metrics (S1)

def _week_start(d: datetime) -> str:
    d = d.astimezone(IST)
    return (d - timedelta(days=d.weekday())).date().isoformat()


def _is_open(r: dict) -> bool:
    """An exception is open until a person overrides it or marks it reviewed (same rule as the queue)."""
    return (r["outcome"] in ("route_for_review", "hold_request_info") and r.get("made_by") != "user"
            and not r.get("confirmed_by"))


def metrics(range_days: int = 30) -> dict:
    now = anchor_now()
    start = now - timedelta(days=range_days)
    prev_start = start - timedelta(days=range_days)
    cfg = settings_store.current()[1]
    baseline_min = cfg["global"].get("baseline", 9)
    with db.conn() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT i.id, i.total_paise, i.vendor_id, r.started_at, r.duration_ms, r.status, cd.outcome, cd.made_by, cd.confirmed_by, "
            "cd.exposure_paise, cd.category, cd.created_at AS decided_at, "
            "(SELECT outcome FROM decisions s WHERE s.invoice_id=i.id AND s.made_by='system' ORDER BY s.version DESC LIMIT 1) AS sys_outcome, "
            "(SELECT exposure_paise FROM decisions s WHERE s.invoice_id=i.id AND s.made_by='system' ORDER BY s.version DESC LIMIT 1) AS sys_exposure, "
            "(SELECT category FROM decisions s WHERE s.invoice_id=i.id AND s.made_by='system' ORDER BY s.version DESC LIMIT 1) AS sys_category, "
            "(SELECT MIN(created_at) FROM decisions s WHERE s.invoice_id=i.id) AS first_decided "
            "FROM invoices i JOIN runs r ON r.id = i.current_run_id LEFT JOIN decisions cd ON cd.id = i.current_decision_id")]
        running = con.execute("SELECT COUNT(*) AS n FROM runs WHERE status IN ('queued','running')").fetchone()["n"]

    def window(a, b):
        return [r for r in rows if r["outcome"] and a <= (parse_ts(r["started_at"]) or now) < b]

    def kpis(ws):
        n = len(ws)
        stp = sum(1 for r in ws if r["sys_outcome"] in APPROVED_OUTCOMES)
        durs = [r["duration_ms"] for r in ws if r["duration_ms"]]
        protected = [r for r in ws if r["sys_category"] in ("Duplicate", "Quantity or price above PO")
                     and r["sys_outcome"] in ("route_for_review", "reject", "hold_request_info")]
        return {
            "processed": n,
            "straight_through_rate": round(100.0 * stp / n, 1) if n else None,
            "median_time_to_decision_ms": int(statistics.median(durs)) if durs else None,
            "open_exceptions": sum(1 for r in ws if _is_open(r)),
            "value_protected_paise": sum(r["sys_exposure"] or 0 for r in protected),
            "value_approved_paise": sum(r["total_paise"] or 0 for r in ws if r["outcome"] in APPROVED_OUTCOMES),
            "_protected": protected,
        }

    cur_w = window(start, now + timedelta(days=3650))
    prev_w = window(prev_start, start)
    k, kp = kpis(cur_w), kpis(prev_w)
    contributors = {}
    for r in k.pop("_protected"):
        contributors.setdefault(r["sys_category"], {"category": r["sys_category"], "count": 0, "value_paise": 0})
        contributors[r["sys_category"]]["count"] += 1
        contributors[r["sys_category"]]["value_paise"] += r["sys_exposure"] or 0
    kp.pop("_protected")
    open_all = [r for r in rows if _is_open(r)]
    oldest = max([(now - (parse_ts(r["first_decided"]) or now)).days for r in open_all] or [0])

    def trend(a, b):
        if a is None or b is None:
            return None
        return round(a - b, 1) if isinstance(a, float) else a - b

    tiles = {key: {"value": k[key], "previous": kp[key], "change": trend(k[key], kp[key])} for key in k}
    tiles["open_exceptions"]["value_all_time"] = len(open_all)
    tiles["median_time_to_decision_ms"]["manual_baseline_ms"] = int(baseline_min * 60000)
    tiles["value_protected_paise"]["contributors"] = sorted(contributors.values(), key=lambda c: -c["value_paise"])
    # charts
    weeks: dict[str, dict] = {}
    for r in cur_w:
        wk = _week_start(parse_ts(r["started_at"]) or now)
        w = weeks.setdefault(wk, {"week_start": wk, "auto_approve": 0, "approve_with_note": 0, "route_for_review": 0,
                                  "hold_request_info": 0, "reject": 0, "_d": []})
        w[r["outcome"]] = w.get(r["outcome"], 0) + 1
        if r["duration_ms"]:
            w["_d"].append(r["duration_ms"])
    per_week, median_week = [], []
    for wk in sorted(weeks):
        w = weeks[wk]
        d = w.pop("_d")
        per_week.append(w)
        median_week.append({"week_start": wk, "median_ms": int(statistics.median(d)) if d else None})
    mix = {o: sum(1 for r in cur_w if r["outcome"] == o) for o in OUTCOME_LABEL}
    reasons: dict[str, int] = {}
    for r in cur_w:
        if r["outcome"] in ("route_for_review", "hold_request_info", "reject") and r["category"]:
            reasons[r["category"]] = reasons.get(r["category"], 0) + 1
    banner = {"review": sum(1 for r in open_all if r["outcome"] == "route_for_review"),
              "hold": sum(1 for r in open_all if r["outcome"] == "hold_request_info"), "oldest_days": oldest}
    banner["text"] = (f"{banner['review']} invoice{'s' if banner['review'] != 1 else ''} need review, {banner['hold']} on "
                      f"hold, oldest {oldest} day{'s' if oldest != 1 else ''}") if open_all else None
    return {"range_days": range_days, "as_of": now.isoformat(), "period_start": start.isoformat(), "tiles": tiles,
            "charts": {"decisions_per_week": per_week, "outcome_mix": mix,
                       "top_exception_reasons": sorted(({"category": c, "count": n} for c, n in reasons.items()),
                                                       key=lambda x: -x["count"]),
                       "median_time_per_week": median_week},
            "banner": banner, "running": running,
            "estimated_minutes_saved": round(k["processed"] * baseline_min - sum(
                (r["duration_ms"] or 0) for r in cur_w) / 60000.0, 1)}
