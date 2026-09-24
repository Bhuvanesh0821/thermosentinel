// Thin client for the ThermoSentinel REST API. Never holds secrets: the browser only
// ever talks to our own backend, which owns every credential.

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor({ status, code, message, details }) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function buildUrl(path, params) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
    });
  }
  return API_BASE ? url.toString() : `${url.pathname}${url.search}`;
}

async function request(method, path, { params, body, signal } = {}) {
  let response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: 'Cannot reach the ThermoSentinel API. Is the backend running?',
    });
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // non-JSON (e.g. proxy error page)
  }
  if (!response.ok || payload?.status === 'error') {
    const error = payload?.error || {};
    throw new ApiError({
      status: response.status,
      code: error.code || (response.status === 502 || response.status === 504 ? 'network_error' : 'http_error'),
      message:
        error.message ||
        (response.status >= 500 ? 'The API is unavailable.' : `Request failed (HTTP ${response.status}).`),
      details: error.details,
    });
  }
  return { data: payload?.data, meta: payload?.meta || {} };
}

export const api = {
  get: (path, params, signal) => request('GET', path, { params, signal }),
  post: (path, params, body) => request('POST', path, { params, body }),
};

export const streamUrl = () => buildUrl('/api/stream');

/** WebSocket URL on the API origin (same origin in dev via the Vite proxy). */
export function wsUrl(path) {
  const base = API_BASE ? new URL(API_BASE) : window.location;
  const proto = base.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${base.host}${path}`;
}
export const docsUrl = () => buildUrl('/api/docs');
