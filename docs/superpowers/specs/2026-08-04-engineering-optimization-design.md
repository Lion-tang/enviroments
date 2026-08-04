# Engineering Optimization Design

## Goal

Improve topology discovery, resource stability, file-transfer memory usage, log growth, and bulk status checks without breaking existing SQLite databases or existing API consumers.

## Compatibility constraints

- Existing SQLite files remain usable in place; no column or table is removed.
- Existing topology, server, log, and legacy Base64 upload response shapes remain valid.
- Schema maintenance is idempotent and clears obsolete `network_links.raw_output` values only.
- Timestamps written by background and discovery jobs use UTC consistently.

## Topology discovery

Discovery snapshots only the server and switch fields required for SSH, then ends the read transaction before network I/O. Server scans return an explicit `scan_complete` value. A server's stale links are deleted only after a complete interface scan; command failures, empty command output, malformed JSON, and SSH failures preserve the last known topology.

Switch MAC output is parsed immediately and discarded. ORM reads defer the legacy `raw_output` column and avoid loading unused relationships. Writes occur in one short transaction.

The in-process lock remains as a fast guard. Deployment documentation will state that the embedded scheduler requires one application process; a future multi-worker deployment must move scheduling to a designated process or distributed lease.

## Resource lifecycle and file transfer

Database reads for file operations return a plain connection configuration and close the session before SFTP begins. An SFTP context manager owns and closes the SSH client, SFTP channel, and transport.

Downloads yield fixed-size chunks from the remote file. New uploads use multipart form data and copy the uploaded stream to SFTP in chunks. The existing Base64 endpoint remains available for old clients but receives a size limit. Frontend downloads use authenticated Axios blob requests and uploads keep the browser `File` object rather than creating Base64 copies.

## Logs and status checks

Log writes rotate by size with a bounded number of backups. Reads keep only the requested tail in memory while still returning an exact line count.

Bulk server status checks run through a backend endpoint with bounded concurrency and one batched database update transaction. The periodic status job uses the same bounded worker pattern. Frontend list and favorites views call the batch endpoint once instead of creating an unbounded `Promise.all`.

## Frontend loading

Large views are loaded with Vue async components so unopened tabs do not contribute their component code to the initial application chunk. Existing UI behavior and routes remain unchanged.

## Error handling and verification

- A topology command failure is data-preserving, not an empty successful snapshot.
- SFTP resources close after success, error, cancellation, and generator termination.
- Upload size validation returns HTTP 413.
- Bulk status results include per-server failures without aborting the entire batch.
- Backend unit/integration tests, Python compilation, frontend production build, and an old-schema SQLite migration test must pass.
