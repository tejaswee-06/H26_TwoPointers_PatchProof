import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, ClipboardCheck, Download, FileJson, FlaskConical, Loader2, Lock, Play, Plus, ShieldCheck, Terminal, Trash2, Upload, X } from 'lucide-react';
import JobProgress from '../components/JobProgress.jsx';
import { CodeBlock, Disclosure, Empty, EvidenceLabel, JsonTree, Panel, Pill, Reveal, Tabs, VerificationBadge } from '../components/ui.jsx';
import { api, fileUrl, readTextFile } from '../lib/api.js';
import { duration, extractPins, joinArgv, tokenize, VERIFICATION_STATUS } from '../lib/model.js';
import { hrefFor } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';

// ---------------------------------------------------------------- config draft helpers
function draftFromConfig(cfg) {
  const lines = (arr) => (arr || []).map(joinArgv);
  const bSetup = lines(cfg?.baseline?.setup); const bCmds = lines(cfg?.baseline?.commands);
  const aSetup = lines(cfg?.after?.setup); const aCmds = lines(cfg?.after?.commands);
  const same = !cfg?.after || (JSON.stringify(aSetup) === JSON.stringify(bSetup) && JSON.stringify(aCmds) === JSON.stringify(bCmds));
  return {
    description: cfg?.description || '', isolation: cfg?.isolation || 'venv', timeout: cfg?.timeout_seconds || 900,
    baselineSetup: bSetup, baselineCmds: bCmds.length ? bCmds : ['{python} -m pytest -q'],
    afterEnabled: !!cfg?.after || !!cfg?.change, sameAsBaseline: same, afterSetup: aSetup, afterCmds: aCmds,
    pins: cfg?.change?.pip_install || [], pipArgs: joinArgv(cfg?.change?.pip_args || []),
  };
}

function configFromDraft(d) {
  const errors = [];
  const parse = (arr, where) => arr.map((l, i) => l.trim()).filter(Boolean).map((l, i) => {
    try { const t = tokenize(l); if (!t.length) throw new Error('empty'); return t; } catch (e) { errors.push(`${where} line ${i + 1}: ${e.message}`); return null; }
  }).filter(Boolean);
  const cfg = { isolation: d.isolation, timeout_seconds: Number(d.timeout) || 900, baseline: { setup: parse(d.baselineSetup, 'Baseline setup'), commands: parse(d.baselineCmds, 'Baseline command') } };
  if (d.description) cfg.description = d.description;
  if (!cfg.baseline.commands.length) errors.push('Add at least one baseline command.');
  if (d.afterEnabled) {
    cfg.after = d.sameAsBaseline ? { setup: cfg.baseline.setup, commands: cfg.baseline.commands }
      : { setup: parse(d.afterSetup, 'After setup'), commands: parse(d.afterCmds, 'After command') };
    if (!cfg.after.commands.length) errors.push('Add at least one after-change command.');
    const pins = d.pins.map((p) => p.trim()).filter(Boolean);
    if (pins.length) {
      cfg.change = { pip_install: pins };
      try { const a = tokenize(d.pipArgs); if (a.length) cfg.change.pip_args = a; } catch (e) { errors.push(`pip arguments: ${e.message}`); }
    }
    if (!pins.length) errors.push('Declare the dependency change to test (for example MarkupSafe==2.0.1). Without a change the result can only be TESTS_PASS_CHANGE_UNVERIFIED.');
    if (pins.length && d.isolation !== 'venv') errors.push('Installing a change requires isolation “venv”; PatchProof refuses to modify the host environment.');
  }
  return { cfg, errors, softErrors: errors.filter((e) => e.startsWith('Declare the dependency change')) };
}

function LinesEditor({ label, hint, lines, onChange, placeholder }) {
  return (
    <div className="lines-editor">
      <div className="lines-head"><span>{label}</span>{hint && <small>{hint}</small>}</div>
      {lines.map((l, i) => (
        <div className="line-row" key={i}>
          <span className="prompt" aria-hidden="true">$</span>
          <input value={l} onChange={(e) => onChange(lines.map((x, k) => (k === i ? e.target.value : x)))} spellCheck={false} aria-label={`${label} ${i + 1}`} placeholder={placeholder} />
          <button type="button" className="icon-btn small" onClick={() => onChange(lines.filter((_, k) => k !== i))} aria-label={`Remove ${label} ${i + 1}`}><Trash2 size={13} /></button>
        </div>
      ))}
      <button type="button" className="ghost-btn" onClick={() => onChange([...lines, ''])}><Plus size={14} /> Add</button>
    </div>
  );
}

// ---------------------------------------------------------------- lab
function Lab({ view, params }) {
  const { runId, trackJob, jobs, toast, reload } = useWS();
  const [draft, setDraft] = useState(null);
  const [source, setSource] = useState('');
  const [mode, setMode] = useState('form');
  const [raw, setRaw] = useState('');
  const [rawError, setRawError] = useState('');
  const [consent, setConsent] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef(null);
  const job = Object.values(jobs).filter((j) => j.kind === 'verify' && j.run_id === runId).slice(-1)[0];
  const running = job && ['queued', 'running'].includes(job.state);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let base; let src;
      if (view.verifyConfig) { base = view.verifyConfig; src = 'the configuration used for the last verification of this run'; }
      else { try { const t = await api.verifyTemplate(runId); base = t.config; src = t.source; } catch (e) { base = null; src = e.message; } }
      if (cancelled) return;
      const d = draftFromConfig(base || {});
      const idx = params.draft != null ? Number(params.draft) : null;
      const opt = idx != null ? view.ai?.options?.[idx] : null;
      if (opt) {
        const pins = extractPins([opt.description, ...(opt.verification_commands || [])].join(' '));
        d.afterEnabled = true; d.sameAsBaseline = true; if (pins.length) d.pins = pins;
        src = `AI option ${idx + 1} (PROPOSED) — review every field; requirement pins were extracted from its text`;
      }
      setDraft(d); setSource(src);
    })();
    return () => { cancelled = true; };
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  const built = useMemo(() => (draft ? configFromDraft(draft) : null), [draft]);
  useEffect(() => { setConsent(false); }, [built && JSON.stringify(built.cfg), raw, mode]); // consent applies to the exact config

  if (!draft) return <Panel title="Verification lab"><div className="panel-pad"><Loader2 className="spin" size={16} /> Preparing configuration…</div></Panel>;
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const hardErrors = mode === 'json' ? (rawError ? [rawError] : []) : built.errors.filter((e) => !built.softErrors.includes(e));
  const cfg = mode === 'json' ? (() => { try { return JSON.parse(raw); } catch { return null; } })() : built.cfg;

  function switchMode(m) {
    if (m === 'json') { setRaw(JSON.stringify({ target: '<TARGET — the scanned folder>', ...built.cfg }, null, 2)); setRawError(''); }
    else if (mode === 'json') {
      try { const c = JSON.parse(raw); setDraft(draftFromConfig(c)); setRawError(''); } catch (e) { setRawError(`JSON: ${e.message}`); return; }
    }
    setMode(m);
  }
  async function loadFile(f) {
    try { const c = JSON.parse(await readTextFile(f)); setDraft(draftFromConfig(c)); setSource(`${f.name} (its "target" is ignored — the scanned folder is used)`); setMode('form'); toast('Configuration loaded'); }
    catch { toast(`${f.name} is not valid JSON`, 'bad'); }
  }
  async function run() {
    setSubmitError(''); setSubmitting(true);
    try {
      const { job: j } = await api.verify(runId, cfg, `Reviewed ${countCommands(cfg)} command(s) in the dashboard and consented to run them.`);
      trackJob(j, (done) => {
        if (done.state === 'succeeded') { toast(`Verification recorded: ${done.result?.status}`, done.result?.verified ? 'good' : 'warn'); }
        else if (done.state === 'cancelled') toast('Verification cancelled; nothing was recorded', 'warn');
        else toast(done.error || 'Verification failed to complete', 'bad');
        reload();
      });
    } catch (e) { setSubmitError(e.message); } finally { setSubmitting(false); }
  }

  const plan = cfg ? planOf(cfg) : [];
  return (
    <>
      <Panel title="Configure the run" subtitle={`Target: the scanned folder “${view.run.root_name}”. Starting point: ${source}.`}
        actions={<>
          <Tabs label="Editor mode" value={mode} onChange={switchMode} tabs={[{ value: 'form', label: 'Form' }, { value: 'json', label: 'JSON', icon: FileJson }]} />
          <button type="button" className="ghost-btn" onClick={() => fileRef.current?.click()}><Upload size={14} /> Load config</button>
          <input ref={fileRef} type="file" hidden accept=".json,application/json" onChange={(e) => { if (e.target.files?.[0]) loadFile(e.target.files[0]); e.target.value = ''; }} />
        </>}>
        {mode === 'json' ? (
          <div className="panel-pad">
            <textarea className="json-editor" value={raw} spellCheck={false} aria-label="Verification config JSON" rows={18}
              onChange={(e) => { setRaw(e.target.value); try { JSON.parse(e.target.value); setRawError(''); } catch (er) { setRawError(`JSON: ${er.message}`); } }} />
            <small className="muted">Same format as <code>verify-config.json</code> in the runbook. <code>target</code> is always replaced with the scanned folder.</small>
          </div>
        ) : (
          <div className="lab-form panel-pad">
            <div className="lab-row">
              <label className="field"><span>Isolation</span>
                <select value={draft.isolation} onChange={(e) => set('isolation', e.target.value)}>
                  <option value="venv">venv — fresh virtual environment per phase (recommended)</option>
                  <option value="none">none — host Python in a copied folder (not isolated; no installs)</option>
                </select>
              </label>
              <label className="field narrow"><span>Timeout per command (s)</span><input type="number" min="10" value={draft.timeout} onChange={(e) => set('timeout', e.target.value)} /></label>
            </div>
            <div className="phase-box">
              <h4><span className="phase-dot base" />Baseline phase</h4>
              <LinesEditor label="Setup command" hint="Runs first; a failure blocks the phase" lines={draft.baselineSetup} onChange={(v) => set('baselineSetup', v)} placeholder="{python} -m pip install -r requirements.txt" />
              <LinesEditor label="Test command" hint="Recorded with exit code and output" lines={draft.baselineCmds} onChange={(v) => set('baselineCmds', v)} placeholder="{python} -m pytest -q" />
            </div>
            <label className="check-row"><input type="checkbox" checked={draft.afterEnabled} onChange={(e) => set('afterEnabled', e.target.checked)} /><span><strong>Test a dependency change</strong><small>Runs an after-change phase in a second disposable copy</small></span></label>
            {draft.afterEnabled && (
              <div className="phase-box after">
                <h4><span className="phase-dot after" />After-change phase</h4>
                <LinesEditor label="Requirement to install" hint="The declared change, e.g. MarkupSafe==2.0.1" lines={draft.pins.length ? draft.pins : ['']} onChange={(v) => set('pins', v)} placeholder="package==version" />
                <label className="field"><span>Extra pip arguments <em>(optional)</em></span><input value={draft.pipArgs} onChange={(e) => set('pipArgs', e.target.value)} placeholder="--index-url https://…" spellCheck={false} /></label>
                <label className="check-row"><input type="checkbox" checked={draft.sameAsBaseline} onChange={(e) => set('sameAsBaseline', e.target.checked)} /><span><strong>Repeat the baseline setup and commands</strong><small>Required for VERIFIED_CHANGE: every baseline command must run again after the change</small></span></label>
                {!draft.sameAsBaseline && <>
                  <LinesEditor label="After setup command" lines={draft.afterSetup} onChange={(v) => set('afterSetup', v)} />
                  <LinesEditor label="After test command" lines={draft.afterCmds} onChange={(v) => set('afterCmds', v)} />
                </>}
              </div>
            )}
            <p className="muted small"><code>{'{python}'}</code> is replaced by the phase's interpreter. Commands run as argument lists — never through a shell.</p>
          </div>
        )}
        {(built.errors.length > 0 && mode === 'form') && (
          <ul className="form-issues">{built.errors.map((e, i) => <li key={i} className={built.softErrors.includes(e) ? 'soft' : ''}><AlertTriangle size={13} /> {e}</li>)}</ul>
        )}
        {rawError && mode === 'json' && <p className="form-error">{rawError}</p>}
      </Panel>

      <Panel title="Review and consent" subtitle="Nothing runs until you confirm these exact commands" className="consent-panel">
        <div className="panel-pad">
          <ol className="plan">
            {plan.map((p, i) => <li key={i} className={`plan-${p.phase}`}><span className="plan-phase">{p.phase}</span><span className="plan-kind">{p.kind}</span><code>{p.text}</code></li>)}
            {!plan.length && <li className="muted">Fix the configuration to see the plan.</li>}
          </ol>
          <div className="trust">
            <Lock size={16} />
            <p>Each phase runs in a fresh copy of <strong>{view.run.root_name}</strong>{cfg?.isolation === 'venv' ? ' with its own virtual environment' : ' using the host Python (not isolated)'}. Your folder and active environment are not modified. Test commands may execute arbitrary project code, and setup commands have network access.</p>
          </div>
          <label className="check-row consent">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={!cfg || hardErrors.length > 0 || running} />
            <span><strong>I have reviewed these {plan.length} command(s) and consent to running them</strong><small>Consent applies to this exact configuration; editing it clears the checkbox.</small></span>
          </label>
          {submitError && <p className="form-error" role="alert">{submitError}</p>}
          <div className="form-actions">
            <button type="button" className="button button-blue" onClick={run} disabled={!consent || !cfg || hardErrors.length > 0 || running || submitting}>
              {running ? <><Loader2 size={15} className="spin" /> Verification running</> : <><Play size={15} /> Run verification</>}
            </button>
          </div>
        </div>
      </Panel>
      {job && <LiveRun job={job} />}
    </>
  );
}

function countCommands(cfg) { return planOf(cfg).length; }
function planOf(cfg) {
  const out = [];
  for (const ph of ['baseline', 'after']) {
    if (!cfg?.[ph]) continue;
    for (const s of cfg[ph].setup || []) out.push({ phase: ph, kind: 'setup', text: joinArgv(s) });
    if (ph === 'after' && cfg.change?.pip_install?.length) out.push({ phase: ph, kind: 'change', text: joinArgv(['{python}', '-m', 'pip', 'install', ...(cfg.change.pip_args || []), ...cfg.change.pip_install]) });
    for (const c of cfg[ph].commands || []) out.push({ phase: ph, kind: 'test', text: joinArgv(c) });
  }
  return out;
}

function LiveRun({ job }) {
  const cmds = [];
  for (const e of job.events) {
    if (e.event === 'command_started') cmds.push({ ...e, done: false });
    if (e.event === 'command_finished') {
      const c = [...cmds].reverse().find((x) => !x.done && x.display === e.display && x.phase === e.phase);
      if (c) Object.assign(c, e, { done: true });
    }
  }
  const active = ['queued', 'running'].includes(job.state);
  return (
    <JobProgress job={job} title="Verification run">
      {cmds.length > 0 && (
        <ol className="cmd-timeline" aria-label="Command timeline">
          {cmds.map((c, i) => (
            <li key={i} className={`tl tl-${c.done ? c.status : 'running'}`}>
              <span className="tl-dot">{c.done ? (c.status === 'passed' ? <Check size={11} /> : <X size={11} />) : <Loader2 size={11} className="spin" />}</span>
              <span className="tl-phase">{c.phase}</span><span className="tl-kind">{c.kind}</span>
              <code>{c.display}</code>
              <span className="tl-meta">{c.done ? `exit ${c.exit_code ?? '—'} · ${duration(c.duration_seconds)}` : 'running…'}</span>
            </li>
          ))}
        </ol>
      )}
      {!active && job.log_tail?.length > 0 && <Disclosure summary="Runner log"><CodeBlock>{job.log_tail.join('\n')}</CodeBlock></Disclosure>}
    </JobProgress>
  );
}

// ---------------------------------------------------------------- results
function CommandRow({ c }) {
  const tone = c.status === 'passed' ? 'good' : c.status === 'not_started' || c.status === 'timeout' ? 'warn' : 'bad';
  return (
    <li className={`cmd-result tone-${tone}`}>
      <div className="cmd-line">
        <span className="tl-dot">{c.passed ? <Check size={11} /> : <X size={11} />}</span>
        <code>{c.display || joinArgv(c.command)}</code>
      </div>
      <div className="cmd-meta">
        <Pill tone={tone}>{c.status}</Pill>
        <span>exit <strong>{c.exit_code ?? '—'}</strong></span>
        <span>{duration(c.duration_seconds)}</span>
        {c.test_summary && <span className="cmd-summary">{c.test_summary}</span>}
        {c.timed_out && <Pill tone="warn">timed out</Pill>}
      </div>
      {c.error && <p className="tone-text-bad small">{c.error}</p>}
      {(c.stdout || c.stderr) && (
        <Disclosure summary={`Output${c.output_truncated ? ' (truncated by the runner)' : ''}`}>
          {c.stdout && <CodeBlock label="stdout">{c.stdout}</CodeBlock>}
          {c.stderr && <CodeBlock label="stderr">{c.stderr}</CodeBlock>}
        </Disclosure>
      )}
    </li>
  );
}

function PhaseColumn({ name, phase, env }) {
  if (!phase) {
    return (
      <div className="phase-col empty">
        <h4>{name}</h4>
        <p className="muted small">{name === 'After change' ? 'No after-change phase was recorded.' : 'The baseline did not run.'}</p>
      </div>
    );
  }
  return (
    <div className={`phase-col ${phase.passed ? 'ok' : 'fail'}`}>
      <div className="phase-col-head">
        <h4>{name}</h4>
        <Pill tone={phase.passed ? 'good' : 'bad'}>{phase.passed ? 'passed' : 'failed'}</Pill>
      </div>
      <p className="phase-summary">{phase.test_summary || 'No test summary line was captured.'}</p>
      {env && <p className="muted small">Python {env.python_version || '?'} ({env.python_implementation || '?'}) on {env.os} {env.os_release} · {env.environment_isolated ? 'isolated venv' : 'NOT isolated'}</p>}
      {(phase.setup || []).length > 0 && (
        <Disclosure summary={`${phase.setup.length} setup / change command${phase.setup.length === 1 ? '' : 's'}`}>
          <ul className="cmd-results">{phase.setup.map((c, i) => <CommandRow key={i} c={c} />)}</ul>
        </Disclosure>
      )}
      <ul className="cmd-results">{(phase.commands || []).map((c, i) => <CommandRow key={i} c={c} />)}</ul>
      {(phase.file_edits || []).length > 0 && <Disclosure summary="File edits"><ul className="plain-list">{phase.file_edits.map((e, i) => <li key={i}><code>{e.file}</code> {e.applied ? 'applied' : `not applied: ${e.error}`}</li>)}</ul></Disclosure>}
    </div>
  );
}

function Results({ view, rid }) {
  const v = view.verification;
  const a = view.assessment;
  const meta = VERIFICATION_STATUS[a.status] || VERIFICATION_STATUS.NOT_RUN;
  const downgraded = v.status && v.status !== a.status;
  const diff = v.change?.environment_diff || [];
  const depDiff = v.dependency_state?.difference || [];
  return (
    <>
      <Reveal i={1} className={`status-hero tone-${meta.tone}`}>
        <div className="status-hero-icon">{a.verified ? <ShieldCheck size={26} /> : meta.tone === 'bad' ? <X size={26} /> : <ClipboardCheck size={26} />}</div>
        <div className="status-hero-text">
          <div className="row-wrap"><VerificationBadge status={a.status} large /><EvidenceLabel label={a.label} />{a.legacy && <Pill tone="warn">legacy artifact</Pill>}</div>
          <h2>{meta.label}</h2>
          <p>{meta.meaning}</p>
          <ul className="plain-list">{(a.reasons || []).map((r, i) => <li key={i}>{r}</li>)}</ul>
          {downgraded && <p className="notice-inline"><AlertTriangle size={14} /> The artifact says <code>{v.status}</code>; the capsule re-derived <code>{a.status}</code> from the evidence.</p>}
        </div>
        <div className="status-hero-actions">
          {rid && <a className="button button-outline button-small" href={fileUrl(rid, 'verification.json')} download><Download size={14} /> verification.json</a>}
          {rid && view.files.includes('verification.log') && <a className="ghost-btn" href={fileUrl(rid, 'verification.log')} download>Runner log</a>}
        </div>
      </Reveal>

      <Reveal i={2}>
        <Panel title="Before and after" subtitle="Each phase ran in its own disposable copy">
          <div className="ba-grid panel-pad">
            <PhaseColumn name="Baseline" phase={v.baseline || v.before} env={v.environments?.baseline || v.environment} />
            <div className="ba-change">
              <ArrowRight size={18} />
              <span className="obs-label">Declared change</span>
              {v.change?.declared ? (
                <>
                  {(v.change.pip_install || []).map((p) => <code key={p}>{p}</code>)}
                  <Pill tone={v.change.applied_with_evidence ? 'good' : 'warn'}>{v.change.applied_with_evidence ? 'applied with evidence' : 'not evidenced'}</Pill>
                </>
              ) : <span className="muted small">none</span>}
            </div>
            <PhaseColumn name="After change" phase={v.after} env={v.environments?.after} />
          </div>
        </Panel>
      </Reveal>

      <div className="two-col">
        <Reveal i={3}>
          <Panel title="Environment difference" subtitle="Captured with pip list before and after">
            {diff.length || depDiff.length ? (
              <table className="diff-table">
                <thead><tr><th>Package</th><th>Before</th><th>After</th></tr></thead>
                <tbody>{(diff.length ? diff : depDiff).map((d) => <tr key={d.package}><td><code>{d.package}</code></td><td>{d.before ?? '—'}</td><td>{d.after ?? '—'}</td></tr>)}</tbody>
              </table>
            ) : <p className="panel-pad muted small">{v.after ? 'No package versions changed between phases.' : 'Needs both phases to compare.'}</p>}
            {(v.change?.manifest_diff || []).map((m, i) => <CodeBlock key={i} label={m.file}>{m.diff}</CodeBlock>)}
          </Panel>
        </Reveal>
        <Reveal i={4}>
          <Panel title="Isolation and trust boundary">
            <ul className="kv-list">
              <li><span>Requested isolation</span><strong>{v.isolation?.requested ?? '—'}</strong></li>
              <li><span>Baseline isolated</span><strong>{String(v.isolation?.baseline_isolated ?? '—')}</strong></li>
              <li><span>After isolated</span><strong>{String(v.isolation?.after_isolated ?? '—')}</strong></li>
              <li><span>Disposable working copy</span><strong>{String(v.isolation?.working_copy_used ?? '—')}</strong></li>
            </ul>
            <div className="panel-pad">
              {v.isolation?.note && <p className="small">{v.isolation.note}</p>}
              {v.trust_boundary && <p className="muted small">{v.trust_boundary}</p>}
              {(v.blockers || []).length > 0 && <div className="form-error"><strong>Blockers</strong>{v.blockers.map((b, i) => <div key={i}>• {b}</div>)}</div>}
            </div>
          </Panel>
        </Reveal>
      </div>
      <Reveal i={5}>
        <Disclosure summary="Limitations of this verification" className="limits"><ul className="plain-list">{(v.limitations || []).map((l, i) => <li key={i}>{l}</li>)}</ul></Disclosure>
        <Disclosure summary="Raw verification.json" className="limits"><JsonTree data={v} /></Disclosure>
      </Reveal>
    </>
  );
}

export default function Verification({ params }) {
  const { view, runId, offline } = useWS();
  const rid = offline ? undefined : runId;
  return (
    <>
      {view.verification ? <Results view={view} rid={rid} /> : (
        <Reveal i={0}>
          <Empty icon={ClipboardCheck} title="No verification recorded for this run" compact>
            {view.run.can_verify ? 'Configure the run below. PatchProof records exactly what happens — a failing baseline is useful evidence too.' : 'The status stays NOT_RUN. Nothing has been inferred from the AI analysis or the scan.'}
          </Empty>
        </Reveal>
      )}
      {view.run.can_verify ? (
        <section className="lab" aria-label="Verification lab">
          <h2 className="lab-title"><FlaskConical size={18} /> {view.verification ? 'Run another verification' : 'Run a verification'}</h2>
          <Lab view={view} params={params} />
        </section>
      ) : !offline && (
        <Reveal className="notice notice-info"><Terminal size={17} /><div><strong>Verification needs the repository folder</strong><p>{view.run.source === 'bundled' || view.run.source === 'import' ? 'This run holds imported evidence, so there is no local folder to copy. Scan the repository on this computer, then verify that run.' : 'The scanned folder is no longer available at its original location.'}</p></div><a className="button button-outline button-small" href={hrefFor('runs')}>Scan a folder</a></Reveal>
      )}
    </>
  );
}
