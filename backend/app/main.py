"""Ledgerlight HTTP API (FastAPI). See backend/API.md for every endpoint and the SSE event schema.

Run:  uvicorn app.main:app --port 8010   (from backend/, with the venv active)"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse

from . import admin, config, db, pdfio, pipeline, repo, seed, services, settings_store
from .catalogue import (CATEGORY_BY_RULE, HARD_STOP_RULES, OUTCOME_LABEL, OUTCOME_LONG, PARAM_LABELS, RULES, STAGES,
                        allowed_text, default_config, sentence)
from .events import BUS, load_events

logging.basicConfig(level=os.environ.get("LEDGERLIGHT_LOG", "INFO"))
log = logging.getLogger("ledgerlight")
TERMINAL = {"run_completed", "run_failed", "run_cancelled"}
_tasks: set = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect().close()
    if os.environ.get("LEDGERLIGHT_AUTOSEED", "1") != "0":
        await asyncio.to_thread(seed.ensure_seeded)
    # runs interrupted by a server restart cannot resume: mark them failed so the UI offers Retry
    with db.tx() as con:
        for r in con.execute("SELECT id FROM runs WHERE status IN ('queued','running')").fetchall():
            con.execute("UPDATE runs SET status='failed', error='Server restarted during the run' WHERE id=?", (r["id"],))
    log.info("Ledgerlight ready. Extraction mode: %s", "Claude vision (%s)" % config.LLM_MODEL if config.llm_available()
             else "deterministic text parser (no ANTHROPIC_API_KEY)")
    yield


app = FastAPI(title="Ledgerlight API", version="1.0.0", lifespan=lifespan,
              description="AI invoice processing. The AI reads, rules decide, everyone can see why.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("LEDGERLIGHT_CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])


def who(role: str | None, user: str | None) -> tuple[str, str]:
    return admin.actor(role, user)


def start_background(run_id: str) -> None:
    async def _go():
        try:
            await asyncio.to_thread(pipeline.run_sync, run_id)
        except Exception:  # the runner already records failures; this guards against crashes in the guard itself
            log.exception("run %s crashed", run_id)
    t = asyncio.create_task(_go())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def err(status: int, message, **extra):
    detail = {"error": message} if isinstance(message, str) else {"error": "Validation failed", "fields": message}
    return JSONResponse(status_code=status, content={**detail, **extra})


# ------------------------------------------------------------------ meta

@app.get("/api/health")
def health():
    with db.conn() as con:
        n = con.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
    return {"ok": True, "version": app.version, "extraction_mode": "llm" if config.llm_available() else "text-only",
            "llm_model": config.LLM_MODEL if config.llm_available() else None,
            "scanned_pdfs_supported": config.llm_available(), "as_of": config.AS_OF or None, "runs": n,
            "default_pace": config.DEFAULT_PACE, "pace_presets": config.PACE_PRESETS}


@app.get("/api/meta")
def meta():
    cfg = settings_store.current()[1]
    return {"stages": STAGES, "rules": [{**r, "hard": bool(r.get("hard")), "sentence": sentence(r["id"], cfg)} for r in RULES],
            "outcomes": [{"id": k, "label": OUTCOME_LABEL[k], "long": OUTCOME_LONG[k]} for k in OUTCOME_LABEL],
            "severities": ["pass", "note", "review", "hold", "reject"], "reason_codes": admin.REASON_CODES,
            "roles": [{"id": k, "name": v} for k, v in admin.ROLES.items()],
            "categories": sorted(set(CATEGORY_BY_RULE.values()) | {"Needs AI extraction"}),
            "pace_presets": config.PACE_PRESETS}


# ------------------------------------------------------------------ samples and demo

@app.get("/api/samples")
def list_samples(reveal: bool = True):
    with db.conn() as con:
        ran = {r["sample_id"]: r["n"] for r in con.execute(
            "SELECT sample_id, COUNT(*) AS n FROM invoices WHERE sample_id IS NOT NULL GROUP BY sample_id")}
    out = []
    for s in services.samples():
        d = {k: s[k] for k in ("id", "file", "vendor", "vendor_id", "title", "description", "tags", "edge_case",
                               "invoice_no", "gross_paise", "requires_llm", "available", "size_bytes")}
        d["expected_outcome"] = s["expected_outcome"] if reveal else None
        d["expected_label"] = OUTCOME_LABEL.get(s["expected_outcome"]) if reveal else None
        d["driving_rules"] = s["driving_rules"] if reveal else None
        d["run_before"] = bool(ran.get(s["id"]))
        d["runnable_now"] = s["available"] and (not s["requires_llm"] or config.llm_available())
        d["note"] = None if d["runnable_now"] or not s["requires_llm"] else \
            "Image-only scan: without ANTHROPIC_API_KEY it will be put on hold (scanned invoice needs AI extraction)."
        d["pdf_url"] = f"/api/samples/{s['id']}/pdf"
        d["thumbnail_url"] = f"/api/samples/{s['id']}/thumbnail.png"
        out.append(d)
    return {"samples": out}


def _sample_path(sample_id: str) -> Path:
    s = services.sample_by_id(sample_id)
    if not s or not s["available"]:
        raise HTTPException(404, "Sample not found")
    return config.SAMPLES_DIR / s["file"]


@app.get("/api/samples/{sample_id}/pdf")
def sample_pdf(sample_id: str):
    p = _sample_path(sample_id)
    return FileResponse(p, media_type="application/pdf", filename=p.name, content_disposition_type="inline")


@app.get("/api/samples/{sample_id}/thumbnail.png")
def sample_thumb(sample_id: str, dpi: int = 40):
    p = _sample_path(sample_id)
    return Response(pdfio.render_png(p.read_bytes(), 0, dpi=max(20, min(dpi, 150))), media_type="image/png")


@app.post("/api/demo/reset")
async def demo_reset(x_ledgerlight_role: str | None = Header(None), x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    res = await asyncio.to_thread(seed.reset_and_seed, user)
    BUS.publish_global({"event": "demo_reset", "data": res})
    return res


@app.post("/api/demo/seed")
async def demo_seed():
    if seed.is_seeded():
        return {"seeded": False, "message": "Data already present. Use POST /api/demo/reset to start over."}
    res = await asyncio.to_thread(seed.reset_and_seed)
    return {"seeded": True, **res}


# ------------------------------------------------------------------ runs

@app.post("/api/runs", status_code=201)
async def create_runs(request: Request, x_ledgerlight_role: str | None = Header(None),
                      x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    ctype = request.headers.get("content-type", "")
    created, rejected = [], []
    if ctype.startswith("multipart/"):
        form = await request.form()
        pace = form.get("pace") or None
        use_cache = str(form.get("use_cache", "true")).lower() != "false"
        files = form.getlist("files") + form.getlist("file")
        if not files:
            return err(400, "Send one or more PDFs in the 'files' field, or JSON {\"sample_id\": \"SI-01\"}.")
        if len(files) > 10:
            return err(400, "Up to 10 files per upload.")
        for f in files:
            data = await f.read()
            try:
                iid, rid = services.new_run(file_name=f.filename or "invoice.pdf", data=data, source="upload",
                                            sample_id=None, pace=pace, use_cache=use_cache, triggered_by=user)
                created.append({"run_id": rid, "invoice_id": iid, "file_name": f.filename})
            except pdfio.PdfRejected as e:
                rejected.append({"file_name": f.filename, "error": str(e)})
    else:
        try:
            body = await request.json()
        except Exception:
            return err(400, "Send JSON {\"sample_id\": \"SI-01\"} or multipart files.")
        sid = body.get("sample_id")
        s = services.sample_by_id(sid or "")
        if not s or not s["available"]:
            return err(404, f"Unknown sample '{sid}'.")
        data = (config.SAMPLES_DIR / s["file"]).read_bytes()
        try:
            iid, rid = services.new_run(file_name=s["file"], data=data, source="sample", sample_id=s["id"],
                                        pace=body.get("pace"), use_cache=body.get("use_cache", True), triggered_by=user)
        except pdfio.PdfRejected as e:
            return err(400, str(e))
        created.append({"run_id": rid, "invoice_id": iid, "file_name": s["file"]})
    for c in created:
        c["events_url"] = f"/api/runs/{c['run_id']}/events"
        c["detail_url"] = f"/api/runs/{c['run_id']}"
        start_background(c["run_id"])
    if not created:
        return err(400, "No valid files.", rejected=rejected)
    return {"runs": created, "rejected": rejected}


@app.get("/api/runs")
def runs_list(status: str | None = None, q: str | None = None, range: str | None = "30d", vendor_id: str | None = None,
              overridden: bool | None = None, all_runs: bool = False, sort: str = "time", order: str = "desc",
              page: int = 1, page_size: int = Query(25, le=200)):
    days = None if (range or "").lower() in ("all", "") else int(str(range).rstrip("d"))
    statuses = [s for s in (status or "").split(",") if s]
    return repo.list_runs(statuses=statuses or None, q=q, range_days=days, vendor_id=vendor_id, overridden=overridden,
                          all_runs=all_runs, sort=sort, order=order, page=page, page_size=page_size)


@app.get("/api/runs/{run_id}")
def run_get(run_id: str):
    d = repo.run_detail(run_id)
    if not d:
        raise HTTPException(404, "Run not found")
    return d


@app.get("/api/runs/{run_id}/decision.json")
def run_decision_json(run_id: str):
    d = repo.run_detail(run_id)
    if not d:
        raise HTTPException(404, "Run not found")
    out = {"run_id": run_id, "invoice": d["invoice"], "decision": d["decision"], "system_decision": d["system_decision"],
           "rules": [{k: r[k] for k in ("rule_id", "name", "severity", "skipped", "message", "facts", "exposure_paise")}
                     for r in d["rules"]],
           "fields": d["fields"], "lines": d["lines"], "po": d["po_panel"], "config_version": d["run"].get("config_version")}
    with db.tx() as con:
        db.audit(con, actor_type="human", actor_id="export", event_type="export", object_type="invoice",
                 object_id=d["invoice"]["id"], invoice_id=d["invoice"]["id"], summary=f"Downloaded decision JSON for run {run_id}")
    return Response(json.dumps(out, indent=2, ensure_ascii=False, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}-decision.json"'})


@app.post("/api/runs/{run_id}/cancel")
def run_cancel(run_id: str):
    with db.conn() as con:
        r = con.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Run not found")
    if r["status"] not in ("queued", "running"):
        return err(409, f"Run is already {r['status']}.")
    pipeline.CANCEL.setdefault(run_id, threading.Event()).set()
    return {"run_id": run_id, "cancel_requested": True}


@app.post("/api/runs/{run_id}/retry", status_code=201)
def run_retry(run_id: str, x_ledgerlight_role: str | None = Header(None), x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    with db.conn() as con:
        r = con.execute("SELECT invoice_id, pace, use_cache FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Run not found")
    try:
        rid = services.rerun(r["invoice_id"], pace=r["pace"], use_cache=bool(r["use_cache"]), triggered_by=user,
                             reason="Retry", parent_run_id=run_id)
    except ValueError as e:
        return err(400, str(e))
    start_background(rid)
    return {"run_id": rid, "invoice_id": r["invoice_id"], "events_url": f"/api/runs/{rid}/events"}


def _sse(ev: dict) -> str:
    return f"id: {ev['id']}\nevent: {ev['event']}\ndata: {json.dumps({**ev['data'], '_ts': ev['ts']}, ensure_ascii=False, default=str)}\n\n"


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, replay: bool = False, speed: float = 1.0,
                     last_event_id: int | None = Query(None), last_event_id_header: str | None = Header(None, alias="Last-Event-ID")):
    with db.conn() as con:
        if not con.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
            raise HTTPException(404, "Run not found")
    start_after = last_event_id if last_event_id is not None else int(last_event_id_header or 0)

    async def gen():
        q = BUS.subscribe(run_id)
        try:
            yield "retry: 2000\n\n"
            sent = start_after
            past = load_events(run_id, sent)
            prev_ts = None
            for ev in past:
                if replay and prev_ts is not None:
                    gap = (repo.parse_ts(ev["ts"]) - repo.parse_ts(prev_ts)).total_seconds() / max(0.1, speed)
                    await asyncio.sleep(min(max(gap, 0), 2.5))
                prev_ts = ev["ts"]
                yield _sse(ev)
                sent = ev["id"]
                if ev["event"] in TERMINAL:
                    return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    missed = load_events(run_id, sent)
                    for m in missed:
                        yield _sse(m)
                        sent = m["id"]
                        if m["event"] in TERMINAL:
                            return
                    continue
                if ev["id"] <= sent:
                    continue
                if ev["id"] > sent + 1:  # gap: fill from the database
                    for m in load_events(run_id, sent):
                        if m["id"] >= ev["id"]:
                            break
                        yield _sse(m)
                        sent = m["id"]
                yield _sse(ev)
                sent = ev["id"]
                if ev["event"] in TERMINAL:
                    return
        finally:
            BUS.unsubscribe(run_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@app.get("/api/stream/runs")
async def stream_runs(request: Request):
    async def gen():
        q = BUS.subscribe(None)
        n = 0
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                n += 1
                yield f"id: {n}\nevent: {ev['event']}\ndata: {json.dumps(ev['data'], default=str)}\n\n"
        finally:
            BUS.unsubscribe(None, q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache",
                                                                             "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ invoices

@app.get("/api/invoices/{invoice_id}")
def invoice_get(invoice_id: str):
    d = repo.invoice_detail(invoice_id)
    if not d:
        raise HTTPException(404, "Invoice not found")
    return d


def _invoice_file(invoice_id: str) -> Path:
    with db.conn() as con:
        r = con.execute("SELECT file_path FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Invoice not found")
    if not r["file_path"] or not Path(r["file_path"]).exists():
        raise HTTPException(404, "PDF not stored for demo history.")
    return Path(r["file_path"])


@app.get("/api/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: str):
    p = _invoice_file(invoice_id)
    return FileResponse(p, media_type="application/pdf", filename=p.name, content_disposition_type="inline")


@app.get("/api/invoices/{invoice_id}/pages/{page}.png")
def invoice_page(invoice_id: str, page: int, dpi: int = 110):
    p = _invoice_file(invoice_id)
    return Response(pdfio.render_png(p.read_bytes(), max(0, page - 1), dpi=max(30, min(dpi, 200))), media_type="image/png")


@app.get("/api/invoices/{invoice_id}/audit")
def invoice_audit(invoice_id: str):
    return admin.audit_query(invoice_id=invoice_id, page_size=1000)


@app.post("/api/invoices/{invoice_id}/rerun", status_code=201)
async def invoice_rerun(invoice_id: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                        x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    body = await _json(request)
    try:
        rid = services.rerun(invoice_id, pace=body.get("pace"), use_cache=body.get("use_cache", True), triggered_by=user,
                             reason=body.get("reason"))
    except ValueError as e:
        return err(400, str(e))
    start_background(rid)
    return {"run_id": rid, "invoice_id": invoice_id, "events_url": f"/api/runs/{rid}/events"}


async def _json(request: Request) -> dict:
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


@app.post("/api/invoices/{invoice_id}/override")
async def invoice_override(invoice_id: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                           x_ledgerlight_user: str | None = Header(None)):
    role, user = who(x_ledgerlight_role, x_ledgerlight_user)
    b = await _json(request)
    try:
        res = admin.override(invoice_id, action=b.get("action", ""), reason_code=b.get("reason_code", ""),
                             reason_text=b.get("reason_text", ""), role=role, user=user, checklist=b.get("checklist"))
    except admin.Forbidden as e:
        return err(403, str(e))
    except admin.Invalid as e:
        return err(422, e.args[0])
    BUS.publish_global({"event": "decision_overridden", "data": {"invoice_id": invoice_id, **res}})
    return {**res, "invoice": repo.invoice_detail(invoice_id)}


@app.post("/api/invoices/{invoice_id}/accept")
async def invoice_accept(invoice_id: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                         x_ledgerlight_user: str | None = Header(None)):
    role, user = who(x_ledgerlight_role, x_ledgerlight_user)
    b = await _json(request)
    try:
        return admin.accept(invoice_id, user=user, role=role, note=b.get("note"))
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.post("/api/invoices/{invoice_id}/info-requested")
def invoice_info_requested(invoice_id: str, x_ledgerlight_role: str | None = Header(None),
                           x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    try:
        return admin.mark_info_requested(invoice_id, user=user)
    except admin.Invalid as e:
        return err(404, e.args[0])


@app.patch("/api/invoices/{invoice_id}/fields/{name}")
async def invoice_correct_field(invoice_id: str, name: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                                x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    b = await _json(request)
    try:
        admin.correct_field(invoice_id, name, value=b.get("value"), reason=b.get("reason"), user=user)
        rid = services.rerun(invoice_id, pace=b.get("pace"), use_cache=True, triggered_by=user,
                             reason=f"Field {name} corrected")
    except admin.Invalid as e:
        return err(422, e.args[0])
    except ValueError as e:
        return err(400, str(e))
    start_background(rid)
    return {"run_id": rid, "invoice_id": invoice_id, "events_url": f"/api/runs/{rid}/events"}


@app.post("/api/invoices/{invoice_id}/documents", status_code=201)
async def invoice_new_document(invoice_id: str, file: UploadFile = File(...), pace: str | None = Form(None),
                               x_ledgerlight_role: str | None = Header(None), x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    data = await file.read()
    try:
        pdfio.check_upload(data, config.MAX_UPLOAD_BYTES, config.MAX_PAGES)
    except pdfio.PdfRejected as e:
        return err(400, str(e))
    path = services.store_upload(file.filename or "document.pdf", data)
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM invoices WHERE id=?", (invoice_id,)).fetchone():
            raise HTTPException(404, "Invoice not found")
        con.execute("UPDATE invoices SET file_path=?, file_name=?, file_sha256=?, file_size=?, extraction=NULL, "
                    "corrections='{}' WHERE id=?", (str(path), file.filename, pdfio.sha256(data), len(data), invoice_id))
        db.audit(con, actor_type="human", actor_id=user, event_type="document_received", object_type="invoice",
                 object_id=invoice_id, invoice_id=invoice_id, summary=f"Received document {file.filename}; re-running",
                 payload={"file": file.filename})
    rid = services.rerun(invoice_id, pace=pace, use_cache=False, triggered_by=user, reason="Received document")
    start_background(rid)
    return {"run_id": rid, "invoice_id": invoice_id, "events_url": f"/api/runs/{rid}/events"}


# ------------------------------------------------------------------ review queue

@app.get("/api/review-queue")
def review_queue(tab: str = "review", assigned: str | None = None, min_exposure: float | None = None,
                 vendor_id: str | None = None, category: str | None = None, sort: str = "priority"):
    if tab not in ("review", "hold", "rejected", "resolved"):
        raise HTTPException(400, "tab must be review, hold, rejected or resolved")
    return repo.review_queue(tab=tab, assigned=assigned, min_exposure_paise=int(min_exposure * 100) if min_exposure else None,
                             vendor_id=vendor_id, category=category, sort=sort)


# ------------------------------------------------------------------ master data

@app.get("/api/vendors")
def vendors(q: str | None = None, status: str | None = None):
    return {"items": admin.list_vendors(q, status)}


@app.get("/api/vendors/{vid}")
def vendor_get(vid: str):
    v = admin.get_vendor(vid)
    if not v:
        raise HTTPException(404, "Vendor not found")
    return v


@app.post("/api/vendors", status_code=201)
async def vendor_create(request: Request, x_ledgerlight_role: str | None = Header(None),
                        x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    try:
        return admin.create_vendor(await _json(request), user=user)
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.patch("/api/vendors/{vid}")
async def vendor_update(vid: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                        x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    b = await _json(request)
    if any(k.startswith("bank") for k in b):
        return err(422, "Bank details change only through POST /api/vendors/{id}/bank (manager, with a reason).")
    try:
        return admin.update_vendor(vid, b, user=user)
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.post("/api/vendors/{vid}/bank")
async def vendor_bank(vid: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                      x_ledgerlight_user: str | None = Header(None)):
    role, user = who(x_ledgerlight_role, x_ledgerlight_user)
    try:
        return admin.change_bank(vid, await _json(request), user=user, role=role)
    except admin.Forbidden as e:
        return err(403, str(e))
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.get("/api/pos")
def pos(status: str | None = None, vendor_id: str | None = None, q: str | None = None):
    return {"items": admin.list_pos(status, vendor_id, q)}


@app.get("/api/pos/{po_id}")
def po_get(po_id: str):
    p = admin.get_po(po_id)
    if not p:
        raise HTTPException(404, "PO not found")
    return p


@app.post("/api/pos", status_code=201)
async def po_create(request: Request, x_ledgerlight_role: str | None = Header(None),
                    x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    try:
        return admin.create_po(await _json(request), user=user)
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.patch("/api/pos/{po_id}")
async def po_update(po_id: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                    x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    try:
        return admin.update_po(po_id, await _json(request), user=user)
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.post("/api/pos/{po_id}/lines", status_code=201)
async def po_add_line(po_id: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                      x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    try:
        return admin.add_po_line(po_id, await _json(request), user=user)
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.post("/api/pos/{po_id}/{action}")
async def po_status(po_id: str, action: str, request: Request, x_ledgerlight_role: str | None = Header(None),
                    x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    status = {"close": "closed", "cancel": "cancelled", "reopen": "open"}.get(action)
    if not status:
        raise HTTPException(404, "Unknown action")
    b = await _json(request)
    try:
        return admin.set_po_status(po_id, status, user=user, reason=b.get("reason"))
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.post("/api/import/{kind}")
async def import_csv(kind: str, file: UploadFile = File(...), commit: bool = False,
                     x_ledgerlight_role: str | None = Header(None), x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        return admin.import_csv(kind, text, commit=commit, user=user)
    except admin.Invalid as e:
        return err(422, e.args[0])


@app.get("/api/export/{kind}.csv")
def export_csv(kind: str, range: str = "30d"):
    if kind in ("vendors", "pos"):
        return PlainTextResponse(admin.export_csv(kind), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})
    if kind != "approved":
        raise HTTPException(404, "Unknown export")
    days = None if range == "all" else int(range.rstrip("d"))
    rows = repo.list_runs(statuses=["auto_approve", "approve_with_note"], range_days=days, page_size=100000)["items"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["invoice_id", "run_id", "vendor_id", "vendor", "invoice_no", "po", "gross_inr", "decision", "reason",
                "decided_at"])
    for r in rows:
        w.writerow([r["invoice_id"], r["run_id"], r["vendor_id"], r["vendor_name"], r["invoice_no"], r["po_id"],
                    f"{(r['gross_paise'] or 0) / 100:.2f}", r["outcome_label"], r["main_reason"], r["finished_at"]])
    with db.tx() as con:
        db.audit(con, actor_type="human", actor_id="export", event_type="export", object_type="export",
                 object_id="approved.csv", summary=f"Exported approved invoices (CSV), {range}", payload={"rows": len(rows)})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="approved.csv"'})


# ------------------------------------------------------------------ settings

def _settings_view() -> dict:
    ver, cfg = settings_store.current()
    dflt = default_config()
    rules = []
    for r in RULES:
        params = cfg["rules"].get(r["id"])
        rules.append({**r, "hard": bool(r.get("hard")), "enabled": cfg["enabled"].get(r["id"], True),
                      "can_disable": r["id"] not in HARD_STOP_RULES, "params": params,
                      "param_labels": {k: PARAM_LABELS.get(k, k) for k in (params or {})},
                      "default_params": dflt["rules"].get(r["id"]),
                      "is_default": params == dflt["rules"].get(r["id"]) and cfg["enabled"].get(r["id"], True),
                      "sentence": sentence(r["id"], cfg), "allowed": allowed_text(r["id"], cfg)})
    return {"version": ver, "config": cfg, "defaults": dflt, "rules": rules, "global": cfg["global"],
            "advanced": cfg["advanced"], "history": settings_store.history()}


@app.get("/api/settings")
def settings_get():
    return _settings_view()


@app.get("/api/settings/history")
def settings_history():
    return {"items": settings_store.history()}


@app.put("/api/settings")
async def settings_put(request: Request, x_ledgerlight_role: str | None = Header(None),
                       x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    b = await _json(request)
    try:
        ver, _, changes = settings_store.save(b.get("config") or {}, changed_by=user, reason=b.get("reason") or "")
    except settings_store.SettingsError as e:
        return err(422, e.errors)
    return {"version": ver, "changes": changes, "message": "Settings saved. New runs use these values. Existing decisions "
                                                            "are unchanged unless you re-run them.", **_settings_view()}


@app.post("/api/settings/preview")
async def settings_preview(request: Request):
    b = await _json(request)
    return admin.impact_preview(b.get("config") or {}, days=int(b.get("days") or 90))


@app.post("/api/settings/revert")
async def settings_revert(request: Request, x_ledgerlight_role: str | None = Header(None),
                          x_ledgerlight_user: str | None = Header(None)):
    _, user = who(x_ledgerlight_role, x_ledgerlight_user)
    b = await _json(request)
    to = b.get("to", "defaults")
    try:
        if to == "defaults":
            ver, _, ch = settings_store.save(default_config(), changed_by=user, reason=b.get("reason") or "",
                                             replace=True, summary="Reverted to shipped defaults")
        else:
            hist = settings_store.history()
            target = int(to) if str(to).isdigit() else (hist[1]["version"] if len(hist) > 1 else None)
            cfg = settings_store.get_version(target) if target else None
            if not cfg:
                return err(404, "No previous version to revert to.")
            ver, _, ch = settings_store.save(cfg, changed_by=user, reason=b.get("reason") or "", replace=True,
                                             summary=f"Reverted to version {target}")
    except settings_store.SettingsError as e:
        return err(422, e.errors)
    return {"version": ver, "changes": ch, **_settings_view()}


# ------------------------------------------------------------------ audit and metrics

@app.get("/api/audit")
def audit(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"),
          actor_type: str | None = None, user: str | None = None, event_type: str | None = None,
          object_id: str | None = None, invoice_id: str | None = None, q: str | None = None, page: int = 1,
          page_size: int = Query(100, le=1000)):
    return admin.audit_query(date_from=date_from, date_to=date_to, actor_type=actor_type, user=user,
                             event_type=event_type, object_id=object_id, invoice_id=invoice_id, q=q, page=page,
                             page_size=page_size)


@app.get("/api/audit/export")
def audit_export(format: str = "csv", date_from: str | None = Query(None, alias="from"),
                 date_to: str | None = Query(None, alias="to"), actor_type: str | None = None, event_type: str | None = None,
                 object_id: str | None = None, q: str | None = None):
    res = admin.audit_query(date_from=date_from, date_to=date_to, actor_type=actor_type, event_type=event_type,
                            object_id=object_id, q=q, page_size=100000)
    if format == "json":
        return Response(json.dumps(res["items"], indent=2, ensure_ascii=False, default=str), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="audit.json"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "ts", "actor_type", "actor", "event_type", "object_type", "object_id", "invoice_id", "run_id",
                "outcome", "summary", "payload"])
    for e in res["items"]:
        w.writerow([e["id"], e["ts"], e["actor_type"], e["actor_id"], e["event_type"], e["object_type"], e["object_id"],
                    e["invoice_id"], e["run_id"], e["outcome"], e["summary"], json.dumps(e["payload"], ensure_ascii=False)])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="audit.csv"'})


@app.get("/api/metrics")
def metrics(range: str = "30d"):
    days = int(range.rstrip("d")) if range.rstrip("d").isdigit() else 30
    return repo.metrics(days)
