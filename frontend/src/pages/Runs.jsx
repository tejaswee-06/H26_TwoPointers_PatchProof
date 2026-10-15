import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, Beaker, Folder, FolderOpen, FolderSearch, HardDrive, RefreshCw, ScanSearch, Trash2, Upload } from 'lucide-react';
import JobProgress from '../components/JobProgress.jsx';
import { Empty, Modal, Panel, Pill, Reveal, VerificationBadge } from '../components/ui.jsx';
import { api, readTextFile } from '../lib/api.js';
import { plural, shortTime } from '../lib/model.js';
import { navigate } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';

function FolderBrowser({ start, onPick, onClose }) {
  const [state, setState] = useState({ loading: true });
  const load = async (p) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try { setState({ loading: false, data: await api.fs(p) }); } catch (e) { setState((s) => ({ ...s, loading: false, error: e.message })); }
  };
  useEffect(() => { load(start || ''); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const d = state.data;
  return (
    <Modal title="Choose a repository folder" onClose={onClose} wide
      footer={<>
        <span className="muted small">{d?.path ? (d.has_manifest ? 'This folder contains a supported manifest.' : 'No manifest directly in this folder.') : 'Pick a starting location.'}</span>
        <button type="button" className="button button-outline" onClick={onClose}>Cancel</button>
        <button type="button" className="button button-blue" disabled={!d?.path} onClick={() => onPick(d.path)}>Use this folder</button>
      </>}>
      <div className="fs-bar">
        <button type="button" className="icon-btn" disabled={!d?.parent} onClick={() => load(d.parent)} aria-label="Parent folder"><ArrowUp size={15} /></button>
        <code className="fs-path">{d?.path || 'Locations'}</code>
        <button type="button" className="ghost-btn" onClick={() => load('')}><HardDrive size={14} /> Locations</button>
      </div>
      {state.error && <p className="form-error">{state.error}</p>}
      <ul className="fs-list" aria-busy={state.loading}>
        {(d?.entries || []).map((e) => (
          <li key={e.path}>
            <button type="button" onDoubleClick={() => onPick(e.path)} onClick={() => load(e.path)}>
              {e.has_manifest ? <FolderSearch size={16} className="tone-text-good" /> : <Folder size={16} />}
              <span>{e.name}</span>{e.has_manifest && <Pill tone="good">manifest</Pill>}
            </button>
          </li>
        ))}
        {d && !d.entries?.length && <li className="muted small fs-empty">No sub-folders.</li>}
      </ul>
    </Modal>
  );
}

export default function Runs() {
  const { runs, runId, selectRun, trackJob, jobs, toast, refreshRuns, health } = useWS();
  const [root, setRoot] = useState(() => { try { return localStorage.getItem('patchproof-last-root') || ''; } catch { return ''; } });
  const [exclude, setExclude] = useState('');
  const [formError, setFormError] = useState('');
  const [browse, setBrowse] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const fileRef = useRef(null);
  const scanJobs = Object.values(jobs).filter((j) => j.kind === 'scan').slice(-1);

  const onScanDone = (job) => {
    if (job.state === 'succeeded' && job.result?.run_id) {
      toast('Scan complete — evidence is ready');
      selectRun(job.result.run_id);
      navigate('overview', { run: job.result.run_id });
    } else if (job.state === 'cancelled') toast('Scan cancelled; the partial run was removed', 'warn');
    else toast(job.error || 'Scan failed', 'bad');
  };

  async function startScan(body) {
    setFormError(''); setBusy(true);
    try {
      const { job } = await api.scan(body);
      trackJob(job, onScanDone);
      if (body.root) { try { localStorage.setItem('patchproof-last-root', body.root); } catch { /* ignore */ } }
    } catch (e) { setFormError(e.message); } finally { setBusy(false); }
  }

  async function rescan(id) {
    try { const { job } = await api.rescan(id); trackJob(job, onScanDone); toast('Rescan started'); } catch (e) { toast(e.message, 'bad'); }
  }

  async function del(id) {
    try {
      if (id === runId) {  // move off the run first so nothing keeps requesting it
        const next = runs.find((r) => r.id !== id);
        if (next) selectRun(next.id);
      }
      await api.deleteRun(id);
      toast('Run deleted');
      setConfirmDelete(null);
      await refreshRuns();
    } catch (e) { toast(e.message, 'bad'); }
  }

  async function importFiles(fileList) {
    const files = [];
    for (const f of fileList) files.push({ name: f.name, content: await readTextFile(f) });
    try {
      const res = await api.importFiles(files);
      setImportResult(res);
      await refreshRuns();
      selectRun(res.run_id);
      toast(`Imported ${res.imported.join(', ')}`);
    } catch (e) {
      setImportResult({ error: e.message, problems: e.data?.problems || [] });
      toast(e.message, 'bad');
    }
  }

  return (
    <>
      <div className="runs-grid">
        <Reveal i={0}>
          <Panel title="Scan a repository" subtitle="Reads manifests and Python source. Nothing in the repository is executed.">
            <form className="form panel-pad" onSubmit={(e) => { e.preventDefault(); startScan({ root, exclude: exclude.split(',').map((x) => x.trim()).filter(Boolean) }); }}>
              <label className="field">
                <span>Repository folder</span>
                <div className="input-row">
                  <input value={root} onChange={(e) => setRoot(e.target.value)} placeholder="C:\projects\LinkWatch" spellCheck={false} aria-describedby="root-help" />
                  <button type="button" className="button button-outline" onClick={() => setBrowse(true)}><FolderOpen size={15} /> Browse</button>
                </div>
                <small id="root-help">Absolute path on this computer. The engine reads it locally.</small>
              </label>
              <label className="field">
                <span>Exclude folders <em>(optional)</em></span>
                <input value={exclude} onChange={(e) => setExclude(e.target.value)} placeholder="docs, scripts/legacy" spellCheck={false} />
                <small>Comma-separated names or relative paths. .venv, node_modules, build output and caches are always skipped.</small>
              </label>
              {formError && <p className="form-error" role="alert">{formError}</p>}
              <div className="form-actions">
                <button type="submit" className="button button-blue" disabled={busy || !root.trim()}><ScanSearch size={15} /> Scan repository</button>
              </div>
            </form>
          </Panel>
        </Reveal>
        <Reveal i={1} className="runs-side">
          <Panel title="Try the compatibility fixture" subtitle="A tiny synthetic project that reproduces the Jinja2 / MarkupSafe mechanism (not LinkWatch).">
            <div className="panel-pad">
              <button type="button" className="button button-outline" disabled={busy || !health?.examples?.[0]?.available} onClick={() => startScan({ example: 'compat_fixture' })}><Beaker size={15} /> Scan the fixture</button>
              <p className="muted small mt">Verification of the fixture downloads packages from PyPI into disposable environments.</p>
            </div>
          </Panel>
          <Panel title="Import artifacts" subtitle="Load JSON produced by the engine on another machine.">
            <div className="panel-pad">
              <button type="button" className="button button-outline" onClick={() => fileRef.current?.click()}><Upload size={15} /> Choose JSON files</button>
              <input ref={fileRef} type="file" hidden multiple accept=".json,application/json" onChange={(e) => { if (e.target.files?.length) importFiles([...e.target.files]); e.target.value = ''; }} />
              <p className="muted small mt">patchproof-report.json, patchproof-usage-report.json, verification.json, ai-analysis.json or a dependency-exit-capsule.json. Verification status is re-derived from evidence.</p>
              {importResult && (
                <div className={`import-result ${importResult.error ? 'bad' : ''}`}>
                  {importResult.error ? <strong>{importResult.error}</strong> : <strong>Imported: {importResult.imported.join(', ')}</strong>}
                  {(importResult.problems || []).map((p, i) => <small key={i}>{p.file}: {p.error}</small>)}
                </div>
              )}
            </div>
          </Panel>
        </Reveal>
      </div>

      {scanJobs.map((j) => <Reveal key={j.id}><JobProgress job={j} title="Scan progress" /></Reveal>)}

      <Reveal i={2}>
        <Panel title="Run history" subtitle={`${runs.length} run${runs.length === 1 ? '' : 's'} in this workspace`}>
          {runs.length ? (
            <ul className="run-list">
              {runs.map((r) => (
                <li key={r.id} className={`run-row ${r.id === runId ? 'current' : ''}`}>
                  <div className="run-main">
                    <div className="row-wrap">
                      <strong>{r.root_name || r.label}</strong>
                      <Pill tone={r.source === 'bundled' ? 'observed' : r.source === 'import' ? 'hypothesis' : 'muted'}>{r.source === 'bundled' ? 'Bundled' : r.source === 'import' ? 'Imported' : 'Scan'}</Pill>
                      {r.state && r.state !== 'ready' && <Pill tone={r.state === 'failed' ? 'bad' : 'warn'}>{r.state}</Pill>}
                    </div>
                    <small>{r.label !== r.root_name ? `${r.label} · ` : ''}{r.source === 'bundled' ? 'Shipped with the project' : shortTime(r.created_at)} · {plural(r.summary?.manifest_count ?? 0, 'manifest')} · {plural(r.summary?.finding_count ?? 0, 'finding')} · {plural(r.summary?.review_lead_count ?? 0, 'lead')}</small>
                    {r.error && <small className="tone-text-bad">{r.error}</small>}
                  </div>
                  <VerificationBadge status={r.verification_status} />
                  <div className="run-actions">
                    <button type="button" className="button button-small button-outline" onClick={() => { selectRun(r.id); navigate('overview', { run: r.id }); }}>Open</button>
                    {r.can_rescan && <button type="button" className="ghost-btn" onClick={() => rescan(r.id)} title="Scan this folder again as a new run"><RefreshCw size={14} /> Rescan</button>}
                    {r.deletable && (confirmDelete === r.id
                      ? <span className="confirm"><button type="button" className="ghost-btn tone-text-bad" onClick={() => del(r.id)}>Confirm delete</button><button type="button" className="ghost-btn" onClick={() => setConfirmDelete(null)}>Keep</button></span>
                      : <button type="button" className="ghost-btn" onClick={() => setConfirmDelete(r.id)} aria-label={`Delete run ${r.root_name}`}><Trash2 size={14} /> Delete</button>)}
                  </div>
                </li>
              ))}
            </ul>
          ) : <Empty icon={ScanSearch} title="No runs yet" compact>Scan a folder or import artifacts to create the first run.</Empty>}
        </Panel>
      </Reveal>
      {browse && <FolderBrowser start={root} onClose={() => setBrowse(false)} onPick={(p) => { setRoot(p); setBrowse(false); }} />}
    </>
  );
}
