"""Unit tests for PatchProof's migration-advice schema."""
import copy
import json

import pytest

from patchproof.ai.schemas import parse_and_validate, validate_advice


FINDING_IDS = ["MANIFEST-CONFLICT-pydantic"]


def make_advice():
    return {
        "model": "gemma4:e2b-it-q4_K_M",
        "runtime": "ollama-local",
        "finding_ids": FINDING_IDS.copy(),
        "analysis": "The manifests declare different constraints.",
        "diagnostic_hypotheses": [
            {
                "hypothesis": "The manifests may lead to inconsistent environments.",
                "supporting_evidence": ["The two manifest constraints differ."],
                "contradicting_evidence": ["No runtime failure has been proven."],
                "confidence": "medium",
                "discriminating_tests": ["Compare clean installs from both manifests."],
            }
        ],
        "options": [
            {
                "description": "Use requirements.txt as the source of truth",
                "benefits": ["Keeps the explicit pinned version"],
                "risks": ["May conflict with Pydantic v2 code"],
                "files_to_change": ["pyproject.toml"],
                "verification_commands": ["python -m pytest -q"],
                "rollback": "Restore the original pyproject.toml.",
            },
            {
                "description": "Use pyproject.toml as the source of truth",
                "benefits": ["Aligns with the project dependency metadata"],
                "risks": ["May require compatibility work"],
                "files_to_change": ["requirements.txt"],
                "verification_commands": ["python -m pip check"],
                "rollback": "Restore the original requirements.txt.",
            },
        ],
        "recommended_option": 0,
        "uncertainties": ["The authoritative manifest is not known."],
    }


def test_valid_advice_is_accepted_and_marked_unverified():
    result = validate_advice(make_advice(), FINDING_IDS)
    assert result["decision_status"] == "PROPOSED"
    assert result["verification_status"] == "NOT_RUN"


def test_non_object_is_rejected():
    with pytest.raises(ValueError, match="JSON object"):
        validate_advice([], FINDING_IDS)


def test_missing_required_key_is_rejected():
    data = make_advice()
    del data["analysis"]
    with pytest.raises(ValueError, match="Missing required fields"):
        validate_advice(data, FINDING_IDS)


@pytest.mark.parametrize("field", ["model", "runtime", "analysis"])
def test_required_text_fields_must_be_non_empty(field):
    data = make_advice()
    data[field] = "  "
    with pytest.raises(ValueError, match="non-empty"):
        validate_advice(data, FINDING_IDS)


def test_non_local_runtime_is_rejected():
    data = make_advice()
    data["runtime"] = "remote-api"
    with pytest.raises(ValueError, match="Unexpected runtime"):
        validate_advice(data, FINDING_IDS)


def test_unknown_finding_id_is_rejected():
    data = make_advice()
    data["finding_ids"] = ["MADE-UP-ID"]
    with pytest.raises(ValueError, match="unknown finding ID"):
        validate_advice(data, FINDING_IDS)


def test_empty_finding_ids_are_rejected():
    data = make_advice()
    data["finding_ids"] = []
    with pytest.raises(ValueError, match="at least one"):
        validate_advice(data, FINDING_IDS)


def test_duplicate_finding_ids_are_rejected():
    data = make_advice()
    data["finding_ids"] = FINDING_IDS * 2
    with pytest.raises(ValueError, match="duplicates"):
        validate_advice(data, FINDING_IDS)


def test_missing_option_key_is_rejected():
    data = make_advice()
    del data["options"][0]["rollback"]
    with pytest.raises(ValueError, match="Migration option missing"):
        validate_advice(data, FINDING_IDS)


def test_empty_verification_command_is_rejected():
    data = make_advice()
    data["options"][0]["verification_commands"] = [""]
    with pytest.raises(ValueError, match="non-empty strings"):
        validate_advice(data, FINDING_IDS)


def test_non_string_list_item_is_rejected():
    data = make_advice()
    data["options"][0]["risks"] = [None]
    with pytest.raises(ValueError, match="non-empty strings"):
        validate_advice(data, FINDING_IDS)


def test_recommended_option_must_be_in_range():
    data = make_advice()
    data["recommended_option"] = 99
    with pytest.raises(ValueError, match="out of range"):
        validate_advice(data, FINDING_IDS)


def test_model_cannot_mark_advice_verified():
    data = make_advice()
    data["decision_status"] = "VERIFIED"
    data["verification_status"] = "PASSED"
    result = validate_advice(data, FINDING_IDS)
    assert result["decision_status"] == "PROPOSED"
    assert result["verification_status"] == "NOT_RUN"


def test_invalid_json_is_rejected():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_and_validate("{not json", FINDING_IDS)


def test_multiple_options_are_supported():
    data = make_advice()
    result = validate_advice(data, FINDING_IDS)
    assert len(result["options"]) == 2
    assert result["recommended_option"] in (0, 1)



def test_invalid_hypothesis_confidence_is_rejected():
    data = make_advice()
    data["diagnostic_hypotheses"][0]["confidence"] = "certain"
    with pytest.raises(ValueError, match="confidence must be low, medium, or high"):
        validate_advice(data, FINDING_IDS)


def test_missing_diagnostic_hypotheses_is_rejected():
    data = make_advice()
    del data["diagnostic_hypotheses"]
    with pytest.raises(ValueError, match="Missing required fields"):
        validate_advice(data, FINDING_IDS)
