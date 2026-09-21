# Relationships, states, counters and ordering

Scope: the [observed DB29 layout](versions/things-3.24-build-32400506-db29/catalog.md). Physical facts: S-STRUCT. Semantic claims below are explicitly scoped source review or hypotheses; see [provenance](provenance.md).

## No declared SQL foreign keys

Every captured `foreign_key_list` is empty. Link-looking columns are not database-enforced references. Text types and indexes do not prove referential integrity, cascading deletion, uniqueness, or valid target kinds.

| Source column | Proposed target | Confidence / evidence |
| --- | --- | --- |
| TMChecklistItem.task | TMTask.uuid | Observed/source-reviewed owner check, P-STATUS |
| TMTask.project | TMTask.uuid, project role | Observed/source-reviewed, P-REL |
| TMTask.heading | TMTask.uuid, heading role | Observed/source-reviewed, P-REL |
| TMTask.rt1_repeatingTemplate | TMTask.uuid, RT1 template role | Observed/source-reviewed, P-RECURRENCE |
| TMTask.area | TMArea.uuid | Hypothesis; direct/inherited area semantics not established here |
| TMTask.contact | TMContact.uuid | Hypothesis; current use unknown |
| TMTaskTag.tasks / tags | TMTask.uuid / TMTag.uuid | Observed/source-reviewed creation validator, P-REL |
| TMAreaTag.areas / tags | TMArea.uuid / TMTag.uuid | Hypothesis, naming only |
| TMTag.parent | TMTag.uuid | Hypothesis; cycles and hierarchy rules unverified |
| TMTombstone.deletedObjectUUID | Unspecified object identifier | Hypothesis; no single target table certified |

The association tables have no declared primary key or unique pair constraint. Do not deduplicate them on the assumption that SQL already enforces a set. Repeated rows, orphan links and cycles were not queried in this exercise.

## Scoped state values

| Field | Source-reviewed interpretation | Limit |
| --- | --- | --- |
| TMTask.type | 0 task; 1 project; 2 heading | P-REL; preserve other values as unknown |
| TMTask.status | 0 open; 2 canceled; 3 completed | P-STATUS; no claim for 1 or other values |
| TMChecklistItem.status | 0 open; 2 canceled; 3 completed | P-STATUS; independent child state |
| TMTask.start | 1 Anytime; 2 scheduled | P-DATE; not a complete enum or UI selection formula |
| TMTask.trashed | Ordinary validators require 0 for nontrashed targets | P-STATUS; deletion lifecycle not fully established |

Do not adopt historical cancellation mappings that disagree with the reviewed contracts. The current source explicitly distinguishes cancel=2 from complete=3. This is still source review, not a rerun of native acceptance. Template/occurrence roles are identified through recurrence fields rather than a new task-type enum. `leavesTombstone` is not synonymous with `trashed`.

## Counts are cached domain state, not universal repair formulas

In scoped ordinary/RT1-occurrence checklist validators, `checklistItemsCount` equals the number of owned child rows and `openChecklistItemsCount` counts status-0 children. Selected-child tests and validators preserve parent status while reducing its open-child cache. A completed parent can therefore have independently open children in the reviewed test scenario. Do not force every child to match its parent. P-STATUS.

Private task-creation/ancestor validators count untrashed task leaves through project/heading ancestry, with an open subset using status 0. That is evidence for the named supported cases, not a verified formula for all trashed/closed/recurring/nested states. No counters were read or repaired in the live store. P-REL.

## Ordering

`index`, `todayIndex`, `todayIndexReferenceDate`, and `startBucket` must not be conflated with SQL rowid or a single global sort key. The declaration is known; complete UI ordering, tie-breakers, bucket enums and cache invalidation are not. A deterministic diagnostic ordering is not necessarily the application's visible ordering.

`BSSpotlightDirtyEntity` is WITHOUT ROWID with a composite `(entityType, id)` primary key. Do not skip it or use a universal `SELECT rowid` strategy. Its BLOB keys and tokens remain opaque. S-STRUCT.
