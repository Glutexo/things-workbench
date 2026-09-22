"""Synthetic after_check recovery: receipt-only status under ACL activity."""
import ctypes
import errno
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import unittest
from unittest.mock import patch

from things_workbench import copies, publication as pub, wording
from things_workbench.fingerprint import snapshot


class ACLStatusTests(unittest.TestCase):
    def test_reconciled_status_reinspects_activity_without_sql_or_mutation(self):
        from test_publication import PublicationTests
        case = PublicationTests('test_real_child_death_reached_boundaries')
        self.addCleanup(case.doCleanups)
        case.setUp()
        wording.apply_copy(case.packet, case.view['approval_digest'])
        target = pub.create_target(case.packet, case.root/'after_check')
        run = pub.prepare(case.packet, target, 'one')
        approval = pub.preview(run)['approval_digest']
        command = [sys.executable, '-B', '-W', 'error::ResourceWarning', '-c',
                   'import sys;sys.path.insert(0,'+repr(str(Path(__file__).resolve().parent))+');from test_publication import publication_worker;publication_worker()',
                   str(run), approval, 'after_check']
        child = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 73, child.stderr)
        self.assertEqual(copies.load(run/'reached.json'), {'point':'after_check'})
        self.assertTrue(pub.status(run)['quarantined'])
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64):
            view = pub.recovery_preview(run, 'recover', authorize_owned_recovery=True)
            self.assertEqual(view['classification'], 'before_present')
            pub.reconcile(run/'recover.json', approval=view['approval_digest'])
        before_events = {p.name:p.read_bytes() for p in (run/'events').iterdir()}
        before = snapshot(target/'target.sqlite')
        self.assertEqual(before, snapshot(case.packet/'before.sqlite'))
        states = [json.loads(v)['state'] for _,v in sorted(before_events.items())]
        self.assertEqual(states[-2:], ['reconciled','resolved'])
        original_target = pub._target
        lib = copies._acl_library()
        original_get = lib.acl_get_link_np
        observations = []
        def get(path, kind):
            acl = original_get(path, kind)
            error = ctypes.get_errno()
            if os.fsdecode(path) == str(case.root):
                if not observations:
                    self.assertIsNone(acl)
                    self.assertEqual(error, errno.ENOENT)
                    first = case.root.lstat()
                    (case.root/'one-benign-child').mkdir(mode=0o700)
                    second = case.root.lstat()
                    self.assertEqual(first.st_ino, second.st_ino)
                    self.assertNotEqual(first.st_ctime_ns, second.st_ctime_ns)
                observations.append((acl,error))
            ctypes.set_errno(error)
            return acl
        def target_with_activity(*args, **kwargs):
            with patch.object(lib, 'acl_get_link_np', side_effect=get):
                return original_target(*args, **kwargs)
        with patch.object(pub, '_target', side_effect=target_with_activity), patch('sqlite3.connect', side_effect=AssertionError('receipt-only status opened SQLite')) as connect:
            state = pub.status(run)
            connect.assert_not_called()
        self.assertEqual(state['state'], 'reconciled')
        self.assertFalse(state['quarantined'])
        self.assertGreaterEqual(len(observations), 2)
        with patch('sqlite3.connect', side_effect=AssertionError('receipt-only status opened SQLite')):
            self.assertFalse(pub.status(run)['quarantined'])
        # An actually unverified ACL still quarantines. Arm inside _target so
        # status's outside-try run check is not what this assertion exercises.
        grants = []
        def target_with_acl(*args, **kwargs):
            if not grants:
                result = subprocess.run(['/bin/chmod', '+a', pwd.getpwuid(os.getuid()).pw_name+' allow read', str(case.root)], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                grants.append(True)
            return original_target(*args, **kwargs)
        try:
            with patch.object(pub, '_target', side_effect=target_with_acl), patch('sqlite3.connect', side_effect=AssertionError('receipt-only status opened SQLite')):
                refused = pub.status(run)
            self.assertTrue(refused['quarantined'])
            # Persistent granting ACL also prevents reading retained events;
            # unlike a transient refusal, it cannot prove even 'resolved'.
            self.assertEqual(refused['state'], 'unknown')
        finally:
            if grants:
                subprocess.run(['/bin/chmod', '-N', str(case.root)], check=True, capture_output=True, timeout=5)
        self.assertEqual(before_events, {p.name:p.read_bytes() for p in (run/'events').iterdir()})
        self.assertEqual(before, snapshot(target/'target.sqlite'))
        self.assertFalse(pub.status(run)['quarantined'])
        self.assertEqual(case.starts, 1, 'synthetic mutation must not replay')
