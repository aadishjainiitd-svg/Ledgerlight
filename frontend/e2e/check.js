/* End-to-end check for Ledgerlight:  npm run check
   Works from cold: if the backend (API_URL) or the frontend (FRONTEND_URL) is not answering, this script starts it
   (backend with the repo's .venv, frontend with `next start`, building first if .next is missing or stale) and stops
   only what it started when it finishes. Servers that are already up are reused and left running.
   Env: FRONTEND_URL (default http://127.0.0.1:3000), API_URL (default http://127.0.0.1:8010) */
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { chromium } = require('playwright');

const FRONT = (process.env.FRONTEND_URL || 'http://127.0.0.1:3000').replace(/\/$/, '');
const API = (process.env.API_URL || 'http://127.0.0.1:8010').replace(/\/$/, '');
const SHOTS = path.join(__dirname, 'screenshots');
const ROOT = path.join(__dirname, '..', '..');
const expected = JSON.parse(fs.readFileSync(path.join(ROOT, 'samples', 'expected.json'), 'utf8')).samples;
const LABEL = { auto_approve: 'Approved', approve_with_note: 'Approved, note', route_for_review: 'Needs review', hold_request_info: 'On hold', reject: 'Rejected' };

const rows = []; // [section, check, result, detail]
const record = (section, check, ok, detail = '') => { rows.push([section, check, ok ? 'PASS' : 'FAIL', String(detail)]); return ok; };
const consoleErrors = [];

async function api(p, opts) { const r = await fetch(API + p, opts); return r.json(); }

/* ---------- start / stop the servers ---------- */
const FRONTEND_DIR = path.join(__dirname, '..');
const BACKEND_DIR = path.join(ROOT, 'backend');
const LOGS = path.join(FRONTEND_DIR, '.logs');
const started = []; // child processes this run started
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isUp = async (url) => { try { const r = await fetch(url, { signal: AbortSignal.timeout(3000) }); return r.status < 500; } catch { return false; } };
async function waitUp(url, seconds, what) {
  const until = Date.now() + seconds * 1000;
  while (Date.now() < until) { if (await isUp(url)) return; await sleep(500); }
  throw new Error(`${what} did not come up at ${url} within ${seconds}s (see ${LOGS})`);
}
function spawnLogged(cmd, args, cwd, name, env) {
  fs.mkdirSync(LOGS, { recursive: true });
  const out = fs.openSync(path.join(LOGS, `${name}.out.log`), 'w');
  const err = fs.openSync(path.join(LOGS, `${name}.err.log`), 'w');
  const child = spawn(cmd, args, { cwd, stdio: ['ignore', out, err], windowsHide: true, env: { ...process.env, ...(env || {}) } });
  child.on('error', (e) => console.error(`could not start ${name}: ${e.message}`));
  started.push(child);
  return child;
}
function stopStarted() {
  for (const c of started.splice(0)) {
    if (!c.pid || c.exitCode !== null) continue;
    try { if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(c.pid), '/T', '/F'], { stdio: 'ignore' }); else process.kill(c.pid, 'SIGTERM'); } catch { /* already gone */ }
  }
}
function newestMtime(p) {
  let t = 0; if (!fs.existsSync(p)) return t;
  const st = fs.statSync(p); if (!st.isDirectory()) return st.mtimeMs;
  for (const f of fs.readdirSync(p)) { if (f === 'node_modules' || f === '.next' || f === '.logs' || f === 'e2e') continue; t = Math.max(t, newestMtime(path.join(p, f))); }
  return t;
}
async function ensureServers() {
  const apiUrl = new URL(API); const frontUrl = new URL(FRONT);
  if (await isUp(`${API}/api/health`)) console.log(`backend already running at ${API} (reusing it)`);
  else {
    const py = process.platform === 'win32' ? path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe') : path.join(BACKEND_DIR, '.venv', 'bin', 'python');
    if (!fs.existsSync(py)) throw new Error(`backend virtualenv not found at ${py}. Run start.ps1 (repo root) once to create it.`);
    console.log(`starting backend on ${API} ...`);
    spawnLogged(py, ['-m', 'uvicorn', 'app.main:app', '--host', apiUrl.hostname, '--port', apiUrl.port || '80'], BACKEND_DIR, 'check-backend');
    await waitUp(`${API}/api/health`, 60, 'the backend');
  }
  if (await isUp(FRONT + '/')) console.log(`frontend already running at ${FRONT} (reusing it)`);
  else {
    const buildId = path.join(FRONTEND_DIR, '.next', 'BUILD_ID');
    const srcNewest = Math.max(...['app', 'components', 'lib', 'pages', 'public', 'next.config.mjs', 'package.json', 'package-lock.json', 'tailwind.config.js', 'postcss.config.js'].map((f) => newestMtime(path.join(FRONTEND_DIR, f))));
    const stale = !fs.existsSync(buildId) || fs.statSync(buildId).mtimeMs < srcNewest;
    if (stale) {
      console.log('building the frontend (npm run build) ...');
      fs.mkdirSync(LOGS, { recursive: true });
      const b = spawnSync('npm run build', { cwd: FRONTEND_DIR, shell: true, encoding: 'utf8', env: { ...process.env, NEXT_PUBLIC_API_BASE: API } });
      fs.writeFileSync(path.join(LOGS, 'check-build.log'), (b.stdout || '') + (b.stderr || ''));
      if (b.status !== 0) throw new Error(`frontend build failed, see ${path.join(LOGS, 'check-build.log')}`);
    }
    console.log(`starting frontend on ${FRONT} ...`);
    spawnLogged(process.execPath, [path.join(FRONTEND_DIR, 'node_modules', 'next', 'dist', 'bin', 'next'), 'start', '-p', frontUrl.port || '3000', '-H', frontUrl.hostname], FRONTEND_DIR, 'check-frontend');
    await waitUp(FRONT + '/', 90, 'the frontend');
  }
}
process.on('exit', stopStarted);
process.on('SIGINT', () => { stopStarted(); process.exit(130); });

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  await ensureServers();
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const u = (m.location() && m.location().url) || '';
    if (/fonts\.(googleapis|gstatic)\.com/.test(u)) return; // web fonts are optional (system fallbacks)
    consoleErrors.push(`${m.text()} ${u}`.slice(0, 240));
  });

  /* (a) reset the demo data */
  const health = await api('/api/health');
  const reset = await api('/api/demo/reset', { method: 'POST' });
  record('a', 'demo reset', reset.runs === 60 && reset.open_exceptions === 14, `runs=${reset.runs}, open exceptions=${reset.open_exceptions}, extraction=${health.extraction_mode}`);

  /* (c) every sample, end to end: S2 -> S3 (live events) -> S4 */
  const runIds = {};
  for (const s of expected) {
    const tag = `c ${s.id}`;
    await page.goto(`${FRONT}/new`, { waitUntil: 'load' });
    await page.waitForSelector(`[data-testid="run-${s.id}"]`);
    if (s.id === 'SI-01') await page.screenshot({ path: path.join(SHOTS, 'S2.png'), fullPage: true });
    await page.click(`[data-testid="run-${s.id}"]`);
    await page.waitForURL(/\/runs\/run_/, { timeout: 15000 });
    const runId = page.url().split('/runs/')[1];
    runIds[s.id] = runId;

    // watch the stages light up from live events
    const seenRunning = new Set(); const seenDone = new Set(); let firstLog = null; let sawLive = false; let shot = false;
    const t0 = Date.now(); let state = '';
    while (Date.now() - t0 < 90000) {
      const snap = await page.evaluate(() => ({
        st: [...document.querySelectorAll('[data-testid^="stage-"]')].map((e) => e.dataset.status),
        state: (document.querySelector('[data-testid="live-run"]') || {}).dataset && document.querySelector('[data-testid="live-run"]').dataset.runState,
        logs: (document.querySelector('[data-testid="log-count"]') || {}).textContent || '',
        chip: (document.querySelector('[data-testid="conn-chip"]') || {}).dataset && document.querySelector('[data-testid="conn-chip"]').dataset.state,
      }));
      snap.st.forEach((v, i) => { if (v === 'running') seenRunning.add(i + 1); if (v === 'done' || v === 'skipped') seenDone.add(i + 1); });
      if (snap.chip === 'live') sawLive = true;
      if (firstLog === null && /^[1-9]/.test(snap.logs)) firstLog = parseInt(snap.logs, 10);
      if (!shot && s.id === 'SI-03' && seenRunning.has(6)) { await page.screenshot({ path: path.join(SHOTS, 'S3-running.png') }); shot = true; }
      state = snap.state;
      if (state === 'completed' || state === 'failed' || state === 'cancelled') break;
      await page.waitForTimeout(120);
    }
    const finalSt = await page.evaluate(() => [...document.querySelectorAll('[data-testid^="stage-"]')].map((e) => e.dataset.status));
    const finalLogs = parseInt(await page.textContent('[data-testid="log-count"]'), 10);
    const nine = finalSt.length === 9 && finalSt.every((v) => v === 'done' || v === 'skipped');
    record(tag, 'S3 live: all 9 stages complete', state === 'completed' && nine, `state=${state}, stages=${finalSt.filter((v) => v === 'done').length} done/${finalSt.filter((v) => v === 'skipped').length} skipped, saw ${seenRunning.size} stages running live, ${finalLogs} log events (first poll ${firstLog})`);
    record(tag, 'S3 events arrived progressively', sawLive && seenRunning.size >= 6 && firstLog !== null && firstLog < finalLogs, `live chip=${sawLive}`);
    const dOutcome = await page.getAttribute('[data-testid="decision-card"]', 'data-outcome');
    if (s.id === 'SI-01') await page.screenshot({ path: path.join(SHOTS, 'S3.png'), fullPage: true });
    if (s.id === 'SI-05' && health.extraction_mode === 'text-only') {
      record(tag, 'S3 shows graceful "needs AI extraction" notice', await page.isVisible('[data-testid="needs-ai-notice"]'), '');
      await page.screenshot({ path: path.join(SHOTS, 'S3-SI-05-needs-ai.png'), fullPage: true });
    }

    // S4
    await page.click('[data-testid="see-explanation"]');
    await page.waitForSelector('[data-testid="decision-card"] [data-testid="decision-chip"]');
    const chip = (await page.textContent('[data-testid="decision-chip"]')).trim();
    const want = s.id === 'SI-05' && health.extraction_mode === 'text-only' ? 'On hold' : LABEL[s.expected_outcome];
    record(tag, `S4 decision label = ${want}`, chip === want && dOutcome !== null, `got "${chip}" (expected.json: ${LABEL[s.expected_outcome]})`);
    const nRules = await page.locator('[data-testid="rule-row"]').count();
    await page.waitForSelector('[data-testid="pdf-page"]', { state: 'visible', timeout: 15000 }).catch(() => {});
    const hasPdf = await page.isVisible('[data-testid="pdf-page"]');
    record(tag, 'S4 PDF page + 16 rule results', nRules === 16 && hasPdf, `rules=${nRules}, pdf image=${hasPdf}`);
    if (s.id === 'SI-03') await page.screenshot({ path: path.join(SHOTS, 'S4.png'), fullPage: true });
    if (s.id === 'SI-05') await page.screenshot({ path: path.join(SHOTS, 'S4-SI-05.png'), fullPage: true });
  }

  /* (d) override with a reason, then find it in S8 */
  const reason = 'E2E check: vendor agreed to send a credit note';
  await page.goto(`${FRONT}/decision/${runIds['SI-03']}`, { waitUntil: 'load' });
  await page.waitForSelector('[data-testid="override-btn"]');
  await page.click('[data-testid="override-btn"]');
  await page.click('[data-testid="ov-reject"]');
  const submitDisabledBefore = await page.isDisabled('[data-testid="ov-submit"]');
  await page.selectOption('[data-testid="ov-code"]', 'Credit note requested');
  await page.fill('[data-testid="ov-text"]', reason);
  const enabledAfter = !(await page.isDisabled('[data-testid="ov-submit"]'));
  await page.screenshot({ path: path.join(SHOTS, 'S4-override-sheet.png') });
  await page.click('[data-testid="ov-submit"]');
  await page.waitForSelector('[data-testid="override-banner"]', { timeout: 10000 });
  const banner = await page.textContent('[data-testid="override-banner"]');
  record('d', 'override needs a reason, then saves', submitDisabledBefore && enabledAfter && banner.includes('Credit note requested'), `submit disabled with no reason=${submitDisabledBefore}`);
  await page.goto(`${FRONT}/audit`, { waitUntil: 'load' });
  await page.selectOption('[data-testid="audit-event"]', 'decision_overridden');
  await page.waitForSelector('[data-testid="audit-row"][data-event="decision_overridden"]');
  const row = page.locator('[data-testid="audit-row"][data-event="decision_overridden"]').first();
  await row.click();
  const payloadText = await page.locator('tr.payload').first().textContent();
  const rowText = await row.textContent();
  record('d', 'override appears in S8 with before/after and reason', /K\/1241/.test(rowText) && payloadText.includes(reason), `row: ${rowText.replace(/\s+/g, ' ').slice(0, 110)}`);

  /* (b) visit S1..S8 and look for the key element on each */
  const tests = [
    ['S1', '/', async () => { await page.waitForSelector('[data-testid="runs-table"] [data-testid="run-row"]'); await page.waitForFunction(() => document.querySelectorAll('svg.chart').length >= 4, null, { timeout: 20000 }).catch(() => {}); const k = await page.locator('.kpis .kpi').count(); const c = await page.locator('svg.chart').count(); const r = await page.locator('[data-testid="run-row"]').count(); return [k === 6 && c >= 4 && r > 0, `${k} KPI tiles, ${c} charts, ${r} run rows`]; }],
    ['S2', '/new', async () => { await page.waitForSelector('[data-testid="sample-SI-07"]'); const n = await page.locator('[data-testid^="sample-SI-"]').count(); return [n === 7 && (await page.isVisible('[data-testid="dropzone"]')), `${n} sample cards + drop zone`]; }],
    ['S3', `/runs/${runIds['SI-03']}`, async () => { await page.waitForSelector('[data-testid="pipeline"]'); await page.waitForSelector('[data-testid="live-run"][data-run-state="completed"]', { timeout: 30000 }); const n = await page.locator('[data-testid^="stage-"]').count(); const l = parseInt(await page.textContent('[data-testid="log-count"]'), 10); return [n === 9 && l > 20, `${n} stage cards, ${l} log events (replayed from the stored stream)`]; }],
    ['S4', `/decision/${runIds['SI-02']}`, async () => { await page.waitForSelector('[data-testid="decision-card"]'); const n = await page.locator('[data-testid="rule-row"]').count(); return [n === 16 && (await page.isVisible('[data-testid="po-table"]')), `${n} rules, PO table visible`]; }],
    ['S5', '/queue', async () => { await page.waitForSelector('[data-testid="queue-row"]'); const n = await page.locator('[data-testid="queue-row"]').count(); await page.locator('[data-testid="queue-row"]').first().click(); await page.waitForSelector('[data-testid="quick-panel"]'); return [n > 0, `${n} exceptions in the Needs review tab, quick panel opens`]; }],
    ['S6', '/master', async () => { await page.waitForSelector('[data-testid="po-row"]'); const n = await page.locator('[data-testid="po-row"]').count(); await page.click('[data-testid="tab-vendors"]'); await page.waitForSelector('[data-testid="vendor-row"]'); const v = await page.locator('[data-testid="vendor-row"]').count(); await page.click('[data-testid="tab-po"]'); return [n > 0 && v > 0, `${n} POs, ${v} vendors`]; }],
    ['S7', '/rules', async () => { await page.waitForSelector('[data-testid="settings-rule"]'); const n = await page.locator('[data-testid="settings-rule"]').count(); return [n === 16, `${n} rules with plain-English sentences`]; }],
    ['S8', '/audit', async () => { await page.waitForSelector('[data-testid="audit-row"]'); const n = await page.locator('[data-testid="audit-row"]').count(); const t = await page.textContent('body'); return [n > 0 && /cannot be edited or deleted/.test(t), `${n} rows, append-only notice`]; }],
  ];
  for (const [id, url, fn] of tests) {
    const before = consoleErrors.length;
    await page.goto(FRONT + url, { waitUntil: 'load' });
    let ok = false; let detail = '';
    try { [ok, detail] = await fn(); } catch (e) { detail = 'error: ' + e.message.split('\n')[0]; }
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SHOTS, `${id}.png`), fullPage: true });
    record('b', `${id} key element`, ok, `${detail}; console errors on page: ${consoleErrors.length - before}`);
  }
  record('b', 'console errors across the whole run', consoleErrors.length === 0, consoleErrors.length ? consoleErrors.slice(0, 3).join(' | ') : '0');

  /* (e) no dark theme shipped: scan every built CSS, JS and HTML file, plus what the server actually serves */
  const DARK = /prefers-color-scheme\s*:\s*dark|data-theme\s*=\s*["']?dark|\.dark\s*[{,]|color-scheme\s*:\s*dark/i;
  const nextDir = path.join(__dirname, '..', '.next');
  const walk = (d, out = []) => { if (!fs.existsSync(d)) return out; for (const f of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, f.name); if (f.isDirectory()) { if (f.name !== 'cache') walk(p, out); } else out.push(p); } return out; };
  const builtFiles = ['static', 'server'].flatMap((d) => walk(path.join(nextDir, d))).filter((f) => /\.(css|js|html|rsc|mjs)$/.test(f));
  const byExt = (e) => builtFiles.filter((f) => f.endsWith(e)).length;
  const darkBuilt = builtFiles.filter((f) => DARK.test(fs.readFileSync(f, 'utf8'))).map((f) => path.relative(nextDir, f));
  record('e', 'no dark-theme styles in built CSS, JS or HTML', byExt('.css') > 0 && byExt('.js') > 0 && byExt('.html') > 0 && darkBuilt.length === 0, `scanned ${byExt('.css')} css, ${byExt('.js')} js, ${byExt('.html')} html files; dark matches: ${darkBuilt.length}${darkBuilt.length ? ' (' + darkBuilt.slice(0, 3).join(', ') + ')' : ''}`);
  const darkServed = []; let servedN = 0;
  for (const u of ['/', '/new', '/audit', '/nope-not-a-page']) {
    const html = await (await fetch(FRONT + u)).text(); servedN++;
    if (DARK.test(html)) darkServed.push(u + ' (html)');
    for (const m of html.matchAll(/(?:href|src)="([^"]+\.(?:css|js)[^"]*)"/g)) { const l = m[1]; if (/^https?:/.test(l) && !l.startsWith(FRONT)) continue; const t = await (await fetch(l.startsWith('http') ? l : FRONT + l)).text(); servedN++; if (DARK.test(t)) darkServed.push(l); }
  }
  record('e', 'no dark-theme styles in served pages, CSS and JS', darkServed.length === 0, `${servedN} served resources; dark matches: ${darkServed.length}${darkServed.length ? ' (' + darkServed.slice(0, 3).join(', ') + ')' : ''}`);
  const hasToggle = await page.evaluate(() => !!document.querySelector('#theme-btn, [aria-label*="theme" i]'));
  record('e', 'no theme toggle in the UI', !hasToggle, '');

  /* (e2) a 404 page visit, even with the browser asking for dark mode, stays light and on brand */
  {
    const dctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
    const p404 = await dctx.newPage();
    const resp = await p404.goto(`${FRONT}/nope`, { waitUntil: 'load' });
    await p404.waitForSelector('[data-testid="not-found"]').catch(() => {});
    const info = await p404.evaluate(() => {
      const lum = (c) => { const m = c.match(/[\d.]+/g).map(Number); return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255; };
      const cs = getComputedStyle(document.body);
      return { bg: cs.backgroundColor, bgLum: lum(cs.backgroundColor), fg: cs.color, brand: !!document.querySelector('[data-testid="not-found"]') && /Ledgerlight/.test(document.body.innerText), text: (document.querySelector('[data-testid="not-found"] h1') || {}).textContent || '', darkRules: [...document.styleSheets].some((ss) => { try { return [...ss.cssRules].some((r) => r.media && /prefers-color-scheme:\s*dark/.test(r.media.mediaText)); } catch { return false; } }) || /prefers-color-scheme\s*:\s*dark/.test([...document.querySelectorAll('style')].map((x) => x.textContent).join('')) };
    });
    await p404.screenshot({ path: path.join(SHOTS, 'S404.png'), fullPage: true });
    record('e', 'GET /nope: 404 status, light on-brand page, no dark rules (browser asking for dark)', resp.status() === 404 && info.brand && info.bgLum > 0.85 && !info.darkRules, `status=${resp.status()}, body bg=${info.bg}, heading="${info.text}", dark rules in page=${info.darkRules}`);
    await dctx.close();
  }

  /* (f) layout: no clipped table columns at 1440 (they scroll inside their card when narrow); sidebar fills the page */
  {
    const measure = () => page.evaluate(() => {
      const wraps = [...document.querySelectorAll('.tbl-wrap')].filter((w) => w.offsetParent !== null);
      const cut = wraps.filter((w) => w.scrollWidth > w.clientWidth + 1).map((w) => `${(w.querySelector('table') || {}).className || 'table'} ${w.scrollWidth}>${w.clientWidth}`);
      const app = document.querySelector('.app'); const rail = document.querySelector('.rail');
      return { n: wraps.length, cut, pageOverflow: document.documentElement.scrollWidth - window.innerWidth, appH: app.offsetHeight, docH: document.documentElement.scrollHeight, bgImg: getComputedStyle(app).backgroundImage, railBg: getComputedStyle(rail).backgroundColor };
    });
    for (const [id, url, sel] of [['S3', `/runs/${runIds['SI-03']}`, '.lines-t'], ['S4', `/decision/${runIds['SI-02']}`, '[data-testid="po-table"]']]) {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(FRONT + url, { waitUntil: 'load' });
      await page.waitForSelector(sel, { timeout: 30000 });
      await page.waitForTimeout(600);
      const wide = await measure();
      record('f', `${id} tables: every column fully visible at 1440px`, wide.n > 0 && wide.cut.length === 0, `${wide.n} tables, clipped: ${wide.cut.length ? wide.cut.join('; ') : 'none'}`);
      record('f', `${id} sidebar background fills the full page height`, /gradient/.test(wide.bgImg) && wide.appH >= wide.docH - 1, `app ${wide.appH}px vs page ${wide.docH}px, rail ${wide.railBg}`);
      await page.setViewportSize({ width: 700, height: 900 });
      await page.waitForTimeout(500);
      const narrow = await measure();
      const scrolls = await page.evaluate((q) => { const t = document.querySelector(q); const w = t && t.closest('.tbl-wrap'); return !!w && getComputedStyle(w).overflowX === 'auto'; }, sel);
      record('f', `${id} tables scroll inside their card at 700px, page itself does not`, scrolls && narrow.pageOverflow <= 1, `table wrapper scrolls=${scrolls}, page overflow=${narrow.pageOverflow}px`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  }

  /* (g) reconnect: drop the stream mid-run, the page resumes with Last-Event-ID and loses nothing */
  {
    const p2 = await ctx.newPage();
    await p2.addInitScript(() => {
      const Orig = window.EventSource; let dropped = false; window.__urls = [];
      window.EventSource = function (url, o) {
        const es = new Orig(url, o); window.__urls.push(url);
        if (/\/runs\/run_[^/]+\/events/.test(url) && !dropped) { dropped = true; let n = 0; es.addEventListener('log', () => { if (++n === 12) { es.close(); setTimeout(() => es.onerror && es.onerror(new Event('error')), 50); } }); }
        return es;
      };
      window.EventSource.prototype = Orig.prototype;
    });
    await p2.goto(`${FRONT}/new`, { waitUntil: 'load' });
    await p2.click('[data-testid="run-SI-02"]');
    await p2.waitForURL(/\/runs\/run_/);
    const rid = p2.url().split('/runs/')[1];
    const chips = new Set(); const t1 = Date.now(); let st2 = '';
    while (Date.now() - t1 < 60000) { st2 = await p2.getAttribute('[data-testid="live-run"]', 'data-run-state').catch(() => ''); chips.add(await p2.getAttribute('[data-testid="conn-chip"]', 'data-state').catch(() => null)); if (st2 === 'completed') break; await p2.waitForTimeout(100); }
    const uiLogs = parseInt(await p2.textContent('[data-testid="log-count"]'), 10);
    // read the stored stream from the same sandbox as the browser (a backend without sandboxes ignores the id)
    const sb = await p2.evaluate(() => { try { return localStorage.getItem('ll-sandbox') || ''; } catch { return ''; } });
    const stored = ((await (await fetch(`${API}/api/runs/${rid}/events${sb ? `?sandbox=${sb}` : ''}`)).text()).match(/event: log/g) || []).length;
    const urls = await p2.evaluate(() => window.__urls);
    record('g', 'stream drop -> reconnecting -> resumes with last_event_id, no lost events', st2 === 'completed' && chips.has('reconnecting') && uiLogs === stored && urls.some((u) => /last_event_id=\d+/.test(u)), `states=${[...chips].join('>')}, UI log events ${uiLogs} = stored ${stored}`);
    await p2.close();
  }

  await browser.close();

  /* report */
  const w = [Math.max(...rows.map((r) => r[0].length), 3), Math.max(...rows.map((r) => r[1].length), 5)];
  console.log('\nLedgerlight e2e results');
  console.log('-'.repeat(120));
  rows.forEach((r) => console.log(`${r[2].padEnd(4)} | ${r[0].padEnd(w[0])} | ${r[1].padEnd(w[1])} | ${r[3]}`));
  console.log('-'.repeat(120));
  const fails = rows.filter((r) => r[2] === 'FAIL').length;
  stopStarted();
  console.log(`${rows.length - fails}/${rows.length} checks passed, ${consoleErrors.length} console errors. Screenshots: ${SHOTS}`);
  fs.writeFileSync(path.join(__dirname, 'results.json'), JSON.stringify({ rows, consoleErrors }, null, 2));
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); stopStarted(); process.exit(2); });
