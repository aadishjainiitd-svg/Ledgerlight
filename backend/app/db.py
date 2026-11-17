"""SQLite storage (WAL mode). Money is integer paise; timestamps are UTC ISO-8601."""
from __future__ import annotations

import contextvars
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, short TEXT, aliases TEXT DEFAULT '[]',
  gstin TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'approved', payment_terms_days INTEGER DEFAULT 30,
  bank_name TEXT, bank_account_no TEXT, bank_ifsc TEXT, bank_changed_at TEXT, bank_verified_by TEXT,
  contact_phone TEXT, contact_email TEXT, address TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL REFERENCES vendors(id), issue_date TEXT, valid_to TEXT,
  status_override TEXT, currency TEXT DEFAULT 'INR', notes TEXT, is_seed INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS po_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT, po_id TEXT NOT NULL REFERENCES purchase_orders(id), line_no INTEGER,
  item_code TEXT, description TEXT, uom TEXT, ordered_qty REAL, unit_price_paise INTEGER,
  tax_rate_pct REAL, opening_billed_qty REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY, file_name TEXT, file_path TEXT, file_sha256 TEXT, file_size INTEGER, page_count INTEGER,
  doc_type TEXT, text_source TEXT, source TEXT, sample_id TEXT, vendor_id TEXT,
  vendor_name_raw TEXT, vendor_gstin_raw TEXT, invoice_no_raw TEXT, invoice_no_canonical TEXT,
  serial_token TEXT, invoice_date TEXT, date_ambiguous INTEGER DEFAULT 0, po_ref_raw TEXT, po_id TEXT,
  po_match_method TEXT, po_match_score REAL, po_runner_up TEXT, currency TEXT, subtotal_paise INTEGER,
  tax_paise INTEGER, total_paise INTEGER, tax_inclusive INTEGER DEFAULT 0, bank_name_raw TEXT,
  bank_account_raw TEXT, bank_ifsc_raw TEXT, bank_change_notice INTEGER DEFAULT 0, fields TEXT,
  extraction TEXT, corrections TEXT DEFAULT '{}', current_decision_id INTEGER, current_run_id TEXT,
  is_synthetic INTEGER DEFAULT 0, paid_at TEXT, info_requested_at TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_inv_vendor ON invoices(vendor_id);
CREATE INDEX IF NOT EXISTS ix_inv_hash ON invoices(file_sha256);
CREATE TABLE IF NOT EXISTS line_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT NOT NULL, line_no INTEGER, description_raw TEXT,
  description_norm TEXT, item_code TEXT, qty REAL, uom TEXT, unit_price_paise INTEGER, amount_paise INTEGER,
  pretax_amount_paise INTEGER, tax_rate_pct REAL, matched_po_line_ids TEXT DEFAULT '[]', match_method TEXT,
  match_score REAL, confidence REAL, alloc TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_li_inv ON line_items(invoice_id);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL, source TEXT, status TEXT, current_stage INTEGER DEFAULT 0,
  started_at TEXT, finished_at TEXT, duration_ms INTEGER, pace TEXT, pace_ms INTEGER, use_cache INTEGER DEFAULT 1,
  config_version INTEGER, model_name TEXT, prompt_version TEXT, extraction_mode TEXT, parent_run_id TEXT,
  triggered_by TEXT, error TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_runs_inv ON runs(invoice_id);
CREATE TABLE IF NOT EXISTS stage_results (
  run_id TEXT NOT NULL, stage_no INTEGER NOT NULL, stage_name TEXT, status TEXT, severity_max TEXT,
  started_at TEXT, ended_at TEXT, duration_ms INTEGER, input_summary TEXT, output_summary TEXT, message TEXT,
  PRIMARY KEY (run_id, stage_no)
);
CREATE TABLE IF NOT EXISTS rule_results (
  run_id TEXT NOT NULL, rule_id TEXT NOT NULL, stage_no INTEGER, rule_name TEXT, severity TEXT,
  skipped INTEGER DEFAULT 0, message_plain TEXT, facts TEXT, threshold_used TEXT, exposure_paise INTEGER DEFAULT 0,
  PRIMARY KEY (run_id, rule_id)
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, invoice_id TEXT NOT NULL, version INTEGER, outcome TEXT,
  headline TEXT, explanation TEXT, driving_rule_ids TEXT, exposure_paise INTEGER DEFAULT 0, category TEXT,
  assigned_to TEXT, sla_due_at TEXT, made_by TEXT, actor_name TEXT, actor_role TEXT, reason_code TEXT,
  reason_text TEXT, supersedes_decision_id INTEGER, confirmed_by TEXT, confirmed_at TEXT, drafts TEXT,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_dec_inv ON decisions(invoice_id);
CREATE TABLE IF NOT EXISTS run_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT, event TEXT, data TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ev_run_seq ON run_events(run_id, seq);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor_type TEXT, actor_id TEXT, event_type TEXT,
  object_type TEXT, object_id TEXT, run_id TEXT, invoice_id TEXT, summary TEXT, payload TEXT, outcome TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_events(ts);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TABLE IF NOT EXISTS settings_versions (
  version INTEGER PRIMARY KEY, config TEXT NOT NULL, changed_by TEXT, reason TEXT, summary TEXT,
  changes TEXT, changed_at TEXT
);
CREATE TABLE IF NOT EXISTS extraction_cache (
  cache_key TEXT PRIMARY KEY, file_sha256 TEXT, prompt_version TEXT, model TEXT, result TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_lock = threading.RLock()
_initialised: set[str] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str, nbytes: int = 3) -> str:
    return f"{prefix}{secrets.token_hex(nbytes)}"


def dumps(v) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def loads(v, default=None):
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ per-visitor sandboxes
# With LEDGERLIGHT_SANDBOXES=1 (the public deployment) every visitor gets a private copy of the demo database,
# cloned from a template that is seeded once at startup. The visitor's sandbox id travels with each request
# (header or ?sandbox=) and is held in a context variable, which background runs inherit, so every query of a
# request or run goes to that visitor's file. Without the setting there is one database, as before.
_SANDBOX: contextvars.ContextVar[str | None] = contextvars.ContextVar("ledgerlight_sandbox", default=None)
SANDBOX_RE = re.compile(r"^[a-f0-9]{16,40}$")
TEMPLATE = "template"
SANDBOX_MAX_AGE_S = 24 * 3600
SANDBOX_MAX_COUNT = 300


def sandboxes_enabled() -> bool:
    return config.SANDBOXES


def current_sandbox() -> str | None:
    return _SANDBOX.get()


@contextmanager
def use_sandbox(sb: str | None):
    token = _SANDBOX.set(sb)
    try:
        yield
    finally:
        _SANDBOX.reset(token)


def sandbox_dir() -> Path:
    return Path(config.DATA_DIR) / "sandboxes"


def template_path() -> Path:
    return Path(config.DATA_DIR) / "template.db"


def shared_path() -> Path:
    """Where data shared by all visitors lives (the AI extraction cache): the main database without sandboxes."""
    return Path(config.DATA_DIR) / "shared.db" if sandboxes_enabled() else Path(config.DB_PATH)


def db_path() -> Path:
    sb = _SANDBOX.get()
    if sb == TEMPLATE:
        return template_path()
    if sb:
        return sandbox_dir() / f"{sb}.db"
    return Path(config.DB_PATH)


def _copy_db(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst), timeout=30)
    try:
        s.backup(d)
    finally:
        s.close()
        d.close()


def ensure_sandbox(sb: str, fresh: bool = False) -> bool:
    """Create the sandbox from the template if it does not exist (or always, with fresh=True, which is a reset).
    Returns True when a copy was made."""
    p = sandbox_dir() / f"{sb}.db"
    if p.exists() and not fresh:
        try:
            os.utime(p, None)          # last-used time, for clean-up
        except OSError:
            pass
        return False
    with _lock:
        if p.exists() and not fresh:
            return False
        if not template_path().exists():
            raise RuntimeError("The demo template database has not been built yet.")
        _copy_db(template_path(), p)
        _initialised.discard(str(p))
    _clean_sandboxes(keep=p)
    return True


def _clean_sandboxes(keep: Path) -> None:
    """Delete sandboxes unused for a day, and the oldest beyond the cap."""
    try:
        files = sorted(sandbox_dir().glob("*.db"), key=lambda f: f.stat().st_mtime)
    except OSError:
        return
    now = time.time()
    doomed = [f for f in files if f != keep and now - f.stat().st_mtime > SANDBOX_MAX_AGE_S]
    rest = [f for f in files if f not in doomed]
    doomed += [f for f in rest[:max(0, len(rest) - SANDBOX_MAX_COUNT)] if f != keep]
    for f in doomed:
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(f) + suffix).unlink(missing_ok=True)
            except OSError:
                pass
        _initialised.discard(str(f))


@contextmanager
def shared_conn():
    """Connection to the shared database (AI extraction cache), whatever sandbox is active."""
    con = connect(shared_path())
    try:
        yield con
    finally:
        con.close()


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path is not None else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=30, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("PRAGMA busy_timeout=30000")
    key = str(p)
    if key not in _initialised:
        with _lock:
            con.executescript(SCHEMA)
            _initialised.add(key)
    return con


@contextmanager
def conn():
    con = connect()
    try:
        yield con
    finally:
        con.close()


@contextmanager
def tx():
    """A write transaction (serialised across threads)."""
    with _lock:
        con = connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()


def row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def reset_schema() -> None:
    """Drop everything and recreate (demo reset). The audit triggers are dropped with the table.

    extraction_cache is kept: entries are keyed by file hash, prompt version and model, so they stay correct, and a
    demo reset must not throw away an AI reading that took a minute on a rate-limited provider."""
    with _lock:
        con = connect()
        try:
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for t in tables:
                if t == "extraction_cache":
                    continue
                con.execute(f"DROP TABLE IF EXISTS {t}")
            con.executescript(SCHEMA)
        finally:
            con.close()


def audit(con: sqlite3.Connection, *, actor_type: str, actor_id: str, event_type: str, summary: str,
          object_type: str | None = None, object_id: str | None = None, run_id: str | None = None,
          invoice_id: str | None = None, payload: dict | None = None, outcome: str | None = None,
          ts: str | None = None) -> None:
    con.execute(
        "INSERT INTO audit_events (ts, actor_type, actor_id, event_type, object_type, object_id, run_id, "
        "invoice_id, summary, payload, outcome) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ts or now_iso(), actor_type, actor_id, event_type, object_type, object_id, run_id, invoice_id,
         summary, dumps(payload or {}), outcome))
