# Support matrix

**Public scope: read-only.** This matrix distinguishes documentation evidence from executable feature support. It does not inherit acceptance from a separate private tool. Consult package tests and CLI help for the exact implemented commands; the documentation recipe is independently reproducible and uses no package internals.

| Operation / claim | Public status | Evidence boundary |
| --- | --- | --- |
| Inspect installed application version/build without launching it | Documented and used for this catalog | S-APP: Info.plist scalar fields only |
| Enumerate physical schema in a read-only snapshot | Documented recipe exercised | S-STRUCT; complete versioned inventory |
| Things format detection | Verified for this observed store | Plist integer at `Meta.databaseVersion`, not SQLite schema_version |
| Export a publication-safe catalog | This checked-in export audited | Arbitrary future exports require their own literal/privacy audit |
| Decode packed date in scoped task fields | Source-reviewed semantics; synthetic arithmetic check | P-DATE; not an all-fields decoder or native test |
| List/show user tasks through the public package | Not certified by this documentation exercise | Requires package-specific tests; do not infer from physical inventory |
| Explain all enum values, BLOB grammars and migrations | Unsupported | Explicit unknowns retained |
| Prepare a native mutation on a copy | Unsupported in initial public scope | Private predecessor is background evidence only |
| Publish a live database change | Unsupported | No public write adapter/acceptance established here |
| Stage native synchronization history | Unsupported | SQL changes are not native staging |
| Contact Things Cloud / obtain remote ACK | Unsupported | No credentials/network/native helper used here |
| Verify cloud readback or another device | Unsupported | No public end-to-end proof |
| Automatic recurring-task generation, repair or migration | Unsupported | No scheduler or mutation authorization |

## Compatibility identity

| Component | Observed value / limit |
| --- | --- |
| Platform/application | macOS, Things **3.24** |
| Installed build | **32400506** |
| Things database format | **29**, independently decoded from the selected store |
| SQLite schema cookie | **8** in this capture; not a Things format version |
| SQLite user_version / application_id | **0 / 0** in this capture; not substituted for format detection |
| Physical layout | [Versioned catalog](database/versions/things-3.24-build-32400506-db29/catalog.md) |
| Other builds, formats, platforms | Not certified by this catalog |

The installed bundle identity does not prove which version created every historical row. Format 29 alone does not identify all indexes, auxiliary tables, migration history or native ABI. Read-only inspection of an unfamiliar schema is a diagnostic operation, not a compatibility guarantee for domain interpretation. See [provenance](database/provenance.md).
