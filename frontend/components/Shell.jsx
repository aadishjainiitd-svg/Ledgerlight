'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API, ROLES, api, setApiRole } from '@/lib/api';
import { AppCtx, Ic, TipLayer, useApi, useToasts } from '@/lib/ui';

const NAV = [
  ['/', 'Dashboard', 'dash', 's1'],
  ['/new', 'New run', 'upload', 's2'],
  ['/runs', 'Live run', 'bolt', 's3'],
  ['/queue', 'Review queue', 'queue', 's5'],
  ['/master', 'Purchase orders and vendors', 'db', 's6'],
  ['/rules', 'Rules and tolerances', 'sliders', 's7'],
  ['/audit', 'Audit log', 'scroll', 's8'],
];
const EC_NAV = [['SI-03', 'EC1', 'Kestrel, split PO'], ['SI-04', 'EC2', 'Brightline, duplicate'], ['SI-05', 'EC3', 'Greenleaf, blurry scan'], ['SI-06', 'EC4', 'Corevolt, bank change']];

const LOGO = (
  <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#2c55d9" /><path d="M9 22V10m0 12h14" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" fill="none" /><path d="M13 18l3-3 3 2 4-5" stroke="#9ff0c5" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" /></svg>
);

function activeKey(path) {
  if (path === '/') return 's1';
  if (path.startsWith('/new')) return 's2';
  if (path.startsWith('/runs')) return 's3';
  if (path.startsWith('/decision')) return 's4';
  if (path.startsWith('/queue')) return 's5';
  if (path.startsWith('/master')) return 's6';
  if (path.startsWith('/rules')) return 's7';
  if (path.startsWith('/audit')) return 's8';
  return '';
}

export default function Shell({ children }) {
  const path = usePathname();
  const router = useRouter();
  const [role, setRoleState] = useState('clerk');
  const [settings, setSettingsState] = useState({ speed: 'normal', cache: true });
  const [tick, setTick] = useState(0);
  const [roleTick, setRoleTick] = useState(0);
  const [connected, setConnected] = useState(true);
  const [menu, setMenu] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [crumb, setCrumb] = useState(null);
  const [toast, toastView] = useToasts();
  const lastLive = useRef(null);
  const [live, setLive] = useState(null);
  const [lastRunRoute, setLastRunRoute] = useState('/new');

  /* persisted per-viewer conveniences */
  useEffect(() => {
    try {
      const r = localStorage.getItem('ll-role'); if (r && ROLES[r]) { setRoleState(r); setApiRole(r); }
      const s = JSON.parse(localStorage.getItem('ll-settings') || 'null'); if (s) setSettingsState((x) => ({ ...x, ...s }));
      const lr = sessionStorage.getItem('ll-last-run'); if (lr) setLastRunRoute(lr);
    } catch { /* storage unavailable */ }
  }, []);
  const setRole = useCallback((r) => {
    setRoleState(r); setApiRole(r); setRoleTick((n) => n + 1);
    try { localStorage.setItem('ll-role', r); } catch { /* ignore */ }
    toast(`Now acting as ${ROLES[r].label}, ${ROLES[r].name}.`);
  }, [toast]);
  const setSettings = useCallback((patch) => {
    setSettingsState((s) => { const n = { ...s, ...patch }; try { localStorage.setItem('ll-settings', JSON.stringify(n)); } catch { /* ignore */ } return n; });
  }, []);
  const rememberRun = useCallback((href) => { setLastRunRoute(href); try { sessionStorage.setItem('ll-last-run', href); } catch { /* ignore */ } }, []);

  /* global live stream: new runs, stage changes, completions, overrides, resets */
  useEffect(() => {
    let es; let timer; let debounce; let stopped = false;
    const bump = (type, data) => {
      setLive({ type, data, at: Date.now() });
      clearTimeout(debounce); debounce = setTimeout(() => setTick((n) => n + 1), 250);
    };
    const open = () => {
      es = new EventSource(API + '/api/stream/runs');
      es.onopen = () => setConnected(true);
      es.onerror = () => { setConnected(false); if (es.readyState === 2 && !stopped) { timer = setTimeout(open, 2500); } };
      ['run_created', 'run_stage', 'run_completed', 'run_failed', 'run_cancelled', 'decision_overridden', 'demo_reset'].forEach((t) => {
        es.addEventListener(t, (e) => { let d = null; try { d = JSON.parse(e.data); } catch { /* ignore */ } bump(t, d); });
      });
    };
    open();
    return () => { stopped = true; clearTimeout(timer); clearTimeout(debounce); es && es.close(); };
  }, []);

  const queue = useApi('/api/review-queue?tab=review', { tick, deps: [roleTick] });
  const openCount = queue.data ? queue.data.open_exceptions : null;
  useEffect(() => { setRailOpen(false); }, [path]);
  useEffect(() => { setCrumb(null); }, [path]);
  useEffect(() => {
    const h = (e) => { if (!e.target.closest('#demo-menu') && !e.target.closest('[data-demo-btn]')) setMenu(false); };
    document.addEventListener('click', h); return () => document.removeEventListener('click', h);
  }, []);

  const resetDemo = useCallback(async () => {
    setMenu(false);
    try {
      await api('/api/demo/reset', { method: 'POST' });
      toast('Demo data reset. History, master data and rules are back to the seeded state.');
      setTick((n) => n + 1);
      router.refresh();
      window.dispatchEvent(new Event('ll-reset'));
    } catch (e) { toast(e.message); }
  }, [toast, router]);

  const ctx = useMemo(() => ({ role, setRole, settings, setSettings, toast, tick, roleTick, connected, live, setCrumb, openCount, rememberRun, refreshQueue: queue.refresh }),
    [role, setRole, settings, setSettings, toast, tick, roleTick, connected, live, openCount, rememberRun, queue.refresh]);

  const key = activeKey(path);
  const crumbDefault = (NAV.find((n) => n[3] === key) || [])[1] || (key === 's4' ? 'Invoice decision' : 'Dashboard');

  return (
    <AppCtx.Provider value={ctx}>
      <div className="app">
        <aside className={`rail ${railOpen ? 'open' : ''}`} id="rail" aria-label="Main navigation">
          <div className="brand">{LOGO}Ledgerlight</div>
          <nav className="nav" id="nav">
            {NAV.map(([href, name, icon, k]) => {
              const to = k === 's3' ? lastRunRoute : href;
              return (
                <Link key={k} href={k === 's3' ? to : href} data-nav={k} className={key === k || (k === 's3' && key === 's4' && false) ? 'on' : ''}>
                  <Ic n={icon} /><span>{name}</span>
                  {k === 's5' && openCount != null ? <span className="badge" id="nav-badge" data-testid="nav-badge">{openCount}</span> : null}
                </Link>
              );
            })}
          </nav>
          <div className="rail-label">Demo cases</div>
          <nav className="nav" id="nav-ec">
            {EC_NAV.map(([sid, c, n]) => (
              <Link key={sid} href={`/new?focus=${sid}`}><span className="mono" style={{ fontSize: 11, opacity: 0.7, width: 24 }}>{c}</span><span>{n}</span></Link>
            ))}
          </nav>
          <div className="rail-foot">
            <div className="row gap-s" data-testid="conn-indicator"><span className={`live-dot ${connected ? '' : 'off'}`} /><span>{connected ? 'Live stream connected' : 'Reconnecting to the server'}</span></div>
            <div className="tiny">All names, vendors and bank accounts are fictional. Sample data as of 16 Nov 2026.</div>
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <button className="icon-btn menu-btn" onClick={() => setRailOpen((o) => !o)} aria-label="Open navigation"><Ic n="menu" /></button>
            <div className="crumb" id="crumb">{crumb || crumbDefault}</div>
            <div className="row right gap-s">
              <div className="seg role-seg" role="group" aria-label="Role switcher">
                {Object.entries(ROLES).map(([k, r]) => (
                  <button key={k} data-testid={`role-${k}`} aria-pressed={role === k} onClick={() => setRole(k)}>{r.label}</button>
                ))}
              </div>
              <div style={{ position: 'relative' }}>
                <button className="btn sm" data-demo-btn aria-haspopup="true" onClick={() => setMenu((m) => !m)} data-testid="demo-menu-btn"><Ic n="sliders" c="sm" />Demo mode</button>
                <div className={`menu ${menu ? 'show' : ''}`} id="demo-menu">
                  <div><b>Demo mode</b><div className="small muted">Controls for presenting. Resetting wipes runs and the audit log back to the seeded state.</div></div>
                  <button className="btn sm" onClick={resetDemo} data-testid="reset-demo"><Ic n="refresh" c="sm" />Reset demo data</button>
                  <label className="row"><button className="toggle" role="switch" aria-checked={settings.cache} aria-label="Use saved AI results" onClick={() => setSettings({ cache: !settings.cache })} /><span className="small">Use saved AI results</span></label>
                  <div><div className="small muted" style={{ marginBottom: 4 }}>Pacing speed</div>
                    <div className="seg">{[['slow', 'Slow'], ['normal', 'Normal'], ['fast', 'Fast']].map(([s, l]) => (
                      <button key={s} aria-pressed={settings.speed === s} onClick={() => setSettings({ speed: s })}>{l}</button>))}</div></div>
                </div>
              </div>
            </div>
          </header>
          <main className="page" id="view" tabIndex={-1}>{children}</main>
        </div>
      </div>
      {toastView}
      <TipLayer />
    </AppCtx.Provider>
  );
}
