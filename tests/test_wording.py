"""Synthetic plan validation, with no native invocation."""
import importlib.util
import json
import unittest

class PlanTests(unittest.TestCase):
    def test_strict_wording_plan(self):
        self.assertIsNotNone(importlib.util.find_spec('things_workbench.wording'), 'wording missing')
        from things_workbench.wording import parse_plan
        uid = 'A' * 22
        valid = {'version':1,'task':uid,'changes':{'notes':'e\u0301\r\n😀'}}
        self.assertEqual(parse_plan(json.dumps(valid)), valid)
        self.assertEqual(parse_plan(json.dumps({**valid,'changes':{'notes':''}}))['changes']['notes'],'')
        invalid = [
            {**valid,'task':uid+' '}, {**valid,'version':True}, {**valid,'extra':0},
            {**valid,'changes':{}}, {**valid,'changes':{'title':''}},
            {**valid,'changes':{'notes':None}}, {**valid,'changes':{'status':1}},
            {**valid,'changes':{'notes':'x'*40000}}, {**valid,'changes':{'notes':'😀'*20000}},
            {**valid,'changes':{'title':'x'*1001}}, {**valid,'changes':{'notes':'\ud800'}},
            {**valid,'changes':{'notes':'a\x00b'}},
        ]
        for plan in invalid:
            with self.subTest(plan_kind=list(plan['changes'])):
                with self.assertRaises(ValueError): parse_plan(json.dumps(plan))
        with self.assertRaises(ValueError): parse_plan('{"version":1,"version":1}')
        self.assertEqual(len(parse_plan(json.dumps({**valid,'changes':{'notes':'x'*39999}}))['changes']['notes']),39999)
