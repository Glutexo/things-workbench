# Unknowns and interpretation limits

Every column appears in the physical catalog with a confidence label. **Unknown does not mean unused, irrelevant, corrupt, safe to reset or safe to omit.**

## Unresolved contracts

- Complete task/checklist/status/start/startBucket enums; unknown numeric states remain unknown.
- User-visible sorting, index spacing, ties and Today grouping.
- Effective relationship inheritance, orphan/cycle handling and deletion cascades outside scoped validators.
- Universal leaf/checklist cache maintenance across recurrence, nested containers, trash and closed states.
- Every `experimental` and `cachedTags` payload; `repeater` migration/encoding.
- Reminder encoding, complete time-like field epochs, sentinels and timezone behavior.
- Full RT1 rule grammar, after-completion modes, exceptions and calendar-boundary behavior.
- Contact lifecycle and smart-list definition grammar.
- Spotlight entity-type/update-state enums and BLOB token/cursor protocols.
- Metadata key namespaces other than the allowlisted format-version key.
- Extension command types/body grammar and execution semantics.
- Authentication/settings values, note-history representation and synchronization wire protocol.
- Format migrations and compatibility across builds, platforms or databases with the same reported format but different DDL.

## Structural subtleties

`table_xinfo.notnull` is retained literally, not rewritten to an oversimplified nullable boolean. SQL primary-key/rowid rules can affect effective behavior. No CHECK, UNIQUE or FOREIGN KEY constraints should be inferred from a domain-friendly name. The exact DDL and index metadata are the structural authority for this observed snapshot.

`Meta.value` is declared TEXT even though the allowlisted version is decoded as a plist. This illustrates why declared SQLite affinity is not a proof of runtime value type or serialization format. No other metadata value was sampled.

SQLite internal objects and auxiliary WITHOUT ROWID tables are included; skipping them can invalidate claims of full inventory. Physical catalog completeness is not domain-semantic completeness.

## Evidence upgrade policy

To promote a hypothesis, add a reproducible synthetic test where possible and separately scoped native evidence where necessary. Record exact build/format, input boundaries, before/after invariants and negative controls. Do not replace unavailable native evidence with a plausible fixture and call it an end-to-end result. Sanitized summaries can be public; user snapshots, identifiers and receipts stay private.

Historical schema notes that disagree with later operation contracts are not an authority for writes. Even the source-reviewed mappings here must not be treated as a vendor guarantee or a fresh run of predecessor tests.
