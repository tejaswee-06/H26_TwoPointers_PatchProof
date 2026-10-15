import json
import sys

import pytest

from conftest import write
from patchproof.verify import (ConfigError, classify, extract_test_summary, main as verify_main,
                               run_command, validate_argv, verify)

PY = sys.executable


def cfg(target, baseline, after=None, **kw):
    c = {"target": str(target), "isolation": "none", "timeout_seconds": 30, "baseline": {"commands": baseline}}
    if after is not None:
        c["after"] = {"commands": after}
    c.update(kw)
    return c


# ---------------- command runner ----------------
def test_runner_captures_real_exit_code_stdout_stderr(tmp_path):
    r = run_command([PY, "-c", "import sys;print('actual-output');print('err-out',file=sys.stderr);sys.exit(3)"], tmp_path, 10)
    assert r["exit_code"] == 3 and r["passed"] is False and r["status"] == "failed"
    assert "actual-output" in r["stdout"] and "err-out" in r["stderr"]
    assert r["command"][0] == PY and r["shell"] is False and r["duration_seconds"] >= 0


def test_arguments_containing_flags_are_preserved(tmp_path):
    r = run_command([PY, "-c", "import sys;print(sys.argv[1:])", "-q", "--flag=x", "-m"], tmp_path, 10)
    assert r["passed"] and "['-q', '--flag=x', '-m']" in r["stdout"]


def test_no_shell_interpolation(tmp_path):
    r = run_command([PY, "-c", "import sys;print(sys.argv[1])", "a && echo INJECTED; $(whoami)"], tmp_path, 10)
    assert "a && echo INJECTED; $(whoami)" in r["stdout"] and r["stdout"].count("INJECTED") == 1


def test_working_directory_is_respected(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    r = run_command([PY, "-c", "import os;print(os.path.basename(os.getcwd()))"], sub, 10)
    assert r["stdout"].strip() == "sub"


def test_missing_executable_is_not_a_pass(tmp_path):
    r = run_command(["definitely-not-a-real-binary-xyz"], tmp_path, 5)
    assert r["status"] == "not_started" and r["passed"] is False and r["exit_code"] is None and "error" in r


def test_timeout_is_not_a_pass(tmp_path):
    r = run_command([PY, "-c", "import time;print('start',flush=True);time.sleep(30)"], tmp_path, 1)
    assert r["timed_out"] is True and r["passed"] is False and r["status"] == "timeout" and r["exit_code"] is None


@pytest.mark.parametrize("bad", [[], [""], None, "python -m pytest", [PY, 3], ["  "]])
def test_empty_or_malformed_commands_rejected(bad):
    with pytest.raises(ConfigError):
        validate_argv(bad)


def test_extract_test_summary_from_real_output():
    assert extract_test_summary("..\n== 2 passed in 0.1s ==\n") == "2 passed in 0.1s"
    assert extract_test_summary("nothing here") is None


# ---------------- status model (pure) ----------------
def _ph(passed):
    return {"passed": passed}


def test_classify_not_run_and_blocked():
    assert classify(commands_configured=False, blockers=[], baseline=None, after=None, change_declared=False, change_applied=False)[0] == "NOT_RUN"
    assert classify(commands_configured=True, blockers=["x"], baseline=None, after=None, change_declared=False, change_applied=False)[0] == "BLOCKED"


def test_classify_baseline_failed_without_after():
    assert classify(commands_configured=True, blockers=[], baseline=_ph(False), after=None, change_declared=True, change_applied=False)[0] == "BASELINE_FAILED"


def test_classify_passing_baseline_alone_is_not_verified():
    assert classify(commands_configured=True, blockers=[], baseline=_ph(True), after=None, change_declared=False, change_applied=False)[0] == "TESTS_PASS_CHANGE_UNVERIFIED"


def test_classify_after_fails():
    for b in (True, False):
        assert classify(commands_configured=True, blockers=[], baseline=_ph(b), after=_ph(False), change_declared=True, change_applied=True)[0] == "VERIFICATION_FAILED"


def test_classify_after_pass_without_change_is_unverified():
    s, why = classify(commands_configured=True, blockers=[], baseline=_ph(True), after=_ph(True), change_declared=False, change_applied=False)
    assert s == "TESTS_PASS_CHANGE_UNVERIFIED" and "No concrete dependency change" in why[0]


def test_classify_declared_but_unevidenced_change_is_unverified():
    assert classify(commands_configured=True, blockers=[], baseline=_ph(False), after=_ph(True), change_declared=True, change_applied=False)[0] == "TESTS_PASS_CHANGE_UNVERIFIED"


def test_classify_requires_baseline_commands_repeated():
    s, _ = classify(commands_configured=True, blockers=[], baseline=_ph(True), after=_ph(True), change_declared=True,
                    change_applied=True, baseline_cmds=[["a"], ["b"]], after_cmds=[["a"]])
    assert s == "TESTS_PASS_CHANGE_UNVERIFIED"


@pytest.mark.parametrize("flag", ["same_target", "baseline_env_recorded", "after_env_recorded"])
def test_classify_missing_prerequisites_block_verified(flag):
    kw = dict(commands_configured=True, blockers=[], baseline=_ph(True), after=_ph(True), change_declared=True, change_applied=True)
    assert classify(**kw)[0] == "VERIFIED_CHANGE"
    assert classify(**kw, **{flag: False})[0] == "TESTS_PASS_CHANGE_UNVERIFIED"


def test_classify_baseline_failure_not_required():
    assert classify(commands_configured=True, blockers=[], baseline=_ph(True), after=_ph(True), change_declared=True, change_applied=True)[0] == "VERIFIED_CHANGE"


# ---------------- end-to-end runs (host interpreter in a copied dir) ----------------
def test_invalid_config_is_blocked_not_crash(tmp_path):
    r = verify({"target": str(tmp_path), "baseline": {"commands": [[]]}})
    assert r["status"] == "BLOCKED" and r["verified"] is False
    assert verify({"target": str(tmp_path / "missing"), "baseline": {"commands": [[PY, "-V"]]}})["status"] == "BLOCKED"
    assert verify({"target": str(tmp_path)})["status"] == "BLOCKED"
    assert verify(tmp_path / "does-not-exist.json")["status"] == "BLOCKED"


def test_baseline_only_pass_is_unverified_and_honest_about_isolation(tmp_path):
    write(tmp_path / "t.py", "print('ok')\n")
    r = verify(cfg(tmp_path, [[PY, "t.py"]]))
    assert r["status"] == "TESTS_PASS_CHANGE_UNVERIFIED" and r["verified"] is False
    assert r["environment"]["environment_isolated"] is False
    assert "NOT isolated" in r["environment"]["isolation_note"]
    assert r["baseline"]["commands"][0]["stdout"].strip() == "ok"
    assert r["environment"]["python_version"] and r["environment"]["os"]


def test_baseline_failure_recorded(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "raise SystemExit(1)"]]))
    assert r["status"] == "BASELINE_FAILED" and r["before"]["exit_code"] == 1 and r["after"] is None


def test_after_failure(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "pass"]], [[PY, "-c", "raise SystemExit(2)"]]))
    assert r["status"] == "VERIFICATION_FAILED" and r["after"]["exit_code"] == 2


def test_passing_tests_without_dependency_change_never_verified(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "pass"]], [[PY, "-c", "pass"]]))
    assert r["status"] == "TESTS_PASS_CHANGE_UNVERIFIED" and r["verified"] is False
    assert r["baseline"]["passed"] and r["after"]["passed"]  # both outputs preserved


def test_both_fail_preserves_outputs(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "print('b');raise SystemExit(1)"]], [[PY, "-c", "print('a');raise SystemExit(1)"]]))
    assert r["status"] == "VERIFICATION_FAILED"
    assert "b" in r["baseline"]["commands"][0]["stdout"] and "a" in r["after"]["commands"][0]["stdout"]


def test_timeout_and_missing_executable_surface_in_status(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "import time;time.sleep(20)"]], timeout_seconds=1))
    assert r["status"] == "BASELINE_FAILED" and r["baseline"]["commands"][0]["timed_out"]
    r = verify(cfg(tmp_path, [["no-such-binary-abc"]]))
    assert r["status"] == "BASELINE_FAILED" and r["baseline"]["commands"][0]["status"] == "not_started"


def test_target_is_copied_not_modified(tmp_path):
    write(tmp_path / "f.txt", "orig")
    verify(cfg(tmp_path, [[PY, "-c", "open('f.txt','w').write('changed');open('new.txt','w').write('x')"]]))
    assert (tmp_path / "f.txt").read_text() == "orig" and not (tmp_path / "new.txt").exists()


def test_working_directory_setting_and_escape_rejected(tmp_path):
    write(tmp_path / "sub" / "x.txt", "1")
    r = verify(cfg(tmp_path, [[PY, "-c", "import os;print(os.path.exists('x.txt'))"]], working_directory="sub"))
    assert r["baseline"]["commands"][0]["stdout"].strip() == "True"
    assert verify(cfg(tmp_path, [[PY, "-V"]], working_directory="../x"))["status"] == "BLOCKED"


def test_file_edit_change_is_evidenced_by_manifest_diff(tmp_path):
    write(tmp_path / "requirements.txt", "pkg==1.0\n")
    check = "import sys;sys.exit(0 if 'pkg==2.0' in open('requirements.txt').read() else 1)"
    r = verify(cfg(tmp_path, [[PY, "-c", check]], [[PY, "-c", check]],
                   change={"file_edits": [{"file": "requirements.txt", "old": "pkg==1.0", "new": "pkg==2.0"}]}))
    # env state captured (host pip list) but identical; manifest diff is the evidence
    assert r["baseline"]["passed"] is False and r["after"]["passed"] is True
    assert r["change"]["manifest_diff"] and "pkg==2.0" in r["change"]["manifest_diff"][0]["diff"]
    assert r["status"] == "VERIFIED_CHANGE" and r["verified"] is True
    assert (tmp_path / "requirements.txt").read_text() == "pkg==1.0\n"


def test_file_edit_that_does_not_match_blocks(tmp_path):
    write(tmp_path / "requirements.txt", "pkg==1.0\n")
    r = verify(cfg(tmp_path, [[PY, "-c", "pass"]], [[PY, "-c", "pass"]],
                   change={"file_edits": [{"file": "requirements.txt", "old": "nope", "new": "x"}]}))
    assert r["status"] == "BLOCKED" and r["verified"] is False


def test_pip_install_refused_without_isolation(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "pass"]], [[PY, "-c", "pass"]], change={"pip_install": ["demo-dep==2.0"]}))
    assert r["status"] == "BLOCKED" and "host environment" in " ".join(r["blockers"])


def test_declared_change_with_no_after_commands_is_not_verified(tmp_path):
    r = verify(cfg(tmp_path, [[PY, "-c", "pass"]], change={"pip_install": ["x"]}))
    assert r["status"] == "BLOCKED" or r["status"] == "TESTS_PASS_CHANGE_UNVERIFIED"
    assert r["verified"] is False


# ---------------- genuine isolated venv end-to-end (offline wheels) ----------------
def _venv_ok():
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as d:
        return subprocess.run([PY, "-m", "venv", d + "/v"], capture_output=True).returncode == 0


needs_venv = pytest.mark.skipif(not _venv_ok(), reason="venv creation unavailable in this environment")

PROJECT_TEST = "import demo_dep,sys\nsys.exit(0 if demo_dep.VERSION == '2.0' else 1)\n"


@needs_venv
def test_verified_change_end_to_end_in_isolated_venv(tmp_path, wheelhouse):
    proj = tmp_path / "proj"
    write(proj / "check.py", PROJECT_TEST)
    pipflags = ["--no-index", "--find-links", str(wheelhouse)]
    c = {"target": str(proj), "isolation": "venv", "timeout_seconds": 120,
         "baseline": {"setup": [["{python}", "-m", "pip", "install", *pipflags, "demo_dep==1.0"]],
                      "commands": [["{python}", "check.py"]]},
         "after": {"setup": [["{python}", "-m", "pip", "install", *pipflags, "demo_dep==1.0"]],
                   "commands": [["{python}", "check.py"]]},
         "change": {"pip_install": ["demo_dep==2.0"], "pip_args": pipflags}}
    r = verify(c)
    assert r["status"] == "VERIFIED_CHANGE", r["status_reasons"]
    assert r["baseline"]["passed"] is False and r["after"]["passed"] is True
    assert {"package": "demo-dep", "before": "1.0", "after": "2.0"} in r["change"]["environment_diff"]
    assert r["environment"]["environment_isolated"] is True and r["isolation"]["after_isolated"] is True
    assert r["environments"]["after"]["python_version"]
    # the host interpreter was not modified
    import importlib.util
    assert importlib.util.find_spec("demo_dep") is None


@needs_venv
def test_failed_change_application_blocks(tmp_path, wheelhouse):
    proj = tmp_path / "proj"
    write(proj / "check.py", "pass\n")
    pipflags = ["--no-index", "--find-links", str(wheelhouse)]
    r = verify({"target": str(proj), "isolation": "venv", "baseline": {"commands": [["{python}", "check.py"]]},
                "after": {"commands": [["{python}", "check.py"]]},
                "change": {"pip_install": ["demo_dep==9.9"], "pip_args": pipflags}})
    assert r["status"] == "BLOCKED" and r["verified"] is False and "dependency change failed" in " ".join(r["blockers"])


@needs_venv
def test_setup_failure_is_visible_not_success(tmp_path):
    proj = tmp_path / "proj"
    write(proj / "check.py", "pass\n")
    r = verify({"target": str(proj), "isolation": "venv",
                "baseline": {"setup": [["{python}", "-c", "raise SystemExit(5)"]], "commands": [["{python}", "check.py"]]}})
    assert r["status"] == "BLOCKED" and r["baseline"] is None


@needs_venv
def test_venv_and_pytest_style_commands_with_flags_run_inside_venv(tmp_path):
    proj = tmp_path / "proj"
    write(proj / "check.py", "import sys;print(sys.prefix != sys.base_prefix)\n")
    r = verify({"target": str(proj), "isolation": "venv", "baseline": {"commands": [["python", "check.py"], ["python", "-m", "pip", "check"]]}})
    assert r["baseline"]["commands"][0]["stdout"].strip() == "True"
    assert r["baseline"]["commands"][1]["command"][1:] == ["-m", "pip", "check"]


# ---------------- CLI ----------------
def test_cli_with_config_file_and_exit_codes(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    out = tmp_path / "v.json"
    write(tmp_path / "cfg.json", json.dumps(cfg(proj, [[PY, "-c", "pass"]])))
    rc = verify_main(["--config", str(tmp_path / "cfg.json"), "--output", str(out)])
    assert rc == 3 and json.loads(out.read_text())["status"] == "TESTS_PASS_CHANGE_UNVERIFIED"
    write(tmp_path / "bad.json", "{not json")
    assert verify_main(["--config", str(tmp_path / "bad.json"), "--output", str(out)]) == 2


def test_cli_json_encoded_commands_keep_flags(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    out = tmp_path / "v.json"
    rc = verify_main(["--target", str(proj), "--isolation", "none", "--baseline-cmd",
                      json.dumps([PY, "-c", "import sys;print(sys.argv[1:])", "-q", "--x"]), "--output", str(out)])
    data = json.loads(out.read_text())
    assert rc == 3 and "['-q', '--x']" in data["baseline"]["commands"][0]["stdout"]


def test_local_absolute_paths_are_scrubbed_from_report(tmp_path):
    proj = tmp_path / "myproject-dir"
    write(proj / "t.py", "import os,sys;print(os.getcwd());print(sys.executable)\n")
    r = verify(cfg(proj, [[PY, "t.py"]]))
    blob = json.dumps(r)
    assert str(tmp_path) not in blob and PY not in blob
    assert "<WORKDIR>" in r["baseline"]["commands"][0]["stdout"]


# --------------------------------------------------------------------------
# Optional progress notifications (added for the dashboard)
# --------------------------------------------------------------------------
def test_progress_events_are_scrubbed_and_do_not_affect_status(tmp_path):
    from patchproof.verify import verify as _verify
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("print('1 passed in 0.01s')\n", encoding="utf-8")
    cfg = {"target": str(proj), "isolation": "none", "baseline": {"commands": [["{python}", "ok.py"]]}}
    events = []
    rep = _verify(dict(cfg), progress=lambda e, p: events.append((e, p)))
    names = [e for e, _ in events]
    assert names[0] == "verification_started" and names[-1] == "verification_finished"
    assert "command_started" in names and "command_finished" in names
    assert str(tmp_path) not in json.dumps(events)
    assert events[-1][1]["status"] == rep["status"] == "TESTS_PASS_CHANGE_UNVERIFIED"

    def boom(e, p):
        raise RuntimeError("callback failure must be ignored")
    rep2 = _verify(dict(cfg), progress=boom)
    assert rep2["status"] == rep["status"]


def test_cli_progress_flag_emits_machine_readable_lines(tmp_path, capsys):
    from patchproof.verify import main as _main
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps({"target": str(proj), "isolation": "none",
                                "baseline": {"commands": [["{python}", "ok.py"]]}}), encoding="utf-8")
    code = _main(["--config", str(cfgp), "--output", str(tmp_path / "v.json"), "--progress"])
    err = capsys.readouterr().err
    lines = [json.loads(x.split(" ", 1)[1]) for x in err.splitlines() if x.startswith("PATCHPROOF_PROGRESS ")]
    assert lines and lines[-1]["event"] == "verification_finished"
    assert code == 3


def test_report_scrubs_home_temp_and_pytest_user_dirs(tmp_path):
    import tempfile
    from pathlib import Path as _P
    from patchproof.verify import verify as _verify
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "leak.py").write_text(
        "import tempfile, pathlib\nprint(tempfile.gettempdir()); print(pathlib.Path.home())\n"
        "print('/tmp/pytest-of-Jane Doe/pytest-1/x')\nraise SystemExit(1)\n", encoding="utf-8")
    rep = _verify({"target": str(proj), "isolation": "none", "baseline": {"commands": [["{python}", "leak.py"]]}})
    out = rep["baseline"]["commands"][0]["stdout"]
    assert tempfile.gettempdir() not in out and str(_P.home()) not in out
    assert "Jane Doe" not in out and "pytest-of-<user>" in out
