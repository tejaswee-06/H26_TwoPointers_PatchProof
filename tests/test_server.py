"""Integration tests for the local API server (scan → diagnosis → verification → capsule)."""
import http.client
import json
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from patchproof import server as srv
from conftest import write

HDR = {"X-PatchProof-Client": "1", "Content-Type": "application/json"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("PATCHPROOF_AI_ADAPTER", raising=False)
    from patchproof.ai import ollama_adapter
    monkeypatch.setattr(ollama_adapter, "OLLAMA_URL", "http://127.0.0.1:9/api/chat")  # hermetic: no local Ollama
    app = srv.App(tmp_path / "ws", None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.make_handler(app, 0))
    port = httpd.server_port
    httpd.RequestHandlerClass = srv.make_handler(app, port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    def call(method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        h = dict(HDR if method != "GET" else {})
        h.update(headers or {})
        if host:
            h["Host"] = host
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        raw = r.read()
        ctype = r.getheader("Content-Type") or ""
        data = json.loads(raw) if ctype.startswith("application/json") and raw else raw.decode("utf-8", "replace")
        c.close()
        return r.status, data
    call.app = app
    call.port = port
    yield call
    httpd.shutdown()
    httpd.server_close()


def wait_job(call, job_id, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st, data = call("GET", f"/api/jobs/{job_id}")
        assert st == 200
        if data["job"]["state"] not in ("queued", "running"):
            return data["job"]
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def make_repo(tmp_path):
    repo = tmp_path / "demo_repo"
    write(repo / "requirements.txt", "demo_dep==1.0\nrequests==2.31.0\n")
    write(repo / "pyproject.toml", '[project]\nname="demo"\ndependencies=["requests>=3"]\n')
    write(repo / "app.py", "import requests\n")
    return repo


def test_health_bundled_linkwatch_and_ai_pending(api):
    st, h = api("GET", "/api/health")
    assert st == 200 and h["ai_adapter"]["state"] == "UNAVAILABLE"
    assert "Ollama" in h["ai_adapter"]["reason"]
    st, runs = api("GET", "/api/runs")
    lw = [r for r in runs["runs"] if r["id"] == "bundled-linkwatch"][0]
    assert lw["verification_status"] == "VERIFIED_CHANGE" and lw["can_verify"] is False and lw["deletable"] is False
    st, d = api("GET", "/api/runs/bundled-linkwatch")
    assert st == 200
    assert d["artifacts"]["ai"] is None
    assert d["capsule"]["labels"]["ai_analysis"] == "AI PROPOSAL"
    assert any("ai_analysis artifact: not_provided" in n for n in d["capsule"]["missing_artifact_notices"])
    types = [c["type"] for c in d["artifacts"]["diagnosis"]["candidates"]]
    assert "runtime_import_incompatibility" in types
    assert "## Root-cause candidates" in d["capsule_markdown"]
    assert str(srv.PROJECT_ROOT) not in json.dumps(d)
    assert api("DELETE", "/api/runs/bundled-linkwatch")[0] == 403


def test_guards(api):
    assert api("GET", "/api/health", host="evil.example:80")[0] == 403
    assert api("POST", "/api/runs/scan", {"example": "compat_fixture"}, headers={"X-PatchProof-Client": "0"})[0] == 403
    assert api("POST", "/api/runs/scan", {"example": "x"}, headers={"Origin": "https://evil.example"})[0] == 403
    assert api("GET", "/api/runs/..%2F..%2Fetc")[0] == 404
    assert api("GET", "/api/runs/bundled-linkwatch/files/..%2Frun.json")[0] == 404
    st, html = api("GET", "/")
    assert st == 200 and "has not been built" in html


def test_scan_then_verify_without_change_is_not_verified(api, tmp_path):
    repo = make_repo(tmp_path)
    assert api("POST", "/api/runs/scan", {"root": "relative/path"})[0] == 422
    assert api("POST", "/api/runs/scan", {"root": str(tmp_path / "nope")})[0] == 422
    st, data = api("POST", "/api/runs/scan", {"root": str(repo)})
    assert st == 202
    job = wait_job(api, data["job"]["id"])
    assert job["state"] == "succeeded", job
    rid = job["run_id"]
    st, d = api("GET", f"/api/runs/{rid}")
    assert d["run"]["root_name"] == "demo_repo" and "root_path" not in d["run"]
    assert d["artifacts"]["scan"]["summary"]["finding_count"] == 1
    assert d["capsule"]["overall_status"] == "NOT_VERIFIED"
    assert d["capsule"]["verification_status"] == "NOT_RUN"
    # consent + config validation
    cfg = {"isolation": "none", "baseline": {"commands": [["{python}", "-c", "print('2 passed in 0.01s')"]]}}
    assert api("POST", f"/api/runs/{rid}/verify", {"config": cfg})[0] == 428
    assert api("POST", f"/api/runs/{rid}/verify", {"config": {"baseline": {"commands": []}}, "consent": True})[0] == 422
    assert api("POST", "/api/runs/bundled-linkwatch/verify", {"config": cfg, "consent": True})[0] == 409
    st, data = api("POST", f"/api/runs/{rid}/verify", {"config": cfg, "consent": True})
    assert st == 202
    job = wait_job(api, data["job"]["id"])
    assert job["state"] == "succeeded", job
    assert job["result"]["status"] == "TESTS_PASS_CHANGE_UNVERIFIED" and job["result"]["verified"] is False
    assert any(e["event"] == "command_finished" for e in job["events"])
    st, d = api("GET", f"/api/runs/{rid}")
    assert d["artifacts"]["verification"]["status"] == "TESTS_PASS_CHANGE_UNVERIFIED"
    assert d["capsule"]["overall_status"] == "NOT_VERIFIED"
    assert d["verify_config"]["target"] == "<TARGET>"
    st, md = api("GET", f"/api/runs/{rid}/files/dependency-exit-capsule.md")
    assert st == 200 and "TESTS_PASS_CHANGE_UNVERIFIED" in md
    assert api("DELETE", f"/api/runs/{rid}")[0] == 200
    assert api("GET", f"/api/runs/{rid}")[0] == 404


def test_verified_change_with_offline_wheels(api, tmp_path, wheelhouse):
    repo = tmp_path / "proj"
    write(repo / "requirements.txt", "demo_dep==1.0\n")
    write(repo / "check.py", "import demo_dep, sys\nprint('version', demo_dep.VERSION)\nsys.exit(0 if demo_dep.VERSION == '2.0' else 1)\n")
    st, data = api("POST", "/api/runs/scan", {"root": str(repo)})
    rid = wait_job(api, data["job"]["id"])["run_id"]
    pip = ["{python}", "-m", "pip", "install", "--no-index", "--find-links", str(wheelhouse), "-r", "requirements.txt"]
    cfg = {"isolation": "venv", "timeout_seconds": 300,
           "baseline": {"setup": [pip], "commands": [["{python}", "check.py"]]},
           "after": {"setup": [pip], "commands": [["{python}", "check.py"]]},
           "change": {"pip_install": ["demo_dep==2.0"], "pip_args": ["--no-index", "--find-links", str(wheelhouse)]}}
    st, data = api("POST", f"/api/runs/{rid}/verify", {"config": cfg, "consent": True})
    job = wait_job(api, data["job"]["id"])
    if job["result"] and job["result"]["status"] == "BLOCKED":
        pytest.skip("venv creation unavailable: " + "; ".join(job["result"]["status_reasons"]))
    assert job["result"]["status"] == "VERIFIED_CHANGE", job
    st, d = api("GET", f"/api/runs/{rid}")
    assert d["capsule"]["overall_status"] == "VERIFIED_CHANGE"
    assert d["artifacts"]["verification"]["change"]["environment_diff"] == [{"package": "demo-dep", "before": "1.0", "after": "2.0"}]


def test_cancel_verification_stops_process_and_cleans_up(api, tmp_path):
    repo = make_repo(tmp_path)
    st, data = api("POST", "/api/runs/scan", {"root": str(repo)})
    rid = wait_job(api, data["job"]["id"])["run_id"]
    cfg = {"isolation": "none", "timeout_seconds": 120,
           "baseline": {"commands": [["{python}", "-c", "import time; time.sleep(60)"]]}}
    st, data = api("POST", f"/api/runs/{rid}/verify", {"config": cfg, "consent": True})
    jid = data["job"]["id"]
    t0 = time.time()
    while time.time() - t0 < 30:
        j = api("GET", f"/api/jobs/{jid}")[1]["job"]
        if any(e["event"] == "command_started" and e.get("kind") == "command" for e in j["events"]):
            break
        time.sleep(0.2)
    workdir = j["events"][0].get("workdir_name")
    assert api("POST", f"/api/jobs/{jid}/cancel", {})[0] == 200
    job = wait_job(api, jid, timeout=40)
    assert job["state"] == "cancelled"
    assert time.time() - t0 < 40
    st, d = api("GET", f"/api/runs/{rid}")
    assert d["artifacts"]["verification"] is None  # nothing recorded for a cancelled run
    assert d["capsule"]["verification_status"] == "NOT_RUN"
    time.sleep(1)
    assert not (Path(tempfile.gettempdir()) / workdir).exists()


def test_import_malformed_legacy_and_ai(api, tmp_path):
    lw = srv.PROJECT_ROOT / "examples" / "linkwatch_artifacts"
    files = [{"name": n, "content": (lw / n).read_text(encoding="utf-8")} for n in ("patchproof-report.json", "patchproof-usage-report.json")]
    files.append({"name": "broken.json", "content": "{not json"})
    files.append({"name": "verification.json", "content": json.dumps({"verified": True, "after": {"passed": True}})})
    st, data = api("POST", "/api/import", {"files": files})
    assert st == 201
    assert any(p["file"] == "broken.json" for p in data["problems"])
    rid = data["run_id"]
    st, d = api("GET", f"/api/runs/{rid}")
    # legacy bare verified:true is never trusted
    assert d["capsule"]["overall_status"] == "NOT_VERIFIED"
    assert d["capsule"]["verification_assessment"].get("legacy") is True
    assert api("POST", "/api/import", {"files": [{"name": "x.json", "content": "nope"}]})[0] == 422
    # AI: invalid rejected, valid stored as proposal, never changes verification
    bad = api("POST", f"/api/runs/{rid}/ai", {"artifact": {"model": "x"}})
    assert bad[0] == 422 and bad[1]["validation"]["errors"]
    ai = {"model": "TEST-FIXTURE", "runtime": "none", "finding_ids": ["F-3C1708E248", "F-NOPE"], "analysis": "fixture",
          "options": [{"description": "a", "verification_commands": ["pytest"], "rollback": "r", "verified": True}],
          "recommended_option": 0, "uncertainties": []}
    st, val = api("POST", f"/api/runs/{rid}/ai", {"artifact": ai})
    assert st == 200
    w = " ".join(val["validation"]["warnings"])
    assert "F-NOPE" in w and "does not identify a Gemma model" in w and "cannot record verification" in w
    st, d = api("GET", f"/api/runs/{rid}")
    assert d["capsule"]["overall_status"] == "NOT_VERIFIED"
    assert d["ai_validation"]["option_states"][0]["status"] == "PROPOSED"
    assert d["ai_validation"]["option_states"][0]["verification_commands"][0]["status"] == "NOT_RUN"
    assert d["capsule"]["rollback"][0]["source"] == "AI PROPOSAL"
    st, bundle = api("GET", f"/api/runs/{rid}/ai-input")
    assert bundle["report_type"] == "ai_evidence_bundle" and bundle["findings"][0]["id"] == "F-3C1708E248"
    assert api("POST", f"/api/runs/{rid}/ai/run", {})[0] == 409  # Person 2's adapter installed but local Ollama is not running
    assert api("DELETE", f"/api/runs/{rid}/ai")[0] == 200
    assert api("GET", f"/api/runs/{rid}")[1]["artifacts"]["ai"] is None


def test_adapter_integration_point(api, monkeypatch):
    monkeypatch.setenv("PATCHPROOF_AI_ADAPTER", "fake_ai_adapter")
    st, h = api("GET", "/api/health")
    assert h["ai_adapter"]["state"] == "READY"
    st, data = api("POST", "/api/runs/bundled-linkwatch/ai/run", {})
    assert st == 202
    job = wait_job(api, data["job"]["id"])
    assert job["state"] == "succeeded", job
    st, d = api("GET", "/api/runs/bundled-linkwatch")
    assert d["artifacts"]["ai"]["model"] == "TEST-DOUBLE-not-a-model"
    assert d["capsule"]["labels"]["ai_analysis"] == "AI PROPOSAL"
    assert d["capsule"]["verification_status"] == "VERIFIED_CHANGE"  # from the real verification evidence only
    assert any("ignored" in w for w in d["ai_validation"]["warnings"])


def test_fs_listing(api, tmp_path):
    make_repo(tmp_path)
    st, data = api("GET", f"/api/fs?path={tmp_path}")
    assert st == 200 and any(e["name"] == "demo_repo" and e["has_manifest"] for e in data["entries"])
    assert api("GET", "/api/fs?path=relative")[0] == 422


def test_keepalive_post_without_body_read_does_not_corrupt_next_request(api):
    """Regression: a POST whose JSON body the route ignores must not leak into the next request."""
    import http.client as hc
    c = hc.HTTPConnection("127.0.0.1", api.port, timeout=30)
    c.request("POST", "/api/jobs/doesnotexist/cancel", body="{}", headers=HDR)
    r = c.getresponse(); r.read()
    assert r.status == 404
    c.request("GET", "/api/health")
    r = c.getresponse(); body = r.read()
    assert r.status == 200 and json.loads(body)["ok"] is True
    c.close()
