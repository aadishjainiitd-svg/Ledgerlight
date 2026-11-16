'use client';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Fragment, useEffect, useState } from 'react';
import { API, qs } from '@/lib/api';
import { addDays, downloadText, fmtDT, initials } from '@/lib/format';
import { Chip, Empty, ErrorBanner, Ic, OUT_COLOR, PageHead, Shimmer, outKey, useApi, useApp } from '@/lib/ui';

const AS_OF = '2026-11-16';
const EVT = { run_created: 'Run created', stage_completed: 'Stage completed', rule_evaluated: 'Rule evaluated', decision_made: 'Decision made', decision_overridden: 'Override', decision_confirmed: 'Decision confirmed', field_corrected: 'Field corrected', master_data_changed: 'Master data changed', settings_changed: 'Settings changed', export: 'Export', info_requested: 'Info requested', document_received: 'Document received', payment_recorded: 'Payment recorded', run_failed: 'Run failed', run_cancelled: 'Run cancelled', demo_reset: 'Demo reset' };
const ACTORS = { system: 'System', ai: 'AI model', human: 'Human' };
const isDecision = (o) => ['auto_approve', 'approve_with_note', 'route_for_review', 'hold_request_info', 'reject'].includes(o);

function Actor({ e }) {
  const t = e.actor_type;
  return (
    <span className="actor"><span className={`av ${t === 'system' ? 'sys' : t === 'ai' ? 'ai' : 'hum'}`}>{t === 'system' ? <Ic n="gear" c="sm" /> : t === 'ai' ? <Ic n="cpu" c="sm" /> : initials(e.actor_id)}</span>
      <span><div style={{ fontWeight: 600, fontSize: 13 }}>{e.actor_id}</div><div className="tiny muted">{ACTORS[t] || t}</div></span></span>
  );
}
const fmtVal = (v) => (v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
function Payload({ e }) {
  const p = e.payload || {}; const [json, setJson] = useState(false);
  const hasDiff = p.before !== undefined && p.after !== undefined;
  const rest = Object.entries(p).filter(([k]) => !['before', 'after'].includes(k));
  return (
    <>
      {hasDiff ? <div className="diffbox"><div className="bf"><div className="upper">Before</div>{fmtVal(p.before)}</div><div className="af"><div className="upper">After</div>{fmtVal(p.after)}</div></div> : null}
      {rest.length ? <dl className="kv" style={{ marginTop: hasDiff ? 12 : 0 }}>{rest.map(([k, v]) => <Fragment key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd>{fmtVal(v)}</dd></Fragment>)}</dl> : null}
      {!hasDiff && !rest.length ? <span className="muted">No extra details.</span> : null}
      <div style={{ marginTop: 10 }}><a href="#json" className="small" onClick={(ev) => { ev.preventDefault(); setJson((j) => !j); }}>{json ? 'Hide JSON' : 'View JSON'}</a>
        {json ? <pre className="json" style={{ marginTop: 8, borderRadius: 8, padding: '10px 12px' }}>{JSON.stringify(e, null, 2)}</pre> : null}</div>
    </>
  );
}

function ObjLink({ e }) {
  const kind = e.object_type; const id = e.object_id;
  const label = <><span className="muted small">{kind}</span> <b className="mono">{id}</b></>;
  if (kind === 'invoice' || kind === 'run') return <Link href={`/audit?invoice=${e.invoice_id || id}`} onClick={(ev) => ev.stopPropagation()}>{label}</Link>;
  if (kind === 'po' || kind === 'purchase_order') return <Link href={`/master?po=${id}`}>{label}</Link>;
  if (kind === 'vendor') return <Link href="/master">{label}</Link>;
  if (kind === 'setting' || kind === 'settings') return <Link href="/rules">{label}</Link>;
  return <span>{label}</span>;
}

export default function Audit() {
  const params = useSearchParams(); const router = useRouter();
  const { tick, toast } = useApp();
  const invoice = params.get('invoice');
  const [f, setF] = useState({ actor_type: 'all', user: 'all', event_type: 'all', range: 90 });
  const [q, setQ] = useState(''); const [dq, setDq] = useState('');
  const [size, setSize] = useState(40);
  const [open, setOpen] = useState(new Set());
  useEffect(() => { const t = setTimeout(() => setDq(q), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { setSize(40); }, [f, dq, invoice]);
  const filt = { from: addDays(AS_OF, -f.range - 1), actor_type: f.actor_type, user: f.user, event_type: f.event_type, invoice_id: invoice, q: dq };
  const { data, error, loading, reload } = useApi('/api/audit' + qs({ ...filt, page_size: size }), { tick });
  const trace = useApi(invoice ? `/api/invoices/${invoice}/audit` : null, { enabled: !!invoice, deps: [invoice], tick });
  const items = data ? data.items : [];
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const tog = (id) => setOpen((o) => { const n = new Set(o); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const invRun = trace.data && (trace.data.items || trace.data.events || [])[0];

  async function exportAs(fmt) {
    try {
      const t = await (await fetch(`${API}/api/audit/export${qs({ ...filt, format: fmt })}`)).text();
      downloadText(`audit-log.${fmt}`, t, fmt === 'csv' ? 'text/csv' : 'application/json');
      toast(`Audit log exported as ${fmt.toUpperCase()}. The export itself is recorded below.`); setTimeout(reload, 400);
    } catch { toast("Couldn't export. The server is not reachable."); }
  }
  const traceItems = trace.data ? (trace.data.items || trace.data.events || trace.data.timeline || (Array.isArray(trace.data) ? trace.data : [])) : [];

  return (
    <>
      <PageHead title="Audit log" sub="Everything the system did and every decision a person made, with the reason.">
        <button className="btn" onClick={() => exportAs('csv')} data-testid="export-csv"><Ic n="download" c="sm" />Export CSV</button>
        <button className="btn" onClick={() => exportAs('json')}><Ic n="download" c="sm" />Export JSON</button>
      </PageHead>
      <div className="stack">
        <ErrorBanner error={error} onRetry={reload} />
        <div className="banner info"><Ic n="lock" c="lg" /><span><b>Entries cannot be edited or deleted.</b> This log is append-only. Corrections are recorded as new entries.</span></div>
        {invoice ? (
          <div className="card panel" data-testid="trace"><h3><Ic n="link" c="sm" />Trace for <span className="mono">{invoice}</span><span className="muted small" style={{ fontWeight: 500 }}>from upload to payment queue</span><button className="btn sm right" onClick={() => router.push('/audit')}>Clear invoice filter</button></h3>
            {trace.loading && !trace.data ? <Shimmer h={80} /> : traceItems.length ? <div className="tl">{traceItems.slice().sort((a, b) => (a.ts > b.ts ? 1 : -1)).map((e) => <div className="ev" key={e.id} style={{ '--evc': isDecision(e.outcome) ? OUT_COLOR[outKey(e.outcome)] : 'var(--line-2)' }}><div className="small muted">{fmtDT(e.ts)} · {e.actor_id} · {EVT[e.event_type] || e.event_type}</div><div>{e.summary}</div></div>)}</div> : <div className="muted">No events for this invoice.</div>}
          </div>
        ) : null}
        <div className="card">
          <div className="row wrap" style={{ padding: '14px 16px' }}>
            <div className="search grow" style={{ minWidth: 220 }}><Ic n="search" /><input type="search" id="a-q" placeholder="Search invoice, PO, vendor, person or text" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the audit log" data-testid="audit-search" /></div>
            <label className="row gap-s small sec">Dates<select id="a-r" value={f.range} onChange={(e) => set('range', +e.target.value)}>{[7, 30, 90].map((n) => <option key={n} value={n}>Last {n} days</option>)}</select></label>
            <label className="row gap-s small sec">Actor<select id="a-a" value={f.actor_type} onChange={(e) => set('actor_type', e.target.value)}><option value="all">Anyone</option>{Object.entries(ACTORS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label className="row gap-s small sec">Person<select id="a-u" value={f.user} onChange={(e) => set('user', e.target.value)}><option value="all">Anyone</option>{(data ? data.users : []).map((u) => <option key={u}>{u}</option>)}</select></label>
            <label className="row gap-s small sec">Event<select id="a-t" value={f.event_type} onChange={(e) => set('event_type', e.target.value)} data-testid="audit-event"><option value="all">All events</option>{(data ? data.event_types : Object.keys(EVT)).map((t) => <option key={t} value={t}>{EVT[t] || t}</option>)}</select></label>
          </div>
          <div className="tbl-wrap"><table className="tbl" data-testid="audit-table"><thead><tr><th>Time</th><th>Actor</th><th>Event</th><th>Object</th><th>Outcome</th><th /></tr></thead><tbody>
            {loading && !data ? Array.from({ length: 6 }).map((_, i) => <tr key={i}><td colSpan={6}><Shimmer h={30} /></td></tr>) : null}
            {items.map((e) => {
              const isOpen = open.has(e.id);
              return (
                <Fragment key={e.id}>
                  <tr className="link audit-row" onClick={() => tog(e.id)} data-testid="audit-row" data-event={e.event_type}>
                    <td className="nowrap"><div style={{ fontWeight: 600 }}>{fmtDT(e.ts)}</div><div className="tiny muted">{String(e.ts).slice(0, 4)}</div></td>
                    <td><Actor e={e} /></td>
                    <td style={{ minWidth: 260 }}><span className="tag">{EVT[e.event_type] || e.event_type}</span><div style={{ marginTop: 4 }}>{e.summary}</div></td>
                    <td className="nowrap"><ObjLink e={e} /></td>
                    <td>{isDecision(e.outcome) ? <Chip k={e.outcome} /> : null}</td>
                    <td className="c"><Ic n={isOpen ? 'chev-u' : 'chev-d'} c="sm" /></td>
                  </tr>
                  {isOpen ? <tr className="payload" style={{ display: 'table-row' }}><td colSpan={6}><Payload e={e} /></td></tr> : null}
                </Fragment>
              );
            })}
            {!loading && !items.length ? <tr><td colSpan={6}><Empty title="No events match"><p>Clear the filters to see everything.</p><p style={{ marginTop: 10 }}><button className="btn" onClick={() => { setF({ actor_type: 'all', user: 'all', event_type: 'all', range: 90 }); setQ(''); router.push('/audit'); }}>Clear filters</button></p></Empty></td></tr> : null}
          </tbody></table></div>
          <div className="pager"><span data-testid="audit-count">Showing {items.length} of {data ? data.total : 0} events, newest first</span>{data && items.length < data.total ? <button className="btn sm right" onClick={() => setSize((s) => s + 60)}>Show more</button> : null}</div>
        </div>
      </div>
    </>
  );
}
