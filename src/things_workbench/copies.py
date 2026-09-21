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


_supplier_chain: ContextVar[tuple] = ContextVar('supplier_chain', default=())


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


def inspect_acl(path):
    """Refuse granting/inherited ACLs without rewriting any source ACL.

    Deny-only ancestor ACLs grant no access. Inspection errors fail closed.
    """
    if sys.platform != 'darwin':
        raise CopyError('ACL inspection unsupported')
    try:
        lib = _acl_library()
    except (OSError, AttributeError) as exc:
        raise CopyError('ACL inspection unavailable') from exc
    before = Path(path).lstat()
    ctypes.set_errno(0)
    acl = lib.acl_get_link_np(os.fsencode(path), 0x100)
    if not acl:
        # Darwin returns ENOENT for an existing object with no extended ACL.
        # Recheck the object so a missing/replaced pathname is never that case.
        after = Path(path).lstat()
        if ctypes.get_errno() == errno.ENOENT and (before.st_dev, before.st_ino, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_ctime_ns):
            return
        raise CopyError('ACL inspection failed')
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
    finally:
        lib.acl_free(acl)


def checked(path, *, directory=False, private=True):
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
        if stat.S_ISLNK(s.st_mode) or s.st_uid not in (0, os.getuid()):
            raise CopyError('unsafe path component')
        if s.st_mode & 0o022 and not (stat.S_ISDIR(s.st_mode) and s.st_mode & stat.S_ISVTX):
            raise CopyError('writable path component')
        inspect_acl(part)
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


def _read_file(path, *, private=True, collect=False):
    path = checked(path, private=private)
    initial = path.lstat()
    with parent_handle(path) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            s = os.fstat(fd)
            if _file_stamp(initial) != _file_stamp(s) or not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                raise CopyError('file changed before read')
            h, chunks = hashlib.sha256(), []
            while block := os.read(fd, 1024 * 1024):
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
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def durable(path, value):
    """Exclusive, private, FD-bound durable record; never overwrite approvals."""
    path = Path(os.path.abspath(path))
    checked(path.parent, directory=True)
    payload = canonical(value)
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


def load(path):
    checked(path)
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise CopyError('duplicate JSON key')
            result[k] = v
        return result
    try:
        value = json.loads(read_bytes(path), object_pairs_hook=unique)
        canonical(value)  # Reject NaN/Infinity, including exponent overflow.
        return value
    except CopyError:
        raise
    except (UnicodeError, ValueError) as exc:
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
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=2)) as src:
                src.execute('PRAGMA query_only=ON')
                no_sidecars(destination)
                checked(destination)
                if (owned.st_dev, owned.st_ino) != (destination.lstat().st_dev, destination.lstat().st_ino):
                    raise CopyError('backup destination identity changed before connect')
                with closing(sqlite3.connect(destination.as_uri() + '?mode=rw', uri=True, timeout=2)) as dst:
                    # The new, exclusively owned output has no other readers.
                    # Exclusive SQLite locking avoids creating a persistent SHM
                    # carrier when backup inherits the source's WAL header.
                    if dst.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone() != ('exclusive',):
                        raise CopyError('backup destination locking refused')
                    src.backup(dst, pages=256)
                    # Backup inherits WAL mode. Finalize only this exclusively
                    # created destination through SQLite, never unlink sidecars
                    # or checkpoint the read-only supplier/source database.
                    if dst.execute('PRAGMA journal_mode=DELETE').fetchone() != ('delete',):
                        raise CopyError('backup destination could not detach')
                    if dst.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
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
