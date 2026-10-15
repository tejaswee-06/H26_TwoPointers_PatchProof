# PERSON 1 IMPLEMENTATION AUDIT

Audited: uploaded `PatchProof_Person1_Engine_QA` ZIP against `PatchProof_3_Hour_Team_Implementation_Playbook.docx`.
Environment used for all execution below: Linux container, Python 3.12.3, packaging 26.0, pytest (installed for QA). **Windows was not available; nothing here was executed on Windows.**

## Phase A — initial state (before any change)
- ZIP contained: `patchproof/{scanner,usage,verify,capsule,common}.py`, 2 test files (10 tests), README_PERSON1.md, minimal pyproject.toml, stale `TEST_RESULTS.txt`, `.pytest_cache`, `__pycache__`. No `.git` metadata, **no LinkWatch repository, no AI adapter, no dashboard**.
- Baseline test run (before edits): `10 passed` (pytest not preinstalled in the container; installed it first).
- Existing-code findings that drove the work: regex-based requirement parsing (no extras/markers/URL/`-r` handling, markers dropped); conflict = "constraints differ as strings" (false positives for compatible ranges, no semantic comparison); absolute `root` path leaked in reports; `usage.py` swallowed syntax errors silently and fell back to a name guess without labelling; `verify.py` ran `before` in the user's own directory with the host interpreter, `--before nargs="+"` could not accept flags such as `-q`/`-m`, and set `verified=true` whenever the after command exited 0; capsule trusted `verified`.

## Requirement audit
States: COMPLETE AND TESTED · IMPLEMENTED BUT NOT TESTED · PARTIALLY IMPLEMENTED · MISSING · BLOCKED BY MISSING INPUT OR ENVIRONMENT

| # | Requirement | Before | After | Evidence / reason |
|---|---|---|---|---|
| A1 | Manifest formats: requirements*.txt, pyproject (PEP 621 + optional), setup.cfg, setup.py (safe) | PARTIALLY (fixed filenames only; setup.py missing; setup.cfg only install_requires) | COMPLETE AND TESTED | `tests/test_scanner.py` (formats, setup.py never executed test) |
| A2 | Robust parsing (comments, extras, markers, URLs, editable, continuations, -r includes, outside-root includes, malformed/unreadable) | PARTIALLY | COMPLETE AND TESTED | `packaging.requirements.Requirement`; ~20 tests |
| A3 | Name normalization | COMPLETE AND TESTED | COMPLETE AND TESTED | PEP 503 normalization; variant tests |
| A4 | Semantic cross-manifest comparison; uncertainty reporting | MISSING (string compare) | COMPLETE AND TESTED | `assess_pair`; compatible / incompatible / uncertain |
| A5 | Stable finding IDs | PARTIALLY (hash included only file+constraint) | COMPLETE AND TESTED | hash of package + (file, section, specifier, marker); line shifts do not change ID |
| A6 | Real source evidence incl. both declarations, observed vs inferred | PARTIALLY (no line for pyproject, no observed/inferred) | COMPLETE AND TESTED | pyproject/setup.cfg/setup.py line numbers located; `observed` / `inferred` fields |
| A7 | Deterministic JSON | PARTIALLY | COMPLETE AND TESTED | byte-identical repeated output test; no timestamp (policy field documents this) |
| A8 | Exclusions (venv, node_modules, .git, caches, build/dist, generated output, pyvenv.cfg dirs) | PARTIALLY | COMPLETE AND TESTED | `iter_files`; `--exclude` for user exclusions |
| A9 | Selectable root | COMPLETE | COMPLETE AND TESTED | `--root`; nonexistent root → exit 1 |
| A10 | Report fields (schema, exclusions, errors, limitations, safe root) | PARTIALLY | COMPLETE AND TESTED | no absolute paths asserted by test |
| A11 | No manifests ≠ clean | MISSING | COMPLETE AND TESTED | `scan_status: no_manifests_found` |
| B | Usage tracer (AST, metadata mapping, multi-name dists, statuses, limitations, parse errors, deterministic) | PARTIALLY (silent parse errors, no statuses, no aliases) | COMPLETE AND TESTED | 17 tests; statuses import_observed / no_static_import_found / mapping_unavailable / analysis_incomplete |
| C1 | Reliable command handling (flags) | MISSING | COMPLETE AND TESTED | JSON argument arrays + config file; tests with `-q --flag=x -m` |
| C2 | Disposable copy + isolated venv; honest isolation flag | MISSING | COMPLETE AND TESTED (Linux) | real venv tests with offline wheels; host-environment mode labelled NOT isolated and refuses `pip install` |
| C3 | Captured argv, cwd, times, exit code, timeout, stdout/stderr, env, dependency state before/after | PARTIALLY | COMPLETE AND TESTED | |
| C4 | Honest statuses (NOT_RUN … VERIFIED_CHANGE) | MISSING (`verified = after exit 0`) | COMPLETE AND TESTED | pure `classify()` tests + end-to-end |
| C5 | Timeout / missing executable / empty config / setup failure never a pass | PARTIALLY | COMPLETE AND TESTED | |
| D1 | Jinja2/MarkupSafe reproduction harness | MISSING | COMPLETE AND TESTED (synthetic fixture) | `examples/compat_fixture`; real run recorded in `sample_output/` |
| D2 | Reproduction against the actual LinkWatch repo and its 10 tests | — | **BLOCKED BY MISSING INPUT** | LinkWatch was not in the uploaded files |
| D3 | Pydantic `==1.10.13` vs `>=2` inconsistency | — | Detected generically; tested with a synthetic tree | Not asserted for LinkWatch (not available). No names hard-coded in scanner logic |
| E | Test suite (scanner / usage / verify / capsule) | 10 tests | 124 tests | see Completion Report |
| F | Artifact contracts + capsule semantics (OBSERVED / AI PROPOSAL / VERIFIED / BLOCKED, missing notices, rollback, no "vulnerability") | PARTIALLY | COMPLETE AND TESTED | capsule re-derives status from evidence |
| G | One-command orchestration, scan-only independent, nonzero on failed stages | MISSING | COMPLETE AND TESTED | `python -m patchproof.run` |
| H | Documentation | PARTIALLY | COMPLETE | this file + 3 more docs |
| I | Clean delivery | — | See completion report | |

## Outside Person 1 ownership (not modified)
- Person 2 Gemma 4 adapter and Person 3 dashboard: **not present in the ZIP**. The capsule accepts an AI artifact only if one is supplied and never creates AI output. Contract changes that Persons 2/3 should know about are in `PERSON1_JSON_CONTRACTS.md` §Compatibility.

## Remaining blockers
1. Actual LinkWatch repository (and its report tests) — required to reproduce the real 10-test case and to scan its real manifests.
2. Windows CMD execution of the venv path was not exercised (code uses `Scripts\python.exe` on `os.name == "nt"`); run the smoke checklist in `PERSON1_RUNBOOK.md`.
3. A real `ai-analysis.json` from Person 2 to exercise capsule rendering against the true AI schema (rendering is covered with a hand-written schema-shaped test fixture only).
