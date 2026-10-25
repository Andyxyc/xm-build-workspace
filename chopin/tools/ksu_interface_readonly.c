/* SPDX-License-Identifier: GPL-2.0 */
/* Read-only real ABI queries. No feature toggles, module loads or reboot. */
#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "uapi/supercall.h"
#include "uapi/extension.h"
#include "../susfs_typed_abi.h"

_Static_assert(sizeof(struct chopin_susfs_kstat) == 376, "typed kstat size");
_Static_assert(offsetof(struct chopin_susfs_kstat, err) == 372, "typed kstat err");
_Static_assert(sizeof(struct chopin_susfs_redirect) == 520, "typed redirect size");
_Static_assert(offsetof(struct chopin_susfs_uname, err) == 132, "typed uname err");

static int read_feature(int fd, unsigned id, const char *name)
{
    struct ksu_get_feature_cmd feature = {.feature_id=id};
    int result = ioctl(fd, KSU_IOCTL_GET_FEATURE, &feature);
    printf("feature %s id=%u ioctl=%d errno=%d supported=%u value=%llu\n",
           name, id, result, result < 0 ? errno : 0, feature.supported,
           (unsigned long long)feature.value);
    return result < 0 || !(feature.supported & KSU_FEATURE_FLAG_SUPPORTED);
}

int main(void)
{
    int fd = -1, failed = 0, result = -EINPROGRESS;
    struct ksu_get_info_cmd info = {0};
    struct chopin_susfs_version version = {.err=126};
    struct chopin_susfs_variant variant = {.err=126};
    struct chopin_susfs_features features = {.err=126};
    char kpm_version[1024] = {0};
    struct ksu_kpm_cmd kpm = {SUKISU_KPM_VERSION, (uintptr_t)kpm_version,
                              sizeof(kpm_version), (uintptr_t)&result};
    struct ksu_extension_cmd extension = {.id=KSU_EXTENSION_KPM,
        .op=KSU_EXTENSION_IO, .user_ptr=(uintptr_t)&kpm};
    long call;

    if (geteuid() != 0) {
        fputs("Root required; no automatic grant attempted\n", stderr);
        return 2;
    }
    call = syscall(SYS_reboot, KSU_INSTALL_MAGIC1, KSU_INSTALL_MAGIC2, 0, &fd);
    if (call < 0 || fd < 0) {
        fprintf(stderr, "driver fd error: syscall=%ld errno=%d fd=%d\n", call, errno, fd);
        return 1;
    }
    if (ioctl(fd, KSU_IOCTL_GET_INFO, &info) < 0) {
        close(fd);
        return 1;
    }
    printf("driver version=%u uapi=%u flags=%u mode=%s\n", info.version,
           info.uapi_version, info.flags, info.flags & KSU_GET_INFO_FLAG_LKM ? "LKM" : "Built-in");
    failed |= read_feature(fd, 4, "selinux_hide");
    failed |= read_feature(fd, 10003, "avc_spoof");
    if (ioctl(fd, KSU_IOCTL_EXTENSION, &extension) < 0)
        result = -errno;
    printf("KPM VERSION capacity=1024 result=%d value=%.*s\n", result,
           (int)sizeof(kpm_version), kpm_version);
    failed |= result != 0 || !kpm_version[0] ||
              !memchr(kpm_version, 0, sizeof(kpm_version));

    call = syscall(SYS_reboot, 0xDEADBEEFu, 0xFAFAFAFAu, 0x555e1u, &version);
    printf("SUSFS typed version syscall=%ld err=%d value=%.*s\n", call,
           version.err, (int)sizeof(version.value), version.value);
    failed |= call < 0 || version.err || version.value[0] != 'v';
    call = syscall(SYS_reboot, 0xDEADBEEFu, 0xFAFAFAFAu, 0x555e3u, &variant);
    printf("SUSFS typed variant syscall=%ld err=%d value=%.*s\n", call,
           variant.err, (int)sizeof(variant.value), variant.value);
    failed |= call < 0 || variant.err || !variant.value[0];
    call = syscall(SYS_reboot, 0xDEADBEEFu, 0xFAFAFAFAu, 0x555e2u, &features);
    printf("SUSFS typed features syscall=%ld err=%d value=\n%.*s\n", call,
           features.err, (int)sizeof(features.value), features.value);
    failed |= call < 0 || features.err || !features.value[0];
    close(fd);
    return failed ? 1 : 0;
}
