'use client';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { API, url, api } from '@/lib/api';
import { clamp, fmtD, fmtDT, fmtDay, fmtT, inr, inrP, inrP2, num, secs } from '@/lib/format';
import { Chip, ConfChip, Empty, ErrorBanner, Ic, Modal, OUT, OUT_COLOR, SEVRANK, SevChip, SevIcon, Shimmer, Sheet, copyText, outKey, useApi, useApp } from '@/lib/ui';

const STAGE_NAMES = ['Ingest', 'Extract', 'Normalise and field checks', 'Vendor check', 'Duplicate check', 'PO match', 'Validation rules', 'Decision', 'Explain and output'];
const CLERK_LIMIT_PAISE = 1000000;

function Gauge({ score, th }) {
  const mk = clamp(score * 100, 1, 99);
  return (
    <div className="gauge" role="img" aria-label={`Similarity ${score.toFixed(2)}`} style={{ background: `linear-gradient(90deg, var(--ok) 0 ${th.review * 100}%, var(--review) ${th.review * 100}% ${th.reject * 100}%, var(--reject) ${th.reject * 100}% 100%)` }}>
      <span className="th" style={{ left: `${th.review * 100}%` }}>{th.review.toFixed(2)} review</span>
      <span className="th" style={{ left: `${th.reject * 100}%` }}>{th.reject.toFixed(2)} reject</span>
      <span className="mk" style={{ left: `${mk}%` }}><em>{score.toFixed(2)}</em></span>
    </div>
  );
}
const fmtSig = (sig, v) => {
  if (v == null) return '—';
  if (sig === 'amount') return inrP2(v);
  if (sig === 'date') return fmtDay(v);
  if (Array.isArray(v)) return `${v.length} line${v.length === 1 ? '' : 's'}: ${v.map((l) => `${l.qty} × ${inrP(l.unit_price_paise, 2)}`).join(', ')}`;
  return String(v);
};

/* ---------- override sheet ---------- */
function OverrideSheet({ open, onClose, d, onDone }) {
  const { role, toast } = useApp();
  const worstRules = d.rules.filter((r) => r.hard_stop && r.severity === worstSev(d.rules) && ['reject', 'hold'].includes(r.severity));
  const bank = d.rules.some((r) => r.rule_id === 'R05' && r.severity === 'hold');
  const [action, setAction] = useState('approve');
  const [code, setCode] = useState('Other');
  const [text, setText] = useState('');
  const [chk, setChk] = useState([false, false, false]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const codes = useApi('/api/meta');
  useEffect(() => { if (open) { setAction('approve'); setText(''); setErr(null); setChk([false, false, false]); } }, [open]);
  const cur = outKey(d.decision.outcome);
  const exposure = d.decision.exposure_paise || 0;
  let perm = { ok: true };
  if (cur === 'auto' && action === 'approve') perm = { ok: false, why: 'This invoice is already approved.' };
  else if (action === 'approve' && role === 'clerk') {
    if (worstRules.length) perm = { ok: false, why: `This is a hard stop (${worstRules.map((r) => r.rule_id).join(', ')}). Only an AP manager can override it. Switch role in the top bar.` };
    else if (!(cur === 'review' && exposure <= CLERK_LIMIT_PAISE)) perm = { ok: false, why: `A clerk can approve a review item only when the exposure is ₹10,000 or less. This one is ${inrP(exposure)}. Switch role in the top bar.` };
  }
  const needChk = bank && action === 'approve';
  const valid = text.trim().length >= 10 && perm.ok && (!needChk || chk.every(Boolean));
  const effect = { approve: 'This will move the invoice to the payment queue and be recorded in the audit log. The original decision stays on record.', reject: 'This will reject the invoice and queue a return notice for the vendor. It is recorded in the audit log.', hold: 'This will put the invoice on hold, start the wait for the vendor and keep the drafted message ready. It is recorded in the audit log.' }[action];

  async function submit() {
    setBusy(true); setErr(null);
    try {
      const body = { action, reason_code: code, reason_text: text.trim() };
      if (needChk) body.checklist = { called_vendor_on_master_number: chk[0], written_request_received: chk[1], second_person_confirmed: chk[2] };
      const r = await api(`/api/invoices/${d.invoice.id}/override`, { method: 'POST', body });
      onClose(); toast(`Decision changed to ${(OUT[outKey(r.outcome)] || {}).label}. Recorded in the audit log.`); onDone();
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <Sheet open={open} onClose={onClose} label="Override decision">
      <div className="sheet-h"><div><div className="upper">Override decision</div><h3>{d.invoice.invoice_no_raw} · {d.vendor_panel && d.vendor_panel.vendor ? d.vendor_panel.vendor.short : d.invoice.vendor_name_raw || 'Unknown vendor'}</h3></div><button className="icon-btn right" onClick={onClose} aria-label="Close"><Ic n="x" /></button></div>
      <div className="sheet-b" data-testid="override-sheet">
        <div className="row gap-s wrap">Current decision <Chip k={cur} /><span className="small muted">{d.invoice.total_paise ? inrP2(d.invoice.total_paise) : ''}{exposure ? ` · exposure ${inrP(exposure)}` : ''}</span></div>
        {!perm.ok ? <div className="banner bad" data-testid="perm-banner"><Ic n="lock" c="lg" /><span>{perm.why}</span></div> : null}
        {err ? <div className="banner bad" role="alert" data-testid="override-error"><Ic n="warn" c="lg" /><span>{err.message}</span></div> : null}
        <div className="field-l">Action
          <div className="seg" style={{ alignSelf: 'flex-start' }}>{[['approve', 'Approve'], ['reject', 'Reject'], ['hold', 'Send back for info']].map(([k, l]) => <button key={k} className={action === k ? 'on' : ''} onClick={() => setAction(k)} data-testid={`ov-${k}`}>{l}</button>)}</div></div>
        {bank ? <div className="stack-s"><div className="upper">Bank change verification (manager only)</div><div className="checklist">{['Called the vendor on the number in the master', 'Received a written change request', 'A second person confirmed the new account'].map((t, i) => <label key={i}><input type="checkbox" className="check" checked={chk[i]} onChange={(e) => setChk((c) => c.map((x, j) => (j === i ? e.target.checked : x)))} /><span>{t}</span></label>)}</div></div> : null}
        <label className="field-l">Reason code<select id="ov-code" value={code} onChange={(e) => setCode(e.target.value)} data-testid="ov-code">{(codes.data ? codes.data.reason_codes : ['Other']).map((c) => <option key={c}>{c}</option>)}</select></label>
        <label className="field-l">Reason (at least 10 characters)<textarea id="ov-text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Say why you are changing this decision" data-testid="ov-text" /><span className="tiny muted">{text.trim().length} of 10 characters</span></label>
        <div className="small sec" style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>{effect}</div>
      </div>
      <div className="sheet-f"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!valid || busy} onClick={submit} data-testid="ov-submit">{busy ? 'Saving…' : 'Confirm override'}</button></div>
    </Sheet>
  );
}
const worstSev = (rules) => rules.reduce((m, r) => (!r.skipped && SEVRANK[r.severity] > SEVRANK[m] ? r.severity : m), 'pass');

/* ---------- field correction ---------- */
function EditField({ f, d, onClose }) {
  const router = useRouter(); const { toast } = useApp();
  const [val, setVal] = useState(''); const [why, setWhy] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState(null);
  useEffect(() => { if (f) { setVal(f.value ?? ''); setWhy(''); setErr(null); } }, [f]);
  async function save() {
    setBusy(true); setErr(null);
    try { const r = await api(`/api/invoices/${d.invoice.id}/fields/${f.name}`, { method: 'PATCH', body: { value: val, reason: why.trim() } }); onClose(); toast('Field corrected. Ledgerlight is re-checking stages 3 to 9.'); router.push(`/runs/${r.run_id}`); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <Modal open={!!f} onClose={onClose} label="Correct a field">
      <div className="sheet-h"><h3>Correct {f ? f.label : ''}</h3><button className="icon-btn right" onClick={onClose} aria-label="Close"><Ic n="x" /></button></div>
      <div className="sheet-b">
        {err ? <div className="banner bad"><Ic n="warn" /><span>{err.message}</span></div> : null}
        <p className="small sec">Read as <b>{f ? f.raw_text || f.value : ''}</b>. Both values are kept in the audit log, and stages 3 to 9 run again with your correction.</p>
        <label className="field-l">New value<input type="text" value={val} onChange={(e) => setVal(e.target.value)} /></label>
        <label className="field-l">Reason (at least 10 characters)<textarea value={why} onChange={(e) => setWhy(e.target.value)} placeholder="For example: read from the paper copy" /></label>
      </div>
      <div className="sheet-f"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy || why.trim().length < 10 || !String(val).trim()} onClick={save}>{busy ? 'Saving…' : 'Save and re-run'}</button></div>
    </Modal>
  );
}

/* ---------- panels ---------- */
function Explain({ d }) {
  const ex = d.decision.explanation || {}; const k = outKey(d.decision.outcome);
  const drv = d.decision.driving_rule_ids || [];
  const nm = Object.fromEntries(d.rules.map((r) => [r.rule_id, r.name]));
  const li = (ico, t, i) => <div className="ex-li" key={i}>{ico}<span>{t}</span></div>;
  const attIcon = <Ic n={k === 'reject' ? 'x-circle' : k === 'hold' ? 'pause-circle' : k === 'review' ? 'eye' : 'note-circle'} c={`c-${k === 'auto' ? 'note' : k}`} />;
  return (
    <div className="card explain" style={{ marginTop: 14 }} data-testid="explanation">
      {(ex.ok || []).length ? <div className="ex-blk"><h4>What we checked and found OK</h4>{ex.ok.map((t, i) => li(<Ic n="check-circle" c="c-pass" />, t, i))}</div> : null}
      {(ex.attention || []).length ? <div className="ex-blk"><h4>{k === 'note' || k === 'auto' ? 'Please note' : 'What needs attention'} {drv.map((r) => <span key={r} className="rid" data-tip={nm[r]}>{r}</span>)}</h4>{ex.attention.map((t, i) => li(attIcon, t, i))}</div> : null}
      {ex.next_step ? <div className="ex-blk"><h4>Suggested action</h4><div className="next"><b>{ex.next_step}</b>{ex.alternative_step ? <div className="small sec" style={{ marginTop: 8 }}>{ex.alternative_step}</div> : null}</div></div> : null}
      <div className="small muted row gap-s"><Ic n="info" c="sm" />{ex.confidence_note}<span className="right tiny">Text is written from rule results only. Every amount comes from the checks below.</span></div>
    </div>
  );
}

function FieldsPanel({ d, onEdit }) {
  const fields = Object.entries(d.fields || {}).map(([name, f]) => ({ name, ...f }));
  const low = fields.filter((f) => f.effective_confidence != null && f.effective_confidence < 0.9);
  const r01 = d.rules.find((r) => r.rule_id === 'R01');
  const docType = r01 && r01.facts && r01.facts.reason === 'wrong_doc_type' ? r01.facts : null;
  if (!fields.length && docType) {
    return (
      <div className="card panel" data-testid="fields-panel"><h3><Ic n="list" c="sm" />Extracted data</h3>
        <div className="notice-scan" data-testid="doc-type-notice"><Ic n="pause-circle" c="lg" /><div><b>{`This is a ${docType.doc_label}, not a tax invoice`}</b><p>{r01.message_plain || r01.message}</p></div></div>
      </div>
    );
  }
  if (!fields.length) {
    return (
      <div className="card panel" data-testid="fields-panel"><h3><Ic n="list" c="sm" />Extracted data</h3>
        <div className="notice-scan"><Ic n="pause-circle" c="lg" /><div><b>Nothing could be read from this document</b><p>{d.invoice.doc_type === 'scanned' ? 'It is an image-only scan and no AI key is set on this server, so the invoice was held rather than guessed at. Set GROQ_API_KEY or ANTHROPIC_API_KEY in backend/.env, restart and re-run, or ask the vendor for a text PDF.' : 'No fields were found in the file.'}</p></div></div>
      </div>
    );
  }
  return (
    <div className="card panel" data-testid="fields-panel">
      <h3><Ic n="list" c="sm" />Extracted data {low.length ? <span className="pill" style={{ background: 'var(--review-bg)', color: 'var(--review-fg)' }}>{low.length} below 0.90</span> : null}<span className="right muted small" style={{ fontWeight: 500 }}>Pencil to correct a value</span></h3>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Field</th><th>Value</th><th>Confidence</th><th>Source</th><th /></tr></thead><tbody>
        {fields.map((f) => {
          const amber = f.effective_confidence != null && f.effective_confidence < 0.9;
          const shown = f.parsed != null && /subtotal|tax|total/.test(f.name) && typeof f.parsed === 'number' ? inrP2(f.parsed) : f.value;
          return (
            <tr key={f.name} style={amber ? { background: 'color-mix(in srgb,var(--review-bg) 55%,transparent)' } : undefined} data-testid={`fld-${f.name}`}>
              <td className="sec">{f.label}</td>
              <td><b>{shown || <span className="muted">Not found</span>}</b>{f.raw_text && f.raw_text !== f.value ? <div className="tiny muted">Read as: {f.raw_text}</div> : null}</td>
              <td><ConfChip c={f.effective_confidence} />{f.boosted ? <> <span className="boost">raised</span></> : null}</td>
              <td className="small sec">{f.source}{f.why ? <> <span data-tip={f.why} style={{ cursor: 'help' }}><Ic n="info" c="sm" /></span></> : null}</td>
              <td className="r"><button className="icon-btn" style={{ width: 26, height: 26 }} aria-label={`Edit ${f.label}`} onClick={() => onEdit(f)}><Ic n="edit" c="sm" /></button></td>
            </tr>
          );
        })}
      </tbody></table></div>
      <h3 style={{ margin: '18px 0 8px', fontSize: 13.5 }}>Line items</h3>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Description</th><th className="r">Qty</th><th className="r">Unit price</th><th className="r">Amount</th><th className="r">GST</th></tr></thead><tbody>
        {(d.lines || []).map((l) => <tr key={l.line_no}><td>{l.description_raw}</td><td className="r num">{num(l.qty, 2)} {l.uom}</td><td className="r num">{inrP2(l.unit_price_paise)}</td><td className="r num">{inrP2(l.amount_paise)}</td><td className="r num">{l.tax_rate_pct}%</td></tr>)}
      </tbody></table></div>
    </div>
  );
}

function VendorPanel({ d }) {
  const vp = d.vendor_panel || {}; const v = vp.vendor; const dup = d.duplicate_panel && d.duplicate_panel.score != null ? d.duplicate_panel : null;
  const bad = vp.bank_match === false;
  const bankBox = (t, b, cls, isInv) => b ? (
    <div className={`b ${cls || ''}`}><div className="upper" style={{ marginBottom: 4 }}>{t}</div><b>{b.bank_name}</b>
      <div className="mono small">A/c {bad && isInv ? <span className="diff">{b.account}</span> : b.account}</div><div className="mono small">IFSC {bad && isInv ? <span className="diff">{b.ifsc}</span> : b.ifsc}</div></div>
  ) : <div className="b"><div className="upper" style={{ marginBottom: 4 }}>{t}</div><span className="sec">{isInv ? 'No bank details printed on the invoice. Nothing to compare.' : 'No bank details on file.'}</span></div>;
  const method = { gstin: 'GSTIN match (decisive)', name: 'Exact name match', fuzzy: 'Similar name only', none: 'No match' }[vp.match && vp.match.method] || (vp.match && vp.match.method) || '—';
  const showCompare = dup && dup.compare && dup.compare.length && (dup.score >= dup.thresholds.review);
  const sc = dup ? dup.score : 0;
  return (
    <div className="card panel" data-testid="vendor-panel"><h3><Ic n="shield" c="sm" />Vendor and duplicate check</h3>
      {v ? (
        <>
          <dl className="kv" style={{ marginBottom: 14 }}>
            <dt>Matched vendor</dt><dd><b>{v.name}</b> <span className="muted mono small">{v.id}</span></dd>
            <dt>Match method</dt><dd>{method}</dd>
            <dt>Status</dt><dd><span className={`chip ${v.status === 'approved' ? 's-auto' : 's-hold'}`}><Ic n={v.status === 'approved' ? 'check-circle' : 'pause-circle'} />{{ approved: 'Approved', pending: 'Pending onboarding', blocked: 'Blocked' }[v.status] || v.status}</span></dd>
            <dt>GSTIN</dt><dd className="mono small">{v.gstin}</dd>
          </dl>
          <div className="upper" style={{ marginBottom: 6 }}>Bank details {vp.bank_match === false ? <span className="chip s-hold" style={{ marginLeft: 6 }}><Ic n="pause-circle" />Mismatch</span> : vp.bank_match ? <span className="chip s-auto" style={{ marginLeft: 6 }}><Ic n="check-circle" />Match</span> : null}</div>
          <div className="bank-cmp">{bankBox('On invoice', vp.bank_on_invoice, bad ? 'bad' : '', true)}{bankBox('On file (vendor master)', vp.bank_on_file, '', false)}</div>
          {bad && vp.bank_on_invoice && vp.bank_on_invoice.change_notice ? <div className="banner bad" style={{ marginTop: 12 }}><Ic n="warn" c="lg" /><span>The invoice also says: &ldquo;{vp.bank_on_invoice.change_text}&rdquo; No change request is on file. Last verified change: {fmtDay(v.bank_changed_at)}.</span></div> : null}
        </>
      ) : <div className="small sec" style={{ marginBottom: 8 }}>No vendor could be matched yet, because nothing was read from the document.</div>}
      {dup ? (
        <>
          <hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: '18px 0 8px' }} />
          <div className="upper">How similar this is to an earlier invoice</div>
          <Gauge score={sc} th={dup.thresholds} />
          {dup.exact ? <div className="banner bad" style={{ marginTop: 12 }}><Ic n="x-circle" />Exact copy: the file fingerprint (SHA-256) matches a file we already processed.</div> : null}
          {!showCompare && !dup.exact ? <p className="small sec">Closest earlier invoice is <b>{dup.closest ? dup.closest.invoice_no : 'none'}</b> at {sc.toFixed(2)}. Allowed below {dup.thresholds.review.toFixed(2)}.</p> : null}
          {showCompare ? (
            <>
              <p className="small sec">{sc >= dup.thresholds.reject ? 'Same invoice written differently. A string match would miss it; the signals below agree.' : 'Possible duplicate. Compare the two invoices below and decide.'}</p>
              <div className="sbs" style={{ marginTop: 16 }}>
                <div className="doc this"><div className="upper">This invoice</div><b>{d.invoice.invoice_no_raw}</b><div className="sec">{inrP2(d.invoice.total_paise)} · {fmtDay(d.invoice.invoice_date)}</div></div>
                <div className="doc orig"><div className="upper">Matched earlier invoice</div><b>{dup.closest.invoice_no}</b> {dup.closest.id ? <Link href={`/audit?invoice=${dup.closest.id}`} className="small">Trace</Link> : null}<div className="sec">{inrP2(dup.closest.total_paise)} · {fmtDay(dup.closest.invoice_date)}</div><div className="small muted">{dup.closest.paid_at ? `Paid ${fmtDay(dup.closest.paid_at)}` : `Decision: ${(OUT[outKey(dup.closest.outcome)] || {}).label || ''}`}</div></div>
              </div>
              <div style={{ marginTop: 12 }}>
                <div className="sig h"><span>Signal</span><span>This invoice</span><span>Earlier invoice</span><span /><span>Score</span></div>
                {dup.compare.map((s) => (
                  <div className="sig" key={s.signal}><span><b>{s.label}</b><div className="tiny muted">weight {s.weight}</div></span><span className="mono small">{fmtSig(s.signal, s.this)}</span><span className="mono small">{fmtSig(s.signal, s.other)}</span><span><Ic n={s.score >= 0.9 ? 'check-circle' : 'x-circle'} c={s.score >= 0.9 ? 'c-pass' : 'c-review'} /></span><span className="num"><b>{(s.score ?? 0).toFixed(2)}</b></span></div>
                ))}
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function POPanel({ d }) {
  const p = d.po_panel;
  if (!p) return (
    <div className="card panel" data-testid="po-panel"><h3><Ic n="link" c="sm" />Purchase order match</h3><div className="small sec">No purchase order could be matched yet{d.invoice.doc_type === 'scanned' && !Object.keys(d.fields || {}).length ? ', because nothing was read from the document' : ''}.</div></div>
  );
  const po = p.po, c = p.cumulative || {}; const before = c.before_pct || 0, after = c.after_pct || 0;
  const scale = Math.max(112, after + 4), over = after > 100.5;
  const aW = (before / scale) * 100, bW = Math.min(after, 100) > before ? ((Math.min(after, 100) - before) / scale) * 100 : 0, oW = over ? ((after - 100) / scale) * 100 : 0;
  const cands = (p.runner_up && p.runner_up.candidates) || [];
  const implied = p.match_method === 'implied' || p.match_method === 'other_vendor';
  const methodLabel = { explicit: 'Explicit', implied: 'Implied', other_vendor: 'Belongs to another vendor', none: 'No match' }[p.match_method] || p.match_method;
  return (
    <div className="card panel" data-testid="po-panel"><h3><Ic n="link" c="sm" />Purchase order match</h3>
      <div className="row wrap" style={{ marginBottom: 14 }}>
        <Link className="mono" href={`/master?po=${po.id}`} style={{ fontSize: 15, fontWeight: 700 }}>{po.id}</Link>
        <span className={`chip ${p.match_method === 'explicit' ? 's-auto' : 's-note'}`}><Ic n={p.match_method === 'explicit' ? 'check-circle' : 'note-circle'} />{methodLabel}{implied && p.match_score != null ? ` · ${Math.round(p.match_score * 100)}%` : ''}</span>
        <span className="small sec">Issued {fmtDay(po.issue_date)} · valid to {fmtDay(po.valid_to)} · {String(po.status).replace(/_/g, ' ')}</span>
      </div>
      {implied && cands.length ? (
        <div className="stack-s" style={{ marginBottom: 14 }}><div className="upper">Match candidates (inferred, no PO on the invoice)</div>
          {cands.slice(0, 3).map((cd, i) => (
            <div className={`cand ${i === 0 ? 'win' : ''}`} key={cd.po_id}>
              <div className="row"><b className="mono">{cd.po_id}</b>{i === 0 ? <span className="chip s-auto"><Ic n="check-circle" />Selected</span> : <span className="pill">Runner-up</span>}<span className="right" style={{ fontFamily: 'var(--f-head)', fontWeight: 800, fontSize: 18 }}>{Math.round(cd.score * 100)}%</span></div>
              {Object.entries(cd.parts || {}).map(([k, v]) => <div className="mini-b" key={k}><span>{k}</span><div className="bar"><i style={{ width: `${v * 100}%`, background: i === 0 ? 'var(--ok)' : 'var(--ink-3)' }} /></div><span className="num">{Math.round(v * 100)}%</span></div>)}
            </div>))}
        </div>
      ) : null}
      <div className="tbl-wrap"><table className="tbl po-t" data-testid="po-table"><thead><tr><th>Invoice line</th><th className="r">Ordered</th><th className="r">Billed before</th><th className="r">This invoice</th><th className="r">Remaining</th><th className="r">Unit price<div className="tiny" style={{ textTransform: 'none', letterSpacing: 0 }}>PO → invoice</div></th><th className="r">Variance</th><th className="c">Status</th></tr></thead><tbody>
        {(p.table || []).map((r) => {
          const none = !r.this_invoice_qty && !r.invoice_description;
          if (none) return <tr className="muted-row" key={r.po_line_id}><td>{r.item_code}: not on this invoice</td><td className="r num">{num(r.ordered_qty)}</td><td className="r num">{num(r.billed_before_qty)}</td><td className="r num">0</td><td className="r num">{num(r.remaining_before_qty)}</td><td colSpan={3} className="muted small">Already billed before</td></tr>;
          const color = r.status === 'pass' ? 'transparent' : OUT_COLOR[r.status] || 'transparent';
          const dp = r.unit_price_delta_pct || 0;
          return (
            <tr className="sev" style={{ '--sev': color }} key={`${r.po_line_id}-${r.invoice_line_no}`}>
              <td><div className="clamp2" title={r.invoice_description}>{r.invoice_description}</div><div className="tiny muted"><span className="mono">{r.item_code}</span>{r.bundle ? ' · bundle matched across PO lines' : ''}</div></td>
              <td className="r num">{num(r.ordered_qty)}</td><td className="r num">{num(r.billed_before_qty)}</td><td className="r num"><b>{num(r.this_invoice_qty)}</b></td>
              <td className="r num" style={r.over_qty ? { color: 'var(--reject-fg)', fontWeight: 700 } : undefined}>{num(Math.max(r.remaining_after_qty, 0) || r.remaining_before_qty - r.this_invoice_qty)}{r.over_qty ? <div className="tiny">{num(r.over_qty)} over</div> : null}</td>
              <td className="r num">{inrP2(r.po_unit_price_paise)} → {inrP2(r.invoice_unit_price_paise)}<div className={`tiny ${Math.abs(dp) > 0.005 ? '' : 'muted'}`}>{dp >= 0 ? '+' : ''}{dp.toFixed(1)}%</div></td>
              <td className="r num">{r.amount_variance_paise ? (r.amount_variance_paise > 0 ? '+' : '−') + inrP(Math.abs(r.amount_variance_paise)) : '₹0'}<div className="tiny muted">{r.amount_variance_pct ? r.amount_variance_pct.toFixed(1) + '%' : ''}</div></td>
              <td className="c"><SevIcon s={r.status} /></td>
            </tr>
          );
        })}
      </tbody></table></div>
      <div className="cum" style={{ marginTop: 16 }}><div className="upper" style={{ marginBottom: 6 }}>Cumulative billed against this PO (before tax)</div>
        <div className="track" role="img" aria-label={`${before.toFixed(0)} percent billed before, ${after.toFixed(0)} percent after`}><div className="a" style={{ width: `${aW}%` }} /><div className="b" style={{ width: `${bW}%` }} /><div className="b over" style={{ width: `${oW}%` }} /><span className="line" style={{ left: `${(100 / scale) * 100}%` }} /></div>
        <div className="cum-lab"><span><b>{before.toFixed(0)}%</b> billed before ({inrP(c.before_paise)})</span><span>PO value {inrP(c.po_subtotal_paise)} = 100%</span><span style={over ? { color: 'var(--reject-fg)', fontWeight: 700 } : undefined}><b>{after.toFixed(0)}%</b> after this invoice ({inrP((c.before_paise || 0) + (c.this_invoice_paise || 0))})</span></div></div>
      {(p.timeline || []).length ? (
        <><div className="upper" style={{ margin: '18px 0 10px' }}>All invoices against this PO</div>
          <div className="tl">{p.timeline.map((h) => (
            <div className={`ev ${h.is_current ? 'now' : ''}`} style={{ '--evc': OUT_COLOR[outKey(h.outcome)] }} key={h.invoice_id}>
              <div className="row wrap gap-s"><Link href={`/decision/${h.run_id}`} className="mono"><b>{h.invoice_no}</b></Link><span className="muted small">{fmtDay(h.invoice_date)}</span><span className="num">{inrP(h.total_paise)}</span><Chip k={h.outcome} />{h.is_current ? <span className="pill accent">This invoice</span> : null}{h.paid_at ? <span className="small sec">Paid {fmtDay(h.paid_at)}</span> : null}</div>
            </div>))}</div></>
      ) : null}
    </div>
  );
}

function RulesPanel({ d }) {
  const [showAll, setShowAll] = useState(true);
  const sorted = d.rules.slice().sort((a, b) => (b.skipped ? -1 : SEVRANK[b.severity]) - (a.skipped ? -1 : SEVRANK[a.severity]) || a.stage_no - b.stage_no);
  const vis = sorted.filter((r) => showAll || (r.severity !== 'pass' && !r.skipped));
  const flagged = d.rules.filter((r) => r.severity !== 'pass' && !r.skipped).length;
  const skipped = d.rules.filter((r) => r.skipped).length;
  return (
    <div className="card panel" data-testid="rules-panel"><h3><Ic n="check-circle" c="sm" />Rule checklist<span className="muted small" style={{ fontWeight: 500 }} data-testid="rules-summary">{flagged} flagged · {d.rules.length - flagged - skipped} passed{skipped ? ` · ${skipped} not checked` : ''}</span>
      <label className="right row gap-s small sec" style={{ fontWeight: 500, cursor: 'pointer' }}><button className="toggle" role="switch" aria-checked={showAll} onClick={() => setShowAll((s) => !s)} aria-label="Show passed checks" data-testid="toggle-passed" />Show passed checks</label></h3>
      {vis.map((r) => (
        <div className="rule" key={r.rule_id} data-testid="rule-row" data-rule={r.rule_id}>
          <span>{r.skipped ? <Ic n="minus" c="sm" style={{ color: 'var(--ink-3)' }} /> : <SevIcon s={r.severity} />}</span>
          <div><div className="rt">{r.name} <span className="rid">{r.rule_id}</span>{r.hard_stop ? <> <span className="pill" style={{ fontSize: 10.5 }}>Hard stop</span></> : null}<span className="tiny muted"> · {STAGE_NAMES[r.stage_no - 1]}</span></div>
            <div className="rs">{r.message}</div>
            <div className="tiny muted" style={{ marginTop: 2 }}>{r.allowed ? `${r.allowed}. ` : ''}<Link href="/rules">Why this rule?</Link></div></div>
          {r.skipped ? <span className="chip s-none">Not checked</span> : <SevChip s={r.severity} />}
        </div>
      ))}
    </div>
  );
}

function DraftsPanel({ d }) {
  const { toast } = useApp();
  const [chk, setChk] = useState({});
  const mail = (d.drafts || []).filter((x) => x.kind !== 'checklist'); const list = (d.drafts || []).find((x) => x.kind === 'checklist');
  if (!mail.length && !list) return null;
  return (
    <>
      {mail.map((dr, i) => (
        <div className="card panel" key={i} data-testid="draft-panel"><h3><Ic n="mail" c="sm" />{dr.title}<span className="pill right">Draft. Nothing is sent automatically</span></h3>
          <div className="small muted" style={{ marginBottom: 8 }}>To: {dr.to} · Subject: <b>{dr.subject}</b></div>
          <div className="draft">{dr.body}</div>
          <div className="row" style={{ marginTop: 12 }}><button className="btn" onClick={async () => { await copyText(`To: ${dr.to}\nSubject: ${dr.subject}\n\n${dr.body}`); toast('Email draft copied to the clipboard'); }}><Ic n="copy" c="sm" />Copy email draft</button></div>
        </div>
      ))}
      {list ? (
        <div className="card panel"><h3><Ic n="shield" c="sm" />{list.title}</h3>
          <div className="checklist">{list.items.map((t, i) => <label key={i}><input type="checkbox" className="check" checked={!!chk[i]} onChange={(e) => setChk((c) => ({ ...c, [i]: e.target.checked }))} /><span>{t}</span></label>)}</div>
          <p className="small sec" style={{ marginTop: 8 }}>After the checklist, a manager updates the vendor record in <Link href="/master">master data</Link> and re-runs the invoice. Ledgerlight then re-checks the bank details.</p></div>
      ) : null}
    </>
  );
}

/* ---------- page ---------- */
export default function Decision({ runId }) {
  const router = useRouter(); const params = useSearchParams();
  const { toast, tick, roleTick, setCrumb, settings } = useApp();
  const { data: d, error, loading, reload } = useApi(`/api/runs/${runId}`, { tick, deps: [roleTick] });
  const [override, setOverride] = useState(false);
  const [editF, setEditF] = useState(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [tab, setTab] = useState('doc');
  const [busy, setBusy] = useState(false);
  const [imgOk, setImgOk] = useState(false);
  useEffect(() => { setImgOk(false); }, [page, runId]);
  const rev = useApi('/api/review-queue?tab=review', { tick }); const hold = useApi('/api/review-queue?tab=hold', { tick });

  useEffect(() => { if (d && d.run.status === 'running') router.replace(`/runs/${runId}`); }, [d, runId, router]);
  useEffect(() => { if (params.get('override') === '1' && d) setOverride(true); }, [params, d]);
  useEffect(() => {
    if (!d) return undefined;
    const v = d.vendor_panel && d.vendor_panel.vendor ? d.vendor_panel.vendor.short : d.invoice.vendor_name_raw;
    setCrumb(<><span className="muted">Invoice decision</span><Ic n="chev-r" c="sm" />{v ? `${v} ` : ''}{d.invoice.invoice_no_raw || d.invoice.file_name}</>);
    return () => setCrumb(null);
  }, [d, setCrumb]);

  const exc = useMemo(() => {
    const all = [...(rev.data ? rev.data.items : []), ...(hold.data ? hold.data.items : [])];
    return all.sort((a, b) => b.exposure_paise * (1 + b.age_days) - a.exposure_paise * (1 + a.age_days));
  }, [rev.data, hold.data]);

  if (error && !d) return <div style={{ maxWidth: 640 }}><ErrorBanner error={error} onRetry={reload} /><div className="card"><Empty title={error.status === 404 ? 'We could not find that decision' : 'This decision could not be loaded'}><p>Open the dashboard to pick another run.</p><p style={{ marginTop: 12 }}><Link className="btn" href="/">Back to the dashboard</Link></p></Empty></div></div>;
  if (!d) return <div className="stack"><Shimmer h={110} style={{ borderRadius: 12 }} /><Shimmer h={220} style={{ borderRadius: 12 }} /><Shimmer h={420} style={{ borderRadius: 12 }} /></div>;

  const dec = d.decision; const k = outKey(dec.outcome); const inv = d.invoice;
  const hard = d.rules.some((r) => r.hard_stop && !r.skipped && r.severity === worstSev(d.rules) && ['reject', 'hold'].includes(r.severity));
  const idx = exc.findIndex((e) => e.run_id === runId || e.invoice_id === inv.id);
  const vend = d.vendor_panel && d.vendor_panel.vendor;
  const poId = d.po_panel ? d.po_panel.po.id : null;
  const overridden = d.overridden && dec.made_by === 'user';
  const sys = d.system_decision || {};
  const nPages = inv.page_count || 1;
  const decideBy = overridden ? `Overridden by ${dec.actor_name}` : `Decided by Ledgerlight at ${fmtT(dec.created_at)}${d.run.duration_ms != null ? ` in ${secs(d.run.duration_ms)}` : ''}`;

  async function accept() {
    setBusy(true);
    try { await api(`/api/invoices/${inv.id}/accept`, { method: 'POST', body: {} }); toast('Decision confirmed. Recorded in the audit log.'); reload(); } catch (e) { toast(e.message); } finally { setBusy(false); }
  }
  async function rerun() {
    try { const r = await api(`/api/invoices/${inv.id}/rerun`, { method: 'POST', body: { reason: 'Re-run from the decision page', pace: settings.speed, use_cache: settings.cache } }); router.push(`/runs/${r.run_id}`); } catch (e) { toast(e.message); }
  }
  async function copyJson() {
    try { const t = await (await fetch(url(`/api/runs/${runId}/decision.json`))).text(); await copyText(t); toast('Decision JSON copied to the clipboard'); } catch { toast("Couldn't fetch the decision JSON."); }
  }

  return (
    <div data-testid="decision-page" data-outcome={dec.outcome} data-run={runId}>
      <div className="row wrap" style={{ marginBottom: 12 }}>
        <Link className="btn ghost sm" href="/"><Ic n="arrow-l" c="sm" />Dashboard</Link>
        <span className="muted small">Run <span className="mono">{runId}</span> · {fmtDT(d.run.started_at)}{inv.sample_id ? <> · {inv.sample_id}</> : null}</span>
        <span className="right row gap-s">{idx >= 0 ? <>
          <button className="icon-btn" aria-label="Previous exception" disabled={idx === 0} onClick={() => router.push(`/decision/${exc[idx - 1].run_id}`)}><Ic n="chev-l" /></button>
          <span className="small muted">{idx + 1} of {exc.length} open exceptions</span>
          <button className="icon-btn" aria-label="Next exception" disabled={idx === exc.length - 1} onClick={() => router.push(`/decision/${exc[idx + 1].run_id}`)}><Ic n="chev-r" /></button></> : null}</span>
      </div>

      {overridden ? (
        <div className="banner info" style={{ marginBottom: 12 }} data-testid="override-banner"><Ic n="info" c="lg" /><span className="grow"><b>Decision changed from {(OUT[outKey(sys.outcome)] || {}).label} to {(OUT[k] || {}).label} by {dec.actor_name}, {fmtDT(dec.created_at)}.</b> Reason: {dec.reason_code}. {dec.reason_text} The original decision is preserved in the audit log.</span></div>
      ) : null}

      <div className={`card dcard sev-${k}`} id="dcard" data-testid="decision-card">
        <div className="grow" style={{ minWidth: 260 }}>
          <div className="row wrap gap-s" style={{ marginBottom: 8 }}><span data-testid="decision-chip"><Chip k={k} lg /></span><span className="muted small">{dec.outcome_long}{hard ? ' · hard stop, manager only' : ''}</span></div>
          <h2 data-testid="decision-headline">{dec.headline}</h2>
          <div className="meta">
            {inv.total_paise ? <span><b>{inrP2(inv.total_paise)}</b> gross</span> : null}
            {vend || inv.vendor_name_raw ? <span>{vend ? vend.name : inv.vendor_name_raw}</span> : null}
            {inv.invoice_no_raw ? <span className="mono">{inv.invoice_no_raw}</span> : null}
            {poId ? <span><Link href={`/master?po=${poId}`} className="mono">{poId}{inv.po_match_method === 'implied' ? ' (inferred)' : ''}</Link></span> : null}
            {dec.exposure_paise ? <span>Exposure <b style={{ color: `var(--${k === 'hold' ? 'hold' : k === 'reject' ? 'reject' : 'review'}-fg)` }}>{inrP(dec.exposure_paise)}</b></span> : null}
            {dec.assigned_to && ['review', 'hold', 'reject'].includes(k) ? <span>Assigned to <b>{dec.assigned_to === 'manager' ? 'Manager' : 'Clerk pool'}</b></span> : null}
            {k === 'hold' && dec.sla_due_at ? <span>SLA due {fmtDay(dec.sla_due_at.slice(0, 10))}</span> : null}
            <span>{decideBy}{dec.confirmed_by ? ` · confirmed by ${dec.confirmed_by}` : ''}</span>
          </div>
        </div>
        <div className="row wrap gap-s" style={{ alignSelf: 'flex-start' }}>
          <button className="btn" onClick={accept} disabled={!!dec.confirmed_by || busy} data-testid="accept-btn"><Ic n="check" c="sm" />{dec.confirmed_by ? 'Confirmed' : 'Accept decision'}</button>
          <button className="btn primary" onClick={() => setOverride(true)} data-testid="override-btn"><Ic n="edit" c="sm" />Override…</button>
          <button className="btn" onClick={rerun}><Ic n="refresh" c="sm" />Re-run</button>
          <button className="btn" onClick={copyJson}><Ic n="copy" c="sm" />Copy JSON</button>
        </div>
      </div>

      <div className="m-tabs tabs" style={{ marginTop: 12 }}><button className={tab === 'doc' ? 'on' : ''} onClick={() => setTab('doc')}>Document</button><button className={tab === 'an' ? 'on' : ''} onClick={() => setTab('an')}>Analysis</button></div>
      <Explain d={d} />

      <div className="split" data-tab={tab} id="split">
        <div className="doccol card flat" style={{ overflow: 'hidden', alignSelf: 'start' }}>
          <div className="pdfcol" style={{ boxShadow: 'none' }} data-testid="pdf-col">
            <div className="pdf-bar"><Ic n="file" c="sm" /><span className="trunc grow">{inv.file_name}</span>{inv.doc_type === 'scanned' ? <span className="pill accent">Scanned image</span> : null}
              {d.has_pdf ? <>
                <button className="icon-btn" onClick={() => setZoom((z) => clamp(+(z - 0.1).toFixed(1), 0.6, 1.5))} aria-label="Zoom out" style={{ width: 28, height: 28 }}>−</button><span className="small num">{Math.round(zoom * 100)}%</span><button className="icon-btn" onClick={() => setZoom((z) => clamp(+(z + 0.1).toFixed(1), 0.6, 1.5))} aria-label="Zoom in" style={{ width: 28, height: 28 }}>+</button>
                {nPages > 1 ? <><button className="icon-btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Previous page" style={{ width: 28, height: 28 }}><Ic n="chev-l" c="sm" /></button><span className="small muted">Page {page} of {nPages}</span><button className="icon-btn" disabled={page >= nPages} onClick={() => setPage((p) => p + 1)} aria-label="Next page" style={{ width: 28, height: 28 }}><Ic n="chev-r" c="sm" /></button></> : <span className="small muted">Page 1 of 1</span>}
                <a className="btn sm" href={url(`${d.pdf_url}`)} target="_blank" rel="noreferrer" data-testid="open-pdf"><Ic n="download" c="sm" />PDF</a></> : null}
            </div>
            <div className="paper-wrap">
              {d.has_pdf ? <div style={{ width: `${zoom * 100}%`, maxWidth: 640 * zoom }}>{!imgOk ? <Shimmer h={460} /> : null}<img className="pdf-img" data-testid="pdf-page" style={imgOk ? undefined : { display: 'none' }} onLoad={() => setImgOk(true)} src={url(`/api/invoices/${inv.id}/pages/${page}.png?dpi=110`)} alt={`Page ${page} of ${inv.file_name}, the original invoice`} /></div>
                : <div className="nopdf"><Ic n="file" c="lg" /><b>PDF not stored for demo history</b><span className="small">{d.pdf_note || 'This run came from the seeded history, so only the extracted data and decision are kept. Uploaded invoices keep their PDF.'}</span></div>}
            </div>
          </div>
        </div>
        <div className="stack analysis">
          <FieldsPanel d={d} onEdit={setEditF} />
          <VendorPanel d={d} />
          <POPanel d={d} />
          <RulesPanel d={d} />
          <DraftsPanel d={d} />
          <div className="card panel" data-testid="activity"><h3><Ic n="clock" c="sm" />Activity<Link className="right small" href={`/audit?invoice=${inv.id}`} data-testid="audit-link">Open this invoice in the audit log</Link></h3>
            <div className="tl">{(d.timeline || []).map((e, i, a) => <div className={`ev ${i === a.length - 1 ? 'now' : ''}`} key={e.id} style={{ '--evc': e.outcome && OUT_COLOR[outKey(e.outcome)] ? OUT_COLOR[outKey(e.outcome)] : 'var(--line-2)' }}><div className="small muted">{fmtDT(e.ts)} · {e.actor_id}</div><div>{e.summary}</div></div>)}</div></div>
          <details className="drawer"><summary><Ic n="cpu" c="sm" />Technical details<span className="muted small" style={{ fontWeight: 500 }}>Extraction and decision JSON</span></summary>
            <div className="row" style={{ padding: '0 18px 12px' }}><a className="btn sm" href={url(`/api/runs/${runId}/decision.json`)} target="_blank" rel="noreferrer"><Ic n="download" c="sm" />Download decision JSON</a></div>
            <pre className="json">{JSON.stringify({ decision: { id: dec.id, version: dec.version, outcome: dec.outcome, driving_rule_ids: dec.driving_rule_ids, exposure_paise: dec.exposure_paise, made_by: dec.made_by }, technical: d.technical, run: d.run }, null, 2)}</pre></details>
        </div>
      </div>

      <OverrideSheet open={override} onClose={() => setOverride(false)} d={d} onDone={reload} />
      <EditField f={editF} d={d} onClose={() => setEditF(null)} />
    </div>
  );
}
