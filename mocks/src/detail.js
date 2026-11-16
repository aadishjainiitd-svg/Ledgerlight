/* ===== Builds the full detail model for one invoice (fields, rules, PO match, vendor, duplicate, drafts) ===== */
const BAND_NOTE = 'allowed: up to 0.5% or ₹50 passes; up to 2% and ₹5,000 gets a note';
function PR(il, pl, ord, bb, ti, pp, ip, note) {
  const rem = ord - bb, over = Math.max(0, ti - rem), dp = pp ? (ip - pp) / pp : 0;
  const av = over * pp + ti * (ip - pp);
  let sev = 'pass';
  if (ti === 0) sev = 'none';
  else if (over > 0) { const p = over / ord; sev = p <= 0.005 ? 'pass' : p <= 0.02 && over * pp <= 5000 ? 'note' : p <= 0.10 ? 'review' : 'reject'; }
  else if (Math.abs(dp) > 0.005) sev = Math.abs(dp) <= 0.02 ? 'note' : Math.abs(dp) <= 0.10 ? 'review' : 'reject';
  return { il, pl, ord, bb, ti, rem, pp, ip, dp, av, sev: note && note.sev || sev, over, note: note && note.t };
}
const NAMED_ROWS = {
  bl0377: () => [PR('Copier paper A4 75gsm', 'CP-A4-75', 400, 0, 400, 250, 250)],
  k1187: () => [PR('Corrugated shipping carton, large', 'CTN-L', 10000, 0, 4000, 40, 40), PR('Custom print setup', 'SETUP-01', 1, 0, 1, 20000, 20000)],
  k1203: () => [PR('Corrugated shipping carton, large', 'CTN-L', 10000, 4000, 3500, 40, 40), PR('', 'SETUP-01', 1, 1, 0, 20000, 20000)],
  si01: () => [PR('Ergonomic mesh chair', 'CH-ERG-01', 40, 0, 40, 6500, 6500), PR('Height-adjustable standing desk', 'DK-STD-02', 20, 0, 20, 12000, 12000)],
  si02: () => [PR('IT peripherals supply (bundle)', 'DS-USB-C + KM-W1', 60, 0, 60, 4500, 4567.5, { sev: 'note', t: 'Bundle matched across 2 PO lines: 30 docking stations at ₹7,200 plus 30 keyboard-mouse sets at ₹1,800. Billed ₹2,74,050 against ₹2,70,000.' })],
  si03: () => [PR('Corrugated shipping carton, large', 'CTN-L', 10000, 7500, 3000, 40, 40), PR('', 'SETUP-01', 1, 1, 0, 20000, 20000)],
  si04: () => [PR('Copier paper A4 75gsm', 'CP-A4-75', 400, 400, 400, 250, 250)],
  si05: () => [PR('Tea premix', 'PNT-TEA', 200, 0, 150, 420, 420), PR('Sugar', 'PNT-SUG', 300, 0, 250, 48, 48)],
  si06: () => [PR('24-port managed switch', 'NS-24P', 6, 0, 6, 21000, 21000), PR('Cat6 patch cable 2 m', 'PC-CAT6', 60, 0, 60, 250, 250)],
  si07: () => [PR('Full-truck freight Mumbai to Pune', 'FR-MUM-PUN', 12, 0, 12, 14500, 14500)],
};

function synRule(inv) {   /* which single rule drives a synthetic invoice */
  const o = inv.outcome, c = inv.cat, r = inv.reason;
  if (o === 'auto') return null;
  if (o === 'note') { const id = /Price/.test(r) ? 'R10' : /PO inferred/.test(r) ? 'R07' : /Quantity/.test(r) ? 'R11' : /GST/.test(r) ? 'R13' : /older/.test(r) ? 'R03' : 'R02'; return [id, 'note', r]; }
  if (c === 'Quantity or price above PO') return [/Quantity|boxes|trips/.test(r) ? 'R11' : 'R10', o, r];
  if (c === 'Duplicate') return ['R06', o, r];
  if (c === 'Vendor problem') return [/PO belongs/.test(r) ? 'R07' : 'R04', o, r];
  if (c === 'Tax or total') return ['R13', o, r];
  if (c === 'Missing information') return [/date/.test(r) ? 'R01' : /Total/.test(r) ? 'R02' : 'R07', o, r];
  if (c === 'Bank change') return ['R05', o, r];
  return ['R02', o, r];
}

function defRule(id, inv, d) {
  const v = V(inv.vendor), g = inv.gross;
  const M = {
    R01: 'Invoice number, date, vendor, total and currency are all present.',
    R02: `All key fields were read with confidence of 0.90 or more (lowest ${inv.conf.toFixed(2)}).`,
    R03: `Invoice date ${inv.date} is not in the future and is after the PO date.`,
    R04: `${v.short} is an approved vendor (matched by GSTIN ${v.gstin}).`,
    R05: v.acct ? `Bank account ending ${v.acct.slice(-4)} on the invoice matches the account on file.` : 'No bank details on the invoice. Nothing to compare.',
    R06: `Not similar to any earlier invoice (highest similarity ${d.dup.score.toFixed(2)}, allowed below 0.60).`,
    R07: `${inv.po} was written on the invoice and belongs to ${v.short}.`,
    R08: `${inv.poInferred || inv.po} is open and the invoice date is inside its validity window.`,
    R09: 'Every invoice line maps to a line on the PO.',
    R10: 'Unit prices match the PO.',
    R11: 'Quantities are within what remains on the PO.',
    R12: 'Invoice value fits within the PO value remaining.',
    R13: `GST of ${inr(inv.tax)} is correct at ${inv.rate}%.`,
    R14: `Subtotal ${inr(inv.sub)} plus tax ${inr(inv.tax)} equals the total ${inr(g)}.`,
    R15: g > 1000000 ? `Total ${inr(g)} is above ₹10,00,000 so a manager must sign off.` : `Total ${inr(g)} is below the ₹10,00,000 manager sign-off limit.`,
    R16: 'Invoice currency (INR) matches the PO currency.',
  };
  return M[id];
}
const ALLOWED = { R10: 'Allowed: 0.5% or ₹50 passes; 2% and ₹5,000 notes', R11: 'Allowed: 0.5% passes; 2% notes', R12: 'Allowed: 0.5% or ₹50 passes; 2% and ₹5,000 notes', R13: 'Allowed: ₹1 passes; ₹10 notes', R14: 'Allowed: ₹1 passes; ₹10 notes', R06: 'Review at 0.60, reject at 0.85', R02: 'Fine at 0.90, note at 0.75', R15: 'Limit ₹10,00,000' };

function buildDetail(inv) {
  if (inv._d) return inv._d;
  const d = { inv };
  const v = V(inv.vendor), sc = inv.doc === 'scanned';
  const hi = i => Math.min(0.99, 0.965 + (i % 4) * 0.007);

  /* ---- fields ---- */
  const lowKey = { si04: 'inv', si05: 'date' }[inv.key] || 'total';
  const F = [
    { k: 'vendor', label: 'Vendor', val: inv.vfull }, { k: 'inv', label: 'Invoice no.', val: inv.invNo }, { k: 'date', label: 'Invoice date', val: inv.date },
    { k: 'po', label: 'PO reference', val: inv.po === '—' ? 'Not found' : inv.po }, { k: 'cur', label: 'Currency', val: 'INR' },
    { k: 'sub', label: 'Subtotal', val: inr2(inv.sub) }, { k: 'tax', label: `Tax (GST ${inv.rate}%)`, val: inr2(inv.tax) }, { k: 'total', label: 'Total', val: inr2(inv.gross) },
  ].map((f, i) => {
    const base = sc ? 0.92 + (i % 3) * 0.015 : hi(i);
    f.conf = f.k === lowKey && inv.conf < 0.9 ? inv.conf : Math.max(base, inv.conf < 0.9 ? 0.9 : inv.conf);
    f.mc = f.conf; f.src = sc ? 'image read' : 'text layer'; if (['sub', 'tax', 'total'].includes(f.k) && !sc) f.src = 'text layer'; return f;
  });
  const FF = k => F.find(f => f.k === k);
  if (inv.key === 'si02') {
    Object.assign(FF('po'), { raw: 'Ref your PO 1002/2026', src: 'normalised from text', why: 'Written as "1002/2026" in the narrative. Matched PO-2026-1002 by serial and year.' });
    Object.assign(FF('sub'), { src: 'calculated', why: 'Prices were tax-inclusive. Backed out GST: ₹3,23,379 ÷ 1.18 = ₹2,74,050.' }); Object.assign(FF('tax'), { src: 'calculated' });
  }
  if (inv.key === 'si04') Object.assign(FF('inv'), { raw: 'BL-0377-26', src: 'image read', why: 'The photo is skewed and the last digits are soft. Canonical form BL-377 (serial token 377).' });
  if (inv.key === 'si05') {
    Object.assign(FF('date'), { raw: '12/11/26', mc: 0.80, why: '12/11/26 could mean 12 Nov or 11 Dec. 11 Dec 2026 is in the future, so we read it as 12 Nov 2026.', amber: true });
    Object.assign(FF('po'), { conf: null, raw: 'Not found', val: 'Not found', why: 'A RECEIVED stamp covers the PO field. Inferred PO-2026-1005 instead (see PO match).', src: 'not on invoice' });
    Object.assign(FF('total'), { raw: '₹78,7?0', mc: 0.78, conf: 0.92, boost: true, amber: false, why: 'OCR 0.78 raised to 0.92 because the lines plus tax equal the total.' });
    Object.assign(FF('sub'), { mc: 0.83, conf: 0.90, boost: true, why: 'Raised to 0.90 because the lines add up to this subtotal.' });
    Object.assign(FF('tax'), { mc: 0.81, conf: 0.90, boost: true, why: 'Raised to 0.90 because subtotal plus tax equals the total.' });
    Object.assign(FF('inv'), { conf: 0.91 }); Object.assign(FF('vendor'), { conf: 0.96, why: 'Letterhead is legible, so the vendor matches exactly.' });
  }
  if (inv.key === 'si06') F.push({ k: 'bankn', label: 'Bank change notice', val: 'Found in footer', conf: 0.96, mc: 0.96, src: 'text layer', why: '"Our bank details have changed with effect from 1 Nov 2026."' });
  if (inv.cat === 'Missing information' && /date/.test(inv.reason || '')) Object.assign(FF('date'), { val: 'Missing', conf: null, src: 'not on invoice' });
  F.forEach(f => { if (f.conf != null && f.conf < 0.9 && !f.why) { f.why = 'Low confidence read. Check this value against the document.'; f.amber = true; } if (f.conf != null && f.conf < 0.9) f.amber = f.amber !== false; });
  d.fields = F;
  d.lowest = Math.min(...F.filter(f => f.conf != null).map(f => f.conf));

  /* ---- lines ---- */
  d.lines = (inv.items || []).map(l => ({ desc: l[0], qty: l[1], uom: l[2], price: l[3], amt: l[4], rate: l[5] }));

  /* ---- PO panel ---- */
  const poId = inv.poInferred || inv.po; const po = PO(poId);
  let rows = NAMED_ROWS[inv.key] ? NAMED_ROWS[inv.key]() : null;
  if (!rows && po) {
    const l = inv.items[0], pl = po.lines[0]; const ord = Math.ceil(l[1] * 1.7), bb = Math.round(l[1] * 0.4); let ti = l[1], ip = pl[4];
    if (inv.cat === 'Quantity or price above PO' && /Quantity|boxes|trips/.test(inv.reason)) ti = ord - bb + 14;
    if (inv.cat === 'Quantity or price above PO' && !/Quantity|boxes|trips/.test(inv.reason)) ip = pl[4] * (inv.outcome === 'reject' ? 1.14 : /3\.1/.test(inv.reason) ? 1.031 : 1.042);
    rows = [PR(l[0], pl[0], ord, bb, ti, pl[4], ip)];
  }
  d.rows = rows || [];
  const beforeVal = sum(d.rows.map(r => r.bb * r.pp)), thisVal = sum(d.rows.map(r => r.ti * r.ip)), totalVal = po ? poSub(po) : (sum(d.rows.map(r => r.ord * r.pp)) || inv.sub);
  d.cum = { before: beforeVal / totalVal * 100, after: (beforeVal + thisVal) / totalVal * 100, beforeVal, thisVal, totalVal };
  const implied = !!inv.poInferred;
  d.po = { id: poId, obj: po, method: implied ? 'Implied' : 'Explicit', score: implied ? 0.96 : 1, runner: implied ? 0.14 : null,
    cands: implied ? [
      { id: 'PO-2026-1005', score: 0.96, parts: [['Item descriptions', 0.89, 0.35], ['Unit prices within 2%', 1, 0.30], ['Quantities fit remaining', 1, 0.15], ['Total fits remaining', 1, 0.10], ['PO date window', 1, 0.10]], note: 'Tea premix and sugar, prices match exactly, 150 kg of 200 and 250 kg of 300 remain.' },
      { id: 'PO-2026-1007', score: 0.14, parts: [['Item descriptions', 0.10, 0.35], ['Unit prices within 2%', 0, 0.30], ['Quantities fit remaining', 0, 0.15], ['Total fits remaining', 0, 0.10], ['PO date window', 1, 0.10]], note: 'Paper cups and stirrers. No items in common; the invoice total exceeds this PO.' },
    ] : null };

  /* ---- vendor ---- */
  const bankBad = inv.key === 'si06';
  d.vendorP = { v, bankInv: inv.key === 'si05' ? null : bankBad ? { bank: 'Riverbend Co-operative Bank', acct: '5020 0091 2334 7', ifsc: 'RBCB0000412' } : { bank: v.bank, acct: v.acct, ifsc: v.ifsc }, bankFile: { bank: v.bank, acct: v.acct, ifsc: v.ifsc }, match: bankBad ? false : true, method: 'GSTIN match (decisive)' };
  if (inv.cat === 'Vendor problem' && inv.outcome === 'review' && /name only/.test(inv.reason)) d.vendorP.method = 'Fuzzy name match only (GSTIN differs)';
  if (/pending/i.test(inv.reason || '')) d.vendorP.status = 'Pending onboarding';

  /* ---- duplicate ---- */
  const prior = RUNS.filter(r => r.vendor === inv.vendor && r !== inv && r.time < inv.time).sort((a, b) => b.time - a.time)[0] || RUNS.find(r => r.vendor === inv.vendor && r !== inv);
  let dup = { score: 0.08 + ((inv.invNo.length * 7) % 17) / 100, closest: prior, sigs: null };
  if (inv.key === 'si04') {
    const o = INV.bl0377; dup = { score: 1, closest: o, exact: false, sigs: [
      ['Total amount', '30%', inr2(inv.gross), inr2(o.gross), true, '1.00'], ['Invoice number', '25%', 'BL-0377-26', 'BL/2026/0377', true, '1.00', 'Same prefix BL, same serial token 377'], ['Invoice date', '15%', inv.date, o.date, true, '1.00'], ['PO reference', '10%', inv.po, o.po, true, '1.00'], ['Line items', '20%', '400 reams copier paper at ₹250', '400 reams copier paper at ₹250', true, '1.00'] ] };
  } else if (inv.cat === 'Duplicate') {
    dup = { score: inv.outcome === 'reject' ? 1 : 0.72, closest: prior, exact: inv.outcome === 'reject', sigs: inv.outcome === 'reject' ? null : [['Total amount', '30%', inr2(inv.gross), inr2(inv.gross), true, '1.00'], ['Invoice number', '25%', inv.invNo, prior ? prior.invNo : '', false, '0.55'], ['Invoice date', '15%', inv.date, prior ? prior.date : '', false, '0.50'], ['PO reference', '10%', inv.po, inv.po, true, '1.00'], ['Line items', '20%', 'Same items', 'Partly the same', false, '0.55']] };
  }
  d.dup = dup;

  /* ---- rules ---- */
  const sr = inv.synth ? synRule(inv) : null; const rv = Object.assign({}, inv.rv);
  if (sr) rv[sr[0]] = [sr[1], sr[2]];
  if (inv.cat === 'Missing information' && !inv.synth) { }
  d.rules = RULES.map(r => { const o = rv[r.id]; return { id: r.id, name: r.name, stage: r.stage, hard: r.hard, sev: o ? o[0] : 'pass', msg: o ? o[1] : defRule(r.id, inv, d), allowed: ALLOWED[r.id] }; });
  d.sev = worst(d.rules.map(r => r.sev));
  d.stageSev = n => worst(d.rules.filter(r => r.stage === n).map(r => r.sev));

  /* ---- explanation ---- */
  const dr = d.rules.filter(r => r.sev !== 'pass').sort((a, b) => SEVRANK[b.sev] - SEVRANK[a.sev]);
  d.headline = inv.headline || ({
    auto: 'Approved: everything checks out and it is safe to pay.',
    note: 'Approved with a note: ' + (inv.reason || '').replace(/\.$/, '').replace(/^./, c => c.toLowerCase()) + '.',
    review: 'Review needed: ' + (inv.reason || '').replace(/\.$/, '').replace(/^./, c => c.toLowerCase()) + '.',
    hold: 'Hold: ' + (inv.reason || '').replace(/\.$/, '').replace(/^./, c => c.toLowerCase()) + '.',
    reject: 'Reject: ' + (inv.reason || '').replace(/\.$/, '').replace(/^./, c => c.toLowerCase()) + '.' })[inv.outcome];
  d.ok = inv.ok || [`${v.short} is an approved vendor`, `${poId} found and open`, 'Prices, quantities, GST and total match', 'Not a duplicate'].filter((x, i) => !(sr && ((sr[0] === 'R04' && i === 0) || (sr[0] === 'R06' && i === 3))));
  d.attention = inv.attention || (dr.length ? dr.slice(0, 2).map(r => r.msg) : []);
  d.next = inv.next || ({ auto: 'None needed. The invoice is in the payment queue.', note: 'None needed. The invoice is in the payment queue with the note attached.', review: inv.rec ? inv.rec + '.' : 'Review the evidence and accept or override.', hold: inv.rec ? inv.rec + '.' : 'Chase the vendor for the missing information. The invoice re-runs when it arrives.', reject: inv.rec ? inv.rec + '.' : 'Send the return notice. Nothing is paid.' })[inv.outcome];
  d.confNote = inv.key === 'si05' ? 'Three fields were below 0.90 before arithmetic checks. The total is trusted because lines plus tax equal it.' : (d.lowest < 0.9 ? `Lowest field confidence is ${d.lowest.toFixed(2)}. Check the amber fields.` : `All fields read at ${d.lowest.toFixed(2)} or higher.`);

  /* ---- drafts ---- */
  d.draft = draftFor(inv, v);

  /* ---- stage messages for the live view ---- */
  d.stageMsg = stageMsgs(inv, d);
  inv._d = d; return d;
}

function draftFor(inv, v) {
  if (inv.key === 'si06') return { kind: 'verify', title: 'Drafted vendor verification request', to: 'accounts@corevolt-electronics.example', subject: 'Please confirm change of bank details (invoice CV-8902)', body: `Hello Corevolt accounts team,\n\nInvoice CV-8902 dated 13 Nov 2026 (PO-2026-1008, ₹1,66,380.00) asks us to pay Riverbend Co-operative Bank, account ending 2347.\nOur records show Harbor Union Bank, account ending 6789.\n\nBefore we can release payment, please send:\n1. A written request on company letterhead, signed by an authorised person.\n2. A bank letter or cancelled cheque for the new account.\n\nWe will also call you on the number held in our vendor file to confirm the change. No payment will be made to the new account until this is complete.\n\nThank you,\nAccounts Payable` };
  if (inv.key === 'si04') return { kind: 'return', title: 'Drafted reply to vendor', to: 'ar@brightline-supplies.example', subject: 'Invoice BL-0377-26 was already paid', body: `Hello Brightline accounts team,\n\nThank you for your reminder. Invoice BL-0377-26 (₹1,18,000.00, dated 20 Oct 2026, PO-2026-0998) is the same invoice as BL/2026/0377, which we approved on 21 Oct and paid on 5 Nov 2026.\n\nNo further payment is due for this invoice. If you believe this is a different invoice, please reply with the invoice number, service dates and the PO it relates to.\n\nRegards,\nAccounts Payable` };
  if (inv.key === 'si07') return { kind: 'return', title: 'Drafted return notice', to: 'billing@meridian-logistics.example', subject: 'Invoice MX-5530 needs a corrected GST amount', body: `Hello Meridian billing team,\n\nInvoice MX-5530 (PO-2026-1009) shows GST of ₹21,320.00. At 18% of the taxable value of ₹1,74,000.00 the GST should be ₹31,320.00, so the total should be ₹2,05,320.00.\n\nPlease send a corrected invoice. We cannot pay the current one because the GST must be right for input credit.\n\nRegards,\nAccounts Payable` };
  if (inv.key === 'si03') return { kind: 'credit', title: 'Drafted credit note request', to: 'accounts@kestrelpack.example', subject: 'Credit note request for invoice K/1241 (PO-2026-1004)', body: `Hello Kestrel accounts team,\n\nWith invoices K/1187, K/1203 and K/1241 you have billed 10,500 cartons against PO-2026-1004, which allows 10,000.\n\nWe will pay K/1241 for the 2,500 cartons that remain on the order (₹1,18,000.00 with GST). Please send a credit note of ₹23,600.00 for the extra 500 cartons, or tell us if a PO change was agreed.\n\nRegards,\nAccounts Payable` };
  if (inv.outcome === 'hold') return { kind: 'info', title: 'Drafted message to vendor', to: V(inv.vendor).short.toLowerCase() + '@vendor.example', subject: `Information needed for invoice ${inv.invNo}`, body: `Hello,\n\nWe could not process invoice ${inv.invNo} yet: ${(inv.reason || '').replace(/\.$/, '').toLowerCase()}.\n\nPlease reply with a corrected or clearer copy. We will re-check it as soon as it arrives.\n\nRegards,\nAccounts Payable` };
  if (inv.outcome === 'reject') return { kind: 'return', title: 'Drafted return notice', to: V(inv.vendor).short.toLowerCase() + '@vendor.example', subject: `Invoice ${inv.invNo} cannot be paid as sent`, body: `Hello,\n\nInvoice ${inv.invNo} cannot be paid as it stands: ${(inv.reason || '').replace(/\.$/, '').toLowerCase()}.\n\nPlease reissue the invoice or reply if you believe this is wrong.\n\nRegards,\nAccounts Payable` };
  return null;
}

function stageMsgs(inv, d) {
  const v = V(inv.vendor), sc = inv.doc === 'scanned'; const rs = n => d.rules.filter(r => r.stage === n);
  const top = n => { const l = rs(n).filter(r => r.sev !== 'pass').sort((a, b) => SEVRANK[b.sev] - SEVRANK[a.sev])[0]; return l; };
  const m = {};
  m[1] = sc ? (inv.photo ? 'Scanned image (phone photo), 1 page. Will read by vision.' : 'Scanned image, 1 page. Will read by vision.') : 'Text PDF, 1 page. New file, not seen before.';
  m[2] = `Read ${d.fields.length} fields and ${d.lines.length} line item${d.lines.length > 1 ? 's' : ''}${sc ? '. Two passes agree on amounts' : ''}.`;
  m[3] = inv.key === 'si05' ? 'Date read as 12 Nov 2026. Total confidence raised 0.78 to 0.92.' : inv.key === 'si02' ? 'Prices are tax-inclusive. Backed out GST to ₹2,74,050.' : top(3) ? top(3).msg : `All required fields present. Lowest confidence ${d.lowest.toFixed(2)}.`;
  m[4] = inv.key === 'si06' ? 'Vendor found. Bank account differs from the master.' : inv.key === 'si05' ? 'Vendor found by GSTIN. No bank details on invoice.' : top(4) ? top(4).msg : `Vendor found: ${v.name}. Bank matches.`;
  m[5] = inv.key === 'si04' ? 'Closest match BL/2026/0377, similarity 1.00.' : top(5) ? top(5).msg : `No earlier invoice is similar (highest ${d.dup.score.toFixed(2)}).`;
  m[6] = inv.key === 'si05' ? 'No PO on invoice. Inferred PO-2026-1005 at 96% (runner-up 14%).' : inv.key === 'si03' ? `${d.po.id} found. ${d.cum.before.toFixed(0)}% billed before this invoice.` : top(6) ? top(6).msg : `${d.po.id} found. ${d.rows.length} line${d.rows.length > 1 ? 's' : ''} aligned.`;
  const n7 = rs(7).filter(r => r.sev === 'pass').length; const t7 = top(7);
  m[7] = t7 ? `${n7} of ${rs(7).length} checks passed. ${t7.name}: ${t7.sev}.` : `All ${rs(7).length} number checks passed.`;
  m[8] = `Worst severity ${d.sev.toUpperCase()}: ${OUT[SEV2OUT[d.sev]].long}.`;
  m[9] = d.draft ? 'Explanation written. Vendor message drafted.' : 'Explanation written.';
  return m;
}
