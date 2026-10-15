import React, { useState } from 'react';
import { ArrowRight, ChevronDown, FileCode2, Microscope, Package, Terminal } from 'lucide-react';
import { CopyButton, Disclosure, Empty, EvidenceLabel, Loc, Panel, Pill, Reveal } from '../components/ui.jsx';
import { joinArgv, SUPPORT_META } from '../lib/model.js';
import { RichText } from '../lib/markdown.jsx';
import { hrefFor } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';

const SOURCE_LABEL = { scan: 'Manifest scan', usage: 'Usage tracing', verification: 'Verification output' };
const TYPE_LABEL = {
  runtime_import_incompatibility: 'Runtime import incompatibility', missing_module: 'Missing module',
  manifest_inconsistency: 'Manifest inconsistency', runtime_failure_unclassified: 'Unclassified failure',
};

function Candidate({ c, open, onToggle, rid }) {
  const sup = SUPPORT_META[c.support] || { tone: 'muted', label: c.support };
  const groups = c.observed.reduce((acc, o) => { (acc[o.source] ||= []).push(o); return acc; }, {});
  return (
    <article className={`candidate ${open ? 'open' : ''}`} id={`ev-${c.id}`}>
      <button type="button" className="candidate-head" onClick={onToggle} aria-expanded={open}>
        <span className="cand-icon"><Microscope size={17} /></span>
        <span className="cand-title">
          <strong><RichText text={c.title} /></strong>
          <small><code>{c.id}</code> · {TYPE_LABEL[c.type] || c.type}</small>
        </span>
        <span className="finding-pills"><EvidenceLabel label="HYPOTHESIS" /><Pill tone={sup.tone}>{sup.label}</Pill></span>
        <ChevronDown size={16} className={`chev ${open ? 'rot' : ''}`} />
      </button>
      {open && (
        <div className="candidate-body">
          {c.packages?.length > 0 && <div className="row-wrap">{c.packages.map((p) => <a key={p} className="chip-link" href={hrefFor('usage', { run: rid, pkg: p })}><Package size={13} />{p}</a>)}</div>}
          <div className="cand-grid">
            <div className="cand-observed">
              <h4><EvidenceLabel label="OBSERVED" /> What the artifacts show</h4>
              {Object.entries(groups).map(([src, items]) => (
                <div className="obs-group" key={src}>
                  <span className="obs-label">{SOURCE_LABEL[src] || src}</span>
                  <ul className="obs-items">
                    {items.map((o, i) => (
                      <li key={i} className={`obs-${o.kind}`}>
                        {o.file ? <Loc file={o.file} line={o.line} /> : null}
                        <span className="obs-text">{o.kind === 'traceback_frame' ? <span className="muted">{/\(project\)$/.test(o.text) ? 'your code' : /\(installed\)$/.test(o.text) ? 'installed package' : 'frame'}</span>
                          : o.kind === 'error_line' || o.kind === 'command_failure' ? <code>{o.text}</code> : <RichText text={o.text} />}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <div className="cand-reasoning">
              <div className="inf">
                <h4>Inferred, not observed</h4>
                <p><RichText text={c.inferred} /></p>
              </div>
              <div className="uncertain">
                <h4>Uncertainty</h4>
                <ul className="plain-list">{(c.uncertainties || []).map((u, i) => <li key={i}><RichText text={u} /></li>)}</ul>
              </div>
              {c.discriminating_checks?.length > 0 && (
                <div className="checks">
                  <h4>Checks that would discriminate <EvidenceLabel label="NOT_RUN" /></h4>
                  <ul className="plain-list">
                    {c.discriminating_checks.map((ch, i) => (
                      <li key={i}>
                        <span><RichText text={ch.description} /></span>
                        {ch.command && <div className="cmd-row"><code>{joinArgv(ch.command).replace('{python}', 'python')}</code><CopyButton text={joinArgv(ch.command).replace('{python}', 'python')} /></div>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {c.related_ids?.length > 0 && (
                <div className="related">
                  <span className="obs-label">Related evidence</span>
                  {c.related_ids.map((id) => <a key={id} className="related-link" href={hrefFor('findings', { run: rid, id })}><code>{id}</code><ArrowRight size={13} /></a>)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function FailureChain({ f }) {
  const frames = f.frames || [];
  const shown = frames.length > 8 ? [...frames.slice(0, 2), null, ...frames.slice(-5)] : frames;
  return (
    <div className="failure">
      <div className="failure-head">
        <Terminal size={15} />
        <code className="failure-cmd">{f.command}</code>
        <Pill tone="bad">exit {f.exit_code ?? '—'}</Pill>
        <Pill tone="muted">{f.phase}</Pill>
      </div>
      {f.test_summary && <p className="muted small">{f.test_summary}</p>}
      {f.errors?.length > 0 && <div className="error-lines">{f.errors.slice(0, 4).map((e, i) => <code key={i}>{e.text}</code>)}</div>}
      {shown.length > 0 && (
        <ol className="frame-chain" aria-label="Traceback frames, outermost first">
          {shown.map((fr, i) => fr === null
            ? <li key={`gap-${i}`} className="frame-gap">… {frames.length - 7} more frames</li>
            : <li key={i} className={`frame frame-${fr.origin}`}><FileCode2 size={13} /><Loc file={fr.file} line={fr.line} /><span>{fr.origin === 'project' ? 'your code' : fr.origin === 'installed' ? 'installed package' : 'unknown'}</span></li>)}
        </ol>
      )}
      {f.failing_tests?.length > 0 && (
        <div className="failing-tests"><span className="obs-label">Failing tests</span>{f.failing_tests.map((t, i) => <code key={i}>{t.test}</code>)}</div>
      )}
    </div>
  );
}

export default function RootCause({ params }) {
  const { view, runId, offline } = useWS();
  const d = view.diagnosis;
  const [open, setOpen] = useState(() => new Set(params.id ? [params.id] : view.candidates.slice(0, 1).map((c) => c.id)));
  const rid = offline ? undefined : runId;
  if (!d) {
    return <Empty icon={Microscope} title="Diagnosis unavailable">{offline ? 'Root-cause correlation runs in the engine. Start it to derive candidate causes from these files.' : 'The engine did not produce a diagnosis for this run. Use “Rebuild capsule” on the Exit Capsule page.'}</Empty>;
  }
  const failures = d.observed_failures || [];
  return (
    <>
      <Reveal i={0} className="cause-summary">
        <div><strong>{d.summary.candidate_count}</strong><small>Candidate causes</small></div>
        <div><strong>{d.summary.runtime_failures_observed}</strong><small>Baseline failures parsed</small></div>
        <div><strong>{d.summary.supported_by_verification}</strong><small>Supported by verification</small></div>
        <p className="muted small">Every candidate is a hypothesis. “Supported by verification” only means a recorded, verified change touching the same packages made the recorded commands pass.</p>
      </Reveal>
      <Reveal i={1}>
        <Panel title="Candidate causes" subtitle="Observed evidence on the left, inference and uncertainty on the right">
          {view.candidates.length ? view.candidates.map((c) => (
            <Candidate key={c.id} c={c} rid={rid} open={open.has(c.id)} onToggle={() => setOpen((s) => { const n = new Set(s); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); return n; })} />
          )) : (
            <Empty icon={Microscope} title="No candidate causes" compact
              actions={view.run.can_verify ? <a className="button button-outline button-small" href={hrefFor('verification', { run: rid })}>Open the verification lab</a> : null}>
              {d.inputs?.verification ? 'The artifacts contain no failures or manifest conflicts to explain.' : 'No manifest conflicts were found, and runtime causes need captured command output — run a verification first.'}
            </Empty>
          )}
        </Panel>
      </Reveal>
      <Reveal i={2}>
        <Panel title="Observed failures" subtitle="Parsed from the failing commands recorded in verification.json">
          <div className="panel-pad">
            {failures.length ? failures.map((f) => <FailureChain key={f.id} f={f} />) : <p className="muted small">{d.inputs?.verification ? 'No failing commands were recorded.' : 'No verification artifact — nothing to parse yet.'}</p>}
          </div>
        </Panel>
      </Reveal>
      <Reveal i={3}>
        <Disclosure summary="Diagnosis limitations" className="limits">
          <ul className="plain-list">{(d.limitations || []).map((l, i) => <li key={i}>{l}</li>)}</ul>
        </Disclosure>
      </Reveal>
    </>
  );
}
