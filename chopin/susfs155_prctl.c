/* SPDX-License-Identifier: GPL-3.0-only */
/* Native ARM64 control ABI used by the pinned SUSFS v1.5.5 userspace tool. */
extern void susfs_run_try_umount_for_current_mnt_ns(void);

int chopin_susfs_prctl(unsigned long cmd, unsigned long data,
                       unsigned long unused, unsigned long result)
{
    void __user *arg = (void __user *)data;
    int __user *out = (int __user *)result;
    int error = -EOPNOTSUPP;
    u64 features = 0;

    if (current_uid().val != 0)
        return -EPERM;
    if (!out || !access_ok(VERIFY_WRITE, out, sizeof(*out)))
        return -EFAULT;
#ifdef CONFIG_COMPAT
    /* The legacy structs contain native unsigned long. Do not reinterpret ARM32. */
    if (is_compat_task())
        goto reply;
#endif
    switch (cmd) {
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
    case CMD_SUSFS_ADD_SUS_PATH:
        error = susfs_add_sus_path(arg);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
    case CMD_SUSFS_ADD_SUS_MOUNT:
        error = susfs_add_sus_mount(arg);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
    case CMD_SUSFS_ADD_SUS_KSTAT:
    case CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY:
        error = susfs_add_sus_kstat(arg);
        break;
    case CMD_SUSFS_UPDATE_SUS_KSTAT:
        error = susfs_update_sus_kstat(arg);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
    case CMD_SUSFS_ADD_TRY_UMOUNT:
        error = susfs_add_try_umount(arg);
        break;
    case CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS:
        susfs_run_try_umount_for_current_mnt_ns();
        error = 0;
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
    case CMD_SUSFS_SET_UNAME:
        error = susfs_set_uname(arg);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
    case CMD_SUSFS_ENABLE_LOG:
        if (data > 1) {
            error = -EINVAL;
            break;
        }
        susfs_set_log(data != 0);
        error = 0;
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    case CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG:
        error = susfs_set_cmdline_or_bootconfig(arg);
        break;
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
    case CMD_SUSFS_ADD_OPEN_REDIRECT:
        error = susfs_add_open_redirect(arg);
        break;
#endif
    case CMD_SUSFS_SHOW_VERSION:
        error = copy_to_user(arg, SUSFS_VERSION, sizeof(SUSFS_VERSION)) ? -EFAULT : 0;
        break;
    case CMD_SUSFS_SHOW_VARIANT:
        error = copy_to_user(arg, SUSFS_VARIANT, sizeof(SUSFS_VARIANT)) ? -EFAULT : 0;
        break;
    case CMD_SUSFS_SHOW_ENABLED_FEATURES:
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
        features |= 1ULL << 0;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
        features |= 1ULL << 1;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
        features |= 1ULL << 2;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
        features |= 1ULL << 3;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
        features |= 1ULL << 4;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_OVERLAYFS
        features |= 1ULL << 5;
#endif
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
        features |= 1ULL << 6;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
        features |= 1ULL << 7;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
        features |= 1ULL << 8;
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
        features |= 1ULL << 9;
#endif
#ifdef CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
        features |= 1ULL << 10;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
        features |= 1ULL << 11;
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
        features |= 1ULL << 12;
#endif
#ifdef CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT
        features |= 1ULL << 14;
#endif
        error = copy_to_user(arg, &features, sizeof(features)) ? -EFAULT : 0;
        break;
    }
#ifdef CONFIG_COMPAT
reply:
#endif
    if (copy_to_user(out, &error, sizeof(error)))
        return -EFAULT;
    return error < 0 ? error : 0;
}
