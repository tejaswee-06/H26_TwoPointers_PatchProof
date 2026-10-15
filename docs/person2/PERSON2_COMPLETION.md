# Person 2 Completion Notes — PatchProof

## Scope completed in this archive

- Strengthened local-only Ollama/Gemma 4 migration-advisor prompt.
- Added structured `diagnostic_hypotheses` to the AI output contract. Each hypothesis records supporting evidence, contradicting evidence, a conservative confidence level, and tests that could distinguish the hypothesis.
- Improved manifest evidence collection to resolve manifest entries that do not include line numbers, such as dependencies in `pyproject.toml`.
- Corrected usage-evidence selection so the model receives package-specific entries rather than an accidentally broad parent report.
- Added repository-root path checks before reading manifest evidence.
- Hardened schema validation for finding IDs and structured hypotheses.
- Added offline tests for schema validation, adapter behavior, manifest evidence, usage evidence, and path handling.
- Updated runtime-proof documentation.

## Tests run

- AI-focused tests: 28 passed.
- Repeated the AI-focused test suite 25 times in this workspace: all 25 runs passed.
- Python compilation check (`compileall`): passed.

## Environment limitation

The full project suite could not be independently rerun in this workspace because the environment lacks LinkWatch runtime dependencies (the first failure was `ModuleNotFoundError: appdirs`) and network access prevented installing them. The previously reported Windows full-suite result from the supplied project is not represented as a new test result here.

## Before committing on the development machine

1. Activate the project's existing virtual environment.
2. Run `python -m pytest -q`.
3. Run `python -m patchproof.scanner`.
4. Run `python -m patchproof.usage`.
5. Ensure local Ollama is running with the configured Gemma 4 model.
6. Run `python -m patchproof.ai.migration_agent`.
7. Inspect `patchproof-ai-advice.json` and `patchproof-ai-runtime-proof.json`.
8. Confirm the output contains `diagnostic_hypotheses` and retains `PROPOSED` / `NOT_RUN`.
9. Coordinate the updated AI JSON contract with Person 3 before integrating the dashboard.

No new model inference result has been fabricated in this archive. The runtime-proof JSON is generated only by a successful local inference run.
