#!/usr/bin/env python3
"""Targeted 4.14 source API port after SUSFS v1.5.5 and SukiSU builtin patches."""
from pathlib import Path
import sys
kernel=Path(sys.argv[1]).resolve()

def change(path, old, new, label):
    f=kernel/path
    s=f.read_text()
    if old not in s:
        if new in s:
            print("already ported:",label)
            return
        raise SystemExit(f"4.14 API anchor missing: {path} {label}")
    assert s.count(old)==1, f"Unsafe multiple matches {label}: {s.count(old)}"
    f.write_text(s.replace(old,new,1))
    print("ported:",label)

# Linux static_call was introduced after 4.14. This inclusion is only
# required for newer kernel LSM backends; never fabricate a fake call hook.
change("KernelSU/kernel/kernel_includes.h",
       "#include <linux/static_call.h>",
       "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n#include <linux/static_call.h>\n#endif",
       "static_call header version gating")

# Vendor fs/notify has no inotify_mark_user_mask() helper.
# This kernel already presents exactly mark->mask & IN_ALL_EVENTS for userspace.
change("fs/notify/fdinfo.c",
       "inotify_mark_user_mask(mark)",
       "(mark->mask & IN_ALL_EVENTS)",
       "inotify mark mask semantics")

# d_path() can return ERR_PTR, not NULL. Check ERR_PTR to prevent
# dereference during SUSFS fake-kstat inotify path handling.
change("fs/notify/fdinfo.c",
       "if (!dpath) {",
       "if (IS_ERR(dpath)) {",
       "inotify d_path error handling")

print("chopin 4.14 compatibility ports applied")
