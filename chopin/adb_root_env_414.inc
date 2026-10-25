/* SPDX-License-Identifier: GPL-2.0 */
/* Bounded native-ARM64 environment construction for the real ADB-root hook. */
static long setup_ld_preload(void ***envp_user_ptr)
{
    const size_t limit = 4096;
    const char *preload = "LD_PRELOAD=/data/adb/ksu/lib/libadbroot.so";
    const char *libpath = "LD_LIBRARY_PATH=/data/adb/ksu/lib";
    unsigned long envp = (unsigned long)*envp_user_ptr;
    unsigned long stackp = current_user_stack_pointer();
    unsigned long *vector, item;
    size_t i, kept = 0, bytes;
    char head[17], *oldpreload = NULL, *oldpath = NULL;
    char *newpreload = NULL, *newpath = NULL;
    long error = 0;
    if (is_compat_task())
        return -EOPNOTSUPP;
    vector = kmalloc_array(limit + 3, sizeof(*vector), GFP_KERNEL);
    if (!vector)
        return -ENOMEM;
    for (i = 0; i < limit; ++i) {
        long length;
        if (copy_from_user(&item, (void __user *)(envp + i * sizeof(item)), sizeof(item))) {
            error = -EFAULT;
            goto done;
        }
        if (!item)
            break;
        memset(head, 0, sizeof(head));
        length = strncpy_from_user(head, (char __user *)item, sizeof(head) - 1);
        if (length < 0) {
            error = -EFAULT;
            goto done;
        }
        if (!strncmp(head, "LD_PRELOAD=", 11)) {
            if (!oldpreload) {
                oldpreload = strndup_user((char __user *)item + 11, limit);
                if (IS_ERR(oldpreload)) { error = PTR_ERR(oldpreload); oldpreload = NULL; goto done; }
            }
        } else if (!strncmp(head, "LD_LIBRARY_PATH=", 16)) {
            if (!oldpath) {
                oldpath = strndup_user((char __user *)item + 16, limit);
                if (IS_ERR(oldpath)) { error = PTR_ERR(oldpath); oldpath = NULL; goto done; }
            }
        } else {
            vector[kept++] = item;
        }
    }
    if (i == limit) { error = -E2BIG; goto done; }
    newpreload = kasprintf(GFP_KERNEL, "%s%s%s", preload,
                          oldpreload && *oldpreload ? ":" : "", oldpreload ? oldpreload : "");
    newpath = kasprintf(GFP_KERNEL, "%s%s%s", libpath,
                       oldpath && *oldpath ? ":" : "", oldpath ? oldpath : "");
    if (!newpreload || !newpath) { error = -ENOMEM; goto done; }
    bytes = strlen(newpreload) + 1;
    stackp = ALIGN_DOWN(stackp - bytes, 8);
    if (copy_to_user((void __user *)stackp, newpreload, bytes)) { error = -EFAULT; goto done; }
    vector[kept++] = stackp;
    bytes = strlen(newpath) + 1;
    stackp = ALIGN_DOWN(stackp - bytes, 8);
    if (copy_to_user((void __user *)stackp, newpath, bytes)) { error = -EFAULT; goto done; }
    vector[kept++] = stackp;
    vector[kept++] = 0;
    bytes = kept * sizeof(*vector);
    stackp = ALIGN_DOWN(stackp - bytes, 16);
    if (copy_to_user((void __user *)stackp, vector, bytes)) { error = -EFAULT; goto done; }
    *envp_user_ptr = (void **)stackp;
done:
    kfree(newpreload); kfree(newpath); kfree(oldpreload); kfree(oldpath); kfree(vector);
    return error;
}
