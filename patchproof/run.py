"""One-command artifact generation (PatchProof Person 1).

  python -m patchproof.run --root <repo> --out-dir patchproof-output [--verify-config cfg.json] [--ai ai-analysis.json]

Scan-only works with no verification or AI. Verification runs ONLY when
--verify-config is supplied. Output directory is excluded from scanning.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capsule import build_capsule, to_markdown
from .common import load_json_artifact, write_json
from .diagnose import diagnose
from .scanner import scan_repository
from .usage import trace_usage
from .verify import EXIT_CODES, verify


def run(root: Path, out_dir: Path, verify_config: str | None = None, ai_path: str | None = None,
        exclude: tuple[str, ...] = (), strict: bool = False) -> int:
    stages: list[tuple[str, str, str]] = []
    code = 0
    root = Path(root)
    if not root.is_dir():
        print(f"[FAIL] validate: root is not a directory: {root.name or root}", file=sys.stderr)
        return 1
    root_r = root.resolve()
    ex = list(exclude)
    try:
        rel = out_dir.resolve().relative_to(root_r).as_posix()
        ex.append(rel)  # never scan our own output
    except ValueError:
        pass
    ex_t = tuple(ex)
    stages.append(("validate", "OK", f"root={root_r.name}"))
    try:
        scan = scan_repository(root, ex_t)
        write_json(out_dir / "patchproof-report.json", scan)
        s = scan["summary"]
        note = f"{scan['scan_status']}; {s['manifest_count']} manifest(s), {s['finding_count']} finding(s), {s['error_count']} error(s)"
        stages.append(("scan", "WARN" if s["error_count"] or scan["scan_status"] == "no_manifests_found" else "OK", note))
        if strict and s["error_count"]:
            code = code or 2
    except Exception as exc:  # report and fail the stage honestly
        print(f"[FAIL] scan: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    try:
        usage = trace_usage(root, ex_t, scan=scan)
        write_json(out_dir / "patchproof-usage-report.json", usage)
        stages.append(("usage", "OK", f"{usage['summary']['declared_packages']} package(s); {usage['summary']['by_status']}"))
    except Exception as exc:
        print(f"[FAIL] usage: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    ver = None
    if verify_config:
        ver = verify(verify_config)
        write_json(out_dir / "verification.json", ver)
        vcode = EXIT_CODES.get(ver["status"], 2)
        stages.append(("verify", "OK" if vcode == 0 else "FAIL" if vcode in (1, 2) else "WARN", f"status={ver['status']}"))
        if vcode:
            code = code or vcode
    else:
        stages.append(("verify", "SKIPPED", "no --verify-config supplied; no repository commands were run"))
    ai = load_json_artifact(ai_path) if ai_path else None
    stages.append(("ai", "SKIPPED" if ai is None else ("FAIL" if ai.get("status") in ("missing", "unreadable") and "schema_version" not in ai and "model" not in ai else "OK"),
                   "no AI artifact supplied; nothing fabricated" if ai is None else f"using {Path(ai_path).name}"))
    if stages[-1][1] == "FAIL":
        code = code or 1
    try:
        capsule = build_capsule(scan, usage, ai, ver, diagnose(scan, usage, ver))
        write_json(out_dir / "dependency-exit-capsule.json", capsule)
        with open(out_dir / "dependency-exit-capsule.md", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(to_markdown(capsule))
        stages.append(("capsule", "OK", f"overall_status={capsule['overall_status']}; verification_status={capsule['verification_status']}"))
    except Exception as exc:
        print(f"[FAIL] capsule: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    for name, state, note in stages:
        print(f"[{state:7}] {name}: {note}")
    print(f"Artifacts in: {out_dir}")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate all PatchProof artifacts for a repository.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out-dir", default="patchproof-output")
    ap.add_argument("--verify-config")
    ap.add_argument("--ai", help="Path to a genuine ai-analysis.json (optional)")
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--strict", action="store_true", help="Exit nonzero if manifests had parse/read errors")
    a = ap.parse_args(argv)
    return run(Path(a.root), Path(a.out_dir), a.verify_config, a.ai, tuple(a.exclude), a.strict)


if __name__ == "__main__":
    raise SystemExit(main())
