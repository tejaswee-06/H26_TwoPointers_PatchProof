"""Root-cause diagnostics (PatchProof Person 1 — evidence correlation).

Correlates the artifacts the engine already produced -- manifest declarations
(scan), source imports (usage) and captured command output (verification) --
into *candidate* causes. Nothing is executed and no network or model is used.

Honesty rules
-------------
* Every candidate is a ``hypothesis``. ``observed`` items quote artifacts
  verbatim (with their source); ``inferred`` text is clearly separated.
* ``support`` is ``supported_by_verification`` only when the verification
  artifact records ``VERIFIED_CHANGE`` and its applied change touched a package
  named by the candidate. Otherwise it is ``not_tested`` / ``not_resolved``.
* Package names are never hard-coded; everything is parsed from the inputs.
* ``discriminating_checks`` are suggestions with status ``NOT_RUN``.
"""
from __future__ import annotations

import argparse
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

from .common import SCHEMA_VERSION, load_json_artifact, normalize_distribution_name, stable_id, write_json

try:  # packaging is a declared dependency of the engine
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version
except Exception:  # pragma: no cover - defensive
    SpecifierSet = None  # type: ignore

_RE_CANNOT_IMPORT = re.compile(
    r"ImportError: cannot import name '(?P<name>[\w.]+)' from '(?P<module>[\w.]+)'")
_RE_NO_MODULE = re.compile(r"ModuleNotFoundError: No module named '(?P<module>[\w.]+)'")
_RE_GENERIC_ERR = re.compile(r"^(?:E\s+)?(?P<etype>[A-Za-z_][\w.]*(?:Error|Exception)): (?P<msg>.+)$")
_RE_PYTEST_FAILED = re.compile(r"^(?P<kind>FAILED|ERROR) (?P<test>\S+?)(?: - (?P<why>.*))?$")
_RE_PYTEST_FRAME = re.compile(r"^(?P<file>(?:[A-Za-z]:)?[^\s:][^:]*?\.py):(?P<line>\d+): (?:in \S+|\w+(?:Error|Exception))")
_RE_PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+\.py)", line (?P<line>\d+)')
_RE_PIP_FROM = re.compile(r"^Collecting (?P<req>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<spec>[^ (]*) \(from (?P<parent>[^)]+)\)")
_SITE = "site-packages"


def _usable(a: Any) -> bool:
    return isinstance(a, dict) and not (a.get("status") in ("missing", "unreadable") and "schema_version" not in a)


def _norm_path(raw: str) -> str:
    return raw.replace("\\", "/")


def classify_frame(raw_file: str) -> dict[str, Any]:
    """Classify a traceback path as installed-package or project source; scrub prefixes."""
    p = _norm_path(raw_file)
    low = p.lower()
    if f"/{_SITE}/" in low or low.startswith(f"{_SITE}/"):
        idx = low.rfind(_SITE + "/")
        rest = p[idx + len(_SITE) + 1:]
        top = rest.split("/", 1)[0]
        dist_root = top[:-3] if top.endswith(".py") else top
        return {"origin": "installed", "file": f"site-packages/{rest}", "import_root": dist_root}
    # verification copies the project to <WORKDIR>/<phase>/project/...
    m = re.search(r"/project/(.+)$", p) if p.startswith("<WORKDIR>") or "/project/" in p else None
    if m:
        p = m.group(1)
    if p.startswith("<TARGET>/"):
        p = p[len("<TARGET>/"):]
    if re.match(r"^[A-Za-z]:/", p) or p.startswith("/"):
        return {"origin": "unknown", "file": PurePosixPath(p).name, "import_root": None}
    return {"origin": "project", "file": p.lstrip("./"), "import_root": None}


def parse_failure_output(text: str) -> dict[str, Any]:
    """Extract structured facts from one failed command's output (pure)."""
    lines = text.splitlines()
    frames: list[dict[str, Any]] = []
    seen = set()
    for ln in lines:
        m = _RE_PYTEST_FRAME.match(ln.strip()) or _RE_PY_FRAME.match(ln)
        if m:
            key = (m.group("file"), m.group("line"))
            if key in seen:
                continue
            seen.add(key)
            info = classify_frame(m.group("file"))
            info["line"] = int(m.group("line"))
            frames.append(info)
    errors: list[dict[str, Any]] = []
    for ln in lines:
        s = ln.strip()
        m = _RE_CANNOT_IMPORT.search(s)
        if m:
            errors.append({"kind": "cannot_import_name", "name": m.group("name"), "module": m.group("module"),
                           "text": _scrub_line(s)})
            continue
        m = _RE_NO_MODULE.search(s)
        if m:
            errors.append({"kind": "module_not_found", "module": m.group("module"), "text": _scrub_line(s)})
            continue
        m = _RE_GENERIC_ERR.match(s)
        if m and not s.startswith(("FAILED", "ERROR ")):
            errors.append({"kind": "error", "type": m.group("etype"), "text": _scrub_line(s)})
    # de-duplicate by text, keep order
    uniq, keys = [], set()
    for e in errors:
        if e["text"] not in keys:
            keys.add(e["text"])
            uniq.append(e)
    failing = []
    for ln in lines:
        m = _RE_PYTEST_FAILED.match(ln.strip())
        if m:
            failing.append({"test": m.group("test"), "kind": m.group("kind"), "reason": (m.group("why") or "").strip()})
    return {"frames": frames, "errors": uniq, "failing_tests": failing}


def _scrub_line(s: str) -> str:
    s = re.sub(r"\((?:<WORKDIR>|<TARGET>|[A-Za-z]:[\\/]|/)[^)]*\)", "(<path>)", s)
    return s[:400]


def parse_pip_requirement_origins(text: str) -> list[dict[str, str]]:
    """'Collecting X>=1 (from Y==2->-r requirements.txt (line 4))' -> transitive requirement evidence."""
    out = []
    for ln in text.splitlines():
        m = _RE_PIP_FROM.match(ln.strip())
        if m:
            out.append({"requirement": m.group("req") + m.group("spec"), "package": normalize_distribution_name(m.group("req")),
                        "required_by": m.group("parent").split("->")[0].strip(), "line": ln.strip()[:300]})
    return out


# ---------------------------------------------------------------------------
def _decls_by_pkg(scan: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if _usable(scan):
        for d in scan.get("declarations", []) or []:
            if isinstance(d, dict) and d.get("name"):
                key = d.get("normalized_name") or normalize_distribution_name(d["name"])
                out.setdefault(key, []).append(d)
    return out


def _root_to_pkg(usage: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if _usable(usage):
        for p in usage.get("packages", []) or []:
            for r in p.get("candidate_import_roots", []) or []:
                out.setdefault(r.lower(), p.get("package"))
    return out


def _pkg_for_root(root: str, roots: dict[str, str]) -> str:
    top = root.split(".", 1)[0]
    return roots.get(top.lower()) or normalize_distribution_name(top)


def _installed(ver: Any, phase: str) -> dict[str, str]:
    st = ((ver or {}).get("dependency_state") or {}).get("before" if phase == "baseline" else "after") or {}
    return st.get("packages") or {} if st.get("captured") else {}


def _spec_allows(spec: str, version: str) -> bool | None:
    if SpecifierSet is None:
        return None
    try:
        return Version(version) in SpecifierSet(spec or "")
    except (InvalidSpecifier, InvalidVersion, TypeError):
        return None


def _usage_import_sites(usage: Any, pkg: str) -> list[dict[str, Any]]:
    if not _usable(usage):
        return []
    for p in usage.get("packages", []) or []:
        if normalize_distribution_name(p.get("package") or "") == pkg:
            return list(p.get("imports_found") or [])
    return []


def _ids_for(scan: Any, usage: Any, pkgs: Iterable[str]) -> list[str]:
    pk = set(pkgs)
    ids = []
    if _usable(scan):
        ids += [f["id"] for f in scan.get("findings", []) or [] if normalize_distribution_name(f.get("package") or "") in pk and f.get("id")]
    if _usable(usage):
        ids += [f["id"] for f in usage.get("review_leads", []) or [] if normalize_distribution_name(f.get("package") or "") in pk and f.get("id")]
    return sorted(set(ids))


def _phase_failures(ver: Any) -> list[dict[str, Any]]:
    out = []
    if not _usable(ver):
        return out
    for phase in ("baseline", "after"):
        ph = ver.get(phase) or (ver.get("before") if phase == "baseline" else None)
        if not isinstance(ph, dict):
            continue
        passed_cmds = [c for c in ph.get("commands", []) or [] if isinstance(c, dict) and c.get("passed")]
        for idx, c in enumerate(ph.get("commands", []) or []):
            if not isinstance(c, dict) or c.get("passed"):
                continue
            text = f"{c.get('stdout') or ''}\n{c.get('stderr') or ''}"
            parsed = parse_failure_output(text)
            out.append({
                "id": stable_id("E", phase, idx, c.get("display") or c.get("command")),
                "phase": phase, "command_index": idx, "command": c.get("display") or " ".join(map(str, c.get("command") or [])),
                "exit_code": c.get("exit_code"), "status": c.get("status"), "test_summary": c.get("test_summary"),
                "timed_out": bool(c.get("timed_out")), **parsed,
                "metadata_check_passed_same_phase": any(_is_pip_check(p) for p in passed_cmds),
            })
    return out


def _is_pip_check(cmd: dict[str, Any]) -> bool:
    argv = [str(a).lower() for a in cmd.get("command") or []]
    return "pip" in argv and "check" in argv


def _change_info(ver: Any) -> tuple[str | None, set[str], list[dict[str, Any]], dict[str, Any] | None]:
    if not _usable(ver):
        return None, set(), [], None
    ch = ver.get("change") or {}
    diff = ch.get("environment_diff") or []
    touched = {normalize_distribution_name(d.get("package", "")) for d in diff if isinstance(d, dict)}
    for p in ch.get("pip_install") or []:
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(p))
        if m:
            touched.add(normalize_distribution_name(m.group(1)))
    return ver.get("status"), touched, diff, ver.get("after")


def _support(pkgs: set[str], ver: Any) -> tuple[str, list[dict[str, Any]]]:
    status, touched, diff, after = _change_info(ver)
    if status is None:
        return "not_tested", []
    obs: list[dict[str, Any]] = []
    relevant = sorted(pkgs & touched)
    if not relevant or not isinstance(after, dict):
        return "not_tested", obs
    for d in diff:
        if normalize_distribution_name(d.get("package", "")) in pkgs:
            obs.append({"kind": "environment_diff", "source": "verification",
                        "text": f"{d.get('package')}: {d.get('before')} -> {d.get('after')} (declared change, after-phase environment)"})
    obs.append({"kind": "after_run", "source": "verification",
                "text": f"After-change run {'passed' if after.get('passed') else 'failed'}"
                        + (f": {after.get('test_summary')}" if after.get("test_summary") else "")
                        + f" (verification status {status})"})
    if status == "VERIFIED_CHANGE":
        return "supported_by_verification", obs
    if after.get("passed") is False:
        return "not_resolved_by_change", obs
    return "change_tested_not_verified", obs


# ---------------------------------------------------------------------------
def diagnose(scan: Any, usage: Any, verification: Any) -> dict[str, Any]:
    decls = _decls_by_pkg(scan)
    roots = _root_to_pkg(usage)
    failures = _phase_failures(verification)
    installed_before = _installed(verification, "baseline") if _usable(verification) else {}
    pip_origins: list[dict[str, str]] = []
    if _usable(verification):
        for ph in ("baseline", "after"):
            for s in ((verification.get(ph) or {}).get("setup") or []):
                if isinstance(s, dict):
                    pip_origins += parse_pip_requirement_origins(s.get("stdout") or "")
    candidates: list[dict[str, Any]] = []
    explained_failures: set[str] = set()

    # 1) runtime import incompatibilities / missing modules from *baseline* failures
    for f in [x for x in failures if x["phase"] == "baseline"]:
        installed_frames = [fr for fr in f["frames"] if fr["origin"] == "installed"]
        project_frames = [fr for fr in f["frames"] if fr["origin"] == "project"]
        for err in f["errors"]:
            if err["kind"] not in ("cannot_import_name", "module_not_found"):
                continue
            provider = _pkg_for_root(err["module"], roots)
            consumer_frame = installed_frames[-1] if installed_frames else None
            consumer = _pkg_for_root(consumer_frame["import_root"], roots) if consumer_frame and consumer_frame.get("import_root") else None
            if consumer == provider:
                consumer = None
            pkgs = {p for p in (provider, consumer) if p}
            observed: list[dict[str, Any]] = [
                {"kind": "command_failure", "source": "verification",
                 "text": f"[{f['phase']}] `{f['command']}` exited {f['exit_code']} ({f['status']})"
                         + (f" — {f['test_summary']}" if f.get("test_summary") else "")},
                {"kind": "error_line", "source": "verification", "text": err["text"]},
            ]
            for t in f["failing_tests"][:5]:
                observed.append({"kind": "failing_test", "source": "verification", "text": t["test"] + (f" — {t['reason']}" if t["reason"] else "")})
            for fr in (project_frames[-3:] + installed_frames[-3:]):
                observed.append({"kind": "traceback_frame", "source": "verification", "file": fr["file"], "line": fr["line"],
                                 "text": f"{fr['file']}:{fr['line']} ({fr['origin']})"})
            for p in sorted(pkgs):
                for d in decls.get(p, []):
                    observed.append({"kind": "declaration", "source": "scan", "file": d.get("file"), "line": d.get("line"),
                                     "text": d.get("excerpt") or f"{d.get('name')}{d.get('specifier') or ''}"})
                if p not in decls:
                    origin = next((o for o in pip_origins if o["package"] == p), None)
                    observed.append({"kind": "not_declared", "source": "scan",
                                     "text": f"{p} is not declared in any scanned manifest"
                                             + (f"; pip resolved it as a transitive requirement: \"{origin['line']}\"" if origin else ".")})
                if p in installed_before:
                    observed.append({"kind": "installed_version", "source": "verification",
                                     "text": f"{p}=={installed_before[p]} installed in the baseline environment"})
            for fr in project_frames:
                for p in sorted(pkgs):
                    for site in _usage_import_sites(usage, p):
                        if site.get("file") == fr["file"]:
                            observed.append({"kind": "import_site", "source": "usage", "file": site["file"], "line": site.get("line"),
                                             "text": site.get("statement") or site.get("module")})
            if f["metadata_check_passed_same_phase"]:
                observed.append({"kind": "metadata_check", "source": "verification",
                                 "text": "`pip check` passed in the same environment (declared metadata reported no conflict)."})
            pv = f" {installed_before[provider]}" if provider in installed_before else ""
            cv = f" {installed_before[consumer]}" if consumer and consumer in installed_before else ""
            if err["kind"] == "cannot_import_name":
                title = (f"{consumer}{cv} imports `{err['name']}` from {provider}, which the installed {provider}{pv} does not provide"
                         if consumer else f"`{err['name']}` cannot be imported from installed {provider}{pv}")
                inferred = (f"The installed {provider}{pv} appears not to export `{err['name']}`, which "
                            + (f"{consumer}{cv} expects. " if consumer else "the failing code expects. ")
                            + "A version incompatibility between these packages is the candidate cause.")
                ctype = "runtime_import_incompatibility"
            else:
                title = f"Module `{err['module']}` could not be imported"
                inferred = (f"The module `{err['module']}` (distribution guess: {provider}) was not importable in the recorded environment. "
                            "It may be undeclared, not installed by the setup commands, or provided under a different distribution name.")
                ctype = "missing_module"
            if f["metadata_check_passed_same_phase"]:
                inferred += " Because `pip check` passed, the declared requirement metadata does not exclude this combination."
            support, sup_obs = _support(pkgs, verification)
            observed += sup_obs
            unc = ["Derived by pattern-matching captured output; frames outside the captured (possibly truncated) output are not seen."]
            if support == "supported_by_verification":
                unc.append("Verification shows the recorded commands pass after the declared change; it does not show that this change "
                           "is the best long-term fix (for example, upgrading the importing package instead).")
            else:
                unc.append("No verified change isolates this cause yet.")
            if provider not in decls:
                unc.append(f"{provider} is resolved transitively, so its version can change without any manifest edit in this repository.")
            checks = []
            if err["kind"] == "cannot_import_name":
                checks.append({"description": f"Confirm whether the installed {provider} exports `{err['name']}`",
                               "command": ["{python}", "-c", f"import {err['module']} as m; print(hasattr(m, '{err['name'].split('.')[-1]}'))"],
                               "status": "NOT_RUN"})
            if pkgs:
                checks.append({"description": "Record installed versions and declared requirements of the implicated packages",
                               "command": ["{python}", "-m", "pip", "show", *sorted(pkgs)], "status": "NOT_RUN"})
            candidates.append({
                "id": stable_id("D", ctype, *sorted(pkgs), err.get("name", ""), err["module"]),
                "type": ctype, "title": title, "status": "hypothesis", "support": support,
                "packages": sorted(pkgs), "observed": observed, "inferred": inferred, "uncertainties": unc,
                "related_ids": _ids_for(scan, usage, pkgs), "failure_ids": [f["id"]], "discriminating_checks": checks,
            })
            explained_failures.add(f["id"])

    # 2) manifest inconsistencies (scanner findings) correlated with installs/failures
    if _usable(scan):
        for fd in scan.get("findings", []) or []:
            if not isinstance(fd, dict) or fd.get("type") != "manifest_inconsistency":
                continue
            pkg = normalize_distribution_name(fd.get("package") or "")
            observed = [{"kind": "declaration", "source": "scan", "file": e.get("file"), "line": e.get("line"),
                         "text": e.get("excerpt") or e.get("specifier")} for e in fd.get("evidence", []) or []]
            inferred = fd.get("inferred") or ""
            if pkg in installed_before:
                v = installed_before[pkg]
                sats = []
                for e in fd.get("evidence", []) or []:
                    ok = _spec_allows(e.get("specifier") or "", v)
                    if ok is not None:
                        sats.append(f"{e.get('file')}:{e.get('line')} `{e.get('specifier') or '(any)'}` {'allows' if ok else 'does NOT allow'} {v}")
                observed.append({"kind": "installed_version", "source": "verification",
                                 "text": f"{pkg}=={v} installed in the baseline environment"})
                if sats:
                    inferred += (" " if inferred else "") + "Installed version check: " + "; ".join(sats) + "."
            roots_for = {r for r, p in roots.items() if normalize_distribution_name(p or "") == pkg} | {pkg.replace("-", "_")}
            mentions = [f for f in failures if any(re.search(rf"\b{re.escape(r)}\b", " ".join(e["text"] for e in f["errors"])) for r in roots_for)]
            unc = ["Which declaration is intended is not determined from the files."]
            if failures and not mentions:
                unc.append(f"No captured failure output references {pkg}; there is no runtime evidence of impact yet.")
            elif not failures:
                unc.append("No failing command output is available to correlate.")
            for site in _usage_import_sites(usage, pkg)[:4]:
                observed.append({"kind": "import_site", "source": "usage", "file": site.get("file"), "line": site.get("line"),
                                 "text": site.get("statement") or site.get("module")})
            candidates.append({
                "id": stable_id("D", "manifest_inconsistency", pkg, fd.get("id")),
                "type": "manifest_inconsistency",
                "title": f"Disagreeing declarations for {fd.get('package')}: the installed version depends on which manifest is used",
                "status": "hypothesis", "support": "runtime_impact_observed" if mentions else "not_tested",
                "packages": [pkg], "observed": observed, "inferred": inferred, "uncertainties": unc,
                "related_ids": [fd["id"]] if fd.get("id") else [], "failure_ids": [m["id"] for m in mentions],
                "discriminating_checks": [{"description": f"Install from each manifest separately and run the tests to see whether {fd.get('package')} behaviour differs",
                                           "command": None, "status": "NOT_RUN"}],
            })

    # 3) remaining baseline failures that no pattern explained
    for f in failures:
        if f["phase"] != "baseline" or f["id"] in explained_failures:
            continue
        last = f["errors"][-1]["text"] if f["errors"] else None
        observed = [{"kind": "command_failure", "source": "verification",
                     "text": f"[{f['phase']}] `{f['command']}` exited {f['exit_code']} ({f['status']})"
                             + (f" — {f['test_summary']}" if f.get("test_summary") else "")}]
        if last:
            observed.append({"kind": "error_line", "source": "verification", "text": last})
        for t in f["failing_tests"][:5]:
            observed.append({"kind": "failing_test", "source": "verification", "text": t["test"]})
        candidates.append({
            "id": stable_id("D", "runtime_failure_unclassified", f["command"]),
            "type": "runtime_failure_unclassified", "title": "Baseline command failed for a reason PatchProof could not classify",
            "status": "hypothesis", "support": "not_tested", "packages": [], "observed": observed,
            "inferred": "No dependency-related cause was recognised in the captured output. Inspect the command output directly.",
            "uncertainties": ["Unclassified failures may be unrelated to dependencies."], "related_ids": [],
            "failure_ids": [f["id"]], "discriminating_checks": [],
        })

    order = {"runtime_import_incompatibility": 0, "missing_module": 1, "manifest_inconsistency": 2, "runtime_failure_unclassified": 3}
    candidates.sort(key=lambda c: (order.get(c["type"], 9), c["id"]))
    ver_ok = _usable(verification)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "diagnosis",
        "status": "completed" if (ver_ok or _usable(scan)) else "insufficient_evidence",
        "inputs": {"scan": _usable(scan), "usage": _usable(usage), "verification": ver_ok},
        "summary": {
            "candidate_count": len(candidates),
            "runtime_failures_observed": len([f for f in failures if f["phase"] == "baseline"]),
            "after_failures_observed": len([f for f in failures if f["phase"] == "after"]),
            "supported_by_verification": len([c for c in candidates if c["support"] == "supported_by_verification"]),
        },
        "observed_failures": failures,
        "candidates": candidates,
        "limitations": [
            "Candidates are hypotheses derived from existing artifacts; no command was run to produce them.",
            "Runtime causes can only be derived when a verification artifact with failing command output is available."
            + ("" if ver_ok else " None was supplied, so only manifest-level candidates are listed."),
            "'supported_by_verification' means a recorded, verified change touching the package made the recorded commands pass; "
            "it does not prove there is no other cause.",
            "Discriminating checks are suggestions (NOT_RUN) until a human runs them.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Derive evidence-backed candidate causes from PatchProof artifacts (no execution).")
    ap.add_argument("--scan")
    ap.add_argument("--usage")
    ap.add_argument("--verification")
    ap.add_argument("--output", default="diagnosis.json")
    a = ap.parse_args(argv)
    from pathlib import Path
    d = diagnose(load_json_artifact(a.scan), load_json_artifact(a.usage), load_json_artifact(a.verification))
    write_json(Path(a.output), d)
    print(f"Wrote {a.output}: {d['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
