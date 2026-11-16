'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ICONS } from './icons';
import { api } from './api';

/* ---------- icons ---------- */
export function Ic({ n, c = '', style }) {
  return <svg className={`ic ${c}`} viewBox="0 0 24 24" aria-hidden="true" style={style} dangerouslySetInnerHTML={{ __html: ICONS[n] || '' }} />;
}

/* ---------- status vocabulary (one chip, colour, icon and wording everywhere) ---------- */
export const OUT = {
  auto: { id: 'auto_approve', label: 'Approved', long: 'Auto-approve', ic: 'check-circle', rank: 0 },
  note: { id: 'approve_with_note', label: 'Approved, note', long: 'Approve with note', ic: 'note-circle', rank: 1 },
  review: { id: 'route_for_review', label: 'Needs review', long: 'Route for review', ic: 'eye', rank: 2 },
  hold: { id: 'hold_request_info', label: 'On hold', long: 'Hold: request info', ic: 'pause-circle', rank: 3 },
  reject: { id: 'reject', label: 'Rejected', long: 'Reject', ic: 'x-circle', rank: 4 },
};
export const OUT_KEYS = ['auto', 'note', 'review', 'hold', 'reject'];
export const OUT_COLOR = { auto: 'var(--ok)', note: 'var(--note)', review: 'var(--review)', hold: 'var(--hold)', reject: 'var(--reject)' };
const API2KEY = { auto_approve: 'auto', approve_with_note: 'note', route_for_review: 'review', hold_request_info: 'hold', reject: 'reject' };
export const outKey = (o) => API2KEY[o] || o;
export const KEY2API = Object.fromEntries(Object.entries(API2KEY).map(([a, k]) => [k, a]));

export function Chip({ k, lg, label }) {
  k = outKey(k);
  if (k === 'running') return <span className={`chip s-running ${lg ? 'lg' : ''}`}><Ic n="spinner" c="spin" />Running</span>;
  if (k === 'failed') return <span className={`chip s-error ${lg ? 'lg' : ''}`}><Ic n="warn" />Error</span>;
  if (k === 'cancelled') return <span className={`chip s-none ${lg ? 'lg' : ''}`}><Ic n="cancel" />Cancelled</span>;
  const o = OUT[k]; if (!o) return null;
  return <span className={`chip s-${k} ${lg ? 'lg' : ''}`}><Ic n={o.ic} />{label || o.label}</span>;
}
export const confClass = (c) => (c == null ? 'na' : c >= 0.9 ? 'hi' : c >= 0.75 ? 'mid' : 'lo');
export function ConfChip({ c }) {
  return <span className={`conf ${confClass(c)}`} title={`Confidence ${c == null ? 'not applicable' : c.toFixed(2)}`}>{c == null ? 'n/a' : c.toFixed(2)}</span>;
}
export const SEVRANK = { pass: 0, note: 1, review: 2, hold: 3, reject: 4 };
const SEV_ICON = { pass: ['check-circle', 'c-pass'], note: ['note-circle', 'c-note'], review: ['eye', 'c-review'], hold: ['pause-circle', 'c-hold'], reject: ['x-circle', 'c-reject'] };
export const SevIcon = ({ s }) => { const [i, c] = SEV_ICON[s] || SEV_ICON.pass; return <Ic n={i} c={c} />; };
export function SevChip({ s }) {
  if (s === 'pass') return <span className="chip s-pass"><Ic n="check-circle" />Pass</span>;
  const o = OUT[s]; const label = { note: 'Note', review: 'Review', hold: 'Hold', reject: 'Reject' }[s];
  return <span className={`chip s-${s}`}><Ic n={o.ic} />{label}</span>;
}
export const sevToOut = (s) => (s === 'pass' ? 'auto' : s);

/* ---------- small atoms ---------- */
export function PageHead({ title, sub, children }) {
  return (
    <div className="page-head">
      <div className="grow"><h1>{title}</h1>{sub ? <p>{sub}</p> : null}</div>
      <div className="row wrap">{children}</div>
    </div>
  );
}
export const Shimmer = ({ w = '100%', h = 14, style }) => <div className="shimmer" style={{ width: w, height: h, ...style }} />;
export function Empty({ title, children }) { return <div className="empty"><h4>{title}</h4>{children}</div>; }
export function ErrorBanner({ error, onRetry }) {
  if (!error) return null;
  const down = error.status === 0;
  return (
    <div className="banner bad" role="alert" data-testid="error-banner">
      <Ic n="warn" c="lg" /><span className="grow"><b>{down ? "Can't reach the Ledgerlight server. Retrying." : 'Something went wrong.'}</b> {down ? 'Showing the last numbers we had.' : error.message}</span>
      {onRetry ? <button className="btn sm" onClick={onRetry}>Retry</button> : null}
    </div>
  );
}

/* ---------- toasts, tooltips, sheets ---------- */
const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);
export { AppCtx };

export function useToasts() {
  const [items, setItems] = useState([]);
  const idRef = useRef(1);
  const toast = useCallback((msg, undo) => {
    const id = idRef.current++;
    setItems((l) => [...l, { id, msg, undo }]);
    setTimeout(() => setItems((l) => l.filter((x) => x.id !== id)), undo ? 10000 : 4600);
  }, []);
  const kill = (id) => setItems((l) => l.filter((x) => x.id !== id));
  const view = (
    <div className="toasts" role="status" aria-live="polite" data-testid="toasts">
      {items.map((t) => (
        <div key={t.id} className="toast"><span>{t.msg}</span>{t.undo ? <button onClick={() => { kill(t.id); t.undo(); }}>Undo</button> : null}</div>
      ))}
    </div>
  );
  return [toast, view];
}

/** One floating tooltip for every [data-tip] element (plain text, line breaks kept). */
export function TipLayer() {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    const move = (e) => {
      const t = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!t) { el.classList.remove('show'); return; }
      el.textContent = t.getAttribute('data-tip'); el.classList.add('show');
      const w = el.offsetWidth, h = el.offsetHeight; let left = e.clientX + 14, top = e.clientY + 14;
      if (left + w > innerWidth - 8) left = e.clientX - w - 14;
      if (left < 8) left = 8;
      if (top + h > innerHeight - 8) top = e.clientY - h - 14;
      if (top < 8) top = 8;
      el.style.left = left + 'px'; el.style.top = top + 'px';
    };
    const hide = () => el.classList.remove('show');
    document.addEventListener('mousemove', move); document.addEventListener('scroll', hide, true);
    return () => { document.removeEventListener('mousemove', move); document.removeEventListener('scroll', hide, true); };
  }, []);
  return <div ref={ref} className="tip" role="tooltip" style={{ whiteSpace: 'pre-line' }} />;
}

function useShown(open) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (open) { const r = requestAnimationFrame(() => setShown(true)); return () => cancelAnimationFrame(r); }
    setShown(false);
  }, [open]);
  return shown;
}
function useEsc(open, onClose) {
  useEffect(() => {
    if (!open) return;
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', k); return () => document.removeEventListener('keydown', k);
  }, [open, onClose]);
}
export function Sheet({ open, onClose, wide, children, label }) {
  const shown = useShown(open); useEsc(open, onClose);
  if (!open) return null;
  return (
    <>
      <div className={`scrim ${shown ? 'show' : ''}`} onClick={onClose} />
      <aside className={`sheet ${wide ? 'wide' : ''} ${shown ? 'show' : ''}`} role="dialog" aria-modal="true" aria-label={label}>{children}</aside>
    </>
  );
}
export function Modal({ open, onClose, children, label }) {
  const shown = useShown(open); useEsc(open, onClose);
  if (!open) return null;
  return (
    <>
      <div className={`scrim ${shown ? 'show' : ''}`} onClick={onClose} />
      <div className={`modal ${shown ? 'show' : ''}`} role="dialog" aria-modal="true" aria-label={label}>{children}</div>
    </>
  );
}

export async function copyText(txt) {
  try { await navigator.clipboard.writeText(txt); return true; } catch {
    const ta = document.createElement('textarea'); ta.value = txt; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch { /* ignore */ } ta.remove(); return ok;
  }
}

/* ---------- data hook ---------- */
export function useApi(path, { deps = [], tick = 0, enabled = true, interval = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const load = useCallback(async (quiet) => {
    if (!path || !enabled) return;
    const my = ++seq.current;
    if (!quiet) setState((s) => ({ ...s, loading: true }));
    try {
      const data = await api(path);
      if (my === seq.current) setState({ data, error: null, loading: false });
    } catch (error) {
      if (my === seq.current) setState((s) => ({ data: s.data, error, loading: false }));
    }
  }, [path, enabled]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(false); }, [path, enabled, ...deps]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (tick) load(true); }, [tick]);
  useEffect(() => { if (!interval) return undefined; const t = setInterval(() => load(true), interval); return () => clearInterval(t); }, [interval, load]);
  return { ...state, reload: () => load(false), refresh: () => load(true) };
}
