# PERSON 1 COMPLETION REPORT

## Test results (actual, Linux, Python 3.12.3)
- Before changes: `10 passed` (original suite).
- After changes: **`124 passed, 0 failed, 0 skipped, 0 blocked`** in ~61 s (`TEST_RESULTS.txt` holds the raw output). Per file: scanner 43, usage 17, verify 44, capsule/orchestration 20.
- Static check: `pyflakes patchproof tests` — clean. `compileall` — clean.
- Smoke runs performed: scan twice → byte-identical JSON; `patchproof.run` scan-only on a synthetic tree; `patchproof.run` with verification on `examples/compat_fixture` (real network run, status `VERIFIED_CHANGE` for the **synthetic fixture**); all sample JSON parses.
- **Not run:** anything on Windows; anything against LinkWatch; anything against a real Gemma 4 `ai-analysis.json`; a `git diff` review (the ZIP had no Git metadata).
- Removed v1 tests: `tests/test_verify_capsule.py` was replaced because it exercised the old unsafe `verify(root, before, after)` API (exit code 0 ⇒ `verified`). Its intents (real exit code captured, failed/missing after ⇒ not verified, capsule does not fabricate verification) are preserved in `tests/test_verify.py` and `tests/test_capsule.py`. All 6 original scanner tests are kept unchanged and pass.

## Implemented
- Scanner: `packaging`-based parsing; extras, markers, direct URLs (credentials redacted), editable, continuations, `--hash`, `-r` includes (cycle-safe; outside-root includes refused), pyproject (PEP 621, optional deps, PEP 735 groups, build-system), setup.cfg, setup.py via AST only; semantic comparison with compatible / incompatible / uncertain; stable line-independent IDs; real line numbers incl. pyproject; observed vs inferred; deterministic output without absolute paths; exclusions (incl. `pyvenv.cfg` dirs and the output dir); `no_manifests_found` ≠ clean.
- Usage tracer: AST imports (aliases, `from`, literal `import_module`), metadata mapping, four statuses, parse errors surfaced, review-lead IDs (`U-…`), no code execution.
- Verification: config/JSON-array commands (flags safe, no shell), disposable copy + fresh venv per phase, `{python}` substitution, environment + dependency-state capture and diff, timeouts, output limits, local-path scrubbing, refusal to `pip install` without isolation, six explicit statuses with documented precedence, exit codes.
- Capsule: re-derives status from evidence (bare `verified:true` rejected), OBSERVED / AI PROPOSAL / VERIFIED / BLOCKED labels, missing-artifact notices, unknown AI finding-ID warnings, rollback only from real AI artifacts, no "vulnerability" wording, v1 keys preserved.
- `patchproof.run` one-command pipeline; docs (audit, runbook, contracts, this report); synthetic Jinja2/MarkupSafe fixture with real sample output.

## Files
New: `patchproof/run.py`, `tests/{conftest,test_usage,test_verify,test_capsule}.py`, `examples/compat_fixture/**`, `requirements-dev.txt`, `PERSON1_*.md`.
Rewritten: `patchproof/{common,scanner,usage,verify,capsule}.py`, `pyproject.toml`, `README_PERSON1.md`, `TEST_RESULTS.txt`, `tests/test_scanner.py` (original 6 tests kept; 37 added).
Removed: `tests/test_verify_capsule.py` (see above), stale caches.

## Jinja2 / MarkupSafe
- **Real LinkWatch case: NOT reproduced — BLOCKED** (repository and its tests not supplied).
- Mechanism reproduced on a synthetic fixture on Python 3.12.3 (playbook used 3.13.9): Jinja2 2.11.3 + MarkupSafe 3.0.4 → `ImportError: cannot import name 'soft_unicode' from 'markupsafe'` while `pip check` printed "No broken requirements found"; the same fixture with MarkupSafe 2.0.1 imports and renders. Captured in `examples/compat_fixture/sample_output/verification.json`. The 2.0.1 pin is a diagnostic workaround only; no long-term recommendation is made.
- The playbook's "all 10 tests pass" claim could not be checked (those tests are not in the upload).

## Known limitations
- `.egg-info`/`build`/`dist` etc. are excluded by name everywhere, so a legitimately named `build/requirements.txt` is skipped (use the exclusion list in the report to see what was skipped).
- Poetry/PDM/Pipfile/conda manifests and lockfiles are not parsed; constraint files (`-c`) are noted, not compared.
- Specifier comparison uses a bounded candidate-version set; exotic specifiers (`!=`, `===`, wildcards) yield `uncertain` rather than a guess.
- Usage mapping needs the dependencies installed in the interpreter running the tracer; top-level import roots only.
- Isolation is a venv + copied working directory, not a sandbox: no network or filesystem confinement; setup commands have network access.
- `verification.json` contains start times and is not byte-deterministic (other artifacts are).
- Windows venv paths are coded but untested.

## Compatibility changes needed by others
See `PERSON1_JSON_CONTRACTS.md` → "Compatibility guidance" (stable `F-…` IDs instead of ordinals, read `status` not `verified`, `root` is a directory name, `before.command` is a single argv).
