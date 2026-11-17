"""Demo reset and seed loader (spec 9.1-9.3). Loads vendors, POs, rule-set history, three named history
invoices (run through the real pipeline from their PDFs at their historical dates) and 57 synthetic
metadata-only runs, for 60 runs in total and 14 open exceptions."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from . import config, db, pipeline
from .catalogue import CATEGORY_BY_RULE, OUTCOME_LONG, RULES, STAGES, default_config
from .events import Clock
from .settings_store import _merge
from .textutil import fmt_date, inr0

IST = timezone(timedelta(hours=5, minutes=30))


def _seed_file():
    return config.SAMPLES_DIR / "seed_data.json"


def load_seed_data() -> dict:
    return json.loads(_seed_file().read_text(encoding="utf-8"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_master(con, data: dict) -> None:
    now = db.now_iso()
    for v in data["vendors"]:
        con.execute("INSERT INTO vendors (id, name, short, aliases, gstin, status, payment_terms_days, bank_name, "
                    "bank_account_no, bank_ifsc, bank_changed_at, bank_verified_by, contact_phone, contact_email, address, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (v["id"], v["name"], v.get("short"), db.dumps(v.get("aliases", [])), v.get("gstin"), v["status"],
                     v.get("payment_terms_days", 30), v.get("bank_name"), v.get("bank_account_no"), v.get("bank_ifsc"),
                     v.get("bank_changed_at"), "Rahul Mehta" if v.get("bank_changed_at") else None, v.get("contact_phone"),
                     v.get("contact_email"), v.get("address"), now, now))
    for p in data["purchase_orders"]:
        con.execute("INSERT INTO purchase_orders (id, vendor_id, issue_date, valid_to, status_override, currency, is_seed, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (p["id"], p["vendor_id"], p["issue_date"], p["valid_to"], p.get("status_override"), "INR",
                     1 if p.get("is_seed") else 0, now, now))
        for i, (code, desc, uom, qty, price, rate, opening) in enumerate(p["lines"], 1):
            con.execute("INSERT INTO po_lines (po_id, line_no, item_code, description, uom, ordered_qty, unit_price_paise, "
                        "tax_rate_pct, opening_billed_qty) VALUES (?,?,?,?,?,?,?,?,?)",
                        (p["id"], i, code, desc, uom, qty, int(round(price * 100)), rate, opening))


def seed_settings(con, data: dict) -> None:
    for s in data["settings_history"]:
        cfg = _merge(default_config(), s["patch"])
        cfg["global"]["cap"] = cfg["rules"]["R15"]["cap"]
        con.execute("INSERT INTO settings_versions (version, config, changed_by, reason, summary, changes, changed_at) "
                    "VALUES (?,?,?,?,?,?,?)", (s["version"], db.dumps(cfg), s["by"], s["reason"], s["summary"],
                                               db.dumps([]), s["when"]))
        db.audit(con, actor_type="human" if s["by"] != "System" else "system", actor_id=s["by"],
                 event_type="settings_changed", object_type="setting", object_id=f"v{s['version']}",
                 summary=f"Rule set version {s['version']}: {s['summary']}",
                 payload={"version": s["version"], "reason": s["reason"]}, ts=s["when"])


def seed_named_history(data: dict) -> list[dict]:
    results = []
    for h in data["named_history"]:
        path = config.SAMPLES_DIR / h["file"]
        raw = path.read_bytes()
        decided = datetime.fromisoformat(h["decided_at"].replace("Z", "+00:00"))
        start = decided - timedelta(seconds=13)
        with db.tx() as con:
            iid = pipeline.create_invoice(con, file_name=path.name, file_path=str(path), data=raw, source=h["source"],
                                          sample_id=None, created_at=_iso(start - timedelta(seconds=2)))
            rid = pipeline.create_run(con, invoice_id=iid, source=h["source"], pace=0, use_cache=True,
                                      triggered_by="system", created_at=_iso(start))
            db.audit(con, actor_type="system", actor_id="Email intake", event_type="run_created", object_type="invoice",
                     object_id=iid, run_id=rid, invoice_id=iid, summary=f"Received {path.name} by email",
                     payload={"run": rid, "source": h["source"], "file": path.name}, ts=_iso(start))
        res = pipeline.run_sync(rid, clock=Clock(start), publish=False, force_text_parser=True)
        if res["outcome"] != h["expected_outcome"]:
            raise RuntimeError(f"Seed history {path.name} decided {res['outcome']}, expected {h['expected_outcome']}")
        if h.get("paid_at"):
            with db.tx() as con:
                con.execute("UPDATE invoices SET paid_at=? WHERE id=?", (h["paid_at"], iid))
                db.audit(con, actor_type="system", actor_id="Payment run", event_type="payment_recorded",
                         object_type="invoice", object_id=iid, invoice_id=iid,
                         summary=f"Paid in the payment run of {fmt_date(h['paid_at'])}", payload={"paid_at": h["paid_at"]},
                         ts=h["paid_at"] + "T06:30:00.000Z")
        results.append({"invoice_id": iid, "run_id": rid, **res})
    return results


GENERIC_PASS = {
    "R01": "Invoice number, date, vendor, total and currency are all present.",
    "R03": "Invoice date is not in the future and is after the PO date.",
    "R05": "Bank account on the invoice matches the account on file.",
    "R06": "Not similar to any earlier invoice.",
    "R08": "The PO is open and the invoice date is inside its validity window.",
    "R09": "Every invoice line maps to a line on the PO.",
    "R10": "Unit prices match the PO.",
    "R11": "Quantities are within what remains on the PO.",
    "R12": "Invoice value fits within the PO value remaining.",
    "R14": "Subtotal plus tax equals the stated total.",
    "R16": "Invoice currency (INR) matches the PO currency.",
}
SEV_OF = {"approve_with_note": "note", "route_for_review": "review", "hold_request_info": "hold", "reject": "reject"}
PREFIX = {"auto_approve": "Approved", "approve_with_note": "Approved with a note", "route_for_review": "Review needed",
          "hold_request_info": "Hold", "reject": "Reject"}


def seed_synthetic(data: dict) -> int:
    syn = data["synthetic"]
    rng = random.Random(syn["seed"])
    cat = syn["catalog"]
    as_of = datetime.fromisoformat(data["as_of"]).replace(hour=11, minute=5, tzinfo=IST)
    serial = {k: v["serial_from"] for k, v in cat.items()}
    vendors = ["V-101", "V-102", "V-103", "V-104", "V-105"]
    specs = []
    for _ in range(syn["counts"]["auto_approve"]):
        specs.append({"outcome": "auto_approve", "vendor": rng.choice(vendors)})
    for i in range(syn["counts"]["approve_with_note"]):
        rid, reason = syn["note_reasons"][i % len(syn["note_reasons"])]
        specs.append({"outcome": "approve_with_note", "vendor": rng.choice(vendors), "rule": rid, "reason": reason})
    for out, vid, rid, reason, exp, owner, age, rec in syn["exceptions"]:
        specs.append({"outcome": out, "vendor": vid, "rule": rid, "reason": reason, "exposure": exp, "owner": owner,
                      "age": age, "rec": rec})
    count = 0
    with db.tx() as con:
        po_lines = {r["po_id"]: dict(r) for r in con.execute("SELECT * FROM po_lines")}
        vend = {r["id"]: dict(r) for r in con.execute("SELECT * FROM vendors")}
        for n, s in enumerate(specs, 1):
            vid = s["vendor"]
            c = cat[vid]
            serial[vid] += 1 + rng.randrange(3)
            inv_no = f"{c['prefix']}{serial[vid]}"
            desc, price, uom = c["item"]
            qty = max(2, round((18000 + rng.random() * 420000) / price))
            if s["outcome"] in ("route_for_review", "hold_request_info", "reject") and s.get("exposure"):
                qty = max(2, round(s["exposure"] * rng.uniform(2.2, 6.0) / price))
            sub = int(round(qty * price * 100))
            tax = int(round(sub * c["rate"] / 100))
            total = sub + tax
            if "age" in s:
                decided = as_of - timedelta(days=s["age"], hours=1 + rng.random() * 5)
            else:
                decided = as_of - timedelta(days=rng.random() * 28.0)
                decided = decided.replace(hour=9 + rng.randrange(8), minute=rng.randrange(60))
                if decided > as_of:
                    decided = as_of - timedelta(hours=2 + n % 5)
            dur = 9000 + rng.randrange(8000)
            start = decided - timedelta(milliseconds=dur)
            inv_date = (decided - timedelta(days=2 + rng.randrange(6))).date()
            rule = s.get("rule")
            if rule == "R03":
                inv_date = (decided - timedelta(days=190 + rng.randrange(20))).date()
            if rule == "R01" and "date" in s["reason"]:
                inv_date = None
            if rule == "R01" and "number" in s["reason"]:
                inv_no = None
            po_id = c["po"]
            if rule == "R07" and s["outcome"] == "hold_request_info":
                po_id = None
            scanned = rule == "R02"
            low = round(0.93 + rng.random() * 0.06, 2) if s["outcome"] == "auto_approve" else (
                round(0.78 + rng.random() * 0.11, 2) if rule == "R02" and s["outcome"] == "approve_with_note" else (
                    0.62 if rule == "R02" else round(0.9 + rng.random() * 0.07, 2)))
            iid = f"INV-S{n:03d}"
            run_id = f"run_s{n:03d}"
            fields = {}
            for k, label, val in (("vendor_name", "Vendor", vend[vid]["name"]), ("invoice_no", "Invoice no.", inv_no),
                                  ("invoice_date", "Invoice date", inv_date.isoformat() if inv_date else None),
                                  ("po_reference", "PO reference", po_id), ("currency", "Currency", "INR"),
                                  ("subtotal", "Subtotal", f"{sub / 100:.2f}"), ("tax_total", "Tax (GST)", f"{tax / 100:.2f}"),
                                  ("total", "Total", f"{total / 100:.2f}")):
                conf = low if k == ("total" if rule == "R02" else "invoice_no") else round(max(low, 0.95), 2)
                fields[k] = {"name": k, "label": label, "value": val, "effective_confidence": conf if val else 0.0,
                             "model_confidence": conf, "source": ("image read" if scanned else "text layer") if val else "not found"}
            con.execute(
                "INSERT INTO invoices (id, file_name, file_path, file_sha256, page_count, doc_type, text_source, source, "
                "vendor_id, vendor_name_raw, vendor_gstin_raw, invoice_no_raw, invoice_no_canonical, serial_token, "
                "invoice_date, po_ref_raw, po_id, po_match_method, po_match_score, currency, subtotal_paise, tax_paise, "
                "total_paise, fields, is_synthetic, current_run_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (iid, (inv_no or f"invoice-{n}").replace("/", "-") + ".pdf", None, None, 1,
                 "scanned" if scanned else "text", "none" if scanned else "text_layer", "seed", vid, vend[vid]["name"],
                 vend[vid]["gstin"], inv_no, "".join(ch for ch in (inv_no or "") if ch.isalnum()).upper() or None,
                 str(serial[vid]), inv_date.isoformat() if inv_date else None, po_id, po_id,
                 "explicit" if po_id else "none", 1.0 if po_id else None, "INR", sub, tax, total, db.dumps(fields), 1,
                 run_id, _iso(start)))
            pl = po_lines.get(po_id) if po_id else None
            con.execute("INSERT INTO line_items (invoice_id, line_no, description_raw, description_norm, qty, uom, "
                        "unit_price_paise, amount_paise, pretax_amount_paise, tax_rate_pct, matched_po_line_ids, match_method, "
                        "match_score, confidence, alloc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (iid, 1, desc, desc.lower(), qty, uom, int(round(price * 100)), sub, sub, c["rate"],
                         db.dumps([pl["id"]] if pl else []), "sku" if pl else "none", 1.0 if pl else 0.0, low,
                         db.dumps([{"po_line_id": pl["id"], "qty": qty, "amount_paise": sub}] if pl else [])))
            con.execute("INSERT INTO runs (id, invoice_id, source, status, current_stage, started_at, finished_at, "
                        "duration_ms, pace, pace_ms, use_cache, config_version, model_name, prompt_version, extraction_mode, "
                        "triggered_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, iid, "seed", "completed", 9, _iso(start), _iso(decided), dur, "normal", 0, 1, 14,
                         config.DEFAULT_MODELS["anthropic"], config.PROMPT_VERSION, "seed", "system", _iso(start)))
            sev = SEV_OF.get(s["outcome"])
            for r in RULES:
                rid = r["id"]
                if rule == rid and sev:
                    sv, msg = sev, s["reason"]
                else:
                    sv = "pass"
                    msg = GENERIC_PASS.get(rid) or {
                        "R02": f"All key fields were read with confidence of 0.90 or more (lowest {max(low, 0.9):.2f}).",
                        "R04": f"{vend[vid]['name']} is an approved vendor (matched by GSTIN {vend[vid]['gstin']}).",
                        "R07": f"{po_id} was written on the invoice." if po_id else "No PO needed.",
                        "R13": f"GST of {inr0(tax)} is correct at {c['rate']}%.",
                        "R15": f"Total {inr0(total)} is below the ₹10,00,000 manager sign-off limit.",
                    }.get(rid, "Passed.")
                con.execute("INSERT INTO rule_results (run_id, rule_id, stage_no, rule_name, severity, skipped, message_plain, "
                            "facts, threshold_used, exposure_paise) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (run_id, rid, r["stage"], r["name"], sv, 0, msg, db.dumps({"synthetic": True}), db.dumps({}),
                             int(s.get("exposure", 0)) * 100 if rule == rid and sev else 0))
            t = start
            for st in STAGES:
                step = dur // 9
                drv_stage = next((x["stage"] for x in RULES if x["id"] == rule), None)
                ssev = sev if (sev and drv_stage == st["no"]) else ("pass" if st["no"] != 8 else (sev or "pass"))
                con.execute("INSERT INTO stage_results (run_id, stage_no, stage_name, status, severity_max, started_at, "
                            "ended_at, duration_ms, input_summary, output_summary, message) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (run_id, st["no"], st["name"], "done", ssev, _iso(t), _iso(t + timedelta(milliseconds=step)),
                             step, "{}", "{}", "Seeded history (summary only)."))
                t += timedelta(milliseconds=step)
            if s["outcome"] == "auto_approve":
                headline = "Approved: everything checks out and it is safe to pay."
                reason = f"All 16 checks passed. Prices, quantities, GST and total match {po_id}."
            else:
                r0 = s["reason"].rstrip(".")
                headline = f"{PREFIX[s['outcome']]}: {r0[0].lower() + r0[1:]}."
                reason = s["reason"]
            category = CATEGORY_BY_RULE.get(rule) if rule and s["outcome"] != "approve_with_note" else None
            if rule == "R07" and s["outcome"] == "route_for_review":
                category = "Vendor problem"
            expl = {"headline": headline, "ok": [f"{vend[vid]['short']} is an approved vendor"] if rule != "R04" else [],
                    "attention": [s["reason"]] if s["outcome"] != "auto_approve" else [],
                    "next_step": (s.get("rec", "") + ".") if s.get("rec") else (
                        "None needed. The invoice is in the payment queue." if s["outcome"] == "auto_approve" else
                        "None needed. The invoice is in the payment queue with the note attached."),
                    "alternative_step": None, "confidence_note": f"Lowest field confidence {low:.2f}.",
                    "main_reason": reason, "short_reason": reason, "polished": False,
                    "decision_label": OUTCOME_LONG[s["outcome"]], "synthetic": True}
            exposure = int(s.get("exposure", 0)) * 100 if s["outcome"] in ("route_for_review", "hold_request_info", "reject") else 0
            sla = None
            if s["outcome"] == "hold_request_info":
                sla = pipeline.business_days_after(decided, 3)
            elif s["outcome"] == "route_for_review":
                sla = pipeline.business_days_after(decided, 1)
            cur = con.execute("INSERT INTO decisions (run_id, invoice_id, version, outcome, headline, explanation, "
                              "driving_rule_ids, exposure_paise, category, assigned_to, sla_due_at, made_by, actor_name, "
                              "drafts, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (run_id, iid, 1, s["outcome"], headline, db.dumps(expl), db.dumps([rule] if sev else []),
                               exposure, category, s.get("owner"), _iso(sla) if sla else None, "system", "Ledgerlight",
                               "[]", _iso(decided)))
            con.execute("UPDATE invoices SET current_decision_id=? WHERE id=?", (cur.lastrowid, iid))
            db.audit(con, actor_type="system", actor_id="Email intake", event_type="run_created", object_type="invoice",
                     object_id=iid, run_id=run_id, invoice_id=iid,
                     summary=f"Received {inv_no or 'an invoice'} from {vend[vid]['short']} by email",
                     payload={"run": run_id, "source": "seed"}, ts=_iso(start))
            db.audit(con, actor_type="system", actor_id="Ledgerlight rules", event_type="decision_made",
                     object_type="invoice", object_id=iid, run_id=run_id, invoice_id=iid,
                     summary=f"{OUTCOME_LONG[s['outcome']]}: {reason}", outcome=s["outcome"],
                     payload={"decision": s["outcome"], "exposure_paise": exposure, "assigned_to": s.get("owner"),
                              "config_version": 14, "synthetic": True}, ts=_iso(decided))
            count += 1
    return count


def seed_audit_extras(con, data: dict) -> None:
    for a in data.get("audit_extras", []):
        db.audit(con, actor_type=a["actor_type"], actor_id=a["actor_id"], event_type=a["event_type"],
                 object_type=a["object_type"], object_id=a["object_id"], summary=a["summary"], payload=a["payload"],
                 ts=a["ts"])


def is_seeded() -> bool:
    with db.conn() as con:
        return bool(con.execute("SELECT COUNT(*) AS n FROM vendors").fetchone()["n"])


def reset_and_seed(actor: str = "system") -> dict:
    data = load_seed_data()
    db.reset_schema()
    with db.tx() as con:
        seed_master(con, data)
        seed_settings(con, data)
        seed_audit_extras(con, data)
    named = seed_named_history(data)
    n_syn = seed_synthetic(data)
    with db.tx() as con:
        db.audit(con, actor_type="human" if actor != "system" else "system", actor_id=actor, event_type="demo_reset",
                 object_type="system", object_id="demo", summary="Demo data reset and seeded",
                 payload={"named_history": len(named), "synthetic": n_syn})
    with db.conn() as con:
        runs = con.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
        open_exc = con.execute("SELECT COUNT(*) AS n FROM invoices i JOIN decisions d ON d.id=i.current_decision_id "
                               "WHERE d.outcome IN ('route_for_review','hold_request_info')").fetchone()["n"]
    return {"runs": runs, "named_history": [{"invoice_id": n["invoice_id"], "run_id": n["run_id"], "outcome": n["outcome"]}
                                            for n in named], "synthetic": n_syn, "open_exceptions": open_exc}


def ensure_seeded() -> None:
    if not is_seeded():
        reset_and_seed()


def build_template() -> dict:
    """Seed the template database that every visitor's sandbox is copied from (sandbox mode, at startup)."""
    with db.use_sandbox(db.TEMPLATE):
        return reset_and_seed()


def reset_sandbox(actor: str = "system") -> dict:
    """Demo reset for the current visitor only: a fresh copy of the template."""
    sb = db.current_sandbox()
    db.ensure_sandbox(sb, fresh=True)
    with db.tx() as con:
        db.audit(con, actor_type="human" if actor != "system" else "system", actor_id=actor, event_type="demo_reset",
                 object_type="system", object_id="demo", summary="Demo data reset (this visitor's sandbox)", payload={})
    with db.conn() as con:
        runs = con.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
        open_exc = con.execute("SELECT COUNT(*) AS n FROM invoices i JOIN decisions d ON d.id=i.current_decision_id "
                               "WHERE d.outcome IN ('route_for_review','hold_request_info')").fetchone()["n"]
    return {"runs": runs, "named_history": [], "synthetic": None, "open_exceptions": open_exc, "sandbox": sb}
