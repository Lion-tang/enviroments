# Python 3.9+ Compatibility Design

## Context

The deployment environment may provide only Python 3.9. The application source must therefore run on every supported CPython version from 3.9 upward, while the official standalone Windows and Linux artifacts must be built on Python 3.9 to establish the lowest interpreter baseline.

The standalone artifacts are produced with PyInstaller and include their own Python interpreter. Their runtime does not depend on the Python version installed on the target machine. Fixing the official build interpreter at Python 3.9 is therefore a reproducibility and compatibility decision, not a requirement that target machines install exactly Python 3.9.

## Goals

- Support running the backend source on CPython 3.9 and newer versions.
- Allow local source and artifact builds with any CPython version greater than or equal to 3.9.
- Build the official Windows x64, Linux x86_64, and Linux ARM64 artifacts with CPython 3.9.
- Continuously test the minimum supported interpreter so later changes cannot silently introduce newer-only syntax or runtime behavior.
- Preserve the existing API, frontend behavior, configuration, and SQLite database format.

## Compatibility Contract

The source compatibility contract is `Python >=3.9`. Local build scripts reject only Python versions older than 3.9 and invoke PyInstaller through the validated interpreter with `python -m PyInstaller`.

The official artifact contract is different: release workflows select CPython 3.9 explicitly. A developer may produce a local standalone artifact using a newer Python version, but that artifact embeds the newer interpreter and is not the canonical Python 3.9 release artifact.

Supporting Python 3.9 does not mean every future dependency release is assumed to remain compatible. Runtime and build dependencies remain pinned to versions tested by CI. PyInstaller is moved into a dedicated build requirements file and pinned to a tested 6.x version that supports Python 3.9.

## Source Changes

The current backend parses as Python 3.9 syntax except for one evaluated PEP 604 annotation in `backend/app/core/request_limits.py`:

```python
def _limit_for(self, scope) -> int | None:
```

It will use `Optional[int]`, which is valid on Python 3.9 without changing runtime behavior. No application logic, API model, or database model needs to change.

## Build Scripts

`build.bat` and `build.sh` perform an early interpreter check:

- Python 3.8 and older: stop with a clear `Python 3.9 or newer is required` message.
- Python 3.9 and newer: continue normally.

Both scripts use the same interpreter for version validation, dependency execution, and PyInstaller invocation. They do not require the interpreter to be exactly Python 3.9.

## Continuous Integration and Packaging

The Windows workflow uses `actions/setup-python` with Python 3.9 for the official executable. The two manylinux workflows use `/opt/python/cp39-cp39/bin/python` instead of the container distribution's unversioned `/usr/bin/python3`. Every packaging job prints and asserts its interpreter version before installing dependencies or running PyInstaller.

A compatibility test job runs the backend suite on Python 3.9 and a current newer interpreter. Python 3.9 is the blocking minimum-version check; the newer interpreter catches forward-compatibility regressions.

The existing platform-specific packaging behavior remains unchanged:

- Windows continues producing the Windows x64 directory artifact.
- Linux x86_64 continues compiling the PyInstaller bootloader in its manylinux container.
- Linux ARM64 continues using the existing manylinux ARM64 flow.

## Regression Protection

A source compatibility test parses backend Python files with the Python 3.9 grammar. This gives fast, explicit feedback if a later change adds syntax unavailable in 3.9, even when a developer runs the test suite on a newer local interpreter.

CI also performs a real import and the complete backend test suite under Python 3.9. Grammar parsing alone is insufficient because dependency imports and evaluated annotations can still fail at runtime.

## Documentation

The README and Linux deployment documentation state:

- Source development and execution require Python 3.9 or newer.
- Official standalone artifacts embed Python 3.9 and require no system Python installation.
- Locally built artifacts embed whichever supported interpreter performed the build.

All commands use `python -m pip` and `python -m PyInstaller` where practical so installation and execution target the same interpreter.

## Compatibility and Migration

This work does not change database schemas, persisted topology data, API payloads, or frontend assets. Existing SQLite databases remain directly compatible and require no migration.

## Verification

- Run the Python 3.9 grammar compatibility test across backend source and tests.
- Run the complete backend test suite on CPython 3.9.
- Run the complete backend test suite on the local newer CPython interpreter.
- Build the frontend production bundle.
- Validate each packaging workflow selects CPython 3.9 before invoking PyInstaller.
- Smoke-start generated artifacts in their native CI operating system when workflow support permits.

## Out of Scope

- Supporting Python 3.8 or older.
- Requiring local developers to use exactly Python 3.9.
- Making PyInstaller artifacts portable across operating systems or CPU architectures.
- Changing application features, APIs, or database schemas.
