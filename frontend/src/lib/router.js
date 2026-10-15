import { useEffect, useState } from 'react';

// Minimal hash router: #/ (landing) and #/app/<section>?run=<id>&id=<evidence id>
export function parseHash(hash = window.location.hash) {
  const h = hash.replace(/^#/, '') || '/';
  const [path, query = ''] = h.split('?');
  const parts = path.split('/').filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(query));
  if (parts[0] !== 'app') return { view: 'home', section: null, params };
  return { view: 'app', section: parts[1] || 'overview', params };
}

export function hrefFor(section, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString();
  return `#/app/${section}${q ? `?${q}` : ''}`;
}

export function navigate(section, params) {
  window.location.hash = section === 'home' ? '#/' : hrefFor(section, params);
}

export function useRoute() {
  const [route, setRoute] = useState(() => parseHash());
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}
