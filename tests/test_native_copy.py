"""Opt-in genuine native-copy test. Never discovers or captures live data."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import unittest

@unittest.skipUnless(os.environ.get('TWB_NATIVE_INPUT') and os.environ.get('TWB_NATIVE_RUN'), 'explicit private native fixture required')
class NativeCopyTests(unittest.TestCase):
    def test_native_title_prepare_preview_apply_copy(self):
        from things_workbench import wording
        self.assertTrue(hasattr(wording,'prepare'), 'native prepare not implemented')
        from things_workbench.copies import import_copy, identity
        from things_workbench.native_runtime import build
        root = Path(os.environ['TWB_NATIVE_RUN'])
        root.mkdir(mode=0o700)
        source = Path(os.environ['TWB_NATIVE_INPUT'])
        initial = identity(source)
        owned = import_copy(source, root / 'import', declaration='detached-stable-resolved')
        with closing(sqlite3.connect(owned.as_uri()+'?mode=ro',uri=True)) as c:
            task = c.execute('SELECT uuid,title FROM TMTask WHERE type=0 AND status=0 AND trashed=0 AND stopDate IS NULL AND repeater IS NULL AND rt1_recurrenceRule IS NULL AND rt1_repeatingTemplate IS NULL AND start=1 AND startDate IS NULL ORDER BY uuid LIMIT 1').fetchone()
        self.assertIsNotNone(task, 'fixture lacks eligible target')
        runtime = build(Path(os.environ.get('TWB_NATIVE_APP','/Applications/Things3.app')), root / 'runtime')
        plan = {'version':1,'task':task[0],'changes':{'title':task[1]+' [copy-only test]'}}
        packet = wording.prepare(owned.parent, plan, root / 'packet', runtime)
        preview = wording.preview(packet)
        self.assertEqual(preview['after']['title'], plan['changes']['title'])
        self.assertTrue(preview['history_verified'])
        result = wording.apply_copy(packet, preview['approval_digest'])
        self.assertEqual(identity(source),initial)
        with closing(sqlite3.connect(result.as_uri()+'?mode=ro',uri=True)) as c:
            self.assertEqual(c.execute('SELECT title FROM TMTask WHERE uuid=?',(task[0],)).fetchone()[0],plan['changes']['title'])
        with self.assertRaises(ValueError): wording.apply_copy(packet,preview['approval_digest'])
