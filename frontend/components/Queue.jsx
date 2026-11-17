'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { api, qs } from '@/lib/api';
import { downloadText, fmtDT, inrP, inrP2 } from '@/lib/format';
import { Chip, Empty, ErrorBanner, Ic, PageHead, SevIcon, Shimmer, copyText, outKey, useApi, useApp } from '@/lib/ui';

const TABS = [['review', 'Needs review'], ['hold', 'On hold'], ['rejected', 'Rejected']];
const ageBadge = (r) => {
  const hold = outKey(r.outcome) === 'hold';
  const cls = r.age_badge === 'red' || (hold && r.sla_breached) ? 'red' : r.age_badge === 'amber' || r.age_days >= 1 ? 'amber' : '';
  return <span className={`age ${cls}`} data-tip={hold ? 'Hold SLA is 3 business days' : 'Same business day target'}>{r.age_days === 0 ? 'Today' : `${r.age_days} ${r.age_days === 1 ? 'day' : 'days'}`}</span>;
};
const owner = (a) => (a === 'manager' ? 'Manager' : a === 'clerk' ? 'Clerk pool' : 'Unassigned');

function QuickPanel({ item, onClose, onChanged }) {
  const router = useRouter(); const { toast, settings } = useApp();
  const { data: d } = useApi(`/api/runs/${item.run_id}`, { deps: [item.run_id] });
  const [busy, setBusy] = useState(false);
  const k = outKey(item.outcome);
  const top = d && d.po_panel ? (d.po_panel.table || []).filter((x) => x.this_invoice_qty && x.status !== 'pass').slice(0, 2) : [];
  const draft = d && (d.drafts || []).find((x) => x.kind !== 'checklist');
  async function accept() {
    setBusy(true);
    try { await api(`/api/invoices/${item.invoice_id}/accept`, { method: 'POST', body: { note: 'Marked reviewed from the review queue' } }); toast(`${item.invoice_no} marked reviewed and moved to Resolved. To change what is paid, use Override.`); onChanged(); onClose(); }
    catch (e) { toast(e.message); } finally { setBusy(false); }
  }
  async function asked() { try { const r = await api(`/api/invoices/${item.invoice_id}/info-requested`, { method: 'POST', body: {} }); toast('Info requested. The wait for the vendor has started.'); onChanged(); return r; } catch (e) { toast(e.message); } return null; }
  async function upload(file) {
    if (!file) return; const fd = new FormData(); fd.append('file', file); fd.append('pace', settings.speed);
    try { const r = await api(`/api/invoices/${item.invoice_id}/documents`, { method: 'POST', form: fd }); toast('Document received. The pipeline is re-running with the new file.'); router.push(`/runs/${r.run_id}`); } catch (e) { toast(e.message); }
  }
  return (
    <aside className="card qpanel fade-in" aria-label="Quick view" data-testid="quick-panel">
      <div className="row"><div className="grow"><div className="row gap-s"><Chip k={k} /><span className="mono small muted">{item.invoice_no}</span></div></div><button className="icon-btn" onClick={onClose} aria-label="Close quick view"><Ic n="x" c="sm" /></button></div>
      <h3 style={{ fontSize: 16, lineHeight: 1.35 }}>{item.headline}</h3>
      <dl className="kv"><dt>Vendor</dt><dd>{item.vendor_name}</dd><dt>Amount</dt><dd className="num"><b>{inrP2(item.gross_paise)}</b></dd><dt>Exposure</dt><dd className="num"><b>{inrP(item.exposure_paise)}</b></dd><dt>PO</dt><dd className="mono">{item.po_id || '—'}</dd><dt>Assigned</dt><dd>{owner(item.assigned_to)} · {ageBadge(item)}</dd></dl>
      {!d ? <Shimmer h={40} /> : null}
      {top.length ? <div><div className="upper" style={{ marginBottom: 6 }}>Biggest differences from the PO</div>{top.map((x) => <div className="row small" style={{ padding: '6px 0', borderBottom: '1px solid var(--line)' }} key={x.po_line_id}><SevIcon s={x.status} /><span className="grow">{x.invoice_description}</span><span className="num sec">{x.over_qty ? `${x.over_qty} over` : `${x.unit_price_delta_pct.toFixed(1)}%`}</span><b className="num">{x.amount_variance_paise ? '+' + inrP(x.amount_variance_paise) : ''}</b></div>)}</div> : null}
      <div className="next small"><b>{item.recommended_action}</b></div>
      {k === 'hold' ? (
        <div className="stack-s"><div className="upper">Hold controls</div>
          <div className="row wrap gap-s">
            <button className="btn sm" disabled={!draft} onClick={async () => { await copyText(`To: ${draft.to}\nSubject: ${draft.subject}\n\n${draft.body}`); toast('Email draft copied to the clipboard'); }}><Ic n="copy" c="sm" />Copy vendor email draft</button>
            <button className="btn sm" onClick={asked} disabled={!!item.info_requested_at}><Ic n="clock" c="sm" />{item.info_requested_at ? 'Info requested. SLA running' : 'Mark info requested'}</button>
            <label className="btn sm" htmlFor={`up-${item.invoice_id}`}><Ic n="upload" c="sm" />Upload received document</label>
            <input hidden type="file" id={`up-${item.invoice_id}`} accept="application/pdf" onChange={(e) => upload(e.target.files[0])} />
          </div></div>
      ) : null}
      <div className="row wrap gap-s">
        {k !== 'reject' ? <button className="btn primary" onClick={accept} disabled={busy} data-testid="q-accept"><Ic n="check" c="sm" />Mark reviewed (agree)</button> : null}
        <Link className="btn" href={`/decision/${item.run_id}?override=1`}>Override…</Link>
        <Link className="btn" href={`/decision/${item.run_id}`} data-testid="q-open">Open full detail</Link>
      </div>
    </aside>
  );
}

export default function Queue() {
  const { tick, roleTick, role, refreshQueue } = useApp();
  const [tab, setTab] = useState('review');
  const [f, setF] = useState({ assigned: 'all', min_exposure: 'all', category: 'all', vendor_id: 'all', sort: 'priority' });
  const [sel, setSel] = useState(null);
  const [checked, setChecked] = useState(new Set());
  const apiAssigned = f.assigned === 'me' ? role : f.assigned;
  const path = '/api/review-queue' + qs({ tab, assigned: apiAssigned, min_exposure: f.min_exposure, category: f.category, vendor_id: f.vendor_id, sort: f.sort });
  const { data, error, loading, reload } = useApi(path, { tick, deps: [roleTick] });
  const vendors = useApi('/api/vendors');
  const items = data ? data.items : [];
  const counts = data ? data.counts : {};
  const selItem = sel ? items.find((i) => i.invoice_id === sel) : null;
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const toggleChk = (id) => setChecked((c) => { const n = new Set(c); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const cats = data && data.categories && data.categories.length ? data.categories : ['Quantity or price above PO', 'Duplicate', 'Bank change', 'Missing information', 'Vendor problem', 'Tax or total'];
  const refresh = () => { reload(); refreshQueue && refreshQueue(); };

  function exportSel() {
    const rows = items.filter((i) => checked.has(i.invoice_id));
    const head = ['invoice_no', 'vendor', 'po', 'gross_inr', 'exposure_inr', 'decision', 'assigned_to', 'reason'];
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    downloadText('review-queue-selected.csv', [head.join(','), ...rows.map((r) => [r.invoice_no, r.vendor_name, r.po_id, r.gross_paise / 100, r.exposure_paise / 100, r.outcome_label, r.assigned_to, r.reason].map(esc).join(','))].join('\n'), 'text/csv');
  }

  return (
    <>
      <PageHead title="Review queue" sub="Everything a person has to touch, ranked by risk and age.">
        <span className="small muted">Showing the queue as <b>{role === 'manager' ? 'AP Manager' : 'AP Clerk'}</b></span>
      </PageHead>
      <div className="stack">
        <ErrorBanner error={error} onRetry={reload} />
        <div className="tabs" role="tablist">
          {TABS.map(([k, n]) => <button key={k} role="tab" className={tab === k ? 'on' : ''} onClick={() => { setTab(k); setSel(null); setChecked(new Set()); }} data-testid={`tab-${k}`}>{n}<span className="ct">{counts[k] ?? '–'}</span></button>)}
          <button role="tab" className={tab === 'resolved' ? 'on' : ''} onClick={() => { setTab('resolved'); setSel(null); }} data-testid="tab-resolved">Resolved, last 30 days<span className="ct">{counts.resolved ?? '–'}</span></button>
        </div>
        {tab !== 'resolved' ? (
          <div className="row wrap">
            <label className="field-l" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>Assigned to<select value={f.assigned} onChange={(e) => set('assigned', e.target.value)}><option value="all">Anyone</option><option value="me">Me</option><option value="clerk">Clerk pool</option><option value="manager">Manager</option></select></label>
            <label className="field-l" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>Exposure<select value={f.min_exposure} onChange={(e) => set('min_exposure', e.target.value)}><option value="all">Any</option><option value="10000">Above ₹10,000</option><option value="100000">Above ₹1,00,000</option></select></label>
            <label className="field-l" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>Vendor<select value={f.vendor_id} onChange={(e) => set('vendor_id', e.target.value)}><option value="all">All vendors</option>{(vendors.data ? vendors.data.items : []).map((v) => <option key={v.id} value={v.id}>{v.short}</option>)}</select></label>
            <label className="field-l" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>Reason<select value={f.category} onChange={(e) => set('category', e.target.value)}><option value="all">All reasons</option>{cats.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="field-l right" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>Sort<select value={f.sort} onChange={(e) => set('sort', e.target.value)}><option value="priority">Risk and age</option><option value="exposure">Exposure</option><option value="age">Age</option></select></label>
          </div>
        ) : null}
        {checked.size ? <div className="banner info fade-in"><b>{checked.size} selected</b><span className="grow" /><button className="btn sm" onClick={exportSel}><Ic n="download" c="sm" />Export CSV</button></div> : null}
        <div className={`q-layout ${selItem && tab !== 'resolved' ? 'has-panel' : ''}`}>
          <div className="stack-s" style={{ gap: 10, minWidth: 0 }} data-testid="queue-list">
            {loading && !data ? Array.from({ length: 4 }).map((_, i) => <Shimmer key={i} h={86} style={{ borderRadius: 12 }} />) : null}
            {tab === 'resolved' ? (
              <div className="card"><div className="tbl-wrap"><table className="tbl"><thead><tr><th>Invoice</th><th>Vendor</th><th className="r">Amount</th><th>Final</th><th>Resolved by</th><th>Reason</th><th>When</th></tr></thead><tbody>
                {items.map((r) => <tr key={r.invoice_id} className="link" onClick={() => (location.href = `/decision/${r.run_id}`)}><td className="mono">{r.invoice_no}</td><td>{r.vendor_short}</td><td className="r num">{inrP2(r.gross_paise)}</td><td><Chip k={r.outcome} /></td><td>{r.actor_name || '—'}</td><td className="sec">{r.reason_code || ''}</td><td className="muted small">{fmtDT(r.decided_at)}</td></tr>)}
                {!items.length && !loading ? <tr><td colSpan={7}><Empty title="Nothing resolved yet"><p>Decisions a person confirms or overrides in the last 30 days show up here.</p></Empty></td></tr> : null}
              </tbody></table></div></div>
            ) : items.map((r) => {
              const k = outKey(r.outcome);
              return (
                <div key={r.invoice_id} className={`qrow sev-${k} ${sel === r.invoice_id ? 'sel' : ''}`} tabIndex={0} role="button" aria-label={`Open quick view for ${r.invoice_no}`} data-testid="queue-row"
                  onClick={(e) => { if (e.target.closest('input')) return; setSel(r.invoice_id); }} onKeyDown={(e) => { if (e.key === 'Enter') setSel(r.invoice_id); }}>
                  <input type="checkbox" className="check" checked={checked.has(r.invoice_id)} onChange={() => toggleChk(r.invoice_id)} onClick={(e) => e.stopPropagation()} aria-label={`Select ${r.invoice_no}`} />
                  <div className="trunc" style={{ minWidth: 150 }}><div className="row gap-s"><Chip k={k} /></div><div style={{ marginTop: 6 }}><b>{r.vendor_short || r.vendor_name}</b> <span className="mono small sec">{r.invoice_no}</span></div><div className="tiny muted">{inrP2(r.gross_paise)}</div></div>
                  <div className="sec" style={{ minWidth: 0 }}>{r.reason}<div className="tiny muted" style={{ marginTop: 3 }}>{r.category || ''}</div></div>
                  <div className="side"><div className="num" style={{ fontFamily: 'var(--f-head)', fontWeight: 800, fontSize: 16 }}>{inrP(r.exposure_paise)}</div><div className="tiny muted">exposure</div><div className="row gap-s">{ageBadge(r)}<span className="tag">{owner(r.assigned_to)}</span></div></div>
                  <div className="rec"><Ic n="arrow-r" c="sm" /><span><b>Recommended:</b> {r.recommended_action}</span></div>
                </div>
              );
            })}
            {tab !== 'resolved' && !loading && !items.length ? <div className="card empty"><h4>Nothing needs you right now</h4><p>Everything in this view has been handled, or was approved without a person.</p><p style={{ marginTop: 12 }}><Link className="btn" href="/">Back to the dashboard</Link></p></div> : null}
          </div>
          {selItem && tab !== 'resolved' ? <QuickPanel item={selItem} onClose={() => setSel(null)} onChanged={refresh} /> : null}
        </div>
      </div>
    </>
  );
}
