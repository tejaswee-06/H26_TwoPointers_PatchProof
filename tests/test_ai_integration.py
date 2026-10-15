"""Person 2's Gemma adapter wired into the engine (P1) and dashboard contract (P3). Offline: Ollama is mocked."""
import json
from pathlib import Path

import pytest

from patchproof import ai as ai_pkg
from patchproof import ai_bridge, capsule
from patchproof.ai import ollama_adapter as oa

from test_server import api, wait_job  # noqa: F401  (reuse the API fixture/helpers)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _model_reply(ids):
    return {"model": "gemma4:test", "total_duration": 5, "message": {"content": json.dumps({
        "model": "gemma4:test", "runtime": "ollama-local", "finding_ids": ids[:1], "analysis": "Grounded in the bundle.",
        "diagnostic_hypotheses": [{"hypothesis": "h", "supporting_evidence": ["s"], "contradicting_evidence": [],
                                   "confidence": "low", "discriminating_tests": ["t"]}],
        "options": [{"description": f"opt {i}", "benefits": ["b"], "risks": ["r"], "files_to_change": [],
                     "verification_commands": ["python -m pytest -q"], "rollback": "git checkout"} for i in range(2)],
        "recommended_option": 0, "uncertainties": ["u"],
        "decision_status": "VERIFIED", "verification_status": "PASSED"})}}


@pytest.fixture
def bundle():
    d = EX / "linkwatch_artifacts"
    return ai_bridge.build_evidence_bundle(_load(d / "patchproof-report.json"), _load(d / "patchproof-usage-report.json"),
                                           _load(d / "verification.json"), None)


def test_bundle_maps_to_adapter_inputs(bundle):
    items, ctx = ai_pkg.bundle_to_inputs(bundle)
    assert items and all(i["id"] for i in items)
    assert ctx["manifest_excerpts"] and ctx["manifest_excerpts"][0]["finding_id"].startswith("F-")
    assert ctx["test_evidence"]["available"] in (True, False)


def test_empty_bundle_rejected():
    with pytest.raises(ValueError, match="no findings"):
        ai_pkg.bundle_to_inputs({"findings": []})


def test_analyze_validates_and_cannot_self_verify(bundle, monkeypatch):
    ids = [f["id"] for f in bundle["findings"]]
    monkeypatch.setattr(oa, "_post_chat", lambda payload, timeout=None: _model_reply(ids))
    out = ai_pkg.analyze(bundle, timeout_seconds=5)
    assert out["decision_status"] == "PROPOSED" and out["verification_status"] == "NOT_RUN"
    assert out["diagnostic_hypotheses"][0]["confidence"] == "low"
    val = ai_bridge.validate_ai_artifact(out, ai_bridge.known_ids(None, None) | set(ids))
    assert val["valid"] and not any("ignored" in w for w in val["warnings"])


def test_unknown_finding_id_from_model_is_rejected(bundle, monkeypatch):
    bad = _model_reply(["F-DOESNOTEXIST"])
    monkeypatch.setattr(oa, "_post_chat", lambda payload, timeout=None: bad)
    with pytest.raises(oa.OllamaAdapterError, match="schema validation"):
        ai_pkg.analyze(bundle)


def test_status_reports_unreachable_ollama(monkeypatch):
    monkeypatch.setattr(oa, "OLLAMA_URL", "http://127.0.0.1:9/api/chat")
    st = ai_pkg.status()
    assert st["ready"] is False and "Ollama" in st["reason"]
    assert ai_bridge.adapter_status()["state"] == "UNAVAILABLE"


def test_p2_sample_output_passes_bridge_validation_and_renders_in_capsule():
    ai = _load(EX / "linkwatch_ai_output" / "ai-analysis.json")
    val = ai_bridge.validate_ai_artifact(ai, {"MANIFEST-CONFLICT-pydantic"})
    assert val["valid"], val
    assert not [w for w in val["warnings"] if "ignored" in w]
    md = capsule.to_markdown(capsule.build_capsule(None, None, ai, None))
    assert "Hypothesis 0" in md and "AI PROPOSAL" in md


def test_bridge_rejects_malformed_hypotheses():
    ai = {"model": "gemma4", "runtime": "x", "analysis": "a", "finding_ids": [], "options": [],
          "diagnostic_hypotheses": [{"hypothesis": "h", "confidence": "certain"}]}
    val = ai_bridge.validate_ai_artifact(ai)
    assert not val["valid"] and any("confidence" in e for e in val["errors"])


def test_end_to_end_server_run_with_real_p2_adapter(api, monkeypatch):
    monkeypatch.setattr(ai_pkg, "status", lambda: {"model": "gemma4:test", "runtime": "ollama-local", "ready": True})
    ids = [x["id"] for x in api.app.evidence_bundle("bundled-linkwatch")["findings"]]
    monkeypatch.setattr(oa, "_post_chat", lambda payload, timeout=None: _model_reply(ids))
    assert api("GET", "/api/health")[1]["ai_adapter"]["state"] == "READY"
    st, data = api("POST", "/api/runs/bundled-linkwatch/ai/run", {})
    assert st == 202
    job = wait_job(api, data["job"]["id"])
    assert job["state"] == "succeeded", job
    _, d = api("GET", "/api/runs/bundled-linkwatch")
    assert d["artifacts"]["ai"]["diagnostic_hypotheses"]
    assert d["artifacts"]["ai"]["verification_status"] == "NOT_RUN"
    assert d["capsule"]["verification_status"] == "VERIFIED_CHANGE"  # only real verification evidence
    assert "Hypothesis 0" in d["capsule_markdown"]
