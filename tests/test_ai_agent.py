"""Tests for evidence collection in the migration agent."""
from pathlib import Path

from patchproof.ai import migration_agent as agent


def test_manifest_evidence_resolves_pyproject_entry_without_line_number(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n    "pydantic>=2",\n]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(agent, "ROOT", tmp_path)

    findings = [{
        "id": "MANIFEST-CONFLICT-pydantic",
        "package": "pydantic",
        "evidence": [{
            "file": "pyproject.toml",
            "line": None,
            "declaration": "pydantic>=2",
        }],
    }]

    result = agent.matching_manifest_evidence(findings)

    assert len(result) == 1
    assert result[0]["line"] == 3
    assert result[0]["text"] == '"pydantic>=2",'


def test_manifest_evidence_rejects_paths_outside_repo(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside-requirements.txt"
    outside.write_text("pydantic>=2\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ROOT", tmp_path)

    findings = [{
        "id": "F-1",
        "package": "pydantic",
        "evidence": [{
            "file": "../outside-requirements.txt",
            "line": 1,
            "declaration": "pydantic>=2",
        }],
    }]

    assert agent.matching_manifest_evidence(findings) == []


def test_usage_evidence_returns_package_entry_not_entire_report():
    report = {
        "tool": "PatchProof",
        "results": [
            {"package": "pydantic", "status": "import_found",
             "locations": [{"file": "app.py", "line": 4, "module": "pydantic"}]},
            {"package": "requests", "status": "import_found", "locations": []},
        ],
    }

    result = agent.matching_usage_evidence(
        report, [{"id": "F-1", "package": "pydantic"}]
    )

    assert len(result) == 1
    assert result[0]["entry"]["package"] == "pydantic"
    assert result[0]["entry"] != report


def test_usage_evidence_handles_missing_report():
    assert agent.matching_usage_evidence(
        None, [{"id": "F-1", "package": "pydantic"}]
    ) == []


def test_manifest_evidence_deduplicates_same_declaration(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text(
        "pydantic==1.10.13\n", encoding="utf-8"
    )
    monkeypatch.setattr(agent, "ROOT", tmp_path)
    item = {"file": "requirements.txt", "line": 1,
            "declaration": "pydantic==1.10.13"}
    findings = [{"id": "F-1", "package": "pydantic",
                 "evidence": [item, dict(item)]}]

    result = agent.matching_manifest_evidence(findings)

    assert len(result) == 1
