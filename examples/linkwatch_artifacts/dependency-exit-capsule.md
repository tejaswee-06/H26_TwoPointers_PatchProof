# PatchProof Dependency Exit Capsule

**Overall status:** `VERIFIED_CHANGE`  |  **Verification status:** `VERIFIED_CHANGE`

A declared dependency change was applied with evidence and the recorded after-change commands passed in the recorded environment.

## Missing artifact notices
- **BLOCKED** — ai_analysis artifact: not_provided. Nothing was substituted for it.

## Repository and scan summary (OBSERVED)
- Scan root: `LinkWatch`
- Scan status: `completed`
- Manifests scanned: 3
- Declarations: 27
- Findings: 1
- Parse/read errors: 0

### F-3C1708E248: Incompatible declarations for pydantic  `OBSERVED`
- Type: `manifest_inconsistency`; severity: `review`; assessment: `incompatible_constraints`
- Summary: pydantic is declared with constraints that cannot be satisfied together across manifests. This is a manifest inconsistency to review; it is not proof that the application fails, and this scanner does not decide which declaration is correct.
- Evidence: `pyproject.toml` line 17: `pydantic>=2`
- Evidence: `requirements.txt` line 5: `pydantic==1.10.13`
- Inferred (not observed): pyproject.toml:17 vs requirements.txt:5: Exact pin ==1.10.13 is not allowed by the other declaration's specifier.

## Dependency usage (OBSERVED)
- Declared packages traced: 14
- Status counts: {'import_observed': 9, 'mapping_unavailable': 5}
- Analysis complete: True
- Review lead `U-39AC5AE0C1` — idna: mapping_unavailable (a lead, not proof the package is unused)
- Review lead `U-F1082F3688` — nose: mapping_unavailable (a lead, not proof the package is unused)
- Review lead `U-9C6F3AC19D` — python-dateutil: mapping_unavailable (a lead, not proof the package is unused)
- Review lead `U-90F0EE6B9B` — setuptools: mapping_unavailable (a lead, not proof the package is unused)
- Review lead `U-437C6776AB` — six: mapping_unavailable (a lead, not proof the package is unused)

## AI migration analysis (AI PROPOSAL)
AI analysis artifact unavailable; no AI result has been fabricated.

## Verification
- Status: `VERIFIED_CHANGE` `VERIFIED`
- Reason: Baseline captured; declared dependency change applied with evidence; every baseline command was repeated after the change and passed.
- Environment: Python 3.12.1 on Windows; isolated: True
- Declared change: pip_install=['MarkupSafe==2.0.1'] file_edits=0; applied with evidence: True
  - markupsafe: 3.0.4 -> 2.0.1
- Baseline: failed — 1 failed, 9 passed, 1 warning in 9.26s
  - `<WORKDIR>\baseline\venv\Scripts\python.exe -m pip check` → exit code `0`, status `passed`
  - `<WORKDIR>\baseline\venv\Scripts\python.exe -m pytest -q` → exit code `1`, status `failed`
- After: passed — 10 passed, 1 warning in 8.73s
  - `<WORKDIR>\after\venv\Scripts\python.exe -m pip check` → exit code `0`, status `passed`
  - `<WORKDIR>\after\venv\Scripts\python.exe -m pytest -q` → exit code `0`, status `passed`

## Rollback
- No rollback information was supplied by a real analysis artifact.

## Limitations
- This capsule records available evidence only; it does not assess security advisories.
- Missing or unreadable artifacts remain missing and are not replaced with synthetic results.
- Scanner findings are manifest observations, not proof of runtime failure.
- A package with no detected import is a review lead, not proof it is unused.
- A migration recommendation is a proposal until the verification runner records a VERIFIED_CHANGE.
- Human review is required before applying dependency changes.
