"""Private detached snapshots only. No live discovery or publication API."""
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import re
import stat
import sys
import ctypes
import errno
from functools import lru_cache, wraps
from contextvars import ContextVar
import threading
import time


_supplier_chain: ContextVar[tuple] = ContextVar('supplier_chain', default=())
_work_budget: ContextVar[dict | None] = ContextVar('work_budget', default=None)
MAX_SNAPSHOT_ROWS = 500000
MAX_FILE_BYTES = 268435456
MAX_RECORD_BYTES = 4194304
MAX_NATIVE_RUNTIME_RECORD_BYTES = 16777216
MAX_WORK_BYTES = 8589934592
MAX_SNAPSHOT_BYTES = 268435456
MAX_WORK_ROWS = 8000000
MAX_PATH_ENTRIES = 4096
MAX_DEPENDENCY_DEPTH = 64


def bounded_paths(root):
    paths = []
    for path in root.rglob('*'):
        check_budget()
        if len(paths) >= MAX_PATH_ENTRIES: raise CopyError('runtime path budget exceeded')
        paths.append(path)
    return sorted(paths)


@contextmanager
def work_scope():
    """Nested provenance shares the outer deadline, never refreshes it."""
    current = _work_budget.get()
    token = None
    if current is None:
        token = _work_budget.set({'deadline': time.monotonic() + 120, 'bytes': 0, 'rows': 0})
    try:
        check_budget()
        yield
        check_budget()
    finally:
        if token is not None: _work_budget.reset(token)


def bounded_work(function):
    @wraps(function)
    def bounded(*args, **kwargs):
        with work_scope(): return function(*args, **kwargs)
    return bounded


def check_budget(*, byte_count=0, row_count=0):
    budget = _work_budget.get()
    if budget is not None:
        budget['bytes'] += byte_count
        budget['rows'] += row_count
        if time.monotonic() > budget['deadline'] or budget['bytes'] > MAX_WORK_BYTES or budget['rows'] > MAX_WORK_ROWS:
            raise CopyError('cumulative work budget exceeded')


def work_deadline():
    check_budget()
    budget = _work_budget.get()
    if budget is None: raise CopyError('missing work budget')
    return budget['deadline']


@contextmanager
def sql_budget(db):
    """Own the progress-handler slot, but never the caller transaction."""
    with work_scope():
        deadline = work_deadline()
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            yield
            check_budget()
        except sqlite3.Error:
            check_budget()  # Preserve genuine extended errors unless expired.
            raise
        finally:
            db.set_progress_handler(None, 0)
_active_sqlite = {}
_file_lifetimes = threading.RLock()


@contextmanager
def raw_read_scope(path):
    """Serialize check/open/close against SQL lifetime registration process-wide.

    The caller must close every raw handle before leaving this scope. This
    coordinates tool-owned I/O only, not arbitrary external Python code.
    """
    if not _file_lifetimes.acquire(timeout=5): raise CopyError('file lifetime coordination busy')
    try:
        assert_not_sqlite_alias(path)
        if Path(path).stat().st_size > MAX_FILE_BYTES: raise CopyError('file byte budget exceeded')
        yield
    finally:
        _file_lifetimes.release()


@contextmanager
def sqlite_handle_scope(path):
    """Reject raw payload reads of main/SHM aliases until ALL SQL handles close."""
    path = Path(path)
    if not _file_lifetimes.acquire(timeout=5): raise CopyError('file lifetime coordination busy')
    token = object()
    try:
        s = path.stat()
        _active_sqlite[token] = (str(path), s.st_dev, s.st_ino)
    finally:
        _file_lifetimes.release()
    try:
        yield
    finally:
        with _file_lifetimes:
            del _active_sqlite[token]


def assert_not_sqlite_alias(path):
    if not _active_sqlite: return
    path = Path(path)
    s = path.stat()
    for name, device, inode in tuple(_active_sqlite.values()):
        if (s.st_dev, s.st_ino) == (device, inode):
            raise CopyError('raw read of active SQLite file refused')
        for suffix in ('-shm', '-wal', '-journal'):
            side = Path(name+suffix)
            if side.exists():
                side_s = side.stat()
                if (s.st_dev, s.st_ino) == (side_s.st_dev, side_s.st_ino):
                    raise CopyError('raw read of active SQLite sidecar refused')


def bounded_supplier(function):
    @wraps(function)
    def verify(root, *args, **kwargs):
        path = checked(root, directory=True)
        s = path.stat()
        key = (s.st_dev, s.st_ino)
        chain = _supplier_chain.get()
        if key in chain or len(chain) >= 16:
            raise CopyError('supplier lineage cycle or depth bound')
        token = _supplier_chain.set((*chain, key))
        try:
            return function(path, *args, **kwargs)
        finally:
            _supplier_chain.reset(token)
    return verify


def exact_keys(value, keys, label='record'):
    if type(value) is not dict or set(value) != set(keys):
        raise CopyError(label + ' schema')


def absolute_text(value):
    if type(value) is not str or not value or '\x00' in value or not Path(value).is_absolute() or os.path.abspath(value) != value:
        raise CopyError('absolute path schema')


def hash_text(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise CopyError('digest schema')


def root_identity(value):
    if type(value) is not list or len(value) != 2 or any(type(x) is not int or x < 0 for x in value):
        raise CopyError('root identity schema')


def identity_schema(value):
    exact_keys(value, {'path', 'device', 'inode', 'size', 'sha256'}, 'identity')
    absolute_text(value['path'])
    for key in ('device', 'inode', 'size'):
        if type(value[key]) is not int or value[key] < 0:
            raise CopyError('identity number schema')
    hash_text(value['sha256'])


def import_schema(record):
    exact_keys(record, {'version', 'state', 'root', 'root_identity', 'supplier_declaration', 'cloud_safety_verified', 'source', 'copy'}, 'import')
    if type(record['version']) is not int or record['version'] != 1 or record['state'] != 'imported' or record['supplier_declaration'] != 'detached-stable-resolved' or record['cloud_safety_verified'] is not False:
        raise CopyError('import state schema')
    absolute_text(record['root'])
    root_identity(record['root_identity'])
    identity_schema(record['source'])
    identity_schema(record['copy'])


class CopyError(ValueError):
    """A sanitized fail-closed copy boundary refusal."""


def forbidden_roots():
    """Directory metadata only; never discover or open a live database."""
    home = Path.home()
    return [home / 'Library' / name for name in ('Containers', 'Group Containers', 'Keychains')] + [Path('/Library/Keychains'), home / 'things-offline-lab']


@lru_cache(maxsize=1)
def _acl_library():
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    lib.acl_get_link_np.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.acl_get_link_np.restype = ctypes.c_void_p
    lib.acl_valid.argtypes = [ctypes.c_void_p]
    lib.acl_valid.restype = ctypes.c_int
    lib.acl_get_entry.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    lib.acl_get_entry.restype = ctypes.c_int
    lib.acl_get_tag_type.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    lib.acl_get_tag_type.restype = ctypes.c_int
    lib.acl_free.argtypes = [ctypes.c_void_p]
    lib.acl_free.restype = ctypes.c_int
    return lib


def _acl_security(s):
    if stat.S_ISLNK(s.st_mode) or s.st_uid not in (0, os.getuid()):
        raise CopyError('unsafe path component')
    if s.st_mode & 0o022 and not (stat.S_ISDIR(s.st_mode) and s.st_mode & stat.S_ISVTX):
        raise CopyError('writable path component')
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_flags)


def inspect_acl(path, *, expected=None):
    """Refuse granting/inherited ACLs without rewriting any source ACL.

    Only unstable ACL-absence observations get at most three whole inspections.
    Pin identity and security metadata across attempts, including checked's stat;
    a fresh stable ctime alone must never accept an intervening security change.
    Deny-only ancestor ACLs grant no access. Inspection errors fail closed.
    """
    if sys.platform != 'darwin':
        raise CopyError('ACL inspection unsupported')
    try:
        lib = _acl_library()
    except (OSError, AttributeError) as exc:
        raise CopyError('ACL inspection unavailable') from exc
    baseline = _acl_security(expected) if expected is not None else None
    for attempt in range(3):
        check_budget()  # Reuse, never refresh, the caller's work deadline.
        before = Path(path).lstat()
        security = _acl_security(before)
        if baseline is None:
            baseline = security
        if security != baseline:
            raise CopyError('ACL path identity or permissions changed')
        ctypes.set_errno(0)
        acl = lib.acl_get_link_np(os.fsencode(path), 0x100)
        error = ctypes.get_errno()  # Retain errno before any further calls.
        if not acl:
            # Darwin ENOENT means no extended ACL only on a verified object.
            if error != errno.ENOENT:
                raise CopyError('ACL inspection failed')
            after = Path(path).lstat()
            if _acl_security(after) != baseline:
                raise CopyError('ACL path identity or permissions changed')
            check_budget()
            if before.st_ctime_ns == after.st_ctime_ns:
                return
            continue  # Reinspect ACL AND metadata; never retry a mutation.
        try:
            if lib.acl_valid(acl) != 0:
                raise CopyError('invalid ACL')
            index = 0
            while True:
                entry = ctypes.c_void_p()
                ctypes.set_errno(0)
                if lib.acl_get_entry(acl, index, ctypes.byref(entry)) != 0:
                    if ctypes.get_errno() == errno.EINVAL:
                        break  # Darwin end-of-valid-ACL is EINVAL, not POSIX 0.
                    raise CopyError('ACL entry inspection failed')
                tag = ctypes.c_int()
                if lib.acl_get_tag_type(entry, ctypes.byref(tag)) != 0 or tag.value != 2:
                    raise CopyError('granting or unknown ACL refused')
                index = -1  # ACL_NEXT_ENTRY
            after = Path(path).lstat()
            if _acl_security(after) != baseline or before.st_ctime_ns != after.st_ctime_ns:
                raise CopyError('ACL observation changed')
            check_budget()
            return
        finally:
            lib.acl_free(acl)
    raise CopyError('ACL inspection unstable')


def checked(path, *, directory=False, private=True):
    check_budget()
    path = Path(os.path.abspath(path))
    if any(p.casefold() in ('containers', 'group containers', 'keychains', 'things-offline-lab') for p in path.parts):
        raise CopyError('forbidden source location')
    forbidden = set()
    for root in forbidden_roots():
        try:
            s = root.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CopyError('forbidden root identity unavailable') from exc
        forbidden.add((s.st_dev, s.st_ino))
    for part in reversed((path, *path.parents)):
        try:
            s = part.lstat()
        except OSError as exc:
            raise CopyError('path unavailable') from exc
        if (s.st_dev, s.st_ino) in forbidden:
            raise CopyError('forbidden physical ancestor')
        inspect_acl(part, expected=s)
    s = path.stat()
    if directory:
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
            raise CopyError('directory must be owned and private')
    elif not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid():
        raise CopyError('file must be owned regular and unlinked')
    elif private and stat.S_IMODE(s.st_mode) != 0o600:
        raise CopyError('data file must have private mode 0600')
    return path


def _file_stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


@contextmanager
def parent_handle(path):
    """Pin each physical ancestor; relative opens cannot follow parent symlinks.

    SQLite still reopens a pathname: repeated checks detect ordinary drift, not
    arbitrary hostile same-UID races. No same-UID isolation is promised.
    """
    parent = Path(os.path.abspath(path)).parent
    handles = []
    try:
        for part in reversed((parent, *parent.parents)):
            fd = os.open(part.name if handles else str(part), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=handles[-1][1] if handles else None)
            handles.append((part, fd))
            a, b = os.fstat(fd), part.lstat()
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino) or not stat.S_ISDIR(b.st_mode):
                raise CopyError('ancestor identity changed')
        yield handles[-1][1]
        for part, fd in handles:
            a, b = os.fstat(fd), part.lstat()
            if (a.st_dev, a.st_ino, a.st_mode, a.st_uid) != (b.st_dev, b.st_ino, b.st_mode, b.st_uid):
                raise CopyError('ancestor identity changed')
    finally:
        for _, fd in reversed(handles):
            os.close(fd)


def _read_file(path, *, private=True, collect=False, prefix=None):
    path = checked(path, private=private)
    with raw_read_scope(path):
        return _read_file_guarded(path, private=private, collect=collect, prefix=prefix)


def _read_file_guarded(path, *, private=True, collect=False, prefix=None):
    path = checked(path, private=private)
    assert_not_sqlite_alias(path)
    initial = path.lstat()
    with parent_handle(path) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            s = os.fstat(fd)
            if _file_stamp(initial) != _file_stamp(s) or not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                raise CopyError('file changed before read')
            h, chunks = hashlib.sha256(), []
            remaining = s.st_size if prefix is None else prefix
            while remaining and (block := os.read(fd, min(remaining, 1024 * 1024))):
                check_budget(byte_count=len(block))
                remaining -= len(block)
                h.update(block)
                if collect: chunks.append(block)
            checked(path, private=private)
            if _file_stamp(s) != _file_stamp(os.fstat(fd)) or _file_stamp(s) != _file_stamp(path.lstat()):
                raise CopyError('file changed during read')
            result = {'path': str(path), 'device': s.st_dev, 'inode': s.st_ino, 'size': s.st_size, 'sha256': h.hexdigest()}
        finally:
            os.close(fd)
    return result, b''.join(chunks)


def identity(path, *, private=True):
    return _read_file(path, private=private)[0]


def read_bytes(path):
    return _read_file(path, collect=True)[1]


def read_header(path):
    return _read_file(path, collect=True, prefix=100)[1]


def detached(path):
    path = checked(path)
    for suffix in ('-wal', '-shm', '-journal'):
        side = Path(str(path) + suffix)
        if os.path.lexists(side):
            checked(side)
            if suffix != '-shm' and side.stat().st_size:
                raise CopyError('source must be detached without active sidecars')
    return path


def canonical(value):
    check_budget()
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _record_limit(record_kind):
    if record_kind is None: return MAX_RECORD_BYTES
    if type(record_kind) is str and record_kind == 'native-runtime':
        return MAX_NATIVE_RUNTIME_RECORD_BYTES
    raise CopyError('unknown record kind')


def _record_schema(path, value, record_kind):
    if record_kind == 'native-runtime':
        from .native_runtime import _schema
        _schema(value, Path(os.path.abspath(path)).parent)


def durable(path, value, *, record_kind=None):
    """Exclusive, private, FD-bound durable record; never overwrite approvals."""
    path = Path(os.path.abspath(path))
    checked(path.parent, directory=True)
    payload = canonical(value)
    if len(payload) > _record_limit(record_kind): raise CopyError('record byte budget exceeded')
    _record_schema(path, value, record_kind)
    check_budget(byte_count=len(payload))
    with parent_handle(path) as parent:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            checked(path)
            original = os.fstat(fd)
            with os.fdopen(fd, 'wb', closefd=False) as output:
                output.write(payload)
                output.flush()
                os.fsync(fd)
            checked(path)
            if _file_stamp(os.fstat(fd)) != _file_stamp(path.lstat()) or (original.st_dev, original.st_ino) != (path.lstat().st_dev, path.lstat().st_ino):
                raise CopyError('record identity changed')
            os.fsync(parent)
        finally:
            os.close(fd)


def load(path, *, record_kind=None):
    checked(path)
    limit = _record_limit(record_kind)
    if Path(path).stat().st_size > limit: raise CopyError('record byte budget exceeded')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise CopyError('duplicate JSON key')
            result[k] = v
        return result
    try:
        payload = read_bytes(path)
        if len(payload) > limit: raise CopyError('record byte budget exceeded')
        # Count structural depth outside strings BEFORE recursive JSON parsing.
        depth = 0; quoted = False; escaped = False
        for byte in payload:
            if quoted:
                if escaped: escaped = False
                elif byte == 92: escaped = True
                elif byte == 34: quoted = False
            elif byte == 34: quoted = True
            elif byte in (91, 123):
                depth += 1
                if depth > 64: raise CopyError('JSON depth budget exceeded')
            elif byte in (93, 125): depth -= 1
        value = json.loads(payload, object_pairs_hook=unique)
        canonical(value)  # Reject NaN/Infinity, including exponent overflow.
        _record_schema(path, value, record_kind)
        return value
    except CopyError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CopyError('invalid JSON') from exc


def new_root(path):
    path = Path(os.path.abspath(path))
    checked(path.parent, directory=True)
    try:
        path.mkdir(mode=0o700)
    except OSError as exc:
        raise CopyError('destination must be new') from exc
    return checked(path, directory=True)


def no_sidecars(path):
    if any(os.path.lexists(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise CopyError('destination sidecar exists')


@bounded_work
def backup(source, destination):
    """Read a detached source; exclusively create a new private output only."""
    source = detached(source)
    destination = Path(os.path.abspath(destination))
    checked(destination.parent, directory=True)
    before = identity(source)
    if shutil.disk_usage(destination.parent).free < max(100 * 1024 * 1024, before['size'] * 5):
        raise CopyError('insufficient copy space')
    no_sidecars(destination)
    with parent_handle(source), parent_handle(destination) as parent:
        no_sidecars(destination)
        fd = os.open(destination.name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            checked(destination)
            owned = os.fstat(fd)
            no_sidecars(destination)
            # Both identities are checked immediately before SQLite pathname IO.
            if identity(source) != before:
                raise CopyError('source drift before backup')
            with sqlite_handle_scope(source), closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=2)) as src:
                src.execute('PRAGMA query_only=ON')
                no_sidecars(destination)
                checked(destination)
                if (owned.st_dev, owned.st_ino) != (destination.lstat().st_dev, destination.lstat().st_ino):
                    raise CopyError('backup destination identity changed before connect')
                with sqlite_handle_scope(destination), closing(sqlite3.connect(destination.as_uri() + '?mode=rw', uri=True, timeout=2)) as dst:
                    # The new, exclusively owned output has no other readers.
                    # Exclusive SQLite locking avoids creating a persistent SHM
                    # carrier when backup inherits the source's WAL header.
                    if dst.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone() != ('exclusive',):
                        raise CopyError('backup destination locking refused')
                    page_size = src.execute('PRAGMA page_size').fetchone()[0]
                    def progress(status, remaining, total):
                        check_budget()
                        if total * page_size > MAX_FILE_BYTES: raise CopyError('backup byte budget exceeded')
                    src.backup(dst, pages=256, progress=progress, sleep=.01)
                    # Backup inherits WAL mode. Finalize only this exclusively
                    # created destination through SQLite, never unlink sidecars
                    # or checkpoint the read-only supplier/source database.
                    if dst.execute('PRAGMA journal_mode=DELETE').fetchone() != ('delete',):
                        raise CopyError('backup destination could not detach')
                    with sql_budget(dst):
                        if dst.execute('PRAGMA integrity_check').fetchmany(2) != [('ok',)]:
                            raise CopyError('backup integrity refused')
            no_sidecars(destination)
            checked(destination)
            end = destination.lstat()
            if (owned.st_dev, owned.st_ino) != (end.st_dev, end.st_ino) or _file_stamp(os.fstat(fd)) != _file_stamp(end):
                raise CopyError('backup destination identity changed')
            detached(source)
            if identity(source) != before:
                raise CopyError('source drift during backup')
            os.fsync(fd)
            os.fsync(parent)
        finally:
            os.close(fd)
    return destination


def supplier_state(source):
    """Known owned interruptions override the external supplier declaration."""
    source = detached(source)
    if any(os.path.lexists(parent / 'target.json') for parent in source.parents):
        raise CopyError('mutable publication target is never an importable supplier')
    if any(os.path.lexists(parent / 'failed.json') for parent in source.parents):
        raise CopyError('quarantined source ancestry')
    for parent in source.parents:
        if any(os.path.lexists(parent / name) for name in ('importing.json', 'preparing.json')) or (os.path.lexists(parent / 'applying.json') and not os.path.lexists(parent / 'complete.json')):
            raise CopyError('interrupted supplier source')
        if any(os.path.lexists(parent / name) for name in ('packet.json', 'applying.json', 'complete.json')):
            if source != parent / 'output.sqlite':
                raise CopyError('supplier is not an accepted output')
            # Deferred import avoids a module initialization cycle. This is the
            # same full packet validator, not permission from a copied receipt.
            from .wording import verify_completed
            verify_completed(parent)
        elif os.path.lexists(parent / 'copy.json'):
            if source != parent / 'source.sqlite':
                raise CopyError('supplier is not the owned imported source')
            verify_copy(parent)
        elif os.path.lexists(parent / 'started.json'):
            raise CopyError('incomplete supplier lifecycle')


def import_copy(source, workspace, *, declaration):
    if declaration != 'detached-stable-resolved':
        raise CopyError('supplier declaration required; not autonomous cloud verification')
    source = detached(source)
    supplier_state(source)
    if source.stat().st_mode & 0o077:
        raise CopyError('input must be private')
    before = identity(source)
    root = new_root(workspace)
    durable(root / 'importing.json', {'state': 'importing'})
    durable(root / 'started.json', {'operation': 'import', 'source': before})
    try:
        copied = backup(source, root / 'source.sqlite')
        record = {'version': 1, 'state': 'imported', 'root': str(root), 'root_identity': [root.stat().st_dev, root.stat().st_ino], 'supplier_declaration': declaration, 'cloud_safety_verified': False, 'source': before, 'copy': identity(copied)}
        durable(root / 'copy.json', record)
        supplier_state(source)
        if identity(source) != before:
            raise CopyError('supplier drift during import')
        # Remove the interruption guard only after all data/records are durable.
        # No fallible step follows unlink. Power loss can resurrect the guard,
        # causing conservative refusal, never acceptance of unflushed records.
        (root / 'importing.json').unlink()
        return copied
    except BaseException:
        durable(root / 'failed.json', {'state': 'quarantined'})
        raise


@bounded_supplier
def verify_copy(root):
    root = checked(root, directory=True)
    if os.path.lexists(root / 'importing.json'):
        raise CopyError('interrupted importing copy')
    record = load(root / 'copy.json')
    import_schema(record)
    started = load(root / 'started.json')
    exact_keys(started, {'operation', 'source'}, 'import start')
    if started['operation'] != 'import' or canonical(started['source']) != canonical(record['source']):
        raise CopyError('import start drift')
    if os.path.lexists(root / 'failed.json') or record['root'] != str(root) or record['root_identity'] != [root.stat().st_dev, root.stat().st_ino]:
        raise CopyError('copy ownership drift')
    supplier_state(record['source']['path'])
    if record['copy'] != identity(detached(root / 'source.sqlite')) or record['source'] != identity(detached(record['source']['path'])):
        raise CopyError('source or copy drift')
    return record


@contextmanager
def lock(root):
    root = checked(root, directory=True)
    fd = os.open(root / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        checked(root / 'lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CopyError('workspace busy') from exc
        yield
    finally:
        os.close(fd)
