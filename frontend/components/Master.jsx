'use client';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { API, url, api, getApiRole, qs } from '@/lib/api';
import { downloadText, fmtDay, inrP, num } from '@/lib/format';
import { Chip, Empty, ErrorBanner, Ic, Modal, PageHead, Sheet, Shimmer, useApi, useApp } from '@/lib/ui';

const PO_CHIP = { open: ['s-note', 'Open'], partially_billed: ['s-review', 'Partially billed'], fully_billed: ['s-auto', 'Fully billed'], closed: ['s-none', 'Closed'], cancelled: ['s-reject', 'Cancelled'] };
const V_CHIP = { approved: ['s-auto', 'Approved', 'check-circle'], pending: ['s-hold', 'Pending onboarding', 'pause-circle'], blocked: ['s-reject', 'Blocked', 'x-circle'] };
const POChip = ({ s }) => { const [c, l] = PO_CHIP[s] || ['s-none', s]; return <span className={`chip ${c}`}>{l}</span>; };

/* ---------- PO drawer ---------- */
function PoDrawer({ id, onClose, onChanged }) {
  const { toast } = useApp();
  const { data: p, reload } = useApi(id ? `/api/pos/${id}` : null, { deps: [id], enabled: !!id });
  const [hdr, setHdr] = useState({ issue_date: '', valid_to: '' });
  const [newLine, setNewLine] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { if (p) setHdr({ issue_date: p.issue_date, valid_to: p.valid_to }); setErr(null); setNewLine(null); }, [p && p.id, p && p.valid_to]);
  async function save() {
    setErr(null);
    try { await api(`/api/pos/${id}`, { method: 'PATCH', body: hdr }); toast('Saved. The change was recorded in the audit log with the values before and after.'); reload(); onChanged(); }
    catch (e) { setErr(e); }
  }
  async function act(a) {
    try { await api(`/api/pos/${id}/${a}`, { method: 'POST', body: { reason: `${a} from the master data screen` } }); toast(`${id} is now ${a === 'reopen' ? 'open' : a === 'close' ? 'closed' : 'cancelled'}. Recorded in the audit log.`); reload(); onChanged(); }
    catch (e) { setErr(e); }
  }
  async function addLine() {
    setErr(null);
    try { await api(`/api/pos/${id}/lines`, { method: 'POST', body: { item_code: newLine.item_code, description: newLine.description, uom: newLine.uom || 'nos', ordered_qty: Number(newLine.ordered_qty), unit_price: String(newLine.unit_price), tax_rate_pct: Number(newLine.tax_rate_pct || 18) } }); toast('Line added and recorded in the audit log.'); setNewLine(null); reload(); onChanged(); }
    catch (e) { setErr(e); }
  }
  return (
    <Sheet open={!!id} onClose={onClose} wide label="Purchase order">
      {!p ? <div className="sheet-b"><Shimmer h={30} /><Shimmer h={200} /></div> : (
        <>
          <div className="sheet-h"><div><div className="upper">Purchase order</div><h3 className="mono">{p.id}</h3></div><POChip s={p.status} /><button className="icon-btn right" onClick={onClose} aria-label="Close"><Ic n="x" /></button></div>
          <div className="sheet-b" data-testid="po-drawer">
            {p.locked ? <div className="banner info"><Ic n="lock" c="lg" /><span>This PO has invoices against it, so the vendor and item codes are read-only. Changing them would rewrite history.</span></div> : null}
            {err ? <div className="banner bad" role="alert"><Ic n="warn" /><span>{err.message}</span></div> : null}
            <div className="params">
              <label className="field-l">Vendor<input type="text" value={p.vendor_name} disabled /></label>
              <label className="field-l">Issued<input type="text" value={hdr.issue_date} onChange={(e) => setHdr({ ...hdr, issue_date: e.target.value })} placeholder="YYYY-MM-DD" /></label>
              <label className="field-l">Valid to<input type="text" value={hdr.valid_to} onChange={(e) => setHdr({ ...hdr, valid_to: e.target.value })} placeholder="YYYY-MM-DD" /></label>
              <label className="field-l">Pre-tax value<input type="text" value={inrP(p.subtotal_paise)} disabled /></label>
            </div>
            <div><div className="upper" style={{ marginBottom: 6 }}>Lines</div><div className="tbl-wrap"><table className="tbl"><thead><tr><th>Item code</th><th>Description</th><th className="r">Ordered</th><th className="r">Unit price</th><th className="r">GST</th><th className="r">Billed</th><th className="r">Remaining</th></tr></thead><tbody>
              {p.lines.map((l) => <tr key={l.id}><td className="mono small">{l.item_code}</td><td>{l.description}</td><td className="r num">{num(l.ordered_qty)} {l.uom}</td><td className="r num">{inrP(l.unit_price_paise, l.unit_price_paise % 100 ? 2 : 0)}</td><td className="r num">{l.tax_rate_pct}%</td><td className="r num">{num(l.billed_qty)}{l.pending_qty ? <div className="tiny muted">+{num(l.pending_qty)} pending</div> : null}</td><td className="r num"><b>{num(l.remaining_qty)}</b></td></tr>)}
            </tbody></table></div></div>
            {newLine ? (
              <div className="stack-s fade-in" style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
                <div className="params">
                  {[['item_code', 'Item code'], ['description', 'Description'], ['uom', 'Unit'], ['ordered_qty', 'Ordered qty'], ['unit_price', 'Unit price (₹)'], ['tax_rate_pct', 'GST %']].map(([k, l]) => <label className="field-l" key={k}>{l}<input type="text" value={newLine[k] || ''} onChange={(e) => setNewLine({ ...newLine, [k]: e.target.value })} /></label>)}
                </div>
                <div className="row"><button className="btn primary sm" onClick={addLine}>Save line</button><button className="btn sm" onClick={() => setNewLine(null)}>Cancel</button></div>
              </div>
            ) : null}
            <div><div className="upper" style={{ marginBottom: 8 }}>Billing history</div>
              {p.billing_history.length ? <div className="tl">{p.billing_history.map((h) => <div className="ev" key={h.invoice_id} style={{ '--evc': 'var(--line-2)' }}><div className="row wrap gap-s"><Link className="mono" href={`/decision/${h.run_id}`}><b>{h.invoice_no}</b></Link><span className="muted small">{fmtDay(h.invoice_date)}</span><span className="num">{inrP(h.total_paise)}</span><Chip k={h.outcome} />{h.paid_at ? <span className="small sec">Paid {fmtDay(h.paid_at)}</span> : null}</div></div>)}</div> : <div className="small muted">No invoices yet.</div>}</div>
          </div>
          <div className="sheet-f">
            {p.status === 'closed' || p.status === 'cancelled' ? <button className="btn" onClick={() => act('reopen')}>Reopen PO</button> : <><button className="btn danger" onClick={() => act('cancel')}>Cancel PO</button><button className="btn" onClick={() => act('close')}>Close PO</button></>}
            <button className="btn" onClick={() => setNewLine({})}>Add line</button>
            <button className="btn primary" onClick={save}>Save changes</button>
          </div>
        </>
      )}
    </Sheet>
  );
}

/* ---------- vendor drawer ---------- */
function VendorDrawer({ id, onClose, onChanged }) {
  const { toast, role } = useApp();
  const { data: v, reload } = useApi(id ? `/api/vendors/${id}` : null, { deps: [id], enabled: !!id });
  const [form, setForm] = useState(null); const [bank, setBank] = useState({ bank_name: '', bank_account_no: '', bank_ifsc: '', verified_by: '', reason: '' });
  const [err, setErr] = useState(null);
  useEffect(() => { setForm(null); setErr(null); }, [id]);
  const mgr = role === 'manager';
  async function setStatus(s) { try { await api(`/api/vendors/${id}`, { method: 'PATCH', body: { status: s } }); toast(`${v.short} is now ${V_CHIP[s][1].toLowerCase()}. Recorded in the audit log.`); reload(); onChanged(); } catch (e) { setErr(e); } }
  async function saveBank() {
    setErr(null);
    try { await api(`/api/vendors/${id}/bank`, { method: 'POST', body: bank }); toast('Bank details updated and recorded. Re-run the held invoice to clear the hold.'); setForm(null); reload(); onChanged(); } catch (e) { setErr(e); }
  }
  const st = v ? V_CHIP[v.status] : null;
  return (
    <Sheet open={!!id} onClose={onClose} label="Vendor">
      {!v ? <div className="sheet-b"><Shimmer h={30} /><Shimmer h={200} /></div> : (
        <>
          <div className="sheet-h"><div><div className="upper">Vendor {v.id}</div><h3>{v.name}</h3></div><span className={`chip ${st[0]}`}><Ic n={st[2]} />{st[1]}</span><button className="icon-btn right" onClick={onClose} aria-label="Close"><Ic n="x" /></button></div>
          <div className="sheet-b" data-testid="vendor-drawer">
            {err ? <div className="banner bad" role="alert"><Ic n="warn" /><span>{err.message}{err.fields ? ' ' + Object.values(err.fields).join(' ') : ''}</span></div> : null}
            <dl className="kv"><dt>GSTIN</dt><dd className="mono">{v.gstin}</dd><dt>Also known as</dt><dd>{(v.aliases || []).join(', ') || '—'}</dd><dt>Payment terms</dt><dd>Net {v.payment_terms_days}</dd><dt>Contact phone</dt><dd className="mono">{v.contact_phone} <span className="muted small">(call this number to verify changes)</span></dd><dt>Address</dt><dd>{v.address}</dd></dl>
            <div className="card flat" style={{ padding: '14px 16px' }}>
              <div className="row" style={{ marginBottom: 8 }}><b>Bank details</b><span className="muted small right">Last change {v.bank_changed_at ? fmtDay(v.bank_changed_at) : 'n/a'}{v.bank_verified_by ? ` · verified by ${v.bank_verified_by}` : ''}</span></div>
              {v.bank_account_no ? <div className="kv"><dt>Bank</dt><dd>{v.bank_name}</dd><dt>Account</dt><dd className="mono">{v.bank_account_no}</dd><dt>IFSC</dt><dd className="mono">{v.bank_ifsc}</dd></div> : <div className="sec small">No bank details on file.</div>}
              <div style={{ marginTop: 12 }}><button className="btn" disabled={!mgr} onClick={() => setForm(true)} data-testid="change-bank"><Ic n="lock" c="sm" />Change bank details</button>{!mgr ? <span className="small muted" style={{ marginLeft: 8 }}>Manager only. Switch role in the top bar.</span> : null}</div>
              {form ? (
                <div className="stack-s fade-in" style={{ marginTop: 14, borderTop: '1px solid var(--line)', paddingTop: 14 }}>
                  <div className="params">{[['bank_name', 'Bank'], ['bank_account_no', 'Account'], ['bank_ifsc', 'IFSC']].map(([k, l]) => <label className="field-l" key={k}>{l}<input type="text" value={bank[k]} onChange={(e) => setBank({ ...bank, [k]: e.target.value })} /></label>)}</div>
                  <label className="field-l">Verified by<input type="text" value={bank.verified_by} onChange={(e) => setBank({ ...bank, verified_by: e.target.value })} placeholder="Rahul Mehta and a second person" /></label>
                  <label className="field-l">Reason (required, 10+ characters)<textarea value={bank.reason} onChange={(e) => setBank({ ...bank, reason: e.target.value })} placeholder="Written request received on letterhead and confirmed by phone" /></label>
                  <button className="btn primary" onClick={saveBank} disabled={bank.reason.trim().length < 10 || !bank.bank_account_no || !bank.verified_by}>Save bank details</button>
                </div>
              ) : null}
            </div>
            <div><div className="upper" style={{ marginBottom: 6 }}>Open purchase orders</div>{(v.purchase_orders || []).filter((p) => !['closed', 'fully_billed', 'cancelled'].includes(p.status)).map((p) => <div className="row small" style={{ padding: '5px 0' }} key={p.id}><span className="mono">{p.id}</span><POChip s={p.status} /><span className="right num">{inrP(p.subtotal_paise)}</span></div>)}{!(v.purchase_orders || []).some((p) => !['closed', 'fully_billed', 'cancelled'].includes(p.status)) ? <div className="small muted">None open.</div> : null}</div>
            <div><div className="upper" style={{ marginBottom: 6 }}>Recent invoices</div>{(v.recent_invoices || []).slice(0, 4).map((r) => <div className="row small" style={{ padding: '5px 0' }} key={r.invoice_id}><Link className="mono" href={`/decision/${r.run_id}`}>{r.invoice_no}</Link><Chip k={r.outcome} /><span className="right num">{inrP(r.total_paise)}</span></div>)}{!(v.recent_invoices || []).length ? <div className="small muted">No invoices yet.</div> : null}</div>
            <label className="field-l">Vendor status<select value={v.status} onChange={(e) => setStatus(e.target.value)} data-testid="vendor-status"><option value="approved">Approved</option><option value="pending">Pending onboarding</option><option value="blocked">Blocked</option></select></label>
          </div>
        </>
      )}
    </Sheet>
  );
}

/* ---------- add / import ---------- */
function AddModal({ kind, open, onClose, vendors, onDone }) {
  const { toast } = useApp();
  const [f, setF] = useState({}); const [err, setErr] = useState(null);
  useEffect(() => { if (open) { setF(kind === 'po' ? { id: '', vendor_id: vendors[0] ? vendors[0].id : '', issue_date: '2026-11-16', valid_to: '2026-12-31', item_code: '', description: '', uom: 'nos', ordered_qty: '', unit_price: '', tax_rate_pct: '18' } : { name: '', gstin: '', status: 'pending', payment_terms_days: '30' }); setErr(null); } }, [open, kind]); // eslint-disable-line
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    setErr(null);
    try {
      if (kind === 'po') await api('/api/pos', { method: 'POST', body: { id: f.id, vendor_id: f.vendor_id, issue_date: f.issue_date, valid_to: f.valid_to, currency: 'INR', lines: [{ item_code: f.item_code, description: f.description, uom: f.uom, ordered_qty: Number(f.ordered_qty), unit_price: String(f.unit_price), tax_rate_pct: Number(f.tax_rate_pct) }] } });
      else await api('/api/vendors', { method: 'POST', body: { name: f.name, gstin: f.gstin, status: f.status, payment_terms_days: Number(f.payment_terms_days) } });
      toast(kind === 'po' ? 'Purchase order saved.' : 'Vendor saved.'); onClose(); onDone();
    } catch (e) { setErr(e); }
  }
  return (
    <Modal open={open} onClose={onClose} label={kind === 'po' ? 'Add purchase order' : 'Add vendor'}>
      <div className="sheet-h"><h3>{kind === 'po' ? 'Add purchase order' : 'Add vendor'}</h3><button className="icon-btn right" onClick={onClose} aria-label="Close"><Ic n="x" /></button></div>
      <div className="sheet-b">
        {err ? <div className="banner bad" role="alert"><Ic n="warn" /><span>{err.message}{err.fields ? ' ' + Object.entries(err.fields).map(([k, v]) => `${k}: ${v}`).join(' · ') : ''}</span></div> : null}
        {kind === 'po' ? (
          <>
            <label className="field-l">Vendor<select value={f.vendor_id || ''} onChange={set('vendor_id')}>{vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
            <div className="params"><label className="field-l">PO number<input type="text" value={f.id || ''} onChange={set('id')} placeholder="PO-2026-1010" /></label><label className="field-l">Issued<input type="text" value={f.issue_date || ''} onChange={set('issue_date')} /></label><label className="field-l">Valid to<input type="text" value={f.valid_to || ''} onChange={set('valid_to')} /></label></div>
            <div className="upper">First line</div>
            <div className="params">{[['item_code', 'Item code'], ['description', 'Description'], ['uom', 'Unit'], ['ordered_qty', 'Ordered qty'], ['unit_price', 'Unit price (₹)'], ['tax_rate_pct', 'GST %']].map(([k, l]) => <label className="field-l" key={k}>{l}<input type="text" value={f[k] || ''} onChange={set(k)} /></label>)}</div>
          </>
        ) : (
          <>
            <label className="field-l">Vendor name<input type="text" value={f.name || ''} onChange={set('name')} /></label>
            <div className="params"><label className="field-l">GSTIN<input type="text" maxLength={15} value={f.gstin || ''} onChange={set('gstin')} /></label><label className="field-l">Payment terms (days)<input type="text" value={f.payment_terms_days || ''} onChange={set('payment_terms_days')} /></label>
              <label className="field-l">Status<select value={f.status} onChange={set('status')}><option value="pending">Pending onboarding</option><option value="approved">Approved</option></select></label></div>
          </>
        )}
        <p className="small muted">Every save writes an audit event with the values before and after.</p>
      </div>
      <div className="sheet-f"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save {kind === 'po' ? 'PO' : 'vendor'}</button></div>
    </Modal>
  );
}

function ImportModal({ kind, open, onClose, onDone }) {
  const { toast } = useApp();
  const [file, setFile] = useState(null); const [res, setRes] = useState(null); const [err, setErr] = useState(null); const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setFile(null); setRes(null); setErr(null); } }, [open]);
  async function check(f, commit) {
    setBusy(true); setErr(null);
    const fd = new FormData(); fd.append('file', f);
    try { const r = await api(`/api/import/${kind === 'po' ? 'pos' : 'vendors'}?commit=${commit}`, { method: 'POST', form: fd }); setRes(r); if (commit) { toast(`Imported ${r.rows} rows.`); onClose(); onDone(); } }
    catch (e) { setErr(e); if (e.fields || e.status === 422) setRes((x) => x); } finally { setBusy(false); }
  }
  const problems = res ? res.problems || [] : [];
  return (
    <Modal open={open} onClose={onClose} label="Import wizard">
      <div className="sheet-h"><div><div className="upper">Import wizard</div><h3>Import {kind === 'po' ? 'purchase orders' : 'vendors'} from CSV</h3></div><button className="icon-btn right" onClick={onClose} aria-label="Close"><Ic n="x" /></button></div>
      <div className="sheet-b">
        <div className="row gap-s small"><span className="pill accent">1 Upload</span><Ic n="chev-r" c="sm" /><span className={`pill ${res ? 'accent' : ''}`}>2 Check rows</span><Ic n="chev-r" c="sm" /><span className={`pill ${res && !problems.length ? 'accent' : ''}`}>3 Import</span></div>
        <label className="drop" style={{ padding: 20 }} htmlFor="imp-file"><Ic n="upload" c="lg" /><b>{file ? file.name : 'Choose a CSV file'}</b><span className="small sec">{kind === 'po' ? 'One row per PO line: po_number, vendor_id, issue_date, valid_to, currency, item_code, description, uom, ordered_qty, unit_price, tax_rate_pct' : 'id, name, gstin, status, payment_terms_days, bank_name, bank_account_no, bank_ifsc, contact_phone, contact_email, aliases, address'}</span>
          <input id="imp-file" type="file" accept=".csv,text/csv" hidden onChange={(e) => { const f = e.target.files[0]; if (f) { setFile(f); check(f, false); } }} /></label>
        {err ? <div className="banner bad" role="alert"><Ic n="warn" /><span>{err.message}</span></div> : null}
        {res ? (
          <>
            <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Row</th><th>Check</th></tr></thead><tbody>
              {problems.map((p) => <tr key={p.row}><td className="mono">{p.row}</td><td style={{ color: 'var(--reject-fg)' }}><Ic n="x-circle" c="sm" /> {Object.entries(p.errors).map(([k, v]) => `${k}: ${v}`).join(' · ')}</td></tr>)}
              {!problems.length ? <tr><td colSpan={2}><span className="chip s-auto"><Ic n="check-circle" />All {res.rows} rows are valid</span></td></tr> : null}
            </tbody></table></div>
            {problems.length ? <div className="banner"><Ic n="warn" c="lg" /><span><b>{problems.length} rows have problems.</b> Nothing is imported until every row is valid. Fix the file and upload it again.</span></div> : null}
          </>
        ) : null}
      </div>
      <div className="sheet-f"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!res || problems.length > 0 || busy} onClick={() => check(file, true)}>Import {res ? res.rows : ''} rows</button></div>
    </Modal>
  );
}

/* ---------- page ---------- */
function MasterInner() {
  const params = useSearchParams();
  const { tick, toast, roleTick } = useApp();
  const [tab, setTab] = useState('po');
  const [status, setStatus] = useState('all'); const [vendor, setVendor] = useState('all'); const [q, setQ] = useState(''); const [dq, setDq] = useState('');
  const [poOpen, setPoOpen] = useState(null); const [vOpen, setVOpen] = useState(null);
  const [add, setAdd] = useState(false); const [imp, setImp] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDq(q), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { const p = params.get('po'); if (p) { setTab('po'); setPoOpen(p); } }, [params]);
  const pos = useApi('/api/pos' + qs({ status, vendor_id: vendor, q: dq }), { tick, deps: [roleTick] });
  const vendors = useApi('/api/vendors' + qs({ q: dq }), { tick });
  const allV = useApi('/api/vendors');
  const reloadAll = () => { pos.refresh(); vendors.refresh(); };
  async function exportKind() {
    const kind = tab === 'po' ? 'pos' : 'vendors';
    try { const t = await (await fetch(url(`/api/export/${kind}.csv`))).text(); downloadText(`${kind}.csv`, t, 'text/csv'); toast('Export ready. The export was recorded in the audit log.'); } catch { toast("Couldn't export. The server is not reachable."); }
  }
  const poItems = pos.data ? pos.data.items : []; const vItems = vendors.data ? vendors.data.items : [];
  return (
    <>
      <PageHead title="Purchase orders and vendors" sub="The procurement data every rule depends on. Editing it changes the next run.">
        <button className="btn" onClick={() => setImp(true)} data-testid="import-btn"><Ic n="upload" c="sm" />Import CSV</button>
        <button className="btn" onClick={exportKind}><Ic n="download" c="sm" />Export</button>
        <button className="btn primary" onClick={() => setAdd(true)} data-testid="add-btn"><Ic n="plus" c="sm" />{tab === 'po' ? 'Add PO' : 'Add vendor'}</button>
      </PageHead>
      <ErrorBanner error={pos.error || vendors.error} onRetry={reloadAll} />
      <div className="card" data-testid="master-card">
        <div className="tabs" style={{ padding: '0 12px' }}>
          <button className={tab === 'po' ? 'on' : ''} onClick={() => { setTab('po'); setQ(''); }} data-testid="tab-po">Purchase orders<span className="ct">{pos.data ? poItems.length : '–'}</span></button>
          <button className={tab === 'v' ? 'on' : ''} onClick={() => { setTab('v'); setQ(''); }} data-testid="tab-vendors">Vendors<span className="ct">{allV.data ? allV.data.items.length : '–'}</span></button>
        </div>
        <div className="row wrap" style={{ padding: '12px 16px' }}>
          {tab === 'po' ? (
            <>
              <label className="row gap-s small sec">Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">All</option>{Object.entries(PO_CHIP).map(([k, [, l]]) => <option key={k} value={k}>{l}</option>)}</select></label>
              <label className="row gap-s small sec">Vendor<select value={vendor} onChange={(e) => setVendor(e.target.value)}><option value="all">All</option>{(allV.data ? allV.data.items : []).map((v) => <option key={v.id} value={v.id}>{v.short}</option>)}</select></label>
            </>
          ) : null}
          <div className="search right" style={{ width: 260 }}><Ic n="search" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={tab === 'po' ? 'Search PO or vendor' : 'Search vendor, ID or GSTIN'} aria-label="Search" /></div>
        </div>
        <div className="tbl-wrap">
          {tab === 'po' ? (
            <table className="tbl" data-testid="po-list"><thead><tr><th>PO number</th><th>Vendor</th><th>Issued</th><th>Valid to</th><th>Status</th><th className="r">Pre-tax value</th><th>Billed to date</th><th className="r">Remaining</th><th className="r">Invoices</th></tr></thead><tbody>
              {pos.loading && !pos.data ? Array.from({ length: 5 }).map((_, i) => <tr key={i}><td colSpan={9}><Shimmer h={26} /></td></tr>) : null}
              {poItems.map((p) => { const pc = Math.round(p.pct_billed); return (
                <tr className="link" key={p.id} onClick={() => setPoOpen(p.id)} data-testid="po-row"><td className="mono"><b>{p.id}</b></td><td>{p.vendor_short}</td><td className="nowrap">{fmtDay(p.issue_date)}</td><td className="nowrap">{fmtDay(p.valid_to)}</td><td><POChip s={p.status} /></td><td className="r num">{inrP(p.subtotal_paise)}</td>
                  <td style={{ minWidth: 150 }}><div className="row gap-s"><div className="bar grow"><i style={{ width: `${Math.min(pc, 100)}%`, background: pc >= 100 ? 'var(--ok)' : 'var(--accent)' }} /></div><span className="num small">{pc}%</span></div><div className="tiny muted num">{inrP(p.billed_subtotal_paise)}{p.pending_subtotal_paise ? ` · +${inrP(p.pending_subtotal_paise)} pending` : ''}</div></td>
                  <td className="r num">{inrP(p.remaining_subtotal_paise)}</td><td className="r num">{p.invoice_count}</td></tr>); })}
              {!pos.loading && !poItems.length ? <tr><td colSpan={9}><Empty title="No purchase orders match"><p>Change the filters or import a CSV.</p></Empty></td></tr> : null}
            </tbody></table>
          ) : (
            <table className="tbl" data-testid="vendor-list"><thead><tr><th>ID</th><th>Vendor</th><th>GSTIN</th><th>Status</th><th>Payment terms</th><th>Bank account</th><th>Last bank change</th></tr></thead><tbody>
              {vItems.map((v) => { const s = V_CHIP[v.status]; return (
                <tr className="link" key={v.id} onClick={() => setVOpen(v.id)} data-testid="vendor-row"><td className="mono"><b>{v.id}</b></td><td>{v.name}</td><td className="mono small">{v.gstin}</td><td><span className={`chip ${s[0]}`}><Ic n={s[2]} />{s[1]}</span></td><td>Net {v.payment_terms_days}</td><td className="mono small">{v.bank_account_masked ? '•••• ' + String(v.bank_account_masked).replace(/\D/g, '').slice(-4) : <span className="muted">none</span>}</td><td className="muted small nowrap">{v.bank_changed_at ? fmtDay(v.bank_changed_at) : 'n/a'}</td></tr>); })}
              {!vendors.loading && !vItems.length ? <tr><td colSpan={7}><Empty title="No vendors match"><p>Change the search or add a vendor.</p></Empty></td></tr> : null}
            </tbody></table>
          )}
        </div>
        <div className="pager"><span>{tab === 'po' ? `${poItems.length} purchase orders. Billed to date counts approved invoices; pending ones are shown separately.` : `${vItems.length} vendors. Bank account numbers are masked.`}</span></div>
      </div>
      <PoDrawer id={poOpen} onClose={() => setPoOpen(null)} onChanged={reloadAll} />
      <VendorDrawer id={vOpen} onClose={() => setVOpen(null)} onChanged={reloadAll} />
      <AddModal kind={tab} open={add} onClose={() => setAdd(false)} vendors={allV.data ? allV.data.items : []} onDone={reloadAll} />
      <ImportModal kind={tab} open={imp} onClose={() => setImp(false)} onDone={reloadAll} />
    </>
  );
}

export default function Master() { return <Suspense fallback={null}><MasterInner /></Suspense>; }
