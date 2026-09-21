"""Raw task reads against synthetic stores, without inferred Things semantics."""
import importlib
from pathlib import Path
import sqlite3
import tempfile
import unittest


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='things-workbench-tasks-')
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'synthetic.sqlite'
        self.ids = ['A' * 21 + letter for letter in 'BCDE']
        connection = sqlite3.connect(self.db)
        connection.execute('''CREATE TABLE TMTask (
            uuid TEXT PRIMARY KEY, title TEXT, type INTEGER, status INTEGER,
            trashed INTEGER, startDate INTEGER, stopDate REAL, unknown_secret TEXT,
            notes TEXT
        )''')
        connection.executemany('INSERT INTO TMTask VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', [
            (key, 'Synthetic ' + str(index), 900 + index, 700 + index, index % 2,
             123456 + index, None, 'UNKNOWN_PRIVATE', 'PRIVATE_NOTES')
            for index, key in enumerate(self.ids)
        ])
        connection.commit()
        connection.close()

    def api(self, name):
        function = getattr(importlib.import_module('things_workbench'), name, None)
        self.assertTrue(callable(function), f'Missing API: {name}')
        return function

    def test_list_returns_only_allowlisted_raw_fields(self):
        result = self.api('list_tasks')(self.db)
        self.assertEqual([r['uuid'] for r in result], self.ids)
        self.assertEqual(result[0], {
            'uuid': self.ids[0], 'title': 'Synthetic 0', 'type': 900,
            'status': 700, 'trashed': 0, 'startDate': 123456, 'stopDate': None,
        })

    def test_list_enforces_bounded_pagination(self):
        import inspect
        import things_workbench as workbench
        listing = self.api('list_tasks')
        self.assertIn('limit', inspect.signature(listing).parameters)
        self.assertEqual([r['uuid'] for r in listing(self.db, limit=2, offset=1)], self.ids[1:3])
        self.assertEqual(listing(self.db, limit=1, offset=4), [])
        for kwargs in ({'limit': 0}, {'limit': 501}, {'limit': True}, {'limit': 2.5},
                       {'offset': -1}, {'offset': 100001}, {'offset': '0'}, {'offset': False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(workbench.WorkbenchError):
                listing(self.db, **kwargs)

    def test_show_looks_up_exact_syntactically_valid_id(self):
        import things_workbench as workbench
        show = self.api('show_task')
        self.assertEqual(show(self.db, self.ids[2])['status'], 702)
        self.assertIsNone(show(self.db, 'Z' * 22))
        for invalid in ('', 'A' * 21, 'A' * 23, ' ' + self.ids[0],
                        self.ids[0] + '\n', 'é' * 22, "' OR 1=1 --", 123, None):
            with self.subTest(identifier=invalid), self.assertRaisesRegex(workbench.WorkbenchError, '22 ASCII'):
                show(self.db, invalid)
        self.assertNotIn('unknown_secret', show(self.db, self.ids[0]))

    def test_task_reads_refuse_unsubstantiated_layouts(self):
        import things_workbench as workbench
        connection = sqlite3.connect(self.db)
        connection.execute('DROP TABLE TMTask')
        connection.execute('CREATE VIEW TMTask AS SELECT uuid, title FROM hidden_source')
        connection.execute('CREATE TABLE hidden_source (uuid TEXT, title TEXT)')
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(workbench.WorkbenchError, 'Unsupported TMTask layout'):
            workbench.list_tasks(self.db)
        layouts = (
            'CREATE TABLE TMTask (title TEXT)',
            'CREATE TABLE TMTask (uuid TEXT, title TEXT)',
            'CREATE TABLE TMTask (uuid TEXT, part INTEGER, PRIMARY KEY (uuid, part))',
            'CREATE TABLE TMTask (uuid TEXT PRIMARY KEY, title TEXT GENERATED ALWAYS AS (uuid))',
        )
        for ddl in layouts:
            with self.subTest(ddl=ddl):
                connection = sqlite3.connect(self.db)
                connection.execute('DROP VIEW IF EXISTS TMTask') if 'VIEW' in connection.execute(
                    "SELECT sql FROM sqlite_schema WHERE name='TMTask'"
                ).fetchone()[0] else connection.execute('DROP TABLE TMTask')
                connection.execute(ddl)
                connection.commit()
                connection.close()
                with self.assertRaisesRegex(workbench.WorkbenchError, 'Unsupported TMTask layout'):
                    workbench.list_tasks(self.db)
                with self.assertRaisesRegex(workbench.WorkbenchError, 'Unsupported TMTask layout'):
                    workbench.show_task(self.db, self.ids[0])

    def test_default_and_maximum_list_bounds_with_many_rows(self):
        connection = sqlite3.connect(self.db)
        connection.executemany('INSERT INTO TMTask (uuid, title, status) VALUES (?, ?, ?)',
                               [('B' + str(index).zfill(21), 'Synthetic', 1234) for index in range(600)])
        connection.commit()
        connection.close()
        listing = self.api('list_tasks')
        self.assertEqual(len(listing(self.db)), 50)
        self.assertEqual(len(listing(self.db, limit=500)), 500)
