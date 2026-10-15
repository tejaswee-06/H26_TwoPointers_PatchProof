"""Integration point between the engine/dashboard and Person 2's local Gemma 4 adapter.

This module contains NO model and never produces analysis text. It:

1. builds the bounded *evidence bundle* that the Gemma 4 adapter should reason over
   (findings, usage leads, root-cause candidates, failing-output excerpts);
2. discovers Person 2's adapter, if installed, and reports ``NOT_CONNECTED`` otherwise;
3. validates an ``ai-analysis.json`` against the agreed schema and normalises
   status labels so model output is always ``PROPOSED`` / ``NOT_RUN``.

Adapter contract (to be implemented by Person 2 in ``patchproof/ai/__init__.py`` or any
module named by the ``PATCHPROOF_AI_ADAPTER`` environment variable)::

    def status() -> dict:            # optional
        return {"model": "<exact Gemma 4 model id>", "runtime": "<local runtime + version>", "ready": True}

    def analyze(bundle: dict, timeout_seconds: int = 300) -> dict:
        # call the LOCAL Gemma 4 runtime with `bundle`; return the AI schema below.
        ...

AI schema (playbook section 4): ``model, runtime, finding_ids, analysis, options[{description,
benefits, risks, files_to_change, verification_commands, rollback}], recommended_option, uncertainties``,
plus Person 2's optional ``diagnostic_hypotheses[{hypothesis, supporting_evidence, contradicting_evidence,
confidence, discriminating_tests}]`` and the inert ``decision_status: PROPOSED`` / ``verification_status: NOT_RUN``.
"""
from __future__ import annotations

import importlib
import os
from typing import Any

from .common import SCHEMA_VERSION

DEFAULT_ADAPTER = "patchproof.ai"
EXCERPT_LIMIT = 4000
_FORBIDDEN_CLAIMS = ("verified", "tests_passed", "status")
_INERT_STATUS_FIELDS = {"decision_status": "PROPOSED", "verification_status": "NOT_RUN"}


def _usable(a: Any) -> bool:
    return isinstance(a, dict) and not (a.get("status") in ("missing", "unreadable") and "schema_version" not in a)


def known_ids(scan: Any, usage: Any, diagnosis: Any = None) -> set[str]:
    ids: set[str] = set()
    if _usable(scan):
        ids |= {f.get("id") for f in scan.get("findings", []) or [] if isinstance(f, dict)}
    if _usable(usage):
        ids |= {f.get("id") for f in usage.get("review_leads", []) or [] if isinstance(f, dict)}
    if isinstance(diagnosis, dict):
        ids |= {c.get("id") for c in diagnosis.get("candidates", []) or [] if isinstance(c, dict)}
    ids.discard(None)
    return ids


def build_evidence_bundle(scan: Any, usage: Any, verification: Any, diagnosis: Any) -> dict[str, Any]:
    """Bounded, deterministic evidence for the model. Never includes whole files or absolute paths."""
    findings = []
    if _usable(scan):
        for f in scan.get("findings", []) or []:
            findings.append({k: f.get(k) for k in ("id", "type", "severity", "package", "title", "observed", "inferred", "status")}
                            | {"evidence": [{k: e.get(k) for k in ("file", "line", "excerpt", "section")} for e in f.get("evidence", []) or []]})
    leads = []
    if _usable(usage):
        for lead in usage.get("review_leads", []) or []:
            leads.append({k: lead.get(k) for k in ("id", "package", "usage_status", "summary")})
    candidates = []
    failures = []
    if isinstance(diagnosis, dict):
        for c in diagnosis.get("candidates", []) or []:
            candidates.append({"id": c.get("id"), "type": c.get("type"), "title": c.get("title"), "support": c.get("support"),
                               "packages": c.get("packages"),
                               "observed": [o.get("text") for o in c.get("observed", []) or []][:20],
                               "inferred": c.get("inferred"), "uncertainties": c.get("uncertainties")})
        budget = EXCERPT_LIMIT
        for f in diagnosis.get("observed_failures", []) or []:
            lines = [e.get("text", "") for e in f.get("errors", [])] + [t.get("test", "") for t in f.get("failing_tests", [])]
            text = "\n".join(lines)[:budget]
            budget -= len(text)
            failures.append({"id": f.get("id"), "phase": f.get("phase"), "command": f.get("command"), "exit_code": f.get("exit_code"),
                             "test_summary": f.get("test_summary"), "excerpt": text})
            if budget <= 0:
                break
    ver = None
    if _usable(verification):
        ch = verification.get("change") or {}
        ver = {"status": verification.get("status"), "status_reasons": verification.get("status_reasons"),
               "change": {"pip_install": ch.get("pip_install"), "environment_diff": ch.get("environment_diff")},
               "baseline_summary": (verification.get("baseline") or {}).get("test_summary"),
               "after_summary": (verification.get("after") or {}).get("test_summary"),
               "environment": {k: (verification.get("environment") or {}).get(k) for k in ("python_version", "os")}}
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "ai_evidence_bundle",
        "repository": scan.get("root") if _usable(scan) else None,
        "instructions": [
            "Reason only over the evidence in this bundle; reference evidence by the IDs given (F-, U-, D-).",
            "Do not invent files, line numbers, versions or test results.",
            "Return at least two migration options when feasible, each with benefits, risks, files_to_change, "
            "verification_commands, and rollback.",
            "Give diagnostic_hypotheses with conservative confidence; a manifest conflict alone is not a runtime cause.",
            "Your output is a PROPOSAL. Do not state that anything was tested or verified.",
        ],
        "response_schema": {"model": "str", "runtime": "str", "finding_ids": ["str"], "analysis": "str",
                            "options": [{"description": "str", "benefits": ["str"], "risks": ["str"], "files_to_change": ["str"],
                                         "verification_commands": ["str"], "rollback": "str"}],
                            "recommended_option": "int|null", "uncertainties": ["str"],
                            "diagnostic_hypotheses": [{"hypothesis": "str", "supporting_evidence": ["str"], "contradicting_evidence": ["str"],
                                                       "confidence": "low|medium|high", "discriminating_tests": ["str"]}]},
        "findings": findings, "usage_review_leads": leads, "root_cause_candidates": candidates,
        "failing_output": failures, "verification": ver,
    }


# ---------------------------------------------------------------------------
def _adapter_name() -> str:
    return os.environ.get("PATCHPROOF_AI_ADAPTER", "").strip() or DEFAULT_ADAPTER


def load_adapter() -> tuple[Any | None, str | None]:
    name = _adapter_name()
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and (name == exc.name or name.startswith(exc.name + ".")):
            return None, f"No Gemma 4 adapter module '{name}' is installed (set PATCHPROOF_AI_ADAPTER to use another module)."
        return None, f"Adapter '{name}' failed to import: {exc}"
    except Exception as exc:  # noqa: BLE001 - surface any import failure honestly
        return None, f"Adapter '{name}' failed to import: {exc.__class__.__name__}: {exc}"
    if not callable(getattr(mod, "analyze", None)):
        return None, f"Adapter '{name}' does not define analyze(bundle, timeout_seconds)."
    return mod, None


def adapter_status() -> dict[str, Any]:
    mod, err = load_adapter()
    base = {"adapter_module": _adapter_name(),
            "integration_point": "patchproof/ai/__init__.py: analyze(bundle: dict, timeout_seconds: int) -> dict",
            "contract_doc": "docs/AI_INTEGRATION.md"}
    if mod is None:
        return {**base, "state": "NOT_CONNECTED", "available": False, "reason": err}
    info: dict[str, Any] = {}
    if callable(getattr(mod, "status", None)):
        try:
            info = mod.status() or {}
        except Exception as exc:  # noqa: BLE001
            return {**base, "state": "ERROR", "available": False, "reason": f"status() failed: {exc.__class__.__name__}: {exc}"}
    ready = info.get("ready", True) is not False
    return {**base, "state": "READY" if ready else "UNAVAILABLE", "available": ready,
            "model": info.get("model"), "runtime": info.get("runtime"), "reason": info.get("reason")}


def run_adapter(bundle: dict[str, Any], timeout_seconds: int = 300) -> dict[str, Any]:
    mod, err = load_adapter()
    if mod is None:
        raise RuntimeError(err or "Adapter unavailable")
    out = mod.analyze(bundle, timeout_seconds=timeout_seconds)
    if not isinstance(out, dict):
        raise ValueError("Adapter returned a non-object result.")
    return out


# ---------------------------------------------------------------------------
def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def validate_ai_artifact(ai: Any, ids: set[str] | None = None) -> dict[str, Any]:
    """Validate against the agreed schema. Never upgrades anything to verified."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(ai, dict):
        return {"valid": False, "errors": ["AI artifact must be a JSON object."], "warnings": [], "option_states": []}
    for key in ("model", "runtime", "analysis"):
        if not isinstance(ai.get(key), str) or not ai.get(key, "").strip():
            errors.append(f"'{key}' must be a non-empty string.")
    if not _str_list(ai.get("finding_ids", [])):
        errors.append("'finding_ids' must be an array of strings.")
    opts = ai.get("options")
    if not isinstance(opts, list):
        errors.append("'options' must be an array.")
        opts = []
    for i, o in enumerate(opts):
        if not isinstance(o, dict):
            errors.append(f"options[{i}] must be an object.")
            continue
        if not isinstance(o.get("description"), str) or not o["description"].strip():
            errors.append(f"options[{i}].description must be a non-empty string.")
        for k in ("benefits", "risks", "files_to_change", "verification_commands"):
            if k in o and not _str_list(o[k]):
                errors.append(f"options[{i}].{k} must be an array of strings.")
            elif k not in o:
                warnings.append(f"options[{i}] has no '{k}'.")
        if "rollback" in o and not isinstance(o["rollback"], str):
            errors.append(f"options[{i}].rollback must be a string.")
        elif not o.get("rollback"):
            warnings.append(f"options[{i}] has no rollback guidance.")
        for claim in _FORBIDDEN_CLAIMS + tuple(_INERT_STATUS_FIELDS):
            if claim in o:
                warnings.append(f"options[{i}].{claim} was ignored: AI output cannot record verification results.")
    ro = ai.get("recommended_option")
    if ro is not None and (not isinstance(ro, int) or isinstance(ro, bool) or not (0 <= ro < len(opts))):
        errors.append("'recommended_option' must be null or an index into 'options'.")
    if "uncertainties" in ai and not _str_list(ai["uncertainties"]):
        errors.append("'uncertainties' must be an array of strings.")
    model = str(ai.get("model") or "")
    if model and "gemma" not in model.lower():
        warnings.append(f"Model id '{model}' does not identify a Gemma model; the event requires a local Gemma 4 model.")
    for claim in _FORBIDDEN_CLAIMS:
        if claim in ai:
            warnings.append(f"Top-level '{claim}' was ignored: AI output cannot record verification results.")
    # Person 2's adapter stamps these two fields itself; they are only accepted in their inert form.
    for key, inert in _INERT_STATUS_FIELDS.items():
        if key in ai and ai[key] != inert:
            warnings.append(f"Top-level '{key}' = {ai[key]!r} was ignored: AI output is always {inert}.")
    hyps = ai.get("diagnostic_hypotheses")
    if hyps is not None:
        if not isinstance(hyps, list):
            errors.append("'diagnostic_hypotheses' must be an array.")
        else:
            for i, h in enumerate(hyps):
                if not isinstance(h, dict) or not isinstance(h.get("hypothesis"), str) or not h["hypothesis"].strip():
                    errors.append(f"diagnostic_hypotheses[{i}] must be an object with a non-empty 'hypothesis'.")
                    continue
                if h.get("confidence") not in ("low", "medium", "high"):
                    errors.append(f"diagnostic_hypotheses[{i}].confidence must be low, medium or high.")
                for k in ("supporting_evidence", "contradicting_evidence", "discriminating_tests"):
                    if not _str_list(h.get(k, [])):
                        errors.append(f"diagnostic_hypotheses[{i}].{k} must be an array of strings.")
    if ids is not None and _str_list(ai.get("finding_ids", [])):
        unknown = sorted(set(ai.get("finding_ids", [])) - ids)
        if unknown:
            warnings.append("finding_ids not present in this run's evidence: " + ", ".join(unknown))
    if len(opts) < 2:
        warnings.append("Fewer than two migration options were provided.")
    states = [{"option_index": i, "status": "PROPOSED",
               "verification_commands": [{"command": c, "status": "NOT_RUN"} for c in (o.get("verification_commands") or [])
                                         if isinstance(c, str)] if isinstance(o, dict) else []}
              for i, o in enumerate(opts)]
    return {"valid": not errors, "errors": errors, "warnings": warnings, "option_states": states}
