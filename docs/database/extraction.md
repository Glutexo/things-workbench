# Reproducing the physical catalog

This is a standalone **documentation recipe**, independent of the package exporter. Supply your own existing database path and installed bundle Info.plist. Store output privately first. It includes DDL: inspect object names, comments, string literals and defaults before publishing anything. See [safety](../safety.md).

## What is read

Within one explicitly owned transaction: the main schema's objects, table-list entries, extended columns, index lists/columns and foreign-key lists; four read-only SQLite metadata pragmas; and **only** the `Meta` value for `databaseVersion`. That allowlisted value must decode to an integer plist. No other application row, row count, setting or BLOB is queried. Info.plist is read separately; it cannot be made atomic with the database transaction.

The recipe requires SQLite with `table_list` support (3.37.0 or later). It preserves hidden/generated-column metadata instead of relying on `table_info` alone.[1] Refuse absent/ambiguous format metadata rather than guessing from a header or app version. This recipe deliberately does not execute arbitrary caller SQL or load extensions.

## Executable recipe

Save the following code outside the repository, then invoke it with three explicit arguments: database, Info.plist and a **new private output file**. It does not discover accounts or infer a default store. A normal local WAL-aware read is used; do not add `immutable=1` or disable locks.

```python
import json
import pathlib
import plistlib
import sqlite3
import sys
import time


def quote_literal(value):
    return "'" + value.replace("'", "''") + "'"


def records(connection, statement):
    return [dict(row) for row in connection.execute(statement)]


def extract(database, info_plist):
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise RuntimeError("SQLite table_list support is required")
    database = pathlib.Path(database).resolve(strict=True)
    if not database.is_file():
        raise ValueError("Expected an existing database file")
    with pathlib.Path(info_plist).open("rb") as stream:
        info = plistlib.load(stream)
    version = info["CFBundleShortVersionString"]
    build = info["CFBundleVersion"]
    if not isinstance(version, str) or not isinstance(build, str):
        raise ValueError("Expected application version/build strings")
    connection = sqlite3.connect(
        database.as_uri() + "?mode=ro", uri=True,
        isolation_level=None, timeout=2,
    )
    connection.row_factory = sqlite3.Row
    deadline = time.monotonic() + 20
    connection.set_progress_handler(
        lambda: int(time.monotonic() > deadline), 1000
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        metadata = {
            name: connection.execute("PRAGMA main." + name).fetchone()[0]
            for name in ("schema_version", "user_version", "application_id", "encoding")
        }
        objects = records(connection,
            "SELECT type,name,tbl_name,sql FROM main.sqlite_schema ORDER BY type,name")
        tables = sorted(records(connection, "PRAGMA main.table_list"),
                        key=lambda table: table["name"])
        tables = [table for table in tables if table["schema"] == "main"]
        if not tables:
            raise RuntimeError("No table-list inventory returned")
        for table in tables:
            if time.monotonic() > deadline:
                raise TimeoutError("Structural inspection time budget exceeded")
            name = quote_literal(table["name"])
            table["columns"] = sorted(records(connection,
                "PRAGMA main.table_xinfo(" + name + ")"), key=lambda column: column["cid"])
            table["foreign_keys"] = sorted(records(connection,
                "PRAGMA main.foreign_key_list(" + name + ")"),
                key=lambda key: (key["id"], key["seq"]))
            table["indexes"] = sorted(records(connection,
                "PRAGMA main.index_list(" + name + ")"), key=lambda index: index["name"])
            for index in table["indexes"]:
                index["columns"] = sorted(records(connection,
                    "PRAGMA main.index_xinfo(" + quote_literal(index["name"]) + ")"),
                    key=lambda column: column["seqno"])
        rows = connection.execute(
            "SELECT value FROM main.Meta WHERE key = ?", ("databaseVersion",)
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("Expected exactly one databaseVersion value")
        raw = rows[0][0]
        if not isinstance(raw, (str, bytes)):
            raise ValueError("Unsupported databaseVersion serialization")
        format_version = plistlib.loads(raw.encode("utf-8") if isinstance(raw, str) else raw)
        if type(format_version) is not int:
            raise ValueError("Expected an integer databaseVersion, not boolean or other type")
        return {
            "catalog_format_version": 1,
            "application": {"name": "Things", "platform": "macOS",
                            "version": version, "build": build},
            "database_format": {
                "version": format_version,
                "source": "Meta.value for the single key databaseVersion; decoded plist integer",
            },
            "sqlite_metadata": metadata,
            "objects": objects,
            "tables": tables,
        }
    finally:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()


if __name__ == "__main__":
    import os
    os.umask(0o077)
    if len(sys.argv) != 4:
        raise SystemExit("Usage: recipe.py DATABASE INFO_PLIST NEW_PRIVATE_OUTPUT")
    result = extract(sys.argv[1], sys.argv[2])
    with open(sys.argv[3], "x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
```

The executable block was extracted and exercised against the selected read-only source. Two recipe exports and the checked-in JSON matched byte-for-byte for this capture. This proves reproduction of this artifact, not safety for arbitrary input databases or write compatibility.

## JSON field contract, version 1

- `catalog_format_version`: version of this documentation export shape, not Things or SQLite.
- `application`: independently inspected bundle version/build, platform and name; no bundle path.
- `database_format`: allowlisted decoded integer plus a constant source description.
- `sqlite_metadata`: raw schema cookie, user_version, application_id and encoding. The schema cookie may differ after schema operations even when a Things format number matches.
- `objects`: every main `sqlite_schema` object's `type`, `name`, `tbl_name`, and `sql`, sorted by type/name. Null SQL for implicit indexes is retained. Storage-dependent `rootpage` **values** are deliberately omitted. The `rootpage` **column declaration** remains in the sqlite_schema table inventory.
- `tables`: every main `table_list` entry, including SQLite internal, virtual/shadow/view entries if present; original `schema`, `name`, `type`, `ncol`, `wr`, `strict` fields retained, sorted by name. No objects of those kinds are silently filtered out; their absence in this catalog is observed, not assumed.
- `tables[].columns`: all `table_xinfo` fields, ordered by `cid`; `type` is the literal declared type, `dflt_value` the SQL expression or null, `notnull` the raw flag, `pk` the primary-key ordinal, `hidden` the raw classification.
- `tables[].foreign_keys`: all `foreign_key_list` rows ordered by `(id, seq)`; empty means none declared in that snapshot.
- `tables[].indexes`: all `index_list` fields ordered by name, with original `seq`, `unique`, `origin`, `partial`; nested `columns` contains complete `index_xinfo` rows in `seqno` order, including auxiliary columns and null names.

Index `cid=-1` means rowid and `cid=-2` an expression; `key=0` marks an auxiliary column rather than an index key. `origin` distinguishes explicit creation, UNIQUE and primary-key indexes.[1] Keep raw flags/ordinals; do not invent nullable booleans or drop auxiliary entries.

SQLite's schema table is implicit, and WITHOUT ROWID primary keys need not have a separate sqlite_schema index row.[2] Therefore `table_list`, schema-table counts and index-list/schema-index counts intentionally differ in this catalog. Comparing only CREATE statements misses part of the inventory.

## Reconciliation with a package exporter

Do not require a separate exporter to share this JSON envelope. Compare its schema objects/DDL, full column metadata, table flags, every index including implicit indexes, and foreign-key declarations after normalizing ordering only. Compare application identity, Things format and SQLite metadata separately. Do not silently discard an extra field/object to make the outputs match. Account for omitted storage-page values explicitly.

A regenerated physical JSON is not automatically ready to publish: rerun the privacy review and update the human catalog, confidence notes and completeness checks. Never publish a database to make reproduction easier.

### Package CLI envelope, version 1

The implemented `things_workbench.inspect_schema(db)` API and
`python3 -m things_workbench --db DATABASE schema --json` CLI return the same
physical structure. The CLI writes JSON to stdout and the sharing warning to
stderr. Neither reads Info.plist nor `Meta.databaseVersion`; neither emits
application identity, Things format detection, or the recipe's SQLite metadata.
Their envelope is intentionally **not** the documentation recipe's envelope.

| Package API / CLI field | Catalog field | Reconciliation |
| --- | --- | --- |
| `format_version` | `catalog_format_version` | Both currently 1, but version different envelope contracts; not interchangeable. |
| `semantics` | `not present` | Package value is `uninterpreted`; semantic prose stays separate. |
| `sharing_warning` | `not present` | Package warns that DDL and defaults may contain private literals. |
| `objects` | `objects` | Compare every object's type, name, tbl_name and exact SQL, including null SQL; sorted by type/name. |
| `objects[].rootpage` | `not present` | Package retains storage-page values. Validate against the inspected file, then explicitly exclude only this field from catalog equality. |
| `tables[].name` | `tables[].name` | Package name duplicates its table_list name; require equality before flattening. |
| `tables[].table_list` | `tables[]` | Flatten schema, name, type, ncol, wr and strict without changing raw values. |
| `tables[].columns` | `tables[].columns` | Compare every table_xinfo field, including hidden flags, raw notnull, PK ordinals and SQL defaults. |
| `tables[].indices` | `tables[].indexes` | Rename the container only; retain every index_list field and complete nested index_xinfo columns. |
| `tables[].foreign_keys` | `tables[].foreign_keys` | Compare every declaration; do not infer relationships from names. |
| `not emitted` | `application` | Independently captured bundle identity; not recoverable from the structure-only test fixture. |
| `not emitted` | `database_format` | Recipe-only allowlisted plist scalar; the synthetic fixture deliberately has no Meta rows. |
| `not emitted` | `sqlite_metadata` | Recipe-only header metadata; compare separately, not by fabricating package fields. |

The package sorts tables and indexes by name. Its column/index-column/FK arrays
retain SQLite PRAGMA order; when reconciling other exporters, sort them by cid,
seqno and (id, seq), respectively, without dropping fields or rows. Unknown keys,
extra objects, missing implicit indexes, or auxiliary columns are discrepancies,
not permission to intersect the two inventories. Do not rewrite DDL whitespace,
comments, types, nulls or default expressions to conceal a mismatch.

### Automated structure-only integration

`tests/test_schema_docs.py` checks every human-catalog table, column, index,
physical flag, SQL block and declared inventory total. Confidence-labeled unknown
semantics remain acceptable. It also reconstructs a **fresh temporary SQLite
file** from this fixed reviewed catalog's DDL, then compares the complete API and
CLI exports with the catalog after the explicit envelope conversion above.

The reconstruction is test-only: no caller-supplied DDL execution is added to the
package. No personal database, copied application rows, installed bundle, native
framework, Things process or network is used. All application tables remain empty.
SQLite creates `sqlite_sequence` from the published `AUTOINCREMENT` declaration;
its displayed CREATE statement is **not** executed directly. SQLite also supplies
the implicit schema table and primary-key indexes, including the WITHOUT ROWID
primary key absent from sqlite_schema. This capture has no sqlite_stat tables,
so no ANALYZE is needed or run. New internal objects require an explicit genuine
SQLite construction path and full comparison, never writable_schema or filtering.

Explicit indexes are created in descending captured `index_list.seq` order per
table so this fixture reproduces and compares those sequence values too. Every
column flag, table flag, index field, auxiliary index column and FK list is checked;
negative controls verify that extra or changed metadata is not silently discarded.
Two CLI invocations must emit identical JSON and leave the synthetic file bytes
and directory entries unchanged.

Storage-dependent `rootpage` values are checked against the fresh file, not the
historical source, whose values the catalog deliberately omits. The historical
`schema_version` cookie is not recreated or overwritten: the test separately
checks that the fresh cookie is positive and compares application_id, encoding
and user_version with this capture. Neither matching DDL nor a schema cookie
proves Things DB29 identity, domain semantics, native write support or sync safety.
The standalone recipe above is not executed by this structure-only test because
it additionally requires application identity and a databaseVersion row.

Run from the repository root (Python 3.11+, SQLite 3.37+):

```sh
PYTHONPATH="$PWD/src" python3 -B -W error::ResourceWarning -m unittest discover -s tests -v
```

## Sources

[1] https://www.sqlite.org/pragma.html
[2] https://www.sqlite.org/schematab.html
