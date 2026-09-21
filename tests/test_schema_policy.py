"""Known physical schema only. Fixtures contain no application row payloads."""
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import subprocess
import sys
import unittest

from things_workbench.copies import CopyError
from importlib.resources import files

NATIVE = Path(str(files('things_workbench').joinpath('native')))


def schema_fixture(path, mutate=None):
    descriptor = json.loads((NATIVE/'schema_32400506.json').read_text())
    objects = [dict(zip(('type','name','tbl_name','sql'), row)) for row in descriptor['schema']]
    with closing(sqlite3.connect(path)) as c:
        for kind in ('table', 'index'):
            for item in objects:
                if item['type'] == kind and item['sql'] is not None and not item['name'].startswith('sqlite_'):
                    sql = item['sql']
                    if mutate is not None: sql = mutate(item['name'], sql)
                    c.execute(sql)
        c.execute('INSERT INTO Meta(key,value) VALUES (?,?)', ('databaseVersion', plistlib.dumps(29)))
        c.commit()
    os.chmod(path, 0o600)
    return path


class SchemaPolicyTests(unittest.TestCase):
    def test_xml_text_storage_preserves_strict_integer_version(self):
        from things_workbench.schema_policy import verify_schema
        with tempfile.TemporaryDirectory() as tmp:
            path = schema_fixture(Path(tmp).resolve()/'synthetic.sqlite')
            for value in (29, True, 29.0, '29', 30):
                with closing(sqlite3.connect(path)) as db:
                    db.execute('UPDATE Meta SET value=? WHERE key=?',
                               (plistlib.dumps(value).decode('utf-8'), 'databaseVersion'))
                    db.commit()
                with self.subTest(plist_type=type(value).__name__):
                    if type(value) is int and value == 29:
                        self.assertEqual(len(verify_schema(path)), 64)
                    else:
                        with self.assertRaises(CopyError): verify_schema(path)

    def test_reviewed_schema_accepts_without_binding_cookie_or_rootpages(self):
        self.assertIsNotNone(importlib.util.find_spec('things_workbench.schema_policy'), 'known-schema gate must exist')
        policy = importlib.import_module('things_workbench.schema_policy')
        with tempfile.TemporaryDirectory() as tmp:
            path = schema_fixture(Path(tmp).resolve() / 'synthetic.sqlite')
            digest = policy.verify_schema(path)
            self.assertEqual(len(digest), 64)
            with closing(sqlite3.connect(path)) as c:
                c.execute('PRAGMA schema_version=172')
                c.execute('VACUUM')
            self.assertEqual(policy.verify_schema(path), digest)

    def test_bad_database_version_is_always_copy_error(self):
        from things_workbench.schema_policy import verify_schema
        for value in (True, 29.0, '29', 30, b'<?xml version="1.0"?><plist><broken>'):
            with self.subTest(value_type=type(value).__name__), tempfile.TemporaryDirectory() as tmp:
                path = schema_fixture(Path(tmp).resolve()/'synthetic.sqlite')
                blob = value if type(value) is bytes else plistlib.dumps(value)
                with closing(sqlite3.connect(path)) as c:
                    c.execute('UPDATE Meta SET value=? WHERE key=?', (blob,'databaseVersion')); c.commit()
                with self.assertRaises(CopyError): verify_schema(path)

    def test_unknown_ddl_and_header_refused(self):
        from things_workbench.schema_policy import verify_schema
        mutations = ['CREATE TABLE Unexpected(x TEXT)', 'ALTER TABLE BSSyncronyMetadata ADD COLUMN opaque BLOB', 'DROP INDEX index_TMTask_area', 'CREATE INDEX UnexpectedIndex ON TMTask(title)', 'CREATE TRIGGER Unexpected AFTER INSERT ON Meta BEGIN SELECT 1; END', 'PRAGMA user_version=1', 'PRAGMA application_id=99']
        for sql in mutations:
            with self.subTest(sql=sql), tempfile.TemporaryDirectory() as tmp:
                path = schema_fixture(Path(tmp).resolve() / 'synthetic.sqlite')
                with closing(sqlite3.connect(path)) as c: c.executescript(sql)
                with self.assertRaises(CopyError): verify_schema(path)
        for replacement in ('TEXT', 'BLOB DEFAULT 1', 'BLOB NOT NULL', 'BLOB REFERENCES Meta(key)'):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                path = schema_fixture(Path(tmp).resolve() / 'synthetic.sqlite', lambda name, sql: sql.replace('BLOB', replacement) if name == 'BSSyncronyMetadata' else sql)
                with self.assertRaises(CopyError): verify_schema(path)


@unittest.skipUnless(sys.platform == 'darwin', 'Objective-C runtime probe requires macOS')
class NativeABIProbeTests(unittest.TestCase):
    def test_metadata_observers_forward_once_and_capture_immutable_values(self):
        native = NATIVE
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            source = tmp / 'observer_probe.m'
            source.write_text(r'''
#define main unused_writer_main
#include "wording.m"
#undef main
void *twb_coordinator(void *p) { (void)p; return NULL; }
void *twb_controller(void *p) { (void)p; return NULL; }
@interface BSSyncronyMetadataEncoder : NSObject
+ (id)syncronyMetadataUUIDForKey:(id)key;
@end
@implementation BSSyncronyMetadataEncoder
+ (id)syncronyMetadataUUIDForKey:(id)key { (void)key; return @"CCCCCCCCCCCCCCCCCCCCC"; }
@end
static int getCalls, sets;
static id originalGet(id self, SEL cmd, id controller, id key) {
    (void)self; (void)cmd; (void)controller; (void)key; getCalls++; return nil;
}
static void originalSet(id self, SEL cmd, id controller, id value, id key) {
    (void)self; (void)cmd; (void)controller; (void)key; sets++; [value removeAllObjects];
}
int main(void) { @autoreleasepool {
    metadataTrace=[NSMutableArray new];
    metadataGetOriginal=(IMP)originalGet; metadataSetOriginal=(IMP)originalSet;
    NSMutableDictionary *value=[@{@"synthetic":@1} mutableCopy];
    metadataGet(nil,NULL,nil,@"synthetic-key");
    metadataSet(nil,NULL,nil,value,@"synthetic-key");
    if (getCalls!=2 || sets!=1 || metadataTrace.count!=2) return 1;
    if (metadataTrace[0][@"value"]!=NSNull.null || metadataTrace[1][@"before"]!=NSNull.null) return 2;
    if (![metadataTrace[1][@"value"] isEqual:@{@"synthetic":@1}] || value.count) return 3;
    return 0;
}}
''')
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp), 'TMPDIR': str(tmp)}
            build = subprocess.run(['/usr/bin/xcrun', 'clang', '-Wall', '-Wextra', '-Werror', '-I', str(native), str(source), '-framework', 'Foundation', '-lsqlite3', '-o', str(tmp/'probe')], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(subprocess.run([str(tmp/'probe')], env=env, timeout=10).returncode, 0)

    def test_typed_private_call_signature_matrix(self):
        native = NATIVE
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            source = tmp / 'signature_probe.m'
            source.write_text(r'''
#define main unused_writer_main
#include "wording.m"
#undef main
void *twb_coordinator(void *p) { (void)p; return NULL; }
void *twb_controller(void *p) { (void)p; return NULL; }
static int calls;
@interface Wrong : NSObject
- (id)initWithDatabasePath:(id)p upgradeIfNeeded:(NSInteger)b;
- (NSInteger)taskWithUUID:(id)p;
- (id)operationForUUID:(NSInteger)p;
- (NSInteger)objectValue;
- (NSInteger)syncController:(id)c metaDataForKey:(id)k;
- (id)syncController:(id)c setMetaData:(id)v forKey:(id)k;
- (id)stage:(id)c baseStateMap:(id)b;
+ (id)maxNotesLength;
+ (id)valueWithFADate:(double)d;
+ (NSInteger)syncronyMetadataUUIDForKey:(id)k;
@end
@implementation Wrong
- (id)initWithDatabasePath:(id)p upgradeIfNeeded:(NSInteger)b { (void)p; (void)b; calls++; return self; }
- (NSInteger)taskWithUUID:(id)p { (void)p; calls++; return 0; }
- (id)operationForUUID:(NSInteger)p { (void)p; calls++; return self; }
- (NSInteger)objectValue { calls++; return 0; }
- (NSInteger)syncController:(id)c metaDataForKey:(id)k { (void)c; (void)k; calls++; return 0; }
- (id)syncController:(id)c setMetaData:(id)v forKey:(id)k { (void)c; (void)v; (void)k; calls++; return self; }
- (id)stage:(id)c baseStateMap:(id)b { (void)c; (void)b; calls++; return self; }
+ (id)maxNotesLength { calls++; return nil; }
+ (id)valueWithFADate:(double)d { (void)d; calls++; return nil; }
+ (NSInteger)syncronyMetadataUUIDForKey:(id)k { (void)k; calls++; return 0; }
@end
#define REFUSES(expr) do { BOOL rejected=NO; @try { expr; } @catch(NSException *e) { (void)e; rejected=YES; } if (!rejected || calls) return __LINE__; } while(0)
int main(void) { @autoreleasepool {
    Wrong *obj=[Wrong new];
    const char *one[]={@encode(id)}, *two[]={@encode(id),@encode(id)}, *three[]={@encode(id),@encode(id),@encode(id)}, *date[]={@encode(TWBDate)};
    REFUSES(openStore(Wrong.class,@"synthetic"));
    REFUSES(objectArgument(obj,@"taskWithUUID:",@"synthetic"));
    REFUSES(objectArgument(obj,@"operationForUUID:",@"synthetic"));
    REFUSES(get(obj,@"objectValue"));
    REFUSES(requireABI(Wrong.class,@"maxNotesLength",@encode(NSInteger),0,NULL));
    REFUSES(requireABI(Wrong.class,@"valueWithFADate:",@encode(id),1,date));
    REFUSES(requireABI(Wrong.class,@"syncronyMetadataUUIDForKey:",@encode(id),1,one));
    REFUSES(requireMethodABI(class_getInstanceMethod(Wrong.class,NSSelectorFromString(@"syncController:metaDataForKey:")),@encode(id),2,two));
    REFUSES(requireMethodABI(class_getInstanceMethod(Wrong.class,NSSelectorFromString(@"syncController:setMetaData:forKey:")),@encode(void),3,three));
    REFUSES(requireMethodABI(class_getInstanceMethod(Wrong.class,NSSelectorFromString(@"stage:baseStateMap:")),@encode(void),2,two));
    return 0;
}}
''')
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp), 'TMPDIR': str(tmp)}
            build = subprocess.run(['/usr/bin/xcrun', 'clang', '-Wall', '-Wextra', '-Werror', '-I', str(native), str(source), '-framework', 'Foundation', '-lsqlite3', '-o', str(tmp/'probe')], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(subprocess.run([str(tmp/'probe')], env=env, timeout=10).returncode, 0)

    def test_native_known_schema_refuses_extra_column(self):
        native = NATIVE
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            source = tmp / 'schema_probe.m'
            source.write_text(r'''
#define main unused_writer_main
#include "wording.m"
#undef main
void *twb_coordinator(void *p) { (void)p; return NULL; }
void *twb_controller(void *p) { (void)p; return NULL; }
int main(int argc, const char **argv) { @autoreleasepool {
    if(argc!=3) return 2;
    return database29([NSString stringWithUTF8String:argv[1]], [NSString stringWithUTF8String:argv[2]]) ? 0 : 20;
}}
''')
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp), 'TMPDIR': str(tmp)}
            build = subprocess.run(['/usr/bin/xcrun', 'clang', '-Wall', '-Wextra', '-Werror', '-I', str(native), str(source), '-framework', 'Foundation', '-lsqlite3', '-o', str(tmp/'probe')], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            path = schema_fixture(tmp/'synthetic.sqlite')
            argv = [str(tmp/'probe'), str(path), str(native/'schema_32400506.json')]
            self.assertEqual(subprocess.run(argv, env=env, timeout=10).returncode, 0)
            for value in (29, True, 29.0, '29', 30):
                with closing(sqlite3.connect(path)) as db:
                    db.execute('UPDATE Meta SET value=? WHERE key=?',
                               (plistlib.dumps(value).decode('utf-8'), 'databaseVersion'))
                    db.commit()
                expected = 0 if type(value) is int and value == 29 else 20
                with self.subTest(text_plist_type=type(value).__name__):
                    self.assertEqual(subprocess.run(argv, env=env, timeout=10).returncode, expected)
            with closing(sqlite3.connect(path)) as db:
                db.execute('UPDATE Meta SET value=? WHERE key=?', (plistlib.dumps(29), 'databaseVersion'))
                db.commit()
            with closing(sqlite3.connect(path)) as c: c.execute('ALTER TABLE BSSyncronyMetadata ADD COLUMN opaque BLOB')
            self.assertEqual(subprocess.run(argv, env=env, timeout=10).returncode, 20)

    def test_wrong_void_method_refuses_before_invocation(self):
        native = NATIVE
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            source = tmp / 'probe.m'
            source.write_text(r'''
#define main unused_writer_main
#include "wording.m"
#undef main
void *twb_coordinator(void *p) { (void)p; return NULL; }
void *twb_controller(void *p) { (void)p; return NULL; }
static int calls;
@interface Wrong : NSObject
- (id)save;
@end
@implementation Wrong
- (id)save { calls++; return self; }
@end
int main(void) { @autoreleasepool {
    @try { perform([Wrong new], @"save"); }
    @catch(NSException *e) { (void)e; return calls ? 2 : 0; }
    return 1;
}}
''')
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp), 'TMPDIR': str(tmp)}
            build = subprocess.run(['/usr/bin/xcrun', 'clang', '-Wall', '-Wextra', '-Werror', '-I', str(native), str(source), '-framework', 'Foundation', '-lsqlite3', '-o', str(tmp/'probe')], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(tmp/'probe')], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, 'wrong ABI must refuse without entering method')
