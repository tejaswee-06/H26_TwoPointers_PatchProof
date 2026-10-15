# LinkWatch artifacts (bundled evidence)

These four files were produced by the Person 1 engine against the organizer's **LinkWatch** repository on a teammate's
Windows 11 machine (Python 3.12.1, isolated venvs). They are shipped unchanged so judges can inspect the real case
without the repository:

| file | what it records |
|---|---|
| `patchproof-report.json` | 3 manifests, 27 declarations, finding `F-3C1708E248`: `pydantic>=2` (pyproject.toml:17) vs `pydantic==1.10.13` (requirements.txt:5) |
| `patchproof-usage-report.json` | 14 declared packages, 9 with observed imports, 5 review leads (`mapping_unavailable`) |
| `verification.json` | `VERIFIED_CHANGE`: baseline `pytest -q` 1 failed / 9 passed (`ImportError: cannot import name 'soft_unicode' from 'markupsafe'`) while `pip check` passed; after `MarkupSafe==2.0.1` → 10 passed |
| `dependency-exit-capsule.json/.md` | the capsule as generated on that machine (before root-cause diagnosis existed) |

The dashboard seeds them as the read-only run **"LinkWatch — imported engine artifacts"** and rebuilds the diagnosis and
capsule from them on first start. They were not re-run in this environment. `MarkupSafe==2.0.1` is a diagnostic
workaround, not a recommended long-term fix.

`verify-config.linkwatch.json` is the configuration used for that run, with the teammate's local path replaced by a
placeholder. To reproduce: scan your LinkWatch folder in the dashboard and use these commands in the verification lab.
