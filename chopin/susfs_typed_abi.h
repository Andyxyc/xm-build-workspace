/* SPDX-License-Identifier: GPL-3.0-only */
/* Fixed-width ABI from official SukiSU v4.2.1-r2 ksud susfs/abi/types.rs. */
#ifndef CHOPIN_SUSFS_TYPED_ABI_H
#define CHOPIN_SUSFS_TYPED_ABI_H
#include <linux/types.h>

struct chopin_susfs_version { char value[16]; __s32 err; };
struct chopin_susfs_variant { char value[16]; __s32 err; };
struct chopin_susfs_features { char value[8192]; __s32 err; };
struct chopin_susfs_uname { char release[65]; char version[65]; __s32 err; };
struct chopin_susfs_toggle { __u32 enabled; __s32 err; };
struct chopin_susfs_path { char target_pathname[256]; __s32 err; };
struct chopin_susfs_redirect {
    char target_pathname[256];
    char redirected_pathname[256];
    __u32 uid_scheme;
    __s32 err;
};
struct chopin_susfs_kstat {
    __u32 is_statically;
    __aligned_u64 target_ino;
    char target_pathname[256];
    __aligned_u64 spoofed_ino;
    __aligned_u64 spoofed_dev;
    __u32 spoofed_nlink;
    __aligned_u64 spoofed_size;
    __aligned_s64 spoofed_atime_tv_sec;
    __aligned_u64 spoofed_atime_tv_nsec;
    __aligned_s64 spoofed_mtime_tv_sec;
    __aligned_u64 spoofed_mtime_tv_nsec;
    __aligned_s64 spoofed_ctime_tv_sec;
    __aligned_u64 spoofed_ctime_tv_nsec;
    __aligned_u64 spoofed_blocks;
    __aligned_s64 spoofed_blksize;
    __u32 flags;
    __s32 err;
};
struct chopin_susfs_cmdline { char value[8192]; __s32 err; };
#endif
