const TZ = 'Asia/Kolkata';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Integer paise -> Indian-grouped rupees. */
export const inrP = (paise, d = 0) => inr((paise || 0) / 100, d);
export const inr = (n, d = 0) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
export const inrP2 = (paise) => inrP(paise, 2);
export const num = (n, d = 0) => Number(n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: d });

function parts(iso) {
  const d = new Date(iso);
  const f = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).formatToParts(d);
  const o = {}; f.forEach((p) => { o[p.type] = p.value; });
  return o;
}
export const fmtDS = (iso) => { if (!iso) return ''; const p = parts(iso); return `${p.day} ${p.month}`; };
export const fmtD = (iso) => { if (!iso) return ''; const p = parts(iso); return `${p.day} ${p.month} ${p.year}`; };
export const fmtT = (iso) => { if (!iso) return ''; const p = parts(iso); return `${p.hour}:${p.minute}`; };
export const fmtTS = (iso) => { if (!iso) return ''; const p = parts(iso); return `${p.hour}:${p.minute}:${p.second}`; };
export const fmtDT = (iso) => (iso ? `${fmtDS(iso)}, ${fmtT(iso)}` : '');
/** 'YYYY-MM-DD' -> '16 Nov 2026' */
export const fmtDay = (s) => { if (!s) return ''; const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return `${d} ${MON[m - 1]} ${y}`; };
export const fmtDayS = (s) => { const [, m, d] = String(s).slice(0, 10).split('-').map(Number); return `${d} ${MON[m - 1]}`; };
export const addDays = (s, n) => { const d = new Date(s + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
export const secs = (ms) => (ms == null ? '—' : (ms / 1000).toFixed(ms < 9500 ? 1 : 0) + ' s');
export const pct = (n, d = 1) => (Math.round(n * 10 ** d) / 10 ** d).toFixed(d) + '%';
export const esc = (s) => String(s ?? '');
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const initials = (n) => String(n || '?').split(' ').map((x) => x[0]).join('').slice(0, 2);
export function downloadText(name, text, type = 'text/plain') {
  const blob = new Blob([text], { type });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
