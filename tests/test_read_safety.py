"""Integration safety regressions for the previously introduced read boundary."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from things_workbench import WorkbenchError, doctor, inspect_schema, list_tasks, show_task


class ReadSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='things-workbench-safety-')
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'synthetic.sqlite'
        self.writer = sqlite3.connect(self.db, isolation_level=None)
        self.addCleanup(self.writer.close)
        self.writer.execute('CREATE TABLE TMTask (uuid TEXT PRIMARY KEY, title TEXT, status INTEGER)')
        self.writer.execute('INSERT INTO TMTask VALUES (?, ?, ?)', ('A' * 22, 'Synthetic', 901))

    def test_wal_commits_are_visible_without_immutable_bypass(self):
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.execute('PRAGMA wal_autocheckpoint=0')
        self.writer.execute('CREATE TABLE wal_only (id INTEGER)')
        self.writer.execute('UPDATE TMTask SET status=902')
        self.assertTrue(Path(str(self.db) + '-wal').exists())
        schema = inspect_schema(self.db)
        self.assertIn('wal_only', {obj['name'] for obj in schema['objects']})
        self.assertEqual(show_task(self.db, 'A' * 22)['status'], 902)

    def test_schema_is_one_snapshot_during_concurrent_ddl(self):
        self.writer.execute('PRAGMA journal_mode=WAL')
        # Materialize WAL/SHM using the fixture writer. Some SQLite builds refuse
        # mode=ro cold WAL without sidecars; the reader must never repair that.
        self.writer.execute('UPDATE TMTask SET status=902')
        connect = sqlite3.connect
        commits = []

        def observe(*args, **kwargs):
            connection = connect(*args, **kwargs)
            def trace(sql):
                # sqlite_schema rows have already been fetched at this point.
                if sql == 'PRAGMA main.table_list' and not commits:
                    self.writer.execute('ALTER TABLE TMTask ADD COLUMN late_column TEXT')
                    self.writer.execute('CREATE TABLE late_table(id)')
                    commits.append(True)
            connection.set_trace_callback(trace)
            return connection

        with patch('sqlite3.connect', side_effect=observe):
            original = inspect_schema(self.db)
        self.assertEqual(commits, [True])
        self.assertNotIn('late_table', {t['name'] for t in original['tables']})
        task = next(t for t in original['tables'] if t['name'] == 'TMTask')
        self.assertNotIn('late_column', {c['name'] for c in task['columns']})
        refreshed = inspect_schema(self.db)
        self.assertIn('late_table', {t['name'] for t in refreshed['tables']})
        task = next(t for t in refreshed['tables'] if t['name'] == 'TMTask')
        self.assertIn('late_column', {c['name'] for c in task['columns']})

    def test_inspection_never_selects_application_rows(self):
        connect = sqlite3.connect
        reads = []
        def guarded(*args, **kwargs):
            connection = connect(*args, **kwargs)
            def authorize(action, arg1, arg2, database, source):
                if action == sqlite3.SQLITE_READ:
                    reads.append((arg1, arg2))
                    if arg1 not in ('sqlite_master', 'sqlite_schema'):
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection.set_authorizer(authorize)
            return connection
        with patch('sqlite3.connect', side_effect=guarded):
            inspect_schema(self.db)
            doctor(self.db)
        self.assertTrue(reads)
        self.assertEqual({table for table, column in reads}, {'sqlite_master'})

    def test_reads_leave_database_and_wal_bytes_unchanged(self):
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.execute('PRAGMA wal_autocheckpoint=0')
        self.writer.execute('UPDATE TMTask SET status=903')
        paths = (self.db, Path(str(self.db) + '-wal'))
        before = {p: p.read_bytes() for p in paths}
        names = {p.name for p in self.db.parent.iterdir()}
        inspect_schema(self.db)
        doctor(self.db)
        list_tasks(self.db)
        show_task(self.db, 'A' * 22)
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertEqual(names, {p.name for p in self.db.parent.iterdir()})
        # SHM reader marks/locks are SQLite-managed, not a byte-stability promise.

    def test_quote_and_uri_characters_are_literal_file_names(self):
        self.writer.close()
        original = self.db.read_bytes()
        for name in ('space číselník.sqlite', 'a?#%&=.sqlite', "a'\".sqlite", 'file:literal.sqlite'):
            with self.subTest(name=name):
                path = self.db.parent / name
                path.write_bytes(original)
                before = set(self.db.parent.iterdir())
                self.assertEqual(list_tasks(path)[0]['status'], 901)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(before, set(self.db.parent.iterdir()))

    def test_optional_unknown_columns_do_not_expand_task_allowlist(self):
        self.writer.execute('ALTER TABLE TMTask ADD COLUMN future_secret BLOB')
        self.writer.execute('UPDATE TMTask SET future_secret=?', (b'synthetic-secret',))
        self.assertEqual(set(list_tasks(self.db)[0]), {'uuid', 'title', 'status'})
        exported = next(t for t in inspect_schema(self.db)['tables'] if t['name'] == 'TMTask')
        self.assertIn('future_secret', {c['name'] for c in exported['columns']})

    def test_virtual_hidden_columns_are_not_dropped(self):
        try:
            self.writer.execute('CREATE VIRTUAL TABLE search USING fts5(content)')
        except sqlite3.OperationalError as error:
            if 'no such module' in str(error):
                self.skipTest('This SQLite build does not provide FTS5')
            raise
        table = next(t for t in inspect_schema(self.db)['tables'] if t['name'] == 'search')
        self.assertEqual(table['table_list']['type'], 'virtual')
        self.assertTrue(any(column['hidden'] == 1 for column in table['columns']))

    def test_without_rowid_task_table_remains_readable(self):
        self.writer.execute('DROP TABLE TMTask')
        self.writer.execute('CREATE TABLE TMTask (uuid TEXT PRIMARY KEY, status INTEGER) WITHOUT ROWID')
        self.writer.execute('INSERT INTO TMTask VALUES (?, ?)', ('B' * 22, 1001))
        self.assertEqual(list_tasks(self.db), [{'uuid': 'B' * 22, 'status': 1001}])
        self.assertEqual(show_task(self.db, 'B' * 22)['status'], 1001)

    def test_lock_failure_is_bounded_and_connection_is_released(self):
        self.writer.execute('BEGIN EXCLUSIVE')
        try:
            with self.assertRaises(WorkbenchError):
                inspect_schema(self.db)
        finally:
            self.writer.execute('ROLLBACK')
        self.assertTrue(inspect_schema(self.db)['objects'])
