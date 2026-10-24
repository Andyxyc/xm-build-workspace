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

# Linux 4.14 access_ok(VERIFY_READ/VERIFY_WRITE, ptr, size) uses three
# arguments; modern SukiSU KPM assumes the two-argument API.
kpm=kernel/"KernelSU/kernel/extension/kpm/kpm.c"
src=kpm.read_text()
kpm_changes=[
    ("access_ok(arg1, 255)", "access_ok(VERIFY_READ, (const void __user *)arg1, 255)", 1),
    ("access_ok(arg2, 255)", "access_ok(VERIFY_READ, (const void __user *)arg2, 255)", 1),
    ("access_ok(arg1, sizeof(s->kernel_name_buffer))",
     "access_ok(VERIFY_READ, (const void __user *)arg1, sizeof(s->kernel_name_buffer))", 2),
    ("access_ok(arg2, size)", "access_ok(VERIFY_WRITE, (void __user *)arg2, size)", 1),
    # LIST: arg1 is the output pointer; arg2 is the length, never a pointer.
    ("access_ok(arg2, len)", "access_ok(VERIFY_WRITE, (void __user *)arg1, len)", 1),
    ("access_ok(arg1, sizeof(s->kpm_name))",
     "access_ok(VERIFY_READ, (const void __user *)arg1, sizeof(s->kpm_name))", 1),
    ("access_ok(arg2, sizeof(s->kpm_args))",
     "access_ok(VERIFY_READ, (const void __user *)arg2, sizeof(s->kpm_args))", 1),
    # control_code is the numeric KPM operation, not a userspace pointer.
    ("access_ok(cmd.control_code, sizeof(int))",
     "(cmd.control_code >= SUKISU_KPM_LOAD && cmd.control_code <= SUKISU_KPM_VERSION)", 1),
    ("access_ok(cmd.result_code, sizeof(int))",
     "access_ok(VERIFY_WRITE, (void __user *)(unsigned long)cmd.result_code, sizeof(int))", 1),
]
for old,new,num in kpm_changes:
    if src.count(old)!=num:
        raise SystemExit(f"KPM 4.14 API changed: {old!r} found {src.count(old)} instead of {num}")
    src=src.replace(old,new)

# Guard scalar control_code range rather than testing it as a pointer.
old="if (!(cmd.control_code >= SUKISU_KPM_LOAD && cmd.control_code <= SUKISU_KPM_VERSION))"
assert src.count(old)==1
src=src.replace(old,"if (cmd.control_code < SUKISU_KPM_LOAD || cmd.control_code > SUKISU_KPM_VERSION)",1)

# KPM LIST must never copy more bytes than its scratch buffer.
old="if (len <= 0) {"
new="if (len <= 0 || (size_t)len > sizeof(s->buf)) {"
assert src.count(old)==1
src=src.replace(old,new,1)

# User-visible data and optional module load arguments must be zero-initialized.
old="struct kpm_scratch *s = kmalloc(sizeof(*s), GFP_KERNEL);"
new="struct kpm_scratch *s = kzalloc(sizeof(*s), GFP_KERNEL);"
assert src.count(old)==1
src=src.replace(old,new,1)

assert "access_ok(arg" not in src and "access_ok(cmd." not in src
kpm.write_text(src)
print("KPM 4.14 pointer API ported with READ/WRITE validation; KPM remains enabled.")
