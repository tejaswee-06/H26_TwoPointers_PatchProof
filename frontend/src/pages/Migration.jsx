import React, { useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Bot, Download, FlaskConical, Play, RotateCcw, ShieldAlert, Sparkles, Trash2, Upload } from 'lucide-react';
import JobProgress from '../components/JobProgress.jsx';
import { Disclosure, Empty, EvidenceLabel, Panel, Pill, Reveal, VerificationBadge } from '../components/ui.jsx';
import { api, fileUrl, readTextFile } from '../lib/api.js';
import { normalizeCommand, recordedCommands } from '../lib/model.js';
import { hrefFor, navigate } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';

function CompatibilityEvidence({ view, rid }) {
  const v = view.verification;
  const runtime = view.candidates.filter((c) => c.type === 'runtime_import_incompatibility' || c.type === 'missing_module');
  const manifest = view.candidates.filter((c) => c.type === 'manifest_inconsistency');
  return (
    <Panel title="Compatibility evidence" subtitle="Supplied by the engine — reproducible errors and recorded changes" actions={<EvidenceLabel label="OBSERVED" />}>
      <div className="compat-grid panel-pad">
        <div>
          <span className="obs-label">Reproduced runtime errors</span>
          {runtime.length ? runtime.map((c) => {
            const err = c.observed.find((o) => o.kind === 'error_line');
            return <a key={c.id} className="compat-item" href={hrefFor('root-cause', { run: rid, id: c.id })}><code>{err?.text || c.title}</code><small>{c.packages.join(' + ')} · {c.id}</small></a>;
          }) : <p className="muted small">{v ? 'No dependency-related runtime error was parsed from the recorded output.' : 'No verification output yet.'}</p>}
        </div>
        <div>
          <span className="obs-label">Declaration conflicts</span>
          {manifest.length ? manifest.map((c) => <a key={c.id} className="compat-item" href={hrefFor('findings', { run: rid, id: c.related_ids?.[0] })}><code>{c.observed.filter((o) => o.kind === 'declaration').map((o) => `${o.file}:${o.line} ${o.text}`).join('  vs  ')}</code><small>{c.packages.join(', ')}</small></a>) : <p className="muted small">None found.</p>}
        </div>
        <div>
          <span className="obs-label">Recorded dependency change</span>
          {v?.change?.declared ? (
            <div className="compat-item static">
              <code>{(v.change.environment_diff || []).map((d) => `${d.package} ${d.before ?? '∅'} → ${d.after ?? '∅'}`).join(', ') || (v.change.pip_install || []).join(', ')}</code>
              <small><VerificationBadge status={view.assessment.status} /></small>
            </div>
          ) : <p className="muted small">No change has been tested.</p>}
        </div>
      </div>
    </Panel>
  );
}

function HypothesesPanel({ hypotheses }) {
  if (!Array.isArray(hypotheses) || !hypotheses.length) return null;
  const list = (items) => (Array.isArray(items) && items.length ? <ul className="plain-list">{items.map((x, k) => <li key={k}>{x}</li>)}</ul> : <p className="muted small">None supplied.</p>);
  return (
    <Panel title="Diagnostic hypotheses" subtitle="Possible causes proposed by the model — not established facts" actions={<EvidenceLabel label="AI PROPOSAL" />}>
      <div className="panel-pad">
        {hypotheses.map((h, i) => (
          <div key={i} className="hypothesis">
            <div className="row-wrap"><strong>{h.hypothesis}</strong><Pill tone={h.confidence === 'high' ? 'warn' : 'muted'}>{h.confidence || 'unknown'} confidence</Pill></div>
            <span className="obs-label">Supporting evidence</span>{list(h.supporting_evidence)}
            <span className="obs-label">Contradicting evidence</span>{list(h.contradicting_evidence)}
            <span className="obs-label">Tests that could tell them apart (NOT_RUN)</span>{list(h.discriminating_tests)}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function OptionCard({ opt, i, recommended, state, recorded, rid, canVerify }) {
  return (
    <article className={`option ${recommended ? 'recommended' : ''}`}>
      <header className="option-head">
        <span className="option-index">Option {i + 1}</span>
        <div className="row-wrap">
          {recommended && <Pill tone="proposal"><Sparkles size={12} /> Model's recommendation</Pill>}
          <EvidenceLabel label={state?.status || 'PROPOSED'} />
        </div>
      </header>
      <h4>{opt.description}</h4>
      <div className="option-cols">
        <div><span className="obs-label">Benefits</span>{opt.benefits?.length ? <ul className="plain-list">{opt.benefits.map((b, k) => <li key={k}>{b}</li>)}</ul> : <p className="muted small">None stated.</p>}</div>
        <div><span className="obs-label">Risks</span>{opt.risks?.length ? <ul className="plain-list risk">{opt.risks.map((b, k) => <li key={k}>{b}</li>)}</ul> : <p className="muted small">None stated.</p>}</div>
      </div>
      {opt.files_to_change?.length > 0 && <div className="row-wrap files"><span className="obs-label">Files to change</span>{opt.files_to_change.map((f) => <code key={f}>{f}</code>)}</div>}
      <div className="option-tests">
        <span className="obs-label">Proposed test commands</span>
        {opt.verification_commands?.length ? (
          <ul className="cmd-list">
            {opt.verification_commands.map((c, k) => {
              const hits = recorded.filter((r) => r.norm === normalizeCommand(c));
              return (
                <li key={k}>
                  <code>{c}</code>
                  {hits.length ? <Pill tone="observed" title="The same command appears in the recorded verification (the option itself is still a proposal)">recorded · {hits.map((h) => `${h.phase} exit ${h.cmd.exit_code ?? '—'}`).join(' · ')}</Pill> : <EvidenceLabel label="NOT_RUN" />}
                </li>
              );
            })}
          </ul>
        ) : <p className="muted small">No test commands proposed.</p>}
      </div>
      <div className="rollback"><RotateCcw size={14} /><div><span className="obs-label">Rollback (proposed)</span><p>{opt.rollback || 'No rollback guidance supplied.'}</p></div></div>
      {canVerify && <button type="button" className="button button-outline button-small" onClick={() => navigate('verification', { run: rid, draft: i })}><FlaskConical size={14} /> Draft a verification from this option</button>}
    </article>
  );
}

export default function Migration() {
  const { view, runId, health, toast, reload, trackJob, jobs, offline } = useWS();
  const ref = useRef(null);
  const [error, setError] = useState(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const rid = offline ? undefined : runId;
  const adapter = health?.ai_adapter;
  const ai = view.ai;
  const val = view.aiValidation;
  const recorded = useMemo(() => recordedCommands(view.verification), [view.verification]);
  const knownIds = new Set([...view.all.map((f) => f.id), ...view.candidates.map((c) => c.id)]);
  const aiJob = Object.values(jobs).filter((j) => j.kind === 'ai' && j.run_id === runId).slice(-1)[0];

  async function importAi(file) {
    setError(null);
    let data;
    try { data = JSON.parse(await readTextFile(file)); } catch { setError({ message: `${file.name} is not valid JSON.` }); return; }
    try {
      const res = await api.storeAi(runId, data);
      toast(`AI analysis stored as a proposal${res.validation.warnings.length ? ` with ${res.validation.warnings.length} warning(s)` : ''}`);
      reload();
    } catch (e) { setError({ message: e.message, errors: e.data?.validation?.errors }); }
  }
  async function runAdapter() {
    try { const { job } = await api.runAi(runId); trackJob(job, (j) => { if (j.state === 'succeeded') { toast('Gemma 4 analysis stored as a proposal'); reload(); } else toast(j.error || `Analysis ${j.state}`, 'bad'); }); } catch (e) { toast(e.message, 'bad'); }
  }
  async function remove() {
    try { await api.removeAi(runId); setConfirmRemove(false); toast('AI analysis removed'); reload(); } catch (e) { toast(e.message, 'bad'); }
  }

  return (
    <>
      <Reveal i={0}><CompatibilityEvidence view={view} rid={rid} /></Reveal>
      <Reveal i={1}>
        <section className={`ai-stage ${ai ? 'has-ai' : 'pending'}`} aria-labelledby="ai-title">
          <div className="ai-orb" aria-hidden="true"><Bot size={26} /></div>
          <div className="ai-content">
            <div className="row-wrap"><EvidenceLabel label="AI PROPOSAL" /><Pill tone={adapter?.state === 'READY' ? 'good' : 'warn'}>Adapter: {adapter?.state === 'READY' ? 'ready' : adapter?.state === 'NOT_CONNECTED' ? 'not connected' : (adapter?.state || 'unknown').toLowerCase()}</Pill></div>
            <h2 id="ai-title">{ai ? 'Gemma 4 migration analysis' : 'The reasoning layer is waiting for Gemma 4'}</h2>
            {ai ? (
              <p>Model <code>{ai.model}</code> on <code>{ai.runtime}</code> analysed {(ai.finding_ids || []).length} evidence ID(s). Everything below is a proposal; only the verification lab can change a status.</p>
            ) : (
              <p>No analysis exists for this run yet, and none was generated in its place. The local Gemma 4 adapter reports the state shown above (it needs a running local Ollama with the model pulled). {adapter?.reason}</p>
            )}
            {!ai && (
              <div className="integration-card">
                <span className="obs-label">Integration point</span>
                <code>{adapter?.integration_point || 'patchproof/ai/__init__.py: analyze(bundle, timeout_seconds) -> dict'}</code>
                <small>Contract: docs/AI_INTEGRATION.md. Start Ollama locally with the Gemma 4 model pulled and the button below becomes active.</small>
              </div>
            )}
            <div className="ai-actions">
              <button type="button" className="button button-blue" onClick={runAdapter} disabled={offline || adapter?.state !== 'READY' || ['queued', 'running'].includes(aiJob?.state)}
                title={adapter?.state !== 'READY' ? 'Gemma 4 adapter not connected' : 'Send the evidence bundle to the local model'}><Play size={15} /> Run Gemma 4 analysis</button>
              <a className={`button button-outline ${offline ? 'disabled' : ''}`} href={offline ? undefined : fileUrl(runId, 'ai-input.json')} download="ai-input.json" aria-disabled={offline}><Download size={15} /> Evidence bundle for Gemma 4</a>
              <button type="button" className="button button-outline" onClick={() => ref.current?.click()} disabled={offline}><Upload size={15} /> Import ai-analysis.json</button>
              <input ref={ref} type="file" hidden accept=".json,application/json" onChange={(e) => { if (e.target.files?.[0]) importAi(e.target.files[0]); e.target.value = ''; }} />
              {ai && !offline && (confirmRemove
                ? <span className="confirm"><button type="button" className="ghost-btn tone-text-bad" onClick={remove}>Confirm removal</button><button type="button" className="ghost-btn" onClick={() => setConfirmRemove(false)}>Keep</button></span>
                : <button type="button" className="ghost-btn" onClick={() => setConfirmRemove(true)}><Trash2 size={14} /> Remove analysis</button>)}
            </div>
            {error && <div className="form-error" role="alert"><strong>{error.message}</strong>{error.errors?.map((x, i) => <div key={i}>• {x}</div>)}</div>}
            <ul className="ai-rules"><li>Evidence-linked by ID</li><li>Options, risks, tests and rollback</li><li>Never sets a verified status</li></ul>
          </div>
        </section>
      </Reveal>
      {aiJob && <Reveal><JobProgress job={aiJob} title="Gemma 4 analysis" /></Reveal>}

      {ai ? (
        <>
          {val?.warnings?.length > 0 && (
            <Reveal className="notice notice-warn"><AlertTriangle size={17} /><div><strong>Schema check warnings</strong><ul className="plain-list">{val.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div></Reveal>
          )}
          <Reveal i={2}>
            <Panel title="Analysis" subtitle="Model reasoning over the supplied evidence" actions={<EvidenceLabel label="AI PROPOSAL" />}>
              <div className="panel-pad">
                <p className="analysis-text">{ai.analysis}</p>
                <div className="row-wrap">
                  <span className="obs-label">Evidence cited</span>
                  {(ai.finding_ids || []).map((id) => knownIds.has(id)
                    ? <a key={id} className="chip-link" href={hrefFor(id.startsWith('D-') ? 'root-cause' : 'findings', { run: rid, id })}>{id}</a>
                    : <Pill key={id} tone="bad" title="This ID does not exist in this run's evidence">{id} · unknown</Pill>)}
                </div>
              </div>
            </Panel>
          </Reveal>
          {(ai.diagnostic_hypotheses || []).length > 0 && <Reveal i={3}><HypothesesPanel hypotheses={ai.diagnostic_hypotheses} /></Reveal>}
          <div className="options-grid">
            {(ai.options || []).map((o, i) => (
              <Reveal key={i} i={3 + i}>
                <OptionCard opt={o} i={i} recommended={ai.recommended_option === i} state={val?.option_states?.[i]} recorded={recorded} rid={rid} canVerify={!offline && view.run.can_verify} />
              </Reveal>
            ))}
          </div>
          {(ai.uncertainties || []).length > 0 && (
            <Reveal><Panel title="Model-stated uncertainties"><ul className="plain-list panel-pad">{ai.uncertainties.map((u, i) => <li key={i}>{u}</li>)}</ul></Panel></Reveal>
          )}
        </>
      ) : (
        <Reveal i={2}>
          <Empty icon={ShieldAlert} title="No AI proposals for this run">
            The capsule records the AI analysis as <code>not_provided</code>. Findings, candidate causes and verification remain fully usable without it.
            <Disclosure summary="What Gemma 4 will receive"><p className="small">The evidence bundle holds finding IDs and their manifest lines, usage leads, candidate causes with their observed evidence, and the failing error lines — not the whole repository.</p></Disclosure>
          </Empty>
        </Reveal>
      )}
      {!ai && view.run.can_verify && <p className="muted small center">You can still test a change by hand in the <a href={hrefFor('verification', { run: rid })}>verification lab <ArrowRight size={12} /></a></p>}
    </>
  );
}
