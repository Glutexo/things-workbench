"""Real CLI subprocesses, with synthetic files and explicit paths only."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='things-workbench-cli-')
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "příliš space '?#%.sqlite"
        connection = sqlite3.connect(self.db)
        connection.execute('CREATE TABLE TMTask(uuid TEXT PRIMARY KEY, title TEXT, status INTEGER)')
        connection.execute('INSERT INTO TMTask VALUES (?, ?, ?)', ('A' * 22, 'Synthetic title', 999))
        connection.commit()
        connection.close()

    def run_cli(self, *args):
        env = dict(os.environ)
        # Resolve inherited relative PYTHONPATH before leaving the repository.
        env['PYTHONPATH'] = os.pathsep.join(str(Path(p).resolve()) for p in env.get('PYTHONPATH', '').split(os.pathsep) if p)
        return subprocess.run([sys.executable, '-W', 'error', '-m', 'things_workbench', *args],
                              cwd=self.temp.name, env=env, capture_output=True, text=True, timeout=10)

    def test_schema_json_runs_outside_repository(self):
        result = self.run_cli('--db', str(self.db), 'schema', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        schema = json.loads(result.stdout)
        self.assertTrue(any(o['name'] == 'TMTask' for o in schema['objects']))
        self.assertNotIn('Synthetic title', result.stdout)
        self.assertNotIn(str(self.db), result.stdout)
        self.assertIn('DDL', result.stderr)

    def test_doctor_cli_cannot_claim_sync_safety(self):
        result = self.run_cli('--db', str(self.db), 'doctor', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['sync_safety'], 'not_assessed')
        human = self.run_cli('--db', str(self.db), 'doctor')
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn('not a sync-safety', human.stdout)

    def test_task_list_cli_applies_bounds(self):
        result = self.run_cli('--db', str(self.db), 'tasks', 'list', '--limit', '1', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{'uuid': 'A' * 22, 'title': 'Synthetic title', 'status': 999}])
        page = self.run_cli('--db', str(self.db), 'tasks', 'list', '--offset', '1', '--json')
        self.assertEqual(json.loads(page.stdout), [])
        invalid = self.run_cli('--db', str(self.db), 'tasks', 'list', '--limit', '501')
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn('Traceback', invalid.stderr)

    def test_task_show_cli_distinguishes_not_found_from_bad_input(self):
        result = self.run_cli('--db', str(self.db), 'tasks', 'show', 'A' * 22, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 999)
        absent = self.run_cli('--db', str(self.db), 'tasks', 'show', 'Z' * 22, '--json')
        self.assertEqual(absent.returncode, 3, absent.stderr)
        self.assertEqual(json.loads(absent.stdout), None)
        self.assertIn('not found', absent.stderr)
        invalid = self.run_cli('--db', str(self.db), 'tasks', 'show', 'bad')
        self.assertEqual(invalid.returncode, 2)
        self.assertIn('22 ASCII', invalid.stderr)

    def test_cli_preserves_unexpected_blob_and_infinite_real_values(self):
        connection = sqlite3.connect(self.db)
        connection.execute('UPDATE TMTask SET title=?, status=?', (b'\x00\xff', float('inf')))
        connection.commit()
        connection.close()
        result = self.run_cli('--db', str(self.db), 'tasks', 'show', 'A' * 22, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        self.assertEqual(row['title'], {'sqlite_blob_hex': '00ff'})
        self.assertEqual(row['status'], {'sqlite_real': 'Infinity'})

    def test_cli_errors_are_clean_and_do_not_create_databases(self):
        missing = self.db.parent / 'missing.sqlite'
        for command in (('schema', '--json'), ('doctor', '--json'), ('tasks', 'list', '--json')):
            result = self.run_cli('--db', str(missing), *command)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(missing.exists())
        self.db.write_bytes(b'not SQLite')
        result = self.run_cli('--db', str(self.db), 'schema', '--json')
        self.assertEqual(result.returncode, 2)
        self.assertIn('SQLite inspection failed', result.stderr)
        self.assertNotIn(str(self.db), result.stderr)
        self.assertEqual(self.run_cli('schema', '--json').returncode, 2)
        self.assertEqual(self.run_cli('--db', str(self.db), 'sql', 'DELETE FROM TMTask').returncode, 2)

    def test_cli_symlink_loop_errors_are_clean(self):
        loop = self.db.parent / 'private-loop.sqlite'
        loop.symlink_to(loop.name)
        for command in (('schema', '--json'), ('doctor', '--json'),
                        ('tasks', 'list', '--json'), ('tasks', 'show', 'A' * 22, '--json')):
            with self.subTest(command=command):
                result = self.run_cli('--db', str(loop), *command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('error: '), result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertNotIn(str(loop.parent), result.stderr)
                self.assertNotIn(loop.name, result.stderr)
                self.assertTrue(loop.is_symlink())
                self.assertEqual(loop.readlink(), Path(loop.name))

    def test_import_and_help_do_not_open_databases_network_or_processes(self):
        program = '''
import sys
blocked = {'sqlite3.connect', 'socket.__new__', 'socket.connect', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}
def audit(event, args):
    if event in blocked:
        raise RuntimeError('Forbidden import/help side effect: ' + event)
sys.addaudithook(audit)
import things_workbench
from things_workbench.cli import main
main(['--help'])
'''
        result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('things-workbench', result.stdout)

    def test_terminal_output_escapes_untrusted_titles(self):
        connection = sqlite3.connect(self.db)
        connection.execute('UPDATE TMTask SET title=?', ('\x1b[2J\nSynthetic',))
        connection.commit()
        connection.close()
        for command in (('tasks', 'list'), ('tasks', 'show', 'A' * 22)):
            result = self.run_cli('--db', str(self.db), *command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('\x1b', result.stdout)
            self.assertEqual(len(result.stdout.splitlines()), 1)
