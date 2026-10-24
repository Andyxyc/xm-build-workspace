#!/usr/bin/env python3
"""Chopin Android 13, Linux 4.14: SukiSU builtin + SUSFS manual hook adaptation.

Use the vendor-owned path lookup, not an incompatible userspace-pointer shim:
CONFIG_KSU_SUSFS changes faccessat/stat hook arguments to struct filename **.
Only touch the two syscall paths needed for sucompat.
"""
from pathlib import Path
import sys

kernel = Path(sys.argv[1]).resolve()

def patch(path, old, new, label, expect=1):
    f = kernel / path
    text = f.read_text()
    if new in text:
        print("already patched:", label)
        return
    count = text.count(old)
    if count != expect:
        raise SystemExit(f"UNMATCHED {label} in {path}: expected {expect}, got {count}")
    f.write_text(text.replace(old, new, expect))
    print("patched:", label)

# execveat: current builtin signature matches this 4.14 vendor implementation.
f = kernel / "fs/exec.c"
s = f.read_text()
i = s.index("static int do_execveat_common(")
end = s.index("\n\tif (IS_ERR(filename))", i)
segment = s[i:end]
if "ksu_handle_execveat(" not in segment:
    anchor = "\n\tint retval;\n"
    assert segment.count(anchor) == 1, "execveat declaration position changed"
    block = """
#ifdef CONFIG_KSU
    extern int ksu_handle_execveat(int *, struct filename **, void *, void *, int *);
    if (!IS_ERR(filename))\n        ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
#endif
"""
    s = s[:i] + segment.replace(anchor, anchor+block,1) + s[end:]
    f.write_text(s)
print("patched/verified: execveat")

# SukiSU builtin has a runtime init.rc proxy that must be reached through vfs_read
# on manually hooked Non-GKI 4.14. Keep a strict per-function insertion point.
f = kernel / "fs/read_write.c"
src = f.read_text()
marker = "ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)"
assert src.count(marker) == 1, "vendor 4.14 vfs_read prototype changed"
start = src.index(marker)
end = src.index("EXPORT_SYMBOL(vfs_read);", start)
section = src[start:end]
if "ksu_handle_vfs_read(" not in section:
    anchor = "\tssize_t ret;\n"
    assert section.count(anchor) == 1, "vendor vfs_read variable anchor changed"
    hook = """
#ifdef CONFIG_KSU
    extern bool ksu_vfs_read_hook __read_mostly;
    extern int ksu_handle_vfs_read(struct file **, char __user **, size_t *, loff_t **);
    if (unlikely(ksu_vfs_read_hook))
        ksu_handle_vfs_read(&file, &buf, &count, &pos);
#endif
"""
    section = section.replace(anchor, anchor + hook, 1)
    src = src[:start] + section + src[end:]
    f.write_text(src)
print("patched/verified: SukiSU init.rc read proxy")

# SukiSU builtin with SUSFS expects struct filename **, NOT
# const char __user **. Interpose before the internal filename_lookup().
namei = kernel / "fs/namei.c"
src = namei.read_text()
marker = "EXPORT_SYMBOL(user_path_at_empty);"
assert src.count(marker) == 1, "namei export anchor changed"
bridge = """
#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)
extern int ksu_handle_faccessat(int *, struct filename **, int *, int *);
extern int ksu_handle_stat(int *, struct filename **, int *);

/* filename_lookup() consumes the struct filename and calls putname(). */
int ksu_user_path_at_faccessat(int dfd, const char __user *name,
                              unsigned int flags, struct path *path, int *mode)
{
    struct filename *fn = getname_flags(name, flags, NULL);
    if (!IS_ERR(fn))
        ksu_handle_faccessat(&dfd, &fn, mode, NULL);
    return filename_lookup(dfd, fn, flags, path, NULL);
}

int ksu_user_path_at_stat(int dfd, const char __user *name,
                          unsigned int flags, struct path *path)
{
    struct filename *fn = getname_flags(name, flags, NULL);
    int ksu_flags = (int)flags;
    if (!IS_ERR(fn))
        ksu_handle_stat(&dfd, &fn, &ksu_flags);
    return filename_lookup(dfd, fn, flags, path, NULL);
}
#endif
"""
if "int ksu_user_path_at_faccessat(" not in src:
    namei.write_text(src.replace(marker,marker+"\n"+bridge,1))
print("patched/verified: SUSFS-compatible pathname bridge")

# Alter only the faccessat syscall's lookup, not all user_path_at callers.
f = kernel/"fs/open.c"; s=f.read_text()
start=s.index("SYSCALL_DEFINE3(faccessat,")
end=s.index("SYSCALL_DEFINE2(access,",start)
section=s[start:end]
original = "\tres = user_path_at(dfd, filename, lookup_flags, &path);"
replacement = """#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)
    res = ksu_user_path_at_faccessat(dfd, filename, lookup_flags, &path, &mode);
#else
    res = user_path_at(dfd, filename, lookup_flags, &path);
#endif"""
if "ksu_user_path_at_faccessat(" not in section:
    assert section.count(original)==1,"faccessat lookup changed"
    section=section.replace(original,replacement,1)
    decl = """#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)
extern int ksu_user_path_at_faccessat(int, const char __user *,
                                     unsigned int, struct path *, int *);
#endif

"""
    s=s[:start]+decl+section+s[end:]
    f.write_text(s)
print("patched/verified: faccessat only")

# vfs_statx is the common 4.14 stat path, including newfstatat.
f=kernel/"fs/stat.c";s=f.read_text()
start=s.index("int vfs_statx(")
end=s.index("EXPORT_SYMBOL(vfs_statx);",start)
section=s[start:end]
original="\terror = user_path_at(dfd, filename, lookup_flags, &path);"
replacement="""#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)
    error = ksu_user_path_at_stat(dfd, filename, lookup_flags, &path);
#else
    error = user_path_at(dfd, filename, lookup_flags, &path);
#endif"""
if "ksu_user_path_at_stat(" not in section:
    assert section.count(original)==1,"statx lookup changed"
    section=section.replace(original,replacement,1)
    decl="""#if defined(CONFIG_KSU) && defined(CONFIG_KSU_SUSFS)
extern int ksu_user_path_at_stat(int, const char __user *,
                                 unsigned int, struct path *);
#endif

"""
    s=s[:start]+decl+section+s[end:]
    f.write_text(s)
print("patched/verified: statx")

# The builder already injects the new reboot supercall and backports
# SukiSU 4.14 incompatibilities. Fail if it stopped doing so.
s=(kernel/"kernel/reboot.c").read_text()
assert "ksu_handle_sys_reboot(" in s, "reboot supercall hook not installed"
print("verified: reboot supercall")

# No touch to camera, ISP, GPU, devicetree, thermal, clock or power drivers.
for path in ("fs/exec.c","fs/open.c","fs/stat.c","fs/namei.c","kernel/reboot.c"):
    assert (kernel/path).exists()
print("Chopin manual hook port completed (source integration, NOT boot verified).")
