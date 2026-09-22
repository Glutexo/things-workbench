# Private transactional publication rehearsal (development)

This is an **experimental private-copy capability**, not true-live support or a
release approval. It transfers an unchanged, fully verified completed Stage-2
wording packet into an **existing tool-created private target**, in place.
Independent safety acceptance remains separate; default synthetic tests and
historical Stage-2 native evidence do not certify the entire publication matrix.

## Explicit lifecycle

All parent directories must already be owned/private. These are example paths,
not defaults or permission to use a live store.

```sh
things-workbench publication create-target --completed-packet /private-owned/packet --new-root /private-owned/target
things-workbench publication prepare --completed-packet /private-owned/packet --target-root /private-owned/target --name first
things-workbench publication preview --run /private-owned/target/runs/first
things-workbench publication rehearse --run /private-owned/target/runs/first --approve EXACT_PUBLICATION_DIGEST
things-workbench publication status --run /private-owned/target/runs/first
```

`create-target` verifies completed provenance before taking a SQLite backup of
its BEFORE. It never adopts an arbitrary existing file. `prepare` requires exact
logical BEFORE. Preview derives full escaped strings from verified data and
binds the destination identity, source packet, BEFORE/AFTER, package resources,
engine identity and policy. A copy approval cannot approve publication. Test
approval is not human consent to modify a live task.

`rehearse` is a real write to that existing private target, not a dry run. Only
validated TMTask updates and BSSyncronyMetadata updates/inserts are transferred.
No native helper is invoked during publication; no history is invented or
cleared, no general SQL input is accepted. Existing native wording scope and
the narrow empty-root/single-prior same-target note rule remain unchanged.
Mutable targets and recovery copies are never importable Stage-2 suppliers.
Use accepted immutable Stage-2 outputs for subsequent native candidate lineage.

## Transaction and durability

Only **DELETE journal mode** is supported here. WAL/unknown modes and preexisting
sidecars refuse before the publication writer opens; the target mode is never
converted. WAL support is not claimed. The read-only SQLite minimum elsewhere
in this project is not write certification. The publisher currently gates the
observed 3.53.4 and 3.54.0 engines on Darwin, additionally binding the actual
interpreter, extension, loaded SQLite image, dependency information, source ID,
compile options and OS. A standalone image is hashed; an OS shared-cache image
is explicitly UUID/OS-bound, not represented as a fictional on-disk hash.

Lock order is the permanent managed-target lock, then that target's immutable
registry/run records. All runs targeting that physical DB share this authority.
A missing lock/registry is lost authority, never empty clearance. This is not
an adapter to any production registry. Ordinary SQLite writers are separately
serialized by BEGIN IMMEDIATE. Process checks detect Things at individual
moments; they do **not** enforce a no-consumer window or prevent app startup.
An unavailable or timed-out process census never means stopped. The API raises
a sanitized domain refusal; pre-intent CLI create/prepare/rehearse returns 2
without creating intent or changing the target. After intent, quarantine and
commit uncertainty remain in force, including when census failure prevents
fresh rollback verification.

The writer verifies full BEFORE on its own connection. While it holds the
reservation, a separate read-only target connection backs up into a new exclusive
private destination. The reader closes before target DML. Backup integrity/full
BEFORE, file fsync, Darwin F_FULLFSYNC and parent-directory fsync precede DML.
No same-writer backup, target replacement, sidecar deletion, manual checkpoint,
REPLACE or table-wide rewriting is used. Target synchronous=EXTRA and
fullfsync=ON are read back. Event files use fsync plus parent-directory fsync.
The space policy requires a 4-GiB reserve and caps target main size at 256 MiB;
SQLite progress and backup callbacks impose a cooperative transaction deadline.
These are not guarantees against physical power loss or faulty storage.

Full typed AFTER and integrity are checked on the writer. Source/runtime/preview
bindings and metadata-only target identity are rechecked before explicit SQL
COMMIT. Raw target main/SHM hash reads are forbidden while target SQL handles
are active: closing such a descriptor can release POSIX SQLite locks. Fresh
readback must match AFTER before the terminal receipt and append-only resolution.
Unrelated tables, WITHOUT ROWID state, sqlite_sequence and row identities remain
part of the full fingerprint. Existing read-only DELETE-reader failures on the
observed system SQLite remain safe refusals; no ro-to-rw fallback is used.

## Uncertainty and recovery

A durable target-associated guard precedes the publication writer. Event files
form an append-only hash chain; the independent guard survives failed receipts.
Errors after commit invocation are uncertain, not promises of rollback. An
ordinary precommit rollback is called verified only after fresh BEFORE readback.
Both retain quarantine until explicitly assessed/resolved.

`status` reads receipts/metadata only, never SQLite. It therefore reports history
and quarantine, **not current target content**. To authorize an owned-target
assessment, including possible SQLite hot-journal recovery:

```sh
things-workbench publication recovery-preview --run /private-owned/target/runs/first --name assessment --authorize-owned-recovery
things-workbench publication reconcile --assessment /private-owned/target/runs/first/assessment.json --approve EXACT_RECOVERY_DIGEST
things-workbench publication restore-copy --run /private-owned/target/runs/first --new-root /private-owned/recovery
```

Assessment and resolution acquire a current writer reservation. Exact BEFORE
or AFTER can be recorded without DML or native replay; neither proves historical
commit certainty (ABA is possible). OTHER, identity drift or missing/corrupt
required evidence retains quarantine. Recovery currently requires a durable
verified backup; interruptions before backup completion need manual review.
`restore-copy` creates a **new** nonimportable recovery copy and verifies full
BEFORE. In-place restoration/compensation is deliberately unsupported. Foreign
postcommit changes are never overwritten with the backup.

`publication publish-live` unconditionally returns
`LIVE_PUBLICATION_SEALED_DISABLED` before any target access. There is no force,
environment or caller assertion override. This release does not provide cloud,
credentials, scheduler, application launch/kill, sync ACK or UI visibility.
Path/ACL/physical checks detect ordinary drift; they do not provide isolation
against root or a hostile same-UID process.

## Hardening boundaries and finite work limits

Prepared runs retain a separate exact preparation binding. Receipt-only status
validates that binding, the retained Stage-2 preview/manifest, exact typed policy,
engine and identities. Once started, intent, registry and every event must refer
to the same envelope/approval; terminal history must retain its backup and exact
recovery assessment. Missing, partial, corrupt or contradictory authority blocks
new work. A resolved run is historical: later legitimate publications do not
invalidate it merely because the target no longer equals its AFTER. Repeated
reconciliation refuses before appending an event. Old runs without the new
preparation binding are unsupported; their receipts are not rewritten or migrated.

Process-wide coordination registers tool-managed SQLite file lifetimes before
connect through close, including nested scopes, snapshot readers, backups and
recovery writers. Raw-read check/open/close is serialized with registration;
active main/sidecar aliases refuse before payload reads, across tool threads.
This includes plist, Mach-O and package-resource readers. Metadata inspection is
not a payload read. Arbitrary unmanaged same-process I/O and hostile same-UID
filesystem replacement remain outside this coordination guarantee.

The current conservative caps are refusal boundaries, not supported-size claims:

| Resource | Bound |
|---|---|
| Outer create/prepare/preview/rehearse/recovery/restore operation | 120 seconds cooperative, shared by nested provenance/runtime work |
| Raw input file | 256 MiB |
| Aggregate payload/encoded-row work per outer operation | 8 GiB, repeated checks count again |
| Snapshot | 500,000 rows including metadata; 256 MiB encoded row content |
| Cumulative snapshot rows per outer operation | 8,000,000 |
| Ordinary JSON record | 4 MiB (4,194,304 bytes), nesting depth 64 on read |
| Explicit native-runtime JSON record | 16 MiB (16,777,216 bytes), nesting depth 64 on read |
| Input/derived transfer plan | 1 MiB |
| Events per run / runs per target | 128 / 256 |
| Runtime inventory traversal | 4,096 paths per traversal |
| Native dependency traversal / supplier ancestry | depth 64 / depth 16 |
| File-lifetime coordination acquisition | 5 seconds |
| Publication SQLite busy timeout | 1 second |

Only the explicit `record_kind='native-runtime'` read/write policy selects the
16-MiB cap; filenames never select it. Both paths validate the existing exact
runtime envelope/source/artifact schema. Runtime verification still recomputes
and compares the complete dependency closure and all existing source/runtime
bindings; a stored receipt is not execution authority by itself. The cap covers
the observed roughly 11.3-MB, 20-image / 15,379-edge closure with finite headroom,
without pruning dependency fields. All other records retain the 4-MiB cap.
Record reads and durable writes charge the shared cumulative byte budget;
the existing deadline, path, dependency-depth and row limits are unchanged.

Header inspection reads at most 100 bytes, not the whole target. Backup callbacks,
SQLite progress callbacks and per-record/row checks share the outer budget;
nested checks do not restart it. Snapshot format is unchanged; caller transactions
and savepoints remain caller-owned. Snapshot helpers own the connection's progress
handler slot (they clear it rather than restoring an arbitrary caller handler).
Expired handlers are disabled before owned rollback and nested cleanup closes
handles even on failure. Limits do not preempt an OS filesystem/fsync call or
provide a hard memory ceiling: a single SQLite row/JSON serialization is allocated
before encoded size is checked. Exhaustion is a refusal and can leave a retained
incomplete run requiring review; it is not permission to remove history or raise
limits in place. Receipt-only status does not open SQLite and does not establish
current target contents.

Synthetic SQLite tests and mocked-native lifecycle fixtures cover these repairs.
Final genuine native transfer/lineage, complete signal/fsync/VFS fault coverage and
independent exact-byte review remain separate acceptance gates. No live, WAL,
cloud, export or in-place-restore capability is added.
