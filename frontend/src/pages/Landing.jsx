import React, { useEffect, useState } from 'react';
import { ArrowDown, ArrowRight, BadgeCheck, Bot, ClipboardCheck, FileCode2, FolderGit2, Layers3, Microscope, ScanSearch } from 'lucide-react';
import ParticleWave from '../components/ParticleWave.jsx';
import { EvidenceLabel } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { buildView } from '../lib/model.js';
import { useWS } from '../lib/workspace.js';

function liveLines(view) {
  if (!view) return [];
  const lines = [];
  const f = view.findings[0];
  if (f) {
    const ev = f.evidence.map((e) => `${e.file}:${e.line} ${e.excerpt}`).join('  vs  ');
    lines.push({ label: 'OBSERVED', text: ev || f.title });
  }
  const fail = view.diagnosis?.observed_failures?.[0];
  if (fail) {
    const t = fail.failing_tests?.[0]?.test;
    const e = fail.errors?.find((x) => x.kind !== 'error') || fail.errors?.[0];
    lines.push({ label: 'OBSERVED', text: `${t ? `${t} — ` : ''}${(e?.text || '').replace(/^E\s+/, '')}` });
  }
  const c = view.candidates.find((x) => x.type !== 'manifest_inconsistency') || view.candidates[0];
  if (c) lines.push({ label: 'HYPOTHESIS', text: c.title });
  lines.push({ label: view.ai ? 'AI PROPOSAL' : 'BLOCKED', text: view.ai ? `${(view.ai.options || []).length} options from ${view.ai.model}` : 'Gemma 4 analysis not connected — nothing generated in its place' });
  const v = view.verification;
  if (v) {
    const diff = (v.change?.environment_diff || []).map((d) => `${d.package} ${d.before} → ${d.after}`).join(', ');
    lines.push({ label: view.assessment.verified ? 'VERIFIED' : 'OBSERVED',
      text: `${diff ? `${diff} · ` : ''}${v.baseline?.test_summary || 'baseline'} → ${v.after?.test_summary || 'no after-run'}` });
  }
  return lines;
}

const CAPS = [
  { key: 'repo', label: 'Repository', title: 'Every claim has a place to click.', body: 'Findings carry stable IDs and point to the exact manifest line that produced them. Cross-manifest conflicts show both declarations side by side.', points: ['Stable F- and U- evidence IDs', 'requirements, pyproject, setup.cfg, setup.py', 'No manifests is reported as not assessed, never clean'], section: 'findings' },
  { key: 'cause', label: 'Root cause', title: 'Failures traced back to packages.', body: 'Captured test output is correlated with declarations, installed versions and import sites to form candidate causes — kept separate from what was observed.', points: ['Observed evidence and inference side by side', 'Transitive dependencies surfaced', 'Discriminating checks marked not run'], section: 'root-cause' },
  { key: 'ai', label: 'AI analysis', title: 'Reasoning that stays a proposal.', body: 'The local Gemma 4 adapter receives a bounded evidence bundle and returns options, risks, tests and rollback steps. The model never marks its own answer verified.', points: ['Schema-validated output', 'Unknown evidence IDs flagged', 'Pending state when the model is not connected'], section: 'migration' },
  { key: 'verify', label: 'Verification', title: 'Before and after, in disposable copies.', body: 'Your exact commands run in a copied project with a fresh virtual environment per phase. Exit codes, output and dependency diffs are recorded as-is.', points: ['Runs only after explicit consent', 'Six explicit statuses, VERIFIED only with evidence', 'Cancel at any point'], section: 'verification' },
  { key: 'capsule', label: 'Exit Capsule', title: 'Hand over the whole record.', body: 'The Dependency Exit Capsule bundles evidence, candidate causes, AI proposals, verification and limitations into JSON and readable Markdown.', points: ['Re-derives status from evidence', 'Missing artifacts stated, never filled in', 'One-click JSON and Markdown export'], section: 'capsule' },
];

export default function Landing({ goApp, motionReduced }) {
  const { engineState } = useWS();
  const [lw, setLw] = useState(null);
  const [cap, setCap] = useState('repo');
  useEffect(() => {
    if (engineState !== 'online') return;
    api.run('bundled-linkwatch').then((d) => setLw(buildView(d))).catch(() => setLw(null));
  }, [engineState]);
  const lines = liveLines(lw);
  const active = CAPS.find((c) => c.key === cap);

  return (
    <main id="main-content" tabIndex={-1} className="landing">
      <section className="hero">
        <ParticleWave reducedMotion={motionReduced} />
        <div className="hero-grid" aria-hidden="true" />
        <div className="hero-glow" aria-hidden="true" />
        <div className="hero-content">
          <p className="eyebrow"><span className="live-dot" /> Evidence-first dependency maintenance</p>
          <h1>Upgrade with proof,<br />not guesswork.</h1>
          <p className="hero-subtitle">PatchProof reads your manifests and source, explains why a dependency breaks, asks a local Gemma 4 model for options, and proves the fix in a disposable environment before anything reaches production.</p>
          <div className="hero-actions">
            <button type="button" className="button button-blue button-large" onClick={() => goApp('overview')}>Open workspace <ArrowRight size={18} /></button>
            <button type="button" className="button button-glass button-large" onClick={() => goApp('overview', { run: 'bundled-linkwatch' })}>Inspect the LinkWatch case</button>
          </div>
        </div>
        <div className="hero-evidence" aria-label="Live evidence from the LinkWatch artifacts">
          <div className="hero-evidence-head">
            <span className="term-dots" aria-hidden="true"><i /><i /><i /></span>
            <span>linkwatch · dependency-exit-capsule</span>
            <span className={`engine-chip engine-${engineState}`}><span className="dot" />{engineState === 'online' ? 'live from engine' : 'engine offline'}</span>
          </div>
          {lines.length ? (
            <ol className="hero-evidence-lines">
              {lines.map((l, i) => (
                <li key={i} style={{ '--i': i }}><EvidenceLabel label={l.label} /><code>{l.text.replaceAll('`', '')}</code></li>
              ))}
            </ol>
          ) : (
            <p className="hero-evidence-empty">{engineState === 'offline' ? 'Start the engine (python -m patchproof.server) to stream the real LinkWatch evidence chain here.' : 'Loading evidence…'}</p>
          )}
        </div>
        <button type="button" className="scroll-cue" onClick={() => document.getElementById('how')?.scrollIntoView({ behavior: motionReduced ? 'auto' : 'smooth' })} aria-label="See how it works"><ArrowDown size={16} /></button>
      </section>

      <section className="flow-strip" aria-label="Workflow">
        {[['Scan', ScanSearch], ['Diagnose', Microscope], ['Reason', Bot], ['Verify', ClipboardCheck], ['Export', Layers3]].map(([l, Icon], i, arr) => (
          <React.Fragment key={l}>
            <div><Icon size={16} /><span>{l}</span></div>
            {i < arr.length - 1 && <ArrowRight size={14} className="flow-arrow" aria-hidden="true" />}
          </React.Fragment>
        ))}
      </section>

      <section className="section how-section" id="how">
        <div className="section-heading-row">
          <h2>Data gets you started.<br /><span>Evidence gets you further.</span></h2>
          <p>Dependency upgrades are not just version numbers. PatchProof connects declarations, source usage, migration reasoning and real verification into one inspectable workflow.</p>
        </div>
        <div className="process-grid">
          <article className="process-card">
            <div className="process-top"><span>Discover</span><FolderGit2 size={18} /></div>
            <div className="process-visual scan-visual">
              <div className="scan-line" />
              <div className="file-chip"><FileCode2 size={15} /> requirements.txt <span>pydantic==1.10.13</span></div>
              <div className="file-chip"><FileCode2 size={15} /> pyproject.toml <span>pydantic&gt;=2</span></div>
            </div>
            <h3>Scan the repository</h3>
            <p>Read supported manifests and source imports without executing anything, and point each finding at the line that produced it.</p>
          </article>
          <article className="process-card">
            <div className="process-top"><span>Reason</span><Bot size={18} /></div>
            <div className="process-visual reason-visual">
              <div className="reason-node">Observed evidence</div>
              <div className="reason-connector" />
              <div className="reason-node active">Candidate cause · Gemma 4 proposal</div>
              <div className="reason-connector" />
              <div className="reason-node">Options, risks, rollback</div>
            </div>
            <h3>Understand the options</h3>
            <p>Candidate causes and model-generated migration options stay visibly separate from what was actually observed.</p>
          </article>
          <article className="process-card">
            <div className="process-top"><span>Prove</span><BadgeCheck size={18} /></div>
            <div className="process-visual verify-visual">
              <div className="terminal-head"><span /><span /><span /><label>verification.json</label></div>
              <div className="terminal-lines">
                <p><i>$</i> python -m pytest -q <b className="term-fail">exit 1</b></p>
                <p className="term-muted">change: markupsafe 3.0.4 → 2.0.1</p>
                <p><i>$</i> python -m pytest -q <b className="term-pass">exit 0</b></p>
              </div>
            </div>
            <h3>Verify before you trust</h3>
            <p>Commands, exit codes, output and environment details are recorded. A suggestion never verifies itself.</p>
          </article>
        </div>
      </section>

      <section className="capabilities-section" id="capabilities">
        <div className="capability-frame">
          <div className="capability-tabs" role="tablist" aria-label="Capabilities">
            {CAPS.map((c) => (
              <button key={c.key} type="button" role="tab" aria-selected={cap === c.key} className={`cap-tab ${cap === c.key ? 'active' : ''}`} onClick={() => setCap(c.key)}>{c.label}</button>
            ))}
          </div>
          <div className="capability-body" role="tabpanel" key={active.key}>
            <div className="cap-copy">
              <h2>{active.title}</h2>
              <p>{active.body}</p>
              <ul>{active.points.map((p) => <li key={p}>{p}</li>)}</ul>
              <button type="button" className="text-link" onClick={() => goApp(active.section)}>Open {active.label.toLowerCase()} <ArrowRight size={16} /></button>
            </div>
            <div className="cap-labels" aria-label="Evidence classes">
              <p className="cap-labels-title">Every item in PatchProof carries one of these labels</p>
              {[['OBSERVED', 'Read from files or captured output'], ['HYPOTHESIS', 'Candidate cause derived from evidence'], ['AI PROPOSAL', 'Model output, not applied'], ['VERIFIED', 'Recorded VERIFIED_CHANGE only'], ['BLOCKED', 'Missing or could not run']].map(([l, d]) => (
                <div className="cap-label-row" key={l}><EvidenceLabel label={l} /><span>{d}</span></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="about-section" id="principle">
        <div>
          <h2>Trust the evidence.<br /><span>Not the confidence.</span></h2>
        </div>
        <p>PatchProof keeps observation, hypotheses, AI proposals and test-verified changes distinct. A passing metadata check is not treated as proof that every runtime path works, and a missing artifact is shown as missing — never quietly filled with sample output.</p>
        <button type="button" className="button button-blue" onClick={() => goApp('runs')}>Scan a repository <ArrowRight size={17} /></button>
      </section>

      <footer className="footer">
        <span className="footer-brand">PatchProof<span className="brand-period">.</span></span>
        <span>Evidence before upgrades.</span>
        <span>Local-first · runs on 127.0.0.1 · no cloud model</span>
        <span>Team TwoPointers · 2026</span>
      </footer>
    </main>
  );
}
