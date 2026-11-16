/* ===== S3 Live run view: simulated pipeline with timers ===== */
const RUN = { tok: 0, key: 'si05', speed: 1, log: [], lf: 'all', paused: false, done: false, timers: [], t0: 0, tick: null, open: new Set() };
const sleep = ms => new Promise(r => { RUN.timers.push(setTimeout(r, ms / RUN.speed)); });
function stopRun() { RUN.tok++; RUN.timers.forEach(clearTimeout); RUN.timers = []; clearInterval(RUN.tick); }

const SEV_NODE = { pass: 'check', note: 'check', review: 'warn', hold: 'pause', reject: 'x' };
function stageHTML(s) {
  return `<div class="stage pending" id="st-${s.n}" data-act="stageToggle" data-n="${s.n}"><div class="node" id="nd-${s.n}">${s.n}</div><i class="fill"></i><div class="body"><div class="t"><span>${s.name}</span><span class="dur" id="du-${s.n}"></span></div><div class="d">${s.desc}</div><div class="res" id="rs-${s.n}" hidden></div><div class="io" id="io-${s.n}"></div></div></div>`;
}
function renderS3(arg) {
  const key = INV[arg] ? arg : (INV[ALIAS[arg]] ? ALIAS[arg] : 'si05'); RUN.key = key; const inv = INV[key];
  return `
  <div class="card run-head" id="run-head">
    <div class="grow" style="min-width:230px"><div class="upper">Live run</div><div class="big" id="rh-title">${esc(inv.file)}</div><div class="small muted"><span class="mono">${inv.run}</span> · <span id="rh-vi">Vendor and invoice number: Reading…</span></div></div>
    <div><div class="upper">Elapsed</div><div class="timer" id="rh-timer">0.0 s</div></div>
    <div id="rh-conn" class="chip s-auto"><span class="live-dot" style="width:7px;height:7px"></span>Live</div>
    <div class="row wrap">
      <div class="seg" role="group" aria-label="Pacing speed" data-tip="Display pacing for the demo. Fast stages are slowed so you can watch them."><button data-act="pace" data-s="0.5" aria-pressed="${RUN.speed === 0.5}">0.5x</button><button data-act="pace" data-s="1" aria-pressed="${RUN.speed === 1}">1x</button><button data-act="pace" data-s="2" aria-pressed="${RUN.speed === 2}">2x</button></div>
      <button class="btn" id="btn-cancel" data-act="cancelRun">${ic('cancel')}Cancel run</button>
      <button class="btn" id="btn-again" data-act="runAgain">${ic('refresh')}Run again</button>
      <a class="btn primary" id="btn-open" href="#s4-${key}" hidden>Open full decision ${ic('arrow-r')}</a>
    </div>
  </div>
  <div class="live-cols">
    <div class="card pipe" aria-label="Pipeline stages">${STAGES.map(stageHTML).join('')}</div>
    <div class="card canvas" id="canvas">
      <div class="row" style="align-items:flex-start;gap:14px;margin-bottom:14px">
        <div class="docthumb ${inv.doc === 'scanned' ? 'scanned' : ''}" data-act="zoomDoc" data-tip="Click to open a larger preview"><i style="top:10px;width:30px;background:${HUES[inv.vendor]}"></i><i style="top:24px;width:44px"></i><i style="top:38px"></i><i style="top:46px"></i><i style="top:54px;width:36px"></i><i style="top:70px;width:30px;left:auto;right:8px"></i></div>
        <div class="grow"><div class="row wrap gap-s"><h3 style="font-size:15px">Extracted fields</h3>${inv.doc === 'scanned' ? '<span class="pill accent">Scanned image</span>' : '<span class="pill">Text PDF</span>'}</div>
        <p class="small sec" style="margin-top:3px">${inv.doc === 'scanned' ? 'We read this by looking at the image, so some values carry less confidence.' : 'Read from the text layer of the PDF and confirmed against the page image.'} Fields appear as each stage finishes.</p></div>
      </div>
      <div class="fgrid" id="fgrid"></div>
      <h3 style="font-size:13.5px;margin:18px 0 8px">Line items</h3>
      <div class="tbl-wrap"><table class="tbl lines-t"><thead><tr><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Amount</th><th class="r">GST</th></tr></thead><tbody id="lines"></tbody></table></div>
      <h3 style="font-size:13.5px;margin:18px 0 8px">Bank block</h3>
      <div class="bank" id="bankb"><div class="shimmer" style="height:14px;width:55%"></div></div>
      <div class="decide" id="decide"></div>
    </div>
    <div class="log" aria-label="Streaming log">
      <div class="log-h">${ic('scroll', 'sm')}Streaming log<span class="right row gap-s"><span class="seg" id="lf">${['all', 'info', 'pass', 'warn', 'fail'].map(l => `<button class="${RUN.lf === l ? 'on' : ''}" data-act="logFilter" data-l="${l}">${l[0].toUpperCase() + l.slice(1)}</button>`).join('')}</span><button class="icon-btn" style="background:#15213f;border-color:#2a3d6e;color:#cdd8f3;width:28px;height:28px" data-act="copyLog" aria-label="Copy log">${ic('copy', 'sm')}</button></span></div>
      <div class="log-b" id="logb" role="log" aria-live="off"></div>
      <div class="log-f"><span id="log-count">0 events</span><button class="btn sm ghost" id="btn-pause" data-act="pauseScroll" style="color:#9fb0d4;border-color:#2a3d6e">Pause scroll</button><span class="right">Same events as the audit log</span></div>
    </div>
  </div>`;
}

const LV = { info: 'info', pass: 'check-circle', warn: 'warn', fail: 'x-circle' };
function logLine(stage, level, msg, pace) {
  const clk = new Date(2026, 10, 16, 10, 41, 2 + Math.floor((performance.now() - RUN.t0) * RUN.speed / 1000));
  const e = { t: pad(clk.getHours()) + ':' + pad(clk.getMinutes()) + ':' + pad(clk.getSeconds()), stage, level, msg, pace }; RUN.log.push(e); appendLog(e);
}
function logHTML(e) { return `<div class="ll l-${e.level} ${e.pace ? 'pace' : ''}"><span class="ts">${e.t}</span><span class="st">${e.stage ? '[S' + e.stage + ']' : '[run]'}</span>${ic(LV[e.level])}<span class="m">${esc(e.msg)}</span></div>`; }
function appendLog(e) {
  const b = $('#logb'); if (!b) return; $('#log-count').textContent = RUN.log.length + ' events';
  if (RUN.lf !== 'all' && RUN.lf !== e.level) return; b.insertAdjacentHTML('beforeend', logHTML(e)); if (!RUN.paused) b.scrollTop = b.scrollHeight;
}
function sevOfLevel(s) { return s === 'pass' ? 'pass' : s === 'note' ? 'warn' : 'fail'; }

function setStage(n, st, o = {}) {
  const el = $('#st-' + n); if (!el) return; el.className = 'stage ' + st + (o.sev ? ' sev-' + o.sev : '') + (RUN.open.has(n) ? ' open' : '');
  const nd = $('#nd-' + n);
  if (st === 'running') nd.innerHTML = ic('spinner', 'spin'); else if (st === 'done') nd.innerHTML = ic(SEV_NODE[o.sev] || 'check'); else nd.textContent = n;
  if (o.dur != null) $('#du-' + n).textContent = o.dur.toFixed(1) + ' s';
  if (o.msg) { const r = $('#rs-' + n); r.hidden = false; r.textContent = o.msg; }
  if (o.io) $('#io-' + n).innerHTML = o.io;
}
function stageIO(inv, d, n) {
  const v = V(inv.vendor), T = rows => `<table>${rows.map(r => `<tr><td>${r[0]}</td><td>${esc(r[1])}</td></tr>`).join('')}</table>`;
  const L = {
    1: [[['File', inv.file], ['Source', 'Sample picker']], [['Pages', '1'], ['Document type', inv.doc === 'scanned' ? 'Scanned image' : 'Text PDF'], ['Seen before', 'No (new file hash)']]],
    2: [[['Page images', '1 at 150 dpi'], ['Text layer', inv.doc === 'scanned' ? 'None' : 'Found']], [['Fields read', d.fields.length], ['Line items', d.lines.length], ['Lowest model confidence', Math.min(...d.fields.map(f => f.mc ?? 1)).toFixed(2)]]],
    3: [[['Raw date', d.fields[2].raw || inv.date], ['Money', 'Read as text']], [['Invoice date', inv.date + (inv.key === 'si05' ? ' (day-first)' : '')], ['Money', 'Stored as integer paise'], ['Invoice number', 'Canonical ' + inv.invNo.replace(/[^A-Za-z0-9]/g, '').toUpperCase()], ['Lowest confidence', d.lowest.toFixed(2)]]],
    4: [[['Vendor name', v.name], ['GSTIN', v.gstin]], [['Vendor ID', v.id], ['Status', 'Approved'], ['Bank', inv.key === 'si06' ? 'Does not match the master' : inv.key === 'si05' ? 'None on invoice' : 'Matches the master']]],
    5: [[['History searched', '142 earlier invoices'], ['Vendor', v.short]], [['Similarity', d.dup.score.toFixed(2)], ['Closest', d.dup.closest ? d.dup.closest.invNo : 'none']]],
    6: [[['PO reference', inv.po === '—' ? 'Not on invoice' : inv.po], ['Open POs for vendor', inv.key === 'si05' ? '2' : '1+']], [['PO', d.po.id], ['Method', d.po.method + (d.po.method === 'Implied' ? ' (96%, runner-up 14%)' : '')], ['Lines aligned', d.rows.filter(r => r.ti).length], ['Billed before', d.cum.before.toFixed(0) + '% of PO']]],
    7: [[['Aligned lines', d.rows.filter(r => r.ti).length], ['Rule set', 'Version 14']], [['Passed', d.rules.filter(r => r.stage === 7 && r.sev === 'pass').length + ' of 7'], ['Flagged', d.rules.filter(r => r.stage === 7 && r.sev !== 'pass').map(r => r.id).join(', ') || 'none']]],
    8: [[['Rule results', '16'], ['Rule', 'Worst severity wins']], [['Decision', OUT[inv.outcome].long], ['Driving rules', d.rules.filter(r => r.sev === d.sev && r.sev !== 'pass').map(r => r.id).join(', ') || 'none'], ['Exposure', inv.exposure ? inr(inv.exposure) : 'None']]],
    9: [[['Decision', OUT[inv.outcome].long], ['Facts', 'Rule results only']], [['Headline', d.headline], ['Draft', d.draft ? d.draft.title : 'None needed']]],
  }[n];
  const rl = d.rules.filter(r => r.stage === n);
  return `<h5>Input</h5>${T(L[0])}<h5>Output</h5>${T(L[1])}${rl.length ? `<h5>Rules at this stage</h5>${rl.map(r => `<div class="rl">${sevIcon(r.sev)}<span>${esc(r.name)}<span class="rid">${r.id}</span></span></div>`).join('')}` : ''}`;
}

function fieldCard(f, i, state) {
  if (state === 'empty') return `<div class="fcard empty" id="fc-${i}"><div class="l">${f.label}</div><div class="v shimmer"></div></div>`;
  const shown = state === 'raw' ? (f.raw || f.val) : f.val, c = state === 'raw' ? f.mc : f.conf;
  const amber = state === 'norm' && (f.amber || (c != null && c < 0.9));
  const tipw = state === 'norm' && f.why ? ` data-tip="${esc(f.why)}"` : '';
  return `<div class="fcard ${amber ? 'amber' : ''}" id="fc-${i}"${tipw}><div class="l"><span>${f.label}</span><span class="row gap-s">${state === 'norm' && f.boost ? '<span class="boost">raised</span>' : ''}${confChip(c)}</span></div><div class="v">${esc(shown)}</div>${state === 'norm' && f.why && (amber || f.boost) ? `<div class="why">${esc(f.why)}</div>` : ''}</div>`;
}

async function runPipeline(key) {
  stopRun(); const tok = ++RUN.tok; const inv = INV[key], d = buildDetail(inv), v = V(inv.vendor); const alive = () => RUN.tok === tok;
  RUN.log = []; RUN.done = false; RUN.t0 = performance.now();
  const g = id => $(id);
  g('#logb').innerHTML = ''; g('#log-count').textContent = '0 events';
  g('#fgrid').innerHTML = d.fields.map((f, i) => fieldCard(f, i, 'empty')).join(''); g('#lines').innerHTML = ''; g('#bankb').innerHTML = '<div class="shimmer" style="height:14px;width:55%"></div>';
  g('#decide').classList.remove('show'); g('#decide').className = 'decide'; g('#btn-open').hidden = true; g('#btn-cancel').hidden = false; g('#rh-vi').textContent = 'Vendor and invoice number: Reading…';
  const conn = g('#rh-conn'); conn.className = 'chip s-auto'; conn.innerHTML = '<span class="live-dot" style="width:7px;height:7px"></span>Live';
  g('#rh-timer').textContent = '0.0 s'; STAGES.forEach(s => { setStage(s.n, 'pending'); $('#rs-' + s.n).hidden = true; $('#du-' + s.n).textContent = ''; $('#io-' + s.n).innerHTML = ''; });
  clearInterval(RUN.tick); RUN.tick = setInterval(() => { const t = $('#rh-timer'); if (t && !RUN.done) t.textContent = ((performance.now() - RUN.t0) * RUN.speed / 1000).toFixed(1) + ' s'; }, 100);
  logLine(0, 'info', `Run ${inv.run} started for ${inv.file}`);
  const stage = async (n, fn) => {
    if (!alive()) return false; const t0 = performance.now(); setStage(n, 'running'); logLine(n, 'info', `${STAGES[n - 1].name} started`); await fn(); if (!alive()) return false;
    const sev = n === 1 || n === 2 ? 'pass' : n === 8 || n === 9 ? d.sev : d.stageSev(n);
    setStage(n, 'done', { sev, dur: (performance.now() - t0) * RUN.speed / 1000, msg: d.stageMsg[n], io: stageIO(inv, d, n) });
    logLine(n, sevOfLevel(sev) === 'pass' ? 'pass' : sevOfLevel(sev), d.stageMsg[n]); await sleep(120); return alive();
  };
  const ruleLogs = async ids => { for (const r of d.rules.filter(x => ids.includes(x.id))) { if (!alive()) return; logLine(r.stage, sevOfLevel(r.sev), `${r.id} ${r.name}: ${r.sev.toUpperCase()}. ${r.msg}`); await sleep(190); } };

  if (!await stage(1, async () => {
    await sleep(380); logLine(1, 'info', `File stored: ${inv.file} (${inv.doc === 'scanned' ? '412' : '38'} KB, 1 page)`); await sleep(360);
    logLine(1, 'info', inv.key === 'si04' ? 'SHA-256 7be1…a90c differs from every earlier file (different image of the same invoice)' : 'SHA-256 3f9a…c1d2 not seen before'); await sleep(360);
    logLine(1, inv.doc === 'scanned' ? 'warn' : 'pass', inv.doc === 'scanned' ? 'Fewer than 50 text characters per page: scanned image. Using vision.' : 'Text layer found. Document looks like an invoice.');
    logLine(1, 'info', 'Display pacing: minimum 600 ms per stage', true);
  })) return;

  if (!await stage(2, async () => {
    logLine(2, 'info', `Reading page image with vision model (vision-llm-v3${STATE2.opts.cache ? ', saved result' : ''})`); await sleep(520);
    for (let i = 0; i < d.fields.length; i++) {
      if (!alive()) return; const f = d.fields[i]; const el = $('#fc-' + i); if (el) { el.outerHTML = fieldCard(f, i, 'raw'); $('#fc-' + i).classList.add('pop-in'); }
      if (f.k === 'vendor') { RUN.vtxt = inv.vname; } if (f.k === 'inv') $('#rh-vi').textContent = `${inv.vname} · invoice ${inv.invNo}`;
      logLine(2, f.mc != null && f.mc < 0.9 ? 'warn' : 'info', `Found ${f.label}: ${f.raw || f.val} (confidence ${f.mc == null ? 'n/a' : f.mc.toFixed(2)})`); await sleep(330);
    }
    for (let i = 0; i < d.lines.length; i++) {
      if (!alive()) return; const l = d.lines[i];
      $('#lines').insertAdjacentHTML('beforeend', `<tr class="fade-in"><td>${esc(l.desc)}</td><td class="r num">${l.qty} ${l.uom}</td><td class="r num">${inr2(l.price)}</td><td class="r num">${inr2(l.amt)}</td><td class="r num">${l.rate}%</td></tr>`);
      logLine(2, 'info', `Line ${i + 1}: ${l.desc} · ${l.qty} ${l.uom} × ${inr2(l.price)}`); await sleep(420);
    }
    const bi = d.vendorP.bankInv; $('#bankb').innerHTML = bi ? `<div class="fade-in"><div class="row wrap"><b>${esc(bi.bank)}</b><span class="mono small">A/c ${esc(bi.acct)}</span><span class="mono small">IFSC ${esc(bi.ifsc)}</span></div>${inv.key === 'si06' ? '<div class="small" style="margin-top:6px;color:var(--review-fg)">Footer says: "Our bank details have changed with effect from 1 Nov 2026."</div>' : ''}</div>` : '<div class="fade-in sec small">No bank details printed on this invoice.</div>';
    logLine(2, inv.key === 'si06' ? 'warn' : 'info', bi ? `Bank block read: ${bi.bank}, account ending ${bi.acct.slice(-4)}${inv.key === 'si06' ? '. Bank change notice found.' : ''}` : 'No bank block on the invoice');
    if (inv.doc === 'scanned') { logLine(2, 'pass', 'Second pass with a different image order: amounts agree'); await sleep(260); }
  })) return;

  if (!await stage(3, async () => {
    await sleep(300);
    for (let i = 0; i < d.fields.length; i++) { const f = d.fields[i]; const changed = f.raw != null || f.boost || f.amber || f.why; if (!changed) continue; if (!alive()) return; const el = $('#fc-' + i); if (el) { el.outerHTML = fieldCard(f, i, 'norm'); $('#fc-' + i).classList.add('flash'); }
      logLine(3, f.boost ? 'pass' : f.amber ? 'warn' : 'info', f.boost ? `${f.label}: confidence ${f.mc.toFixed(2)} raised to ${f.conf.toFixed(2)} because the numbers add up` : `${f.label}: normalised to ${f.val}${f.amber ? ` (confidence ${f.conf == null ? 'n/a' : f.conf.toFixed(2)})` : ''}`); await sleep(340); }
    d.fields.forEach((f, i) => { const el = $('#fc-' + i); if (el && !el.classList.contains('flash') && f.conf !== f.mc) { } });
    for (let i = 0; i < d.fields.length; i++) { const f = d.fields[i]; if (!(f.raw != null || f.boost || f.amber || f.why)) { const el = $('#fc-' + i); if (el) el.outerHTML = fieldCard(f, i, 'norm'); } }
    logLine(3, 'info', 'Money converted to integer paise. Invoice number canonical form ' + inv.invNo.replace(/[^A-Za-z0-9]/g, '').toUpperCase()); await sleep(260);
    await ruleLogs(['R01', 'R02', 'R03']);
  })) return;

  if (!await stage(4, async () => {
    await sleep(250); logLine(4, 'info', 'Matching vendor against the master list (6 vendors)'); await sleep(380);
    logLine(4, 'pass', `Matched ${v.name} by GSTIN ${v.gstin}`); await sleep(300);
    if (inv.key === 'si06') { const b = $('#bankb'); b.insertAdjacentHTML('beforeend', `<div class="row gap-s fade-in" style="margin-top:8px"><span class="chip s-hold">${ic('pause-circle')}Does not match the bank on file</span><span class="small muted">On file: ${v.bank}, A/c ending ${v.acct.slice(-4)}</span></div>`); }
    else if (d.vendorP.bankInv) $('#bankb').insertAdjacentHTML('beforeend', `<div class="row gap-s fade-in" style="margin-top:8px"><span class="chip s-auto">${ic('check-circle')}Matches the bank on file</span></div>`);
    await ruleLogs(['R04', 'R05']);
  })) return;

  if (!await stage(5, async () => {
    await sleep(250); logLine(5, 'info', 'Comparing with 142 earlier invoices'); await sleep(520);
    if (inv.key === 'si04') { logLine(5, 'warn', 'Canonical number BL-377 equals BL/2026/0377 (serial token 377)'); await sleep(300); logLine(5, 'fail', 'Closest match BL/2026/0377, similarity 1.00 (amount, number, date, PO, items all match)'); }
    else logLine(5, d.dup.score >= 0.6 ? 'warn' : 'pass', `Closest earlier invoice ${d.dup.closest ? d.dup.closest.invNo : 'none'}, similarity ${d.dup.score.toFixed(2)}`);
    await sleep(260); await ruleLogs(['R06']);
  })) return;

  if (!await stage(6, async () => {
    await sleep(250);
    if (inv.key === 'si05') {
      logLine(6, 'warn', 'No PO reference found. Scoring the 2 open POs for Greenleaf'); await sleep(450);
      logLine(6, 'info', 'PO-2026-1007: item descriptions 10%, prices 0% match, score 0.14'); await sleep(450);
      logLine(6, 'pass', 'PO-2026-1005: tea and sugar at exactly the PO prices, score 0.96 (runner-up gap 0.82, needs 0.20)'); await sleep(350);
    } else { logLine(6, 'pass', `Found ${d.po.id} on the invoice (${inv.key === 'si02' ? 'written as "1002/2026", normalised' : 'explicit match'})`); await sleep(320); }
    for (const r of d.rows.filter(r => r.ti)) { if (!alive()) return; logLine(6, r.sev === 'pass' ? 'info' : 'warn', `Aligned "${r.il}" to ${r.pl}: ordered ${r.ord}, billed before ${r.bb}, this invoice ${r.ti}`); await sleep(260); }
    logLine(6, d.cum.after > 100.5 ? 'warn' : 'info', `Cumulative position: ${d.cum.before.toFixed(0)}% billed before, ${d.cum.after.toFixed(0)}% after this invoice`); await sleep(280);
    await ruleLogs(['R07', 'R08', 'R09']);
  })) return;

  if (!await stage(7, async () => { await sleep(200); await ruleLogs(['R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R16']); })) return;

  if (!await stage(8, async () => { await sleep(300); logLine(8, 'info', 'Collecting 16 rule results. The worst severity wins: REJECT, HOLD, REVIEW, NOTE, PASS'); await sleep(420); logLine(8, sevOfLevel(d.sev) === 'pass' ? 'pass' : sevOfLevel(d.sev), `Worst severity ${d.sev.toUpperCase()}. Decision: ${OUT[inv.outcome].long}${inv.exposure ? '. Exposure ' + inr(inv.exposure) : ''}`); })) return;

  if (!await stage(9, async () => { await sleep(300); logLine(9, 'info', 'Writing the explanation from rule facts (template, wording checked)'); await sleep(380); if (d.draft) { logLine(9, 'info', `Drafted: ${d.draft.title}. Nothing is sent automatically`); await sleep(260); } logLine(9, 'pass', 'Decision saved to the audit log'); })) return;

  /* done */
  RUN.done = true; clearInterval(RUN.tick); const el = ((performance.now() - RUN.t0) * RUN.speed / 1000);
  $('#rh-timer').textContent = el.toFixed(1) + ' s'; logLine(0, 'pass', `Run completed in ${el.toFixed(0)} s`);
  const dc = $('#decide'); dc.className = 'decide d-' + inv.outcome;
  dc.innerHTML = `${chip(inv.outcome, true)}<div class="grow" style="min-width:220px"><div style="font-family:var(--f-head);font-weight:700;font-size:15px;line-height:1.35">${esc(d.headline)}</div><div class="small muted" style="margin-top:3px">Completed in ${el.toFixed(0)} s${inv.exposure ? ' · exposure ' + inr(inv.exposure) : ''}${inv.owner ? ' · assigned to ' + inv.owner : ''}</div></div><a class="btn primary" href="#s4-${key}">See the full explanation ${ic('arrow-r')}</a>`;
  requestAnimationFrame(() => dc.classList.add('show'));
  $('#btn-open').hidden = false; $('#btn-cancel').hidden = true; $('#canvas').dataset.state = 'done'; document.body.dataset.s3 = 'done';
  const cn = $('#rh-conn'); if (cn) { cn.className = 'chip s-none'; cn.innerHTML = 'Completed'; }
}
function s3After() { document.body.dataset.s3 = 'running'; runPipeline(RUN.key); }

ACT.stageToggle = t => { const n = +t.dataset.n; RUN.open.has(n) ? RUN.open.delete(n) : RUN.open.add(n); t.classList.toggle('open'); };
ACT.runAgain = () => { document.body.dataset.s3 = 'running'; runPipeline(RUN.key); };
ACT.cancelRun = () => { stopRun(); RUN.done = true; STAGES.forEach(s => { const e = $('#st-' + s.n); if (e && e.classList.contains('running')) { e.className = 'stage pending'; $('#nd-' + s.n).textContent = s.n; } }); logLine(0, 'warn', 'Run cancelled by user. No decision was made.'); const cn = $('#rh-conn'); cn.className = 'chip s-error'; cn.innerHTML = 'Cancelled'; $('#btn-cancel').hidden = true; document.body.dataset.s3 = 'cancelled'; };
ACT.pace = t => { RUN.speed = +t.dataset.s; $$('[data-act="pace"]').forEach(b => b.setAttribute('aria-pressed', String(b === t))); };
ACT.logFilter = t => { RUN.lf = t.dataset.l; $$('#lf button').forEach(b => b.classList.toggle('on', b === t)); const b = $('#logb'); b.innerHTML = RUN.log.filter(e => RUN.lf === 'all' || e.level === RUN.lf).map(logHTML).join(''); b.scrollTop = b.scrollHeight; };
ACT.pauseScroll = t => { RUN.paused = !RUN.paused; t.textContent = RUN.paused ? 'Resume scroll' : 'Pause scroll'; };
ACT.copyLog = () => copyText(RUN.log.map(e => `${e.t} [${e.stage ? 'S' + e.stage : 'run'}] ${e.level.toUpperCase()} ${e.msg}`).join('\n'), 'Log');
ACT.zoomDoc = () => { const inv = INV[RUN.key]; openModal(`<div class="sheet-h"><h3>${esc(inv.file)}</h3><button class="icon-btn right" data-act="closeModal" aria-label="Close">${ic('x')}</button></div><div class="paper-wrap">${paperHTML(inv, false)}</div>`); };
ACT.closeModal = () => closeModal();
