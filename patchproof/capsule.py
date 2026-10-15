"""Dependency Exit Capsule builder (PatchProof Person 1 integration).

Combines available artifacts without inventing anything. Verification status
is RE-DERIVED from the evidence inside the verification artifact; a bare
``verified: true`` is never trusted.

Labels: OBSERVED (from scan/usage), AI PROPOSAL (from the AI artifact),
VERIFIED (only for VERIFIED_CHANGE), BLOCKED.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .common import SCHEMA_VERSION, load_json_artifact, write_json

LABELS = ("OBSERVED", "AI PROPOSAL", "VERIFIED", "BLOCKED")


def _missing(artifact: Any) -> bool:
    return isinstance(artifact, dict) and artifact.get("status") in ("missing", "unreadable") \
        and "schema_version" not in artifact


def _artifact_state(name: str, artifact: Any, requested: bool = True) -> dict[str, Any]:
    if artifact is None:
        return {"artifact": name, "state": "not_provided"}
    if _missing(artifact):
        return {"artifact": name, "state": artifact["status"], "detail": artifact.get("error") or artifact.get("requested_path")}
    if not isinstance(artifact, dict):
        return {"artifact": name, "state": "invalid", "detail": "Artifact is not a JSON object."}
    return {"artifact": name, "state": "available"}


def assess_verification(v: Any) -> dict[str, Any]:
    """Derive the verification status from evidence. Unknown/legacy -> not verified."""
    if v is None:
        return {"status": "NOT_RUN", "verified": False, "reasons": ["No verification artifact was provided."], "label": "BLOCKED"}
    if _missing(v):
        return {"status": "BLOCKED", "verified": False,
                "reasons": [f"Verification artifact is {v['status']}."], "label": "BLOCKED"}
    if not isinstance(v, dict):
        return {"status": "BLOCKED", "verified": False, "reasons": ["Verification artifact is not a JSON object."], "label": "BLOCKED"}
    status = v.get("status")
    if status is None:
        why = ["Legacy verification artifact without an explicit status or change evidence; "
               "a bare 'verified' flag is not accepted as evidence."]
        return {"status": "TESTS_PASS_CHANGE_UNVERIFIED" if (v.get("after") or {}).get("passed") else "NOT_RUN",
                "verified": False, "reasons": why, "label": "OBSERVED", "legacy": True}
    if status != "VERIFIED_CHANGE":
        return {"status": status, "verified": False, "reasons": list(v.get("status_reasons") or []),
                "label": "BLOCKED" if status in ("BLOCKED", "NOT_RUN") else "OBSERVED"}
    problems = []
    base, after, change = v.get("baseline") or v.get("before"), v.get("after"), v.get("change") or {}
    if not (isinstance(base, dict) and base.get("commands")):
        problems.append("baseline command results are missing")
    if not (isinstance(after, dict) and after.get("passed") is True and after.get("commands")
            and all(c.get("passed") is True for c in after["commands"])):
        problems.append("after-change results are missing or not all passing")
    if not (change.get("declared") and change.get("applied_with_evidence")):
        problems.append("no applied dependency change with evidence is recorded")
    if not (v.get("environments") or v.get("environment")):
        problems.append("environment details are missing")
    if problems:
        return {"status": "TESTS_PASS_CHANGE_UNVERIFIED", "verified": False, "label": "OBSERVED",
                "reasons": ["Artifact claims VERIFIED_CHANGE but is inconsistent: " + "; ".join(problems) + "."]}
    return {"status": "VERIFIED_CHANGE", "verified": True, "label": "VERIFIED", "reasons": list(v.get("status_reasons") or [])}


def _finding_ids(scan: Any, usage: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(scan, dict):
        ids |= {f.get("id") for f in scan.get("findings", []) if isinstance(f, dict)}
    if isinstance(usage, dict):
        ids |= {f.get("id") for f in usage.get("review_leads", []) if isinstance(f, dict)}
    ids.discard(None)
    return ids


def build_capsule(scan: Any, usage: Any, ai: Any, verification: Any, diagnosis: Any = None) -> dict[str, Any]:
    """``diagnosis`` (optional) is the output of :func:`patchproof.diagnose.diagnose`;
    its candidates are carried as HYPOTHESIS items and never change the verification status."""
    va = assess_verification(verification)
    artifacts = [_artifact_state("scan", scan), _artifact_state("usage", usage),
                 _artifact_state("ai_analysis", ai), _artifact_state("verification", verification)]
    notices = []
    for a in artifacts:
        if a["state"] != "available":
            notices.append(f"{a['artifact']} artifact: {a['state']}" + (f" ({a['detail']})" if a.get("detail") else "")
                           + ". Nothing was substituted for it.")
    ai_ok = isinstance(ai, dict) and not _missing(ai)
    known = _finding_ids(scan, usage)
    unknown_refs = sorted(set(ai.get("finding_ids", [])) - known) if ai_ok and isinstance(ai.get("finding_ids"), list) else []
    if unknown_refs:
        notices.append("AI analysis references finding IDs not present in the scan/usage artifacts: " + ", ".join(map(str, unknown_refs)))
    rollback = []
    if ai_ok:
        for i, opt in enumerate(ai.get("options") or []):
            if isinstance(opt, dict) and opt.get("rollback"):
                rollback.append({"option_index": i, "rollback": opt["rollback"], "source": "AI PROPOSAL"})
    scan_ok = isinstance(scan, dict) and not _missing(scan)
    scan_ctx = None
    if scan_ok:
        scan_ctx = {"root": scan.get("root"), "scan_status": scan.get("scan_status", "unknown"),
                    "manifests_scanned": len(scan.get("manifests_scanned", [])),
                    "declaration_count": scan.get("declaration_count"),
                    "finding_count": len(scan.get("findings", [])), "error_count": len(scan.get("errors", []))}
    overall = "VERIFIED_CHANGE" if va["verified"] else "NOT_VERIFIED"
    labels = {"scan_findings": "OBSERVED", "usage": "OBSERVED", "ai_analysis": "AI PROPOSAL",
              "verification": va["label"]}
    diag_ok = isinstance(diagnosis, dict) and diagnosis.get("report_type") == "diagnosis"
    if diag_ok:
        labels["diagnosis"] = "HYPOTHESIS"
    capsule = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "dependency_exit_capsule",
        "product": "PatchProof",
        "purpose": "Evidence-backed dependency maintenance record",
        "labels": labels,
        "repository": scan_ctx,
        "scan": scan, "usage": usage, "ai_analysis": ai, "verification": verification,
        "verification_assessment": va,
        "verification_status": va["status"],
        "overall_status": overall,
        "interpretation": (
            "A declared dependency change was applied with evidence and the recorded after-change commands passed in the recorded environment."
            if va["verified"] else
            "No verified dependency change is recorded (" + va["status"] + "). Any AI output remains a proposal; "
            "observations are not proof of runtime failure."),
        "artifact_states": artifacts,
        "missing_artifact_notices": notices,
        "rollback": rollback,
        "rollback_note": None if rollback else "No rollback information was supplied by a real analysis artifact.",
        "limitations": [
            "This capsule records available evidence only; it does not assess security advisories.",
            "Missing or unreadable artifacts remain missing and are not replaced with synthetic results.",
            "Scanner findings are manifest observations, not proof of runtime failure.",
            "A package with no detected import is a review lead, not proof it is unused.",
            "A migration recommendation is a proposal until the verification runner records a VERIFIED_CHANGE.",
            "Human review is required before applying dependency changes.",
        ],
    }
    if diag_ok:
        capsule["diagnosis"] = diagnosis
    return capsule


def to_markdown(c: dict[str, Any]) -> str:
    L = ["# PatchProof Dependency Exit Capsule", "",
         f"**Overall status:** `{c['overall_status']}`  |  **Verification status:** `{c['verification_status']}`", "",
         c["interpretation"], ""]
    if c.get("missing_artifact_notices"):
        L += ["## Missing artifact notices", *[f"- **BLOCKED** — {n}" for n in c["missing_artifact_notices"]], ""]
    L += ["## Repository and scan summary (OBSERVED)"]
    scan = c.get("scan")
    if isinstance(scan, dict) and not _missing(scan):
        L += [f"- Scan root: `{scan.get('root', 'unknown')}`", f"- Scan status: `{scan.get('scan_status', 'unknown')}`",
              f"- Manifests scanned: {len(scan.get('manifests_scanned', []))}",
              f"- Declarations: {scan.get('declaration_count', 'unknown')}",
              f"- Findings: {len(scan.get('findings', []))}",
              f"- Parse/read errors: {(scan.get('summary') or {}).get('error_count', len(scan.get('errors', [])))}"]
        if scan.get("scan_status") == "no_manifests_found":
            L.append("- No manifests were found: the repository was not assessed (this is not a clean result).")
        for f in scan.get("findings", []):
            L += ["", f"### {f.get('id', 'Finding')}: {f.get('title', 'Untitled')}  `OBSERVED`",
                  f"- Type: `{f.get('type', 'unknown')}`; severity: `{f.get('severity', 'unknown')}`; assessment: `{f.get('assessment', 'n/a')}`",
                  f"- Summary: {f.get('summary', '')}"]
            for ev in f.get("evidence", []):
                L.append(f"- Evidence: `{ev.get('file', '?')}` line {ev.get('line') if ev.get('line') is not None else 'n/a'}: `{ev.get('excerpt', '')}`")
            if f.get("inferred"):
                L.append(f"- Inferred (not observed): {f['inferred']}")
    else:
        L.append("- Scan report unavailable.")
    L += ["", "## Dependency usage (OBSERVED)"]
    usage = c.get("usage")
    if isinstance(usage, dict) and not _missing(usage):
        s = usage.get("summary", {})
        L += [f"- Declared packages traced: {s.get('declared_packages', 'unknown')}",
              f"- Status counts: {s.get('by_status', {})}",
              f"- Analysis complete: {s.get('analysis_complete', 'unknown')}"]
        for lead in usage.get("review_leads", []):
            L.append(f"- Review lead `{lead.get('id')}` — {lead.get('package')}: {lead.get('usage_status')} (a lead, not proof the package is unused)")
    else:
        L.append("- Usage report unavailable.")
    diag = c.get("diagnosis")
    if isinstance(diag, dict) and diag.get("candidates") is not None:
        L += ["", "## Root-cause candidates (HYPOTHESIS)"]
        if not diag["candidates"]:
            L.append("- No candidate causes could be derived from the available artifacts.")
        for cand in diag["candidates"]:
            L += ["", f"### {cand.get('id')}: {cand.get('title')}  `HYPOTHESIS`",
                  f"- Type: `{cand.get('type')}`; support: `{cand.get('support')}`"]
            for o in cand.get("observed", []):
                loc = f" (`{o['file']}` line {o['line']})" if o.get("file") and o.get("line") is not None else ""
                L.append(f"- Observed [{o.get('source')}]: {o.get('text')}{loc}")
            if cand.get("inferred"):
                L.append(f"- Inferred (not observed): {cand['inferred']}")
            for u in cand.get("uncertainties", []):
                L.append(f"- Uncertainty: {u}")
    L += ["", "## AI migration analysis (AI PROPOSAL)"]
    ai = c.get("ai_analysis")
    if isinstance(ai, dict) and not _missing(ai):
        L += [f"- Model: `{ai.get('model', 'not recorded')}`", f"- Runtime: `{ai.get('runtime', 'not recorded')}`",
              f"- Finding IDs: {', '.join(map(str, ai.get('finding_ids', []))) or 'none recorded'}",
              f"- Analysis: {ai.get('analysis', 'No analysis text recorded.')}"]
        for i, h in enumerate(ai.get("diagnostic_hypotheses") or []):
            if isinstance(h, dict):
                L.append(f"- Hypothesis {i} ({h.get('confidence', 'confidence not recorded')} confidence, AI PROPOSAL): {h.get('hypothesis', '(none)')}")
                for k, label in (("supporting_evidence", "Supporting"), ("contradicting_evidence", "Contradicting"),
                                 ("discriminating_tests", "Discriminating test (NOT_RUN)")):
                    for item in h.get(k) or []:
                        L.append(f"  - {label}: {item}")
        for i, opt in enumerate(ai.get("options") or []):
            if isinstance(opt, dict):
                L.append(f"- Option {i}: {opt.get('description', '(no description)')}")
        if ai.get("uncertainties"):
            L.append("- Uncertainties: " + "; ".join(map(str, ai["uncertainties"])))
        L.append("- These are proposals; none has been applied or verified unless the verification section says so.")
    else:
        L.append("AI analysis artifact unavailable; no AI result has been fabricated.")
    L += ["", "## Verification"]
    va = c["verification_assessment"]
    tag = {"VERIFIED": "VERIFIED", "BLOCKED": "BLOCKED"}.get(va["label"], "OBSERVED")
    L += [f"- Status: `{va['status']}` `{tag}`"] + [f"- Reason: {r}" for r in va.get("reasons", [])]
    v = c.get("verification")
    if isinstance(v, dict) and not _missing(v):
        env = v.get("environment") or {}
        if env:
            L.append(f"- Environment: Python {env.get('python_version', '?')} on {env.get('os', '?')}; "
                     f"isolated: {env.get('environment_isolated', 'unknown')}")
        chg = v.get("change") or {}
        if chg.get("declared"):
            L.append(f"- Declared change: pip_install={chg.get('pip_install')} file_edits={len(chg.get('file_edits', []))}; "
                     f"applied with evidence: {chg.get('applied_with_evidence')}")
            for d in chg.get("environment_diff") or []:
                L.append(f"  - {d['package']}: {d['before']} -> {d['after']}")
        else:
            L.append("- No dependency change was declared.")
        for key in ("baseline", "after"):
            ph = v.get(key) if key != "baseline" else (v.get("baseline") or v.get("before"))
            if isinstance(ph, dict):
                L.append(f"- {key.title()}: {'passed' if ph.get('passed') else 'failed'}"
                         + (f" — {ph['test_summary']}" if ph.get("test_summary") else ""))
                for cmd in ph.get("commands", []) or []:
                    L.append(f"  - `{cmd.get('display') or cmd.get('command')}` → exit code `{cmd.get('exit_code')}`, status `{cmd.get('status', 'n/a')}`")
                if not ph.get("commands") and ph.get("command"):
                    L.append(f"  - `{ph.get('command')}` → exit code `{ph.get('exit_code')}`")
    L += ["", "## Rollback"]
    L += [f"- (AI PROPOSAL, option {r['option_index']}) {r['rollback']}" for r in c.get("rollback", [])] or [f"- {c['rollback_note']}"]
    L += ["", "## Limitations", *[f"- {x}" for x in c.get("limitations", [])], ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Combine PatchProof evidence artifacts into an exit capsule.")
    for opt in ("--scan", "--usage", "--ai", "--verification", "--diagnosis"):
        p.add_argument(opt)
    p.add_argument("--json", default="dependency-exit-capsule.json")
    p.add_argument("--markdown", default="dependency-exit-capsule.md")
    a = p.parse_args(argv)
    capsule = build_capsule(load_json_artifact(a.scan), load_json_artifact(a.usage),
                            load_json_artifact(a.ai), load_json_artifact(a.verification),
                            load_json_artifact(a.diagnosis) if a.diagnosis else None)
    jp, mp = Path(a.json), Path(a.markdown)
    write_json(jp, capsule)
    mp.parent.mkdir(parents=True, exist_ok=True)
    with open(mp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(to_markdown(capsule))
    print(f"Wrote {jp} and {mp}; overall_status={capsule['overall_status']}; verification_status={capsule['verification_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
