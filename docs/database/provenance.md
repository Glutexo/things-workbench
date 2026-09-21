# Provenance and evidence ledger

## Locally inspected sources

| ID | Source | What this establishes | Limits |
| --- | --- | --- | --- |
| S-APP | Installed Things bundle Info.plist | Short version 3.24 and build 32400506 | Does not prove historical row provenance or native ABI compatibility |
| S-STRUCT | Selected local SQLite store, `mode=ro`, explicit bounded read transaction | sqlite_schema, table_list, table_xinfo, index_list/index_xinfo, foreign_key_list; allowlisted `Meta.databaseVersion` decoded to integer 29 | No app records/settings/sync payloads sampled; structural evidence only |
| P-STATUS | Private predecessor selected-checklist/status validators and associated test source | Scoped status mappings, child ownership, parent/child independence and cache assertions | Source reviewed only; tests not rerun; private fixtures not published |
| P-DATE | Private predecessor task-date validator/test and pure calendar packing helper | Scoped packed-day representation, scheduled-state checks and relative timestamp assertions | Only pure synthetic packing exercised here, not native rescheduling |
| P-REL | Private predecessor creation and ancestor-cache validators | Scoped task/project/heading roles, ancestor traversal and tag associations | No universal foreign-key or cache specification |
| P-RECURRENCE | Private predecessor daily creation/generation validators; explicitly experimental recurrence helper | Narrow RT1 template/occurrence and daily-rule checks | Experimental constructor is not production support; no native generation run here |
| P-SYNC | Private predecessor operation validators | Native history is separate from application row state | No published complete payload grammar or new remote proof |
| P-WORKFLOW | Current installed private predecessor release workflow and release plan | Operation/review/recovery separation and exact-byte provenance boundary | Read-only provenance review, not authorization or a public adapter |

Private receipts retain exact local source filenames, hashes, execution/query traces and audit details. The public documentation intentionally omits those local paths, account-derived examples and private receipt contents. The private semantic evidence is **not independently executable from this repository**. These notes expose that limitation instead of presenting a private test assertion as a public test result.

## Public physical artifact

The version directory groups installed bundle version/build with the independently decoded Things format. `schema.json` contains no timestamps, local paths, task identifiers, account metadata, row counts, actual BLOB values or SQLite storage root-page values. The catalog retains unknown/internal objects and original DDL/default expressions after review.

[extraction.md](extraction.md) specifies an independent reproduction recipe and the JSON field contract. A package exporter may use a different transport shape; compare normalized physical fields, not file shape or an application version string alone. SQLite schema cookie is recorded as an observation, not part of the Things format number.

## Official SQLite references

The numbered references in these docs refer to the official SQLite pages below. Their content was retrieved for this documentation, with evidence copies retained privately. They support SQLite mechanics, **not Things semantics**. Local source IDs above are a separate provenance namespace.

- PRAGMA reference: table/index/foreign-key introspection and schema-version cookie.[1]
- Schema table: object/DDL inventory, implicit schema table and internal indexes.[2]
- Write-ahead logging: read snapshots and WAL/SHM operational caveats.[3]
- URI filenames: read-only mode and immutable-file assumptions.[4]

## Sources

[1] https://www.sqlite.org/pragma.html
[2] https://www.sqlite.org/schematab.html
[3] https://www.sqlite.org/wal.html
[4] https://www.sqlite.org/uri.html
