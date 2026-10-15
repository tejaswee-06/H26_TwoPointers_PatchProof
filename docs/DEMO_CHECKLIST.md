# Demo checklist (judges and teammates)

## Before the demo (once, on the demo laptop)

- [ ] `python --version` is 3.11+ and `node --version` is 20+.
- [ ] Install exactly as in README §2; `python -m pytest -q` passes; `cd frontend && npm test && npm run build` passes.
- [ ] `python -m patchproof.server` opens http://127.0.0.1:8765 and the top bar shows **Engine online**.
- [ ] **Windows smoke test (never run by us):** Scans & runs → *Scan the fixture* → Verification lab → tick consent → *Run verification*. Expect `VERIFIED_CHANGE` in about a minute (needs PyPI). Then start another run and press *Cancel* — it should end as *Cancelled* and keep the previous record.
- [ ] If you have the LinkWatch folder: scan it, then verify with the commands from `examples/linkwatch_artifacts/verify-config.linkwatch.json` (loaded via *Load config*).
- [ ] If Person 2's adapter is ready: put it in `patchproof/ai/`, restart, and confirm the Migration page says *Adapter: ready*.

## Three-minute script

| Time | Do | Say |
|---|---|---|
| 0:00 | Landing page — point at the live evidence panel, click **Inspect the LinkWatch case** | "Upgrades fail at runtime even when metadata checks pass. PatchProof connects manifests, source usage, AI reasoning and verification." |
| 0:25 | Overview → evidence chain; **Findings** → expand `F-3C1708E248` | "Two separate things: a manifest conflict — pyproject says `pydantic>=2`, requirements pins `1.10.13` — observed, not proven harmful…" |
| 0:45 | **Root cause** → first candidate | "…and a reproduced runtime failure: Jinja2 2.11.3 imports `soft_unicode`, which MarkupSafe 3.0.4 no longer has. `pip check` passed in the same environment. Observed on the left, inference and uncertainty on the right." |
| 1:10 | **Migration** | "Gemma 4 receives this bounded evidence bundle. The model never marks its own answer verified." (If the adapter is not connected: "Person 2's adapter plugs in here; we show the pending state instead of faking output.") |
| 1:35 | **Verification lab** (LinkWatch, or the fixture run you verified live) | "Baseline: 1 failed, 9 passed. Declared change MarkupSafe 2.0.1, applied in a fresh venv. After: 10 passed. Commands, exit codes and output are all here." |
| 2:20 | **Exit Capsule** → Preview → **Export Markdown** and **Export JSON** | "Another developer gets the evidence, candidate causes, proposals, verification record, limitations and rollback path." |

## Things to point out if asked

- Verification only runs after consent to the exact command list; each phase uses a disposable copy and its own venv.
- Bare `verified: true` is never trusted — import `examples/linkwatch_artifacts` files or a hand-edited verification.json and the capsule re-derives the status.
- Missing artifacts are shown as missing (`not_provided`), never filled in.
- Everything is local: the API refuses non-loopback hosts and cross-origin requests.
