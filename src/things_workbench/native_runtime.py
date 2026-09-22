"""Explicit local build and deny-network native supervisor. Never auto-build."""
import hashlib
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
import struct
import stat
from .copies import CopyError, checked, durable, identity, load, new_root, digest, raw_read_scope, bounded_paths

RESOURCE = Path(__file__).parent / 'native'
ARTIFACTS = frozenset(('wording', 'scratch.dylib', 'canary'))
REQUIRED_SOURCES = frozenset((
    '__init__.py', '__main__.py', 'cli.py', 'copy_cli.py', 'copies.py',
    'fingerprint.py', 'history.py', 'native_runtime.py', 'schema_policy.py', 'wording.py', 'note_representation.py',
    'publication.py', 'publication_runtime.py', 'publication_cli.py',
    'native/canary.c', 'native/coordinator.swift', 'native/copy.sb',
    'native/date_324.h', 'native/scratch.c', 'native/wording.m',
    'native/schema_32400506.json',
))
MANIFEST_KEYS = frozenset(('version', 'state', 'layout', 'root', 'app', 'application',
    'sources', 'artifacts', 'commands', 'dependencies', 'toolchain', 'os', 'python'))


def _hash(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _absolute(value):
    return (type(value) is str and '\x00' not in value and value.startswith('/')
            and os.path.normpath(value) == value)


def _relative(value):
    return (type(value) is str and value and '\x00' not in value
            and not value.startswith('/') and all(p not in ('', '.', '..') for p in value.split('/')))


def _schema(manifest, runtime):
    """Validate the consumer's schema, never a producer-supplied list of seals."""
    if type(manifest) is not dict or set(manifest) != MANIFEST_KEYS:
        raise CopyError('runtime record fields invalid')
    if (type(manifest['version']) is not int or manifest['version'] != 2
            or type(manifest['layout']) is not int or manifest['layout'] != 1
            or manifest['state'] != 'ready'):
        raise CopyError('runtime version/state/layout invalid')
    if manifest['root'] != str(runtime) or not _absolute(manifest['app']):
        raise CopyError('runtime location invalid')
    pins = manifest['sources']
    if type(pins) is not dict or set(pins) != REQUIRED_SOURCES or not all(_hash(v) for v in pins.values()):
        raise CopyError('runtime required source pins invalid')
    pins = manifest['application']
    if type(pins) is not dict or not pins or not all(_relative(k) for k in pins):
        raise CopyError('runtime application pins invalid')
    for value in pins.values():
        if not (_hash(value) or (type(value) is dict and set(value) == {'link'}
                                and type(value['link']) is str and value['link'] and '\x00' not in value['link'])):
            raise CopyError('runtime application pin invalid')
    pins = manifest['artifacts']
    if type(pins) is not dict or set(pins) != ARTIFACTS:
        raise CopyError('runtime required artifacts invalid')
    for name, value in pins.items():
        if (type(value) is not dict or set(value) != {'path', 'device', 'inode', 'size', 'sha256'}
                or value['path'] != str(runtime / name) or not _hash(value['sha256'])
                or any(type(value[k]) is not int or value[k] < 0 for k in ('device', 'inode', 'size'))):
            raise CopyError('runtime artifact identity invalid')
    commands = manifest['commands']
    if (type(commands) is not list or not commands or any(type(c) is not list or not c
            or not _absolute(c[0]) or any(type(a) is not str or '\x00' in a for a in c) for c in commands)):
        raise CopyError('runtime command receipt invalid')
    toolchain = manifest['toolchain']
    if (type(toolchain) is not dict or set(toolchain) != {'clang', 'swift', 'sdk', 'sdk_version', 'compiler_identities', 'sdk_settings'}
            or any(type(toolchain[k]) is not str or not toolchain[k] for k in ('clang', 'swift', 'sdk', 'sdk_version'))
            or not _absolute(toolchain['sdk'])):
        raise CopyError('runtime toolchain receipt invalid')
    compilers = toolchain['compiler_identities']
    settings = toolchain['sdk_settings']
    if (type(compilers) is not dict or set(compilers) != {'clang', 'swift'}
            or type(settings) is not dict or not settings
            or not set(settings) <= {'SDKSettings.json', 'SDKSettings.plist'}
            or not all(_hash(v) for v in settings.values())):
        raise CopyError('runtime compiler/SDK receipt invalid')
    for value in compilers.values():
        if (type(value) is not dict or set(value) != {'path', 'device', 'inode', 'size', 'sha256'}
                or not _absolute(value['path']) or not _hash(value['sha256'])
                or any(type(value[k]) is not int or value[k] < 0 for k in ('device', 'inode', 'size'))):
            raise CopyError('runtime compiler identity invalid')
    python = manifest['python']
    if (type(python) is not dict or set(python) != {'executable', 'version', 'sha256'}
            or not _absolute(python['executable']) or type(python['version']) is not str
            or not _hash(python['sha256']) or type(manifest['os']) is not str
            or type(manifest['dependencies']) is not dict):
        raise CopyError('runtime interpreter/OS/dependency receipt invalid')

# Reviewed discovery evidence for the only supported binary release.
PINS = {
    'Contents/MacOS/Things3': 'f3e2ebde29695333026c3d20e6d5d4bf7cd2ecf06fa5649a3ddb66720842395f',
    'Base':'0bd5cb0bd701c4bf99de9235a1d1a54d50b9fb1dec56df6f031c32d3d6cf7079',
    'ThingsModel':'2c18aa2c010151c9ee8d1d33b5915a8161aef659100cec1b433a33c8aa7eb7aa',
    'Syncrony':'b6dc35bbc72030c4979d466ec581d54b5adbeb1660437d2118423be002f32590',
    'ThingsCommon':'6c4268539704d02061393ec199775b4db0bff05bdc89e02f93a81db20f5a6ebb',
    'FoundationAdditions':'6f13c2ebe6658d799cc6c5c84563dcb14708c3467bd4662dcbc1fd6d1db437b6',
}


def sha(path):
    with raw_read_scope(path), open(path,'rb') as f:
        from . import copies
        h = hashlib.sha256(); total = 0
        while block := f.read(1024*1024):
            total += len(block)
            copies.check_budget(byte_count=len(block))
            if total > copies.MAX_FILE_BYTES: raise CopyError('runtime byte budget exceeded')
            h.update(block)
        return h.hexdigest()


def resource_bytes(path):
    from . import copies
    with raw_read_scope(path), open(path, 'rb') as f:
        data = f.read(copies.MAX_FILE_BYTES + 1)
        if len(data) > copies.MAX_FILE_BYTES: raise CopyError('runtime byte budget exceeded')
        copies.check_budget(byte_count=len(data))
        return data


def stopped():
    try:
        result = subprocess.run(['/usr/bin/pgrep','-x','Things3'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=environment(),close_fds=True,timeout=5)
    except (subprocess.SubprocessError, OSError) as exc:
        raise CopyError('process census unavailable; stopped state unproven') from exc
    if result.returncode != 1:
        raise CopyError('Things must remain stopped; no app control is performed')


def sources():
    root = Path(__file__).parent
    actual = {str(p.relative_to(root)) for p in bounded_paths(root)
              if '__pycache__' not in p.parts and not p.is_dir()}
    if actual != REQUIRED_SOURCES:
        raise CopyError('required package source/resource inventory mismatch')
    result = {}
    for name in sorted(REQUIRED_SOURCES):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise CopyError('package source/resource must be a regular file')
        result[name] = sha(path)
    return result


def application(app):
    app = Path(os.path.abspath(app))
    if app.is_symlink() or not app.is_dir() or platform.machine() != 'arm64':
        raise CopyError('unsupported application or architecture')
    info = plistlib.loads(resource_bytes(app/'Contents/Info.plist'))
    if info.get('CFBundleVersion') != '32400506' or info.get('CFBundleShortVersionString') != '3.24' or info.get('CFBundleIdentifier') != 'com.culturedcode.ThingsMac':
        raise CopyError('unsupported Things build')
    for key,expected in PINS.items():
        relative = key if '/' in key else 'Contents/Frameworks/'+key+'.framework/'+key
        if sha(app/relative) != expected:
            raise CopyError('unsupported framework bytes')
    # Pin every regular resource and symlink target in the private framework tree,
    # not merely the six discovery binaries. System libraries are OS trust roots.
    result = {'Contents/Info.plist':sha(app/'Contents/Info.plist'),'Contents/MacOS/Things3':sha(app/'Contents/MacOS/Things3')}
    for p in bounded_paths(app/'Contents/Frameworks'):
        resolved = p.resolve()
        if not resolved.is_relative_to(app.resolve()):
            raise CopyError('framework dependency escapes application')
        if p.is_file():
            result[str(p.relative_to(app))] = sha(p)
        elif p.is_symlink():
            result[str(p.relative_to(app))] = {'link':os.readlink(p)}
    return result


# These are OS trust roots, not an allowlist for /usr/local or arbitrary /Library.
OS_ROOTS = (Path('/usr/lib'), Path('/System/Library'), Path('/Library/Apple/System/Library'),
            Path('/System/Volumes/Preboot/Cryptexes/OS/System/Library'),
            Path('/System/Volumes/Preboot/Cryptexes/OS/usr/lib'))


def _thin_macho(data):
    if len(data) < 32 or data[:4] != b'\xcf\xfa\xed\xfe':
        raise CopyError('unsupported Mach-O image')
    _, cpu, subtype, kind, count, size, _, _ = struct.unpack_from('<8I', data)
    if kind not in (2, 6, 8) or count > 65536 or size > len(data) - 32:
        raise CopyError('malformed Mach-O header')
    dependencies, rpaths = [], []
    offset, end = 32, 32 + size
    for _ in range(count):
        if offset + 8 > end:
            raise CopyError('truncated Mach-O command')
        command, length = struct.unpack_from('<II', data, offset)
        if length < 8 or length % 8 or offset + length > end:
            raise CopyError('malformed Mach-O command')
        # Include weak, reexport, lazy and upward dependencies; missing weak loads
        # are deliberately refused rather than silently changing the closure.
        if command in (0xC, 0xE, 0x80000018, 0x8000001F, 0x20, 0x80000023, 0x8000001C):
            minimum = 12 if command in (0xE, 0x8000001C) else 24
            if length < minimum:
                raise CopyError('malformed Mach-O load name')
            start = struct.unpack_from('<I', data, offset + 8)[0]
            if not minimum <= start < length:
                raise CopyError('malformed Mach-O string offset')
            raw = data[offset + start:offset + length]
            if b'\0' not in raw:
                raise CopyError('unterminated Mach-O load name')
            try:
                name = raw.split(b'\0', 1)[0].decode('utf-8')
            except UnicodeError as exc:
                raise CopyError('invalid Mach-O load name') from exc
            if not name:
                raise CopyError('empty Mach-O load name')
            if command == 0x8000001C:
                rpaths.append(name)
            else:
                dependencies.append({'command': command, 'name': name})
        elif command not in (0x1, 0x2, 0x3, 0x4, 0x5, 0x8, 0xA, 0xB, 0xD, 0xF,
                             0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x19, 0x1A,
                             0x1B, 0x1D, 0x1E, 0x21, 0x22, 0x24, 0x25, 0x26, 0x29,
                             0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32,
                             0x80000022, 0x80000028, 0x80000033, 0x80000034):
            # Reject legacy FVMLIB/prebound loads, embedded dyld environment,
            # filesets and future commands until their load semantics are reviewed.
            raise CopyError('unsupported Mach-O dynamic loader command')
        offset += length
    if offset != end:
        raise CopyError('Mach-O load command size mismatch')
    return {str(cpu) + ':' + str(subtype): {'dependencies': dependencies, 'rpaths': rpaths}}


def inspect_macho(path):
    """Parse bytes rather than trusting an otool transcript or shell output."""
    try:
        data = resource_bytes(path)
    except OSError as exc:
        raise CopyError('Mach-O image unavailable') from exc
    if data[:4] not in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'):
        return _thin_macho(data)
    endian = '>' if data[0] == 0xCA else '<'
    wide = data[:4] in (b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')
    if len(data) < 8:
        raise CopyError('truncated universal Mach-O header')
    count = struct.unpack_from(endian + 'I', data, 4)[0]
    entry_size = 32 if wide else 20
    table_end = 8 + count * entry_size
    if not 0 < count <= 32 or table_end > len(data):
        raise CopyError('invalid universal Mach-O architecture table')
    result, ranges = {}, []
    for n in range(count):
        fields = struct.unpack_from(endian + ('IIQQII' if wide else 'IIIII'), data, 8 + n * entry_size)
        cpu, subtype, offset, size, alignment = fields[:5]
        if (alignment > 31 or offset % (1 << alignment) or offset < table_end
                or size < 32 or offset + size > len(data)
                or any(offset < end and offset + size > start for start, end in ranges)):
            raise CopyError('invalid universal Mach-O slice bounds')
        ranges.append((offset, offset + size))
        slices = _thin_macho(data[offset:offset + size])
        key = str(cpu) + ':' + str(subtype)
        if set(slices) != {key} or key in result:
            raise CopyError('universal Mach-O slice identity mismatch')
        result.update(slices)
    return result


def _os_path(path):
    return any(path.is_relative_to(root) for root in OS_ROOTS)


def _os_available(path):
    if path.is_file():
        return True
    # Modern macOS libraries may only exist in the dyld shared cache. Ask the
    # OS about membership, not whether an arbitrary missing pathname looks safe.
    if sys.platform != 'darwin':
        return False
    import ctypes
    try:
        system = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
        contains = system._dyld_shared_cache_contains_path
        contains.argtypes = [ctypes.c_char_p]
        contains.restype = ctypes.c_bool
        if contains(os.fsencode(path)):
            return True
        cryptex = Path('/System/Volumes/Preboot/Cryptexes/OS')
        if path.is_relative_to(cryptex):
            alias = Path('/') / path.relative_to(cryptex)
            # Only a real OS alias to this exact canonical image is acceptable.
            return alias.resolve() == path and bool(contains(os.fsencode(alias)))
        return False
    except (AttributeError, OSError):
        return False


def _image_identity(path):
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise CopyError('dependency is not a regular file')
    result = {'path': str(path), 'device': before.st_dev, 'inode': before.st_ino,
              'size': before.st_size, 'sha256': sha(path)}
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise CopyError('dependency changed during inspection')
    return result


def dependency_closure(runtime, app, app_pins):
    """Resolve every non-OS load recursively, tied to verified application pins.

    OS libraries are explicit trust leaves. This detects ordinary drift, not
    malicious same-UID/root races or a compromised interpreter/operating system.
    """
    runtime, app = Path(runtime).resolve(), Path(app).resolve()
    allowed = {runtime / name for name in ARTIFACTS}
    pinned = {}
    for name, value in app_pins.items():
        if not _relative(name):
            raise CopyError('invalid application resource path')
        if _hash(value):
            path = (app / name).resolve()
            if not path.is_relative_to(app):
                raise CopyError('application dependency outside verified root')
            if path in pinned and pinned[path] != value:
                raise CopyError('ambiguous application resource pin')
            pinned[path] = value
    allowed.update(pinned)
    images, edges, os_images, absent_rpaths = {}, [], set(), set()
    visited = set()

    def canonical(path, *, search=False):
        path = Path(path).resolve()
        if not _os_path(path) and path not in allowed:
            if not (search and not path.exists() and (path.is_relative_to(app) or path.is_relative_to(runtime))):
                raise CopyError('dependency outside verified application/runtime roots')
        return path

    def expand(name, loader, executable):
        for token, base in (('@loader_path', loader.parent), ('@executable_path', executable.parent)):
            if name == token or name.startswith(token + '/'):
                return Path(str(base) + name[len(token):])
        if name.startswith('/'):
            return Path(name)
        raise CopyError('unresolved relative or nested rpath load name')

    def visit(path, arch, executable, inherited, depth=0):
        from . import copies
        copies.check_budget()
        if depth > copies.MAX_DEPENDENCY_DEPTH: raise CopyError('dependency depth budget exceeded')
        path = canonical(path)
        if _os_path(path):
            if not _os_available(path):
                raise CopyError('missing OS dependency')
            os_images.add(str(path))
            return
        if not path.is_file():
            raise CopyError('missing Mach-O dependency')
        if str(path) not in images:
            record = _image_identity(path)
            if path in pinned and record['sha256'] != pinned[path]:
                raise CopyError('application dependency pin drift')
            images[str(path)] = {'identity': record, 'slices': inspect_macho(path)}
            if _image_identity(path) != record:
                raise CopyError('dependency drift during parsing')
        slices = images[str(path)]['slices']
        arches = list(slices) if arch is None else [arch]
        for current_arch in arches:
            if current_arch not in slices:
                raise CopyError('dependency architecture missing')
            info = slices[current_arch]
            local = []
            for raw in info['rpaths']:
                d = expand(raw, path, executable).resolve()
                if not (d.is_relative_to(app) or d.is_relative_to(runtime) or _os_path(d)):
                    # A pinned app framework has an app-layout fallback that is
                    # absent for the standalone executable. Bind its absence;
                    # never grant it as a search/load root. A created directory,
                    # even an empty one, invalidates the closure on revalidation.
                    if (path in pinned and raw == '@executable_path/../Frameworks'
                            and not os.path.lexists(d)):
                        absent_rpaths.add(str(d))
                        continue
                    raise CopyError('external rpath outside verified roots')
                local.append(str(d))
            stack = tuple(dict.fromkeys(tuple(local) + inherited))
            context = (path, current_arch, executable, stack)
            if context in visited:
                continue
            visited.add(context)
            if len(visited) > 4096:
                raise CopyError('dependency closure exceeds bounded inspection')
            for dependency in info['dependencies']:
                name = dependency['name']
                if name.startswith('@rpath/'):
                    candidates = [canonical(Path(d) / name[7:], search=True) for d in stack]
                    matches = {p for p in candidates if p.is_file() or (_os_path(p) and _os_available(p))}
                    if len(matches) != 1:
                        raise CopyError('missing or ambiguous rpath dependency')
                    target = matches.pop()
                else:
                    target = canonical(expand(name, path, executable))
                edge = {'loader': str(path), 'arch': current_arch, 'executable': str(executable),
                        'rpaths': list(stack), 'name': name, 'command': dependency['command'], 'target': str(target)}
                edges.append(edge)
                visit(target, current_arch, executable, stack, depth + 1)

    roots = [(runtime / 'wording', runtime / 'wording'),
             (runtime / 'scratch.dylib', runtime / 'wording'),
             (runtime / 'canary', runtime / 'canary'),
             (app / 'Contents/MacOS/Things3', app / 'Contents/MacOS/Things3')]
    for image, executable in roots:
        visit(image, None, executable.resolve(), ())
    return {'version': 1, 'roots': [str(p.resolve()) for p, _ in roots],
            'images': images, 'edges': edges, 'os_images': sorted(os_images),
            'os_roots': [str(p) for p in OS_ROOTS], 'absent_rpaths': sorted(absent_rpaths)}


def environment(work=None):
    result = {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'en_US.UTF-8'}
    if work:
        result.update(HOME=str(work),CFFIXED_USER_HOME=str(work),TMPDIR=str(work)+'/',TWB_SCRATCH_DIRECTORY=str(work)+'/')
    return result


def toolchain_receipt():
    versions = {}
    for name, argv in {
        'clang': ['/usr/bin/xcrun', 'clang', '--version'],
        'swift': ['/usr/bin/xcrun', 'swiftc', '--version'],
        'sdk': ['/usr/bin/xcrun', '--show-sdk-path'],
        'sdk_version': ['/usr/bin/xcrun', '--show-sdk-version'],
    }.items():
        try:
            result = subprocess.run(argv, capture_output=True, check=True,
                                    env=environment(), close_fds=True, timeout=20)
            versions[name] = result.stdout.decode('utf-8').strip()
        except (subprocess.SubprocessError, OSError, UnicodeError) as exc:
            raise CopyError('toolchain inspection refused') from exc
    compilers = {}
    for name, command in (('clang', 'clang'), ('swift', 'swiftc')):
        try:
            result = subprocess.run(['/usr/bin/xcrun', '--find', command], capture_output=True,
                                    check=True, env=environment(), close_fds=True, timeout=20)
            path = result.stdout.decode('utf-8').strip()
            if not _absolute(path):
                raise CopyError('compiler path invalid')
            compilers[name] = _image_identity(Path(path).resolve(strict=True))
        except (subprocess.SubprocessError, OSError, UnicodeError) as exc:
            raise CopyError('compiler identity unavailable') from exc
    sdk = versions['sdk']
    if not _absolute(sdk):
        raise CopyError('SDK path invalid')
    settings = {name: sha(Path(sdk) / name) for name in ('SDKSettings.json', 'SDKSettings.plist')
                if (Path(sdk) / name).is_file()}
    if not settings:
        raise CopyError('SDK settings receipt unavailable')
    versions.update(compiler_identities=compilers, sdk_settings=settings)
    return versions


def build(app, destination):
    stopped()
    app = Path(os.path.abspath(app))
    app_pins = application(app)
    source_pins = sources()
    versions = toolchain_receipt()
    root = new_root(destination)
    durable(root/'started.json',{'state':'building'})
    frameworks = app/'Contents/Frameworks'
    commands = [
        ['/usr/bin/xcrun','clang','-Wall','-Wextra','-Werror',str(RESOURCE/'canary.c'),'-o',str(root/'canary')],
        ['/usr/bin/xcrun','clang','-Wall','-Wextra','-Werror','-dynamiclib',str(RESOURCE/'scratch.c'),'-o',str(root/'scratch.dylib')],
        ['/usr/bin/xcrun','swiftc','-parse-as-library','-emit-object',str(RESOURCE/'coordinator.swift'),'-o',str(root/'coordinator.o')],
        ['/usr/bin/xcrun','clang','-Wall','-Wextra','-Werror','-c',str(RESOURCE/'wording.m'),'-o',str(root/'wording.o')],
        ['/usr/bin/xcrun','swiftc',str(root/'wording.o'),str(root/'coordinator.o'),'-F',str(frameworks),'-framework','ThingsModel','-framework','Base','-lsqlite3','-Xlinker','-rpath','-Xlinker',str(frameworks),'-o',str(root/'wording')],
    ]
    for n, command in enumerate(commands):
        try:
            r = subprocess.run(command, capture_output=True, env=environment(), close_fds=True, timeout=120)
        except (subprocess.SubprocessError, OSError) as exc:
            raise CopyError('native build unavailable or timed out') from exc
        durable(root/('build-'+str(n)+'.json'),{'argv':command,'exit':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')})
        if r.returncode:
            raise CopyError('native build failed; private build receipt retained')
    for p in root.iterdir():
        p.chmod(0o700 if p.name in ('wording','canary') else 0o600)
    dependencies = dependency_closure(root, app, app_pins)
    if sources() != source_pins or application(app) != app_pins or toolchain_receipt() != versions:
        raise CopyError('build input drift')
    manifest = {'version':2,'state':'ready','layout':1,'root':str(root),'app':str(app),'application':app_pins,'sources':source_pins,'artifacts':{n:artifact_identity(root/n) for n in sorted(ARTIFACTS)},'commands':commands,'dependencies':dependencies,'toolchain':versions,'os':platform.platform(),'python':{'executable':sys.executable,'version':sys.version,'sha256':sha(sys.executable)}}
    _schema(manifest, root)
    durable(root/'runtime.json',manifest,record_kind='native-runtime')
    verify(root)
    return root


def artifact_identity(path):
    path = Path(path)
    result = identity(path, private=False)
    expected_mode = 0o600 if path.name == 'scratch.dylib' else 0o700
    if stat.S_IMODE(path.stat().st_mode) != expected_mode:
        raise CopyError('runtime artifact private mode drift')
    return result


def verify(runtime):
    runtime = checked(runtime,directory=True)
    manifest = load(runtime/'runtime.json',record_kind='native-runtime')
    _schema(manifest, runtime)
    if manifest['root'] != str(runtime) or manifest['sources'] != sources():
        raise CopyError('runtime source/header/profile drift')
    if manifest['application'] != application(manifest['app']):
        raise CopyError('framework resource drift')
    if type(manifest.get('artifacts')) is not dict or set(manifest['artifacts']) != {'wording', 'scratch.dylib', 'canary'}:
        raise CopyError('runtime required artifacts invalid')
    for n,expected in manifest['artifacts'].items():
        if artifact_identity(runtime/n) != expected:
            raise CopyError('native runtime artifact drift')
    if manifest['python'] != {'executable':sys.executable,'version':sys.version,'sha256':sha(sys.executable)}:
        raise CopyError('Python runtime drift')
    if manifest['os'] != platform.platform():
        raise CopyError('OS runtime drift')
    actual_closure = dependency_closure(runtime, manifest['app'], manifest['application'])
    if digest(actual_closure) != digest(manifest['dependencies']):
        raise CopyError('recursive dependency closure drift')
    return manifest


def _work_boundary(runtime, work, app, plan):
    work = Path(work).resolve()
    protected = (Path(runtime).resolve(), Path(app).resolve(), RESOURCE.parent.resolve(), Path(plan).resolve())
    if any(work.is_relative_to(p) or p.is_relative_to(work) for p in protected):
        raise CopyError('native writable work overlaps protected inputs')


def run(runtime, work, plan):
    manifest = verify(runtime)
    stopped()
    runtime = checked(runtime,directory=True)
    work = checked(work,directory=True)
    plan = checked(plan)
    _work_boundary(runtime, work, manifest['app'], plan)
    schema = RESOURCE / 'schema_32400506.json'
    params = {'APP':manifest['app'],'RUNTIME':str(runtime),'WORK':str(work),'PLAN':str(plan),'SCHEMA':str(schema)}
    command = ['/usr/bin/sandbox-exec']
    for k,v in params.items(): command += ['-D',k+'='+v]
    command += ['-f',str(RESOURCE/'copy.sb'),'/usr/bin/env','DYLD_INSERT_LIBRARIES='+str(runtime/'scratch.dylib'),str(runtime/'wording'),str(work/'candidate.sqlite'),str(plan),str(schema)]
    durable(work/'invocation.json',{'argv':command,'environment':environment(work),'runtime_digest':digest(manifest),'native_start_count':1})
    try:
        result = subprocess.run(command,env=environment(work),capture_output=True,timeout=30,close_fds=True)
    except subprocess.TimeoutExpired as exc:
        durable(work/'native-timeout.json',{'timeout':True})
        raise CopyError('native helper timeout; candidate quarantined') from exc
    durable(work/'native-result.json',{'exit':result.returncode,'stdout':result.stdout.decode(errors='replace'),'stderr':result.stderr.decode(errors='replace')})
    stopped()
    verify(runtime)
    if result.returncode:
        raise CopyError('native helper refused; private evidence retained')
    import json
    try:
        return json.loads(result.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CopyError('invalid native proof') from exc


def probe(runtime, destination):
    """Exercise the real profile on harmless local canaries (no DB)."""
    import json
    manifest=verify(runtime); stopped()
    root=new_root(destination); work=new_root(root/'work')
    durable(root/'sentinel.json',{'synthetic':'must not be read or written'})
    sentinel=identity(root/'sentinel.json')
    durable(root/'plan.json',{'synthetic_probe':True})
    _work_boundary(runtime, work, manifest['app'], root/'plan.json')
    params={'APP':manifest['app'],'RUNTIME':str(runtime),'WORK':str(work),'PLAN':str(root/'plan.json'),'SCHEMA':str(RESOURCE/'schema_32400506.json')}
    command=['/usr/bin/sandbox-exec']
    for k,v in params.items(): command+=['-D',k+'='+v]
    command+=['-f',str(RESOURCE/'copy.sb'),'/usr/bin/env','DYLD_INSERT_LIBRARIES='+str(Path(runtime)/'scratch.dylib'),str(Path(runtime)/'canary'),str(root/'sentinel.json'),str(work/'allowed')]
    r=subprocess.run(command,env=environment(work),capture_output=True,timeout=15,close_fds=True)
    durable(root/'probe.json',{'argv':command,'environment':environment(work),'exit':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace'),'runtime_digest':digest(manifest)})
    if r.returncode or identity(root/'sentinel.json')!=sentinel:
        raise CopyError('sandbox canary denial failed')
    verify(runtime); stopped()
    return json.loads(r.stdout)
