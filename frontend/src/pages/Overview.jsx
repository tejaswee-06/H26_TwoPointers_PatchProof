import React from 'react';
import { AlertTriangle, ArrowRight, Check, CircleDashed, ClipboardCheck, Code2, FileStack, FolderGit2, Info, ScanSearch, X } from 'lucide-react';
import Pipeline from '../components/Pipeline.jsx';
import { EvidenceLabel, Metric, Panel, Pill, Reveal, VerificationBadge } from '../components/ui.jsx';
import { healthChecks, pipelineStages, plural, shortTime, SUPPORT_META } from '../lib/model.js';
import { hrefFor, navigate } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';
import { RichText } from '../lib/markdown.jsx';

const TONE_ICON = { good: Check, warn: AlertTriangle, bad: X, muted: CircleDashed };
const SEV = [['high', 'High'], ['review', 'Review'], ['info', 'Info']];

export default function Overview() {
  const { view, health, runs, runId, selectRun, offline } = useWS();
  const go = (s, p = {}) => navigate(s, { run: offline ? undefined : runId, ...p });
  const stages = pipelineStages(view, health?.ai_adapter);
  const checks = healthChecks(view);
  const total = view.all.length;
  const v = view.verification;
  const top = view.candidates.find((c) => c.type !== 'manifest_inconsistency') || view.candidates[0];

  return (
    <>
      {view.run.note && <Reveal i={0} className="notice notice-info"><Info size={17} /><div><strong>{view.run.label}</strong><p>{view.run.note}</p></div></Reveal>}
      {view.run.state === 'failed' && <Reveal className="notice notice-bad"><AlertTriangle size={17} /><div><strong>This scan did not finish</strong><p>{view.run.error}</p></div><a className="button button-outline button-small" href={hrefFor('runs')}>Retry from Scans & runs</a></Reveal>}

      <Reveal i={1}><Pipeline stages={stages} onSelect={(s) => go(s.route)} /></Reveal>

      <div className="metric-grid">
        <Reveal i={2}><Metric icon={FolderGit2} label="Manifests scanned" value={view.scan?.summary?.manifest_count ?? '—'} note={view.scan ? (view.scan.manifests_scanned || []).join(', ') || view.scan.scan_status : 'No scan artifact'} onClick={() => go('findings')} /></Reveal>
        <Reveal i={3}><Metric icon={ScanSearch} label="Findings & review leads" value={view.scan || view.usage ? total : '—'} note={`${view.findings.length} manifest finding${view.findings.length === 1 ? '' : 's'} · ${view.leads.length} usage lead${view.leads.length === 1 ? '' : 's'}`} onClick={() => go('findings')} /></Reveal>
        <Reveal i={4}><Metric icon={Code2} label="Declared packages" value={view.usage?.summary?.declared_packages ?? '—'} note={view.usage ? `${view.usage.python_files_scanned ?? '?'} Python files traced` : 'No usage artifact'} onClick={() => go('usage')} /></Reveal>
        <Reveal i={5}><Metric icon={ClipboardCheck} label="Verification" value={view.verificationMeta.short} tone={view.verificationMeta.tone} note={v ? `${v.baseline?.test_summary || 'baseline recorded'}${v.after ? ` → ${v.after.test_summary || 'after recorded'}` : ''}` : 'No verification artifact'} onClick={() => go('verification')} /></Reveal>
      </div>

      <div className="overview-grid">
        <Reveal i={6}>
          <Panel title="Repository health" subtitle="Checks derived from the run's artifacts — no synthetic score">
            <ul className="health-list">
              {checks.map((c) => {
                const Icon = TONE_ICON[c.tone] || CircleDashed;
                return <li key={c.title} className={`tone-${c.tone}`}><span className="health-icon"><Icon size={14} /></span><div><strong>{c.title}</strong><small>{c.detail}</small></div></li>;
              })}
            </ul>
          </Panel>
        </Reveal>
        <Reveal i={7}>
          <Panel title="Severity distribution" subtitle={`${total} finding${total === 1 ? '' : 's'} and review lead${total === 1 ? '' : 's'}; 'review' is not a vulnerability rating`}>
            {total ? (
              <div className="sev-chart">
                <div className="sev-bar" role="img" aria-label={SEV.map(([k, l]) => `${l}: ${view.severityCounts[k] || 0}`).join(', ')}>
                  {SEV.map(([k]) => view.severityCounts[k] ? <span key={k} className={`sev-seg sev-${k}`} style={{ flexGrow: view.severityCounts[k] }} /> : null)}
                </div>
                <ul className="sev-legend">
                  {SEV.map(([k, l]) => (
                    <li key={k}><button type="button" onClick={() => go('findings', { severity: k })}><span className={`sev-swatch sev-${k}`} />{l}<strong>{view.severityCounts[k] || 0}</strong></button></li>
                  ))}
                </ul>
                <div className="sev-split">
                  <div><small>Manifest findings</small><strong>{view.findings.length}</strong></div>
                  <div><small>Usage review leads</small><strong>{view.leads.length}</strong></div>
                </div>
              </div>
            ) : <p className="panel-pad muted">{view.scan ? 'No findings or review leads in this run.' : 'No scan evidence loaded.'}</p>}
          </Panel>
        </Reveal>
      </div>

      <div className="overview-grid">
        <Reveal i={8}>
          <Panel title="Leading candidate cause" subtitle="Hypothesis derived from the evidence" actions={<a className="text-link small" href={hrefFor('root-cause', { run: offline ? undefined : runId })}>All candidates <ArrowRight size={14} /></a>}>
            {top ? (
              <div className="panel-pad top-cause">
                <div className="row-wrap"><EvidenceLabel label="HYPOTHESIS" /><Pill tone={SUPPORT_META[top.support]?.tone}>{SUPPORT_META[top.support]?.label || top.support}</Pill></div>
                <h4><RichText text={top.title} /></h4>
                <p className="muted"><RichText text={top.inferred} /></p>
              </div>
            ) : <p className="panel-pad muted">{view.diagnosis ? 'No candidate causes could be derived from these artifacts.' : offline ? 'Root-cause diagnosis needs the engine.' : 'Diagnosis not available.'}</p>}
          </Panel>
        </Reveal>
        <Reveal i={9}>
          <Panel title="Verification record" subtitle="Independent runner output only" actions={<VerificationBadge status={view.assessment.status} />}>
            {v ? (
              <div className="ba-mini panel-pad">
                <div className={`ba-cell ${v.baseline?.passed ? 'ok' : 'fail'}`}><small>Baseline</small><strong>{v.baseline?.passed ? 'Passed' : v.baseline ? 'Failed' : 'Not run'}</strong><span>{v.baseline?.test_summary || '—'}</span></div>
                <ArrowRight size={16} className="ba-arrow" aria-hidden="true" />
                <div className={`ba-cell ${v.after?.passed ? 'ok' : v.after ? 'fail' : ''}`}><small>After change</small><strong>{v.after ? (v.after.passed ? 'Passed' : 'Failed') : 'Not run'}</strong><span>{v.after?.test_summary || (v.after ? '—' : 'No after-change phase')}</span></div>
                {(v.change?.environment_diff || []).length > 0 && <p className="ba-diff">Change: {(v.change.environment_diff).map((d) => `${d.package} ${d.before ?? '∅'} → ${d.after ?? '∅'}`).join(', ')}</p>}
              </div>
            ) : <p className="panel-pad muted">No verification has been recorded. {view.run.can_verify ? 'Open the verification lab to run one.' : 'Scan the repository folder locally to enable verification.'}</p>}
          </Panel>
        </Reveal>
      </div>

      {!offline && (
        <Reveal i={10}>
          <Panel title="Scan history" subtitle="Recent runs in this workspace" actions={<a className="text-link small" href={hrefFor('runs', { run: runId })}>Manage <ArrowRight size={14} /></a>}>
            <ul className="history-mini">
              {runs.slice(0, 5).map((r) => (
                <li key={r.id} className={r.id === runId ? 'current' : ''}>
                  <button type="button" onClick={() => selectRun(r.id)} aria-current={r.id === runId}>
                    <FileStack size={15} />
                    <span className="hm-name">{r.root_name || r.label}<small>{r.source === 'bundled' ? 'Bundled evidence' : `${r.source === 'import' ? 'Imported' : 'Scanned'} ${shortTime(r.created_at)}`}</small></span>
                    <span className="hm-count">{plural(r.summary?.finding_count ?? 0, 'finding')}</span>
                    <VerificationBadge status={r.verification_status} />
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </Reveal>
      )}
    </>
  );
}
