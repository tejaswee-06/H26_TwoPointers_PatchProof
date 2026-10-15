
"""Validation for PatchProof migration-advisor output."""
import json


REQUIRED_KEYS = {
    "model",
    "runtime",
    "finding_ids",
    "analysis",
    "diagnostic_hypotheses",
    "options",
    "recommended_option",
    "uncertainties",
}

OPTION_KEYS = {
    "description",
    "benefits",
    "risks",
    "files_to_change",
    "verification_commands",
    "rollback",
}


def validate_advice(data: dict, expected_finding_ids: list[str]) -> dict:
    """Validate Gemma's migration advice and mark it as unverified."""
    if not isinstance(data, dict):
        raise ValueError("AI output must be a JSON object")

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    for key in ("model", "runtime", "analysis"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"{key} must be a non-empty string")

    if data["runtime"] != "ollama-local":
        raise ValueError("Unexpected runtime")

    hypotheses = data["diagnostic_hypotheses"]
    if not isinstance(hypotheses, list) or not hypotheses:
        raise ValueError("At least one diagnostic hypothesis is required")

    hypothesis_keys = {
        "hypothesis",
        "supporting_evidence",
        "contradicting_evidence",
        "confidence",
        "discriminating_tests",
    }
    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            raise ValueError("Each diagnostic hypothesis must be an object")
        missing_hypothesis = hypothesis_keys - hypothesis.keys()
        if missing_hypothesis:
            raise ValueError(
                f"Diagnostic hypothesis missing: {sorted(missing_hypothesis)}"
            )
        if (
            not isinstance(hypothesis["hypothesis"], str)
            or not hypothesis["hypothesis"].strip()
        ):
            raise ValueError("hypothesis must be a non-empty string")
        if hypothesis["confidence"] not in {"low", "medium", "high"}:
            raise ValueError("hypothesis confidence must be low, medium, or high")
        for key in (
            "supporting_evidence",
            "contradicting_evidence",
            "discriminating_tests",
        ):
            value = hypothesis[key]
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip()
                for item in value
            ):
                raise ValueError(
                    f"{key} must be a list of non-empty strings"
                )

    if not isinstance(data["finding_ids"], list):
        raise ValueError("finding_ids must be a list")
    if not data["finding_ids"]:
        raise ValueError("finding_ids must contain at least one finding ID")

    if not all(
        isinstance(item, str) and item.strip()
        for item in data["finding_ids"]
    ):
        raise ValueError("finding_ids must contain non-empty strings")

    if len(data["finding_ids"]) != len(set(data["finding_ids"])):
        raise ValueError("finding_ids must not contain duplicates")

    if not set(data["finding_ids"]).issubset(set(expected_finding_ids)):
        raise ValueError("AI referenced an unknown finding ID")

    if not isinstance(data["options"], list) or not data["options"]:
        raise ValueError("At least one migration option is required")

    for option in data["options"]:
        if not isinstance(option, dict):
            raise ValueError("Each option must be an object")

        missing_option = OPTION_KEYS - option.keys()
        if missing_option:
            raise ValueError(
                f"Migration option missing: {sorted(missing_option)}"
            )

        if (
            not isinstance(option["description"], str)
            or not option["description"].strip()
        ):
            raise ValueError(
                "description must be a non-empty string"
            )

        for key in (
            "benefits",
            "risks",
            "files_to_change",
            "verification_commands",
        ):
            if not isinstance(option[key], list):
                raise ValueError(f"{key} must be a list")

            if any(
                not isinstance(item, str) or not item.strip()
                for item in option[key]
            ):
                raise ValueError(
                    f"{key} must contain only non-empty strings"
                )

        if not isinstance(option["rollback"], str):
            raise ValueError("rollback must be a string")

        if not option["rollback"].strip():
            raise ValueError("rollback must be a non-empty string")

    index = data["recommended_option"]
    if type(index) is not int or not 0 <= index < len(data["options"]):
        raise ValueError("recommended_option is out of range")

    if not isinstance(data["uncertainties"], list):
        raise ValueError("uncertainties must be a list")

    if any(
        not isinstance(item, str) or not item.strip()
        for item in data["uncertainties"]
    ):
        raise ValueError(
            "uncertainties must contain only non-empty strings"
        )

    # The AI cannot certify its own recommendation.
    data["decision_status"] = "PROPOSED"
    data["verification_status"] = "NOT_RUN"

    return data


def parse_and_validate(
    raw: str,
    expected_finding_ids: list[str],
) -> dict:
    """Parse JSON from Gemma and validate its structure."""
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemma returned invalid JSON: {exc}"
        ) from exc

    return validate_advice(result, expected_finding_ids)
