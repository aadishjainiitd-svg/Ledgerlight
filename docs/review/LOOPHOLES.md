# Ledgerlight invoice-decision pipeline: adversarial review

**Summary: 23 findings: 6 critical, 3 high, 8 medium, 6 low (51 cases run through the real API: 24 LOOPHOLE, 3 WEAK, 23 OK, 1 UNTESTED).**

> **Status, 17 Nov 2026: all 23 findings are fixed.** Re-running the 49 text cases gives 49 OK
> (`adversarial/results.after-fixes.json`; `results.json` keeps the original run). Each fix has a regression test
> built from the attack PDF in `backend/tests/test_review_fixes.py`. The two scan cases (S01, S02) need a Groq or
> Claude key and are not part of that re-run. The findings below describe the state at review time.

Date: 16 Nov 2026 (the app's as-of date). Nothing in `backend/`, `frontend/`, `samples/` or the tests was changed.

## How to reproduce

```
backend\.venv\Scripts\python docs\review\adversarial\run.py --data-dir <empty temp folder>
```

`run.py` regenerates every input PDF (`gen.py` writes them to `docs/review/adversarial/pdfs/`), starts its own
uvicorn on `127.0.0.1:8050` with `LEDGERLIGHT_DATA_DIR` set to that temp folder (never `backend/data`) and
`LEDGERLIGHT_PACE=instant`, runs `POST /api/demo/reset` before every case, uploads the files through
`POST /api/runs`, waits for each run, then stops the server. It runs in two phases:

* **text phase** (49 cases): AI keys switched off, so text PDFs go through the deterministic parser and explanations
  are the deterministic templates (the default product behaviour for text PDFs; it also keeps results repeatable).
* **scan phase** (2 cases, `S01`, `S02`): `backend/.env` is loaded so image-only scans go to the Groq vision model,
  with a 65 s pause between cases for the free-tier limits.

Options: `--no-scans`, `--only A01,A05`, `--no-server` (use a server you already started on 8050).
Each case's full decision (outcome, driving rules, headline, every non-pass rule message) is saved in
`docs/review/adversarial/results.json`.

Verdicts: **LOOPHOLE** = the decision is wrong (pays what a careful AP manager would stop, or stops a legitimate
invoice, or the run fails); **WEAK** = defensible decision, misleading explanation; **OK** = right decision;
**UNTESTED** = the AI provider refused the call (rate limit), so no product decision was made.

## Results table (as printed by run.py)

```
======================================================================================================================================================
case  verdict  sev if wrong expected                           actual                                                       title
------------------------------------------------------------------------------------------------------------------------------------------------------
A01   LOOPHOLE critical     REVIEW/HOLD/REJECT                 APPROVE [-]                                                  Subtotal includes an un-itemised 15,000 row the parser drops
A02   LOOPHOLE critical     HOLD/REJECT                        APPROVE [-]                                                  Master bank line first, new account in a second line
A03   LOOPHOLE critical     HOLD/REJECT                        APPROVE [-]                                                  New bank account written with hyphens and no IFSC
A04   LOOPHOLE critical     HOLD/REJECT                        APPROVE [-]                                                  Invisible text layer carries the master account; visible tex
A05   LOOPHOLE critical     at most one paid                   APPROVE [-] | APPROVE [-]                                    Same invoice uploaded twice in one batch (race)
A06   LOOPHOLE high         REVIEW/HOLD/REJECT                 REVIEW [R10] | APPROVE [-]                                   Second invoice on a PO whose quantity is already claimed by 
A07   LOOPHOLE critical     REVIEW/HOLD/REJECT                 APPROVE [-]                                                  Credit note processed as an invoice
A07b  LOOPHOLE high         REVIEW                             APPROVE [-] | REJECT [R06]                                   Genuine K/1241 (sample SI-03) after the credit note was proc
A08   LOOPHOLE high         REVIEW/HOLD/REJECT                 APPROVE [-]                                                  Proforma invoice auto-approved
A09   LOOPHOLE critical     REVIEW/REJECT                      APPROVE [-]                                                  Line with no quantity column: price +20% passes
A10   LOOPHOLE medium       REVIEW/HOLD/REJECT                 APPROVE+NOTE [R10]                                           Line maths wrong (qty x rate != amount) by 1.9%
A11   LOOPHOLE medium       REVIEW                             APPROVE+NOTE [R10] | APPROVE+NOTE [R10] | APPROVE+NOTE [R10] Salami slicing: 3 invoices each +1.975% on unit price
A12   LOOPHOLE low          APPROVE+NOTE/REVIEW/REJECT         APPROVE [-]                                                  Tiny lines: unit price more than doubled, under the Rs 50 fl
A13   LOOPHOLE medium       REVIEW                             APPROVE [-] | APPROVE [-]                                    High-value invoice split in two to dodge the Rs 10 lakh mana
A14   LOOPHOLE medium       REVIEW                             APPROVE+NOTE [R07] | APPROVE+NOTE [R07]                      Implied-PO ceiling dodged by splitting (no PO number)
A15   LOOPHOLE high         REVIEW/REJECT                      APPROVE [-] | APPROVE+NOTE [R07]                             Same delivery re-billed a month later with a new number and 
A16   LOOPHOLE medium       REVIEW/HOLD                        APPROVE [-]                                                  Exact vendor name, no GSTIN anywhere on a tax invoice
A17   LOOPHOLE medium       REVIEW/HOLD                        APPROVE+NOTE [R07]                                           Invoice quotes a PO number that does not exist
A18   LOOPHOLE medium       REVIEW/HOLD/REJECT                 APPROVE [-]                                                  Invoice billed in USD but mentions INR elsewhere
B01   LOOPHOLE medium       REVIEW/APPROVE+NOTE                REJECT [R14]                                                 Legit invoice with a freight line between subtotal and total
B02   LOOPHOLE high         APPROVE                            REJECT [R13]                                                 Legit two-page invoice (table continues on page 2)
B03   LOOPHOLE low          APPROVE/APPROVE+NOTE               HOLD [R01]                                                   Legit invoice with no currency symbol anywhere
B04   LOOPHOLE medium       APPROVE/APPROVE+NOTE/REVIEW        REJECT [R13]                                                 Legit invoice with a returned-goods credit line in brackets
B07   LOOPHOLE low          APPROVE/APPROVE+NOTE               HOLD [R01]                                                   Legit invoice whose number is printed in lower case
B06   WEAK     low          HOLD/APPROVE                       APPROVE [-]  (notice says the bank changed from 1 Nov 2026,  Bank-change notice that repeats the same (master) account
K15   WEAK     high         HOLD/REJECT                        HOLD [R01,R07]  (a vendor statement is held as 'missing the  Statement of account (not an invoice)
W01   WEAK     low          APPROVE/APPROVE+NOTE               APPROVE+NOTE [R02]  (a clean text PDF is told 'some fields w Clean text invoice dated 10/11/2026 (normal Indian dd/mm dat
S02   UNTESTED critical     REJECT                             APPROVE [-] | failed: The Groq API could not be reached (HTT Re-scanned copy of an invoice already processed as a text PD
B05   OK       low          APPROVE                            APPROVE [-]                                                  Legit invoice saved with owner-only PDF permissions (no open
K01   OK       medium       APPROVE                            APPROVE [-]                                                  Clean Brightline invoice on PO-2026-1001
K02   OK       high         REVIEW/HOLD/REJECT                 REVIEW [R04]                                                 Valid vendor name with a different GSTIN
K03   OK       high         REVIEW/HOLD/REJECT                 REVIEW [R04]                                                 Lookalike vendor (homoglyph) with no GSTIN
K04   OK       high         HOLD/REJECT                        HOLD [R05]                                                   Lookalike vendor with its own GSTIN and bank
K05   OK       high         REJECT                             REJECT [R04]                                                 Blocked vendor
K06   OK       high         HOLD/REJECT                        HOLD [R04,R07]                                               Pending-onboarding vendor
K07   OK       high         REJECT/REVIEW                      REJECT [R08]                                                 Closed PO
K08   OK       high         REVIEW/HOLD/REJECT                 REVIEW [R07]                                                 PO belongs to another vendor
K09   OK       medium       HOLD                               HOLD [R03]                                                   Future-dated invoice
K10   OK       low          APPROVE+NOTE/REVIEW/HOLD           APPROVE+NOTE [R02]                                           Ambiguous dd/mm date where day-first is in the future
K11   OK       medium       REVIEW/HOLD/REJECT                 REVIEW [R08,R03]                                             Very old invoice (2 years)
K12   OK       critical     REJECT                             APPROVE [-] | REJECT [R06]                                   Resubmission with different separator and case
K13   OK       medium       REVIEW                             REVIEW [R15]                                                 Same 200 chairs on one invoice (control for A13)
K14   OK       critical     REVIEW/REJECT                      REJECT [R10]                                                 Prompt injection in a text PDF
K16   OK       low          APPROVE/APPROVE+NOTE/REVIEW/HOLD/R REVIEW [R10]                                                 Zero-value invoice (free replacement)
K17   OK       low          APPROVE/APPROVE+NOTE/REVIEW/HOLD/R REVIEW [R09]                                                 Extremely long fields
S01   OK       critical     HOLD/REJECT                        HOLD [R05]                                                   Prompt injection on an image-only scan (vision model)
U01   OK       low          upload rejected                    upload rejected: This PDF has 11 pages; the limit is 10.     11-page PDF
U02   OK       low          upload rejected                    upload rejected: File is larger than 10 MB.                  File over 10 MB
U03   OK       low          upload rejected                    upload rejected: This file could not be opened as a PDF. Ask Corrupt PDF
U04   OK       low          upload rejected                    upload rejected: Only PDF files are supported.               PNG renamed to .pdf
U05   OK       low          upload rejected                    upload rejected: This PDF is password protected. Ask the sen Password-protected PDF
------------------------------------------------------------------------------------------------------------------------------------------------------
Verdicts: LOOPHOLE 24, WEAK 3, UNTESTED 1, OK 23
```

Case-to-finding map: A01 C1; A02, A04 C2; A03 C3; A05 C4; A07, A07b, A08 C5; A09 C6; A06 H1; A15 H2; B02 H3; A10 M1; A11 M2;
A13, A14 M3; A16 M4; A17 M5; A18 M6; B01 M7; B04 M8; A12 L1; B03 L2; B07 L3; W01 L4; B06 L5; K15 L6.

## Findings, ranked

Severity: **critical** = money could be paid wrongly with no human touching it; **high** = money could be paid
wrongly after a normal approval, or a legitimate invoice is rejected with a false reason sent to the vendor;
**medium** = bounded leak, wrong-but-not-paid decision, or misleading reason; **low** = noise or cosmetic.

---

### C1. Critical: nothing checks that the line items add up to the subtotal (A01)

* **Repro:** `run.py --only A01` (`pdfs/A01_subtotal_gap.pdf`). Brightline, PO-2026-1001: one line, 10 chairs = ₹65,000,
  plus a table row "Delivery and installation (exempt)" with only an amount (₹15,000). Sub Total ₹80,000, CGST+SGST
  18% on ₹65,000 (₹11,700), Grand Total ₹91,700.
* **Actual:** Auto-approve, "everything checks out and it is safe to pay". The OK list says "Every line is on the PO",
  "Total adds up", "GST at 18% is calculated correctly". ₹15,000 that is on no PO is paid.
* **Expected:** Reject or Review: the lines sum to ₹65,000 but the subtotal says ₹80,000.
* **Root cause:** `backend/app/extract_text.py:272` keeps a table row only if it has an amount *and* a quantity or
  rate, so the amount-only row is silently dropped. No rule compares the line sum with the printed subtotal:
  `rules.py:729` (R14) uses the printed subtotal, `rules.py:644-649` (R13) taxes only the lines that were read, and
  R09/R10/R12 only see aligned lines. `normalize.py:191` computes `lines_ok` but uses it only to gate the
  confidence boost.
* **Fix:** add a "lines add up" check to R14 (|sum of line pre-tax amounts − subtotal| > ₹1 → REJECT, or HOLD when
  confidence is low), and keep amount-only rows as lines so R09 reports them as unordered. Effort: S (2-3 h incl. tests).

### C2. Critical: R05 compares only the first bank account on the page, including invisible text (A02, A04)

* **Repro:** `run.py --only A02,A04`. Corevolt CV-9131/CV-9133, perfect numbers on PO-2026-1008.
  A02 footer: the master account, then "For faster credit kindly remit to Riverbend Co-operative Bank A/c No:
  5020 0091 2334 7 IFSC: RVCB0000456". A04: the only *visible* bank line is Riverbend; an invisible
  (text render mode 3) line with the master account sits above it.
* **Actual:** both Auto-approve; R05 "Bank account ending 6789 on the invoice matches the account on file."
* **Expected:** Hold (EC4): the invoice asks us to pay an account we do not have.
* **Root cause:** `extract_text.py:403-414` (`parse_bank`) keeps the first account/IFSC it finds
  (`res["account"] or ...`) and ignores every later bank line; `matching.py:88-100` compares that one value.
  `pdfio.py:86` returns all words, including invisible render-mode-3 and white text, so a reader and the parser
  see different documents.
* **Fix:** collect every account number and IFSC in the document and HOLD if *any* differs from the master; ignore
  (and flag as suspicious) invisible or white text using PyMuPDF span flags/colour. Effort: M (half a day).

### C3. Critical: a new account the parser cannot read counts as "no bank details" (A03)

* **Repro:** `run.py --only A03`. Footer: "Remit to Riverbend Co-operative Bank, A/c 5020-0091-23347" (hyphens, no IFSC).
* **Actual:** Auto-approve; R05 "No bank details printed on the invoice. Nothing to compare." The bank name
  "Riverbend Co-operative Bank" *was* extracted.
* **Expected:** Hold: a different bank is named and an account is printed.
* **Root cause:** `extract_text.py:392` `ACCT_RE` accepts only digits and spaces; `matching.py:91` returns
  `not_applicable` when no account and no IFSC were parsed, even though a bank name was read and differs from the
  master; `rules.py:239-241` then passes.
* **Fix:** accept `-`/`.` separators; when a bank name or "remit/pay to ... A/c" text is present but no account parsed,
  or the bank name differs from the master, HOLD with "we could not read the bank details". Effort: S (1-2 h).

### C4. Critical: the same invoice uploaded twice in one batch is paid twice (A05)

* **Repro:** `run.py --only A05`: `pdfs/A05_copy1.pdf` and `A05_copy2.pdf` (byte-identical, GL-2390) in one
  multipart upload.
* **Actual:** both Auto-approve. Sequentially the system catches it (K12: the re-sent copy is Rejected by R06).
* **Expected:** the second copy Rejected as a duplicate (exact file hash and exact number).
* **Root cause:** each file in an upload starts its own background thread (`main.py:202`, `main.py:58-65`). The
  duplicate check only looks at invoices that already have a decision: `matching.py:182-184` (hash) and
  `matching.py:165` (`current_decision_id IS NOT NULL`), and the decision id is written only at stage 9
  (`pipeline.py:661`). Two runs in flight never see each other.
* **Fix:** serialise stages 5-8 per vendor (a per-vendor lock around duplicate check + decision), or have stage 5
  also compare against in-flight invoices by sha256 / canonical number; back it with a uniqueness check on
  (vendor, canonical number) for non-rejected invoices. Effort: M (half a day).

### C5. Critical: credit notes and proforma invoices are paid as invoices (A07, A07b, A08; also K15)

* **Repro:** `run.py --only A07,A07b,A08`.
  A07: Kestrel "CREDIT NOTE" CN/26/014 "Against Invoice No: K/1241", 500 cartons, ₹23,600.
  A07b: the same credit note, then the genuine invoice K/1241 (sample SI-03).
  A08: Greenleaf "PROFORMA INVOICE" PI/2026/077 ("tax invoice will be issued on dispatch").
* **Actual:** A07 Auto-approve (we would *pay* the vendor the credit they owe us). A07b: the credit note is
  approved, then the real K/1241 is **Rejected** "we have already received an invoice with this number" (R06), so
  the genuine EC1 review never happens and a return notice goes to the vendor. A08 Auto-approve (an advance
  request paid with no tax invoice).
* **Expected:** credit note: never a payable (route to AP as a credit, or Hold); proforma: Hold/Review.
* **Root cause:** there is no document-type check. `extract_text.py:83` (`LBL_INVNO`) matches "Against Invoice
  No" and "Proforma Invoice No"; `pdfio.py:9` (`INVOICE_WORDS`) matches any "invoice"; `pipeline.py:359-361`
  marks a file "not an invoice" only when it has neither a number nor a total. The document title is used only to
  skip it as a vendor name (`extract_text.py:425`). In A07b, `matching.py:199-204` then matches the real invoice
  to the approved credit note by number. K15 (a statement of account) is held, but for the wrong reason: "the
  invoice is missing the invoice number".
* **Fix:** classify the document title/keywords (credit note, debit note, proforma, quotation, statement,
  delivery challan) at stage 2; anything but a tax invoice/bill of supply gets HOLD with a doc-type headline; credit
  notes are stored as credits against the referenced invoice. Effort: S-M (3-4 h).

### C6. Critical: a line without a quantity skips the price and quantity checks (A09)

* **Repro:** `run.py --only A09`. Kestrel K/1250 on PO-2026-1004, table columns Description | Item Code | Rate |
  Amount: carton CTN-L at **₹48.00** (PO ₹40, +20%), amount ₹96,000.
* **Actual:** Auto-approve. R10 says "Price per carton ₹0.00 matches the PO"; the OK list says "Price per carton
  matches (₹40)". 2,000 cartons' worth is billed at 20% over.
* **Expected:** Reject (price +20%), or at least Review "quantity not readable".
* **Root cause:** `rules.py:484-490`: `q = l.get("qty") or 0` makes `expected = 0`, then `pct = 0.0`, and
  `band()` (`rules.py:39`) returns PASS for 0%. `matching.py:434` allocates quantity 0, so R11 also passes. The
  rate printed on the line (₹48) is never compared with the PO.
* **Fix:** when qty is missing, derive it from amount ÷ rate; if it cannot be derived, R10/R11 return REVIEW
  ("quantity not readable"), never PASS; compare the printed rate with the PO rate as well. Effort: S (1-2 h).

---

### H1. High: invoices waiting in Review or Hold do not use up the PO (A06)

* **Repro:** `run.py --only A06`. Corevolt CV-9140 bills all 30 docks and 30 keyboard sets on PO-2026-1002 (keyboard
  price +3%, goes to Review). CV-9147, five days later, bills 30 docks again.
* **Actual:** CV-9140 Review; CV-9147 **Auto-approve** ("Quantities are within what is left on the order"). When the
  reviewer approves CV-9140 (it only has a 3% price issue), 60 docks have been paid against 30 ordered.
* **Expected:** CV-9147 Review: the PO's remaining quantity is already claimed by a pending invoice.
* **Root cause:** `matching.py:254-266` puts Review/Hold invoices in a separate `pending` bucket and
  `matching.py:272` computes `remaining_qty = ordered - billed` without it; `rules.py:557` (R11) and
  `rules.py:600` (R12) use only billed. Spec §2.3 says billed includes held and review invoices ("shown separately").
* **Fix:** R11/R12 compare against `ordered − billed − pending` (or at least REVIEW when this + pending exceeds the PO),
  and name the pending invoice in the message. Effort: S (1-2 h).

### H2. High: the same delivery re-billed a month later with a new number and no PO is paid again (A15)

* **Repro:** `run.py --only A15`. BLS/26-27/0590 (10 toner cartridges, PO-2026-0985, dated 10 Oct) is approved; the
  identical lines come back as BLS/26-27/0655 dated 14 Nov with the PO number left off.
* **Actual:** Approve with note (R07: "matched this invoice to a purchase order that the vendor did not mention").
  R06 passes.
* **Expected:** Review as a possible duplicate (same vendor, same items and quantities, same amount).
* **Root cause:** `matching.py:152-155`: the "recurring-charge guard" zeroes the number and date signals for any two
  invoices with different serials 25+ days apart, for goods as well as services. The PO signal is 0 because stage 5
  only uses an explicitly printed PO (`pipeline.py:497-499`); the implied PO is found later at stage 6. Score = 0.30
  (amount) + 0.20 (lines) = 0.50 < 0.60.
* **Fix:** apply the guard only when the line fingerprints differ (or to vendors flagged as recurring/service);
  re-score duplicates after PO resolution using the implied PO. Effort: S-M (2-4 h).

### H3. High: a legitimate two-page invoice is rejected as "GST is wrong" (B02)

* **Repro:** `run.py --only B02`. Brightline BLS/26-27/0702: 4 chairs on page 1, 3 desks plus totals on page 2.
* **Actual:** Reject (R13): "GST shown is ₹11,160 but 18% of ₹26,000 is ₹4,680", and a return notice telling the
  vendor its GST is wrong. The GST is right.
* **Expected:** Auto-approve.
* **Root cause:** `extract_text.py:263`: the line table stops at the first page break (`if r.page != row.page: break`),
  so page-2 lines are never read; R13 then taxes only page 1.
* **Fix:** continue the table on later pages (same columns, or a repeated header); with C1's lines-vs-subtotal check
  the explanation would also say "we could not read all lines" instead of blaming the vendor. Effort: M (half a day).

---

### M1. Medium: line arithmetic is never checked; the explanation invents a unit price (A10)

* **Repro:** `run.py --only A10`. 10 chairs × ₹6,500.00 printed, line amount ₹66,235.00 (+1.9%); subtotal, GST and
  total follow the wrong amount.
* **Actual:** Approve with note: "Price per chair is ₹6,623.50 against ₹6,500.00", a price that is printed nowhere.
* **Expected:** Reject or Review: the invoice's own arithmetic is wrong.
* **Root cause:** `rules.py:484-488` uses only the line amount; the printed rate is used only when the amount is
  missing (`normalize.py:132-135`).
* **Fix:** flag |qty × rate − amount| > ₹1 as an arithmetic error (REJECT, or HOLD when low confidence). Effort: S.

### M2. Medium: salami slicing just under the 2% price band (A11)

* **Repro:** `run.py --only A11`: three Kestrel invoices, 700/800/900 cartons at ₹40.79 (PO ₹40, +1.98%).
* **Actual:** Approve with note, three times; ₹1,896 overpaid plus GST, and the pattern is never escalated.
* **Expected:** the second or third repeat from the same vendor on the same PO line goes to Review.
* **Root cause:** `rules.py:477-538` (R10) judges each invoice alone; R12 only fires once the PO value is exceeded,
  so a vendor that never bills the last ~2% of the quantity is never caught.
* **Fix:** keep cumulative price variance per PO line; REVIEW when the summed overcharge exceeds the note cap or the
  note band is used repeatedly. Effort: M.

### M3. Medium: splitting an invoice dodges the ₹10 lakh manager cap and the ₹1 lakh implied-PO ceiling (A13, A14)

* **Repro:** `run.py --only A13,K13,A14`. A13: a new PO for 200 chairs (₹13 lakh) billed as 90 + 110 chairs, same
  day, consecutive numbers. K13 (control): the same 200 chairs on one invoice. A14: Greenleaf tea and sugar worth
  ₹1,02,816 with no PO number, sent as two invoices.
* **Actual:** A13 both Auto-approve (₹15.3 lakh with no manager); K13 Review (R15) as designed. A14 both Approve with
  note on an inferred PO (one invoice would be Review).
* **Expected:** the second half goes to Review (manager).
* **Root cause:** `rules.py:755-766` (R15) and `rules.py:356-358` (R07 ceiling) look at one invoice's gross only.
* **Fix:** apply both caps to the sum of the same vendor's invoices on the same PO (or with no PO) within e.g. 7 days.
  Effort: S-M.

### M4. Medium: a tax invoice with no supplier GSTIN passes on the name alone (A16)

* **Repro:** `run.py --only A16`. Brightline name, master bank, no vendor GSTIN anywhere.
* **Actual:** Auto-approve ("Vendor approved (matched by name)").
* **Expected:** Review or Hold: without the supplier's GSTIN the input tax credit is lost and identity is unconfirmed.
* **Root cause:** `matching.py:58-64` returns an exact-name match with no conflict when the GSTIN is absent;
  `rules.py:220` passes it.
* **Fix:** missing supplier GSTIN on an invoice that charges GST → REVIEW (or HOLD asking for a corrected invoice). Effort: XS.

### M5. Medium: an invoice quoting a PO that does not exist is matched silently, and the explanation says it had no PO (A17)

* **Repro:** `run.py --only A17`. Greenleaf GL-2410 prints "PO Ref: PO-2026-1099" (no such PO); items match PO-2026-1005.
* **Actual:** Approve with note, R07 "No PO number on the invoice. PO-2026-1005 is the best match at 100%".
* **Expected:** Review: the vendor cited a PO we do not have; the reason must say so.
* **Root cause:** `matching.py:333-363` falls through to implied matching when the reference is unknown;
  `rules.py:359-363` ignores `reference_not_found`.
* **Fix:** a printed but unknown reference → REVIEW at least, message "The invoice quotes PO-2026-1099, which we
  do not have". Effort: XS.

### M6. Medium: an invoice in USD is treated as INR if "INR" appears anywhere (A18)

* **Repro:** `run.py --only A18`. Header "Currency: USD", "Grand Total (USD)"; the bank line says "(INR account)".
* **Actual:** Auto-approve as INR; R16 passes.
* **Expected:** Review (R16, currency differs from the PO).
* **Root cause:** `extract_text.py:472-476`: any ₹/INR/Rs anywhere wins over USD; there is no "Currency:" label check.
* **Fix:** read an explicit currency label and the symbol next to the total first; conflicting currencies → REVIEW.
  Effort: S.

### M7. Medium: a legitimate freight or discount line makes the invoice "not add up" and it is rejected (B01)

* **Repro:** `run.py --only B01`. Sub Total ₹65,000 + GST ₹11,700 + "Freight charges ₹1,500" = ₹78,200.
* **Actual:** Reject (R14) "the invoice total does not add up ... off by ₹1,500", return notice to the vendor.
* **Expected:** Review (freight is not on the PO) or Approve with note; the total does add up.
* **Root cause:** `extract_text.py:531` hard-codes `other_charges` and `discount` to None, and `parse_totals`
  (`extract_text.py:380-386`) skips rows without a known label; R14 (`rules.py:729`, `rules.py:744`) then rejects.
* **Fix:** parse labelled charge rows (freight, packing, insurance, round off, discount) into `other_charges` /
  `discount`, and send unordered charges through R09 as REVIEW. Effort: S-M.

### M8. Medium: a returned-goods line in brackets is read as a charge, so a correct invoice is rejected (B04)

* **Repro:** `run.py --only B04`. 10 chairs ₹65,000 and "Less: returned chairs (2) ... (13,000.00)"; Sub Total ₹52,000.
* **Actual:** Reject (R13) "GST shown is ₹9,360 but 18% of ₹78,000 is ₹14,040".
* **Expected:** Approve (8 chairs) or Review.
* **Root cause:** `extract_text.py:74-76` (`MONEY_RE`) drops the brackets/minus, and `textutil.py:52-62`
  (`parse_number`) reads "(2)" as 2, so the credit line is added instead of subtracted.
* **Fix:** keep the sign for bracketed or minus amounts and quantities; treat negative lines as credits. Effort: S.

---

### L1. Low: the ₹50 "exact enough" floor is per line, so tiny lines can more than double in price (A12)

* **Repro:** `run.py --only A12`. Five lines of 100 wooden stirrers at ₹0.89 (PO ₹0.40, +122%).
* **Actual:** Auto-approve (each line is ₹49 over). **Expected:** Approve with note or Review.
* **Root cause:** `rules.py:39` applies `pass_abs` per line; `matching.py:409` lets several invoice lines match the
  same PO line by SKU (the `used` set is not checked).
* **Fix:** apply the ₹50 floor to the invoice total of line deltas and cap it by a percentage. Effort: XS.

### L2. Low: a domestic invoice with no currency symbol is held (B03)

* **Repro:** `run.py --only B03` ("Grand Total 76,700.00", no ₹/Rs/INR). **Actual:** Hold "the invoice is missing the
  currency". **Expected:** Approve (Indian GST invoice, INR PO).
* **Root cause:** `extract_text.py:472-476`, `rules.py:104`. **Fix:** default to the PO currency when no other currency
  is printed, with a note. Effort: XS.

### L3. Low: lower-case invoice numbers are not read (B07)

* **Repro:** `run.py --only B07` ("bls/26-27/0675"). **Actual:** Hold "the invoice is missing the invoice number".
  **Expected:** Approve.
* **Root cause:** `extract_text.py:80` `INVNO_RE` only matches upper-case letters and has no `re.I`.
* **Fix:** make it case-insensitive. Effort: XS.

### L4. Low (weak): clean text invoices with a normal dd/mm date are told "some fields were hard to read" (W01, K10)

* **Repro:** `run.py --only W01` (date "10/11/2026" on a clean text PDF).
* **Actual:** Approve with note, headline "some fields were hard to read, but the numbers check out". Any dd/mm date
  with a day of 12 or less does this, so most Indian invoices lose straight-through status for no reason.
* **Expected:** Auto-approve (the setting says "Day first") or a note that says "the date could be read two ways".
* **Root cause:** `textutil.py:147-158` marks every both-valid date ambiguous; `normalize.py:103-105` caps it at 0.80;
  `rules.py:139-143` uses a "hard to read" headline. **Fix:** with "Day first" configured and the day-first reading
  valid and not in the future, do not cap; use a date-specific headline otherwise. Effort: XS.

### L5. Low (weak): a "bank details have changed" notice with the old account is approved as a "verified change" (B06)

* **Repro:** `run.py --only B06`. Greenleaf: "our bank details have changed with effect from 1 Nov 2026" followed by
  the master account.
* **Actual:** Auto-approve; R05 "The new account ending 5508 matches the vendor record, which Rahul Mehta verified
  on 30 Sep 2025". The account is the old one, and the verification predates the notice by 13 months.
* **Expected:** Hold (the vendor says it has a new account we do not have) or at least an honest message.
* **Root cause:** `matching.py:101-104` treats any old verification as covering a new notice; `rules.py:245-250`
  writes "new account". **Fix:** only accept as verified when the verification date is on or after the notice date.
  Effort: XS.

### L6. Low (weak): a statement of account is held as "missing the invoice number" (K15)

* **Repro:** `run.py --only K15`. **Actual:** Hold "the invoice is missing the invoice number" (R01, R07, R09).
  **Expected:** Hold "this is a statement, not an invoice". **Root cause / fix:** as C5 (`pipeline.py:359-361`).

---

## What held up (OK cases)

Blocked vendor (K05) Reject; pending vendor (K06) Hold; closed PO (K07) Reject; another vendor's PO (K08) Review;
same name with a different GSTIN (K02) Review; homoglyph name (K03) Review; lookalike with its own GSTIN and bank
(K04) Hold; future date (K09) Hold; 2-year-old invoice (K11) Review; re-sent invoice with a different separator (K12)
Reject; split-free ₹13 lakh invoice (K13) Review by manager; prompt injection on a text PDF (K14, the parser ignores
it and R10 rejects the +15% price); prompt injection on an image-only scan (S01, the vision model reported the
printed Riverbend account and R05 held it); zero-value (K16) and 300-character fields (K17) do not crash;
11 pages, >10 MB, corrupt, PNG-renamed and password-protected uploads (U01-U05) are refused with clear messages;
an owner-password-only PDF (B05) is accepted.

## What could not be tested, and caveats

* **Scan re-submission (S02) is UNTESTED.** In all three runs, including one with a 65 s pause before the scan, Groq
  refused the extraction call: "HTTP 429 ... output tokens per minute (OTPM): Limit 1000, Requested 1049". A single
  request asks for more output than the free tier allows per minute, so waiting does not help; the run fails with Retry
  (the designed behaviour). Whether a re-scan of an approved invoice is caught could not be observed. Operational note:
  on this tier, any scan whose extraction needs more than ~1,000 output tokens can never be read
  (`extract_llm.py:113`, `GROQ_MAX_TOKENS = 8000`, is far above the tier's OTPM). Only 2 scans were run, per the budget.
* Text PDFs were run with AI switched off (the default for text PDFs is the deterministic parser anyway). With
  `LEDGERLIGHT_EXTRACTION=llm`, text PDFs would go to the model; prompt injection there was not tested.
* Explanation "AI polish" was off in the text phase, so headlines are the template wording.
* The duplicate race (C4) depends on timing; with `pace=instant` it reproduced on every run. At normal pacing the
  window is wider, not narrower.
