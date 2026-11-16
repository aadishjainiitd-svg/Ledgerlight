'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { API, api } from '@/lib/api';
import { fmtTS, inrP, secs } from '@/lib/format';
import { Chip, ConfChip, ErrorBanner, Ic, Modal, SevIcon, Shimmer, copyText, outKey, useApp } from '@/lib/ui';

const STAGES = [
  [1, 'Ingest', 'Store the file, hash it, detect text or scan'],
  [2, 'Extract', 'Read fields and line items with confidence'],
  [3, 'Normalise and field checks', 'Dates, money, tax, required fields'],
  [4, 'Vendor check', 'Approved vendor? Do the bank details match?'],
  [5, 'Duplicate check', 'Is this an invoice we have seen before?'],
  [6, 'PO match', 'Find the PO and align every line'],
  [7, 'Validation rules', 'Price, quantity, cumulative value, tax, total'],
  [8, 'Decision', 'Worst severity across all rules wins'],
  [9, 'Explain and output', 'Plain-English reasons and drafts'],
];
const HEADER_FIELDS = [['vendor_name', 'Vendor'], ['invoice_no', 'Invoice no.'], ['invoice_date', 'Invoice date'], ['po_reference', 'PO reference'], ['currency', 'Currency'], ['subtotal', 'Subtotal'], ['tax_total', 'Tax (GST)'], ['total', 'Total']];
const BANK_FIELDS = ['bank_name', 'bank_account', 'bank_ifsc'];
const SEV_NODE = { pass: 'check', note: 'check', review: 'warn', hold: 'pause', reject: 'x' };

function freshState() {
  const stages = {}; STAGES.forEach(([n]) => { stages[n] = { status: 'pending', rules: [] }; });
  return { meta: null, stages, order: [], raw: {}, conf: {}, lines: [], log: [], decision: null, completed: null, failed: null, cancelled: null, count: 0, lastId: 0 };
}

function reducer(s, a) {
  if (a.type === 'reset') return freshState();
  if (a.type !== 'ev') return s;
  const { id, name, d } = a;
  if (id && id <= s.lastId) return s; // replay / reconnect overlap
  const n = { ...s, lastId: id || s.lastId, count: s.count + 1 };
  const st = (no, patch) => { n.stages = { ...n.stages, [no]: { ...n.stages[no], ...patch } }; };
  switch (name) {
    case 'run_started': n.meta = d; break;
    case 'stage_started': st(d.stage_no, { status: 'running' }); break;
    case 'field_extracted':
      n.raw = { ...n.raw, [d.field]: d }; if (!n.order.includes(d.field)) n.order = [...n.order, d.field]; break;
    case 'line_extracted': n.lines = [...n.lines.filter((l) => l.line_no !== d.line_no), d]; break;
    case 'field_confidence': n.conf = { ...n.conf, [d.field]: d }; if (!n.order.includes(d.field)) n.order = [...n.order, d.field]; break;
    case 'log': n.log = [...n.log, { id, ts: d._ts, stage: d.stage_no, level: d.level, text: d.text, pace: d.display_pacing }]; break;
    case 'rule_result': {
      const cur = n.stages[d.stage_no]; const rules = [...cur.rules.filter((r) => r.rule_id !== d.rule_id), d];
      st(d.stage_no, { rules }); break;
    }
    case 'stage_completed':
      st(d.stage_no, { status: d.status === 'done' && /^skipped/i.test(d.message || '') ? 'skipped' : d.status, sev: d.severity_max, dur: d.duration_ms, msg: d.message, input: d.input, output: d.output }); break;
    case 'decision': n.decision = d; break;
    case 'run_completed': n.completed = d; break;
    case 'run_failed': n.failed = d; { const sn = d.stage_no; if (sn && n.stages[sn]) st(sn, { status: 'failed', msg: d.error }); } break;
    case 'run_cancelled': n.cancelled = d; break;
    default: return s;
  }
  return n;
}

/* ---------- readable input/output tables ---------- */
const human = (k) => { const t = k.replace(/_/g, ' '); return t[0].toUpperCase() + t.slice(1); };
function flat(o) {
  const rows = [];
  Object.entries(o || {}).forEach(([k, v]) => {
    if (v == null || v === '') return;
    if (Array.isArray(v)) { if (!v.length) return; rows.push([human(k), v.every((x) => typeof x !== 'object') ? v.join(', ') : `${v.length} item${v.length > 1 ? 's' : ''}`]); }
    else if (typeof v === 'object') { const inner = Object.entries(v).filter(([, x]) => x != null && typeof x !== 'object').map(([a, b]) => `${human(a).toLowerCase()} ${b}`).join(', '); if (inner) rows.push([human(k), inner]); }
    else if (typeof v === 'boolean') rows.push([human(k), v ? 'Yes' : 'No']);
    else if (/paise$/.test(k)) rows.push([human(k.replace(/_paise$/, '')), inrP(v, 2)]);
    else rows.push([human(k), String(v).length > 70 ? String(v).slice(0, 12) + '…' + String(v).slice(-6) : String(v)]);
  });
  return rows;
}
const KV = ({ rows }) => (rows.length ? <table><tbody>{rows.map(([a, b], i) => <tr key={i}><td>{a}</td><td>{b}</td></tr>)}</tbody></table> : <div className="muted" style={{ marginBottom: 8 }}>Nothing recorded.</div>);

function StageCard({ def, s, open, toggle }) {
  const [n, name, desc] = def;
  const status = s.status; const done = status === 'done';
  const cls = ['stage', status === 'done' ? 'done' : status, done && s.sev ? `sev-${s.sev}` : '', open ? 'open' : ''].join(' ');
  const node = status === 'running' ? <Ic n="spinner" c="spin" /> : done ? <Ic n={SEV_NODE[s.sev] || 'check'} /> : status === 'skipped' ? <Ic n="minus" c="sm" /> : status === 'failed' ? <Ic n="warn" c="sm" /> : n;
  return (
    <div className={cls} data-testid={`stage-${n}`} data-status={status} onClick={toggle} role="button" tabIndex={0} aria-expanded={open}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } }}>
      <div className="node">{node}</div><i className="fill" />
      <div className="body">
        <div className="t"><span>{name}</span><span className="dur">{s.dur != null ? secs(s.dur) : ''}</span></div>
        <div className="d">{desc}</div>
        {s.msg ? <div className="res">{status === 'skipped' && !/^skipped/i.test(s.msg) ? <b>Skipped. </b> : null}{s.msg}</div> : null}
        <div className="io">
          <h5>Input</h5><KV rows={flat(s.input)} />
          <h5>Output</h5><KV rows={flat(s.output)} />
          {s.rules.length ? <><h5>Rules at this stage</h5>{s.rules.map((r) => <div className="rl" key={r.rule_id}><SevIcon s={r.skipped ? 'pass' : r.severity} /><span>{r.rule_name}<span className="rid">{r.rule_id}</span>{r.skipped ? <span className="muted"> not checked</span> : null}</span></div>)}</> : null}
        </div>
      </div>
    </div>
  );
}

function FieldCard({ label, raw, conf }) {
  if (!raw && !conf) return <div className="fcard empty"><div className="l">{label}</div><div className="v shimmer" /></div>;
  const norm = !!conf; const c = norm ? conf.effective_confidence : raw.confidence;
  const shown = norm ? conf.display : (raw.raw_text || raw.value);
  const low = norm && (c < 0.9 || conf.ambiguous);
  const why = norm && conf.why;
  return (
    <div className={`fcard pop-in ${low ? 'amber' : ''}`} data-testid={`field-${(raw || conf).field}`} data-tip={why || undefined}>
      <div className="l"><span>{(conf || raw).label || label}</span><span className="row gap-s">{norm && conf.boosted ? <span className="boost">raised</span> : null}<ConfChip c={c} /></span></div>
      <div className="v">{shown === '' || shown == null ? <span className="muted">Not found</span> : shown}</div>
      {why && (low || conf.boosted) ? <div className="why">{why}</div> : null}
    </div>
  );
}

export default function LiveRun({ runId }) {
  const router = useRouter();
  const { toast, role, rememberRun, settings } = useApp();
  const app = useApp();
  const [st, dispatch] = useReducer(reducer, null, freshState);
  const [info, setInfo] = useState(null); // GET /api/runs/{id} header
  const [mode, setMode] = useState(null); // 'live' | 'replay'
  const [speed, setSpeed] = useState(1);
  const [conn, setConn] = useState('connecting');
  const [notFound, setNotFound] = useState(null);
  const [open, setOpen] = useState(() => new Set());
  const [lf, setLf] = useState('all');
  const [paused, setPaused] = useState(false);
  const [zoom, setZoom] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [batch, setBatch] = useState([]);
  const [replayKey, setReplayKey] = useState(0);
  const logRef = useRef(null);
  const doneRef = useRef(false);
  const t0 = useRef(null);

  useEffect(() => { rememberRun(`/runs/${runId}`); try { setBatch(JSON.parse(sessionStorage.getItem('ll-batch') || '[]')); } catch { /* ignore */ } /* eslint-disable-next-line */ }, [runId]);

  /* header info and live-vs-replay decision */
  useEffect(() => {
    let dead = false; setInfo(null); setNotFound(null); setMode(null);
    api(`/api/runs/${runId}`).then((d) => {
      if (dead) return; setInfo(d);
      setMode(d.run.status === 'running' ? 'live' : 'replay');
    }).catch((e) => { if (!dead) setNotFound(e); });
    return () => { dead = true; };
  }, [runId]);

  /* the SSE stream */
  useEffect(() => {
    if (!mode) return undefined;
    dispatch({ type: 'reset' }); doneRef.current = false; t0.current = performance.now();
    let es; let timer; let lastId = 0; let closed = false;
    const TYPES = ['run_started', 'stage_started', 'field_extracted', 'line_extracted', 'field_confidence', 'log', 'rule_result', 'stage_completed', 'decision', 'run_completed', 'run_failed', 'run_cancelled'];
    const connect = () => {
      if (closed) return;
      const p = new URLSearchParams();
      if (mode === 'replay') { p.set('replay', 'true'); p.set('speed', String(speed)); }
      if (lastId) p.set('last_event_id', String(lastId));
      es = new EventSource(`${API}/api/runs/${runId}/events${p.toString() ? '?' + p : ''}`);
      es.onopen = () => setConn(mode === 'replay' ? 'replay' : 'live');
      es.onerror = () => {
        if (doneRef.current || closed) return;
        es.close(); setConn('reconnecting'); timer = setTimeout(connect, 1500); // resume with last_event_id; nothing is lost
      };
      TYPES.forEach((t) => es.addEventListener(t, (e) => {
        let d = {}; try { d = JSON.parse(e.data); } catch { return; }
        const id = Number(e.lastEventId) || 0; if (id) lastId = Math.max(lastId, id);
        dispatch({ type: 'ev', id, name: t, d });
        if (t === 'run_completed' || t === 'run_failed' || t === 'run_cancelled') { doneRef.current = true; es.close(); setConn('done'); app.refreshQueue && app.refreshQueue(); }
      }));
    };
    connect();
    return () => { closed = true; clearTimeout(timer); es && es.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, runId, speed, replayKey]);

  /* elapsed timer */
  const finished = !!(st.completed || st.failed || st.cancelled);
  useEffect(() => { if (finished) return undefined; const t = setInterval(() => setNow(Date.now()), 100); return () => clearInterval(t); }, [finished]);
  const elapsed = st.completed ? st.completed.duration_ms / 1000
    : finished ? (st.meta && st.log.length ? Math.max(0, (Date.parse(st.log[st.log.length - 1].ts) - Date.parse(st.meta._ts || st.log[0].ts)) / 1000) : 0)
      : mode === 'replay' ? ((performance.now() - (t0.current || performance.now())) / 1000) * speed
        : st.meta ? Math.max(0, (now - Date.parse(st.meta._ts || new Date().toISOString())) / 1000) : 0;

  /* log autoscroll */
  const visLog = useMemo(() => (lf === 'all' ? st.log : st.log.filter((l) => l.level === lf)), [st.log, lf]);
  useEffect(() => { if (!paused && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [visLog.length, paused]);

  const toggle = (n) => setOpen((o) => { const x = new Set(o); x.has(n) ? x.delete(n) : x.add(n); return x; });

  const invoiceId = (st.meta && st.meta.invoice_id) || (info && info.invoice.id);
  const fileName = (st.meta && st.meta.file_name) || (info && info.invoice.file_name) || 'Starting…';
  const doc = st.stages[1].output && st.stages[1].output.doc_type;
  const scanned = doc === 'scanned' || (info && info.invoice.doc_type === 'scanned');
  const needsAi = st.stages[2].status === 'skipped' && st.stages[2].output && st.stages[2].output.reason === 'scanned_no_key';
  const vend = st.conf.vendor_name ? st.conf.vendor_name.display : st.raw.vendor_name ? st.raw.vendor_name.value : null;
  const invno = st.conf.invoice_no ? st.conf.invoice_no.display : st.raw.invoice_no ? st.raw.invoice_no.value : null;
  const dk = st.decision ? outKey(st.decision.outcome) : null;
  const doneCount = Object.values(st.stages).filter((s) => ['done', 'skipped', 'failed'].includes(s.status)).length;
  const stateAttr = st.cancelled ? 'cancelled' : st.failed ? 'failed' : st.completed ? 'completed' : st.meta ? 'running' : 'connecting';

  useEffect(() => { app.setCrumb && app.setCrumb(<><span className="muted">Live run</span><Ic n="chev-r" c="sm" />{fileName}</>); /* eslint-disable-next-line */ }, [fileName]);

  async function cancel() { try { await api(`/api/runs/${runId}/cancel`, { method: 'POST' }); toast('Cancelling. The run stops at the next stage boundary.'); } catch (e) { toast(e.message); } }
  async function retry() { try { const r = await api(`/api/runs/${runId}/retry`, { method: 'POST' }); router.push(`/runs/${r.run_id}`); } catch (e) { toast(e.message); } }
  async function runAgain() {
    try { const r = await api(`/api/invoices/${invoiceId}/rerun`, { method: 'POST', body: { reason: 'Run again from the live view', pace: settings.speed, use_cache: settings.cache } }); router.push(`/runs/${r.run_id}`); } catch (e) { toast(e.message); }
  }
  const replay = (sp) => { if (sp) setSpeed(sp); setMode('replay'); setReplayKey((k) => k + 1); };

  if (notFound) return (
    <div className="card" style={{ maxWidth: 560 }}><div className="empty"><h4>{notFound.status === 404 ? 'We could not find that run' : "We couldn't load this run"}</h4><p>{notFound.message}</p><p style={{ marginTop: 12 }}><Link className="btn" href="/new">Start a new run</Link></p></div></div>
  );

  const connChip = conn === 'reconnecting' ? <div className="chip s-review" data-testid="conn-chip" data-state="reconnecting"><span className="live-dot off" style={{ width: 7, height: 7 }} />Reconnecting</div>
    : st.cancelled ? <div className="chip s-none" data-testid="conn-chip" data-state="cancelled">Cancelled</div>
      : st.failed ? <div className="chip s-error" data-testid="conn-chip" data-state="failed">Failed</div>
        : st.completed ? <div className="chip s-none" data-testid="conn-chip" data-state="completed">Completed</div>
          : mode === 'replay' ? <div className="chip s-running" data-testid="conn-chip" data-state="replay">Replay</div>
            : <div className="chip s-auto" data-testid="conn-chip" data-state="live"><span className="live-dot" style={{ width: 7, height: 7 }} />Live</div>;

  return (
    <div data-testid="live-run" data-run-state={stateAttr} data-done-stages={doneCount}>
      {batch.length > 1 && batch.some((b) => b.id === runId) ? (
        <div className="banner info" style={{ marginBottom: 12 }}><Ic n="queue" /><span className="grow"><b>{batch.length} runs in progress.</b> Open another:</span>
          {batch.filter((b) => b.id !== runId).map((b) => <Link key={b.id} href={`/runs/${b.id}`} className="pill accent">{b.name}</Link>)}</div>
      ) : null}
      {mode === 'replay' && !finished ? <div className="banner info" style={{ marginBottom: 12 }} data-testid="replay-banner"><Ic n="play" /><span className="grow"><b>Replay.</b> This run already finished, so the stored events are replaying at {speed}x.</span></div> : null}
      <div className="card run-head" id="run-head">
        <div className="grow" style={{ minWidth: 230 }}>
          <div className="upper">Live run</div>
          <div className="big" data-testid="run-title">{fileName}</div>
          <div className="small muted"><span className="mono">{runId}</span> · <span data-testid="vendor-invoice">{vend || invno ? `${vend || 'Vendor'}${invno ? ` · invoice ${invno}` : ''}` : finished ? 'Vendor and invoice number: not read from this file' : 'Vendor and invoice number: Reading…'}</span></div>
        </div>
        <div><div className="upper">Elapsed</div><div className="timer" data-testid="timer">{elapsed.toFixed(1)} s</div></div>
        {connChip}
        <div className="row wrap">
          {st.meta ? <span className="pill" data-tip="Display pacing for the demo. Fast stages are held for a minimum time so you can watch them. The real work time is in each stage's detail and the log.">Pacing {st.meta.pace_ms ? `${st.meta.pace_ms} ms per stage` : 'off'}</span> : null}
          {(mode === 'replay') ? <div className="seg" role="group" aria-label="Replay speed">{[0.5, 1, 2, 4].map((s) => <button key={s} aria-pressed={speed === s} onClick={() => replay(s)}>{s}x</button>)}</div> : null}
          {!finished && mode === 'live' ? <button className="btn" data-testid="cancel-run" onClick={cancel}><Ic n="cancel" />Cancel run</button> : null}
          {finished ? <button className="btn" data-testid="replay-btn" onClick={() => replay(1)}><Ic n="play" />Replay</button> : null}
          {finished && invoiceId ? <button className="btn" onClick={runAgain}><Ic n="refresh" />Run again</button> : null}
          {st.failed && st.failed.retryable !== false ? <button className="btn primary" onClick={retry}><Ic n="refresh" />Retry</button> : null}
          {st.completed ? <Link className="btn primary" id="btn-open" data-testid="open-decision" href={`/decision/${runId}`}>Open full decision <Ic n="arrow-r" /></Link> : null}
        </div>
      </div>
      {conn === 'reconnecting' ? <div className="banner" style={{ marginBottom: 12 }} role="status"><Ic n="warn" /><span>Live updates paused, reconnecting. Missed events are replayed from the stored log, so nothing is lost.</span></div> : null}
      {st.failed ? <div className="banner bad" style={{ marginBottom: 12 }} role="alert"><Ic n="warn" c="lg" /><span><b>The run stopped.</b> {st.failed.error}</span></div> : null}
      {st.cancelled ? <div className="banner" style={{ marginBottom: 12 }}><Ic n="cancel" /><span><b>Run cancelled.</b> {st.cancelled.reason || 'No decision was made.'}</span></div> : null}

      <div className="live-cols">
        <div className="card pipe" aria-label="Pipeline stages" data-testid="pipeline">
          {STAGES.map((def) => <StageCard key={def[0]} def={def} s={st.stages[def[0]]} open={open.has(def[0])} toggle={() => toggle(def[0])} />)}
        </div>

        <div className={`card canvas ${st.decision ? 'has-decision' : ''}`} id="canvas" data-state={st.completed ? 'done' : ''}>
          <div className="row" style={{ alignItems: 'flex-start', gap: 14, marginBottom: 14 }}>
            <button className={`docthumb ${scanned ? 'scanned' : ''}`} style={{ padding: 0 }} onClick={() => setZoom(true)} data-tip="Click to open a larger preview" aria-label="Open a larger preview of the invoice" disabled={!invoiceId}>
              {st.stages[1].status === 'done' || st.stages[1].status === 'skipped' || finished ? <img src={`${API}/api/invoices/${invoiceId}/pages/1.png?dpi=45`} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} /> : <Shimmer h={96} />}
            </button>
            <div className="grow">
              <div className="row wrap gap-s"><h3 style={{ fontSize: 15 }}>Extracted fields</h3>{scanned ? <span className="pill accent">Scanned image</span> : doc ? <span className="pill">Text PDF</span> : null}</div>
              <p className="small sec" style={{ marginTop: 3 }}>{scanned ? 'We read this by looking at the image, so some values carry less confidence.' : 'Read from the text layer of the PDF and confirmed against the page image.'} Fields appear as each stage finishes.</p>
            </div>
          </div>

          {needsAi ? (
            <div className="notice-scan" data-testid="needs-ai-notice">
              <Ic n="pause-circle" c="lg" />
              <div><b>This scan needs AI extraction</b><p>It is an image with no text layer, and no AI key is set on this server. Ledgerlight does not guess at numbers it cannot read, so the invoice goes on hold with a clear reason. With an Anthropic API key set, the same file is read by the vision model and decided automatically.</p></div>
            </div>
          ) : (
            <div className="fgrid" id="fgrid" data-testid="field-grid">
              {(() => {
                const keys = st.order.filter((k) => !BANK_FIELDS.includes(k));
                const base = HEADER_FIELDS.map(([k]) => k);
                const all = [...base, ...keys.filter((k) => !base.includes(k))];
                return all.map((k) => <FieldCard key={k} label={(HEADER_FIELDS.find((h) => h[0] === k) || [])[1] || (st.raw[k] || st.conf[k] || {}).label || k} raw={st.raw[k]} conf={st.conf[k]} />);
              })()}
            </div>
          )}

          <h3 style={{ fontSize: 13.5, margin: '18px 0 8px' }}>Line items</h3>
          <div className="tbl-wrap"><table className="tbl lines-t"><thead><tr><th>Description</th><th className="r">Qty</th><th className="r">Unit price</th><th className="r">Amount</th><th className="r">GST</th></tr></thead>
            <tbody data-testid="lines">{st.lines.map((l) => <tr className="fade-in" key={l.line_no}><td>{l.description}</td><td className="r num">{l.qty} {l.uom}</td><td className="r num">₹{l.unit_price}</td><td className="r num">₹{l.amount}</td><td className="r num">{l.tax_rate_pct}%</td></tr>)}
              {!st.lines.length ? <tr><td colSpan={5} className="muted small">{needsAi ? 'No line items could be read from the image.' : 'Waiting for the extraction stage…'}</td></tr> : null}</tbody></table></div>

          <h3 style={{ fontSize: 13.5, margin: '18px 0 8px' }}>Bank block</h3>
          <div className="bank" data-testid="bank-block">
            {st.raw.bank_account || st.raw.bank_name ? (
              <div className="fade-in">
                <div className="row wrap"><b>{(st.conf.bank_name || st.raw.bank_name || {}).display || (st.raw.bank_name || {}).value}</b><span className="mono small">A/c {(st.raw.bank_account || {}).value}</span><span className="mono small">IFSC {(st.raw.bank_ifsc || {}).value}</span></div>
                {st.stages[4].output && st.stages[4].output.bank ? (() => { const b = String(st.stages[4].output.bank); const bad = /mismatch|differ|not match|changed/i.test(b); return <div className="row gap-s fade-in" style={{ marginTop: 8 }}><span className={`chip ${bad ? 's-hold' : 's-auto'}`}><Ic n={bad ? 'pause-circle' : 'check-circle'} />{bad ? 'Does not match the bank on file' : 'Matches the bank on file'}</span></div>; })() : null}
              </div>
            ) : st.stages[2].status === 'done' || st.stages[2].status === 'skipped' ? <div className="sec small">{needsAi ? 'Nothing read from the image.' : 'No bank details printed on this invoice.'}</div> : <Shimmer w="55%" />}
          </div>

          {st.decision ? (
            <div className={`decide d-${dk} show`} data-testid="decision-card" data-outcome={st.decision.outcome}>
              <Chip k={dk} lg />
              <div className="grow" style={{ minWidth: 220 }}>
                <div style={{ fontFamily: 'var(--f-head)', fontWeight: 700, fontSize: 15, lineHeight: 1.35 }}>{st.decision.headline}</div>
                <div className="small muted" style={{ marginTop: 3 }}>{st.completed ? `Completed in ${secs(st.completed.duration_ms)}` : 'Finishing up'}{st.decision.exposure_paise ? ` · exposure ${inrP(st.decision.exposure_paise)}` : ''}{st.decision.assigned_to ? ` · assigned to ${st.decision.assigned_to === 'manager' ? 'Manager' : 'Clerk pool'}` : ''}</div>
              </div>
              <Link className="btn primary" href={`/decision/${runId}`} data-testid="see-explanation">See the full explanation <Ic n="arrow-r" /></Link>
            </div>
          ) : null}
        </div>

        <div className="log" aria-label="Streaming log">
          <div className="log-h"><Ic n="scroll" c="sm" />Streaming log
            <span className="right row gap-s">
              <span className="seg" id="lf">{['all', 'info', 'pass', 'warn', 'fail'].map((l) => <button key={l} className={lf === l ? 'on' : ''} onClick={() => setLf(l)}>{l[0].toUpperCase() + l.slice(1)}</button>)}</span>
              <button className="icon-btn" style={{ background: '#15213f', borderColor: '#2a3d6e', color: '#cdd8f3', width: 28, height: 28 }} aria-label="Copy log" onClick={async () => { await copyText(st.log.map((e) => `${fmtTS(e.ts)} [${e.stage ? 'S' + e.stage : 'run'}] ${e.level.toUpperCase()} ${e.text}`).join('\n')); toast('Log copied to the clipboard'); }}><Ic n="copy" c="sm" /></button>
            </span></div>
          <div className="log-b" id="logb" ref={logRef} role="log" aria-live="off" data-testid="log">
            {visLog.map((e) => (
              <div key={e.id} className={`ll l-${e.level} ${e.pace ? 'pace' : ''}`}><span className="ts">{fmtTS(e.ts)}</span><span className="st">{e.stage ? `[S${e.stage}]` : '[run]'}</span><Ic n={{ info: 'info', pass: 'check-circle', warn: 'warn', fail: 'x-circle' }[e.level] || 'info'} /><span className="m">{e.text}</span></div>
            ))}
            {!visLog.length ? <div className="ll"><span className="ts" /><span className="st" /><span /><span className="m" style={{ color: '#62749c' }}>{st.meta ? 'No events at this level yet.' : 'Starting…'}</span></div> : null}
          </div>
          <div className="log-f"><span data-testid="log-count">{st.log.length} events</span><button className="btn sm ghost" style={{ color: '#9fb0d4', borderColor: '#2a3d6e' }} onClick={() => setPaused((p) => !p)}>{paused ? 'Resume scroll' : 'Pause scroll'}</button><span className="right">Same events as the audit log</span></div>
        </div>
      </div>

      <Modal open={zoom} onClose={() => setZoom(false)} label="Invoice preview">
        <div className="sheet-h"><h3>{fileName}</h3><a className="btn sm right" href={`${API}/api/invoices/${invoiceId}/pdf`} target="_blank" rel="noreferrer">Open the PDF</a><button className="icon-btn" onClick={() => setZoom(false)} aria-label="Close"><Ic n="x" /></button></div>
        <div className="paper-wrap">{invoiceId ? <img className="pdf-img" style={{ maxWidth: 560 }} src={`${API}/api/invoices/${invoiceId}/pages/1.png?dpi=110`} alt={`Page 1 of ${fileName}`} /> : null}</div>
      </Modal>
    </div>
  );
}
