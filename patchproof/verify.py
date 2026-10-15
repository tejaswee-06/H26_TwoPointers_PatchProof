"""Verification runner (PatchProof Person 1).

Runs explicit, user-supplied commands (argument vectors, never shell strings)
in disposable copies of the target project and records what actually happened.

Trust boundary: the configured commands (e.g. a repository's test suite) may
execute arbitrary project code. They run only when you pass a verification
configuration. Nothing here modifies the target directory or the active
Python environment.

Status model (see PERSON1_JSON_CONTRACTS.md):
  NOT_RUN, BLOCKED, BASELINE_FAILED, TESTS_PASS_CHANGE_UNVERIFIED,
  VERIFIED_CHANGE, VERIFICATION_FAILED.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .common import SCHEMA_VERSION, EXCLUDED_DIR_NAMES, normalize_distribution_name, write_json

STATUSES = ("NOT_RUN", "BLOCKED", "BASELINE_FAILED", "TESTS_PASS_CHANGE_UNVERIFIED",
            "VERIFIED_CHANGE", "VERIFICATION_FAILED")
OUTPUT_LIMIT = 20000
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PY_TOKENS = {"python", "python3", "{python}"}
MAX_COPY_BYTES = 200 * 1024 * 1024


class ConfigError(ValueError):
    """Verification configuration is invalid."""


# --------------------------------------------------------------------------
# Command execution
# --------------------------------------------------------------------------
def _clip(text: str | bytes | None) -> tuple[str, bool]:
    if text is None:
        return "", False
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = ANSI_RE.sub("", text)
    if len(text) <= OUTPUT_LIMIT:
        return text, False
    half = OUTPUT_LIMIT // 2
    return text[:half] + "\n...[output truncated]...\n" + text[-half:], True


def extract_test_summary(stdout: str) -> str | None:
    """Pull a pytest-style summary line from real output; None if absent."""
    for line in reversed(stdout.strip().splitlines()):
        clean = line.strip().strip("=").strip()
        if re.search(r"\b\d+ (passed|failed|error|errors|skipped)\b", clean) or "no tests ran" in clean:
            return clean
    return None


def validate_argv(argv: Any) -> list[str]:
    if not isinstance(argv, list) or not argv:
        raise ConfigError("A command must be a non-empty JSON array of strings.")
    if not all(isinstance(a, str) for a in argv):
        raise ConfigError("Every command argument must be a string.")
    if not argv[0].strip():
        raise ConfigError("The executable (first element) must not be empty.")
    return list(argv)


def run_command(argv: list[str], cwd: Path, timeout_seconds: int = 120,
                env: dict[str, str] | None = None, display_cwd: str = ".") -> dict[str, Any]:
    """Run one argv without a shell; never raises for execution problems."""
    validate_argv(argv)
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    base = {"command": list(argv), "display": subprocess.list2cmdline(argv), "cwd": display_cwd,
            "started_at": started.isoformat(timespec="seconds"), "timeout_seconds": timeout_seconds,
            "shell": False}
    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, timeout=timeout_seconds,
                              shell=False, env=env)
        out, t1 = _clip(proc.stdout)
        err, t2 = _clip(proc.stderr)
        return {**base, "status": "passed" if proc.returncode == 0 else "failed",
                "exit_code": proc.returncode, "passed": proc.returncode == 0, "timed_out": False,
                "stdout": out, "stderr": err, "output_truncated": t1 or t2,
                "duration_seconds": round(time.monotonic() - t0, 3), "test_summary": extract_test_summary(out)}
    except subprocess.TimeoutExpired as exc:
        out, t1 = _clip(exc.stdout)
        err, t2 = _clip(exc.stderr)
        return {**base, "status": "timeout", "exit_code": None, "passed": False, "timed_out": True,
                "stdout": out, "stderr": err, "output_truncated": t1 or t2,
                "duration_seconds": round(time.monotonic() - t0, 3), "test_summary": None,
                "error": f"Timed out after {timeout_seconds} seconds"}
    except (OSError, ValueError) as exc:
        return {**base, "status": "not_started", "exit_code": None, "passed": False, "timed_out": False,
                "stdout": "", "stderr": "", "output_truncated": False,
                "duration_seconds": round(time.monotonic() - t0, 3), "test_summary": None,
                "error": f"Could not start command: {exc.__class__.__name__}: {exc}"}


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def load_config(source: str | os.PathLike | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        cfg = source
        base_dir = Path.cwd()
    else:
        p = Path(source)
        try:
            cfg = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ConfigError(f"Could not read verification config: {exc.__class__.__name__}: {exc}") from exc
        base_dir = p.resolve().parent
    if not isinstance(cfg, dict):
        raise ConfigError("Verification config must be a JSON object.")
    cfg = dict(cfg)
    cfg["_base_dir"] = str(base_dir)
    return cfg


def _phase_commands(cfg: dict[str, Any], key: str, required: bool) -> list[list[str]]:
    section = cfg.get(key)
    if section is None:
        if required:
            raise ConfigError(f"Missing '{key}' section.")
        return []
    if not isinstance(section, dict):
        raise ConfigError(f"'{key}' must be an object with a 'commands' array.")
    cmds = section.get("commands", [])
    if not isinstance(cmds, list):
        raise ConfigError(f"'{key}.commands' must be an array of command arrays.")
    if required and not cmds:
        raise ConfigError(f"'{key}.commands' must contain at least one command.")
    return [validate_argv(c) for c in cmds]


def _setup_commands(cfg: dict[str, Any], key: str) -> list[list[str]]:
    section = cfg.get(key) or {}
    if not isinstance(section, dict):
        return []
    return [validate_argv(c) for c in section.get("setup", [])]


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate; raises ConfigError. Does not touch the filesystem beyond the target check."""
    if "target" not in cfg or not isinstance(cfg["target"], str) or not cfg["target"].strip():
        raise ConfigError("'target' (path to the project directory) is required.")
    target = Path(cfg["target"])
    if not target.is_absolute():
        target = Path(cfg["_base_dir"]) / target
    target = target.resolve()
    if not target.is_dir():
        raise ConfigError(f"Target directory does not exist: {target.name}")
    timeout = cfg.get("timeout_seconds", 300)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ConfigError("'timeout_seconds' must be a positive number.")
    isolation = cfg.get("isolation", "venv")
    if isolation not in ("venv", "none"):
        raise ConfigError("'isolation' must be 'venv' or 'none'.")
    workdir_rel = cfg.get("working_directory", ".")
    if not isinstance(workdir_rel, str) or Path(workdir_rel).is_absolute() or ".." in Path(workdir_rel).parts:
        raise ConfigError("'working_directory' must be a relative path inside the target.")
    change = cfg.get("change")
    if change is not None:
        if not isinstance(change, dict):
            raise ConfigError("'change' must be an object.")
        pins = change.get("pip_install", [])
        edits = change.get("file_edits", [])
        if not isinstance(pins, list) or not all(isinstance(x, str) and x.strip() for x in pins):
            raise ConfigError("'change.pip_install' must be an array of requirement strings.")
        if not isinstance(edits, list):
            raise ConfigError("'change.file_edits' must be an array.")
        for e in edits:
            if not (isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("file", "old", "new"))):
                raise ConfigError("Each file edit needs string fields 'file', 'old', 'new'.")
            fp = Path(e["file"])
            if fp.is_absolute() or ".." in fp.parts:
                raise ConfigError("File edits must use relative paths inside the target.")
        if not pins and not edits:
            raise ConfigError("'change' must declare 'pip_install' and/or 'file_edits'.")
    return {
        "target": target, "timeout": timeout, "isolation": isolation, "workdir": workdir_rel,
        "baseline": _phase_commands(cfg, "baseline", required=True),
        "after": _phase_commands(cfg, "after", required=False),
        "baseline_setup": _setup_commands(cfg, "baseline"),
        "after_setup": _setup_commands(cfg, "after"),
        "change": change,
        "description": str(cfg.get("description", ""))[:500],
        "keep_workdir": bool(cfg.get("keep_workdir", False)),
    }


# --------------------------------------------------------------------------
# Environments
# --------------------------------------------------------------------------
def _copy_project(src: Path, dst: Path) -> None:
    total = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in EXCLUDED_DIR_NAMES and not d.endswith(".egg-info")
                             and not (Path(dirpath) / d / "pyvenv.cfg").exists())
        rel = Path(dirpath).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for fn in sorted(filenames):
            f = Path(dirpath) / fn
            if f.is_symlink():
                continue
            total += f.stat().st_size
            if total > MAX_COPY_BYTES:
                raise OSError("Project exceeds the 200 MB working-copy limit.")
            shutil.copy2(f, dst / rel / fn)


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _clean_env(venv: Path | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if venv is not None:
        bindir = str(_venv_python(venv).parent)
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(venv)
    return env


def _resolve_argv(argv: list[str], interpreter: str) -> list[str]:
    first = argv[0]
    if first in PY_TOKENS or first == sys.executable:
        return [interpreter] + argv[1:]
    return list(argv)


def _dependency_state(interpreter: str, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    res = run_command([interpreter, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                      cwd, 120, env)
    if not res["passed"]:
        return {"captured": False, "error": (res.get("error") or res["stderr"] or "pip list failed")[-300:], "packages": {}}
    try:
        pkgs = {normalize_distribution_name(p["name"]): p["version"] for p in json.loads(res["stdout"])}
    except (ValueError, KeyError, TypeError):
        return {"captured": False, "error": "pip list output could not be parsed", "packages": {}}
    return {"captured": True, "packages": dict(sorted(pkgs.items()))}


def _env_info(interpreter: str, cwd: Path, env: dict[str, str], isolated: bool, kind: str) -> dict[str, Any]:
    res = run_command([interpreter, "-c",
                       "import sys,platform;print(sys.version.split()[0]);print(platform.python_implementation())"],
                      cwd, 60, env)
    lines = res["stdout"].split() if res["passed"] else []
    return {"python_version": lines[0] if lines else None,
            "python_implementation": lines[1] if len(lines) > 1 else None,
            "os": platform.system(), "os_release": platform.release(), "machine": platform.machine(),
            "interpreter_kind": kind, "environment_isolated": isolated,
            "isolation_note": ("Fresh virtual environment created for this phase; the host environment was not modified."
                               if isolated else
                               "Commands ran with the HOST interpreter inside a copied working directory. "
                               "The Python environment is NOT isolated."),
            "interpreter_probe_ok": bool(lines)}


def _diff_states(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not (before.get("captured") and after.get("captured")):
        return None
    b, a = before["packages"], after["packages"]
    out = []
    for name in sorted(set(b) | set(a)):
        if b.get(name) != a.get(name):
            out.append({"package": name, "before": b.get(name), "after": a.get(name)})
    return out


def _phase_summary(results: list[dict[str, Any]], ran: bool) -> dict[str, Any] | None:
    if not ran:
        return None
    failing = next((r for r in results if not r["passed"]), None)
    pick = failing or (results[-1] if results else None)
    return {"passed": bool(results) and failing is None, "all_commands_attempted": True,
            "exit_code": pick["exit_code"] if pick else None, "command": pick["command"] if pick else None,
            "test_summary": next((r["test_summary"] for r in reversed(results) if r["test_summary"]), None),
            "commands": results}


# --------------------------------------------------------------------------
# Status decision (pure function; unit tested directly)
# --------------------------------------------------------------------------
def classify(*, commands_configured: bool, blockers: list[str], baseline: dict[str, Any] | None,
             after: dict[str, Any] | None, change_declared: bool, change_applied: bool,
             baseline_cmds: list[list[str]] | None = None, after_cmds: list[list[str]] | None = None,
             same_target: bool = True, baseline_env_recorded: bool = True,
             after_env_recorded: bool = True) -> tuple[str, list[str]]:
    """Return (status, reasons). VERIFIED_CHANGE requires ALL prerequisites."""
    if not commands_configured:
        return "NOT_RUN", ["No verification commands were configured."]
    if blockers:
        return "BLOCKED", list(blockers)
    if baseline is None:
        return "NOT_RUN", ["No baseline run was recorded."]
    b_pass = bool(baseline.get("passed"))
    if after is None:
        if not b_pass:
            return "BASELINE_FAILED", ["Baseline commands failed and no after-change run exists."]
        return "TESTS_PASS_CHANGE_UNVERIFIED", [
            "Baseline commands passed, but no after-change run exists, so no dependency change was verified."]
    if not after.get("passed"):
        return "VERIFICATION_FAILED", ["After-change commands failed."
                                       + (" Baseline had also failed." if not b_pass else "")]
    # after passed: every prerequisite for VERIFIED_CHANGE must hold
    missing = []
    if not change_declared:
        missing.append("No concrete dependency change was declared.")
    elif not change_applied:
        missing.append("The declared change is not evidenced by a manifest edit or a before/after dependency-state difference.")
    if not same_target:
        missing.append("Baseline and after runs are not associated with the same target project.")
    if not (baseline_env_recorded and after_env_recorded):
        missing.append("Environment details were not recorded for both runs.")
    if baseline_cmds is not None and after_cmds is not None:
        absent = [c for c in baseline_cmds if c not in after_cmds]
        if absent:
            missing.append("After-change run did not repeat every baseline command.")
    if missing:
        return "TESTS_PASS_CHANGE_UNVERIFIED", ["After-change commands passed, but: " + " ".join(missing)]
    return "VERIFIED_CHANGE", ["Baseline captured; declared dependency change applied with evidence; "
                              "every baseline command was repeated after the change and passed."]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def _blocked_report(reason: str, extra: dict[str, Any] | None = None, status: str = "BLOCKED") -> dict[str, Any]:
    r = _empty_report()
    r["status"] = status
    r["status_reasons"] = [reason]
    r["blockers"] = [reason] if status == "BLOCKED" else []
    r["test_summary"] = f"Not verified: {reason}"
    r.update(extra or {})
    return r


def _empty_report() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "report_type": "verification",
            "status": "NOT_RUN", "status_reasons": [], "verified": False, "blockers": [],
            "target": None, "description": "", "isolation": None, "environment": None, "environments": {},
            "change": None, "dependency_state": None, "baseline": None, "after": None,
            "before": None, "test_summary": "Not verified.",
            "trust_boundary": ("Configured commands may execute arbitrary project code. They ran only because a "
                               "verification configuration was supplied."),
            "limitations": [
                "Verification applies only to the exact commands, project copy and environment recorded here.",
                "A passing command is not a dependency change; a dependency change is not a verified fix; "
                "VERIFIED_CHANGE means the declared change was applied with evidence and the recorded commands passed afterwards.",
                "A passing verification does not establish that the change is the best long-term choice, "
                "and no security advisory data is consulted.",
                "Network access was not restricted during setup commands.",
            ]}


ProgressFn = Callable[[str, dict[str, Any]], None]


def verify(config: dict[str, Any] | str | os.PathLike, progress: ProgressFn | None = None) -> dict[str, Any]:
    """Run baseline (and optional after-change) verification. Never raises for run problems.

    ``progress`` (optional, added for the dashboard) receives ``(event, payload)``
    notifications as phases and commands start/finish. Payloads are scrubbed of
    local paths. It never influences the status decision; errors raised by the
    callback are ignored.
    """
    try:
        cfg = validate_config(load_config(config))
    except ConfigError as exc:
        _notify(progress, "config_invalid", {"error": str(exc)}, {})
        return _blocked_report(f"Invalid verification configuration: {exc}")
    report = _empty_report()
    report["target"] = {"name": cfg["target"].name, "path_policy": "directory name only"}
    report["description"] = cfg["description"]
    report["isolation"] = {"requested": cfg["isolation"]}
    tmp_root = Path(tempfile.mkdtemp(prefix="patchproof-verify-"))
    scrub_map = {str(tmp_root): "<WORKDIR>", str(cfg["target"]): "<TARGET>",
                 sys.executable: "<host-python>", sys.prefix: "<host-prefix>"}

    def emit(event: str, **payload: Any) -> None:
        _notify(progress, event, payload, scrub_map)

    def run_tracked(kind: str, phase: str, argv: list[str], cwd: Path, timeout: int | float,
                    env: dict[str, str]) -> dict[str, Any]:
        emit("command_started", phase=phase, kind=kind, display=subprocess.list2cmdline(argv))
        r = run_command(argv, cwd, timeout, env, cfg["workdir"])
        emit("command_finished", phase=phase, kind=kind, display=r["display"], status=r["status"],
             exit_code=r["exit_code"], duration_seconds=r["duration_seconds"], test_summary=r["test_summary"])
        return r

    emit("verification_started", target=cfg["target"].name, isolation=cfg["isolation"], workdir_name=tmp_root.name,
         phases=["baseline"] + (["after"] if cfg["after"] else []),
         baseline_commands=len(cfg["baseline"]), after_commands=len(cfg["after"]))
    try:
        phases: dict[str, dict[str, Any]] = {}
        blockers: list[str] = []
        phase_names = ["baseline"] + (["after"] if cfg["after"] else [])
        change = cfg["change"]
        for phase in phase_names:
            pdir = tmp_root / phase
            copy = pdir / "project"
            emit("phase_started", phase=phase)
            emit("step", phase=phase, step="copy", message="Creating disposable working copy")
            try:
                _copy_project(cfg["target"], copy)
            except OSError as exc:
                blockers.append(f"Could not create disposable working copy for {phase}: {exc}")
                break
            venv = None
            isolated = False
            kind = "host"
            interpreter = sys.executable
            if cfg["isolation"] == "venv":
                venv = pdir / "venv"
                emit("step", phase=phase, step="venv", message="Creating isolated virtual environment")
                cp = run_command([sys.executable, "-m", "venv", str(venv)], pdir, 300, _clean_env(None))
                if not cp["passed"] or not _venv_python(venv).exists():
                    blockers.append(f"Virtual environment creation failed for {phase}: "
                                    f"{(cp.get('error') or cp['stderr'] or 'unknown error')[-300:]}")
                    break
                interpreter, isolated, kind = str(_venv_python(venv)), True, "venv"
            env = _clean_env(venv)
            cwd = (copy / cfg["workdir"]).resolve()
            if not cwd.is_dir():
                blockers.append(f"working_directory '{cfg['workdir']}' does not exist in the copied target.")
                break
            info = _env_info(interpreter, cwd, env, isolated, kind)
            ph: dict[str, Any] = {"environment": info, "setup": [], "results": [], "edits": []}
            # Setup commands (e.g. install requirements) -- failures block the phase.
            setup = cfg["baseline_setup"] if phase == "baseline" else cfg["after_setup"]
            setup_failed = False
            for argv in setup:
                if not isolated and _looks_like_pip_install(argv):
                    blockers.append(f"{phase}: refusing pip install without isolation (would modify the host environment). "
                                    "Set isolation to 'venv'.")
                    setup_failed = True
                    break
                r = run_tracked("setup", phase, _resolve_argv(argv, interpreter), cwd, cfg["timeout"], env)
                ph["setup"].append(r)
                if not r["passed"]:
                    blockers.append(f"{phase} setup command failed: {r['display'][:120]} "
                                    f"({r.get('error') or 'exit code ' + str(r['exit_code'])})")
                    setup_failed = True
                    break
            if setup_failed:
                phases[phase] = ph
                break
            if phase == "baseline":
                ph["dependency_state_pre_change"] = _dependency_state(interpreter, cwd, env)
            if phase == "after" and change:
                # file edits in the after copy only
                for e in change.get("file_edits", []):
                    ph["edits"].append(_apply_edit(copy, e))
                if any(not e["applied"] for e in ph["edits"]):
                    blockers.append("after: a declared file edit could not be applied: "
                                    + "; ".join(e["error"] for e in ph["edits"] if not e["applied"]))
                    phases[phase] = ph
                    break
                pins = change.get("pip_install", [])
                if pins:
                    if not isolated:
                        blockers.append("after: change.pip_install requires isolation 'venv'; refusing to modify the host environment.")
                        phases[phase] = ph
                        break
                    flags = [str(x) for x in change.get("pip_args", []) if isinstance(x, str)]
                    r = run_tracked("change", phase, [interpreter, "-m", "pip", "install", *flags, *pins], cwd, cfg["timeout"], env)
                    ph["setup"].append(r)
                    if not r["passed"]:
                        blockers.append(f"after: applying the dependency change failed: {r['display'][:120]} "
                                        f"({(r.get('error') or r['stderr'])[-200:].strip()})")
                        phases[phase] = ph
                        break
            ph["dependency_state"] = _dependency_state(interpreter, cwd, env)
            commands = cfg["baseline"] if phase == "baseline" else cfg["after"]
            for argv in commands:
                ph["results"].append(run_tracked("command", phase, _resolve_argv(argv, interpreter), cwd, cfg["timeout"], env))
            ph["ran"] = True
            phases[phase] = ph
            emit("phase_finished", phase=phase, passed=all(r["passed"] for r in ph["results"]) and bool(ph["results"]))
        # ---- assemble report
        base_ph, after_ph = phases.get("baseline"), phases.get("after")
        if base_ph and base_ph.get("ran"):
            report["baseline"] = _phase_summary(base_ph["results"], True)
            report["before"] = report["baseline"]
            report["baseline"]["setup"] = base_ph["setup"]
        if after_ph and after_ph.get("ran"):
            report["after"] = _phase_summary(after_ph["results"], True)
            report["after"]["setup"] = after_ph["setup"]
            report["after"]["file_edits"] = after_ph["edits"]
        envs = {k: v["environment"] for k, v in phases.items() if "environment" in v}
        report["environments"] = envs
        report["environment"] = envs.get("baseline") or next(iter(envs.values()), None)
        report["isolation"] = {"requested": cfg["isolation"],
                               "baseline_isolated": bool(envs.get("baseline", {}).get("environment_isolated")),
                               "after_isolated": bool(envs.get("after", {}).get("environment_isolated")) if "after" in envs else None,
                               "working_copy_used": True,
                               "note": (envs.get("baseline") or {}).get("isolation_note")}
        applied, change_info = False, None
        pre = (base_ph or {}).get("dependency_state_pre_change") or (base_ph or {}).get("dependency_state")
        post = (after_ph or {}).get("dependency_state")
        env_diff = _diff_states(pre, post) if pre and post else None
        manifest_diff = []
        if after_ph:
            for e in after_ph["edits"]:
                if e["applied"]:
                    manifest_diff.append({"file": e["file"], "diff": e["diff"]})
        if change:
            named = [_pin_name(p) for p in change.get("pip_install", [])]
            env_ok = bool(env_diff) and (not named or any(d["package"] in named for d in env_diff))
            applied = bool(manifest_diff) or env_ok
            if change.get("pip_install") and not env_ok and not manifest_diff:
                applied = False
            change_info = {"declared": True, "pip_install": change.get("pip_install", []),
                           "file_edits": [{"file": e["file"], "old": e["old"], "new": e["new"]} for e in change.get("file_edits", [])],
                           "applied_with_evidence": applied, "environment_diff": env_diff, "manifest_diff": manifest_diff}
        else:
            change_info = {"declared": False, "applied_with_evidence": False, "environment_diff": env_diff,
                           "manifest_diff": []}
        report["change"] = change_info
        report["dependency_state"] = {
            "before": (base_ph or {}).get("dependency_state"),
            "after": (after_ph or {}).get("dependency_state"),
            "difference": env_diff,
        }
        status, reasons = classify(
            commands_configured=bool(cfg["baseline"]), blockers=blockers,
            baseline=report["baseline"], after=report["after"],
            change_declared=bool(change), change_applied=applied,
            baseline_cmds=cfg["baseline"], after_cmds=cfg["after"] or None,
            same_target=True,
            baseline_env_recorded=bool(envs.get("baseline", {}).get("interpreter_probe_ok")),
            after_env_recorded=bool(envs.get("after", {}).get("interpreter_probe_ok")))
        if status == "VERIFIED_CHANGE" and not (pre and pre.get("captured") and post and post.get("captured")) and not manifest_diff:
            status, reasons = "TESTS_PASS_CHANGE_UNVERIFIED", ["Dependency state could not be captured before and after."]
        report.update({"status": status, "status_reasons": reasons, "blockers": blockers,
                       "verified": status == "VERIFIED_CHANGE"})
        report["test_summary"] = _summary_text(report)
        report = _scrub(report, {str(tmp_root): "<WORKDIR>", str(cfg["target"]): "<TARGET>",
                                 sys.executable: "<host-python>", sys.prefix: "<host-prefix>",
                                 tempfile.gettempdir(): "<TMP>", str(Path.home()): "<HOME>"})
        report = _scrub_user_dirs(report)
        if cfg["keep_workdir"]:
            report["workdir_kept"] = True
        emit("verification_finished", status=status, verified=status == "VERIFIED_CHANGE", blockers=blockers)
    finally:
        if not cfg["keep_workdir"]:
            shutil.rmtree(tmp_root, ignore_errors=True)
    return report


def _notify(progress: ProgressFn | None, event: str, payload: dict[str, Any], scrub_map: dict[str, str]) -> None:
    """Deliver a scrubbed progress event; never lets a callback error affect verification."""
    if progress is None:
        return
    try:
        progress(event, _scrub(payload, scrub_map) if scrub_map else payload)
    except Exception:  # noqa: BLE001 - progress reporting is best effort by design
        pass


def _path_variants(path: str) -> set[str]:
    """Spellings a path may take in captured output (resolved, long/short form, slash style)."""
    out = {path}
    try:
        out.add(os.path.realpath(path))
        out.add(str(Path(path).resolve()))
    except (OSError, ValueError):
        pass
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(32768)
            for fn in (ctypes.windll.kernel32.GetLongPathNameW, ctypes.windll.kernel32.GetShortPathNameW):
                if fn(path, buf, 32768):
                    out.add(buf.value)
        except Exception:  # best effort only
            pass
    out |= {v.replace("\\", "/") for v in out} | {v.replace("/", "\\") for v in out}
    return {v for v in out if v and len(v) > 3}


def _scrub(obj: Any, replacements: dict[str, str]) -> Any:
    """Replace local absolute paths in captured text so artifacts do not leak them."""
    pairs: dict[str, str] = {}
    for old, new in replacements.items():
        for v in _path_variants(old) if old else ():
            pairs[v] = new
    flags = re.IGNORECASE if os.name == "nt" else 0
    pattern = re.compile("|".join(re.escape(k) for k in sorted(pairs, key=len, reverse=True)), flags) if pairs else None
    lookup = {k.lower() if os.name == "nt" else k: v for k, v in pairs.items()}

    def walk(o: Any) -> Any:
        if isinstance(o, str):
            if pattern is None:
                return o
            return pattern.sub(lambda m: lookup[m.group(0).lower() if os.name == "nt" else m.group(0)], o)
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o
    return walk(obj)


_PYTEST_USER = re.compile(r"pytest-of-[^/\\'\"\s]+(?: [^/\\'\"\s]+)*")


def _scrub_user_dirs(obj: Any) -> Any:
    """pytest's tmp_path embeds the OS user name (pytest-of-<name>); remove it."""
    if isinstance(obj, str):
        return _PYTEST_USER.sub("pytest-of-<user>", obj)
    if isinstance(obj, list):
        return [_scrub_user_dirs(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_user_dirs(v) for k, v in obj.items()}
    return obj


def _pin_name(spec: str) -> str:
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return normalize_distribution_name(m.group(1)) if m else spec


def _looks_like_pip_install(argv: list[str]) -> bool:
    low = [a.lower() for a in argv]
    return "pip" in low and "install" in low


def _apply_edit(copy: Path, edit: dict[str, str]) -> dict[str, Any]:
    target = (copy / edit["file"]).resolve()
    rec = {"file": edit["file"], "old": edit["old"], "new": edit["new"], "applied": False, "error": "", "diff": ""}
    try:
        target.relative_to(copy.resolve())
        text = target.read_text(encoding="utf-8")
    except (ValueError, OSError, UnicodeError) as exc:
        rec["error"] = f"{edit['file']}: cannot read ({exc.__class__.__name__})"
        return rec
    if text.count(edit["old"]) != 1:
        rec["error"] = f"{edit['file']}: expected exactly one occurrence of the text to replace, found {text.count(edit['old'])}"
        return rec
    new_text = text.replace(edit["old"], edit["new"])
    target.write_text(new_text, encoding="utf-8")
    rec["applied"] = True
    rec["diff"] = "".join(difflib.unified_diff(text.splitlines(True), new_text.splitlines(True),
                                               f"a/{edit['file']}", f"b/{edit['file']}"))[:4000]
    return rec


def _summary_text(r: dict[str, Any]) -> str:
    parts = [f"Status {r['status']}."]
    for key in ("baseline", "after"):
        ph = r.get(key)
        if ph:
            parts.append(f"{key}: {'passed' if ph['passed'] else 'failed'}"
                         + (f" ({ph['test_summary']})" if ph.get("test_summary") else ""))
    parts.append(" ".join(r["status_reasons"]))
    return " ".join(parts)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
EXIT_CODES = {"VERIFIED_CHANGE": 0, "VERIFICATION_FAILED": 1, "BASELINE_FAILED": 1, "BLOCKED": 2,
              "NOT_RUN": 2, "TESTS_PASS_CHANGE_UNVERIFIED": 3}


def _json_cmd(text: str) -> list[str]:
    try:
        return validate_argv(json.loads(text))
    except (ValueError, ConfigError) as exc:
        raise argparse.ArgumentTypeError(f"Command must be a JSON array of strings, e.g. '[\"python\",\"-m\",\"pytest\",\"-q\"]' ({exc})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run baseline/after-change verification in disposable copies. Commands are JSON argument arrays; "
                    "no shell is used. Repository commands may execute arbitrary project code.")
    ap.add_argument("--config", help="Verification config JSON file (recommended; see PERSON1_RUNBOOK.md)")
    ap.add_argument("--target", help="Project directory (when not using --config)")
    ap.add_argument("--baseline-cmd", action="append", type=_json_cmd, default=[], metavar="JSON_ARRAY",
                    help="Baseline command as a JSON array; repeatable")
    ap.add_argument("--after-cmd", action="append", type=_json_cmd, default=[], metavar="JSON_ARRAY")
    ap.add_argument("--pip-install", action="append", default=[], metavar="REQ",
                    help="Requirement to install in the AFTER environment as the proposed change; repeatable")
    ap.add_argument("--isolation", choices=["venv", "none"], default="venv")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--output", default="verification.json")
    ap.add_argument("--progress", action="store_true",
                    help="Emit machine-readable progress lines ('PATCHPROOF_PROGRESS <json>') on stderr (used by the dashboard)")
    args = ap.parse_args(argv)
    if args.config:
        source: Any = args.config
    else:
        if not args.target or not args.baseline_cmd:
            ap.error("Provide --config, or --target together with at least one --baseline-cmd.")
        source = {"target": args.target, "isolation": args.isolation, "timeout_seconds": args.timeout,
                  "baseline": {"commands": args.baseline_cmd}}
        if args.after_cmd:
            source["after"] = {"commands": args.after_cmd}
        if args.pip_install:
            source["change"] = {"pip_install": args.pip_install}
    def _stderr_progress(event: str, payload: dict[str, Any]) -> None:
        sys.stderr.write("PATCHPROOF_PROGRESS " + json.dumps({"event": event, **payload}) + "\n")
        sys.stderr.flush()

    if args.progress and hasattr(signal, "SIGTERM"):
        # Let a dashboard cancellation (SIGTERM) unwind normally so the disposable
        # working directories are removed by verify()'s cleanup.
        def _terminate(signum: int, frame: Any) -> None:
            raise SystemExit(130)
        try:
            signal.signal(signal.SIGTERM, _terminate)
        except (ValueError, OSError):
            pass
    report = verify(source, progress=_stderr_progress if args.progress else None)
    write_json(Path(args.output), report)
    print(json.dumps({"status": report["status"], "verified": report["verified"],
                      "reasons": report["status_reasons"], "output": args.output}, indent=2))
    return EXIT_CODES.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
