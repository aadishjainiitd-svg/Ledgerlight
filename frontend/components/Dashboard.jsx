'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { API, url, api, qs } from '@/lib/api';
import { addDays, clamp, fmtDS, fmtDayS, fmtT, inr, inrP, inrP2, pct, secs } from '@/lib/format';
import { Chip, ConfChip, Empty, ErrorBanner, Ic, OUT, OUT_COLOR, OUT_KEYS, PageHead, Shimmer, outKey, KEY2API, useApi, useApp } from '@/lib/ui';

const OUT_API = { auto: 'auto_approve', note: 'approve_with_note', review: 'route_for_review', hold: 'hold_request_info', reject: 'reject' };

/* ---------- sparkline (area + line + emphasised endpoint) ---------- */
function Spark({ vals, color = 'var(--accent)' }) {
  if (!vals || vals.length < 2) return <div style={{ height: 26 }} />;
  const w = 120, h = 26, mx = Math.max(...vals, 1), mn = Math.min(...vals, 0), sp = mx - mn || 1;
  const pts = vals.map((v, i) => [(i / (vals.length - 1)) * (w - 6) + 3, h - 4 - ((v - mn) / sp) * (h - 9)]);
  const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
  const last = pts[pts.length - 1];
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={`${line} L${last[0]} ${h} L${pts[0][0]} ${h}Z`} fill={color} opacity=".12" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2.6" fill={color} stroke="var(--surface)" strokeWidth="1.5" />
    </svg>
  );
}

const weekLabel = (ws) => { const e = addDays(ws, 6); const a = fmtDayS(ws), b = fmtDayS(e); return a.split(' ')[1] === b.split(' ')[1] ? `${a.split(' ')[0]}–${b}` : `${a}–${b}`; };

/* ---------- charts (hand-drawn SVG so every mark, tick and label shares one scale) ---------- */
function StackChart({ weeks, onPick }) {
  const W = 600, H = 250, L = 34, R = 8, T = 10, B = 40;
  const tot = (w) => OUT_KEYS.reduce((s, k) => s + (w[OUT_API[k]] || 0), 0);
  const mx = Math.max(...weeks.map(tot), 4), step = mx <= 8 ? 2 : mx <= 20 ? 5 : 10, top = Math.ceil(mx / step) * step;
  const iw = W - L - R, ih = H - T - B, bw = Math.min(54, (iw / Math.max(weeks.length, 1)) * 0.56);
  const [tip, setTip] = useState(null);
  const ticks = []; for (let v = 0; v <= top; v += step) ticks.push(v);
  return (
    <div style={{ position: 'relative' }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Decisions per week by outcome" data-testid="chart-stack">
        {ticks.map((v) => { const y = T + ih - (v / top) * ih; return <g key={v}><line className="gl" x1={L} x2={W - R} y1={y} y2={y} /><text x={L - 8} y={y + 4} textAnchor="end">{v}</text></g>; })}
        {weeks.map((w, i) => {
          const cx = L + (iw / weeks.length) * (i + 0.5); let y0 = T + ih; const lab = weekLabel(w.week_start);
          return (
            <g key={w.week_start}>
              {OUT_KEYS.map((o) => {
                const cnt = w[OUT_API[o]] || 0; if (!cnt) return null; const hh = (cnt / top) * ih; y0 -= hh;
                return (
                  <g key={o}>
                    <rect className="seg-r" x={cx - bw / 2} y={y0} width={bw} height={hh} rx="2" fill={OUT_COLOR[o]} style={{ cursor: 'pointer' }}
                      onClick={() => onPick(o)} onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, t: `${lab}\n${OUT[o].label}: ${cnt}\nClick to filter the table` })} onMouseLeave={() => setTip(null)} />
                    {hh > 15 ? <text x={cx} y={y0 + hh / 2 + 4} textAnchor="middle" style={{ fill: '#fff', fontWeight: 700, pointerEvents: 'none' }}>{cnt}</text> : null}
                  </g>
                );
              })}
              <text x={cx} y={H - 20} textAnchor="middle">{lab}</text>
              <text x={cx} y={H - 6} textAnchor="middle" style={{ fontWeight: 700, fill: 'var(--ink-2)' }}>{tot(w)} total</text>
            </g>
          );
        })}
      </svg>
      {tip ? <div className="tip show" style={{ left: tip.x + 14, top: tip.y + 14, whiteSpace: 'pre-line' }}>{tip.t}</div> : null}
    </div>
  );
}

function Donut({ mix, onPick }) {
  const tot = OUT_KEYS.reduce((s, k) => s + (mix[OUT_API[k]] || 0), 0) || 1;
  const R0 = 62, sw = 24, C = 2 * Math.PI * R0; let off = 0;
  const [tip, setTip] = useState(null);
  return (
    <div className="row wrap" style={{ gap: 22, justifyContent: 'center' }}>
      <svg className="chart" viewBox="0 0 180 180" style={{ width: 170, flex: 'none' }} role="img" aria-label="Outcome mix" data-testid="chart-donut">
        {OUT_KEYS.map((o) => {
          const c = mix[OUT_API[o]] || 0; if (!c) return null; const len = (c / tot) * C; const el = (
            <circle key={o} className="seg-r" cx="90" cy="90" r={R0} fill="none" style={{ stroke: OUT_COLOR[o], strokeWidth: sw, cursor: 'pointer' }} strokeDasharray={`${Math.max(len - 2.5, 0.5)} ${C}`} strokeDashoffset={-off} transform="rotate(-90 90 90)"
              onClick={() => onPick(o)} onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, t: `${OUT[o].label}\n${c} invoices (${Math.round((c / tot) * 100)}%)` })} onMouseLeave={() => setTip(null)} />
          ); off += len; return el;
        })}
        <text x="90" y="88" textAnchor="middle" style={{ fontFamily: 'var(--f-head)', fontSize: 28, fontWeight: 800, fill: 'var(--ink)' }}>{OUT_KEYS.reduce((s, k) => s + (mix[OUT_API[k]] || 0), 0)}</text>
        <text x="90" y="106" textAnchor="middle">invoices</text>
      </svg>
      <div className="stack-s grow" style={{ minWidth: 170, fontSize: 13 }}>
        {OUT_KEYS.map((o) => { const c = mix[OUT_API[o]] || 0; return (
          <div key={o} className="row" style={{ justifyContent: 'space-between', gap: 12 }}>
            <span className="row gap-s"><i style={{ width: 10, height: 10, borderRadius: 3, background: OUT_COLOR[o], display: 'inline-block' }} />{OUT[o].label}</span>
            <span className="num"><b>{c}</b> <span className="muted">{Math.round((c / tot) * 100)}%</span></span>
          </div>); })}
      </div>
      {tip ? <div className="tip show" style={{ left: tip.x + 14, top: tip.y + 14, whiteSpace: 'pre-line' }}>{tip.t}</div> : null}
    </div>
  );
}

function Reasons({ items }) {
  if (!items.length) return <Empty title="No exceptions in this period"><p>Everything went straight through.</p></Empty>;
  const mx = Math.max(...items.map((i) => i.count), 1), W = 520, rowH = 34, H = items.length * rowH + 4, lab = 190;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Top reasons for exceptions" data-testid="chart-reasons">
      {items.map((it, i) => { const y = i * rowH + 4, bw = Math.max(6, (it.count / mx) * (W - lab - 44)); return (
        <g key={it.category}>
          <text x="0" y={y + 17} style={{ fill: 'var(--ink-2)', fontSize: 12.5 }}>{it.category}</text>
          <rect x={lab} y={y + 5} width={W - lab - 44} height="16" rx="4" fill="var(--surface-3)" />
          <rect x={lab} y={y + 5} width={bw} height="16" rx="4" fill="var(--accent)"><title>{`${it.category}: ${it.count} invoices`}</title></rect>
          <text x={lab + bw + 8} y={y + 18} style={{ fill: 'var(--ink)', fontWeight: 700, fontSize: 12.5 }}>{it.count}</text>
        </g>); })}
    </svg>
  );
}

function MedianLine({ weeks }) {
  const W = 520, H = 220, L = 34, R = 14, T = 14, B = 30, iw = W - L - R, ih = H - T - B;
  const vals = weeks.map((w) => (w.median_ms ? w.median_ms / 1000 : null));
  const real = vals.filter((v) => v != null);
  const mx = Math.max(20, Math.ceil((Math.max(...real, 1) + 1) / 4) * 4), mn = 0;
  const X = (i) => L + (weeks.length === 1 ? iw / 2 : (i / (weeks.length - 1)) * iw), Y = (v) => T + ih - ((v - mn) / (mx - mn)) * ih;
  const ticks = [0, mx / 4, mx / 2, (mx * 3) / 4, mx].map((v) => Math.round(v));
  const pts = vals.map((v, i) => (v == null ? null : [X(i), Y(v)])).filter(Boolean);
  const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Median time to decision per week" data-testid="chart-median">
      {ticks.map((v) => <g key={v}><line className="gl" x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} /><text x={L - 8} y={Y(v) + 4} textAnchor="end">{v}s</text></g>)}
      {pts.length > 1 ? <><path d={`${path}L${pts[pts.length - 1][0]} ${T + ih}L${pts[0][0]} ${T + ih}Z`} fill="var(--accent)" opacity=".1" /><path d={path} fill="none" stroke="var(--accent)" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" /></> : null}
      {weeks.map((w, i) => <text key={w.week_start} x={X(i)} y={H - 8} textAnchor="middle">{fmtDayS(w.week_start)}</text>)}
      {vals.map((v, i) => { if (v == null) return null; const last = i === vals.length - 1; return (
        <g key={i}><circle cx={X(i)} cy={Y(v)} r={last ? 5.5 : 4} fill="var(--accent)" stroke="var(--surface)" strokeWidth="2"><title>{`Week of ${fmtDayS(weeks[i].week_start)}: median ${v.toFixed(1)} s`}</title></circle>
          {last ? <text x={X(i) - 4} y={Y(v) - 12} textAnchor="middle" style={{ fill: 'var(--ink)', fontWeight: 700, fontSize: 12 }}>{v.toFixed(0)} s</text> : null}</g>); })}
    </svg>
  );
}

/* ---------- runs table ---------- */
const COLS = [['time', 'Run'], ['vendor', 'Vendor'], ['invoice_no', 'Invoice no.'], ['po', 'PO'], ['amount', 'Amount'], ['outcome', 'Decision'], [null, 'Main reason'], ['confidence', 'Confidence'], ['duration', 'Duration'], [null, 'Edited']];

function RunsCard({ range, filters, setFilters, tick, onReset }) {
  const router = useRouter();
  const [q, setQ] = useState(''); const [dq, setDq] = useState('');
  const [sort, setSort] = useState({ k: 'time', d: 'desc' });
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setDq(q); setPage(1); }, 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { setPage(1); }, [range, filters]);
  const status = [...filters].map((f) => (f === 'running' ? 'running' : OUT_API[f])).join(',');
  const path = '/api/runs' + qs({ range: range + 'd', status, q: dq, sort: sort.k, order: sort.d, page, page_size: 25 });
  const { data, error, loading, reload } = useApi(path, { tick });
  const countsRes = useApi('/api/runs' + qs({ range: range + 'd', page_size: 1 }), { tick });
  const counts = (countsRes.data || data || {}).counts || {};
  const items = data ? data.items : [];
  const total = data ? data.total : 0, pages = Math.max(1, Math.ceil(total / 25));
  const toggle = (o) => { const n = new Set(filters); n.has(o) ? n.delete(o) : n.add(o); setFilters(n); };
  const hasRunning = (counts.running || 0) > 0;
  return (
    <div className="card" id="runs-card" data-testid="runs-card">
      <div className="card-h" style={{ paddingBottom: 12, flexWrap: 'wrap' }}>
        <h3>Runs</h3>
        <div className="chips grow">
          <button className={`fchip ${filters.size ? '' : 'on'}`} onClick={() => setFilters(new Set())}>All <span className="n">{counts.all ?? '–'}</span></button>
          {OUT_KEYS.map((o) => (
            <button key={o} className={`fchip ${filters.has(o) ? 'on' : ''}`} aria-pressed={filters.has(o)} onClick={() => toggle(o)}><Ic n={OUT[o].ic} c="sm" />{OUT[o].label} <span className="n">{counts[OUT_API[o]] ?? 0}</span></button>
          ))}
          <button className={`fchip ${filters.has('running') ? 'on' : ''}`} aria-pressed={filters.has('running')} onClick={() => toggle('running')}><Ic n="spinner" c={`sm ${hasRunning ? 'spin' : ''}`} />Running <span className="n">{counts.running ?? 0}</span></button>
        </div>
        <div className="search" style={{ width: 240 }}><Ic n="search" /><input type="search" id="run-search" placeholder="Search vendor, invoice or PO" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search runs" /></div>
      </div>
      <div className={`tbl-wrap ${loading && !data ? '' : ''}`}>
        <table className="tbl" data-testid="runs-table">
          <thead><tr>{COLS.map(([k, l], i) => (
            <th key={i} className={`${k ? 'sortable' : ''} ${k === 'amount' || k === 'duration' ? 'r' : ''}`} onClick={k ? () => setSort((s) => ({ k, d: s.k === k && s.d === 'desc' ? 'asc' : 'desc' })) : undefined} aria-sort={sort.k === k ? (sort.d === 'asc' ? 'ascending' : 'descending') : undefined}>
              {l}{sort.k === k ? <span className="arr">{sort.d === 'asc' ? '▲' : '▼'}</span> : null}</th>))}</tr></thead>
          <tbody>
            {loading && !data ? Array.from({ length: 6 }).map((_, i) => <tr key={i}><td colSpan={10}><Shimmer h={30} /></td></tr>) : null}
            {items.map((r) => {
              const k = outKey(r.outcome); const running = r.status === 'running';
              const href = running ? `/runs/${r.run_id}` : `/decision/${r.run_id}`;
              return (
                <tr key={r.run_id} className="link sev" style={{ '--sev': running ? 'var(--accent)' : OUT_COLOR[k] }} onClick={() => router.push(href)} data-testid="run-row" data-run={r.run_id} title={r.headline || ''}>
                  <td><div className="mono small">{r.run_id}</div><div className="tiny muted">{running ? 'Just now' : `${fmtDS(r.received_at)}, ${fmtT(r.received_at)}`}</div></td>
                  <td className="nowrap">{r.vendor_short || r.vendor_name || <span className="muted">{running ? 'Reading…' : 'Not read'}</span>}</td>
                  <td className="mono nowrap">{r.invoice_no || '—'}</td>
                  <td className="mono small nowrap">{r.po_id ? r.po_id + (r.po_inferred ? '*' : '') : '—'}</td>
                  <td className="r num nowrap">{r.gross_paise ? inrP2(r.gross_paise) : '—'}</td>
                  <td>{running ? <Chip k="running" /> : r.status === 'failed' ? <Chip k="failed" /> : r.status === 'cancelled' ? <Chip k="cancelled" /> : <Chip k={r.outcome} />}</td>
                  <td className="sec" style={{ minWidth: 230, maxWidth: 340 }}>{running ? (r.stage_label || 'Starting…') : r.main_reason || r.error || ''}</td>
                  <td><ConfChip c={r.lowest_confidence} /></td>
                  <td className="r num muted">{running ? '—' : secs(r.duration_ms)}</td>
                  <td className="c">{r.overridden ? <span data-tip="Changed by a person"><Ic n="edit" c="sm c-review" /></span> : null}</td>
                </tr>
              );
            })}
            {!loading && !items.length ? <tr><td colSpan={10}><Empty title="No runs match these filters"><p>Try a different status or clear the search.</p><p style={{ marginTop: 10 }}><button className="btn" onClick={() => { setFilters(new Set()); setQ(''); }}>Clear filters</button></p></Empty></td></tr> : null}
          </tbody>
        </table>
      </div>
      {error && !data ? <div style={{ padding: 16 }}><ErrorBanner error={error} onRetry={reload} /></div> : null}
      <div className="pager">
        <span>Showing {items.length} of {total} runs</span>
        <span className="right row gap-s">
          <button className="btn sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button className="btn sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
          <Link href="/audit" style={{ marginLeft: 10 }}>Open the audit log</Link>
        </span>
      </div>
    </div>
  );
}

/* ---------- page ---------- */
export default function Dashboard() {
  const { tick, toast } = useApp();
  const router = useRouter();
  const [range, setRange] = useState(30);
  const [filters, setFilters] = useState(new Set());
  const { data, error, loading, reload } = useApi(`/api/metrics?range=${range}d`, { tick, deps: [range], interval: 15000 });
  const runsRef = useRef(null);
  const pick = (o) => { setFilters(new Set([o])); setTimeout(() => runsRef.current && runsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50); };

  const t = data && data.tiles; const ch = data && data.charts; const bn = data && data.banner;
  const weeks = ch ? ch.decisions_per_week : [];
  const wTot = (w) => OUT_KEYS.reduce((s, k) => s + (w[OUT_API[k]] || 0), 0);
  const sN = weeks.map(wTot);
  const sS = weeks.map((w) => (wTot(w) ? ((w.auto_approve + w.approve_with_note) / wTot(w)) * 100 : 0));
  const sM = (ch ? ch.median_time_per_week : []).map((w) => (w.median_ms || 0) / 1000);
  const empty = data && data.tiles.processed.value === 0 && data.running === 0;

  async function exportCsv() {
    try {
      const res = await fetch(url(`/api/export/approved.csv?range=${range}d`));
      const text = await res.text();
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' })); a.download = `approved-invoices-${range}d.csv`; document.body.appendChild(a); a.click(); a.remove();
      toast('Approved invoices exported as CSV. The export was recorded in the audit log.');
    } catch { toast("Couldn't export. The server is not reachable."); }
  }
  async function loadDemo() { try { await api('/api/demo/reset', { method: 'POST' }); toast('Demo data loaded.'); reload(); } catch (e) { toast(e.message); } }

  const approvedV = t ? t.value_approved_paise.value : 0;
  const crore = approvedV / 100 >= 10000000;
  const contributors = t ? t.value_protected_paise.contributors || [] : [];
  const protTip = ['Value protected', ...contributors.map((c) => `${c.category}: ${inrP(c.value_paise)} (${c.count})`)].join('\n');
  const delta = (tile, unit = '') => (tile && tile.change != null && tile.previous ? <span className={`delta ${tile.change >= 0 ? 'up' : 'down'}`}>{tile.change >= 0 ? '▲' : '▼'} {Math.abs(tile.change)}{unit}</span> : null);

  return (
    <>
      <PageHead title="Dashboard" sub="How accounts payable is doing, and what needs a person.">
        <div className="seg" role="group" aria-label="Date range">{[7, 30, 90].map((n) => <button key={n} aria-pressed={range === n} onClick={() => setRange(n)}>{n} days</button>)}</div>
        <button className="btn" onClick={exportCsv}><Ic n="download" />Export approved (CSV)</button>
        <Link className="btn primary" href="/new"><Ic n="plus" />Process invoice</Link>
      </PageHead>
      <div className="stack">
        <ErrorBanner error={error} onRetry={reload} />
        {bn && (bn.review + bn.hold > 0) ? (
          <div className="banner" role="status" data-testid="attention-banner"><Ic n="eye" c="lg" /><span className="grow"><b>{bn.review} invoices need review, {bn.hold} on hold, oldest {bn.oldest_days} days.</b></span><Link href="/queue">Open the review queue</Link></div>
        ) : null}
        {empty ? (
          <div className="card"><Empty title="No invoices processed yet"><p>Process an invoice to see decisions here, or load the demo data.</p><p style={{ marginTop: 12 }} className="row" ><Link className="btn primary" href="/new">Process an invoice</Link><button className="btn" onClick={loadDemo}>Load demo data</button></p></Empty></div>
        ) : null}
        <div className={`kpis ${error && data ? 'dimmed' : ''}`} data-testid="kpis">
          {loading && !data ? Array.from({ length: 6 }).map((_, i) => <div key={i} className="card kpi skel-card"><Shimmer w="60%" /><Shimmer w="40%" h={26} /></div>) : t ? (
            <>
              <div className="card kpi" data-testid="kpi-processed"><div className="lab">Invoices processed</div><div className="val num">{t.processed.value}</div><div className="sub">{delta(t.processed)} in the last {range} days</div><Spark vals={sN} /></div>
              <div className="card kpi hero" data-testid="kpi-str"><div className="lab">Straight-through rate</div><div className="val num">{Math.round(t.straight_through_rate.value)}<small>%</small></div><div className="sub">{delta(t.straight_through_rate, ' pts')} approved with no human touch</div><Spark vals={sS} /></div>
              <div className="card kpi"><div className="lab">Median time to decision</div><div className="val num">{Math.round(t.median_time_to_decision_ms.value / 1000)}<small>s</small></div><div className="sub">est. {Math.round(t.median_time_to_decision_ms.manual_baseline_ms / 60000)} min by hand</div><Spark vals={sM} /></div>
              <div className="card kpi"><div className="lab">Open exceptions</div><div className="val num">{t.open_exceptions.value_all_time ?? t.open_exceptions.value}</div><div className="sub">{bn ? `${bn.review} to review · ${bn.hold} on hold` : ''}</div><div className="bar" style={{ marginTop: 8 }}><i style={{ width: `${t.processed.value ? Math.min(100, (t.open_exceptions.value / t.processed.value) * 100) : 0}%`, background: 'var(--review)' }} /></div></div>
              <div className="card kpi" data-tip={protTip}><div className="lab">Value protected <Ic n="info" c="sm" /></div><div className="val num">{inrP(t.value_protected_paise.value)}</div><div className="sub">Duplicates and overbilling stopped</div></div>
              <div className="card kpi"><div className="lab">Value approved</div><div className="val num">{crore ? <>₹{(approvedV / 100 / 10000000).toFixed(2)}<small>Cr</small></> : approvedV / 100 >= 100000 ? <>₹{(approvedV / 100 / 100000).toFixed(1)}<small>lakh</small></> : inrP(approvedV)}</div><div className="sub">Gross, in the payment queue</div></div>
            </>
          ) : null}
        </div>
        <div className={`chart-grid ${error && data ? 'dimmed' : ''}`}>
          <div className="card cg-7"><div className="card-h"><h3>Decisions per week</h3><div className="legend right">{OUT_KEYS.map((o) => <span key={o}><i style={{ background: OUT_COLOR[o] }} />{OUT[o].label}</span>)}</div></div><div className="card-b">{ch ? <StackChart weeks={weeks} onPick={pick} /> : <Shimmer h={220} />}</div></div>
          <div className="card cg-5"><div className="card-h"><h3>Outcome mix</h3><span className="muted small right">Click a slice to filter</span></div><div className="card-b" style={{ paddingTop: 22 }}>{ch ? <Donut mix={ch.outcome_mix} onPick={pick} /> : <Shimmer h={170} />}</div></div>
          <div className="card cg-7"><div className="card-h"><h3>Top reasons for exceptions</h3><span className="muted small right">Review, hold and reject</span></div><div className="card-b">{ch ? <Reasons items={ch.top_exception_reasons} /> : <Shimmer h={170} />}</div></div>
          <div className="card cg-5"><div className="card-h"><h3>Median time to decision</h3><span className="muted small right">Manual baseline: {t ? Math.round(t.median_time_to_decision_ms.manual_baseline_ms / 60000) : 9} min (est.)</span></div><div className="card-b">{ch ? <MedianLine weeks={ch.median_time_per_week} /> : <Shimmer h={170} />}</div></div>
        </div>
        <div ref={runsRef}><RunsCard range={range} filters={filters} setFilters={setFilters} tick={tick} /></div>
      </div>
    </>
  );
}
