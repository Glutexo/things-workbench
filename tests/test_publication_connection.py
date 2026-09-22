"""Real synthetic SQLite transaction ownership; no native acceptance."""
from contextlib import closing
import sqlite3
import tempfile
from pathlib import Path
import unittest
from things_workbench import fingerprint, schema_policy
from things_workbench.copies import canonical, CopyError
from test_schema_policy import schema_fixture


class ConnectionTests(unittest.TestCase):
    def test_snapshot_joins_caller_and_preserves_legacy_shape(self):
        self.assertTrue(hasattr(fingerprint, 'snapshot_connection'))
        modes = [{}, {'isolation_level': None}]
        if hasattr(sqlite3, 'LEGACY_TRANSACTION_CONTROL'):
            modes += [{'autocommit': True}, {'autocommit': False}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve()/'test.sqlite'
            with closing(sqlite3.connect(path)) as db:
                db.executescript("CREATE TABLE a(id INTEGER PRIMARY KEY AUTOINCREMENT,v); INSERT INTO a(v) VALUES (NULL),(1),(1.0),('x'),(x'ff'); UPDATE sqlite_sequence SET seq=100; CREATE TABLE b(x TEXT,y INTEGER,v,PRIMARY KEY(y,x)) WITHOUT ROWID; INSERT INTO b VALUES ('z',2,x'00'),('a',1,'');")
            path.chmod(0o600)
            legacy = fingerprint.snapshot(path)
            for mode in modes:
                with self.subTest(mode=mode), closing(sqlite3.connect(path, **mode)) as db:
                    initial = db.in_transaction
                    self.assertEqual(canonical(fingerprint.snapshot_connection(db)), canonical(legacy))
                    self.assertEqual(db.in_transaction, initial)
                    db.execute('SAVEPOINT caller')
                    db.execute("UPDATE a SET v='pending' WHERE id=1")
                    pending = fingerprint.snapshot_connection(db)
                    self.assertNotEqual(pending, legacy)
                    self.assertTrue(db.in_transaction)
                    db.execute('ROLLBACK TO caller'); db.execute('RELEASE caller')
                    self.assertEqual(fingerprint.snapshot_connection(db), legacy)
                    if db.in_transaction: db.execute('ROLLBACK')

    def test_schema_connection_joins_and_exception_cleanup(self):
        self.assertTrue(hasattr(schema_policy, 'verify_schema_connection'))
        with tempfile.TemporaryDirectory() as tmp:
            path = schema_fixture(Path(tmp).resolve()/'known.sqlite')
            with closing(sqlite3.connect(path, isolation_level=None)) as db:
                self.assertEqual(schema_policy.verify_schema_connection(db), schema_policy.verify_schema(path))
                self.assertFalse(db.in_transaction)
                db.execute('SAVEPOINT caller')
                db.execute('CREATE TABLE unexpected(x)')
                with self.assertRaises(CopyError): schema_policy.verify_schema_connection(db)
                self.assertTrue(db.in_transaction)
                db.execute('ROLLBACK TO caller'); db.execute('RELEASE caller')
                db.execute('CREATE VIEW unexpected AS SELECT 1')
                with self.assertRaises(CopyError): fingerprint.snapshot_connection(db)
                self.assertFalse(db.in_transaction)
                with self.assertRaises(CopyError): schema_policy.verify_schema_connection(db)
                self.assertFalse(db.in_transaction)

    def test_fresh_wal_reads_do_not_leak_owned_snapshot(self):
        self.assertTrue(hasattr(fingerprint, 'snapshot_connection'))
        modes = [{'isolation_level': None}]
        if hasattr(sqlite3, 'LEGACY_TRANSACTION_CONTROL'): modes += [{'autocommit': True}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'wal.sqlite'
            with closing(sqlite3.connect(path, isolation_level=None)) as writer:
                writer.execute('PRAGMA journal_mode=WAL'); writer.execute('CREATE TABLE a(x)')
                for mode in modes:
                    with closing(sqlite3.connect(path, **mode)) as reader:
                        a = fingerprint.snapshot_connection(reader)
                        writer.execute('INSERT INTO a VALUES (1)')
                        self.assertNotEqual(a, fingerprint.snapshot_connection(reader))
                        self.assertFalse(reader.in_transaction)
