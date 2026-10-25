/* SPDX-License-Identifier: GPL-2.0 */
/* Typed SukiSU transport backed by the actual pinned SUSFS v1.5.5 core. */
#ifdef CONFIG_KSU_SUSFS
#include <linux/susfs.h>
#include <linux/chopin_susfs_state.h>
#include "chopin_susfs_typed_abi.h"

#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
extern bool chopin_susfs_hide_mounts;
#endif

static int chopin_susfs_typed_error(void __user *arg, size_t offset, int error)
{
    int __user *result;
    if (!arg || offset > 8192 ||
        !access_ok(VERIFY_WRITE, arg, offset + sizeof(*result)))
        return -EFAULT;
    result = (int __user *)((char __user *)arg + offset);
    if (error > 0)
        error = -EIO; /* Legacy core has a few generic positive failure returns. */
    if (put_user(error, result))
        return -EFAULT;
    return error;
}

#define CHOPIN_TYPED_GET(type) \
    struct type *p; \
    int error; \
    if (!arg || !access_ok(VERIFY_WRITE, arg, sizeof(*p))) return -EFAULT; \
    p = memdup_user(arg, sizeof(*p)); \
    if (IS_ERR(p)) return PTR_ERR(p)
#define CHOPIN_TYPED_DONE(type) \
    do { kfree(p); return chopin_susfs_typed_error(arg, offsetof(struct type, err), error); } while (0)

static int chopin_susfs_typed_ino(const char *pathname, unsigned long *ino)
{
    struct path path;
    struct inode *inode;
    int error;
    if (!memchr(pathname, 0, 256) || !pathname[0])
        return -EINVAL;
    error = kern_path(pathname, LOOKUP_FOLLOW, &path);
    if (error)
        return error;
    inode = d_inode(path.dentry);
    if (inode)
        *ino = inode->i_ino;
    else
        error = -ENOENT;
    path_put(&path);
    return error;
}

static noinline int chopin_susfs_typed_path(void __user *arg)
{
    CHOPIN_TYPED_GET(chopin_susfs_path);
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    {
        struct st_susfs_sus_path info = {0};
        memcpy(info.target_pathname, p->target_pathname, sizeof(info.target_pathname));
        error = chopin_susfs_typed_ino(info.target_pathname, &info.target_ino);
        if (!error)
            error = susfs_add_sus_path_kern(&info);
    }
#else
    error = -EOPNOTSUPP;
#endif
    CHOPIN_TYPED_DONE(chopin_susfs_path);
}

static noinline int chopin_susfs_typed_uname(void __user *arg)
{
    CHOPIN_TYPED_GET(chopin_susfs_uname);
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
    {
        struct st_susfs_uname info;
        memcpy(info.release, p->release, sizeof(info.release));
        memcpy(info.version, p->version, sizeof(info.version));
        error = susfs_set_uname_kern(&info);
    }
#else
    error = -EOPNOTSUPP;
#endif
    CHOPIN_TYPED_DONE(chopin_susfs_uname);
}

static noinline int chopin_susfs_typed_cmdline(void __user *arg)
{
    CHOPIN_TYPED_GET(chopin_susfs_cmdline);
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    if (!memchr(p->value, 0, sizeof(p->value)))
        error = -EINVAL;
    else
        error = susfs_set_cmdline_or_bootconfig_kern(p->value);
#else
    error = -EOPNOTSUPP;
#endif
    CHOPIN_TYPED_DONE(chopin_susfs_cmdline);
}

static noinline int chopin_susfs_typed_redirect(void __user *arg)
{
    CHOPIN_TYPED_GET(chopin_susfs_redirect);
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
    {
        struct st_susfs_open_redirect info = {0};
        memcpy(info.target_pathname, p->target_pathname, sizeof(info.target_pathname));
        memcpy(info.redirected_pathname, p->redirected_pathname, sizeof(info.redirected_pathname));
        if (p->uid_scheme > 4 ||
            !memchr(info.redirected_pathname, 0, sizeof(info.redirected_pathname)))
            error = -EINVAL;
        else {
            error = chopin_susfs_typed_ino(info.target_pathname, &info.target_ino);
            if (!error)
                error = susfs_add_open_redirect_kern(&info, p->uid_scheme);
        }
    }
#else
    error = -EOPNOTSUPP;
#endif
    CHOPIN_TYPED_DONE(chopin_susfs_redirect);
}

static noinline int chopin_susfs_typed_kstat(unsigned int cmd, void __user *arg)
{
    CHOPIN_TYPED_GET(chopin_susfs_kstat);
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    {
        struct st_susfs_sus_kstat info = {0};
        if (p->is_statically > 1 || p->flags & ~0xfffU ||
            p->spoofed_size > 0x7fffffffffffffffULL || p->spoofed_blksize < 0 ||
            p->spoofed_atime_tv_nsec > 999999999ULL ||
            p->spoofed_mtime_tv_nsec > 999999999ULL ||
            p->spoofed_ctime_tv_nsec > 999999999ULL) {
            error = -EINVAL;
            goto kstat_done;
        }
        info.is_statically = p->is_statically;
        memcpy(info.target_pathname, p->target_pathname, sizeof(info.target_pathname));
        info.spoofed_ino = p->spoofed_ino;
        info.spoofed_dev = p->spoofed_dev;
        info.spoofed_nlink = p->spoofed_nlink;
        info.spoofed_size = p->spoofed_size;
        info.spoofed_atime_tv_sec = p->spoofed_atime_tv_sec;
        info.spoofed_atime_tv_nsec = p->spoofed_atime_tv_nsec;
        info.spoofed_mtime_tv_sec = p->spoofed_mtime_tv_sec;
        info.spoofed_mtime_tv_nsec = p->spoofed_mtime_tv_nsec;
        info.spoofed_ctime_tv_sec = p->spoofed_ctime_tv_sec;
        info.spoofed_ctime_tv_nsec = p->spoofed_ctime_tv_nsec;
        info.spoofed_blocks = p->spoofed_blocks;
        info.spoofed_blksize = p->spoofed_blksize;
        error = chopin_susfs_typed_ino(info.target_pathname, &info.target_ino);
        if (!error) {
            if (cmd == 0x55571)
                error = susfs_update_sus_kstat_typed_kern(&info, p->flags);
            else
                error = susfs_add_sus_kstat_kern(&info);
        }
    }
kstat_done:
#else
    error = -EOPNOTSUPP;
#endif
    CHOPIN_TYPED_DONE(chopin_susfs_kstat);
}

static noinline int chopin_susfs_typed_toggle(unsigned int cmd, void __user *arg)
{
    CHOPIN_TYPED_GET(chopin_susfs_toggle);
    if (p->enabled > 1) {
        error = -EINVAL;
        goto toggle_done;
    }
    error = -EOPNOTSUPP;
    switch (cmd) {
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
    case 0x555a0:
        susfs_set_log(p->enabled != 0);
        error = 0;
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
    case 0x55561:
        WRITE_ONCE(chopin_susfs_hide_mounts, p->enabled != 0);
        error = 0;
        break;
#endif
#ifdef CHOPIN_AVC_SPOOF_SUPPORTED
    case 0x60010:
        error = chopin_avc_feature_set(p->enabled);
        break;
#endif
    }
toggle_done:
    CHOPIN_TYPED_DONE(chopin_susfs_toggle);
}

static const char chopin_susfs_feature_names[] =
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    "CONFIG_KSU_SUSFS_SUS_PATH\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
    "CONFIG_KSU_SUSFS_SUS_MOUNT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
    "CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
    "CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    "CONFIG_KSU_SUSFS_SUS_KSTAT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    "CONFIG_KSU_SUSFS_TRY_UMOUNT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
    "CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
    "CONFIG_KSU_SUSFS_SPOOF_UNAME\n"
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
    "CONFIG_KSU_SUSFS_ENABLE_LOG\n"
#endif
#ifdef CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
    "CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS\n"
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    "CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n"
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
    "CONFIG_KSU_SUSFS_OPEN_REDIRECT\n"
#endif
#ifdef CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT
    "CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT\n"
#endif
#ifdef CHOPIN_AVC_SPOOF_SUPPORTED
    "CONFIG_KSU_SUSFS_SPOOF_AVC_LOG\n"
#endif
    "";

int chopin_susfs_typed_reboot(unsigned int cmd, void __user *arg)
{
    if (current_uid().val != 0)
        return -EPERM;
    BUILD_BUG_ON(sizeof(struct chopin_susfs_version) != 20);
    BUILD_BUG_ON(offsetof(struct chopin_susfs_uname, err) != 132);
    BUILD_BUG_ON(sizeof(struct chopin_susfs_redirect) != 520);
    BUILD_BUG_ON(sizeof(struct chopin_susfs_kstat) != 376);
    BUILD_BUG_ON(offsetof(struct chopin_susfs_kstat, err) != 372);
    BUILD_BUG_ON(sizeof(chopin_susfs_feature_names) > 8192);
    switch (cmd) {
    case 0x555e1: {
        struct chopin_susfs_version reply = {0};
        strlcpy(reply.value, SUSFS_VERSION, sizeof(reply.value));
        return copy_to_user(arg, &reply, sizeof(reply)) ? -EFAULT : 0;
    }
    case 0x555e3: {
        struct chopin_susfs_variant reply = {0};
        strlcpy(reply.value, SUSFS_VARIANT, sizeof(reply.value));
        return copy_to_user(arg, &reply, sizeof(reply)) ? -EFAULT : 0;
    }
    case 0x555e2: {
        struct chopin_susfs_features *reply = kzalloc(sizeof(*reply), GFP_KERNEL);
        int error;
        if (!reply)
            return -ENOMEM;
        strlcpy(reply->value, chopin_susfs_feature_names, sizeof(reply->value));
        error = copy_to_user(arg, reply, sizeof(*reply)) ? -EFAULT : 0;
        kfree(reply);
        return error;
    }
    case 0x55550: return chopin_susfs_typed_path(arg);
    case 0x55570:
    case 0x55571:
    case 0x55572: return chopin_susfs_typed_kstat(cmd, arg);
    case 0x55590: return chopin_susfs_typed_uname(arg);
    case 0x555b0: return chopin_susfs_typed_cmdline(arg);
    case 0x555c0: return chopin_susfs_typed_redirect(arg);
    case 0x55561:
    case 0x555a0:
    case 0x60010: return chopin_susfs_typed_toggle(cmd, arg);
    case 0x55553: /* Persistent path-loop tracking is not part of v1.5.5. */
    case 0x60020: /* v2.1 sus_map has no equivalent in this pinned core. */
        return chopin_susfs_typed_error(arg, offsetof(struct chopin_susfs_path, err), -EOPNOTSUPP);
    default: return -EOPNOTSUPP;
    }
}
#undef CHOPIN_TYPED_GET
#undef CHOPIN_TYPED_DONE
#endif /* CONFIG_KSU_SUSFS */
