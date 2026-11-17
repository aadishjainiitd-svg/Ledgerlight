/* API client. The browser talks to the FastAPI backend directly (CORS is open); SSE needs a long-lived connection. */
export const API = (process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8010').replace(/\/$/, '');

export const ROLES = {
  clerk: { name: 'Priya Nair', label: 'AP Clerk' },
  manager: { name: 'Rahul Mehta', label: 'AP Manager' },
};

let currentRole = 'clerk';
export function setApiRole(r) { currentRole = r; }
export function getApiRole() { return currentRole; }

export class ApiError extends Error {
  constructor(message, status, fields) { super(message); this.status = status; this.fields = fields || null; }
}

/* Per-visitor sandbox (public deployment): this browser's private copy of the demo data. The id is made here,
   once, and kept in localStorage, so every request (including ones fired at the same moment on first load) uses
   the same sandbox. It travels as a header on fetch calls and as ?sandbox= on URLs the browser loads by itself
   (the live run stream, page images, PDF links). A backend without sandboxes ignores it. */
const SB_KEY = 'll-sandbox';
let memSandbox = '';
export function sandboxId() {
  if (typeof window === 'undefined') return '';
  try {
    let id = window.localStorage.getItem(SB_KEY);
    if (!id || !/^[a-f0-9]{16,40}$/.test(id)) {
      const b = new Uint8Array(12); window.crypto.getRandomValues(b);
      id = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
      window.localStorage.setItem(SB_KEY, id);
    }
    return id;
  } catch {
    if (!memSandbox) { const b = new Uint8Array(12); window.crypto.getRandomValues(b); memSandbox = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join(''); }
    return memSandbox;
  }
}

export const url = (path) => {
  const full = path.startsWith('http') ? path : API + path;
  const sb = sandboxId();
  if (!sb || !full.startsWith(API)) return full;
  return full + (full.includes('?') ? '&' : '?') + 'sandbox=' + sb;
};

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = { 'X-Ledgerlight-Role': currentRole };
  const sb = sandboxId();
  if (sb) headers['X-Ledgerlight-Sandbox'] = sb;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(url(path), { method, headers, body: payload, cache: 'no-store' });
  } catch (e) {
    throw new ApiError("Can't reach the Ledgerlight server. Check that the backend is running.", 0);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const msg = (data && (data.error || data.detail)) || `Request failed (${res.status})`;
    throw new ApiError(typeof msg === 'string' ? msg : JSON.stringify(msg), res.status, data && data.fields, data);
  }
  return data;
}

export const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '' && v !== 'all') p.set(k, v); });
  const s = p.toString();
  return s ? '?' + s : '';
};
