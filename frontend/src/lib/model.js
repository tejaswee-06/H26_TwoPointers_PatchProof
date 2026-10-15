// Pure data helpers shared by every view. No React, no DOM — unit-tested with `node --test`.
// Everything here derives from real artifacts; nothing is invented when a field is missing.

export const VERIFICATION_STATUS = {
  VERIFIED_CHANGE: { tone: 'good', label: 'Verified change', short: 'Verified',
    meaning: 'The declared change was applied in a disposable environment with evidence, and every baseline command passed afterwards.' },
  TESTS_PASS_CHANGE_UNVERIFIED: { tone: 'warn', label: 'Tests pass, change unverified', short: 'Unverified',
    meaning: 'Commands passed, but no declared change was applied with evidence (or the after-run did not repeat every baseline command).' },
  BASELINE_FAILED: { tone: 'bad', label: 'Baseline failed', short: 'Baseline failed',
    meaning: 'The baseline commands failed and no after-change run exists. The failure is recorded evidence, not a verdict on a fix.' },
  VERIFICATION_FAILED: { tone: 'bad', label: 'Verification failed', short: 'Failed',
    meaning: 'The after-change commands failed. The proposed change did not make the recorded commands pass.' },
  BLOCKED: { tone: 'warn', label: 'Blocked', short: 'Blocked',
    meaning: 'Verification could not run to completion (invalid config, environment or setup failure). Nothing was verified.' },
  NOT_RUN: { tone: 'muted', label: 'Not run', short: 'Not run',
    meaning: 'No verification has been run for this repository yet.' },
};

export const EVIDENCE_LABELS = {
  OBSERVED: { tone: 'observed', hint: 'Read directly from repository files or captured command output.' },
  HYPOTHESIS: { tone: 'hypothesis', hint: 'A candidate explanation derived from observed evidence. Not proven.' },
  'AI PROPOSAL': { tone: 'proposal', hint: 'Model output. Remains a proposal until independent verification records a result.' },
  PROPOSED: { tone: 'proposal', hint: 'Suggested by the AI analysis. Not applied, not verified.' },
  NOT_RUN: { tone: 'muted', hint: 'Suggested command. PatchProof has not run it.' },
  VERIFIED: { tone: 'good', hint: 'Recorded by the independent verification runner as VERIFIED_CHANGE.' },
  BLOCKED: { tone: 'warn', hint: 'Unavailable or could not run. Nothing was substituted.' },
};

export const SUPPORT_META = {
  supported_by_verification: { tone: 'good', label: 'Supported by verification' },
  runtime_impact_observed: { tone: 'warn', label: 'Runtime impact observed' },
  change_tested_not_verified: { tone: 'warn', label: 'Change tested, not verified' },
  not_resolved_by_change: { tone: 'bad', label: 'Not resolved by the tested change' },
  not_tested: { tone: 'muted', label: 'Not tested yet' },
};

export const USAGE_STATUS = {
  import_observed: { tone: 'observed', label: 'Import observed' },
  no_static_import_found: { tone: 'warn', label: 'No static import found' },
  mapping_unavailable: { tone: 'warn', label: 'Mapping unavailable' },
  analysis_incomplete: { tone: 'warn', label: 'Analysis incomplete' },
};

export function isUsable(a) {
  return !!a && typeof a === 'object' && !Array.isArray(a)
    && !(['missing', 'unreadable'].includes(a.status) && !('schema_version' in a));
}

// Port of patchproof.capsule.assess_verification — used only for offline imports when the engine is not running.
export function assessVerification(v) {
  if (v == null) return { status: 'NOT_RUN', verified: false, reasons: ['No verification artifact was provided.'], label: 'BLOCKED' };
  if (!isUsable(v)) return { status: 'BLOCKED', verified: false, reasons: ['Verification artifact is missing, unreadable or not an object.'], label: 'BLOCKED' };
  const status = v.status;
  if (status == null) {
    return { status: v.after?.passed ? 'TESTS_PASS_CHANGE_UNVERIFIED' : 'NOT_RUN', verified: false, legacy: true, label: 'OBSERVED',
      reasons: ["Legacy verification artifact without an explicit status or change evidence; a bare 'verified' flag is not accepted as evidence."] };
  }
  if (status !== 'VERIFIED_CHANGE') {
    return { status, verified: false, reasons: [...(v.status_reasons || [])], label: ['BLOCKED', 'NOT_RUN'].includes(status) ? 'BLOCKED' : 'OBSERVED' };
  }
  const problems = [];
  const base = v.baseline || v.before; const after = v.after; const change = v.change || {};
  if (!(base && typeof base === 'object' && base.commands?.length)) problems.push('baseline command results are missing');
  if (!(after && after.passed === true && after.commands?.length && after.commands.every((c) => c.passed === true))) problems.push('after-change results are missing or not all passing');
  if (!(change.declared && change.applied_with_evidence)) problems.push('no applied dependency change with evidence is recorded');
  if (!(v.environments || v.environment)) problems.push('environment details are missing');
  if (problems.length) {
    return { status: 'TESTS_PASS_CHANGE_UNVERIFIED', verified: false, label: 'OBSERVED',
      reasons: [`Artifact claims VERIFIED_CHANGE but is inconsistent: ${problems.join('; ')}.`] };
  }
  return { status: 'VERIFIED_CHANGE', verified: true, label: 'VERIFIED', reasons: [...(v.status_reasons || [])] };
}

// Port of patchproof.server.classify_artifact
export function classifyArtifact(name, data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const rt = data.report_type;
  const map = { scan: 'scan', patchproof_scan: 'scan', usage: 'usage', verification: 'verification', dependency_exit_capsule: 'capsule', diagnosis: 'diagnosis' };
  if (map[rt]) return map[rt];
  const n = String(name || '').toLowerCase();
  if ('model' in data && ('options' in data || 'analysis' in data)) return 'ai';
  if (n.includes('ai-analysis') || n.includes('ai_analysis')) return 'ai';
  if (n.includes('capsule') && ('overall_status' in data || 'verification_status' in data)) return 'capsule';
  if (n.includes('usage') || ('packages' in data && 'review_leads' in data)) return 'usage';
  if (n.includes('verification') || 'verified' in data || 'baseline' in data || 'before' in data) return 'verification';
  if ('findings' in data || 'declarations' in data) return 'scan';
  return null;
}

const SEV_ORDER = { high: 0, review: 1, info: 2 };

export function buildView(detail) {
  if (!detail) return null;
  const a = detail.artifacts || {};
  const scan = isUsable(a.scan) ? a.scan : null;
  const usage = isUsable(a.usage) ? a.usage : null;
  const verification = isUsable(a.verification) ? a.verification : null;
  const ai = isUsable(a.ai) ? a.ai : null;
  const diagnosis = isUsable(a.diagnosis) ? a.diagnosis : null;
  const capsule = detail.capsule || null;
  const assessment = capsule?.verification_assessment || assessVerification(a.verification ?? null);

  const findings = (scan?.findings || []).filter(Boolean).map((f) => ({
    kind: 'finding', id: f.id || null, type: f.type || 'finding', severity: String(f.severity || 'review').toLowerCase(),
    title: f.title || f.package || 'Dependency finding', summary: f.summary || '', package: f.package || null,
    assessment: f.assessment || null, observed: f.observed || null, inferred: f.inferred || null,
    pairs: f.pairs || [], evidence: Array.isArray(f.evidence) ? f.evidence : [], status: f.status || 'observed', raw: f,
  }));
  const leads = (usage?.review_leads || []).filter(Boolean).map((l) => ({
    kind: 'lead', id: l.id || null, type: l.type || 'usage_review', severity: String(l.severity || 'info').toLowerCase(),
    title: l.title || `Review ${l.package}`, summary: l.summary || '', package: l.package || null, usageStatus: l.usage_status,
    evidence: [], status: l.status || 'observed', raw: l,
  }));
  const all = [...findings, ...leads].sort((x, y) => (SEV_ORDER[x.severity] ?? 3) - (SEV_ORDER[y.severity] ?? 3));
  const severityCounts = all.reduce((acc, f) => { acc[f.severity] = (acc[f.severity] || 0) + 1; return acc; }, {});
  const packages = (usage?.packages || []).filter(Boolean);
  const candidates = diagnosis?.candidates || [];
  const vs = VERIFICATION_STATUS[assessment.status] || VERIFICATION_STATUS.NOT_RUN;

  return {
    run: detail.run || {}, scan, usage, verification, ai, diagnosis, capsule, markdown: detail.capsule_markdown || null,
    aiValidation: detail.ai_validation || null, verifyConfig: detail.verify_config || null, files: detail.files || [],
    rawArtifacts: a, findings, leads, all, severityCounts, packages, candidates, assessment, verificationMeta: vs,
    activeJobs: detail.active_jobs || [], offline: !!detail.offline,
  };
}

// Five-stage evidence chain with honest states.
export function pipelineStages(view, aiAdapter) {
  if (!view) return [];
  const scanState = !view.scan ? 'missing' : view.scan.scan_status === 'completed' ? 'done' : 'warn';
  const diagState = !view.diagnosis ? 'missing' : view.candidates.length ? 'done' : 'empty';
  const aiState = view.ai ? (view.aiValidation?.valid === false ? 'warn' : 'proposal') : 'pending';
  const st = view.assessment.status;
  const verState = st === 'VERIFIED_CHANGE' ? 'done' : st === 'NOT_RUN' ? 'pending' : ['VERIFICATION_FAILED', 'BASELINE_FAILED'].includes(st) ? 'bad' : 'warn';
  const capState = view.capsule ? 'done' : 'missing';
  return [
    { key: 'scan', label: 'Scan', route: 'findings', state: scanState,
      detail: view.scan ? `${plural(view.scan.summary?.manifest_count ?? 0, 'manifest')} · ${plural(view.findings.length, 'finding')}` : 'No scan artifact' },
    { key: 'diagnose', label: 'Diagnose', route: 'root-cause', state: diagState,
      detail: view.diagnosis ? `${view.candidates.length} candidate cause${view.candidates.length === 1 ? '' : 's'}` : 'Not derived' },
    { key: 'ai', label: 'Gemma 4', route: 'migration', state: aiState,
      detail: view.ai ? `${(view.ai.options || []).length} proposed options` : aiAdapter?.state === 'READY' ? 'Adapter ready, not run' : 'Start local Ollama to run' },
    { key: 'verify', label: 'Verify', route: 'verification', state: verState, detail: (VERIFICATION_STATUS[st] || VERIFICATION_STATUS.NOT_RUN).label },
    { key: 'capsule', label: 'Capsule', route: 'capsule', state: capState, detail: view.capsule ? view.capsule.overall_status : 'Not built' },
  ];
}

// Evidence-based health checks (no invented score).
export function healthChecks(view) {
  if (!view) return [];
  const out = [];
  const s = view.scan;
  if (!s) out.push({ tone: 'muted', title: 'Manifests', detail: 'No scan artifact loaded.' });
  else if (s.scan_status === 'no_manifests_found') out.push({ tone: 'warn', title: 'Manifests', detail: 'No supported manifests found — the repository was not assessed (this is not a clean result).' });
  else {
    const errs = s.summary?.error_count ?? (s.errors || []).filter((e) => (e.severity || 'error') === 'error').length;
    out.push({ tone: errs ? 'warn' : 'good', title: 'Manifests parsed', detail: `${s.summary?.manifest_count ?? s.manifests_scanned?.length ?? 0} manifest(s), ${s.summary?.declaration_count ?? s.declaration_count ?? 0} declarations, ${errs} parse error(s).` });
    const incompatible = view.findings.filter((f) => f.assessment === 'incompatible_constraints').length;
    const uncertain = view.findings.filter((f) => f.assessment === 'uncertain').length;
    out.push({ tone: incompatible ? 'bad' : uncertain ? 'warn' : 'good', title: 'Declaration consistency',
      detail: incompatible || uncertain ? `${incompatible} incompatible, ${uncertain} uncertain across manifests.` : 'No conflicting declarations found.' });
  }
  if (view.usage) {
    const by = view.usage.summary?.by_status || {};
    const leads = view.leads.length;
    out.push({ tone: leads ? 'warn' : 'good', title: 'Source usage', detail: `${by.import_observed || 0} package(s) with observed imports, ${leads} review lead(s).` });
  } else out.push({ tone: 'muted', title: 'Source usage', detail: 'No usage artifact loaded.' });
  const vm = view.verificationMeta;
  out.push({ tone: vm.tone === 'good' ? 'good' : vm.tone === 'bad' ? 'bad' : vm.tone === 'muted' ? 'muted' : 'warn', title: 'Runtime verification', detail: vm.label + (view.verification?.baseline?.test_summary ? ` — baseline: ${view.verification.baseline.test_summary}` : '') });
  return out;
}

// Normalise a captured or suggested command so suggestions can be matched to recorded runs.
export function normalizeCommand(cmd) {
  const s = Array.isArray(cmd) ? cmd.join(' ') : String(cmd || '');
  const toks = s.trim().split(/\s+/).filter(Boolean);
  if (!toks.length) return '';
  const first = toks[0].replace(/\\/g, '/').split('/').pop().toLowerCase();
  if (/^(python|python3|python\.exe|\{python\}|py)$/.test(first) || first.startsWith('python3.')) toks[0] = 'python';
  if (toks[0] === 'pytest') toks.splice(0, 1, 'python', '-m', 'pytest');
  if (toks[0] === 'pip') toks.splice(0, 1, 'python', '-m', 'pip');
  return toks.join(' ').toLowerCase();
}

export function recordedCommands(verification) {
  const out = [];
  for (const phase of ['baseline', 'after']) {
    for (const c of verification?.[phase]?.commands || []) out.push({ phase, norm: normalizeCommand(c.display || c.command), cmd: c });
  }
  return out;
}

// Simple shell-like tokenizer for editing argv as a single line ("double" and 'single' quotes).
export function tokenize(line) {
  const out = []; let cur = ''; let q = null; let has = false;
  for (const ch of String(line || '')) {
    if (q) { if (ch === q) q = null; else cur += ch; continue; }
    if (ch === '"' || ch === "'") { q = ch; has = true; continue; }
    if (/\s/.test(ch)) { if (cur || has) { out.push(cur); cur = ''; has = false; } continue; }
    cur += ch;
  }
  if (q) throw new Error('Unclosed quote');
  if (cur || has) out.push(cur);
  return out;
}

export function joinArgv(argv) {
  return (argv || []).map((a) => (a === '' ? '""' : /[\s"']/.test(a) ? (a.includes('"') ? `'${a}'` : `"${a}"`) : a)).join(' ');
}

export function extractPins(text) {
  const re = /\b([A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^\]]+\])?(?:==|>=|<=|~=|!=)[A-Za-z0-9.*+!-]+(?:,(?:==|>=|<=|<|>|~=|!=)[A-Za-z0-9.*+!-]+)*)/g;
  const out = new Set();
  for (const m of String(text || '').matchAll(re)) out.add(m[1]);
  return [...out];
}

export function plural(n, word, pluralWord) {
  return `${n} ${n === 1 ? word : pluralWord || `${word}s`}`;
}

export function shortTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function duration(sec) {
  if (sec == null || Number.isNaN(Number(sec))) return '—';
  const s = Number(sec);
  return s < 1 ? `${Math.round(s * 1000)} ms` : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

export function buildOfflineDetail(files) {
  // files: [{name, data}] — parsed client-side when the engine is not running.
  const artifacts = { scan: null, usage: null, verification: null, ai: null, diagnosis: null };
  const problems = [];
  for (const f of files) {
    const kind = classifyArtifact(f.name, f.data);
    if (!kind) { problems.push(`${f.name}: artifact type not recognised`); continue; }
    if (kind === 'capsule') {
      for (const [k, ck] of [['scan', 'scan'], ['usage', 'usage'], ['verification', 'verification'], ['ai', 'ai_analysis'], ['diagnosis', 'diagnosis']]) {
        if (isUsable(f.data[ck]) && !artifacts[k]) artifacts[k] = f.data[ck];
      }
      continue;
    }
    artifacts[kind] = f.data;
  }
  if (!Object.values(artifacts).some(Boolean)) return { problems };
  const va = assessVerification(artifacts.verification);
  const states = ['scan', 'usage', 'ai', 'verification'].map((k) => ({ artifact: k === 'ai' ? 'ai_analysis' : k, state: artifacts[k] ? 'available' : 'not_provided' }));
  return {
    problems,
    detail: {
      offline: true,
      run: { id: 'offline', label: 'Local files (engine offline)', source: 'offline', root_name: artifacts.scan?.root || 'local files', can_verify: false, deletable: false },
      artifacts,
      capsule: {
        overall_status: va.verified ? 'VERIFIED_CHANGE' : 'NOT_VERIFIED', verification_status: va.status, verification_assessment: va,
        labels: { scan_findings: 'OBSERVED', usage: 'OBSERVED', ai_analysis: 'AI PROPOSAL', verification: va.label },
        artifact_states: states,
        missing_artifact_notices: states.filter((s) => s.state !== 'available').map((s) => `${s.artifact} artifact: not_provided. Nothing was substituted for it.`),
        interpretation: 'Assessed in the browser because the engine is offline. Start the engine to build the official capsule and root-cause diagnosis.',
      },
      capsule_markdown: null, files: [],
    },
  };
}
