/* ===== S7 Rules and tolerances ===== */
const BAND0 = { pass_pct: 0.5, pass_abs: 50, note_pct: 2, note_abs: 5000, review_pct: 10 };
const DEF = {
  R02: { ok: 0.90, min: 0.75 }, R03: { days: 180 }, R06: { review: 0.60, reject: 0.85 }, R07: { score: 0.90, gap: 0.20, ceil: 100000 }, R09: { pct: 10 },
  R10: { ...BAND0 }, R11: { ...BAND0, pass_abs: 0, note_abs: 0 }, R12: { ...BAND0 }, R13: { pass: 1, note: 10, review: 100 }, R14: { pass: 1, note: 10 }, R15: { cap: 1000000 },
};
const LABELS = { ok: ['Fine at or above', 'conf'], min: ['Hold below', 'conf'], days: ['Note when older than (days)', 'n'], review: ['Send to review from', 'x'], reject: ['Reject from', 'x'], score: ['Best score needed', 'x'], gap: ['Runner-up gap needed', 'x'], ceil: ['Invoice ceiling (₹)', '₹'], pct: ['Review up to (% of invoice)', '%'], pass_pct: ['Passes silently up to (%)', '%'], pass_abs: ['…or up to (₹)', '₹'], note_pct: ['Note up to (%)', '%'], note_abs: ['…and no more than (₹)', '₹'], review_pct: ['Review up to (%)', '%'], pass: ['Passes up to (₹)', '₹'], note: ['Note up to (₹)', '₹'], cap: ['Manager sign-off above (₹)', '₹'] };
const CFG = JSON.parse(JSON.stringify(DEF)); const CFG_ON = {}; RULES.forEach(r => CFG_ON[r.id] = true);
const GLOBAL = { cap: 1000000, split: 10000, sample: 10, sla: 3, auto: true, baseline: 9, dateOrder: 'Day first', currency: '₹' };
const S7 = { open: new Set(), logv: [
  { v: 14, by: 'Rahul Mehta', when: '14 Nov 2026, 11:08', what: 'R10 Unit price: note band 1.5% to 2.0%', why: 'Aligned with contract terms for office supplies' },
  { v: 13, by: 'Rahul Mehta', when: '3 Nov 2026, 15:20', what: 'R07 PO resolved: ceiling ₹50,000 to ₹1,00,000', why: 'Small vendors often leave the PO off; ceiling raised for implied matches' },
  { v: 12, by: 'Meera Rao', when: '21 Oct 2026, 10:02', what: 'Global: hold SLA 5 to 3 business days', why: 'Audit recommendation' },
  { v: 11, by: 'Rahul Mehta', when: '9 Oct 2026, 17:44', what: 'R13 Tax maths: review step ₹50 to ₹100', why: 'Per-line rounding in freight invoices' },
  { v: 1, by: 'System', when: '1 Sep 2026, 09:00', what: 'Shipped defaults loaded', why: 'Initial configuration' },
] };

function sentence(id) {
  const p = CFG[id], f = (n, d = 2) => { const t = (+n).toFixed(d); return t.includes('.') ? t.replace(/\.?0+$/, '') : t; };
  switch (id) {
    case 'R10': case 'R11': case 'R12': { const lab = { R10: 'unit price', R11: 'quantity over what remains', R12: 'cumulative billed value' }[id]; return `Allow a ${lab} up to ${f(p.note_pct)}% above the PO${id === 'R11' ? '' : ', and no more than ' + inr(p.note_abs)}, with a note. Up to ${f(p.pass_pct)}%${id === 'R11' ? '' : ' or ' + inr(p.pass_abs)} passes silently. Up to ${f(p.review_pct)}% goes to review. Above that is rejected.`; }
    case 'R02': return `Key fields need confidence of ${f(p.ok)} or more. Between ${f(p.min)} and ${f(p.ok)} we approve with a note. Below ${f(p.min)} we hold the invoice.`;
    case 'R03': return `The date cannot be in the future or before the PO date. Dates older than ${p.days} days get a note.`;
    case 'R06': return `Reject if the invoice is ${f(p.reject * 100, 0)}% or more similar to an earlier one. Send to review from ${f(p.review * 100, 0)}% up to ${f(p.reject * 100, 0)}%.`;
    case 'R07': return `Use the PO on the invoice. With no PO, infer it only when the best match scores ${f(p.score * 100, 0)}% or more, beats the runner-up by ${f(p.gap * 100, 0)} points and the invoice is up to ${inr(p.ceil)}.`;
    case 'R09': return `Lines that are not on the PO go to review when they are up to ${f(p.pct)}% of the invoice, and are rejected above that.`;
    case 'R13': return `GST must equal the taxable value times the rate. Up to ${inr(p.pass)} passes, up to ${inr(p.note)} gets a note, up to ${inr(p.review)} goes to review and more is rejected.`;
    case 'R14': return `Subtotal plus tax must equal the stated total. Up to ${inr(p.pass)} passes, up to ${inr(p.note)} gets a note. Above that we reject, or hold if we may have misread.`;
    case 'R15': return `Any invoice above ${inr(p.cap)} needs a manager to sign it off.`;
    default: return RULES.find(r => r.id === id).sent;
  }
}
function validate(id) {
  const p = CFG[id], e = {};
  Object.entries(p).forEach(([k, v]) => { if (!(v >= 0) || isNaN(v)) e[k] = 'Enter a number of zero or more.'; });
  if (['R10', 'R11', 'R12'].includes(id)) { if (p.pass_pct > p.note_pct) e.pass_pct = 'Passes-silently limit cannot be above the note limit.'; if (p.note_pct > p.review_pct) e.note_pct = 'The note limit cannot be above the review limit.'; if (p.pass_abs > p.note_abs) e.pass_abs = 'Cannot be above the note amount.'; }
  if (id === 'R02' && p.min >= p.ok) e.min = 'Hold limit must be below the fine limit.';
  if (id === 'R06' && p.review >= p.reject) e.review = 'Review line must be below the reject line.';
  if (id === 'R13' && !(p.pass <= p.note && p.note <= p.review)) e.note = 'Steps must increase: pass, note, review.';
  if (id === 'R14' && p.pass > p.note) e.pass = 'Passes limit cannot be above the note limit.';
  return e;
}
const dirty = id => JSON.stringify(CFG[id]) !== JSON.stringify(DEF[id]);
const dirtyIds = () => Object.keys(DEF).filter(dirty);
function impact() {
  const ids = dirtyIds(); if (!ids.length) return null; let toReview = 0, toNote = 0;
  ids.forEach(id => { const p = CFG[id], d = DEF[id]; const k = Object.keys(p).find(k => p[k] !== d[k]); const ch = Math.abs(p[k] - d[k]); const tighter = (['pass_pct', 'note_pct', 'review_pct', 'pass_abs', 'note_abs', 'ok', 'review', 'reject', 'ceil', 'pct', 'days', 'pass', 'note', 'cap'].includes(k)) ? (['ok', 'min'].includes(k) ? p[k] > d[k] : p[k] < d[k]) : p[k] < d[k]; const n = Math.max(1, Math.round(ch / (d[k] || 1) * 4)); tighter ? toReview += n : toNote += n; });
  return { toReview, toNote, total: toReview + toNote };
}

function ruleRow(r) {
  const open = S7.open.has(r.id), p = CFG[r.id], has = !!p, err = has ? validate(r.id) : {}, on = CFG_ON[r.id], d = has && dirty(r.id);
  const inputs = has ? `<div class="params">${Object.keys(p).map(k => `<label class="field-l ${err[k] ? 'bad' : ''}">${LABELS[k][0]}<input type="number" step="any" data-rule="${r.id}" data-k="${k}" id="in-${r.id}-${k}" value="${p[k]}" aria-invalid="${!!err[k]}">${err[k] ? `<span class="err-t">${err[k]}</span>` : ''}</label>`).join('')}</div>` : `<p class="small sec">This rule has no thresholds. It is a yes or no check.${r.hard ? ' It is a hard stop and cannot be switched off.' : ''}</p>`;
  const sevOpts = ['R10', 'R11', 'R12'].includes(r.id) ? `<div class="row wrap gap-s small sec" style="margin-top:10px"><span>Severity for each band:</span><span class="chip s-auto">Passes</span>${ic('arrow-r', 'sm')}<span class="chip s-note">Note</span>${ic('arrow-r', 'sm')}<span class="chip s-review">Review</span>${ic('arrow-r', 'sm')}<span class="chip s-reject">Reject</span><span class="muted">(fixed bands, thresholds editable)</span></div>` : '';
  return `<div class="rule-row ${open ? 'open' : ''}" id="rr-${r.id}"><div><button class="toggle" role="switch" aria-checked="${on}" ${r.hard ? 'disabled' : ''} data-act="toggleRule" data-id="${r.id}" aria-label="${r.name} enabled" ${r.hard ? 'data-tip="Hard-stop rules cannot be disabled"' : ''}></button></div>
    <div class="grow" style="min-width:0"><h4>${r.name}<span class="rid">${r.id}</span>${r.hard ? '<span class="pill">' + ic('lock', 'sm') + 'Hard stop</span>' : ''}${d ? '<span class="pill accent" id="bd-' + r.id + '">Edited</span>' : '<span class="pill" id="bd-' + r.id + '">Default</span>'}</h4><p class="sec" style="margin-top:3px" id="sn-${r.id}">${esc(sentence(r.id))}</p></div>
    <div class="rr-act"><button class="btn sm" data-act="editRule" data-id="${r.id}">${ic('edit', 'sm')}${open ? 'Close' : 'Edit'}</button></div>
    <div class="editor">${inputs}${sevOpts}<div class="preview-sent"><b>Preview.</b> <span id="pv-${r.id}">${esc(sentence(r.id))}</span></div></div></div>`;
}
function renderS7() {
  const groups = ['Fields', 'Vendor', 'Duplicate', 'Purchase order', 'Numbers']; const di = dirtyIds(), im = impact();
  const bad = di.some(id => Object.keys(validate(id)).length);
  return `${pageHead('Rules and tolerances', 'Every check in plain language. Change a number, see the sentence change, and see what it would do to past decisions.', `<span class="pill ${di.length ? 'accent' : ''}" id="dirty-pill">${di.length ? di.length + ' unsaved change' + (di.length > 1 ? 's' : '') : 'Rule set version 14'}</span><button class="btn" data-act="revertDefaults">Revert to defaults</button><button class="btn" data-act="revertPrev">Revert to previous version</button><button class="btn primary" id="save-rules" data-act="saveRules" ${!di.length || bad ? 'disabled' : ''}>Save with reason</button>`)}
  <div class="two-col">
    <div class="stack">${groups.map(g => `<div class="card"><div class="card-h" style="padding-bottom:10px;border-bottom:1px solid var(--line)"><h3>${g}</h3><span class="muted small">${RULES.filter(r => r.grp === g).map(r => r.id).join(', ')}</span></div>${RULES.filter(r => r.grp === g).map(ruleRow).join('')}</div>`).join('')}</div>
    <div class="stack" style="position:sticky;top:76px">
      <div class="card" id="impact-card">${impactHTML(im)}</div>
      <div class="card"><div class="card-h"><h3>Global settings</h3></div><div class="card-b stack-s" style="gap:12px">
        <label class="field-l">High-value cap (₹)<input type="number" id="g-cap" value="${GLOBAL.cap}" data-g="cap"></label><label class="field-l">Exposure split, clerk up to (₹)<input type="number" id="g-split" value="${GLOBAL.split}" data-g="split"></label>
        <div class="params"><label class="field-l">Audit sample (%)<input type="number" id="g-sample" value="${GLOBAL.sample}" data-g="sample"></label><label class="field-l">Hold SLA (days)<input type="number" id="g-sla" value="${GLOBAL.sla}" data-g="sla"></label><label class="field-l">Manual minutes<input type="number" id="g-base" value="${GLOBAL.baseline}" data-g="baseline"></label><label class="field-l">Date order<select id="g-do"><option>Day first</option><option>Month first</option></select></label></div>
        <label class="row"><button class="toggle" role="switch" aria-checked="${GLOBAL.auto}" data-act="toggleAuto" aria-label="Auto-approve enabled"></button><span><b>Auto-approve enabled</b><br><span class="small muted">Turn off to send every invoice to a person.</span></span></label></div></div>
      <div class="card"><div class="card-h"><h3>Change log</h3></div><div class="card-b"><div class="tl">${S7.logv.map((l, i) => `<div class="ev ${i === 0 ? 'now' : ''}" style="--evc:var(--accent)"><div class="row gap-s"><span class="pill ${i === 0 ? 'accent' : ''}">v${l.v}</span><span class="small muted">${l.when}</span></div><div style="margin-top:2px"><b>${esc(l.what)}</b></div><div class="small sec">${esc(l.by)}: ${esc(l.why)}</div></div>`).join('')}</div></div></div>
    </div></div>`;
}
function impactHTML(im) {
  return `<div class="card-h"><h3>Impact preview</h3><span class="pill right">Last 90 days</span></div><div class="card-b">${im ? `<p><b>If you save this, ${im.total} of the last 90 days' decisions would change.</b></p><div class="stack-s" style="margin-top:10px">${im.toReview ? `<div class="row gap-s">${chip('note')}${ic('arrow-r', 'sm')}${chip('review')}<b class="right num">${im.toReview}</b></div>` : ''}${im.toNote ? `<div class="row gap-s">${chip('review')}${ic('arrow-r', 'sm')}${chip('note')}<b class="right num">${im.toNote}</b></div>` : ''}</div><p class="small muted" style="margin-top:10px">Existing decisions stay as they are unless you re-run them. <a href="#s1" data-act="toastMsg" data-m="Listing the affected invoices opens in a later release of this mock.">See the list</a></p>` : `<p class="sec">Change a threshold and Ledgerlight shows how many past decisions would flip. Nothing is saved until you give a reason.</p>`}</div>`;
}
function s7After() { }
document.addEventListener('input', e => {
  const t = e.target.closest('input[data-rule]'); if (!t) return; const id = t.dataset.rule; CFG[id][t.dataset.k] = t.value === '' ? NaN : +t.value;
  const err = validate(id), row = $('#rr-' + id); const label = t.closest('label'); label.classList.toggle('bad', !!err[t.dataset.k]); let msg = label.querySelector('.err-t'); if (err[t.dataset.k]) { if (!msg) { msg = document.createElement('span'); msg.className = 'err-t'; label.appendChild(msg); } msg.textContent = err[t.dataset.k]; } else if (msg) msg.remove();
  const s = isNaN(CFG[id][t.dataset.k]) ? sentence(id) : sentence(id); $('#sn-' + id).textContent = s; $('#pv-' + id).textContent = s; const bd = $('#bd-' + id); bd.className = 'pill' + (dirty(id) ? ' accent' : ''); bd.textContent = dirty(id) ? 'Edited' : 'Default';
  refreshS7();
});
function refreshS7() { const di = dirtyIds(), bad = di.some(id => Object.keys(validate(id)).length); const sv = $('#save-rules'); if (sv) sv.disabled = !di.length || bad; const dp = $('#dirty-pill'); if (dp) { dp.className = 'pill ' + (di.length ? 'accent' : ''); dp.textContent = di.length ? di.length + ' unsaved change' + (di.length > 1 ? 's' : '') : 'Rule set version 14'; } const ic2 = $('#impact-card'); if (ic2) ic2.innerHTML = impactHTML(impact()); }
document.addEventListener('input', e => { const g = e.target.closest('[data-g]'); if (g) GLOBAL[g.dataset.g] = +g.value; });
ACT.editRule = t => { const id = t.dataset.id; S7.open.has(id) ? S7.open.delete(id) : S7.open.add(id); const row = $('#rr-' + id); row.classList.toggle('open'); t.innerHTML = ic('edit', 'sm') + (S7.open.has(id) ? 'Close' : 'Edit'); };
ACT.toggleRule = t => { const id = t.dataset.id; CFG_ON[id] = !CFG_ON[id]; t.setAttribute('aria-checked', CFG_ON[id]); toast(`${id} is now ${CFG_ON[id] ? 'on' : 'off'}. The change takes effect when you save with a reason.`); };
ACT.toggleAuto = t => { GLOBAL.auto = !GLOBAL.auto; t.setAttribute('aria-checked', GLOBAL.auto); };
ACT.revertDefaults = () => { Object.keys(DEF).forEach(k => CFG[k] = JSON.parse(JSON.stringify(DEF[k]))); route(true); toast('All thresholds are back to the shipped defaults. Nothing is saved yet.'); };
ACT.revertPrev = () => toast('Rule set version 14 is already the latest. Version 13 can be restored once a newer version exists.');
ACT.saveRules = () => {
  const ids = dirtyIds(); openModal(`<div class="sheet-h"><h3>Save ${ids.length} change${ids.length > 1 ? 's' : ''}</h3><button class="icon-btn right" data-act="closeModal" aria-label="Close">${ic('x')}</button></div><div class="sheet-b"><div class="small sec">${ids.map(id => `<div><b>${id}</b> ${esc(sentence(id))}</div>`).join('')}</div>${impactHTML(impact()).replace('card-h', 'row').replace('card-b', 'stack-s')}<label class="field-l">Reason for the change (required)<textarea id="sv-why" placeholder="For example: aligned with the new contract terms"></textarea></label></div><div class="sheet-f"><button class="btn" data-act="closeModal">Cancel</button><button class="btn primary" id="sv-go" data-act="confirmSave" disabled>Save settings</button></div>`);
  $('#sv-why').oninput = () => { $('#sv-go').disabled = $('#sv-why').value.trim().length < 10; };
};
ACT.confirmSave = () => {
  const ids = dirtyIds(), why = $('#sv-why').value.trim(), v = S7.logv[0].v + 1;
  S7.logv.unshift({ v, by: ROLES[S.role].name, when: fmtD(TODAY) + ', ' + fmtT(new Date(TODAY.getTime() + 600000)), what: ids.map(id => `${id} ${RULES.find(r => r.id === id).name}`).join(', ') + ' changed', why });
  ids.forEach(id => { DEF[id] = JSON.parse(JSON.stringify(CFG[id])); });
  AUDIT.unshift({ ts: new Date(TODAY.getTime() + 600000), actor: { t: 'Human', n: ROLES[S.role].name }, type: 'Settings changed', summary: `Saved rule set version ${v}: ${ids.join(', ')} changed`, obj: { k: 'Setting', id: ids[0], href: '#s7' }, outcome: null, payload: { version: `${v - 1} to ${v}`, reason: why, changed: ids.join(', ') } });
  closeModal(); toast('Settings saved. New runs use these values. Existing decisions are unchanged unless you re-run them.'); route(true);
};
