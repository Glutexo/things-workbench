"""Real Darwin ACL observations on new owned fixtures; no native model code."""
import ctypes
import errno
import os
from pathlib import Path
import tempfile
import subprocess
import pwd
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from things_workbench import copies


class ACLObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='acl-observation-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'owned'
        self.root.mkdir(mode=0o700)
        self.lib = copies._acl_library()
        self.original_get = self.lib.acl_get_link_np
        self.calls = []

    def observe(self, action):
        def get(path, kind):
            acl = self.original_get(path, kind)
            error = ctypes.get_errno()  # Save immediately at the real C boundary.
            if os.fsdecode(path) == str(self.root):
                self.calls.append((acl, error))
                action(len(self.calls), acl, error)
            ctypes.set_errno(error)
            return acl
        return patch.object(self.lib, 'acl_get_link_np', side_effect=get)

    def test_checked_pins_ancestor_permissions_before_acl_entry(self):
        child = self.root/'file'
        child.write_bytes(b'owned')
        child.chmod(0o600)
        original = copies.inspect_acl
        fired = []
        def inspect(path, **kwargs):
            if path == self.root and not fired:
                self.root.chmod(0o500)  # Still non-writable, but no longer approved.
                fired.append(path)
            return original(path, **kwargs)
        try:
            with patch.object(copies, 'inspect_acl', side_effect=inspect):
                with self.assertRaises(copies.CopyError):
                    copies.checked(child)
            self.assertEqual(fired, [self.root])
        finally:
            self.root.chmod(0o700)

    def test_one_mkdir_reinspects_whole_acl_observation(self):
        stamps = []
        def once(count, acl, error):
            if count == 1:
                self.assertIsNone(acl)
                self.assertEqual(error, errno.ENOENT)
                stamps.append(self.root.lstat())
                (self.root/'new-child').mkdir(mode=0o700)
                stamps.append(self.root.lstat())
        with self.observe(once):
            try:
                actual = copies.checked(self.root, directory=True)
            except copies.CopyError as exc:
                self.fail(f'benign finite directory activity refused: {exc}')
        self.assertEqual(actual, self.root)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(stamps[0].st_ino, stamps[1].st_ino)
        self.assertNotEqual(stamps[0].st_ctime_ns, stamps[1].st_ctime_ns)

    def test_two_mkdirs_use_last_bounded_attempt(self):
        def twice(count, acl, error):
            if count <= 2:
                self.assertIsNone(acl)
                self.assertEqual(error, errno.ENOENT)
                (self.root/str(count)).mkdir(mode=0o700)
        with self.observe(twice):
            copies.inspect_acl(self.root)
        self.assertEqual(len(self.calls), 3)

    def test_permanent_instability_is_bounded(self):
        def always(count, acl, error):
            self.assertIsNone(acl)
            self.assertEqual(error, errno.ENOENT)
            (self.root/str(count)).mkdir(mode=0o700)
        with self.observe(always):
            with self.assertRaisesRegex(copies.CopyError, 'ACL inspection'):
                copies.inspect_acl(self.root)
        self.assertLessEqual(len(self.calls), 3)
        self.assertGreaterEqual(len(self.calls), 1)

    def test_retry_shares_existing_deadline(self):
        def expire(count, acl, error):
            (self.root/str(count)).mkdir(mode=0o700)
            budget = copies._work_budget.get()
            assert budget is not None
            budget['deadline'] = 0
        with self.assertRaisesRegex(copies.CopyError, 'budget'):
            with copies.work_scope(), self.observe(expire):
                copies.inspect_acl(self.root)
        self.assertEqual(len(self.calls), 1)

    def test_errno_is_saved_before_post_api_stat(self):
        original = Path.lstat
        def lstat(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            ctypes.set_errno(errno.EIO)
            return result
        with patch.object(Path, 'lstat', lstat):
            copies.inspect_acl(self.root)

    def test_unexpected_errno_is_not_retried(self):
        for error in (0, errno.EIO, errno.EACCES, errno.EINTR):
            with self.subTest(errno=error):
                def get(path, kind):
                    ctypes.set_errno(error)
                    return None  # Explicit fault injection; not a real ACL witness.
                with patch.object(self.lib, 'acl_get_link_np', side_effect=get) as call:
                    with self.assertRaisesRegex(copies.CopyError, 'ACL inspection failed'):
                        copies.inspect_acl(self.root)
                self.assertEqual(call.call_count, 1)

    def test_missing_path_is_not_acl_absence(self):
        with self.assertRaises(OSError):
            copies.inspect_acl(self.root/'missing')

    def test_disappearing_path_is_not_retried(self):
        def remove(count, acl, error):
            self.root.rmdir()
        with self.observe(remove):
            with self.assertRaises(OSError):
                copies.inspect_acl(self.root)
        self.assertEqual(len(self.calls), 1)

    def test_replaced_inode_is_not_retried(self):
        original = self.root.lstat()
        def replace(count, acl, error):
            self.root.rename(self.root.with_name('retained-original'))
            self.root.mkdir(mode=0o700)
        with self.observe(replace):
            with self.assertRaises(copies.CopyError):
                copies.inspect_acl(self.root)
        self.assertNotEqual(original.st_ino, self.root.lstat().st_ino)
        self.assertEqual(len(self.calls), 1)

    def test_symlink_replacement_is_not_retried(self):
        def replace(count, acl, error):
            retained = self.root.with_name('retained-original')
            self.root.rename(retained)
            self.root.symlink_to(retained, target_is_directory=True)
        with self.observe(replace):
            with self.assertRaises(copies.CopyError):
                copies.inspect_acl(self.root)
        self.assertEqual(len(self.calls), 1)

    def test_mode_change_is_not_retried(self):
        def change(count, acl, error):
            self.root.chmod(0o500)
        try:
            with self.observe(change):
                with self.assertRaises(copies.CopyError):
                    copies.inspect_acl(self.root)
            self.assertEqual(len(self.calls), 1)
        finally:
            self.root.chmod(0o700)

    def test_flags_change_is_not_retried(self):
        original = self.root.lstat().st_flags
        def change(count, acl, error):
            os.chflags(self.root, original ^ stat.UF_HIDDEN)
        try:
            with self.observe(change):
                with self.assertRaises(copies.CopyError):
                    copies.inspect_acl(self.root)
            self.assertEqual(len(self.calls), 1)
        finally:
            os.chflags(self.root, original)

    def test_owner_or_group_observation_change_is_not_retried(self):
        # Real chown to another uid requires privileges; inject only these stat
        # fields on own fixture, retaining real API, inode, mode and timestamps.
        original = Path.lstat
        for field in ('st_uid', 'st_gid'):
            with self.subTest(field=field):
                seen = []
                def lstat(path, *args, **kwargs):
                    result = original(path, *args, **kwargs)
                    if path == self.root:
                        seen.append(path)
                        if len(seen) > 1:
                            values = {k:getattr(result,k) for k in dir(result) if k.startswith('st_')}
                            values[field] = 0 if values[field] != 0 else 1
                            return SimpleNamespace(**values)
                    return result
                with patch.object(Path, 'lstat', lstat):
                    with self.assertRaises(copies.CopyError):
                        copies.inspect_acl(self.root)
                self.assertEqual(len(seen), 2)

    def test_between_attempt_mode_change_keeps_initial_security_pin(self):
        original = Path.lstat
        seen = []
        def lstat(path, *args, **kwargs):
            if path == self.root:
                seen.append(path)
                if len(seen) == 3:
                    self.root.chmod(0o500)
            return original(path, *args, **kwargs)
        def once(count, acl, error):
            (self.root/'child').mkdir(mode=0o700)
        try:
            with patch.object(Path, 'lstat', lstat), self.observe(once):
                with self.assertRaises(copies.CopyError):
                    copies.inspect_acl(self.root)
            self.assertEqual(len(self.calls), 1)
        finally:
            self.root.chmod(0o700)

    def add_acl(self, path, text):
        result = subprocess.run(['/bin/chmod', '+a', text, str(path)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_acl_added_during_absence_is_reinspected_and_freed(self):
        def grant(count, acl, error):
            if count == 1:
                self.assertIsNone(acl)
                self.assertEqual(error, errno.ENOENT)
                self.add_acl(self.root, pwd.getpwuid(os.getuid()).pw_name+' allow read')
        with self.observe(grant), patch.object(self.lib, 'acl_free', wraps=self.lib.acl_free) as free:
            with self.assertRaises(copies.CopyError):
                copies.inspect_acl(self.root)
        self.assertEqual(len(self.calls), 2)
        self.assertIsNotNone(self.calls[1][0])
        free.assert_called_once_with(self.calls[1][0])

    def test_granting_acl_refused_with_handle_freed(self):
        self.add_acl(self.root, pwd.getpwuid(os.getuid()).pw_name+' allow read')
        with patch.object(self.lib, 'acl_free', wraps=self.lib.acl_free) as free:
            with self.assertRaisesRegex(copies.CopyError, 'granting or unknown ACL refused'):
                copies.inspect_acl(self.root)
        self.assertEqual(free.call_count, 1)

    def test_inherited_granting_acl_is_refused(self):
        self.add_acl(self.root, 'everyone allow list,search,readattr,readextattr,readsecurity,file_inherit,directory_inherit')
        child = self.root/'inherited'
        child.mkdir(mode=0o700)
        with self.assertRaisesRegex(copies.CopyError, 'granting or unknown ACL refused'):
            copies.inspect_acl(child)

    def test_deny_only_acl_retains_existing_behavior_and_frees_handle(self):
        self.add_acl(self.root, 'everyone deny delete')
        self.addCleanup(subprocess.run, ['/bin/chmod', '-N', str(self.root)], check=True, capture_output=True, timeout=5)
        with patch.object(self.lib, 'acl_free', wraps=self.lib.acl_free) as free:
            copies.inspect_acl(self.root)
        self.assertEqual(free.call_count, 1)
