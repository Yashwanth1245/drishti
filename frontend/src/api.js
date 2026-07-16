// Thin fetch layer. Vite proxies /api to the backend in dev; in production
// the backend serves the built app from the same origin.
//
// Auth (Phase 5): the login token + user live in localStorage; every request
// carries the Bearer token. A 401 anywhere clears the session and fires the
// "drishti-auth" event so App falls back to the login screen.

const TOKEN_KEY = "drishti_token";
const USER_KEY = "drishti_user";

export const getToken = () => localStorage.getItem(TOKEN_KEY);

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("drishti-auth"));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event("drishti-auth"));
}

// api(path) for GETs; api(path, {method:"POST", json:{...}}) for JSON posts;
// pass body (e.g. FormData) directly for uploads.
export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts = { ...opts, body: JSON.stringify(opts.json) };
    delete opts.json;
  }
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401 && !path.startsWith("/api/auth/login")) {
    clearSession();
  }
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (j.detail) msg = j.detail;
    } catch { /* non-JSON error body */ }
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

export const fmt = (n) =>
  n === null || n === undefined ? "—" : Number(n).toLocaleString("en-IN");

export function riskClass(score) {
  if (score >= 55) return "risk-high";
  if (score >= 35) return "risk-med";
  return "risk-low";
}
