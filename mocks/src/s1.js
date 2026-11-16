/* ===== S1 Dashboard ===== */
const STATE1 = { range: 30, filters: new Set(), search: '', sort: { k: 'time', d: -1 }, page: 0 };
const inRange = r => r.time >= new Date(TODAY.getTime() - STATE1.range * 86400000);
const rangeRuns = () => RUNS.filter(inRange);

function buckets() {
  const n = STATE1.range; const rr = rangeRuns();
  if (n === 7) { return Array.from({ length: 7 }, (_, i) => { const d = new Date(2026, 10, 10 + i); return { lab: fmtDS(d), s: d, e: new Date(d.getTime() + 86400000) }; }).map(b => ({ ...b, runs: rr.filter(r => r.time >= b.s && r.time < b.e) })); }
  const out = []; for (let i = 4; i >= 0; i--) { const e = new Date(2026, 10, 17 - i * 7), s = new Date(e.getTime() - 7 * 86400000); const last = new Date(e.getTime() - 86400000); out.push({ lab: fmtDS(s) + '–' + fmtDS(last).split(' ')[0] + (s.getMonth() !== last.getMonth() ? ' ' + MON[last.getMonth()] : ''), s, e }); }
  out[0].lab = '13–19 Oct'; out[1].lab = '20–26 Oct'; out[2].lab = '27 Oct–2 Nov'; out[3].lab = '3–9 Nov'; out[4].lab = '10–16 Nov';
  return out.map(b => ({ ...b, runs: rr.filter(r => r.time >= b.s && r.time < b.e) }));
}

function spark(vals, color = 'var(--accent)') {
  const w = 120, h = 26, mx = Math.max(...vals, 1), mn = Math.min(...vals, 0); const sp = mx - mn || 1;
  const pts = vals.map((v, i) => [i / (vals.length - 1) * (w - 6) + 3, h - 4 - (v - mn) / sp * (h - 9)]);
  const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${line} L${last[0]} ${h} L${pts[0][0]} ${h}Z" fill="${color}" opacity=".12"/><path d="${line}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${last[0]}" cy="${last[1]}" r="2.6" fill="${color}" stroke="var(--surface)" stroke-width="1.5"/></svg>`;
}

function kpiData() {
  const rr = rangeRuns(), n = rr.length, c = o => rr.filter(r => r.outcome === o).length;
  const str = n ? (c('auto') + c('note')) / n : 0;
  const dup = sum(rr.filter(r => r.cat === 'Duplicate').map(r => r.exposure)), over = sum(rr.filter(r => r.cat === 'Quantity or price above PO').map(r => r.exposure));
  const approved = sum(rr.filter(r => r.outcome === 'auto' || r.outcome === 'note').map(r => r.gross));
  const bk = buckets();
  return { n, str, med: median(rr.map(r => r.dur)), open: c('review') + c('hold'), rev: c('review'), hold: c('hold'), dup, over, protectedV: dup + over, approved, bk,
    sN: bk.map(b => b.runs.length), sS: bk.map(b => b.runs.length ? (b.runs.filter(r => r.outcome === 'auto' || r.outcome === 'note').length / b.runs.length) * 100 : 0), sM: bk.map(b => median(b.runs.map(r => r.dur))) };
}

function chartStack(k) {
  const bk = k.bk, W = 600, H = 250, L = 34, Rr = 8, T = 10, B = 40;
  const mx = Math.max(...bk.map(b => b.runs.length), 4), step = mx <= 8 ? 2 : mx <= 20 ? 5 : 10, top = Math.ceil(mx / step) * step;
  const iw = W - L - Rr, ih = H - T - B, bw = Math.min(54, iw / bk.length * .56);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Decisions per period by outcome">`;
  for (let v = 0; v <= top; v += step) { const y = T + ih - v / top * ih; s += `<line class="gl" x1="${L}" x2="${W - Rr}" y1="${y}" y2="${y}"/><text x="${L - 8}" y="${y + 4}" text-anchor="end">${v}</text>`; }
  bk.forEach((b, i) => {
    const cx = L + iw / bk.length * (i + .5); let y0 = T + ih;
    OUT_KEYS.forEach(o => {
      const cnt = b.runs.filter(r => r.outcome === o).length; if (!cnt) return; const hh = cnt / top * ih;
      s += `<rect class="seg-r" x="${cx - bw / 2}" y="${y0 - hh}" width="${bw}" height="${hh}" rx="2" fill="${OUT_COLOR[o]}" data-act="segFilter" data-o="${o}" data-tip="<b>${b.lab}</b><br>${OUT[o].label}: ${cnt}<br><span style='opacity:.75'>Click to filter the table</span>"/>`;
      if (hh > 15) s += `<text x="${cx}" y="${y0 - hh / 2 + 4}" text-anchor="middle" style="fill:#fff;font-weight:700;pointer-events:none">${cnt}</text>`;
      y0 -= hh;
    });
    s += `<text x="${cx}" y="${H - 20}" text-anchor="middle">${b.lab}</text><text x="${cx}" y="${H - 6}" text-anchor="middle" style="font-weight:700;fill:var(--ink-2)">${b.runs.length} total</text>`;
  });
  return s + '</svg>';
}
function chartDonut(rr) {
  const tot = rr.length || 1, R0 = 62, sw = 24, C = 2 * Math.PI * R0; let off = 0, arcs = '';
  OUT_KEYS.forEach(o => { const c = rr.filter(r => r.outcome === o).length; if (!c) return; const len = c / tot * C; arcs += `<circle class="seg-r" cx="90" cy="90" r="${R0}" fill="none" style="stroke:${OUT_COLOR[o]};stroke-width:${sw}px;stroke-linecap:butt" stroke-dasharray="${Math.max(len - 2.5, 0.5)} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 90 90)" data-act="segFilter" data-o="${o}" data-tip="<b>${OUT[o].label}</b><br>${c} invoices (${pct(c / tot * 100, 0)})"/>`; off += len; });
  const legend = OUT_KEYS.map(o => { const c = rr.filter(r => r.outcome === o).length; return `<div class="row" style="justify-content:space-between;gap:12px"><span class="row gap-s"><i style="width:10px;height:10px;border-radius:3px;background:${OUT_COLOR[o]};display:inline-block"></i>${OUT[o].label}</span><span class="num"><b>${c}</b> <span class="muted">${pct(c / tot * 100, 0)}</span></span></div>`; }).join('');
  return `<div class="row wrap" style="gap:22px;justify-content:center"><svg class="chart" viewBox="0 0 180 180" style="width:170px;flex:none" role="img" aria-label="Outcome mix donut">${arcs}<text x="90" y="88" text-anchor="middle" style="font-family:var(--f-head);font-size:28px;font-weight:800;fill:var(--ink)">${rr.length}</text><text x="90" y="106" text-anchor="middle">invoices</text></svg><div class="stack-s grow" style="min-width:170px;font-size:13px">${legend}</div></div>`;
}
function chartReasons(rr) {
  const cats = {}; rr.filter(r => r.cat).forEach(r => cats[r.cat] = (cats[r.cat] || 0) + 1);
  const items = Object.entries(cats).sort((a, b) => b[1] - a[1]); const mx = Math.max(...items.map(i => i[1]), 1);
  const W = 520, rowH = 34, H = items.length * rowH + 4, lab = 190;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Top reasons for exceptions">`;
  items.forEach(([c, n], i) => { const y = i * rowH + 4, bw = Math.max(6, n / mx * (W - lab - 44)); s += `<text x="0" y="${y + 17}" style="fill:var(--ink-2);font-size:12.5px">${esc(c)}</text><rect x="${lab}" y="${y + 5}" width="${W - lab - 44}" height="16" rx="4" fill="var(--surface-3)"/><rect class="seg-r" x="${lab}" y="${y + 5}" width="${bw}" height="16" rx="4" fill="var(--accent)" style="stroke:none" data-tip="<b>${esc(c)}</b><br>${n} invoices"/><text x="${lab + bw + 8}" y="${y + 18}" style="fill:var(--ink);font-weight:700;font-size:12.5px">${n}</text>`; });
  return s + '</svg>';
}
function chartLine(k) {
  const bk = k.bk, W = 520, H = 220, L = 34, Rr = 14, T = 14, B = 30, iw = W - L - Rr, ih = H - T - B; const vals = k.sM.map(v => v || null);
  const mn = 8, mx = 20; const X = i => L + (bk.length === 1 ? iw / 2 : i / (bk.length - 1) * iw), Y = v => T + ih - (v - mn) / (mx - mn) * ih;
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Median time to decision">`;
  [8, 12, 16, 20].forEach(v => { const y = Y(v); s += `<line class="gl" x1="${L}" x2="${W - Rr}" y1="${y}" y2="${y}"/><text x="${L - 8}" y="${y + 4}" text-anchor="end">${v}s</text>`; });
  const pts = vals.map((v, i) => v == null ? null : [X(i), Y(clamp(v, mn, mx))]).filter(Boolean);
  if (pts.length > 1) { const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(''); s += `<path d="${path}L${pts[pts.length - 1][0]} ${T + ih}L${pts[0][0]} ${T + ih}Z" fill="var(--accent)" opacity=".1"/><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`; }
  bk.forEach((b, i) => { s += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle">${b.lab.length > 9 && bk.length === 5 ? b.lab : b.lab}</text>`; });
  vals.forEach((v, i) => { if (v == null) return; const last = i === vals.length - 1; s += `<circle cx="${X(i)}" cy="${Y(clamp(v, mn, mx))}" r="${last ? 5.5 : 4}" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" data-tip="<b>${bk[i].lab}</b><br>Median ${v.toFixed(0)} s (${bk[i].runs.length} runs)"/>`; if (last) s += `<text x="${X(i)}" y="${Y(clamp(v, mn, mx)) - 12}" text-anchor="middle" style="fill:var(--ink);font-weight:700;font-size:12px">${v.toFixed(0)} s</text>`; });
  return s + '</svg>';
}

function renderS1() {
  const k = kpiData(), all = RUNS, cAll = COUNTS();
  const oldest = Math.max(...OPEN_EXC().map(r => r.age));
  const d = { 7: ['+9%', '+3 pts', '−1 s'], 30: ['+12%', '+4 pts', '−2 s'], 90: ['+12%', '+4 pts', '−2 s'] }[STATE1.range];
  const tip = `<b>Value protected</b><br>Duplicates blocked or held: ${inr(k.dup)}<br>Overbilling caught: ${inr(k.over)}`;
  return `
  ${pageHead('Dashboard', 'How accounts payable is doing, and what needs a person.', `
    <div class="seg" role="group" aria-label="Date range">${[7, 30, 90].map(n => `<button aria-pressed="${STATE1.range === n}" data-act="range" data-n="${n}">${n} days</button>`).join('')}</div>
    <button class="btn" data-act="exportCsv">${ic('download')}Export approved (CSV)</button>
    <a class="btn primary" href="#s2">${ic('plus')}Process invoice</a>`)}
  <div class="stack">
    <div class="banner" role="status">${ic('eye', 'lg')}<span class="grow"><b>${cAll.review} invoices need review, ${cAll.hold} on hold, oldest ${oldest} days.</b> The largest open exposure is ${inr(Math.max(...OPEN_EXC().map(r => r.exposure)))}.</span><a href="#s5">Open the review queue</a></div>
    <div class="kpis">
      <div class="card kpi"><div class="lab">Invoices processed</div><div class="val num">${k.n}</div><div class="sub"><span class="delta up">▲ ${d[0]}</span> vs previous ${STATE1.range} days</div>${spark(k.sN)}</div>
      <div class="card kpi hero"><div class="lab">Straight-through rate</div><div class="val num">${(k.str * 100).toFixed(0)}<small>%</small></div><div class="sub"><span class="delta up">▲ ${d[1]}</span> approved with no human touch</div>${spark(k.sS)}</div>
      <div class="card kpi"><div class="lab">Median time to decision</div><div class="val num">${k.med.toFixed(0)}<small>s</small></div><div class="sub"><span class="delta up">▼ ${d[2]}</span> est. 9 min by hand</div>${spark(k.sM)}</div>
      <div class="card kpi"><div class="lab">Open exceptions</div><div class="val num">${k.open}</div><div class="sub">${k.rev} to review · ${k.hold} on hold</div><div class="bar" style="margin-top:8px"><i style="width:${k.n ? k.open / k.n * 100 : 0}%;background:var(--review)"></i></div></div>
      <div class="card kpi" data-tip="${esc(tip)}"><div class="lab">Value protected ${ic('info', 'sm')}</div><div class="val num">${inr(k.protectedV)}</div><div class="sub">Duplicates and overbilling stopped</div></div>
      <div class="card kpi"><div class="lab">Value approved</div><div class="val num">${k.approved >= 10000000 ? '₹' + (k.approved / 10000000).toFixed(2) + '<small>Cr</small>' : k.approved >= 100000 ? '₹' + (k.approved / 100000).toFixed(1) + '<small>lakh</small>' : inr(k.approved)}</div><div class="sub">Gross, in the payment queue</div></div>
    </div>
    <div class="chart-grid">
      <div class="card cg-7"><div class="card-h"><h3>Decisions ${STATE1.range === 7 ? 'per day' : 'per week'}</h3><div class="legend right">${OUT_KEYS.map(o => `<span><i style="background:${OUT_COLOR[o]}"></i>${OUT[o].label}</span>`).join('')}</div></div><div class="card-b">${chartStack(k)}</div></div>
      <div class="card cg-5"><div class="card-h"><h3>Outcome mix</h3><span class="muted small right">Click a slice to filter</span></div><div class="card-b" style="padding-top:22px">${chartDonut(rangeRuns())}</div></div>
      <div class="card cg-7"><div class="card-h"><h3>Top reasons for exceptions</h3><span class="muted small right">Review, hold and reject</span></div><div class="card-b">${chartReasons(rangeRuns())}</div></div>
      <div class="card cg-5"><div class="card-h"><h3>Median time to decision</h3><span class="muted small right">Manual baseline: 9 min (est.)</span></div><div class="card-b">${chartLine(k)}</div></div>
    </div>
    <div class="card" id="runs-card"></div>
  </div>`;
}

const REASON_COLS = [['time', 'Run'], ['vname', 'Vendor'], ['invNo', 'Invoice no.'], ['po', 'PO'], ['gross', 'Amount'], ['outcome', 'Decision'], ['reason', 'Main reason'], ['conf', 'Confidence'], ['dur', 'Duration'], ['ovr', 'Edited']];
function filteredRuns() {
  let rr = rangeRuns(); const f = STATE1.filters;
  if (f.size) rr = rr.filter(r => f.has(r.outcome));
  const q = STATE1.search.trim().toLowerCase();
  if (q) rr = rr.filter(r => (r.vfull + ' ' + r.invNo + ' ' + (r.poInferred || r.po)).toLowerCase().includes(q));
  const { k, d } = STATE1.sort; const val = r => k === 'ovr' ? (r.overridden ? 1 : 0) : k === 'outcome' ? OUT[r.outcome].rank : k === 'po' ? r.po : r[k];
  return rr.slice().sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * d; });
}
function renderRunsCard() {
  const el = $('#runs-card'); if (!el) return;
  const base = rangeRuns(), rr = filteredRuns(), pages = Math.max(1, Math.ceil(rr.length / 25)); STATE1.page = clamp(STATE1.page, 0, pages - 1);
  const slice = rr.slice(STATE1.page * 25, STATE1.page * 25 + 25);
  const cnt = o => base.filter(r => r.outcome === o).length; const f = STATE1.filters;
  const chips = `<button class="fchip ${f.size ? '' : 'on'}" data-act="chipAll">All <span class="n">${base.length}</span></button>` + OUT_KEYS.map(o => `<button class="fchip ${f.has(o) ? 'on' : ''}" data-act="chip" data-o="${o}" aria-pressed="${f.has(o)}">${ic(OUT[o].ic, 'sm')}${OUT[o].label} <span class="n">${cnt(o)}</span></button>`).join('') + `<button class="fchip ${f.has('running') ? 'on' : ''}" data-act="chip" data-o="running">${ic('spinner', 'sm spin')}Running <span class="n">1</span></button>`;
  const showRunning = !f.size || f.has('running');
  const th = REASON_COLS.map(([k, l]) => `<th class="sortable ${k === 'gross' || k === 'dur' ? 'r' : ''}" data-act="sort" data-k="${k}">${l}${STATE1.sort.k === k ? `<span class="arr">${STATE1.sort.d > 0 ? '▲' : '▼'}</span>` : ''}</th>`).join('');
  const runRow = showRunning && STATE1.page === 0 && !STATE1.search ? `<tr class="link sev" style="--sev:var(--accent)" data-href="#s3" data-pop="<b>Running now</b><br>Meridian Logistics invoice MX-5541 is being checked against PO-2026-1009."><td><div class="mono small">${RUNNING.run}</div><div class="tiny muted">Just now</div></td><td>${esc(RUNNING.vname)}</td><td class="mono">${RUNNING.invNo}</td><td class="mono small">${RUNNING.po}</td><td class="r num">${inr2(RUNNING.gross)}</td><td>${chip('running')}</td><td class="sec" id="run-stage">Stage 6 of 9: PO match</td><td>${confChip(null)}</td><td class="r num muted">—</td><td></td></tr>` : '';
  const body = slice.map(r => `<tr class="link sev" style="--sev:${OUT_COLOR[r.outcome]}" data-href="#s4-${r.key}" data-pop="${esc(`<b>${OUT[r.outcome].long}</b><br>${buildDetail(r).headline}`)}">
    <td><div class="mono small">${r.run}</div><div class="tiny muted">${fmtDS(r.time)}, ${fmtT(r.time)}</div></td>
    <td class="nowrap">${esc(r.vname)}</td><td class="mono nowrap">${esc(r.invNo)}</td><td class="mono small nowrap">${esc(r.poInferred ? r.poInferred + '*' : r.po)}</td><td class="r num nowrap">${inr2(r.gross)}</td><td>${chip(r.outcome)}</td>
    <td class="sec" style="min-width:230px;max-width:340px">${esc(r.reason)}</td><td>${confChip(r.conf)}</td><td class="r num muted">${r.dur} s</td><td class="c">${r.overridden ? `<span data-tip="Changed by a person">${ic('edit', 'sm c-review')}</span>` : ''}</td></tr>`).join('');
  el.innerHTML = `<div class="card-h" style="padding-bottom:12px;flex-wrap:wrap"><h3>Runs</h3><div class="chips grow">${chips}</div><div class="search" style="width:240px"><span class="sr-only"></span>${ic('search')}<input type="search" id="run-search" placeholder="Search vendor, invoice or PO" value="${esc(STATE1.search)}" aria-label="Search runs"></div></div>
  <div class="tbl-wrap"><table class="tbl"><thead><tr>${th}</tr></thead><tbody>${runRow}${body || `<tr><td colspan="10"><div class="empty"><h4>No runs match these filters</h4><p>Try a different status or clear the search.</p><p style="margin-top:10px"><button class="btn" data-act="clearFilters">Clear filters</button></p></div></td></tr>`}</tbody></table></div>
  <div class="pager"><span>Showing ${slice.length} of ${rr.length} completed runs${showRunning ? ' · 1 running' : ''}</span><span class="right row gap-s"><button class="btn sm" data-act="page" data-d="-1" ${STATE1.page === 0 ? 'disabled' : ''}>Previous</button><span>Page ${STATE1.page + 1} of ${pages}</span><button class="btn sm" data-act="page" data-d="1" ${STATE1.page >= pages - 1 ? 'disabled' : ''}>Next</button><a href="#s8" style="margin-left:10px">Open the audit log</a></span></div>`;
  const si = $('#run-search'); if (si) { si.oninput = () => { STATE1.search = si.value; STATE1.page = 0; const pos = si.selectionStart; renderRunsCard(); const n = $('#run-search'); n.focus(); n.setSelectionRange(pos, pos); }; }
  $$('tr[data-href]', el).forEach(tr => tr.onclick = () => { location.hash = tr.dataset.href; });
}
function s1After() {
  renderRunsCard();
  const stages = ['Stage 3 of 9: Normalise', 'Stage 4 of 9: Vendor check', 'Stage 5 of 9: Duplicate check', 'Stage 6 of 9: PO match', 'Stage 7 of 9: Rules']; let i = 3;
  S1_TIMER = setInterval(() => { const e = $('#run-stage'); if (e) { i = (i + 1) % stages.length; e.textContent = stages[i]; } }, 2200);
}
let S1_TIMER = null;
ACT.range = t => { STATE1.range = +t.dataset.n; STATE1.page = 0; route(true); };
ACT.segFilter = t => { STATE1.filters = new Set([t.dataset.o]); STATE1.page = 0; renderRunsCard(); $('#runs-card').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
ACT.chip = t => { const o = t.dataset.o; STATE1.filters.has(o) ? STATE1.filters.delete(o) : STATE1.filters.add(o); STATE1.page = 0; renderRunsCard(); };
ACT.chipAll = () => { STATE1.filters.clear(); STATE1.page = 0; renderRunsCard(); };
ACT.clearFilters = () => { STATE1.filters.clear(); STATE1.search = ''; renderRunsCard(); };
ACT.sort = t => { const k = t.dataset.k; STATE1.sort = { k, d: STATE1.sort.k === k ? -STATE1.sort.d : -1 }; renderRunsCard(); };
ACT.page = t => { STATE1.page += +t.dataset.d; renderRunsCard(); };
ACT.exportCsv = () => { AUDIT.unshift({ ts: new Date(TODAY.getTime() + 60000), actor: { t: 'Human', n: ROLES[S.role].name }, type: 'Export', summary: 'Exported approved invoices (CSV), last ' + STATE1.range + ' days', obj: { k: 'Export', id: 'approved.csv', href: '#s1' }, outcome: null, payload: { rows: rangeRuns().filter(r => r.outcome === 'auto' || r.outcome === 'note').length, filter: 'Approved, Approved with note' } }); toast('Approved invoices exported as CSV. The export was recorded in the audit log.'); };
