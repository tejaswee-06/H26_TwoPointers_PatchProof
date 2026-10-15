// Thin client for the local PatchProof engine (python -m patchproof.server).
export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

async function request(method, path, body) {
  const headers = {};
  if (method !== 'GET') { headers['X-PatchProof-Client'] = '1'; headers['Content-Type'] = 'application/json'; }
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('The PatchProof engine is not reachable. Start it with: python -m patchproof.server', 0);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) {
    if (res.status === 502 || res.status === 504 || (res.status === 500 && !data)) {
      throw new ApiError('The PatchProof engine is not reachable. Start it with: python -m patchproof.server', 0);
    }
    throw new ApiError(data?.error || `Request failed (${res.status})`, res.status, data);
  }
  if (data === null) throw new ApiError('The engine returned an unexpected response.', res.status);
  return data;
}

export const api = {
  health: () => request('GET', '/api/health'),
  runs: () => request('GET', '/api/runs'),
  run: (id) => request('GET', `/api/runs/${encodeURIComponent(id)}`),
  deleteRun: (id) => request('DELETE', `/api/runs/${encodeURIComponent(id)}`),
  scan: (body) => request('POST', '/api/runs/scan', body),
  rescan: (id) => request('POST', `/api/runs/${encodeURIComponent(id)}/rescan`, {}),
  rebuild: (id) => request('POST', `/api/runs/${encodeURIComponent(id)}/rebuild`, {}),
  verifyTemplate: (id) => request('GET', `/api/runs/${encodeURIComponent(id)}/verify-template`),
  verify: (id, config, statement) => request('POST', `/api/runs/${encodeURIComponent(id)}/verify`, { config, consent: true, consent_statement: statement }),
  storeAi: (id, artifact) => request('POST', `/api/runs/${encodeURIComponent(id)}/ai`, { artifact }),
  removeAi: (id) => request('DELETE', `/api/runs/${encodeURIComponent(id)}/ai`),
  runAi: (id) => request('POST', `/api/runs/${encodeURIComponent(id)}/ai/run`, {}),
  importFiles: (files, label) => request('POST', '/api/import', { files, label }),
  job: (id) => request('GET', `/api/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id) => request('POST', `/api/jobs/${encodeURIComponent(id)}/cancel`, {}),
  fs: (path) => request('GET', `/api/fs${path ? `?path=${encodeURIComponent(path)}` : ''}`),
  capsuleJson: (id) => request('GET', `/api/runs/${encodeURIComponent(id)}/files/dependency-exit-capsule.json`),
};

export const fileUrl = (runId, name) => `/api/runs/${encodeURIComponent(runId)}/files/${encodeURIComponent(name)}`;

export function readTextFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ''));
    r.onerror = () => reject(new Error(`Could not read ${file.name}`));
    r.readAsText(file);
  });
}

export function saveBlob(name, content, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
