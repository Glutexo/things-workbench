"""Synthetic atom semantics; native carriers are tested separately."""
import copy
import unittest
from things_workbench.copies import CopyError
from things_workbench.history import atoms, retain, typed
from test_metadata_stage import fixture, inventory, OLD, LOCAL, TIMELINE, replace_value

U='A'*22
V='B'*22


def op(value, entity='Task7', kind=1):
    return {'e':entity,'t':kind,'p':{'nt':value}}


class HistoryTests(unittest.TestCase):
    def test_malformed_operation_id_refused(self):
        with self.assertRaisesRegex(ValueError,'history'):
            atoms([{'invalid':op('value')}])

    def test_distinct_values_bases_and_duplicates(self):
        maps=[{U:op({'v':1,'text':'old'})},{V:op('unrelated')}]
        self.assertEqual(atoms(maps),atoms(list(reversed(maps))+maps))
        for change in (op('extra',kind=True),{'e':'Task7','t':1,'p':{}}):
            with self.assertRaises(CopyError): atoms([{U:change}])
        self.assertNotEqual(typed(True),typed(1))
        self.assertNotEqual(typed(1.0),typed(1))

    def test_metadata_binding_is_required_not_an_optional_relaxation(self):
        before, events, after, metadata = fixture()
        with self.assertRaises(TypeError): retain(before,events,after)
        with self.assertRaises(CopyError): retain(before,events,after,{})
        self.assertTrue(retain(before,events,after,metadata)['complete'])
