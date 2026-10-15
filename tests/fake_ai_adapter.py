"""TEST DOUBLE ONLY — not a model and never shipped as analysis.

Used by tests/test_server.py to exercise the adapter integration path
(PATCHPROOF_AI_ADAPTER=fake_ai_adapter). It echoes evidence IDs back so the
plumbing can be checked; its text says plainly that it is not model output.
"""


def status():
    return {"model": "TEST-DOUBLE-not-a-model", "runtime": "pytest", "ready": True}


def analyze(bundle, timeout_seconds=300):
    ids = [f["id"] for f in bundle.get("findings", [])]
    return {
        "model": "TEST-DOUBLE-not-a-model",
        "runtime": "pytest",
        "finding_ids": ids,
        "analysis": "TEST DOUBLE OUTPUT — not produced by any model.",
        "options": [
            {"description": "Test option A", "benefits": [], "risks": [], "files_to_change": [],
             "verification_commands": ["python -m pytest -q"], "rollback": "Revert the test change.", "verified": True},
            {"description": "Test option B", "benefits": [], "risks": [], "files_to_change": [],
             "verification_commands": [], "rollback": "n/a"},
        ],
        "recommended_option": 0,
        "uncertainties": ["Test double."],
    }
