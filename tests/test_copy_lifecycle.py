"""SYNTHETIC lifecycle only: no native execution or native-positive evidence.

The explicit fake backend edits only this test's newly created SQLite fixtures.
Schema/history/native proof are replaced at the lifecycle seam, not certified.
Real copy, identity, packet, preview, locks, and output backup code are exercised.
"""
from contextlib import closing, ExitStack
import copy
import errno
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from things_workbench import copies, wording
from things_workbench.fingerprint import snapshot

UID = 'S' * 22
real_validate = wording.validate


def synthetic_verdict(before, candidate, plan, proof):
    if proof != {'synthetic_lifecycle_only': True}:
        raise copies.CopyError('synthetic proof drift')
    with closing(sqlite3.connect(candidate)) as db:
        title, notes = db.execute('SELECT title,notes FROM TMTask').fetchone()
    with closing(sqlite3.connect(before)) as db:
        old_title, old_notes = db.execute('SELECT title,notes FROM TMTask').fetchone()
    if (title, notes) != (plan['changes'].get('title', old_title), plan['changes'].get('notes', old_notes)):
        raise copies.CopyError('synthetic candidate drift')
    return {'before_fingerprint': copies.digest(snapshot(before)),
            'candidate_fingerprint': copies.digest(snapshot(candidate)),
            'fields': sorted([*plan['changes'], 'userModificationDate']),
            'history': {'synthetic_lifecycle_only': True}}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.source = self.root / 'supplier.sqlite'
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE Meta (key TEXT, value BLOB)')
            db.execute('INSERT INTO Meta VALUES (?,?)', ('databaseVersion', plistlib.dumps(29)))
            db.execute('CREATE TABLE TMTask (uuid TEXT PRIMARY KEY,title TEXT,notes TEXT,type INTEGER,status INTEGER,trashed INTEGER,start INTEGER,startDate REAL,stopDate REAL,repeater BLOB,rt1_recurrenceRule BLOB,rt1_repeatingTemplate TEXT,userModificationDate REAL,notesSync INTEGER)')
            db.execute('INSERT INTO TMTask VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (UID, 'synthetic old', 'private synthetic notes\r\n😀', 0, 0, 0, 1, None, None, None, None, None, 1.0, 0))
            db.commit()
        self.source.chmod(0o600)
        self.source_identity = copies.identity(self.source)
        self.imported = copies.import_copy(self.source, self.root / 'import', declaration='detached-stable-resolved')
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.runtime_record = {'synthetic_lifecycle_runtime': True}
        self.starts = 0
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(wording.native_runtime, 'verify', side_effect=lambda _: copy.deepcopy(self.runtime_record)))
        stack.enter_context(patch.object(wording.native_runtime, 'stopped'))
        stack.enter_context(patch.object(wording.native_runtime, 'run', side_effect=self.synthetic_backend))
        stack.enter_context(patch.object(wording.history, 'inventory', return_value=[]))
        stack.enter_context(patch.object(wording, 'verify_schema', return_value='0' * 64, create=True))
        stack.enter_context(patch.object(wording, 'validate', side_effect=synthetic_verdict))
        self.plan = {'version': 1, 'task': UID, 'changes': {'title': 'new "title"\n😀', 'notes': 'e\u0301\r\n' + 'x' * 39990}}
        self.packet = wording.prepare(self.imported.parent, self.plan, self.root / 'packet', self.runtime)
        self.view = wording.preview(self.packet)
        self.before_identity = copies.identity(self.packet / 'before.sqlite')

    def synthetic_backend(self, runtime, work, plan_path):
        self.starts += 1
        plan = copies.load(plan_path)
        with closing(sqlite3.connect(work / 'candidate.sqlite')) as db:
            for field, value in plan['changes'].items():
                db.execute('UPDATE TMTask SET ' + field + '=?', (value,))
            db.execute('UPDATE TMTask SET userModificationDate=2.0,notesSync=1')
            db.commit()
        return {'synthetic_lifecycle_only': True}

    def rewrite(self, path, value):
        path.write_bytes(copies.canonical(value))

    def assert_preserved(self):
        self.assertEqual(copies.identity(self.source), self.source_identity)
        self.assertEqual(copies.identity(self.packet / 'before.sqlite'), self.before_identity)
        self.assertEqual(self.starts, 1)

    def test_00_synthetic_positive_exact_preview_output_no_replay(self):
        self.assertEqual(self.view['before']['notes'], 'private synthetic notes\r\n😀')
        self.assertEqual(self.view['after'], self.plan['changes'])
        encoded = json.dumps(self.view, ensure_ascii=True)
        self.assertIn('\\r\\n', encoded)
        self.assertNotIn('😀', encoded)
        candidate = copies.digest(snapshot(self.packet / 'native/candidate.sqlite'))
        output = wording.apply_copy(self.packet, self.view['approval_digest'])
        self.assertEqual(copies.digest(snapshot(output)), candidate)
        self.assertTrue((self.packet / 'complete.json').is_file())
        self.assert_preserved()
        with self.assertRaises(copies.CopyError):
            wording.apply_copy(self.packet, self.view['approval_digest'])

    def test_interrupted_output_cannot_be_reimported(self):
        command = [sys.executable, '-B', '-c',
                   'import runpy;runpy.run_path(' + repr(str(Path(__file__).resolve())) + ')["synthetic_worker"]()',
                   str(self.packet), self.view['approval_digest'], 'backup-exit']
        crashed = subprocess.run(command, input='go\n', text=True, capture_output=True, timeout=20)
        self.assertEqual(crashed.returncode, 71, crashed.stderr)
        self.assertEqual(copies.load(self.packet / 'crash-reached.json')['point'], 'backup-exit')
        self.assertFalse((self.packet / 'complete.json').exists())
        self.assertFalse((self.packet / 'failed.json').exists())
        with patch.object(copies, 'backup', wraps=copies.backup) as backup:
            with self.assertRaisesRegex(copies.CopyError, 'supplier|source|interrupted'):
                copies.import_copy(self.packet / 'output.sqlite', self.root / 'reimport', declaration='detached-stable-resolved')
            backup.assert_not_called()
        self.assert_preserved()

    def test_supplier_quarantine_rechecked_after_import(self):
        output = wording.apply_copy(self.packet, self.view['approval_digest'])
        imported = copies.import_copy(output, self.root / 'accepted-import', declaration='detached-stable-resolved')
        copies.verify_copy(imported.parent)
        copies.durable(self.packet / 'failed.json', {'state': 'quarantined'})
        with patch.object(wording, 'backup', wraps=wording.backup) as backup:
            with self.assertRaisesRegex(copies.CopyError, 'source|supplier|quarantined'):
                wording.prepare(imported.parent, {**self.plan, 'changes': {'title': 'next synthetic title'}}, self.root / 'later', self.runtime)
            backup.assert_not_called()
        with self.assertRaises(copies.CopyError):
            copies.verify_copy(imported.parent)
        self.assert_preserved()

    def test_completed_supplier_requires_full_binding(self):
        output = wording.apply_copy(self.packet, self.view['approval_digest'])
        imported = copies.import_copy(output, self.root / 'accepted', declaration='detached-stable-resolved')
        self.assertTrue((self.packet / 'applying.json').exists())
        originals = {name: (self.packet / name).read_bytes() for name in ('complete.json', 'applying.json', 'packet.json', 'proof.json')}
        complete = copies.load(self.packet / 'complete.json')
        mutations = [('complete.json', b'{}'), ('complete.json', b'{'),
                     ('complete.json', copies.canonical({**complete, 'approval': '0' * 64})),
                     ('complete.json', copies.canonical({**complete, 'fingerprint': '0' * 64})),
                     ('complete.json', copies.canonical({**complete, 'live_published': True})),
                     ('applying.json', b'{}'), ('packet.json', b'{}'), ('proof.json', b'{}')]
        for index, (name, value) in enumerate(mutations):
            with self.subTest(name=name, index=index):
                (self.packet / name).write_bytes(value)
                with patch.object(copies, 'backup', wraps=copies.backup) as backup:
                    with self.assertRaises(copies.CopyError):
                        copies.import_copy(output, self.root / ('bad-' + str(index)), declaration='detached-stable-resolved')
                    backup.assert_not_called()
                with self.assertRaises(copies.CopyError):
                    copies.verify_copy(imported.parent)
                (self.packet / name).write_bytes(originals[name])
        copies.verify_copy(imported.parent)
        for source in (self.packet / 'before.sqlite', self.packet / 'native/candidate.sqlite'):
            with self.assertRaises(copies.CopyError):
                copies.import_copy(source, self.root / 'not-output', declaration='detached-stable-resolved')
        self.assert_preserved()

    def test_supplier_cycles_and_depth_fail_closed(self):
        original = copies.load(self.imported.parent / 'copy.json')
        changed = copy.deepcopy(original)
        changed['source'] = changed['copy']
        self.rewrite(self.imported.parent / 'copy.json', changed)
        self.rewrite(self.imported.parent / 'started.json', {'operation': 'import', 'source': changed['source']})
        with self.assertRaisesRegex(copies.CopyError, 'cycle|bound'):
            copies.verify_copy(self.imported.parent)

    def test_supplier_changes_during_import_are_not_released(self):
        supplier_root = self.root / 'supplier-owned'; supplier_root.mkdir(mode=0o700)
        supplier = copies.backup(self.source, supplier_root / 'detached.sqlite')
        real_backup = copies.backup
        def changed(source, destination):
            result = real_backup(source, destination)
            copies.durable(supplier_root / 'preparing.json', {'state': 'preparing'})
            return result
        with patch.object(copies, 'backup', side_effect=changed):
            with self.assertRaisesRegex(copies.CopyError, 'supplier|source|interrupted'):
                copies.import_copy(supplier, self.root / 'drift-import', declaration='detached-stable-resolved')
        self.assertTrue((self.root / 'drift-import/importing.json').exists())

    def test_strict_packet_import_identity_envelopes(self):
        for filename in (self.packet / 'packet.json', self.imported.parent / 'copy.json'):
            original = copies.load(filename)
            mutations = []
            for key in original:
                changed = copy.deepcopy(original); del changed[key]
                mutations.append(('missing-' + key, changed))
                changed = copy.deepcopy(original); changed[key] = None
                mutations.append(('null-' + key, changed))
            mutations += [('extra', {**original, 'extra': 1}),
                          ('bool-version', {**original, 'version': True}),
                          ('wrong-version', {**original, 'version': 2}),
                          ('wrong-state', {**original, 'state': 'complete'})]
            for label, changed in mutations:
                with self.subTest(file=filename.name, mutation=label):
                    self.rewrite(filename, changed)
                    with self.assertRaises(copies.CopyError):
                        wording.preview(self.packet)
                    self.rewrite(filename, original)
        original = copies.load(self.packet / 'packet.json')
        for key in original['files']['proof.json']:
            changed = copy.deepcopy(original)
            del changed['files']['proof.json'][key]
            self.rewrite(self.packet / 'packet.json', changed)
            with self.subTest(identity_missing=key), self.assertRaises(copies.CopyError):
                wording.preview(self.packet)
        self.rewrite(self.packet / 'packet.json', original)
        changed = copy.deepcopy(original)
        changed['files']['../escape'] = changed['files']['proof.json']
        self.rewrite(self.packet / 'packet.json', changed)
        with self.assertRaises(copies.CopyError):
            wording.preview(self.packet)

    def test_preview_recomputed_even_when_resealed(self):
        manifest = copies.load(self.packet / 'packet.json')
        view = copies.load(self.packet / 'preview.json')
        view['before']['notes'] = 'misleading synthetic preview'
        self.rewrite(self.packet / 'preview.json', view)
        manifest['files']['preview.json'] = copies.identity(self.packet / 'preview.json')
        self.rewrite(self.packet / 'packet.json', manifest)
        with self.assertRaisesRegex(copies.CopyError, 'preview'):
            wording.preview(self.packet)
        self.assert_preserved()

    def test_schema_gate_precedes_target_and_runtime(self):
        with patch.object(wording, 'verify_schema', side_effect=copies.CopyError('synthetic schema denied')) as gate, patch.object(wording, 'target') as lookup:
            with self.assertRaisesRegex(copies.CopyError, 'schema denied'):
                wording.prepare(self.imported.parent, self.plan, self.root / 'new-packet', self.runtime)
            gate.assert_called_once_with(self.imported)
            lookup.assert_not_called()
        self.assertEqual(self.starts, 1)

    def test_native_proof_metadata_is_required_and_forwarded(self):
        # Synthetic proof-schema seam only; retain is explicitly not certified.
        proof = {'events': [{'changes': {UID: {'e': 'Task7', 't': 1, 'p': {'tt': self.plan['changes']['title'], 'nt': 'synthetic note operation', 'md': 2.0}}}, 'base': None}],
                 'max_notes_length': 40000, 'schema_version': 301,
                 'history_connected': True, 'metadata': {'synthetic_binding': True}}
        with patch.object(wording.history, 'retain', return_value={'synthetic': True}) as retained:
            real_validate(self.packet / 'before.sqlite', self.packet / 'native/candidate.sqlite', self.plan, proof)
            self.assertEqual(retained.call_args.args[3], proof['metadata'])
            for key in proof:
                bad = copy.deepcopy(proof); del bad[key]
                with self.subTest(omission=key), self.assertRaises(copies.CopyError):
                    real_validate(self.packet / 'before.sqlite', self.packet / 'native/candidate.sqlite', self.plan, bad)
            for location, value in ((('events', 0, 'changes'), None), (('events', 0, 'changes'), []),
                                    (('events', 0, 'base'), []), (('events', 0, 'changes', UID), None),
                                    (('events', 0, 'changes', UID, 'p'), None)):
                bad = copy.deepcopy(proof); cursor = bad
                for key in location[:-1]: cursor = cursor[key]
                cursor[location[-1]] = value
                with self.subTest(malformed=location), self.assertRaises(copies.CopyError):
                    real_validate(self.packet / 'before.sqlite', self.packet / 'native/candidate.sqlite', self.plan, bad)

    def test_tamper_after_preview_each_artifact_source_runtime(self):
        for name in ('plan.json', 'proof.json', 'preview.json', 'before.sqlite', 'native/candidate.sqlite'):
            path = self.packet / name; original = path.read_bytes()
            with self.subTest(artifact=name):
                path.write_bytes(original + b' ')
                with self.assertRaisesRegex(copies.CopyError, 'artifact drift'):
                    wording.apply_copy(self.packet, self.view['approval_digest'])
                self.assertFalse((self.packet / 'complete.json').exists())
                path.write_bytes(original)
        original = self.source.read_bytes(); self.source.write_bytes(original + b' ')
        with self.assertRaisesRegex(copies.CopyError, 'source or copy drift'):
            wording.apply_copy(self.packet, self.view['approval_digest'])
        self.source.write_bytes(original)
        self.runtime_record['tampered'] = True
        with self.assertRaisesRegex(copies.CopyError, 'runtime manifest drift'):
            wording.apply_copy(self.packet, self.view['approval_digest'])
        self.assert_preserved()

    def test_wrong_approval_sibling_copy_and_interrupted_markers(self):
        with self.assertRaisesRegex(copies.CopyError, 'approval'):
            wording.apply_copy(self.packet, '0' * 64)
        sibling = self.root / 'sibling'; shutil.copytree(self.packet, sibling)
        with self.assertRaisesRegex(copies.CopyError, 'drift'):
            wording.apply_copy(sibling, self.view['approval_digest'])
        for name in ('applying.json', 'failed.json', 'complete.json'):
            marker = self.packet / name
            marker.symlink_to(self.root / 'missing-marker')
            with self.subTest(marker=name), self.assertRaisesRegex(copies.CopyError, 'quarantined|consumed|interrupted'):
                wording.preview(self.packet)
            marker.unlink()
        self.assert_preserved()

    def test_output_and_complete_failure_quarantine_even_failed_record_fails(self):
        original_durable = wording.durable
        for name in ('applying.json', 'output.sqlite', 'complete.json'):
            with self.subTest(failure_point=name):
                # Each attempt has its own genuine synthetic prepared packet.
                packet = wording.prepare(self.imported.parent, self.plan, self.root / ('failure-' + name), self.runtime)
                approval = wording.preview(packet)['approval_digest']
                reached = []
                def fail_record(path, value):
                    if Path(path).name in (name, 'failed.json'):
                        reached.append(Path(path).name)
                        if name == 'applying.json' and Path(path).name == name:
                            Path(path).touch(mode=0o600)
                        raise OSError(errno.ENOSPC, 'synthetic disk full')
                    return original_durable(path, value)
                def fail_backup(*args):
                    reached.append('output.sqlite')
                    raise OSError(errno.ENOSPC, 'synthetic backup full')
                with ExitStack() as stack:
                    stack.enter_context(patch.object(wording, 'durable', side_effect=fail_record))
                    if name == 'output.sqlite': stack.enter_context(patch.object(wording, 'backup', side_effect=fail_backup))
                    with self.assertRaises(OSError): wording.apply_copy(packet, approval)
                self.assertIn(name, reached)
                self.assertFalse((packet / 'complete.json').exists())
                with self.assertRaisesRegex(copies.CopyError, 'interrupted|consumed'):
                    wording.apply_copy(packet, approval)
        self.assertEqual(copies.identity(self.source), self.source_identity)
        self.assertEqual(copies.identity(self.packet / 'before.sqlite'), self.before_identity)

    def test_prepare_final_record_failure_cannot_resume_without_failed_record(self):
        packet = self.root / 'incomplete-packet'
        real_durable = wording.durable
        reached = []
        def failing(path, value):
            if Path(path).name == 'failed.json':
                reached.append('failed.json'); raise OSError(errno.ENOSPC, 'synthetic failed receipt full')
            result = real_durable(path, value)
            if Path(path).name == 'packet.json':
                reached.append('packet.json'); raise OSError(errno.EIO, 'synthetic post-write fsync failure')
            return result
        with patch.object(wording, 'durable', side_effect=failing):
            with self.assertRaises(OSError):
                wording.prepare(self.imported.parent, self.plan, packet, self.runtime)
        self.assertEqual(reached, ['packet.json', 'failed.json'])
        self.assertTrue((packet / 'packet.json').exists())
        self.assertFalse((packet / 'failed.json').exists())
        with self.assertRaisesRegex(copies.CopyError, 'interrupted|preparing'):
            wording.preview(packet)
        with patch.object(copies, 'backup', wraps=copies.backup) as backup:
            with self.assertRaises(copies.CopyError):
                copies.import_copy(packet / 'native/candidate.sqlite', self.root / 'reimport-incomplete', declaration='detached-stable-resolved')
            backup.assert_not_called()

    def test_two_process_apply_at_most_one_output_no_native_replay(self):
        command = [sys.executable, '-B', '-W', 'error', '-c',
                   ('import runpy; runpy.run_path(' + repr(str(Path(__file__).resolve())) + ')["synthetic_worker"]()'),
                   str(self.packet), self.view['approval_digest'], 'apply']
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as first, subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as second:
            for process in (first, second): process.stdin.write('go\n'); process.stdin.flush()
            results = [(p.communicate(timeout=20), p.returncode) for p in (first, second)]
        self.assertEqual(sorted(code for _, code in results), [0, 2], results)
        self.assertEqual(copies.digest(snapshot(self.packet / 'output.sqlite')), copies.digest(snapshot(self.packet / 'native/candidate.sqlite')))
        self.assert_preserved()

    def test_fresh_process_restart_and_crash_refusal_points(self):
        for point in ('applying', 'backup-enter', 'backup-exit', 'complete-fsync', 'complete-written'):
            packet = wording.prepare(self.imported.parent, self.plan, self.root / ('crash-' + point), self.runtime)
            approval = wording.preview(packet)['approval_digest']
            command = [sys.executable, '-B', '-W', 'error', '-c',
                       ('import runpy; runpy.run_path(' + repr(str(Path(__file__).resolve())) + ')["synthetic_worker"]()'), str(packet), approval, point]
            crashed = subprocess.run(command, input='go\n', text=True, capture_output=True, timeout=20)
            self.assertEqual(crashed.returncode, 71, (point, crashed.stderr))
            self.assertEqual(copies.load(packet / 'crash-reached.json')['point'], point)
            command[-1] = 'apply'
            restarted = subprocess.run(command, input='go\n', text=True, capture_output=True, timeout=20)
            self.assertEqual(restarted.returncode, 2, (point, restarted.stderr))
            self.assertEqual(restarted.stdout.strip(), 'refused')
        self.assertEqual(copies.identity(self.source), self.source_identity)
        self.assertEqual(copies.identity(self.packet / 'before.sqlite'), self.before_identity)

    def test_preview_returns_verified_value_not_a_second_unchecked_read(self):
        real_load = wording.load; seen = []
        def changed_second_read(path):
            value = real_load(path)
            if Path(path).name == 'preview.json':
                seen.append(True)
                if len(seen) > 1: value['after']['title'] = 'unverified synthetic substitution'
            return value
        with patch.object(wording, 'load', side_effect=changed_second_read):
            view = wording.preview(self.packet)
        self.assertEqual(view['after']['title'], self.plan['changes']['title'])
        self.assertEqual(view['approval_digest'], self.view['approval_digest'])

    def test_packet_database_sidecars_refused_before_target_lookup(self):
        for name in ('before.sqlite', 'native/candidate.sqlite'):
            path = self.packet / name
            for suffix in ('-wal', '-journal'):
                side = Path(str(path) + suffix)
                side.write_bytes(b'synthetic stale sidecar'); side.chmod(0o600)
                with self.subTest(database=name, suffix=suffix), patch.object(wording, 'target') as lookup:
                    with self.assertRaisesRegex(copies.CopyError, 'detached|sidecar'):
                        wording.preview(self.packet)
                    lookup.assert_not_called()
                self.assertEqual(side.read_bytes(), b'synthetic stale sidecar')
                side.unlink()
        self.assert_preserved()

    def test_continued_verification_requires_private_modes(self):
        paths = [self.source, self.imported, self.imported.parent / 'copy.json',
                 self.packet / 'before.sqlite', self.packet / 'native/candidate.sqlite',
                 self.packet / 'proof.json', self.packet / 'preview.json',
                 self.packet / 'plan.json', self.packet / 'packet.json', self.packet / 'started.json']
        for path in paths:
            with self.subTest(file=path.name):
                path.chmod(0o644)
                with self.assertRaisesRegex(copies.CopyError, 'private|mode'):
                    wording.preview(self.packet)
                path.chmod(0o600)
        for path in (self.packet, self.packet / 'native', self.imported.parent):
            with self.subTest(directory=path.name):
                path.chmod(0o755)
                with self.assertRaisesRegex(copies.CopyError, 'private|mode'):
                    wording.preview(self.packet)
                path.chmod(0o700)

    def test_required_fingerprint_cannot_be_omitted(self):
        original = copies.load(self.packet / 'packet.json')
        for name in original['files']:
            with self.subTest(omitted=name):
                changed = copy.deepcopy(original)
                del changed['files'][name]
                self.rewrite(self.packet / 'packet.json', changed)
                with self.assertRaisesRegex(copies.CopyError, 'schema|artifact'):
                    wording.preview(self.packet)
        self.assert_preserved()


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.source = self.root / 'source.sqlite'
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE fixture (value TEXT)')
            db.commit()
        self.source.chmod(0o600)

    @unittest.skipUnless(sys.platform == 'darwin', 'real macOS ACL sentinel lane')
    def test_explicit_and_inherited_acl_refused_without_rewrite(self):
        for path, acl in ((self.source, 'everyone allow read'),
                          (self.root, 'everyone allow list,search,readattr,readextattr,readsecurity,file_inherit,directory_inherit')):
            with self.subTest(kind='file' if path == self.source else 'ancestor'):
                subprocess.run(['/bin/chmod', '+a', acl, str(path)], check=True, capture_output=True)
                try:
                    if path == self.root:
                        child = self.root / 'inherited'
                        child.write_bytes(b'synthetic'); child.chmod(0o600)
                        inspected = child
                    else: inspected = path
                    before = subprocess.run(['/bin/ls', '-lde', str(inspected)], check=True, capture_output=True).stdout
                    with self.assertRaisesRegex(copies.CopyError, 'ACL'):
                        copies.checked(inspected)
                    after = subprocess.run(['/bin/ls', '-lde', str(inspected)], check=True, capture_output=True).stdout
                    self.assertEqual(before, after)
                finally:
                    subprocess.run(['/bin/chmod', '-N', str(path)], check=True, capture_output=True)

    def test_acl_inspection_failure_is_closed(self):
        with patch.object(copies, 'inspect_acl', side_effect=copies.CopyError('ACL unavailable'), create=True):
            with self.assertRaisesRegex(copies.CopyError, 'ACL'):
                copies.checked(self.source)

    def test_import_final_record_failure_cannot_resume_without_failed_record(self):
        root = self.root / 'incomplete-import'; real_durable = copies.durable
        reached = []
        def failing(path, value):
            if Path(path).name == 'failed.json':
                reached.append('failed.json'); raise OSError(errno.ENOSPC, 'synthetic full')
            result = real_durable(path, value)
            if Path(path).name == 'copy.json':
                reached.append('copy.json'); raise OSError(errno.EIO, 'synthetic fsync failure')
            return result
        with patch.object(copies, 'durable', side_effect=failing):
            with self.assertRaises(OSError):
                copies.import_copy(self.source, root, declaration='detached-stable-resolved')
        self.assertEqual(reached, ['copy.json', 'failed.json'])
        with self.assertRaisesRegex(copies.CopyError, 'interrupted|importing'):
            copies.verify_copy(root)
        with patch.object(copies, 'backup', wraps=copies.backup) as backup:
            with self.assertRaises(copies.CopyError):
                copies.import_copy(root / 'source.sqlite', self.root / 'reimport-incomplete', declaration='detached-stable-resolved')
            backup.assert_not_called()

    def test_supplier_depth_bound(self):
        source = self.source
        for index in range(16):
            source = copies.import_copy(source, self.root / ('chain-' + str(index)), declaration='detached-stable-resolved')
        copies.verify_copy(source.parent)
        # The import can inspect sixteen ancestors, but continued verification
        # of a seventeenth node must refuse; it cannot recurse without bound.
        source = copies.import_copy(source, self.root / 'chain-16', declaration='detached-stable-resolved')
        with self.assertRaisesRegex(copies.CopyError, 'bound'):
            copies.verify_copy(source.parent)

    def test_json_reader_refuses_symlink_swap_and_nonfinite_values(self):
        path = self.root / 'record.json'; path.write_bytes(b'{"ok":1}'); path.chmod(0o600)
        for text in ('NaN', 'Infinity', '-Infinity', '1e999', '{"a":1,"a":2}'):
            path.write_text(text)
            with self.subTest(json=text), self.assertRaises(copies.CopyError): copies.load(path)
        path.write_bytes(b'{"ok":1}')
        secret = self.root / 'sentinel.json'; secret.write_bytes(b'{"not_authorized":1}'); secret.chmod(0o600)
        real_checked = copies.checked
        switched = []
        def swap(value, **kwargs):
            result = real_checked(value, **kwargs)
            if Path(value) == path and not switched:
                switched.append(True); path.unlink(); path.symlink_to(secret)
            return result
        with patch.object(copies, 'checked', side_effect=swap):
            with self.assertRaises((copies.CopyError, OSError)): copies.load(path)
        self.assertEqual(secret.read_bytes(), b'{"not_authorized":1}')

    def test_identity_rejects_ancestor_symlink_swap_during_read(self):
        folder = self.root / 'owned'; folder.mkdir(mode=0o700)
        path = folder / 'record'; path.write_bytes(b'synthetic'); path.chmod(0o600)
        moved = self.root / 'moved'; real_read = os.read; swapped = []
        def read(fd, count):
            result = real_read(fd, count)
            if not swapped:
                swapped.append(True); folder.rename(moved); folder.symlink_to(moved, target_is_directory=True)
            return result
        try:
            with patch.object(copies.os, 'read', side_effect=read):
                with self.assertRaisesRegex(copies.CopyError, 'ancestor|path|changed'):
                    copies.identity(path)
        finally:
            if folder.is_symlink(): folder.unlink()
        self.assertEqual((moved / 'record').read_bytes(), b'synthetic')

    def test_writes_pin_parent_and_do_not_follow_swapped_ancestor(self):
        for operation in ('record', 'backup'):
            folder = self.root / ('owned-' + operation); folder.mkdir(mode=0o700)
            foreign = self.root / ('foreign-' + operation); foreign.mkdir(mode=0o700)
            moved = self.root / ('moved-' + operation)
            name = 'new.json' if operation == 'record' else 'new.sqlite'
            target = folder / name; real_open = os.open; swapped = []
            def opening(path, flags, *args, **kwargs):
                if Path(path).name == name and flags & os.O_CREAT and not swapped:
                    swapped.append(True); folder.rename(moved); folder.symlink_to(foreign, target_is_directory=True)
                return real_open(path, flags, *args, **kwargs)
            with self.subTest(operation=operation), patch.object(copies.os, 'open', side_effect=opening):
                with self.assertRaises((copies.CopyError, OSError)):
                    if operation == 'record': copies.durable(target, {'synthetic': True})
                    else: copies.backup(self.source, target)
            self.assertEqual(swapped, [True])
            self.assertFalse((foreign / name).exists())
            folder.unlink()

    def test_destination_sidecar_injected_before_connect_and_after_close(self):
        for point in ('source-open', 'destination-close'):
            destination = self.root / (point + '.sqlite')
            side = Path(str(destination) + '-journal')
            real_connect = sqlite3.connect; destination_opens = []
            class Connection(sqlite3.Connection):
                def close(self):
                    super().close()
                    side.write_bytes(b'synthetic foreign journal'); side.chmod(0o600)
            def connect(path, *args, **kwargs):
                if 'mode=rw' in str(path):
                    destination_opens.append(True)
                    if point == 'destination-close': kwargs['factory'] = Connection
                    return real_connect(path, *args, **kwargs)
                conn = real_connect(path, *args, **kwargs)
                if point == 'source-open':
                    side.write_bytes(b'synthetic foreign journal'); side.chmod(0o600)
                return conn
            with self.subTest(point=point), patch.object(copies.sqlite3, 'connect', side_effect=connect):
                with self.assertRaisesRegex(copies.CopyError, 'sidecar'):
                    copies.backup(self.source, destination)
            if point == 'source-open': self.assertEqual(destination_opens, [])
            self.assertEqual(side.read_bytes(), b'synthetic foreign journal')

    def test_forbidden_casefold_components_before_sqlite(self):
        for name in ('cOnTaInErS', 'gRoUp CoNtAiNeRs', 'kEyChAiNs', 'ThInGs-OfFlInE-LaB'):
            folder = self.root / name
            folder.mkdir(mode=0o700)
            path = folder / 'fixture.sqlite'
            shutil.copyfile(self.source, path); path.chmod(0o600)
            with self.subTest(component=name), patch.object(copies.sqlite3, 'connect') as connect:
                with self.assertRaisesRegex(copies.CopyError, 'forbidden'):
                    copies.backup(path, self.root / 'output.sqlite')
                connect.assert_not_called()

    def test_physical_forbidden_ancestor_identity(self):
        # Own sentinel substitutes for a forbidden physical root; no live stat/read.
        with patch.object(copies, 'forbidden_roots', return_value=[self.root], create=True):
            with self.assertRaisesRegex(copies.CopyError, 'forbidden'):
                copies.checked(self.source)

    def test_real_case_alias_on_this_volume(self):
        original = self.root / 'Containers'; original.mkdir(mode=0o700)
        alternate = self.root / 'containers'
        if not alternate.exists():
            self.skipTest('synthetic volume is case-sensitive; alias lane inapplicable')
        self.assertTrue(os.path.samefile(original, alternate))
        path = original / 'fixture.sqlite'
        shutil.copyfile(self.source, path); path.chmod(0o600)
        with self.assertRaisesRegex(copies.CopyError, 'forbidden'):
            copies.checked(alternate / path.name)

    def test_destination_sidecars_refused_without_open_or_cleanup(self):
        sentinel = self.root / 'sentinel'; sentinel.write_bytes(b'synthetic untouched'); sentinel.chmod(0o600)
        for suffix in ('-wal', '-shm', '-journal'):
            for kind in ('empty', 'stale', 'symlink', 'dangling', 'hardlink', 'fifo'):
                destination = self.root / ('out-' + kind + suffix + '.sqlite')
                side = Path(str(destination) + suffix)
                if kind == 'symlink': side.symlink_to(sentinel)
                elif kind == 'dangling': side.symlink_to(self.root / 'missing')
                elif kind == 'hardlink': os.link(sentinel, side)
                elif kind == 'fifo': os.mkfifo(side, 0o600)
                else: side.write_bytes(b'' if kind == 'empty' else b'stale'); side.chmod(0o600)
                with self.subTest(suffix=suffix, kind=kind), patch.object(copies.sqlite3, 'connect') as connect:
                    with self.assertRaisesRegex(copies.CopyError, 'sidecar'):
                        copies.backup(self.source, destination)
                    connect.assert_not_called()
                    self.assertFalse(destination.exists())
                    self.assertTrue(os.path.lexists(side))
                    self.assertEqual(sentinel.read_bytes(), b'synthetic untouched')
                side.unlink()


def synthetic_worker():
    """Fresh process lifecycle worker; no native backend may start here."""
    packet, approval, point = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    real_durable, real_backup, real_fsync = wording.durable, wording.backup, os.fsync
    def crash():
        # Evidence is owned synthetic data, written even inside the fsync seam.
        path = packet / 'crash-reached.json'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, copies.canonical({'point': point})); real_fsync(fd)
        finally: os.close(fd)
        os._exit(71)
    def record(path, value):
        if Path(path).name == 'complete.json' and point == 'complete-fsync':
            with patch.object(copies.os, 'fsync', side_effect=lambda _: crash()):
                return real_durable(path, value)
        result = real_durable(path, value)
        if (Path(path).name, point) in (('applying.json', 'applying'), ('complete.json', 'complete-written')): crash()
        return result
    def backup(*args):
        if point == 'backup-enter': crash()
        result = real_backup(*args)
        if point == 'backup-exit': crash()
        return result
    with ExitStack() as stack:
        stack.enter_context(patch.object(wording.native_runtime, 'verify', return_value={'synthetic_lifecycle_runtime': True}))
        stack.enter_context(patch.object(wording.native_runtime, 'stopped'))
        stack.enter_context(patch.object(wording.native_runtime, 'run', side_effect=AssertionError('native replay forbidden')))
        stack.enter_context(patch.object(wording, 'validate', side_effect=synthetic_verdict))
        stack.enter_context(patch.object(wording, 'verify_schema', return_value='0' * 64))
        stack.enter_context(patch.object(wording, 'durable', side_effect=record))
        stack.enter_context(patch.object(wording, 'backup', side_effect=backup))
        sys.stdin.readline()
        try: wording.apply_copy(packet, approval)
        except copies.CopyError:
            print('refused'); sys.exit(2)
        print('output')


if __name__ == '__main__':
    unittest.main()
