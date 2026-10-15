# PatchProof — Gemma 4 Runtime Proof

## Purpose
PatchProof uses a locally hosted Gemma 4 model through Ollama to generate evidence-grounded dependency migration proposals.

## Runtime
- Model ID: `gemma4:e2b-it-q4_K_M`
- Runtime: Ollama, local HTTP API
- Default API endpoint: `http://127.0.0.1:11434/api/chat`
- Inference command: `python -m patchproof.ai.migration_agent`
- Generated advice: `patchproof-ai-advice.json`
- Runtime proof: `patchproof-ai-runtime-proof.json`

The runtime-proof JSON records the model response excerpt, Ollama version when available, inference duration when returned, and a summary of evidence supplied to the analysis. The advice JSON includes structured diagnostic hypotheses with supporting evidence, contrary evidence, confidence, and discriminating tests.

## Reproduce
1. Activate the project's Python virtual environment.
2. Ensure Ollama is running locally and the configured model is available.
3. Run `ollama list` to inspect installed models.
4. Run `ollama --version` to record the installed runtime version.
5. Run `python -m patchproof.scanner`.
6. Run `python -m patchproof.usage` if the usage tracer is available.
7. Run `python -m patchproof.ai.migration_agent`.
8. Inspect `patchproof-ai-advice.json` and `patchproof-ai-runtime-proof.json`.

## Optional Captured Test Evidence
If actual captured output from the Jinja2/MarkupSafe reproduction is available, save it as `patchproof-test-evidence.txt` in the repository root. Include the command, environment details, exit code, and relevant error/test summary.

Do not invent or reconstruct output from memory. If the file is absent, the migration agent records that test-failure evidence was unavailable.

## Trust Boundary
Gemma proposes migration options. It does not apply changes and cannot declare a migration successful. Actual verification must be performed by the separate verification workflow. A passing baseline test suite does not prove that a proposed dependency migration works.
