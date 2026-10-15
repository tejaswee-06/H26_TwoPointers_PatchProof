# Gemma 4 integration (Person 2's adapter — connected)

PatchProof ships **no model** and never generates analysis text. Person 2's adapter (`patchproof/ai/`) calls a **local Ollama**
Gemma 4 model. If Ollama is down or the model is not pulled, the dashboard shows `UNAVAILABLE` with the reason (or `NOT_CONNECTED`
if the adapter module itself is missing). Nothing is substituted.

Wiring: `ai_bridge.run_adapter(bundle)` → `patchproof.ai.analyze(bundle)` → `ollama_adapter.generate_migration_advice(findings, context)`
→ P2's `schemas.validate_advice` (strict, with one self-correcting retry) → `ai_bridge.validate_ai_artifact` → capsule.
The bundle's F-/U-/D- items are all valid `finding_ids`.

## 1. Adapter contract (implemented by `patchproof/ai/__init__.py`)

Create `patchproof/ai/__init__.py` (or any importable module and set `PATCHPROOF_AI_ADAPTER=<module>`):

```python
def status() -> dict:                        # optional, shown in the dashboard
    return {"model": "<exact Gemma 4 model id>", "runtime": "<local runtime + version>", "ready": True}

def analyze(bundle: dict, timeout_seconds: int = 300) -> dict:
    """Call the LOCAL Gemma 4 runtime with `bundle` and return the agreed AI schema."""
    ...
```

Restart `python -m patchproof.server`. The Migration page's **Run Gemma 4 analysis** button becomes active,
the engine calls `analyze()` in a background job, validates the result and rebuilds the capsule.

## 2. Input: the evidence bundle

`GET /api/runs/<run>/ai-input` (also the **Evidence bundle for Gemma 4** button) returns
`report_type: "ai_evidence_bundle"`, built by `patchproof/ai_bridge.py::build_evidence_bundle`:

| key | content |
|---|---|
| `findings` | scanner findings: `id` (F-…), type, severity, package, title, observed, inferred, evidence (file, line, excerpt) |
| `usage_review_leads` | usage leads (U-…) |
| `root_cause_candidates` | diagnosis candidates (D-…): title, support, packages, observed texts, inferred, uncertainties |
| `failing_output` | error lines + failing test IDs from verification (bounded to 4 000 chars) |
| `verification` | status, reasons, declared change, environment diff, baseline/after summaries |
| `instructions`, `response_schema` | the rules below and the expected output shape |

No whole files, no absolute paths, no repository dump.

## 3. Output schema (playbook §4)

```json
{ "model": "exact-model-id", "runtime": "ollama-local",
  "diagnostic_hypotheses": [{ "hypothesis": "...", "supporting_evidence": ["..."], "contradicting_evidence": ["..."],
                              "confidence": "low|medium|high", "discriminating_tests": ["..."] }],   // P2 addition
  "decision_status": "PROPOSED", "verification_status": "NOT_RUN",                                    // stamped by the adapter
  "finding_ids": ["F-…", "U-…", "D-…"], "analysis": "reasoning grounded in the bundle",
  "options": [{ "description": "...", "benefits": ["..."], "risks": ["..."], "files_to_change": ["..."],
                "verification_commands": ["..."], "rollback": "..." }],
  "recommended_option": 0, "uncertainties": ["..."] }
```

`patchproof/ai_bridge.py::validate_ai_artifact` enforces it:

* **Errors (artifact rejected):** missing/empty `model`, `runtime`, `analysis`; `options` not an array; wrong field types; `recommended_option` out of range.
* **Warnings (stored, shown in the UI):** model id without "gemma"; `finding_ids` not present in the run's evidence; fewer than two options; missing rollback; any `verified` / `status` / `tests_passed` field (ignored — AI cannot record verification).

Every option is displayed as **PROPOSED**; every `verification_commands` entry as **NOT_RUN** unless the identical command
appears in the recorded `verification.json` (then the recorded exit code is shown, and the option is still PROPOSED).
Only the independent verification runner can produce `VERIFIED_CHANGE`.

## 4. Without the adapter

`ai-analysis.json` produced elsewhere can be imported on the Migration page (or `POST /api/runs/<run>/ai`);
it passes the same validation. The CLI equivalent is `python -m patchproof.run ... --ai ai-analysis.json`.
