/* ===== Shell, router, boot ===== */
const S = { role: 'clerk', theme: 'auto' };
const NAV = [
  ['s1', 'Dashboard', 'dash', '#s1'], ['s2', 'New run', 'upload', '#s2'], ['s3', 'Live run', 'bolt', '#s3'], ['s4', 'Invoice decision', 'check-circle', '#s4-ec1'],
  ['s5', 'Review queue', 'queue', '#s5'], ['s6', 'Purchase orders and vendors', 'db', '#s6'], ['s7', 'Rules and tolerances', 'sliders', '#s7'], ['s8', 'Audit log', 'scroll', '#s8'],
];
const EC_NAV = [['ec1', 'EC1', 'Kestrel, split PO'], ['ec2', 'EC2', 'Brightline, duplicate'], ['ec3', 'EC3', 'Greenleaf, blurry scan'], ['ec4', 'EC4', 'Corevolt, bank change']];
const LOGO = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#2c55d9"/><path d="M9 22V10m0 12h14" stroke="#fff" stroke-width="2.6" stroke-linecap="round" fill="none"/><path d="M13 18l3-3 3 2 4-5" stroke="#9ff0c5" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`;

function shell() {
  $('#root').innerHTML = `<div class="app">
  <aside class="rail" id="rail" aria-label="Main navigation"><div class="brand">${LOGO}Ledgerlight</div>
    <nav class="nav" id="nav">${NAV.map(([k, n, i, h]) => `<a href="${h}" data-nav="${k}">${ic(i)}<span>${n}</span>${k === 's5' ? `<span class="badge" id="nav-badge">${openExcCount()}</span>` : ''}</a>`).join('')}</nav>
    <div class="rail-label">Demo cases</div><nav class="nav" id="nav-ec">${EC_NAV.map(([k, c, n]) => `<a href="#s4-${k}" data-ec="${k}"><span class="mono" style="font-size:11px;opacity:.7;width:24px">${c}</span><span>${n}</span></a>`).join('')}</nav>
    <div class="rail-foot"><div class="row gap-s"><span class="live-dot"></span><span>Live stream connected</span></div><div class="tiny">All names, vendors and bank accounts are fictional. Sample data as of 16 Nov 2026.</div></div></aside>
  <div class="main"><header class="topbar"><button class="icon-btn menu-btn" data-act="menu" aria-label="Open navigation">${ic('menu')}</button><div class="crumb" id="crumb">Dashboard</div>
    <div class="row right gap-s"><div class="seg role-seg" role="group" aria-label="Role switcher">${Object.entries(ROLES).map(([k, r]) => `<button data-act="role" data-r="${k}" aria-pressed="${S.role === k}">${r.label}</button>`).join('')}</div>
      <div style="position:relative"><button class="btn sm" data-act="demoMenu" aria-haspopup="true">${ic('sliders', 'sm')}Demo mode</button><div class="menu" id="demo-menu"><div><b>Demo mode</b><div class="small muted">Controls for presenting. Nothing here changes real data.</div></div><button class="btn sm" data-act="resetDemo">${ic('refresh', 'sm')}Reset demo data</button><label class="row"><button class="toggle" role="switch" aria-checked="${STATE2.opts.cache}" data-act="optCache2" aria-label="Use saved AI results"></button><span class="small">Use saved AI results</span></label><div><div class="small muted" style="margin-bottom:4px">Pacing speed</div><div class="seg">${[['0.5', 'Slow'], ['1', 'Normal'], ['2', 'Fast']].map(([s, l]) => `<button data-act="pace2" data-s="${s}" aria-pressed="${RUN.speed === +s}">${l}</button>`).join('')}</div></div></div></div>
      <button class="icon-btn" data-act="theme" id="theme-btn" aria-label="Switch colour theme" data-tip="Switch colour theme">${ic('moon')}</button></div></header>
    <main class="page" id="view" tabindex="-1"></main></div></div>`;
}
const ROUTES = { s1: [renderS1, s1After], s2: [renderS2, s2After], s3: [renderS3, s3After], s4: [renderS4, null], s5: [renderS5, null], s6: [renderS6, s6After], s7: [renderS7, s7After], s8: [renderS8, s8After] };
function parseHash() { const m = (location.hash.slice(1) || 's1').match(/^(s[1-8])(?:-([a-z0-9]+))?$/i); return m ? { s: m[1].toLowerCase(), arg: (m[2] || '').toLowerCase() } : { s: 's1', arg: '' }; }
let LAST = '';
function route(keep) {
  const { s, arg } = parseHash(), id = s + '-' + arg;
  if (keep && s === 's3') return;
  const y = window.scrollY; clearInterval(S1_TIMER); if (s !== 's3') { stopRun(); document.body.dataset.s3 = ''; }
  if (!keep) { closeSheet(true); closeModal(true); }
  const [render, after] = ROUTES[s]; $('#view').innerHTML = render(arg); document.body.dataset.route = s + (arg ? '-' + arg : ''); if (after) after(arg);
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === s)); $$('#nav-ec a').forEach(a => a.classList.toggle('on', s === 's4' && (a.dataset.ec === arg || ALIAS[a.dataset.ec] === arg)));
  const inv = INV[arg] || INV[ALIAS[arg]]; const name = NAV.find(n => n[0] === s)[1];
  $('#crumb').innerHTML = s === 's4' && inv ? `<span class="muted">Invoice decision</span>${ic('chev-r', 'sm')}${esc(inv.vname)} ${esc(inv.invNo)}` : s === 's3' ? `<span class="muted">Live run</span>${ic('chev-r', 'sm')}${esc((INV[arg] || INV.si05).file)}` : name;
  $('#rail').classList.remove('open'); updateNavBadge();
  if (keep) window.scrollTo(0, y); else { window.scrollTo(0, 0); }
  LAST = id;
}
window.addEventListener('hashchange', () => route(false));
ACT.role = t => { S.role = t.dataset.r; $$('.role-seg button').forEach(b => b.setAttribute('aria-pressed', String(b === t))); if (parseHash().s !== 's3') route(true); toast(`Now acting as ${ROLES[S.role].label}, ${ROLES[S.role].name}.`); };
ACT.menu = () => $('#rail').classList.toggle('open');
ACT.demoMenu = () => $('#demo-menu').classList.toggle('show');
ACT.optCache2 = t => { STATE2.opts.cache = !STATE2.opts.cache; t.setAttribute('aria-checked', STATE2.opts.cache); };
ACT.pace2 = t => { RUN.speed = +t.dataset.s; $$('[data-act="pace2"]').forEach(b => b.setAttribute('aria-pressed', String(b === t))); $$('[data-act="pace"]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.s === RUN.speed))); };
ACT.resetDemo = () => { $('#demo-menu').classList.remove('show'); RUNS.forEach(r => { delete r.resolved; delete r.confirmedBy; }); toast('Demo data reset. History, master data and rules are back to the seeded state.'); route(true); updateNavBadge(); };
ACT.theme = () => {
  const order = ['auto', 'light', 'dark']; S.theme = order[(order.indexOf(S.theme) + 1) % 3]; applyTheme();
  try { localStorage.setItem('ll-theme', S.theme); } catch (e) { }
};
function applyTheme() {
  const r = document.documentElement; if (S.theme === 'auto') r.removeAttribute('data-theme'); else r.dataset.theme = S.theme;
  const b = $('#theme-btn'); if (b) { b.innerHTML = ic(S.theme === 'dark' ? 'sun' : 'moon'); b.dataset.tip = 'Theme: ' + S.theme; }
}
document.addEventListener('click', e => { if (!e.target.closest('#demo-menu') && !e.target.closest('[data-act="demoMenu"]')) { const m = $('#demo-menu'); if (m) m.classList.remove('show'); } if (innerWidth <= 900 && !e.target.closest('#rail') && !e.target.closest('[data-act="menu"]')) { const r = $('#rail'); if (r) r.classList.remove('open'); } });
document.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.qrow')) { e.preventDefault(); e.target.click(); } });

/* boot */
try { const t = localStorage.getItem('ll-theme'); if (t) S.theme = t; } catch (e) { }
shell(); applyTheme(); route(false);
window.__ledgerlight = { ready: true };
