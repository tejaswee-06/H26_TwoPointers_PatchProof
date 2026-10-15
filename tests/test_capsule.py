import copy
import json
import sys

from conftest import write
from patchproof.capsule import assess_verification, build_capsule, main as capsule_main, to_markdown
from patchproof.run import run
from patchproof.scanner import scan_repository
from patchproof.usage import trace_usage

PY = sys.executable
CMD = {"command": ["x"], "display": "x", "exit_code": 0, "passed": True, "status": "passed"}
VERIFIED = {
    "schema_version": "2.0", "status": "VERIFIED_CHANGE", "verified": True, "status_reasons": ["ok"],
    "baseline": {"passed": False, "commands": [{**CMD, "exit_code": 1, "passed": False, "status": "failed"}]},
    "after": {"passed": True, "commands": [CMD], "test_summary": "10 passed"},
    "change": {"declared": True, "applied_with_evidence": True, "pip_install": ["m==2.0.1"],
               "environment_diff": [{"package": "m", "before": "3.0", "after": "2.0.1"}], "file_edits": []},
    "environment": {"python_version": "3.12", "os": "Linux", "environment_isolated": True},
    "environments": {"baseline": {}, "after": {}},
}


def scan_report(tmp_path):
    write(tmp_path / "requirements.txt", "pydantic==1.10.13\n")
    write(tmp_path / "pyproject.toml", '[project]\nname="x"\ndependencies=["pydantic>=2"]\n')
    return scan_repository(tmp_path)


def test_capsule_does_not_fabricate_verification():
    c = build_capsule({"findings": [], "manifests_scanned": [], "declaration_count": 0, "errors": []}, None, None, None)
    assert c["overall_status"] == "NOT_VERIFIED" and c["verification_status"] == "NOT_RUN"
    assert "synthetic results" in " ".join(c["limitations"]) or "No AI result has been fabricated" in to_markdown(c) or "fabricated" in to_markdown(c)
    assert c["ai_analysis"] is None and c["verification"] is None


def test_valid_scan_and_usage_included_with_finding_evidence(tmp_path):
    scan = scan_report(tmp_path)
    usage = trace_usage(tmp_path, mapping={})
    c = build_capsule(scan, usage, None, None)
    md = to_markdown(c)
    assert scan["findings"][0]["id"] in md
    assert "`requirements.txt` line 1: `pydantic==1.10.13`" in md
    assert "`pyproject.toml` line 3" in md
    assert "OBSERVED" in md
    json.loads(json.dumps(c))  # valid JSON


def test_missing_ai_and_verification_artifacts_are_reported(tmp_path):
    c = build_capsule(scan_report(tmp_path), None, {"status": "missing", "requested_path": "ai.json"},
                      {"status": "unreadable", "requested_path": "v.json", "error": "boom"})
    notes = " ".join(c["missing_artifact_notices"])
    assert "ai_analysis artifact: missing" in notes and "verification artifact: unreadable" in notes
    assert c["verification_status"] == "BLOCKED" and c["overall_status"] == "NOT_VERIFIED"
    md = to_markdown(c)
    assert "AI analysis artifact unavailable" in md and "Missing artifact notices" in md


def test_failed_verification_not_verified():
    c = build_capsule(None, None, None, {"schema_version": "2.0", "status": "VERIFICATION_FAILED", "status_reasons": ["After failed"], "verified": False})
    assert c["overall_status"] == "NOT_VERIFIED" and c["verification_status"] == "VERIFICATION_FAILED"


def test_bare_verified_true_is_not_trusted():
    legacy = {"verified": True, "before": {"passed": True}, "after": {"passed": True, "exit_code": 0}}
    c = build_capsule(None, None, None, legacy)
    assert c["overall_status"] == "NOT_VERIFIED" and "bare" in " ".join(c["verification_assessment"]["reasons"])


def test_status_claiming_verified_without_evidence_is_downgraded():
    for mutate in (lambda v: v.pop("baseline"), lambda v: v["change"].update(applied_with_evidence=False),
                   lambda v: v["after"]["commands"][0].update(passed=False), lambda v: (v.pop("environment"), v.pop("environments")), lambda v: v["change"].update(declared=False)):
        v = copy.deepcopy(VERIFIED)
        mutate(v)
        a = assess_verification(v)
        assert a["status"] == "TESTS_PASS_CHANGE_UNVERIFIED" and a["verified"] is False


def test_genuine_verified_change_is_accepted_and_rendered():
    c = build_capsule(None, None, None, copy.deepcopy(VERIFIED))
    assert c["overall_status"] == "VERIFIED_CHANGE" and c["labels"]["verification"] == "VERIFIED"
    md = to_markdown(c)
    assert "m: 3.0 -> 2.0.1" in md and "VERIFIED" in md and "exit code `0`" in md


def test_passing_tests_without_change_labelled_not_verified():
    v = copy.deepcopy(VERIFIED)
    v.update(status="TESTS_PASS_CHANGE_UNVERIFIED", verified=False, change={"declared": False})
    c = build_capsule(None, None, None, v)
    assert c["overall_status"] == "NOT_VERIFIED" and "No dependency change was declared" in to_markdown(c)


def test_ai_is_labelled_proposal_with_rollback_and_unknown_ids_flagged(tmp_path):
    scan = scan_report(tmp_path)
    ai = {"model": "m", "runtime": "r", "finding_ids": [scan["findings"][0]["id"], "F-NOPE"], "analysis": "text",
          "options": [{"description": "Option A", "rollback": "pip install pydantic==1.10.13"}], "uncertainties": ["u"]}
    c = build_capsule(scan, None, ai, None)
    md = to_markdown(c)
    assert "AI PROPOSAL" in md and "pip install pydantic==1.10.13" in md
    assert any("F-NOPE" in n for n in c["missing_artifact_notices"])
    assert c["rollback"][0]["source"] == "AI PROPOSAL"


def test_rollback_absent_is_stated_not_invented():
    c = build_capsule(None, None, None, None)
    assert c["rollback"] == [] and "No rollback information" in to_markdown(c)


def test_no_manifests_not_presented_as_clean(tmp_path):
    write(tmp_path / "a.py", "x=1\n")
    md = to_markdown(build_capsule(scan_repository(tmp_path), None, None, None))
    assert "not assessed" in md and "not a clean result" in md


def test_vulnerability_word_not_used_without_advisory_evidence(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    c = build_capsule(scan_report(root), trace_usage(root, mapping={}), None, None)
    assert "vulnerab" not in to_markdown(c).lower() and "vulnerab" not in json.dumps(c["limitations"]).lower()


def test_legacy_consumer_keys_preserved(tmp_path):
    c = build_capsule(scan_report(tmp_path), None, None, None)
    for key in ("schema_version", "product", "scan", "usage", "ai_analysis", "verification", "overall_status", "interpretation", "limitations"):
        assert key in c


def test_capsule_cli_handles_missing_files(tmp_path):
    write(tmp_path / "scan.json", json.dumps(scan_report(tmp_path / "r")) if False else "{}")
    rc = capsule_main(["--scan", str(tmp_path / "scan.json"), "--ai", str(tmp_path / "none.json"),
                       "--verification", str(tmp_path / "none2.json"),
                       "--json", str(tmp_path / "c.json"), "--markdown", str(tmp_path / "c.md")])
    data = json.loads((tmp_path / "c.json").read_text())
    assert rc == 0 and data["verification_status"] == "BLOCKED"
    assert (tmp_path / "c.md").read_text().startswith("# PatchProof")


# ---------------- orchestration ----------------
def test_run_scan_only_does_not_execute_anything(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    write(repo / "requirements.txt", "requests==2.0\n")
    write(repo / "test_boom.py", "raise SystemExit('tests must not run')\n")
    write(repo / "main.py", "import requests\n")
    assert run(repo, out) == 0
    names = {p.name for p in out.iterdir()}
    assert names == {"patchproof-report.json", "patchproof-usage-report.json", "dependency-exit-capsule.json", "dependency-exit-capsule.md"}
    cap = json.loads((out / "dependency-exit-capsule.json").read_text())
    assert cap["verification"] is None and cap["verification_status"] == "NOT_RUN"


def test_run_output_dir_inside_root_is_not_rescanned(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "requirements.txt", "a==1\n")
    out = repo / "reports"
    run(repo, out)
    first = (out / "patchproof-report.json").read_bytes()
    write(repo / "reports" / "requirements.txt", "poison==9\n")
    run(repo, out)
    assert (out / "patchproof-report.json").read_bytes() == first


def test_run_invalid_root_returns_nonzero(tmp_path):
    assert run(tmp_path / "missing", tmp_path / "out") == 1


def test_run_with_verification_config_and_nonzero_when_not_verified(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    write(repo / "requirements.txt", "a==1\n")
    cfgp = write(tmp_path / "v.json", json.dumps({"target": str(repo), "isolation": "none",
                                                   "baseline": {"commands": [[PY, "-c", "raise SystemExit(1)"]]}}))
    assert run(repo, out, verify_config=str(cfgp)) != 0
    v = json.loads((out / "verification.json").read_text())
    cap = json.loads((out / "dependency-exit-capsule.json").read_text())
    assert v["status"] == "BASELINE_FAILED" and cap["verification_status"] == "BASELINE_FAILED"


def test_run_missing_ai_file_fails_stage_but_still_writes_capsule(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    write(repo / "requirements.txt", "a==1\n")
    assert run(repo, out, ai_path=str(tmp_path / "nope.json")) != 0
    assert (out / "dependency-exit-capsule.json").exists()


def test_run_is_deterministic(tmp_path):
    repo = tmp_path / "repo"
    write(repo / "requirements.txt", "a==1\n")
    write(repo / "requirements-dev.txt", "a==2\n")
    run(repo, tmp_path / "o1")
    run(repo, tmp_path / "o2")
    for name in ("patchproof-report.json", "patchproof-usage-report.json", "dependency-exit-capsule.json", "dependency-exit-capsule.md"):
        assert (tmp_path / "o1" / name).read_bytes() == (tmp_path / "o2" / name).read_bytes()
