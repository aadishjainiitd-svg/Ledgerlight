# Ledgerlight API

Base URL: `http://127.0.0.1:8010` (all routes are under `/api`). Interactive OpenAPI docs: `/docs`.

## Conventions

| Topic | Rule |
|---|---|
| Money | Integer **paise** in every `*_paise` field (₹1 = 100 paise). Settings thresholds are in **rupees** (as typed in S7). |
| Dates | `invoice_date`, `issue_date`, `valid_to`: `YYYY-MM-DD`. Timestamps: UTC ISO-8601 with `Z`. |
| Outcomes | `auto_approve` (chip "Approved"), `approve_with_note` ("Approved, note"), `route_for_review` ("Needs review"), `hold_request_info` ("On hold"), `reject` ("Rejected"). Run rows can also be `running`, `failed`, `cancelled`. |
| Severities | `pass` < `note` < `review` < `hold` < `reject`. A rule with `skipped: true` was not evaluated (message says why). |
| Role switcher | Send `X-Ledgerlight-Role: clerk` (default, "Priya Nair") or `manager` ("Rahul Mehta"). Optional `X-Ledgerlight-User: <name>`. Used for permissions and the audit log. |
| Errors | JSON `{"error": "plain English"}` or `{"error": "Validation failed", "fields": {"R10.note_pct": "..."}}`. 400 bad input, 403 role not allowed, 404 not found, 409 conflict, 422 validation. |
| CORS | `*` by default (`LEDGERLIGHT_CORS_ORIGINS` to restrict). |
| "Today" | `LEDGERLIGHT_AS_OF` (default `2026-11-16`) for date rules and dashboard ranges. |

## Endpoint index

| Screen | Method and path | Purpose |
|---|---|---|
| all | `GET /api/health` | Status, extraction mode (`llm` or `text-only`), pacing presets |
| all | `GET /api/meta` | Stages, rule catalogue with sentences, outcomes, reason codes, roles, categories |
| S1 | `GET /api/metrics?range=7d\|30d\|90d` | KPI tiles with trends, 4 charts, needs-attention banner |
| S1 | `GET /api/runs` | Runs table with filters, search, sorting, paging and status counts |
| S1 | `GET /api/stream/runs` | SSE: run created / stage / completed, overrides, demo reset (live dashboard) |
| S1 | `GET /api/export/approved.csv?range=30d` | CSV of approved invoices |
| S2 | `GET /api/samples` | The 7 sample cards (expected outcome, tags, run-before badge) |
| S2 | `GET /api/samples/{id}/pdf`, `GET /api/samples/{id}/thumbnail.png?dpi=40` | Sample file and thumbnail |
| S2 | `POST /api/runs` | Upload PDFs (multipart) or start a sample (JSON). Returns run ids |
| S3 | `GET /api/runs/{run_id}/events` | SSE stream of a run: live, reconnect with `Last-Event-ID`, or `?replay=true&speed=1` |
| S3 | `POST /api/runs/{run_id}/cancel`, `POST /api/runs/{run_id}/retry` | Control |
| S4 | `GET /api/runs/{run_id}` | Full decision detail for that run |
| S4 | `GET /api/invoices/{invoice_id}` | Same detail for the invoice's current run |
| S4 | `GET /api/invoices/{id}/pdf`, `GET /api/invoices/{id}/pages/{n}.png?dpi=110` | Original PDF, page image |
| S4 | `GET /api/runs/{run_id}/decision.json` | Downloadable decision JSON |
| S4/S5 | `POST /api/invoices/{id}/override` | Override with reason code + text (roles enforced) |
| S4/S5 | `POST /api/invoices/{id}/accept` | Confirm the system decision |
| S4 | `POST /api/invoices/{id}/rerun` | Re-run (e.g. after master data or settings change) |
| S4 | `PATCH /api/invoices/{id}/fields/{name}` | Correct an extracted field and re-run stages 3-9 |
| S4/S8 | `GET /api/invoices/{id}/audit` | Per-invoice trace |
| S5 | `GET /api/review-queue` | Tabs Needs review / On hold / Rejected / Resolved with counts |
| S5 | `POST /api/invoices/{id}/info-requested` | Start the hold SLA wait |
| S5 | `POST /api/invoices/{id}/documents` | Upload a received document and re-run |
| S6 | `GET/POST /api/vendors`, `GET/PATCH /api/vendors/{id}`, `POST /api/vendors/{id}/bank` | Vendor master |
| S6 | `GET/POST /api/pos`, `GET/PATCH /api/pos/{id}`, `POST /api/pos/{id}/lines`, `POST /api/pos/{id}/close\|cancel\|reopen` | PO master with cumulative position |
| S6 | `POST /api/import/{vendors\|pos}?commit=false\|true`, `GET /api/export/{vendors\|pos}.csv` | CSV import (preview then commit) and export |
| S7 | `GET /api/settings`, `PUT /api/settings`, `POST /api/settings/preview`, `POST /api/settings/revert`, `GET /api/settings/history` | Rules and tolerances |
| S8 | `GET /api/audit`, `GET /api/audit/export?format=csv\|json` | Append-only audit log |
| demo | `POST /api/demo/reset`, `POST /api/demo/seed` | Reset to the seeded demo state |

---

## S1 Dashboard

### `GET /api/metrics?range=30d`
```json
{
  "range_days": 30, "as_of": "2026-11-16T18:29:00+00:00", "period_start": "...",
  "tiles": {
    "processed":                  {"value": 60, "previous": 0, "change": 60},
    "straight_through_rate":      {"value": 70.0, "previous": null, "change": null},
    "median_time_to_decision_ms": {"value": 12193, "previous": null, "change": null, "manual_baseline_ms": 540000},
    "open_exceptions":            {"value": 14, "previous": 0, "change": 14, "value_all_time": 14},
    "value_protected_paise":      {"value": 29287200, "contributors": [{"category": "Duplicate", "count": 3, "value_paise": 13134000}]},
    "value_approved_paise":       {"value": 1084073346}
  },
  "charts": {
    "decisions_per_week": [{"week_start": "2026-10-12", "auto_approve": 3, "approve_with_note": 1, "route_for_review": 0, "hold_request_info": 0, "reject": 0}],
    "outcome_mix": {"auto_approve": 32, "approve_with_note": 10, "route_for_review": 9, "hold_request_info": 5, "reject": 4},
    "top_exception_reasons": [{"category": "Quantity or price above PO", "count": 6}],
    "median_time_per_week": [{"week_start": "2026-10-12", "median_ms": 12000}]
  },
  "banner": {"review": 9, "hold": 5, "oldest_days": 3, "text": "9 invoices need review, 5 on hold, oldest 3 days"},
  "running": 0, "estimated_minutes_saved": 528.4
}
```
Straight-through rate uses the latest **system** decision (no human touch). `value_protected` sums the exposure of duplicate and over-billing exceptions. Time saved is an estimate against the manual baseline in settings.

### `GET /api/runs`
Query: `status` (comma list of outcomes incl. `running`, `failed`), `q` (vendor, invoice no., PO, run id), `range` (`7d`, `30d` default, `90d`, `all`), `vendor_id`, `overridden` (bool), `all_runs` (default false = latest run per invoice), `sort` (`time`, `amount`, `vendor`, `invoice_no`, `duration`, `confidence`, `outcome`, `po`), `order` (`asc`/`desc`), `page`, `page_size` (default 25).

```json
{"total": 60, "page": 1, "page_size": 25,
 "counts": {"all": 60, "auto_approve": 32, "approve_with_note": 10, "route_for_review": 9, "hold_request_info": 5, "reject": 4, "running": 0, "failed": 0, "cancelled": 0},
 "items": [{
   "run_id": "run_a51511", "invoice_id": "INV-27F8F2C1", "received_at": "2026-11-16T09:12:01.120Z", "finished_at": "...",
   "status": "completed", "outcome": "auto_approve", "outcome_label": "Approved",
   "current_stage": 9, "stage_label": null,
   "vendor_id": "V-101", "vendor_name": "Brightline Office Supplies Pvt Ltd", "vendor_short": "Brightline",
   "invoice_no": "BL/2026/0412", "po_id": "PO-2026-1001", "po_inferred": false, "gross_paise": 59000000,
   "main_reason": "All 16 checks passed. Prices, quantities, GST and total match PO-2026-1001.",
   "headline": "Approved: everything checks out and it is safe to pay.",
   "lowest_confidence": 0.96, "duration_ms": 6077, "overridden": false, "exposure_paise": 0,
   "assigned_to": null, "category": null, "is_synthetic": false, "has_pdf": true, "file_name": "SI-01_....pdf",
   "doc_type": "text", "source": "upload", "sample_id": null, "is_latest_run": true, "error": null}]}
```
While running, `outcome` is `running` and `stage_label` is e.g. `"Stage 6 of 9: PO match"`. Seeded history rows have `is_synthetic: true, has_pdf: false` (S4 shows "PDF not stored for demo history").

### `GET /api/stream/runs` (SSE)
Events: `run_created {run_id, invoice_id, file_name}`, `run_stage {run_id, invoice_id, stage_no, name}`, `run_completed {run_id, invoice_id, outcome}`, `run_failed`, `run_cancelled`, `decision_overridden {invoice_id, outcome, ...}`, `demo_reset`. Heartbeat comment every 15 s.

## S2 New run

### `GET /api/samples?reveal=true`
```json
{"samples": [{"id": "SI-03", "file": "SI-03_kestrel_K-1241.pdf", "vendor": "Kestrel Print & Pack", "vendor_id": "V-103",
  "title": "Kestrel: split PO, third lot", "description": "Third invoice against a split PO, same template as before",
  "tags": ["text PDF", "split PO", "EC1"], "edge_case": "EC1", "invoice_no": "K/1241", "gross_paise": 14160000,
  "requires_llm": false, "available": true, "size_bytes": 78000,
  "expected_outcome": "route_for_review", "expected_label": "Needs review", "driving_rules": ["R11", "R12"],
  "run_before": false, "runnable_now": true, "note": null,
  "pdf_url": "/api/samples/SI-03/pdf", "thumbnail_url": "/api/samples/SI-03/thumbnail.png"}]}
```
`reveal=false` hides the expected outcome ("Show what to expect" toggle). SI-05 has `requires_llm: true`; without a key `runnable_now` is false and `note` explains it will be held.

### `POST /api/runs`
Either **multipart** (`files` repeated, up to 10 PDFs; optional `pace`, `use_cache`) or **JSON** `{"sample_id": "SI-01", "pace": "normal", "use_cache": true}`.

`pace`: `instant` (0 ms), `fast` (150), `normal` (550, default), `slow` (1200) or a number of ms: the minimum visible dwell per stage (display pacing, logged as such). `use_cache`: reuse a saved AI extraction for the same file, prompt version and model.

Response `201`:
```json
{"runs": [{"run_id": "run_a51511", "invoice_id": "INV-27F8F2C1", "file_name": "SI-01.pdf",
           "events_url": "/api/runs/run_a51511/events", "detail_url": "/api/runs/run_a51511"}],
 "rejected": [{"file_name": "notes.txt", "error": "Only PDF files are supported."}]}
```
Rejection messages: "Only PDF files are supported.", "File is larger than 10 MB.", "This PDF is password protected. Ask the sender for an unlocked copy.", "This PDF has 14 pages; the limit is 10." If every file is rejected the status is 400 with the same `rejected` list. The run starts immediately in the background; open the SSE stream next.

## S3 Live run view: SSE

### `GET /api/runs/{run_id}/events`
`Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `retry: 2000`, heartbeat `: heartbeat` every 15 s.

Every event is **persisted before it is published**, so the stream is the same for live viewers, late joiners and reconnects:
- Reconnect: the browser's `EventSource` sends `Last-Event-ID`; or pass `?last_event_id=N`. Only events with `id > N` are sent.
- Finished run: all stored events are sent at once, then the stream closes.
- Replay mode (S3 "Replay"): `?replay=true&speed=1` re-sends stored events with their original spacing divided by `speed` (gaps capped at 2.5 s).
- The stream closes after `run_completed`, `run_failed` or `run_cancelled`.

Wire format (one message):
```
id: 74
event: stage_completed
data: {"stage_no": 5, "name": "Duplicate check", "status": "done", "severity_max": "reject", "duration_ms": 561, "work_ms": 12, "display_pacing_ms": 549, "message": "Closest match BL/2026/0377, similarity 1.00.", "input": {}, "output": {"score": 1.0, "exact": null, "closest_invoice": "INV-...", "closest_invoice_no": "BL/2026/0377", "signals": {"amount": 1.0, "number": 1.0, "date": 1.0, "po": 1.0, "lines": 1.0}}, "_ts": "2026-11-16T09:12:04.512Z"}
```
`id` increases by 1 per run. `_ts` is the server timestamp of the event.

| `event` | `data` fields | Drives |
|---|---|---|
| `run_started` | `run_id, invoice_id, file_name, source, pace_ms, config_version, stages[{stage_no,name}]` | Header, skeleton rail |
| `stage_started` | `stage_no, name` | Card turns Running |
| `field_extracted` | `field, label, value, raw_text, confidence` (model's own, 0-1), `source` (`text layer`, `OCR text layer`, `image read`, `vision + text layer`, `not found`) | Field card appears (stage 2) |
| `line_extracted` | `line_no, description, item_code, qty, uom, unit_price, amount, tax_rate_pct, confidence` (raw printed strings) | Line-items table row |
| `field_confidence` | `field, label, value, display` (formatted), `model_confidence, evidence, format_valid, effective_confidence, boosted, boosted_from, source, why, ambiguous` | Confidence chip and "why" tooltip (stage 3). Chip colours: >= 0.90 green, 0.75-0.90 amber, < 0.75 red |
| `log` | `stage_no` (0 = run), `level` (`info`,`pass`,`warn`,`fail`), `text`, `display_pacing` (bool) | Streaming log |
| `rule_result` | `rule_id, rule_name, stage_no, severity, skipped, message, exposure_paise` | Tick or flag in the stage card. R03 can be sent twice (stage 3, then re-checked against the PO date at stage 6): keep the latest |
| `stage_completed` | `stage_no, name, status` (`done`,`skipped`,`failed`), `severity_max, duration_ms, work_ms, display_pacing_ms, message, input, output` | Card result line and expanded input/output |
| `decision` | `decision_id, version, outcome, label, headline, exposure_paise, assigned_to` (`clerk`/`manager`/null), `driving_rule_ids, category, explanation{headline, ok[], attention[], next_step, alternative_step, confidence_note, short_reason, polished}, explanation_mode, sla_due_at` | Decision reveal |
| `run_completed` | `run_id, duration_ms, outcome` | Timer stops; stream closes |
| `run_failed` | `stage_no, error, retryable` | Failed card with Retry (`POST /api/runs/{id}/retry`) |
| `run_cancelled` | `run_id, reason` | Cancelled state |

Typical order: `run_started`, then per stage `stage_started`, `log`*, (`field_extracted`*, `line_extracted`* in stage 2), (`field_confidence`* in stage 3), `rule_result`* (stages 3-7), `stage_completed`; `decision` inside stage 9; `run_completed`.

Stage outputs (`stage_completed.output`): 1 `{sha256, page_count, doc_type, text_source, chars_per_page, looks_like_invoice, seen_before}`; 2 `{extractor, model, fields_found, line_items, cached, passes}`; 3 `{invoice_no, canonical, serial_token, invoice_date, subtotal_paise, tax_paise, total_paise, tax_inclusive, reconciled}`; 4 `{vendor_id, vendor_name, method, score, status, bank}`; 5 `{score, exact, closest_invoice, closest_invoice_no, signals}`; 6 `{po_id, method, score, runner_up, candidates[], pct_billed_before, alignment[]}`; 7 `{rules{R10..R16: severity}}`; 8 `{outcome, driving_rule_ids, exposure_paise, assigned_to}`; 9 `{headline, explanation_mode, drafts[]}`.

### `POST /api/runs/{run_id}/cancel` -> `{"run_id", "cancel_requested": true}` (409 if already finished). The run stops at the next stage boundary.
### `POST /api/runs/{run_id}/retry` -> `201 {"run_id", "invoice_id", "events_url"}` (new run of the same invoice; `parent_run_id` links them).

## S4 Invoice decision detail

### `GET /api/runs/{run_id}` and `GET /api/invoices/{invoice_id}`
```jsonc
{
  "invoice": {"id", "file_name", "file_sha256", "page_count", "doc_type": "text|scanned", "text_source": "text_layer|ocr_layer|none",
              "vendor_id", "vendor_name_raw", "vendor_gstin_raw", "invoice_no_raw", "invoice_no_canonical", "serial_token",
              "invoice_date", "date_ambiguous", "po_ref_raw", "po_id", "po_match_method": "explicit|implied|other_vendor|none",
              "po_match_score", "currency", "subtotal_paise", "tax_paise", "total_paise", "tax_inclusive", "paid_at",
              "info_requested_at", "is_synthetic", "created_at", "current_run_id", "source", "sample_id"},
  "has_pdf": true, "pdf_url": "/api/invoices/INV-.../pdf", "pdf_note": null,
  "run": {"id", "status", "started_at", "finished_at", "duration_ms", "pace", "pace_ms", "config_version", "model_name",
          "prompt_version", "extraction_mode": "llm|text-parser|unavailable", "parent_run_id", "triggered_by", "error"},
  "stages": [{"stage_no": 1, "stage_name": "Ingest", "status": "done", "severity_max": "pass", "duration_ms": 561,
              "message": "...", "input_summary": {}, "output_summary": {}}],          // always 9 entries
  "fields": {"total": {"label": "Total", "value": "78,750", "raw_text": "78,7?0", "model_confidence": 0.78, "evidence": 1.0,
                       "format_valid": 1.0, "effective_confidence": 0.92, "boosted": true, "boosted_from": 0.89,
                       "source": "image read", "why": "Read at 0.89, raised to 0.92 because the lines plus tax equal the total.",
                       "parsed": 7875000}},                                            // vendor_name, vendor_gstin, invoice_no, invoice_date, po_reference, currency, subtotal, tax_total, total, bank_*
  "corrections": {},
  "lines": [{"line_no": 1, "description_raw", "item_code", "qty", "uom", "unit_price_paise", "amount_paise", "pretax_amount_paise",
             "tax_rate_pct", "matched_po_line_ids": [12], "match_method": "sku|fuzzy|bundle|none", "match_score", "confidence",
             "alloc": [{"po_line_id": 12, "qty": 3000, "amount_paise": 12000000}]}],
  "vendor_panel": {"vendor": {"id", "name", "short", "gstin", "status", "payment_terms_days", "contact_phone", "bank_changed_at", "bank_verified_by"},
                   "match": {"method": "gstin|name|fuzzy|none", "score", "gstin_on_invoice"},
                   "bank_on_invoice": {"bank_name", "account", "account_masked": "ending 3347", "ifsc", "change_notice", "change_text"},
                   "bank_on_file": {"bank_name", "account", "account_masked", "ifsc"}, "bank_match": false},
  "duplicate_panel": {"score": 1.0, "thresholds": {"review": 0.6, "reject": 0.85}, "exact": null, "closest": {"id", "invoice_no",
                      "total_paise", "invoice_date", "po_id", "outcome", "decided_at", "paid_at", "lines": []},
                      "signals": {"amount": 1, "number": 1, "date": 1, "po": 1, "lines": 1}, "recurring_guard": false, "compared": 12,
                      "compare": [{"signal": "amount", "label": "Total amount", "weight": 0.3, "this": 11800000, "other": 11800000, "score": 1.0}]},
  "po_panel": {"po": {"id", "vendor_id", "issue_date", "valid_to", "status", "currency", "subtotal_paise", "tax_paise", "total_paise",
                      "billed_subtotal_paise", "pending_subtotal_paise", "remaining_subtotal_paise", "pct_billed"},
               "match_method": "explicit", "match_score": 1.0, "runner_up": {"po_id", "score", "candidates": [{"po_id", "score", "parts": {"desc", "price", "qty", "total", "date"}}]},
               "written_as": "PO-2026-1004",
               "table": [{"po_line_id", "item_code", "po_description", "invoice_line_no", "invoice_description", "match_method", "bundle",
                          "uom", "ordered_qty", "billed_before_qty", "pending_qty", "this_invoice_qty", "remaining_before_qty",
                          "remaining_after_qty", "po_unit_price_paise", "invoice_unit_price_paise", "unit_price_delta_pct",
                          "amount_variance_paise", "amount_variance_pct", "over_qty", "tax_rate_pct", "status"}],
               "cumulative": {"before_pct": 76.19, "after_pct": 104.76, "before_paise", "this_invoice_paise", "po_subtotal_paise", "pending_paise"},
               "timeline": [{"invoice_id", "invoice_no", "invoice_date", "total_paise", "outcome", "paid_at", "is_current", "run_id"}]},
  "rules": [{"rule_id": "R11", "name": "Quantity vs PO remaining", "stage_no": 7, "group": "Numbers", "hard_stop": false,
             "severity": "review", "skipped": false, "message": "3,000 cartons billed against 2,500 remaining: ...",
             "facts": {}, "threshold_used": {}, "exposure_paise": 2360000, "allowed": "Allowed: 0.5% passes; 2% notes"}],   // always 16
  "decision": {"id", "run_id", "version", "outcome", "outcome_label", "outcome_long", "headline",
               "explanation": {"headline", "ok": [], "attention": [], "next_step", "alternative_step", "confidence_note",
                               "main_reason", "short_reason", "polished", "banner"?, "override"?},
               "driving_rule_ids": ["R11", "R12"], "exposure_paise", "category", "assigned_to", "sla_due_at",
               "made_by": "system|user", "actor_name", "actor_role", "reason_code", "reason_text", "supersedes_decision_id",
               "confirmed_by", "confirmed_at", "drafts": [], "created_at"},
  "system_decision": {},            // the run's own system decision (unchanged by overrides)
  "decision_history": [],           // every version, oldest first; version 1 is the system decision
  "overridden": false,
  "drafts": [{"kind": "credit|return|verify|info", "title", "to", "subject", "body"},
             {"kind": "checklist", "title": "Verification checklist (manager releases the hold)", "items": ["..."]}],
  "timeline": [{"id", "ts", "actor_type", "actor_id", "event_type", "summary", "outcome", "run_id"}],
  "technical": {"extraction": {}, "config_version", "model_name", "prompt_version", "extraction_mode"}
}
```

### `POST /api/invoices/{id}/override`
```json
{"action": "approve|reject|hold", "reason_code": "Credit note requested", "reason_text": "Credit note for 500 cartons requested",
 "checklist": {"called_vendor_on_master_number": true, "written_request_received": true, "second_person_confirmed": true}}
```
`reason_code` is one of `GET /api/meta` `reason_codes`; `reason_text` needs 10+ characters (422 otherwise). `hold` = "Send back for info". Permissions (spec 3.8): a **clerk** may approve only a `route_for_review` decision with exposure up to the clerk limit (default ₹10,000) and not a hard stop (R04, R05, R06); reject and hold are open to both roles. Releasing a bank-change hold (R05) is **manager only** and needs all three checklist items. 403 with a plain message when not allowed. Response: `{"decision_id", "version", "outcome", "previous_outcome", "invoice": <detail>}`. The original decision is kept in `decision_history`; an audit event `decision_overridden` records before, after and the reason.

### `POST /api/invoices/{id}/accept` `{"note": "optional"}` -> `{"decision_id", "confirmed_by", "confirmed_at"}`
### `POST /api/invoices/{id}/rerun` `{"reason"?, "pace"?, "use_cache"?: true}` -> `201 {"run_id", "invoice_id", "events_url"}`. Uses the current settings and master data; reuses the saved extraction for the same file.
### `PATCH /api/invoices/{id}/fields/{name}` `{"value": "78,750", "reason": "Read from the paper copy"}` -> `201 {"run_id", ...}`. `name` is one of `vendor_name, vendor_gstin, invoice_no, invoice_date, po_reference, currency, subtotal, tax_total, total, bank_name, bank_account, bank_ifsc`. Both values are stored; the field shows `source: "corrected by user"`.
### `GET /api/invoices/{id}/pdf` (inline PDF; 404 "PDF not stored for demo history." for seeded rows) and `GET /api/invoices/{id}/pages/{n}.png`
### `GET /api/runs/{run_id}/decision.json` (attachment).

## S5 Review queue

### `GET /api/review-queue?tab=review|hold|rejected|resolved`
Filters: `assigned=clerk|manager`, `min_exposure` (rupees, strictly above), `vendor_id`, `category`, `sort=priority|age|exposure` (priority = exposure x (1 + age days)).
```json
{"tab": "review", "counts": {"review": 9, "hold": 5, "rejected": 4, "resolved": 0}, "open_exceptions": 14,
 "categories": ["Duplicate", "Quantity or price above PO"],
 "items": [{"invoice_id", "run_id", "decision_id", "outcome", "outcome_label", "vendor_id", "vendor_name", "vendor_short",
            "invoice_no", "po_id", "gross_paise", "exposure_paise", "assigned_to", "category", "reason", "headline",
            "recommended_action", "age_days", "age_badge": "amber|red|null", "sla_due_at", "sla_breached", "info_requested_at",
            "made_by", "actor_name", "reason_code", "decided_at", "is_synthetic", "driving_rule_ids"}]}
```
Categories: Quantity or price above PO, Duplicate, Bank change, Missing information, Vendor problem, Tax or total, PO problem, Date problem, High value, Currency, Needs AI extraction. Resolved = decided by a person in the last 30 days.

### `POST /api/invoices/{id}/info-requested` -> `{"info_requested_at"}`
### `POST /api/invoices/{id}/documents` multipart `file` (+ `pace`) -> `201 {"run_id", ...}`: replaces the invoice's document and re-runs from stage 1.

## S6 Master data

### Vendors
- `GET /api/vendors?q=&status=` -> `{"items": [{"id", "name", "short", "aliases", "gstin", "status": "approved|pending|blocked", "payment_terms_days", "bank_name", "bank_ifsc", "bank_account_masked", "bank_changed_at", "bank_verified_by", "contact_phone", "contact_email", "address"}]}`
- `GET /api/vendors/{id}` adds `bank_account_no`, `purchase_orders[]` (PO summaries) and `recent_invoices[]`.
- `POST /api/vendors` `{"name", "gstin", "status", "payment_terms_days", "aliases": [], ...}` -> 201 vendor.
- `PATCH /api/vendors/{id}` any of `name, short, aliases, gstin, status, payment_terms_days, contact_phone, contact_email, address` (bank fields are refused here).
- `POST /api/vendors/{id}/bank` (**manager**) `{"bank_name", "bank_account_no", "bank_ifsc", "reason" (10+ chars), "verified_by"}`. This is how an EC4 hold is cleared: change the master, then re-run the invoice; R05 then passes ("matches the vendor record, which ... verified").

### Purchase orders
- `GET /api/pos?status=open|partially_billed|fully_billed|closed|cancelled&vendor_id=&q=` -> `{"items": [{"id", "vendor_id", "vendor_name", "vendor_short", "issue_date", "valid_to", "status", "currency", "subtotal_paise", "tax_paise", "total_paise", "billed_subtotal_paise", "pending_subtotal_paise", "remaining_subtotal_paise", "pct_billed", "invoice_count", "is_seed"}]}`. Status is derived from billing unless closed or cancelled.
- `GET /api/pos/{id}` adds `lines[{id, line_no, item_code, description, uom, ordered_qty, unit_price_paise, tax_rate_pct, billed_qty, pending_qty, remaining_qty, opening_billed_qty, line_value_paise, billed_value_paise}]`, `billing_history[]` (every invoice with outcome), `locked`, `locked_fields`.
- `POST /api/pos` `{"id": "PO-2026-1010", "vendor_id", "issue_date", "valid_to", "currency": "INR", "lines": [{"item_code", "description", "uom", "ordered_qty", "unit_price": "14500" | "unit_price_paise": 1450000, "tax_rate_pct": 18}]}`
- `PATCH /api/pos/{id}` header fields and `lines: [{"id", ...}]`. Vendor and item codes are locked once the PO has invoices (422 with explanation).
- `POST /api/pos/{id}/lines`, `POST /api/pos/{id}/close|cancel|reopen` `{"reason"?}`.

Billed quantities count invoices whose current decision is approved; Review and Hold invoices are shown separately as `pending`; rejected invoices are ignored. Seeded legacy POs carry an `opening_billed_qty`.

### CSV
- `POST /api/import/vendors|pos?commit=false` multipart `file` -> `{"kind", "rows", "valid", "problems": [{"row": 2, "errors": {"ordered_qty": "..."}}], "preview": [...], "committed": false}`. With `commit=true` it writes only if every row is valid (otherwise 422, nothing committed).
- Vendor columns: `id,name,gstin,status,payment_terms_days,bank_name,bank_account_no,bank_ifsc,contact_phone,contact_email,aliases,address` (aliases separated by `|`).
- PO columns (one row per line): `po_number,vendor_id,issue_date,valid_to,currency,item_code,description,uom,ordered_qty,unit_price,tax_rate_pct`.
- `GET /api/export/vendors.csv`, `GET /api/export/pos.csv`.

## S7 Rules and tolerances

### `GET /api/settings`
```json
{"version": 14, "config": {"rules": {"R02": {"ok": 0.9, "min": 0.75}, "R03": {"days": 180}, "R06": {"review": 0.6, "reject": 0.85},
   "R07": {"score": 0.9, "gap": 0.2, "ceil": 100000}, "R09": {"pct": 10},
   "R10": {"pass_pct": 0.5, "pass_abs": 50, "note_pct": 2, "note_abs": 5000, "review_pct": 10},
   "R11": {"pass_pct": 0.5, "pass_abs": 0, "note_pct": 2, "note_abs": 0, "review_pct": 10},
   "R12": {"pass_pct": 0.5, "pass_abs": 50, "note_pct": 2, "note_abs": 5000, "review_pct": 10},
   "R13": {"pass": 1, "note": 10, "review": 100}, "R14": {"pass": 1, "note": 10}, "R15": {"cap": 1000000}},
  "enabled": {"R01": true, "...": true},
  "global": {"cap": 1000000, "split": 10000, "sample": 10, "sla": 3, "auto": true, "baseline": 9, "dateOrder": "Day first", "currency": "₹"},
  "advanced": {"boost_to": 0.92, "ambiguous_date_cap": 0.8, "disagree_cap": 0.6, "fuzzy_vendor": 0.85, "dup_weights": {}, "implied_weights": {}, "implied_review_floor": 0.5, "line_fuzzy": 0.8}},
 "defaults": {}, "global": {}, "advanced": {},
 "rules": [{"id": "R10", "name": "Unit price vs PO", "stage": 7, "group": "Numbers", "hard": false, "band": true, "enabled": true,
            "can_disable": true, "params": {}, "param_labels": {"note_pct": "Note up to (%)"}, "default_params": {}, "is_default": true,
            "sentence": "Allow a unit price up to 2% above the PO, and no more than ₹5,000, with a note. ...", "allowed": "..."}],
 "history": [{"version": 14, "changed_by": "Rahul Mehta", "reason": "...", "summary": "R10 Unit price: note band 1.5% to 2.0%", "changes": [], "changed_at": "..."}]}
```
Amounts in `rules`/`global` are rupees; percentages are percent numbers (`2` = 2%); confidences and scores are 0-1. `abs` caps of 0 mean "not used" (R11).

### `PUT /api/settings` `{"config": {"rules": {"R10": {"note_pct": 1}}}, "reason": "Aligned with contract terms"}`
A partial patch merged onto the current version. Requires a reason of 10+ characters. Validation (422 `fields`): numbers >= 0; pass <= note <= review for the bands; R02 min < ok; R06 review < reject; R13 steps increase; hard-stop rules R04-R06 cannot be disabled. Success: `{"version": 15, "changes": [{"key": "rules.R10.note_pct", "before": 2, "after": 1}], "message": "Settings saved. ...", ...settings}`. Each run records the `config_version` it used; existing decisions do not change unless re-run.

### `POST /api/settings/preview` `{"config": {...patch}, "days": 90}`
`{"valid", "errors", "days", "checked_runs", "would_change", "changes": {"approve_with_note->route_for_review": 1}, "invoices": [{"invoice_id", "invoice_no", "from", "to"}], "sentences": {"R10": "..."}, "note"}`. Re-checks stored rule facts of real (non-synthetic) runs.
### `POST /api/settings/revert` `{"to": "defaults" | "previous" | <version>, "reason"}` -> new version.
### `GET /api/settings/history`.

## S8 Audit log

### `GET /api/audit`
Query: `from`, `to` (ISO date or timestamp), `actor_type=system|ai|human`, `user`, `event_type` (comma list), `object_id` (invoice, run, PO, vendor or setting id), `invoice_id`, `q` (text), `page`, `page_size` (default 100).
```json
{"total": 168, "page": 1, "page_size": 100, "notice": "Entries cannot be edited or deleted.",
 "event_types": ["decision_made", "decision_overridden", "..."], "users": ["Rahul Mehta"],
 "items": [{"id": 412, "ts": "...", "actor_type": "human", "actor_id": "Rahul Mehta", "event_type": "decision_overridden",
            "object_type": "invoice", "object_id": "INV-...", "run_id": "run_...", "invoice_id": "INV-...", "outcome": "hold_request_info",
            "summary": "Hold: request info K/1241 (was Route for review): Credit note requested",
            "payload": {"before": "route_for_review", "after": "hold_request_info", "reason_code": "...", "reason_text": "..."}}]}
```
Event types: `run_created`, `stage_completed`, `rule_evaluated` (non-pass rules, with facts and config version), `decision_made`, `decision_overridden`, `decision_confirmed`, `field_corrected`, `master_data_changed` (before/after), `settings_changed` (version, reason, changes), `export`, `info_requested`, `document_received`, `payment_recorded`, `run_failed`, `run_cancelled`, `demo_reset`. AI events (`actor_type: ai`) carry the model and prompt version. The table is append-only: SQLite triggers reject UPDATE and DELETE.
### `GET /api/audit/export?format=csv|json` with the same filters.

## Demo
- `POST /api/demo/reset` -> `{"runs": 60, "named_history": [{"invoice_id", "run_id", "outcome"}], "synthetic": 57, "open_exceptions": 14}`. Wipes everything (including the audit log) and reloads master data, rule history and history.
- `POST /api/demo/seed` seeds only if the database is empty.
- The server auto-seeds an empty database at startup (`LEDGERLIGHT_AUTOSEED=0` to disable).
