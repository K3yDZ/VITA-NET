// api.js — thin wrapper around the optional FastAPI backend.
// Every call has a short timeout and never throws past its caller in a
// way that could freeze the UI; callers (advisor.js) always have a local
// fallback. In single-port mode (frontend served by FastAPI) relative
// URLs are used so no CORS is needed.

async function fetchWithTimeout(url, options = {}, timeoutMs = 4000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(id);
  }
}

// Canonical backend base resolution (runs once, then cached).
// Probes candidates in priority order; first to answer /api/health wins.
// Offline-first: if none respond, returns null and callers fall back to local rules.
let _resolvedBase = null;          // string | null (null = no backend found yet)
let _resolvingPromise = null;      // Promise<string | null> while probing

function buildCandidates() {
  // Explicit user override (set by host page before import) has highest priority.
  if (window.VITA_NET_API_BASE !== undefined) {
    return [window.VITA_NET_API_BASE];
  }
  // Same-origin (single-port FastAPI serving frontend) — relative URLs work.
  if (window.location.origin && (window.location.port === "8000" || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
    return ["", "http://localhost:8000"];
  }
  // Cross-origin (dev: frontend on 5500, backend on 8000; or public tunnel).
  // Try same-origin first (if served via proxy), then localhost:8000.
  // Do NOT hardcode http://localhost:8000 when on HTTPS — mixed content blocks it.
  const sameOrigin = "";
  const candidates = [sameOrigin];
  if (window.location.protocol !== "https:") {
    candidates.push("http://localhost:8000");
  }
  return candidates;
}

async function resolveBase() {
  if (_resolvedBase !== null || _resolvingPromise) {
    return _resolvingPromise ?? Promise.resolve(_resolvedBase);
  }
  _resolvingPromise = (async () => {
    for (const base of buildCandidates()) {
      try {
        const res = await fetchWithTimeout(`${base}/api/health`, {}, 1500);
        if (res && res.status === "ok") {
          _resolvedBase = base;
          return base;
        }
      } catch {}
    }
    _resolvedBase = null;
    return null;
  })();
  return _resolvingPromise;
}

export async function getBase() {
  if (_resolvedBase !== null) return _resolvedBase;
  return resolveBase();
}

export async function checkBackend() {
  const base = await getBase();
  return base !== null;
}

async function fetchOnResolvedBase(path, options = {}, timeoutMs = 4000) {
  const base = await getBase();
  if (base === null) return null; // offline — caller handles fallback
  return fetchWithTimeout(`${base}${path}`, options, timeoutMs);
}

export async function requestAdvice(payload) {
  const res = await fetchOnResolvedBase("/api/advice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, 5000);
  return res;
}

export async function fetchHistory(astronautId, limit = 60) {
  return fetchOnResolvedBase(`/api/astronauts/${astronautId}/history?limit=${limit}`, {}, 3000);
}

export async function logReading(astronautId, vitals) {
  const { hrv: _hrv, ...clean } = vitals;
  try {
    return await fetchOnResolvedBase(
      `/api/astronauts/${astronautId}/vitals`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clean),
      },
      3000
    );
  } catch (e) {
    console.warn(`[VITA-NET] logReading ${astronautId} failed:`, e?.message ?? e);
    return null;
  }
}

// For modules that still import checkBackend directly and want a boolean.
export { fetchWithTimeout };