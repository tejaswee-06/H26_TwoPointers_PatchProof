import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AudioLines, Check, ChevronDown, Info, Keyboard, Menu, Moon, Sun, X } from 'lucide-react';
import { api } from './lib/api.js';
import { buildView } from './lib/model.js';
import { navigate, useRoute } from './lib/router.js';
import { WorkspaceContext, speak as speakText } from './lib/workspace.js';
import Landing from './pages/Landing.jsx';
import Workspace from './pages/Workspace.jsx';

const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
};

function usePref(key, initial) {
  const [v, setV] = useState(() => store.get(key, initial));
  useEffect(() => { store.set(key, v); }, [key, v]);
  return [v, setV];
}

export default function App() {
  const route = useRoute();
  const [theme, setTheme] = usePref('patchproof-theme', window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  const [motion, setMotion] = usePref('patchproof-motion', window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'reduced' : 'full');
  const [textSize, setTextSize] = usePref('patchproof-text', 'normal');
  const [contrast, setContrast] = usePref('patchproof-contrast', 'off');
  const [a11yOpen, setA11yOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [capOpen, setCapOpen] = useState(false);
  const [toasts, setToasts] = useState([]);

  const [health, setHealth] = useState(null);
  const [engineState, setEngineState] = useState('connecting'); // connecting | online | offline
  const [runs, setRuns] = useState([]);
  const [runId, setRunIdState] = useState(() => route.params.run || store.get('patchproof-run', ''));
  const [detail, setDetail] = useState(null);
  const [detailState, setDetailState] = useState('idle'); // idle | loading | ready | error
  const [detailError, setDetailError] = useState('');
  const [offlineDetail, setOfflineDetail] = useState(null);
  const [jobs, setJobs] = useState({});
  const jobCallbacks = useRef({});

  useEffect(() => {
    const d = document.documentElement.dataset;
    d.theme = theme; d.motion = motion; d.text = textSize; d.contrast = contrast;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f4f6fa' : '#05070b');
  }, [theme, motion, textSize, contrast]);

  const toast = useCallback((message, tone = 'good') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t.slice(-2), { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'bad' ? 7000 : 3800);
  }, []);
  const speak = useCallback((text) => speakText(text, (m) => toast(m, 'warn')), [toast]);

  const refreshRuns = useCallback(async () => {
    try {
      const [h, r] = await Promise.all([api.health(), api.runs()]);
      setHealth(h); setRuns(r.runs); setEngineState('online');
      return r.runs;
    } catch (e) {
      setEngineState('offline');
      return null;
    }
  }, []);

  const selectRun = useCallback((id) => {
    setOfflineDetail(null);
    setRunIdState(id);
    if (id) store.set('patchproof-run', id);
    const r = window.location.hash.startsWith('#/app') ? route : null;
    if (r && r.view === 'app') navigate(r.section, { run: id });
  }, [route]);

  const loadDetail = useCallback(async (id, quiet) => {
    if (!id) { setDetail(null); setDetailState('idle'); return; }
    if (!quiet) setDetailState('loading');
    try {
      const d = await api.run(id);
      setDetail(d); setDetailState('ready'); setDetailError('');
    } catch (e) {
      if (e.status === 404) {
        setDetail(null); setDetailState('error'); setDetailError('This run no longer exists. Choose another run or start a new scan.');
      } else if (e.status === 0) {
        setEngineState('offline'); setDetailState('error'); setDetailError(e.message);
      } else { setDetailState('error'); setDetailError(e.message); }
    }
  }, []);

  // initial connection + choose a run
  useEffect(() => {
    (async () => {
      const list = await refreshRuns();
      if (!list) return;
      const wanted = route.params.run || runId;
      const pick = list.find((r) => r.id === wanted) ? wanted
        : (list.find((r) => r.source !== 'bundled' && r.state === 'ready') || list.find((r) => r.id === 'bundled-linkwatch') || list[0])?.id;
      if (pick) selectRun(pick);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // keep run in sync with the URL (deep links / back button)
  // (runs only when the URL changes, so a pending hash update cannot undo a newer selection)
  useEffect(() => {
    if (route.params.run && route.params.run !== 'offline') { setRunIdState(route.params.run); store.set('patchproof-run', route.params.run); }
  }, [route.params.run]);

  useEffect(() => { if (engineState === 'online' && runId && !offlineDetail) loadDetail(runId); }, [runId, engineState, loadDetail, offlineDetail]);

  // poll running jobs
  const running = Object.values(jobs).filter((j) => ['queued', 'running'].includes(j.state));
  useEffect(() => {
    if (!running.length) return undefined;
    const t = setInterval(async () => {
      for (const j of running) {
        try {
          const { job } = await api.job(j.id);
          setJobs((all) => ({ ...all, [job.id]: job }));
          if (!['queued', 'running'].includes(job.state)) {
            const cb = jobCallbacks.current[job.id];
            delete jobCallbacks.current[job.id];
            await refreshRuns();
            cb?.(job);
          }
        } catch (e) {
          if (e.status === 404) setJobs((all) => ({ ...all, [j.id]: { ...j, state: 'failed', error: 'The engine restarted; this job is no longer tracked.' } }));
          else if (e.status === 0) setEngineState('offline');
        }
      }
    }, 800);
    return () => clearInterval(t);
  }, [running.map((j) => j.id).join(','), refreshRuns]); // eslint-disable-line react-hooks/exhaustive-deps

  const trackJob = useCallback((job, onDone) => {
    setJobs((all) => ({ ...all, [job.id]: job }));
    if (onDone) jobCallbacks.current[job.id] = onDone;
  }, []);
  const dismissJob = useCallback((id) => setJobs((all) => { const n = { ...all }; delete n[id]; return n; }), []);

  const activeDetail = offlineDetail || detail;
  const view = useMemo(() => buildView(activeDetail), [activeDetail]);

  const ctx = {
    health, engineState, runs, runId: offlineDetail ? 'offline' : runId, view, detailState: offlineDetail ? 'ready' : detailState, detailError,
    selectRun, reload: () => loadDetail(runId, true), refreshRuns, retryEngine: async () => { setEngineState('connecting'); const l = await refreshRuns(); if (l && runId) loadDetail(runId); },
    jobs, trackJob, dismissJob, toast, speak, setOfflineDetail, offline: !!offlineDetail, theme,
    motionReduced: motion === 'reduced',
  };

  const goApp = (section = 'overview', params = {}) => { setMenuOpen(false); setCapOpen(false); navigate(section, { run: params.run || (offlineDetail ? undefined : runId) || undefined, ...params }); window.scrollTo({ top: 0 }); };
  const goHomeAnchor = (id) => {
    setMenuOpen(false);
    if (route.view !== 'home') { navigate('home'); setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: motion === 'reduced' ? 'auto' : 'smooth' }), 60); }
    else document.getElementById(id)?.scrollIntoView({ behavior: motion === 'reduced' ? 'auto' : 'smooth' });
  };
  const capabilityLinks = [['Repository scan', 'runs'], ['Source evidence', 'findings'], ['Root-cause diagnosis', 'root-cause'], ['AI migration', 'migration'], ['Verification lab', 'verification'], ['Exit Capsule', 'capsule']];

  return (
    <WorkspaceContext.Provider value={ctx}>
      <div className="site-shell">
        <a className="skip-link" href="#main-content" onClick={(e) => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a>
        <header className="topbar">
          <button type="button" className="brand" onClick={() => navigate('home')} aria-label="PatchProof home">
            <span className="brand-mark">P</span><span>atchProof<span className="brand-period">.</span></span>
          </button>
          <nav className="main-nav" aria-label="Primary">
            <button type="button" onClick={() => goHomeAnchor('how')}>How it works</button>
            <div className="nav-dropdown">
              <button type="button" onClick={() => setCapOpen(!capOpen)} aria-expanded={capOpen} aria-haspopup="true">Capabilities <ChevronDown size={15} /></button>
              {capOpen && (
                <div className="dropdown-panel" onMouseLeave={() => setCapOpen(false)}>
                  {capabilityLinks.map(([label, s]) => <button type="button" key={s} onClick={() => goApp(s)}>{label}</button>)}
                </div>
              )}
            </div>
            <button type="button" onClick={() => goHomeAnchor('principle')}>Principle</button>
          </nav>
          <div className="top-actions">
            <span className={`engine-chip engine-${engineState}`} title={engineState === 'online' ? `Engine ${health?.engine_version} · Python ${health?.python}` : 'Start the engine: python -m patchproof.server'}>
              <span className="dot" />{engineState === 'online' ? 'Engine online' : engineState === 'connecting' ? 'Connecting' : 'Engine offline'}
            </span>
            {route.view === 'home' && <button type="button" className="button button-blue top-cta" onClick={() => goApp()}>Open workspace</button>}
            <button type="button" className="icon-btn" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} title={theme === 'dark' ? 'Light theme' : 'Dark theme'}>
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button type="button" className="icon-btn" onClick={() => setA11yOpen(!a11yOpen)} aria-label="Accessibility settings" aria-expanded={a11yOpen} title="Accessibility settings"><Keyboard size={17} /></button>
            <button type="button" className="icon-btn mobile-only" onClick={() => setMenuOpen(!menuOpen)} aria-label="Open menu" aria-expanded={menuOpen}><Menu size={18} /></button>
          </div>
        </header>

        {menuOpen && (
          <div className="mobile-drawer" role="dialog" aria-label="Menu">
            <button type="button" onClick={() => goHomeAnchor('how')}>How it works</button>
            <button type="button" onClick={() => goHomeAnchor('principle')}>Principle</button>
            <div className="drawer-sep">Workspace</div>
            <button type="button" onClick={() => goApp('overview')}>Overview</button>
            {capabilityLinks.map(([label, s]) => <button type="button" key={s} onClick={() => goApp(s)}>{label}</button>)}
          </div>
        )}

        {route.view === 'home' ? <Landing goApp={goApp} motionReduced={motion === 'reduced'} /> : <Workspace section={route.section} params={route.params} />}

        {a11yOpen && (
          <section className="a11y-panel" role="dialog" aria-modal="false" aria-labelledby="a11y-title">
            <div className="a11y-head">
              <h2 id="a11y-title">Accessibility</h2>
              <button type="button" className="icon-btn" onClick={() => setA11yOpen(false)} aria-label="Close accessibility settings"><X size={16} /></button>
            </div>
            <label className="a11y-option"><span><strong>Reduce motion</strong><small>Stop decorative movement and transitions</small></span>
              <input type="checkbox" checked={motion === 'reduced'} onChange={(e) => setMotion(e.target.checked ? 'reduced' : 'full')} /></label>
            <label className="a11y-option"><span><strong>Larger text</strong><small>Increase interface text size</small></span>
              <input type="checkbox" checked={textSize === 'large'} onChange={(e) => setTextSize(e.target.checked ? 'large' : 'normal')} /></label>
            <label className="a11y-option"><span><strong>Higher contrast</strong><small>Stronger borders, text and focus rings</small></span>
              <input type="checkbox" checked={contrast === 'on'} onChange={(e) => setContrast(e.target.checked ? 'on' : 'off')} /></label>
            <div className="a11y-speech">
              <button type="button" className="button button-outline button-small" onClick={() => { if ('speechSynthesis' in window) { window.speechSynthesis.pause(); toast('Speech paused'); } else toast('Speech is not supported here', 'warn'); }}><AudioLines size={14} /> Pause speech</button>
              <button type="button" className="button button-outline button-small" onClick={() => { if ('speechSynthesis' in window) { window.speechSynthesis.cancel(); toast('Speech stopped'); } else toast('Speech is not supported here', 'warn'); }}><X size={14} /> Stop speech</button>
            </div>
            <p className="a11y-note">Voice search and read-aloud use your browser's speech features when available. Everything also works with keyboard and text.</p>
          </section>
        )}

        <div className="toast-stack" role="status" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className={`toast toast-${t.tone}`}>
              {t.tone === 'good' ? <Check size={16} /> : <Info size={16} />}
              <span>{t.message}</span>
              <button type="button" onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))} aria-label="Dismiss"><X size={14} /></button>
            </div>
          ))}
        </div>
      </div>
    </WorkspaceContext.Provider>
  );
}
