"""Synthetic exact stage/carrier tests; these are not native acceptance."""
import copy
import plistlib
import unittest
from things_workbench.copies import CopyError
from things_workbench.history import retain, semantic
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import tempfile

TASK = 'T' * 22
OTHER = 'O' * 22
COUNTER, LOCAL, TIMELINE, OLD, SCALAR = [c * 22 for c in 'CLDOS']
HISTORY = 'synthetic-history'


def operation(properties):
    return {TASK: {'e': 'Task7', 't': 1, 'p': properties}}


def inventory(rows):
    result = {'columns': ['rowid', 'uuid', 'value'], 'raw': [], 'maps': [], 'scalars': []}
    for rid, uid, value in rows:
        row = [rid, uid, plistlib.dumps(value, fmt=plistlib.FMT_BINARY).hex()]
        result['raw'].append(row)
        if type(value) is dict:
            result['maps'].append(semantic(value))
        else:
            result['scalars'].append(row.copy())
    return result


def fixture():
    old = {OTHER: {'e': 'Task7', 't': 1, 'p': {'nt': {'text': 'inherited', 'v': 1}}}}
    local = operation({'nt': {'text': 'old base', 'v': 0}})
    changes = operation({'nt': {'text': 'new note', 'v': 2}, 'md': 10.25})
    base = operation({'nt': {'text': 'new base', 'v': 1}})
    # Keep each old value represented; the native local state can add a base.
    local_after = copy.deepcopy(local)
    local_after[OTHER] = {'e': 'Task7', 't': 1, 'p': {'nt': {'text': 'new base', 'v': 1}}}
    base = {OTHER: copy.deepcopy(local_after[OTHER])}
    rows = [(10, COUNTER, 8), (20, LOCAL, local), (30, OLD, old), (40, SCALAR, 'opaque')]
    before = inventory(rows)
    after = inventory([(10, COUNTER, 9), (20, LOCAL, local_after), *rows[2:], (50, TIMELINE, changes)])
    keys = {COUNTER: HISTORY + '-IndexOfLastLocalItem-Item-1', LOCAL: HISTORY + '-LocalState-Item-1', TIMELINE: HISTORY + '-LocalTimeline-Item-9'}
    def get(uid, value):
        return {'kind': 'get', 'key': keys[uid], 'uuid': uid, 'value': value}
    def set_(uid, previous, value):
        return {'kind': 'set', 'key': keys[uid], 'uuid': uid, 'before': previous, 'value': value}
    metadata = {'build': '32400506', 'schema': 301, 'history_key': HISTORY, 'history_uuid': HISTORY, 'history_key_after': HISTORY, 'history_uuid_after': HISTORY,
                'trace': [get(LOCAL, local), get(COUNTER, 8), set_(TIMELINE, None, changes), set_(COUNTER, 8, 9), set_(LOCAL, local, local_after)]}
    return before, [{'changes': changes, 'base': base}], after, metadata


def replace_value(inv, uid, value):
    rows = [(r, u, value if u == uid else plistlib.loads(bytes.fromhex(b))) for r, u, b in inv['raw']]
    inv.update(inventory(rows))


class MetadataStageTests(unittest.TestCase):
    def test_inventory_preserves_full_reviewed_columns_and_refuses_extras(self):
        from things_workbench.history import inventory as read_inventory
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / 'synthetic.sqlite'
            with closing(sqlite3.connect(path)) as c:
                c.execute('CREATE TABLE BSSyncronyMetadata(uuid TEXT PRIMARY KEY, value BLOB)')
                c.execute('INSERT INTO BSSyncronyMetadata VALUES (?,?)', (COUNTER, plistlib.dumps(8)))
                c.commit()
            os.chmod(path, 0o600)
            self.assertEqual(read_inventory(path).get('columns'), ['rowid','uuid','value'])
            with closing(sqlite3.connect(path)) as c:
                c.execute('ALTER TABLE BSSyncronyMetadata ADD COLUMN opaque BLOB')
            with self.assertRaises(CopyError): read_inventory(path)

    def test_native_encoded_metadata_identity_is_not_task_id_width(self):
        before, events, after, metadata = fixture()
        for inv in (before, after):
            for row in inv['raw']:
                if row[1] == TIMELINE: row[1] = 'D' * 21
        metadata['trace'][2]['uuid'] = 'D' * 21
        self.assertTrue(retain(before,events,after,metadata)['complete'])

    def test_exact_observed_stage_preserves_all_carriers(self):
        result = retain(*fixture())
        self.assertTrue(result['complete'])
        self.assertEqual(result['stages'], 1)
        self.assertEqual(result['index_advance'], 1)

    def test_writing_non_wording_operation_is_not_an_index_permit(self):
        data = list(fixture())
        data[1][0]['changes'][TASK]['e'] = 'UnexpectedEntity'
        replace_value(data[2], TIMELINE, data[1][0]['changes'])
        with self.assertRaises(CopyError):
            retain(*data)

    def test_carrier_identities_raw_columns_and_extra_rows(self):
        for kind in ('rowid', 'uuid', 'deleted', 'extra', 'column', 'reserialized', 'old-timeline-alias'):
            data = list(fixture()); after = data[2]
            row = next(r for r in after['raw'] if r[1] == OLD)
            if kind == 'rowid': row[0] = 999
            elif kind == 'uuid': row[1] = 'Z' * 22
            elif kind == 'deleted': after['raw'].remove(row)
            elif kind == 'extra': after['raw'].append([999, 'Z'*22, row[2]])
            elif kind == 'column': after['columns'].append('opaque')
            elif kind == 'reserialized': row[2] = plistlib.dumps(plistlib.loads(bytes.fromhex(row[2])), fmt=plistlib.FMT_XML).hex()
            else: next(r for r in after['raw'] if r[1] == TIMELINE)[0] = row[0]
            # Rebuild only derived views; the raw tamper is the test input.
            after['maps'] = [semantic(plistlib.loads(bytes.fromhex(r[2]))) for r in after['raw'] if type(plistlib.loads(bytes.fromhex(r[2]))) is dict]
            with self.subTest(kind=kind), self.assertRaises(CopyError): retain(*data)

    def test_index_wrong_types_steps_getter_and_unrelated_scalar(self):
        for value in (True, 9.0, '9', 7, 8, 10, 2**63):
            data = list(fixture()); replace_value(data[2], COUNTER, value)
            with self.subTest(value=value), self.assertRaises(CopyError): retain(*data)
        for record, field, value in ((1, 'value', True), (3, 'before', 7), (3, 'value', True), (3, 'uuid', SCALAR), (3, 'key', 'bare-index-key'), (2, 'uuid', OLD), (4, 'uuid', OLD), (4, 'before', {})):
            data = list(fixture()); data[3]['trace'][record][field] = value
            with self.subTest(record=record, field=field), self.assertRaises(CopyError): retain(*data)
        data = list(fixture()); replace_value(data[2], SCALAR, 1)
        with self.assertRaises(CopyError): retain(*data)

    def test_exact_timeline_full_map_and_native_base_required(self):
        for kind in ('timeline-value', 'missing-base', 'bad-base', 'no-stage', 'two-stages', 'extra-callback', 'wrong-history'):
            data = list(fixture())
            if kind == 'timeline-value': replace_value(data[2], TIMELINE, operation({'nt': 'different', 'md': 10.25}))
            elif kind == 'missing-base': del data[1][0]['base']
            elif kind == 'bad-base': data[1][0]['base'] = False
            elif kind == 'no-stage': data[1].clear()
            elif kind == 'two-stages': data[1].append(copy.deepcopy(data[1][0]))
            elif kind == 'extra-callback': data[3]['trace'].append(copy.deepcopy(data[3]['trace'][0]))
            else: data[3]['history_uuid_after'] = 'different-history'
            with self.subTest(kind=kind), self.assertRaises(CopyError): retain(*data)

    def test_all_carriers_of_each_old_new_atom_are_required(self):
        from things_workbench.history import atoms, typed
        original = fixture()
        required = atoms(original[0]['maps']) | atoms([original[1][0]['changes'], original[1][0]['base']])
        self.assertGreater(len(required), 0)
        for atom in required:
            data = list(copy.deepcopy(original))
            for row in list(data[2]['raw']):
                value = plistlib.loads(bytes.fromhex(row[2]))
                if type(value) is not dict: continue
                for uid, op in list(value.items()):
                    for key, prop in list(op['p'].items()):
                        if (uid,op['e'],op['t'],key,typed(prop)) == atom: del op['p'][key]
                    if not op['p']: del value[uid]
                replace_value(data[2], row[1], value)
            with self.subTest(atom_property=atom[3]), self.assertRaises(CopyError): retain(*data)

    def test_carrier_order_is_irrelevant_but_duplicate_deletion_is_unsupported(self):
        before, events, after, metadata = fixture()
        before['raw'].append([60,'X'*22,before['raw'][2][2]])
        before['maps'].append(copy.deepcopy(before['maps'][1]))
        after['raw'].append([60,'X'*22,before['raw'][2][2]])
        after['maps'].append(copy.deepcopy(before['maps'][1]))
        self.assertTrue(retain(before,events,after,metadata)['complete'])
        after['raw'].reverse(); after['maps'].reverse(); after['scalars'].reverse()
        self.assertTrue(retain(before,events,after,metadata)['complete'])
        after['raw']=[r for r in after['raw'] if r[1]!='X'*22]
        after['maps']=after['maps'][1:]
        with self.assertRaisesRegex(CopyError, 'carrier'):
            retain(before,events,after,metadata)

    def test_base_loss_even_with_matching_observed_local_write(self):
        data = list(fixture()); previous = data[3]['trace'][4]['before']
        replace_value(data[2], LOCAL, previous)
        data[3]['trace'][4]['value'] = previous
        with self.assertRaisesRegex(CopyError, 'lost new'): retain(*data)

    def test_old_base_loss_even_with_matching_observed_local_write(self):
        data = list(fixture()); replacement = data[1][0]['base']
        replace_value(data[2], LOCAL, replacement)
        data[3]['trace'][4]['value'] = replacement
        with self.assertRaisesRegex(CopyError, 'lost old'): retain(*data)
