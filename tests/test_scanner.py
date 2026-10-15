from pathlib import Path
from patchproof.common import normalize_distribution_name
from patchproof.scanner import scan_repository, parse_requirement_line

def test_normalization():
    assert normalize_distribution_name("MarkupSafe") == "markupsafe"
    assert normalize_distribution_name("my_pkg.name") == "my-pkg-name"

def test_requirements_comments_blank_lines_and_versions():
    assert parse_requirement_line("# hello") is None
    assert parse_requirement_line("   ") is None
    assert parse_requirement_line("pydantic==1.10.13")[1] == "==1.10.13"
    assert parse_requirement_line("Requests>=2.0 # comment")[1] == ">=2.0"

def test_conflicting_manifest_constraints(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("pydantic==1.10.13\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\ndependencies=["pydantic>=2"]\n', encoding="utf-8")
    report = scan_repository(tmp_path)
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["type"] == "manifest_inconsistency"
    assert {e["file"] for e in finding["evidence"]} == {"requirements.txt", "pyproject.toml"}
    assert finding["status"] == "observed"

def test_consistent_declarations_not_flagged(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\ndependencies=["requests>=2"]\n', encoding="utf-8")
    assert scan_repository(tmp_path)["findings"] == []

def test_malformed_toml_reported(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project\nname = ", encoding="utf-8")
    report = scan_repository(tmp_path)
    assert report["errors"]
    assert "Could not parse TOML" in report["errors"][0]["error"]

def test_generated_and_venv_paths_are_ignored(tmp_path: Path):
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "requirements.txt").write_text("bad==1\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("good==1\n", encoding="utf-8")
    report = scan_repository(tmp_path)
    assert report["manifests_scanned"] == ["requirements.txt"]


# ---------------------------------------------------------------------------
# Expanded scanner coverage (Person 1 hardening)
# ---------------------------------------------------------------------------
import json
import pytest
from conftest import write
from patchproof.scanner import assess_pair, main as scanner_main


def _decl(spec, marker=None, url=None):
    return {"specifier": spec, "marker": marker, "url": url}


def test_exact_pin_parsed_with_line_number(tmp_path):
    write(tmp_path / "requirements.txt", "# header\n\nrequests==2.31.0\n")
    d = scan_repository(tmp_path)["declarations"][0]
    assert (d["normalized_name"], d["specifier"], d["line"], d["excerpt"]) == ("requests", "==2.31.0", 3, "requests==2.31.0")


@pytest.mark.parametrize("name", ["Foo_Bar", "foo.bar", "FOO-BAR", "foo__bar"])
def test_name_variants_normalize_to_one_package(tmp_path, name):
    write(tmp_path / "requirements.txt", f"{name}==1.0\n")
    assert scan_repository(tmp_path)["declarations"][0]["normalized_name"] == "foo-bar"


def test_case_and_separator_variants_do_not_create_false_conflict(tmp_path):
    write(tmp_path / "requirements.txt", "Foo_Bar>=1.0\n")
    write(tmp_path / "pyproject.toml", '[project]\nname="x"\ndependencies=["foo-bar>=1.0"]\n')
    assert scan_repository(tmp_path)["findings"] == []


def test_exact_pin_vs_incompatible_lower_bound_is_flagged_with_both_declarations(tmp_path):
    write(tmp_path / "requirements.txt", "pydantic==1.10.13\n")
    write(tmp_path / "pyproject.toml", '[project]\nname="x"\ndependencies=[\n  "pydantic>=2",\n]\n')
    f = scan_repository(tmp_path)["findings"][0]
    assert f["assessment"] == "incompatible_constraints"
    lines = {(e["file"], e["line"], e["excerpt"]) for e in f["evidence"]}
    assert lines == {("requirements.txt", 1, "pydantic==1.10.13"), ("pyproject.toml", 4, "pydantic>=2")}
    assert "observed" in f and "inferred" in f


def test_mutually_incompatible_ranges(tmp_path):
    write(tmp_path / "requirements.txt", "pkg>=3,<4\n")
    write(tmp_path / "requirements-dev.txt", "pkg<2\n")
    assert scan_repository(tmp_path)["findings"][0]["assessment"] == "incompatible_constraints"


def test_pin_conflicting_with_compatible_release(tmp_path):
    write(tmp_path / "requirements.txt", "pkg==1.4.0\n")
    write(tmp_path / "requirements-dev.txt", "pkg~=2.1\n")
    assert len(scan_repository(tmp_path)["findings"]) == 1


def test_different_but_compatible_constraints_not_flagged(tmp_path):
    write(tmp_path / "requirements.txt", "pkg==1.5.0\n")
    write(tmp_path / "requirements-dev.txt", "pkg>=1.0,<2\n")
    assert scan_repository(tmp_path)["findings"] == []


def test_repeated_identical_declarations_not_a_conflict(tmp_path):
    write(tmp_path / "requirements.txt", "pkg==1.0\npkg==1.0\n")
    write(tmp_path / "requirements-dev.txt", "pkg==1.0\n")
    assert scan_repository(tmp_path)["findings"] == []


def test_different_markers_are_uncertain_not_conflict():
    verdict, _ = assess_pair({**_decl("==1.0"), "marker": 'python_version < "3.8"'}, {**_decl("==2.0"), "marker": 'python_version >= "3.8"'})
    assert verdict == "uncertain"


def test_wildcard_exclusion_without_proof_is_uncertain():
    assert assess_pair(_decl("!=1.0,>=1.0,<=1.0"), _decl(">=0.5"))[0] == "uncertain"
    assert assess_pair(_decl("==1.*"), _decl(">=1.2,<1.5"))[0] == "compatible"


def test_direct_url_vs_version_is_uncertain():
    assert assess_pair(_decl("", url="https://x/y.whl"), _decl(">=1"))[0] == "uncertain"


def test_extras_markers_and_urls_parse(tmp_path):
    write(tmp_path / "requirements.txt",
          'requests[security,socks]>=2.0; python_version >= "3.8"\n'
          'mypkg @ https://user:secret@example.com/mypkg-1.0.whl\n')
    ds = {d["normalized_name"]: d for d in scan_repository(tmp_path)["declarations"]}
    assert ds["requests"]["extras"] == ["security", "socks"]
    assert ds["requests"]["marker"] == 'python_version >= "3.8"'
    assert ds["mypkg"]["kind"] == "direct_url"
    blob = json.dumps(ds["mypkg"])
    assert "secret" not in blob


def test_inline_comments_continuations_hashes_and_options(tmp_path):
    write(tmp_path / "requirements.txt",
          "--index-url https://pypi.org/simple\n"
          "flask==3.0.0 \\\n    --hash=sha256:abc  # pinned\n"
          "click>=8 # inline\n"
          "numpy>=1.0\\\n  ,<2\n")
    ds = {d["normalized_name"]: d for d in scan_repository(tmp_path)["declarations"]}
    assert ds["flask"]["specifier"] == "==3.0.0"
    assert ds["click"]["specifier"] == ">=8"
    assert ds["numpy"]["specifier"] == "<2,>=1.0"
    assert ds["flask"]["line"] == 2


def test_include_directive_followed_inside_root(tmp_path):
    write(tmp_path / "requirements.txt", "-r base/common.txt\n")
    write(tmp_path / "base" / "common.txt", "six==1.16.0\n")
    r = scan_repository(tmp_path)
    assert "base/common.txt" in r["manifests_scanned"]
    assert any(d["name"] == "six" for d in r["declarations"])


def test_include_outside_root_not_read(tmp_path):
    root = tmp_path / "proj"
    write(root / "requirements.txt", "-r ../secret.txt\n")
    write(tmp_path / "secret.txt", "leaked==9.9\n")
    r = scan_repository(root)
    assert not any(d["name"] == "leaked" for d in r["declarations"])
    assert any(e["code"] == "include_outside_root" for e in r["errors"])


def test_include_cycle_terminates(tmp_path):
    write(tmp_path / "requirements.txt", "-r requirements-a.txt\n")
    write(tmp_path / "requirements-a.txt", "-r requirements.txt\nx==1\n")
    assert len(scan_repository(tmp_path)["declarations"]) == 1


def test_editable_with_egg_name_recorded(tmp_path):
    write(tmp_path / "requirements.txt", "-e git+https://github.com/o/r.git#egg=mylib\n")
    d = scan_repository(tmp_path)["declarations"][0]
    assert d["kind"] == "editable" and d["normalized_name"] == "mylib"


def test_malformed_requirement_line_reported_not_fatal(tmp_path):
    write(tmp_path / "requirements.txt", "good==1.0\n!!! nonsense ???\nalso-good>=2\n")
    r = scan_repository(tmp_path)
    assert [d["name"] for d in r["declarations"]] == ["good", "also-good"]
    err = r["errors"][0]
    assert (err["code"], err["line"]) == ("invalid_requirement", 2)
    assert r["scan_status"] == "completed_with_errors"


def test_unreadable_file_reported_not_fatal(tmp_path):
    write(tmp_path / "requirements.txt", "ok==1\n")
    (tmp_path / "requirements-dev.txt").write_bytes(b"\xff\xfe\x00bad\xff")
    r = scan_repository(tmp_path)
    assert any(d["name"] == "ok" for d in r["declarations"])
    assert any(e["code"] == "unreadable" for e in r["errors"])


def test_missing_manifests_distinguishable_from_clean(tmp_path):
    write(tmp_path / "main.py", "print(1)\n")
    r = scan_repository(tmp_path)
    assert r["scan_status"] == "no_manifests_found" and r["findings"] == []
    write(tmp_path / "requirements.txt", "a==1\n")
    assert scan_repository(tmp_path)["scan_status"] == "completed"


def test_nonexistent_root_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_repository(tmp_path / "nope")


def test_nested_manifests_found_with_relative_paths(tmp_path):
    write(tmp_path / "services" / "api" / "requirements.txt", "fastapi>=0.100\n")
    r = scan_repository(tmp_path)
    assert r["manifests_scanned"] == ["services/api/requirements.txt"]


def test_pyproject_optional_dependencies_and_groups(tmp_path):
    write(tmp_path / "pyproject.toml",
          '[project]\nname="x"\ndependencies=["a>=1"]\n[project.optional-dependencies]\ndev=["pytest>=7"]\n'
          '[dependency-groups]\ndocs=["sphinx>=7"]\n[build-system]\nrequires=["setuptools>=68"]\n')
    sections = {d["name"]: d["section"] for d in scan_repository(tmp_path)["declarations"]}
    assert sections == {"a": "project.dependencies", "pytest": "project.optional-dependencies.dev",
                        "sphinx": "dependency-groups.docs", "setuptools": "build-system.requires"}


def test_setup_cfg_install_requires_and_extras(tmp_path):
    write(tmp_path / "setup.cfg", "[options]\ninstall_requires =\n    attrs>=21\n    # comment\n    six\n"
                                  "[options.extras_require]\ntest =\n    pytest>=7\n")
    r = scan_repository(tmp_path)
    assert {d["name"] for d in r["declarations"]} == {"attrs", "six", "pytest"}
    assert next(d for d in r["declarations"] if d["name"] == "attrs")["line"] == 3


def test_setup_py_literal_analysed_but_never_executed(tmp_path):
    marker = tmp_path / "EXECUTED"
    write(tmp_path / "setup.py",
          f"from setuptools import setup\nopen({str(marker)!r}, 'w').write('x')\n"
          "setup(name='x', install_requires=['lxml>=4', 'idna'], extras_require={'t': ['pytest']})\n")
    r = scan_repository(tmp_path)
    assert not marker.exists()
    assert {d["name"] for d in r["declarations"]} == {"lxml", "idna", "pytest"}
    assert next(d for d in r["declarations"] if d["name"] == "lxml")["line"] == 3


def test_setup_py_dynamic_requirements_noted(tmp_path):
    write(tmp_path / "setup.py", "from setuptools import setup\nsetup(install_requires=read_reqs())\n")
    r = scan_repository(tmp_path)
    assert r["declarations"] == []
    assert any(e["code"] == "setup_py_dynamic" for e in r["errors"])


def test_venv_node_modules_generated_dirs_and_pyvenv_cfg_excluded(tmp_path):
    for d in (".venv", "venv", "node_modules", "build", "dist", "foo.egg-info", "patchproof-output"):
        write(tmp_path / d / "requirements.txt", "bad==1\n")
    write(tmp_path / "customenv" / "pyvenv.cfg", "home = x\n")
    write(tmp_path / "customenv" / "requirements.txt", "bad==1\n")
    write(tmp_path / "requirements.txt", "good==1\n")
    r = scan_repository(tmp_path)
    assert r["manifests_scanned"] == ["requirements.txt"]
    reasons = {e["path"]: e["reason"] for e in r["exclusions"]["excluded_directories_encountered"]}
    assert reasons["customenv"] == "virtual_environment"


def test_user_exclusion(tmp_path):
    write(tmp_path / "vendor" / "requirements.txt", "x==1\n")
    write(tmp_path / "requirements.txt", "y==1\n")
    assert scan_repository(tmp_path, exclude=("vendor",))["manifests_scanned"] == ["requirements.txt"]


def test_generated_reports_are_not_treated_as_manifests(tmp_path):
    write(tmp_path / "patchproof-report.json", '{"x": 1}')
    write(tmp_path / "requirements.txt", "y==1\n")
    assert scan_repository(tmp_path)["manifests_scanned"] == ["requirements.txt"]


def _conflict_tree(root):
    write(root / "requirements.txt", "pydantic==1.10.13\nz==1\n")
    write(root / "pyproject.toml", '[project]\nname="x"\ndependencies=["pydantic>=2"]\n')


def test_finding_ids_are_stable_and_independent_of_line_shifts(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _conflict_tree(a)
    _conflict_tree(b)
    write(b / "requirements.txt", "# extra comment shifts lines\n\npydantic==1.10.13\nz==1\n")
    ida = scan_repository(a)["findings"][0]["id"]
    assert ida == scan_repository(a)["findings"][0]["id"] == scan_repository(b)["findings"][0]["id"]
    assert ida.startswith("F-")


def test_distinct_findings_get_distinct_ids(tmp_path):
    write(tmp_path / "requirements.txt", "a==1\nb==1\n")
    write(tmp_path / "requirements-dev.txt", "a==2\nb==2\n")
    ids = [f["id"] for f in scan_repository(tmp_path)["findings"]]
    assert len(ids) == len(set(ids)) == 2


def test_json_output_is_deterministic_and_has_no_absolute_paths(tmp_path):
    _conflict_tree(tmp_path)
    out1, out2 = tmp_path.parent / "o1.json", tmp_path.parent / "o2.json"
    assert scanner_main(["--root", str(tmp_path), "--output", str(out1)]) == 0
    assert scanner_main(["--root", str(tmp_path), "--output", str(out2)]) == 0
    assert out1.read_bytes() == out2.read_bytes()
    text = out1.read_text()
    assert str(tmp_path) not in text
    data = json.loads(text)
    assert data["schema_version"] and "timestamp_policy" in data


def test_cli_bad_root_returns_nonzero(tmp_path, capsys):
    assert scanner_main(["--root", str(tmp_path / "missing"), "--output", str(tmp_path / "o.json")]) == 1


def test_cli_exit_2_on_parse_errors(tmp_path):
    write(tmp_path / "pyproject.toml", "[project\n")
    assert scanner_main(["--root", str(tmp_path), "--output", str(tmp_path / "o.json")]) == 2
