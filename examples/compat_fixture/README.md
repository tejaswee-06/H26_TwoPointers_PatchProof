# Jinja2 / MarkupSafe compatibility fixture (SYNTHETIC — not LinkWatch)

`project/` is a tiny stand-in that reproduces the *mechanism* described in the playbook
(Jinja2 2.11.3 importing `soft_unicode`, which MarkupSafe 3.x no longer provides). It is **not**
the organizer's LinkWatch repository and does not run LinkWatch's 10 tests.

Reproduce (needs network access to PyPI; creates two throw-away virtual environments):

    python -m patchproof.run --root examples/compat_fixture/project --out-dir examples/compat_fixture/sample_output --verify-config examples/compat_fixture/verify-config.json

`sample_output/` holds the output of one real run of exactly that command (Linux, Python 3.12.3).
It is sample data from the fixture; regenerate it on your machine rather than citing it as LinkWatch evidence.

Why `pip check` passes while the import fails: Jinja2 2.11.3 declares `MarkupSafe (>=0.23)` with no upper bound, so
the declared requirements are satisfied by MarkupSafe 3.x. `pip check` validates declared metadata only; it does not import modules.

The MarkupSafe 2.0.1 pin is a **diagnostic workaround**, not a recommended long-term fix. Upgrading Jinja2 to a release that
no longer uses `soft_unicode` is the kind of option that should be evaluated separately.
Rollback: the verification runs in disposable copies; nothing in `project/` or your own environment is modified.
