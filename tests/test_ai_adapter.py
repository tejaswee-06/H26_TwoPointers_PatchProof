
"""Offline tests for the local Gemma adapter."""

import pytest

from patchproof.ai import ollama_adapter as adapter


FINDINGS = [
    {
        "id": "MANIFEST-CONFLICT-pydantic",
        "package": "pydantic",
        "title": "Conflicting declarations for pydantic",
        "evidence": [
            {
                "file": "requirements.txt",
                "line": 5,
                "declaration": "pydantic==1.10.13",
            },
            {
                "file": "pyproject.toml",
                "line": None,
                "declaration": "pydantic>=2",
            },
        ],
    }
]


def test_prompt_requests_multiple_options_and_preserves_evidence():
    prompt = adapter._build_prompt(
        FINDINGS,
        {
            "manifest_excerpts": [
                {
                    "file": "requirements.txt",
                    "line": 5,
                    "text": "pydantic==1.10.13",
                }
            ]
        },
    )

    assert "at least TWO distinct migration options" in prompt
    assert "MANIFEST-CONFLICT-pydantic" in prompt
    assert "pydantic==1.10.13" in prompt
    assert "Additional evidence context" in prompt


def test_empty_findings_are_rejected():
    with pytest.raises(ValueError, match="non-empty list"):
        adapter.generate_migration_advice([])


def test_finding_without_id_is_rejected():
    with pytest.raises(ValueError, match="valid id"):
        adapter.generate_migration_advice(
            [{"package": "pydantic"}]
        )


def test_duplicate_finding_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        adapter.generate_migration_advice(
            [FINDINGS[0], dict(FINDINGS[0])]
        )


def test_model_failure_is_reported_without_remote_fallback(monkeypatch):
    def fail_request(_payload):
        raise adapter.OllamaAdapterError("local Ollama unavailable")

    monkeypatch.setattr(adapter, "_post_chat", fail_request)

    with pytest.raises(
        adapter.OllamaAdapterError,
        match="local Ollama unavailable",
    ):
        adapter.generate_migration_advice(FINDINGS)


def test_model_output_cannot_mark_itself_verified(monkeypatch):
    """Model-supplied status must never override application status."""
    valid_response = {
        "model": adapter.MODEL,
        "message": {
            "content": (
                "{"
                '"model":"test-model",'
                '"runtime":"ollama-local",'
                '"finding_ids":["MANIFEST-CONFLICT-pydantic"],'
                '"analysis":"The manifests have conflicting constraints.",'
                '"diagnostic_hypotheses":[{"hypothesis":"The declarations may diverge",'
                '"supporting_evidence":["Two manifest constraints differ"],'
                '"contradicting_evidence":["No runtime failure is proven"],'
                '"confidence":"medium",'
                '"discriminating_tests":["Compare clean installs from each manifest"]}],'
                '"options":['
                '{"description":"Use requirements.txt as the source of truth",'
                '"benefits":["Preserves the pinned declaration"],'
                '"risks":["May conflict with code requiring Pydantic v2"],'
                '"files_to_change":["pyproject.toml"],'
                '"verification_commands":["python -m pytest -q"],'
                '"rollback":"Restore the original pyproject.toml."},'
                '{"description":"Use pyproject.toml as the source of truth",'
                '"benefits":["Aligns with the declared v2 constraint"],'
                '"risks":["May require compatibility changes"],'
                '"files_to_change":["requirements.txt"],'
                '"verification_commands":["python -m pip check"],'
                '"rollback":"Restore the original requirements.txt."}'
                '],'
                '"recommended_option":0,'
                '"uncertainties":["The authoritative manifest is unknown"],'
                '"decision_status":"VERIFIED",'
                '"verification_status":"PASSED"'
                "}"
            )
        },
        "total_duration": 123,
    }

    monkeypatch.setattr(
        adapter,
        "_post_chat",
        lambda _payload: valid_response,
    )

    result = adapter.generate_migration_advice(FINDINGS)

    assert len(result["options"]) == 2
    assert result["decision_status"] == "PROPOSED"
    assert result["verification_status"] == "NOT_RUN"
