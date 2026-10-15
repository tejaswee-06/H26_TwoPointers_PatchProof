# PERSON 1 JSON CONTRACTS

All examples are **EXAMPLE shapes**, abbreviated, not execution output. Real output: `examples/compat_fixture/sample_output/` (synthetic fixture).
Paths in artifacts are root-relative POSIX paths; absolute local paths are not written. Reports contain no wall-clock timestamp except command start times inside `verification.json` (documented as non-deterministic).
`schema_version` is `"2.0"` for all four artifacts.

## 1. `patchproof-report.json` (scan)
```
{ "schema_version": "2.0", "report_type": "scan", "root": "<directory name>",
  "scan_status": "no_manifests_found | completed | completed_with_errors",
  "summary": {"manifest_count","declaration_count","finding_count","error_count","note_count"},
  "manifests_scanned": ["requirements.txt"], "manifests": [{"file","format","declaration_count","included_by"}],
  "declarations": [{"name","normalized_name","extras","specifier","original_specifier","constraint","marker","url","kind","file","line","section","excerpt"}],
  "directives": [...], "errors": [{"file","line","code","severity":"error|warning|info","error","excerpt"}],
  "exclusions": {...}, "limitations": [...],
  "findings": [{
      "id": "F-3C1708E248", "type": "manifest_inconsistency", "severity": "review | info",
      "assessment": "incompatible_constraints | uncertain", "package": "pydantic",
      "title": "...", "summary": "...", "observed": "...", "inferred": "...",
      "pairs": [{"a","b","assessment","reason"}],
      "evidence": [{"file","line","excerpt","normalized_package","specifier","original_specifier","section","marker","role"}],
      "status": "observed" }] }
```
- Finding IDs: `F-` + 10 hex chars of SHA-256 over (type, package, sorted `file|section|specifier|marker|url`). Independent of line numbers and ordering; changes only if a declaration involved changes.
- `evidence` holds **every** declaration involved (both files for a cross-manifest conflict). `observed` = what the files say; `inferred` = the comparison result. The scanner never states which declaration is correct.
- `line` is `null` only if the exact line could not be located. `severity: review` is not "vulnerability"; no advisory data is consulted.
- `no_manifests_found` means the repository was **not assessed**.
- Backward compatibility with v1: `findings[].id/type/severity/title/summary/package/evidence[file,line,excerpt]/status`, `manifests_scanned`, `declaration_count`, `declarations[].name/normalized_name/constraint/file/line/excerpt`, `errors[].file/error` are preserved. Changed: `root` is now the directory name only; `errors[]` gained `code`/`severity`.

## 2. `patchproof-usage-report.json`
```
{ "schema_version": "2.0", "report_type": "usage", "root", "scan_status", "python_files_scanned",
  "summary": {"declared_packages","by_status","parse_error_count","analysis_complete"},
  "packages": [{ "package", "declarations": [...], "candidate_import_roots": ["yaml"],
      "mapping_source": "installed_metadata | name_heuristic",
      "imports_found": [{"file","line","module","import_name","alias","kind":"import|from_import|dynamic_literal","statement"}],
      "usage_status": "import_observed | no_static_import_found | mapping_unavailable | analysis_incomplete",
      "interpretation": "...", "review_lead_id": "U-... (only for lead statuses)" }],
  "review_leads": [{"id": "U-...","type":"usage_review","severity":"info","package","usage_status","status":"observed","title","summary"}],
  "parse_errors": [...], "unresolved_dynamic_imports": {"file": count}, "mapping": {...}, "limitations": [...] }
```
`no_static_import_found` / `mapping_unavailable` / `analysis_incomplete` are **review leads**, never evidence a package is unused.
Mapping depends on metadata installed in the Python environment that runs the tool.

## 3. `verification.json`
Input: a verification **config** (JSON file, `--config`):
```
{ "target": "project", "isolation": "venv | none", "timeout_seconds": 300, "working_directory": ".",
  "baseline": {"setup": [["{python}","-m","pip","install","-r","requirements.txt"]], "commands": [["{python}","-m","pytest","-q"]]},
  "after":    {"setup": [...], "commands": [...]},
  "change":   {"pip_install": ["markupsafe==2.0.1"], "pip_args": [], "file_edits": [{"file","old","new"}]} }
```
`{python}` / `python` as first argument = the phase's interpreter (venv or host). No shell is ever used. `target` is relative to the config file.

Output:
```
{ "schema_version": "2.0", "report_type": "verification",
  "status": "NOT_RUN | BLOCKED | BASELINE_FAILED | TESTS_PASS_CHANGE_UNVERIFIED | VERIFIED_CHANGE | VERIFICATION_FAILED",
  "status_reasons": [...], "verified": false, "blockers": [...],
  "isolation": {"requested","baseline_isolated","after_isolated","working_copy_used","note"},
  "environment": {"python_version","python_implementation","os","os_release","machine","interpreter_kind","environment_isolated","isolation_note"},
  "environments": {"baseline": {...}, "after": {...}},
  "change": {"declared","pip_install","file_edits","applied_with_evidence","environment_diff":[{"package","before","after"}],"manifest_diff":[{"file","diff"}]},
  "dependency_state": {"before": {"captured","packages":{name:version}}, "after": {...}, "difference": [...]},
  "baseline": {"passed","exit_code","command","test_summary","setup":[...],"commands":[<cmd>...]},
  "after": {...same, plus "file_edits"}, "before": <alias of baseline>,
  "test_summary": "...", "trust_boundary": "...", "limitations": [...] }
<cmd> = {"command":[argv],"display","cwd","started_at","timeout_seconds","shell":false,"status":"passed|failed|timeout|not_started",
         "exit_code","passed","timed_out","stdout","stderr","output_truncated","duration_seconds","test_summary","error?"}
```
### Status semantics (precedence top→bottom)
1. no baseline commands configured → `NOT_RUN`
2. config invalid, copy/venv creation failed, setup command failed, change could not be applied, pip install requested without isolation → `BLOCKED`
3. no after-run: baseline failed → `BASELINE_FAILED`; baseline passed → `TESTS_PASS_CHANGE_UNVERIFIED`
4. after-run failed (baseline passed or failed) → `VERIFICATION_FAILED`
5. after-run passed but any of: no declared change · declared change not evidenced (no manifest edit or dependency-state diff) · after-run did not repeat every baseline command · environment not recorded · dependency state could not be captured → `TESTS_PASS_CHANGE_UNVERIFIED`
6. otherwise → `VERIFIED_CHANGE` (`verified: true`). A failing baseline is **not** required.

"A command ran", "tests passed", "a change was applied" and "a change was verified" are different states. `VERIFIED_CHANGE` means: the declared change was applied in a disposable environment with evidence, and all recorded baseline commands passed afterwards. It does not mean the change is the best long-term choice.
CLI exit codes: 0 VERIFIED_CHANGE · 1 VERIFICATION_FAILED/BASELINE_FAILED · 2 BLOCKED/NOT_RUN · 3 TESTS_PASS_CHANGE_UNVERIFIED.
**Breaking change from v1:** the old `verify(root, before, after)` Python API and `--before/--after nargs` CLI are replaced (they could not take flags and treated exit 0 as verified).

## 4. `dependency-exit-capsule.json/.md`
Keys: `schema_version, report_type, product, purpose, labels, repository, scan, usage, ai_analysis, verification, verification_assessment, verification_status, overall_status, interpretation, artifact_states, missing_artifact_notices, rollback, rollback_note, limitations`.
- `overall_status`: `VERIFIED_CHANGE` or `NOT_VERIFIED` (v1-compatible). `verification_status` gives the detailed status.
- The capsule **re-derives** verification status from evidence in the artifact. A bare `verified: true`, a legacy artifact without `status`, or a `VERIFIED_CHANGE` missing baseline/after/change/environment evidence is downgraded.
- Labels: scan/usage = `OBSERVED`; AI = `AI PROPOSAL`; `VERIFIED` only for a genuine `VERIFIED_CHANGE`; absent/blocked inputs = `BLOCKED`.
- Missing/unreadable artifacts → entries in `missing_artifact_notices`; nothing is substituted. Rollback text appears only if a supplied AI artifact has `options[].rollback`.
- AI `finding_ids` not found in scan/usage IDs are flagged in the notices.

## Compatibility guidance
- **Person 2 (AI adapter):** reference findings by the new stable `id` (`F-…`, usage leads `U-…`); do not rely on `F-001` ordinals. Input evidence is in `findings[].evidence[]` (+ `observed`/`inferred`). Keep your schema (`model, runtime, finding_ids, analysis, options[{description, benefits, risks, files_to_change, verification_commands, rollback}], recommended_option, uncertainties`); the capsule renders those keys and does not alter them. `verification_commands` suggested by the model are not run unless a human puts them into a verification config.
- **Person 3 (dashboard):** read `verification.status`, not `verified`; show `BLOCKED` for `NOT_RUN/BLOCKED`, `OBSERVED` for scan/usage, `AI PROPOSAL` for AI, `VERIFIED` only for `VERIFIED_CHANGE`. `scan.root` is now a directory name. `scan.errors[]` contains `severity: info|warning|error` entries; count only `error` for failures (`scan.summary.error_count`). `verification.before` is kept as an alias of `baseline`, but `before.command` is now a single argv (the first failing or last command); use `baseline.commands[]` for the full list.
