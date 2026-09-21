# Database documentation

Start with the [physical catalog](versions/things-3.24-build-32400506-db29/catalog.md) and its [machine-readable schema](versions/things-3.24-build-32400506-db29/schema.json). The observed identity is **Things 3.24 / build 32400506 / DB29**. This is a structural snapshot, not a specification supplied by the vendor.

## Evidence levels

- **Verified/structure:** direct read-only introspection or installed bundle metadata. A declared column is verified even if its meaning is unknown.
- **Verified/limited:** an explicitly allowlisted scalar, not a table dump.
- **Observed/source-reviewed:** a private implementation/test contract was read. Those tests were **not rerun** during this documentation exercise; this is not new native acceptance or a public-package guarantee.
- **Hypothesis:** suggested by naming, DDL comments or conventional relationships; not independently validated.
- **Unknown:** semantics/encoding/lifecycle not established. Preserve the distinction rather than filling gaps with plausible values.

Confidence labels qualify meaning, never override the exact physical declaration. There are **17 application tables / 111 application columns**, plus the two SQLite internal table-list entries. The full table-list inventory covers **19 entries / 118 columns**. No declared foreign keys, views or triggers were found in this snapshot. Source: S-STRUCT.

## Topics

- [Reproduction and JSON field contract](extraction.md)
- [Source provenance and evidence limits](provenance.md)
- [Relationships, enums, counters and ordering](relationships.md)
- [Dates and time-like values](dates.md)
- [Recurrence](recurrence.md)
- [Synchronization/history](sync-history.md)
- [Unknowns and research gaps](unknowns.md)
- [Architecture](../architecture.md), [safety](../safety.md), [support](../support-matrix.md)

SQLite `schema_version` is a schema-change cookie, not the application's database-format identity.[1] DB29 here comes from the decoded `Meta` value for the exact key `databaseVersion`. No other Meta values, settings, account metadata or sync payloads were inspected.

## Sources

[1] https://www.sqlite.org/pragma.html
