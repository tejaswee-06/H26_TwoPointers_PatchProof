"""Root-cause diagnostics: evidence correlation without execution or hard-coded package names."""
import json
from pathlib import Path

from patchproof.capsule import build_capsule, to_markdown
from patchproof.diagnose import classify_frame, diagnose, parse_failure_output, parse_pip_requirement_origins

LW = Path(__file__).resolve().parents[1] / "examples" / "linkwatch_artifacts"


def _lw(name):
    return json.loads((LW / name).read_text(encoding="utf-8"))


def _ver(stdout, after_passed=None, status="BASELINE_FAILED", diff=None, pip_install=None, pip_check=True):
    cmds = []
    if pip_check:
        cmds.append({"command": ["python", "-m", "pip", "check"], "display": "python -m pip check", "passed": True,
                     "status": "passed", "exit_code": 0, "stdout": "No broken requirements found.", "stderr": ""})
    cmds.append({"command": ["python", "-m", "pytest", "-q"], "display": "python -m pytest -q", "passed": False,
                 "status": "failed", "exit_code": 1, "stdout": stdout, "stderr": "", "test_summary": "1 failed"})
    v = {"schema_version": "2.0", "report_type": "verification", "status": status,
         "baseline": {"passed": False, "commands": cmds, "setup": []},
         "dependency_state": {"before": {"captured": True, "packages": {"consumerpkg": "1.0", "providerlib": "9.0"}}},
         "change": {"declared": bool(pip_install), "pip_install": pip_install or [], "environment_diff": diff or []}}
    if after_passed is not None:
        v["after"] = {"passed": after_passed, "test_summary": "3 passed" if after_passed else "1 failed",
                      "commands": [{"passed": after_passed, "stdout": "", "stderr": ""}]}
    return v


TRACE = """
tests/test_x.py:4: in test_x
    import myapp.views
myapp/views.py:2: in <module>
    from consumerpkg import render
/home/u/venv/lib/python3.12/site-packages/consumerpkg/core.py:7: ImportError
E   ImportError: cannot import name 'old_helper' from 'providerlib' (/home/u/venv/lib/python3.12/site-packages/providerlib/__init__.py)
=========================== short test summary info ===========================
FAILED tests/test_x.py::test_x - ImportError: cannot import name 'old_helper'
1 failed, 2 passed in 0.5s
"""


def test_linkwatch_artifacts_yield_supported_runtime_candidate():
    d = diagnose(_lw("patchproof-report.json"), _lw("patchproof-usage-report.json"), _lw("verification.json"))
    runtime = [c for c in d["candidates"] if c["type"] == "runtime_import_incompatibility"]
    assert len(runtime) == 1
    c = runtime[0]
    assert c["status"] == "hypothesis"
    assert c["support"] == "supported_by_verification"
    assert set(c["packages"]) == {"jinja2", "markupsafe"}
    kinds = {o["kind"] for o in c["observed"]}
    assert {"error_line", "failing_test", "traceback_frame", "declaration", "not_declared", "metadata_check",
            "environment_diff", "after_run", "import_site"} <= kinds
    assert any(o.get("file") == "linkwatch/report.py" and o.get("line") == 3 for o in c["observed"] if o["kind"] == "import_site")
    assert all(ch["status"] == "NOT_RUN" for ch in c["discriminating_checks"])
    manifest = [c for c in d["candidates"] if c["type"] == "manifest_inconsistency"][0]
    assert manifest["related_ids"] == ["F-3C1708E248"]
    assert manifest["support"] == "not_tested"
    assert "does NOT allow 1.10.13" in manifest["inferred"]


def test_generic_names_are_parsed_not_hardcoded():
    d = diagnose(None, None, _ver(TRACE))
    c = d["candidates"][0]
    assert c["type"] == "runtime_import_incompatibility"
    assert c["packages"] == ["consumerpkg", "providerlib"]
    assert "old_helper" in c["title"]
    assert c["support"] == "not_tested"
    assert any(o["kind"] == "traceback_frame" and o["file"] == "myapp/views.py" for o in c["observed"])
    assert "/home/u" not in json.dumps(d)


def test_after_failure_is_not_resolved():
    d = diagnose(None, None, _ver(TRACE, after_passed=False, status="VERIFICATION_FAILED",
                                  diff=[{"package": "providerlib", "before": "9.0", "after": "8.0"}], pip_install=["providerlib==8.0"]))
    assert d["candidates"][0]["support"] == "not_resolved_by_change"


def test_verified_change_on_unrelated_package_does_not_support():
    d = diagnose(None, None, _ver(TRACE, after_passed=True, status="VERIFIED_CHANGE",
                                  diff=[{"package": "otherpkg", "before": "1", "after": "2"}], pip_install=["otherpkg==2"]))
    assert d["candidates"][0]["support"] == "not_tested"


def test_module_not_found_and_unclassified():
    out = 'Traceback (most recent call last):\n  File "C:\\\\work\\\\project\\\\run.py", line 1, in <module>\nModuleNotFoundError: No module named \'yaml\'\n'
    d = diagnose(None, None, _ver(out, pip_check=False))
    assert d["candidates"][0]["type"] == "missing_module"
    d2 = diagnose(None, None, _ver("something odd happened\nexit"))
    assert d2["candidates"][0]["type"] == "runtime_failure_unclassified"


def test_without_verification_only_manifest_candidates_and_limitation():
    d = diagnose(_lw("patchproof-report.json"), _lw("patchproof-usage-report.json"), None)
    assert {c["type"] for c in d["candidates"]} == {"manifest_inconsistency"}
    assert d["inputs"]["verification"] is False
    assert any("None was supplied" in x for x in d["limitations"])


def test_missing_markers_and_garbage_inputs_do_not_crash():
    d = diagnose({"status": "missing"}, "not a dict", {"status": "unreadable"})
    assert d["status"] == "insufficient_evidence" and d["candidates"] == []


def test_frame_classification_and_pip_origins():
    assert classify_frame("<WORKDIR>\\baseline\\venv\\Lib\\site-packages\\jinja2\\filters.py")["import_root"] == "jinja2"
    assert classify_frame("<WORKDIR>/after/project/pkg/mod.py") == {"origin": "project", "file": "pkg/mod.py", "import_root": None}
    assert classify_frame("C:/abs/elsewhere/x.py")["origin"] == "unknown"
    o = parse_pip_requirement_origins("Collecting MarkupSafe>=0.23 (from Jinja2==2.11.3->-r requirements.txt (line 4))")
    assert o[0]["package"] == "markupsafe" and o[0]["required_by"] == "Jinja2==2.11.3"
    p = parse_failure_output(TRACE)
    assert p["failing_tests"][0]["test"] == "tests/test_x.py::test_x"


def test_diagnosis_is_deterministic_and_rendered_in_capsule():
    args = (_lw("patchproof-report.json"), _lw("patchproof-usage-report.json"), _lw("verification.json"))
    a, b = diagnose(*args), diagnose(*args)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    cap = build_capsule(args[0], args[1], None, args[2], a)
    assert cap["labels"]["diagnosis"] == "HYPOTHESIS"
    assert cap["overall_status"] == "VERIFIED_CHANGE"  # diagnosis never changes verification status
    md = to_markdown(cap)
    assert "## Root-cause candidates (HYPOTHESIS)" in md
    assert "vulnerab" not in md.lower()
    # Capsule without diagnosis keeps the original shape
    assert "diagnosis" not in build_capsule(args[0], args[1], None, args[2])


def test_windows_drive_letter_frames_are_parsed_and_scrubbed():
    out = ("C:\\Users\\dev\\proj\\tests\\test_a.py:3: in test_a\n"
           "C:\\Users\\dev\\venv\\Lib\\site-packages\\consumerpkg\\x.py:9: ImportError\n"
           "E   ImportError: cannot import name 'gone' from 'providerlib' (C:\\Users\\dev\\venv\\Lib\\site-packages\\providerlib\\__init__.py)\n")
    p = parse_failure_output(out)
    assert any(f["origin"] == "installed" and f["import_root"] == "consumerpkg" for f in p["frames"])
    assert "Users" not in json.dumps(p["errors"])
