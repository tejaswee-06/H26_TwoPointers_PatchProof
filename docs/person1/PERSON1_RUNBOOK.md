# PERSON 1 RUNBOOK

Tested on Linux (Python 3.12.3). Windows CMD commands below follow the same code paths but **were not executed on Windows**; run the smoke checklist at the end first.

## 1. Install
Requires Python 3.11+.

Windows CMD:
```
cd PatchProof_Person1_Engine_QA
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```
Linux/macOS:
```
cd PatchProof_Person1_Engine_QA
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```
(`requirements-dev.txt` installs `packaging` and `pytest`. `pip install -e .[dev]` also works.) To use PatchProof on LinkWatch, copy `patchproof/` and `tests/` into the LinkWatch root (as the playbook intends) or keep this folder and point `--root` at LinkWatch.

## 2. Scan (read-only; never executes repository code)
```
python -m patchproof.scanner --root C:\path\to\LinkWatch --output out\patchproof-report.json
```
`--exclude NAME_OR_REL_PATH` (repeatable) skips extra directories. Exit codes: 0 ok, 1 root invalid, 2 manifest parse/read errors (report still written).

## 3. Usage tracing (static `ast`; never imports project code)
```
python -m patchproof.usage --root C:\path\to\LinkWatch --output out\patchproof-usage-report.json
```
Run it inside the environment where the project's dependencies are installed, otherwise import names cannot be mapped (`mapping_unavailable`).

## 4. Verification (runs ONLY the commands you put in the config)
Repository test commands can execute arbitrary project code. Create `verify-config.json` (example for LinkWatch — **you** must confirm the commands):
```
{
  "target": "C:\\path\\to\\LinkWatch",
  "isolation": "venv",
  "timeout_seconds": 600,
  "baseline": {
    "setup":    [["{python}", "-m", "pip", "install", "-r", "requirements.txt"]],
    "commands": [["{python}", "-m", "pip", "check"], ["{python}", "-m", "pytest", "-q"]]
  },
  "after": {
    "setup":    [["{python}", "-m", "pip", "install", "-r", "requirements.txt"]],
    "commands": [["{python}", "-m", "pip", "check"], ["{python}", "-m", "pytest", "-q"]]
  },
  "change": { "pip_install": ["MarkupSafe==2.0.1"] }
}
```
(Add `pytest` to the setup install if the project's requirements do not include it.) Then:
```
python -m patchproof.verify --config verify-config.json --output out\verification.json
```
How it works: the target is copied (excluding `.venv`, `.git`, caches) into a temp directory; a fresh venv is created per phase; `setup` commands run, the dependency state is captured, baseline commands run; the `after` phase repeats this, applies `change`, and runs the after commands. Your project directory and active environment are never modified. Temp directories are deleted unless `"keep_workdir": true`.
Ad-hoc alternative (commands as JSON arrays; CMD needs escaped quotes):
```
python -m patchproof.verify --target C:\path\to\proj --isolation none --baseline-cmd "[\"python\",\"-m\",\"pytest\",\"-q\"]" --output out\verification.json
```
`--isolation none` runs with the host interpreter inside the copied directory, is recorded as **not isolated**, and refuses `pip install`.
Exit codes: 0 VERIFIED_CHANGE · 1 failed · 2 blocked/not run · 3 tests pass but change unverified.

## 5. Capsule
```
python -m patchproof.capsule --scan out\patchproof-report.json --usage out\patchproof-usage-report.json --ai out\ai-analysis.json --verification out\verification.json --json out\dependency-exit-capsule.json --markdown out\dependency-exit-capsule.md
```
Omit `--ai` / `--verification` when those artifacts do not exist; the capsule records them as missing.

## 6. One command
```
python -m patchproof.run --root C:\path\to\LinkWatch --out-dir out [--verify-config verify-config.json] [--ai ai-analysis.json] [--strict]
```
Scan-only by default (no repository command is run). The output directory is excluded from scanning. Stage summary lines: `OK / WARN / FAIL / SKIPPED`. Exit code is nonzero if a stage fails (invalid root, crash, requested verification not `VERIFIED_CHANGE`, unreadable `--ai` file, or `--strict` with parse errors).

## 7. Tests
```
python -m pytest -q
```
No internet is needed. Four tests build a venv (about 1 minute total); they skip automatically if venv creation is unavailable.
The Jinja2/MarkupSafe fixture (`examples/compat_fixture`) needs PyPI access.

## 8. Troubleshooting
- `BLOCKED … Virtual environment creation failed`: install the `venv`/`ensurepip` component (on Debian/Ubuntu `python3-venv`).
- `BLOCKED … setup command failed`: read `baseline.setup[].stderr` in verification.json (usually network/index problems).
- `TESTS_PASS_CHANGE_UNVERIFIED`: tests passed, but no change was declared/applied with evidence, or the after-run did not repeat every baseline command.
- `mapping_unavailable`: package not installed in the interpreter running `patchproof.usage`.
- Windows: use `python`, not `python3`; quote JSON with `\"` in CMD, or use the config file.
- Why `pip check` can pass while an import fails: it validates declared metadata only. Jinja2 2.11.3 declares `MarkupSafe (>=0.23)` without an upper bound, so MarkupSafe 3.x satisfies it, yet `import jinja2` fails on `soft_unicode`.

## Windows CMD smoke checklist
1. `python --version` (3.11+). 2. venv + `python -m pip install -r requirements-dev.txt`. 3. `python -m pytest -q` (record result). 4. `python -m patchproof.run --root examples\compat_fixture\project --out-dir out\scan_only`. 5. With network: `python -m patchproof.run --root examples\compat_fixture\project --out-dir out\fixture --verify-config examples\compat_fixture\verify-config.json`. 6. Open `out\fixture\dependency-exit-capsule.md`. 7. Report any failure from the venv path (`Scripts\python.exe`) back — this path is untested.
