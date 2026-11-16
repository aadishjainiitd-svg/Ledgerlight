// Opens the local prototype, visits every route, waits for the S3 animation, saves one PNG per route and prints a status line per route.
const { chromium } = require('playwright');
const path = require('path'), fs = require('fs');
const FILE = 'file:///' + path.join(__dirname, 'ledgerlight.preview.html').split(path.sep).join('/');
const OUT = path.join(__dirname, 'screenshots'); fs.mkdirSync(OUT, { recursive: true });
const ROUTES = [
  ['s1', 'S1 Dashboard', 'h1:has-text("Dashboard")', '#runs-card tbody tr'],
  ['s2', 'S2 New run', 'h1:has-text("New run")', '.samples .sample'],
  ['s3', 'S3 Live run view', '#run-head', '.stage'],
  ['s4-ec1', 'S4 EC1 Kestrel split PO', '#dcard h2', '.cum .track'],
  ['s4-ec2', 'S4 EC2 Brightline duplicate', '#dcard h2', '.sbs .doc.orig'],
  ['s4-ec3', 'S4 EC3 Greenleaf scan', '#dcard h2', '.cand.win'],
  ['s4-ec4', 'S4 EC4 Corevolt bank change', '#dcard h2', '.bank-cmp .b.bad'],
  ['s5', 'S5 Review queue', 'h1:has-text("Review queue")', '.qrow'],
  ['s6', 'S6 PO and vendor master data', 'h1:has-text("Purchase orders")', 'table.tbl tbody tr'],
  ['s7', 'S7 Rules and tolerances', 'h1:has-text("Rules and tolerances")', '.rule-row'],
  ['s8', 'S8 Audit log', 'h1:has-text("Audit log")', 'tr.audit-row'],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
  const page = await ctx.newPage(); const errs = []; const netfail = [];
  page.on('console', m => { if (m.type() === 'error') { const t = m.text(); (/Failed to load resource|ERR_/.test(t) ? netfail : errs).push(t); } });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  let bad = 0;
  console.log('route | screen | key element | console errors');
  for (const [route, label, head, key] of ROUTES) {
    const before = errs.length;
    await page.goto(FILE + '#' + route); await page.reload(); // fresh run each time
    await page.waitForSelector(head, { timeout: 8000 }).catch(() => { });
    if (route === 's3') { await page.waitForSelector('body[data-s3="done"]', { timeout: 40000 }).catch(() => { }); await page.waitForTimeout(900); }
    else await page.waitForTimeout(450);
    const has = await page.locator(head).count() > 0, n = await page.locator(key).count();
    let extra = '';
    if (route === 's3') { const done = await page.locator('.stage.done').count(); const shown = await page.locator('#decide.show').count(); extra = ` stages done ${done}/9, decision card ${shown ? 'shown' : 'MISSING'}`; if (done !== 9 || !shown) bad++; }
    if (route.startsWith('s4')) extra = ' "' + ((await page.locator('#dcard h2').first().innerText()).slice(0, 60)) + '..."';
    await page.screenshot({ path: path.join(OUT, route.replace(/^s(\d)/, 'S$1') + '.png'), fullPage: true });
    const ec = errs.length - before; if (!has || !n || ec) bad++;
    console.log(`#${route} | ${label} | heading ${has ? 'present' : 'MISSING'}, key element x${n}${extra} | ${ec}`);
  }
  // interaction smoke test: S2 sample click leads to S3 then S4
  await page.goto(FILE + '#s2'); await page.reload(); await page.click('button[data-k="si03"]');
  await page.waitForSelector('body[data-s3="done"]', { timeout: 40000 }); await page.click('#decide a.btn'); await page.waitForSelector('#dcard h2');
  console.log('flow S2 -> S3 -> S4: ' + (page.url().endsWith('#s4-si03') ? 'ok' : 'FAILED ' + page.url()));
  // dark + mobile extras
  const dctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' }); const dp = await dctx.newPage(); dp.on('pageerror', e => errs.push('dark pageerror: ' + e.message));
  for (const r of ['s1', 's4-ec1', 's7']) { await dp.goto(FILE + '#' + r); await dp.reload(); await dp.waitForTimeout(700); await dp.screenshot({ path: path.join(OUT, 'dark_' + r + '.png'), fullPage: true }); }
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2, colorScheme: 'light' }); const mp = await mctx.newPage(); mp.on('pageerror', e => errs.push('mobile pageerror: ' + e.message));
  for (const r of ['s1', 's2', 's3', 's4-ec4', 's5', 's6', 's7', 's8']) {
    await mp.goto(FILE + '#' + r); await mp.reload(); await mp.waitForTimeout(r === 's3' ? 6000 : 600);
    const ov = await mp.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }));
    await mp.screenshot({ path: path.join(OUT, 'mobile_' + r + '.png'), fullPage: true });
    console.log(`mobile #${r}: scrollWidth ${ov.sw} vs viewport ${ov.iw} ${ov.sw > ov.iw ? 'OVERFLOW' : 'ok'}`);
  }
  console.log(`total console errors: ${errs.length}${errs.length ? ' -> ' + errs.slice(0, 5).join(' || ') : ''}; blocked network loads (fonts, offline sandbox): ${netfail.length}`);
  await browser.close(); process.exit(bad || errs.length ? 1 : 0);
})();
