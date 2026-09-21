"""Complete typed SQLite snapshots; no omitted application tables."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from .copies import CopyError, checked


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
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as c:
        c.execute('PRAGMA query_only=ON')
        c.execute('BEGIN')
        try:
            if c.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise CopyError('database integrity refused')
            schema = c.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
            if any(r[0] in ('trigger','view') for r in schema):
                raise CopyError('unsupported schema object')
            headers = {k:c.execute('PRAGMA '+k).fetchone()[0] for k in ('application_id','user_version','encoding','page_size','auto_vacuum')}
            tables = {}
            for db, name, kind, count, wr, strict in c.execute('PRAGMA table_list').fetchall():
                if db != 'main' or name == 'sqlite_schema':
                    continue
                if kind != 'table':
                    raise CopyError('unsupported schema table')
                columns = c.execute('PRAGMA table_xinfo('+quote(name)+')').fetchall()
                if any(r[6] or r[1].lower() in ('rowid','oid','_rowid_') for r in columns):
                    raise CopyError('unsupported schema column')
                names = [r[1] for r in columns]
                keys = [r[1] for r in sorted(columns, key=lambda r:r[5]) if r[5]] if wr else ['rowid']
                if not keys:
                    raise CopyError('unsupported schema identity')
                projection = names if wr else ['rowid',*names]
                rows = c.execute('SELECT '+','.join(map(quote,projection))+' FROM '+quote(name)+' ORDER BY '+','.join(map(quote,keys))).fetchall()
                tables[name] = {'columns': projection, 'layout': [list(r) for r in columns], 'without_rowid': bool(wr), 'strict': bool(strict), 'rows': [[value(v) for v in r] for r in rows]}
            return {'schema':[list(r) for r in schema], 'headers':headers, 'tables':tables}
        finally:
            if c.in_transaction:
                c.execute('ROLLBACK')
