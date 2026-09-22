"""Observed publisher engine identity; independent fixed inventory, Darwin only."""
from contextlib import closing
import ctypes
import _sqlite3
import sqlite3
import sys
import platform
import struct
from pathlib import Path
from .copies import CopyError
from . import native_runtime


def runtime_binding():
    if sys.platform != 'darwin' or sqlite3.sqlite_version not in ('3.53.4', '3.54.0'):
        raise CopyError('publisher engine combination not exercised')
    extension = Path(_sqlite3.__file__).resolve(strict=True)
    library = ctypes.CDLL(str(extension))
    system = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    class DlInfo(ctypes.Structure):
        _fields_ = [('filename', ctypes.c_char_p), ('base', ctypes.c_void_p),
                    ('symbol', ctypes.c_char_p), ('address', ctypes.c_void_p)]
    system.dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(DlInfo)]
    system.dladdr.restype = ctypes.c_int
    info = DlInfo()
    if not system.dladdr(ctypes.cast(library.sqlite3_libversion, ctypes.c_void_p), ctypes.byref(info)) or not info.filename:
        raise CopyError('actual loaded SQLite image unavailable')
    image = Path(info.filename.decode()).resolve()
    if image.is_file():
        image_binding = native_runtime._image_identity(image)
    elif native_runtime._os_path(image) and native_runtime._os_available(image):
        # A shared-cache image has no standalone file to hash. Bind its actual
        # loaded LC_UUID and OS trust root explicitly; never invent a file hash.
        header = ctypes.string_at(info.base, 32)
        magic, _, _, _, count, size, _, _ = struct.unpack('<8I', header)
        if magic != 0xfeedfacf or size > 1048576 or count > 65536:
            raise CopyError('loaded SQLite Mach-O header refused')
        commands = ctypes.string_at(info.base+32, size)
        offset = 0; uuids = []
        for _ in range(count):
            command, length = struct.unpack_from('<II', commands, offset)
            if length < 8 or offset+length > size: raise CopyError('loaded SQLite command refused')
            if command == 0x1b and length == 24: uuids.append(commands[offset+8:offset+24].hex())
            offset += length
        if offset != size or len(uuids) != 1: raise CopyError('loaded SQLite UUID unavailable')
        image_binding = {'path': str(image), 'shared_cache_uuid': uuids[0], 'trust': 'signed-OS-shared-cache', 'os': platform.version()}
    else:
        raise CopyError('actual SQLite identity unavailable')
    dependencies = {}
    def visit(path):
        if str(path) in dependencies: return
        if len(dependencies) >= 32: raise CopyError('engine dependency depth')
        record = native_runtime._image_identity(path)
        slices = native_runtime.inspect_macho(path)
        dependencies[str(path)] = {'identity': record, 'slices': slices}
        for data in slices.values():
            for dep in data['dependencies']:
                name = dep['name']
                if name.startswith('@loader_path/'):
                    child = (path.parent/name[len('@loader_path/'):]).resolve()
                elif name.startswith('/'):
                    child = Path(name).resolve()
                else:
                    raise CopyError('unresolved publisher engine dependency')
                if native_runtime._os_path(child):
                    if not native_runtime._os_available(child): raise CopyError('missing engine OS dependency')
                else:
                    visit(child)
    visit(extension)
    if image.is_file(): visit(image)
    with closing(sqlite3.connect(':memory:', isolation_level=None)) as db:
        source_id = db.execute('SELECT sqlite_source_id()').fetchone()[0]
        options = sorted(row[0] for row in db.execute('PRAGMA compile_options'))
    return {'python': native_runtime._image_identity(Path(sys.executable).resolve(strict=True)),
            'extension': native_runtime._image_identity(extension), 'sqlite': image_binding,
            'dependencies': dependencies, 'version': sqlite3.sqlite_version, 'source_id': source_id,
            'compile_options': options, 'os': platform.platform()}
