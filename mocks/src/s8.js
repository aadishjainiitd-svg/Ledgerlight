/* ===== S8 Audit log ===== */
const STATE8 = { actor: 'all', type: 'all', user: 'all', range: 90, q: '', inv: null, open: new Set(), limit: 30 };
const EVT_TYPES = ['Run created', 'Stage completed', 'Rule evaluated', 'Decision made', 'Override', 'Field corrected', 'Master data changed', 'Settings changed', 'Export'];
const evKey = e => e.ts.getTime() + '|' + e.type + '|' + e.obj.id;
function auditFiltered() {
  const S8 = STATE8; const since = new Date(TODAY.getTime() - S8.range * 86400000 - 86400000);
  return AUDIT.filter(e => e.ts >= since && (S8.actor === 'all' || e.actor.t === S8.actor) && (S8.type === 'all' || e.type === S8.type) && (S8.user === 'all' || e.actor.n === S8.user) && (!S8.inv || e.obj.id === S8.inv) && (!S8.q || (e.summary + e.obj.id + e.actor.n + e.type).toLowerCase().includes(S8.q.toLowerCase()))).sort((a, b) => b.ts - a.ts);
}
const actorHTML = a => `<span class="actor"><span class="av ${a.t === 'System' ? 'sys' : a.t === 'AI model' ? 'ai' : 'hum'}">${a.t === 'System' ? ic('gear', 'sm') : a.t === 'AI model' ? ic('cpu', 'sm') : a.n.split(' ').map(x => x[0]).join('')}</span><span><div style="font-weight:600;font-size:13px">${esc(a.n)}</div><div class="tiny muted">${a.t}</div></span></span>`;
function payloadHTML(e) {
  const p = e.payload || {}; let h = '';
  if (p.before !== undefined && p.after !== undefined) h += `<div class="diffbox"><div class="bf"><div class="upper">Before</div>${esc(p.before)}</div><div class="af"><div class="upper">After</div>${esc(p.after)}</div></div>`;
  const rest = Object.entries(p).filter(([k]) => !['before', 'after'].includes(k));
  if (rest.length) h += `<dl class="kv" style="margin-top:${h ? 12 : 0}px">${rest.map(([k, v]) => `<dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${typeof v === 'object' ? esc(JSON.stringify(v)) : esc(v)}</dd>`).join('')}</dl>`;
  return (h || '<span class="muted">No extra details.</span>') + `<div style="margin-top:10px"><a href="#" data-act="viewJson" data-k="${esc(evKey(e))}" class="small">View JSON</a><pre class="json" hidden style="margin-top:8px;border-radius:8px;padding:10px 12px">${esc(JSON.stringify({ ts: e.ts.toISOString(), actor: e.actor, type: e.type, object: e.obj, payload: p }, null, 2))}</pre></div>`;
}
function renderS8() {
  const S8 = STATE8, list = auditFiltered(), shown = list.slice(0, S8.limit);
  const users = ['all', 'Priya Nair', 'Rahul Mehta'];
  const inv = S8.inv ? RUNS.find(r => r.invNo === S8.inv) : null;
  const trace = S8.inv ? `<div class="card panel"><h3>${ic('link', 'sm')}Trace for ${esc(S8.inv)}<span class="muted small" style="font-weight:500">from upload to payment queue</span><button class="btn sm right" data-act="clearInv">Clear invoice filter</button></h3>${list.length ? `<div class="tl">${list.slice().reverse().map(e => `<div class="ev" style="--evc:${e.outcome ? OUT_COLOR[e.outcome] : 'var(--line-2)'}"><div class="small muted">${fmtDS(e.ts)}, ${fmtT(e.ts)} · ${esc(e.actor.n)} · ${e.type}</div><div>${esc(e.summary)}</div></div>`).join('')}</div>` : '<div class="muted">No events for this invoice.</div>'}${inv ? `<div style="margin-top:12px"><a class="btn sm" href="#s4-${inv.key}">Open decision detail ${ic('arrow-r', 'sm')}</a></div>` : ''}</div>` : '';
  const rows = shown.map(e => { const k = evKey(e), open = S8.open.has(k); return `<tr class="link audit-row ${open ? 'open' : ''}" data-act="auditRow" data-k="${esc(k)}"><td class="nowrap"><div style="font-weight:600">${fmtDS(e.ts)}, ${fmtT(e.ts)}</div><div class="tiny muted">${e.ts.getFullYear()}</div></td><td>${actorHTML(e.actor)}</td><td style="min-width:260px"><span class="tag">${e.type}</span><div style="margin-top:4px">${esc(e.summary)}</div></td><td class="nowrap"><a href="${e.obj.href}" data-act="objLink" data-id="${esc(e.obj.id)}" data-kind="${e.obj.k}"><span class="muted small">${e.obj.k}</span> <b class="mono">${esc(e.obj.id)}</b></a></td><td>${e.outcome ? chip(e.outcome) : ''}</td><td class="c">${ic(open ? 'chev-u' : 'chev-d', 'sm')}</td></tr>${open ? `<tr class="payload" style="display:table-row"><td colspan="6">${payloadHTML(e)}</td></tr>` : ''}`; }).join('');
  return `${pageHead('Audit log', 'Everything the system did and every decision a person made, with the reason.', `<button class="btn" data-act="auditExport" data-f="CSV">${ic('download', 'sm')}Export CSV</button><button class="btn" data-act="auditExport" data-f="JSON">${ic('download', 'sm')}Export JSON</button>`)}
  <div class="stack">
    <div class="banner info">${ic('lock', 'lg')}<span><b>Entries cannot be edited or deleted.</b> This log is append-only. Corrections are recorded as new entries.</span></div>
    ${trace}
    <div class="card"><div class="row wrap" style="padding:14px 16px">
      <div class="search grow" style="min-width:220px">${ic('search')}<input type="search" id="a-q" placeholder="Search invoice, PO, vendor, person or text" value="${esc(S8.q)}" aria-label="Search the audit log"></div>
      <label class="row gap-s small sec">Dates<select id="a-r" data-act="a8" data-f="range">${[7, 30, 90].map(n => `<option value="${n}" ${S8.range === n ? 'selected' : ''}>Last ${n} days</option>`).join('')}</select></label>
      <label class="row gap-s small sec">Actor<select id="a-a" data-act="a8" data-f="actor"><option value="all">Anyone</option><option ${S8.actor === 'System' ? 'selected' : ''}>System</option><option ${S8.actor === 'AI model' ? 'selected' : ''}>AI model</option><option ${S8.actor === 'Human' ? 'selected' : ''}>Human</option></select></label>
      <label class="row gap-s small sec">Person<select id="a-u" data-act="a8" data-f="user">${users.map(u => `<option value="${u}" ${S8.user === u ? 'selected' : ''}>${u === 'all' ? 'Anyone' : u}</option>`).join('')}</select></label>
      <label class="row gap-s small sec">Event<select id="a-t" data-act="a8" data-f="type"><option value="all">All events</option>${EVT_TYPES.map(t => `<option ${S8.type === t ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Time</th><th>Actor</th><th>Event</th><th>Object</th><th>Outcome</th><th></th></tr></thead><tbody>${rows || `<tr><td colspan="6"><div class="empty"><h4>No events match</h4><p>Clear the filters to see everything.</p><p style="margin-top:10px"><button class="btn" data-act="a8clear">Clear filters</button></p></div></td></tr>`}</tbody></table></div>
    <div class="pager"><span>Showing ${shown.length} of ${list.length} events, newest first</span>${shown.length < list.length ? `<button class="btn sm right" data-act="a8more">Show more</button>` : ''}</div></div></div>`;
}
function s8After() { const q = $('#a-q'); if (q) q.oninput = () => { STATE8.q = q.value; STATE8.limit = 30; const p = q.selectionStart; route(true); const n = $('#a-q'); n.focus(); n.setSelectionRange(p, p); }; }
document.addEventListener('change', e => { const t = e.target.closest('[data-act="a8"]'); if (t) { STATE8[t.dataset.f] = t.dataset.f === 'range' ? +t.value : t.value; STATE8.limit = 30; route(true); } });
ACT.auditRow = (t, e) => { if (e.target.closest('a')) return; const k = t.dataset.k; STATE8.open.has(k) ? STATE8.open.delete(k) : STATE8.open.add(k); route(true); };
ACT.viewJson = (t, e) => { e.preventDefault(); const pre = t.nextElementSibling; pre.hidden = !pre.hidden; };
ACT.a8clear = () => { Object.assign(STATE8, { actor: 'all', type: 'all', user: 'all', q: '', inv: null, range: 90 }); route(true); };
ACT.a8more = () => { STATE8.limit += 30; route(true); };
ACT.clearInv = () => { STATE8.inv = null; route(true); };
ACT.auditFor = t => { STATE8.inv = t.dataset.inv; STATE8.q = ''; STATE8.type = 'all'; STATE8.actor = 'all'; STATE8.user = 'all'; STATE8.open.clear(); };
ACT.objLink = t => { if (t.dataset.kind === 'Invoice') { /* navigates via href */ } };
ACT.auditExport = t => { toast(`Audit log exported as ${t.dataset.f}. The export itself is recorded below.`); AUDIT.unshift({ ts: new Date(TODAY.getTime() + 1000000), actor: { t: 'Human', n: ROLES[S.role].name }, type: 'Export', summary: `Exported the audit log (${t.dataset.f}), ${auditFiltered().length} events`, obj: { k: 'Export', id: 'audit.' + t.dataset.f.toLowerCase(), href: '#s8' }, outcome: null, payload: { filter: 'Current filters', rows: auditFiltered().length } }); route(true); };
