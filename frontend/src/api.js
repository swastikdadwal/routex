async function request(method, path, body) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error('Cannot reach the RouteX server. Check that it is running.');
  }
  if (response.status === 204) return null;
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // A proxy or crash can answer with non-JSON; the status check below covers it.
  }
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === 'string' ? detail : `The server answered ${response.status}.`);
  }
  return data;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body ?? {}),
  patch: (path, body) => request('PATCH', path, body),
  del: (path) => request('DELETE', path),
};

// Road geometry goes through a serial queue, because the public road services
// ask for light use. Results are kept per route, so switching plans is instant.
const geometryCache = new Map();
let queue = Promise.resolve();

export function routeGeometry(source, stops) {
  const key = `${source}:${stops.map((p) => `${p.lat.toFixed(6)},${p.lng.toFixed(6)}`).join(';')}`;
  if (!geometryCache.has(key)) {
    const job = queue.then(async () => {
      try {
        const { line } = await api.post('/geometry', {
          source,
          stops: stops.map(({ lat, lng }) => ({ lat, lng })),
        });
        return line;
      } catch {
        geometryCache.delete(key);
        return null;
      }
    });
    queue = job;
    geometryCache.set(key, job);
  }
  return geometryCache.get(key);
}
