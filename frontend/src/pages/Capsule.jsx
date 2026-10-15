import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, CircleDashed, Download, FileJson, FileText, Layers3, Loader2, RefreshCw, X } from 'lucide-react';
import { CopyButton, Empty, EvidenceLabel, JsonTree, Panel, Pill, Reveal, Tabs, VerificationBadge } from '../components/ui.jsx';
import { api, fileUrl, saveBlob } from '../lib/api.js';
import { Markdown } from '../lib/markdown.jsx';
import { useWS } from '../lib/workspace.js';

const ARTIFACT_NAMES = { scan: 'Repository scan', usage: 'Usage tracing', ai_analysis: 'Gemma 4 analysis', verification: 'Verification' };
const LABEL_KEYS = { scan: 'scan_findings', usage: 'usage', ai_analysis: 'ai_analysis', verification: 'verification' };

export default function Capsule() {
  const { view, runId, toast, reload, offline } = useWS();
  const [tab, setTab] = useState('preview');
  const [full, setFull] = useState(null);
  const [fullState, setFullState] = useState('idle');
  const [rebuilding, setRebuilding] = useState(false);
  const c = view.capsule;

  useEffect(() => { setFull(null); setFullState('idle'); }, [runId, c?.verification_status, view.ai]);
  useEffect(() => {
    if (tab !== 'json' || full || offline || fullState !== 'idle') return;
    setFullState('loading');
    api.capsuleJson(runId).then((d) => { setFull(d); setFullState('ready'); }).catch((e) => { setFullState('error'); toast(e.message, 'bad'); });
  }, [tab, full, offline, runId, fullState, toast]);

  if (!c) return <Empty icon={Layers3} title="No capsule for this run">The engine builds the capsule after every scan, verification or AI import. Use Rebuild if it is missing.</Empty>;

  async function rebuild() {
    setRebuilding(true);
    try { await api.rebuild(runId); toast('Capsule rebuilt from the stored artifacts'); setFull(null); reload(); } catch (e) { toast(e.message, 'bad'); } finally { setRebuilding(false); }
  }
  const states = c.artifact_states || [];
  const diagLabel = c.labels?.diagnosis;

  return (
    <>
      <Reveal i={0} className="capsule-hero">
        <div className="capsule-icon"><Layers3 size={24} /></div>
        <div className="capsule-hero-text">
          <div className="row-wrap">
            <Pill tone={c.overall_status === 'VERIFIED_CHANGE' ? 'good' : 'warn'} className="pill-large">Overall {c.overall_status}</Pill>
            <VerificationBadge status={c.verification_status} />
          </div>
          <h2>Carry the evidence forward.</h2>
          <p>{c.interpretation}</p>
        </div>
        <div className="capsule-actions">
          {offline ? (
            <>
              <button type="button" className="button button-outline" onClick={() => saveBlob('loaded-artifacts.json', JSON.stringify({ note: 'Offline view: artifacts loaded in the browser; not an engine-built capsule.', ...view.rawArtifacts, assessment: c.verification_assessment }, null, 2))}><FileJson size={16} /> Export loaded artifacts</button>
              <small className="muted">Official JSON and Markdown capsules are built by the engine.</small>
            </>
          ) : (
            <>
              <a className="button button-blue" href={fileUrl(runId, 'dependency-exit-capsule.json')} download><FileJson size={16} /> Export JSON <Download size={14} /></a>
              <a className="button button-outline" href={fileUrl(runId, 'dependency-exit-capsule.md')} download><FileText size={16} /> Export Markdown <Download size={14} /></a>
              <button type="button" className="ghost-btn" onClick={rebuild} disabled={rebuilding}>{rebuilding ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} Rebuild capsule</button>
            </>
          )}
        </div>
      </Reveal>

      <div className="capsule-layout">
        <Reveal i={1}>
          <Panel title="What the capsule contains" subtitle="Missing artifacts are recorded as missing">
            <ul className="capsule-checks">
              {states.map((s) => {
                const ok = s.state === 'available';
                return (
                  <li key={s.artifact} className={ok ? 'ok' : ''}>
                    <span className={`check-box ${ok ? 'checked' : ''}`}>{ok ? <Check size={12} /> : <CircleDashed size={12} />}</span>
                    <span>{ARTIFACT_NAMES[s.artifact] || s.artifact}</span>
                    {ok ? <EvidenceLabel label={c.labels?.[LABEL_KEYS[s.artifact]] || 'OBSERVED'} /> : <Pill tone="warn">{s.state.replaceAll('_', ' ')}</Pill>}
                  </li>
                );
              })}
              <li className={diagLabel ? 'ok' : ''}>
                <span className={`check-box ${diagLabel ? 'checked' : ''}`}>{diagLabel ? <Check size={12} /> : <CircleDashed size={12} />}</span>
                <span>Root-cause candidates</span>
                {diagLabel ? <EvidenceLabel label="HYPOTHESIS" /> : <Pill tone="muted">not included</Pill>}
              </li>
            </ul>
            {(c.missing_artifact_notices || []).length > 0 && (
              <div className="panel-pad notices">
                {c.missing_artifact_notices.map((n, i) => <p key={i}><AlertTriangle size={13} /> {n}</p>)}
              </div>
            )}
            <div className="panel-pad">
              <span className="obs-label">Rollback</span>
              {(c.rollback || []).length ? c.rollback.map((r, i) => <p key={i} className="small"><EvidenceLabel label="AI PROPOSAL" /> Option {r.option_index + 1}: {r.rollback}</p>) : <p className="muted small">{c.rollback_note}</p>}
            </div>
            {!offline && view.files.length > 0 && (
              <div className="panel-pad file-links">
                <span className="obs-label">Individual artifacts</span>
                {view.files.filter((f) => !f.startsWith('dependency-exit-capsule')).map((f) => <a key={f} className="ghost-btn" href={fileUrl(runId, f)} download><Download size={13} /> {f}</a>)}
              </div>
            )}
          </Panel>
        </Reveal>
        <Reveal i={2}>
          <Panel title="Capsule" className="capsule-viewer"
            actions={<Tabs label="Capsule view" value={tab} onChange={setTab} tabs={[{ value: 'preview', label: 'Preview', icon: FileText }, { value: 'markdown', label: 'Markdown' }, { value: 'json', label: 'JSON', icon: FileJson }]} />}>
            {tab === 'preview' && (view.markdown ? <div className="md-wrap"><Markdown source={view.markdown} /></div> : <p className="panel-pad muted">{offline ? 'The Markdown capsule is generated by the engine.' : 'Markdown not generated yet — rebuild the capsule.'}</p>)}
            {tab === 'markdown' && (view.markdown ? (
              <div className="md-source"><div className="codeblock-head"><span>dependency-exit-capsule.md</span><CopyButton text={view.markdown} label="Copy Markdown" /></div><pre tabIndex={0}>{view.markdown}</pre></div>
            ) : <p className="panel-pad muted">Not available.</p>)}
            {tab === 'json' && (offline ? <div className="panel-pad"><JsonTree data={{ ...c, ...view.rawArtifacts }} /></div>
              : !full ? (fullState === 'error' ? <p className="panel-pad tone-text-bad"><X size={14} /> Could not load the capsule JSON. <button type="button" className="ghost-btn" onClick={() => setFullState('idle')}>Retry</button></p> : <p className="panel-pad muted"><Loader2 size={14} className="spin" /> Loading full capsule…</p>)
              : <div className="panel-pad"><JsonTree data={full} /></div>)}
          </Panel>
        </Reveal>
      </div>
      <Reveal i={3}>
        <Panel title="Capsule limitations"><ul className="plain-list panel-pad">{(c.limitations || []).map((l, i) => <li key={i}>{l}</li>)}</ul></Panel>
      </Reveal>
    </>
  );
}
