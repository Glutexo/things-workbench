"""Complete typed SQLite snapshots; no omitted application tables."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from .copies import CopyError, checked, sqlite_handle_scope
from . import copies


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def value(v):
    if v is None:
        return ['null', None]
    if type(v) is int:
        return ['integer', v]
    if type(v) is float:
        return ['real', v.hex()]
    if type(v) is str:
        return ['text', v]
    if type(v) is bytes:
        return ['blob', v.hex()]
    raise CopyError('unsupported SQLite value')


def snapshot(path):
    path = checked(path)
    for suffix in ('-wal','-shm','-journal'):
        side = Path(str(path)+suffix)
        if os.path.lexists(side):
            checked(side)
    with sqlite_handle_scope(path), closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as c:
        c.execute('PRAGMA query_only=ON')
        return snapshot_connection(c)


def snapshot_connection(c):
    with copies.sql_budget(c):
        return _snapshot_connection(c)


def _snapshot_connection(c):
    """Join caller state; close only our own snapshot with explicit SQL."""
    owned = not c.in_transaction
    if owned:
        c.execute('BEGIN')
    row_count = 0; byte_count = 0
    def rows(cursor):
        nonlocal row_count, byte_count
        result = []
        for row in cursor:
            encoded_size = len(copies.canonical([value(v) for v in row]))
            copies.check_budget(row_count=1, byte_count=encoded_size)
            row_count += 1
            byte_count += encoded_size
            if row_count > copies.MAX_SNAPSHOT_ROWS: raise CopyError('snapshot row budget exceeded')
            if byte_count > copies.MAX_SNAPSHOT_BYTES: raise CopyError('snapshot byte budget exceeded')
            result.append(row)
        return result
    try:
        if c.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise CopyError('database integrity refused')
        schema = rows(c.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name'))
        if any(r[0] in ('trigger','view') for r in schema):
            raise CopyError('unsupported schema object')
        headers = {k:c.execute('PRAGMA '+k).fetchone()[0] for k in ('application_id','user_version','encoding','page_size','auto_vacuum')}
        tables = {}
        for db, name, kind, count, wr, strict in rows(c.execute('PRAGMA table_list')):
            if db != 'main' or name == 'sqlite_schema':
                continue
            if kind != 'table':
                raise CopyError('unsupported schema table')
            columns = rows(c.execute('PRAGMA table_xinfo('+quote(name)+')'))
            if any(r[6] or r[1].lower() in ('rowid','oid','_rowid_') for r in columns):
                raise CopyError('unsupported schema column')
            names = [r[1] for r in columns]
            keys = [r[1] for r in sorted(columns, key=lambda r:r[5]) if r[5]] if wr else ['rowid']
            if not keys:
                raise CopyError('unsupported schema identity')
            projection = names if wr else ['rowid',*names]
            data = rows(c.execute('SELECT '+','.join(map(quote,projection))+' FROM '+quote(name)+' ORDER BY '+','.join(map(quote,keys))))
            tables[name] = {'columns': projection, 'layout': [list(r) for r in columns], 'without_rowid': bool(wr), 'strict': bool(strict), 'rows': [[value(v) for v in r] for r in data]}
        return {'schema':[list(r) for r in schema], 'headers':headers, 'tables':tables}
    finally:
        if owned and c.in_transaction:
            c.set_progress_handler(None, 0)
            c.execute('ROLLBACK')
