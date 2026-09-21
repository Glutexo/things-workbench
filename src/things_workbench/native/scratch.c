// This helper-local dyld interpose entry redirects only its private temp path.
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
static size_t private_temp_confstr(int name, char *buffer, size_t capacity) {
    const char *directory = getenv("TWB_SCRATCH_DIRECTORY");
    if (name != _CS_DARWIN_USER_TEMP_DIR || !directory || !directory[0])
        return confstr(name, buffer, capacity);
    if (buffer && capacity) strlcpy(buffer, directory, capacity);
    return strlen(directory) + 1;
}
__attribute__((used, section("__DATA,__interpose")))
static const struct { const void *new_address; const void *old_address; } temp_redirect = {
    (const void *)&private_temp_confstr, (const void *)&confstr
};
