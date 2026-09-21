#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#include <dlfcn.h>
#include <sqlite3.h>
#include <sys/stat.h>
#include <unistd.h>
#include <CommonCrypto/CommonDigest.h>
#include "date_324.h"
extern void *twb_coordinator(void *);
extern void *twb_controller(void *);
static IMP stageOriginal, metadataGetOriginal, metadataSetOriginal;
static NSMutableArray *events, *metadataTrace;
static id immutableValue(id value) {
    if (!value) return NSNull.null;
    NSData *bytes=[NSJSONSerialization dataWithJSONObject:@[value] options:0 error:NULL];
    if (!bytes) [NSException raise:@"Refused" format:@"metadata value shape"];
    id result=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
    if (!result) [NSException raise:@"Refused" format:@"metadata snapshot failed"];
    return result[0];
}
static id metadataUUID(id key) {
    if (![key isKindOfClass:NSString.class]) [NSException raise:@"Refused" format:@"metadata key type"];
    Class encoder=NSClassFromString(@"BSSyncronyMetadataEncoder");
    const char *args[]={@encode(id)};
    SEL selector=requireABI(encoder,@"syncronyMetadataUUIDForKey:",@encode(id),1,args);
    id uuid=((id(*)(id,SEL,id))objc_msgSend)(encoder,selector,key);
    if (![uuid isKindOfClass:NSString.class] || ![uuid length]) [NSException raise:@"Refused" format:@"metadata UUID type"];
    return uuid;
}
static id metadataGet(id self, SEL cmd, id controller, id key) {
    id value=((id(*)(id,SEL,id,id))metadataGetOriginal)(self,cmd,controller,key);
    [metadataTrace addObject:@{@"kind":@"get",@"key":immutableValue(key),@"uuid":immutableValue(metadataUUID(key)),@"value":immutableValue(value)}];
    return value;
}
static void metadataSet(id self, SEL cmd, id controller, id value, id key) {
    // This read is observation only; the real setter is forwarded exactly once.
    id previous=((id(*)(id,SEL,id,id))metadataGetOriginal)(self,NSSelectorFromString(@"syncController:metaDataForKey:"),controller,key);
    [metadataTrace addObject:@{@"kind":@"set",@"key":immutableValue(key),@"uuid":immutableValue(metadataUUID(key)),@"before":immutableValue(previous),@"value":immutableValue(value)}];
    ((void(*)(id,SEL,id,id,id))metadataSetOriginal)(self,cmd,controller,value,key);
}
static id get(id obj, NSString *name) {
    SEL s=requireABI(obj,name,@encode(id),0,NULL);
    return ((id(*)(id,SEL))objc_msgSend)(obj,s);
}
static id objectArgument(id obj, NSString *name, id argument) {
    const char *args[]={@encode(id)};
    SEL s=requireABI(obj,name,@encode(id),1,args);
    return ((id(*)(id,SEL,id))objc_msgSend)(obj,s,argument);
}
static id openStore(Class cls, NSString *path) {
    id allocated=[cls alloc];
    const char *args[]={@encode(id),@encode(BOOL)};
    SEL s=requireABI(allocated,@"initWithDatabasePath:upgradeIfNeeded:",@encode(id),2,args);
    return ((id(*)(id,SEL,id,BOOL))objc_msgSend)(allocated,s,path,NO);
}
static void perform(id obj, NSString *name) {
    SEL s=requireABI(obj,name,@encode(void),0,NULL);
    ((void(*)(id,SEL))objc_msgSend)(obj,s);
}
static NSDictionary *map(id native) {
    if (!native) return nil;
    NSMutableDictionary *result=[NSMutableDictionary dictionary];
    id ids=get(native,@"allUUIDs");
    if (![ids conformsToProtocol:@protocol(NSFastEnumeration)]) [NSException raise:@"Refused" format:@"map IDs"];
    for (id uid in ids) {
        id op=objectArgument(native,@"operationForUUID:",uid);
        id entity=get(op,@"entityName"), properties=get(op,@"properties"), type=[op valueForKey:@"type"];
        if (![uid isKindOfClass:NSString.class] || ![entity isKindOfClass:NSString.class] || ![properties isKindOfClass:NSDictionary.class] || ![type isKindOfClass:NSNumber.class]) [NSException raise:@"Refused" format:@"map shape"];
        result[uid]=@{@"e":entity,@"t":type,@"p":properties};
    }
    if (![NSJSONSerialization isValidJSONObject:result]) [NSException raise:@"Refused" format:@"non-JSON native map"];
    NSData *bytes=[NSJSONSerialization dataWithJSONObject:result options:0 error:NULL];
    return [NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
}
static void observe(id self, SEL cmd, id changes, id base) {
    NSDictionary *actual=map(changes);
    if (!actual) [NSException raise:@"Refused" format:@"absent changes"];
    [events addObject:@{@"changes":actual,@"base":base ? map(base) : NSNull.null}];
    ((void(*)(id,SEL,id,id))stageOriginal)(self,cmd,changes,base);
}
// Exported C signatures are supported only for the pinned arm64 framework
// bytes checked by the supervisor. These are map operations, not receiver IO.
typedef void *TWBMap;
static void *mapSymbol(void *handle, const char *name) {
    void *value=dlsym(handle,name);
    if (!value) [NSException raise:@"Refused" format:@"map ABI export absent"];
    return value;
}
static id mapSnapshot(TWBMap value, CFDictionaryRef (*serialize)(TWBMap)) {
    CFDictionaryRef encoded=serialize(value);
    if (!encoded) [NSException raise:@"Refused" format:@"map serialization absent"];
    id result=immutableValue((id)encoded); CFRelease(encoded); return result;
}
static id noteWitness(NSString *frameworks, NSString *uid, id original, id prior, id event, NSString *before, NSString *after) {
    if (![original isKindOfClass:NSDictionary.class] || [original count]!=1 || ![prior isKindOfClass:NSDictionary.class] || [prior count]!=1 || !original[uid] || !prior[uid]) return nil;
    id root=original[uid][@"p"][@"nt"], intermediate=event[@"base"];
    if (![root isKindOfClass:NSDictionary.class] || ![root[@"v"] isEqual:@""] || ![intermediate isKindOfClass:NSDictionary.class] || [intermediate count]!=1 || !intermediate[uid]) return nil;
    if (![prior[uid][@"p"][@"nt"] isKindOfClass:NSDictionary.class] || ![before isKindOfClass:NSString.class] || ![after isKindOfClass:NSString.class]) return nil;
#if !defined(__arm64__)
    [NSException raise:@"Refused" format:@"unsupported map ABI architecture"];
#endif
    void *sync=dlopen([[frameworks stringByAppendingPathComponent:@"Syncrony.framework/Syncrony"] fileSystemRepresentation],RTLD_NOW|RTLD_LOCAL);
    void *model=dlopen([[frameworks stringByAppendingPathComponent:@"ThingsModel.framework/ThingsModel"] fileSystemRepresentation],RTLD_NOW|RTLD_LOCAL);
    if (!sync || !model) [NSException raise:@"Refused" format:@"map ABI framework absent"];
    TWBMap (*create)(CFDictionaryRef)=mapSymbol(sync,"SCChangeMapCreateWithPropertyList");
    CFDictionaryRef (*serialize)(TWBMap)=mapSymbol(sync,"SCChangeMapCreatePropertyListRepresentation");
    void (*stateExtend)(TWBMap,TWBMap)=mapSymbol(sync,"SCChangeMapStateExtend");
    void (*apply)(TWBMap,TWBMap)=mapSymbol(sync,"SCChangeMapStateApply");
    void (*releaseMap)(TWBMap)=mapSymbol(sync,"CCRelease");
    CFTypeRef (*normalize)(CFTypeRef)=mapSymbol(model,"THMOperationPropertyTextCreateNormalizedSet");
    NSDictionary *texts=@{@"first_before":@"",@"first_after":before,@"before":before,@"after":after};
    NSDictionary *input=@{@"original":original,@"intermediate":intermediate,@"first":prior,@"second":event[@"changes"],@"texts":texts,@"task":uid};
    TWBMap start=create((CFDictionaryRef)original), mid=create((CFDictionaryRef)intermediate), first=create((CFDictionaryRef)prior), second=create((CFDictionaryRef)event[@"changes"]);
    TWBMap rootMap=create((CFDictionaryRef)original), empty=create((CFDictionaryRef)@{}), wrong=create((CFDictionaryRef)original);
    id roundtrip=mapSnapshot(start,serialize);
    stateExtend(rootMap,mid); id extended=mapSnapshot(rootMap,serialize);
    stateExtend(empty,mid); id emptyExtended=mapSnapshot(empty,serialize);
    apply(start,first); id afterFirst=mapSnapshot(start,serialize);
    apply(start,second); id afterSecond=mapSnapshot(start,serialize);
    apply(mid,second); id fromIntermediate=mapSnapshot(mid,serialize);
    apply(wrong,second); id withoutFirst=mapSnapshot(wrong,serialize);
    NSMutableDictionary *normalized=[NSMutableDictionary dictionary];
    for (NSString *key in texts) {
        CFTypeRef v=normalize((CFTypeRef)texts[key]);
        if (!v) [NSException raise:@"Refused" format:@"normalization absent"];
        normalized[key]=immutableValue((id)v); CFRelease(v);
    }
    NSDictionary *result=@{@"roundtrip_original":roundtrip,@"extended":extended,@"empty_extended":emptyExtended,@"after_first":afterFirst,@"after_second":afterSecond,@"from_intermediate":fromIntermediate,@"without_first":withoutFirst,@"normalized":normalized};
    for (NSValue *v in @[[NSValue valueWithPointer:start],[NSValue valueWithPointer:mid],[NSValue valueWithPointer:first],[NSValue valueWithPointer:second],[NSValue valueWithPointer:rootMap],[NSValue valueWithPointer:empty],[NSValue valueWithPointer:wrong]]) releaseMap(v.pointerValue);
    return @{@"input":input,@"result":result};
}

static BOOL database29(NSString *path, NSString *descriptorPath) {
    struct stat s;
    if (lstat(path.fileSystemRepresentation,&s) || !S_ISREG(s.st_mode) || s.st_nlink!=1 || s.st_uid!=getuid()) return NO;
    NSData *bytes=[NSData dataWithContentsOfFile:descriptorPath];
    if (!bytes || bytes.length>1000000) return NO;
    unsigned char hash[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(bytes.bytes,(CC_LONG)bytes.length,hash);
    NSMutableString *digest=[NSMutableString string];
    for (unsigned i=0;i<CC_SHA256_DIGEST_LENGTH;i++) [digest appendFormat:@"%02x",hash[i]];
    if (![digest isEqual:@"380679da007e54d578e501532a258433e1d90769734a014584352ca4e4d2baab"]) return NO;
    NSDictionary *descriptor=[NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
    sqlite3 *db=NULL; sqlite3_stmt *statement=NULL;
    if (sqlite3_open_v2(path.fileSystemRepresentation,&db,SQLITE_OPEN_READONLY,NULL)!=SQLITE_OK) { if(db)sqlite3_close(db); return NO; }
    BOOL valid=NO;
    if (sqlite3_exec(db,"PRAGMA query_only=ON; BEGIN",NULL,NULL,NULL)!=SQLITE_OK) goto done;
    if (sqlite3_prepare_v2(db,"SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name",-1,&statement,NULL)!=SQLITE_OK) goto done;
    NSMutableArray *schema=[NSMutableArray array];
    int step;
    while ((step=sqlite3_step(statement))==SQLITE_ROW) {
        NSMutableArray *row=[NSMutableArray array];
        for (int i=0;i<4;i++) {
            if (sqlite3_column_type(statement,i)==SQLITE_NULL) [row addObject:NSNull.null];
            else if (sqlite3_column_type(statement,i)==SQLITE_TEXT) {
                NSString *text=[[NSString alloc] initWithBytes:sqlite3_column_text(statement,i) length:sqlite3_column_bytes(statement,i) encoding:NSUTF8StringEncoding];
                if (!text) goto done;
                [row addObject:text]; [text release];
            } else goto done;
        }
        [schema addObject:row];
    }
    sqlite3_finalize(statement); statement=NULL;
    if (step!=SQLITE_DONE || ![schema isEqual:descriptor[@"schema"]]) goto done;
    for (NSString *key in descriptor[@"headers"]) {
        NSString *sql=[@"PRAGMA " stringByAppendingString:key];
        if (sqlite3_prepare_v2(db,sql.UTF8String,-1,&statement,NULL)!=SQLITE_OK || sqlite3_step(statement)!=SQLITE_ROW) goto done;
        id value=nil;
        if(sqlite3_column_type(statement,0)==SQLITE_INTEGER) value=@(sqlite3_column_int64(statement,0));
        else if(sqlite3_column_type(statement,0)==SQLITE_TEXT) value=[NSString stringWithUTF8String:(const char *)sqlite3_column_text(statement,0)];
        if(!value || ![value isEqual:descriptor[@"headers"][key]] || sqlite3_step(statement)!=SQLITE_DONE) goto done;
        sqlite3_finalize(statement); statement=NULL;
    }
    if (sqlite3_prepare_v2(db,"SELECT value FROM Meta WHERE key='databaseVersion'",-1,&statement,NULL)==SQLITE_OK && sqlite3_step(statement)==SQLITE_ROW && (sqlite3_column_type(statement,0)==SQLITE_BLOB || sqlite3_column_type(statement,0)==SQLITE_TEXT)) {
        NSData *data=[NSData dataWithBytes:sqlite3_column_blob(statement,0) length:sqlite3_column_bytes(statement,0)];
        id v=[NSPropertyListSerialization propertyListWithData:data options:0 format:NULL error:NULL];
        valid=v && CFGetTypeID((CFTypeRef)v)==CFNumberGetTypeID() && !CFNumberIsFloatType((CFNumberRef)v) && [v longLongValue]==29 && sqlite3_step(statement)==SQLITE_DONE;
    }
 done:
    if(statement)sqlite3_finalize(statement);
    sqlite3_exec(db,"ROLLBACK",NULL,NULL,NULL); sqlite3_close(db); return valid;
}
int main(int argc, const char **argv) { @autoreleasepool { @try {
    if(argc!=4) return 2;
    NSString *database=[NSString stringWithUTF8String:argv[1]], *planPath=[NSString stringWithUTF8String:argv[2]], *descriptorPath=[NSString stringWithUTF8String:argv[3]], *app=@"/Applications/Things3.app";
    if (!database29(database,descriptorPath)) return 20;
    NSDictionary *info=[NSDictionary dictionaryWithContentsOfFile:[app stringByAppendingPathComponent:@"Contents/Info.plist"]];
    if (![info[@"CFBundleVersion"] isEqual:@"32400506"] || ![info[@"CFBundleShortVersionString"] isEqual:@"3.24"]) return 20;
    NSDictionary *plan=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:planPath] options:0 error:NULL];
    if (![plan isKindOfClass:NSDictionary.class] || plan.count!=3 || ![plan[@"changes"] isKindOfClass:NSDictionary.class]) return 21;
    NSString *frameworks=[app stringByAppendingPathComponent:@"Contents/Frameworks"];
    if (!dlopen([[frameworks stringByAppendingPathComponent:@"ThingsModel.framework/ThingsModel"] fileSystemRepresentation],RTLD_NOW|RTLD_LOCAL)) return 22;
    Class storeClass=NSClassFromString(@"_TtC11ThingsModel8THMStore");
    id store=openStore(storeClass,database);
    id task=objectArgument(store,@"taskWithUUID:",plan[@"task"]);
    if (!task || [[task valueForKey:@"type"] integerValue]!=0 || [[task valueForKey:@"status"] integerValue]!=0 || [[task valueForKey:@"trashed"] boolValue] || [[task valueForKey:@"start"] integerValue]!=1) return 23;
    for (NSString *key in @[@"stopDate",@"startDate",@"deprecated_recurrenceRule",@"deprecated_repeatingTemplate",@"objcRepeater"]) if ([task valueForKey:key]!=nil) return 24;
    Class taskClass=NSClassFromString(@"_TtC11ThingsModel7THMTask");
    SEL limitSelector=requireABI(taskClass,@"maxNotesLength",@encode(NSInteger),0,NULL);
    NSInteger maximum=((NSInteger(*)(id,SEL))objc_msgSend)(taskClass,limitSelector);
    if(maximum<=0 || maximum>10000000) return 26;
    NSDictionary *changes=plan[@"changes"];
    if (!changes.count || changes.count>2) return 27;
    for(NSString *key in changes) {
        NSString *text=changes[key];
        if (![@[@"title",@"notes"] containsObject:key] || ![text isKindOfClass:NSString.class] || [text isEqual:[task valueForKey:key]]) return 28;
        if ([key isEqual:@"notes"] && (text.length>=40000 || text.length>(NSUInteger)maximum)) return 29;
        if ([key isEqual:@"title"] && (!text.length || text.length>1000)) return 30;
    }
    id coordinator=(id)twb_coordinator((void *)store); if(!coordinator)return 31;
    id controller=(id)twb_controller((void *)coordinator);
    id history=get(controller,@"mainHistory");
    if (!history || ![[controller valueForKey:@"isConnectedToHistory"] boolValue] || [[controller valueForKey:@"schemaVersion"] integerValue]!=301) return 32;
    id historyKey=[get(controller,@"historyKey") copy];
    id historyUUID=[get(history,@"uuid") copy];
    if (![historyKey isKindOfClass:NSString.class] || ![historyKey isEqual:historyUUID]) return 32;
    Method method=class_getInstanceMethod([controller class],NSSelectorFromString(@"stage:baseStateMap:"));
    const char *stageArgs[]={@encode(id),@encode(id)};
    requireMethodABI(method,@encode(void),2,stageArgs);
    Method mg=class_getInstanceMethod([coordinator class],NSSelectorFromString(@"syncController:metaDataForKey:"));
    Method ms=class_getInstanceMethod([coordinator class],NSSelectorFromString(@"syncController:setMetaData:forKey:"));
    const char *setArgs[]={@encode(id),@encode(id),@encode(id)};
    const char *encoderArgs[]={@encode(id)};
    requireMethodABI(mg,@encode(id),2,stageArgs);
    requireMethodABI(ms,@encode(void),3,setArgs);
    requireABI(NSClassFromString(@"BSSyncronyMetadataEncoder"),@"syncronyMetadataUUIDForKey:",@encode(id),1,encoderArgs);
    // All mutation-path ABI checks precede the first model write.
    for (NSString *name in @[@"beginTransaction",@"endTransaction",@"save"])
        requireABI(store,name,@encode(void),0,NULL);
    id date=modificationDate(frameworks); // Validate boxing ABI before any write.
    NSString *beforeNotes=[[task valueForKey:@"notes"] copy];
    id prior=nil;
    if (changes[@"notes"]) {
        SEL selector=NSSelectorFromString(@"syncController:metaDataForKey:");
        id index=((id(*)(id,SEL,id,id))objc_msgSend)(coordinator,selector,controller,[historyKey stringByAppendingString:@"-IndexOfLastLocalItem-Item-1"]);
        if (index && CFGetTypeID((CFTypeRef)index)==CFNumberGetTypeID() && !CFNumberIsFloatType((CFNumberRef)index) && [index longLongValue]>0) {
            NSString *key=[NSString stringWithFormat:@"%@-LocalTimeline-Item-%lld",historyKey,[index longLongValue]];
            prior=immutableValue(((id(*)(id,SEL,id,id))objc_msgSend)(coordinator,selector,controller,key));
        }
    }
    events=[NSMutableArray new]; metadataTrace=[NSMutableArray new];
    metadataGetOriginal=method_setImplementation(mg,(IMP)metadataGet);
    metadataSetOriginal=method_setImplementation(ms,(IMP)metadataSet);
    stageOriginal=method_setImplementation(method,(IMP)observe);
    @try {
        perform(store,@"beginTransaction");
        for(NSString *key in changes) [task setValue:changes[key] forKey:key];
        [task setValue:date forKey:@"userModificationDate"];
        perform(store,@"endTransaction"); perform(store,@"save");
    } @finally {
        method_setImplementation(method,stageOriginal);
        method_setImplementation(mg,metadataGetOriginal);
        method_setImplementation(ms,metadataSetOriginal);
    }
    id historyKeyAfter=get(controller,@"historyKey"), historyUUIDAfter=get(get(controller,@"mainHistory"),@"uuid");
    if (events.count!=1 || metadataTrace.count!=5 || [[store valueForKey:@"hasTransactionChanges"] boolValue] || ![historyKeyAfter isEqual:historyKey] || ![historyUUIDAfter isEqual:historyUUID]) return 35;
    NSDictionary *metadata=@{@"build":@"32400506",@"schema":@301,@"history_key":historyKey,@"history_uuid":historyUUID,@"history_key_after":historyKeyAfter,@"history_uuid_after":historyUUIDAfter,@"trace":metadataTrace};
    NSMutableDictionary *proof=[NSMutableDictionary dictionaryWithDictionary:@{@"events":events,@"max_notes_length":@(maximum),@"schema_version":@301,@"history_connected":@YES,@"metadata":metadata}];
    if (changes[@"notes"]) {
        id witness=noteWitness(frameworks,plan[@"task"],metadataTrace[0][@"value"],prior,events[0],beforeNotes,[task valueForKey:@"notes"]);
        if (witness) proof[@"note_witness"]=witness;
    }
    [beforeNotes release];
    NSData *output=[NSJSONSerialization dataWithJSONObject:proof options:NSJSONWritingSortedKeys error:NULL];
    if (!output) return 36;
    fwrite(output.bytes,1,output.length,stdout); fputc('\n',stdout);
    return 0;
} @catch(NSException *exception) { (void)exception; fprintf(stderr,"native copy refused\n"); return 70; } } }
