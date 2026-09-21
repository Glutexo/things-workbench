# Synchronization and history boundary

**No cloud or native synchronization operation was performed to produce these docs.** The public package's initial scope is read-only. A private predecessor's deployment or cloud success cannot establish public-package write support.

## Physical evidence

S-STRUCT verifies `BSSyncronyMetadata(uuid TEXT PRIMARY KEY, value BLOB)`, task `notesSync`, `TMTombstone`, and opaque `experimental`/metadata/extension fields. These names and declarations do not expose a complete synchronization protocol. No sync BLOB, settings value, account key, note history, command body or tombstone record was read.

P-SYNC source review shows private validators treating synchronization metadata as part of native operation state, with separate pending-history checks. Those private protocols are not copied into this project or presented as an implementation contract.

## Distinct claims

| Claim | What would be needed; not proved by schema inspection |
| --- | --- |
| Local model changed | Authorized mutation and exact target readback |
| Native history staged | Native transaction/history evidence, including preserved preexisting state |
| Remote service accepted | Genuine authenticated remote receipt; a synthetic ACK is insufficient |
| Local publication succeeded | Transactional source-bound publication plus fresh readback |
| Remote readback agrees | Independent remote retrieval with declared scope |
| Another device displays it | Separate authorized device/UI observation |

A locally edited task row is not a staged native operation. Pending-zero alone is not proof of every required remote effect. A read-only status report cannot erase evidence of an earlier network request.

## Unknowns and preservation

The complete BLOB grammar, entity/property revisions, compression, note-base representation, retry/ACK protocol, deletion retention, account state and conflict semantics are not specified here. `notesSync` must not be treated as a complete synopsis of visible notes or remote history. Clearing history, reconstructing BLOBs or deleting tombstones to pass a check is outside scope.

The private predecessor workflow distinguishes capture, semantic review, merged state, delivery review, a bounded upload attempt and receipt-bound recovery. This is background for architectural separation, not a usable public workflow or standing authorization. Specific private policies, receipts, runtime seals and exceptions are deliberately not published. P-WORKFLOW.
