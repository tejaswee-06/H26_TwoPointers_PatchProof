"""Shared helpers for PatchProof engine modules (Person 1).

Deterministic by design: no random IDs, sorted directory walks, no absolute
local paths in artifacts.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = "2.0"

# Directory *names* never descended into.
EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "site-packages", "build", "dist", ".eggs", ".idea", ".vscode",
    "patchproof-output", "patchproof_output",
})
# Glob patterns (matched against a directory name) that are also excluded.
EXCLUDED_DIR_PATTERNS = ("*.egg-info", "*.dist-info")


def normalize_distribution_name(name: str) -> str:
    """PEP 503 normalization: runs of -, _, . become one hyphen; lower-case."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def stable_id(prefix: str, *parts: object, length: int = 10) -> str:
    payload = "\x1f".join(str(p) for p in parts).encode("utf-8", errors="replace")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:length].upper()}"


def safe_relative(path: Path, root: Path) -> str:
    """Posix-style path relative to root; never leaks an absolute path.

    If *path* is outside *root* the bare file name is returned.
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


_URL_CRED = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@")


def redact_urls(text: str) -> str:
    """Remove user:password@ credentials embedded in URLs."""
    return _URL_CRED.sub(r"\1***@", text)


def is_excluded_dir(dir_path: Path, root: Path, extra: tuple[str, ...] = ()) -> str | None:
    """Return the exclusion reason for a directory, or None if it is scannable."""
    name = dir_path.name
    if name in EXCLUDED_DIR_NAMES:
        return "excluded_name"
    if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDED_DIR_PATTERNS):
        return "excluded_pattern"
    if (dir_path / "pyvenv.cfg").is_file():
        return "virtual_environment"
    if extra:
        rel = safe_relative(dir_path, root)
        if name in extra or rel in extra:
            return "user_exclusion"
    return None


def iter_files(root: Path, extra_exclude: tuple[str, ...] = (),
               excluded_log: list[dict[str, str]] | None = None) -> Iterator[Path]:
    """Deterministic walk yielding files; prunes excluded directories."""
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        keep = []
        for d in sorted(dirnames):
            reason = is_excluded_dir(current / d, root, extra_exclude)
            if reason:
                # user exclusions are listed separately in the report; omitting them here keeps
                # output identical whether or not an excluded output directory exists yet.
                if excluded_log is not None and reason != "user_exclusion":
                    excluded_log.append({"path": safe_relative(current / d, root), "reason": reason})
            else:
                keep.append(d)
        dirnames[:] = keep
        for fn in sorted(filenames):
            yield current / fn


def dumps_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps_json(data))


def load_json_artifact(path: str | os.PathLike | None) -> Any:
    """Load a JSON artifact. Returns None when no path was requested; a
    marker dict with status 'missing' / 'unreadable' when the file cannot be used."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return {"status": "missing", "requested_path": p.name}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {"status": "unreadable", "requested_path": p.name,
                "error": f"{exc.__class__.__name__}: {exc}"}
