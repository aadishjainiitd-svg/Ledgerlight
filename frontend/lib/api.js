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

export const url = (path) => (path.startsWith('http') ? path : API + path);

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = { 'X-Ledgerlight-Role': currentRole };
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
