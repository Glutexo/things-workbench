"""Private managed-target transactional rehearsal; never a live adapter."""
from contextlib import closing, contextmanager
import os
from pathlib import Path
import re
import sqlite3
from . import copies, wording, native_runtime
from .copies import CopyError, checked, digest, durable, load, exact_keys
from .fingerprint import snapshot, snapshot_connection, quote
from .schema_policy import verify_schema_connection
from .publication_runtime import runtime_binding
import fcntl
import shutil
import sys
import time

MAX_EVENTS = 128
MAX_RUNS = 256
MAX_PLAN_BYTES = 1048576


def _entries(path, limit):
    result = []
    for item in path.iterdir():
        copies.check_budget()
        if len(result) >= limit: raise CopyError('directory entry budget exceeded')
        result.append(item)
    return sorted(result)

POLICY = {'version': 1, 'class': 'owned-private-rehearsal', 'journal': 'delete',
          'live_enabled': False, 'cloud_performed': False, 'exports': False,
          'synchronous': 3, 'fullfsync': 1, 'minimum_free_bytes': 4294967296,
          'max_database_bytes': 268435456, 'max_seconds': 120, 'busy_timeout_ms': 1000}


def physical(path, *, directory=False):
    """Metadata only: MUST NOT raw-open/close a SQLite main/SHM file."""
    path = checked(path, directory=directory)
    s = path.stat()
    return {'path': str(path), 'device': s.st_dev, 'inode': s.st_ino,
            'owner': s.st_uid, 'mode': s.st_mode, 'nlink': None if directory else s.st_nlink,
            'parents': [[str(p), p.stat().st_dev, p.stat().st_ino] for p in path.parents]}


def _same(actual, expected):
    """Recursive exact types and fields; bool/int equality is not authority."""
    if type(actual) is not type(expected): return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(_same(actual[k], v) for k, v in expected.items())
    if type(expected) in (list, tuple):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _source_schema(source):
    exact_keys(source, {'packet', 'manifest', 'complete', 'runtime'}, 'publication source')
    copies.absolute_text(source['packet'])
    copies.hash_text(source['manifest']); copies.hash_text(source['runtime'])
    copies.identity_schema(source['complete'])


def _engine_schema(engine):
    exact_keys(engine, {'python', 'extension', 'sqlite', 'dependencies', 'version', 'source_id', 'compile_options', 'os'}, 'publisher engine')
    for key in ('python', 'extension'): copies.identity_schema(engine[key])
    image = engine['sqlite']
    if type(image) is dict and 'shared_cache_uuid' in image:
        exact_keys(image, {'path', 'shared_cache_uuid', 'trust', 'os'}, 'shared cache')
        copies.absolute_text(image['path'])
        if (type(image['shared_cache_uuid']) is not str or not re.fullmatch('[0-9a-f]{32}', image['shared_cache_uuid'])
                or image['trust'] != 'signed-OS-shared-cache' or type(image['os']) is not str):
            raise CopyError('shared cache types')
    else: copies.identity_schema(image)
    for key in ('version', 'source_id', 'os'):
        if type(engine[key]) is not str or not engine[key]: raise CopyError('engine text type')
    if type(engine['compile_options']) is not list or any(type(v) is not str for v in engine['compile_options']):
        raise CopyError('engine options type')
    deps = engine['dependencies']
    if type(deps) is not dict or not 1 <= len(deps) <= 32: raise CopyError('engine dependencies type')
    for path, record in deps.items():
        copies.absolute_text(path)
        exact_keys(record, {'identity', 'slices'}, 'engine dependency')
        copies.identity_schema(record['identity'])
        if record['identity']['path'] != path: raise CopyError('engine dependency path')
        slices = record['slices']
        if type(slices) is not dict or not 1 <= len(slices) <= 32: raise CopyError('engine slices type')
        for arch, data in slices.items():
            if type(arch) is not str or not re.fullmatch('[0-9]+:[0-9]+', arch): raise CopyError('engine architecture type')
            exact_keys(data, {'dependencies', 'rpaths'}, 'engine slice')
            if type(data['rpaths']) is not list or any(type(v) is not str for v in data['rpaths']): raise CopyError('engine rpaths type')
            if type(data['dependencies']) is not list: raise CopyError('engine loads type')
            for dep in data['dependencies']:
                exact_keys(dep, {'command', 'name'}, 'engine load')
                if type(dep['command']) is not int or type(dep['name']) is not str: raise CopyError('engine load types')


def _completed(packet):
    packet = checked(packet, directory=True)
    if (packet/'plan.json').stat().st_size > MAX_PLAN_BYTES: raise CopyError('plan byte budget exceeded')
    manifest = wording.verify_completed(packet)
    before = snapshot(packet/'before.sqlite')
    after = snapshot(packet/'output.sqlite')
    if digest(before) != manifest['verdict']['before_fingerprint'] or digest(after) != manifest['verdict']['candidate_fingerprint']:
        raise CopyError('completed data drift')
    plan = wording.parse_plan(copies.canonical(load(packet/'plan.json')))
    if copies.identity(packet/'plan.json') != manifest['files']['plan.json']:
        raise CopyError('completed plan drift')
    table = before['tables']['TMTask']
    rows = [dict(zip(table['columns'], r)) for r in table['rows'] if r[table['columns'].index('uuid')] == ['text', plan['task']]]
    if len(rows) != 1: raise CopyError('completed task identity')
    text = {k: rows[0][k][1] for k in ('title', 'notes')}
    view = wording.preview_value(text, plan, manifest['verdict'])
    binding = {'packet': str(packet), 'manifest': digest(manifest),
               'complete': copies.identity(packet/'complete.json'), 'runtime': manifest['runtime_digest']}
    return binding, view, before, after


def _target(root):
    root = checked(root, directory=True)
    m = load(root/'target.json')
    exact_keys(m, {'version', 'policy', 'root', 'target', 'registry', 'bootstrap', 'lock'}, 'managed target')
    if type(m['version']) is not int or m['version'] != 1 or not _same(m['policy'], POLICY):
        raise CopyError('target policy mismatch')
    _source_schema(m['bootstrap'])
    if not _same(m['lock'], physical(root/'lock')): raise CopyError('target lock authority lost')
    if not _same(m['root'], physical(root, directory=True)) or not _same(m['target'], physical(root/'target.sqlite')) or not _same(m['registry'], physical(root/'registry', directory=True)):
        raise CopyError('managed target identity drift')
    if load(root/'preparing.json') != {'state': 'permanently-nonimportable-stage3-target'}:
        raise CopyError('target supplier guard lost')
    if not _same(load(root/'registry/enrollment.json'), {'version': 1, 'target': m['target'], 'root': m['root']}):
        raise CopyError('registry authority lost')
    return m


@contextmanager
def _locked(root):
    m = _target(root)  # Missing lock is lost authority, not O_CREAT.
    fd = os.open(root/'lock', os.O_RDWR|os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if (s.st_dev, s.st_ino) != (m['lock']['device'], m['lock']['inode']):
            raise CopyError('lock replaced')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CopyError('target busy') from exc
        _target(root)
        yield
    finally:
        os.close(fd)


def _delete_header(path):
    # Only called BEFORE opening any target SQL connection. No mode conversion.
    copies.no_sidecars(path)
    data = copies.read_header(path)
    if len(data) < 100 or data[:16] != b'SQLite format 3\x00' or data[18:20] != b'\x01\x01':
        raise CopyError('DELETE-only target; WAL or unknown format refused')


@copies.bounded_work
def create_target(completed_packet, destination):
    binding, _, before, _ = _completed(completed_packet)
    native_runtime.stopped()
    root = copies.new_root(destination)
    durable(root/'preparing.json', {'state': 'permanently-nonimportable-stage3-target'})
    registry = copies.new_root(root/'registry')
    copies.new_root(root/'runs')
    durable(root/'lock', {'version': 1, 'purpose': 'permanent-target-lock'})
    target = copies.backup(Path(binding['packet'])/'before.sqlite', root/'target.sqlite')
    _delete_header(target)
    if snapshot(target) != before: raise CopyError('bootstrap mismatch')
    m = {'version': 1, 'policy': POLICY, 'root': physical(root, directory=True),
         'target': physical(target), 'registry': physical(registry, directory=True), 'bootstrap': binding, 'lock': physical(root/'lock')}
    durable(registry/'enrollment.json', {'version': 1, 'target': m['target'], 'root': m['root']})
    durable(root/'target.json', m)
    return root


def _envelope(run):
    run = checked(run, directory=True)
    m = _receipt_envelope(run)
    if not _same(m['sources'], native_runtime.sources()) or not _same(m['engine'], runtime_binding()): raise CopyError('publisher source/engine drift')
    binding, view, before, after = _completed(m['source']['packet'])
    if not _same(binding, m['source']) or not _same(view, m['wording']) or digest(before) != m['before'] or digest(after) != m['after']:
        raise CopyError('publication source/preview drift')
    return m, before, after


@copies.bounded_work
def prepare(completed_packet, target_root, name):
    if type(name) is not str or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', name):
        raise CopyError('invalid run name')
    target_root = checked(target_root, directory=True)
    with _locked(target_root):
        target = _target(target_root)
        _guard(target_root)
        if len(_entries(target_root/'runs', MAX_RUNS)) >= MAX_RUNS: raise CopyError('run budget exceeded')
        binding, view, before, after = _completed(completed_packet)
        native_runtime.stopped()
        path = target_root/'target.sqlite'
        _delete_header(path)
        if snapshot(path) != before: raise CopyError('stale target BEFORE')
        root = copies.new_root(target_root/'runs'/name)
        m = {'version': 1, 'kind': 'private-transactional-rehearsal', 'run': physical(root, directory=True),
             'target': target, 'source': binding, 'before': digest(before), 'after': digest(after),
             'wording': view, 'policy': POLICY, 'sources': native_runtime.sources(), 'engine': runtime_binding()}
        durable(root/'publication.json', m)
        durable(root/'prepared.json', {'version': 1, 'publication': digest(m)})
        return root


@copies.bounded_work
def preview(run):
    m, _, _ = _envelope(run)
    return {'banner': 'PRIVATE TRANSACTIONAL REHEARSAL ONLY / NO CLOUD / LIVE DISABLED',
            'target': m['target']['target'], 'wording': m['wording'], 'before': m['before'],
            'after': m['after'], 'policy': m['policy'], 'approval_digest': digest(m)}


def publish_live(*args, **kwargs):
    raise CopyError('LIVE_PUBLICATION_SEALED_DISABLED')


def _phase(name, db=None):
    """Internal test observation seam; no public fault/SQL input."""


def _decode(v):
    kind, data = v
    if kind == 'null': return None
    if kind in ('integer', 'text'): return data
    if kind == 'real': return float.fromhex(data)
    if kind == 'blob': return bytes.fromhex(data)
    raise CopyError('typed transfer value refused')


def _transfer(before, after):
    if before['schema'] != after['schema'] or before['headers'] != after['headers'] or before['tables'].keys() != after['tables'].keys():
        raise CopyError('transfer schema/header drift')
    plan = []
    plan_bytes = 0
    for name, old in before['tables'].items():
        new = after['tables'][name]
        if old == new: continue
        if name not in ('TMTask', 'BSSyncronyMetadata') or old['without_rowid'] or {k:v for k,v in old.items() if k != 'rows'} != {k:v for k,v in new.items() if k != 'rows'}:
            raise CopyError('transfer unrelated table/layout')
        columns = old['columns']
        key_columns = {'rowid'} | {r[1] for r in old['layout'] if r[5]}
        left = {r[0][1]: r for r in old['rows']}
        right = {r[0][1]: r for r in new['rows']}
        if left.keys() - right.keys(): raise CopyError('transfer deletes refused')
        for rid, row in right.items():
            previous_length = len(plan)
            if rid not in left:
                if name != 'BSSyncronyMetadata': raise CopyError('task insertion refused')
                plan.append(('insert', name, columns, row, rid))
            elif row != left[rid]:
                changed = [i for i,(a,b) in enumerate(zip(left[rid], row)) if a != b]
                names = [columns[i] for i in changed]
                if key_columns.intersection(names): raise CopyError('transfer key rewrite')
                plan.append(('update', name, names, [row[i] for i in changed], rid))
            if len(plan) != previous_length:
                plan_bytes += len(copies.canonical(plan[-1]))
                if plan_bytes > MAX_PLAN_BYTES: raise CopyError('transfer plan byte budget exceeded')
    if not plan: raise CopyError('empty transfer')
    return plan


def _events(run):
    directory = checked(run/'events', directory=True)
    records = []
    for i, path in enumerate(_entries(directory, MAX_EVENTS)):
        if path.name != f'{i:04}.json': raise CopyError('event sequence gap')
        records.append(load(path))
    return _validate_events(records)


def _validate_events(records):
    result = []
    for i, event in enumerate(records):
        exact_keys(event, {'version', 'sequence', 'previous', 'approval', 'state', 'data'}, 'publication event')
        if type(event['version']) is not int or event['version'] != 1 or type(event['sequence']) is not int or event['sequence'] != i or event['previous'] != (digest(result[-1]) if result else None):
            raise CopyError('event chain mismatch')
        copies.hash_text(event['approval'])
        state, data = event['state'], event['data']
        if type(state) is not str: raise CopyError('event state type')
        prior = result[-1]['state'] if result else None
        transitions = {'reserved': {None}, 'backup_durable': {'reserved'}, 'writing': {'backup_durable'},
                       'commit_intent': {'writing'}, 'sqlite_commit_returned': {'commit_intent'},
                       'committed_verified': {'sqlite_commit_returned'}, 'resolved': {'committed_verified', 'reconciled'}}
        if state in transitions:
            if prior not in transitions[state]: raise CopyError('invalid event transition')
        elif state in ('uncertain', 'rolled_back_verified', 'reconciled'):
            if prior is None or prior == 'resolved': raise CopyError('invalid recovery transition')
        else:
            raise CopyError('unknown event state')
        if state in ('reserved', 'writing', 'sqlite_commit_returned'):
            if data is not None: raise CopyError('unexpected event data')
        elif state == 'backup_durable':
            copies.identity_schema(data)
        elif state == 'commit_intent':
            exact_keys(data, {'backup', 'before', 'after'}, 'commit intent')
            copies.identity_schema(data['backup']); copies.hash_text(data['before']); copies.hash_text(data['after'])
        elif state == 'committed_verified':
            exact_keys(data, {'state', 'before', 'after', 'backup', 'live_published', 'cloud_performed'}, 'terminal')
            if data['state'] != state or data['live_published'] is not False or data['cloud_performed'] is not False: raise CopyError('terminal state')
            copies.hash_text(data['before']); copies.hash_text(data['after']); copies.identity_schema(data['backup'])
        elif state in ('uncertain', 'rolled_back_verified'):
            exact_keys(data, {'sqlite_errorcode', 'commit_invoked'}, 'failure')
            if type(data['commit_invoked']) is not bool or (data['sqlite_errorcode'] is not None and type(data['sqlite_errorcode']) is not int): raise CopyError('failure types')
            if state == 'rolled_back_verified' and data['commit_invoked']: raise CopyError('false rollback assertion')
        elif state == 'reconciled':
            exact_keys(data, {'classification', 'current', 'assessment', 'historical_commit_proven', 'live_published', 'cloud_performed'}, 'reconciliation')
            if data['classification'] not in ('before_present', 'after_present') or any(data[k] is not False for k in ('historical_commit_proven', 'live_published', 'cloud_performed')): raise CopyError('reconciliation truth')
            copies.hash_text(data['current']); copies.hash_text(data['assessment'])
        elif state == 'resolved':
            if data != digest(result[-1]): raise CopyError('resolution terminal drift')
        result.append(event)
    return result


def _event(run, approval, state, data=None):
    events = _events(run)
    if len(events) >= MAX_EVENTS: raise CopyError('event budget exceeded')
    record = {'version': 1, 'sequence': len(events), 'previous': digest(events[-1]) if events else None,
              'approval': approval, 'state': state, 'data': data}
    _validate_events([*events, record])  # Refuse invalid transitions before durable append.
    _retained_history(run, [*events, record])
    durable(run/'events'/f'{len(events):04}.json', record)
    return record


def _receipt_envelope(run):
    """Retained authority only, not current SQLite state or runtime execution."""
    m = load(run/'publication.json')
    exact_keys(m, {'version', 'kind', 'run', 'target', 'source', 'before', 'after', 'wording', 'policy', 'sources', 'engine'}, 'publication')
    if type(m['version']) is not int or m['version'] != 1 or m['kind'] != 'private-transactional-rehearsal' or not _same(m['policy'], POLICY):
        raise CopyError('retained publication policy')
    if run.parent.name != 'runs' or not _same(m['run'], physical(run, directory=True)) or not _same(m['target'], _target(run.parent.parent)):
        raise CopyError('retained publication identity')
    copies.hash_text(m['before']); copies.hash_text(m['after'])
    _source_schema(m['source'])
    exact_keys(m['sources'], native_runtime.REQUIRED_SOURCES, 'publisher sources')
    for pin in m['sources'].values(): copies.hash_text(pin)
    _engine_schema(m['engine'])
    # Receipt-only provenance: validate retained Stage-2 authorities, not SQL.
    packet = checked(m['source']['packet'], directory=True)
    manifest = load(packet/'packet.json')
    wording.packet_schema(manifest)
    if digest(manifest) != m['source']['manifest'] or not _same(copies.identity(packet/'complete.json'), m['source']['complete']):
        raise CopyError('retained source authority drift')
    if not _same(copies.identity(packet/'preview.json'), manifest['files']['preview.json']) or not _same(load(packet/'preview.json'), m['wording']):
        raise CopyError('retained preview drift')
    if not _same(load(run/'prepared.json'), {'version': 1, 'publication': digest(m)}):
        raise CopyError('retained preparation binding')
    return m


def _retained_history(run, events):
    m = _receipt_envelope(run)
    expected = {'run': m['run'], 'approval': digest(m), 'target': m['target']['target']}
    if not _same(load(run/'intent.json'), expected) or not _same(load(run.parent.parent/'registry'/(run.name+'.json')), expected):
        raise CopyError('retained intent binding')
    backup = None
    for event in events:
        if event['approval'] != digest(m): raise CopyError('retained approval binding')
        if event['state'] == 'backup_durable':
            backup = copies.identity(run/'backup.sqlite')
            if not _same(event['data'], backup): raise CopyError('retained backup binding')
        if event['state'] in ('commit_intent', 'committed_verified'):
            data = event['data']
            if backup is None or not _same(data['backup'], backup) or data['before'] != m['before'] or data['after'] != m['after']:
                raise CopyError('terminal publication/backup contradiction')
        if event['state'] == 'reconciled':
            matches = [load(p) for p in _entries(run, MAX_EVENTS + 8) if p.suffix == '.json' and p.name not in ('publication.json', 'intent.json')]
            matches = [a for a in matches if digest(a) == event['data']['assessment']]
            if len(matches) != 1: raise CopyError('retained recovery assessment missing or ambiguous')
            a = matches[0]
            exact_keys(a, {'version', 'kind', 'run', 'publication', 'event_head', 'current', 'classification', 'historical_commit_proven', 'sources'}, 'recovery assessment')
            expected_current = m['before'] if a['classification'] == 'before_present' else m['after'] if a['classification'] == 'after_present' else None
            if (type(a['version']) is not int or a['version'] != 1 or a['kind'] != 'owned-recovery-assessment'
                    or a['historical_commit_proven'] is not False or not _same(a['run'], m['run'])
                    or a['publication'] != digest(m) or a['event_head'] != event['previous']
                    or not _same(a['sources'], m['sources']) or expected_current is None
                    or a['current'] != expected_current or event['data']['current'] != expected_current
                    or event['data']['classification'] != a['classification']):
                raise CopyError('retained recovery assessment contradiction')
        if event['state'] in ('committed_verified', 'reconciled') and backup is None:
            raise CopyError('terminal backup missing')
    return m


def _guard(root):
    _target(root)
    for run in _entries(root/'runs', MAX_RUNS):
        checked(run, directory=True)
        _receipt_envelope(run)
        if os.path.lexists(run/'intent.json') or os.path.lexists(run/'events'):
            marker = load(root/'registry'/(run.name+'.json'))
            if not _same(marker, load(run/'intent.json')): raise CopyError('registry intent mismatch')
    for marker in _entries(root/'registry', MAX_RUNS + 1):
        if marker.name == 'enrollment.json': continue
        if not re.fullmatch('[a-zA-Z0-9_-]{1,64}.json', marker.name): raise CopyError('registry entry refused')
        guard = load(marker)
        exact_keys(guard, {'run', 'approval', 'target'}, 'registry guard')
        run = root/'runs'/marker.stem
        if not _same(guard['run'], physical(run, directory=True)) or not _same(guard['target'], physical(root/'target.sqlite')):
            raise CopyError('registry binding drift')
        events = _events(run)
        _retained_history(run, events)
        if not events or any(e['approval'] != guard['approval'] for e in events) or events[-1]['state'] != 'resolved':
            raise CopyError('target quarantined; reconcile required')
        if len(events) < 2 or events[-2]['state'] not in ('committed_verified', 'reconciled') or events[-1]['data'] != digest(events[-2]):
            raise CopyError('registry terminal proof refused')


def _check(m, db=None):
    native_runtime.stopped()
    path = Path(m['target']['target']['path'])
    if not _same(physical(path), m['target']['target']) or not _same(_target(path.parent), m['target']):
        raise CopyError('target metadata drift')
    for suffix in ('-wal', '-shm', '-journal'):
        side = Path(str(path)+suffix)
        if os.path.lexists(side):
            checked(side)
            if suffix != '-journal': raise CopyError('unsupported target sidecar')
    if path.stat().st_size > POLICY['max_database_bytes'] or shutil.disk_usage(path.parent).free < POLICY['minimum_free_bytes']:
        raise CopyError('publication space budget')
    if db is not None and db.execute('PRAGMA journal_mode').fetchone() != ('delete',):
        raise CopyError('DELETE-only target mode drift')


def _backup_reserved(path, destination, before, deadline):
    """W is reserved by caller; R backs up to new D, closes before DML."""
    copies.no_sidecars(destination)
    with copies.parent_handle(destination) as parent:
        fd = os.open(destination.name, os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            owned = physical(destination)
            with copies.sqlite_handle_scope(path), closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, isolation_level=None, timeout=1)) as reader:
                reader.execute('PRAGMA query_only=ON'); reader.execute('BEGIN')
                try:
                    if snapshot_connection(reader) != before: raise CopyError('backup reader BEFORE mismatch')
                    with copies.sqlite_handle_scope(destination), closing(sqlite3.connect(destination.as_uri()+'?mode=rw', uri=True, isolation_level=None, timeout=1)) as dest:
                        if dest.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone() != ('exclusive',): raise CopyError('backup locking refused')
                        def progress(status, remaining, total):
                            if time.monotonic() > deadline or total*65536 > POLICY['max_database_bytes']*16:
                                raise CopyError('backup budget exceeded')
                        reader.backup(dest, pages=256, progress=progress, sleep=.01)
                        if dest.execute('PRAGMA journal_mode=DELETE').fetchone() != ('delete',): raise CopyError('backup detach refused')
                        if snapshot_connection(dest) != before: raise CopyError('backup full BEFORE mismatch')
                finally:
                    if reader.in_transaction: reader.execute('ROLLBACK')
            # Only destination FD: never the target main/SHM.
            copies.no_sidecars(destination)
            if physical(destination) != owned: raise CopyError('backup identity drift')
            os.fsync(fd)
            if sys.platform == 'darwin': fcntl.fcntl(fd, 51)  # F_FULLFSYNC
            os.fsync(parent)
        finally:
            os.close(fd)
    return copies.identity(destination)


def _fresh(m):
    _check(m)
    path = Path(m['target']['target']['path'])
    with copies.sqlite_handle_scope(path), closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, isolation_level=None, timeout=1)) as db:
        db.execute('PRAGMA query_only=ON')
        result = snapshot_connection(db)
    _check(m)
    return digest(result)


@copies.bounded_work
def rehearse(run, *, approval):
    run = checked(run, directory=True)
    root = run.parent.parent
    with _locked(root):
        _guard(root)
        m, before, after = _envelope(run)
        copies.hash_text(approval)
        if approval != digest(m): raise CopyError('publication approval mismatch')
        if os.path.lexists(root/'registry'/(run.name+'.json')): raise CopyError('approval consumed')
        plan = _transfer(before, after)
        path = root/'target.sqlite'
        _delete_header(path); _check(m)
        intent = {'run': m['run'], 'approval': approval, 'target': m['target']['target']}
        durable(run/'intent.json', intent)
        durable(root/'registry'/(run.name+'.json'), intent)
        copies.new_root(run/'events')
        _event(run, approval, 'reserved')
        _phase('intent')
        deadline = copies.work_deadline()
        db = None
        commit_invoked = False
        scope = copies.sqlite_handle_scope(path)
        scope.__enter__()
        try:
            _retained_history(run, _events(run))
            db = sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, isolation_level=None, timeout=1)
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute('PRAGMA synchronous=EXTRA'); db.execute('PRAGMA fullfsync=ON')
            if db.execute('PRAGMA synchronous').fetchone() != (3,) or db.execute('PRAGMA fullfsync').fetchone() != (1,): raise CopyError('durability settings refused')
            db.execute('BEGIN IMMEDIATE')
            _check(m, db); verify_schema_connection(db)
            if snapshot_connection(db) != before: raise CopyError('stale writer BEFORE')
            _phase('writer_before', db)
            backup = _backup_reserved(path, run/'backup.sqlite', before, deadline)
            _event(run, approval, 'backup_durable', backup)
            _phase('backup_durable', db)
            if snapshot_connection(db) != before: raise CopyError('writer BEFORE changed during backup')
            _check(m, db)
            _event(run, approval, 'writing')
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            for index, (kind, table, columns, values, rid) in enumerate(plan):
                if kind == 'update':
                    sql = 'UPDATE '+quote(table)+' SET '+','.join(quote(c)+'=?' for c in columns)+' WHERE rowid=?'
                    args = [_decode(v) for v in values]+[rid]
                else:
                    sql = 'INSERT INTO '+quote(table)+' ('+','.join(map(quote, columns))+') VALUES ('+','.join('?' for _ in columns)+')'
                    args = [_decode(v) for v in values]
                if db.execute(sql, args).rowcount != 1: raise CopyError('transfer rowcount')
                _phase('first_update' if kind == 'update' and index == 0 else kind, db)
            if snapshot_connection(db) != after: raise CopyError('writer full AFTER mismatch')
            _phase('after_check', db)
            # Revalidation must never raw-open a target alias (see alias gate).
            current, _, _ = _envelope(run)
            if not _same(current, m): raise CopyError('publication changed before commit')
            _check(m, db)
            _phase('precommit_revalidated', db)
            _event(run, approval, 'commit_intent', {'backup': backup, 'before': m['before'], 'after': m['after']})
            if snapshot_connection(db) != after: raise CopyError('last writer AFTER mismatch')
            _phase('commit_intent', db)
            _check(m, db)
            _retained_history(run, _events(run))
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            commit_invoked = True
            _commit(db)
            _phase('commit_returned', db)
            _event(run, approval, 'sqlite_commit_returned')
            db.close(); db = None
            _phase('before_readback')
            if _fresh(m) != m['after']: raise CopyError('postcommit external drift')
            _phase('readback')
            receipt = {'state': 'committed_verified', 'before': m['before'], 'after': m['after'],
                       'backup': backup, 'live_published': False, 'cloud_performed': False}
            terminal = _event(run, approval, 'committed_verified', receipt)
            _phase('terminal')
            _event(run, approval, 'resolved', digest(terminal))
            _phase('resolved')
            _guard(root)
            return receipt
        except BaseException as exc:
            state = 'uncertain'
            try:
                if db is not None:
                    try:
                        db.set_progress_handler(None, 0)
                        if db.in_transaction: db.execute('ROLLBACK')
                    finally:
                        db.close(); db = None
                if not commit_invoked and _fresh(m) == m['before']:
                    state = 'rolled_back_verified'
                _event(run, approval, state, {'sqlite_errorcode': getattr(exc, 'sqlite_errorcode', None), 'commit_invoked': commit_invoked})
            except BaseException:
                pass  # Prior independent guard, not failure-receipt durability, is authority.
            raise CopyError('publication '+state+'; reconcile required') from exc
        finally:
            try:
                if db is not None: db.close()
            finally:
                scope.__exit__(None, None, None)


def _commit(db):
    db.execute('COMMIT')


def _recovery_evidence(run):
    m, _, _ = _envelope(run)
    marker = load(run.parent.parent/'registry'/(run.name+'.json'))
    if not _same(marker, {'run': m['run'], 'approval': digest(m), 'target': m['target']['target']}):
        raise CopyError('recovery registry binding')
    events = _events(run)
    _retained_history(run, events)
    if not events or any(e['approval'] != digest(m) for e in events): raise CopyError('recovery event binding')
    backups = [e['data'] for e in events if e['state'] == 'backup_durable']
    if len(backups) != 1 or copies.identity(run/'backup.sqlite') != backups[0] or digest(snapshot(run/'backup.sqlite')) != m['before']:
        raise CopyError('recovery requires a durable verified backup')
    return m, events


@contextmanager
def _recovery_writer(m):
    _check(m)
    path = Path(m['target']['target']['path'])
    # A valid owned rollback journal may need recovery. Never unlink it.
    for suffix in ('-wal', '-shm'):
        if os.path.lexists(str(path)+suffix): raise CopyError('DELETE-only recovery')
    with copies.sqlite_handle_scope(path):
        db = sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, isolation_level=None, timeout=1)
        try:
            with copies.sql_budget(db):
                db.execute('PRAGMA synchronous=EXTRA'); db.execute('PRAGMA fullfsync=ON')
                db.execute('BEGIN IMMEDIATE')
                _check(m, db); verify_schema_connection(db)
                yield db
        finally:
            try:
                db.set_progress_handler(None, 0)
                if db.in_transaction: db.execute('ROLLBACK')
            finally:
                db.close()


@copies.bounded_work
def recovery_preview(run, name, *, authorize_owned_recovery=False):
    """Explicit authorization includes SQLite hot-journal recovery, not DML."""
    if authorize_owned_recovery is not True: raise CopyError('owned-target recovery authorization required')
    if type(name) is not str or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', name): raise CopyError('recovery name')
    run = checked(run, directory=True)
    with _locked(run.parent.parent):
        m, events = _recovery_evidence(run)
        if events[-1]['state'] == 'resolved': raise CopyError('recovery already resolved')
        with _recovery_writer(m) as db:
            try:
                current = digest(snapshot_connection(db))
                classification = 'before_present' if current == m['before'] else ('after_present' if current == m['after'] else 'external_conflict')
                assessment = {'version': 1, 'kind': 'owned-recovery-assessment', 'run': m['run'],
                              'publication': digest(m), 'event_head': digest(events[-1]),
                              'current': current, 'classification': classification,
                              'historical_commit_proven': False, 'sources': native_runtime.sources()}
                durable(run/(name+'.json'), assessment)
                return {**assessment, 'approval_digest': digest(assessment)}
            finally:
                if db.in_transaction: db.execute('ROLLBACK')


@copies.bounded_work
def reconcile(assessment_path, *, approval):
    assessment_path = checked(assessment_path)
    run = assessment_path.parent
    with _locked(run.parent.parent):
        a = load(assessment_path)
        exact_keys(a, {'version', 'kind', 'run', 'publication', 'event_head', 'current', 'classification', 'historical_commit_proven', 'sources'}, 'recovery assessment')
        copies.hash_text(approval)
        if approval != digest(a) or type(a['version']) is not int or a['version'] != 1 or a['kind'] != 'owned-recovery-assessment' or a['historical_commit_proven'] is not False:
            raise CopyError('recovery approval refused')
        m, events = _recovery_evidence(run)
        if events[-1]['state'] == 'resolved': raise CopyError('recovery already resolved')
        if not _same(a['run'], m['run']) or a['publication'] != digest(m) or a['event_head'] != digest(events[-1]) or not _same(a['sources'], native_runtime.sources()):
            raise CopyError('stale recovery assessment')
        expected = m['before'] if a['classification'] == 'before_present' else m['after'] if a['classification'] == 'after_present' else None
        if expected is None or expected != a['current']: raise CopyError('external conflict remains quarantined')
        with _recovery_writer(m) as db:
            try:
                if digest(snapshot_connection(db)) != expected: raise CopyError('recovery current state drift')
                _check(m, db)
                receipt = {'classification': a['classification'], 'current': expected, 'assessment': approval,
                           'historical_commit_proven': False, 'live_published': False, 'cloud_performed': False}
                terminal = _event(run, digest(m), 'reconciled', receipt)
                _event(run, digest(m), 'resolved', digest(terminal))
                return receipt
            finally:
                if db.in_transaction: db.execute('ROLLBACK')


@copies.bounded_work
def restore_copy(run, destination):
    """Restore backup only into a NEW nonimportable recovery copy, never target."""
    run = checked(run, directory=True)
    with _locked(run.parent.parent):
        m, _ = _recovery_evidence(run)
        root = copies.new_root(destination)
        durable(root/'preparing.json', {'state': 'nonimportable-recovery-copy'})
        result = copies.backup(run/'backup.sqlite', root/'recovery.sqlite')
        if digest(snapshot(result)) != m['before']: raise CopyError('recovery copy mismatch')
        durable(root/'restored.json', {'before': m['before'], 'copy': copies.identity(result), 'in_place': False})
        return result


def status(run):
    """Receipt-only. Never opens SQLite or performs implicit journal recovery."""
    run = checked(run, directory=True)
    try:
        _target(run.parent.parent)
        _receipt_envelope(run)
        _guard(run.parent.parent)
        if not os.path.lexists(run/'events'):
            if os.path.lexists(run/'intent.json') or os.path.lexists(run.parent.parent/'registry'/(run.name+'.json')):
                raise CopyError('started run missing events')
            return {'state': 'prepared', 'quarantined': False, 'target_inspected': False}
        events = _events(run)
        return {'state': events[-2]['state'] if events else 'prepared', 'quarantined': False, 'target_inspected': False}
    except (CopyError, OSError):
        try:
            events = _events(run)
            state = events[-1]['state'] if events else 'unknown'
        except (CopyError, OSError):
            state = 'unknown'
        return {'state': state, 'quarantined': True, 'target_inspected': False}
