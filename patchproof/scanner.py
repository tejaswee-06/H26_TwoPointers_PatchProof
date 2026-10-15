"""Evidence-backed dependency manifest scanner (PatchProof Person 1).

Supported: requirements*.txt (with -r includes, continuations, markers,
extras, direct URLs, editable), pyproject.toml (PEP 621 dependencies and
optional-dependencies, PEP 735 dependency-groups, build-system.requires),
setup.cfg (install_requires, extras_require) and setup.py (STATIC analysis
of literal install_requires/extras_require only -- never executed).

Findings are observations about declarations. They are not proof of runtime
failure and make no claim about security advisories.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import fnmatch
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .common import (EXCLUDED_DIR_NAMES, SCHEMA_VERSION, iter_files, normalize_distribution_name,
                     redact_urls, safe_relative, stable_id, write_json)

REQUIREMENTS_GLOB = "requirements*.txt"
FIXED_MANIFESTS = ("pyproject.toml", "setup.cfg", "setup.py")
_COMMENT_RE = re.compile(r"(^|\s)#.*$")
_REQ_OPTION_RE = re.compile(r"\s+--(?:hash|global-option|install-option|config-settings|no-binary|only-binary)\b.*$")
_INCLUDE_RE = re.compile(r"^(?:-r|--requirement|-c|--constraint)(?:\s*=\s*|\s+|(?=[^\s=-]))(.+)$")
_EDITABLE_RE = re.compile(r"^(?:-e|--editable)(?:\s*=\s*|\s+)(.+)$")
_SPEC_TEXT_RE = re.compile(r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*(?:\[[^\]]*\])?\s*(.*?)\s*(?:;.*)?$")


# --------------------------------------------------------------------------
# Single-requirement parsing
# --------------------------------------------------------------------------
def _parse_requirement(text: str) -> tuple[Requirement | None, str | None]:
    text = _REQ_OPTION_RE.sub("", text.strip())
    try:
        return Requirement(text), None
    except InvalidRequirement as exc:
        return None, str(exc).splitlines()[0][:200]


def parse_requirement_line(line: str) -> tuple[str, str] | None:
    """Compatibility helper: (name, constraint) for one requirement line, else None."""
    stripped = _COMMENT_RE.sub("", line).strip()
    if not stripped or stripped.startswith("-"):
        return None
    req, _ = _parse_requirement(stripped)
    if req is None:
        return None
    return req.name, _constraint_text(req)


def _constraint_text(req: Requirement) -> str:
    spec = str(req.specifier)
    if spec:
        return spec
    if req.url:
        return "@ " + redact_urls(req.url)
    return "(unspecified)"


def _make_decl(req: Requirement, *, file: str, line: int | None, section: str,
               excerpt: str, kind: str = "requirement") -> dict[str, Any]:
    m = _SPEC_TEXT_RE.match(excerpt)
    original = m.group(1) if m else ""
    return {
        "name": req.name,
        "normalized_name": normalize_distribution_name(req.name),
        "extras": sorted(req.extras),
        "specifier": str(req.specifier),
        "original_specifier": redact_urls(original)[:200],
        "constraint": _constraint_text(req),
        "marker": str(req.marker) if req.marker else None,
        "url": redact_urls(req.url) if req.url else None,
        "kind": kind,
        "file": file,
        "line": line,
        "section": section,
        "excerpt": redact_urls(excerpt.strip())[:240],
    }


def _err(file: str, code: str, message: str, line: int | None = None,
         excerpt: str | None = None, severity: str = "error") -> dict[str, Any]:
    e: dict[str, Any] = {"file": file, "line": line, "code": code, "severity": severity, "error": message}
    if excerpt is not None:
        e["excerpt"] = redact_urls(excerpt)[:240]
    return e


def _read_text(path: Path, rel: str) -> tuple[str | None, dict[str, Any] | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except (OSError, UnicodeError) as exc:
        return None, _err(rel, "unreadable", f"Could not read manifest: {exc.__class__.__name__}: {exc}")


def _locate(lines: list[str], needle: str, used: set[tuple[int, str]]) -> int | None:
    """1-based number of the first line containing *needle* not already claimed
    for the same needle (so duplicate entries map to successive lines)."""
    for i, text in enumerate(lines):
        if (i, needle) not in used and needle in text:
            used.add((i, needle))
            return i + 1
    return None


# --------------------------------------------------------------------------
# requirements*.txt
# --------------------------------------------------------------------------
def _parse_requirements_file(path: Path, root: Path, rel: str):
    decls: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    directives: list[dict[str, Any]] = []
    includes: list[Path] = []
    text, err = _read_text(path, rel)
    if err:
        return decls, [err], directives, includes
    raw = text.splitlines()
    i = 0
    while i < len(raw):
        start = i + 1
        buf = raw[i]
        while buf.rstrip().endswith("\\") and i + 1 < len(raw):
            i += 1
            buf = buf.rstrip()[:-1] + " " + raw[i].strip()
        i += 1
        logical = _COMMENT_RE.sub("", buf).strip()
        if not logical:
            continue
        if logical.startswith("-"):
            inc = _INCLUDE_RE.match(logical)
            edit = _EDITABLE_RE.match(logical)
            if inc:
                target = inc.group(1).strip().strip("'\"")
                is_constraint = logical.startswith(("-c", "--constraint"))
                directives.append({"file": rel, "line": start, "directive": "constraint" if is_constraint else "include",
                                   "target": redact_urls(target)})
                if "://" in target:
                    errors.append(_err(rel, "remote_include", "Remote include not followed.", start, logical, "warning"))
                    continue
                tpath = (path.parent / target).resolve()
                try:
                    tpath.relative_to(root.resolve())
                except ValueError:
                    errors.append(_err(rel, "include_outside_root",
                                       "Include points outside the selected root; not read.", start, logical, "warning"))
                    continue
                if not tpath.is_file():
                    errors.append(_err(rel, "include_not_found", "Included file does not exist.", start, logical))
                    continue
                if is_constraint:
                    # Constraint files limit versions but do not request installs.
                    errors.append(_err(rel, "constraint_file_not_compared",
                                       "Constraint file noted but not compared as declarations.", start, logical, "info"))
                else:
                    includes.append(tpath)
            elif edit:
                target = edit.group(1).strip()
                egg = re.search(r"#egg=([A-Za-z0-9._-]+)", target)
                directives.append({"file": rel, "line": start, "directive": "editable", "target": redact_urls(target)[:200]})
                if egg:
                    req, _ = _parse_requirement(egg.group(1))
                    if req:
                        decls.append(_make_decl(req, file=rel, line=start, section="editable", excerpt=logical, kind="editable"))
                else:
                    errors.append(_err(rel, "editable_unnamed",
                                       "Editable install has no #egg= name; package identity unknown.", start, logical, "info"))
            else:
                directives.append({"file": rel, "line": start, "directive": "option", "target": redact_urls(logical)[:200]})
            continue
        req, why = _parse_requirement(logical)
        if req is None:
            errors.append(_err(rel, "invalid_requirement",
                               f"Unrecognized requirement syntax ({why}); review manually", start, logical))
            continue
        decls.append(_make_decl(req, file=rel, line=start, section="requirements", excerpt=logical,
                                kind="direct_url" if req.url else "requirement"))
    return decls, errors, directives, includes


# --------------------------------------------------------------------------
# pyproject.toml / setup.cfg / setup.py
# --------------------------------------------------------------------------
def _decls_from_items(items: list[tuple[str, str]], lines: list[str], rel: str):
    """items: (section, requirement-string)."""
    used: set[tuple[int, str]] = set()
    decls, errors = [], []
    for section, item in items:
        if not isinstance(item, str):
            errors.append(_err(rel, "non_string_dependency", f"Non-string dependency entry in {section}"))
            continue
        line = _locate(lines, item, used)
        req, why = _parse_requirement(item)
        if req is None:
            errors.append(_err(rel, "invalid_requirement", f"Could not parse dependency in {section} ({why})", line, item))
            continue
        decls.append(_make_decl(req, file=rel, line=line, section=section, excerpt=item,
                                kind="direct_url" if req.url else "requirement"))
    return decls, errors


def _parse_pyproject(path: Path, rel: str):
    text, err = _read_text(path, rel)
    if err:
        return [], [err]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], [_err(rel, "invalid_toml", f"Could not parse TOML: {exc.__class__.__name__}: {exc}")]
    items: list[tuple[str, Any]] = []
    errors: list[dict[str, Any]] = []
    project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    deps = project.get("dependencies", [])
    if isinstance(deps, list):
        items += [("project.dependencies", d) for d in deps]
    opt = project.get("optional-dependencies", {})
    if isinstance(opt, dict):
        for group in sorted(opt):
            if isinstance(opt[group], list):
                items += [(f"project.optional-dependencies.{group}", d) for d in opt[group]]
    groups = data.get("dependency-groups", {})
    if isinstance(groups, dict):
        for group in sorted(groups):
            if isinstance(groups[group], list):
                items += [(f"dependency-groups.{group}", d) for d in groups[group] if isinstance(d, str)]
    bs = data.get("build-system", {})
    if isinstance(bs, dict) and isinstance(bs.get("requires"), list):
        items += [("build-system.requires", d) for d in bs["requires"]]
    if "dependencies" in (project.get("dynamic") or []):
        errors.append(_err(rel, "dynamic_dependencies",
                           "project.dependencies is declared dynamic; values come from the build backend and were not evaluated.",
                           severity="info"))
    if "poetry" in (data.get("tool") or {}):
        errors.append(_err(rel, "unsupported_tool_table",
                           "[tool.poetry] dependency tables are not parsed by this scanner.", severity="info"))
    decls, perr = _decls_from_items(items, text.splitlines(), rel)
    return decls, errors + perr


def _parse_setup_cfg(path: Path, rel: str):
    text, err = _read_text(path, rel)
    if err:
        return [], [err]
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cfg.read_string(text)
    except configparser.Error as exc:
        return [], [_err(rel, "invalid_cfg", f"Could not parse setup.cfg: {exc.__class__.__name__}: {str(exc).splitlines()[0]}")]
    items: list[tuple[str, str]] = []

    def lines_of(raw: str) -> list[str]:
        return [_COMMENT_RE.sub("", l).strip() for l in raw.splitlines() if _COMMENT_RE.sub("", l).strip()]

    if cfg.has_option("options", "install_requires"):
        items += [("options.install_requires", l) for l in lines_of(cfg.get("options", "install_requires"))]
    for sec in sorted(s for s in cfg.sections() if s == "options.extras_require"):
        for key in cfg.options(sec):
            items += [(f"options.extras_require.{key}", l) for l in lines_of(cfg.get(sec, key))]
    decls, errors = _decls_from_items(items, text.splitlines(), rel)
    return decls, errors


def _str_nodes(node: ast.AST) -> list[tuple[str, int]] | None:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append((elt.value, elt.lineno))
            else:
                return None
        return out
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [(l.strip(), node.lineno) for l in node.value.splitlines() if l.strip()]
    return None


def _parse_setup_py(path: Path, rel: str):
    text, err = _read_text(path, rel)
    if err:
        return [], [err]
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return [], [_err(rel, "invalid_python", f"setup.py could not be parsed: {exc.__class__.__name__}: {exc}")]
    decls, errors = [], []
    found_setup = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not ((isinstance(fn, ast.Name) and fn.id == "setup") or (isinstance(fn, ast.Attribute) and fn.attr == "setup")):
            continue
        found_setup = True
        for kw in node.keywords:
            if kw.arg == "install_requires":
                groups = [("setup.install_requires", kw.value)]
            elif kw.arg == "extras_require" and isinstance(kw.value, ast.Dict):
                groups = [(f"setup.extras_require.{k.value}", v) for k, v in zip(kw.value.keys, kw.value.values)
                          if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            elif kw.arg in ("extras_require",):
                errors.append(_err(rel, "setup_py_dynamic", "extras_require is not a literal dict; not evaluated "
                                   "(setup.py is never executed).", kw.value.lineno, severity="info"))
                continue
            else:
                continue
            for section, value in groups:
                strs = _str_nodes(value)
                if strs is None:
                    errors.append(_err(rel, "setup_py_dynamic",
                                       f"{section} is not a literal list of strings; not evaluated "
                                       "(setup.py is never executed).", value.lineno, severity="info"))
                    continue
                for item, lineno in strs:
                    req, why = _parse_requirement(item)
                    if req is None:
                        errors.append(_err(rel, "invalid_requirement", f"Could not parse dependency in {section} ({why})",
                                           lineno, item))
                    else:
                        decls.append(_make_decl(req, file=rel, line=lineno, section=section, excerpt=item))
    if not found_setup:
        errors.append(_err(rel, "setup_py_no_setup_call", "No setup(...) call found to analyze statically.", severity="info"))
    return decls, errors


# --------------------------------------------------------------------------
# Constraint comparison
# --------------------------------------------------------------------------
def _candidates(*specs: SpecifierSet) -> list[Version]:
    out: set[Version] = {Version("0"), Version("0.0.1"), Version("1000000")}
    for ss in specs:
        for s in ss:
            raw = s.version[:-2] if s.version.endswith(".*") else s.version
            try:
                v = Version(raw)
            except InvalidVersion:
                continue
            rel = list(v.release)
            out.add(v)
            out.add(Version(".".join(map(str, rel + [1]))))
            up = rel[:-1] + [rel[-1] + 1]
            out.add(Version(".".join(map(str, up))))
            if rel[-1] > 0:
                out.add(Version(".".join(map(str, rel[:-1] + [rel[-1] - 1]))))
    return sorted(out)


def assess_pair(a: dict[str, Any], b: dict[str, Any]) -> tuple[str, str]:
    """Return (assessment, reason): compatible | incompatible | uncertain."""
    if (a["marker"] or b["marker"]) and a["marker"] != b["marker"]:
        return "uncertain", "Declarations carry different environment markers; applicability depends on the environment."
    if a["url"] or b["url"]:
        if a["url"] == b["url"] and a["specifier"] == b["specifier"]:
            return "compatible", "Identical direct reference."
        return "uncertain", "A direct URL/VCS reference cannot be compared with a version specifier without resolving it."
    try:
        sa, sb = SpecifierSet(a["specifier"]), SpecifierSet(b["specifier"])
    except InvalidSpecifier:
        return "uncertain", "A version specifier could not be parsed."
    if not a["specifier"] or not b["specifier"]:
        return "compatible", "At least one declaration is unconstrained."
    pins = []
    for ss in (sa, sb):
        pins += [s.version for s in ss if s.operator == "==" and not s.version.endswith(".*")]
    for pin in pins:
        try:
            v = Version(pin)
        except InvalidVersion:
            continue
        if not sa.contains(v, prereleases=True) or not sb.contains(v, prereleases=True):
            return "incompatible", f"Exact pin =={pin} is not allowed by the other declaration's specifier."
    for cand in _candidates(sa, sb):
        if sa.contains(cand, prereleases=True) and sb.contains(cand, prereleases=True):
            return "compatible", f"Version {cand} satisfies both specifiers."
    complex_ops = any(s.operator in ("!=", "===") or s.version.endswith(".*") for ss in (sa, sb) for s in ss)
    if complex_ops:
        return "uncertain", "No satisfying version found among tested boundary versions, but the specifiers use !=, === or wildcards."
    return "incompatible", "No version in the tested boundary set satisfies both specifiers."


def _decl_key(d: dict[str, Any]):
    return (d["file"], d["line"] or 0, d["section"], d["name"])


def _build_findings(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for d in declarations:
        by_name.setdefault(d["normalized_name"], []).append(d)
    findings = []
    for name in sorted(by_name):
        entries = sorted(by_name[name], key=_decl_key)
        involved: dict[tuple, dict[str, Any]] = {}
        pairs = []
        verdicts: set[str] = set()
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                if a["file"] == b["file"] and a["section"] != b["section"]:
                    continue  # alternative groups within a single manifest are not comparable
                if (a["specifier"], a["marker"], a["url"]) == (b["specifier"], b["marker"], b["url"]):
                    continue
                verdict, reason = assess_pair(a, b)
                if verdict == "compatible":
                    continue
                pairs.append({"a": f"{a['file']}:{a['line']}", "b": f"{b['file']}:{b['line']}",
                              "assessment": verdict, "reason": reason})
                for d in (a, b):
                    involved[_decl_key(d)] = d
                verdicts.add(verdict)
        if not pairs:
            continue
        evid = []
        for d in sorted(involved.values(), key=_decl_key):
            evid.append({"file": d["file"], "line": d["line"], "excerpt": d["excerpt"],
                         "normalized_package": d["normalized_name"], "specifier": d["specifier"],
                         "original_specifier": d["original_specifier"], "section": d["section"],
                         "marker": d["marker"], "role": "declaration"})
        sig = sorted(f"{d['file']}|{d['section']}|{d['specifier']}|{d['marker']}|{d['url']}" for d in involved.values())
        incompatible = "incompatible" in verdicts
        findings.append({
            "id": stable_id("F", "manifest_inconsistency", name, *sig),
            "type": "manifest_inconsistency",
            "severity": "review" if incompatible else "info",
            "title": f"{'Incompatible' if incompatible else 'Possibly inconsistent'} declarations for {name}",
            "summary": (f"{name} is declared with constraints that "
                        f"{'cannot be satisfied together' if incompatible else 'could not be proven compatible'} "
                        "across manifests. This is a manifest inconsistency to review; it is not proof that the "
                        "application fails, and this scanner does not decide which declaration is correct."),
            "package": name,
            "assessment": "incompatible_constraints" if incompatible else "uncertain",
            "observed": "; ".join(f"{e['file']}:{e['line']} declares `{e['excerpt']}`" for e in evid),
            "inferred": "; ".join(f"{p['a']} vs {p['b']}: {p['reason']}" for p in pairs),
            "pairs": pairs,
            "evidence": evid,
            "status": "observed",
        })
    return sorted(findings, key=lambda f: (f["package"], f["id"]))


# --------------------------------------------------------------------------
# Discovery and scan
# --------------------------------------------------------------------------
def _manifest_format(name: str) -> str | None:
    if fnmatch.fnmatch(name, REQUIREMENTS_GLOB):
        return "requirements"
    return {"pyproject.toml": "pyproject", "setup.cfg": "setup.cfg", "setup.py": "setup.py"}.get(name)


def discover_manifests(root: Path, exclude: tuple[str, ...] = (),
                       excluded_log: list[dict[str, str]] | None = None) -> list[Path]:
    found = [p for p in iter_files(root, exclude, excluded_log) if _manifest_format(p.name)]
    return sorted(found, key=lambda p: safe_relative(p, root).lower())


def scan_repository(root: Path, exclude: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Scan root is not a directory: {root.name or root}")
    root = root.resolve()
    exclude = tuple(exclude)
    excluded: list[dict[str, str]] = []
    queue = discover_manifests(root, exclude, excluded)
    seen: set[Path] = set()
    declarations: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    directives: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    included_by: dict[Path, list[str]] = {}
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        rel = safe_relative(path, root)
        fmt = _manifest_format(path.name) or "requirements"
        if fmt == "requirements":
            decls, errs, dirs, incs = _parse_requirements_file(path, root, rel)
            directives += dirs
            for inc in incs:
                included_by.setdefault(inc, []).append(rel)
                if inc not in seen:
                    queue.append(inc)
        elif fmt == "pyproject":
            decls, errs = _parse_pyproject(path, rel)
        elif fmt == "setup.cfg":
            decls, errs = _parse_setup_cfg(path, rel)
        else:
            decls, errs = _parse_setup_py(path, rel)
        declarations += decls
        errors += errs
        manifests.append({"file": rel, "format": fmt, "declaration_count": len(decls),
                          "included_by": sorted(included_by.get(path, []))})
    manifests.sort(key=lambda m: m["file"].lower())
    declarations.sort(key=_decl_key)
    errors.sort(key=lambda e: (e["file"], e.get("line") or 0, e["code"]))
    findings = _build_findings(declarations)
    hard_errors = [e for e in errors if e["severity"] == "error"]
    status = "no_manifests_found" if not manifests else ("completed_with_errors" if hard_errors else "completed")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "scan",
        "timestamp_policy": "No wall-clock timestamp is embedded so repeated scans of unchanged source are byte-identical.",
        "root": root.name,
        "root_policy": "Only the directory name is recorded; all paths in this report are relative to the scan root.",
        "scan_status": status,
        "summary": {"manifest_count": len(manifests), "declaration_count": len(declarations),
                    "finding_count": len(findings), "error_count": len(hard_errors),
                    "note_count": len(errors) - len(hard_errors)},
        "manifests_scanned": [m["file"] for m in manifests],
        "manifests": manifests,
        "declaration_count": len(declarations),
        "declarations": declarations,
        "directives": sorted(directives, key=lambda d: (d["file"], d["line"])),
        "findings": findings,
        "errors": errors,
        "exclusions": {
            "directory_names": sorted(EXCLUDED_DIR_NAMES),
            "directory_patterns": ["*.egg-info", "*.dist-info", "directories containing pyvenv.cfg"],
            "user_exclusions": sorted(exclude),
            "excluded_directories_encountered": sorted(excluded, key=lambda e: e["path"]),
        },
        "limitations": [
            "Only requirements*.txt, pyproject.toml, setup.cfg and setup.py (literal values) are parsed; "
            "Pipfile, poetry/pdm tables, conda files and lockfiles are not.",
            "setup.py is analyzed statically and never executed; computed dependency lists are not evaluated.",
            "Constraint files (-c) and remote includes are noted but not compared.",
            "Compatibility of two specifiers is judged against a bounded set of candidate versions; when the "
            "result cannot be proven the finding is reported as uncertain.",
            "Different or incompatible constraints are observations, not proof of runtime failure, and no "
            "security advisory data is consulted.",
            "No manifests found means the repository was not assessed, not that it is clean.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scan Python dependency manifests for evidence-backed inconsistencies.")
    ap.add_argument("--root", default=".", help="Repository root to scan (default: current directory)")
    ap.add_argument("--output", default="patchproof-report.json", help="JSON output path")
    ap.add_argument("--exclude", action="append", default=[], help="Extra directory name or root-relative path to skip (repeatable)")
    args = ap.parse_args(argv)
    try:
        report = scan_repository(Path(args.root), tuple(args.exclude))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    write_json(Path(args.output), report)
    s = report["summary"]
    print(f"Scan status: {report['scan_status']}; {s['manifest_count']} manifest(s); {s['declaration_count']} declaration(s); "
          f"{s['finding_count']} finding(s); {s['error_count']} parse/read error(s).")
    print(f"Report: {args.output}")
    return 2 if s["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
