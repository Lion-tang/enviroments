# Python 3.9+ Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the backend source and local build entry points support Python 3.9 and newer while producing all official standalone artifacts with CPython 3.9.

**Architecture:** Keep application behavior unchanged and enforce compatibility at three boundaries: source annotations, automated tests, and packaging interpreter selection. Local scripts accept every interpreter at or above the minimum; official GitHub Actions builds select CPython 3.9 explicitly, and PyInstaller remains responsible for embedding that interpreter in standalone artifacts.

**Tech Stack:** CPython 3.9+, pytest, AST compatibility checks, PyInstaller 6.x, GitHub Actions, manylinux_2_34, PowerShell/batch, Bash.

## Global Constraints

- Backend source compatibility is `Python >=3.9`.
- Local builds reject only Python versions older than 3.9.
- Official Windows x64, Linux x86_64, and Linux ARM64 artifacts use CPython 3.9.
- Standalone artifacts continue embedding Python and require no system Python on the target machine.
- Existing APIs, frontend behavior, SQLite schema, and persisted data must not change.
- Python 3.8 and older remain unsupported.

---

### Task 1: Protect and Fix Python 3.9 Source Compatibility

**Files:**
- Create: `backend/tests/test_python_compatibility.py`
- Modify: `backend/app/core/request_limits.py:1-24`

**Interfaces:**
- Consumes: Python source files below `backend/app`, `backend/infrastructure`, and `backend/tests`.
- Produces: a pytest guard for the Python 3.9 grammar and PEP 604 annotations; `_limit_for(self, scope) -> Optional[int]` with unchanged return behavior.

- [ ] **Step 1: Write the failing compatibility tests**

```python
import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    BACKEND_ROOT / "app",
    BACKEND_ROOT / "infrastructure",
    BACKEND_ROOT / "tests",
)


def _python_files():
    return sorted(
        path
        for root in SOURCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def test_backend_parses_with_python39_grammar():
    for path in _python_files():
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=9,
        )


def test_annotations_do_not_use_pep604_union_operator():
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for annotation in _annotations(tree):
            if any(
                isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                for node in ast.walk(annotation)
            ):
                violations.append(f"{path.relative_to(BACKEND_ROOT)}:{annotation.lineno}")

    assert violations == [], "Python 3.10+ union annotations found: " + ", ".join(violations)
```

- [ ] **Step 2: Run the focused test and verify the current annotation fails**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_python_compatibility.py -v
```

Expected: `test_backend_parses_with_python39_grammar` passes and `test_annotations_do_not_use_pep604_union_operator` fails with `app/core/request_limits.py:24`.

- [ ] **Step 3: Replace the evaluated PEP 604 annotation**

Add the import and change only the return annotation:

```python
from typing import Optional


def _limit_for(self, scope) -> Optional[int]:
```

- [ ] **Step 4: Run the compatibility and request-limit tests**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_python_compatibility.py tests/test_request_limits.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the source compatibility guard**

```powershell
git add backend/tests/test_python_compatibility.py backend/app/core/request_limits.py
git commit -m "test: enforce Python 3.9 source compatibility"
```

---

### Task 2: Make Local Builds Version-Safe and Reproducible

**Files:**
- Create: `backend/requirements-build.txt`
- Modify: `build.bat:1-19`
- Modify: `build.sh:1-24`

**Interfaces:**
- Consumes: a `python` command on Windows or `python3` command on Linux/macOS with `sys.version_info >= (3, 9)`.
- Produces: local build scripts that reject unsupported interpreters and invoke the pinned `PyInstaller` module through the validated interpreter.

- [ ] **Step 1: Pin the artifact build tool**

Create `backend/requirements-build.txt`:

```text
pyinstaller==6.21.0
```

- [ ] **Step 2: Add the Windows minimum-version check and module invocation**

Before the frontend build in `build.bat`, add:

```bat
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.9 or newer is required.
    exit /b 1
)
```

Replace the direct executable call with:

```bat
python -m PyInstaller Enviroments.spec --noconfirm --clean --distpath "%~dp0dist" --workpath "%~dp0build"
```

Update the prerequisite comment to install `backend/requirements-build.txt`.

- [ ] **Step 3: Add the Bash minimum-version check and module invocation**

After `set -e` in `build.sh`, add:

```bash
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "ERROR: Python 3.9 or newer is required." >&2
  exit 1
fi
```

Replace the direct executable call with:

```bash
python3 -m PyInstaller Enviroments.spec --noconfirm --clean --distpath ../dist --workpath ../build
```

Update the prerequisite comment to install `backend/requirements-build.txt`.

- [ ] **Step 4: Validate local script behavior without running a full package build**

Run:

```powershell
python -c "import pathlib; text=pathlib.Path('build.bat').read_text(); assert 'sys.version_info >= (3, 9)' in text; assert 'python -m PyInstaller' in text"
python -c "import pathlib; text=pathlib.Path('build.sh').read_text(); assert 'sys.version_info >= (3, 9)' in text; assert 'python3 -m PyInstaller' in text"
python -c "from pathlib import Path; assert Path('backend/requirements-build.txt').read_text().strip() == 'pyinstaller==6.21.0'"
```

Expected: all three commands exit with status 0. Do not run the full local build here because it reinstalls frontend dependencies and creates large artifacts; official packaging is validated in Task 3.

- [ ] **Step 5: Commit local build support**

```powershell
git add backend/requirements-build.txt build.bat build.sh
git commit -m "build: support Python 3.9 and newer locally"
```

---

### Task 3: Test the Minimum Version and Build Official Artifacts with Python 3.9

> Correction after CI verification: the manylinux `/opt/python/cp39-cp39` interpreter is built without shared libpython and cannot be used by PyInstaller. Linux artifact jobs use AlmaLinux's system Python 3.9 plus `python3-devel` and assert `Py_ENABLE_SHARED == 1`.

**Files:**
- Create: `.github/workflows/test-python.yml`
- Modify: `.github/workflows/build.yml:22-70`
- Modify: `.github/workflows/build-linux.yml:43-61`
- Modify: `.github/workflows/build-linux-x86.yml:44-63`

**Interfaces:**
- Consumes: `backend/requirements.txt`, `backend/requirements-build.txt`, and the test created in Task 1.
- Produces: backend CI coverage on Python 3.9 and 3.12 plus official platform artifacts embedding CPython 3.9.

- [ ] **Step 1: Add the backend compatibility workflow**

Create `.github/workflows/test-python.yml`:

```yaml
name: Test Backend Python Compatibility

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-22.04
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        python-version: ['3.9', '3.12']

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: backend/requirements.txt

      - name: Install backend dependencies
        run: python -m pip install -r backend/requirements.txt

      - name: Run backend tests
        working-directory: backend
        run: python -m pytest -v

      - name: Smoke import application
        working-directory: backend
        run: python -c "import app.main"
```

- [ ] **Step 2: Pin the Windows official build to Python 3.9**

In `.github/workflows/build.yml`:

- Change `python-version` from `'3.11'` to `'3.9'`.
- Include both requirements files in the pip cache key.
- Add `python -c "import sys; print(sys.version); assert sys.version_info[:2] == (3, 9)"` before dependency installation.
- Install with `python -m pip install -r backend/requirements.txt -r backend/requirements-build.txt`.
- Build with `python -m PyInstaller Enviroments.spec ...`.

- [ ] **Step 3: Pin the Linux ARM64 official build to the system CPython 3.9 interpreter**

Inside the manylinux shell in `.github/workflows/build-linux.yml`, install and validate the distribution Python 3.9 with shared libpython:

```bash
dnf install -y python3 python3-pip python3-devel
ENVIROMENTS_PYTHON=/usr/bin/python3
"${ENVIROMENTS_PYTHON}" -c 'import sys, sysconfig; shared = sysconfig.get_config_var("Py_ENABLE_SHARED"); print(sys.version, shared); assert sys.version_info[:2] == (3, 9); assert shared == 1'
"${ENVIROMENTS_PYTHON}" -m pip install --upgrade pip
"${ENVIROMENTS_PYTHON}" -m pip install -r requirements.txt -r requirements-build.txt
"${ENVIROMENTS_PYTHON}" -m PyInstaller Enviroments.spec --noconfirm --clean --distpath ../dist --workpath ../build
```

Do not use `/opt/python/cp39-cp39`; it lacks the shared libpython required by PyInstaller.

- [ ] **Step 4: Pin the Linux x86_64 official build and preserve bootloader compilation**

Inside the manylinux shell in `.github/workflows/build-linux-x86.yml`, retain `gcc`, `zlib-devel`, and `binutils`, then use:

```bash
dnf install -y python3 python3-pip python3-devel gcc zlib-devel binutils
ENVIROMENTS_PYTHON=/usr/bin/python3
"${ENVIROMENTS_PYTHON}" -c 'import sys, sysconfig; shared = sysconfig.get_config_var("Py_ENABLE_SHARED"); print(sys.version, shared); assert sys.version_info[:2] == (3, 9); assert shared == 1'
"${ENVIROMENTS_PYTHON}" -m pip install --upgrade pip
"${ENVIROMENTS_PYTHON}" -m pip install -r requirements.txt
PYINSTALLER_COMPILE_BOOTLOADER=1 "${ENVIROMENTS_PYTHON}" -m pip install --no-binary pyinstaller -r requirements-build.txt
"${ENVIROMENTS_PYTHON}" -m PyInstaller Enviroments.spec --noconfirm --clean --distpath ../dist --workpath ../build
```

Keep the existing `libgcc_s.so.1` removal and GLIBC 2.34 validation unchanged.

- [ ] **Step 5: Validate workflow interpreter selection and dependency usage**

Run from the repository root:

```powershell
python -c "from pathlib import Path; w=Path('.github/workflows/build.yml').read_text(); assert \"python-version: '3.9'\" in w; assert 'requirements-build.txt' in w; assert 'python -m PyInstaller' in w"
python -c "from pathlib import Path; files=['.github/workflows/build-linux.yml','.github/workflows/build-linux-x86.yml']; texts=[Path(f).read_text() for f in files]; assert all('/usr/bin/python3' in t for t in texts); assert all('python3-devel' in t for t in texts); assert all('Py_ENABLE_SHARED' in t for t in texts)"
python -c "from pathlib import Path; w=Path('.github/workflows/test-python.yml').read_text(); assert \"['3.9', '3.12']\" in w; assert 'python -m pytest -v' in w; assert 'import app.main' in w"
```

Expected: all commands exit with status 0.

- [ ] **Step 6: Commit CI and packaging compatibility**

```powershell
git add .github/workflows/test-python.yml .github/workflows/build.yml .github/workflows/build-linux.yml .github/workflows/build-linux-x86.yml
git commit -m "ci: build official artifacts with Python 3.9"
```

---

### Task 4: Document the Compatibility Contract and Verify the Repository

**Files:**
- Modify: `README.md:28,105,215-219,273-289`
- Modify: `docs/README_DEPLOY_LINUX.md:18-25`

**Interfaces:**
- Consumes: the source, local scripts, and workflow behavior implemented in Tasks 1-3.
- Produces: operator-facing documentation that distinguishes source Python requirements from standalone artifact behavior.

- [ ] **Step 1: Update source and local-build documentation**

Change the README prerequisite from `Python 3.11 或更新版本` to `Python 3.9 或更新版本`. Replace unqualified pip and PyInstaller commands with:

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller Enviroments.spec --noconfirm --clean --distpath ../dist --workpath ../build
```

State that local scripts accept Python 3.9 and newer and that locally generated artifacts embed the interpreter used for that build.

- [ ] **Step 2: Update official workflow and offline-runtime documentation**

Describe all three official workflows as using CPython 3.9. For Linux, document the AlmaLinux system Python and `python3-devel` requirement that provides shared libpython to PyInstaller.

Add this runtime distinction to `docs/README_DEPLOY_LINUX.md`:

```markdown
- Official standalone packages embed CPython 3.9. The Python version installed on the offline machine is not used; no Node.js, pnpm, Python, or pip installation is required.
```

- [ ] **Step 3: Run the complete local verification suite**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m compileall -q app infrastructure tests
.\.venv\Scripts\python.exe -c "import app.main"
```

Expected: all backend tests pass, compilation exits 0, and the application imports without error.

Run from `frontend`:

```powershell
pnpm run build
```

Expected: Vite production build succeeds.

- [ ] **Step 4: Review the final diff and compatibility boundaries**

Run from the repository root:

```powershell
git diff --check
git status --short
rg -n "int \| None|python-version: '3.11'|PYTHON=/usr/bin/python3|pip install -r backend/requirements.txt pyinstaller" backend .github build.bat build.sh README.md docs/README_DEPLOY_LINUX.md
```

Expected: `git diff --check` is clean. The `rg` command returns no active source, workflow, script, or current documentation matches; historical design/plan documents are not included in this scan. The only unrelated untracked files remain runtime-generated database sidecars, the local pnpm store, and `frontend/pnpm-workspace.yaml`.

- [ ] **Step 5: Commit the documentation and verification result**

```powershell
git add README.md docs/README_DEPLOY_LINUX.md
git commit -m "docs: describe Python 3.9 compatibility"
```
