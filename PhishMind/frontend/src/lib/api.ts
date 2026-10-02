// All PhishMind backend responses are wrapped as { status: "success"|"error", data | message }.
// unwrap() centralizes that so callers just get the payload or a thrown Error.

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function unwrap(res: Response) {
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    // no JSON body (e.g. network-level failure) — fall through to the status check below
  }
  if (!res.ok) {
    const message = body?.detail || body?.message || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return body?.data ?? body;
}

export async function fetchHistory() {
  const res = await fetch(`${API_BASE}/api/v1/history`);
  return unwrap(res);
}

export async function fetchScanResult(id: string) {
  const res = await fetch(`${API_BASE}/api/v1/scan/${id}`);
  return unwrap(res);
}

export async function scanEmail(rawEmailText: string) {
  const res = await fetch(`${API_BASE}/api/v1/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_email_text: rawEmailText }),
  });
  return unwrap(res);
}

export function createEventSource() {
  return new EventSource(`${API_BASE}/api/v1/listener/events`);
}

export async function startListener(credentials: { host: string; username: string; app_password: string }) {
  const res = await fetch(`${API_BASE}/api/v1/listener/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials),
  });
  return unwrap(res);
}

export async function fetchListenerStatus() {
  const res = await fetch(`${API_BASE}/api/v1/listener/status`);
  return unwrap(res);
}
