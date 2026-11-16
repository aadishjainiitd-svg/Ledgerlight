/* ===== S5 Review queue ===== */
const STATE5 = { tab: 'review', assigned: 'all', exposure: 'all', cat: 'all', sort: 'priority', sel: null, checked: new Set(), asked: new Set() };
const RESOLVED_SEED = [
  { vname: 'Corevolt', invNo: 'CV-8790', gross: 186400, final: 'auto', by: 'Rahul Mehta', code: 'PO amended by Procurement', when: '16 Nov, 09:41' },
  { vname: 'Greenleaf', invNo: 'GL-2268', gross: 121000, final: 'auto', by: 'Priya Nair', code: 'Extraction corrected', when: '15 Nov, 16:22' },
  { vname: 'Brightline', invNo: 'BL/2026/0398', gross: 64900, final: 'reject', by: 'Priya Nair', code: 'Credit note requested', when: '13 Nov, 12:10' },
  { vname: 'Meridian', invNo: 'MX-5502', gross: 92300, final: 'auto', by: 'Rahul Mehta', code: 'Price agreed with Procurement', when: '11 Nov, 15:48' },
  { vname: 'Kestrel', invNo: 'K/1229', gross: 143800, final: 'auto', by: 'Rahul Mehta', code: 'Vendor confirmed by phone', when: '6 Nov, 10:05' },
  { vname: 'Corevolt', invNo: 'CV-8812', gross: 53600, final: 'reject', by: 'Priya Nair', code: 'Not actually a duplicate', when: '3 Nov, 14:30' },
];
const qItems = tab => RUNS.filter(r => r.outcome === ({ review: 'review', hold: 'hold', rejected: 'reject' })[tab] && !r.resolved);
const openExcCount = () => RUNS.filter(r => (r.outcome === 'review' || r.outcome === 'hold') && !r.resolved).length;
function updateNavBadge() { const b = $('#nav-badge'); if (b) b.textContent = openExcCount(); }

function queueFiltered() {
  const S5 = STATE5; let l = qItems(S5.tab);
  if (S5.assigned !== 'all') { const me = S.role === 'manager' ? 'Manager' : 'Clerk pool'; l = l.filter(r => r.owner === (S5.assigned === 'me' ? me : S5.assigned)); }
  if (S5.exposure === '10k') l = l.filter(r => r.exposure > 10000); if (S5.exposure === '1l') l = l.filter(r => r.exposure > 100000);
  if (S5.cat !== 'all') l = l.filter(r => r.cat === S5.cat);
  return l.sort((a, b) => S5.sort === 'exposure' ? b.exposure - a.exposure : S5.sort === 'age' ? b.age - a.age : (b.exposure * (1 + b.age)) - (a.exposure * (1 + a.age)));
}
function ageBadge(r) { const lim = r.outcome === 'hold' ? 3 : 2; const cls = r.age >= (r.outcome === 'hold' ? 3 : 99) ? 'red' : r.age >= 1 ? 'amber' : ''; return `<span class="age ${cls}" data-tip="${r.outcome === 'hold' ? 'Hold SLA is 3 business days' : 'Same business day target'}">${r.age === 0 ? 'Today' : r.age + (r.age === 1 ? ' day' : ' days')}</span>`; }

function renderS5() {
  const S5 = STATE5, cnt = t => qItems(t).length; const l = S5.tab === 'resolved' ? null : queueFiltered();
  const cats = ['Quantity or price above PO', 'Duplicate', 'Bank change', 'Missing information', 'Vendor problem', 'Tax or total'];
  const sel = S5.sel && INV[S5.sel] ? INV[S5.sel] : null;
  const resolvedRows = [...RUNS.filter(r => r.resolved).map(r => ({ vname: r.vname, invNo: r.invNo, gross: r.gross, final: r.outcome, by: r.resolved.by, code: 'Accepted recommendation', when: r.resolved.when })), ...RESOLVED_SEED];
  const body = S5.tab === 'resolved' ? `<div class="card"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Invoice</th><th>Vendor</th><th class="r">Amount</th><th>Final</th><th>Resolved by</th><th>Reason</th><th>When</th></tr></thead><tbody>${resolvedRows.map(r => `<tr><td class="mono">${esc(r.invNo)}</td><td>${esc(r.vname)}</td><td class="r num">${inr2(r.gross)}</td><td>${chip(r.final)}</td><td>${esc(r.by)}</td><td class="sec">${esc(r.code)}</td><td class="muted small">${r.when}</td></tr>`).join('')}</tbody></table></div></div>`
    : l.length ? l.map(r => { const d = buildDetail(r); return `<div class="qrow sev-${r.outcome} ${S5.sel === r.key ? 'sel' : ''}" data-act="qSelect" data-k="${r.key}" tabindex="0" role="button" aria-label="Open quick view for ${esc(r.invNo)}">
      <input type="checkbox" class="check" data-act="qCheck" data-k="${r.key}" ${S5.checked.has(r.key) ? 'checked' : ''} aria-label="Select ${esc(r.invNo)}">
      <div class="trunc" style="min-width:150px"><div class="row gap-s">${chip(r.outcome)}</div><div style="margin-top:6px"><b>${esc(r.vname)}</b> <span class="mono small sec">${esc(r.invNo)}</span></div><div class="tiny muted">${inr2(r.gross)}</div></div>
      <div class="sec" style="min-width:0">${esc(r.reason)}<div class="tiny muted" style="margin-top:3px">${r.cat || ''}${r.ec ? ` · <b style="color:var(--accent-fg)">${r.ec}</b>` : ''}</div></div>
      <div class="side"><div class="num" style="font-family:var(--f-head);font-weight:800;font-size:16px">${inr(r.exposure)}</div><div class="tiny muted">exposure</div><div class="row gap-s">${ageBadge(r)}<span class="tag">${r.owner}</span></div></div>
      <div class="rec">${ic('arrow-r', 'sm')}<span><b>Recommended:</b> ${esc(r.rec)}</span></div></div>`; }).join('') : `<div class="card empty"><h4>Nothing needs you right now</h4><p>42 invoices were approved without a person this month.</p><p style="margin-top:12px"><a class="btn" href="#s1">Back to the dashboard</a></p></div>`;
  return `${pageHead('Review queue', 'Everything a person has to touch, ranked by risk and age.', `<span class="small muted">Showing the queue as <b>${ROLES[S.role].label}</b></span>`)}
  <div class="stack">
    <div class="tabs" role="tablist">${[['review', 'Needs review'], ['hold', 'On hold'], ['rejected', 'Rejected']].map(([k, n]) => `<button role="tab" class="${S5.tab === k ? 'on' : ''}" data-act="qTab" data-t="${k}">${n}<span class="ct">${cnt(k)}</span></button>`).join('')}<button role="tab" class="${S5.tab === 'resolved' ? 'on' : ''}" data-act="qTab" data-t="resolved">Resolved, last 30 days<span class="ct">${resolvedRows.length}</span></button></div>
    ${S5.tab === 'resolved' ? '' : `<div class="row wrap">
      <label class="field-l" style="flex-direction:row;align-items:center;gap:8px">Assigned to<select id="q-as" data-act="qFilter" data-f="assigned"><option value="all">Anyone</option><option value="me" ${S5.assigned === 'me' ? 'selected' : ''}>Me</option><option ${S5.assigned === 'Clerk pool' ? 'selected' : ''}>Clerk pool</option><option ${S5.assigned === 'Manager' ? 'selected' : ''}>Manager</option></select></label>
      <label class="field-l" style="flex-direction:row;align-items:center;gap:8px">Exposure<select id="q-ex" data-act="qFilter" data-f="exposure"><option value="all">Any</option><option value="10k" ${S5.exposure === '10k' ? 'selected' : ''}>Above ₹10,000</option><option value="1l" ${S5.exposure === '1l' ? 'selected' : ''}>Above ₹1,00,000</option></select></label>
      <label class="field-l" style="flex-direction:row;align-items:center;gap:8px">Reason<select id="q-ca" data-act="qFilter" data-f="cat"><option value="all">All reasons</option>${cats.map(c => `<option ${S5.cat === c ? 'selected' : ''}>${c}</option>`).join('')}</select></label>
      <label class="field-l right" style="flex-direction:row;align-items:center;gap:8px">Sort<select id="q-so" data-act="qFilter" data-f="sort"><option value="priority">Risk and age</option><option value="exposure" ${S5.sort === 'exposure' ? 'selected' : ''}>Exposure</option><option value="age" ${S5.sort === 'age' ? 'selected' : ''}>Age</option></select></label></div>
    ${S5.checked.size ? `<div class="banner info fade-in"><b>${S5.checked.size} selected</b><span class="grow"></span><label class="row gap-s small">Assign to <select id="bulk-as"><option>Clerk pool</option><option>Manager</option></select></label><button class="btn sm" data-act="bulkAssign">Assign</button><button class="btn sm" data-act="bulkExport">${ic('download', 'sm')}Export CSV</button></div>` : ''}`}
    <div class="q-layout ${sel && S5.tab !== 'resolved' ? 'has-panel' : ''}"><div class="stack-s" style="gap:10px;min-width:0">${body}</div>${sel && S5.tab !== 'resolved' ? quickPanel(sel) : ''}</div>
  </div>`;
}
function quickPanel(r) {
  const d = buildDetail(r), asked = STATE5.asked.has(r.key);
  const top = d.rows.filter(x => x.ti && (x.sev !== 'pass')).slice(0, 2);
  return `<aside class="card qpanel fade-in" aria-label="Quick view"><div class="row"><div class="grow"><div class="row gap-s">${chip(r.outcome)}<span class="mono small muted">${esc(r.invNo)}</span></div></div><button class="icon-btn" data-act="qClose" aria-label="Close quick view">${ic('x', 'sm')}</button></div>
  <h3 style="font-size:16px;line-height:1.35">${esc(d.headline)}</h3>
  <dl class="kv"><dt>Vendor</dt><dd>${esc(r.vfull)}</dd><dt>Amount</dt><dd class="num"><b>${inr2(r.gross)}</b></dd><dt>Exposure</dt><dd class="num"><b>${inr(r.exposure)}</b></dd><dt>PO</dt><dd class="mono">${d.po.id}</dd><dt>Assigned</dt><dd>${r.owner} · ${ageBadge(r)}</dd></dl>
  ${top.length ? `<div><div class="upper" style="margin-bottom:6px">Biggest differences from the PO</div>${top.map(x => `<div class="row small" style="padding:6px 0;border-bottom:1px solid var(--line)">${sevIcon(x.sev)}<span class="grow">${esc(x.il)}</span><span class="num sec">${x.over ? x.over + ' over' : (x.dp * 100).toFixed(1) + '%'}</span><b class="num">${x.av ? '+' + inr(Math.round(x.av)) : ''}</b></div>`).join('')}</div>` : ''}
  <div class="next small"><b>${esc(r.rec)}</b></div>
  ${r.outcome === 'hold' ? `<div class="stack-s"><div class="upper">Hold controls</div><div class="row wrap gap-s"><button class="btn sm" data-act="copyHoldDraft" data-k="${r.key}">${ic('copy', 'sm')}Copy vendor email draft</button><button class="btn sm" data-act="markAsked" data-k="${r.key}">${ic('clock', 'sm')}${asked ? 'Info requested. SLA running' : 'Mark info requested'}</button><label class="btn sm" for="up-${r.key}">${ic('upload', 'sm')}Upload received document</label><input hidden type="file" id="up-${r.key}" accept="application/pdf" data-act="uploadHold" data-k="${r.key}"></div></div>` : ''}
  <div class="row wrap gap-s"><button class="btn primary" data-act="qAccept" data-k="${r.key}">${ic('check', 'sm')}Accept recommendation</button><a class="btn" href="#s4-${r.key}" data-act="qOverride" data-k="${r.key}">Override…</a><a class="btn" href="#s4-${r.key}">Open full detail</a></div></aside>`;
}
ACT.qTab = t => { STATE5.tab = t.dataset.t; STATE5.sel = null; STATE5.checked.clear(); route(true); };
ACT.qSelect = (t, e) => { if (e.target.closest('input')) return; STATE5.sel = t.dataset.k; route(true); };
ACT.qClose = () => { STATE5.sel = null; route(true); };
ACT.qCheck = (t, e) => { e.stopPropagation(); t.checked ? STATE5.checked.add(t.dataset.k) : STATE5.checked.delete(t.dataset.k); route(true); };
document.addEventListener('change', e => { const t = e.target.closest('[data-act="qFilter"]'); if (t) { STATE5[t.dataset.f] = t.value; route(true); } const u = e.target.closest('[data-act="uploadHold"]'); if (u && u.files.length) { toast('Document received. The pipeline is re-running with the new file attached to the same invoice.'); setTimeout(() => location.hash = '#s3-' + u.dataset.k, 900); } });
ACT.bulkAssign = () => { const to = $('#bulk-as').value; STATE5.checked.forEach(k => { INV[k].owner = to; }); toast(`${STATE5.checked.size} invoices assigned to ${to}.`); STATE5.checked.clear(); route(true); };
ACT.bulkExport = () => { toast(`${STATE5.checked.size} invoices exported as CSV.`); };
ACT.copyHoldDraft = t => { const dr = buildDetail(INV[t.dataset.k]).draft; copyText(`To: ${dr.to}\nSubject: ${dr.subject}\n\n${dr.body}`, 'Email draft'); };
ACT.markAsked = t => { STATE5.asked.add(t.dataset.k); addAudit('Decision made', `Marked info requested for ${INV[t.dataset.k].invNo}. 3 business day SLA started`, INV[t.dataset.k], 'hold', { sla: '3 business days' }); toast('Info requested. The 3 business day SLA clock has started.'); route(true); };
ACT.qOverride = (t, e) => { e.preventDefault(); S4KEY = t.dataset.k; location.hash = '#s4-' + t.dataset.k; setTimeout(() => ACT.openOverride(), 120); };
ACT.qAccept = t => {
  const r = INV[t.dataset.k]; r.resolved = { by: ROLES[S.role].name, when: fmtDS(TODAY) + ', ' + fmtT(new Date(TODAY.getTime() + 300000)) }; STATE5.sel = null;
  addAudit('Decision made', `${ROLES[S.role].name} accepted the recommendation on ${r.invNo}: ${r.rec}`, r, r.outcome, { recommendation: r.rec }); updateNavBadge(); route(true);
  toast(`${esc(r.invNo)} approved by you.`, () => { delete r.resolved; AUDIT.shift(); updateNavBadge(); route(true); });
};
