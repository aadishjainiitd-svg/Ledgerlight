# Ledgerlight

AI invoice processing for Accounts Payable. A vendor invoice PDF goes in, runs through a nine-stage pipeline and
sixteen deterministic rules, and comes out as one of five decisions with a plain-English explanation. Every stage
streams live to the UI. **The AI reads, rules decide, everyone can see why.**

All vendors, GSTINs, bank accounts and people in the data are fictional. "Today" in the demo data is 16 Nov 2026.

## Layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI app (`app/`), tests (`tests/`), HTTP check script (`scripts/check_sse.py`), `API.md` |
| `samples/` | Seven sample invoices SI-01..SI-07, `history/` PDFs, `expected.json`, `seed_data.json`, generator `make_samples.py` |
| `frontend/` | Next.js 15 + Tailwind UI (screens S1 to S8, light theme only), Playwright check in `e2e/` |
| `start.ps1` | One command that starts the backend and the frontend together |

## Backend: setup and run (Windows, Python 3.11)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

macOS/Linux: use `.venv/bin/python` instead of `.venv\Scripts\python`.

- API: http://127.0.0.1:8010/api/health, interactive docs at http://127.0.0.1:8010/docs, full reference in `backend/API.md`.
- On first start the server creates `backend/data/ledgerlight.db` (SQLite, WAL) and seeds the demo data: 6 vendors,
  14 POs (the 8 demo POs plus 6 older ones for history), rule-set history, and **60 runs**
  (3 named history invoices run through the real pipeline from their PDFs, plus 57 synthetic history rows):
  32 Approved, 10 Approved with note, 9 Needs review, 5 On hold, 4 Rejected = 70% straight through, 14 open exceptions.
- Reset any time: `POST /api/demo/reset`. Running the same sample file twice is (correctly) rejected as an exact
  duplicate, so reset between demo takes.

### Optional: AI extraction (Groq or Claude)

Put one key in `backend/.env` (git-ignored; copy `backend/.env.example`), or set it in the shell, which wins:

```powershell
# backend/.env
GROQ_API_KEY=<your key>          # Groq, model qwen/qwen3.8-27b (vision)
# ANTHROPIC_API_KEY=<your key>   # Claude, model claude-sonnet-5-5 (used instead of Groq when both are set)
```

The app never logs or stores keys. Which invoices the AI reads is set by `LEDGERLIGHT_EXTRACTION`:

| | `auto` (default) | `llm` | No key |
|---|---|---|---|
| Text PDFs (SI-01, 02, 03, 06, 07) | Deterministic text-layer parser | AI reads the PDF (text layer passed as a hint) | Parser |
| Scan with OCR layer (SI-04) | Parser reads the OCR layer | AI reads the image (two passes) | Parser |
| Image-only scan (SI-05) | AI reads the image twice (self-consistency) | Same | **Hold**: "scanned invoice needs AI extraction" |
| Explanation wording | AI may polish the template; any new number or ID is rejected | Same | Template text |

`auto` keeps the tested parser where the PDF already has reliable text and uses AI only where there is nothing
else to read. Groq notes: page images are sent (Groq takes images, not PDFs, at most 5 pages); the free tier
allows about 7,000 input tokens per minute and one scan uses about 6,000 over two passes, so back-to-back scan
runs may pause while the client waits out the rate limit (it honours `retry-after`). The wording polish never
waits; it falls back to the template.

On a scan, an exact vendor-name match whose GSTIN differs from the master in one OCR-confusable character
(0/G, 0/O, 1/I, 5/S, 8/B, 2/Z) is treated as a misread and gives a note (R04), not a review. Any other GSTIN
difference still goes to review.

The model is only used to read the invoice and to word the explanation. Every decision is made by the rules.
Results are cached per (file hash, prompt version, model) so repeated demo runs are identical. Other settings:
`LEDGERLIGHT_MODEL`, `LEDGERLIGHT_PACE` (`instant|fast|normal|slow` or ms, default `normal` = 550 ms minimum dwell
per stage, labelled "display pacing" in the log), `LEDGERLIGHT_AS_OF` (default `2026-11-16`), `LEDGERLIGHT_DB`,
`LEDGERLIGHT_DATA_DIR`, `LEDGERLIGHT_CORS_ORIGINS`, `LEDGERLIGHT_AUTOSEED`.

### Tests and checks

```powershell
cd backend
.venv\Scripts\python -m pytest -q                 # golden samples, R01-R16 pass/fail, seed, API, SSE
.venv\Scripts\python scripts\check_sse.py         # with the server running: upload SI-01 over HTTP, print the SSE sequence
```

The main suite is offline: it ignores `backend/.env` and removes AI keys, so the SI-05 golden test is skipped
there; `test_scan_without_key_is_held` checks the Hold, and `test_llm_path.py` drives the real extraction code for
SI-05 with a simulated model response plus the Groq request format (no network). `tests/test_live_ai.py` runs SI-05
against the real API for each provider whose key is set (shell or `backend/.env`) and skips the rest:

```powershell
.venv\Scripts\python -m pytest -q tests\test_live_ai.py -rs   # about a minute on Groq's free tier
```

### Regenerating the sample PDFs

```powershell
backend\.venv\Scripts\python samples\make_samples.py
```

## The seven samples

| ID | File | What it shows | Expected decision |
|---|---|---|---|
| SI-01 | `SI-01_brightline_BL-2026-0412.pdf` | Happy path, classic grid layout | Auto-approve |
| SI-02 | `SI-02_corevolt_CV-8841.pdf` | Compact layout, one bundled line, tax-inclusive, PO "1002/2026" in the narrative | Approve with note (+1.5%) |
| SI-03 | `SI-03_kestrel_K-1241.pdf` | EC1: third invoice on a split PO overbills by 500 cartons | Route for review (manager, ₹23,600) |
| SI-04 | `SI-04_brightline_rescan_BL-0377-26.pdf` | EC2: skewed phone photo of an already-paid invoice, number written differently | Reject (duplicate, ₹1,18,000) |
| SI-05 | `SI-05_greenleaf_GL-2291_scan.pdf` | EC3: image-only degraded scan, stamp over the PO field, smudged total, date 12/11/26 | Approve with note (PO inferred); Hold without a key |
| SI-06 | `SI-06_corevolt_CV-8902_bank-change.pdf` | EC4: perfect invoice with new bank details in the footer | Hold: request info (₹1,66,380) |
| SI-07 | `SI-07_meridian_MX-5530_tax-error.pdf` | GST digit slip (₹21,320 instead of ₹31,320) | Reject |

## Frontend

Next.js 15 (App Router) with Tailwind, ported from the approved clickable mock. **Light theme only**: there is no
theme toggle and no dark CSS. Every number on screen comes from the backend API; the live run view (S3) is driven by
the real Server-Sent Events stream (`GET /api/runs/{id}/events`), including reconnect with `Last-Event-ID`
and replay of finished runs.

| Screen | Route |
|---|---|
| S1 Dashboard | `/` |
| S2 New run (upload or sample) | `/new` |
| S3 Live run | `/runs/{run_id}` |
| S4 Invoice decision | `/decision/{run_id}` |
| S5 Review queue | `/queue` |
| S6 Purchase orders and vendors | `/master` |
| S7 Rules and tolerances | `/rules` |
| S8 Audit log | `/audit` (`?invoice=INV-...` for one invoice trace) |

### One-command start (Windows PowerShell)

```powershell
.\start.ps1
```

This starts the backend on `http://127.0.0.1:8010` (reuses it if already running), picks the first free frontend port
from 3000 upward (3000 when free), builds the frontend on the first run (about a minute), waits until both answer,
and opens the browser. Press Ctrl+C to stop both. Logs are in `frontend\.logs\`.

Options: `-NoBrowser`, `-Dev` (Next.js dev server), `-Rebuild`, `-BackendPort 8010`, `-FrontendPort 3000`.
From the `frontend` folder, `npm run demo` does the same.

### Manual start

```powershell
# terminal 1: backend (see above)
cd backend; .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

# terminal 2: frontend
cd frontend
npm install
npm run build
npm start            # http://localhost:3000   (npm run dev for development)
```

The browser calls the backend directly (CORS is open). The API base URL is `NEXT_PUBLIC_API_BASE` in
`frontend/.env.local` (default `http://127.0.0.1:8010`); it is read at build time, so rebuild after changing it.

### End-to-end check

With both servers running:

```powershell
cd frontend
npx playwright install chromium      # once
npm run check                        # FRONTEND_URL / API_URL override the defaults
```

`e2e/check.js` resets the demo data, runs all seven samples from S2 through the live S3 view to the S4 decision and
compares each label with `samples/expected.json` (SI-05 is Hold when no `ANTHROPIC_API_KEY` is set), does one
override and finds it in S8, visits every screen counting console errors, asserts no dark-theme CSS is shipped, drops
the live stream mid-run to prove reconnect loses nothing, and saves a screenshot per screen to `e2e/screenshots/`.
