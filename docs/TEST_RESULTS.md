# Test results — integrated build v0.3.0

Recorded on 2026-10-15 in a Linux container (Python 3.13.16, Node 22.22.0, Chromium via Playwright), from a
**clean extraction of the delivery ZIP**: fresh `.venv` + `pip install -r requirements-dev.txt`, fresh `npm ci`.

## Summary

| Check | Command | Result |
|---|---|---|
| Engine + server tests | `python -m pytest -q -rs` | **151 passed, 0 failed, 0 skipped** (124 original Person 1 tests unchanged + 27 new) |
| Static check | `python -m pyflakes patchproof tests` | clean |
| Dashboard unit tests | `npm test` | **9 passed, 0 failed** |
| Production build | `npm run build` | success (JS 299 kB / 90 kB gzip, CSS 77 kB / 18 kB gzip) |
| Browser end-to-end walkthrough | Playwright script against `python -m patchproof.server` (below) | **13 / 13 passed** |
| Responsive layout | every workspace page at 360, 390, 820, 1024 px with all panels expanded; screenshots at 390, 820, 1440 px | no clipped content after fixes |
| Engine-offline mode | `vite preview` with the engine stopped | offline guidance shown; local JSON viewing and export work |
| Dev proxy | `vite preview` → engine on 8765 | GET and POST (capsule rebuild) through the proxy work |

## Browser walkthrough (real engine, real data)

1. Landing streams the live LinkWatch evidence chain from the engine; capability tabs switch; CTA opens the LinkWatch run.
2. LinkWatch overview: 5-stage chain with **Gemma 4 pending**; root-cause candidate "jinja2 2.11.3 imports `soft_unicode`…" marked *Supported by verification*.
3. Findings: 6 items; search, expand evidence (`requirements.txt:5`), export `F-3C1708E248.json`, kind tabs.
4. Usage tracing: 14 packages; status filter (5 *mapping unavailable*); import evidence `linkwatch/report.py:3`.
5. Migration, missing-AI scenario: pending state, *Run Gemma 4 analysis* disabled, evidence bundle downloads, an invalid `ai-analysis.json` is rejected with schema errors.
6. Capsule: JSON export (`overall_status: VERIFIED_CHANGE`, `labels.diagnosis: HYPOTHESIS`), Markdown export contains the root-cause section, JSON inspector and Markdown source tabs.
7. **Live scan** of `examples/compat_fixture` → new run → overview.
8. **Live verification**: run button disabled until consent; live command timeline; real `pip install` into two fresh venvs; result `VERIFIED_CHANGE` (baseline `check_import.py` exit 1 with `ImportError: cannot import name 'soft_unicode'`, `pip check` exit 0; after `MarkupSafe==2.0.1` all commands exit 0).
9. Diagnosis rebuilt from that live verification; overview shows 4 stages ready + Gemma 4 pending.
10. **Cancel**: a second verification cancelled mid-run ends as *Cancelled*; the previous record is kept.
11. Import of LinkWatch scan + usage JSON creates a `NOT_RUN` run; inline delete confirmation removes it.
12. Theme switch, reduced motion and keyboard focus persist.
13. No uncaught page errors (one expected 422 from the rejected AI file is excluded).

The walkthrough passed 13/13 on the final package. During the second-to-last clean-room pass, steps 8–10 failed once
with a visibility timeout and passed on the immediate rerun against the same build; the cause was not identified
(the live steps depend on PyPI downloads). Treat the live-verification step as network-dependent.

Additional browser checks run during development: drafting a verification from an AI option (requirement pins
extracted, JSON editor round-trip) using a schema-shaped **UI test fixture** that was labelled as not model output and
is not shipped.

## Bugs found by testing and fixed

| Found by | Bug | Fix |
|---|---|---|
| Browser E2E | Keep-alive HTTP: a POST whose body the route ignored corrupted the next request (`501 Unsupported method ('{}GET')`) | Server always consumes the request body; regression test `test_keepalive_post_without_body_read…` |
| Browser E2E | Import result disappeared because the page remounted when the selected run changed | Runs page no longer keyed by run id |
| Browser E2E | Deleting the selected run triggered a 404 fetch (a stale URL-sync effect re-selected the deleted run) | Switch runs before deleting; URL sync now reacts only to URL changes |
| Screenshots | Root-cause reasoning column and mobile pages clipped (grid min-content widths) | `minmax(0, 1fr)` tracks, wrapping guards; re-verified at 360–1024 px |
| Artifact audit | Bundled LinkWatch verification output contained a Windows user name via pytest's `tmp_path` | Redacted in the bundled copy; engine now scrubs temp dir, home dir and `pytest-of-<user>` (new test) |
| Review | Windows registry can serve `.js` as `text/plain`, breaking module scripts | Explicit MIME types in the server |

## Not run / untested

* **Anything on Windows** (CMD commands, venv `Scripts\python.exe` path, `taskkill` cancellation). The LinkWatch artifacts themselves came from a Windows run by Person 1's teammate.
* **Real Gemma 4 inference** — no adapter or model was supplied. Only the integration path was tested, with a labelled test double (`tests/fake_ai_adapter.py`).
* Scanning/verifying the actual LinkWatch repository in this environment (repository not supplied; its artifacts are bundled).
* Screen-reader walkthrough and automated WCAG audit; speech recognition and synthesis (headless browser has none).
* Safari and Firefox; only Chromium was automated.

## Addendum — Person 2 integration (v0.4.0), run in a Linux sandbox

* `python -m pytest -q`: **189 passed** (151 previous + 28 P2 AI tests + 10 integration tests; Ollama mocked, no network).
* `npm test`: 9 passed. Edited JSX files syntax-checked with esbuild. **`npm run build` was not run here** (the sandbox cannot reach the npm registry) — run `npm install && npm run build` before the demo.
* Real-HTTP smoke test: `migration_agent` engine mode against a stand-in Ollama HTTP server produced `ai-analysis.json` + `ai-runtime-proof.json`; the server reports `UNAVAILABLE` with the reason when Ollama is not running.
* **Not run:** inference against a real Gemma 4 model. P2's own recorded real run is in `examples/linkwatch_ai_output/`.
