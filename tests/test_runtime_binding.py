"""Runtime-only synthetic fixtures: never load an application framework."""
import copy
import json
import os
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch

from things_workbench import native_runtime as nr
from things_workbench.copies import CopyError, identity

ORIGINAL_SOURCES = nr.sources


class RuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        for name in ('wording', 'scratch.dylib', 'canary'):
            path = self.runtime / name
            path.write_bytes(b'synthetic artifact, not executable')
            path.chmod(0o700 if name != 'scratch.dylib' else 0o600)
        self.source_pins = {name: '1' * 64 for name in nr.REQUIRED_SOURCES}
        self.app_pins = {'Contents/Info.plist': '2' * 64}
        self.manifest = {
            'version': 2, 'state': 'ready', 'layout': 1,
            'root': str(self.runtime), 'app': str(self.root / 'Fixture.app'),
            'application': self.app_pins, 'sources': self.source_pins,
            'artifacts': {n: identity(self.runtime / n, private=False) for n in ('wording', 'scratch.dylib', 'canary')},
            'commands': [['/usr/bin/xcrun', 'clang']],
            'dependencies': {},
            'toolchain': {'clang': 'fixture', 'swift': 'fixture', 'sdk': '/synthetic/sdk', 'sdk_version': '1',
                          'compiler_identities': {k: {'path': '/synthetic/compiler', 'device': 1, 'inode': 1,
                                                     'size': 1, 'sha256': '1' * 64} for k in ('clang', 'swift')},
                          'sdk_settings': {'SDKSettings.json': '1' * 64}},
            'os': nr.platform.platform(),
            'python': {'executable': sys.executable, 'version': sys.version, 'sha256': nr.sha(sys.executable)},
        }
        self.addCleanup(patch.stopall)
        self.closure_patcher = patch.object(nr, 'dependency_closure', return_value={'synthetic': 'complete'})
        self.closure_mock = self.closure_patcher.start()
        self.manifest['dependencies'] = {'synthetic': 'complete'}
        patch.object(nr, 'sources', return_value=self.source_pins).start()
        patch.object(nr, 'application', return_value=self.app_pins).start()

    def save(self, manifest):
        path = self.runtime / 'runtime.json'
        path.write_text(json.dumps(manifest))
        path.chmod(0o600)

    def test_run_refuses_writable_overlap_before_process_start(self):
        plan = self.root / 'plan.json'
        plan.write_text('{}')
        plan.chmod(0o600)
        with patch.object(nr, 'verify', return_value=self.manifest), patch.object(nr, 'stopped'), \
             patch.object(nr.subprocess, 'run') as run:
            with self.assertRaisesRegex(CopyError, 'overlap'):
                nr.run(self.runtime, self.runtime, plan)
            run.assert_not_called()

    def test_run_uses_fixed_schema_and_preserves_full_proof(self):
        work = self.root / 'work'
        work.mkdir(mode=0o700)
        plan = self.root / 'plan.json'
        plan.write_text('{}')
        plan.chmod(0o600)
        proof = {'metadata': {'opaque': ['preserve', 1]}, 'other': 'proof'}
        completed = nr.subprocess.CompletedProcess([], 0, json.dumps(proof).encode(), b'')
        with patch.object(nr, 'verify', return_value=self.manifest), \
             patch.object(nr, 'stopped'), patch.object(nr.subprocess, 'run', return_value=completed) as run:
            self.assertEqual(nr.run(self.runtime, work, plan), proof)
        args, kwargs = run.call_args
        self.assertEqual(args[0][-4:], [str(self.runtime / 'wording'), str(work / 'candidate.sqlite'),
                                      str(plan), str(nr.RESOURCE / 'schema_32400506.json')])
        self.assertIn('SCHEMA=' + str(nr.RESOURCE / 'schema_32400506.json'), args[0])
        self.assertTrue(kwargs['close_fds'])
        self.assertLessEqual(kwargs['timeout'], 30)
        self.assertNotIn('DYLD_INSERT_LIBRARIES', kwargs['env'])
        self.assertEqual(json.loads((work / 'native-result.json').read_text())['stdout'], json.dumps(proof))

    def test_build_and_inspection_commands_have_clean_environment(self):
        sdk = self.root / 'SDK'
        sdk.mkdir()
        (sdk / 'SDKSettings.json').write_text('{}')
        commands = []

        def fake_run(argv, **kwargs):
            commands.append((argv, kwargs))
            if '-o' in argv:
                Path(argv[argv.index('-o') + 1]).write_bytes(macho_bytes())
            output = b'fixture compiler 1\n'
            if '--show-sdk-path' in argv:
                output = str(sdk).encode() + b'\n'
            if '--find' in argv:
                output = b'/usr/bin/true\n'
            return nr.subprocess.CompletedProcess(argv, 0, output, b'')

        with patch.object(nr, 'stopped'), patch.object(nr.subprocess, 'run', side_effect=fake_run), \
             patch.dict(os.environ, {'DYLD_LIBRARY_PATH': '/injected', 'SDKROOT': '/injected', 'CPATH': '/injected'}):
            destination = nr.build(self.manifest['app'], self.root / 'built')
        for argv, kwargs in commands:
            with self.subTest(argv=argv):
                self.assertEqual(kwargs.get('env'), nr.environment())
                self.assertIs(kwargs.get('close_fds'), True)
                self.assertLessEqual(kwargs.get('timeout', 999), 120)
        record = json.loads((destination / 'runtime.json').read_text())
        self.assertEqual(record['version'], 2)
        self.assertEqual(record['state'], 'ready')
        self.assertEqual(record['dependencies'], self.closure_mock.return_value)
        self.assertIn('compiler_identities', record['toolchain'])
        self.assertIn('sdk_settings', record['toolchain'])

    def test_genuine_sized_runtime_build_roundtrip_keeps_complete_closure(self):
        # Match the observed 20-image / 15,379-edge shape, not private paths.
        from things_workbench import copies
        prefix = '/synthetic/' + 'framework-layout/' * 8
        images = {prefix + str(i): {'identity': {'path': prefix + str(i),
                  'device': 1, 'inode': i, 'size': 32, 'sha256': '1' * 64},
                  'slices': {'16777228:0': {'dependencies': [], 'rpaths': []}}}
                  for i in range(20)}
        edges = [{'loader': prefix + str(i % 20), 'arch': '16777228:0',
                  'executable': prefix + 'wording', 'rpaths': [prefix, prefix + 'nested'],
                  'name': '@rpath/ThingsModel.framework/ThingsModel', 'command': 12,
                  'target': prefix + str((i + 1) % 20)} for i in range(15379)]
        closure = {'version': 1, 'roots': [prefix + 'wording'], 'images': images,
                   'edges': edges, 'os_images': ['/usr/lib/libSystem.B.dylib'],
                   'os_roots': [str(p) for p in nr.OS_ROOTS], 'absent_rpaths': []}
        self.assertGreater(len(copies.canonical(closure)), 11309313)
        self.assertLess(len(copies.canonical(closure)), 16777216)
        self.closure_mock.return_value = closure
        def compile_fixture(argv, **kwargs):
            Path(argv[argv.index('-o') + 1]).write_bytes(macho_bytes())
            return nr.subprocess.CompletedProcess(argv, 0, b'', b'')
        with patch.object(nr, 'stopped'), \
             patch.object(nr, 'toolchain_receipt', return_value=self.manifest['toolchain']), \
             patch.object(nr.subprocess, 'run', side_effect=compile_fixture):
            root = nr.build(self.manifest['app'], self.root / 'large-runtime')
        result = nr.verify(root)
        self.assertEqual(result['dependencies'], closure)
        self.assertEqual(len(result['dependencies']['images']), 20)
        self.assertEqual(len(result['dependencies']['edges']), 15379)
        self.assertEqual(result['sources'], self.source_pins)
        self.closure_mock.return_value = {**closure, 'edges': edges[:-1]}
        with self.assertRaisesRegex(CopyError, 'dependency'):
            nr.verify(root)

    def test_record_kind_limits_are_symmetric_and_not_filename_authority(self):
        from things_workbench import copies
        self.assertEqual(copies.MAX_RECORD_BYTES, 4194304)
        self.assertEqual(copies.MAX_NATIVE_RUNTIME_RECORD_BYTES, 16777216)
        for kind, limit in [(None, 4194304), ('native-runtime', 16777216)]:
            for extra in (0, 1):
                value = copy.deepcopy(self.manifest) if kind else {'padding': ''}
                key = 'os' if kind else 'padding'
                value[key] = ''
                value[key] = 'x' * (limit + extra - len(copies.canonical(value)))
                path = self.runtime / ('bounded-' + str(kind) + str(extra) + '.json')
                if extra:
                    with self.assertRaisesRegex(CopyError, 'record byte budget'):
                        copies.durable(path, value, record_kind=kind)
                    self.assertFalse(path.exists())
                    path.write_bytes(copies.canonical(value)); path.chmod(0o600)
                    with self.assertRaisesRegex(CopyError, 'record byte budget'):
                        copies.load(path, record_kind=kind)
                else:
                    copies.durable(path, value, record_kind=kind)
                    self.assertEqual(copies.load(path, record_kind=kind), value)
        value = {**self.manifest, 'os': 'x' * 4194304}
        path = self.runtime / 'runtime.json'
        with self.assertRaisesRegex(CopyError, 'record byte budget'):
            copies.durable(path, value)
        copies.durable(path, value, record_kind='native-runtime')
        with self.assertRaisesRegex(CopyError, 'record byte budget'):
            copies.load(path)
        self.assertEqual(copies.load(path, record_kind='native-runtime'), value)

    def test_native_record_kind_preserves_schema_and_json_refusals(self):
        from things_workbench import copies
        bad = [None, [], {}, {**self.manifest, 'version': True},
               {**self.manifest, 'dependencies': []}, {**self.manifest, 'sources': {}},
               {**self.manifest, 'root': str(self.root)},
               {**self.manifest, 'python': {**self.manifest['python'], 'sha256': 1}}]
        for index, value in enumerate(bad):
            path = self.runtime / ('malformed-' + str(index) + '.json')
            with self.assertRaises(CopyError):
                copies.durable(path, value, record_kind='native-runtime')
            self.assertFalse(path.exists())
            path.write_bytes(copies.canonical(value)); path.chmod(0o600)
            with self.assertRaises(CopyError):
                copies.load(path, record_kind='native-runtime')
        for index, payload in enumerate((b'{"version":2,"version":2}', b'[' * 65 + b']' * 65, b'NaN')):
            path = self.runtime / ('bad-json-' + str(index))
            path.write_bytes(payload); path.chmod(0o600)
            with self.assertRaises(CopyError):
                copies.load(path, record_kind='native-runtime')
        path = self.runtime / 'kinds.json'
        copies.durable(path, {})
        for kind in (True, 16777216, [], {}, 'runtime.json', 'other'):
            with self.assertRaisesRegex(CopyError, 'unknown record kind'):
                copies.durable(self.runtime / 'never-created', {}, record_kind=kind)
            with self.assertRaisesRegex(CopyError, 'unknown record kind'):
                copies.load(path, record_kind=kind)

    def test_native_record_bytes_still_charge_shared_work_budget(self):
        from things_workbench import copies
        path = self.runtime / 'budget.json'
        copies.durable(path, self.manifest, record_kind='native-runtime')
        for operation in (lambda: copies.load(path, record_kind='native-runtime'),
                          lambda: copies.durable(self.runtime / 'never-written', self.manifest,
                                                 record_kind='native-runtime')):
            with self.assertRaisesRegex(CopyError, 'cumulative'):
                with patch.object(copies, 'MAX_WORK_BYTES', 1), copies.work_scope():
                    operation()
        self.assertFalse((self.runtime / 'never-written').exists())

    def test_stopped_inspection_environment_is_sanitized(self):
        completed = nr.subprocess.CompletedProcess([], 1)
        with patch.object(nr.subprocess, 'run', return_value=completed) as run, \
             patch.dict(os.environ, {'DYLD_INSERT_LIBRARIES': '/injected'}):
            nr.stopped()
        self.assertEqual(run.call_args.kwargs.get('env'), nr.environment())
        self.assertIs(run.call_args.kwargs['close_fds'], True)

    def test_dependency_evidence_is_recomputed_not_trusted(self):
        self.save(self.manifest)
        self.assertEqual(nr.verify(self.runtime), self.manifest)
        self.closure_mock.return_value = {'synthetic': 'drift'}
        with self.assertRaisesRegex(CopyError, 'dependency'):
            nr.verify(self.runtime)
        self.closure_mock.return_value = self.manifest['dependencies']
        self.manifest['dependencies'] = {}
        self.save(self.manifest)
        with self.assertRaisesRegex(CopyError, 'dependency'):
            nr.verify(self.runtime)

    def test_manifest_envelope_and_identity_are_strict(self):
        cases = []
        for field in self.manifest:
            value = copy.deepcopy(self.manifest)
            del value[field]
            cases.append(value)
        for field, value in [('version', True), ('version', 1), ('layout', True),
                             ('state', 'building'), ('extra', 1), ('app', '../app'),
                             ('commands', []), ('toolchain', {}), ('python', {}),
                             ('application', {}), ('sources', {}), ('os', 1)]:
            broken = copy.deepcopy(self.manifest)
            broken[field] = value
            cases.append(broken)
        for field, value in [('inode', True), ('sha256', 'bad'), ('size', -1),
                             ('path', str(self.runtime / '..' / 'wording')), ('extra', 1)]:
            broken = copy.deepcopy(self.manifest)
            broken['artifacts']['wording'][field] = value
            cases.append(broken)
        for name in ('../wording', '/wording', 'other'):
            broken = copy.deepcopy(self.manifest)
            broken['artifacts'][name] = broken['artifacts']['wording']
            cases.append(broken)
        for index, broken in enumerate(cases):
            with self.subTest(index=index):
                self.save(broken)
                with self.assertRaises(CopyError):
                    nr.verify(self.runtime)

    def test_complete_source_inventory_rejects_each_missing_or_extra_file(self):
        package = self.root / 'whole-package'
        (package / 'native').mkdir(parents=True)
        for name in nr.REQUIRED_SOURCES:
            (package / name).write_text('synthetic source')
        with patch.object(nr, '__file__', str(package / 'native_runtime.py')), \
             patch.object(nr, 'RESOURCE', package / 'native'):
            self.assertEqual(set(ORIGINAL_SOURCES()), nr.REQUIRED_SOURCES)
            for name in nr.REQUIRED_SOURCES:
                with self.subTest(name=name):
                    path = package / name
                    path.unlink()
                    with self.assertRaises(CopyError):
                        ORIGINAL_SOURCES()
                    path.write_text('synthetic source')
            (package / 'extra.py').write_text('not approved')
            with self.assertRaises(CopyError):
                ORIGINAL_SOURCES()

    def test_required_sources_are_independent_of_directory_inventory(self):
        # A deleted package resource must not simply disappear from producer pins.
        package = self.root / 'package'
        package.mkdir()
        (package / 'native').mkdir()
        (package / 'native_runtime.py').write_text('fixture')
        with patch.object(nr, '__file__', str(package / 'native_runtime.py')), \
             patch.object(nr, 'RESOURCE', package / 'native'):
            # Stop just the fixture patch: exercise the real source collector.
            with self.assertRaises(CopyError):
                ORIGINAL_SOURCES()

    def test_required_artifacts_cannot_be_omitted(self):
        self.save(self.manifest)
        self.assertEqual(nr.verify(self.runtime), self.manifest)
        for name in ('wording', 'scratch.dylib', 'canary'):
            with self.subTest(name=name):
                broken = copy.deepcopy(self.manifest)
                del broken['artifacts'][name]
                self.save(broken)
                with self.assertRaises(CopyError):
                    nr.verify(self.runtime)


def macho_bytes(dependencies=(), rpaths=(), cpu=0x0100000C, subtype=0):
    commands = []
    for command, text in [(0xC, d) for d in dependencies] + [(0x8000001C, p) for p in rpaths]:
        offset = 24 if command == 0xC else 12
        payload = text.encode() + b'\0'
        size = (offset + len(payload) + 7) & ~7
        command_bytes = struct.pack('<III', command, size, offset)
        command_bytes += b'\0' * (offset - len(command_bytes)) + payload
        commands.append(command_bytes.ljust(size, b'\0'))
    body = b''.join(commands)
    return struct.pack('<8I', 0xFEEDFACF, cpu, subtype, 6, len(commands), len(body), 0, 0) + body


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.app = self.root / 'Fixture.app'
        self.frameworks = self.app / 'Contents/Frameworks'
        self.frameworks.mkdir(parents=True)
        self.main = self.app / 'Contents/MacOS/Things3'
        self.main.parent.mkdir()
        self.main.write_bytes(macho_bytes())
        for name in ('wording', 'scratch.dylib', 'canary'):
            (self.runtime / name).write_bytes(macho_bytes())
        self.library = self.frameworks / 'A.dylib'
        self.library.write_bytes(macho_bytes())
        self.leaf = self.frameworks / 'B.dylib'
        self.leaf.write_bytes(macho_bytes())
        self.helper = self.runtime / 'wording'
        self.helper.write_bytes(macho_bytes(['@rpath/A.dylib'], [str(self.frameworks)]))
        self.library.write_bytes(macho_bytes(['@loader_path/B.dylib']))

    def pins(self):
        return {str(p.relative_to(self.app)): nr.sha(p)
                for p in self.app.rglob('*') if p.is_file()}

    def closure(self):
        self.assertTrue(callable(getattr(nr, 'dependency_closure', None)), 'recursive enforcement missing')
        return nr.dependency_closure(self.runtime, self.app, self.pins())

    def test_loader_command_and_unknown_required_commands_fail_closed(self):
        payload = b'/outside/dyld\0'
        size = (12 + len(payload) + 7) & ~7
        command = (struct.pack('<III', 0xE, size, 12) + payload).ljust(size, b'\0')
        self.helper.write_bytes(struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, 2, 1, size, 0, 0) + command)
        with self.assertRaisesRegex(CopyError, 'outside'):
            self.closure()
        for command in (0x80000035, 0x8000FFFF):
            self.helper.write_bytes(struct.pack('<8I', 0xFEEDFACF, 0x0100000C, 0, 2, 1, 8, 0, 0)
                                    + struct.pack('<II', command, 8))
            with self.assertRaisesRegex(CopyError, 'unsupported'):
                self.closure()

    def test_os_cryptex_canonical_framework_is_trusted(self):
        path = '/System/Volumes/Preboot/Cryptexes/OS/System/Library/Frameworks/WebKit.framework/Versions/A/WebKit'
        self.leaf.write_bytes(macho_bytes([path]))
        with patch.object(nr, '_os_available', return_value=True):
            self.assertIn(path, self.closure()['os_images'])

    def test_pinned_framework_absent_executable_fallback_is_bound(self):
        # Bundled frameworks retain this app-relative search path when loaded
        # by a standalone helper. It must never become an external load grant.
        self.library.write_bytes(macho_bytes(['@loader_path/B.dylib'], ['@executable_path/../Frameworks']))
        closure = self.closure()
        self.assertIn(str(self.root / 'Frameworks'), closure['absent_rpaths'])
        (self.root / 'Frameworks').mkdir()
        with self.assertRaisesRegex(CopyError, 'external rpath'):
            self.closure()

    def test_rpath_search_skips_missing_candidates_but_refuses_ambiguity(self):
        second = self.frameworks / 'second'
        second.mkdir()
        self.helper.write_bytes(macho_bytes(['@rpath/A.dylib'], [str(second), str(self.frameworks)]))
        self.assertIn(str(self.library), self.closure()['images'])
        (second / 'A.dylib').write_bytes(macho_bytes())
        with self.assertRaisesRegex(CopyError, 'ambiguous'):
            self.closure()

    def test_external_rpath_and_missing_dependency_refused(self):
        self.helper.write_bytes(macho_bytes(['@rpath/A.dylib'], [str(self.root), str(self.frameworks)]))
        with self.assertRaisesRegex(CopyError, 'external rpath'):
            self.closure()
        self.helper.write_bytes(macho_bytes(['@rpath/not-there.dylib'], [str(self.frameworks)]))
        with self.assertRaisesRegex(CopyError, 'missing'):
            self.closure()

    def test_universal_slices_are_inspected_and_resolved(self):
        arm = macho_bytes()
        intel = macho_bytes(cpu=0x01000007, subtype=3)
        fat = (struct.pack('>II', 0xCAFEBABE, 2)
               + struct.pack('>IIIII', 0x0100000C, 0, 48, len(arm), 0)
               + struct.pack('>IIIII', 0x01000007, 3, 48 + len(arm), len(intel), 0)
               + arm + intel)
        self.main.write_bytes(fat)
        closure = self.closure()
        self.assertEqual(len(closure['images'][str(self.main)]['slices']), 2)
        # A second architecture must not conceal an external dependency.
        intel = macho_bytes(['/outside/unverified.dylib'], cpu=0x01000007, subtype=3)
        fat = (struct.pack('>II', 0xCAFEBABE, 2)
               + struct.pack('>IIIII', 0x0100000C, 0, 48, len(arm), 0)
               + struct.pack('>IIIII', 0x01000007, 3, 48 + len(arm), len(intel), 0)
               + arm + intel)
        self.main.write_bytes(fat)
        with self.assertRaisesRegex(CopyError, 'outside'):
            self.closure()

    def test_framework_symlink_binds_canonical_identity(self):
        versions = self.frameworks / 'C.framework/Versions/A'
        versions.mkdir(parents=True)
        actual = versions / 'C'
        actual.write_bytes(macho_bytes())
        framework = versions.parent.parent
        (framework / 'Versions/Current').symlink_to('A')
        (framework / 'C').symlink_to('Versions/Current/C')
        self.helper.write_bytes(macho_bytes(['@rpath/C.framework/C'], [str(self.frameworks)]))
        closure = self.closure()
        self.assertIn(str(actual), closure['images'])
        self.assertEqual(closure['edges'][0]['target'], str(actual))

    def test_executable_path_and_os_trust_are_explicit(self):
        self.main.write_bytes(macho_bytes(['@executable_path/../Frameworks/A.dylib']))
        self.leaf.write_bytes(macho_bytes(['/usr/lib/libSystem.B.dylib']))
        with patch.object(nr, '_os_available', return_value=True):
            self.assertIn('/usr/lib/libSystem.B.dylib', self.closure()['os_images'])
        with patch.object(nr, '_os_available', return_value=False):
            with self.assertRaisesRegex(CopyError, 'missing OS'):
                self.closure()
        self.leaf.write_bytes(macho_bytes(['/usr/local/lib/not-OS.dylib']))
        with self.assertRaisesRegex(CopyError, 'outside'):
            self.closure()

    def test_symlink_dotdot_uses_filesystem_not_lexical_resolution(self):
        nested = self.frameworks / 'different/nested'
        nested.mkdir(parents=True)
        target = nested.parent / 'A.dylib'
        target.write_bytes(macho_bytes())
        (self.frameworks / 'alias').symlink_to('different/nested')
        self.helper.write_bytes(macho_bytes([str(self.frameworks / 'alias/../A.dylib')]))
        self.assertIn(str(target), self.closure()['images'])

    def test_closure_binds_bytes_and_rejects_unpinned_app_file(self):
        first = self.closure()
        self.leaf.write_bytes(macho_bytes(rpaths=['@loader_path']))
        second = self.closure()
        self.assertNotEqual(first, second)
        pins = self.pins()
        del pins[str(self.leaf.relative_to(self.app))]
        with self.assertRaisesRegex(CopyError, 'outside'):
            nr.dependency_closure(self.runtime, self.app, pins)

    def test_recursive_external_dependency_is_refused(self):
        good = self.closure()
        self.assertIn(str(self.leaf), good['images'])
        external = self.root / 'external.dylib'
        external.write_bytes(macho_bytes())
        self.leaf.write_bytes(macho_bytes([str(external)]))
        with self.assertRaisesRegex(CopyError, 'outside|external'):
            self.closure()


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TWB_RUNTIME_CANARIES') == '1',
                     'explicit harmless runtime sandbox canaries only')
class SandboxCanaryTests(unittest.TestCase):
    def test_real_denials_descriptor_environment_and_inherited_fd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            app = root / 'Empty.app'
            app.mkdir(mode=0o700)
            sentinel = root / 'outside-synthetic'
            sentinel.write_text('synthetic, not a credential')
            sentinel.chmod(0o600)
            code = root / 'fd_environment.c'
            code.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    FILE *plan = fopen(argv[2], "r"); int fd = -1;
    if (!plan || fscanf(plan, "%d", &fd) != 1) return 3;
    fclose(plan);
    errno = 0;
    int closed = fcntl(fd, F_GETFD) == -1 && errno == EBADF;
    int clean = !getenv("DYLD_LIBRARY_PATH") && !getenv("CPATH") && !getenv("PYTHONPATH")
        && getenv("HOME") && getenv("TWB_SCRATCH_DIRECTORY")
        && !strcmp(getenv("HOME"), getenv("CFFIXED_USER_HOME"));
    FILE *schema = fopen(argv[3], "r"); int readable = schema != NULL;
    if (schema) fclose(schema);
    printf("{\"fd_closed\":%s,\"environment_clean\":%s,\"schema_readable\":%s}\n",
           closed ? "true" : "false", clean ? "true" : "false", readable ? "true" : "false");
    return closed && clean && readable ? 0 : 1;
}
''')
            for source, output, flags in [(nr.RESOURCE / 'canary.c', runtime / 'canary', []),
                                          (nr.RESOURCE / 'scratch.c', runtime / 'scratch.dylib', ['-dynamiclib']),
                                          (code, runtime / 'wording', [])]:
                nr.subprocess.run(['/usr/bin/xcrun', 'clang', '-Wall', '-Wextra', '-Werror', *flags,
                                   str(source), '-o', str(output)], check=True, capture_output=True,
                                  env=nr.environment(), close_fds=True, timeout=120)
                output.chmod(0o600 if output.suffix == '.dylib' else 0o700)
            with patch.object(nr, 'verify', return_value={'app': str(app)}), patch.object(nr, 'stopped'):
                denials = nr.probe(runtime, root / 'probe')
                self.assertTrue(all(denials.values()), denials)
                work = root / 'work'
                work.mkdir(mode=0o700)
                fd = os.open(sentinel, os.O_RDONLY)
                try:
                    os.set_inheritable(fd, True)
                    plan = root / 'plan.json'
                    plan.write_text(str(fd))
                    plan.chmod(0o600)
                    with patch.dict(os.environ, {'DYLD_LIBRARY_PATH': '/synthetic-injection',
                                                 'DYLD_INSERT_LIBRARIES': '/synthetic-injection',
                                                 'CPATH': '/synthetic-injection', 'PYTHONPATH': '/synthetic-injection'}):
                        try:
                            proof = nr.run(runtime, work, plan)
                        except CopyError:
                            self.fail((work / 'native-result.json').read_text())
                    self.assertEqual(proof, {'fd_closed': True, 'environment_clean': True, 'schema_readable': True})
                finally:
                    os.close(fd)
            self.assertEqual(sentinel.read_text(), 'synthetic, not a credential')


if __name__ == '__main__':
    unittest.main()
