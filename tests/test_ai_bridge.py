"""AI integration point: evidence bundle, adapter discovery and schema validation (no model involved)."""
import json
from pathlib import Path

from patchproof import ai_bridge
from patchproof.diagnose import diagnose

LW = Path(__file__).resolve().parents[1] / "examples" / "linkwatch_artifacts"


def _lw(name):
    return json.loads((LW / name).read_text(encoding="utf-8"))


def _valid(**over):
    base = {"model": "gemma-4-e4b-it", "runtime": "local", "finding_ids": ["F-3C1708E248"], "analysis": "text",
            "options": [{"description": "a", "benefits": [], "risks": [], "files_to_change": [], "verification_commands": [], "rollback": "r"},
                        {"description": "b", "benefits": [], "risks": [], "files_to_change": [], "verification_commands": ["pytest -q"], "rollback": "r"}],
            "recommended_option": 1, "uncertainties": []}
    base.update(over)
    return base


def test_bundle_is_bounded_deterministic_and_path_free():
    scan, usage, ver = _lw("patchproof-report.json"), _lw("patchproof-usage-report.json"), _lw("verification.json")
    diag = diagnose(scan, usage, ver)
    a = ai_bridge.build_evidence_bundle(scan, usage, ver, diag)
    b = ai_bridge.build_evidence_bundle(scan, usage, ver, diag)
    assert a == b
    text = json.dumps(a)
    assert len(text) < 40000
    assert "<WORKDIR>" in text or "WORKDIR" not in text
    assert a["findings"][0]["id"] == "F-3C1708E248"
    assert {c["type"] for c in a["root_cause_candidates"]} >= {"runtime_import_incompatibility"}
    assert any("soft_unicode" in f["excerpt"] for f in a["failing_output"])
    assert any("PROPOSAL" in i for i in a["instructions"])


def test_adapter_not_connected_when_module_missing(monkeypatch):
    monkeypatch.setenv("PATCHPROOF_AI_ADAPTER", "no_such_adapter_module")
    st = ai_bridge.adapter_status()
    assert st["state"] == "NOT_CONNECTED" and st["available"] is False
    assert "no_such_adapter_module" in st["reason"]


def test_adapter_discovery_via_env(monkeypatch):
    monkeypatch.setenv("PATCHPROOF_AI_ADAPTER", "fake_ai_adapter")
    assert ai_bridge.adapter_status()["state"] == "READY"
    monkeypatch.setenv("PATCHPROOF_AI_ADAPTER", "json")  # importable but no analyze()
    assert ai_bridge.adapter_status()["state"] == "NOT_CONNECTED"


def test_validator_accepts_schema_and_marks_everything_proposed():
    v = ai_bridge.validate_ai_artifact(_valid(), {"F-3C1708E248"})
    assert v["valid"] and not v["errors"]
    assert all(s["status"] == "PROPOSED" for s in v["option_states"])
    assert v["option_states"][1]["verification_commands"] == [{"command": "pytest -q", "status": "NOT_RUN"}]


def test_validator_errors_and_warnings():
    assert not ai_bridge.validate_ai_artifact([], set())["valid"]
    v = ai_bridge.validate_ai_artifact(_valid(model="", options="x", recommended_option=5), set())
    assert not v["valid"] and len(v["errors"]) >= 2
    v = ai_bridge.validate_ai_artifact(_valid(model="other-llm", verified=True, finding_ids=["F-X"]), {"F-3C1708E248"})
    w = " ".join(v["warnings"])
    assert v["valid"] and "Gemma" in w and "F-X" in w and "cannot record verification" in w
    v = ai_bridge.validate_ai_artifact(_valid(options=[{"description": "only"}], recommended_option=0), set())
    assert any("Fewer than two" in x for x in v["warnings"])
    assert not ai_bridge.validate_ai_artifact(_valid(recommended_option=True), set())["valid"]
