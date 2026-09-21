"""Synthetic complete logical snapshot checks."""
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

class FingerprintTests(unittest.TestCase):
    def test_all_tables_storage_types_and_row_identity(self):
        self.assertIsNotNone(importlib.util.find_spec('things_workbench.fingerprint'), 'fingerprint missing')
        from things_workbench.fingerprint import snapshot
        with tempfile.TemporaryDirectory() as d:
            p = Path(d).resolve() / 'test.sqlite'
            with closing(sqlite3.connect(p)) as c:
                c.executescript('CREATE TABLE a(x); CREATE TABLE b(k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID; INSERT INTO a VALUES (1),(1.0),(NULL); INSERT INTO b VALUES (\'x\',x\'ff\');')
            p.chmod(0o600)
            first = snapshot(p)
            self.assertEqual(first, snapshot(p))
            self.assertEqual(set(first['tables']), {'a','b'})
            self.assertEqual(first['tables']['a']['rows'][0][1], ['integer',1])
            self.assertEqual(first['tables']['a']['rows'][1][1], ['real','0x1.0000000000000p+0'])
            with closing(sqlite3.connect(p)) as c:
                c.execute('UPDATE b SET v=x\'00\''); c.commit()
            self.assertNotEqual(first, snapshot(p))
            side = Path(str(p) + '-wal')
            side.symlink_to(p)
            with self.assertRaisesRegex(ValueError, 'unsafe path'):
                snapshot(p)
            side.unlink()
            with closing(sqlite3.connect(p)) as c:
                c.execute('CREATE TRIGGER extra AFTER INSERT ON a BEGIN UPDATE b SET v=NULL; END')
            with self.assertRaisesRegex(ValueError, 'unsupported schema'):
                snapshot(p)
