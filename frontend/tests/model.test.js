// Unit tests for the dashboard's pure data layer: `npm test` (node --test, no extra dependencies).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  assessVerification, buildOfflineDetail, buildView, classifyArtifact, extractPins, healthChecks,
  joinArgv, normalizeCommand, pipelineStages, tokenize,
} from '../src/lib/model.js';

const here = dirname(fileURLToPath(import.meta.url));
const lw = (name) => JSON.parse(readFileSync(join(here, '..', '..', 'examples', 'linkwatch_artifacts', name), 'utf8'));

test('assessVerification mirrors the engine: genuine VERIFIED_CHANGE accepted', () => {
  const a = assessVerification(lw('verification.json'));
  assert.equal(a.status, 'VERIFIED_CHANGE');
  assert.equal(a.verified, true);
  assert.equal(a.label, 'VERIFIED');
});

test('bare legacy verified:true is never trusted', () => {
  const a = assessVerification({ verified: true, after: { passed: true } });
  assert.equal(a.verified, false);
  assert.equal(a.legacy, true);
  assert.equal(a.status, 'TESTS_PASS_CHANGE_UNVERIFIED');
});

test('VERIFIED_CHANGE claim without evidence is downgraded', () => {
  const a = assessVerification({ status: 'VERIFIED_CHANGE', verified: true });
  assert.equal(a.verified, false);
  assert.equal(a.status, 'TESTS_PASS_CHANGE_UNVERIFIED');
  assert.match(a.reasons[0], /inconsistent/);
});

test('missing / blocked verification', () => {
  assert.equal(assessVerification(null).status, 'NOT_RUN');
  assert.equal(assessVerification({ status: 'missing' }).status, 'BLOCKED');
  assert.equal(assessVerification({ schema_version: '2.0', status: 'BLOCKED' }).label, 'BLOCKED');
});

test('classifyArtifact recognises every engine artifact', () => {
  assert.equal(classifyArtifact('patchproof-report.json', lw('patchproof-report.json')), 'scan');
  assert.equal(classifyArtifact('x.json', lw('patchproof-usage-report.json')), 'usage');
  assert.equal(classifyArtifact('x.json', lw('verification.json')), 'verification');
  assert.equal(classifyArtifact('x.json', lw('dependency-exit-capsule.json')), 'capsule');
  assert.equal(classifyArtifact('ai-analysis.json', { model: 'gemma', options: [] }), 'ai');
  assert.equal(classifyArtifact('random.json', { hello: 1 }), null);
  assert.equal(classifyArtifact('x.json', [1, 2]), null);
});

test('buildView keeps IDs, evidence and severity; AI absent stays pending', () => {
  const v = buildView({ run: { id: 'r' }, artifacts: { scan: lw('patchproof-report.json'), usage: lw('patchproof-usage-report.json'), verification: lw('verification.json') } });
  assert.equal(v.findings[0].id, 'F-3C1708E248');
  assert.equal(v.findings[0].evidence.length, 2);
  assert.equal(v.leads.length, 5);
  assert.equal(v.severityCounts.review, 1);
  assert.equal(v.severityCounts.info, 5);
  const stages = pipelineStages(v, { state: 'NOT_CONNECTED' });
  assert.equal(stages.find((s) => s.key === 'ai').state, 'pending');
  assert.equal(stages.find((s) => s.key === 'verify').state, 'done');
  const checks = healthChecks(v);
  assert.equal(checks.find((c) => c.title === 'Declaration consistency').tone, 'bad');
});

test('offline import builds an honest read-only detail', () => {
  const { detail, problems } = buildOfflineDetail([
    { name: 'patchproof-report.json', data: lw('patchproof-report.json') },
    { name: 'mystery.json', data: { a: 1 } },
  ]);
  assert.equal(problems.length, 1);
  assert.equal(detail.capsule.overall_status, 'NOT_VERIFIED');
  assert.equal(detail.capsule.verification_status, 'NOT_RUN');
  assert.ok(detail.capsule.missing_artifact_notices.some((n) => n.startsWith('ai_analysis')));
});

test('command tokenizer round-trips and matches recorded commands', () => {
  assert.deepEqual(tokenize('{python} -c "import a; print(1)"'), ['{python}', '-c', 'import a; print(1)']);
  assert.throws(() => tokenize('"unclosed'));
  const argv = ['{python}', '-c', "import m; print(hasattr(m, 'x'))"];
  assert.deepEqual(tokenize(joinArgv(argv)), argv);
  assert.equal(normalizeCommand('<WORKDIR>\\baseline\\venv\\Scripts\\python.exe -m pytest -q'), normalizeCommand('pytest -q'));
  assert.equal(normalizeCommand(['{python}', '-m', 'pip', 'check']), 'python -m pip check');
});

test('extractPins finds requirement pins in proposal text only', () => {
  assert.deepEqual(extractPins('Pin MarkupSafe==2.0.1 and run pip install "Jinja2>=3.0,<4" — not 3.0.4'), ['MarkupSafe==2.0.1', 'Jinja2>=3.0,<4']);
});
