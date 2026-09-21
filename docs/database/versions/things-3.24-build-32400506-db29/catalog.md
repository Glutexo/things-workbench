# Physical catalog: Things 3.24, build 32400506, DB29

Source: S-STRUCT and S-APP in [provenance](../../provenance.md). Raw machine-readable inventory: [schema.json](schema.json). This is a single observed layout, not a vendor schema contract. Every physical column is listed even when its meaning is unknown.

## Inventory totals

- application_tables: **17**
- table_list_entries: **19**
- columns: **118**
- application_columns: **111**
- schema_objects: **42**
- schema_tables: **18**
- schema_indexes: **24**
- index_list_entries: **25**
- foreign_keys: **0**
- views: **0**
- triggers: **0**

The extra index-list entry is the WITHOUT ROWID primary-key index of BSSpotlightDirtyEntity, absent as a separate sqlite_schema object. sqlite_schema itself appears in table_list but not as a schema-table object. The inventory does not filter out SQLite internal tables.

## Reading columns

`NN` is the raw table_xinfo.notnull flag, not a rewritten effective nullability claim. `PK` is the primary-key ordinal (0 = not in PK); `hidden` is retained verbatim. SQL defaults are expressions; JSON null means no declared default. Blank declared types are shown as (empty). Check DDL for INTEGER PRIMARY KEY, CHECK and WITHOUT ROWID behavior rather than equating NN=0 with all possible NULL behavior. Physical declarations are verified; the final column is separately confidence-labeled. See [unknowns](../../unknowns.md).

## `BSSpotlightDirtyEntity`

**Role (hypothesis):** Spotlight dirty-entity bookkeeping; operational protocol and BLOB encodings unknown.

Type: `table`; columns: `4`; WITHOUT ROWID (`wr`): `1`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `entityType` | INTEGER | 1 | (none) | 1 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 1 | `id` | BLOB | 1 | (none) | 2 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 2 | `changeToken` | BLOB | 1 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 3 | `expansionCursor` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

#### `index_BSSpotlightDirtyEntity_expansionCursor`

`seq=0`, `unique=0`, `origin=c`, `partial=1`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `entityType` | 0 | BINARY | 1 |
| 1 | 1 | `id` | 0 | BINARY | 1 |

```sql
CREATE INDEX "index_BSSpotlightDirtyEntity_expansionCursor"
    ON BSSpotlightDirtyEntity ("entityType", "id")
    WHERE "expansionCursor" IS NOT NULL
```

#### `sqlite_autoindex_BSSpotlightDirtyEntity_1`

`seq=1`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `entityType` | 0 | BINARY | 1 |
| 1 | 1 | `id` | 0 | BINARY | 1 |
| 2 | 2 | `changeToken` | 0 | BINARY | 0 |
| 3 | 3 | `expansionCursor` | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE BSSpotlightDirtyEntity (

    "entityType"        INTEGER NOT NULL,
    "id"                BLOB NOT NULL,
    "changeToken"       BLOB NOT NULL,
    "expansionCursor"   BLOB,

    PRIMARY KEY ("entityType", "id")

) WITHOUT ROWID
```

## `BSSpotlightIndexState`

**Role (hypothesis):** Spotlight indexing checkpoint state; update-state enum and tokens unknown.

Type: `table`; columns: `7`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `id` | INTEGER | 0 | (none) | 1 | 0 | **verified/structure** — DDL has INTEGER PRIMARY KEY and CHECK(id = 1). See exact DDL. S-STRUCT. |
| 1 | `updateState` | INTEGER | 1 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 2 | `isEnabled` | INTEGER | 1 | `0` | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 3 | `wholeIndexUpdateToken` | BLOB | 1 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 4 | `wholeIndexExpansionCursor` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 5 | `staticEntitiesUpdateToken` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 6 | `lastCheckpointID` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

None.

### Table DDL

```sql
CREATE TABLE BSSpotlightIndexState (

    "id"                          INTEGER PRIMARY KEY CHECK ("id" = 1),
    "updateState"                 INTEGER NOT NULL,
    "isEnabled"                   INTEGER NOT NULL DEFAULT 0,
    "wholeIndexUpdateToken"       BLOB NOT NULL,
    "wholeIndexExpansionCursor"   BLOB,
    "staticEntitiesUpdateToken"   BLOB,
    "lastCheckpointID"            BLOB
)
```

## `BSSyncronyMetadata`

**Role (observed/source-reviewed):** Opaque synchronization metadata. Private validators include it when native operations stage history; payload format is not a public contract. P-SYNC.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `value` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_BSSyncronyMetadata_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE "BSSyncronyMetadata" (          'uuid'                 TEXT PRIMARY KEY,               'value'                BLOB                            )
```

## `Meta`

**Role (verified/limited):** Key-value metadata; only databaseVersion was read and decoded, as integer 29. Other keys and values were not inspected. S-STRUCT.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `key` | TEXT | 0 | (none) | 1 | 0 | **verified/limited** — Only the databaseVersion key is allowlisted in this inspection. Other keys unknown. S-STRUCT. |
| 1 | `value` | TEXT | 0 | (none) | 0 | 0 | **verified/limited** — Declared TEXT; databaseVersion was decoded as a plist integer. Do not infer runtime storage class from declared type. Other values uninspected. S-STRUCT. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_Meta_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `key` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'Meta' (                    'key'                 TEXT PRIMARY KEY,                'value'               TEXT                             )
```

## `TMArea`

**Role (hypothesis):** Area records, inferred from naming and task area references. No live area rows read.

Type: `table`; columns: `6`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `title` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 2 | `visible` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 3 | `index` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |
| 4 | `cachedTags` | BLOB | 0 | (none) | 0 | 0 | **hypothesis** — Opaque likely tag cache. Canonical source, inheritance and invalidation rules unknown. |
| 5 | `experimental` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Opaque extension payload. Encoding, feature flags, and migration semantics unknown; preserve, do not decode speculatively. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_TMArea_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMArea' (                  'uuid'                 TEXT PRIMARY KEY,               'title'                TEXT,                           'visible'              INTEGER,                        'index'                INTEGER                         , 'cachedTags' BLOB, experimental BLOB)
```

## `TMAreaTag`

**Role (hypothesis):** Area-to-tag link table; endpoints inferred, not declared foreign keys.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `areas` | TEXT | 1 | (none) | 0 | 0 | **hypothesis** — Likely TMArea.uuid endpoint; no SQL FK. |
| 1 | `tags` | TEXT | 1 | (none) | 0 | 0 | **hypothesis** — Likely TMTag.uuid endpoint; no SQL FK. |

### Declared foreign keys

None.

### Index inventory

#### `index_TMAreaTag_areas`

`seq=0`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `areas` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMAreaTag_areas ON TMAreaTag (areas)
```

### Table DDL

```sql
CREATE TABLE 'TMAreaTag' (                                                     'areas'                TEXT NOT NULL,                                                        'tags'                 TEXT NOT NULL                                                         )
```

## `TMChecklistItem`

**Role (observed/source-reviewed):** Checklist children of tasks; source-reviewed validators and tests, not freshly executed native tests. P-STATUS.

Type: `table`; columns: `10`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `userModificationDate` | REAL | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Time-like REAL validated for finite positive values and relative ordering in scoped private operations. Epoch/timezone not independently verified in this inspection. P-DATE, P-STATUS. |
| 2 | `creationDate` | REAL | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Time-like REAL validated for finite positive values and relative ordering in scoped private operations. Epoch/timezone not independently verified in this inspection. P-DATE, P-STATUS. |
| 3 | `title` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 4 | `status` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — 0 open, 2 canceled, 3 completed in selected-child contract/tests. Other values unknown. P-STATUS. |
| 5 | `stopDate` | REAL | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Time-like REAL validated for finite positive values and relative ordering in scoped private operations. Epoch/timezone not independently verified in this inspection. P-DATE, P-STATUS. |
| 6 | `index` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |
| 7 | `task` | TEXT | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Owner reference to TMTask.uuid; enforced in private validators, not by SQL FK. P-STATUS. |
| 8 | `leavesTombstone` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Daily-creation validator expects differing values for template and occurrence children; not a trash flag or universal policy. P-RECURRENCE. |
| 9 | `experimental` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Opaque extension payload. Encoding, feature flags, and migration semantics unknown; preserve, do not decode speculatively. |

### Declared foreign keys

None.

### Index inventory

#### `index_TMChecklistItem_task`

`seq=0`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 7 | `task` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMChecklistItem_task ON TMChecklistItem (task)
```

#### `sqlite_autoindex_TMChecklistItem_1`

`seq=1`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMChecklistItem' (                                                 'uuid'                 TEXT PRIMARY KEY,                                                       'userModificationDate' REAL,                                                                   'creationDate'         REAL,                                                                   'title'                TEXT,                                                                   'status'               INTEGER,                                                                'stopDate'             REAL,                                                                   'index'                INTEGER,                                                                'task'                 TEXT                                                                    , 'leavesTombstone' INTEGER, experimental BLOB)
```

## `TMContact`

**Role (hypothesis):** Contact-related records; use, lifecycle, and current feature coverage unknown.

Type: `table`; columns: `7`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `displayName` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 2 | `firstName` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 3 | `lastName` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 4 | `emails` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 5 | `appleAddressBookId` | TEXT | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 6 | `index` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_TMContact_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMContact' (               'uuid'                 TEXT PRIMARY KEY,               'displayName'          TEXT,                           'firstName'            TEXT,                           'lastName'             TEXT,                           'emails'               TEXT,                           'appleAddressBookId'   TEXT,                           'index'                INTEGER                         )
```

## `TMMetaItem`

**Role (unknown):** Opaque metadata; no keys or values inspected.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `value` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_TMMetaItem_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMMetaItem' (              'uuid'                 TEXT PRIMARY KEY,               'value'                BLOB                            )
```

## `TMSettings`

**Role (hypothesis):** Application settings; values deliberately not inspected. Treat authentication-related values as secrets.

Type: `table`; columns: `6`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `logInterval` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 2 | `manualLogDate` | REAL | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 3 | `groupTodayByParent` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 4 | `uriSchemeAuthenticationToken` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Potential credential field. Value never read/exported; do not include settings rows in diagnostics. |
| 5 | `experimental` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Opaque extension payload. Encoding, feature flags, and migration semantics unknown; preserve, do not decode speculatively. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_TMSettings_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMSettings' (                 'uuid'                 TEXT PRIMARY KEY,                  'logInterval'          INTEGER,                           'manualLogDate'        REAL                               , 'groupTodayByParent' INTEGER, 'uriSchemeAuthenticationToken' TEXT, experimental BLOB)
```

## `TMSmartList`

**Role (hypothesis):** Smart-list definitions; BLOB grammar and relationship semantics unknown.

Type: `table`; columns: `5`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `title` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 2 | `index` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |
| 3 | `definition` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 4 | `experimental` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Opaque extension payload. Encoding, feature flags, and migration semantics unknown; preserve, do not decode speculatively. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_TMSmartList_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE TMSmartList (

        "uuid"          TEXT PRIMARY KEY,

        "title"         TEXT,
        "index"         INTEGER,
        "definition"    BLOB,

        "experimental"  BLOB
    )
```

## `TMTag`

**Role (hypothesis):** Tag records and possible hierarchy; naming evidence only unless stated otherwise.

Type: `table`; columns: `7`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `title` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 2 | `shortcut` | TEXT | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 3 | `usedDate` | REAL | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 4 | `parent` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Likely TMTag.uuid parent reference; hierarchy and cycle rules unverified. |
| 5 | `index` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |
| 6 | `experimental` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Opaque extension payload. Encoding, feature flags, and migration semantics unknown; preserve, do not decode speculatively. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_TMTag_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMTag' (                   'uuid'                 TEXT PRIMARY KEY,               'title'                TEXT,                           'shortcut'             TEXT,                           'usedDate'             REAL,                           'parent'               TEXT,                           'index'                INTEGER                         , experimental BLOB)
```

## `TMTask`

**Role (observed/source-reviewed):** Tasks, projects and headings share this table. RT1 templates/occurrences are roles, not additional SQL tables. P-STATUS, P-REL, P-RECURRENCE.

Type: `table`; columns: `41`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `leavesTombstone` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Not equivalent to trashed. Full deletion/sync policy not established. |
| 2 | `creationDate` | REAL | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Time-like REAL validated for finite positive values and relative ordering in scoped private operations. Epoch/timezone not independently verified in this inspection. P-DATE, P-STATUS. |
| 3 | `userModificationDate` | REAL | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Time-like REAL validated for finite positive values and relative ordering in scoped private operations. Epoch/timezone not independently verified in this inspection. P-DATE, P-STATUS. |
| 4 | `type` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — 0 task, 1 project, 2 heading in private validators. Other values unknown. P-STATUS, P-REL. |
| 5 | `status` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — 0 open, 2 canceled, 3 completed in reviewed operation contracts. Other values unknown. P-STATUS. |
| 6 | `stopDate` | REAL | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Time-like REAL validated for finite positive values and relative ordering in scoped private operations. Epoch/timezone not independently verified in this inspection. P-DATE, P-STATUS. |
| 7 | `trashed` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Scoped ordinary validators require zero for nontrashed targets. Other values and lifecycle not fully characterized. P-STATUS. |
| 8 | `title` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 9 | `notes` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Text field; human-content role suggested by name. No content read/exported; normalization and exact grammar unverified. |
| 10 | `notesSync` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 11 | `cachedTags` | BLOB | 0 | (none) | 0 | 0 | **hypothesis** — Opaque likely tag cache. Canonical source, inheritance and invalidation rules unknown. |
| 12 | `start` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — 1 Anytime, 2 scheduled in scoped date/creation validators. Not a complete enum and not enough to derive UI Today state. P-DATE. |
| 13 | `startDate` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Packed calendar date in scoped reschedule validator/test. See dates.md. P-DATE. |
| 14 | `startBucket` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 15 | `reminderTime` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 16 | `lastReminderInteractionDate` | REAL | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 17 | `deadline` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Calendar-day field suggested by DDL rename/type comments and model role; independent conversion/edge cases not verified here. See dates.md. |
| 18 | `deadlineSuppressionDate` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Calendar-day field suggested by DDL rename/type comments and model role; independent conversion/edge cases not verified here. See dates.md. |
| 19 | `t2_deadlineOffset` | INTEGER | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 20 | `index` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |
| 21 | `todayIndex` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Ordering-related field by name; scope, spacing, tie-breaks and user-visible sort precedence unverified. |
| 22 | `todayIndexReferenceDate` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Packed calendar date in scoped reschedule validator/test. See dates.md. P-DATE. |
| 23 | `area` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Likely TMArea.uuid reference; not a SQL FK. Inheritance/direct-assignment rules unverified. |
| 24 | `project` | TEXT | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Reference to a project/heading row in TMTask in scoped validators. No SQL FK. P-REL. |
| 25 | `heading` | TEXT | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Reference to a project/heading row in TMTask in scoped validators. No SQL FK. P-REL. |
| 26 | `contact` | TEXT | 0 | (none) | 0 | 0 | **hypothesis** — Likely TMContact.uuid reference; current use and null semantics unverified. |
| 27 | `untrashedLeafActionsCount` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Private validators compute untrashed task descendants through task ancestors; open subset uses status==0. Scope restrictions matter. P-REL. |
| 28 | `openUntrashedLeafActionsCount` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Private validators compute untrashed task descendants through task ancestors; open subset uses status==0. Scope restrictions matter. P-REL. |
| 29 | `checklistItemsCount` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Scoped ordinary/RT1 occurrence validators compare children and status==0 children respectively. Not a universal repair formula. P-STATUS. |
| 30 | `openChecklistItemsCount` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Scoped ordinary/RT1 occurrence validators compare children and status==0 children respectively. Not a universal repair formula. P-STATUS. |
| 31 | `rt1_repeatingTemplate` | TEXT | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Occurrence reference to template TMTask.uuid; not a SQL FK. P-RECURRENCE. |
| 32 | `rt1_recurrenceRule` | BLOB | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Private validators decode plist recurrence rules; only a narrow daily shape is reviewed. Never publish actual payloads. P-RECURRENCE. |
| 33 | `rt1_instanceCreationStartDate` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Packed calendar date in scoped native-generation validator; cursor/next-cache meanings not universal. P-RECURRENCE. |
| 34 | `rt1_instanceCreationPaused` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Scoped validators recognize 0 active and 1 paused and check next-date coherence. Not authorization to toggle. P-RECURRENCE. |
| 35 | `rt1_instanceCreationCount` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Generation-related counter checked in limited creation/generation validators. Universal counting semantics unknown. P-RECURRENCE. |
| 36 | `rt1_afterCompletionReferenceDate` | INTEGER | 0 | (none) | 0 | 0 | **hypothesis** — Calendar-day field suggested by DDL rename/type comments and model role; independent conversion/edge cases not verified here. See dates.md. |
| 37 | `rt1_nextInstanceStartDate` | INTEGER | 0 | (none) | 0 | 0 | **observed/source-reviewed** — Packed calendar date in scoped native-generation validator; cursor/next-cache meanings not universal. P-RECURRENCE. |
| 38 | `experimental` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Opaque extension payload. Encoding, feature flags, and migration semantics unknown; preserve, do not decode speculatively. |
| 39 | `repeater` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 40 | `repeaterMigrationDate` | REAL | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

#### `index_TMTask_area`

`seq=3`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 23 | `area` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_area ON TMTask(area)
```

#### `index_TMTask_heading`

`seq=4`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 25 | `heading` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_heading ON TMTask(heading)
```

#### `index_TMTask_id_where_recurrenceRuleNotNull`

`seq=2`, `unique=0`, `origin=c`, `partial=1`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_id_where_recurrenceRuleNotNull
    ON TMTask (uuid)
    WHERE rt1_recurrenceRule IS NOT NULL
```

#### `index_TMTask_project`

`seq=5`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 24 | `project` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_project ON TMTask(project)
```

#### `index_TMTask_repeatingTemplate_and_creationDate`

`seq=1`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 31 | `rt1_repeatingTemplate` | 0 | BINARY | 1 |
| 1 | 2 | `creationDate` | 0 | BINARY | 1 |
| 2 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_repeatingTemplate_and_creationDate
    ON TMTask(rt1_repeatingTemplate, creationDate)
```

#### `index_TMTask_stopDate`

`seq=6`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 6 | `stopDate` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_stopDate ON TMTask(stopDate)
```

#### `index_TMTask_userModificationDate`

`seq=0`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 3 | `userModificationDate` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTask_userModificationDate ON TMTask(userModificationDate)
```

#### `sqlite_autoindex_TMTask_1`

`seq=7`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE TMTask (

        "uuid"                              TEXT PRIMARY KEY,
        "leavesTombstone"                   INTEGER,

        "creationDate"                      REAL,
        "userModificationDate"              REAL,

        "type"                              INTEGER,

        "status"                            INTEGER,
        "stopDate"                          REAL,

        "trashed"                           INTEGER,

        "title"                             TEXT,
        "notes"                             TEXT,
        "notesSync"                         INTEGER,

        "cachedTags"                        BLOB,

        "start"                             INTEGER,
        "startDate"                         INTEGER,   -- REAL -> INTEGER
        "startBucket"                       INTEGER,
        "reminderTime"                      INTEGER,
        "lastReminderInteractionDate"       REAL,      -- Renamed from "lastAlarmInteractionDate"

        "deadline"                          INTEGER,   -- Renamed from "dueDate", REAL -> INTEGER
        "deadlineSuppressionDate"           INTEGER,   -- Renamed from "dueDateSuppressionDate", REAL -> INTEGER
        "t2_deadlineOffset"                 INTEGER,   -- Renamed from "dueDateOffset"

        "index"                             INTEGER,
        "todayIndex"                        INTEGER,
        "todayIndexReferenceDate"           INTEGER,   -- REAL -> INTEGER

        "area"                              TEXT,
        "project"                           TEXT,
        "heading"                           TEXT,      -- Renamed from "actionGroup"
        "contact"                           TEXT,      -- Renamed from "delegate"

        "untrashedLeafActionsCount"         INTEGER,
        "openUntrashedLeafActionsCount"     INTEGER,

        "checklistItemsCount"               INTEGER,
        "openChecklistItemsCount"           INTEGER,

        "rt1_repeatingTemplate"             TEXT,      -- Renamed from "repeatingTemplate"
        "rt1_recurrenceRule"                BLOB,      -- Renamed from "recurrenceRule"
        "rt1_instanceCreationStartDate"     INTEGER,   -- Renamed from "instanceCreationStartDate", REAL -> INTEGER
        "rt1_instanceCreationPaused"        INTEGER,   -- Renamed from "instanceCreationPaused"
        "rt1_instanceCreationCount"         INTEGER,   -- Renamed from "instanceCreationCount"
        "rt1_afterCompletionReferenceDate"  INTEGER,   -- Renamed from "afterCompletionReferenceDate", REAL -> INTEGER
        "rt1_nextInstanceStartDate"         INTEGER,   -- Renamed from "nextInstanceStartDate", REAL -> INTEGER

        "experimental"                      BLOB,

        "repeater"                          BLOB,
        "repeaterMigrationDate"             REAL
    )
```

## `TMTaskTag`

**Role (observed/source-reviewed):** Task-to-tag associations used by private creation validators; no SQL foreign keys or uniqueness constraints. P-REL.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `tasks` | TEXT | 1 | (none) | 0 | 0 | **observed/source-reviewed** — Task endpoint used against TMTask.uuid in private creation validator; no SQL FK. P-REL. |
| 1 | `tags` | TEXT | 1 | (none) | 0 | 0 | **observed/source-reviewed** — Tag endpoint used against TMTag.uuid in private creation validator; no SQL FK. P-REL. |

### Declared foreign keys

None.

### Index inventory

#### `index_TMTaskTag_tasks`

`seq=0`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `tasks` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTaskTag_tasks ON TMTaskTag (tasks)
```

### Table DDL

```sql
CREATE TABLE 'TMTaskTag' (                                                     'tasks'                TEXT NOT NULL,                                                        'tags'                 TEXT NOT NULL                                                         )
```

## `TMTombstone`

**Role (hypothesis):** Deletion-history records; target resolution and retention policy unknown.

Type: `table`; columns: `3`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `uuid` | TEXT | 0 | (none) | 1 | 0 | **verified/structure** — Declared TEXT primary-key identifier. Encoding, allocation, and lifecycle rules are not established by the declaration. |
| 1 | `deletionDate` | REAL | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 2 | `deletedObjectUUID` | TEXT | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

#### `index_TMTombstone_deletedObjectUUID`

`seq=0`, `unique=0`, `origin=c`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 2 | `deletedObjectUUID` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

```sql
CREATE INDEX index_TMTombstone_deletedObjectUUID ON TMTombstone (deletedObjectUUID)
```

#### `sqlite_autoindex_TMTombstone_1`

`seq=1`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `uuid` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE 'TMTombstone' (                                                            'uuid'          TEXT PRIMARY KEY,                                                                 'deletionDate'  REAL,                                                                             'deletedObjectUUID' TEXT                                                                      )
```

## `ThingsTouch_ExtensionCommandStore_Commands`

**Role (hypothesis):** Extension-command queue, inferred from naming; command types and BLOB body grammar unknown.

Type: `table`; columns: `3`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `id` | INTEGER | 0 | (none) | 1 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 1 | `type` | TEXT | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 2 | `body` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

None.

### Table DDL

```sql
CREATE TABLE "ThingsTouch_ExtensionCommandStore_Commands" (
"id" INTEGER PRIMARY KEY AUTOINCREMENT,
"type" TEXT,
"body" BLOB
)
```

## `ThingsTouch_ExtensionCommandStore_Meta`

**Role (unknown):** Opaque extension-command-store metadata; no values inspected.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `key` | TEXT | 0 | (none) | 1 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |
| 1 | `value` | BLOB | 0 | (none) | 0 | 0 | **unknown** — Meaning/encoding not established beyond the physical declaration; no values inspected. |

### Declared foreign keys

None.

### Index inventory

#### `sqlite_autoindex_ThingsTouch_ExtensionCommandStore_Meta_1`

`seq=0`, `unique=1`, `origin=pk`, `partial=0`.

| seqno | cid | Column | desc | Collation | key |
| ---: | ---: | --- | ---: | --- | ---: |
| 0 | 0 | `key` | 0 | BINARY | 1 |
| 1 | -1 | (null) | 0 | BINARY | 0 |

No separate CREATE INDEX SQL; key structure is retained above.

### Table DDL

```sql
CREATE TABLE "ThingsTouch_ExtensionCommandStore_Meta" (
"key" TEXT PRIMARY KEY,
"value" BLOB
)
```

## `sqlite_schema`

**Role (verified/structure):** SQLite schema inventory, implicitly present; not itself represented by a CREATE TABLE row. S-STRUCT.

Type: `table`; columns: `5`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `type` | TEXT | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |
| 1 | `name` | TEXT | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |
| 2 | `tbl_name` | TEXT | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |
| 3 | `rootpage` | INT | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |
| 4 | `sql` | TEXT | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |

### Declared foreign keys

None.

### Index inventory

None.

### Table DDL

Implicit SQLite schema table; no CREATE TABLE entry.

## `sqlite_sequence`

**Role (verified/structure):** SQLite internal table associated with AUTOINCREMENT; its row values were not read. S-STRUCT.

Type: `table`; columns: `2`; WITHOUT ROWID (`wr`): `0`; STRICT: `0`. Source: S-STRUCT.

| cid | Column | Declared type | NN | Default SQL | PK | hidden | Meaning / confidence |
| ---: | --- | --- | ---: | --- | ---: | ---: | --- |
| 0 | `name` | (empty) | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |
| 1 | `seq` | (empty) | 0 | (none) | 0 | 0 | **verified/structure** — SQLite structural field; raw declaration retained. Schema-object metadata is exported; application records and sqlite_sequence values are not. |

### Declared foreign keys

None.

### Index inventory

None.

### Table DDL

```sql
CREATE TABLE sqlite_sequence(name,seq)
```
