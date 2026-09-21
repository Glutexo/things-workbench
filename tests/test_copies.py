"""Synthetic ownership tests; not native Things acceptance."""
from contextlib import closing
import hashlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest


class CopyTests(unittest.TestCase):
    def test_detached_wal_backup_finalizes_only_owned_destination(self):
        from things_workbench.copies import backup, identity
        from things_workbench.fingerprint import snapshot
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            source = root / 'detached-wal.sqlite'
            source.touch(mode=0o600)
            with closing(sqlite3.connect(source)) as db:
                self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
                db.execute('CREATE TABLE synthetic(value TEXT)')
                db.execute('INSERT INTO synthetic VALUES (?)', ('exact 😀\r\n',))
                db.commit()
            source.chmod(0o600)
            initial = identity(source)
            expected = snapshot(source)
            destination = backup(source, root / 'output.sqlite')
            self.assertEqual(identity(source), initial)
            self.assertEqual(snapshot(destination), expected)
            for suffix in ('-wal', '-shm', '-journal'):
                self.assertFalse(os.path.lexists(str(destination) + suffix))

    def test_import_is_exclusive_private_complete_backup(self):
        self.assertIsNotNone(importlib.util.find_spec('things_workbench.copies'), 'copy import not implemented')
        from things_workbench.copies import import_copy, verify_copy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'detached #%.sqlite'
            with closing(sqlite3.connect(source)) as c:
                c.execute('CREATE TABLE sample (a TEXT, b BLOB, PRIMARY KEY(a,b)) WITHOUT ROWID')
                c.execute('INSERT INTO sample VALUES (?,?)', ('synthetic', b'\x00\xff'))
                c.commit()
            source.chmod(0o600)
            # Detached WAL-mode backups may retain harmless SHM with no WAL.
            (root / (source.name + '-shm')).write_bytes(b'synthetic-shared-memory')
            (root / (source.name + '-shm')).chmod(0o600)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            copied = import_copy(source, root / 'owned', declaration='detached-stable-resolved')
            self.assertEqual(copied, root / 'owned' / 'source.sqlite')
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
            self.assertEqual(copied.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(verify_copy(copied.parent)['state'], 'imported')
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            with self.assertRaises(ValueError):
                import_copy(source, copied.parent, declaration='detached-stable-resolved')
            with closing(sqlite3.connect(copied)) as c:
                self.assertEqual(c.execute('SELECT * FROM sample').fetchone(), ('synthetic', b'\x00\xff'))


if __name__ == '__main__':
    unittest.main()
