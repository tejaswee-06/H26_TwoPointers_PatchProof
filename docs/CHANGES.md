# Changes in the integrated build (v0.3.0)

Starting points: Person 1 `PatchProof_Person1_COMPLETE_ENGINE_QA` (engine v0.2.0, 124 tests) and Person 3
`frontend-react` (single-file React UI that loaded JSON in the browser; never built or run).

## New files

| File | Purpose |
|---|---|
| `patchproof/server.py` | Local API + static server (stdlib only): runs/workspace, scan jobs, consent-gated cancellable verification subprocess, AI adapter jobs, import, downloads, folder browser, loopback/Origin/header guards |
| `patchproof/diagnose.py` | Root-cause diagnostics: parses failing command output (ImportError / ModuleNotFoundError / pytest frames and failures, pip "Collecting … (from …)" lines) and correlates it with declarations, installed versions, import sites and the verified change. Candidates are hypotheses with separate observed / inferred / uncertainty fields |
| `patchproof/ai_bridge.py` | Gemma 4 integration point: evidence bundle, adapter discovery (`patchproof.ai` or `PATCHPROOF_AI_ADAPTER`), schema validation that forces `PROPOSED` / `NOT_RUN` |
| `tests/test_diagnose.py`, `tests/test_server.py`, `tests/test_ai_bridge.py`, `tests/fake_ai_adapter.py` | 24 new tests (the adapter file is a clearly labelled test double, used only by tests) |
| `frontend/src/**` | Dashboard rebuilt from P3's single `main.jsx` into `App.jsx`, `pages/*` (Landing, Workspace, Overview, Runs, Findings, Usage, RootCause, Migration, Verification, Capsule), `components/*` (ui, Pipeline, JobProgress, ParticleWave), `lib/*` (api, model, router, markdown, workspace) |
| `frontend/tests/model.test.js`, `frontend/vite.config.js` | Data-layer unit tests (node:test); dev proxy to the engine |
| `docs/AI_INTEGRATION.md`, `docs/CHANGES.md`, `docs/TEST_RESULTS.md`, `docs/DEMO_CHECKLIST.md`, `README.md`, `.gitignore` | Documentation |
| `examples/linkwatch_artifacts/*` | Person 1's real LinkWatch output (was `out/linkwatch/`), with README and a sanitized `verify-config.linkwatch.json` |

## Modified Person 1 files (additive; no status logic changed)

| File | Change | Why |
|---|---|---|
| `patchproof/verify.py` | Optional `progress` callback on `verify()` (scrubbed events, callback errors ignored); `--progress` CLI flag emitting `PATCHPROOF_PROGRESS {json}` on stderr; SIGTERM → clean unwind so temp dirs are removed on cancel; extra scrubbing of temp dir, home dir and `pytest-of-<user>` | Live timeline + cancellation in the dashboard; the LinkWatch artifact leaked a Windows user name through pytest's `tmp_path` |
| `patchproof/capsule.py` | Optional `diagnosis` argument → `labels.diagnosis = HYPOTHESIS`, `diagnosis` key and a "Root-cause candidates (HYPOTHESIS)" Markdown section; `--diagnosis` CLI flag | Capsule must carry the evidence-backed diagnosis; without the argument the capsule is unchanged |
| `patchproof/run.py` | Passes `diagnose(...)` into the capsule | CLI and dashboard produce the same capsule |
| `patchproof/__init__.py`, `pyproject.toml` | Version 0.3.0 | |
| `tests/test_verify.py` | +3 tests (progress events, CLI progress lines, path scrubbing) | |

All 124 original Person 1 tests are unchanged and pass.

## Modified Person 3 files

| File | Change |
|---|---|
| `frontend/package.json` | Exact pinned versions instead of `latest` (React 18.3.1, Vite 5.4.11, lucide-react 0.460.0); build tools moved to devDependencies; unused TypeScript removed; self-hosted fonts (no Google Fonts request); `npm test` |
| `frontend/index.html` | Theme colour, favicon, noscript |
| `frontend/src/styles.css` | Rewritten as a readable token-based system that keeps P3's language (Manrope + DM Mono, electric blue, dark surfaces, particle wave) and adds glass, grid, glow, evidence-label colours, motion and responsive rules |

Retained P3 features: landing page structure and copy, particle wave, dark/light theme, accessibility panel (reduced motion,
larger text, higher contrast, speech controls), skip link, read-aloud, voice search, JSON import, finding export,
capsule export. Fixed: the mobile menu button did nothing (nav was hidden), the landing "tabs" were static, the
fixture preview used hand-written sample data (replaced by real bundled artifacts), the UI trusted `verified: true`,
the Markdown export was assembled in the browser (now the engine's capsule).

## Data handling

* `examples/linkwatch_artifacts/verification.json` and `dependency-exit-capsule.json`: the OS user name inside pytest temp paths replaced with `<user>`; nothing else changed.
* `verify-config.json` from Person 1's root (contained a personal absolute path) moved to `examples/linkwatch_artifacts/verify-config.linkwatch.json` with a placeholder target.
* Not shipped: `.venv`, `node_modules`, `dist`, caches, `out/fixture` and `out/scan_only` (regenerable; `examples/compat_fixture/sample_output` is kept).


## Person 2 integration (v0.4.0)

Source: `PatchProof_Person2_Completed.zip` (a LinkWatch checkout with P2's `patchproof/ai/` added).

| Area | Change |
|---|---|
| `patchproof/ai/{ollama_adapter,schemas,migration_agent}.py` | P2's local Ollama/Gemma 4 adapter, strict schema validation and CLI, taken as delivered. `ollama_adapter` gained an optional `timeout_seconds`; `migration_agent` gained an engine mode (scan/usage/verification/diagnosis artifacts -> `ai-analysis.json` + `ai-runtime-proof.json`) next to P2's original legacy mode |
| `patchproof/ai/__init__.py` (new) | The glue: `status()` (Ollama reachable + model pulled) and `analyze(bundle)` mapping P1's evidence bundle (F-/U-/D- items, failing output, verification) onto P2's inputs |
| `patchproof/ai_bridge.py` | Accepts P2's inert `decision_status: PROPOSED` / `verification_status: NOT_RUN`; validates optional `diagnostic_hypotheses`; bundle schema/instructions now ask for them |
| `patchproof/capsule.py` | Markdown renders diagnostic hypotheses (labelled AI PROPOSAL, tests NOT_RUN) |
| `frontend/src/pages/Migration.jsx`, `model.js`, `styles.css` | Hypotheses panel; "pending Person 2 adapter" copy replaced by real adapter state |
| `pyproject.toml` | Packages `patchproof.ai`; pytest `pythonpath` for shared test helpers |
| `examples/linkwatch_project/` | P2's LinkWatch source/tests (the sample target repo); `.venv`, caches and its duplicated AI tests removed |
| `examples/linkwatch_ai_output/` | P2's recorded real Gemma output and runtime proof |
| `docs/person2/` | P2's completion notes and runtime-proof doc |
| Tests | P2's 28 AI tests + `tests/test_ai_integration.py` (bundle mapping, validation, self-verify rejection, unknown-ID rejection, status, full server job with mocked Ollama); `test_server`/`test_ai_bridge` updated for adapter states |

**Deliberately not taken from P2's zip:** its `patchproof/scanner.py`, `usage.py`, `verify.py` (older minimal versions; P1's engine is kept),
and its root-level `patchproof-report.json`, `dependency-exit-capsule.*`, `patchproof-usage-report.json` (superseded by P1's schema-2.0 artifacts).
P2's `patchproof-test-evidence.txt` contains a Windows user path, so it is not shipped.
