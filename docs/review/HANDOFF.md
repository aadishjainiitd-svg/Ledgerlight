# Handoff: fix the review findings before submission

**Goal:** Ledgerlight is the PS-1 take-home (invoice PDF → explained AP decision). Fix what the review found,
then deploy a live link and record the 5-minute video. Submission needs: a live runnable link + a demo video.

**State (2026-11-16)**
- Repo: this folder, branch `main`, 2 commits (`2ef4697` initial, `2231711` Groq extraction). No remote yet.
- Backend tests: 175+ pass offline (`backend\.venv\Scripts\python -m pytest -q`); live Groq test:
  `tests\test_live_ai.py`. Frontend e2e: `cd frontend; npm run check` (51/51).
- Groq key is in the git-ignored `backend/.env`. Never print or commit it; rotate it after submission.
- Review reports (read these first):
  - `docs/review/LOOPHOLES.md`: 23 pipeline findings (6 critical) with repro, root cause (file:line), fix.
    Re-run: `backend\.venv\Scripts\python docs\review\adversarial\run.py --data-dir <tmp> [--no-scans] [--only A01]`
    (uses port 8050 and its own data dir; note it rewrites `results.json` and regenerates `pdfs/`).
  - `docs/review/OFFICE_HOURS.md`: product critique, 13 loopholes, interviewer Q&A, do-before-submission list.

**Verified fix order (independent verifier, merged across both reports)**
1. Bank check R05: only the first account on the page is checked and invisible text counts (C2); a
   hyphenated new account with no IFSC reads as "no bank details" and passes (C3).
2. Document type and same-batch duplicates: credit notes and proformas are auto-approved, and the real
   invoice is then rejected as a duplicate (C5); two uploads of one invoice in a batch both get approved (C4).
3. Line checks: a line with no quantity skips R10 ("₹0.00 matches") (C6); a charge with no PO line is
   auto-paid (C1). It should go to Hold or Review, not Reject; the PDF's own rows do add up.
4. Live link with per-visitor data (one shared DB + duplicate rejects + open reset would break a public
   link), and make "Accept recommendation" really resolve the item, or rename it (OH L1, L2).
5. Scan reliability: keep `extraction_cache` across demo reset and pre-warm SI-05. Groq free tier returned
   429 "OTPM limit 1000" on some scans, so consider a lower `max_tokens` (GROQ_MAX_TOKENS is 8000) or a paid
   key. Remove the false "confirmed against the page image" wording; the text parser reports a fixed 0.98 (OH L5, L3).

**Done when:** each fixed finding has a regression test; `run.py --no-scans` shows those cases as OK;
pytest and `npm run check` stay green.
