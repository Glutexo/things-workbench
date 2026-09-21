"""Catalog/exporter integration using only the fixed, reviewed public fixture.

Never discover a Things store or read private rows. DDL reconstruction belongs
only in these tests, not in the deployed exporter or a caller-SQL interface.
"""
from collections import Counter
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from things_workbench import inspect_schema


ROOT = Path(__file__).resolve().parents[1]
VERSION = ROOT / 'docs/database/versions/things-3.24-build-32400506-db29'


def numeric_rows(markdown):
    """Read physical metadata rows, excluding headings and separator rows."""
    return [
        [cell.strip() for cell in line.strip().strip('|').split('|')]
        for line in markdown.splitlines() if re.match(r'^\| -?\d+ \|', line)
    ]


class SchemaDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((VERSION / 'schema.json').read_text(encoding='utf-8'))
        self.markdown = (VERSION / 'catalog.md').read_text(encoding='utf-8')

    def test_catalog_covers_every_table_column_index_and_ddl(self):
        sections = re.findall(r'^## `([^`]+)`\n(.*?)(?=^## |\Z)',
                              self.markdown, re.MULTILINE | re.DOTALL)
        self.assertCountEqual([name for name, _ in sections],
                              [table['name'] for table in self.catalog['tables']])
        by_name = dict(sections)
        objects = {obj['name']: obj for obj in self.catalog['objects']}
        self.assertEqual(len(objects), len(self.catalog['objects']))
        self.assertCountEqual(
            re.findall(r'^```sql\n(.*?)\n```', self.markdown, re.MULTILINE | re.DOTALL),
            [obj['sql'] for obj in self.catalog['objects'] if obj['sql'] is not None],
        )
        for table in self.catalog['tables']:
            with self.subTest(table=table['name']):
                section = by_name[table['name']]
                self.assertIn('**Role (', section)
                self.assertIn(
                    f"Type: `{table['type']}`; columns: `{table['ncol']}`; "
                    f"WITHOUT ROWID (`wr`): `{table['wr']}`; STRICT: `{table['strict']}`.",
                    section,
                )
                columns_text, rest = section.split('### Declared foreign keys\n', 1)
                rows = numeric_rows(columns_text)
                self.assertEqual(len(rows), len(table['columns']))
                for row, column in zip(rows, table['columns']):
                    self.assertEqual(len(row), 8)
                    self.assertEqual(row[:7], [
                        str(column['cid']), f"`{column['name']}`",
                        column['type'] or '(empty)', str(column['notnull']),
                        '(none)' if column['dflt_value'] is None else f"`{column['dflt_value']}`",
                        str(column['pk']), str(column['hidden']),
                    ])
                    self.assertRegex(row[7], r'^\*\*(unknown|hypothesis|verified/[^*]+|observed/source-reviewed)\*\* — .+')
                foreign_keys, rest = rest.split('### Index inventory\n', 1)
                # This fixed capture has no declared FKs. A future declaration
                # must update its prose and this assertion, never be ignored.
                self.assertEqual(table['foreign_keys'], [])
                self.assertEqual(foreign_keys.strip(), 'None.')
                indexes_text, table_ddl = rest.split('### Table DDL\n', 1)
                index_sections = re.findall(r'^#### `([^`]+)`\n(.*?)(?=^#### |\Z)',
                                            indexes_text, re.MULTILINE | re.DOTALL)
                self.assertCountEqual([name for name, _ in index_sections],
                                      [index['name'] for index in table['indexes']])
                by_index = dict(index_sections)
                if not table['indexes']:
                    self.assertEqual(indexes_text.strip(), 'None.')
                for index in table['indexes']:
                    description = by_index[index['name']]
                    self.assertIn(', '.join(f'`{key}={index[key]}`' for key in
                                           ('seq', 'unique', 'origin', 'partial')) + '.', description)
                    self.assertEqual(numeric_rows(description), [
                        [str(column['seqno']), str(column['cid']),
                         '(null)' if column['name'] is None else f"`{column['name']}`",
                         str(column['desc']), column['coll'], str(column['key'])]
                        for column in index['columns']
                    ])
                    obj = objects.get(index['name'])
                    if obj is None or obj['sql'] is None:
                        self.assertIn('No separate CREATE INDEX SQL; key structure is retained above.', description)
                    else:
                        self.assertIn('```sql\n' + obj['sql'] + '\n```', description)
                if table['name'] == 'sqlite_schema':
                    self.assertIn('Implicit SQLite schema table; no CREATE TABLE entry.', table_ddl)
                else:
                    self.assertIn('```sql\n' + objects[table['name']]['sql'] + '\n```', table_ddl)

    def test_extraction_documents_package_envelope_bridge(self):
        extraction = (ROOT / 'docs/database/extraction.md').read_text(encoding='utf-8')
        heading = '### Package CLI envelope, version 1'
        self.assertIn(heading, extraction)
        bridge = extraction.split(heading, 1)[1].split('\n## Sources', 1)[0]
        documented = re.findall(r'^\| `([^`]+)` \| `([^`]+)` \|', bridge, re.MULTILINE)
        self.assertEqual(documented, [
            ('format_version', 'catalog_format_version'),
            ('semantics', 'not present'),
            ('sharing_warning', 'not present'),
            ('objects', 'objects'),
            ('objects[].rootpage', 'not present'),
            ('tables[].name', 'tables[].name'),
            ('tables[].table_list', 'tables[]'),
            ('tables[].columns', 'tables[].columns'),
            ('tables[].indices', 'tables[].indexes'),
            ('tables[].foreign_keys', 'tables[].foreign_keys'),
            ('not emitted', 'application'),
            ('not emitted', 'database_format'),
            ('not emitted', 'sqlite_metadata'),
        ])
        for required in ('sqlite_sequence', 'AUTOINCREMENT', 'index_list.seq',
                         'schema_version', 'rootpage', 'structure-only',
                         'tests/test_schema_docs.py'):
            self.assertIn(required, bridge)
        self.assertIn('PYTHONPATH="$PWD/src" python3 -B -W error::ResourceWarning '
                      '-m unittest discover -s tests -v', bridge)

    def test_documented_totals_are_computed_from_complete_inventory(self):
        tables, objects = self.catalog['tables'], self.catalog['objects']
        application_tables = [table for table in tables if not table['name'].startswith('sqlite_')]
        kinds = Counter(obj['type'] for obj in objects)
        expected = {
            'application_tables': len(application_tables),
            'table_list_entries': len(tables),
            'columns': sum(len(table['columns']) for table in tables),
            'application_columns': sum(len(table['columns']) for table in application_tables),
            'schema_objects': len(objects), 'schema_tables': kinds['table'],
            'schema_indexes': kinds['index'],
            'index_list_entries': sum(len(table['indexes']) for table in tables),
            'foreign_keys': sum(len(table['foreign_keys']) for table in tables),
            'views': kinds['view'], 'triggers': kinds['trigger'],
        }
        entries = re.findall(r'^- ([a-z_]+): \*\*(\d+)\*\*$', self.markdown, re.MULTILINE)
        self.assertEqual(len(entries), len(expected))
        self.assertEqual({key: int(value) for key, value in entries}, expected)


class SchemaExporterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((VERSION / 'schema.json').read_text(encoding='utf-8'))
        temporary = tempfile.TemporaryDirectory(prefix='things-workbench-catalog-')
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / 'structure-only.sqlite'
        self.assertFalse(self.db.exists())
        objects = self.catalog['objects']
        self.assertEqual({obj['type'] for obj in objects}, {'table', 'index'})
        self.assertEqual(
            {obj['name'] for obj in objects if obj['type'] == 'table' and obj['name'].startswith('sqlite_')},
            {'sqlite_sequence'},
        )
        by_name = {obj['name']: obj for obj in objects}
        with closing(sqlite3.connect(self.db)) as connection:
            for obj in objects:
                if obj['type'] == 'table' and obj['name'] != 'sqlite_sequence':
                    self.assertTrue(obj['sql'].startswith('CREATE TABLE '))
                    connection.execute(obj['sql'])
            # sqlite_sequence is created by the catalog's AUTOINCREMENT DDL;
            # sqlite_schema and implicit PK indexes are also made by SQLite.
            # Recreate explicit indexes in reverse recorded seq order so the
            # returned index_list.seq is tested too, not silently normalized.
            for table in self.catalog['tables']:
                for index in sorted(table['indexes'], key=lambda item: item['seq'], reverse=True):
                    if index['origin'] == 'c':
                        ddl = by_name[index['name']]['sql']
                        self.assertTrue(ddl.startswith('CREATE INDEX '))
                        connection.execute(ddl)
            connection.commit()
            self.metadata = {
                key: connection.execute('PRAGMA main.' + key).fetchone()[0]
                for key in ('application_id', 'encoding', 'schema_version', 'user_version')
            }
            self.rootpages = dict(connection.execute('SELECT name, rootpage FROM main.sqlite_schema'))
            # These are NEW synthetic tables, never application/personal stores.
            # No metadata rows are invented to claim Things format detection.
            for table in self.catalog['tables']:
                if table['name'] != 'sqlite_schema':
                    name = '"' + table['name'].replace('"', '""') + '"'
                    self.assertEqual(connection.execute('SELECT count(*) FROM ' + name).fetchone()[0], 0)
        self.before_bytes = self.db.read_bytes()
        self.before_files = {path.name for path in self.db.parent.iterdir()}

    def assert_catalog_parity(self, exported):
        self.assertEqual(set(exported), {'format_version', 'semantics', 'sharing_warning', 'objects', 'tables'})
        self.assertEqual(exported['format_version'], 1)
        self.assertEqual(exported['semantics'], 'uninterpreted')
        self.assertEqual(exported['sharing_warning'],
                         'Review before sharing: schema DDL and defaults may contain private literals.')
        self.assertEqual(set(self.catalog), {
            'catalog_format_version', 'application', 'database_format', 'sqlite_metadata', 'objects', 'tables',
        })
        self.assertEqual(self.catalog['catalog_format_version'], 1)
        objects = []
        for obj in exported['objects']:
            obj = dict(obj)
            self.assertEqual(set(obj), {'type', 'name', 'tbl_name', 'rootpage', 'sql'})
            # Only rootpage is excluded from catalog equality, explicitly. Its
            # actual export is independently checked against this fresh file.
            rootpage = obj.pop('rootpage')
            self.assertIs(type(rootpage), int)
            self.assertEqual(rootpage, self.rootpages[obj['name']])
            objects.append(obj)
        self.assertEqual(objects, self.catalog['objects'])
        tables = []
        for table in exported['tables']:
            self.assertEqual(set(table), {'name', 'table_list', 'columns', 'indices', 'foreign_keys'})
            self.assertEqual(table['name'], table['table_list']['name'])
            self.assertEqual(set(table['table_list']), {'schema', 'name', 'type', 'ncol', 'wr', 'strict'})
            tables.append({**table['table_list'], 'columns': table['columns'],
                           'indexes': table['indices'], 'foreign_keys': table['foreign_keys']})
        # Full dictionaries/lists preserve unknown extras, null SQL/defaults,
        # ordinal flags, index seq/auxiliary columns and every declared FK.
        self.assertEqual(tables, self.catalog['tables'])

    def assert_unchanged(self):
        self.assertEqual(self.db.read_bytes(), self.before_bytes)
        self.assertEqual({path.name for path in self.db.parent.iterdir()}, self.before_files)

    def test_exporter_matches_complete_reconstructed_physical_catalog(self):
        first = inspect_schema(self.db)
        self.assert_catalog_parity(first)
        self.assertEqual(inspect_schema(self.db), first)
        self.assert_unchanged()
        captured = dict(self.catalog['sqlite_metadata'])
        actual = dict(self.metadata)
        self.assertEqual(set(captured), set(actual))
        # A fresh sequence of CREATE statements does not recreate historical
        # schema cookies; do not overwrite that cookie or claim it is DB29.
        self.assertIs(type(captured.pop('schema_version')), int)
        self.assertGreater(actual.pop('schema_version'), 0)
        self.assertEqual(actual, captured)

    def test_cli_json_matches_api_and_is_repeatable_without_writes(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        command = [sys.executable, '-B', '-W', 'error::ResourceWarning', '-m',
                   'things_workbench', '--db', str(self.db), 'schema', '--json']
        first = subprocess.run(command, cwd=self.db.parent, env=env,
                               capture_output=True, text=True, timeout=10)
        second = subprocess.run(command, cwd=self.db.parent, env=env,
                                capture_output=True, text=True, timeout=10)
        for result in (first, second):
            self.assertEqual(result.returncode, 0, result.stderr)
            decoded = json.loads(result.stdout)
            self.assertEqual(result.stderr, decoded['sharing_warning'] + '\n')
            self.assert_catalog_parity(decoded)
            self.assertEqual(decoded, inspect_schema(self.db))
            self.assertNotIn(str(self.db), result.stdout)
        self.assertEqual(first.stdout, second.stdout)
        self.assert_unchanged()

    def test_parity_check_rejects_extras_and_changed_nested_metadata(self):
        original = inspect_schema(self.db)
        mutations = [
            lambda value: value.update(extra='unexpected'),
            lambda value: value['objects'].append(dict(value['objects'][0])),
            lambda value: value['objects'][0].update(extra='unexpected'),
            lambda value: value['objects'][0].update(sql='changed DDL'),
            lambda value: value['tables'].append(deepcopy(value['tables'][0])),
            lambda value: value['tables'][0].update(extra='unexpected'),
            lambda value: value['tables'][0]['table_list'].update(strict=1),
            lambda value: value['tables'][0]['columns'][0].update(hidden=1),
            lambda value: value['tables'][0]['columns'][0].update(extra='unexpected'),
            lambda value: value['tables'][0]['indices'].pop(),
            lambda value: value['tables'][0]['indices'][0].update(seq=99),
            lambda value: value['tables'][0]['indices'][1]['columns'].pop(),
            lambda value: value['tables'][0]['foreign_keys'].append({'id': 0}),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(mutation=number):
                changed = deepcopy(original)
                mutate(changed)
                with self.assertRaises(AssertionError):
                    self.assert_catalog_parity(changed)
        self.assert_catalog_parity(original)
