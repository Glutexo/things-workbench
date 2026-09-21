"""Synthetic SQLite fixtures only; never discover or open a personal store."""
import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='things-workbench-test-')
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'synthetic.sqlite'
        with sqlite3.connect(self.db) as connection:
            connection.execute('CREATE TABLE example (id INTEGER PRIMARY KEY, value TEXT)')
        connection.close()

    def api(self, name):
        try:
            module = importlib.import_module('things_workbench')
        except ModuleNotFoundError:
            module = None
        function = getattr(module, name, None)
        self.assertTrue(callable(function), f'Missing API: {name}')
        return function

    def test_schema_exports_ddl_without_personal_rows(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute('INSERT INTO example(value) VALUES (?)', ('ROW_SENTINEL_DO_NOT_EXPORT',))
        connection.close()
        result = self.api('inspect_schema')(self.db)
        table = next(obj for obj in result['objects'] if obj['name'] == 'example')
        self.assertEqual(table['type'], 'table')
        self.assertIn('CREATE TABLE example', table['sql'])
        self.assertNotIn('ROW_SENTINEL_DO_NOT_EXPORT', json.dumps(result))
        self.assertNotIn(str(self.db), json.dumps(result))

    def test_schema_preserves_complete_physical_metadata(self):
        with sqlite3.connect(self.db) as connection:
            connection.executescript('''
                CREATE TABLE "odd' table" (
                    a TEXT, b INTEGER, extra TEXT DEFAULT 'DDL_LITERAL',
                    generated TEXT GENERATED ALWAYS AS (a || b) STORED,
                    PRIMARY KEY (b, a), FOREIGN KEY (b) REFERENCES example(id)
                ) WITHOUT ROWID;
                CREATE INDEX "odd index" ON "odd' table"(a COLLATE NOCASE DESC, (b + 1)) WHERE b > 0;
                CREATE VIEW sample_view AS SELECT id FROM example;
                CREATE TRIGGER example_trigger AFTER INSERT ON example BEGIN SELECT 1; END;
            ''')
        connection.close()
        inspect = self.api('inspect_schema')
        result = inspect(self.db)
        self.assertIn('tables', result)
        table = next(t for t in result['tables'] if t['name'] == "odd' table")
        self.assertEqual(table['table_list']['wr'], 1)
        self.assertEqual([c['name'] for c in table['columns']], ['a', 'b', 'extra', 'generated'])
        self.assertEqual(table['columns'][3]['hidden'], 3)
        self.assertEqual([c['pk'] for c in table['columns'][:2]], [2, 1])
        self.assertEqual(table['columns'][2]['dflt_value'], "'DDL_LITERAL'")
        self.assertEqual(table['foreign_keys'][0]['table'], 'example')
        index = next(i for i in table['indices'] if i['name'] == 'odd index')
        self.assertEqual(index['partial'], 1)
        self.assertEqual(index['columns'][0]['desc'], 1)
        self.assertEqual(index['columns'][1]['cid'], -2)
        self.assertIn('view', {o['type'] for o in result['objects']})
        self.assertIn('trigger', {o['type'] for o in result['objects']})
        self.assertEqual(result, inspect(self.db))

    def test_inspection_owns_bounded_read_only_snapshot(self):
        from unittest.mock import patch
        statements = []
        settings = []
        write_rejected = []
        connect = sqlite3.connect

        def observe(*args, **kwargs):
            connection = connect(*args, **kwargs)
            def trace(sql):
                statements.append(sql)
                if sql.startswith('SELECT type'):
                    settings.append((connection.in_transaction,
                                     connection.execute('PRAGMA query_only').fetchone()[0]))
                    try:
                        connection.execute('CREATE TABLE forbidden (id)')
                    except sqlite3.OperationalError:
                        write_rejected.append(True)
                    else:
                        write_rejected.append(False)
            connection.set_trace_callback(trace)
            return connection

        with patch('sqlite3.connect', side_effect=observe):
            self.api('inspect_schema')(self.db)
        self.assertEqual(settings, [(True, 1)])
        self.assertEqual(write_rejected, [True])
        self.assertIn('BEGIN', statements)
        self.assertIn('ROLLBACK', statements)

    def test_database_failures_are_actionable_without_creating_files(self):
        module = importlib.import_module('things_workbench')
        error = getattr(module, 'WorkbenchError', None)
        self.assertTrue(isinstance(error, type), 'Missing public WorkbenchError')
        missing = self.db.parent / 'missing.sqlite'
        before = set(self.db.parent.iterdir())
        with self.assertRaisesRegex(error, 'existing SQLite database'):
            module.inspect_schema(missing)
        self.assertEqual(before, set(self.db.parent.iterdir()))
        self.db.write_bytes(b'not a sqlite database')
        with self.assertRaisesRegex(error, 'SQLite inspection failed') as caught:
            module.inspect_schema(self.db)
        self.assertNotIn(str(self.db), str(caught.exception))

    def test_inspection_deadline_is_enforced(self):
        from unittest.mock import patch
        import inspect
        inspect_schema = self.api('inspect_schema')
        self.assertIn('timeout', inspect.signature(inspect_schema).parameters)
        import things_workbench as workbench
        with patch.object(workbench, 'monotonic', side_effect=[0.0] + [2.0] * 100):
            with self.assertRaisesRegex(workbench.WorkbenchError, 'time limit'):
                inspect_schema(self.db, timeout=1.0)
        # Aborted inspection did not keep the DB locked.
        with sqlite3.connect(self.db, timeout=0.1) as connection:
            connection.execute('CREATE TABLE after_abort (id)')
        connection.close()
        for invalid in (0, -1, float('nan'), float('inf'), True, '1', 61):
            with self.subTest(timeout=invalid), self.assertRaises(workbench.WorkbenchError):
                inspect_schema(self.db, timeout=invalid)

    def test_doctor_reports_only_read_only_inspection_not_sync_safety(self):
        report = self.api('doctor')(self.db)
        self.assertIs(report['read_only'], True)
        self.assertEqual(report['inspection'], 'schema_only')
        self.assertEqual(report['sync_safety'], 'not_assessed')
        self.assertEqual(report['integrity'], 'not_checked')
        self.assertEqual(report['repair'], 'not_available')
        self.assertEqual(report['sqlite_version'], sqlite3.sqlite_version)
        self.assertNotIn(str(self.db), json.dumps(report))
        self.assertIn('not', report['warning'])

    def test_deadline_checked_between_small_metadata_queries(self):
        from unittest.mock import patch
        import things_workbench as workbench
        clock = [0.0]
        statements = []
        connect = sqlite3.connect
        def observe(*args, **kwargs):
            connection = connect(*args, **kwargs)
            def trace(sql):
                statements.append(sql)
                if sql.startswith('SELECT type'):
                    clock[0] = 2.0
            connection.set_trace_callback(trace)
            return connection
        with patch('sqlite3.connect', side_effect=observe), patch.object(workbench, 'monotonic', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(workbench.WorkbenchError, 'time limit'):
                workbench.inspect_schema(self.db, timeout=1.0)
        self.assertNotIn('PRAGMA main.table_list', statements)
        self.assertIn('ROLLBACK', statements)

    def test_sqlite_without_table_list_support_is_refused(self):
        from unittest.mock import patch
        import things_workbench as workbench
        with patch.object(sqlite3, 'sqlite_version_info', (3, 36, 0)):
            with self.assertRaisesRegex(workbench.WorkbenchError, 'SQLite 3.37'):
                workbench.inspect_schema(self.db)

    def test_schema_export_labels_uninterpreted_structure(self):
        result = self.api('inspect_schema')(self.db)
        self.assertEqual(result.get('format_version'), 1)
        self.assertEqual(result['semantics'], 'uninterpreted')
        self.assertIn('private literals', result['sharing_warning'])
