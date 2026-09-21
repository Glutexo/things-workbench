"""Synthetic semantic fixtures only; no real IDs, text or native evidence."""
import copy
import unittest
import zlib
from things_workbench import history as H
from things_workbench.copies import CopyError
from test_metadata_stage import inventory, operation, TASK, COUNTER, LOCAL, HISTORY


def text_base(text):
    return {'_t': 'tx', 't': 1, 'v': text, 'ch': zlib.crc32(text.encode())}


def text_patch(before, after):
    return {'_t': 'tx', 't': 2, 'ps': [{'p': 0, 'l': len(before.encode()), 'r': after, 'ch': zlib.crc32(after.encode())}]}


def fixture():
    original, mid, final = '', 'synthetic 😀 e\u0301\r\n ', 'second synthetic 🐈\n'
    root = operation({'nt': text_base(original)})
    intermediate = operation({'nt': text_base(mid)})
    first = operation({'nt': text_patch(original, mid), 'md': 1.25})
    second = operation({'nt': text_patch(mid, final), 'md': 2.25})
    def metadata(index, previous, current, timeline, changes):
        local_key = HISTORY + '-LocalState-Item-1'
        counter_key = HISTORY + '-IndexOfLastLocalItem-Item-1'
        return {'build': '32400506', 'schema': 301, 'history_key': HISTORY, 'history_uuid': HISTORY, 'history_key_after': HISTORY, 'history_uuid_after': HISTORY,
                'trace': [{'kind': 'get', 'key': local_key, 'uuid': LOCAL, 'value': previous},
                          {'kind': 'get', 'key': counter_key, 'uuid': COUNTER, 'value': index},
                          {'kind': 'set', 'key': HISTORY + '-LocalTimeline-Item-' + str(index+1), 'uuid': timeline, 'before': None, 'value': changes},
                          {'kind': 'set', 'key': counter_key, 'uuid': COUNTER, 'before': index, 'value': index+1},
                          {'kind': 'set', 'key': local_key, 'uuid': LOCAL, 'before': previous, 'value': current}]}
    first_id, second_id = 'F'*21, 'G'*21
    old = inventory([(1, COUNTER, 0), (2, LOCAL, {})])
    before = inventory([(1, COUNTER, 1), (2, LOCAL, root), (3, first_id, first)])
    after = inventory([(1, COUNTER, 2), (2, LOCAL, root), (3, first_id, first), (4, second_id, second)])
    events = [{'changes': second, 'base': intermediate}]
    meta = metadata(1, root, root, second_id, second)
    texts = {'first_before': original, 'first_after': mid, 'before': mid, 'after': final}
    lineage = {'before': old, 'after': before, 'events': [{'changes': first, 'base': root}], 'metadata': metadata(0, {}, root, first_id, first), 'texts': texts, 'task': TASK}
    composed = operation({'nt': {**text_base(mid), 'ps': second[TASK]['p']['nt']['ps']}})
    wrong = operation({'nt': {**text_base(original), 'ps': second[TASK]['p']['nt']['ps']}})
    witness = {'input': {'original': root, 'intermediate': intermediate, 'first': first, 'second': second, 'texts': texts, 'task': TASK},
               'result': {'roundtrip_original': root, 'extended': root, 'empty_extended': intermediate, 'after_first': intermediate, 'after_second': composed, 'from_intermediate': composed, 'without_first': wrong, 'normalized': {k: text_base(v) for k,v in texts.items()}}}
    return copy.deepcopy([before, events, after, meta, lineage, witness])


def candidate(*args):
    try:
        from things_workbench.note_representation import retain
    except ImportError:
        return H.retain(*args[:4])
    return retain(*args)


class RepresentationTests(unittest.TestCase):
    def test_exact_single_intermediate_representation(self):
        result = candidate(*fixture())
        self.assertTrue(result['complete'])
        self.assertEqual(result['represented_intermediate_bases'], 1)
        self.assertFalse(result['strict_literal_retention'])

    def test_actual_package_source_closure(self):
        from things_workbench.native_runtime import sources
        self.assertIn('note_representation.py', sources())

    def test_prior_lineage_cannot_hide_an_earlier_note_operation(self):
        args = fixture()
        extra = inventory([(9, 'Z'*21, operation({'nt': text_patch('', 'earlier synthetic')}))])
        for inv in {id(inv): inv for inv in (args[0], args[2], args[4]['before'], args[4]['after'])}.values():
            inv['raw'].extend(copy.deepcopy(extra['raw']))
            inv['maps'].extend(copy.deepcopy(extra['maps']))
        with self.assertRaisesRegex(CopyError, 'prior|root|earlier'):
            candidate(*args)

    def test_semantic_negative_matrix(self):
        from test_metadata_stage import replace_value
        # JSON roundtrip separates aliased fixture objects before tampering.
        import json
        mutations = [
            ('absent-base', (1, 0, 'base'), None),
            ('empty-base', (1, 0, 'base'), {}),
            ('base-bool-type', (1, 0, 'base', TASK, 't'), True),
            ('base-entity', (1, 0, 'base', TASK, 'e'), 'Other'),
            ('base-inner-bool', (1, 0, 'base', TASK, 'p', 'nt', 't'), True),
            ('base-crc-bool', (1, 0, 'base', TASK, 'p', 'nt', 'ch'), True),
            ('base-text', (1, 0, 'base', TASK, 'p', 'nt', 'v'), 'forged'),
            ('witness', (5, 'result', 'after_first'), {}),
            ('witness-input', (5, 'input', 'texts', 'before'), 'forged'),
            ('readback', (4, 'texts', 'after'), 'forged'),
            ('lineage', (4, 'after', 'maps'), []),
            ('callback-bool', (3, 'trace', 3, 'value'), True),
        ]
        for label, path, value in mutations:
            args = json.loads(json.dumps(fixture()))
            cursor = args
            for key in path[:-1]: cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(label=label), self.assertRaises(CopyError): candidate(*args)
        for key, value in [('p', True), ('p', 1), ('l', -1), ('l', 1), ('ch', True), ('ch', 0), ('r', 'forged')]:
            args = json.loads(json.dumps(fixture()))
            args[1][0]['changes'][TASK]['p']['nt']['ps'][0][key] = value
            args[3]['trace'][2]['value'] = copy.deepcopy(args[1][0]['changes'])
            replace_value(args[2], 'G'*21, args[1][0]['changes'])
            with self.subTest(patch=key, value=value), self.assertRaises(CopyError): candidate(*args)
        args = json.loads(json.dumps(fixture()))
        args[1][0]['changes'][TASK]['p']['nt']['ps'].append(copy.deepcopy(args[1][0]['changes'][TASK]['p']['nt']['ps'][0]))
        args[3]['trace'][2]['value'] = copy.deepcopy(args[1][0]['changes'])
        replace_value(args[2], 'G'*21, args[1][0]['changes'])
        with self.assertRaisesRegex(CopyError, 'patch'): candidate(*args)
        # Loss of every distinct old/new carrier stays forbidden.
        for atom in H.atoms(fixture()[0]['maps']) | H.atoms([fixture()[1][0]['changes']]):
            args = json.loads(json.dumps(fixture()))
            for row in list(args[2]['raw']):
                import plistlib
                mapping = plistlib.loads(bytes.fromhex(row[2]))
                if type(mapping) is not dict: continue
                for uid, operation_ in list(mapping.items()):
                    for key, value in list(operation_['p'].items()):
                        if (uid, operation_['e'], operation_['t'], key, H.typed(value)) == atom:
                            del operation_['p'][key]
                    if not operation_['p']: del mapping[uid]
                replace_value(args[2], row[1], mapping)
            with self.subTest(lost=atom[3]), self.assertRaises(CopyError): candidate(*args)

    def test_generic_guard_stays_strict(self):
        with self.assertRaisesRegex(CopyError, 'lost new'):
            H.retain(*fixture()[:4])
