# Ledgerlight: Office Hours, second pass

Reviewer posture: a demanding Zamp hiring panel for the AI Solutions Analyst role, using the gstack `/office-hours`
method (startup mode, intrapreneurship variant, run non-interactively). Date: 17 Nov 2026. Scope: Ledgerlight as it
will be submitted: repo `main` at `ee14515`, frontend https://ledgerlight-snowy.vercel.app, backend
https://ledgerlight-api.onrender.com. Judged against `ASA Case Study - Candidate Guide.pdf` (PS-1) and re-assessing
the 13 loopholes in `docs/review/OFFICE_HOURS.md`.

## 0. How this review was run

- **Evidence kinds.** (a) Static reads of code and docs, cited as `file:line`. (b) Test names from
  `backend/tests/`. (c) Live runs against the public site with three Playwright scripts written for this review and
  run today. No app code, test, config or sample was changed; nothing was committed or deployed.
- **The live scripts** (kept in the session scratchpad, not in the repo):
  - `oh2_check.js`: two separate browser contexts (two visitors, two sandboxes). Visitor A runs all seven samples
    (SI-05 once, from the cache), marks SI-03 reviewed from the queue as a clerk, releases the SI-06 bank hold as one
    manager through the API, uploads two invoices in layouts the generator never produced (U1 known vendor, U2
    unknown vendor), resets its own sandbox, reads S8, and checks S1 at 390 px. Visitor B runs SI-01 and checks it
    cannot see A's runs. Also probes CORS and header-less requests.
  - `oh2_cold.js`: waits 17 minutes with no traffic so the free Render instance sleeps, then opens the site as a
    panel member would and runs SI-05 (the second and last SI-05 run of this review).
  - `oh2_u3.js`: uploads a known vendor's invoice in an unseen layout whose bank line names a new account in plain
    words, to see whether the bank-change control still fires.
- **Key live output, quoted** (full output in section 9):

```
0. backend /api/health answered after 0.2s: {"ok":true,"ai_reads":"scans","runs":60,"extraction_mode":"llm","llm_provider":"groq","llm_model":"qwen/qwen3.8-27b","scanned_pdfs_supported":true}
   CORS for a foreign origin: access-control-allow-origin=null
SUMMARY: SI-01=Approved (10.5s), SI-02=Approved, note (7.6s), SI-03=Needs review (7.6s), SI-04=Rejected (8.1s), SI-06=On hold (7.5s), SI-07=Rejected (7.5s), SI-05=Approved, note (8.4s); B SI-01=Approved; U1=Approved; U2=Rejected
SI-01 ... log: 13:22:36[S2]No AI key configured: reading the PDF text layer with the deterministic parser
SI-05 ... [SI-05] headline: Approved with a note: the vendor is Greenleaf; one smudged character of its GSTIN was misread on the scan.
9. console/page errors across the run: 0
```

- **Skipped skill steps** (to stay inside "write one file in docs/review"): web landscape search, Codex second
  opinion, the `~/.gstack` design-doc copy, builder-profile logging, telemetry, upgrade prompt. The forcing questions
  were answered as the candidate from the guide, `PRODUCT_SPEC.md` and the live observations, then pushed.

---

## 1. Verdict: ready to submit?

**Yes, submit it, after about two hours of fixes that are all cheap and all visible on screen.** The blocker from the
first review is gone: the link is live, every visitor gets a private sandbox, all seven samples give their designed
decision on the public site in 7 to 10 seconds, a second visitor running SI-01 gets Approved (not a duplicate
Reject), reset only touches your own copy, CORS refuses foreign origins, and the live check ran with zero console
errors. An invoice in a layout the generator never produced was read field-for-field and approved correctly. That
already meets the guide's "process that actually runs, handles real inputs". What still costs credibility is a short
list of things a sharp panel sees in the first five minutes: the EC3 showcase (SI-05) still headlines "one smudged
character of its GSTIN was misread" and shows "Implied · 100%", which is exactly what the first review flagged and
what `HANDOFF.md` says was fixed; every clean PDF's live log says "No AI key configured" on a server that has one;
one manager can tick "second person confirmed" and release a bank-change hold alone; and the AI cache and every
sandbox live on a temporary disk that any restart or redeploy throws away (a sleep did not happen in today's 17-minute
idle test, but nothing guarantees it will not happen before the panel's first click). Fix those (sections 3 and 6), re-record
from the live URL, and this is a strong submission on all three graded axes.

---

## 2. The 13 earlier loopholes, re-assessed

Status: **closed** = the panel cannot find it; **partly** = the main harm is gone but a residue is visible or
answerable only with words; **open** = unchanged on the live site.

| # | First-review loophole | Status | Evidence today |
|---|---|---|---|
| L1 | No live link; shared state breaks on the second visitor | **closed** | Live: "two visitors: sandbox A 04416e..., sandbox B b5f30e... different=true; B's SI-01 = Approved; B can see A's SI-01 run: false" and "A reset ... B's SI-01 run still visible to B: true". CORS: foreign origin gets `access-control-allow-origin=null`, the Vercel origin is echoed. Code: `SandboxMiddleware` (`backend/app/main.py:55-89`), `ensure_sandbox` (`backend/app/db.py:190-208`). Tests: `test_two_visitors_get_the_designed_decision_and_never_see_each_other`, `test_reset_only_affects_that_visitor`. Residue: no LLM budget per sandbox (N4) and sandboxes live on `/tmp` (N3) |
| L2 | "Accept recommendation" did nothing | **partly** | Renamed and real: live quick panel shows "Mark reviewed (agree)", toast "K/1241 marked reviewed and moved to Resolved", and the item is in the Resolved tab (test `test_mark_reviewed_moves_item_to_resolved`). Residue, seen live: the clerk (Priya) resolved a manager-assigned ₹23,600 item ("assigned_to=manager exposure=2360000 ... confirmed_by=Priya Nair"), because `accept` has no role check (`backend/app/admin.py:102-119`); and the invoice stays "Needs review" for ever ("after: decision outcome=route_for_review"), so "resolved" has no payment meaning |
| L3 | Confidence theatre on text PDFs | **partly** | Fixed: the S3 sentence now reads "Read from the text layer of the PDF. Confidence reflects whether each value is in the expected format and agrees with the rest of the invoice" (`frontend/components/LiveRun.jsx:261`, seen live), and effective confidence is derived (live API: "invoice_no:0.96->0.98 ... total:0.96->0.98"). Still there: the base is a constant, `hi_conf = 0.88 if low else 0.96` (`backend/app/extract_text.py:526`), so every field on every clean PDF shows 0.96 (live S3 grid: "Invoice no.0.96 ... Invoice date0.96 ... PO reference0.96"); and the live log on every text PDF says "No AI key configured" on a Groq-enabled server (`backend/app/pipeline.py:330`, N1) |
| L4 | "Where is the AI?" and "will it read our invoice?" | **partly** | Better than feared: live U1 (a Tally-style "TAX INVOICE" with "Description of Goods / HSN/SAC / per" columns and split CGST/SGST rows) was read field-for-field: "vendor_gstin=27AAFCB4821K1Z3 invoice_no=BOS/26-27/0912 ... tax_total=6210.00 total=₹ 40,710.00 bank_account=0123 4567 8901" and approved; U2 (unknown vendor) got "Reject: this vendor is not on our approved vendor list". Still open: no AI fallback when the parser fails to reconcile (routing at `backend/app/pipeline.py:292`), no "Read by" chip on S3/S4 (no match for `extraction_mode`/`Read by` in `frontend/components`), and SI-04's "phone photo" is still read from its generated OCR layer (live log: "reading the PDF text layer with the deterministic parser (OCR layer of a scan)"). Live U3 (same layout, a new bank account written as "Please pay to: Account 5566 7788 9900, IFSC KKBK0000123") was correctly held by R05, although the account number itself was not read (N2) |
| L5 | EC3 is the least reliable step and reset destroyed its safety net | **partly** | Fixed: the cache survives reset (`backend/app/db.py:290-306`, test `test_demo_reset_keeps_extraction_cache`) and is shared by all sandboxes (test `test_ai_extraction_cache_is_shared_by_all_visitors`); live SI-05 took 8.4 s with "Saved AI result used (same file, prompt version and model)". Still open: the cache and the template live under `LEDGERLIGHT_DATA_DIR=/tmp/ledgerlight` on a free instance (`render.yaml:21-22`), so a restart or redeploy empties it (N3). Not observed today: after 17 minutes idle the cold probe found the instance awake and SI-05 still cached ("SI-05 after the sleep: state=completed in 10.2s ... Saved AI result used"); no "waiting for the AI provider" message while `_retry_wait` sleeps up to 65 s (`backend/app/extract_llm.py:151-159`) |
| L6 | EC3's story hijacked by a GSTIN-forgiveness rule | **open** | Live S4 headline for SI-05: "Approved with a note: the vendor is Greenleaf; one smudged character of its GSTIN was misread on the scan." Non-pass rules "R02:note, R04:note, R07:note". The rule was widened, not replaced: `OCR_CONFUSABLE` now has 10 pairs including 0/D, 0/Q, 1/L, 6/G (`backend/app/matching.py:28`), while `README.md:63` lists six; no GSTIN checksum; "smudged" is still the headline text (`backend/app/rules.py:248`); R04 still outranks R07 (`backend/app/rules.py:1006`). `HANDOFF.md` item 4 ("SI-05 now approved with a note for the inferred PO only") does not match the live site |
| L7 | Implied PO reports 100% certainty | **open** | Live R07 facts: `"method":"implied","po_id":"PO-2026-1005","score":1,"runner_up":0.1` with every part at 1. The chip renders `Math.round(score*100)%` (`frontend/components/Decision.jsx:239`), so S4 says "Implied · 100%". No two-PO near-miss fixture ready for the spec's own interview variation (`PRODUCT_SPEC.md:1120`, item 3) |
| L8 | Dashboard KPIs mostly synthetic, unlabelled | **open** | Live KPI strip: "Invoices processed 60 ... Straight-through rate 70% ... Median time to decision 12s est. 9 min by hand ... Value protected ₹2,92,872". 57 of the 60 runs are seeded (`README.md:31-32`). No `synthetic`/`Seeded` label anywhere in `frontend/components/Dashboard.jsx`; the only "seeded" words are in the demo-mode menu (`frontend/components/Shell.jsx:154`) and the S4 "PDF not stored for demo history" placeholder (`frontend/components/Decision.jsx:433`). Live visible-text check on S1: "dashboard VISIBLE text mentions seeded/synthetic/demo history: false" |
| L9 | "Append-only" audit log wiped by one button | **partly** | Reset now only wipes the visitor's own sandbox (live step 7). But the banner still promises "Entries cannot be edited or deleted. This log is append-only" (`frontend/components/Audit.jsx:82`, read live after the reset), and the SI-06 override made minutes earlier was gone: "earlier SI-06 override still in log: false". No reset ledger |
| L10 | Bank-change four-eyes control is a self-ticked checkbox | **open** | Live: "SI-06 bank-change hold released by ONE manager ticking "second_person_confirmed": HTTP 200 ... "outcome":"auto_approve","previous_outcome":"hold_request_info"". Code unchanged: one manager ticks all three items (`backend/app/admin.py:67-74`); `change_bank` takes a free-text `verified_by` (`backend/app/admin.py:257-263`) |
| L11 | Billed-to-date assumes Ledgerlight is the system of record | **partly** | The model already supports it: `po_lines.opening_billed_qty` (`backend/app/db.py:33`) seeds billed quantity (`backend/app/matching.py:291`) and the seed data uses it. But the CSV import, the day-one path, drops it: `PO_COLS` has no `opening_billed_qty` (`backend/app/admin.py:461-462`) and the S6 wizard hint does not mention it (`frontend/components/Master.jsx:175`) |
| L12 | Tolerance band auto-pays past the PO | **closed** | Needs an answer, not code, and the abuse case is now covered: repeated small overcharges go to review (test `test_m2_repeated_small_overcharges_go_to_review`), and split invoices hit the limits together (`test_m3_split_invoices_hit_the_limits_together`). Live SI-02 still "Approved with a note: the vendor billed 1.5% more than the PO, which is within the allowed difference", which is the designed behaviour |
| L13 | Developer jargon in buyer-facing text | **partly** | Not reachable on the live site while the Groq key is set (live SI-05 is read, not held). Still in code for the no-key path: `backend/app/rules.py:80-84`, `backend/app/explain.py:182`, `backend/app/pipeline.py:300-305`, and S4 tells the user to "Set GROQ_API_KEY or ANTHROPIC_API_KEY in backend/.env" (`frontend/components/Decision.jsx:141`). `README.md:165` still says SI-05 is Hold "when no `ANTHROPIC_API_KEY` is set" |

**Count: 2 closed (L1, L12), 7 partly (L2, L3, L4, L5, L9, L11, L13), 4 open (L6, L7, L8, L10).**

---

## 3. New findings, ranked

Severity: **blocker** (cannot submit, or the demo collapses), **high** (a sharp interviewer finds it and it costs the
round's credibility), **medium** (costs points, has a good answer), **low** (polish). Effort is (human / Claude Code).

**Ranking at a glance.** No blocker. **High:** N1. **Medium:** N3, N4, N5, N6. **Low:** N2, N7, N8. (N2 is numbered
in the order it was found; its live result turned out benign.) The carried-over items that still matter most rank
alongside these: **L6 (high)** and **L10 (high)** are the two a panel is likeliest to hit in the first ten minutes,
then **L7 (medium)**, **L8 (medium)** and the L2 role check (medium).

### N1. The live log says "No AI key configured" on every clean PDF (high)
- **Evidence (live):** every text sample logs `[S2]No AI key configured: reading the PDF text layer with the
  deterministic parser`, while `/api/health` on the same server reports `"extraction_mode":"llm","llm_provider":"groq"`.
  Source: `backend/app/pipeline.py:330`. This was half of L3 and was not changed.
- **Why it hurts:** the live run log is the screen the panel watches most. In an AI interview, a log line claiming
  the AI is not configured, followed by the AI reading SI-05 thirty seconds later, reads as "the candidate does not
  know what their own system is doing".
- **Fix:** branch the message: with a key, "Text PDF: reading the exact text layer with the deterministic parser
  (AI is used for image-only scans)"; without one, keep the current line. Add a one-line test on the log text.
- **Effort:** (human: 15 min / CC: 5 min).

### N2. On an unseen layout, a new bank account is caught by its IFSC, not its number (low)
- **Evidence (live, `oh2_u3.js`):** a Brightline invoice in the U1 layout with "Please pay to: Account 5566 7788 9900,
  IFSC KKBK0000123". Result: "outcome=hold_request_info; headline: Hold: the bank account on this invoice is
  different from the one we have on file". But "bank fields read: account=null ifsc="KKBK0000123"", and the rule
  message says "The invoice asks us to pay a different bank (account none)".
- **Why it matters:** the control did its job, which is the headline. But the decision rests on the IFSC alone, and
  the buyer-facing sentence prints "account none". An invoice that changed only the account number, kept the IFSC and
  used this phrasing would depend on the "unreadable bank" path (test
  `test_bank_compare_checks_every_entry_and_unreadable_bank`), which this review did not probe live.
- **Fix:** accept "Account", "Acct", "Pay to" and "Beneficiary account" labels in the bank parser; when the number is
  unreadable, say "the account number could not be read" instead of "account none". Add the U3 PDF as a fixture.
- **Effort:** (human: 1 h / CC: 20 min).

### N3. The AI cache and every sandbox live on a temporary disk (medium; sleep not reproduced today)
- **Evidence:** `LEDGERLIGHT_DATA_DIR=/tmp/ledgerlight` on `plan: free` (`render.yaml:7,21-22`); the template is
  rebuilt on each start (`backend/app/main.py:35-38`, `seed.build_template`); `DEPLOY_PLAN.md` itself notes "sandboxes and the AI cache are
  lost on each deploy or restart". **Today's cold probe did not reproduce a sleep:** after 17 minutes with no
  traffic from this review, the site loaded in 1.0 s ("cold visit: dashboard with run rows after 1.0s") and SI-05 was
  still served from the cache in 10.2 s. Something kept the instance awake (other traffic, or Render's own health
  checks; not determined). So the risk is real on any restart or redeploy, and on a sleep if one happens, but it was
  not observed.
- **Why it hurts:** the panel will open the link hours or days after you warmed it. The first SI-05 run after a restart goes
  to Groq's free tier (about 6k of the 7k tokens a minute, `README.md:57-60`), so EC3 can take a minute or stall on a
  rate limit, in front of them, with no on-screen reason. A panel member who ran samples, left for 20 minutes and
  came back also finds their runs gone.
- **Fix (pick one):** (a) commit the SI-05 extraction (the JSON already stored in `extraction_cache`) as a seed file
  and load it into the shared cache at startup, so a cold instance is warm by construction (human: 1 h / CC: 20
  min); (b) pay for the $7 starter plan for the interview week, which removes the sleep (5 min, money); (c) at
  minimum, run `backend/scripts/warmup.py` five minutes before the interview and before sending the email. Do (a)
  regardless: it is the only one that protects the panel's own first visit.

### N4. No per-visitor AI budget on a public link (medium)
- **Evidence:** a header-less request gets a brand-new sandbox (live: "request with no sandbox id -> server issued
  sandbox header: yes (new sandbox created)"); uploads are capped at 10 files and 10 MB (`backend/app/main.py:217`,
  `backend/app/config.py:63`) but there is no cap on image-only scans per sandbox or per hour (no budget or quota
  code in `backend/app`). Each distinct scan is a fresh Groq call.
- **Why it hurts:** anyone who finds the link (or one curious panel member uploading phone photos) can burn the free
  Groq quota, and then SI-05 for everyone waits behind the rate limit or fails with "AI extraction failed".
- **Fix:** allow at most 3 uncached scan reads per sandbox and 20 per hour per server; beyond that, hold with "This
  demo server reads up to 3 new scans per visitor. Samples still run." Serialise Groq calls so two visitors queue
  instead of colliding. Rotate the key after submission, as `HANDOFF.md` already says.
- **Effort:** (human: 2 h / CC: 30 min).

### N5. Health checks and other header-less calls create sandboxes (medium, partly inferred)
- **Evidence:** `SandboxMiddleware` gives every `/api` request without an id a new sandbox, copying the template
  (`backend/app/main.py:67-80`), and keeps at most 300, deleting the least recently used (`backend/app/db.py:137,
  211-222`). `render.yaml:12` points Render's health check at `/api/health`. The live probe confirmed the
  new-sandbox behaviour for a header-less `/api/health` call. **Inferred, not measured:** how often Render's checker
  calls it. If it is every few seconds, it churns a template copy per call and, within the hour, pushes any sandbox
  idle for longer than that out of the 300 cap.
- **Fix:** skip the middleware for `/api/health` and make health read a constant instead of counting runs.
- **Effort:** (human: 20 min / CC: 10 min).

### N6. The docs and the demo script describe a different build from the live one (medium)
- **Evidence:** `README.md` has no live URL (no match for `ledgerlight-snowy`), still says "CORS is open"
  (`README.md:151`) and lists six confusable pairs (`README.md:63`) where the code has ten. The demo script promises
  "96% match against 14%" (`PRODUCT_SPEC.md:1113`) where the live site shows 100% vs 10%, "roughly ₹4 lakh" stopped
  (`PRODUCT_SPEC.md:1110`) where the live KPI is ₹2,92,872, and a `docker-compose up` fallback (`PRODUCT_SPEC.md:1122`)
  for a compose file that does not exist. S5 is still specified with "Accept recommendation" (`PRODUCT_SPEC.md:678`).
  `HANDOFF.md` item 4 lists the doc update as not done.
- **Why it hurts:** the candidate rehearses from this script. Saying "96%" while the screen says 100% is a live
  contradiction, and a panel that reads the repo sees a README that does not mention the link it was sent.
- **Fix:** add the live link and the sandbox note at the top of the README; correct the four stale lines; rewrite
  §10 against the numbers in section 9 of this review; add a short "Known differences from the spec" list.
- **Effort:** (human: 1 h / CC: 20 min).

### N7. "Unknown vendor" is a hard Reject (low)
- **Evidence (live):** U2, a plausible housekeeping invoice from a vendor not in master data: "Reject: this vendor is
  not on our approved vendor list".
- **Why it matters:** a panel member may argue that a first invoice from a new supplier is an onboarding task, not a
  rejection. The decision is defensible (do not pay an unapproved vendor), but say why.
- **Fix:** no code needed. Answer: "Reject means 'do not pay this document'; the drafted reply asks the vendor to
  complete onboarding first, and re-running after S6 adds them gives a normal decision." Optional later: route
  unknown vendors to a "vendor onboarding" queue (PS-2's territory).

### N8. Roles are a client header (low)
- **Evidence:** `X-Ledgerlight-Role` is set by the browser (`frontend/lib/api.js:9-11,47`) and trusted by the API
  (`backend/app/admin.py:30-34`); the live probe released a bank hold by sending `role: manager`.
- **Why it matters:** inside a sandbox it harms nobody, and assumption A11 (`PRODUCT_SPEC.md:1142`) states roles are
  simulated. Have the sentence ready rather than being caught.

---

## 4. Live-demo risks and how to avoid each

| # | Risk | What the panel would see | How to avoid it |
|---|---|---|---|
| R1 | Cold start after 15 min idle | Not reproduced today (17 min idle, then a 1.0 s dashboard); the brief's ~50 s cold start is unverified by this review. If it happens: a spinning dashboard for most of a minute | Open the backend URL and the site 2 to 3 minutes before the call; better, buy the starter plan for the week (N3 b) |
| R2 | SI-05 cache lost on restart, redeploy or sleep | EC3 takes about a minute, or pauses on a rate limit with no explanation | Ship N3 (a); until then run `warmup.py` right before; never run SI-05 first in a cold session |
| R3 | EC3 headline is the GSTIN "smudged character" note | You say "watch it infer the PO" and the headline talks about a tax ID | Fix L6 (move R07 ahead of R04-NOTE, drop "smudged") before recording; if not fixed, say it out loud first: "it also forgave a one-character GSTIN misread; here is why that is a note and not a review" |
| R4 | "Implied · 100%" | "No PO number and you are 100% sure?" | Cap displayed implied scores at 99% and label "inferred" (L7); have the two-PO near-miss variation ready |
| R5 | "No AI key configured" in the S3 log | A visible contradiction on the most-watched screen | Ship N1 (5 minutes) |
| R6 | Groq slow or down during the interview | Stage 2 spins, then "AI extraction failed" with Retry | Keep "Use saved AI results" on (default true, `frontend/components/Shell.jsx:39`); have the recorded video open in a tab; for the interview, a paid Groq or Claude key |
| R7 | Panel uploads their own invoice | Parser misreads a layout, or a scan burns quota | Rehearse with U1/U2-style invoices; say before uploading: "if it cannot read something it holds with a reason, it never guesses"; ship N4 |
| R8 | Panel member resolves a review as clerk | A ₹23,600 manager item disappears into Resolved while still "Needs review" | Add the role check to `accept` (L2); in the demo, switch to AP Manager before touching the queue |
| R9 | "Who is the second person?" on EC4 | You tick all three boxes yourself | Ship L10 (second user must release), or say it plainly: "in the demo one person plays both roles; in production the release requires a second login" |
| R10 | Your earlier runs vanish between takes | Sandboxes and runs reset on any restart or redeploy | Do not push between the recording and the interview (`autoDeploy: true`, `render.yaml:13`); reset deliberately before each take |
| R11 | The script's numbers differ from the screen | "96%", "₹4 lakh", "11 seconds" vs 100%, ₹2,92,872, 7 to 10 s | Rewrite §10 from section 9 of this review (N6) |

---

## 5. The eight hardest interviewer questions, with honest answers

1. **"Where exactly is the AI, and why does most of your demo not use it?"**
   "In two places, deliberately. A clean PDF already contains the exact text, so a deterministic parser reads it:
   free, instant, and the same answer every time. The vision model reads what has no text, like the Greenleaf scan,
   twice in different orders, and I compare the two reads. The model also words the explanation, and any number it
   adds that is not in the rule facts is rejected. It never decides money; sixteen rules do. What I have not built
   yet is the automatic hand-off from the parser to the model when the parser's numbers do not add up. That is the
   first thing I would add." (Honest only after N1 is fixed, or the log contradicts you.)

2. **"Here is one of our invoices. Run it."**
   "Sure." Then upload. The live probe shows a layout it was never built for (U1) read field-for-field and approved.
   If it cannot read something, the honest outcome is a Hold with the field named, not a guess: "a Hold with a
   reason is a correct outcome; a wrong approval is not." Do not promise more than that.

3. **"Your EC3 screen says one smudged character of the GSTIN was misread. Why does a tax-ID mismatch get a
   note on a fraud check?"**
   Best answer (after the L6 fix): "It no longer does by a lookalike-character list. A read GSTIN that fails the
   format or the check digit, and is one character away from a valid master value with an exact name match, is
   provably a misread, so it is a note. Anything else goes to review." If not fixed, be straight: "It is a narrow
   rule: scan only, exact name match, one character, a known lookalike pair. I added it because the vision model
   misread my own sample, and I would replace it with checksum validation before any real use."

4. **"No PO number, and you show 100%?"**
   "The score is how well this invoice fits each open PO on items, unit prices, remaining quantity, remaining value
   and date. It fits PO-1005 on all five and the other open order on one. 100% says the data is clean, not that the
   inference is certain, which is why the outcome is a note telling the clerk what was inferred, and why a close
   second candidate turns it into a review." (Then cap the display at 99%, L7.)

5. **"Show me the four-eyes control on the bank change. Who is the second person?"**
   Today: "In this demo one manager can tick all three items. That is a gap: the release should require a second
   user, and the person who changed the vendor's bank record should not be the one who releases the hold." After
   L10: switch users live and show the refusal.

6. **"How much of your dashboard is real?"**
   "Three of the sixty history rows ran through the pipeline from real PDFs; fifty-seven are seeded so every chart
   and filter has data. Every run you start, including the ones you just watched, is real and is added on top." Say
   it before they ask (L8), ideally with a "Seeded" chip on screen.

7. **"Your ERP already does two-way match. What do you add?"**
   "Memory across split invoices (EC1: the third Kestrel invoice is perfect alone and 500 cartons over in total);
   duplicate identity when the number is written differently (EC2); and fraud signals inside an otherwise perfect
   invoice (EC4). Plus a plain-English reason a clerk can send the vendor. And on day one, billed-to-date comes from
   the ERP export as an opening quantity; the model supports it today, and I would add the column to the CSV import
   (L11)."

8. **"What breaks this in production that your demo hides?"**
   "Four things, in order: layouts the parser has never seen without an AI fallback; no real authentication, so roles
   are simulated; one SQLite file per visitor on a temporary disk, which is fine for a demo and wrong for a company;
   and two-way match only, no goods receipt. For a pilot I would measure straight-through rate, wrongly auto-approved
   invoices in a 10% sample, override rate per rule and rupees blocked, weekly, with a target of zero misses on
   duplicates and bank changes."

---

## 6. Pre-submission checklist

Ordered by value per minute. Tick every box before the email goes out.

| # | Action | Closes | Effort (human / CC) |
|---|---|---|---|
| 1 | Change the S2 log line on text PDFs when a key is set (`backend/app/pipeline.py:330`) | N1, L3 | 15 min / 5 min |
| 2 | Make EC3 lead with the inferred PO: put R07 ahead of R04-NOTE in `LEAD_PRIORITY` (`backend/app/rules.py:1006`), drop "smudged" (`backend/app/rules.py:248`); better, replace the confusable list with GSTIN format and check-digit validation | L6 | 30 min (checksum: 2 h) / 10 min (30 min) |
| 3 | Cap displayed implied-PO scores at 99% and label them "inferred" (`frontend/components/Decision.jsx:239,246`) | L7 | 15 min / 5 min |
| 4 | Seed the SI-05 extraction into the shared cache at startup, or buy the starter plan for the week | N3, L5 | 1 h / 20 min |
| 5 | Role check on "Mark reviewed": a clerk cannot resolve a manager-assigned item (`backend/app/admin.py:102`) | L2 | 20 min / 10 min |
| 6 | Bank-hold release needs a second user, and not the one who changed the bank record | L10 | 3 h / 30 min |
| 7 | "Seeded" chip on synthetic rows and a line under the KPI strip | L8 | 2 h / 20 min |
| 8 | Per-sandbox and per-hour cap on uncached scan reads; skip sandboxes for `/api/health` | N4, N5 | 2 h / 40 min |
| 9 | README: live link first, sandbox note, fix lines 63, 151, 165; rewrite `PRODUCT_SPEC.md` §10 against live numbers; remove the docker-compose fallback | N6, L13 | 1 h / 20 min |
| 10 | S8 banner: "Resetting the demo starts a new log for your sandbox" | L9 | 10 min / 5 min |
| 11 | Re-run `pytest`, the live `npm run check` (51/51) and the probes in this review after the fixes; redeploy; run `warmup.py` | all | 30 min / 15 min |
| 12 | Record the video from the live URL in a fresh browser profile, after a warm-up, with no redeploy afterwards | R1, R2, R10 | 1 h / n/a |
| 13 | Rotate the Groq key after the interview (it was pasted in a chat, `HANDOFF.md`) | security | 5 min |
| 14 | Send the coordinator the live link and the video link; say in one line that the backend may take a minute to wake | guide, Day 7 | 5 min |

If only an hour is available: items 1, 2, 3, 4 (or the paid plan), 9's README link, and 12.

---

## 7. Five-minute video outline

Record on the live URL in a fresh browser profile (new sandbox), 1440 wide, AP Clerk role, "Use saved AI results"
on, speed Normal, after running `warmup.py`. This assumes checklist items 1 to 3 are done; where they are not, use
the bracketed line instead. Numbers below are what the live site showed today.

| Time | Screen | What to click | What to say |
|---|---|---|---|
| 0:00-0:25 | S1 Dashboard | Hover the KPI strip, then the runs table | "This is Ledgerlight, live at this link; every visitor gets their own private copy, so you can run everything I show. Invoice PDF in, a decision out, every step visible. Sixty invoices in the last thirty days, 70% straight through. Three of these history rows came from real PDFs and the rest are seeded so the charts have data; everything I run now is real." |
| 0:25-1:20 | S2, S3, S4: SI-01 happy path | S2: Brightline card, Run this sample. S3: narrate the stages as they light up; point at the field grid. Then See the full explanation | "A clean PDF has exact text, so a deterministic parser reads it: free, instant, repeatable. Nine stages: read, normalise, vendor, duplicate check, PO, sixteen rules, explanation. About eight seconds; the pacing is slowed on purpose so you can watch it, and it says so in the log. Approved, nothing for a person to do. On the left the PDF, on the right every line matched to the PO with zero variance." |
| 1:20-2:20 | S3, S4: EC1 split PO (SI-03) | Run Kestrel. In S4 show the cumulative bar. Switch to AP Manager, Override, Send back for info, reason "Credit note requested" | "This one looks perfect on its own: right price, right PO. But it is the third invoice on this PO and only 2,500 cartons remain, so it bills 500 too many, ₹23,600 with GST. An ERP that checks one invoice at a time pays it. Ledgerlight routes it to the manager, who sends it back with a reason and a drafted email; the audit log records who and why." |
| 2:20-3:05 | S3, S4: EC4 bank change (SI-06) | Run Corevolt bank change. Show bank on invoice vs on file, then the release checklist | "Everything is right except the bank details in the footer. That is the classic payment-fraud pattern, so it is never auto-approved and never a judgment call: On hold, call the vendor on the number we already have, get it in writing, and a second person releases it." [If L10 is not done: "In this demo one manager plays both roles; in production the release needs a second login."] |
| 3:05-3:55 | S3, S4: EC3 scan with no PO (SI-05) | Run the Greenleaf scan. In S3 point at the "Reading the page image with the vision model" and "Second pass ... agree" log lines. In S4 open the PO match panel | "A blurry image with no text and no PO number. Here the AI reads the image, twice in different orders, and the two reads agree. The rules then infer the PO: it fits PO-1005 on items, prices, quantity, value and date, and the other open order on almost nothing. Approved with a note that says exactly what was inferred, so a person can check it in seconds." [If L6 is not fixed: "It also caught a one-character misread of the vendor's tax ID and noted it rather than blocking, because the name matched exactly and the characters are a known scanner confusion."] |
| 3:55-4:25 | S4: EC2 duplicate (SI-04) (cut first if long) | Run Brightline rescan; show the similarity gauge and the side-by-side | "A re-scan of an invoice we already paid, with the number written differently. A string match misses it. Five signals give near-certain similarity to the invoice paid on 5 November: Rejected, ₹1,18,000 not paid twice." |
| 4:25-5:00 | S8, then S1 | Filter S8 to K/1241; back to S1 | "Everything is in the audit log: what was read, each rule, the override and its reason. The numbers on the dashboard have moved with what we ran. The AI reads, the rules decide, and anyone can see why. Thanks." |

**Do not** in the video: upload an unrehearsed invoice, run SI-05 first in a cold session, or say any number you
have not just seen on screen.

**Live interview, same spine plus:** (1) S7: change the allowed difference from 2% to 1%, re-run SI-02, watch it flip
to Needs review ("rules are policy, not code"); (2) S6: update Corevolt's bank record with a reason, re-run SI-06,
R05 passes; (3) a rehearsed "bring your own invoice" in a new layout (U1 is the template); (4) only if built, the
two-PO near-miss that turns EC3 into a review.

---

## 8. Forcing questions, second round (answered as the candidate, then pushed)

**Q1 Demand reality.** *Candidate:* "The brief is the demand: PS-1 'reflects work Zamp actually does'." *Push:* still
the right framing for a take-home, and now there is better evidence than the brief: a stranger's layout (U1) read and
decided correctly on the live link. Say that, not "AI reads invoices". **Position:** acceptable.

**Q2 Status quo.** *Candidate:* "PDF, spreadsheet, calculator; or an ERP two-way match." *Push:* the answer to "my ERP
already matches" is in the product (EC1, EC2, EC4) and belongs in the first minute of the video, not in Q&A.

**Q3 Desperate specificity.** *Candidate:* "Rahul, the AP manager, gets fired for a payment to a fraudster's account."
*Push:* then EC4 is the most important screen, and today its control is the weakest (L10). The story and the control
must match before the interview.

**Q4 (intrapreneurship) Smallest demo that gets a yes.** *Candidate:* "One link that works for every panel member, one
sample live, one unseen invoice that does not lie." *Push:* the first and third now hold (L1 closed, U1 correct). The
second holds for SI-01 to SI-07 when warm; the risk is the first visit after a sleep (N3). That is the one to buy down.

**Q5 Observation and surprise.** *Candidate:* "I ran a live script as two visitors." *Push:* the surprise a script
found is the kind a person would: the clerk can "resolve" a manager's ₹23,600 item, and the EC3 headline still talks
about a tax ID. The first review's assignment (watch a non-finance person use the link) is still undone. Do it before
recording; it takes 20 minutes.

**Q6 Future-fit.** *Candidate:* "Extraction becomes a commodity; the control layer, the exception workflow and the
audit trail are what last." *Push:* right, and that makes every control gap (L10, L2's role check) more costly to
leave than any extraction gap.

**The assignment:** before recording, give the live link to one person outside finance, hand them a real PDF bill,
say nothing, and note the first screen where they hesitate and the first sentence they misread. Fix that sentence.

---

## 9. Live evidence (Playwright output, 17 Nov 2026)

`oh2_check.js` (RUN_SCAN=1), trimmed only of repeated S3 notes and explicit-PO R07 lines; long lines cut at 330 characters:

```
0. backend /api/health answered after 0.2s: {"ok":true,"ai_reads":"scans","runs":60,"extraction_mode":"llm","llm_provider":"groq","llm_model":"qwen/qwen3.8-27b","scanned_pdfs_supported":true}
   request with no sandbox id -> server issued sandbox header: yes (new sandbox created)
   CORS for a foreign origin: access-control-allow-origin=null
   CORS for the Vercel origin: access-control-allow-origin=https://ledgerlight-snowy.vercel.app
1. S1 dashboard with run rows after 1.1s
   KPI tiles: Invoices processed 60 in the last 30 days || Straight-through rate 70% approved with no human touch || Median time to decision 12s est. 9 min by hand || Open exceptions 14 9 to review · 5 on hold || Value protected ₹2,92,872 Duplicates and overbilling stopped || Value approved ₹1.08Cr Gross, in the payment queue
   runs rows: 25; text mentions seeded/synthetic/sample history: true
SI-01: run run_674b10 state=completed in 10.5s
  log: 13:22:36[S2]No AI key configured: reading the PDF text layer with the deterministic parser
  S3 field source note: "Read from the text layer of the PDF. Confidence reflects whether each value is in the expected format and agrees with the rest of the invoice. Fields appear as "
  [SI-01] outcome=auto_approve (Approved) made_by=system | non-pass rules: none
  [SI-01] headline: Approved: everything checks out and it is safe to pay.
SI-02: run run_30e41f state=completed in 7.6s
  log: 13:22:46[S2]No AI key configured: reading the PDF text layer with the deterministic parser
  [SI-02] outcome=approve_with_note (Approved, note) made_by=system | non-pass rules: R10:note, R12:note
  [SI-02] headline: Approved with a note: the vendor billed 1.5% more than the PO, which is within the allowed difference.
SI-03: run run_c682a4 state=completed in 7.6s
  log: 13:22:55[S2]No AI key configured: reading the PDF text layer with the deterministic parser
  [SI-03] outcome=route_for_review (Needs review) made_by=system | non-pass rules: R11:review, R12:review
  [SI-03] headline: Check this: The bill is higher than what was ordered.
SI-04: run run_a2b85e state=completed in 8.1s
  log: 13:23:03[S2]No AI key configured: reading the PDF text layer with the deterministic parser (OCR layer of a scan)
  S3 field source note: "We read this by looking at the image, so some values carry less confidence. Fields appear as each stage finishes."
  [SI-04] outcome=reject (Rejected) made_by=system | non-pass rules: R06:reject, R08:reject, R11:reject, R12:reject
  [SI-04] headline: Reject: this looks like an invoice we have already paid.
SI-06: run run_9c4966 state=completed in 7.5s
  log: 13:23:12[S2]No AI key configured: reading the PDF text layer with the deterministic parser
  [SI-06] outcome=hold_request_info (On hold) made_by=system | non-pass rules: R05:hold
  [SI-06] headline: Hold: the bank account on this invoice is different from the one we have on file.
SI-07: run run_719fc6 state=completed in 7.5s
  log: 13:23:20[S2]No AI key configured: reading the PDF text layer with the deterministic parser
  [SI-07] outcome=reject (Rejected) made_by=system | non-pass rules: R13:reject, R14:reject
  [SI-07] headline: Reject: the GST on this invoice is wrong and the vendor must send a corrected one.
SI-05: run run_28cc86 state=completed in 8.4s
  log: 13:23:28[S2]Reading the page image with the vision model (groq qwen/qwen3.8-27b, saved result if available)
  log: 13:23:28[S2]Saved AI result used (same file, prompt version and model).
  log: 13:23:28[S2]Second pass with a different reading order: amounts and fields agree
  [SI-05] outcome=approve_with_note (Approved, note) made_by=system | non-pass rules: R02:note, R04:note, R07:note
  [SI-05] headline: Approved with a note: the vendor is Greenleaf; one smudged character of its GSTIN was misread on the scan.
  [SI-05] R07 facts: {"method":"implied","po_id":"PO-2026-1005","score":1,"runner_up":0.1,"runner_up_po":"PO-2026-0979","gap":0.9,"candidates":[{"po_id":"PO-2026-1005","score":1,"parts":{"desc":1,"price":1,"qty":1,"total":1,"date":1}},{"po_id":"PO-2026-0979","score":0.1,"parts":{"
   SI-01 S3 field grid text: Vendor0.93Brightline Office Supplies Pvt LtdInvoice no.0.96BL/2026/0412Invoice date0.9614 Nov 2026PO reference0.96PO-2026-1001Currency0.95₹SubtotalTax (GST)TotalVendor GSTIN0.9627AAFCB4821K1Z3
   SI-01 parser confidences (API): vendor_name:0.93->0.965 vendor_gstin:0.96->0.98 invoice_no:0.96->0.98 invoice_date:0.96->0.98 po_reference:0.96->0.98 currency:0.95->0.975 subtotal:0.96->0.98 tax_total:0.96->0.98 total:0.96->0.98 bank_name:0.96->0.98 bank_account:0.96->0.98 bank_ifsc:0.96->0.98
SI-01: run run_6d7b21 state=completed in 7.4s
  log: 13:23:39[S2]No AI key configured: reading the PDF text layer with the deterministic parser
  [SI-01] outcome=auto_approve (Approved) made_by=system | non-pass rules: none
  [SI-01] headline: Approved: everything checks out and it is safe to pay.
3. two visitors: sandbox A 04416e..., sandbox B b5f30e... different=true; B's SI-01 = Approved; B can see A's SI-01 run: false
4. SI-03 queue item: assigned_to=manager exposure=2360000
   quick panel primary button: "Mark reviewed (agree)"
   toast after click (role = clerk): "K/1241 marked reviewed and moved to Resolved. To change what is paid, use Override."
   after: decision outcome=route_for_review, confirmed_by=Priya Nair; in Resolved tab: true
5. SI-06 bank-change hold released by ONE manager ticking "second_person_confirmed": HTTP 200 {"decision_id":68,"version":2,"outcome":"auto_approve","previous_outcome":"hold_request_info","invoice":{"invoice":{"id":"INV-E09E361E","fil
U1 (unseen layout, uploaded): run run_e700d8 state=completed in 7.7s
  [U1] outcome=auto_approve (Approved) made_by=system | non-pass rules: none
  [U1] headline: Approved: everything checks out and it is safe to pay.
  [U1] R07 facts: {"method":"explicit","po_id":"PO-2026-0985","score":1,"runner_up":null,"runner_up_po":null,"gap":null,"candidates":[],"written_as":"2026-0985","reference_not_found":null}
  [U1] extracted: vendor_name="BRIGHTLINE OFFICE SUPPLIES" | vendor_gstin="27AAFCB4821K1Z3" | invoice_no="BOS/26-27/0912" | invoice_date="14-Nov-2026" | po_reference="2026-0985" | subtotal="34500.00" | tax_total="6210.00" | total="₹ 40,710.00" | bank_account="0123 4567 8901" | bank_ifsc="HUBK0000214"
  [U1] lines read: 1 undefined|qty 10|unit 345000|amt 3450000
U2 (unseen layout, uploaded): run run_a760ae state=completed in 7.1s
  [U2] outcome=reject (Rejected) made_by=system | non-pass rules: R04:reject, R07:hold
  [U2] headline: Reject: this vendor is not on our approved vendor list.
  [U2] R07 facts: {"method":"none","po_id":null,"score":null,"runner_up":null,"runner_up_po":null,"gap":null,"candidates":[],"written_as":null,"reference_not_found":null}
  [U2] extracted: vendor_name="Sunrise Facility Services" | vendor_gstin="19AAPFS2231L1Z5" | invoice_no="SFS-1182" | invoice_date="10/11/2026" | po_reference=null | subtotal=null | tax_total="8640.00" | total="56,640.00" | bank_account=null | bank_ifsc="KKBK0000123"
  [U2] lines read: 0 
7. A reset: HTTP 200 {"runs":60,"named_history":[],"synthetic":null,"open_exceptions":14,"sandbox":"04416ed62d0eea9461fd1; B's SI-01 run still visible to B: true
   S8 banner after reset: "Entries cannot be edited or deleted. This log is append-only. Corrections are recorded as new entries."; earlier SI-06 override still in log: false
8. S1 at 390px: horizontal page overflow 0px (screenshot oh2_S1_390.png)
9. console/page errors across the run: 0
SUMMARY: SI-01=Approved (10.5s), SI-02=Approved, note (7.6s), SI-03=Needs review (7.6s), SI-04=Rejected (8.1s), SI-06=On hold (7.5s), SI-07=Rejected (7.5s), SI-05=Approved, note (8.4s); B SI-01=Approved; U1=Approved; U2=Rejected
```

`oh2_cold.js` (17 minutes idle first, then a fresh visitor):

```
07:55:12 idle wait 17 min (no requests to the backend)
08:12:13 frontend HTML loaded in 0.9s
08:12:13 first visible text: "Ledgerlight Dashboard New run Live run Review queue Purchase orders and vendors Rules and tolerances Audit log DEMO CASES EC1 Kestrel, split PO EC2 Brightline, duplicate EC3 Greenleaf, blurry scan EC4"
08:12:13 cold visit: dashboard with run rows after 1.0s
08:12:13 dashboard VISIBLE text mentions seeded/synthetic/demo history: false
08:12:24 SI-05 after the sleep: state=completed in 10.2s
08:12:24   log: 13:41:52[S2]Reading the page image with the vision model (groq qwen/qwen3.8-27b, saved result if available)
08:12:24   log: 13:41:52[S2]Saved AI result used (same file, prompt version and model).
08:12:24   log: 13:41:52[S2]Second pass with a different reading order: amounts and fields agree
08:12:24   outcome=approve_with_note headline: Approved with a note: the vendor is Greenleaf; one smudged character of its GSTIN was misread on the scan.
08:12:25   S4 PO panel: "Purchase order match PO-2026-1005 Implied · 100% Issued 2 Nov 2026 · valid to 31 Dec 2026 · open MATCH CANDIDATES (INFERRED, NO PO ON THE INVOICE) PO-2026-1005 Selected 100% desc 100% price 100% qty 100% total 100% date 100% PO-2026-0979 Runner-up 10% desc 0% "
08:12:25   S4 headline: "Approved with a note: the vendor is Greenleaf; one smudged character of its GSTIN was misread on the scan."
```

`oh2_u3.js` (new bank account in plain words, unseen layout):

```
U3 run run_a624ba state=completed: outcome=hold_request_info; headline: Hold: the bank account on this invoice is different from the one we have on file.
U3 bank fields read: account=null ifsc="KKBK0000123"; R05 hold: The invoice asks us to pay a different bank (account none). We have Harbor Union Bank (account ending 8901).
U3 non-pass rules: R05:hold
```

**What the probes did not cover:** a real Render sleep (it did not happen in the idle window), a Groq call on a cold
cache (both SI-05 runs were served from the cache, so the rate-limit path is untested live), and the panel's
browsers (Chromium only, 1440 px and 390 px).

**Scripts:** `oh2_check.js`, `oh2_cold.js`, `oh2_u3.js` in the session scratchpad. Re-run with
`node oh2_check.js` (add `RUN_SCAN=1` to include SI-05); they require Playwright from `frontend/node_modules` and
change nothing outside the sandboxes they create.
