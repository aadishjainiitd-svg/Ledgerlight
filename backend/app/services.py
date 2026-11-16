"""Shared operations used by the API and the tests: store an upload, start a run, list samples."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config, db, pdfio, pipeline


def samples() -> list[dict]:
    p = config.SAMPLES_DIR / "expected.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for s in data["samples"]:
        f = config.SAMPLES_DIR / s["file"]
        out.append({**s, "available": f.exists(), "size_bytes": f.stat().st_size if f.exists() else None})
    return out


def sample_by_id(sample_id: str) -> dict | None:
    return next((s for s in samples() if s["id"].lower() == sample_id.lower()), None)


def store_upload(file_name: str, data: bytes) -> Path:
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name).name)[-120:] or "invoice.pdf"
    p = config.UPLOAD_DIR / f"{pdfio.sha256(data)[:12]}_{safe}"
    if not p.exists():
        p.write_bytes(data)
    return p


def new_run(*, file_name: str, data: bytes, source: str, sample_id: str | None, pace, use_cache: bool,
            triggered_by: str) -> tuple[str, str]:
    """Validate, store and register an invoice and a queued run. Raises pdfio.PdfRejected."""
    pdfio.check_upload(data, config.MAX_UPLOAD_BYTES, config.MAX_PAGES)
    path = store_upload(file_name, data)
    with db.tx() as con:
        iid = pipeline.create_invoice(con, file_name=file_name, file_path=str(path), data=data, source=source,
                                      sample_id=sample_id)
        rid = pipeline.create_run(con, invoice_id=iid, source=source, pace=pace, use_cache=use_cache,
                                  triggered_by=triggered_by)
        db.audit(con, actor_type="human", actor_id=triggered_by, event_type="run_created", object_type="invoice",
                 object_id=iid, run_id=rid, invoice_id=iid,
                 summary=f"{'Started sample ' + sample_id if sample_id else 'Uploaded ' + file_name}",
                 payload={"run": rid, "source": source, "file": file_name, "pace": pace, "use_cache": use_cache})
    return iid, rid


def rerun(invoice_id: str, *, pace, use_cache: bool, triggered_by: str, reason: str | None = None,
          parent_run_id: str | None = None) -> str:
    with db.tx() as con:
        inv = con.execute("SELECT id, file_path, current_run_id FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or not inv["file_path"]:
            raise ValueError("This invoice has no stored PDF to re-run.")
        rid = pipeline.create_run(con, invoice_id=invoice_id, source="rerun", pace=pace, use_cache=use_cache,
                                  triggered_by=triggered_by, parent_run_id=parent_run_id or inv["current_run_id"])
        db.audit(con, actor_type="human", actor_id=triggered_by, event_type="run_created", object_type="invoice",
                 object_id=invoice_id, run_id=rid, invoice_id=invoice_id,
                 summary=f"Re-ran invoice {invoice_id}" + (f": {reason}" if reason else ""),
                 payload={"run": rid, "parent_run_id": parent_run_id or inv["current_run_id"], "reason": reason})
    return rid
