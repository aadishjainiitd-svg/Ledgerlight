/* ===== Ledgerlight mock data. All people, vendors, GSTINs and bank accounts are fictional. "Today" = 16 Nov 2026. ===== */
const TODAY = new Date(2026, 10, 16, 11, 5);
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmtD = d => d.getDate() + ' ' + MON[d.getMonth()] + ' ' + d.getFullYear();
const fmtDS = d => d.getDate() + ' ' + MON[d.getMonth()];
const pad = n => String(n).padStart(2, '0');
const fmtT = d => pad(d.getHours()) + ':' + pad(d.getMinutes());
const inr = (n, d = 0) => '₹' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
const inr2 = n => inr(n, 2);
const dt = (m, d, h = 10, mi = 0) => new Date(2026, m - 1, d, h, mi);

const OUT = {
  auto:   { label: 'Approved',     long: 'Auto-approve',          ic: 'check-circle', rank: 0 },
  note:   { label: 'Approved, note', long: 'Approve with note',   ic: 'note-circle',  rank: 1 },
  review: { label: 'Needs review', long: 'Route for review',      ic: 'eye',          rank: 2 },
  hold:   { label: 'On hold',      long: 'Hold: request info',    ic: 'pause-circle', rank: 3 },
  reject: { label: 'Rejected',     long: 'Reject',                ic: 'x-circle',     rank: 4 },
};
const OUT_KEYS = ['auto', 'note', 'review', 'hold', 'reject'];
const OUT_COLOR = { auto: 'var(--ok)', note: 'var(--note)', review: 'var(--review)', hold: 'var(--hold)', reject: 'var(--reject)' };

const VENDORS = [
  { id: 'V-101', name: 'Brightline Office Supplies Pvt Ltd', short: 'Brightline', gstin: '27AAFCB4821K1Z3', status: 'approved', terms: 'Net 30', bank: 'Harbor Union Bank', acct: '0123 4567 8901', ifsc: 'HUBK0000214', changed: '14 Mar 2025', phone: '+91 22 4018 2290', aliases: ['Brightline', 'Brightline Office Supplies'], addr: '14 Dockyard Road, Mumbai 400010' },
  { id: 'V-102', name: 'Corevolt Electronics Pvt Ltd', short: 'Corevolt', gstin: '29AAHCC7710M1Z8', status: 'approved', terms: 'Net 45', bank: 'Harbor Union Bank', acct: '0001 2345 6789', ifsc: 'HUBK0000101', changed: '02 Aug 2024', phone: '+91 80 4125 7700', aliases: ['Corevolt', 'Corevolt Electronics'], addr: '22 Electronic City Phase 1, Bengaluru 560100' },
  { id: 'V-103', name: 'Kestrel Print & Pack', short: 'Kestrel', gstin: '24AAMFK3302Q1Z6', status: 'approved', terms: 'Net 30', bank: 'Delta Savings Bank', acct: '7712 0034 2214', ifsc: 'DLSB0000220', changed: '19 Jan 2025', phone: '+91 79 4003 1182', aliases: ['Kestrel', 'Kestrel Print and Pack'], addr: 'Plot 88, GIDC Vatva, Ahmedabad 382445' },
  { id: 'V-104', name: 'Greenleaf Pantry Supplies', short: 'Greenleaf', gstin: '27AAJFG9054R1Z2', status: 'approved', terms: 'Net 15', bank: 'Lakeview Bank', acct: '3300 1275 5508', ifsc: 'LKVB0000318', changed: '30 Sep 2025', phone: '+91 20 4410 6035', aliases: ['Greenleaf', 'Greenleaf Pantry'], addr: '5 Market Yard, Pune 411037' },
  { id: 'V-105', name: 'Meridian Logistics Pvt Ltd', short: 'Meridian', gstin: '27AABCM6620D1Z9', status: 'approved', terms: 'Net 30', bank: 'Delta Savings Bank', acct: '7712 0098 4410', ifsc: 'DLSB0000220', changed: '11 Jun 2025', phone: '+91 22 6120 5544', aliases: ['Meridian', 'Meridian Logistics'], addr: 'Gala 12, Andheri East, Mumbai 400093' },
  { id: 'V-106', name: 'Orion Stationers', short: 'Orion', gstin: '06AAKFO1177P1Z4', status: 'pending', terms: 'Net 30', bank: 'none on file', acct: '', ifsc: '', changed: 'n/a', phone: '+91 124 455 0182', aliases: ['Orion'], addr: 'Sector 18, Gurugram 122015' },
];
const V = id => VENDORS.find(v => v.id === id);

/* ---- Rule catalogue (spec 3.4). stage: 3 fields, 4 vendor, 5 duplicate, 6 PO, 7 numbers ---- */
const RULES = [
  { id: 'R01', name: 'Required fields present', stage: 3, grp: 'Fields', sent: 'Invoice number, date, vendor, total and currency must all be present. If one is missing we hold the invoice and ask the vendor.' },
  { id: 'R02', name: 'Extraction confidence', stage: 3, grp: 'Fields', sent: 'Every key field must be read with confidence of 0.90 or more. Between 0.75 and 0.90 we approve with a note. Below 0.75 we hold.' },
  { id: 'R03', name: 'Invoice date sanity', stage: 3, grp: 'Fields', sent: 'The date cannot be in the future or before the PO date. Dates older than 180 days get a note.' },
  { id: 'R04', name: 'Vendor approved and active', stage: 4, grp: 'Vendor', hard: true, sent: 'The vendor must be an approved vendor. Name-only matches go to review, pending vendors are held, blocked vendors are rejected.' },
  { id: 'R05', name: 'Bank details match master', stage: 4, grp: 'Vendor', hard: true, sent: 'The bank account on the invoice must equal the one on file. Any change, or a note saying the details changed, puts the invoice on hold.' },
  { id: 'R06', name: 'Duplicate invoice', stage: 5, grp: 'Duplicate', hard: true, sent: 'Reject if the invoice is 85% or more similar to an earlier one. Send to review between 60% and 85%.' },
  { id: 'R07', name: 'PO resolved', stage: 6, grp: 'Purchase order', sent: 'Use the PO on the invoice. If none, infer it only when the best match scores 90% or more, beats the runner-up by 20 points and the invoice is up to ₹1,00,000.' },
  { id: 'R08', name: 'PO status and validity', stage: 6, grp: 'Purchase order', sent: 'The PO must be open or partly billed and the invoice date must fall inside its validity window.' },
  { id: 'R09', name: 'Every line maps to the PO', stage: 6, grp: 'Purchase order', sent: 'Lines that are not on the PO are sent to review when they are up to 10% of the invoice, and rejected above that.' },
  { id: 'R10', name: 'Unit price vs PO', stage: 7, grp: 'Numbers', band: true, sent: '' },
  { id: 'R11', name: 'Quantity vs PO remaining', stage: 7, grp: 'Numbers', band: true, sent: '' },
  { id: 'R12', name: 'Cumulative billed vs PO value', stage: 7, grp: 'Numbers', band: true, sent: '' },
  { id: 'R13', name: 'Tax maths', stage: 7, grp: 'Numbers', sent: 'GST must equal the taxable value times the rate. A difference up to ₹1 passes, up to ₹10 gets a note, up to ₹100 goes to review and more is rejected.' },
  { id: 'R14', name: 'Total reconciles', stage: 7, grp: 'Numbers', sent: 'Subtotal plus tax must equal the stated total. Differences over ₹10 are rejected if we read the numbers clearly, otherwise held for re-checking.' },
  { id: 'R15', name: 'High-value cap', stage: 7, grp: 'Numbers', sent: 'Any invoice above ₹10,00,000 needs a manager to sign it off.' },
  { id: 'R16', name: 'Currency matches PO', stage: 7, grp: 'Numbers', sent: 'The invoice currency must be the same as the PO currency, otherwise it goes to review.' },
];
const STAGES = [
  { n: 1, name: 'Ingest', desc: 'Store the file, hash it, detect text or scan' },
  { n: 2, name: 'Extract', desc: 'Read fields and line items with confidence' },
  { n: 3, name: 'Normalise and field checks', desc: 'Dates, money, tax, required fields' },
  { n: 4, name: 'Vendor check', desc: 'Approved vendor? Do the bank details match?' },
  { n: 5, name: 'Duplicate check', desc: 'Is this an invoice we have seen before?' },
  { n: 6, name: 'PO match', desc: 'Find the PO and align every line' },
  { n: 7, name: 'Validation rules', desc: 'Price, quantity, cumulative value, tax, total' },
  { n: 8, name: 'Decision', desc: 'Worst severity across all rules wins' },
  { n: 9, name: 'Explain and output', desc: 'Plain-English reasons and drafts' },
];

/* ---- Purchase orders (spec 9.2) ---- */
const POS = [
  { id: 'PO-2026-0998', v: 'V-101', issued: '2 Sep 2026', valid: '31 Dec 2026', status: 'Fully billed', lines: [['CP-A4-75', 'Copier paper A4 75gsm', 'reams', 400, 250, 18, 400]],
    hist: [['BL/2026/0377', '20 Oct 2026', 118000, 'auto', 'bl0377', 'Paid 5 Nov'], ['BL-0377-26', '16 Nov 2026', 118000, 'reject', 'si04', 'Duplicate, blocked']] },
  { id: 'PO-2026-1001', v: 'V-101', issued: '2 Oct 2026', valid: '31 Dec 2026', status: 'Fully billed', lines: [['CH-ERG-01', 'Ergonomic mesh chair', 'nos', 40, 6500, 18, 40], ['DK-STD-02', 'Height-adjustable standing desk', 'nos', 20, 12000, 18, 20]],
    hist: [['BL/2026/0412', '14 Nov 2026', 590000, 'auto', 'si01', 'In payment queue']] },
  { id: 'PO-2026-1002', v: 'V-102', issued: '12 Oct 2026', valid: '31 Dec 2026', status: 'Fully billed', lines: [['DS-USB-C', 'USB-C docking station', 'nos', 30, 7200, 18, 30], ['KM-W1', 'Wireless keyboard and mouse set', 'nos', 30, 1800, 18, 30]],
    hist: [['CV-8841', '9 Nov 2026', 323379, 'note', 'si02', 'Billed 1.5% above PO']] },
  { id: 'PO-2026-1004', v: 'V-103', issued: '20 Sep 2026', valid: '31 Dec 2026', status: 'Partially billed', lines: [['CTN-L', 'Corrugated shipping carton, large', 'nos', 10000, 40, 18, 7500], ['SETUP-01', 'Custom print setup', 'lot', 1, 20000, 18, 1]],
    hist: [['K/1187', '6 Oct 2026', 212400, 'auto', 'k1187', '4,000 cartons + setup'], ['K/1203', '27 Oct 2026', 165200, 'auto', 'k1203', '3,500 cartons'], ['K/1241', '10 Nov 2026', 141600, 'review', 'si03', '3,000 cartons, pending review']], pending: 120000 },
  { id: 'PO-2026-1005', v: 'V-104', issued: '2 Nov 2026', valid: '31 Dec 2026', status: 'Open', lines: [['PNT-TEA', 'Tea premix', 'kg', 200, 420, 5, 0], ['PNT-SUG', 'Sugar', 'kg', 300, 48, 5, 0]],
    hist: [['GL-2291', '12 Nov 2026', 78750, 'note', 'si05', 'PO inferred, 96%']] },
  { id: 'PO-2026-1007', v: 'V-104', issued: '4 Nov 2026', valid: '31 Dec 2026', status: 'Open', lines: [['PNT-CUP', 'Paper cup 150 ml', 'nos', 25000, 1.6, 12, 0], ['PNT-STR', 'Wooden stirrer', 'nos', 20000, 0.4, 12, 0]], hist: [] },
  { id: 'PO-2026-1008', v: 'V-102', issued: '28 Oct 2026', valid: '31 Dec 2026', status: 'Open', lines: [['NS-24P', '24-port managed switch', 'nos', 6, 21000, 18, 0], ['PC-CAT6', 'Cat6 patch cable 2 m', 'nos', 60, 250, 18, 0]],
    hist: [['CV-8902', '13 Nov 2026', 166380, 'hold', 'si06', 'Bank details changed']], pending: 141000 },
  { id: 'PO-2026-1009', v: 'V-105', issued: '30 Oct 2026', valid: '31 Dec 2026', status: 'Open', lines: [['FR-MUM-PUN', 'Full-truck freight Mumbai to Pune', 'trips', 12, 14500, 18, 0]],
    hist: [['MX-5530', '11 Nov 2026', 195320, 'reject', 'si07', 'GST wrong by ₹10,000']] },
  { id: 'PO-2026-0968', v: 'V-103', issued: '14 Aug 2026', valid: '30 Nov 2026', status: 'Closed', lines: [['CTN-M', 'Corrugated carton, medium', 'nos', 6000, 28, 18, 6000]], hist: [], seed: 1 },
  { id: 'PO-2026-0971', v: 'V-101', issued: '21 Aug 2026', valid: '30 Nov 2026', status: 'Fully billed', lines: [['FL-A4-01', 'Filing folder A4 (box of 50)', 'boxes', 120, 780, 18, 120]], hist: [], seed: 1 },
  { id: 'PO-2026-0974', v: 'V-102', issued: '25 Aug 2026', valid: '30 Nov 2026', status: 'Closed', lines: [['MON-27', '27-inch monitor', 'nos', 24, 12500, 18, 24]], hist: [], seed: 1 },
  { id: 'PO-2026-0977', v: 'V-105', issued: '1 Sep 2026', valid: '31 Dec 2026', status: 'Partially billed', lines: [['FR-DEL-NG', 'Freight Delhi to Noida', 'trips', 30, 6200, 18, 21]], hist: [], seed: 1 },
  { id: 'PO-2026-0979', v: 'V-104', issued: '4 Sep 2026', valid: '31 Dec 2026', status: 'Partially billed', lines: [['PNT-COF', 'Instant coffee 500 g', 'nos', 400, 310, 5, 260]], hist: [], seed: 1 },
  { id: 'PO-2026-0985', v: 'V-101', issued: '12 Sep 2026', valid: '31 Dec 2026', status: 'Open', lines: [['TNR-BK', 'Black toner cartridge', 'nos', 36, 3450, 18, 0]], hist: [], seed: 1 },
];
const PO = id => POS.find(p => p.id === id);
const poSub = p => p.lines.reduce((s, l) => s + l[3] * l[4], 0);
const poBilled = p => p.lines.reduce((s, l) => s + l[6] * l[4], 0);

/* ---- helpers to build invoice objects ---- */
const CATALOG = {
  'V-101': { po: ['PO-2026-0971'], pre: 'BL/2026/', item: ['Filing folder A4 (box of 50)', 780, 'boxes'], pat: 'bl' },
  'V-102': { po: ['PO-2026-0974'], pre: 'CV-', item: ['27-inch monitor', 12500, 'nos'], pat: 'cv' },
  'V-103': { po: ['PO-2026-0968'], pre: 'K/', item: ['Corrugated carton, medium', 28, 'nos'], pat: 'k' },
  'V-104': { po: ['PO-2026-0979'], pre: 'GL-', item: ['Instant coffee 500 g', 310, 'nos'], pat: 'gl' },
  'V-105': { po: ['PO-2026-0977'], pre: 'MX-', item: ['Freight Delhi to Noida', 6200, 'trips'], pat: 'mx' },
};
function rnd(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const R = rnd(20261116);

const RUNS = [];   /* summary rows for dashboard and queue */
const INV = {};    /* full detail by key */
const ALIAS = { ec1: 'si03', ec2: 'si04', ec3: 'si05', ec4: 'si06' };

/* Compact constructor for any invoice. Detail panels are generated from this plus per-invoice overrides. */
function mkInv(o) {
  const v = V(o.vendor);
  const sub = o.sub, rate = o.rate ?? 18, tax = o.tax ?? Math.round(sub * rate / 100), gross = o.gross ?? (sub + tax);
  const inv = Object.assign({
    key: o.key, code: o.code || '', file: o.file || (o.invNo.replace(/[\/ ]/g, '-') + '.pdf'), run: o.run || ('run_' + Math.floor(R() * 0xffff).toString(16).padStart(4, '0')),
    invNo: o.invNo, vendor: o.vendor, vname: v.short, vfull: v.name, po: o.po, date: o.date, sub, rate, tax, gross, outcome: o.outcome, exposure: o.exposure || 0,
    owner: o.owner || null, time: o.time, dur: o.dur || 11 + Math.floor(R() * 6), doc: o.doc || 'text', pdf: o.pdf !== false, pages: 1, conf: o.conf || 0.96, overridden: false,
    cat: o.cat || null, reason: o.reason || 'All 16 checks passed', rec: o.rec || '', age: o.age || 0,
  }, o);
  inv.rv = o.rv || {};
  return inv;
}
const addRun = inv => { INV[inv.key] = inv; RUNS.push(inv); return inv; };

/* ---- The 7 samples + 3 seeded named invoices ---- */
addRun(mkInv({ key: 'bl0377', code: 'Seed', file: 'BL-2026-0377.pdf', run: 'run_2a07', invNo: 'BL/2026/0377', vendor: 'V-101', po: 'PO-2026-0998', date: '20 Oct 2026', sub: 100000, outcome: 'auto', time: dt(10, 21, 10, 12), dur: 12, conf: 0.97, reason: 'All 16 checks passed. Paid on 5 Nov.', paid: '5 Nov 2026',
  items: [['Copier paper A4 75gsm', 400, 'reams', 250, 100000, 18]] }));
addRun(mkInv({ key: 'k1187', code: 'Seed', file: 'K-1187.pdf', run: 'run_91d4', invNo: 'K/1187', vendor: 'V-103', po: 'PO-2026-1004', date: '6 Oct 2026', sub: 180000, outcome: 'auto', time: dt(10, 17, 15, 40), dur: 13, conf: 0.98, reason: 'All 16 checks passed. 4,000 cartons plus print setup.',
  items: [['Corrugated shipping carton, large (lot 1 of 3)', 4000, 'nos', 40, 160000, 18], ['Custom print setup', 1, 'lot', 20000, 20000, 18]] }));
addRun(mkInv({ key: 'k1203', code: 'Seed', file: 'K-1203.pdf', run: 'run_c4b8', invNo: 'K/1203', vendor: 'V-103', po: 'PO-2026-1004', date: '27 Oct 2026', sub: 140000, outcome: 'auto', time: dt(10, 28, 11, 5), dur: 12, conf: 0.98, reason: 'All 16 checks passed. 3,500 cartons.',
  items: [['Corrugated shipping carton, large (lot 2 of 3)', 3500, 'nos', 40, 140000, 18]] }));
addRun(mkInv({ key: 'si01', code: 'SI-01', file: 'SI-01_brightline_BL-2026-0412.pdf', run: 'run_5b21', invNo: 'BL/2026/0412', vendor: 'V-101', po: 'PO-2026-1001', date: '14 Nov 2026', sub: 500000, outcome: 'auto', time: dt(11, 14, 16, 20), dur: 11, conf: 0.95, reason: 'All 16 checks passed. Prices, quantities, GST and total match PO-2026-1001.',
  items: [['Ergonomic mesh chair', 40, 'nos', 6500, 260000, 18], ['Height-adjustable standing desk', 20, 'nos', 12000, 240000, 18]],
  sampleDesc: 'Clean PDF, tax separate, PO printed on the invoice', expect: 'Approved' }));
addRun(mkInv({ key: 'si02', code: 'SI-02', file: 'SI-02_corevolt_CV-8841.pdf', run: 'run_77e0', invNo: 'CV-8841', vendor: 'V-102', po: 'PO-2026-1002', date: '9 Nov 2026', sub: 274050, tax: 49329, gross: 323379, outcome: 'note', time: dt(11, 10, 11, 32), dur: 14, conf: 0.93, taxIncl: true,
  reason: 'Billed 1.5% above the PO (₹4,050), inside the allowed 2%.', items: [['IT peripherals supply: docking stations and wireless keyboard-mouse sets, 30 each', 30, 'sets', 10779.3, 323379, 18]],
  sampleDesc: 'Compact layout, one bundled line, prices include GST', expect: 'Approved, note',
  rv: { R10: ['note', 'The bundle is priced ₹4,050 (1.5%) above the two PO lines it covers. Allowed: up to 2% and ₹5,000.'], R12: ['note', 'Pre-tax ₹2,74,050 against ₹2,70,000 on the PO: ₹4,050 (1.5%) over. Allowed: up to 2% and ₹5,000.'], R13: ['pass', 'GST of ₹49,329 is correct once the tax-inclusive prices are backed out (₹3,23,379 ÷ 1.18).'], R09: ['pass', 'One invoice line covers two PO lines (docking station and keyboard-mouse set). Matched as a bundle.'], R07: ['pass', 'PO-2026-1002 found. The invoice wrote it as "Ref your PO 1002/2026", which we normalised.'] },
  ok: ['Vendor approved; PO-2026-1002 found (written as "1002/2026" and normalised)', 'The bundled line covers both PO lines, 30 docking stations and 30 keyboard-mouse sets', 'GST of ₹49,329 is correct for the tax-inclusive prices', 'Not a duplicate'],
  attention: ['The vendor billed ₹4,050 (1.5%) more than the PO. That is inside the allowed difference of 2% and ₹5,000, so we approved it and attached a note.'],
  next: 'None needed. The invoice is in the payment queue with the note attached. About 1 in 10 noted invoices is sampled for the monthly audit.', headline: 'Approved with a note: the vendor billed 1.5% more than the PO, which is within the allowed difference.' }));
addRun(mkInv({ key: 'si03', code: 'SI-03', ec: 'EC1', file: 'SI-03_kestrel_K-1241.pdf', run: 'run_3c9e', invNo: 'K/1241', vendor: 'V-103', po: 'PO-2026-1004', date: '10 Nov 2026', sub: 120000, outcome: 'review', time: dt(11, 13, 14, 5), dur: 14, conf: 0.97, exposure: 23600, owner: 'Manager', age: 3, cat: 'Quantity or price above PO',
  reason: 'Third lot would bill 500 more cartons than were ordered (₹23,600 with GST).', rec: 'Approve ₹1,18,000, request credit note ₹23,600',
  items: [['Corrugated shipping carton, large (lot 3 of 3)', 3000, 'nos', 40, 120000, 18]],
  sampleDesc: 'Third invoice against a split PO, same template as before', expect: 'Needs review',
  rv: { R11: ['review', '3,000 cartons billed against 2,500 remaining: 500 over, which is 5.0% of the 10,000 ordered. Allowed: up to 2%.'], R12: ['review', 'Cumulative pre-tax billed would be ₹4,40,000 against ₹4,20,000 on the PO: ₹20,000 (4.76%) over.'], R10: ['pass', 'Price per carton ₹40.00 matches the PO.'], R13: ['pass', 'GST of ₹21,600 is correct at 18%.'] },
  headline: 'Review needed: this invoice would bill more than the purchase order allows.',
  ok: ['Vendor approved', 'PO-2026-1004 found on the invoice', 'Price per carton matches (₹40)', 'GST is calculated correctly', 'Not a duplicate'],
  attention: ['Together with the two earlier invoices, Kestrel has now billed for 10,500 cartons, but only 10,000 were ordered. This invoice asks for 3,000 cartons and only 2,500 remain on the order. That is 500 cartons, or ₹23,600 including GST, more than agreed.'],
  next: 'Approve ₹1,18,000 (2,500 cartons) and ask Kestrel for a credit note of ₹23,600. Or ask Procurement to increase the PO if the extra cartons were really delivered.' }));
addRun(mkInv({ key: 'si04', code: 'SI-04', ec: 'EC2', file: 'SI-04_brightline_rescan_BL-0377-26.pdf', run: 'run_8f3a', invNo: 'BL-0377-26', vendor: 'V-101', po: 'PO-2026-0998', date: '20 Oct 2026', sub: 100000, outcome: 'reject', time: dt(11, 16, 10, 41), dur: 14, doc: 'scanned', photo: true, conf: 0.84, exposure: 118000, owner: 'Manager', age: 0, cat: 'Duplicate',
  reason: 'Same invoice as BL/2026/0377, already paid on 5 Nov. The number is written differently.', rec: 'Do not pay. Reply to Brightline that this was paid on 5 Nov',
  items: [['Copier paper A4 75gsm', 400, 'reams', 250, 100000, 18]],
  sampleDesc: 'Phone photo of an invoice, image-only PDF, skewed', expect: 'Rejected',
  rv: { R06: ['reject', 'This is 100% similar to BL/2026/0377 (₹1,18,000.00, 20 Oct 2026), approved 21 Oct and paid 5 Nov. Amount, number, date, PO and items all match.'], R08: ['reject', 'PO-2026-0998 is already fully billed (400 of 400 reams).'], R11: ['reject', '400 reams billed against 0 remaining: 400 over, which is 100% of the 400 ordered.'], R12: ['reject', 'Cumulative pre-tax billed would be ₹2,00,000 against ₹1,00,000 on the PO.'], R02: ['note', 'The invoice number was read at 0.84 because the photo is skewed.'] },
  headline: 'Reject: this looks like an invoice we have already paid.',
  ok: ['Vendor approved (matched by GSTIN)', 'Bank account matches the one on file', 'GST of ₹18,000 is correct at 18%'],
  attention: ['This matches invoice BL/2026/0377 from Brightline (₹1,18,000.00, dated 20 Oct 2026), which was approved on 21 Oct and paid on 5 Nov. The invoice number is written differently ("BL-0377-26"), but the amount, date, PO (PO-2026-0998) and items are identical. Also, that PO is already fully billed.'],
  next: 'Do not pay. Reply to Brightline that this was paid on 5 Nov (draft ready). If this is genuinely a different invoice, a manager can overturn this decision.' }));
addRun(mkInv({ key: 'si05', code: 'SI-05', ec: 'EC3', file: 'SI-05_greenleaf_GL-2291_scan.pdf', run: 'run_a61c', invNo: 'GL-2291', vendor: 'V-104', po: '—', poInferred: 'PO-2026-1005', date: '12 Nov 2026', sub: 75000, rate: 5, outcome: 'note', time: dt(11, 13, 9, 48), dur: 15, doc: 'scanned', conf: 0.80,
  reason: 'PO number was missing. Matched to PO-2026-1005 with 96% confidence.', items: [['Tea premix', 150, 'kg', 420, 63000, 5], ['Sugar', 250, 'kg', 48, 12000, 5]],
  sampleDesc: 'Degraded scan, no PO number, smudged total', expect: 'Approved, note',
  rv: { R02: ['note', 'Lowest confidence is the invoice date at 0.80 (it could be read two ways). The total was read at 0.78 and raised to 0.92 because lines plus tax equal the total.'], R07: ['note', 'No PO number on the invoice. PO-2026-1005 is the best match at 96%; the other open order scores 14%.'], R03: ['pass', 'Read as 12 Nov 2026 (day first). The other reading, 11 Dec 2026, is in the future.'], R04: ['pass', 'Greenleaf Pantry Supplies is an approved vendor (matched by GSTIN on the letterhead).'], R05: ['pass', 'No bank details printed on the invoice. Nothing to compare.'] },
  headline: 'Approved with a note: we matched this invoice to a purchase order that the vendor did not mention.',
  ok: ['Vendor approved', 'Items and prices match PO-2026-1005 exactly', 'GST at 5% is correct', 'Quantities are within what is left on the order', 'Not a duplicate'],
  attention: ['The PO number was missing. PO-2026-1005 is the only open order with tea and sugar at these prices (96% match; the other open order scores 14%).', 'The scan was blurry. We checked the total by adding up the lines and tax (₹75,000 plus ₹3,750 equals ₹78,750), so we trust it.', 'The date "12/11/26" was read as 12 November 2026.'],
  next: 'None needed. You can correct any field if you disagree and the invoice will be re-checked.' }));
addRun(mkInv({ key: 'si06', code: 'SI-06', ec: 'EC4', file: 'SI-06_corevolt_CV-8902_bank-change.pdf', run: 'run_d2f5', invNo: 'CV-8902', vendor: 'V-102', po: 'PO-2026-1008', date: '13 Nov 2026', sub: 141000, outcome: 'hold', time: dt(11, 14, 15, 22), dur: 13, conf: 0.96, exposure: 166380, owner: 'Manager', age: 2, cat: 'Bank change',
  reason: 'Bank account on the invoice differs from the one on file. Everything else matches.', rec: 'Call Corevolt on the number in our vendor file and confirm in writing',
  items: [['24-port managed switch', 6, 'nos', 21000, 126000, 18], ['Cat6 patch cable 2 m', 60, 'nos', 250, 15000, 18]],
  sampleDesc: 'Perfect numbers, new bank details in the footer', expect: 'On hold',
  rv: { R05: ['hold', 'The invoice asks us to pay Riverbend Co-operative Bank (account ending 2347). We have Harbor Union Bank (account ending 6789). The invoice also says "bank details have changed".'] },
  headline: 'Hold: the bank account on this invoice is different from the one we have on file.',
  ok: ['Approved vendor', 'PO-2026-1008 found', 'All prices, quantities, GST and total match'],
  attention: ['The invoice asks us to pay Riverbend Co-operative Bank (account ending 2347). Our records have Harbor Union Bank (account ending 6789) for Corevolt. A changed bank account on an invoice is a common sign of payment fraud, so we never pay on the invoice alone.'],
  next: 'Call Corevolt on the phone number in our vendor file (not the one on the invoice) and confirm the change. Ask for the change on company letterhead. A manager will update the vendor record and release the hold.' }));
addRun(mkInv({ key: 'si07', code: 'SI-07', file: 'SI-07_meridian_MX-5530_tax-error.pdf', run: 'run_e0b9', invNo: 'MX-5530', vendor: 'V-105', po: 'PO-2026-1009', date: '11 Nov 2026', sub: 174000, tax: 21320, gross: 195320, outcome: 'reject', time: dt(11, 15, 17, 10), dur: 12, conf: 0.97, exposure: 10000, owner: 'Clerk pool', age: 1, cat: 'Tax or total',
  reason: 'GST on the invoice is ₹10,000 too low. It should be ₹31,320.', rec: 'Send return notice asking Meridian for a corrected invoice',
  items: [['Full-truck freight Mumbai to Pune', 12, 'trips', 14500, 174000, 18]],
  sampleDesc: 'Clean PDF with a wrong GST amount (a digit slip)', expect: 'Rejected',
  rv: { R13: ['reject', 'GST shown is ₹21,320 but 18% of ₹1,74,000 is ₹31,320. Off by ₹10,000. Allowed: up to ₹100.'], R14: ['pass', 'Subtotal ₹1,74,000 plus tax ₹21,320 equals the stated total ₹1,95,320 (consistent with the wrong tax).'] },
  headline: 'Reject: the GST on this invoice is wrong and the vendor must send a corrected one.',
  ok: ['Vendor approved', 'PO-2026-1009 found', 'Freight rate matches the PO (₹14,500 a trip, 12 trips)', 'Not a duplicate'],
  attention: ['GST should be ₹31,320 (18% of ₹1,74,000) but the invoice shows ₹21,320, which is ₹10,000 too low. The total on the invoice is consistent with the wrong tax, so the error is in the tax line. GST amounts must be right for input credit.'],
  next: 'Send Meridian the return notice (draft ready) and ask for a corrected invoice. Nothing is paid until it arrives.' }));

/* ---- synthetic history: 28 auto, 8 note, 14 exceptions (8 review, 4 hold, 2 reject) ---- */
const VPOOL = ['V-101', 'V-102', 'V-103', 'V-104', 'V-105'];
let serial = { 'V-101': 410, 'V-102': 8800, 'V-103': 1210, 'V-104': 2270, 'V-105': 5500 };
const nextNo = vid => { const s = ++serial[vid] + Math.floor(R() * 3); serial[vid] = s; const c = CATALOG[vid]; return c.pre + (vid === 'V-101' ? '0' + s : s); };
function synthTime(i, n) { const d = new Date(TODAY.getTime() - Math.floor(R() * 29.5 * 86400000)); d.setHours(9 + Math.floor(R() * 8), Math.floor(R() * 60)); return d > TODAY ? dt(11, 16, 9, 20 + i % 30) : d; }
const NOTE_REASONS = ['Price 1.2% above the PO, inside the allowed 2%.', 'PO inferred at 94% confidence; the invoice had no PO number.', 'Scan was blurry; total confirmed because the lines add up.', 'Quantity 1.4% above what remained on the PO.', 'GST off by ₹6 from rounding, inside the allowed ₹10.', 'Invoice dated more than 180 days ago.', 'Price 0.9% above the PO, inside the allowed 2%.', 'Date could be read two ways; read as day first.'];
let si = 0;
const mkSyn = (out, vid, sp) => {
  const c = CATALOG[vid]; const qty = Math.max(2, Math.round((18000 + R() * 420000) / c.item[1] / (c.item[2] === 'trips' ? 1 : 1)));
  const sub = qty * c.item[1]; const invNo = nextNo(vid); const key = 'r' + (++si);
  const conf = out === 'auto' ? 0.93 + R() * 0.06 : out === 'note' ? 0.78 + R() * 0.11 : sp.conf || 0.88 + R() * 0.09;
  const inv = mkInv(Object.assign({ key, code: 'Seed', invNo, vendor: vid, po: c.po[Math.floor(R() * c.po.length)], date: '', sub, outcome: out, time: synthTime(si, 50), dur: 9 + Math.floor(R() * 9), conf: Math.round(conf * 100) / 100, pdf: false,
    items: [[c.item[0], qty, c.item[2], c.item[1], sub, 18]], reason: out === 'auto' ? 'All 16 checks passed' : out === 'note' ? NOTE_REASONS[si % NOTE_REASONS.length] : '', synth: true }, sp));
  if (sp.age !== undefined) inv.time = new Date(TODAY.getTime() - sp.age * 86400000 - (1 + R() * 5) * 3600000);
  const d = new Date(inv.time.getTime() - (2 + Math.floor(R() * 6)) * 86400000); inv.date = fmtD(d);
  return addRun(inv);
};
for (let i = 0; i < 28; i++) mkSyn('auto', VPOOL[Math.floor(R() * 5)], {});
for (let i = 0; i < 8; i++) mkSyn('note', VPOOL[Math.floor(R() * 5)], {});
const EXC = [
  ['review', 'V-101', 'Quantity or price above PO', 'Billed 14 boxes more than remain on the PO (₹12,908 with GST).', 12908, 'Manager', 2, 'Approve what remains, request credit note ₹12,908'],
  ['review', 'V-102', 'Quantity or price above PO', 'Monitor price 4.2% above the PO (₹21,000 over).', 24780, 'Manager', 1, 'Ask Procurement to confirm the new price'],
  ['review', 'V-105', 'Quantity or price above PO', 'Three more trips billed than the PO allows (₹43,500 with GST).', 51330, 'Manager', 3, 'Approve 27 trips, request credit note ₹51,330'],
  ['review', 'V-103', 'Quantity or price above PO', 'Carton price 3.1% above the PO (₹1,848 over).', 2181, 'Clerk pool', 0, 'Accept if Procurement agreed the new price'],
  ['review', 'V-104', 'Duplicate', 'Possible duplicate: 72% similar to an invoice from 3 Nov.', 31500, 'Clerk pool', 1, 'Compare side by side, then accept or reject'],
  ['review', 'V-101', 'Vendor problem', 'Vendor matched by name only; the GSTIN did not match.', 8200, 'Clerk pool', 2, 'Confirm the vendor with Procurement'],
  ['review', 'V-102', 'Tax or total', 'GST rate is 18% but the PO line says 12%.', 7740, 'Clerk pool', 0, 'Ask Corevolt which rate applies'],
  ['review', 'V-105', 'Vendor problem', 'The PO belongs to a different vendor (Kestrel).', 62000, 'Manager', 1, 'Ask Procurement which PO was meant'],
  ['hold', 'V-104', 'Missing information', 'Invoice date is missing. We asked Greenleaf for a copy with the date.', 18400, 'Clerk pool', 3, 'Chase Greenleaf; SLA ends tomorrow'],
  ['hold', 'V-102', 'Missing information', 'Total could not be read with confidence (0.62).', 88500, 'Clerk pool', 1, 'Ask for a clearer copy of the invoice'],
  ['hold', 'V-101', 'Vendor problem', 'Vendor is pending onboarding (Orion Stationers).', 22400, 'Manager', 2, 'Finish onboarding, then re-run'],
  ['hold', 'V-103', 'Missing information', 'No PO on the invoice and no plausible match among open POs.', 46200, 'Clerk pool', 0, 'Ask Procurement or the vendor for the PO'],
  ['reject', 'V-103', 'Duplicate', 'Exact copy of a file we already processed (same file hash).', 52640, 'Manager', 1, 'Send return notice; do not pay'],
  ['reject', 'V-101', 'Quantity or price above PO', 'Unit price 14% above the PO, so this is a different transaction.', 63200, 'Clerk pool', 2, 'Send return notice and ask for a reissue'],
];
EXC.forEach(([out, vid, cat, reason, exp, owner, age, rec]) => mkSyn(out, vid, { cat, reason, exposure: exp, owner, age, rec, conf: out === 'hold' ? 0.58 + R() * 0.2 : 0.9 + R() * 0.07 }));
RUNS.sort((a, b) => b.time - a.time);
/* one run still in progress, shown live on the dashboard */
const RUNNING = { key: 'running1', invNo: 'MX-5541', vname: 'Meridian', vfull: V('V-105').name, vendor: 'V-105', po: 'PO-2026-1009', gross: 205320, outcome: 'running', time: new Date(TODAY.getTime() - 90000), run: 'run_f01a' };

/* ---- metrics helpers ---- */
const COUNTS = () => OUT_KEYS.reduce((m, k) => (m[k] = RUNS.filter(r => r.outcome === k).length, m), {});
const EXCEPTIONS = () => RUNS.filter(r => ['review', 'hold', 'reject'].includes(r.outcome));
const OPEN_EXC = () => RUNS.filter(r => r.outcome === 'review' || r.outcome === 'hold');

/* ---- audit log ---- */
const AUDIT = [];
function buildAudit() {
  const add = (ts, actor, type, summary, obj, outcome, payload) => AUDIT.push({ ts, actor, type, summary, obj, outcome, payload: payload || {} });
  const SYS = { t: 'System', n: 'Ledgerlight rules' }, AI = { t: 'AI model', n: 'Vision model v3' };
  RUNS.filter(r => !r.synth).forEach(r => {
    const t = r.time, who = { t: 'Human', n: r.key === 'si04' ? 'Priya Nair' : 'Priya Nair' };
    const o = { k: 'Invoice', id: r.invNo, href: '#s4-' + r.key };
    add(new Date(t.getTime() - 14000), who, 'Run created', `Uploaded ${r.file} for ${r.vname}`, o, null, { run: r.run, source: r.code === 'Seed' ? 'email' : 'sample', file: r.file });
    add(new Date(t.getTime() - 9500), AI, 'Stage completed', `Extracted ${r.items ? r.items.length + 2 : 8} fields and ${r.items ? r.items.length : 1} line item(s) from ${r.vname} invoice ${r.invNo}`, o, null, { model: 'vision-llm-v3', prompt: 'extract-2.4', lowest: r.conf, cached: true });
    Object.keys(r.rv).slice(0, 2).forEach((rid, i) => { const [sev, msg] = r.rv[rid]; if (sev !== 'pass') add(new Date(t.getTime() - 4000 + i * 300), SYS, 'Rule evaluated', `${RULES.find(x => x.id === rid).name}: ${msg}`, o, sev, { rule: rid, severity: sev, facts: { invoice: r.invNo, gross: r.gross } }); });
    add(t, SYS, 'Decision made', `${OUT[r.outcome].long}: ${r.headline || r.reason}`, o, r.outcome, { decision: r.outcome, exposure: r.exposure, assigned: r.owner, config_version: 14 });
  });
  const S = (r) => ({ k: 'Invoice', id: r.invNo, href: '#s4-' + r.key });
  const syn = RUNS.filter(r => r.synth);
  syn.slice(0, 18).forEach(r => add(r.time, SYS, 'Decision made', `${OUT[r.outcome].long}: ${r.reason}`, S(r), r.outcome, { decision: r.outcome, config_version: 14 }));
  add(dt(11, 16, 9, 41), { t: 'Human', n: 'Rahul Mehta' }, 'Override', `Approved CV-8790 after review: PO amended by Procurement`, { k: 'Invoice', id: 'CV-8790', href: '#s5' }, 'auto', { before: 'Needs review', after: 'Approved', reason_code: 'PO amended by Procurement', reason_text: 'Procurement raised PO quantity by 14 boxes on 15 Nov.' });
  add(dt(11, 15, 16, 22), { t: 'Human', n: 'Priya Nair' }, 'Field corrected', `Corrected total on GL-2268: ₹1,12,000 to ₹1,21,000`, { k: 'Invoice', id: 'GL-2268', href: '#s5' }, null, { before: '₹1,12,000.00', after: '₹1,21,000.00', field: 'total', stages_rerun: '3 to 9' });
  add(dt(11, 14, 11, 8), { t: 'Human', n: 'Rahul Mehta' }, 'Settings changed', 'Rule R10 unit price: note band changed from 1.5% to 2.0%', { k: 'Setting', id: 'R10', href: '#s7' }, null, { before: '1.5%', after: '2.0%', reason: 'Aligned with contract terms for office supplies', version: '13 to 14' });
  add(dt(11, 12, 15, 30), { t: 'Human', n: 'Rahul Mehta' }, 'Master data changed', 'Updated Kestrel contact phone', { k: 'Vendor', id: 'V-103', href: '#s6' }, null, { before: '+91 79 4003 1100', after: '+91 79 4003 1182', verified_by: 'Rahul Mehta' });
  add(dt(11, 15, 18, 2), { t: 'Human', n: 'Rahul Mehta' }, 'Export', 'Exported approved invoices (CSV), last 30 days', { k: 'Export', id: 'approved.csv', href: '#s1' }, null, { rows: 42, filter: 'Approved, Approved with note' });
  add(dt(11, 9, 10, 2), { t: 'Human', n: 'Rahul Mehta' }, 'Master data changed', 'Added purchase order PO-2026-1009 for Meridian Logistics', { k: 'PO', id: 'PO-2026-1009', href: '#s6' }, null, { before: '(none)', after: '12 trips x ₹14,500, GST 18%', source: 'CSV import (3 rows)' });
  AUDIT.sort((a, b) => b.ts - a.ts);
}
buildAudit();
