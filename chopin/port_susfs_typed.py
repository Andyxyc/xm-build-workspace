#!/usr/bin/env python3
"""Share real v1.5.5 core operations with the modern typed reboot transport."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
ksu = root / 'KernelSU/kernel'
core = root / 'fs/susfs.c'
header = root / 'include/linux/susfs.h'
source = core.read_text()
declarations = []

# Both transports copy a single user snapshot, then use the same core logic.
# Never cast the typed layout to the incompatible native legacy layout, and
# never use set_fs(KERNEL_DS) to pass a kernel pointer to copy_from_user().
operations = {
    'susfs_add_sus_path': 'st_susfs_sus_path',
    'susfs_add_sus_mount': 'st_susfs_sus_mount',
    'susfs_add_sus_kstat': 'st_susfs_sus_kstat',
    'susfs_update_sus_kstat': 'st_susfs_sus_kstat',
    'susfs_set_uname': 'st_susfs_uname',
    'susfs_add_open_redirect': 'st_susfs_open_redirect',
}
for function, structure in operations.items():
    signature = f'int {function}(struct {structure}* __user user_info) {{'
    assert source.count(signature) == 1, function
    start = source.index(signature)
    end = source.index('\n}', start) + 2
    part = source[start:end]
    copy = '\tif (copy_from_user(&info, user_info, sizeof(info))) {\n\t\tSUSFS_LOGE("failed copying from userspace\\n");\n\t\treturn 1;\n\t}'
    if function == 'susfs_set_uname':
        copy = copy.replace('sizeof(info)', 'sizeof(struct st_susfs_uname)').replace('userspace\\n', 'userspace.\\n')
    assert part.count(copy) == 1, function
    extra = ', int uid_scheme' if function == 'susfs_add_open_redirect' else ''
    helper = part.replace(signature, f'int {function}_kern(const struct {structure} *snapshot{extra}) {{', 1)
    helper = helper.replace(copy, '\tinfo = *snapshot;', 1)
    if function in ['susfs_add_sus_path', 'susfs_add_sus_kstat', 'susfs_add_open_redirect']:
        # Validate/allocate/mark first; replace the old entry only at publication.
        lock_start = helper.index('\tspin_lock(&susfs_spin_lock);')
        lock_end = helper.index('\tspin_unlock(&susfs_spin_lock);', lock_start) + len('\tspin_unlock(&susfs_spin_lock);')
        retire = helper[lock_start:lock_end]
        helper = helper[:lock_start] + helper[lock_end:]
        publish = helper.index('\tspin_lock(&susfs_spin_lock);')
        inner = retire[len('\tspin_lock(&susfs_spin_lock);'): -len('\tspin_unlock(&susfs_spin_lock);')]
        at = publish + len('\tspin_lock(&susfs_spin_lock);')
        helper = helper[:at] + inner + helper[at:]
    if function == 'susfs_add_open_redirect':
        assert helper.count('new_entry->target_ino = info.target_ino;') == 1
        helper = helper.replace('new_entry->target_ino = info.target_ino;',
                                'new_entry->target_ino = info.target_ino;\n\tnew_entry->uid_scheme = uid_scheme;', 1)
    extra_call = ', -1' if extra else ''
    wrapper = f'''\n\nint {function}(struct {structure}* __user user_info) {{
    struct {structure} info;
    if (copy_from_user(&info, user_info, sizeof(info)))
        return 1;
    return {function}_kern(&info{extra_call});
}}'''
    source = source[:start] + helper + wrapper + source[end:]
    declarations.append((function, structure, extra))

# Share the corrected rebind implementation with native callers as well. Preserve
# native size/blocks sentinel semantics; typed callers use explicit field flags.
start = source.index('int susfs_update_sus_kstat_kern(')
end = source.index('\n}', start) + 2
source = source[:start] + '''int susfs_update_sus_kstat_kern(const struct st_susfs_sus_kstat *snapshot)
{
    u32 keep = 0xfffU;
    if (snapshot->spoofed_size > 0)
        keep &= ~(1U << 3);
    if (snapshot->spoofed_blocks > 0)
        keep &= ~(1U << 10);
    return susfs_update_sus_kstat_typed_kern(snapshot, keep);
}''' + source[end:]

# List readers must finish their snapshots before a writer can retire an entry.
start = source.index('int susfs_sus_ino_for_filldir64(')
end = source.index('\n}', start) + 2
source = source[:start] + '''int susfs_sus_ino_for_filldir64(unsigned long ino)
{
    struct st_susfs_sus_path_hlist *entry;
    int found = 0;
    spin_lock(&susfs_spin_lock);
    hash_for_each_possible(SUS_PATH_HLIST, entry, node, ino) {
        if (entry->target_ino == ino) {
            found = 1;
            break;
        }
    }
    spin_unlock(&susfs_spin_lock);
    return found;
}''' + source[end:]

for function in ['susfs_sus_ino_for_generic_fillattr', 'susfs_sus_ino_for_show_map_vma']:
    start = source.index('void ' + function + '(')
    end = source.index('\n}', start) + 2
    part = source[start:end]
    at = part.index('\thash_for_each_possible(')
    assert 'return;' not in part[:at]
    part = part[:at] + '\tspin_lock(&susfs_spin_lock);\n' + part[at:]
    part = part.replace('return;', 'goto out_read_unlock;')
    part = part[:-2] + '\nout_read_unlock:\n\tspin_unlock(&susfs_spin_lock);\n}'
    source = source[:start] + part + source[end:]

# Redirect lookup copies the string while protected, then allocates its filename
# after releasing the lock. Keep the native UID selection in the new per-entry
# predicate instead of unconditionally redirecting app processes.
start = source.index('struct filename* susfs_get_redirected_path(')
end = source.index('\n}', start) + 2
source = source[:start] + '''struct filename* susfs_get_redirected_path(unsigned long ino)
{
    struct st_susfs_open_redirect_hlist *entry;
    char pathname[SUSFS_MAX_LEN_PATHNAME];
    bool found = false;
    spin_lock(&susfs_spin_lock);
    hash_for_each_possible(OPEN_REDIRECT_HLIST, entry, node, ino) {
        if (entry->target_ino == ino &&
            chopin_susfs_redirect_uid_matches(entry->uid_scheme)) {
            memcpy(pathname, entry->redirected_pathname, sizeof(pathname));
            found = true;
            break;
        }
    }
    spin_unlock(&susfs_spin_lock);
    return found ? getname_kernel(pathname) : ERR_PTR(-ENOENT);
}''' + source[end:]

source = '#include <linux/chopin_susfs_state.h>\n' + source
source = source.replace('static spinlock_t susfs_spin_lock;',
    'static spinlock_t susfs_spin_lock;\n#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT\n'
    'static bool chopin_susfs_redirect_uid_matches(int scheme);\n#endif', 1)

# Terminate the fixed-length path copies even at their maximum accepted length.
source, count = re.subn(r'kmalloc\((sizeof\(struct st_susfs_[a-z_]+\)), GFP_KERNEL\)',
                       r'kzalloc(\1, GFP_KERNEL)', source)
assert count >= 5, count

# The command-line publisher already uses a mutex. Share the final publication
# while keeping each transport's user copy outside it.
start = source.index('int susfs_set_cmdline_or_bootconfig(char __user *user_string)')
end = source.index('\nint susfs_spoof_cmdline_or_bootconfig', start)
old = source[start:end]
assert 'strndup_user(user_string, SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE)' in old
assert 'mutex_lock(&susfs_cmdline_lock)' in old
new = '''static int susfs_publish_cmdline(char *replacement)
{
    char *previous;
    if (IS_ERR(replacement))
        return PTR_ERR(replacement);
    mutex_lock(&susfs_cmdline_lock);
    previous = fake_cmdline_or_bootconfig;
    fake_cmdline_or_bootconfig = replacement;
    mutex_unlock(&susfs_cmdline_lock);
    kfree(previous);
    return 0;
}

int susfs_set_cmdline_or_bootconfig(char __user *user_string)
{
    return susfs_publish_cmdline(strndup_user(user_string,
                                SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE));
}

int susfs_set_cmdline_or_bootconfig_kern(const char *snapshot)
{
    char *copy = kstrndup(snapshot, SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE, GFP_KERNEL);
    return susfs_publish_cmdline(copy ? copy : ERR_PTR(-ENOMEM));
}
'''
source = source[:start] + new + source[end:]
source += '\n#include "chopin_susfs_typed_core.inc"\n'
core.write_text(source)
(root / 'fs/chopin_susfs_typed_core.inc').write_bytes(
    (Path(__file__).parent / 'susfs_typed_core.inc').read_bytes())

h = header.read_text()
for function, structure, extra in declarations:
    old = f'int {function}(struct {structure}* __user user_info);'
    assert h.count(old) == 1, function
    h = h.replace(old, old + f'\nint {function}_kern(const struct {structure} *snapshot{extra});', 1)
anchor = 'struct st_susfs_open_redirect_hlist {'
start = h.index(anchor)
at = h.index('\tstruct hlist_node', start)
h = h[:at] + '\tint uid_scheme;\n' + h[at:]
anchor = 'int susfs_update_sus_kstat(struct st_susfs_sus_kstat* __user user_info);'
h = h.replace(anchor, anchor + '\nint susfs_update_sus_kstat_typed_kern(const struct st_susfs_sus_kstat *snapshot, u32 flags);', 1)
old = 'int susfs_set_cmdline_or_bootconfig(char* __user user_fake_boot_config);'
assert h.count(old) == 1
h = h.replace(old, old + '\nint susfs_set_cmdline_or_bootconfig_kern(const char *snapshot);', 1)
header.write_text(h)

f = root / 'include/linux/chopin_susfs_state.h'
s = f.read_text()
assert '#define CHOPIN_SUSFS_TASK_UMOUNTED' not in s
f.write_text(s.replace('#include <linux/types.h>', '#include <linux/types.h>\n'
                      '#define CHOPIN_SUSFS_TASK_UMOUNTED (1ULL << 63)', 1))
f = ksu / 'feature/kernel_umount.c'
s = f.read_text()
anchor = '    ksu_handle_umount(current_uid().val, uid);'
assert s.count(anchor) == 1
s = '#include <linux/chopin_susfs_state.h>\n' + s
s = s.replace(anchor, anchor + '\n    chopin_susfs_task_state(current)->task_state |= CHOPIN_SUSFS_TASK_UMOUNTED;', 1)
f.write_text(s)
f = root / 'fs/namei.c'
s = f.read_text()
anchor = ' && current_uid().val < 2000) {'
assert s.count(anchor) == 1
f.write_text(s.replace(anchor, ') {', 1))
f = root / 'fs/proc_namespace.c'
s = f.read_text()
anchor = '\tif (unlikely(r->mnt_id >= DEFAULT_SUS_MNT_ID))'
assert s.count(anchor) == 3
s = s.replace(anchor, '\tif (READ_ONCE(chopin_susfs_hide_mounts) && !susfs_is_current_ksu_domain() &&\n'
              '\t    unlikely(r->mnt_id >= DEFAULT_SUS_MNT_ID))')
s = s.replace('#include <linux/susfs_def.h>', '#include <linux/susfs_def.h>\n'
              'extern bool chopin_susfs_hide_mounts;\nextern bool susfs_is_current_ksu_domain(void);', 1)
f.write_text(s)

for name in ['susfs_typed_abi.h', 'susfs_typed_reboot.c']:
    (ksu / ('chopin_' + name)).write_bytes((Path(__file__).parent / name).read_bytes())
f = ksu / 'ksu_main.c'
s = f.read_text()
anchor = '#include "chopin_susfs155_prctl.c"'
assert s.count(anchor) == 1
f.write_text(s.replace(anchor, anchor + '\n#include "chopin_susfs_typed_reboot.c"', 1))
f = root / 'kernel/reboot.c'
s = f.read_text()
anchor = 'SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd,'
assert s.count(anchor) == 1
at = s.index(anchor)
s = s[:at] + '#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)\nextern int chopin_susfs_typed_reboot(unsigned int cmd, void __user *arg);\n#endif\n' + s[at:]
anchor = '\tif ((u32)magic1 == 0xDEADBEEFu && (u32)magic2 == 0xCAFEBABEu)'
assert s.count(anchor) == 1
s = s.replace(anchor, '#ifdef CONFIG_KSU_SUSFS\n\tif ((u32)magic1 == 0xDEADBEEFu && (u32)magic2 == 0xFAFAFAFAu)\n'
              '\t\treturn chopin_susfs_typed_reboot(cmd, arg);\n#endif\n' + anchor, 1)
f.write_text(s)
print('Shared v1.5.5 core snapshots and distinct typed reboot transport integrated')
