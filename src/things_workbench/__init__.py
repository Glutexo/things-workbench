"""Explicit-path, read-only inspection of SQLite Things stores."""
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
import math
import re
import sqlite3


class WorkbenchError(Exception):
    """An expected inspection or input failure, safe for a CLI diagnostic."""


class _Reader:
    """Internal deadline-checked query handle, never returned by a public API."""

    def __init__(self, connection, deadline):
        self._connection = connection
        self._deadline = deadline

    def execute(self, sql, parameters=()):
        if monotonic() >= self._deadline:
            raise WorkbenchError('SQLite inspection exceeded its time limit.')
        return self._connection.execute(sql, parameters)


@contextmanager
def _snapshot(db, timeout=5.0):
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise WorkbenchError('SQLite 3.37 or newer is required for complete table_list inspection.')
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 60):
        raise WorkbenchError('timeout must be a finite number greater than 0 and at most 60 seconds.')
    deadline = monotonic() + timeout
    connection = None
    try:
        try:
            path = Path(db).resolve()
        except RuntimeError as error:
            # Python 3.11 reports symlink loops as RuntimeError, not OSError.
            raise WorkbenchError('Choose an existing SQLite database file with --db.') from error
        if not path.is_file():
            raise WorkbenchError('Choose an existing SQLite database file with --db.')
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                     isolation_level=None, timeout=0.25)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('BEGIN')
        connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
        yield _Reader(connection, deadline)
        if monotonic() >= deadline:
            raise WorkbenchError('SQLite inspection exceeded its time limit.')
    except (sqlite3.Error, OSError) as error:
        if isinstance(error, sqlite3.Error) and getattr(error, 'sqlite_errorcode', None) == sqlite3.SQLITE_INTERRUPT:
            raise WorkbenchError('SQLite inspection exceeded its time limit.') from error
        raise WorkbenchError('SQLite inspection failed; check file format, permissions and locks.') from error
    finally:
        if connection is not None:
            connection.set_progress_handler(None, 0)
            try:
                if connection.in_transaction:
                    connection.execute('ROLLBACK')
            finally:
                connection.close()


def _pragma(connection, pragma, name=None):
    # Only fixed internal pragma names are passed here; identifiers are quoted.
    argument = '' if name is None else '("' + name.replace('"', '""') + '")'
    return [dict(row) for row in connection.execute('PRAGMA main.' + pragma + argument)]


def inspect_schema(db, *, timeout=5.0):
    """Export SQLite DDL, not row data. DDL may itself contain private literals."""
    with _snapshot(db, timeout) as connection:
        objects = [dict(row) for row in connection.execute(
            'SELECT type, name, tbl_name, rootpage, sql FROM main.sqlite_schema ORDER BY type, name'
        )]
        tables = []
        for layout in sorted(_pragma(connection, 'table_list'), key=lambda row: row['name']):
            if layout['schema'] != 'main':
                continue
            name = layout['name']
            indices = sorted(_pragma(connection, 'index_list', name), key=lambda row: row['name'])
            for index in indices:
                index['columns'] = _pragma(connection, 'index_xinfo', index['name'])
            tables.append({
                'name': name, 'table_list': layout,
                'columns': _pragma(connection, 'table_xinfo', name),
                'indices': indices,
                'foreign_keys': _pragma(connection, 'foreign_key_list', name),
            })
        return {
            'format_version': 1, 'semantics': 'uninterpreted',
            'sharing_warning': 'Review before sharing: schema DDL and defaults may contain private literals.',
            'objects': objects, 'tables': tables,
        }


def doctor(db, *, timeout=5.0):
    """Inspect schema readability; do not diagnose sync, integrity or repairs."""
    schema = inspect_schema(db, timeout=timeout)
    return {
        'read_only': True, 'inspection': 'schema_only',
        'sync_safety': 'not_assessed', 'integrity': 'not_checked',
        'repair': 'not_available', 'sqlite_version': sqlite3.sqlite_version,
        'schema_object_count': len(schema['objects']),
        'warning': 'Read-only schema inspection is not a sync-safety or integrity assessment. No repair is performed.',
    }


TASK_FIELDS = ('uuid', 'title', 'type', 'status', 'trashed', 'startDate', 'stopDate')


def _task_select(connection):
    layout = next((row for row in _pragma(connection, 'table_list')
                   if row['schema'] == 'main' and row['name'] == 'TMTask'), None)
    columns = _pragma(connection, 'table_xinfo', 'TMTask')
    primary = [column['name'] for column in columns if column['pk']]
    if (layout is None or layout['type'] != 'table' or primary != ['uuid']
            or any(column['hidden'] for column in columns if column['name'] in TASK_FIELDS)):
        raise WorkbenchError('Unsupported TMTask layout: require an ordinary table with sole uuid primary key and non-generated allowlisted fields.')
    names = {row['name'] for row in columns}
    return ', '.join('"' + name + '"' for name in TASK_FIELDS if name in names)


def list_tasks(db, *, limit=50, offset=0, timeout=5.0):
    """Read allowlisted fields as stored; do not interpret enum or date values."""
    if type(limit) is not int or not 1 <= limit <= 500:
        raise WorkbenchError('limit must be an integer between 1 and 500.')
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise WorkbenchError('offset must be an integer between 0 and 100000.')
    with _snapshot(db, timeout) as connection:
        select = _task_select(connection)
        return [dict(row) for row in connection.execute(
            'SELECT ' + select + ' FROM main.TMTask ORDER BY uuid COLLATE BINARY LIMIT ? OFFSET ?',
            (limit, offset),
        )]


def show_task(db, identifier, *, timeout=5.0):
    """Read an exact 22-ASCII-alphanumeric ID; return None when absent.

    This is a lexical input shape, not proof of a real Things identifier.
    """
    if not isinstance(identifier, str) or re.fullmatch(r'[A-Za-z0-9]{22}', identifier) is None:
        raise WorkbenchError('Task ID must contain exactly 22 ASCII alphanumeric characters; no normalization is performed.')
    with _snapshot(db, timeout) as connection:
        select = _task_select(connection)
        row = connection.execute(
            'SELECT ' + select + ' FROM main.TMTask WHERE uuid COLLATE BINARY = ? LIMIT 1',
            (identifier,),
        ).fetchone()
        return dict(row) if row is not None else None
