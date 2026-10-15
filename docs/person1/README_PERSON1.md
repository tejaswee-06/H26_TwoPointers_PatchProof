# PatchProof — Person 1: Engine & QA (v0.2.0)

Evidence-backed dependency-manifest scanning, static usage tracing, honest verification and the Dependency Exit Capsule.
**Start with `PERSON1_RUNBOOK.md`.** Contracts: `PERSON1_JSON_CONTRACTS.md`. What was done and what remains: `PERSON1_COMPLETION_REPORT.md`, `PERSON1_IMPLEMENTATION_AUDIT.md`.

Important: the organizer's LinkWatch repository was **not** part of the uploaded files. Nothing here has been run against LinkWatch.
The Jinja2/MarkupSafe mechanism was reproduced on a small synthetic fixture (`examples/compat_fixture`), not on LinkWatch.

## Modules
- `patchproof/scanner.py` — requirements*.txt, pyproject.toml, setup.cfg, setup.py (static only); semantic constraint comparison; stable IDs; evidence.
- `patchproof/usage.py` — `ast`-based import tracing mapped through installed distribution metadata.
- `patchproof/verify.py` — config-driven baseline/after runner in disposable copies with isolated venvs and explicit statuses.
- `patchproof/capsule.py` — combines artifacts; re-derives verification status from evidence.
- `patchproof/run.py` — one-command orchestration (scan-only by default).

## Quick start
```
python -m pip install -r requirements-dev.txt
python -m patchproof.run --root . --out-dir patchproof-output
python -m pytest -q
```

## Honesty rules
Findings are observations, not proof of runtime failure or security issues. No import found = review lead, not "unused".
`verified` is true only for `VERIFIED_CHANGE`: baseline captured, a declared change applied with evidence, and all baseline commands repeated and passing afterwards.
Repository commands run only when you supply a verification config, and may execute arbitrary project code.
