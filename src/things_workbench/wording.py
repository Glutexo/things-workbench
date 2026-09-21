"""Experimental exact wording changes on owned copies, never live stores."""
from contextlib import closing
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
from .copies import (CopyError, backup, canonical, checked, detached, digest, durable, identity, load, lock, new_root, verify_copy)
from .copies import exact_keys, absolute_text, hash_text, root_identity, identity_schema, import_schema, bounded_supplier
from .fingerprint import snapshot
from .schema_policy import verify_schema


PACKET_FILES = {'before.sqlite', 'native/candidate.sqlite', 'plan.json', 'proof.json', 'preview.json'}


def packet_schema(m):
    exact_keys(m, {'version', 'state', 'root', 'root_identity', 'copy_root', 'imported', 'runtime', 'runtime_digest', 'files', 'verdict'}, 'packet')
    if type(m['version']) is not int or m['version'] != 1 or m['state'] != 'prepared':
        raise CopyError('packet state schema')
    for key in ('root', 'copy_root', 'runtime'):
        absolute_text(m[key])
    root_identity(m['root_identity'])
    hash_text(m['runtime_digest'])
    import_schema(m['imported'])
    exact_keys(m['files'], PACKET_FILES, 'packet artifact')
    for entry in m['files'].values():
        identity_schema(entry)
    verdict = m['verdict']
    exact_keys(verdict, {'before_fingerprint', 'candidate_fingerprint', 'fields', 'history'}, 'verdict')
    hash_text(verdict['before_fingerprint'])
    hash_text(verdict['candidate_fingerprint'])
    if type(verdict['fields']) is not list or not verdict['fields'] or any(type(x) is not str for x in verdict['fields']) or verdict['fields'] != sorted(set(verdict['fields'])) or type(verdict['history']) is not dict:
        raise CopyError('verdict types schema')


def preview_value(before_text, plan, verdict):
    return {'banner':'EXPERIMENTAL COPY ONLY / NO CLOUD / NOT FOR LIVE IMPORT', 'task':plan['task'], 'before':{k:before_text[k] for k in ('title','notes')}, 'after':{k:plan['changes'].get(k,before_text[k]) for k in ('title','notes')}, 'changed_fields':verdict['fields'], 'history_verified':True, 'history':verdict['history']}

from . import history, native_runtime


def parse_plan(text):
    def pairs(items):
        result = {}
        for k,v in items:
            if k in result:
                raise CopyError('duplicate plan key')
            result[k] = v
        return result
    try:
        p = json.loads(text, object_pairs_hook=pairs)
        if type(p) is not dict or set(p) != {'version','task','changes'} or type(p['version']) is not int or p['version'] != 1:
            raise CopyError('unsupported plan envelope')
        if type(p['task']) is not str or not re.fullmatch('[A-Za-z0-9]{22}',p['task']):
            raise CopyError('malformed task identifier')
        changes = p['changes']
        if type(changes) is not dict or not changes or not set(changes) <= {'title','notes'}:
            raise CopyError('only title and notes are permitted')
        for key,v in changes.items():
            if type(v) is not str or '\x00' in v or any(ord(c)<32 and c not in '\n\r\t' for c in v):
                raise CopyError('invalid text value')
            length = len(v.encode('utf-16-le')) // 2
            if key == 'title' and (not length or length > 1000):
                raise CopyError('title policy: 1..1000 UTF-16 units')
            if key == 'notes' and length >= 40000:
                raise CopyError('notes policy: fewer than 40000 UTF-16 units')
        return p
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CopyError('invalid plan encoding') from exc


def target(path, plan):
    with closing(sqlite3.connect(detached(path).as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        version=c.execute("SELECT value FROM Meta WHERE key='databaseVersion'").fetchone()
        encoded = version[0].encode('utf-8') if version and type(version[0]) is str else (version[0] if version else b'')
        if not version or type(plistlib.loads(encoded)) is not int or plistlib.loads(encoded) != 29:
            raise CopyError('unsupported database format')
        row=c.execute('SELECT * FROM TMTask WHERE uuid=?',(plan['task'],)).fetchone()
        if row is None: raise CopyError('task absent')
        row=dict(row)
        if any(row[k] != v for k,v in {'type':0,'status':0,'trashed':0,'start':1,'startDate':None,'stopDate':None,'repeater':None,'rt1_recurrenceRule':None,'rt1_repeatingTemplate':None}.items()):
            raise CopyError('unsupported target state')
        actual={k:v for k,v in plan['changes'].items() if row[k] != v}
        if not actual: raise CopyError('no-op plan')
        return row,{**plan,'changes':actual}


def validate(before, candidate, plan, proof, *, lineage=None):
    detached(before); detached(candidate)
    old=snapshot(before); new=snapshot(candidate)
    if old['schema'] != new['schema'] or old['headers'] != new['headers'] or set(old['tables']) != set(new['tables']):
        raise CopyError('schema/header drift')
    for name,table in old['tables'].items():
        if name not in ('TMTask','BSSyncronyMetadata') and table != new['tables'][name]:
            raise CopyError('unrelated table changed')
    a=old['tables']['TMTask']; b=new['tables']['TMTask']
    if {k:v for k,v in a.items() if k!='rows'} != {k:v for k,v in b.items() if k!='rows'} or len(a['rows']) != len(b['rows']):
        raise CopyError('task layout or row count changed')
    changes=[]; after_row=None
    for left,right in zip(a['rows'],b['rows']):
        if left==right: continue
        left=dict(zip(a['columns'],left)); right=dict(zip(b['columns'],right))
        if left['uuid'] != ['text',plan['task']] or right['uuid'] != left['uuid']:
            raise CopyError('unrelated task or row identity changed')
        fields={k for k in left if left[k]!=right[k]}
        allowed=set(plan['changes']) | {'userModificationDate'}
        if 'notes' in plan['changes']: allowed.add('notesSync')
        if not fields <= allowed or not set(plan['changes']) <= fields or 'userModificationDate' not in fields:
            raise CopyError('unapproved task field delta')
        for k,v in plan['changes'].items():
            if right[k] != ['text',v]: raise CopyError('exact wording readback failed')
        if 'notes' in plan['changes'] and right['notesSync'] != ['integer',1]: raise CopyError('notesSync missing')
        changes.append(sorted(fields)); after_row=right
    if len(changes)!=1: raise CopyError('expected exactly one changed task')
    proof_fields = {'events','max_notes_length','schema_version','history_connected','metadata'}
    if type(proof) is not dict or set(proof) not in (proof_fields, proof_fields | {'note_witness'}) or proof['history_connected'] is not True or type(proof['schema_version']) is not int or proof['schema_version'] != 301 or type(proof['metadata']) is not dict:
        raise CopyError('invalid native proof envelope')
    maximum=proof['max_notes_length']
    if type(maximum) is not int or not 0<maximum<=10000000: raise CopyError('unmeasured notes limit')
    if 'notes' in plan['changes'] and len(plan['changes']['notes'].encode('utf-16-le'))//2 > maximum: raise CopyError('native notes limit')
    events=proof['events']
    if type(events) is not list or len(events)!=1: raise CopyError('expected one native stage')
    event=events[0]
    if type(event) is not dict or set(event)!= {'changes','base'} or type(event['changes']) is not dict or set(event['changes']) != {plan['task']} or (event['base'] is not None and type(event['base']) is not dict): raise CopyError('native stage scope')
    op=event['changes'][plan['task']]
    expected={'md'} | ({'tt'} if 'title' in plan['changes'] else set()) | ({'nt'} if 'notes' in plan['changes'] else set())
    if type(op) is not dict or set(op) != {'e','t','p'} or op['e']!='Task7' or type(op['t']) is not int or op['t']!=1 or type(op['p']) is not dict or set(op['p'])!=expected:
        raise CopyError('native stage entity/type/properties')
    if 'title' in plan['changes'] and op['p']['tt']!=plan['changes']['title']: raise CopyError('native title proof mismatch')
    if type(op['p']['md']) not in (int,float): raise CopyError('native date proof type')
    stored=after_row['userModificationDate']
    epoch=float.fromhex(stored[1]) if stored[0]=='real' else stored[1]
    if epoch != op['p']['md']: raise CopyError('native date proof mismatch')
    if 'note_witness' in proof:
        from .note_representation import retain
        retained=retain(history.inventory(before),events,history.inventory(candidate),proof['metadata'],lineage,proof['note_witness'])
    else:
        retained=history.retain(history.inventory(before),events,history.inventory(candidate),proof['metadata'])
    return {'before_fingerprint':digest(old),'candidate_fingerprint':digest(new),'fields':changes[0],'history':retained}


def _note_lineage(imported, plan, before, candidate, runtime_digest):
    """Derive, never adopt, lineage from a fully verified completed supplier."""
    source = Path(imported['source']['path'])
    if source.name != 'output.sqlite':
        raise CopyError('completed note supplier required')
    prior = verify_completed(source.parent)
    if prior['runtime_digest'] != runtime_digest or prior['verdict']['candidate_fingerprint'] != digest(snapshot(before)):
        raise CopyError('note supplier runtime or full snapshot mismatch')
    prior_plan = parse_plan(canonical(load(source.parent / 'plan.json')))
    if prior_plan['task'] != plan['task'] or set(prior_plan['changes']) != {'notes'} or set(plan['changes']) != {'notes'}:
        raise CopyError('unsupported note lineage plan')
    proof = load(source.parent / 'proof.json')
    if 'note_witness' in proof:
        raise CopyError('only one prior note stage supported')
    def notes(path):
        table = snapshot(path)['tables']['TMTask']
        uid, column = table['columns'].index('uuid'), table['columns'].index('notes')
        rows = [row[column] for row in table['rows'] if row[uid] == ['text', plan['task']]]
        if len(rows) != 1 or rows[0][0] != 'text':
            raise CopyError('note lineage readback refused')
        return rows[0][1]
    return {'before': history.inventory(source.parent / 'before.sqlite'), 'after': history.inventory(source),
            'events': proof['events'], 'metadata': proof['metadata'], 'task': plan['task'],
            'texts': {'first_before': notes(source.parent / 'before.sqlite'), 'first_after': notes(source), 'before': notes(before), 'after': notes(candidate)}}


def _validate_bound(before, candidate, plan, proof, imported, runtime_digest):
    if type(proof) is dict and 'note_witness' in proof:
        lineage = _note_lineage(imported, plan, before, candidate, runtime_digest)
        return validate(before, candidate, plan, proof, lineage=lineage)
    return validate(before, candidate, plan, proof)


def prepare(copy_root, plan, destination, runtime):
    plan=parse_plan(canonical(plan))
    copy_root=checked(copy_root,directory=True)
    with lock(copy_root):
        imported=verify_copy(copy_root)
        source=copy_root/'source.sqlite'
        snapshot(source)  # Reject unsupported layouts before target/native lookup.
        verify_schema(source)
        before_text,plan=target(source,plan)
        history.inventory(source)  # Unknown inherited maps must not reach a save.
        native_runtime.verify(runtime)
        native_runtime.stopped()
        root=new_root(destination)
        durable(root/'preparing.json',{'state':'preparing'})
        durable(root/'started.json',{'state':'preparing','root':str(root)})
        try:
            before=backup(source,root/'before.sqlite')
            native=new_root(root/'native')
            candidate=backup(before,native/'candidate.sqlite')
            durable(root/'plan.json',plan)
            before_identity=identity(before)
            proof=native_runtime.run(runtime,native,root/'plan.json')
            durable(root/'proof.json',proof)
            verdict=_validate_bound(before,candidate,plan,proof,imported,digest(native_runtime.verify(runtime)))
            if identity(before)!=before_identity or verify_copy(copy_root)!=imported: raise CopyError('before/source changed')
            view=preview_value(before_text,plan,verdict)
            durable(root/'preview.json',view)
            manifest={'version':1,'state':'prepared','root':str(root),'root_identity':[root.stat().st_dev,root.stat().st_ino],'copy_root':str(copy_root),'imported':imported,'runtime':str(Path(runtime).absolute()),'runtime_digest':digest(native_runtime.verify(runtime)),'files':{n:identity(root/n) for n in ('before.sqlite','native/candidate.sqlite','plan.json','proof.json','preview.json')},'verdict':verdict}
            durable(root/'packet.json',manifest)
            # Last operation: only durable records can lose the refusal guard.
            # A resurrected guard after power loss is conservatively refused.
            (root/'preparing.json').unlink()
            return root
        except BaseException:
            durable(root/'failed.json',{'state':'quarantined','native_candidate_not_approved':True})
            raise


def _verified_packet(packet, *, completed=False):
    root=checked(packet,directory=True)
    forbidden = ('preparing.json','failed.json') if completed else ('preparing.json','failed.json','applying.json','complete.json','output.sqlite')
    if any(os.path.lexists(root/n) for n in forbidden):
        raise CopyError('quarantined, interrupted, or consumed packet')
    m=load(root/'packet.json')
    packet_schema(m)
    checked(root/'native',directory=True)
    started=load(root/'started.json')
    exact_keys(started, {'state','root'}, 'prepare start')
    if started != {'state':'preparing','root':str(root)}: raise CopyError('prepare start drift')
    if m['root']!=str(root) or m['root_identity']!=[root.stat().st_dev,root.stat().st_ino]: raise CopyError('packet identity drift')
    if verify_copy(m['copy_root'])!=m['imported']: raise CopyError('source provenance drift')
    if digest(native_runtime.verify(m['runtime']))!=m['runtime_digest']: raise CopyError('runtime manifest drift')
    if type(m['files']) is not dict or set(m['files']) != {'before.sqlite','native/candidate.sqlite','plan.json','proof.json','preview.json'}:
        raise CopyError('packet artifact schema')
    for n,expected in m['files'].items():
        if identity(root/n)!=expected: raise CopyError('approved artifact drift')
    detached(root/'before.sqlite'); detached(root/'native/candidate.sqlite')
    plan=parse_plan(canonical(load(root/'plan.json')))
    before_text,actual_plan=target(root/'before.sqlite',plan)
    if canonical(actual_plan)!=canonical(plan): raise CopyError('plan contains unperformed changes')
    verdict=_validate_bound(root/'before.sqlite',root/'native/candidate.sqlite',plan,load(root/'proof.json'),m['imported'],m['runtime_digest'])
    if canonical(verdict)!=canonical(m['verdict']): raise CopyError('reopened proof drift')
    view=preview_value(before_text,plan,verdict)
    if canonical(load(root/'preview.json'))!=canonical(view):
        raise CopyError('preview does not match verified wording')
    return m,view


@bounded_supplier
def verify_completed(packet):
    """Read-only completed-source proof; never replay a native save."""
    root = checked(packet, directory=True)
    complete = load(root / 'complete.json')
    exact_keys(complete, {'state', 'output', 'approval', 'fingerprint', 'live_published', 'cloud_performed'}, 'complete')
    identity_schema(complete['output'])
    hash_text(complete['approval']); hash_text(complete['fingerprint'])
    if complete['state'] != 'output_copy_created' or complete['live_published'] is not False or complete['cloud_performed'] is not False:
        raise CopyError('completed supplier state')
    applying = load(root / 'applying.json')
    exact_keys(applying, {'state', 'approval'}, 'applying')
    if applying != {'state': 'applying', 'approval': complete['approval']}:
        raise CopyError('completed supplier approval drift')
    m, _ = _verified_packet(root, completed=True)
    output = detached(root / 'output.sqlite')
    if digest(m) != complete['approval'] or identity(output) != complete['output'] or digest(snapshot(output)) != complete['fingerprint'] or complete['fingerprint'] != m['verdict']['candidate_fingerprint']:
        raise CopyError('completed supplier output binding drift')
    return m


def verify_packet(packet):
    return _verified_packet(packet)[0]


def preview(packet):
    with lock(packet):
        m,view=_verified_packet(packet)
        return {**view,'approval_digest':digest(m)}


def apply_copy(packet, approval):
    root=checked(packet,directory=True)
    with lock(root):
        m=verify_packet(root)
        if type(approval) is not str or not re.fullmatch('[0-9a-f]{64}',approval) or approval!=digest(m): raise CopyError('approval digest mismatch')
        native_runtime.stopped()
        durable(root/'applying.json',{'state':'applying','approval':approval})
        try:
            output=backup(root/'native/candidate.sqlite',root/'output.sqlite')
            if digest(snapshot(output))!=m['verdict']['candidate_fingerprint']: raise CopyError('output not exact approved candidate')
            for n,expected in m['files'].items():
                if identity(root/n)!=expected: raise CopyError('artifact changed during apply')
            if verify_copy(m['copy_root'])!=m['imported']: raise CopyError('source changed during apply')
            native_runtime.stopped()
            if digest(native_runtime.verify(m['runtime']))!=m['runtime_digest']: raise CopyError('runtime changed during apply')
            durable(root/'complete.json',{'state':'output_copy_created','output':identity(output),'approval':approval,'fingerprint':digest(snapshot(output)),'live_published':False,'cloud_performed':False})
            return output
        except BaseException:
            durable(root/'failed.json',{'state':'quarantined','output_not_approved':True})
            raise
