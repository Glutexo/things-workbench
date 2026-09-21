"""Synthetic refusal controls. These do not assert native acceptance."""
from contextlib import closing
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import unittest
from things_workbench import copies, wording

class CopyRefusalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.source=self.root/'input.sqlite'
        with closing(sqlite3.connect(self.source)) as c: c.execute('CREATE TABLE t(a)')
        self.source.chmod(0o600)

    def test_known_quarantined_parent_is_not_an_import_source(self):
        (self.root/'failed.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'quarantined'):
            copies.import_copy(self.source,self.root/'imported',declaration='detached-stable-resolved')

    def test_symlink_hardlink_fifo_and_sidecar_aliases(self):
        link=self.root/'link.sqlite'; link.symlink_to(self.source)
        with self.assertRaises(ValueError): copies.detached(link)
        link.unlink(); os.link(self.source,link)
        with self.assertRaises(ValueError): copies.detached(self.source)
        link.unlink(); os.mkfifo(link)
        with self.assertRaises(ValueError): copies.detached(link)
        link.unlink(); side=Path(str(self.source)+'-wal'); side.symlink_to(self.source)
        with self.assertRaises(ValueError): copies.detached(self.source)

    def test_wal_and_unknown_declaration_refused(self):
        side=Path(str(self.source)+'-wal'); side.write_bytes(b'active'); side.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'detached'): copies.detached(self.source)
        with self.assertRaisesRegex(ValueError,'declaration'): copies.import_copy(self.source,self.root/'copy',declaration='unknown')

    def test_replaced_inode_and_double_lock_refused(self):
        p=copies.import_copy(self.source,self.root/'copy',declaration='detached-stable-resolved')
        with copies.lock(p.parent):
            with self.assertRaisesRegex(ValueError,'busy'):
                with copies.lock(p.parent): pass
        data=p.read_bytes(); p.unlink(); p.write_bytes(data); p.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'drift'): copies.verify_copy(p.parent)

    def test_duplicate_manifest_keys_refused(self):
        p=self.root/'record.json'; p.write_text('{"state":1,"state":2}'); p.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'duplicate'): copies.load(p)

class TargetRefusalTests(unittest.TestCase):
    def test_trigger_refused_before_runtime_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); p=root/'input.sqlite'; uid='A'*22
            with closing(sqlite3.connect(p)) as c:
                c.executescript('CREATE TABLE Meta(key,value); CREATE TABLE TMTask(uuid,title,notes,type,status,trashed,start,startDate,stopDate,repeater,rt1_recurrenceRule,rt1_repeatingTemplate); CREATE TRIGGER unexpected AFTER UPDATE ON TMTask BEGIN SELECT 1; END;')
                c.execute('INSERT INTO Meta VALUES (?,?)',('databaseVersion',plistlib.dumps(29)))
                c.execute('INSERT INTO TMTask VALUES (?,?,?,0,0,0,1,NULL,NULL,NULL,NULL,NULL)',(uid,'title','notes')); c.commit()
            p.chmod(0o600)
            owned=copies.import_copy(p,root/'import',declaration='detached-stable-resolved')
            with self.assertRaisesRegex(ValueError,'unsupported schema'):
                wording.prepare(owned.parent,{'version':1,'task':uid,'changes':{'title':'new'}},root/'packet',root/'missing-runtime')
            self.assertFalse((root/'packet').exists())

    def test_unsupported_states_and_noop(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'input.sqlite'; uid='A'*22
            with closing(sqlite3.connect(p)) as c:
                c.executescript('CREATE TABLE Meta(key,value); CREATE TABLE TMTask(uuid,title,notes,type,status,trashed,start,startDate,stopDate,repeater,rt1_recurrenceRule,rt1_repeatingTemplate);')
                c.execute('INSERT INTO Meta VALUES (?,?)',('databaseVersion',plistlib.dumps(29)))
                c.execute('INSERT INTO TMTask VALUES (?,?,?,0,0,0,1,NULL,NULL,NULL,NULL,NULL)',(uid,'title','notes'));c.commit()
            p.chmod(0o600)
            plan={'version':1,'task':uid,'changes':{'title':'new'}}
            self.assertEqual(wording.target(p,plan)[1],plan)
            with self.assertRaisesRegex(ValueError,'no-op'): wording.target(p,{**plan,'changes':{'title':'title'}})
            for key,bad in [('type',1),('type',2),('status',3),('trashed',1),('start',0),('start',2),('startDate',1),('stopDate',1),('repeater','x'),('rt1_recurrenceRule','x'),('rt1_repeatingTemplate','x')]:
                with closing(sqlite3.connect(p)) as c:
                    old=c.execute('SELECT '+key+' FROM TMTask').fetchone()[0]
                    c.execute('UPDATE TMTask SET '+key+'=?',(bad,));c.commit()
                with self.subTest(field=key,value=bad),self.assertRaisesRegex(ValueError,'target state'): wording.target(p,plan)
                with closing(sqlite3.connect(p)) as c: c.execute('UPDATE TMTask SET '+key+'=?',(old,));c.commit()
