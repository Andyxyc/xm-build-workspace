#!/usr/bin/env python3
"""Port the actual v1.5.5 Kconfig, prctl ABI and per-task mount policy to builtin."""
from pathlib import Path
import re
import sys

root=Path(sys.argv[1]).resolve()
susfs=Path(sys.argv[2]).resolve()
ksu=root/'KernelSU/kernel'

def edit(file,old,new):
    s=file.read_text()
    assert s.count(old)==1, f'{file}: anchor count {s.count(old)}'
    file.write_text(s.replace(old,new,1))

assert '#define SUSFS_VERSION "v1.5.5"' in (root/'include/linux/susfs.h').read_text()
assert 'VERSION = 4\nPATCHLEVEL = 14\n' in (root/'Makefile').read_text()

# Reuse the existing bounded no-fault string reader. The pinned builder also
# dereferences USER_ARG_NULL unconditionally, but the SUSFS branch takes a pointer.
f=ksu/'sulog/event.c'
edit(f,'            strncpy_from_user_nofault(arg,',
     '            ksu_strncpy_from_user_nofault(arg,')
edit(f,'#define USER_ARG_NULL (*user_arg_null_ptr())',
     '#ifdef CONFIG_KSU_SUSFS\n#define USER_ARG_NULL user_arg_null_ptr()\n'
     '#else\n#define USER_ARG_NULL (*user_arg_null_ptr())\n#endif')

f=ksu/'kernel_compat.h';s=f.read_text();anchor='#ifndef __KSU_H_KERNEL_COMPAT\n#define __KSU_H_KERNEL_COMPAT\n'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'''
static inline void *chopin_kvcalloc(size_t count, size_t size, gfp_t flags)
{
    if (size && count > SIZE_MAX / size)
        return NULL;
    return kvzalloc(count * size, flags);
}
''',1);f.write_text(s)
f=ksu/'supercall/dispatch.c';s=f.read_text();assert s.count('kvcalloc(')==2
f.write_text(s.replace('kvcalloc(', 'chopin_kvcalloc('))
patch=(susfs/'kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch').read_text()
section=patch[:patch.index('diff --git a/kernel/Makefile')]
legacy='\n'.join(l[1:] for l in section.splitlines() if l.startswith('+') and not l.startswith('+++')).strip()+'\n'
assert legacy.startswith('menu "KernelSU - SUSFS"') and legacy.endswith('endmenu\n')
f=ksu/'Kconfig';s=f.read_text();start=s.index('menu "KernelSU - SUSFS"');end=s.index('endmenu',start)+len('endmenu')
f.write_text(s[:start]+legacy.rstrip()+s[end:])

# Replace the previous partial reboot shim with the existing fd transport only.
# The native v1.5.5 tool uses prctl(0xDEADBEEF, command, data, 0, result).
f=ksu/'supercall/dispatch.c';s=f.read_text()
start=s.index('#ifdef CONFIG_KSU_SUSFS\n#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)')
end=s.index('\nstatic int do_nuke_ext4_sysfs',start)
s=s[:start]+'''#ifdef CONFIG_KSU_SUSFS
int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg)
{
    if ((u32)magic1 != KSU_INSTALL_MAGIC1 || (u32)magic2 != KSU_INSTALL_MAGIC2)
        return -EINVAL;
    if (!arg || !*arg || IS_ERR(*arg))
        return -EFAULT;
    return ksu_supercall_reboot_handler(arg);
}
#endif
'''+s[end:];f.write_text(s)
f=ksu/'supercall/supercall.c';s=f.read_text()
start=s.index('int ksu_supercall_reboot_handler(void __user **arg)')
end=s.index('\n#else',start)
s=s[:start]+'''int ksu_supercall_reboot_handler(void __user **arg)
{
    if (!arg || !*arg || !access_ok(VERIFY_WRITE, *arg, sizeof(int)))
        return -EFAULT;
    return ksu_handle_fd_request(*arg);
}
'''+s[end:];f.write_text(s)
f=root/'kernel/reboot.c'
edit(f,'\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);',
     '\tif ((u32)magic1 == 0xDEADBEEFu && (u32)magic2 == 0xCAFEBABEu)\n'
     '\t\treturn ksu_handle_sys_reboot(magic1, magic2, cmd, &arg);')

(ksu/'chopin_susfs155_prctl.c').write_text((Path(__file__).parent/'susfs155_prctl.c').read_text())
edit(ksu/'ksu_main.c','#include "supercall/dispatch.c"',
     '#include "chopin_susfs155_prctl.c"\n#include "supercall/dispatch.c"')
f=root/'kernel/sys.c';s=f.read_text();anchor='SYSCALL_DEFINE5(prctl, int, option, unsigned long, arg2, unsigned long, arg3,'
assert s.count(anchor)==1
s=s.replace(anchor,'#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)\n'
    'extern int chopin_susfs_prctl(unsigned long, unsigned long, unsigned long, unsigned long);\n'
    '#endif\n'+anchor,1)
anchor='\terror = security_task_prctl(option, arg2, arg3, arg4, arg5);'
assert s.count(anchor)==1
s=s.replace(anchor,'#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)\n'
    '\tif ((u32)option == 0xDEADBEEFu)\n'
    '\t\treturn chopin_susfs_prctl(arg2, arg3, arg4, arg5);\n#endif\n\n'+anchor,1)
f.write_text(s)

# v1.5.5 has one task-state bit; v2-only no-su flags and extra-work queues
# are deliberately not mapped to fictitious helpers. Install the real LSM path.
f=ksu/'hook/lsm_hook.c';s=f.read_text();start=s.index('#ifdef CONFIG_KSU_SUSFS\n');end=s.index('\n#else\nstatic int ksu_task_fix_setuid',start)
legacy_lsm='''#ifdef CONFIG_KSU_SUSFS
extern u32 susfs_zygote_sid;
extern u32 susfs_zygote_next_sid;
extern void disable_seccomp(void);
extern void susfs_try_umount_all(uid_t uid);
static int ksu_task_fix_setuid(struct cred *new, const struct cred *old, int flags)
{
    uid_t uid;
    bool zygote_next;
    if (!new || !old || old->uid.val != 0)
        return 0;
    if (!susfs_is_sid_equal(old, susfs_zygote_sid) &&
        !susfs_is_sid_equal(old, susfs_zygote_next_sid))
        return 0;
    uid = new->uid.val;
    zygote_next = susfs_is_sid_equal(old, susfs_zygote_next_sid);
    if (is_uid_manager(uid)) {
        disable_seccomp();
        ksu_install_fd();
        return 0;
    }
    if (ksu_is_allow_uid_for_current(uid)) {
        disable_seccomp();
        return 0;
    }
    if (!is_appuid(uid) && !is_isolated_process(uid))
        return 0;
    task_lock(current);
    current->susfs_task_state |= TASK_STRUCT_NON_ROOT_USER_APP_PROC;
    task_unlock(current);
    /* zygote_next still owns the init mount namespace: never unmount there. */
    if (!zygote_next && (ksu_uid_should_umount(uid) || is_isolated_process(uid)))
        susfs_try_umount_all(uid);
    return 0;
}
'''
f.write_text(s[:start]+legacy_lsm+s[end:])
edit(f,'#ifndef CONFIG_KSU_SUSFS\n    LSM_HOOK_INIT(task_fix_setuid, ksu_task_fix_setuid),\n#endif',
     '    LSM_HOOK_INIT(task_fix_setuid, ksu_task_fix_setuid),')
edit(ksu/'feature/sucompat.c','        susfs_set_current_proc_no_su();',
     '        /* v1.5.5 does not have the v2 no-sucompat shortcut flag. */')

# Restore the legacy unmount entry points with real path/namespace validation.
f=ksu/'feature/kernel_umount.c';s=f.read_text();anchor='struct umount_tw {'
assert s.count(anchor)==1
adapter='''extern bool susfs_is_mnt_devname_ksu(struct path *path);
void ksu_try_umount(const char *mnt, bool check_mnt, int flags, uid_t uid)
{
    struct path path;
    if (kern_path(mnt, 0, &path))
        return;
    if (path.dentry != path.mnt->mnt_root ||
        (check_mnt && !susfs_is_mnt_devname_ksu(&path))) {
        path_put(&path);
        return;
    }
    ksu_umount_mnt(mnt, &path, flags);
}

void susfs_try_umount_all(uid_t uid)
{
    const struct cred *saved;
    if (!ksu_cred || !ksu_kernel_umount_enabled)
        return;
    saved = override_creds(ksu_cred);
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    susfs_try_umount(uid);
#endif
    revert_creds(saved);
    ksu_handle_umount(current_uid().val, uid);
}

'''
s=s.replace(anchor,adapter+anchor,1);f.write_text(s)

# Harden strings after the core copies its own snapshot (no double-fetch check).
f=root/'fs/susfs.c';s=f.read_text()
checks={
 'susfs_add_sus_path':['target_pathname'],
 'susfs_add_sus_mount':['target_pathname'],
 'susfs_add_sus_kstat':['target_pathname'],
 'susfs_update_sus_kstat':['target_pathname'],
 'susfs_add_try_umount':['target_pathname'],
 'susfs_add_open_redirect':['target_pathname','redirected_pathname'],
 'susfs_set_uname':['release','version'],
}
for func,fields in checks.items():
    start=s.index('int '+func+'(');end=s.index('\n}',start);part=s[start:end]
    copy=part.index('copy_from_user(&info, user_info, sizeof(')
    endcopy=part.index('\n\t}',copy)+len('\n\t}')
    guard='\n'+''.join('\tif (!memchr(info.'+field+", '\\0', sizeof(info."+field+')))\n\t\treturn -EINVAL;\n' for field in fields)
    if func=='susfs_add_try_umount':
        guard+='\tif (info.mnt_mode != TRY_UMOUNT_DEFAULT && info.mnt_mode != TRY_UMOUNT_DETACH)\n\t\treturn -EINVAL;\n'
    part=part[:endcopy]+guard+part[endcopy:];s=s[:start]+part+s[end:]
f.write_text(s)

# This legacy setter originally copied faultable user memory under a spinlock.
# Serialize only the published string; the copy and allocation can sleep safely.
f=root/'fs/susfs.c';s=f.read_text()
start=s.index('static char *fake_cmdline_or_bootconfig = NULL;')
end=s.index('\n#endif',s.index('int susfs_spoof_cmdline_or_bootconfig(',start))
s=s[:start]+'''static char *fake_cmdline_or_bootconfig;
static DEFINE_MUTEX(susfs_cmdline_lock);
int susfs_set_cmdline_or_bootconfig(char __user *user_string)
{
    char *replacement, *previous;
    replacement = strndup_user(user_string, SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE);
    if (IS_ERR(replacement))
        return PTR_ERR(replacement);
    mutex_lock(&susfs_cmdline_lock);
    previous = fake_cmdline_or_bootconfig;
    fake_cmdline_or_bootconfig = replacement;
    mutex_unlock(&susfs_cmdline_lock);
    kfree(previous);
    return 0;
}

int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m)
{
    int ret = 1;
    mutex_lock(&susfs_cmdline_lock);
    if (fake_cmdline_or_bootconfig) {
        seq_puts(m, fake_cmdline_or_bootconfig);
        ret = 0;
    }
    mutex_unlock(&susfs_cmdline_lock);
    return ret;
}
'''+s[end:];f.write_text(s)
print('Applied native SUSFS 1.5.5 ABI, real task/umount policy, fd error propagation and bounded strings')
