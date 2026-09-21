# Safety and publication policy

## Read-only does not mean no filesystem interaction

Open an existing database with a properly encoded `file:` URI and `mode=ro`; enable `query_only` as defense in depth. Never use `immutable=1` for a store another process might change: it suppresses locking/change detection.[4]

A WAL reader can interact with shared-memory/locking state. `mode=ro` promises no SQL database updates, not byte-identical WAL/SHM files. Keep a read transaction short; long readers can impede checkpoint progress. Do not force a checkpoint, remove sidecars, or copy only the main file and treat that as a current consistent database.[3]

The structural recipe owns its connection and explicit `BEGIN`, and closes that transaction with SQL `ROLLBACK` in `finally`. It does not commit, migrate, repair, change journal mode, launch Things, load native helpers, read a keychain, or contact Things Cloud. Use a private SQLite backup only if separately necessary and authorized; do not put one in the public repository.

## Publication allowlist

Allowed after review:

- Application version/build and a scalar, strictly decoded Things database-format version.
- Table/column/index/constraint structure, including unknown/internal objects.
- Structural DDL and default expressions **only after literal review**.
- Synthetic examples with no user-derived identifiers or text.
- Generalized, explicitly scoped semantic observations.

Never publish databases or sidecars; task/checklist text or identifiers; contact records; settings values; sync BLOBs; note histories; account IDs; authentication tokens; private paths; operation receipts; request/response payloads; private native binaries/frameworks; or disassembly.

Names such as `uriSchemeAuthenticationToken` are schema identifiers, not secret values. Removing that column from the catalog would hide a safety risk. Conversely, structure-only extraction is not automatically anonymous: a custom trigger, view, default, object name or DDL comment can contain private literals. Review the entire export, not just data tables. Scanner success alone is not proof that arbitrary future exports are safe.

## No implied write/sync support

- Do not normalize unknown enum values or rebuild counters because their names look obvious.
- Do not clear sync history or tombstones to make a validation pass.
- Do not clone a recurring row into a new live occurrence with SQL.
- Do not use a matching schema or an integrity check as evidence of cloud correctness.
- Do not reuse a predecessor's approval, retry an uncertain upload, rewrite seals, or bypass a refused operation.

Future write work requires independent scope/authorization, exact source binding, transaction/concurrency control, fail-closed compatibility checks, preserved unknown state, rollback and verified readback. Any remote side effect needs its own receipt and recovery boundary.

## Evidence retained privately

The catalog review retains the executed query trace, app-plist provenance, raw structural capture, before/after source hashes, reproducibility checks and publication-audit results outside the repository under restricted permissions. No live application payloads were queried for this catalog; the one `Meta.databaseVersion` lookup is explicitly allowlisted. This is not a test of native writes, synchronization or UI behavior.

## Sources

[3] https://www.sqlite.org/wal.html
[4] https://www.sqlite.org/uri.html
