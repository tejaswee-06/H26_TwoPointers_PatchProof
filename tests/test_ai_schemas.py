
import pytest

from patchproof.ai.schemas import (
    parse_and_validate,
    validate_advice,
)


VALID_OPTION = {
    "description": "Reconcile the conflicting Pydantic constraints.",
    "benefits": ["Consistent dependency declarations"],
    "risks": ["The correct version may require compatibility changes"],
    "files_to_change": ["requirements.txt", "pyproject.toml"],
    "verification_commands": ["python -m pytest -q", "python -m pip check"],
    "rollback": "Restore the previous dependency declarations.",
}


VALID_ADVICE = {
    "model": "gemma4:e2b-it-q4_K_M",
    "runtime": "ollama-local",
    "finding_ids": ["MANIFEST-CONFLICT-pydantic"],
    "analysis": "The manifests declare conflicting Pydantic constraints.",
    "options": [VALID_OPTION],
    "recommended_option": 0,
    "uncertainties": ["Which manifest is authoritative?"],
}


EXPECTED_IDS = ["MANIFEST-CONFLICT-pydantic"]


def make_advice():
    """Return a fresh sample so tests cannot contaminate one another."""
    return {
        **VALID_ADVICE,
        "finding_ids": list(VALID_ADVICE["finding_ids"]),
        "options": [
            {
                **VALID_OPTION,
                "benefits": list(VALID_OPTION["benefits"]),
                "risks": list(VALID_OPTION["risks"]),
                "files_to_change": list(VALID_OPTION["files_to_change"]),
                "verification_commands": list(
                    VALID_OPTION["verification_commands"]
                ),
            }
        ],
        "uncertainties": list(VALID_ADVICE["uncertainties"]),
    }


def test_valid_advice_is_accepted_and_marked_unverified():
    result = validate_advice(make_advice(), EXPECTED_IDS)

    assert result["decision_status"] == "PROPOSED"
    assert result["verification_status"] == "NOT_RUN"


def test_non_object_output_is_rejected():
    with pytest.raises(ValueError, match="JSON object"):
        validate_advice([], EXPECTED_IDS)


def test_missing_required_field_is_rejected():
    data = make_advice()
    del data["analysis"]

    with pytest.raises(ValueError, match="Missing required fields"):
        validate_advice(data, EXPECTED_IDS)


def test_empty_analysis_is_rejected():
    data = make_advice()
    data["analysis"] = "  "

    with pytest.raises(ValueError, match="analysis must be a non-empty string"):
        validate_advice(data, EXPECTED_IDS)


def test_non_local_runtime_is_rejected():
    data = make_advice()
    data["runtime"] = "remote-api"

    with pytest.raises(ValueError, match="Unexpected runtime"):
        validate_advice(data, EXPECTED_IDS)


def test_unknown_finding_id_is_rejected():
    data = make_advice()
    data["finding_ids"] = ["MADE-UP-FINDING"]

    with pytest.raises(ValueError, match="unknown finding ID"):
        validate_advice(data, EXPECTED_IDS)


def test_empty_options_are_rejected():
    data = make_advice()
    data["options"] = []

    with pytest.raises(ValueError, match="At least one migration option"):
        validate_advice(data, EXPECTED_IDS)


def test_option_with_missing_field_is_rejected():
    data = make_advice()
    del data["options"][0]["rollback"]

    with pytest.raises(ValueError, match="Migration option missing"):
        validate_advice(data, EXPECTED_IDS)


def test_invalid_recommendation_index_is_rejected():
    data = make_advice()
    data["recommended_option"] = 1

    with pytest.raises(ValueError, match="out of range"):
        validate_advice(data, EXPECTED_IDS)


def test_boolean_recommendation_index_is_rejected():
    data = make_advice()
    data["recommended_option"] = True

    with pytest.raises(ValueError, match="out of range"):
        validate_advice(data, EXPECTED_IDS)


def test_invalid_json_is_rejected():
    with pytest.raises(ValueError, match="Gemma returned invalid JSON"):
        parse_and_validate("{invalid json", EXPECTED_IDS)


def test_json_array_is_rejected():
    with pytest.raises(ValueError, match="JSON object"):
        parse_and_validate("[]", EXPECTED_IDS)


def test_empty_verification_command_is_rejected():
    data = make_advice()
    data["options"][0]["verification_commands"] = [""]

    with pytest.raises(ValueError, match="non-empty"):
        validate_advice(data, EXPECTED_IDS)
