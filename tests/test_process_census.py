"""Synthetic lifecycle with the real process-census exception seam."""
from contextlib import redirect_stderr, redirect_stdout
import io
import subprocess
import unittest
from unittest.mock import patch
from test_copy_lifecycle import LifecycleTests
from things_workbench import copies, wording, native_runtime as nr, publication as pub, publication_cli
from things_workbench.fingerprint import snapshot

REAL_STOPPED = nr.stopped


def unavailable():
    with patch.object(nr.subprocess, 'run', side_effect=subprocess.TimeoutExpired(
            ['private-sensitive-command'], 5, output=b'private-sensitive-output')):
        REAL_STOPPED()


class ProcessCensusTests(LifecycleTests):
    def test_timeout_api_and_all_preintent_cli_entries_refuse_without_write(self):
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root / 'target')
        run = pub.prepare(self.packet, target, 'one')
        approval = pub.preview(run)['approval_digest']
        before = snapshot(target / 'target.sqlite')
        operations = [
            ('create-target', ['--completed-packet', str(self.packet), '--new-root', str(self.root / 'never-created')],
             lambda: pub.create_target(self.packet, self.root / 'never-created')),
            ('prepare', ['--completed-packet', str(self.packet), '--target-root', str(target), '--name', 'never-prepared'],
             lambda: pub.prepare(self.packet, target, 'never-prepared')),
            ('rehearse', ['--run', str(run), '--approve', approval],
             lambda: pub.rehearse(run, approval=approval)),
        ]
        for operation, args, api in operations:
            with self.subTest(operation=operation), patch.object(nr, 'stopped', side_effect=unavailable):
                with self.subTest(boundary='API'):
                    with self.assertRaisesRegex(copies.CopyError, 'process census unavailable'):
                        api()
                out, err = io.StringIO(), io.StringIO()
                with self.subTest(boundary='CLI'), redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(publication_cli.main([operation, *args]), 2)
                self.assertEqual(out.getvalue(), '')
                self.assertEqual(err.getvalue(), 'publication refused: process census unavailable; stopped state unproven\n')
            self.assertEqual(snapshot(target / 'target.sqlite'), before)
            self.assertFalse((run / 'intent.json').exists())
            self.assertFalse((target / 'registry/one.json').exists())
            self.assertFalse((self.root / 'never-created').exists())
            self.assertFalse((target / 'runs/never-prepared').exists())
        self.assert_preserved()


    def test_postintent_census_failure_retains_quarantine_and_commit_uncertainty(self):
        wording.apply_copy(self.packet, self.view['approval_digest'])
        for point in ('intent', 'commit_intent', 'commit_returned'):
            with self.subTest(point=point):
                target = pub.create_target(self.packet, self.root / point)
                run = pub.prepare(self.packet, target, 'one')
                approval = pub.preview(run)['approval_digest']
                reached = []
                failed = False
                def phase(name, db=None):
                    nonlocal failed
                    if name == point:
                        failed = True
                        reached.append(name)
                def census():
                    if failed:
                        unavailable()
                out, err = io.StringIO(), io.StringIO()
                with patch.object(pub, 'verify_schema_connection', return_value='0' * 64), \
                     patch.object(pub, '_phase', side_effect=phase), \
                     patch.object(nr, 'stopped', side_effect=census), \
                     redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(publication_cli.main(['rehearse', '--run', str(run), '--approve', approval]), 2)
                self.assertEqual(reached, [point])
                self.assertEqual(out.getvalue(), '')
                self.assertEqual(err.getvalue(), 'publication refused: publication uncertain; reconcile required\n')
                self.assertTrue((run / 'intent.json').exists())
                state = pub.status(run)
                self.assertTrue(state['quarantined'])
                self.assertNotEqual(state['state'], 'rolled_back_verified')
                self.assertEqual(snapshot(target / 'target.sqlite'), snapshot(self.packet / (
                    'output.sqlite' if point == 'commit_returned' else 'before.sqlite')))
                with self.assertRaises(copies.CopyError):
                    pub.prepare(self.packet, target, 'blocked')


class CensusDomainTests(unittest.TestCase):
    def test_unavailable_and_non_stopped_results_never_grant_stopped(self):
        for error in (subprocess.TimeoutExpired('sensitive', 5), OSError('sensitive'),
                      subprocess.SubprocessError('sensitive')):
            with self.subTest(error=type(error).__name__), patch.object(nr.subprocess, 'run', side_effect=error):
                with self.assertRaisesRegex(copies.CopyError, '^process census unavailable; stopped state unproven$'):
                    REAL_STOPPED()
        for code in (0, 2, -15):
            with self.subTest(code=code), patch.object(nr.subprocess, 'run', return_value=subprocess.CompletedProcess([], code)):
                with self.assertRaises(copies.CopyError):
                    REAL_STOPPED()
        with patch.object(nr.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertIsNone(REAL_STOPPED())


for _name in tuple(vars(LifecycleTests)):
    if _name.startswith('test_'):
        setattr(ProcessCensusTests, _name, None)
del LifecycleTests
