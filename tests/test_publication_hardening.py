"""Synthetic SQLite hardening; mocked native provenance is not acceptance."""
from pathlib import Path
import unittest
from unittest.mock import patch
from test_copy_lifecycle import LifecycleTests
from things_workbench import copies, wording, publication as pub


class HardeningTests(LifecycleTests):
    def prepared(self):
        wording.apply_copy(self.packet, self.view['approval_digest'])
        target = pub.create_target(self.packet, self.root/'target')
        run = pub.prepare(self.packet, target, 'one')
        return target, run, pub.preview(run)['approval_digest']

    def resolved_before(self):
        target, run, approval = self.prepared()
        def stop(name, db=None):
            if name == 'first_update': raise OSError('reached')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64):
            with patch.object(pub, '_phase', side_effect=stop):
                with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
            assessment = pub.recovery_preview(run, 'assessment', authorize_owned_recovery=True)
            pub.reconcile(run/'assessment.json', approval=assessment['approval_digest'])
        return target, run

    def test_missing_retained_terminal_authority_blocks_new_run(self):
        target, run = self.resolved_before()
        for name in ('publication.json', 'backup.sqlite', 'assessment.json'):
            with self.subTest(name=name):
                path = run/name
                path.rename(run/(name+'.retained'))
                try:
                    with patch('sqlite3.connect') as connect:
                        self.assertTrue(pub.status(run)['quarantined'])
                        with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')
                        connect.assert_not_called()
                finally: (run/(name+'.retained')).rename(path)

    def test_contradictory_terminal_observation_blocks_new_run(self):
        target, run = self.resolved_before()
        files = sorted((run/'events').iterdir())
        events = [copies.load(p) for p in files]
        terminal = next(e for e in events if e['state'] == 'reconciled')
        terminal['data']['classification'] = 'after_present'
        terminal['data']['current'] = copies.load(run/'publication.json')['after']
        for i, (path, event) in enumerate(zip(files, events)):
            event['previous'] = copies.digest(events[i-1]) if i else None
            if event['state'] == 'resolved': event['data'] = copies.digest(events[i-1])
            path.write_bytes(copies.canonical(event))
        with patch('sqlite3.connect') as connect:
            self.assertTrue(pub.status(run)['quarantined'])
            with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')
            connect.assert_not_called()

    def test_event_approval_mismatch_never_returns_success(self):
        target, run, approval = self.prepared()
        reached = []
        def tamper(name, db=None):
            if name == 'intent':
                reached.append(name)
                path = run/'events/0000.json'
                event = copies.load(path); event['approval'] = 'f'*64
                path.write_bytes(copies.canonical(event))
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=tamper):
            with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
        self.assertEqual(reached, ['intent'])
        from things_workbench.fingerprint import snapshot
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'before.sqlite'))
        self.assertTrue(pub.status(run)['quarantined'])

    def test_nested_types_are_strict_without_uncaught_exceptions(self):
        import copy
        target, run, approval = self.prepared()
        original = copies.load(run/'publication.json')
        cases = [(('wording', 'history_verified'), 1), (('policy', 'fullfsync'), True),
                 (('source',), []), (('source', 'packet'), 5),
                 (('engine', 'python', 'size'), float(original['engine']['python']['size']))]
        for keys, value in cases:
            with self.subTest(keys=keys):
                record = copy.deepcopy(original); item = record
                for key in keys[:-1]: item = item[key]
                item[keys[-1]] = value
                (run/'publication.json').write_bytes(copies.canonical(record))
                error = None
                try: pub.preview(run)
                except Exception as exc: error = exc
                self.assertIsInstance(error, copies.CopyError)
        (run/'publication.json').write_bytes(copies.canonical(original))

    def test_receipt_types_refuse_without_sql_or_type_errors(self):
        import copy
        target, run = self.resolved_before()
        cases = [(target/'registry/one.json', ('target', 'nlink'), True),
                 (run/'intent.json', ('target', 'nlink'), True),
                 (run/'events/0000.json', ('state',), []),
                 (run/'assessment.json', ('run', 'owner'), float(run.stat().st_uid))]
        for path, keys, value in cases:
            with self.subTest(file=path.name, keys=keys):
                original = path.read_bytes(); record = copies.load(path); item = record
                for key in keys[:-1]: item = item[key]
                item[keys[-1]] = value; path.write_bytes(copies.canonical(record))
                try:
                    with patch('sqlite3.connect') as connect:
                        result = None
                        try: result = pub.status(run)
                        except Exception as exc: result = type(exc).__name__
                        self.assertIsInstance(result, dict)
                        self.assertTrue(result['quarantined']); connect.assert_not_called()
                finally: path.write_bytes(original)

    def test_prepared_status_is_distinct_from_missing_started_evidence(self):
        target, run, approval = self.prepared()
        with patch('sqlite3.connect') as connect:
            self.assertEqual(pub.status(run), {'state': 'prepared', 'quarantined': False, 'target_inspected': False})
            connect.assert_not_called()
        original = (run/'publication.json').read_bytes()
        (run/'publication.json').write_bytes(b'{')
        self.assertTrue(pub.status(run)['quarantined'])
        (run/'publication.json').write_bytes(original)
        copies.durable(run/'intent.json', {'partial': True})
        with patch('sqlite3.connect') as connect:
            self.assertTrue(pub.status(run)['quarantined']); connect.assert_not_called()
        with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')

    def assert_competitor_busy(self, path):
        import subprocess, sys
        code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1],timeout=.05);\ntry: c.execute('BEGIN IMMEDIATE')\nexcept sqlite3.OperationalError as e: c.close(); sys.exit(0 if e.sqlite_errorcode in (5,3850) else 9)\nc.rollback(); c.close(); sys.exit(7)"
        result = subprocess.run([sys.executable, '-B', '-W', 'error::ResourceWarning', '-c', code, str(path)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cross_thread_raw_identity_preserves_writer_exclusion(self):
        import sqlite3
        from concurrent.futures import ThreadPoolExecutor
        from contextlib import closing
        with copies.sqlite_handle_scope(self.source), closing(sqlite3.connect(self.source, isolation_level=None)) as db:
            db.execute('BEGIN IMMEDIATE')
            self.assert_competitor_busy(self.source)
            with ThreadPoolExecutor(max_workers=1) as pool:
                error = None
                try: pool.submit(copies.identity, self.source).result(timeout=5)
                except Exception as exc: error = exc
            self.assert_competitor_busy(self.source)
            self.assertIsInstance(error, copies.CopyError)
            db.execute('ROLLBACK')

    def test_transitive_runtime_reads_preserve_writer_exclusion(self):
        import sqlite3
        from contextlib import closing
        from things_workbench import native_runtime, schema_policy
        app = self.root/'fake-app'; (app/'Contents').mkdir(parents=True)
        (app/'Contents/Info.plist').symlink_to(self.source)
        class Resource:
            def joinpath(inner, name): return self.source
        calls = [('application', lambda db: native_runtime.application(app)),
                 ('macho', lambda db: native_runtime.inspect_macho(self.source)),
                 ('schema', lambda db: schema_policy.verify_schema_connection(db))]
        for name, call in calls:
            with self.subTest(name=name), patch.object(schema_policy, 'files', return_value=Resource()):
                with copies.sqlite_handle_scope(self.source), closing(sqlite3.connect(self.source, isolation_level=None)) as db:
                    db.execute('BEGIN IMMEDIATE'); self.assert_competitor_busy(self.source)
                    error = None
                    try: call(db)
                    except Exception as exc: error = exc
                    self.assert_competitor_busy(self.source)
                    self.assertIsInstance(error, copies.CopyError)
                    self.assertIn('active SQLite', str(error))
                    db.execute('ROLLBACK')

    def test_recovery_sql_lifetime_preserves_writer_exclusion(self):
        target, run, approval = self.prepared()
        def stop(name, db=None):
            if name == 'first_update': raise OSError('reached')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=stop):
            with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
        reached = []
        def guarded(db):
            reached.append(True)
            error = None
            try: copies.identity(target/'target.sqlite')
            except Exception as exc: error = exc
            self.assert_competitor_busy(target/'target.sqlite')
            self.assertIsInstance(error, copies.CopyError)
        with patch.object(pub, 'verify_schema_connection', side_effect=guarded):
            view = pub.recovery_preview(run, 'recovery', authorize_owned_recovery=True)
            pub.reconcile(run/'recovery.json', approval=view['approval_digest'])
        self.assertEqual(len(reached), 2)

    def test_path_snapshot_and_backup_register_handle_lifetimes(self):
        import sqlite3
        from things_workbench import fingerprint, schema_policy
        def read_guard(db):
            with self.assertRaises(copies.CopyError): copies.identity(self.source)
            return {}
        with patch.object(fingerprint, 'snapshot_connection', side_effect=read_guard):
            fingerprint.snapshot(self.source)
        with patch.object(schema_policy, 'verify_schema_connection', side_effect=read_guard):
            schema_policy.verify_schema(self.source)
        real_connect = sqlite3.connect; test = self
        destination = self.root/'guarded-backup.sqlite'
        class Connection(sqlite3.Connection):
            def backup(self, other, **kwargs):
                for p in (test.source, destination):
                    with test.assertRaises(copies.CopyError): copies.identity(p)
                return super().backup(other, **kwargs)
        def connect(*a, **kw): return real_connect(*a, factory=Connection, **kw)
        with patch.object(sqlite3, 'connect', side_effect=connect):
            copies.backup(self.source, destination)
        copies.identity(self.source); copies.identity(destination)

    def test_delete_header_reads_only_bounded_prefix(self):
        total = []
        real_read = copies.os.read
        def counted(fd, n):
            value = real_read(fd, n); total.append(len(value)); return value
        with patch.object(copies.os, 'read', side_effect=counted): pub._delete_header(self.source)
        self.assertLessEqual(sum(total), 100)

    def test_prepare_enforces_one_cumulative_provenance_deadline(self):
        target, run, approval = self.prepared()
        clock = [100.0]; completed = pub._completed
        def slow(packet):
            result = completed(packet)
            clock[0] += pub.POLICY['max_seconds'] + 1
            return result
        with patch.object(pub.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(pub, '_completed', side_effect=slow):
            with self.assertRaisesRegex(copies.CopyError, 'budget'):
                pub.prepare(self.packet, target, 'expired')
        self.assertFalse((target/'runs/expired').exists())

    def test_snapshot_row_budget_preserves_caller_transaction(self):
        import sqlite3
        from contextlib import closing
        from things_workbench.fingerprint import snapshot_connection
        with closing(sqlite3.connect(self.source, isolation_level=None)) as db:
            db.execute('BEGIN'); db.execute('SAVEPOINT caller')
            with patch.object(copies, 'MAX_SNAPSHOT_ROWS', 1, create=True):
                with self.assertRaisesRegex(copies.CopyError, 'budget'): snapshot_connection(db)
            self.assertTrue(db.in_transaction)
            db.execute('ROLLBACK TO caller'); db.execute('RELEASE caller'); db.execute('ROLLBACK')
            self.assertFalse(db.in_transaction)
            self.assertIn('tables', snapshot_connection(db))

    def test_payload_byte_budgets_refuse_before_unbounded_reads(self):
        from things_workbench import native_runtime
        for name, call in [('identity', lambda: copies.identity(self.source)),
                           ('read', lambda: copies.read_bytes(self.source)),
                           ('runtime', lambda: native_runtime.resource_bytes(self.source)),
                           ('hash', lambda: native_runtime.sha(self.source))]:
            with self.subTest(name=name), patch.object(copies, 'MAX_FILE_BYTES', 100, create=True):
                with self.assertRaisesRegex(copies.CopyError, 'budget'): call()

    def test_json_record_depth_and_size_are_bounded(self):
        path = self.root/'deep.json'
        path.write_bytes(b'['*80+b'0'+b']'*80); path.chmod(0o600)
        with self.assertRaisesRegex(copies.CopyError, 'budget'): copies.load(path)
        path.write_bytes(b'"'+b'x'*200+b'"')
        with patch.object(copies, 'MAX_RECORD_BYTES', 100, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'): copies.load(path)

    def test_publication_collections_and_transfer_plan_are_bounded(self):
        from things_workbench.fingerprint import snapshot
        target, run = self.resolved_before()
        with patch.object(pub, 'MAX_EVENTS', 1, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'): pub._events(run)
        with patch.object(pub, 'MAX_RUNS', 1, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'): pub.prepare(self.packet, target, 'two')
        with patch.object(pub, 'MAX_PLAN_BYTES', 1, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'):
                pub._transfer(snapshot(self.packet/'before.sqlite'), snapshot(self.packet/'output.sqlite'))

    def test_expired_sql_progress_is_disabled_before_rollback_and_close(self):
        import sqlite3
        from things_workbench.fingerprint import snapshot
        target, run, approval = self.prepared()
        real_connect = sqlite3.connect; rollbacks = []; closed = []
        class Connection(sqlite3.Connection):
            active_progress = None
            def set_progress_handler(inner, callback, count):
                inner.active_progress = callback
                return super().set_progress_handler(callback, count)
            def execute(inner, sql, *args):
                if sql == 'ROLLBACK': rollbacks.append(inner.active_progress is None)
                return super().execute(sql, *args)
            def close(inner):
                closed.append(id(inner)); return super().close()
        opened = []
        def connect(*args, **kwargs):
            db = real_connect(*args, factory=Connection, **kwargs); opened.append(id(db)); return db
        def fault(name, db=None):
            if name == 'first_update':
                db.set_progress_handler(lambda: 1, 1)
                raise OSError('expired SQL')
        with patch.object(sqlite3, 'connect', side_effect=connect), patch.object(pub, 'verify_schema_connection', return_value='0'*64), patch.object(pub, '_phase', side_effect=fault):
            with self.assertRaises(copies.CopyError): pub.rehearse(run, approval=approval)
        self.assertTrue(rollbacks); self.assertTrue(all(rollbacks))
        from collections import Counter
        self.assertEqual(Counter(opened), Counter(closed))
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'before.sqlite'))
        copies.identity(target/'target.sqlite')

    def test_nested_provenance_shares_cumulative_byte_allowance(self):
        from things_workbench import native_runtime
        with patch.object(copies, 'MAX_WORK_BYTES', self.source.stat().st_size + 1, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'):
                with copies.work_scope():
                    copies.identity(self.source)
                    with copies.work_scope(): native_runtime.sha(self.source)
        copies.identity(self.source)  # exhaustion must not poison a new operation

    def test_sql_snapshot_deadline_interrupts_work_and_releases_handler(self):
        import sqlite3
        from contextlib import closing
        from things_workbench.fingerprint import snapshot_connection
        clock = [0.0]; ticks = []
        class Connection(sqlite3.Connection):
            def execute(inner, sql, *args):
                if sql == 'PRAGMA integrity_check':
                    clock[0] = 121.0
                    return super().execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000) SELECT sum(tick(x)) FROM n')
                return super().execute(sql, *args)
        with closing(sqlite3.connect(':memory:', factory=Connection, isolation_level=None)) as db:
            db.create_function('tick', 1, lambda x: ticks.append(x) or x)
            with patch.object(pub.time, 'monotonic', side_effect=lambda: clock[0]):
                with self.assertRaises(copies.CopyError):
                    with copies.work_scope(): snapshot_connection(db)
            self.assertLess(len(ticks), 1000, 'deadline must interrupt SQL, not just notice after full query')
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute('SELECT 1').fetchone(), (1,))

    def test_rehashed_receipt_cannot_replace_verified_preview_or_engine_types(self):
        import copy
        target, run, approval = self.prepared()
        original = copies.load(run/'publication.json')
        cases = [(('wording', 'history_verified'), 1), (('engine', 'python', 'size'), float(original['engine']['python']['size'])),
                 (('engine', 'compile_options'), {}), (('engine', 'dependencies'), [])]
        for keys, value in cases:
            with self.subTest(keys=keys):
                record = copy.deepcopy(original); item = record
                for k in keys[:-1]: item = item[k]
                item[keys[-1]] = value
                (run/'publication.json').write_bytes(copies.canonical(record))
                (run/'prepared.json').write_bytes(copies.canonical({'version': 1, 'publication': copies.digest(record)}))
                with patch('sqlite3.connect') as connect:
                    with self.assertRaises(copies.CopyError): pub._receipt_envelope(run)
                    connect.assert_not_called()

    def test_two_publication_processes_share_target_reservation(self):
        import subprocess, sys, select
        from things_workbench.fingerprint import snapshot
        target, run, approval = self.prepared()
        other = pub.prepare(self.packet, target, 'other')
        other_approval = pub.preview(other)['approval_digest']
        code = 'import sys;sys.path.insert(0,'+repr(str(Path(__file__).resolve().parent))+');from test_publication_hardening import race_worker;race_worker()'
        command = [sys.executable, '-B', '-W', 'error::ResourceWarning', '-c', code]
        with subprocess.Popen(command+[str(run), approval, 'hold'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as first:
            try:
                self.assertTrue(select.select([first.stdout], [], [], 10)[0])
                self.assertEqual(first.stdout.readline().strip(), 'reserved')
                second = subprocess.run(command+[str(other), other_approval, 'busy'], capture_output=True, text=True, timeout=10)
                self.assertEqual(second.returncode, 17, second.stderr)
                self.assertIn('target busy', second.stdout)
                stdout, stderr = first.communicate('release\n', timeout=20)
                self.assertEqual(first.returncode, 0, stderr)
                self.assertIn('committed_verified', stdout)
            finally:
                if first.poll() is None:
                    first.communicate('release\n', timeout=20)
        self.assertEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'output.sqlite'))
        self.assertFalse((other/'intent.json').exists())
        self.assertFalse(pub.status(run)['quarantined'])
        self.assertEqual(pub.status(other)['state'], 'prepared')

    def test_later_legitimate_run_preserves_historical_terminal(self):
        from things_workbench.fingerprint import snapshot
        target, run, approval = self.prepared()
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64): pub.rehearse(run, approval=approval)
        copied = copies.import_copy(self.packet/'output.sqlite', self.root/'next-import', declaration='detached-stable-resolved')
        packet = wording.prepare(copied.parent, {'version':1, 'task':self.plan['task'], 'changes':{'title':'third synthetic title'}}, self.root/'next-packet', self.runtime)
        wording.apply_copy(packet, wording.preview(packet)['approval_digest'])
        next_run = pub.prepare(packet, target, 'later')
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64): pub.rehearse(next_run, approval=pub.preview(next_run)['approval_digest'])
        self.assertNotEqual(snapshot(target/'target.sqlite'), snapshot(self.packet/'output.sqlite'))
        with patch('sqlite3.connect') as connect:
            self.assertFalse(pub.status(run)['quarantined']); self.assertFalse(pub.status(next_run)['quarantined'])
            connect.assert_not_called()
        self.assertEqual(wording.verify_completed(self.packet)['state'], 'prepared')
        with self.assertRaises(copies.CopyError): copies.import_copy(target/'target.sqlite', self.root/'forbidden', declaration='detached-stable-resolved')

    def test_nested_scopes_and_registration_wait_for_raw_close(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from things_workbench import native_runtime
        entered = threading.Event(); release = threading.Event(); registered = threading.Event()
        real_read = copies.os.read
        def blocking_read(fd, n):
            entered.set()
            if not release.wait(5): raise RuntimeError('bounded test wait')
            return real_read(fd, n)
        def register():
            with copies.sqlite_handle_scope(self.source): registered.set()
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(copies.os, 'read', side_effect=blocking_read):
            reading = pool.submit(copies.identity, self.source)
            self.assertTrue(entered.wait(5))
            registering = pool.submit(register)
            try: self.assertFalse(registered.wait(.1))
            finally: release.set()
            reading.result(timeout=5); registering.result(timeout=5)
        with copies.sqlite_handle_scope(self.source):
            with copies.sqlite_handle_scope(self.source):
                with self.assertRaises(copies.CopyError): native_runtime.sha(self.source)
            with self.assertRaises(copies.CopyError): copies.identity(self.source)
        copies.identity(self.source)

    def test_backup_deadline_stops_progress_and_closes_connections(self):
        import sqlite3
        target = self.root/'budget-backup.sqlite'; clock = [0.0]
        real_connect = sqlite3.connect; reached = []; opened = []; closed = []
        class Connection(sqlite3.Connection):
            def backup(inner, destination, **kwargs):
                clock[0] = 121.0; reached.append(True)
                callback = kwargs.get('progress')
                if callback: callback(sqlite3.SQLITE_BUSY, 4, 4)
                return super().backup(destination, **kwargs)
            def close(inner): closed.append(id(inner)); return super().close()
        def connect(*a, **kw):
            db = real_connect(*a, factory=Connection, **kw); opened.append(id(db)); return db
        with patch.object(pub.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(sqlite3, 'connect', side_effect=connect):
            with self.assertRaisesRegex(copies.CopyError, 'budget'):
                with copies.work_scope(): copies.backup(self.source, target)
        self.assertEqual(reached, [True])
        self.assertEqual(target.stat().st_size, 0, 'expired backup must stop before page transfer')
        from collections import Counter
        self.assertEqual(Counter(opened), Counter(closed))
        copies.identity(self.source)

    def test_stage2_target_reader_registers_its_sql_lifetime(self):
        import sqlite3
        real_connect = sqlite3.connect; test = self; reached = []
        class Connection(sqlite3.Connection):
            def execute(inner, sql, *args):
                result = super().execute(sql, *args)
                reached.append(sql)
                with test.assertRaises(copies.CopyError): copies.identity(test.source)
                return result
        with patch.object(sqlite3, 'connect', side_effect=lambda *a, **kw: real_connect(*a, factory=Connection, **kw)):
            wording.target(self.source, self.plan)
        self.assertTrue(reached)
        copies.identity(self.source)

    def test_snapshot_bytes_and_cumulative_rows_are_bounded(self):
        from things_workbench.fingerprint import snapshot
        with patch.object(copies, 'MAX_SNAPSHOT_BYTES', 100, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'): snapshot(self.source)
        with patch.object(copies, 'MAX_WORK_ROWS', 1, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'):
                with copies.work_scope(): snapshot(self.source)
        self.assertIn('tables', snapshot(self.source))

    def test_runtime_inventory_has_finite_path_budget(self):
        from things_workbench import native_runtime
        with patch.object(copies, 'MAX_PATH_ENTRIES', 1, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'): native_runtime.sources()

    def test_runtime_dependency_depth_is_explicitly_bounded(self):
        from things_workbench import native_runtime as native
        runtime = self.root/'depth-runtime'; runtime.mkdir(mode=0o700)
        app = self.root/'depth-app'; (app/'Contents/MacOS').mkdir(parents=True)
        image = app/'Contents/MacOS/Things3'; image.write_bytes(b'synthetic')
        paths = [app/('dep'+str(i)) for i in range(6)]
        for p in [*(runtime/n for n in native.ARTIFACTS), *paths]: p.write_bytes(b'synthetic')
        pins = {str(p.relative_to(app)):native.sha(p) for p in [image, *paths]}
        def macho(path):
            chain = [runtime/'wording', *paths]
            deps = []
            if path in chain[:-1]: deps = [{'command':12, 'name':str(chain[chain.index(path)+1])}]
            return {'1:1': {'dependencies':deps, 'rpaths':[]}}
        with patch.object(native, 'inspect_macho', side_effect=macho), patch.object(copies, 'MAX_DEPENDENCY_DEPTH', 4, create=True):
            with self.assertRaisesRegex(copies.CopyError, 'budget'): native.dependency_closure(runtime, app, pins)

    def test_recovery_schema_sql_uses_outer_deadline_and_closes(self):
        import sqlite3
        target, run, approval = self.prepared()
        m = copies.load(run/'publication.json'); reached = []; clock = [0.0]
        def schema(db):
            reached.append(db); clock[0] = 1000.0
            with self.assertRaisesRegex(sqlite3.OperationalError, 'interrupted'):
                db.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000) SELECT sum(x) FROM n').fetchone()
        with patch.object(copies.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(pub, 'verify_schema_connection', side_effect=schema):
            with self.assertRaisesRegex(copies.CopyError, 'budget'):
                with copies.work_scope(), pub._recovery_writer(m): pass
        self.assertEqual(len(reached), 1)
        with self.assertRaises(sqlite3.ProgrammingError): reached[0].execute('SELECT 1')
        copies.identity(target/'target.sqlite')

    def test_valid_stage2_supplier_and_all_stage3_copies_remain_distinct(self):
        target, run = self.resolved_before()
        imported = copies.import_copy(self.packet/'output.sqlite', self.root/'valid-stage2', declaration='detached-stable-resolved')
        copies.verify_copy(imported.parent)
        restored = pub.restore_copy(run, self.root/'recovery-copy')
        for source in (target/'target.sqlite', run/'backup.sqlite', restored):
            with self.subTest(source=source.name), patch.object(copies, 'backup') as backup:
                with self.assertRaises(copies.CopyError):
                    copies.import_copy(source, self.root/'forbidden-import', declaration='detached-stable-resolved')
                backup.assert_not_called()

    def test_truncated_and_partial_retained_receipts_fail_closed(self):
        target, run = self.resolved_before()
        for path in (run/'publication.json', run/'prepared.json', run/'intent.json', target/'registry/one.json', run/'assessment.json', run/'events/0000.json'):
            original = path.read_bytes()
            for payload in (b'{', b'{}'):
                with self.subTest(file=path.name, payload=payload):
                    path.write_bytes(payload)
                    try:
                        with patch('sqlite3.connect') as connect:
                            self.assertTrue(pub.status(run)['quarantined'])
                            with self.assertRaises(copies.CopyError): pub.prepare(self.packet, target, 'two')
                            connect.assert_not_called()
                    finally: path.write_bytes(original)

    def test_repeat_recovery_leaves_resolved_history_unchanged(self):
        target, run, approval = self.prepared()
        with patch.object(pub, 'verify_schema_connection', return_value='0'*64):
            pub.rehearse(run, approval=approval)
            original = {p.name: p.read_bytes() for p in (run/'events').iterdir()}
            with self.assertRaises(copies.CopyError):
                view = pub.recovery_preview(run, 'again', authorize_owned_recovery=True)
                pub.reconcile(run/'again.json', approval=view['approval_digest'])
        self.assertEqual({p.name: p.read_bytes() for p in (run/'events').iterdir()}, original)
        self.assertFalse(pub.status(run)['quarantined'])


for _name in tuple(vars(LifecycleTests)):
    if _name.startswith('test_'):
        setattr(HardeningTests, _name, None)
del LifecycleTests


def race_worker():
    import sys
    from contextlib import ExitStack
    from test_copy_lifecycle import synthetic_verdict
    run, approval, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    def phase(name, db=None):
        if mode == 'hold' and name == 'writer_before':
            print('reserved', flush=True)
            if sys.stdin.readline() != 'release\n': raise RuntimeError('missing release')
    with ExitStack() as stack:
        stack.enter_context(patch.object(wording.native_runtime, 'verify', return_value={'synthetic_lifecycle_runtime': True}))
        stack.enter_context(patch.object(wording.native_runtime, 'stopped'))
        stack.enter_context(patch.object(wording.native_runtime, 'run', side_effect=AssertionError('native replay')))
        stack.enter_context(patch.object(wording, 'validate', side_effect=synthetic_verdict))
        stack.enter_context(patch.object(pub, 'verify_schema_connection', return_value='0'*64))
        stack.enter_context(patch.object(pub, '_phase', side_effect=phase))
        try: print(pub.rehearse(run, approval=approval), flush=True)
        except copies.CopyError as exc:
            print(str(exc), flush=True)
            sys.exit(17 if mode == 'busy' and str(exc) == 'target busy' else 18)
