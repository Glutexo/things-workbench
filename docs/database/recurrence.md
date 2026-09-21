# Recurrence: physical fields versus interpretation

The full [TMTask catalog](versions/things-3.24-build-32400506-db29/catalog.md) includes both `rt1_*` fields and `repeater`/`repeaterMigrationDate`. Their coexistence is verified; interchangeability and complete migration behavior are not.

## Source-reviewed RT1 roles

- `rt1_recurrenceRule`: a BLOB decoded with a plist parser by narrow private validators. No live rule BLOB was read or published.
- `rt1_repeatingTemplate`: an occurrence-to-template reference in those validators. The target is another TMTask row, not a SQL foreign key.
- `rt1_instanceCreationPaused`: scoped validators recognize active=0 and paused=1, with corresponding next-date checks. This is not an exhaustive truth table.
- `rt1_instanceCreationStartDate`: a generation/scan-start cursor in the reviewed workflow, not evidence by itself that an occurrence was created.
- `rt1_nextInstanceStartDate`: derived next-date state in narrow validators; a null value must not be guessed into a date.
- `rt1_instanceCreationCount`: generation-related cached count. Complete semantics, overflow and lifetime policy are unknown.
- `rt1_afterCompletionReferenceDate`: structurally known; complete after-completion scheduling behavior unverified.

Source: P-RECURRENCE, **observed/source-reviewed**, not a new native execution result. Ordinary/RT1 scopes explicitly reject non-null `repeater`; that is a boundary of those operations, not proof that `repeater` is unused.

## Narrow daily-rule observation, not a schema for all recurrence

A reviewed private creation validator checks plist fields `tp=0`, `fu=16`, `fa=1`, `rc=0`, `ts=0`, `of=[{"dy":0}]` for its limited daily case. Another explicitly experimental module constructs a rule with `rrv=4` and calendar/time reference keys. This documentation does not promote that experimental constructor into a supported writer or infer a complete enum from one pattern. Different calendar-unit enums must not be assumed interchangeable. Unknown keys and plist types need preservation. P-RECURRENCE.

A template and an occurrence can differ in task fields, child identifiers, child tombstone policy, notes/history and caches. Copying a sibling SQL row is not verified recurrence generation. A date match alone is not a safe deduplication key.

## Unsupported in the public package's initial scope

No native generation, pause/unpause, completion-triggered repetition, migration, missing-instance repair, cloud reconciliation or automatic schedule is certified. No recurrence payload values were inspected in the live store. Monthly/yearly rules, exceptions, end conditions, DST behavior, missed intervals and every interaction with completion or trash remain explicit research gaps.
