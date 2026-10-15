# PatchProof Dependency Exit Capsule

**Overall status:** `VERIFIED_CHANGE`  |  **Verification status:** `VERIFIED_CHANGE`

A declared dependency change was applied with evidence and the recorded after-change commands passed in the recorded environment.

## Missing artifact notices
- **BLOCKED** — ai_analysis artifact: not_provided. Nothing was substituted for it.

## Repository and scan summary (OBSERVED)
- Scan root: `project`
- Scan status: `completed`
- Manifests scanned: 1
- Declarations: 2
- Findings: 0
- Parse/read errors: 0

## Dependency usage (OBSERVED)
- Declared packages traced: 2
- Status counts: {'import_observed': 1, 'no_static_import_found': 1}
- Analysis complete: True
- Review lead `U-9DDB9D1BF9` — markupsafe: no_static_import_found (a lead, not proof the package is unused)

## AI migration analysis (AI PROPOSAL)
AI analysis artifact unavailable; no AI result has been fabricated.

## Verification
- Status: `VERIFIED_CHANGE` `VERIFIED`
- Reason: Baseline captured; declared dependency change applied with evidence; every baseline command was repeated after the change and passed.
- Environment: Python 3.12.3 on Linux; isolated: True
- Declared change: pip_install=['MarkupSafe==2.0.1'] file_edits=0; applied with evidence: True
  - markupsafe: 3.0.4 -> 2.0.1
- Baseline: failed
  - `<WORKDIR>/baseline/venv/bin/python -m pip check` → exit code `0`, status `passed`
  - `<WORKDIR>/baseline/venv/bin/python check_import.py` → exit code `1`, status `failed`
- After: passed
  - `<WORKDIR>/after/venv/bin/python -m pip check` → exit code `0`, status `passed`
  - `<WORKDIR>/after/venv/bin/python check_import.py` → exit code `0`, status `passed`

## Rollback
- No rollback information was supplied by a real analysis artifact.

## Limitations
- This capsule records available evidence only; it does not assess security advisories.
- Missing or unreadable artifacts remain missing and are not replaced with synthetic results.
- Scanner findings are manifest observations, not proof of runtime failure.
- A package with no detected import is a review lead, not proof it is unused.
- A migration recommendation is a proposal until the verification runner records a VERIFIED_CHANGE.
- Human review is required before applying dependency changes.
