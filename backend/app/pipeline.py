"""The nine-stage pipeline (spec 2). Runs in a worker thread, persists every stage, rule, decision and
event, and streams events live. Later stages always run after a failed rule (principle 6)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, db, matching, pdfio, settings_store
from .catalogue import OUTCOME_LONG, SEV_RANK, STAGE_NAME
from .events import BUS, Clock, Emitter
from .explain import build as build_explanation
from .explain import drafts as build_drafts
from .explain import maybe_polish
from .normalize import normalise
from .rules import STAGE_RULES, apply_enabled, decide, r03
from .textutil import fmt_date, fmt_qty, inr, inr0, mask_account, to_date

log = logging.getLogger("ledgerlight.pipeline")

CANCEL: dict[str, threading.Event] = {}


_VENDOR_LOCKS: dict[str, threading.Lock] = {}
_VENDOR_LOCKS_GUARD = threading.Lock()


def _vendor_lock(key: str) -> threading.Lock:
    with _VENDOR_LOCKS_GUARD:
        return _VENDOR_LOCKS.setdefault(key, threading.Lock())


class Cancelled(Exception):
    pass


class StageFailed(Exception):
    def __init__(self, stage_no: int, message: str):
        super().__init__(message)
        self.stage_no = stage_no
        self.message = message


def as_of_date() -> date:
    return date.fromisoformat(config.AS_OF) if config.AS_OF else date.today()


def business_days_after(start: datetime, n: int) -> datetime:
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


# ------------------------------------------------------------------ run creation

def create_invoice(con, *, file_name: str, file_path: str, data: bytes, source: str, sample_id: str | None,
                   created_at: str | None = None, invoice_id: str | None = None) -> str:
    iid = invoice_id or db.new_id("INV-", 4).upper().replace("INV-", "INV-")
    con.execute("INSERT INTO invoices (id, file_name, file_path, file_sha256, file_size, source, sample_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (iid, file_name, file_path, pdfio.sha256(data), len(data), source, sample_id,
                                             created_at or db.now_iso()))
    return iid


def create_run(con, *, invoice_id: str, source: str, pace: str | int | None, use_cache: bool, triggered_by: str,
               parent_run_id: str | None = None, created_at: str | None = None) -> str:
    rid = db.new_id("run_", 3)
    while con.execute("SELECT 1 FROM runs WHERE id=?", (rid,)).fetchone():
        rid = db.new_id("run_", 3)
    pms = config.pace_ms(pace)
    ver, _ = settings_store.current(con)
    con.execute("INSERT INTO runs (id, invoice_id, source, status, current_stage, pace, pace_ms, use_cache, "
                "config_version, model_name, prompt_version, extraction_mode, parent_run_id, triggered_by, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, invoice_id, source, "queued", 0, str(pace if pace is not None else config.DEFAULT_PACE), pms,
                 1 if use_cache else 0, ver, None, None, None, parent_run_id, triggered_by, created_at or db.now_iso()))
    con.execute("UPDATE invoices SET current_run_id=? WHERE id=?", (rid, invoice_id))
    return rid


# ------------------------------------------------------------------ the runner

class Runner:
    def __init__(self, run_id: str, clock: Clock | None = None, publish: bool = True, force_text_parser: bool = False):
        self.run_id = run_id
        self.clock = clock or Clock()
        self.force_text = force_text_parser
        with db.conn() as con:
            self.run_row = dict(con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
            self.inv = dict(con.execute("SELECT * FROM invoices WHERE id=?", (self.run_row["invoice_id"],)).fetchone())
            self.cfg_version, self.cfg = settings_store.current(con)
        self.pace = int(self.run_row.get("pace_ms") or 0)
        self.em = Emitter(run_id, self.clock, self.pace, publish=publish)
        self.cancel = CANCEL.setdefault(run_id, threading.Event())
        self.ctx: dict = {"cfg": self.cfg, "as_of": as_of_date(), "rules": {}, "extraction_status": "ok",
                          "vendor_match": {"vendor": None, "method": "none", "score": 0.0},
                          "po_res": {"method": "none", "po": None, "candidates": []}, "alignment": [], "dup": {"score": 0}}
        self.t_start = time.monotonic()

    # ---------------- helpers
    def log(self, stage: int, level: str, text: str, pacing: bool = False):
        self.em.emit("log", {"stage_no": stage, "level": level, "text": text, "display_pacing": pacing})
        self.em.tick()

    def rule(self, result: dict):
        result = apply_enabled(result, self.cfg)
        self.ctx["rules"][result["rule_id"]] = result
        public = {k: result[k] for k in ("rule_id", "rule_name", "stage_no", "severity", "skipped", "message",
                                         "exposure_paise")}
        self.em.emit("rule_result", public)
        lvl = "info" if result["skipped"] else {"pass": "pass", "note": "warn", "review": "warn", "hold": "fail",
                                                "reject": "fail"}[result["severity"]]
        self.log(result["stage_no"], lvl, f"{result['rule_id']} {result['rule_name']}: "
                                          f"{'SKIPPED' if result['skipped'] else result['severity'].upper()}. {result['message']}")
        with db.tx() as con:
            con.execute("INSERT OR REPLACE INTO rule_results (run_id, rule_id, stage_no, rule_name, severity, skipped, "
                        "message_plain, facts, threshold_used, exposure_paise) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (self.run_id, result["rule_id"], result["stage_no"], result["rule_name"], result["severity"],
                         1 if result["skipped"] else 0, result["message"], db.dumps(result["facts"]),
                         db.dumps(result["threshold_used"]), result["exposure_paise"]))
            if not result["skipped"] and result["severity"] != "pass":
                db.audit(con, actor_type="system", actor_id="Ledgerlight rules", event_type="rule_evaluated",
                         object_type="invoice", object_id=self.inv["id"], run_id=self.run_id, invoice_id=self.inv["id"],
                         summary=f"{result['rule_name']}: {result['message']}", outcome=result["severity"],
                         payload={"rule": result["rule_id"], "severity": result["severity"], "facts": result["facts"],
                                  "threshold": result["threshold_used"], "config_version": self.cfg_version},
                         ts=self.clock.iso())

    def stage(self, n: int, fn) -> dict:
        if self.cancel.is_set():
            raise Cancelled()
        t0 = time.monotonic()
        started = self.clock.iso()
        self.em.emit("stage_started", {"stage_no": n, "name": STAGE_NAME[n]})
        with db.tx() as con:
            con.execute("UPDATE runs SET current_stage=? WHERE id=?", (n, self.run_id))
            con.execute("INSERT OR REPLACE INTO stage_results (run_id, stage_no, stage_name, status, started_at) "
                        "VALUES (?,?,?,?,?)", (self.run_id, n, STAGE_NAME[n], "running", started))
        BUS.publish_global({"event": "run_stage", "data": {"run_id": self.run_id, "invoice_id": self.inv["id"],
                                                            "stage_no": n, "name": STAGE_NAME[n]}})
        try:
            out = fn() or {}
        except (Cancelled, StageFailed):
            raise
        except Exception as e:  # unexpected bug or I/O error: the run fails visibly, never silently
            log.exception("stage %s failed", n)
            raise StageFailed(n, f"{type(e).__name__}: {e}")
        work_ms = int((time.monotonic() - t0) * 1000)
        if self.pace > 0:
            remaining = self.pace / 1000.0 - (time.monotonic() - t0)
            if remaining > 0:
                time.sleep(remaining)
        dur = int((time.monotonic() - t0) * 1000)
        sev = "pass"
        for r in self.ctx["rules"].values():
            if r["stage_no"] == n and not r["skipped"] and SEV_RANK[r["severity"]] > SEV_RANK[sev]:
                sev = r["severity"]
        if n == 8:
            sev = self.ctx["decision"]["worst"]
        status = out.get("status", "done")
        data = {"stage_no": n, "name": STAGE_NAME[n], "status": status, "severity_max": sev, "duration_ms": dur,
                "work_ms": work_ms, "display_pacing_ms": max(0, dur - work_ms), "message": out.get("message", ""),
                "input": out.get("input", {}), "output": out.get("output", {})}
        with db.tx() as con:
            con.execute("UPDATE stage_results SET status=?, severity_max=?, ended_at=?, duration_ms=?, input_summary=?, "
                        "output_summary=?, message=? WHERE run_id=? AND stage_no=?",
                        (status, sev, self.clock.iso(), dur, db.dumps(data["input"]), db.dumps(data["output"]),
                         data["message"], self.run_id, n))
            db.audit(con, actor_type="ai" if n == 2 and self.ctx.get("extractor") == "llm" else "system",
                     actor_id=config.llm_model() if n == 2 and self.ctx.get("extractor") == "llm" else "Ledgerlight pipeline",
                     event_type="stage_completed", object_type="invoice", object_id=self.inv["id"], run_id=self.run_id,
                     invoice_id=self.inv["id"], summary=f"Stage {n} {STAGE_NAME[n]}: {data['message']}", outcome=sev,
                     payload={"stage_no": n, "status": status, "duration_ms": dur, "work_ms": work_ms,
                              **({"model": config.llm_model(), "prompt_version": config.PROMPT_VERSION}
                                 if n == 2 and self.ctx.get("extractor") == "llm" else {})},
                     ts=self.clock.iso())
        self.em.emit("stage_completed", data)
        return out

    # ---------------- main
    def run(self) -> dict:
        with db.tx() as con:
            con.execute("UPDATE runs SET status='running', started_at=?, config_version=? WHERE id=?",
                        (self.clock.iso(), self.cfg_version, self.run_id))
        self.em.emit("run_started", {"run_id": self.run_id, "invoice_id": self.inv["id"], "file_name": self.inv["file_name"],
                                     "source": self.run_row["source"], "pace_ms": self.pace, "config_version": self.cfg_version,
                                     "stages": [{"stage_no": n, "name": STAGE_NAME[n]} for n in range(1, 10)]})
        BUS.publish_global({"event": "run_created", "data": {"run_id": self.run_id, "invoice_id": self.inv["id"],
                                                             "file_name": self.inv["file_name"]}})
        try:
            self.stage(1, self.s1_ingest)
            self.stage(2, self.s2_extract)
            self.stage(3, self.s3_normalise)
            self.stage(4, self.s4_vendor)
            # Duplicate check through decision run one at a time per vendor: two copies of one invoice uploaded in
            # the same batch would otherwise both pass R06, because each only sees invoices that already have a
            # decision.
            vendor = (self.ctx.get("vendor_match") or {}).get("vendor") or {}
            with _vendor_lock(vendor.get("id") or "no-vendor"):
                self.stage(5, self.s5_duplicate)
                self.stage(6, self.s6_po)
                self.stage(7, self.s7_validate)
                self.stage(8, self.s8_decide)
                self.stage(9, self.s9_explain)
        except Cancelled:
            return self._finish("cancelled", error="Cancelled by user")
        except StageFailed as e:
            self.em.emit("stage_completed", {"stage_no": e.stage_no, "name": STAGE_NAME[e.stage_no], "status": "failed",
                                             "severity_max": None, "duration_ms": 0, "message": e.message,
                                             "input": {}, "output": {}})
            with db.tx() as con:
                con.execute("UPDATE stage_results SET status='failed', message=?, ended_at=? WHERE run_id=? AND stage_no=?",
                            (e.message, self.clock.iso(), self.run_id, e.stage_no))
            self.em.emit("run_failed", {"stage_no": e.stage_no, "error": e.message, "retryable": True})
            return self._finish("failed", error=e.message)
        return self._finish("completed")

    def _finish(self, status: str, error: str | None = None) -> dict:
        dur = int((time.monotonic() - self.t_start) * 1000)
        with db.tx() as con:
            con.execute("UPDATE runs SET status=?, finished_at=?, duration_ms=?, error=? WHERE id=?",
                        (status, self.clock.iso(), dur, error, self.run_id))
            if status != "completed":
                db.audit(con, actor_type="system", actor_id="Ledgerlight pipeline", event_type="run_" + status,
                         object_type="invoice", object_id=self.inv["id"], run_id=self.run_id, invoice_id=self.inv["id"],
                         summary=f"Run {self.run_id} {status}" + (f": {error}" if error else ""), ts=self.clock.iso())
        if status == "completed":
            self.em.emit("run_completed", {"run_id": self.run_id, "duration_ms": dur,
                                           "outcome": self.ctx["decision"]["outcome"]})
        elif status == "cancelled":
            self.em.emit("run_cancelled", {"run_id": self.run_id, "reason": error})
        BUS.publish_global({"event": "run_" + status, "data": {"run_id": self.run_id, "invoice_id": self.inv["id"],
                                                               "outcome": self.ctx.get("decision", {}).get("outcome")}})
        CANCEL.pop(self.run_id, None)
        return {"run_id": self.run_id, "status": status, "outcome": self.ctx.get("decision", {}).get("outcome"),
                "error": error}

    # ---------------- stage 1
    def s1_ingest(self):
        path = Path(self.inv["file_path"])
        data = path.read_bytes()
        self.data = data
        sha = pdfio.sha256(data)
        info = pdfio.inspect(data)
        self.info = info
        kb = max(1, len(data) // 1024)
        self.log(1, "info", f"File stored: {self.inv['file_name']} ({kb} KB, {info['page_count']} page"
                            f"{'s' if info['page_count'] > 1 else ''})")
        with db.conn() as con:
            hit = con.execute("SELECT id, invoice_no_raw FROM invoices WHERE file_sha256=? AND id != ? AND "
                              "current_decision_id IS NOT NULL LIMIT 1", (sha, self.inv["id"])).fetchone()
            n_prior = con.execute("SELECT COUNT(*) AS n FROM invoices WHERE id != ? AND current_decision_id IS NOT NULL",
                                  (self.inv["id"],)).fetchone()["n"]
        if hit:
            self.log(1, "warn", f"SHA-256 {sha[:4]}...{sha[-4:]} matches an earlier file "
                                f"({hit['invoice_no_raw'] or hit['id']}). Stage 5 will check it.")
        else:
            self.log(1, "info", f"SHA-256 {sha[:4]}...{sha[-4:]} differs from all {n_prior} earlier files")
        if info["doc_type"] == "text":
            self.log(1, "pass", f"Text layer found ({int(info['avg_chars'])} characters per page). "
                                + ("Document looks like an invoice." if info["looks_like_invoice"] else
                                   "No invoice wording found."))
        elif info["text_source"] == "ocr_layer":
            self.log(1, "warn", "Scanned image (a photo or scan) with an embedded OCR text layer from the scanning app.")
        else:
            self.log(1, "warn", "Fewer than 50 text characters per page: scanned image. It must be read by vision.")
        if self.pace:
            self.log(1, "info", f"Display pacing: minimum {self.pace} ms per stage so each step is visible", pacing=True)
        with db.tx() as con:
            con.execute("UPDATE invoices SET file_sha256=?, page_count=?, doc_type=?, text_source=? WHERE id=?",
                        (sha, info["page_count"], info["doc_type"], info["text_source"], self.inv["id"]))
        self.inv.update(file_sha256=sha, doc_type=info["doc_type"], text_source=info["text_source"])
        kind = {"text_layer": "Text PDF", "ocr_layer": "Scanned photo with OCR text layer", "none": "Scanned image"}[info["text_source"]]
        msg = f"{kind}, {info['page_count']} page{'s' if info['page_count'] > 1 else ''}. " + \
              ("Same file seen before." if hit else "New file, not seen before.")
        return {"message": msg, "input": {"file_name": self.inv["file_name"], "size_kb": kb},
                "output": {"sha256": sha, "page_count": info["page_count"], "doc_type": info["doc_type"],
                           "text_source": info["text_source"], "chars_per_page": info["avg_chars"],
                           "looks_like_invoice": info["looks_like_invoice"], "seen_before": bool(hit)}}

    # ---------------- stage 2
    def s2_extract(self):
        info = self.info
        stored = db.loads(self.inv.get("extraction"))
        # AI reads image-only scans whenever a key is set; text PDFs too only in LEDGERLIGHT_EXTRACTION=llm mode.
        llm = config.llm_available() and not self.force_text and             (info["text_source"] == "none" or config.llm_reads_text_pdfs())
        extraction = None
        if stored and self.run_row.get("use_cache") and stored.get("_sha") == self.inv["file_sha256"] and \
                (stored.get("extractor") == "llm" or not llm):
            extraction = stored
            self.log(2, "info", "Using the saved extraction for this file (re-run).")
        elif info["text_source"] == "none" and not llm:
            self.ctx["extraction_status"] = "unavailable"
            self.ctx["extractor"] = "none"
            self.log(2, "fail", "This is an image-only scan and no AI key is configured: scanned invoice needs AI "
                                "extraction; set ANTHROPIC_API_KEY or GROQ_API_KEY.")
            with db.tx() as con:
                con.execute("UPDATE runs SET extraction_mode='unavailable' WHERE id=?", (self.run_id,))
            return {"status": "skipped", "message": "Skipped: scanned invoice needs AI extraction; set ANTHROPIC_API_KEY or GROQ_API_KEY.",
                    "output": {"extractor": None, "reason": "scanned_no_key"}}
        elif llm:
            from . import extract_llm  # noqa: PLC0415
            scanned = info["doc_type"] == "scanned"
            self.log(2, "info", f"Reading the {'page image' if scanned else 'PDF'} with the vision model "
                                f"({config.llm_provider()} {config.llm_model()}{', saved result if available' if self.run_row.get('use_cache') else ''})")
            try:
                extraction = extract_llm.extract(self.data, self.inv["file_sha256"], scanned=scanned,
                                                 text_hint=info.get("text", ""), use_cache=bool(self.run_row.get("use_cache")))
            except Exception as e:  # API, network or validation failure -> run_failed with Retry (spec 8.4)
                msg = str(e) if isinstance(e, extract_llm.ExtractionError) else f"AI extraction failed ({type(e).__name__})."
                raise StageFailed(2, msg)
            if extraction.get("cached"):
                self.log(2, "info", "Saved AI result used (same file, prompt version and model).")
            if scanned:
                agree = extraction.get("self_consistency") or {}
                bad = [k for k, v in agree.items() if v is False]
                self.log(2, "pass" if not bad else "warn",
                         "Second pass with a different reading order: " + ("amounts and fields agree" if not bad else
                                                                           f"disagreement on {', '.join(bad)}"))
            if extraction.get("contains_instructions"):
                self.log(2, "warn", "The document contains text addressed to an AI. It was treated as data and ignored.")
        else:
            from . import extract_text  # noqa: PLC0415
            self.log(2, "info", "No AI key configured: reading the PDF text layer with the deterministic parser"
                                + (" (OCR layer of a scan)" if info["text_source"] == "ocr_layer" else ""))
            extraction = extract_text.extract(self.data, info["text_source"])
            hidden = pdfio.hidden_text(self.data) if info["text_source"] == "text_layer" else []
            if hidden:
                self.log(2, "warn", f"The PDF contains {len(hidden)} line(s) of invisible text, which a reader cannot "
                                    f"see. They were ignored: \"{hidden[0][:80]}\"")
                extraction["document_notes"] = ((extraction.get("document_notes") or "") +
                                                " The PDF contains invisible text, which was ignored.").strip()
        extraction["_sha"] = self.inv["file_sha256"]
        self.extraction = extraction
        self.ctx["extractor"] = extraction.get("extractor")
        with db.tx() as con:
            con.execute("UPDATE invoices SET extraction=? WHERE id=?", (db.dumps(extraction), self.inv["id"]))
            con.execute("UPDATE runs SET extraction_mode=?, model_name=?, prompt_version=? WHERE id=?",
                        (extraction.get("extractor"), extraction.get("model") or "deterministic text parser",
                         extraction.get("extractor_version"), self.run_id))
        from .normalize import FIELD_LABELS  # noqa: PLC0415
        n_found = 0
        src = {"llm": "image read" if info["doc_type"] == "scanned" else "vision + text layer",
               "text-parser": "OCR text layer" if info["text_source"] == "ocr_layer" else "text layer"}.get(
            extraction.get("extractor"), "text layer")
        for name, f in extraction["fields"].items():
            if f.get("value") is None and name.startswith("bank"):
                continue
            n_found += 1 if f.get("value") is not None else 0
            self.em.emit("field_extracted", {"field": name, "label": FIELD_LABELS.get(name, name), "value": f.get("value"),
                                             "raw_text": f.get("raw_text"), "confidence": f.get("confidence"),
                                             "source": src if f.get("value") is not None else "not found"})
            lvl = "warn" if f.get("value") is not None and (f.get("confidence") or 0) < 0.9 else (
                "info" if f.get("value") is not None else "warn")
            self.log(2, lvl, f"Found {FIELD_LABELS.get(name, name)}: {f.get('raw_text') or f.get('value')} (confidence "
                             f"{(f.get('confidence') or 0):.2f})" if f.get("value") is not None else
                     f"{FIELD_LABELS.get(name, name)}: not found")
        for i, it in enumerate(extraction.get("line_items") or [], 1):
            self.em.emit("line_extracted", {"line_no": i, "description": it.get("description"), "item_code": it.get("item_code"),
                                            "qty": it.get("qty"), "uom": it.get("uom"), "unit_price": it.get("unit_price"),
                                            "amount": it.get("amount"), "tax_rate_pct": it.get("tax_rate_pct"),
                                            "confidence": it.get("confidence")})
            self.log(2, "info", f"Line {i}: {it.get('description')} - {it.get('qty')} {it.get('uom') or ''} x "
                                f"{it.get('unit_price')} = {it.get('amount')}")
        bank = extraction["fields"]
        if bank["bank_account"].get("value") or bank["bank_name"].get("value"):
            self.log(2, "warn" if extraction.get("bank_change_notice") else "info",
                     f"Bank block read: {bank['bank_name'].get('value') or 'bank'}, account "
                     f"{mask_account(bank['bank_account'].get('value'))}"
                     + (". Bank change notice found." if extraction.get("bank_change_notice") else ""))
        else:
            self.log(2, "info", "No bank block on the invoice")
        from . import extract_text as _xt  # noqa: PLC0415
        kind = _xt.classify_document(info.get("text", "")) or _xt.DOC_KIND_ALIASES.get(
            str(extraction.get("document_type") or "").strip().lower().replace(" ", "_").replace("-", "_"))
        if kind:
            self.ctx["extraction_status"] = "wrong_doc_type"
            self.ctx["doc_kind"] = kind
            self.ctx["doc_ref"] = extraction["fields"]["invoice_no"].get("value")
            self.log(2, "warn", f"This document is a {_xt.DOC_KIND_LABEL[kind]}, not a tax invoice. "
                                f"It will not be processed for payment.")
        elif info["text_source"] == "text_layer" and info["looks_like_invoice"] is False and \
                not extraction["fields"]["invoice_no"].get("value") and not extraction["fields"]["total"].get("value"):
            self.ctx["extraction_status"] = "not_invoice"
        nlines = len(extraction.get("line_items") or [])
        return {"message": f"Read {n_found} fields and {nlines} line item{'s' if nlines != 1 else ''}"
                           + (". Two passes agree on amounts" if extraction.get("passes") == 2 and
                              (extraction.get("self_consistency") or {}).get("total") else "") + ".",
                "input": {"text_source": info["text_source"], "extractor": extraction.get("extractor")},
                "output": {"extractor": extraction.get("extractor"), "model": extraction.get("model"),
                           "fields_found": n_found, "line_items": nlines, "cached": extraction.get("cached", False),
                           "passes": extraction.get("passes", 1)}}

    # ---------------- stage 3
    def s3_normalise(self):
        if self.ctx["extraction_status"] != "ok":
            for fn in STAGE_RULES[3]:
                self.rule(fn(self.ctx))
            return {"status": "done", "message": self.ctx["rules"]["R01"]["message"].split(".")[0] + ".",
                    "output": {"canonical": None}}
        corrections = db.loads(self.inv.get("corrections"), {}) or {}
        canon = normalise(self.extraction, text_layer=self.info.get("text", ""),
                          scanned_no_text=self.info["text_source"] == "none", cfg=self.cfg, as_of=self.ctx["as_of"],
                          corrections=corrections)
        self.ctx["canon"] = canon
        for name, f in canon["fields"].items():
            if f["value"] is None and name.startswith("bank"):
                continue
            disp = f["value"]
            if isinstance(f.get("parsed"), int) and name in ("subtotal", "tax_total", "total"):
                disp = inr(f["parsed"])
            elif isinstance(f.get("parsed"), date):
                disp = fmt_date(f["parsed"])
            self.em.emit("field_confidence", {"field": name, "label": f["label"], "value": f["value"], "display": disp,
                                              "model_confidence": f["model_confidence"], "evidence": f["evidence"],
                                              "format_valid": f["format_valid"],
                                              "effective_confidence": f["effective_confidence"],
                                              "boosted": f["boosted"], "boosted_from": f.get("boosted_from"),
                                              "source": f["source"], "why": f.get("why"),
                                              "ambiguous": f.get("ambiguous", False)})
            if f["boosted"]:
                self.log(3, "pass", f"{f['label']}: confidence {f['boosted_from']:.2f} raised to "
                                    f"{f['effective_confidence']:.2f} because the numbers add up")
            elif f.get("ambiguous"):
                self.log(3, "warn", f"{f['label']}: {f.get('note')}")
        for n in canon["notes"]:
            self.log(3, "info", n)
        self.log(3, "info", f"Money converted to integer paise. Invoice number canonical form "
                            f"{canon['invoice_no_canonical']} (serial token {canon['serial_token']})")
        self._save_canon(canon)
        for fn in STAGE_RULES[3]:
            self.rule(fn(self.ctx))
        f = canon["fields"]
        if canon["tax_inclusive"]:
            msg = f"Prices are tax-inclusive. Backed out GST to {inr0(canon['subtotal_paise'])}."
        elif any(x["boosted"] for x in f.values()):
            b = next(x for x in f.values() if x["boosted"] and x["name"] == "total") if f["total"]["boosted"] else None
            msg = (f"Date read as {fmt_date(canon['invoice_date'])}. " if canon["date_ambiguous"] else "") + \
                  (f"Total confidence raised {b['boosted_from']:.2f} to {b['effective_confidence']:.2f}." if b else
                   "Confidence raised because the numbers add up.")
        else:
            low = min([x["effective_confidence"] for x in f.values() if x["value"] is not None] or [0])
            r1 = self.ctx["rules"]["R01"]
            msg = r1["message"] if r1["severity"] != "pass" else f"All required fields present. Lowest confidence {low:.2f}."
        return {"message": msg, "output": {"invoice_no": canon["invoice_no"], "canonical": canon["invoice_no_canonical"],
                                           "serial_token": canon["serial_token"],
                                           "invoice_date": canon["invoice_date"].isoformat() if canon["invoice_date"] else None,
                                           "subtotal_paise": canon["subtotal_paise"], "tax_paise": canon["tax_paise"],
                                           "total_paise": canon["total_paise"], "tax_inclusive": canon["tax_inclusive"],
                                           "reconciled": canon["reconciled"]}}

    def _save_canon(self, canon: dict):
        f = canon["fields"]
        fields_json = {k: {kk: (vv.isoformat() if isinstance(vv, date) else vv) for kk, vv in v.items()} for k, v in f.items()}
        with db.tx() as con:
            con.execute(
                "UPDATE invoices SET vendor_name_raw=?, vendor_gstin_raw=?, invoice_no_raw=?, invoice_no_canonical=?, "
                "serial_token=?, invoice_date=?, date_ambiguous=?, po_ref_raw=?, currency=?, subtotal_paise=?, tax_paise=?, "
                "total_paise=?, tax_inclusive=?, bank_name_raw=?, bank_account_raw=?, bank_ifsc_raw=?, bank_change_notice=?, "
                "fields=? WHERE id=?",
                (f["vendor_name"]["value"], canon["vendor_gstin"], canon["invoice_no"], canon["invoice_no_canonical"],
                 canon["serial_token"], canon["invoice_date"].isoformat() if canon["invoice_date"] else None,
                 1 if canon["date_ambiguous"] else 0, canon["po_reference"], canon["currency"], canon["subtotal_paise"],
                 canon["tax_paise"], canon["total_paise"], 1 if canon["tax_inclusive"] else 0, canon["bank"]["name"],
                 canon["bank"]["account"], canon["bank"]["ifsc"], 1 if canon["bank_change_notice"] else 0,
                 db.dumps(fields_json), self.inv["id"]))
            con.execute("DELETE FROM line_items WHERE invoice_id=?", (self.inv["id"],))
            for l in canon["lines"]:
                con.execute("INSERT INTO line_items (invoice_id, line_no, description_raw, description_norm, item_code, qty, "
                            "uom, unit_price_paise, amount_paise, pretax_amount_paise, tax_rate_pct, confidence) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (self.inv["id"], l["line_no"], l["description"], l["desc_norm"], l["item_code"], l["qty"],
                             l["uom"], l["unit_price_paise"], l["amount_paise"], l["pretax_amount_paise"],
                             l["tax_rate_pct"], l["confidence"]))

    # ---------------- stage 4
    def s4_vendor(self):
        if self.ctx["extraction_status"] == "ok":
            c = self.ctx["canon"]
            with db.conn() as con:
                vendors = matching.load_vendors(con)
            self.log(4, "info", f"Matching vendor against the master list ({len(vendors)} vendors)")
            vm = matching.match_vendor(vendors, c["fields"]["vendor_name"]["value"], c["vendor_gstin"],
                                       self.cfg["advanced"]["fuzzy_vendor"], scanned=self.info["doc_type"] == "scanned")
            self.ctx["vendor_match"] = vm
            v = vm["vendor"]
            if v:
                self.log(4, "pass" if vm["method"] in ("gstin", "name") else "warn",
                         f"Matched {v['name']} by {'GSTIN ' + v['gstin'] if vm['method'] == 'gstin' else vm['method'] + ' match'}")
                with db.tx() as con:
                    con.execute("UPDATE invoices SET vendor_id=? WHERE id=?", (v["id"], self.inv["id"]))
            else:
                self.log(4, "fail", "No vendor in the master matches this invoice")
            notice_date = None
            if c["bank_change_notice"]:
                from datetime import timedelta  # noqa: PLC0415
                from .textutil import parse_date  # noqa: PLC0415
                notice_date = parse_date(c.get("bank_change_text") or "", as_of=self.ctx["as_of"])["value"] or (
                    c["invoice_date"] - timedelta(days=60) if c.get("invoice_date") else None)
            self.ctx["bank"] = matching.bank_compare(c["bank"], c["bank_change_notice"], v, c.get("bank_entries"),
                                                     notice_date=notice_date)
        else:
            self.ctx["bank"] = {"status": "no_vendor"}
        for fn in STAGE_RULES[4]:
            self.rule(fn(self.ctx))
        vm = self.ctx["vendor_match"]
        v = vm.get("vendor")
        b = self.ctx["bank"]
        if not v:
            msg = "Vendor not identified." if self.ctx["extraction_status"] == "ok" else "Skipped: nothing was extracted."
        elif b["status"] == "not_applicable":
            msg = f"Vendor found by {vm['method'].upper() if vm['method'] == 'gstin' else vm['method']}. No bank details on invoice."
        elif b["status"] == "match":
            msg = f"Vendor found: {v['name']}. Bank matches."
        else:
            msg = "Vendor found. Bank account differs from the master."
        return {"message": msg, "output": {"vendor_id": v["id"] if v else None, "vendor_name": v["name"] if v else None,
                                           "method": vm["method"], "score": vm["score"], "status": v["status"] if v else None,
                                           "bank": b.get("status")}}

    # ---------------- stage 5
    def s5_duplicate(self):
        v = self.ctx["vendor_match"].get("vendor")
        if self.ctx["extraction_status"] == "ok":
            c = self.ctx["canon"]
            with db.conn() as con:
                po_guess, _ = matching.find_po_by_reference(con, [c.get("po_reference")] + list(c.get("po_reference_candidates") or []))
                cur = {"invoice_no": c["invoice_no"], "invoice_date": c["invoice_date"], "total_paise": c["total_paise"],
                       "po_id": po_guess["id"] if po_guess else None, "lines": c["lines"]}
                dup = matching.duplicate_check(con, vendor_id=v["id"] if v else None, invoice_id=self.inv["id"],
                                               sha=self.inv["file_sha256"], cur=cur, cfg=self.cfg)
            self.ctx["dup"] = dup
            self.log(5, "info", f"Comparing with {dup.get('compared', 0)} earlier invoices from this vendor")
            cl = dup.get("closest")
            if dup.get("signals") and cl and dup["score"] >= 0.6 and dup.get("serials") and dup["serials"][0] == dup["serials"][1]:
                self.log(5, "warn", f"Canonical number {c['invoice_prefix']}-{c['serial_token']} has the same serial token "
                                    f"as {cl['invoice_no']} ({dup['serials'][1]})")
            if cl:
                lvl = "fail" if dup["score"] >= self.cfg["rules"]["R06"]["reject"] else (
                    "warn" if dup["score"] >= self.cfg["rules"]["R06"]["review"] else "pass")
                self.log(5, lvl, f"Closest earlier invoice {cl['invoice_no']}, similarity {dup['score']:.2f}"
                                 + (f" (exact {dup['exact']} match)" if dup.get("exact") else ""))
        for fn in STAGE_RULES[5]:
            self.rule(fn(self.ctx))
        d = self.ctx["dup"]
        cl = d.get("closest")
        msg = (f"Closest match {cl['invoice_no']}, similarity {d['score']:.2f}." if cl and d["score"] >= 0.6 else
               f"No earlier invoice is similar (highest {d.get('score', 0):.2f}).")
        return {"message": msg, "output": {"score": d.get("score"), "exact": d.get("exact"),
                                           "closest_invoice": cl.get("id") if cl else None,
                                           "closest_invoice_no": cl.get("invoice_no") if cl else None,
                                           "signals": d.get("signals")}}

    # ---------------- stage 6
    def s6_po(self):
        if self.ctx["extraction_status"] == "ok":
            c = self.ctx["canon"]
            v = self.ctx["vendor_match"].get("vendor")
            with db.conn() as con:
                res = matching.resolve_po(con, c, v, self.cfg, self.inv["id"])
                # Same vendor, same PO, within a week: value limits (R15 manager sign-off, R07 inferred-PO ceiling)
                # apply to these together, so splitting one bill into two smaller invoices does not dodge them.
                self.ctx["siblings"] = matching.recent_siblings(
                    con, vendor_id=v["id"] if v else None, po_id=(res.get("po") or {}).get("id"),
                    invoice_id=self.inv["id"], invoice_date=c.get("invoice_date"))
            self.ctx["po_res"] = res
            if res["method"] == "explicit":
                self.log(6, "pass", f"Found {res['po']['id']} on the invoice" +
                         (f' (written as "{res["matched_text"]}", normalised)' if res.get("normalised") else " (explicit match)"))
            elif res["method"] == "implied":
                self.log(6, "warn", f"No PO reference found. Scoring the {len(res['candidates'])} open PO"
                                    f"{'s' if len(res['candidates']) != 1 else ''} for {v.get('short') or v['name']}")
                for cand in reversed(res["candidates"]):
                    self.log(6, "info", f"{cand['po_id']}: descriptions {cand['parts']['desc']:.2f}, prices "
                                        f"{cand['parts']['price']:.2f}, quantities {cand['parts']['qty']:.2f}, score "
                                        f"{cand['score']:.2f}")
            elif res["method"] == "other_vendor":
                self.log(6, "warn", f"{res['po']['id']} belongs to vendor {res['po']['vendor_id']}")
            else:
                self.log(6, "warn", "No PO reference and no open PO to match")
            po = res.get("po")
            if po:
                al = matching.align_lines(c["lines"], po["lines"], self.cfg["advanced"]["line_fuzzy"])
                self.ctx["alignment"] = al
                pl_by_id = {l["id"]: l for l in po["lines"]}
                for a in al:
                    l = next(x for x in c["lines"] if x["line_no"] == a["line_no"])
                    if a["method"] == "none":
                        self.log(6, "warn", f'"{l["description"]}" is not on {po["id"]}')
                        continue
                    for pid in a["po_line_ids"]:
                        pl = pl_by_id[pid]
                        self.log(6, "info", f'Aligned "{l["description"][:48]}" to {pl["item_code"]} ({a["method"]}): '
                                            f"ordered {fmt_qty(pl['ordered_qty'])}, billed before {fmt_qty(pl['billed_qty'])}, "
                                            f"this invoice {fmt_qty(next(x['qty'] for x in a['alloc'] if x['po_line_id'] == pid))}")
                this = sum(x["amount_paise"] for a in al for x in a["alloc"])
                after = 100.0 * (po["billed_subtotal_paise"] + this) / po["subtotal_paise"] if po["subtotal_paise"] else 0
                self.log(6, "warn" if after > 100.5 else "info",
                         f"Cumulative position: {po['pct_billed']:.0f}% billed before, {after:.0f}% after this invoice")
                with db.tx() as con:
                    con.execute("UPDATE invoices SET po_id=?, po_match_method=?, po_match_score=?, po_runner_up=? WHERE id=?",
                                (po["id"], res["method"], res.get("score"),
                                 db.dumps({"po_id": res.get("runner_up_po"), "score": res.get("runner_up"),
                                           "candidates": res.get("candidates")}), self.inv["id"]))
                    for a in al:
                        con.execute("UPDATE line_items SET matched_po_line_ids=?, match_method=?, match_score=?, alloc=? "
                                    "WHERE invoice_id=? AND line_no=?",
                                    (db.dumps(a["po_line_ids"]), a["method"], a["score"], db.dumps(a["alloc"]),
                                     self.inv["id"], a["line_no"]))
                # R03 also checks the invoice date against the PO date (needs the PO, so it is re-evaluated here)
                if c.get("invoice_date") and to_date(po.get("issue_date")) and c["invoice_date"] < to_date(po["issue_date"]):
                    self.rule(r03(self.ctx, to_date(po["issue_date"])))
            else:
                with db.tx() as con:
                    con.execute("UPDATE invoices SET po_id=NULL, po_match_method=?, po_match_score=NULL, po_runner_up=? "
                                "WHERE id=?", (res["method"], db.dumps({"candidates": res.get("candidates")}), self.inv["id"]))
        for fn in STAGE_RULES[6]:
            self.rule(fn(self.ctx))
        res = self.ctx["po_res"]
        po = res.get("po")
        if res["method"] == "implied":
            msg = (f"No PO on invoice. Inferred {po['id']} at {res['score'] * 100:.0f}%"
                   + (f" (runner-up {res['runner_up'] * 100:.0f}%)." if res.get("runner_up_po") else "."))
        elif po:
            msg = f"{po['id']} found. {po['pct_billed']:.0f}% billed before this invoice. {len(self.ctx['alignment'])} " \
                  f"line{'s' if len(self.ctx['alignment']) != 1 else ''} aligned."
        else:
            msg = "No purchase order found." if self.ctx["extraction_status"] == "ok" else "Skipped: nothing was extracted."
        return {"message": msg, "output": {"po_id": po["id"] if po else None, "method": res["method"],
                                           "score": res.get("score"), "runner_up": res.get("runner_up"),
                                           "candidates": res.get("candidates"),
                                           "pct_billed_before": po["pct_billed"] if po else None,
                                           "alignment": [{k: a[k] for k in ("line_no", "po_line_ids", "method", "score")}
                                                         for a in self.ctx["alignment"]]}}

    # ---------------- stage 7
    def s7_validate(self):
        for fn in STAGE_RULES[7]:
            self.rule(fn(self.ctx))
        rs = [self.ctx["rules"][r] for r in ("R10", "R11", "R12", "R13", "R14", "R15", "R16")]
        active = [r for r in rs if not r["skipped"]]
        n_pass = sum(1 for r in active if r["severity"] == "pass")
        worst = max(active, key=lambda r: SEV_RANK[r["severity"]], default=None)
        if not active:
            msg = "Skipped: nothing to validate."
        elif worst["severity"] == "pass":
            msg = f"All {len(active)} number checks passed."
        else:
            msg = f"{n_pass} of {len(active)} checks passed. {worst['rule_name']}: {worst['severity']}."
        return {"message": msg, "output": {"rules": {r["rule_id"]: r["severity"] for r in rs}}}

    # ---------------- stage 8
    def s8_decide(self):
        self.log(8, "info", "Collecting 16 rule results. The worst severity wins: REJECT, HOLD, REVIEW, NOTE, PASS")
        total = (self.ctx.get("canon") or {}).get("total_paise")
        d = decide(self.ctx["rules"], self.cfg, total)
        self.ctx["decision"] = d
        lvl = {"auto_approve": "pass", "approve_with_note": "pass", "route_for_review": "warn",
               "hold_request_info": "fail", "reject": "fail"}[d["outcome"]]
        self.log(8, lvl, f"Worst severity {d['worst'].upper()}. Decision: {OUTCOME_LONG[d['outcome']]}"
                         + (f". Exposure {inr0(d['exposure_paise'])}" if d["exposure_paise"] else "")
                         + (f". Driving rules: {', '.join(d['driving_rule_ids'])}" if d["driving_rule_ids"] else ""))
        return {"message": f"Worst severity {d['worst'].upper()}: {OUTCOME_LONG[d['outcome']]}.",
                "output": {"outcome": d["outcome"], "driving_rule_ids": d["driving_rule_ids"],
                           "exposure_paise": d["exposure_paise"], "assigned_to": d["assigned_to"]}}

    # ---------------- stage 9
    def s9_explain(self):
        self.log(9, "info", "Writing the explanation from rule facts (template, numbers checked)")
        d = self.ctx["decision"]
        expl = build_explanation(self.ctx, self.ctx["rules"], d)
        expl, mode = maybe_polish(expl, enabled=True)
        drafts = build_drafts(self.ctx, self.ctx["rules"], d, expl)
        for dr in drafts:
            if dr["kind"] != "checklist":
                self.log(9, "info", f"Drafted: {dr['title']}. Nothing is sent automatically")
        now = self.clock.now()
        sla = None
        if d["outcome"] == "hold_request_info":
            sla = business_days_after(now, int(self.cfg["global"].get("sla", 3)))
        elif d["outcome"] == "route_for_review":
            sla = business_days_after(now, 1)
        with db.tx() as con:
            prev = con.execute("SELECT current_decision_id FROM invoices WHERE id=?", (self.inv["id"],)).fetchone()
            ver = con.execute("SELECT COALESCE(MAX(version), 0) AS v FROM decisions WHERE invoice_id=?",
                              (self.inv["id"],)).fetchone()["v"] + 1
            cur = con.execute(
                "INSERT INTO decisions (run_id, invoice_id, version, outcome, headline, explanation, driving_rule_ids, "
                "exposure_paise, category, assigned_to, sla_due_at, made_by, actor_name, supersedes_decision_id, drafts, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.run_id, self.inv["id"], ver, d["outcome"], expl["headline"], db.dumps(expl),
                 db.dumps(d["driving_rule_ids"]), d["exposure_paise"], d["category"], d["assigned_to"],
                 sla.isoformat(timespec="seconds").replace("+00:00", "Z") if sla else None, "system", "Ledgerlight",
                 prev["current_decision_id"] if prev else None, db.dumps(drafts), self.clock.iso()))
            dec_id = cur.lastrowid
            con.execute("UPDATE invoices SET current_decision_id=? WHERE id=?", (dec_id, self.inv["id"]))
            db.audit(con, actor_type="system", actor_id="Ledgerlight rules", event_type="decision_made",
                     object_type="invoice", object_id=self.inv["id"], run_id=self.run_id, invoice_id=self.inv["id"],
                     summary=f"{OUTCOME_LONG[d['outcome']]}: {expl['headline']}", outcome=d["outcome"],
                     payload={"decision": d["outcome"], "decision_id": dec_id, "version": ver,
                              "driving_rule_ids": d["driving_rule_ids"], "exposure_paise": d["exposure_paise"],
                              "assigned_to": d["assigned_to"], "config_version": self.cfg_version,
                              "explanation_mode": mode}, ts=self.clock.iso())
        self.log(9, "pass", "Decision saved to the audit log")
        self.em.emit("decision", {"decision_id": dec_id, "version": ver, "outcome": d["outcome"],
                                  "label": OUTCOME_LONG[d["outcome"]], "headline": expl["headline"],
                                  "exposure_paise": d["exposure_paise"], "assigned_to": d["assigned_to"],
                                  "driving_rule_ids": d["driving_rule_ids"], "category": d["category"],
                                  "explanation": expl, "explanation_mode": mode,
                                  "sla_due_at": sla.isoformat(timespec="seconds").replace("+00:00", "Z") if sla else None})
        return {"message": "Explanation written." + (" Vendor message drafted." if drafts else ""),
                "output": {"headline": expl["headline"], "explanation_mode": mode,
                           "drafts": [x["title"] for x in drafts]}}


def run_sync(run_id: str, clock: Clock | None = None, publish: bool = True, force_text_parser: bool = False) -> dict:
    return Runner(run_id, clock=clock, publish=publish, force_text_parser=force_text_parser).run()
