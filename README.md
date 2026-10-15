# PatchProof — Evidence Before Upgrades

PatchProof is a local-first dependency maintenance tool. It scans a Python repository's manifests and source,
correlates failures into candidate root causes, hands a bounded evidence bundle to a local Gemma 4 model for
migration options, proves (or disproves) a change by running your own commands before and after it in disposable
environments, and exports everything as a **Dependency Exit Capsule** (JSON + Markdown).

Everything runs on `127.0.0.1`. No cloud service, no paid API, no telemetry.

| Definition-of-done step | State in this build |
|---|---|
| Scan (manifests, findings with stable IDs and source lines) | **Working** — Person 1 engine, in the dashboard and CLI |
| Evidence-backed diagnosis | **Working** — new `patchproof/diagnose.py`; every candidate is a labelled hypothesis |
| Local Gemma 4 analysis | **Working** — Person 2's Ollama adapter (`patchproof/ai/`) is plugged into the engine. Needs a local Ollama with the Gemma 4 model pulled; without it the dashboard shows `UNAVAILABLE` with the reason and generates nothing. Output is always `AI PROPOSAL` / `PROPOSED`, commands `NOT_RUN`, and now includes `diagnostic_hypotheses`. ([docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md)) |
| Independent verification | **Working** — consent-gated, cancellable, disposable copy + fresh venv per phase |
| JSON + Markdown capsule | **Working** — built by the engine, exported from the dashboard |

---

## 1. Requirements

* Windows 10/11, macOS or Linux
* **Python 3.11+** (`python --version`)
* **Node.js 20+** and npm (`node --version`) — only needed to build the dashboard
* Internet access only for `pip install` / `npm install`, and for verification runs whose setup commands download packages

## 1b. Local Gemma 4 (Person 2's adapter)

```cmd
ollama serve                         :: if not already running
ollama pull gemma4:e2b-it-q4_K_M     :: default model; override with PATCHPROOF_MODEL
```

Optional env vars: `PATCHPROOF_MODEL`, `OLLAMA_URL` (default `http://127.0.0.1:11434/api/chat`). Then use **Run Gemma 4 analysis**
on the Migration page, or the CLI:
`python -m patchproof.ai.migration_agent out\patchproof-report.json --usage out\patchproof-usage-report.json --verification out\verification.json`
(writes `ai-analysis.json` + `ai-runtime-proof.json`). The LinkWatch sample project is in `examples/linkwatch_project`, with P2's real
recorded output in `examples/linkwatch_ai_output`. P2's notes: `docs/person2/`.

## 2. Install and start (Windows CMD)

Run these from the folder that contains this README:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt

cd frontend
npm install
npm run build
cd ..

python -m patchproof.server
```

The server prints `PatchProof 0.4.0 — local dashboard at http://127.0.0.1:8765/` and opens your browser.
Stop it with **Ctrl+C**. Options: `--port 8765`, `--workspace .patchproof-workspace`, `--no-browser`.

> Usage tracing maps distributions to import names using the metadata of the Python environment that runs the
> server. For the most accurate mapping, start the server from an environment where the scanned project's
> dependencies are installed; otherwise packages are labelled `mapping_unavailable` (a review lead, never "unused").

### Development mode (hot reload)

Two Command Prompts:

```cmd
:: terminal 1 — engine/API
.venv\Scripts\activate
python -m patchproof.server --no-browser

:: terminal 2 — dashboard with hot reload (proxies /api to 127.0.0.1:8765)
cd frontend
npm run dev
```

Open http://127.0.0.1:5173.

### macOS / Linux

Same steps with `python3 -m venv .venv` and `source .venv/bin/activate`.

## 3. Test and build

```cmd
.venv\Scripts\activate
python -m pytest -q

cd frontend
npm test
npm run build
```

`pytest` needs no internet; a few tests create real virtual environments from locally built wheels (≈1 minute).
Results recorded for this delivery: [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md).

## 4. Command line (no dashboard)

```cmd
python -m patchproof.run --root C:\path\to\LinkWatch --out-dir out
python -m patchproof.run --root C:\path\to\LinkWatch --out-dir out --verify-config verify-config.json [--ai ai-analysis.json]
python -m patchproof.diagnose --scan out\patchproof-report.json --usage out\patchproof-usage-report.json --verification out\verification.json --output out\diagnosis.json
```

Scan-only is the default; repository commands run **only** when `--verify-config` is given. Config format and exit
codes: [docs/person1/PERSON1_RUNBOOK.md](docs/person1/PERSON1_RUNBOOK.md) and [PERSON1_JSON_CONTRACTS.md](docs/person1/PERSON1_JSON_CONTRACTS.md).

## 5. Architecture

```
 Browser (React 18 + Vite build, served by the engine)
   │  fetch /api/*  (same origin; mutating calls carry X-PatchProof-Client: 1)
   ▼
 patchproof/server.py  — stdlib ThreadingHTTPServer on 127.0.0.1 only
   ├─ scan job (thread)      → scanner.scan_repository → usage.trace_usage → diagnose.diagnose → capsule.build_capsule
   ├─ verify job (process)   → python -m patchproof.verify --config … --progress   (cancellable process tree)
   │                            progress lines "PATCHPROOF_PROGRESS {json}" on stderr → live timeline
   ├─ AI job (thread)        → ai_bridge.run_adapter(bundle) → patchproof.ai.analyze → local Ollama (Gemma 4)
   ├─ import                 → classify + validate JSON artifacts, re-derive verification status
   └─ workspace/runs/<id>/   → run.json, patchproof-report.json, patchproof-usage-report.json,
                                verification.json, ai-analysis.json, diagnosis.json,
                                dependency-exit-capsule.json/.md, verify-config.json, verification.log
```

**Boundaries kept from the work division.** Person 1's engine establishes facts (scan, usage, verification);
`diagnose.py` only correlates those artifacts. Person 2's Gemma 4 adapter is a pluggable module the server discovers;
its output is validated and always shown as `AI PROPOSAL` / `PROPOSED`, with suggested commands `NOT_RUN`. Person 3's
dashboard presents, never decides: verification status comes from the capsule's `verification_assessment`, which
re-derives status from evidence and ignores a bare `verified: true`.

**Safety model**
* Loopback only; requests with a non-loopback `Host` (DNS rebinding) or foreign `Origin` are rejected; state-changing calls need a custom header, so other websites cannot trigger them.
* Repository commands run only after explicit consent to the exact command list (checkbox resets whenever the config changes; the server returns `428` without `consent: true`).
* Every phase runs in a disposable copy with its own venv (`isolation: venv`); `isolation: none` is labelled *not isolated* and refuses `pip install`. Isolation is not a sandbox: setup commands have network access.
* Artifacts never store absolute paths: verification output is scrubbed (`<WORKDIR>`, `<TARGET>`, `<TMP>`, `<HOME>`, `pytest-of-<user>`); the API returns folder names only.

**API** (all JSON): `GET /api/health`, `GET /api/runs`, `POST /api/runs/scan`, `GET|DELETE /api/runs/<id>`,
`POST /api/runs/<id>/rescan|rebuild|verify`, `GET /api/runs/<id>/verify-template`, `POST|DELETE /api/runs/<id>/ai`,
`POST /api/runs/<id>/ai/run`, `GET /api/runs/<id>/ai-input`, `GET /api/runs/<id>/files/<artifact>`, `POST /api/import`,
`GET /api/jobs/<id>`, `POST /api/jobs/<id>/cancel`, `GET /api/fs?path=`.

## 6. Dashboard tour

| Page | What it shows (all from real artifacts) |
|---|---|
| Landing | Hero with the live LinkWatch evidence chain streamed from the engine; how it works; evidence labels |
| Overview | Five-stage evidence chain, metrics, evidence-based health checks (no invented score), severity distribution, leading cause, before/after, scan history |
| Scans & runs | Folder path + folder browser, fixture quick-scan, JSON import, live progress with cancel, history with rescan/delete |
| Findings | Manifest findings (F-) and usage leads (U-), search / voice search, severity filter, evidence blocks with file:line, observed vs inferred, export |
| Usage tracing | Package → import evidence, status filters, mapping source, parse errors, interpretation notes |
| Root cause | Candidate causes: observed evidence by source, inference, uncertainty, discriminating checks (NOT_RUN); parsed failure chains |
| Migration | Compatibility evidence, Gemma 4 pending/ready state, evidence bundle, AI import, options with risks/tests/rollback |
| Verification lab | Form or JSON config, consent review, live command timeline, cancel, before/after comparison, env diff, isolation |
| Exit Capsule | Artifact states, missing notices, rendered Markdown, Markdown source, JSON inspector, JSON/Markdown export, rebuild |

Dark and light themes, reduced motion (also follows the OS), larger text, higher contrast, keyboard navigation and
skip link, read-aloud and voice search where the browser supports them. Layouts are tested at 360–1440 px.

## 7. Evidence labels

| Label | Meaning |
|---|---|
| `OBSERVED` | Read from repository files or captured command output |
| `HYPOTHESIS` | Candidate cause derived from observed evidence — not proven |
| `AI PROPOSAL` / `PROPOSED` | Model output; not applied, not verified |
| `NOT_RUN` | A suggested command PatchProof has not run |
| `VERIFIED` | Only for a recorded `VERIFIED_CHANGE` with baseline, change and after-run evidence |
| `BLOCKED` | Missing or could not run — nothing substituted |

## 8. Bundled data

* `examples/linkwatch_artifacts/` — real engine output for the organizer's LinkWatch repo, produced on a teammate's Windows machine (see its README). Shown as the read-only run *LinkWatch — imported engine artifacts*. The OS user name inside a pytest temp path was redacted to `<user>`; no result field was changed.
* `examples/compat_fixture/` — tiny synthetic project reproducing the Jinja2 2.11.3 / MarkupSafe 3.x mechanism. Scan and verify it live from **Scans & runs → Scan the fixture** (verification downloads packages from PyPI).

## 9. Known limitations

* **Gemma 4 is not integrated** (Person 2's adapter was not supplied). The end-to-end flow runs with the AI stage visibly pending.
* Windows: the Python code paths include Windows handling (venv `Scripts\python.exe`, `taskkill /T` for cancellation, MIME fixes), but **nothing in this delivery was executed on Windows**; run the checklist in [docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md) first.
* Verification needs the repository folder on the machine running the engine; imported/bundled runs are read-only.
* Root-cause diagnosis pattern-matches captured output (ImportError / ModuleNotFoundError / pytest summaries); other failures are listed as unclassified.
* A cancelled verification on Windows is force-killed; its temporary folder is removed by the server afterwards (best effort).
* No security-advisory data is consulted; "review" severity is not a vulnerability rating.

## 10. More documentation

* [docs/CHANGES.md](docs/CHANGES.md) — files changed and features implemented
* [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) — actual test results (passed / failed / skipped / untested)
* [docs/DEMO_CHECKLIST.md](docs/DEMO_CHECKLIST.md) — 3-minute judge demo and rehearsal checklist
* [docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md) — Gemma 4 adapter contract
* [docs/person1/](docs/person1/) and [docs/person3/](docs/person3/) — the original Person 1 and Person 3 reports, kept for history
