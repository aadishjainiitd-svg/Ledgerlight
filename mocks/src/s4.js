/* ===== S4 Invoice decision detail ===== */
const ROLES = { clerk: { name: 'Priya Nair', label: 'AP Clerk' }, manager: { name: 'Rahul Mehta', label: 'AP Manager' } };
const REASON_CODES = ['Vendor confirmed by phone', 'PO amended by Procurement', 'Credit note promised', 'Credit note requested', 'Price agreed with Procurement', 'Extraction corrected', 'Not actually a duplicate', 'Within policy for this vendor', 'Other'];
const STATE4 = { showPassed: false, tab: 'doc', zoom: 1, hl: null };

function paperHTML(inv) {
  const d = buildDetail(inv), v = V(inv.vendor), sc = inv.doc === 'scanned', col = HUES[inv.vendor];
  const cls = 'paper' + (sc ? ' scan' : '') + (inv.photo ? ' photo' : '');
  const f = (k, t) => `<span data-f="${k}">${t}</span>`;
  const incl = inv.taxIncl;
  const lines = d.lines.map(l => `<tr><td>${esc(l.desc)}</td><td class="r">${l.qty}</td><td class="r">${inr2(l.price)}</td><td class="r">${inr2(l.amt)}</td></tr>`).join('');
  const bi = d.vendorP.bankInv;
  const poTxt = inv.po === '—' ? `<span style="color:#9a9a9a">—</span><span class="stamp" style="top:-8px;left:40px">RECEIVED</span>` : inv.key === 'si02' ? f('po', 'Ref your PO 1002/2026') : f('po', inv.po);
  return `<div class="${cls}" style="--vc:${col}">
    <div class="ph"><div><div class="vn" style="color:${col}">${esc(v.name)}</div><div style="color:#5b6477;margin-top:3px">${esc(v.addr)}<br>GSTIN ${v.gstin}</div></div><div><h5>${incl ? 'INVOICE' : 'TAX INVOICE'}</h5></div></div>
    <div class="mm"><div><span>Invoice no.</span>${f('inv', esc(inv.invNo))}</div><div><span>Date</span>${f('date', inv.key === 'si05' ? '12/11/26' : esc(inv.date))}</div><div style="position:relative"><span>PO ref</span>${poTxt}</div><div><span>Bill to</span>Aster Industries Pvt Ltd</div><div><span>Vendor</span>${f('vendor', esc(inv.vname))}</div><div><span>Currency</span>${f('cur', 'INR')}</div></div>
    <table><thead><tr><th>Description</th><th class="r">Qty</th><th class="r">${incl ? 'Rate (incl. GST)' : 'Rate'}</th><th class="r">Amount</th></tr></thead><tbody>${lines}</tbody></table>
    <div class="tot"><div><span>${incl ? 'Taxable value' : 'Subtotal'}</span>${f('sub', inr2(inv.sub))}</div><div><span>GST @ ${inv.rate}%</span>${f('tax', inr2(inv.tax))}</div><div class="g" style="position:relative"><span>${incl ? 'Total (inclusive of GST)' : 'Total'}</span>${f('total', inr2(inv.gross))}${inv.key === 'si05' ? '<span class="smudge" style="right:-8px;top:-4px"></span>' : ''}</div></div>
    ${bi ? `<div class="bk" data-f="bank"><b>Pay to</b> ${esc(bi.bank)} · A/c ${esc(bi.acct)} · IFSC ${esc(bi.ifsc)}</div>` : ''}
    ${inv.key === 'si06' ? '<div class="foot" style="color:#8a1c14;font-weight:600">Our bank details have changed with effect from 1 Nov 2026. Please remit to Riverbend Co-operative Bank, A/c 5020 0091 2334 7.</div>' : ''}
    <div class="foot">${incl ? 'All prices are inclusive of GST. ' : ''}Payment terms ${v.terms}. Subject to local jurisdiction. This is a computer generated invoice.</div></div>`;
}
const noPdf = inv => `<div class="nopdf">${ic('file', 'lg')}<b>PDF not stored for demo history</b><span class="small">This run came from the seeded history, so only the extracted data and decision are kept. Uploaded invoices keep their PDF.</span></div>`;

function canOverride(inv, action) {
  const d = buildDetail(inv), role = S.role; const hard = d.rules.some(r => r.hard && r.sev === d.sev && ['reject', 'hold'].includes(r.sev));
  if (inv.outcome === 'auto' && action === 'approve') return { ok: false, why: 'Already approved.' };
  if (hard) return role === 'manager' ? { ok: true } : { ok: false, why: 'This is a hard stop (' + d.rules.filter(r => r.hard && r.sev === d.sev).map(r => r.id).join(', ') + '). Only an AP manager can override it. Switch role in the top bar.' };
  if (action === 'approve' && role === 'clerk' && !(inv.outcome === 'review' && inv.exposure <= 10000)) return { ok: false, why: 'A clerk can approve a review item only when the exposure is ₹10,000 or less. This one is ' + inr(inv.exposure) + '.' };
  return { ok: true };
}

function decisionJSON(inv, d) {
  return JSON.stringify({ run_id: inv.run, invoice: inv.invNo, vendor_id: inv.vendor, po: d.po.id, outcome: ({ auto: 'auto_approve', note: 'approve_with_note', review: 'route_for_review', hold: 'hold_request_info', reject: 'reject' })[inv.outcome], headline: d.headline, driving_rule_ids: d.rules.filter(r => r.sev === d.sev && r.sev !== 'pass').map(r => r.id), exposure_paise: inv.exposure * 100, assigned_to: inv.owner, made_by: inv.overridden ? 'user' : 'system', config_version: 14, rules: d.rules.map(r => ({ id: r.id, severity: r.sev, message: r.msg })) }, null, 2);
}
function extractionJSON(inv, d) { return JSON.stringify({ model: 'vision-llm-v3', prompt_version: 'extract-2.4', doc_type: inv.doc, fields: Object.fromEntries(d.fields.map(f => [f.k, { value: f.val, raw_text: f.raw || f.val, model_confidence: f.mc, effective_confidence: f.conf, source: f.src }])), line_items: d.lines }, null, 2); }

function renderS4(arg) {
  const key = INV[arg] ? arg : INV[ALIAS[arg]] ? ALIAS[arg] : 'si03'; const inv = INV[key], d = buildDetail(inv), v = V(inv.vendor);
  S4KEY = key; const dsev = d.sev, sevcls = 'sev-' + inv.outcome;
  const list = QUEUE_ORDER(); const idx = list.findIndex(r => r.key === key);
  const ovr = inv.overridden ? `<div class="banner info" style="margin-bottom:12px">${ic('info', 'lg')}<span class="grow"><b>Decision changed from ${OUT[inv.overridden.from].label} to ${OUT[inv.outcome].label} by ${esc(inv.overridden.by)}, ${inv.overridden.when}.</b> Reason: ${esc(inv.overridden.code)}. ${esc(inv.overridden.text)} The original decision is preserved in the audit log.</span></div>` : '';
  const meta = `<div class="meta"><span><b>${inr2(inv.gross)}</b> gross</span><span>${esc(inv.vfull)}</span><span class="mono">${esc(inv.invNo)}</span><span><a href="#s6" data-act="openPo" data-id="${d.po.id}" class="mono">${d.po.id}${inv.poInferred ? ' (inferred)' : ''}</a></span>${inv.exposure ? `<span>Exposure <b style="color:var(--${inv.outcome === 'hold' ? 'hold' : inv.outcome === 'reject' ? 'reject' : 'review'}-fg)">${inr(inv.exposure)}</b></span>` : ''}${inv.owner && ['review', 'hold', 'reject'].includes(inv.outcome) ? `<span>Assigned to <b>${inv.owner}</b></span>` : ''}${inv.outcome === 'hold' ? '<span>SLA: 3 business days</span>' : ''}<span>${inv.overridden ? 'Overridden by ' + esc(inv.overridden.by) : 'Decided by Ledgerlight at ' + fmtT(inv.time) + ' in ' + inv.dur + ' s'}${inv.confirmedBy ? ' · confirmed by ' + esc(inv.confirmedBy) : ''}</span></div>`;
  return `
  <div class="row wrap" style="margin-bottom:12px"><a class="btn ghost sm" href="#s1">${ic('arrow-l', 'sm')}Dashboard</a><span class="muted small">Run <span class="mono">${inv.run}</span> · ${inv.ec ? `<b style="color:var(--accent-fg)">${inv.ec}</b> · ` : ''}${fmtDS(inv.time)}, ${fmtT(inv.time)}</span>
    <span class="right row gap-s">${idx >= 0 ? `<button class="icon-btn" data-act="navExc" data-d="-1" aria-label="Previous exception" ${idx === 0 ? 'disabled' : ''}>${ic('chev-l')}</button><span class="small muted">${idx + 1} of ${list.length} open exceptions</span><button class="icon-btn" data-act="navExc" data-d="1" aria-label="Next exception" ${idx === list.length - 1 ? 'disabled' : ''}>${ic('chev-r')}</button>` : ''}</span></div>
  ${ovr}
  <div class="card dcard ${sevcls}" id="dcard"><div class="grow" style="min-width:260px"><div class="row wrap gap-s" style="margin-bottom:8px">${chip(inv.outcome, true)}<span class="muted small">${OUT[inv.outcome].long}${d.rules.some(r => r.hard && r.sev === d.sev && r.sev !== 'pass') ? ' · hard stop, manager only' : ''}</span></div><h2>${esc(d.headline)}</h2>${meta}</div>
    <div class="row wrap gap-s" style="align-self:flex-start">
      <button class="btn" data-act="acceptDecision" ${inv.confirmedBy ? 'disabled' : ''}>${ic('check', 'sm')}${inv.confirmedBy ? 'Confirmed' : 'Accept decision'}</button>
      <button class="btn primary" data-act="openOverride">${ic('edit', 'sm')}Override…</button>
      <a class="btn" href="#s3-${key}">${ic('refresh', 'sm')}Re-run</a>
      <button class="btn" data-act="copyJson">${ic('copy', 'sm')}Copy JSON</button></div></div>
  <div class="m-tabs tabs" style="margin-top:12px"><button class="${STATE4.tab === 'doc' ? 'on' : ''}" data-act="s4tab" data-t="doc">Document</button><button class="${STATE4.tab === 'an' ? 'on' : ''}" data-act="s4tab" data-t="an">Analysis</button></div>
  <div class="card explain" style="margin-top:14px">${explainHTML(inv, d)}</div>
  <div class="split" data-tab="${STATE4.tab}" id="split">
    <div class="doccol card flat" style="overflow:hidden;align-self:start"><div class="pdfcol" style="box-shadow:none">
      <div class="pdf-bar">${ic('file', 'sm')}<span class="trunc grow">${esc(inv.file)}</span>${inv.doc === 'scanned' ? '<span class="pill accent">Scanned image</span>' : ''}<button class="icon-btn" data-act="zoom" data-d="-0.1" aria-label="Zoom out" style="width:28px;height:28px">−</button><span class="small num">${Math.round(STATE4.zoom * 100)}%</span><button class="icon-btn" data-act="zoom" data-d="0.1" aria-label="Zoom in" style="width:28px;height:28px">+</button><span class="small muted">Page 1 of ${inv.pages}</span></div>
      <div class="paper-wrap">${inv.pdf ? `<div style="width:${STATE4.zoom * 100}%;max-width:${560 * STATE4.zoom}px">${paperHTML(inv)}</div>` : noPdf(inv)}</div></div></div>
    <div class="stack analysis">
      ${panelFields(inv, d)}
      ${panelVendor(inv, d)}
      ${panelPO(inv, d)}
      ${panelRules(inv, d)}
      ${panelDrafts(inv, d)}
      ${panelActivity(inv, d)}
      <details class="drawer"><summary>${ic('cpu', 'sm')}Technical details<span class="muted small" style="font-weight:500">Extraction and decision JSON</span></summary><pre class="json">${esc(decisionJSON(inv, d))}\n\n${esc(extractionJSON(inv, d))}</pre></details>
    </div>
  </div>`;
}
let S4KEY = 'si03';
const QUEUE_ORDER = () => RUNS.filter(r => ['review', 'hold'].includes(r.outcome) && !r.resolved).sort((a, b) => (b.exposure * (1 + b.age)) - (a.exposure * (1 + a.age)));

function explainHTML(inv, d) {
  const li = (ico, t) => `<div class="ex-li">${ico}<span>${t}</span></div>`;
  const att = d.attention.map(t => li(ic(inv.outcome === 'reject' ? 'x-circle' : inv.outcome === 'hold' ? 'pause-circle' : inv.outcome === 'review' ? 'eye' : 'note-circle', 'c-' + inv.outcome), esc(t))).join('');
  const drv = d.rules.filter(r => r.sev === d.sev && r.sev !== 'pass').map(r => `<span class="rid" data-tip="${esc(r.name)}">${r.id}</span>`).join('');
  return `<div class="ex-blk"><h4>What we checked and found OK</h4>${d.ok.map(t => li(ic('check-circle', 'c-pass'), esc(t))).join('')}</div>
  ${att ? `<div class="ex-blk"><h4>${inv.outcome === 'note' || inv.outcome === 'auto' ? 'Please note' : 'What needs attention'} ${drv}</h4>${att}</div>` : ''}
  <div class="ex-blk"><h4>Suggested action</h4><div class="next"><b>${esc(d.next)}</b>${inv.key === 'si03' ? `<div class="small sec" style="margin-top:8px">The part that fits: 2,500 cartons ₹1,00,000 + GST ₹18,000 = <b>₹1,18,000</b>. The part that does not: 500 cartons ₹20,000 + GST ₹3,600 = <b>₹23,600</b>.</div>` : ''}</div></div>
  <div class="small muted row gap-s">${ic('info', 'sm')}${esc(d.confNote)}<span class="right tiny">Text is written from rule results only. Every amount comes from the checks below.</span></div>`;
}

function panelFields(inv, d) {
  const rows = d.fields.map(f => `<tr class="${f.amber ? '' : ''}" style="${f.amber ? 'background:color-mix(in srgb,var(--review-bg) 55%,transparent)' : ''}" data-act="hlField" data-f="${f.k}"><td class="sec">${f.label}</td><td><b>${esc(f.val)}</b>${f.raw && f.raw !== f.val ? `<div class="tiny muted">Read as: ${esc(f.raw)}</div>` : ''}</td><td>${confChip(f.conf)}${f.boost ? ' <span class="boost">raised</span>' : ''}</td><td class="small sec">${f.src}${f.why ? ` <span data-tip="${esc(f.why)}" style="cursor:help">${ic('info', 'sm')}</span>` : ''}</td><td class="r"><button class="icon-btn" style="width:26px;height:26px" data-act="editField" aria-label="Edit ${f.label}">${ic('edit', 'sm')}</button></td></tr>`).join('');
  const low = d.fields.filter(f => f.conf != null && f.conf < 0.9);
  return `<div class="card panel"><h3>${ic('list', 'sm')}Extracted data ${low.length ? `<span class="pill" style="background:var(--review-bg);color:var(--review-fg)">${low.length} below 0.90</span>` : ''}<span class="right muted small" style="font-weight:500">Click a row to highlight it on the document</span></h3>
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Field</th><th>Value</th><th>Confidence</th><th>Source</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
  <h3 style="margin:18px 0 8px;font-size:13.5px">Line items</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Amount</th><th class="r">GST</th></tr></thead><tbody>${d.lines.map(l => `<tr><td>${esc(l.desc)}</td><td class="r num">${l.qty} ${l.uom}</td><td class="r num">${inr2(l.price)}</td><td class="r num">${inr2(l.amt)}</td><td class="r num">${l.rate}%</td></tr>`).join('')}</tbody></table></div></div>`;
}

function panelVendor(inv, d) {
  const v = V(inv.vendor), vp = d.vendorP, dup = d.dup, bad = !vp.match;
  const bankBox = (t, b, cls) => b ? `<div class="b ${cls || ''}"><div class="upper" style="margin-bottom:4px">${t}</div><b>${esc(b.bank)}</b><div class="mono small">A/c ${bad && t.startsWith('On invoice') ? `<span class="diff">${esc(b.acct)}</span>` : esc(b.acct)}</div><div class="mono small">IFSC ${bad && t.startsWith('On invoice') ? `<span class="diff">${esc(b.ifsc)}</span>` : esc(b.ifsc)}</div></div>` : `<div class="b"><div class="upper" style="margin-bottom:4px">${t}</div><span class="sec">No bank details printed on the invoice. Nothing to compare.</span></div>`;
  const sc = dup.score, mk = clamp(sc * 100, 1, 99);
  const sigs = dup.sigs ? `<div class="sbs" style="margin-top:16px"><div class="doc this"><div class="upper">This invoice</div><b>${esc(inv.invNo)}</b><div class="sec">${inr2(inv.gross)} · ${inv.date}</div><div class="small muted">${inv.doc === 'scanned' ? 'Phone photo, received ' + fmtDS(inv.time) : 'Received ' + fmtDS(inv.time)}</div></div><div class="doc orig"><div class="upper">Matched earlier invoice</div><b>${esc(dup.closest.invNo)}</b> <a href="#s4-${dup.closest.key}" class="small">Open</a><div class="sec">${inr2(dup.closest.gross)} · ${dup.closest.date}</div><div class="small muted">${dup.closest.paid ? 'Approved 21 Oct, paid ' + dup.closest.paid : 'Decision: ' + OUT[dup.closest.outcome].label}</div></div></div>
    <div style="margin-top:12px"><div class="sig h"><span>Signal</span><span>This invoice</span><span>Earlier invoice</span><span></span><span>Score</span></div>${dup.sigs.map(s => `<div class="sig"><span><b>${s[0]}</b><div class="tiny muted">weight ${s[1]}</div></span><span class="mono small">${esc(s[2])}</span><span class="mono small">${esc(s[3])}</span><span>${s[4] ? ic('check-circle', 'c-pass') : ic('x-circle', 'c-review')}</span><span class="num"><b>${s[5]}</b></span></div>${s[6] ? `<div class="tiny sec" style="margin:-4px 0 6px">${s[6]}</div>` : ''}`).join('')}</div>` : dup.exact ? `<div class="banner bad" style="margin-top:12px">${ic('x-circle')}Exact copy: the file fingerprint (SHA-256) matches a file we already processed.</div>` : '';
  return `<div class="card panel"><h3>${ic('shield', 'sm')}Vendor and duplicate check</h3>
    <dl class="kv" style="margin-bottom:14px"><dt>Matched vendor</dt><dd><b>${esc(v.name)}</b> <span class="muted mono small">${v.id}</span></dd><dt>Match method</dt><dd>${vp.method}</dd><dt>Status</dt><dd><span class="chip ${vp.status ? 's-hold' : 's-auto'}">${ic(vp.status ? 'pause-circle' : 'check-circle')}${vp.status || 'Approved'}</span></dd><dt>GSTIN</dt><dd class="mono small">${v.gstin}</dd></dl>
    <div class="upper" style="margin-bottom:6px">Bank details ${bad ? '<span class="chip s-hold" style="margin-left:6px">' + ic('pause-circle') + 'Mismatch</span>' : vp.bankInv ? '<span class="chip s-auto" style="margin-left:6px">' + ic('check-circle') + 'Match</span>' : ''}</div>
    <div class="bank-cmp">${bankBox('On invoice', vp.bankInv, bad ? 'bad' : '')}${bankBox('On file (vendor master)', vp.bankFile)}</div>
    ${bad ? `<div class="banner bad" style="margin-top:12px">${ic('warn', 'lg')}<span>The invoice also says: "Our bank details have changed with effect from 1 Nov 2026." The account changed on invoice only. No change request is on file. Last verified change: ${v.changed}.</span></div>` : ''}
    <hr style="border:0;border-top:1px solid var(--line);margin:18px 0 8px"><div class="upper">How similar this is to an earlier invoice</div>
    <div class="gauge" role="img" aria-label="Similarity ${sc.toFixed(2)}"><span class="th" style="left:60%">0.60 review</span><span class="th" style="left:85%">0.85 reject</span><span class="mk" style="left:${mk}%"><em>${sc.toFixed(2)}</em></span></div>
    <p class="small sec">${dup.sigs || dup.exact ? '' : `Closest earlier invoice is <b>${dup.closest ? esc(dup.closest.invNo) : 'none'}</b> at ${sc.toFixed(2)}. Allowed below 0.60.`}${dup.sigs && inv.key !== 'si04' ? 'Possible duplicate. Compare the two invoices below and decide.' : ''}${inv.key === 'si04' ? 'Same invoice written differently. A string match would miss it; five signals agree.' : ''}</p>${sigs}</div>`;
}

function panelPO(inv, d) {
  const p = d.po, po = p.obj, c = d.cum; const v = V(inv.vendor);
  const scale = Math.max(112, c.after + 4), over = c.after > 100.5;
  const aW = c.before / scale * 100, bW = Math.min(c.after, 100) > c.before ? (Math.min(c.after, 100) - c.before) / scale * 100 : 0, oW = over ? (c.after - 100) / scale * 100 : 0;
  const rows = d.rows.map(r => r.sev === 'none' ? `<tr class="muted-row"><td colspan="2">${r.pl}: not on this invoice</td><td class="r num">${r.ord}</td><td class="r num">${r.bb}</td><td class="r num">0</td><td class="r num">${r.rem}</td><td colspan="3" class="muted small">Already billed before</td></tr>` : `<tr class="sev" style="--sev:${r.sev === 'pass' ? 'transparent' : OUT_COLOR[r.sev === 'note' ? 'note' : r.sev]}"><td>${esc(r.il)}</td><td class="mono small">${esc(r.pl)}</td><td class="r num">${r.ord.toLocaleString('en-IN')}</td><td class="r num">${r.bb.toLocaleString('en-IN')}</td><td class="r num"><b>${r.ti.toLocaleString('en-IN')}</b></td><td class="r num" style="${r.over ? 'color:var(--reject-fg);font-weight:700' : ''}">${r.rem.toLocaleString('en-IN')}${r.over ? `<div class="tiny">${r.over} over</div>` : ''}</td><td class="r num nowrap">${inr2(r.pp)} → ${inr2(r.ip)}<div class="tiny ${Math.abs(r.dp) > 0.005 ? '' : 'muted'}">${r.dp >= 0 ? '+' : ''}${(r.dp * 100).toFixed(1)}%</div></td><td class="r num nowrap">${r.av ? (r.av > 0 ? '+' : '−') + inr(Math.abs(Math.round(r.av))) : '₹0'}</td><td class="c">${sevIcon(r.sev)}</td></tr>${r.note ? `<tr><td colspan="9" class="small sec" style="background:var(--surface-2)">${ic('link', 'sm')} ${esc(r.note)}</td></tr>` : ''}`).join('');
  const cands = p.cands ? `<div class="stack-s" style="margin-bottom:14px"><div class="upper">Match candidates (inferred, no PO on the invoice)</div>${p.cands.map((cd, i) => `<div class="cand ${i === 0 ? 'win' : ''}"><div class="row"><b class="mono">${cd.id}</b>${i === 0 ? '<span class="chip s-auto">' + ic('check-circle') + 'Selected</span>' : '<span class="pill">Runner-up</span>'}<span class="right" style="font-family:var(--f-head);font-weight:800;font-size:18px">${Math.round(cd.score * 100)}%</span></div><div class="small sec">${cd.note}</div>${cd.parts.map(pt => `<div class="mini-b"><span>${pt[0]} <span class="tiny muted">(${Math.round(pt[2] * 100)}%)</span></span><div class="bar"><i style="width:${pt[1] * 100}%;background:${i === 0 ? 'var(--ok)' : 'var(--ink-3)'}"></i></div><span class="num">${Math.round(pt[1] * 100)}%</span></div>`).join('')}</div>`).join('')}
    <div class="small sec" style="background:var(--surface-2);border-radius:8px;padding:8px 12px">Rule: accept an implied PO only when the best score is 90% or more, the runner-up is at least 20 points lower and the invoice is up to ₹1,00,000. Here: <b>96%</b>, a gap of <b>82 points</b>, and a total of <b>${inr(inv.gross)}</b>. All three conditions hold.</div></div>` : '';
  const tl = po && po.hist.length ? `<div class="upper" style="margin:18px 0 10px">All invoices against this PO</div><div class="tl">${po.hist.map(h => `<div class="ev ${h[4] === inv.key ? 'now' : ''}" style="--evc:${OUT_COLOR[h[3]]}"><div class="row wrap gap-s"><a href="#s4-${h[4]}" class="mono"><b>${h[0]}</b></a><span class="muted small">${h[1]}</span><span class="num">${inr(h[2])}</span>${chip(h[3])}${h[4] === inv.key ? '<span class="pill accent">This invoice</span>' : ''}</div><div class="small sec">${h[5]}</div></div>`).join('')}</div>` : '';
  return `<div class="card panel"><h3>${ic('link', 'sm')}Purchase order match</h3>
  <div class="row wrap" style="margin-bottom:14px"><a class="mono" href="#s6" data-act="openPo" data-id="${p.id}" style="font-size:15px;font-weight:700">${p.id}</a><span class="chip ${p.method === 'Explicit' ? 's-auto' : 's-note'}">${ic(p.method === 'Explicit' ? 'check-circle' : 'note-circle')}${p.method}${p.method === 'Implied' ? ' · ' + Math.round(p.score * 100) + '% vs ' + Math.round(p.runner * 100) + '%' : ''}</span>${po ? `<span class="small sec">${esc(v.short)} · issued ${po.issued} · valid to ${po.valid} · ${po.status}</span>` : ''}</div>
  ${cands}
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Invoice line</th><th>PO line</th><th class="r">Ordered</th><th class="r">Billed before</th><th class="r">This invoice</th><th class="r">Remaining</th><th class="r">Unit price, PO → invoice</th><th class="r">Variance</th><th class="c">Status</th></tr></thead><tbody>${rows}</tbody></table></div>
  <div class="cum" style="margin-top:16px"><div class="upper" style="margin-bottom:6px">Cumulative billed against this PO (before tax)</div><div class="track" role="img" aria-label="${c.before.toFixed(0)} percent billed before, ${c.after.toFixed(0)} percent after"><div class="a" style="width:${aW}%"></div><div class="b" style="width:${bW}%"></div><div class="b over" style="width:${oW}%"></div><span class="line" style="left:${100 / scale * 100}%"></span></div>
  <div class="cum-lab"><span><b>${c.before.toFixed(0)}%</b> billed before (${inr(c.beforeVal)})</span><span>PO value ${inr(c.totalVal)} = 100%</span><span style="${over ? 'color:var(--reject-fg);font-weight:700' : ''}"><b>${c.after.toFixed(0)}%</b> after this invoice (${inr(c.beforeVal + c.thisVal)})</span></div></div>${tl}</div>`;
}

function panelRules(inv, d) {
  const sorted = d.rules.slice().sort((a, b) => SEVRANK[b.sev] - SEVRANK[a.sev] || a.stage - b.stage);
  const vis = sorted.filter(r => STATE4.showPassed || r.sev !== 'pass');
  const flagged = sorted.filter(r => r.sev !== 'pass').length;
  const rowsH = vis.map(r => `<div class="rule"><span>${sevIcon(r.sev)}</span><div><div class="rt">${esc(r.name)} <span class="rid">${r.id}</span>${r.hard ? ' <span class="pill" style="font-size:10.5px">Hard stop</span>' : ''}<span class="tiny muted"> · ${STAGES[r.stage - 1].name}</span></div><div class="rs">${esc(r.msg)}</div>${r.allowed ? `<div class="tiny muted" style="margin-top:2px">${r.allowed}. <a href="#s7">Why this rule?</a></div>` : `<div class="tiny" style="margin-top:2px"><a href="#s7">Why this rule?</a></div>`}</div>${sevChip(r.sev)}</div>`).join('');
  return `<div class="card panel"><h3>${ic('check-circle', 'sm')}Rule checklist<span class="muted small" style="font-weight:500">${flagged} flagged · ${16 - flagged} passed</span><label class="right row gap-s small sec" style="font-weight:500;cursor:pointer"><button class="toggle" role="switch" aria-checked="${STATE4.showPassed}" data-act="togglePassed" aria-label="Show passed checks"></button>Show passed checks</label></h3>${rowsH || '<div class="empty small">All 16 checks passed.</div>'}</div>`;
}

function panelDrafts(inv, d) {
  const dr = d.draft; if (!dr) return '';
  const chk = inv.key === 'si06' ? `<div class="upper" style="margin:18px 0 6px">Verification checklist (manager releases the hold when all three are ticked)</div><div class="checklist">${['Called Corevolt on the number in our vendor file (' + V('V-102').phone + '), not the number on the invoice', 'Received a written change request on company letterhead', 'A second person confirmed the new account'].map((t, i) => `<label><input type="checkbox" class="check" id="vc${i}"><span>${t}</span></label>`).join('')}</div><p class="small sec" style="margin-top:8px">After the checklist, a manager updates the vendor record in <a href="#s6">master data</a> and releases the hold. Ledgerlight then re-checks the bank details.</p>` : '';
  return `<div class="card panel"><h3>${ic('mail', 'sm')}${dr.title}<span class="pill right">Draft. Nothing is sent automatically</span></h3><div class="small muted" style="margin-bottom:8px">To: ${esc(dr.to)} · Subject: <b>${esc(dr.subject)}</b></div><div class="draft" id="draft-text">${esc(dr.body)}</div><div class="row" style="margin-top:12px"><button class="btn" data-act="copyDraft">${ic('copy', 'sm')}Copy email draft</button>${inv.key === 'si06' ? `<span class="small muted">Call script: "Hello, this is Accounts Payable at Aster Industries. We received invoice CV-8902 with a new bank account. Can you confirm the change?"</span>` : ''}</div>${chk}</div>`;
}

function activityFor(inv) {
  const ev = AUDIT.filter(a => a.obj.id === inv.invNo).sort((a, b) => a.ts - b.ts);
  return ev.length ? ev : [{ ts: inv.time, actor: { t: 'System', n: 'Ledgerlight rules' }, type: 'Decision made', summary: `${OUT[inv.outcome].long}: ${inv.reason}`, outcome: inv.outcome }];
}
function panelActivity(inv, d) {
  const ev = activityFor(inv);
  return `<div class="card panel"><h3>${ic('clock', 'sm')}Activity<a class="right small" href="#s8" data-act="auditFor" data-inv="${esc(inv.invNo)}">Open this invoice in the audit log</a></h3><div class="tl">${ev.map((e, i) => `<div class="ev ${i === ev.length - 1 ? 'now' : ''}" style="--evc:${e.outcome ? OUT_COLOR[e.outcome] : 'var(--line-2)'}"><div class="small muted">${fmtDS(e.ts)}, ${fmtT(e.ts)} · ${esc(e.actor.n)}</div><div>${esc(e.summary)}</div></div>`).join('')}</div></div>`;
}

/* ---- S4 actions ---- */
ACT.s4tab = t => { STATE4.tab = t.dataset.t; route(true); };
ACT.zoom = t => { STATE4.zoom = clamp(STATE4.zoom + +t.dataset.d, 0.6, 1.4); route(true); };
ACT.togglePassed = () => { STATE4.showPassed = !STATE4.showPassed; route(true); };
ACT.hlField = t => { const k = t.dataset.f; const on = STATE4.hl === k; STATE4.hl = on ? null : k; $$('.paper [data-f]').forEach(e => e.classList.toggle('hl', !on && e.dataset.f === k)); if (!on && STATE4.tab === 'doc' || innerWidth > 900) { const el = $(`.paper [data-f="${k}"]`); if (el && !on) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } };
ACT.editField = () => toast('To correct a field, edit the value and Ledgerlight re-checks stages 3 to 9. Editing is switched off in this mock.');
ACT.copyJson = () => { const inv = INV[S4KEY]; copyText(decisionJSON(inv, buildDetail(inv)), 'Decision JSON'); };
ACT.copyDraft = () => { const dr = buildDetail(INV[S4KEY]).draft; copyText(`To: ${dr.to}\nSubject: ${dr.subject}\n\n${dr.body}`, 'Email draft'); };
ACT.openPo = () => { };
ACT.navExc = t => { const l = QUEUE_ORDER(); const i = l.findIndex(r => r.key === S4KEY) + +t.dataset.d; if (l[i]) location.hash = '#s4-' + l[i].key; };
ACT.acceptDecision = () => { const inv = INV[S4KEY]; inv.confirmedBy = ROLES[S.role].name; addAudit('Decision made', `${ROLES[S.role].name} accepted the decision on ${inv.invNo}: ${OUT[inv.outcome].long}`, inv, inv.outcome, { confirmed_by: ROLES[S.role].name }); toast('Decision confirmed. Recorded in the audit log.'); route(true); };
function addAudit(type, summary, inv, outcome, payload) { AUDIT.unshift({ ts: new Date(TODAY.getTime() + (AUDIT.length % 50) * 60000 + 900000), actor: { t: 'Human', n: ROLES[S.role].name }, type, summary, obj: { k: 'Invoice', id: inv.invNo, href: '#s4-' + inv.key }, outcome, payload }); }

ACT.openOverride = () => {
  const inv = INV[S4KEY], d = buildDetail(inv); const bank = d.rules.some(r => r.id === 'R05' && r.sev === 'hold');
  const perm = canOverride(inv, 'approve');
  openSheet(`<div class="sheet-h"><div><div class="upper">Override decision</div><h3>${esc(inv.invNo)} · ${esc(inv.vname)}</h3></div><button class="icon-btn right" data-act="closeSheet" aria-label="Close">${ic('x')}</button></div>
  <div class="sheet-b"><div class="row gap-s">Current decision ${chip(inv.outcome)}<span class="small muted">${inr2(inv.gross)}${inv.exposure ? ' · exposure ' + inr(inv.exposure) : ''}</span></div>
  ${!perm.ok && inv.outcome !== 'auto' ? `<div class="banner bad" id="perm-banner">${ic('lock', 'lg')}<span>${perm.why}</span></div>` : ''}
  <div class="field-l">Action<div class="seg" id="ov-action" style="align-self:flex-start"><button class="on" data-act="ovAction" data-a="approve">Approve</button><button data-act="ovAction" data-a="reject">Reject</button><button data-act="ovAction" data-a="info">Send back for info</button></div></div>
  ${bank ? `<div class="stack-s"><div class="upper">Bank change verification (manager only)</div><div class="checklist">${['Called the vendor on the number in the master', 'Received a written change request', 'A second person confirmed the new account'].map((t, i) => `<label><input type="checkbox" class="check ov-chk" id="ovc${i}"><span>${t}</span></label>`).join('')}</div></div>` : ''}
  <label class="field-l">Reason code<select id="ov-code">${REASON_CODES.map(c => `<option>${c}</option>`).join('')}</select></label>
  <label class="field-l">Reason (at least 10 characters)<textarea id="ov-text" placeholder="Say why you are changing this decision"></textarea><span class="tiny muted" id="ov-count">0 of 10 characters</span></label>
  <div class="small sec" id="ov-effect" style="background:var(--surface-2);border-radius:8px;padding:10px 12px">This will move the invoice to the payment queue and be recorded in the audit log. The original decision stays on record.</div></div>
  <div class="sheet-f"><button class="btn" data-act="closeSheet">Cancel</button><button class="btn primary" id="ov-submit" data-act="submitOverride" disabled>Confirm override</button></div>`);
  const upd = () => { const t = $('#ov-text').value.trim().length, a = $('#ov-action .on').dataset.a; $('#ov-count').textContent = t + ' of 10 characters'; const p = canOverride(inv, a); const chk = bank ? $$('.ov-chk').every(c => c.checked) : true; const ok = t >= 10 && p.ok && chk && !(inv.outcome === 'auto' && a === 'approve'); $('#ov-submit').disabled = !ok; };
  $('#ov-text').oninput = upd; $$('.ov-chk').forEach(c => c.onchange = upd); window.__ovUpd = upd; upd();
};
ACT.closeSheet = () => closeSheet();
ACT.ovAction = t => { $$('#ov-action button').forEach(b => b.classList.toggle('on', b === t)); const inv = INV[S4KEY]; const a = t.dataset.a; $('#ov-effect').textContent = { approve: 'This will move the invoice to the payment queue and be recorded in the audit log. The original decision stays on record.', reject: 'This will reject the invoice and queue a return notice for the vendor. It is recorded in the audit log.', info: 'This will put the invoice on hold, start the 3 business day wait and keep the drafted message ready.' }[a]; const p = canOverride(inv, a); let b = $('#perm-banner'); if (!p.ok) { if (!b) $('.sheet-b').insertAdjacentHTML('afterbegin', `<div class="banner bad" id="perm-banner">${ic('lock', 'lg')}<span>${p.why}</span></div>`); else b.lastChild.textContent = p.why; } else if (b) b.remove(); window.__ovUpd(); };
ACT.submitOverride = () => {
  const inv = INV[S4KEY], a = $('#ov-action .on').dataset.a, code = $('#ov-code').value, text = $('#ov-text').value.trim(); const to = { approve: 'auto', reject: 'reject', info: 'hold' }[a]; const from = inv.outcome;
  inv.overridden = { from, by: ROLES[S.role].name, code, text, when: fmtDS(TODAY) + ', ' + fmtT(new Date(TODAY.getTime() + 420000)) }; inv.outcome = to; inv.exposure = to === 'auto' ? 0 : inv.exposure; delete inv._d;
  addAudit('Override', `${ROLES[S.role].name} changed ${inv.invNo} from ${OUT[from].label} to ${OUT[to].label}: ${code}`, inv, to, { before: OUT[from].label, after: OUT[to].label, reason_code: code, reason_text: text });
  closeSheet(); toast(`Decision changed to ${OUT[to].label}. Recorded in the audit log.`); updateNavBadge(); route(true);
};
