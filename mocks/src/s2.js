/* ===== S2 New run ===== */
ICONS.pause = '<path d="M9 6v12M15 6v12"/>';
const STATE2 = { expect: false, queue: [], opts: { speed: 'Normal', cache: true } };
const SAMPLE_KEYS = ['si01', 'si02', 'si03', 'si04', 'si05', 'si06', 'si07'];
const HUES = { 'V-101': '#2c55d9', 'V-102': '#0b8f8f', 'V-103': '#b4531a', 'V-104': '#3c8b3c', 'V-105': '#6b4fd1' };

function thumbSvg(inv) {
  const sc = inv.doc === 'scanned', col = HUES[inv.vendor], id = 'f' + inv.key;
  const rows = [0, 1, 2, 3].map(i => `<rect x="14" y="${62 + i * 9}" width="${70 - (i % 2) * 14}" height="3" rx="1.5" fill="#c4c9d4"/><rect x="${90}" y="${62 + i * 9}" width="22" height="3" rx="1.5" fill="#c4c9d4"/>`).join('');
  return `<svg viewBox="0 0 126 160" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><defs><filter id="${id}"><feGaussianBlur stdDeviation=".5"/></filter></defs>
  <g ${sc ? `transform="rotate(${inv.photo ? -3 : 1.6} 63 80)" filter="url(#${id})"` : ''}><rect x="4" y="4" width="118" height="152" rx="3" fill="${sc ? '#e9e5d9' : '#fffefb'}" stroke="#c9cedb"/>
  <rect x="14" y="14" width="40" height="8" rx="2" fill="${col}"/><rect x="14" y="26" width="28" height="3" rx="1.5" fill="#c4c9d4"/><rect x="82" y="14" width="30" height="5" rx="2" fill="#9aa3b5"/>
  <rect x="14" y="44" width="98" height="1.5" fill="#9aa3b5"/>${rows}<rect x="70" y="110" width="42" height="3" rx="1.5" fill="#9aa3b5"/><rect x="82" y="118" width="30" height="5" rx="2" fill="#4b5568"/>
  ${inv.key === 'si06' ? '<rect x="14" y="134" width="98" height="12" rx="2" fill="#f1d9d6" stroke="#d6453d" stroke-width=".6"/>' : '<rect x="14" y="138" width="60" height="3" rx="1.5" fill="#c4c9d4"/>'}
  ${inv.key === 'si05' ? '<rect x="20" y="40" width="46" height="14" rx="2" fill="none" stroke="#b3261e" stroke-width="1.6" transform="rotate(-8 43 47)"/><ellipse cx="94" cy="116" rx="16" ry="6" fill="#222" opacity=".55"/>' : ''}</g></svg>`;
}

function renderS2() {
  const q = STATE2.queue;
  const cards = SAMPLE_KEYS.map(k => {
    const i = INV[k]; const ran = RUNS.some(r => r.key === k);
    return `<div class="card sample"><div class="thumb">${thumbSvg(i)}</div>
      <div class="row gap-s wrap"><span class="tag">${i.code}</span><span class="tag">${V(i.vendor).short}</span>${i.doc === 'scanned' ? '<span class="pill accent">Scanned</span>' : '<span class="pill">Text PDF</span>'}${ran ? '<span class="pill" data-tip="This sample has been run before">Run before</span>' : ''}</div>
      <div><h4>${esc(i.invNo)}</h4><p class="small sec" style="margin-top:2px">${esc(i.sampleDesc)}</p></div>
      ${STATE2.expect ? `<div class="row gap-s small sec fade-in">Expected: ${chip(i.outcome)}</div>` : ''}
      <button class="btn primary" data-act="runSample" data-k="${k}" style="margin-top:auto">${ic('play', 'sm')}Run this sample</button></div>`;
  }).join('');
  const queue = q.length ? `<div class="card flat"><div class="card-h" style="padding-bottom:6px"><h3>Upload queue</h3><span class="muted small">${q.filter(x => x.ok).length} ready</span></div>${q.map((f, i) => `<div class="q-item"><span>${ic(f.ok ? 'file' : 'warn', f.ok ? '' : 'c-reject')}</span><div class="trunc"><div class="trunc"><b>${esc(f.name)}</b></div>${f.err ? `<div class="tiny" style="color:var(--reject-fg)">${esc(f.err)}</div>` : ''}</div><div>${f.ok ? `<div class="bar"><i style="width:${f.p}%"></i></div>` : ''}</div><span class="small muted nowrap">${f.size}</span><span class="row gap-s"><span class="chip ${f.ok ? (f.p >= 100 ? 's-auto' : 's-running') : 's-reject'}">${f.ok ? (f.p >= 100 ? 'Ready' : 'Uploading') : 'Rejected'}</span><button class="icon-btn" data-act="rmq" data-i="${i}" aria-label="Remove ${esc(f.name)}">${ic('x', 'sm')}</button></span></div>`).join('')}</div>` : '';
  return `${pageHead('New run', 'Drop an invoice or pick a sample. Ledgerlight reads it, checks it against vendor and PO data, and gives a decision with reasons. Nothing is paid or sent automatically.', `<a class="btn ghost" href="#s1">Recent runs ${ic('arrow-r', 'sm')}</a>`)}
  <div class="stack" style="gap:18px">
    <label class="drop" id="dropzone" for="file-in"><div class="ico">${ic('upload', 'lg')}</div><h3>Drag an invoice PDF here or <span style="color:var(--accent-fg);text-decoration:underline">browse</span></h3><p class="sec small">Up to 10 PDFs, 10 MB and 10 pages each. Scanned images and phone photos work too.</p><input id="file-in" type="file" accept="application/pdf" multiple hidden></label>
    ${queue}
    <details class="card" style="padding:0"><summary style="padding:13px 18px;cursor:pointer;font-weight:700;list-style:none;display:flex;gap:8px;align-items:center">${ic('sliders')}Options<span class="muted small" style="font-weight:500">Speed: ${STATE2.opts.speed} · Saved AI results: ${STATE2.opts.cache ? 'on' : 'off'}</span></summary>
      <div class="card-b row wrap gap-l" style="border-top:1px solid var(--line)"><div class="field-l">Processing speed<div class="seg" role="group">${['Slow for demo', 'Normal', 'Fast'].map(s => `<button aria-pressed="${STATE2.opts.speed === s}" data-act="optSpeed" data-s="${s}">${s}</button>`).join('')}</div></div>
      <label class="row" style="margin-top:18px"><button class="toggle" role="switch" aria-checked="${STATE2.opts.cache}" data-act="optCache" aria-label="Use saved AI results"></button><span><b>Use saved AI results</b><br><span class="small muted">Replays the stored extraction so a demo is repeatable and works offline.</span></span></label></div></details>
    <div class="row wrap"><div><h2 style="font-size:18px">Sample invoices</h2><p class="sec small">Seven invoices that cover every outcome. Pick one to watch it run.</p></div>
      <label class="row right small sec" style="cursor:pointer"><button class="toggle" role="switch" aria-checked="${STATE2.expect}" data-act="toggleExpect" aria-label="Show what to expect"></button>Show what to expect</label></div>
    <div class="samples">${cards}</div>
    <div class="row wrap"><button class="btn primary lg" data-act="startQueue" ${q.some(f => f.ok) ? '' : 'disabled'}>Start processing</button><span class="small muted">${q.some(f => f.ok) ? 'The first file opens in the live run view.' : 'Add a PDF or run a sample to begin.'}</span></div>
  </div>`;
}
function s2After() {
  const dz = $('#dropzone'), fi = $('#file-in'); if (!dz) return;
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('over'); dz.querySelector('h3').firstChild.textContent = 'Drop to upload '; }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('over'); }));
  dz.addEventListener('drop', e => addFiles([...e.dataTransfer.files]));
  fi.addEventListener('change', () => addFiles([...fi.files]));
}
function addFiles(files) {
  files.slice(0, 10).forEach(f => {
    const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf'; const big = f.size > 10 * 1048576;
    const o = { name: f.name, size: (f.size / 1048576 >= 1 ? (f.size / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(f.size / 1024)) + ' KB'), ok: isPdf && !big, p: 0, err: !isPdf ? 'Only PDF files are supported' : big ? 'File is larger than 10 MB' : '' };
    STATE2.queue.push(o);
    if (o.ok) { const iv = setInterval(() => { o.p = Math.min(100, o.p + 14 + Math.random() * 18); if (o.p >= 100) clearInterval(iv); if (location.hash.startsWith('#s2')) { const keep = $('#view').scrollTop; route(true); } }, 220); }
  });
  route(true);
}
ACT.toggleExpect = () => { STATE2.expect = !STATE2.expect; route(true); };
ACT.optSpeed = t => { STATE2.opts.speed = t.dataset.s; RUN.speed = { 'Slow for demo': 0.5, Normal: 1, Fast: 2 }[t.dataset.s]; route(true); $('details.card').open = true; };
ACT.optCache = () => { STATE2.opts.cache = !STATE2.opts.cache; route(true); $('details.card').open = true; };
ACT.rmq = t => { STATE2.queue.splice(+t.dataset.i, 1); route(true); };
ACT.runSample = t => { location.hash = '#s3-' + t.dataset.k; };
ACT.startQueue = () => { location.hash = '#s3-si01'; };
