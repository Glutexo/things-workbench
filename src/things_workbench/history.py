"""Lossless typed pending-map retention. Unknown coalescing is refusal."""
from contextlib import closing
import math
import plistlib
import re
import sqlite3
from .copies import CopyError, checked

NULL_SENTINEL = 'com.culturedcode.NSPropertyListSerialization.NSNull'


def typed(v):
    if v is None: return ('null',)
    if type(v) is bool: return ('bool',v)
    if type(v) is int: return ('int',v)
    if type(v) is float and math.isfinite(v): return ('real',v.hex())
    if type(v) is str: return ('text',v)
    if type(v) is bytes: return ('blob',v.hex())
    if type(v) is list: return ('list',tuple(typed(x) for x in v))
    if type(v) is dict and all(type(k) is str for k in v): return ('dict',tuple((k,typed(v[k])) for k in sorted(v)))
    raise CopyError('unsupported history value')


def semantic(v):
    if type(v) is str and v == NULL_SENTINEL: return None
    if type(v) is dict: return {k:semantic(x) for k,x in v.items()}
    if type(v) is list: return [semantic(x) for x in v]
    return v


def atoms(maps):
    result = set()
    for mapping in maps:
        if type(mapping) is not dict: raise CopyError('unknown history map')
        for uid,op in mapping.items():
            if type(uid) is not str or not re.fullmatch('[A-Za-z0-9]{22}',uid) or type(op) is not dict or set(op) != {'e','t','p'} or type(op['e']) is not str or type(op['t']) is not int or op['t'] not in (0,1,2) or type(op['p']) is not dict or not op['p']:
                raise CopyError('unknown or empty history operation')
            for k,v in op['p'].items():
                if type(k) is not str: raise CopyError('invalid property key')
                result.add((uid,op['e'],op['t'],k,typed(v)))
    return result


def inventory(path):
    with closing(sqlite3.connect(checked(path).as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('PRAGMA query_only=ON'); c.execute('BEGIN')
        try:
            layout = c.execute('PRAGMA table_xinfo(BSSyncronyMetadata)').fetchall()
            expected = [(0, 'uuid', 'TEXT', 0, None, 1, 0), (1, 'value', 'BLOB', 0, None, 0, 0)]
            if layout != expected:
                raise CopyError('unsupported metadata columns')
            maps=[]; scalars=[]; raw=[]
            for rid,uid,blob in c.execute('SELECT rowid,uuid,value FROM BSSyncronyMetadata ORDER BY rowid'):
                if type(blob) is not bytes: raise CopyError('non-blob history')
                try: obj=plistlib.loads(blob)
                except Exception as exc: raise CopyError('undecodable history') from exc
                raw.append([rid,uid,blob.hex()])
                if type(obj) is dict: maps.append(semantic(obj))
                else:
                    typed(obj)
                    scalars.append([rid,uid,blob.hex()])
            atoms(maps)
            result = {'columns':['rowid','uuid','value'],'maps':maps,'scalars':scalars,'raw':raw}
            _records(result)
            return result
        finally:
            c.execute('ROLLBACK')


def _records(inv):
    if type(inv) is not dict or set(inv) != {'columns', 'raw', 'maps', 'scalars'} or inv['columns'] != ['rowid', 'uuid', 'value'] or type(inv['raw']) is not list:
        raise CopyError('unsupported metadata inventory columns')
    records = {}; ids = set(); maps = []; scalars = []
    for row in inv['raw']:
        if type(row) is not list or len(row) != 3 or type(row[0]) is not int or type(row[1]) is not str or not row[1] or type(row[2]) is not str:
            raise CopyError('invalid metadata raw record')
        if row[0] in ids or row[1] in records:
            raise CopyError('duplicate metadata identity')
        try:
            value = plistlib.loads(bytes.fromhex(row[2]))
        except Exception as exc:
            raise CopyError('undecodable metadata record') from exc
        typed(value)
        records[row[1]] = (row, value); ids.add(row[0])
        if type(value) is dict: maps.append(semantic(value))
        else: scalars.append(row)
    if typed(inv['maps']) != typed(maps) or typed(inv['scalars']) != typed(scalars):
        raise CopyError('metadata raw/decoded inventory mismatch')
    return records


def _binding(metadata):
    fields = {'build', 'schema', 'history_key', 'history_uuid', 'history_key_after', 'history_uuid_after', 'trace'}
    if type(metadata) is not dict or set(metadata) != fields or metadata['build'] != '32400506' or type(metadata['schema']) is not int or metadata['schema'] != 301:
        raise CopyError('unsupported native metadata envelope')
    history = metadata['history_key']
    if type(history) is not str or not history or any(metadata[k] != history for k in ('history_uuid', 'history_key_after', 'history_uuid_after')):
        raise CopyError('native history identity changed')
    trace = metadata['trace']
    if type(trace) is not list or len(trace) != 5:
        raise CopyError('unknown native metadata callback sequence')
    for record, kind in zip(trace, ('get', 'get', 'set', 'set', 'set')):
        fields = {'kind', 'key', 'uuid', 'value'} | ({'before'} if kind == 'set' else set())
        if type(record) is not dict or set(record) != fields or record['kind'] != kind or type(record['key']) is not str or type(record['uuid']) is not str or not record['uuid']:
            raise CopyError('malformed native metadata callback')
    lg, cg, timeline, counter, local = trace
    if type(counter['before']) is not int or type(counter['value']) is not int or not 0 <= counter['before'] < 2**63-1 or counter['value'] != counter['before']+1:
        raise CopyError('native index integer transition refused')
    expected = ((counter, history+'-IndexOfLastLocalItem-Item-1'), (local, history+'-LocalState-Item-1'), (timeline, history+'-LocalTimeline-Item-'+str(counter['value'])))
    if any(record['key'] != key for record, key in expected) or len({counter['uuid'], local['uuid'], timeline['uuid']}) != 3:
        raise CopyError('native qualified metadata resolution mismatch')
    for getter, setter in ((lg, local), (cg, counter)):
        if getter['key'] != setter['key'] or getter['uuid'] != setter['uuid'] or typed(getter['value']) != typed(setter['before']):
            raise CopyError('native metadata getter/setter mismatch')
    if timeline['before'] is not None or type(timeline['value']) is not dict:
        raise CopyError('timeline was not newly inserted')
    return {'counter': counter, 'local': local, 'timeline': timeline}


def retain(before, events, after, metadata):
    """Validate one observed native stage, never a generic scalar exemption.

    The caller must bind metadata to the trusted native runtime and packet.
    An arbitrary JSON dictionary is not authority to resolve native keys.
    """
    binding = _binding(metadata)
    if type(events) is not list or len(events) != 1:
        raise CopyError('exactly one native history stage required')
    b = _records(before)
    a = _records(after)
    counter, local, timeline = (binding[k] for k in ('counter', 'local', 'timeline'))
    try:
        br, bv = b[counter['uuid']]
        ar, av = a[counter['uuid']]
        lr, lv = b[local['uuid']]
        nr, nv = a[local['uuid']]
        tr, tv = a[timeline['uuid']]
    except KeyError as exc:
        raise CopyError('missing native metadata row') from exc
    if br[:2] != ar[:2] or type(bv) is not int or type(av) is not int or not 0 <= bv < 2**63-1 or av != bv+1:
        raise CopyError('local history index identity/type/advance refused')
    if typed(bv) != typed(counter['before']) or typed(av) != typed(counter['value']):
        raise CopyError('native index getter/setter mismatch')
    if typed(semantic(lv)) != typed(local['before']) or typed(semantic(nv)) != typed(local['value']):
        raise CopyError('native local-state getter/setter mismatch')
    if type(lv) is not dict or type(nv) is not dict:
        raise CopyError('native local-state must be a full map')
    if timeline['uuid'] in b or set(a)-set(b) != {timeline['uuid']} or set(b)-set(a):
        raise CopyError('exactly one new timeline carrier required')
    if tr[0] in {row[0] for row, _ in b.values()}:
        raise CopyError('timeline aliases existing row')
    for uid, (row, _) in b.items():
        after_row = a[uid][0]
        if row[:2] != after_row[:2]:
            raise CopyError('metadata carrier identity changed')
        if uid not in (counter['uuid'], local['uuid']) and row != after_row:
            raise CopyError('unrelated metadata raw bytes changed')
    event = events[0]
    if type(event) is not dict or set(event) != {'changes', 'base'} or type(event['changes']) is not dict or len(event['changes']) != 1 or (event['base'] is not None and type(event['base']) is not dict):
        raise CopyError('missing native changes/base proof')
    atoms([event['changes']])
    operation = next(iter(event['changes'].values()))
    keys = set(operation['p'])
    if operation['e'] != 'Task7' or type(operation['t']) is not int or operation['t'] != 1 or 'md' not in keys or not keys & {'tt', 'nt'} or keys - {'md', 'tt', 'nt'}:
        raise CopyError('unsupported native wording operation')
    if typed(semantic(tv)) != typed(event['changes']) or typed(timeline['value']) != typed(event['changes']):
        raise CopyError('complete timeline changes map mismatch')
    new=[]
    for event in events:
        if type(event) is not dict or set(event) != {'changes','base'} or not event['changes']:
            raise CopyError('missing native changes/base proof')
        new.append(event['changes'])
        if event['base'] is not None: new.append(event['base'])
    old_atoms=atoms(before['maps']); new_atoms=atoms(new); actual=atoms(after['maps'])
    expected=old_atoms | new_atoms
    if actual - expected: raise CopyError('unapproved persisted history value')
    if old_atoms - actual: raise CopyError('lost old history operation or base')
    if new_atoms - actual: raise CopyError('lost new history operation or base')
    return {'old_atoms':len(old_atoms),'new_atoms':len(new_atoms),'after_atoms':len(actual),'complete':True,'stages':1,'index_advance':1}
