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
if (kpm.parent/'bridge.h').is_file():
    old='access_ok(u64_to_user_ptr(cmd.result_code), sizeof(result))'
    new='access_ok(VERIFY_WRITE, u64_to_user_ptr(cmd.result_code), sizeof(result))'
    assert src.count(old)==1
    kpm.write_text(src.replace(old,new,1))
    print('Current KPM bridge: 4.14 output-pointer validation retained')
else:
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

# Linux 4.14 SUSFS v1.5.5 has a different userspace ABI from the 2026
# SukiSU builtin v2-style reboot dispatcher. Preserve old core functions,
# expose only verified legacy-safe operations, and reject modern-only ones.
change("KernelSU/kernel/policy/feature.c",
       '    [KSU_FEATURE_SELINUX_HIDE] = "selinux_hide",',
       '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n'
       '    [KSU_FEATURE_SELINUX_HIDE] = "selinux_hide",\n#endif',
       "SELinux-hide feature gated consistently with its enum")

change("KernelSU/kernel/supercall/dispatch.c",
       '#ifdef CONFIG_KSU_SUSFS\n            susfs_start_sdcard_monitor_fn();\n#endif',
       '#if defined(CONFIG_KSU_SUSFS) && LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n'
       '            susfs_start_sdcard_monitor_fn();\n#endif',
       "v2-only SD-card monitor excluded on v1.5.5")

dispatch=kernel/"KernelSU/kernel/supercall/dispatch.c"
code=dispatch.read_text()
start='''#ifdef CONFIG_KSU_SUSFS
int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg)
'''
finish='\n#endif\n\nstatic int do_nuke_ext4_sysfs'
assert code.count(start)==1, "cannot find SukiSU reboot handler to port"
assert code.count(finish)==1, "unexpected SukiSU reboot handler trailing section"
before=code.index(start)
after=code.index(finish,before)
existing=code[before+len('#ifdef CONFIG_KSU_SUSFS\n'):after]
assert existing.count('SUSFS_MAGIC')==1 and 'ksu_supercall_reboot_handler' in existing

legacy=String if False else r'''
static bool chopin_susfs_legacy_path_ok(const char *name, size_t maxlen)
{
    return name[0] == '/' && memchr(name, '\0', maxlen) != NULL;
}

int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd,
                          void __user **arg)
{
    if (magic1 != KSU_INSTALL_MAGIC1)
        return -EINVAL;

    if (magic2 == KSU_INSTALL_MAGIC2)
        return ksu_supercall_reboot_handler(arg);

    if ((u32)magic2 != 0xFAFAFAFAu || current_uid().val != 0)
        return -EINVAL;
    if (!arg || !*arg)
        return -EFAULT;

    switch (cmd) {
    case CMD_SUSFS_SHOW_VERSION: {
        struct { char version[16]; int err; } v = {
            .version = SUSFS_VERSION, .err = 0
        };
        return copy_to_user(*arg, &v, sizeof(v)) ? -EFAULT : 0;
    }
    case CMD_SUSFS_SHOW_VARIANT: {
        struct { char variant[16]; int err; } v = {
            .variant = SUSFS_VARIANT, .err = 0
        };
        return copy_to_user(*arg, &v, sizeof(v)) ? -EFAULT : 0;
    }
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    case CMD_SUSFS_ADD_SUS_PATH: {
        struct st_susfs_sus_path info;
        if (copy_from_user(&info, *arg, sizeof(info)))
            return -EFAULT;
        if (!info.target_ino ||
            !chopin_susfs_legacy_path_ok(info.target_pathname,
                                          sizeof(info.target_pathname)))
            return -EINVAL;
        return susfs_add_sus_path((struct st_susfs_sus_path __user *)*arg);
    }
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
    case CMD_SUSFS_ADD_SUS_MOUNT: {
        struct st_susfs_sus_mount info;
        if (copy_from_user(&info, *arg, sizeof(info)))
            return -EFAULT;
        if (!chopin_susfs_legacy_path_ok(info.target_pathname,
                                          sizeof(info.target_pathname)))
            return -EINVAL;
        return susfs_add_sus_mount((struct st_susfs_sus_mount __user *)*arg);
    }
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
    case CMD_SUSFS_SET_UNAME:
        return susfs_set_uname((struct st_susfs_uname __user *)*arg);
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    case CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG:
        return susfs_set_cmdline_or_bootconfig((char __user *)*arg);
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
    case CMD_SUSFS_ADD_OPEN_REDIRECT: {
        struct st_susfs_open_redirect info;
        if (copy_from_user(&info, *arg, sizeof(info)))
            return -EFAULT;
        if (!info.target_ino ||
            !chopin_susfs_legacy_path_ok(info.target_pathname,
                                          sizeof(info.target_pathname)) ||
            !chopin_susfs_legacy_path_ok(info.redirected_pathname,
                                          sizeof(info.redirected_pathname)))
            return -EINVAL;
        return susfs_add_open_redirect(
                     (struct st_susfs_open_redirect __user *)*arg);
    }
#endif
    default:
        /* SUSFS v2-only commands are not implemented by v1.5.5. */
        return -EOPNOTSUPP;
    }
}
'''
new='#ifdef CONFIG_KSU_SUSFS\n#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)\n'+legacy+'\n#else\n'+existing+'\n#endif'
code=code[:before]+new+code[after:]
dispatch.write_text(code)
print("SUSFS v1.5.5 legacy-safe reboot controls integrated; modern v2 commands rejected.")
