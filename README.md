# Things Workbench

An independent toolkit for understanding and working with Things databases without launching the app.

**Status: early read-only implementation.** Includes a Python library, a command-line inspector and a versioned physical database catalog. No write, repair, migration or cloud-sync API is provided. This is not a replacement for Things.

## Install from source

Requires Python 3.11 or later and SQLite 3.37 or later in that Python runtime. Runtime dependencies: Python standard library only. The build uses setuptools.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/things-workbench --help
```

There is no PyPI release yet. Use this checkout rather than assuming a package with the same name on a package index is this project.

## Command line

Always pass an explicit existing database file. There is no automatic account/store discovery. Global options precede the command; `--json` follows the leaf command.

```sh
things-workbench --db /path/to/main.sqlite schema --json
things-workbench --db /path/to/main.sqlite doctor --json
things-workbench --db /path/to/main.sqlite tasks list --limit 50 --offset 0 --json
things-workbench --db /path/to/main.sqlite tasks show YOUR_22_CHARACTER_ID --json
```

Replace `YOUR_22_CHARACTER_ID` with an actual ID; the placeholder itself is not valid. An ID must be exactly 22 ASCII alphanumeric characters and is never normalized. Shape validation does not establish that an ID exists.

- **`schema`** exports objects, DDL, table flags, extended columns, indexes and declared foreign keys, not application records. DDL and defaults can still contain private literals: review before sharing.
- **`doctor`** checks schema readability only. It does not check database integrity, detect a supported Things build, assess synchronization safety or perform repairs.
- **`tasks list/show`** returns raw allowlisted `TMTask` fields: `uuid`, `title`, `type`, `status`, `trashed`, `startDate`, `stopDate`, where present. These results are personal data. Lists include all types/statuses, including trashed rows; there is no inferred “active to-dos only” filter, enum mapping or date conversion. Unknown columns never widen the allowlist.
- Lists default to 50 rows, allow at most 500, and support offsets up to 100,000. Each page is an independent snapshot; pagination is not a stable snapshot across concurrent changes.
- The default cooperative inspection budget is 5 seconds; use global `--timeout` for a positive value up to 60 seconds.
- Exit codes: `0` success, `2` invalid input or inspection failure, `3` task not found (`null` with `--json`).

## Python API

```python
from things_workbench import inspect_schema, doctor, list_tasks, show_task, WorkbenchError

structure = inspect_schema("/path/to/main.sqlite")
report = doctor("/path/to/main.sqlite")
rows = list_tasks("/path/to/main.sqlite", limit=20)
```

`show_task(database, identifier)` returns a row or `None`. All inspection APIs accept `timeout=5.0`; expected input/read failures raise `WorkbenchError`. Stored enum/date values remain uninterpreted. CLI JSON tags unexpected BLOBs and non-finite REAL values rather than silently discarding them.

## Database documentation

The [database guide](docs/database/index.md) links a complete structural catalog for **Things 3.24 / build 32400506 / DB29**, reproduction instructions and topic notes. It distinguishes verified structure, source-reviewed observations, hypotheses and unknown semantics. The catalog is not a vendor specification or certification of all behaviors for that build.

- [Architecture](docs/architecture.md)
- [Support matrix and evidence boundaries](docs/support-matrix.md)
- [Safety and privacy](docs/safety.md)
- [Physical database catalog](docs/database/versions/things-3.24-build-32400506-db29/catalog.md)
- [Machine-readable catalog](docs/database/versions/things-3.24-build-32400506-db29/schema.json)
- [Unknowns and research gaps](docs/database/unknowns.md)

## Development and tests

From the repository root, run the source tests without installation:

```sh
PYTHONPATH="$PWD/src" python3 -B -W error::ResourceWarning -m unittest discover -s tests -v
```

Or install in a virtual environment first and run the same unittest command with that environment's Python, without `PYTHONPATH`. Tests use synthetic databases, not your Things account. Use a private temporary directory outside the checkout; tests honor Python's temporary-directory configuration.

The initial implementation was exercised on Python 3.11 and 3.14, including installed-wheel CLI use outside the repository. Physical-schema documentation and synthetic reader tests are separate evidence; neither establishes public-package write or cloud-sync support.

## Safety and privacy

SQLite connections use `mode=ro`, `query_only`, ordinary WAL-aware locking and bounded read transactions. No `immutable` shortcut, writable fallback, checkpoint or repair is performed. This is SQL read-only behavior, **not** a guarantee of zero filesystem effects: SQLite may use shared-memory reader marks, locks or sidecars. Keep originals and use a consistent private backup for research. Do not copy only `main.sqlite` away from an active WAL and assume the copy is current.

Never commit databases, sidecars, account settings, authentication material, raw synchronization payloads, personal task content or private execution records. `.gitignore` is a guardrail, not a privacy audit. Every export needs review before publication, including DDL/defaults.

Development is separate from any existing installation. No app launch, cloud operation, credentials or scheduler change is needed by this toolkit. Future mutation support must be separately reviewed and include compatibility checks, previews, concurrency protection, verified publication and recovery.

## Independence and license

This is an unofficial project, not affiliated with or endorsed by Cultured Code. Things is the product being studied, not software distributed by this repository. No open-source license has been selected yet.
