"""Static source-usage tracer (PatchProof Person 1).

Relates declared distributions to imports found by parsing Python source with
``ast``. Project source is never imported or executed. "No static import
found" is a review lead, never proof that a dependency is unused.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any, Mapping

from .common import (SCHEMA_VERSION, iter_files, normalize_distribution_name,
                     safe_relative, stable_id, write_json)
from .scanner import scan_repository

DYNAMIC_FUNCS = {"import_module", "__import__"}


def _load_distribution_mapping() -> dict[str, list[str]]:
    """Top-level import name -> distributions, from the *active* environment's metadata."""
    try:
        from importlib.metadata import packages_distributions
        return {k: list(v) for k, v in packages_distributions().items()}
    except Exception:  # metadata unreadable: treated as 'mapping unavailable'
        return {}


def invert_mapping(mapping: Mapping[str, list[str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for module, dists in mapping.items():
        for dist in dists or []:
            out.setdefault(normalize_distribution_name(dist), set()).add(module.split(".", 1)[0])
    return out


def analyze_source(path: Path, rel: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, int]:
    """Return (imports, parse_error, unresolved_dynamic_import_count)."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=rel)
    except (OSError, UnicodeError) as exc:
        return [], {"file": rel, "line": None, "error": f"Could not read source: {exc.__class__.__name__}: {exc}"}, 0
    except (SyntaxError, ValueError) as exc:
        return [], {"file": rel, "line": getattr(exc, "lineno", None),
                    "error": f"Could not parse source: {exc.__class__.__name__}: {getattr(exc, 'msg', exc)}"}, 0
    imports: list[dict[str, Any]] = []
    unresolved = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append({"file": rel, "line": node.lineno, "module": a.name.split(".", 1)[0],
                                "import_name": a.name, "alias": a.asname, "kind": "import",
                                "statement": f"import {a.name}" + (f" as {a.asname}" if a.asname else "")})
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue  # relative import: project-local
            names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
            imports.append({"file": rel, "line": node.lineno, "module": node.module.split(".", 1)[0],
                            "import_name": node.module, "alias": None, "kind": "from_import",
                            "statement": f"from {node.module} import {names}"[:200]})
        elif isinstance(node, ast.Call):
            fn = node.func
            fname = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if fname in DYNAMIC_FUNCS:
                arg = node.args[0] if node.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and not arg.value.startswith("."):
                    imports.append({"file": rel, "line": node.lineno, "module": arg.value.split(".", 1)[0],
                                    "import_name": arg.value, "alias": None, "kind": "dynamic_literal",
                                    "statement": f"{fname}({arg.value!r})"})
                else:
                    unresolved += 1
    imports.sort(key=lambda i: (i["file"], i["line"], i["import_name"]))
    return imports, None, unresolved


def trace_usage(root: Path, exclude: tuple[str, ...] | list[str] = (),
                mapping: Mapping[str, list[str]] | None = None,
                scan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Trace declared distributions to imports.

    ``mapping`` (import-name -> distributions) may be supplied for deterministic
    testing; otherwise the active environment's installed metadata is used.
    ``scan`` may be a previously produced scan report (shared representation).
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Scan root is not a directory: {root.name or root}")
    root = root.resolve()
    exclude = tuple(exclude)
    scan = scan if scan is not None else scan_repository(root, exclude)
    excluded: list[dict[str, str]] = []
    imports: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    unresolved_by_file: dict[str, int] = {}
    files = 0
    for path in iter_files(root, exclude, excluded):
        if path.suffix != ".py":
            continue
        rel = safe_relative(path, root)
        files += 1
        found, err, unresolved = analyze_source(path, rel)
        imports += found
        if err:
            parse_errors.append(err)
        if unresolved:
            unresolved_by_file[rel] = unresolved
    imports.sort(key=lambda i: (i["file"], i["line"], i["import_name"]))
    raw_mapping = dict(mapping) if mapping is not None else _load_distribution_mapping()
    dist_to_modules = invert_mapping(raw_mapping)

    by_pkg: dict[str, list[dict[str, Any]]] = {}
    for d in scan.get("declarations", []):
        by_pkg.setdefault(d["normalized_name"], []).append(d)
    incomplete_reasons = []
    if parse_errors:
        incomplete_reasons.append(f"{len(parse_errors)} source file(s) could not be parsed")
    if unresolved_by_file:
        incomplete_reasons.append(f"{sum(unresolved_by_file.values())} dynamic import call(s) with non-literal targets")
    packages, leads = [], []
    for pkg in sorted(by_pkg):
        decls = by_pkg[pkg]
        mapped = sorted(dist_to_modules.get(pkg, set()))
        if mapped:
            roots, source = mapped, "installed_metadata"
        else:
            roots, source = [pkg.replace("-", "_")], "name_heuristic"
        hits = [i for i in imports if i["module"] in roots]
        if hits:
            status = "import_observed"
        elif source == "name_heuristic":
            status = "mapping_unavailable"
        elif incomplete_reasons:
            status = "analysis_incomplete"
        else:
            status = "no_static_import_found"
        if status == "import_observed":
            note = ("Import(s) matching the candidate import root(s) were observed in source."
                    + (" The import root is a guess from the distribution name because no installed metadata was found."
                       if source == "name_heuristic" else ""))
        elif status == "mapping_unavailable":
            note = ("The distribution is not installed in the active environment, so its import names are unknown; "
                    "the name-based guess found no import. Install it (or supply metadata) to get a reliable mapping.")
        elif status == "analysis_incomplete":
            note = "No import found, but analysis was incomplete (" + "; ".join(incomplete_reasons) + "). Review manually."
        else:
            note = ("No static import was found. This is a review lead only, not proof the package is unused: dynamic imports, plugins, entry points, "
                    "CLI use or optional features may still use the package.")
        entry = {
            "package": pkg,
            "declarations": [{"file": d["file"], "line": d["line"], "constraint": d["constraint"], "section": d["section"]}
                             for d in decls],
            "candidate_import_roots": roots,
            "mapping_source": source,
            "imports_found": hits,
            "usage_status": status,
            "interpretation": note,
        }
        if status in ("no_static_import_found", "analysis_incomplete", "mapping_unavailable"):
            lead_id = stable_id("U", "usage_review", pkg, *sorted(f"{d['file']}|{d['section']}" for d in decls))
            entry["review_lead_id"] = lead_id
            leads.append({"id": lead_id, "type": "usage_review", "severity": "info", "package": pkg,
                          "usage_status": status, "status": "observed",
                          "title": f"No confirmed static import for {pkg}",
                          "summary": note})
        packages.append(entry)
    counts: dict[str, int] = {}
    for p in packages:
        counts[p["usage_status"]] = counts.get(p["usage_status"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "usage",
        "root": root.name,
        "scan_status": scan.get("scan_status"),
        "python_files_scanned": files,
        "python_files_with_imports": len({i["file"] for i in imports}),
        "summary": {"declared_packages": len(packages), "by_status": dict(sorted(counts.items())),
                    "parse_error_count": len(parse_errors), "analysis_complete": not incomplete_reasons},
        "packages": packages,
        "review_leads": leads,
        "parse_errors": sorted(parse_errors, key=lambda e: (e["file"], e.get("line") or 0)),
        "unresolved_dynamic_imports": dict(sorted(unresolved_by_file.items())),
        "mapping": {"source": "supplied" if mapping is not None else "installed_metadata_of_active_python",
                    "entries": len(raw_mapping)},
        "exclusions": {"excluded_directories_encountered": sorted(excluded, key=lambda e: e["path"])},
        "limitations": [
            "Import-to-distribution mappings come from metadata installed in the Python environment running this tool; "
            "uninstalled distributions fall back to a name-based guess and are labelled mapping_unavailable when unmatched.",
            "Dynamic imports with non-literal targets, plugin loading, entry points, runtime loading, CLI-only use, "
            "data-only packages and optional features cannot be detected statically.",
            "Literal importlib.import_module('x') / __import__('x') calls are recorded as kind=dynamic_literal.",
            "A missing import must never be treated as proof that a package is unused; do not remove packages on this basis.",
            "Import roots are matched at top level only; namespace packages shared by several distributions may over-match.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Trace declared Python packages to source imports (static analysis only).")
    ap.add_argument("--root", default=".")
    ap.add_argument("--output", default="patchproof-usage-report.json")
    ap.add_argument("--exclude", action="append", default=[])
    args = ap.parse_args(argv)
    try:
        report = trace_usage(Path(args.root), tuple(args.exclude))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    write_json(Path(args.output), report)
    print(f"Traced {report['summary']['declared_packages']} declared package(s) across "
          f"{report['python_files_scanned']} Python file(s); by status: {report['summary']['by_status']}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
