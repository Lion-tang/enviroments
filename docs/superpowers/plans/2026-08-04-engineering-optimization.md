# Engineering Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve topology correctness and large-installation performance while preserving old SQLite databases and API compatibility.

**Architecture:** Network operations work from detached configuration snapshots and persist results in short database transactions. Streaming/context-managed I/O bounds memory and resource lifetimes. Bulk operations use small fixed worker pools and batch database writes.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2, SQLite WAL, Paramiko, pytest, Vue 3, Axios, Vite.

## Global Constraints

- Do not remove or rename existing database columns or API routes.
- Preserve the legacy Base64 file upload endpoint.
- Use UTC for persisted discovery and scheduler timestamps.
- Bound SSH and HTTP fan-out; never use unbounded `Promise.all` for server checks.

---

### Task 1: Safe topology snapshots

**Files:**
- Modify: `backend/infrastructure/ssh_client.py`
- Modify: `backend/app/core/topology_discovery.py`
- Modify: `backend/app/api/v1/routers/topology.py`
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/test_topology_discovery.py`

**Interfaces:**
- Produces: server scan dictionaries with `interfaces`, `error`, and `scan_complete`.
- Produces: switch scan dictionaries containing only `mac_map` and `error`.

- [ ] Write a test where an incomplete empty server scan preserves an existing link.
- [ ] Run `pytest tests/test_topology_discovery.py -v` and verify the new test fails by deleting the link.
- [ ] Check the remote command exit status and reject empty or malformed interface JSON.
- [ ] End the initial database read transaction before submitting SSH work.
- [ ] Defer `raw_output`, avoid unused relationship loads, use UTC, and clean legacy raw values idempotently.
- [ ] Run the topology tests and confirm all pass.

### Task 2: Bounded log storage

**Files:**
- Modify: `backend/app/core/audit_log.py`
- Modify: `backend/app/api/v1/routers/logs.py`
- Modify: `backend/app/api/v1/routers/switches.py`
- Test: `backend/tests/test_audit_log.py`

**Interfaces:**
- Produces: `append_json_log(path, payload, max_bytes, backup_count)` and memory-bounded `read_json_lines`.

- [ ] Write tests proving tail order, exact total, malformed-line handling, and size rotation.
- [ ] Run the audit-log tests and verify tail/rotation tests fail.
- [ ] Implement locked rotation and deque-based tail reads.
- [ ] Route server and switch log writers/readers through the shared helpers.
- [ ] Run the audit-log tests and confirm all pass.

### Task 3: SFTP lifecycle and streaming transfer

**Files:**
- Modify: `backend/infrastructure/sftp_client.py`
- Modify: `backend/app/api/v1/routers/files.py`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/components/ServerDetail.vue`
- Test: `backend/tests/test_sftp_client.py`

**Interfaces:**
- Produces: `sftp_connection(...)` context manager, `stream_file(...)`, and `upload_stream(...)`.
- Produces: authenticated frontend `files.download()` and multipart `files.upload()`.

- [ ] Write tests proving SSH and SFTP clients close on success and failure and stream uploads are chunked.
- [ ] Run the SFTP tests and verify they fail because the lifecycle API does not exist.
- [ ] Implement the context manager and stream helpers, including explicit connection/auth/banner timeouts.
- [ ] Snapshot server credentials in a short database session.
- [ ] Add multipart upload and streaming download while retaining the legacy Base64 route with a limit.
- [ ] Replace browser Base64 reads and unauthenticated anchor downloads.
- [ ] Run SFTP tests and the frontend production build.

### Task 4: Bounded bulk status checks

**Files:**
- Modify: `backend/app/api/v1/schemas.py`
- Modify: `backend/app/api/v1/routers/servers.py`
- Modify: `backend/app/core/scheduler.py`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/views/ServerList.vue`
- Modify: `frontend/src/views/ServerFavorites.vue`
- Test: `backend/tests/test_status_checks.py`

**Interfaces:**
- Produces: `POST /servers/status/batch` accepting optional `server_ids` and returning `results`, `online`, and `total`.

- [ ] Write tests for partial worker failures and one-transaction persistence.
- [ ] Run the status tests and verify they fail because the batch service is absent.
- [ ] Extract a bounded status worker/service and use it from the API and scheduler.
- [ ] Replace both frontend `Promise.all` implementations with the batch API.
- [ ] Run status tests and the frontend build.

### Task 5: Startup and regression verification

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `docs/README_DEPLOY_LINUX.md`
- Test: `backend/tests/test_database_compatibility.py`

**Interfaces:**
- Produces: idempotent startup behavior for an old SQLite schema.

- [ ] Write an old-schema database compatibility test and verify it fails if required migrations are absent.
- [ ] Add async component loading and document the single-process scheduler requirement plus WAL-safe backups.
- [ ] Run `pytest -v`, `python -m compileall app infrastructure`, and `npm run build`.
- [ ] Run `git diff --check` and inspect the final diff for accidental API or schema breaks.
