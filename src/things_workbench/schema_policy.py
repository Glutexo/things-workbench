"""Reviewed build-32400506 schema, preserving caller transaction ownership."""
from contextlib import closing
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import plistlib
import sqlite3
from .copies import CopyError, checked, sqlite_handle_scope

DESCRIPTOR_SHA256 = '380679da007e54d578e501532a258433e1d90769734a014584352ca4e4d2baab'


def verify_schema(path):
    path = checked(path)
    for suffix in ('-wal', '-shm', '-journal'):
        side = Path(str(path)+suffix)
        if os.path.lexists(side): checked(side)
    with sqlite_handle_scope(path), closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)) as c:
        c.execute('PRAGMA query_only=ON')
        return verify_schema_connection(c)


def verify_schema_connection(c):
    from .copies import sql_budget
    with sql_budget(c):
        return _verify_schema_connection(c)


def _verify_schema_connection(c):
    """Check the independent descriptor on the caller's actual SQL state."""
    owned = not c.in_transaction
    try:
        from .native_runtime import resource_bytes
        data = resource_bytes(files('things_workbench').joinpath('native/schema_32400506.json'))
        digest = hashlib.sha256(data).hexdigest()
        if digest != DESCRIPTOR_SHA256:
            raise CopyError('reviewed schema descriptor changed')
        descriptor = json.loads(data)
        if owned: c.execute('BEGIN')
        schema = [list(row) for row in c.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name')]
        headers = {key:c.execute('PRAGMA '+key).fetchone()[0] for key in descriptor['headers']}
        if schema != descriptor['schema'] or headers != descriptor['headers']:
            raise CopyError('unsupported known schema or header')
        rows = c.execute("SELECT value FROM Meta WHERE key='databaseVersion'").fetchall()
        if len(rows) != 1 or type(rows[0][0]) not in (bytes, str):
            raise CopyError('unsupported database format')
        try:
            encoded = rows[0][0].encode('utf-8') if type(rows[0][0]) is str else rows[0][0]
            version = plistlib.loads(encoded)
        except Exception as exc:
            raise CopyError('undecodable database format') from exc
        if type(version) is not int or version != descriptor['database_version']:
            raise CopyError('unsupported database format')
        return digest
    except CopyError:
        raise
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        raise CopyError('known schema verification failed') from exc
    finally:
        if owned and c.in_transaction:
            c.set_progress_handler(None, 0)
            c.execute('ROLLBACK')
