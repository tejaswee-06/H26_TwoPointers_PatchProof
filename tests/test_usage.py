import json

from conftest import write
from patchproof.usage import trace_usage, main as usage_main, analyze_source

MAPPING = {"yaml": ["PyYAML"], "PIL": ["Pillow"], "google": ["protobuf", "google-auth"],
           "attr": ["attrs"], "attrs": ["attrs"], "requests": ["requests"], "numpy": ["numpy"]}


def _project(tmp_path, reqs, sources):
    write(tmp_path / "requirements.txt", reqs)
    for name, text in sources.items():
        write(tmp_path / name, text)
    return tmp_path


def _by_pkg(report):
    return {p["package"]: p for p in report["packages"]}


def test_normal_import_with_file_and_line_evidence(tmp_path):
    _project(tmp_path, "requests==2.0\n", {"app/main.py": "import os\n\nimport requests\n"})
    p = _by_pkg(trace_usage(tmp_path, mapping=MAPPING))["requests"]
    assert p["usage_status"] == "import_observed"
    hit = p["imports_found"][0]
    assert (hit["file"], hit["line"], hit["import_name"], hit["kind"]) == ("app/main.py", 3, "requests", "import")


def test_aliased_import(tmp_path):
    _project(tmp_path, "numpy\n", {"a.py": "import numpy as np\n"})
    hit = _by_pkg(trace_usage(tmp_path, mapping=MAPPING))["numpy"]["imports_found"][0]
    assert hit["alias"] == "np" and "as np" in hit["statement"]


def test_from_import_and_submodule(tmp_path):
    _project(tmp_path, "requests\n", {"a.py": "from requests.adapters import HTTPAdapter\n"})
    hit = _by_pkg(trace_usage(tmp_path, mapping=MAPPING))["requests"]["imports_found"][0]
    assert hit["kind"] == "from_import" and hit["import_name"] == "requests.adapters"


def test_distribution_name_differs_from_import_name(tmp_path):
    _project(tmp_path, "PyYAML>=6\nPillow\n", {"a.py": "import yaml\nfrom PIL import Image\n"})
    r = _by_pkg(trace_usage(tmp_path, mapping=MAPPING))
    assert r["pyyaml"]["usage_status"] == "import_observed" and r["pyyaml"]["candidate_import_roots"] == ["yaml"]
    assert r["pillow"]["usage_status"] == "import_observed" and r["pillow"]["mapping_source"] == "installed_metadata"


def test_distribution_with_multiple_import_names(tmp_path):
    _project(tmp_path, "attrs\n", {"a.py": "import attr\n", "b.py": "import attrs\n"})
    p = _by_pkg(trace_usage(tmp_path, mapping=MAPPING))["attrs"]
    assert p["candidate_import_roots"] == ["attr", "attrs"]
    assert {h["file"] for h in p["imports_found"]} == {"a.py", "b.py"}


def test_no_static_import_is_a_lead_not_proof(tmp_path):
    _project(tmp_path, "requests\n", {"a.py": "import os\n"})
    r = trace_usage(tmp_path, mapping=MAPPING)
    p = _by_pkg(r)["requests"]
    assert p["usage_status"] == "no_static_import_found"
    assert "not proof" in p["interpretation"]
    assert r["review_leads"][0]["id"].startswith("U-") and r["review_leads"][0]["package"] == "requests"
    assert "unused" in " ".join(r["limitations"]).lower()


def test_mapping_unavailable_when_not_installed(tmp_path):
    _project(tmp_path, "some-uninstalled-pkg\n", {"a.py": "import os\n"})
    p = _by_pkg(trace_usage(tmp_path, mapping={}))["some-uninstalled-pkg"]
    assert p["usage_status"] == "mapping_unavailable" and p["mapping_source"] == "name_heuristic"


def test_name_heuristic_hit_is_labelled_as_guess(tmp_path):
    _project(tmp_path, "some-pkg\n", {"a.py": "import some_pkg\n"})
    p = _by_pkg(trace_usage(tmp_path, mapping={}))["some-pkg"]
    assert p["usage_status"] == "import_observed" and "guess" in p["interpretation"]


def test_dynamic_import_literal_recorded_and_nonliteral_marks_incomplete(tmp_path):
    _project(tmp_path, "requests\nnumpy\n", {"a.py": "import importlib\nimportlib.import_module('requests')\nname='x'\n__import__(name)\n"})
    r = trace_usage(tmp_path, mapping=MAPPING)
    p = _by_pkg(r)
    assert p["requests"]["imports_found"][0]["kind"] == "dynamic_literal"
    assert p["numpy"]["usage_status"] == "analysis_incomplete"
    assert r["unresolved_dynamic_imports"] == {"a.py": 1}
    assert r["summary"]["analysis_complete"] is False


def test_syntax_error_reported_without_crash(tmp_path):
    _project(tmp_path, "requests\nnumpy\n", {"bad.py": "def (:\n", "good.py": "import requests\n"})
    r = trace_usage(tmp_path, mapping=MAPPING)
    assert r["parse_errors"][0]["file"] == "bad.py" and r["parse_errors"][0]["line"] == 1
    assert _by_pkg(r)["requests"]["usage_status"] == "import_observed"
    assert _by_pkg(r)["numpy"]["usage_status"] == "analysis_incomplete"


def test_undecodable_source_reported(tmp_path):
    _project(tmp_path, "requests\n", {})
    (tmp_path / "bin.py").write_bytes(b"\xff\xfe\x00\x00import requests")
    assert trace_usage(tmp_path, mapping=MAPPING)["parse_errors"]


def test_excluded_directories_not_scanned(tmp_path):
    _project(tmp_path, "requests\n", {".venv/lib/x.py": "import requests\n", "node_modules/a.py": "import requests\n",
                                      "build/b.py": "import requests\n"})
    r = trace_usage(tmp_path, mapping=MAPPING)
    assert r["python_files_scanned"] == 0
    assert _by_pkg(r)["requests"]["usage_status"] == "no_static_import_found"


def test_relative_imports_ignored(tmp_path):
    _project(tmp_path, "requests\n", {"pkg/a.py": "from . import requests\nfrom .requests import x\n"})
    assert _by_pkg(trace_usage(tmp_path, mapping=MAPPING))["requests"]["usage_status"] == "no_static_import_found"


def test_source_is_never_executed(tmp_path):
    marker = tmp_path / "RAN"
    _project(tmp_path, "requests\n", {"a.py": f"open({str(marker)!r}, 'w')\nimport requests\n"})
    trace_usage(tmp_path, mapping=MAPPING)
    assert not marker.exists()


def test_report_is_deterministic_and_has_no_absolute_paths(tmp_path):
    _project(tmp_path, "requests\nnumpy\n", {"a.py": "import requests\n"})
    o1, o2 = tmp_path.parent / "u1.json", tmp_path.parent / "u2.json"
    # real installed metadata path (no supplied mapping) must still be deterministic
    assert usage_main(["--root", str(tmp_path), "--output", str(o1)]) == 0
    assert usage_main(["--root", str(tmp_path), "--output", str(o2)]) == 0
    assert o1.read_bytes() == o2.read_bytes()
    assert str(tmp_path) not in o1.read_text()
    assert json.loads(o1.read_text())["report_type"] == "usage"


def test_uses_shared_scan_representation(tmp_path):
    _project(tmp_path, "requests\n", {"a.py": "import requests\n"})
    from patchproof.scanner import scan_repository
    scan = scan_repository(tmp_path)
    assert trace_usage(tmp_path, mapping=MAPPING, scan=scan)["scan_status"] == "completed"


def test_analyze_source_line_numbers(tmp_path):
    f = write(tmp_path / "m.py", '"""doc"""\nimport a\nif True:\n    import b\n')
    imports, err, _ = analyze_source(f, "m.py")
    assert err is None and [(i["module"], i["line"]) for i in imports] == [("a", 2), ("b", 4)]
