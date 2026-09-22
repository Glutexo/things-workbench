"""Synthetic public lifecycle integration. Never native-positive evidence."""
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from test_copy_lifecycle import LifecycleTests
from things_workbench import copies, wording
from things_workbench.fingerprint import snapshot


class PublicationTests(LifecycleTests):
    # Reuse setup, not the inherited Stage-2 tests in discovery below.
    def test_inplace_writer_backup_and_second_process_exclusion(self):
        from things_workbench import publication as pub
        self.assertTrue(hasattr(pub, 'rehearse'))
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        inode = (target/'target.sqlite').stat().st_ino
        run = pub.prepare(self.packet, target, 'one')
        approval = pub.preview(run)['approval_digest']
        reached = []
        import subprocess, sys
        def phase(name, db=None):
            reached.append(name)
            if db is not None and db.in_transaction:
                code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1],timeout=.1);\ntry: c.execute('BEGIN IMMEDIATE')\nexcept sqlite3.OperationalError as e: sys.exit(0 if e.sqlite_errorcode in (5,3850) else 9)\nsys.exit(7)"
                result = subprocess.run([sys.executable, '-B', '-c', code, str(target/'target.sqlite')], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, (name, result.stderr))
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=phase):
            receipt = pub.rehearse(run, approval=approval)
        self.assertEqual(receipt['state'], 'committed_verified')
        self.assertFalse(receipt['live_published'])
        self.assertEqual((target/'target.sqlite').stat().st_ino, inode)
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'output.sqlite'))
        self.assertEqual(snapshot(run/'backup.sqlite'), snapshot(self.packet/'before.sqlite'))
        self.assertIn('first_update', reached)
        self.assertIn('after_check', reached)
        self.assertIn('precommit_revalidated', reached)
        self.assertEqual(self.starts, 1)
        with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)

    def test_reached_failures_are_quarantined_and_never_false_rollback(self):
        from things_workbench import publication as pub
        self.assertTrue(hasattr(pub, 'status'))
        wording.apply_copy(self.packet, self.view['approval_digest'])
        for point in ('first_update', 'after_check', 'commit_intent', 'commit_returned', 'before_readback'):
            with self.subTest(point=point):
                target = pub.create_target(self.packet, self.root/point)
                run = pub.prepare(self.packet, target, 'one')
                approval = pub.preview(run)['approval_digest']
                reached = []
                def fault(name, db=None):
                    if name == point:
                        reached.append(name)
                        raise OSError('injected reached failure')
                with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=fault):
                    with self.assertRaisesRegex(copies.CopyError, 'reconcile required'):
                        pub.rehearse(run, approval=approval)
                self.assertEqual(reached, [point])
                committed = point in ('commit_returned', 'before_readback')
                self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/('output.sqlite' if committed else 'before.sqlite')))
                with patch('sqlite3.connect') as connect:
                    state = pub.status(run)
                    connect.assert_not_called()
                self.assertTrue(state['quarantined'])
                self.assertEqual(state['state'], 'uncertain' if committed else 'rolled_back_verified')
                with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')
                with self.assertRaises(copies.CopyError): copies.import_copy(target/'target.sqlite', self.root/('launder-'+point), declaration='detached-stable-resolved')
        self.assert_preserved()

    def test_authorized_reconciliation_observes_without_replay_and_restores_new_copy(self):
        from things_workbench import publication as pub
        self.assertTrue(hasattr(pub, 'recovery_preview'))
        wording.apply_copy(self.packet, self.view['approval_digest'])
        for point in ('first_update', 'commit_returned', 'foreign'):
            target = pub.create_target(self.packet, self.root/point)
            run = pub.prepare(self.packet, target, 'one')
            approval = pub.preview(run)['approval_digest']
            def stop(name, db=None):
                if name == ('commit_returned' if point == 'foreign' else point):
                    raise RuntimeError('reached')
            with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=stop):
                with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
            if point == 'foreign':
                with closing(sqlite3.connect(target/'target.sqlite')) as db:
                    db.execute("UPDATE TMTask SET title='foreign'"); db.commit()
            present = snapshot(target/'target.sqlite')
            with patch.object(pub, 'verify_schema_connection', return_value='0'*64):
                view = pub.recovery_preview(run, 'assessment', authorize_owned_recovery=True)
                self.assertEqual(view['classification'], {'first_update':'before_present', 'commit_returned':'after_present', 'foreign':'external_conflict'}[point])
                if point == 'foreign':
                    with self.assertRaises(copies.CopyError): pub.reconcile(run/'assessment.json', approval=view['approval_digest'])
                    self.assertTrue(pub.status(run)['quarantined'])
                else:
                    receipt = pub.reconcile(run/'assessment.json', approval=view['approval_digest'])
                    self.assertFalse(receipt['historical_commit_proven'])
                    self.assertFalse(pub.status(run)['quarantined'])
                    restored = pub.restore_copy(run, self.root/('recovery-'+point))
                    self.assertEqual(snapshot(restored), snapshot(self.packet/'before.sqlite'))
            self.assertEqual(snapshot(target/'target.sqlite'), present)
        self.assert_preserved()

    def test_runtime_binding_and_lost_registry_lock_are_fail_closed(self):
        from things_workbench import publication as pub
        self.assertTrue(hasattr(pub, 'runtime_binding'))
        binding = pub.runtime_binding()
        self.assertEqual(set(binding), {'python', 'extension', 'sqlite', 'dependencies', 'version', 'source_id', 'compile_options', 'os'})
        self.assertEqual(binding['version'], sqlite3.sqlite_version)
        self.assertTrue(binding['sqlite'].get('sha256') or binding['sqlite'].get('shared_cache_uuid'))
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        run = pub.prepare(self.packet, target, 'one')
        envelope = copies.load(run/'publication.json')
        self.assertEqual(envelope['engine'], binding)
        (target/'lock').unlink()
        with patch('sqlite3.connect') as connect:
            with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')
            connect.assert_not_called()
        self.assertFalse((target/'lock').exists(), 'lost authority must not recreate a lock')

    def test_deleted_guard_and_active_raw_alias_reads_refuse(self):
        from things_workbench import publication as pub
        self.assertTrue(hasattr(copies, 'sqlite_handle_scope'))
        with closing(sqlite3.connect(self.source, isolation_level=None)) as db:
            db.execute('BEGIN IMMEDIATE')
            with copies.sqlite_handle_scope(self.source):
                with self.assertRaisesRegex(copies.CopyError, 'active SQLite'):
                    copies.identity(self.source)
                with self.assertRaisesRegex(copies.CopyError, 'active SQLite'):
                    wording.native_runtime.sha(self.source)
                self.assertEqual(pub.physical(self.source)['inode'], self.source.stat().st_ino)
            db.execute('ROLLBACK')
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        run = pub.prepare(self.packet, target, 'one')
        approval = pub.preview(run)['approval_digest']
        def fault(name, db=None):
            if name == 'first_update': raise OSError('reached')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=fault):
            with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
        (target/'registry/one.json').unlink()
        with patch('sqlite3.connect') as connect:
            with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')
            connect.assert_not_called()
        self.assertTrue(pub.status(run)['quarantined'])

    def test_real_child_death_reached_boundaries(self):
        from things_workbench import publication as pub
        import subprocess, sys
        wording.apply_copy(self.packet, self.view['approval_digest'])
        for point in ('intent', 'writer_before', 'backup_durable', 'first_update', 'after_check', 'commit_intent', 'commit_returned', 'readback', 'terminal', 'resolved'):
            with self.subTest(point=point):
                target = pub.create_target(self.packet, self.root/point)
                run = pub.prepare(self.packet, target, 'one')
                approval = pub.preview(run)['approval_digest']
                command = [sys.executable, '-B', '-c', 'import sys,runpy;sys.path.insert(0,'+repr(str(Path(__file__).resolve().parent))+');runpy.run_path('+repr(str(Path(__file__).resolve()))+')["publication_worker"]()', str(run), approval, point]
                result = subprocess.run(command, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 73, result.stderr)
                self.assertEqual(copies.load(run/'reached.json')['point'], point)
                committed = point in ('commit_returned', 'readback', 'terminal', 'resolved')
                self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/('output.sqlite' if committed else 'before.sqlite')))
                state = pub.status(run)
                self.assertEqual(state['quarantined'], point != 'resolved')
                if point not in ('intent', 'writer_before', 'resolved'):
                    with patch.object(pub, 'verify_schema_connection', return_value='0'*64):
                        view = pub.recovery_preview(run, 'recover', authorize_owned_recovery=True)
                        pub.reconcile(run/'recover.json', approval=view['approval_digest'])
                    self.assertFalse(pub.status(run)['quarantined'])

    def test_sqlite_full_is_real_and_commit_then_raise_is_uncertain(self):
        from things_workbench import publication as pub
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'full')
        run = pub.prepare(self.packet, target, 'one')
        reached = []
        def full(name, db=None):
            if name == 'backup_durable':
                count = db.execute('PRAGMA page_count').fetchone()[0]
                db.execute('PRAGMA max_page_count='+str(count))
                reached.append(name)
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=full):
            with self.assertRaises(copies.CopyError) as error:
                pub.rehearse(run, approval=pub.preview(run)['approval_digest'])
        self.assertEqual(error.exception.__cause__.sqlite_errorcode, sqlite3.SQLITE_FULL)
        self.assertEqual(reached, ['backup_durable'])
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'before.sqlite'))
        target = pub.create_target(self.packet, self.root/'commit-raise')
        run = pub.prepare(self.packet, target, 'one')
        def commit(db):
            db.execute('COMMIT'); reached.append('real_commit'); raise OSError('after commit')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_commit', side_effect=commit):
            with self.assertRaisesRegex(copies.CopyError, 'uncertain'):
                pub.rehearse(run, approval=pub.preview(run)['approval_digest'])
        self.assertIn('real_commit', reached)
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'output.sqlite'))
        self.assertTrue(pub.status(run)['quarantined'])

    def test_state_schema_and_wal_refuse_without_target_sql(self):
        from things_workbench import publication as pub
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        run = pub.prepare(self.packet, target, 'one')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64):
            pub.rehearse(run, approval=pub.preview(run)['approval_digest'])
        files = sorted((run/'events').iterdir())
        events = [copies.load(p) for p in files]
        events[1]['state'] = 'unknown-state'
        for index, (p, event) in enumerate(zip(files, events)):
            event['previous'] = copies.digest(events[index-1]) if index else None
            if event['state'] == 'resolved': event['data'] = copies.digest(events[index-1])
            p.write_bytes(copies.canonical(event))
        self.assertTrue(pub.status(run)['quarantined'], 'unknown state must not become clearance')
        target = pub.create_target(self.packet, self.root/'wal')
        with closing(sqlite3.connect(target/'target.sqlite')) as db:
            db.execute('PRAGMA journal_mode=WAL')
        actual = (target/'target.sqlite').read_bytes()
        with patch.object(pub, '_completed', wraps=pub._completed):
            with self.assertRaisesRegex(copies.CopyError, 'DELETE-only'):
                pub.prepare(self.packet, target, 'one')
        self.assertEqual((target/'target.sqlite').read_bytes(), actual)

    def test_publication_cli_live_is_sealed_before_payload_access(self):
        from things_workbench.cli import main
        from contextlib import redirect_stderr
        import io
        with patch('sqlite3.connect') as connect, redirect_stderr(io.StringIO()) as output:
            try:
                code = main(['publication', 'publish-live', '--run', '/does/not/exist', '--approve', '0'*64])
            except SystemExit as exc:
                code = exc.code
            self.assertEqual(code, 2)
            self.assertIn('LIVE_PUBLICATION_SEALED_DISABLED', output.getvalue())
            connect.assert_not_called()

    def test_foreign_edits_before_and_after_commit_are_retained(self):
        from things_workbench import publication as pub
        import subprocess, sys
        wording.apply_copy(self.packet, self.view['approval_digest'])
        for point in ('intent', 'commit_returned'):
            target = pub.create_target(self.packet, self.root/point)
            run = pub.prepare(self.packet, target, 'one')
            reached = []
            def foreign(name, db=None):
                if name == point:
                    code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1],timeout=1); c.execute(\"UPDATE TMTask SET title='foreign'\"); c.commit(); c.close()"
                    child = subprocess.run([sys.executable, '-B', '-c', code, str(target/'target.sqlite')], capture_output=True, timeout=5)
                    self.assertEqual(child.returncode, 0, child.stderr)
                    reached.append(point)
            with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=foreign):
                with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=pub.preview(run)['approval_digest'])
            self.assertEqual(reached, [point])
            with closing(sqlite3.connect(target/'target.sqlite')) as db:
                self.assertEqual(db.execute('SELECT title FROM TMTask').fetchone(), ('foreign',))
            self.assertTrue(pub.status(run)['quarantined'])

    def test_backup_and_terminal_durability_failure_keep_independent_guard(self):
        from things_workbench import publication as pub
        import stat
        wording.apply_copy(self.packet, self.view['approval_digest'])
        for point in ('backup_fsync', 'backup_dirsync', 'terminal_fsync', 'terminal_dirsync', 'failure_receipt'):
            target = pub.create_target(self.packet, self.root/point)
            run = pub.prepare(self.packet, target, 'one')
            approval = pub.preview(run)['approval_digest']
            reached = []
            real_fsync, real_event = os.fsync, pub._event
            def failing_sync(fd):
                if point.startswith('backup') and (run/'backup.sqlite').exists():
                    s = os.fstat(fd)
                    is_backup = (s.st_dev, s.st_ino) == ((run/'backup.sqlite').stat().st_dev, (run/'backup.sqlite').stat().st_ino)
                    is_parent = stat.S_ISDIR(s.st_mode) and s.st_ino == run.stat().st_ino
                    if (point == 'backup_fsync' and is_backup) or (point == 'backup_dirsync' and is_parent):
                        reached.append(point); raise OSError('injected backup durability')
                return real_fsync(fd)
            def event(r, a, state, data=None):
                if point.startswith('terminal') and state == 'committed_verified':
                    def fail(fd):
                        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
                        if directory == (point == 'terminal_dirsync'):
                            reached.append(point); raise OSError('injected terminal durability')
                        return real_fsync(fd)
                    with patch.object(copies.os, 'fsync', side_effect=fail): return real_event(r, a, state, data)
                if point == 'failure_receipt' and state in ('uncertain', 'rolled_back_verified'):
                    reached.append(point); raise OSError('failure receipt unavailable')
                return real_event(r, a, state, data)
            def fault(name, db=None):
                if point == 'failure_receipt' and name == 'first_update': raise RuntimeError('reached update')
            with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=fault), patch.object(pub, '_event', side_effect=event), patch.object(copies.os, 'fsync', side_effect=failing_sync):
                with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
            self.assertTrue(reached, point)
            self.assertTrue(pub.status(run)['quarantined'])
            committed = point.startswith('terminal')
            self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/('output.sqlite' if committed else 'before.sqlite')))
            with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')

    def test_process_detection_rechecks_after_commit_intent(self):
        from things_workbench import publication as pub
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        run = pub.prepare(self.packet, target, 'one')
        approval = pub.preview(run)['approval_digest']
        changed = []
        def phase(name, db=None):
            if name == 'commit_intent': changed.append(name)
        def stopped():
            if changed: raise copies.CopyError('simulated process detection')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=phase), patch.object(pub.native_runtime, 'stopped', side_effect=stopped):
            with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
        self.assertEqual(changed, ['commit_intent'])
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'before.sqlite'))

    def test_managed_target_and_destination_approval(self):
        self.assertIsNotNone(importlib.util.find_spec('things_workbench.publication'))
        from things_workbench import publication as pub
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'before.sqlite'))
        with self.assertRaises(copies.CopyError):
            copies.import_copy(target/'target.sqlite', self.root/'launder', declaration='detached-stable-resolved')
        run = pub.prepare(self.packet, target, 'one')
        view = pub.preview(run)
        self.assertNotEqual(view['approval_digest'], self.view['approval_digest'])
        self.assertEqual(view['wording']['after'], self.plan['changes'])
        self.assertEqual(view['target']['path'], str(target/'target.sqlite'))
        with patch('sqlite3.connect') as connect:
            with self.assertRaisesRegex(copies.CopyError, 'LIVE_PUBLICATION_SEALED_DISABLED'):
                pub.publish_live(run, approval=view['approval_digest'])
            connect.assert_not_called()
        self.assert_preserved()


# unittest otherwise repeats all inherited lifecycle tests.
for _name in tuple(vars(LifecycleTests)):
    if _name.startswith('test_'):
        setattr(PublicationTests, _name, None)
del LifecycleTests


def publication_worker():
    """Real child exit using synthetic completed provenance, never native proof."""
    import sys
    from contextlib import ExitStack
    from test_copy_lifecycle import synthetic_verdict
    from things_workbench import publication as pub
    run, approval, point = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    def fault(name, db=None):
        if name == point:
            copies.durable(run/'reached.json', {'point': point})
            os._exit(73)
    with ExitStack() as stack:
        stack.enter_context(patch.object(wording.native_runtime, 'verify', return_value={'synthetic_lifecycle_runtime': True}))
        stack.enter_context(patch.object(wording.native_runtime, 'stopped'))
        stack.enter_context(patch.object(wording.native_runtime, 'run', side_effect=AssertionError('native replay')))
        stack.enter_context(patch.object(wording, 'validate', side_effect=synthetic_verdict))
        stack.enter_context(patch.object(pub, 'verify_schema_connection', return_value='0'*64))
        stack.enter_context(patch.object(pub, '_phase', side_effect=fault))
        pub.rehearse(run, approval=approval)
