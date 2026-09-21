// Original minimal ABI checks: exact encodings, no coercing casts.
static void signatureABI(NSMethodSignature *signature, const char *result,
                         NSUInteger count, const char *const *arguments) {
    if (!signature || signature.numberOfArguments != count+2 ||
        strcmp(signature.methodReturnType, result) ||
        strcmp([signature getArgumentTypeAtIndex:0], @encode(id)) ||
        strcmp([signature getArgumentTypeAtIndex:1], @encode(SEL)))
        [NSException raise:@"Refused" format:@"method ABI"];
    for (NSUInteger i=0; i<count; i++)
        if (strcmp([signature getArgumentTypeAtIndex:i+2], arguments[i]))
            [NSException raise:@"Refused" format:@"argument ABI"];
}
static SEL requireABI(id receiver, NSString *name, const char *result,
                      NSUInteger count, const char *const *arguments) {
    SEL selector = NSSelectorFromString(name);
    signatureABI([receiver methodSignatureForSelector:selector], result, count, arguments);
    return selector;
}
static void requireMethodABI(Method method, const char *result,
                             NSUInteger count, const char *const *arguments) {
    if (!method) [NSException raise:@"Refused" format:@"missing method"];
    signatureABI([NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(method)],
                 result, count, arguments);
}

// Original minimal declaration for the verified build's one-double FADate ABI.
typedef struct { double value; } TWBDate;
_Static_assert(sizeof(TWBDate) == 8, "FADate ABI");
static id modificationDate(NSString *frameworks) {
    NSString *path = [frameworks stringByAppendingPathComponent:@"FoundationAdditions.framework/FoundationAdditions"];
    void *library = dlopen(path.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
    TWBDate (*make)(double) = library ? dlsym(library, "FADateMakeWithTimeIntervalSince1970") : NULL;
    Class cls = NSClassFromString(@"FADateValue");
    if (!make) [NSException raise:@"Refused" format:@"date symbol ABI"];
    const char *arguments[]={@encode(TWBDate)};
    SEL selector=requireABI(cls,@"valueWithFADate:",@encode(id),1,arguments);
    return ((id(*)(id,SEL,TWBDate))objc_msgSend)(cls,selector,make(NSDate.date.timeIntervalSince1970));
}
