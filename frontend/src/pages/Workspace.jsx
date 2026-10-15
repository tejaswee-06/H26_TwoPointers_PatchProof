import React, { useRef } from 'react';
import { Activity, ArrowLeft, Bot, ClipboardCheck, Code2, FolderGit2, Headphones, Layers3, Loader2, Microscope, RefreshCw, ScanSearch, Server, Upload, Volume2, X } from 'lucide-react';
import { Empty, Pill, Skeleton } from '../components/ui.jsx';
import { readTextFile } from '../lib/api.js';
import { buildOfflineDetail, shortTime } from '../lib/model.js';
import { hrefFor, navigate } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';
import Overview from './Overview.jsx';
import Runs from './Runs.jsx';
import Findings from './Findings.jsx';
import Usage from './Usage.jsx';
import RootCause from './RootCause.jsx';
import Migration from './Migration.jsx';
import Verification from './Verification.jsx';
import Capsule from './Capsule.jsx';

export const SECTIONS = [
  { key: 'overview', label: 'Overview', icon: Activity, title: 'Repository overview', blurb: 'What failed, where the evidence is, what is proposed, and whether verification passed.' },
  { key: 'runs', label: 'Scans & runs', icon: FolderGit2, title: 'Scans & runs', blurb: 'Choose a repository folder to scan, import existing artifacts, and revisit earlier runs.' },
  { key: 'findings', label: 'Findings', icon: ScanSearch, title: 'Findings explorer', blurb: 'Manifest observations and usage review leads, each traced to its source line.' },
  { key: 'usage', label: 'Usage tracing', icon: Code2, title: 'Usage tracing', blurb: 'Declared packages mapped to the imports found in source. A missing import is a lead, not proof a package is unused.' },
  { key: 'root-cause', label: 'Root cause', icon: Microscope, title: 'Root-cause diagnostics', blurb: 'Candidate causes correlated from manifests, imports and captured failures — observation and inference kept apart.' },
  { key: 'migration', label: 'Migration', icon: Bot, title: 'Migration intelligence', blurb: 'Compatibility evidence from the engine and Gemma 4 proposals, which stay proposals until verified.' },
  { key: 'verification', label: 'Verification lab', icon: ClipboardCheck, title: 'Verification lab', blurb: 'Run your exact commands before and after a change in disposable copies, and inspect what actually happened.' },
  { key: 'capsule', label: 'Exit Capsule', icon: Layers3, title: 'Dependency Exit Capsule', blurb: 'The complete, exportable record for review, handoff and audit.' },
];

const PAGES = { overview: Overview, runs: Runs, findings: Findings, usage: Usage, 'root-cause': RootCause, migration: Migration, verification: Verification, capsule: Capsule };

function EngineOffline() {
  const { retryEngine, setOfflineDetail, toast } = useWS();
  const ref = useRef(null);
  async function openFiles(files) {
    const parsed = [];
    for (const f of files) {
      try { parsed.push({ name: f.name, data: JSON.parse(await readTextFile(f)) }); } catch { toast(`${f.name} is not valid JSON`, 'bad'); }
    }
    const { detail, problems } = buildOfflineDetail(parsed);
    problems?.forEach((p) => toast(p, 'warn'));
    if (detail) { setOfflineDetail(detail); navigate('overview', {}); toast('Local files opened in read-only mode'); }
  }
  return (
    <div className="offline-card reveal">
      <div className="offline-icon"><Server size={24} /></div>
      <h2>The PatchProof engine isn't running</h2>
      <p>Scanning, diagnosis, verification and capsule export happen in the local engine. Start it in a Command Prompt from the project folder:</p>
      <pre className="cmd">.venv\Scripts\activate{'\n'}python -m patchproof.server</pre>
      <div className="empty-actions">
        <button type="button" className="button button-blue" onClick={retryEngine}><RefreshCw size={15} /> Try again</button>
        <button type="button" className="button button-outline" onClick={() => ref.current?.click()}><Upload size={15} /> View local JSON files instead</button>
        <input ref={ref} type="file" hidden multiple accept=".json,application/json" onChange={(e) => { if (e.target.files?.length) openFiles([...e.target.files]); e.target.value = ''; }} />
      </div>
      <p className="muted small">Read-only mode shows artifacts you select; root-cause diagnosis, verification and official capsule export need the engine.</p>
    </div>
  );
}

function JobTray() {
  const { jobs, dismissJob, runId } = useWS();
  const list = Object.values(jobs).slice(-3);
  if (!list.length) return null;
  const label = { scan: 'Scan', verify: 'Verification', ai: 'Gemma 4 analysis' };
  const target = { scan: 'runs', verify: 'verification', ai: 'migration' };
  return (
    <div className="job-tray" aria-live="polite">
      {list.map((j) => {
        const done = j.stages.filter((s) => ['done', 'warn', 'skipped'].includes(s.state)).length;
        const active = ['queued', 'running'].includes(j.state);
        return (
          <div key={j.id} className={`job-chip job-${j.state}`}>
            {active ? <Loader2 size={14} className="spin" /> : <span className="dot" />}
            <a href={hrefFor(target[j.kind], { run: j.run_id || runId })}>{label[j.kind]} · {active ? `${done}/${j.stages.length}` : j.state}</a>
            <div className="job-bar"><span style={{ width: `${(done / j.stages.length) * 100}%` }} /></div>
            {!active && <button type="button" onClick={() => dismissJob(j.id)} aria-label="Dismiss"><X size={13} /></button>}
          </div>
        );
      })}
    </div>
  );
}

export default function Workspace({ section, params }) {
  const ws = useWS();
  const { engineState, runs, runId, view, detailState, detailError, selectRun, speak, offline, setOfflineDetail } = ws;
  const meta = SECTIONS.find((s) => s.key === section) || SECTIONS[0];
  const Page = PAGES[meta.key];
  const counts = view ? { findings: view.all.length, 'root-cause': view.candidates.length, usage: view.packages.length } : {};
  const needsRun = !['runs'].includes(meta.key);

  let body;
  if (engineState === 'offline' && !offline) body = <EngineOffline />;
  else if (engineState === 'connecting') body = <div className="page-skeleton"><Skeleton lines={2} height={90} /><Skeleton lines={5} /></div>;
  else if (needsRun && detailState === 'loading' && !view) body = <div className="page-skeleton"><Skeleton lines={2} height={90} /><Skeleton lines={6} /></div>;
  else if (needsRun && detailState === 'error') body = <Empty icon={FolderGit2} title="This run couldn't be opened" actions={<a className="button button-blue" href={hrefFor('runs')}>Go to scans & runs</a>}>{detailError}</Empty>;
  else if (needsRun && !view) body = <Empty icon={FolderGit2} title="Choose or create a run" actions={<a className="button button-blue" href={hrefFor('runs')}>Scan a repository</a>}>Every page works from one run — a scan of a repository folder or a set of imported artifacts.</Empty>;
  else body = <Page params={params} />;

  return (
    <main className="app-view">
      <aside className="app-sidebar" aria-label="Workspace sections">
        <p className="workspace-label">Workspace</p>
        <nav>
          {SECTIONS.map((s) => (
            <a key={s.key} href={hrefFor(s.key, { run: offline ? undefined : runId })} className={`side-link ${meta.key === s.key ? 'active' : ''}`} aria-current={meta.key === s.key ? 'page' : undefined}>
              <s.icon size={17} /><span>{s.label}</span>
              {counts[s.key] != null && <span className="side-count">{counts[s.key]}</span>}
              {s.key === 'migration' && !view?.ai && <span className="pending-dot" title="AI analysis pending" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <JobTray />
          <div className="side-status">
            <span className={`status-ring engine-${engineState}`} />
            <div><strong>{view ? (view.run.root_name || view.run.label) : 'No run selected'}</strong><small>{view ? (view.run.source === 'bundled' ? 'Imported evidence (bundled)' : view.run.source === 'import' ? 'Imported artifacts' : view.run.source === 'offline' ? 'Read-only local files' : 'Local scan') : 'Scan a repository to begin'}</small></div>
          </div>
          <a className="side-link" href="#/"><ArrowLeft size={16} /> Back to landing</a>
        </div>
      </aside>
      <section className="workspace" id="main-content" tabIndex={-1}>
        <div className="workspace-top">
          <div className="breadcrumb"><span>PatchProof</span><span aria-hidden="true">/</span><strong>{meta.label}</strong></div>
          <div className="workspace-tools">
            {offline ? (
              <span className="offline-pill"><Pill tone="warn">Read-only local files</Pill><button type="button" className="ghost-btn" onClick={() => { setOfflineDetail(null); ws.retryEngine(); }}>Close</button></span>
            ) : engineState === 'online' && runs.length > 0 && (
              <label className="run-select">
                <span className="sr-only">Current run</span>
                <select value={runId || ''} onChange={(e) => selectRun(e.target.value)}>
                  {runs.map((r) => <option key={r.id} value={r.id}>{r.root_name || r.label} — {r.source === 'bundled' ? 'bundled evidence' : shortTime(r.created_at)}{r.state && r.state !== 'ready' ? ` (${r.state})` : ''}</option>)}
                </select>
              </label>
            )}
            <button type="button" className="icon-btn" title="Read this page summary aloud" aria-label="Read page summary aloud"
              onClick={() => speak(view ? `${meta.title}. ${view.all.length} findings and review leads. ${view.candidates.length} candidate causes. AI analysis ${view.ai ? 'loaded as a proposal' : 'pending'}. Verification status: ${view.verificationMeta.label}.` : `${meta.title}. No run selected.`)}>
              <Volume2 size={16} />
            </button>
            {!offline && engineState === 'online' && <button type="button" className="icon-btn" title="Reload run" aria-label="Reload run data" onClick={() => { ws.refreshRuns(); ws.reload(); }}><RefreshCw size={16} /></button>}
          </div>
        </div>
        <div className="workspace-heading reveal" key={`h-${meta.key}`}>
          <div>
            <h1>{meta.title}</h1>
            <p>{meta.blurb}</p>
          </div>
          {view?.run?.source === 'bundled' && needsRun && <Pill tone="observed" title={view.run.note}>Bundled LinkWatch evidence</Pill>}
        </div>
        <div className="page" key={needsRun ? `${meta.key}-${runId}` : meta.key}>{body}</div>
        <footer className="workspace-footer">
          <span><span className={`live-dot engine-${engineState}`} /> Local engine on 127.0.0.1 · artifacts stay on this machine</span>
          <button type="button" onClick={() => speak('PatchProof is an evidence-first dependency maintenance workspace. Use the sections to inspect findings, usage, candidate causes, AI proposals, verification and the exit capsule.')}><Headphones size={14} /> Read workspace guide</button>
        </footer>
      </section>
    </main>
  );
}
