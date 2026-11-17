# Ledgerlight: Office Hours Review

Reviewer posture: a demanding Zamp hiring panel for the AI Solutions Analyst role, using the gstack `/office-hours` method.
Date: 16 Nov 2026. Scope: the whole product as built in `C:\Users\ASUS\Desktop\Ledgerlight`, judged against
`ASA Case Study - Candidate Guide.pdf` (PS-1).

## 0. How this review was run

- **Mode:** Startup mode (intrapreneurship variant). A take-home pitched to a "non-technical buyer" is a sale, so the
  hard questions apply. Q4 becomes "the smallest demo that gets the panel to say yes" and Q6 becomes "does the
  product thesis still hold in 3 years".
- **Non-interactive.** The skill normally asks the founder six forcing questions one at a time. Here the reviewer
  answered them as the candidate, from the guide, `PRODUCT_SPEC.md` and the build, then pushed back on each answer.
- **Evidence kinds used.** Static reads of code and docs (file:line), the e2e screenshots in
  `frontend/e2e/screenshots/`, `frontend/e2e/results.json`, and one live test run:
  `backend\.venv\Scripts\python -m pytest -q` gave **176 passed, 2 skipped in 74 s** (the brief said 175; 176 is
  what ran today). No server was started, nothing was deployed, no LLM was called by the reviewer.
- **Skipped skill steps** (to stay inside the "write one file" boundary): web landscape search, Codex second
  opinion, the `~/.gstack` design-doc copy, builder-profile logging, gstack upgrade prompt.

---

## 1. Verdict

**Not submittable today, and a strong contender within two focused days.** The thinking is top-decile for a
take-home: a written process map, sixteen named rules with a reason for every threshold (`PRODUCT_SPEC.md` 3.5), four
edge cases that each fool a naive checker (EC1 cumulative overbilling, EC2 re-keyed duplicate, EC3 inferred PO on a
scan, EC4 bank-change fraud), a clean "AI reads, rules decide" thesis, a polished live run view and dashboard, and
real test depth (176 backend tests, 51/51 e2e checks). But the guide's first requirement is a "live and runnable"
link, and there is none. The current single shared database would also break on the second visitor: running a sample
twice is rejected as a duplicate (`README.md:34-35`). Then a sharp interviewer finds three credibility cracks in under
ten minutes: (1) the text-PDF parser reports a hard-coded 0.96 confidence while the UI says the values were "confirmed
against the page image"; (2) the review queue's main "Accept recommendation" button changes nothing about the
invoice; (3) the EC3 showcase leads with a GSTIN-forgiveness rule that looks fitted to the demo. None of these is deep.
All of them cost trust, and trust is what this product sells. Fix the link, the three cracks and the EC3 live
reliability, and this beats most submissions on "judgment behind design choices".

---

## 2. Scorecard against the guide's grading criteria

The guide grades "whether your process actually works, the judgment behind your design choices, and how you explain
it to a non-technical buyer", plus explicit deliverable requirements. Scores are out of 10 for the current state.

| # | Criterion (from the guide) | Score | Evidence | What moves it to 9+ |
|---|---|---|---|---|
| 1 | **Deliverable 1: live and runnable link** ("a link to your process (live and runnable)") | **2** | Local only. No Dockerfile, Procfile or host config in the repo root or `backend/`. API base is baked at build time to `http://127.0.0.1:8010` (`README.md:151-152`). Shared state makes a public link fragile: a second run of any sample is an exact-duplicate Reject (`README.md:34-35`), and reset is an open endpoint (`backend/app/main.py:142-147`) | Deploy with a per-visitor sandbox (loophole L1) |
| 2 | **It actually works on real inputs** ("accept real inputs ... run through your logic ... real output") | **7** | 176 backend tests pass (run today); e2e `results.json` has 51 PASS, 0 FAIL, and all seven samples hit their expected label, SI-05 included ("Approved, note"). But 6 of 7 samples never reach the LLM in `auto` mode (`backend/app/pipeline.py:277-278`, `backend/app/config.py:84-85`), and the parser is regex-based on the candidate's own layouts (`backend/app/extract_text.py:74-163`). Untested against an invoice the panel brings | Run 5 unseen invoices; add an LLM fallback when the parser fails to reconcile (L4) |
| 3 | **Edge cases: 2-4, non-trivial, handled deliberately** | **9** | Four cases, each with different reasoning and a different decision (`PRODUCT_SPEC.md:400-410`). EC1 compares against what remains on the PO, not the PO (S3.png: "76% billed before this invoice", decision "Needs review", exposure ₹23,600). EC4 is a HOLD, not a REVIEW, which is the right call. Weak point: EC2's "phone photo" carries an OCR layer the candidate's generator wrote (`samples/make_samples.py:628-666`), and EC3's headline is about a GSTIN, not the inferred PO (S4-SI-05.png) | Fix L4 and L6 so the edge cases prove what they claim |
| 4 | **UI: live run view showing each stage** | **9** | S3.png: nine stage cards with durations and one-line results, fields with confidence chips, streaming log, decision reveal, replay, pacing disclosed ("Pacing 550 ms per stage"). SSE with reconnect is tested by e2e | Make the "Extracted fields" source line truthful (L3) |
| 5 | **UI: dashboard of history, status and outputs** | **8** | S1.png: needs-attention banner, six KPI tiles, four charts, status chips, runs table with plain-English "main reason". CSV export button present. Loses points because 57 of the runs are synthetic and nothing on screen says so (L8) | Label seeded rows; let the buyer exclude them |
| 6 | **Judgment behind design choices** | **8** | Rules decide money, the LLM only reads and polishes, and the polish is fact-checked (`backend/app/explain.py:289-310`). Severity order with reasons (`PRODUCT_SPEC.md:293`). Reasons per threshold (`PRODUCT_SPEC.md:345-360`). Pacing labelled as theatre. Undercut by demo-fitted patches (L6), fake confidence (L3) and a self-ticked four-eyes control (L10) | Close L3, L6 and L10, then say why in the demo |
| 7 | **Explaining it to a non-technical buyer** | **7** | Four-block explanation with numbers and a next step (S4.png SI-02: "the vendor billed 1.5% more than the PO, which is within the allowed difference"). But buyer-facing text leaks env-var names: the decision headline says "set ANTHROPIC_API_KEY or GROQ_API_KEY" (`backend/app/rules.py:80-85`, S3-SI-05-needs-ai.png), and the EC3 headline talks about "character 7 ('0' vs 'G')" of a tax ID (S1.png row run_23613a) | Rewrite those two strings; lead EC3 with the PO story |
| 8 | **Deliverable 2: 5-minute video** | **n/a** | Script exists (`PRODUCT_SPEC.md` section 10). No recording found in the repo. The script narrates "Use saved AI results" as the safety net, but demo reset wipes that cache (L5) | Record on the deployed URL after a reset, cold cache tested |
| 9 | **Live interview demo with no slides** ("one that breaks live ... is hard to recover from") | **5** | EC3 took 66 s in the run on S1.png (row run_23613a, "66 s"). Groq free tier is about 7k tokens a minute and one scan uses about 6k (`README.md:57-60`). The spec's live extension promises "upload any PDF from the audience" (`PRODUCT_SPEC.md:1120`), which is exactly where the parser is weakest | Preserve the cache across reset; rehearse BYO-invoice |

**Weighted read:** 7 of 9 rows are strong. The two weak rows (link, live-demo risk) are the ones that decide
whether the panel ever sees the strong rows.

---

## 3. The forcing questions (answered as the candidate, then pushed)

**Q1. Demand reality: who would be upset if this disappeared tomorrow?**
*Candidate:* "Zamp. PS-1 'reflects work Zamp actually does', and Meera the Finance Controller loses duplicate and
fraud protection."
*Push:* That is a proxy, not demand. Nobody, including a fictional Priya, has used it. The honest version: "My demand
evidence is the brief itself. My user evidence is zero." That is fine for a take-home, but then the product must
never claim things it has not measured. Today it does: the 0.96 parser confidence (L3) and the "smudged character"
headline (L6) are claims without evidence. **Position:** the demand framing is acceptable; the measurement honesty
is not yet.

**Q2. Status quo: what does the AP team do today and what does it cost?**
*Candidate:* "Open the PDF, find the PO in a spreadsheet, check by calculator. 8 to 12 minutes per invoice
(`PRODUCT_SPEC.md:61`, flagged as an assumption at line 66)."
*Push:* The real status quo for a mid-size company is often an ERP with a two-way match module plus an OCR add-on. A
panel member will ask "my ERP already matches invoice to PO, what do you add?". The strong answer exists in the build
and should be the first sentence of the demo: cumulative position across split invoices (EC1), fuzzy duplicate
identity (EC2), and bank-change fraud control (EC4) are where ERP matching is weakest.

**Q3. Desperate specificity: name the human.**
*Candidate:* "Rahul Mehta, AP Manager. He answers to the Controller and the auditors (`PRODUCT_SPEC.md:81-89`)."
*Push:* Good, and the career consequence should be said aloud: Rahul gets fired for a ₹1.66 lakh payment to a
fraudster's account (EC4) or a duplicate payment (EC2), not for slow invoices. That reframes the pitch from
"time saved" to "losses prevented", which is also the KPI the build already shows ("Value protected ₹4,34,472",
S1.png). Lead with it.

**Q4 (intrapreneurship). The smallest demo that gets the panel to say yes.**
*Candidate:* "The five-minute script with four edge cases."
*Push:* Smaller. One URL that works for every panel member independently, one sample that runs live with every stage
visible, and one invoice the panel brings that does not produce a lie. If those three work, the rest is upside. If
any of them fails, the rest is never seen. Today none of the three is guaranteed (L1, L4, L5).

**Q5. Observation and surprise: have you watched anyone use it without helping?**
*Candidate:* "The Playwright run drives every screen."
*Push:* A script is not a user. Reading the screenshots cold surfaced exactly the kind of surprise a user test would:
the EC3 invoice, the one meant to show PO inference, is headlined by a GSTIN character note (S4-SI-05.png), and the
queue's "Accept recommendation" leaves the item in the queue (L2). Neither was caught because nobody non-technical
has clicked through it.

**Q6 (intrapreneurship). Does the thesis hold in 3 years?**
*Candidate:* "Models get better, extraction gets better."
*Push:* That is the rising-tide answer every competitor gives. The better thesis is already in the spec: extraction
becomes a commodity, so the durable value is the deterministic control layer, the exception workflow and the audit
trail. That makes "AI reads, rules decide" more valuable over time, not less. Say it that way.

---

## 4. Premises (accepted on the candidate's behalf)

1. The grade is decided by the link and the live demo, not by the spec. A perfect spec behind a dead link scores low.
2. One false claim on screen costs more than one missing screen. Fix honesty gaps before adding features.
3. "The AI reads, rules decide, everyone can see why" is the right thesis. Keep it and make every screen consistent with it.
4. The panel will try their own invoice. Plan for it instead of hoping they do not.

---

## 5. Loopholes, ranked

13 loopholes. Severity: blocker (cannot submit or the demo collapses), high (a sharp interviewer finds it and it costs
the round's credibility), medium (costs points, has a good answer), low (polish). Effort is given as
(human team / Claude Code).

### L1. No live link, and the shared-state design would break the moment there is one (blocker)
- **Why an interviewer catches it:** The guide's submission is "a link to your process (live and runnable)". Each
  panel member clicks the link separately. The second person to run SI-01 gets "Rejected: exact copy of a file we
  already processed", because running a sample twice is an exact duplicate (`README.md:34-35`). Anyone can press
  reset for everyone (`backend/app/main.py:142-147`), and roles come from a client-sent header with no auth
  (`backend/app/admin.py:30-34`), so on a public URL anyone can act as manager, change bank details or wipe data.
- **Evidence:** no Dockerfile, Procfile or host config in the repo root or `backend/` (directory listing);
  `NEXT_PUBLIC_API_BASE` defaults to `http://127.0.0.1:8010` and is fixed at build time (`README.md:151-152`); spec
  planned a public deploy on day 3 (`PRODUCT_SPEC.md:915`, 8.6 row 3).
- **Fix:** Deploy backend and frontend (one container, or Render/Railway backend plus Vercel frontend) with a
  per-visitor sandbox: a cookie-scoped sandbox id that clones a seeded SQLite file on first visit, with all API
  calls and SSE scoped to it, and reset scoped to it. Add an upload cap and a per-sandbox LLM call budget so the key
  cannot be drained. Minimum fallback if time runs out: one shared instance, hourly auto-reset, and a "Reset demo"
  button on S2 with a line saying the data is shared.
- **Effort:** sandbox version (human: 1.5 days / CC: 3 h); minimum fallback (human: 0.5 day / CC: 1 h).

### L2. "Accept recommendation" does nothing to the invoice, and the recommended action cannot be executed (high)
- **Why an interviewer catches it:** It is the primary button on S5. The card says "Recommended: Approve 27 trips,
  request credit note ₹51,330" (S5.png). The interviewer clicks it, the toast says "confirmed", and the invoice is
  still in "Needs review", neither paid nor partly paid, with no credit note.
- **Evidence:** the button calls `/accept` (`frontend/components/Queue.jsx:26,52`); `accept` only stamps
  `confirmed_by` on the existing system decision (`backend/app/admin.py:102-114`); the queue moves an item to
  Resolved only when `made_by == "user"` (`backend/app/repo.py:336-339`), which `accept` never sets. Partial approval
  is listed as P2, not built (`PRODUCT_SPEC.md:540`), yet the EC1 explanation recommends it
  (`PRODUCT_SPEC.md:428`). `accept` also has no role check, so a clerk can "accept" a manager-assigned item.
- **Fix:** Either make it real (accept on a review item writes decision v2 `approve_partial` with the payable amount,
  moves the item to Resolved, and copies the drafted credit-note request), or make it honest (rename to "Confirm
  review needed" and make "Approve" and "Send back" the two primary buttons). Add the clerk/manager check either way.
- **Effort:** real partial approval (human: 1 day / CC: 2 h); honest rename plus role check (human: 1 h / CC: 15 min).

### L3. Confidence theatre on text PDFs (high)
- **Why an interviewer catches it:** The product's pitch is "per-field confidence" and "never trust the model's own
  score". The panel asks "how did you get 0.98 for the invoice number on K/1241?" The true answer is that it is a
  constant.
- **Evidence:** the parser sets `hi_conf = 0.88 if low else 0.96` for every field (`backend/app/extract_text.py:435-436`,
  used at 511-522). The S3 header says "Read from the text layer of the PDF and confirmed against the page image"
  (`frontend/components/LiveRun.jsx:261`, visible on S3.png), but no image comparison happens on the parser path
  (`backend/app/pipeline.py:314-318`). The same branch logs "No AI key configured" even when a key is set and `auto`
  mode simply chose the parser (`backend/app/pipeline.py:316`).
- **Fix:** For parser output, show the source as "Exact text from the PDF" and derive confidence from checks that ran
  (label found, value parsed, lines plus tax equal total, value found twice) instead of a constant. Change the S3
  sentence to "Read from the PDF's text layer." Change the log line to "Text PDF: reading the text layer with the
  deterministic parser (AI is used for image-only scans)".
- **Effort:** (human: 3 h / CC: 30 min).

### L4. "Where is the AI?" and "will it read our invoice?" (high)
- **Why an interviewer catches it:** This is an AI Solutions Analyst interview. In the default `auto` mode, six of the
  seven samples are read by a regex parser and only SI-05 reaches a model. The parser is tuned to the three layouts
  the candidate's own generator produces. The spec's live extension invites "upload any PDF from the audience"
  (`PRODUCT_SPEC.md:1120`), which is the parser's weakest case. EC2's "phone photo" is read from an invisible OCR text
  layer that the candidate's generator wrote, so it does not test reading a photo at all.
- **Evidence:** routing `llm = ... (info["text_source"] == "none" or config.llm_reads_text_pdfs())`
  (`backend/app/pipeline.py:277-278`); `llm_reads_text_pdfs()` is true only in `llm` mode
  (`backend/app/config.py:84-85`); the README table confirms text PDFs and SI-04 use the parser in `auto`
  (`README.md:49-56`); SI-04's OCR layer is written with `render_mode=3` (`samples/make_samples.py:628-666`), tag
  "OCR layer" in `samples/expected.json`.
- **Fix:** Keep parser-first (it is a defensible cost and determinism choice) but add an automatic AI fallback when
  the parser's output fails R14 reconciliation, misses a required field or finds no line table. Show "Read by: text
  parser" or "Read by: AI vision" as a chip on S3 and S4. Build a five-invoice "unseen layout" set (real-world
  shaped, different from the generator's templates) and run it before the interview. Say plainly in the demo that
  SI-04 has an OCR layer, or add an SI-04b without one.
- **Effort:** (human: 1 day / CC: 2 h).

### L5. EC3, the AI showcase, is the least reliable thing in the demo, and reset destroys its safety net (high)
- **Why an interviewer catches it:** It is the one live LLM call. On S1.png the EC3 run (run_23613a) took **66 s**
  while every text PDF took about 8 s. The free Groq tier allows about 7k tokens a minute and one scan uses about 6k
  over two passes (`README.md:57-60`). The spec's safety net is "Use saved AI results" with a pre-warmed cache
  (`PRODUCT_SPEC.md:998`, fallback at 1122), but the demo needs a reset between takes, and reset drops every table,
  including `extraction_cache`.
- **Evidence:** `reset_schema` drops all non-sqlite tables (`backend/app/db.py:178-186`), called by `reset_and_seed`
  (`backend/app/seed.py:287-289`); the cache table is `extraction_cache` (`backend/app/extract_llm.py:306,352`).
- **Fix:** Exclude `extraction_cache` from the reset drop list and pre-warm all samples after each deploy. Use a paid
  key (or Claude) for the interview. When waiting on a rate limit, log "Waiting 40 s for the AI provider's rate
  limit" so a pause reads as designed, not broken.
- **Effort:** (human: 1-2 h / CC: 15 min).

### L6. EC3's story is hijacked by a demo-fitted GSTIN-forgiveness rule (high)
- **Why an interviewer catches it:** EC3 exists to show "PO number missing, inferred with confidence". The S4
  headline instead reads "Approved with a note: the vendor is Greenleaf; one smudged character of its GSTIN was
  misread on the scan" (S4-SI-05.png), and the S1 main reason is a five-line paragraph about character 7 ('0' vs
  'G'). The interviewer asks three things. Why does a tax-ID mismatch get auto-approved on a fraud-sensitive vendor
  check? Did you add this rule because the model misread your own sample? Where is the smudge? The spec places the
  smudge over the total, not the GSTIN, and says the GSTIN is legible (`PRODUCT_SPEC.md:1087`, 1096).
- **Evidence:** OCR-confusable pair table and one-char rule (`backend/app/matching.py:27-40`, applied at 62); R04
  NOTE with the "smudged character" headline (`backend/app/rules.py:211-219`); R04 outranks R07 for the headline in
  `LEAD_PRIORITY` (`backend/app/rules.py:796`, used at `backend/app/explain.py:51-60`).
- **Fix:** Replace "confusable pairs" with GSTIN structural validation: positions 3-7 must be letters (PAN format),
  and the 15th character is a checksum. A read value that fails format or checksum, differs from a valid master value
  by one character and comes with an exact name match is provably a misread, so a NOTE is justified. Anything else
  goes to REVIEW. Drop the word "smudged". Put R07 ahead of R04-NOTE in `LEAD_PRIORITY` so EC3 headlines the inferred
  PO. Better still, also tune the extraction prompt so the GSTIN reads correctly and the rule is a safety net, not
  the headline.
- **Effort:** (human: 3 h / CC: 30 min).

### L7. Implied PO reports 100% certainty (medium)
- **Why an interviewer catches it:** "No PO number on the invoice and you are 100% sure?" S4-SI-05.png shows
  "Implied · 100%", every component at 100%, and runner-ups at 10% each, with only the date component scoring. The
  spec designed 0.96 vs 0.14 (`PRODUCT_SPEC.md:463`); the brief lists this as a known deviation. A perfect score
  shows the synthetic data was built to match, not that the scorer is calibrated.
- **Evidence:** S4-SI-05.png, Purchase order match panel; scorer at `backend/app/matching.py:311-362`.
- **Fix:** Never display 100% for an inferred match (cap at 0.99, labelled "inferred"); add a near-miss fixture where
  two POs share an item and the decision must become Review with candidates listed (the spec's own interview
  variation, `PRODUCT_SPEC.md:466`). Have that variation ready to run live.
- **Effort:** (human: 2 h / CC: 30 min).

### L8. Dashboard KPIs are mostly synthetic and not labelled (medium)
- **Why an interviewer catches it:** The buyer persona "will judge the product on the Dashboard" (`PRODUCT_SPEC.md:91`).
  The panel asks "which of these numbers came from your pipeline?" Of 67 runs, 57 are synthetic metadata rows
  (`README.md:31-33`) with invented durations of 9 to 17 s (S1.png), so "Median time to decision 12 s" and much of
  "Value protected ₹4,34,472" come from seeded data.
- **Evidence:** S1.png; no `synthetic` or `is_synthetic` reference anywhere in `frontend/components` (grep returned
  nothing), although the backend has the flag (`backend/app/repo.py:329`).
- **Fix:** A small "Seeded" chip on synthetic rows, a "Seeded history included" note under the KPI strip, and a
  toggle to exclude seeded rows from KPIs. Saying this first in the video turns a gotcha into a judgment point.
- **Effort:** (human: 2 h / CC: 20 min).

### L9. The "append-only" audit log is wiped by one unauthenticated button (medium)
- **Why an interviewer catches it:** S8 says "Entries cannot be edited or deleted. This log is append-only"
  (`frontend/components/Audit.jsx:82`), and SQLite triggers block UPDATE and DELETE (`backend/app/db.py:86-88`). But
  `POST /api/demo/reset` drops the table (`backend/app/db.py:178-186`) with no role check
  (`backend/app/main.py:142-147`). An auditor-minded panel member will ask.
- **Fix:** In a deployed sandbox, reset only that visitor's sandbox (L1). Keep a separate reset ledger that survives
  resets, and change the S8 banner to "Demo resets start a new log; resets are recorded in the reset ledger".
- **Effort:** (human: 1 h / CC: 15 min, after L1).

### L10. Bank-change four-eyes control is a self-ticked checkbox (medium)
- **Why an interviewer catches it:** EC4 is the fraud story. The release checklist includes "second person
  confirmed" (`PRODUCT_SPEC.md:388`), but the same manager ticks it (`backend/app/admin.py:68-74`), and the same
  manager can change the vendor's bank record with a free-text "verified_by" (`backend/app/admin.py:257-263`). One
  compromised manager login defeats the control the demo celebrates.
- **Fix:** Require two distinct users: the person who changes the bank master cannot be the one who releases the
  hold, and the "second person" tick must come from a second user's action. With a role switcher this can be shown
  by switching users.
- **Effort:** (human: 3 h / CC: 30 min).

### L11. Cumulative billing assumes Ledgerlight is the system of record (medium)
- **Why an interviewer catches it:** EC1 works because Ledgerlight remembers K/1187 and K/1203. In a real company,
  some invoices against the same PO were paid before Ledgerlight existed or through another channel. "Where does
  billed-to-date come from on day one?"
- **Evidence:** billed position is derived only from invoices in Ledgerlight's own history
  (`PRODUCT_SPEC.md:253`, data model 789); ERP integration is out of scope (`PRODUCT_SPEC.md:553`).
- **Fix:** Add an "opening billed-to-date" field to the PO import (S6 already has CSV import), and say in the demo:
  "On day one we load billed-to-date from the ERP export; after that Ledgerlight keeps it current."
- **Effort:** (human: 2 h / CC: 20 min).

### L12. The tolerance band auto-pays past the PO limit (low)
- **Why an interviewer catches it:** SI-02 is approved with a note while its cumulative bar shows "102% after this
  invoice" (S4.png). A controller may ask why money above the approved PO goes out with no human touch.
- **Evidence:** NOTE band up to 2% and ₹5,000 (`PRODUCT_SPEC.md:316`); S4.png cumulative bar.
- **Fix:** No code needed. Have the answer ready: the band is a common contractual tolerance, it is capped in rupees,
  10% of noted invoices are sampled, and S7 can set it to zero per policy. Optionally add a per-vendor "no overbilling
  past PO" toggle later.
- **Effort:** (human: 0 / CC: 0) to answer; per-vendor toggle (human: 3 h / CC: 30 min).

### L13. Developer jargon and stale text in buyer-facing places (low)
- **Why an interviewer catches it:** A Hold headline that tells a clerk to "set ANTHROPIC_API_KEY or GROQ_API_KEY"
  is not written for a non-technical buyer, the criterion the panel grades.
- **Evidence:** `backend/app/rules.py:80-85`, `backend/app/pipeline.py:287-291`; the committed screenshot
  `S3-SI-05-needs-ai.png` mentions only ANTHROPIC_API_KEY, and `README.md:165` still says SI-05 is Hold "when no
  `ANTHROPIC_API_KEY` is set" although Groq now works too. Also note: the spec's EC4 text says "account ending 2347",
  but A/c 5020 0091 2334 7 ends in 3347, so the build's "3347" is correct and the spec has the typo.
- **Fix:** Headline: "This scan needs the AI reader, which is switched off on this server." Keep the env-var name in
  the technical drawer and the server log. Refresh the README line and regenerate the screenshot.
- **Effort:** (human: 30 min / CC: 10 min).

---

## 6. Questions the interviewer will most likely ask, with strong answers

1. **"Where exactly is the AI, and why so little of it?"**
   "In two places on purpose: reading the invoice and wording the explanation. Clean PDFs carry exact text, so I read
   that text with a deterministic parser: free, instant, repeatable. Scans have no text, so the vision model reads
   them, twice, and I compare the two reads. If the parser's numbers don't add up, the model reads it instead. The
   model never decides money: sixteen rules do, and every number in the explanation is checked against the rule
   facts before it is shown." (True only after L4 and L3 are fixed.)

2. **"Upload this invoice of ours."**
   "Sure." Then it works, or it ends in a clear Hold that says what could not be read and offers a field correction.
   A Hold with a reason is a correct outcome; a wrong approval is not. Rehearse with five unseen layouts first (L4).

3. **"How do you know your confidence numbers mean anything?"**
   "I don't trust the model's own score. Effective confidence is half the model's score, 30% whether the value was
   found independently, 20% whether its format is valid. Amounts that reconcile get raised and the screen says why."
   Then show the EC3 total "read at 0.78, raised because lines plus tax equal the total". Never let them find the
   0.96 constant first (L3).

4. **"Why is a bank change a Hold and not a Review?"**
   "Because the risk is the whole invoice and the safe action is a phone call, not a judgment about a threshold. A
   Review lets a clerk click approve. A Hold forces the verification steps, and only a manager can release it after
   the vendor master is changed by someone else." (True after L10.)

5. **"Your ERP already does two-way match. What do you add?"**
   "Three things ERPs do badly: memory across split invoices (EC1), duplicate identity when the number is written
   differently (EC2), and fraud signals inside an otherwise perfect invoice (EC4). Plus an explanation a clerk can
   send to the vendor."

6. **"Three-way match? You approved 3,000 cartons nobody confirmed were delivered."**
   "Out of scope by assumption A3: PS-1 describes PO data only. The rule engine takes one more input; a goods-receipt
   check would be R17 with the same variance bands. I would add it first in a pilot."

7. **"Why 2% and ₹5,000? Why not 1%?"**
   "2% is a common contractual tolerance; the rupee cap exists because a percentage alone is scale-blind, since 2% of
   ₹50 lakh is ₹1 lakh. And it is policy, not code." Then change it to 1% live in S7, show the impact preview, re-run
   SI-02 and watch it flip to Needs review.

8. **"What happens when a duplicate is not a duplicate, like monthly rent?"**
   "The recurring-charge guard: if serial numbers differ by the billing cadence and the service period differs, the
   number and date signals don't push toward duplicate. There is a lookalike test for exactly that, and 0.60 to 0.85
   goes to Review, not Reject."

9. **"Where does billed-to-date come from on day one?"**
   "From the ERP's PO export, loaded through the S6 CSV import as an opening balance; after that every decision
   updates it." (Ship L11.)

10. **"What would you build next, and what would you measure in a pilot?"**
    "Partial approval with an auto-drafted credit note, then email ingestion. I'd measure straight-through rate,
    wrongly auto-approved invoices in a 10% sample, override rate per rule, and rupees blocked, weekly, with a target
    of zero misses on duplicates and bank changes."

11. **"Is the dashboard real?"**
    "The last ten rows are real pipeline runs; the 57 older rows are seeded so every filter has data, and they are
    labelled. Toggle them off and the KPIs show only live runs." (Ship L8.)

12. **"What stops a prompt injection inside an invoice?"**
    "The model has no tools and returns JSON only; every value it returns is then checked by deterministic rules. If
    the document contains text addressed to an AI, the log says so (`backend/app/pipeline.py:312-313`)."

---

## 7. Alternatives for the next 48 hours

**APPROACH A: Minimum viable submission**
- Summary: Deploy one shared instance with hourly auto-reset, preserve the cache, fix the three credibility cracks
  (L2 rename, L3, L6), record the video.
- Effort: S (human: 1.5 days / CC: 3 h). Risk: Medium (shared state can still surprise a panel member).
- Pros: ships fastest; removes every "gotcha in ten minutes" item.
- Cons: two panel members at once can still collide; the "upload your own invoice" risk remains.
- Reuses: existing reset, seed and cache code.

**APPROACH B: Sandbox and honest AI (recommended)**
- Summary: Approach A plus a per-visitor sandbox (L1), parser-to-LLM fallback and a read-by chip (L4), labelled
  synthetic data (L8), and two-person bank release (L10).
- Effort: M (human: 3 days / CC: 6-8 h). Risk: Low-Medium.
- Pros: every panel member gets a clean, working link; BYO-invoice becomes a strength; the controls hold up.
- Cons: more surface area to break two days before submission.
- Reuses: seed template DB, `extract_llm.extract`, S6 import, role switcher.

**APPROACH C: Lateral, lead with "bring your own invoice"**
- Summary: Restructure the video and live demo around one unseen invoice first, then the four edge cases as "and
  here is what it catches that your ERP does not".
- Effort: S once B's fallback exists. Risk: High without B.
- Pros: the strongest possible proof that it "handles real inputs".
- Cons: only safe after L4 is fixed and rehearsed.

**RECOMMENDATION:** B, because the guide's core question is "can you build a process that actually runs, handles real
inputs, and deals with edge cases gracefully", and B is the only option that makes "actually runs" and "real inputs"
true for every panel member. Choose A only if fewer than two days remain.

---

## 8. Do before submission (ranked)

| Rank | Action | Closes | Effort (human / CC) |
|---|---|---|---|
| 1 | Deploy a live URL with per-visitor sandbox (or at least hourly auto-reset plus a visible reset button), upload cap and LLM budget | L1, L9 | 1.5 days / 3 h |
| 2 | Make "Accept recommendation" real (partial approve plus credit-note draft) or rename it honestly; add role check | L2 | 1 day / 2 h (rename: 1 h / 15 min) |
| 3 | Remove confidence theatre: truthful S3 source sentence, evidence-based parser confidence, fix the "No AI key configured" log | L3 | 3 h / 30 min |
| 4 | Make EC3 safe live: keep `extraction_cache` across reset, pre-warm, paid or Claude key for the interview, visible rate-limit wait message | L5 | 2 h / 15 min |
| 5 | Replace the GSTIN confusable rule with format and checksum validation; lead EC3 with the inferred PO; drop "smudged" | L6 | 3 h / 30 min |
| 6 | Run five unseen-layout invoices; add parser-to-LLM fallback and a "Read by" chip | L4 | 1 day / 2 h |
| 7 | Label seeded history on S1 and allow excluding it from KPIs | L8 | 2 h / 20 min |
| 8 | Cap inferred-PO display below 100%; prepare the two-PO near-miss variation to run live | L7 | 2 h / 30 min |
| 9 | Two-person bank change and release | L10 | 3 h / 30 min |
| 10 | Opening billed-to-date on PO import | L11 | 2 h / 20 min |
| 11 | Rewrite jargon headlines, refresh README line 165 and the stale screenshot | L13 | 30 min / 10 min |
| 12 | Record the 5-minute video on the deployed URL after a reset with a cold cache; rehearse Q1-Q12 above without notes | L5, L12 | 0.5 day / n/a |

---

## 9. The assignment

Before writing more code: put the deployed link in front of one person who has never seen Ledgerlight and does not
work in finance. Hand them any real PDF bill they have (a phone or utility bill is fine), say nothing, and watch.
Write down the first screen where they hesitate and the first sentence they misread. Fix that before the video.

---

## Appendix: evidence checked

- Guide: `ASA Case Study - Candidate Guide.pdf` (read with `pdftotext -layout`).
- Docs: `PRODUCT_SPEC.md` (sections 1-11 in full), `README.md` (full).
- Code: `backend/app/pipeline.py`, `rules.py`, `matching.py`, `extract_text.py`, `extract_llm.py` (cache and retry),
  `explain.py`, `admin.py`, `repo.py`, `db.py`, `seed.py`, `main.py`, `config.py`;
  `frontend/components/LiveRun.jsx`, `Queue.jsx`, `Audit.jsx`, `Dashboard.jsx`, `Shell.jsx`, `NewRun.jsx`, `Rules.jsx`
  (grep); `samples/make_samples.py`, `samples/expected.json`.
- Screenshots viewed: `S1.png`, `S3.png`, `S4.png` (SI-02), `S4-SI-05.png`, `S3-SI-05-needs-ai.png`, `S5.png`.
- Runs: `pytest -q` in `backend` gave 176 passed, 2 skipped; `frontend/e2e/results.json` has 51 PASS, 0 FAIL.
- Not checked: the mock in `mocks/`, S6, S7 and S8 screenshots, live LLM behaviour, any deployed environment.
