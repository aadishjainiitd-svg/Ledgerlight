/* ===== UI helpers ===== */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const sleepRaw = ms => new Promise(r => setTimeout(r, ms));

const ICONS = {
  'check': '<path d="M20 6 9 17l-5-5"/>',
  'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 3 3 5-6"/>',
  'note-circle': '<circle cx="11" cy="13" r="8"/><path d="m7.5 13 2.5 2.5 4.5-5"/><circle cx="19" cy="5" r="2.4" fill="currentColor" stroke="none"/>',
  'x-circle': '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  'x': '<path d="M18 6 6 18M6 6l12 12"/>',
  'eye': '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  'pause-circle': '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
  'spinner': '<path d="M12 3a9 9 0 1 0 9 9" />',
  'warn': '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  'dash': '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  'upload': '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  'queue': '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  'db': '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  'sliders': '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  'scroll': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h6"/>',
  'search': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  'chev-r': '<path d="m9 6 6 6-6 6"/>', 'chev-d': '<path d="m6 9 6 6 6-6"/>', 'chev-l': '<path d="m15 6-6 6 6 6"/>', 'chev-u': '<path d="m6 15 6-6 6 6"/>',
  'arrow-r': '<path d="M5 12h14M13 6l6 6-6 6"/>', 'arrow-l': '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  'download': '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
  'copy': '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  'edit': '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/>',
  'user': '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
  'cpu': '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  'gear': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  'link': '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  'refresh': '<path d="M20 11a8 8 0 0 0-14.3-4M4 4v4h4M4 13a8 8 0 0 0 14.3 4M20 20v-4h-4"/>',
  'plus': '<path d="M12 5v14M5 12h14"/>',
  'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  'moon': '<path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z"/>',
  'menu': '<path d="M4 6h16M4 12h16M4 18h16"/>',
  'filter': '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
  'mail': '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  'shield': '<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  'lock': '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  'file': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
  'phone': '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  'play': '<path d="m6 4 14 8-14 8z"/>', 'cancel': '<circle cx="12" cy="12" r="9"/><path d="M8 8l8 8"/>',
  'zoom': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>',
  'rotate': '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
  'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  'bolt': '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  'undo': '<path d="M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3"/>',
  'tag': '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>',
  'pin': '<path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/>',
  'grid': '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
  'list': '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
};
const ic = (n, c = '') => `<svg class="ic ${c}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;

const chip = (k, lg) => k === 'running' ? `<span class="chip s-running ${lg ? 'lg' : ''}">${ic('spinner', 'spin')}Running</span>` : `<span class="chip s-${k} ${lg ? 'lg' : ''}">${ic(OUT[k].ic)}${OUT[k].label}</span>`;
const confClass = c => c == null ? 'na' : c >= 0.90 ? 'hi' : c >= 0.75 ? 'mid' : 'lo';
const confChip = (c, extra = '') => `<span class="conf ${confClass(c)}" title="Confidence ${c == null ? 'not applicable' : c.toFixed(2)}">${c == null ? 'n/a' : c.toFixed(2)}${extra}</span>`;
const sevIcon = s => ({ pass: ic('check-circle', 'c-pass'), note: ic('note-circle', 'c-note'), review: ic('eye', 'c-review'), hold: ic('pause-circle', 'c-hold'), reject: ic('x-circle', 'c-reject') }[s]);
const sevChip = s => s === 'pass' ? `<span class="chip s-pass">${ic('check-circle')}Pass</span>` : `<span class="chip s-${s === 'note' ? 'note' : s}">${ic(OUT[s === 'note' ? 'note' : s].ic)}${({ note: 'Note', review: 'Review', hold: 'Hold', reject: 'Reject' })[s]}</span>`;
const SEVRANK = { pass: 0, note: 1, review: 2, hold: 3, reject: 4 };
const SEV2OUT = { pass: 'auto', note: 'note', review: 'review', hold: 'hold', reject: 'reject' };
const worst = arr => arr.reduce((m, s) => SEVRANK[s] > SEVRANK[m] ? s : m, 'pass');

/* tooltips and popovers */
let tipEl, popEl;
function ensureFloaters() {
  if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'tip'; tipEl.setAttribute('role', 'tooltip'); document.body.appendChild(tipEl); }
  if (!popEl) { popEl = document.createElement('div'); popEl.className = 'pop'; document.body.appendChild(popEl); }
}
function placeFloat(el, x, y, pad = 14) {
  const w = el.offsetWidth, h = el.offsetHeight; let left = x + pad, top = y + pad;
  if (left + w > innerWidth - 8) left = x - w - pad; if (left < 8) left = 8;
  if (top + h > innerHeight - 8) top = y - h - pad; if (top < 8) top = 8;
  el.style.left = left + 'px'; el.style.top = top + 'px';
}
document.addEventListener('mousemove', e => {
  ensureFloaters();
  const t = e.target.closest ? e.target.closest('[data-tip]') : null;
  if (t) { tipEl.innerHTML = t.dataset.tip; tipEl.classList.add('show'); placeFloat(tipEl, e.clientX, e.clientY); } else tipEl.classList.remove('show');
  const p = e.target.closest ? e.target.closest('[data-pop]') : null;
  if (p) { popEl.innerHTML = p.dataset.pop; popEl.classList.add('show'); placeFloat(popEl, e.clientX, e.clientY, 18); } else popEl.classList.remove('show');
});
document.addEventListener('scroll', () => { tipEl && tipEl.classList.remove('show'); popEl && popEl.classList.remove('show'); }, true);

/* toasts */
function toast(msg, undo) {
  let c = $('.toasts'); if (!c) { c = document.createElement('div'); c.className = 'toasts'; c.setAttribute('role', 'status'); c.setAttribute('aria-live', 'polite'); document.body.appendChild(c); }
  const t = document.createElement('div'); t.className = 'toast';
  t.innerHTML = `<span>${msg}</span>${undo ? '<button data-undo>Undo</button>' : ''}`;
  c.appendChild(t);
  const kill = () => t.remove(); const to = setTimeout(kill, undo ? 10000 : 4200);
  if (undo) $('[data-undo]', t).onclick = () => { clearTimeout(to); kill(); undo(); };
}
function copyText(txt, label) {
  const done = () => toast((label || 'Text') + ' copied to the clipboard');
  try { navigator.clipboard.writeText(txt).then(done, () => { fallbackCopy(txt); done(); }); } catch (e) { fallbackCopy(txt); done(); }
}
function fallbackCopy(txt) { const ta = document.createElement('textarea'); ta.value = txt; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) { } ta.remove(); }

/* sheet and modal containers */
function openSheet(html, wide) {
  closeSheet(true);
  const sc = document.createElement('div'); sc.className = 'scrim'; sc.id = 'scrim'; sc.onclick = () => closeSheet();
  const sh = document.createElement('aside'); sh.className = 'sheet' + (wide ? ' wide' : ''); sh.id = 'sheet'; sh.setAttribute('role', 'dialog'); sh.setAttribute('aria-modal', 'true'); sh.innerHTML = html;
  document.body.append(sc, sh); requestAnimationFrame(() => { sc.classList.add('show'); sh.classList.add('show'); });
  return sh;
}
function closeSheet(now) {
  const sc = $('#scrim'), sh = $('#sheet'); if (!sh) return;
  sc.classList.remove('show'); sh.classList.remove('show');
  const rm = () => { sc.remove(); sh.remove(); }; now ? rm() : setTimeout(rm, 260);
}
function openModal(html) {
  closeModal(true);
  const sc = document.createElement('div'); sc.className = 'scrim'; sc.id = 'mscrim'; sc.onclick = () => closeModal();
  const m = document.createElement('div'); m.className = 'modal'; m.id = 'modal'; m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true'); m.innerHTML = html;
  document.body.append(sc, m); requestAnimationFrame(() => { sc.classList.add('show'); m.classList.add('show'); });
}
function closeModal(now) { const sc = $('#mscrim'), m = $('#modal'); if (!m) return; sc.classList.remove('show'); m.classList.remove('show'); const rm = () => { sc.remove(); m.remove(); }; now ? rm() : setTimeout(rm, 220); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeSheet(); closeModal(); } });

/* delegated actions */
const ACT = {};
document.addEventListener('click', e => {
  const t = e.target.closest('[data-act]'); if (!t) return;
  const a = ACT[t.dataset.act]; if (a) { if (t.tagName === 'A' && !t.getAttribute('href')) e.preventDefault(); a(t, e); }
});

/* layout atoms */
const pageHead = (title, sub, right = '') => `<div class="page-head"><div class="grow"><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ''}</div><div class="row wrap">${right}</div></div>`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sum = a => a.reduce((s, x) => s + x, 0);
const median = a => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : 0; };
const pct = (n, d = 1) => (Math.round(n * Math.pow(10, d)) / Math.pow(10, d)).toFixed(d) + '%';
const dayAge = d => Math.max(0, Math.round((TODAY - d) / 86400000));
