/* SPDX-License-Identifier: GPL-2.0 */
/* Included in fs/susfs.c so both control transports share the real lists. */
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
bool chopin_susfs_hide_mounts __read_mostly = true;
#endif

#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
/* flags select the ORIGINAL spoofed members to retain during a rebind. */
int susfs_update_sus_kstat_typed_kern(const struct st_susfs_sus_kstat *snapshot,
                                     u32 flags)
{
    struct st_susfs_sus_kstat info = *snapshot;
    struct st_susfs_sus_kstat_hlist *new_entry, *entry;
    struct hlist_node *tmp;
    int bkt, error = -ENOENT;

    if (flags & ~0xfffU ||
        !memchr(info.target_pathname, 0, sizeof(info.target_pathname)))
        return -EINVAL;
    new_entry = kzalloc(sizeof(*new_entry), GFP_KERNEL);
    if (!new_entry)
        return -ENOMEM;
    /* Path lookup and allocation can sleep. Neither runs under the list lock. */
    if (susfs_update_sus_kstat_inode(info.target_pathname)) {
        kfree(new_entry);
        return -ENOENT;
    }
#if defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_COMPAT_STAT64)
#ifdef CONFIG_MIPS
    info.spoofed_dev = new_decode_dev(info.spoofed_dev);
#else
    info.spoofed_dev = huge_decode_dev(info.spoofed_dev);
#endif
#else
    info.spoofed_dev = old_decode_dev(info.spoofed_dev);
#endif
    spin_lock(&susfs_spin_lock);
    hash_for_each_safe(SUS_KSTAT_HLIST, bkt, tmp, entry, node) {
        if (strcmp(entry->info.target_pathname, info.target_pathname))
            continue;
        new_entry->info = entry->info;
        new_entry->target_ino = info.target_ino;
        new_entry->info.target_ino = info.target_ino;
#define CHOPIN_KSTAT_UPDATE(bit, member) \
        do { if (!(flags & (1U << (bit)))) new_entry->info.member = info.member; } while (0)
        CHOPIN_KSTAT_UPDATE(0, spoofed_ino);
        CHOPIN_KSTAT_UPDATE(1, spoofed_dev);
        CHOPIN_KSTAT_UPDATE(2, spoofed_nlink);
        CHOPIN_KSTAT_UPDATE(3, spoofed_size);
        CHOPIN_KSTAT_UPDATE(4, spoofed_atime_tv_sec);
        CHOPIN_KSTAT_UPDATE(5, spoofed_atime_tv_nsec);
        CHOPIN_KSTAT_UPDATE(6, spoofed_mtime_tv_sec);
        CHOPIN_KSTAT_UPDATE(7, spoofed_mtime_tv_nsec);
        CHOPIN_KSTAT_UPDATE(8, spoofed_ctime_tv_sec);
        CHOPIN_KSTAT_UPDATE(9, spoofed_ctime_tv_nsec);
        CHOPIN_KSTAT_UPDATE(10, spoofed_blocks);
        CHOPIN_KSTAT_UPDATE(11, spoofed_blksize);
#undef CHOPIN_KSTAT_UPDATE
        hash_del(&entry->node);
        hash_add(SUS_KSTAT_HLIST, &new_entry->node, info.target_ino);
        kfree(entry);
        new_entry = NULL;
        error = 0;
        break;
    }
    spin_unlock(&susfs_spin_lock);
    kfree(new_entry);
    return error;
}
#endif

#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
/* UID_SCHEME values from the official SUSFS 2.1 userspace ABI. The native
 * v1.5.5 transport uses -1 to retain its original uid < 2000 semantics. */
static bool chopin_susfs_redirect_uid_matches(int scheme)
{
    uid_t uid = current_uid().val;
    bool umounted = READ_ONCE(chopin_susfs_task_state(current)->task_state) &
                    CHOPIN_SUSFS_TASK_UMOUNTED;
    switch (scheme) {
    case -1: return uid < 2000;
    case 0: return uid % 100000 < 10000;
    case 1: return uid == 0 && !susfs_is_current_ksu_domain();
    case 2: return !susfs_is_current_ksu_domain();
    case 3: return uid % 100000 >= 10000 && umounted;
    case 4: return umounted;
    default: return false;
    }
}
#endif
