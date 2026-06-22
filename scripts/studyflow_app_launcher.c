#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static char *parent_dir(char *path) {
    return dirname(path);
}

int main(void) {
    char executable_path[PATH_MAX];
    uint32_t size = sizeof(executable_path);
    if (_NSGetExecutablePath(executable_path, &size) != 0) {
        return 1;
    }

    char resolved_path[PATH_MAX];
    if (realpath(executable_path, resolved_path) == NULL) {
        strncpy(resolved_path, executable_path, sizeof(resolved_path) - 1);
        resolved_path[sizeof(resolved_path) - 1] = '\0';
    }

    char root_path[PATH_MAX];
    strncpy(root_path, resolved_path, sizeof(root_path) - 1);
    root_path[sizeof(root_path) - 1] = '\0';

    // /Project/StudyFlow.app/Contents/MacOS/StudyFlow -> /Project
    for (int i = 0; i < 4; i++) {
        char *parent = parent_dir(root_path);
        if (parent == NULL) {
            return 1;
        }
        memmove(root_path, parent, strlen(parent) + 1);
    }

    char launcher_path[PATH_MAX];
    int written = snprintf(
        launcher_path,
        sizeof(launcher_path),
        "%s/scripts/studyflow_mac_launcher.sh",
        root_path
    );
    if (written < 0 || written >= (int)sizeof(launcher_path)) {
        return 1;
    }

    execl(launcher_path, launcher_path, (char *)NULL);
    return 1;
}
