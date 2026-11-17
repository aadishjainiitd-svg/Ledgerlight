# Handoff: what is left before submission

**Goal:** Ledgerlight is the PS-1 take-home (invoice PDF → explained AP decision). The submission needs a
**live runnable link** and a **5-minute demo video**, sent to the hiring coordinator.

**State (17 Nov 2026)**
- Repo: this folder, branch `main`, 4 commits, latest `b20fa86`. **No remote yet.**
- Checks: backend `backend\.venv\Scripts\python -m pytest -q` → 205 passed, 1 skipped (~2.5 min); frontend
  `cd frontend; npm run check` → 51/51; adversarial text cases
  `backend\.venv\Scripts\python docs\review\adversarial\run.py --data-dir <tmp> --no-scans` → 49/49 OK
  (it rewrites `results.json`; keep the original, which holds the 51-case review record).
- All 23 findings in `docs/review/LOOPHOLES.md` are fixed, each with a regression test in
  `backend/tests/test_review_fixes.py`.
- Groq key is in the git-ignored `backend/.env`. Never print or commit it. Rotate it after submission
  (it was pasted in a chat).

**Left, in order**
1. **Deploy a live link.** One shared SQLite database is risky for a public link: running a sample twice is
   correctly rejected as a duplicate, and demo reset is open to anyone. Give each visitor their own sandbox, or
   at least reset automatically every hour, and lock down reset (OFFICE_HOURS.md L1). Set the Groq key as a
   host environment variable, then pre-warm SI-05 so the AI result is cached (the cache now survives reset).
2. **Push to GitHub**, which hosting needs anyway.
3. **Run the two scan attack cases** (S01 prompt injection on a scan, S02 re-scanned duplicate) with the key.
   They were last tested before the fixes (S02 was never tested, because of Groq rate limits).
4. **Update the docs to match the build:** README and PRODUCT_SPEC (document-type holds, "Mark reviewed",
   Groq auto mode, the new checks), plus an assumptions list to refer to in the interview. Include the spec
   differences: SI-05 match 1.00/0.10; SI-06 account ending 3347; SI-05 now approved with a note for the
   inferred PO only.
5. **Re-read OFFICE_HOURS.md.** L2, L3, L5 and the pipeline holes are fixed. The other product points (for
   example L4: most samples never reach the AI, and EC2's "scan" has a generated OCR layer) are about the demo
   story. Decide how to present or address them.
6. **Record the 5-minute video** (script in PRODUCT_SPEC.md §10), then email both links to the coordinator.

**Known, not built:** bulk assign on S5, undo, PDF field highlighting, an embedded PDF viewer.
**Watch:** one full test run stalled for over 6 minutes once and never again; the suite slowed from ~1 to
~2.5 minutes after the latest rules.
